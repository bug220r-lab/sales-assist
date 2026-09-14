"""Accessible, fail-closed HTML rendering for the local Milestone 7 Control Center.

The renderer consumes only closed dictionaries produced by ``ControlCenterApplication``.
It performs no rule evaluation, projection update, SQL access, or action authorization.  Every
dynamic value is privacy checked and HTML escaped before it can enter markup; action forms merely
describe the closed local transport contract enforced again by the server/application boundary.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html import escape
from typing import Final, Never

from synthetic_sales_assist import __version__ as APPLICATION_VERSION
from synthetic_sales_assist.application.control_center import (
    CONTROL_CENTER_SCHEMA_VERSION,
    DENOMINATOR_REGISTRY_VERSION,
    EXTENSION_STATUS_SCHEMA_VERSION,
    METRIC_DENOMINATOR_REGISTRY,
    M4_BENCHMARK_REFERENCE_VERSION,
    ExtensionStatusState,
)
from synthetic_sales_assist.application.views import (
    APPLICATION_BUILD_VERSION,
    APPLICATION_SCHEMA_VERSION,
)
from synthetic_sales_assist.domain.numeric import (
    CURRENCY_REGISTRY_VERSION,
    Money,
    MoneyViolation,
)
from synthetic_sales_assist.domain.registries import (
    RegistryLookupError,
    load_doi_registries,
)
from synthetic_sales_assist.domain.timestamps import (
    CanonicalTimestamp,
    TimestampValidationError,
)
from synthetic_sales_assist.portal.contracts import (
    API_REQUEST_SCHEMA_VERSION,
    API_SCHEMA_VERSION,
    DOM_SCHEMA_VERSION,
    MAX_RESPONSE_BODY_BYTES,
    PortalContractError,
    validate_dashboard_response,
)
from synthetic_sales_assist.portal.dashboard_assets import DASHBOARD_ASSET_MARKER
from synthetic_sales_assist.persistence.telemetry import SAFETY_COUNTER_NAMES
from synthetic_sales_assist.safety.chrome import CHROME_EXTENSION_VERSION
from synthetic_sales_assist.safety.identity import is_reserved_identity


DASHBOARD_DOM_VERSION: Final = "synthetic-sales-assist-dashboard-dom/v1"
MANAGER_OUTCOME_REQUEST_VERSION: Final = (
    "synthetic-sales-assist-manager-outcome-request/v1"
)
DOI_SCENARIO_SELECTION_REQUEST_VERSION: Final = (
    "synthetic-sales-assist-doi-scenario-selection-request/v1"
)
DATABASE_VERIFY_REQUEST_VERSION: Final = (
    "synthetic-sales-assist-database-verify-request/v1"
)
BACKUP_REQUEST_VERSION: Final = "synthetic-sales-assist-backup-request/v1"

_CSRF_TOKEN = re.compile(r"\A[0-9a-f]{64}\Z", re.ASCII)
_LOWER_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z", re.ASCII)
_SYNTHETIC_ID = re.compile(
    r"\ASYN-(?:ORDER|EVIDENCE|EVALUATION|RUN|SNAPSHOT)-[A-Z0-9][A-Z0-9-]{0,111}\Z",
    re.ASCII,
)
_LOOPBACK_ORIGIN = re.compile(
    r"\Ahttp://(?:127\.0\.0\.1|localhost):([0-9]{1,5})/?\Z",
    re.ASCII,
)
_UNSAFE_PATH = re.compile(
    r"(?:\A[/\\~]|[A-Za-z]:[/\\]|[/\\][Uu][Ss][Ee][Rr][Ss][/\\]|"
    r"\\\\|//|file:|device:)",
    re.ASCII,
)
_GOVERNED_ENUM = re.compile(r"\A[A-Z][A-Z0-9_]{0,95}\Z", re.ASCII)
_RECORD_DOMAIN = re.compile(
    r"\A[a-z][a-z0-9-]{0,95}/v[1-9][0-9]{0,8}\Z",
    re.ASCII,
)
_VERSION_IDENTIFIER = re.compile(
    r"\A[a-z][a-z0-9-]{0,95}/v(?:0|[1-9][0-9]{0,8})(?:\.[0-9]+){0,2}\Z",
    re.ASCII,
)
_TRANSITION_ID = re.compile(
    r"\ATR-(?:00[1-9]|0[1-9][0-9]|1(?:0[0-9]|1[0-5]))\Z",
    re.ASCII,
)
_SEMANTIC_VERSION = re.compile(
    r"\A(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z",
    re.ASCII,
)
_MIGRATION_WRITER_TIMESTAMP = re.compile(
    r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"\.[0-9]{6}Z\Z",
    re.ASCII,
)
_BACKUP_ID_PREFIX: Final = "SYN-EVIDENCE-BACKUP-"
_RESTORE_ID_PREFIX: Final = "SYN-EVIDENCE-RESTORE-"
_MIGRATION_NAME = re.compile(r"\A[a-z][a-z0-9_]{0,95}\Z", re.ASCII)
_ACTION_DATE = re.compile(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}\Z", re.ASCII)
_QUANTITY_TEXT = re.compile(
    r"\A(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z",
    re.ASCII,
)
_SYNTHETIC_SEARCH = re.compile(r"\ASYN-[A-Z0-9-]{1,92}\Z", re.ASCII)
_QUEUE_QUERY_MEMBERS: Final = frozenset(
    {"descending", "search", "sort_by", "state"}
)
_SALES_CREDIT_QUEUE_STATES: Final = (
    "AWAITING_SOURCE_REVIEW",
    "CHECKED_NO_ORDER_WINDOW_ACTIVE",
    "REVIEW_WINDOW_CLOSED_NO_ORDER",
    "CREDIT_CONFIRMED_TARGET_REP",
    "EVIDENCE_NEEDED",
    "VERIFIED_PREORDER_EVIDENCE",
    "OUTBOUND_EVIDENCE_HUMAN_REVIEW",
    "INBOUND_EVIDENCE_HUMAN_REVIEW",
    "TIMING_UNCERTAIN_HUMAN_REVIEW",
    "OTHER_REP_HUMAN_REVIEW",
    "ORDER_CHANGED_HUMAN_REVIEW",
    "CANCELED_REPLACEMENT_WINDOW_ACTIVE",
    "POSSIBLE_REPLACEMENT_HUMAN_REVIEW",
    "CANCELED_NO_REPLACEMENT",
    "MANUAL_REVIEW_REQUIRED",
)
_DOI_QUEUE_STATES: Final = (
    "DOI_OPPORTUNITY",
    "DOI_MANUAL_REVIEW",
    "DOI_EXCLUDED",
    "DOI_MONITOR",
)
_SC_WORKFLOW_STATES: Final = frozenset((*_SALES_CREDIT_QUEUE_STATES, "CLOSED"))
_DOI_STATES: Final = frozenset(_DOI_QUEUE_STATES)
_REQUEST_RESULT_STATES: Final = frozenset(
    {"CONFLICT", "ERROR", "FAILED_CLOSED", "HUMAN_REVIEW", "SUCCESS"}
)
_OPPORTUNITY_TYPES: Final = frozenset(
    {
        "DS_SEPARATION",
        "EXACT_MFG_ALTERNATE",
        "EXACT_SKU_RECHECK",
        "FULFILLMENT_SPLIT",
        "FUNCTIONAL_ALTERNATE",
        "MFG_CROSS_REFERENCE",
        "MFG_SUPERSESSION",
        "PARTIAL_QUANTITY_REVIEW",
    }
)
_AUDIT_NAMESPACES: Final = {
    "DOI_CASE": "EVIDENCE",
    "DOI_RUN": "RUN",
    "EVALUATION": "EVALUATION",
    "SALES_CREDIT_CASE": "ORDER",
}
_SC_AUDIT_EVENT_KINDS: Final = frozenset(
    {
        "CASE_CREATED",
        "CLOSED_MINIMIZED",
        "FACTS_APPENDED",
        "OUTCOME_RECORDED",
        "REPLACEMENT_PARENT_DETACHED",
    }
)
_DOI_ARTIFACT_KINDS: Final = frozenset(
    {
        "CASE_ADMISSION_PROOF",
        "CASE_SOURCE_BINDING",
        "COMPLETENESS_PROOF",
        "EVALUATION",
        "EXTRACTION_ATTEMPT",
        "INTERVENTION",
        "KPI_CONTRIBUTION",
        "LINE_CONTINUITY_PROOF",
        "LINE_SNAPSHOT",
        "OPPORTUNITY",
        "ORDER_SNAPSHOT",
        "RESULTING_LINK",
        "RESULTING_SEARCH",
        "RETENTION_BINDING",
    }
)
_DOI_STREAM_STATES: Final = {
    "ACTION_CONTEXT": frozenset(
        {"CLOSED_ABANDONED", "CLOSED_COMPLETED", "CLOSED_SUPERSEDED", "OPEN"}
    ),
    "ATTENTION": frozenset({"CLEAR", "SET"}),
    "CASE": frozenset({"ACTIVE", "CLOSED_HARD", "CLOSED_REVERSIBLE"}),
    "CONTACT": frozenset(
        {
            "BIDIRECTIONAL_OBSERVED",
            "INBOUND_OBSERVED",
            "NONE_OBSERVED",
            "OUTBOUND_OBSERVED",
            "UNKNOWN",
        }
    ),
    "CONTACT_WORKFLOW": frozenset(
        {
            "AWAITING_CUSTOMER",
            "CONTACT_ATTEMPTED",
            "CONTACT_REQUIRED",
            "CUSTOMER_APPROVED",
            "CUSTOMER_DECLINED",
            "NOT_CONTACTED",
            "NO_RESPONSE",
        }
    ),
    "DEDUPE": frozenset(
        {
            "APPROVED_AWAITING_VERIFICATION",
            "CANDIDATE",
            "CONFIRMED",
            "INCOMPLETE",
            "NOT_CANDIDATE",
            "NOT_PRESENT",
            "REJECTED",
            "SOURCE_PRESENT",
        }
    ),
    "HUMAN_FACT": frozenset(
        {
            "APPROVED",
            "COORDINATION_RESOLUTION_RECORDED",
            "CORRECTED",
            "NO_VIABLE_ALTERNATE",
            "OUT_OF_SCOPE",
            "REJECTED",
            "SCENARIO_GROUPED",
            "SCENARIO_SELECTED",
        }
    ),
    "INTERVENTION_VALUE": frozenset(
        {"CORRECTION", "FULL_REVERSAL", "INITIAL_VERIFIED_VALUE", "PARTIAL_REVERSAL"}
    ),
    "KPI": frozenset({"FINALIZED", "NOT_ELIGIBLE", "RETAINED"}),
    "LIFECYCLE": frozenset(),
    "RESULTING_LINK": frozenset({"AMBIGUOUS", "AUTO_LINKED", "HUMAN_CONFIRMED"}),
    "RESULTING_SEARCH": frozenset({"AMBIGUOUS", "NOT_FOUND"}),
    "WWC": frozenset(
        {
            "ACTIVE_OTHER_REP",
            "ACTIVE_SELF",
            "AUTHOR_AND_TIMING_UNCERTAIN",
            "AUTHOR_UNCERTAIN",
            "EXPIRED_OTHER_REP",
            "NOT_APPLICABLE",
            "TIMING_UNCERTAIN",
        }
    ),
}
_DATABASE_SCHEMA_VERSION: Final = 4
_DATABASE_LOCATION_CLASSES: Final = frozenset(
    {
        "LOCAL_APPLICATION_DATA",
        "LOCAL_FILESYSTEM",
        "LOCAL_TEMPORARY",
        "REPOSITORY_LOCAL",
    }
)
_MIGRATION_INVENTORY: Final = (
    (
        1,
        "foundation",
        "5693cfe9868f10868d134bd042ccc26271126be9eae847a214c26f57216d6638",
    ),
    (
        2,
        "shared_persistence",
        "5e6f5ea08a4cfd5ec6241da60c49721d99c246fa1e4251d44293a1487e749e31",
    ),
    (
        3,
        "sales_credit_persistence",
        "fd22b13f73d389422405bf222313e34a4aa5995f6b28610a222108a3da813395",
    ),
    (
        4,
        "doi_persistence",
        "5799e5fe3b0e1c9ffae948f6c6b0a820556a9a0d200b29d7c5751e80c475b09d",
    ),
)
_EXPECTED_EXTENSION_PACKAGE_SHA256: Final = (
    "3c0d145c789fb990c9fe849f16a031f397285de020ec14b6bb97551ddf1aca55"
)
_CANONICAL_DECIMAL = re.compile(
    r"\A(?:0|[1-9][0-9]*)\.[0-9]+\Z",
    re.ASCII,
)

_PAGE_TITLES: Final = {
    "overview": "Control Center overview",
    "campaign-replies": "Campaign Replies",
    "sales_credit_queue": "Sales Credit queue",
    "sales_credit_detail": "Sales Credit case",
    "doi_queue": "DOI queue",
    "doi_detail": "DOI case",
    "review": "Human-review queue",
    "audit": "Immutable audit timeline",
    "system": "System health",
    "database": "Database health",
    "backups": "Verified backups",
    "telemetry": "Telemetry and metric denominators",
    "extension": "Chrome extension status",
}

_METRICS_MEMBERS: Final = frozenset(
    {
        "active_doi_cases",
        "active_doi_opportunities",
        "active_sales_credit_cases",
        "current_human_review_items",
        "database_error_count",
        "doi_evaluation_result_distribution",
        "doi_state_distribution",
        "exact_replays",
        "failed_closed_rate",
        "failed_closed_requests",
        "human_review_rate",
        "manager_outcome_rate",
        "material_conflicts",
        "median_latency_ns",
        "opportunity_type_counts",
        "p95_latency_ns",
        "potential_by_currency",
        "potential_unavailable_count",
        "realized_by_currency",
        "request_result_distribution",
        "requests_received",
        "safety_counters",
        "schema_version",
        "sales_credit_result_distribution",
        "successful_request_rate",
        "successful_requests",
        "throughput_per_second",
        "unique_evaluations",
        "unresolved_overlap_count",
        "window",
    }
)
_RATE_MEMBERS: Final = frozenset(
    {"defined", "display", "denominator", "numerator"}
)
_CURRENCY_MEMBERS: Final = frozenset(
    {
        "amount_minor_units",
        "currency_code",
        "currency_registry_version",
        "currency_scale",
        "item_count",
    }
)
_TIMELINE_MEMBERS: Final = frozenset(
    {"event_id", "event_kind", "occurred_at", "sequence", "state", "transition_id"}
)
_SC_SUMMARY_MEMBERS: Final = frozenset(
    {
        "attribution",
        "current_evaluation_id",
        "human_review_required",
        "interaction_count",
        "manager_outcome",
        "order_id",
        "order_value_status",
        "unresolved_human_review",
        "updated_at",
        "workflow_state",
    }
)
_SC_DETAIL_MEMBERS: Final = frozenset(
    {
        "current_evaluation",
        "evidence",
        "interactions",
        "manager_outcomes",
        "reason_codes",
        "schema_version",
        "search_runs",
        "snapshots",
        "summary",
        "timeline",
    }
)
_SC_CURRENT_EVALUATION_MEMBERS: Final = frozenset(
    {
        "evaluation_id",
        "human_review_required",
        "material_sha256",
        "rule_pack_version",
        "snapshot_id",
    }
)
_SC_SNAPSHOT_MEMBERS: Final = frozenset(
    {
        "captured_at",
        "extraction_status",
        "is_current",
        "lifecycle_status",
        "line_count",
        "parser_version",
        "snapshot_id",
    }
)
_SC_INTERACTION_MEMBERS: Final = frozenset(
    {
        "interaction_id",
        "recorded_at",
        "source_ref_id",
        "timestamp_precision",
        "workflow_state",
    }
)
_SC_EVIDENCE_MEMBERS: Final = frozenset(
    {
        "classification",
        "evidence_id",
        "interaction_id",
        "occurred_at",
        "source_type",
    }
)
_SC_SEARCH_RUN_MEMBERS: Final = frozenset(
    {
        "adapter_version",
        "completed_at",
        "enumeration_complete",
        "identifier_count",
        "run_id",
        "started_at",
        "terminal_outcome",
        "trigger_type",
    }
)
_SC_PRIVACY_PROJECTED_MEMBERS: Final = frozenset(
    {
        "adapter_version",
        "classification",
        "extraction_status",
        "lifecycle_status",
        "parser_version",
        "rule_pack_version",
        "source_type",
        "terminal_outcome",
        "timestamp_precision",
        "trigger_type",
        "workflow_state",
    }
)
_DOI_SUMMARY_MEMBERS: Final = frozenset(
    {
        "aggregate_potential_state",
        "attention_causes",
        "case_id",
        "current_evaluation_id",
        "doi_state",
        "human_review_required",
        "lifecycle_state",
        "opportunity_types",
        "order_id",
        "reason_codes",
        "scenario_selection_state",
        "updated_at",
    }
)
_DOI_DETAIL_MEMBERS: Final = frozenset(
    {
        "current_attention_causes",
        "current_evaluation",
        "handling_flags",
        "human_fact_events",
        "interventions",
        "opportunities",
        "reason_explanations",
        "resulting_order_links",
        "retained_kpi_contributions",
        "schema_version",
        "scenario_selection",
        "source_completeness",
        "summary",
        "timeline",
        "value_events",
    }
)
_DOI_CURRENT_EVALUATION_MEMBERS: Final = frozenset(
    {
        "evaluation_id",
        "input_domain",
        "input_sha256",
        "output_domain",
        "output_sha256",
        "run_id",
        "snapshot_id",
        "top_level_state",
        "transition_id",
    }
)
_DOI_REASON_EXPLANATION_MEMBERS: Final = frozenset(
    {"class", "code", "description", "label", "registry_version"}
)
_DOI_SCENARIO_SELECTION_MEMBERS: Final = frozenset(
    {"option_opportunity_ids", "selected_opportunity_id", "selection_id"}
)
_DOI_OPPORTUNITY_MEMBERS: Final = frozenset(
    {
        "amount_minor_units",
        "currency_code",
        "currency_registry_version",
        "currency_scale",
        "mutual_exclusion_group_id",
        "opportunity_id",
        "opportunity_type",
        "potential_state",
        "scope_components",
    }
)
_DOI_SCOPE_MEMBERS: Final = frozenset(
    {"line_snapshot_id", "ordinal", "quantity_text", "role"}
)
_DOI_SOURCE_MEMBERS: Final = frozenset(
    {
        "completeness_proof_present",
        "completeness_sha256",
        "is_current",
        "line_count",
        "order_id",
        "record_domain",
        "record_sha256",
        "relevant_line_count",
        "run_id",
        "snapshot_id",
        "source_observed_at",
    }
)
_DOI_ATTENTION_MEMBERS: Final = frozenset(
    {
        "cause_key",
        "condition",
        "current_event_id",
        "current_event_occurred_at",
        "head_sha256",
        "projection_state",
        "record_domain",
        "record_sha256",
        "sequence",
        "stream_id",
    }
)
_DOI_HUMAN_FACT_MEMBERS: Final = frozenset(
    {
        "event_id",
        "occurred_at",
        "projection_state",
        "record_domain",
        "record_sha256",
        "sequence",
        "stream_id",
        "transition_id",
    }
)
_DOI_INTERVENTION_MEMBERS: Final = frozenset(
    {
        "action_occurred_at",
        "created_at",
        "head_sha256",
        "intervention_id",
        "intervention_type",
        "opportunity_id",
        "projection_version",
        "record_domain",
        "record_sha256",
        "status",
        "verification_events",
    }
)
_DOI_VERIFICATION_MEMBERS: Final = frozenset(
    {"event_id", "occurrence_id", "record_domain", "record_sha256"}
)
_DOI_LINK_MEMBERS: Final = frozenset(
    {
        "child_order_id",
        "current_revision",
        "head_sha256",
        "intervention_id",
        "link_id",
        "parent_order_id",
        "revisions",
        "state",
    }
)
_DOI_REVISION_MEMBERS: Final = frozenset(
    {
        "mapping_components",
        "predecessor_sha256",
        "record_domain",
        "record_sha256",
        "revision",
        "revision_id",
    }
)
_DOI_MAPPING_MEMBERS: Final = frozenset(
    {"child_line_id", "ordinal", "parent_line_id", "quantity_text"}
)
_DOI_VALUE_MEMBERS: Final = frozenset(
    {
        "amount_minor_units",
        "currency_code",
        "currency_registry_version",
        "currency_scale",
        "event_id",
        "event_type",
        "intervention_id",
        "occurrence_id",
        "predecessor_sha256",
        "record_domain",
        "record_sha256",
        "sequence",
    }
)
_DOI_KPI_MEMBERS: Final = frozenset(
    {
        "action_date",
        "amount_minor_units",
        "currency_code",
        "currency_registry_version",
        "currency_scale",
        "head_sha256",
        "intervention_id",
        "intervention_type",
        "revision",
    }
)
_DOI_PRIVACY_PROJECTED_MEMBERS: Final = frozenset(
    {
        "action_date",
        "class",
        "condition",
        "description",
        "event_type",
        "handling_flags",
        "input_domain",
        "intervention_type",
        "label",
        "line_snapshot_id",
        "output_domain",
        "projection_state",
        "quantity_text",
        "record_domain",
        "registry_version",
        "role",
        "top_level_state",
    }
)
_REVIEW_MEMBERS: Final = frozenset(
    {
        "action_available",
        "audit_subject_kind",
        "domain",
        "order_id",
        "reason_codes",
        "required_action",
        "source_completeness_state",
        "subject_id",
        "system_state",
    }
)
_EXTENSION_MEMBERS: Final = frozenset(
    {
        "expected_package_sha256",
        "expected_version",
        "last_seen_at",
        "observed_version",
        "schema_version",
        "stale_after_seconds",
        "state",
    }
)
_DATABASE_MEMBERS: Final = frozenset(
    {
        "application_schema_version",
        "build_version",
        "database_location_class",
        "database_size_bytes",
        "database_status",
        "foreign_key_status",
        "integrity_check",
        "latest_backup",
        "latest_restore",
        "migrations",
        "projection_status",
        "quick_check",
        "safety_counters",
        "safety_observed_at",
        "schema_version",
        "verification_observed_at",
    }
)
_BACKUP_MEMBERS: Final = frozenset(
    {
        "backup_id",
        "backup_sha256",
        "completed_at",
        "foreign_key_check",
        "quick_check",
        "schema_version",
        "status",
    }
)
_RESTORE_MEMBERS: Final = frozenset(
    {
        "backup_sha256",
        "completed_at",
        "error_code",
        "pre_restore_backup_id",
        "restore_id",
        "schema_version",
        "status",
    }
)
_SAFE_ERROR_MEMBERS: Final = frozenset(
    {"category", "code", "occurred_at", "retryable"}
)
_BENCHMARK_REFERENCE_MEMBERS: Final = frozenset(
    {
        "database_size_bytes",
        "exact_replays",
        "median_latency_ms",
        "p95_latency_ms",
        "throughput_per_second",
        "unique_evaluations",
        "verified_backup_sha256",
        "version",
    }
)
_OPERATIONAL_STATUS_MEMBERS: Final = frozenset(
    {
        "database_size_bytes",
        "latest_backup",
        "latest_restore",
        "safety_observed_at",
        "verification_observed_at",
    }
)


def _fail(code: str) -> Never:
    raise PortalContractError(code, status=500)


def _h(value: object) -> str:
    return escape(str(value), quote=True)


def _closed_mapping(
    value: object,
    members: frozenset[str],
    code: str,
) -> dict[str, object]:
    if type(value) is not dict or frozenset(value) != members:
        _fail(code)
    return value


def _list(value: object, code: str) -> list[object]:
    if type(value) is not list:
        _fail(code)
    return value


def _text(value: object, code: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if type(value) is not str or not value:
        _fail(code)
    return value


def _integer(value: object, code: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fail(code)
    return value


def _boolean(value: object, code: str) -> bool:
    if type(value) is not bool:
        _fail(code)
    return value


def _synthetic_id(value: object, code: str) -> str:
    text = _text(value, code)
    assert text is not None
    if _SYNTHETIC_ID.fullmatch(text) is None:
        _fail(code)
    return text


def _namespace_id(value: object, namespace: str, code: str) -> str:
    if not is_reserved_identity(value, expected_namespace=namespace):
        _fail(code)
    assert type(value) is str
    return value


def _evidence_kind_id(value: object, prefix: str, code: str) -> str:
    identifier = _namespace_id(value, "EVIDENCE", code)
    if not identifier.startswith(prefix) or len(identifier) == len(prefix):
        _fail(code)
    return identifier


def _lower_sha256(value: object, code: str, *, optional: bool = False) -> str | None:
    text = _text(value, code, optional=optional)
    if text is not None and _LOWER_SHA256.fullmatch(text) is None:
        _fail(code)
    return text


def _governed_enum(value: object, code: str) -> str:
    text = _text(value, code)
    assert text is not None
    if _GOVERNED_ENUM.fullmatch(text) is None:
        _fail(code)
    return text


def _reason_code(value: object, code: str) -> str:
    text = _text(value, code)
    assert text is not None
    if re.fullmatch(r"[A-Z][A-Z0-9_-]{0,95}", text, re.ASCII) is None:
        _fail(code)
    return text


def _record_domain(value: object, code: str) -> str:
    text = _text(value, code)
    assert text is not None
    if _RECORD_DOMAIN.fullmatch(text) is None:
        _fail(code)
    return text


def _version_identifier(value: object, code: str) -> str:
    text = _text(value, code)
    assert text is not None
    if _VERSION_IDENTIFIER.fullmatch(text) is None:
        _fail(code)
    return text


def _timestamp(value: object, code: str, *, optional: bool = False) -> str | None:
    text = _text(value, code, optional=optional)
    if text is None:
        return None
    try:
        accepted = CanonicalTimestamp(text)
    except TimestampValidationError:
        _fail(code)
    if accepted.value != text:
        _fail(code)
    return text


def _migration_timestamp(value: object) -> str:
    text = _text(value, "DASHBOARD_MIGRATION_TIMESTAMP_INVALID")
    assert text is not None
    if _MIGRATION_WRITER_TIMESTAMP.fullmatch(text) is not None:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            _fail("DASHBOARD_MIGRATION_TIMESTAMP_INVALID")
        if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != text:
            _fail("DASHBOARD_MIGRATION_TIMESTAMP_INVALID")
        return text
    accepted = _timestamp(text, "DASHBOARD_MIGRATION_TIMESTAMP_INVALID")
    assert accepted is not None
    return accepted


def _action_date(value: object, code: str) -> str:
    text = _text(value, code)
    assert text is not None
    if _ACTION_DATE.fullmatch(text) is None:
        _fail(code)
    try:
        accepted = date.fromisoformat(text)
    except ValueError:
        _fail(code)
    if accepted.isoformat() != text:
        _fail(code)
    return text


def _money_text(
    amount: object,
    currency: object,
    registry_version: object,
    scale: object,
    code: str,
) -> str:
    if type(amount) is not int:
        _fail(code)
    if type(currency) is not str or type(registry_version) is not str or type(scale) is not int:
        _fail(code)
    try:
        money = Money.from_minor_units(
            amount,
            currency_code=currency,
            registry_version=registry_version,
            scale=scale,
        )
    except MoneyViolation:
        _fail(code)
    return _format_minor_units(money.minor_units, money.scale, money.currency_code)


def _optional_money_text(item: Mapping[str, object], code: str) -> str:
    members = (
        item["amount_minor_units"],
        item["currency_code"],
        item["currency_registry_version"],
        item["currency_scale"],
    )
    if members[0] is None:
        if any(member is not None for member in members):
            _fail(code)
        return "Unavailable"
    if any(member is None for member in members):
        _fail(code)
    return _money_text(*members, code)


def _doi_privacy_check(value: object) -> object:
    """Run common privacy checks without rescanning strict governed DOI tokens."""

    def project(item: object, member: str | None = None) -> object:
        if (
            type(item) is str
            and member == "event_id"
            and _LOWER_SHA256.fullmatch(item) is not None
        ):
            return "SYN-EVIDENCE-DASHBOARD-HASH-EVENT"
        if type(item) is str and member == "line_snapshot_id":
            # The common scanner assigns this suffix to SNAPSHOT, while the binding DOI
            # primitive is an EVIDENCE identity already validated by this renderer.
            return "SYN-SNAPSHOT-DASHBOARD-GOVERNED-LINE"
        if type(item) is str and member in _DOI_PRIVACY_PROJECTED_MEMBERS:
            return "SYNTHETIC_GOVERNED_VALUE"
        if type(item) is dict:
            return {key: project(child, key) for key, child in item.items()}
        if type(item) is list:
            return [project(child, member) for child in item]
        return item

    _privacy_check(project(value))
    return value


def _sc_privacy_check(value: object) -> object:
    """Run common privacy checks after strict Sales Credit token validation."""

    def project(item: object, member: str | None = None) -> object:
        if type(item) is str and member in _SC_PRIVACY_PROJECTED_MEMBERS:
            return "SYNTHETIC_GOVERNED_VALUE"
        if type(item) is dict:
            return {key: project(child, key) for key, child in item.items()}
        if type(item) is list:
            return [project(child, member) for child in item]
        return item

    _privacy_check(project(value))
    return value


def _audit_kind(value: object) -> str:
    kind = _text(value, "DASHBOARD_AUDIT_KIND_INVALID")
    assert kind is not None
    if kind not in {"SALES_CREDIT_CASE", "DOI_CASE", "DOI_RUN", "EVALUATION"}:
        _fail("DASHBOARD_AUDIT_KIND_INVALID")
    return kind


def _audit_subject_id(value: object, kind: str, code: str) -> str:
    namespace = _AUDIT_NAMESPACES.get(kind)
    if namespace is None:
        _fail(code)
    return _namespace_id(value, namespace, code)


def _privacy_check(value: object) -> object:
    safe = validate_dashboard_response(value)

    def visit(item: object) -> None:
        if type(item) is str:
            origin_match = _LOOPBACK_ORIGIN.fullmatch(item)
            if origin_match is not None and int(origin_match.group(1)) <= 65_535:
                return
            if any(ord(character) < 32 for character in item) or _UNSAFE_PATH.search(item):
                _fail("DASHBOARD_PRIVATE_PATH_PROHIBITED")
            return
        if type(item) is dict:
            for child in item.values():
                visit(child)
            return
        if type(item) is list:
            for child in item:
                visit(child)

    visit(safe)
    return safe


def _service_origin(value: object) -> str:
    origin = _text(value, "DASHBOARD_SERVICE_ORIGIN_INVALID")
    assert origin is not None
    matched = _LOOPBACK_ORIGIN.fullmatch(origin)
    if (
        matched is None
        or not origin.endswith("/")
        or not 1 <= int(matched.group(1)) <= 65_535
    ):
        _fail("DASHBOARD_SERVICE_ORIGIN_INVALID")
    return origin


def _display(value: object) -> str:
    if value is None:
        return "Unavailable"
    if type(value) is bool:
        return "Yes" if value else "No"
    if type(value) in {str, int}:
        return str(value)
    if type(value) is list:
        return ", ".join(_display(item) for item in value) if value else "None"
    if type(value) is dict:
        return ", ".join(f"{key}: {_display(item)}" for key, item in value.items())
    _fail("DASHBOARD_DISPLAY_VALUE_INVALID")


def _humanize_token(value: object, code: str) -> str:
    text = _governed_enum(value, code)
    words = text.replace("_", " ").lower()
    humanized = words[:1].upper() + words[1:]
    return humanized.replace("Doi ", "DOI ").replace("Kpi ", "KPI ")


def _state(value: object) -> str:
    text = _text(value, "DASHBOARD_STATE_INVALID", optional=True)
    return "Unavailable" if text is None else text


def _state_badge(value: object) -> str:
    displayed = _state(value)
    upper = displayed.upper()
    if any(token in upper for token in ("FAIL", "CONFLICT", "UNHEALTHY", "MISMATCH")):
        severity = "error"
    elif any(
        token in upper
        for token in ("REVIEW", "REQUIRED", "STALE", "UNKNOWN", "UNAVAILABLE")
    ):
        severity = "attention"
    elif any(token in upper for token in ("PASS", "HEALTHY", "APPROVED", "RECORDED")):
        severity = "success"
    else:
        severity = "neutral"
    return (
        f'<span class="dashboard-state" data-severity="{severity}" '
        f'data-ssa-dashboard-state="{_h(displayed)}">{_h(displayed)}</span>'
    )


def _format_minor_units(amount: object, scale: object, currency: object) -> str:
    minor = _integer(amount, "DASHBOARD_MONEY_AMOUNT_INVALID", minimum=-10**30)
    digits = _integer(scale, "DASHBOARD_MONEY_SCALE_INVALID")
    code = _text(currency, "DASHBOARD_MONEY_CURRENCY_INVALID")
    assert code is not None
    if digits > 9 or re.fullmatch(r"[A-Z]{3}", code, re.ASCII) is None:
        _fail("DASHBOARD_MONEY_INVALID")
    sign = "-" if minor < 0 else ""
    absolute = str(abs(minor)).zfill(digits + 1)
    if digits:
        amount_text = f"{absolute[:-digits]}.{absolute[-digits:]}"
    else:
        amount_text = absolute
    return f"{sign}{amount_text} {code}"


def _table(
    *,
    caption: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    selector: str,
    empty_message: str = "No current synthetic records match this view.",
) -> str:
    header_cells = "".join(f'<th scope="col">{_h(item)}</th>' for item in headers)
    body_rows = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    if not body_rows:
        body_rows = (
            f'<tr><td colspan="{len(headers)}" class="dashboard-empty">'
            f"{_h(empty_message)}</td></tr>"
        )
    return f"""<div class="dashboard-table-wrap" data-ssa-dashboard-table="{_h(selector)}">
