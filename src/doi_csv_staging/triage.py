"""Evidence-bound human review candidates, never readiness or DOI evaluation."""

from __future__ import annotations

import re
from datetime import date
from zoneinfo import ZoneInfo
from synthetic_sales_assist.domain.timestamps import parse_timestamp, TimestampValidationError

from .staging import StagedOrder, _number, _time, ascii_four_trim, purchase_nature

SCHEMA = "doi-triage/v1"
PRIMARY_BUCKETS = (
    "INPUT_QUARANTINED",
    "FAILED_CAPTURE",
    "EVIDENCE_REVIEW",
    "STOCK_TRANSFER_REVIEW",
    "APPARENT_STOCK_PROGRESS_REVIEW",
    "LEAD_TIME_AVAILABILITY_RESEARCH",
    "NO_CANDIDATE",
)
TRIAGE_FLAGS = (
    "STOCK_TRANSFER_REVIEW",
    "APPARENT_STOCK_PROGRESS_REVIEW",
    "LEAD_TIME_AVAILABILITY_RESEARCH",
    "EVIDENCE_REVIEW",
)
REASON_CODES = frozenset(
    (
        'GLOBAL_INPUT_HOLD STRUCTURAL_INPUT_HOLD CAPTURE_FAILED CAPTURE_TIME_MISSING '
        'CAPTURE_TIME_FUTURE CAPTURE_STALE ETA_YEAR_ANOMALY ETA_BEFORE_CAPTURE '
        'ETA_DATE_CONFLICT ETA_DATE_INVALID PRODUCT_CURRENT_LABEL_CONTRAST '
        'WAREHOUSE_TRANSFER_CURRENT_STOCK NEGATIVE_OPAQUE_OS_CURRENT_STOCK '
        'APPARENT_CURRENT_STOCK OBSERVED_TERMINAL_PROGRESS_SUPPRESSED '
        'OBSERVED_LEAD_TIME_LABEL OBSERVED_RELATIVE_SHIP_LABEL OBSERVED_FUTURE_ETA '
        'KIT_COMPONENT_EVIDENCE_UNRESOLVED UNKNOWN_FACTS NO_POSITIVE_SIGNAL'
    ).split()
)
REASON_CODES = REASON_CODES | {"CAPTURE_INCOMPLETE_SOURCE"}
MISSING_FACT_CODES = frozenset(
    (
        'AT_ORDER_STOCK_NOT_CAPTURED ORDER_DATE_NOT_CAPTURED DS_NOT_CONFIRMED '
        'QUANTITY_NOT_CONFIRMED ALLOCATION_NOT_CAPTURED CURRENCY_NOT_CONFIRMED '
        'KIT_COMPONENT_EVIDENCE_UNRESOLVED CURRENT_STOCK_NOT_CAPTURED'
    ).split()
)
EVIDENCE_FIELDS = frozenset(
    {
        "order_status",
        "captured_at_america_new_york",
        "expected_arrival_date_exact",
        "current_expected_ship_date_exact",
        "revised_ship_date_exact",
        "stock_eta_exact",
        "product_eta_exact",
        "current_stock_icon_exact",
        "dated_line_eta",
        "OS_displayed",
        "drop_ship",
        "remaining_quantity",
        "component_coverage_complete",
    }
)
MAX_EVIDENCE_REFS = 6
_APPARENT = frozenset({"in stock", "instock", "ships today", "shipstoday"})
_DELAYED = frozenset(
    {
        "backordered",
        "back ordered",
        "back order",
        "special order no guaranteed eta",
        "special order - no guaranteed eta",
        "special order: no guaranteed eta",
        "specialorder: noguaranteedeta",
        "specialorder noguaranteedeta",
        "nla",
    }
)
_VENDOR = frozenset(
    {
        "vendor stock",
        "in stock at vendor",
        "in stock at supplier",
        "instockatvendor",
        "in stock (at vendor)",
        "instock(atvendor)",
    }
)
_STRUCTURAL = frozenset(
    (
        'STRUCTURAL_COVERAGE_INCOMPLETE LINE_STRUCTURE_CONFLICT LINE_STRUCTURE_UNRESOLVED '
        'MISSING_LINE_ID DUPLICATE_LINE_ID INVALID_COMPONENT_PARENT '
        'MISSING_COMPONENT_PARENT CONFLICTING_LINE DUPLICATE_SUMMARY CONFLICTING_SUMMARY '
        'SOURCE_JOIN_MISMATCH TIMESTAMP_MISMATCH TIMESTAMP_INVALID_OR_NAIVE '
        'TIMESTAMP_RANGE_UNSUPPORTED TIMEZONE_MISMATCH UTC_OFFSET_MISMATCH '
        'SUMMARY_LINE_COUNT_MISMATCH PAGINATION_COVERAGE_UNVERIFIED '
        'SOURCE_ASSIGNMENT_CONFLICT_OR_UNKNOWN REVIEW_ASSIGNMENT_UNVERIFIED'
    ).split()
)
_GLOBAL = frozenset(
    (
        'MISSING_HEADER DUPLICATE_HEADER MISSING_COLUMN UNEXPECTED_COLUMN MALFORMED_CSV '
        'MALFORMED_ROW_WIDTH INVALID_ORDER_ID CSV_INPUT_TYPE CSV_FORMULA_RISK '
        'GLOBAL_INPUT_HOLD'
    ).split()
)


