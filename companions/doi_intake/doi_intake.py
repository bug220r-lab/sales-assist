#!/usr/bin/env python3
"""Read-only DOI intake companion. No Order Admin adapter or source writes.

Python 3.10+. Offline demo/tests use only the standard library. Live acquisition
uses a separately authorized, Sheets-read-only Google OAuth token. This is NOT a
replacement for the synthetic Sales Assist domain engine or an R01/R02 adapter.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping

VERSION = "1.0.0"
SCHEMA = "sales-assist-doi-intake/v1"
HISTORY_SCHEMA = "sales-assist-doi-intake-history/v1"
WORKBOOK_ID = "1OKbjzvMHcxlksqg7cnXV_G9PG92-92vHMX8FGfFwCPA"
TABS = {"monday": ("DOI Monday", 0), "wednesday": ("DOI Wednesday", 1267803554),
        "friday": ("DOI Friday", 593832135)}
ANCHORS = {"A1": None, "B1": None, "E1": "Rep", "F1": "# Of Orders", "G1": "Completed"}
SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
SCOPES = [SCOPE]
TRIM = "\t\n\r "
MAX_ID = 9007199254740991
MAX_ROWS = 25000
MAX_BYTES = 25 * 1024 * 1024
API = "https://sheets.googleapis.com/v4/spreadsheets/"
META_FIELDS = "spreadsheetId,sheets(properties(sheetId,title,gridProperties(rowCount,columnCount)))"
DATA_FIELDS = (
    "spreadsheetId,sheets(properties(sheetId,title,gridProperties(rowCount,columnCount)),"
    "merges,data(startRow,startColumn,rowData(values(userEnteredValue,effectiveValue,"
    "effectiveFormat(numberFormat(type))))))"
)
READ_NOTE = "TWO_EQUAL_READS_NO_REVISION_LOCK"
NORM_VERSION = "doi-jude-normalization-algorithm/v1"
NORM_DIGEST = "657f304462a6ca8674322562bc378eee8392abdb59061a4b7f5659932dffd8af"


class IntakeError(Exception):
    """Safe error: messages are fixed text, never raw source or credential values."""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


class NumberLexeme(str):
    """Exact lexical JSON number; never reconstruct a source number from float."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise IntakeError("INVALID_JSON", "Duplicate JSON object members are not accepted.")
        obj[key] = value
    return obj


def decode_json(raw: str, *, api_numbers: bool = False) -> Any:
    try:
        return json.loads(raw, object_pairs_hook=_unique_object,
                          parse_float=NumberLexeme if api_numbers else Decimal,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError, RecursionError) as exc:
        raise IntakeError("INVALID_JSON", "Input is not supported finite JSON.") from exc


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def timestamp(value: Any) -> datetime:
    try:
        if not isinstance(value, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value
        ):
            raise ValueError()
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError()
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError) as exc:
        raise IntakeError("INVALID_TIMESTAMP", "Use an ISO timestamp including its UTC offset.") from exc


def canonical_id(value: Any, *, numeric: bool = False) -> str | None:
    """Conservative positive-ID subset, not a claimed full R01 implementation."""
    if isinstance(value, bool):
        return None
    if numeric:
        if isinstance(value, NumberLexeme):
            # Reject scientific notation, signs, fractional IDs and ambiguous floats.
            if not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value):
                return None
            try:
                n = Decimal(value)
                if n != n.to_integral_value() or not 1 <= n <= MAX_ID:
                    return None
                return str(int(n))
            except InvalidOperation:
                return None
        if isinstance(value, int) and 1 <= value <= MAX_ID:
            return str(value)
        return None
    if not isinstance(value, str) or isinstance(value, NumberLexeme):
        return None
    if re.fullmatch(r"[1-9][0-9]{0,15}", value) and int(value) <= MAX_ID:
        return value
    return None


@dataclass(frozen=True)
class Cell:
    kind: str
    value: str | int | None = None


BLANK = Cell("BLANK")


def google_cell(raw: Mapping[str, Any]) -> Cell:
    if not isinstance(raw, dict):
        return Cell("UNSUPPORTED")
    entered, effective = raw.get("userEnteredValue", {}), raw.get("effectiveValue", {})
    if not isinstance(entered, dict) or not isinstance(effective, dict):
        return Cell("UNSUPPORTED")
    if "formulaValue" in entered:
        return Cell("FORMULA")
    if "errorValue" in effective:
        return Cell("ERROR")
    fmt = raw.get("effectiveFormat", {}).get("numberFormat", {}).get("type")
    if fmt in {"DATE", "TIME", "DATE_TIME", "DURATION"} and (entered or effective):
        return Cell("DATE_TIME")
    if not entered and not effective:
        return BLANK
    if entered != effective or len(entered) != 1:
        return Cell("UNSUPPORTED")
    if "stringValue" in entered and isinstance(entered["stringValue"], str):
        return Cell("TEXT", entered["stringValue"])
    if "numberValue" in entered:
        number = canonical_id(entered["numberValue"], numeric=True)
        return Cell("NUMBER", number) if number else Cell("INVALID_NUMBER")
    if "boolValue" in entered:
        return Cell("BOOLEAN")
    return Cell("UNSUPPORTED")


