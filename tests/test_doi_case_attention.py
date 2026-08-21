from __future__ import annotations

import dataclasses
import unittest

from synthetic_sales_assist.doi.case_attention import (
    AttentionOwnerDecision,
    AttentionOwnerHistory,
    CaseAttentionOwnerError,
    CaseOwnerDecision,
    CaseOwnerHistory,
    attention_owner_transition_ids,
    case_attention_hash_contracts,
    case_attention_hash_fixtures,
    case_owner_transition_ids,
    clear_human_coordination_review_from_evaluation,
    clear_human_coordination_review_from_human_fact,
    clear_intervention_verification_from_action,
    clear_recheck_from_complete_evaluation,
    clear_resulting_link_review_from_exact_link,
    clear_resulting_link_review_from_not_found_search,
    clear_source_absence_from_complete_evaluation,
    issue_case_creation_decision,
    issue_case_refresh_decision,
    replace_source_absence_with_failed_recheck,
    set_human_coordination_review_from_wwc,
    set_intervention_verification_from_changed_evaluation,
    set_recheck_from_failed_extraction,
    set_resulting_link_review_from_ambiguous_search,
    set_resulting_link_review_from_mapping_conflict,
    set_source_absence_from_evaluation,
    validate_attention_owner_decision,
    validate_case_owner_decision,
)
from synthetic_sales_assist.doi.evaluator import evaluate_doi
from synthetic_sales_assist.doi.extraction import (
    DOIExtractionAttempt,
    DOIExtractionResult,
    ExtractionStatus,
)
from synthetic_sales_assist.doi.identities import (
    DoiOrderId,
    ExtractionAttemptId,
    RunWorkItemId,
    SourceBatchId,
)
from synthetic_sales_assist.doi.interventions import (
    DOIResultingOrderLinkSearchHistory,
    InterventionError,
    ResultingLinkSearchEvidence,
    append_resulting_link_revision,
    append_resulting_link_search,
    record_verified_intervention,
)
from synthetic_sales_assist.domain.canonical import domain_hash
from synthetic_sales_assist.doi.models import (
    ActionContextKind,
    AttentionCondition,
    CaseLifecycleState,
    DOIHumanFactEvent,
    DOIHumanFactHistory,
    DOIEvaluationInput,
    DOIModelError,
    DOIOccurrenceGuard,
    DOIOrderCase,
    DOIWWCEvent,
    DOIWWCHistory,
    HumanFactEventType,
    HumanFactResultCode,
    HumanFactUsageKind,
    InterventionType,
    SourcePresence,
    StructuredHumanFact,
    WWCAuthorRelation,
    WWCEventType,
    WWCProjectionState,
    WWCTimingState,
    reduce_human_fact,
    reduce_wwc,
    unknown_fact,
    verify_synthetic_human_authority,
)
from synthetic_sales_assist.doi.source import (
    DOIRunWorkItem,
    RunWorkOrigin,
    ingest_synthetic_queue,
)
from synthetic_sales_assist.domain.identities import (
    EvidenceId,
    EvaluationId,
    InteractionId,
    OrderId,
    RepId,
    RunId,
)
from synthetic_sales_assist.domain.numeric import NonNegativeCount
from synthetic_sales_assist.domain.observed import FindingPresenceV2
from synthetic_sales_assist.domain.records import (
    ReasonSet,
    SourceKind,
    SourceObjectNamespace,
    SourceRef,
)
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from tests.test_doi_evaluator import evaluation_input, split_lines
from tests.test_doi_interventions import (
    _action,
    _completed_system_action_proof,
    _mapping,
    _revision,
    _order_source as intervention_order_source,
)
from tests.test_doi_models import (
    OBSERVED_AT,
    interaction_source,
    make_line,
    make_snapshot,
    make_wwc,
    open_context_fixture,
    order_source,
)
from tests.test_doi_source import _batch_id, _image, _row


CASE_ID = EvidenceId("SYN-EVIDENCE-CASE-ATTENTION-OWNER")
ORDER = DoiOrderId(OrderId("SYN-ORDER-DOI-0001"))


def _source_result(suffix: str = "CASE"):
    # The source normalizer deliberately distinguishes an already-firewalled
    # OrderId from a raw queue string whose numeric core must be normalized.
    image = _image((_row(1, ORDER.value),))
    return ingest_synthetic_queue(
        image,
        image,
        candidate_batch_id=SourceBatchId(
            EvidenceId(f"SYN-EVIDENCE-DOI-BATCH-{suffix}")
        ),
    )


def _source_work(result, suffix: str = "CASE") -> DOIRunWorkItem:  # type: ignore[no-untyped-def]
    assert result.batch is not None
    return DOIRunWorkItem(
        work_item_id=RunWorkItemId(
            InteractionId(f"SYN-INTERACTION-CASE-WORK-{suffix}")
        ),
        run_id=RunId(f"SYN-RUN-CASE-WORK-{suffix}"),
        order_id=ORDER.value,
        origin=RunWorkOrigin.SOURCE_IMPORT,
        source_batch_id=result.batch.batch_id,
    )


def _case_creation(suffix: str = "BASE") -> CaseOwnerDecision:
    result = _source_result(suffix)
    assert result.batch is not None
    return issue_case_creation_decision(
        history=CaseOwnerHistory(CASE_ID, ORDER),
        event_id=EvidenceId(f"SYN-EVIDENCE-CASE-CREATED-{suffix}"),
        binding_id=EvidenceId(f"SYN-EVIDENCE-CASE-SOURCE-BINDING-{suffix}"),
        admission_proof_id=EvidenceId(f"SYN-EVIDENCE-CASE-ADMISSION-{suffix}"),
        source_result=result,
        staged_order=result.batch.staged_orders[0],
        work_item=_source_work(result, suffix),
        admitted_at=CanonicalTimestamp("2026-08-20T12:00:00Z"),
    )


def _case_for_evaluation(case_id: EvidenceId, request: DOIEvaluationInput) -> DOIOrderCase:
    result = evaluate_doi(request)
    return DOIOrderCase(
        case_id=case_id,
        order_id=request.snapshot.order_id,
        lifecycle_state=CaseLifecycleState.ACTIVE,
        current_snapshot_id=request.snapshot.snapshot_id,
        current_evaluation_id=result.evaluation_id,
        terminal_closure_reason=None,
    )


