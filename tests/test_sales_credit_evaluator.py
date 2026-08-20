from __future__ import annotations

import dataclasses
import unittest
from datetime import date
from decimal import Decimal

from synthetic_sales_assist.domain.identities import (
    CustomerId,
    EvaluationId,
    EvidenceId,
    InteractionId,
    OrderId,
    RunId,
    SkuId,
    SnapshotId,
)
from synthetic_sales_assist.domain.numeric import CURRENCY_REGISTRY_VERSION, Money, Quantity
from synthetic_sales_assist.domain.records import VersionBinding
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.sales_credit.discovery import (
    IdentifierSearchResult,
    OrderSearchRun,
    SearchCompleteness,
    SearchIdentifier,
    SearchIdentifierKind,
)
from synthetic_sales_assist.sales_credit.evaluator import (
    SalesCreditEvaluationError,
    classify_evidence,
    classify_evidence_event,
    derive_replacement_facts,
    evidence_identifier_binding,
    evaluate_sales_credit,
)
from synthetic_sales_assist.sales_credit.models import (
    AttributionClassification,
    CustomerContinuityStatus,
    EvidenceClassification,
    EvidenceDirection,
    EvidenceEvent,
    EvidenceIdentifierKind,
    EvidenceSourceType,
    EvidenceTimingRelation,
    InteractionRecord,
    LineItemSnapshot,
    MaterialChange,
    MaterialChangeKind,
    NotesScanStatus,
    OrderLifecycleStatus,
    OrderSnapshot,
    OrderValueStatus,
    ProductContinuityStatus,
    ReplacementCandidateInput,
    ReplacementStatus,
    SALES_CREDIT_RULE_PACK_VERSION,
    SalesCreditEffect,
    SalesCreditReason,
    SalesCreditRule,
    SalesCreditValidation,
    SearchTriggerType,
    SnapshotStatus,
    TimestampPrecision,
    WorkflowState,
    order_provenance_binding,
)


KNOWN_OTHER_REPS = frozenset({"synthetic_other_rep"})
ORDER = OrderId("SYN-ORDER-SC-EVAL-0001")
REPLACEMENT_ORDER = OrderId("SYN-ORDER-SC-EVAL-0002")
REPLACEMENT_ORDER_2 = OrderId("SYN-ORDER-SC-EVAL-0003")
ORDER_AT = CanonicalTimestamp("2026-08-10T17:00:00Z")
CANCELED_AT = CanonicalTimestamp("2026-08-11T16:00:00Z")
EVALUATED_AT = CanonicalTimestamp("2026-08-12T16:00:00Z")
CAPTURED_AT = CanonicalTimestamp("2026-08-12T16:00:00Z")
_DEFAULT = object()


def money(amount: str = "100.00") -> Money:
    return Money(
        Decimal(amount),
        "USD",
        CURRENCY_REGISTRY_VERSION,
        2,
    )


def line(
    index: int,
    *,
    es: str | None = None,
    mfg: str | None = None,
    raw_line_rep: str | None = None,
    quantity: int = 1,
    line_value: str = "10.00",
) -> LineItemSnapshot:
    return LineItemSnapshot.create(
        line_id=EvidenceId(f"SYN-EVIDENCE-SC-LINE-{index:04d}"),
        sku_id=SkuId(f"SYN-SKU-SC-EVAL-{index:04d}"),
        quantity=Quantity(quantity),
        line_value=money(line_value),
        raw_es_number=None if es is None else f"synthetic: {es}",
        canonical_es_number=None if es is None else es.lstrip("0"),
        raw_mfg_oe_number=None if mfg is None else f"synthetic: {mfg}",
        canonical_mfg_oe_number=None if mfg is None else mfg.upper(),
        raw_line_rep=raw_line_rep,
    )


def change(index: int, kind: MaterialChangeKind) -> MaterialChange:
    return MaterialChange(
        EvidenceId(f"SYN-EVIDENCE-SC-CHANGE-{index:04d}"),
        kind,
        kind.is_material,
    )


def snapshot(
    *,
    snapshot_index: int = 1,
    order_id: OrderId | None = ORDER,
    source_ref: EvidenceId | None | object = _DEFAULT,
    extraction_status: SnapshotStatus = SnapshotStatus.VALID,
    lifecycle_status: OrderLifecycleStatus = OrderLifecycleStatus.ACTIVE,
    notes_scan_status: NotesScanStatus = NotesScanStatus.COMPLETE,
    placed_at: CanonicalTimestamp | None = ORDER_AT,
    placed_at_precision: TimestampPrecision | None = TimestampPrecision.EXACT,
    raw_order_status: str | None = "active",
    raw_order_rep: str | None = "target_rep",
    current_value: Money | None = None,
    placed_value: Money | None | object = _DEFAULT,
    customer_ids: tuple[CustomerId, ...] = (
        CustomerId("SYN-CUSTOMER-SC-EVAL-0001"),
    ),
    lines: tuple[LineItemSnapshot, ...] = (),
    material_changes: tuple[MaterialChange, ...] = (),
    provenance: object = _DEFAULT,
    canceled_at: CanonicalTimestamp | None = None,
    warnings: tuple[str, ...] = (),
    captured_at: CanonicalTimestamp = CAPTURED_AT,
) -> OrderSnapshot:
    current = money() if current_value is None else current_value
    placed = money() if placed_value is _DEFAULT else placed_value
    captured = captured_at
    parser = VersionBinding("sales_credit_parser", "sales-credit-parser/v1")
    ref = (
        EvidenceId(f"SYN-EVIDENCE-SC-ORDER-SOURCE-{snapshot_index:04d}")
        if source_ref is _DEFAULT
        else source_ref
    )
    source = (
        order_provenance_binding(source_ref=ref, captured_at=captured, parser=parser)
        if provenance is _DEFAULT and ref is not None
        else provenance
    )
    return OrderSnapshot(
        snapshot_id=SnapshotId(f"SYN-SNAPSHOT-SC-EVAL-{snapshot_index:04d}"),
        order_id=order_id,
        source_ref=ref,  # type: ignore[arg-type]
        captured_at=captured,
        parser=parser,
        extraction_status=extraction_status,
        lifecycle_status=lifecycle_status,
        notes_scan_status=notes_scan_status,
        placed_at=placed_at,
        placed_at_precision=placed_at_precision,
        raw_order_status=raw_order_status,
        raw_order_rep=raw_order_rep,
        current_value=current,
        placed_value=placed,  # type: ignore[arg-type]
        customer_ids=customer_ids,
        lines=lines,
        material_changes=material_changes,
        provenance=source,  # type: ignore[arg-type]
        canceled_at=canceled_at,
        warnings=warnings,
    )


def evidence(
    index: int,
    *,
    source_type: EvidenceSourceType = EvidenceSourceType.SYNTHETIC_CONVERSATION,
    occurred_at: str = "2026-08-10T16:00:00Z",
    precision: TimestampPrecision = TimestampPrecision.EXACT,
    direction: EvidenceDirection = EvidenceDirection.TWO_WAY,
    target: bool | None = True,
    connected: bool | None = False,
    two_way: bool | None = True,
    timing: EvidenceTimingRelation = EvidenceTimingRelation.PRE_ORDER,
    order_id: OrderId = ORDER,
    interaction_id: InteractionId = InteractionId("SYN-INTERACTION-SC-EVAL-0001"),
    identifier_kind: EvidenceIdentifierKind = EvidenceIdentifierKind.EMAIL,
) -> EvidenceEvent:
    return EvidenceEvent(
        evidence_id=EvidenceId(f"SYN-EVIDENCE-SC-EVENT-{index:04d}"),
        order_id=order_id,
        interaction_id=interaction_id,
        source_type=source_type,
        source_ref=EvidenceId(f"SYN-EVIDENCE-SC-SOURCE-{index:04d}"),
        occurred_at=CanonicalTimestamp(occurred_at),
        timestamp_precision=precision,
        direction=direction,
        target_rep_participated=target,
        connected=connected,
        two_way=two_way,
        identifier_kind=identifier_kind,
        matched_identifier_ref=evidence_identifier_binding(
            interaction_id=interaction_id,
            identifier_kind=identifier_kind,
        ),
        timing=timing,
    )


def interaction(
    interaction_id: InteractionId = InteractionId("SYN-INTERACTION-SC-EVAL-0001"),
    *,
    recorded_at: str = "2026-08-10T14:00:00Z",
    precision: TimestampPrecision = TimestampPrecision.EXACT,
    review_start: date = date(2026, 8, 10),
) -> InteractionRecord:
    return InteractionRecord(
        interaction_id=interaction_id,
        source_ref=EvidenceId("SYN-EVIDENCE-SC-INTERACTION-SOURCE-0001"),
        recorded_at=CanonicalTimestamp(recorded_at),
        timestamp_precision=precision,
        review_window_start=review_start,
        review_window_end=date.fromordinal(review_start.toordinal() + 14),
        workflow_state=WorkflowState.AWAITING_SOURCE_REVIEW,
        provenance=VersionBinding(
            "sales_credit_interaction_source",
            "sales-credit-interaction-source/v1",
        ),
        email="case@example.test",
    )


def replacement_input(
    candidate: OrderSnapshot,
    *,
    line_universe_complete: bool = True,
    possible_nonexact_continuity: bool = False,
) -> ReplacementCandidateInput:
    return ReplacementCandidateInput(
        snapshot=candidate,
        line_universe_complete=line_universe_complete,
        possible_nonexact_continuity=possible_nonexact_continuity,
    )


