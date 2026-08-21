"""Executable synthetic inputs and normalized observations for DOI catalog reconciliation.

This is test support, not a second rule engine.  Every builder terminates at the real
``evaluate_doi`` owner boundary, and normalization reads only the immutable returned record.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from synthetic_sales_assist.doi.evaluator import evaluate_doi
from synthetic_sales_assist.doi.fixtures import ScenarioEffect, ScopeExpectation
from synthetic_sales_assist.doi.knowledge import exact_sku_candidate
from synthetic_sales_assist.doi.models import (
    AlternateResearchState,
    AlternateRelationshipType,
    AttentionCondition,
    CompatibilityDecision,
    ContinuityProofType,
    DOIEvaluation,
    DOIEvaluationInput,
    DOIMutualExclusionEvidence,
    DOIState,
    DropShipState,
    GeographyClass,
    HandlingFlag,
    HumanFactResultCode,
    HumanFactUsageKind,
    HumanReviewKind,
    LineAvailability,
    LineContinuityState,
    OpportunityType,
    OrderState,
    PaymentCondition,
    QuantityAvailability,
    RepRelation,
    ScenarioSelection,
    SourcePresence,
    TerminalClosureReason,
    ValueAvailabilityState,
    unknown_fact,
)
from synthetic_sales_assist.domain.identities import EvidenceId, OrderId
from synthetic_sales_assist.domain.numeric import PositiveQuantity
from synthetic_sales_assist.domain.observed import FindingPresenceV2
from tests.test_doi_evaluator import (
    evaluation_input,
    exact_observation,
    human_fact,
    relationship_candidate,
    split_lines,
)
from tests.test_doi_models import make_line, order_source


SUPPORTED_EVALUATION_SCENARIOS = frozenset(
    {
        "ALL_IN_STOCK_PROGRESS_REVIEW",
        "CANCELED_HARD_CLOSURE",
        "DISJOINT_MUTUALLY_EXCLUSIVE_OPTIONS",
        "DOMESTIC_SPECIAL_REVIEW_SPLIT",
        "EXACT_MFG_ALTERNATE",
        "EXACT_SKU_RECHECK",
        "FULFILLMENT_SPLIT_WITH_UNRELATED_UNKNOWN",
        "FULFILLMENT_SPLIT_WITH_UNRELATED_UNKNOWN_DS",
        "FULL_DIRECT_SHIP",
        "FUNCTIONAL_ALTERNATE",
        "HUMAN_NO_ACTION_MONITOR",
        "HUMAN_OUT_OF_SCOPE_REVERSIBLE_CLOSURE",
        "HUMAN_SCENARIO_SELECTION_RESOLVES_AGGREGATE",
        "INTERNATIONAL_SPLIT",
        "INTERNATIONAL_SPLIT_WITH_UNKNOWN_ETA",
        "MANUAL_ALTERNATE_IDENTIFICATION",
        "MFG_CROSS_REFERENCE",
        "MFG_SUPERSESSION",
        "MIXED_DIRECT_SHIP",
        "MULTI_UNKNOWN_EXACT_SET_UNION",
        "NO_EXACT_MFG_OR_VERIFIED_ALTERNATE",
        "ONLY_CANDIDATE_BLOCKED_BY_UNKNOWN",
        "ORDINARY_FULFILLMENT_SPLIT",
        "OVERLAP_UNAVAILABLE_THEN_HUMAN_SELECTED",
        "PARTIAL_QUANTITY_REVIEW",
        "PAYMENT_ONLY_EXCLUSION",
        "PAYMENT_WITH_SPLIT_OPPORTUNITY",
        "REP_TRANSFER_REVERSIBLE_CLOSURE",
        "SHIPPED_HARD_CLOSURE",
        "SOURCE_ABSENCE_RECHECK",
        "UNKNOWN_CONTINUITY_PRESERVES_INDEPENDENT_SPLIT",
        "UNKNOWN_GEOGRAPHY_SPLIT",
    }
)


@dataclass(frozen=True, slots=True)
class EvaluatedScenarioDimensions:
    """All catalog dimensions observable from one real DOI evaluation result."""

    state: DOIState
    reasons: tuple[str, ...]
    opportunities: tuple[OpportunityType, ...]
    scope: ScopeExpectation
    reviews: tuple[HumanReviewKind, ...]
    attention: tuple[AttentionCondition, ...]
    closure: TerminalClosureReason | None
    transitions: tuple[str, ...]
    effects: tuple[ScenarioEffect, ...]
    value: ValueAvailabilityState


def _scenario_scope(result: DOIEvaluation) -> ScopeExpectation:
    if not result.opportunities:
        return ScopeExpectation.NONE
    if len(result.opportunities) > 1:
        return ScopeExpectation.PRESERVED_SEPARATE
    line_ids = {
        component.line_snapshot_id
        for opportunity in result.opportunities
        for component in opportunity.scope.components
    }
    if len(line_ids) == 1:
        return ScopeExpectation.EXACT_SINGLE
    return ScopeExpectation.EXACT_MULTI_LINE


def observe_evaluation(result: DOIEvaluation) -> EvaluatedScenarioDimensions:
    """Normalize a real immutable evaluation without restating any business rule."""

    attention: set[AttentionCondition] = set()
    if HandlingFlag.SOURCE_ABSENCE_RECHECK_REQUIRED in result.handling_flags:
        attention.add(AttentionCondition.SOURCE_ABSENCE_RECHECK_REQUIRED)
    effects = {
        ScenarioEffect.APPEND_EVALUATION,
        ScenarioEffect.NO_DURABLE_BUSINESS_PERSISTENCE,
        ScenarioEffect.NO_EXTERNAL_MUTATION,
    }
    if result.closure_proposal is not None:
        effects.add(ScenarioEffect.CLOSE_CASE)
    if attention:
        effects.add(ScenarioEffect.SET_ATTENTION)
    transitions = {result.transition.transition_id}
    transitions.update(item.transition_id for item in result.append_transitions)
    return EvaluatedScenarioDimensions(
        state=result.state,
        reasons=tuple(reason.code for reason in result.reasons.reasons),
        opportunities=tuple(
            sorted(
                {item.opportunity_type for item in result.opportunities},
                key=lambda item: item.value,
            )
        ),
        scope=_scenario_scope(result),
        reviews=result.human_review_requirements,
        attention=tuple(sorted(attention, key=lambda item: item.value)),
        closure=(
            None
            if result.closure_proposal is None
            else result.closure_proposal.reason
        ),
        transitions=tuple(sorted(transitions)),
        effects=tuple(sorted(effects, key=lambda item: item.value)),
        value=result.aggregate_potential_state,
    )


def _overlap_evaluation(*, selected: bool) -> DOIEvaluation:
    suffix = "SCENARIO-OVERLAP"
    base = evaluation_input(split_lines(), evaluation_suffix=suffix)
    exact = exact_sku_candidate(
        candidate_id=EvidenceId("SYN-EVIDENCE-DOI-CANDIDATE-SCENARIO-OVERLAP"),
        quantity=PositiveQuantity(1),
        observation=exact_observation(base, suffix="SCENARIO-OVERLAP"),
    )
    request = evaluation_input(
        split_lines(),
        evaluation_suffix=suffix,
        alternate_candidates=(exact,),
    )
    unresolved = evaluate_doi(request)
    if not selected:
        return unresolved
    selected_opportunity = next(
        item
        for item in unresolved.opportunities
        if item.opportunity_type is OpportunityType.EXACT_SKU_RECHECK
    )
    selection_fact = human_fact(
        request,
        usage=HumanFactUsageKind.SCENARIO_SELECTION,
        result=HumanFactResultCode.SCENARIO_SELECTED,
        suffix="SCENARIO-OVERLAP-SELECTION",
        opportunity_id=selected_opportunity.opportunity_id,
    )
    selection = ScenarioSelection(
        selection_id=EvidenceId("SYN-EVIDENCE-DOI-SELECTION-SCENARIO-OVERLAP"),
        selected_opportunity_id=selected_opportunity.opportunity_id,
        option_opportunity_ids=tuple(
            sorted(
                (item.opportunity_id for item in unresolved.opportunities),
                key=lambda item: item.value,
            )
        ),
        human_fact_binding=selection_fact.hash_binding(),
    )
    return evaluate_doi(
        evaluation_input(
            split_lines(),
            evaluation_suffix=suffix,
            alternate_candidates=(exact,),
            scenario_selection=selection,
            human_facts=(selection_fact,),
        )
    )


def _disjoint_mutually_exclusive_evaluation() -> DOIEvaluation:
    source = order_source(OrderId("SYN-ORDER-DOI-0001"))
    lines = (make_line(1, source), make_line(2, source))
    suffix = "SCENARIO-DISJOINT"
    base = evaluation_input(lines, evaluation_suffix=suffix)
    ungrouped = tuple(
        exact_sku_candidate(
            candidate_id=EvidenceId(
                f"SYN-EVIDENCE-DOI-DISJOINT-SCENARIO-CANDIDATE-{index + 1:04d}"
            ),
            quantity=PositiveQuantity(1),
            observation=exact_observation(
                base,
                line_index=index,
                suffix=f"SCENARIO-DISJOINT-{index + 1:04d}",
            ),
        )
        for index in range(2)
    )
    group_id = EvidenceId("SYN-EVIDENCE-DOI-SCENARIO-GROUP-DISJOINT-ORACLE")
    grouping_fact = human_fact(
        base,
        usage=HumanFactUsageKind.SCENARIO_GROUPING,
        result=HumanFactResultCode.SCENARIO_GROUPED,
        suffix="SCENARIO-DISJOINT-GROUP",
    )
    grouping = DOIMutualExclusionEvidence(
        evidence_id=EvidenceId(
            "SYN-EVIDENCE-DOI-SCENARIO-GROUP-EVIDENCE-DISJOINT-ORACLE"
        ),
        group_id=group_id,
        candidate_ids=tuple(
            sorted((item.candidate_id for item in ungrouped), key=lambda item: item.value)
        ),
        human_fact=grouping_fact,
    )
    candidates = tuple(
        dataclasses.replace(
            candidate,
            mutual_exclusion_group=group_id,
            mutual_exclusion_evidence=grouping,
        )
        for candidate in ungrouped
    )
    return evaluate_doi(
        evaluation_input(
            lines,
            evaluation_suffix=suffix,
            alternate_candidates=candidates,
            human_facts=(grouping_fact,),
        )
    )


def _alternate_evaluation(
    relationship_type: AlternateRelationshipType,
    compatibility: CompatibilityDecision,
    suffix: str,
) -> DOIEvaluation:
    source = order_source(OrderId("SYN-ORDER-DOI-0001"))
    lines = (make_line(1, source),)
    base = evaluation_input(lines, evaluation_suffix=suffix)
    candidate = relationship_candidate(
        base,
        relationship_type=relationship_type,
        compatibility=compatibility,
        suffix=suffix,
    )
    return evaluate_doi(
        evaluation_input(
            lines,
            evaluation_suffix=suffix,
            alternate_candidates=(candidate,),
        )
    )


def execute_evaluation_scenario(scenario_key: str) -> DOIEvaluation:
    """Execute one catalog evaluation scenario through the real DOI rule owner."""

    if scenario_key not in SUPPORTED_EVALUATION_SCENARIOS:
        raise KeyError(f"unsupported evaluation scenario: {scenario_key}")
    source = order_source(OrderId("SYN-ORDER-DOI-0001"))

    if scenario_key == "FULL_DIRECT_SHIP":
        line = make_line(
            1,
            source,
            drop_ship=DropShipState.DS,
            availability=LineAvailability.IN_STOCK,
            quantity_availability=QuantityAvailability.FULL,
            explicitly_available=2,
        )
        return evaluate_doi(evaluation_input((line,), evaluation_suffix="SCENARIO-FULL-DS"))
    if scenario_key == "MIXED_DIRECT_SHIP":
        return evaluate_doi(
            evaluation_input(
                (
                    make_line(1, source, drop_ship=DropShipState.DS),
                    make_line(2, source),
                ),
                evaluation_suffix="SCENARIO-MIXED-DS",
            )
        )
    if scenario_key == "ORDINARY_FULFILLMENT_SPLIT":
        return evaluate_doi(
            evaluation_input(split_lines(), evaluation_suffix="SCENARIO-SPLIT")
        )
    if scenario_key == "FULFILLMENT_SPLIT_WITH_UNRELATED_UNKNOWN":
        unknown_line = make_line(
            3,
            source,
            availability=unknown_fact("RC-016"),
            quantity_availability=QuantityAvailability.NONE,
        )
        return evaluate_doi(
            evaluation_input(
                split_lines(third=unknown_line),
                evaluation_suffix="SCENARIO-UNKNOWN-AVAILABILITY",
            )
        )
    if scenario_key == "FULFILLMENT_SPLIT_WITH_UNRELATED_UNKNOWN_DS":
        unknown_line = make_line(
            3,
            source,
            drop_ship=unknown_fact("RC-017"),
            availability=LineAvailability.DELAYED,
            quantity_availability=QuantityAvailability.NONE,
        )
        return evaluate_doi(
            evaluation_input(
                split_lines(third=unknown_line),
                evaluation_suffix="SCENARIO-UNKNOWN-DS",
            )
        )
    if scenario_key == "ONLY_CANDIDATE_BLOCKED_BY_UNKNOWN":
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
        return evaluate_doi(
            evaluation_input(lines, evaluation_suffix="SCENARIO-ONLY-BLOCKED")
        )
    if scenario_key == "UNKNOWN_CONTINUITY_PRESERVES_INDEPENDENT_SPLIT":
        lines = split_lines()
        unverified = dataclasses.replace(
            lines[0].continuity,
            state=LineContinuityState.UNVERIFIED,
            proof_type=ContinuityProofType.NONE,
            stable_source_line_id=None,
        )
        first = dataclasses.replace(
            lines[0],
            stable_source_line_id=unknown_fact("RC-124"),
            continuity=unverified,
        )
        return evaluate_doi(
            evaluation_input(
                (first, lines[1]),
                evaluation_suffix="SCENARIO-UNKNOWN-CONTINUITY",
            )
        )
    if scenario_key == "MULTI_UNKNOWN_EXACT_SET_UNION":
        line = make_line(
            1,
            source,
            availability=unknown_fact("RC-016"),
            drop_ship=unknown_fact("RC-017"),
            eta=unknown_fact("RC-115"),
            quantity_availability=QuantityAvailability.NONE,
        )
        base = evaluation_input((line,), evaluation_suffix="SCENARIO-MULTI-UNKNOWN")
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
        return evaluate_doi(dataclasses.replace(base, snapshot=snapshot))
    if scenario_key == "PARTIAL_QUANTITY_REVIEW":
        line = make_line(
            1,
            source,
            availability=LineAvailability.IN_STOCK,
            quantity_availability=QuantityAvailability.PARTIAL,
            active_quantity=3,
            explicitly_available=1,
        )
        return evaluate_doi(
            evaluation_input((line,), evaluation_suffix="SCENARIO-PARTIAL")
        )
    if scenario_key == "PAYMENT_ONLY_EXCLUSION":
        return evaluate_doi(
            evaluation_input(
                (make_line(1, source),),
                evaluation_suffix="SCENARIO-PAYMENT-ONLY",
                payment=PaymentCondition.PRESENT,
            )
        )
    if scenario_key == "PAYMENT_WITH_SPLIT_OPPORTUNITY":
        return evaluate_doi(
            evaluation_input(
                split_lines(),
                evaluation_suffix="SCENARIO-PAYMENT-SPLIT",
                payment=PaymentCondition.PRESENT,
            )
        )
    if scenario_key == "ALL_IN_STOCK_PROGRESS_REVIEW":
        line = make_line(
            1,
            source,
            availability=LineAvailability.IN_STOCK,
            quantity_availability=QuantityAvailability.FULL,
            explicitly_available=2,
        )
        return evaluate_doi(
            evaluation_input((line,), evaluation_suffix="SCENARIO-PROGRESS")
        )
    if scenario_key == "HUMAN_NO_ACTION_MONITOR":
        base = evaluation_input(
            (make_line(1, source),),
            evaluation_suffix="SCENARIO-NO-ACTION",
        )
        fact = human_fact(
            base,
            usage=HumanFactUsageKind.NO_ACTION_DECISION,
            result=HumanFactResultCode.APPROVED,
            suffix="SCENARIO-NO-ACTION",
        )
        return evaluate_doi(dataclasses.replace(base, human_facts=(fact,)))
    if scenario_key in {
        "SHIPPED_HARD_CLOSURE",
        "CANCELED_HARD_CLOSURE",
        "REP_TRANSFER_REVERSIBLE_CLOSURE",
    }:
        changes: dict[str, object]
        if scenario_key == "SHIPPED_HARD_CLOSURE":
            changes = {"order_state": OrderState.SHIPPED}
        elif scenario_key == "CANCELED_HARD_CLOSURE":
            changes = {"order_state": OrderState.CANCELED}
        else:
            changes = {"rep_relation": RepRelation.OTHER_REP}
        return evaluate_doi(
            evaluation_input(
                split_lines(),
                evaluation_suffix=f"SCENARIO-{scenario_key.replace('_', '-')}",
                **changes,
            )
        )
    if scenario_key == "HUMAN_OUT_OF_SCOPE_REVERSIBLE_CLOSURE":
        base = evaluation_input(
            (make_line(1, source),),
            evaluation_suffix="SCENARIO-OUT-OF-SCOPE",
        )
        fact = human_fact(
            base,
            usage=HumanFactUsageKind.OUT_OF_SCOPE_CLOSURE,
            result=HumanFactResultCode.OUT_OF_SCOPE,
            suffix="SCENARIO-OUT-OF-SCOPE",
        )
        return evaluate_doi(dataclasses.replace(base, human_facts=(fact,)))
    if scenario_key == "SOURCE_ABSENCE_RECHECK":
        base = evaluation_input(
            split_lines(),
            evaluation_suffix="SCENARIO-SOURCE-ABSENT",
            order_state=OrderState.SHIPPED,
        )
        snapshot = dataclasses.replace(
            base.snapshot,
            source_presence=SourcePresence.ABSENT_RECHECK_REQUIRED,
        )
        return evaluate_doi(dataclasses.replace(base, snapshot=snapshot))
    geography_by_key = {
        "DOMESTIC_SPECIAL_REVIEW_SPLIT": GeographyClass.DOMESTIC_SPECIAL_REVIEW,
        "INTERNATIONAL_SPLIT": GeographyClass.INTERNATIONAL,
        "UNKNOWN_GEOGRAPHY_SPLIT": unknown_fact("RC-119"),
    }
    if scenario_key in geography_by_key:
        return evaluate_doi(
            evaluation_input(
                split_lines(),
                evaluation_suffix=f"SCENARIO-{scenario_key.replace('_', '-')}",
                geography=geography_by_key[scenario_key],
            )
        )
    if scenario_key == "INTERNATIONAL_SPLIT_WITH_UNKNOWN_ETA":
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
        return evaluate_doi(
            evaluation_input(
                lines,
                evaluation_suffix="SCENARIO-INTERNATIONAL-UNKNOWN-ETA",
                geography=GeographyClass.INTERNATIONAL,
            )
        )
    if scenario_key == "OVERLAP_UNAVAILABLE_THEN_HUMAN_SELECTED":
        return _overlap_evaluation(selected=False)
    if scenario_key == "HUMAN_SCENARIO_SELECTION_RESOLVES_AGGREGATE":
        return _overlap_evaluation(selected=True)
    if scenario_key == "DISJOINT_MUTUALLY_EXCLUSIVE_OPTIONS":
        return _disjoint_mutually_exclusive_evaluation()
    if scenario_key == "EXACT_SKU_RECHECK":
        lines = (make_line(1, source),)
        base = evaluation_input(lines, evaluation_suffix="SCENARIO-EXACT-SKU")
        candidate = exact_sku_candidate(
            candidate_id=EvidenceId("SYN-EVIDENCE-DOI-CANDIDATE-SCENARIO-EXACT-SKU"),
            quantity=PositiveQuantity(1),
            observation=exact_observation(base, suffix="SCENARIO-EXACT-SKU"),
        )
        return evaluate_doi(
            evaluation_input(
                lines,
                evaluation_suffix="SCENARIO-EXACT-SKU",
                alternate_candidates=(candidate,),
            )
        )
    alternates = {
        "EXACT_MFG_ALTERNATE": (
            AlternateRelationshipType.EXACT_MFG,
            CompatibilityDecision.NOT_REQUIRED,
        ),
        "MFG_CROSS_REFERENCE": (
            AlternateRelationshipType.MFG_CROSS_REFERENCE,
            CompatibilityDecision.NOT_REQUIRED,
        ),
        "MFG_SUPERSESSION": (
            AlternateRelationshipType.MFG_SUPERSESSION,
            CompatibilityDecision.NOT_REQUIRED,
        ),
        "FUNCTIONAL_ALTERNATE": (
            AlternateRelationshipType.FUNCTIONAL,
            CompatibilityDecision.APPROVED,
        ),
    }
    if scenario_key in alternates:
        relationship_type, compatibility = alternates[scenario_key]
        return _alternate_evaluation(
            relationship_type,
            compatibility,
            f"SCENARIO-{scenario_key.replace('_', '-')}",
        )
    if scenario_key == "NO_EXACT_MFG_OR_VERIFIED_ALTERNATE":
        return evaluate_doi(
            evaluation_input(
                (make_line(1, source),),
                evaluation_suffix="SCENARIO-NO-ALTERNATE",
                alternate_research_state=AlternateResearchState.COMPLETE,
            )
        )
    if scenario_key == "MANUAL_ALTERNATE_IDENTIFICATION":
        return evaluate_doi(
            evaluation_input(
                (make_line(1, source),),
                evaluation_suffix="SCENARIO-MANUAL-ALTERNATE",
                alternate_research_state=(
                    AlternateResearchState.MANUAL_IDENTIFICATION_REQUIRED
                ),
            )
        )
    raise AssertionError(f"unreachable scenario dispatch: {scenario_key}")


__all__ = [
    "EvaluatedScenarioDimensions",
    "SUPPORTED_EVALUATION_SCENARIOS",
    "execute_evaluation_scenario",
    "observe_evaluation",
]