def _failed_extraction(
    *,
    suffix: str,
    at: str = "2026-08-20T14:16:00Z",
) -> DOIExtractionResult:
    attempt = DOIExtractionAttempt(
        attempt_id=ExtractionAttemptId(
            InteractionId(f"SYN-INTERACTION-FAILED-EXTRACTION-{suffix}")
        ),
        run_id=request_run_id(suffix),
        order_id=ORDER,
        started_at=CanonicalTimestamp("2026-08-20T14:15:30Z"),
        completed_at=CanonicalTimestamp(at),
        status=ExtractionStatus.FAILED,
        snapshot_id=None,
        reasons=reason_set("RC-011", "RC-014", "RC-015"),
        portal_read_count=NonNegativeCount(1),
    )
    return DOIExtractionResult(
        attempt=attempt,
        snapshot=None,
        attention_conditions=(AttentionCondition.RECHECK_REQUIRED,),
    )


def request_run_id(suffix: str):  # type: ignore[no-untyped-def]
    from synthetic_sales_assist.doi.identities import DoiRunId

    return DoiRunId(RunId(f"SYN-RUN-FAILED-EXTRACTION-{suffix}"))


def reason_set(*codes: str) -> ReasonSet:
    from synthetic_sales_assist.domain.registries import load_doi_registries

    registry = load_doi_registries()
    return ReasonSet(tuple(registry.reason_ref(code) for code in sorted(codes)))


def _successful_extraction(request: DOIEvaluationInput, suffix: str) -> DOIExtractionResult:
    snapshot = request.snapshot
    return DOIExtractionResult(
        attempt=DOIExtractionAttempt(
            attempt_id=ExtractionAttemptId(
                InteractionId(f"SYN-INTERACTION-SUCCESS-EXTRACTION-{suffix}")
            ),
            run_id=snapshot.run_id,
            order_id=snapshot.order_id,
            started_at=CanonicalTimestamp("2026-08-20T14:16:30Z"),
            completed_at=CanonicalTimestamp("2026-08-20T14:16:45Z"),
            status=ExtractionStatus.SUCCEEDED,
            snapshot_id=snapshot.snapshot_id,
            reasons=ReasonSet(),
            portal_read_count=NonNegativeCount(1),
        ),
        snapshot=snapshot,
        attention_conditions=(),
    )


def _attention_history(case: DOIOrderCase) -> AttentionOwnerHistory:
    return AttentionOwnerHistory(case.case_id, case.order_id)


def _interaction_guard(
    *,
    event_id: EvidenceId,
    stream_id: EvidenceId,
    suffix: str,
    source: SourceRef | None = None,
) -> DOIOccurrenceGuard:
    occurrence = (
        source.object_id
        if source is not None
        else InteractionId(f"SYN-INTERACTION-CASE-ATTN-{suffix}")
    )
    if type(occurrence) is not InteractionId:
        raise AssertionError("interaction guard source must retain an interaction id")
    bound_source = source or SourceRef.create(
        source_ref_id=EvidenceId(f"SYN-EVIDENCE-CASE-ATTN-SOURCE-{suffix}"),
        source_kind=SourceKind.SYNTHETIC_INTERACTION_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_INTERACTION,
        object_id=occurrence,
    )
    return DOIOccurrenceGuard(
        guard_id=event_id,
        owner_id=stream_id,
        occurrence_id=occurrence,
        source=bound_source,
    )


