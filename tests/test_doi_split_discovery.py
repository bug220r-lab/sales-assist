"""Fictional capture hints stay separate from split decisions and source evidence."""

from __future__ import annotations

import copy
import json
from dataclasses import replace

import pytest

from doi_csv_staging.review_marks import evidence_key
from doi_csv_staging.split_discovery import (
    classify_split_discovery,
    validate_discovery_projection,
)
from doi_csv_staging.split_review import classify_split_order
from tests.test_csv_staging_independent import line, stage, summary


def projection(category="NONE", **changes):
    value = {
        "schema": "doi-split-discovery/v1",
        "category": category,
        "ready_line_ordinals": [],
        "waiting_line_ordinals": [],
        "kit_dependent": False,
        "stock_clues": [],
        "quantity_verified": False,
        "decision_eligible": False,
    }
    if category == "HELD_MIXED_LABELS":
        value.update(ready_line_ordinals=[2], waiting_line_ordinals=[3])
    elif category == "STOCK_COUNTER_CLUE":
        value["stock_clues"] = [{"record_ordinal": 2, "ordered": "4", "oh": "1"}]
    value.update(changes)
    return value


def stock_line(**changes):
    values = {
        "ordered_quantity_displayed": "4",
        "OH_displayed": "1",
        "current_stock_icon_exact": "Unknown - not verified",
    }
    values.update(changes)
    return line(**values)


def mixed_order(*, assignment="yes", extra_rows=(), summary_changes=None):
    rows = [
        stock_line(current_stock_icon_exact="In Stock"),
        line(line_identifier="SYN-LINE-2", current_stock_icon_exact="Back Ordered"),
        *extra_rows,
    ]
    values = {
        "active_purchased_rows": str(len(rows)),
        "doi_source_assignment_conflict": assignment,
    }
    values.update(summary_changes or {})
    return stage([summary(**values)], rows).orders[0]


@pytest.mark.parametrize("assignment", ["yes", "unknown", ""])
def test_assignment_held_mixed_labels_are_a_hint_and_do_not_change_original_split(assignment):
    order = mixed_order(assignment=assignment)
    before = copy.deepcopy(order)
    original = classify_split_order(order)
    key = evidence_key(order)
    assert key is not None
    assert original["status"] == "CAPTURE_HELD"
    assert "SOURCE_ASSIGNMENT_CONFLICT_OR_UNKNOWN" in order.holds
    result = classify_split_discovery(order, split=original)
    assert result == projection("HELD_MIXED_LABELS")
    assert order == before and evidence_key(order) == key
    assert classify_split_order(order) == original
    assert not order.decision_eligible and not result["quantity_verified"]
    assert not result["decision_eligible"]
    assert classify_split_discovery(order) == result


def test_existing_apparent_split_is_not_duplicated_as_discovery_or_counter_clue():
    order = mixed_order(assignment="no")
    assert classify_split_order(order)["status"] == "APPARENT_SPLIT_CANDIDATE"
    assert classify_split_discovery(order) == projection()


@pytest.mark.parametrize("changed", ["global", "terminal", "structural", "future", "other_order"])
def test_reused_split_must_match_current_source_and_capture_guards(changed):
    order = stage(lines=[stock_line()]).orders[0]
    stale = classify_split_order(order)
    kwargs = {}
    if changed == "global":
        kwargs["global_input_held"] = True
    elif changed == "terminal":
        order = stage([summary(order_status="Shipped")], [stock_line()]).orders[0]
    elif changed == "structural":
        order = replace(order, holds=(*order.holds, "SOURCE_JOIN_MISMATCH"))
    elif changed == "future":
        kwargs["as_of"] = "2026-10-04T14:00:00Z"
    else:
        order = mixed_order(assignment="no")
    with pytest.raises(ValueError, match=r"^DISCOVERY_SOURCE_MISMATCH$"):
        classify_split_discovery(order, split=stale, **kwargs)


@pytest.mark.parametrize(
    "changes",
    [
        {"capture_complete": "no"},
        {"purchased_line_coverage_complete": "no"},
        {"active_purchased_rows": "3"},
        {"pagination_controls_displayed": "yes"},
        {"doi_review_assignment": "Unknown"},
        {"order_id_matches_queue": "no"},
        {"captured_at_america_new_york": ""},
        {"order_status": "Shipped"},
        {"order_status": "Canceled"},
        {"order_status": "Cancelled"},
        {"timezone": "UTC"},
    ],
)
def test_capture_review_assignment_and_terminal_holds_are_not_relaxed(changes):
    order = mixed_order(summary_changes=changes)
    assert classify_split_discovery(order) == projection()


