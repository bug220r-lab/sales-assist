from __future__ import annotations

import dataclasses
import hashlib
import unittest
from decimal import Decimal

from synthetic_sales_assist.doi.identities import (
    DoiOrderId,
    DoiRunId,
    DoiSnapshotId,
    LineSnapshotId,
)
from synthetic_sales_assist.doi.evaluator import evaluate_doi
from synthetic_sales_assist.doi.models import (
    ActionContextCloseReason,
    ActionContextCompletionTrigger,
    ActionContextEventType,
    ActionContextKind,
    ActionContextState,
    CaseLifecycleState,
    ContactEventType,
    ContactState,
    ContactWorkflowEvent,
    ContactWorkflowEventType,
    ContactWorkflowHistory,
    ContactWorkflowReduction,
    ContactWorkflowState,
    DOI_MODEL_SCHEMA_VERSION,
    DOICaseAdmissionProof,
    DOICaseSourceBinding,
    DOIActionContext,
    DOIActionContextEvent,
    DOIActionContextHistory,
    DOIActionContextStore,
    DOIContactEvent,
    DOIContactHistory,
    DOIEvaluation,
    DOIEvaluationInput,
    DOIHumanFactEvent,
    DOIHumanFactHistory,
    DOIOccurrenceGuard,
    DOIWWCEvent,
    DOIWWCHistory,
    DedupeFinding,
    DedupeState,
    DOIExplanation,
    DOILineItemSnapshot,
    DOIModelError,
    DOIOpportunity,
    DOIOrderCase,
    DOIOpportunityScope,
    DOIOpportunityScopeComponent,
    DOIOrderSnapshot,
    DropShipState,
    GeographyClass,
    LineActivity,
    LineAvailability,
    LineContinuityProof,
    LineContinuityState,
    ContinuityProofType,
    OpportunityScopeRole,
    OrderState,
    PaymentCondition,
    QuantityAvailability,
    RepRelation,
    SourcePresence,
    HumanFactEventType,
    HumanFactResultCode,
    HumanFactUsageKind,
    StructuredHumanFact,
    WWCEventType,
    WWCAuthorRelation,
    WWCFinding,
    WWCProjectionState,
    WWCTimingState,
    known_fact,
    model_hash_contracts,
    model_hash_fixtures,
    model_hash_known_answer,
    not_applicable_fact,
    rule_pack_hash_binding,
    unknown_fact,
    reduce_action_context,
    reduce_action_context_store,
    reduce_contact,
    reduce_contact_workflow,
    reduce_human_fact,
    reduce_wwc,
    verify_action_context_opening_authority,
    verify_synthetic_human_authority,
)
from synthetic_sales_assist.domain.canonical import canonical_json_bytes, domain_hash
from synthetic_sales_assist.domain.identities import (
    EvidenceId,
    EvaluationId,
    InteractionId,
    OrderId,
    RepId,
    RunId,
    SkuId,
    SnapshotId,
)
from synthetic_sales_assist.domain.numeric import (
    CURRENCY_REGISTRY_VERSION,
    Money,
    NonNegativeCount,
    PositiveOrdinal,
    PositiveQuantity,
    Quantity,
)
from synthetic_sales_assist.domain.observed import FindingPresenceV2
from synthetic_sales_assist.domain.registries import load_doi_registries
from synthetic_sales_assist.domain.records import (
    LineManifestEntry,
    RequiredSectionProof,
    SourceKind,
    SourceObjectNamespace,
    SourceRef,
    VersionBinding,
    WholeOrderCompletenessProof,
)
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp


OBSERVED_AT = CanonicalTimestamp("2026-08-20T14:15:16Z")


def usd(amount: str) -> Money:
    return Money(Decimal(amount), "USD", CURRENCY_REGISTRY_VERSION, 2)


def order_source(order_id: OrderId) -> SourceRef:
    return SourceRef.create(
        source_ref_id=EvidenceId("SYN-EVIDENCE-DOI-ORDER-SOURCE-0001"),
        source_kind=SourceKind.SYNTHETIC_ORDER_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_ORDER,
        object_id=order_id,
    )


def interaction_source(suffix: str) -> tuple[InteractionId, SourceRef]:
    occurrence = InteractionId(f"SYN-INTERACTION-DOI-MODEL-{suffix}")
    source = SourceRef.create(
        source_ref_id=EvidenceId(f"SYN-EVIDENCE-DOI-MODEL-SOURCE-{suffix}"),
        source_kind=SourceKind.SYNTHETIC_INTERACTION_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_INTERACTION,
        object_id=occurrence,
    )
    return occurrence, source


def open_context_fixture(
    snapshot: DOIOrderSnapshot,
    suffix: str,
    *,
    evaluation: DOIEvaluation | None = None,
    opportunity: DOIOpportunity | None = None,
    context_kind: ActionContextKind = ActionContextKind.FULFILLMENT_SPLIT_REVIEW,
) -> tuple[
    DOIActionContext,
    DOIActionContextEvent,
    DOIOrderCase,
    DOICaseSourceBinding,
    DOIEvaluation,
    DOIOpportunity,
]:
    if evaluation is None:
        order_fact_source = snapshot.wwc_finding.source
        context_snapshot = make_snapshot(
            (
                make_line(
                    1,
                    order_fact_source,
                    availability=LineAvailability.IN_STOCK,
                    quantity_availability=QuantityAvailability.FULL,
                    explicitly_available=2,
                ),
                make_line(2, order_fact_source),
            ),
            snapshot_suffix=f"CONTEXT-{suffix}",
            run_suffix=f"CONTEXT-{suffix}",
        )
        evaluation = evaluate_doi(
            DOIEvaluationInput(
                evaluation_id=EvaluationId(f"SYN-EVALUATION-DOI-CONTEXT-{suffix}"),
                snapshot=context_snapshot,
                evaluated_at=OBSERVED_AT,
            )
        )
    else:
        context_snapshot = snapshot
        order_fact_source = snapshot.wwc_finding.source
    selected_opportunity = opportunity or evaluation.opportunities[0]
    if selected_opportunity not in evaluation.opportunities:
        raise AssertionError("fixture opportunity must belong to the evaluation")
    context_id = EvidenceId(f"SYN-EVIDENCE-DOI-CONTEXT-{suffix}")
    event_id = EvidenceId(f"SYN-EVIDENCE-DOI-CONTEXT-EVENT-{suffix}")
    occurrence, source = interaction_source(f"CONTEXT-{suffix}")
    case_id = EvidenceId(f"SYN-EVIDENCE-DOI-CONTEXT-CASE-{suffix}")
    admission = DOICaseAdmissionProof(
        proof_id=EvidenceId(f"SYN-EVIDENCE-DOI-CONTEXT-ADMISSION-{suffix}"),
        case_id=case_id,
        order_id=context_snapshot.order_id,
        source=order_fact_source,
        completeness_proof=context_snapshot.completeness_proof,
        admitted_at=OBSERVED_AT,
    )
    case_source = DOICaseSourceBinding(
        binding_id=EvidenceId(f"SYN-EVIDENCE-DOI-CONTEXT-SOURCE-{suffix}"),
        case_id=case_id,
        order_id=context_snapshot.order_id,
        source=order_fact_source,
        admission_proof=admission,
    )
    order_case = DOIOrderCase(
        case_id=case_id,
        order_id=context_snapshot.order_id,
        lifecycle_state=CaseLifecycleState.ACTIVE,
        current_snapshot_id=context_snapshot.snapshot_id,
        current_evaluation_id=evaluation.evaluation_id,
        terminal_closure_reason=None,
    )
    opening_authority = verify_action_context_opening_authority(
        authorization_id=EvidenceId(
            f"SYN-EVIDENCE-DOI-CONTEXT-OPEN-AUTH-{suffix}"
        ),
        attempt_intent_id=occurrence,
        case=order_case,
        case_source_binding=case_source,
        evaluation=evaluation,
        opportunity=selected_opportunity,
        context_kind=context_kind,
        actor=RepId(f"SYN-REP-DOI-CONTEXT-AUTH-{suffix}"),
        granted_at=OBSERVED_AT,
        authority_source=source,
    )
    event = DOIActionContextEvent.opened(
        event_id=event_id,
        action_context_id=context_id,
        opening_authorization=opening_authority,
        created_at=OBSERVED_AT,
        guard=DOIOccurrenceGuard(
            guard_id=event_id,
            owner_id=context_id,
            occurrence_id=occurrence,
            source=source,
        ),
    )
    return (
        DOIActionContext.from_event(event),
        event,
        order_case,
        case_source,
        evaluation,
        selected_opportunity,
    )