class DOICaseOwnerTests(unittest.TestCase):
    def test_tr007_is_minimized_sealed_and_replay_validated(self) -> None:
        decision = _case_creation()
        self.assertIsInstance(decision, CaseOwnerDecision)
        self.assertEqual(decision.transition_id, "TR-007")
        self.assertEqual(case_owner_transition_ids(), ("TR-007", "TR-008"))
        self.assertIs(validate_case_owner_decision(decision), decision)
        projection = decision.result.history.projection
        assert projection is not None
        self.assertIsNone(projection.current_snapshot_id)
        self.assertIsNone(projection.current_evaluation_id)
        proof_text = (
            decision.result.event.source_binding.admission_proof.canonical_bytes().decode()
        )
        for forbidden in ("attempt", "row", "tab", "actor", "work_item", "run_id"):
            self.assertNotIn(forbidden, proof_text)
        with self.assertRaises(CaseAttentionOwnerError):
            CaseOwnerDecision()  # type: ignore[call-arg]
        with self.assertRaisesRegex(
            CaseAttentionOwnerError,
            "CASE_OWNER_DECISION_INVALID",
        ):
            validate_case_owner_decision(object.__new__(CaseOwnerDecision))

    def test_tr007_rejects_wrong_order_batch_and_retained_case(self) -> None:
        result = _source_result("WRONG")
        assert result.batch is not None
        staged = result.batch.staged_orders[0]
        work = _source_work(result, "WRONG")
        with self.assertRaisesRegex(
            CaseAttentionOwnerError,
            "CASE_SOURCE_ADMISSION_INVALID",
        ):
            issue_case_creation_decision(
                history=CaseOwnerHistory(CASE_ID, ORDER),
                event_id=EvidenceId("SYN-EVIDENCE-WRONG-BATCH-CREATE"),
                binding_id=EvidenceId("SYN-EVIDENCE-WRONG-BATCH-BINDING"),
                admission_proof_id=EvidenceId("SYN-EVIDENCE-WRONG-BATCH-PROOF"),
                source_result=result,
                staged_order=staged,
                work_item=dataclasses.replace(
                    work,
                    source_batch_id=_batch_id("WRONG-OWNER-BATCH"),
                ),
                admitted_at=OBSERVED_AT,
            )
        with self.assertRaisesRegex(CaseAttentionOwnerError, "CASE_ORDER_SCOPE_INVALID"):
            issue_case_creation_decision(
                history=CaseOwnerHistory(
                    EvidenceId("SYN-EVIDENCE-WRONG-CASE"),
                    DoiOrderId(OrderId("SYN-ORDER-DIFFERENT")),
                ),
                event_id=EvidenceId("SYN-EVIDENCE-WRONG-CREATE"),
                binding_id=EvidenceId("SYN-EVIDENCE-WRONG-BINDING"),
                admission_proof_id=EvidenceId("SYN-EVIDENCE-WRONG-PROOF"),
                source_result=result,
                staged_order=staged,
                work_item=work,
                admitted_at=OBSERVED_AT,
            )
        created = _case_creation("RETAINED")
        with self.assertRaisesRegex(CaseAttentionOwnerError, "CASE_ALREADY_RETAINED"):
            issue_case_creation_decision(
                history=created.result.history,
                event_id=EvidenceId("SYN-EVIDENCE-DUPLICATE-CREATE"),
                binding_id=EvidenceId("SYN-EVIDENCE-DUPLICATE-BINDING"),
                admission_proof_id=EvidenceId("SYN-EVIDENCE-DUPLICATE-PROOF"),
                source_result=result,
                staged_order=staged,
                work_item=work,
                admitted_at=OBSERVED_AT,
            )

    def test_tr008_refresh_binds_current_complete_evaluation_and_history(self) -> None:
        created = _case_creation("REFRESH")
        request = evaluation_input(
            split_lines(),
            evaluation_suffix="CASE-REFRESH",
            snapshot_suffix="CASE-REFRESH",
            run_suffix="CASE-REFRESH",
        )
        evaluation = evaluate_doi(request)
        work = DOIRunWorkItem(
            work_item_id=RunWorkItemId(
                InteractionId("SYN-INTERACTION-CASE-REFRESH-WORK")
            ),
            run_id=request.snapshot.run_id.value,
            order_id=request.snapshot.order_id.value,
            origin=RunWorkOrigin.ORDER_RECHECK,
            source_batch_id=None,
        )
        decision = issue_case_refresh_decision(
            history=created.result.history,
            event_id=EvidenceId("SYN-EVIDENCE-CASE-REFRESH-EVENT"),
            work_item=work,
            extraction_result=_successful_extraction(request, "CASE-REFRESH"),
            evaluation_input=request,
            evaluation=evaluation,
        )
        self.assertEqual(decision.transition_id, "TR-008")
        self.assertIs(validate_case_owner_decision(decision), decision)
        self.assertEqual(
            decision.result.history.projection.current_evaluation_id,
            evaluation.evaluation_id,
        )
        omitted = dataclasses.replace(
            created.result.history,
            events=(),
            projection=None,
            source_binding=None,
        )
        with self.assertRaises(CaseAttentionOwnerError):
            issue_case_refresh_decision(
                history=omitted,
                event_id=EvidenceId("SYN-EVIDENCE-CASE-REFRESH-OMITTED"),
                work_item=work,
                extraction_result=_successful_extraction(request, "OMITTED"),
                evaluation_input=request,
                evaluation=evaluation,
            )
        wrong = dataclasses.replace(
            evaluation,
            evaluation_id=EvaluationId("SYN-EVALUATION-WRONG-REFRESH"),
        )
        with self.assertRaises(CaseAttentionOwnerError):
            issue_case_refresh_decision(
                history=created.result.history,
                event_id=EvidenceId("SYN-EVIDENCE-CASE-REFRESH-WRONG"),
                work_item=work,
                extraction_result=_successful_extraction(request, "WRONG"),
                evaluation_input=request,
                evaluation=wrong,
            )

        later_source = _source_result("REFRESH-LATER-SOURCE")
        assert later_source.batch is not None
        later_work = DOIRunWorkItem(
            work_item_id=RunWorkItemId(
                InteractionId("SYN-INTERACTION-CASE-REFRESH-LATER-SOURCE-WORK")
            ),
            run_id=request.snapshot.run_id.value,
            order_id=request.snapshot.order_id.value,
            origin=RunWorkOrigin.SOURCE_IMPORT,
            source_batch_id=later_source.batch.batch_id,
        )
        admitted_at = CanonicalTimestamp("2026-08-20T13:00:00Z")
        later_admission = issue_case_refresh_decision(
            history=created.result.history,
            event_id=EvidenceId("SYN-EVIDENCE-CASE-REFRESH-LATER-SOURCE-EVENT"),
            work_item=later_work,
            extraction_result=_successful_extraction(request, "LATER-SOURCE"),
            evaluation_input=request,
            evaluation=evaluation,
            source_result=later_source,
            staged_order=later_source.batch.staged_orders[0],
            binding_id=EvidenceId(
                "SYN-EVIDENCE-CASE-REFRESH-LATER-SOURCE-BINDING"
            ),
            admission_proof_id=EvidenceId(
                "SYN-EVIDENCE-CASE-REFRESH-LATER-SOURCE-PROOF"
            ),
            admitted_at=admitted_at,
        )
        self.assertEqual(
            later_admission.result.event.source_binding.admission_proof.admitted_at,
            admitted_at,
        )
        self.assertIs(validate_case_owner_decision(later_admission), later_admission)
        with self.assertRaisesRegex(
            CaseAttentionOwnerError,
            "CASE_REFRESH_ADMISSION_TIME_INVALID",
        ):
            issue_case_refresh_decision(
                history=created.result.history,
                event_id=EvidenceId("SYN-EVIDENCE-CASE-REFRESH-BACKDATED-EVENT"),
                work_item=later_work,
                extraction_result=_successful_extraction(request, "BACKDATED"),
                evaluation_input=request,
                evaluation=evaluation,
                source_result=later_source,
                staged_order=later_source.batch.staged_orders[0],
                binding_id=EvidenceId(
                    "SYN-EVIDENCE-CASE-REFRESH-BACKDATED-BINDING"
                ),
                admission_proof_id=EvidenceId(
                    "SYN-EVIDENCE-CASE-REFRESH-BACKDATED-PROOF"
                ),
                admitted_at=CanonicalTimestamp("2026-08-20T11:59:59Z"),
            )