<table><caption>{_h(caption)}</caption><thead><tr>{header_cells}</tr></thead>
<tbody>{body_rows}</tbody></table></div>"""


def _definition_list(items: Sequence[tuple[str, object]]) -> str:
    return "<dl>" + "".join(
        f"<dt>{_h(label)}</dt><dd>{_h(_display(value))}</dd>" for label, value in items
    ) + "</dl>"


def _page(
    *,
    route_name: str,
    heading: str,
    lede: str,
    body: str,
    csrf_token: str,
    presentation: bool,
) -> bytes:
    if _CSRF_TOKEN.fullmatch(csrf_token) is None:
        _fail("DASHBOARD_CSRF_TOKEN_INVALID")
    if route_name not in _PAGE_TITLES:
        _fail("DASHBOARD_ROUTE_INVALID")
    active = (
        "sales-credit"
        if route_name.startswith("sales_credit")
        else "doi"
        if route_name.startswith("doi")
        else "system"
        if route_name in {"system", "database", "backups", "telemetry", "extension"}
        else route_name
    )
    nav_items = (
        ("overview", "/overview", "Overview"),
        ("sales-credit", "/sales-credit", "Sales Credit"),
        ("doi", "/doi", "DOI"),
        ("review", "/review", "Human review"),
        ("campaigns", "/campaigns", "Campaigns"),
        ("replies", "/replies", "Replies"),
        ("writing-history", "/writing-history", "Writing history"),
        ("campaign-replies", "/campaign-replies", "Campaign Replies"),
        ("system", "/system", "System"),
    )
    navigation = "".join(
        f'<a href="{path}"{(" aria-current=\"page\"" if key == active else "")}>{label}</a>'
        for key, path, label in nav_items
    )
    companion = route_name == "campaign-replies"
    banner = (
        '<div class="dashboard-synthetic-banner">'
        'Campaign Replies · Local companion · Read-only review</div>'
        if companion else
        '<div class="dashboard-synthetic-banner">'
        'Synthetic demo · Localhost only · Not connected to live systems</div>'
    )
    service_status = (
        "Campaign review runs in its own local service. Sales Credit and DOI remain synthetic."
        if companion else
        "Local loopback response received. Dashboard actions remain synthetic and local only."
    )
    footer = (
        "Review only. Editing and sending stay in the separate support application."
        if companion else
        "Fictional local demonstration · no external system access · current projections and "
        "immutable history are labeled separately."
    )
    doctype = "<!" + "doctype html>"
    html_open = "<" + f'html lang="en" data-ssa-dashboard-contract="{DASHBOARD_DOM_VERSION}">'
    document = f"""{doctype}
<!-- {DASHBOARD_ASSET_MARKER} -->
{html_open}
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="ssa-csrf-token" content="{_h(csrf_token)}">
  <title>{_h(_PAGE_TITLES[route_name])} · ECS Sales Assist</title>
  <link rel="stylesheet" href="/static/ssa-dashboard.css">
  <script src="/static/ssa-dashboard.js" defer></script>
</head>
<body data-ssa-dashboard-page="{_h(route_name)}"
      data-ssa-dashboard-presentation="{str(presentation).lower()}">
  <a class="dashboard-skip-link" href="#ssa-dashboard-main">Skip to main content</a>
  {banner}
  <header class="dashboard-header">
    <span class="dashboard-brand">ECS Sales Assist</span>
    <nav class="dashboard-nav" aria-label="Primary">{navigation}</nav>
  </header>
  <aside class="dashboard-service-status" role="status" aria-label="Local service status"
         data-ssa-dashboard-status="LOCAL_RESPONSE">
    {_h(service_status)}
  </aside>
  <main id="ssa-dashboard-main" class="dashboard-main dashboard-stack" tabindex="-1"
        data-ssa-page-kind="control-center-{_h(route_name)}"
        data-ssa-schema-version="{DOM_SCHEMA_VERSION}"
        data-ssa-dashboard-schema-version="{DASHBOARD_DOM_VERSION}">
    <header><h1>{_h(heading)}</h1><p class="dashboard-lede">{_h(lede)}</p></header>
    {body}
  </main>
  <footer class="dashboard-footer">
    {_h(footer)}
  </footer>
</body>
</html>"""
    encoded = document.encode("utf-8")
    if len(encoded) > MAX_RESPONSE_BODY_BYTES:
        _fail("DASHBOARD_RESPONSE_BODY_TOO_LARGE")
    return encoded


def render_campaign_replies(csrf_token: str, *, enabled: bool = False) -> bytes:
    """Render only the companion shell; never accept or query customer records."""

    if enabled:
        body = """<section class="dashboard-companion" aria-label="Campaign reply review">
<div class="dashboard-companion-tools">
<p>Search drafts, review their context, and open the conversation to make changes.</p>
<a href="http://127.0.0.1:8770/" target="_blank" rel="noopener noreferrer">
Open dashboard separately ↗</a></div>
<iframe class="dashboard-companion-frame" src="http://127.0.0.1:8770/?embedded=1"
 title="Campaign reply review dashboard" referrerpolicy="no-referrer"
 sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"></iframe>
<p class="dashboard-help">If the review panel does not load, start the campaign dashboard
on this PC, then reload this page. Its review timestamps appear inside the panel.</p>
</section>"""
    else:
        body = """<section class="dashboard-panel" aria-label="Campaign companion setup">
<h2>Campaign dashboard is not enabled</h2>
<p>This view connects to a separately running, read-only dashboard on this PC.</p>
<p>Start the campaign dashboard, then start Sales Assist at
<code>http://127.0.0.1:8765</code> with <code>SSA_CAMPAIGN_REPLIES=1</code>.</p>
<p>The synthetic Sales Credit and DOI modules remain independent.</p></section>"""
    return _page(
        route_name="campaign-replies",
        heading="Campaign Replies",
        lede="Your draft review workspace, alongside Sales Credit and DOI.",
        body=body,
        csrf_token=csrf_token,
        presentation=False,
    )


def _metric_card(
    metric_id: str,
    label: str,
    value: object,
    window: object,
    *,
    note: str,
) -> str:
    return f"""<article class="dashboard-card" data-ssa-dashboard-card="{_h(metric_id)}">
<h2>{_h(label)}</h2><strong class="dashboard-value">{_h(_display(value))}</strong>
<p class="dashboard-meta">{_h(note)} · Window: {_h(_display(window))}</p>
<a href="/system/telemetry#{_h(metric_id)}">View numerator, denominator, and exclusions</a>
</article>"""


def _status_card(
    card_id: str,
    label: str,
    value: object,
    note: str,
    href: str,
) -> str:
    return f"""<article class="dashboard-card"
 data-ssa-dashboard-card="{_h(card_id)}">
<h2>{_h(label)}</h2><strong class="dashboard-value">{_h(_display(value))}</strong>
<p class="dashboard-meta">{_h(note)}</p><a href="{_h(href)}">View current evidence</a>
</article>"""


def _validated_rate(value: object, code: str) -> dict[str, object]:
    rate = _closed_mapping(value, _RATE_MEMBERS, code)
    defined = _boolean(rate["defined"], code)
    numerator = _integer(rate["numerator"], code)
    denominator = _integer(rate["denominator"], code)
    display = _text(rate["display"], code)
    if numerator > denominator:
        _fail(code)
    expected = "N/A" if denominator == 0 else f"{numerator / denominator:.1%}"
    if defined != (denominator > 0) or display != expected:
        _fail(code)
    return rate


def _validated_metric_window(value: object) -> str:
    window = _text(value, "DASHBOARD_METRIC_WINDOW_INVALID")
    assert window is not None
    if window == "ALL_DURABLE_HISTORY":
        return window
    if not window.startswith("[") or not window.endswith(")"):
        _fail("DASHBOARD_METRIC_WINDOW_INVALID")
    parts = window[1:-1].split(", ")
    if len(parts) != 2:
        _fail("DASHBOARD_METRIC_WINDOW_INVALID")
    start_text, end_text = parts
    start = None
    end = None
    if start_text != "-infinity":
        _timestamp(start_text, "DASHBOARD_METRIC_WINDOW_INVALID")
        start = CanonicalTimestamp(start_text)
    if end_text != "+infinity":
        _timestamp(end_text, "DASHBOARD_METRIC_WINDOW_INVALID")
        end = CanonicalTimestamp(end_text)
    if start is not None and end is not None and (
        start.epoch_seconds,
        start.nanosecond,
    ) >= (end.epoch_seconds, end.nanosecond):
        _fail("DASHBOARD_METRIC_WINDOW_INVALID")
    return window


def _validated_currency_totals(value: object, code: str) -> list[object]:
    items = _list(value, code)
    observed: list[tuple[str, str, int]] = []
    for raw in items:
        item = _closed_mapping(raw, _CURRENCY_MEMBERS, code)
        amount = item["amount_minor_units"]
        currency = item["currency_code"]
        registry = item["currency_registry_version"]
        scale = item["currency_scale"]
        if registry != CURRENCY_REGISTRY_VERSION:
            _fail(code)
        _integer(amount, code)
        _money_text(amount, currency, registry, scale, code)
        _integer(item["item_count"], code, minimum=1)
        assert type(currency) is str and type(registry) is str and type(scale) is int
        observed.append((currency, registry, scale))
    if observed != sorted(set(observed)):
        _fail(code)
    return items


def _zero_safety_counters(value: object, code: str) -> dict[str, object]:
    if type(value) is not dict or frozenset(value) != frozenset(SAFETY_COUNTER_NAMES):
        _fail(code)
    if any(type(count) is not int or count != 0 for count in value.values()):
        _fail(code)
    return value


def _validated_metrics(value: object) -> dict[str, object]:
    metrics = _closed_mapping(value, _METRICS_MEMBERS, "DASHBOARD_METRICS_INVALID")
    if metrics["schema_version"] != DENOMINATOR_REGISTRY_VERSION:
        _fail("DASHBOARD_METRICS_VERSION_INVALID")
    counts = (
        "active_doi_cases",
        "active_doi_opportunities",
        "active_sales_credit_cases",
        "current_human_review_items",
        "database_error_count",
        "exact_replays",
        "failed_closed_requests",
        "material_conflicts",
        "potential_unavailable_count",
        "requests_received",
        "successful_requests",
        "unique_evaluations",
        "unresolved_overlap_count",
    )
    accepted_counts = {
        member: _integer(metrics[member], "DASHBOARD_METRIC_COUNT_INVALID")
        for member in counts
    }
    requests = accepted_counts["requests_received"]
    window = _validated_metric_window(metrics["window"])
    for member in (
        "database_error_count",
        "exact_replays",
        "failed_closed_requests",
        "material_conflicts",
        "successful_requests",
    ):
        if accepted_counts[member] > requests:
            _fail("DASHBOARD_METRIC_RECONCILIATION_INVALID")
    if accepted_counts["unresolved_overlap_count"] > accepted_counts[
        "potential_unavailable_count"
    ]:
        _fail("DASHBOARD_METRIC_RECONCILIATION_INVALID")
    if accepted_counts["current_human_review_items"] > (
        accepted_counts["active_sales_credit_cases"]
        + accepted_counts["active_doi_cases"]
    ):
        _fail("DASHBOARD_METRIC_RECONCILIATION_INVALID")
    # Human selection can append a durable evaluation outside processing telemetry.
    # These independently defined populations have no cross-population cardinality bound.

    rates = {
        member: _validated_rate(metrics[member], "DASHBOARD_RATE_INVALID")
        for member in (
            "failed_closed_rate",
            "human_review_rate",
            "manager_outcome_rate",
            "successful_request_rate",
        )
    }
    expected_rate_counts = {
        "failed_closed_rate": (
            accepted_counts["failed_closed_requests"],
            requests,
        ),
        "human_review_rate": (
            rates["human_review_rate"]["numerator"],
            accepted_counts["unique_evaluations"],
        ),
        "successful_request_rate": (
            accepted_counts["successful_requests"],
            requests,
        ),
    }
    for member, (numerator, denominator) in expected_rate_counts.items():
        if rates[member]["numerator"] != numerator or rates[member]["denominator"] != denominator:
            _fail("DASHBOARD_RATE_RECONCILIATION_INVALID")

    distribution_members = {
        "doi_evaluation_result_distribution": _DOI_STATES,
        "doi_state_distribution": _DOI_STATES,
        "opportunity_type_counts": _OPPORTUNITY_TYPES,
        "request_result_distribution": _REQUEST_RESULT_STATES,
        "sales_credit_result_distribution": _SC_WORKFLOW_STATES,
    }
    distributions = {
        member: _distribution(
            metrics[member],
            "DASHBOARD_RESULT_DISTRIBUTION_INVALID",
            allowed=allowed,
        )
        for member, allowed in distribution_members.items()
    }
    if (
        sum(distributions["request_result_distribution"].values()) != requests
        or sum(distributions["doi_state_distribution"].values())
        != accepted_counts["active_doi_cases"]
        or sum(distributions["opportunity_type_counts"].values())
        != accepted_counts["active_doi_opportunities"]
        or sum(distributions["doi_evaluation_result_distribution"].values())
        + sum(distributions["sales_credit_result_distribution"].values())
        != accepted_counts["unique_evaluations"]
    ):
        _fail("DASHBOARD_METRIC_DISTRIBUTION_RECONCILIATION_INVALID")
    request_results = distributions["request_result_distribution"]
    if (
        request_results.get("FAILED_CLOSED", 0)
        != accepted_counts["failed_closed_requests"]
        or request_results.get("CONFLICT", 0) != accepted_counts["material_conflicts"]
        or accepted_counts["database_error_count"]
        > request_results.get("ERROR", 0)
        or request_results.get("SUCCESS", 0) + request_results.get("HUMAN_REVIEW", 0)
        != accepted_counts["successful_requests"]
    ):
        _fail("DASHBOARD_METRIC_DISTRIBUTION_RECONCILIATION_INVALID")

    median = metrics["median_latency_ns"]
    p95 = metrics["p95_latency_ns"]
    if requests == 0:
        if median is not None or p95 is not None or metrics["throughput_per_second"] is not None:
            _fail("DASHBOARD_LATENCY_RECONCILIATION_INVALID")
    else:
        median_value = _integer(median, "DASHBOARD_LATENCY_INVALID")
        p95_value = _integer(p95, "DASHBOARD_LATENCY_INVALID")
        if median_value > p95_value:
            _fail("DASHBOARD_LATENCY_INVALID")
    throughput = metrics["throughput_per_second"]
    if throughput is not None:
        throughput_text = _text(throughput, "DASHBOARD_THROUGHPUT_INVALID")
        assert throughput_text is not None
        try:
            throughput_value = Decimal(throughput_text)
        except InvalidOperation:
            _fail("DASHBOARD_THROUGHPUT_INVALID")
        if _CANONICAL_DECIMAL.fullmatch(throughput_text) is None or throughput_value <= 0:
            _fail("DASHBOARD_THROUGHPUT_INVALID")
    potential = _validated_currency_totals(
        metrics["potential_by_currency"],
        "DASHBOARD_POTENTIAL_TOTALS_INVALID",
    )
    _validated_currency_totals(
        metrics["realized_by_currency"],
        "DASHBOARD_REALIZED_TOTALS_INVALID",
    )
    available_potential = sum(
        _integer(item["item_count"], "DASHBOARD_POTENTIAL_TOTALS_INVALID")
        for item in potential
        if type(item) is dict
    )
    if (
        available_potential + accepted_counts["potential_unavailable_count"]
        != accepted_counts["active_doi_cases"]
    ):
        _fail("DASHBOARD_POTENTIAL_TOTALS_RECONCILIATION_INVALID")
    _zero_safety_counters(
        metrics["safety_counters"],
        "DASHBOARD_SAFETY_COUNTERS_INVALID",
    )
    return metrics


def render_overview(data: object, csrf_token: str, *, presentation: bool = False) -> bytes:
    root = _closed_mapping(
        _privacy_check(data),
        frozenset({"metrics", "reconciliation", "schema_version", "system"}),
        "DASHBOARD_OVERVIEW_INVALID",
    )
    if root["schema_version"] != CONTROL_CENTER_SCHEMA_VERSION:
        _fail("DASHBOARD_OVERVIEW_VERSION_INVALID")
    metrics = _validated_metrics(root["metrics"])
    reconciliation = _closed_mapping(
        root["reconciliation"],
        frozenset(
            {
                "active_doi_cases",
                "active_sales_credit_cases",
                "current_human_review_items",
                "doi_history_events",
                "exact_replays",
                "material_conflicts",
                "sales_credit_history_events",
                "unique_evaluations",
            }
        ),
        "DASHBOARD_RECONCILIATION_INVALID",
    )
    reconciliation_counts = {
        member: _integer(
            reconciliation[member],
            "DASHBOARD_RECONCILIATION_COUNT_INVALID",
        )
        for member in reconciliation
    }
    reconciliation_metrics = {
        "active_doi_cases": "active_doi_cases",
        "active_sales_credit_cases": "active_sales_credit_cases",
        "current_human_review_items": "current_human_review_items",
        "exact_replays": "exact_replays",
        "material_conflicts": "material_conflicts",
        "unique_evaluations": "unique_evaluations",
    }
    if any(
        reconciliation_counts[member] != metrics[metric_member]
        for member, metric_member in reconciliation_metrics.items()
    ):
        _fail("DASHBOARD_RECONCILIATION_MISMATCH")
    if (
        reconciliation_counts["active_sales_credit_cases"]
        > reconciliation_counts["sales_credit_history_events"]
        or reconciliation_counts["active_doi_cases"]
        > reconciliation_counts["doi_history_events"]
    ):
        _fail("DASHBOARD_RECONCILIATION_HISTORY_INVALID")
    system = _closed_mapping(
        root["system"],
        frozenset(
            {
                "database_status",
                "extension_status",
                "latest_backup",
                "service_status",
            }
        ),
        "DASHBOARD_OVERVIEW_SYSTEM_INVALID",
    )
    database_status = _text(
        system["database_status"],
        "DASHBOARD_DATABASE_STATUS_INVALID",
    )
    extension_status = _text(
        system["extension_status"],
        "DASHBOARD_EXTENSION_STATE_INVALID",
    )
    service_status = _text(
        system["service_status"],
        "DASHBOARD_SERVICE_STATUS_INVALID",
    )
    if database_status not in {"HEALTHY", "UNHEALTHY"}:
        _fail("DASHBOARD_DATABASE_STATUS_INVALID")
    if extension_status not in ExtensionStatusState.ALL:
        _fail("DASHBOARD_EXTENSION_STATE_INVALID")
    if service_status not in {"FAIL", "PASS"}:
        _fail("DASHBOARD_SERVICE_STATUS_INVALID")
    if service_status == "PASS" and database_status != "HEALTHY":
        _fail("DASHBOARD_OVERVIEW_SYSTEM_COHERENCE_INVALID")
    window = metrics["window"]
    cards = (
        (
            "requests_received",
            "Business requests received",
            metrics["requests_received"],
            "Terminal business requests",
        ),
        (
            "unique_evaluations",
            "Unique new evaluations",
            metrics["unique_evaluations"],
            "Durable evaluation IDs; replays excluded",
        ),
        (
            "exact_replays",
            "Exact replays",
            metrics["exact_replays"],
            "History receipts; not new evaluations",
        ),
        (
            "material_conflicts",
            "Material conflicts",
            metrics["material_conflicts"],
            "Rejected changed-material requests",
        ),
        (
            "successful_requests",
            "Successful requests",
            metrics["successful_requests"],
            "Successful terminal business requests",
        ),
        (
            "failed_closed_requests",
            "Failed-closed requests",
            metrics["failed_closed_requests"],
            "Terminal requests stopped safely",
        ),
        (
            "active_sales_credit_cases",
            "Current Sales Credit cases",
            metrics["active_sales_credit_cases"],
            "Current nonclosed projections",
        ),
        (
            "active_doi_cases",
            "Current DOI cases",
            metrics["active_doi_cases"],
            "Current active projections",
        ),
        (
            "active_doi_opportunities",
            "Current active DOI opportunities",
            metrics["active_doi_opportunities"],
            "Opportunity count can exceed case count",
        ),
        (
            "current_human_review_items",
            "Current human-review items",
            metrics["current_human_review_items"],
            "Unresolved current projections only",
        ),
        (
            "median_latency_ns",
            "Median processing latency",
            metrics["median_latency_ns"],
            "Nanoseconds; N/A for an empty sample",
        ),
        (
            "p95_latency_ns",
            "P95 processing latency",
            metrics["p95_latency_ns"],
            "Nanoseconds; nearest-rank P95",
        ),
    )
    card_html = "".join(
        _metric_card(metric_id, label, value, window, note=note)
        for metric_id, label, value, note in cards
    )
    latest_backup = system["latest_backup"]
    if latest_backup is None:
        latest_backup_value = "N/A"
        latest_backup_note = "No verified backup receipt is currently available"
    else:
        backup = _backup(latest_backup)
        if backup["status"] != "COMPLETED":
            _fail("DASHBOARD_BACKUP_VERIFICATION_INVALID")
        latest_backup_value = backup["status"]
        latest_backup_note = f"Completed: {_display(backup['completed_at'])}"
    status_cards = "".join(
        (
            _status_card(
                "service-status",
                "Service status",
                system["service_status"],
                "Owned localhost listener",
                "/system",
            ),
            _status_card(
                "database-status",
                "Database health",
                system["database_status"],
                "Current schema and projection verification",
                "/system/database",
            ),
            _status_card(
                "latest-backup",
                "Latest verified backup",
                latest_backup_value,
                latest_backup_note,
                "/system/backups",
            ),
            _status_card(
                "extension-status",
                "Extension status",
                system["extension_status"],
                "Package presence alone is not installation evidence",
                "/system/extension",
            ),
        )
    )
    distributions = _closed_mapping(
        metrics["doi_state_distribution"],
        frozenset(
            metrics["doi_state_distribution"]
            if type(metrics["doi_state_distribution"]) is dict
            else ()
        ),
        "DASHBOARD_DOI_DISTRIBUTION_INVALID",
    )
    distribution_rows = [
        (_h(state), _h(_integer(count, "DASHBOARD_DOI_COUNT_INVALID")))
        for state, count in sorted(distributions.items())
    ]
    safety = _closed_mapping(
        metrics["safety_counters"],
        frozenset(
            metrics["safety_counters"]
            if type(metrics["safety_counters"]) is dict
            else ()
        ),
        "DASHBOARD_SAFETY_COUNTERS_INVALID",
    )
    safety_rows = [
        (_h(name), _h(_integer(value, "DASHBOARD_SAFETY_COUNTER_INVALID")))
        for name, value in sorted(safety.items())
    ]
    history_rows = [
        ("Current Sales Credit projections", reconciliation["active_sales_credit_cases"]),
        ("Immutable Sales Credit history events", reconciliation["sales_credit_history_events"]),
        ("Current DOI projections", reconciliation["active_doi_cases"]),
        ("Immutable DOI history events", reconciliation["doi_history_events"]),
    ]
    body = f"""<section class="dashboard-grid" aria-label="Current operational metrics">
{card_html}{status_cards}</section>
<section class="dashboard-split">
  <article class="dashboard-panel">
    <h2>Current DOI state distribution</h2>
    {_table(
        caption="Current DOI cases by state",
        headers=("State", "Case count"),
        rows=distribution_rows,
        selector="doi-state-distribution",
    )}
  </article>
  <article class="dashboard-panel">
    <h2>Current projections versus immutable history</h2>
    {_table(
        caption="Projection and history populations",
        headers=("Population", "Count"),
        rows=[(_h(label), _h(value)) for label, value in history_rows],
        selector="projection-history-reconciliation",
    )}
  </article>
