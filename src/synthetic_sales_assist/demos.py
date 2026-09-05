"""Closed synthetic demonstration catalog and CLI integration boundary.

The catalog is descriptive only.  Business execution is delegated to the durable
Sales Credit and DOI services through :class:`DemoAuditBackend`; the CLI never
re-implements rule behavior and never imports test modules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Protocol

from synthetic_sales_assist.safety.identity import is_reserved_identity


DEMO_CATALOG_VERSION: Final = "synthetic-sales-assist-demo-catalog/v1"
_REQUEST_KEY = re.compile(r"\A[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}\Z", re.ASCII)
_AUDIT_KEYS: Final = frozenset(
    {
        "case_id",
        "created_at",
        "attribution",
        "current_evaluation_id",
        "current_snapshot_id",
        "evaluation_id",
        "event_count",
        "event_id",
        "event_type",
        "after_sequence",
        "through_sequence",
        "through_event_id",
        "next_after_sequence",
        "returned_event_count",
        "has_more",
        "sequence",
        "found",
        "human_review_required",
        "opportunity_count",
        "order_id",
        "projection_version",
        "reason",
        "reason_count",
        "rule_pack",
        "run_id",
        "source_status",
        "state",
        "status",
        "terminal_closure_reason",
        "top_level_result",
        "transition_id",
        "updated_at",
        "value_status",
    }
)


class DemoError(RuntimeError):
    """Closed demo or audit-view failure without source payload material."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"synthetic demonstration rejected: {code}")


@dataclass(frozen=True, slots=True)
class DemoDescriptor:
    alias: str
    rule_pack: str
    description: str
    expected_result: str
    collected_scenario: str

    def to_dict(self) -> dict[str, str]:
        return {
            "alias": self.alias,
            "collected_scenario": self.collected_scenario,
            "description": self.description,
            "expected_result": self.expected_result,
            "rule_pack": self.rule_pack,
        }


_CATALOG: Final = (
    DemoDescriptor(
        "sales-credit-target-rep",
        "SALES_CREDIT",
        "Known exact order rep receives TARGET_REP credit.",
        "CREDIT_CONFIRMED_TARGET_REP",
        "milestone2_case_mutation",
    ),
    DemoDescriptor(
        "sales-credit-human-review",
        "SALES_CREDIT",
        "Unrecognized exact order rep fails closed to human review.",
        "MANUAL_REVIEW_REQUIRED",
        "REP_UNRECOGNIZED",
    ),
    DemoDescriptor(
        "doi-fulfillment-split",
        "DOI",
        "Known ordinary fulfillment split produces a DOI opportunity.",
        "DOI_OPPORTUNITY",
        "ORDINARY_FULFILLMENT_SPLIT",
    ),
    DemoDescriptor(
        "doi-full-ds",
        "DOI",
        "Known full direct-ship order is excluded by the full-DS rule.",
        "DOI_EXCLUDED",
        "FULL_DIRECT_SHIP",
    ),
    DemoDescriptor(
        "doi-manual-review",
        "DOI",
        "An unknown fact blocks the only candidate and requires review.",
        "DOI_MANUAL_REVIEW",
        "ONLY_CANDIDATE_BLOCKED_BY_UNKNOWN",
    ),
    DemoDescriptor(
        "doi-overlap",
        "DOI",
        "Valid overlapping opportunities remain separate pending selection.",
        "DOI_OPPORTUNITY",
        "OVERLAP_UNAVAILABLE_THEN_HUMAN_SELECTED",
    ),
    DemoDescriptor(
        "malformed-input",
        "DOI",
        "Malformed synthetic order input is rejected without durable business state.",
        "INVALID_INPUT",
        "INVALID_ORDER_NUMBER",
    ),
)


def demo_catalog() -> tuple[DemoDescriptor, ...]:
    """Return the stable required alias inventory in canonical alias order."""

    return tuple(sorted(_CATALOG, key=lambda item: item.alias))


def demo_descriptor(alias: str) -> DemoDescriptor:
    if type(alias) is not str:
        raise DemoError("DEMO_ALIAS_INVALID")
    for descriptor in _CATALOG:
        if descriptor.alias == alias:
            return descriptor
    raise DemoError("DEMO_ALIAS_UNKNOWN")


def validate_request_key(value: str | None) -> str | None:
    if value is None:
        return None
    if type(value) is not str or _REQUEST_KEY.fullmatch(value) is None:
        raise DemoError("REQUEST_KEY_INVALID")
    return value


