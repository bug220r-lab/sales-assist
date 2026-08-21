from __future__ import annotations

import dataclasses
import unittest
from collections.abc import Callable
from unittest.mock import patch

import synthetic_sales_assist.doi.lifecycle as lifecycle_module
from synthetic_sales_assist.doi.case_attention import (
    AttentionOwnerDecision,
    CaseOwnerDecision,
)
from synthetic_sales_assist.domain.canonical import domain_hash, parse_canonical_json_bytes
from synthetic_sales_assist.domain.identities import (
    EvidenceId,
    EvaluationId,
    InteractionId,
    OrderId,
    RepId,
    RunId,
    SkuId,
)
from synthetic_sales_assist.domain.records import (
    ReasonSet,
    SourceKind,
    SourceObjectNamespace,
    SourceRef,
)
from synthetic_sales_assist.domain.registries import (
    RegistryLookupError,
    TransitionRef,
    load_doi_registries,
)
from synthetic_sales_assist.domain.numeric import PositiveQuantity
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.doi.lifecycle import (
    AttentionAction,
    AttentionEvent,
    AttentionStream,
    LifecycleCollisionError,
    LifecycleConflictError,
    LifecycleSchemaError,
    TransitionEffect,
    TransitionEffectKind,
    TransitionEvent,
    TransitionCommand,
    TransitionFixture,
    TransitionGuardAuthorityEvidence,
    TransitionGuardAuthorityIssuer,
    TransitionGuardEvidenceKind,
    TransitionGuardProof,
    TransitionGuardVerdict,
    TransitionStream,
    action_context_event_occurrence_id,
    alternate_observation_occurrence_id,
    case_purge_occurrence_id,
    contact_workflow_event_occurrence_id,
    failing_transition_guard_facts,
    evaluation_transition_occurrence_id,
    evaluation_transition_stream_id,
    extraction_transition_occurrence_id,
    extraction_transition_stream_id,
    identity_retention_occurrence_id,
    identity_retention_stream_id,
    legal_reason_refs,
    lifecycle_hash_fixtures,
    make_transition_command,
    make_action_context_transition_guard_proof,
    make_action_context_completion_guard_proof,
    make_alternate_observation_transition_guard_proof,
    make_attention_owner_transition_guard_proof,
    make_case_purge_transition_guard_proof,
    make_case_owner_transition_guard_proof,
    make_case_recheck_transition_guard_proof,
    make_closure_transition_guard_proof,
    make_contact_workflow_transition_guard_proof,
    make_dedupe_reduction_transition_guard_proof,
    make_evaluation_transition_guard_proof,
    make_extraction_transition_guard_proof,
    make_human_action_transition_guard_proof,
    make_human_fact_reduction_transition_guard_proof,
    make_human_review_evaluation_guard_proof,
    make_identity_retention_purge_guard_proof,
    make_intervention_transition_guard_proof,
    make_kpi_contribution_transition_guard_proof,
    make_observation_graph_deletion_guard_proof,
    make_out_of_scope_closure_guard_proof,
    make_run_control_transition_guard_proof,
    make_relationship_transition_guard_proof,
    make_resulting_link_search_transition_guard_proof,
    make_resulting_link_transition_guard_proof,
    make_transition_guard_proof,
    make_source_batch_release_guard_proof,
    make_source_import_commit_guard_proof,
    make_source_import_start_guard_proof,
    make_source_rejection_retention_guard_proof,
    make_system_action_transition_guard_proof,
    make_value_reduction_transition_guard_proof,
    make_wwc_transition_guard_proof,
    missing_production_owner_adapter_transition_ids,
    production_owner_adapter_transition_ids,
    protected_transition_ids,
    recognized_transition_ids,
    registered_transition_effects,
    reduce_attention,
    reduce_fixture_transition,
    reduce_transition,
    satisfying_transition_guard_facts,
    source_batch_release_occurrence_id,
    source_import_event_occurrence_id,
    source_import_transition_stream_id,
    source_rejection_retention_occurrence_id,
    run_transition_occurrence_id,
    run_transition_stream_id,
    observation_deletion_occurrence_id,
    transition_definition,
    transition_guard_fact_schema,
    transition_matrix,
    wwc_event_occurrence_id,
    _make_fixture_transition_guard_proof,
)
from synthetic_sales_assist.doi.evaluator import evaluate_doi
from synthetic_sales_assist.doi.extraction import extract_order_snapshot
from synthetic_sales_assist.doi.identities import (
    AcceptedCommandId,
    DoiOrderId,
    LineSnapshotId,
    RunInvocationId,
    SourceBatchId,
    SourceIdentityId,
)
from synthetic_sales_assist.doi.interventions import (
    ActionVerificationEvent,
    CompletedSystemActionProof,
    DOIIntervention,
    DOIResultingOrderLinkSearchHistory,
    EvidenceKeyKind,
    LogicalEvidenceKey,
    ResultingLinkSearchEvidence,
    SystemResultingLinkEvidence,
    ValueCorrectionKind,
    ValueEvent,
    VerificationEvidence,
    append_resulting_link_revision,
    append_resulting_link_search,
    append_value_event,
    record_verified_intervention,
)
from synthetic_sales_assist.doi.knowledge import (
    DOIExactSKUObservation,
    DOIAlternateObservation,
    append_relationship_revision,
    candidate_from_relationship,
    create_relationship,
    exact_sku_candidate,
)
from synthetic_sales_assist.doi.models import (
    ActionContextKind,
    ActionContextCompletionTrigger,
    ActionContextCloseReason,
    ActionContextEventType,
    ActionContextState,
    ActionVerificationState,
    AlternateRelationshipState,
    AlternateRelationshipType,
    AlternateAvailability,
    AlternateObservationState,
    AlternateResearchState,
    AlternateRevisionKind,
    AttentionCondition,
    CaseLifecycleState,
    CompatibilityDecision,
    ContactWorkflowEvent,
    ContactWorkflowEventType,
    ContactWorkflowHistory,
    ContactWorkflowState,
    DedupeEventType,
    DedupeState,
    DedupeVerificationFact,
    DOIActionContext,
    DOIActionContextEvent,
    DOIActionContextHistory,
    DOIActionContextStore,
    DOIDedupeEvent,
    DOIDedupeHistory,
    DOIEvaluationInput,
    DOIHumanFactEvent,
    DOIHumanFactHistory,
    DOIModelError,
    DOIOrderCase,
    DOIWWCEvent,
    DOIWWCHistory,
    DropShipState,
    FindingPresenceV2,
    GeographyClass,
    HandlingFlag,
    HumanFactResultCode,
    HumanFactEventType,
    HumanFactUsageKind,
    InterventionType,
    LineAvailability,
    OrderState,
    OpportunityType,
    PaymentCondition,
    QuantityAvailability,
    TerminalClosureReason,
    ValueEventType,
    ValueVerificationState,
    WWCAuthorRelation,
    WWCEventType,
    WWCProjectionState,
    WWCTimingState,
    DOIOccurrenceGuard,
    reduce_action_context,
    reduce_action_context_store,
    reduce_contact_workflow,
    reduce_dedupe,
    reduce_human_fact,
    reduce_wwc,
    verify_synthetic_human_authority,
    verify_action_context_opening_authority,
    known_fact,
    not_applicable_fact,
    unknown_fact,
)
from synthetic_sales_assist.doi.retention import (
    DOICaseGraph,
    IdentityRetentionKind,
    KPIContributionHistory,
    reduce_kpi_contribution,
    calendar90,
    schedule_identity_retention,
    schedule_retention,
)
from synthetic_sales_assist.doi.source import (
    DOIRun,
    DOIRunCounts,
    DOIRunWorkDisposition,
    InMemoryDOIRunControl,
    RunStatus,
    RunType,
    RunWorkDispositionKind,
    SyntheticQueueTab,
    accept_no_retry_command,
    ingest_synthetic_queue,
    source_hash_fixture_records,
)
from tests.test_doi_evaluator import (
    OBSERVED_AT,
    evaluation_input,
    human_fact,
    occurrence_guard,
    split_lines,
)
from tests.test_doi_extraction import _surface
from tests.test_doi_interventions import (
    CHILD,
    LINK_ID,
    _action,
    _human_action_history,
    _mapping,
    _revision,
    _value_event,
)
from tests.test_doi_retention import (
    _currency_envelope as _kpi_currency_envelope,
    _intervention as _kpi_intervention,
    _link as _kpi_link,
)
from tests.test_doi_knowledge import (
    action_context as knowledge_action_context,
    product_source,
    relationship,
)
from tests.test_doi_models import (
    make_line,
    make_snapshot,
    make_wwc,
    open_context,
    open_context_fixture,
    order_source,
    usd,
)
from tests.test_doi_source import _image, _row


def _guard_proof(
    transition: TransitionRef,
    facts: dict[str, object] | None = None,
) -> TransitionGuardProof:
    return _make_fixture_transition_guard_proof(
        transition,
        (
            satisfying_transition_guard_facts(transition)
            if facts is None
            else facts
        ),
    )


def _reduce_owner_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    proof: TransitionGuardProof,
    occurred_at: CanonicalTimestamp,
) -> TransitionEvent:
    definition = transition_definition(transition)
    command = make_transition_command(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        current_state=definition.from_state,
        expected_sequence=1,
        expected_predecessor_sha256=None,
        guard_proof=proof,
    )
    return reduce_transition(
        TransitionStream.initial(
            stream_id=stream_id,
            state=definition.from_state,
        ),
        command,
        occurred_at=occurred_at,
    ).event


def _interaction_source(marker: str) -> SourceRef:
    return SourceRef.create(
        source_ref_id=EvidenceId(f"SYN-EVIDENCE-LIFECYCLE-SOURCE-{marker}"),
        source_kind=SourceKind.SYNTHETIC_INTERACTION_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_INTERACTION,
        object_id=InteractionId(f"SYN-INTERACTION-LIFECYCLE-{marker}"),
    )


def _system_action_history_and_event() -> tuple[
    DOIActionContextHistory,
    ActionVerificationEvent,
]:
    seed_snapshot = make_snapshot(
        (),
        snapshot_suffix="LIFECYCLE-SYSTEM-ACTION-SEED",
        run_suffix="LIFECYCLE-SYSTEM-ACTION-SEED",
    )
    opening_context, opening = open_context(
        seed_snapshot,
        "LIFECYCLE-SYSTEM-ACTION",
    )
    opened = reduce_action_context(
        DOIActionContextHistory(
            action_context_id=opening_context.action_context_id
        ),
        opening,
    )
    completion_id = EvidenceId(
        "SYN-EVIDENCE-LIFECYCLE-SYSTEM-CONTEXT-COMPLETE"
    )
    completion_source = _interaction_source("SYSTEM-CONTEXT-COMPLETE")
    completion = DOIActionContextEvent.completed(
        event_id=completion_id,
        action_context=opening_context,
        completion_trigger=ActionContextCompletionTrigger.SYSTEM_VERIFIED,
        occurred_at=OBSERVED_AT,
        close_reason=ActionContextCloseReason.ACTION_VERIFIED,
        guard=DOIOccurrenceGuard(
            guard_id=completion_id,
            owner_id=opening_context.action_context_id,
            occurrence_id=InteractionId(
                "SYN-INTERACTION-LIFECYCLE-SYSTEM-CONTEXT-COMPLETE"
            ),
            source=completion_source,
        ),
    )
    history = reduce_action_context(opened.history, completion).history
    context = history.projection
    if type(context) is not DOIActionContext:
        raise AssertionError("system action context must be retained")
    order_id = opening_context.order_id
    opportunity_id = opening_context.opportunity_id
    intervention_id = EvidenceId("SYN-EVIDENCE-LIFECYCLE-SYSTEM-INTERVENTION")
    order_source_ref = SourceRef.create(
        source_ref_id=EvidenceId("SYN-EVIDENCE-LIFECYCLE-SYSTEM-ORDER-SOURCE"),
        source_kind=SourceKind.SYNTHETIC_ORDER_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_ORDER,
        object_id=order_id.value,
    )
    verification = VerificationEvidence.from_system_observation(
        evidence_id=EvidenceId("SYN-EVIDENCE-LIFECYCLE-SYSTEM-EVIDENCE"),
        intervention_id=intervention_id,
        opportunity_id=opportunity_id,
        intervention_type=InterventionType.PRODUCT_SUBSTITUTION,
        completed_action_proof=CompletedSystemActionProof.from_history(
            history=history,
        ),
        source=order_source_ref,
        occurred_at=completion.occurred_at,
    )
    action = ActionVerificationEvent(
        event_id=EvidenceId("SYN-EVIDENCE-LIFECYCLE-SYSTEM-ACTION"),
        intervention_id=intervention_id,
        opportunity_id=opportunity_id,
        intervention_type=InterventionType.PRODUCT_SUBSTITUTION,
        key=LogicalEvidenceKey(
            key_id=EvidenceId("SYN-EVIDENCE-LIFECYCLE-SYSTEM-ACTION-KEY"),
            owner_id=intervention_id,
            occurrence_id=verification.evidence_id,
            kind=EvidenceKeyKind.ACTION,
        ),
        evidence=verification,
    )
    return history, action


def _exact_observation_for_history(
    history: DOIActionContextHistory,
) -> DOIExactSKUObservation:
    opening = DOIActionContext.from_event(history.events[0])
    sku = SkuId("SYN-SKU-LIFECYCLE-OBSERVATION")
    source = SourceRef.create(
        source_ref_id=EvidenceId("SYN-EVIDENCE-LIFECYCLE-PRODUCT-SOURCE"),
        source_kind=SourceKind.SYNTHETIC_PRODUCT_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_PRODUCT,
        object_id=sku,
    )
    return DOIExactSKUObservation(
        observation_id=EvidenceId("SYN-EVIDENCE-LIFECYCLE-OBSERVATION"),
        action_context_id=opening.action_context_id,
        action_context_binding=opening.hash_binding(),
        ordered_line_id=opening.line_scope[0],
        ordered_sku=sku,
        observed_sku=sku,
        state=AlternateObservationState.CURRENT,
        observed_availability=AlternateAvailability.IN_STOCK,
        potential_unit_value=None,
        observed_at=OBSERVED_AT,
        source=source,
    )


def _dedupe_closure_evidence() -> tuple[DOIEvaluationInput, object]:
    source = order_source(OrderId("SYN-ORDER-DOI-0001"))
    base = evaluation_input(
        (make_line(1, source),),
        evaluation_suffix="LIFECYCLE-DEDUPE",
        alternate_research_state=AlternateResearchState.COMPLETE,
        dedupe_state=DedupeState.SOURCE_PRESENT,
    )
    candidate_evaluation = evaluate_doi(base)
    approval = human_fact(
        base,
        usage=HumanFactUsageKind.DEDUPE_DECISION,
        result=HumanFactResultCode.APPROVED,
        suffix="LIFECYCLE-DEDUPE",
    )
    stream_id = EvidenceId("SYN-EVIDENCE-LIFECYCLE-DEDUPE-STREAM")
    history = DOIDedupeHistory.empty(
        stream_id=stream_id,
        order_id=base.snapshot.order_id,
    )
    observed_id = EvidenceId("SYN-EVIDENCE-LIFECYCLE-DEDUPE-OBSERVED")
    observed = DOIDedupeEvent(
        event_id=observed_id,
        stream_id=stream_id,
        order_id=base.snapshot.order_id,
        event_type=DedupeEventType.SOURCE_OBSERVED,
        finding=base.snapshot.dedupe_finding,
        evaluation=None,
        human_fact=None,
        verification=None,
        recorded_at=OBSERVED_AT,
        sequence=1,
        predecessor_binding=None,
        guard=occurrence_guard(
            owner_id=stream_id,
            event_id=observed_id,
            suffix="LIFECYCLE-DEDUPE-OBSERVED",
        ),
    )
    history = reduce_dedupe(history, observed).history
    candidate_id = EvidenceId("SYN-EVIDENCE-LIFECYCLE-DEDUPE-CANDIDATE")
    candidate = DOIDedupeEvent(
        event_id=candidate_id,
        stream_id=stream_id,
        order_id=base.snapshot.order_id,
        event_type=DedupeEventType.CANDIDATE_IDENTIFIED,
        finding=None,
        evaluation=candidate_evaluation,
        human_fact=None,
        verification=None,
        recorded_at=OBSERVED_AT,
        sequence=2,
        predecessor_binding=history.events[-1].hash_binding(),
        guard=occurrence_guard(
            owner_id=stream_id,
            event_id=candidate_id,
            suffix="LIFECYCLE-DEDUPE-CANDIDATE",
        ),
    )
    history = reduce_dedupe(history, candidate).history
    approval_id = EvidenceId("SYN-EVIDENCE-LIFECYCLE-DEDUPE-APPROVED")
    approved = DOIDedupeEvent(
        event_id=approval_id,
        stream_id=stream_id,
        order_id=base.snapshot.order_id,
        event_type=DedupeEventType.HUMAN_APPROVED,
        finding=None,
        evaluation=None,
        human_fact=approval,
        verification=None,
        recorded_at=OBSERVED_AT,
        sequence=3,
        predecessor_binding=history.events[-1].hash_binding(),
        guard=occurrence_guard(
            owner_id=stream_id,
            event_id=approval_id,
            suffix="LIFECYCLE-DEDUPE-APPROVED",
        ),
    )
    history = reduce_dedupe(history, approved).history
    verified_at = CanonicalTimestamp("2026-08-20T14:15:17Z")
    verified_snapshot = make_snapshot(
        base.snapshot.lines,
        dedupe_state=DedupeState.SOURCE_PRESENT,
        observed_at=verified_at,
        snapshot_suffix="LIFECYCLE-DEDUPE-VERIFIED",
        run_suffix="LIFECYCLE-DEDUPE-VERIFIED",
        dedupe_suffix="LIFECYCLE-DEDUPE-VERIFIED",
    )
    verification = DedupeVerificationFact(
        verification_id=EvidenceId("SYN-EVIDENCE-LIFECYCLE-DEDUPE-VERIFY"),
        order_id=base.snapshot.order_id,
        prior_snapshot=base.snapshot,
        verified_snapshot=verified_snapshot,
        approved_human_fact_binding=approval.hash_binding(),
        prior_projection_binding=history.projection.hash_binding(),
        approved_at=approval.occurred_at,
    )
    request = DOIEvaluationInput(
        evaluation_id=base.evaluation_id,
        snapshot=verified_snapshot,
        evaluated_at=verified_at,
        human_facts=(approval,),
        dedupe_history=history,
        dedupe_verification=verification,
    )
    return request, evaluate_doi(request)


def _terminal_source_batch_owner_graph() -> tuple[
    InMemoryDOIRunControl,
    object,
    object,
    DOIRun,
    object,
]:
    control = InMemoryDOIRunControl()
    started = control.begin_review_run(
        run_id=RunId("SYN-RUN-LIFECYCLE-OWNER"),
        invocation_id=RunInvocationId(
            InteractionId("SYN-INTERACTION-LIFECYCLE-OWNER")
        ),
        source_identity_id=SourceIdentityId(
            EvidenceId("SYN-EVIDENCE-LIFECYCLE-OWNER-SOURCE")
        ),
        locked_tab=SyntheticQueueTab.MONDAY,
        tab_confirmed=True,
        accepted_at=CanonicalTimestamp("2026-05-22T11:00:00Z"),
    )
    assert started.source_attempt is not None
    image = _image(
        (
            _row(1, "SYN-ORDER-2"),
            _row(2, "SYN-ORDER-2", "OTHER_REP"),
        )
    )
    imported = ingest_synthetic_queue(
        image,
        image,
        candidate_batch_id=SourceBatchId(
            EvidenceId("SYN-EVIDENCE-LIFECYCLE-OWNER-BATCH")
        ),
    )
    assert imported.batch is not None
    attempt = control.commit_import_result(
        attempt_id=started.source_attempt.attempt_id,
        result=imported,
        completed_at=CanonicalTimestamp("2026-05-22T11:30:00Z"),
    )
    terminal = control.finalize_processing(
        run_id=started.run.run_id,
        completed_at=CanonicalTimestamp("2026-05-22T12:00:00Z"),
    )
    return control, imported.batch, attempt, terminal.run, terminal