class DOIAttentionExtractionTests(unittest.TestCase):
    def test_tr020_tr021_tr022_and_tr024_are_typed_and_preserve_unrelated_causes(self) -> None:
        base = evaluation_input(
            split_lines(),
            evaluation_suffix="ATTN-BASE",
            snapshot_suffix="ATTN-BASE",
            run_suffix="ATTN-BASE",
        )
        absent_snapshot = dataclasses.replace(
            base.snapshot,
            source_presence=SourcePresence.ABSENT_RECHECK_REQUIRED,
        )
        absent_request = dataclasses.replace(base, snapshot=absent_snapshot)
        absent_evaluation = evaluate_doi(absent_request)
        case = _case_for_evaluation(CASE_ID, absent_request)
        initial = _attention_history(case)
        absence = set_source_absence_from_evaluation(
            history=initial,
            case=case,
            event_id=EvidenceId("SYN-EVIDENCE-ATTN-ABSENCE-SET"),
            evaluation_input=absent_request,
            evaluation=absent_evaluation,
        )
        self.assertEqual(absence.transition_id, "TR-021")
        self.assertIs(validate_attention_owner_decision(absence), absence)
        failed = _failed_extraction(suffix="PARALLEL")
        recheck = set_recheck_from_failed_extraction(
            history=absence.result.history,
            case=case,
            event_id=EvidenceId("SYN-EVIDENCE-ATTN-RECHECK-SET"),
            extraction_result=failed,
        )
        self.assertEqual(recheck.transition_id, "TR-020")
        self.assertEqual(len(recheck.result.history.active), 2)

        replacement = replace_source_absence_with_failed_recheck(
            history=recheck.result.history,
            case=case,
            event_id=EvidenceId("SYN-EVIDENCE-ATTN-ABSENCE-REPLACE"),
            active_set_event_id=absence.result.event.event_id,
            extraction_result=_failed_extraction(suffix="ABSENCE-VERIFY"),
        )
        self.assertEqual(replacement.transition_id, "TR-022")
        self.assertEqual(
            {item.condition for item in replacement.result.history.active},
            {AttentionCondition.RECHECK_REQUIRED},
        )
        self.assertEqual(len(replacement.result.history.active), 2)

        later_at = CanonicalTimestamp("2026-08-20T14:17:00Z")
        later_snapshot = make_snapshot(
            split_lines(),
            observed_at=later_at,
            snapshot_suffix="ATTN-LATER",
            run_suffix="ATTN-LATER",
        )
        later_request = DOIEvaluationInput(
            evaluation_id=EvaluationId("SYN-EVALUATION-ATTN-LATER"),
            snapshot=later_snapshot,
            evaluated_at=later_at,
        )
        later_evaluation = evaluate_doi(later_request)
        later_case = _case_for_evaluation(CASE_ID, later_request)
        replacement_active = next(
            item
            for item in replacement.result.history.active
            if item.set_event_id == replacement.result.event.event_id
        )
        cleared = clear_recheck_from_complete_evaluation(
            history=replacement.result.history,
            case=later_case,
            event_id=EvidenceId("SYN-EVIDENCE-ATTN-RECHECK-CLEAR"),
            active_set_event_id=replacement_active.set_event_id,
            extraction_result=_successful_extraction(later_request, "ATTN-LATER"),
            evaluation_input=later_request,
            evaluation=later_evaluation,
        )
        self.assertEqual(cleared.transition_id, "TR-024")
        self.assertEqual(len(cleared.result.history.active), 1)
        self.assertEqual(
            cleared.result.history.active[0].set_event_id,
            recheck.result.event.event_id,
        )

    def test_tr023_requires_present_current_evaluation_and_exact_active_set(self) -> None:
        base = evaluation_input(
            split_lines(),
            evaluation_suffix="ATTN-ABSENCE",
            snapshot_suffix="ATTN-ABSENCE",
            run_suffix="ATTN-ABSENCE",
        )
        absent_request = dataclasses.replace(
            base,
            snapshot=dataclasses.replace(
                base.snapshot,
                source_presence=SourcePresence.ABSENT_RECHECK_REQUIRED,
            ),
        )
        absent_eval = evaluate_doi(absent_request)
        case = _case_for_evaluation(CASE_ID, absent_request)
        set_result = set_source_absence_from_evaluation(
            history=_attention_history(case),
            case=case,
            event_id=EvidenceId("SYN-EVIDENCE-ATTN-ABSENCE-023"),
            evaluation_input=absent_request,
            evaluation=absent_eval,
        )
        later = CanonicalTimestamp("2026-08-20T14:17:00Z")
        present_snapshot = make_snapshot(
            split_lines(),
            observed_at=later,
            snapshot_suffix="ATTN-PRESENT",
            run_suffix="ATTN-PRESENT",
        )
        present_request = DOIEvaluationInput(
            evaluation_id=EvaluationId("SYN-EVALUATION-ATTN-PRESENT"),
            snapshot=present_snapshot,
            evaluated_at=later,
        )
        present_eval = evaluate_doi(present_request)
        present_case = _case_for_evaluation(CASE_ID, present_request)
        cleared = clear_source_absence_from_complete_evaluation(
            history=set_result.result.history,
            case=present_case,
            event_id=EvidenceId("SYN-EVIDENCE-ATTN-ABSENCE-CLEAR-023"),
            active_set_event_id=set_result.result.event.event_id,
            extraction_result=_successful_extraction(present_request, "PRESENT"),
            evaluation_input=present_request,
            evaluation=present_eval,
        )
        self.assertEqual(cleared.transition_id, "TR-023")
        self.assertEqual(cleared.result.history.active, ())
        with self.assertRaises(CaseAttentionOwnerError):
            clear_source_absence_from_complete_evaluation(
                history=set_result.result.history,
                case=present_case,
                event_id=EvidenceId("SYN-EVIDENCE-ATTN-WRONG-SET-CLEAR"),
                active_set_event_id=EvidenceId("SYN-EVIDENCE-WRONG-ACTIVE-SET"),
                extraction_result=_successful_extraction(present_request, "WRONG-SET"),
                evaluation_input=present_request,
                evaluation=present_eval,
            )