class TriageError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _label(value: str) -> str:
    return ascii_four_trim(value).lower()


def _relative(value: str) -> bool:
    return (
        re.fullmatch(
            r"ships ?in ?[1-9][0-9]{0,2}(?:-[1-9][0-9]{0,2})? ?(?:business ?)?days?",
            _label(value),
            flags=re.ASCII,
        )
        is not None
    )


def _date(value: str) -> date | None:
    candidate = ascii_four_trim(value)
    if candidate.lower().startswith("ships on "):
        candidate = candidate[9:]
    candidate = re.sub(r" \([0-9]{1,6}\)$", "", candidate)
    try:
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", candidate):
            return date.fromisoformat(candidate)
        match = re.fullmatch(r"([0-9]{1,2})/([0-9]{1,2})/([0-9]{4})", candidate)
        if match:
            return date(int(match[3]), int(match[1]), int(match[2]))
        months = {
            name: n
            for n, name in enumerate(
                (
                    "jan",
                    "feb",
                    "mar",
                    "apr",
                    "may",
                    "jun",
                    "jul",
                    "aug",
                    "sep",
                    "oct",
                    "nov",
                    "dec",
                ),
                1,
            )
        }
        match = re.fullmatch(r"([0-9]{1,2})-([A-Za-z]{3})-([0-9]{4})", candidate)
        if match and match[2].lower() in months:
            return date(int(match[3]), months[match[2].lower()], int(match[1]))
        match = re.fullmatch(r"([A-Za-z]{3}) ([0-9]{1,2}), ([0-9]{4})", candidate)
        if match and match[1].lower() in months:
            return date(int(match[3]), months[match[1].lower()], int(match[2]))
    except ValueError:
        return None
    return None


def _utc(value: str) -> str:
    try:
        return parse_timestamp(ascii_four_trim(value)).to_json_value()
    except (TimestampValidationError, ValueError, OverflowError, TypeError):
        raise TriageError("TRIAGE_AS_OF_INVALID") from None


def validate_triage_context(as_of: str) -> dict[str, str]:
    return {"as_of": _utc(as_of)}


def _safe_value(field: str, value: str) -> str | None:
    candidate = ascii_four_trim(value)
    if not candidate or not candidate.isascii() or len(candidate) > 64:
        return None
    if field in {"OS_displayed", "remaining_quantity"}:
        return (
            candidate if re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", candidate, flags=re.ASCII) else None
        )
    if field == "captured_at_america_new_york":
        return candidate if _time(candidate) is not None else None
    if field == "drop_ship":
        return candidate if _label(candidate) in {"yes", "no", "true", "false"} else None
    if field == "component_coverage_complete":
        return (
            candidate
            if _label(candidate) in {"yes", "no", "true", "false", "complete", "verified"}
            else None
        )
    if field == "order_status":
        return (
            candidate
            if _label(candidate)
            in {
                "active",
                "batched",
                "warehouse transfer",
                "warehousetransfer",
                "shipped",
                "canceled",
                "cancelled",
            }
            else None
        )
    return (
        candidate
        if _label(candidate) in _APPARENT | _DELAYED | _VENDOR
        or _relative(candidate)
        or _date(candidate) is not None
        else None
    )


