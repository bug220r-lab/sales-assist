"""Closed immutable representations for observed source facts.

Observation wrappers carry facts only.  They cannot carry business conclusions,
free-form source text, or guessed values.  Each serialized wrapper has the same
four closed members; the selected tag determines the required null partition.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Set
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Generic, TypeVar, cast

from synthetic_sales_assist.domain.canonical import HashBinding
from synthetic_sales_assist.domain.identities import TYPED_ID_CLASSES
from synthetic_sales_assist.domain.numeric import Money, PositiveQuantity, Quantity
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.domain.tokens import ImmutableStrEnum


OBSERVED_TAGGED_VALUE_VERSION = "doi-observed-tagged-value/r01-v2"
FINDING_PRESENCE_VERSION = "doi-finding-presence/r01-v2"
RAW_HINT_MAX_UTF8_BYTES = 48

# These symbolic, nonidentifying codes are the complete supported raw-hint
# vocabulary.  A field specialization must pass a subset of this vocabulary.
RAW_HINT_CODES = frozenset(
    {
        "CONTRADICTORY_AVAILABILITY_TOKENS",
        "CONTRADICTORY_DS_TOKENS",
        "CONTRADICTORY_ETA_TOKENS",
        "ETA_OUT_OF_RANGE",
        "UNRECOGNIZED_AVAILABILITY_TOKEN",
        "UNRECOGNIZED_DS_TOKEN",
        "UNRECOGNIZED_ETA_TOKEN",
        "UNSUPPORTED_ETA_FORMAT",
    }
)

_SERIALIZED_MEMBERS = frozenset({"raw_hint", "reason_code", "tag", "value"})
_REASON_CODE = re.compile(r"\ARC-(?P<number>[0-9]{3})\Z", re.ASCII)
_RAW_HINT = re.compile(r"\A[A-Z][A-Z0-9_]{0,47}\Z", re.ASCII)
_KNOWN_CONSTRUCTION_TOKEN = object()

KnownValue = TypeVar("KnownValue")


class ObservedValueError(ValueError):
    """A non-reflecting closed-shape or branch validation failure."""

    def __init__(self) -> None:
        super().__init__("observed tagged value rejected")


class ObservedTag(ImmutableStrEnum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FindingPresenceV2(ImmutableStrEnum):
    """Direct four-member finding presence; no outer wrapper is permitted."""

    PRESENT = "PRESENT"
    NOT_PRESENT = "NOT_PRESENT"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ObservedTaggedValue(ABC, Generic[KnownValue]):
    """Base type for the three and only three observation branches."""

    __slots__ = ()

    @property
    @abstractmethod
    def tag(self) -> ObservedTag:
        raise NotImplementedError

    @abstractmethod
    def to_mapping(self) -> dict[str, object]:
        raise NotImplementedError


def _reject_unsafe_known_value(value: object) -> None:
    if value is None:
        raise ObservedValueError
    if isinstance(value, ObservedTaggedValue):
        raise ObservedValueError
    if type(value) is str:
        if value == ObservedTag.UNKNOWN.value:
            raise ObservedValueError
        invalid_unicode = False
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            invalid_unicode = True
        if invalid_unicode:
            raise ObservedValueError
        return
    if type(value) in (bool, int):
        return
    if type(value) is float:
        raise ObservedValueError
    if type(value) is Decimal:
        if not value.is_finite():
            raise ObservedValueError
        return
    if type(value) in {
        HashBinding,
        Money,
        PositiveQuantity,
        Quantity,
        CanonicalTimestamp,
        *TYPED_ID_CLASSES,
    }:
        return
    if isinstance(value, StrEnum):
        raise ObservedValueError
    if type(value) is tuple:
        for item in value:
            _reject_unsafe_known_value(item)
        return
    if isinstance(value, (bytes, bytearray, memoryview, Mapping, Set)):
        raise ObservedValueError
    # Generic user objects and unregistered data classes have no closed,
    # inspectable immutability contract.
    raise ObservedValueError


@dataclass(frozen=True, slots=True, init=False, repr=False)
class KnownObservedValue(ObservedTaggedValue[KnownValue]):
    value: KnownValue

    def __init__(self, value: KnownValue, *, _token: object | None = None) -> None:
        if _token is not _KNOWN_CONSTRUCTION_TOKEN:
            raise ObservedValueError
        _reject_unsafe_known_value(value)
        object.__setattr__(self, "value", value)

    def __repr__(self) -> str:
        return "KnownObservedValue(<redacted>)"

    @property
    def tag(self) -> ObservedTag:
        return ObservedTag.KNOWN

    @property
    def reason_code(self) -> None:
        return None

    @property
    def raw_hint(self) -> None:
        return None

    def to_mapping(self) -> dict[str, object]:
        return {
            "raw_hint": None,
            "reason_code": None,
            "tag": self.tag.value,
            "value": self.value,
        }


def _closed_reason_allowlist(values: Set[str]) -> frozenset[str]:
    if isinstance(values, (str, bytes)):
        raise ObservedValueError
    conversion_failed = False
    try:
        result = frozenset(values)
    except Exception:
        conversion_failed = True
        result = frozenset()
    if conversion_failed:
        raise ObservedValueError
    if not result:
        raise ObservedValueError
    for value in result:
        if type(value) is not str:
            raise ObservedValueError
        match = _REASON_CODE.fullmatch(value)
        if match is None or not 1 <= int(match.group("number")) <= 138:
            raise ObservedValueError
    return result


def _closed_raw_hint_allowlist(values: Set[str]) -> frozenset[str]:
    if isinstance(values, (str, bytes)):
        raise ObservedValueError
    conversion_failed = False
    try:
        result = frozenset(values)
    except Exception:
        conversion_failed = True
        result = frozenset()
    if conversion_failed:
        raise ObservedValueError
    if not result.issubset(RAW_HINT_CODES):
        raise ObservedValueError
    for value in result:
        if (
            type(value) is not str
            or _RAW_HINT.fullmatch(value) is None
            or len(value.encode("utf-8")) > RAW_HINT_MAX_UTF8_BYTES
        ):
            raise ObservedValueError
    return result


@dataclass(frozen=True, slots=True, init=False)
class UnknownObservedValue(ObservedTaggedValue[None]):
    reason_code: str
    raw_hint: str | None

    def __init__(
        self,
        reason_code: str,
        *,
        allowed_reason_codes: Set[str],
        raw_hint: str | None = None,
        allowed_raw_hints: Set[str] = frozenset(),
    ) -> None:
        reasons = _closed_reason_allowlist(allowed_reason_codes)
        hints = _closed_raw_hint_allowlist(allowed_raw_hints)
        if reason_code not in reasons:
            raise ObservedValueError
        if raw_hint is not None and raw_hint not in hints:
            raise ObservedValueError
        object.__setattr__(self, "reason_code", reason_code)
        object.__setattr__(self, "raw_hint", raw_hint)

    @property
    def tag(self) -> ObservedTag:
        return ObservedTag.UNKNOWN

    @property
    def value(self) -> None:
        return None

    def to_mapping(self) -> dict[str, object]:
        return {
            "raw_hint": self.raw_hint,
            "reason_code": self.reason_code,
            "tag": self.tag.value,
            "value": None,
        }


@dataclass(frozen=True, slots=True)
class NotApplicableObservedValue(ObservedTaggedValue[None]):
    @property
    def tag(self) -> ObservedTag:
        return ObservedTag.NOT_APPLICABLE

    @property
    def value(self) -> None:
        return None

    @property
    def reason_code(self) -> None:
        return None

    @property
    def raw_hint(self) -> None:
        return None

    def to_mapping(self) -> dict[str, object]:
        return {
            "raw_hint": None,
            "reason_code": None,
            "tag": self.tag.value,
            "value": None,
        }


def parse_observed_tagged_value(
    payload: Mapping[str, object],
    *,
    version: str,
    known_value_parser: Callable[[object], KnownValue],
    allowed_unknown_reasons: Set[str],
    allowed_raw_hints: Set[str] = frozenset(),
    allow_not_applicable: bool = True,
) -> ObservedTaggedValue[KnownValue]:
    """Strictly deserialize one wrapper under a field-specific policy."""

    if type(version) is not str or version != OBSERVED_TAGGED_VALUE_VERSION:
        raise ObservedValueError
    if type(payload) is not dict:
        raise ObservedValueError
    if set(payload) != _SERIALIZED_MEMBERS:
        raise ObservedValueError
    if type(allow_not_applicable) is not bool:
        raise ObservedValueError

    raw_tag = payload["tag"]
    if type(raw_tag) is not str:
        raise ObservedValueError
    tag: ObservedTag | None = None
    try:
        tag = ObservedTag(raw_tag)
    except ValueError:
        pass
    if tag is None:
        raise ObservedValueError

    value = payload["value"]
    reason_code = payload["reason_code"]
    raw_hint = payload["raw_hint"]

    if tag is ObservedTag.KNOWN:
        if reason_code is not None or raw_hint is not None or value is None:
            raise ObservedValueError
        parser_failed = False
        parsed: KnownValue | None = None
        try:
            parsed = known_value_parser(value)
            _reject_unsafe_known_value(parsed)
        except Exception:
            parser_failed = True
        if parser_failed:
            raise ObservedValueError
        return KnownObservedValue(parsed, _token=_KNOWN_CONSTRUCTION_TOKEN)

    if tag is ObservedTag.UNKNOWN:
        if value is not None or type(reason_code) is not str:
            raise ObservedValueError
        if raw_hint is not None and type(raw_hint) is not str:
            raise ObservedValueError
        unknown = UnknownObservedValue(
            reason_code,
            allowed_reason_codes=allowed_unknown_reasons,
            raw_hint=raw_hint,
            allowed_raw_hints=allowed_raw_hints,
        )
        return cast(ObservedTaggedValue[KnownValue], unknown)

    if (
        not allow_not_applicable
        or value is not None
        or reason_code is not None
        or raw_hint is not None
    ):
        raise ObservedValueError
    return cast(ObservedTaggedValue[KnownValue], NotApplicableObservedValue())


def _reject_json_constant(_: str) -> None:
    raise ObservedValueError


def _closed_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ObservedValueError
        result[key] = value
    return result


def parse_observed_tagged_value_json(
    document: str | bytes,
    *,
    version: str,
    known_value_parser: Callable[[object], KnownValue],
    allowed_unknown_reasons: Set[str],
    allowed_raw_hints: Set[str] = frozenset(),
    allow_not_applicable: bool = True,
) -> ObservedTaggedValue[KnownValue]:
    """Strict JSON entry point that also rejects duplicates and non-finite numbers."""

    if type(document) not in (str, bytes):
        raise ObservedValueError
    decoded: object = None
    decode_failed = False
    try:
        if type(document) is bytes:
            if document.startswith(b"\xef\xbb\xbf"):
                raise ObservedValueError
            text = document.decode("utf-8", errors="strict")
        else:
            text = document
        decoded = json.loads(
            text,
            object_pairs_hook=_closed_json_object,
            parse_constant=_reject_json_constant,
        )
    except (
        ObservedValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        TypeError,
        ValueError,
    ):
        decode_failed = True
    if decode_failed:
        raise ObservedValueError
    if type(decoded) is not dict:
        raise ObservedValueError
    return parse_observed_tagged_value(
        decoded,
        version=version,
        known_value_parser=known_value_parser,
        allowed_unknown_reasons=allowed_unknown_reasons,
        allowed_raw_hints=allowed_raw_hints,
        allow_not_applicable=allow_not_applicable,
    )


def parse_finding_presence(
    value: object,
    *,
    version: str,
) -> FindingPresenceV2:
    """Parse the direct scalar representation and reject wrappers or aliases."""

    if (
        type(version) is not str
        or version != FINDING_PRESENCE_VERSION
        or type(value) is not str
    ):
        raise ObservedValueError
    result: FindingPresenceV2 | None = None
    try:
        result = FindingPresenceV2(value)
    except ValueError:
        pass
    if result is None:
        raise ObservedValueError
    return result


__all__ = [
    "FINDING_PRESENCE_VERSION",
    "OBSERVED_TAGGED_VALUE_VERSION",
    "RAW_HINT_CODES",
    "RAW_HINT_MAX_UTF8_BYTES",
    "FindingPresenceV2",
    "KnownObservedValue",
    "NotApplicableObservedValue",
    "ObservedTag",
    "ObservedTaggedValue",
    "ObservedValueError",
    "UnknownObservedValue",
    "parse_finding_presence",
    "parse_observed_tagged_value",
    "parse_observed_tagged_value_json",
]
