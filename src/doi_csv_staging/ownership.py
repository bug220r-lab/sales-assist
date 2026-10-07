"""Exact captured order-level sales-rep scope, separate from credit or fulfillment."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .staging import StagedOrder
from .split_review import SPLIT_STATUSES, split_sort_key

REP_SCOPES = (
    "OWNER",
    "UNASSIGNED_WEB",
    "OTHER_REP",
    "FIELD_UNVERIFIED",
    "REP_MISSING",
    "REP_UNMAPPED",
    "REP_CONFLICT",
    "CAPTURE_UNVERIFIED",
)
ELIGIBLE_REP_SCOPES = frozenset({"OWNER", "UNASSIGNED_WEB"})
_UNTRUSTED_CAPTURE = frozenset(
    {
        "DISPLAYED_ORDER_ID_UNVERIFIED",
        "SOURCE_JOIN_MISMATCH",
        "SOURCE_ASSIGNMENT_CONFLICT_OR_UNKNOWN",
        "REVIEW_ASSIGNMENT_UNVERIFIED",
        "TIMESTAMP_INVALID_OR_NAIVE",
        "TIMESTAMP_MISMATCH",
        "TIMEZONE_MISMATCH",
        "UTC_OFFSET_MISMATCH",
        "ORDER_CAPTURE_INCOMPLETE",
        "GLOBAL_INPUT_HOLD",
    }
)


@dataclass(frozen=True)
class RepScopePolicy:
    owner_aliases: frozenset[str]
    unassigned_web_aliases: frozenset[str]
    known_other_aliases: frozenset[str]

    def __post_init__(self) -> None:
        groups = (self.owner_aliases, self.unassigned_web_aliases, self.known_other_aliases)
        if (
            any(type(group) is not frozenset for group in groups)
            or any(
                type(value) is not str or re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", value) is None
                for group in groups
                for value in group
            )
            or any(groups[i] & groups[j] for i in range(3) for j in range(i + 1, 3))
        ):
            raise ValueError("REP_SCOPE_POLICY_INVALID")


# Established exact-match aliases. No case folding, whitespace trimming,
# suffix removal or multiline alias inference.
DEFAULT_REP_POLICY = RepScopePolicy(
    frozenset({"jlewis", "jlewis_web"}), frozenset({"customer-web"}), frozenset({"akeesy"})
)


def classify_rep_scope(
    order: StagedOrder,
    *,
    policy: RepScopePolicy = DEFAULT_REP_POLICY,
    global_input_held: bool = False,
) -> str:
    """Return only a closed status code; retain no raw rep string in the projection."""
    if type(policy) is not RepScopePolicy:
        raise ValueError("REP_SCOPE_POLICY_INVALID")
    summaries = [dict(row.raw_fields) for row in order.summary_occurrences]
    pairs = {
        (row.get("displayed_sales_credit_field", ""), row.get("displayed_sales_credit_value", ""))
        for row in summaries
    }
    if len(pairs) > 1:
        return "REP_CONFLICT"
    if not summaries:
        return "CAPTURE_UNVERIFIED"
    field, value = next(iter(pairs))
    if field != "ECS Sales Rep":
        return "FIELD_UNVERIFIED"
    if not value:
        return "REP_MISSING"
    if global_input_held or len(summaries) != 1 or set(order.holds) & _UNTRUSTED_CAPTURE:
        return "CAPTURE_UNVERIFIED"
    if summaries[0].get("snapshot_consistency_verified", "").lower() not in {"yes", "true"}:
        return "CAPTURE_UNVERIFIED"
    if value in policy.owner_aliases:
        return "OWNER"
    if value in policy.unassigned_web_aliases:
        return "UNASSIGNED_WEB"
    if value in policy.known_other_aliases:
        return "OTHER_REP"
    return "REP_UNMAPPED"


def full_total_order_key(order: dict[str, object]) -> tuple[object, ...]:
    """Valid nominal full totals descend; no currency conversion or split valuation."""
    return (
        *split_sort_key(order["split"])[1:],
        min(order["summary_record_ordinals"], default=5002),
        len(order["order_id"]),
        order["order_id"],
    )


def ownership_counts(orders: list[dict[str, object]]) -> dict[str, object]:
    observed = Counter(order["rep_scope"] for order in orders)
    eligible = [order for order in orders if order["rep_scope"] in ELIGIBLE_REP_SCOPES]
    split_counts = Counter(order["split"]["status"] for order in eligible)
    excluded = observed.get("OTHER_REP", 0)
    return {
        "schema": "doi-rep-scope/v1",
        "order_count": len(orders),
        "eligible_count": len(eligible),
        "excluded_count": excluded,
        "held_count": len(orders) - len(eligible) - excluded,
        "status_counts": {key: observed.get(key, 0) for key in REP_SCOPES},
        "eligible_split_counts": {key: split_counts.get(key, 0) for key in SPLIT_STATUSES},
    }