def assignee(cell: Cell) -> str:
    if cell.kind != "TEXT" or not isinstance(cell.value, str):
        return "MALFORMED"
    value = cell.value.strip(TRIM)
    # ASCII-only lowercase; deliberately NOT strip() / Unicode casefold().
    lowered = value.translate(str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"))
    return "JUDE" if lowered == "jude" else ("EMPTY_TEXT" if value == "" else "OTHER")


@dataclass(frozen=True)
class Source:
    kind: str
    day: str
    source_date: str
    captured_at: str
    row_count: int
    rows: tuple[tuple[Cell, Cell], ...]
    anchors: Mapping[str, Cell]
    workbook_id: str = WORKBOOK_ID
    consistency: str = READ_NOTE
    merged_input: bool = False

    def identity(self) -> dict:
        title, gid = TABS[self.day]
        return {"kind": self.kind, "spreadsheet_id": self.workbook_id, "tab": title,
                "gid": gid, "source_date": self.source_date,
                "source_date_basis": "CALLER_SUPPLIED_NOT_PROVEN_BY_CELLS"}

    def acquisition(self) -> dict:
        return {**self.identity(), "captured_at": self.captured_at,
                "consistency": self.consistency, "grid_rows_read": self.row_count,
                "requested_record_columns": ["A", "B"],
                "operational_timezone": "America/New_York",
                "source_unchanged_after_capture": "NOT_GUARANTEED"}


def validate_source_options(day: str, source_date: str, run_id: str) -> None:
    if day not in TABS:
        raise IntakeError("INVALID_DAY", "Select monday, wednesday or friday.")
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", source_date):
            raise ValueError()
        parsed = date.fromisoformat(source_date)
    except ValueError as exc:
        raise IntakeError("INVALID_SOURCE_DATE", "Supply the actual batch date as YYYY-MM-DD.") from exc
    if parsed.weekday() != {"monday": 0, "wednesday": 2, "friday": 4}[day]:
        raise IntakeError("SOURCE_DAY_MISMATCH", "The batch date must match the selected weekday tab.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", run_id) or run_id.split(".", 1)[0].upper() in {
        "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))
    } or run_id.endswith("."):
        raise IntakeError("INVALID_RUN_ID", "Use a safe 1-80-character run ID, not a path or device name.")


def selected_properties(payload: dict, day: str) -> dict:
    if not isinstance(payload, dict) or payload.get("spreadsheetId") != WORKBOOK_ID:
        raise IntakeError("SOURCE_IDENTITY_MISMATCH", "The response is not the configured manager workbook.")
    title, gid = TABS[day]
    matches = [s.get("properties", {}) for s in payload.get("sheets", [])
               if s.get("properties", {}).get("sheetId") == gid]
    if len(matches) != 1 or type(matches[0].get("sheetId")) is not int or matches[0].get("title") != title:
        raise IntakeError("SOURCE_IDENTITY_MISMATCH", "The selected tab title and gid must match the saved contract.")
    grid = matches[0].get("gridProperties", {})
    n, width = grid.get("rowCount"), grid.get("columnCount")
    if type(n) is not int or type(width) is not int or not 2 <= n <= MAX_ROWS or width < 7:
        raise IntakeError("SOURCE_BOUNDS_UNSUPPORTED", "Grid must contain 2-25,000 rows and at least seven columns. No truncation is allowed.")
    return matches[0]


def source_from_google(payload: dict, props: dict, day: str, source_date: str, captured_at: str,
                       *, kind: str = "GOOGLE_SHEETS") -> Source:
    current = selected_properties(payload, day)
    if current != props:
        raise IntakeError("SOURCE_CHANGED_DURING_READ", "Tab identity or grid bounds changed during acquisition.")
    n = props["gridProperties"]["rowCount"]
    gid = props["sheetId"]
    sheet = next(s for s in payload["sheets"] if s.get("properties", {}).get("sheetId") == gid)
    coords: dict[tuple[int, int], Cell] = {}
    blocks = sheet.get("data", [])
    if not isinstance(blocks, list) or not blocks:
        raise IntakeError("SOURCE_RESPONSE_INCOMPLETE", "The requested grid data was not returned.")
    if len(blocks) != 3 or {(b.get("startRow", 0), b.get("startColumn", 0)) for b in blocks} != {(0, 0), (0, 4), (1, 0)}:
        raise IntakeError("SOURCE_RESPONSE_INCOMPLETE", "All three requested range blocks must be present, including empty blocks.")
    for block in blocks:
        r0, c0 = block.get("startRow", 0), block.get("startColumn", 0)
        if type(r0) is not int or type(c0) is not int:
            raise IntakeError("SOURCE_RESPONSE_INVALID", "Invalid grid offsets.")
        end_row, end_column = {(0, 0): (1, 2), (0, 4): (1, 7), (1, 0): (n, 2)}[(r0, c0)]
        rows_data = block.get("rowData", [])
        if not isinstance(rows_data, list) or len(rows_data) > end_row - r0:
            raise IntakeError("SOURCE_RESPONSE_INVALID", "A returned grid block exceeds its requested row bounds.")
        for r, row in enumerate(rows_data, r0):
            values = row.get("values", [])
            if not isinstance(values, list) or len(values) > end_column - c0:
                raise IntakeError("SOURCE_RESPONSE_INVALID", "A returned grid block exceeds its requested column bounds.")
            for c, raw in enumerate(values, c0):
                if not (r0 <= r < end_row and c0 <= c < end_column):
                    raise IntakeError("SOURCE_RESPONSE_INVALID", "The response contains cells outside its requested range.")
                if (r, c) in coords:
                    raise IntakeError("SOURCE_RESPONSE_INVALID", "Overlapping grid blocks are not accepted.")
                coords[r, c] = google_cell(raw)
    merged = False
    for merge in sheet.get("merges", []):
        rs, re_ = merge.get("startRowIndex", 0), merge.get("endRowIndex", n)
        cs, ce = merge.get("startColumnIndex", 0), merge.get("endColumnIndex", props["gridProperties"]["columnCount"])
        if (rs < n and re_ > 0 and cs < 2 and ce > 0) or (rs <= 0 < re_ and cs < 7 and ce > 4):
            merged = True
    anchors = {"A1": coords.get((0, 0), BLANK), "B1": coords.get((0, 1), BLANK),
               "E1": coords.get((0, 4), BLANK), "F1": coords.get((0, 5), BLANK),
               "G1": coords.get((0, 6), BLANK)}
    rows = tuple((coords.get((r, 0), BLANK), coords.get((r, 1), BLANK)) for r in range(1, n))
    return Source(kind, day, source_date, captured_at, n, rows, anchors, merged_input=merged)


def _read_get(session: Any, params: dict, sleep: Callable[[float], None] = time.sleep) -> dict:
    """The only data-network operation in this module is GET to the fixed Sheets host."""
    for attempt in range(4):
        response = None
        try:
            response = session.get(API + WORKBOOK_ID, params=params, timeout=(10, 45),
                                   allow_redirects=False, stream=True)
            code = response.status_code
            if code in (429, 500, 502, 503, 504) and attempt < 3:
                response.close()
                sleep(2 ** attempt)
                continue
            if code != 200:
                failure = {401: "GOOGLE_AUTH_REQUIRED", 403: "GOOGLE_ACCESS_DENIED", 404: "GOOGLE_SOURCE_NOT_FOUND"}.get(code, "GOOGLE_READ_FAILED")
                raise IntakeError(failure, "Google did not provide a readable source. No lookup queue was released.")
            content = bytearray()
            for chunk in response.iter_content(chunk_size=65536):
                content.extend(chunk)
                if len(content) > MAX_BYTES:
                    raise IntakeError("SOURCE_RESPONSE_TOO_LARGE", "Response exceeds the read cap; nothing was truncated or released.")
            return decode_json(content.decode("utf-8"), api_numbers=True)
        except IntakeError:
            raise
        except Exception as exc:
            # Do not echo HTTP bodies, token details, source values or stack traces.
            raise IntakeError("GOOGLE_TRANSPORT_FAILED", "Source transport failed. No lookup queue was released.") from exc
        finally:
            if response is not None:
                response.close()
    raise IntakeError("GOOGLE_READ_FAILED", "The bounded read retry budget was exhausted.")


def acquire_google(session: Any, day: str, source_date: str,
                   *, clock: Callable[[], str] = iso_now) -> Source:
    props = selected_properties(_read_get(session, {"fields": META_FIELDS}), day)
    n = props["gridProperties"]["rowCount"]
    title = props["title"].replace("'", "''")
    ranges = [f"'{title}'!A1:B1", f"'{title}'!E1:G1", f"'{title}'!A2:B{n}"]
    params = {"fields": DATA_FIELDS, "ranges": ranges}
    first = source_from_google(_read_get(session, params), props, day, source_date, clock())
    second = source_from_google(_read_get(session, params), props, day, source_date, clock())
    if (first.rows, first.anchors, first.merged_input) != (second.rows, second.anchors, second.merged_input):
        raise IntakeError("SOURCE_CHANGED_DURING_READ", "The two source reads differ. Run again against a stable source.")
    # Equal reads are NOT a Google revision lock or proof of R02 provider coherence.
    return second


def project_source(source: Source) -> dict:
    timestamp(source.captured_at)
    if source.row_count != len(source.rows) + 1 or not 2 <= source.row_count <= MAX_ROWS:
        raise IntakeError("SOURCE_RESPONSE_INCOMPLETE", "The entire bounded A:B grid must be accounted for.")
    if source.merged_input or set(source.anchors) != set(ANCHORS) or any(
        source.anchors[key] != (BLANK if expected is None else Cell("TEXT", expected))
        for key, expected in ANCHORS.items()
    ):
        raise IntakeError("SOURCE_SCHEMA_UNRECOGNIZED", "Expected physical-blank A1/B1 and exact E1:G1 anchors, with no input merges.")
    jude: dict[str, list[int]] = {}
    other: set[str] = set()
    counts = {"record_rows": 0, "jude_occurrences": 0, "out_of_scope_rows": 0, "blank_rows": 0}
    for row_number, (a, b) in enumerate(source.rows, 2):
        if a == BLANK and b == BLANK:
            counts["blank_rows"] += 1
            continue
        counts["record_rows"] += 1
        order = canonical_id(a.value) if a.kind in ("TEXT", "NUMBER") else None
        owner = assignee(b)
        if order is None or owner == "MALFORMED":
            raise IntakeError("SOURCE_SCHEMA_UNRECOGNIZED", "At least one populated A:B row has an invalid order ID or non-text/physical-blank rep. The entire batch is held.")
        if owner == "JUDE":
            jude.setdefault(order, []).append(row_number)
            counts["jude_occurrences"] += 1
        else:
            counts["out_of_scope_rows"] += 1
            if owner == "OTHER":
                other.add(order)
    conflicts = set(jude).intersection(other)
    # Other-rep names, order IDs and row locators are never part of the persisted projection.
    counts["unique_jude_orders"] = len(jude)
    counts["duplicate_jude_occurrences"] = counts["jude_occurrences"] - len(jude)
    counts["held_orders"] = len(conflicts)
    counts["lookup_orders"] = len(jude) - len(conflicts)
    checks = {
        "grid_reconciles": counts["record_rows"] + counts["blank_rows"] == len(source.rows),
        "assignments_reconcile": counts["record_rows"] == counts["jude_occurrences"] + counts["out_of_scope_rows"],
        "duplicates_reconcile": counts["jude_occurrences"] == counts["unique_jude_orders"] + counts["duplicate_jude_occurrences"],
        "dispositions_reconcile": counts["unique_jude_orders"] == counts["lookup_orders"] + counts["held_orders"],
    }
    if not all(checks.values()):
        raise IntakeError("RECONCILIATION_FAILED", "Source counts did not reconcile.")
    return {"orders": [{"order_number": number, "source_rows": rows,
                         "assignment_conflict": number in conflicts} for number, rows in jude.items()],
            "counts": counts, "reconciliation": checks}


def read_history(path: Path | None) -> Any:
    if path is None:
        return {"schema_version": HISTORY_SCHEMA, "records": []}
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise IntakeError("HISTORY_TOO_LARGE", "History exceeds the local file size cap.")
        return decode_json(raw.decode("utf-8-sig"))
    except (OSError, UnicodeError) as exc:
        raise IntakeError("HISTORY_UNREADABLE", "The supplied history file could not be read.") from exc


def history_for_orders(raw: Any, order_ids: set[str], captured_at: str) -> dict[str, dict]:
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "records"} or raw["schema_version"] != HISTORY_SCHEMA or not isinstance(raw["records"], list):
        raise IntakeError("HISTORY_SCHEMA_UNRECOGNIZED", "History must use the bundled, versioned history contract.")
    allowed = {"order_number", "observed_at", "lookup_state", "followup_at", "last_known_status", "evidence_ref"}
    grouped: dict[str, list[dict]] = {}
    now = timestamp(captured_at)
    for record in raw["records"]:
        if not isinstance(record, dict) or set(record) != allowed or canonical_id(record.get("order_number")) is None:
            raise IntakeError("HISTORY_SCHEMA_UNRECOGNIZED", "History records must have the documented fields and canonical order IDs.")
        # Do not retain unrelated order histories in the output.
        if record["order_number"] not in order_ids:
            continue
        observed = timestamp(record["observed_at"])
        if observed > now:
            raise IntakeError("HISTORY_FROM_FUTURE", "Historical observations cannot postdate this acquisition.")
        if record["lookup_state"] not in {"unfinished", "failed", "completed", "unknown"}:
            raise IntakeError("HISTORY_SCHEMA_UNRECOGNIZED", "Unrecognized historical lookup state.")
        followup = record["followup_at"]
        if followup is not None:
            followup = timestamp(followup).isoformat()
        if not all(isinstance(record[k], str) and len(record[k]) <= 500 and not any(ord(c) < 32 for c in record[k])
                   for k in ("last_known_status", "evidence_ref")) or not record["evidence_ref"]:
            raise IntakeError("HISTORY_SCHEMA_UNRECOGNIZED", "History status and evidence reference must be bounded plain text.")
        item = {**record, "observed_at": observed.isoformat(), "followup_at": followup}
        bucket = grouped.setdefault(record["order_number"], [])
        if item not in bucket:
            bucket.append(item)
    result: dict[str, dict] = {}
    for order, observations in grouped.items():
        observations.sort(key=lambda item: (timestamp(item["observed_at"]), canonical(item)))
        latest_at = observations[-1]["observed_at"]
        latest = [item for item in observations if item["observed_at"] == latest_at]
        operational = {(item["lookup_state"], item["followup_at"], item["last_known_status"]) for item in latest}
        result[order] = {"historical_only": True, "observations": observations,
                         "latest": latest[-1] if len(operational) == 1 else None,
                         "conflicting_latest": len(operational) > 1}
    return result


