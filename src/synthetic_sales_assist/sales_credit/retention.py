"""Pure Sales Credit closure minimization and elapsed retention decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import ClassVar

from synthetic_sales_assist.domain.canonical import (
    HashBinding,
    canonical_json_bytes,
    domain_hash,
)
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.sales_credit.discovery import (
    DiscoveryOutcome,
    NoOrderLedgerError,
    NoOrderStateResult,
    OrderSearchRun,
    _NoOrderTransitionAuthority,
    combine_search_results,
    plan_discovery,
)
from synthetic_sales_assist.sales_credit.models import (
    ClosedNoteCode,
    ClosedAuditRecord,
    EvidenceEvent,
    HumanOutcomeType,
    InteractionRecord,
    SALES_CREDIT_RULE_PACK_VERSION,
    SalesCreditCase,
    SalesCreditEvaluation,
    SalesCreditReason,
    SalesCreditValidationError,
    SearchTriggerType,
    TimestampPrecision,
    WorkflowState,
)
from synthetic_sales_assist.sales_credit.windows import business_local_date


RETENTION_SECONDS = 90 * 24 * 60 * 60
_TERMINAL_WITHOUT_HUMAN = {
    WorkflowState.CANCELED_NO_REPLACEMENT,
    WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
    WorkflowState.VERIFIED_PREORDER_EVIDENCE,
}
_MANAGER_OUTCOME_WORKFLOWS = {
    WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
    WorkflowState.INBOUND_EVIDENCE_HUMAN_REVIEW,
    WorkflowState.MANUAL_REVIEW_REQUIRED,
    WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
    WorkflowState.OTHER_REP_HUMAN_REVIEW,
    WorkflowState.OUTBOUND_EVIDENCE_HUMAN_REVIEW,
    WorkflowState.POSSIBLE_REPLACEMENT_HUMAN_REVIEW,
    WorkflowState.TIMING_UNCERTAIN_HUMAN_REVIEW,
    WorkflowState.VERIFIED_PREORDER_EVIDENCE,
}


class RetentionDecisionError(ValueError):
    """Reject an invalid closure operation without retaining active material."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Sales Credit retention input rejected: {code}")


