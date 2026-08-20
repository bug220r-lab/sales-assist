from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import date
from decimal import Decimal

from synthetic_sales_assist.domain.canonical import canonical_json_bytes, domain_hash
from synthetic_sales_assist.domain.identities import (
    EvaluationId,
    EvidenceId,
    InteractionId,
    OrderId,
    RepId,
    RunId,
    SnapshotId,
)
from synthetic_sales_assist.domain.numeric import CURRENCY_REGISTRY_VERSION, Money
from synthetic_sales_assist.domain.records import VersionBinding
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.sales_credit.models import (
    AttributionClassification,
    AttributionDecision,
    CustomerContinuityStatus,
    EvidenceDirection,
    EvidenceEvent,
    EvidenceIdentifierKind,
    EvidenceSourceType,
    EvidenceTimingRelation,
    HumanOutcomeType,
    InteractionRecord,
    ManagerOutcome,
    MaterialChangeKind,
    OrderValueStatus,
    ProductContinuityStatus,
    ReplacementDecision,
    ReplacementStatus,
    SalesCreditEffect,
    SalesCreditEvaluation,
    SalesCreditFact,
    SalesCreditRule,
    SalesCreditValidation,
    SalesCreditCase,
    SalesCreditReason,
    TimestampPrecision,
    WorkflowState,
    ValueDecision,
)
from synthetic_sales_assist.sales_credit.retention import (
    RETENTION_SECONDS,
    ClosureProjection,
    RetentionDecisionError,
    build_closure_projection,
    purge_eligible,
)


def ts(value: str) -> CanonicalTimestamp:
    return CanonicalTimestamp(value)


def usd(value: str) -> Money:
    return Money(
        Decimal(value),
        "USD",
        CURRENCY_REGISTRY_VERSION,
        2,
    )


def interaction() -> InteractionRecord:
    return InteractionRecord(
        interaction_id=InteractionId("SYN-INTERACTION-RETENTION-001"),
        source_ref=EvidenceId("SYN-EVIDENCE-INTERACTION-SOURCE-001"),
        recorded_at=ts("2026-08-01T14:00:00Z"),
        timestamp_precision=TimestampPrecision.EXACT,
        review_window_start=date(2026, 8, 1),
        review_window_end=date(2026, 8, 15),
        workflow_state=WorkflowState.AWAITING_SOURCE_REVIEW,
        provenance=VersionBinding(
            "sales_credit_interaction_source",
            "sales-credit-interaction-source/v1",
        ),
        email="retention@example.test",
        phone="212-555-0101",
        active_notes="synthetic: remove this interaction note",
    )


def evidence() -> EvidenceEvent:
    identifier_ref = domain_hash(
        EvidenceEvent.IDENTIFIER_REF_DOMAIN,
        canonical_json_bytes(
            {"kind": "EMAIL", "reference": "SYN-EVIDENCE-IDENTIFIER-001"},
            expected_members={"kind", "reference"},
        ),
    )
    return EvidenceEvent(
        evidence_id=EvidenceId("SYN-EVIDENCE-CONTACT-001"),
        order_id=OrderId("SYN-ORDER-RETENTION-001"),
        interaction_id=interaction().interaction_id,
        source_type=EvidenceSourceType.SYNTHETIC_CONVERSATION,
        source_ref=EvidenceId("SYN-EVIDENCE-CONVERSATION-SOURCE-001"),
        occurred_at=ts("2026-08-01T13:00:00Z"),
        timestamp_precision=TimestampPrecision.EXACT,
        direction=EvidenceDirection.TWO_WAY,
        target_rep_participated=True,
        connected=True,
        two_way=True,
        identifier_kind=EvidenceIdentifierKind.EMAIL,
        matched_identifier_ref=identifier_ref,
        timing=EvidenceTimingRelation.PRE_ORDER,
        active_excerpt="synthetic: remove this evidence excerpt",
    )


def outcome() -> ManagerOutcome:
    return ManagerOutcome(
        occurrence_id=EvidenceId("SYN-EVIDENCE-MANAGER-OUTCOME-001"),
        outcome=HumanOutcomeType.PARTIAL,
        decided_at=ts("2026-08-02T12:00:00Z"),
        actor=RepId("SYN-REP-MANAGER-001"),
        recorded_at=ts("2026-08-02T12:01:00Z"),
        approved_amount=usd("25.00"),
        controlled_reason=SalesCreditReason.AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW,
        active_note="synthetic: remove manager note body",
    )


