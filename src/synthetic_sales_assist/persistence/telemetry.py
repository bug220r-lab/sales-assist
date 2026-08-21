"""Persisted, identity-free processing telemetry and aggregate health metrics."""

from __future__ import annotations

import math
import re
import sqlite3
from dataclasses import dataclass
from typing import Final

from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.domain.tokens import ImmutableStrEnum


TELEMETRY_SCHEMA_VERSION: Final = "synthetic-sales-assist-telemetry/v1"
SAFETY_COUNTER_NAMES: Final = (
    "EXTERNAL_MUTATION_REQUEST_COUNT",
    "EXTERNAL_PRODUCTION_SYSTEM_ACCESS_COUNT",
    "NON_LOCALHOST_RUNTIME_REQUEST_COUNT",
    "NON_SYNTHETIC_FIXTURE_COUNT",
    "PRODUCTION_MUTATION_REQUEST_COUNT",
    "PRODUCTION_SYSTEM_ACCESS_COUNT",
    "REAL_CUSTOMER_DATA_COUNT",
    "REAL_CUSTOMER_IDENTITY_COUNT",
    "SECRET_MATERIAL_COUNT",
)
ZERO_SAFETY_COUNTERS: Final = tuple((name, 0) for name in SAFETY_COUNTER_NAMES)

_OPERATION_ID = re.compile(r"\ASYN-EVIDENCE-[A-Z0-9][A-Z0-9-]{0,126}\Z", re.ASCII)
_ALIAS = re.compile(r"\A[a-z][a-z0-9-]{0,62}[a-z0-9]\Z", re.ASCII)
_VERSION = re.compile(r"\A[a-z0-9][a-z0-9._/-]{0,127}\Z", re.ASCII)
_ERROR_CODE = re.compile(r"\A[A-Z][A-Z0-9_]{0,95}\Z", re.ASCII)