@dataclass(frozen=True, slots=True)
class ClosureProjection:
    """Verified minimized survivor plus nonidentifying removal counts."""

    record: ClosedAuditRecord
    interactions_removed: int
    snapshots_removed: int
    evidence_removed: int
    evaluations_removed: int

    def __post_init__(self) -> None:
        if type(self.record) is not ClosedAuditRecord:
            raise RetentionDecisionError("closure_record_type")
        for value in (
            self.interactions_removed,
            self.snapshots_removed,
            self.evidence_removed,
            self.evaluations_removed,
        ):
            if type(value) is not int or value < 0:
                raise RetentionDecisionError("closure_count")


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class NoOrderClosedAuditRecord:
    """Identity-free survivor for one terminal, fully enumerated no-order run."""

    opened_at: CanonicalTimestamp
    closed_at: CanonicalTimestamp
    latest_review_window_end: date
    interaction_count: int
    interaction_precisions: tuple[TimestampPrecision, ...]
    search_trigger: SearchTriggerType
    identifiers_required: int
    identifiers_attempted: int
    identifiers_completed: int
    enumeration_complete: bool
    system_workflow_before_close: WorkflowState
    reasons: tuple[SalesCreditReason, ...]
    concise_note: ClosedNoteCode
    search_adapter_version: str
    search_run_schema_version: str
    rule_pack_version: str
    retention_policy_version: str = "sales-credit-retention-elapsed-90d/v1"
    schema_version: str = "sales-credit-no-order-closed-audit/v1"

    HASH_DOMAIN: ClassVar[str] = "sales-credit-no-order-closed-audit/v1"

    def __post_init__(self) -> None:
        if type(self.opened_at) is not CanonicalTimestamp:
            raise RetentionDecisionError("no_order_record_opened_at")
        if type(self.closed_at) is not CanonicalTimestamp:
            raise RetentionDecisionError("no_order_record_closed_at")
        if (self.closed_at.epoch_seconds, self.closed_at.nanosecond) < (
            self.opened_at.epoch_seconds,
            self.opened_at.nanosecond,
        ):
            raise RetentionDecisionError("no_order_record_time_order")
        if type(self.latest_review_window_end) is not date:
            raise RetentionDecisionError("no_order_record_review_window")
        if business_local_date(self.closed_at) <= self.latest_review_window_end:
            raise RetentionDecisionError("no_order_record_review_window")
        if type(self.interaction_count) is not int or not (
            1 <= self.interaction_count <= 1_000_000
        ):
            raise RetentionDecisionError("no_order_record_interaction_count")
        if type(self.interaction_precisions) is not tuple or any(
            type(item) is not TimestampPrecision
            for item in self.interaction_precisions
        ):
            raise RetentionDecisionError("no_order_record_precisions")
        expected_precisions = tuple(
            sorted(set(self.interaction_precisions), key=lambda item: item.value)
        )
        if (
            not self.interaction_precisions
            or self.interaction_precisions != expected_precisions
            or len(self.interaction_precisions) > self.interaction_count
        ):
            raise RetentionDecisionError("no_order_record_precisions")
        if type(self.search_trigger) is not SearchTriggerType:
            raise RetentionDecisionError("no_order_record_trigger")
        counts = (
            self.identifiers_required,
            self.identifiers_attempted,
            self.identifiers_completed,
        )
        if any(type(value) is not int or value <= 0 for value in counts):
            raise RetentionDecisionError("no_order_record_identifier_counts")
        if not (
            self.identifiers_required
            == self.identifiers_attempted
            == self.identifiers_completed
        ):
            raise RetentionDecisionError("no_order_record_identifier_counts")
        if type(self.enumeration_complete) is not bool or not self.enumeration_complete:
            raise RetentionDecisionError("no_order_record_enumeration")
        if self.system_workflow_before_close is not WorkflowState.REVIEW_WINDOW_CLOSED_NO_ORDER:
            raise RetentionDecisionError("no_order_record_workflow")
        if self.reasons != (SalesCreditReason.NO_ORDER_WINDOW_CLOSED,):
            raise RetentionDecisionError("no_order_record_reasons")
        if self.concise_note is not ClosedNoteCode.REVIEW_WINDOW_CLOSED_NO_ORDER:
            raise RetentionDecisionError("no_order_record_note")
        if self.search_adapter_version != OrderSearchRun.ADAPTER_VERSION:
            raise RetentionDecisionError("no_order_record_adapter")
        if self.search_run_schema_version != "sales-credit-order-search-run/v1":
            raise RetentionDecisionError("no_order_record_search_schema")
        if self.rule_pack_version != SALES_CREDIT_RULE_PACK_VERSION:
            raise RetentionDecisionError("no_order_record_rule_version")
        if self.retention_policy_version != "sales-credit-retention-elapsed-90d/v1":
            raise RetentionDecisionError("no_order_record_retention_version")
        if self.schema_version != "sales-credit-no-order-closed-audit/v1":
            raise RetentionDecisionError("no_order_record_schema")

    def to_dict(self) -> dict[str, object]:
        return {
            "closed_at": self.closed_at.value,
            "concise_note": self.concise_note.value,
            "enumeration_complete": self.enumeration_complete,
            "identifiers_attempted": self.identifiers_attempted,
            "identifiers_completed": self.identifiers_completed,
            "identifiers_required": self.identifiers_required,
            "interaction_count": self.interaction_count,
            "interaction_precisions": [
                item.value for item in self.interaction_precisions
            ],
            "latest_review_window_end": self.latest_review_window_end.isoformat(),
            "opened_at": self.opened_at.value,
            "reasons": [reason.value for reason in self.reasons],
            "retention_policy_version": self.retention_policy_version,
            "rule_pack_version": self.rule_pack_version,
            "schema_version": self.schema_version,
            "search_adapter_version": self.search_adapter_version,
            "search_run_schema_version": self.search_run_schema_version,
            "search_trigger": self.search_trigger.value,
            "system_workflow_before_close": self.system_workflow_before_close.value,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "NoOrderClosedAuditRecord(<minimized>)"


@dataclass(frozen=True, slots=True)
class NoOrderClosureProjection:
    """Verified no-order survivor plus exact active-detail removal counts."""

    record: NoOrderClosedAuditRecord
    interactions_removed: int
    identifiers_removed: int
    native_result_sets_removed: int

    def __post_init__(self) -> None:
        if type(self.record) is not NoOrderClosedAuditRecord:
            raise RetentionDecisionError("no_order_projection_record")
        for value in (
            self.interactions_removed,
            self.identifiers_removed,
            self.native_result_sets_removed,
        ):
            if type(value) is not int or value < 0:
                raise RetentionDecisionError("no_order_projection_count")
        if self.interactions_removed != self.record.interaction_count:
            raise RetentionDecisionError("no_order_projection_count")
        if (
            self.identifiers_removed != self.record.identifiers_required
            or self.native_result_sets_removed != self.record.identifiers_required
        ):
            raise RetentionDecisionError("no_order_projection_count")


@dataclass(frozen=True, slots=True, repr=False, kw_only=True)
class NoOrderClosureResult(NoOrderStateResult):
    """Identity-free terminal ledger result and minimized replay survivor."""

    receipt_id: str
    projection: NoOrderClosureProjection
    replayed: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.receipt_id) is not str
            or not self.receipt_id.startswith("SYN-NO-ORDER-CLOSURE-")
            or not self.receipt_id.removeprefix(
                "SYN-NO-ORDER-CLOSURE-"
            ).isdigit()
        ):
            raise RetentionDecisionError("no_order_closure_result_receipt")
        if type(self.projection) is not NoOrderClosureProjection:
            raise RetentionDecisionError("no_order_closure_result_projection")
        if type(self.replayed) is not bool:
            raise RetentionDecisionError("no_order_closure_result_replayed")

    def __repr__(self) -> str:
        return "NoOrderClosureResult(<minimized>)"