def make_plan(source: Source, run_id: str, *, sort: str = "source", history: Any = None) -> dict:
    validate_source_options(source.day, source.source_date, run_id)
    if sort not in {"source", "followups"}:
        raise IntakeError("INVALID_SORT", "Supported sorts are source and followups.")
    projection = project_source(source)
    histories = history_for_orders(history if history is not None else read_history(None),
                                   {o["order_number"] for o in projection["orders"]}, source.captured_at)
    # Own companion identity only. Not an R01 SourceRef, R02 batch ID or domain hash.
    source_fp = digest({"identity": source.identity(), "projection": projection,
                        "normalization": NORM_VERSION, "intake_version": VERSION})
    day_now = timestamp(source.captured_at)
    jobs, holds, occurrences = [], [], []
    for order in projection["orders"]:
        number, rows = order["order_number"], order["source_rows"]
        past = histories.get(number)
        reason, priority = "SOURCE_ORDER", 0
        if sort == "followups":
            latest = past["latest"] if past else None
            if latest and latest["lookup_state"] in {"unfinished", "failed"}:
                reason, priority = "HISTORICAL_UNFINISHED_CHECK", 0
            elif latest and latest["followup_at"] and timestamp(latest["followup_at"]) <= day_now:
                reason, priority = "HISTORICAL_FOLLOWUP_DUE", 1
            elif past is None:
                reason, priority = "NO_PRIOR_HISTORY", 2
            else:
                reason, priority = ("CONFLICTING_HISTORY" if past["conflicting_latest"] else "HISTORICAL_RECHECK"), 3
        job = {"run_order_key": f"{run_id}|{number}", "order_number": number, "assigned_rep": "JUDE",
               "source_rows": rows, "first_source_row": min(rows),
               "priority_group": priority, "priority_reason": reason,
               "requires_fresh_order_admin_read": True, "historical_context": past,
               "state": "HELD_ASSIGNMENT_CONFLICT" if order["assignment_conflict"] else "PENDING_ORDER_ADMIN_READ"}
        (holds if order["assignment_conflict"] else jobs).append(job)
        for row in rows:
            occurrences.append({"run_order_key": job["run_order_key"], "order_number": number,
                                "source_row": row, "state": job["state"]})
    jobs.sort(key=lambda j: (j["priority_group"], j["first_source_row"], j["order_number"]))
    for position, job in enumerate(jobs, 1):
        job["queue_position"] = position
    occurrences.sort(key=lambda item: item["source_row"])
    status = "PREPARED_WITH_HOLDS" if holds else "PREPARED"
    if not projection["counts"]["jude_occurrences"]:
        status = "NO_JUDE_ORDERS"
    # The candidate queue does not authorize OA reads. A future reader must perform
    # its own scope/freshness/authorization checks and map the companion contract.
    content = {"schema_version": SCHEMA, "version": VERSION, "run_id": run_id,
               "status": status, "stage": "PRE_ORDER_ADMIN", "sort": sort,
               "source": source.acquisition(), "source_fingerprint": source_fp,
               "counts": projection["counts"], "reconciliation": projection["reconciliation"],
               "lookup_queue": jobs, "held_orders": holds, "source_occurrences": occurrences,
               "order_admin_reads": 0, "source_writes": 0,
               "execution_authorized": False, "candidate_queue_prepared": True,
               "integration_state": "REQUIRES_REVIEWED_READER_ADAPTER",
               "warnings": ["Source date is caller supplied, not inferred from the tab.",
                            "No live status, totals, stock, split eligibility, or business outcome is inferred.",
                            "Old shipped/canceled/excluded statuses do not suppress a fresh lookup.",
                            "Two matching reads do not provide a revision lock or full R02 compliance."]}
    if source.kind != "GOOGLE_SHEETS":
        content["warnings"].append("SYNTHETIC PREVIEW: never process these example order numbers in Order Admin.")
    # Fresh capture timestamps are not material for exact import replay. Any changed
    # effective priority, source membership, history, configuration or version is.
    material = {k: v for k, v in content.items() if k not in {"source", "warnings"}}
    material["source_identity"] = source.identity()
    content["plan_fingerprint"] = digest(material)
    return content


