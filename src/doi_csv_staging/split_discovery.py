"""Non-authoritative purchased-line clues, separate from the split decision projection."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal, TypedDict, cast

from .split_review import (
    _KIT,
    _amount,
    _canonical,
    _label,
    classify_split_order,
    validate_split_projection,
)
from .staging import StagedOrder, _number, _time, purchase_nature

SCHEMA = "doi-split-discovery/v1"
DISCOVERY_CATEGORIES = ("NONE", "HELD_MIXED_LABELS", "STOCK_COUNTER_CLUE")
ASSIGNMENT_HOLD = "SOURCE_ASSIGNMENT_CONFLICT_OR_UNKNOWN"
MAX_DISCOVERY_ROWS = 5000


class StockClue(TypedDict):
    record_ordinal: int
    ordered: str
    oh: str


class DiscoveryProjection(TypedDict):
    schema: str
    category: Literal["NONE", "HELD_MIXED_LABELS", "STOCK_COUNTER_CLUE"]
    ready_line_ordinals: list[int]
    waiting_line_ordinals: list[int]
    kit_dependent: bool
    stock_clues: list[StockClue]
    quantity_verified: Literal[False]
    decision_eligible: Literal[False]


def classify_split_discovery(
    order: StagedOrder,
    *,
    global_input_held: bool = False,
    as_of: str | None = None,
    split: dict[str, object] | None = None,
) -> DiscoveryProjection:
    """Find clues without changing source evidence, holds, marks, or split eligibility.

    ``split`` may assert the canonical projection for this same order and arguments;
    it is checked against current source rather than trusted as a capture gate.
    Assignment is ignored only in a temporary diagnostic copy. Counter values are
    captured comparisons, never allocated, available, active, or remaining quantities.
    """
    result: DiscoveryProjection = {
        "schema": SCHEMA,
        "category": "NONE",
        "ready_line_ordinals": [],
        "waiting_line_ordinals": [],
        "kit_dependent": False,
        "stock_clues": [],
        "quantity_verified": False,
        "decision_eligible": False,
    }
    original = classify_split_order(order, global_input_held=global_input_held, as_of=as_of)
    if split is not None and validate_split_projection(split) != original:
        raise ValueError("DISCOVERY_SOURCE_MISMATCH")
    summary = dict(order.summary_occurrences[0].raw_fields) if order.summary_occurrences else {}
    if (
        original["status"] == "APPARENT_SPLIT_CANDIDATE"
        or "DISPLAYED_ORDER_ID_UNVERIFIED" in order.holds
        or _time(summary.get("captured_at_america_new_york", "")) is None
    ):
        return result
    diagnostic = original
    if ASSIGNMENT_HOLD in order.holds:
        diagnostic = classify_split_order(
            replace(order, holds=tuple(hold for hold in order.holds if hold != ASSIGNMENT_HOLD)),
            global_input_held=global_input_held,
            as_of=as_of,
        )
    # Capture, identity, global input, terminal status and all other structural
    # holds continue to block both categories, including the numeric fallback.
    if diagnostic["status"] == "CAPTURE_HELD":
        return result

    fields_by_row = [(row.row_number, dict(row.raw_fields)) for row in order.line_occurrences]
    if (
        original["status"] == "CAPTURE_HELD"
        and ASSIGNMENT_HOLD in order.holds
        and diagnostic["status"] == "APPARENT_SPLIT_CANDIDATE"
    ):
        result["category"] = "HELD_MIXED_LABELS"
        result["ready_line_ordinals"] = list(cast(list[int], diagnostic["ready_line_ordinals"]))
        result["waiting_line_ordinals"] = list(cast(list[int], diagnostic["waiting_line_ordinals"]))
        non_kit = {
            ordinal
            for ordinal, fields in fields_by_row
            if _label(fields.get("row_type", "")) not in _KIT
        }
        result["kit_dependent"] = not (
            non_kit.intersection(result["ready_line_ordinals"])
            and non_kit.intersection(result["waiting_line_ordinals"])
        )
    else:
        for ordinal, fields in fields_by_row:
            if (
                _label(fields.get("counts_as_purchase", "")) not in {"yes", "true"}
                or _label(fields.get("row_type", "")) in _KIT
                or purchase_nature(
                    fields.get("row_type", ""),
                    fields.get("physical_or_service", ""),
                    fields.get("parent_line_id", ""),
                )
                != "physical"
                or _label(fields.get("drop_ship", "")) in {"yes", "true"}
                or _number(fields.get("remaining_quantity", "")) == 0
            ):
                continue
            ordered = _amount(fields.get("ordered_quantity_displayed", ""))
            oh = _amount(fields.get("OH_displayed", ""))
            if ordered is not None and oh is not None and 0 < oh < ordered:
                result["stock_clues"].append(
                    {
                        "record_ordinal": ordinal,
                        "ordered": _canonical(ordered),
                        "oh": _canonical(oh),
                    }
                )
        if result["stock_clues"]:
            result["category"] = "STOCK_COUNTER_CLUE"
    validate_discovery_projection(result)
    return result


def validate_discovery_projection(value: object) -> DiscoveryProjection:
    """Validate the closed advisory payload; the containing response binds source refs."""
    error = "DISCOVERY_PROJECTION_INVALID"
    if (
        type(value) is not dict
        or set(value)
        != {
            "schema",
            "category",
            "ready_line_ordinals",
            "waiting_line_ordinals",
            "kit_dependent",
            "stock_clues",
            "quantity_verified",
            "decision_eligible",
        }
        or value["schema"] != SCHEMA
        or type(value["category"]) is not str
        or value["category"] not in DISCOVERY_CATEGORIES
        or type(value["kit_dependent"]) is not bool
        or value["quantity_verified"] is not False
        or value["decision_eligible"] is not False
    ):
        raise ValueError(error)
    references: list[int] = []
    for name in ("ready_line_ordinals", "waiting_line_ordinals"):
        rows = value[name]
        if (
            type(rows) is not list
            or len(rows) > MAX_DISCOVERY_ROWS
            or any(type(row) is not int or not 2 <= row <= MAX_DISCOVERY_ROWS + 1 for row in rows)
        ):
            raise ValueError(error)
        references.extend(rows)
    if len(references) > MAX_DISCOVERY_ROWS or len(references) != len(set(references)):
        raise ValueError(error)
    clues = value["stock_clues"]
    if type(clues) is not list or len(clues) > MAX_DISCOVERY_ROWS:
        raise ValueError(error)
    clue_refs: set[int] = set()
    for clue in clues:
        if (
            type(clue) is not dict
            or set(clue) != {"record_ordinal", "ordered", "oh"}
            or type(clue["record_ordinal"]) is not int
            or not 2 <= clue["record_ordinal"] <= MAX_DISCOVERY_ROWS + 1
            or clue["record_ordinal"] in clue_refs
            or type(clue["ordered"]) is not str
            or type(clue["oh"]) is not str
        ):
            raise ValueError(error)
        clue_refs.add(clue["record_ordinal"])
        ordered, oh = _amount(clue["ordered"]), _amount(clue["oh"])
        if (
            ordered is None
            or oh is None
            or not 0 < oh < ordered
            or _canonical(ordered) != clue["ordered"]
            or _canonical(oh) != clue["oh"]
        ):
            raise ValueError(error)
    category = value["category"]
    if (
        (category == "NONE" and (references or clues or value["kit_dependent"]))
        or (
            category == "HELD_MIXED_LABELS"
            and (not value["ready_line_ordinals"] or not value["waiting_line_ordinals"] or clues)
        )
        or (
            category == "STOCK_COUNTER_CLUE" and (not clues or references or value["kit_dependent"])
        )
    ):
        raise ValueError(error)
    return cast(DiscoveryProjection, value)
