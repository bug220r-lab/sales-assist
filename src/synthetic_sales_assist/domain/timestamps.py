"""Nanosecond-exact RFC-3339 timestamp canonicalization and hashing."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


TIMESTAMP_HASH_DOMAIN = "doi-timestamp/r01-v1"
TIMESTAMP_JSON_REPRESENTATION = "string"
TIMESTAMP_SQLITE_TYPE = "TEXT"
TIMESTAMP_SQLITE_COLLATION = "BINARY"
TIMESTAMP_SQLITE_DECLARATION = "TEXT COLLATE BINARY"
TIMESTAMP_KNOWN_ANSWER_CANONICAL = "2026-08-10T12:34:56.12Z"
TIMESTAMP_KNOWN_ANSWER_SHA256 = (
    "ba8fc05dbdbba6fec52a3ed7b0a93a0d8dbb8512e9fe95c56d6d4bd4708d2112"
)

_RFC3339_PATTERN = re.compile(
    r"\A"
    r"(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})"
    r"T(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})"
    r"(?:\.(?P<fraction>[0-9]{1,9}))?"
    r"(?P<offset>Z|[+-][0-9]{2}:[0-9]{2})"
    r"\Z",
    re.ASCII,
)
_EPOCH_NAIVE = datetime(1970, 1, 1)


class TimestampValidationError(ValueError):
    """Reject a timestamp without retaining or echoing the source value."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"timestamp rejected: {code}")


def _parse_components(value: object) -> tuple[str, int, int]:
    if type(value) is not str:
        raise TimestampValidationError("timestamp_type")
    match = _RFC3339_PATTERN.fullmatch(value)
    if match is None:
        raise TimestampValidationError("timestamp_grammar")

    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    second = int(match.group("second"))

    fraction = match.group("fraction") or ""
    nanosecond = int(fraction.ljust(9, "0")) if fraction else 0

    offset_text = match.group("offset")
    if offset_text == "Z":
        offset_minutes = 0
    else:
        offset_hour = int(offset_text[1:3])
        offset_minute = int(offset_text[4:6])
        if offset_hour > 23 or offset_minute > 59:
            raise TimestampValidationError("timestamp_offset")
        if offset_text == "-00:00":
            raise TimestampValidationError("timestamp_unknown_local_offset")
        magnitude = offset_hour * 60 + offset_minute
        offset_minutes = magnitude if offset_text[0] == "+" else -magnitude

    calendar_invalid = False
    try:
        local_zone = timezone(timedelta(minutes=offset_minutes))
        local = datetime(year, month, day, hour, minute, second, tzinfo=local_zone)
        utc = local.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        calendar_invalid = True
        utc = None
    if calendar_invalid or utc is None:
        raise TimestampValidationError("timestamp_calendar_or_offset")

    utc_naive = utc.replace(tzinfo=None)
    epoch_delta = utc_naive - _EPOCH_NAIVE
    epoch_seconds = epoch_delta.days * 86_400 + epoch_delta.seconds
    canonical = (
        f"{utc.year:04d}-{utc.month:02d}-{utc.day:02d}"
        f"T{utc.hour:02d}:{utc.minute:02d}:{utc.second:02d}"
    )
    if nanosecond:
        canonical += f".{nanosecond:09d}".rstrip("0")
    canonical += "Z"
    return canonical, epoch_seconds, nanosecond


@dataclass(frozen=True, slots=True, init=False, repr=False)
class CanonicalTimestamp:
    """One immutable instant with a nanosecond-exact canonical UTC representation."""

    value: str = field(repr=False)
    epoch_seconds: int = field(repr=False)
    nanosecond: int = field(repr=False)

    def __init__(self, source: object) -> None:
        canonical, epoch_seconds, nanosecond = _parse_components(source)
        object.__setattr__(self, "value", canonical)
        object.__setattr__(self, "epoch_seconds", epoch_seconds)
        object.__setattr__(self, "nanosecond", nanosecond)

    @classmethod
    def parse(cls, source: object) -> CanonicalTimestamp:
        return cls(source)

    @classmethod
    def from_sqlite_text(cls, value: object) -> CanonicalTimestamp:
        """Load only the canonical form required for SQLite logical storage."""

        timestamp = cls(value)
        if timestamp.value != value:
            raise TimestampValidationError("sqlite_timestamp_not_canonical")
        return timestamp

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return "CanonicalTimestamp(<redacted>)"

    def canonical_bytes(self) -> bytes:
        return self.value.encode("ascii")

    def to_json_value(self) -> str:
        return self.value

    def to_sqlite_value(self) -> str:
        return self.value


def parse_timestamp(value: object) -> CanonicalTimestamp:
    """Parse the closed RFC-3339 subset into an immutable canonical instant."""

    return CanonicalTimestamp(value)


def canonicalize_timestamp(value: object) -> str:
    """Return the canonical UTC ``Z`` representation of one accepted timestamp."""

    return CanonicalTimestamp(value).value


def _as_timestamp(value: object) -> CanonicalTimestamp:
    if type(value) is CanonicalTimestamp:
        return value
    return CanonicalTimestamp(value)


def timestamp_hash_preimage(value: object) -> bytes:
    """Return the exact versioned timestamp primitive hash preimage."""

    timestamp = _as_timestamp(value)
    return TIMESTAMP_HASH_DOMAIN.encode("ascii") + b"\n" + timestamp.canonical_bytes()


def timestamp_sha256(value: object) -> str:
    """Hash one canonical instant under the required timestamp domain."""

    return hashlib.sha256(timestamp_hash_preimage(value)).hexdigest()


def timestamps_same_instant(left: object, right: object) -> bool:
    """Compare accepted inputs by their canonical instant and nanosecond."""

    first = _as_timestamp(left)
    second = _as_timestamp(right)
    return (first.epoch_seconds, first.nanosecond) == (
        second.epoch_seconds,
        second.nanosecond,
    )


def assert_same_canonical_instant(left: object, right: object) -> CanonicalTimestamp:
    """Require source-time coherence and return the first canonical instant."""

    first = _as_timestamp(left)
    second = _as_timestamp(right)
    if (first.epoch_seconds, first.nanosecond) != (
        second.epoch_seconds,
        second.nanosecond,
    ):
        raise TimestampValidationError("timestamp_instant_mismatch")
    return first


def verify_timestamp_known_answer() -> bool:
    """Execute the fixed published primitive known-answer oracle."""

    return timestamp_sha256(TIMESTAMP_KNOWN_ANSWER_CANONICAL) == TIMESTAMP_KNOWN_ANSWER_SHA256


__all__ = [
    "CanonicalTimestamp",
    "TIMESTAMP_HASH_DOMAIN",
    "TIMESTAMP_JSON_REPRESENTATION",
    "TIMESTAMP_KNOWN_ANSWER_CANONICAL",
    "TIMESTAMP_KNOWN_ANSWER_SHA256",
    "TIMESTAMP_SQLITE_COLLATION",
    "TIMESTAMP_SQLITE_DECLARATION",
    "TIMESTAMP_SQLITE_TYPE",
    "TimestampValidationError",
    "assert_same_canonical_instant",
    "canonicalize_timestamp",
    "parse_timestamp",
    "timestamp_hash_preimage",
    "timestamp_sha256",
    "timestamps_same_instant",
    "verify_timestamp_known_answer",
]