def default_home() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return base / "SalesAssistDOIIntake"


def safe_read(path: Path, limit: int = MAX_BYTES) -> bytes:
    try:
        with path.open("rb") as handle:
            data = handle.read(limit + 1)
        if len(data) > limit:
            raise IntakeError("FILE_TOO_LARGE", "A local file exceeds the supported size cap.")
        return data
    except OSError as exc:
        raise IntakeError("LOCAL_FILE_UNREADABLE", "A required local file could not be read.") from exc


def load_credentials(token: Path) -> Any:
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError as exc:
        raise IntakeError("GOOGLE_DEPENDENCIES_MISSING", "Install requirements-google.txt for live Google access. Demo and tests need no packages.") from exc
    if not token.exists():
        raise IntakeError("GOOGLE_AUTH_REQUIRED", "Run the auth command with your approved Desktop OAuth client file first.")
    data = decode_json(safe_read(token, 65536).decode("utf-8"))
    if not isinstance(data, dict) or set(data.get("scopes", [])) != {SCOPE} or data.get("token_uri") != "https://oauth2.googleapis.com/token":
        raise IntakeError("GOOGLE_TOKEN_SCOPE_MISMATCH", "Use this companion's separate Sheets-read-only token, not an existing broader token.")
    try:
        credentials = Credentials.from_authorized_user_info(data, SCOPES)
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            write_secret(token, credentials.to_json())
        if not credentials.valid:
            raise IntakeError("GOOGLE_AUTH_REQUIRED", "Reauthorize the companion with the auth command.")
        return credentials
    except IntakeError:
        raise
    except Exception as exc:
        raise IntakeError("GOOGLE_AUTH_FAILED", "Google authorization failed. Credential details were not logged.") from exc


