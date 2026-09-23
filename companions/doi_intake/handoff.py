"""Validate companion outputs for review, not for synthetic-domain ingestion or OA.

Checksums detect accidental changes, not malicious replacement. A downstream
reader still needs independent authorization and a fresh source check.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import doi_intake as d

JOB_KEYS = {
    "run_order_key", "order_number", "assigned_rep", "source_rows", "first_source_row",
    "priority_group", "priority_reason", "requires_fresh_order_admin_read",
    "historical_context", "state",
}
COUNT_KEYS = {
    "record_rows", "jude_occurrences", "out_of_scope_rows", "blank_rows",
    "unique_jude_orders", "duplicate_jude_occurrences", "held_orders", "lookup_orders",
}
CHECK_KEYS = {
    "grid_reconciles", "assignments_reconcile", "duplicates_reconcile",
    "dispositions_reconcile",
}
SOURCE_KEYS = {
    "kind", "spreadsheet_id", "tab", "gid", "source_date", "source_date_basis",
    "captured_at", "consistency", "grid_rows_read", "requested_record_columns",
    "operational_timezone", "source_unchanged_after_capture",
}
PLAN_KEYS = {
    "schema_version", "version", "run_id", "status", "stage", "sort", "source",
    "source_fingerprint", "counts", "reconciliation", "lookup_queue", "held_orders",
    "source_occurrences", "order_admin_reads", "source_writes", "execution_authorized",
    "candidate_queue_prepared", "integration_state", "warnings", "plan_fingerprint",
}


def require(condition: bool) -> None:
    if not condition:
        raise d.IntakeError("HANDOFF_INVALID", "The bundle failed semantic validation.")


def load_review_queue(
    folder: Path, *, expected_run_id: str, expected_source_date: str,
    max_age_hours: int = 4, allow_synthetic: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Read one verified bundle; return pending candidates separately from held IDs.

    max_age_hours is an intake freshness guard, not an approved DOI business rule.
    Synthetic examples also need --allow-synthetic and are never OA work.
    """
    try:
        return _load(folder, expected_run_id, expected_source_date,
                     max_age_hours, allow_synthetic, now)
    except d.IntakeError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError):
        raise d.IntakeError("HANDOFF_INVALID", "The bundle failed semantic validation.") from None


