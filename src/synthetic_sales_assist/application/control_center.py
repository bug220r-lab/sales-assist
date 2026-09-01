"""Read-only, projection-first application boundary for the local Control Center.

This module deliberately owns no business transitions.  It reads only normalized current
projections, immutable event metadata, governed evaluation output bindings, and maintenance
receipts.  Raw retained payloads, canonical source facts, SQL text supplied by callers, and
filesystem paths never cross this boundary.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final, Generic, TypeVar, cast

from synthetic_sales_assist.application.views import (
    APPLICATION_BUILD_VERSION,
    APPLICATION_SCHEMA_VERSION,
)
from synthetic_sales_assist.benchmark import BENCHMARK_VERSION
from synthetic_sales_assist.doi.lifecycle import AttentionAction, AttentionEvent
from synthetic_sales_assist.domain.canonical import (
    CanonicalJsonViolation,
    HashDomainViolation,
    domain_hash,
    parse_canonical_json_bytes,
)
from synthetic_sales_assist.domain.numeric import Money, MoneyViolation
from synthetic_sales_assist.domain.registries import (
    RegistryLookupError,
    load_doi_registries,
)
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.persistence.database import SQLiteDatabase
from synthetic_sales_assist.persistence.doi_repository import (
    DOIPersistenceError,
    DOIRepository,
    decode_payload,
)
from synthetic_sales_assist.persistence.projections import verify_sales_credit_projections
from synthetic_sales_assist.persistence.schema import verify_database
from synthetic_sales_assist.persistence.telemetry import (
    SAFETY_COUNTER_NAMES,
)

from .control_center_actions import ControlCenterActions, ScenarioSelectionSource


CONTROL_CENTER_SCHEMA_VERSION: Final = "synthetic-sales-assist-control-center/v1"
DENOMINATOR_REGISTRY_VERSION: Final = (
    "synthetic-sales-assist-metric-denominators/v1"
)
EXTENSION_STATUS_SCHEMA_VERSION: Final = "synthetic-sales-assist-extension-status/v1"
DEFAULT_EXTENSION_STALE_AFTER: Final = timedelta(minutes=5)
M4_BENCHMARK_REFERENCE_VERSION: Final = BENCHMARK_VERSION

_SYNTHETIC_ID = re.compile(
    r"\ASYN-(?:ORDER|EVIDENCE|EVALUATION|RUN|SNAPSHOT)-[A-Z0-9][A-Z0-9-]{0,111}\Z",
    re.ASCII,
)
_FILTER_TOKEN = re.compile(r"\A[A-Z][A-Z0-9_]{0,63}\Z", re.ASCII)
_HEX_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z", re.ASCII)
_VERSION = re.compile(r"\A[0-9A-Za-z][0-9A-Za-z._/-]{0,63}\Z", re.ASCII)
_TRANSITION_ID = re.compile(r"\ATR-[0-9]{3}\Z", re.ASCII)
_DOI_EVALUATION_INPUT_MEMBERS: Final = frozenset(
    {
        "alternate_candidates",
        "alternate_research_state",
        "available_rule_pack_binding",
        "dedupe_history_projection",
        "dedupe_verification",
        "evaluated_at",
        "evaluation_id",
        "human_facts",
        "required_rule_pack",
        "scenario_selection",
        "schema_version",
        "snapshot",
    }
)
_DOI_OWNER_EVENT_ENVELOPE_MEMBERS: Final = frozenset(
    {
        "event_canonical_b64",
        "event_domain",
        "event_id",
        "event_payload_b64",
        "event_sha256",
        "occurred_at",
        "projected_state",
        "stream_family",
        "stream_id",
        "transition_id",
    }
)


@dataclass(frozen=True, slots=True)
class BenchmarkReference:
    version: str
    unique_evaluations: int
    exact_replays: int
    median_latency_ms: str
    p95_latency_ms: str
    throughput_per_second: str
    database_size_bytes: int
    verified_backup_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "database_size_bytes": self.database_size_bytes,
            "exact_replays": self.exact_replays,
            "median_latency_ms": self.median_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "throughput_per_second": self.throughput_per_second,
            "unique_evaluations": self.unique_evaluations,
            "verified_backup_sha256": self.verified_backup_sha256,
            "version": self.version,
        }


M4_BENCHMARK_REFERENCE: Final = BenchmarkReference(
    version=M4_BENCHMARK_REFERENCE_VERSION,
    unique_evaluations=1_000,
    exact_replays=100,
    median_latency_ms="226.490150",
    p95_latency_ms="545.652600",
    throughput_per_second="4.409734",
    database_size_bytes=78_577_664,
    verified_backup_sha256=(
        "d2b30ebd3dc7daad6ccec65b46f1e6836a6463e5669a89beee02c8fb37ed073d"
    ),
)


class ControlCenterError(RuntimeError):
    """Closed non-payload failure for read-only Control Center requests."""

    def __init__(self, code: str) -> None:
        if type(code) is not str or _FILTER_TOKEN.fullmatch(code) is None:
            raise ValueError("CONTROL_CENTER_ERROR_INVALID")
        self.code = code
        super().__init__(f"control center request rejected: {code}")


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    metric_id: str
    label: str
    numerator: str
    denominator: str | None
    inclusions: tuple[str, ...]
    exclusions: tuple[str, ...]
    time_basis: str
    empty_display: str

    def to_dict(self) -> dict[str, object]:
        return {
            "denominator": self.denominator,
            "empty_display": self.empty_display,
            "exclusions": list(self.exclusions),
            "inclusions": list(self.inclusions),
            "label": self.label,
            "metric_id": self.metric_id,
            "numerator": self.numerator,
            "time_basis": self.time_basis,
        }


METRIC_DENOMINATOR_REGISTRY: Final = (
    MetricDefinition(
        "requests_received",
        "Business requests received",
        "Terminal SALES_CREDIT and DOI processing-telemetry rows",
        None,
        ("Exact replays", "Conflicts", "Failed-closed requests"),
        ("SHARED maintenance operations",),
        "Telemetry ended_at in the selected half-open UTC window",
        "0",
    ),
    MetricDefinition(
        "unique_evaluations",
        "Unique new evaluations",
        "Distinct durable Sales Credit and DOI evaluation IDs",
        None,
        ("New durable evaluations",),
        ("Exact replays", "Conflicts", "Malformed requests without an evaluation"),
        "First durable evaluation occurrence in the selected half-open UTC window",
        "0",
    ),
    MetricDefinition(
        "successful_request_rate",
        "Successful request rate",
        "Terminal business requests classified SUCCESS or HUMAN_REVIEW",
        "All terminal business requests",
        ("Exact replays, reported separately",),
        ("SHARED maintenance operations",),
        "Telemetry ended_at in the selected half-open UTC window",
        "N/A",
    ),
    MetricDefinition(
        "fail_closed_rate",
        "Fail-closed rate",
        "Terminal business requests with fail_closed = true",
        "All terminal business requests",
        (),
        ("SHARED maintenance operations",),
        "Telemetry ended_at in the selected half-open UTC window",
        "N/A",
    ),
    MetricDefinition(
        "human_review_rate",
        "Human-review rate",
        "New evaluations whose durable result requires human review",
        "New unique evaluations",
        (),
        ("Exact replays", "Conflicts"),
        "First durable evaluation occurrence in the selected half-open UTC window",
        "N/A",
    ),
    MetricDefinition(
        "active_sales_credit_cases",
        "Active Sales Credit cases",
        "Current nonclosed Sales Credit projections",
        None,
        (),
        ("Closed and purged cases",),
        "Current projection at query time",
        "0",
    ),
    MetricDefinition(
        "manager_outcome_rate",
        "Manager-outcome rate",
        "Eligible Sales Credit cases with a recorded manager outcome",
        "Sales Credit cases presented for a human decision",
        (),
        ("Cases never presented for a human decision",),
        "Durable evaluation and outcome history in the selected window",
        "N/A",
    ),
    MetricDefinition(
        "active_doi_opportunities",
        "Active DOI opportunities",
        "Opportunities attached to each active case's current evaluation",
        None,
        (),
        ("Closed, superseded, invalidated, and purged opportunities",),
        "Current projection at query time",
        "0",
    ),
    MetricDefinition(
        "doi_state_distribution",
        "DOI state distribution",
        "Active DOI cases in each current top-level state",
        "All active DOI case projections with a current evaluation",
        (),
        ("Closed and purged cases",),
        "Current projection at query time",
        "N/A",
    ),
    MetricDefinition(
        "opportunity_type_count",
        "Opportunity type count",
        "Current active opportunities grouped by type",
        None,
        ("Multiple opportunities may belong to one case",),
        ("Opportunities outside the current active evaluation",),
        "Current projection at query time",
        "0",
    ),
    MetricDefinition(
        "latency",
        "Processing latency",
        "Median and nearest-rank P95 total_ns",
        "Terminal business telemetry sample",
        ("Exact replays, broken out separately",),
        ("SHARED maintenance operations",),
        "Telemetry ended_at in the selected half-open UTC window",
        "N/A",
    ),
    MetricDefinition(
        "throughput",
        "Business throughput",
        "Terminal business request count per elapsed wall-clock second",
        "Elapsed time from earliest start to latest end",
        ("Exact replays, reported separately",),
        ("SHARED maintenance operations",),
        "Telemetry timestamps in the selected half-open UTC window",
        "N/A",
    ),
    MetricDefinition(
        "potential_value",
        "Current exact potential value",
        "Current active evaluation aggregate potential, grouped by currency binding",
        None,
        ("Exact AVAILABLE aggregates",),
        ("Unavailable values", "Unresolved overlap", "Mixed-currency combination"),
        "Current projection at query time",
        "Unavailable",
    ),
    MetricDefinition(
        "realized_value",
        "Current verified realized value",
        "Current retained KPI contributions, grouped by currency binding",
        None,
        ("Verified contribution after corrections and reversals",),
        ("Unverified interventions",),
        "Current retained contribution projection at query time",
        "0",
    ),
    MetricDefinition(
        "backup_database_safety_status",
        "Backup, database, and safety status",
        "Latest durable receipts and current verification results",
        None,
        (),
        ("Unverified filesystem artifacts",),
        "Latest receipt and query timestamps",
        "N/A",
    ),
)


def denominator_registry() -> dict[str, object]:
    """Return the stable machine-readable denominator registry."""

    return {
        "metrics": [item.to_dict() for item in METRIC_DENOMINATOR_REGISTRY],
        "schema_version": DENOMINATOR_REGISTRY_VERSION,
    }


@dataclass(frozen=True, slots=True)
class MetricWindow:
    start_utc: str | None = None
    end_utc: str | None = None

    def __post_init__(self) -> None:
        start = None if self.start_utc is None else CanonicalTimestamp(self.start_utc)
        end = None if self.end_utc is None else CanonicalTimestamp(self.end_utc)
        if start is not None and end is not None and (
            start.epoch_seconds,
            start.nanosecond,
        ) >= (end.epoch_seconds, end.nanosecond):
            raise ControlCenterError("METRIC_WINDOW_INVALID")

    @property
    def label(self) -> str:
        if self.start_utc is None and self.end_utc is None:
            return "ALL_DURABLE_HISTORY"
        return f"[{self.start_utc or '-infinity'}, {self.end_utc or '+infinity'})"


@dataclass(frozen=True, slots=True)
class PageRequest:
    search: str | None = None
    state: str | None = None
    sort_by: str = "updated_at"
    descending: bool = True
    offset: int = 0
    limit: int = 25

    def __post_init__(self) -> None:
        if self.search is not None and (
            type(self.search) is not str
            or not 1 <= len(self.search) <= 96
            or any(ord(character) < 32 for character in self.search)
        ):
            raise ControlCenterError("SEARCH_INVALID")
        if self.state is not None and (
            type(self.state) is not str or _FILTER_TOKEN.fullmatch(self.state) is None
        ):
            raise ControlCenterError("FILTER_INVALID")
        if type(self.sort_by) is not str or not self.sort_by:
            raise ControlCenterError("SORT_INVALID")
        if type(self.descending) is not bool:
            raise ControlCenterError("SORT_INVALID")
        if (
            type(self.offset) is not int
            or type(self.limit) is not int
            or self.offset < 0
            or not 1 <= self.limit <= 100
        ):
            raise ControlCenterError("PAGE_INVALID")


_ItemT = TypeVar("_ItemT")


@dataclass(frozen=True, slots=True)
class Page(Generic[_ItemT]):
    items: tuple[_ItemT, ...]
    total_count: int
    offset: int
    limit: int

    def __post_init__(self) -> None:
        if self.total_count < 0 or self.offset < 0 or not 1 <= self.limit <= 100:
            raise ControlCenterError("PAGE_INVALID")


@dataclass(frozen=True, slots=True)
class SalesCreditCaseSummary:
    order_id: str
    workflow_state: str
    attribution: str
    order_value_status: str
    human_review_required: bool
    unresolved_human_review: bool
    interaction_count: int
    updated_at: str
    manager_outcome: str | None
    current_evaluation_id: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "attribution": self.attribution,
            "current_evaluation_id": self.current_evaluation_id,
            "human_review_required": self.human_review_required,
            "interaction_count": self.interaction_count,
            "manager_outcome": self.manager_outcome,
            "order_id": self.order_id,
            "order_value_status": self.order_value_status,
            "unresolved_human_review": self.unresolved_human_review,
            "updated_at": self.updated_at,
            "workflow_state": self.workflow_state,
        }


@dataclass(frozen=True, slots=True)
class DOICaseSummary:
    case_id: str
    order_id: str
    lifecycle_state: str
    doi_state: str | None
    opportunity_types: tuple[str, ...]
    reason_codes: tuple[str, ...]
    aggregate_potential_state: str
    scenario_selection_state: str
    attention_causes: tuple[str, ...]
    human_review_required: bool
    updated_at: str
    current_evaluation_id: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "aggregate_potential_state": self.aggregate_potential_state,
            "attention_causes": list(self.attention_causes),
            "case_id": self.case_id,
            "current_evaluation_id": self.current_evaluation_id,
            "doi_state": self.doi_state,
            "human_review_required": self.human_review_required,
            "lifecycle_state": self.lifecycle_state,
            "opportunity_types": list(self.opportunity_types),
            "order_id": self.order_id,
            "reason_codes": list(self.reason_codes),
            "scenario_selection_state": self.scenario_selection_state,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class HumanReviewItem:
    domain: str
    subject_id: str
    order_id: str
    reason_codes: tuple[str, ...]
    system_state: str
    source_completeness_state: str
    required_action: str
    action_available: bool
    audit_subject_kind: str

    def to_dict(self) -> dict[str, object]:
        return {
            "action_available": self.action_available,
            "audit_subject_kind": self.audit_subject_kind,
            "domain": self.domain,
            "order_id": self.order_id,
            "reason_codes": list(self.reason_codes),
            "required_action": self.required_action,
            "source_completeness_state": self.source_completeness_state,
            "subject_id": self.subject_id,
            "system_state": self.system_state,
        }


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    sequence: int
    event_id: str
    event_kind: str
    state: str
    occurred_at: str
    transition_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "event_kind": self.event_kind,
            "occurred_at": self.occurred_at,
            "sequence": self.sequence,
            "state": self.state,
            "transition_id": self.transition_id,
        }


@dataclass(frozen=True, slots=True)
class CurrencyTotal:
    currency_code: str
    currency_registry_version: str
    currency_scale: int
    amount_minor_units: int
    item_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "amount_minor_units": self.amount_minor_units,
            "currency_code": self.currency_code,
            "currency_registry_version": self.currency_registry_version,
            "currency_scale": self.currency_scale,
            "item_count": self.item_count,
        }


@dataclass(frozen=True, slots=True)
class RateValue:
    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if (
            self.numerator < 0
            or self.denominator < 0
            or self.numerator > self.denominator
        ):
            raise ControlCenterError("METRIC_RATE_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "defined": self.denominator > 0,
            "display": (
                "N/A"
                if self.denominator == 0
                else f"{self.numerator / self.denominator:.1%}"
            ),
            "denominator": self.denominator,
            "numerator": self.numerator,
        }


@dataclass(frozen=True, slots=True)
class ProjectionReconciliation:
    active_sales_credit_cases: int
    sales_credit_history_events: int
    active_doi_cases: int
    doi_history_events: int
    current_human_review_items: int
    unique_evaluations: int
    exact_replays: int
    material_conflicts: int

    def to_dict(self) -> dict[str, int]:
        return {
            "active_doi_cases": self.active_doi_cases,
            "active_sales_credit_cases": self.active_sales_credit_cases,
            "current_human_review_items": self.current_human_review_items,
            "doi_history_events": self.doi_history_events,
            "exact_replays": self.exact_replays,
            "material_conflicts": self.material_conflicts,
            "sales_credit_history_events": self.sales_credit_history_events,
            "unique_evaluations": self.unique_evaluations,
        }


@dataclass(frozen=True, slots=True)
class DashboardMetrics:
    window: str
    requests_received: int
    unique_evaluations: int
    exact_replays: int
    material_conflicts: int
    successful_requests: int
    failed_closed_requests: int
    database_error_count: int
    successful_request_rate: RateValue
    failed_closed_rate: RateValue
    human_review_rate: RateValue
    manager_outcome_rate: RateValue
    active_sales_credit_cases: int
    active_doi_cases: int
    active_doi_opportunities: int
    current_human_review_items: int
    doi_state_distribution: tuple[tuple[str, int], ...]
    request_result_distribution: tuple[tuple[str, int], ...]
    sales_credit_result_distribution: tuple[tuple[str, int], ...]
    doi_evaluation_result_distribution: tuple[tuple[str, int], ...]
    opportunity_type_counts: tuple[tuple[str, int], ...]
    median_latency_ns: int | None
    p95_latency_ns: int | None
    throughput_per_second: str | None
    potential_by_currency: tuple[CurrencyTotal, ...]
    potential_unavailable_count: int
    unresolved_overlap_count: int
    realized_by_currency: tuple[CurrencyTotal, ...]
    safety_counters: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "active_doi_cases": self.active_doi_cases,
            "active_doi_opportunities": self.active_doi_opportunities,
            "active_sales_credit_cases": self.active_sales_credit_cases,
            "current_human_review_items": self.current_human_review_items,
            "database_error_count": self.database_error_count,
            "doi_evaluation_result_distribution": dict(
                self.doi_evaluation_result_distribution
            ),
            "doi_state_distribution": dict(self.doi_state_distribution),
            "exact_replays": self.exact_replays,
            "failed_closed_rate": self.failed_closed_rate.to_dict(),
            "failed_closed_requests": self.failed_closed_requests,
            "human_review_rate": self.human_review_rate.to_dict(),
            "manager_outcome_rate": self.manager_outcome_rate.to_dict(),
            "material_conflicts": self.material_conflicts,
            "median_latency_ns": self.median_latency_ns,
            "opportunity_type_counts": dict(self.opportunity_type_counts),
            "p95_latency_ns": self.p95_latency_ns,
            "potential_by_currency": [item.to_dict() for item in self.potential_by_currency],
            "potential_unavailable_count": self.potential_unavailable_count,
            "realized_by_currency": [item.to_dict() for item in self.realized_by_currency],
            "request_result_distribution": dict(self.request_result_distribution),
            "requests_received": self.requests_received,
            "safety_counters": dict(self.safety_counters),
            "schema_version": DENOMINATOR_REGISTRY_VERSION,
            "successful_request_rate": self.successful_request_rate.to_dict(),
            "successful_requests": self.successful_requests,
            "sales_credit_result_distribution": dict(
                self.sales_credit_result_distribution
            ),
            "throughput_per_second": self.throughput_per_second,
            "unique_evaluations": self.unique_evaluations,
            "unresolved_overlap_count": self.unresolved_overlap_count,
            "window": self.window,
        }


class ExtensionStatusState:
    EXPECTED_PACKAGE_ONLY: Final = "EXPECTED_PACKAGE_ONLY"
    LAST_SEEN_HEALTHY: Final = "LAST_SEEN_HEALTHY"
    LAST_SEEN_STALE: Final = "LAST_SEEN_STALE"
    VERSION_MISMATCH: Final = "VERSION_MISMATCH"
    UNKNOWN: Final = "UNKNOWN"

    ALL: Final = frozenset(
        {
            EXPECTED_PACKAGE_ONLY,
            LAST_SEEN_HEALTHY,
            LAST_SEEN_STALE,
            VERSION_MISMATCH,
            UNKNOWN,
        }
    )


@dataclass(frozen=True, slots=True)
class ExtensionObservation:
    version: str
    last_seen_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.version) is not str
            or _VERSION.fullmatch(self.version) is None
            or type(self.last_seen_at) is not datetime
            or self.last_seen_at.tzinfo is None
        ):
            raise ControlCenterError("EXTENSION_OBSERVATION_INVALID")


@dataclass(frozen=True, slots=True)
class ExtensionStatus:
    state: str
    expected_version: str
    expected_package_sha256: str
    last_seen_at: str | None
    observed_version: str | None
    stale_after_seconds: int

    def __post_init__(self) -> None:
        if self.state not in ExtensionStatusState.ALL:
            raise ControlCenterError("EXTENSION_STATUS_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "expected_package_sha256": self.expected_package_sha256,
            "expected_version": self.expected_version,
            "last_seen_at": self.last_seen_at,
            "observed_version": self.observed_version,
            "schema_version": EXTENSION_STATUS_SCHEMA_VERSION,
            "stale_after_seconds": self.stale_after_seconds,
            "state": self.state,
        }


def classify_extension_status(
    *,
    expected_version: str,
    expected_package_sha256: str,
    package_available: bool,
    observation: ExtensionObservation | None,
    now: datetime,
    stale_after: timedelta = DEFAULT_EXTENSION_STALE_AFTER,
) -> ExtensionStatus:
    """Classify evidence without equating package presence with installation."""

    if (
        type(expected_version) is not str
        or _VERSION.fullmatch(expected_version) is None
        or type(expected_package_sha256) is not str
        or _HEX_SHA256.fullmatch(expected_package_sha256) is None
        or type(package_available) is not bool
        or type(now) is not datetime
        or now.tzinfo is None
        or type(stale_after) is not timedelta
        or stale_after <= timedelta(0)
        or stale_after > timedelta(days=1)
    ):
        raise ControlCenterError("EXTENSION_STATUS_INPUT_INVALID")
    now_utc = now.astimezone(timezone.utc)
    if observation is None:
        state = (
            ExtensionStatusState.EXPECTED_PACKAGE_ONLY
            if package_available
            else ExtensionStatusState.UNKNOWN
        )
        return ExtensionStatus(
            state,
            expected_version,
            expected_package_sha256,
            None,
            None,
            int(stale_after.total_seconds()),
        )
    seen = observation.last_seen_at.astimezone(timezone.utc)
    if seen > now_utc + timedelta(seconds=5):
        raise ControlCenterError("EXTENSION_OBSERVATION_INVALID")
    if observation.version != expected_version:
        state = ExtensionStatusState.VERSION_MISMATCH
    elif now_utc - seen <= stale_after:
        state = ExtensionStatusState.LAST_SEEN_HEALTHY
    else:
        state = ExtensionStatusState.LAST_SEEN_STALE
    return ExtensionStatus(
        state,
        expected_version,
        expected_package_sha256,
        seen.isoformat().replace("+00:00", "Z"),
        observation.version,
        int(stale_after.total_seconds()),
    )


@dataclass(frozen=True, slots=True)
class BackupSummary:
    backup_id: str
    completed_at: str | None
    schema_version: int
    backup_sha256: str | None
    status: str
    quick_check: str
    foreign_key_check: str

    def to_dict(self) -> dict[str, object]:
        return {
            "backup_id": self.backup_id,
            "backup_sha256": self.backup_sha256,
            "completed_at": self.completed_at,
            "foreign_key_check": self.foreign_key_check,
            "quick_check": self.quick_check,
            "schema_version": self.schema_version,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class RestoreSummary:
    restore_id: str
    completed_at: str | None
    backup_sha256: str
    pre_restore_backup_id: str | None
    schema_version: int | None
    status: str
    error_code: str | None

    def __post_init__(self) -> None:
        if (
            _SYNTHETIC_ID.fullmatch(self.restore_id) is None
            or _HEX_SHA256.fullmatch(self.backup_sha256) is None
            or (
                self.pre_restore_backup_id is not None
                and _SYNTHETIC_ID.fullmatch(self.pre_restore_backup_id) is None
            )
            or self.status not in {"STARTED", "COMPLETED", "FAILED"}
            or (
                self.schema_version is not None
                and (
                    type(self.schema_version) is not int
                    or self.schema_version <= 0
                )
            )
            or (
                self.error_code is not None
                and _FILTER_TOKEN.fullmatch(self.error_code) is None
            )
        ):
            raise ControlCenterError("RESTORE_RECEIPT_INVALID")
        if self.completed_at is not None:
            CanonicalTimestamp.from_sqlite_text(self.completed_at)

    def to_dict(self) -> dict[str, object]:
        return {
            "backup_sha256": self.backup_sha256,
            "completed_at": self.completed_at,
            "error_code": self.error_code,
            "pre_restore_backup_id": self.pre_restore_backup_id,
            "restore_id": self.restore_id,
            "schema_version": self.schema_version,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class SafeErrorSummary:
    code: str
    category: str
    retryable: bool
    occurred_at: str

    def __post_init__(self) -> None:
        categories = {
            "COLLISION",
            "CONFLICT",
            "DATABASE",
            "PRIVACY",
            "VALIDATION",
            "VERSION",
        }
        if (
            _FILTER_TOKEN.fullmatch(self.code) is None
            or self.category not in categories
            or type(self.retryable) is not bool
        ):
            raise ControlCenterError("SAFE_ERROR_INVALID")
        CanonicalTimestamp.from_sqlite_text(self.occurred_at)

    def to_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "code": self.code,
            "occurred_at": self.occurred_at,
            "retryable": self.retryable,
        }


@dataclass(frozen=True, slots=True)
class SystemDatabaseStatus:
    application_schema_version: str
    build_version: str
    schema_version: int
    database_status: str
    quick_check: str
    integrity_check: str
    foreign_key_status: str
    projection_status: str
    database_location_class: str
    database_size_bytes: int
    migrations: tuple[tuple[int, str, str, str], ...]
    latest_backup: BackupSummary | None
    latest_restore: RestoreSummary | None
    verification_observed_at: str
    safety_observed_at: str
    safety_counters: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "application_schema_version": self.application_schema_version,
            "build_version": self.build_version,
            "database_location_class": self.database_location_class,
            "database_size_bytes": self.database_size_bytes,
            "database_status": self.database_status,
            "foreign_key_status": self.foreign_key_status,
            "integrity_check": self.integrity_check,
            "latest_backup": (
                None if self.latest_backup is None else self.latest_backup.to_dict()
            ),
            "latest_restore": (
                None if self.latest_restore is None else self.latest_restore.to_dict()
            ),
            "migrations": [
                {
                    "applied_at_utc": applied_at,
                    "name": name,
                    "sha256": sha256,
                    "version": version,
                }
                for version, name, sha256, applied_at in self.migrations
            ],
            "projection_status": self.projection_status,
            "quick_check": self.quick_check,
            "safety_observed_at": self.safety_observed_at,
            "safety_counters": dict(self.safety_counters),
            "schema_version": self.schema_version,
            "verification_observed_at": self.verification_observed_at,
        }


def privacy_safe_path_class(path: Path, *, repository_root: Path | None = None) -> str:
    """Classify a local path without returning user-bearing path material."""

    resolved = path.resolve(strict=False)
    if repository_root is not None:
        root = repository_root.resolve(strict=True)
        if resolved.is_relative_to(root):
            return "REPOSITORY_LOCAL"
    lowered = tuple(part.lower() for part in resolved.parts)
    if "appdata" in lowered and "local" in lowered:
        return "LOCAL_APPLICATION_DATA"
    if "temp" in lowered or "tmp" in lowered:
        return "LOCAL_TEMPORARY"
    return "LOCAL_FILESYSTEM"


_DOI_OUTPUT_MEMBERS: Final = frozenset(
    {
        "aggregate_potential",
        "aggregate_potential_state",
        "append_transitions",
        "closure_proposal",
        "explanation",
        "handling_flags",
        "human_review_requirements",
        "opportunities",
        "reason_routes",
        "reasons",
        "scenario_selection_state",
        "state",
        "transition",
    }
)


def _doi_output_facts(
    value: object,
) -> tuple[str, str, bool, Money | None, tuple[str, ...]]:
    try:
        raw = bytes(value)
        decoded = json.loads(raw.decode("utf-8"))
    except (TypeError, UnicodeError, ValueError):
        raise ControlCenterError("DOI_OUTPUT_BINDING_INVALID") from None
    if type(decoded) is not dict or frozenset(decoded) != _DOI_OUTPUT_MEMBERS:
        raise ControlCenterError("DOI_OUTPUT_BINDING_INVALID")
    body = cast(dict[str, object], decoded)
    aggregate_state = body["aggregate_potential_state"]
    selection_state = body["scenario_selection_state"]
    reviews = body["human_review_requirements"]
    flags = body["handling_flags"]
    if (
        type(aggregate_state) is not str
        or aggregate_state not in {"AVAILABLE", "UNAVAILABLE"}
        or type(selection_state) is not str
        or selection_state not in {"NOT_REQUIRED", "REQUIRED", "SELECTED"}
        or type(reviews) is not list
        or any(type(item) is not str or _FILTER_TOKEN.fullmatch(item) is None for item in reviews)
        or type(flags) is not list
        or any(type(item) is not str or _FILTER_TOKEN.fullmatch(item) is None for item in flags)
        or len(flags) != len(set(flags))
    ):
        raise ControlCenterError("DOI_OUTPUT_BINDING_INVALID")
    potential: Money | None = None
    if aggregate_state == "AVAILABLE":
        try:
            potential = Money.from_json_value(body["aggregate_potential"])
        except MoneyViolation:
            raise ControlCenterError("DOI_OUTPUT_BINDING_INVALID") from None
    elif body["aggregate_potential"] is not None:
        raise ControlCenterError("DOI_OUTPUT_BINDING_INVALID")
    return (
        str(aggregate_state),
        str(selection_state),
        bool(reviews),
        potential,
        tuple(sorted(cast(list[str], flags))),
    )


def _doi_reason_explanations(
    reason_codes: tuple[str, ...],
) -> list[dict[str, str]]:
    try:
        registries = load_doi_registries()
        result: list[dict[str, str]] = []
        for code in reason_codes:
            ref = registries.reason_ref(code)
            record = registries.reason_record(ref)
            reason_id = record["reason_id"]
            label = record["label"]
            reason_class = record["class"]
            description = record["description"]
            if (
                reason_id != ref.code
                or label != ref.label
                or type(reason_class) is not str
                or type(description) is not str
            ):
                raise RegistryLookupError
            result.append(
                {
                    "class": reason_class,
                    "code": ref.code,
                    "description": description,
                    "label": ref.label,
                    "registry_version": ref.registry_version,
                }
            )
        return result
    except (KeyError, RegistryLookupError, TypeError):
        raise ControlCenterError("DOI_REASON_REGISTRY_MISMATCH") from None


def _closed_hash_binding(value: object) -> dict[str, str]:
    if type(value) is not dict or frozenset(value) != {"domain", "sha256"}:
        raise ControlCenterError("DOI_EVALUATION_INPUT_INVALID")
    body = cast(dict[str, object], value)
    domain = body["domain"]
    sha256 = body["sha256"]
    if (
        type(domain) is not str
        or _VERSION.fullmatch(domain) is None
        or type(sha256) is not str
        or _HEX_SHA256.fullmatch(sha256) is None
    ):
        raise ControlCenterError("DOI_EVALUATION_INPUT_INVALID")
    return {"domain": domain, "sha256": sha256}


def _scenario_selection_from_input(
    raw: bytes,
    *,
    evaluation_id: str,
    opportunity_ids: tuple[str, ...],
    selection_state: str,
) -> dict[str, object] | None:
    try:
        decoded = parse_canonical_json_bytes(
            raw,
            expected_members=_DOI_EVALUATION_INPUT_MEMBERS,
        )
    except CanonicalJsonViolation:
        raise ControlCenterError("DOI_EVALUATION_INPUT_INVALID") from None
    if type(decoded) is not dict:
        raise ControlCenterError("DOI_EVALUATION_INPUT_INVALID")
    body = cast(dict[str, object], decoded)
    try:
        CanonicalTimestamp(cast(str, body["evaluated_at"]))
    except (TypeError, ValueError):
        raise ControlCenterError("DOI_EVALUATION_INPUT_INVALID") from None
    if (
        body["evaluation_id"] != evaluation_id
        or body["schema_version"] != "synthetic-doi-models/v1"
        or type(body["alternate_research_state"]) is not str
        or _FILTER_TOKEN.fullmatch(cast(str, body["alternate_research_state"])) is None
        or type(body["alternate_candidates"]) is not list
        or type(body["human_facts"]) is not list
    ):
        raise ControlCenterError("DOI_EVALUATION_INPUT_INVALID")
    bindings = (
        cast(list[object], body["alternate_candidates"])
        + cast(list[object], body["human_facts"])
    )
    for binding in bindings:
        _closed_hash_binding(binding)
    for optional_name in (
        "available_rule_pack_binding",
        "dedupe_history_projection",
        "dedupe_verification",
    ):
        optional = body[optional_name]
        if optional is not None:
            _closed_hash_binding(optional)
    _closed_hash_binding(body["snapshot"])
    required = body["required_rule_pack"]
    if (
        type(required) is not dict
        or frozenset(required) != {"component", "version"}
        or required["component"] != "rule_pack"
        or type(required["version"]) is not str
        or _VERSION.fullmatch(cast(str, required["version"])) is None
    ):
        raise ControlCenterError("DOI_EVALUATION_INPUT_INVALID")
    raw_selection = body["scenario_selection"]
    if raw_selection is None:
        if selection_state == "SELECTED":
            raise ControlCenterError("DOI_SCENARIO_SELECTION_BINDING_INVALID")
        return None
    if (
        selection_state != "SELECTED"
        or type(raw_selection) is not dict
        or frozenset(raw_selection)
        != {
            "human_fact_binding",
            "option_opportunity_ids",
            "selected_opportunity_id",
            "selection_id",
        }
    ):
        raise ControlCenterError("DOI_SCENARIO_SELECTION_BINDING_INVALID")
    selection = cast(dict[str, object], raw_selection)
    human_binding = _closed_hash_binding(selection["human_fact_binding"])
    if human_binding not in cast(list[object], body["human_facts"]):
        raise ControlCenterError("DOI_SCENARIO_SELECTION_BINDING_INVALID")
    selection_id = selection["selection_id"]
    selected_id = selection["selected_opportunity_id"]
    options = selection["option_opportunity_ids"]
    if (
        type(selection_id) is not str
        or _SYNTHETIC_ID.fullmatch(selection_id) is None
        or type(selected_id) is not str
        or _SYNTHETIC_ID.fullmatch(selected_id) is None
        or type(options) is not list
        or any(
            type(item) is not str or _SYNTHETIC_ID.fullmatch(item) is None
            for item in options
        )
    ):
        raise ControlCenterError("DOI_SCENARIO_SELECTION_BINDING_INVALID")
    option_values = tuple(cast(list[str], options))
    normalized_universe = tuple(sorted(opportunity_ids))
    if (
        len(option_values) < 2
        or option_values != tuple(sorted(set(option_values)))
        or selected_id not in option_values
        or option_values != normalized_universe
    ):
        raise ControlCenterError("DOI_SCENARIO_SELECTION_BINDING_INVALID")
    return {
        "option_opportunity_ids": list(option_values),
        "selected_opportunity_id": selected_id,
        "selection_id": selection_id,
    }


def _decode_current_attention_cause(
    row: sqlite3.Row | tuple[object, ...],
    *,
    case_id: str,
) -> dict[str, object]:
    """Verify and expose the governed identity of one current SET attention head."""

    try:
        (
            stream_id,
            current_state,
            sequence,
            head_sha256,
            event_id,
            occurred_at,
            transition_id,
            record_domain,
            record_sha256,
            record_canonical_bytes,
            record_payload,
        ) = row
        canonical = bytes(record_canonical_bytes)
        retained_payload = bytes(record_payload)
    except (TypeError, ValueError):
        raise ControlCenterError("DOI_ATTENTION_BINDING_INVALID") from None
    if (
        type(stream_id) is not str
        or _SYNTHETIC_ID.fullmatch(stream_id) is None
        or current_state != "SET"
        or type(sequence) is not int
        or sequence < 1
        or type(head_sha256) is not str
        or _HEX_SHA256.fullmatch(head_sha256) is None
        or type(event_id) is not str
        or _SYNTHETIC_ID.fullmatch(event_id) is None
        or type(occurred_at) is not str
        or type(transition_id) is not str
        or _TRANSITION_ID.fullmatch(transition_id) is None
        or record_domain != "doi-owner-event-envelope/v1"
        or type(record_sha256) is not str
        or _HEX_SHA256.fullmatch(record_sha256) is None
        or record_sha256 != head_sha256
        or canonical != retained_payload
    ):
        raise ControlCenterError("DOI_ATTENTION_BINDING_INVALID")
    try:
        CanonicalTimestamp(occurred_at)
        if domain_hash(record_domain, canonical).sha256 != record_sha256:
            raise ControlCenterError("DOI_ATTENTION_BINDING_INVALID")
        decoded = parse_canonical_json_bytes(
            canonical,
            expected_members=_DOI_OWNER_EVENT_ENVELOPE_MEMBERS,
        )
    except (CanonicalJsonViolation, HashDomainViolation, TypeError, ValueError):
        raise ControlCenterError("DOI_ATTENTION_BINDING_INVALID") from None
    if type(decoded) is not dict:
        raise ControlCenterError("DOI_ATTENTION_BINDING_INVALID")
    envelope = cast(dict[str, object], decoded)
    event_domain = envelope["event_domain"]
    event_sha256 = envelope["event_sha256"]
    if (
        envelope["event_id"] != event_id
        or envelope["occurred_at"] != occurred_at
        or envelope["projected_state"] != "SET"
        or envelope["stream_family"] != "ATTENTION"
        or envelope["stream_id"] != stream_id
        or envelope["transition_id"] != transition_id
        or event_domain != AttentionEvent.HASH_DOMAIN
        or type(event_sha256) is not str
        or _HEX_SHA256.fullmatch(event_sha256) is None
        or type(envelope["event_canonical_b64"]) is not str
        or type(envelope["event_payload_b64"]) is not str
    ):
        raise ControlCenterError("DOI_ATTENTION_BINDING_INVALID")
    try:
        event_canonical = base64.b64decode(
            cast(str, envelope["event_canonical_b64"]),
            validate=True,
        )
        event_payload = base64.b64decode(
            cast(str, envelope["event_payload_b64"]),
            validate=True,
        )
        event = decode_payload(event_payload, AttentionEvent)
        binding = event.hash_binding()
    except (binascii.Error, DOIPersistenceError, HashDomainViolation, ValueError):
        raise ControlCenterError("DOI_ATTENTION_BINDING_INVALID") from None
    if (
        binding.domain != event_domain
        or binding.sha256 != event_sha256
        or binding.canonical_bytes != event_canonical
        or event.canonical_bytes() != event_canonical
        or event.event_id.value != event_id
        or event.case_id.value != case_id
        or event.action is not AttentionAction.SET
        or event.occurred_at.value != occurred_at
        or event.transition.transition_id != transition_id
    ):
        raise ControlCenterError("DOI_ATTENTION_BINDING_INVALID")
    return {
        "cause_key": event.cause_key.value,
        "condition": event.condition.value,
        "current_event_id": event_id,
        "current_event_occurred_at": occurred_at,
        "head_sha256": head_sha256,
        "projection_state": "SET",
        "record_domain": record_domain,
        "record_sha256": record_sha256,
        "sequence": sequence,
        "stream_id": stream_id,
    }


def _current_attention_causes(
    connection: sqlite3.Connection,
    *,
    case_id: str,
) -> list[dict[str, object]]:
    rows = connection.execute(
        "SELECT s.stream_id, s.current_state, s.sequence_no, s.head_sha256, "
        "e.event_id, e.occurred_at, e.transition_id, e.record_domain, "
        "e.record_sha256, e.record_canonical_bytes, e.record_payload "
        "FROM doi_owner_streams s JOIN doi_owner_events e "
        "ON e.stream_family=s.stream_family AND e.stream_id=s.stream_id "
        "AND e.sequence_no=s.sequence_no "
        "WHERE s.case_id=? AND s.stream_family='ATTENTION' "
        "AND s.current_state='SET' ORDER BY s.stream_id",
        (case_id,),
    ).fetchall()
    result = [
        _decode_current_attention_cause(row, case_id=case_id)
        for row in rows
    ]
    result.sort(
        key=lambda item: (
            str(item["condition"]),
            str(item["cause_key"]),
            str(item["stream_id"]),
        )
    )
    return result


def _window_clause(window: MetricWindow, column: str) -> tuple[str, list[object]]:
    clauses: list[str] = []
    parameters: list[object] = []
    if window.start_utc is not None:
        clauses.append(f"{column} >= ?")
        parameters.append(window.start_utc)
    if window.end_utc is not None:
        clauses.append(f"{column} < ?")
        parameters.append(window.end_utc)
    return (" AND ".join(clauses), parameters)


def _nearest_rank_p95(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * 0.95) - 1]


def _median(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) // 2


def _distribution(values: list[str]) -> tuple[tuple[str, int], ...]:
    counts = Counter(values)
    if len(counts) > 64 or any(_FILTER_TOKEN.fullmatch(item) is None for item in counts):
        raise ControlCenterError("METRIC_DISTRIBUTION_INVALID")
    return tuple(sorted(counts.items()))


def _observation_timestamp(value: datetime) -> str:
    if type(value) is not datetime or value.tzinfo is None:
        raise ControlCenterError("OBSERVATION_CLOCK_INVALID")
    rendered = value.astimezone(timezone.utc).isoformat(timespec="microseconds")
    return CanonicalTimestamp(rendered.replace("+00:00", "Z")).value


def _currency_totals(values: list[Money]) -> tuple[CurrencyTotal, ...]:
    totals: dict[tuple[str, str, int], tuple[int, int]] = {}
    for value in values:
        key = (value.currency_code, value.registry_version, value.scale)
        prior_amount, prior_count = totals.get(key, (0, 0))
        totals[key] = (prior_amount + value.minor_units, prior_count + 1)
    return tuple(
        CurrencyTotal(code, registry, scale, amount, count)
        for (code, registry, scale), (amount, count) in sorted(totals.items())
    )


class ControlCenterApplication:
    """Read-only facade used by thin local HTTP adapters.

    Mutation adapters may be composed alongside this facade; they must not be implemented
    by these query methods or inferred from projection state.
    """

    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        scenario_application: ScenarioSelectionSource | None = None,
    ) -> None:
        if type(database) is not SQLiteDatabase:
            raise ControlCenterError("DATABASE_INVALID")
        self.database = database
        self._actions = ControlCenterActions(
            database,
            scenario_application=scenario_application,
        )

    def record_sales_credit_manager_outcome(
        self,
        order_id: str,
        *,
        actor_id: str,
        outcome: str,
        amount_minor_units: int | None,
        currency_code: str | None,
        request_key: str,
        confirmed: bool,
        decided_at: str,
    ) -> dict[str, object]:
        return self._actions.record_sales_credit_manager_outcome(
            order_id,
            actor_id=actor_id,
            outcome=outcome,
            amount_minor_units=amount_minor_units,
            currency_code=currency_code,
            request_key=request_key,
            confirmed=confirmed,
            decided_at=decided_at,
        )

    def record_doi_overlap_selection(
        self,
        case_id: str,
        *,
        evaluation_id: str,
        actor_id: str,
        selected_opportunity_id: str,
        option_opportunity_ids: tuple[str, ...],
        request_key: str,
        confirmed: bool,
        occurred_at: str,
    ) -> dict[str, object]:
        return self._actions.record_doi_overlap_selection(
            case_id,
            evaluation_id=evaluation_id,
            actor_id=actor_id,
            selected_opportunity_id=selected_opportunity_id,
            option_opportunity_ids=option_opportunity_ids,
            request_key=request_key,
            confirmed=confirmed,
            occurred_at=occurred_at,
        )

    def create_verified_backup(
        self,
        *,
        request_key: str,
        confirmed: bool,
    ) -> dict[str, object]:
        return self._actions.create_verified_backup(
            request_key=request_key,
            confirmed=confirmed,
        )

    def deep_verify(self) -> dict[str, object]:
        return self.database_view(deep=True)

    @staticmethod
    def _page_view(
        page: Page[object],
        request: PageRequest,
    ) -> dict[str, object]:
        serialized: list[object] = []
        for item in page.items:
            converter = getattr(item, "to_dict", None)
            if not callable(converter):
                raise ControlCenterError("VIEW_SERIALIZATION_INVALID")
            serialized.append(converter())
        return {
            "items": serialized,
            "limit": page.limit,
            "offset": page.offset,
            "query": {
                "descending": request.descending,
                "search": request.search,
                "sort_by": request.sort_by,
                "state": request.state,
            },
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
            "total_count": page.total_count,
        }

    def overview_view(self, window: MetricWindow = MetricWindow()) -> dict[str, object]:
        metrics = self.metrics(window)
        return {
            "metrics": metrics.to_dict(),
            "reconciliation": self.reconciliation(window).to_dict(),
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
        }

    def sales_credit_queue_view(
        self,
        request: PageRequest = PageRequest(),
    ) -> dict[str, object]:
        page = self.sales_credit_cases(request)
        return self._page_view(cast(Page[object], page), request)

    def doi_queue_view(
        self,
        request: PageRequest = PageRequest(),
    ) -> dict[str, object]:
        page = self.doi_cases(request)
        return self._page_view(cast(Page[object], page), request)

    def review_queue_view(self) -> dict[str, object]:
        items = self.human_review_queue()
        return {
            "items": [item.to_dict() for item in items],
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
            "total_count": len(items),
        }

    def audit_view(self, subject_kind: str, subject_id: str) -> dict[str, object]:
        events = self.audit_timeline(subject_kind, subject_id)
        return {
            "events": [item.to_dict() for item in events],
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
            "subject_id": subject_id,
            "subject_kind": subject_kind,
        }

    def database_view(
        self,
        *,
        deep: bool = False,
        repository_root: Path | None = None,
    ) -> dict[str, object]:
        status = self.system_database_status(
            deep=deep,
            repository_root=repository_root,
        )
        return {
            "database": status.to_dict(),
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
        }

    def backups_view(self, *, limit: int = 25) -> dict[str, object]:
        receipts = self.backup_receipts(limit=limit)
        return {
            "items": [item.to_dict() for item in receipts],
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
            "total_count": len(receipts),
        }

    def telemetry_view(
        self,
        window: MetricWindow = MetricWindow(),
    ) -> dict[str, object]:
        database = self.system_database_status()
        return {
            "benchmark_reference": M4_BENCHMARK_REFERENCE.to_dict(),
            "denominator_registry": denominator_registry(),
            "metrics": self.metrics(window).to_dict(),
            "operational_status": {
                "database_size_bytes": database.database_size_bytes,
                "latest_backup": (
                    None
                    if database.latest_backup is None
                    else database.latest_backup.to_dict()
                ),
                "latest_restore": (
                    None
                    if database.latest_restore is None
                    else database.latest_restore.to_dict()
                ),
                "safety_observed_at": database.safety_observed_at,
                "verification_observed_at": database.verification_observed_at,
            },
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
        }

    @staticmethod
    def extension_status_view(
        *,
        expected_version: str,
        expected_package_sha256: str,
        package_available: bool,
        observed_version: str | None,
        observed_at: datetime | None,
        now: datetime,
        stale_after: timedelta = DEFAULT_EXTENSION_STALE_AFTER,
    ) -> dict[str, object]:
        supplied = (observed_version, observed_at)
        if any(item is None for item in supplied) and not all(
            item is None for item in supplied
        ):
            raise ControlCenterError("EXTENSION_OBSERVATION_INVALID")
        observation = None
        if observed_version is not None:
            observation = ExtensionObservation(
                observed_version,
                cast(datetime, observed_at),
            )
        status = classify_extension_status(
            expected_version=expected_version,
            expected_package_sha256=expected_package_sha256,
            package_available=package_available,
            observation=observation,
            now=now,
            stale_after=stale_after,
        )
        return {
            "extension": status.to_dict(),
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
        }

    def system_view(
        self,
        *,
        expected_extension_version: str,
        expected_extension_package_sha256: str,
        extension_package_available: bool,
        observed_extension_version: str | None,
        extension_observed_at: datetime | None,
        now: datetime,
        repository_root: Path | None = None,
    ) -> dict[str, object]:
        return {
            "application_schema_version": APPLICATION_SCHEMA_VERSION,
            "benchmark_reference": M4_BENCHMARK_REFERENCE.to_dict(),
            "build_version": APPLICATION_BUILD_VERSION,
            "database": self.system_database_status(
                repository_root=repository_root
            ).to_dict(),
            "extension": self.extension_status_view(
                expected_version=expected_extension_version,
                expected_package_sha256=expected_extension_package_sha256,
                package_available=extension_package_available,
                observed_version=observed_extension_version,
                observed_at=extension_observed_at,
                now=now,
            )["extension"],
            "recent_safe_errors": [
                item.to_dict() for item in self.recent_safe_errors()
            ],
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
        }

    def sales_credit_cases(
        self,
        request: PageRequest = PageRequest(),
    ) -> Page[SalesCreditCaseSummary]:
        sort_columns = {
            "order_id": "c.order_id",
            "workflow_state": "c.workflow_state",
            "updated_at": "c.updated_at",
        }
        sort_column = sort_columns.get(request.sort_by)
        if sort_column is None:
            raise ControlCenterError("SORT_INVALID")
        predicates = ["c.workflow_state != 'CLOSED'", "closed.order_id IS NULL"]
        parameters: list[object] = []
        if request.search is not None:
            predicates.append("c.order_id LIKE ? ESCAPE '\\'")
            escaped = request.search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            parameters.append(f"%{escaped}%")
        if request.state is not None:
            predicates.append("c.workflow_state = ?")
            parameters.append(request.state)
        where = " AND ".join(predicates)
        direction = "DESC" if request.descending else "ASC"
        with self.database.read() as connection:
            total = int(
                connection.execute(
                    "SELECT COUNT(*) FROM sc_cases c "
                    "LEFT JOIN sc_closed_audits closed ON closed.order_id=c.order_id "
                    f"WHERE {where}",
                    parameters,
                ).fetchone()[0]
            )
            rows = connection.execute(
                "SELECT c.order_id, c.workflow_state, c.attribution, "
                "c.order_value_status, c.updated_at, c.current_evaluation_id, "
                "e.human_review_required, outcome.outcome, "
                "(SELECT COUNT(*) FROM sc_case_interactions ci "
                " WHERE ci.order_id=c.order_id) AS interaction_count "
                "FROM sc_cases c "
                "LEFT JOIN sc_closed_audits closed ON closed.order_id=c.order_id "
                "LEFT JOIN sc_evaluations e ON e.evaluation_id=c.current_evaluation_id "
                "LEFT JOIN sc_manager_outcomes outcome "
                " ON outcome.occurrence_id=c.manager_occurrence_id "
                f"WHERE {where} ORDER BY {sort_column} {direction}, c.order_id ASC "
                "LIMIT ? OFFSET ?",
                (*parameters, request.limit, request.offset),
            ).fetchall()
        items = tuple(
            SalesCreditCaseSummary(
                order_id=str(row[0]),
                workflow_state=str(row[1]),
                attribution=str(row[2]),
                order_value_status=str(row[3]),
                updated_at=str(row[4]),
                current_evaluation_id=None if row[5] is None else str(row[5]),
                human_review_required=bool(int(row[6] or 0)),
                unresolved_human_review=bool(int(row[6] or 0)) and row[7] is None,
                manager_outcome=None if row[7] is None else str(row[7]),
                interaction_count=int(row[8]),
            )
            for row in rows
        )
        return Page(items, total, request.offset, request.limit)

    def doi_cases(self, request: PageRequest = PageRequest()) -> Page[DOICaseSummary]:
        sort_columns = {
            "case_id": "c.case_id",
            "order_id": "c.order_id",
            "updated_at": "updated_at",
            "doi_state": "e.top_level_state",
        }
        sort_column = sort_columns.get(request.sort_by)
        if sort_column is None:
            raise ControlCenterError("SORT_INVALID")
        predicates = ["p.lifecycle_state = 'ACTIVE'"]
        parameters: list[object] = []
        if request.search is not None:
            predicates.append("(c.order_id LIKE ? ESCAPE '\\' OR c.case_id LIKE ? ESCAPE '\\')")
            escaped = request.search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            parameters.extend((f"%{escaped}%", f"%{escaped}%"))
        if request.state is not None:
            predicates.append("e.top_level_state = ?")
            parameters.append(request.state)
        where = " AND ".join(predicates)
        direction = "DESC" if request.descending else "ASC"
        with self.database.read() as connection:
            total = int(
                connection.execute(
                    "SELECT COUNT(*) FROM doi_cases c "
                    "JOIN doi_case_projections p ON p.case_id=c.case_id "
                    "LEFT JOIN doi_evaluations e ON e.evaluation_id=p.current_evaluation_id "
                    f"WHERE {where}",
                    parameters,
                ).fetchone()[0]
            )
            rows = connection.execute(
                "SELECT c.case_id, c.order_id, p.lifecycle_state, "
                "p.current_evaluation_id, e.top_level_state, e.output_canonical_bytes, "
                "COALESCE(a.created_at, c.created_at) AS updated_at "
                "FROM doi_cases c JOIN doi_case_projections p ON p.case_id=c.case_id "
                "LEFT JOIN doi_evaluations e ON e.evaluation_id=p.current_evaluation_id "
                "LEFT JOIN doi_case_artifacts a ON a.artifact_pk=e.record_artifact_pk "
                f"WHERE {where} ORDER BY {sort_column} {direction}, c.case_id ASC "
                "LIMIT ? OFFSET ?",
                (*parameters, request.limit, request.offset),
            ).fetchall()
            summaries: list[DOICaseSummary] = []
            for row in rows:
                evaluation_id = None if row[3] is None else str(row[3])
                reasons: tuple[str, ...] = ()
                opportunity_types: tuple[str, ...] = ()
                aggregate_state = "UNAVAILABLE"
                selection_state = "NOT_REQUIRED"
                review_required = False
                if evaluation_id is not None:
                    reasons = tuple(
                        str(item[0])
                        for item in connection.execute(
                            "SELECT reason_code FROM doi_evaluation_reasons "
                            "WHERE evaluation_id=? ORDER BY ordinal",
                            (evaluation_id,),
                        ).fetchall()
                    )
                    opportunity_types = tuple(
                        str(item[0])
                        for item in connection.execute(
                            "SELECT opportunity_type FROM doi_opportunities "
                            "WHERE evaluation_id=? ORDER BY opportunity_type, opportunity_id",
                            (evaluation_id,),
                        ).fetchall()
                    )
                    (
                        aggregate_state,
                        selection_state,
                        review_required,
                        _,
                        _,
                    ) = _doi_output_facts(row[5])
                attention_causes = _current_attention_causes(
                    connection,
                    case_id=str(row[0]),
                )
                summaries.append(
                    DOICaseSummary(
                        case_id=str(row[0]),
                        order_id=str(row[1]),
                        lifecycle_state=str(row[2]),
                        current_evaluation_id=evaluation_id,
                        doi_state=None if row[4] is None else str(row[4]),
                        opportunity_types=opportunity_types,
                        reason_codes=reasons,
                        aggregate_potential_state=aggregate_state,
                        scenario_selection_state=selection_state,
                        attention_causes=tuple(
                            str(item["condition"]) for item in attention_causes
                        ),
                        human_review_required=review_required,
                        updated_at=str(row[6]),
                    )
                )
        return Page(tuple(summaries), total, request.offset, request.limit)

    def human_review_queue(self) -> tuple[HumanReviewItem, ...]:
        sales_credit_items: list[SalesCreditCaseSummary] = []
        offset = 0
        while True:
            page = self.sales_credit_cases(
                PageRequest(
                    limit=100,
                    offset=offset,
                    sort_by="order_id",
                    descending=False,
                )
            )
            sales_credit_items.extend(page.items)
            offset += len(page.items)
            if not page.items or offset >= page.total_count:
                break
        doi_items: list[DOICaseSummary] = []
        offset = 0
        while True:
            page = self.doi_cases(
                PageRequest(
                    limit=100,
                    offset=offset,
                    sort_by="order_id",
                    descending=False,
                )
            )
            doi_items.extend(page.items)
            offset += len(page.items)
            if not page.items or offset >= page.total_count:
                break
        items = [
            HumanReviewItem(
                domain="SALES_CREDIT",
                subject_id=item.order_id,
                order_id=item.order_id,
                reason_codes=(item.workflow_state,),
                system_state=item.workflow_state,
                source_completeness_state="COMPLETE_EVALUATION_RECORDED",
                required_action="RECORD_MANAGER_OUTCOME",
                action_available=True,
                audit_subject_kind="SALES_CREDIT_CASE",
            )
            for item in sales_credit_items
            if item.unresolved_human_review
        ]
        items.extend(
            HumanReviewItem(
                domain="DOI",
                subject_id=item.case_id,
                order_id=item.order_id,
                reason_codes=item.reason_codes,
                system_state=item.doi_state or "UNEVALUATED",
                source_completeness_state="COMPLETE_EVALUATION_RECORDED",
                required_action=(
                    "SELECT_OVERLAP_SCENARIO"
                    if item.scenario_selection_state == "REQUIRED"
                    else "REVIEW_EXACT_REASON"
                ),
                action_available=item.scenario_selection_state == "REQUIRED",
                audit_subject_kind="DOI_CASE",
            )
            for item in doi_items
            if item.human_review_required
        )
        return tuple(sorted(items, key=lambda item: (item.domain, item.order_id, item.subject_id)))

    def sales_credit_detail(self, order_id: str) -> dict[str, object]:
        self._require_id(order_id, "SALES_CREDIT_CASE_ID_INVALID")
        current_evaluation: dict[str, object] | None = None
        evidence: list[dict[str, object]] = []
        interactions: list[dict[str, object]] = []
        search_runs: list[dict[str, object]] = []
        snapshots: list[dict[str, object]] = []
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT c.order_id, c.workflow_state, c.attribution, "
                "c.order_value_status, c.updated_at, c.current_evaluation_id, "
                "e.human_review_required, outcome.outcome, "
                "(SELECT COUNT(*) FROM sc_case_interactions ci "
                " WHERE ci.order_id=c.order_id) AS interaction_count "
                "FROM sc_cases c "
                "LEFT JOIN sc_case_evaluations owned_evaluation "
                " ON owned_evaluation.order_id=c.order_id "
                " AND owned_evaluation.evaluation_id=c.current_evaluation_id "
                "LEFT JOIN sc_evaluations e "
                " ON e.evaluation_id=owned_evaluation.evaluation_id "
                " AND e.order_id=owned_evaluation.order_id "
                "LEFT JOIN sc_manager_outcomes outcome "
                " ON outcome.occurrence_id=c.manager_occurrence_id "
                " AND outcome.order_id=c.order_id "
                "WHERE c.order_id=?",
                (order_id,),
            ).fetchone()
            if row is None:
                raise ControlCenterError("SALES_CREDIT_CASE_NOT_FOUND")
            summary = SalesCreditCaseSummary(
                order_id=str(row[0]),
                workflow_state=str(row[1]),
                attribution=str(row[2]),
                order_value_status=str(row[3]),
                updated_at=str(row[4]),
                current_evaluation_id=None if row[5] is None else str(row[5]),
                human_review_required=bool(int(row[6] or 0)),
                unresolved_human_review=bool(int(row[6] or 0)) and row[7] is None,
                manager_outcome=None if row[7] is None else str(row[7]),
                interaction_count=int(row[8]),
            )
            reasons = tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT r.reason_code FROM sc_evaluation_reasons r "
                    "JOIN sc_cases c ON c.current_evaluation_id=r.evaluation_id "
                    "WHERE c.order_id=? ORDER BY r.ordinal",
                    (order_id,),
                ).fetchall()
            )
            outcomes = tuple(
                {
                    "actor_id": str(row[0]),
                    "amount_minor_units": (
                        None if row[4] is None else int(str(row[4]))
                    ),
                    "currency_code": None if row[5] is None else str(row[5]),
                    "currency_registry_version": (
                        None if row[6] is None else str(row[6])
                    ),
                    "currency_scale": None if row[7] is None else int(row[7]),
                    "decided_at": str(row[1]),
                    "occurrence_id": str(row[2]),
                    "outcome": str(row[3]),
                }
                for row in connection.execute(
                    "SELECT actor_id, decided_at, occurrence_id, outcome, "
                    "approved_minor_units, approved_currency, "
                    "approved_registry_version, approved_scale "
                    "FROM sc_manager_outcomes WHERE order_id=? ORDER BY decided_at, occurrence_id",
                    (order_id,),
                ).fetchall()
            )
            if summary.current_evaluation_id is not None:
                evaluation = connection.execute(
                    "SELECT e.evaluation_id, e.snapshot_id, e.rule_pack_version, "
                    "e.material_sha256, e.human_review_required "
                    "FROM sc_case_evaluations owned JOIN sc_evaluations e "
                    "ON e.evaluation_id=owned.evaluation_id "
                    "AND e.order_id=owned.order_id "
                    "WHERE owned.order_id=? AND owned.evaluation_id=?",
                    (order_id, summary.current_evaluation_id),
                ).fetchone()
                if evaluation is None:
                    raise ControlCenterError("SALES_CREDIT_EVALUATION_NOT_FOUND")
                current_evaluation = {
                    "evaluation_id": str(evaluation[0]),
                    "human_review_required": bool(int(evaluation[4])),
                    "material_sha256": str(evaluation[3]),
                    "rule_pack_version": str(evaluation[2]),
                    "snapshot_id": str(evaluation[1]),
                }
            snapshots = [
                {
                    "captured_at": str(snapshot[1]),
                    "extraction_status": str(snapshot[2]),
                    "is_current": (
                        current_evaluation is not None
                        and str(snapshot[0]) == current_evaluation["snapshot_id"]
                    ),
                    "lifecycle_status": str(snapshot[3]),
                    "line_count": int(snapshot[5]),
                    "parser_version": str(snapshot[4]),
                    "snapshot_id": str(snapshot[0]),
                }
                for snapshot in connection.execute(
                    "SELECT s.snapshot_id, s.captured_at, s.extraction_status, "
                    "s.lifecycle_status, s.parser_version, "
                    "(SELECT COUNT(*) FROM sc_snapshot_lines l "
                    " WHERE l.snapshot_id=s.snapshot_id) AS line_count "
                    "FROM sc_case_snapshots owned JOIN sc_snapshots s "
                    "ON s.snapshot_id=owned.snapshot_id "
                    "AND s.order_id=owned.order_id WHERE owned.order_id=? "
                    "ORDER BY s.captured_at, s.snapshot_id",
                    (order_id,),
                ).fetchall()
            ]
            interactions = [
                {
                    "interaction_id": str(interaction[0]),
                    "recorded_at": str(interaction[2]),
                    "source_ref_id": str(interaction[1]),
                    "timestamp_precision": str(interaction[3]),
                    "workflow_state": str(interaction[4]),
                }
                for interaction in connection.execute(
                    "SELECT i.interaction_id, i.source_ref_id, i.recorded_at, "
                    "i.timestamp_precision, i.workflow_state "
                    "FROM sc_case_interactions ci JOIN sc_interactions i "
                    "ON i.interaction_id=ci.interaction_id WHERE ci.order_id=? "
                    "ORDER BY i.recorded_at, i.interaction_id",
                    (order_id,),
                ).fetchall()
            ]
            evidence = [
                {
                    "classification": str(item[3]),
                    "evidence_id": str(item[0]),
                    "interaction_id": str(item[1]),
                    "occurred_at": str(item[4]),
                    "source_type": str(item[2]),
                }
                for item in connection.execute(
                    "SELECT e.evidence_id, e.interaction_id, e.source_type, "
                    "e.classification, e.occurred_at "
                    "FROM sc_case_evidence ce JOIN sc_evidence_events e "
                    "ON e.evidence_id=ce.evidence_id WHERE ce.order_id=? "
                    "AND e.order_id=ce.order_id "
                    "ORDER BY e.occurred_at, e.evidence_id",
                    (order_id,),
                ).fetchall()
            ]
            search_runs = [
                {
                    "adapter_version": str(run[4]),
                    "completed_at": str(run[3]),
                    "enumeration_complete": bool(int(run[5])),
                    "identifier_count": int(run[7]),
                    "run_id": str(run[0]),
                    "started_at": str(run[2]),
                    "terminal_outcome": str(run[6]),
                    "trigger_type": str(run[1]),
                }
                for run in connection.execute(
                    "SELECT r.run_id, r.trigger_type, r.started_at, r.completed_at, "
                    "r.adapter_version, r.enumeration_complete, r.terminal_outcome, "
                    "(SELECT COUNT(*) FROM sc_search_identifiers i "
                    " WHERE i.run_id=r.run_id) AS identifier_count "
                    "FROM sc_case_search_runs cr JOIN sc_search_runs r "
                    "ON r.run_id=cr.run_id WHERE cr.order_id=? "
                    "ORDER BY r.started_at, r.run_id",
                    (order_id,),
                ).fetchall()
            ]
        return {
            "current_evaluation": current_evaluation,
            "evidence": evidence,
            "interactions": interactions,
            "manager_outcomes": list(outcomes),
            "reason_codes": list(reasons),
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
            "search_runs": search_runs,
            "snapshots": snapshots,
            "summary": summary.to_dict(),
            "timeline": [
                item.to_dict()
                for item in self.audit_timeline("SALES_CREDIT_CASE", order_id)
            ],
        }

    def doi_detail(self, case_id: str) -> dict[str, object]:
        self._require_id(case_id, "DOI_CASE_ID_INVALID")
        current_evaluation: dict[str, object] | None = None
        evaluation_input_bytes: bytes | None = None
        opportunities: list[dict[str, object]] = []
        reason_explanations: list[dict[str, str]] = []
        handling_flags: tuple[str, ...] = ()
        source_completeness: list[dict[str, object]] = []
        current_attention_causes: list[dict[str, object]] = []
        human_fact_events: list[dict[str, object]] = []
        interventions: list[dict[str, object]] = []
        resulting_order_links: list[dict[str, object]] = []
        value_events: list[dict[str, object]] = []
        retained_kpi_contributions: list[dict[str, object]] = []
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT c.case_id, c.order_id, p.lifecycle_state, "
                "p.current_snapshot_id, p.current_evaluation_id, e.top_level_state, "
                "e.output_canonical_bytes, "
                "COALESCE(a.created_at, c.created_at) AS updated_at "
                "FROM doi_cases c JOIN doi_case_projections p ON p.case_id=c.case_id "
                "LEFT JOIN doi_evaluations e ON e.evaluation_id=p.current_evaluation_id "
                "LEFT JOIN doi_case_artifacts a ON a.artifact_pk=e.record_artifact_pk "
                "WHERE c.case_id=?",
                (case_id,),
            ).fetchone()
            if row is None:
                raise ControlCenterError("DOI_CASE_NOT_FOUND")
            current_snapshot_id = None if row[3] is None else str(row[3])
            evaluation_id = None if row[4] is None else str(row[4])
            reasons: tuple[str, ...] = ()
            opportunity_types: tuple[str, ...] = ()
            aggregate_state = "UNAVAILABLE"
            selection_state = "NOT_REQUIRED"
            review_required = False
            if evaluation_id is not None:
                evaluation = connection.execute(
                    "SELECT evaluation_id, snapshot_id, run_id, transition_id, "
                    "input_domain, input_sha256, input_canonical_bytes, output_domain, "
                    "output_sha256, output_canonical_bytes, top_level_state "
                    "FROM doi_evaluations WHERE evaluation_id=? AND case_id=? "
                    "AND order_id=?",
                    (evaluation_id, case_id, str(row[1])),
                ).fetchone()
                if evaluation is None:
                    raise ControlCenterError("DOI_EVALUATION_NOT_FOUND")
                evaluation_input_bytes = bytes(evaluation[6])
                output_bytes = bytes(evaluation[9])
                input_domain = str(evaluation[4])
                input_sha256 = str(evaluation[5])
                output_domain = str(evaluation[7])
                output_sha256 = str(evaluation[8])
                if (
                    str(evaluation[0]) != evaluation_id
                    or str(evaluation[1]) != current_snapshot_id
                    or _SYNTHETIC_ID.fullmatch(str(evaluation[2])) is None
                    or _TRANSITION_ID.fullmatch(str(evaluation[3])) is None
                    or input_domain != "doi-evaluation-input/v1"
                    or output_domain != "doi-evaluation-output/v1"
                    or _HEX_SHA256.fullmatch(input_sha256) is None
                    or _HEX_SHA256.fullmatch(output_sha256) is None
                    or str(evaluation[10]) != str(row[5])
                    or output_bytes != bytes(row[6])
                ):
                    raise ControlCenterError("DOI_EVALUATION_BINDING_INVALID")
                try:
                    hashes_match = (
                        domain_hash(input_domain, evaluation_input_bytes).sha256
                        == input_sha256
                        and domain_hash(output_domain, output_bytes).sha256
                        == output_sha256
                    )
                except HashDomainViolation:
                    hashes_match = False
                if not hashes_match:
                    raise ControlCenterError("DOI_EVALUATION_BINDING_INVALID")
                current_evaluation = {
                    "evaluation_id": evaluation_id,
                    "input_domain": input_domain,
                    "input_sha256": input_sha256,
                    "output_domain": output_domain,
                    "output_sha256": output_sha256,
                    "run_id": str(evaluation[2]),
                    "snapshot_id": str(evaluation[1]),
                    "top_level_state": str(evaluation[10]),
                    "transition_id": str(evaluation[3]),
                }
                reasons = tuple(
                    str(item[0])
                    for item in connection.execute(
                        "SELECT reason_code FROM doi_evaluation_reasons "
                        "WHERE evaluation_id=? ORDER BY ordinal",
                        (evaluation_id,),
                        ).fetchall()
                )
                reason_explanations = _doi_reason_explanations(reasons)
                opportunity_types = tuple(
                    str(item[0])
                    for item in connection.execute(
                        "SELECT opportunity_type FROM doi_opportunities "
                        "WHERE evaluation_id=? ORDER BY opportunity_type, opportunity_id",
                        (evaluation_id,),
                    ).fetchall()
                )
                (
                    aggregate_state,
                    selection_state,
                    review_required,
                    _,
                    handling_flags,
                ) = _doi_output_facts(row[6])
            current_attention_causes = _current_attention_causes(
                connection,
                case_id=case_id,
            )
            summary = DOICaseSummary(
                case_id=str(row[0]),
                order_id=str(row[1]),
                lifecycle_state=str(row[2]),
                current_evaluation_id=evaluation_id,
                doi_state=None if row[5] is None else str(row[5]),
                opportunity_types=opportunity_types,
                reason_codes=reasons,
                aggregate_potential_state=aggregate_state,
                scenario_selection_state=selection_state,
                attention_causes=tuple(
                    str(item["condition"]) for item in current_attention_causes
                ),
                human_review_required=review_required,
                updated_at=str(row[7]),
            )
            if evaluation_id is not None:
                opportunity_rows = connection.execute(
                    "SELECT opportunity_id, opportunity_type, potential_state, "
                    "amount_minor_units, currency_code, currency_registry_version, "
                    "currency_scale, mutual_exclusion_group_id "
                    "FROM doi_opportunities WHERE evaluation_id=? AND case_id=? "
                    "ORDER BY opportunity_type, opportunity_id",
                    (evaluation_id, case_id),
                ).fetchall()
                scope_rows = connection.execute(
                    "SELECT s.opportunity_id, s.line_snapshot_id, s.role, "
                    "s.quantity_text, s.ordinal "
                    "FROM doi_opportunity_scope_components s "
                    "JOIN doi_opportunities o ON o.opportunity_id=s.opportunity_id "
                    "JOIN doi_evaluations e ON e.evaluation_id=o.evaluation_id "
                    "JOIN doi_line_snapshots l ON l.line_snapshot_id=s.line_snapshot_id "
                    "AND l.case_id=o.case_id AND l.snapshot_id=e.snapshot_id "
                    "WHERE o.evaluation_id=? AND o.case_id=? "
                    "ORDER BY s.opportunity_id, s.ordinal",
                    (evaluation_id, case_id),
                ).fetchall()
                scope_by_opportunity: dict[str, list[dict[str, object]]] = {}
                for scope in scope_rows:
                    scope_by_opportunity.setdefault(str(scope[0]), []).append(
                        {
                            "line_snapshot_id": str(scope[1]),
                            "ordinal": int(scope[4]),
                            "quantity_text": str(scope[3]),
                            "role": str(scope[2]),
                        }
                    )
                opportunities = [
                    {
                        "amount_minor_units": opportunity[3],
                        "currency_code": opportunity[4],
                        "currency_registry_version": opportunity[5],
                        "currency_scale": opportunity[6],
                        "mutual_exclusion_group_id": opportunity[7],
                        "opportunity_id": str(opportunity[0]),
                        "opportunity_type": str(opportunity[1]),
                        "potential_state": str(opportunity[2]),
                        "scope_components": scope_by_opportunity.get(
                            str(opportunity[0]), []
                        ),
                    }
                    for opportunity in opportunity_rows
                ]
                assert evaluation_input_bytes is not None
                scenario_selection = _scenario_selection_from_input(
                    evaluation_input_bytes,
                    evaluation_id=evaluation_id,
                    opportunity_ids=tuple(
                        str(opportunity[0]) for opportunity in opportunity_rows
                    ),
                    selection_state=selection_state,
                )
            else:
                scenario_selection = None
            snapshot_rows = connection.execute(
                "SELECT s.snapshot_id, s.run_id, s.order_id, s.source_observed_at, "
                "s.completeness_sha256, "
                "(SELECT COUNT(*) FROM doi_line_snapshots l "
                " WHERE l.snapshot_id=s.snapshot_id) AS line_count, "
                "(SELECT COUNT(*) FROM doi_line_snapshots l "
                " WHERE l.snapshot_id=s.snapshot_id AND l.relevant_merchandise=1) "
                "AS relevant_line_count, "
                "EXISTS(SELECT 1 FROM doi_snapshot_completeness_proof_references p "
                " WHERE p.snapshot_id=s.snapshot_id) AS proof_present, "
                "a.record_domain, a.record_sha256 "
                "FROM doi_order_snapshots s JOIN doi_case_artifacts a "
                "ON a.artifact_pk=s.record_artifact_pk WHERE s.case_id=? "
                "ORDER BY s.source_observed_at, s.snapshot_id",
                (case_id,),
            ).fetchall()
            source_completeness = [
                {
                    "completeness_proof_present": bool(int(snapshot[7])),
                    "completeness_sha256": str(snapshot[4]),
                    "is_current": str(snapshot[0]) == current_snapshot_id,
                    "line_count": int(snapshot[5]),
                    "order_id": str(snapshot[2]),
                    "relevant_line_count": int(snapshot[6]),
                    "record_domain": str(snapshot[8]),
                    "record_sha256": str(snapshot[9]),
                    "run_id": str(snapshot[1]),
                    "snapshot_id": str(snapshot[0]),
                    "source_observed_at": str(snapshot[3]),
                }
                for snapshot in snapshot_rows
            ]
            human_rows = connection.execute(
                "SELECT e.stream_id, e.event_id, e.sequence_no, e.transition_id, "
                "e.projection_state, e.occurred_at, e.record_domain, e.record_sha256 "
                "FROM doi_owner_events e JOIN doi_owner_streams s "
                "ON s.stream_family=e.stream_family AND s.stream_id=e.stream_id "
                "WHERE s.case_id=? AND e.stream_family='HUMAN_FACT' "
                "ORDER BY e.occurred_at, e.stream_id, e.sequence_no",
                (case_id,),
            ).fetchall()
            human_fact_events = [
                {
                    "event_id": str(event[1]),
                    "occurred_at": str(event[5]),
                    "projection_state": str(event[4]),
                    "record_domain": str(event[6]),
                    "record_sha256": str(event[7]),
                    "sequence": int(event[2]),
                    "stream_id": str(event[0]),
                    "transition_id": None if event[3] is None else str(event[3]),
                }
                for event in human_rows
            ]
            intervention_rows = connection.execute(
                "SELECT i.intervention_id, i.opportunity_id, i.intervention_type, "
                "i.status, i.action_occurred_at, i.projection_version, i.head_sha256, "
                "a.created_at, a.record_domain, a.record_sha256 "
                "FROM doi_interventions i JOIN doi_case_artifacts a "
                "ON a.artifact_pk=i.record_artifact_pk "
                "WHERE i.case_id=? ORDER BY a.created_at, i.intervention_id",
                (case_id,),
            ).fetchall()
            for intervention in intervention_rows:
                intervention_id = str(intervention[0])
                verification_rows = connection.execute(
                    "SELECT event_id, occurrence_id, record_domain, record_sha256 "
                    "FROM doi_action_verification_events WHERE intervention_id=? "
                    "ORDER BY event_id",
                    (intervention_id,),
                ).fetchall()
                interventions.append(
                    {
                        "action_occurred_at": (
                            None if intervention[4] is None else str(intervention[4])
                        ),
                        "created_at": str(intervention[7]),
                        "head_sha256": str(intervention[6]),
                        "intervention_id": intervention_id,
                        "intervention_type": str(intervention[2]),
                        "opportunity_id": str(intervention[1]),
                        "projection_version": int(intervention[5]),
                        "record_domain": str(intervention[8]),
                        "record_sha256": str(intervention[9]),
                        "status": str(intervention[3]),
                        "verification_events": [
                            {
                                "event_id": str(verification[0]),
                                "occurrence_id": str(verification[1]),
                                "record_domain": str(verification[2]),
                                "record_sha256": str(verification[3]),
                            }
                            for verification in verification_rows
                        ],
                    }
                )
            link_rows = connection.execute(
                "SELECT link_id, intervention_id, parent_order_id, child_order_id, "
                "state, current_revision, head_sha256 "
                "FROM doi_resulting_order_links WHERE case_id=? ORDER BY link_id",
                (case_id,),
            ).fetchall()
            for link in link_rows:
                link_id = str(link[0])
                revision_rows = connection.execute(
                    "SELECT revision_no, revision_id, predecessor_sha256, "
                    "record_domain, record_sha256 "
                    "FROM doi_resulting_order_link_revisions WHERE link_id=? "
                    "ORDER BY revision_no",
                    (link_id,),
                ).fetchall()
                revisions: list[dict[str, object]] = []
                for revision in revision_rows:
                    revision_number = int(revision[0])
                    mapping_rows = connection.execute(
                        "SELECT parent_line_id, child_line_id, quantity_text, ordinal "
                        "FROM doi_resulting_order_mapping_components "
                        "WHERE link_id=? AND revision_no=? ORDER BY ordinal",
                        (link_id, revision_number),
                    ).fetchall()
                    revisions.append(
                        {
                            "mapping_components": [
                                {
                                    "child_line_id": str(mapping[1]),
                                    "ordinal": int(mapping[3]),
                                    "parent_line_id": str(mapping[0]),
                                    "quantity_text": str(mapping[2]),
                                }
                                for mapping in mapping_rows
                            ],
                            "predecessor_sha256": (
                                None if revision[2] is None else str(revision[2])
                            ),
                            "record_domain": str(revision[3]),
                            "record_sha256": str(revision[4]),
                            "revision": revision_number,
                            "revision_id": str(revision[1]),
                        }
                    )
                resulting_order_links.append(
                    {
                        "child_order_id": str(link[3]),
                        "current_revision": int(link[5]),
                        "head_sha256": str(link[6]),
                        "intervention_id": str(link[1]),
                        "link_id": link_id,
                        "parent_order_id": str(link[2]),
                        "revisions": revisions,
                        "state": str(link[4]),
                    }
                )
            value_rows = connection.execute(
                "SELECT v.intervention_id, v.event_id, v.sequence_no, v.occurrence_id, "
                "v.event_type, v.predecessor_sha256, v.amount_minor_units, "
                "v.currency_code, v.currency_registry_version, v.currency_scale, "
                "v.record_domain, v.record_sha256 "
                "FROM doi_value_events v JOIN doi_interventions i "
                "ON i.intervention_id=v.intervention_id WHERE i.case_id=? "
                "ORDER BY v.intervention_id, v.sequence_no",
                (case_id,),
            ).fetchall()
            value_events = [
                {
                    "amount_minor_units": int(value[6]),
                    "currency_code": str(value[7]),
                    "currency_registry_version": str(value[8]),
                    "currency_scale": int(value[9]),
                    "event_id": str(value[1]),
                    "event_type": str(value[4]),
                    "intervention_id": str(value[0]),
                    "occurrence_id": str(value[3]),
                    "predecessor_sha256": None if value[5] is None else str(value[5]),
                    "record_domain": str(value[10]),
                    "record_sha256": str(value[11]),
                    "sequence": int(value[2]),
                }
                for value in value_rows
            ]
            contribution_rows = connection.execute(
                "SELECT intervention_id, intervention_type, action_date, "
                "amount_minor_units, currency_code, currency_registry_version, "
                "currency_scale, revision, head_sha256 "
                "FROM doi_retained_kpi_contributions WHERE case_id=? "
                "ORDER BY action_date, intervention_type, intervention_id",
                (case_id,),
            ).fetchall()
            retained_kpi_contributions = [
                {
                    "action_date": str(contribution[2]),
                    "amount_minor_units": int(contribution[3]),
                    "currency_code": str(contribution[4]),
                    "currency_registry_version": str(contribution[5]),
                    "currency_scale": int(contribution[6]),
                    "head_sha256": str(contribution[8]),
                    "intervention_id": str(contribution[0]),
                    "intervention_type": str(contribution[1]),
                    "revision": int(contribution[7]),
                }
                for contribution in contribution_rows
            ]
        return {
            "current_attention_causes": current_attention_causes,
            "current_evaluation": current_evaluation,
            "handling_flags": list(handling_flags),
            "human_fact_events": human_fact_events,
            "interventions": interventions,
            "opportunities": opportunities,
            "reason_explanations": reason_explanations,
            "resulting_order_links": resulting_order_links,
            "retained_kpi_contributions": retained_kpi_contributions,
            "schema_version": CONTROL_CENTER_SCHEMA_VERSION,
            "scenario_selection": scenario_selection,
            "source_completeness": source_completeness,
            "summary": summary.to_dict(),
            "timeline": [item.to_dict() for item in self.audit_timeline("DOI_CASE", case_id)],
            "value_events": value_events,
        }

    def audit_timeline(self, subject_kind: str, subject_id: str) -> tuple[TimelineEvent, ...]:
        if subject_kind not in {
            "SALES_CREDIT_CASE",
            "DOI_CASE",
            "DOI_RUN",
            "EVALUATION",
        }:
            raise ControlCenterError("AUDIT_SUBJECT_KIND_INVALID")
        self._require_id(subject_id, "AUDIT_SUBJECT_ID_INVALID")
        with self.database.read() as connection:
            if subject_kind == "EVALUATION":
                rows = connection.execute(
                    "SELECT e.evaluation_id, e.workflow_state, s.captured_at "
                    "FROM sc_evaluations e JOIN sc_snapshots s "
                    "ON s.snapshot_id=e.snapshot_id WHERE e.evaluation_id=? "
                    "UNION ALL "
                    "SELECT e.evaluation_id, e.top_level_state, a.created_at "
                    "FROM doi_evaluations e JOIN doi_case_artifacts a "
                    "ON a.artifact_pk=e.record_artifact_pk WHERE e.evaluation_id=?",
                    (subject_id, subject_id),
                ).fetchall()
                if len(rows) != 1:
                    raise ControlCenterError("AUDIT_SUBJECT_NOT_FOUND")
                row = rows[0]
                return (
                    TimelineEvent(
                        1,
                        str(row[0]),
                        "EVALUATION_RECORDED",
                        str(row[1]),
                        str(row[2]),
                    ),
                )
            if subject_kind == "SALES_CREDIT_CASE":
                if connection.execute(
                    "SELECT 1 FROM sc_cases WHERE order_id=?",
                    (subject_id,),
                ).fetchone() is None:
                    raise ControlCenterError("AUDIT_SUBJECT_NOT_FOUND")
                rows = connection.execute(
                    "SELECT sequence, event_id, event_kind, workflow_state, occurred_at "
                    "FROM sc_case_events WHERE order_id=? ORDER BY sequence",
                    (subject_id,),
                ).fetchall()
                return tuple(
                    TimelineEvent(int(row[0]), str(row[1]), str(row[2]), str(row[3]), str(row[4]))
                    for row in rows
                )
            if subject_kind == "DOI_RUN":
                if connection.execute(
                    "SELECT 1 FROM doi_runs WHERE run_id=?",
                    (subject_id,),
                ).fetchone() is None:
                    raise ControlCenterError("AUDIT_SUBJECT_NOT_FOUND")
                rows = connection.execute(
                    "SELECT sequence_no, record_sha256, event_kind, event_kind, occurred_at "
                    "FROM doi_run_events WHERE run_id=? ORDER BY sequence_no",
                    (subject_id,),
                ).fetchall()
                return tuple(
                    TimelineEvent(int(row[0]), str(row[1]), str(row[2]), str(row[3]), str(row[4]))
                    for row in rows
                )
            if connection.execute(
                "SELECT 1 FROM doi_cases WHERE case_id=?",
                (subject_id,),
            ).fetchone() is None:
                raise ControlCenterError("AUDIT_SUBJECT_NOT_FOUND")
            rows = connection.execute(
                "SELECT created_at, artifact_id, artifact_kind, artifact_kind, "
                "NULL AS transition_id, 0 AS source_order "
                "FROM doi_case_artifacts WHERE case_id=? "
                "UNION ALL "
                "SELECT e.occurred_at, e.event_id, s.stream_family, "
                "e.projection_state, e.transition_id, 1 AS source_order "
                "FROM doi_owner_events e JOIN doi_owner_streams s "
                "ON s.stream_family=e.stream_family AND s.stream_id=e.stream_id "
                "WHERE s.case_id=? "
                "ORDER BY 1, 6, 2",
                (subject_id, subject_id),
            ).fetchall()
            return tuple(
                TimelineEvent(
                    sequence,
                    str(row[1]),
                    str(row[2]),
                    str(row[3]),
                    str(row[0]),
                    None if row[4] is None else str(row[4]),
                )
                for sequence, row in enumerate(rows, start=1)
            )

    def reconciliation(self, window: MetricWindow = MetricWindow()) -> ProjectionReconciliation:
        metrics = self.metrics(window)
        with self.database.read() as connection:
            sc_events = int(connection.execute("SELECT COUNT(*) FROM sc_case_events").fetchone()[0])
            doi_events = int(
                connection.execute(
                    "SELECT (SELECT COUNT(*) FROM doi_case_artifacts) + "
                    "(SELECT COUNT(*) FROM doi_owner_events)"
                ).fetchone()[0]
            )
        return ProjectionReconciliation(
            metrics.active_sales_credit_cases,
            sc_events,
            metrics.active_doi_cases,
            doi_events,
            metrics.current_human_review_items,
            metrics.unique_evaluations,
            metrics.exact_replays,
            metrics.material_conflicts,
        )

    def metrics(self, window: MetricWindow = MetricWindow()) -> DashboardMetrics:
        with self.database.read() as connection:
            telemetry_clause, telemetry_parameters = _window_clause(window, "ended_at")
            telemetry_where = "rule_pack IN ('SALES_CREDIT', 'DOI')"
            if telemetry_clause:
                telemetry_where += f" AND {telemetry_clause}"
            telemetry_rows = connection.execute(
                "SELECT started_at, ended_at, total_ns, result_class, human_review, "
                "fail_closed, replay, conflict, database_error FROM processing_telemetry "
                f"WHERE {telemetry_where} ORDER BY operation_id",
                telemetry_parameters,
            ).fetchall()
            safety_rows = connection.execute(
                "SELECT counter_name, counter_value FROM system_safety_counters "
                "ORDER BY counter_name"
            ).fetchall()
            counters = tuple((str(row[0]), int(row[1])) for row in safety_rows)
            if tuple(name for name, _ in counters) != SAFETY_COUNTER_NAMES or any(
                value != 0 for _, value in counters
            ):
                raise ControlCenterError("SAFETY_COUNTERS_NONZERO")

            sc_eval_where, sc_eval_params = _window_clause(window, "first_occurred_at")
            sc_evaluations = connection.execute(
                "SELECT e.evaluation_id, e.human_review_required, e.order_id, "
                "e.workflow_state "
                "FROM sc_evaluations e JOIN ("
                " SELECT current_evaluation_id AS evaluation_id, "
                " MIN(occurred_at) AS first_occurred_at "
                " FROM sc_case_events WHERE current_evaluation_id IS NOT NULL "
                " GROUP BY current_evaluation_id"
                ") seen ON seen.evaluation_id=e.evaluation_id "
                + (f"WHERE {sc_eval_where}" if sc_eval_where else "")
                + " ORDER BY e.evaluation_id",
                sc_eval_params,
            ).fetchall()
            doi_eval_where, doi_eval_params = _window_clause(window, "a.created_at")
            doi_evaluations = connection.execute(
                "SELECT e.evaluation_id, e.top_level_state, e.order_id "
                "FROM doi_evaluations e JOIN doi_case_artifacts a "
                "ON a.artifact_pk=e.record_artifact_pk "
                + (f"WHERE {doi_eval_where}" if doi_eval_where else "")
                + " ORDER BY e.evaluation_id",
                doi_eval_params,
            ).fetchall()

            active_sc = int(
                connection.execute(
                    "SELECT COUNT(*) FROM sc_cases c LEFT JOIN sc_closed_audits closed "
                    "ON closed.order_id=c.order_id "
                    "WHERE c.workflow_state!='CLOSED' AND closed.order_id IS NULL"
                ).fetchone()[0]
            )
            active_doi = int(
                connection.execute(
                    "SELECT COUNT(*) FROM doi_case_projections WHERE lifecycle_state='ACTIVE'"
                ).fetchone()[0]
            )
            active_opportunities = int(
                connection.execute(
                    "SELECT COUNT(*) FROM doi_opportunities o "
                    "JOIN doi_case_projections p ON p.case_id=o.case_id "
                    "WHERE p.lifecycle_state='ACTIVE' "
                    "AND p.current_evaluation_id=o.evaluation_id"
                ).fetchone()[0]
            )
            state_distribution = tuple(
                (str(row[0]), int(row[1]))
                for row in connection.execute(
                    "SELECT e.top_level_state, COUNT(*) FROM doi_case_projections p "
                    "JOIN doi_evaluations e ON e.evaluation_id=p.current_evaluation_id "
                    "WHERE p.lifecycle_state='ACTIVE' GROUP BY e.top_level_state "
                    "ORDER BY e.top_level_state"
                ).fetchall()
            )
            type_counts = tuple(
                (str(row[0]), int(row[1]))
                for row in connection.execute(
                    "SELECT o.opportunity_type, COUNT(*) FROM doi_opportunities o "
                    "JOIN doi_case_projections p ON p.case_id=o.case_id "
                    "WHERE p.lifecycle_state='ACTIVE' "
                    "AND p.current_evaluation_id=o.evaluation_id "
                    "GROUP BY o.opportunity_type ORDER BY o.opportunity_type"
                ).fetchall()
            )

            current_doi_outputs = connection.execute(
                "SELECT e.output_canonical_bytes FROM doi_case_projections p "
                "JOIN doi_evaluations e ON e.evaluation_id=p.current_evaluation_id "
                "WHERE p.lifecycle_state='ACTIVE' ORDER BY p.case_id"
            ).fetchall()
            potential_values: list[Money] = []
            unavailable_count = 0
            unresolved_overlap_count = 0
            current_doi_reviews = 0
            for row in current_doi_outputs:
                (
                    aggregate_state,
                    selection_state,
                    reviews,
                    potential,
                    _,
                ) = _doi_output_facts(row[0])
                current_doi_reviews += int(reviews)
                if aggregate_state == "AVAILABLE" and potential is not None:
                    potential_values.append(potential)
                else:
                    unavailable_count += 1
                    unresolved_overlap_count += int(selection_state == "REQUIRED")

            realized_values = [
                Money.from_minor_units(
                    int(row[0]),
                    currency_code=str(row[1]),
                    registry_version=str(row[2]),
                    scale=int(row[3]),
                )
                for row in connection.execute(
                    "SELECT amount_minor_units, currency_code, currency_registry_version, "
                    "currency_scale FROM doi_retained_kpi_contributions "
                    "ORDER BY currency_code, currency_registry_version, "
                    "currency_scale, intervention_id"
                ).fetchall()
            ]

            current_sc_reviews = int(
                connection.execute(
                    "SELECT COUNT(*) FROM sc_cases c "
                    "JOIN sc_evaluations e ON e.evaluation_id=c.current_evaluation_id "
                    "LEFT JOIN sc_closed_audits closed ON closed.order_id=c.order_id "
                    "WHERE c.workflow_state!='CLOSED' AND closed.order_id IS NULL "
                    "AND e.human_review_required=1 AND c.manager_occurrence_id IS NULL"
                ).fetchone()[0]
            )
            eligible_orders = {str(row[2]) for row in sc_evaluations if int(row[1]) == 1}
            manager_outcome_count = 0
            if eligible_orders:
                placeholders = ",".join("?" for _ in eligible_orders)
                manager_outcome_count = int(
                    connection.execute(
                        "SELECT COUNT(DISTINCT order_id) FROM sc_manager_outcomes "
                        f"WHERE order_id IN ({placeholders})",
                        tuple(sorted(eligible_orders)),
                    ).fetchone()[0]
                )

        requests = len(telemetry_rows)
        success = sum(str(row[3]) in {"SUCCESS", "HUMAN_REVIEW"} for row in telemetry_rows)
        fail_closed = sum(int(row[5]) for row in telemetry_rows)
        replay = sum(int(row[6]) for row in telemetry_rows)
        conflicts = sum(int(row[7]) for row in telemetry_rows)
        database_errors = sum(int(row[8]) for row in telemetry_rows)
        unique_evaluations = len(sc_evaluations) + len(doi_evaluations)
        new_review_evaluations = sum(int(row[1]) for row in sc_evaluations) + sum(
            str(row[1]) == "DOI_MANUAL_REVIEW" for row in doi_evaluations
        )
        latencies = [int(row[2]) for row in telemetry_rows]
        throughput: str | None = None
        if telemetry_rows:
            starts = [CanonicalTimestamp(str(row[0])) for row in telemetry_rows]
            ends = [CanonicalTimestamp(str(row[1])) for row in telemetry_rows]
            first = min(item.epoch_seconds * 1_000_000_000 + item.nanosecond for item in starts)
            last = max(item.epoch_seconds * 1_000_000_000 + item.nanosecond for item in ends)
            if last > first:
                throughput = f"{requests * 1_000_000_000 / (last - first):.6f}"
        return DashboardMetrics(
            window=window.label,
            requests_received=requests,
            unique_evaluations=unique_evaluations,
            exact_replays=replay,
            material_conflicts=conflicts,
            successful_requests=success,
            failed_closed_requests=fail_closed,
            database_error_count=database_errors,
            successful_request_rate=RateValue(success, requests),
            failed_closed_rate=RateValue(fail_closed, requests),
            human_review_rate=RateValue(new_review_evaluations, unique_evaluations),
            manager_outcome_rate=RateValue(manager_outcome_count, len(eligible_orders)),
            active_sales_credit_cases=active_sc,
            active_doi_cases=active_doi,
            active_doi_opportunities=active_opportunities,
            current_human_review_items=current_sc_reviews + current_doi_reviews,
            doi_state_distribution=state_distribution,
            request_result_distribution=_distribution(
                [str(row[3]) for row in telemetry_rows]
            ),
            sales_credit_result_distribution=_distribution(
                [str(row[3]) for row in sc_evaluations]
            ),
            doi_evaluation_result_distribution=_distribution(
                [str(row[1]) for row in doi_evaluations]
            ),
            opportunity_type_counts=type_counts,
            median_latency_ns=_median(latencies),
            p95_latency_ns=_nearest_rank_p95(latencies),
            throughput_per_second=throughput,
            potential_by_currency=_currency_totals(potential_values),
            potential_unavailable_count=unavailable_count,
            unresolved_overlap_count=unresolved_overlap_count,
            realized_by_currency=_currency_totals(realized_values),
            safety_counters=counters,
        )

    def backup_receipts(self, *, limit: int = 25) -> tuple[BackupSummary, ...]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ControlCenterError("PAGE_INVALID")
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT backup_id, completed_at, schema_version, backup_sha256, "
                "status, quick_check, foreign_key_check FROM backup_receipts "
                "ORDER BY COALESCE(completed_at, created_at) DESC, backup_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return tuple(
            BackupSummary(
                str(row[0]),
                None if row[1] is None else str(row[1]),
                int(row[2]),
                None if row[3] is None else str(row[3]),
                str(row[4]),
                str(row[5]),
                str(row[6]),
            )
            for row in rows
        )

    def latest_verified_backup(self) -> BackupSummary | None:
        """Return only the newest receipt that proves a completed verified backup."""

        with self.database.read() as connection:
            row = connection.execute(
                "SELECT backup_id, completed_at, schema_version, backup_sha256, "
                "status, quick_check, foreign_key_check FROM backup_receipts "
                "WHERE status='COMPLETED' AND completed_at IS NOT NULL "
                "AND backup_sha256 IS NOT NULL AND quick_check='ok' "
                "AND foreign_key_check='ok' "
                "ORDER BY completed_at DESC, backup_id DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return BackupSummary(
            str(row[0]),
            str(row[1]),
            int(row[2]),
            str(row[3]),
            str(row[4]),
            str(row[5]),
            str(row[6]),
        )

    def restore_receipts(self, *, limit: int = 25) -> tuple[RestoreSummary, ...]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ControlCenterError("PAGE_INVALID")
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT restore_id, completed_at, backup_sha256, "
                "pre_restore_backup_id, schema_version, status, error_code "
                "FROM restore_receipts "
                "ORDER BY COALESCE(completed_at, started_at) DESC, restore_id DESC "
                "LIMIT ?",
                (limit,),
            ).fetchall()
        return tuple(
            RestoreSummary(
                str(row[0]),
                None if row[1] is None else str(row[1]),
                str(row[2]),
                None if row[3] is None else str(row[3]),
                None if row[4] is None else int(row[4]),
                str(row[5]),
                None if row[6] is None else str(row[6]),
            )
            for row in rows
        )

    def recent_safe_errors(self, *, limit: int = 10) -> tuple[SafeErrorSummary, ...]:
        if type(limit) is not int or not 1 <= limit <= 25:
            raise ControlCenterError("PAGE_INVALID")
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT error_code, error_category, retryable, occurred_at "
                "FROM structured_domain_failures "
                "ORDER BY occurred_at DESC, failure_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return tuple(
            SafeErrorSummary(
                str(row[0]),
                str(row[1]),
                bool(row[2]),
                str(row[3]),
            )
            for row in rows
        )

    def system_database_status(
        self,
        *,
        deep: bool = False,
        repository_root: Path | None = None,
    ) -> SystemDatabaseStatus:
        if type(deep) is not bool:
            raise ControlCenterError("DATABASE_VERIFY_INPUT_INVALID")
        with self.database.read() as connection:
            verification = verify_database(connection, deep=deep)
            sales_credit_projection = verify_sales_credit_projections(connection)
            doi_projection = DOIRepository(connection).verify_projections()
            safety_rows = connection.execute(
                "SELECT counter_name, counter_value FROM system_safety_counters "
                "ORDER BY counter_name"
            ).fetchall()
        counters = tuple((str(row[0]), int(row[1])) for row in safety_rows)
        if tuple(name for name, _ in counters) != SAFETY_COUNTER_NAMES or any(
            value != 0 for _, value in counters
        ):
            raise ControlCenterError("SAFETY_COUNTERS_NONZERO")
        latest = self.latest_verified_backup()
        latest_restore = self.restore_receipts(limit=1)
        observed_at = _observation_timestamp(self.database.clock())
        return SystemDatabaseStatus(
            application_schema_version=APPLICATION_SCHEMA_VERSION,
            build_version=APPLICATION_BUILD_VERSION,
            schema_version=verification.schema_version,
            database_status="HEALTHY" if verification.healthy else "UNHEALTHY",
            quick_check=verification.quick_check,
            integrity_check=verification.integrity_check or "NOT_REQUESTED",
            foreign_key_status=(
                "OK" if not verification.foreign_key_violations else "VIOLATIONS"
            ),
            projection_status=(
                "OK"
                if sales_credit_projection.valid and doi_projection.ok
                else "DRIFT"
            ),
            database_location_class=privacy_safe_path_class(
                self.database.path,
                repository_root=repository_root,
            ),
            database_size_bytes=self.database.path.stat().st_size,
            migrations=tuple(
                (item.version, item.name, item.sha256, item.applied_at_utc)
                for item in verification.migration_receipts
            ),
            latest_backup=latest,
            latest_restore=None if not latest_restore else latest_restore[0],
            verification_observed_at=observed_at,
            safety_observed_at=observed_at,
            safety_counters=counters,
        )

    @staticmethod
    def _require_id(value: object, code: str) -> str:
        if type(value) is not str or _SYNTHETIC_ID.fullmatch(value) is None:
            raise ControlCenterError(code)
        return value


__all__ = [
    "CONTROL_CENTER_SCHEMA_VERSION",
    "DEFAULT_EXTENSION_STALE_AFTER",
    "DENOMINATOR_REGISTRY_VERSION",
    "EXTENSION_STATUS_SCHEMA_VERSION",
    "M4_BENCHMARK_REFERENCE",
    "M4_BENCHMARK_REFERENCE_VERSION",
    "METRIC_DENOMINATOR_REGISTRY",
    "BackupSummary",
    "BenchmarkReference",
    "ControlCenterApplication",
    "ControlCenterError",
    "CurrencyTotal",
    "DOICaseSummary",
    "DashboardMetrics",
    "ExtensionObservation",
    "ExtensionStatus",
    "ExtensionStatusState",
    "HumanReviewItem",
    "MetricDefinition",
    "MetricWindow",
    "Page",
    "PageRequest",
    "ProjectionReconciliation",
    "RateValue",
    "RestoreSummary",
    "SafeErrorSummary",
    "SalesCreditCaseSummary",
    "SystemDatabaseStatus",
    "TimelineEvent",
    "classify_extension_status",
    "denominator_registry",
    "privacy_safe_path_class",
]
