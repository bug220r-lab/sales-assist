from __future__ import annotations

import dataclasses
import unittest
from decimal import Decimal

from synthetic_sales_assist.doi.evaluator import (
    DOIEvaluationError,
    DOIRuleVersionUnavailable,
    assert_reason_route_legal,
    effective_reason_routes,
    construct_doi_money,
    evaluate_doi,
)
from synthetic_sales_assist.doi.knowledge import (
    DOIAlternateObservation,
    DOIExactSKUObservation,
    append_relationship_revision,
    candidate_from_relationship,
    create_relationship,
    exact_sku_candidate,
)
from synthetic_sales_assist.doi.models import (
    ActionContextKind,
    ActionContextEventType,
    AlternateAvailability,
    AlternateObservationState,
    AlternateRelationshipState,
    AlternateRelationshipType,
    AlternateResearchState,
    AlternateRevisionKind,
    AlternateValidityState,
    CompatibilityDecision,
    ContinuityProofType,
    DedupeEventType,
    DedupeState,
    DedupeVerificationFact,
    DOIActionContext,
    DOIActionContextEvent,
    DOIDedupeEvent,
    DOIDedupeHistory,
    DOIEvaluationInput,
    DOIMutualExclusionEvidence,
    DOIModelError,
    DOIOccurrenceGuard,
    DOIState,
    DropShipState,
    GeographyClass,
    HandlingFlag,
    HumanReviewKind,
    HumanFactResultCode,
    HumanFactUsageKind,
    LineAvailability,
    LineContinuityState,
    OpportunityType,
    OrderState,
    PaymentCondition,
    QuantityAvailability,
    RepRelation,
    ScenarioSelection,
    ScenarioSelectionState,
    SourcePresence,
    StructuredHumanFact,
    TerminalClosureReason,
    ValueAvailabilityState,
    WWCAuthorRelation,
    WWCTimingState,
    known_fact,
    model_hash_known_answer,
    not_applicable_fact,
    reduce_dedupe,
    unknown_fact,
    verify_synthetic_human_authority,
)
from synthetic_sales_assist.domain.canonical import canonical_json_bytes, domain_hash
from synthetic_sales_assist.domain.identities import (
    EvaluationId,
    EvidenceId,
    InteractionId,
    OrderId,
    RepId,
    SkuId,
)
from synthetic_sales_assist.domain.numeric import (
    CURRENCY_REGISTRY_VERSION,
    Money,
    PositiveQuantity,
)
from synthetic_sales_assist.domain.observed import FindingPresenceV2
from synthetic_sales_assist.domain.registries import (
    EXPECTED_OWNERSHIP_COUNT,
    EXPECTED_REASON_COUNT,
    EXPECTED_TRANSITION_COUNT,
    load_doi_registries,
)
from synthetic_sales_assist.domain.records import (
    SourceKind,
    SourceObjectNamespace,
    SourceRef,
)
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from tests.test_doi_models import (
    OBSERVED_AT,
    make_line,
    make_snapshot,
    open_context_fixture,
    order_source,
    usd,
)


def evaluation_input(
    lines: tuple[object, ...],
    *,
    evaluation_suffix: str = "0001",
    alternate_research_state: AlternateResearchState = AlternateResearchState.NOT_STARTED,
    alternate_candidates: tuple[object, ...] = (),
    scenario_selection: ScenarioSelection | None = None,
    human_facts: tuple[StructuredHumanFact, ...] = (),
    **snapshot_changes: object,
) -> DOIEvaluationInput:
    return DOIEvaluationInput(
        evaluation_id=EvaluationId(f"SYN-EVALUATION-DOI-{evaluation_suffix}"),
        snapshot=make_snapshot(lines, **snapshot_changes),  # type: ignore[arg-type]
        evaluated_at=OBSERVED_AT,
        alternate_research_state=alternate_research_state,
        alternate_candidates=alternate_candidates,  # type: ignore[arg-type]
        scenario_selection=scenario_selection,
        human_facts=human_facts,
    )


def human_fact(
    request: DOIEvaluationInput,
    *,
    usage: HumanFactUsageKind,
    result: HumanFactResultCode,
    suffix: str = "0001",
    opportunity_id: EvidenceId | None = None,
) -> StructuredHumanFact:
    selected_opportunity = None
    if opportunity_id is not None:
        owner_snapshot = request.snapshot
        owner_evaluation = evaluate_doi(request)
        selected_opportunity = next(
            item
            for item in owner_evaluation.opportunities
            if item.opportunity_id == opportunity_id
        )
        if selected_opportunity.opportunity_type in {
            OpportunityType.EXACT_SKU_RECHECK,
            OpportunityType.PARTIAL_QUANTITY_REVIEW,
        }:
            selected_opportunity = None
        else:
            context_kind = (
                ActionContextKind.FULFILLMENT_SPLIT_REVIEW
                if selected_opportunity.opportunity_type
                is OpportunityType.FULFILLMENT_SPLIT
                else (
                    ActionContextKind.DS_SEPARATION_REVIEW
                    if selected_opportunity.opportunity_type
                    is OpportunityType.DS_SEPARATION
                    else ActionContextKind.SUBSTITUTION
                )
            )
    if selected_opportunity is None:
        fact_source = order_source(OrderId("SYN-ORDER-DOI-0001"))
        owner_snapshot = make_snapshot(
            (
                make_line(
                    1,
                    fact_source,
                    availability=LineAvailability.IN_STOCK,
                    quantity_availability=QuantityAvailability.FULL,
                    explicitly_available=2,
                ),
                make_line(2, fact_source),
            ),
            snapshot_suffix=f"HUMAN-{suffix}",
            run_suffix=f"HUMAN-{suffix}",
        )
        owner_request = DOIEvaluationInput(
            evaluation_id=request.evaluation_id,
            snapshot=owner_snapshot,
            evaluated_at=OBSERVED_AT,
        )
        owner_evaluation = evaluate_doi(owner_request)
        context_kind = ActionContextKind.FULFILLMENT_SPLIT_REVIEW
    context, _, _, _, _, _ = open_context_fixture(
        owner_snapshot,
        f"EVAL-{suffix}",
        evaluation=owner_evaluation,
        opportunity=selected_opportunity,
        context_kind=context_kind,
    )
    interaction_id = InteractionId(f"SYN-INTERACTION-DOI-HUMAN-{suffix}")
    source = SourceRef.create(
        source_ref_id=EvidenceId(f"SYN-EVIDENCE-DOI-HUMAN-SOURCE-{suffix}"),
        source_kind=SourceKind.SYNTHETIC_INTERACTION_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_INTERACTION,
        object_id=interaction_id,
    )
    actor = RepId("SYN-REP-DOI-AUTHORIZED-0001")
    authority = verify_synthetic_human_authority(
        grant_id=EvidenceId(f"SYN-EVIDENCE-DOI-AUTHORITY-GRANT-{suffix}"),
        actor=actor,
        action_context=context,
        granted_at=OBSERVED_AT,
        authority_source=source,
    )
    return StructuredHumanFact.create(
        fact_id=EvidenceId(f"SYN-EVIDENCE-DOI-HUMAN-FACT-{suffix}"),
        action_context=context,
        evaluation_id=request.evaluation_id,
        usage_kind=usage,
        result_code=result,
        authority_grant=authority,
        occurred_at=OBSERVED_AT,
        source=source,
    )


def split_lines(*, third: object | None = None) -> tuple[object, ...]:
    source = order_source(OrderId("SYN-ORDER-DOI-0001"))
    lines: list[object] = [
        make_line(
            1,
            source,
            availability=LineAvailability.IN_STOCK,
            quantity_availability=QuantityAvailability.FULL,
            explicitly_available=2,
        ),
        make_line(2, source),
    ]
    if third is not None:
        lines.append(third)
    return tuple(lines)


def exact_observation(
    request: DOIEvaluationInput,
    *,
    line_index: int = 0,
    suffix: str = "0001",
) -> DOIExactSKUObservation:
    line = request.snapshot.lines[line_index]
    context = human_fact(
        request,
        usage=HumanFactUsageKind.NO_ACTION_DECISION,
        result=HumanFactResultCode.APPROVED,
        suffix=f"OBS-{suffix}",
    ).action_context
    sku = SkuId(f"SYN-SKU-DOI-ES-{line_index + 1:04d}")
    source = SourceRef.create(
        source_ref_id=EvidenceId(f"SYN-EVIDENCE-DOI-EXACT-SOURCE-{suffix}"),
        source_kind=SourceKind.SYNTHETIC_PRODUCT_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_PRODUCT,
        object_id=sku,
    )
    return DOIExactSKUObservation(
        observation_id=EvidenceId(f"SYN-EVIDENCE-DOI-EXACT-OBSERVATION-{suffix}"),
        action_context_id=context.action_context_id,
        action_context_binding=context.hash_binding(),
        ordered_line_id=line.line_snapshot_id,
        ordered_sku=sku,
        observed_sku=sku,
        state=AlternateObservationState.CURRENT,
        observed_availability=AlternateAvailability.IN_STOCK,
        potential_unit_value=usd("10.00"),
        observed_at=OBSERVED_AT,
        source=source,
    )