class DOIAttentionActionAndLinkTests(unittest.TestCase):
    def test_tr025_tr026_require_same_opportunity_and_verified_action_history(self) -> None:
        marker = "attention-action-owner"
        proof = _completed_system_action_proof(
            marker,
            InterventionType.FULFILLMENT_SPLIT,
        )
        changed_request = evaluation_input(
            split_lines(),
            evaluation_suffix="INTERVENTION-SPLIT-OWNER",
        )
        changed = evaluate_doi(changed_request)
        prior_source = order_source(ORDER.value)
        prior_request = evaluation_input(
            (make_line(1, prior_source),),
            evaluation_suffix="ATTN-ACTION-PRIOR",
            snapshot_suffix="ATTN-ACTION-PRIOR",
            run_suffix="ATTN-ACTION-PRIOR",
        )
        prior = evaluate_doi(prior_request)
        case = DOIOrderCase(
            case_id=proof.completed_context.case_id,
            order_id=changed.order_id,
            lifecycle_state=CaseLifecycleState.ACTIVE,
            current_snapshot_id=changed.snapshot_id,
            current_evaluation_id=changed.evaluation_id,
            terminal_closure_reason=None,
        )
        attention = set_intervention_verification_from_changed_evaluation(
            history=_attention_history(case),
            case=case,
            event_id=EvidenceId("SYN-EVIDENCE-ATTN-ACTION-SET"),
            prior_evaluation_input=prior_request,
            prior_evaluation=prior,
            changed_evaluation_input=changed_request,
            changed_evaluation=changed,
        )
        self.assertEqual(attention.transition_id, "TR-025")
        action = _action(
            intervention_type=InterventionType.FULFILLMENT_SPLIT,
            marker=marker,
            event_id="SYN-EVIDENCE-ATTN-ACTION-EVENT",
            evidence_id="SYN-EVIDENCE-ATTN-ACTION-EVIDENCE",
            key_id="SYN-EVIDENCE-ATTN-ACTION-KEY",
        )
        intervention = record_verified_intervention(None, action).intervention
        cleared = clear_intervention_verification_from_action(
            history=attention.result.history,
            case=case,
            event_id=EvidenceId("SYN-EVIDENCE-ATTN-ACTION-CLEAR"),
            active_set_event_id=attention.result.event.event_id,
            action_event=action,
            intervention=intervention,
            completion_proof=proof,
        )
        self.assertEqual(cleared.transition_id, "TR-026")
        self.assertIs(validate_attention_owner_decision(cleared), cleared)
        wrong_action = _action(
            intervention_type=InterventionType.PRODUCT_SUBSTITUTION,
            marker="different-attention-action",
            event_id="SYN-EVIDENCE-ATTN-WRONG-ACTION-EVENT",
            evidence_id="SYN-EVIDENCE-ATTN-WRONG-ACTION-EVIDENCE",
            key_id="SYN-EVIDENCE-ATTN-WRONG-ACTION-KEY",
        )
        with self.assertRaises(CaseAttentionOwnerError):
            clear_intervention_verification_from_action(
                history=attention.result.history,
                case=case,
                event_id=EvidenceId("SYN-EVIDENCE-ATTN-WRONG-ACTION-CLEAR"),
                active_set_event_id=attention.result.event.event_id,
                action_event=wrong_action,
                intervention=record_verified_intervention(None, wrong_action).intervention,
                completion_proof=proof,
            )

    def test_tr092_tr093_search_history_is_exact_and_omission_fails(self) -> None:
        case = _case_for_evaluation(
            CASE_ID,
            evaluation_input(split_lines(), evaluation_suffix="SEARCH-CASE"),
        )
        search_id = EvidenceId("SYN-EVIDENCE-ATTN-SEARCH")
        search = DOIResultingOrderLinkSearchHistory(
            search_id=search_id,
            parent_order_id=case.order_id,
            intervention_type=InterventionType.FULFILLMENT_SPLIT,
        )
        candidates = (
            DoiOrderId(OrderId("SYN-ORDER-ATTN-CHILD-001")),
            DoiOrderId(OrderId("SYN-ORDER-ATTN-CHILD-002")),
        )
        first_evidence = ResultingLinkSearchEvidence.from_complete_search(
            evidence_id=EvidenceId("SYN-EVIDENCE-ATTN-SEARCH-EVIDENCE-001"),
            search_id=search_id,
            parent_order_id=case.order_id,
            intervention_type=InterventionType.FULFILLMENT_SPLIT,
            candidate_order_ids=candidates,
            observed_at=OBSERVED_AT,
            source=intervention_order_source(case.order_id, "ATTN-SEARCH-001"),
        )
        ambiguous = append_resulting_link_search(
            search,
            event_id=EvidenceId("SYN-EVIDENCE-ATTN-SEARCH-EVENT-001"),
            evidence=first_evidence,
        )
        set_result = set_resulting_link_review_from_ambiguous_search(
            history=_attention_history(case),
            case=case,
            event_id=EvidenceId("SYN-EVIDENCE-ATTN-SEARCH-SET"),
            search_history=ambiguous.history,
        )
        self.assertEqual(set_result.transition_id, "TR-092")
        second_evidence = ResultingLinkSearchEvidence.from_complete_search(
            evidence_id=EvidenceId("SYN-EVIDENCE-ATTN-SEARCH-EVIDENCE-002"),
            search_id=search_id,
            parent_order_id=case.order_id,
            intervention_type=InterventionType.FULFILLMENT_SPLIT,
            candidate_order_ids=(),
            disproved_candidate_order_ids=candidates,
            observed_at=CanonicalTimestamp("2026-08-20T14:16:00Z"),
            source=intervention_order_source(case.order_id, "ATTN-SEARCH-002"),
        )
        not_found = append_resulting_link_search(
            ambiguous.history,
            event_id=EvidenceId("SYN-EVIDENCE-ATTN-SEARCH-EVENT-002"),
            evidence=second_evidence,
        )
        cleared = clear_resulting_link_review_from_not_found_search(
            history=set_result.result.history,
            case=case,
            event_id=EvidenceId("SYN-EVIDENCE-ATTN-SEARCH-CLEAR"),
            active_set_event_id=set_result.result.event.event_id,
            search_history=not_found.history,
        )
        self.assertEqual(cleared.transition_id, "TR-093")
        self.assertEqual(cleared.result.history.active, ())
        with self.assertRaises(InterventionError):
            omitted = dataclasses.replace(
                not_found.history,
                events=(not_found.history.events[-1],),
            )
            clear_resulting_link_review_from_not_found_search(
                history=set_result.result.history,
                case=case,
                event_id=EvidenceId("SYN-EVIDENCE-ATTN-SEARCH-OMITTED"),
                active_set_event_id=set_result.result.event.event_id,
                search_history=omitted,
            )
        alternate_candidates = (
            DoiOrderId(OrderId("SYN-ORDER-ATTN-CHILD-003")),
            DoiOrderId(OrderId("SYN-ORDER-ATTN-CHILD-004")),
        )
        alternate_ambiguous = append_resulting_link_search(
            search,
            event_id=EvidenceId("SYN-EVIDENCE-ATTN-SEARCH-ALT-EVENT-001"),
            evidence=ResultingLinkSearchEvidence.from_complete_search(
                evidence_id=EvidenceId(
                    "SYN-EVIDENCE-ATTN-SEARCH-ALT-EVIDENCE-001"
                ),
                search_id=search_id,
                parent_order_id=case.order_id,
                intervention_type=InterventionType.FULFILLMENT_SPLIT,
                candidate_order_ids=alternate_candidates,
                observed_at=OBSERVED_AT,
                source=intervention_order_source(
                    case.order_id,
                    "ATTN-SEARCH-ALT-001",
                ),
            ),
        )
        alternate_not_found = append_resulting_link_search(
            alternate_ambiguous.history,
            event_id=EvidenceId("SYN-EVIDENCE-ATTN-SEARCH-ALT-EVENT-002"),
            evidence=ResultingLinkSearchEvidence.from_complete_search(
                evidence_id=EvidenceId(
                    "SYN-EVIDENCE-ATTN-SEARCH-ALT-EVIDENCE-002"
                ),
                search_id=search_id,
                parent_order_id=case.order_id,
                intervention_type=InterventionType.FULFILLMENT_SPLIT,
                candidate_order_ids=(),
                disproved_candidate_order_ids=alternate_candidates,
                observed_at=CanonicalTimestamp("2026-08-20T14:16:00Z"),
                source=intervention_order_source(
                    case.order_id,
                    "ATTN-SEARCH-ALT-002",
                ),
            ),
        )
        with self.assertRaisesRegex(
            CaseAttentionOwnerError,
            "NEGATIVE_RESULTING_SEARCH_REQUIRED",
        ):
            clear_resulting_link_review_from_not_found_search(
                history=set_result.result.history,
                case=case,
                event_id=EvidenceId("SYN-EVIDENCE-ATTN-SEARCH-ALT-CLEAR"),
                active_set_event_id=set_result.result.event.event_id,
                search_history=alternate_not_found.history,
            )

    def test_tr092_mapping_conflict_and_tr093_exact_link_bind_same_subject(self) -> None:
        action = _action(
            intervention_type=InterventionType.FULFILLMENT_SPLIT,
            marker="attention-link",
            event_id="SYN-EVIDENCE-ATTN-LINK-ACTION",
            evidence_id="SYN-EVIDENCE-ATTN-LINK-ACTION-EVIDENCE",
            key_id="SYN-EVIDENCE-ATTN-LINK-ACTION-KEY",
        )
        intervention = record_verified_intervention(None, action).intervention
        first_evidence = _revision(
            revision_id="SYN-EVIDENCE-ATTN-LINK-REV-001",
            mappings=_mapping(
                intervention=intervention,
                quantity=1,
                marker="attention-link",
            ),
            predecessor=None,
            intervention=intervention,
            marker="attention-link",
        )
        first = append_resulting_link_revision(
            None,
            revision_id=EvidenceId("SYN-EVIDENCE-ATTN-LINK-REV-001"),
            intervention=intervention,
            evidence=first_evidence,
        )
        conflict_evidence = _revision(
            revision_id="SYN-EVIDENCE-ATTN-LINK-REV-002",
            mappings=_mapping(
                intervention=intervention,
                quantity=2,
                marker="attention-link",
            ),
            predecessor=first.link.revisions[-1],
            intervention=intervention,
            rep_verified=False,
            marker="attention-link",
        )
        conflict = append_resulting_link_revision(
            first.link,
            revision_id=EvidenceId("SYN-EVIDENCE-ATTN-LINK-REV-002"),
            intervention=intervention,
            evidence=conflict_evidence,
        )
        context_order = action.evidence.material.source.object_id
        case = DOIOrderCase(
            case_id=EvidenceId("SYN-EVIDENCE-ATTN-LINK-CASE"),
            order_id=DoiOrderId(context_order),
            lifecycle_state=CaseLifecycleState.ACTIVE,
            current_snapshot_id=None,
            current_evaluation_id=None,
            terminal_closure_reason=None,
        )
        set_result = set_resulting_link_review_from_mapping_conflict(
            history=_attention_history(case),
            case=case,
            event_id=EvidenceId("SYN-EVIDENCE-ATTN-LINK-SET"),
            intervention=intervention,
            link=conflict.link,
        )
        resolve_evidence = _revision(
            revision_id="SYN-EVIDENCE-ATTN-LINK-REV-003",
            mappings=_mapping(
                intervention=intervention,
                quantity=1,
                marker="attention-link",
            ),
            predecessor=conflict.link.revisions[-1],
            intervention=intervention,
            human=True,
            resolves_conflict=conflict.link.revisions[-1],
            marker="attention-link",
        )
        resolved = append_resulting_link_revision(
            conflict.link,
            revision_id=EvidenceId("SYN-EVIDENCE-ATTN-LINK-REV-003"),
            intervention=intervention,
            evidence=resolve_evidence,
        )
        cleared = clear_resulting_link_review_from_exact_link(
            history=set_result.result.history,
            case=case,
            event_id=EvidenceId("SYN-EVIDENCE-ATTN-LINK-CLEAR"),
            active_set_event_id=set_result.result.event.event_id,
            intervention=intervention,
            link=resolved.link,
        )
        self.assertEqual(cleared.transition_id, "TR-093")
        wrong_case = dataclasses.replace(
            case,
            case_id=EvidenceId("SYN-EVIDENCE-ATTN-LINK-WRONG-CASE"),
        )
        with self.assertRaises(CaseAttentionOwnerError):
            clear_resulting_link_review_from_exact_link(
                history=set_result.result.history,
                case=wrong_case,
                event_id=EvidenceId("SYN-EVIDENCE-ATTN-LINK-WRONG-CLEAR"),
                active_set_event_id=set_result.result.event.event_id,
                intervention=intervention,
                link=resolved.link,
            )
        different_link_id = EvidenceId("SYN-EVIDENCE-ATTN-DIFFERENT-LINK")
        different_child = DoiOrderId(OrderId("SYN-ORDER-ATTN-DIFFERENT-CHILD"))
        different_evidence = _revision(
            revision_id="SYN-EVIDENCE-ATTN-DIFFERENT-LINK-REV-901",
            mappings=_mapping(
                intervention=intervention,
                link_id=different_link_id,
                child=different_child,
                quantity=1,
                marker="attention-link",
            ),
            predecessor=None,
            intervention=intervention,
            link_id=different_link_id,
            child=different_child,
            marker="attention-link",
        )
        different = append_resulting_link_revision(
            None,
            revision_id=EvidenceId(
                "SYN-EVIDENCE-ATTN-DIFFERENT-LINK-REV-901"
            ),
            intervention=intervention,
            evidence=different_evidence,
        )
        with self.assertRaisesRegex(
            CaseAttentionOwnerError,
            "RESULTING_LINK_RESOLVER_SCOPE_INVALID",
        ):
            clear_resulting_link_review_from_exact_link(
                history=set_result.result.history,
                case=case,
                event_id=EvidenceId("SYN-EVIDENCE-ATTN-DIFFERENT-LINK-CLEAR"),
                active_set_event_id=set_result.result.event.event_id,
                intervention=intervention,
                link=different.link,
            )


