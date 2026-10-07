"""Closed, apparent split patterns and captured full totals for human review."""

from __future__ import annotations

import re
from decimal import Decimal
from datetime import date
from zoneinfo import ZoneInfo
from synthetic_sales_assist.domain.timestamps import parse_timestamp
from synthetic_sales_assist.domain.normalization import normalize_es_number, NormalizationError
from .staging import StagedOrder, ascii_four_trim, purchase_nature, _number, _time
from .triage import (
    _APPARENT,
    _DELAYED,
    _VENDOR,
    _relative,
    _date,
    _STRUCTURAL,
    _GLOBAL,
    _safe_value,
    _utc,
)

SCHEMA = "doi-split-review/v1"
SPLIT_STATUSES = (
    "CONFIRMED_SPLIT_CRITERIA",
    "APPARENT_SPLIT_CANDIDATE",
    "INSUFFICIENT_SPLIT_EVIDENCE",
    "NO_SPLIT_PATTERN",
    "CAPTURE_HELD",
)
SPLIT_REASON_CODES = frozenset(
    (
        'DISTINCT_READY_WAITING_LINES LABELS_ONLY NOT_CONFIRMED_FULL '
        'CAPTURE_COHERENCE_HOLD TERMINAL_ORDER_OBSERVED KNOWN_DS_EXCLUDED '
        'ZERO_REMAINING_EXCLUDED KIT_EVIDENCE_UNRESOLVED STOCK_LABEL_CONFLICT '
        'NO_DISTINCT_SPLIT_PATTERN TOTAL_INVALID TOTAL_MISMATCH TOTAL_UNKNOWN'
    ).split()
)
SPLIT_MISSING_FACT_CODES = frozenset(
    (
        'ACTIVE_QUANTITY_UNVERIFIED FULL_ALLOCATION_NOT_CAPTURED DS_UNVERIFIED '
        'CURRENT_STOCK_UNVERIFIED KIT_COMPONENT_SCOPE_UNVERIFIED'
    ).split()
)
TOTAL_STATUSES = ("VALID", "UNKNOWN", "INVALID", "MISMATCH")
_KIT = frozenset({"kit", "purchased kit", "purchased_kit", "purchased kit parent"})
_SYMBOLS = frozenset(
    {
        "$",
        "US$",
        "CA$",
        "C$",
        "A$",
        "AU$",
        "NZ$",
        "€",
        "£",
        "¥",
        "USD",
        "CAD",
        "AUD",
        "NZD",
        "EUR",
        "GBP",
        "JPY",
    }
)
_NUMERIC = re.compile(r"[0-9]{1,18}(?:\.[0-9]{1,6})?", re.ASCII)
_DISPLAY_NUMBER = re.compile(
    r"(?:[0-9]{1,18}|[0-9]{1,3}(?:,[0-9]{3}){1,5})(?:\.[0-9]{1,6})?", re.ASCII
)


def _label(value: str) -> str:
    return ascii_four_trim(value).lower()


def _amount(value: str, *, display: bool = False) -> Decimal | None:
    value = ascii_four_trim(value)
    grammar = _DISPLAY_NUMBER if display else _NUMERIC
    if len(value) > 32 or grammar.fullmatch(value) is None:
        return None
    return Decimal(value.replace(",", ""))


