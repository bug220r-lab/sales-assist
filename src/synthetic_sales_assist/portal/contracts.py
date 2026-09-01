"""Closed HTTP and rendering contracts for the synthetic localhost portal."""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path
from typing import Final, NoReturn, Protocol, cast, runtime_checkable

from synthetic_sales_assist.application import validate_line_fact
from synthetic_sales_assist.application.manifest import (
    ordered_line_manifest_digest_from_mappings,
)
from synthetic_sales_assist.domain.canonical import canonical_json_bytes
from synthetic_sales_assist.domain.numeric import (
    JSON_SAFE_INTEGER_MAXIMUM,
    Money,
    MoneyViolation,
)
from synthetic_sales_assist.domain.timestamps import (
    CanonicalTimestamp,
    TimestampValidationError,
)
from synthetic_sales_assist.persistence.telemetry import SAFETY_COUNTER_NAMES
from synthetic_sales_assist.safety.content import assert_payload_safe
from synthetic_sales_assist.safety.identity import is_reserved_identity


API_SCHEMA_VERSION = "synthetic-sales-assist-api/v1"
API_REQUEST_SCHEMA_VERSION = "synthetic-sales-assist-api-request/v1"
DOM_SCHEMA_VERSION = "synthetic-sales-assist-dom/v1"
RUNTIME_RECEIPT_SCHEMA_VERSION = "synthetic-sales-assist-runtime-receipt/v1"
APPLICATION_SCHEMA_VERSION = "synthetic-sales-assist-application/v1"
CONTROL_CENTER_SCHEMA_VERSION = "synthetic-sales-assist-control-center/v1"
EXTENSION_HANDSHAKE_SCHEMA_VERSION = (
    "synthetic-sales-assist-extension-handshake/v1"
)
MANAGER_OUTCOME_REQUEST_SCHEMA_VERSION = (
    "synthetic-sales-assist-manager-outcome-request/v1"
)
DOI_SCENARIO_SELECTION_REQUEST_SCHEMA_VERSION = (
    "synthetic-sales-assist-doi-scenario-selection-request/v1"
)
DATABASE_VERIFY_REQUEST_SCHEMA_VERSION = (
    "synthetic-sales-assist-database-verify-request/v1"
)
BACKUP_CREATE_REQUEST_SCHEMA_VERSION = "synthetic-sales-assist-backup-request/v1"
HUMAN_ACTION_RESULT_SCHEMA_VERSION = "synthetic-sales-assist-human-action-result/v1"
BACKUP_ACTION_RESULT_SCHEMA_VERSION = (
    "synthetic-sales-assist-backup-action-result/v1"
)
M8_EVIDENCE_SURFACES_SCHEMA_VERSION = (
    "synthetic-sales-assist-m8-evidence-surfaces/v1"
)

MAX_REQUEST_BODY_BYTES = 16 * 1024
MAX_RESPONSE_BODY_BYTES = 512 * 1024
MAX_PUBLIC_DEPTH = 20
MAX_PUBLIC_COLLECTION = 4_096
MAX_PUBLIC_STRING = 4_096

FAIL_CLOSED_RENDER_MODES: Final = frozenset(
    {
        "dom-payload-mismatch",
        "missing-required-section",
        "stale-source-changed",
    }
)

_REQUEST_KEY = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)
_EXTENSION_VERSION = re.compile(
    r"\A(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z",
    re.ASCII,
)
_ALIAS = re.compile(r"\A[a-z][a-z0-9-]{0,62}[a-z0-9]\Z", re.ASCII)
_MODE = re.compile(r"\A[a-z][a-z0-9-]{0,62}[a-z0-9]\Z", re.ASCII)
_LOWER_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z", re.ASCII)
_ERROR_CODE = re.compile(r"\A[A-Z][A-Z0-9_]{0,95}\Z", re.ASCII)
_SAFE_MEMBER = re.compile(r"\A[A-Za-z][A-Za-z0-9_]{0,95}\Z", re.ASCII)
_CANONICAL_DECIMAL = re.compile(r"\A(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z", re.ASCII)
_CANONICAL_TOKEN = re.compile(r"\A[A-Z][A-Z0-9_.:/-]{0,255}\Z", re.ASCII)
_TRANSITION_ID = re.compile(r"\ATR-(?:00[1-9]|0[1-9][0-9]|1[01][0-5])\Z")
_DASHBOARD_PRIVATE_PATH = re.compile(
    r"(?:\A[/\\~]|(?<![A-Za-z])[A-Za-z]:[/\\]|"
    r"[/\\]users[/\\]|\\\\|file:|device:)",
    re.IGNORECASE,
)
_DASHBOARD_LOOPBACK_ORIGIN = re.compile(
    r"\Ahttp://(?:127\.0\.0\.1|localhost):[0-9]{1,5}/\Z",
    re.ASCII,
)
_DASHBOARD_LOCAL_ROUTE = re.compile(r"\A/[A-Za-z0-9_/-]*\Z", re.ASCII)
_EMPTY_MEMBERS: Final[frozenset[str]] = frozenset()
_DASHBOARD_GOVERNED_TEXT_MEMBERS: Final = frozenset(
    {
        "aggregate_potential_state",
        "amount_minor_units",
        "application_schema_version",
        "application_version",
        "attribution",
        "audit_subject_kind",
        "build_version",
        "currency_code",
        "currency_registry_version",
        "currency_scale",
        "database_location_class",
        "database_size_bytes",
        "database_status",
        "direction",
        "doi_state",
        "doi_state_distribution",
        "domain",
        "empty_display",
        "event_kind",
        "exclusions",
        "extension_status",
        "foreign_key_status",
        "inclusions",
        "integrity_check",
        "interaction_count",
        "label",
        "lifecycle_state",
        "limit",
        "location_class",
        "manager_outcome",
        "median_latency_ms",
        "metric_id",
        "mutual_exclusion_group_id",
        "name",
        "network_policy",
        "numerator",
        "offset",
        "opportunity_type",
        "opportunity_type_counts",
        "opportunity_types",
        "order_value_status",
        "owned_pid",
        "potential_state",
        "p95_latency_ms",
        "potential_by_currency",
        "projection_status",
        "quick_check",
        "reason_codes",
        "realized_by_currency",
        "required_action",
        "runtime_directory_class",
        "scenario_selection_state",
        "safety_counters",
        "schema_version",
        "service_origin",
        "service_status",
        "stale_after_seconds",
        "source_completeness_state",
        "state",
        "status",
        "subject_kind",
        "time_basis",
        "total_count",
        "transition_id",
        "window",
        "workflow_state",
    }
)
_MONEY_MEMBERS: Final = frozenset(
    {"amount", "currency_code", "currency_registry_version", "currency_scale"}
)
_FACT_MEMBERS: Final = frozenset({"reason_code", "tag", "value"})
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
_COMPLETENESS_MEMBERS: Final = frozenset(
    {
        "declared_relevant_line_count",
        "fixture_version",
        "observed_order_id",
        "ordered_line_manifest_digest",
        "rendered_relevant_line_count",
        "requested_order_id",
        "source_observed_at",
        "source_schema_version",
        "state",
    }
)
_SCENARIO_MEMBERS: Final = frozenset(
    {
        "alias",
        "allowed_modes",
        "collected_scenario",
        "complexity",
        "description",
        "expected_result",
        "rule_pack",
        "schema_version",
    }
)
_ORDER_SUMMARY_MEMBERS: Final = frozenset(
    {
        "doi_state",
        "evaluated",
        "human_review_required",
        "mode",
        "order_id",
        "order_status",
        "relevant_line_count",
        "rule_pack",
        "sales_credit_state",
        "scenario_alias",
        "schema_version",
        "updated_at",
    }
)
_ORDER_DETAIL_MEMBERS: Final = _ORDER_SUMMARY_MEMBERS | frozenset(
    {
        "completeness",
        "created_at",
        "interaction_ids",
        "latest_evaluation",
        "lines",
        "source_status",
    }
)
_OPPORTUNITY_MEMBERS: Final = frozenset(
    {"line_ids", "opportunity_type", "potential_value"}
)
_EXPLANATION_MEMBERS: Final = frozenset(
    {
        "normalized_facts",
        "precedence_decision",
        "reason_ownership",
        "rules_evaluated",
        "supplied_facts",
        "unavailable_facts",
    }
)
_PROCESSING_STAGE_MEMBERS: Final = frozenset({"duration_ns", "stage", "status"})
_EVALUATION_MEMBERS: Final = frozenset(
    {
        "aggregate_potential_status",
        "aggregate_potential_value",
        "case_id",
        "closure_state",
        "command_id",
        "conflict",
        "evaluation_id",
        "explanation",
        "fired_rules",
        "handling_flags",
        "human_review_required",
        "opportunities",
        "order_id",
        "processing_duration_ns",
        "processing_stages",
        "reasons",
        "replayed",
        "rule_pack",
        "rule_pack_version",
        "run_id",
        "scenario_alias",
        "schema_version",
        "snapshot_id",
        "top_level_result",
        "value",
        "value_status",
        "workflow_state",
    }
)
_HISTORY_EVENT_MEMBERS: Final = frozenset(
    {"evaluation_id", "event_id", "event_kind", "occurred_at", "sequence", "state"}
)
_HISTORY_ARTIFACT_MEMBERS: Final = frozenset(
    {
        "artifact_id",
        "artifact_type",
        "occurred_at",
        "reasons",
        "state",
        "transition_id",
        "value",
    }
)
_RECEIPT_MEMBERS: Final = frozenset({"command_id", "recorded_at", "replayed"})
_ATTEMPT_RECEIPT_MEMBERS: Final = frozenset(
    {
        "attempt_id",
        "command_id",
        "conflict",
        "error_code",
        "outcome",
        "recorded_at",
        "replayed",
        "telemetry_operation_id",
    }
)
_HISTORY_MEMBERS: Final = frozenset(
    {
        "artifacts",
        "attention_causes",
        "attempt_receipts",
        "conflict_count",
        "events",
        "exact_replay_count",
        "intervention_events",
        "manager_outcomes",
        "order_id",
        "receipts",
        "schema_version",
        "telemetry_event_count",
        "value_events",
    }
)
_INTERACTION_MEMBERS: Final = frozenset(
    {
        "direction",
        "evidence_classification",
        "identifier_kind",
        "interaction_id",
        "order_id",
        "schema_version",
        "target_rep_participation",
        "timestamp",
        "timestamp_precision",
    }
)
_RUN_MEMBERS: Final = frozenset(
    {
        "completed_at",
        "event_count",
        "order_id",
        "rule_pack",
        "run_id",
        "run_type",
        "schema_version",
        "started_at",
        "status",
    }
)
_SUCCESS_RATE_MEMBERS: Final = frozenset({"defined", "denominator", "numerator"})
_METRICS_MEMBERS: Final = frozenset(
    {
        "conflict_count",
        "database_error_count",
        "exact_replay_count",
        "failed_closed_count",
        "human_review_count",
        "median_latency_ns",
        "p95_latency_ns",
        "safety_counters",
        "schema_version",
        "success_count",
        "success_rate",
        "throughput_per_second",
        "total_processed",
    }
)
_SYSTEM_STATUS_MEMBERS: Final = frozenset(
    {
        "app_version",
        "build_version",
        "database_schema_version",
        "database_status",
        "evaluated_count",
        "expected_schema_version",
        "integrity_check",
        "migration_status",
        "projection_status",
        "quick_check",
        "registry_capacity",
        "registry_count",
        "safety_counters",
        "schema_version",
    }
)
_HEALTH_MEMBERS: Final = _SYSTEM_STATUS_MEMBERS | frozenset({"status"})
_SHUTDOWN_MEMBERS: Final = frozenset({"status"})
_PROHIBITED_RESPONSE_MEMBERS = frozenset(
    {
        "canonical_bytes",
        "canonical_preimage",
        "cookie",
        "database_path",
        "debug_trace",
        "file_path",
        "filesystem_path",
        "password",
        "preimage",
        "raw_database_row",
        "raw_log",
        "raw_sql",
        "secret",
        "shutdown_token",
        "stack_trace",
        "token",
        "traceback",
    }
)