</section>
<section class="dashboard-panel" data-ssa-dashboard-card="safety-counters">
  <h2>All nine safety counters</h2>
  {_table(
      caption="Current safety counter values",
      headers=("Counter", "Value"),
      rows=safety_rows,
      selector="safety-counters",
  )}
</section>"""
    return _page(
        route_name="overview",
        heading="Local Control Center overview",
        lede=(
            "Current queue cards come from current projections. Replay, conflict, and history "
            "totals remain separate and cannot inflate active work."
        ),
        body=body,
        csrf_token=csrf_token,
        presentation=presentation,
    )


def _queue_root(
    data: object,
    code: str,
    *,
    sort_fields: frozenset[str],
    state_values: frozenset[str],
) -> dict[str, object]:
    root = _closed_mapping(
        data,
        frozenset(
            {"items", "limit", "offset", "query", "schema_version", "total_count"}
        ),
        code,
    )
    if root["schema_version"] != CONTROL_CENTER_SCHEMA_VERSION:
        _fail(f"{code}_VERSION")
    items = _list(root["items"], f"{code}_ITEMS")
    limit = _integer(root["limit"], f"{code}_LIMIT", minimum=1)
    offset = _integer(root["offset"], f"{code}_OFFSET")
    total = _integer(root["total_count"], f"{code}_TOTAL")
    query = _closed_mapping(root["query"], _QUEUE_QUERY_MEMBERS, f"{code}_QUERY")
    search = _text(query["search"], f"{code}_SEARCH", optional=True)
    if search is not None and _SYNTHETIC_SEARCH.fullmatch(search) is None:
        _fail(f"{code}_SEARCH")
    state = _text(query["state"], f"{code}_STATE", optional=True)
    if state is not None and state not in state_values:
        _fail(f"{code}_STATE")
    sort_by = _text(query["sort_by"], f"{code}_SORT")
    if sort_by not in sort_fields:
        _fail(f"{code}_SORT")
    _boolean(query["descending"], f"{code}_DIRECTION")
    if (
        limit not in frozenset({10, 25, 50})
        or offset % limit != 0
        or len(items) > limit
        or (offset < total and not items)
        or (items and offset >= total)
        or (items and offset + len(items) > total)
    ):
        _fail(f"{code}_PAGINATION")
    _privacy_check(root)
    return root


def _selected(selected: bool) -> str:
    return " selected" if selected else ""


def _filter_form(
    route: str,
    sort_options: Sequence[tuple[str, str]],
    state_options: Sequence[str],
    query: Mapping[str, object],
    page_size: int,
    *,
    presentation: bool,
) -> str:
    search = "" if query["search"] is None else str(query["search"])
    current_state = query["state"]
    current_sort = query["sort_by"]
    descending = bool(query["descending"])
    options = "".join(
        f'<option value="{_h(value)}"{_selected(value == current_sort)}>{_h(label)}</option>'
        for value, label in sort_options
    )
    states = '<option value="">All current states</option>' + "".join(
        f'<option value="{_h(value)}"{_selected(value == current_state)}>'
        f"{_h(_humanize_token(value, 'DASHBOARD_QUEUE_STATE_INVALID'))}</option>"
        for value in state_options
    )
    sizes = "".join(
        f'<option value="{value}"{_selected(value == page_size)}>{value}</option>'
        for value in (10, 25, 50)
    )
    presentation_member = (
        '<input type="hidden" name="presentation" value="1">' if presentation else ""
    )
    return f"""<form class="dashboard-panel dashboard-filter" method="get" action="{route}"
      role="search" aria-label="Current synthetic queue filters">
  <input type="hidden" name="page" value="1">
  {presentation_member}
  <label class="dashboard-field"><span>Search synthetic ID</span>
    <input name="q" value="{_h(search)}" maxlength="96" pattern="SYN-[A-Z0-9-]+"
      autocomplete="off">
  </label>
  <label class="dashboard-field"><span>Current state</span>
    <select name="state">{states}</select></label>
  <label class="dashboard-field"><span>Sort by</span>
    <select name="sort">{options}</select></label>
  <label class="dashboard-field"><span>Direction</span><select name="direction">
    <option value="desc"{_selected(descending)}>Descending</option>
    <option value="asc"{_selected(not descending)}>Ascending</option>
  </select></label>
  <label class="dashboard-field"><span>Rows</span>
    <select name="page_size">{sizes}</select></label>
  <button type="submit">Apply filters</button>
</form>"""


def _queue_href(
    route: str,
    page: int,
    limit: int,
    query: Mapping[str, object],
    *,
    presentation: bool,
) -> str:
    pairs: list[tuple[str, object]] = []
    if query["search"] is not None:
        pairs.append(("q", query["search"]))
    if query["state"] is not None:
        pairs.append(("state", query["state"]))
    pairs.extend(
        (
            ("sort", query["sort_by"]),
            ("direction", "desc" if query["descending"] else "asc"),
            ("page", page),
            ("page_size", limit),
        )
    )
    if presentation:
        pairs.append(("presentation", 1))
    encoded = "&amp;".join(f"{name}={_h(value)}" for name, value in pairs)
    return f"{route}?{encoded}"


def _pagination(
    route: str,
    offset: int,
    limit: int,
    total: int,
    query: Mapping[str, object],
    *,
    presentation: bool,
) -> str:
    links: list[str] = []
    current_page = offset // limit + 1
    if offset > 0:
        previous = _queue_href(
            route,
            current_page - 1,
            limit,
            query,
            presentation=presentation,
        )
        links.append(
            f'<a href="{previous}">Previous page</a>'
        )
    if offset + limit < total:
        following = _queue_href(
            route,
            current_page + 1,
            limit,
            query,
            presentation=presentation,
        )
        links.append(
            f'<a href="{following}">Next page</a>'
        )
    if offset > 0 and offset >= total:
        links.append(
            f"<span>No results on requested page {current_page}; {total} total.</span>"
        )
    else:
        start = min(offset + 1, total) if total else 0
        end = min(offset + limit, total)
        links.append(f"<span>Showing {start}–{end} of {total}</span>")
    return '<nav class="dashboard-pagination" aria-label="Queue pages">' + "".join(links) + "</nav>"


def render_sales_credit_queue(
    data: object,
    csrf_token: str,
    *,
    presentation: bool = False,
) -> bytes:
    root = _queue_root(
        data,
        "DASHBOARD_SC_QUEUE_INVALID",
        sort_fields=frozenset({"order_id", "updated_at", "workflow_state"}),
        state_values=frozenset(_SALES_CREDIT_QUEUE_STATES),
    )
    query = _closed_mapping(
        root["query"],
        _QUEUE_QUERY_MEMBERS,
        "DASHBOARD_SC_QUEUE_QUERY_INVALID",
    )
    rows: list[tuple[str, ...]] = []
    for raw in _list(root["items"], "DASHBOARD_SC_QUEUE_ITEMS_INVALID"):
        item = _closed_mapping(raw, _SC_SUMMARY_MEMBERS, "DASHBOARD_SC_SUMMARY_INVALID")
        order_id = _synthetic_id(item["order_id"], "DASHBOARD_SC_ORDER_ID_INVALID")
        rows.append(
            (
                (
                    f'<a data-ssa-dashboard-id="{_h(order_id)}" '
                    f'href="/sales-credit/{_h(order_id)}">{_h(order_id)}</a>'
                ),
                _state_badge(item["workflow_state"]),
                _h(_display(item["attribution"])),
                _h(_display(item["order_value_status"])),
                _h(
                    "Required"
                    if _boolean(
                        item["human_review_required"],
                        "DASHBOARD_SC_REVIEW_INVALID",
                    )
                    else "Not required"
                ),
                _h(_integer(item["interaction_count"], "DASHBOARD_SC_INTERACTIONS_INVALID")),
                _h(_display(item["manager_outcome"])),
                _h(_display(item["updated_at"])),
            )
        )
    table = _table(
        caption="Current nonclosed Sales Credit projections",
        headers=(
            "Synthetic order",
            "Workflow",
            "System classification",
            "Placed-value status",
            "Human review",
            "Interactions",
            "Manager outcome",
            "Updated",
        ),
        rows=rows,
        selector="sales-credit-current-projections",
    )
    body = (
        _filter_form(
            "/sales-credit",
            (
                ("updated_at", "Most recent update"),
                ("order_id", "Order ID"),
                ("workflow_state", "Workflow state"),
            ),
            _SALES_CREDIT_QUEUE_STATES,
            query,
            int(root["limit"]),
            presentation=presentation,
        )
        + '<section class="dashboard-panel" '
        + f'data-ssa-dashboard-current-projection="sales-credit">{table}'
        + _pagination(
            "/sales-credit",
            int(root["offset"]),
            int(root["limit"]),
            int(root["total_count"]),
            query,
            presentation=presentation,
        )
        + "</section>"
    )
    return _page(
        route_name="sales_credit_queue",
        heading="Current Sales Credit queue",
        lede=(
            "Current nonclosed case projections only. Closed cases and prior evaluations "
            "remain in immutable history."
        ),
        body=body,
        csrf_token=csrf_token,
        presentation=presentation,
    )


def render_doi_queue(data: object, csrf_token: str, *, presentation: bool = False) -> bytes:
    root = _queue_root(
        data,
        "DASHBOARD_DOI_QUEUE_INVALID",
        sort_fields=frozenset({"case_id", "doi_state", "order_id", "updated_at"}),
        state_values=frozenset(_DOI_QUEUE_STATES),
    )
    query = _closed_mapping(
        root["query"],
        _QUEUE_QUERY_MEMBERS,
        "DASHBOARD_DOI_QUEUE_QUERY_INVALID",
    )
    rows: list[tuple[str, ...]] = []
    for raw in _list(root["items"], "DASHBOARD_DOI_QUEUE_ITEMS_INVALID"):
        item = _closed_mapping(raw, _DOI_SUMMARY_MEMBERS, "DASHBOARD_DOI_SUMMARY_INVALID")
        case_id = _synthetic_id(item["case_id"], "DASHBOARD_DOI_CASE_ID_INVALID")
        order_id = _synthetic_id(item["order_id"], "DASHBOARD_DOI_ORDER_ID_INVALID")
        attention_causes = [
            _governed_enum(
                value,
                "DASHBOARD_DOI_QUEUE_ATTENTION_CAUSE_INVALID",
            )
            for value in _list(
                item["attention_causes"],
                "DASHBOARD_DOI_QUEUE_ATTENTION_INVALID",
            )
        ]
        rows.append(
            (
                (
                    f'<a data-ssa-dashboard-id="{_h(case_id)}" '
                    f'href="/doi/{_h(case_id)}">{_h(order_id)}</a>'
                ),
                _state_badge(item["doi_state"]),
                _h(_display(item["opportunity_types"])),
                _h(_display(item["reason_codes"])),
                _h(_display(item["aggregate_potential_state"])),
                _h(_display(attention_causes)),
                _h(_display(item["scenario_selection_state"])),
                _h(_display(item["lifecycle_state"])),
                _h(_display(item["updated_at"])),
            )
        )
    table = _table(
        caption="Current DOI case projections; opportunity count may exceed case count",
        headers=(
            "Synthetic order",
            "DOI state",
            "Opportunity types",
            "Reasons",
            "Potential-value state",
            "Current attention causes",
            "Scenario selection",
            "Lifecycle",
            "Updated",
        ),
        rows=rows,
        selector="doi-current-projections",
    )
    body = (
        _filter_form(
            "/doi",
            (
                ("updated_at", "Most recent update"),
                ("case_id", "Case ID"),
                ("order_id", "Order ID"),
                ("doi_state", "DOI state"),
            ),
            _DOI_QUEUE_STATES,
            query,
            int(root["limit"]),
            presentation=presentation,
        )
        + f'<section class="dashboard-panel" data-ssa-dashboard-current-projection="doi">{table}'
        + _pagination(
            "/doi",
            int(root["offset"]),
            int(root["limit"]),
            int(root["total_count"]),
            query,
            presentation=presentation,
        )
        + "</section>"
    )
    return _page(
        route_name="doi_queue",
        heading="Current DOI queue",
        lede=(
            "Current active cases and their current opportunities. Unknown and unresolved "
            "values remain visibly unavailable."
        ),
        body=body,
        csrf_token=csrf_token,
        presentation=presentation,
    )


def _timeline(value: object, *, subject_kind: str, subject_id: str) -> str:
    rows: list[tuple[str, ...]] = []
    event_facts: list[tuple[int, str, str]] = []
    event_ids: set[str] = set()
    last_sequence = -1
    for raw in _list(value, "DASHBOARD_TIMELINE_INVALID"):
        event = _closed_mapping(raw, _TIMELINE_MEMBERS, "DASHBOARD_TIMELINE_EVENT_INVALID")
        sequence = _integer(event["sequence"], "DASHBOARD_TIMELINE_SEQUENCE_INVALID")
        if sequence <= last_sequence:
            _fail("DASHBOARD_TIMELINE_ORDER_INVALID")
        last_sequence = sequence
        event_id = _text(event["event_id"], "DASHBOARD_EVENT_ID_INVALID")
        assert event_id is not None
        event_kind = _governed_enum(
            event["event_kind"],
            "DASHBOARD_TIMELINE_EVENT_KIND_INVALID",
        )
        if event_id in event_ids:
            _fail("DASHBOARD_TIMELINE_EVENT_ID_DUPLICATE")
        event_ids.add(event_id)
        if subject_kind == "SALES_CREDIT_CASE":
            _namespace_id(event_id, "EVIDENCE", "DASHBOARD_EVENT_ID_INVALID")
        elif subject_kind == "EVALUATION":
            _namespace_id(event_id, "EVALUATION", "DASHBOARD_EVENT_ID_INVALID")
        elif subject_kind == "DOI_RUN":
            if _LOWER_SHA256.fullmatch(event_id) is None:
                _fail("DASHBOARD_EVENT_ID_INVALID")
        elif _SYNTHETIC_ID.fullmatch(event_id) is None and not (
            _LOWER_SHA256.fullmatch(event_id) is not None
            and event_kind in {"COMPLETENESS_PROOF", "LINE_CONTINUITY_PROOF"}
        ):
            _fail("DASHBOARD_EVENT_ID_INVALID")
        state = _governed_enum(
            event["state"],
            "DASHBOARD_TIMELINE_STATE_INVALID",
        )
        transition = _text(
            event["transition_id"],
            "DASHBOARD_TIMELINE_TRANSITION_INVALID",
            optional=True,
        )
        if transition is not None and _TRANSITION_ID.fullmatch(transition) is None:
            _fail("DASHBOARD_TIMELINE_TRANSITION_INVALID")
        _validate_timeline_semantics(
            subject_kind=subject_kind,
            event_kind=event_kind,
            state=state,
            transition_id=transition,
        )
        occurred_at = _timestamp(
            event["occurred_at"],
            "DASHBOARD_TIMELINE_TIMESTAMP_INVALID",
        )
        event_facts.append((sequence, event_id, event_kind))
        rows.append(
            (
                _h(sequence),
                _h(event_id),
                _h(event_kind),
                _h(state),
                _h(_display(transition)),
                _h(occurred_at),
            )
        )
    if subject_kind == "EVALUATION" and event_facts != [
        (1, subject_id, "EVALUATION_RECORDED")
    ]:
        _fail("DASHBOARD_TIMELINE_EVALUATION_COHERENCE_INVALID")
    if subject_kind == "DOI_RUN" and (
        not event_facts
        or event_facts[0][0] != 1
        or event_facts[0][2] != "RUN_STARTED"
    ):
        _fail("DASHBOARD_TIMELINE_RUN_COHERENCE_INVALID")
    return f"""<section class="dashboard-panel" id="immutable-timeline"
 data-ssa-dashboard-timeline="{_h(subject_kind)}" data-ssa-dashboard-id="{_h(subject_id)}">
<h2>Immutable timeline</h2>
<p>Events and receipts are history. Replays do not create new evaluations or current cases.</p>
{_table(
    caption="Immutable events in durable sequence",
    headers=("Sequence", "Event ID", "Event kind", "State", "Transition", "Occurred"),
    rows=rows,
    selector="immutable-timeline",
)}
</section>"""


def _validate_timeline_semantics(
    *,
    subject_kind: str,
    event_kind: str,
    state: str,
    transition_id: str | None,
) -> None:
    if subject_kind == "SALES_CREDIT_CASE":
        if (
            event_kind not in _SC_AUDIT_EVENT_KINDS
            or state not in _SC_WORKFLOW_STATES
            or transition_id is not None
        ):
            _fail("DASHBOARD_TIMELINE_COHERENCE_INVALID")
        return
    if subject_kind == "DOI_RUN":
        if (
            event_kind not in {"RUN_STARTED", "RUN_TERMINAL"}
            or state != event_kind
            or transition_id is not None
        ):
            _fail("DASHBOARD_TIMELINE_COHERENCE_INVALID")
        return
    if subject_kind == "EVALUATION":
        if (
            event_kind != "EVALUATION_RECORDED"
            or state not in _SC_WORKFLOW_STATES | _DOI_STATES
            or transition_id is not None
        ):
            _fail("DASHBOARD_TIMELINE_COHERENCE_INVALID")
        return
    if subject_kind != "DOI_CASE":
        _fail("DASHBOARD_TIMELINE_COHERENCE_INVALID")
    if event_kind in _DOI_ARTIFACT_KINDS:
        if state != event_kind or transition_id is not None:
            _fail("DASHBOARD_TIMELINE_COHERENCE_INVALID")
        return
    states = _DOI_STREAM_STATES.get(event_kind)
    if states is None:
        _fail("DASHBOARD_TIMELINE_EVENT_KIND_INVALID")
    if transition_id is None:
        if state not in states:
            _fail("DASHBOARD_TIMELINE_STATE_INVALID")
        return
    try:
        transition = load_doi_registries().transition_record(transition_id)
    except RegistryLookupError:
        _fail("DASHBOARD_TIMELINE_TRANSITION_INVALID")
    expected_state = transition.get("To", transition.get("To/action"))
    if type(expected_state) is not str or state not in re.findall(
        r"[A-Z][A-Z0-9_]*",
        expected_state,
        re.ASCII,
    ):
        _fail("DASHBOARD_TIMELINE_COHERENCE_INVALID")


def _hidden(name: str, value: str) -> str:
    return f'<input type="hidden" name="{_h(name)}" value="{_h(value)}">'


def _hidden_array_member(name: str, value: str) -> str:
    return (
        f'<input type="hidden" name="{_h(name)}" value="{_h(value)}" '
        'data-ssa-value-type="array">'
    )


def _manager_outcome_form(order_id: str) -> str:
    endpoint = f"/api/v1/dashboard/sales-credit/{order_id}/manager-outcome"
    return f"""<section class="dashboard-panel dashboard-warning"
 data-ssa-dashboard-action-region="manager-outcome">