def replacement_search_run(
    *,
    order_ids: tuple[OrderId, ...] = (),
    interactions: tuple[InteractionRecord, ...] | None = None,
    trigger: SearchTriggerType = SearchTriggerType.REPLACEMENT_CHECK,
    completeness: SearchCompleteness = SearchCompleteness.COMPLETE,
    started_at: str = "2026-08-12T15:50:00Z",
    completed_at: str = "2026-08-12T15:55:00Z",
    run_index: int = 1,
) -> OrderSearchRun:
    scope = (interaction(),) if interactions is None else interactions
    return OrderSearchRun(
        run_id=RunId(f"SYN-RUN-SC-REPLACEMENT-{run_index:04d}"),
        trigger=trigger,
        interactions=scope,
        native_result_sets=(
            IdentifierSearchResult(
                identifier=SearchIdentifier(
                    SearchIdentifierKind.EMAIL,
                    "case@example.test",
                ),
                completeness=completeness,
                order_ids=order_ids,
            ),
        ),
        adapter=VersionBinding(
            "sales_credit_search_adapter",
            "sales-credit-search-adapter/v1",
        ),
        started_at=CanonicalTimestamp(started_at),
        completed_at=CanonicalTimestamp(completed_at),
    )


def evaluate(
    source: OrderSnapshot,
    *,
    events: tuple[EvidenceEvent, ...] = (),
    replacement_run: OrderSearchRun | None = None,
    replacement_candidates: tuple[ReplacementCandidateInput, ...] = (),
    prior_snapshots: tuple[OrderSnapshot, ...] = (),
    interactions: tuple[InteractionRecord, ...] | None = None,
    evaluated_at: CanonicalTimestamp = EVALUATED_AT,
):
    resolved_interactions = (
        (interaction(),) if interactions is None else interactions
    )
    return evaluate_sales_credit(
        evaluation_id=EvaluationId("SYN-EVALUATION-SC-EVAL-0001"),
        expected_order_id=ORDER,
        snapshot=source,
        evaluated_at=evaluated_at,
        known_other_reps=KNOWN_OTHER_REPS,
        interactions=resolved_interactions,
        evidence_events=events,
        replacement_run=replacement_run,
        replacement_candidates=replacement_candidates,
        prior_snapshots=prior_snapshots,
    )


class SnapshotPrecedenceTests(unittest.TestCase):
    def test_invalid_or_missing_core_fact_stops_all_favorable_rules(self) -> None:
        complete = snapshot()
        cases = {
            "explicit-invalid": dataclasses.replace(
                complete,
                extraction_status=SnapshotStatus.INVALID,
            ),
            "order-missing": snapshot(
                extraction_status=SnapshotStatus.INVALID,
                order_id=None,
            ),
            "order-mismatch": snapshot(
                extraction_status=SnapshotStatus.INVALID,
                order_id=OrderId("SYN-ORDER-SC-EVAL-0099"),
            ),
            "placed-time-missing": snapshot(
                extraction_status=SnapshotStatus.INVALID,
                placed_at=None,
                placed_at_precision=None,
            ),
            "status-missing": snapshot(
                extraction_status=SnapshotStatus.INVALID,
                raw_order_status=None,
            ),
            "unrecognized-status-forged-active": snapshot(
                raw_order_status="synthetic_unknown_status",
                lifecycle_status=OrderLifecycleStatus.ACTIVE,
            ),
            "active-status-forged-unknown": snapshot(
                raw_order_status="active",
                lifecycle_status=OrderLifecycleStatus.UNKNOWN,
            ),
            "provenance-missing": snapshot(
                extraction_status=SnapshotStatus.INVALID,
                source_ref=None,
                provenance=None,
            ),
        }
        for name, source in cases.items():
            with self.subTest(name=name):
                result = evaluate(source, events=(evidence(1),))
                self.assertIs(result.workflow_state, WorkflowState.MANUAL_REVIEW_REQUIRED)
                self.assertIs(
                    result.attribution.classification,
                    AttributionClassification.UNKNOWN,
                )
                self.assertIs(result.value.status, OrderValueStatus.UNKNOWN)
                self.assertIsNone(result.value.active_value)
                self.assertIn(SalesCreditReason.SNAPSHOT_INVALID, result.reasons)
                if name not in {
                    "active-status-forged-unknown",
                    "explicit-invalid",
                    "order-mismatch",
                    "unrecognized-status-forged-active",
                }:
                    self.assertIn(SalesCreditReason.MISSING_REQUIRED_FIELD, result.reasons)
                self.assertEqual(
                    result.rules_evaluated,
                    (SalesCreditRule.SNAPSHOT_VALIDATION,),
                )
        self.assertNotIn(SalesCreditReason.TARGET_REP, result.reasons)

    def test_candidate_order_must_qualify_against_an_attached_interaction(self) -> None:
        source = snapshot(raw_order_rep="target_rep")
        cases = (
            (
                "before-interaction",
                (
                    interaction(
                        recorded_at="2026-08-11T14:00:00Z",
                        review_start=date(2026, 8, 11),
                    ),
                ),
                SalesCreditReason.ORDER_BEFORE_INTERACTION,
                WorkflowState.MANUAL_REVIEW_REQUIRED,
            ),
            (
                "after-window",
                (
                    interaction(
                        recorded_at="2026-07-20T14:00:00Z",
                        review_start=date(2026, 7, 20),
                    ),
                ),
                SalesCreditReason.ORDER_AFTER_REVIEW_WINDOW,
                WorkflowState.MANUAL_REVIEW_REQUIRED,
            ),
            (
                "same-day-uncertain",
                (
                    interaction(
                        precision=TimestampPrecision.HISTORICAL_APPROXIMATION,
                    ),
                ),
                SalesCreditReason.ORDER_TIMING_UNCERTAIN,
                WorkflowState.TIMING_UNCERTAIN_HUMAN_REVIEW,
            ),
            (
                "missing-interaction",
                (),
                SalesCreditReason.MISSING_REQUIRED_FIELD,
                WorkflowState.MANUAL_REVIEW_REQUIRED,
            ),
        )
        for name, interactions, reason, expected_workflow in cases:
            with self.subTest(name=name):
                result = evaluate(source, interactions=interactions)
                self.assertIs(result.workflow_state, expected_workflow)
                self.assertTrue(result.human_review_required)
                self.assertIn(reason, result.reasons)
                self.assertNotIn(SalesCreditReason.TARGET_REP, result.reasons)
                self.assertIn(SalesCreditRule.ORDER_WINDOW, result.rules_fired)

        qualifying = evaluate(source, interactions=(interaction(),))
        self.assertIs(
            qualifying.workflow_state,
            WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
        )
        self.assertIn(SalesCreditValidation.ORDER_TIMING_ACCEPTED, qualifying.validations)

        invalid_canceled = snapshot(
            extraction_status=SnapshotStatus.INVALID,
            lifecycle_status=OrderLifecycleStatus.CANCELED,
            order_id=None,
            raw_order_status="canceled",
            canceled_at=CANCELED_AT,
        )
        candidate = snapshot(
            snapshot_index=90,
            order_id=REPLACEMENT_ORDER,
            placed_at=CanonicalTimestamp("2026-08-12T15:00:00Z"),
        )
        result = evaluate(
            invalid_canceled,
            replacement_run=replacement_search_run(
                order_ids=(REPLACEMENT_ORDER,),
            ),
            replacement_candidates=(
                replacement_input(candidate, line_universe_complete=False),
            ),
        )
        self.assertIs(result.replacement.status, ReplacementStatus.BLOCKED)
        self.assertEqual(
            result.rules_evaluated,
            (SalesCreditRule.SNAPSHOT_VALIDATION,),
        )

    def test_partial_snapshot_blocks_only_its_dependent_dimension(self) -> None:
        unrelated_line_partial = snapshot(
            extraction_status=SnapshotStatus.PARTIAL,
            warnings=("LINES_INCOMPLETE",),
        )
        result = evaluate(unrelated_line_partial)
        self.assertIs(result.workflow_state, WorkflowState.CREDIT_CONFIRMED_TARGET_REP)
        self.assertIs(result.attribution.classification, AttributionClassification.TARGET_REP)
        self.assertIs(result.value.status, OrderValueStatus.PLACED_VALUE_VERIFIED)
        self.assertNotIn(
            SalesCreditReason.SNAPSHOT_PARTIAL_DEPENDENCY_BLOCKED,
            result.reasons,
        )

        notes_partial = snapshot(
            extraction_status=SnapshotStatus.PARTIAL,
            notes_scan_status=NotesScanStatus.INCOMPLETE,
        )
        result = evaluate(notes_partial)
        self.assertIs(result.attribution.classification, AttributionClassification.TARGET_REP)
        self.assertIs(result.value.status, OrderValueStatus.PLACED_VALUE_VERIFIED)
        self.assertIs(result.workflow_state, WorkflowState.ORDER_CHANGED_HUMAN_REVIEW)
        self.assertIn(
            SalesCreditReason.SNAPSHOT_PARTIAL_DEPENDENCY_BLOCKED,
            result.reasons,
        )

    def test_lifecycle_raw_fact_contradiction_fails_before_rules(self) -> None:
        source = snapshot(
            extraction_status=SnapshotStatus.PARTIAL,
            lifecycle_status=OrderLifecycleStatus.ACTIVE,
            raw_order_status="canceled",
            warnings=("LINES_INCOMPLETE",),
        )
        result = evaluate(source)
        self.assertIn(SalesCreditReason.CONTRADICTORY_FACTS, result.reasons)
        self.assertEqual(result.rules_evaluated, (SalesCreditRule.SNAPSHOT_VALIDATION,))

        unsupported = evaluate(
            snapshot(
                lifecycle_status=OrderLifecycleStatus.UNKNOWN,
                raw_order_status="unknown",
            )
        )
        self.assertIs(unsupported.workflow_state, WorkflowState.MANUAL_REVIEW_REQUIRED)
        self.assertIn(
            SalesCreditReason.UNSUPPORTED_SCHEMA_OR_SNAPSHOT,
            unsupported.reasons,
        )