class TestDoiLifecycle(unittest.TestCase):
    def test_registry_is_closed_and_all_115_rows_normalize(self) -> None:
        self.assertEqual(len(recognized_transition_ids()), 115)
        self.assertEqual(len(transition_matrix()), 115)
        self.assertEqual(len(set(recognized_transition_ids())), 115)
        with self.assertRaises(RegistryLookupError):
            load_doi_registries().transition_ref("TR-999")
        with self.assertRaises(LifecycleSchemaError):
            transition_definition("TR-001")  # type: ignore[arg-type]

    def test_closed_guard_schemas_cover_all_115_registered_expressions(self) -> None:
        transitions = load_doi_registries().transition_refs
        schemas = tuple(transition_guard_fact_schema(item) for item in transitions)
        self.assertEqual(len(schemas), 115)
        self.assertEqual(sum(len(schema.required_facts) for schema in schemas), 286)
        self.assertEqual(
            {schema.transition.transition_id for schema in schemas},
            set(recognized_transition_ids()),
        )
        for transition, schema in zip(transitions, schemas, strict=True):
            with self.subTest(transition=transition.transition_id):
                facts = satisfying_transition_guard_facts(transition)
                self.assertEqual(set(facts), set(schema.required_facts))
                self.assertNotIn("fixture", facts)
                self.assertNotIn("valid", facts)
                self.assertTrue(all(facts.values()))
                proof = _guard_proof(transition, facts)
                self.assertIs(proof.verdict, TransitionGuardVerdict.SATISFIED)
                self.assertEqual(
                    parse_canonical_json_bytes(proof.guard_facts.canonical_bytes),
                    facts,
                )
                failing = failing_transition_guard_facts(transition)
                self.assertEqual(
                    sum(value is False for value in failing.values()),
                    1,
                )
                self.assertIs(
                    _guard_proof(transition, failing).verdict,
                    TransitionGuardVerdict.NOT_SATISFIED,
                )

    def test_guard_verdict_is_not_a_public_factory_argument(self) -> None:
        transition = load_doi_registries().transition_ref("TR-044")
        definition = transition_definition(transition)
        with self.assertRaisesRegex(TypeError, "verdict"):
            make_transition_guard_proof(
                transition=transition,
                from_state=definition.from_state,
                expected_to_state=definition.to_state,
                registered_guard=definition.guard,
                required_effects=definition.required_effects,
                guard_facts=satisfying_transition_guard_facts(transition),
                verdict=TransitionGuardVerdict.NOT_SATISFIED,  # type: ignore[call-arg]
            )

    def test_boolean_facts_cannot_prove_human_verified_or_destructive_guards(self) -> None:
        registries = load_doi_registries()
        for transition_id in ("TR-013", "TR-044", "TR-112"):
            transition = registries.transition_ref(transition_id)
            definition = transition_definition(transition)
            with self.subTest(transition=transition_id):
                with self.assertRaisesRegex(
                    LifecycleSchemaError,
                    "TRANSITION_GUARD_AUTHORITY_REQUIRED",
                ) as caught:
                    make_transition_guard_proof(
                        transition=transition,
                        from_state=definition.from_state,
                        expected_to_state=definition.to_state,
                        registered_guard=definition.guard,
                        required_effects=definition.required_effects,
                        guard_facts=satisfying_transition_guard_facts(transition),
                    )
                self.assertEqual(caught.exception.reason.code, "RC-113")

    def test_protected_routes_are_closed_and_fixture_authority_never_reduces(self) -> None:
        self.assertEqual(
            set(protected_transition_ids()),
            set(recognized_transition_ids()),
        )
        registries = load_doi_registries()
        for transition in registries.transition_refs:
            with self.subTest(transition=transition.transition_id):
                fixture = TransitionFixture.legal(transition)
                self.assertIs(
                    fixture.command.guard_proof.authority_evidence.issuer,
                    TransitionGuardAuthorityIssuer.SYNTHETIC_FIXTURE,
                )
                with self.assertRaisesRegex(
                    LifecycleSchemaError,
                    "TRANSITION_SYNTHETIC_FIXTURE_AUTHORITY_FORBIDDEN",
                ) as caught:
                    reduce_transition(
                        fixture.stream,
                        fixture.command,
                        occurred_at=fixture.occurred_at,
                    )
                self.assertEqual(caught.exception.reason.code, "RC-113")
                self.assertEqual(fixture.stream.events, ())

    def test_raw_guard_fact_mappings_have_no_production_authority_path(self) -> None:
        self.assertNotIn(
            "INTERNAL_FACT_REDUCER",
            {item.value for item in TransitionGuardEvidenceKind},
        )
        for transition in load_doi_registries().transition_refs:
            definition = transition_definition(transition)
            with self.subTest(transition=transition.transition_id), self.assertRaisesRegex(
                LifecycleSchemaError,
                "TRANSITION_GUARD_AUTHORITY_REQUIRED",
            ) as caught:
                make_transition_guard_proof(
                    transition=transition,
                    from_state=definition.from_state,
                    expected_to_state=definition.to_state,
                    registered_guard=definition.guard,
                    required_effects=definition.required_effects,
                    guard_facts=satisfying_transition_guard_facts(transition),
                )
            self.assertEqual(caught.exception.reason.code, "RC-113")

    def test_uninitialized_exact_owner_types_fail_closed_at_every_adapter(self) -> None:
        registries = load_doi_registries()
        stream_id = EvidenceId("SYN-EVIDENCE-LIFECYCLE-RAW-OWNER-STREAM")
        occurrence_id = EvidenceId(
            "SYN-EVIDENCE-LIFECYCLE-RAW-OWNER-OCCURRENCE"
        )
        cases = (
            (
                "TR-045A",
                "INTERVENTION_REDUCTION_OWNER_INVALID",
                lambda: make_intervention_transition_guard_proof(
                    transition=registries.transition_ref("TR-045A"),
                    stream_id=stream_id,
                    occurrence_id=occurrence_id,
                    prior_intervention=None,
                    action_event=object.__new__(ActionVerificationEvent),
                ),
            ),
            (
                "TR-046",
                "VALUE_REDUCTION_OWNER_INVALID",
                lambda: make_value_reduction_transition_guard_proof(
                    transition=registries.transition_ref("TR-046"),
                    stream_id=stream_id,
                    occurrence_id=occurrence_id,
                    prior_intervention=object.__new__(DOIIntervention),
                    value_event=object.__new__(ValueEvent),
                ),
            ),
            (
                "TR-054",
                "RESULTING_LINK_REDUCTION_OWNER_INVALID",
                lambda: make_resulting_link_transition_guard_proof(
                    transition=registries.transition_ref("TR-054"),
                    stream_id=stream_id,
                    occurrence_id=occurrence_id,
                    prior_link=None,
                    intervention=object.__new__(DOIIntervention),
                    evidence=object.__new__(SystemResultingLinkEvidence),
                ),
            ),
            (
                "TR-088",
                "RESULTING_LINK_SEARCH_REDUCTION_OWNER_INVALID",
                lambda: make_resulting_link_search_transition_guard_proof(
                    transition=registries.transition_ref("TR-088"),
                    stream_id=stream_id,
                    occurrence_id=occurrence_id,
                    prior_history=object.__new__(
                        DOIResultingOrderLinkSearchHistory
                    ),
                    evidence=object.__new__(ResultingLinkSearchEvidence),
                ),
            ),
            (
                "TR-106",
                "KPI_CONTRIBUTION_REDUCTION_OWNER_INVALID",
                lambda: make_kpi_contribution_transition_guard_proof(
                    transition=registries.transition_ref("TR-106"),
                    stream_id=stream_id,
                    occurrence_id=occurrence_id,
                    prior_history=object.__new__(KPIContributionHistory),
                    prior_interventions=(),
                    prior_resulting_links=(),
                    prior_currency_evidence=(),
                    intervention=object.__new__(DOIIntervention),
                    resulting_link=None,
                ),
            ),
            (
                "TR-084",
                "ACTION_CONTEXT_OWNER_STORE_INVALID",
                lambda: make_action_context_transition_guard_proof(
                    transition=registries.transition_ref("TR-084"),
                    stream_id=stream_id,
                    occurrence_id=occurrence_id,
                    prior_store=object.__new__(DOIActionContextStore),
                    event=object.__new__(DOIActionContextEvent),
                ),
            ),
        )
        for transition_id, error, call in cases:
            with self.subTest(transition=transition_id), self.assertRaisesRegex(
                LifecycleConflictError,
                error,
            ) as caught:
                call()
            self.assertEqual(caught.exception.reason.code, "RC-081")

    def test_every_public_owner_adapter_has_one_fail_closed_input_boundary(self) -> None:
        names = lifecycle_module._FAIL_CLOSED_OWNER_ADAPTER_NAMES
        self.assertEqual(len(names), 31)
        self.assertEqual(len(set(names)), len(names))
        for name in names:
            with self.subTest(adapter=name), self.assertRaisesRegex(
                LifecycleConflictError,
                "TRANSITION_OWNER_ADAPTER_INPUT_INVALID",
            ) as caught:
                getattr(lifecycle_module, name)()
            self.assertEqual(caught.exception.reason.code, "RC-081")

    def test_production_owner_adapter_inventory_is_machine_checkable(self) -> None:
        covered = set(production_owner_adapter_transition_ids())
        missing = set(missing_production_owner_adapter_transition_ids())
        registered = set(recognized_transition_ids())
        self.assertEqual(covered, set(protected_transition_ids()))
        self.assertFalse(covered & missing)
        self.assertEqual(covered | missing, registered)
        self.assertEqual(len(covered), 115)
        self.assertEqual(len(missing), 0)

    def test_case_and_attention_owner_decisions_prove_all_13_routes(self) -> None:
        from tests import test_doi_case_attention as owner_tests

        captured: dict[str, CaseOwnerDecision | AttentionOwnerDecision] = {}
        original_case_issue = CaseOwnerDecision._issue
        original_attention_issue = AttentionOwnerDecision._issue

        def capture_case(**kwargs: object) -> CaseOwnerDecision:
            decision = original_case_issue(**kwargs)  # type: ignore[arg-type]
            captured.setdefault(decision.transition_id, decision)
            return decision

        def capture_attention(**kwargs: object) -> AttentionOwnerDecision:
            decision = original_attention_issue(**kwargs)  # type: ignore[arg-type]
            captured.setdefault(decision.transition_id, decision)
            return decision

        owner_methods = (
            (
                owner_tests.DOICaseOwnerTests,
                "test_tr007_is_minimized_sealed_and_replay_validated",
            ),
            (
                owner_tests.DOICaseOwnerTests,
                "test_tr008_refresh_binds_current_complete_evaluation_and_history",
            ),
            (
                owner_tests.DOIAttentionExtractionTests,
                "test_tr020_tr021_tr022_and_tr024_are_typed_and_preserve_unrelated_causes",
            ),
            (
                owner_tests.DOIAttentionExtractionTests,
                "test_tr023_requires_present_current_evaluation_and_exact_active_set",
            ),
            (
                owner_tests.DOIAttentionActionAndLinkTests,
                "test_tr025_tr026_require_same_opportunity_and_verified_action_history",
            ),
            (
                owner_tests.DOIAttentionActionAndLinkTests,
                "test_tr092_tr093_search_history_is_exact_and_omission_fails",
            ),
            (
                owner_tests.DOIAttentionActionAndLinkTests,
                "test_tr092_mapping_conflict_and_tr093_exact_link_bind_same_subject",
            ),
            (
                owner_tests.DOIAttentionWWCTests,
                "test_tr094_and_tr095_evaluation_route_bind_exact_wwc_history",
            ),
            (
                owner_tests.DOIAttentionWWCTests,
                "test_tr095_human_fact_pair_history_scope_source_and_time_are_exact",
            ),
        )
        with patch.object(
            CaseOwnerDecision,
            "_issue",
            side_effect=capture_case,
        ), patch.object(
            AttentionOwnerDecision,
            "_issue",
            side_effect=capture_attention,
        ):
            for owner_class, method_name in owner_methods:
                case = owner_class(methodName=method_name)
                case.setUp()
                try:
                    getattr(case, method_name)()
                finally:
                    case.tearDown()

        expected = {
            "TR-007",
            "TR-008",
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
        }
        self.assertEqual(set(captured), expected)
        registries = load_doi_registries()
        for transition_id in sorted(expected):
            with self.subTest(transition=transition_id):
                decision = captured[transition_id]
                transition = registries.transition_ref(transition_id)
                proof = (
                    make_case_owner_transition_guard_proof(
                        transition=transition,
                        decision=decision,
                    )
                    if type(decision) is CaseOwnerDecision
                    else make_attention_owner_transition_guard_proof(
                        transition=transition,
                        decision=decision,
                    )
                )
                event = _reduce_owner_guard_proof(
                    transition=transition,
                    stream_id=decision.stream_id,
                    occurrence_id=decision.occurrence_id,
                    proof=proof,
                    occurred_at=decision.occurred_at,
                )
                self.assertEqual(event.transition, transition)

        for transition_id, raw, factory, error in (
            (
                "TR-007",
                object.__new__(CaseOwnerDecision),
                make_case_owner_transition_guard_proof,
                "CASE_OWNER_REDUCTION_GUARD_NOT_SATISFIED",
            ),
            (
                "TR-020",
                object.__new__(AttentionOwnerDecision),
                make_attention_owner_transition_guard_proof,
                "ATTENTION_OWNER_REDUCTION_GUARD_NOT_SATISFIED",
            ),
            (
                "TR-020",
                AttentionEvent.set(
                    event_id=EvidenceId(
                        "SYN-EVIDENCE-LIFECYCLE-LEGACY-ATTENTION"
                    ),
                    case_id=EvidenceId(
                        "SYN-EVIDENCE-LIFECYCLE-LEGACY-ATTENTION-CASE"
                    ),
                    condition=AttentionCondition.RECHECK_REQUIRED,
                    cause_key=EvidenceId(
                        "SYN-EVIDENCE-LIFECYCLE-LEGACY-ATTENTION-CAUSE"
                    ),
                    occurred_at=OBSERVED_AT,
                ),
                make_attention_owner_transition_guard_proof,
                "ATTENTION_OWNER_REDUCTION_GUARD_NOT_SATISFIED",
            ),
        ):
            with self.subTest(raw_transition=transition_id), self.assertRaisesRegex(
                LifecycleConflictError,
                error,
            ):
                factory(
                    transition=registries.transition_ref(transition_id),
                    decision=raw,
                )

    def test_run_control_owner_reducer_proves_tr001_through_tr004(self) -> None:
        start_control = InMemoryDOIRunControl()
        started = start_control.begin_review_run(
            run_id=RunId("SYN-RUN-LIFECYCLE-TR001"),
            invocation_id=RunInvocationId(
                InteractionId("SYN-INTERACTION-LIFECYCLE-TR001")
            ),
            source_identity_id=SourceIdentityId(
                EvidenceId("SYN-EVIDENCE-LIFECYCLE-TR001-SOURCE")
            ),
            locked_tab=SyntheticQueueTab.MONDAY,
            tab_confirmed=True,
            accepted_at=CanonicalTimestamp("2026-05-22T10:00:00Z"),
        )
        complete_control, _, _, _, completed = _terminal_source_batch_owner_graph()

        exception_control = InMemoryDOIRunControl()
        exception_start = exception_control.begin_recheck_run(
            run_id=RunId("SYN-RUN-LIFECYCLE-TR003"),
            invocation_id=RunInvocationId(
                InteractionId("SYN-INTERACTION-LIFECYCLE-TR003")
            ),
            run_type=RunType.RECHECK_ORDER,
            order_id=OrderId("SYN-ORDER-3"),
            accepted_at=CanonicalTimestamp("2026-05-22T10:00:00Z"),
        )
        work_item = exception_control.work_items(exception_start.run.run_id)[0]
        lifecycle_fixture = TransitionFixture.legal(
            load_doi_registries().transition_ref("TR-044")
        )
        lifecycle_event = reduce_fixture_transition(
            lifecycle_fixture.stream,
            lifecycle_fixture.command,
            occurred_at=lifecycle_fixture.occurred_at,
        ).event
        exception_control.record_work_disposition(
            DOIRunWorkDisposition.exception_or_block(
                work_item=work_item,
                kind=RunWorkDispositionKind.BLOCKED_ORDER,
                portal_read_performed=False,
                lifecycle_event=lifecycle_event,
                occurred_at=CanonicalTimestamp("2026-05-22T10:30:00Z"),
                reasons=ReasonSet((load_doi_registries().reason_ref("RC-011"),)),
            )
        )
        completed_with_exceptions = exception_control.finalize_processing(
            run_id=exception_start.run.run_id,
            completed_at=CanonicalTimestamp("2026-05-22T11:00:00Z"),
        )

        failed_control = InMemoryDOIRunControl()
        failed_start = failed_control.begin_review_run(
            run_id=RunId("SYN-RUN-LIFECYCLE-TR004"),
            invocation_id=RunInvocationId(
                InteractionId("SYN-INTERACTION-LIFECYCLE-TR004")
            ),
            source_identity_id=SourceIdentityId(
                EvidenceId("SYN-EVIDENCE-LIFECYCLE-TR004-SOURCE")
            ),
            locked_tab=SyntheticQueueTab.MONDAY,
            tab_confirmed=True,
            accepted_at=CanonicalTimestamp("2026-05-22T10:00:00Z"),
        )
        assert failed_start.source_attempt is not None
        invalid_image = _image((_row(1, "SYN-ORDER-INVALID"),))
        failed_attempt = failed_control.commit_import_result(
            attempt_id=failed_start.source_attempt.attempt_id,
            result=ingest_synthetic_queue(
                invalid_image,
                invalid_image,
                candidate_batch_id=SourceBatchId(
                    EvidenceId("SYN-EVIDENCE-LIFECYCLE-TR004-BATCH")
                ),
            ),
            completed_at=CanonicalTimestamp("2026-05-22T10:30:00Z"),
        )
        no_retry = accept_no_retry_command(
            command_id=AcceptedCommandId(
                InteractionId("SYN-INTERACTION-LIFECYCLE-TR004-NO-RETRY")
            ),
            run_id=failed_start.run.run_id,
            greatest_failed_attempt_id=failed_attempt.attempt_id,
            accepted_actor_id=RepId("SYN-REP-AUTHORIZED-0001"),
            accepted_at=CanonicalTimestamp("2026-05-22T11:00:00Z"),
        )
        failed_receipt = failed_control.finalize_failed_source_import_no_retry(
            no_retry
        )
        cases = (
            ("TR-001", start_control, started, None),
            ("TR-002", complete_control, completed, None),
            (
                "TR-003",
                exception_control,
                completed_with_exceptions,
                None,
            ),
            ("TR-004", failed_control, failed_receipt, no_retry),
        )
        registries = load_doi_registries()
        for transition_id, control, owner_result, command_owner in cases:
            with self.subTest(transition=transition_id):
                transition = registries.transition_ref(transition_id)
                definition = transition_definition(transition)
                run = (
                    owner_result.run
                    if transition_id != "TR-004"
                    else control.run(no_retry.run_id)
                )
                event = (
                    owner_result.run_event
                    if transition_id != "TR-004"
                    else control.run_events(run.run_id)[-1]
                )
                stream_id = run_transition_stream_id(run)
                occurrence_id = run_transition_occurrence_id(event)
                proof = make_run_control_transition_guard_proof(
                    transition=transition,
                    stream_id=stream_id,
                    occurrence_id=occurrence_id,
                    run_control=control,
                    owner_result=owner_result,
                    accepted_command=command_owner,
                )
                lifecycle_command = make_transition_command(
                    transition=transition,
                    stream_id=stream_id,
                    occurrence_id=occurrence_id,
                    current_state=definition.from_state,
                    expected_sequence=1,
                    expected_predecessor_sha256=None,
                    guard_proof=proof,
                )
                reduced = reduce_transition(
                    TransitionStream.initial(
                        stream_id=stream_id,
                        state=definition.from_state,
                    ),
                    lifecycle_command,
                    occurred_at=event.occurred_at,
                )
                self.assertEqual(reduced.event.transition, transition)

    def test_extraction_owner_reducer_proves_tr005_and_tr006(self) -> None:
        registries = load_doi_registries()
        successful_surface = _surface()
        successful = extract_order_snapshot(successful_surface)
        failed_surface = dataclasses.replace(
            successful_surface,
            observed_order_id=DoiOrderId(OrderId("SYN-ORDER-OTHER")),
        )
        failed = extract_order_snapshot(failed_surface)
        for transition_id, surface, result in (
            ("TR-005", successful_surface, successful),
            ("TR-006", failed_surface, failed),
        ):
            with self.subTest(transition=transition_id):
                transition = registries.transition_ref(transition_id)
                stream_id = extraction_transition_stream_id(result.attempt)
                occurrence_id = extraction_transition_occurrence_id(result.attempt)
                proof = make_extraction_transition_guard_proof(
                    transition=transition,
                    stream_id=stream_id,
                    occurrence_id=occurrence_id,
                    surface=surface,
                    result=result,
                )
                self.assertIs(
                    proof.authority_evidence.evidence_kind,
                    TransitionGuardEvidenceKind.EXTRACTION_REDUCTION,
                )
                definition = transition_definition(transition)
                command = make_transition_command(
                    transition=transition,
                    stream_id=stream_id,
                    occurrence_id=occurrence_id,
                    current_state=definition.from_state,
                    expected_sequence=1,
                    expected_predecessor_sha256=None,
                    guard_proof=proof,
                )
                reduced = reduce_transition(
                    TransitionStream.initial(
                        stream_id=stream_id,
                        state=definition.from_state,
                    ),
                    command,
                    occurred_at=result.attempt.completed_at,
                )
                self.assertEqual(reduced.event.transition, transition)

        with self.assertRaisesRegex(
            LifecycleConflictError,
            "EXTRACTION_REDUCTION_OWNER_INVALID",
        ):
            make_extraction_transition_guard_proof(
                transition=registries.transition_ref("TR-005"),
                stream_id=extraction_transition_stream_id(successful.attempt),
                occurrence_id=extraction_transition_occurrence_id(
                    successful.attempt
                ),
                surface=successful_surface,
                result=failed,
            )

    def test_source_owner_reducers_prove_tr098_through_tr104(self) -> None:
        registries = load_doi_registries()

        def assert_reduces(
            transition_id: str,
            stream_id: EvidenceId,
            occurrence_id: EvidenceId,
            proof: TransitionGuardProof,
            occurred_at: CanonicalTimestamp,
        ) -> None:
            transition = registries.transition_ref(transition_id)
            definition = transition_definition(transition)
            command = make_transition_command(
                transition=transition,
                stream_id=stream_id,
                occurrence_id=occurrence_id,
                current_state=definition.from_state,
                expected_sequence=1,
                expected_predecessor_sha256=None,
                guard_proof=proof,
            )
            reduced = reduce_transition(
                TransitionStream.initial(
                    stream_id=stream_id,
                    state=definition.from_state,
                ),
                command,
                occurred_at=occurred_at,
            )
            self.assertEqual(reduced.event.transition.transition_id, transition_id)

        control = InMemoryDOIRunControl()
        started = control.begin_review_run(
            run_id=RunId("SYN-RUN-LIFECYCLE-SOURCE-PRIMARY"),
            invocation_id=RunInvocationId(
                InteractionId("SYN-INTERACTION-LIFECYCLE-SOURCE-PRIMARY")
            ),
            source_identity_id=SourceIdentityId(
                EvidenceId("SYN-EVIDENCE-LIFECYCLE-SOURCE-PRIMARY")
            ),
            locked_tab=SyntheticQueueTab.MONDAY,
            tab_confirmed=True,
            accepted_at=CanonicalTimestamp("2026-05-22T10:00:00Z"),
        )
        self.assertIsNotNone(started.source_attempt)
        self.assertIsNotNone(started.source_attempt_event)
        initial_attempt = started.source_attempt
        initial_event = started.source_attempt_event
        initial_stream = source_import_transition_stream_id(initial_attempt)
        initial_occurrence = source_import_event_occurrence_id(initial_event)
        initial_proof = make_source_import_start_guard_proof(
            transition=registries.transition_ref("TR-098"),
            stream_id=initial_stream,
            occurrence_id=initial_occurrence,
            run_control=control,
            started_attempt=initial_attempt,
        )
        assert_reduces(
            "TR-098",
            initial_stream,
            initial_occurrence,
            initial_proof,
            initial_event.occurred_at,
        )

        conflict_image = _image(
            (
                _row(1, "SYN-ORDER-2"),
                _row(2, "SYN-ORDER-2", "OTHER_REP"),
            )
        )
        candidate_batch_id = SourceBatchId(
            EvidenceId("SYN-EVIDENCE-LIFECYCLE-SOURCE-BATCH-CREATED")
        )
        source_result = ingest_synthetic_queue(
            conflict_image,
            conflict_image,
            candidate_batch_id=candidate_batch_id,
        )
        committed = control.commit_import_result(
            attempt_id=initial_attempt.attempt_id,
            result=source_result,
            completed_at=CanonicalTimestamp("2026-05-22T10:01:00Z"),
        )
        terminal_event = control.attempt_events(committed.attempt_id)[-1]
        attempt_stream = source_import_transition_stream_id(committed)
        terminal_occurrence = source_import_event_occurrence_id(terminal_event)
        for transition_id, stream_id, rejected_record in (
            ("TR-099", attempt_stream, None),
            (
                "TR-101",
                control.source_batch(committed.source_batch_id).batch_id.value,
                None,
            ),
            (
                "TR-103",
                identity_retention_stream_id(
                    control.source_batch(
                        committed.source_batch_id
                    ).rejected_records[0]
                ),
                control.source_batch(
                    committed.source_batch_id
                ).rejected_records[0],
            ),
        ):
            with self.subTest(transition=transition_id):
                proof = make_source_import_commit_guard_proof(
                    transition=registries.transition_ref(transition_id),
                    stream_id=stream_id,
                    occurrence_id=terminal_occurrence,
                    run_control=control,
                    committed_attempt=committed,
                    source_result=source_result,
                    before_image=conflict_image,
                    after_image=conflict_image,
                    candidate_batch_id=candidate_batch_id,
                    rejected_record=rejected_record,
                )
                assert_reduces(
                    transition_id,
                    stream_id,
                    terminal_occurrence,
                    proof,
                    terminal_event.occurred_at,
                )

        terminal_run = control.finalize_processing(
            run_id=started.run.run_id,
            completed_at=CanonicalTimestamp("2026-05-22T10:02:00Z"),
        ).run
        rejected = control.source_batch(
            committed.source_batch_id
        ).rejected_records[0]
        retention_stream = identity_retention_stream_id(rejected)
        retention_occurrence = source_rejection_retention_occurrence_id(
            rejected,
            terminal_run,
        )
        retention_proof = make_source_rejection_retention_guard_proof(
            transition=registries.transition_ref("TR-104"),
            stream_id=retention_stream,
            occurrence_id=retention_occurrence,
            run_control=control,
            rejected_record=rejected,
            terminal_run=terminal_run,
        )
        assert_reduces(
            "TR-104",
            retention_stream,
            retention_occurrence,
            retention_proof,
            terminal_run.completed_at,
        )

        reused_start = control.begin_review_run(
            run_id=RunId("SYN-RUN-LIFECYCLE-SOURCE-REUSED"),
            invocation_id=RunInvocationId(
                InteractionId("SYN-INTERACTION-LIFECYCLE-SOURCE-REUSED")
            ),
            source_identity_id=SourceIdentityId(
                EvidenceId("SYN-EVIDENCE-LIFECYCLE-SOURCE-PRIMARY")
            ),
            locked_tab=SyntheticQueueTab.MONDAY,
            tab_confirmed=True,
            accepted_at=CanonicalTimestamp("2026-05-22T11:00:00Z"),
        )
        self.assertIsNotNone(reused_start.source_attempt)
        reused_candidate_id = SourceBatchId(
            EvidenceId("SYN-EVIDENCE-LIFECYCLE-SOURCE-BATCH-REUSED")
        )
        reused_result = ingest_synthetic_queue(
            conflict_image,
            conflict_image,
            candidate_batch_id=reused_candidate_id,
        )
        reused_attempt = control.commit_import_result(
            attempt_id=reused_start.source_attempt.attempt_id,
            result=reused_result,
            completed_at=CanonicalTimestamp("2026-05-22T11:01:00Z"),
        )
        reused_event = control.attempt_events(reused_attempt.attempt_id)[-1]
        reused_batch = control.source_batch(reused_attempt.source_batch_id)
        reused_occurrence = source_import_event_occurrence_id(reused_event)
        reused_proof = make_source_import_commit_guard_proof(
            transition=registries.transition_ref("TR-102"),
            stream_id=reused_batch.batch_id.value,
            occurrence_id=reused_occurrence,
            run_control=control,
            committed_attempt=reused_attempt,
            source_result=reused_result,
            before_image=conflict_image,
            after_image=conflict_image,
            candidate_batch_id=reused_candidate_id,
        )
        assert_reduces(
            "TR-102",
            reused_batch.batch_id.value,
            reused_occurrence,
            reused_proof,
            reused_event.occurred_at,
        )
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "SOURCE_IMPORT_COMMIT_ROUTE_INVALID",
        ):
            make_source_import_commit_guard_proof(
                transition=registries.transition_ref("TR-103"),
                stream_id=identity_retention_stream_id(rejected),
                occurrence_id=reused_occurrence,
                run_control=control,
                committed_attempt=reused_attempt,
                source_result=reused_result,
                before_image=conflict_image,
                after_image=conflict_image,
                candidate_batch_id=reused_candidate_id,
                rejected_record=rejected,
            )
        reused_terminal_run = control.finalize_processing(
            run_id=reused_start.run.run_id,
            completed_at=CanonicalTimestamp("2026-05-23T11:02:00Z"),
        ).run
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "SOURCE_REJECTION_RETENTION_OWNER_INVALID",
        ):
            make_source_rejection_retention_guard_proof(
                transition=registries.transition_ref("TR-104"),
                stream_id=retention_stream,
                occurrence_id=source_rejection_retention_occurrence_id(
                    rejected,
                    reused_terminal_run,
                ),
                run_control=control,
                rejected_record=rejected,
                terminal_run=reused_terminal_run,
            )

        failure_control = InMemoryDOIRunControl()
        failure_start = failure_control.begin_review_run(
            run_id=RunId("SYN-RUN-LIFECYCLE-SOURCE-FAILURE"),
            invocation_id=RunInvocationId(
                InteractionId("SYN-INTERACTION-LIFECYCLE-SOURCE-FAILURE")
            ),
            source_identity_id=SourceIdentityId(
                EvidenceId("SYN-EVIDENCE-LIFECYCLE-SOURCE-FAILURE")
            ),
            locked_tab=SyntheticQueueTab.MONDAY,
            tab_confirmed=True,
            accepted_at=CanonicalTimestamp("2026-05-22T12:00:00Z"),
        )
        self.assertIsNotNone(failure_start.source_attempt)
        invalid_image = _image((_row(1, "SYN-ORDER-INVALID"),))
        failed_candidate_id = SourceBatchId(
            EvidenceId("SYN-EVIDENCE-LIFECYCLE-SOURCE-BATCH-FAILED")
        )
        failed_result = ingest_synthetic_queue(
            invalid_image,
            invalid_image,
            candidate_batch_id=failed_candidate_id,
        )
        failed_attempt = failure_control.commit_import_result(
            attempt_id=failure_start.source_attempt.attempt_id,
            result=failed_result,
            completed_at=CanonicalTimestamp("2026-05-22T12:01:00Z"),
        )
        failed_event = failure_control.attempt_events(failed_attempt.attempt_id)[-1]
        failed_stream = source_import_transition_stream_id(failed_attempt)
        failed_occurrence = source_import_event_occurrence_id(failed_event)
        failed_proof = make_source_import_commit_guard_proof(
            transition=registries.transition_ref("TR-100"),
            stream_id=failed_stream,
            occurrence_id=failed_occurrence,
            run_control=failure_control,
            committed_attempt=failed_attempt,
            source_result=failed_result,
            before_image=invalid_image,
            after_image=invalid_image,
            candidate_batch_id=failed_candidate_id,
        )
        assert_reduces(
            "TR-100",
            failed_stream,
            failed_occurrence,
            failed_proof,
            failed_event.occurred_at,
        )

        retry_command_id = AcceptedCommandId(
            InteractionId("SYN-INTERACTION-LIFECYCLE-SOURCE-RETRY")
        )
        retry_attempt = failure_control.retry_source_import(
            run_id=failure_start.run.run_id,
            command_id=retry_command_id,
            source_identity_id=SourceIdentityId(
                EvidenceId("SYN-EVIDENCE-LIFECYCLE-SOURCE-FAILURE")
            ),
            accepted_at=CanonicalTimestamp("2026-05-22T12:02:00Z"),
        )
        retry_event = failure_control.attempt_events(retry_attempt.attempt_id)[0]
        retry_stream = source_import_transition_stream_id(retry_attempt)
        retry_occurrence = source_import_event_occurrence_id(retry_event)
        retry_proof = make_source_import_start_guard_proof(
            transition=registries.transition_ref("TR-098"),
            stream_id=retry_stream,
            occurrence_id=retry_occurrence,
            run_control=failure_control,
            started_attempt=retry_attempt,
            retry_command_id=retry_command_id,
        )
        assert_reduces(
            "TR-098",
            retry_stream,
            retry_occurrence,
            retry_proof,
            retry_event.occurred_at,
        )

        with self.assertRaisesRegex(
            LifecycleConflictError,
            "SOURCE_IMPORT_COMMIT_ROUTE_INVALID",
        ):
            make_source_import_commit_guard_proof(
                transition=registries.transition_ref("TR-102"),
                stream_id=control.source_batch(
                    committed.source_batch_id
                ).batch_id.value,
                occurrence_id=terminal_occurrence,
                run_control=control,
                committed_attempt=committed,
                source_result=source_result,
                before_image=conflict_image,
                after_image=conflict_image,
                candidate_batch_id=candidate_batch_id,
            )

    def test_product_knowledge_owner_reducers_prove_tr040_042_and_tr082_083(self) -> None:
        registries = load_doi_registries()
        created = relationship()
        updated = append_relationship_revision(
            created,
            revision_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-RELATIONSHIP-UPDATED"
            ),
            revision_kind=AlternateRevisionKind.UPDATED,
            state=AlternateRelationshipState.ACTIVE,
            compatibility_review_required=False,
            evidence_source=product_source(created.candidate_sku, "LIFECYCLE-UPDATED"),
        )
        superseded = append_relationship_revision(
            created,
            revision_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-RELATIONSHIP-SUPERSEDED"
            ),
            revision_kind=AlternateRevisionKind.SUPERSEDED,
            state=AlternateRelationshipState.SUPERSEDED,
            compatibility_review_required=False,
            evidence_source=product_source(
                created.candidate_sku,
                "LIFECYCLE-SUPERSEDED",
            ),
        )
        invalidated = append_relationship_revision(
            created,
            revision_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-RELATIONSHIP-INVALIDATED"
            ),
            revision_kind=AlternateRevisionKind.INVALIDATED,
            state=AlternateRelationshipState.INVALIDATED,
            compatibility_review_required=False,
            evidence_source=product_source(
                created.candidate_sku,
                "LIFECYCLE-INVALIDATED",
            ),
        )
        routes = (
            ("TR-082", None, created),
            ("TR-083", created, updated),
            ("TR-040", created, superseded),
            ("TR-041", created, invalidated),
        )
        for transition_id, prior, result_relationship in routes:
            with self.subTest(transition=transition_id):
                transition = registries.transition_ref(transition_id)
                stream_id = result_relationship.relationship_id
                occurrence_id = result_relationship.current_revision.revision_id
                proof = make_relationship_transition_guard_proof(
                    transition=transition,
                    stream_id=stream_id,
                    occurrence_id=occurrence_id,
                    prior_relationship=prior,
                    result_relationship=result_relationship,
                    recorded_at=OBSERVED_AT,
                )
                self.assertIs(
                    proof.authority_evidence.evidence_kind,
                    TransitionGuardEvidenceKind.PRODUCT_KNOWLEDGE_REDUCTION,
                )
                definition = transition_definition(transition)
                command = make_transition_command(
                    transition=transition,
                    stream_id=stream_id,
                    occurrence_id=occurrence_id,
                    current_state=definition.from_state,
                    expected_sequence=1,
                    expected_predecessor_sha256=None,
                    guard_proof=proof,
                )
                reduced = reduce_transition(
                    TransitionStream.initial(
                        stream_id=stream_id,
                        state=definition.from_state,
                    ),
                    command,
                    occurred_at=OBSERVED_AT,
                )
                self.assertEqual(reduced.event.transition, transition)

        context = knowledge_action_context("LIFECYCLE-OBSERVATION")
        observation = DOIAlternateObservation(
            observation_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-ALTERNATE-OBSERVATION"
            ),
            action_context_id=context.action_context_id,
            action_context_binding=context.hash_binding(),
            relationship_revision_binding=created.current_revision.hash_binding(),
            candidate_sku=created.candidate_sku,
            state=AlternateObservationState.CURRENT,
            observed_availability=known_fact(AlternateAvailability.IN_STOCK),
            observed_eta=not_applicable_fact(),
            observed_price=not_applicable_fact(),
            observed_at=OBSERVED_AT,
            source=product_source(created.candidate_sku, "LIFECYCLE-OBSERVATION"),
        )
        observation_occurrence = alternate_observation_occurrence_id(observation)
        observation_proof = make_alternate_observation_transition_guard_proof(
            transition=registries.transition_ref("TR-042"),
            stream_id=observation.observation_id,
            occurrence_id=observation_occurrence,
            observation=observation,
            relationship=created,
            action_context=context,
        )
        definition = transition_definition(registries.transition_ref("TR-042"))
        command = make_transition_command(
            transition=registries.transition_ref("TR-042"),
            stream_id=observation.observation_id,
            occurrence_id=observation_occurrence,
            current_state=definition.from_state,
            expected_sequence=1,
            expected_predecessor_sha256=None,
            guard_proof=observation_proof,
        )
        reduced = reduce_transition(
            TransitionStream.initial(
                stream_id=observation.observation_id,
                state=definition.from_state,
            ),
            command,
            occurred_at=OBSERVED_AT,
        )
        self.assertEqual(reduced.event.transition.transition_id, "TR-042")

        with self.assertRaisesRegex(
            LifecycleConflictError,
            "ALTERNATE_OBSERVATION_OWNER_INVALID",
        ):
            make_alternate_observation_transition_guard_proof(
                transition=registries.transition_ref("TR-042"),
                stream_id=observation.observation_id,
                occurrence_id=observation_occurrence,
                observation=observation,
                relationship=created,
                action_context=knowledge_action_context(
                    "LIFECYCLE-OBSERVATION-WRONG"
                ),
            )

    def test_action_context_owner_reducer_proves_tr084_085_and_both_tr087_routes(
        self,
    ) -> None:
        registries = load_doi_registries()
        base_request = evaluation_input(
            split_lines(),
            evaluation_suffix="LIFECYCLE-ACTION-CONTEXT-BASE",
        )
        base_evaluation = evaluate_doi(base_request)
        split = next(
            item
            for item in base_evaluation.opportunities
            if item.opportunity_type is OpportunityType.FULFILLMENT_SPLIT
        )
        (
            first_context,
            first_open,
            first_case,
            first_case_source,
            _,
            _,
        ) = open_context_fixture(
            base_request.snapshot,
            "LIFECYCLE-ACTION-CONTEXT-FIRST",
            evaluation=base_evaluation,
            opportunity=split,
            context_kind=ActionContextKind.FULFILLMENT_SPLIT_REVIEW,
        )
        empty_store = DOIActionContextStore()
        tr084 = registries.transition_ref("TR-084")
        tr084_occurrence = action_context_event_occurrence_id(first_open)
        tr084_proof = make_action_context_transition_guard_proof(
            transition=tr084,
            stream_id=first_context.action_context_id,
            occurrence_id=tr084_occurrence,
            prior_store=empty_store,
            event=first_open,
        )
        self.assertEqual(
            _reduce_owner_guard_proof(
                transition=tr084,
                stream_id=first_context.action_context_id,
                occurrence_id=tr084_occurrence,
                proof=tr084_proof,
                occurred_at=first_open.occurred_at,
            ).transition,
            tr084,
        )
        first_store = reduce_action_context_store(empty_store, first_open).store

        abandoned_source = _interaction_source("ACTION-CONTEXT-ABANDONED")
        abandoned_authority = verify_synthetic_human_authority(
            grant_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-ACTION-CONTEXT-ABANDONED-AUTH"
            ),
            actor=RepId("SYN-REP-LIFECYCLE-ACTION-CONTEXT-ABANDONED"),
            action_context=first_context,
            granted_at=OBSERVED_AT,
            authority_source=abandoned_source,
        )
        abandoned_id = EvidenceId(
            "SYN-EVIDENCE-LIFECYCLE-ACTION-CONTEXT-ABANDONED"
        )
        abandoned = DOIActionContextEvent.abandoned(
            event_id=abandoned_id,
            action_context=first_context,
            authority=abandoned_authority,
            occurred_at=CanonicalTimestamp("2026-08-20T14:16:00Z"),
            guard=DOIOccurrenceGuard(
                guard_id=abandoned_id,
                owner_id=first_context.action_context_id,
                occurrence_id=abandoned_source.object_id,
                source=abandoned_source,
            ),
        )
        tr087 = registries.transition_ref("TR-087")
        abandoned_occurrence = action_context_event_occurrence_id(abandoned)
        abandoned_proof = make_action_context_transition_guard_proof(
            transition=tr087,
            stream_id=first_context.action_context_id,
            occurrence_id=abandoned_occurrence,
            prior_store=first_store,
            event=abandoned,
            human_authority=abandoned_authority,
        )
        self.assertEqual(
            _reduce_owner_guard_proof(
                transition=tr087,
                stream_id=first_context.action_context_id,
                occurrence_id=abandoned_occurrence,
                proof=abandoned_proof,
                occurred_at=abandoned.occurred_at,
            ).transition,
            tr087,
        )

        superseding_source = _interaction_source("ACTION-CONTEXT-SUPERSEDING")
        superseding_authorization = verify_action_context_opening_authority(
            authorization_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-ACTION-CONTEXT-SUPERSEDING-AUTH"
            ),
            attempt_intent_id=superseding_source.object_id,
            case=first_case,
            case_source_binding=first_case_source,
            evaluation=base_evaluation,
            opportunity=split,
            context_kind=ActionContextKind.FULFILLMENT_SPLIT_REVIEW,
            actor=RepId("SYN-REP-LIFECYCLE-ACTION-CONTEXT-SUPERSEDING"),
            granted_at=CanonicalTimestamp("2026-08-20T14:17:00Z"),
            authority_source=superseding_source,
        )
        superseding_context_id = EvidenceId(
            "SYN-EVIDENCE-LIFECYCLE-ACTION-CONTEXT-SUPERSEDING-CONTEXT"
        )
        superseding_open_id = EvidenceId(
            "SYN-EVIDENCE-LIFECYCLE-ACTION-CONTEXT-SUPERSEDING-OPEN"
        )
        superseding_open = DOIActionContextEvent.opened(
            event_id=superseding_open_id,
            action_context_id=superseding_context_id,
            opening_authorization=superseding_authorization,
            created_at=CanonicalTimestamp("2026-08-20T14:17:00Z"),
            guard=DOIOccurrenceGuard(
                guard_id=superseding_open_id,
                owner_id=superseding_context_id,
                occurrence_id=superseding_source.object_id,
                source=superseding_source,
            ),
        )
        store_with_later_attempt = reduce_action_context_store(
            first_store,
            superseding_open,
        ).store
        superseded_id = EvidenceId(
            "SYN-EVIDENCE-LIFECYCLE-ACTION-CONTEXT-SUPERSEDED"
        )
        superseded = DOIActionContextEvent.superseded(
            event_id=superseded_id,
            action_context=first_context,
            superseding_open_event=superseding_open,
            occurred_at=CanonicalTimestamp("2026-08-20T14:18:00Z"),
            guard=DOIOccurrenceGuard(
                guard_id=superseded_id,
                owner_id=first_context.action_context_id,
                occurrence_id=superseding_source.object_id,
                source=superseding_source,
            ),
        )
        superseded_occurrence = action_context_event_occurrence_id(superseded)
        superseded_proof = make_action_context_transition_guard_proof(
            transition=tr087,
            stream_id=first_context.action_context_id,
            occurrence_id=superseded_occurrence,
            prior_store=store_with_later_attempt,
            event=superseded,
        )
        self.assertEqual(
            _reduce_owner_guard_proof(
                transition=tr087,
                stream_id=first_context.action_context_id,
                occurrence_id=superseded_occurrence,
                proof=superseded_proof,
                occurred_at=superseded.occurred_at,
            ).transition,
            tr087,
        )

        ordered_line = base_request.snapshot.lines[0]
        ordered_sku = ordered_line.es_number.value
        ordered_mfg = ordered_line.mfg_number.value
        if type(ordered_sku) is not SkuId or type(ordered_mfg) is not SkuId:
            raise AssertionError("alternate test requires known ordered identifiers")
        alternate_sku = SkuId(
            "SYN-SKU-LIFECYCLE-ACTION-CONTEXT-ALTERNATE"
        )
        relation = create_relationship(
            relationship_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-ACTION-CONTEXT-RELATIONSHIP"
            ),
            revision_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-ACTION-CONTEXT-RELATIONSHIP-REV"
            ),
            relationship_type=AlternateRelationshipType.EXACT_MFG,
            ordered_sku=ordered_sku,
            candidate_sku=alternate_sku,
            ordered_mfg=ordered_mfg,
            candidate_mfg=ordered_mfg,
            compatibility_review_required=False,
            evidence_source=product_source(
                alternate_sku,
                "LIFECYCLE-ACTION-CONTEXT-RELATIONSHIP",
            ),
        )
        first_observation = DOIAlternateObservation(
            observation_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-ACTION-CONTEXT-FIRST-OBS"
            ),
            action_context_id=first_context.action_context_id,
            action_context_binding=first_context.hash_binding(),
            relationship_revision_binding=relation.current_revision.hash_binding(),
            candidate_sku=relation.candidate_sku,
            state=AlternateObservationState.CURRENT,
            observed_availability=known_fact(AlternateAvailability.IN_STOCK),
            observed_eta=not_applicable_fact(),
            observed_price=known_fact(usd("15.00")),
            observed_at=OBSERVED_AT,
            source=product_source(
                relation.candidate_sku,
                "LIFECYCLE-ACTION-CONTEXT-FIRST-OBS",
            ),
        )
        candidate = candidate_from_relationship(
            candidate_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-ACTION-CONTEXT-CANDIDATE"
            ),
            relationship=relation,
            observation=first_observation,
            ordered_line_id=base_request.snapshot.lines[0].line_snapshot_id,
            quantity=PositiveQuantity(1),
            compatibility_decision=CompatibilityDecision.NOT_REQUIRED,
        )
        alternate_request = DOIEvaluationInput(
            evaluation_id=EvaluationId(
                "SYN-EVALUATION-LIFECYCLE-ACTION-CONTEXT-ALTERNATE"
            ),
            snapshot=base_request.snapshot,
            evaluated_at=OBSERVED_AT,
            alternate_research_state=AlternateResearchState.COMPLETE,
            alternate_candidates=(candidate,),
        )
        alternate_evaluation = evaluate_doi(alternate_request)
        alternate_opportunity = next(
            item
            for item in alternate_evaluation.opportunities
            if item.opportunity_type is OpportunityType.EXACT_MFG_ALTERNATE
        )
        second_context, second_open, _, _, _, _ = open_context_fixture(
            alternate_request.snapshot,
            "LIFECYCLE-ACTION-CONTEXT-SECOND",
            evaluation=alternate_evaluation,
            opportunity=alternate_opportunity,
            context_kind=ActionContextKind.SUBSTITUTION,
        )
        second_store = reduce_action_context_store(
            DOIActionContextStore(),
            second_open,
        ).store
        second_observed_at = CanonicalTimestamp("2026-08-20T14:19:00Z")
        second_observation = DOIAlternateObservation(
            observation_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-ACTION-CONTEXT-SECOND-OBS"
            ),
            action_context_id=second_context.action_context_id,
            action_context_binding=second_context.hash_binding(),
            relationship_revision_binding=relation.current_revision.hash_binding(),
            candidate_sku=relation.candidate_sku,
            state=AlternateObservationState.CURRENT,
            observed_availability=known_fact(AlternateAvailability.IN_STOCK),
            observed_eta=not_applicable_fact(),
            observed_price=known_fact(usd("14.00")),
            observed_at=second_observed_at,
            source=product_source(
                relation.candidate_sku,
                "LIFECYCLE-ACTION-CONTEXT-SECOND-OBS",
            ),
        )
        link_source = _interaction_source("ACTION-CONTEXT-LINK")
        link_authority = verify_synthetic_human_authority(
            grant_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-ACTION-CONTEXT-LINK-AUTH"
            ),
            actor=RepId("SYN-REP-LIFECYCLE-ACTION-CONTEXT-LINK"),
            action_context=second_context,
            granted_at=second_observed_at,
            authority_source=link_source,
        )
        link_event_id = EvidenceId(
            "SYN-EVIDENCE-LIFECYCLE-ACTION-CONTEXT-LINK-EVENT"
        )
        link_event = DOIActionContextEvent.observation_linked(
            event_id=link_event_id,
            action_context=second_context,
            link_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-ACTION-CONTEXT-LINK"
            ),
            observation=second_observation,
            relationship_revision=relation.current_revision,
            authority=link_authority,
            linked_at=second_observed_at,
            guard=DOIOccurrenceGuard(
                guard_id=link_event_id,
                owner_id=second_context.action_context_id,
                occurrence_id=link_source.object_id,
                source=link_source,
            ),
        )
        tr085 = registries.transition_ref("TR-085")
        link_occurrence = action_context_event_occurrence_id(link_event)
        link_proof = make_action_context_transition_guard_proof(
            transition=tr085,
            stream_id=second_context.action_context_id,
            occurrence_id=link_occurrence,
            prior_store=second_store,
            event=link_event,
            observation=second_observation,
            relationship_revision=relation.current_revision,
            human_authority=link_authority,
        )
        self.assertEqual(
            _reduce_owner_guard_proof(
                transition=tr085,
                stream_id=second_context.action_context_id,
                occurrence_id=link_occurrence,
                proof=link_proof,
                occurred_at=link_event.occurred_at,
            ).transition,
            tr085,
        )
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "ACTION_CONTEXT_OBSERVATION_LINK_ROUTE_INVALID",
        ):
            make_action_context_transition_guard_proof(
                transition=tr085,
                stream_id=second_context.action_context_id,
                occurrence_id=link_occurrence,
                prior_store=second_store,
                event=link_event,
                observation=first_observation,
                relationship_revision=relation.current_revision,
                human_authority=link_authority,
            )
        equal_time_observation = dataclasses.replace(
            second_observation,
            observation_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-ACTION-CONTEXT-EQUAL-TIME-OBS"
            ),
            observed_at=second_context.created_at,
        )
        equal_time_event_id = EvidenceId(
            "SYN-EVIDENCE-LIFECYCLE-ACTION-CONTEXT-EQUAL-TIME-EVENT"
        )
        equal_time_event = DOIActionContextEvent.observation_linked(
            event_id=equal_time_event_id,
            action_context=second_context,
            link_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-ACTION-CONTEXT-EQUAL-TIME-LINK"
            ),
            observation=equal_time_observation,
            relationship_revision=relation.current_revision,
            authority=link_authority,
            linked_at=second_observed_at,
            guard=DOIOccurrenceGuard(
                guard_id=equal_time_event_id,
                owner_id=second_context.action_context_id,
                occurrence_id=link_source.object_id,
                source=link_source,
            ),
        )
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "ACTION_CONTEXT_OBSERVATION_LINK_ROUTE_INVALID",
        ):
            make_action_context_transition_guard_proof(
                transition=tr085,
                stream_id=second_context.action_context_id,
                occurrence_id=action_context_event_occurrence_id(
                    equal_time_event
                ),
                prior_store=second_store,
                event=equal_time_event,
                observation=equal_time_observation,
                relationship_revision=relation.current_revision,
                human_authority=link_authority,
            )
        changed_relation = append_relationship_revision(
            relation,
            revision_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-ACTION-CONTEXT-WRONG-REVISION"
            ),
            revision_kind=AlternateRevisionKind.UPDATED,
            state=AlternateRelationshipState.ACTIVE,
            compatibility_review_required=False,
            evidence_source=product_source(
                relation.candidate_sku,
                "LIFECYCLE-ACTION-CONTEXT-WRONG-REVISION",
            ),
        )
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "ACTION_CONTEXT_OBSERVATION_LINK_ROUTE_INVALID",
        ):
            make_action_context_transition_guard_proof(
                transition=tr085,
                stream_id=second_context.action_context_id,
                occurrence_id=link_occurrence,
                prior_store=second_store,
                event=link_event,
                observation=second_observation,
                relationship_revision=changed_relation.current_revision,
                human_authority=link_authority,
            )

    def test_contact_workflow_owner_reducer_proves_every_registered_edge(self) -> None:
        registries = load_doi_registries()
        request = evaluation_input(
            split_lines(),
            evaluation_suffix="LIFECYCLE-CONTACT-WORKFLOW",
            geography=GeographyClass.INTERNATIONAL,
        )
        evaluation = evaluate_doi(request)
        self.assertIn(
            HandlingFlag.CUSTOMER_CONTACT_BEFORE_SPLIT,
            evaluation.handling_flags,
        )
        opportunity = next(
            item
            for item in evaluation.opportunities
            if item.opportunity_type is OpportunityType.FULFILLMENT_SPLIT
        )
        context, opening, _, _, _, _ = open_context_fixture(
            request.snapshot,
            "LIFECYCLE-CONTACT-WORKFLOW",
            evaluation=evaluation,
            opportunity=opportunity,
            context_kind=ActionContextKind.CUSTOMER_CONTACT,
        )
        context_history = reduce_action_context(
            DOIActionContextHistory(action_context_id=context.action_context_id),
            opening,
        ).history
        stream_id = EvidenceId(
            "SYN-EVIDENCE-LIFECYCLE-CONTACT-WORKFLOW-STREAM"
        )
        empty = ContactWorkflowHistory.empty(
            stream_id=stream_id,
            action_context=context,
        )

        system_id = EvidenceId(
            "SYN-EVIDENCE-LIFECYCLE-CONTACT-WORKFLOW-REQUIRED"
        )
        system_source = _interaction_source("CONTACT-WORKFLOW-REQUIRED")
        required = ContactWorkflowEvent(
            event_id=system_id,
            stream_id=stream_id,
            action_context=context,
            prior_state=ContactWorkflowState.NOT_CONTACTED,
            resulting_state=ContactWorkflowState.CONTACT_REQUIRED,
            event_type=ContactWorkflowEventType.CONTACT_REQUIRED_DERIVED,
            evaluation=evaluation,
            human_authority=None,
            contact_occurred_at=None,
            recorded_at=OBSERVED_AT,
            sequence=1,
            predecessor_binding=None,
            guard=DOIOccurrenceGuard(
                guard_id=system_id,
                owner_id=stream_id,
                occurrence_id=system_source.object_id,
                source=system_source,
            ),
        )

        seen: set[str] = set()

        def prove(
            transition_id: str,
            prior: ContactWorkflowHistory,
            event: ContactWorkflowEvent,
            *,
            system_input: DOIEvaluationInput | None = None,
        ) -> None:
            transition = registries.transition_ref(transition_id)
            occurrence_id = contact_workflow_event_occurrence_id(event)
            proof = make_contact_workflow_transition_guard_proof(
                transition=transition,
                stream_id=stream_id,
                occurrence_id=occurrence_id,
                prior_history=prior,
                event=event,
                action_context_history=context_history,
                evaluation_input=system_input,
            )
            self.assertIs(
                proof.authority_evidence.evidence_kind,
                TransitionGuardEvidenceKind.CONTACT_WORKFLOW_REDUCTION,
            )
            self.assertEqual(
                _reduce_owner_guard_proof(
                    transition=transition,
                    stream_id=stream_id,
                    occurrence_id=occurrence_id,
                    proof=proof,
                    occurred_at=event.recorded_at,
                ).transition,
                transition,
            )
            seen.add(transition_id)

        prove("TR-065", empty, required, system_input=request)
        required_history = reduce_contact_workflow(empty, required).history
        counter = 0

        def human_event(
            prior: ContactWorkflowHistory,
            *,
            event_type: ContactWorkflowEventType,
            resulting_state: ContactWorkflowState,
            suffix: str,
            minute: int,
        ) -> tuple[ContactWorkflowEvent, ContactWorkflowHistory]:
            nonlocal counter
            counter += 1
            event_id = EvidenceId(
                f"SYN-EVIDENCE-LIFECYCLE-CONTACT-WORKFLOW-{suffix}-{counter:02d}"
            )
            source = _interaction_source(
                f"CONTACT-WORKFLOW-{suffix}-{counter:02d}"
            )
            occurred_at = CanonicalTimestamp(
                f"2026-08-20T15:{minute:02d}:00Z"
            )
            authority = verify_synthetic_human_authority(
                grant_id=EvidenceId(
                    f"SYN-EVIDENCE-LIFECYCLE-CONTACT-WORKFLOW-AUTH-{suffix}-{counter:02d}"
                ),
                actor=RepId("SYN-REP-LIFECYCLE-CONTACT-WORKFLOW"),
                action_context=context,
                granted_at=occurred_at,
                authority_source=source,
            )
            event = ContactWorkflowEvent(
                event_id=event_id,
                stream_id=stream_id,
                action_context=context,
                prior_state=prior.projection.state,
                resulting_state=resulting_state,
                event_type=event_type,
                evaluation=None,
                human_authority=authority,
                contact_occurred_at=occurred_at,
                recorded_at=occurred_at,
                sequence=len(prior.events) + 1,
                predecessor_binding=(
                    None if not prior.events else prior.events[-1].hash_binding()
                ),
                guard=DOIOccurrenceGuard(
                    guard_id=event_id,
                    owner_id=stream_id,
                    occurrence_id=source.object_id,
                    source=source,
                ),
            )
            return event, reduce_contact_workflow(prior, event).history

        attempted, attempted_history = human_event(
            required_history,
            event_type=ContactWorkflowEventType.CONTACT_ATTEMPT_RECORDED,
            resulting_state=ContactWorkflowState.CONTACT_ATTEMPTED,
            suffix="ATTEMPTED",
            minute=1,
        )
        prove("TR-066", required_history, attempted)
        direct_attempt, direct_attempt_history = human_event(
            empty,
            event_type=ContactWorkflowEventType.CONTACT_ATTEMPT_RECORDED,
            resulting_state=ContactWorkflowState.CONTACT_ATTEMPTED,
            suffix="DIRECT-ATTEMPT",
            minute=2,
        )
        prove("TR-067", empty, direct_attempt)
        awaiting, awaiting_history = human_event(
            attempted_history,
            event_type=ContactWorkflowEventType.AWAITING_CUSTOMER_RECORDED,
            resulting_state=ContactWorkflowState.AWAITING_CUSTOMER,
            suffix="AWAITING",
            minute=3,
        )
        prove("TR-068", attempted_history, awaiting)
        approved, approved_history = human_event(
            awaiting_history,
            event_type=ContactWorkflowEventType.CUSTOMER_APPROVAL_RECORDED,
            resulting_state=ContactWorkflowState.CUSTOMER_APPROVED,
            suffix="APPROVED",
            minute=4,
        )
        prove("TR-069", awaiting_history, approved)
        declined, declined_history = human_event(
            awaiting_history,
            event_type=ContactWorkflowEventType.CUSTOMER_DECLINE_RECORDED,
            resulting_state=ContactWorkflowState.CUSTOMER_DECLINED,
            suffix="DECLINED",
            minute=5,
        )
        prove("TR-070", awaiting_history, declined)
        no_response, no_response_history = human_event(
            awaiting_history,
            event_type=ContactWorkflowEventType.NO_RESPONSE_RECORDED,
            resulting_state=ContactWorkflowState.NO_RESPONSE,
            suffix="NO-RESPONSE",
            minute=6,
        )
        prove("TR-071", awaiting_history, no_response)
        immediate_approval, _ = human_event(
            attempted_history,
            event_type=ContactWorkflowEventType.CUSTOMER_APPROVAL_RECORDED,
            resulting_state=ContactWorkflowState.CUSTOMER_APPROVED,
            suffix="IMMEDIATE-APPROVAL",
            minute=7,
        )
        prove("TR-072", attempted_history, immediate_approval)
        immediate_decline, _ = human_event(
            attempted_history,
            event_type=ContactWorkflowEventType.CUSTOMER_DECLINE_RECORDED,
            resulting_state=ContactWorkflowState.CUSTOMER_DECLINED,
            suffix="IMMEDIATE-DECLINE",
            minute=8,
        )
        prove("TR-073", attempted_history, immediate_decline)
        withdrawn, _ = human_event(
            approved_history,
            event_type=ContactWorkflowEventType.CUSTOMER_DECLINE_RECORDED,
            resulting_state=ContactWorkflowState.CUSTOMER_DECLINED,
            suffix="WITHDRAWN",
            minute=9,
        )
        prove("TR-081", approved_history, withdrawn)

        tr080_priors = (
            direct_attempt_history,
            awaiting_history,
            declined_history,
            no_response_history,
        )
        for index, prior in enumerate(tr080_priors, start=1):
            later_attempt, _ = human_event(
                prior,
                event_type=ContactWorkflowEventType.CONTACT_ATTEMPT_RECORDED,
                resulting_state=ContactWorkflowState.CONTACT_ATTEMPTED,
                suffix=f"LATER-ATTEMPT-{index}",
                minute=20 + index,
            )
            with self.subTest(
                transition="TR-080",
                from_state=prior.projection.state.value,
            ):
                prove("TR-080", prior, later_attempt)
        self.assertEqual(
            seen,
            {
                "TR-065",
                "TR-066",
                "TR-067",
                "TR-068",
                "TR-069",
                "TR-070",
                "TR-071",
                "TR-072",
                "TR-073",
                "TR-080",
                "TR-081",
            },
        )
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "CONTACT_WORKFLOW_REDUCTION_ROUTE_INVALID",
        ):
            make_contact_workflow_transition_guard_proof(
                transition=registries.transition_ref("TR-066"),
                stream_id=stream_id,
                occurrence_id=contact_workflow_event_occurrence_id(
                    direct_attempt
                ),
                prior_history=empty,
                event=direct_attempt,
                action_context_history=context_history,
            )
        same_time_attempt, _ = human_event(
            direct_attempt_history,
            event_type=ContactWorkflowEventType.CONTACT_ATTEMPT_RECORDED,
            resulting_state=ContactWorkflowState.CONTACT_ATTEMPTED,
            suffix="NOT-LATER",
            minute=2,
        )
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "CONTACT_WORKFLOW_LATER_ATTEMPT_INVALID",
        ):
            make_contact_workflow_transition_guard_proof(
                transition=registries.transition_ref("TR-080"),
                stream_id=stream_id,
                occurrence_id=contact_workflow_event_occurrence_id(
                    same_time_attempt
                ),
                prior_history=direct_attempt_history,
                event=same_time_attempt,
                action_context_history=context_history,
            )

    def test_wwc_owner_reducer_proves_all_partition_and_reevaluation_routes(
        self,
    ) -> None:
        registries = load_doi_registries()
        source = order_source(OrderId("SYN-ORDER-DOI-0001"))
        lines = split_lines()
        self.assertTrue(all(line.source == source for line in lines))
        cases = (
            (
                "TR-074",
                "NOT-APPLICABLE",
                make_wwc(source),
                WWCProjectionState.NOT_APPLICABLE,
            ),
            (
                "TR-075",
                "ACTIVE-SELF",
                make_wwc(
                    source,
                    presence=FindingPresenceV2.PRESENT,
                    author=WWCAuthorRelation.TARGET_REP,
                    timing=WWCTimingState.ACTIVE,
                    marker="WWC_MARKER_ACTIVE_SELF",
                    observed_at=OBSERVED_AT,
                ),
                WWCProjectionState.ACTIVE_SELF,
            ),
            (
                "TR-076",
                "ACTIVE-OTHER",
                make_wwc(
                    source,
                    presence=FindingPresenceV2.PRESENT,
                    author=WWCAuthorRelation.OTHER_REP,
                    timing=WWCTimingState.ACTIVE,
                    marker="WWC_MARKER_ACTIVE_OTHER",
                    observed_at=OBSERVED_AT,
                ),
                WWCProjectionState.ACTIVE_OTHER_REP,
            ),
            (
                "TR-077",
                "EXPIRED-OTHER",
                make_wwc(
                    source,
                    presence=FindingPresenceV2.PRESENT,
                    author=WWCAuthorRelation.OTHER_REP,
                    timing=WWCTimingState.EXPIRED,
                    marker="WWC_MARKER_EXPIRED_OTHER",
                    observed_at=OBSERVED_AT,
                ),
                WWCProjectionState.EXPIRED_OTHER_REP,
            ),
            (
                "TR-078",
                "AUTHOR-UNCERTAIN",
                make_wwc(
                    source,
                    presence=FindingPresenceV2.PRESENT,
                    author=WWCAuthorRelation.UNCERTAIN,
                    timing=WWCTimingState.ACTIVE,
                    marker="WWC_MARKER_AUTHOR_UNCERTAIN",
                    observed_at=OBSERVED_AT,
                ),
                WWCProjectionState.AUTHOR_UNCERTAIN,
            ),
            (
                "TR-078",
                "TIMING-UNCERTAIN",
                make_wwc(
                    source,
                    presence=FindingPresenceV2.PRESENT,
                    author=WWCAuthorRelation.TARGET_REP,
                    timing=WWCTimingState.UNCERTAIN,
                    marker="WWC_MARKER_TIMING_UNCERTAIN",
                    observed_at=OBSERVED_AT,
                ),
                WWCProjectionState.TIMING_UNCERTAIN,
            ),
            (
                "TR-078",
                "AUTHOR-AND-TIMING-UNCERTAIN",
                make_wwc(
                    source,
                    presence=FindingPresenceV2.PRESENT,
                    author=WWCAuthorRelation.UNCERTAIN,
                    timing=WWCTimingState.UNCERTAIN,
                    marker="WWC_MARKER_BOTH_UNCERTAIN",
                    observed_at=OBSERVED_AT,
                ),
                WWCProjectionState.AUTHOR_AND_TIMING_UNCERTAIN,
            ),
        )
        seen: set[str] = set()
        retained: dict[
            str,
            tuple[DOIEvaluationInput, DOIWWCHistory, DOIWWCEvent],
        ] = {}
        for index, (transition_id, suffix, finding, expected_state) in enumerate(
            cases,
            start=1,
        ):
            with self.subTest(transition=transition_id, partition=suffix):
                request = evaluation_input(
                    lines,
                    evaluation_suffix=f"LIFECYCLE-WWC-{suffix}",
                    wwc=finding,
                    snapshot_suffix=f"LIFECYCLE-WWC-{suffix}",
                    run_suffix=f"LIFECYCLE-WWC-{suffix}",
                )
                stream_id = EvidenceId(
                    f"SYN-EVIDENCE-LIFECYCLE-WWC-STREAM-{index:02d}"
                )
                prior = DOIWWCHistory(
                    stream_id=stream_id,
                    order_id=request.snapshot.order_id,
                )
                event_id = EvidenceId(
                    f"SYN-EVIDENCE-LIFECYCLE-WWC-EVENT-{index:02d}"
                )
                event = DOIWWCEvent(
                    event_id=event_id,
                    stream_id=stream_id,
                    order_id=request.snapshot.order_id,
                    event_type=WWCEventType.OBSERVED,
                    finding=finding,
                    corrects_event_id=None,
                    recorded_at=OBSERVED_AT,
                    sequence=1,
                    predecessor_binding=None,
                    guard=occurrence_guard(
                        owner_id=stream_id,
                        event_id=event_id,
                        suffix=f"LIFECYCLE-WWC-{index:02d}",
                    ),
                )
                transition = registries.transition_ref(transition_id)
                occurrence_id = wwc_event_occurrence_id(event)
                proof = make_wwc_transition_guard_proof(
                    transition=transition,
                    stream_id=stream_id,
                    occurrence_id=occurrence_id,
                    prior_history=prior,
                    event=event,
                    evaluation_input=request,
                )
                self.assertIs(
                    proof.authority_evidence.evidence_kind,
                    TransitionGuardEvidenceKind.WWC_REDUCTION,
                )
                self.assertEqual(
                    reduce_wwc(prior, event).history.projection.state,
                    expected_state,
                )
                self.assertEqual(
                    _reduce_owner_guard_proof(
                        transition=transition,
                        stream_id=stream_id,
                        occurrence_id=occurrence_id,
                        proof=proof,
                        occurred_at=event.recorded_at,
                    ).transition,
                    transition,
                )
                seen.add(transition_id)
                retained[suffix] = (
                    request,
                    reduce_wwc(prior, event).history,
                    event,
                )

        first_request, first_history, first_event = retained["NOT-APPLICABLE"]
        updated_finding = make_wwc(
            source,
            presence=FindingPresenceV2.PRESENT,
            author=WWCAuthorRelation.TARGET_REP,
            timing=WWCTimingState.ACTIVE,
            marker="WWC_MARKER_REEVALUATED",
            observed_at=OBSERVED_AT,
        )
        updated_request = evaluation_input(
            lines,
            evaluation_suffix="LIFECYCLE-WWC-REEVALUATED",
            wwc=updated_finding,
            snapshot_suffix="LIFECYCLE-WWC-REEVALUATED",
            run_suffix="LIFECYCLE-WWC-REEVALUATED",
        )
        updated_id = EvidenceId(
            "SYN-EVIDENCE-LIFECYCLE-WWC-EVENT-REEVALUATED"
        )
        updated_event = DOIWWCEvent(
            event_id=updated_id,
            stream_id=first_history.stream_id,
            order_id=updated_request.snapshot.order_id,
            event_type=WWCEventType.OBSERVED,
            finding=updated_finding,
            corrects_event_id=None,
            recorded_at=CanonicalTimestamp("2026-08-20T14:16:00Z"),
            sequence=2,
            predecessor_binding=first_event.hash_binding(),
            guard=occurrence_guard(
                owner_id=first_history.stream_id,
                event_id=updated_id,
                suffix="LIFECYCLE-WWC-REEVALUATED",
            ),
        )
        tr079 = registries.transition_ref("TR-079")
        updated_occurrence = wwc_event_occurrence_id(updated_event)
        updated_proof = make_wwc_transition_guard_proof(
            transition=tr079,
            stream_id=first_history.stream_id,
            occurrence_id=updated_occurrence,
            prior_history=first_history,
            event=updated_event,
            evaluation_input=updated_request,
        )
        self.assertEqual(
            _reduce_owner_guard_proof(
                transition=tr079,
                stream_id=first_history.stream_id,
                occurrence_id=updated_occurrence,
                proof=updated_proof,
                occurred_at=updated_event.recorded_at,
            ).transition,
            tr079,
        )
        seen.add("TR-079")
        self.assertEqual(
            seen,
            {"TR-074", "TR-075", "TR-076", "TR-077", "TR-078", "TR-079"},
        )
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "WWC_REEVALUATION_PRIOR_REQUIRED",
        ):
            make_wwc_transition_guard_proof(
                transition=tr079,
                stream_id=first_history.stream_id,
                occurrence_id=wwc_event_occurrence_id(first_event),
                prior_history=DOIWWCHistory(
                    stream_id=first_history.stream_id,
                    order_id=first_request.snapshot.order_id,
                ),
                event=first_event,
                evaluation_input=first_request,
            )

    def test_evaluation_owner_reducer_proves_tr027_028_and_every_top_level_route(self) -> None:
        registries = load_doi_registries()
        source = order_source(OrderId("SYN-ORDER-DOI-0001"))
        full_ds = evaluation_input(
            (
                make_line(
                    1,
                    source,
                    drop_ship=DropShipState.DS,
                    availability=LineAvailability.IN_STOCK,
                    quantity_availability=QuantityAvailability.FULL,
                    explicitly_available=2,
                ),
            ),
            evaluation_suffix="LIFECYCLE-TR031",
            snapshot_suffix="LIFECYCLE-TR031",
            run_suffix="LIFECYCLE-TR031",
        )
        payment_only = evaluation_input(
            (make_line(1, source),),
            evaluation_suffix="LIFECYCLE-TR032",
            snapshot_suffix="LIFECYCLE-TR032",
            run_suffix="LIFECYCLE-TR032",
            payment=PaymentCondition.PRESENT,
        )
        mixed_ds = evaluation_input(
            (
                make_line(1, source, drop_ship=DropShipState.DS),
                make_line(2, source),
            ),
            evaluation_suffix="LIFECYCLE-TR033",
            snapshot_suffix="LIFECYCLE-TR033",
            run_suffix="LIFECYCLE-TR033",
        )
        split = evaluation_input(
            split_lines(),
            evaluation_suffix="LIFECYCLE-TR034",
            snapshot_suffix="LIFECYCLE-TR034",
            run_suffix="LIFECYCLE-TR034",
        )
        alternate_base = evaluation_input(
            (make_line(1, source),),
            evaluation_suffix="LIFECYCLE-TR035",
            snapshot_suffix="LIFECYCLE-TR035",
            run_suffix="LIFECYCLE-TR035",
        )
        alternate_context, _ = open_context(
            alternate_base.snapshot,
            "LIFECYCLE-TR035",
        )
        alternate_line = alternate_base.snapshot.lines[0]
        alternate_sku = alternate_line.es_number.value
        self.assertIsInstance(alternate_sku, SkuId)
        alternate_source = SourceRef.create(
            source_ref_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-TR035-PRODUCT-SOURCE"
            ),
            source_kind=SourceKind.SYNTHETIC_PRODUCT_FIXTURE,
            object_namespace=SourceObjectNamespace.SYNTHETIC_PRODUCT,
            object_id=alternate_sku,
        )
        alternate_observation = DOIExactSKUObservation(
            observation_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-TR035-OBSERVATION"
            ),
            action_context_id=alternate_context.action_context_id,
            action_context_binding=alternate_context.hash_binding(),
            ordered_line_id=alternate_line.line_snapshot_id,
            ordered_sku=alternate_sku,
            observed_sku=alternate_sku,
            state=AlternateObservationState.CURRENT,
            observed_availability=AlternateAvailability.IN_STOCK,
            potential_unit_value=None,
            observed_at=OBSERVED_AT,
            source=alternate_source,
        )
        alternate = exact_sku_candidate(
            candidate_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-TR035-CANDIDATE"
            ),
            quantity=PositiveQuantity(1),
            observation=alternate_observation,
        )
        alternate_request = dataclasses.replace(
            alternate_base,
            alternate_candidates=(alternate,),
        )
        progress_review = evaluation_input(
            (
                make_line(
                    1,
                    source,
                    availability=LineAvailability.IN_STOCK,
                    quantity_availability=QuantityAvailability.FULL,
                    explicitly_available=2,
                ),
            ),
            evaluation_suffix="LIFECYCLE-TR036",
            snapshot_suffix="LIFECYCLE-TR036",
            run_suffix="LIFECYCLE-TR036",
        )
        uncertainty = evaluation_input(
            (
                make_line(
                    1,
                    source,
                    availability=unknown_fact("RC-016"),
                ),
            ),
            evaluation_suffix="LIFECYCLE-TR037",
            snapshot_suffix="LIFECYCLE-TR037",
            run_suffix="LIFECYCLE-TR037",
        )
        monitor = evaluation_input(
            (),
            evaluation_suffix="LIFECYCLE-TR038",
            snapshot_suffix="LIFECYCLE-TR038",
            run_suffix="LIFECYCLE-TR038",
        )
        requests = {
            "TR-031": full_ds,
            "TR-032": payment_only,
            "TR-033": mixed_ds,
            "TR-034": split,
            "TR-035": alternate_request,
            "TR-036": progress_review,
            "TR-037": uncertainty,
            "TR-038": monitor,
        }

        for transition_id, request in requests.items():
            with self.subTest(transition=transition_id):
                evaluation = evaluate_doi(request)
                self.assertEqual(evaluation.transition.transition_id, transition_id)
                transition = registries.transition_ref(transition_id)
                stream_id = evaluation_transition_stream_id(evaluation)
                occurrence_id = evaluation_transition_occurrence_id(evaluation)
                proof = make_evaluation_transition_guard_proof(
                    transition=transition,
                    stream_id=stream_id,
                    occurrence_id=occurrence_id,
                    evaluation_input=request,
                    evaluation=evaluation,
                )
                self.assertIs(
                    proof.authority_evidence.evidence_kind,
                    TransitionGuardEvidenceKind.EVALUATION_REDUCTION,
                )
                definition = transition_definition(transition)
                command = make_transition_command(
                    transition=transition,
                    stream_id=stream_id,
                    occurrence_id=occurrence_id,
                    current_state=definition.from_state,
                    expected_sequence=1,
                    expected_predecessor_sha256=None,
                    guard_proof=proof,
                )
                result = reduce_transition(
                    TransitionStream.initial(
                        stream_id=stream_id,
                        state=definition.from_state,
                    ),
                    command,
                    occurred_at=request.evaluated_at,
                )
                self.assertEqual(result.event.transition, transition)

        first_request = evaluation_input(
            (),
            evaluation_suffix="LIFECYCLE-TR027",
            snapshot_suffix="LIFECYCLE-TR027",
            run_suffix="LIFECYCLE-TR027",
        )
        first_evaluation = evaluate_doi(first_request)
        first_proof = make_evaluation_transition_guard_proof(
            transition=registries.transition_ref("TR-027"),
            stream_id=evaluation_transition_stream_id(first_evaluation),
            occurrence_id=evaluation_transition_occurrence_id(first_evaluation),
            evaluation_input=first_request,
            evaluation=first_evaluation,
        )
        self.assertIs(
            first_proof.authority_evidence.evidence_kind,
            TransitionGuardEvidenceKind.EVALUATION_REDUCTION,
        )

        next_request = evaluation_input(
            (make_line(1, source),),
            evaluation_suffix="LIFECYCLE-TR028",
            snapshot_suffix="LIFECYCLE-TR028",
            run_suffix="LIFECYCLE-TR028",
        )
        next_evaluation = evaluate_doi(next_request)
        recheck_proof = make_evaluation_transition_guard_proof(
            transition=registries.transition_ref("TR-028"),
            stream_id=evaluation_transition_stream_id(next_evaluation),
            occurrence_id=evaluation_transition_occurrence_id(next_evaluation),
            evaluation_input=next_request,
            evaluation=next_evaluation,
            prior_evaluation=first_evaluation,
        )
        self.assertIs(
            recheck_proof.authority_evidence.evidence_kind,
            TransitionGuardEvidenceKind.EVALUATION_REDUCTION,
        )

        with self.assertRaisesRegex(
            LifecycleConflictError,
            "EVALUATION_REDUCTION_OWNER_INVALID",
        ):
            make_evaluation_transition_guard_proof(
                transition=registries.transition_ref("TR-038"),
                stream_id=EvidenceId("SYN-EVIDENCE-WRONG-EVALUATION-STREAM"),
                occurrence_id=evaluation_transition_occurrence_id(
                    evaluate_doi(monitor)
                ),
                evaluation_input=monitor,
                evaluation=evaluate_doi(monitor),
            )

    def test_dedupe_and_human_fact_owner_reducers_cover_tr060_064_and_tr096_097(
        self,
    ) -> None:
        registries = load_doi_registries()
        confirmed_request, _ = _dedupe_closure_evidence()
        approved_history = confirmed_request.dedupe_history
        verification = confirmed_request.dedupe_verification
        if approved_history is None or verification is None:
            raise AssertionError("dedupe fixture must retain approval and verification")
        stream_id = approved_history.projection.stream_id
        order_id = approved_history.projection.order_id

        def prefix(length: int) -> DOIDedupeHistory:
            history = DOIDedupeHistory.empty(
                stream_id=stream_id,
                order_id=order_id,
            )
            for retained in approved_history.events[:length]:
                history = reduce_dedupe(history, retained).history
            return history

        observed_history = prefix(1)
        candidate_history = prefix(2)
        candidate_event = approved_history.events[1]
        approval_event = approved_history.events[2]
        seen: set[str] = set()

        def prove_dedupe(
            transition_id: str,
            prior: DOIDedupeHistory,
            event: DOIDedupeEvent,
        ) -> DOIDedupeHistory:
            transition = registries.transition_ref(transition_id)
            proof = make_dedupe_reduction_transition_guard_proof(
                transition=transition,
                stream_id=stream_id,
                occurrence_id=event.event_id,
                prior_history=prior,
                event=event,
            )
            self.assertIs(
                proof.authority_evidence.evidence_kind,
                TransitionGuardEvidenceKind.DEDUPE_REDUCTION,
            )
            self.assertEqual(
                _reduce_owner_guard_proof(
                    transition=transition,
                    stream_id=stream_id,
                    occurrence_id=event.event_id,
                    proof=proof,
                    occurred_at=event.recorded_at,
                ).transition,
                transition,
            )
            seen.add(transition_id)
            return reduce_dedupe(prior, event).history

        prove_dedupe("TR-060", observed_history, candidate_event)
        prove_dedupe("TR-061", candidate_history, approval_event)
        approval_fact = approval_event.human_fact
        if approval_fact is None:
            raise AssertionError("approval event must retain its exact human fact")
        rejection_fact = dataclasses.replace(
            approval_fact,
            fact_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-DEDUPE-INITIAL-REJECTION-FACT"
            ),
            result_code=HumanFactResultCode.REJECTED,
        )
        rejection_id = EvidenceId(
            "SYN-EVIDENCE-LIFECYCLE-DEDUPE-INITIAL-REJECTION"
        )
        rejection_event = DOIDedupeEvent(
            event_id=rejection_id,
            stream_id=stream_id,
            order_id=order_id,
            event_type=DedupeEventType.HUMAN_REJECTED,
            finding=None,
            evaluation=None,
            human_fact=rejection_fact,
            verification=None,
            recorded_at=OBSERVED_AT,
            sequence=3,
            predecessor_binding=candidate_history.events[-1].hash_binding(),
            guard=occurrence_guard(
                owner_id=stream_id,
                event_id=rejection_id,
                suffix="LIFECYCLE-DEDUPE-INITIAL-REJECTION",
            ),
        )
        rejected_history = prove_dedupe(
            "TR-062",
            candidate_history,
            rejection_event,
        )
        corrected_fact = dataclasses.replace(
            approval_fact,
            fact_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-DEDUPE-CORRECTED-REJECTION-FACT"
            ),
            result_code=HumanFactResultCode.REJECTED,
        )
        corrected_id = EvidenceId(
            "SYN-EVIDENCE-LIFECYCLE-DEDUPE-CORRECTED-REJECTION"
        )
        corrected_event = DOIDedupeEvent(
            event_id=corrected_id,
            stream_id=stream_id,
            order_id=order_id,
            event_type=DedupeEventType.HUMAN_REJECTED,
            finding=None,
            evaluation=None,
            human_fact=corrected_fact,
            verification=None,
            recorded_at=OBSERVED_AT,
            sequence=4,
            predecessor_binding=approved_history.events[-1].hash_binding(),
            guard=occurrence_guard(
                owner_id=stream_id,
                event_id=corrected_id,
                suffix="LIFECYCLE-DEDUPE-CORRECTED-REJECTION",
            ),
            corrects_event_id=approval_event.event_id,
            corrected_human_fact_binding=approval_fact.hash_binding(),
        )
        corrected_history = prove_dedupe(
            "TR-062",
            approved_history,
            corrected_event,
        )
        confirmation_id = EvidenceId(
            "SYN-EVIDENCE-LIFECYCLE-DEDUPE-CONFIRMATION"
        )
        confirmation_event = DOIDedupeEvent(
            event_id=confirmation_id,
            stream_id=stream_id,
            order_id=order_id,
            event_type=DedupeEventType.VERIFIED_SOURCE_CONFIRMED,
            finding=None,
            evaluation=None,
            human_fact=None,
            verification=verification,
            recorded_at=verification.verified_snapshot.source_observed_at,
            sequence=4,
            predecessor_binding=approved_history.events[-1].hash_binding(),
            guard=occurrence_guard(
                owner_id=stream_id,
                event_id=confirmation_id,
                suffix="LIFECYCLE-DEDUPE-CONFIRMATION",
            ),
        )
        confirmed_history = prove_dedupe(
            "TR-063",
            approved_history,
            confirmation_event,
        )
        opportunity_evaluation = evaluate_doi(
            evaluation_input(
                split_lines(),
                evaluation_suffix="LIFECYCLE-DEDUPE-OPPORTUNITY",
                alternate_research_state=AlternateResearchState.COMPLETE,
                dedupe_state=DedupeState.SOURCE_PRESENT,
            )
        )
        self.assertEqual(opportunity_evaluation.state.value, "DOI_OPPORTUNITY")
        self.assertIn(
            "RC-059",
            {reason.code for reason in opportunity_evaluation.reasons.reasons},
        )
        eligibility_id = EvidenceId(
            "SYN-EVIDENCE-LIFECYCLE-DEDUPE-ELIGIBILITY-RETURNED"
        )
        eligibility_event = DOIDedupeEvent(
            event_id=eligibility_id,
            stream_id=stream_id,
            order_id=order_id,
            event_type=DedupeEventType.ELIGIBILITY_RETURNED,
            finding=None,
            evaluation=opportunity_evaluation,
            human_fact=None,
            verification=None,
            recorded_at=verification.verified_snapshot.source_observed_at,
            sequence=5,
            predecessor_binding=confirmed_history.events[-1].hash_binding(),
            guard=occurrence_guard(
                owner_id=stream_id,
                event_id=eligibility_id,
                suffix="LIFECYCLE-DEDUPE-ELIGIBILITY-RETURNED",
            ),
        )
        prove_dedupe("TR-064", confirmed_history, eligibility_event)

        recandidate_input = evaluation_input(
            (make_line(1, order_source(OrderId("SYN-ORDER-DOI-0001"))),),
            evaluation_suffix="LIFECYCLE-DEDUPE-RECANDIDATE",
            alternate_research_state=AlternateResearchState.COMPLETE,
            dedupe_state=DedupeState.SOURCE_PRESENT,
        )
        recandidate_evaluation = evaluate_doi(recandidate_input)
        recandidate_id = EvidenceId(
            "SYN-EVIDENCE-LIFECYCLE-DEDUPE-RECANDIDATE"
        )
        recandidate_event = DOIDedupeEvent(
            event_id=recandidate_id,
            stream_id=stream_id,
            order_id=order_id,
            event_type=DedupeEventType.CANDIDATE_IDENTIFIED,
            finding=None,
            evaluation=recandidate_evaluation,
            human_fact=None,
            verification=None,
            recorded_at=OBSERVED_AT,
            sequence=4,
            predecessor_binding=rejected_history.events[-1].hash_binding(),
            guard=occurrence_guard(
                owner_id=stream_id,
                event_id=recandidate_id,
                suffix="LIFECYCLE-DEDUPE-RECANDIDATE",
            ),
        )
        prove_dedupe("TR-060", rejected_history, recandidate_event)

        for index, prior in enumerate(
            (candidate_history, approved_history, corrected_history),
            start=1,
        ):
            withdrawn_id = EvidenceId(
                f"SYN-EVIDENCE-LIFECYCLE-DEDUPE-WITHDRAWN-{index:02d}"
            )
            withdrawn = DOIDedupeEvent(
                event_id=withdrawn_id,
                stream_id=stream_id,
                order_id=order_id,
                event_type=DedupeEventType.CANDIDATE_WITHDRAWN,
                finding=None,
                evaluation=opportunity_evaluation,
                human_fact=None,
                verification=None,
                recorded_at=OBSERVED_AT,
                sequence=len(prior.events) + 1,
                predecessor_binding=prior.events[-1].hash_binding(),
                guard=occurrence_guard(
                    owner_id=stream_id,
                    event_id=withdrawn_id,
                    suffix=f"LIFECYCLE-DEDUPE-WITHDRAWN-{index:02d}",
                ),
            )
            with self.subTest(
                transition="TR-096",
                from_state=prior.projection.state.value,
            ):
                prove_dedupe("TR-096", prior, withdrawn)

        self.assertEqual(
            seen,
            {"TR-060", "TR-061", "TR-062", "TR-063", "TR-064", "TR-096"},
        )

        human_stream = EvidenceId(
            "SYN-EVIDENCE-LIFECYCLE-HUMAN-FACT-STREAM"
        )
        recorded_id = EvidenceId(
            "SYN-EVIDENCE-LIFECYCLE-HUMAN-FACT-RECORDED"
        )
        recorded = DOIHumanFactEvent(
            event_id=recorded_id,
            stream_id=human_stream,
            event_type=HumanFactEventType.RECORDED,
            fact=approval_fact,
            corrects_event_id=None,
            recorded_at=OBSERVED_AT,
            sequence=1,
            predecessor_binding=None,
            guard=occurrence_guard(
                owner_id=human_stream,
                event_id=recorded_id,
                suffix="LIFECYCLE-HUMAN-FACT-RECORDED",
            ),
        )
        human_empty = DOIHumanFactHistory(stream_id=human_stream)

        def prove_human(
            prior: DOIHumanFactHistory,
            event: DOIHumanFactEvent,
        ) -> DOIHumanFactHistory:
            transition = registries.transition_ref("TR-097")
            proof = make_human_fact_reduction_transition_guard_proof(
                transition=transition,
                stream_id=human_stream,
                occurrence_id=event.event_id,
                prior_history=prior,
                event=event,
            )
            self.assertEqual(
                _reduce_owner_guard_proof(
                    transition=transition,
                    stream_id=human_stream,
                    occurrence_id=event.event_id,
                    proof=proof,
                    occurred_at=event.recorded_at,
                ).transition,
                transition,
            )
            return reduce_human_fact(prior, event).history

        recorded_history = prove_human(human_empty, recorded)
        corrected_human_id = EvidenceId(
            "SYN-EVIDENCE-LIFECYCLE-HUMAN-FACT-CORRECTED"
        )
        corrected_human = DOIHumanFactEvent(
            event_id=corrected_human_id,
            stream_id=human_stream,
            event_type=HumanFactEventType.CORRECTED,
            fact=corrected_fact,
            corrects_event_id=recorded.event_id,
            recorded_at=OBSERVED_AT,
            sequence=2,
            predecessor_binding=recorded.hash_binding(),
            guard=occurrence_guard(
                owner_id=human_stream,
                event_id=corrected_human_id,
                suffix="LIFECYCLE-HUMAN-FACT-CORRECTED",
            ),
        )
        prove_human(recorded_history, corrected_human)
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "HUMAN_FACT_REDUCTION_GUARD_NOT_SATISFIED",
        ):
            make_human_fact_reduction_transition_guard_proof(
                transition=registries.transition_ref("TR-097"),
                stream_id=human_stream,
                occurrence_id=corrected_human.event_id,
                prior_history=human_empty,
                event=corrected_human,
            )

    def test_tr013_requires_real_authorized_out_of_scope_fact(self) -> None:
        base = evaluation_input(split_lines(), evaluation_suffix="LIFECYCLE-013")
        out_of_scope = human_fact(
            base,
            usage=HumanFactUsageKind.OUT_OF_SCOPE_CLOSURE,
            result=HumanFactResultCode.OUT_OF_SCOPE,
            suffix="LIFECYCLE-013",
        )
        transition = load_doi_registries().transition_ref("TR-013")
        definition = transition_definition(transition)
        stream_id = EvidenceId("SYN-EVIDENCE-LIFECYCLE-013-CASE")
        occurrence_id = out_of_scope.fact_id
        case = DOIOrderCase(
            case_id=stream_id,
            order_id=out_of_scope.order_id,
            lifecycle_state=CaseLifecycleState.ACTIVE,
            current_snapshot_id=base.snapshot.snapshot_id,
            current_evaluation_id=out_of_scope.evaluation_id,
            terminal_closure_reason=None,
        )
        proof = make_out_of_scope_closure_guard_proof(
            transition=transition,
            stream_id=stream_id,
            occurrence_id=occurrence_id,
            human_fact=out_of_scope,
            case=case,
        )
        self.assertIs(
            proof.authority_evidence.evidence_kind,
            TransitionGuardEvidenceKind.STRUCTURED_HUMAN_FACT,
        )
        command = make_transition_command(
            transition=transition,
            stream_id=stream_id,
            occurrence_id=occurrence_id,
            current_state=definition.from_state,
            expected_sequence=1,
            expected_predecessor_sha256=None,
            guard_proof=proof,
        )
        accepted = reduce_transition(
            TransitionStream.initial(stream_id=stream_id, state=definition.from_state),
            command,
            occurred_at=out_of_scope.occurred_at,
        )
        self.assertEqual(accepted.event.to_state, "CLOSED_REVERSIBLE")
        unrelated = human_fact(
            base,
            usage=HumanFactUsageKind.NO_ACTION_DECISION,
            result=HumanFactResultCode.APPROVED,
            suffix="LIFECYCLE-013-WRONG",
        )
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "OUT_OF_SCOPE_CLOSURE_EVIDENCE_INVALID",
        ):
            make_out_of_scope_closure_guard_proof(
                transition=transition,
                stream_id=stream_id,
                occurrence_id=occurrence_id,
                human_fact=unrelated,
                case=case,
            )

    def test_tr039_requires_authorized_no_action_fact_and_recomputed_evaluation(self) -> None:
        source = order_source(OrderId("SYN-ORDER-DOI-0001"))
        base = evaluation_input(
            (make_line(1, source),),
            evaluation_suffix="LIFECYCLE-039",
        )
        snapshot = dataclasses.replace(
            base.snapshot,
            order_total=unknown_fact("RC-121"),
        )
        without_fact = DOIEvaluationInput(
            evaluation_id=base.evaluation_id,
            snapshot=snapshot,
            evaluated_at=base.evaluated_at,
        )
        fact = human_fact(
            without_fact,
            usage=HumanFactUsageKind.NO_ACTION_DECISION,
            result=HumanFactResultCode.APPROVED,
            suffix="LIFECYCLE-039",
        )
        request = DOIEvaluationInput(
            evaluation_id=base.evaluation_id,
            snapshot=snapshot,
            evaluated_at=base.evaluated_at,
            human_facts=(fact,),
        )
        evaluation = evaluate_doi(request)
        transition = load_doi_registries().transition_ref("TR-039")
        definition = transition_definition(transition)
        stream_id = evaluation_transition_stream_id(evaluation)
        proof = make_human_review_evaluation_guard_proof(
            transition=transition,
            stream_id=stream_id,
            occurrence_id=fact.fact_id,
            evaluation_input=request,
            evaluation=evaluation,
            human_fact=fact,
        )
        command = make_transition_command(
            transition=transition,
            stream_id=stream_id,
            occurrence_id=fact.fact_id,
            current_state=definition.from_state,
            expected_sequence=1,
            expected_predecessor_sha256=None,
            guard_proof=proof,
        )
        result = reduce_transition(
            TransitionStream.initial(stream_id=stream_id, state=definition.from_state),
            command,
            occurred_at=fact.occurred_at,
        )
        self.assertEqual(result.event.transition, transition)
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "HUMAN_REVIEW_EVALUATION_EVIDENCE_INVALID",
        ):
            make_human_review_evaluation_guard_proof(
                transition=transition,
                stream_id=stream_id,
                occurrence_id=EvidenceId("SYN-EVIDENCE-LIFECYCLE-039-WRONG"),
                evaluation_input=request,
                evaluation=evaluation,
                human_fact=fact,
            )

    def test_tr045_requires_completed_human_action_verification_event(self) -> None:
        action = _action(
            verification=ActionVerificationState.HUMAN_VERIFIED,
            event_id="SYN-EVIDENCE-LIFECYCLE-045-EVENT",
            evidence_id="SYN-EVIDENCE-LIFECYCLE-045-EVIDENCE",
            key_id="SYN-EVIDENCE-LIFECYCLE-045-KEY",
            marker="lifecycle-045",
        )
        self.assertIsInstance(action, ActionVerificationEvent)
        transition = load_doi_registries().transition_ref("TR-045")
        definition = transition_definition(transition)
        proof = make_human_action_transition_guard_proof(
            transition=transition,
            stream_id=action.intervention_id,
            occurrence_id=action.event_id,
            action_event=action,
        )
        self.assertIs(
            proof.authority_evidence.evidence_kind,
            TransitionGuardEvidenceKind.HUMAN_ACTION_VERIFICATION,
        )
        command = make_transition_command(
            transition=transition,
            stream_id=action.intervention_id,
            occurrence_id=action.event_id,
            current_state=definition.from_state,
            expected_sequence=1,
            expected_predecessor_sha256=None,
            guard_proof=proof,
        )
        accepted = reduce_transition(
            TransitionStream.initial(
                stream_id=action.intervention_id,
                state=definition.from_state,
            ),
            command,
            occurred_at=action.evidence.material.occurred_at,
        )
        self.assertEqual(accepted.event.to_state, "VERIFIED")
        system_action = _action(
            verification=ActionVerificationState.SYSTEM_VERIFIED,
            event_id="SYN-EVIDENCE-LIFECYCLE-045-SYSTEM-EVENT",
            evidence_id="SYN-EVIDENCE-LIFECYCLE-045-SYSTEM-EVIDENCE",
            key_id="SYN-EVIDENCE-LIFECYCLE-045-SYSTEM-KEY",
            marker="lifecycle-045-system",
        )
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "HUMAN_ACTION_EVIDENCE_INVALID",
        ):
            make_human_action_transition_guard_proof(
                transition=transition,
                stream_id=system_action.intervention_id,
                occurrence_id=system_action.event_id,
                action_event=system_action,
            )

    def test_tr045a_requires_exact_ds_intervention_reduction(self) -> None:
        action = _action(
            event_id="SYN-EVIDENCE-LIFECYCLE-045A-EVENT",
            evidence_id="SYN-EVIDENCE-LIFECYCLE-045A-EVIDENCE",
            key_id="SYN-EVIDENCE-LIFECYCLE-045A-KEY",
            intervention_type=InterventionType.DS_SEPARATION,
            marker="lifecycle-045a",
            intervention_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-045A-INTERVENTION"
            ),
        )
        transition = load_doi_registries().transition_ref("TR-045A")
        proof = make_intervention_transition_guard_proof(
            transition=transition,
            stream_id=action.intervention_id,
            occurrence_id=action.event_id,
            prior_intervention=None,
            action_event=action,
        )
        event = _reduce_owner_guard_proof(
            transition=transition,
            stream_id=action.intervention_id,
            occurrence_id=action.event_id,
            proof=proof,
            occurred_at=action.evidence.material.occurred_at,
        )
        self.assertEqual(event.transition, transition)
        self.assertIs(
            proof.authority_evidence.evidence_kind,
            TransitionGuardEvidenceKind.INTERVENTION_REDUCTION,
        )
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "INTERVENTION_REDUCTION_ROUTE_INVALID",
        ):
            ordinary = _action(marker="lifecycle-045a-wrong")
            make_intervention_transition_guard_proof(
                transition=transition,
                stream_id=ordinary.intervention_id,
                occurrence_id=ordinary.event_id,
                prior_intervention=None,
                action_event=ordinary,
            )

    def test_value_owner_reducer_proves_every_tr046_through_tr053_route(self) -> None:
        base = record_verified_intervention(
            None,
            _action(marker="lifecycle-value-owner"),
        ).intervention
        system_initial = _value_event(
            intervention=base,
            event_id="SYN-EVIDENCE-LIFECYCLE-VALUE-SYSTEM-INITIAL",
            event_type=ValueEventType.INITIAL_VERIFIED_VALUE,
            cents=10_000,
            predecessor=None,
            marker="lifecycle-value-owner",
        )
        human_initial = _value_event(
            intervention=base,
            event_id="SYN-EVIDENCE-LIFECYCLE-VALUE-HUMAN-INITIAL",
            event_type=ValueEventType.INITIAL_VERIFIED_VALUE,
            cents=10_000,
            predecessor=None,
            verification=ValueVerificationState.HUMAN_VERIFIED,
        )
        verified = append_value_event(base, system_initial).intervention
        original_correction = _value_event(
            intervention=verified,
            event_id="SYN-EVIDENCE-LIFECYCLE-VALUE-ORIGINAL-CORRECTION",
            event_type=ValueEventType.CORRECTION,
            cents=9_000,
            predecessor=system_initial,
            correction_kind=ValueCorrectionKind.ORIGINAL_VALUE_CORRECTED,
            marker="lifecycle-value-owner",
        )
        zero_reversal_sum = _value_event(
            intervention=verified,
            event_id="SYN-EVIDENCE-LIFECYCLE-VALUE-ZERO-REVERSAL",
            event_type=ValueEventType.CORRECTION,
            cents=9_500,
            predecessor=system_initial,
            correction_kind=ValueCorrectionKind.ORIGINAL_VALUE_CORRECTED,
            marker="lifecycle-value-owner",
        )
        partial = _value_event(
            intervention=verified,
            event_id="SYN-EVIDENCE-LIFECYCLE-VALUE-PARTIAL",
            event_type=ValueEventType.PARTIAL_REVERSAL,
            cents=3_000,
            predecessor=system_initial,
            marker="lifecycle-value-owner",
        )
        full = _value_event(
            intervention=verified,
            event_id="SYN-EVIDENCE-LIFECYCLE-VALUE-FULL",
            event_type=ValueEventType.FULL_REVERSAL,
            cents=10_000,
            predecessor=system_initial,
            marker="lifecycle-value-owner",
        )
        partial_projection = append_value_event(verified, partial).intervention
        reversal_void = _value_event(
            intervention=partial_projection,
            event_id="SYN-EVIDENCE-LIFECYCLE-VALUE-REVERSAL-VOID",
            event_type=ValueEventType.CORRECTION,
            cents=0,
            predecessor=partial,
            correction_kind=ValueCorrectionKind.REVERSAL_VOIDED,
            marker="lifecycle-value-owner",
        )
        second_original_correction = _value_event(
            intervention=verified,
            event_id="SYN-EVIDENCE-LIFECYCLE-VALUE-ORIGINAL-CORRECTION-2",
            event_type=ValueEventType.CORRECTION,
            cents=8_500,
            predecessor=system_initial,
            correction_kind=ValueCorrectionKind.ORIGINAL_VALUE_CORRECTED,
            marker="lifecycle-value-owner",
        )
        cases = (
            ("TR-046", base, system_initial),
            ("TR-047", base, human_initial),
            ("TR-048", verified, original_correction),
            ("TR-049", verified, zero_reversal_sum),
            ("TR-050", verified, partial),
            ("TR-051", verified, full),
            ("TR-052", partial_projection, reversal_void),
            ("TR-053", verified, second_original_correction),
        )
        registries = load_doi_registries()
        for transition_id, prior, event in cases:
            with self.subTest(transition=transition_id):
                transition = registries.transition_ref(transition_id)
                definition = transition_definition(transition)
                proof = make_value_reduction_transition_guard_proof(
                    transition=transition,
                    stream_id=prior.intervention_id,
                    occurrence_id=event.event_id,
                    prior_intervention=prior,
                    value_event=event,
                )
                command = make_transition_command(
                    transition=transition,
                    stream_id=prior.intervention_id,
                    occurrence_id=event.event_id,
                    current_state=definition.from_state,
                    expected_sequence=1,
                    expected_predecessor_sha256=None,
                    guard_proof=proof,
                )
                result = reduce_transition(
                    TransitionStream.initial(
                        stream_id=prior.intervention_id,
                        state=definition.from_state,
                    ),
                    command,
                    occurred_at=event.occurred_at,
                )
                self.assertEqual(result.event.transition, transition)

    def test_resulting_link_owner_reducer_proves_all_link_routes(self) -> None:
        marker = "lifecycle-resulting-link"
        intervention = record_verified_intervention(
            None,
            _action(marker=marker),
        ).intervention
        original_mappings = _mapping(intervention=intervention, marker=marker)
        changed_mappings = _mapping(
            intervention=intervention,
            quantity=2,
            marker=marker,
        )
        auto_evidence = _revision(
            revision_id="SYN-EVIDENCE-LIFECYCLE-LINK-101",
            mappings=original_mappings,
            predecessor=None,
            intervention=intervention,
            marker=marker,
        )
        auto = append_resulting_link_revision(
            None,
            revision_id=EvidenceId("SYN-EVIDENCE-LIFECYCLE-LINK-101"),
            intervention=intervention,
            evidence=auto_evidence,
        ).link
        human_evidence = _revision(
            revision_id="SYN-EVIDENCE-LIFECYCLE-LINK-102",
            mappings=original_mappings,
            predecessor=None,
            intervention=intervention,
            human=True,
            marker=marker,
        )
        human = append_resulting_link_revision(
            None,
            revision_id=EvidenceId("SYN-EVIDENCE-LIFECYCLE-LINK-102"),
            intervention=intervention,
            evidence=human_evidence,
        ).link
        auto_conflict_evidence = _revision(
            revision_id="SYN-EVIDENCE-LIFECYCLE-LINK-103",
            mappings=changed_mappings,
            predecessor=auto.revisions[-1],
            intervention=intervention,
            marker=marker,
        )
        auto_conflict = append_resulting_link_revision(
            auto,
            revision_id=EvidenceId("SYN-EVIDENCE-LIFECYCLE-LINK-103"),
            intervention=intervention,
            evidence=auto_conflict_evidence,
        ).link
        system_resolution = _revision(
            revision_id="SYN-EVIDENCE-LIFECYCLE-LINK-104",
            mappings=original_mappings,
            predecessor=auto_conflict.revisions[-1],
            intervention=intervention,
            resolves_conflict=auto_conflict.revisions[-1],
            marker=marker,
        )
        human_resolution = _revision(
            revision_id="SYN-EVIDENCE-LIFECYCLE-LINK-105",
            mappings=changed_mappings,
            predecessor=auto_conflict.revisions[-1],
            intervention=intervention,
            resolves_conflict=auto_conflict.revisions[-1],
            human=True,
            marker=marker,
        )
        human_conflict_evidence = _revision(
            revision_id="SYN-EVIDENCE-LIFECYCLE-LINK-106",
            mappings=changed_mappings,
            predecessor=human.revisions[-1],
            intervention=intervention,
            marker=marker,
        )
        auto_corroboration = _revision(
            revision_id="SYN-EVIDENCE-LIFECYCLE-LINK-107",
            mappings=original_mappings,
            predecessor=auto.revisions[-1],
            intervention=intervention,
            marker=marker,
        )
        human_corroboration = _revision(
            revision_id="SYN-EVIDENCE-LIFECYCLE-LINK-108",
            mappings=original_mappings,
            predecessor=human.revisions[-1],
            intervention=intervention,
            human=True,
            marker=marker,
        )
        system_agreement = _revision(
            revision_id="SYN-EVIDENCE-LIFECYCLE-LINK-109",
            mappings=original_mappings,
            predecessor=human.revisions[-1],
            intervention=intervention,
            marker=marker,
        )
        cases = (
            ("TR-054", None, auto_evidence, "101"),
            ("TR-055", None, human_evidence, "102"),
            ("TR-056", auto_conflict, system_resolution, "104"),
            ("TR-057", auto_conflict, human_resolution, "105"),
            ("TR-058", auto, auto_conflict_evidence, "103"),
            ("TR-059", human, human_conflict_evidence, "106"),
            ("TR-090", auto, auto_corroboration, "107"),
            ("TR-090", human, human_corroboration, "108"),
            ("TR-091", human, system_agreement, "109"),
            ("TR-110", None, auto_evidence, "101"),
            ("TR-111", auto, auto_conflict_evidence, "103"),
        )
        registries = load_doi_registries()
        for transition_id, prior, evidence, suffix in cases:
            with self.subTest(transition=transition_id, suffix=suffix):
                transition = registries.transition_ref(transition_id)
                occurrence_id = EvidenceId(
                    f"SYN-EVIDENCE-LIFECYCLE-LINK-{suffix}"
                )
                proof = make_resulting_link_transition_guard_proof(
                    transition=transition,
                    stream_id=LINK_ID,
                    occurrence_id=occurrence_id,
                    prior_link=prior,
                    intervention=intervention,
                    evidence=evidence,
                )
                event = _reduce_owner_guard_proof(
                    transition=transition,
                    stream_id=LINK_ID,
                    occurrence_id=occurrence_id,
                    proof=proof,
                    occurred_at=evidence.observed_at,
                )
                self.assertEqual(event.transition, transition)
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "RESULTING_LINK_REDUCTION_ROUTE_INVALID",
        ):
            make_resulting_link_transition_guard_proof(
                transition=registries.transition_ref("TR-091"),
                stream_id=LINK_ID,
                occurrence_id=EvidenceId("SYN-EVIDENCE-LIFECYCLE-LINK-108"),
                prior_link=human,
                intervention=intervention,
                evidence=human_corroboration,
            )

    def test_resulting_link_search_owner_reducer_proves_tr088_and_tr089(self) -> None:
        parent = DoiOrderId(OrderId("SYN-ORDER-DOI-0001"))
        candidate_2 = DoiOrderId(OrderId("SYN-ORDER-CHILD-002"))
        history = DOIResultingOrderLinkSearchHistory(
            search_id=EvidenceId("SYN-EVIDENCE-LIFECYCLE-LINK-SEARCH"),
            parent_order_id=parent,
            intervention_type=InterventionType.PRODUCT_SUBSTITUTION,
        )

        def search_evidence(
            suffix: str,
            candidates: tuple[DoiOrderId, ...],
            disproved: tuple[DoiOrderId, ...] = (),
        ) -> ResultingLinkSearchEvidence:
            return ResultingLinkSearchEvidence.from_complete_search(
                evidence_id=EvidenceId(
                    f"SYN-EVIDENCE-LIFECYCLE-SEARCH-EVIDENCE-{suffix}"
                ),
                search_id=history.search_id,
                parent_order_id=parent,
                intervention_type=InterventionType.PRODUCT_SUBSTITUTION,
                candidate_order_ids=candidates,
                disproved_candidate_order_ids=disproved,
                observed_at=OBSERVED_AT,
                source=SourceRef.create(
                    source_ref_id=EvidenceId(
                        f"SYN-EVIDENCE-LIFECYCLE-SEARCH-SOURCE-{suffix}"
                    ),
                    source_kind=SourceKind.SYNTHETIC_ORDER_FIXTURE,
                    object_namespace=SourceObjectNamespace.SYNTHETIC_ORDER,
                    object_id=parent.value,
                ),
            )

        ambiguous_evidence = search_evidence(
            "AMBIGUOUS",
            tuple(sorted((CHILD, candidate_2), key=lambda item: item.to_json_value())),
        )
        ambiguous_id = EvidenceId("SYN-EVIDENCE-LIFECYCLE-SEARCH-AMBIGUOUS")
        ambiguous = append_resulting_link_search(
            history,
            event_id=ambiguous_id,
            evidence=ambiguous_evidence,
        )
        assert ambiguous.history.projection is not None
        not_found_evidence = search_evidence(
            "NOT-FOUND",
            (),
            ambiguous.history.projection.candidate_order_ids,
        )
        cases = (
            ("TR-089", history, ambiguous_id, ambiguous_evidence),
            (
                "TR-088",
                ambiguous.history,
                EvidenceId("SYN-EVIDENCE-LIFECYCLE-SEARCH-NOT-FOUND"),
                not_found_evidence,
            ),
        )
        registries = load_doi_registries()
        for transition_id, prior, occurrence_id, evidence in cases:
            with self.subTest(transition=transition_id):
                transition = registries.transition_ref(transition_id)
                proof = make_resulting_link_search_transition_guard_proof(
                    transition=transition,
                    stream_id=history.search_id,
                    occurrence_id=occurrence_id,
                    prior_history=prior,
                    evidence=evidence,
                )
                event = _reduce_owner_guard_proof(
                    transition=transition,
                    stream_id=history.search_id,
                    occurrence_id=occurrence_id,
                    proof=proof,
                    occurred_at=evidence.observed_at,
                )
                self.assertEqual(event.transition, transition)

    def test_kpi_owner_reducer_proves_tr106_through_tr109(self) -> None:
        registries = load_doi_registries()
        ds = _kpi_intervention(
            InterventionType.DS_SEPARATION,
            verified_cents=None,
            suffix="LIFECYCLE-KPI-DS",
        )
        ds_history = KPIContributionHistory(
            intervention_id=ds.intervention_id,
            intervention_type=ds.intervention_type,
        )
        tr106_occurrence = ds.action_events[0].event_id
        tr106 = registries.transition_ref("TR-106")
        tr106_proof = make_kpi_contribution_transition_guard_proof(
            transition=tr106,
            stream_id=ds.intervention_id,
            occurrence_id=tr106_occurrence,
            prior_history=ds_history,
            prior_interventions=(),
            prior_resulting_links=(),
            prior_currency_evidence=(),
            intervention=ds,
            resulting_link=None,
        )
        self.assertEqual(
            _reduce_owner_guard_proof(
                transition=tr106,
                stream_id=ds.intervention_id,
                occurrence_id=tr106_occurrence,
                proof=tr106_proof,
                occurred_at=ds.action_occurred_at,
            ).transition,
            tr106,
        )
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "KPI_CONTRIBUTION_REDUCTION_OCCURRENCE_INVALID",
        ) as wrong_occurrence:
            make_kpi_contribution_transition_guard_proof(
                transition=tr106,
                stream_id=ds.intervention_id,
                occurrence_id=EvidenceId(
                    "SYN-EVIDENCE-LIFECYCLE-KPI-DS-ARBITRARY"
                ),
                prior_history=ds_history,
                prior_interventions=(),
                prior_resulting_links=(),
                prior_currency_evidence=(),
                intervention=ds,
                resulting_link=None,
            )
        self.assertEqual(wrong_occurrence.exception.reason.code, "RC-081")

        no_date = _kpi_intervention(
            InterventionType.PRODUCT_SUBSTITUTION,
            verified_cents=None,
            action_at=None,
            suffix="LIFECYCLE-KPI-NO-DATE",
        )
        no_date_link = _kpi_link(
            no_date,
            order_rep_verified=False,
            line_rep_verified=True,
            suffix="LIFECYCLE-KPI-NO-DATE",
        )
        no_date_currency = _kpi_currency_envelope(
            no_date,
            suffix="LIFECYCLE-KPI-NO-DATE",
        )
        no_date_occurrence = no_date.action_events[0].event_id
        no_date_proof = make_kpi_contribution_transition_guard_proof(
            transition=tr106,
            stream_id=no_date.intervention_id,
            occurrence_id=no_date_occurrence,
            prior_history=KPIContributionHistory(
                intervention_id=no_date.intervention_id,
                intervention_type=no_date.intervention_type,
            ),
            prior_interventions=(),
            prior_resulting_links=(),
            prior_currency_evidence=(),
            intervention=no_date,
            resulting_link=no_date_link,
            currency_evidence=no_date_currency,
        )
        self.assertEqual(
            _reduce_owner_guard_proof(
                transition=tr106,
                stream_id=no_date.intervention_id,
                occurrence_id=no_date_occurrence,
                proof=no_date_proof,
                occurred_at=no_date_currency.observed_at,
            ).transition,
            tr106,
        )

        suffix = "LIFECYCLE-KPI"
        original = _kpi_intervention(
            InterventionType.PRODUCT_SUBSTITUTION,
            verified_cents=10_000,
            suffix=suffix,
        )
        link = _kpi_link(
            original,
            order_rep_verified=False,
            line_rep_verified=True,
            suffix=suffix,
        )
        empty = KPIContributionHistory(
            intervention_id=original.intervention_id,
            intervention_type=original.intervention_type,
        )
        original_occurrence = EvidenceId("SYN-EVIDENCE-LIFECYCLE-KPI-ORIGINAL")
        first = reduce_kpi_contribution(
            empty,
            event_id=original_occurrence,
            intervention=original,
            resulting_link=link,
        )
        assert first.history is not None
        value_original = original.value_events[-1]
        correction = _value_event(
            intervention=original,
            event_id="SYN-EVIDENCE-LIFECYCLE-KPI-CORRECTION-VALUE",
            event_type=ValueEventType.CORRECTION,
            cents=9_000,
            predecessor=value_original,
            correction_kind=ValueCorrectionKind.ORIGINAL_VALUE_CORRECTED,
            marker=suffix,
        )
        corrected = append_value_event(original, correction).intervention
        correction_occurrence = EvidenceId(
            "SYN-EVIDENCE-LIFECYCLE-KPI-CORRECTION"
        )
        second = reduce_kpi_contribution(
            first.history,
            event_id=correction_occurrence,
            intervention=corrected,
            resulting_link=link,
        )
        assert second.history is not None
        reversal = _value_event(
            intervention=corrected,
            event_id="SYN-EVIDENCE-LIFECYCLE-KPI-REVERSAL-VALUE",
            event_type=ValueEventType.PARTIAL_REVERSAL,
            cents=2_000,
            predecessor=correction,
            marker=suffix,
        )
        reversed_intervention = append_value_event(
            corrected,
            reversal,
        ).intervention
        reversal_occurrence = EvidenceId(
            "SYN-EVIDENCE-LIFECYCLE-KPI-REVERSAL"
        )
        cases = (
            (
                "TR-107",
                empty,
                (),
                (),
                (),
                original,
                original_occurrence,
            ),
            (
                "TR-108",
                first.history,
                (original,),
                (link,),
                (None,),
                corrected,
                correction_occurrence,
            ),
            (
                "TR-109",
                second.history,
                (original, corrected),
                (link, link),
                (None, None),
                reversed_intervention,
                reversal_occurrence,
            ),
        )
        for (
            transition_id,
            prior,
            snapshots,
            links,
            envelopes,
            current,
            occurrence_id,
        ) in cases:
            with self.subTest(transition=transition_id):
                transition = registries.transition_ref(transition_id)
                proof = make_kpi_contribution_transition_guard_proof(
                    transition=transition,
                    stream_id=current.intervention_id,
                    occurrence_id=occurrence_id,
                    prior_history=prior,
                    prior_interventions=snapshots,
                    prior_resulting_links=links,
                    prior_currency_evidence=envelopes,
                    intervention=current,
                    resulting_link=link,
                )
                event = _reduce_owner_guard_proof(
                    transition=transition,
                    stream_id=current.intervention_id,
                    occurrence_id=occurrence_id,
                    proof=proof,
                    occurred_at=current.action_occurred_at,
                )
                self.assertEqual(event.transition, transition)

    def test_complete_evaluation_is_required_for_closure_guard(self) -> None:
        request = evaluation_input(
            split_lines(),
            evaluation_suffix="LIFECYCLE-CLOSURE",
            order_state=OrderState.SHIPPED,
        )
        evaluation = evaluate_doi(request)
        transition = load_doi_registries().transition_ref("TR-009")
        definition = transition_definition(transition)
        stream_id = EvidenceId("SYN-EVIDENCE-LIFECYCLE-CLOSURE-CASE")
        occurrence_id = evaluation_transition_occurrence_id(evaluation)
        case = DOIOrderCase(
            case_id=stream_id,
            order_id=evaluation.order_id,
            lifecycle_state=CaseLifecycleState.ACTIVE,
            current_snapshot_id=evaluation.snapshot_id,
            current_evaluation_id=evaluation.evaluation_id,
            terminal_closure_reason=None,
        )
        proof = make_closure_transition_guard_proof(
            transition=transition,
            stream_id=stream_id,
            occurrence_id=occurrence_id,
            evaluation_input=request,
            evaluation=evaluation,
            case=case,
        )
        command = make_transition_command(
            transition=transition,
            stream_id=stream_id,
            occurrence_id=occurrence_id,
            current_state=definition.from_state,
            expected_sequence=1,
            expected_predecessor_sha256=None,
            guard_proof=proof,
        )
        accepted = reduce_transition(
            TransitionStream.initial(stream_id=stream_id, state=definition.from_state),
            command,
            occurred_at=request.evaluated_at,
        )
        self.assertEqual(accepted.event.to_state, "CLOSED_HARD")
        canceled_request = evaluation_input(
            split_lines(),
            evaluation_suffix="LIFECYCLE-CLOSURE-CANCELED",
            order_state=OrderState.CANCELED,
        )
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "CLOSURE_EVALUATION_EVIDENCE_INVALID",
        ):
            make_closure_transition_guard_proof(
                transition=transition,
                stream_id=stream_id,
                occurrence_id=occurrence_id,
                evaluation_input=canceled_request,
                evaluation=evaluate_doi(canceled_request),
                case=case,
            )

    def test_tr014_and_tr015_require_exact_case_recheck_and_retention(self) -> None:
        reopen_request = evaluation_input(
            split_lines(),
            evaluation_suffix="LIFECYCLE-014",
        )
        same_closure_request = evaluation_input(
            split_lines(),
            evaluation_suffix="LIFECYCLE-015",
            rep_relation="OTHER_REP",
        )
        cases = (
            ("TR-014", reopen_request, True),
            ("TR-015", same_closure_request, False),
        )
        registries = load_doi_registries()
        for transition_id, request, reopening in cases:
            with self.subTest(transition=transition_id):
                evaluation = evaluate_doi(request)
                case_id = EvidenceId(
                    f"SYN-EVIDENCE-LIFECYCLE-CASE-RECHECK-{transition_id}"
                )
                retention = schedule_retention(
                    case_id=case_id,
                    closure_event_id=EvidenceId(
                        f"SYN-EVIDENCE-LIFECYCLE-PRIOR-CLOSURE-{transition_id}"
                    ),
                    lifecycle_state=CaseLifecycleState.CLOSED_REVERSIBLE,
                    closure_reason=TerminalClosureReason.REP_TRANSFERRED,
                    closed_at=CanonicalTimestamp("2026-05-20T12:00:00Z"),
                    projection_revision=1,
                    projection_sha256="d" * 64,
                )
                case = DOIOrderCase(
                    case_id=case_id,
                    order_id=evaluation.order_id,
                    lifecycle_state=CaseLifecycleState.CLOSED_REVERSIBLE,
                    current_snapshot_id=evaluation.snapshot_id,
                    current_evaluation_id=evaluation.evaluation_id,
                    terminal_closure_reason=TerminalClosureReason.REP_TRANSFERRED,
                )
                transition = registries.transition_ref(transition_id)
                definition = transition_definition(transition)
                occurrence_id = evaluation_transition_occurrence_id(evaluation)
                proof = make_case_recheck_transition_guard_proof(
                    transition=transition,
                    stream_id=case_id,
                    occurrence_id=occurrence_id,
                    case=case,
                    retention=retention,
                    evaluation_input=request,
                    evaluation=evaluation,
                    supplied_prior_binding=(
                        retention.binding if reopening else None
                    ),
                )
                command = make_transition_command(
                    transition=transition,
                    stream_id=case_id,
                    occurrence_id=occurrence_id,
                    current_state=definition.from_state,
                    expected_sequence=1,
                    expected_predecessor_sha256=None,
                    guard_proof=proof,
                )
                result = reduce_transition(
                    TransitionStream.initial(
                        stream_id=case_id,
                        state=definition.from_state,
                    ),
                    command,
                    occurred_at=request.evaluated_at,
                )
                self.assertEqual(result.event.transition, transition)
                if reopening:
                    with self.assertRaisesRegex(
                        LifecycleConflictError,
                        "CASE_REOPEN_RETENTION_INVALID",
                    ):
                        make_case_recheck_transition_guard_proof(
                            transition=transition,
                            stream_id=case_id,
                            occurrence_id=occurrence_id,
                            case=case,
                            retention=retention,
                            evaluation_input=request,
                            evaluation=evaluation,
                            supplied_prior_binding=dataclasses.replace(
                                retention.binding,
                                projection_sha256="e" * 64,
                            ),
                        )

    def test_every_protected_closure_route_has_real_complete_evaluation(self) -> None:
        shipped_request = evaluation_input(
            split_lines(),
            evaluation_suffix="LIFECYCLE-CLOSURE-SHIPPED",
            order_state=OrderState.SHIPPED,
        )
        canceled_request = evaluation_input(
            split_lines(),
            evaluation_suffix="LIFECYCLE-CLOSURE-CANCELED-ALL",
            order_state=OrderState.CANCELED,
        )
        transfer_request = evaluation_input(
            split_lines(),
            evaluation_suffix="LIFECYCLE-CLOSURE-TRANSFER",
            rep_relation="OTHER_REP",
        )
        dedupe_request, dedupe_evaluation = _dedupe_closure_evidence()
        evidence_by_transition = {
            "TR-009": (shipped_request, evaluate_doi(shipped_request)),
            "TR-010": (canceled_request, evaluate_doi(canceled_request)),
            "TR-011": (transfer_request, evaluate_doi(transfer_request)),
            "TR-012": (dedupe_request, dedupe_evaluation),
            "TR-016": (shipped_request, evaluate_doi(shipped_request)),
            "TR-017": (canceled_request, evaluate_doi(canceled_request)),
            "TR-029": (shipped_request, evaluate_doi(shipped_request)),
            "TR-030": (transfer_request, evaluate_doi(transfer_request)),
        }
        registries = load_doi_registries()
        for transition_id, (request, evaluation) in evidence_by_transition.items():
            with self.subTest(transition=transition_id):
                transition = registries.transition_ref(transition_id)
                definition = transition_definition(transition)
                case = None
                if transition_id in {
                    "TR-009",
                    "TR-010",
                    "TR-011",
                    "TR-012",
                    "TR-016",
                    "TR-017",
                }:
                    stream_id = EvidenceId(
                        f"SYN-EVIDENCE-CLOSURE-OWNER-STREAM-{transition_id}"
                    )
                    case_state = (
                        CaseLifecycleState.ACTIVE
                        if transition_id
                        in {"TR-009", "TR-010", "TR-011", "TR-012"}
                        else CaseLifecycleState.CLOSED_REVERSIBLE
                    )
                    case = DOIOrderCase(
                        case_id=stream_id,
                        order_id=evaluation.order_id,
                        lifecycle_state=case_state,
                        current_snapshot_id=evaluation.snapshot_id,
                        current_evaluation_id=evaluation.evaluation_id,
                        terminal_closure_reason=(
                            None
                            if case_state is CaseLifecycleState.ACTIVE
                            else TerminalClosureReason.REP_TRANSFERRED
                        ),
                    )
                    occurrence_id = evaluation_transition_occurrence_id(evaluation)
                elif transition_id in {"TR-029", "TR-030"}:
                    stream_id = evaluation_transition_stream_id(evaluation)
                    occurrence_id = evaluation_transition_occurrence_id(evaluation)
                else:
                    raise AssertionError("closure owner route must be explicit")
                proof = make_closure_transition_guard_proof(
                    transition=transition,
                    stream_id=stream_id,
                    occurrence_id=occurrence_id,
                    evaluation_input=request,
                    evaluation=evaluation,
                    case=case,
                )
                command = make_transition_command(
                    transition=transition,
                    stream_id=stream_id,
                    occurrence_id=occurrence_id,
                    current_state=definition.from_state,
                    expected_sequence=1,
                    expected_predecessor_sha256=None,
                    guard_proof=proof,
                )
                result = reduce_transition(
                    TransitionStream.initial(
                        stream_id=stream_id,
                        state=definition.from_state,
                    ),
                    command,
                    occurred_at=request.evaluated_at,
                )
                self.assertEqual(result.event.transition, transition)

    def test_closure_owner_evidence_rejects_cross_stream_order_and_occurrence(self) -> None:
        request = evaluation_input(
            split_lines(),
            evaluation_suffix="LIFECYCLE-CLOSURE-OWNER-NEGATIVE",
            order_state=OrderState.SHIPPED,
        )
        evaluation = evaluate_doi(request)
        transition = load_doi_registries().transition_ref("TR-009")
        stream_id = EvidenceId("SYN-EVIDENCE-LIFECYCLE-CLOSURE-BOUND-CASE")
        occurrence_id = evaluation_transition_occurrence_id(evaluation)
        case = DOIOrderCase(
            case_id=stream_id,
            order_id=evaluation.order_id,
            lifecycle_state=CaseLifecycleState.ACTIVE,
            current_snapshot_id=evaluation.snapshot_id,
            current_evaluation_id=evaluation.evaluation_id,
            terminal_closure_reason=None,
        )
        invalid_cases = (
            (
                EvidenceId("SYN-EVIDENCE-LIFECYCLE-CLOSURE-OTHER-CASE"),
                occurrence_id,
                case,
            ),
            (
                stream_id,
                EvidenceId("SYN-EVIDENCE-LIFECYCLE-CLOSURE-OTHER-EVENT"),
                case,
            ),
            (
                stream_id,
                occurrence_id,
                DOIOrderCase(
                    case_id=stream_id,
                    order_id=DoiOrderId(OrderId("SYN-ORDER-CLOSURE-OTHER")),
                    lifecycle_state=CaseLifecycleState.ACTIVE,
                    current_snapshot_id=evaluation.snapshot_id,
                    current_evaluation_id=evaluation.evaluation_id,
                    terminal_closure_reason=None,
                ),
            ),
        )
        for supplied_stream, supplied_occurrence, supplied_case in invalid_cases:
            with self.subTest(
                stream=supplied_stream,
                occurrence=supplied_occurrence,
                case_order=supplied_case.order_id,
            ), self.assertRaisesRegex(
                LifecycleConflictError,
                "CLOSURE_CASE_OWNER_BINDING_INVALID",
            ):
                make_closure_transition_guard_proof(
                    transition=transition,
                    stream_id=supplied_stream,
                    occurrence_id=supplied_occurrence,
                    evaluation_input=request,
                    evaluation=evaluation,
                    case=supplied_case,
                )

        top_level = load_doi_registries().transition_ref("TR-029")
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "CLOSURE_EVALUATION_OWNER_BINDING_INVALID",
        ):
            make_closure_transition_guard_proof(
                transition=top_level,
                stream_id=stream_id,
                occurrence_id=evaluation_transition_occurrence_id(evaluation),
                evaluation_input=request,
                evaluation=evaluation,
            )


    def test_tr112_recomputes_purge_eligibility_and_reconciliation(self) -> None:
        case_id = EvidenceId("SYN-EVIDENCE-LIFECYCLE-112-CASE")
        graph = DOICaseGraph(
            case_id=case_id,
            order_id=DoiOrderId(OrderId("SYN-ORDER-LIFECYCLE-112")),
            identity_nodes=(),
            retention=schedule_retention(
                case_id=case_id,
                closure_event_id=EvidenceId("SYN-EVIDENCE-LIFECYCLE-112-CLOSURE"),
                lifecycle_state=CaseLifecycleState.CLOSED_REVERSIBLE,
                closure_reason=TerminalClosureReason.REP_TRANSFERRED,
                closed_at=CanonicalTimestamp("2026-05-22T12:00:00Z"),
                projection_revision=1,
                projection_sha256="a" * 64,
            ),
            contribution=None,
        )
        now = graph.retention.purge_eligible_at
        self.assertIsNotNone(now)
        transition = load_doi_registries().transition_ref("TR-112")
        definition = transition_definition(transition)
        occurrence_id = case_purge_occurrence_id(transition, graph)
        proof = make_case_purge_transition_guard_proof(
            transition=transition,
            stream_id=case_id,
            occurrence_id=occurrence_id,
            graph=graph,
            now=now,
            existing_bucket=None,
            expected_contribution=None,
        )
        self.assertIs(
            proof.authority_evidence.evidence_kind,
            TransitionGuardEvidenceKind.CASE_PURGE_RECONCILIATION,
        )
        command = make_transition_command(
            transition=transition,
            stream_id=case_id,
            occurrence_id=occurrence_id,
            current_state=definition.from_state,
            expected_sequence=1,
            expected_predecessor_sha256=None,
            guard_proof=proof,
        )
        accepted = reduce_transition(
            TransitionStream.initial(stream_id=case_id, state=definition.from_state),
            command,
            occurred_at=now,
        )
        self.assertEqual(accepted.event.to_state, definition.to_state)
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "CASE_PURGE_GUARD_NOT_SATISFIED",
        ) as premature:
            make_case_purge_transition_guard_proof(
                transition=transition,
                stream_id=case_id,
                occurrence_id=occurrence_id,
                graph=graph,
                now=CanonicalTimestamp("2026-05-23T12:00:00Z"),
                existing_bucket=None,
                expected_contribution=None,
            )
        self.assertEqual(premature.exception.reason.code, "RC-081")

    def test_tr018_tr019_and_tr112_share_real_case_purge_oracle(self) -> None:
        registries = load_doi_registries()
        cases = (
            (
                "TR-018",
                CaseLifecycleState.CLOSED_HARD,
                TerminalClosureReason.SHIPPED,
            ),
            (
                "TR-019",
                CaseLifecycleState.CLOSED_REVERSIBLE,
                TerminalClosureReason.REP_TRANSFERRED,
            ),
            (
                "TR-112",
                CaseLifecycleState.CLOSED_REVERSIBLE,
                TerminalClosureReason.REP_TRANSFERRED,
            ),
        )
        for transition_id, lifecycle_state, closure_reason in cases:
            with self.subTest(transition=transition_id):
                case_id = EvidenceId(
                    f"SYN-EVIDENCE-LIFECYCLE-PURGE-CASE-{transition_id}"
                )
                graph = DOICaseGraph(
                    case_id=case_id,
                    order_id=DoiOrderId(
                        OrderId(f"SYN-ORDER-LIFECYCLE-PURGE-{transition_id}")
                    ),
                    identity_nodes=(),
                    retention=schedule_retention(
                        case_id=case_id,
                        closure_event_id=EvidenceId(
                            f"SYN-EVIDENCE-LIFECYCLE-CLOSURE-{transition_id}"
                        ),
                        lifecycle_state=lifecycle_state,
                        closure_reason=closure_reason,
                        closed_at=CanonicalTimestamp("2026-05-22T12:00:00Z"),
                        projection_revision=1,
                        projection_sha256="b" * 64,
                    ),
                    contribution=None,
                )
                due = graph.retention.purge_eligible_at
                self.assertIsNotNone(due)
                transition = registries.transition_ref(transition_id)
                definition = transition_definition(transition)
                occurrence_id = case_purge_occurrence_id(transition, graph)
                proof = make_case_purge_transition_guard_proof(
                    transition=transition,
                    stream_id=case_id,
                    occurrence_id=occurrence_id,
                    graph=graph,
                    now=due,
                    existing_bucket=None,
                    expected_contribution=None,
                )
                command = make_transition_command(
                    transition=transition,
                    stream_id=case_id,
                    occurrence_id=occurrence_id,
                    current_state=definition.from_state,
                    expected_sequence=1,
                    expected_predecessor_sha256=None,
                    guard_proof=proof,
                )
                result = reduce_transition(
                    TransitionStream.initial(
                        stream_id=case_id,
                        state=definition.from_state,
                    ),
                    command,
                    occurred_at=due,
                )
                self.assertEqual(result.event.transition, transition)

    def test_tr043_requires_terminal_context_and_exact_due_observation(self) -> None:
        history = _human_action_history("lifecycle-observation-deletion")
        observation = _exact_observation_for_history(history)
        transition = load_doi_registries().transition_ref("TR-043")
        definition = transition_definition(transition)
        occurrence_id = observation_deletion_occurrence_id(observation)
        due = calendar90(observation.observed_at)
        proof = make_observation_graph_deletion_guard_proof(
            transition=transition,
            stream_id=observation.observation_id,
            occurrence_id=occurrence_id,
            observation=observation,
            action_context_history=history,
            now=due,
        )
        command = make_transition_command(
            transition=transition,
            stream_id=observation.observation_id,
            occurrence_id=occurrence_id,
            current_state=definition.from_state,
            expected_sequence=1,
            expected_predecessor_sha256=None,
            guard_proof=proof,
        )
        result = reduce_transition(
            TransitionStream.initial(
                stream_id=observation.observation_id,
                state=definition.from_state,
            ),
            command,
            occurred_at=due,
        )
        self.assertEqual(result.event.transition, transition)
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "OBSERVATION_DELETION_NOT_DUE",
        ):
            make_observation_graph_deletion_guard_proof(
                transition=transition,
                stream_id=observation.observation_id,
                occurrence_id=occurrence_id,
                observation=observation,
                action_context_history=history,
                now=observation.observed_at,
            )
        unrelated_retention = schedule_retention(
            case_id=EvidenceId("SYN-EVIDENCE-LIFECYCLE-UNRELATED-CASE"),
            closure_event_id=EvidenceId(
                "SYN-EVIDENCE-LIFECYCLE-UNRELATED-CLOSURE"
            ),
            lifecycle_state=CaseLifecycleState.CLOSED_REVERSIBLE,
            closure_reason=TerminalClosureReason.REP_TRANSFERRED,
            closed_at=observation.observed_at,
            projection_revision=1,
            projection_sha256="c" * 64,
        )
        opening_context = DOIActionContext.from_event(history.events[0])
        mismatched_case = DOIOrderCase(
            case_id=EvidenceId("SYN-EVIDENCE-LIFECYCLE-DIFFERENT-CASE"),
            order_id=opening_context.order_id,
            lifecycle_state=CaseLifecycleState.CLOSED_REVERSIBLE,
            current_snapshot_id=None,
            current_evaluation_id=None,
            terminal_closure_reason=TerminalClosureReason.REP_TRANSFERRED,
        )
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "OBSERVATION_DELETION_EVIDENCE_INVALID",
        ):
            make_observation_graph_deletion_guard_proof(
                transition=transition,
                stream_id=observation.observation_id,
                occurrence_id=occurrence_id,
                observation=observation,
                action_context_history=history,
                now=unrelated_retention.purge_eligible_at,
                active_case_retention=unrelated_retention,
                case=mismatched_case,
            )

    def test_tr044_and_tr086_require_reducer_accepted_system_completion(self) -> None:
        history, action = _system_action_history_and_event()
        registries = load_doi_registries()
        tr044 = registries.transition_ref("TR-044")
        tr044_definition = transition_definition(tr044)
        action_proof = make_system_action_transition_guard_proof(
            transition=tr044,
            stream_id=action.intervention_id,
            occurrence_id=action.event_id,
            action_event=action,
            action_context_history=history,
        )
        action_command = make_transition_command(
            transition=tr044,
            stream_id=action.intervention_id,
            occurrence_id=action.event_id,
            current_state=tr044_definition.from_state,
            expected_sequence=1,
            expected_predecessor_sha256=None,
            guard_proof=action_proof,
        )
        action_result = reduce_transition(
            TransitionStream.initial(
                stream_id=action.intervention_id,
                state=tr044_definition.from_state,
            ),
            action_command,
            occurred_at=history.events[-1].occurred_at,
        )
        self.assertEqual(action_result.event.transition, tr044)

        tr086 = registries.transition_ref("TR-086")
        tr086_definition = transition_definition(tr086)
        completion = history.events[-1]
        completion_proof = make_action_context_completion_guard_proof(
            transition=tr086,
            stream_id=history.action_context_id,
            occurrence_id=completion.event_id,
            action_context_history=history,
        )
        completion_command = make_transition_command(
            transition=tr086,
            stream_id=history.action_context_id,
            occurrence_id=completion.event_id,
            current_state=tr086_definition.from_state,
            expected_sequence=1,
            expected_predecessor_sha256=None,
            guard_proof=completion_proof,
        )
        completion_result = reduce_transition(
            TransitionStream.initial(
                stream_id=history.action_context_id,
                state=tr086_definition.from_state,
            ),
            completion_command,
            occurred_at=completion.occurred_at,
        )
        self.assertEqual(completion_result.event.transition, tr086)

        open_only = DOIActionContextHistory(
            action_context_id=history.action_context_id,
            projection=DOIActionContext.from_event(history.events[0]),
            events=(history.events[0],),
        )
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "ACTION_CONTEXT_COMPLETION_EVIDENCE_INVALID",
        ):
            make_action_context_completion_guard_proof(
                transition=tr086,
                stream_id=history.action_context_id,
                occurrence_id=completion.event_id,
                action_context_history=open_only,
            )

    def test_tr105_and_tr114_require_real_identity_retention_purge(self) -> None:
        control, batch, attempt, terminal_run, _ = _terminal_source_batch_owner_graph()
        rejected = batch.rejected_records[0]
        cases = (
            (
                "TR-105",
                IdentityRetentionKind.REJECTED_SOURCE_RECORD,
                rejected,
                batch,
            ),
            (
                "TR-114",
                IdentityRetentionKind.SOURCE_IMPORT_ATTEMPT,
                attempt,
                None,
            ),
        )
        registries = load_doi_registries()
        for transition_id, kind, identity_record, source_batch in cases:
            with self.subTest(transition=transition_id):
                scheduled = schedule_identity_retention(
                    kind=kind,
                    identity_binding=identity_record.hash_binding(),
                    run_completed_at=terminal_run.completed_at,
                )
                transition = registries.transition_ref(transition_id)
                definition = transition_definition(transition)
                stream_id = identity_retention_stream_id(identity_record)
                occurrence_id = identity_retention_occurrence_id(
                    transition,
                    identity_record,
                )
                proof = make_identity_retention_purge_guard_proof(
                    transition=transition,
                    stream_id=stream_id,
                    occurrence_id=occurrence_id,
                    scheduled_decision=scheduled,
                    identity_record=identity_record,
                    terminal_run=terminal_run,
                    run_control=control,
                    source_batch=source_batch,
                    now=scheduled.purge_eligible_at,
                )
                command = make_transition_command(
                    transition=transition,
                    stream_id=stream_id,
                    occurrence_id=occurrence_id,
                    current_state=definition.from_state,
                    expected_sequence=1,
                    expected_predecessor_sha256=None,
                    guard_proof=proof,
                )
                result = reduce_transition(
                    TransitionStream.initial(
                        stream_id=stream_id,
                        state=definition.from_state,
                    ),
                    command,
                    occurred_at=scheduled.purge_eligible_at,
                )
                self.assertEqual(result.event.transition, transition)

    def test_identity_purge_rejects_wrong_stream_nonterminal_and_forged_clock(self) -> None:
        control, _, attempt, terminal_run, _ = _terminal_source_batch_owner_graph()
        transition = load_doi_registries().transition_ref("TR-114")
        scheduled = schedule_identity_retention(
            kind=IdentityRetentionKind.SOURCE_IMPORT_ATTEMPT,
            identity_binding=attempt.hash_binding(),
            run_completed_at=terminal_run.completed_at,
        )
        occurrence_id = identity_retention_occurrence_id(transition, attempt)
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "IDENTITY_RETENTION_PURGE_EVIDENCE_INVALID",
        ):
            make_identity_retention_purge_guard_proof(
                transition=transition,
                stream_id=EvidenceId("SYN-EVIDENCE-IDENTITY-PURGE-WRONG-STREAM"),
                occurrence_id=occurrence_id,
                scheduled_decision=scheduled,
                identity_record=attempt,
                terminal_run=terminal_run,
                run_control=control,
                now=scheduled.purge_eligible_at,
            )
        forged = schedule_identity_retention(
            kind=IdentityRetentionKind.SOURCE_IMPORT_ATTEMPT,
            identity_binding=attempt.hash_binding(),
            run_completed_at=CanonicalTimestamp("2026-05-23T12:00:00Z"),
        )
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "IDENTITY_RETENTION_TERMINAL_CLOCK_INVALID",
        ):
            make_identity_retention_purge_guard_proof(
                transition=transition,
                stream_id=identity_retention_stream_id(attempt),
                occurrence_id=occurrence_id,
                scheduled_decision=forged,
                identity_record=attempt,
                terminal_run=terminal_run,
                run_control=control,
                now=forged.purge_eligible_at,
            )

        nonterminal_control = InMemoryDOIRunControl()
        started = nonterminal_control.begin_review_run(
            run_id=RunId("SYN-RUN-LIFECYCLE-NONTERMINAL"),
            invocation_id=RunInvocationId(
                InteractionId("SYN-INTERACTION-LIFECYCLE-NONTERMINAL")
            ),
            source_identity_id=SourceIdentityId(
                EvidenceId("SYN-EVIDENCE-LIFECYCLE-NONTERMINAL-SOURCE")
            ),
            locked_tab=SyntheticQueueTab.MONDAY,
            tab_confirmed=True,
            accepted_at=CanonicalTimestamp("2026-05-22T11:00:00Z"),
        )
        assert started.source_attempt is not None
        nonterminal_schedule = schedule_identity_retention(
            kind=IdentityRetentionKind.SOURCE_IMPORT_ATTEMPT,
            identity_binding=started.source_attempt.hash_binding(),
            run_completed_at=CanonicalTimestamp("2026-05-22T12:00:00Z"),
        )
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "IDENTITY_RETENTION_PURGE_EVIDENCE_INVALID",
        ):
            make_identity_retention_purge_guard_proof(
                transition=transition,
                stream_id=identity_retention_stream_id(started.source_attempt),
                occurrence_id=identity_retention_occurrence_id(
                    transition,
                    started.source_attempt,
                ),
                scheduled_decision=nonterminal_schedule,
                identity_record=started.source_attempt,
                terminal_run=started.run,
                run_control=nonterminal_control,
                now=nonterminal_schedule.purge_eligible_at,
            )

    def test_tr113_derives_due_release_and_last_owner_from_bound_runs(self) -> None:
        control, batch, _, run, _ = _terminal_source_batch_owner_graph()
        completed_at = run.completed_at
        due = run.purge_eligible_at
        self.assertIsNotNone(completed_at)
        self.assertIsNotNone(due)
        transition = load_doi_registries().transition_ref("TR-113")
        definition = transition_definition(transition)
        occurrence_id = source_batch_release_occurrence_id(batch)
        proof = make_source_batch_release_guard_proof(
            transition=transition,
            stream_id=batch.batch_id.value,
            occurrence_id=occurrence_id,
            source_batch=batch,
            run_control=control,
            now=due,
        )
        command = make_transition_command(
            transition=transition,
            stream_id=batch.batch_id.value,
            occurrence_id=occurrence_id,
            current_state=definition.from_state,
            expected_sequence=1,
            expected_predecessor_sha256=None,
            guard_proof=proof,
        )
        result = reduce_transition(
            TransitionStream.initial(
                stream_id=batch.batch_id.value,
                state=definition.from_state,
            ),
            command,
            occurred_at=due,
        )
        self.assertEqual(result.event.transition, transition)
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "SOURCE_BATCH_RELEASE_NOT_DUE",
        ):
            make_source_batch_release_guard_proof(
                transition=transition,
                stream_id=batch.batch_id.value,
                occurrence_id=occurrence_id,
                source_batch=batch,
                run_control=control,
                now=completed_at,
            )

    def test_tr113_owning_registry_prevents_omitted_active_owner_deletion(self) -> None:
        control, batch, _, terminal_run, _ = _terminal_source_batch_owner_graph()
        second = control.begin_review_run(
            run_id=RunId("SYN-RUN-LIFECYCLE-OWNER-SECOND"),
            invocation_id=RunInvocationId(
                InteractionId("SYN-INTERACTION-LIFECYCLE-OWNER-SECOND")
            ),
            source_identity_id=SourceIdentityId(
                EvidenceId("SYN-EVIDENCE-LIFECYCLE-OWNER-SOURCE-SECOND")
            ),
            locked_tab=SyntheticQueueTab.MONDAY,
            tab_confirmed=True,
            accepted_at=CanonicalTimestamp("2026-05-23T11:00:00Z"),
        )
        assert second.source_attempt is not None
        image = _image(
            (
                _row(1, "SYN-ORDER-2"),
                _row(2, "SYN-ORDER-2", "OTHER_REP"),
            )
        )
        second_import = ingest_synthetic_queue(
            image,
            image,
            candidate_batch_id=SourceBatchId(
                EvidenceId("SYN-EVIDENCE-LIFECYCLE-OWNER-BATCH-SECOND")
            ),
        )
        control.commit_import_result(
            attempt_id=second.source_attempt.attempt_id,
            result=second_import,
            completed_at=CanonicalTimestamp("2026-05-23T11:30:00Z"),
        )
        self.assertEqual(len(control.runs_for_source_batch(batch.batch_id)), 2)
        transition = load_doi_registries().transition_ref("TR-113")
        proof = make_source_batch_release_guard_proof(
            transition=transition,
            stream_id=batch.batch_id.value,
            occurrence_id=source_batch_release_occurrence_id(batch),
            source_batch=batch,
            run_control=control,
            now=terminal_run.purge_eligible_at,
        )
        evidence = proof.authority_evidence.evidence
        self.assertIs(type(evidence), dict)
        self.assertFalse(evidence["delete_batch"])
        self.assertEqual(len(evidence["remaining_owner_runs"]), 1)
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "TRANSITION_OWNER_ADAPTER_INPUT_INVALID",
        ):
            make_source_batch_release_guard_proof(
                transition=transition,
                stream_id=batch.batch_id.value,
                occurrence_id=source_batch_release_occurrence_id(batch),
                source_batch=batch,
                owner_runs=(terminal_run,),  # type: ignore[call-arg]
                now=terminal_run.purge_eligible_at,
            )

    def test_guard_authority_is_opaque_hash_bound_and_scope_bound(self) -> None:
        transition = load_doi_registries().transition_ref("TR-013")
        fixture = TransitionFixture.legal(transition)
        authority = fixture.command.guard_proof.authority_evidence
        self.assertEqual(
            authority.hash_binding().domain,
            "doi-transition-guard-authority/v1",
        )
        with self.assertRaisesRegex(
            LifecycleSchemaError,
            "TRANSITION_GUARD_AUTHORITY_CONSTRUCTION_INVALID",
        ):
            TransitionGuardAuthorityEvidence()  # type: ignore[call-arg]
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "TRANSITION_GUARD_AUTHORITY_SCOPE_CONFLICT",
        ):
            make_transition_command(
                transition=transition,
                stream_id=EvidenceId("SYN-EVIDENCE-FORGED-AUTHORITY-STREAM"),
                occurrence_id=EvidenceId("SYN-EVIDENCE-FORGED-AUTHORITY-EVENT"),
                current_state=fixture.definition.from_state,
                expected_sequence=1,
                expected_predecessor_sha256=None,
                guard_proof=fixture.command.guard_proof,
            )
        definition = fixture.definition
        changed_facts = satisfying_transition_guard_facts(transition)
        changed_facts[transition_guard_fact_schema(transition).required_facts[0]] = False
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "TRANSITION_GUARD_AUTHORITY_BINDING_CONFLICT",
        ):
            make_transition_guard_proof(
                transition=transition,
                from_state=definition.from_state,
                expected_to_state=definition.to_state,
                registered_guard=definition.guard,
                required_effects=definition.required_effects,
                guard_facts=changed_facts,
                authority_evidence=authority,
            )

    def test_guard_proof_binds_every_registered_transition_member_exactly(self) -> None:
        transition = load_doi_registries().transition_ref("TR-044")
        definition = transition_definition(transition)
        proof = _guard_proof(transition)
        self.assertEqual(proof.transition, transition)
        self.assertEqual(proof.from_state, definition.from_state)
        self.assertEqual(proof.to_state, definition.to_state)
        self.assertEqual(proof.registered_guard, definition.guard)
        self.assertEqual(proof.required_effects, definition.required_effects)
        self.assertEqual(
            proof.fact_schema,
            transition_guard_fact_schema(transition),
        )
        self.assertEqual(proof.hash_binding().domain, "doi-transition-guard-proof/v1")
        with self.assertRaises(LifecycleSchemaError):
            TransitionGuardProof()  # type: ignore[call-arg]

        claims = (
            (
                {"from_state": "FORGED_FROM_STATE"},
                "TRANSITION_GUARD_FROM_STATE_CONFLICT",
            ),
            (
                {"expected_to_state": f"{definition.to_state} FORGED"},
                "TRANSITION_GUARD_TARGET_CONFLICT",
            ),
            (
                {"registered_guard": f"{definition.guard} FORGED"},
                "TRANSITION_REGISTERED_GUARD_CONFLICT",
            ),
            (
                {"required_effects": f"{definition.required_effects} FORGED"},
                "TRANSITION_REGISTERED_EFFECTS_CONFLICT",
            ),
        )
        for changed, code in claims:
            values = {
                "transition": transition,
                "from_state": definition.from_state,
                "expected_to_state": definition.to_state,
                "registered_guard": definition.guard,
                "required_effects": definition.required_effects,
                "guard_facts": satisfying_transition_guard_facts(transition),
            }
            values.update(changed)
            with self.subTest(code=code):
                with self.assertRaisesRegex(LifecycleConflictError, code):
                    make_transition_guard_proof(**values)  # type: ignore[arg-type]

        other = load_doi_registries().transition_ref("TR-045")
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "TRANSITION_GUARD_PROOF_BINDING_CONFLICT",
        ):
            make_transition_command(
                transition=other,
                stream_id=EvidenceId("SYN-EVIDENCE-CROSS-GUARD-STREAM"),
                occurrence_id=EvidenceId("SYN-EVIDENCE-CROSS-GUARD-EVENT"),
                current_state=transition_definition(other).from_state,
                expected_sequence=1,
                expected_predecessor_sha256=None,
                guard_proof=proof,
            )

    def test_guard_fact_schema_rejects_missing_extra_and_non_boolean_members(self) -> None:
        transition = load_doi_registries().transition_ref("TR-112")
        satisfying = satisfying_transition_guard_facts(transition)
        required = transition_guard_fact_schema(transition).required_facts
        missing = dict(satisfying)
        del missing[required[0]]
        extra = {**satisfying, "caller_asserted_valid": True}
        wrong_type: dict[str, object] = dict(satisfying)
        wrong_type[required[0]] = 1
        for facts in (missing, extra, wrong_type):
            with self.subTest(facts=tuple(facts)):
                with self.assertRaisesRegex(
                    LifecycleSchemaError,
                    "TRANSITION_GUARD_FACT_SCHEMA_INVALID",
                ):
                    _guard_proof(transition, facts)

    def test_tr112_requires_each_purge_and_reconciliation_fact_before_effects(self) -> None:
        transition = load_doi_registries().transition_ref("TR-112")
        definition = transition_definition(transition)
        fixture = TransitionFixture.legal(transition)
        required = transition_guard_fact_schema(transition).required_facts
        self.assertIn("purge_eligible", required)
        self.assertIn("reconciliation_matches", required)
        for fact_name in required:
            with self.subTest(fact=fact_name):
                facts = satisfying_transition_guard_facts(transition)
                facts[fact_name] = False
                proof = _guard_proof(transition, facts)
                self.assertIs(
                    proof.verdict,
                    TransitionGuardVerdict.NOT_SATISFIED,
                )
                stream_id = fixture.command.stream_id
                stream = TransitionStream.initial(
                    stream_id=stream_id,
                    state=definition.from_state,
                )
                command = make_transition_command(
                    transition=transition,
                    stream_id=stream_id,
                    occurrence_id=fixture.command.occurrence_id,
                    current_state=definition.from_state,
                    expected_sequence=1,
                    expected_predecessor_sha256=None,
                    guard_proof=proof,
                )
                with self.assertRaisesRegex(
                    LifecycleConflictError,
                    "TRANSITION_GUARD_FALSE",
                ):
                    reduce_fixture_transition(
                        stream,
                        command,
                        occurred_at=CanonicalTimestamp("2026-08-20T12:00:00Z"),
                    )
                self.assertEqual(stream.events, ())

    def test_exact_replay_returns_original_event_without_append(self) -> None:
        transition = load_doi_registries().transition_ref("TR-044")
        fixture = TransitionFixture.legal(transition)
        accepted = reduce_fixture_transition(
            fixture.stream,
            fixture.command,
            occurred_at=fixture.occurred_at,
        )
        replay = reduce_fixture_transition(
            accepted.stream,
            fixture.command,
            occurred_at=CanonicalTimestamp("2026-08-21T12:00:00Z"),
        )
        self.assertTrue(replay.replayed)
        self.assertIs(replay.stream, accepted.stream)
        self.assertEqual(replay.event, accepted.event)
        self.assertEqual(len(replay.stream.events), 1)

    def test_same_occurrence_with_changed_material_conflicts(self) -> None:
        transition = load_doi_registries().transition_ref("TR-044")
        fixture = TransitionFixture.legal(transition)
        accepted = reduce_fixture_transition(
            fixture.stream,
            fixture.command,
            occurred_at=fixture.occurred_at,
        )
        conflict = make_transition_command(
            transition=transition,
            stream_id=fixture.command.stream_id,
            occurrence_id=fixture.command.occurrence_id,
            current_state=fixture.command.current_state,
            expected_sequence=1,
            expected_predecessor_sha256=None,
            guard_proof=_guard_proof(
                transition,
                failing_transition_guard_facts(transition),
            ),
        )
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "TRANSITION_OCCURRENCE_MATERIAL_CONFLICT",
        ) as conflict_error:
            reduce_fixture_transition(
                accepted.stream,
                conflict,
                occurred_at=fixture.occurred_at,
            )
        self.assertEqual(conflict_error.exception.reason.code, "RC-111")
        with patch.object(
            TransitionCommand,
            "hash_binding",
            return_value=accepted.event.command,
        ):
            with self.assertRaisesRegex(
                LifecycleCollisionError,
                "TRANSITION_COMMAND_DIGEST_COLLISION",
            ) as collision_error:
                reduce_fixture_transition(
                    accepted.stream,
                    conflict,
                    occurred_at=fixture.occurred_at,
                )
        self.assertEqual(collision_error.exception.reason.code, "RC-103")
        self.assertEqual(len(accepted.stream.events), 1)

    def test_sequence_predecessor_and_from_state_conflicts_preserve_stream(self) -> None:
        transition = load_doi_registries().transition_ref("TR-044")
        fixture = TransitionFixture.legal(transition)
        for sequence, predecessor, state, code in (
            (
                2,
                "0" * 64,
                fixture.command.current_state,
                "TRANSITION_SEQUENCE_CONFLICT",
            ),
        ):
            command = make_transition_command(
                transition=transition,
                stream_id=fixture.command.stream_id,
                occurrence_id=fixture.command.occurrence_id,
                current_state=state,
                expected_sequence=sequence,
                expected_predecessor_sha256=predecessor,
                guard_proof=_guard_proof(transition),
            )
            with self.assertRaisesRegex(LifecycleConflictError, code) as caught:
                reduce_fixture_transition(
                    fixture.stream,
                    command,
                    occurred_at=fixture.occurred_at,
                )
            self.assertEqual(caught.exception.reason.code, "RC-111")
            self.assertEqual(fixture.stream.events, ())

    def test_malformed_lifecycle_event_schema_is_rc113_before_append(self) -> None:
        transition = load_doi_registries().transition_ref("TR-044")
        fixture = TransitionFixture.legal(transition)
        with self.assertRaises(LifecycleSchemaError) as caught:
            TransitionEvent(
                event_id=fixture.command.occurrence_id,
                stream_id=fixture.command.stream_id,
                sequence=1,
                transition=transition,
                from_state=fixture.definition.from_state,
                to_state=fixture.definition.to_state,
                occurred_at=fixture.occurred_at,
                predecessor_sha256=None,
                command=fixture.command.hash_binding(),
                command_bytes=b"{}",
                reasons=fixture.command.reasons,
            )
        self.assertEqual(caught.exception.reason.code, "RC-113")
        self.assertEqual(fixture.stream.events, ())

    def test_reason_emission_is_limited_to_exact_transition_ownership(self) -> None:
        registries = load_doi_registries()
        transition = registries.transition_ref("TR-044")
        legal = registries.reason_ref("RC-061")
        illegal = registries.reason_ref("RC-019")
        fixture = TransitionFixture.legal(transition)
        self.assertIn(legal, legal_reason_refs(transition))
        command = make_transition_command(
            transition=transition,
            stream_id=fixture.command.stream_id,
            occurrence_id=fixture.command.occurrence_id,
            current_state=transition_definition(transition).from_state,
            expected_sequence=1,
            expected_predecessor_sha256=None,
            guard_proof=_guard_proof(transition),
            reasons=(legal,),
        )
        self.assertEqual(command.reasons.reasons, (legal,))
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "REASON_TRANSITION_OWNERSHIP_INVALID",
        ):
            make_transition_command(
                transition=transition,
                stream_id=fixture.command.stream_id,
                occurrence_id=fixture.command.occurrence_id,
                current_state=transition_definition(transition).from_state,
                expected_sequence=1,
                expected_predecessor_sha256=None,
                guard_proof=_guard_proof(transition),
                reasons=(illegal,),
            )

    def test_reason_routes_use_the_approved_effective_overlay(self) -> None:
        registries = load_doi_registries()
        opportunity = registries.transition_ref("TR-034")
        manual_review = registries.transition_ref("TR-037")
        availability_unknown = registries.reason_ref("RC-016")
        drop_ship_unknown = registries.reason_ref("RC-017")
        overlap = registries.reason_ref("RC-087")
        opportunity_fixture = TransitionFixture.legal(opportunity)
        manual_review_fixture = TransitionFixture.legal(manual_review)
        opportunity_reasons = legal_reason_refs(opportunity)
        self.assertTrue(
            {availability_unknown, drop_ship_unknown, overlap}.issubset(opportunity_reasons)
        )
        self.assertIn(availability_unknown, legal_reason_refs(manual_review))
        self.assertIn(drop_ship_unknown, legal_reason_refs(manual_review))
        self.assertNotIn(overlap, legal_reason_refs(manual_review))
        command = make_transition_command(
            transition=opportunity,
            stream_id=opportunity_fixture.command.stream_id,
            occurrence_id=opportunity_fixture.command.occurrence_id,
            current_state=transition_definition(opportunity).from_state,
            expected_sequence=1,
            expected_predecessor_sha256=None,
            guard_proof=_guard_proof(opportunity),
            reasons=(availability_unknown, drop_ship_unknown, overlap),
        )
        accepted = reduce_fixture_transition(
            TransitionStream.initial(
                stream_id=command.stream_id,
                state=command.current_state,
            ),
            command,
            occurred_at=CanonicalTimestamp("2026-08-20T12:00:00Z"),
        )
        self.assertEqual(accepted.event.transition, opportunity)
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "REASON_TRANSITION_OWNERSHIP_INVALID",
        ):
            make_transition_command(
                transition=manual_review,
                stream_id=manual_review_fixture.command.stream_id,
                occurrence_id=manual_review_fixture.command.occurrence_id,
                current_state=transition_definition(manual_review).from_state,
                expected_sequence=1,
                expected_predecessor_sha256=None,
                guard_proof=_guard_proof(manual_review),
                reasons=(overlap,),
            )

    def test_purge_transition_effects_are_closed_and_persistence_neutral(self) -> None:
        fixture = TransitionFixture.legal(load_doi_registries().transition_ref("TR-112"))
        result = reduce_fixture_transition(
            fixture.stream,
            fixture.command,
            occurred_at=fixture.occurred_at,
        )
        self.assertEqual(
            result.effects,
            registered_transition_effects(fixture.definition.transition),
        )
        self.assertEqual(len(result.effects), 1)
        self.assertIs(
            result.effects[0].kind,
            TransitionEffectKind.REGISTERED_EFFECTS,
        )
        self.assertEqual(
            result.effects[0].required_effects,
            fixture.definition.required_effects,
        )
        self.assertIn("delete graph", result.effects[0].required_effects.casefold())
        self.assertIn("total unchanged", result.effects[0].required_effects.casefold())

    def test_transition_effect_rejects_non_registry_effect_material(self) -> None:
        transition = load_doi_registries().transition_ref("TR-112")
        with self.assertRaisesRegex(
            LifecycleSchemaError,
            "TRANSITION_REGISTERED_EFFECTS_INVALID",
        ):
            TransitionEffect(
                kind=TransitionEffectKind.REGISTERED_EFFECTS,
                transition=transition,
                ordinal=1,
                required_effects="caller-selected deletion",
            )

    def test_attention_causes_coexist_and_clear_references_exact_set(self) -> None:
        case_id = EvidenceId("SYN-EVIDENCE-ATTENTION-CASE")
        first = AttentionEvent.set(
            event_id=EvidenceId("SYN-EVIDENCE-ATTENTION-SET-001"),
            case_id=case_id,
            condition=AttentionCondition.RECHECK_REQUIRED,
            cause_key=EvidenceId("SYN-EVIDENCE-ATTENTION-CAUSE-001"),
            occurred_at=CanonicalTimestamp("2026-08-20T12:00:00Z"),
        )
        second = AttentionEvent.set(
            event_id=EvidenceId("SYN-EVIDENCE-ATTENTION-SET-002"),
            case_id=case_id,
            condition=AttentionCondition.RESULTING_ORDER_LINK_REVIEW,
            cause_key=EvidenceId("SYN-EVIDENCE-ATTENTION-CAUSE-002"),
            occurred_at=CanonicalTimestamp("2026-08-20T12:01:00Z"),
        )
        stream = reduce_attention(AttentionStream(case_id), first).stream
        stream = reduce_attention(stream, second).stream
        self.assertEqual(len(stream.active), 2)
        clear = AttentionEvent.clear(
            event_id=EvidenceId("SYN-EVIDENCE-ATTENTION-CLEAR-001"),
            active_set=first,
            resolver_id=EvidenceId("SYN-EVIDENCE-ATTENTION-RESOLVER-001"),
            occurred_at=CanonicalTimestamp("2026-08-20T12:02:00Z"),
        )
        result = reduce_attention(stream, clear)
        self.assertEqual(len(result.stream.active), 1)
        self.assertEqual(
            result.stream.active[0].condition,
            AttentionCondition.RESULTING_ORDER_LINK_REVIEW,
        )
        self.assertEqual(clear.transition.transition_id, "TR-024")

    def test_attention_wrong_set_cannot_clear_and_replay_is_exact(self) -> None:
        case_id = EvidenceId("SYN-EVIDENCE-ATTENTION-CASE-REPLAY")
        set_event = AttentionEvent.set(
            event_id=EvidenceId("SYN-EVIDENCE-ATTENTION-SET-REPLAY"),
            case_id=case_id,
            condition=AttentionCondition.HUMAN_COORDINATION_REVIEW_REQUIRED,
            cause_key=EvidenceId("SYN-EVIDENCE-ATTENTION-CAUSE-REPLAY"),
            occurred_at=CanonicalTimestamp("2026-08-20T12:00:00Z"),
        )
        accepted = reduce_attention(AttentionStream(case_id), set_event)
        replay = reduce_attention(accepted.stream, set_event)
        self.assertTrue(replay.replayed)
        wrong_set = AttentionEvent(
            event_id=EvidenceId("SYN-EVIDENCE-ATTENTION-CLEAR-WRONG"),
            case_id=case_id,
            action=AttentionAction.CLEAR,
            condition=set_event.condition,
            cause_key=set_event.cause_key,
            active_set_event_id=EvidenceId("SYN-EVIDENCE-ATTENTION-WRONG-SET"),
            resolver_id=EvidenceId("SYN-EVIDENCE-ATTENTION-RESOLVER-WRONG"),
            occurred_at=CanonicalTimestamp("2026-08-20T12:01:00Z"),
            transition=load_doi_registries().transition_ref("TR-095"),
        )
        with self.assertRaisesRegex(LifecycleConflictError, "ATTENTION_CLEAR_SET_CONFLICT"):
            reduce_attention(accepted.stream, wrong_set)
        self.assertEqual(len(accepted.stream.active), 1)

    def test_lifecycle_local_enum_is_immutable(self) -> None:
        with self.assertRaises(AttributeError):
            TransitionEffectKind.REGISTERED_EFFECTS._value_ = (  # type: ignore[misc]
                "CHANGED"
            )

    def test_forged_from_state_and_prohibited_guard_material_fail_before_append(self) -> None:
        transition = load_doi_registries().transition_ref("TR-114")
        fixture = TransitionFixture.legal(transition)
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "TRANSITION_FROM_STATE_CONFLICT",
        ):
            make_transition_command(
                transition=transition,
                stream_id=fixture.command.stream_id,
                occurrence_id=fixture.command.occurrence_id,
                current_state="FORGED_FROM_STATE",
                expected_sequence=1,
                expected_predecessor_sha256=None,
                guard_proof=fixture.command.guard_proof,
            )
        marker = "private" + "@example.com"
        with self.assertRaises(LifecycleSchemaError) as caught:
            _guard_proof(
                transition=transition,
                facts={"customer_email": marker},
            )
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assertNotIn(marker, str(caught.exception))

    def test_hash_fixtures_cover_each_lifecycle_hash_record(self) -> None:
        fixtures = lifecycle_hash_fixtures()
        self.assertEqual(
            tuple(name for name, _, _, _ in fixtures),
            (
                "TransitionGuardAuthorityEvidence",
                "TransitionGuardFacts",
                "TransitionGuardProof",
                "TransitionCommand",
                "TransitionEvent",
                "AttentionEvent",
            ),
        )
        for _, domain, canonical_bytes, digest in fixtures:
            self.assertEqual(domain_hash(domain, canonical_bytes).sha256, digest)