def test_global_future_and_other_structural_holds_suppress_every_discovery_category():
    for order in (mixed_order(), stage(lines=[stock_line()]).orders[0]):
        assert classify_split_discovery(order, global_input_held=True) == projection()
        assert classify_split_discovery(order, as_of="2026-10-04T14:00:00Z") == projection()
        for code in (
            "GLOBAL_INPUT_HOLD",
            "SOURCE_JOIN_MISMATCH",
            "DUPLICATE_LINE_ID",
            "REVIEW_ASSIGNMENT_UNVERIFIED",
            "STRUCTURAL_COVERAGE_INCOMPLETE",
            "DISPLAYED_ORDER_ID_UNVERIFIED",
        ):
            held = replace(order, holds=(*order.holds, code))
            assert classify_split_discovery(held) == projection()


@pytest.mark.parametrize("kit_side", ["ready", "waiting"])
def test_held_mixed_labels_identify_kit_dependency_without_counting_components(kit_side):
    rows = [
        line(
            row_type="Purchased kit parent",
            current_stock_icon_exact=("In Stock" if kit_side == "ready" else "Back Ordered"),
        ),
        line(
            line_identifier="SYN-LINE-2",
            current_stock_icon_exact=("Back Ordered" if kit_side == "ready" else "In Stock"),
        ),
        line(
            row_type="component",
            counts_as_purchase="no",
            line_identifier="SYN-COMP-1",
            parent_line_id="SYN-LINE-1",
            component_coverage_complete="yes",
            current_stock_icon_exact="In Stock",
        ),
    ]
    order = stage(
        [
            summary(
                active_purchased_rows="2",
                visible_component_rows="1",
                component_coverage="yes",
                doi_source_assignment_conflict="yes",
            )
        ],
        rows,
    ).orders[0]
    result = classify_split_discovery(order)
    assert result == projection(
        "HELD_MIXED_LABELS",
        kit_dependent=True,
        ready_line_ordinals=[2] if kit_side == "ready" else [3],
        waiting_line_ordinals=[3] if kit_side == "ready" else [2],
    )
    assert 4 not in result["ready_line_ordinals"] + result["waiting_line_ordinals"]


def test_additional_kit_does_not_hide_an_independent_nonkit_ready_waiting_pair():
    rows = [
        line(current_stock_icon_exact="In Stock"),
        line(line_identifier="SYN-LINE-2", current_stock_icon_exact="Back Ordered"),
        line(
            line_identifier="SYN-KIT",
            row_type="Purchased kit parent",
            current_stock_icon_exact="In Stock",
        ),
        line(
            line_identifier="SYN-COMP",
            row_type="component",
            counts_as_purchase="no",
            parent_line_id="SYN-KIT",
            component_coverage_complete="yes",
            current_stock_icon_exact="In Stock",
        ),
    ]
    order = stage(
        [
            summary(
                active_purchased_rows="3",
                visible_component_rows="1",
                component_coverage="yes",
                doi_source_assignment_conflict="yes",
            )
        ],
        rows,
    ).orders[0]
    assert classify_split_discovery(order) == projection(
        "HELD_MIXED_LABELS", ready_line_ordinals=[2, 4], waiting_line_ordinals=[3]
    )


@pytest.mark.parametrize("assignment", ["no", "yes"])
@pytest.mark.parametrize(
    "labels",
    [
        {"current_stock_icon_exact": "Unknown - not verified"},
        {"current_stock_icon_exact": "In Stock", "product_eta_exact": "Back Ordered"},
        {"current_stock_icon_exact": "Vendor Stock"},
        {"current_stock_icon_exact": "SYN uninterpreted label"},
    ],
)
def test_partial_stock_counter_is_only_a_clue_despite_unknown_or_conflicting_labels(
    assignment, labels
):
    order = stage(
        [summary(doi_source_assignment_conflict=assignment)], [stock_line(**labels)]
    ).orders[0]
    before, key = copy.deepcopy(order), evidence_key(order)
    assert key is not None
    result = classify_split_discovery(order)
    assert result == projection("STOCK_COUNTER_CLUE")
    assert order == before and evidence_key(order) == key
    assert not order.evidence_complete and not order.decision_eligible
    assert result["ready_line_ordinals"] == result["waiting_line_ordinals"] == []


@pytest.mark.parametrize(
    "changes",
    [
        {"remaining_quantity": "0"},
        {"remaining_quantity": "0.00"},
        {"drop_ship": "yes"},
        {"drop_ship": "true"},
    ],
)
def test_known_zero_remaining_and_known_drop_ship_have_no_counter_clue(changes):
    order = stage(lines=[stock_line(**changes)]).orders[0]
    assert order.visible_coverage_complete
    assert classify_split_discovery(order) == projection()