def open_context(
    snapshot: DOIOrderSnapshot,
    suffix: str,
    *,
    evaluation: DOIEvaluation | None = None,
    opportunity: DOIOpportunity | None = None,
    context_kind: ActionContextKind = ActionContextKind.FULFILLMENT_SPLIT_REVIEW,
) -> tuple[DOIActionContext, DOIActionContextEvent]:
    context, event, _, _, _, _ = open_context_fixture(
        snapshot,
        suffix,
        evaluation=evaluation,
        opportunity=opportunity,
        context_kind=context_kind,
    )
    return context, event


def make_line(
    index: int,
    source: SourceRef,
    *,
    activity: object = LineActivity.ACTIVE,
    drop_ship: object = DropShipState.NON_DS,
    availability: object = LineAvailability.DELAYED,
    quantity_availability: object = QuantityAvailability.NONE,
    active_quantity: int = 2,
    explicitly_available: int = 0,
    eta: object = OBSERVED_AT,
) -> DOILineItemSnapshot:
    line_id = LineSnapshotId(EvidenceId(f"SYN-EVIDENCE-DOI-LINE-{index:04d}"))
    stable_id = EvidenceId(f"SYN-EVIDENCE-DOI-STABLE-LINE-{index:04d}")
    continuity = LineContinuityProof(
        state=LineContinuityState.VERIFIED,
        proof_type=ContinuityProofType.STABLE_SOURCE_LINE_ID,
        stable_source_line_id=stable_id,
        composite_binding=None,
    )
    return DOILineItemSnapshot(
        line_snapshot_id=line_id,
        stable_source_line_id=known_fact(stable_id),
        relevant_merchandise=True,
        activity=(
            activity
            if hasattr(activity, "to_mapping")
            else known_fact(activity)
        ),
        drop_ship_state=(
            drop_ship
            if hasattr(drop_ship, "to_mapping")
            else known_fact(drop_ship)
        ),
        availability=(
            availability
            if hasattr(availability, "to_mapping")
            else known_fact(availability)
        ),
        eta=eta if hasattr(eta, "to_mapping") else known_fact(eta),
        ordered_quantity=known_fact(Quantity(active_quantity)),
        active_quantity=known_fact(Quantity(active_quantity)),
        canceled_quantity=known_fact(Quantity(0)),
        explicitly_available_quantity=known_fact(Quantity(explicitly_available)),
        quantity_availability=(
            quantity_availability
            if hasattr(quantity_availability, "to_mapping")
            else known_fact(quantity_availability)
        ),
        es_number=known_fact(SkuId(f"SYN-SKU-DOI-ES-{index:04d}")),
        mfg_number=known_fact(SkuId(f"SYN-SKU-DOI-MFG-{index:04d}")),
        unit_value=known_fact(usd("10.00")),
        active_line_value=known_fact(usd(f"{active_quantity * 10}.00")),
        line_sales_rep=known_fact(RepId("SYN-REP-TARGET-REP")),
        continuity=continuity,
        source=source,
    )


def make_wwc(
    source: SourceRef,
    *,
    presence: FindingPresenceV2 = FindingPresenceV2.NOT_PRESENT,
    author: object | None = None,
    timing: object | None = None,
    marker: object | None = None,
    observed_at: object | None = None,
) -> WWCFinding:
    if presence is not FindingPresenceV2.PRESENT:
        author_fact = timing_fact = marker_fact = observed_fact = not_applicable_fact()
    else:
        author_fact = author if hasattr(author, "to_mapping") else known_fact(author)
        timing_fact = timing if hasattr(timing, "to_mapping") else known_fact(timing)
        marker_fact = marker if hasattr(marker, "to_mapping") else known_fact(marker)
        observed_fact = (
            observed_at
            if hasattr(observed_at, "to_mapping")
            else known_fact(observed_at)
        )
    return WWCFinding(
        finding_id=EvidenceId("SYN-EVIDENCE-DOI-WWC-0001"),
        presence=presence,
        author_relation=author_fact,
        timing_state=timing_fact,
        marker=marker_fact,
        observed_at=observed_fact,
        source=source,
    )


def make_snapshot(
    lines: tuple[DOILineItemSnapshot, ...],
    *,
    order_state: object = OrderState.ACTIVE,
    rep_relation: object = RepRelation.TARGET_REP_OWNED,
    geography: object = GeographyClass.DOMESTIC_STANDARD,
    payment: object = PaymentCondition.NONE_OBSERVED,
    wwc: WWCFinding | None = None,
    dedupe_state: DedupeState = DedupeState.NOT_PRESENT,
    observed_at: CanonicalTimestamp = OBSERVED_AT,
    snapshot_suffix: str = "0001",
    run_suffix: str = "0001",
    dedupe_suffix: str = "0001",
) -> DOIOrderSnapshot:
    order = OrderId("SYN-ORDER-DOI-0001")
    source = order_source(order)
    if any(line.source != source for line in lines):
        raise AssertionError("fixture lines must bind the exact order source")
    manifest = tuple(
        LineManifestEntry(
            line.line_snapshot_id.value,
            PositiveOrdinal(index),
            source,
            domain_hash(
                LineManifestEntry.CONTENT_DOMAIN,
                canonical_json_bytes(
                    {"line": line.line_snapshot_id.to_json_value()},
                    expected_members={"line"},
                ),
            ),
        )
        for index, line in enumerate(lines, start=1)
    )
    sections = tuple(
        RequiredSectionProof.complete(
            section=section,
            source=source,
            observed_at=observed_at,
        )
        for section in WholeOrderCompletenessProof.REQUIRED_SECTIONS
    )
    proof = WholeOrderCompletenessProof(
        requested_order_id=order,
        observed_order_id=order,
        schema=VersionBinding(
            "whole_order_completeness",
            WholeOrderCompletenessProof.SCHEMA_VERSION,
        ),
        extractor=VersionBinding("extractor", WholeOrderCompletenessProof.EXTRACTOR_VERSION),
        fixture=VersionBinding("fixture", WholeOrderCompletenessProof.FIXTURE_VERSION),
        order_source_observed_at=observed_at,
        proof_source_observed_at=observed_at,
        required_sections=WholeOrderCompletenessProof.REQUIRED_SECTIONS,
        section_proofs=sections,
        declared_relevant_line_count=NonNegativeCount(len(lines)),
        observed_relevant_line_count=NonNegativeCount(len(lines)),
        ordered_line_manifest=manifest,
        duplicate_rule=VersionBinding(
            "duplicate_rule",
            WholeOrderCompletenessProof.DUPLICATE_RULE_VERSION,
        ),
        reordering_rule=VersionBinding(
            "reordering_rule",
            WholeOrderCompletenessProof.REORDERING_RULE_VERSION,
        ),
        source_refs=(source,),
        coherence_state="COHERENT",
        change_detection_state="UNCHANGED",
        empty_universe_proved=not lines,
    )
    dedupe_present = dedupe_state is DedupeState.SOURCE_PRESENT
    return DOIOrderSnapshot(
        snapshot_id=DoiSnapshotId(
            SnapshotId(f"SYN-SNAPSHOT-DOI-{snapshot_suffix}")
        ),
        run_id=DoiRunId(RunId(f"SYN-RUN-DOI-{run_suffix}")),
        order_id=DoiOrderId(order),
        source_observed_at=observed_at,
        completeness_proof=proof,
        source_presence=SourcePresence.PRESENT,
        order_state=(
            order_state
            if hasattr(order_state, "to_mapping")
            else known_fact(order_state)
        ),
        current_rep_value=known_fact(RepId("SYN-REP-TARGET-REP")),
        current_rep_relation=(
            rep_relation
            if hasattr(rep_relation, "to_mapping")
            else known_fact(rep_relation)
        ),
        geography_class=(
            geography if hasattr(geography, "to_mapping") else known_fact(geography)
        ),
        payment_condition=(
            payment if hasattr(payment, "to_mapping") else known_fact(payment)
        ),
        order_total=known_fact(usd("100.00")),
        wwc_finding=wwc or make_wwc(source),
        dedupe_finding=DedupeFinding(
            finding_id=EvidenceId(
                f"SYN-EVIDENCE-DOI-DEDUPE-{dedupe_suffix}"
            ),
            presence=(
                FindingPresenceV2.PRESENT
                if dedupe_present
                else FindingPresenceV2.NOT_PRESENT
            ),
            observed_at=observed_at if dedupe_present else None,
            state=dedupe_state,
            source=source,
        ),
        lines=lines,
    )