class AttributionAndValueTests(unittest.TestCase):
    def test_every_exact_order_rep_branch_and_no_line_rep_substitution(self) -> None:
        cases = (
            (
                "target_rep",
                AttributionClassification.TARGET_REP,
                WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
                SalesCreditReason.TARGET_REP,
            ),
            (
                "target_rep_web",
                AttributionClassification.TARGET_REP,
                WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
                SalesCreditReason.TARGET_REP_WEB,
            ),
            (
                "unassigned_web",
                AttributionClassification.UNASSIGNED_WEB,
                WorkflowState.EVIDENCE_NEEDED,
                SalesCreditReason.UNASSIGNED_WEB,
            ),
            (
                "synthetic_other_rep",
                AttributionClassification.OTHER_REP,
                WorkflowState.OTHER_REP_HUMAN_REVIEW,
                SalesCreditReason.OTHER_KNOWN_REP,
            ),
            (
                "synthetic_unrecognized_rep",
                AttributionClassification.UNKNOWN,
                WorkflowState.MANUAL_REVIEW_REQUIRED,
                SalesCreditReason.REP_UNRECOGNIZED,
            ),
            (
                None,
                AttributionClassification.UNKNOWN,
                WorkflowState.MANUAL_REVIEW_REQUIRED,
                SalesCreditReason.REP_MISSING,
            ),
            (
                "",
                AttributionClassification.UNKNOWN,
                WorkflowState.MANUAL_REVIEW_REQUIRED,
                SalesCreditReason.REP_MISSING,
            ),
        )
        for raw, classification, workflow, reason in cases:
            with self.subTest(raw=raw):
                status = SnapshotStatus.PARTIAL if raw == "" else SnapshotStatus.VALID
                warnings = ("LINES_INCOMPLETE",) if raw == "" else ()
                result = evaluate(
                    snapshot(
                        raw_order_rep=raw,
                        extraction_status=status,
                        warnings=warnings,
                    )
                )
                self.assertIs(result.attribution.classification, classification)
                self.assertIs(result.workflow_state, workflow)
                self.assertIn(reason, result.reasons)
                self.assertNotIn(SalesCreditReason.SNAPSHOT_INVALID, result.reasons)

        source = snapshot(
            raw_order_rep="synthetic_unrecognized_rep",
            lines=(line(1, raw_line_rep="target_rep"),),
        )
        result = evaluate(source)
        self.assertIs(result.attribution.classification, AttributionClassification.UNKNOWN)
        self.assertIs(result.workflow_state, WorkflowState.MANUAL_REVIEW_REQUIRED)

    def test_each_material_change_overrides_workflow_but_not_attribution(self) -> None:
        material = tuple(kind for kind in MaterialChangeKind if kind.is_material)
        self.assertEqual(len(material), 10)
        for index, kind in enumerate(material, start=1):
            with self.subTest(kind=kind.value):
                result = evaluate(snapshot(material_changes=(change(index, kind),)))
                self.assertIs(
                    result.attribution.classification,
                    AttributionClassification.TARGET_REP,
                )
                self.assertIs(result.value.status, OrderValueStatus.CHANGED_REVIEW)
                self.assertIsNone(result.value.active_value)
                self.assertEqual(result.value.material_changes, (kind,))
                self.assertIs(result.workflow_state, WorkflowState.ORDER_CHANGED_HUMAN_REVIEW)
                self.assertIn(SalesCreditReason.MATERIAL_CHANGE_DETECTED, result.reasons)

    def test_routine_changes_are_nonmaterial_but_current_value_never_substitutes(self) -> None:
        routine = tuple(kind for kind in MaterialChangeKind if not kind.is_material)
        for index, kind in enumerate(routine, start=20):
            with self.subTest(kind=kind.value):
                result = evaluate(snapshot(material_changes=(change(index, kind),)))
                self.assertIs(result.value.status, OrderValueStatus.PLACED_VALUE_VERIFIED)
                self.assertEqual(result.value.active_value, money())
                self.assertIs(result.workflow_state, WorkflowState.CREDIT_CONFIRMED_TARGET_REP)
                self.assertIn(
                    SalesCreditReason.ROUTINE_LIFECYCLE_CHANGE_NONMATERIAL,
                    result.reasons,
                )

        current_only = evaluate(snapshot(placed_value=None))
        self.assertIs(current_only.value.status, OrderValueStatus.CURRENT_ONLY)
        self.assertIsNone(current_only.value.active_value)
        self.assertIs(
            current_only.workflow_state,
            WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
        )
        self.assertIs(
            current_only.attribution.classification,
            AttributionClassification.TARGET_REP,
        )
        self.assertIn(SalesCreditReason.PLACED_VALUE_UNAVAILABLE, current_only.reasons)
        verified = evaluate(snapshot())
        self.assertIn(SalesCreditReason.PLACED_VALUE_PROVED, verified.reasons)

        unknown_without_placed = evaluate(
            snapshot(
                lifecycle_status=OrderLifecycleStatus.UNKNOWN,
                raw_order_status="unknown",
                placed_value=None,
            )
        )
        self.assertIs(
            unknown_without_placed.workflow_state,
            WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
        )
        self.assertIn(
            SalesCreditReason.PLACED_VALUE_UNAVAILABLE,
            unknown_without_placed.reasons,
        )

        unknown_material = evaluate(
            snapshot(
                lifecycle_status=OrderLifecycleStatus.UNKNOWN,
                raw_order_status="unknown",
                material_changes=(
                    change(40, MaterialChangeKind.PRICE_ADJUSTMENT),
                ),
            )
        )
        self.assertIs(
            unknown_material.workflow_state,
            WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
        )
        self.assertIn(
            SalesCreditReason.MATERIAL_CHANGE_DETECTED,
            unknown_material.reasons,
        )

    def test_header_placed_value_is_authoritative_and_lines_are_not_reconstructed(
        self,
    ) -> None:
        source = snapshot(
            current_value=money("200.00"),
            placed_value=money("123.45"),
            lines=(
                line(80, quantity=9, line_value="10.00"),
                line(81, quantity=2, line_value="20.00"),
            ),
        )
        result = evaluate(source)
        self.assertEqual(result.value.placed_value, money("123.45"))
        self.assertEqual(result.value.active_value, money("123.45"))
        self.assertEqual(source.lines[0].line_value, money("10.00"))
        self.assertEqual(source.lines[0].quantity, Quantity(9))
        self.assertIn(SalesCreditReason.PLACED_VALUE_PROVED, result.reasons)
        self.assertIs(
            result.workflow_state,
            WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
        )


