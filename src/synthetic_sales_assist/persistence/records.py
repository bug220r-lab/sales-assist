"""Validated typed records returned by the durable repository layer."""

from __future__ import annotations

from dataclasses import dataclass, field

from synthetic_sales_assist.domain.canonical import HashBinding
from synthetic_sales_assist.domain.identities import EvidenceId, EvaluationId, OrderId
from synthetic_sales_assist.domain.numeric import Money
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.sales_credit.models import (
    AttributionClassification,
    HumanOutcomeType,
    OrderValueStatus,
    WorkflowState,
)


class PersistenceRecordError(ValueError):
    """A persisted row could not be represented by the closed typed surface."""


@dataclass(frozen=True, slots=True, repr=False)
class DurableCommandResult:
    command_id: str
    result: HashBinding = field(repr=False)
    recorded_at: CanonicalTimestamp
    replayed: bool

    def __post_init__(self) -> None:
        if (
            type(self.command_id) is not str
            or not self.command_id
            or type(self.result) is not HashBinding
            or type(self.recorded_at) is not CanonicalTimestamp
            or type(self.replayed) is not bool
        ):
            raise PersistenceRecordError("DURABLE_COMMAND_RESULT_INVALID")

    def __repr__(self) -> str:
        return "DurableCommandResult(<redacted>)"


@dataclass(frozen=True, slots=True)
class StoredSalesCreditCase:
    order_id: OrderId
    projection_version: int
    workflow_state: WorkflowState
    attribution: AttributionClassification
    order_value_status: OrderValueStatus
    placed_value: Money | None
    manager_occurrence_id: EvidenceId | None
    replacement_parent: OrderId | None
    current_evaluation_id: EvaluationId | None
    last_event_sequence: int
    last_event_id: EvidenceId
    created_at: CanonicalTimestamp
    updated_at: CanonicalTimestamp

    def __post_init__(self) -> None:
        if (
            type(self.order_id) is not OrderId
            or type(self.projection_version) is not int
            or self.projection_version < 1
            or type(self.workflow_state) is not WorkflowState
            or type(self.attribution) is not AttributionClassification
            or type(self.order_value_status) is not OrderValueStatus
            or (self.placed_value is not None and type(self.placed_value) is not Money)
            or (
                self.manager_occurrence_id is not None
                and type(self.manager_occurrence_id) is not EvidenceId
            )
            or (
                self.replacement_parent is not None
                and type(self.replacement_parent) is not OrderId
            )
            or (
                self.current_evaluation_id is not None
                and type(self.current_evaluation_id) is not EvaluationId
            )
            or type(self.last_event_sequence) is not int
            or self.last_event_sequence < 1
            or type(self.last_event_id) is not EvidenceId
            or type(self.created_at) is not CanonicalTimestamp
            or type(self.updated_at) is not CanonicalTimestamp
        ):
            raise PersistenceRecordError("STORED_SALES_CREDIT_CASE_INVALID")


@dataclass(frozen=True, slots=True)
class StoredSalesCreditEvent:
    event_id: EvidenceId
    order_id: OrderId
    sequence: int
    predecessor_event_id: EvidenceId | None
    event_kind: str
    workflow_state: WorkflowState
    attribution: AttributionClassification
    order_value_status: OrderValueStatus
    human_outcome: HumanOutcomeType | None
    current_evaluation_id: EvaluationId | None
    replacement_parent_present: bool
    occurred_at: CanonicalTimestamp
    command_id: str

    def __post_init__(self) -> None:
        if (
            type(self.event_id) is not EvidenceId
            or type(self.order_id) is not OrderId
            or type(self.sequence) is not int
            or self.sequence < 1
            or (
                self.predecessor_event_id is not None
                and type(self.predecessor_event_id) is not EvidenceId
            )
            or type(self.event_kind) is not str
            or self.event_kind
            not in {
                "CASE_CREATED",
                "FACTS_APPENDED",
                "OUTCOME_RECORDED",
                "CLOSED_MINIMIZED",
                "REPLACEMENT_PARENT_DETACHED",
            }
            or type(self.workflow_state) is not WorkflowState
            or type(self.attribution) is not AttributionClassification
            or type(self.order_value_status) is not OrderValueStatus
            or (
                self.human_outcome is not None
                and type(self.human_outcome) is not HumanOutcomeType
            )
            or (
                self.current_evaluation_id is not None
                and type(self.current_evaluation_id) is not EvaluationId
            )
            or type(self.replacement_parent_present) is not bool
            or type(self.occurred_at) is not CanonicalTimestamp
            or type(self.command_id) is not str
            or not 1 <= len(self.command_id) <= 128
            or not self.command_id.startswith("SYN-EVIDENCE-M4-")
            or (self.sequence == 1) != (self.predecessor_event_id is None)
            or (
                self.event_kind == "OUTCOME_RECORDED"
                and self.human_outcome is None
            )
            or (
                self.event_kind != "OUTCOME_RECORDED"
                and self.event_kind != "CLOSED_MINIMIZED"
                and self.human_outcome is not None
            )
            or (
                self.event_kind == "REPLACEMENT_PARENT_DETACHED"
                and self.replacement_parent_present
            )
        ):
            raise PersistenceRecordError("STORED_SALES_CREDIT_EVENT_INVALID")


@dataclass(frozen=True, slots=True)
class SalesCreditPurgeResult:
    cases_deleted: int
    closed_audits_deleted: int
    orphan_interactions_deleted: int
    orphan_snapshots_deleted: int
    orphan_evidence_deleted: int
    orphan_evaluations_deleted: int
    receipts_deleted: int

    def __post_init__(self) -> None:
        values = (
            self.cases_deleted,
            self.closed_audits_deleted,
            self.orphan_interactions_deleted,
            self.orphan_snapshots_deleted,
            self.orphan_evidence_deleted,
            self.orphan_evaluations_deleted,
            self.receipts_deleted,
        )
        if any(type(value) is not int or value < 0 for value in values):
            raise PersistenceRecordError("SALES_CREDIT_PURGE_RESULT_INVALID")


__all__ = [
    "DurableCommandResult",
    "PersistenceRecordError",
    "SalesCreditPurgeResult",
    "StoredSalesCreditCase",
    "StoredSalesCreditEvent",
]