@dataclasses.dataclass(frozen=True, slots=True)
class _CapturedProductionOwnerScenario:
    transition: TransitionRef
    stream_id: EvidenceId
    occurrence_id: EvidenceId
    occurred_at: CanonicalTimestamp
    proof: TransitionGuardProof


class _TargetOwnerProofCaptured(RuntimeError):
    def __init__(self, scenario: _CapturedProductionOwnerScenario) -> None:
        self.scenario = scenario
        super().__init__(scenario.transition.transition_id)


def _owner_scenario_method_map() -> dict[str, str]:
    groups = (
        (
            {"TR-001", "TR-002", "TR-003", "TR-004"},
            "test_run_control_owner_reducer_proves_tr001_through_tr004",
        ),
        (
            {"TR-005", "TR-006"},
            "test_extraction_owner_reducer_proves_tr005_and_tr006",
        ),
        (
            {
                "TR-007",
                "TR-008",
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
            },
            "test_case_and_attention_owner_decisions_prove_all_13_routes",
        ),
        (
            {
                "TR-009",
                "TR-010",
                "TR-011",
                "TR-012",
                "TR-016",
                "TR-017",
                "TR-029",
                "TR-030",
            },
            "test_every_protected_closure_route_has_real_complete_evaluation",
        ),
        ({"TR-013"}, "test_tr013_requires_real_authorized_out_of_scope_fact"),
        (
            {"TR-014", "TR-015"},
            "test_tr014_and_tr015_require_exact_case_recheck_and_retention",
        ),
        (
            {"TR-018", "TR-019", "TR-112"},
            "test_tr018_tr019_and_tr112_share_real_case_purge_oracle",
        ),
        (
            {
                "TR-027",
                "TR-028",
                "TR-031",
                "TR-032",
                "TR-033",
                "TR-034",
                "TR-035",
                "TR-036",
                "TR-037",
                "TR-038",
            },
            "test_evaluation_owner_reducer_proves_tr027_028_and_every_top_level_route",
        ),
        (
            {"TR-039"},
            "test_tr039_requires_authorized_no_action_fact_and_recomputed_evaluation",
        ),
        (
            {"TR-040", "TR-041", "TR-042", "TR-082", "TR-083"},
            "test_product_knowledge_owner_reducers_prove_tr040_042_and_tr082_083",
        ),
        (
            {"TR-043"},
            "test_tr043_requires_terminal_context_and_exact_due_observation",
        ),
        (
            {"TR-044", "TR-086"},
            "test_tr044_and_tr086_require_reducer_accepted_system_completion",
        ),
        (
            {"TR-045"},
            "test_tr045_requires_completed_human_action_verification_event",
        ),
        (
            {"TR-045A"},
            "test_tr045a_requires_exact_ds_intervention_reduction",
        ),
        (
            {f"TR-{index:03d}" for index in range(46, 54)},
            "test_value_owner_reducer_proves_every_tr046_through_tr053_route",
        ),
        (
            {
                "TR-054",
                "TR-055",
                "TR-056",
                "TR-057",
                "TR-058",
                "TR-059",
                "TR-090",
                "TR-091",
                "TR-110",
                "TR-111",
            },
            "test_resulting_link_owner_reducer_proves_all_link_routes",
        ),
        (
            {"TR-060", "TR-061", "TR-062", "TR-063", "TR-064", "TR-096", "TR-097"},
            "test_dedupe_and_human_fact_owner_reducers_cover_tr060_064_and_tr096_097",
        ),
        (
            {
                "TR-065",
                "TR-066",
                "TR-067",
                "TR-068",
                "TR-069",
                "TR-070",
                "TR-071",
                "TR-072",
                "TR-073",
                "TR-080",
                "TR-081",
            },
            "test_contact_workflow_owner_reducer_proves_every_registered_edge",
        ),
        (
            {"TR-074", "TR-075", "TR-076", "TR-077", "TR-078", "TR-079"},
            "test_wwc_owner_reducer_proves_all_partition_and_reevaluation_routes",
        ),
        (
            {"TR-084", "TR-085", "TR-087"},
            "test_action_context_owner_reducer_proves_tr084_085_and_both_tr087_routes",
        ),
        (
            {"TR-088", "TR-089"},
            "test_resulting_link_search_owner_reducer_proves_tr088_and_tr089",
        ),
        (
            {f"TR-{index:03d}" for index in range(98, 105)},
            "test_source_owner_reducers_prove_tr098_through_tr104",
        ),
        (
            {"TR-105", "TR-114"},
            "test_tr105_and_tr114_require_real_identity_retention_purge",
        ),
        (
            {"TR-113"},
            "test_tr113_derives_due_release_and_last_owner_from_bound_runs",
        ),
        (
            {"TR-106", "TR-107", "TR-108", "TR-109"},
            "test_kpi_owner_reducer_proves_tr106_through_tr109",
        ),
    )
    result: dict[str, str] = {}
    for transition_ids, method_name in groups:
        for transition_id in transition_ids:
            if transition_id in result:
                raise AssertionError(
                    f"duplicate owner scenario for {transition_id}"
                )
            result[transition_id] = method_name
    return result