def relationship_candidate(
    request: DOIEvaluationInput,
    *,
    relationship_type: AlternateRelationshipType,
    compatibility: CompatibilityDecision,
    suffix: str,
    observation_state: AlternateObservationState = AlternateObservationState.CURRENT,
    terminal_state: AlternateRelationshipState | None = None,
    review_required: bool | None = None,
    unknown_observation_reason: str | None = None,
):
    line = request.snapshot.lines[0]
    ordered_sku = line.es_number.value
    ordered_mfg = line.mfg_number.value
    assert isinstance(ordered_sku, SkuId)
    assert isinstance(ordered_mfg, SkuId)
    candidate_sku = SkuId(f"SYN-SKU-DOI-ALTERNATE-{suffix}")
    candidate_mfg = (
        ordered_mfg
        if relationship_type is AlternateRelationshipType.EXACT_MFG
        else SkuId(f"SYN-SKU-DOI-ALTERNATE-MFG-{suffix}")
    )
    product_source = SourceRef.create(
        source_ref_id=EvidenceId(f"SYN-EVIDENCE-DOI-ALT-SOURCE-{suffix}"),
        source_kind=SourceKind.SYNTHETIC_PRODUCT_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_PRODUCT,
        object_id=candidate_sku,
    )
    requires_review = (
        relationship_type is AlternateRelationshipType.FUNCTIONAL
        if review_required is None
        else review_required
    )
    relation = create_relationship(
        relationship_id=EvidenceId(f"SYN-EVIDENCE-DOI-RELATIONSHIP-{suffix}"),
        revision_id=EvidenceId(f"SYN-EVIDENCE-DOI-RELATIONSHIP-REV-{suffix}"),
        relationship_type=relationship_type,
        ordered_sku=ordered_sku,
        candidate_sku=candidate_sku,
        ordered_mfg=ordered_mfg,
        candidate_mfg=candidate_mfg,
        compatibility_review_required=requires_review,
        evidence_source=product_source,
    )
    if terminal_state is not None:
        revision_kind = {
            AlternateRelationshipState.SUPERSEDED: AlternateRevisionKind.SUPERSEDED,
            AlternateRelationshipState.INVALIDATED: AlternateRevisionKind.INVALIDATED,
        }[terminal_state]
        relation = append_relationship_revision(
            relation,
            revision_id=EvidenceId(
                f"SYN-EVIDENCE-DOI-RELATIONSHIP-TERM-{suffix}"
            ),
            revision_kind=revision_kind,
            state=terminal_state,
            compatibility_review_required=requires_review,
            evidence_source=product_source,
        )
    context = human_fact(
        request,
        usage=HumanFactUsageKind.NO_ACTION_DECISION,
        result=HumanFactResultCode.APPROVED,
        suffix=f"ALT-{suffix}",
    ).action_context
    observation = DOIAlternateObservation(
        observation_id=EvidenceId(f"SYN-EVIDENCE-DOI-ALT-OBS-{suffix}"),
        action_context_id=context.action_context_id,
        action_context_binding=context.hash_binding(),
        relationship_revision_binding=relation.current_revision.hash_binding(),
        candidate_sku=candidate_sku,
        state=observation_state,
        observed_availability=(
            unknown_fact("RC-137")
            if unknown_observation_reason == "RC-137"
            else known_fact(AlternateAvailability.IN_STOCK)
        ),
        observed_eta=(
            unknown_fact("RC-138")
            if unknown_observation_reason == "RC-138"
            else not_applicable_fact()
        ),
        observed_price=(
            unknown_fact("RC-136")
            if unknown_observation_reason == "RC-136"
            else known_fact(usd("10.00"))
        ),
        observed_at=OBSERVED_AT,
        source=product_source,
    )
    candidate = candidate_from_relationship(
        candidate_id=EvidenceId(f"SYN-EVIDENCE-DOI-ALT-CANDIDATE-{suffix}"),
        relationship=relation,
        observation=observation,
        ordered_line_id=line.line_snapshot_id,
        quantity=PositiveQuantity(1),
        compatibility_decision=compatibility,
    )
    return candidate


def occurrence_guard(
    *,
    owner_id: EvidenceId,
    event_id: EvidenceId,
    suffix: str,
) -> DOIOccurrenceGuard:
    occurrence = InteractionId(f"SYN-INTERACTION-DOI-EVENT-{suffix}")
    source = SourceRef.create(
        source_ref_id=EvidenceId(f"SYN-EVIDENCE-DOI-EVENT-SOURCE-{suffix}"),
        source_kind=SourceKind.SYNTHETIC_INTERACTION_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_INTERACTION,
        object_id=occurrence,
    )
    return DOIOccurrenceGuard(
        guard_id=event_id,
        owner_id=owner_id,
        occurrence_id=occurrence,
        source=source,
    )