@pytest.mark.parametrize("remaining", ["", "unknown", "Unknown - not verified"])
@pytest.mark.parametrize("ds", ["", "unknown", "no"])
def test_unknown_remaining_or_ds_does_not_become_a_verified_quantity(remaining, ds):
    order = stage(lines=[stock_line(remaining_quantity=remaining, drop_ship=ds)]).orders[0]
    assert classify_split_discovery(order) == projection("STOCK_COUNTER_CLUE")


@pytest.mark.parametrize("kind", ["service", "component", "kit", "nonpurchase"])
def test_stock_counters_exclude_services_components_kits_and_nonpurchases(kind):
    values = {}
    if kind == "service":
        rows = [stock_line(physical_or_service="service")]
        values["separate_service_rows_displayed"] = "1"
    elif kind == "kit":
        rows = [
            stock_line(row_type="Purchased kit parent", current_stock_icon_exact="Back Ordered")
        ]
    else:
        rows = [
            line(),
            stock_line(
                row_type="component" if kind == "component" else "placeholder",
                counts_as_purchase="no",
                line_identifier="SYN-NONPURCHASE",
                parent_line_id="SYN-LINE-1",
                component_coverage_complete="yes",
            ),
        ]
        if kind == "component":
            values.update(visible_component_rows="1", component_coverage="yes")
    order = stage([summary(**values)], rows).orders[0]
    assert order.visible_coverage_complete
    assert classify_split_discovery(order) == projection()


@pytest.mark.parametrize(
    ("ordered", "oh", "expected"),
    [
        ("003.000000", "01.500000", {"ordered": "3", "oh": "1.5"}),
        ("0.000002", "0.000001", {"ordered": "0.000002", "oh": "0.000001"}),
        (
            "999999999999999999.999999",
            "999999999999999998.999999",
            {"ordered": "999999999999999999.999999", "oh": "999999999999999998.999999"},
        ),
    ],
)
def test_stock_counter_decimal_boundaries_are_exact_and_canonical(ordered, oh, expected):
    order = stage(lines=[stock_line(ordered_quantity_displayed=ordered, OH_displayed=oh)]).orders[0]
    assert classify_split_discovery(order) == projection(
        "STOCK_COUNTER_CLUE", stock_clues=[{"record_ordinal": 2, **expected}]
    )


@pytest.mark.parametrize(
    "value",
    ["", "NaN", "Infinity", "1e1", "-1", "+1", "1,000", "1.0000001", "9" * 19, "SYN <script>"],
)
@pytest.mark.parametrize("field", ["ordered_quantity_displayed", "OH_displayed"])
def test_malformed_or_unbounded_stock_numbers_do_not_produce_clues(field, value):
    order = stage(lines=[stock_line(**{field: value})]).orders[0]
    assert classify_split_discovery(order) == projection()


@pytest.mark.parametrize(("ordered", "oh"), [("0", "0"), ("4", "0"), ("4", "4"), ("4", "5")])
def test_stock_clue_requires_strictly_positive_oh_less_than_ordered(ordered, oh):
    order = stage(lines=[stock_line(ordered_quantity_displayed=ordered, OH_displayed=oh)]).orders[0]
    assert classify_split_discovery(order) == projection()


def test_projection_never_copies_private_source_fields_and_cannot_mutate_source():
    order = stage(
        [summary(customer_info_email="private-synthetic@example.test")],
        [
            stock_line(
                product_name="SYN PRIVATE PRODUCT",
                sku="SYN PRIVATE SKU",
                current_stock_icon_exact="SYN PRIVATE LABEL",
            )
        ],
    ).orders[0]
    before, key = copy.deepcopy(order), evidence_key(order)
    result = classify_split_discovery(order)
    encoded = json.dumps(result)
    for private in ("private-synthetic", "SYN PRIVATE", "http://", "90000001"):
        assert private not in encoded
    result["stock_clues"][0]["oh"] = "999"
    result["ready_line_ordinals"].append(4000)
    assert order == before and evidence_key(order) == key
    assert classify_split_discovery(order) == projection("STOCK_COUNTER_CLUE")


@pytest.mark.parametrize("category", ["NONE", "HELD_MIXED_LABELS", "STOCK_COUNTER_CLUE"])
def test_valid_projection_categories_are_closed_and_nondecisional(category):
    value = projection(category)
    assert validate_discovery_projection(value) == value
    if category == "HELD_MIXED_LABELS":
        value["kit_dependent"] = True
        assert validate_discovery_projection(value) == value


@pytest.mark.parametrize("bad", [None, False, [], "SYN json", 1])
def test_validator_rejects_nonobject_input(bad):
    with pytest.raises(ValueError):
        validate_discovery_projection(bad)


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("schema", "unknown/v1"),
        ("category", "UNKNOWN"),
        ("category", []),
        ("quantity_verified", True),
        ("quantity_verified", 0),
        ("decision_eligible", True),
        ("decision_eligible", 0),
        ("kit_dependent", 1),
        ("ready_line_ordinals", ()),
        ("waiting_line_ordinals", None),
        ("stock_clues", {}),
        ("stock_clues", ()),
    ],
)
def test_validator_rejects_type_or_schema_coercion(field, bad):
    value = projection(**{field: bad})
    with pytest.raises(ValueError):
        validate_discovery_projection(value)