class TelemetryError(RuntimeError):
    """Reject malformed or conflicting telemetry without retaining payload material."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"telemetry rejected: {code}")


class RulePack(ImmutableStrEnum):
    SHARED = "SHARED"
    SALES_CREDIT = "SALES_CREDIT"
    DOI = "DOI"


class ProcessingResultClass(ImmutableStrEnum):
    SUCCESS = "SUCCESS"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    FAILED_CLOSED = "FAILED_CLOSED"
    CONFLICT = "CONFLICT"
    ERROR = "ERROR"


def _duration(value: object, code: str) -> int:
    if type(value) is not int or value < 0:
        raise TelemetryError(code)
    return value


def _version(value: object, code: str) -> str:
    if type(value) is not str or _VERSION.fullmatch(value) is None:
        raise TelemetryError(code)
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessingTelemetry:
    """One closed timing/result record with no business identity or unrestricted payload."""

    operation_id: str
    rule_pack: RulePack
    demo_alias: str | None
    started_at: CanonicalTimestamp
    ended_at: CanonicalTimestamp
    extraction_ns: int
    validation_ns: int
    normalization_ns: int
    rule_ns: int
    database_ns: int
    total_ns: int
    result_class: ProcessingResultClass
    human_review: bool
    fail_closed: bool
    replay: bool
    conflict: bool
    database_error: bool
    rule_version: str
    schema_version: str
    catalog_version: str | None
    error_code: str | None
    safety_counters: tuple[tuple[str, int], ...] = ZERO_SAFETY_COUNTERS

    def __post_init__(self) -> None:
        if type(self.operation_id) is not str or _OPERATION_ID.fullmatch(self.operation_id) is None:
            raise TelemetryError("OPERATION_ID_INVALID")
        if type(self.rule_pack) is not RulePack:
            raise TelemetryError("RULE_PACK_INVALID")
        if self.demo_alias is not None and (
            type(self.demo_alias) is not str or _ALIAS.fullmatch(self.demo_alias) is None
        ):
            raise TelemetryError("DEMO_ALIAS_INVALID")
        if type(self.started_at) is not CanonicalTimestamp or type(
            self.ended_at
        ) is not CanonicalTimestamp:
            raise TelemetryError("TELEMETRY_TIMESTAMP_INVALID")
        if (self.ended_at.epoch_seconds, self.ended_at.nanosecond) < (
            self.started_at.epoch_seconds,
            self.started_at.nanosecond,
        ):
            raise TelemetryError("TELEMETRY_TIME_ORDER_INVALID")
        durations = (
            _duration(self.extraction_ns, "EXTRACTION_DURATION_INVALID"),
            _duration(self.validation_ns, "VALIDATION_DURATION_INVALID"),
            _duration(self.normalization_ns, "NORMALIZATION_DURATION_INVALID"),
            _duration(self.rule_ns, "RULE_DURATION_INVALID"),
            _duration(self.database_ns, "DATABASE_DURATION_INVALID"),
        )
        total = _duration(self.total_ns, "TOTAL_DURATION_INVALID")
        if total < max(durations, default=0):
            raise TelemetryError("TOTAL_DURATION_INVALID")
        if type(self.result_class) is not ProcessingResultClass:
            raise TelemetryError("RESULT_CLASS_INVALID")
        for value in (
            self.human_review,
            self.fail_closed,
            self.replay,
            self.conflict,
            self.database_error,
        ):
            if type(value) is not bool:
                raise TelemetryError("TELEMETRY_FLAG_INVALID")
        if self.result_class is ProcessingResultClass.HUMAN_REVIEW and not self.human_review:
            raise TelemetryError("HUMAN_REVIEW_PARTITION_INVALID")
        if self.result_class is ProcessingResultClass.FAILED_CLOSED and not self.fail_closed:
            raise TelemetryError("FAIL_CLOSED_PARTITION_INVALID")
        if self.result_class is ProcessingResultClass.CONFLICT and not self.conflict:
            raise TelemetryError("CONFLICT_PARTITION_INVALID")
        if self.result_class is ProcessingResultClass.SUCCESS and any(
            (self.human_review, self.fail_closed, self.conflict, self.database_error)
        ):
            raise TelemetryError("SUCCESS_PARTITION_INVALID")
        if self.result_class is ProcessingResultClass.HUMAN_REVIEW and any(
            (self.fail_closed, self.conflict, self.database_error)
        ):
            raise TelemetryError("HUMAN_REVIEW_PARTITION_INVALID")
        if self.result_class is ProcessingResultClass.FAILED_CLOSED and any(
            (self.human_review, self.conflict, self.database_error)
        ):
            raise TelemetryError("FAIL_CLOSED_PARTITION_INVALID")
        if self.result_class is ProcessingResultClass.CONFLICT and any(
            (self.human_review, self.fail_closed, self.database_error)
        ):
            raise TelemetryError("CONFLICT_PARTITION_INVALID")
        if self.database_error and self.result_class is not ProcessingResultClass.ERROR:
            raise TelemetryError("DATABASE_ERROR_PARTITION_INVALID")
        _version(self.rule_version, "RULE_VERSION_INVALID")
        _version(self.schema_version, "SCHEMA_VERSION_INVALID")
        if self.catalog_version is not None:
            _version(self.catalog_version, "CATALOG_VERSION_INVALID")
        if self.error_code is not None and (
            type(self.error_code) is not str or _ERROR_CODE.fullmatch(self.error_code) is None
        ):
            raise TelemetryError("ERROR_CODE_INVALID")
        if self.result_class in {
            ProcessingResultClass.SUCCESS,
            ProcessingResultClass.HUMAN_REVIEW,
        } and self.error_code is not None:
            raise TelemetryError("ERROR_CODE_PARTITION_INVALID")
        if self.result_class in {
            ProcessingResultClass.FAILED_CLOSED,
            ProcessingResultClass.CONFLICT,
            ProcessingResultClass.ERROR,
        } and self.error_code is None:
            raise TelemetryError("ERROR_CODE_PARTITION_INVALID")
        if self.safety_counters != ZERO_SAFETY_COUNTERS:
            raise TelemetryError("SAFETY_COUNTER_SNAPSHOT_INVALID")


@dataclass(frozen=True, slots=True)
class ExactRate:
    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if (
            type(self.numerator) is not int
            or type(self.denominator) is not int
            or self.numerator < 0
            or self.denominator < 0
            or self.numerator > self.denominator
        ):
            raise TelemetryError("RATE_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "defined": self.denominator > 0,
            "denominator": self.denominator,
            "numerator": self.numerator,
        }


@dataclass(frozen=True, slots=True)
class TelemetrySummary:
    total_processed: int
    success_count: int
    success_rate: ExactRate
    failed_closed_count: int
    failed_closed_rate: ExactRate
    human_review_count: int
    human_review_rate: ExactRate
    exact_replay_count: int
    conflict_count: int
    database_error_count: int
    median_latency_ns: int | None
    p95_latency_ns: int | None
    throughput_per_second: str | None
    safety_counters: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "conflict_count": self.conflict_count,
            "database_error_count": self.database_error_count,
            "exact_replay_count": self.exact_replay_count,
            "failed_closed_count": self.failed_closed_count,
            "failed_closed_rate": self.failed_closed_rate.to_dict(),
            "human_review_count": self.human_review_count,
            "human_review_rate": self.human_review_rate.to_dict(),
            "median_latency_ns": self.median_latency_ns,
            "p95_latency_ns": self.p95_latency_ns,
            "safety_counters": dict(self.safety_counters),
            "success_rate": self.success_rate.to_dict(),
            "success_count": self.success_count,
            "throughput_per_second": self.throughput_per_second,
            "total_processed": self.total_processed,
        }


def record_processing_telemetry(
    connection: sqlite3.Connection,
    telemetry: ProcessingTelemetry,
) -> None:
    """Append one telemetry row and its exact nine-counter snapshot in the caller transaction."""

    if type(connection) is not sqlite3.Connection or type(telemetry) is not ProcessingTelemetry:
        raise TelemetryError("TELEMETRY_INPUT_INVALID")
    try:
        connection.execute(
            """
            INSERT INTO processing_telemetry (
                operation_id, rule_pack, demo_alias, started_at, ended_at,
                extraction_ns, validation_ns, normalization_ns, rule_ns,
                database_ns, total_ns, result_class, human_review, fail_closed,
                replay, conflict, database_error, rule_version, schema_version,
                catalog_version, error_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                telemetry.operation_id,
                telemetry.rule_pack.value,
                telemetry.demo_alias,
                telemetry.started_at.value,
                telemetry.ended_at.value,
                telemetry.extraction_ns,
                telemetry.validation_ns,
                telemetry.normalization_ns,
                telemetry.rule_ns,
                telemetry.database_ns,
                telemetry.total_ns,
                telemetry.result_class.value,
                int(telemetry.human_review),
                int(telemetry.fail_closed),
                int(telemetry.replay),
                int(telemetry.conflict),
                int(telemetry.database_error),
                telemetry.rule_version,
                telemetry.schema_version,
                telemetry.catalog_version,
                telemetry.error_code,
            ),
        )
        connection.executemany(
            """
            INSERT INTO telemetry_safety_counters
                (operation_id, counter_name, counter_value)
            VALUES (?, ?, ?)
            """,
            (
                (telemetry.operation_id, counter_name, counter_value)
                for counter_name, counter_value in telemetry.safety_counters
            ),
        )
    except sqlite3.IntegrityError as exc:
        raise TelemetryError("TELEMETRY_CONFLICT") from exc
    except sqlite3.DatabaseError as exc:
        raise TelemetryError("TELEMETRY_DATABASE_ERROR") from exc


