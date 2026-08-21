"""Schema-four durable catalog and outcome receipts for the local portal.

Milestone 4 deliberately provides generic canonical command/receipt tables instead of an
M5-specific table.  Writes therefore use ``SQLiteIdempotencyRepository``.  The bounded
listing projections below are unavoidable because M4 has no typed API for enumerating
generic command owners; they select only fixed columns and validate every retained byte.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

from synthetic_sales_assist.demos import DemoError, validate_request_key
from synthetic_sales_assist.domain.canonical import (
    canonical_json_bytes,
    domain_hash,
    parse_canonical_json_bytes,
)
from synthetic_sales_assist.domain.idempotency import (
    IdempotencyConflictError,
    IdempotencyDefinitionError,
    IdempotencyError,
    NaturalKey,
)
from synthetic_sales_assist.domain.identities import OrderId
from synthetic_sales_assist.domain.numeric import Money, MoneyViolation
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.persistence.database import SQLiteDatabase
from synthetic_sales_assist.persistence.idempotency import SQLiteIdempotencyRepository
from synthetic_sales_assist.persistence.records import DurableCommandResult
from synthetic_sales_assist.persistence.telemetry import (
    ProcessingResultClass,
    ProcessingTelemetry,
    RulePack,
)
from synthetic_sales_assist.safety.identity import is_reserved_identity

from .views import (
    APPLICATION_SCHEMA_VERSION,
    EvaluationResultView,
    ExplanationView,
    MoneyView,
    OpportunityView,
    ProcessingStageView,
)


INSTANCE_SCHEMA_VERSION: Final = "synthetic-sales-assist-scenario-instance/v1"
ATTEMPT_SCHEMA_VERSION: Final = "synthetic-sales-assist-scenario-attempt/v1"
EVALUATION_RESOLUTION_SCHEMA_VERSION: Final = (
    "synthetic-sales-assist-evaluation-resolution/v1"
)
_INSTANCE_NAMESPACE: Final = "application.scenario_instance"
_EVALUATION_NAMESPACE: Final = "application.scenario_evaluation"
_EVALUATION_RESOLUTION_NAMESPACE: Final = "application.scenario_evaluation_resolution"
_ATTEMPT_NAMESPACE: Final = "application.scenario_attempt"
_INSTANCE_COMMAND_DOMAIN: Final = "m5-scenario-instance-command/v1"
_INSTANCE_RESULT_DOMAIN: Final = "m5-scenario-instance-result/v1"
_EVALUATION_COMMAND_DOMAIN: Final = "m5-scenario-evaluation-command/v1"
_EVALUATION_RESULT_DOMAIN: Final = "m5-scenario-evaluation-result/v1"
_EVALUATION_RESOLUTION_COMMAND_DOMAIN: Final = (
    "m5-scenario-evaluation-resolution-command/v1"
)
_EVALUATION_RESOLUTION_RESULT_DOMAIN: Final = (
    "m5-scenario-evaluation-resolution-result/v1"
)
_ATTEMPT_COMMAND_DOMAIN: Final = "m5-scenario-attempt-command/v1"
_ATTEMPT_RESULT_DOMAIN: Final = "m5-scenario-attempt-result/v1"

_INSTANCE_MEMBERS: Final = frozenset(
    {
        "alias",
        "catalog_version",
        "created_at",
        "instance_key",
        "mode",
        "order_id",
        "rule_pack",
        "schema_version",
        "source_binding",
    }
)
_ATTEMPT_MEMBERS: Final = frozenset(
    {
        "auxiliary_event_id",
        "error_code",
        "evaluation",
        "order_id",
        "outcome",
        "schema_version",
        "telemetry_operation_id",
    }
)
_EVALUATION_BINDING_MEMBERS: Final = frozenset(
    {"order_id", "schema_version", "source_binding"}
)
_EVALUATION_RESOLUTION_MEMBERS: Final = frozenset(
    {
        "attempt_id",
        "binding_command_id",
        "order_id",
        "outcome",
        "schema_version",
        "telemetry_operation_id",
    }
)
_ATTEMPT_COMMAND_MEMBERS: Final = frozenset(
    {"attempt_id", "order_id", "schema_version"}
)
_NATURAL_KEY_MEMBERS: Final = frozenset({"components"})
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
_OPPORTUNITY_MEMBERS: Final = frozenset(
    {"line_ids", "opportunity_type", "potential_value"}
)
_STAGE_MEMBERS: Final = frozenset({"duration_ns", "stage", "status"})


class DurableRegistryError(RuntimeError):
    """A closed durable application catalog or receipt could not be trusted."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class DurableScenarioRecord:
    alias: str
    catalog_version: str
    created_at: CanonicalTimestamp
    instance_key: str
    mode: str
    order_id: str
    rule_pack: str
    source_binding: str


@dataclass(frozen=True, slots=True)
class DurableAttemptRecord:
    attempt_id: str
    order_id: str
    outcome: str
    recorded_at: CanonicalTimestamp
    telemetry_operation_id: str
    evaluation: EvaluationResultView | None
    auxiliary_event_id: str | None
    error_code: str | None

    @property
    def replayed(self) -> bool:
        return self.evaluation is not None and self.evaluation.replayed

    @property
    def conflict(self) -> bool:
        return self.outcome == "CONFLICT"


@dataclass(frozen=True, slots=True)
class DurableEvaluationBinding:
    command_id: str
    order_id: str
    request_key: str
    source_binding: str
    recorded_at: CanonicalTimestamp


@dataclass(frozen=True, slots=True)
class DurableEvaluationResolution:
    command_id: str
    binding_command_id: str
    attempt_id: str
    order_id: str
    outcome: str
    telemetry_operation_id: str
    recorded_at: CanonicalTimestamp