def classify_order(
    order: StagedOrder, *, as_of: str, global_input_held: bool = False
) -> dict[str, object]:
    canonical_as_of = _utc(as_of)
    exact_now = parse_timestamp(canonical_as_of)
    now = _time(as_of)
    if now is None:
        raise TriageError("TRIAGE_AS_OF_INVALID")
    try:
        now_date = now.astimezone(ZoneInfo("America/New_York")).date()
    except (ValueError, OverflowError):
        raise TriageError("TRIAGE_AS_OF_INVALID") from None
    reasons: set[str] = set()
    missing: set[str] = {
        "AT_ORDER_STOCK_NOT_CAPTURED",
        "ORDER_DATE_NOT_CAPTURED",
        "ALLOCATION_NOT_CAPTURED",
    }
    flags: set[str] = set()
    refs: list[dict[str, object]] = []
    ref_priorities: dict[tuple[str, int, str], int] = {}
    anomaly_ref_claimed = False

    def evidence(row: int, field: str, value: str, scope: str = "lines", priority: int = 4) -> None:
        nonlocal anomaly_ref_claimed
        if priority == 5 and not anomaly_ref_claimed:
            priority = 1
        if priority == 1:
            anomaly_ref_claimed = True
        safe = _safe_value(field, value)
        ref = {
            "scope": scope,
            "record_ordinal": row,
            "field": field,
            "observed_value": safe,
            "redacted": safe is None,
        }
        if ref not in refs:
            refs.append(ref)
        key = (scope, row, field)
        ref_priorities[key] = min(priority, ref_priorities.get(key, priority))

    summary = dict(order.summary_occurrences[0].raw_fields) if order.summary_occurrences else {}
    summary_row = order.summary_occurrences[0].row_number if order.summary_occurrences else 2
    held = set(order.holds)
    global_bad = global_input_held or bool(held & _GLOBAL)
    structural_bad = bool(held & _STRUCTURAL) or not order.visible_coverage_complete
    failed = (
        not order.summary_occurrences
        or not order.line_occurrences
        or "DISPLAYED_ORDER_ID_UNVERIFIED" in held
    )
    incomplete_capture = "ORDER_CAPTURE_INCOMPLETE" in held
    capture = _time(summary.get("captured_at_america_new_york", ""))
    capture_date: date | None = None
    anomaly = False
    capture_time = None
    snapshot_age_seconds = None
    snapshot_age_status = "UNVERIFIED"
    if capture is None:
        reasons.add("CAPTURE_TIME_MISSING")
        anomaly = True
    else:
        evidence(
            summary_row,
            "captured_at_america_new_york",
            summary["captured_at_america_new_york"],
            "summary",
            priority=0,
        )
        try:
            capture_date = capture.astimezone(ZoneInfo("America/New_York")).date()
            capture_time = _utc(summary["captured_at_america_new_york"])
            exact_capture = parse_timestamp(
                ascii_four_trim(summary["captured_at_america_new_york"])
            )
            age_nanoseconds = (
                (exact_now.epoch_seconds - exact_capture.epoch_seconds) * 1_000_000_000
                + exact_now.nanosecond
                - exact_capture.nanosecond
            )
            if age_nanoseconds < 0:
                reasons.add("CAPTURE_TIME_FUTURE")
                anomaly = True
                snapshot_age_status = "FUTURE_CAPTURE"
            else:
                snapshot_age_seconds = age_nanoseconds // 1_000_000_000
                snapshot_age_status = "KNOWN"
                if age_nanoseconds > 86400 * 1_000_000_000:
                    reasons.add("CAPTURE_STALE")
                    anomaly = True
                    snapshot_age_status = "STALE"
        except (ValueError, OverflowError):
            reasons.add("CAPTURE_TIME_MISSING")
            anomaly = True
    if not re.fullmatch(r"[A-Z]{3}", summary.get("currency_code", "")):
        missing.add("CURRENCY_NOT_CONFIRMED")
    terminal = _label(summary.get("order_status", "")) in {"shipped", "canceled", "cancelled"}
    if terminal:
        reasons.add("OBSERVED_TERMINAL_PROGRESS_SUPPRESSED")
        evidence(summary_row, "order_status", summary.get("order_status", ""), "summary")
    dated_values: list[tuple[int, str, str, date]] = []

    def inspect_date(row: int, field: str, raw: str, scope: str = "lines") -> date | None:
        nonlocal anomaly
        observed = _date(raw)
        if re.search(r"(?<![0-9])1999(?![0-9])", raw):
            first_year_anomaly = "ETA_YEAR_ANOMALY" not in reasons
            reasons.add("ETA_YEAR_ANOMALY")
            anomaly = True
            evidence(row, field, raw, scope, priority=1 if first_year_anomaly else 5)
        if observed is not None:
            dated_values.append((row, field, raw, observed))
            if observed.year == 1999:
                reasons.add("ETA_YEAR_ANOMALY")
                anomaly = True
            elif capture_date is not None and observed < capture_date:
                reasons.add("ETA_BEFORE_CAPTURE")
                anomaly = True
                evidence(row, field, raw, scope, priority=5)
            return observed
        if re.search(
            r"(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}/[0-9]{1,2}/[0-9]{4})", raw
        ) or _label(raw).startswith("ships on "):
            reasons.add("ETA_DATE_INVALID")
            anomaly = True
            evidence(row, field, raw, scope, priority=5)
        return None

    for field in (
        "expected_arrival_date_exact",
        "current_expected_ship_date_exact",
        "revised_ship_date_exact",
        "stock_eta_exact",
    ):
        inspect_date(summary_row, field, summary.get(field, ""), "summary")
    summary_ship = _date(summary.get("current_expected_ship_date_exact", ""))
    arrival = _date(summary.get("expected_arrival_date_exact", ""))
    if arrival is not None and summary_ship is not None and arrival < summary_ship:
        reasons.add("ETA_DATE_CONFLICT")
        anomaly = True
        evidence(
            summary_row,
            "expected_arrival_date_exact",
            summary.get("expected_arrival_date_exact", ""),
            "summary",
            priority=5,
        )
        evidence(
            summary_row,
            "current_expected_ship_date_exact",
            summary.get("current_expected_ship_date_exact", ""),
            "summary",
            priority=5,
        )
    line_data = [(row, dict(row.raw_fields)) for row in order.line_occurrences]
    eligible_lines = []
    for row, fields in line_data:
        purchase = _label(fields.get("counts_as_purchase", "")) in {"yes", "true"}
        physical_purchase = (
            purchase
            and purchase_nature(
                fields.get("row_type", ""),
                fields.get("physical_or_service", ""),
                fields.get("parent_line_id", ""),
            )
            == "physical"
        )
        remaining_zero = _number(fields.get("remaining_quantity", "")) == 0
        if physical_purchase and not remaining_zero:
            eligible_lines.append((row, fields, True))
        role = _label(fields.get("row_type", ""))
        parent = ascii_four_trim(fields.get("parent_line_id", ""))
        parent_known = any(
            _label(p.get("counts_as_purchase", "")) in {"yes", "true"}
            and ascii_four_trim(p.get("line_identifier", "")) == parent
            and purchase_nature(
                p.get("row_type", ""), p.get("physical_or_service", ""), p.get("parent_line_id", "")
            )
            == "physical"
            and _number(p.get("remaining_quantity", "")) != 0
            for _, p in line_data
        )
        component_eligible = (
            not purchase
            and role in {"component", "kit component", "kit_component"}
            and parent
            and parent_known
            and not remaining_zero
        )
        if component_eligible:
            eligible_lines.append((row, fields, False))
        # Components contribute evidence and anomalies but never a second purchase signal.
        role = _label(fields.get("row_type", ""))
        if (physical_purchase and not remaining_zero) or component_eligible:
            product_date = inspect_date(
                row.row_number, "product_eta_exact", fields.get("product_eta_exact", "")
            )
            line_date = inspect_date(
                row.row_number, "dated_line_eta", fields.get("dated_line_eta", "")
            )
            inspect_date(
                row.row_number,
                "current_stock_icon_exact",
                fields.get("current_stock_icon_exact", ""),
            )
            if product_date is not None and line_date is not None and product_date != line_date:
                reasons.add("ETA_DATE_CONFLICT")
                anomaly = True
                evidence(
                    row.row_number,
                    "product_eta_exact",
                    fields.get("product_eta_exact", ""),
                    priority=5,
                )
                evidence(
                    row.row_number, "dated_line_eta", fields.get("dated_line_eta", ""), priority=5
                )
    future_eta = False
    for row, fields, is_purchase in eligible_lines:
        current = fields.get("current_stock_icon_exact", "")
        product = fields.get("product_eta_exact", "")
        current_label, product_label = _label(current), _label(product)
        apparent = current_label in _APPARENT
        delayed = (
            product_label in _DELAYED
            or current_label in _DELAYED
            or _relative(product)
            or _relative(current)
        )
        line_dates = [_date(product), _date(fields.get("dated_line_eta", "")), _date(current)]
        for observed in line_dates:
            if (
                observed is not None
                and observed.year != 1999
                and observed > now_date
                and (capture_date is None or observed >= capture_date)
            ):
                future_eta = True
                delayed = True
        if _label(fields.get("drop_ship", "")) not in {
            "yes",
            "no",
            "true",
            "false",
        } or not ascii_four_trim(fields.get("drop_ship_evidence", "")):
            missing.add("DS_NOT_CONFIRMED")
        if (
            _number(
                fields.get(
                    "remaining_quantity" if is_purchase else "component_quantity_required", ""
                )
            )
            is None
        ):
            missing.add("QUANTITY_NOT_CONFIRMED")
        if not ascii_four_trim(current):
            missing.add("CURRENT_STOCK_NOT_CAPTURED")
        kit_unresolved = False
        if _label(fields.get("row_type", "")) in {
            "kit",
            "purchased kit",
            "purchased_kit",
            "purchased kit parent",
        }:
            native_id = ascii_four_trim(fields.get("line_identifier", ""))
            components = [
                (r, d)
                for r, d in line_data
                if ascii_four_trim(d.get("parent_line_id", "")) == native_id
            ]
            kit_unresolved = not components or any(
                _label(d.get("row_type", "")) not in {"component", "kit component", "kit_component"}
                or _label(d.get("component_coverage_complete", ""))
                not in {"yes", "true", "complete", "verified"}
                or _number(d.get("component_quantity_required", "")) is None
                or _label(d.get("current_stock_icon_exact", "")) not in _APPARENT
                for _, d in components
            )
            if kit_unresolved:
                missing.add("KIT_COMPONENT_EVIDENCE_UNRESOLVED")
                reasons.add("KIT_COMPONENT_EVIDENCE_UNRESOLVED")
        if global_bad or structural_bad or failed or terminal or incomplete_capture:
            continue
        os_raw = ascii_four_trim(fields.get("OS_displayed", ""))
        negative_os = (
            len(os_raw) <= 256
            and re.fullmatch(r"-[0-9]+(?:\.[0-9]+)?", os_raw, flags=re.ASCII) is not None
            and _number(os_raw[1:]) is not None
            and _number(os_raw[1:]) > 0
        )
        contrast = apparent and (
            product_label in _DELAYED | _VENDOR
            or _relative(product)
            or _date(product) is not None
            and _date(product) > now_date
        )
        transfer_status = _label(summary.get("order_status", "")) in {
            "warehouse transfer",
            "warehousetransfer",
        }
        if is_purchase and apparent and (contrast or transfer_status or negative_os):
            flags.add("STOCK_TRANSFER_REVIEW")
            if contrast:
                reasons.add("PRODUCT_CURRENT_LABEL_CONTRAST")
                evidence(row.row_number, "product_eta_exact", product, priority=2)
            if transfer_status:
                reasons.add("WAREHOUSE_TRANSFER_CURRENT_STOCK")
                evidence(
                    summary_row,
                    "order_status",
                    summary.get("order_status", ""),
                    "summary",
                    priority=2,
                )
            if negative_os:
                reasons.add("NEGATIVE_OPAQUE_OS_CURRENT_STOCK")
                evidence(row.row_number, "OS_displayed", fields.get("OS_displayed", ""), priority=2)
            evidence(row.row_number, "current_stock_icon_exact", current, priority=2)
        if is_purchase and apparent and not terminal and not kit_unresolved:
            flags.add("APPARENT_STOCK_PROGRESS_REVIEW")
            reasons.add("APPARENT_CURRENT_STOCK")
            evidence(row.row_number, "current_stock_icon_exact", current, priority=3)
        if delayed:
            flags.add("LEAD_TIME_AVAILABILITY_RESEARCH")
            if product_label in _DELAYED or current_label in _DELAYED:
                reasons.add("OBSERVED_LEAD_TIME_LABEL")
            if _relative(product) or _relative(current):
                reasons.add("OBSERVED_RELATIVE_SHIP_LABEL")
            if any(d is not None and d > now_date and d.year != 1999 for d in line_dates):
                reasons.add("OBSERVED_FUTURE_ETA")
            if product_label in _DELAYED or _relative(product) or _date(product) is not None:
                evidence(row.row_number, "product_eta_exact", product)
            if current_label in _DELAYED or _relative(current) or _date(current) is not None:
                evidence(row.row_number, "current_stock_icon_exact", current)
            if _date(fields.get("dated_line_eta", "")) is not None:
                evidence(row.row_number, "dated_line_eta", fields.get("dated_line_eta", ""))
    if missing or held or anomaly:
        flags.add("EVIDENCE_REVIEW")
        reasons.add("UNKNOWN_FACTS")
    if global_bad:
        bucket = "INPUT_QUARANTINED"
        reasons.add("GLOBAL_INPUT_HOLD")
        flags &= {"EVIDENCE_REVIEW"}
    elif failed:
        bucket = "FAILED_CAPTURE"
        reasons.add("CAPTURE_FAILED")
        flags.clear()
    elif structural_bad:
        bucket = "INPUT_QUARANTINED"
        reasons.add("STRUCTURAL_INPUT_HOLD")
        flags &= {"EVIDENCE_REVIEW"}
    elif incomplete_capture:
        bucket = "EVIDENCE_REVIEW"
        reasons.add("CAPTURE_INCOMPLETE_SOURCE")
        flags &= {"EVIDENCE_REVIEW"}
    else:
        bucket = next(
            (
                b
                for b in (
                    "STOCK_TRANSFER_REVIEW",
                    "APPARENT_STOCK_PROGRESS_REVIEW",
                    "LEAD_TIME_AVAILABILITY_RESEARCH",
                    "EVIDENCE_REVIEW",
                )
                if b in flags
            ),
            "NO_CANDIDATE",
        )
    if bucket == "NO_CANDIDATE":
        reasons.add("NO_POSITIVE_SIGNAL")
    priority = (
        0
        if global_bad
        else (
            7
            if bucket == "FAILED_CAPTURE"
            else (
                1
                if anomaly
                or structural_bad
                or incomplete_capture
                or "KIT_COMPONENT_EVIDENCE_UNRESOLVED" in reasons
                else {
                    "STOCK_TRANSFER_REVIEW": 2,
                    "APPARENT_STOCK_PROGRESS_REVIEW": 3,
                    "LEAD_TIME_AVAILABILITY_RESEARCH": 4,
                    "EVIDENCE_REVIEW": 5,
                    "NO_CANDIDATE": 6,
                }[bucket]
            )
        )
    )
    refs.sort(key=lambda r: ref_priorities[(r["scope"], r["record_ordinal"], r["field"])])
    result = {
        "schema": SCHEMA,
        "primary_bucket": bucket,
        "flags": sorted(flags),
        "reason_codes": sorted(reasons)[:12],
        "missing_fact_codes": sorted(missing)[:8],
        "evidence_references": refs[:MAX_EVIDENCE_REFS],
        "evidence_omitted_count": max(0, len(refs) - MAX_EVIDENCE_REFS),
        "attention_priority": priority,
        "usable_eta": future_eta
        and not anomaly
        and not global_bad
        and not structural_bad
        and not failed
        and not terminal
        and not incomplete_capture
        and "KIT_COMPONENT_EVIDENCE_UNRESOLVED" not in reasons,
        "capture_time": capture_time,
        "snapshot_age_seconds": snapshot_age_seconds,
        "snapshot_age_status": snapshot_age_status,
        "decision_eligible": False,
        "readiness_verified": False,
    }
    validate_triage_projection(result)
    return result


