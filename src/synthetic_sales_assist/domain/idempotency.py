"""Generic, process-local idempotency with retained canonical-byte comparison."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import RLock
from typing import ClassVar

from synthetic_sales_assist.domain.canonical import (
    HashBinding,
    HashDomainViolation,
    domain_hash,
    parse_canonical_json_bytes,
    validate_hash_domain,
)
from synthetic_sales_assist.domain.identities import InteractionId
from synthetic_sales_assist.domain.records import (
    ErrorCategory,
    StructuredDomainError,
    StructuredErrorCode,
)
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp


_NAMESPACE = re.compile(r"\A[a-z][a-z0-9_.-]{0,63}\Z", re.ASCII)
_COMPONENT = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z", re.ASCII)
_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z", re.ASCII)
_TOKEN_CONSTRUCTION_TOKEN = object()


class IdempotencyError(RuntimeError):
    """Base non-leaking idempotency failure."""

    ERROR_CATEGORY: ClassVar[ErrorCategory] = ErrorCategory.VALIDATION

    def __init__(self, code: str) -> None:
        invalid_code = False
        try:
            structured_code = StructuredErrorCode(code)
        except (TypeError, ValueError):
            invalid_code = True
            structured_code = StructuredErrorCode.IDEMPOTENCY_ERROR_CODE_INVALID
        if invalid_code:
            code = structured_code.value
        self.code = structured_code.value
        self.structured = StructuredDomainError(structured_code, self.ERROR_CATEGORY)
        super().__init__(structured_code.value)


class IdempotencyDefinitionError(IdempotencyError):
    """A natural key, canonical command, or allocation is invalid."""


class IdempotencyConflictError(IdempotencyError):
    """One natural key was reused for different canonical material."""

    ERROR_CATEGORY = ErrorCategory.CONFLICT


class DigestCollisionError(IdempotencyError):
    """Equal SHA-256 values were presented for different retained bytes."""

    ERROR_CATEGORY = ErrorCategory.COLLISION


@dataclass(frozen=True, slots=True, repr=False)
class NaturalKey:
    """A bounded, immutable command identity; diagnostic output is redacted."""

    namespace: str
    components: tuple[str, ...] = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.namespace) is not str or _NAMESPACE.fullmatch(self.namespace) is None:
            raise IdempotencyDefinitionError("NATURAL_KEY_NAMESPACE_INVALID")
        if type(self.components) is not tuple or not 1 <= len(self.components) <= 8:
            raise IdempotencyDefinitionError("NATURAL_KEY_COMPONENTS_INVALID")
        invalid_component = any(
            type(item) is not str or _COMPONENT.fullmatch(item) is None
            for item in self.components
        )
        if invalid_component:
            raise IdempotencyDefinitionError("NATURAL_KEY_COMPONENTS_INVALID")

    def __repr__(self) -> str:
        return "NaturalKey(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False, init=False)
class CanonicalToken:
    """Domain-separated command digest plus its complete retained canonical bytes."""

    domain: str
    canonical_bytes: bytes = field(repr=False)
    sha256: str

    @classmethod
    def from_command(cls, domain: str, canonical_command: bytes) -> CanonicalToken:
        """Build a production token using SHA-256 over domain, LF, and canonical JSON."""

        _validate_domain(domain)
        _validate_canonical_bytes(canonical_command, "COMMAND_BYTES_INVALID")
        binding = domain_hash(domain, canonical_command)
        return cls._from_validated(
            domain,
            canonical_command,
            binding.sha256,
            _token=_TOKEN_CONSTRUCTION_TOKEN,
        )

    @classmethod
    def _from_validated(
        cls,
        domain: str,
        canonical_command: bytes,
        digest: str,
        *,
        _token: object | None = None,
    ) -> CanonicalToken:
        if _token is not _TOKEN_CONSTRUCTION_TOKEN:
            raise IdempotencyDefinitionError("COMMAND_TOKEN_CONSTRUCTION_INVALID")
        _validate_domain(domain)
        _validate_canonical_bytes(canonical_command, "COMMAND_BYTES_INVALID")
        if type(digest) is not str or _SHA256.fullmatch(digest) is None:
            raise IdempotencyDefinitionError("COMMAND_DIGEST_INVALID")
        instance = object.__new__(cls)
        object.__setattr__(instance, "domain", domain)
        object.__setattr__(instance, "canonical_bytes", canonical_command)
        object.__setattr__(instance, "sha256", digest)
        return instance

    @property
    def preimage(self) -> bytes:
        return self.domain.encode("ascii") + b"\n" + self.canonical_bytes

    def __repr__(self) -> str:
        return f"CanonicalToken(domain={self.domain!r}, sha256={self.sha256!r})"


@dataclass(frozen=True, slots=True, repr=False)
class ReceiptAllocation:
    """Immutable material allocated only after the receipt lookup misses."""

    receipt_id: InteractionId
    recorded_at: CanonicalTimestamp
    result_domain: str
    result_bytes: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.receipt_id) is not InteractionId:
            raise IdempotencyDefinitionError("RECEIPT_ID_INVALID")
        if type(self.recorded_at) is not CanonicalTimestamp:
            raise IdempotencyDefinitionError("RECEIPT_TIMESTAMP_INVALID")
        _validate_domain(self.result_domain)
        _validate_canonical_bytes(self.result_bytes, "RECEIPT_RESULT_INVALID")

    def __repr__(self) -> str:
        return "ReceiptAllocation(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class IdempotencyReceipt:
    """The immutable replay result retained for one accepted natural key."""

    natural_key: NaturalKey = field(repr=False)
    token: CanonicalToken = field(repr=False)
    receipt_id: InteractionId = field(repr=False)
    recorded_at: CanonicalTimestamp
    result: HashBinding = field(repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.natural_key) is not NaturalKey
            or type(self.token) is not CanonicalToken
            or type(self.receipt_id) is not InteractionId
            or type(self.recorded_at) is not CanonicalTimestamp
            or type(self.result) is not HashBinding
        ):
            raise IdempotencyDefinitionError("RECEIPT_SHAPE_INVALID")

    def __repr__(self) -> str:
        return "IdempotencyReceipt(<redacted>)"


@dataclass(frozen=True, slots=True)
class ReplayOutcome:
    receipt: IdempotencyReceipt = field(repr=False)
    replayed: bool

    def __post_init__(self) -> None:
        if type(self.receipt) is not IdempotencyReceipt or type(self.replayed) is not bool:
            raise IdempotencyDefinitionError("REPLAY_OUTCOME_INVALID")


DigestFunction = Callable[[bytes], str]
ReceiptAllocator = Callable[[], ReceiptAllocation]


def _validate_domain(domain: object) -> str:
    accepted: str | None = None
    try:
        accepted = validate_hash_domain(domain)
    except HashDomainViolation:
        pass
    if accepted is None:
        raise IdempotencyDefinitionError("IDEMPOTENCY_DOMAIN_INVALID")
    return accepted


def _validate_canonical_bytes(value: object, code: str) -> bytes:
    if type(value) is not bytes:
        raise IdempotencyDefinitionError(code)
    canonical_invalid = False
    try:
        parse_canonical_json_bytes(value)
    except (TypeError, ValueError):
        canonical_invalid = True
    if canonical_invalid:
        raise IdempotencyDefinitionError(code)
    return value


def _sha256(preimage: bytes) -> str:
    return hashlib.sha256(preimage).hexdigest()


class InMemoryIdempotencyStore:
    """Resolve exact replays before allocation under one process-local lock."""

    TOKEN_DOMAIN: ClassVar[str] = "shared-idempotency-command/v1"

    def __init__(
        self,
        *,
        token_domain: str = TOKEN_DOMAIN,
        _digest_function: DigestFunction = _sha256,
    ) -> None:
        self._token_domain = _validate_domain(token_domain)
        if not callable(_digest_function):
            raise IdempotencyDefinitionError("DIGEST_FUNCTION_INVALID")
        self._digest_function = _digest_function
        self._receipts: dict[NaturalKey, IdempotencyReceipt] = {}
        self._in_flight: set[NaturalKey] = set()
        self._lock = RLock()

    def _token(self, command_bytes: bytes) -> CanonicalToken:
        canonical = _validate_canonical_bytes(command_bytes, "COMMAND_BYTES_INVALID")
        preimage = self._token_domain.encode("ascii") + b"\n" + canonical
        digest_failed = False
        try:
            digest = self._digest_function(preimage)
        except Exception:
            digest_failed = True
            digest = None
        if digest_failed:
            raise IdempotencyDefinitionError("DIGEST_FUNCTION_FAILED")
        if type(digest) is not str or _SHA256.fullmatch(digest) is None:
            raise IdempotencyDefinitionError("COMMAND_DIGEST_INVALID")
        return CanonicalToken._from_validated(
            self._token_domain,
            canonical,
            digest,
            _token=_TOKEN_CONSTRUCTION_TOKEN,
        )

    def resolve_or_record(
        self,
        natural_key: NaturalKey,
        command_bytes: bytes,
        allocator: ReceiptAllocator,
    ) -> ReplayOutcome:
        """Return an exact replay or allocate and atomically retain one new receipt."""

        if type(natural_key) is not NaturalKey or not callable(allocator):
            raise IdempotencyDefinitionError("IDEMPOTENCY_REQUEST_INVALID")
        candidate = self._token(command_bytes)
        with self._lock:
            retained = self._receipts.get(natural_key)
            if retained is not None:
                if retained.token.sha256 != candidate.sha256:
                    raise IdempotencyConflictError("IDEMPOTENCY_KEY_MATERIAL_CONFLICT")
                if retained.token.canonical_bytes != candidate.canonical_bytes:
                    raise DigestCollisionError("IDEMPOTENCY_DIGEST_COLLISION")
                return ReplayOutcome(retained, True)
            if natural_key in self._in_flight:
                raise IdempotencyConflictError("IDEMPOTENCY_REENTRANT_REQUEST")

            self._in_flight.add(natural_key)
            try:
                allocation_failed = False
                try:
                    allocation = allocator()
                except Exception:
                    allocation_failed = True
                    allocation = None
                if allocation_failed:
                    raise IdempotencyDefinitionError("RECEIPT_ALLOCATION_FAILED")
                if type(allocation) is not ReceiptAllocation:
                    raise IdempotencyDefinitionError("RECEIPT_ALLOCATION_INVALID")
                result = domain_hash(allocation.result_domain, allocation.result_bytes)
                receipt = IdempotencyReceipt(
                    natural_key=natural_key,
                    token=candidate,
                    receipt_id=allocation.receipt_id,
                    recorded_at=allocation.recorded_at,
                    result=result,
                )
                self._receipts[natural_key] = receipt
                return ReplayOutcome(receipt, False)
            finally:
                self._in_flight.remove(natural_key)

    def get(self, natural_key: NaturalKey) -> IdempotencyReceipt | None:
        if type(natural_key) is not NaturalKey:
            raise IdempotencyDefinitionError("NATURAL_KEY_INVALID")
        with self._lock:
            return self._receipts.get(natural_key)

    def __len__(self) -> int:
        with self._lock:
            return len(self._receipts)


__all__ = [
    "CanonicalToken",
    "DigestCollisionError",
    "IdempotencyConflictError",
    "IdempotencyDefinitionError",
    "IdempotencyError",
    "IdempotencyReceipt",
    "InMemoryIdempotencyStore",
    "NaturalKey",
    "ReceiptAllocation",
    "ReplayOutcome",
]