def _canonical(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def parse_order_total(summary_fields: dict[str, str]) -> dict[str, object]:
    """Parse only captured full OrderTotal; never subtotal, balance or currency inference."""
    displayed = ascii_four_trim(summary_fields.get("order_total_displayed", ""))
    numeric = ascii_four_trim(summary_fields.get("order_total_numeric", ""))
    symbol_raw = ascii_four_trim(summary_fields.get("currency_symbol_displayed", ""))
    code_raw = ascii_four_trim(summary_fields.get("currency_code", ""))
    symbol = symbol_raw if symbol_raw in _SYMBOLS else None
    code = code_raw if re.fullmatch(r"[A-Z]{3}", code_raw, re.ASCII) else None
    safe_display = None
    display_number = displayed
    if symbol and display_number.startswith(symbol):
        display_number = ascii_four_trim(display_number[len(symbol) :])
    elif symbol and display_number.endswith(symbol):
        display_number = ascii_four_trim(display_number[: -len(symbol)])
    parsed_display = _amount(display_number, display=True)
    parsed_numeric = _amount(numeric)
    if parsed_display is not None and len(displayed) <= 64:
        safe_display = displayed
    if not displayed and not numeric:
        status = "UNKNOWN"
    elif (
        parsed_display is None
        or parsed_numeric is None
        or symbol_raw
        and symbol is None
        or code_raw
        and code is None
        and _label(code_raw) not in {"unknown", "unknown - not displayed", "not displayed"}
    ):
        status = "INVALID"
    elif parsed_display != parsed_numeric:
        status = "MISMATCH"
    else:
        status = "VALID"
    return {
        "amount": _canonical(parsed_numeric) if status == "VALID" else None,
        "displayed": safe_display,
        "currency_code": code,
        "currency_symbol": symbol,
        "status": status,
    }


def _waiting(value: str, capture_date: date | None = None) -> bool:
    observed = _date(value)
    dated_wait = (
        _label(value).startswith("ships on ")
        and observed is not None
        and observed.year != 1999
        and capture_date is not None
        and observed >= capture_date
    )
    return _label(value) in _DELAYED or _relative(value) or dated_wait


def classify_split_order(
    order: StagedOrder, *, global_input_held: bool = False, as_of: str | None = None
) -> dict[str, object]:
    summary = dict(order.summary_occurrences[0].raw_fields) if order.summary_occurrences else {}
    total = parse_order_total(summary)
    reasons: set[str] = {"LABELS_ONLY", "NOT_CONFIRMED_FULL"}
    missing: set[str] = {"ACTIVE_QUANTITY_UNVERIFIED", "FULL_ALLOCATION_NOT_CAPTURED"}
    capture = _time(summary.get("captured_at_america_new_york", ""))
    capture_date = None
    source_time_invalid = False
    try:
        capture_date = (
            capture.astimezone(ZoneInfo("America/New_York")).date() if capture is not None else None
        )
    except (ValueError, OverflowError):
        source_time_invalid = True
    line_items: list[dict[str, object]] = []
    ready: list[int] = []
    waiting: list[int] = []
    unresolved: list[int] = []
    fields_by_row = [(row, dict(row.raw_fields)) for row in order.line_occurrences]
    incomplete_capture = "ORDER_CAPTURE_INCOMPLETE" in order.holds
    # The schema has no structured missing-scope proof. A linked kit gap
    # remains a warning; it cannot waive whole-order capture incompleteness.
    linked_kit_gap = (
        incomplete_capture
        and order.visible_coverage_complete
        and any(
            _label(g.get("row_type", "")) == "component coverage gap - not a merchandise line"
            and _label(g.get("counts_as_purchase", "")) in {"no", "false"}
            and ascii_four_trim(g.get("parent_line_id", ""))
            and any(
                _label(p.get("row_type", "")) in _KIT
                and ascii_four_trim(p.get("line_identifier", ""))
                == ascii_four_trim(g.get("parent_line_id", ""))
                and purchase_nature(
                    p.get("row_type", ""),
                    p.get("physical_or_service", ""),
                    p.get("parent_line_id", ""),
                )
                == "physical"
                for _, p in fields_by_row
            )
            for _, g in fields_by_row
        )
    )
    held = (
        source_time_invalid
        or global_input_held
        or not order.visible_coverage_complete
        or bool(set(order.holds) & (_GLOBAL | _STRUCTURAL))
        or not order.summary_occurrences
        or not order.line_occurrences
        or incomplete_capture
    )
    if linked_kit_gap:
        reasons.add("KIT_EVIDENCE_UNRESOLVED")
        missing.add("KIT_COMPONENT_SCOPE_UNVERIFIED")
    if as_of is not None:
        exact_now = parse_timestamp(_utc(as_of))
        if capture is not None:
            try:
                exact_capture = parse_timestamp(
                    _utc(summary.get("captured_at_america_new_york", ""))
                )
                held = held or (exact_capture.epoch_seconds, exact_capture.nanosecond) > (
                    exact_now.epoch_seconds,
                    exact_now.nanosecond,
                )
            except (ValueError, OverflowError):
                held = True
    terminal = _label(summary.get("order_status", "")) in {"shipped", "canceled", "cancelled"}
    if held:
        reasons.add("CAPTURE_COHERENCE_HOLD")
    if terminal:
        reasons.add("TERMINAL_ORDER_OBSERVED")
    for row, fields in fields_by_row:
        if (
            _label(fields.get("counts_as_purchase", "")) not in {"yes", "true"}
            or purchase_nature(
                fields.get("row_type", ""),
                fields.get("physical_or_service", ""),
                fields.get("parent_line_id", ""),
            )
            != "physical"
        ):
            continue
        ordinal = row.row_number
        ds = _label(fields.get("drop_ship", ""))
        try:
            es_number = normalize_es_number(fields.get("es_number", ""))
            if len(es_number) > 64:
                es_number = None
        except NormalizationError:
            es_number = None
        line_items.append(
            {
                "record_ordinal": ordinal,
                "es_number": es_number,
                "current_stock": _safe_value(
                    "current_stock_icon_exact", fields.get("current_stock_icon_exact", "")
                ),
                "ds": (
                    "YES" if ds in {"yes", "true"} else "NO" if ds in {"no", "false"} else "UNKNOWN"
                ),
            }
        )
        if _number(fields.get("remaining_quantity", "")) == 0:
            reasons.add("ZERO_REMAINING_EXCLUDED")
            continue
        ds = _label(fields.get("drop_ship", ""))
        if ds in {"yes", "true"}:
            reasons.add("KNOWN_DS_EXCLUDED")
            continue
        if ds not in {"no", "false"}:
            missing.add("DS_UNVERIFIED")
        current = fields.get("current_stock_icon_exact", "")
        product = fields.get("product_eta_exact", "")
        looks_ready = _label(current) in _APPARENT
        looks_waiting = _waiting(current, capture_date)
        conflict = looks_ready and (
            _waiting(product, capture_date)
            or _label(product) in _VENDOR
            or _date(product) is not None
        )
        if conflict:
            reasons.add("STOCK_LABEL_CONFLICT")
            unresolved.append(ordinal)
            continue
        if _label(fields.get("row_type", "")) in _KIT:
            parent = ascii_four_trim(fields.get("line_identifier", ""))
            components = [
                d
                for _, d in fields_by_row
                if ascii_four_trim(d.get("parent_line_id", "")) == parent
            ]
            coherent_components = bool(components) and all(
                _label(d.get("row_type", "")) in {"component", "kit component", "kit_component"}
                and _label(d.get("counts_as_purchase", "")) in {"no", "false"}
                and _label(d.get("component_coverage_complete", ""))
                in {"yes", "true", "complete", "verified"}
                and _label(d.get("current_stock_icon_exact", "")) in _APPARENT
                for d in components
            )
            if looks_ready and not coherent_components:
                looks_ready = False
                reasons.add("KIT_EVIDENCE_UNRESOLVED")
                missing.add("KIT_COMPONENT_SCOPE_UNVERIFIED")
        if held or terminal:
            unresolved.append(ordinal)
        elif looks_ready:
            ready.append(ordinal)
        elif looks_waiting:
            waiting.append(ordinal)
        else:
            unresolved.append(ordinal)
            missing.add("CURRENT_STOCK_UNVERIFIED")
    if held or terminal:
        status = "CAPTURE_HELD"
    elif ready and waiting:
        status = "APPARENT_SPLIT_CANDIDATE"
        reasons.add("DISTINCT_READY_WAITING_LINES")
    elif unresolved:
        status = "INSUFFICIENT_SPLIT_EVIDENCE"
        reasons.add("NO_DISTINCT_SPLIT_PATTERN")
    else:
        status = "NO_SPLIT_PATTERN"
        reasons.add("NO_DISTINCT_SPLIT_PATTERN")
    if total["status"] != "VALID":
        reasons.add("TOTAL_" + str(total["status"]))
    result = {
        "schema": SCHEMA,
        "status": status,
        "line_items": line_items,
        "ready_line_ordinals": ready,
        "waiting_line_ordinals": waiting,
        "unresolved_line_ordinals": unresolved,
        "reason_codes": sorted(reasons),
        "missing_fact_codes": sorted(missing),
        "total": total,
        "quantity_verified": False,
        "decision_eligible": False,
    }
    validate_split_projection(result)
    return result


def validate_split_projection(value: object) -> dict[str, object]:
    keys = {
        "schema",
        "status",
        "line_items",
        "ready_line_ordinals",
        "waiting_line_ordinals",
        "unresolved_line_ordinals",
        "reason_codes",
        "missing_fact_codes",
        "total",
        "quantity_verified",
        "decision_eligible",
    }
    if (
        type(value) is not dict
        or set(value) != keys
        or value["schema"] != SCHEMA
        or value["status"] not in SPLIT_STATUSES
        or value["status"] == "CONFIRMED_SPLIT_CRITERIA"
        or value["quantity_verified"] is not False
        or value["decision_eligible"] is not False
    ):
        raise ValueError("SPLIT_PROJECTION_INVALID")
    items = value["line_items"]
    if type(items) is not list or len(items) > 5000:
        raise ValueError("SPLIT_PROJECTION_INVALID")
    item_ordinals: set[int] = set()
    for item in items:
        if (
            type(item) is not dict
            or set(item) != {"record_ordinal", "es_number", "current_stock", "ds"}
            or type(item["record_ordinal"]) is not int
            or not 2 <= item["record_ordinal"] <= 5001
            or item["record_ordinal"] in item_ordinals
            or item["ds"] not in {"YES", "NO", "UNKNOWN"}
        ):
            raise ValueError("SPLIT_PROJECTION_INVALID")
        item_ordinals.add(item["record_ordinal"])
        es = item["es_number"]
        if es is not None and (
            type(es) is not str or re.fullmatch(r"[1-9][0-9]{0,63}", es, re.ASCII) is None
        ):
            raise ValueError("SPLIT_PROJECTION_INVALID")
        stock = item["current_stock"]
        if stock is not None and (
            type(stock) is not str or _safe_value("current_stock_icon_exact", stock) != stock
        ):
            raise ValueError("SPLIT_PROJECTION_INVALID")
    all_ordinals: list[int] = []
    for name in ("ready_line_ordinals", "waiting_line_ordinals", "unresolved_line_ordinals"):
        ordinals = value[name]
        if (
            type(ordinals) is not list
            or len(ordinals) > 5000
            or any(type(x) is not int or not 2 <= x <= 5001 for x in ordinals)
        ):
            raise ValueError("SPLIT_PROJECTION_INVALID")
        all_ordinals.extend(ordinals)
    if len(all_ordinals) != len(set(all_ordinals)) or not set(all_ordinals) <= item_ordinals:
        raise ValueError("SPLIT_PROJECTION_INVALID")
    item_map = {item["record_ordinal"]: item for item in value["line_items"]}
    for ordinal in value["ready_line_ordinals"]:
        item = item_map[ordinal]
        if (
            item["ds"] == "YES"
            or item["current_stock"] is None
            or _label(item["current_stock"]) not in _APPARENT
        ):
            raise ValueError("SPLIT_PROJECTION_INVALID")
    for ordinal in value["waiting_line_ordinals"]:
        item = item_map[ordinal]
        stock = item["current_stock"]
        dated = _date(stock) if stock is not None else None
        if (
            item["ds"] == "YES"
            or stock is None
            or not _waiting(stock, dated)
            or dated is not None
            and dated.year == 1999
        ):
            raise ValueError("SPLIT_PROJECTION_INVALID")
    for name, allowed in (
        ("reason_codes", SPLIT_REASON_CODES),
        ("missing_fact_codes", SPLIT_MISSING_FACT_CODES),
    ):
        items = value[name]
        if (
            type(items) is not list
            or len(items) != len(set(items))
            or any(type(x) is not str or x not in allowed for x in items)
        ):
            raise ValueError("SPLIT_PROJECTION_INVALID")
    total = value["total"]
    if (
        type(total) is not dict
        or set(total) != {"amount", "displayed", "currency_code", "currency_symbol", "status"}
        or total["status"] not in TOTAL_STATUSES
    ):
        raise ValueError("SPLIT_PROJECTION_INVALID")
    if (
        total["amount"] is not None
        and (type(total["amount"]) is not str or _amount(total["amount"]) is None)
        or total["status"] == "VALID"
        and total["amount"] is None
        or total["status"] != "VALID"
        and total["amount"] is not None
    ):
        raise ValueError("SPLIT_PROJECTION_INVALID")
    if (
        total["currency_code"] is not None
        and (
            type(total["currency_code"]) is not str
            or re.fullmatch(r"[A-Z]{3}", total["currency_code"], re.ASCII) is None
        )
        or total["currency_symbol"] is not None
        and total["currency_symbol"] not in _SYMBOLS
    ):
        raise ValueError("SPLIT_PROJECTION_INVALID")
    if total["displayed"] is not None:
        if type(total["displayed"]) is not str or len(total["displayed"]) > 64:
            raise ValueError("SPLIT_PROJECTION_INVALID")
        token = total["displayed"]
        symbol = total["currency_symbol"]
        if symbol and token.startswith(symbol):
            token = ascii_four_trim(token[len(symbol) :])
        elif symbol and token.endswith(symbol):
            token = ascii_four_trim(token[: -len(symbol)])
        if _amount(token, display=True) is None:
            raise ValueError("SPLIT_PROJECTION_INVALID")
        if total["status"] == "VALID" and _amount(token, display=True) != _amount(total["amount"]):
            raise ValueError("SPLIT_PROJECTION_INVALID")
    elif total["status"] == "VALID":
        raise ValueError("SPLIT_PROJECTION_INVALID")
    if (
        set(value["reason_codes"]) & {"CAPTURE_COHERENCE_HOLD", "TERMINAL_ORDER_OBSERVED"}
        and value["status"] != "CAPTURE_HELD"
    ):
        raise ValueError("SPLIT_PROJECTION_INVALID")
    candidate = bool(value["ready_line_ordinals"] and value["waiting_line_ordinals"])
    if (
        (value["status"] == "APPARENT_SPLIT_CANDIDATE") != candidate
        or value["status"] == "CAPTURE_HELD"
        and (value["ready_line_ordinals"] or value["waiting_line_ordinals"])
    ):
        raise ValueError("SPLIT_PROJECTION_INVALID")
    return value


def split_sort_key(projection: dict[str, object]) -> tuple[object, ...]:
    """Status groups, valid totals first, descending nominal full totals; no conversion."""
    validate_split_projection(projection)
    total = projection["total"]
    valid = total["status"] == "VALID"
    status_rank = {
        "APPARENT_SPLIT_CANDIDATE": 0,
        "INSUFFICIENT_SPLIT_EVIDENCE": 1,
        "NO_SPLIT_PATTERN": 2,
        "CAPTURE_HELD": 3,
    }
    return (
        status_rank[projection["status"]],
        0 if valid else 1,
        -Decimal(total["amount"]) if valid else Decimal(0),
    )