class PortalContractError(ValueError):
    """A closed client or application value violated the portal contract."""

    def __init__(self, code: str, *, status: int = 400) -> None:
        self.code = code
        self.status = status
        super().__init__(code)


@runtime_checkable
class ScenarioApplicationProtocol(Protocol):
    """Structural application boundary consumed by the HTTP adapter."""

    def list_scenarios(self) -> object: ...

    def instantiate(
        self,
        alias: str,
        request_key: str | None = None,
        mode: str = "complete",
    ) -> object: ...

    def list_orders(self) -> object: ...

    def get_order(self, order_id: str) -> object: ...

    def evaluate(self, order_id: str, request_key: str | None = None) -> object: ...

    def get_history(self, order_id: str) -> object: ...

    def get_interaction(self, interaction_id: str) -> object: ...

    def get_run(self, run_id: str) -> object: ...

    def metrics_summary(self) -> object: ...

    def system_status(self, deep: bool = False) -> object: ...


def validate_alias(value: object) -> str:
    if type(value) is not str or _ALIAS.fullmatch(value) is None:
        raise PortalContractError("SCENARIO_ALIAS_INVALID")
    return value


def validate_mode(value: object) -> str:
    if type(value) is not str or _MODE.fullmatch(value) is None:
        raise PortalContractError("SCENARIO_MODE_INVALID")
    return value


def validate_request_key(value: object) -> str | None:
    if value is None:
        return None
    if type(value) is not str or _REQUEST_KEY.fullmatch(value) is None:
        raise PortalContractError("REQUEST_KEY_INVALID")
    return value


def validate_synthetic_id(value: object, namespace: str) -> str:
    if type(value) is not str or not is_reserved_identity(
        value, expected_namespace=namespace
    ):
        raise PortalContractError(f"{namespace}_ID_INVALID")
    return value


def validate_lower_sha256(value: object, code: str) -> str:
    if type(value) is not str or _LOWER_SHA256.fullmatch(value) is None:
        raise PortalContractError(code, status=500)
    return value


def _reject_duplicate_members(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PortalContractError("JSON_DUPLICATE_MEMBER")
        result[key] = value
    return result


def _reject_float(_: str) -> object:
    raise PortalContractError("JSON_FLOAT_PROHIBITED")


def _reject_nonfinite(_: str) -> object:
    raise PortalContractError("JSON_NONFINITE_PROHIBITED")


def parse_closed_json(raw: bytes, *, expected_members: frozenset[str]) -> dict[str, object]:
    """Parse one bounded closed JSON object without duplicate or inexact numbers."""

    if type(raw) is not bytes or len(raw) > MAX_REQUEST_BODY_BYTES:
        raise PortalContractError("REQUEST_BODY_TOO_LARGE", status=413)
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise PortalContractError("JSON_UTF8_INVALID") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_members,
            parse_float=_reject_float,
            parse_constant=_reject_nonfinite,
        )
    except PortalContractError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise PortalContractError("JSON_MALFORMED") from exc
    if type(value) is not dict or frozenset(value) != expected_members:
        raise PortalContractError("JSON_MEMBERS_INVALID")
    return value


def parse_instantiate_request(raw: bytes) -> tuple[str | None, str]:
    value = parse_closed_json(
        raw,
        expected_members=frozenset({"mode", "request_key", "schema_version"}),
    )
    if value["schema_version"] != API_REQUEST_SCHEMA_VERSION:
        raise PortalContractError("REQUEST_SCHEMA_VERSION_UNSUPPORTED")
    return validate_request_key(value["request_key"]), validate_mode(value["mode"])


def parse_evaluate_request(raw: bytes) -> str | None:
    value = parse_closed_json(
        raw,
        expected_members=frozenset({"request_key", "schema_version"}),
    )
    if value["schema_version"] != API_REQUEST_SCHEMA_VERSION:
        raise PortalContractError("REQUEST_SCHEMA_VERSION_UNSUPPORTED")
    return validate_request_key(value["request_key"])


def parse_shutdown_request(raw: bytes) -> None:
    value = parse_closed_json(
        raw,
        expected_members=frozenset({"schema_version"}),
    )
    if value["schema_version"] != API_REQUEST_SCHEMA_VERSION:
        raise PortalContractError("REQUEST_SCHEMA_VERSION_UNSUPPORTED")


def _required_request_key(value: object) -> str:
    request_key = validate_request_key(value)
    if request_key is None:
        raise PortalContractError("REQUEST_KEY_REQUIRED")
    if len(request_key) > 96:
        raise PortalContractError("REQUEST_KEY_INVALID")
    return request_key


def _confirmed(value: object) -> None:
    if value is not True:
        raise PortalContractError("ACTION_CONFIRMATION_REQUIRED")


def _action_version(
    value: Mapping[str, object],
    *,
    action_schema_version: str,
) -> None:
    if value["schema_version"] != action_schema_version:
        raise PortalContractError("ACTION_SCHEMA_VERSION_UNSUPPORTED")
    if value["request_schema_version"] != API_REQUEST_SCHEMA_VERSION:
        raise PortalContractError("REQUEST_SCHEMA_VERSION_UNSUPPORTED")


def parse_manager_outcome_request(raw: bytes) -> dict[str, object]:
    """Parse the closed Sales Credit manager-outcome command transport."""

    value = parse_closed_json(
        raw,
        expected_members=frozenset(
            {
                "actor_id",
                "amount_minor_units",
                "confirmed",
                "currency_code",
                "decided_at",
                "outcome",
                "request_key",
                "request_schema_version",
                "schema_version",
            }
        ),
    )
    _action_version(value, action_schema_version=MANAGER_OUTCOME_REQUEST_SCHEMA_VERSION)
    _confirmed(value["confirmed"])
    actor_id = validate_synthetic_id(value["actor_id"], "REP")
    request_key = _required_request_key(value["request_key"])
    decided_at = value["decided_at"]
    try:
        CanonicalTimestamp(cast(str, decided_at))
    except (TimestampValidationError, TypeError, ValueError) as exc:
        raise PortalContractError("MANAGER_OUTCOME_TIMESTAMP_INVALID") from exc
    outcome = value["outcome"]
    if outcome not in {
        "APPROVED",
        "DENIED",
        "PARTIAL",
        "OTHER_REP",
        "NOT_PURSUED",
    }:
        raise PortalContractError("MANAGER_OUTCOME_INVALID")
    amount = value["amount_minor_units"]
    currency = value["currency_code"]
    if outcome == "PARTIAL":
        if (
            type(amount) is not int
            or amount <= 0
            or amount > JSON_SAFE_INTEGER_MAXIMUM
        ):
            raise PortalContractError("MANAGER_OUTCOME_AMOUNT_INVALID")
        if currency not in {"EUR", "JPY", "KWD", "USD"}:
            raise PortalContractError("MANAGER_OUTCOME_CURRENCY_INVALID")
    elif amount is not None or currency is not None:
        raise PortalContractError("MANAGER_OUTCOME_MONEY_PROHIBITED")
    return {
        "actor_id": actor_id,
        "amount_minor_units": amount,
        "confirmed": True,
        "currency_code": currency,
        "decided_at": decided_at,
        "outcome": outcome,
        "request_key": request_key,
    }


