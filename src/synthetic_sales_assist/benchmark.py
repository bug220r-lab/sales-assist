"""Deterministic Milestone 4 persistence benchmark orchestration."""

from __future__ import annotations

import math
import time
import tracemalloc
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from synthetic_sales_assist.demos import DemoAuditBackend, DemoRunView
from synthetic_sales_assist.persistence.backup import create_backup, verify_backup
from synthetic_sales_assist.persistence.database import SQLiteDatabase
from synthetic_sales_assist.persistence.telemetry import aggregate_processing_telemetry


BENCHMARK_VERSION: Final = "synthetic-sales-assist-milestone4-benchmark/v1"
_ALIASES: Final = (
    "sales-credit-target-rep",
    "sales-credit-human-review",
    "doi-fulfillment-split",
    "doi-full-ds",
    "doi-manual-review",
    "doi-overlap",
)


class BenchmarkError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"benchmark rejected: {code}")


def _median(values: list[int]) -> int:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) // 2


def _p95(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * 0.95) - 1]


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    unique_operation_count: int
    replay_operation_count: int
    total_duration_ns: int
    median_end_to_end_ns: int
    p95_end_to_end_ns: int
    median_database_ns: int
    p95_database_ns: int
    throughput_per_second: str
    database_size_bytes: int
    peak_python_bytes: int
    rule_pack_counts: tuple[tuple[str, int], ...]
    result_counts: tuple[tuple[str, int], ...]
    history_query_count: int
    backup_sha256: str
    safety_counters: tuple[tuple[str, int], ...]
    version: str = BENCHMARK_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "backup_sha256": self.backup_sha256,
            "database_size_bytes": self.database_size_bytes,
            "history_query_count": self.history_query_count,
            "median_database_ns": self.median_database_ns,
            "median_end_to_end_ns": self.median_end_to_end_ns,
            "p95_database_ns": self.p95_database_ns,
            "p95_end_to_end_ns": self.p95_end_to_end_ns,
            "peak_python_bytes": self.peak_python_bytes,
            "replay_operation_count": self.replay_operation_count,
            "result_counts": dict(self.result_counts),
            "rule_pack_counts": dict(self.rule_pack_counts),
            "safety_counters": dict(self.safety_counters),
            "throughput_per_second": self.throughput_per_second,
            "total_duration_ns": self.total_duration_ns,
            "unique_operation_count": self.unique_operation_count,
            "version": self.version,
        }


def run_persistence_benchmark(
    database: SQLiteDatabase,
    backend: DemoAuditBackend,
    backup_path: Path,
    *,
    operation_count: int = 1_000,
    replay_count: int = 100,
    history_sample_count: int = 25,
) -> BenchmarkReport:
    """Run mixed durable demos, exact replays, reads, metrics, backup, and verification."""

    if type(database) is not SQLiteDatabase or not isinstance(backup_path, Path):
        raise BenchmarkError("BENCHMARK_INPUT_INVALID")
    if (
        type(operation_count) is not int
        or type(replay_count) is not int
        or type(history_sample_count) is not int
        or not 1 <= operation_count <= 100_000
        or not 0 <= replay_count <= operation_count
        or not 0 <= history_sample_count <= operation_count
    ):
        raise BenchmarkError("BENCHMARK_COUNT_INVALID")

    database.initialize()
    durations: list[int] = []
    results: list[DemoRunView] = []
    request_rows: list[tuple[str, str]] = []
    rule_packs: Counter[str] = Counter()
    result_classes: Counter[str] = Counter()
    tracemalloc.start()
    started = time.perf_counter_ns()
    try:
        for index in range(operation_count):
            alias = _ALIASES[index % len(_ALIASES)]
            request_key = f"m4-benchmark-{index:06d}"
            operation_started = time.perf_counter_ns()
            view = backend.run_demo(alias, request_key)
            durations.append(time.perf_counter_ns() - operation_started)
            if type(view) is not DemoRunView or view.exact_replay or view.conflict:
                raise BenchmarkError("BENCHMARK_UNIQUE_RESULT_INVALID")
            results.append(view)
            request_rows.append((alias, request_key))
            rule_packs[view.rule_pack] += 1
            result_classes[view.top_level_result] += 1

        for alias, request_key in request_rows[:replay_count]:
            operation_started = time.perf_counter_ns()
            replay = backend.run_demo(alias, request_key)
            durations.append(time.perf_counter_ns() - operation_started)
            if type(replay) is not DemoRunView or not replay.exact_replay or replay.conflict:
                raise BenchmarkError("BENCHMARK_REPLAY_RESULT_INVALID")

        history_queries = 0
        for view in results[:history_sample_count]:
            order_id = next(
                (item for item in view.synthetic_ids if item.startswith("SYN-ORDER-")),
                None,
            )
            if order_id is not None:
                backend.order_show(order_id)
                backend.case_history(order_id)
                history_queries += 2
            if view.run_id is not None:
                backend.run_show(view.run_id)
                history_queries += 1

        with database.read() as connection:
            database_durations = [
                int(row[0])
                for row in connection.execute(
                    "SELECT database_ns FROM processing_telemetry ORDER BY rowid DESC LIMIT ?",
                    (operation_count + replay_count,),
                ).fetchall()
            ]
            metrics = aggregate_processing_telemetry(connection)
        if len(database_durations) < operation_count + replay_count:
            raise BenchmarkError("BENCHMARK_TELEMETRY_INCOMPLETE")
        receipt = create_backup(database, backup_path)
        verified = verify_backup(backup_path)
        if verified != receipt:
            raise BenchmarkError("BENCHMARK_BACKUP_VERIFICATION_INVALID")
    finally:
        total_duration = time.perf_counter_ns() - started
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

    total_calls = operation_count + replay_count
    throughput = f"{total_calls * 1_000_000_000 / max(total_duration, 1):.6f}"
    return BenchmarkReport(
        unique_operation_count=operation_count,
        replay_operation_count=replay_count,
        total_duration_ns=total_duration,
        median_end_to_end_ns=_median(durations),
        p95_end_to_end_ns=_p95(durations),
        median_database_ns=_median(database_durations),
        p95_database_ns=_p95(database_durations),
        throughput_per_second=throughput,
        database_size_bytes=database.path.stat().st_size,
        peak_python_bytes=peak_bytes,
        rule_pack_counts=tuple(sorted(rule_packs.items())),
        result_counts=tuple(sorted(result_classes.items())),
        history_query_count=history_queries,
        backup_sha256=receipt.backup_sha256,
        safety_counters=metrics.safety_counters,
    )


__all__ = [
    "BENCHMARK_VERSION",
    "BenchmarkError",
    "BenchmarkReport",
    "run_persistence_benchmark",
]