def _mapping(value: object, members: Collection[str], code: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or frozenset(value) != frozenset(members):
        raise DurableRegistryError(code)
    return cast(Mapping[str, object], value)


def _text(value: object, code: str, *, maximum: int = 256) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        raise DurableRegistryError(code)
    return value


def _optional_text(value: object, code: str) -> str | None:
    return None if value is None else _text(value, code)


def _texts(value: object, code: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 256:
        raise DurableRegistryError(code)
    return tuple(_text(item, code) for item in value)


def _money(value: object, code: str) -> MoneyView | None:
    if value is None:
        return None
    mapping = _mapping(value, Money.JSON_MEMBERS, code)
    try:
        accepted = Money.from_json_value(dict(mapping))
    except MoneyViolation:
        raise DurableRegistryError(code) from None
    return MoneyView(
        amount=format(accepted.amount, "f"),
        currency_code=accepted.currency_code,
        currency_registry_version=accepted.registry_version,
        currency_scale=accepted.scale,
    )


def _explanation(value: object) -> ExplanationView:
    item = _mapping(value, _EXPLANATION_MEMBERS, "DURABLE_EVALUATION_INVALID")
    return ExplanationView(
        supplied_facts=_texts(item["supplied_facts"], "DURABLE_EVALUATION_INVALID"),
        normalized_facts=_texts(
            item["normalized_facts"], "DURABLE_EVALUATION_INVALID"
        ),
        unavailable_facts=_texts(
            item["unavailable_facts"], "DURABLE_EVALUATION_INVALID"
        ),
        rules_evaluated=_texts(
            item["rules_evaluated"], "DURABLE_EVALUATION_INVALID"
        ),
        precedence_decision=_text(
            item["precedence_decision"], "DURABLE_EVALUATION_INVALID"
        ),
        reason_ownership=_texts(
            item["reason_ownership"], "DURABLE_EVALUATION_INVALID"
        ),
    )


def _opportunities(value: object) -> tuple[OpportunityView, ...]:
    if not isinstance(value, list) or len(value) > 256:
        raise DurableRegistryError("DURABLE_EVALUATION_INVALID")
    result: list[OpportunityView] = []
    for raw in value:
        item = _mapping(raw, _OPPORTUNITY_MEMBERS, "DURABLE_EVALUATION_INVALID")
        lines = _texts(item["line_ids"], "DURABLE_EVALUATION_INVALID")
        if any(not is_reserved_identity(line) for line in lines):
            raise DurableRegistryError("DURABLE_EVALUATION_INVALID")
        result.append(
            OpportunityView(
                opportunity_type=_text(
                    item["opportunity_type"], "DURABLE_EVALUATION_INVALID"
                ),
                line_ids=lines,
                potential_value=_money(
                    item["potential_value"], "DURABLE_EVALUATION_INVALID"
                ),
            )
        )
    return tuple(result)


def _stages(value: object) -> tuple[ProcessingStageView, ...]:
    if not isinstance(value, list) or len(value) > 16:
        raise DurableRegistryError("DURABLE_EVALUATION_INVALID")
    result: list[ProcessingStageView] = []
    for raw in value:
        item = _mapping(raw, _STAGE_MEMBERS, "DURABLE_EVALUATION_INVALID")
        duration = item["duration_ns"]
        if type(duration) is not int or duration < 0:
            raise DurableRegistryError("DURABLE_EVALUATION_INVALID")
        result.append(
            ProcessingStageView(
                stage=_text(item["stage"], "DURABLE_EVALUATION_INVALID"),
                duration_ns=duration,
                status=_text(item["status"], "DURABLE_EVALUATION_INVALID"),
            )
        )
    return tuple(result)


def _evaluation(value: object) -> EvaluationResultView | None:
    if value is None:
        return None
    item = _mapping(value, _EVALUATION_MEMBERS, "DURABLE_EVALUATION_INVALID")
    if item["schema_version"] != APPLICATION_SCHEMA_VERSION:
        raise DurableRegistryError("DURABLE_EVALUATION_INVALID")
    duration = item["processing_duration_ns"]
    if type(duration) is not int or duration < 0:
        raise DurableRegistryError("DURABLE_EVALUATION_INVALID")
    if type(item["replayed"]) is not bool or type(item["conflict"]) is not bool:
        raise DurableRegistryError("DURABLE_EVALUATION_INVALID")
    if type(item["human_review_required"]) is not bool:
        raise DurableRegistryError("DURABLE_EVALUATION_INVALID")
    return EvaluationResultView(
        order_id=_text(item["order_id"], "DURABLE_EVALUATION_INVALID"),
        scenario_alias=_text(
            item["scenario_alias"], "DURABLE_EVALUATION_INVALID"
        ),
        rule_pack=_text(item["rule_pack"], "DURABLE_EVALUATION_INVALID"),
        top_level_result=_text(
            item["top_level_result"], "DURABLE_EVALUATION_INVALID"
        ),
        workflow_state=_text(
            item["workflow_state"], "DURABLE_EVALUATION_INVALID"
        ),
        reasons=_texts(item["reasons"], "DURABLE_EVALUATION_INVALID"),
        fired_rules=_texts(item["fired_rules"], "DURABLE_EVALUATION_INVALID"),
        opportunities=_opportunities(item["opportunities"]),
        aggregate_potential_status=_text(
            item["aggregate_potential_status"], "DURABLE_EVALUATION_INVALID"
        ),
        aggregate_potential_value=_money(
            item["aggregate_potential_value"], "DURABLE_EVALUATION_INVALID"
        ),
        value_status=_text(item["value_status"], "DURABLE_EVALUATION_INVALID"),
        value=_money(item["value"], "DURABLE_EVALUATION_INVALID"),
        human_review_required=item["human_review_required"],
        handling_flags=_texts(
            item["handling_flags"], "DURABLE_EVALUATION_INVALID"
        ),
        closure_state=_optional_text(
            item["closure_state"], "DURABLE_EVALUATION_INVALID"
        ),
        explanation=_explanation(item["explanation"]),
        processing_stages=_stages(item["processing_stages"]),
        replayed=item["replayed"],
        conflict=item["conflict"],
        command_id=_optional_text(item["command_id"], "DURABLE_EVALUATION_INVALID"),
        case_id=_optional_text(item["case_id"], "DURABLE_EVALUATION_INVALID"),
        run_id=_optional_text(item["run_id"], "DURABLE_EVALUATION_INVALID"),
        snapshot_id=_optional_text(
            item["snapshot_id"], "DURABLE_EVALUATION_INVALID"
        ),
        evaluation_id=_optional_text(
            item["evaluation_id"], "DURABLE_EVALUATION_INVALID"
        ),
        rule_pack_version=_text(
            item["rule_pack_version"], "DURABLE_EVALUATION_INVALID"
        ),
        processing_duration_ns=duration,
    )


def _command_id(label: str, material: bytes) -> str:
    digest = hashlib.sha256(label.encode("ascii") + b"\n" + material).hexdigest()
    return f"SYN-EVIDENCE-M5-{label}-{digest.upper()[:24]}"


def _verified_payload(
    result_domain: object,
    result_sha256: object,
    result_bytes: object,
    expected_domain: str,
) -> object:
    if (
        result_domain != expected_domain
        or type(result_sha256) is not str
        or not isinstance(result_bytes, bytes)
    ):
        raise DurableRegistryError("DURABLE_RECEIPT_INVALID")
    material = bytes(result_bytes)
    if domain_hash(expected_domain, material).sha256 != result_sha256:
        raise DurableRegistryError("DURABLE_RECEIPT_INVALID")
    try:
        return parse_canonical_json_bytes(material)
    except (TypeError, ValueError):
        raise DurableRegistryError("DURABLE_RECEIPT_INVALID") from None


def _scenario_record(value: object) -> DurableScenarioRecord:
    item = _mapping(value, _INSTANCE_MEMBERS, "DURABLE_INSTANCE_INVALID")
    if item["schema_version"] != INSTANCE_SCHEMA_VERSION:
        raise DurableRegistryError("DURABLE_INSTANCE_INVALID")
    instance_key = _text(item["instance_key"], "DURABLE_INSTANCE_INVALID")
    source_binding = _text(item["source_binding"], "DURABLE_INSTANCE_INVALID")
    if (
        len(instance_key) != 24
        or any(character not in "0123456789ABCDEF" for character in instance_key)
        or len(source_binding) != 64
        or any(character not in "0123456789abcdef" for character in source_binding)
    ):
        raise DurableRegistryError("DURABLE_INSTANCE_INVALID")
    order_id = _text(item["order_id"], "DURABLE_INSTANCE_INVALID")
    try:
        OrderId(order_id)
        created_at = CanonicalTimestamp(
            _text(item["created_at"], "DURABLE_INSTANCE_INVALID")
        )
    except ValueError:
        raise DurableRegistryError("DURABLE_INSTANCE_INVALID") from None
    return DurableScenarioRecord(
        alias=_text(item["alias"], "DURABLE_INSTANCE_INVALID"),
        catalog_version=_text(
            item["catalog_version"], "DURABLE_INSTANCE_INVALID"
        ),
        created_at=created_at,
        instance_key=instance_key,
        mode=_text(item["mode"], "DURABLE_INSTANCE_INVALID"),
        order_id=order_id,
        rule_pack=_text(item["rule_pack"], "DURABLE_INSTANCE_INVALID"),
        source_binding=source_binding,
    )


def _attempt_record(row: Sequence[object]) -> DurableAttemptRecord:
    if len(row) != 11:
        raise DurableRegistryError("DURABLE_ATTEMPT_INVALID")
    (
        command_id,
        natural_key,
        command_domain,
        command_sha256,
        command_bytes,
        accepted_at,
        owner_id,
        result_domain,
        result_sha256,
        result_bytes,
        recorded_at,
    ) = row
    command_payload, _command_material = _verified_command_payload(
        command_domain,
        command_sha256,
        command_bytes,
        _ATTEMPT_COMMAND_DOMAIN,
    )
    command = _mapping(
        command_payload,
        _ATTEMPT_COMMAND_MEMBERS,
        "DURABLE_ATTEMPT_INVALID",
    )
    item = _mapping(
        _verified_payload(
            result_domain,
            result_sha256,
            result_bytes,
            _ATTEMPT_RESULT_DOMAIN,
        ),
        _ATTEMPT_MEMBERS,
        "DURABLE_ATTEMPT_INVALID",
    )
    if accepted_at != recorded_at:
        raise DurableRegistryError("DURABLE_ATTEMPT_INVALID")
    attempt = _text(command_id, "DURABLE_ATTEMPT_INVALID")
    prefix = "SYN-EVIDENCE-M5-ATTEMPT-"
    if (
        not is_reserved_identity(attempt, expected_namespace="EVIDENCE")
        or not attempt.startswith(prefix)
    ):
        raise DurableRegistryError("DURABLE_ATTEMPT_INVALID")
    attempt_nonce = attempt[len(prefix) :]
    if (
        len(attempt_nonce) != 32
        or any(character not in "0123456789ABCDEF" for character in attempt_nonce)
    ):
        raise DurableRegistryError("DURABLE_ATTEMPT_INVALID")
    try:
        key = _mapping(
            parse_canonical_json_bytes(
                _text(natural_key, "DURABLE_ATTEMPT_INVALID").encode("utf-8")
            ),
            _NATURAL_KEY_MEMBERS,
            "DURABLE_ATTEMPT_INVALID",
        )
        components = key["components"]
        if components != [attempt_nonce]:
            raise DurableRegistryError("DURABLE_ATTEMPT_INVALID")
        NaturalKey(_ATTEMPT_NAMESPACE, (attempt_nonce,))
    except (IdempotencyDefinitionError, TypeError, UnicodeEncodeError, ValueError):
        raise DurableRegistryError("DURABLE_ATTEMPT_INVALID") from None
    if (
        command["schema_version"] != ATTEMPT_SCHEMA_VERSION
        or command["attempt_id"] != attempt
    ):
        raise DurableRegistryError("DURABLE_ATTEMPT_INVALID")
    if item["schema_version"] != ATTEMPT_SCHEMA_VERSION:
        raise DurableRegistryError("DURABLE_ATTEMPT_INVALID")
    order_id = _text(item["order_id"], "DURABLE_ATTEMPT_INVALID")
    if command["order_id"] != order_id or order_id != owner_id:
        raise DurableRegistryError("DURABLE_ATTEMPT_INVALID")
    outcome = _text(item["outcome"], "DURABLE_ATTEMPT_INVALID")
    if outcome not in {"SUCCEEDED", "FAILED_CLOSED", "CONFLICT", "ERROR"}:
        raise DurableRegistryError("DURABLE_ATTEMPT_INVALID")
    evaluation = _evaluation(item["evaluation"])
    if (outcome == "SUCCEEDED") != (evaluation is not None):
        raise DurableRegistryError("DURABLE_ATTEMPT_INVALID")
    if evaluation is not None and evaluation.order_id != order_id:
        raise DurableRegistryError("DURABLE_ATTEMPT_INVALID")
    operation = _text(
        item["telemetry_operation_id"], "DURABLE_ATTEMPT_INVALID"
    )
    if not is_reserved_identity(operation, expected_namespace="EVIDENCE"):
        raise DurableRegistryError("DURABLE_ATTEMPT_INVALID")
    try:
        OrderId(order_id)
        occurred_at = CanonicalTimestamp(
            _text(recorded_at, "DURABLE_ATTEMPT_INVALID")
        )
    except ValueError:
        raise DurableRegistryError("DURABLE_ATTEMPT_INVALID") from None
    return DurableAttemptRecord(
        attempt_id=attempt,
        order_id=order_id,
        outcome=outcome,
        recorded_at=occurred_at,
        telemetry_operation_id=operation,
        evaluation=evaluation,
        auxiliary_event_id=_optional_text(
            item["auxiliary_event_id"], "DURABLE_ATTEMPT_INVALID"
        ),
        error_code=_optional_text(item["error_code"], "DURABLE_ATTEMPT_INVALID"),
    )


def _verified_command_payload(
    command_domain: object,
    command_sha256: object,
    command_bytes: object,
    expected_domain: str,
) -> tuple[object, bytes]:
    if (
        command_domain != expected_domain
        or type(command_sha256) is not str
        or not isinstance(command_bytes, bytes)
    ):
        raise DurableRegistryError("DURABLE_COMMAND_INVALID")
    material = bytes(command_bytes)
    if domain_hash(expected_domain, material).sha256 != command_sha256:
        raise DurableRegistryError("DURABLE_COMMAND_INVALID")
    try:
        return parse_canonical_json_bytes(material), material
    except (TypeError, ValueError):
        raise DurableRegistryError("DURABLE_COMMAND_INVALID") from None


def _binding_record(row: Sequence[object]) -> DurableEvaluationBinding:
    if len(row) != 11:
        raise DurableRegistryError("DURABLE_EVALUATION_BINDING_INVALID")
    (
        command_id,
        natural_key,
        command_domain,
        command_sha256,
        command_bytes,
        accepted_at,
        result_domain,
        result_sha256,
        result_bytes,
        recorded_at,
        owner_id,
    ) = row
    command_payload, command_material = _verified_command_payload(
        command_domain,
        command_sha256,
        command_bytes,
        _EVALUATION_COMMAND_DOMAIN,
    )
    command = _mapping(
        command_payload,
        _EVALUATION_BINDING_MEMBERS,
        "DURABLE_EVALUATION_BINDING_INVALID",
    )
    result = _mapping(
        _verified_payload(
            result_domain,
            result_sha256,
            result_bytes,
            _EVALUATION_RESULT_DOMAIN,
        ),
        _EVALUATION_BINDING_MEMBERS,
        "DURABLE_EVALUATION_BINDING_INVALID",
    )
    if command != result or accepted_at != recorded_at:
        raise DurableRegistryError("DURABLE_EVALUATION_BINDING_INVALID")
    if command["schema_version"] != ATTEMPT_SCHEMA_VERSION:
        raise DurableRegistryError("DURABLE_EVALUATION_BINDING_INVALID")
    order_id = _text(command["order_id"], "DURABLE_EVALUATION_BINDING_INVALID")
    source_binding = _text(
        command["source_binding"],
        "DURABLE_EVALUATION_BINDING_INVALID",
    )
    if (
        order_id != owner_id
        or len(source_binding) != 64
        or any(character not in "0123456789abcdef" for character in source_binding)
    ):
        raise DurableRegistryError("DURABLE_EVALUATION_BINDING_INVALID")
    try:
        OrderId(order_id)
        occurred_at = CanonicalTimestamp(
            _text(recorded_at, "DURABLE_EVALUATION_BINDING_INVALID")
        )
    except ValueError:
        raise DurableRegistryError("DURABLE_EVALUATION_BINDING_INVALID") from None
    command_text = _text(command_id, "DURABLE_EVALUATION_BINDING_INVALID")
    if not is_reserved_identity(command_text, expected_namespace="EVIDENCE"):
        raise DurableRegistryError("DURABLE_EVALUATION_BINDING_INVALID")
    try:
        key = _mapping(
            parse_canonical_json_bytes(
                _text(natural_key, "DURABLE_EVALUATION_BINDING_INVALID").encode(
                    "utf-8"
                )
            ),
            _NATURAL_KEY_MEMBERS,
            "DURABLE_EVALUATION_BINDING_INVALID",
        )
        components = key["components"]
        if not isinstance(components, list) or len(components) != 1:
            raise DurableRegistryError("DURABLE_EVALUATION_BINDING_INVALID")
        request_key = _text(
            components[0],
            "DURABLE_EVALUATION_BINDING_INVALID",
            maximum=128,
        )
        NaturalKey(_EVALUATION_NAMESPACE, (request_key,))
        if validate_request_key(request_key) != request_key:
            raise DurableRegistryError("DURABLE_EVALUATION_BINDING_INVALID")
        binding_material = command_material + b"\n" + request_key.encode("ascii")
    except (
        DemoError,
        IdempotencyDefinitionError,
        TypeError,
        UnicodeEncodeError,
        ValueError,
    ):
        raise DurableRegistryError("DURABLE_EVALUATION_BINDING_INVALID") from None
    if command_text != _command_id("EVALUATION-BINDING", binding_material):
        raise DurableRegistryError("DURABLE_EVALUATION_BINDING_INVALID")
    return DurableEvaluationBinding(
        command_id=command_text,
        order_id=order_id,
        request_key=request_key,
        source_binding=source_binding,
        recorded_at=occurred_at,
    )


def _resolution_record(row: Sequence[object]) -> DurableEvaluationResolution:
    if len(row) != 10:
        raise DurableRegistryError("DURABLE_EVALUATION_RESOLUTION_INVALID")
    (
        command_id,
        command_domain,
        command_sha256,
        command_bytes,
        accepted_at,
        result_domain,
        result_sha256,
        result_bytes,
        recorded_at,
        owner_id,
    ) = row
    command_payload, command_material = _verified_command_payload(
        command_domain,
        command_sha256,
        command_bytes,
        _EVALUATION_RESOLUTION_COMMAND_DOMAIN,
    )
    command = _mapping(
        command_payload,
        _EVALUATION_RESOLUTION_MEMBERS,
        "DURABLE_EVALUATION_RESOLUTION_INVALID",
    )
    result = _mapping(
        _verified_payload(
            result_domain,
            result_sha256,
            result_bytes,
            _EVALUATION_RESOLUTION_RESULT_DOMAIN,
        ),
        _EVALUATION_RESOLUTION_MEMBERS,
        "DURABLE_EVALUATION_RESOLUTION_INVALID",
    )
    if command != result or accepted_at != recorded_at:
        raise DurableRegistryError("DURABLE_EVALUATION_RESOLUTION_INVALID")
    if command["schema_version"] != EVALUATION_RESOLUTION_SCHEMA_VERSION:
        raise DurableRegistryError("DURABLE_EVALUATION_RESOLUTION_INVALID")
    accepted_command_id = _text(
        command_id,
        "DURABLE_EVALUATION_RESOLUTION_INVALID",
    )
    binding_command_id = _text(
        command["binding_command_id"],
        "DURABLE_EVALUATION_RESOLUTION_INVALID",
    )
    attempt_id = _text(
        command["attempt_id"],
        "DURABLE_EVALUATION_RESOLUTION_INVALID",
    )
    telemetry_operation_id = _text(
        command["telemetry_operation_id"],
        "DURABLE_EVALUATION_RESOLUTION_INVALID",
    )
    if any(
        not is_reserved_identity(value, expected_namespace="EVIDENCE")
        for value in (
            accepted_command_id,
            binding_command_id,
            attempt_id,
            telemetry_operation_id,
        )
    ):
        raise DurableRegistryError("DURABLE_EVALUATION_RESOLUTION_INVALID")
    if accepted_command_id != _command_id("EVALUATION-RESOLUTION", command_material):
        raise DurableRegistryError("DURABLE_EVALUATION_RESOLUTION_INVALID")
    order_id = _text(command["order_id"], "DURABLE_EVALUATION_RESOLUTION_INVALID")
    if order_id != owner_id:
        raise DurableRegistryError("DURABLE_EVALUATION_RESOLUTION_INVALID")
    try:
        OrderId(order_id)
        occurred_at = CanonicalTimestamp(
            _text(recorded_at, "DURABLE_EVALUATION_RESOLUTION_INVALID")
        )
    except ValueError:
        raise DurableRegistryError("DURABLE_EVALUATION_RESOLUTION_INVALID") from None
    outcome = _text(command["outcome"], "DURABLE_EVALUATION_RESOLUTION_INVALID")
    if outcome not in {"SUCCEEDED", "CONFLICT"}:
        raise DurableRegistryError("DURABLE_EVALUATION_RESOLUTION_INVALID")
    return DurableEvaluationResolution(
        command_id=accepted_command_id,
        binding_command_id=binding_command_id,
        attempt_id=attempt_id,
        order_id=order_id,
        outcome=outcome,
        telemetry_operation_id=telemetry_operation_id,
        recorded_at=occurred_at,
    )


class DurableScenarioRegistry:
    """Persist and restore a bounded scenario registry without schema changes."""

    def __init__(self, database: SQLiteDatabase, *, limit: int) -> None:
        self.database = database
        self.limit = limit

    def resolve_instance(
        self,
        *,
        natural_component: str,
        alias: str,
        catalog_version: str,
        instance_key: str,
        mode: str,
        order_id: str,
        rule_pack: str,
        source_binding: str,
    ) -> DurableScenarioRecord:
        command = canonical_json_bytes(
            {
                "alias": alias,
                "catalog_version": catalog_version,
                "instance_key": instance_key,
                "mode": mode,
                "schema_version": INSTANCE_SCHEMA_VERSION,
            },
            expected_members={
                "alias",
                "catalog_version",
                "instance_key",
                "mode",
                "schema_version",
            },
        )
        key = NaturalKey(_INSTANCE_NAMESPACE, (natural_component,))
        command_material = command + b"\n" + natural_component.encode("ascii")
        with self.database.write() as connection:
            repository = SQLiteIdempotencyRepository(
                connection,
                command_id_factory=lambda: _command_id("INSTANCE", command_material),
                clock=self.database.clock,
            )

            def allocate(
                _accepted_command_id: str,
                recorded_at: CanonicalTimestamp,
            ) -> tuple[str, bytes]:
                count = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM durable_commands "
                        "WHERE natural_namespace=?",
                        (_INSTANCE_NAMESPACE,),
                    ).fetchone()[0]
                )
                if count > self.limit:
                    raise DurableRegistryError("DURABLE_REGISTRY_CAPACITY_REACHED")
                result = canonical_json_bytes(
                    {
                        "alias": alias,
                        "catalog_version": catalog_version,
                        "created_at": recorded_at.value,
                        "instance_key": instance_key,
                        "mode": mode,
                        "order_id": order_id,
                        "rule_pack": rule_pack,
                        "schema_version": INSTANCE_SCHEMA_VERSION,
                        "source_binding": source_binding,
                    },
                    expected_members=_INSTANCE_MEMBERS,
                )
                return _INSTANCE_RESULT_DOMAIN, result

            resolved = repository.resolve_or_record(
                natural_key=key,
                command_domain=_INSTANCE_COMMAND_DOMAIN,
                command_bytes=command,
                owner_domain="SYSTEM",
                owner_id=order_id,
                result_allocator=allocate,
            )
            row = connection.execute(
                "SELECT result_domain, result_sha256, result_bytes "
                "FROM durable_command_receipts WHERE command_id=?",
                (resolved.command_id,),
            ).fetchone()
        if row is None:
            raise DurableRegistryError("DURABLE_RECEIPT_MISSING")
        payload = _verified_payload(row[0], row[1], row[2], _INSTANCE_RESULT_DOMAIN)
        return _scenario_record(payload)

    def list_instances(self) -> tuple[DurableScenarioRecord, ...]:
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT r.result_domain, r.result_sha256, r.result_bytes, o.owner_id "
                "FROM durable_commands c JOIN durable_command_receipts r "
                "ON r.command_id=c.command_id JOIN durable_receipt_owners o "
                "ON o.command_id=c.command_id WHERE c.natural_namespace=? "
                "AND o.owner_domain='SYSTEM' ORDER BY c.accepted_at, c.command_id "
                "LIMIT ?",
                (_INSTANCE_NAMESPACE, self.limit + 1),
            ).fetchall()
        if len(rows) > self.limit:
            raise DurableRegistryError("DURABLE_REGISTRY_CAPACITY_REACHED")
        records: list[DurableScenarioRecord] = []
        for row in rows:
            payload = _verified_payload(row[0], row[1], row[2], _INSTANCE_RESULT_DOMAIN)
            record = _scenario_record(payload)
            if record.order_id != row[3]:
                raise DurableRegistryError("DURABLE_INSTANCE_INVALID")
            records.append(record)
        return tuple(records)

    def bind_evaluation(
        self,
        *,
        request_key: str,
        order_id: str,
        source_binding: str,
    ) -> DurableCommandResult:
        material = canonical_json_bytes(
            {
                "order_id": order_id,
                "schema_version": ATTEMPT_SCHEMA_VERSION,
                "source_binding": source_binding,
            },
            expected_members=_EVALUATION_BINDING_MEMBERS,
        )
        command_material = material + b"\n" + request_key.encode("ascii")
        with self.database.write() as connection:
            repository = SQLiteIdempotencyRepository(
                connection,
                command_id_factory=lambda: _command_id(
                    "EVALUATION-BINDING", command_material
                ),
                clock=self.database.clock,
            )
            return repository.resolve_or_record(
                natural_key=NaturalKey(_EVALUATION_NAMESPACE, (request_key,)),
                command_domain=_EVALUATION_COMMAND_DOMAIN,
                command_bytes=material,
                owner_domain="SYSTEM",
                owner_id=order_id,
                result_allocator=lambda _command_id, _recorded_at: (
                    _EVALUATION_RESULT_DOMAIN,
                    material,
                ),
            )

    def evaluation_bindings(
        self,
        *,
        limit: int,
    ) -> tuple[DurableEvaluationBinding, ...]:
        if type(limit) is not int or not 1 <= limit <= 65_536:
            raise DurableRegistryError("DURABLE_EVALUATION_BINDING_LIMIT_INVALID")
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT c.command_id, c.natural_key, c.command_domain, "
                "c.command_sha256, c.command_bytes, c.accepted_at, "
                "r.result_domain, r.result_sha256, r.result_bytes, r.recorded_at, "
                "o.owner_id FROM durable_commands c "
                "JOIN durable_command_receipts r ON r.command_id=c.command_id "
                "JOIN durable_receipt_owners o ON o.command_id=c.command_id "
                "WHERE c.natural_namespace=? AND o.owner_domain='SYSTEM' "
                "ORDER BY c.accepted_at, c.command_id LIMIT ?",
                (_EVALUATION_NAMESPACE, limit + 1),
            ).fetchall()
        if len(rows) > limit:
            raise DurableRegistryError("DURABLE_EVALUATION_BINDING_LIMIT_EXCEEDED")
        return tuple(_binding_record(tuple(row)) for row in rows)

    def evaluation_resolution(
        self,
        binding_command_id: str,
    ) -> DurableEvaluationResolution | None:
        try:
            key = NaturalKey(
                _EVALUATION_RESOLUTION_NAMESPACE,
                (binding_command_id,),
            )
        except IdempotencyDefinitionError:
            raise DurableRegistryError(
                "DURABLE_EVALUATION_RESOLUTION_INVALID"
            ) from None
        natural_key = canonical_json_bytes(
            {"components": list(key.components)},
            expected_members=_NATURAL_KEY_MEMBERS,
        ).decode("utf-8")
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT c.command_id, c.command_domain, c.command_sha256, "
                "c.command_bytes, c.accepted_at, r.result_domain, "
                "r.result_sha256, r.result_bytes, r.recorded_at, o.owner_id "
                "FROM durable_commands c JOIN durable_command_receipts r "
                "ON r.command_id=c.command_id JOIN durable_receipt_owners o "
                "ON o.command_id=c.command_id WHERE c.natural_namespace=? "
                "AND c.natural_key=? AND o.owner_domain='SYSTEM' LIMIT 2",
                (_EVALUATION_RESOLUTION_NAMESPACE, natural_key),
            ).fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            raise DurableRegistryError("DURABLE_EVALUATION_RESOLUTION_INVALID")
        resolution = _resolution_record(tuple(rows[0]))
        if resolution.binding_command_id != binding_command_id:
            raise DurableRegistryError("DURABLE_EVALUATION_RESOLUTION_INVALID")
        return resolution

    def append_attempt(
        self,
        *,
        order_id: str,
        outcome: str,
        telemetry_operation_id: str,
        evaluation: EvaluationResultView | None,
        auxiliary_event_id: str | None,
        error_code: str | None,
        evaluation_binding_command_id: str | None = None,
    ) -> CanonicalTimestamp:
        attempt_nonce = uuid.uuid4().hex.upper()
        attempt_id = f"SYN-EVIDENCE-M5-ATTEMPT-{attempt_nonce}"
        result = canonical_json_bytes(
            {
                "auxiliary_event_id": auxiliary_event_id,
                "error_code": error_code,
                "evaluation": None if evaluation is None else evaluation.to_dict(),
                "order_id": order_id,
                "outcome": outcome,
                "schema_version": ATTEMPT_SCHEMA_VERSION,
                "telemetry_operation_id": telemetry_operation_id,
            },
            expected_members=_ATTEMPT_MEMBERS,
        )
        command = canonical_json_bytes(
            {
                "attempt_id": attempt_id,
                "order_id": order_id,
                "schema_version": ATTEMPT_SCHEMA_VERSION,
            },
            expected_members=_ATTEMPT_COMMAND_MEMBERS,
        )
        resolution: bytes | None = None
        if evaluation_binding_command_id is not None:
            if (
                outcome not in {"SUCCEEDED", "CONFLICT"}
                or not is_reserved_identity(
                    evaluation_binding_command_id,
                    expected_namespace="EVIDENCE",
                )
            ):
                raise DurableRegistryError("DURABLE_EVALUATION_RESOLUTION_INVALID")
            resolution = canonical_json_bytes(
                {
                    "attempt_id": attempt_id,
                    "binding_command_id": evaluation_binding_command_id,
                    "order_id": order_id,
                    "outcome": outcome,
                    "schema_version": EVALUATION_RESOLUTION_SCHEMA_VERSION,
                    "telemetry_operation_id": telemetry_operation_id,
                },
                expected_members=_EVALUATION_RESOLUTION_MEMBERS,
            )
        with self.database.write() as connection:
            repository = SQLiteIdempotencyRepository(
                connection,
                command_id_factory=lambda: attempt_id,
                clock=self.database.clock,
            )
            try:
                persisted = repository.resolve_or_record(
                    natural_key=NaturalKey(_ATTEMPT_NAMESPACE, (attempt_nonce,)),
                    command_domain=_ATTEMPT_COMMAND_DOMAIN,
                    command_bytes=command,
                    owner_domain="SYSTEM",
                    owner_id=order_id,
                    result_allocator=lambda _command_id, _recorded_at: (
                        _ATTEMPT_RESULT_DOMAIN,
                        result,
                    ),
                )
            except IdempotencyError:
                raise DurableRegistryError(
                    "DURABLE_ATTEMPT_NONCE_COLLISION"
                ) from None
            if persisted.replayed:
                raise DurableRegistryError("DURABLE_ATTEMPT_NONCE_COLLISION")
            if resolution is not None:
                resolution_repository = SQLiteIdempotencyRepository(
                    connection,
                    command_id_factory=lambda: _command_id(
                        "EVALUATION-RESOLUTION",
                        resolution,
                    ),
                    clock=self.database.clock,
                )
                try:
                    linked = resolution_repository.resolve_or_record(
                        natural_key=NaturalKey(
                            _EVALUATION_RESOLUTION_NAMESPACE,
                            (cast(str, evaluation_binding_command_id),),
                        ),
                        command_domain=_EVALUATION_RESOLUTION_COMMAND_DOMAIN,
                        command_bytes=resolution,
                        owner_domain="SYSTEM",
                        owner_id=order_id,
                        result_allocator=lambda _command_id, _recorded_at: (
                            _EVALUATION_RESOLUTION_RESULT_DOMAIN,
                            resolution,
                        ),
                    )
                except (IdempotencyConflictError, IdempotencyDefinitionError):
                    raise DurableRegistryError(
                        "DURABLE_EVALUATION_RESOLUTION_CONFLICT"
                    ) from None
                if linked.replayed:
                    raise DurableRegistryError(
                        "DURABLE_EVALUATION_RESOLUTION_CONFLICT"
                    )
        return persisted.recorded_at

    def attempts(
        self,
        order_id: str,
        *,
        limit: int,
    ) -> tuple[DurableAttemptRecord, ...]:
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT c.command_id, c.natural_key, c.command_domain, "
                "c.command_sha256, c.command_bytes, c.accepted_at, o.owner_id, "
                "r.result_domain, r.result_sha256, r.result_bytes, r.recorded_at "
                "FROM durable_commands c JOIN durable_command_receipts r "
                "ON r.command_id=c.command_id JOIN durable_receipt_owners o "
                "ON o.command_id=c.command_id WHERE c.natural_namespace=? "
                "AND o.owner_domain='SYSTEM' AND o.owner_id=? "
                "ORDER BY r.recorded_at, c.command_id LIMIT ?",
                (_ATTEMPT_NAMESPACE, order_id, limit + 1),
            ).fetchall()
        if len(rows) > limit:
            raise DurableRegistryError("DURABLE_ATTEMPT_LIMIT_EXCEEDED")
        return tuple(_attempt_record(tuple(row)) for row in rows)

    def attempt(
        self,
        attempt_id: str,
        *,
        order_id: str,
    ) -> DurableAttemptRecord | None:
        if (
            not is_reserved_identity(attempt_id, expected_namespace="EVIDENCE")
            or not is_reserved_identity(order_id, expected_namespace="ORDER")
        ):
            raise DurableRegistryError("DURABLE_ATTEMPT_INVALID")
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT c.command_id, c.natural_key, c.command_domain, "
                "c.command_sha256, c.command_bytes, c.accepted_at, o.owner_id, "
                "r.result_domain, r.result_sha256, r.result_bytes, r.recorded_at "
                "FROM durable_commands c JOIN durable_command_receipts r "
                "ON r.command_id=c.command_id JOIN durable_receipt_owners o "
                "ON o.command_id=c.command_id WHERE c.command_id=? "
                "AND c.natural_namespace=? AND o.owner_domain='SYSTEM' "
                "AND o.owner_id=? LIMIT 2",
                (attempt_id, _ATTEMPT_NAMESPACE, order_id),
            ).fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            raise DurableRegistryError("DURABLE_ATTEMPT_INVALID")
        return _attempt_record(tuple(rows[0]))

    def processing_telemetry(
        self,
        operation_id: str,
    ) -> ProcessingTelemetry | None:
        if not is_reserved_identity(operation_id, expected_namespace="EVIDENCE"):
            raise DurableRegistryError("DURABLE_TELEMETRY_INVALID")
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT operation_id, rule_pack, demo_alias, started_at, ended_at, "
                "extraction_ns, validation_ns, normalization_ns, rule_ns, "
                "database_ns, total_ns, result_class, human_review, fail_closed, "
                "replay, conflict, database_error, rule_version, schema_version, "
                "catalog_version, error_code FROM processing_telemetry "
                "WHERE operation_id=? LIMIT 2",
                (operation_id,),
            ).fetchall()
            counter_rows = connection.execute(
                "SELECT counter_name, counter_value FROM telemetry_safety_counters "
                "WHERE operation_id=? ORDER BY counter_name",
                (operation_id,),
            ).fetchall()
        if not rows:
            if counter_rows:
                raise DurableRegistryError("DURABLE_TELEMETRY_INVALID")
            return None
        if len(rows) != 1:
            raise DurableRegistryError("DURABLE_TELEMETRY_INVALID")
        row = rows[0]
        required_text_indexes = (0, 1, 3, 4, 11, 17, 18)
        optional_text_indexes = (2, 19, 20)
        if (
            any(type(row[index]) is not str for index in required_text_indexes)
            or any(
                row[index] is not None and type(row[index]) is not str
                for index in optional_text_indexes
            )
            or any(
                type(row[index]) is not int or row[index] < 0
                for index in range(5, 11)
            )
            or any(
                type(row[index]) is not int or row[index] not in {0, 1}
                for index in range(12, 17)
            )
            or any(
                type(counter[0]) is not str or type(counter[1]) is not int
                for counter in counter_rows
            )
        ):
            raise DurableRegistryError("DURABLE_TELEMETRY_INVALID")
        counters: tuple[tuple[str, int], ...] = tuple(
            (counter[0], counter[1]) for counter in counter_rows
        )
        try:
            return ProcessingTelemetry(
                operation_id=row[0],
                rule_pack=RulePack(row[1]),
                demo_alias=row[2],
                started_at=CanonicalTimestamp(row[3]),
                ended_at=CanonicalTimestamp(row[4]),
                extraction_ns=row[5],
                validation_ns=row[6],
                normalization_ns=row[7],
                rule_ns=row[8],
                database_ns=row[9],
                total_ns=row[10],
                result_class=ProcessingResultClass(row[11]),
                human_review=bool(row[12]),
                fail_closed=bool(row[13]),
                replay=bool(row[14]),
                conflict=bool(row[15]),
                database_error=bool(row[16]),
                rule_version=row[17],
                schema_version=row[18],
                catalog_version=row[19],
                error_code=row[20],
                safety_counters=counters,
            )
        except (TypeError, ValueError, RuntimeError):
            raise DurableRegistryError("DURABLE_TELEMETRY_INVALID") from None

    def receipt_recorded_at(self, command_ids: Sequence[str]) -> dict[str, str]:
        unique = tuple(dict.fromkeys(command_ids))
        if not unique:
            return {}
        if len(unique) > 256:
            raise DurableRegistryError("DURABLE_RECEIPT_LIMIT_EXCEEDED")
        placeholders = ",".join("?" for _ in unique)
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT command_id, recorded_at FROM durable_command_receipts "
                f"WHERE command_id IN ({placeholders}) ORDER BY command_id",
                unique,
            ).fetchall()
        result = {str(row[0]): str(row[1]) for row in rows}
        if frozenset(result) != frozenset(unique):
            raise DurableRegistryError("DURABLE_RECEIPT_MISSING")
        return result

    def existing_telemetry(self, operation_ids: Sequence[str]) -> frozenset[str]:
        unique = tuple(dict.fromkeys(operation_ids))
        if not unique:
            return frozenset()
        if len(unique) > 256:
            raise DurableRegistryError("DURABLE_ATTEMPT_LIMIT_EXCEEDED")
        placeholders = ",".join("?" for _ in unique)
        with self.database.read() as connection:
            rows = connection.execute(
                "SELECT operation_id FROM processing_telemetry "
                f"WHERE operation_id IN ({placeholders}) ORDER BY operation_id",
                unique,
            ).fetchall()
        return frozenset(str(row[0]) for row in rows)

    def latest_telemetry_operation(
        self,
        *,
        alias: str,
        not_before: CanonicalTimestamp,
    ) -> str:
        """Read the operation emitted by the legacy malformed-input backend."""

        with self.database.read() as connection:
            row = connection.execute(
                "SELECT operation_id FROM processing_telemetry "
                "WHERE demo_alias=? AND started_at>=? "
                "ORDER BY ended_at DESC, operation_id DESC LIMIT 1",
                (alias, not_before.value),
            ).fetchone()
        if row is None or not is_reserved_identity(str(row[0])):
            raise DurableRegistryError("DURABLE_TELEMETRY_MISSING")
        return str(row[0])


__all__ = [
    "ATTEMPT_SCHEMA_VERSION",
    "EVALUATION_RESOLUTION_SCHEMA_VERSION",
    "INSTANCE_SCHEMA_VERSION",
    "DurableAttemptRecord",
    "DurableEvaluationBinding",
    "DurableEvaluationResolution",
    "DurableRegistryError",
    "DurableScenarioRecord",
    "DurableScenarioRegistry",
]