def write_secret(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".oauth-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def authorize(client_secret: Path, token: Path) -> None:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise IntakeError("GOOGLE_DEPENDENCIES_MISSING", "Install requirements-google.txt before authorizing.") from exc
    if token.resolve() == client_secret.resolve():
        raise IntakeError("INVALID_TOKEN_PATH", "The token file must not overwrite the OAuth client file.")
    config = decode_json(safe_read(client_secret, 65536).decode("utf-8"))
    installed = config.get("installed", {}) if isinstance(config, dict) else {}
    if installed.get("auth_uri") != "https://accounts.google.com/o/oauth2/auth" or installed.get("token_uri") != "https://oauth2.googleapis.com/token":
        raise IntakeError("INVALID_OAUTH_CLIENT", "Use an approved Google Desktop OAuth client with Google's standard endpoints.")
    try:
        flow = InstalledAppFlow.from_client_config(config, scopes=SCOPES)
        credentials = flow.run_local_server(host="127.0.0.1", port=0, access_type="offline",
                                            prompt="consent", timeout_seconds=180,
                                            authorization_prompt_message="Opening Google authorization in your browser.",
                                            success_message="DOI intake authorization completed. You may close this tab.")
        granted = getattr(credentials, "granted_scopes", None) or credentials.scopes
        if set(granted or []) != {SCOPE}:
            raise IntakeError("GOOGLE_TOKEN_SCOPE_MISMATCH", "Google did not grant exactly the requested read-only Sheets scope.")
        write_secret(token, credentials.to_json())
    except IntakeError:
        raise
    except Exception as exc:
        raise IntakeError("GOOGLE_AUTH_FAILED", "Authorization was not completed. No credential details were logged.") from exc


def google_session(token: Path) -> Any:
    credentials = load_credentials(token)
    from google.auth.transport.requests import AuthorizedSession
    return AuthorizedSession(credentials)


def csv_bytes(headers: list[str], rows: list[dict]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=headers, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        cleaned = {}
        for header in headers:
            value = row.get(header, "")
            if value is None:
                value = ""
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
            value = str(value)
            # Spreadsheet formula-injection guard. JSON is the machine interchange.
            if value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
                value = "'" + value
            cleaned[header] = value
        writer.writerow(cleaned)
    return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def bundle_files(plan: dict) -> dict[str, bytes]:
    headers = ["queue_position", "run_order_key", "order_number", "assigned_rep", "source_rows",
               "priority_group", "priority_reason", "state", "requires_fresh_order_admin_read"]
    report = {key: value for key, value in plan.items()
              if key not in {"lookup_queue", "held_orders", "source_occurrences"}}
    return {"intake.json": json_bytes(plan), "report.json": json_bytes(report),
            "lookup_queue.csv": csv_bytes(headers, plan["lookup_queue"]),
            "held_orders.csv": csv_bytes(headers, plan["held_orders"]),
            "source_occurrences.csv": csv_bytes(["run_order_key", "order_number", "source_row", "state"], plan["source_occurrences"])}


def verify_bundle(folder: Path) -> dict:
    if folder.is_symlink() or not folder.is_dir():
        raise IntakeError("OUTPUT_NOT_VERIFIABLE", "The run folder is missing or is a symbolic link.")
    manifest_path = folder / "manifest.json"
    if manifest_path.is_symlink():
        raise IntakeError("OUTPUT_NOT_VERIFIABLE", "Manifest must be a regular local file.")
    try:
        manifest = decode_json(safe_read(manifest_path).decode("utf-8"))
        expected = {"intake.json", "report.json", "lookup_queue.csv", "held_orders.csv", "source_occurrences.csv"}
        if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA or set(manifest.get("files", {})) != expected:
            raise IntakeError("OUTPUT_NOT_VERIFIABLE", "The completion manifest is missing or invalid.")
        for name, checksum in manifest["files"].items():
            target = folder / name
            if target.is_symlink() or not re.fullmatch(r"[a-f0-9]{64}", str(checksum)) or hashlib.sha256(safe_read(target)).hexdigest() != checksum:
                raise IntakeError("OUTPUT_INTEGRITY_FAILED", "A run output differs from its completion manifest.")
        plan = decode_json(safe_read(folder / "intake.json").decode("utf-8"))
        if plan.get("plan_fingerprint") != manifest.get("plan_fingerprint") or plan.get("run_id") != manifest.get("run_id"):
            raise IntakeError("OUTPUT_INTEGRITY_FAILED", "Run identity does not match the manifest.")
        return manifest
    except IntakeError:
        raise
    except (ValueError, KeyError, TypeError, AttributeError, UnicodeError) as exc:
        raise IntakeError("OUTPUT_NOT_VERIFIABLE", "The saved run is not a valid companion output bundle.") from exc


def save_bundle(plan: dict, root: Path) -> tuple[Path, bool]:
    validate_source_options(plan["source"]["day"] if "day" in plan["source"] else
                            next(k for k, v in TABS.items() if v[0] == plan["source"]["tab"]),
                            plan["source"]["source_date"], plan["run_id"])
    root.mkdir(parents=True, exist_ok=True)
    target = root / plan["run_id"]
    lock = root / ("." + plan["run_id"] + ".lock")
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise IntakeError("RUN_LOCKED", "This run is being written or has an abandoned lock. Do not start concurrent writers.") from exc
    temp: Path | None = None
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
        if target.exists() or target.is_symlink():
            old = verify_bundle(target)
            if old["plan_fingerprint"] == plan["plan_fingerprint"]:
                return target, True
            raise IntakeError("RUN_CONFLICT", "This run ID already has different source/history/sort content. Use a new explicit run ID; the old run was not overwritten.")
        temp = Path(tempfile.mkdtemp(prefix="." + plan["run_id"] + "-", dir=root))
        files = bundle_files(plan)
        hashes = {}
        for name, content in files.items():
            with (temp / name).open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            hashes[name] = hashlib.sha256(content).hexdigest()
        manifest = {"schema_version": SCHEMA, "version": VERSION, "run_id": plan["run_id"],
                    "plan_fingerprint": plan["plan_fingerprint"], "files": hashes,
                    "completed_at": iso_now(), "integrity_note": "SHA256_CHECKSUMS_NOT_A_DIGITAL_SIGNATURE"}
        (temp / "manifest.json").write_bytes(json_bytes(manifest))
        verify_bundle(temp)
        os.rename(temp, target)  # One local same-filesystem publication, no partial successful run.
        temp = None
        verify_bundle(target)
        return target, False
    finally:
        if temp is not None:
            shutil.rmtree(temp, ignore_errors=True)
        lock.unlink(missing_ok=True)


def record_failure(root: Path, args: argparse.Namespace, error: IntakeError) -> Path:
    """Separate failure receipt. Never replace an existing successful queue."""
    directory = root / "failures"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:10] + ".json")
    failure = {"schema_version": SCHEMA, "status": "BLOCKED", "error_code": error.code,
               "message": error.message, "run_id": getattr(args, "run_id", None),
               "source_date": getattr(args, "source_date", None), "day": getattr(args, "day", None),
               "attempted_at": iso_now(), "counts": None, "candidate_queue_prepared": False,
               "execution_authorized": False, "order_admin_reads": 0, "source_writes": 0,
               "lookup_queue": [], "prior_successful_outputs_unchanged": True}
    with path.open("xb") as handle:
        handle.write(json_bytes(failure))
    return path


