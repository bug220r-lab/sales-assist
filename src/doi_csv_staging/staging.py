"""Closed-schema, immutable CSV staging. Inputs are CSV text, never paths.

Raw records are private evidence. The minimal projection is not a CSV export and
does not include customer contact fields, product names, notes or source URLs.
No result authorizes fulfillment or performs DOI business classification.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from synthetic_sales_assist.domain.normalization import (
    NormalizationError, ascii_four_trim, normalize_order_number,
)

SUMMARY_HEADERS = tuple("order_id displayed_order_id order_id_matches_queue doi_review_assignment doi_source_assignment_conflict queue_position queue_sheet queue_sheet_row queue_range original_source_rows source_occurrences order_status displayed_sales_credit_field displayed_sales_credit_value sales_credit_entitlement order_total_displayed order_total_numeric currency_symbol_displayed currency_code customer_info_email customer_email_checked_at_america_new_york captured_at_america_new_york timezone utc_offset stock_eta_exact revised_ship_date_exact current_expected_ship_date_exact expected_arrival_date_exact days_in_transit_exact arrival_missing_reason inventory_percent_on_shelf_exact active_purchased_rows separate_service_rows_displayed visible_component_rows pagination_controls_displayed purchased_line_coverage_complete component_coverage capture_complete missing_evidence_reason snapshot_consistency_verified snapshot_change_note pure_drop_ship_eligibility order_admin_url queue_source_url earlier_observation_state".split())
LINE_HEADERS = tuple("order_id row_type counts_as_purchase parent_line_id line_identifier line_identifier_basis es_number sku product_name physical_or_service ordered_quantity_displayed fulfilled_quantity remaining_quantity component_quantity_per_parent component_quantity_required product_eta_exact current_stock_icon_exact OH_displayed OS_displayed PO_displayed PC_displayed WC_displayed stock_quantity_applicability dated_line_eta eta_qualification drop_ship drop_ship_evidence each_price_displayed purchased_line_total_displayed line_coverage_complete component_coverage_complete order_capture_complete missing_evidence_reason captured_at_america_new_york order_admin_url queue_source_url queue_position queue_sheet_row original_source_rows".split())
SERVICE_NATURES = frozenset({"service", "service line", "explicit service/charge line"})
PHYSICAL_NATURES = frozenset({"physical", "physical merchandise"})
SERVICE_PURCHASE_ROLES = frozenset({"service", "purchased service/charge line"})
PHYSICAL_PURCHASE_ROLES = frozenset({"purchased merchandise line", "purchased kit parent", "kit", "purchased_kit", "purchased kit", "packaged_product", "packaged product"})
GENERIC_PURCHASE_ROLES = frozenset({"purchased", "purchase", "purchased_line", "purchased line"})
PURCHASE_ROLES = GENERIC_PURCHASE_ROLES | SERVICE_PURCHASE_ROLES | PHYSICAL_PURCHASE_ROLES


def purchase_nature(role: str, nature: str, parent_line_id: str = "") -> str | None:
    """Interpret controlled row metadata only; never product names or stock."""
    role, nature = ascii_four_trim(role).lower(), ascii_four_trim(nature).lower()
    if role not in PURCHASE_ROLES or ascii_four_trim(parent_line_id):
        return None
    if (role in SERVICE_PURCHASE_ROLES and nature in PHYSICAL_NATURES) or (role in PHYSICAL_PURCHASE_ROLES and nature in SERVICE_NATURES):
        return None
    if nature in SERVICE_NATURES:
        return "service"
    if nature in PHYSICAL_NATURES:
        return "physical"
    return None


@dataclass(frozen=True, slots=True, repr=False)
class StagingIssue:
    code: str
    scope: str
    row_number: int | None = None
    order_key: str | None = None


@dataclass(frozen=True, slots=True, repr=False)
class Observation:
    field: str
    state: str
    value: str | None
    reason: str | None = None


@dataclass(frozen=True, slots=True, repr=False)
class RawOccurrence:
    row_number: int
    physical_line_start: int
    physical_line_end: int
    raw_fields: tuple[tuple[str, str], ...]
    raw_cells: tuple[str, ...]
    raw_order_id: str
    canonical_order_id: str | None


@dataclass(frozen=True, slots=True, repr=False)
class StagedOrder:
    canonical_order_id: str
    summary_occurrences: tuple[RawOccurrence, ...]
    line_occurrences: tuple[RawOccurrence, ...]
    issues: tuple[StagingIssue, ...]
    visible_coverage_complete: bool
    evidence_complete: bool
    decision_eligible: bool
    holds: tuple[str, ...]
    review_projection: tuple[tuple[str, str | int | bool | None], ...]
    tags: tuple[Observation, ...]


@dataclass(frozen=True, slots=True, repr=False)
class StagingBatch:
    summary_occurrences: tuple[RawOccurrence, ...]
    line_occurrences: tuple[RawOccurrence, ...]
    issues: tuple[StagingIssue, ...]
    orders: tuple[StagedOrder, ...]
    raw_summary_csv: str
    raw_lines_csv: str


def _issue(code: str, scope: str, row: RawOccurrence | None = None) -> StagingIssue:
    return StagingIssue(code, scope, row.row_number if row else None,
                        row.canonical_order_id if row else None)


def _fields(row: RawOccurrence) -> dict[str, str]:
    return dict(row.raw_fields)


def _trim(value: str) -> str:
    return ascii_four_trim(value)


def _yes(value: str) -> bool:
    return _trim(value).lower() in {"yes", "true", "complete", "verified", "complete verified"}


def _no(value: str) -> bool:
    return _trim(value).lower() in {"no", "false"}


def _bool_yes(value: str) -> bool:
    return _trim(value).lower() in {"yes", "true"}


def _number(value: str) -> Decimal | None:
    candidate = _trim(value)
    if len(candidate) > 256 or re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", candidate) is None:
        return None
    try:
        number = Decimal(candidate)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _count(value: str) -> int | None:
    candidate = _trim(value)
    return int(candidate) if len(candidate) <= 18 and re.fullmatch(r"[0-9]+", candidate) else None


def _time(value: str) -> datetime | None:
    candidate = _trim(value)
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?(?:Z|[+-][0-9]{2}:[0-9]{2})", candidate) is None:
        return None
    offset_match = re.search(r"([+-])([0-9]{2}):([0-9]{2})$", candidate)
    if offset_match and (int(offset_match.group(2)) > 23 or int(offset_match.group(3)) > 59 or offset_match.group(0) == "-00:00"):
        return None
    try:
        result = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        return result if result.tzinfo is not None and result.utcoffset() is not None else None
    except (ValueError, TypeError):
        return None


def _same_time(left: str, right: str) -> bool:
    """Compare instants without dropping supported nanosecond precision."""
    ltime, rtime = _time(left), _time(right)
    def fraction(value: str) -> str:
        match = re.search(r"\.([0-9]{1,9})(?:Z|[+-][0-9]{2}:[0-9]{2})$", _trim(value))
        return (match.group(1) if match else "").ljust(9, "0")
    return ltime is not None and rtime is not None and ltime == rtime and fraction(left) == fraction(right)


def _parse(text: str, headers: tuple[str, ...], scope: str) -> tuple[tuple[RawOccurrence, ...], list[StagingIssue]]:
    issues: list[StagingIssue] = []
    rows: list[RawOccurrence] = []
    if type(text) is not str:
        return (), [StagingIssue("CSV_INPUT_TYPE", scope)]
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        raw_headers = next(reader)
    except StopIteration:
        return (), [StagingIssue("MISSING_HEADER", scope)]
    except csv.Error:
        return (), [StagingIssue("MALFORMED_CSV", scope)]
    names = tuple(_trim(value.lstrip("\ufeff") if i == 0 else value)
                  for i, value in enumerate(raw_headers))
    if len(set(names)) != len(names):
        issues.append(StagingIssue("DUPLICATE_HEADER", scope))
    if any(name not in names for name in headers):
        issues.append(StagingIssue("MISSING_COLUMN", scope))
    if any(name not in headers for name in names):
        issues.append(StagingIssue("UNEXPECTED_COLUMN", scope))
    previous_line = reader.line_num
    logical_row = 1
    try:
        for cells in reader:
            logical_row += 1
            start, end = previous_line + 1, reader.line_num
            previous_line = end
            # Preserve physical and logical occurrence positions, even for blank records.
            pairs = tuple((name, cells[i] if i < len(cells) else "")
                          for i, name in enumerate(names))
            raw_id = ""
            if names.count("order_id") == 1:
                position = names.index("order_id")
                raw_id = cells[position] if position < len(cells) else ""
            try:
                canonical = normalize_order_number(raw_id)
            except NormalizationError:
                canonical = None
            row = RawOccurrence(logical_row, start, end, pairs, tuple(cells), raw_id, canonical)
            rows.append(row)
            if len(cells) != len(names):
                issues.append(_issue("MALFORMED_ROW_WIDTH", scope, row))
            if canonical is None:
                issues.append(_issue("INVALID_ORDER_ID", scope, row))
            def formula_risk(index: int, cell: str) -> bool:
                candidate = _trim(cell)
                header = names[index] if index < len(names) else ""
                if header == "utc_offset" and re.fullmatch(r"[+-](?:0[0-9]|1[0-9]|2[0-3]):[0-5][0-9]", candidate) and candidate != "-00:00":
                    return False
                if header == "OS_displayed" and len(candidate) <= 256 and re.fullmatch(r"-[0-9]+(?:\.[0-9]+)?", candidate, flags=re.ASCII):
                    return False
                return candidate.startswith(("=", "+", "-", "@"))
            if any(formula_risk(i, cell) for i, cell in enumerate(cells)):
                issues.append(_issue("CSV_FORMULA_RISK", scope, row))
    except csv.Error:
        issues.append(StagingIssue("MALFORMED_CSV", scope, logical_row + 1))
    return tuple(rows), issues


def _observation(field: str, value: str, *, numeric: bool = False,
                 explicit_yes_no: bool = False) -> Observation:
    known = bool(_trim(value))
    if numeric:
        known = _number(value) is not None
    if explicit_yes_no:
        known = _bool_yes(value) or _no(value)
    return Observation(field, "OBSERVED" if known else "UNKNOWN",
                       value if known else None, None if known else "NOT_EXPLICITLY_EVIDENCED")


def stage_capture_csvs(summary_csv: str, lines_csv: str) -> StagingBatch:
    """Stage CSV text privately. Every order remains in review, never actionable."""
    summaries, issues = _parse(summary_csv, SUMMARY_HEADERS, "summary")
    lines, line_issues = _parse(lines_csv, LINE_HEADERS, "lines")
    issues.extend(line_issues)
    summary_groups: dict[str, list[RawOccurrence]] = {}
    line_groups: dict[str, list[RawOccurrence]] = {}
    for row in summaries:
        if row.canonical_order_id is not None:
            summary_groups.setdefault(row.canonical_order_id, []).append(row)
    for row in lines:
        if row.canonical_order_id is not None:
            line_groups.setdefault(row.canonical_order_id, []).append(row)
    for key in line_groups.keys() - summary_groups.keys():
        for row in line_groups[key]:
            issues.append(_issue("ORPHAN_LINE", "lines", row))
    orders: list[StagedOrder] = []
    # Preserve first summary occurrence order, followed by orphan order occurrence order.
    keys = dict.fromkeys((*summary_groups, *line_groups))
    for key in keys:
        sr = tuple(summary_groups.get(key, ()))
        lr = tuple(line_groups.get(key, ()))
        local: list[StagingIssue] = []
        s = _fields(sr[0]) if sr else {}
        if not sr:
            local.append(StagingIssue("MISSING_SUMMARY", "order", order_key=key))
        if len(sr) > 1:
            local.append(_issue("DUPLICATE_SUMMARY", "summary", sr[1]))
            if any(row.raw_fields != sr[0].raw_fields for row in sr[1:]):
                local.append(_issue("CONFLICTING_SUMMARY", "summary", sr[1]))
        if not lr:
            local.append(StagingIssue("MISSING_LINES", "order", order_key=key))
        if _trim(s.get("doi_review_assignment", "")).lower() != "jude":
            local.append(StagingIssue("REVIEW_ASSIGNMENT_UNVERIFIED", "order", order_key=key))
        if not _no(s.get("doi_source_assignment_conflict", "")):
            local.append(StagingIssue("SOURCE_ASSIGNMENT_CONFLICT_OR_UNKNOWN", "order", order_key=key))
        try:
            displayed = normalize_order_number(s.get("displayed_order_id", ""))
        except NormalizationError:
            displayed = None
        if displayed != key or not _yes(s.get("order_id_matches_queue", "")):
            local.append(StagingIssue("DISPLAYED_ORDER_ID_UNVERIFIED", "order", order_key=key))
        capture = _time(s.get("captured_at_america_new_york", ""))
        if capture is None:
            local.append(StagingIssue("TIMESTAMP_INVALID_OR_NAIVE", "order", order_key=key))
        else:
            try:
                if s.get("timezone") != "America/New_York" or capture.utcoffset() != capture.astimezone(ZoneInfo("America/New_York")).utcoffset():
                    local.append(StagingIssue("TIMEZONE_MISMATCH", "order", order_key=key))
                offset = capture.strftime("%z")
                if _trim(s.get("utc_offset", "")) != offset[:3] + ":" + offset[3:]:
                    local.append(StagingIssue("UTC_OFFSET_MISMATCH", "order", order_key=key))
            except (OverflowError, ValueError):
                local.append(StagingIssue("TIMESTAMP_RANGE_UNSUPPORTED", "order", order_key=key))
        seen_ids: dict[str, RawOccurrence] = {}
        all_purchased = physical_purchased = components = services = 0
        coverage = bool(sr) and bool(lr)
        line_tags: list[Observation] = []
        for row in lr:
            d = _fields(row)
            purchase = _bool_yes(d.get("counts_as_purchase", ""))
            nonpurchase = _no(d.get("counts_as_purchase", ""))
            role = _trim(d.get("row_type", "")).lower()
            parent = _trim(d.get("parent_line_id", ""))
            native_id = _trim(d.get("line_identifier", ""))
            gap_roles = {"coverage_gap", "coverage-gap", "coverage gap", "placeholder", "component coverage gap - not a merchandise line"}
            placeholder = nonpurchase and role in gap_roles
            component = nonpurchase and role in {"component", "kit_component", "kit component"}
            if purchase and (role in {"component", "kit_component", "kit component"} | gap_roles or parent):
                local.append(_issue("LINE_STRUCTURE_CONFLICT", "lines", row))
                coverage = False
            if purchase and role not in PURCHASE_ROLES:
                local.append(_issue("LINE_STRUCTURE_UNRESOLVED", "lines", row))
                coverage = False
            if role in {"packaged_product", "packaged product"}:
                local.append(_issue("PACKAGED_PRODUCT_STRUCTURE_UNRESOLVED", "lines", row))
            if purchase:
                all_purchased += 1
                nature = _trim(d.get("physical_or_service", "")).lower()
                contradictory = (role in SERVICE_PURCHASE_ROLES and nature in PHYSICAL_NATURES) or (role in PHYSICAL_PURCHASE_ROLES and nature in SERVICE_NATURES)
                if contradictory:
                    local.append(_issue("LINE_STRUCTURE_CONFLICT", "lines", row))
                    coverage = False
                elif nature not in SERVICE_NATURES | PHYSICAL_NATURES:
                    local.append(_issue("LINE_NATURE_UNKNOWN", "lines", row))
                    coverage = False
                subset = purchase_nature(role, nature, parent)
                if subset == "service":
                    services += 1
                elif subset == "physical":
                    physical_purchased += 1
            elif component:
                components += 1
            elif not placeholder:
                local.append(_issue("LINE_STRUCTURE_UNRESOLVED", "lines", row))
            if not native_id and not (placeholder and parent):
                local.append(_issue("MISSING_LINE_ID", "lines", row))
            if native_id:
                if native_id in seen_ids:
                    local.append(_issue("DUPLICATE_LINE_ID", "lines", row))
                    if d != _fields(seen_ids[native_id]):
                        local.append(_issue("CONFLICTING_LINE", "lines", row))
                else:
                    seen_ids[native_id] = row
            if placeholder:
                local.append(_issue("VISIBLE_COVERAGE_GAP", "lines", row))
            if (component or placeholder) and not parent:
                local.append(_issue("MISSING_COMPONENT_PARENT", "lines", row))
            observed = _time(d.get("captured_at_america_new_york", ""))
            if observed is None:
                local.append(_issue("TIMESTAMP_INVALID_OR_NAIVE", "lines", row))
            elif capture is None or not _same_time(d.get("captured_at_america_new_york", ""), s.get("captured_at_america_new_york", "")):
                local.append(_issue("TIMESTAMP_MISMATCH", "lines", row))
            for source_field in ("order_admin_url", "queue_source_url", "queue_position", "queue_sheet_row", "original_source_rows"):
                if not _trim(d.get(source_field, "")) or _trim(d.get(source_field, "")) != _trim(s.get(source_field, "")):
                    local.append(_issue("SOURCE_JOIN_MISMATCH", "lines", row))
            if purchase and not _yes(d.get("line_coverage_complete", "")):
                coverage = False
            if not _yes(d.get("order_capture_complete", "")):
                local.append(_issue("ORDER_CAPTURE_INCOMPLETE", "lines", row))
            if component and not _yes(d.get("component_coverage_complete", "")):
                local.append(_issue("COMPONENT_COVERAGE_INCOMPLETE", "lines", row))
            if d.get("missing_evidence_reason", "").strip():
                local.append(_issue("LINE_EVIDENCE_GAP", "lines", row))
            for field in ("ordered_quantity_displayed", "fulfilled_quantity", "remaining_quantity", "component_quantity_per_parent", "component_quantity_required"):
                line_tags.append(_observation("line:" + str(row.row_number) + ":" + field, d.get(field, ""), numeric=True))
                raw_numeric = _trim(d.get(field, ""))
                unknown_numeric = raw_numeric.lower() in {"unknown", "n/a", "not applicable", "not displayed", "unavailable"} or raw_numeric.lower().startswith("unknown - ")
                if raw_numeric and _number(raw_numeric) is None and not unknown_numeric:
                    local.append(_issue("INVALID_QUANTITY", "lines", row))
                if purchase and field in {"ordered_quantity_displayed", "fulfilled_quantity", "remaining_quantity"} and _number(raw_numeric) is None:
                    local.append(_issue("REQUIRED_QUANTITY_UNKNOWN", "lines", row))
            line_tags.append(_observation("line:" + str(row.row_number) + ":drop_ship", d.get("drop_ship", ""), explicit_yes_no=True))
            if purchase and (not (_bool_yes(d.get("drop_ship", "")) or _no(d.get("drop_ship", ""))) or not _trim(d.get("drop_ship_evidence", ""))):
                local.append(_issue("DS_EVIDENCE_UNKNOWN", "lines", row))
            # Raw icon/warehouse columns never prove full readiness or available quantity.
            line_tags.append(Observation("line:" + str(row.row_number) + ":readiness", "UNKNOWN", None, "NO_VERIFIED_READINESS_MAPPING"))
        for row in lr:
            d = _fields(row)
            parent = _trim(d.get("parent_line_id", ""))
            if parent and (parent not in seen_ids or not _bool_yes(_fields(seen_ids[parent]).get("counts_as_purchase", ""))):
                local.append(_issue("INVALID_COMPONENT_PARENT", "lines", row))
        structural_codes = {
            "DUPLICATE_SUMMARY", "CONFLICTING_SUMMARY", "LINE_STRUCTURE_CONFLICT",
            "LINE_STRUCTURE_UNRESOLVED", "PACKAGED_PRODUCT_STRUCTURE_UNRESOLVED",
            "LINE_NATURE_UNKNOWN", "MISSING_LINE_ID", "DUPLICATE_LINE_ID",
            "CONFLICTING_LINE", "MISSING_COMPONENT_PARENT", "INVALID_COMPONENT_PARENT",
        }
        global_structural_codes = {
            "MISSING_HEADER", "DUPLICATE_HEADER", "MISSING_COLUMN", "UNEXPECTED_COLUMN",
            "MALFORMED_CSV", "MALFORMED_ROW_WIDTH", "INVALID_ORDER_ID", "CSV_INPUT_TYPE",
        }
        # A valid nonpurchase gap placeholder preserves purchased-row visibility;
        # structural ambiguity elsewhere cannot be repaired by matching counts.
        if any(i.code in structural_codes for i in local) or any(i.code in global_structural_codes for i in issues):
            coverage = False
            local.append(StagingIssue("STRUCTURAL_COVERAGE_INCOMPLETE", "order", order_key=key))
        for field, actual in (("active_purchased_rows", all_purchased), ("separate_service_rows_displayed", services), ("visible_component_rows", components)):
            expected = _count(s.get(field, ""))
            if expected is None or expected != actual:
                coverage = False
                local.append(StagingIssue("SUMMARY_LINE_COUNT_MISMATCH", "order", order_key=key))
        if not _yes(s.get("purchased_line_coverage_complete", "")):
            coverage = False
        if _trim(s.get("pagination_controls_displayed", "")).lower() not in {"0", "no", "none", "not displayed", "none displayed", "false"}:
            coverage = False
            local.append(StagingIssue("PAGINATION_COVERAGE_UNVERIFIED", "order", order_key=key))
        if not _yes(s.get("capture_complete", "")):
            local.append(StagingIssue("ORDER_CAPTURE_INCOMPLETE", "order", order_key=key))
        if components and not _yes(s.get("component_coverage", "")):
            local.append(StagingIssue("COMPONENT_COVERAGE_INCOMPLETE", "order", order_key=key))
        evidence_flags = (_yes(s.get("snapshot_consistency_verified", ""))
                          and not _trim(s.get("missing_evidence_reason", "")))
        if not evidence_flags:
            local.append(StagingIssue("SNAPSHOT_EVIDENCE_INCOMPLETE", "order", order_key=key))
        tags = [Observation("currency", "OBSERVED" if re.fullmatch(r"[A-Z]{3}", s.get("currency_code", "")) else "UNKNOWN", s.get("currency_code") if re.fullmatch(r"[A-Z]{3}", s.get("currency_code", "")) else None, None if re.fullmatch(r"[A-Z]{3}", s.get("currency_code", "")) else "CURRENCY_NOT_CONFIRMED"), Observation("readiness", "UNKNOWN", None, "NO_PRODUCTION_EVALUATION"), *line_tags]
        if tags[0].state == "UNKNOWN":
            local.append(StagingIssue("CURRENCY_UNKNOWN", "order", order_key=key))
        local.append(StagingIssue("READINESS_UNVERIFIED", "order", order_key=key))
        # Global unsafe parsing/formulas hold all orders, not merely one row.
        global_block = any(i.code in {"MISSING_HEADER", "DUPLICATE_HEADER", "MISSING_COLUMN", "UNEXPECTED_COLUMN", "MALFORMED_CSV", "MALFORMED_ROW_WIDTH", "CSV_FORMULA_RISK", "INVALID_ORDER_ID", "CSV_INPUT_TYPE"} for i in issues)
        relevant = tuple(i for i in issues if i.order_key == key or i.order_key is None) + tuple(local)
        complete = coverage and evidence_flags and not relevant and not global_block
        holds = tuple(dict.fromkeys((*(i.code for i in relevant), *(('GLOBAL_INPUT_HOLD',) if global_block else ()), *(('COVERAGE_INCOMPLETE',) if not coverage else ()), "PRODUCTION_EVALUATION_NOT_PERFORMED")))
        projection = (("canonical_order_id", key), ("review_assignment", "Jude" if _trim(s.get("doi_review_assignment", "")).lower() == "jude" else None), ("sales_credit_observed_uninterpreted", "OBSERVED" if _trim(s.get("displayed_sales_credit_value", "")) else "UNKNOWN"), ("sales_credit_entitlement", "UNINTERPRETED"), ("summary_occurrence_count", len(sr)), ("line_occurrence_count", len(lr)), ("all_purchased_rows", all_purchased), ("physical_purchased_rows", physical_purchased), ("service_purchased_rows", services), ("review_included", True), ("visible_coverage_complete", coverage), ("evidence_complete", complete), ("decision_eligible", False), ("safe_projection_eligible", not global_block))
        orders.append(StagedOrder(key, sr, lr, relevant, coverage, complete, False, holds, projection, tuple(tags)))
        issues.extend(local)
    return StagingBatch(summaries, lines, tuple(issues), tuple(orders),
                        summary_csv if type(summary_csv) is str else "",
                        lines_csv if type(lines_csv) is str else "")