def parse_doi_scenario_selection_request(raw: bytes) -> dict[str, object]:
    """Parse one exact, bounded overlap-scenario selection command."""

    value = parse_closed_json(
        raw,
        expected_members=frozenset(
            {
                "actor_id",
                "confirmed",
                "evaluation_id",
                "option_opportunity_ids",
                "occurred_at",
                "request_key",
                "request_schema_version",
                "schema_version",
                "selected_opportunity_id",
            }
        ),
    )
    _action_version(
        value,
        action_schema_version=DOI_SCENARIO_SELECTION_REQUEST_SCHEMA_VERSION,
    )
    _confirmed(value["confirmed"])
    actor_id = validate_synthetic_id(value["actor_id"], "REP")
    evaluation_id = validate_synthetic_id(value["evaluation_id"], "EVALUATION")
    request_key = _required_request_key(value["request_key"])
    occurred_at = value["occurred_at"]
    try:
        CanonicalTimestamp(cast(str, occurred_at))
    except (TimestampValidationError, TypeError, ValueError) as exc:
        raise PortalContractError("DOI_SCENARIO_TIMESTAMP_INVALID") from exc
    selected = validate_synthetic_id(value["selected_opportunity_id"], "EVIDENCE")
    options_value = value["option_opportunity_ids"]
    if type(options_value) is not list or not 2 <= len(options_value) <= 32:
        raise PortalContractError("DOI_SCENARIO_OPTIONS_INVALID")
    options = tuple(
        validate_synthetic_id(item, "EVIDENCE") for item in options_value
    )
    if options != tuple(sorted(set(options))) or selected not in options:
        raise PortalContractError("DOI_SCENARIO_OPTIONS_INVALID")
    return {
        "actor_id": actor_id,
        "confirmed": True,
        "evaluation_id": evaluation_id,
        "option_opportunity_ids": options,
        "occurred_at": occurred_at,
        "request_key": request_key,
        "selected_opportunity_id": selected,
    }


def parse_database_verify_request(raw: bytes) -> dict[str, object]:
    value = parse_closed_json(
        raw,
        expected_members=frozenset({"schema_version"}),
    )
    if value["schema_version"] != DATABASE_VERIFY_REQUEST_SCHEMA_VERSION:
        raise PortalContractError("ACTION_SCHEMA_VERSION_UNSUPPORTED")
    return {}


def parse_backup_create_request(raw: bytes) -> dict[str, object]:
    value = parse_closed_json(
        raw,
        expected_members=frozenset(
            {
                "confirmed",
                "request_key",
                "request_schema_version",
                "schema_version",
            }
        ),
    )
    _action_version(value, action_schema_version=BACKUP_CREATE_REQUEST_SCHEMA_VERSION)
    _confirmed(value["confirmed"])
    return {
        "confirmed": True,
        "request_key": _required_request_key(value["request_key"]),
    }


def parse_extension_handshake_request(raw: bytes) -> str:
    value = parse_closed_json(
        raw,
        expected_members=frozenset({"extension_version", "schema_version"}),
    )
    if value["schema_version"] != EXTENSION_HANDSHAKE_SCHEMA_VERSION:
        raise PortalContractError("EXTENSION_HANDSHAKE_SCHEMA_UNSUPPORTED")
    extension_version = value["extension_version"]
    if (
        type(extension_version) is not str
        or _EXTENSION_VERSION.fullmatch(extension_version) is None
    ):
        raise PortalContractError("EXTENSION_VERSION_INVALID")
    return extension_version


def _view_value(value: object) -> object:
    serializer = getattr(value, "to_dict", None)
    if callable(serializer):
        return serializer()
    return value


def public_value(
    value: object,
    *,
    omit_members: frozenset[str] = _EMPTY_MEMBERS,
    safety_exempt_members: frozenset[str] = _EMPTY_MEMBERS,
) -> object:
    """Convert one closed application view into bounded, privacy-safe JSON data."""

    active: set[int] = set()

    def convert(item: object, depth: int) -> object:
        item = _view_value(item)
        if depth > MAX_PUBLIC_DEPTH:
            raise PortalContractError("RESPONSE_DEPTH_EXCEEDED", status=500)
        if item is None or type(item) in {bool, int}:
            return item
        if type(item) is float:
            raise PortalContractError("RESPONSE_FLOAT_PROHIBITED", status=500)
        if type(item) is str:
            if len(item) > MAX_PUBLIC_STRING or "\x00" in item:
                raise PortalContractError("RESPONSE_STRING_INVALID", status=500)
            return item
        if isinstance(item, Path) or isinstance(item, (bytes, bytearray, memoryview)):
            raise PortalContractError("RESPONSE_VALUE_PROHIBITED", status=500)
        if isinstance(item, Mapping):
            identity = id(item)
            if identity in active or len(item) > MAX_PUBLIC_COLLECTION:
                raise PortalContractError("RESPONSE_MAPPING_INVALID", status=500)
            active.add(identity)
            try:
                converted: dict[str, object] = {}
                for key, child in item.items():
                    if type(key) is not str or _SAFE_MEMBER.fullmatch(key) is None:
                        raise PortalContractError("RESPONSE_MEMBER_INVALID", status=500)
                    if key in omit_members:
                        continue
                    normalized_key = key.casefold()
                    if (
                        normalized_key in _PROHIBITED_RESPONSE_MEMBERS
                        or normalized_key.endswith("_path")
                    ):
                        raise PortalContractError("RESPONSE_MEMBER_PROHIBITED", status=500)
                    converted[key] = convert(child, depth + 1)
                return {key: converted[key] for key in sorted(converted)}
            finally:
                active.remove(identity)
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            identity = id(item)
            if identity in active or len(item) > MAX_PUBLIC_COLLECTION:
                raise PortalContractError("RESPONSE_SEQUENCE_INVALID", status=500)
            active.add(identity)
            try:
                return [convert(child, depth + 1) for child in item]
            finally:
                active.remove(identity)
        raise PortalContractError("RESPONSE_TYPE_INVALID", status=500)

    result = convert(value, 0)

    def for_safety_scan(item: object) -> object:
        if type(item) is dict:
            projected: dict[str, object] = {}
            for key, child in item.items():
                if child is None and key.endswith("_id"):
                    continue
                if key in safety_exempt_members:
                    continue
                if key == "throughput_per_second" and child is not None:
                    if (
                        type(child) is not str
                        or _CANONICAL_DECIMAL.fullmatch(child) is None
                    ):
                        raise PortalContractError(
                            "RESPONSE_THROUGHPUT_INVALID", status=500
                        )
                    projected[key] = "SYNTHETIC_NUMERIC_METRIC"
                else:
                    projected[key] = for_safety_scan(child)
            return projected
        if type(item) is list:
            return [for_safety_scan(child) for child in item]
        return item

    safety_projection = for_safety_scan(result)
    assert_payload_safe(safety_projection)
    encoded = canonical_json_bytes(result)
    if len(encoded) > MAX_RESPONSE_BODY_BYTES:
        raise PortalContractError("RESPONSE_BODY_TOO_LARGE", status=500)
    return result


def _response_error(code: str) -> NoReturn:
    raise PortalContractError(code, status=500)


def _response_synthetic_id(value: object, namespace: str, code: str) -> str:
    if type(value) is not str or not is_reserved_identity(
        value,
        expected_namespace=namespace,
    ):
        _response_error(code)
    return value


def _exact_mapping(
    value: object,
    members: frozenset[str],
    code: str,
) -> dict[str, object]:
    if type(value) is not dict or frozenset(value) != members:
        _response_error(code)
    return value


def _exact_list(value: object, code: str) -> list[object]:
    if type(value) is not list:
        _response_error(code)
    return value


def _text(value: object, code: str) -> str:
    if type(value) is not str or not value:
        _response_error(code)
    return value


def _token(value: object, code: str) -> str:
    text = _text(value, code)
    if _CANONICAL_TOKEN.fullmatch(text) is None:
        _response_error(code)
    return text


def _nonnegative_integer(value: object, code: str) -> int:
    if type(value) is not int or value < 0:
        _response_error(code)
    return value


def _optional_nonnegative_integer(value: object, code: str) -> int | None:
    if value is None:
        return None
    return _nonnegative_integer(value, code)


def _timestamp(value: object, code: str) -> str:
    if type(value) is not str:
        _response_error(code)
    try:
        timestamp = CanonicalTimestamp(value)
    except TimestampValidationError:
        _response_error(code)
    if timestamp.value != value:
        _response_error(code)
    return value


def _optional_timestamp(value: object, code: str) -> str | None:
    if value is None:
        return None
    return _timestamp(value, code)


def _response_id(value: object, namespace: str, code: str) -> str:
    if type(value) is not str or not is_reserved_identity(
        value, expected_namespace=namespace
    ):
        _response_error(code)
    return value