class EvidenceClassificationTests(unittest.TestCase):
    def test_every_binding_evidence_branch(self) -> None:
        cases = (
            (
                evidence(1),
                EvidenceClassification.VERIFIED_PREORDER_EVIDENCE,
                WorkflowState.VERIFIED_PREORDER_EVIDENCE,
                SalesCreditReason.TWO_WAY_PREORDER_INTERACTION,
            ),
            (
                evidence(
                    2,
                    source_type=EvidenceSourceType.SYNTHETIC_PHONE_CALL,
                    direction=EvidenceDirection.INBOUND,
                    connected=True,
                    two_way=False,
                ),
                EvidenceClassification.VERIFIED_PREORDER_EVIDENCE,
                WorkflowState.VERIFIED_PREORDER_EVIDENCE,
                SalesCreditReason.CONNECTED_PREORDER_CALL,
            ),
            (
                evidence(
                    3,
                    direction=EvidenceDirection.INBOUND,
                    target=False,
                    connected=False,
                    two_way=False,
                ),
                EvidenceClassification.INBOUND_EVIDENCE_HUMAN_REVIEW,
                WorkflowState.INBOUND_EVIDENCE_HUMAN_REVIEW,
                SalesCreditReason.INBOUND_ONLY_PREORDER_CONTACT,
            ),
            (
                evidence(
                    4,
                    source_type=EvidenceSourceType.SYNTHETIC_PHONE_CALL,
                    direction=EvidenceDirection.INBOUND,
                    target=False,
                    connected=False,
                    two_way=False,
                ),
                EvidenceClassification.INBOUND_EVIDENCE_HUMAN_REVIEW,
                WorkflowState.INBOUND_EVIDENCE_HUMAN_REVIEW,
                SalesCreditReason.MISSED_OR_UNANSWERED_INBOUND_CALL,
            ),
            (
                evidence(
                    5,
                    direction=EvidenceDirection.OUTBOUND,
                    target=True,
                    connected=False,
                    two_way=False,
                ),
                EvidenceClassification.OUTBOUND_EVIDENCE_HUMAN_REVIEW,
                WorkflowState.OUTBOUND_EVIDENCE_HUMAN_REVIEW,
                SalesCreditReason.OUTBOUND_ONLY_PREORDER_CONTACT,
            ),
            (
                evidence(
                    6,
                    occurred_at="2026-08-10T18:00:00Z",
                    direction=EvidenceDirection.UNKNOWN,
                    target=None,
                    connected=None,
                    two_way=None,
                    timing=EvidenceTimingRelation.POST_ORDER,
                ),
                EvidenceClassification.POST_ORDER_CONTACT_ONLY,
                WorkflowState.MANUAL_REVIEW_REQUIRED,
                SalesCreditReason.POST_ORDER_CONTACT_ONLY,
            ),
            (
                evidence(
                    7,
                    precision=TimestampPrecision.REVISION_DERIVED,
                    timing=EvidenceTimingRelation.SAME_DAY_UNCERTAIN,
                ),
                EvidenceClassification.TIMING_UNCERTAIN_HUMAN_REVIEW,
                WorkflowState.TIMING_UNCERTAIN_HUMAN_REVIEW,
                SalesCreditReason.EVIDENCE_TIMING_UNCERTAIN,
            ),
            (
                evidence(
                    8,
                    direction=EvidenceDirection.UNKNOWN,
                    connected=False,
                    two_way=False,
                ),
                EvidenceClassification.UNKNOWN_OR_CONTRADICTORY,
                WorkflowState.MANUAL_REVIEW_REQUIRED,
                SalesCreditReason.EVIDENCE_IDENTITY_UNPROVED,
            ),
        )
        source = snapshot(raw_order_rep="unassigned_web")
        for event, classification, workflow, reason in cases:
            with self.subTest(classification=classification.value, event=event.evidence_id.value):
                decision = classify_evidence_event(
                    event,
                    order_at=ORDER_AT,
                    order_precision=TimestampPrecision.EXACT,
                )
                self.assertIs(decision.classification, classification)
                result = evaluate(source, events=(event,))
                self.assertIs(result.workflow_state, workflow)
                self.assertIn(reason, result.reasons)

        no_evidence = evaluate(source, events=())
        self.assertIs(no_evidence.workflow_state, WorkflowState.EVIDENCE_NEEDED)
        self.assertIn(
            SalesCreditReason.NO_QUALIFYING_PREORDER_EVIDENCE,
            no_evidence.reasons,
        )

    def test_unknown_contradictory_and_wrong_order_evidence_fail_closed(self) -> None:
        source = snapshot(raw_order_rep="unassigned_web")
        contradictory_time = evidence(
            10,
            occurred_at="2026-08-10T18:00:00Z",
            timing=EvidenceTimingRelation.PRE_ORDER,
        )
        result = evaluate(source, events=(contradictory_time,))
        self.assertIs(result.workflow_state, WorkflowState.MANUAL_REVIEW_REQUIRED)
        self.assertIn(SalesCreditReason.CONTRADICTORY_FACTS, result.reasons)

        provably_preorder_but_declared_unknown = evidence(
            16,
            timing=EvidenceTimingRelation.UNKNOWN,
        )
        result = evaluate(source, events=(provably_preorder_but_declared_unknown,))
        self.assertIs(result.workflow_state, WorkflowState.MANUAL_REVIEW_REQUIRED)
        self.assertIn(SalesCreditReason.CONTRADICTORY_FACTS, result.reasons)

        unknown_participation = evidence(
            11,
            direction=EvidenceDirection.OUTBOUND,
            target=None,
            connected=False,
            two_way=False,
        )
        result = evaluate(source, events=(unknown_participation,))
        self.assertIs(result.workflow_state, WorkflowState.MANUAL_REVIEW_REQUIRED)

        wrong_order = evidence(
            12,
            order_id=OrderId("SYN-ORDER-SC-EVAL-0099"),
        )
        result = evaluate(source, events=(wrong_order,))
        self.assertIs(result.workflow_state, WorkflowState.MANUAL_REVIEW_REQUIRED)
        self.assertIn(SalesCreditReason.CONTRADICTORY_FACTS, result.reasons)

        unresolved_interaction = InteractionId("SYN-INTERACTION-SC-EVAL-0099")
        event = evidence(13, interaction_id=unresolved_interaction)
        result = evaluate(source, events=(event,))
        self.assertIs(result.workflow_state, WorkflowState.MANUAL_REVIEW_REQUIRED)
        self.assertIn(SalesCreditReason.EVIDENCE_IDENTITY_UNPROVED, result.reasons)

        wrong_identifier_kind = evidence(
            14,
            identifier_kind=EvidenceIdentifierKind.PHONE,
        )
        result = evaluate(source, events=(wrong_identifier_kind,))
        self.assertIs(result.workflow_state, WorkflowState.MANUAL_REVIEW_REQUIRED)
        self.assertIn(SalesCreditReason.EVIDENCE_IDENTITY_UNPROVED, result.reasons)

        unreliable_preorder = evidence(
            15,
            precision=TimestampPrecision.HISTORICAL_APPROXIMATION,
            timing=EvidenceTimingRelation.PRE_ORDER,
        )
        result = evaluate(source, events=(unreliable_preorder,))
        self.assertIs(result.workflow_state, WorkflowState.MANUAL_REVIEW_REQUIRED)
        self.assertIn(SalesCreditReason.CONTRADICTORY_FACTS, result.reasons)

    def test_evidence_binding_resolves_exact_interaction_and_identifier_kind(self) -> None:
        source = snapshot(raw_order_rep="unassigned_web")
        resolved = evidence(16)
        accepted = evaluate(
            source,
            events=(resolved,),
            interactions=(interaction(resolved.interaction_id),),
        )
        self.assertIs(
            accepted.workflow_state,
            WorkflowState.VERIFIED_PREORDER_EVIDENCE,
        )

        missing_interaction = evaluate(source, events=(resolved,), interactions=())
        self.assertIs(
            missing_interaction.workflow_state,
            WorkflowState.MANUAL_REVIEW_REQUIRED,
        )
        self.assertIn(
            SalesCreditReason.MISSING_REQUIRED_FIELD,
            missing_interaction.reasons,
        )

        phone_without_contact = evidence(
            17,
            identifier_kind=EvidenceIdentifierKind.PHONE,
        )
        missing_kind = evaluate(
            source,
            events=(phone_without_contact,),
            interactions=(interaction(phone_without_contact.interaction_id),),
        )
        self.assertIs(
            missing_kind.workflow_state,
            WorkflowState.MANUAL_REVIEW_REQUIRED,
        )
        self.assertIn(
            SalesCreditReason.EVIDENCE_IDENTITY_UNPROVED,
            missing_kind.reasons,
        )

        other_interaction_id = InteractionId("SYN-INTERACTION-SC-EVAL-0098")
        forged_binding = dataclasses.replace(
            resolved,
            matched_identifier_ref=evidence_identifier_binding(
                interaction_id=other_interaction_id,
                identifier_kind=EvidenceIdentifierKind.EMAIL,
            ),
        )
        mismatched = evaluate(
            source,
            events=(forged_binding,),
            interactions=(interaction(resolved.interaction_id),),
        )
        self.assertIs(
            mismatched.workflow_state,
            WorkflowState.MANUAL_REVIEW_REQUIRED,
        )
        self.assertIn(
            SalesCreditReason.EVIDENCE_IDENTITY_UNPROVED,
            mismatched.reasons,
        )

    def test_distinct_one_way_events_never_infer_two_way_contact(self) -> None:
        inbound = evidence(
            20,
            direction=EvidenceDirection.INBOUND,
            target=False,
            connected=False,
            two_way=False,
        )
        outbound = evidence(
            21,
            direction=EvidenceDirection.OUTBOUND,
            target=True,
            connected=False,
            two_way=False,
        )
        decision = classify_evidence(
            (inbound, outbound),
            order_at=ORDER_AT,
            order_precision=TimestampPrecision.EXACT,
        )
        self.assertIs(
            decision.classification,
            EvidenceClassification.UNKNOWN_OR_CONTRADICTORY,
        )
        result = evaluate(
            snapshot(raw_order_rep="unassigned_web"),
            events=(inbound, outbound),
        )
        self.assertIs(result.workflow_state, WorkflowState.MANUAL_REVIEW_REQUIRED)