def _sorted_precisions(
    interactions: tuple[InteractionRecord, ...],
) -> tuple[TimestampPrecision, ...]:
    return tuple(
        sorted(
            {interaction.effective_precision for interaction in interactions},
            key=lambda item: item.value,
        )
    )


def build_no_order_closure_projection(
    *,
    transition: _NoOrderTransitionAuthority,
) -> NoOrderClosureProjection:
    """Minimize one governed terminal no-order root without inventing a case."""

    if type(transition) is not _NoOrderTransitionAuthority:
        raise RetentionDecisionError("no_order_transition_type")
    if (
        transition.workflow_state
        is not WorkflowState.REVIEW_WINDOW_CLOSED_NO_ORDER
    ):
        raise RetentionDecisionError("no_order_transition_not_terminal")
    try:
        transition._consume_terminal_projection_authority()
    except (NoOrderLedgerError, TypeError, ValueError):
        raise RetentionDecisionError("no_order_transition_invalid") from None
    run = transition.run

    derivation_failed = False
    opened_at: CanonicalTimestamp | None = None
    latest_review_window_end: date | None = None
    interaction_precisions: tuple[TimestampPrecision, ...] | None = None
    search_adapter_version: str | None = None
    try:
        interaction_ids = tuple(
            interaction.interaction_id for interaction in run.interactions
        )
        plan = plan_discovery(
            email_values=tuple(
                interaction.email
                for interaction in run.interactions
                if interaction.email is not None
            ),
            phone_values=tuple(
                interaction.phone
                for interaction in run.interactions
                if interaction.phone is not None
            ),
        )
        completed_date = business_local_date(run.completed_at)
        review_window_closed = all(
            completed_date > interaction.review_window_end
            for interaction in run.interactions
        )
        expected_result = combine_search_results(
            plan=plan,
            results=run.native_result_sets,
            review_window_closed=review_window_closed,
        )
        opened_at = min(
            (interaction.effective_at for interaction in run.interactions),
            key=lambda item: (item.epoch_seconds, item.nanosecond),
        )
        latest_review_window_end = max(
            interaction.review_window_end for interaction in run.interactions
        )
        interaction_precisions = _sorted_precisions(run.interactions)
        search_adapter_version = run.adapter.version
    except (AttributeError, OverflowError, TypeError, ValueError):
        derivation_failed = True
        interaction_ids = ()
        plan = None
        expected_result = None
    if (
        derivation_failed
        or plan is None
        or expected_result is None
        or opened_at is None
        or latest_review_window_end is None
        or interaction_precisions is None
        or search_adapter_version is None
    ):
        raise RetentionDecisionError("no_order_run_invalid") from None
    if (
        run.interaction_ids != interaction_ids
        or run.attempted_identifiers != plan.identifiers
        or run.result != expected_result
    ):
        raise RetentionDecisionError("no_order_run_derivation_parity")
    if (
        not expected_result.enumeration_complete
        or expected_result.identifiers_required <= 0
        or expected_result.identifiers_attempted
        != expected_result.identifiers_required
        or expected_result.identifiers_completed
        != expected_result.identifiers_required
    ):
        raise RetentionDecisionError("no_order_run_incomplete")
    if (
        expected_result.outcome
        is not DiscoveryOutcome.REVIEW_WINDOW_CLOSED_NO_ORDER
        or expected_result.order_ids
        or not review_window_closed
    ):
        raise RetentionDecisionError("no_order_run_not_terminal")

    record = NoOrderClosedAuditRecord(
        opened_at=opened_at,
        closed_at=run.completed_at,
        latest_review_window_end=latest_review_window_end,
        interaction_count=len(run.interactions),
        interaction_precisions=interaction_precisions,
        search_trigger=run.trigger,
        identifiers_required=expected_result.identifiers_required,
        identifiers_attempted=expected_result.identifiers_attempted,
        identifiers_completed=expected_result.identifiers_completed,
        enumeration_complete=expected_result.enumeration_complete,
        system_workflow_before_close=WorkflowState.REVIEW_WINDOW_CLOSED_NO_ORDER,
        reasons=expected_result.reasons,
        concise_note=ClosedNoteCode.REVIEW_WINDOW_CLOSED_NO_ORDER,
        search_adapter_version=search_adapter_version,
        search_run_schema_version=run.schema_version,
        rule_pack_version=SALES_CREDIT_RULE_PACK_VERSION,
    )
    binding = record.hash_binding()
    if binding.canonical_bytes != record.canonical_bytes():
        raise RetentionDecisionError("no_order_hash_verification")
    return NoOrderClosureProjection(
        record=record,
        interactions_removed=len(run.interactions),
        identifiers_removed=len(run.attempted_identifiers),
        native_result_sets_removed=len(run.native_result_sets),
    )


