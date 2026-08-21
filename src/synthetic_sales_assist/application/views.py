"""Closed immutable application views shared by local adapters.

The application layer exposes only allowlisted synthetic facts and durable result
identifiers.  HTTP envelopes, status codes, HTML, and filesystem paths deliberately do
not belong in these records.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, TypeAlias


APPLICATION_SCHEMA_VERSION: Final = "synthetic-sales-assist-application/v1"
APPLICATION_BUILD_VERSION: Final = "synthetic-sales-assist-m5/v1"


class ApplicationError(RuntimeError):
    """A closed application failure that never reflects rejected input."""

    _CATEGORIES: Final = frozenset({"INVALID", "NOT_FOUND", "CONFLICT", "UNAVAILABLE"})

    def __init__(self, code: str, category: str) -> None:
        if (
            type(code) is not str
            or not code
            or len(code) > 96
            or type(category) is not str
            or category not in self._CATEGORIES
        ):
            raise ValueError("APPLICATION_ERROR_INVALID")
        self.code = code
        self.category = category
        super().__init__(f"application request rejected: {code}")


@dataclass(frozen=True, slots=True)
class MoneyView:
    amount: str
    currency_code: str
    currency_registry_version: str
    currency_scale: int

    def to_dict(self) -> dict[str, object]:
        return {
            "amount": self.amount,
            "currency_code": self.currency_code,
            "currency_registry_version": self.currency_registry_version,
            "currency_scale": self.currency_scale,
        }


FactScalar: TypeAlias = str | int | MoneyView | None


@dataclass(frozen=True, slots=True)
class FactView:
    tag: str
    value: FactScalar
    reason_code: str | None

    def to_dict(self) -> dict[str, object]:
        value: object = self.value
        if isinstance(value, MoneyView):
            value = value.to_dict()
        return {"reason_code": self.reason_code, "tag": self.tag, "value": value}


@dataclass(frozen=True, slots=True)
class ScenarioDescriptorView:
    alias: str
    rule_pack: str
    description: str
    expected_result: str
    collected_scenario: str
    complexity: str
    allowed_modes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "alias": self.alias,
            "allowed_modes": list(self.allowed_modes),
            "collected_scenario": self.collected_scenario,
            "complexity": self.complexity,
            "description": self.description,
            "expected_result": self.expected_result,
            "rule_pack": self.rule_pack,
            "schema_version": APPLICATION_SCHEMA_VERSION,
        }


@dataclass(frozen=True, slots=True)
class LineView:
    line_id: str
    line_index: int
    product_id: str
    quantity: FactView
    line_value: FactView
    availability: FactView
    eta: FactView
    drop_ship_state: FactView
    activity: FactView

    def to_dict(self) -> dict[str, object]:
        return {
            "activity": self.activity.to_dict(),
            "availability": self.availability.to_dict(),
            "drop_ship_state": self.drop_ship_state.to_dict(),
            "eta": self.eta.to_dict(),
            "line_id": self.line_id,
            "line_index": self.line_index,
            "line_value": self.line_value.to_dict(),
            "product_id": self.product_id,
            "quantity": self.quantity.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class CompletenessView:
    state: str
    requested_order_id: str
    observed_order_id: str | None
    declared_relevant_line_count: int | None
    rendered_relevant_line_count: int
    ordered_line_manifest_digest: str | None
    fixture_version: str
    source_schema_version: str
    source_observed_at: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "declared_relevant_line_count": self.declared_relevant_line_count,
            "fixture_version": self.fixture_version,
            "observed_order_id": self.observed_order_id,
            "ordered_line_manifest_digest": self.ordered_line_manifest_digest,
            "rendered_relevant_line_count": self.rendered_relevant_line_count,
            "requested_order_id": self.requested_order_id,
            "source_observed_at": self.source_observed_at,
            "source_schema_version": self.source_schema_version,
            "state": self.state,
        }


@dataclass(frozen=True, slots=True)
class OpportunityView:
    opportunity_type: str
    line_ids: tuple[str, ...]
    potential_value: MoneyView | None

    def to_dict(self) -> dict[str, object]:
        return {
            "line_ids": list(self.line_ids),
            "opportunity_type": self.opportunity_type,
            "potential_value": (
                None if self.potential_value is None else self.potential_value.to_dict()
            ),
        }


@dataclass(frozen=True, slots=True)
class ExplanationView:
    supplied_facts: tuple[str, ...]
    normalized_facts: tuple[str, ...]
    unavailable_facts: tuple[str, ...]
    rules_evaluated: tuple[str, ...]
    precedence_decision: str
    reason_ownership: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "normalized_facts": list(self.normalized_facts),
            "precedence_decision": self.precedence_decision,
            "reason_ownership": list(self.reason_ownership),
            "rules_evaluated": list(self.rules_evaluated),
            "supplied_facts": list(self.supplied_facts),
            "unavailable_facts": list(self.unavailable_facts),
        }


@dataclass(frozen=True, slots=True)
class ProcessingStageView:
    stage: str
    duration_ns: int
    status: str

    def to_dict(self) -> dict[str, object]:
        return {
            "duration_ns": self.duration_ns,
            "stage": self.stage,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class EvaluationResultView:
    order_id: str
    scenario_alias: str
    rule_pack: str
    top_level_result: str
    workflow_state: str
    reasons: tuple[str, ...]
    fired_rules: tuple[str, ...]
    opportunities: tuple[OpportunityView, ...]
    aggregate_potential_status: str
    aggregate_potential_value: MoneyView | None
    value_status: str
    value: MoneyView | None
    human_review_required: bool
    handling_flags: tuple[str, ...]
    closure_state: str | None
    explanation: ExplanationView
    processing_stages: tuple[ProcessingStageView, ...]
    replayed: bool
    conflict: bool
    command_id: str | None
    case_id: str | None
    run_id: str | None
    snapshot_id: str | None
    evaluation_id: str | None
    rule_pack_version: str
    processing_duration_ns: int

    def to_dict(self) -> dict[str, object]:
        return {
            "aggregate_potential_status": self.aggregate_potential_status,
            "aggregate_potential_value": (
                None
                if self.aggregate_potential_value is None
                else self.aggregate_potential_value.to_dict()
            ),
            "case_id": self.case_id,
            "closure_state": self.closure_state,
            "command_id": self.command_id,
            "conflict": self.conflict,
            "evaluation_id": self.evaluation_id,
            "explanation": self.explanation.to_dict(),
            "fired_rules": list(self.fired_rules),
            "handling_flags": list(self.handling_flags),
            "human_review_required": self.human_review_required,
            "opportunities": [item.to_dict() for item in self.opportunities],
            "order_id": self.order_id,
            "processing_duration_ns": self.processing_duration_ns,
            "processing_stages": [item.to_dict() for item in self.processing_stages],
            "reasons": list(self.reasons),
            "replayed": self.replayed,
            "rule_pack": self.rule_pack,
            "rule_pack_version": self.rule_pack_version,
            "run_id": self.run_id,
            "scenario_alias": self.scenario_alias,
            "schema_version": APPLICATION_SCHEMA_VERSION,
            "snapshot_id": self.snapshot_id,
            "top_level_result": self.top_level_result,
            "value": None if self.value is None else self.value.to_dict(),
            "value_status": self.value_status,
            "workflow_state": self.workflow_state,
        }


@dataclass(frozen=True, slots=True)
class OrderSummaryView:
    order_id: str
    scenario_alias: str
    mode: str
    rule_pack: str
    order_status: str
    relevant_line_count: int
    doi_state: str | None
    sales_credit_state: str | None
    human_review_required: bool
    evaluated: bool
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "doi_state": self.doi_state,
            "evaluated": self.evaluated,
            "human_review_required": self.human_review_required,
            "mode": self.mode,
            "order_id": self.order_id,
            "order_status": self.order_status,
            "relevant_line_count": self.relevant_line_count,
            "rule_pack": self.rule_pack,
            "sales_credit_state": self.sales_credit_state,
            "scenario_alias": self.scenario_alias,
            "schema_version": APPLICATION_SCHEMA_VERSION,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class OrderDetailView:
    order_id: str
    scenario_alias: str
    mode: str
    rule_pack: str
    source_status: str
    order_status: str
    created_at: str
    updated_at: str
    lines: tuple[LineView, ...]
    interaction_ids: tuple[str, ...]
    completeness: CompletenessView
    latest_evaluation: EvaluationResultView | None

    @property
    def summary(self) -> OrderSummaryView:
        evaluation = self.latest_evaluation
        return OrderSummaryView(
            order_id=self.order_id,
            scenario_alias=self.scenario_alias,
            mode=self.mode,
            rule_pack=self.rule_pack,
            order_status=self.order_status,
            relevant_line_count=len(self.lines),
            doi_state=(
                evaluation.top_level_result
                if evaluation is not None and self.rule_pack == "DOI"
                else None
            ),
            sales_credit_state=(
                evaluation.workflow_state
                if evaluation is not None and self.rule_pack == "SALES_CREDIT"
                else None
            ),
            human_review_required=(
                False if evaluation is None else evaluation.human_review_required
            ),
            evaluated=evaluation is not None,
            updated_at=self.updated_at,
        )

    def to_dict(self) -> dict[str, object]:
        summary = self.summary.to_dict()
        return {
            **summary,
            "completeness": self.completeness.to_dict(),
            "created_at": self.created_at,
            "interaction_ids": list(self.interaction_ids),
            "latest_evaluation": (
                None if self.latest_evaluation is None else self.latest_evaluation.to_dict()
            ),
            "lines": [line.to_dict() for line in self.lines],
            "source_status": self.source_status,
        }


@dataclass(frozen=True, slots=True)
class HistoryEventView:
    sequence: int
    event_id: str | None
    event_kind: str
    state: str
    occurred_at: str
    evaluation_id: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "evaluation_id": self.evaluation_id,
            "event_id": self.event_id,
            "event_kind": self.event_kind,
            "occurred_at": self.occurred_at,
            "sequence": self.sequence,
            "state": self.state,
        }


@dataclass(frozen=True, slots=True)
class HistoryArtifactView:
    artifact_type: str
    artifact_id: str | None
    state: str
    occurred_at: str
    reasons: tuple[str, ...]
    transition_id: str | None
    value: MoneyView | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "occurred_at": self.occurred_at,
            "reasons": list(self.reasons),
            "state": self.state,
            "transition_id": self.transition_id,
            "value": None if self.value is None else self.value.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ReceiptSummaryView:
    command_id: str
    replayed: bool
    recorded_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "command_id": self.command_id,
            "recorded_at": self.recorded_at,
            "replayed": self.replayed,
        }


@dataclass(frozen=True, slots=True)
class AttemptReceiptView:
    attempt_id: str
    command_id: str | None
    outcome: str
    replayed: bool
    conflict: bool
    error_code: str | None
    telemetry_operation_id: str
    recorded_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "attempt_id": self.attempt_id,
            "command_id": self.command_id,
            "conflict": self.conflict,
            "error_code": self.error_code,
            "outcome": self.outcome,
            "recorded_at": self.recorded_at,
            "replayed": self.replayed,
            "telemetry_operation_id": self.telemetry_operation_id,
        }


@dataclass(frozen=True, slots=True)
class HistoryView:
    order_id: str
    events: tuple[HistoryEventView, ...]
    artifacts: tuple[HistoryArtifactView, ...]
    receipts: tuple[ReceiptSummaryView, ...]
    attempt_receipts: tuple[AttemptReceiptView, ...]
    attention_causes: tuple[HistoryArtifactView, ...]
    intervention_events: tuple[HistoryArtifactView, ...]
    value_events: tuple[HistoryArtifactView, ...]
    manager_outcomes: tuple[HistoryArtifactView, ...]
    telemetry_event_count: int
    exact_replay_count: int
    conflict_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "attempt_receipts": [item.to_dict() for item in self.attempt_receipts],
            "conflict_count": self.conflict_count,
            "artifacts": [item.to_dict() for item in self.artifacts],
            "attention_causes": [item.to_dict() for item in self.attention_causes],
            "events": [item.to_dict() for item in self.events],
            "exact_replay_count": self.exact_replay_count,
            "intervention_events": [
                item.to_dict() for item in self.intervention_events
            ],
            "manager_outcomes": [item.to_dict() for item in self.manager_outcomes],
            "order_id": self.order_id,
            "receipts": [item.to_dict() for item in self.receipts],
            "schema_version": APPLICATION_SCHEMA_VERSION,
            "telemetry_event_count": self.telemetry_event_count,
            "value_events": [item.to_dict() for item in self.value_events],
        }


@dataclass(frozen=True, slots=True)
class InteractionView:
    interaction_id: str
    direction: str
    timestamp: str
    timestamp_precision: str
    target_rep_participation: str
    identifier_kind: str
    evidence_classification: str
    order_id: str

    def to_dict(self) -> dict[str, object]:
        return {
            "direction": self.direction,
            "evidence_classification": self.evidence_classification,
            "identifier_kind": self.identifier_kind,
            "interaction_id": self.interaction_id,
            "order_id": self.order_id,
            "schema_version": APPLICATION_SCHEMA_VERSION,
            "target_rep_participation": self.target_rep_participation,
            "timestamp": self.timestamp,
            "timestamp_precision": self.timestamp_precision,
        }


@dataclass(frozen=True, slots=True)
class RunView:
    run_id: str
    rule_pack: str
    order_id: str
    run_type: str
    status: str
    started_at: str
    completed_at: str | None
    event_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "completed_at": self.completed_at,
            "event_count": self.event_count,
            "order_id": self.order_id,
            "rule_pack": self.rule_pack,
            "run_id": self.run_id,
            "run_type": self.run_type,
            "schema_version": APPLICATION_SCHEMA_VERSION,
            "started_at": self.started_at,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class MetricsSummaryView:
    total_processed: int
    success_count: int
    success_rate_numerator: int
    success_rate_denominator: int
    failed_closed_count: int
    human_review_count: int
    exact_replay_count: int
    conflict_count: int
    database_error_count: int
    median_latency_ns: int | None
    p95_latency_ns: int | None
    throughput_per_second: str | None
    safety_counters: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "conflict_count": self.conflict_count,
            "database_error_count": self.database_error_count,
            "exact_replay_count": self.exact_replay_count,
            "failed_closed_count": self.failed_closed_count,
            "human_review_count": self.human_review_count,
            "median_latency_ns": self.median_latency_ns,
            "p95_latency_ns": self.p95_latency_ns,
            "safety_counters": dict(self.safety_counters),
            "schema_version": APPLICATION_SCHEMA_VERSION,
            "success_count": self.success_count,
            "success_rate": {
                "defined": self.success_rate_denominator > 0,
                "denominator": self.success_rate_denominator,
                "numerator": self.success_rate_numerator,
            },
            "throughput_per_second": self.throughput_per_second,
            "total_processed": self.total_processed,
        }


@dataclass(frozen=True, slots=True)
class SystemStatusView:
    app_version: str
    build_version: str
    database_status: str
    database_schema_version: int
    expected_schema_version: int
    quick_check: str
    integrity_check: str
    migration_status: str
    projection_status: str
    safety_counters: tuple[tuple[str, int], ...]
    registry_capacity: int
    registry_count: int
    evaluated_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "app_version": self.app_version,
            "build_version": self.build_version,
            "database_schema_version": self.database_schema_version,
            "database_status": self.database_status,
            "evaluated_count": self.evaluated_count,
            "expected_schema_version": self.expected_schema_version,
            "integrity_check": self.integrity_check,
            "migration_status": self.migration_status,
            "projection_status": self.projection_status,
            "quick_check": self.quick_check,
            "registry_capacity": self.registry_capacity,
            "registry_count": self.registry_count,
            "safety_counters": dict(self.safety_counters),
            "schema_version": APPLICATION_SCHEMA_VERSION,
        }


__all__ = [
    "APPLICATION_BUILD_VERSION",
    "APPLICATION_SCHEMA_VERSION",
    "AttemptReceiptView",
    "ApplicationError",
    "CompletenessView",
    "EvaluationResultView",
    "ExplanationView",
    "FactView",
    "HistoryArtifactView",
    "HistoryEventView",
    "HistoryView",
    "InteractionView",
    "LineView",
    "MetricsSummaryView",
    "MoneyView",
    "OpportunityView",
    "OrderDetailView",
    "OrderSummaryView",
    "ProcessingStageView",
    "ReceiptSummaryView",
    "RunView",
    "ScenarioDescriptorView",
    "SystemStatusView",
]