def ordinary_snapshot() -> DOIOrderSnapshot:
    source = order_source(OrderId("SYN-ORDER-DOI-0001"))
    return make_snapshot((make_line(1, source),))


class DOIModelTests(unittest.TestCase):
    def test_models_are_frozen_slotted_and_hash_bound(self) -> None:
        snapshot = ordinary_snapshot()
        for record in (
            snapshot.lines[0].continuity,
            snapshot.lines[0],
            snapshot.wwc_finding,
            snapshot.dedupe_finding,
            snapshot,
        ):
            with self.subTest(record=type(record).__name__):
                binding = record.hash_binding()
                known_answer = model_hash_known_answer(record)
                self.assertEqual(known_answer.sha256, binding.sha256)
                self.assertEqual(known_answer.preimage, binding.preimage)
                self.assertEqual(
                    binding.sha256,
                    hashlib.sha256(binding.preimage).hexdigest(),
                )
                self.assertEqual(
                    binding.preimage,
                    binding.domain.encode("ascii") + b"\n" + record.canonical_bytes(),
                )
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    record.schema_version = "changed"  # type: ignore[misc]

    def test_closed_enum_alias_and_wrong_field_reason_fail_without_retaining_input(self) -> None:
        source = order_source(OrderId("SYN-ORDER-DOI-0001"))
        marker = "private" + "@example.test"
        with self.assertRaises(DOIModelError) as caught:
            make_line(1, source, availability=known_fact(marker))
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assertNotIn(marker, str(caught.exception))
        with self.assertRaises(DOIModelError):
            make_line(1, source, availability=unknown_fact("RC-017"))

    def test_all_wwc_present_known_unknown_partitions_are_constructible(self) -> None:
        source = order_source(OrderId("SYN-ORDER-DOI-0001"))
        fields = (
            (WWCAuthorRelation.TARGET_REP, unknown_fact("RC-055")),
            (WWCTimingState.ACTIVE, unknown_fact("RC-056")),
            ("WWC_MARKER", unknown_fact("RC-122")),
            (OBSERVED_AT, unknown_fact("RC-056")),
        )
        for mask in range(16):
            values = [pair[(mask >> index) & 1] for index, pair in enumerate(fields)]
            finding = make_wwc(
                source,
                presence=FindingPresenceV2.PRESENT,
                author=values[0],
                timing=values[1],
                marker=values[2],
                observed_at=values[3],
            )
            self.assertEqual(finding.presence, FindingPresenceV2.PRESENT)
        with self.assertRaises(DOIModelError):
            make_wwc(
                source,
                presence=FindingPresenceV2.PRESENT,
                author=not_applicable_fact(),
                timing=WWCTimingState.ACTIVE,
                marker="WWC_MARKER",
                observed_at=OBSERVED_AT,
            )

    def test_all_known_wwc_author_timing_states_reduce_exactly(self) -> None:
        snapshot = ordinary_snapshot()
        expected = {
            (WWCAuthorRelation.TARGET_REP, WWCTimingState.ACTIVE): (
                WWCProjectionState.ACTIVE_SELF
            ),
            (WWCAuthorRelation.OTHER_REP, WWCTimingState.ACTIVE): (
                WWCProjectionState.ACTIVE_OTHER_REP
            ),
        }
        for author_index, author in enumerate(WWCAuthorRelation, start=1):
            for timing_index, timing in enumerate(WWCTimingState, start=1):
                with self.subTest(author=author.value, timing=timing.value):
                    suffix = f"{author_index:02d}{timing_index:02d}"
                    stream_id = EvidenceId(
                        f"SYN-EVIDENCE-DOI-WWC-MATRIX-STREAM-{suffix}"
                    )
                    event_id = EvidenceId(
                        f"SYN-EVIDENCE-DOI-WWC-MATRIX-EVENT-{suffix}"
                    )
                    occurrence, source = interaction_source(
                        f"WWC-MATRIX-{suffix}"
                    )
                    event = DOIWWCEvent(
                        event_id=event_id,
                        stream_id=stream_id,
                        order_id=snapshot.order_id,
                        event_type=WWCEventType.OBSERVED,
                        finding=make_wwc(
                            snapshot.wwc_finding.source,
                            presence=FindingPresenceV2.PRESENT,
                            author=author,
                            timing=timing,
                            marker="WWC_MARKER",
                            observed_at=OBSERVED_AT,
                        ),
                        corrects_event_id=None,
                        recorded_at=OBSERVED_AT,
                        sequence=1,
                        predecessor_binding=None,
                        guard=DOIOccurrenceGuard(
                            guard_id=event_id,
                            owner_id=stream_id,
                            occurrence_id=occurrence,
                            source=source,
                        ),
                    )
                    reduction = reduce_wwc(
                        DOIWWCHistory(
                            stream_id=stream_id,
                            order_id=snapshot.order_id,
                        ),
                        event,
                    )
                    author_uncertain = author is WWCAuthorRelation.UNCERTAIN
                    timing_uncertain = timing is WWCTimingState.UNCERTAIN
                    if author_uncertain and timing_uncertain:
                        expected_state = (
                            WWCProjectionState.AUTHOR_AND_TIMING_UNCERTAIN
                        )
                    elif author_uncertain:
                        expected_state = WWCProjectionState.AUTHOR_UNCERTAIN
                    elif timing_uncertain:
                        expected_state = WWCProjectionState.TIMING_UNCERTAIN
                    elif (
                        author is WWCAuthorRelation.OTHER_REP
                        and timing is WWCTimingState.EXPIRED
                    ):
                        expected_state = WWCProjectionState.EXPIRED_OTHER_REP
                    elif (
                        author is WWCAuthorRelation.TARGET_REP
                        and timing is WWCTimingState.EXPIRED
                    ):
                        expected_state = WWCProjectionState.NOT_APPLICABLE
                    else:
                        expected_state = expected[(author, timing)]
                    self.assertEqual(
                        reduction.history.projection.state,
                        expected_state,
                    )

    def test_all_64_wwc_present_partitions_are_hash_distinct_and_legal(self) -> None:
        source = ordinary_snapshot().wwc_finding.source
        authors = (
            known_fact(WWCAuthorRelation.TARGET_REP),
            known_fact(WWCAuthorRelation.OTHER_REP),
            known_fact(WWCAuthorRelation.UNCERTAIN),
            unknown_fact("RC-055"),
        )
        timings = (
            known_fact(WWCTimingState.ACTIVE),
            known_fact(WWCTimingState.EXPIRED),
            known_fact(WWCTimingState.UNCERTAIN),
            unknown_fact("RC-056"),
        )
        markers = (known_fact("WWC_MARKER"), unknown_fact("RC-122"))
        observed_times = (known_fact(OBSERVED_AT), unknown_fact("RC-056"))
        bindings = set()
        counter = 0
        for author in authors:
            for timing in timings:
                for marker in markers:
                    for observed_at in observed_times:
                        counter += 1
                        finding = make_wwc(
                            source,
                            presence=FindingPresenceV2.PRESENT,
                            author=author,
                            timing=timing,
                            marker=marker,
                            observed_at=observed_at,
                        )
                        bindings.add(finding.hash_binding().sha256)
                        stream_id = EvidenceId(
                            f"SYN-EVIDENCE-DOI-WWC-64-STREAM-{counter:04d}"
                        )
                        event_id = EvidenceId(
                            f"SYN-EVIDENCE-DOI-WWC-64-EVENT-{counter:04d}"
                        )
                        occurrence, event_source = interaction_source(
                            f"WWC-64-{counter:04d}"
                        )
                        event = DOIWWCEvent(
                            event_id=event_id,
                            stream_id=stream_id,
                            order_id=ordinary_snapshot().order_id,
                            event_type=WWCEventType.OBSERVED,
                            finding=finding,
                            corrects_event_id=None,
                            recorded_at=OBSERVED_AT,
                            sequence=1,
                            predecessor_binding=None,
                            guard=DOIOccurrenceGuard(
                                guard_id=event_id,
                                owner_id=stream_id,
                                occurrence_id=occurrence,
                                source=event_source,
                            ),
                        )
                        projection = reduce_wwc(
                            DOIWWCHistory(
                                stream_id=stream_id,
                                order_id=ordinary_snapshot().order_id,
                            ),
                            event,
                        ).history.projection
                        known_author = getattr(author, "value", None)
                        known_timing = getattr(timing, "value", None)
                        marker_known = getattr(marker, "value", None) is not None
                        observed_at_known = (
                            getattr(observed_at, "value", None) is not None
                        )
                        author_uncertain = known_author not in {
                            WWCAuthorRelation.TARGET_REP.value,
                            WWCAuthorRelation.OTHER_REP.value,
                        }
                        timing_uncertain = (
                            known_timing
                            not in {
                                WWCTimingState.ACTIVE.value,
                                WWCTimingState.EXPIRED.value,
                            }
                            or not observed_at_known
                        )
                        if not marker_known:
                            author_uncertain = True
                            timing_uncertain = True
                        if author_uncertain and timing_uncertain:
                            expected_state = (
                                WWCProjectionState.AUTHOR_AND_TIMING_UNCERTAIN
                            )
                        elif author_uncertain:
                            expected_state = WWCProjectionState.AUTHOR_UNCERTAIN
                        elif timing_uncertain:
                            expected_state = WWCProjectionState.TIMING_UNCERTAIN
                        elif known_timing == WWCTimingState.ACTIVE.value:
                            expected_state = {
                                WWCAuthorRelation.TARGET_REP.value: (
                                    WWCProjectionState.ACTIVE_SELF
                                ),
                                WWCAuthorRelation.OTHER_REP.value: (
                                    WWCProjectionState.ACTIVE_OTHER_REP
                                ),
                            }[known_author]
                        elif known_author == WWCAuthorRelation.OTHER_REP.value:
                            expected_state = WWCProjectionState.EXPIRED_OTHER_REP
                        else:
                            expected_state = WWCProjectionState.NOT_APPLICABLE
                        self.assertEqual(projection.state, expected_state)
        self.assertEqual(len(bindings), 64)
        with self.assertRaises(DOIModelError):
            make_wwc(
                source,
                presence=FindingPresenceV2.PRESENT,
                author=unknown_fact("RC-056"),
                timing=WWCTimingState.ACTIVE,
                marker="WWC_MARKER",
                observed_at=OBSERVED_AT,
            )

    def test_dedupe_present_requires_constructible_timestamp(self) -> None:
        source = order_source(OrderId("SYN-ORDER-DOI-0001"))
        with self.assertRaises(DOIModelError):
            DedupeFinding(
                finding_id=EvidenceId("SYN-EVIDENCE-DOI-DEDUPE-0001"),
                presence=FindingPresenceV2.PRESENT,
                observed_at=None,
                state=DedupeState.CONFIRMED,
                source=source,
            )

        with self.assertRaises(DOIModelError):
            DedupeFinding(
                finding_id=EvidenceId("SYN-EVIDENCE-DOI-DEDUPE-0002"),
                presence=FindingPresenceV2.PRESENT,
                observed_at=OBSERVED_AT,
                state=DedupeState.CONFIRMED,
                source=source,
            )

    def test_r01_order_observation_matrix_is_field_specific(self) -> None:
        snapshot = ordinary_snapshot()
        cases = (
            ("order_state", "RC-116", False),
            ("current_rep_value", "RC-117", False),
            ("current_rep_relation", "RC-118", False),
            ("geography_class", "RC-119", False),
            ("payment_condition", "RC-120", False),
            ("order_total", "RC-121", True),
        )
        for field_name, reason, allows_not_applicable in cases:
            with self.subTest(field=field_name, branch="KNOWN"):
                accepted = dataclasses.replace(
                    snapshot,
                    **{field_name: getattr(snapshot, field_name)},
                )
                self.assertEqual(getattr(accepted, field_name).tag.value, "KNOWN")
            with self.subTest(field=field_name, branch="UNKNOWN"):
                accepted = dataclasses.replace(
                    snapshot,
                    **{field_name: unknown_fact(reason)},
                )
                self.assertEqual(getattr(accepted, field_name).reason_code, reason)
            with self.subTest(field=field_name, branch="NOT_APPLICABLE"):
                if allows_not_applicable:
                    accepted = dataclasses.replace(
                        snapshot,
                        **{field_name: not_applicable_fact()},
                    )
                    self.assertEqual(
                        getattr(accepted, field_name).tag.value,
                        "NOT_APPLICABLE",
                    )
                else:
                    with self.assertRaises(DOIModelError):
                        dataclasses.replace(
                            snapshot,
                            **{field_name: not_applicable_fact()},
                        )
            with self.subTest(field=field_name, branch="WRONG_REASON"):
                with self.assertRaises(DOIModelError):
                    dataclasses.replace(
                        snapshot,
                        **{field_name: unknown_fact("RC-115")},
                    )
            with self.subTest(field=field_name, branch="ALIAS"):
                with self.assertRaises(DOIModelError):
                    dataclasses.replace(
                        snapshot,
                        **{field_name: known_fact("ALIAS")},
                    )

    def test_r01_finding_presence_matrix_is_direct_and_closed(self) -> None:
        snapshot = ordinary_snapshot()
        source = order_source(snapshot.order_id.value)
        for presence in FindingPresenceV2:
            with self.subTest(finding="WWC", presence=presence.value):
                if presence is FindingPresenceV2.PRESENT:
                    finding = make_wwc(
                        source,
                        presence=presence,
                        author=WWCAuthorRelation.TARGET_REP,
                        timing=WWCTimingState.ACTIVE,
                        marker="WWC_MARKER",
                        observed_at=OBSERVED_AT,
                    )
                else:
                    finding = make_wwc(source, presence=presence)
                self.assertEqual(finding.presence, presence)
            with self.subTest(finding="DEDUPE", presence=presence.value):
                finding = DedupeFinding(
                    finding_id=EvidenceId(
                        f"SYN-EVIDENCE-DOI-DEDUPE-{len(presence.value):04d}"
                    ),
                    presence=presence,
                    observed_at=(
                        OBSERVED_AT
                        if presence is FindingPresenceV2.PRESENT
                        else None
                    ),
                    state=(
                        DedupeState.SOURCE_PRESENT
                        if presence is FindingPresenceV2.PRESENT
                        else DedupeState.NOT_PRESENT
                    ),
                    source=source,
                )
                self.assertEqual(finding.presence, presence)
        with self.assertRaises(DOIModelError):
            dataclasses.replace(snapshot.wwc_finding, presence="UNKNOWN")
        with self.assertRaises(DOIModelError):
            dataclasses.replace(snapshot.dedupe_finding, presence="UNKNOWN")

    def test_r01_line_observation_matrix_is_field_specific(self) -> None:
        line = ordinary_snapshot().lines[0]
        unverified = LineContinuityProof(
            state=LineContinuityState.UNVERIFIED,
            proof_type=ContinuityProofType.NONE,
            stable_source_line_id=None,
            composite_binding=None,
        )
        cases = (
            ("stable_source_line_id", "RC-124"),
            ("activity", "RC-125"),
            ("es_number", "RC-126"),
            ("mfg_number", "RC-127"),
            ("ordered_quantity", "RC-128"),
            ("active_quantity", "RC-129"),
            ("canceled_quantity", "RC-130"),
            ("explicitly_available_quantity", "RC-131"),
            ("quantity_availability", "RC-132"),
            ("unit_value", "RC-133"),
            ("active_line_value", "RC-134"),
            ("line_sales_rep", "RC-135"),
        )
        for field_name, reason in cases:
            with self.subTest(field=field_name, branch="KNOWN"):
                accepted = dataclasses.replace(
                    line,
                    **{field_name: getattr(line, field_name)},
                )
                self.assertEqual(getattr(accepted, field_name).tag.value, "KNOWN")
            extra = {"continuity": unverified} if field_name.startswith("stable_") else {}
            for branch, value in (
                ("UNKNOWN", unknown_fact(reason)),
                ("NOT_APPLICABLE", not_applicable_fact()),
            ):
                with self.subTest(field=field_name, branch=branch):
                    accepted = dataclasses.replace(
                        line,
                        **{field_name: value, **extra},
                    )
                    self.assertEqual(getattr(accepted, field_name).tag.value, branch)
            for branch, value in (
                ("WRONG_REASON", unknown_fact("RC-115")),
                ("ALIAS", known_fact("ALIAS")),
            ):
                with self.subTest(field=field_name, branch=branch):
                    with self.assertRaises(DOIModelError):
                        dataclasses.replace(
                            line,
                            **{field_name: value, **extra},
                        )

    def test_scope_is_exact_positive_ordered_and_hash_bound(self) -> None:
        first = DOIOpportunityScopeComponent(
            LineSnapshotId(EvidenceId("SYN-EVIDENCE-DOI-LINE-0001")),
            PositiveQuantity(1),
            OpportunityScopeRole.AVAILABLE,
        )
        second = dataclasses.replace(
            first,
            line_snapshot_id=LineSnapshotId(
                EvidenceId("SYN-EVIDENCE-DOI-LINE-0002")
            ),
            role=OpportunityScopeRole.DELAYED,
        )
        scope = DOIOpportunityScope((first, second))
        self.assertEqual(len(scope.line_ids), 2)
        with self.assertRaises(DOIModelError):
            DOIOpportunityScope((second, first))
        with self.assertRaises(DOIModelError):
            DOIOpportunityScope((first, first))

    def test_explanation_rejects_free_text_and_noncanonical_collections(self) -> None:
        registries = load_doi_registries()
        accepted = DOIExplanation(
            supplied_facts=("COMPLETE_ORDER_SNAPSHOT",),
            normalized_facts=("SOURCE_PRESENCE=PRESENT",),
            unavailable_facts=(),
            rules_evaluated=("DIRECT_SHIP",),
            rules_fired=("DIRECT_SHIP",),
            precedence_decision="DOI_EXCLUDED",
            reason_codes=("RC-019",),
            reason_ownership=("RC-019@TR-031",),
            opportunity_ids=(),
            opportunity_scopes=(),
            opportunity_values=(),
            handling_flags=(),
            human_review_requirements=(),
            closure_state="NONE",
            rule_pack_binding=rule_pack_hash_binding(),
            reason_registry_version=registries.reason_registry_version,
            transition_registry_version=registries.transition_registry_version,
        )
        self.assertEqual(accepted.schema_version, DOI_MODEL_SCHEMA_VERSION)
        with self.assertRaises(DOIModelError):
            dataclasses.replace(accepted, rules_fired=("UNKNOWN_RULE",))
        with self.assertRaises(DOIModelError):
            dataclasses.replace(accepted, supplied_facts=("X", "X"))

    def test_case_admission_and_source_binding_are_exact_and_hash_bound(self) -> None:
        snapshot = ordinary_snapshot()
        case_id = EvidenceId("SYN-EVIDENCE-DOI-CASE-MODEL-0001")
        proof = DOICaseAdmissionProof(
            proof_id=EvidenceId("SYN-EVIDENCE-DOI-ADMISSION-MODEL-0001"),
            case_id=case_id,
            order_id=snapshot.order_id,
            source=snapshot.wwc_finding.source,
            completeness_proof=snapshot.completeness_proof,
            admitted_at=OBSERVED_AT,
        )
        source_binding = DOICaseSourceBinding(
            binding_id=EvidenceId("SYN-EVIDENCE-DOI-CASE-SOURCE-MODEL-0001"),
            case_id=case_id,
            order_id=snapshot.order_id,
            source=snapshot.wwc_finding.source,
            admission_proof=proof,
        )
        for record in (proof, source_binding):
            with self.subTest(record=type(record).__name__):
                self.assertEqual(
                    model_hash_known_answer(record).preimage,
                    record.hash_binding().preimage,
                )
        with self.assertRaises(DOIModelError):
            dataclasses.replace(
                source_binding,
                case_id=EvidenceId("SYN-EVIDENCE-DOI-CASE-MODEL-9999"),
            )

    def test_action_context_owner_attempt_and_terminal_routes_are_exact(self) -> None:
        snapshot = ordinary_snapshot()
        (
            context,
            opening,
            order_case,
            case_source,
            evaluation,
            opportunity,
        ) = open_context_fixture(snapshot, "OWNER-0001")
        first = reduce_action_context_store(DOIActionContextStore(), opening)
        replay = reduce_action_context_store(first.store, opening)
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.history, first.history)
        self.assertEqual(context.case_id, order_case.case_id)
        self.assertEqual(context.evaluation_id, evaluation.evaluation_id)
        self.assertEqual(context.opportunity_id, opportunity.opportunity_id)
        self.assertEqual(context.line_scope, tuple(sorted(
            opportunity.scope.line_ids,
            key=lambda item: item.to_json_value(),
        )))
        with self.assertRaises(TypeError):
            DOIActionContextEvent(event_id=opening.event_id)  # type: ignore[call-arg]

        conflict_id = EvidenceId("SYN-EVIDENCE-DOI-CONTEXT-CONFLICT-0001")
        conflict_authority = verify_action_context_opening_authority(
            authorization_id=EvidenceId(
                "SYN-EVIDENCE-DOI-CONTEXT-CONFLICT-AUTH-0001"
            ),
            attempt_intent_id=opening.attempt_intent_id,
            case=order_case,
            case_source_binding=case_source,
            evaluation=evaluation,
            opportunity=opportunity,
            context_kind=ActionContextKind.INTERVENTION_VERIFICATION,
            actor=opening.opening_authorization.actor,
            granted_at=OBSERVED_AT,
            authority_source=opening.opening_authorization.source,
        )
        conflict_opening = DOIActionContextEvent.opened(
            event_id=conflict_id,
            action_context_id=EvidenceId(
                "SYN-EVIDENCE-DOI-CONTEXT-CONFLICT-CONTEXT-0001"
            ),
            opening_authorization=conflict_authority,
            created_at=OBSERVED_AT,
            guard=DOIOccurrenceGuard(
                guard_id=conflict_id,
                owner_id=EvidenceId(
                    "SYN-EVIDENCE-DOI-CONTEXT-CONFLICT-CONTEXT-0001"
                ),
                occurrence_id=opening.attempt_intent_id,
                source=opening.opening_authorization.source,
            ),
        )
        with self.assertRaisesRegex(
            DOIModelError,
            "DOI_ACTION_CONTEXT_ATTEMPT_CONFLICT",
        ):
            reduce_action_context_store(first.store, conflict_opening)
        with self.assertRaisesRegex(
            DOIModelError,
            "DOI_ACTION_CONTEXT_OPENING_OWNER_INVALID",
        ):
            verify_action_context_opening_authority(
                authorization_id=EvidenceId(
                    "SYN-EVIDENCE-DOI-CONTEXT-WRONG-OWNER-AUTH"
                ),
                attempt_intent_id=InteractionId(
                    "SYN-INTERACTION-DOI-MODEL-WRONG-OWNER"
                ),
                case=dataclasses.replace(
                    order_case,
                    current_evaluation_id=EvaluationId(
                        "SYN-EVALUATION-DOI-WRONG-OWNER"
                    ),
                ),
                case_source_binding=case_source,
                evaluation=evaluation,
                opportunity=opportunity,
                context_kind=ActionContextKind.FULFILLMENT_SPLIT_REVIEW,
                actor=RepId("SYN-REP-DOI-CONTEXT-WRONG-OWNER"),
                granted_at=OBSERVED_AT,
                authority_source=interaction_source("WRONG-OWNER")[1],
            )

        later_at = CanonicalTimestamp("2026-08-20T14:15:17Z")
        later_attempt, later_source = interaction_source("LATER-ATTEMPT")
        later_authority = verify_action_context_opening_authority(
            authorization_id=EvidenceId(
                "SYN-EVIDENCE-DOI-CONTEXT-LATER-AUTH-0001"
            ),
            attempt_intent_id=later_attempt,
            case=order_case,
            case_source_binding=case_source,
            evaluation=evaluation,
            opportunity=opportunity,
            context_kind=ActionContextKind.FULFILLMENT_SPLIT_REVIEW,
            actor=RepId("SYN-REP-DOI-CONTEXT-LATER-AUTH"),
            granted_at=later_at,
            authority_source=later_source,
        )
        later_context_id = EvidenceId(
            "SYN-EVIDENCE-DOI-CONTEXT-LATER-CONTEXT-0001"
        )
        later_open_id = EvidenceId("SYN-EVIDENCE-DOI-CONTEXT-LATER-OPEN-0001")
        later_opening = DOIActionContextEvent.opened(
            event_id=later_open_id,
            action_context_id=later_context_id,
            opening_authorization=later_authority,
            created_at=later_at,
            guard=DOIOccurrenceGuard(
                guard_id=later_open_id,
                owner_id=later_context_id,
                occurrence_id=later_attempt,
                source=later_source,
            ),
        )
        supersede_id = EvidenceId("SYN-EVIDENCE-DOI-CONTEXT-SUPERSEDE-0001")
        superseded = DOIActionContextEvent.superseded(
            event_id=supersede_id,
            action_context=context,
            superseding_open_event=later_opening,
            occurred_at=later_at,
            guard=DOIOccurrenceGuard(
                guard_id=supersede_id,
                owner_id=context.action_context_id,
                occurrence_id=later_attempt,
                source=later_source,
            ),
        )
        superseded_history = reduce_action_context(first.history, superseded).history
        self.assertEqual(
            superseded_history.projection.state,
            ActionContextState.CLOSED_SUPERSEDED,
        )
        self.assertEqual(
            superseded_history.projection.close_reason,
            ActionContextCloseReason.SUPERSEDED_BY_LATER_ATTEMPT,
        )

        abandoned_context, abandoned_opening = open_context(snapshot, "ABANDON-0001")
        abandon_occurrence, abandon_source = interaction_source("ABANDON-0001")
        abandon_authority = verify_synthetic_human_authority(
            grant_id=EvidenceId("SYN-EVIDENCE-DOI-CONTEXT-ABANDON-AUTH"),
            actor=RepId("SYN-REP-DOI-CONTEXT-ABANDON-AUTH"),
            action_context=abandoned_context,
            granted_at=OBSERVED_AT,
            authority_source=abandon_source,
        )
        abandon_id = EvidenceId("SYN-EVIDENCE-DOI-CONTEXT-ABANDON-EVENT")
        abandoned = DOIActionContextEvent.abandoned(
            event_id=abandon_id,
            action_context=abandoned_context,
            authority=abandon_authority,
            occurred_at=OBSERVED_AT,
            guard=DOIOccurrenceGuard(
                guard_id=abandon_id,
                owner_id=abandoned_context.action_context_id,
                occurrence_id=abandon_occurrence,
                source=abandon_source,
            ),
        )
        abandoned_history = reduce_action_context(
            reduce_action_context(
                DOIActionContextHistory(
                    action_context_id=abandoned_context.action_context_id
                ),
                abandoned_opening,
            ).history,
            abandoned,
        ).history
        self.assertEqual(
            abandoned_history.projection.state,
            ActionContextState.CLOSED_ABANDONED,
        )
        self.assertNotEqual(
            abandoned_history.projection.state,
            superseded_history.projection.state,
        )

    def test_action_context_and_contact_histories_replay_and_correct_exactly(self) -> None:
        snapshot = ordinary_snapshot()
        context, opened = open_context(snapshot, "HISTORY-0001")
        history = DOIActionContextHistory(action_context_id=context.action_context_id)
        opened_reduction = reduce_action_context(history, opened)
        self.assertFalse(opened_reduction.replayed)
        self.assertEqual(opened_reduction.history.projection, context)
        self.assertTrue(
            reduce_action_context(opened_reduction.history, opened).replayed
        )

        completed_id = EvidenceId("SYN-EVIDENCE-DOI-CONTEXT-COMPLETE-0001")
        completed_occurrence, completed_source = interaction_source(
            "CONTEXT-COMPLETE-0001"
        )
        completion_authority = verify_synthetic_human_authority(
            grant_id=EvidenceId("SYN-EVIDENCE-DOI-CONTEXT-COMPLETE-AUTH-0001"),
            actor=RepId("SYN-REP-DOI-CONTEXT-COMPLETE-AUTH-0001"),
            action_context=context,
            granted_at=OBSERVED_AT,
            authority_source=completed_source,
        )
        completed = DOIActionContextEvent.completed(
            event_id=completed_id,
            action_context=context,
            completion_trigger=ActionContextCompletionTrigger.HUMAN_ACCEPTED,
            occurred_at=OBSERVED_AT,
            authority=completion_authority,
            guard=DOIOccurrenceGuard(
                guard_id=completed_id,
                owner_id=context.action_context_id,
                occurrence_id=completed_occurrence,
                source=completed_source,
            ),
        )
        completed_reduction = reduce_action_context(
            opened_reduction.history,
            completed,
        )
        self.assertEqual(
            completed_reduction.history.projection.state,
            ActionContextState.CLOSED_COMPLETED,
        )
        self.assertTrue(
            reduce_action_context(completed_reduction.history, completed).replayed
        )

        stream_id = EvidenceId("SYN-EVIDENCE-DOI-CONTACT-STREAM-0001")
        event_id = EvidenceId("SYN-EVIDENCE-DOI-CONTACT-EVENT-0001")
        occurrence, source = interaction_source("CONTACT-0001")
        inbound = DOIContactEvent(
            event_id=event_id,
            stream_id=stream_id,
            order_id=snapshot.order_id,
            action_context=context,
            event_type=ContactEventType.INBOUND,
            corrected_direction=None,
            corrects_event_id=None,
            target_rep_participated=True,
            contact_occurred_at=OBSERVED_AT,
            recorded_at=OBSERVED_AT,
            sequence=1,
            predecessor_binding=None,
            guard=DOIOccurrenceGuard(
                guard_id=event_id,
                owner_id=stream_id,
                occurrence_id=occurrence,
                source=source,
            ),
        )
        contact_history = DOIContactHistory.empty(
            stream_id=stream_id,
            order_id=snapshot.order_id,
        )
        self.assertEqual(contact_history.projection.state, ContactState.NONE_OBSERVED)
        inbound_reduction = reduce_contact(contact_history, inbound)
        self.assertEqual(
            inbound_reduction.history.projection.state,
            ContactState.INBOUND_OBSERVED,
        )
        self.assertTrue(reduce_contact(inbound_reduction.history, inbound).replayed)

        correction_id = EvidenceId("SYN-EVIDENCE-DOI-CONTACT-EVENT-0002")
        correction_occurrence, correction_source = interaction_source("CONTACT-0002")
        correction = DOIContactEvent(
            event_id=correction_id,
            stream_id=stream_id,
            order_id=snapshot.order_id,
            action_context=context,
            event_type=ContactEventType.CORRECTION,
            corrected_direction=ContactEventType.OUTBOUND,
            corrects_event_id=inbound.event_id,
            target_rep_participated=True,
            contact_occurred_at=OBSERVED_AT,
            recorded_at=OBSERVED_AT,
            sequence=2,
            predecessor_binding=inbound.hash_binding(),
            guard=DOIOccurrenceGuard(
                guard_id=correction_id,
                owner_id=stream_id,
                occurrence_id=correction_occurrence,
                source=correction_source,
            ),
        )
        corrected = reduce_contact(inbound_reduction.history, correction)
        self.assertEqual(
            corrected.history.projection.state,
            ContactState.OUTBOUND_OBSERVED,
        )
        third_id = EvidenceId("SYN-EVIDENCE-DOI-CONTACT-EVENT-0003")
        third_occurrence, third_source = interaction_source("CONTACT-0003")
        second_direction = DOIContactEvent(
            event_id=third_id,
            stream_id=stream_id,
            order_id=snapshot.order_id,
            action_context=context,
            event_type=ContactEventType.INBOUND,
            corrected_direction=None,
            corrects_event_id=None,
            target_rep_participated=True,
            contact_occurred_at=OBSERVED_AT,
            recorded_at=OBSERVED_AT,
            sequence=3,
            predecessor_binding=correction.hash_binding(),
            guard=DOIOccurrenceGuard(
                guard_id=third_id,
                owner_id=stream_id,
                occurrence_id=third_occurrence,
                source=third_source,
            ),
        )
        bidirectional = reduce_contact(corrected.history, second_direction)
        self.assertEqual(
            bidirectional.history.projection.state,
            ContactState.BIDIRECTIONAL_OBSERVED,
        )
        unknown_id = EvidenceId("SYN-EVIDENCE-DOI-CONTACT-EVENT-0004")
        unknown_occurrence, unknown_source = interaction_source("CONTACT-0004")
        governed_unknown = DOIContactEvent(
            event_id=unknown_id,
            stream_id=stream_id,
            order_id=snapshot.order_id,
            action_context=context,
            event_type=ContactEventType.UNKNOWN,
            corrected_direction=None,
            corrects_event_id=None,
            target_rep_participated=False,
            contact_occurred_at=OBSERVED_AT,
            recorded_at=OBSERVED_AT,
            sequence=4,
            predecessor_binding=second_direction.hash_binding(),
            guard=DOIOccurrenceGuard(
                guard_id=unknown_id,
                owner_id=stream_id,
                occurrence_id=unknown_occurrence,
                source=unknown_source,
            ),
        )
        unknown_reduction = reduce_contact(
            bidirectional.history,
            governed_unknown,
        )
        self.assertEqual(
            unknown_reduction.history.projection.state,
            ContactState.UNKNOWN,
        )
        for record in (
            opened.guard,
            opened,
            context,
            completed,
            inbound,
            inbound_reduction.history.projection,
            correction,
            corrected.history.projection,
            second_direction,
            bidirectional.history.projection,
            governed_unknown,
            unknown_reduction.history.projection,
        ):
            self.assertEqual(
                model_hash_known_answer(record).sha256,
                record.hash_binding().sha256,
            )

    def test_contact_workflow_reducer_covers_registered_edges_only(self) -> None:
        order_source_ref = order_source(OrderId("SYN-ORDER-DOI-0001"))
        snapshot = make_snapshot(
            (
                make_line(
                    1,
                    order_source_ref,
                    availability=LineAvailability.IN_STOCK,
                    quantity_availability=QuantityAvailability.FULL,
                    explicitly_available=2,
                ),
                make_line(2, order_source_ref),
            ),
            geography=GeographyClass.INTERNATIONAL,
        )
        request = DOIEvaluationInput(
            evaluation_id=EvaluationId("SYN-EVALUATION-DOI-CONTACT-WORKFLOW"),
            snapshot=snapshot,
            evaluated_at=OBSERVED_AT,
        )
        evaluation = evaluate_doi(request)
        context, opening = open_context(
            snapshot,
            "CONTACT-WF",
            evaluation=evaluation,
            context_kind=ActionContextKind.CUSTOMER_CONTACT,
        )
        stream_id = EvidenceId("SYN-EVIDENCE-DOI-CONTACT-WF-STREAM")
        system_id = EvidenceId("SYN-EVIDENCE-DOI-CONTACT-WF-EVENT-SYSTEM")
        system_occurrence, system_source = interaction_source("CONTACT-WF-SYSTEM")
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
                occurrence_id=system_occurrence,
                source=system_source,
            ),
        )
        empty = ContactWorkflowHistory.empty(
            stream_id=stream_id,
            action_context=context,
        )
        required_reduction = reduce_contact_workflow(empty, required)
        self.assertEqual(
            required_reduction.history.projection.state,
            ContactWorkflowState.CONTACT_REQUIRED,
        )
        self.assertTrue(
            reduce_contact_workflow(required_reduction.history, required).replayed
        )

        def append_human(
            history: ContactWorkflowHistory,
            *,
            event_type: ContactWorkflowEventType,
            resulting_state: ContactWorkflowState,
            suffix: str,
        ) -> ContactWorkflowHistory:
            event_id = EvidenceId(f"SYN-EVIDENCE-DOI-CONTACT-WF-EVENT-{suffix}")
            occurrence, source = interaction_source(f"CONTACT-WF-{suffix}")
            authority = verify_synthetic_human_authority(
                grant_id=EvidenceId(
                    f"SYN-EVIDENCE-DOI-CONTACT-WF-AUTHORITY-{suffix}"
                ),
                actor=RepId("SYN-REP-DOI-CONTACT-WF-AUTHORIZED"),
                action_context=context,
                granted_at=OBSERVED_AT,
                authority_source=source,
            )
            event = ContactWorkflowEvent(
                event_id=event_id,
                stream_id=stream_id,
                action_context=context,
                prior_state=history.projection.state,
                resulting_state=resulting_state,
                event_type=event_type,
                evaluation=None,
                human_authority=authority,
                contact_occurred_at=OBSERVED_AT,
                recorded_at=OBSERVED_AT,
                sequence=len(history.events) + 1,
                predecessor_binding=(
                    None if not history.events else history.events[-1].hash_binding()
                ),
                guard=DOIOccurrenceGuard(
                    guard_id=event_id,
                    owner_id=stream_id,
                    occurrence_id=occurrence,
                    source=source,
                ),
            )
            return reduce_contact_workflow(history, event).history

        history = required_reduction.history
        steps = (
            (
                ContactWorkflowEventType.CONTACT_ATTEMPT_RECORDED,
                ContactWorkflowState.CONTACT_ATTEMPTED,
            ),
            (
                ContactWorkflowEventType.CONTACT_ATTEMPT_RECORDED,
                ContactWorkflowState.CONTACT_ATTEMPTED,
            ),
            (
                ContactWorkflowEventType.AWAITING_CUSTOMER_RECORDED,
                ContactWorkflowState.AWAITING_CUSTOMER,
            ),
            (
                ContactWorkflowEventType.CONTACT_ATTEMPT_RECORDED,
                ContactWorkflowState.CONTACT_ATTEMPTED,
            ),
            (
                ContactWorkflowEventType.AWAITING_CUSTOMER_RECORDED,
                ContactWorkflowState.AWAITING_CUSTOMER,
            ),
            (
                ContactWorkflowEventType.CUSTOMER_DECLINE_RECORDED,
                ContactWorkflowState.CUSTOMER_DECLINED,
            ),
            (
                ContactWorkflowEventType.CONTACT_ATTEMPT_RECORDED,
                ContactWorkflowState.CONTACT_ATTEMPTED,
            ),
            (
                ContactWorkflowEventType.AWAITING_CUSTOMER_RECORDED,
                ContactWorkflowState.AWAITING_CUSTOMER,
            ),
            (
                ContactWorkflowEventType.CUSTOMER_APPROVAL_RECORDED,
                ContactWorkflowState.CUSTOMER_APPROVED,
            ),
            (
                ContactWorkflowEventType.CUSTOMER_DECLINE_RECORDED,
                ContactWorkflowState.CUSTOMER_DECLINED,
            ),
            (
                ContactWorkflowEventType.CONTACT_ATTEMPT_RECORDED,
                ContactWorkflowState.CONTACT_ATTEMPTED,
            ),
            (
                ContactWorkflowEventType.CUSTOMER_DECLINE_RECORDED,
                ContactWorkflowState.CUSTOMER_DECLINED,
            ),
            (
                ContactWorkflowEventType.CONTACT_ATTEMPT_RECORDED,
                ContactWorkflowState.CONTACT_ATTEMPTED,
            ),
            (
                ContactWorkflowEventType.AWAITING_CUSTOMER_RECORDED,
                ContactWorkflowState.AWAITING_CUSTOMER,
            ),
            (
                ContactWorkflowEventType.NO_RESPONSE_RECORDED,
                ContactWorkflowState.NO_RESPONSE,
            ),
            (
                ContactWorkflowEventType.CONTACT_ATTEMPT_RECORDED,
                ContactWorkflowState.CONTACT_ATTEMPTED,
            ),
            (
                ContactWorkflowEventType.CUSTOMER_APPROVAL_RECORDED,
                ContactWorkflowState.CUSTOMER_APPROVED,
            ),
        )
        for index, (event_type, resulting_state) in enumerate(
            steps,
            start=1,
        ):
            history = append_human(
                history,
                event_type=event_type,
                resulting_state=resulting_state,
                suffix=f"{index:02d}",
            )

        direct_stream = EvidenceId("SYN-EVIDENCE-DOI-CONTACT-WF-DIRECT-STREAM")
        direct_empty = ContactWorkflowHistory.empty(
            stream_id=direct_stream,
            action_context=context,
        )
        event_id = EvidenceId("SYN-EVIDENCE-DOI-CONTACT-WF-DIRECT-EVENT")
        occurrence, source = interaction_source("CONTACT-WF-DIRECT")
        authority = verify_synthetic_human_authority(
            grant_id=EvidenceId("SYN-EVIDENCE-DOI-CONTACT-WF-DIRECT-AUTHORITY"),
            actor=RepId("SYN-REP-DOI-CONTACT-WF-AUTHORIZED"),
            action_context=context,
            granted_at=OBSERVED_AT,
            authority_source=source,
        )
        direct = ContactWorkflowEvent(
            event_id=event_id,
            stream_id=direct_stream,
            action_context=context,
            prior_state=ContactWorkflowState.NOT_CONTACTED,
            resulting_state=ContactWorkflowState.CONTACT_ATTEMPTED,
            event_type=ContactWorkflowEventType.CONTACT_ATTEMPT_RECORDED,
            evaluation=None,
            human_authority=authority,
            contact_occurred_at=OBSERVED_AT,
            recorded_at=OBSERVED_AT,
            sequence=1,
            predecessor_binding=None,
            guard=DOIOccurrenceGuard(
                guard_id=event_id,
                owner_id=direct_stream,
                occurrence_id=occurrence,
                source=source,
            ),
        )
        direct_history = reduce_contact_workflow(direct_empty, direct).history
        self.assertEqual(
            direct_history.projection.state,
            ContactWorkflowState.CONTACT_ATTEMPTED,
        )
        with self.assertRaisesRegex(
            DOIModelError,
            "DOI_CONTACT_WORKFLOW_EVENT_INVALID",
        ):
            dataclasses.replace(
                direct,
                event_type=ContactWorkflowEventType.CUSTOMER_APPROVAL_RECORDED,
                resulting_state=ContactWorkflowState.CUSTOMER_APPROVED,
            )
        conflicting_id = EvidenceId(
            "SYN-EVIDENCE-DOI-CONTACT-WF-DIRECT-CONFLICT"
        )
        conflicting = dataclasses.replace(
            direct,
            event_id=conflicting_id,
            prior_state=ContactWorkflowState.CONTACT_ATTEMPTED,
            sequence=2,
            predecessor_binding=direct.hash_binding(),
            guard=DOIOccurrenceGuard(
                guard_id=conflicting_id,
                owner_id=direct_stream,
                occurrence_id=occurrence,
                source=source,
            ),
        )
        with self.assertRaisesRegex(
            DOIModelError,
            "DOI_EVENT_REPLAY_CONFLICT",
        ):
            reduce_contact_workflow(direct_history, conflicting)
        self.assertFalse(hasattr(ContactWorkflowEvent, "send"))
        self.assertFalse(hasattr(ContactWorkflowReduction, "send"))

    def test_wwc_and_human_fact_correction_histories_are_exact(self) -> None:
        snapshot = ordinary_snapshot()
        stream_id = EvidenceId("SYN-EVIDENCE-DOI-WWC-STREAM-0001")
        first_id = EvidenceId("SYN-EVIDENCE-DOI-WWC-EVENT-0001")
        first_occurrence, first_source = interaction_source("WWC-0001")
        first = DOIWWCEvent(
            event_id=first_id,
            stream_id=stream_id,
            order_id=snapshot.order_id,
            event_type=WWCEventType.OBSERVED,
            finding=make_wwc(
                snapshot.wwc_finding.source,
                presence=FindingPresenceV2.PRESENT,
                author=WWCAuthorRelation.TARGET_REP,
                timing=WWCTimingState.ACTIVE,
                marker="WWC_MARKER",
                observed_at=OBSERVED_AT,
            ),
            corrects_event_id=None,
            recorded_at=OBSERVED_AT,
            sequence=1,
            predecessor_binding=None,
            guard=DOIOccurrenceGuard(
                guard_id=first_id,
                owner_id=stream_id,
                occurrence_id=first_occurrence,
                source=first_source,
            ),
        )
        first_reduction = reduce_wwc(
            DOIWWCHistory(stream_id=stream_id, order_id=snapshot.order_id),
            first,
        )
        self.assertEqual(
            first_reduction.history.projection.state,
            WWCProjectionState.ACTIVE_SELF,
        )
        self.assertTrue(reduce_wwc(first_reduction.history, first).replayed)

        context, context_opening = open_context(snapshot, "HUMAN-0001")
        actor = RepId("SYN-REP-DOI-AUTHORIZED-0001")
        human_occurrence, human_source = interaction_source("HUMAN-0001")
        authority = verify_synthetic_human_authority(
            grant_id=EvidenceId("SYN-EVIDENCE-DOI-AUTHORITY-0001"),
            actor=actor,
            action_context=context,
            granted_at=OBSERVED_AT,
            authority_source=human_source,
        )
        approved = StructuredHumanFact.create(
            fact_id=EvidenceId("SYN-EVIDENCE-DOI-HUMAN-FACT-0001"),
            action_context=context,
            evaluation_id=context.evaluation_id,
            usage_kind=HumanFactUsageKind.CUSTOMER_APPROVAL,
            result_code=HumanFactResultCode.APPROVED,
            authority_grant=authority,
            occurred_at=OBSERVED_AT,
            source=human_source,
        )
        _, different_source = interaction_source("HUMAN-DIFFERENT-SOURCE")
        completion_id = EvidenceId("SYN-EVIDENCE-DOI-HUMAN-CONTEXT-COMPLETE")
        completion = DOIActionContextEvent.completed(
            event_id=completion_id,
            action_context=context,
            completion_trigger=ActionContextCompletionTrigger.HUMAN_ACCEPTED,
            occurred_at=OBSERVED_AT,
            authority=authority,
            guard=DOIOccurrenceGuard(
                guard_id=completion_id,
                owner_id=context.action_context_id,
                occurrence_id=human_occurrence,
                source=human_source,
            ),
        )
        opened_history = reduce_action_context(
            DOIActionContextHistory(action_context_id=context.action_context_id),
            context_opening,
        ).history
        closed_context = reduce_action_context(
            opened_history,
            completion,
        ).history.projection
        invalid_human_fact_mutations = (
            {"source": different_source},
            {"occurred_at": CanonicalTimestamp("2026-08-20T14:15:15Z")},
            {"action_context": closed_context},
        )
        for mutation in invalid_human_fact_mutations:
            with self.subTest(mutation=tuple(mutation)):
                with self.assertRaisesRegex(
                    DOIModelError,
                    "STRUCTURED_HUMAN_FACT_INVALID",
                ):
                    dataclasses.replace(approved, **mutation)
        human_stream = EvidenceId("SYN-EVIDENCE-DOI-HUMAN-STREAM-0001")
        recorded_id = EvidenceId("SYN-EVIDENCE-DOI-HUMAN-EVENT-0001")
        recorded_occurrence, recorded_source = interaction_source("HUMAN-EVENT-0001")
        recorded = DOIHumanFactEvent(
            event_id=recorded_id,
            stream_id=human_stream,
            event_type=HumanFactEventType.RECORDED,
            fact=approved,
            corrects_event_id=None,
            recorded_at=OBSERVED_AT,
            sequence=1,
            predecessor_binding=None,
            guard=DOIOccurrenceGuard(
                guard_id=recorded_id,
                owner_id=human_stream,
                occurrence_id=recorded_occurrence,
                source=recorded_source,
            ),
        )
        recorded_reduction = reduce_human_fact(
            DOIHumanFactHistory(stream_id=human_stream),
            recorded,
        )
        rejected = dataclasses.replace(
            approved,
            fact_id=EvidenceId("SYN-EVIDENCE-DOI-HUMAN-FACT-0002"),
            result_code=HumanFactResultCode.REJECTED,
        )
        corrected_id = EvidenceId("SYN-EVIDENCE-DOI-HUMAN-EVENT-0002")
        corrected_occurrence, corrected_source = interaction_source("HUMAN-EVENT-0002")
        corrected = DOIHumanFactEvent(
            event_id=corrected_id,
            stream_id=human_stream,
            event_type=HumanFactEventType.CORRECTED,
            fact=rejected,
            corrects_event_id=recorded.event_id,
            recorded_at=OBSERVED_AT,
            sequence=2,
            predecessor_binding=recorded.hash_binding(),
            guard=DOIOccurrenceGuard(
                guard_id=corrected_id,
                owner_id=human_stream,
                occurrence_id=corrected_occurrence,
                source=corrected_source,
            ),
        )
        correction_reduction = reduce_human_fact(
            recorded_reduction.history,
            corrected,
        )
        self.assertEqual(
            correction_reduction.history.projection.current_fact.result_code,
            HumanFactResultCode.REJECTED,
        )
        for record in (
            first,
            first_reduction.history.projection,
            context,
            authority,
            approved,
            recorded,
            recorded_reduction.history.projection,
            rejected,
            corrected,
            correction_reduction.history.projection,
        ):
            self.assertEqual(
                model_hash_known_answer(record).sha256,
                record.hash_binding().sha256,
            )

    def test_hash_contract_inventory_is_closed_and_rule_pack_is_known_answer(self) -> None:
        contracts = model_hash_contracts()
        self.assertEqual(len(contracts), 37)
        self.assertEqual(contracts["DOIOrderSnapshot"], DOIOrderSnapshot.HASH_DOMAIN)
        fixtures = model_hash_fixtures()
        self.assertEqual(
            tuple(row[0] for row in fixtures),
            tuple(sorted(contracts)),
        )
        self.assertEqual(
            {row[1] for row in fixtures},
            set(contracts.values()),
        )
        for _, domain, canonical, digest in fixtures:
            preimage = domain.encode("ascii") + b"\n" + canonical
            self.assertEqual(hashlib.sha256(preimage).hexdigest(), digest)
        binding = rule_pack_hash_binding()
        self.assertEqual(
            binding.sha256,
            "aaa63f608d57bf49a8b5eda4294ef7f32b84aee6fae956b64a4327cc7da13789",
        )
        self.assertEqual(hashlib.sha256(binding.preimage).hexdigest(), binding.sha256)


if __name__ == "__main__":
    unittest.main()