<h2>Record a separate manager outcome</h2>
<p>This human decision is stored separately. It does not alter the current system classification
or any source-order fact.</p>
<form class="dashboard-form" data-ssa-dashboard-action="manager-outcome"
 data-ssa-dashboard-endpoint="{_h(endpoint)}">
{_hidden("schema_version", MANAGER_OUTCOME_REQUEST_VERSION)}
{_hidden("request_schema_version", API_REQUEST_SCHEMA_VERSION)}
<label class="dashboard-field"><span>Synthetic manager actor</span>
 <input name="actor_id" value="SYN-REP-M2-MANAGER-0001" readonly required></label>
<label class="dashboard-field"><span>Request key</span>
 <input name="request_key" maxlength="96" autocomplete="off" required>
 <span class="dashboard-field-hint">Reuse the same key and identical fields for an exact
 replay.</span></label>
<label class="dashboard-field"><span>Decision time (canonical UTC)</span>
 <input name="decided_at" maxlength="30" placeholder="2026-09-01T12:00:00Z"
 autocomplete="off" required></label>
<label class="dashboard-field"><span>Manager outcome</span><select name="outcome" required>
 <option value="">Choose an outcome</option><option value="APPROVED">Approved</option>
 <option value="DENIED">Denied</option><option value="PARTIAL">Partial</option>
 <option value="OTHER_REP">Other rep</option><option value="NOT_PURSUED">Not pursued</option>
</select></label>
<label class="dashboard-field"><span>Partial amount in minor units</span>
 <input name="amount_minor_units" data-ssa-value-type="integer" data-ssa-optional="true"
 inputmode="numeric" pattern="[0-9]+" autocomplete="off">
 <span class="dashboard-field-hint">Required only for PARTIAL; for example 1250 means
 12.50 USD.</span></label>
<label class="dashboard-field"><span>Partial currency</span>
 <select name="currency_code" data-ssa-optional="true">
 <option value="">Not applicable</option><option value="EUR">EUR</option>
 <option value="JPY">JPY</option>
 <option value="KWD">KWD</option><option value="USD">USD</option>
</select></label>
<label class="dashboard-confirmation">
 <input type="checkbox" name="confirmed" data-ssa-value-type="boolean" required>
 <span>I confirm this exact fictional manager outcome for {_h(order_id)}. The system
 classification remains unchanged. <strong data-ssa-manager-confirmation></strong></span>
</label>
<button type="submit">Record synthetic manager outcome</button>
<p class="dashboard-live-region" role="status" tabindex="-1"
 data-ssa-dashboard-live-region="manager-outcome" data-ssa-dashboard-action-status></p>
<a href="/sales-credit/{_h(order_id)}">Refresh current projection</a>
</form></section>"""


def _sc_current_evaluation(
    value: object,
    expected_evaluation_id: str | None,
    expected_review: bool,
) -> dict[str, object] | None:
    if expected_evaluation_id is None:
        if value is not None:
            _fail("DASHBOARD_SC_EVALUATION_UNEXPECTED")
        return None
    item = _closed_mapping(
        value,
        _SC_CURRENT_EVALUATION_MEMBERS,
        "DASHBOARD_SC_EVALUATION_INVALID",
    )
    evaluation_id = _namespace_id(
        item["evaluation_id"],
        "EVALUATION",
        "DASHBOARD_SC_EVALUATION_ID_INVALID",
    )
    if evaluation_id != expected_evaluation_id:
        _fail("DASHBOARD_SC_EVALUATION_ID_MISMATCH")
    _namespace_id(
        item["snapshot_id"],
        "SNAPSHOT",
        "DASHBOARD_SC_EVALUATION_SNAPSHOT_INVALID",
    )
    _version_identifier(
        item["rule_pack_version"],
        "DASHBOARD_SC_RULE_PACK_VERSION_INVALID",
    )
    _lower_sha256(
        item["material_sha256"],
        "DASHBOARD_SC_EVALUATION_HASH_INVALID",
    )
    if (
        _boolean(
            item["human_review_required"],
            "DASHBOARD_SC_EVALUATION_REVIEW_INVALID",
        )
        != expected_review
    ):
        _fail("DASHBOARD_SC_EVALUATION_REVIEW_MISMATCH")
    return item


def _sc_source_search_section(
    snapshots_value: object,
    search_runs_value: object,
    current_evaluation: Mapping[str, object] | None,
) -> str:
    snapshot_rows: list[tuple[str, ...]] = []
    snapshot_ids: set[str] = set()
    current_snapshot_ids: list[str] = []
    for raw in _list(snapshots_value, "DASHBOARD_SC_SNAPSHOTS_INVALID"):
        item = _closed_mapping(
            raw,
            _SC_SNAPSHOT_MEMBERS,
            "DASHBOARD_SC_SNAPSHOT_INVALID",
        )
        snapshot_id = _namespace_id(
            item["snapshot_id"],
            "SNAPSHOT",
            "DASHBOARD_SC_SNAPSHOT_ID_INVALID",
        )
        if snapshot_id in snapshot_ids:
            _fail("DASHBOARD_SC_SNAPSHOT_DUPLICATE")
        snapshot_ids.add(snapshot_id)
        captured_at = _timestamp(
            item["captured_at"],
            "DASHBOARD_SC_SNAPSHOT_TIMESTAMP_INVALID",
        )
        extraction = _governed_enum(
            item["extraction_status"],
            "DASHBOARD_SC_EXTRACTION_STATUS_INVALID",
        )
        lifecycle = _governed_enum(
            item["lifecycle_status"],
            "DASHBOARD_SC_SNAPSHOT_LIFECYCLE_INVALID",
        )
        parser_version = _version_identifier(
            item["parser_version"],
            "DASHBOARD_SC_PARSER_VERSION_INVALID",
        )
        line_count = _integer(
            item["line_count"],
            "DASHBOARD_SC_SNAPSHOT_LINE_COUNT_INVALID",
        )
        is_current = _boolean(
            item["is_current"],
            "DASHBOARD_SC_SNAPSHOT_CURRENT_INVALID",
        )
        if is_current:
            current_snapshot_ids.append(snapshot_id)
        snapshot_rows.append(
            tuple(
                _h(value)
                for value in (
                    is_current,
                    snapshot_id,
                    captured_at,
                    extraction,
                    lifecycle,
                    line_count,
                    parser_version,
                )
            )
        )
    expected_snapshot_id = (
        None
        if current_evaluation is None
        else str(current_evaluation["snapshot_id"])
    )
    if (
        (expected_snapshot_id is None and current_snapshot_ids)
        or (
            expected_snapshot_id is not None
            and current_snapshot_ids != [expected_snapshot_id]
        )
    ):
        _fail("DASHBOARD_SC_CURRENT_SNAPSHOT_BINDING_INVALID")

    run_rows: list[tuple[str, ...]] = []
    run_ids: set[str] = set()
    for raw in _list(search_runs_value, "DASHBOARD_SC_SEARCH_RUNS_INVALID"):
        item = _closed_mapping(
            raw,
            _SC_SEARCH_RUN_MEMBERS,
            "DASHBOARD_SC_SEARCH_RUN_INVALID",
        )
        run_id = _namespace_id(
            item["run_id"],
            "RUN",
            "DASHBOARD_SC_SEARCH_RUN_ID_INVALID",
        )
        if run_id in run_ids:
            _fail("DASHBOARD_SC_SEARCH_RUN_DUPLICATE")
        run_ids.add(run_id)
        started_at = _timestamp(
            item["started_at"],
            "DASHBOARD_SC_SEARCH_STARTED_AT_INVALID",
        )
        completed_at = _timestamp(
            item["completed_at"],
            "DASHBOARD_SC_SEARCH_COMPLETED_AT_INVALID",
        )
        adapter_version = _version_identifier(
            item["adapter_version"],
            "DASHBOARD_SC_SEARCH_ADAPTER_INVALID",
        )
        complete = _boolean(
            item["enumeration_complete"],
            "DASHBOARD_SC_SEARCH_COMPLETENESS_INVALID",
        )
        identifier_count = _integer(
            item["identifier_count"],
            "DASHBOARD_SC_SEARCH_IDENTIFIER_COUNT_INVALID",
        )
        terminal = _governed_enum(
            item["terminal_outcome"],
            "DASHBOARD_SC_SEARCH_OUTCOME_INVALID",
        )
        trigger = _governed_enum(
            item["trigger_type"],
            "DASHBOARD_SC_SEARCH_TRIGGER_INVALID",
        )
        run_rows.append(
            tuple(
                _h(value)
                for value in (
                    run_id,
                    trigger,
                    started_at,
                    completed_at,
                    complete,
                    terminal,
                    identifier_count,
                    adapter_version,
                )
            )
        )

    evaluation_items: tuple[tuple[str, object], ...]
    if current_evaluation is None:
        evaluation_items = (("Current evaluation binding", "Unavailable"),)
    else:
        evaluation_items = (
            ("Evaluation ID", current_evaluation["evaluation_id"]),
            ("Snapshot ID", current_evaluation["snapshot_id"]),
            ("Rule pack", current_evaluation["rule_pack_version"]),
            ("Material SHA-256", current_evaluation["material_sha256"]),
            ("Human review", current_evaluation["human_review_required"]),
        )
    return f"""<section class="dashboard-panel"
 data-ssa-dashboard-evidence="sales-credit-source-search">
<h2>Source and search completeness</h2>
<p>Only normalized, owned metadata is shown. Source text and unrestricted values are omitted.</p>
{_definition_list(evaluation_items)}
{_table(
    caption="Governed Sales Credit snapshots",
    headers=(
        "Current",
        "Snapshot ID",
        "Captured",
        "Extraction",
        "Lifecycle",
        "Line count",
        "Parser version",
    ),
    rows=snapshot_rows,
    selector="sales-credit-snapshots",
    empty_message="No governed source snapshot is retained for this case.",
)}
{_table(
    caption="Governed search-run completeness",
    headers=(
        "Run ID",
        "Trigger",
        "Started",
        "Completed",
        "Enumeration complete",
        "Terminal outcome",
        "Identifier count",
        "Adapter version",
    ),
    rows=run_rows,
    selector="sales-credit-search-runs",
    empty_message="No governed search run is retained for this case.",
)}</section>"""


def _sc_interactions_evidence_section(
    interactions_value: object,
    evidence_value: object,
    expected_interaction_count: int,
) -> str:
    interaction_rows: list[tuple[str, ...]] = []
    interaction_ids: set[str] = set()
    for raw in _list(interactions_value, "DASHBOARD_SC_INTERACTIONS_INVALID"):
        item = _closed_mapping(
            raw,
            _SC_INTERACTION_MEMBERS,
            "DASHBOARD_SC_INTERACTION_INVALID",
        )
        interaction_id = _namespace_id(
            item["interaction_id"],
            "INTERACTION",
            "DASHBOARD_SC_INTERACTION_ID_INVALID",
        )
        if interaction_id in interaction_ids:
            _fail("DASHBOARD_SC_INTERACTION_DUPLICATE")
        interaction_ids.add(interaction_id)
        source_ref_id = _namespace_id(
            item["source_ref_id"],
            "EVIDENCE",
            "DASHBOARD_SC_INTERACTION_SOURCE_REF_INVALID",
        )
        recorded_at = _timestamp(
            item["recorded_at"],
            "DASHBOARD_SC_INTERACTION_TIMESTAMP_INVALID",
        )
        precision = _governed_enum(
            item["timestamp_precision"],
            "DASHBOARD_SC_INTERACTION_PRECISION_INVALID",
        )
        workflow = _governed_enum(
            item["workflow_state"],
            "DASHBOARD_SC_INTERACTION_WORKFLOW_INVALID",
        )
        interaction_rows.append(
            tuple(
                _h(value)
                for value in (
                    interaction_id,
                    source_ref_id,
                    recorded_at,
                    precision,
                    workflow,
                )
            )
        )
    if len(interaction_rows) != expected_interaction_count:
        _fail("DASHBOARD_SC_INTERACTION_COUNT_MISMATCH")

    evidence_rows: list[tuple[str, ...]] = []
    evidence_ids: set[str] = set()
    for raw in _list(evidence_value, "DASHBOARD_SC_EVIDENCE_INVALID"):
        item = _closed_mapping(
            raw,
            _SC_EVIDENCE_MEMBERS,
            "DASHBOARD_SC_EVIDENCE_ITEM_INVALID",
        )
        evidence_id = _namespace_id(
            item["evidence_id"],
            "EVIDENCE",
            "DASHBOARD_SC_EVIDENCE_ID_INVALID",
        )
        if evidence_id in evidence_ids:
            _fail("DASHBOARD_SC_EVIDENCE_DUPLICATE")
        evidence_ids.add(evidence_id)
        interaction_id = _namespace_id(
            item["interaction_id"],
            "INTERACTION",
            "DASHBOARD_SC_EVIDENCE_INTERACTION_INVALID",
        )
        if interaction_id not in interaction_ids:
            _fail("DASHBOARD_SC_EVIDENCE_INTERACTION_MISMATCH")
        source_type = _governed_enum(
            item["source_type"],
            "DASHBOARD_SC_EVIDENCE_SOURCE_TYPE_INVALID",
        )
        classification = _governed_enum(
            item["classification"],
            "DASHBOARD_SC_EVIDENCE_CLASSIFICATION_INVALID",
        )
        occurred_at = _timestamp(
            item["occurred_at"],
            "DASHBOARD_SC_EVIDENCE_TIMESTAMP_INVALID",
        )
        evidence_rows.append(
            tuple(
                _h(value)
                for value in (
                    evidence_id,
                    interaction_id,
                    source_type,
                    classification,
                    occurred_at,
                )
            )
        )
    return f"""<section class="dashboard-panel"
 data-ssa-dashboard-evidence="sales-credit-interactions">
<h2>Interactions and evidence</h2>
<p>Only governed fictional identifiers, classifications, and timestamps are displayed.</p>
{_table(
    caption="Current case interactions",
    headers=("Interaction ID", "Source reference", "Recorded", "Precision", "Workflow"),
    rows=interaction_rows,
    selector="sales-credit-interactions",
    empty_message="No governed fictional interaction is attached to this case.",
)}
{_table(
    caption="Current case evidence",
    headers=("Evidence ID", "Interaction ID", "Source type", "Classification", "Occurred"),
    rows=evidence_rows,
    selector="sales-credit-evidence",
    empty_message="No governed fictional evidence event is attached to this case.",
)}</section>"""


def render_sales_credit_detail(
    data: object,
    csrf_token: str,
    *,
    presentation: bool = False,
) -> bytes:
    root = _closed_mapping(
        data,
        _SC_DETAIL_MEMBERS,
        "DASHBOARD_SC_DETAIL_INVALID",
    )
    if root["schema_version"] != CONTROL_CENTER_SCHEMA_VERSION:
        _fail("DASHBOARD_SC_DETAIL_VERSION_INVALID")
    summary = _closed_mapping(root["summary"], _SC_SUMMARY_MEMBERS, "DASHBOARD_SC_SUMMARY_INVALID")
    order_id = _namespace_id(
        summary["order_id"],
        "ORDER",
        "DASHBOARD_SC_ORDER_ID_INVALID",
    )
    classification = _governed_enum(
        summary["attribution"],
        "DASHBOARD_SC_ATTRIBUTION_INVALID",
    )
    classification_label = _humanize_token(
        classification,
        "DASHBOARD_SC_ATTRIBUTION_INVALID",
    )
    workflow_state = _governed_enum(
        summary["workflow_state"],
        "DASHBOARD_SC_WORKFLOW_INVALID",
    )
    workflow_label = _humanize_token(workflow_state, "DASHBOARD_SC_WORKFLOW_INVALID")
    value_state = _governed_enum(
        summary["order_value_status"],
        "DASHBOARD_SC_VALUE_STATUS_INVALID",
    )
    updated_at = _timestamp(
        summary["updated_at"],
        "DASHBOARD_SC_UPDATED_AT_INVALID",
    )
    human_review_required = _boolean(
        summary["human_review_required"],
        "DASHBOARD_SC_HUMAN_REVIEW_INVALID",
    )
    unresolved_review = _boolean(
        summary["unresolved_human_review"],
        "DASHBOARD_SC_REVIEW_INVALID",
    )
    if unresolved_review and not human_review_required:
        _fail("DASHBOARD_SC_REVIEW_INCOHERENT")
    interaction_count = _integer(
        summary["interaction_count"],
        "DASHBOARD_SC_INTERACTION_COUNT_INVALID",
    )
    current_evaluation_id = summary["current_evaluation_id"]
    if current_evaluation_id is not None:
        current_evaluation_id = _namespace_id(
            current_evaluation_id,
            "EVALUATION",
            "DASHBOARD_SC_CURRENT_EVALUATION_ID_INVALID",
        )
    current_evaluation = _sc_current_evaluation(
        root["current_evaluation"],
        current_evaluation_id,
        human_review_required,
    )
    reasons = _list(root["reason_codes"], "DASHBOARD_SC_REASONS_INVALID")
    reason_text = (
        ", ".join(
            _h(_reason_code(item, "DASHBOARD_SC_REASON_INVALID"))
            for item in reasons
        )
        or "None"
    )
    source_search = _sc_source_search_section(
        root["snapshots"],
        root["search_runs"],
        current_evaluation,
    )
    interactions_evidence = _sc_interactions_evidence_section(
        root["interactions"],
        root["evidence"],
        interaction_count,
    )
    outcomes: list[tuple[str, ...]] = []
    outcome_values: list[str] = []
    for raw in _list(root["manager_outcomes"], "DASHBOARD_SC_OUTCOMES_INVALID"):
        outcome = _closed_mapping(
            raw,
            frozenset(
                {
                    "actor_id",
                    "amount_minor_units",
                    "currency_code",
                    "currency_registry_version",
                    "currency_scale",
                    "decided_at",
                    "occurrence_id",
                    "outcome",
                }
            ),
            "DASHBOARD_SC_OUTCOME_INVALID",
        )
        actor_id = _namespace_id(
            outcome["actor_id"],
            "REP",
            "DASHBOARD_SC_OUTCOME_ACTOR_INVALID",
        )
        occurrence_id = _namespace_id(
            outcome["occurrence_id"],
            "EVIDENCE",
            "DASHBOARD_SC_OUTCOME_OCCURRENCE_INVALID",
        )
        decided_at = _timestamp(
            outcome["decided_at"],
            "DASHBOARD_SC_OUTCOME_TIMESTAMP_INVALID",
        )
        outcome_value = _governed_enum(
            outcome["outcome"],
            "DASHBOARD_SC_OUTCOME_VALUE_INVALID",
        )
        if outcome_value not in {
            "APPROVED",
            "DENIED",
            "NOT_PURSUED",
            "OTHER_REP",
            "PARTIAL",
        }:
            _fail("DASHBOARD_SC_OUTCOME_VALUE_INVALID")
        amount = _optional_money_text(
            outcome,
            "DASHBOARD_SC_OUTCOME_MONEY_INVALID",
        )
        if (outcome_value == "PARTIAL") == (amount == "Unavailable"):
            _fail("DASHBOARD_SC_OUTCOME_MONEY_INVALID")
        outcome_values.append(outcome_value)
        outcomes.append(
            tuple(_h(value) for value in (outcome_value, actor_id, decided_at, occurrence_id))
            + (_h(amount),)
        )
    manager_outcome = summary["manager_outcome"]
    if manager_outcome is not None:
        manager_outcome = _governed_enum(
            manager_outcome,
            "DASHBOARD_SC_MANAGER_OUTCOME_INVALID",
        )
    if (outcome_values[-1] if outcome_values else None) != manager_outcome:
        _fail("DASHBOARD_SC_MANAGER_OUTCOME_MISMATCH")
    _sc_privacy_check(root)
    action = (
        _manager_outcome_form(order_id)
        if unresolved_review
        else """<section class="dashboard-panel"><h2>Required human action</h2>
<p>No unresolved manager decision is currently required. Prior outcomes remain in
history.</p></section>"""
    )
    body = f"""<nav class="dashboard-nav" aria-label="Case links">
<a href="/orders/{_h(order_id)}">Synthetic order</a>
<a href="/audit/SALES_CREDIT_CASE/{_h(order_id)}">Audit-only view</a></nav>
<section class="dashboard-split">
 <article class="dashboard-panel dashboard-callout" data-ssa-dashboard-card="system-classification">
  <h2>Current system classification</h2>{_state_badge(classification)}
  {_definition_list(
      (
          ("Workflow state", workflow_state),
          ("Current evaluation", current_evaluation_id),
          ("Last update", updated_at),
      )
 )}</article>
 <article class="dashboard-panel" data-ssa-dashboard-card="plain-english-why">
  <h2>Why the system stopped here</h2>
  <p>The system classified this case as <strong>{_h(classification_label)}</strong>
  (exact code <code>{_h(classification)}</code>) and placed it in
  <strong>{_h(workflow_label)}</strong> (exact code <code>{_h(workflow_state)}</code>).
  The immutable evaluation retained these exact reason codes:
  <strong>{reason_text}</strong>.</p></article>
</section>
{action}
{source_search}
<section class="dashboard-panel"><h2>Current placed-value state</h2>
{_state_badge(value_state)}</section>
{interactions_evidence}
<section class="dashboard-panel" data-ssa-dashboard-card="manager-outcome">
 <h2>Manager outcome — separate human authority</h2>
 {_state_badge(summary["manager_outcome"])}
 {_table(
     caption="Immutable manager outcomes",
     headers=(
         "Outcome",
         "Synthetic actor",
         "Decision time",
         "Occurrence",
         "Exact approved amount / currency",
     ),
     rows=outcomes,
     selector="sales-credit-manager-outcomes",
 )}
</section>
{_timeline(root["timeline"], subject_kind="SALES_CREDIT_CASE", subject_id=order_id)}
<section class="dashboard-panel"><h2>Developer contract identity</h2>
{_definition_list(
    (
        ("Control Center", CONTROL_CENTER_SCHEMA_VERSION),
        ("Dashboard DOM", DASHBOARD_DOM_VERSION),
        ("Portal DOM", DOM_SCHEMA_VERSION),
    )
)}</section>"""
    return _page(
        route_name="sales_credit_detail",
        heading=f"Sales Credit case {order_id}",
        lede=(
            "System classification and human manager authority are deliberately separate "
            "objects and history events."
        ),
        body=body,
        csrf_token=csrf_token,
        presentation=presentation,
    )


def _doi_selection_form(
    case_id: str,
    evaluation_id: str,
    opportunities: Sequence[Mapping[str, object]],
) -> str:
    controls = "".join(
        f"""<label class="dashboard-confirmation">
<input type="radio" name="selected_opportunity_id" value="{_h(item['opportunity_id'])}" required>
<span>{_h(item['opportunity_type'])} · {_h(item['opportunity_id'])}</span></label>
{_hidden_array_member("option_opportunity_ids", str(item["opportunity_id"]))}"""
        for item in sorted(
            opportunities,
            key=lambda opportunity: str(opportunity["opportunity_id"]),
        )
    )
    endpoint = f"/api/v1/dashboard/doi/{case_id}/scenario-selection"
    return f"""<section class="dashboard-panel dashboard-warning"
 data-ssa-dashboard-action-region="doi-scenario-selection">
<h2>Required human action: select one exact overlap scenario</h2>
<p>The opportunities remain separate. This confirmed human fact selects one current scenario and
asks the existing evaluator to recompute aggregate availability; it creates no intervention,
resulting-order link, or realized value.</p>
<form class="dashboard-form" data-ssa-dashboard-action="doi-scenario-selection"
 data-ssa-dashboard-endpoint="{_h(endpoint)}">
{_hidden("schema_version", DOI_SCENARIO_SELECTION_REQUEST_VERSION)}
{_hidden("request_schema_version", API_REQUEST_SCHEMA_VERSION)}
{_hidden("evaluation_id", evaluation_id)}
<label class="dashboard-field"><span>Synthetic human actor</span>
 <input name="actor_id" value="SYN-REP-DOI-AUTHORIZED-0001" readonly required></label>
<label class="dashboard-field"><span>Request key</span>
 <input name="request_key" maxlength="96" autocomplete="off" required>
 <span class="dashboard-field-hint">Reuse the same key and identical selection for an
 exact replay.</span></label>
<label class="dashboard-field"><span>Observation time (canonical UTC)</span>
 <input name="occurred_at" maxlength="30" placeholder="2026-09-01T12:00:00Z"
 autocomplete="off" required></label>
<fieldset><legend>Exact current opportunity selected</legend>{controls}</fieldset>
<label class="dashboard-confirmation">
 <input type="checkbox" name="confirmed" data-ssa-value-type="boolean" required>
 <span>I confirm this exact fictional scenario selection for {_h(case_id)}. Unrelated
 attention causes remain unchanged.</span>
</label>
<button type="submit">Record synthetic scenario selection</button>
<p class="dashboard-live-region" role="status" tabindex="-1"
 data-ssa-dashboard-live-region="doi-scenario-selection" data-ssa-dashboard-action-status></p>