class CancellationAndReplacementTests(unittest.TestCase):
    def canceled(self, **changes: object) -> OrderSnapshot:
        values = {
            "lifecycle_status": OrderLifecycleStatus.CANCELED,
            "raw_order_status": "canceled",
            "canceled_at": CANCELED_AT,
        }
        values.update(changes)
        return snapshot(**values)  # type: ignore[arg-type]

    def test_canceled_order_open_and_expired_windows_have_zero_active_value(self) -> None:
        source = self.canceled()
        open_result = evaluate(source)
        self.assertIs(
            open_result.workflow_state,
            WorkflowState.CANCELED_REPLACEMENT_WINDOW_ACTIVE,
        )
        self.assertIs(open_result.replacement.status, ReplacementStatus.WINDOW_ACTIVE)
        self.assertEqual(open_result.value.active_value, money("0.00"))
        self.assertIs(
            open_result.attribution.classification,
            AttributionClassification.TARGET_REP,
        )
        self.assertIn(SalesCreditEffect.ZERO_ACTIVE_VALUE, open_result.persistence_effects)
        self.assertIn(
            SalesCreditReason.CANCELED_ORDER_ZERO_ACTIVE_VALUE,
            open_result.reasons,
        )
        self.assertIn(SalesCreditReason.REPLACEMENT_WINDOW_ACTIVE, open_result.reasons)

        expired = evaluate_sales_credit(
            evaluation_id=EvaluationId("SYN-EVALUATION-SC-EVAL-0002"),
            expected_order_id=ORDER,
            snapshot=source,
            evaluated_at=CanonicalTimestamp("2026-08-26T05:00:00Z"),
            known_other_reps=KNOWN_OTHER_REPS,
            interactions=(interaction(),),
            replacement_run=replacement_search_run(
                started_at="2026-08-26T04:00:00Z",
                completed_at="2026-08-26T04:01:00Z",
            ),
        )
        self.assertIs(expired.workflow_state, WorkflowState.CANCELED_NO_REPLACEMENT)
        self.assertIs(expired.replacement.status, ReplacementStatus.WINDOW_EXPIRED)
        self.assertIn(SalesCreditReason.REPLACEMENT_WINDOW_EXPIRED, expired.reasons)

        current_only = evaluate(self.canceled(placed_value=None))
        self.assertIs(current_only.value.status, OrderValueStatus.CURRENT_ONLY)
        self.assertIsNone(current_only.value.active_value)
        self.assertIs(
            current_only.workflow_state,
            WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
        )
        self.assertIn(SalesCreditEffect.ZERO_ACTIVE_VALUE, current_only.persistence_effects)

        changed = evaluate(
            self.canceled(
                material_changes=(
                    change(99, MaterialChangeKind.PARTIAL_CANCELLATION),
                )
            )
        )
        self.assertIs(changed.value.status, OrderValueStatus.CHANGED_REVIEW)
        self.assertIsNone(changed.value.active_value)
        self.assertIs(
            changed.workflow_state,
            WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
        )

    def test_exact_es_mfg_one_among_many_nonexact_and_absent_branches(self) -> None:
        parent = self.canceled(
            lines=(line(1, es="00123"), line(2, mfg="ABC-9")),
        )
        candidates = (
            (
                snapshot(
                    snapshot_index=2,
                    order_id=REPLACEMENT_ORDER,
                    placed_at=CanonicalTimestamp("2026-08-12T15:00:00Z"),
                    lines=(line(3, es="999"), line(4, es="123")),
                ),
                False,
                ProductContinuityStatus.EXACT_ES,
                SalesCreditReason.EXACT_ES_PRODUCT_CONTINUITY,
            ),
            (
                snapshot(
                    snapshot_index=3,
                    order_id=REPLACEMENT_ORDER,
                    placed_at=CanonicalTimestamp("2026-08-12T15:00:00Z"),
                    lines=(line(5, mfg="abc-9"),),
                ),
                False,
                ProductContinuityStatus.EXACT_MFG_OE,
                SalesCreditReason.EXACT_MFG_OE_PRODUCT_CONTINUITY,
            ),
            (
                snapshot(
                    snapshot_index=4,
                    order_id=REPLACEMENT_ORDER,
                    placed_at=CanonicalTimestamp("2026-08-12T15:00:00Z"),
                    lines=(line(6, mfg="SUBSTITUTE-1"),),
                ),
                True,
                ProductContinuityStatus.NONEXACT,
                SalesCreditReason.NONEXACT_PRODUCT_CONTINUITY_REQUIRES_REVIEW,
            ),
        )
        for candidate, possible, expected_product, expected_reason in candidates:
            with self.subTest(product=expected_product.value):
                facts = derive_replacement_facts(
                    parent=parent,
                    candidate=candidate,
                    line_universe_complete=True,
                    possible_nonexact_continuity=possible,
                )
                self.assertIs(facts.product_continuity, expected_product)
                result = evaluate(
                    parent,
                    replacement_run=replacement_search_run(
                        order_ids=(REPLACEMENT_ORDER,),
                    ),
                    replacement_candidates=(
                        replacement_input(
                            candidate,
                            possible_nonexact_continuity=possible,
                        ),
                    ),
                )
                self.assertIs(
                    result.workflow_state,
                    WorkflowState.POSSIBLE_REPLACEMENT_HUMAN_REVIEW,
                )
                self.assertIn(expected_reason, result.reasons)

        no_match = snapshot(
            snapshot_index=5,
            order_id=REPLACEMENT_ORDER,
            placed_at=CanonicalTimestamp("2026-08-12T15:00:00Z"),
            lines=(line(7, es="456"),),
        )
        facts = derive_replacement_facts(
            parent=parent,
            candidate=no_match,
            line_universe_complete=True,
        )
        self.assertIs(facts.product_continuity, ProductContinuityStatus.ABSENT)
        result = evaluate(
            parent,
            replacement_run=replacement_search_run(
                order_ids=(REPLACEMENT_ORDER,),
            ),
            replacement_candidates=(replacement_input(no_match),),
        )
        self.assertIs(result.replacement.status, ReplacementStatus.WINDOW_ACTIVE)
        self.assertIs(
            result.workflow_state,
            WorkflowState.CANCELED_REPLACEMENT_WINDOW_ACTIVE,
        )
        self.assertIn(SalesCreditReason.NO_PRODUCT_CONTINUITY, result.reasons)

    def test_customer_absence_and_incomplete_lines_cannot_prove_replacement(self) -> None:
        parent = self.canceled(lines=(line(30, es="123"),))
        customer_absent = snapshot(
            snapshot_index=6,
            order_id=REPLACEMENT_ORDER,
            placed_at=CanonicalTimestamp("2026-08-12T15:00:00Z"),
            customer_ids=(CustomerId("SYN-CUSTOMER-SC-EVAL-0099"),),
            lines=(line(31, es="123"),),
        )
        facts = derive_replacement_facts(
            parent=parent,
            candidate=customer_absent,
            line_universe_complete=True,
        )
        self.assertIs(
            facts.customer_continuity,
            CustomerContinuityStatus.ABSENT,
        )
        result = evaluate(
            parent,
            replacement_run=replacement_search_run(
                order_ids=(REPLACEMENT_ORDER,),
            ),
            replacement_candidates=(replacement_input(customer_absent),),
        )
        self.assertIs(result.replacement.status, ReplacementStatus.WINDOW_ACTIVE)
        self.assertIn(SalesCreditReason.CUSTOMER_CONTINUITY_MISMATCH, result.reasons)

        incomplete = snapshot(
            snapshot_index=7,
            order_id=REPLACEMENT_ORDER,
            extraction_status=SnapshotStatus.PARTIAL,
            placed_at=CanonicalTimestamp("2026-08-12T15:00:00Z"),
            lines=(line(32, es="123"),),
            warnings=("LINES_INCOMPLETE",),
        )
        facts = derive_replacement_facts(
            parent=parent,
            candidate=incomplete,
            line_universe_complete=False,
        )
        self.assertIs(facts.product_continuity, ProductContinuityStatus.UNKNOWN)
        result = evaluate(
            parent,
            replacement_run=replacement_search_run(
                order_ids=(REPLACEMENT_ORDER,),
            ),
            replacement_candidates=(
                replacement_input(incomplete, line_universe_complete=False),
            ),
        )
        self.assertIs(result.replacement.status, ReplacementStatus.BLOCKED)
        self.assertIs(
            result.workflow_state,
            WorkflowState.POSSIBLE_REPLACEMENT_HUMAN_REVIEW,
        )
        self.assertIn(SalesCreditReason.NO_PRODUCT_CONTINUITY, result.reasons)

        unknown_customer = snapshot(
            snapshot_index=71,
            order_id=REPLACEMENT_ORDER,
            placed_at=CanonicalTimestamp("2026-08-12T15:00:00Z"),
            customer_ids=(),
            lines=(line(33, es="123"),),
        )
        unknown_facts = derive_replacement_facts(
            parent=parent,
            candidate=unknown_customer,
            line_universe_complete=True,
        )
        self.assertIs(
            unknown_facts.customer_continuity,
            CustomerContinuityStatus.UNKNOWN,
        )
        unknown_result = evaluate(
            parent,
            replacement_run=replacement_search_run(
                order_ids=(REPLACEMENT_ORDER,),
            ),
            replacement_candidates=(replacement_input(unknown_customer),),
        )
        self.assertIn(
            SalesCreditReason.CUSTOMER_CONTINUITY_UNPROVED,
            unknown_result.reasons,
        )

        incomplete_absence = snapshot(
            snapshot_index=72,
            order_id=REPLACEMENT_ORDER,
            extraction_status=SnapshotStatus.PARTIAL,
            placed_at=CanonicalTimestamp("2026-08-12T15:00:00Z"),
            lines=(line(34, es="456"),),
            warnings=("LINES_INCOMPLETE",),
        )
        result = evaluate(
            parent,
            replacement_run=replacement_search_run(
                order_ids=(REPLACEMENT_ORDER,),
            ),
            replacement_candidates=(
                replacement_input(
                    incomplete_absence,
                    line_universe_complete=False,
                ),
            ),
        )
        self.assertIs(
            result.workflow_state,
            WorkflowState.POSSIBLE_REPLACEMENT_HUMAN_REVIEW,
        )
        self.assertIn(
            SalesCreditReason.SNAPSHOT_PARTIAL_DEPENDENCY_BLOCKED,
            result.reasons,
        )

        incomplete_customers = snapshot(
            snapshot_index=73,
            order_id=REPLACEMENT_ORDER,
            extraction_status=SnapshotStatus.PARTIAL,
            placed_at=CanonicalTimestamp("2026-08-12T15:00:00Z"),
            customer_ids=(CustomerId("SYN-CUSTOMER-SC-EVAL-0099"),),
            lines=(line(35, es="456"),),
            warnings=("CUSTOMERS_INCOMPLETE",),
        )
        result = evaluate(
            parent,
            replacement_run=replacement_search_run(
                order_ids=(REPLACEMENT_ORDER,),
            ),
            replacement_candidates=(replacement_input(incomplete_customers),),
        )
        self.assertIs(
            result.workflow_state,
            WorkflowState.POSSIBLE_REPLACEMENT_HUMAN_REVIEW,
        )
        self.assertIn(
            SalesCreditReason.CUSTOMER_CONTINUITY_UNPROVED,
            result.reasons,
        )

    def test_complete_post_window_batch_is_the_only_terminal_authority(self) -> None:
        parent = self.canceled(lines=(line(60, es="123"),))
        post_window = {
            "started_at": "2026-08-26T04:00:00Z",
            "completed_at": "2026-08-26T04:01:00Z",
        }
        zero = evaluate(
            parent,
            replacement_run=replacement_search_run(**post_window),
            evaluated_at=CanonicalTimestamp("2026-08-26T05:00:00Z"),
        )
        self.assertIs(zero.workflow_state, WorkflowState.CANCELED_NO_REPLACEMENT)
        self.assertIs(zero.replacement.status, ReplacementStatus.WINDOW_EXPIRED)
        self.assertEqual(zero.replacement.candidate_results, ())

        parent_only = evaluate(
            parent,
            replacement_run=replacement_search_run(
                order_ids=(ORDER,),
                **post_window,
            ),
            evaluated_at=CanonicalTimestamp("2026-08-26T05:00:00Z"),
        )
        self.assertIs(
            parent_only.workflow_state,
            WorkflowState.CANCELED_NO_REPLACEMENT,
        )
        self.assertEqual(parent_only.replacement.candidate_results, ())

        first = snapshot(
            snapshot_index=61,
            order_id=REPLACEMENT_ORDER,
            placed_at=CanonicalTimestamp("2026-08-12T15:00:00Z"),
            lines=(line(61, es="999"),),
        )
        second = snapshot(
            snapshot_index=62,
            order_id=REPLACEMENT_ORDER_2,
            placed_at=CanonicalTimestamp("2026-08-13T15:00:00Z"),
            captured_at=CanonicalTimestamp("2026-08-13T16:00:00Z"),
            lines=(line(62, es="998"),),
        )
        two_nonmatches = evaluate(
            parent,
            replacement_run=replacement_search_run(
                order_ids=(REPLACEMENT_ORDER, REPLACEMENT_ORDER_2),
                **post_window,
            ),
            replacement_candidates=(
                replacement_input(first),
                replacement_input(second),
            ),
            evaluated_at=CanonicalTimestamp("2026-08-26T05:00:00Z"),
        )
        self.assertIs(
            two_nonmatches.workflow_state,
            WorkflowState.CANCELED_NO_REPLACEMENT,
        )
        self.assertTrue(
            all(
                item.status is ReplacementStatus.NOT_CONTINUATION
                for item in two_nonmatches.replacement.candidate_results
            )
        )

    def test_preexpiry_or_boundary_crossing_run_cannot_terminalize_later(self) -> None:
        parent = self.canceled()
        late_evaluation = CanonicalTimestamp("2026-08-26T05:00:00Z")
        preexpiry = evaluate(
            parent,
            replacement_run=replacement_search_run(
                started_at="2026-08-25T20:00:00Z",
                completed_at="2026-08-25T20:01:00Z",
            ),
            evaluated_at=late_evaluation,
        )
        self.assertIs(
            preexpiry.workflow_state,
            WorkflowState.CANCELED_REPLACEMENT_WINDOW_ACTIVE,
        )
        self.assertIs(
            preexpiry.replacement.status,
            ReplacementStatus.WINDOW_ACTIVE,
        )

        crossing = evaluate(
            parent,
            replacement_run=replacement_search_run(
                started_at="2026-08-26T03:59:59.999999999Z",
                completed_at="2026-08-26T04:00:00Z",
            ),
            evaluated_at=late_evaluation,
        )
        self.assertIs(crossing.replacement.status, ReplacementStatus.BLOCKED)
        self.assertIs(crossing.workflow_state, WorkflowState.MANUAL_REVIEW_REQUIRED)
        self.assertIn(
            SalesCreditReason.IDENTIFIER_SEARCH_INCOMPLETE,
            crossing.reasons,
        )

        exact_parent = self.canceled(lines=(line(63, es="123"),))
        exact_candidate = replacement_input(
            snapshot(
                snapshot_index=63,
                order_id=REPLACEMENT_ORDER,
                placed_at=CanonicalTimestamp("2026-08-12T15:00:00Z"),
                lines=(line(64, es="123"),),
            )
        )
        exact = evaluate(
            exact_parent,
            replacement_run=replacement_search_run(
                order_ids=(REPLACEMENT_ORDER,),
                started_at="2026-08-26T03:59:59.999999999Z",
                completed_at="2026-08-26T04:00:00Z",
            ),
            replacement_candidates=(exact_candidate,),
            evaluated_at=late_evaluation,
        )
        self.assertIs(exact.replacement.status, ReplacementStatus.EXACT_RELEVANT)

    def test_exact_possible_and_blocked_candidates_dominate_nonmatches(self) -> None:
        parent = self.canceled(lines=(line(70, es="123"),))
        nonmatch = replacement_input(
            snapshot(
                snapshot_index=70,
                order_id=REPLACEMENT_ORDER,
                placed_at=CanonicalTimestamp("2026-08-12T15:00:00Z"),
                lines=(line(71, es="999"),),
            )
        )
        exact = replacement_input(
            snapshot(
                snapshot_index=71,
                order_id=REPLACEMENT_ORDER_2,
                placed_at=CanonicalTimestamp("2026-08-12T15:00:00Z"),
                lines=(line(72, es="123"),),
            )
        )
        run = replacement_search_run(
            order_ids=(REPLACEMENT_ORDER, REPLACEMENT_ORDER_2),
        )
        forward = evaluate(
            parent,
            replacement_run=run,
            replacement_candidates=(nonmatch, exact),
        )
        reversed_result = evaluate(
            parent,
            replacement_run=run,
            replacement_candidates=(exact, nonmatch),
        )
        self.assertEqual(forward.replacement, reversed_result.replacement)
        self.assertIs(
            forward.replacement.status,
            ReplacementStatus.EXACT_RELEVANT,
        )

        possible = replacement_input(
            snapshot(
                snapshot_index=72,
                order_id=REPLACEMENT_ORDER_2,
                placed_at=CanonicalTimestamp("2026-08-12T15:00:00Z"),
                lines=(line(73, mfg="SUBSTITUTE-1"),),
            ),
            possible_nonexact_continuity=True,
        )
        possible_result = evaluate(
            parent,
            replacement_run=run,
            replacement_candidates=(possible, nonmatch),
        )
        self.assertIs(
            possible_result.replacement.status,
            ReplacementStatus.POSSIBLE_REVIEW,
        )

        blocked = replacement_input(
            snapshot(
                snapshot_index=73,
                order_id=REPLACEMENT_ORDER_2,
                extraction_status=SnapshotStatus.PARTIAL,
                placed_at=CanonicalTimestamp("2026-08-12T15:00:00Z"),
                lines=(line(74, es="123"),),
                warnings=("LINES_INCOMPLETE",),
            ),
            line_universe_complete=False,
        )
        blocked_result = evaluate(
            parent,
            replacement_run=run,
            replacement_candidates=(nonmatch, blocked),
        )
        self.assertIs(
            blocked_result.replacement.status,
            ReplacementStatus.BLOCKED,
        )
        self.assertNotEqual(
            blocked_result.workflow_state,
            WorkflowState.CANCELED_NO_REPLACEMENT,
        )

    def test_wrong_incomplete_or_mismatched_batch_authority_fails_closed(self) -> None:
        parent = self.canceled()
        late = CanonicalTimestamp("2026-08-26T05:00:00Z")
        post_window = {
            "started_at": "2026-08-26T04:00:00Z",
            "completed_at": "2026-08-26T04:01:00Z",
        }
        omitted = evaluate(parent, evaluated_at=late)
        incomplete = evaluate(
            parent,
            replacement_run=replacement_search_run(
                completeness=SearchCompleteness.INCOMPLETE,
                **post_window,
            ),
            evaluated_at=late,
        )
        wrong_trigger = evaluate(
            parent,
            replacement_run=replacement_search_run(
                trigger=SearchTriggerType.NORMAL,
                **post_window,
            ),
            evaluated_at=late,
        )
        for result in (omitted, incomplete, wrong_trigger):
            with self.subTest(status=result.replacement.status.value):
                self.assertIs(result.replacement.status, ReplacementStatus.BLOCKED)
                self.assertNotEqual(
                    result.workflow_state,
                    WorkflowState.CANCELED_NO_REPLACEMENT,
                )

        candidate = replacement_input(
            snapshot(
                snapshot_index=74,
                order_id=REPLACEMENT_ORDER,
                placed_at=CanonicalTimestamp("2026-08-12T15:00:00Z"),
            )
        )
        missing = evaluate(
            parent,
            replacement_run=replacement_search_run(
                order_ids=(REPLACEMENT_ORDER,),
            ),
        )
        extra = evaluate(
            parent,
            replacement_run=replacement_search_run(),
            replacement_candidates=(candidate,),
        )
        for result in (missing, extra):
            self.assertIs(result.replacement.status, ReplacementStatus.BLOCKED)
            self.assertIn(SalesCreditReason.CONTRADICTORY_FACTS, result.reasons)

    def test_replacement_scope_time_parent_and_duplicate_guards_are_exact(self) -> None:
        parent = self.canceled()
        altered_scope = (
            dataclasses.replace(
                interaction(),
                active_notes="synthetic: altered replacement scope",
            ),
        )
        wrong_scope = evaluate(
            parent,
            replacement_run=replacement_search_run(interactions=altered_scope),
        )
        before_cancel = evaluate(
            parent,
            replacement_run=replacement_search_run(
                started_at="2026-08-11T15:59:00Z",
                completed_at="2026-08-11T15:59:30Z",
            ),
        )
        after_evaluation = evaluate(
            parent,
            replacement_run=replacement_search_run(
                completed_at="2026-08-12T16:00:00.000000001Z",
            ),
        )
        parent_candidate = replacement_input(
            snapshot(
                snapshot_index=75,
                order_id=ORDER,
                placed_at=CanonicalTimestamp("2026-08-12T15:00:00Z"),
            )
        )
        includes_parent = evaluate(
            parent,
            replacement_run=replacement_search_run(order_ids=(ORDER,)),
            replacement_candidates=(parent_candidate,),
        )
        for result in (wrong_scope, before_cancel, after_evaluation, includes_parent):
            self.assertIs(result.replacement.status, ReplacementStatus.BLOCKED)
            self.assertIs(result.workflow_state, WorkflowState.MANUAL_REVIEW_REQUIRED)

        duplicate = replacement_input(
            snapshot(
                snapshot_index=76,
                order_id=REPLACEMENT_ORDER,
                placed_at=CanonicalTimestamp("2026-08-12T15:00:00Z"),
            )
        )
        with self.assertRaisesRegex(
            SalesCreditEvaluationError,
            "replacement_candidates_duplicate",
        ):
            evaluate(
                parent,
                replacement_run=replacement_search_run(
                    order_ids=(REPLACEMENT_ORDER,),
                ),
                replacement_candidates=(duplicate, duplicate),
            )

        parent_with_line = self.canceled(lines=(line(44, es="123"),))
        observed_at_completion = replacement_input(
            snapshot(
                snapshot_index=77,
                order_id=REPLACEMENT_ORDER,
                placed_at=CanonicalTimestamp("2026-08-12T15:55:00Z"),
                captured_at=CanonicalTimestamp("2026-08-12T16:00:00Z"),
                lines=(line(45, es="123"),),
            )
        )
        observed = evaluate(
            parent_with_line,
            replacement_run=replacement_search_run(
                order_ids=(REPLACEMENT_ORDER,),
            ),
            replacement_candidates=(observed_at_completion,),
        )
        self.assertIs(observed.replacement.status, ReplacementStatus.EXACT_RELEVANT)

        placed_after_completion = replacement_input(
            snapshot(
                snapshot_index=78,
                order_id=REPLACEMENT_ORDER,
                placed_at=CanonicalTimestamp("2026-08-12T15:55:00.000000001Z"),
                captured_at=CanonicalTimestamp("2026-08-12T16:00:00Z"),
                lines=(line(46, es="123"),),
            )
        )
        future_result = evaluate(
            parent_with_line,
            replacement_run=replacement_search_run(
                order_ids=(REPLACEMENT_ORDER,),
            ),
            replacement_candidates=(placed_after_completion,),
        )
        self.assertIs(future_result.replacement.status, ReplacementStatus.BLOCKED)
        self.assertIs(
            future_result.workflow_state,
            WorkflowState.POSSIBLE_REPLACEMENT_HUMAN_REVIEW,
        )
        self.assertIn(SalesCreditReason.CONTRADICTORY_FACTS, future_result.reasons)

    def test_forged_or_out_of_window_replacement_facts_fail_closed(self) -> None:
        parent = self.canceled(lines=(line(40, es="123"),))
        candidate = snapshot(
            snapshot_index=8,
            order_id=REPLACEMENT_ORDER,
            placed_at=CanonicalTimestamp("2026-08-26T15:00:00Z"),
            captured_at=CanonicalTimestamp("2026-08-26T16:00:00Z"),
            lines=(line(41, es="123"),),
        )
        result = evaluate(
            parent,
            replacement_run=replacement_search_run(
                order_ids=(REPLACEMENT_ORDER,),
                started_at="2026-08-26T15:10:00Z",
                completed_at="2026-08-26T15:30:00Z",
            ),
            replacement_candidates=(replacement_input(candidate),),
            evaluated_at=CanonicalTimestamp("2026-08-26T17:00:00Z"),
        )
        self.assertIs(
            result.workflow_state,
            WorkflowState.CANCELED_NO_REPLACEMENT,
        )
        self.assertIn(
            SalesCreditReason.ORDER_AFTER_REPLACEMENT_WINDOW,
            result.reasons,
        )

        before_cancellation = snapshot(
            snapshot_index=9,
            order_id=REPLACEMENT_ORDER,
            placed_at=CanonicalTimestamp("2026-08-11T15:00:00Z"),
            lines=(line(42, es="123"),),
        )
        result = evaluate(
            parent,
            replacement_run=replacement_search_run(
                order_ids=(REPLACEMENT_ORDER,),
            ),
            replacement_candidates=(replacement_input(before_cancellation),),
        )
        self.assertIs(
            result.workflow_state,
            WorkflowState.CANCELED_REPLACEMENT_WINDOW_ACTIVE,
        )
        self.assertIn(SalesCreditReason.ORDER_BEFORE_CANCELLATION, result.reasons)

        imprecise_same_day = dataclasses.replace(
            before_cancellation,
            placed_at_precision=TimestampPrecision.HISTORICAL_APPROXIMATION,
        )
        imprecise_result = evaluate(
            parent,
            replacement_run=replacement_search_run(
                order_ids=(REPLACEMENT_ORDER,),
                started_at="2026-08-26T15:10:00Z",
                completed_at="2026-08-26T15:30:00Z",
            ),
            replacement_candidates=(replacement_input(imprecise_same_day),),
            evaluated_at=CanonicalTimestamp("2026-08-26T17:00:00Z"),
        )
        self.assertIs(
            imprecise_result.workflow_state,
            WorkflowState.POSSIBLE_REPLACEMENT_HUMAN_REVIEW,
        )
        self.assertIs(
            imprecise_result.replacement.status,
            ReplacementStatus.BLOCKED,
        )
        self.assertIn(
            SalesCreditReason.ORDER_TIMING_UNCERTAIN,
            imprecise_result.reasons,
        )

        partial_after_window = snapshot(
            snapshot_index=11,
            order_id=REPLACEMENT_ORDER,
            extraction_status=SnapshotStatus.PARTIAL,
            placed_at=CanonicalTimestamp("2026-08-26T15:00:00Z"),
            captured_at=CanonicalTimestamp("2026-08-26T16:00:00Z"),
            customer_ids=(),
            warnings=("CUSTOMERS_INCOMPLETE", "LINES_INCOMPLETE"),
        )
        result = evaluate(
            parent,
            replacement_run=replacement_search_run(
                order_ids=(REPLACEMENT_ORDER,),
                started_at="2026-08-26T15:10:00Z",
                completed_at="2026-08-26T15:30:00Z",
            ),
            replacement_candidates=(
                replacement_input(
                    partial_after_window,
                    line_universe_complete=False,
                ),
            ),
            evaluated_at=CanonicalTimestamp("2026-08-26T17:00:00Z"),
        )
        self.assertIs(result.workflow_state, WorkflowState.CANCELED_NO_REPLACEMENT)
        candidate_result = result.replacement.candidate_results[0]
        self.assertIs(candidate_result.status, ReplacementStatus.NOT_CONTINUATION)
        self.assertIs(
            candidate_result.customer_continuity,
            CustomerContinuityStatus.UNKNOWN,
        )
        self.assertIs(
            candidate_result.product_continuity,
            ProductContinuityStatus.UNKNOWN,
        )
        self.assertEqual(
            candidate_result.reasons,
            (SalesCreditReason.ORDER_AFTER_REPLACEMENT_WINDOW,),
        )

        captured_before_placed = snapshot(
            snapshot_index=12,
            order_id=REPLACEMENT_ORDER,
            placed_at=CanonicalTimestamp("2026-08-13T16:00:00Z"),
            lines=(line(43, es="123"),),
        )
        result = evaluate(
            parent,
            replacement_run=replacement_search_run(
                order_ids=(REPLACEMENT_ORDER,),
            ),
            replacement_candidates=(replacement_input(captured_before_placed),),
        )
        self.assertIs(
            result.workflow_state,
            WorkflowState.POSSIBLE_REPLACEMENT_HUMAN_REVIEW,
        )
        self.assertIn(SalesCreditReason.CONTRADICTORY_FACTS, result.reasons)
        self.assertIn(
            SalesCreditReason.AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW,
            result.reasons,
        )