def _optional_response_id(value: object, namespace: str, code: str) -> str | None:
    if value is None:
        return None
    return _response_id(value, namespace, code)


def _generic_response_id(value: object, code: str) -> str:
    if type(value) is not str or not is_reserved_identity(value):
        _response_error(code)
    return value


def _optional_generic_response_id(value: object, code: str) -> str | None:
    if value is None:
        return None
    return _generic_response_id(value, code)


def _string_list(value: object, code: str) -> list[str]:
    items = _exact_list(value, code)
    if any(type(item) is not str or not item for item in items):
        _response_error(code)
    return cast(list[str], items)


def _rule_pack(value: object, code: str) -> str:
    if type(value) is not str or value not in {"DOI", "SALES_CREDIT"}:
        _response_error(code)
    return value


def _application_schema(value: object, code: str) -> None:
    if value != APPLICATION_SCHEMA_VERSION:
        _response_error(code)


def _money_mapping(value: object, code: str) -> dict[str, object]:
    money = _exact_mapping(value, _MONEY_MEMBERS, code)
    try:
        parsed = Money.from_json_value(money)
    except MoneyViolation:
        _response_error(code)
    if parsed.to_json_value() != money:
        _response_error(code)
    return money


def _optional_money(value: object, code: str) -> dict[str, object] | None:
    if value is None:
        return None
    return _money_mapping(value, code)


def validate_fact_mapping(value: object, *, field: str) -> dict[str, object]:
    """Validate one exact field-specific factual view for API or DOM use."""

    fact = _exact_mapping(value, _FACT_MEMBERS, "RESPONSE_FACT_MEMBERS_INVALID")
    if fact["tag"] == "MALFORMED":
        if fact["reason_code"] is not None or fact["value"] is not None:
            _response_error("RESPONSE_MALFORMED_FACT_INVALID")
        return fact
    try:
        accepted = validate_line_fact(field, fact)
    except (TypeError, ValueError):
        _response_error("RESPONSE_LINE_FACT_POLICY_INVALID")
    if accepted != fact:
        _response_error("RESPONSE_LINE_FACT_NONCANONICAL")
    return fact


def validate_line_mapping(value: object) -> dict[str, object]:
    """Validate one exact line including governed values and identity namespaces."""

    line = _exact_mapping(value, _LINE_MEMBERS, "RESPONSE_LINE_MEMBERS_INVALID")
    _response_id(line["line_id"], "EVIDENCE", "RESPONSE_LINE_ID_INVALID")
    _response_id(line["product_id"], "SKU", "RESPONSE_PRODUCT_ID_INVALID")
    if type(line["line_index"]) is not int or line["line_index"] < 1:
        _response_error("RESPONSE_LINE_INDEX_INVALID")
    for field in (
        "activity",
        "availability",
        "drop_ship_state",
        "eta",
        "line_value",
        "quantity",
    ):
        validate_fact_mapping(line[field], field=field)
    return line


def _completeness_mapping(value: object) -> dict[str, object]:
    item = _exact_mapping(
        value,
        _COMPLETENESS_MEMBERS,
        "RESPONSE_COMPLETENESS_MEMBERS_INVALID",
    )
    if item["state"] not in {"COMPLETE", "INCOMPLETE", "MALFORMED"}:
        _response_error("RESPONSE_COMPLETENESS_STATE_INVALID")
    _response_id(
        item["requested_order_id"],
        "ORDER",
        "RESPONSE_REQUESTED_ORDER_ID_INVALID",
    )
    _optional_response_id(
        item["observed_order_id"],
        "ORDER",
        "RESPONSE_OBSERVED_ORDER_ID_INVALID",
    )
    _optional_nonnegative_integer(
        item["declared_relevant_line_count"],
        "RESPONSE_DECLARED_LINE_COUNT_INVALID",
    )
    _nonnegative_integer(
        item["rendered_relevant_line_count"],
        "RESPONSE_RENDERED_LINE_COUNT_INVALID",
    )
    digest = item["ordered_line_manifest_digest"]
    if digest is not None:
        validate_lower_sha256(digest, "RESPONSE_LINE_MANIFEST_DIGEST_INVALID")
    _text(item["fixture_version"], "RESPONSE_FIXTURE_VERSION_INVALID")
    _text(item["source_schema_version"], "RESPONSE_SOURCE_SCHEMA_INVALID")
    _optional_timestamp(
        item["source_observed_at"],
        "RESPONSE_SOURCE_TIMESTAMP_INVALID",
    )
    return item


def _scenario_mapping(value: object) -> dict[str, object]:
    item = _exact_mapping(value, _SCENARIO_MEMBERS, "RESPONSE_SCENARIO_MEMBERS_INVALID")
    _application_schema(item["schema_version"], "RESPONSE_SCENARIO_SCHEMA_INVALID")
    try:
        validate_alias(item["alias"])
    except PortalContractError:
        _response_error("RESPONSE_SCENARIO_ALIAS_INVALID")
    _rule_pack(item["rule_pack"], "RESPONSE_SCENARIO_RULE_PACK_INVALID")
    for member in (
        "collected_scenario",
        "complexity",
        "description",
        "expected_result",
    ):
        _text(item[member], "RESPONSE_SCENARIO_TEXT_INVALID")
    modes = _string_list(item["allowed_modes"], "RESPONSE_SCENARIO_MODES_INVALID")
    if not modes or len(modes) != len(set(modes)):
        _response_error("RESPONSE_SCENARIO_MODES_INVALID")
    for mode in modes:
        try:
            validate_mode(mode)
        except PortalContractError:
            _response_error("RESPONSE_SCENARIO_MODE_INVALID")
    return item


def validate_scenarios_response(value: object) -> list[object]:
    items = _exact_list(public_value(value), "RESPONSE_SCENARIOS_INVALID")
    aliases: set[str] = set()
    for item in items:
        scenario = _scenario_mapping(item)
        alias = scenario["alias"]
        assert type(alias) is str
        if alias in aliases:
            _response_error("RESPONSE_SCENARIO_ALIAS_DUPLICATE")
        aliases.add(alias)
    return items


def _order_summary_mapping(value: object) -> dict[str, object]:
    item = _exact_mapping(
        value,
        _ORDER_SUMMARY_MEMBERS,
        "RESPONSE_ORDER_SUMMARY_MEMBERS_INVALID",
    )
    _application_schema(item["schema_version"], "RESPONSE_ORDER_SCHEMA_INVALID")
    _response_id(item["order_id"], "ORDER", "RESPONSE_ORDER_ID_INVALID")
    try:
        validate_alias(item["scenario_alias"])
        validate_mode(item["mode"])
    except PortalContractError:
        _response_error("RESPONSE_ORDER_DESCRIPTOR_INVALID")
    _rule_pack(item["rule_pack"], "RESPONSE_ORDER_RULE_PACK_INVALID")
    _token(item["order_status"], "RESPONSE_ORDER_STATUS_INVALID")
    _nonnegative_integer(
        item["relevant_line_count"],
        "RESPONSE_RELEVANT_LINE_COUNT_INVALID",
    )
    for member in ("doi_state", "sales_credit_state"):
        state = item[member]
        if state is not None:
            _token(state, "RESPONSE_ORDER_STATE_INVALID")
    if type(item["human_review_required"]) is not bool:
        _response_error("RESPONSE_ORDER_REVIEW_INVALID")
    if type(item["evaluated"]) is not bool:
        _response_error("RESPONSE_ORDER_EVALUATED_INVALID")
    _timestamp(item["updated_at"], "RESPONSE_ORDER_UPDATED_AT_INVALID")
    return item


def validate_order_summaries_response(value: object) -> list[object]:
    items = _exact_list(public_value(value), "RESPONSE_ORDERS_INVALID")
    seen: set[str] = set()
    for raw in items:
        item = _order_summary_mapping(raw)
        order_id = item["order_id"]
        assert type(order_id) is str
        if order_id in seen:
            _response_error("RESPONSE_ORDER_DUPLICATE")
        seen.add(order_id)
    return items


def _opportunity_mapping(
    value: object,
    *,
    allowed_line_ids: Collection[str] | None = None,
) -> dict[str, object]:
    item = _exact_mapping(
        value,
        _OPPORTUNITY_MEMBERS,
        "RESPONSE_OPPORTUNITY_MEMBERS_INVALID",
    )
    _token(item["opportunity_type"], "RESPONSE_OPPORTUNITY_TYPE_INVALID")
    line_ids = _exact_list(
        item["line_ids"],
        "RESPONSE_OPPORTUNITY_LINE_IDS_INVALID",
    )
    seen: set[str] = set()
    for line_id in line_ids:
        accepted = _response_id(
            line_id,
            "EVIDENCE",
            "RESPONSE_OPPORTUNITY_LINE_ID_INVALID",
        )
        if accepted in seen:
            _response_error("RESPONSE_OPPORTUNITY_LINE_ID_DUPLICATE")
        seen.add(accepted)
    if allowed_line_ids is not None and not seen.issubset(allowed_line_ids):
        _response_error("RESPONSE_OPPORTUNITY_LINE_SCOPE_INVALID")
    _optional_money(
        item["potential_value"],
        "RESPONSE_OPPORTUNITY_VALUE_INVALID",
    )
    return item