_OWNER_SCENARIO_METHOD = _owner_scenario_method_map()
if set(_OWNER_SCENARIO_METHOD) != set(recognized_transition_ids()):
    raise AssertionError(
        "production owner scenario inventory must cover all 115 transitions"
    )


def _dispatch_production_owner_scenario(
    transition: TransitionRef,
) -> _CapturedProductionOwnerScenario:
    method_name = _OWNER_SCENARIO_METHOD.get(transition.transition_id)
    if method_name is None:
        raise AssertionError(
            f"missing production owner scenario: {transition.transition_id}"
        )
    original = lifecycle_module._make_service_guard_proof

    def capture(**kwargs: object) -> TransitionGuardProof:
        proof = original(**kwargs)  # type: ignore[arg-type]
        captured_transition = kwargs.get("transition")
        if (
            type(captured_transition) is TransitionRef
            and captured_transition == transition
        ):
            scenario = _CapturedProductionOwnerScenario(
                transition=captured_transition,
                stream_id=kwargs["stream_id"],  # type: ignore[arg-type]
                occurrence_id=kwargs["occurrence_id"],  # type: ignore[arg-type]
                occurred_at=kwargs["satisfied_at"],  # type: ignore[arg-type]
                proof=proof,
            )
            raise _TargetOwnerProofCaptured(scenario)
        return proof

    case = TestDoiLifecycle(methodName=method_name)
    case.setUp()
    try:
        with patch.object(
            lifecycle_module,
            "_make_service_guard_proof",
            side_effect=capture,
        ):
            getattr(case, method_name)()
    except _TargetOwnerProofCaptured as captured:
        return captured.scenario
    finally:
        case.tearDown()
    raise AssertionError(
        f"owner scenario did not execute target: {transition.transition_id}"
    )