class HistoricalSnapshotTests(unittest.TestCase):
    def test_prior_material_change_is_order_invariant_and_cannot_disappear(self) -> None:
        material = snapshot(
            snapshot_index=80,
            captured_at=CanonicalTimestamp("2026-08-11T18:00:00Z"),
            material_changes=(change(80, MaterialChangeKind.PRODUCT_ADDITION),),
        )
        clean = snapshot(
            snapshot_index=81,
            captured_at=CanonicalTimestamp("2026-08-12T15:00:00Z"),
        )
        current = snapshot(snapshot_index=82)
        forward = evaluate(current, prior_snapshots=(material, clean))
        reversed_result = evaluate(current, prior_snapshots=(clean, material))
        self.assertEqual(forward, reversed_result)
        self.assertIs(
            forward.workflow_state,
            WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
        )
        self.assertIs(forward.value.status, OrderValueStatus.CHANGED_REVIEW)
        self.assertIn(SalesCreditReason.MATERIAL_CHANGE_DETECTED, forward.reasons)

    def test_conflicting_placed_value_cannot_be_overwritten_by_current(self) -> None:
        prior = snapshot(
            snapshot_index=83,
            captured_at=CanonicalTimestamp("2026-08-11T18:00:00Z"),
            placed_value=money("90.00"),
        )
        result = evaluate(snapshot(snapshot_index=84), prior_snapshots=(prior,))
        self.assertIs(
            result.workflow_state,
            WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
        )
        self.assertIs(result.value.status, OrderValueStatus.UNKNOWN)
        self.assertIsNone(result.value.placed_value)
        self.assertIn(SalesCreditReason.CONTRADICTORY_FACTS, result.reasons)

    def test_stable_historical_placed_value_survives_current_omission(self) -> None:
        prior = snapshot(
            snapshot_index=85,
            captured_at=CanonicalTimestamp("2026-08-11T18:00:00Z"),
        )
        current = snapshot(snapshot_index=86, placed_value=None)
        result = evaluate(current, prior_snapshots=(prior,))
        self.assertIs(result.value.status, OrderValueStatus.PLACED_VALUE_VERIFIED)
        self.assertEqual(result.value.placed_value, money())
        self.assertIs(
            result.workflow_state,
            WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
        )

    def test_prior_cancellation_cannot_silently_reopen_as_active(self) -> None:
        canceled = snapshot(
            snapshot_index=87,
            lifecycle_status=OrderLifecycleStatus.CANCELED,
            raw_order_status="canceled",
            canceled_at=CANCELED_AT,
            captured_at=CanonicalTimestamp("2026-08-11T18:00:00Z"),
        )
        result = evaluate(snapshot(snapshot_index=88), prior_snapshots=(canceled,))
        self.assertIs(result.workflow_state, WorkflowState.MANUAL_REVIEW_REQUIRED)
        self.assertIn(SalesCreditReason.CONTRADICTORY_FACTS, result.reasons)
        self.assertTrue(result.human_review_required)

    def test_immutable_order_times_cannot_be_rewritten_by_a_later_snapshot(self) -> None:
        moved_placement = snapshot(
            snapshot_index=92,
            placed_at=CanonicalTimestamp("2026-08-10T13:00:00Z"),
            captured_at=CanonicalTimestamp("2026-08-11T18:00:00Z"),
        )
        changed_precision = snapshot(
            snapshot_index=93,
            placed_at=CanonicalTimestamp("2026-08-10T15:00:00Z"),
            placed_at_precision=TimestampPrecision.CORRECTED,
            captured_at=CanonicalTimestamp("2026-08-11T18:00:00Z"),
        )
        current = snapshot(
            snapshot_index=94,
            placed_at=CanonicalTimestamp("2026-08-10T15:00:00Z"),
        )
        for prior in (moved_placement, changed_precision):
            with self.subTest(snapshot_id=prior.snapshot_id.value):
                result = evaluate(current, prior_snapshots=(prior,))
                self.assertIs(
                    result.workflow_state,
                    WorkflowState.MANUAL_REVIEW_REQUIRED,
                )
                self.assertIn(SalesCreditReason.CONTRADICTORY_FACTS, result.reasons)
                self.assertTrue(result.human_review_required)

        prior_canceled = snapshot(
            snapshot_index=95,
            lifecycle_status=OrderLifecycleStatus.CANCELED,
            raw_order_status="canceled",
            canceled_at=CanonicalTimestamp("2026-08-11T15:00:00Z"),
            captured_at=CanonicalTimestamp("2026-08-11T18:00:00Z"),
        )
        current_canceled = snapshot(
            snapshot_index=96,
            lifecycle_status=OrderLifecycleStatus.CANCELED,
            raw_order_status="canceled",
            canceled_at=CANCELED_AT,
        )
        canceled_result = evaluate(
            current_canceled,
            prior_snapshots=(prior_canceled,),
        )
        self.assertIs(
            canceled_result.workflow_state,
            WorkflowState.MANUAL_REVIEW_REQUIRED,
        )
        self.assertIn(
            SalesCreditReason.CONTRADICTORY_FACTS,
            canceled_result.reasons,
        )

    def test_complete_line_deltas_derive_material_review_without_annotations(self) -> None:
        prior_line = line(500, es="123", quantity=1, line_value="10.00")
        cases = (
            (
                (line(501, es="123", quantity=1, line_value="10.00"),),
                MaterialChangeKind.PRODUCT_ADDITION,
            ),
            (
                (line(500, es="999", quantity=1, line_value="10.00"),),
                MaterialChangeKind.SUBSTITUTION,
            ),
            (
                (line(500, es="123", quantity=2, line_value="10.00"),),
                MaterialChangeKind.QUANTITY_CHANGE,
            ),
            (
                (line(500, es="123", quantity=1, line_value="11.00"),),
                MaterialChangeKind.PRICE_ADJUSTMENT,
            ),
        )
        for index, (current_lines, expected_change) in enumerate(cases, start=97):
            with self.subTest(change=expected_change.value):
                prior = snapshot(
                    snapshot_index=110 + index,
                    lines=(prior_line,),
                    captured_at=CanonicalTimestamp("2026-08-11T18:00:00Z"),
                )
                current = snapshot(snapshot_index=index, lines=current_lines)
                result = evaluate(current, prior_snapshots=(prior,))
                self.assertIs(
                    result.workflow_state,
                    WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
                )
                self.assertIs(result.value.status, OrderValueStatus.CHANGED_REVIEW)
                self.assertIn(expected_change, result.value.material_changes)
                self.assertIn(
                    SalesCreditReason.MATERIAL_CHANGE_DETECTED,
                    result.reasons,
                )

    def test_prior_history_identity_uniqueness_and_chronology_are_exact(self) -> None:
        current = snapshot(snapshot_index=89)
        stale = snapshot(
            snapshot_index=90,
            captured_at=CanonicalTimestamp("2026-08-12T16:00:00.000000001Z"),
        )
        wrong_order = snapshot(
            snapshot_index=91,
            order_id=REPLACEMENT_ORDER,
            captured_at=CanonicalTimestamp("2026-08-11T18:00:00Z"),
        )
        duplicate_current = snapshot(
            snapshot_index=89,
            captured_at=CanonicalTimestamp("2026-08-11T18:00:00Z"),
        )
        for history, code in (
            ((stale,), "prior_snapshot_chronology"),
            ((wrong_order,), "prior_snapshot_identity"),
            ((duplicate_current,), "prior_snapshots_duplicate"),
        ):
            with self.subTest(code=code):
                with self.assertRaisesRegex(SalesCreditEvaluationError, code):
                    evaluate(current, prior_snapshots=history)