def _explanation_mapping(value: object) -> dict[str, object]:
    item = _exact_mapping(
        value,
        _EXPLANATION_MEMBERS,
        "RESPONSE_EXPLANATION_MEMBERS_INVALID",
    )
    for member in (
        "normalized_facts",
        "reason_ownership",
        "rules_evaluated",
        "supplied_facts",
        "unavailable_facts",
    ):
        _string_list(item[member], "RESPONSE_EXPLANATION_LIST_INVALID")
    _text(
        item["precedence_decision"],
        "RESPONSE_EXPLANATION_PRECEDENCE_INVALID",
    )
    return item


def _processing_stage_mapping(value: object) -> dict[str, object]:
    item = _exact_mapping(
        value,
        _PROCESSING_STAGE_MEMBERS,
        "RESPONSE_PROCESSING_STAGE_MEMBERS_INVALID",
    )
    _token(item["stage"], "RESPONSE_PROCESSING_STAGE_NAME_INVALID")
    _token(item["status"], "RESPONSE_PROCESSING_STAGE_STATUS_INVALID")
    _nonnegative_integer(
        item["duration_ns"],
        "RESPONSE_PROCESSING_STAGE_DURATION_INVALID",
    )
    return item


def _evaluation_mapping(
    value: object,
    *,
    expected_order_id: str | None = None,
    expected_scenario_alias: str | None = None,
    expected_rule_pack: str | None = None,
    allowed_line_ids: Collection[str] | None = None,
) -> dict[str, object]:
    item = _exact_mapping(
        value,
        _EVALUATION_MEMBERS,
        "RESPONSE_EVALUATION_MEMBERS_INVALID",
    )
    _application_schema(item["schema_version"], "RESPONSE_EVALUATION_SCHEMA_INVALID")
    _response_id(item["order_id"], "ORDER", "RESPONSE_EVALUATION_ORDER_ID_INVALID")
    try:
        validate_alias(item["scenario_alias"])
    except PortalContractError:
        _response_error("RESPONSE_EVALUATION_ALIAS_INVALID")
    rule_pack = _rule_pack(
        item["rule_pack"],
        "RESPONSE_EVALUATION_RULE_PACK_INVALID",
    )
    if (
        expected_order_id is not None
        and item["order_id"] != expected_order_id
    ):
        _response_error("RESPONSE_EVALUATION_ROUTE_BINDING_INVALID")
    if (
        expected_scenario_alias is not None
        and item["scenario_alias"] != expected_scenario_alias
    ):
        _response_error("RESPONSE_EVALUATION_ORDER_BINDING_INVALID")
    if expected_rule_pack is not None and rule_pack != expected_rule_pack:
        _response_error("RESPONSE_EVALUATION_ORDER_BINDING_INVALID")
    for member in (
        "aggregate_potential_status",
        "top_level_result",
        "value_status",
        "workflow_state",
    ):
        _token(item[member], "RESPONSE_EVALUATION_STATE_INVALID")
    closure = item["closure_state"]
    if closure is not None:
        _token(closure, "RESPONSE_EVALUATION_CLOSURE_INVALID")
    for member in ("reasons", "fired_rules", "handling_flags"):
        _string_list(item[member], "RESPONSE_EVALUATION_LIST_INVALID")
    opportunities = _exact_list(
        item["opportunities"],
        "RESPONSE_EVALUATION_OPPORTUNITIES_INVALID",
    )
    for opportunity in opportunities:
        _opportunity_mapping(
            opportunity,
            allowed_line_ids=allowed_line_ids,
        )
    _optional_money(
        item["aggregate_potential_value"],
        "RESPONSE_AGGREGATE_VALUE_INVALID",
    )
    _optional_money(item["value"], "RESPONSE_EVALUATION_VALUE_INVALID")
    if type(item["human_review_required"]) is not bool:
        _response_error("RESPONSE_EVALUATION_REVIEW_INVALID")
    if type(item["replayed"]) is not bool or type(item["conflict"]) is not bool:
        _response_error("RESPONSE_EVALUATION_REPLAY_INVALID")
    _optional_response_id(
        item["command_id"],
        "EVIDENCE",
        "RESPONSE_EVALUATION_COMMAND_ID_INVALID",
    )
    case_id = item["case_id"]
    if rule_pack == "SALES_CREDIT":
        accepted_case_id = _response_id(
            case_id,
            "ORDER",
            "RESPONSE_EVALUATION_CASE_ID_INVALID",
        )
        if accepted_case_id != item["order_id"]:
            _response_error("RESPONSE_EVALUATION_CASE_BINDING_INVALID")
    else:
        _optional_response_id(
            case_id,
            "EVIDENCE",
            "RESPONSE_EVALUATION_CASE_ID_INVALID",
        )
    _optional_response_id(
        item["run_id"],
        "RUN",
        "RESPONSE_EVALUATION_RUN_ID_INVALID",
    )
    _optional_response_id(
        item["snapshot_id"],
        "SNAPSHOT",
        "RESPONSE_EVALUATION_SNAPSHOT_ID_INVALID",
    )
    _optional_response_id(
        item["evaluation_id"],
        "EVALUATION",
        "RESPONSE_EVALUATION_ID_INVALID",
    )
    _text(item["rule_pack_version"], "RESPONSE_RULE_PACK_VERSION_INVALID")
    _nonnegative_integer(
        item["processing_duration_ns"],
        "RESPONSE_PROCESSING_DURATION_INVALID",
    )
    _explanation_mapping(item["explanation"])
    stages = _exact_list(
        item["processing_stages"],
        "RESPONSE_PROCESSING_STAGES_INVALID",
    )
    for stage in stages:
        _processing_stage_mapping(stage)
    return item


def validate_evaluation_response(
    value: object,
    *,
    expected_order_id: str | None = None,
    expected_scenario_alias: str | None = None,
    expected_rule_pack: str | None = None,
    allowed_line_ids: Collection[str] | None = None,
) -> dict[str, object]:
    return _evaluation_mapping(
        public_value(value),
        expected_order_id=expected_order_id,
        expected_scenario_alias=expected_scenario_alias,
        expected_rule_pack=expected_rule_pack,
        allowed_line_ids=allowed_line_ids,
    )


def validate_order_detail_response(
    value: object,
    *,
    expected_order_id: str | None = None,
    expected_scenario_alias: str | None = None,
    expected_mode: str | None = None,
) -> dict[str, object]:
    item = _exact_mapping(
        public_value(value),
        _ORDER_DETAIL_MEMBERS,
        "RESPONSE_ORDER_DETAIL_MEMBERS_INVALID",
    )
    summary = {member: item[member] for member in _ORDER_SUMMARY_MEMBERS}
    _order_summary_mapping(summary)
    if expected_order_id is not None and item["order_id"] != expected_order_id:
        _response_error("RESPONSE_ORDER_ROUTE_BINDING_INVALID")
    if (
        expected_scenario_alias is not None
        and item["scenario_alias"] != expected_scenario_alias
    ):
        _response_error("RESPONSE_SCENARIO_ROUTE_BINDING_INVALID")
    if expected_mode is not None and item["mode"] != expected_mode:
        _response_error("RESPONSE_SCENARIO_MODE_BINDING_INVALID")
    _timestamp(item["created_at"], "RESPONSE_ORDER_CREATED_AT_INVALID")
    if item["source_status"] not in {"COMPLETE", "INCOMPLETE", "MALFORMED"}:
        _response_error("RESPONSE_ORDER_SOURCE_STATUS_INVALID")
    lines = _exact_list(item["lines"], "RESPONSE_ORDER_LINES_INVALID")
    accepted_lines: list[dict[str, object]] = []
    seen_line_ids: set[str] = set()
    duplicate_line_id = False
    line_order_invalid = False
    for expected_index, raw in enumerate(lines, start=1):
        line = validate_line_mapping(raw)
        if line["line_index"] != expected_index:
            line_order_invalid = True
        line_id = line["line_id"]
        assert type(line_id) is str
        if line_id in seen_line_ids:
            duplicate_line_id = True
        seen_line_ids.add(line_id)
        accepted_lines.append(line)
    interactions = _exact_list(
        item["interaction_ids"],
        "RESPONSE_ORDER_INTERACTIONS_INVALID",
    )
    seen_interactions: set[str] = set()
    for interaction_id in interactions:
        accepted_interaction = _response_id(
            interaction_id,
            "INTERACTION",
            "RESPONSE_ORDER_INTERACTION_ID_INVALID",
        )
        if accepted_interaction in seen_interactions:
            _response_error("RESPONSE_ORDER_INTERACTION_DUPLICATE")
        seen_interactions.add(accepted_interaction)
    completeness = _completeness_mapping(item["completeness"])
    order_id = item["order_id"]
    if (
        completeness["state"] != item["source_status"]
        or completeness["requested_order_id"] != order_id
    ):
        _response_error("RESPONSE_ORDER_COMPLETENESS_BINDING_INVALID")
    if (
        item["mode"] in FAIL_CLOSED_RENDER_MODES
        and item["source_status"] != "INCOMPLETE"
    ):
        _response_error("RESPONSE_RENDER_MODE_COMPLETENESS_INVALID")
    malformed_present = any(
        fact["tag"] == "MALFORMED"
        for line in accepted_lines
        for fact in (
            line["activity"],
            line["availability"],
            line["drop_ship_state"],
            line["eta"],
            line["line_value"],
            line["quantity"],
        )
        if type(fact) is dict
    )
    if malformed_present and item["source_status"] != "MALFORMED":
        _response_error("RESPONSE_MALFORMED_FACT_CONTEXT_INVALID")
    digest = completeness["ordered_line_manifest_digest"]
    if completeness["state"] == "COMPLETE" and not malformed_present:
        try:
            expected_digest = ordered_line_manifest_digest_from_mappings(
                accepted_lines
            )
        except (TypeError, ValueError):
            _response_error("RESPONSE_ORDER_MANIFEST_INPUT_INVALID")
        if digest != expected_digest:
            _response_error("RESPONSE_ORDER_MANIFEST_INVALID")
    if completeness["state"] == "COMPLETE":
        if (
            duplicate_line_id
            or line_order_invalid
            or completeness["rendered_relevant_line_count"] != len(accepted_lines)
            or item["relevant_line_count"] != len(accepted_lines)
            or completeness["declared_relevant_line_count"] != len(accepted_lines)
            or completeness["observed_order_id"] != order_id
            or completeness["source_observed_at"] is None
            or digest is None
        ):
            _response_error("RESPONSE_COMPLETE_ORDER_INVALID")
    evaluation = item["latest_evaluation"]
    if evaluation is None:
        if item["evaluated"] is not False:
            _response_error("RESPONSE_ORDER_EVALUATION_BINDING_INVALID")
    else:
        accepted_evaluation = _evaluation_mapping(
            evaluation,
            expected_order_id=cast(str, order_id),
            expected_scenario_alias=cast(str, item["scenario_alias"]),
            expected_rule_pack=cast(str, item["rule_pack"]),
            allowed_line_ids=seen_line_ids,
        )
        if (
            item["evaluated"] is not True
            or accepted_evaluation["order_id"] != order_id
            or accepted_evaluation["scenario_alias"] != item["scenario_alias"]
            or accepted_evaluation["rule_pack"] != item["rule_pack"]
        ):
            _response_error("RESPONSE_ORDER_EVALUATION_BINDING_INVALID")
        evaluation_opportunities = accepted_evaluation["opportunities"]
        assert type(evaluation_opportunities) is list
        for opportunity in evaluation_opportunities:
            assert type(opportunity) is dict
            opportunity_line_ids = opportunity["line_ids"]
            assert type(opportunity_line_ids) is list
            if any(
                line_id not in seen_line_ids
                for line_id in opportunity_line_ids
            ):
                _response_error("RESPONSE_OPPORTUNITY_LINE_SCOPE_INVALID")
    return item