class TestStructuralRegisteredDoiTransitions(unittest.TestCase):
    """Fixture-only registry shape tests; these are not business-proof oracles."""


def _structural_legal_test(
    transition: TransitionRef,
) -> Callable[[TestStructuralRegisteredDoiTransitions], None]:
    def test(self: TestStructuralRegisteredDoiTransitions) -> None:
        fixture = TransitionFixture.legal(transition)
        original = fixture.stream
        result = reduce_fixture_transition(
            original,
            fixture.command,
            occurred_at=fixture.occurred_at,
        )
        self.assertFalse(result.replayed)
        self.assertEqual(result.event.transition, transition)
        self.assertEqual(result.event.to_state, fixture.definition.to_state)
        self.assertEqual(result.stream.projection.state, fixture.definition.to_state)
        self.assertEqual(len(result.stream.events), 1)
        self.assertEqual(original.events, ())
        self.assertEqual(result.effects, registered_transition_effects(transition))
        self.assertEqual(len(result.effects), 1)
        self.assertEqual(
            result.effects[0].required_effects,
            fixture.definition.required_effects,
        )
        self.assertIs(
            result.effects[0].kind,
            TransitionEffectKind.REGISTERED_EFFECTS,
        )

    return test


def _structural_invalid_guard_test(
    transition: TransitionRef,
) -> Callable[[TestStructuralRegisteredDoiTransitions], None]:
    def test(self: TestStructuralRegisteredDoiTransitions) -> None:
        guard_fixture = TransitionFixture.legal(transition)
        required_facts = transition_guard_fact_schema(transition).required_facts
        for fact_name in required_facts:
            with self.subTest(guard_fact=fact_name):
                facts = satisfying_transition_guard_facts(transition)
                facts[fact_name] = False
                proof = _guard_proof(transition, facts)
                self.assertIs(
                    proof.verdict,
                    TransitionGuardVerdict.NOT_SATISFIED,
                )
                command = make_transition_command(
                    transition=transition,
                    stream_id=guard_fixture.command.stream_id,
                    occurrence_id=guard_fixture.command.occurrence_id,
                    current_state=guard_fixture.command.current_state,
                    expected_sequence=1,
                    expected_predecessor_sha256=None,
                    guard_proof=proof,
                )
                with self.assertRaisesRegex(
                    LifecycleConflictError,
                    "TRANSITION_GUARD_FALSE",
                ):
                    reduce_fixture_transition(
                        guard_fixture.stream,
                        command,
                        occurred_at=guard_fixture.occurred_at,
                    )
                self.assertEqual(guard_fixture.stream.events, ())

        invalid_fixture = TransitionFixture.invalid(transition)
        self.assertEqual(
            invalid_fixture.command.guard_proof.guard_facts,
            _guard_proof(
                transition,
                failing_transition_guard_facts(transition),
            ).guard_facts,
        )

        state_fixture = TransitionFixture.legal(transition)
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "TRANSITION_FROM_STATE_CONFLICT",
        ):
            make_transition_command(
                transition=transition,
                stream_id=state_fixture.command.stream_id,
                occurrence_id=state_fixture.command.occurrence_id,
                current_state="SYN-INVALID-FROM-STATE",
                expected_sequence=1,
                expected_predecessor_sha256=None,
                guard_proof=state_fixture.command.guard_proof,
            )
        self.assertEqual(state_fixture.stream.events, ())

    return test