def demo_source() -> Source:
    values = [("91000001", "Jude"), ("91000002", "Other Rep"), ("91000001", " JUDE "),
              ("91000003", "jUdE"), ("91000004", "Jude"), ("91000004", "Other Rep"),
              (None, None), ("91000005", "Jude"), ("91000006", "Jude"),
              ("91000007", "\u00a0Jude\u00a0"), ("91000008", "Jude"), ("91000009", "Jude")]
    rows = tuple((BLANK if a is None else Cell("TEXT", a), BLANK if b is None else Cell("TEXT", b)) for a, b in values)
    return Source("SYNTHETIC", "wednesday", "2026-09-23", "2026-09-23T15:00:00+00:00",
                  len(rows) + 1, rows, {key: BLANK if val is None else Cell("TEXT", val) for key, val in ANCHORS.items()},
                  consistency="SYNTHETIC_FIXTURE_NOT_LIVE")


def demo_history() -> dict:
    records = []
    for number, state, followup, status in [
        ("91000003", "unfinished", None, "Unknown"),
        ("91000005", "completed", "2026-09-23T10:00:00-04:00", "Delayed"),
        ("91000006", "completed", None, "Shipped"),
        ("91000008", "completed", None, "Canceled"),
        ("91000009", "completed", None, "Excluded")]:
        records.append({"order_number": number, "observed_at": "2026-09-21T14:00:00-04:00",
                        "lookup_state": state, "followup_at": followup,
                        "last_known_status": status, "evidence_ref": "SYNTHETIC-EXAMPLE-NOT-A-REAL-ORDER"})
    return {"schema_version": HISTORY_SCHEMA, "records": records}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="command", required=True)
    auth = sub.add_parser("auth", help="Authorize Google Sheets read-only; stores a separate local token.")
    auth.add_argument("--client-secret", required=True, type=Path)
    auth.add_argument("--token", type=Path, default=default_home() / "oauth" / "token.json")
    for command in ("demo", "sheets"):
        q = sub.add_parser(command, help="Generate a synthetic example." if command == "demo" else "Prepare a candidate queue from the live manager sheet.")
        q.add_argument("--out", type=Path, default=default_home() / "runs")
        q.add_argument("--sort", choices=["source", "followups"], default="source")
        q.add_argument("--run-id", default="demo-wednesday" if command == "demo" else None, required=command == "sheets")
        q.add_argument("--history", type=Path)
        if command == "sheets":
            q.add_argument("--day", choices=list(TABS), required=True)
            q.add_argument("--source-date", required=True)
            q.add_argument("--token", type=Path, default=default_home() / "oauth" / "token.json")
    verify = sub.add_parser("verify", help="Verify a completed run's checksums; does not authorize execution.")
    verify.add_argument("folder", type=Path)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "auth":
            authorize(args.client_secret, args.token)
            print(json.dumps({"status": "AUTHORIZED", "scope": SCOPE, "token_saved_locally": True}))
            return 0
        if args.command == "verify":
            manifest = verify_bundle(args.folder)
            print(json.dumps({"status": "INTEGRITY_VERIFIED", "run_id": manifest["run_id"], "execution_authorized": False}))
            return 0
        if args.command == "demo":
            source = demo_source()
            history = read_history(args.history) if args.history else demo_history()
        else:
            validate_source_options(args.day, args.source_date, args.run_id)
            with google_session(args.token) as session:
                source = acquire_google(session, args.day, args.source_date)
            history = read_history(args.history)
        plan = make_plan(source, args.run_id, sort=args.sort, history=history)
        path, replay = save_bundle(plan, args.out)
        print(json.dumps({"status": plan["status"], "source_kind": source.kind,
                          "run_id": args.run_id, "output": str(path.resolve()), "exact_replay": replay,
                          "counts": plan["counts"], "execution_authorized": False,
                          "order_admin_reads": 0, "source_writes": 0}, indent=2))
        # 0 means intake finished, not that there are no holds or that OA may be read.
        return 0
    except IntakeError as exc:
        failure = {"status": "BLOCKED", "error_code": exc.code, "message": exc.message,
                   "candidate_queue_prepared": False, "execution_authorized": False}
        if hasattr(args, "out"):
            try:
                receipt = record_failure(args.out, args, exc)
                failure["failure_receipt"] = str(receipt.resolve())
            except OSError:
                failure["failure_receipt"] = "UNAVAILABLE_LOCAL_WRITE_FAILED"
        print(json.dumps(failure, indent=2), file=sys.stderr)
        return 4 if exc.code == "RUN_CONFLICT" else 2
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError) as exc:
        # Safe terminal error. Do not turn malformed external input into a partial queue.
        safe = IntakeError("LOCAL_OR_INPUT_FAILURE", "Local input/output failed. No new completed bundle is being claimed.")
        failure = {"status": "BLOCKED", "error_code": safe.code, "message": safe.message,
                   "execution_authorized": False, "candidate_queue_prepared": False}
        if hasattr(args, "out"):
            try:
                failure["failure_receipt"] = str(record_failure(args.out, args, safe).resolve())
            except OSError:
                pass
        print(json.dumps(failure, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
