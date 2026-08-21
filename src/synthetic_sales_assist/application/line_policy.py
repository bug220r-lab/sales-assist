"""One closed public line-fact policy shared by manifest and local adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, cast

from synthetic_sales_assist.doi.models import (
    DropShipState,
    LineActivity,
    LineAvailability,
)
from synthetic_sales_assist.domain.numeric import (
    Money,
    MoneyViolation,
    Quantity,
    QuantityViolation,
)
from synthetic_sales_assist.domain.timestamps import (
    CanonicalTimestamp,
    TimestampValidationError,
)


@dataclass(frozen=True, slots=True)
class LineFieldPolicy:
    unknown_reason: str
    known_codec: str
    known_values: tuple[str, ...] = ()
    allowed_tags: tuple[str, ...] = ("KNOWN", "UNKNOWN", "NOT_APPLICABLE")


LINE_FIELD_POLICIES: Final = MappingProxyType(
    {
        "activity": LineFieldPolicy(
            "RC-125",
            "ENUM",
            tuple(item.value for item in LineActivity),
        ),
        "availability": LineFieldPolicy(
            "RC-016",
            "ENUM",
            tuple(item.value for item in LineAvailability),
        ),
        "drop_ship_state": LineFieldPolicy(
            "RC-017",
            "ENUM",
            tuple(item.value for item in DropShipState),
        ),
        "eta": LineFieldPolicy("RC-115", "CANONICAL_TIMESTAMP"),
        "line_value": LineFieldPolicy("RC-134", "MONEY"),
        "quantity": LineFieldPolicy("RC-129", "QUANTITY"),
    }
)

_FACT_MEMBERS: Final = frozenset({"reason_code", "tag", "value"})


def _money(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or frozenset(value) != Money.JSON_MEMBERS:
        raise ValueError("LINE_FACT_MONEY_INVALID")
    try:
        return Money.from_json_value(dict(value)).to_json_value()
    except MoneyViolation:
        raise ValueError("LINE_FACT_MONEY_INVALID") from None


def _known_value(policy: LineFieldPolicy, value: object) -> object:
    if policy.known_codec == "ENUM":
        if type(value) is not str or value not in policy.known_values:
            raise ValueError("LINE_FACT_ENUM_INVALID")
        return value
    if policy.known_codec == "CANONICAL_TIMESTAMP":
        try:
            accepted = CanonicalTimestamp(value)
        except TimestampValidationError:
            raise ValueError("LINE_FACT_TIMESTAMP_INVALID") from None
        if accepted.value != value:
            raise ValueError("LINE_FACT_TIMESTAMP_INVALID")
        return accepted.value
    if policy.known_codec == "QUANTITY":
        try:
            accepted_quantity = Quantity.from_json_value(value)
        except QuantityViolation:
            raise ValueError("LINE_FACT_QUANTITY_INVALID") from None
        return accepted_quantity.to_json_value()
    if policy.known_codec == "MONEY":
        return _money(value)
    raise ValueError("LINE_FACT_POLICY_INVALID")


def validate_line_fact(field: str, fact: object) -> dict[str, object]:
    """Return one normalized public fact or raise a closed field-policy error."""

    policy = LINE_FIELD_POLICIES.get(field)
    if policy is None:
        raise ValueError("LINE_FACT_FIELD_INVALID")
    if not isinstance(fact, Mapping) or frozenset(fact) != _FACT_MEMBERS:
        raise ValueError("LINE_FACT_SHAPE_INVALID")
    accepted = cast(Mapping[str, object], fact)
    tag = accepted["tag"]
    reason = accepted["reason_code"]
    value = accepted["value"]
    if type(tag) is not str or tag not in policy.allowed_tags:
        raise ValueError("LINE_FACT_TAG_INVALID")
    if tag == "KNOWN":
        if reason is not None or value is None:
            raise ValueError("LINE_FACT_PARTITION_INVALID")
        value = _known_value(policy, value)
    elif tag == "UNKNOWN":
        if reason != policy.unknown_reason or value is not None:
            raise ValueError("LINE_FACT_UNKNOWN_REASON_INVALID")
    elif reason is not None or value is not None:
        raise ValueError("LINE_FACT_PARTITION_INVALID")
    return {"reason_code": reason, "tag": tag, "value": value}


__all__ = ["LINE_FIELD_POLICIES", "LineFieldPolicy", "validate_line_fact"]