def case_with_human_outcome() -> SalesCreditCase:
    return SalesCreditCase(
        order_id=OrderId("SYN-ORDER-RETENTION-001"),
        interaction_ids=(interaction().interaction_id,),
        snapshot_ids=(SnapshotId("SYN-SNAPSHOT-RETENTION-001"),),
        evidence_ids=(evidence().evidence_id,),
        evaluation_ids=(EvaluationId("SYN-EVALUATION-RETENTION-001"),),
        attribution=AttributionClassification.UNASSIGNED_WEB,
        order_value_status=OrderValueStatus.CHANGED_REVIEW,
        placed_value=None,
        workflow_state=WorkflowState.CLOSED,
        replacement_parent=None,
        manager_outcome=outcome(),
        created_at=ts("2026-08-01T14:00:00Z"),
        updated_at=ts("2026-08-02T12:01:00Z"),
        active_note="synthetic: remove active case note",
    )


def terminal_case() -> SalesCreditCase:
    return SalesCreditCase(
        order_id=OrderId("SYN-ORDER-TERMINAL-001"),
        interaction_ids=(),
        snapshot_ids=(SnapshotId("SYN-SNAPSHOT-TERMINAL-001"),),
        evidence_ids=(),
        evaluation_ids=(EvaluationId("SYN-EVALUATION-TERMINAL-001"),),
        attribution=AttributionClassification.UNKNOWN,
        order_value_status=OrderValueStatus.UNKNOWN,
        placed_value=None,
        workflow_state=WorkflowState.CANCELED_NO_REPLACEMENT,
        replacement_parent=None,
        manager_outcome=None,
        created_at=ts("2026-08-01T00:00:00Z"),
        updated_at=ts("2026-08-10T00:00:00Z"),
    )


def human_evaluation() -> SalesCreditEvaluation:
    active_case = case_with_human_outcome()
    return SalesCreditEvaluation(
        evaluation_id=active_case.evaluation_ids[0],
        order_id=active_case.order_id,
        snapshot_id=active_case.snapshot_ids[0],
        workflow_state=WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
        attribution=AttributionDecision(AttributionClassification.UNASSIGNED_WEB, True),
        value=ValueDecision(
            OrderValueStatus.CHANGED_REVIEW,
            None,
            None,
            (MaterialChangeKind.REFUND,),
        ),
        replacement=ReplacementDecision(
            ReplacementStatus.NOT_APPLICABLE,
            CustomerContinuityStatus.UNKNOWN,
            ProductContinuityStatus.UNKNOWN,
        ),
        reasons=(
            SalesCreditReason.AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW,
            SalesCreditReason.MATERIAL_CHANGE_DETECTED,
        ),
        human_review_required=True,
        supplied_facts=(SalesCreditFact.MATERIAL_CHANGES, SalesCreditFact.SNAPSHOT),
        validations=(SalesCreditValidation.SNAPSHOT_ACCEPTED,),
        rules_evaluated=(
            SalesCreditRule.AMBIGUITY_ROUTING,
            SalesCreditRule.MATERIAL_CHANGE,
            SalesCreditRule.SNAPSHOT_VALIDATION,
        ),
        rules_fired=(
            SalesCreditRule.AMBIGUITY_ROUTING,
            SalesCreditRule.MATERIAL_CHANGE,
        ),
        persistence_effects=(
            SalesCreditEffect.HUMAN_REVIEW_REQUIRED,
            SalesCreditEffect.NO_PERSISTENCE_MILESTONE_2,
        ),
    )


