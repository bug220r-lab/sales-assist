"""Closed, deterministic canonical JSON and domain-separated SHA-256 bindings.

This module is intentionally independent of business records and persistence.  It accepts
only ordinary JSON data, emits one UTF-8 representation, and retains the canonical bytes
needed to distinguish an idempotent replay from a proven digest collision.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import NoReturn, cast


_DOMAIN_PATTERN = re.compile(
    r"^[a-z][a-z0-9]*(?:[._/-][a-z0-9]+)*/v[1-9][0-9]*$",
    re.ASCII,
)
_LOWER_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_MAX_SAFE_JSON_INTEGER = (1 << 53) - 1


class CanonicalJsonViolation(ValueError):
    """Raised when data cannot enter the canonical JSON domain."""


class HashDomainViolation(ValueError):
    """Raised when a hash domain or retained binding is not canonical."""


class CanonicalHashCollision(RuntimeError):
    """Raised when one digest is associated with different canonical bytes."""


@dataclass(frozen=True, slots=True)
class HashBinding:
    """Immutable SHA-256 binding that retains its collision-comparison bytes."""

    domain: str
    sha256: str
    canonical_bytes: bytes = field(repr=False)

    def __post_init__(self) -> None:
        domain_bytes = _domain_bytes(self.domain)
        canonical = _require_canonical_bytes(self.canonical_bytes)
        if type(self.sha256) is not str or not _LOWER_SHA256_PATTERN.fullmatch(
            self.sha256
        ):
            raise HashDomainViolation("SHA-256 must be lowercase hexadecimal")
        expected = hashlib.sha256(domain_bytes + b"\n" + canonical).hexdigest()
        if not hmac.compare_digest(expected, self.sha256):
            raise HashDomainViolation("SHA-256 does not match the retained canonical bytes")

    @property
    def preimage(self) -> bytes:
        """Return the exact versioned-domain, LF, canonical-JSON preimage."""

        return self.domain.encode("ascii") + b"\n" + self.canonical_bytes


def _member_set(expected_members: Collection[str] | None) -> frozenset[str] | None:
    if expected_members is None:
        return None
    if isinstance(expected_members, (str, bytes)):
        raise CanonicalJsonViolation("expected members must be a collection of names")
    members = tuple(expected_members)
    if any(type(member) is not str or not member for member in members):
        raise CanonicalJsonViolation("expected members must be non-empty strings")
    if len(members) != len(set(members)):
        raise CanonicalJsonViolation("expected members must not contain duplicates")
    return frozenset(members)


def _validate_json_value(value: object) -> None:
    value_type = type(value)
    if value is None or value_type is bool:
        return
    if value_type is int:
        number = cast(int, value)
        if not -_MAX_SAFE_JSON_INTEGER <= number <= _MAX_SAFE_JSON_INTEGER:
            raise CanonicalJsonViolation("JSON integer exceeds the exact safe range")
        return
    if value_type is float:
        raise CanonicalJsonViolation(
            "binary floating-point JSON numbers are prohibited; use an exact type"
        )
    if value_type is str:
        text = cast(str, value)
        try:
            text.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            pass
        else:
            return
        raise CanonicalJsonViolation("JSON text must contain valid Unicode scalars")
    if value_type is list:
        for item in cast(list[object], value):
            _validate_json_value(item)
        return
    if value_type is dict:
        for key, item in cast(dict[object, object], value).items():
            if type(key) is not str:
                raise CanonicalJsonViolation("JSON object member names must be strings")
            _validate_json_value(key)
            _validate_json_value(item)
        return
    raise CanonicalJsonViolation("value contains a non-JSON type")


def _validate_expected_members(
    value: object, expected_members: Collection[str] | None
) -> None:
    expected = _member_set(expected_members)
    if expected is None:
        return
    if type(value) is not dict:
        raise CanonicalJsonViolation("a closed JSON schema requires an object")
    actual = frozenset(cast(dict[object, object], value))
    if actual != expected:
        raise CanonicalJsonViolation("closed JSON object members do not match its schema")


def canonical_json_bytes(
    value: object, *, expected_members: Collection[str] | None = None
) -> bytes:
    """Return the one compact, member-sorted UTF-8 representation of ``value``.

    ``expected_members`` closes the top-level object and is exact: missing and unknown
    members both fail.  Nested closed objects are canonicalized separately by their owning
    contract before being embedded.
    """

    validation_failed = False
    try:
        _validate_json_value(value)
        _validate_expected_members(value, expected_members)
    except CanonicalJsonViolation:
        raise
    except RecursionError:
        validation_failed = True
    if validation_failed:
        raise CanonicalJsonViolation("value exceeds the canonical JSON depth boundary")
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        encoded = text.encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError):
        pass
    else:
        return encoded
    raise CanonicalJsonViolation("value cannot be encoded as canonical JSON")


def _reject_duplicate_members(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CanonicalJsonViolation("duplicate JSON object members are prohibited")
        result[key] = value
    return result


def _reject_nonfinite_constant(_: str) -> NoReturn:
    raise CanonicalJsonViolation("non-finite JSON numbers are prohibited")


def parse_canonical_json_bytes(
    raw: bytes, *, expected_members: Collection[str] | None = None
) -> object:
    """Decode canonical UTF-8 JSON, rejecting aliases before returning its value."""

    if type(raw) is not bytes:
        raise CanonicalJsonViolation("canonical JSON input must be immutable bytes")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        text = None
    if text is None:
        raise CanonicalJsonViolation("canonical JSON input must be valid UTF-8")
    parse_failed = False
    try:
        value: object = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_members,
            parse_constant=_reject_nonfinite_constant,
        )
    except CanonicalJsonViolation:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError):
        parse_failed = True
        value = None
    if parse_failed:
        raise CanonicalJsonViolation("canonical JSON input is malformed")

    canonical = canonical_json_bytes(value, expected_members=expected_members)
    if not hmac.compare_digest(raw, canonical):
        raise CanonicalJsonViolation("JSON input uses a noncanonical representation")
    return value


def _require_canonical_bytes(canonical_bytes: bytes) -> bytes:
    if type(canonical_bytes) is not bytes:
        raise HashDomainViolation("canonical JSON must be immutable bytes")
    valid = True
    try:
        parse_canonical_json_bytes(canonical_bytes)
    except CanonicalJsonViolation:
        valid = False
    if not valid:
        raise HashDomainViolation("hash input must be canonical JSON bytes")
    return canonical_bytes


def _domain_bytes(domain: str) -> bytes:
    if type(domain) is not str or not _DOMAIN_PATTERN.fullmatch(domain):
        raise HashDomainViolation("hash domain must be a lowercase versioned identifier")
    return domain.encode("ascii")


def validate_hash_domain(domain: object) -> str:
    """Return one accepted versioned domain without normalizing or echoing it."""

    if type(domain) is not str:
        raise HashDomainViolation("hash domain must be a lowercase versioned identifier")
    _domain_bytes(domain)
    return domain


def domain_hash(domain: str, canonical_bytes: bytes) -> HashBinding:
    """Bind canonical JSON to ``domain`` using exactly one LF and lowercase SHA-256."""

    domain_bytes = _domain_bytes(domain)
    canonical = _require_canonical_bytes(canonical_bytes)
    digest = hashlib.sha256(domain_bytes + b"\n" + canonical).hexdigest()
    return HashBinding(domain=domain, sha256=digest, canonical_bytes=canonical)


def _validated_digest(digest: str) -> str:
    if type(digest) is not str or not _LOWER_SHA256_PATTERN.fullmatch(digest):
        raise HashDomainViolation("retained SHA-256 must be lowercase hexadecimal")
    return digest


def compare_retained_canonical_bytes(
    retained_sha256: str,
    retained_bytes: bytes,
    candidate_sha256: str,
    candidate_bytes: bytes,
) -> bool:
    """Classify a retained digest comparison without trusting digest equality alone.

    ``False`` means distinct digests.  ``True`` means exact replay bytes.  Equal digests
    with different canonical bytes are a proven collision and raise before any caller can
    treat the candidate as an idempotent replay.
    """

    retained_digest = _validated_digest(retained_sha256)
    candidate_digest = _validated_digest(candidate_sha256)
    retained = _require_canonical_bytes(retained_bytes)
    candidate = _require_canonical_bytes(candidate_bytes)
    if not hmac.compare_digest(retained_digest, candidate_digest):
        return False
    if not hmac.compare_digest(retained, candidate):
        raise CanonicalHashCollision(
            "equal SHA-256 values have different retained canonical bytes"
        )
    return True


__all__ = [
    "CanonicalHashCollision",
    "CanonicalJsonViolation",
    "HashBinding",
    "HashDomainViolation",
    "canonical_json_bytes",
    "compare_retained_canonical_bytes",
    "domain_hash",
    "parse_canonical_json_bytes",
    "validate_hash_domain",
]