class ExplanationAndSafetyTests(unittest.TestCase):
    def test_explanation_is_closed_deterministic_and_contains_no_doi_reason(self) -> None:
        source = snapshot()
        first = evaluate(source)
        second = evaluate(source)
        self.assertEqual(first, second)
        self.assertEqual(first.canonical_bytes(), second.canonical_bytes())
        self.assertEqual(first.rule_pack_version, SALES_CREDIT_RULE_PACK_VERSION)
        self.assertTrue(set(first.rules_fired).issubset(first.rules_evaluated))
        self.assertTrue(all(type(reason) is SalesCreditReason for reason in first.reasons))
        self.assertNotIn("RC-", first.canonical_bytes().decode("utf-8"))
        self.assertNotIn("target_rep", repr(first))
        self.assertEqual(
            first.persistence_effects,
            (
                SalesCreditEffect.ACTIVE_CASE_CLASSIFICATION,
                SalesCreditEffect.NO_PERSISTENCE_MILESTONE_2,
            ),
        )

    def test_wrong_shapes_and_private_payloads_reject_without_echo(self) -> None:
        marker = "synthetic:private-evaluator-canary"

        class Hostile:
            def __repr__(self) -> str:
                return marker

        with self.assertRaises(SalesCreditEvaluationError) as caught:
            evaluate_sales_credit(
                evaluation_id=EvaluationId("SYN-EVALUATION-SC-EVAL-0099"),
                expected_order_id=ORDER,
                snapshot=Hostile(),  # type: ignore[arg-type]
                evaluated_at=EVALUATED_AT,
                known_other_reps=KNOWN_OTHER_REPS,
            )
        self.assertNotIn(marker, str(caught.exception))
        self.assertNotIn(marker, repr(caught.exception))

        for overrides in (
            {"replacement_run": Hostile()},
            {"replacement_candidates": [replacement_input(snapshot())]},
            {"prior_snapshots": [snapshot()]},
        ):
            with self.subTest(fields=tuple(overrides)):
                with self.assertRaises(SalesCreditEvaluationError) as rejected:
                    evaluate(snapshot(), **overrides)  # type: ignore[arg-type]
                self.assertNotIn(marker, str(rejected.exception))

        with self.assertRaises(SalesCreditEvaluationError):
            evaluate_sales_credit(
                evaluation_id=EvaluationId("SYN-EVALUATION-SC-EVAL-0098"),
                expected_order_id=ORDER,
                snapshot=snapshot(),
                evaluated_at=EVALUATED_AT,
                known_other_reps=frozenset({"target_rep"}),
            )

    def test_evidence_ordering_duplicates_and_alias_collections_fail_closed(self) -> None:
        first = evidence(50)
        second = evidence(51)
        with self.assertRaises(SalesCreditEvaluationError):
            classify_evidence(
                (second, first),
                order_at=ORDER_AT,
                order_precision=TimestampPrecision.EXACT,
            )
        with self.assertRaises(SalesCreditEvaluationError):
            evaluate(
                snapshot(raw_order_rep="unassigned_web"),
                events=(first, first),
            )
        with self.assertRaises(SalesCreditEvaluationError):
            evaluate_sales_credit(
                evaluation_id=EvaluationId("SYN-EVALUATION-SC-EVAL-0097"),
                expected_order_id=ORDER,
                snapshot=snapshot(),
                evaluated_at=EVALUATED_AT,
                known_other_reps={"synthetic_other_rep"},  # type: ignore[arg-type]
            )

        with self.assertRaisesRegex(
            SalesCreditEvaluationError,
            "known_other_reps_version",
        ):
            evaluate_sales_credit(
                evaluation_id=EvaluationId("SYN-EVALUATION-SC-EVAL-0096"),
                expected_order_id=ORDER,
                snapshot=snapshot(),
                evaluated_at=EVALUATED_AT,
                known_other_reps=frozenset(
                    {"synthetic_other_rep", "synthetic_other_rep_2"}
                ),
            )


if __name__ == "__main__":
    unittest.main()