def terminal_evaluation() -> SalesCreditEvaluation:
    active_case = terminal_case()
    return SalesCreditEvaluation(
        evaluation_id=active_case.evaluation_ids[0],
        order_id=active_case.order_id,
        snapshot_id=active_case.snapshot_ids[0],
        workflow_state=WorkflowState.CANCELED_NO_REPLACEMENT,
        attribution=AttributionDecision(AttributionClassification.UNKNOWN, False),
        value=ValueDecision(OrderValueStatus.UNKNOWN, None, None, ()),
        replacement=ReplacementDecision(
            ReplacementStatus.WINDOW_EXPIRED,
            CustomerContinuityStatus.UNKNOWN,
            ProductContinuityStatus.UNKNOWN,
            search_run_id=RunId("SYN-RUN-RETENTION-REPLACEMENT-001"),
            enumeration_complete=True,
        ),
        reasons=(
            SalesCreditReason.CANCELED_ORDER_ZERO_ACTIVE_VALUE,
            SalesCreditReason.REPLACEMENT_WINDOW_EXPIRED,
        ),
        human_review_required=False,
        supplied_facts=(SalesCreditFact.ORDER_LIFECYCLE, SalesCreditFact.SNAPSHOT),
        validations=(SalesCreditValidation.SNAPSHOT_ACCEPTED,),
        rules_evaluated=(
            SalesCreditRule.CANCELLATION,
            SalesCreditRule.REPLACEMENT,
            SalesCreditRule.SNAPSHOT_VALIDATION,
        ),
        rules_fired=(SalesCreditRule.CANCELLATION, SalesCreditRule.REPLACEMENT),
        persistence_effects=(
            SalesCreditEffect.ACTIVE_CASE_CLASSIFICATION,
            SalesCreditEffect.NO_PERSISTENCE_MILESTONE_2,
            SalesCreditEffect.ZERO_ACTIVE_VALUE,
        ),
    )


class ClosureProjectionTests(unittest.TestCase):
    def test_human_closure_preserves_only_minimized_governed_metadata(self) -> None:
        active_case = case_with_human_outcome()
        interaction_value = interaction()
        evidence_value = evidence()
        projection = build_closure_projection(
            case=active_case,
            interactions=(interaction_value,),
            evidence=(evidence_value,),
            evaluation=human_evaluation(),
            closed_at=ts("2026-08-03T00:00:00Z"),
        )
        record = projection.record
        self.assertEqual(
            (
                projection.interactions_removed,
                projection.snapshots_removed,
                projection.evidence_removed,
                projection.evaluations_removed,
            ),
            (1, 1, 1, 1),
        )
        self.assertIs(record.human_outcome, HumanOutcomeType.PARTIAL)
        self.assertEqual(record.approved_amount, usd("25.00"))
        self.assertEqual(record.decision_actor, RepId("SYN-REP-MANAGER-001"))
        self.assertEqual(
            tuple(item.value for item in record.reasons),
            (
                "AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW",
                "MATERIAL_CHANGE_DETECTED",
            ),
        )
        self.assertEqual(record.hash_binding().domain, "sales-credit-closed-audit/v1")
        self.assertEqual(
            record.hash_binding().canonical_bytes,
            record.canonical_bytes(),
        )

        serialized = record.canonical_bytes().decode("utf-8")
        prohibited_survivors = (
            interaction_value.email,
            interaction_value.phone,
            interaction_value.interaction_id.value,
            interaction_value.source_ref.value,
            evidence_value.evidence_id.value,
            evidence_value.source_ref.value,
            "remove this interaction note",
            "remove this evidence excerpt",
            "remove manager note body",
            "remove active case note",
            active_case.snapshot_ids[0].value,
            active_case.evaluation_ids[0].value,
        )
        for survivor in prohibited_survivors:
            with self.subTest(survivor=survivor):
                self.assertNotIn(survivor, serialized)
        decoded = json.loads(serialized)
        self.assertNotIn("contacts", decoded)
        self.assertNotIn("snapshots", decoded)
        self.assertNotIn("line_items", decoded)
        self.assertNotIn("notes", decoded)

    def test_terminal_system_closure_requires_no_fabricated_human_outcome(self) -> None:
        active_case = terminal_case()
        projection = build_closure_projection(
            case=active_case,
            interactions=(),
            evidence=(),
            evaluation=terminal_evaluation(),
            closed_at=ts("2026-08-16T00:00:00Z"),
        )
        record = projection.record
        self.assertIsNone(record.human_outcome)
        self.assertIsNone(record.human_decided_at)
        self.assertIsNone(record.human_recorded_at)
        self.assertIsNone(record.decision_actor)
        self.assertIsNone(record.approved_amount)

    def test_missing_human_outcome_is_rejected_for_nonterminal_system_state(self) -> None:
        active_case = replace(
            case_with_human_outcome(),
            manager_outcome=None,
            workflow_state=WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
            updated_at=ts("2026-08-02T11:59:00Z"),
        )
        with self.assertRaisesRegex(RetentionDecisionError, "closure_missing_outcome"):
            build_closure_projection(
                case=active_case,
                interactions=(interaction(),),
                evidence=(evidence(),),
                evaluation=human_evaluation(),
                closed_at=ts("2026-08-16T00:00:00Z"),
            )

    def test_identity_parity_is_exact_and_failure_does_not_create_a_projection(self) -> None:
        active_case = case_with_human_outcome()
        for interactions, evidence_values, code in (
            ((), (evidence(),), "closure_interaction_parity"),
            ((interaction(),), (), "closure_evidence_parity"),
            ((interaction(), interaction()), (evidence(),), "closure_interaction_parity"),
        ):
            with self.subTest(code=code):
                with self.assertRaisesRegex(RetentionDecisionError, code):
                    build_closure_projection(
                        case=active_case,
                        interactions=interactions,
                        evidence=evidence_values,
                        evaluation=human_evaluation(),
                        closed_at=ts("2026-08-03T00:00:00Z"),
                    )

    def test_closure_time_cannot_precede_latest_active_case_state(self) -> None:
        active_case = case_with_human_outcome()
        with self.assertRaises(RetentionDecisionError):
            build_closure_projection(
                case=active_case,
                interactions=(interaction(),),
                evidence=(evidence(),),
                evaluation=human_evaluation(),
                closed_at=ts("2026-08-02T00:00:00Z"),
            )

    def test_projection_is_deeply_immutable_and_strictly_typed(self) -> None:
        projection = build_closure_projection(
            case=terminal_case(),
            interactions=(),
            evidence=(),
            evaluation=terminal_evaluation(),
            closed_at=ts("2026-08-16T00:00:00Z"),
        )
        with self.assertRaises(FrozenInstanceError):
            projection.interactions_removed = 2  # type: ignore[misc]
        with self.assertRaisesRegex(RetentionDecisionError, "closure_count"):
            ClosureProjection(
                record=projection.record,
                interactions_removed=True,  # type: ignore[arg-type]
                snapshots_removed=0,
                evidence_removed=0,
                evaluations_removed=0,
            )
        with self.assertRaisesRegex(RetentionDecisionError, "closure_evaluation_type"):
            build_closure_projection(
                case=terminal_case(),
                interactions=(),
                evidence=(),
                evaluation=[],  # type: ignore[arg-type]
                closed_at=ts("2026-08-16T00:00:00Z"),
            )