for _transition_ref in load_doi_registries().transition_refs:
    _stem = _transition_ref.transition_id.lower().replace("-", "_")
    setattr(
        TestStructuralRegisteredDoiTransitions,
        f"test_structural_{_stem}_legal",
        _structural_legal_test(_transition_ref),
    )
    setattr(
        TestStructuralRegisteredDoiTransitions,
        f"test_structural_{_stem}_invalid_guard",
        _structural_invalid_guard_test(_transition_ref),
    )


class TestAllRegisteredDoiTransitions(unittest.TestCase):
    """Every generated selector executes a real typed production-owner route."""


def _production_owner_legal_test(
    transition: TransitionRef,
) -> Callable[[TestAllRegisteredDoiTransitions], None]:
    def test(self: TestAllRegisteredDoiTransitions) -> None:
        scenario = _dispatch_production_owner_scenario(transition)
        definition = transition_definition(transition)
        self.assertEqual(scenario.transition, transition)
        self.assertEqual(
            scenario.proof.authority_evidence.transition,
            transition,
        )
        self.assertIs(
            scenario.proof.authority_evidence.issuer,
            TransitionGuardAuthorityIssuer.OWNING_SERVICE,
        )
        self.assertEqual(
            scenario.proof.authority_evidence.stream_id,
            scenario.stream_id,
        )
        self.assertEqual(
            scenario.proof.authority_evidence.occurrence_id,
            scenario.occurrence_id,
        )
        command = make_transition_command(
            transition=transition,
            stream_id=scenario.stream_id,
            occurrence_id=scenario.occurrence_id,
            current_state=definition.from_state,
            expected_sequence=1,
            expected_predecessor_sha256=None,
            guard_proof=scenario.proof,
        )
        original = TransitionStream.initial(
            stream_id=scenario.stream_id,
            state=definition.from_state,
        )
        result = reduce_transition(
            original,
            command,
            occurred_at=scenario.occurred_at,
        )
        self.assertFalse(result.replayed)
        self.assertEqual(result.event.transition, transition)
        self.assertEqual(result.event.to_state, definition.to_state)
        self.assertEqual(result.stream.projection.state, definition.to_state)
        self.assertEqual(result.effects, registered_transition_effects(transition))
        self.assertEqual(original.events, ())

    return test