def _history_event_mapping(value: object) -> dict[str, object]:
    item = _exact_mapping(
        value,
        _HISTORY_EVENT_MEMBERS,
        "RESPONSE_HISTORY_EVENT_MEMBERS_INVALID",
    )
    _nonnegative_integer(item["sequence"], "RESPONSE_HISTORY_SEQUENCE_INVALID")
    _optional_response_id(
        item["event_id"],
        "EVIDENCE",
        "RESPONSE_HISTORY_EVENT_ID_INVALID",
    )
    _token(item["event_kind"], "RESPONSE_HISTORY_EVENT_KIND_INVALID")
    _token(item["state"], "RESPONSE_HISTORY_EVENT_STATE_INVALID")
    _timestamp(item["occurred_at"], "RESPONSE_HISTORY_EVENT_TIME_INVALID")
    _optional_response_id(
        item["evaluation_id"],
        "EVALUATION",
        "RESPONSE_HISTORY_EVALUATION_ID_INVALID",
    )
    return item


def _history_artifact_mapping(value: object) -> dict[str, object]:
    item = _exact_mapping(
        value,
        _HISTORY_ARTIFACT_MEMBERS,
        "RESPONSE_HISTORY_ARTIFACT_MEMBERS_INVALID",
    )
    _token(item["artifact_type"], "RESPONSE_HISTORY_ARTIFACT_TYPE_INVALID")
    artifact_id = _optional_generic_response_id(
        item["artifact_id"],
        "RESPONSE_HISTORY_ARTIFACT_ID_INVALID",
    )
    if artifact_id is not None and not artifact_id.startswith(
        ("SYN-EVALUATION-", "SYN-EVIDENCE-", "SYN-SNAPSHOT-")
    ):
        _response_error("RESPONSE_HISTORY_ARTIFACT_ID_INVALID")
    _token(item["state"], "RESPONSE_HISTORY_ARTIFACT_STATE_INVALID")
    _timestamp(item["occurred_at"], "RESPONSE_HISTORY_ARTIFACT_TIME_INVALID")
    _string_list(
        item["reasons"],
        "RESPONSE_HISTORY_ARTIFACT_REASONS_INVALID",
    )
    transition_id = item["transition_id"]
    if transition_id is not None and (
        type(transition_id) is not str
        or _TRANSITION_ID.fullmatch(transition_id) is None
    ):
        _response_error("RESPONSE_HISTORY_TRANSITION_ID_INVALID")
    _optional_money(item["value"], "RESPONSE_HISTORY_VALUE_INVALID")
    return item


def _receipt_mapping(value: object) -> dict[str, object]:
    item = _exact_mapping(
        value,
        _RECEIPT_MEMBERS,
        "RESPONSE_HISTORY_RECEIPT_MEMBERS_INVALID",
    )
    _response_id(
        item["command_id"],
        "EVIDENCE",
        "RESPONSE_HISTORY_COMMAND_ID_INVALID",
    )
    _timestamp(item["recorded_at"], "RESPONSE_HISTORY_RECEIPT_TIME_INVALID")
    if type(item["replayed"]) is not bool:
        _response_error("RESPONSE_HISTORY_RECEIPT_REPLAY_INVALID")
    return item


def _attempt_receipt_mapping(value: object) -> dict[str, object]:
    item = _exact_mapping(
        value,
        _ATTEMPT_RECEIPT_MEMBERS,
        "RESPONSE_ATTEMPT_RECEIPT_MEMBERS_INVALID",
    )
    _response_id(
        item["attempt_id"],
        "EVIDENCE",
        "RESPONSE_ATTEMPT_ID_INVALID",
    )
    _optional_response_id(
        item["command_id"],
        "EVIDENCE",
        "RESPONSE_ATTEMPT_COMMAND_ID_INVALID",
    )
    _token(item["outcome"], "RESPONSE_ATTEMPT_OUTCOME_INVALID")
    error_code = item["error_code"]
    if error_code is not None:
        _token(error_code, "RESPONSE_ATTEMPT_ERROR_CODE_INVALID")
    if type(item["replayed"]) is not bool or type(item["conflict"]) is not bool:
        _response_error("RESPONSE_ATTEMPT_FLAGS_INVALID")
    _response_id(
        item["telemetry_operation_id"],
        "EVIDENCE",
        "RESPONSE_ATTEMPT_OPERATION_ID_INVALID",
    )
    _timestamp(item["recorded_at"], "RESPONSE_ATTEMPT_TIME_INVALID")
    return item


def validate_history_response(
    value: object,
    *,
    expected_order_id: str | None = None,
) -> dict[str, object]:
    item = _exact_mapping(
        public_value(value),
        _HISTORY_MEMBERS,
        "RESPONSE_HISTORY_MEMBERS_INVALID",
    )
    _application_schema(item["schema_version"], "RESPONSE_HISTORY_SCHEMA_INVALID")
    _response_id(item["order_id"], "ORDER", "RESPONSE_HISTORY_ORDER_ID_INVALID")
    if expected_order_id is not None and item["order_id"] != expected_order_id:
        _response_error("RESPONSE_HISTORY_ROUTE_BINDING_INVALID")
    for member in (
        "conflict_count",
        "exact_replay_count",
        "telemetry_event_count",
    ):
        _nonnegative_integer(item[member], "RESPONSE_HISTORY_COUNT_INVALID")
    events = _exact_list(item["events"], "RESPONSE_HISTORY_EVENTS_INVALID")
    expected_sequence = 1
    event_ids: set[str] = set()
    for event in events:
        accepted = _history_event_mapping(event)
        if accepted["sequence"] != expected_sequence:
            _response_error("RESPONSE_HISTORY_SEQUENCE_INVALID")
        event_id = accepted["event_id"]
        if event_id is not None:
            assert type(event_id) is str
            if event_id in event_ids:
                _response_error("RESPONSE_HISTORY_EVENT_ID_DUPLICATE")
            event_ids.add(event_id)
        expected_sequence += 1
    for member in (
        "artifacts",
        "attention_causes",
        "intervention_events",
        "manager_outcomes",
        "value_events",
    ):
        artifacts = _exact_list(
            item[member],
            "RESPONSE_HISTORY_ARTIFACTS_INVALID",
        )
        for artifact in artifacts:
            _history_artifact_mapping(artifact)
    receipts = _exact_list(item["receipts"], "RESPONSE_HISTORY_RECEIPTS_INVALID")
    for receipt in receipts:
        _receipt_mapping(receipt)
    attempts = _exact_list(
        item["attempt_receipts"],
        "RESPONSE_ATTEMPT_RECEIPTS_INVALID",
    )
    attempt_ids: set[str] = set()
    operation_ids: set[str] = set()
    for attempt in attempts:
        accepted = _attempt_receipt_mapping(attempt)
        attempt_id = cast(str, accepted["attempt_id"])
        operation_id = cast(str, accepted["telemetry_operation_id"])
        if attempt_id in attempt_ids or operation_id in operation_ids:
            _response_error("RESPONSE_ATTEMPT_ID_DUPLICATE")
        attempt_ids.add(attempt_id)
        operation_ids.add(operation_id)
    return item


