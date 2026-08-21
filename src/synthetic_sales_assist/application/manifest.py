"""Published reconstructible line-manifest algorithm for local adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from synthetic_sales_assist.domain.canonical import canonical_json_bytes, domain_hash
from synthetic_sales_assist.safety.identity import is_reserved_identity

from .line_policy import LINE_FIELD_POLICIES, validate_line_fact
from .views import LineView


LINE_MANIFEST_SCHEMA_VERSION: Final = "synthetic-sales-assist-line-manifest/v1"
LINE_MANIFEST_DOMAIN: Final = "m5-rendered-line-manifest/v1"
_LINE_MEMBERS: Final = frozenset(
    {
        "activity",
        "availability",
        "drop_ship_state",
        "eta",
        "line_id",
        "line_index",
        "line_value",
        "product_id",
        "quantity",
    }
)
_FACT_FIELDS: Final = tuple(LINE_FIELD_POLICIES)


def ordered_line_manifest_digest_from_mappings(
    lines: Sequence[Mapping[str, object]],
) -> str:
    """Validate and hash an ordered sequence of exact public line mappings."""

    if isinstance(lines, (str, bytes, bytearray)) or not isinstance(lines, Sequence):
        raise TypeError("LINE_MANIFEST_INPUT_INVALID")
    closed: list[dict[str, object]] = []
    for expected_index, line in enumerate(lines, start=1):
        if not isinstance(line, Mapping) or set(line) != _LINE_MEMBERS:
            raise ValueError("LINE_MANIFEST_LINE_INVALID")
        if (
            type(line["line_id"]) is not str
            or not is_reserved_identity(line["line_id"])
            or type(line["product_id"]) is not str
            or not is_reserved_identity(line["product_id"], expected_namespace="SKU")
            or type(line["line_index"]) is not int
            or line["line_index"] != expected_index
        ):
            raise ValueError("LINE_MANIFEST_LINE_INVALID")
        normalized: dict[str, object] = {
            "line_id": line["line_id"],
            "line_index": expected_index,
            "product_id": line["product_id"],
        }
        normalized.update(
            {field: validate_line_fact(field, line[field]) for field in _FACT_FIELDS}
        )
        closed.append(normalized)
    material = canonical_json_bytes(
        {"lines": closed, "schema_version": LINE_MANIFEST_SCHEMA_VERSION},
        expected_members={"lines", "schema_version"},
    )
    return domain_hash(LINE_MANIFEST_DOMAIN, material).sha256


def ordered_line_manifest_digest(lines: tuple[LineView, ...]) -> str:
    """Hash the exact ordered, allowlisted line representation exposed to adapters."""

    if type(lines) is not tuple or any(type(line) is not LineView for line in lines):
        raise TypeError("LINE_MANIFEST_INPUT_INVALID")
    return ordered_line_manifest_digest_from_mappings(
        tuple(line.to_dict() for line in lines)
    )


__all__ = [
    "LINE_MANIFEST_DOMAIN",
    "LINE_MANIFEST_SCHEMA_VERSION",
    "ordered_line_manifest_digest",
    "ordered_line_manifest_digest_from_mappings",
]