def _production_owner_invalid_from_state_test(
    transition: TransitionRef,
) -> Callable[[TestAllRegisteredDoiTransitions], None]:
    def test(self: TestAllRegisteredDoiTransitions) -> None:
        scenario = _dispatch_production_owner_scenario(transition)
        definition = transition_definition(transition)
        command = make_transition_command(
            transition=transition,
            stream_id=scenario.stream_id,
            occurrence_id=scenario.occurrence_id,
            current_state=definition.from_state,
            expected_sequence=1,
            expected_predecessor_sha256=None,
            guard_proof=scenario.proof,
        )
        wrong_state_stream = TransitionStream.initial(
            stream_id=scenario.stream_id,
            state="SYN-INVALID-FROM-STATE",
        )
        with self.assertRaisesRegex(
            LifecycleConflictError,
            "TRANSITION_FROM_STATE_CONFLICT",
        ) as caught:
            reduce_transition(
                wrong_state_stream,
                command,
                occurred_at=scenario.occurred_at,
            )
        self.assertEqual(caught.exception.reason.code, "RC-081")
        self.assertEqual(wrong_state_stream.events, ())

    return test


for _transition_ref in load_doi_registries().transition_refs:
    _stem = _transition_ref.transition_id.lower().replace("-", "_")
    setattr(
        TestAllRegisteredDoiTransitions,
        f"test_{_stem}_production_owner_legal",
        _production_owner_legal_test(_transition_ref),
    )
    setattr(
        TestAllRegisteredDoiTransitions,
        f"test_{_stem}_production_owner_invalid_from_state",
        _production_owner_invalid_from_state_test(_transition_ref),
    )


del _stem
del _transition_ref


if __name__ == "__main__":
    unittest.main()