<a href="/doi/{_h(case_id)}">Refresh current projection</a>
</form></section>"""


def _doi_source_section(
    value: object,
    order_id: str,
    *,
    expected_snapshot_id: str | None,
    expected_run_id: str | None,
) -> str:
    rows: list[tuple[str, ...]] = []
    seen_snapshots: set[str] = set()
    current_bindings: list[tuple[str, str]] = []
    for raw in _list(value, "DASHBOARD_DOI_SOURCE_INVALID"):
        item = _closed_mapping(raw, _DOI_SOURCE_MEMBERS, "DASHBOARD_DOI_SOURCE_ITEM_INVALID")
        snapshot_id = _namespace_id(
            item["snapshot_id"],
            "SNAPSHOT",
            "DASHBOARD_DOI_SOURCE_SNAPSHOT_INVALID",
        )
        if snapshot_id in seen_snapshots:
            _fail("DASHBOARD_DOI_SOURCE_SNAPSHOT_DUPLICATE")
        seen_snapshots.add(snapshot_id)
        source_order_id = _namespace_id(
            item["order_id"],
            "ORDER",
            "DASHBOARD_DOI_SOURCE_ORDER_INVALID",
        )
        if source_order_id != order_id:
            _fail("DASHBOARD_DOI_SOURCE_ORDER_MISMATCH")
        run_id = _namespace_id(
            item["run_id"],
            "RUN",
            "DASHBOARD_DOI_SOURCE_RUN_INVALID",
        )
        observed_at = _timestamp(
            item["source_observed_at"],
            "DASHBOARD_DOI_SOURCE_TIMESTAMP_INVALID",
        )
        completeness_sha = _lower_sha256(
            item["completeness_sha256"],
            "DASHBOARD_DOI_COMPLETENESS_HASH_INVALID",
        )
        record_sha = _lower_sha256(
            item["record_sha256"],
            "DASHBOARD_DOI_SOURCE_RECORD_HASH_INVALID",
        )
        record_domain = _record_domain(
            item["record_domain"],
            "DASHBOARD_DOI_SOURCE_RECORD_DOMAIN_INVALID",
        )
        line_count = _integer(item["line_count"], "DASHBOARD_DOI_LINE_COUNT_INVALID")
        relevant_count = _integer(
            item["relevant_line_count"],
            "DASHBOARD_DOI_RELEVANT_LINE_COUNT_INVALID",
        )
        if relevant_count > line_count:
            _fail("DASHBOARD_DOI_SOURCE_COUNTS_INCOHERENT")
        proof_present = _boolean(
            item["completeness_proof_present"],
            "DASHBOARD_DOI_COMPLETENESS_PROOF_INVALID",
        )
        is_current = _boolean(item["is_current"], "DASHBOARD_DOI_SOURCE_CURRENT_INVALID")
        if is_current:
            current_bindings.append((snapshot_id, run_id))
        rows.append(
            tuple(
                _h(_display(field))
                for field in (
                    is_current,
                    snapshot_id,
                    run_id,
                    observed_at,
                    line_count,
                    relevant_count,
                    proof_present,
                    completeness_sha,
                    record_domain,
                    record_sha,
                )
            )
        )
    if len(current_bindings) > 1:
        _fail("DASHBOARD_DOI_SOURCE_CURRENT_DUPLICATE")
    if expected_snapshot_id is not None:
        if current_bindings != [(expected_snapshot_id, expected_run_id)]:
            _fail("DASHBOARD_DOI_SOURCE_EVALUATION_BINDING_INVALID")
    return f"""<section class="dashboard-panel"
 data-ssa-dashboard-evidence="doi-source-completeness">
<h2>Source completeness</h2>
<p>Line counts and proof presence come from governed snapshots. Missing proof remains visible.</p>
{_table(
    caption="Governed source snapshots and completeness evidence",
    headers=(
        "Current",
        "Snapshot ID",
        "Run ID",
        "Observed UTC",
        "All lines",
        "Relevant lines",
        "Proof present",
        "Completeness SHA-256",
        "Record domain",
        "Record SHA-256",
    ),
    rows=rows,
    selector="doi-source-completeness",
    empty_message="No governed source-completeness snapshot is recorded for this case.",
)}</section>"""


def _doi_handling_attention_section(
    flags_value: object,
    attention_value: object,
    expected_conditions: Sequence[str],
) -> str:
    flag_rows: list[tuple[str, ...]] = []
    seen_flags: set[str] = set()
    for raw in _list(flags_value, "DASHBOARD_DOI_HANDLING_FLAGS_INVALID"):
        flag = _governed_enum(raw, "DASHBOARD_DOI_HANDLING_FLAG_INVALID")
        if flag in seen_flags:
            _fail("DASHBOARD_DOI_HANDLING_FLAG_DUPLICATE")
        seen_flags.add(flag)
        flag_rows.append((_h(flag),))

    attention_rows: list[tuple[str, ...]] = []
    seen_streams: set[str] = set()
    observed_conditions: list[str] = []
    for raw in _list(attention_value, "DASHBOARD_DOI_ATTENTION_INVALID"):
        item = _closed_mapping(
            raw,
            _DOI_ATTENTION_MEMBERS,
            "DASHBOARD_DOI_ATTENTION_ITEM_INVALID",
        )
        stream_id = _namespace_id(
            item["stream_id"],
            "EVIDENCE",
            "DASHBOARD_DOI_ATTENTION_STREAM_INVALID",
        )
        if stream_id in seen_streams:
            _fail("DASHBOARD_DOI_ATTENTION_STREAM_DUPLICATE")
        seen_streams.add(stream_id)
        cause_key = _namespace_id(
            item["cause_key"],
            "EVIDENCE",
            "DASHBOARD_DOI_ATTENTION_CAUSE_KEY_INVALID",
        )
        condition = _governed_enum(
            item["condition"],
            "DASHBOARD_DOI_ATTENTION_CONDITION_INVALID",
        )
        observed_conditions.append(condition)
        event_id = _namespace_id(
            item["current_event_id"],
            "EVIDENCE",
            "DASHBOARD_DOI_ATTENTION_EVENT_INVALID",
        )
        state = _governed_enum(
            item["projection_state"],
            "DASHBOARD_DOI_ATTENTION_STATE_INVALID",
        )
        if state != "SET":
            _fail("DASHBOARD_DOI_ATTENTION_STATE_INVALID")
        occurred_at = _timestamp(
            item["current_event_occurred_at"],
            "DASHBOARD_DOI_ATTENTION_TIMESTAMP_INVALID",
        )
        sequence = _integer(
            item["sequence"],
            "DASHBOARD_DOI_ATTENTION_SEQUENCE_INVALID",
            minimum=1,
        )
        head_sha = _lower_sha256(
            item["head_sha256"],
            "DASHBOARD_DOI_ATTENTION_HEAD_INVALID",
        )
        record_domain = _record_domain(
            item["record_domain"],
            "DASHBOARD_DOI_ATTENTION_DOMAIN_INVALID",
        )
        record_sha = _lower_sha256(
            item["record_sha256"],
            "DASHBOARD_DOI_ATTENTION_RECORD_HASH_INVALID",
        )
        attention_rows.append(
            tuple(
                _h(field)
                for field in (
                    condition,
                    cause_key,
                    stream_id,
                    state,
                    sequence,
                    event_id,
                    occurred_at,
                    head_sha,
                    record_domain,
                    record_sha,
                )
            )
        )
    if observed_conditions != list(expected_conditions):
        _fail("DASHBOARD_DOI_ATTENTION_SUMMARY_MISMATCH")
    return f"""<section class="dashboard-panel"
 data-ssa-dashboard-evidence="doi-handling-attention">
<h2>Handling flags and current attention</h2>
<p>Each current attention cause remains separate. Resolving one cause cannot clear another.</p>
{_table(
    caption="Current governed handling flags",
    headers=("Handling flag",),
    rows=flag_rows,
    selector="doi-handling-flags",
    empty_message="No current handling flag is recorded.",
)}
{_table(
    caption="Current unresolved attention causes only",
    headers=(
        "Condition",
        "Cause key",
        "Attention stream",
        "Current state",
        "Sequence",
        "Current event",
        "Occurred UTC",
        "Head SHA-256",
        "Record domain",
        "Record SHA-256",
    ),
    rows=attention_rows,
    selector="doi-current-attention-causes",
    empty_message="No current unresolved attention cause is recorded.",
)}</section>"""


def _doi_human_facts_section(value: object) -> str:
    rows: list[tuple[str, ...]] = []
    seen_events: set[str] = set()
    for raw in _list(value, "DASHBOARD_DOI_HUMAN_FACTS_INVALID"):
        item = _closed_mapping(
            raw,
            _DOI_HUMAN_FACT_MEMBERS,
            "DASHBOARD_DOI_HUMAN_FACT_INVALID",
        )
        event_id = _namespace_id(
            item["event_id"],
            "EVIDENCE",
            "DASHBOARD_DOI_HUMAN_EVENT_INVALID",
        )
        if event_id in seen_events:
            _fail("DASHBOARD_DOI_HUMAN_EVENT_DUPLICATE")
        seen_events.add(event_id)
        stream_id = _namespace_id(
            item["stream_id"],
            "EVIDENCE",
            "DASHBOARD_DOI_HUMAN_STREAM_INVALID",
        )
        occurred_at = _timestamp(
            item["occurred_at"],
            "DASHBOARD_DOI_HUMAN_TIMESTAMP_INVALID",
        )
        state = _governed_enum(
            item["projection_state"],
            "DASHBOARD_DOI_HUMAN_STATE_INVALID",
        )
        sequence = _integer(
            item["sequence"],
            "DASHBOARD_DOI_HUMAN_SEQUENCE_INVALID",
            minimum=1,
        )
        transition = _text(
            item["transition_id"],
            "DASHBOARD_DOI_HUMAN_TRANSITION_INVALID",
            optional=True,
        )
        if transition is not None and _TRANSITION_ID.fullmatch(transition) is None:
            _fail("DASHBOARD_DOI_HUMAN_TRANSITION_INVALID")
        record_domain = _record_domain(
            item["record_domain"],
            "DASHBOARD_DOI_HUMAN_DOMAIN_INVALID",
        )
        record_sha = _lower_sha256(
            item["record_sha256"],
            "DASHBOARD_DOI_HUMAN_RECORD_HASH_INVALID",
        )
        rows.append(
            tuple(
                _h(_display(field))
                for field in (
                    stream_id,
                    sequence,
                    state,
                    transition,
                    event_id,
                    occurred_at,
                    record_domain,
                    record_sha,
                )
            )
        )
    return f"""<section class="dashboard-panel" data-ssa-dashboard-evidence="doi-human-facts">
<h2>Human facts</h2>
<p>Recorded facts are human-owned evidence. They do not rewrite the system classification.</p>
{_table(
    caption="Immutable governed DOI human-fact events",
    headers=(
        "Fact stream",
        "Sequence",
        "Projection state",
        "Transition",
        "Event ID",
        "Occurred UTC",
        "Record domain",
        "Record SHA-256",
    ),
    rows=rows,
    selector="doi-human-fact-events",
    empty_message="No DOI human fact has been recorded for this case.",
)}</section>"""


def _doi_interventions_section(value: object) -> tuple[str, set[str]]:
    intervention_rows: list[tuple[str, ...]] = []
    verification_rows: list[tuple[str, ...]] = []
    intervention_ids: set[str] = set()
    verification_ids: set[str] = set()
    for raw in _list(value, "DASHBOARD_DOI_INTERVENTIONS_INVALID"):
        item = _closed_mapping(
            raw,
            _DOI_INTERVENTION_MEMBERS,
            "DASHBOARD_DOI_INTERVENTION_INVALID",
        )
        intervention_id = _namespace_id(
            item["intervention_id"],
            "EVIDENCE",
            "DASHBOARD_DOI_INTERVENTION_ID_INVALID",
        )
        if intervention_id in intervention_ids:
            _fail("DASHBOARD_DOI_INTERVENTION_DUPLICATE")
        intervention_ids.add(intervention_id)
        opportunity_id = _namespace_id(
            item["opportunity_id"],
            "EVIDENCE",
            "DASHBOARD_DOI_INTERVENTION_OPPORTUNITY_INVALID",
        )
        intervention_type = _governed_enum(
            item["intervention_type"],
            "DASHBOARD_DOI_INTERVENTION_TYPE_INVALID",
        )
        status = _governed_enum(
            item["status"],
            "DASHBOARD_DOI_INTERVENTION_STATUS_INVALID",
        )
        action_at = _timestamp(
            item["action_occurred_at"],
            "DASHBOARD_DOI_INTERVENTION_ACTION_TIMESTAMP_INVALID",
            optional=True,
        )
        created_at = _timestamp(
            item["created_at"],
            "DASHBOARD_DOI_INTERVENTION_CREATED_TIMESTAMP_INVALID",
        )
        projection_version = _integer(
            item["projection_version"],
            "DASHBOARD_DOI_INTERVENTION_VERSION_INVALID",
            minimum=1,
        )
        head_sha = _lower_sha256(
            item["head_sha256"],
            "DASHBOARD_DOI_INTERVENTION_HEAD_INVALID",
        )
        record_domain = _record_domain(
            item["record_domain"],
            "DASHBOARD_DOI_INTERVENTION_DOMAIN_INVALID",
        )
        record_sha = _lower_sha256(
            item["record_sha256"],
            "DASHBOARD_DOI_INTERVENTION_RECORD_HASH_INVALID",
        )
        intervention_rows.append(
            tuple(
                _h(_display(field))
                for field in (
                    intervention_id,
                    opportunity_id,
                    intervention_type,
                    status,
                    action_at,
                    projection_version,
                    created_at,
                    head_sha,
                    record_domain,
                    record_sha,
                )
            )
        )
        for verification_raw in _list(
            item["verification_events"],
            "DASHBOARD_DOI_VERIFICATIONS_INVALID",
        ):
            verification = _closed_mapping(
                verification_raw,
                _DOI_VERIFICATION_MEMBERS,
                "DASHBOARD_DOI_VERIFICATION_INVALID",
            )
            event_id = _namespace_id(
                verification["event_id"],
                "EVIDENCE",
                "DASHBOARD_DOI_VERIFICATION_EVENT_INVALID",
            )
            if event_id in verification_ids:
                _fail("DASHBOARD_DOI_VERIFICATION_EVENT_DUPLICATE")
            verification_ids.add(event_id)
            occurrence_id = _namespace_id(
                verification["occurrence_id"],
                "INTERACTION",
                "DASHBOARD_DOI_VERIFICATION_OCCURRENCE_INVALID",
            )
            verification_domain = _record_domain(
                verification["record_domain"],
                "DASHBOARD_DOI_VERIFICATION_DOMAIN_INVALID",
            )
            verification_sha = _lower_sha256(
                verification["record_sha256"],
                "DASHBOARD_DOI_VERIFICATION_RECORD_HASH_INVALID",
            )
            verification_rows.append(
                tuple(
                    _h(field)
                    for field in (
                        intervention_id,
                        event_id,
                        occurrence_id,
                        verification_domain,
                        verification_sha,
                    )
                )
            )
    html = f"""<section class="dashboard-panel"
 data-ssa-dashboard-evidence="doi-interventions">
<h2>Interventions and verification</h2>
<p>Evaluation does not create an intervention. Verification remains explicit evidence.</p>
{_table(
    caption="Governed intervention projections",
    headers=(
        "Intervention ID",
        "Opportunity ID",
        "Type",
        "Status",
        "Action occurred UTC",
        "Projection version",
        "Created UTC",
        "Head SHA-256",
        "Record domain",
        "Record SHA-256",
    ),
    rows=intervention_rows,
    selector="doi-interventions",
    empty_message="No intervention has been recorded for this case.",
)}
{_table(
    caption="Immutable action-verification events",
    headers=(
        "Intervention ID",
        "Verification event",
        "Occurrence",
        "Record domain",
        "Record SHA-256",
    ),
    rows=verification_rows,
    selector="doi-intervention-verifications",
    empty_message="No intervention verification has been recorded for this case.",
)}</section>"""
    return html, intervention_ids


def _doi_links_section(
    value: object,
    intervention_ids: set[str],
    order_id: str,
) -> str:
    link_rows: list[tuple[str, ...]] = []
    revision_rows: list[tuple[str, ...]] = []
    mapping_rows: list[tuple[str, ...]] = []
    seen_links: set[str] = set()
    for raw in _list(value, "DASHBOARD_DOI_LINKS_INVALID"):
        item = _closed_mapping(raw, _DOI_LINK_MEMBERS, "DASHBOARD_DOI_LINK_INVALID")
        link_id = _namespace_id(
            item["link_id"],
            "EVIDENCE",
            "DASHBOARD_DOI_LINK_ID_INVALID",
        )
        if link_id in seen_links:
            _fail("DASHBOARD_DOI_LINK_DUPLICATE")
        seen_links.add(link_id)
        intervention_id = _namespace_id(
            item["intervention_id"],
            "EVIDENCE",
            "DASHBOARD_DOI_LINK_INTERVENTION_INVALID",
        )
        if intervention_id not in intervention_ids:
            _fail("DASHBOARD_DOI_LINK_INTERVENTION_MISMATCH")
        parent_order_id = _namespace_id(
            item["parent_order_id"],
            "ORDER",
            "DASHBOARD_DOI_LINK_PARENT_ORDER_INVALID",
        )
        if parent_order_id != order_id:
            _fail("DASHBOARD_DOI_LINK_PARENT_ORDER_MISMATCH")
        child_order_id = _namespace_id(
            item["child_order_id"],
            "ORDER",
            "DASHBOARD_DOI_LINK_CHILD_ORDER_INVALID",
        )
        state = _governed_enum(item["state"], "DASHBOARD_DOI_LINK_STATE_INVALID")
        current_revision = _integer(
            item["current_revision"],
            "DASHBOARD_DOI_LINK_CURRENT_REVISION_INVALID",
            minimum=1,
        )
        head_sha = _lower_sha256(
            item["head_sha256"],
            "DASHBOARD_DOI_LINK_HEAD_INVALID",
        )
        link_rows.append(
            tuple(
                _h(field)
                for field in (
                    link_id,
                    intervention_id,
                    parent_order_id,
                    child_order_id,
                    state,
                    current_revision,
                    head_sha,
                )
            )
        )
        revision_numbers: list[int] = []
        for revision_raw in _list(
            item["revisions"],
            "DASHBOARD_DOI_LINK_REVISIONS_INVALID",
        ):
            revision = _closed_mapping(
                revision_raw,
                _DOI_REVISION_MEMBERS,
                "DASHBOARD_DOI_LINK_REVISION_INVALID",
            )
            number = _integer(
                revision["revision"],
                "DASHBOARD_DOI_LINK_REVISION_NUMBER_INVALID",
                minimum=1,
            )
            revision_numbers.append(number)
            revision_id = _namespace_id(
                revision["revision_id"],
                "EVIDENCE",
                "DASHBOARD_DOI_LINK_REVISION_ID_INVALID",
            )
            predecessor = _lower_sha256(
                revision["predecessor_sha256"],
                "DASHBOARD_DOI_LINK_PREDECESSOR_INVALID",
                optional=True,
            )
            record_domain = _record_domain(
                revision["record_domain"],
                "DASHBOARD_DOI_LINK_REVISION_DOMAIN_INVALID",
            )
            record_sha = _lower_sha256(
                revision["record_sha256"],
                "DASHBOARD_DOI_LINK_REVISION_HASH_INVALID",
            )
            revision_rows.append(
                tuple(
                    _h(_display(field))
                    for field in (
                        link_id,
                        number,
                        revision_id,
                        predecessor,
                        record_domain,
                        record_sha,
                    )
                )
            )
            ordinals: list[int] = []
            for mapping_raw in _list(
                revision["mapping_components"],
                "DASHBOARD_DOI_LINK_MAPPINGS_INVALID",
            ):
                mapping = _closed_mapping(
                    mapping_raw,
                    _DOI_MAPPING_MEMBERS,
                    "DASHBOARD_DOI_LINK_MAPPING_INVALID",
                )
                ordinal = _integer(
                    mapping["ordinal"],
                    "DASHBOARD_DOI_LINK_MAPPING_ORDINAL_INVALID",
                    minimum=1,
                )
                ordinals.append(ordinal)
                parent_line_id = _namespace_id(
                    mapping["parent_line_id"],
                    "EVIDENCE",
                    "DASHBOARD_DOI_LINK_PARENT_LINE_INVALID",
                )
                child_line_id = _namespace_id(
                    mapping["child_line_id"],
                    "EVIDENCE",
                    "DASHBOARD_DOI_LINK_CHILD_LINE_INVALID",
                )
                quantity = _text(
                    mapping["quantity_text"],
                    "DASHBOARD_DOI_LINK_QUANTITY_INVALID",
                )
                assert quantity is not None
                if len(quantity) > 64 or _QUANTITY_TEXT.fullmatch(quantity) is None:
                    _fail("DASHBOARD_DOI_LINK_QUANTITY_INVALID")
                mapping_rows.append(
                    tuple(
                        _h(field)
                        for field in (
                            link_id,
                            number,
                            ordinal,
                            parent_line_id,
                            child_line_id,
                            quantity,
                        )
                    )
                )
            if ordinals != sorted(set(ordinals)):
                _fail("DASHBOARD_DOI_LINK_MAPPING_ORDER_INVALID")
        if (
            revision_numbers != sorted(set(revision_numbers))
            or current_revision not in revision_numbers
        ):
            _fail("DASHBOARD_DOI_LINK_REVISION_ORDER_INVALID")
    return f"""<section class="dashboard-panel"
 data-ssa-dashboard-evidence="doi-resulting-order-links">