@dataclass(frozen=True, slots=True)
class DemoRunView:
    """Closed privacy-safe result returned by a durable demo service."""

    scenario: str
    rule_pack: str
    synthetic_ids: tuple[str, ...]
    top_level_result: str
    workflow_state: str
    reasons: tuple[str, ...]
    opportunities: tuple[str, ...]
    human_review_required: bool
    run_id: str | None
    evaluation_id: str | None
    case_id: str | None
    exact_replay: bool
    conflict: bool
    processing_duration_ns: int

    def __post_init__(self) -> None:
        if self.scenario not in {item.alias for item in _CATALOG}:
            raise DemoError("DEMO_RESULT_SCENARIO_INVALID")
        descriptor = demo_descriptor(self.scenario)
        if self.rule_pack != descriptor.rule_pack:
            raise DemoError("DEMO_RESULT_RULE_PACK_INVALID")
        if (
            type(self.synthetic_ids) is not tuple
            or not self.synthetic_ids
            or any(not is_reserved_identity(item) for item in self.synthetic_ids)
        ):
            raise DemoError("DEMO_RESULT_IDENTIFIERS_INVALID")
        for value in (self.top_level_result, self.workflow_state):
            if type(value) is not str or not value or len(value) > 96:
                raise DemoError("DEMO_RESULT_STATE_INVALID")
        for values in (self.reasons, self.opportunities):
            if type(values) is not tuple or any(
                type(item) is not str or not item or len(item) > 128 for item in values
            ):
                raise DemoError("DEMO_RESULT_DETAILS_INVALID")
        for value in (self.human_review_required, self.exact_replay, self.conflict):
            if type(value) is not bool:
                raise DemoError("DEMO_RESULT_FLAGS_INVALID")
        identifiers = (self.run_id, self.evaluation_id, self.case_id)
        if any(
            item is not None
            and not is_reserved_identity(item)
            for item in identifiers
        ):
            raise DemoError("DEMO_RESULT_IDENTIFIERS_INVALID")
        if type(self.processing_duration_ns) is not int or self.processing_duration_ns < 0:
            raise DemoError("DEMO_RESULT_DURATION_INVALID")

    def to_dict(self, *, database_path: str) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "conflict": self.conflict,
            "database_path": database_path,
            "evaluation_id": self.evaluation_id,
            "exact_replay": self.exact_replay,
            "human_review_required": self.human_review_required,
            "opportunities": list(self.opportunities),
            "processing_duration_ns": self.processing_duration_ns,
            "reasons": list(self.reasons),
            "rule_pack": self.rule_pack,
            "run_id": self.run_id,
            "scenario": self.scenario,
            "synthetic_ids": list(self.synthetic_ids),
            "top_level_result": self.top_level_result,
            "workflow_state": self.workflow_state,
        }


@dataclass(frozen=True, slots=True)
class AuditView:
    """Closed fictional audit projection, never a raw database-row dump."""

    view_kind: str
    synthetic_id: str
    summary: tuple[tuple[str, str | int | bool | None], ...]
    events: tuple[tuple[tuple[str, str | int | bool | None], ...], ...] = ()

    def __post_init__(self) -> None:
        if self.view_kind not in {"ORDER", "CASE_HISTORY", "RUN"}:
            raise DemoError("AUDIT_VIEW_KIND_INVALID")
        if not is_reserved_identity(self.synthetic_id):
            raise DemoError("AUDIT_VIEW_ID_INVALID")
        if type(self.summary) is not tuple or type(self.events) is not tuple:
            raise DemoError("AUDIT_VIEW_INVALID")
        if len(self.summary) > len(_AUDIT_KEYS) or len(self.events) > 1_000:
            raise DemoError("AUDIT_VIEW_INVALID")
        for row in (self.summary, *self.events):
            if type(row) is not tuple or len(row) > len(_AUDIT_KEYS):
                raise DemoError("AUDIT_VIEW_INVALID")
            if any(type(item) is not tuple or len(item) != 2 for item in row):
                raise DemoError("AUDIT_VIEW_INVALID")
            keys = tuple(item[0] for item in row)
            if (
                len(keys) != len(set(keys))
                or tuple(sorted(keys)) != keys
                or any(key not in _AUDIT_KEYS for key in keys)
            ):
                raise DemoError("AUDIT_VIEW_FIELDS_INVALID")
            for _, value in row:
                if value is not None and type(value) not in {str, int, bool}:
                    raise DemoError("AUDIT_VIEW_VALUE_INVALID")
                if type(value) is str and (
                    not value.isascii()
                    or not value
                    or len(value) > 128
                    or "\n" in value
                    or "\r" in value
                ):
                    raise DemoError("AUDIT_VIEW_VALUE_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "events": [dict(event) for event in self.events],
            "summary": dict(self.summary),
            "synthetic_id": self.synthetic_id,
            "view_kind": self.view_kind,
        }


class DemoAuditBackend(Protocol):
    """Narrow durable-service adapter consumed by the local CLI."""

    def run_demo(self, alias: str, request_key: str | None) -> DemoRunView: ...

    def order_show(self, synthetic_order_id: str) -> AuditView: ...

    def case_history(
        self, synthetic_order_id: str, *, after_sequence: int = 0,
        through_sequence: int | None = None, limit: int = 1_000,
        through_event_id: str | None = None,
    ) -> AuditView: ...

    def run_show(self, synthetic_run_id: str) -> AuditView: ...


class UnavailableDemoAuditBackend:
    """Fail-closed default until durable service composition supplies an adapter."""

    @staticmethod
    def _unavailable() -> None:
        raise DemoError("DURABLE_DEMO_BACKEND_UNAVAILABLE")

    def run_demo(self, alias: str, request_key: str | None) -> DemoRunView:
        del alias, request_key
        self._unavailable()
        raise AssertionError("unreachable")

    def order_show(self, synthetic_order_id: str) -> AuditView:
        del synthetic_order_id
        self._unavailable()
        raise AssertionError("unreachable")

    def case_history(
        self, synthetic_order_id: str, *, after_sequence: int = 0,
        through_sequence: int | None = None, limit: int = 1_000,
        through_event_id: str | None = None,
    ) -> AuditView:
        del synthetic_order_id, after_sequence, through_sequence, limit, through_event_id
        self._unavailable()
        raise AssertionError("unreachable")

    def run_show(self, synthetic_run_id: str) -> AuditView:
        del synthetic_run_id
        self._unavailable()
        raise AssertionError("unreachable")


__all__ = [
    "DEMO_CATALOG_VERSION",
    "AuditView",
    "DemoAuditBackend",
    "DemoDescriptor",
    "DemoError",
    "DemoRunView",
    "UnavailableDemoAuditBackend",
    "demo_catalog",
    "demo_descriptor",
    "validate_request_key",
]