class PurgeBoundaryTests(unittest.TestCase):
    def test_exact_elapsed_ninety_day_nanosecond_boundary(self) -> None:
        closed = ts("2026-01-01T00:00:00.000000001Z")
        before = ts("2026-04-01T00:00:00Z")
        exact = ts("2026-04-01T00:00:00.000000001Z")
        self.assertEqual(RETENTION_SECONDS, 7_776_000)
        self.assertFalse(purge_eligible(closed_at=closed, now=before))
        self.assertTrue(purge_eligible(closed_at=closed, now=exact))
        self.assertTrue(
            purge_eligible(
                closed_at=closed,
                now=ts("2026-04-01T00:00:00.000000002Z"),
            )
        )

    def test_elapsed_policy_is_not_local_calendar_day_arithmetic(self) -> None:
        closed = ts("2026-03-01T12:00:00-05:00")
        self.assertFalse(
            purge_eligible(
                closed_at=closed,
                now=ts("2026-05-30T16:59:59.999999999Z"),
            )
        )
        self.assertTrue(
            purge_eligible(
                closed_at=closed,
                now=ts("2026-05-30T17:00:00Z"),
            )
        )

    def test_time_before_closure_is_not_eligible_and_types_are_exact(self) -> None:
        self.assertFalse(
            purge_eligible(
                closed_at=ts("2026-08-02T00:00:00Z"),
                now=ts("2026-08-01T00:00:00Z"),
            )
        )
        with self.assertRaisesRegex(RetentionDecisionError, "purge_timestamp_type"):
            purge_eligible(
                closed_at="2026-08-01T00:00:00Z",  # type: ignore[arg-type]
                now=ts("2026-11-01T00:00:00Z"),
            )


if __name__ == "__main__":
    unittest.main()