<h2>Resulting-order links</h2>
<p>Links are shown only when explicitly governed; no resulting order is inferred.</p>
{_table(
    caption="Current resulting-order link projections",
    headers=(
        "Link ID",
        "Intervention ID",
        "Parent order",
        "Child order",
        "State",
        "Current revision",
        "Head SHA-256",
    ),
    rows=link_rows,
    selector="doi-resulting-order-links",
    empty_message="No resulting-order link has been recorded for this case.",
)}
{_table(
    caption="Immutable resulting-order link revisions",
    headers=(
        "Link ID",
        "Revision",
        "Revision ID",
        "Predecessor SHA-256",
        "Record domain",
        "Record SHA-256",
    ),
    rows=revision_rows,
    selector="doi-resulting-order-link-revisions",
    empty_message="No resulting-order link revision has been recorded for this case.",
)}
{_table(
    caption="Exact line-mapping components by link revision",
    headers=(
        "Link ID",
        "Revision",
        "Ordinal",
        "Parent line",
        "Child line",
        "Exact quantity",
    ),
    rows=mapping_rows,
    selector="doi-resulting-order-line-mappings",
    empty_message="No exact line-mapping component has been recorded for this case.",
)}</section>"""


def _doi_value_section(value: object, intervention_ids: set[str]) -> str:
    by_currency: dict[str, list[tuple[str, ...]]] = {}
    seen_events: set[str] = set()
    for raw in _list(value, "DASHBOARD_DOI_VALUE_EVENTS_INVALID"):
        item = _closed_mapping(raw, _DOI_VALUE_MEMBERS, "DASHBOARD_DOI_VALUE_EVENT_INVALID")
        intervention_id = _namespace_id(
            item["intervention_id"],
            "EVIDENCE",
            "DASHBOARD_DOI_VALUE_INTERVENTION_INVALID",
        )
        if intervention_id not in intervention_ids:
            _fail("DASHBOARD_DOI_VALUE_INTERVENTION_MISMATCH")
        event_id = _namespace_id(
            item["event_id"],
            "EVIDENCE",
            "DASHBOARD_DOI_VALUE_EVENT_ID_INVALID",
        )
        if event_id in seen_events:
            _fail("DASHBOARD_DOI_VALUE_EVENT_DUPLICATE")
        seen_events.add(event_id)
        occurrence_id = _namespace_id(
            item["occurrence_id"],
            "INTERACTION",
            "DASHBOARD_DOI_VALUE_OCCURRENCE_INVALID",
        )
        event_type = _governed_enum(
            item["event_type"],
            "DASHBOARD_DOI_VALUE_EVENT_TYPE_INVALID",
        )
        sequence = _integer(
            item["sequence"],
            "DASHBOARD_DOI_VALUE_SEQUENCE_INVALID",
            minimum=1,
        )
        predecessor = _lower_sha256(
            item["predecessor_sha256"],
            "DASHBOARD_DOI_VALUE_PREDECESSOR_INVALID",
            optional=True,
        )
        amount = _money_text(
            item["amount_minor_units"],
            item["currency_code"],
            item["currency_registry_version"],
            item["currency_scale"],
            "DASHBOARD_DOI_VALUE_MONEY_INVALID",
        )
        currency = str(item["currency_code"])
        record_domain = _record_domain(
            item["record_domain"],
            "DASHBOARD_DOI_VALUE_DOMAIN_INVALID",
        )
        record_sha = _lower_sha256(
            item["record_sha256"],
            "DASHBOARD_DOI_VALUE_RECORD_HASH_INVALID",
        )
        by_currency.setdefault(currency, []).append(
            tuple(
                _h(_display(field))
                for field in (
                    intervention_id,
                    sequence,
                    event_id,
                    event_type,
                    occurrence_id,
                    amount,
                    predecessor,
                    record_domain,
                    record_sha,
                )
            )
        )
    if not by_currency:
        return _table(
            caption="Verified value history grouped by exact currency binding",
            headers=(
                "Intervention ID",
                "Sequence",
                "Event ID",
                "Type",
                "Occurrence",
                "Exact amount / currency",
                "Predecessor SHA-256",
                "Record domain",
                "Record SHA-256",
            ),
            rows=(),
            selector="doi-value-events-empty",
            empty_message="No verified value event has been recorded for this case.",
        )
    return "".join(
        f"""<h3>Verified value events — {_h(currency)}</h3>
{_table(
    caption=f"Verified value-event history for {currency}; no mixed-currency total",
    headers=(
        "Intervention ID",
        "Sequence",
        "Event ID",
        "Type",
        "Occurrence",
        "Exact amount / currency",
        "Predecessor SHA-256",
        "Record domain",
        "Record SHA-256",
    ),
    rows=by_currency[currency],
    selector=f"doi-value-events-{currency.casefold()}",
)}"""
        for currency in sorted(by_currency)
    )


def _doi_kpi_section(value: object, intervention_ids: set[str]) -> str:
    by_currency: dict[str, list[tuple[str, ...]]] = {}
    seen_interventions: set[str] = set()
    for raw in _list(value, "DASHBOARD_DOI_KPI_CONTRIBUTIONS_INVALID"):
        item = _closed_mapping(raw, _DOI_KPI_MEMBERS, "DASHBOARD_DOI_KPI_CONTRIBUTION_INVALID")
        intervention_id = _namespace_id(
            item["intervention_id"],
            "EVIDENCE",
            "DASHBOARD_DOI_KPI_INTERVENTION_INVALID",
        )
        if intervention_id not in intervention_ids:
            _fail("DASHBOARD_DOI_KPI_INTERVENTION_MISMATCH")
        if intervention_id in seen_interventions:
            _fail("DASHBOARD_DOI_KPI_INTERVENTION_DUPLICATE")
        seen_interventions.add(intervention_id)
        intervention_type = _governed_enum(
            item["intervention_type"],
            "DASHBOARD_DOI_KPI_TYPE_INVALID",
        )
        action_day = _action_date(item["action_date"], "DASHBOARD_DOI_KPI_DATE_INVALID")
        revision = _integer(
            item["revision"],
            "DASHBOARD_DOI_KPI_REVISION_INVALID",
            minimum=1,
        )
        head_sha = _lower_sha256(
            item["head_sha256"],
            "DASHBOARD_DOI_KPI_HEAD_INVALID",
        )
        amount = _money_text(
            item["amount_minor_units"],
            item["currency_code"],
            item["currency_registry_version"],
            item["currency_scale"],
            "DASHBOARD_DOI_KPI_MONEY_INVALID",
        )
        currency = str(item["currency_code"])
        by_currency.setdefault(currency, []).append(
            tuple(
                _h(field)
                for field in (
                    intervention_id,
                    intervention_type,
                    action_day,
                    amount,
                    revision,
                    head_sha,
                )
            )
        )
    if not by_currency:
        return _table(
            caption="Current retained KPI contributions grouped by exact currency binding",
            headers=(
                "Intervention ID",
                "Type",
                "Action date",
                "Exact retained amount / currency",
                "Revision",
                "Head SHA-256",
            ),
            rows=(),
            selector="doi-retained-kpi-empty",
            empty_message="No retained verified KPI contribution is currently recorded.",
        )
    return "".join(
        f"""<h3>Retained KPI contributions — {_h(currency)}</h3>
{_table(
    caption=f"Current retained KPI contribution for {currency}; no mixed-currency total",
    headers=(
        "Intervention ID",
        "Type",
        "Action date",
        "Exact retained amount / currency",
        "Revision",
        "Head SHA-256",
    ),
    rows=by_currency[currency],
    selector=f"doi-retained-kpi-{currency.casefold()}",
)}"""
        for currency in sorted(by_currency)
    )


def _doi_current_evaluation(
    value: object,
    expected_evaluation_id: str | None,
    expected_state: str | None,
) -> dict[str, object] | None:
    if expected_evaluation_id is None:
        if value is not None:
            _fail("DASHBOARD_DOI_EVALUATION_UNEXPECTED")
        return None
    item = _closed_mapping(
        value,
        _DOI_CURRENT_EVALUATION_MEMBERS,
        "DASHBOARD_DOI_EVALUATION_INVALID",
    )
    evaluation_id = _namespace_id(
        item["evaluation_id"],
        "EVALUATION",
        "DASHBOARD_DOI_EVALUATION_ID_INVALID",
    )
    if evaluation_id != expected_evaluation_id:
        _fail("DASHBOARD_DOI_EVALUATION_ID_MISMATCH")
    _namespace_id(
        item["snapshot_id"],
        "SNAPSHOT",
        "DASHBOARD_DOI_EVALUATION_SNAPSHOT_INVALID",
    )
    _namespace_id(
        item["run_id"],
        "RUN",
        "DASHBOARD_DOI_EVALUATION_RUN_INVALID",
    )
    if item["input_domain"] != "doi-evaluation-input/v1":
        _fail("DASHBOARD_DOI_EVALUATION_INPUT_DOMAIN_INVALID")
    if item["output_domain"] != "doi-evaluation-output/v1":
        _fail("DASHBOARD_DOI_EVALUATION_OUTPUT_DOMAIN_INVALID")
    _lower_sha256(
        item["input_sha256"],
        "DASHBOARD_DOI_EVALUATION_INPUT_HASH_INVALID",
    )
    _lower_sha256(
        item["output_sha256"],
        "DASHBOARD_DOI_EVALUATION_OUTPUT_HASH_INVALID",
    )
    top_level_state = _governed_enum(
        item["top_level_state"],
        "DASHBOARD_DOI_EVALUATION_STATE_INVALID",
    )
    if top_level_state != expected_state:
        _fail("DASHBOARD_DOI_EVALUATION_STATE_MISMATCH")
    transition = _text(
        item["transition_id"],
        "DASHBOARD_DOI_EVALUATION_TRANSITION_INVALID",
    )
    assert transition is not None
    if _TRANSITION_ID.fullmatch(transition) is None:
        _fail("DASHBOARD_DOI_EVALUATION_TRANSITION_INVALID")
    return item


def _doi_reason_explanation_section(
    value: object,
    expected_codes: Sequence[str],
) -> str:
    rows: list[tuple[str, ...]] = []
    observed_codes: list[str] = []
    registries = load_doi_registries()
    for raw in _list(value, "DASHBOARD_DOI_REASON_EXPLANATIONS_INVALID"):
        item = _closed_mapping(
            raw,
            _DOI_REASON_EXPLANATION_MEMBERS,
            "DASHBOARD_DOI_REASON_EXPLANATION_INVALID",
        )
        code = _reason_code(item["code"], "DASHBOARD_DOI_REASON_CODE_INVALID")
        reason_class = _governed_enum(
            item["class"],
            "DASHBOARD_DOI_REASON_CLASS_INVALID",
        )
        label = _governed_enum(
            item["label"],
            "DASHBOARD_DOI_REASON_LABEL_INVALID",
        )
        description = _text(
            item["description"],
            "DASHBOARD_DOI_REASON_DESCRIPTION_INVALID",
        )
        registry_version = _version_identifier(
            item["registry_version"],
            "DASHBOARD_DOI_REASON_REGISTRY_VERSION_INVALID",
        )
        assert description is not None
        try:
            ref = registries.reason_ref(
                code,
                expected_label=label,
                expected_registry_version=registry_version,
            )
            record = registries.reason_record(ref)
        except RegistryLookupError:
            _fail("DASHBOARD_DOI_REASON_REGISTRY_MISMATCH")
        if (
            record.get("class") != reason_class
            or record.get("description") != description
            or record.get("reason_id") != code
        ):
            _fail("DASHBOARD_DOI_REASON_REGISTRY_MISMATCH")
        observed_codes.append(code)
        rows.append(
            tuple(
                _h(field)
                for field in (
                    code,
                    _humanize_token(label, "DASHBOARD_DOI_REASON_LABEL_INVALID"),
                    description,
                    reason_class,
                    registry_version,
                )
            )
        )
    if observed_codes != list(expected_codes):
        _fail("DASHBOARD_DOI_REASON_ORDER_MISMATCH")
    return _table(
        caption="Immutable DOI registry explanations in evaluation order",
        headers=("Exact code", "Plain label", "Description", "Class", "Registry"),
        rows=rows,
        selector="doi-reason-explanations",
        empty_message="No DOI registry reason is retained for this evaluation.",
    )


def _doi_scenario_selection_section(
    value: object,
    selection_state: str,
    opportunity_ids: set[str],
) -> str:
    if value is None:
        if selection_state == "SELECTED":
            _fail("DASHBOARD_DOI_SCENARIO_SELECTION_MISSING")
        return """<p data-ssa-dashboard-evidence="doi-scenario-selection">
No exact scenario selection is recorded.</p>"""
    if selection_state != "SELECTED":
        _fail("DASHBOARD_DOI_SCENARIO_SELECTION_UNEXPECTED")
    item = _closed_mapping(
        value,
        _DOI_SCENARIO_SELECTION_MEMBERS,
        "DASHBOARD_DOI_SCENARIO_SELECTION_INVALID",
    )
    selection_id = _namespace_id(
        item["selection_id"],
        "EVIDENCE",
        "DASHBOARD_DOI_SELECTION_ID_INVALID",
    )
    selected_id = _namespace_id(
        item["selected_opportunity_id"],
        "EVIDENCE",
        "DASHBOARD_DOI_SELECTED_OPPORTUNITY_INVALID",
    )
    options = [
        _namespace_id(
            raw,
            "EVIDENCE",
            "DASHBOARD_DOI_SELECTION_OPTION_INVALID",
        )
        for raw in _list(
            item["option_opportunity_ids"],
            "DASHBOARD_DOI_SELECTION_OPTIONS_INVALID",
        )
    ]
    expected_options = sorted(opportunity_ids)
    if (
        len(options) < 2
        or options != sorted(set(options))
        or options != expected_options
        or selected_id not in options
    ):
        _fail("DASHBOARD_DOI_SELECTION_OPTIONS_MISMATCH")
    return f"""<div data-ssa-dashboard-evidence="doi-scenario-selection">
{_definition_list(
    (
        ("Selection ID", selection_id),
        ("Selected opportunity", selected_id),
        ("Exact option universe", options),
    )
)}</div>"""


def render_doi_detail(data: object, csrf_token: str, *, presentation: bool = False) -> bytes:
    root = _closed_mapping(data, _DOI_DETAIL_MEMBERS, "DASHBOARD_DOI_DETAIL_INVALID")
    if root["schema_version"] != CONTROL_CENTER_SCHEMA_VERSION:
        _fail("DASHBOARD_DOI_DETAIL_VERSION_INVALID")
    summary = _closed_mapping(
        root["summary"],
        _DOI_SUMMARY_MEMBERS,
        "DASHBOARD_DOI_SUMMARY_INVALID",
    )
    case_id = _namespace_id(
        summary["case_id"],
        "EVIDENCE",
        "DASHBOARD_DOI_CASE_ID_INVALID",
    )
    order_id = _namespace_id(
        summary["order_id"],
        "ORDER",
        "DASHBOARD_DOI_ORDER_ID_INVALID",
    )
    evaluation_id = summary["current_evaluation_id"]
    if evaluation_id is not None:
        evaluation_id = _namespace_id(
            evaluation_id,
            "EVALUATION",
            "DASHBOARD_DOI_EVALUATION_ID_INVALID",
        )
    lifecycle_state = _governed_enum(
        summary["lifecycle_state"],
        "DASHBOARD_DOI_LIFECYCLE_INVALID",
    )
    doi_state = summary["doi_state"]
    if doi_state is not None:
        doi_state = _governed_enum(doi_state, "DASHBOARD_DOI_STATE_INVALID")
    doi_state_label = (
        "Unavailable"
        if doi_state is None
        else _humanize_token(doi_state, "DASHBOARD_DOI_STATE_INVALID")
    )
    current_evaluation = _doi_current_evaluation(
        root["current_evaluation"],
        evaluation_id,
        doi_state,
    )
    aggregate_state = _governed_enum(
        summary["aggregate_potential_state"],
        "DASHBOARD_DOI_AGGREGATE_STATE_INVALID",
    )
    selection_state = _governed_enum(
        summary["scenario_selection_state"],
        "DASHBOARD_DOI_SELECTION_STATE_INVALID",
    )
    updated_at = _timestamp(summary["updated_at"], "DASHBOARD_DOI_UPDATED_AT_INVALID")
    _boolean(
        summary["human_review_required"],
        "DASHBOARD_DOI_REVIEW_REQUIRED_INVALID",
    )
    attention_conditions = [
        _governed_enum(
            raw,
            "DASHBOARD_DOI_SUMMARY_ATTENTION_CAUSE_INVALID",
        )
        for raw in _list(
            summary["attention_causes"],
            "DASHBOARD_DOI_SUMMARY_ATTENTION_INVALID",
        )
    ]
    if len(attention_conditions) != len(set(attention_conditions)):
        _fail("DASHBOARD_DOI_SUMMARY_ATTENTION_DUPLICATE")
    opportunities: list[dict[str, object]] = []
    opportunity_rows: list[tuple[str, ...]] = []
    scope_rows: list[tuple[str, ...]] = []
    opportunity_ids: set[str] = set()
    observed_opportunity_types: set[str] = set()
    for raw in _list(root["opportunities"], "DASHBOARD_DOI_OPPORTUNITIES_INVALID"):
        item = _closed_mapping(
            raw,
            _DOI_OPPORTUNITY_MEMBERS,
            "DASHBOARD_DOI_OPPORTUNITY_INVALID",
        )
        opportunity_id = _namespace_id(
            item["opportunity_id"],
            "EVIDENCE",
            "DASHBOARD_DOI_OPPORTUNITY_ID_INVALID",
        )
        if opportunity_id in opportunity_ids:
            _fail("DASHBOARD_DOI_OPPORTUNITY_DUPLICATE")
        opportunity_ids.add(opportunity_id)
        opportunity_type = _governed_enum(
            item["opportunity_type"],
            "DASHBOARD_DOI_OPPORTUNITY_TYPE_INVALID",
        )
        observed_opportunity_types.add(opportunity_type)
        potential_state = _governed_enum(
            item["potential_state"],
            "DASHBOARD_DOI_OPPORTUNITY_STATE_INVALID",
        )
        exclusion_group = item["mutual_exclusion_group_id"]
        if exclusion_group is not None:
            exclusion_group = _namespace_id(
                exclusion_group,
                "EVIDENCE",
                "DASHBOARD_DOI_EXCLUSION_GROUP_INVALID",
            )
        opportunities.append(item)
        amount = _optional_money_text(item, "DASHBOARD_DOI_OPPORTUNITY_MONEY_INVALID")
        observed_ordinals: list[int] = []
        for scope_raw in _list(
            item["scope_components"],
            "DASHBOARD_DOI_OPPORTUNITY_SCOPE_INVALID",
        ):
            scope = _closed_mapping(
                scope_raw,
                _DOI_SCOPE_MEMBERS,
                "DASHBOARD_DOI_SCOPE_COMPONENT_INVALID",
            )
            line_snapshot_id = _namespace_id(
                scope["line_snapshot_id"],
                "EVIDENCE",
                "DASHBOARD_DOI_SCOPE_LINE_INVALID",
            )
            ordinal = _integer(
                scope["ordinal"],
                "DASHBOARD_DOI_SCOPE_ORDINAL_INVALID",
                minimum=1,
            )
            role = _governed_enum(
                scope["role"],
                "DASHBOARD_DOI_SCOPE_ROLE_INVALID",
            )
            quantity = _text(
                scope["quantity_text"],
                "DASHBOARD_DOI_SCOPE_QUANTITY_INVALID",
            )
            assert quantity is not None
            if _QUANTITY_TEXT.fullmatch(quantity) is None:
                _fail("DASHBOARD_DOI_SCOPE_QUANTITY_INVALID")
            observed_ordinals.append(ordinal)
            scope_rows.append(
                tuple(
                    _h(value)
                    for value in (
                        opportunity_id,
                        ordinal,
                        line_snapshot_id,
                        role,
                        quantity,
                    )
                )
            )
        if observed_ordinals != list(range(1, len(observed_ordinals) + 1)):
            _fail("DASHBOARD_DOI_SCOPE_ORDINAL_SEQUENCE_INVALID")
        opportunity_rows.append(
            tuple(
                _h(value)
                for value in (
                    opportunity_id,
                    opportunity_type,
                    potential_state,
                    amount,
                    _display(exclusion_group),
                )
            )
        )
    summary_opportunity_types: set[str] = set()
    for raw in _list(
        summary["opportunity_types"],
        "DASHBOARD_DOI_SUMMARY_OPPORTUNITY_TYPES_INVALID",
    ):
        summary_opportunity_types.add(
            _governed_enum(raw, "DASHBOARD_DOI_SUMMARY_OPPORTUNITY_TYPE_INVALID")
        )
    if summary_opportunity_types != observed_opportunity_types:
        _fail("DASHBOARD_DOI_OPPORTUNITY_TYPES_MISMATCH")
    reasons = _list(summary["reason_codes"], "DASHBOARD_DOI_REASONS_INVALID")
    validated_reasons = [
        _reason_code(raw, "DASHBOARD_DOI_REASON_INVALID") for raw in reasons
    ]
    reason_explanations = _doi_reason_explanation_section(
        root["reason_explanations"],
        validated_reasons,
    )
    scenario_selection = _doi_scenario_selection_section(
        root["scenario_selection"],
        selection_state,
        opportunity_ids,
    )
    if selection_state == "REQUIRED" and (
        evaluation_id is None or len(opportunities) < 2
    ):
        _fail("DASHBOARD_DOI_REQUIRED_SELECTION_INCOHERENT")
    selection = (
        _doi_selection_form(
            case_id,
            evaluation_id,
            opportunities,
        )
        if selection_state == "REQUIRED" and evaluation_id is not None and opportunities
        else """<section class="dashboard-panel"><h2>Required human action</h2>
<p>No supported overlap-scenario action is currently required. Other DOI human
operations remain read-only because no purpose-specific committed service exists.</p></section>"""
    )
    expected_snapshot_id = (
        None if current_evaluation is None else str(current_evaluation["snapshot_id"])
    )
    expected_run_id = (
        None if current_evaluation is None else str(current_evaluation["run_id"])
    )
    source_section = _doi_source_section(
        root["source_completeness"],
        order_id,
        expected_snapshot_id=expected_snapshot_id,
        expected_run_id=expected_run_id,
    )
    handling_attention_section = _doi_handling_attention_section(
        root["handling_flags"],
        root["current_attention_causes"],
        attention_conditions,
    )
    human_facts_section = _doi_human_facts_section(root["human_fact_events"])
    interventions_section, intervention_ids = _doi_interventions_section(
        root["interventions"]
    )
    links_section = _doi_links_section(
        root["resulting_order_links"],
        intervention_ids,
        order_id,
    )
    value_section = _doi_value_section(root["value_events"], intervention_ids)
    kpi_section = _doi_kpi_section(
        root["retained_kpi_contributions"],
        intervention_ids,
    )
    timeline = _timeline(root["timeline"], subject_kind="DOI_CASE", subject_id=case_id)
    _doi_privacy_check(root)
    evaluation_binding: tuple[tuple[str, object], ...]
    if current_evaluation is None:
        evaluation_binding = (("Current evaluation binding", "Unavailable"),)
    else:
        evaluation_binding = (
            ("Evaluation ID", current_evaluation["evaluation_id"]),
            ("Snapshot ID", current_evaluation["snapshot_id"]),
            ("Run ID", current_evaluation["run_id"]),
            ("Transition", current_evaluation["transition_id"]),
            ("Input domain", current_evaluation["input_domain"]),
            ("Input SHA-256", current_evaluation["input_sha256"]),
            ("Output domain", current_evaluation["output_domain"]),
            ("Output SHA-256", current_evaluation["output_sha256"]),
        )
    body = f"""<nav class="dashboard-nav" aria-label="Case links">
<a href="/orders/{_h(order_id)}">Synthetic order</a>
<a href="/audit/DOI_CASE/{_h(case_id)}">Audit-only view</a></nav>
<section class="dashboard-split">
 <article class="dashboard-panel dashboard-callout"
  data-ssa-dashboard-card="doi-system-state"><h2>Current DOI state</h2>
 {_state_badge(doi_state)}{_definition_list(
     (
         ("Lifecycle", lifecycle_state),
         ("Current evaluation", evaluation_id),
         ("Updated", updated_at),
     )
 )}</article>
 <article class="dashboard-panel" data-ssa-dashboard-card="plain-english-why">
  <h2>Why the system stopped here</h2>
  <p>The system state is <strong>{_h(doi_state_label)}</strong>
  (exact code <code>{_h(_display(doi_state))}</code>). Registry labels and descriptions
  below are retained in exact evaluation order. Unknown facts remain unknown.</p>
  {reason_explanations}</article>