def _load(folder: Path, run_id: str, source_date: str, max_age: int,
          allow_synthetic: bool, now: datetime | None) -> dict[str, Any]:
    require(type(max_age) is int and 1 <= max_age <= 24)
    require(type(allow_synthetic) is bool)
    current = datetime.now(timezone.utc) if now is None else now
    require(isinstance(current, datetime) and current.tzinfo is not None)
    current = current.astimezone(timezone.utc)
    # Verify the actual bytes read below, not only an earlier file read.
    manifest = d.verify_bundle(folder)
    raw = d.safe_read(folder / "intake.json")
    require(hashlib.sha256(raw).hexdigest() == manifest["files"]["intake.json"])
    plan = d.decode_json(raw.decode("utf-8"))
    require(isinstance(plan, dict) and set(plan) == PLAN_KEYS)
    require(plan["schema_version"] == d.SCHEMA and plan["version"] == d.VERSION)
    require(plan["run_id"] == run_id and plan["stage"] == "PRE_ORDER_ADMIN")
    require(plan["execution_authorized"] is False)
    require(plan["candidate_queue_prepared"] is True)
    require(plan["integration_state"] == "REQUIRES_REVIEWED_READER_ADAPTER")
    for key in ("order_admin_reads", "source_writes"):
        require(type(plan[key]) is int and plan[key] == 0)
    require(plan["sort"] in {"source", "followups"})
    require(isinstance(plan["warnings"], list)
            and all(isinstance(w, str) and len(w) <= 1000 for w in plan["warnings"]))
    source = plan["source"]
    require(isinstance(source, dict) and set(source) == SOURCE_KEYS)
    require(source["kind"] in {"GOOGLE_SHEETS", "SYNTHETIC"})
    synthetic = source["kind"] == "SYNTHETIC"
    if synthetic and not allow_synthetic:
        raise d.IntakeError("SYNTHETIC_QUEUE_BLOCKED", "Example orders are not live work.")
    require(source["spreadsheet_id"] == d.WORKBOOK_ID)
    require(type(source["gid"]) is int)
    days = [k for k, v in d.TABS.items() if v == (source["tab"], source["gid"])]
    require(len(days) == 1 and source["source_date"] == source_date)
    d.validate_source_options(days[0], source_date, run_id)
    require(source["source_date_basis"] == "CALLER_SUPPLIED_NOT_PROVEN_BY_CELLS")
    require(source["requested_record_columns"] == ["A", "B"])
    require(source["operational_timezone"] == "America/New_York")
    require(source["source_unchanged_after_capture"] == "NOT_GUARANTEED")
    expected_consistency = "SYNTHETIC_FIXTURE_NOT_LIVE" if synthetic else d.READ_NOTE
    require(source["consistency"] == expected_consistency)
    captured = d.timestamp(source["captured_at"])
    if captured > current or current - captured > timedelta(hours=max_age):
        raise d.IntakeError("QUEUE_NOT_FRESH", "Capture is future-dated or outside the age limit.")
    grid = source["grid_rows_read"]
    require(type(grid) is int and 2 <= grid <= d.MAX_ROWS)
    counts, checks = plan["counts"], plan["reconciliation"]
    require(isinstance(counts, dict) and set(counts) == COUNT_KEYS)
    require(all(type(v) is int and 0 <= v <= d.MAX_ROWS for v in counts.values()))
    require(isinstance(checks, dict) and set(checks) == CHECK_KEYS)
    require(all(v is True for v in checks.values()))
    queue, holds, occurrences = (plan[k] for k in
                                ("lookup_queue", "held_orders", "source_occurrences"))
    require(all(isinstance(v, list) and len(v) <= d.MAX_ROWS for v in
                (queue, holds, occurrences)))
    all_jobs = queue + holds
    numbers: set[str] = set()
    rows_seen: set[int] = set()
    expected_occurrences = []
    history_records = []
    for held, jobs in ((False, queue), (True, holds)):
        state = "HELD_ASSIGNMENT_CONFLICT" if held else "PENDING_ORDER_ADMIN_READ"
        for position, job in enumerate(jobs, 1):
            require(isinstance(job, dict)
                    and set(job) == JOB_KEYS | (set() if held else {"queue_position"}))
            number = job["order_number"]
            require(d.canonical_id(number) is not None and number not in numbers)
            numbers.add(number)
            require(job["assigned_rep"] == "JUDE" and job["state"] == state)
            require(job["run_order_key"] == f"{run_id}|{number}")
            require(job["requires_fresh_order_admin_read"] is True)
            if not held:
                require(type(job["queue_position"]) is int and job["queue_position"] == position)
            rows = job["source_rows"]
            require(isinstance(rows, list) and 0 < len(rows) < grid)
            require(all(type(r) is int and 2 <= r <= grid for r in rows))
            require(rows == sorted(set(rows)) and not rows_seen.intersection(rows))
            require(type(job["first_source_row"]) is int and job["first_source_row"] == rows[0])
            rows_seen.update(rows)
            require(type(job["priority_group"]) is int)
            for row in rows:
                expected_occurrences.append({"run_order_key": job["run_order_key"],
                                             "order_number": number, "source_row": row,
                                             "state": state})
            past = job["historical_context"]
            if past is not None:
                require(isinstance(past, dict) and set(past) == {
                    "historical_only", "observations", "latest", "conflicting_latest"})
                require(past["historical_only"] is True)
                require(isinstance(past["observations"], list) and bool(past["observations"]))
                require(all(isinstance(r, dict) and r.get("order_number") == number
                            for r in past["observations"]))
                history_records.extend(past["observations"])
    histories = d.history_for_orders({"schema_version": d.HISTORY_SCHEMA,
                                      "records": history_records}, numbers,
                                     source["captured_at"])
    for job in all_jobs:
        past = histories.get(job["order_number"])
        require(d.canonical(job["historical_context"]) == d.canonical(past))
        reason, priority = "SOURCE_ORDER", 0
        if plan["sort"] == "followups":
            latest = past["latest"] if past else None
            if latest and latest["lookup_state"] in {"unfinished", "failed"}:
                reason, priority = "HISTORICAL_UNFINISHED_CHECK", 0
            elif latest and latest["followup_at"] and d.timestamp(latest["followup_at"]) <= captured:
                reason, priority = "HISTORICAL_FOLLOWUP_DUE", 1
            elif past is None:
                reason, priority = "NO_PRIOR_HISTORY", 2
            else:
                reason = "CONFLICTING_HISTORY" if past["conflicting_latest"] else "HISTORICAL_RECHECK"
                priority = 3
        require(job["priority_reason"] == reason and job["priority_group"] == priority)
    require(queue == sorted(queue, key=lambda j: (j["priority_group"],
                                                  j["first_source_row"], j["order_number"])))
    require(holds == sorted(holds, key=lambda j: j["first_source_row"]))
    require(d.canonical(occurrences) == d.canonical(sorted(expected_occurrences,
                                                        key=lambda o: o["source_row"])))
    require(counts["record_rows"] + counts["blank_rows"] == grid - 1)
    require(counts["record_rows"] == counts["jude_occurrences"] + counts["out_of_scope_rows"])
    require(counts["jude_occurrences"] == len(rows_seen))
    require(counts["unique_jude_orders"] == len(numbers))
    require(counts["duplicate_jude_occurrences"] == len(rows_seen) - len(numbers))
    require(counts["lookup_orders"] == len(queue) and counts["held_orders"] == len(holds))
    expected_status = ("NO_JUDE_ORDERS" if not numbers else
                       "PREPARED_WITH_HOLDS" if holds else "PREPARED")
    require(plan["status"] == expected_status)
    identity = {k: source[k] for k in ("kind", "spreadsheet_id", "tab", "gid",
                                     "source_date", "source_date_basis")}
    projection = {"orders": [
        {"order_number": j["order_number"], "source_rows": j["source_rows"],
         "assignment_conflict": j["state"] == "HELD_ASSIGNMENT_CONFLICT"}
        for j in sorted(all_jobs, key=lambda j: j["first_source_row"])],
        "counts": counts, "reconciliation": checks}
    require(plan["source_fingerprint"] == d.digest({"identity": identity,
            "projection": projection, "normalization": d.NORM_VERSION,
            "intake_version": d.VERSION}))
    material = {k: v for k, v in plan.items() if k not in
                {"source", "warnings", "plan_fingerprint"}}
    material["source_identity"] = identity
    require(plan["plan_fingerprint"] == d.digest(material))
    # Report and CSV files must encode this same plan, not merely have valid hashes.
    for name, content in d.bundle_files(plan).items():
        require(hashlib.sha256(content).hexdigest() == manifest["files"][name])
    final_manifest = d.verify_bundle(folder)
    require(d.canonical(final_manifest) == d.canonical(manifest))
    return {"schema_version": "sales-assist-doi-review-queue/v1",
            "status": "SYNTHETIC_REVIEW_ONLY" if synthetic else "REVIEW_ONLY",
            "run_id": run_id, "source_date": source_date,
            "captured_at": source["captured_at"], "reviewed_at": current.isoformat(),
            "max_age_hours": max_age, "source_kind": source["kind"],
            "plan_fingerprint": plan["plan_fingerprint"],
            "lookup_queue": queue,
            "held_order_numbers": [j["order_number"] for j in holds],
            "counts": counts, "execution_authorized": False,
            "synthetic_database_writes": 0, "order_admin_reads": 0,
            "source_authenticity": "NOT_PROVEN_BY_CHECKSUMS",
            "next_step": "HUMAN_REVIEW_AND_SEPARATE_READ_ONLY_ADAPTER_AUTHORIZATION"}
