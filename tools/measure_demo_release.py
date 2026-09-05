"""Offline, counted persistence-service workloads for exact extracted release evidence."""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import platform
import shutil
import sqlite3
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from tools.release_support import validate_external_directory

from synthetic_sales_assist.application.scenarios import ScenarioApplication
from synthetic_sales_assist.demos import DemoError
from synthetic_sales_assist.durable_demo_backend import DurableDemoAuditBackend
from synthetic_sales_assist.persistence.backup import create_backup, verify_backup
from synthetic_sales_assist.persistence.telemetry import aggregate_processing_telemetry


ALIASES = (
    "sales-credit-target-rep", "sales-credit-human-review", "doi-fulfillment-split",
    "doi-full-ds", "doi-manual-review", "doi-overlap",
)


def memory_sample() -> dict[str, int] | None:
    """Read actual current-process Windows working set, not Python allocations."""
    if os.name != "nt":
        return None
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                "PagefileUsage", "PeakPagefileUsage", "PrivateUsage",
            )
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters),
                                      counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return {"working_set_bytes": counters.WorkingSetSize,
            "process_lifetime_peak_working_set_bytes": counters.PeakWorkingSetSize,
            "private_bytes": counters.PrivateUsage}


def distribution(samples: list[int]) -> dict[str, int]:
    values = sorted(samples)
    if not values:
        raise ValueError("EMPTY_MEASUREMENT")
    middle = len(values) // 2
    median = values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) // 2
    return {"count": len(values), "median_ns": median,
            "p95_ns": values[math.ceil(len(values) * .95) - 1], "max_ns": values[-1]}


def storage(path: Path) -> dict[str, int]:
    return {name: item.stat().st_size if item.exists() else 0 for name, item in (
        ("database_bytes", path), ("wal_bytes", Path(str(path) + "-wal")),
        ("shm_bytes", Path(str(path) + "-shm")),
    )}