def test_validator_rejects_missing_and_extra_fields():
    for field in projection():
        value = projection()
        del value[field]
        with pytest.raises(ValueError):
            validate_discovery_projection(value)
    with pytest.raises(ValueError):
        validate_discovery_projection(projection(customer_email="synthetic@example.test"))


@pytest.mark.parametrize("category", ["HELD_MIXED_LABELS", "STOCK_COUNTER_CLUE"])
@pytest.mark.parametrize("ordinal", [True, "2", 1, 5002, -2, None])
def test_validator_rejects_invalid_ordinals(category, ordinal):
    value = projection(category)
    if category == "HELD_MIXED_LABELS":
        value["ready_line_ordinals"] = [ordinal]
    else:
        value["stock_clues"][0]["record_ordinal"] = ordinal
    with pytest.raises(ValueError):
        validate_discovery_projection(value)


@pytest.mark.parametrize(
    "value",
    [
        projection("NONE", ready_line_ordinals=[2]),
        projection("NONE", kit_dependent=True),
        projection("NONE", stock_clues=[{"record_ordinal": 2, "ordered": "4", "oh": "1"}]),
        projection("HELD_MIXED_LABELS", ready_line_ordinals=[]),
        projection("HELD_MIXED_LABELS", waiting_line_ordinals=[]),
        projection("HELD_MIXED_LABELS", ready_line_ordinals=[2, 2]),
        projection("HELD_MIXED_LABELS", waiting_line_ordinals=[2]),
        projection(
            "HELD_MIXED_LABELS", stock_clues=[{"record_ordinal": 4, "ordered": "2", "oh": "1"}]
        ),
        projection("STOCK_COUNTER_CLUE", stock_clues=[]),
        projection("STOCK_COUNTER_CLUE", ready_line_ordinals=[3]),
        projection("STOCK_COUNTER_CLUE", waiting_line_ordinals=[3]),
        projection("STOCK_COUNTER_CLUE", kit_dependent=True),
    ],
)
def test_validator_rejects_contradictory_or_duplicate_category_members(value):
    with pytest.raises(ValueError):
        validate_discovery_projection(value)


@pytest.mark.parametrize(
    "number",
    [
        None,
        True,
        1,
        "01",
        "1.0",
        "1.20",
        " 1",
        "1 ",
        "1e0",
        "+1",
        "-1",
        "NaN",
        "1.0000001",
        "9" * 19,
    ],
)
@pytest.mark.parametrize("field", ["ordered", "oh"])
def test_validator_requires_canonical_bounded_numeric_strings(field, number):
    value = projection("STOCK_COUNTER_CLUE")
    value["stock_clues"][0][field] = number
    with pytest.raises(ValueError):
        validate_discovery_projection(value)


def test_validator_enforces_stock_item_shape_uniqueness_and_counter_relation():
    invalid = [
        None,
        [],
        {"record_ordinal": 2, "ordered": "4"},
        {"record_ordinal": 2, "ordered": "4", "oh": "1", "sku": "SYN-PRIVATE"},
        {"record_ordinal": 2, "ordered": "4", "oh": "0"},
        {"record_ordinal": 2, "ordered": "4", "oh": "4"},
        {"record_ordinal": 2, "ordered": "4", "oh": "5"},
    ]
    for item in invalid:
        with pytest.raises(ValueError):
            validate_discovery_projection(projection("STOCK_COUNTER_CLUE", stock_clues=[item]))
    duplicate = projection("STOCK_COUNTER_CLUE")
    duplicate["stock_clues"].append(copy.deepcopy(duplicate["stock_clues"][0]))
    with pytest.raises(ValueError):
        validate_discovery_projection(duplicate)


def test_validator_accepts_exact_5000_ordinal_boundary_and_rejects_overflow():
    held = projection(
        "HELD_MIXED_LABELS", ready_line_ordinals=list(range(2, 5001)), waiting_line_ordinals=[5001]
    )
    stock = projection(
        "STOCK_COUNTER_CLUE",
        stock_clues=[
            {"record_ordinal": ordinal, "ordered": "2", "oh": "1"} for ordinal in range(2, 5002)
        ],
    )
    for value in (held, stock):
        assert validate_discovery_projection(value) == value
    held["ready_line_ordinals"].append(5002)
    stock["stock_clues"].append({"record_ordinal": 5002, "ordered": "2", "oh": "1"})
    for value in (held, stock):
        with pytest.raises(ValueError):
            validate_discovery_projection(value)