</section>
{selection}
{source_section}
<section class="dashboard-panel" data-ssa-dashboard-evidence="doi-evaluation-binding">
<h2>Current evaluation binding</h2>{_definition_list(evaluation_binding)}</section>
<section class="dashboard-panel" data-ssa-dashboard-current-projection="doi-opportunities">
<h2>Current opportunities and exact scope</h2>
{_table(
    caption="Separate current DOI opportunities; overlap is not combined",
    headers=(
        "Opportunity ID",
        "Type",
        "Potential state",
        "Exact amount by currency",
        "Exclusion group",
    ),
    rows=opportunity_rows,
    selector="doi-opportunities",
)}
{_table(
    caption="Ordered line scope for each separate current opportunity",
    headers=("Opportunity ID", "Ordinal", "Line snapshot", "Role", "Quantity"),
    rows=scope_rows,
    selector="doi-opportunity-scope",
    empty_message="No governed line-scope component is recorded for these opportunities.",
)}</section>
<section class="dashboard-panel" data-ssa-dashboard-card="doi-aggregate-potential">
<h2>Aggregate-potential state</h2>{_state_badge(aggregate_state)}
{_definition_list((("Scenario selection", selection_state),))}
{scenario_selection}
<p>Unresolved overlap is unavailable, not zero. Separate currencies are never combined.</p>
</section>
{handling_attention_section}
{human_facts_section}
{interventions_section}
{links_section}
<section class="dashboard-panel" data-ssa-dashboard-evidence="doi-value-kpi-history">
<h2>Value and KPI history by currency</h2>
<p>Only verified evidence contributes. Corrections and reversals remain immutable events;
current retained contributions are separate and no mixed-currency total is shown.</p>
{value_section}{kpi_section}</section>
{timeline}
<section class="dashboard-panel"><h2>Developer contract identity</h2>
{_definition_list(
    (
        ("Control Center", CONTROL_CENTER_SCHEMA_VERSION),
        ("Dashboard DOM", DASHBOARD_DOM_VERSION),
        ("Portal DOM", DOM_SCHEMA_VERSION),
    )
)}</section>"""
    return _page(
        route_name="doi_detail",
        heading=f"DOI case {case_id}",
        lede=(
            "Current system state, opportunities, human facts, intervention evidence, "
            "and immutable history remain distinct."
        ),
        body=body,
        csrf_token=csrf_token,
        presentation=presentation,
    )


def render_review(data: object, csrf_token: str, *, presentation: bool = False) -> bytes:
    root = _closed_mapping(
        _privacy_check(data),
        frozenset({"items", "schema_version", "total_count"}),
        "DASHBOARD_REVIEW_INVALID",
    )
    if root["schema_version"] != CONTROL_CENTER_SCHEMA_VERSION:
        _fail("DASHBOARD_REVIEW_VERSION_INVALID")
    items = _list(root["items"], "DASHBOARD_REVIEW_ITEMS_INVALID")
    if _integer(root["total_count"], "DASHBOARD_REVIEW_TOTAL_INVALID") != len(items):
        _fail("DASHBOARD_REVIEW_RECONCILIATION_INVALID")
    rows: list[tuple[str, ...]] = []
    observed_subjects: set[tuple[str, str]] = set()
    for raw in items:
        item = _closed_mapping(raw, _REVIEW_MEMBERS, "DASHBOARD_REVIEW_ITEM_INVALID")
        domain = _text(item["domain"], "DASHBOARD_REVIEW_DOMAIN_INVALID")
        audit_kind = _audit_kind(item["audit_subject_kind"])
        assert domain is not None
        if domain not in {"SALES_CREDIT", "DOI"}:
            _fail("DASHBOARD_REVIEW_DOMAIN_INVALID")
        namespace = "ORDER" if domain == "SALES_CREDIT" else "EVIDENCE"
        subject_id = _namespace_id(
            item["subject_id"],
            namespace,
            "DASHBOARD_REVIEW_SUBJECT_INVALID",
        )
        subject_key = (domain, subject_id)
        if subject_key in observed_subjects:
            _fail("DASHBOARD_REVIEW_SUBJECT_DUPLICATE")
        observed_subjects.add(subject_key)
        order_id = _namespace_id(
            item["order_id"],
            "ORDER",
            "DASHBOARD_REVIEW_ORDER_INVALID",
        )
        source_state = _governed_enum(
            item["source_completeness_state"],
            "DASHBOARD_REVIEW_SOURCE_INVALID",
        )
        if source_state != "COMPLETE_EVALUATION_RECORDED":
            _fail("DASHBOARD_REVIEW_SOURCE_INVALID")
        system_state = _governed_enum(
            item["system_state"],
            "DASHBOARD_REVIEW_SYSTEM_STATE_INVALID",
        )
        required_action = _governed_enum(
            item["required_action"],
            "DASHBOARD_REVIEW_ACTION_INVALID",
        )
        action_available = _boolean(
            item["action_available"],
            "DASHBOARD_REVIEW_ACTION_AVAILABLE_INVALID",
        )
        reason_codes = _list(
            item["reason_codes"],
            "DASHBOARD_REVIEW_REASONS_INVALID",
        )
        if not reason_codes:
            _fail("DASHBOARD_REVIEW_REASONS_INVALID")
        accepted_reasons = [
            _reason_code(reason, "DASHBOARD_REVIEW_REASON_INVALID")
            for reason in reason_codes
        ]
        if len(set(accepted_reasons)) != len(accepted_reasons):
            _fail("DASHBOARD_REVIEW_REASON_INVALID")
        if domain == "SALES_CREDIT":
            if (
                subject_id != order_id
                or audit_kind != "SALES_CREDIT_CASE"
                or required_action != "RECORD_MANAGER_OUTCOME"
                or not action_available
                or system_state not in _SC_WORKFLOW_STATES - {"CLOSED"}
                or accepted_reasons != [system_state]
            ):
                _fail("DASHBOARD_REVIEW_DOMAIN_BINDING_INVALID")
        else:
            if (
                audit_kind != "DOI_CASE"
                or required_action
                not in {"REVIEW_EXACT_REASON", "SELECT_OVERLAP_SCENARIO"}
                or action_available
                != (required_action == "SELECT_OVERLAP_SCENARIO")
                or system_state not in _DOI_STATES
                or (
                    required_action == "SELECT_OVERLAP_SCENARIO"
                    and (
                        system_state != "DOI_OPPORTUNITY"
                        or "RC-087" not in accepted_reasons
                    )
                )
            ):
                _fail("DASHBOARD_REVIEW_DOMAIN_BINDING_INVALID")
            registries = load_doi_registries()
            for reason in accepted_reasons:
                try:
                    registries.reason_ref(reason)
                except RegistryLookupError:
                    _fail("DASHBOARD_REVIEW_REASON_INVALID")
        detail = "/sales-credit/" if domain == "SALES_CREDIT" else "/doi/"
        rows.append(
            (
                _h(domain),
                (
                    f'<a data-ssa-dashboard-id="{_h(subject_id)}" '
                    f'href="{detail}{_h(subject_id)}">{_h(subject_id)}</a>'
                ),
                _h(_display(accepted_reasons)),
                _h(system_state),
                _h(source_state),
                _h(required_action),
                _h("Action available on detail" if action_available else "Read-only"),
                f'<a href="/audit/{_h(audit_kind)}/{_h(subject_id)}">Audit history</a>',
            )
        )
    body = f"""<section class="dashboard-panel"
 data-ssa-dashboard-current-projection="human-review">
{_table(
    caption="Current unresolved review items with domain authority preserved",
    headers=(
        "Domain",
        "Current subject",
        "Exact reasons",
        "System state",
        "Source completeness",
        "Required human action",
        "Permitted local action",
        "History",
    ),
    rows=rows,
    selector="human-review-current-projections",
)}
</section>"""
    return _page(
        route_name="review",
        heading="Current human-review queue",
        lede=(
            "One presentation layer, separate authorities: Sales Credit manager outcomes "
            "never become DOI human facts, and vice versa."
        ),
        body=body,
        csrf_token=csrf_token,
        presentation=presentation,
    )


def render_audit(data: object, csrf_token: str, *, presentation: bool = False) -> bytes:
    root = _closed_mapping(
        _privacy_check(data),
        frozenset({"events", "schema_version", "subject_id", "subject_kind"}),
        "DASHBOARD_AUDIT_INVALID",
    )
    if root["schema_version"] != CONTROL_CENTER_SCHEMA_VERSION:
        _fail("DASHBOARD_AUDIT_VERSION_INVALID")
    kind = _audit_kind(root["subject_kind"])
    subject_id = _audit_subject_id(
        root["subject_id"],
        kind,
        "DASHBOARD_AUDIT_SUBJECT_INVALID",
    )
    body = _timeline(root["events"], subject_kind=kind, subject_id=subject_id)
    return _page(
        route_name="audit",
        heading=f"Immutable audit timeline for {subject_id}",
        lede="History is append-only evidence. It is not the current queue population.",
        body=body,
        csrf_token=csrf_token,
        presentation=presentation,
    )


def _extension(value: object) -> dict[str, object]:
    extension = _closed_mapping(value, _EXTENSION_MEMBERS, "DASHBOARD_EXTENSION_INVALID")
    if extension["schema_version"] != EXTENSION_STATUS_SCHEMA_VERSION:
        _fail("DASHBOARD_EXTENSION_VERSION_INVALID")
    expected_version = _text(
        extension["expected_version"],
        "DASHBOARD_EXTENSION_EXPECTED_VERSION_INVALID",
    )
    if (
        expected_version != CHROME_EXTENSION_VERSION
        or _SEMANTIC_VERSION.fullmatch(expected_version) is None
    ):
        _fail("DASHBOARD_EXTENSION_EXPECTED_VERSION_INVALID")
    package_sha = _text(
        extension["expected_package_sha256"],
        "DASHBOARD_EXTENSION_HASH_INVALID",
    )
    if (
        package_sha != _EXPECTED_EXTENSION_PACKAGE_SHA256
        or _LOWER_SHA256.fullmatch(package_sha) is None
    ):
        _fail("DASHBOARD_EXTENSION_HASH_INVALID")
    observed_version = _text(
        extension["observed_version"],
        "DASHBOARD_EXTENSION_OBSERVED_VERSION_INVALID",
        optional=True,
    )
    if (
        observed_version is not None
        and _SEMANTIC_VERSION.fullmatch(observed_version) is None
    ):
        _fail("DASHBOARD_EXTENSION_OBSERVED_VERSION_INVALID")
    last_seen = _timestamp(
        extension["last_seen_at"],
        "DASHBOARD_EXTENSION_LAST_SEEN_INVALID",
        optional=True,
    )
    stale_after = _integer(
        extension["stale_after_seconds"],
        "DASHBOARD_EXTENSION_STALE_AFTER_INVALID",
        minimum=1,
    )
    if stale_after > 86_400:
        _fail("DASHBOARD_EXTENSION_STALE_AFTER_INVALID")
    state = _text(extension["state"], "DASHBOARD_EXTENSION_STATE_INVALID")
    if state not in ExtensionStatusState.ALL:
        _fail("DASHBOARD_EXTENSION_STATE_INVALID")
    has_observation = observed_version is not None and last_seen is not None
    if (observed_version is None) != (last_seen is None):
        _fail("DASHBOARD_EXTENSION_OBSERVATION_INVALID")
    if state in {
        ExtensionStatusState.EXPECTED_PACKAGE_ONLY,
        ExtensionStatusState.UNKNOWN,
    }:
        if has_observation:
            _fail("DASHBOARD_EXTENSION_COHERENCE_INVALID")
    elif not has_observation:
        _fail("DASHBOARD_EXTENSION_COHERENCE_INVALID")
    elif state == ExtensionStatusState.VERSION_MISMATCH:
        if observed_version == expected_version:
            _fail("DASHBOARD_EXTENSION_COHERENCE_INVALID")
    elif observed_version != expected_version:
        _fail("DASHBOARD_EXTENSION_COHERENCE_INVALID")
    if last_seen is not None:
        seen = CanonicalTimestamp(last_seen)
        seen_ns = seen.epoch_seconds * 1_000_000_000 + seen.nanosecond
        age_ns = time.time_ns() - seen_ns
        future_tolerance_ns = 5_000_000_000
        stale_after_ns = stale_after * 1_000_000_000
        if age_ns < -future_tolerance_ns:
            _fail("DASHBOARD_EXTENSION_LAST_SEEN_INVALID")
        if state == ExtensionStatusState.LAST_SEEN_HEALTHY and age_ns > stale_after_ns:
            _fail("DASHBOARD_EXTENSION_FRESHNESS_INVALID")
        if state == ExtensionStatusState.LAST_SEEN_STALE and age_ns <= stale_after_ns:
            _fail("DASHBOARD_EXTENSION_FRESHNESS_INVALID")
    return extension


def _backup(value: object) -> dict[str, object]:
    backup = _closed_mapping(value, _BACKUP_MEMBERS, "DASHBOARD_BACKUP_INVALID")
    _evidence_kind_id(
        backup["backup_id"],
        _BACKUP_ID_PREFIX,
        "DASHBOARD_BACKUP_ID_INVALID",
    )
    if backup["schema_version"] != _DATABASE_SCHEMA_VERSION:
        _fail("DASHBOARD_BACKUP_SCHEMA_INVALID")
    _timestamp(
        backup["completed_at"],
        "DASHBOARD_BACKUP_TIMESTAMP_INVALID",
        optional=True,
    )
    sha256 = _text(
        backup["backup_sha256"],
        "DASHBOARD_BACKUP_HASH_INVALID",
        optional=True,
    )
    if sha256 is not None and _LOWER_SHA256.fullmatch(sha256) is None:
        _fail("DASHBOARD_BACKUP_HASH_INVALID")
    status = _governed_enum(backup["status"], "DASHBOARD_BACKUP_STATUS_INVALID")
    if status not in {"COMPLETED", "FAILED", "STARTED"}:
        _fail("DASHBOARD_BACKUP_STATUS_INVALID")
    for member in ("foreign_key_check", "quick_check"):
        if backup[member] not in {"failed", "not_run", "ok"}:
            _fail("DASHBOARD_BACKUP_CHECK_INVALID")
    if status == "COMPLETED" and (
        backup["completed_at"] is None
        or sha256 is None
        or backup["quick_check"] != "ok"
        or backup["foreign_key_check"] != "ok"
    ):
        _fail("DASHBOARD_BACKUP_VERIFICATION_INVALID")
    if status == "STARTED" and (
        backup["completed_at"] is not None
        or sha256 is not None
        or backup["quick_check"] != "not_run"
        or backup["foreign_key_check"] != "not_run"
    ):
        _fail("DASHBOARD_BACKUP_VERIFICATION_INVALID")
    if status == "FAILED" and (
        backup["completed_at"] is None
        or sha256 is None
        or "failed"
        not in {backup["quick_check"], backup["foreign_key_check"]}
    ):
        _fail("DASHBOARD_BACKUP_FAILURE_EVIDENCE_INVALID")
    return backup


def _restore(value: object) -> dict[str, object]:
    restore = _closed_mapping(value, _RESTORE_MEMBERS, "DASHBOARD_RESTORE_INVALID")
    _evidence_kind_id(
        restore["restore_id"],
        _RESTORE_ID_PREFIX,
        "DASHBOARD_RESTORE_ID_INVALID",
    )
    _lower_sha256(restore["backup_sha256"], "DASHBOARD_RESTORE_HASH_INVALID")
    pre_restore = restore["pre_restore_backup_id"]
    if pre_restore is not None:
        _evidence_kind_id(
            pre_restore,
            _BACKUP_ID_PREFIX,
            "DASHBOARD_RESTORE_BACKUP_ID_INVALID",
        )
    schema_version = restore["schema_version"]
    if schema_version is not None:
        if schema_version != _DATABASE_SCHEMA_VERSION:
            _fail("DASHBOARD_RESTORE_SCHEMA_INVALID")
    _timestamp(
        restore["completed_at"],
        "DASHBOARD_RESTORE_TIMESTAMP_INVALID",
        optional=True,
    )
    status = _governed_enum(restore["status"], "DASHBOARD_RESTORE_STATUS_INVALID")
    if status not in {"COMPLETED", "FAILED", "STARTED"}:
        _fail("DASHBOARD_RESTORE_STATUS_INVALID")
    error_code = restore["error_code"]
    if error_code is not None:
        _governed_enum(error_code, "DASHBOARD_RESTORE_ERROR_INVALID")
    if status == "COMPLETED" and (
        restore["completed_at"] is None
        or schema_version != _DATABASE_SCHEMA_VERSION
        or error_code is not None
    ):
        _fail("DASHBOARD_RESTORE_COHERENCE_INVALID")
    if status == "STARTED" and (
        restore["completed_at"] is not None
        or schema_version is not None
        or error_code is not None
    ):
        _fail("DASHBOARD_RESTORE_COHERENCE_INVALID")
    if status == "FAILED" and (
        restore["completed_at"] is None or error_code is None
    ):
        _fail("DASHBOARD_RESTORE_COHERENCE_INVALID")
    return restore


def _benchmark_reference(value: object) -> dict[str, object]:
    reference = _closed_mapping(
        value,
        _BENCHMARK_REFERENCE_MEMBERS,
        "DASHBOARD_BENCHMARK_REFERENCE_INVALID",
    )
    if reference["version"] != M4_BENCHMARK_REFERENCE_VERSION:
        _fail("DASHBOARD_BENCHMARK_VERSION_INVALID")
    exact_numbers = {
        "database_size_bytes": 78_577_664,
        "exact_replays": 100,
        "unique_evaluations": 1_000,
    }
    for member, expected in exact_numbers.items():
        if reference[member] != expected:
            _fail("DASHBOARD_BENCHMARK_VALUE_INVALID")
    exact_decimals = {
        "median_latency_ms": "226.490150",
        "p95_latency_ms": "545.652600",
        "throughput_per_second": "4.409734",
    }
    for member, expected in exact_decimals.items():
        value_text = _text(reference[member], "DASHBOARD_BENCHMARK_VALUE_INVALID")
        if value_text != expected or _CANONICAL_DECIMAL.fullmatch(value_text) is None:
            _fail("DASHBOARD_BENCHMARK_VALUE_INVALID")
    expected_sha = (
        "d2b30ebd3dc7daad6ccec65b46f1e6836a6463e5669a89beee02c8fb37ed073d"
    )
    if _lower_sha256(
        reference["verified_backup_sha256"],
        "DASHBOARD_BENCHMARK_HASH_INVALID",
    ) != expected_sha:
        _fail("DASHBOARD_BENCHMARK_HASH_INVALID")
    return reference


def _safe_errors(value: object) -> list[dict[str, object]]:
    accepted: list[dict[str, object]] = []
    items = _list(value, "DASHBOARD_SAFE_ERRORS_INVALID")
    if len(items) > 10:
        _fail("DASHBOARD_SAFE_ERRORS_INVALID")
    for raw in items:
        item = _closed_mapping(raw, _SAFE_ERROR_MEMBERS, "DASHBOARD_SAFE_ERROR_INVALID")
        _governed_enum(item["code"], "DASHBOARD_SAFE_ERROR_CODE_INVALID")
        category = _governed_enum(
            item["category"],
            "DASHBOARD_SAFE_ERROR_CATEGORY_INVALID",
        )
        if category not in {
            "COLLISION",
            "CONFLICT",
            "DATABASE",
            "PRIVACY",
            "VALIDATION",
            "VERSION",
        }:
            _fail("DASHBOARD_SAFE_ERROR_CATEGORY_INVALID")
        _boolean(item["retryable"], "DASHBOARD_SAFE_ERROR_RETRYABLE_INVALID")
        _timestamp(item["occurred_at"], "DASHBOARD_SAFE_ERROR_TIMESTAMP_INVALID")
        accepted.append(item)
    return accepted


def _distribution(
    value: object,
    code: str,
    *,
    allowed: frozenset[str] | None = None,
) -> dict[str, object]:
    if type(value) is not dict:
        _fail(code)
    distribution = value
    if len(distribution) > 64:
        _fail(code)
    for key, count in distribution.items():
        _governed_enum(key, code)
        if allowed is not None and key not in allowed:
            _fail(code)
        _integer(count, code, minimum=1)
    return distribution


def _operational_status(value: object) -> dict[str, object]:
    status = _closed_mapping(
        value,
        _OPERATIONAL_STATUS_MEMBERS,
        "DASHBOARD_OPERATIONAL_STATUS_INVALID",
    )
    _integer(status["database_size_bytes"], "DASHBOARD_DATABASE_SIZE_INVALID")
    if status["latest_backup"] is not None:
        _backup(status["latest_backup"])
    if status["latest_restore"] is not None:
        _restore(status["latest_restore"])
    safety_observed_at = _timestamp(
        status["safety_observed_at"],
        "DASHBOARD_SAFETY_OBSERVED_AT_INVALID",
    )
    verification_observed_at = _timestamp(
        status["verification_observed_at"],
        "DASHBOARD_VERIFICATION_OBSERVED_AT_INVALID",
    )
    if safety_observed_at != verification_observed_at:
        _fail("DASHBOARD_OPERATIONAL_OBSERVATION_COHERENCE_INVALID")
    return status


def _migrations(value: object) -> list[object]:
    items = _list(value, "DASHBOARD_MIGRATIONS_INVALID")
    if len(items) != len(_MIGRATION_INVENTORY):
        _fail("DASHBOARD_MIGRATION_INVENTORY_INVALID")
    observed: list[tuple[int, str, str]] = []
    for raw in items:
        item = _closed_mapping(
            raw,
            frozenset({"applied_at_utc", "name", "sha256", "version"}),
            "DASHBOARD_MIGRATION_INVALID",
        )
        version = _integer(
            item["version"],
            "DASHBOARD_MIGRATION_VERSION_INVALID",
            minimum=1,
        )
        name = _text(item["name"], "DASHBOARD_MIGRATION_NAME_INVALID")
        assert name is not None
        if _MIGRATION_NAME.fullmatch(name) is None:
            _fail("DASHBOARD_MIGRATION_NAME_INVALID")
        sha256 = _lower_sha256(
            item["sha256"],
            "DASHBOARD_MIGRATION_HASH_INVALID",
        )
        assert sha256 is not None
        _migration_timestamp(item["applied_at_utc"])
        observed.append((version, name, sha256))
    if tuple(observed) != _MIGRATION_INVENTORY:
        _fail("DASHBOARD_MIGRATION_INVENTORY_INVALID")
    return items


def _database(value: object) -> dict[str, object]:
    database = _closed_mapping(value, _DATABASE_MEMBERS, "DASHBOARD_DATABASE_INVALID")
    if database["schema_version"] != _DATABASE_SCHEMA_VERSION:
        _fail("DASHBOARD_DATABASE_SCHEMA_INVALID")
    if database["application_schema_version"] != APPLICATION_SCHEMA_VERSION:
        _fail("DASHBOARD_DATABASE_APPLICATION_VERSION_INVALID")
    if database["build_version"] != APPLICATION_BUILD_VERSION:
        _fail("DASHBOARD_DATABASE_BUILD_VERSION_INVALID")
    location_class = _text(
        database["database_location_class"],
        "DASHBOARD_DATABASE_LOCATION_CLASS_INVALID",
    )
    if location_class not in _DATABASE_LOCATION_CLASSES:
        _fail("DASHBOARD_DATABASE_LOCATION_CLASS_INVALID")
    _integer(database["database_size_bytes"], "DASHBOARD_DATABASE_SIZE_INVALID")
    database_status = _text(
        database["database_status"],
        "DASHBOARD_DATABASE_STATUS_INVALID",
    )
    if database_status not in {"HEALTHY", "UNHEALTHY"}:
        _fail("DASHBOARD_DATABASE_STATUS_INVALID")
    quick_check = _text(
        database["quick_check"],
        "DASHBOARD_DATABASE_QUICK_CHECK_INVALID",
    )
    if quick_check != "ok":
        _fail("DASHBOARD_DATABASE_QUICK_CHECK_INVALID")
    integrity_check = _text(
        database["integrity_check"],
        "DASHBOARD_DATABASE_INTEGRITY_CHECK_INVALID",
    )
    if integrity_check not in {"NOT_REQUESTED", "ok"}:
        _fail("DASHBOARD_DATABASE_INTEGRITY_CHECK_INVALID")
    foreign_key_status = _text(
        database["foreign_key_status"],
        "DASHBOARD_DATABASE_FOREIGN_KEY_STATUS_INVALID",
    )
    if foreign_key_status not in {"OK", "VIOLATIONS"}:
        _fail("DASHBOARD_DATABASE_FOREIGN_KEY_STATUS_INVALID")
    projection_status = _text(
        database["projection_status"],
        "DASHBOARD_DATABASE_PROJECTION_STATUS_INVALID",
    )
    if projection_status not in {"DRIFT", "OK"}:
        _fail("DASHBOARD_DATABASE_PROJECTION_STATUS_INVALID")
    if (database_status == "HEALTHY") != (foreign_key_status == "OK"):
        _fail("DASHBOARD_DATABASE_STATUS_COHERENCE_INVALID")
    _migrations(database["migrations"])
    if database["latest_backup"] is not None:
        latest_backup = _backup(database["latest_backup"])
        if latest_backup["status"] != "COMPLETED":
            _fail("DASHBOARD_BACKUP_VERIFICATION_INVALID")
    if database["latest_restore"] is not None:
        _restore(database["latest_restore"])
    safety_observed_at = _timestamp(
        database["safety_observed_at"],
        "DASHBOARD_SAFETY_OBSERVED_AT_INVALID",
    )
    verification_observed_at = _timestamp(
        database["verification_observed_at"],
        "DASHBOARD_VERIFICATION_OBSERVED_AT_INVALID",
    )
    if safety_observed_at != verification_observed_at:
        _fail("DASHBOARD_DATABASE_OBSERVATION_COHERENCE_INVALID")
    _zero_safety_counters(
        database["safety_counters"],
        "DASHBOARD_SAFETY_COUNTERS_INVALID",
    )
    return database


def _safety_table(value: object) -> str:
    counters = _zero_safety_counters(value, "DASHBOARD_SAFETY_COUNTERS_INVALID")
    rows = [
        (_h(name), _h(count))
        for name, count in sorted(counters.items())
    ]
    return _table(
        caption="All nine current safety counters",
        headers=("Counter", "Value"),
        rows=rows,
        selector="system-safety-counters",
    )


def _database_summary(database: Mapping[str, object]) -> str:
    latest = database["latest_backup"]
    latest_status = (
        "No verified backup receipt"
        if latest is None
        else (
            f"{_backup(latest)['backup_id']} / "
            f"{_display(_backup(latest)['status'])}"
        )
    )
    latest_restore = database["latest_restore"]
    latest_restore_status = (
        "No restore receipt"
        if latest_restore is None
        else (
            f"{_restore(latest_restore)['restore_id']} / "
            f"{_display(_restore(latest_restore)['status'])}"
        )
    )
    return _definition_list(
        (
            ("Database status", database["database_status"]),
            ("Schema version", database["schema_version"]),
            ("Privacy-safe location class", database["database_location_class"]),
            ("Database size (bytes)", database["database_size_bytes"]),
            ("Quick check", database["quick_check"]),
            ("Integrity check", database["integrity_check"]),
            ("Foreign keys", database["foreign_key_status"]),
            ("Projection verification", database["projection_status"]),
            ("Latest verified backup", latest_status),
            ("Latest restore receipt", latest_restore_status),
            ("Verification observed at", database["verification_observed_at"]),
            ("Safety counters observed at", database["safety_observed_at"]),
        )
    )


def render_system(data: object, csrf_token: str, *, presentation: bool = False) -> bytes:
    root = _closed_mapping(
        _privacy_check(data),
        frozenset(
            {
                "api_request_schema_version",
                "api_schema_version",
                "application_schema_version",
                "application_version",
                "benchmark_reference",
                "build_version",
                "database",
                "dom_schema_version",
                "extension",
                "network_policy",
                "owned_pid",
                "recent_safe_errors",
                "runtime_directory_class",
                "schema_version",
                "service_origin",
                "service_status",
            }
        ),
        "DASHBOARD_SYSTEM_INVALID",
    )
    if root["schema_version"] != CONTROL_CENTER_SCHEMA_VERSION:
        _fail("DASHBOARD_SYSTEM_VERSION_INVALID")
    exact_versions = {
        "api_request_schema_version": API_REQUEST_SCHEMA_VERSION,
        "api_schema_version": API_SCHEMA_VERSION,
        "application_schema_version": APPLICATION_SCHEMA_VERSION,
        "application_version": APPLICATION_VERSION,
        "build_version": APPLICATION_BUILD_VERSION,
        "dom_schema_version": DOM_SCHEMA_VERSION,
    }
    if any(root[member] != expected for member, expected in exact_versions.items()):
        _fail("DASHBOARD_SYSTEM_COMPONENT_VERSION_INVALID")
    service_status = _text(
        root["service_status"],
        "DASHBOARD_SERVICE_STATUS_INVALID",
    )
    if service_status not in {"FAIL", "PASS"}:
        _fail("DASHBOARD_SERVICE_STATUS_INVALID")
    if root["network_policy"] != "LOOPBACK_ONLY_EXTERNAL_REQUESTS_ZERO":
        _fail("DASHBOARD_NETWORK_POLICY_INVALID")
    if root["runtime_directory_class"] != "OWNED_LOCAL_RUNTIME_DIRECTORY":
        _fail("DASHBOARD_RUNTIME_DIRECTORY_CLASS_INVALID")
    _service_origin(root["service_origin"])
    _integer(root["owned_pid"], "DASHBOARD_OWNED_PID_INVALID", minimum=1)
    benchmark = _benchmark_reference(root["benchmark_reference"])
    database = _database(root["database"])
    expected_service_status = (
        "PASS"
        if database["database_status"] == "HEALTHY"
        and database["projection_status"] == "OK"
        else "FAIL"
    )
    if service_status != expected_service_status:
        _fail("DASHBOARD_SYSTEM_STATUS_COHERENCE_INVALID")
    extension = _extension(root["extension"])
    recent_errors = _safe_errors(root["recent_safe_errors"])
    benchmark_rows = [
        (_h(label), _h(benchmark[member]), _h(unit))
        for member, label, unit in (
            ("unique_evaluations", "Unique evaluations", "evaluations"),
            ("exact_replays", "Exact replays", "requests"),
            ("median_latency_ms", "Median latency", "milliseconds"),
            ("p95_latency_ms", "P95 latency", "milliseconds"),
            ("throughput_per_second", "Throughput", "calls/second"),
            ("database_size_bytes", "Database size", "bytes"),
            ("verified_backup_sha256", "Verified backup", "SHA-256"),
        )
    ]
    error_rows = [
        (
            _h(item["occurred_at"]),
            _h(item["code"]),
            _h(item["category"]),
            "Yes" if item["retryable"] else "No",
        )
        for item in recent_errors
    ]
    body = f"""<section class="dashboard-grid">