def run_workload(data_dir: Path, calls: int) -> dict[str, object]:
    if type(calls) is not int or calls < 10 or calls > 100_000 or calls % 10:
        raise ValueError("MULTIPLE_OF_TEN_CALL_COUNT_REQUIRED")
    data_dir = validate_external_directory(data_dir, ROOT)
    if data_dir.exists():
        raise ValueError("NEW_DISPOSABLE_DATA_ROOT_REQUIRED")
    total_start = time.perf_counter_ns()
    application = ScenarioApplication.open(data_dir)
    database = application.database
    backend = DurableDemoAuditBackend(database)
    initial_storage = storage(database.path)
    initial_memory = memory_sample()
    free_disk = shutil.disk_usage(data_dir).free
    setup_ns = time.perf_counter_ns() - total_start
    durations: dict[str, list[int]] = {key: [] for key in ("new", "replay", "conflict", "query")}
    samples = [initial_memory] if initial_memory is not None else []
    started = time.perf_counter_ns()
    cpu_started = time.process_time_ns()
    for group in range(calls // 10):
        views = []
        for index, alias in enumerate(ALIASES):
            tick = time.perf_counter_ns()
            view = backend.run_demo(alias, f"m8-mixed-{group:06d}-{index}")
            durations["new"].append(time.perf_counter_ns() - tick)
            if view.exact_replay or view.conflict:
                raise AssertionError("NEW_RESULT_INVALID")
            views.append(view)
        for index in (group % 6, (group + 3) % 6):
            tick = time.perf_counter_ns()
            replay = backend.run_demo(ALIASES[index], f"m8-mixed-{group:06d}-{index}")
            durations["replay"].append(time.perf_counter_ns() - tick)
            if not replay.exact_replay or replay.conflict or any(
                getattr(replay, name) != getattr(views[index], name)
                for name in ("evaluation_id", "case_id", "run_id", "synthetic_ids")
            ):
                raise AssertionError("REPLAY_IDENTITY_INVALID")
        original = group % 6
        alternate = 1 - original if original < 2 else 2 + (original - 1) % 4
        tick = time.perf_counter_ns()
        try:
            backend.run_demo(ALIASES[alternate], f"m8-mixed-{group:06d}-{original}")
        except DemoError as error:
            if error.code != "IDEMPOTENCY_KEY_MATERIAL_CONFLICT":
                raise
        else:
            raise AssertionError("EXPECTED_CONFLICT_MISSING")
        durations["conflict"].append(time.perf_counter_ns() - tick)
        order = next(item for item in views[original].synthetic_ids
                     if item.startswith("SYN-ORDER-"))
        tick = time.perf_counter_ns()
        (backend.order_show if group % 2 == 0 else backend.case_history)(order)
        durations["query"].append(time.perf_counter_ns() - tick)
        sample = memory_sample()
        if sample is not None:
            samples.append(sample)
    workload_ns = time.perf_counter_ns() - started
    cpu_ns = time.process_time_ns() - cpu_started
    after_storage = storage(database.path)
    verification_start = time.perf_counter_ns()
    status = application.system_status(deep=True)
    if status.database_status != "PASS" or status.projection_status != "PASS":
        raise AssertionError("POST_WORKLOAD_VERIFICATION_FAILED")
    expected = {"sc_evaluations": calls // 5, "doi_evaluations": calls * 2 // 5,
                "durable_command_receipts": calls * 3 // 5,
                "processing_telemetry": calls * 9 // 10}
    with database.read() as connection:
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in expected}
        replay_count = connection.execute(
            "SELECT COUNT(*) FROM processing_telemetry WHERE replay = 1"
        ).fetchone()[0]
        conflict_count = connection.execute(
            "SELECT COUNT(*) FROM processing_telemetry WHERE conflict = 1"
        ).fetchone()[0]
        metrics = aggregate_processing_telemetry(connection)
    if counts != expected or replay_count != calls // 5 or conflict_count != calls // 10:
        raise AssertionError("POST_WORKLOAD_COUNTS_INVALID")
    if any(dict(metrics.safety_counters).values()):
        raise AssertionError("POST_WORKLOAD_SAFETY_INVALID")
    verification_ns = time.perf_counter_ns() - verification_start
    backup_path = data_dir / "backups" / "measured.sqlite3"
    backup_start = time.perf_counter_ns()
    receipt = create_backup(database, backup_path)
    if verify_backup(backup_path) != receipt:
        raise AssertionError("BACKUP_VERIFICATION_FAILED")
    backup_ns = time.perf_counter_ns() - backup_start
    return {
        "schema": "synthetic-sales-assist-m8-measurement/v1", "status": "PASS",
        "method": "PERSISTENCE_SERVICE_BENCHMARK", "ui_registry_limit": 256,
        "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
        "platform": platform.system(), "total_calls": calls,
        "operation_counts": {key: len(value) for key, value in durations.items()},
        "distributions": {key: distribution(value) for key, value in durations.items()},
        "workload_elapsed_ns": workload_ns, "cpu_ns": cpu_ns,
        "cpu_percent_of_one_logical_cpu": cpu_ns * 100 / workload_ns,
        "calls_per_second": calls * 1_000_000_000 / workload_ns,
        "setup_ns": setup_ns, "post_verification_ns": verification_ns,
        "backup_and_readback_ns": backup_ns,
        "total_harness_ns": time.perf_counter_ns() - total_start,
        "memory_initial": initial_memory, "memory_final": memory_sample(),
        "sampled_peak_working_set_bytes": max(
            (item["working_set_bytes"] for item in samples), default=None,
        ),
        "memory_sample_count": len(samples), "storage_initial": initial_storage,
        "storage_after_workload": after_storage, "storage_after_backup": storage(database.path),
        "database_growth_bytes": (after_storage["database_bytes"]
                                  - initial_storage["database_bytes"]),
        "available_disk_bytes_at_start": free_disk, "backup_bytes": backup_path.stat().st_size,
        "backup_sha256": receipt.backup_sha256, "durable_counts": counts,
        "replay_telemetry_rows": replay_count, "conflict_telemetry_rows": conflict_count,
        "safety_counters": dict(metrics.safety_counters),
        "ambient_load": "Same PC; external background load uncontrolled and not measured.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--calls", type=int, choices=(1_000, 10_000), required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    args.report = validate_external_directory(args.report, ROOT)
    if args.report.exists():
        parser.error("report must be new")
    report = run_workload(args.data_dir, args.calls)
    with args.report.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "total_calls": args.calls}))