class DOIEvaluatorOverlayTests(unittest.TestCase):
    def test_known_split_preserved_with_unrelated_unknown_availability(self) -> None:
        source = order_source(OrderId("SYN-ORDER-DOI-0001"))
        unknown_line = make_line(
            3,
            source,
            availability=unknown_fact("RC-016"),
            quantity_availability=QuantityAvailability.NONE,
        )
        result = evaluate_doi(evaluation_input(split_lines(third=unknown_line)))
        self.assertEqual(result.state, DOIState.DOI_OPPORTUNITY)
        self.assertEqual(result.transition.transition_id, "TR-034")
        self.assertEqual(
            {item.opportunity_type for item in result.opportunities},
            {OpportunityType.FULFILLMENT_SPLIT},
        )
        self.assertIn("RC-016", {reason.code for reason in result.reasons.reasons})
        route = next(item for item in result.reason_routes if item.reason.code == "RC-016")
        self.assertEqual(route.owning_transition.transition_id, "TR-034")
        self.assertTrue(route.effective_overlay)
        self.assertIn(
            HumanReviewKind.UNKNOWN_FACT,
            result.human_review_requirements,
        )

    def test_known_split_preserved_with_unrelated_unknown_ds_state(self) -> None:
        source = order_source(OrderId("SYN-ORDER-DOI-0001"))
        unknown_line = make_line(
            3,
            source,
            drop_ship=unknown_fact("RC-017"),
            availability=LineAvailability.DELAYED,
            quantity_availability=QuantityAvailability.NONE,
        )
        result = evaluate_doi(evaluation_input(split_lines(third=unknown_line)))
        self.assertEqual(result.state, DOIState.DOI_OPPORTUNITY)
        self.assertEqual(result.transition.transition_id, "TR-034")
        route = next(item for item in result.reason_routes if item.reason.code == "RC-017")
        self.assertEqual(route.owning_transition.transition_id, "TR-034")

    def test_unknown_that_blocks_only_candidate_routes_to_tr037(self) -> None:
        source = order_source(OrderId("SYN-ORDER-DOI-0001"))
        lines = (
            make_line(
                1,
                source,
                availability=LineAvailability.IN_STOCK,
                quantity_availability=QuantityAvailability.FULL,
                explicitly_available=2,
            ),
            make_line(
                2,
                source,
                availability=unknown_fact("RC-016"),
                quantity_availability=QuantityAvailability.NONE,
            ),
        )
        result = evaluate_doi(evaluation_input(lines))
        self.assertEqual(result.state, DOIState.DOI_MANUAL_REVIEW)
        self.assertEqual(result.transition.transition_id, "TR-037")
        self.assertEqual(result.opportunities, ())

    def test_overlapping_opportunities_survive_and_withhold_aggregate(self) -> None:
        request = evaluation_input(split_lines())
        split_result = evaluate_doi(request)
        exact = exact_sku_candidate(
            candidate_id=EvidenceId("SYN-EVIDENCE-DOI-CANDIDATE-0001"),
            quantity=PositiveQuantity(1),
            observation=exact_observation(request),
        )
        overlapped_request = evaluation_input(
            split_lines(),
            alternate_candidates=(exact,),
        )
        overlapped = evaluate_doi(overlapped_request)
        for record in (
            overlapped_request,
            exact,
            *overlapped.opportunities,
            *(item.scope for item in overlapped.opportunities),
            overlapped.explanation,
            overlapped,
        ):
            with self.subTest(hash_record=type(record).__name__):
                known_answer = model_hash_known_answer(record)
                self.assertEqual(
                    known_answer.sha256,
                    record.hash_binding().sha256,
                )
        self.assertEqual(overlapped.state, DOIState.DOI_OPPORTUNITY)
        self.assertEqual(len(split_result.opportunities), 1)
        self.assertEqual(len(overlapped.opportunities), 2)
        self.assertEqual(
            overlapped.aggregate_potential_state,
            ValueAvailabilityState.UNAVAILABLE,
        )
        self.assertIsNone(overlapped.aggregate_potential)
        self.assertEqual(
            overlapped.scenario_selection_state,
            ScenarioSelectionState.REQUIRED,
        )
        self.assertIn("RC-087", {reason.code for reason in overlapped.reasons.reasons})
        self.assertIn(
            HandlingFlag.HUMAN_SCENARIO_SELECTION_REQUIRED,
            overlapped.handling_flags,
        )
        self.assertIn(
            HumanReviewKind.SCENARIO_SELECTION,
            overlapped.human_review_requirements,
        )

        selected = next(
            item
            for item in overlapped.opportunities
            if item.opportunity_type is OpportunityType.EXACT_SKU_RECHECK
        )
        selection_base = evaluation_input(
            split_lines(),
            alternate_candidates=(exact,),
        )
        selection_fact = human_fact(
            selection_base,
            usage=HumanFactUsageKind.SCENARIO_SELECTION,
            result=HumanFactResultCode.SCENARIO_SELECTED,
            opportunity_id=selected.opportunity_id,
        )
        selection = ScenarioSelection(
            selection_id=EvidenceId("SYN-EVIDENCE-DOI-SELECTION-0001"),
            selected_opportunity_id=selected.opportunity_id,
            option_opportunity_ids=tuple(
                sorted(
                    (item.opportunity_id for item in overlapped.opportunities),
                    key=lambda item: item.value,
                )
            ),
            human_fact_binding=selection_fact.hash_binding(),
        )
        resolved = evaluate_doi(
            evaluation_input(
                split_lines(),
                alternate_candidates=(exact,),
                scenario_selection=selection,
                human_facts=(selection_fact,),
            )
        )
        self.assertEqual(
            resolved.scenario_selection_state,
            ScenarioSelectionState.SELECTED,
        )
        self.assertEqual(
            resolved.aggregate_potential_state,
            ValueAvailabilityState.AVAILABLE,
        )
        self.assertEqual(resolved.aggregate_potential, usd("10.00"))
        self.assertNotIn("RC-087", {reason.code for reason in resolved.reasons.reasons})
        conflicting_options = tuple(
            sorted(
                (
                    selected.opportunity_id,
                    EvidenceId("SYN-EVIDENCE-DOI-UNRELATED-OPTION"),
                ),
                key=lambda item: item.value,
            )
        )
        conflicting_selection = dataclasses.replace(
            selection,
            option_opportunity_ids=conflicting_options,
        )
        with self.assertRaises(DOIEvaluationError) as selection_error:
            evaluate_doi(
                evaluation_input(
                    split_lines(),
                    alternate_candidates=(exact,),
                    scenario_selection=conflicting_selection,
                    human_facts=(selection_fact,),
                )
            )
        self.assertEqual(
            tuple(
                reason.code
                for reason in selection_error.exception.reasons.reasons
            ),
            ("RC-098",),
        )

    def test_scenario_selection_rejects_invalid_human_fact_provenance(self) -> None:
        request = evaluation_input(split_lines())
        exact = exact_sku_candidate(
            candidate_id=EvidenceId("SYN-EVIDENCE-DOI-CANDIDATE-PROVENANCE"),
            quantity=PositiveQuantity(1),
            observation=exact_observation(request, suffix="PROVENANCE"),
        )
        unresolved_request = evaluation_input(
            split_lines(),
            alternate_candidates=(exact,),
        )
        unresolved = evaluate_doi(unresolved_request)
        self.assertEqual(
            unresolved.scenario_selection_state,
            ScenarioSelectionState.REQUIRED,
        )
        self.assertEqual(
            unresolved.aggregate_potential_state,
            ValueAvailabilityState.UNAVAILABLE,
        )
        selected = unresolved.opportunities[0]
        valid_fact = human_fact(
            unresolved_request,
            usage=HumanFactUsageKind.SCENARIO_SELECTION,
            result=HumanFactResultCode.SCENARIO_SELECTED,
            suffix="PROVENANCE",
            opportunity_id=selected.opportunity_id,
        )
        different_interaction = InteractionId(
            "SYN-INTERACTION-DOI-HUMAN-PROVENANCE-OTHER"
        )
        different_source = SourceRef.create(
            source_ref_id=EvidenceId(
                "SYN-EVIDENCE-DOI-HUMAN-SOURCE-PROVENANCE-OTHER"
            ),
            source_kind=SourceKind.SYNTHETIC_INTERACTION_FIXTURE,
            object_namespace=SourceObjectNamespace.SYNTHETIC_INTERACTION,
            object_id=different_interaction,
        )
        for mutation in (
            {"source": different_source},
            {"occurred_at": CanonicalTimestamp("2026-08-20T14:15:15Z")},
        ):
            with self.subTest(mutation=tuple(mutation)):
                with self.assertRaisesRegex(
                    DOIModelError,
                    "STRUCTURED_HUMAN_FACT_INVALID",
                ):
                    dataclasses.replace(valid_fact, **mutation)

        rejected_selection = ScenarioSelection(
            selection_id=EvidenceId(
                "SYN-EVIDENCE-DOI-SELECTION-PROVENANCE-REJECTED"
            ),
            selected_opportunity_id=selected.opportunity_id,
            option_opportunity_ids=tuple(
                sorted(
                    (item.opportunity_id for item in unresolved.opportunities),
                    key=lambda item: item.value,
                )
            ),
            human_fact_binding=valid_fact.hash_binding(),
        )
        with self.assertRaisesRegex(
            DOIModelError,
            "DOI_SCENARIO_SELECTION_FACT_INVALID",
        ):
            evaluation_input(
                split_lines(),
                alternate_candidates=(exact,),
                scenario_selection=rejected_selection,
                human_facts=(),
            )

    def test_disjoint_mutually_exclusive_options_require_scenario_selection(self) -> None:
        source = order_source(OrderId("SYN-ORDER-DOI-0001"))
        lines = (make_line(1, source), make_line(2, source))
        base = evaluation_input(lines, evaluation_suffix="DISJOINT")
        group = EvidenceId("SYN-EVIDENCE-DOI-SCENARIO-GROUP-DISJOINT")
        ungrouped_candidates = tuple(
            exact_sku_candidate(
                candidate_id=EvidenceId(
                    f"SYN-EVIDENCE-DOI-DISJOINT-CANDIDATE-{index + 1:04d}"
                ),
                quantity=PositiveQuantity(1),
                observation=exact_observation(
                    base,
                    line_index=index,
                    suffix=f"DISJOINT-{index + 1:04d}",
                ),
            )
            for index in range(2)
        )
        grouping_fact = human_fact(
            base,
            usage=HumanFactUsageKind.SCENARIO_GROUPING,
            result=HumanFactResultCode.SCENARIO_GROUPED,
            suffix="DISJOINT-GROUP",
        )
        grouping_evidence = DOIMutualExclusionEvidence(
            evidence_id=EvidenceId(
                "SYN-EVIDENCE-DOI-SCENARIO-GROUP-EVIDENCE-DISJOINT"
            ),
            group_id=group,
            candidate_ids=tuple(
                sorted(
                    (item.candidate_id for item in ungrouped_candidates),
                    key=lambda item: item.value,
                )
            ),
            human_fact=grouping_fact,
        )
        candidates = tuple(
            dataclasses.replace(
                candidate,
                mutual_exclusion_group=group,
                mutual_exclusion_evidence=grouping_evidence,
            )
            for candidate in ungrouped_candidates
        )

        with self.assertRaisesRegex(
            DOIEvaluationError,
            "MUTUAL_EXCLUSION_EVIDENCE_INVALID",
        ) as incomplete:
            evaluate_doi(
                evaluation_input(
                    lines,
                    evaluation_suffix="DISJOINT",
                    alternate_candidates=candidates,
                )
            )
        self.assertEqual(
            tuple(reason.code for reason in incomplete.exception.reasons.reasons),
            ("RC-105",),
        )
        unresolved_request = evaluation_input(
            lines,
            evaluation_suffix="DISJOINT",
            alternate_candidates=candidates,
            human_facts=(grouping_fact,),
        )
        unresolved = evaluate_doi(unresolved_request)
        self.assertFalse(
            unresolved.opportunities[0].scope.line_ids
            & unresolved.opportunities[1].scope.line_ids
        )
        self.assertEqual(
            {item.mutual_exclusion_group for item in unresolved.opportunities},
            {group},
        )
        self.assertEqual(
            unresolved.scenario_selection_state,
            ScenarioSelectionState.REQUIRED,
        )
        self.assertEqual(
            unresolved.aggregate_potential_state,
            ValueAvailabilityState.UNAVAILABLE,
        )
        self.assertIn("RC-087", {item.code for item in unresolved.reasons.reasons})

        selected = unresolved.opportunities[0]
        selection_fact = human_fact(
            unresolved_request,
            usage=HumanFactUsageKind.SCENARIO_SELECTION,
            result=HumanFactResultCode.SCENARIO_SELECTED,
            suffix="DISJOINT-SELECT",
            opportunity_id=selected.opportunity_id,
        )
        selection = ScenarioSelection(
            selection_id=EvidenceId("SYN-EVIDENCE-DOI-DISJOINT-SELECTION"),
            selected_opportunity_id=selected.opportunity_id,
            option_opportunity_ids=tuple(
                sorted(
                    (item.opportunity_id for item in unresolved.opportunities),
                    key=lambda item: item.value,
                )
            ),
            human_fact_binding=selection_fact.hash_binding(),
        )
        resolved = evaluate_doi(
            DOIEvaluationInput(
                evaluation_id=unresolved_request.evaluation_id,
                snapshot=unresolved_request.snapshot,
                evaluated_at=unresolved_request.evaluated_at,
                alternate_candidates=candidates,
                scenario_selection=selection,
                human_facts=tuple(
                    sorted(
                        (grouping_fact, selection_fact),
                        key=lambda item: item.fact_id.value,
                    )
                ),
            )
        )
        self.assertEqual(
            resolved.scenario_selection_state,
            ScenarioSelectionState.SELECTED,
        )
        self.assertEqual(
            resolved.aggregate_potential_state,
            ValueAvailabilityState.AVAILABLE,
        )

    def test_effective_ownership_overlay_is_exact_and_registry_counts_unchanged(self) -> None:
        registries = load_doi_registries()
        routes = effective_reason_routes(registries)
        self.assertEqual(len(registries.reason_refs), EXPECTED_REASON_COUNT)
        self.assertEqual(len(routes), EXPECTED_OWNERSHIP_COUNT)
        self.assertEqual(len(registries.transition_refs), EXPECTED_TRANSITION_COUNT)
        self.assertEqual(
            {item.transition_id for item in routes["RC-016"]},
            {"TR-027", "TR-028", "TR-033", "TR-034", "TR-035", "TR-037"},
        )
        self.assertEqual(
            {item.transition_id for item in routes["RC-017"]},
            {"TR-027", "TR-028", "TR-033", "TR-034", "TR-035", "TR-037"},
        )
        for code in ("RC-018", "RC-115", "RC-116"):
            self.assertEqual(
                {item.transition_id for item in routes[code]},
                {"TR-027", "TR-028", "TR-033", "TR-034", "TR-035", "TR-037"},
            )
        self.assertEqual(
            {item.transition_id for item in routes["RC-087"]},
            {"TR-033", "TR-034", "TR-035"},
        )
        assert_reason_route_legal("RC-087", registries.transition_ref("TR-034"))
        with self.assertRaises(DOIEvaluationError):
            assert_reason_route_legal("RC-087", registries.transition_ref("TR-037"))

    def test_every_emission_has_an_exact_effective_legal_route(self) -> None:
        source = order_source(OrderId("SYN-ORDER-DOI-0001"))
        unknown_line = make_line(
            3,
            source,
            availability=unknown_fact("RC-016"),
            drop_ship=unknown_fact("RC-017"),
            eta=unknown_fact("RC-115"),
            quantity_availability=QuantityAvailability.NONE,
        )
        result = evaluate_doi(evaluation_input(split_lines(third=unknown_line)))
        executed = {result.transition, *result.append_transitions}
        for route in result.reason_routes:
            assert_reason_route_legal(route.reason, route.owning_transition)
            if route.owning_transition is not None:
                self.assertIn(route.owning_transition, executed)

    def test_unknown_continuity_routes_to_actual_opportunity_not_tr037(self) -> None:
        lines = split_lines()
        unverified = dataclasses.replace(
            lines[0].continuity,
            state=type(lines[0].continuity.state).UNVERIFIED,
            proof_type=type(lines[0].continuity.proof_type).NONE,
            stable_source_line_id=None,
        )
        first = dataclasses.replace(
            lines[0],
            stable_source_line_id=unknown_fact("RC-124"),
            continuity=unverified,
        )
        result = evaluate_doi(evaluation_input((first, lines[1])))
        route = next(item for item in result.reason_routes if item.reason.code == "RC-018")
        self.assertEqual(result.transition.transition_id, "TR-034")
        self.assertEqual(route.owning_transition, result.transition)
        self.assertNotEqual(route.owning_transition.transition_id, "TR-037")
        with self.assertRaisesRegex(ValueError, "DOI_REASON_ROUTE_NOT_EXECUTED"):
            dataclasses.replace(
                result,
                append_transitions=(result.append_transition,),
            )

    def test_unknown_order_state_routes_to_actual_independent_split(self) -> None:
        result = evaluate_doi(
            evaluation_input(
                split_lines(),
                order_state=unknown_fact("RC-116"),
            )
        )
        route = next(item for item in result.reason_routes if item.reason.code == "RC-116")
        self.assertEqual(result.transition.transition_id, "TR-034")
        self.assertEqual(route.owning_transition, result.transition)
        self.assertTrue(route.effective_overlay)
        self.assertIn(
            HumanReviewKind.UNKNOWN_FACT,
            result.human_review_requirements,
        )

    def test_isolated_order_rep_and_payment_unknowns_require_manual_review(self) -> None:
        source = order_source(OrderId("SYN-ORDER-DOI-0001"))
        full_line = make_line(
            1,
            source,
            availability=LineAvailability.IN_STOCK,
            quantity_availability=QuantityAvailability.FULL,
            explicitly_available=2,
        )
        base = evaluation_input((full_line,))
        cases = (
            ("order_state", "RC-116"),
            ("current_rep_relation", "RC-118"),
            ("payment_condition", "RC-120"),
        )
        for field_name, reason_code in cases:
            with self.subTest(field=field_name):
                snapshot = dataclasses.replace(
                    base.snapshot,
                    **{field_name: unknown_fact(reason_code)},
                )
                result = evaluate_doi(dataclasses.replace(base, snapshot=snapshot))
                codes = {reason.code for reason in result.reasons.reasons}
                self.assertEqual(result.state, DOIState.DOI_MANUAL_REVIEW)
                self.assertEqual(result.transition.transition_id, "TR-037")
                self.assertIn(reason_code, codes)
                self.assertNotIn("RC-028", codes)
                self.assertFalse(result.opportunities)
                self.assertIn(
                    HumanReviewKind.UNKNOWN_FACT,
                    result.human_review_requirements,
                )

    def test_multiple_independent_unknowns_emit_the_exact_set_union(self) -> None:
        source = order_source(OrderId("SYN-ORDER-DOI-0001"))
        line = make_line(
            1,
            source,
            availability=unknown_fact("RC-016"),
            drop_ship=unknown_fact("RC-017"),
            eta=unknown_fact("RC-115"),
            quantity_availability=QuantityAvailability.NONE,
        )
        base = evaluation_input((line,))
        snapshot = dataclasses.replace(
            base.snapshot,
            order_total=unknown_fact("RC-121"),
            wwc_finding=dataclasses.replace(
                base.snapshot.wwc_finding,
                presence=FindingPresenceV2.UNKNOWN,
            ),
            dedupe_finding=dataclasses.replace(
                base.snapshot.dedupe_finding,
                presence=FindingPresenceV2.UNKNOWN,
            ),
        )
        result = evaluate_doi(
            DOIEvaluationInput(
                evaluation_id=base.evaluation_id,
                snapshot=snapshot,
                evaluated_at=base.evaluated_at,
            )
        )
        self.assertEqual(result.transition.transition_id, "TR-037")
        self.assertEqual(
            {reason.code for reason in result.reasons.reasons},
            {"RC-016", "RC-017", "RC-115", "RC-121", "RC-122", "RC-123"},
        )

    def test_full_ds_retains_unrelated_unknown_via_append_route(self) -> None:
        source = order_source(OrderId("SYN-ORDER-DOI-0001"))
        line = make_line(
            1,
            source,
            drop_ship=DropShipState.DS,
            availability=unknown_fact("RC-016"),
            quantity_availability=QuantityAvailability.FULL,
            explicitly_available=2,
        )
        result = evaluate_doi(evaluation_input((line,)))
        self.assertEqual(result.transition.transition_id, "TR-031")
        self.assertEqual(result.state, DOIState.DOI_EXCLUDED)
        route = next(item for item in result.reason_routes if item.reason.code == "RC-016")
        self.assertEqual(route.owning_transition.transition_id, "TR-027")
        self.assertEqual(result.opportunities, ())

    def test_structured_no_action_preserves_monitor_for_unrelated_unknown_only(self) -> None:
        source = order_source(OrderId("SYN-ORDER-DOI-0001"))
        base = evaluation_input((make_line(1, source),))
        unrelated_snapshot = dataclasses.replace(
            base.snapshot,
            order_total=unknown_fact("RC-121"),
        )
        unrelated_base = DOIEvaluationInput(
            evaluation_id=base.evaluation_id,
            snapshot=unrelated_snapshot,
            evaluated_at=base.evaluated_at,
        )
        fact = human_fact(
            unrelated_base,
            usage=HumanFactUsageKind.NO_ACTION_DECISION,
            result=HumanFactResultCode.APPROVED,
        )
        monitor = evaluate_doi(
            DOIEvaluationInput(
                evaluation_id=unrelated_base.evaluation_id,
                snapshot=unrelated_snapshot,
                evaluated_at=unrelated_base.evaluated_at,
                human_facts=(fact,),
            )
        )
        self.assertEqual(monitor.state, DOIState.DOI_MONITOR)
        self.assertEqual(monitor.transition.transition_id, "TR-039")
        self.assertTrue(
            {"RC-029", "RC-121"}.issubset(
                {reason.code for reason in monitor.reasons.reasons}
            )
        )

        dependent_line = make_line(
            1,
            source,
            availability=unknown_fact("RC-016"),
            quantity_availability=QuantityAvailability.NONE,
        )
        dependent_base = evaluation_input((dependent_line,), evaluation_suffix="0002")
        dependent_fact = human_fact(
            dependent_base,
            usage=HumanFactUsageKind.NO_ACTION_DECISION,
            result=HumanFactResultCode.APPROVED,
            suffix="0002",
        )
        blocked = evaluate_doi(
            DOIEvaluationInput(
                evaluation_id=dependent_base.evaluation_id,
                snapshot=dependent_base.snapshot,
                evaluated_at=dependent_base.evaluated_at,
                human_facts=(dependent_fact,),
            )
        )
        self.assertEqual(blocked.transition.transition_id, "TR-037")

    def test_every_field_specific_unknown_reason_is_emitted_by_actual_evaluation(self) -> None:
        base = evaluation_input(split_lines())
        order_fields = (
            ("order_state", "RC-116"),
            ("current_rep_value", "RC-117"),
            ("current_rep_relation", "RC-118"),
            ("geography_class", "RC-119"),
            ("payment_condition", "RC-120"),
            ("order_total", "RC-121"),
        )
        for field_name, reason_code in order_fields:
            with self.subTest(field=field_name):
                snapshot = dataclasses.replace(
                    base.snapshot,
                    **{field_name: unknown_fact(reason_code)},
                )
                result = evaluate_doi(dataclasses.replace(base, snapshot=snapshot))
                self.assertEqual(result.state, DOIState.DOI_OPPORTUNITY)
                self.assertIn(
                    reason_code,
                    {reason.code for reason in result.reasons.reasons},
                )

        finding_snapshots = (
            (
                "RC-122",
                dataclasses.replace(
                    base.snapshot,
                    wwc_finding=dataclasses.replace(
                        base.snapshot.wwc_finding,
                        presence=FindingPresenceV2.UNKNOWN,
                    ),
                ),
            ),
            (
                "RC-123",
                dataclasses.replace(
                    base.snapshot,
                    dedupe_finding=dataclasses.replace(
                        base.snapshot.dedupe_finding,
                        presence=FindingPresenceV2.UNKNOWN,
                    ),
                ),
            ),
        )
        for reason_code, snapshot in finding_snapshots:
            with self.subTest(finding=reason_code):
                result = evaluate_doi(dataclasses.replace(base, snapshot=snapshot))
                self.assertEqual(result.state, DOIState.DOI_OPPORTUNITY)
                self.assertIn(
                    reason_code,
                    {reason.code for reason in result.reasons.reasons},
                )

        source = order_source(OrderId("SYN-ORDER-DOI-0001"))
        line_fields = (
            ("eta", "RC-115"),
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
        for field_name, reason_code in line_fields:
            with self.subTest(field=field_name):
                third = make_line(3, source)
                changes: dict[str, object] = {
                    field_name: unknown_fact(reason_code),
                }
                if field_name == "stable_source_line_id":
                    changes["continuity"] = dataclasses.replace(
                        third.continuity,
                        state=LineContinuityState.UNVERIFIED,
                        proof_type=ContinuityProofType.NONE,
                        stable_source_line_id=None,
                    )
                third = dataclasses.replace(third, **changes)
                result = evaluate_doi(
                    evaluation_input(split_lines(third=third))
                )
                self.assertEqual(result.state, DOIState.DOI_OPPORTUNITY)
                self.assertIn(
                    reason_code,
                    {reason.code for reason in result.reasons.reasons},
                )

        for reason_code in ("RC-136", "RC-137", "RC-138"):
            with self.subTest(alternate_observation=reason_code):
                request = evaluation_input(split_lines())
                candidate = relationship_candidate(
                    request,
                    relationship_type=AlternateRelationshipType.MFG_CROSS_REFERENCE,
                    compatibility=CompatibilityDecision.NOT_REQUIRED,
                    suffix=f"UNKNOWN-{reason_code}",
                    unknown_observation_reason=reason_code,
                )
                result = evaluate_doi(
                    evaluation_input(
                        split_lines(),
                        alternate_candidates=(candidate,),
                    )
                )
                self.assertEqual(result.state, DOIState.DOI_OPPORTUNITY)
                self.assertIn(
                    reason_code,
                    {reason.code for reason in result.reasons.reasons},
                )

    def test_value_unavailability_and_mixed_currency_emit_exact_reasons(self) -> None:
        source = order_source(OrderId("SYN-ORDER-DOI-0001"))
        unavailable_line = dataclasses.replace(
            make_line(
                1,
                source,
                availability=LineAvailability.IN_STOCK,
                quantity_availability=QuantityAvailability.FULL,
                explicitly_available=2,
            ),
            unit_value=not_applicable_fact(),
            active_line_value=not_applicable_fact(),
        )
        unavailable = evaluate_doi(
            evaluation_input((unavailable_line, make_line(2, source)))
        )
        self.assertIn("RC-085", {reason.code for reason in unavailable.reasons.reasons})
        self.assertIs(
            unavailable.aggregate_potential_state,
            ValueAvailabilityState.UNAVAILABLE,
        )

        jpy = Money.from_minor_units(
            100,
            currency_code="JPY",
            registry_version=CURRENCY_REGISTRY_VERSION,
            scale=0,
        )
        usd_partial = make_line(
            1,
            source,
            availability=LineAvailability.IN_STOCK,
            quantity_availability=QuantityAvailability.PARTIAL,
            explicitly_available=1,
        )
        jpy_partial = dataclasses.replace(
            make_line(
                2,
                source,
                availability=LineAvailability.IN_STOCK,
                quantity_availability=QuantityAvailability.PARTIAL,
                explicitly_available=1,
            ),
            unit_value=known_fact(jpy),
        )
        mixed = evaluate_doi(evaluation_input((usd_partial, jpy_partial)))
        self.assertIn("RC-095", {reason.code for reason in mixed.reasons.reasons})
        self.assertIs(
            mixed.aggregate_potential_state,
            ValueAvailabilityState.UNAVAILABLE,
        )

    def test_currency_and_evaluation_hash_boundaries_emit_exact_reasons(self) -> None:
        with self.assertRaises(DOIEvaluationError) as currency_error:
            construct_doi_money(
                Decimal("10.00"),
                "US",
                CURRENCY_REGISTRY_VERSION,
                2,
            )
        self.assertEqual(
            tuple(reason.code for reason in currency_error.exception.reasons.reasons),
            ("RC-094",),
        )
        request = evaluation_input(split_lines())
        forged = domain_hash(
            request.available_rule_pack_binding.domain,
            canonical_json_bytes({"forged": True}, expected_members={"forged"}),
        )
        with self.assertRaises(DOIEvaluationError) as provenance_error:
            evaluate_doi(
                dataclasses.replace(
                    request,
                    available_rule_pack_binding=forged,
                )
            )
        self.assertEqual(
            tuple(
                reason.code
                for reason in provenance_error.exception.reasons.reasons
            ),
            ("RC-106",),
        )

    def test_caller_booleans_cannot_forge_human_conclusions(self) -> None:
        base = evaluation_input(split_lines())
        values = {
            "evaluation_id": base.evaluation_id,
            "snapshot": base.snapshot,
            "evaluated_at": base.evaluated_at,
            "authorized_human_out_of_scope": True,
        }
        with self.assertRaises(TypeError):
            DOIEvaluationInput(**values)  # type: ignore[arg-type]

    def test_rc084_evaluation_gate_creates_no_substitute_evaluation(self) -> None:
        request = evaluation_input(split_lines())
        unavailable = dataclasses.replace(
            request,
            available_rule_pack_binding=None,
        )
        with self.assertRaises(DOIRuleVersionUnavailable) as caught:
            evaluate_doi(unavailable)
        blocked = caught.exception
        self.assertEqual(blocked.reason.code, "RC-084")
        self.assertIsNone(blocked.evaluation)
        self.assertEqual(
            {item.transition_id for item in blocked.governed_transitions},
            {"TR-027", "TR-037"},
        )
        for transition in blocked.governed_transitions:
            assert_reason_route_legal(blocked.reason, transition)

    def test_dedupe_approval_does_not_close_but_verified_later_note_does(self) -> None:
        source = order_source(OrderId("SYN-ORDER-DOI-0001"))
        base = evaluation_input(
            (make_line(1, source),),
            alternate_research_state=AlternateResearchState.COMPLETE,
            dedupe_state=DedupeState.SOURCE_PRESENT,
        )
        candidate_evaluation = evaluate_doi(base)
        self.assertIn(
            "RC-058",
            {reason.code for reason in candidate_evaluation.reasons.reasons},
        )
        approval = human_fact(
            base,
            usage=HumanFactUsageKind.DEDUPE_DECISION,
            result=HumanFactResultCode.APPROVED,
        )
        self.assertEqual(
            model_hash_known_answer(approval).sha256,
            approval.hash_binding().sha256,
        )
        awaiting = evaluate_doi(
            DOIEvaluationInput(
                evaluation_id=base.evaluation_id,
                snapshot=base.snapshot,
                evaluated_at=base.evaluated_at,
                human_facts=(approval,),
            )
        )
        self.assertIsNone(awaiting.closure_proposal)
        stream_id = EvidenceId("SYN-EVIDENCE-DOI-DEDUPE-STREAM-0001")
        history = DOIDedupeHistory.empty(
            stream_id=stream_id,
            order_id=base.snapshot.order_id,
        )
        observed_event_id = EvidenceId("SYN-EVIDENCE-DOI-DEDUPE-EVENT-0001")
        observed = DOIDedupeEvent(
            event_id=observed_event_id,
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
                event_id=observed_event_id,
                suffix="DED-0001",
            ),
        )
        history = reduce_dedupe(history, observed).history
        observed_history = history
        candidate_event_id = EvidenceId("SYN-EVIDENCE-DOI-DEDUPE-EVENT-0002")
        candidate = DOIDedupeEvent(
            event_id=candidate_event_id,
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
                event_id=candidate_event_id,
                suffix="DED-0002",
            ),
        )
        history = reduce_dedupe(history, candidate).history
        candidate_history = history
        self.assertEqual(history.projection.state, DedupeState.CANDIDATE)

        incomplete_evaluation = evaluate_doi(
            evaluation_input(
                split_lines(),
                evaluation_suffix="DED-INCOMPLETE",
                alternate_research_state=AlternateResearchState.COMPLETE,
                dedupe_state=DedupeState.SOURCE_PRESENT,
            )
        )
        self.assertIn(
            "RC-059",
            {item.code for item in incomplete_evaluation.reasons.reasons},
        )
        incomplete_event_id = EvidenceId(
            "SYN-EVIDENCE-DOI-DEDUPE-EVENT-INCOMPLETE"
        )
        incomplete = DOIDedupeEvent(
            event_id=incomplete_event_id,
            stream_id=stream_id,
            order_id=base.snapshot.order_id,
            event_type=DedupeEventType.ANALYSIS_INCOMPLETE,
            finding=None,
            evaluation=incomplete_evaluation,
            human_fact=None,
            verification=None,
            recorded_at=OBSERVED_AT,
            sequence=2,
            predecessor_binding=observed_history.events[-1].hash_binding(),
            guard=occurrence_guard(
                owner_id=stream_id,
                event_id=incomplete_event_id,
                suffix="DED-INCOMPLETE",
            ),
        )
        incomplete_history = reduce_dedupe(observed_history, incomplete).history
        self.assertEqual(incomplete_history.projection.state, DedupeState.INCOMPLETE)

        rejection = human_fact(
            base,
            usage=HumanFactUsageKind.DEDUPE_DECISION,
            result=HumanFactResultCode.REJECTED,
            suffix="DED-REJECTED",
        )
        rejected_event_id = EvidenceId(
            "SYN-EVIDENCE-DOI-DEDUPE-EVENT-REJECTED"
        )
        rejected_event = DOIDedupeEvent(
            event_id=rejected_event_id,
            stream_id=stream_id,
            order_id=base.snapshot.order_id,
            event_type=DedupeEventType.HUMAN_REJECTED,
            finding=None,
            evaluation=None,
            human_fact=rejection,
            verification=None,
            recorded_at=OBSERVED_AT,
            sequence=3,
            predecessor_binding=candidate_history.events[-1].hash_binding(),
            guard=occurrence_guard(
                owner_id=stream_id,
                event_id=rejected_event_id,
                suffix="DED-REJECTED",
            ),
        )
        rejected_history = reduce_dedupe(
            candidate_history,
            rejected_event,
        ).history
        self.assertEqual(rejected_history.projection.state, DedupeState.REJECTED)
        approval_event_id = EvidenceId("SYN-EVIDENCE-DOI-DEDUPE-EVENT-0003")
        approved = DOIDedupeEvent(
            event_id=approval_event_id,
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
                event_id=approval_event_id,
                suffix="DED-0003",
            ),
        )
        history = reduce_dedupe(history, approved).history
        self.assertEqual(
            history.projection.state,
            DedupeState.APPROVED_AWAITING_VERIFICATION,
        )
        verified_at = CanonicalTimestamp("2026-08-20T14:15:17Z")
        verified_snapshot = make_snapshot(
            base.snapshot.lines,
            dedupe_state=DedupeState.SOURCE_PRESENT,
            observed_at=verified_at,
            snapshot_suffix="DEDUPE-VERIFIED",
            run_suffix="DEDUPE-VERIFIED",
            dedupe_suffix="VERIFIED-0002",
        )
        verification = DedupeVerificationFact(
            verification_id=EvidenceId("SYN-EVIDENCE-DOI-DEDUPE-VERIFY-0001"),
            order_id=base.snapshot.order_id,
            prior_snapshot=base.snapshot,
            verified_snapshot=verified_snapshot,
            approved_human_fact_binding=approval.hash_binding(),
            prior_projection_binding=history.projection.hash_binding(),
            approved_at=approval.occurred_at,
        )
        with self.assertRaisesRegex(
            ValueError,
            "DEDUPE_VERIFICATION_REUSED_SOURCE_OBSERVATION",
        ):
            dataclasses.replace(
                verification,
                verified_snapshot=base.snapshot,
            )
        preapproval_snapshot = make_snapshot(
            base.snapshot.lines,
            dedupe_state=DedupeState.SOURCE_PRESENT,
            observed_at=approval.occurred_at,
            snapshot_suffix="DEDUPE-PREAPPROVAL",
            run_suffix="DEDUPE-PREAPPROVAL",
            dedupe_suffix="PREAPPROVAL-0002",
        )
        with self.assertRaisesRegex(
            ValueError,
            "DEDUPE_VERIFICATION_NOT_LATER_THAN_APPROVAL",
        ):
            dataclasses.replace(
                verification,
                verified_snapshot=preapproval_snapshot,
            )
        self.assertEqual(
            model_hash_known_answer(verification).preimage,
            verification.hash_binding().preimage,
        )
        confirmed = evaluate_doi(
            DOIEvaluationInput(
                evaluation_id=base.evaluation_id,
                snapshot=verified_snapshot,
                evaluated_at=verified_at,
                human_facts=(approval,),
                dedupe_history=history,
                dedupe_verification=verification,
            )
        )
        self.assertEqual(confirmed.transition.transition_id, "TR-030")
        self.assertEqual(
            confirmed.closure_proposal.reason,
            TerminalClosureReason.DEDUPE_CONFIRMED,
        )
        self.assertIn(
            "RC-024",
            {reason.code for reason in confirmed.reasons.reasons},
        )
        forged_prior_snapshot = make_snapshot(
            base.snapshot.lines,
            dedupe_state=DedupeState.SOURCE_PRESENT,
            snapshot_suffix="DEDUPE-FORGED-PRIOR",
            run_suffix="DEDUPE-FORGED-PRIOR",
            dedupe_suffix="FORGED-PRIOR",
        )
        forged_verification = dataclasses.replace(
            verification,
            prior_snapshot=forged_prior_snapshot,
        )
        with self.assertRaisesRegex(
            ValueError,
            "DOI_DEDUPE_VERIFICATION_BINDING_INVALID",
        ):
            DOIEvaluationInput(
                evaluation_id=base.evaluation_id,
                snapshot=verified_snapshot,
                evaluated_at=verified_at,
                human_facts=(approval,),
                dedupe_history=history,
                dedupe_verification=forged_verification,
            )

        confirmation_event_id = EvidenceId(
            "SYN-EVIDENCE-DOI-DEDUPE-EVENT-0004"
        )
        confirmation_event = DOIDedupeEvent(
            event_id=confirmation_event_id,
            stream_id=stream_id,
            order_id=base.snapshot.order_id,
            event_type=DedupeEventType.VERIFIED_SOURCE_CONFIRMED,
            finding=None,
            evaluation=None,
            human_fact=None,
            verification=verification,
            recorded_at=verified_at,
            sequence=4,
            predecessor_binding=history.events[-1].hash_binding(),
            guard=occurrence_guard(
                owner_id=stream_id,
                event_id=confirmation_event_id,
                suffix="DED-0004",
            ),
        )
        confirmed_history = reduce_dedupe(
            history,
            confirmation_event,
        ).history
        self.assertEqual(confirmed_history.projection.state, DedupeState.CONFIRMED)
        self.assertEqual(
            confirmed_history.projection.source_finding_binding,
            verified_snapshot.dedupe_finding.hash_binding(),
        )

        corrected_id = EvidenceId(
            "SYN-EVIDENCE-DOI-DEDUPE-EVENT-CORRECTED-REJECTION"
        )
        corrected_rejection_fact = dataclasses.replace(
            approval,
            fact_id=EvidenceId(
                "SYN-EVIDENCE-DOI-DEDUPE-FACT-CORRECTED-REJECTION"
            ),
            result_code=HumanFactResultCode.REJECTED,
        )
        corrected_rejection = DOIDedupeEvent(
            event_id=corrected_id,
            stream_id=stream_id,
            order_id=base.snapshot.order_id,
            event_type=DedupeEventType.HUMAN_REJECTED,
            finding=None,
            evaluation=None,
            human_fact=corrected_rejection_fact,
            verification=None,
            recorded_at=OBSERVED_AT,
            sequence=4,
            predecessor_binding=history.events[-1].hash_binding(),
            guard=occurrence_guard(
                owner_id=stream_id,
                event_id=corrected_id,
                suffix="DED-CORRECTED-REJECTION",
            ),
            corrects_event_id=approved.event_id,
            corrected_human_fact_binding=approval.hash_binding(),
        )
        corrected_history = reduce_dedupe(
            history,
            corrected_rejection,
        ).history
        self.assertEqual(corrected_history.projection.state, DedupeState.REJECTED)
        with self.assertRaisesRegex(
            ValueError,
            "DOI_DEDUPE_HUMAN_DECISION_PREMATURE",
        ):
            reduce_dedupe(
                history,
                dataclasses.replace(
                    corrected_rejection,
                    corrects_event_id=None,
                    corrected_human_fact_binding=None,
                ),
            )

        recandidate_id = EvidenceId(
            "SYN-EVIDENCE-DOI-DEDUPE-EVENT-RECANDIDATE"
        )
        candidate_recheck_evaluation = evaluate_doi(
            dataclasses.replace(
                base,
                evaluation_id=EvaluationId(
                    "SYN-EVALUATION-DOI-DEDUPE-RECANDIDATE"
                ),
            )
        )
        recandidate = DOIDedupeEvent(
            event_id=recandidate_id,
            stream_id=stream_id,
            order_id=base.snapshot.order_id,
            event_type=DedupeEventType.CANDIDATE_IDENTIFIED,
            finding=None,
            evaluation=candidate_recheck_evaluation,
            human_fact=None,
            verification=None,
            recorded_at=OBSERVED_AT,
            sequence=5,
            predecessor_binding=corrected_history.events[-1].hash_binding(),
            guard=occurrence_guard(
                owner_id=stream_id,
                event_id=recandidate_id,
                suffix="DED-RECANDIDATE",
            ),
        )
        recandidate_history = reduce_dedupe(
            corrected_history,
            recandidate,
        ).history
        self.assertEqual(recandidate_history.projection.state, DedupeState.CANDIDATE)

        def withdrawal(
            source_history: DOIDedupeHistory,
            suffix: str,
        ) -> DOIDedupeHistory:
            event_id = EvidenceId(
                f"SYN-EVIDENCE-DOI-DEDUPE-EVENT-WITHDRAW-{suffix}"
            )
            event = DOIDedupeEvent(
                event_id=event_id,
                stream_id=stream_id,
                order_id=base.snapshot.order_id,
                event_type=DedupeEventType.CANDIDATE_WITHDRAWN,
                finding=None,
                evaluation=incomplete_evaluation,
                human_fact=None,
                verification=None,
                recorded_at=OBSERVED_AT,
                sequence=len(source_history.events) + 1,
                predecessor_binding=source_history.events[-1].hash_binding(),
                guard=occurrence_guard(
                    owner_id=stream_id,
                    event_id=event_id,
                    suffix=f"DED-WITHDRAW-{suffix}",
                ),
            )
            return reduce_dedupe(source_history, event).history

        for source_history, suffix in (
            (candidate_history, "CANDIDATE"),
            (history, "APPROVED"),
            (corrected_history, "REJECTED"),
        ):
            with self.subTest(withdrawal=suffix):
                self.assertEqual(
                    withdrawal(source_history, suffix).projection.state,
                    DedupeState.NOT_CANDIDATE,
                )

        eligibility_id = EvidenceId(
            "SYN-EVIDENCE-DOI-DEDUPE-EVENT-ELIGIBILITY-RETURNED"
        )
        eligibility = DOIDedupeEvent(
            event_id=eligibility_id,
            stream_id=stream_id,
            order_id=base.snapshot.order_id,
            event_type=DedupeEventType.ELIGIBILITY_RETURNED,
            finding=None,
            evaluation=candidate_evaluation,
            human_fact=None,
            verification=None,
            recorded_at=verified_at,
            sequence=5,
            predecessor_binding=confirmed_history.events[-1].hash_binding(),
            guard=occurrence_guard(
                owner_id=stream_id,
                event_id=eligibility_id,
                suffix="DED-ELIGIBILITY-RETURNED",
            ),
        )
        eligibility_history = reduce_dedupe(
            confirmed_history,
            eligibility,
        ).history
        self.assertEqual(
            eligibility_history.projection.state,
            DedupeState.NOT_CANDIDATE,
        )
        with self.assertRaisesRegex(ValueError, "DOI_DEDUPE_STATE_CONFLICT"):
            reduce_dedupe(
                candidate_history,
                dataclasses.replace(
                    eligibility,
                    sequence=len(candidate_history.events) + 1,
                    predecessor_binding=candidate_history.events[-1].hash_binding(),
                ),
            )

    def test_forged_alternate_candidate_material_cannot_enable_tr035(self) -> None:
        request = evaluation_input(split_lines())
        line = request.snapshot.lines[0]
        exact = exact_sku_candidate(
            candidate_id=EvidenceId("SYN-EVIDENCE-DOI-CANDIDATE-0099"),
            quantity=PositiveQuantity(1),
            observation=exact_observation(request, suffix="0099"),
        )
        forged_values = (
            (
                dataclasses.replace(
                    exact,
                    candidate_sku=SkuId("SYN-SKU-DOI-FORGED-0001"),
                ),
                "RC-105",
            ),
            (
                dataclasses.replace(
                    exact,
                    ordered_line_id=type(line.line_snapshot_id)(
                        EvidenceId("SYN-EVIDENCE-DOI-LINE-9999")
                    ),
                ),
                "RC-097",
            ),
            (
                dataclasses.replace(
                    exact,
                    observation_binding=domain_hash(
                        "doi-forged-observation/v1",
                        canonical_json_bytes(
                            {"current": True},
                            expected_members={"current"},
                        ),
                    ),
                ),
                "RC-105",
            ),
        )
        for forged, expected_reason in forged_values:
            with self.subTest(candidate=forged.candidate_sku.value):
                with self.assertRaises(DOIEvaluationError) as caught:
                    evaluate_doi(
                        evaluation_input(
                            split_lines(),
                            alternate_candidates=(forged,),
                        )
                    )
                self.assertEqual(
                    tuple(
                        reason.code
                        for reason in caught.exception.reasons.reasons
                    ),
                    (expected_reason,),
                )


class DOIEvaluatorBranchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = order_source(OrderId("SYN-ORDER-DOI-0001"))

    def test_full_ds_is_excluded_but_has_no_closure(self) -> None:
        line = make_line(
            1,
            self.source,
            drop_ship=DropShipState.DS,
            availability=LineAvailability.IN_STOCK,
            quantity_availability=QuantityAvailability.FULL,
            explicitly_available=2,
        )
        result = evaluate_doi(evaluation_input((line,)))
        self.assertEqual(result.state, DOIState.DOI_EXCLUDED)
        self.assertEqual(result.transition.transition_id, "TR-031")
        self.assertIsNone(result.closure_proposal)

    def test_source_absence_forces_recheck_monitor_and_suppresses_stale_closure(self) -> None:
        request = evaluation_input(
            split_lines(),
            order_state=OrderState.SHIPPED,
        )
        absent = dataclasses.replace(
            request.snapshot,
            source_presence=SourcePresence.ABSENT_RECHECK_REQUIRED,
        )
        result = evaluate_doi(
            DOIEvaluationInput(
                evaluation_id=request.evaluation_id,
                snapshot=absent,
                evaluated_at=request.evaluated_at,
            )
        )
        self.assertEqual(result.state, DOIState.DOI_MONITOR)
        self.assertEqual(result.transition.transition_id, "TR-038")
        self.assertEqual(
            {reason.code for reason in result.reasons.reasons},
            {"RC-010"},
        )
        self.assertIn(
            HandlingFlag.SOURCE_ABSENCE_RECHECK_REQUIRED,
            result.handling_flags,
        )
        self.assertIsNone(result.closure_proposal)
        self.assertEqual(result.opportunities, ())

    def test_default_monitor_is_tr038_and_human_out_of_scope_is_exact_closure(self) -> None:
        monitor = evaluate_doi(evaluation_input(()))
        self.assertEqual(monitor.state, DOIState.DOI_MONITOR)
        self.assertEqual(monitor.transition.transition_id, "TR-038")
        self.assertNotIn("RC-029", {reason.code for reason in monitor.reasons.reasons})

        base = evaluation_input(
            (make_line(1, self.source),),
            evaluation_suffix="OUT-0001",
        )
        fact = human_fact(
            base,
            usage=HumanFactUsageKind.OUT_OF_SCOPE_CLOSURE,
            result=HumanFactResultCode.OUT_OF_SCOPE,
            suffix="OUT-0001",
        )
        closed = evaluate_doi(
            DOIEvaluationInput(
                evaluation_id=base.evaluation_id,
                snapshot=base.snapshot,
                evaluated_at=base.evaluated_at,
                human_facts=(fact,),
            )
        )
        self.assertEqual(closed.transition.transition_id, "TR-030")
        self.assertEqual(
            closed.closure_proposal.reason,
            TerminalClosureReason.HUMAN_OUT_OF_SCOPE,
        )
        self.assertIn("RC-025", {reason.code for reason in closed.reasons.reasons})

    def test_mixed_ds_continues_non_ds_analysis(self) -> None:
        ds = make_line(1, self.source, drop_ship=DropShipState.DS)
        non_ds = make_line(2, self.source)
        result = evaluate_doi(evaluation_input((ds, non_ds)))
        self.assertEqual(result.state, DOIState.DOI_OPPORTUNITY)
        self.assertEqual(result.transition.transition_id, "TR-033")
        self.assertEqual(result.opportunities[0].opportunity_type, OpportunityType.DS_SEPARATION)

    def test_payment_only_excludes_but_payment_with_split_preserves_opportunity(self) -> None:
        payment_only = evaluate_doi(
            evaluation_input(
                (make_line(1, self.source),),
                payment=PaymentCondition.PRESENT,
            )
        )
        self.assertEqual(payment_only.transition.transition_id, "TR-032")
        self.assertIn("RC-026", {reason.code for reason in payment_only.reasons.reasons})

        with_split = evaluate_doi(
            evaluation_input(split_lines(), payment=PaymentCondition.PRESENT)
        )
        self.assertEqual(with_split.state, DOIState.DOI_OPPORTUNITY)
        self.assertIn("RC-027", {reason.code for reason in with_split.reasons.reasons})
        self.assertIn(HandlingFlag.PAYMENT_BEFORE_ACTION, with_split.handling_flags)

    def test_geography_and_unknown_eta_do_not_erase_split(self) -> None:
        source = self.source
        lines = (
            make_line(
                1,
                source,
                availability=LineAvailability.IN_STOCK,
                quantity_availability=QuantityAvailability.FULL,
                explicitly_available=2,
                eta=unknown_fact("RC-115"),
            ),
            make_line(2, source),
        )
        result = evaluate_doi(
            evaluation_input(lines, geography=GeographyClass.INTERNATIONAL)
        )
        self.assertEqual(result.state, DOIState.DOI_OPPORTUNITY)
        self.assertTrue(
            {"RC-050", "RC-051", "RC-115"}.issubset(
                {reason.code for reason in result.reasons.reasons}
            )
        )
        self.assertIn(HandlingFlag.ETA_RANKING_UNAVAILABLE, result.handling_flags)

    def test_every_valid_alternate_type_reaches_tr035_with_exact_reason(self) -> None:
        base = evaluation_input((make_line(1, self.source),))
        cases = (
            (
                AlternateRelationshipType.EXACT_MFG,
                CompatibilityDecision.NOT_REQUIRED,
                OpportunityType.EXACT_MFG_ALTERNATE,
                "RC-034",
            ),
            (
                AlternateRelationshipType.MFG_CROSS_REFERENCE,
                CompatibilityDecision.NOT_REQUIRED,
                OpportunityType.MFG_CROSS_REFERENCE,
                "RC-035",
            ),
            (
                AlternateRelationshipType.MFG_SUPERSESSION,
                CompatibilityDecision.NOT_REQUIRED,
                OpportunityType.MFG_SUPERSESSION,
                "RC-036",
            ),
            (
                AlternateRelationshipType.FUNCTIONAL,
                CompatibilityDecision.APPROVED,
                OpportunityType.FUNCTIONAL_ALTERNATE,
                "RC-037",
            ),
        )
        for index, (relation_type, decision, opportunity_type, reason) in enumerate(
            cases,
            start=1,
        ):
            with self.subTest(relationship=relation_type.value):
                candidate = relationship_candidate(
                    base,
                    relationship_type=relation_type,
                    compatibility=decision,
                    suffix=f"TYPE-{index:04d}",
                )
                result = evaluate_doi(
                    evaluation_input(
                        (make_line(1, self.source),),
                        alternate_candidates=(candidate,),
                    )
                )
                self.assertEqual(result.transition.transition_id, "TR-035")
                self.assertEqual(
                    {item.opportunity_type for item in result.opportunities},
                    {opportunity_type},
                )
                codes = {item.code for item in result.reasons.reasons}
                self.assertIn(reason, codes)
                self.assertIn("RC-042", codes)

    def test_exact_sku_standalone_is_rc033_and_never_substitution(self) -> None:
        base = evaluation_input((make_line(1, self.source),))
        candidate = exact_sku_candidate(
            candidate_id=EvidenceId("SYN-EVIDENCE-DOI-CANDIDATE-STANDALONE"),
            quantity=PositiveQuantity(1),
            observation=exact_observation(base, suffix="STANDALONE"),
        )
        result = evaluate_doi(
            evaluation_input(
                (make_line(1, self.source),),
                alternate_candidates=(candidate,),
            )
        )
        codes = {item.code for item in result.reasons.reasons}
        self.assertEqual(result.transition.transition_id, "TR-035")
        self.assertIn("RC-033", codes)
        self.assertNotIn("RC-042", codes)

    def test_alternate_observation_and_terminal_relationship_blocks_are_exact(self) -> None:
        base = evaluation_input((make_line(1, self.source),))
        current = relationship_candidate(
            base,
            relationship_type=AlternateRelationshipType.EXACT_MFG,
            compatibility=CompatibilityDecision.NOT_REQUIRED,
            suffix="BLOCK-CURRENT",
        )
        missing = dataclasses.replace(
            current,
            current_observation=False,
            observation_binding=None,
        )
        stale = relationship_candidate(
            base,
            relationship_type=AlternateRelationshipType.EXACT_MFG,
            compatibility=CompatibilityDecision.NOT_REQUIRED,
            suffix="BLOCK-STALE",
            observation_state=AlternateObservationState.STALE,
        )
        superseded = relationship_candidate(
            base,
            relationship_type=AlternateRelationshipType.MFG_SUPERSESSION,
            compatibility=CompatibilityDecision.NOT_REQUIRED,
            suffix="BLOCK-SUPERSEDED",
            terminal_state=AlternateRelationshipState.SUPERSEDED,
        )
        invalidated = relationship_candidate(
            base,
            relationship_type=AlternateRelationshipType.MFG_CROSS_REFERENCE,
            compatibility=CompatibilityDecision.NOT_REQUIRED,
            suffix="BLOCK-INVALIDATED",
            terminal_state=AlternateRelationshipState.INVALIDATED,
        )
        for candidate, reason in (
            (missing, "RC-044"),
            (stale, "RC-045"),
            (superseded, "RC-046"),
            (invalidated, "RC-047"),
        ):
            with self.subTest(reason=reason):
                result = evaluate_doi(
                    evaluation_input(
                        (make_line(1, self.source),),
                        alternate_candidates=(candidate,),
                    )
                )
                self.assertEqual(result.opportunities, ())
                self.assertIn(reason, {item.code for item in result.reasons.reasons})

    def test_alternate_research_and_compatibility_decisions_are_distinct(self) -> None:
        delayed = (make_line(1, self.source),)
        complete = evaluate_doi(
            evaluation_input(
                delayed,
                alternate_research_state=AlternateResearchState.COMPLETE,
            )
        )
        self.assertTrue(
            {"RC-038", "RC-039"}.issubset(
                {item.code for item in complete.reasons.reasons}
            )
        )
        manual = evaluate_doi(
            evaluation_input(
                delayed,
                alternate_research_state=(
                    AlternateResearchState.MANUAL_IDENTIFICATION_REQUIRED
                ),
            )
        )
        self.assertEqual(manual.transition.transition_id, "TR-037")
        self.assertTrue(
            {"RC-040", "RC-059"}.issubset(
                {item.code for item in manual.reasons.reasons}
            )
        )

        no_viable_base = evaluation_input(
            delayed,
            evaluation_suffix="NO-VIABLE",
            alternate_research_state=AlternateResearchState.COMPLETE,
        )
        no_viable_fact = human_fact(
            no_viable_base,
            usage=HumanFactUsageKind.ALTERNATE_RESEARCH,
            result=HumanFactResultCode.NO_VIABLE_ALTERNATE,
            suffix="NO-VIABLE",
        )
        no_viable = evaluate_doi(
            DOIEvaluationInput(
                evaluation_id=no_viable_base.evaluation_id,
                snapshot=no_viable_base.snapshot,
                evaluated_at=no_viable_base.evaluated_at,
                alternate_research_state=AlternateResearchState.COMPLETE,
                human_facts=(no_viable_fact,),
            )
        )
        self.assertIn("RC-041", {item.code for item in no_viable.reasons.reasons})

        review_candidate = relationship_candidate(
            no_viable_base,
            relationship_type=AlternateRelationshipType.FUNCTIONAL,
            compatibility=CompatibilityDecision.MORE_EVIDENCE_REQUIRED,
            suffix="COMPAT-MORE",
        )
        review = evaluate_doi(
            evaluation_input(
                delayed,
                alternate_candidates=(review_candidate,),
            )
        )
        self.assertEqual(
            review_candidate.validity,
            AlternateValidityState.COMPATIBILITY_REVIEW_REQUIRED,
        )
        self.assertTrue(
            {"RC-037", "RC-042", "RC-043", "RC-048"}.issubset(
                {item.code for item in review.reasons.reasons}
            )
        )
        self.assertIn(
            HandlingFlag.COMPATIBILITY_REVIEW_REQUIRED,
            review.handling_flags,
        )

        rejected_candidate = relationship_candidate(
            no_viable_base,
            relationship_type=AlternateRelationshipType.FUNCTIONAL,
            compatibility=CompatibilityDecision.REJECTED,
            suffix="COMPAT-REJECTED",
        )
        rejected = evaluate_doi(
            evaluation_input(
                delayed,
                alternate_candidates=(rejected_candidate,),
            )
        )
        self.assertEqual(rejected_candidate.validity, AlternateValidityState.REJECTED)
        self.assertEqual(rejected.opportunities, ())

    def test_every_geography_class_has_its_exact_split_handling(self) -> None:
        cases = (
            (GeographyClass.DOMESTIC_STANDARD, set(), set()),
            (
                GeographyClass.DOMESTIC_SPECIAL_REVIEW,
                {"RC-049"},
                {HandlingFlag.AK_HI_SHIPPING_REVIEW},
            ),
            (
                GeographyClass.INTERNATIONAL,
                {"RC-050", "RC-051"},
                {
                    HandlingFlag.INTERNATIONAL_REVIEW,
                    HandlingFlag.CUSTOMER_CONTACT_BEFORE_SPLIT,
                },
            ),
        )
        for geography, expected_reasons, expected_flags in cases:
            with self.subTest(geography=geography.value):
                result = evaluate_doi(
                    evaluation_input(split_lines(), geography=geography)
                )
                codes = {reason.code for reason in result.reasons.reasons}
                self.assertEqual(codes & {"RC-049", "RC-050", "RC-051"}, expected_reasons)
                self.assertEqual(
                    set(result.handling_flags)
                    & {
                        HandlingFlag.AK_HI_SHIPPING_REVIEW,
                        HandlingFlag.INTERNATIONAL_REVIEW,
                        HandlingFlag.CUSTOMER_CONTACT_BEFORE_SPLIT,
                    },
                    expected_flags,
                )

        unknown = evaluate_doi(
            evaluation_input(
                split_lines(),
                geography=unknown_fact("RC-119"),
            )
        )
        self.assertEqual(unknown.state, DOIState.DOI_OPPORTUNITY)
        self.assertIn("RC-119", {item.code for item in unknown.reasons.reasons})
        self.assertIn(
            HandlingFlag.GEOGRAPHY_ACTION_READINESS_REVIEW_REQUIRED,
            unknown.handling_flags,
        )
        self.assertTrue(
            {HumanReviewKind.SHIPPING, HumanReviewKind.UNKNOWN_FACT}.issubset(
                set(unknown.human_review_requirements)
            )
        )

    def test_wwc_known_author_and_timing_matrix_has_exact_behavior(self) -> None:
        for author in WWCAuthorRelation:
            for timing in WWCTimingState:
                with self.subTest(author=author.value, timing=timing.value):
                    base = evaluation_input((make_line(1, self.source),))
                    snapshot = dataclasses.replace(
                        base.snapshot,
                        wwc_finding=dataclasses.replace(
                            base.snapshot.wwc_finding,
                            presence=FindingPresenceV2.PRESENT,
                            author_relation=known_fact(author),
                            timing_state=known_fact(timing),
                            marker=known_fact("WWC_MARKER"),
                            observed_at=known_fact(OBSERVED_AT),
                        ),
                    )
                    result = evaluate_doi(
                        DOIEvaluationInput(
                            evaluation_id=base.evaluation_id,
                            snapshot=snapshot,
                            evaluated_at=base.evaluated_at,
                        )
                    )
                    codes = {item.code for item in result.reasons.reasons}
                    expected: set[str] = set()
                    if timing is WWCTimingState.ACTIVE:
                        if author is WWCAuthorRelation.TARGET_REP:
                            expected.add("RC-053")
                        elif author is WWCAuthorRelation.OTHER_REP:
                            expected.add("RC-054")
                    if author is WWCAuthorRelation.UNCERTAIN:
                        expected.update(("RC-055", "RC-057"))
                    if timing is WWCTimingState.UNCERTAIN:
                        expected.update(("RC-056", "RC-057"))
                    self.assertEqual(
                        codes & {"RC-053", "RC-054", "RC-055", "RC-056", "RC-057"},
                        expected,
                    )

    def test_partial_quantity_is_never_an_automatic_action(self) -> None:
        line = make_line(
            1,
            self.source,
            availability=LineAvailability.IN_STOCK,
            quantity_availability=QuantityAvailability.PARTIAL,
            active_quantity=3,
            explicitly_available=1,
        )
        result = evaluate_doi(evaluation_input((line,)))
        self.assertEqual(result.state, DOIState.DOI_OPPORTUNITY)
        self.assertEqual(result.transition.transition_id, "TR-034")
        self.assertEqual(
            result.opportunities[0].opportunity_type,
            OpportunityType.PARTIAL_QUANTITY_REVIEW,
        )
        self.assertEqual(result.opportunities[0].potential_value, usd("10.00"))

    def test_hard_and_reversible_closures_precede_product_rules(self) -> None:
        cases = (
            (
                "shipped",
                {"order_state": OrderState.SHIPPED},
                "TR-029",
                TerminalClosureReason.SHIPPED,
            ),
            (
                "canceled",
                {"order_state": OrderState.CANCELED},
                "TR-029",
                TerminalClosureReason.CANCELED,
            ),
            (
                "transfer",
                {"rep_relation": RepRelation.OTHER_REP},
                "TR-030",
                TerminalClosureReason.REP_TRANSFERRED,
            ),
        )
        for name, changes, transition, closure in cases:
            with self.subTest(name=name):
                result = evaluate_doi(evaluation_input(split_lines(), **changes))
                self.assertEqual(result.state, DOIState.DOI_EXCLUDED)
                self.assertEqual(result.transition.transition_id, transition)
                self.assertEqual(result.closure_proposal.reason, closure)
                self.assertEqual(result.opportunities, ())

    def test_all_in_stock_progress_review_and_monitor(self) -> None:
        line = make_line(
            1,
            self.source,
            availability=LineAvailability.IN_STOCK,
            quantity_availability=QuantityAvailability.FULL,
            explicitly_available=2,
        )
        review = evaluate_doi(evaluation_input((line,)))
        self.assertEqual(review.transition.transition_id, "TR-036")
        self.assertEqual(review.state, DOIState.DOI_MANUAL_REVIEW)

        monitor_base = evaluation_input(
            (make_line(1, self.source),),
            order_state=OrderState.ACTIVE,
        )
        monitor_fact = human_fact(
            monitor_base,
            usage=HumanFactUsageKind.NO_ACTION_DECISION,
            result=HumanFactResultCode.APPROVED,
        )
        monitor_request = DOIEvaluationInput(
            evaluation_id=monitor_base.evaluation_id,
            snapshot=monitor_base.snapshot,
            evaluated_at=monitor_base.evaluated_at,
            human_facts=(monitor_fact,),
        )
        monitor = evaluate_doi(monitor_request)
        self.assertEqual(monitor.state, DOIState.DOI_MONITOR)
        self.assertEqual(monitor.transition.transition_id, "TR-039")


if __name__ == "__main__":
    unittest.main()