<article class="dashboard-card" data-ssa-dashboard-card="service-status"><h2>Service status</h2>
<strong class="dashboard-value">{_h(root['service_status'])}</strong>
<p>Owned service response at {_h(root['service_origin'])}.</p>
<p class="dashboard-volatile">Owned PID: {_h(root['owned_pid'])}</p></article>
<article class="dashboard-card" data-ssa-dashboard-card="database-status"><h2>Database health</h2>
<strong class="dashboard-value">{_h(_display(database['database_status']))}</strong>
<a href="/system/database">Verification details</a></article>
<article class="dashboard-card" data-ssa-dashboard-card="extension-status"><h2>Extension status</h2>
{_state_badge(extension['state'])}
<p>Package presence alone never means installed or running.</p>
<a href="/system/extension">Status evidence</a></article>
<article class="dashboard-card" data-ssa-dashboard-card="network-policy"><h2>Network policy</h2>
<strong class="dashboard-value">{_h(root['network_policy'])}</strong>
<p>Runtime external network requests: 0.</p></article>
</section>
<section class="dashboard-split">
<article class="dashboard-panel"><h2>Version identity</h2>
{_definition_list(
    (
        ("Application view", root["application_schema_version"]),
        ("Application version", root["application_version"]),
        ("Build", root["build_version"]),
        ("API response", root["api_schema_version"]),
        ("API request", root["api_request_schema_version"]),
        ("Portal DOM", root["dom_schema_version"]),
        ("Control Center", root["schema_version"]),
        ("Database schema", database["schema_version"]),
        ("Runtime directory", root["runtime_directory_class"]),
    )
)}</article>
<article class="dashboard-panel"><h2>Database summary</h2>{_database_summary(database)}</article>
</section>
<section class="dashboard-panel" data-ssa-dashboard-card="safety-counters">
<h2>Safety boundary</h2>{_safety_table(database['safety_counters'])}</section>
<section class="dashboard-panel" data-ssa-dashboard-card="benchmark-reference">
<h2>Committed Milestone 4 benchmark reference</h2>
<p>Reference version: {_h(benchmark['version'])}. This fixed baseline is not a live result.</p>
{_table(
    caption="Committed Milestone 4 benchmark baseline and verified backup reference",
    headers=("Measure", "Value", "Unit"),
    rows=benchmark_rows,
    selector="system-benchmark-reference",
)}</section>
<section class="dashboard-panel" data-ssa-dashboard-card="recent-safe-errors">
<h2>Recent safe errors</h2>
{_table(
    caption="Bounded recent error metadata; no raw payload, stack trace, or path",
    headers=("Observed", "Code", "Category", "Retryable"),
    rows=error_rows,
    selector="system-recent-safe-errors",
)}</section>
<section class="dashboard-panel"><h2>Operations</h2>
<nav class="dashboard-nav" aria-label="System operations">
<a href="/system">Refresh health</a><a href="/system/database">Database verification</a>
<a href="/system/backups">Verified backups</a><a href="/system/telemetry">Telemetry</a></nav>
<p>Restore and reset remain separate strongly confirmed maintenance workflows and are
not dashboard actions.</p></section>"""
    return _page(
        route_name="system",
        heading="Local system health",
        lede=(
            "Privacy-safe operational evidence for the owned loopback service, schema-4 "
            "database, expected extension package, and safety boundary."
        ),
        body=body,
        csrf_token=csrf_token,
        presentation=presentation,
    )


def render_database(data: object, csrf_token: str, *, presentation: bool = False) -> bytes:
    root = _closed_mapping(
        _privacy_check(data),
        frozenset({"database", "schema_version"}),
        "DASHBOARD_DATABASE_VIEW_INVALID",
    )
    if root["schema_version"] != CONTROL_CENTER_SCHEMA_VERSION:
        _fail("DASHBOARD_DATABASE_VIEW_VERSION_INVALID")
    database = _database(root["database"])
    migration_rows: list[tuple[str, ...]] = []
    for raw in _list(database["migrations"], "DASHBOARD_MIGRATIONS_INVALID"):
        item = _closed_mapping(
            raw,
            frozenset({"applied_at_utc", "name", "sha256", "version"}),
            "DASHBOARD_MIGRATION_INVALID",
        )
        migration_rows.append(
            tuple(
                _h(_display(item[key]))
                for key in ("version", "name", "sha256", "applied_at_utc")
            )
        )
    verify_form = f"""<form class="dashboard-form" data-ssa-dashboard-action="database-verify"
 data-ssa-dashboard-endpoint="/api/v1/dashboard/system/database/verify">
{_hidden("schema_version", DATABASE_VERIFY_REQUEST_VERSION)}
<button type="submit">Run deep read-only verification</button>
<p class="dashboard-live-region" role="status" tabindex="-1"
 data-ssa-dashboard-live-region="database-verify"
 data-ssa-dashboard-action-status></p>
<a href="/system/database">Refresh database verification</a>
</form>"""
    body = f"""<section class="dashboard-panel dashboard-callout"
 data-ssa-dashboard-card="database-verification">
<h2>Current database verification</h2>
{_database_summary(database)}{verify_form}</section>
<section class="dashboard-panel"><h2>Applied migrations</h2>
{_table(
    caption="Applied schema migrations and committed checksums",
    headers=("Version", "Name", "SHA-256", "Applied UTC"),
    rows=migration_rows,
    selector="database-migrations",
)}</section>
<section class="dashboard-panel"><h2>Projection and safety integrity</h2>
{_safety_table(database['safety_counters'])}</section>"""
    return _page(
        route_name="database",
        heading="Database health and verification",
        lede=(
            "Read-only quick, deep, foreign-key, migration, and projection evidence. "
            "No raw SQL rows or absolute path is exposed."
        ),
        body=body,
        csrf_token=csrf_token,
        presentation=presentation,
    )


def render_backups(data: object, csrf_token: str, *, presentation: bool = False) -> bytes:
    root = _closed_mapping(
        _privacy_check(data),
        frozenset({"items", "schema_version", "total_count"}),
        "DASHBOARD_BACKUPS_INVALID",
    )
    if root["schema_version"] != CONTROL_CENTER_SCHEMA_VERSION:
        _fail("DASHBOARD_BACKUPS_VERSION_INVALID")
    items = _list(root["items"], "DASHBOARD_BACKUP_ITEMS_INVALID")
    if len(items) > 25:
        _fail("DASHBOARD_BACKUP_ITEMS_INVALID")
    if _integer(root["total_count"], "DASHBOARD_BACKUP_TOTAL_INVALID") != len(items):
        _fail("DASHBOARD_BACKUP_RECONCILIATION_INVALID")
    rows = []
    observed_backup_ids: set[str] = set()
    for raw in items:
        item = _backup(raw)
        backup_id = str(item["backup_id"])
        if backup_id in observed_backup_ids:
            _fail("DASHBOARD_BACKUP_ID_DUPLICATE")
        observed_backup_ids.add(backup_id)
        rows.append(
            tuple(
                _h(_display(item[key]))
                for key in (
                    "backup_id",
                    "status",
                    "completed_at",
                    "schema_version",
                    "quick_check",
                    "foreign_key_check",
                    "backup_sha256",
                )
            )
        )
    create_form = f"""<section class="dashboard-panel dashboard-warning"
 data-ssa-dashboard-action-region="create-backup"><h2>Create one verified backup</h2>
<p>The server derives a managed local destination. The browser cannot supply a
filesystem path or overwrite flag.</p>
<form class="dashboard-form" data-ssa-dashboard-action="create-backup"
 data-ssa-dashboard-endpoint="/api/v1/dashboard/system/backups">
{_hidden("schema_version", BACKUP_REQUEST_VERSION)}
{_hidden("request_schema_version", API_REQUEST_SCHEMA_VERSION)}
<label class="dashboard-field"><span>Request key</span>
<input name="request_key" maxlength="96" autocomplete="off" required></label>
<label class="dashboard-confirmation">
<input type="checkbox" name="confirmed" data-ssa-value-type="boolean" required>
<span>I confirm creation and immediate verification of one new owned local synthetic
backup.</span></label>
<button type="submit">Create verified backup</button>
<p class="dashboard-live-region" role="status" tabindex="-1"
 data-ssa-dashboard-live-region="create-backup" data-ssa-dashboard-action-status></p>
<a href="/system/backups">Refresh backup receipts</a>
</form></section>"""
    body = f"""{create_form}<section class="dashboard-panel"
 data-ssa-dashboard-current-projection="backup-receipts">
<h2>Verified backup receipts</h2>
{_table(
    caption="Privacy-safe verified backup receipt inventory",
    headers=(
        "Backup ID",
        "Status",
        "Completed",
        "Schema",
        "Quick check",
        "Foreign keys",
        "SHA-256",
    ),
    rows=rows,
    selector="verified-backup-receipts",
)}</section>
<section class="dashboard-panel"><h2>Recovery boundary</h2>
<p>Restore and reset are deliberately absent from this overview workflow. Use their
separate, strongly confirmed maintenance interfaces.</p></section>"""
    return _page(
        route_name="backups",
        heading="Verified local backups",
        lede=(
            "Only managed, verified receipt summaries are displayed. Absolute paths and "
            "local usernames are never returned."
        ),
        body=body,
        csrf_token=csrf_token,
        presentation=presentation,
    )


def _rate_row(label: str, rate: object) -> tuple[str, ...]:
    item = _closed_mapping(rate, _RATE_MEMBERS, "DASHBOARD_RATE_INVALID")
    _boolean(item["defined"], "DASHBOARD_RATE_DEFINED_INVALID")
    numerator = _integer(item["numerator"], "DASHBOARD_RATE_NUMERATOR_INVALID")
    denominator = _integer(item["denominator"], "DASHBOARD_RATE_DENOMINATOR_INVALID")
    display = _text(item["display"], "DASHBOARD_RATE_DISPLAY_INVALID")
    return (_h(label), _h(display), _h(numerator), _h(denominator))


def _currency_rows(value: object) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    for raw in _list(value, "DASHBOARD_CURRENCY_TOTALS_INVALID"):
        item = _closed_mapping(raw, _CURRENCY_MEMBERS, "DASHBOARD_CURRENCY_TOTAL_INVALID")
        rows.append(
            (
                _h(item["currency_code"]),
                _h(
                    _format_minor_units(
                        item["amount_minor_units"],
                        item["currency_scale"],
                        item["currency_code"],
                    )
                ),
                _h(item["item_count"]),
                _h(item["currency_registry_version"]),
            )
        )
    return rows


def render_telemetry(data: object, csrf_token: str, *, presentation: bool = False) -> bytes:
    root = _closed_mapping(
        _privacy_check(data),
        frozenset(
            {
                "benchmark_reference",
                "denominator_registry",
                "metrics",
                "operational_status",
                "schema_version",
            }
        ),
        "DASHBOARD_TELEMETRY_INVALID",
    )
    if root["schema_version"] != CONTROL_CENTER_SCHEMA_VERSION:
        _fail("DASHBOARD_TELEMETRY_VERSION_INVALID")
    benchmark = _benchmark_reference(root["benchmark_reference"])
    metrics = _validated_metrics(root["metrics"])
    operational = _operational_status(root["operational_status"])
    registry = _closed_mapping(
        root["denominator_registry"],
        frozenset({"metrics", "schema_version"}),
        "DASHBOARD_DENOMINATOR_REGISTRY_INVALID",
    )
    if registry["schema_version"] != DENOMINATOR_REGISTRY_VERSION:
        _fail("DASHBOARD_DENOMINATOR_VERSION_INVALID")
    registry_items = _list(
        registry["metrics"],
        "DASHBOARD_DENOMINATOR_ITEMS_INVALID",
    )
    expected_registry_items = [item.to_dict() for item in METRIC_DENOMINATOR_REGISTRY]
    if registry_items != expected_registry_items:
        _fail("DASHBOARD_DENOMINATOR_INVENTORY_INVALID")
    definition_rows: list[tuple[str, ...]] = []
    for raw in registry_items:
        item = _closed_mapping(
            raw,
            frozenset(
                {
                    "denominator",
                    "empty_display",
                    "exclusions",
                    "inclusions",
                    "label",
                    "metric_id",
                    "numerator",
                    "time_basis",
                }
            ),
            "DASHBOARD_DENOMINATOR_ITEM_INVALID",
        )
        metric_id = _text(item["metric_id"], "DASHBOARD_METRIC_ID_INVALID")
        definition_rows.append(
            (
                f'<span id="{_h(metric_id)}">{_h(item["label"])}</span>',
                _h(item["numerator"]),
                _h(_display(item["denominator"])),
                _h(_display(item["inclusions"])),
                _h(_display(item["exclusions"])),
                _h(item["time_basis"]),
                _h(item["empty_display"]),
            )
        )
    rate_rows = [
        _rate_row("Successful request rate", metrics["successful_request_rate"]),
        _rate_row("Fail-closed rate", metrics["failed_closed_rate"]),
        _rate_row("Human-review rate", metrics["human_review_rate"]),
        _rate_row("Manager-outcome rate", metrics["manager_outcome_rate"]),
    ]
    count_rows = [
        (_h(label), _h(metrics[key]))
        for key, label in (
            ("requests_received", "Business requests received"),
            ("unique_evaluations", "Unique evaluations"),
            ("exact_replays", "Exact replays"),
            ("material_conflicts", "Material conflicts"),
            ("successful_requests", "Successful requests"),
            ("failed_closed_requests", "Failed-closed requests"),
            ("database_error_count", "Database-error requests"),
            ("active_sales_credit_cases", "Active Sales Credit cases"),
            ("active_doi_cases", "Active DOI cases"),
            ("active_doi_opportunities", "Active DOI opportunities"),
            ("current_human_review_items", "Current human-review items"),
        )
    ]
    latency_rows = [
        ("Median", _h(_display(metrics["median_latency_ns"])), "nanoseconds"),
        ("P95", _h(_display(metrics["p95_latency_ns"])), "nanoseconds"),
        (
            "Throughput",
            _h(_display(metrics["throughput_per_second"])),
            "terminal business requests/second",
        ),
    ]
    potential_rows = _currency_rows(metrics["potential_by_currency"])
    realized_rows = _currency_rows(metrics["realized_by_currency"])
    distribution_rows: list[tuple[str, ...]] = []
    for member, series in (
        ("request_result_distribution", "Terminal request result"),
        ("sales_credit_result_distribution", "Sales Credit evaluation result"),
        ("doi_evaluation_result_distribution", "DOI evaluation result"),
        ("doi_state_distribution", "Current DOI case state"),
        ("opportunity_type_counts", "Current active opportunity type"),
    ):
        for label, count in _distribution(
            metrics[member],
            "DASHBOARD_RESULT_DISTRIBUTION_INVALID",
        ).items():
            distribution_rows.append((_h(series), _h(_display(label)), _h(count)))
    latest_backup = operational["latest_backup"]
    backup_display = (
        "No verified backup receipt"
        if latest_backup is None
        else f"{_backup(latest_backup)['backup_id']} / {_backup(latest_backup)['status']}"
    )
    latest_restore = operational["latest_restore"]
    restore_display = (
        "No restore receipt"
        if latest_restore is None
        else f"{_restore(latest_restore)['restore_id']} / {_restore(latest_restore)['status']}"
    )
    current_database_size = _integer(
        operational["database_size_bytes"],
        "DASHBOARD_DATABASE_SIZE_INVALID",
    )
    benchmark_database_size = _integer(
        benchmark["database_size_bytes"],
        "DASHBOARD_BENCHMARK_VALUE_INVALID",
    )
    operational_rows = [
        ("Current database size", _h(current_database_size), "bytes"),
        (
            "Delta from M4 benchmark reference",
            _h(current_database_size - benchmark_database_size),
            "bytes",
        ),
        ("Latest verified backup", _h(backup_display), "receipt / status"),
        ("Latest restore", _h(restore_display), "receipt / status"),
        (
            "Database verification observed",
            _h(operational["verification_observed_at"]),
            "UTC",
        ),
        (
            "Safety counters observed",
            _h(operational["safety_observed_at"]),
            "UTC",
        ),
    ]
    benchmark_rows = [
        (_h(label), _h(benchmark[member]), _h(unit))
        for member, label, unit in (
            ("unique_evaluations", "Unique evaluations", "evaluations"),
            ("exact_replays", "Exact replays", "requests"),
            ("median_latency_ms", "Median latency", "milliseconds"),
            ("p95_latency_ms", "P95 latency", "milliseconds"),
            ("throughput_per_second", "Throughput", "calls/second"),
            ("database_size_bytes", "Database size", "bytes"),
            ("verified_backup_sha256", "Verified backup", "SHA-256"),
        )
    ]
    body = f"""<section class="dashboard-panel"><h2>Declared metric window</h2>
<p>{_h(metrics['window'])}</p></section>
<section class="dashboard-panel">{_table(
    caption="Current counts with replays and conflicts separated",
    headers=("Metric", "Count"),
    rows=count_rows,
    selector="telemetry-counts",
)}</section>
<section class="dashboard-panel">{_table(
    caption="Closed result and current-projection distributions",
    headers=("Series", "Result or state", "Count"),
    rows=distribution_rows,
    selector="telemetry-result-distributions",
)}</section>
<section class="dashboard-panel">{_table(
    caption="Rates with explicit numerator and denominator; empty denominator displays N/A",
    headers=("Rate", "Display", "Numerator", "Denominator"),
    rows=rate_rows,
    selector="telemetry-rates",
)}</section>
<section class="dashboard-panel">{_table(
    caption="Latency and throughput sample for terminal business requests",
    headers=("Series", "Value", "Unit"),
    rows=latency_rows,
    selector="telemetry-latency",
)}</section>
<section class="dashboard-split">
<article class="dashboard-panel"><h2>Current exact potential by currency</h2>
{_table(
    caption="Potential value; unavailable and unresolved overlap are excluded",
    headers=("Currency", "Exact total", "Items", "Registry"),
    rows=potential_rows,
    selector="potential-by-currency",
)}
<p>Unavailable values: {_h(metrics['potential_unavailable_count'])} · unresolved overlap:
{_h(metrics['unresolved_overlap_count'])}.</p></article>
<article class="dashboard-panel"><h2>Current verified realized value by currency</h2>
{_table(
    caption="Verified realized value after corrections and reversals",
    headers=("Currency", "Exact total", "Items", "Registry"),
    rows=realized_rows,
    selector="realized-by-currency",
)}</article>
</section>
<section class="dashboard-panel"><h2>Versioned denominator registry</h2>
{_table(
    caption=(
        "Every metric numerator, denominator, inclusion, exclusion, time basis, and "
        "empty display"
    ),
    headers=(
        "Metric",
        "Numerator",
        "Denominator",
        "Included",
        "Excluded",
        "Time basis",
        "Empty display",
    ),
    rows=definition_rows,
    selector="metric-denominator-registry",
)}</section>
<section class="dashboard-split">
<article class="dashboard-panel"><h2>Current operational metadata</h2>
{_table(
    caption="Current database, backup, restore, verification, and safety observations",
    headers=("Measure", "Value", "Unit"),
    rows=operational_rows,
    selector="telemetry-operational-status",
)}</article>
<article class="dashboard-panel"><h2>Milestone 4 benchmark reference</h2>
<p>Reference version: {_h(benchmark['version'])}. This is a committed comparison baseline.</p>
{_table(
    caption="Committed Milestone 4 benchmark baseline and verified backup reference",
    headers=("Measure", "Value", "Unit"),
    rows=benchmark_rows,
    selector="telemetry-benchmark-reference",
)}</article></section>
<section class="dashboard-panel"><h2>Safety status</h2>
{_safety_table(metrics['safety_counters'])}</section>"""
    return _page(
        route_name="telemetry",
        heading="Telemetry and metric denominators",
        lede=(
            "Every rate exposes its population. Money is segmented by currency, overlap "
            "remains unavailable, and empty denominators display N/A."
        ),
        body=body,
        csrf_token=csrf_token,
        presentation=presentation,
    )


def render_extension(data: object, csrf_token: str, *, presentation: bool = False) -> bytes:
    root = _closed_mapping(
        _privacy_check(data),
        frozenset({"extension", "schema_version"}),
        "DASHBOARD_EXTENSION_VIEW_INVALID",
    )
    if root["schema_version"] != CONTROL_CENTER_SCHEMA_VERSION:
        _fail("DASHBOARD_EXTENSION_VIEW_VERSION_INVALID")
    extension = _extension(root["extension"])
    semantics = {
        "EXPECTED_PACKAGE_ONLY": (
            "The expected repository package exists; installation or execution has not "
            "been observed."
        ),
        "LAST_SEEN_HEALTHY": (
            "A matching local extension version was observed within the documented "
            "stale threshold."
        ),
        "LAST_SEEN_STALE": (
            "A matching version was observed locally, but its last-seen time is now stale."
        ),
        "VERSION_MISMATCH": (
            "The most recently observed local extension version differs from the "
            "expected package."
        ),
        "UNKNOWN": "Neither expected package evidence nor a usable local observation is available.",
    }
    state = _text(extension["state"], "DASHBOARD_EXTENSION_STATE_INVALID")
    assert state is not None
    if state not in semantics:
        _fail("DASHBOARD_EXTENSION_STATE_INVALID")
    body = f"""<section class="dashboard-panel dashboard-callout"
 data-ssa-dashboard-card="extension-status"><h2>Truthful extension state</h2>
{_state_badge(state)}<p>{_h(semantics[state])}</p>
{_definition_list(
    (
        ("Expected version", extension["expected_version"]),
        ("Expected package SHA-256", extension["expected_package_sha256"]),
        ("Observed version", extension["observed_version"]),
        ("Last seen", extension["last_seen_at"]),
        ("Stale threshold (seconds)", extension["stale_after_seconds"]),
    )
)}</section>
<section class="dashboard-panel"><h2>Exact Chrome permission boundary</h2>
{_definition_list(
    (
        ("Permission", "sidePanel"),
        ("Host permission", "http://127.0.0.1/*"),
        ("Host permission ", "http://localhost/*"),
    )
)}</section>
<section class="dashboard-panel"><h2>Operational meaning</h2>
<p>The dashboard works without the extension. A process-local heartbeat uses no new
permission, stores no source payload, and is lost on service restart.</p></section>"""
    return _page(
        route_name="extension",
        heading="Chrome extension status",
        lede=(
            "Package presence is not installation evidence. Status reflects only the "
            "expected package and bounded local last-seen observation."
        ),
        body=body,
        csrf_token=csrf_token,
        presentation=presentation,
    )


_RENDERERS: Final[Mapping[str, Callable[..., bytes]]] = {
    "overview": render_overview,
    "sales_credit_queue": render_sales_credit_queue,
    "sales_credit_detail": render_sales_credit_detail,
    "doi_queue": render_doi_queue,
    "doi_detail": render_doi_detail,
    "review": render_review,
    "audit": render_audit,
    "system": render_system,
    "database": render_database,
    "backups": render_backups,
    "telemetry": render_telemetry,
    "extension": render_extension,
}


def render_dashboard_page(
    route_name: str,
    data: object,
    csrf_token: str,
    *,
    presentation: bool = False,
) -> bytes:
    """Render one allowlisted Control Center page from its closed application view."""

    if type(route_name) is not str or type(presentation) is not bool:
        _fail("DASHBOARD_RENDER_REQUEST_INVALID")
    renderer = _RENDERERS.get(route_name)
    if renderer is None:
        _fail("DASHBOARD_ROUTE_INVALID")
    return renderer(data, csrf_token, presentation=presentation)


def validate_dashboard_page_data(route_name: str, data: object) -> object:
    """Run the exact HTML route contract before returning privacy-safe JSON data."""

    if type(route_name) is not str:
        _fail("DASHBOARD_RENDER_REQUEST_INVALID")
    renderer = _RENDERERS.get(route_name)
    if renderer is None:
        _fail("DASHBOARD_ROUTE_INVALID")
    renderer(data, "0" * 64, presentation=False)
    return data


__all__ = [
    "BACKUP_REQUEST_VERSION",
    "DASHBOARD_DOM_VERSION",
    "DATABASE_VERIFY_REQUEST_VERSION",
    "DOI_SCENARIO_SELECTION_REQUEST_VERSION",
    "MANAGER_OUTCOME_REQUEST_VERSION",
    "render_audit",
    "render_backups",
    "render_campaign_replies",
    "render_dashboard_page",
    "render_database",
    "render_doi_detail",
    "render_doi_queue",
    "render_extension",
    "render_overview",
    "render_review",
    "render_sales_credit_detail",
    "render_sales_credit_queue",
    "render_system",
    "render_telemetry",
    "validate_dashboard_page_data",
]