def validate_triage_projection(value: object) -> dict[str, object]:
    keys = {
        "schema",
        "primary_bucket",
        "flags",
        "reason_codes",
        "missing_fact_codes",
        "evidence_references",
        "evidence_omitted_count",
        "attention_priority",
        "usable_eta",
        "decision_eligible",
        "readiness_verified",
        "capture_time",
        "snapshot_age_seconds",
        "snapshot_age_status",
    }
    if (
        type(value) is not dict
        or set(value) != keys
        or value["schema"] != SCHEMA
        or value["primary_bucket"] not in PRIMARY_BUCKETS
    ):
        raise TriageError("TRIAGE_PROJECTION_INVALID")
    for field, allowed, limit in (
        ("flags", TRIAGE_FLAGS, 4),
        ("reason_codes", REASON_CODES, 12),
        ("missing_fact_codes", MISSING_FACT_CODES, 8),
    ):
        items = value[field]
        if (
            type(items) is not list
            or len(items) > limit
            or any(type(x) is not str or x not in allowed for x in items)
        ):
            raise TriageError("TRIAGE_PROJECTION_INVALID")
    if (
        type(value["attention_priority"]) is not int
        or not 0 <= value["attention_priority"] <= 7
        or type(value["evidence_omitted_count"]) is not int
        or value["evidence_omitted_count"] < 0
        or type(value["usable_eta"]) is not bool
        or value["decision_eligible"] is not False
        or value["readiness_verified"] is not False
    ):
        raise TriageError("TRIAGE_PROJECTION_INVALID")
    refs = value["evidence_references"]
    if (
        value["snapshot_age_status"] not in {"KNOWN", "STALE", "FUTURE_CAPTURE", "UNVERIFIED"}
        or (
            value["snapshot_age_seconds"] is not None
            and (
                type(value["snapshot_age_seconds"]) is not int or value["snapshot_age_seconds"] < 0
            )
        )
        or (
            value["capture_time"] is not None
            and (
                type(value["capture_time"]) is not str
                or _utc(value["capture_time"]) != value["capture_time"]
            )
        )
    ):
        raise TriageError("TRIAGE_PROJECTION_INVALID")
    if type(refs) is not list or len(refs) > MAX_EVIDENCE_REFS:
        raise TriageError("TRIAGE_PROJECTION_INVALID")
    for ref in refs:
        if (
            type(ref) is not dict
            or set(ref) != {"scope", "record_ordinal", "field", "observed_value", "redacted"}
            or ref["scope"] not in {"summary", "lines"}
            or type(ref["record_ordinal"]) is not int
            or not 2 <= ref["record_ordinal"] <= 5001
            or ref["field"] not in EVIDENCE_FIELDS
            or type(ref["redacted"]) is not bool
        ):
            raise TriageError("TRIAGE_PROJECTION_INVALID")
        raw = ref["observed_value"]
        if raw is None:
            if ref["redacted"] is not True:
                raise TriageError("TRIAGE_PROJECTION_INVALID")
        elif type(raw) is not str or ref["redacted"] or _safe_value(ref["field"], raw) != raw:
            raise TriageError("TRIAGE_PROJECTION_INVALID")
    bucket, flags, reasons = (
        value["primary_bucket"],
        set(value["flags"]),
        set(value["reason_codes"]),
    )
    if (
        len(flags) != len(value["flags"])
        or len(reasons) != len(value["reason_codes"])
        or len(set(value["missing_fact_codes"])) != len(value["missing_fact_codes"])
        or len({(r["scope"], r["record_ordinal"], r["field"]) for r in refs}) != len(refs)
    ):
        raise TriageError("TRIAGE_PROJECTION_INVALID")
    if "OBSERVED_TERMINAL_PROGRESS_SUPPRESSED" in reasons and flags - {"EVIDENCE_REVIEW"}:
        raise TriageError("TRIAGE_PROJECTION_INVALID")
    anomaly_codes = {
        "CAPTURE_TIME_MISSING",
        "CAPTURE_TIME_FUTURE",
        "CAPTURE_STALE",
        "ETA_YEAR_ANOMALY",
        "ETA_BEFORE_CAPTURE",
        "ETA_DATE_CONFLICT",
        "ETA_DATE_INVALID",
        "KIT_COMPONENT_EVIDENCE_UNRESOLVED",
        "CAPTURE_INCOMPLETE_SOURCE",
    }
    if bucket == "INPUT_QUARANTINED":
        if (
            flags - {"EVIDENCE_REVIEW"}
            or not reasons & {"GLOBAL_INPUT_HOLD", "STRUCTURAL_INPUT_HOLD"}
            or value["usable_eta"]
        ):
            raise TriageError("TRIAGE_PROJECTION_INVALID")
        expected_priority = 0 if "GLOBAL_INPUT_HOLD" in reasons else 1
    elif bucket == "FAILED_CAPTURE":
        if flags or "CAPTURE_FAILED" not in reasons or value["usable_eta"]:
            raise TriageError("TRIAGE_PROJECTION_INVALID")
        expected_priority = 7
    else:
        expected_bucket = next((b for b in TRIAGE_FLAGS if b in flags), "NO_CANDIDATE")
        if bucket != expected_bucket:
            raise TriageError("TRIAGE_PROJECTION_INVALID")
        expected_priority = (
            1
            if reasons & anomaly_codes
            else {
                "STOCK_TRANSFER_REVIEW": 2,
                "APPARENT_STOCK_PROGRESS_REVIEW": 3,
                "LEAD_TIME_AVAILABILITY_RESEARCH": 4,
                "EVIDENCE_REVIEW": 5,
                "NO_CANDIDATE": 6,
            }[bucket]
        )
    if (
        value["attention_priority"] != expected_priority
        or value["usable_eta"]
        and (reasons & anomaly_codes or "OBSERVED_FUTURE_ETA" not in reasons)
    ):
        raise TriageError("TRIAGE_PROJECTION_INVALID")
    age_status, age, capture = (
        value["snapshot_age_status"],
        value["snapshot_age_seconds"],
        value["capture_time"],
    )
    if value["usable_eta"] and age_status != "KNOWN":
        raise TriageError("TRIAGE_PROJECTION_INVALID")
    for status, reason in (
        ("STALE", "CAPTURE_STALE"),
        ("FUTURE_CAPTURE", "CAPTURE_TIME_FUTURE"),
        ("UNVERIFIED", "CAPTURE_TIME_MISSING"),
    ):
        if age_status == status and reason not in reasons:
            raise TriageError("TRIAGE_PROJECTION_INVALID")
    if age_status in {"KNOWN", "STALE"}:
        if (
            age is None
            or capture is None
            or age_status == "KNOWN"
            and age > 86400
            or age_status == "STALE"
            and age < 86400
        ):
            raise TriageError("TRIAGE_PROJECTION_INVALID")
    elif (
        age is not None
        or age_status == "FUTURE_CAPTURE"
        and capture is None
        or age_status == "UNVERIFIED"
        and capture is not None
    ):
        raise TriageError("TRIAGE_PROJECTION_INVALID")
    return value


def aggregate_triage(
    orders: list[StagedOrder], *, as_of: str, global_input_held: bool = False
) -> dict[str, object]:
    results = [
        classify_order(order, as_of=as_of, global_input_held=global_input_held) for order in orders
    ]
    return {
        "schema": SCHEMA,
        "as_of": _utc(as_of),
        "order_count": len(results),
        "bucket_counts": {
            bucket: sum(r["primary_bucket"] == bucket for r in results)
            for bucket in PRIMARY_BUCKETS
        },
        "flag_counts": {
            flag: sum(flag in r["flags"] for r in results) for flag in sorted(TRIAGE_FLAGS)
        },
        "decision_eligible_count": 0,
    }