def build_closure_projection(
    *,
    case: SalesCreditCase,
    interactions: tuple[InteractionRecord, ...],
    evidence: tuple[EvidenceEvent, ...],
    evaluation: SalesCreditEvaluation,
    closed_at: CanonicalTimestamp,
) -> ClosureProjection:
    """Build and hash-verify the sole long-lived record from active detail."""

    if type(case) is not SalesCreditCase:
        raise RetentionDecisionError("closure_case_type")
    if type(interactions) is not tuple or any(
        type(item) is not InteractionRecord for item in interactions
    ):
        raise RetentionDecisionError("closure_interactions_type")
    if type(evidence) is not tuple or any(type(item) is not EvidenceEvent for item in evidence):
        raise RetentionDecisionError("closure_evidence_type")
    if type(evaluation) is not SalesCreditEvaluation:
        raise RetentionDecisionError("closure_evaluation_type")
    if type(closed_at) is not CanonicalTimestamp:
        raise RetentionDecisionError("closure_timestamp_type")
    closed_key = (closed_at.epoch_seconds, closed_at.nanosecond)
    updated_key = (case.updated_at.epoch_seconds, case.updated_at.nanosecond)
    if closed_key < updated_key:
        raise RetentionDecisionError("closure_time_regression")
    if (
        evaluation.order_id != case.order_id
        or evaluation.evaluation_id not in case.evaluation_ids
        or evaluation.snapshot_id not in case.snapshot_ids
        or evaluation.attribution.classification is not case.attribution
        or evaluation.value.status is not case.order_value_status
        or evaluation.value.placed_value != case.placed_value
    ):
        raise RetentionDecisionError("closure_evaluation_parity")
    system_workflow_before_close = evaluation.workflow_state
    ordered_reasons = evaluation.reasons

    interaction_ids = tuple(
        sorted((item.interaction_id.value for item in interactions))
    )
    if interaction_ids != tuple(item.value for item in case.interaction_ids):
        raise RetentionDecisionError("closure_interaction_parity")
    evidence_ids = tuple(sorted(item.evidence_id.value for item in evidence))
    if evidence_ids != tuple(item.value for item in case.evidence_ids):
        raise RetentionDecisionError("closure_evidence_parity")
    if case.manager_outcome is None:
        if system_workflow_before_close not in _TERMINAL_WITHOUT_HUMAN:
            raise RetentionDecisionError("closure_missing_outcome")
        if case.workflow_state not in {
            system_workflow_before_close,
            WorkflowState.CLOSED,
        }:
            raise RetentionDecisionError("closure_system_workflow_mismatch")
        human_outcome: HumanOutcomeType | None = None
    else:
        if case.workflow_state is not WorkflowState.CLOSED:
            raise RetentionDecisionError("closure_human_workflow")
        if system_workflow_before_close not in _MANAGER_OUTCOME_WORKFLOWS:
            raise RetentionDecisionError("closure_human_authority")
        human_outcome = case.manager_outcome.outcome

    record_failed = False
    record: ClosedAuditRecord | None = None
    try:
        record = ClosedAuditRecord(
            order_id=case.order_id,
            opened_at=case.created_at,
            closed_at=closed_at,
            interaction_precisions=_sorted_precisions(interactions),
            system_workflow_before_close=system_workflow_before_close,
            attribution=case.attribution,
            order_value_status=case.order_value_status,
            evidence_source_types=tuple(
                sorted(
                    {item.source_type for item in evidence},
                    key=lambda item: item.value,
                )
            ),
            evidence_classifications=tuple(
                sorted(
                    {item.classification for item in evidence},
                    key=lambda item: item.value,
                )
            ),
            reasons=ordered_reasons,
            human_outcome=human_outcome,
            human_decided_at=(
                None if case.manager_outcome is None else case.manager_outcome.decided_at
            ),
            human_recorded_at=(
                None if case.manager_outcome is None else case.manager_outcome.recorded_at
            ),
            decision_actor=(
                None if case.manager_outcome is None else case.manager_outcome.actor
            ),
            approved_amount=(
                None if case.manager_outcome is None else case.manager_outcome.approved_amount
            ),
            controlled_reason=(
                None if case.manager_outcome is None else case.manager_outcome.controlled_reason
            ),
            concise_note=(
                ClosedNoteCode.HUMAN_OUTCOME_RECORDED
                if case.manager_outcome is not None
                else (
                    ClosedNoteCode.CANCELED_NO_REPLACEMENT
                    if system_workflow_before_close
                    is WorkflowState.CANCELED_NO_REPLACEMENT
                    else ClosedNoteCode.AUTOMATIC_CLASSIFICATION_CLOSED
                )
            ),
            rule_pack_version=SALES_CREDIT_RULE_PACK_VERSION,
        )
    except SalesCreditValidationError:
        record_failed = True
    if record_failed or record is None:
        raise RetentionDecisionError("closure_record_invalid") from None
    binding = record.hash_binding()
    if binding.canonical_bytes != record.canonical_bytes():
        raise RetentionDecisionError("closure_hash_verification")
    return ClosureProjection(
        record=record,
        interactions_removed=len(case.interaction_ids),
        snapshots_removed=len(case.snapshot_ids),
        evidence_removed=len(case.evidence_ids),
        evaluations_removed=len(case.evaluation_ids),
    )


def purge_eligible(
    *,
    closed_at: CanonicalTimestamp,
    now: CanonicalTimestamp,
) -> bool:
    """Return whether exact elapsed time has reached the 90-day boundary."""

    if type(closed_at) is not CanonicalTimestamp or type(now) is not CanonicalTimestamp:
        raise RetentionDecisionError("purge_timestamp_type")
    elapsed_seconds = now.epoch_seconds - closed_at.epoch_seconds
    elapsed_nanoseconds = now.nanosecond - closed_at.nanosecond
    return (elapsed_seconds, elapsed_nanoseconds) >= (RETENTION_SECONDS, 0)


__all__ = [
    "ClosureProjection",
    "NoOrderClosedAuditRecord",
    "NoOrderClosureResult",
    "NoOrderClosureProjection",
    "RETENTION_SECONDS",
    "RetentionDecisionError",
    "build_closure_projection",
    "build_no_order_closure_projection",
    "purge_eligible",
]