def _median(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) // 2


def _nearest_rank_p95(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def aggregate_processing_telemetry(connection: sqlite3.Connection) -> TelemetrySummary:
    """Return a deterministic identity-free aggregate over persisted operation telemetry."""

    if type(connection) is not sqlite3.Connection:
        raise TelemetryError("TELEMETRY_CONNECTION_INVALID")
    try:
        rows = connection.execute(
            """
            SELECT started_at, ended_at, total_ns, result_class, human_review,
                   fail_closed, replay, conflict, database_error
            FROM processing_telemetry
            ORDER BY operation_id
            """
        ).fetchall()
        counter_rows = connection.execute(
            """
            SELECT counter_name, MAX(counter_value)
            FROM telemetry_safety_counters
            GROUP BY counter_name
            ORDER BY counter_name
            """
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        raise TelemetryError("TELEMETRY_DATABASE_ERROR") from exc

    total = len(rows)
    success = sum(row[3] in {"SUCCESS", "HUMAN_REVIEW"} for row in rows)
    failed_closed = sum(int(row[5]) for row in rows)
    human_review = sum(int(row[4]) for row in rows)
    replay = sum(int(row[6]) for row in rows)
    conflict = sum(int(row[7]) for row in rows)
    database_error = sum(int(row[8]) for row in rows)
    latencies = [int(row[2]) for row in rows]

    throughput: str | None = None
    if rows:
        starts = [CanonicalTimestamp(str(row[0])) for row in rows]
        ends = [CanonicalTimestamp(str(row[1])) for row in rows]
        start_ns = min(item.epoch_seconds * 1_000_000_000 + item.nanosecond for item in starts)
        end_ns = max(item.epoch_seconds * 1_000_000_000 + item.nanosecond for item in ends)
        span = end_ns - start_ns
        if span > 0:
            throughput = f"{total * 1_000_000_000 / span:.6f}"

    counters = tuple((str(name), int(value)) for name, value in counter_rows)
    if total == 0:
        counters = ZERO_SAFETY_COUNTERS
    if tuple(name for name, _ in counters) != SAFETY_COUNTER_NAMES or any(
        value != 0 for _, value in counters
    ):
        raise TelemetryError("SAFETY_COUNTER_AGGREGATE_INVALID")
    return TelemetrySummary(
        total_processed=total,
        success_count=success,
        success_rate=ExactRate(success, total),
        failed_closed_count=failed_closed,
        failed_closed_rate=ExactRate(failed_closed, total),
        human_review_count=human_review,
        human_review_rate=ExactRate(human_review, total),
        exact_replay_count=replay,
        conflict_count=conflict,
        database_error_count=database_error,
        median_latency_ns=_median(latencies),
        p95_latency_ns=_nearest_rank_p95(latencies),
        throughput_per_second=throughput,
        safety_counters=counters,
    )


__all__ = [
    "SAFETY_COUNTER_NAMES",
    "TELEMETRY_SCHEMA_VERSION",
    "ZERO_SAFETY_COUNTERS",
    "ExactRate",
    "ProcessingResultClass",
    "ProcessingTelemetry",
    "RulePack",
    "TelemetryError",
    "TelemetrySummary",
    "aggregate_processing_telemetry",
    "record_processing_telemetry",
]