class DOIAttentionWWCTests(unittest.TestCase):
    def _uncertain_fixture(self, suffix: str):  # type: ignore[no-untyped-def]
        source = order_source(ORDER.value)
        finding = make_wwc(
            source,
            presence=FindingPresenceV2.PRESENT,
            author=unknown_fact("RC-055"),
            timing=unknown_fact("RC-056"),
            marker="WWC_MARKER",
            observed_at=OBSERVED_AT,
        )
        request = evaluation_input(
            split_lines(),
            evaluation_suffix=f"WWC-{suffix}",
            snapshot_suffix=f"WWC-{suffix}",
            run_suffix=f"WWC-{suffix}",
            wwc=finding,
        )
        evaluation = evaluate_doi(request)
        context, _, case, _, _, _ = open_context_fixture(
            request.snapshot,
            f"WWC-{suffix}",
            evaluation=evaluation,
            opportunity=evaluation.opportunities[0],
            context_kind=ActionContextKind.FULFILLMENT_SPLIT_REVIEW,
        )
        stream_id = EvidenceId(f"SYN-EVIDENCE-WWC-ATTN-STREAM-{suffix}")
        event_id = EvidenceId(f"SYN-EVIDENCE-WWC-ATTN-EVENT-{suffix}")
        event = DOIWWCEvent(
            event_id=event_id,
            stream_id=stream_id,
            order_id=case.order_id,
            event_type=WWCEventType.OBSERVED,
            finding=finding,
            corrects_event_id=None,
            recorded_at=OBSERVED_AT,
            sequence=1,
            predecessor_binding=None,
            guard=_interaction_guard(
                event_id=event_id,
                stream_id=stream_id,
                suffix=f"WWC-{suffix}",
            ),
        )
        wwc = reduce_wwc(
            DOIWWCHistory(stream_id=stream_id, order_id=case.order_id),
            event,
        ).history
        return context, case, request, evaluation, wwc

    def test_tr094_and_tr095_evaluation_route_bind_exact_wwc_history(self) -> None:
        _, case, request, evaluation, wwc = self._uncertain_fixture("EVAL")
        set_result = set_human_coordination_review_from_wwc(
            history=_attention_history(case),
            case=case,
            event_id=EvidenceId("SYN-EVIDENCE-WWC-ATTN-SET-EVAL"),
            evaluation_input=request,
            evaluation=evaluation,
            wwc_history=wwc,
        )
        self.assertEqual(set_result.transition_id, "TR-094")
        resolved_at = CanonicalTimestamp("2026-08-20T14:17:00Z")
        resolved_finding = make_wwc(
            request.snapshot.wwc_finding.source,
            presence=FindingPresenceV2.PRESENT,
            author=WWCAuthorRelation.TARGET_REP,
            timing=WWCTimingState.ACTIVE,
            marker="WWC_MARKER",
            observed_at=resolved_at,
        )
        resolved_snapshot = make_snapshot(
            split_lines(),
            wwc=resolved_finding,
            observed_at=resolved_at,
            snapshot_suffix="WWC-RESOLVED-EVAL",
            run_suffix="WWC-RESOLVED-EVAL",
        )
        resolved_request = DOIEvaluationInput(
            evaluation_id=EvaluationId("SYN-EVALUATION-WWC-RESOLVED-EVAL"),
            snapshot=resolved_snapshot,
            evaluated_at=resolved_at,
        )
        resolved_evaluation = evaluate_doi(resolved_request)
        resolved_case = DOIOrderCase(
            case_id=case.case_id,
            order_id=case.order_id,
            lifecycle_state=CaseLifecycleState.ACTIVE,
            current_snapshot_id=resolved_snapshot.snapshot_id,
            current_evaluation_id=resolved_evaluation.evaluation_id,
            terminal_closure_reason=None,
        )
        corrected_id = EvidenceId("SYN-EVIDENCE-WWC-ATTN-CORRECTED-EVAL")
        corrected = DOIWWCEvent(
            event_id=corrected_id,
            stream_id=wwc.stream_id,
            order_id=case.order_id,
            event_type=WWCEventType.CORRECTED,
            finding=resolved_finding,
            corrects_event_id=wwc.events[-1].event_id,
            recorded_at=resolved_at,
            sequence=2,
            predecessor_binding=wwc.events[-1].hash_binding(),
            guard=_interaction_guard(
                event_id=corrected_id,
                stream_id=wwc.stream_id,
                suffix="WWC-CORRECTED-EVAL",
            ),
        )
        resolved_wwc = reduce_wwc(wwc, corrected).history
        cleared = clear_human_coordination_review_from_evaluation(
            history=set_result.result.history,
            case=resolved_case,
            event_id=EvidenceId("SYN-EVIDENCE-WWC-ATTN-CLEAR-EVAL"),
            active_set_event_id=set_result.result.event.event_id,
            evaluation_input=resolved_request,
            evaluation=resolved_evaluation,
            resulting_wwc_history=resolved_wwc,
        )
        self.assertEqual(cleared.transition_id, "TR-095")
        self.assertIsNotNone(cleared.result.event.resulting_projection_binding)
        self.assertNotEqual(
            cleared.result.event.resolver_binding,
            cleared.result.event.resulting_projection_binding,
        )
        self.assertIs(validate_attention_owner_decision(cleared), cleared)

    def test_tr095_human_fact_pair_history_scope_source_and_time_are_exact(self) -> None:
        context, case, request, evaluation, wwc = self._uncertain_fixture("HUMAN")
        set_result = set_human_coordination_review_from_wwc(
            history=_attention_history(case),
            case=case,
            event_id=EvidenceId("SYN-EVIDENCE-WWC-ATTN-SET-HUMAN"),
            evaluation_input=request,
            evaluation=evaluation,
            wwc_history=wwc,
        )
        fact_time = CanonicalTimestamp("2026-08-20T14:17:00Z")
        _, fact_source = interaction_source("WWC-COORDINATION-HUMAN")
        authority = verify_synthetic_human_authority(
            grant_id=EvidenceId("SYN-EVIDENCE-WWC-COORDINATION-GRANT"),
            actor=RepId("SYN-REP-WWC-COORDINATION"),
            action_context=context,
            granted_at=OBSERVED_AT,
            authority_source=fact_source,
        )
        fact = StructuredHumanFact.create(
            fact_id=EvidenceId("SYN-EVIDENCE-WWC-COORDINATION-FACT"),
            action_context=context,
            evaluation_id=evaluation.evaluation_id,
            usage_kind=HumanFactUsageKind.COORDINATION_RESOLUTION,
            result_code=HumanFactResultCode.COORDINATION_RESOLUTION_RECORDED,
            authority_grant=authority,
            occurred_at=fact_time,
            source=fact_source,
        )
        human_stream = EvidenceId("SYN-EVIDENCE-WWC-COORDINATION-FACT-STREAM")
        human_event_id = EvidenceId("SYN-EVIDENCE-WWC-COORDINATION-FACT-EVENT")
        human_event = DOIHumanFactEvent(
            event_id=human_event_id,
            stream_id=human_stream,
            event_type=HumanFactEventType.RECORDED,
            fact=fact,
            corrects_event_id=None,
            recorded_at=fact_time,
            sequence=1,
            predecessor_binding=None,
            guard=_interaction_guard(
                event_id=human_event_id,
                stream_id=human_stream,
                suffix="WWC-HUMAN-FACT",
                source=fact_source,
            ),
        )
        human_history = reduce_human_fact(
            DOIHumanFactHistory(stream_id=human_stream),
            human_event,
        ).history
        resolved_finding = make_wwc(
            request.snapshot.wwc_finding.source,
            presence=FindingPresenceV2.PRESENT,
            author=WWCAuthorRelation.OTHER_REP,
            timing=WWCTimingState.ACTIVE,
            marker="WWC_MARKER",
            observed_at=fact_time,
        )
        corrected_id = EvidenceId("SYN-EVIDENCE-WWC-COORDINATION-CORRECTED")
        corrected = DOIWWCEvent(
            event_id=corrected_id,
            stream_id=wwc.stream_id,
            order_id=case.order_id,
            event_type=WWCEventType.CORRECTED,
            finding=resolved_finding,
            corrects_event_id=wwc.events[-1].event_id,
            recorded_at=fact_time,
            sequence=2,
            predecessor_binding=wwc.events[-1].hash_binding(),
            guard=_interaction_guard(
                event_id=corrected_id,
                stream_id=wwc.stream_id,
                suffix="WWC-HUMAN-CORRECTED",
                source=fact_source,
            ),
        )
        resolved_wwc = reduce_wwc(wwc, corrected).history
        with self.assertRaisesRegex(DOIModelError, "DOI_HUMAN_FACT_HISTORY_INVALID"):
            dataclasses.replace(
                human_history,
                stream_id=EvidenceId(
                    "SYN-EVIDENCE-WWC-COORDINATION-WRONG-FACT-STREAM"
                ),
            )
        with self.assertRaisesRegex(DOIModelError, "DOI_WWC_HISTORY_INVALID"):
            dataclasses.replace(
                resolved_wwc,
                stream_id=EvidenceId(
                    "SYN-EVIDENCE-WWC-COORDINATION-WRONG-WWC-STREAM"
                ),
            )
        with self.assertRaisesRegex(
            CaseAttentionOwnerError,
            "RESOLVED_WWC_PROJECTION_REQUIRED",
        ):
            clear_human_coordination_review_from_human_fact(
                history=set_result.result.history,
                case=case,
                event_id=EvidenceId("SYN-EVIDENCE-WWC-ATTN-UNCERTAIN-CLEAR"),
                active_set_event_id=set_result.result.event.event_id,
                human_fact_history=human_history,
                resulting_wwc_history=wwc,
            )
        cleared = clear_human_coordination_review_from_human_fact(
            history=set_result.result.history,
            case=case,
            event_id=EvidenceId("SYN-EVIDENCE-WWC-ATTN-CLEAR-HUMAN"),
            active_set_event_id=set_result.result.event.event_id,
            human_fact_history=human_history,
            resulting_wwc_history=resolved_wwc,
        )
        self.assertEqual(cleared.transition_id, "TR-095")
        self.assertIs(validate_attention_owner_decision(cleared), cleared)
        for usage, result_code in (
            (
                HumanFactUsageKind.COORDINATION_RESOLUTION,
                HumanFactResultCode.APPROVED,
            ),
            (
                HumanFactUsageKind.NO_ACTION_DECISION,
                HumanFactResultCode.COORDINATION_RESOLUTION_RECORDED,
            ),
        ):
            with self.subTest(usage=usage, result=result_code):
                with self.assertRaisesRegex(
                    DOIModelError,
                    "STRUCTURED_HUMAN_FACT_RESULT_INVALID",
                ):
                    dataclasses.replace(fact, usage_kind=usage, result_code=result_code)
        _, wrong_source = interaction_source("WWC-COORDINATION-WRONG-SOURCE")
        with self.assertRaisesRegex(DOIModelError, "STRUCTURED_HUMAN_FACT_INVALID"):
            dataclasses.replace(fact, source=wrong_source)
        with self.assertRaisesRegex(DOIModelError, "STRUCTURED_HUMAN_FACT_INVALID"):
            dataclasses.replace(
                fact,
                occurred_at=CanonicalTimestamp("2026-08-20T14:15:15Z"),
            )
        omitted_human = DOIHumanFactHistory(stream_id=human_stream)
        with self.assertRaises(CaseAttentionOwnerError):
            clear_human_coordination_review_from_human_fact(
                history=set_result.result.history,
                case=case,
                event_id=EvidenceId("SYN-EVIDENCE-WWC-ATTN-OMITTED-HUMAN"),
                active_set_event_id=set_result.result.event.event_id,
                human_fact_history=omitted_human,
                resulting_wwc_history=resolved_wwc,
            )

    def test_owner_inventory_is_exact_and_generic_decisions_are_not_constructible(self) -> None:
        self.assertEqual(
            attention_owner_transition_ids(),
            (
                "TR-020",
                "TR-021",
                "TR-022",
                "TR-023",
                "TR-024",
                "TR-025",
                "TR-026",
                "TR-092",
                "TR-093",
                "TR-094",
                "TR-095",
            ),
        )
        self.assertEqual(len(case_attention_hash_contracts()), 7)
        fixtures = case_attention_hash_fixtures()
        self.assertEqual(
            {name for name, _, _, _ in fixtures},
            set(case_attention_hash_contracts()),
        )
        self.assertEqual(fixtures, case_attention_hash_fixtures())
        for name, domain, canonical, digest in fixtures:
            with self.subTest(name=name):
                self.assertEqual(domain, case_attention_hash_contracts()[name])
                self.assertEqual(domain_hash(domain, canonical).sha256, digest)
        with self.assertRaises(CaseAttentionOwnerError):
            AttentionOwnerDecision()  # type: ignore[call-arg]
        with self.assertRaisesRegex(
            CaseAttentionOwnerError,
            "ATTENTION_DECISION_INVALID",
        ):
            validate_attention_owner_decision(
                object.__new__(AttentionOwnerDecision)
            )


if __name__ == "__main__":
    unittest.main()