def validate_interaction_response(
    value: object,
    *,
    expected_interaction_id: str | None = None,
) -> dict[str, object]:
    item = _exact_mapping(
        public_value(value),
        _INTERACTION_MEMBERS,
        "RESPONSE_INTERACTION_MEMBERS_INVALID",
    )
    _application_schema(item["schema_version"], "RESPONSE_INTERACTION_SCHEMA_INVALID")
    _response_id(
        item["interaction_id"],
        "INTERACTION",
        "RESPONSE_INTERACTION_ID_INVALID",
    )
    if (
        expected_interaction_id is not None
        and item["interaction_id"] != expected_interaction_id
    ):
        _response_error("RESPONSE_INTERACTION_ROUTE_BINDING_INVALID")
    _response_id(item["order_id"], "ORDER", "RESPONSE_INTERACTION_ORDER_ID_INVALID")
    for member in (
        "direction",
        "evidence_classification",
        "identifier_kind",
        "target_rep_participation",
        "timestamp_precision",
    ):
        _token(item[member], "RESPONSE_INTERACTION_VALUE_INVALID")
    _timestamp(item["timestamp"], "RESPONSE_INTERACTION_TIMESTAMP_INVALID")
    return item


def validate_run_response(
    value: object,
    *,
    expected_run_id: str | None = None,
) -> dict[str, object]:
    item = _exact_mapping(
        public_value(value),
        _RUN_MEMBERS,
        "RESPONSE_RUN_MEMBERS_INVALID",
    )
    _application_schema(item["schema_version"], "RESPONSE_RUN_SCHEMA_INVALID")
    _response_id(item["run_id"], "RUN", "RESPONSE_RUN_ID_INVALID")
    if expected_run_id is not None and item["run_id"] != expected_run_id:
        _response_error("RESPONSE_RUN_ROUTE_BINDING_INVALID")
    _response_id(item["order_id"], "ORDER", "RESPONSE_RUN_ORDER_ID_INVALID")
    _rule_pack(item["rule_pack"], "RESPONSE_RUN_RULE_PACK_INVALID")
    _token(item["run_type"], "RESPONSE_RUN_TYPE_INVALID")
    _token(item["status"], "RESPONSE_RUN_STATUS_INVALID")
    _timestamp(item["started_at"], "RESPONSE_RUN_STARTED_AT_INVALID")
    _optional_timestamp(item["completed_at"], "RESPONSE_RUN_COMPLETED_AT_INVALID")
    _nonnegative_integer(item["event_count"], "RESPONSE_RUN_EVENT_COUNT_INVALID")
    return item


def _safety_counters(value: object) -> dict[str, object]:
    expected = frozenset(SAFETY_COUNTER_NAMES)
    counters = _exact_mapping(
        value,
        expected,
        "RESPONSE_SAFETY_COUNTER_MEMBERS_INVALID",
    )
    for counter_value in counters.values():
        _nonnegative_integer(
            counter_value,
            "RESPONSE_SAFETY_COUNTER_VALUE_INVALID",
        )
    return counters


def validate_metrics_response(value: object) -> dict[str, object]:
    item = _exact_mapping(
        public_value(value),
        _METRICS_MEMBERS,
        "RESPONSE_METRICS_MEMBERS_INVALID",
    )
    _application_schema(item["schema_version"], "RESPONSE_METRICS_SCHEMA_INVALID")
    for member in (
        "conflict_count",
        "database_error_count",
        "exact_replay_count",
        "failed_closed_count",
        "human_review_count",
        "success_count",
        "total_processed",
    ):
        _nonnegative_integer(item[member], "RESPONSE_METRICS_COUNT_INVALID")
    for member in ("median_latency_ns", "p95_latency_ns"):
        _optional_nonnegative_integer(
            item[member],
            "RESPONSE_METRICS_LATENCY_INVALID",
        )
    throughput = item["throughput_per_second"]
    if throughput is not None and (
        type(throughput) is not str
        or _CANONICAL_DECIMAL.fullmatch(throughput) is None
    ):
        _response_error("RESPONSE_METRICS_THROUGHPUT_INVALID")
    success_rate = _exact_mapping(
        item["success_rate"],
        _SUCCESS_RATE_MEMBERS,
        "RESPONSE_SUCCESS_RATE_MEMBERS_INVALID",
    )
    numerator = _nonnegative_integer(
        success_rate["numerator"],
        "RESPONSE_SUCCESS_RATE_NUMERATOR_INVALID",
    )
    denominator = _nonnegative_integer(
        success_rate["denominator"],
        "RESPONSE_SUCCESS_RATE_DENOMINATOR_INVALID",
    )
    if (
        type(success_rate["defined"]) is not bool
        or success_rate["defined"] is not (denominator > 0)
        or numerator > denominator
    ):
        _response_error("RESPONSE_SUCCESS_RATE_INVALID")
    _safety_counters(item["safety_counters"])
    return item


def _system_status_mapping(value: object) -> dict[str, object]:
    item = _exact_mapping(
        value,
        _SYSTEM_STATUS_MEMBERS,
        "RESPONSE_SYSTEM_STATUS_MEMBERS_INVALID",
    )
    _application_schema(item["schema_version"], "RESPONSE_SYSTEM_STATUS_SCHEMA_INVALID")
    for member in (
        "app_version",
        "build_version",
        "database_status",
        "integrity_check",
        "migration_status",
        "projection_status",
        "quick_check",
    ):
        _text(item[member], "RESPONSE_SYSTEM_STATUS_TEXT_INVALID")
    for member in (
        "database_schema_version",
        "evaluated_count",
        "expected_schema_version",
        "registry_capacity",
        "registry_count",
    ):
        _nonnegative_integer(item[member], "RESPONSE_SYSTEM_STATUS_COUNT_INVALID")
    registry_count = cast(int, item["registry_count"])
    registry_capacity = cast(int, item["registry_capacity"])
    if registry_count > registry_capacity:
        _response_error("RESPONSE_SYSTEM_STATUS_REGISTRY_INVALID")
    _safety_counters(item["safety_counters"])
    return item


def validate_system_status_response(value: object) -> dict[str, object]:
    return _system_status_mapping(public_value(value))


def validate_health_response(value: object) -> dict[str, object]:
    item = _exact_mapping(
        public_value(value),
        _HEALTH_MEMBERS,
        "RESPONSE_HEALTH_MEMBERS_INVALID",
    )
    status = item["status"]
    if status not in {"PASS", "FAIL"}:
        _response_error("RESPONSE_HEALTH_STATUS_INVALID")
    system_status = {member: item[member] for member in _SYSTEM_STATUS_MEMBERS}
    _system_status_mapping(system_status)
    return item


def validate_shutdown_response(value: object) -> dict[str, object]:
    item = _exact_mapping(
        public_value(value),
        _SHUTDOWN_MEMBERS,
        "RESPONSE_SHUTDOWN_MEMBERS_INVALID",
    )
    if item["status"] != "SHUTDOWN_ACCEPTED":
        _response_error("RESPONSE_SHUTDOWN_STATUS_INVALID")
    return item


def validate_dashboard_response(value: object) -> object:
    """Apply the common bounded/privacy-safe boundary to an M7 closed view."""

    closed = public_value(
        value,
        safety_exempt_members=_DASHBOARD_GOVERNED_TEXT_MEMBERS,
    )

    def reject_private_paths(item: object, *, member: str | None = None) -> None:
        if type(item) is str:
            if member == "service_origin" and _DASHBOARD_LOOPBACK_ORIGIN.fullmatch(item):
                port = int(item.rsplit(":", 1)[1][:-1])
                if 1 <= port <= 65_535:
                    return
            if member == "dashboard_routes" and _DASHBOARD_LOCAL_ROUTE.fullmatch(item):
                return
            if _DASHBOARD_PRIVATE_PATH.search(item):
                raise PortalContractError(
                    "DASHBOARD_PRIVATE_PATH_PROHIBITED",
                    status=500,
                )
        if type(item) is dict:
            for key, child in item.items():
                reject_private_paths(child, member=key)
        elif type(item) is list:
            for child in item:
                reject_private_paths(child, member=member)

    reject_private_paths(closed)
    return closed


