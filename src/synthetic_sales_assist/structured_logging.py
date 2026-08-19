"""Privacy-safe structured logging for the Milestone 0 foundation.

The public logger deliberately has no free-form message or exception API.  Callers
may emit only closed, machine-readable fields whose values are validated before a
``LogRecord`` is created.  This keeps contact values, notes, credentials, sessions,
and unrestricted source text out of logs by construction.
"""

from __future__ import annotations

import json
import logging
import math
import re
import sys
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Final, TextIO


LOG_SCHEMA_VERSION: Final = "synthetic-sales-assist-log/v1"
JSON_SAFE_INTEGER_MAX: Final = 9_007_199_254_740_991

# Preserve both binding counter vocabularies.  The similarly named counters are
# intentionally not aliases; only SECRET_MATERIAL_COUNT is shared by both specs.
SAFETY_COUNTER_NAMES: Final[tuple[str, ...]] = (
    "PRODUCTION_SYSTEM_ACCESS_COUNT",
    "PRODUCTION_MUTATION_REQUEST_COUNT",
    "REAL_CUSTOMER_IDENTITY_COUNT",
    "NON_SYNTHETIC_FIXTURE_COUNT",
    "SECRET_MATERIAL_COUNT",
    "EXTERNAL_PRODUCTION_SYSTEM_ACCESS_COUNT",
    "EXTERNAL_MUTATION_REQUEST_COUNT",
    "NON_LOCALHOST_RUNTIME_REQUEST_COUNT",
    "REAL_CUSTOMER_DATA_COUNT",
)

ZERO_SAFETY_COUNTERS: Final[Mapping[str, int]] = MappingProxyType(
    {name: 0 for name in SAFETY_COUNTER_NAMES}
)

_ALLOWED_FIELDS: Final = frozenset(
    {
        "artifact_schema_version",
        "code",
        "component",
        "count",
        "duration_ms",
        "migration_version",
        "operation",
        "rule_pack_version",
        "safety_counters",
        "status",
    }
)
_TOKEN_FIELDS: Final = frozenset(
    {
        "artifact_schema_version",
        "code",
        "component",
        "operation",
        "rule_pack_version",
    }
)
_ALLOWED_STATUSES: Final = frozenset(
    {
        "APPLIED",
        "BLOCKED",
        "CRITICAL",
        "FAILED",
        "HEALTHY",
        "NOOP",
        "REJECTED",
        "ROLLED_BACK",
        "STARTED",
        "SUCCEEDED",
    }
)
_LEVELS: Final[Mapping[str, int]] = MappingProxyType(
    {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
)
_SAFE_TOKEN = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}\Z", re.ASCII)
_SECRET_SHAPE = re.compile(
    r"\A(?:gh[pousr]_|github_pat_|xox[baprs]-|AKIA[A-Z0-9]{16}|ASIA[A-Z0-9]{16})",
    re.ASCII,
)
_JWT_SHAPE = re.compile(
    r"\A[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\Z",
    re.ASCII,
)
_PHONE_TOKEN_SHAPE = re.compile(r"\A[0-9][0-9.:-]*\Z", re.ASCII)


class UnsafeLogDataError(ValueError):
    """Raised without reflecting the rejected field name or value."""

    def __init__(self) -> None:
        super().__init__("unsafe structured log data rejected")


class SafetyCounterInvariantError(ValueError):
    """Raised when the closed safety-counter shape or zero invariant is broken."""

    def __init__(self) -> None:
        super().__init__("safety counter invariant violated")


def zero_safety_counters() -> dict[str, int]:
    """Return a mutable, fresh snapshot containing all nine counters at zero."""

    return dict(ZERO_SAFETY_COUNTERS)


def assert_safety_counters_zero(counters: Mapping[str, object]) -> None:
    """Validate the exact closed counter set and its commit-gating zero value."""

    if not isinstance(counters, Mapping):
        raise SafetyCounterInvariantError
    if set(counters) != set(SAFETY_COUNTER_NAMES):
        raise SafetyCounterInvariantError
    for value in counters.values():
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            or value > JSON_SAFE_INTEGER_MAX
            or value != 0
        ):
            raise SafetyCounterInvariantError


def _safe_token(value: object) -> str:
    if not isinstance(value, str) or not _SAFE_TOKEN.fullmatch(value):
        raise UnsafeLogDataError
    if (
        "://" in value
        or value.upper().startswith("SYN-")
        or _SECRET_SHAPE.match(value)
        or _JWT_SHAPE.fullmatch(value)
    ):
        raise UnsafeLogDataError
    # Seven or more digits in a digits-and-separators token is contact- or
    # identity-shaped.  Versions that need that shape belong in typed fields.
    if _PHONE_TOKEN_SHAPE.fullmatch(value) and sum(character.isdigit() for character in value) >= 7:
        raise UnsafeLogDataError
    return value