def validate_human_action_response(
    value: object,
    *,
    expected_subject_id: str,
    expected_subject_namespace: str,
    evaluation_required: bool,
) -> dict[str, object]:
    """Validate one route-bound human-action receipt without business inference."""

    if type(evaluation_required) is not bool:
        _response_error("RESPONSE_HUMAN_ACTION_CONTEXT_INVALID")
    accepted_subject = _response_synthetic_id(
        expected_subject_id,
        expected_subject_namespace,
        "RESPONSE_HUMAN_ACTION_CONTEXT_INVALID",
    )
    item = _exact_mapping(
        validate_dashboard_response(value),
        frozenset(
            {
                "command_id",
                "evaluation_id",
                "recorded_at",
                "replayed",
                "schema_version",
                "status",
                "subject_id",
            }
        ),
        "RESPONSE_HUMAN_ACTION_MEMBERS_INVALID",
    )
    if item["schema_version"] != HUMAN_ACTION_RESULT_SCHEMA_VERSION:
        _response_error("RESPONSE_HUMAN_ACTION_VERSION_INVALID")
    _response_synthetic_id(
        item["command_id"],
        "EVIDENCE",
        "RESPONSE_HUMAN_ACTION_COMMAND_INVALID",
    )
    subject = _response_synthetic_id(
        item["subject_id"],
        expected_subject_namespace,
        "RESPONSE_HUMAN_ACTION_SUBJECT_INVALID",
    )
    if subject != accepted_subject:
        _response_error("RESPONSE_HUMAN_ACTION_SUBJECT_INVALID")
    evaluation = item["evaluation_id"]
    if evaluation_required:
        _response_synthetic_id(
            evaluation,
            "EVALUATION",
            "RESPONSE_HUMAN_ACTION_EVALUATION_INVALID",
        )
    elif evaluation is not None:
        _response_error("RESPONSE_HUMAN_ACTION_EVALUATION_INVALID")
    _timestamp(item["recorded_at"], "RESPONSE_HUMAN_ACTION_TIMESTAMP_INVALID")
    replayed = item["replayed"]
    status = item["status"]
    if type(replayed) is not bool or status not in {"EXACT_REPLAY", "RECORDED"}:
        _response_error("RESPONSE_HUMAN_ACTION_STATUS_INVALID")
    if (status == "EXACT_REPLAY") != replayed:
        _response_error("RESPONSE_HUMAN_ACTION_STATUS_INVALID")
    return item


def validate_backup_action_response(value: object) -> dict[str, object]:
    """Validate the closed privacy-safe result of one local backup action."""

    item = _exact_mapping(
        validate_dashboard_response(value),
        frozenset(
            {
                "backup_id",
                "backup_sha256",
                "completed_at",
                "location_class",
                "replayed",
                "schema_version",
                "status",
                "verified_schema_version",
            }
        ),
        "RESPONSE_BACKUP_ACTION_MEMBERS_INVALID",
    )
    if item["schema_version"] != BACKUP_ACTION_RESULT_SCHEMA_VERSION:
        _response_error("RESPONSE_BACKUP_ACTION_VERSION_INVALID")
    _response_synthetic_id(
        item["backup_id"],
        "EVIDENCE",
        "RESPONSE_BACKUP_ACTION_ID_INVALID",
    )
    sha256 = item["backup_sha256"]
    if type(sha256) is not str or _LOWER_SHA256.fullmatch(sha256) is None:
        _response_error("RESPONSE_BACKUP_ACTION_HASH_INVALID")
    _timestamp(item["completed_at"], "RESPONSE_BACKUP_ACTION_TIMESTAMP_INVALID")
    replayed = item["replayed"]
    status = item["status"]
    if (
        item["location_class"] != "OWNED_LOCAL_BACKUP_DIRECTORY"
        or item["verified_schema_version"] != 4
        or type(replayed) is not bool
        or status not in {"EXACT_REPLAY", "RECORDED"}
        or (status == "EXACT_REPLAY") != replayed
    ):
        _response_error("RESPONSE_BACKUP_ACTION_STATUS_INVALID")
    return item


def validate_dashboard_evidence_response(
    value: object,
    *,
    expected_routes: Collection[str],
) -> dict[str, object]:
    item = _exact_mapping(
        validate_dashboard_response(value),
        frozenset(
            {
                "dashboard_routes",
                "manager_demo_steps",
                "schema_version",
                "selector_prefix",
            }
        ),
        "RESPONSE_DASHBOARD_EVIDENCE_MEMBERS_INVALID",
    )
    routes = _exact_list(
        item["dashboard_routes"],
        "RESPONSE_DASHBOARD_EVIDENCE_ROUTES_INVALID",
    )
    expected = sorted(expected_routes)
    routes_are_local = all(
        type(route) is str and _DASHBOARD_LOCAL_ROUTE.fullmatch(route) is not None
        for route in routes
    )
    if (
        routes != expected
        or not routes_are_local
        or item["manager_demo_steps"] != 12
        or item["schema_version"] != M8_EVIDENCE_SURFACES_SCHEMA_VERSION
        or item["selector_prefix"] != "data-ssa-dashboard-"
    ):
        _response_error("RESPONSE_DASHBOARD_EVIDENCE_INVALID")
    return item


def validate_extension_handshake_response(value: object) -> dict[str, object]:
    item = _exact_mapping(
        public_value(value),
        frozenset(
            {
                "expected_extension_version",
                "last_seen_at",
                "observed_extension_version",
                "stale_after_seconds",
                "status",
            }
        ),
        "RESPONSE_EXTENSION_HANDSHAKE_MEMBERS_INVALID",
    )
    expected = item["expected_extension_version"]
    observed = item["observed_extension_version"]
    if (
        type(expected) is not str
        or _EXTENSION_VERSION.fullmatch(expected) is None
        or type(observed) is not str
        or _EXTENSION_VERSION.fullmatch(observed) is None
        or item["status"] not in {"LAST_SEEN_HEALTHY", "VERSION_MISMATCH"}
        or type(item["stale_after_seconds"]) is not int
        or cast(int, item["stale_after_seconds"]) != 300
    ):
        _response_error("RESPONSE_EXTENSION_HANDSHAKE_INVALID")
    _timestamp(item["last_seen_at"], "RESPONSE_EXTENSION_HANDSHAKE_TIMESTAMP_INVALID")
    return item

def response_bytes(data: object) -> bytes:
    envelope = {
        "data": public_value(data),
        "schema_version": API_SCHEMA_VERSION,
    }
    encoded = canonical_json_bytes(envelope, expected_members=set(envelope))
    if len(encoded) > MAX_RESPONSE_BODY_BYTES:
        raise PortalContractError("RESPONSE_BODY_TOO_LARGE", status=500)
    return encoded


def dashboard_response_bytes(data: object) -> bytes:
    envelope = {
        "data": validate_dashboard_response(data),
        "schema_version": API_SCHEMA_VERSION,
    }
    encoded = canonical_json_bytes(envelope, expected_members=set(envelope))
    if len(encoded) > MAX_RESPONSE_BODY_BYTES:
        raise PortalContractError("RESPONSE_BODY_TOO_LARGE", status=500)
    return encoded


def route_validated_dashboard_response_bytes(data: object) -> bytes:
    """Encode data only after an exact route renderer validated shape and privacy."""

    envelope = {
        "data": data,
        "schema_version": API_SCHEMA_VERSION,
    }
    encoded = canonical_json_bytes(envelope, expected_members=set(envelope))
    if len(encoded) > MAX_RESPONSE_BODY_BYTES:
        raise PortalContractError("RESPONSE_BODY_TOO_LARGE", status=500)
    return encoded


def error_bytes(code: str) -> bytes:
    if type(code) is not str or _ERROR_CODE.fullmatch(code) is None:
        code = "INTERNAL_ERROR"
    envelope = {
        "error": {
            "code": code,
            "message": "Synthetic localhost request could not be completed.",
        },
        "schema_version": API_SCHEMA_VERSION,
    }
    return canonical_json_bytes(envelope, expected_members=set(envelope))


__all__ = [
    "APPLICATION_SCHEMA_VERSION",
    "API_REQUEST_SCHEMA_VERSION",
    "API_SCHEMA_VERSION",
    "BACKUP_CREATE_REQUEST_SCHEMA_VERSION",
    "BACKUP_ACTION_RESULT_SCHEMA_VERSION",
    "CONTROL_CENTER_SCHEMA_VERSION",
    "DATABASE_VERIFY_REQUEST_SCHEMA_VERSION",
    "DOI_SCENARIO_SELECTION_REQUEST_SCHEMA_VERSION",
    "DOM_SCHEMA_VERSION",
    "EXTENSION_HANDSHAKE_SCHEMA_VERSION",
    "FAIL_CLOSED_RENDER_MODES",
    "MANAGER_OUTCOME_REQUEST_SCHEMA_VERSION",
    "HUMAN_ACTION_RESULT_SCHEMA_VERSION",
    "M8_EVIDENCE_SURFACES_SCHEMA_VERSION",
    "MAX_REQUEST_BODY_BYTES",
    "MAX_RESPONSE_BODY_BYTES",
    "PortalContractError",
    "RUNTIME_RECEIPT_SCHEMA_VERSION",
    "ScenarioApplicationProtocol",
    "dashboard_response_bytes",
    "error_bytes",
    "parse_backup_create_request",
    "parse_closed_json",
    "parse_database_verify_request",
    "parse_doi_scenario_selection_request",
    "parse_evaluate_request",
    "parse_extension_handshake_request",
    "parse_instantiate_request",
    "parse_manager_outcome_request",
    "parse_shutdown_request",
    "public_value",
    "response_bytes",
    "route_validated_dashboard_response_bytes",
    "validate_alias",
    "validate_dashboard_response",
    "validate_backup_action_response",
    "validate_dashboard_evidence_response",
    "validate_human_action_response",
    "validate_evaluation_response",
    "validate_extension_handshake_response",
    "validate_fact_mapping",
    "validate_health_response",
    "validate_history_response",
    "validate_interaction_response",
    "validate_line_mapping",
    "validate_lower_sha256",
    "validate_metrics_response",
    "validate_mode",
    "validate_order_detail_response",
    "validate_order_summaries_response",
    "validate_request_key",
    "validate_run_response",
    "validate_scenarios_response",
    "validate_shutdown_response",
    "validate_synthetic_id",
    "validate_system_status_response",
]