def _safe_nonnegative_integer(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > JSON_SAFE_INTEGER_MAX
    ):
        raise UnsafeLogDataError
    return value


def _safe_duration(value: object) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UnsafeLogDataError
    if value < 0 or not math.isfinite(value):
        raise UnsafeLogDataError
    return value


def _format_timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise UnsafeLogDataError
    utc_value = value.astimezone(timezone.utc)
    return utc_value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_log_record(
    event: object,
    *,
    level: object = "INFO",
    fields: Mapping[str, object] | None = None,
    timestamp: datetime | None = None,
) -> dict[str, object]:
    """Build one closed JSON-safe record without retaining rejected material."""

    safe_event = _safe_token(event)
    if not isinstance(level, str) or level not in _LEVELS:
        raise UnsafeLogDataError
    if fields is None:
        fields = {}
    if not isinstance(fields, Mapping) or any(
        not isinstance(key, str) or key not in _ALLOWED_FIELDS for key in fields
    ):
        raise UnsafeLogDataError

    record: dict[str, object] = {
        "event": safe_event,
        "level": level,
        "log_schema_version": LOG_SCHEMA_VERSION,
        "timestamp": _format_timestamp(timestamp or datetime.now(timezone.utc)),
    }

    for key in sorted(fields):
        value = fields[key]
        if key in _TOKEN_FIELDS:
            record[key] = _safe_token(value)
        elif key == "status":
            if not isinstance(value, str) or value not in _ALLOWED_STATUSES:
                raise UnsafeLogDataError
            record[key] = value
        elif key in {"count", "migration_version"}:
            record[key] = _safe_nonnegative_integer(value)
        elif key == "duration_ms":
            record[key] = _safe_duration(value)
        elif key == "safety_counters":
            if not isinstance(value, Mapping):
                raise UnsafeLogDataError
            try:
                assert_safety_counters_zero(value)
            except SafetyCounterInvariantError:
                raise UnsafeLogDataError from None
            record[key] = {name: value[name] for name in SAFETY_COUNTER_NAMES}
        else:  # Defensive closure if _ALLOWED_FIELDS and validation diverge.
            raise UnsafeLogDataError

    # ``allow_nan=False`` is a second line of defense for future numeric fields.
    json.dumps(record, allow_nan=False, ensure_ascii=True)
    return record


class _PrevalidatedJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = getattr(record, "structured_payload", None)
        if not isinstance(payload, dict):
            raise UnsafeLogDataError
        return json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )


class StructuredLogger:
    """A stream-only logger facade with no free-text or raw-exception surface."""

    def __init__(
        self,
        name: str,
        *,
        stream: TextIO | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        # Logger names are configuration, but validate them like every other token so
        # they cannot become a covert free-text field.
        _safe_token(name)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._logger = logging.Logger(name=name, level=logging.DEBUG)
        self._logger.propagate = False
        handler = logging.StreamHandler(stream if stream is not None else sys.stdout)
        handler.setFormatter(_PrevalidatedJsonFormatter())
        self._logger.addHandler(handler)

    @property
    def handlers(self) -> tuple[logging.Handler, ...]:
        """Expose an immutable inventory for safety checks."""

        return tuple(self._logger.handlers)

    @property
    def propagates(self) -> bool:
        return self._logger.propagate

    def emit(self, event: object, *, level: object = "INFO", **fields: object) -> None:
        payload = build_log_record(
            event,
            level=level,
            fields=fields,
            timestamp=self._clock(),
        )
        assert isinstance(level, str)  # Narrowed by build_log_record.
        self._logger.log(
            _LEVELS[level],
            "",
            extra={"structured_payload": payload},
        )

    def close(self) -> None:
        """Flush and detach the sole stream handler without closing its stream."""

        for handler in tuple(self._logger.handlers):
            handler.flush()
            self._logger.removeHandler(handler)
            handler.close()


__all__ = [
    "JSON_SAFE_INTEGER_MAX",
    "LOG_SCHEMA_VERSION",
    "SAFETY_COUNTER_NAMES",
    "ZERO_SAFETY_COUNTERS",
    "SafetyCounterInvariantError",
    "StructuredLogger",
    "UnsafeLogDataError",
    "assert_safety_counters_zero",
    "build_log_record",
    "zero_safety_counters",
]
