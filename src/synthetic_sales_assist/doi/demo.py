"""Pure synthetic DOI demo fixtures mapped to the Milestone 3 scenario catalog.

This module promotes only deterministic fixture construction needed by the local CLI.  It
terminates at the real evaluator and run-control owner boundaries and has no persistence,
clock, filesystem, adapter, or network capability.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal

from synthetic_sales_assist.doi.evaluator import evaluate_doi
from synthetic_sales_assist.doi.fixtures import DOISyntheticScenario, scenario_catalog
from synthetic_sales_assist.doi.identities import (
    DoiOrderId,
    DoiRunId,
    DoiSnapshotId,
    LineSnapshotId,
    RunInvocationId,
)
from synthetic_sales_assist.doi.knowledge import DOIExactSKUObservation, exact_sku_candidate
from synthetic_sales_assist.doi.models import (
    AlternateAvailability,
    AlternateObservationState,
    AlternateResearchState,
    ContinuityProofType,
    DOIEvaluation,
    DOIEvaluationInput,
    DOILineItemSnapshot,
    DOIOrderSnapshot,
    DOIState,
    DedupeFinding,
    DedupeState,
    DropShipState,
    GeographyClass,
    LineActivity,
    LineAvailability,
    LineContinuityProof,
    LineContinuityState,
    OrderState,
    OpportunityType,
    PaymentCondition,
    QuantityAvailability,
    RepRelation,
    SourcePresence,
    WWCFinding,
    known_fact,
    model_action_context_fixture,
    not_applicable_fact,
    unknown_fact,
)
from synthetic_sales_assist.doi.source import (
    InMemoryDOIRunControl,
    RunStartResult,
    RunType,
)
from synthetic_sales_assist.domain.canonical import canonical_json_bytes, domain_hash
from synthetic_sales_assist.domain.identities import (
    EvaluationId,
    EvidenceId,
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


DEMO_OBSERVED_AT = CanonicalTimestamp("2026-08-20T14:15:16Z")


@dataclass(frozen=True, slots=True)
class DOIApplicationOracle:
    state: DOIState
    reasons: tuple[str, ...]
    opportunities: tuple[OpportunityType, ...]


@dataclass(frozen=True, slots=True)
class DOIDemoDefinition:
    alias: str
    scenario_key: str
    description: str
    application_oracle: DOIApplicationOracle | None = None


@dataclass(frozen=True, slots=True)
class DOIDemoExecution:
    definition: DOIDemoDefinition
    scenario: DOISyntheticScenario
    instance_key: str
    run_start: RunStartResult
    snapshot: DOIOrderSnapshot
    evaluation: DOIEvaluation


@dataclass(frozen=True, slots=True)
class DOIDemoFixture:
    """One immutable synthetic source instance before rule evaluation."""

    definition: DOIDemoDefinition
    scenario: DOISyntheticScenario
    instance_key: str
    run_start: RunStartResult
    request: DOIEvaluationInput

    @property
    def snapshot(self) -> DOIOrderSnapshot:
        return self.request.snapshot

    def evaluate(self) -> DOIDemoExecution:
        evaluation = evaluate_doi(self.request)
        expected_state = self.scenario.expected_top_level_state
        expected_reasons = tuple(reason.code for reason in self.scenario.expected_reasons)
        expected_opportunities = self.scenario.expected_opportunities
        oracle = self.definition.application_oracle
        if oracle is not None:
            expected_state = oracle.state
            expected_reasons = oracle.reasons
            expected_opportunities = oracle.opportunities
        if expected_state is None or evaluation.state is not expected_state:
            raise RuntimeError("DOI_DEMO_SCENARIO_RECONCILIATION_FAILED")
        if tuple(
            reason.code for reason in evaluation.reasons.reasons
        ) != expected_reasons:
            raise RuntimeError("DOI_DEMO_SCENARIO_RECONCILIATION_FAILED")
        if tuple(
            sorted(
                (item.opportunity_type for item in evaluation.opportunities),
                key=lambda item: item.value,
            )
        ) != expected_opportunities:
            raise RuntimeError("DOI_DEMO_SCENARIO_RECONCILIATION_FAILED")
        return DOIDemoExecution(
            self.definition,
            self.scenario,
            self.instance_key,
            self.run_start,
            self.snapshot,
            evaluation,
        )


DOI_DEMOS = (
    DOIDemoDefinition(
        "doi-fulfillment-split",
        "ORDINARY_FULFILLMENT_SPLIT",
        "Known in-stock and delayed lines preserve one fulfillment-split opportunity.",
    ),
    DOIDemoDefinition(
        "doi-full-ds",
        "FULL_DIRECT_SHIP",
        "A complete direct-ship order is excluded without a closure proposal.",
    ),
    DOIDemoDefinition(
        "doi-manual-review",
        "ONLY_CANDIDATE_BLOCKED_BY_UNKNOWN",
        "An unknown availability fact blocks the only safe opportunity.",
    ),
    DOIDemoDefinition(
        "doi-overlap",
        "OVERLAP_UNAVAILABLE_THEN_HUMAN_SELECTED",
        "Two independently valid overlapping opportunities remain separate.",
    ),
)
DOI_APPLICATION_FIXTURES = (
    DOIDemoDefinition(
        "doi-long-order",
        "LARGE_AND_ZERO_RELEVANT_ORDERS",
        "A complete long synthetic order preserves every relevant line.",
        DOIApplicationOracle(
            DOIState.DOI_OPPORTUNITY,
            ("RC-031", "RC-052"),
            (OpportunityType.FULFILLMENT_SPLIT,),
        ),
    ),
    DOIDemoDefinition(
        "doi-partial-quantity",
        "PARTIAL_QUANTITY_REVIEW",
        "A partially available quantity is presented as a review opportunity.",
        DOIApplicationOracle(
            DOIState.DOI_OPPORTUNITY,
            ("RC-032", "RC-052"),
            (OpportunityType.PARTIAL_QUANTITY_REVIEW,),
        ),
    ),
    DOIDemoDefinition(
        "doi-unknown-containment",
        "FULFILLMENT_SPLIT_WITH_UNRELATED_UNKNOWN",
        "An unrelated unknown fact does not erase a proved fulfillment split.",
        DOIApplicationOracle(
            DOIState.DOI_OPPORTUNITY,
            ("RC-016", "RC-031", "RC-052"),
            (OpportunityType.FULFILLMENT_SPLIT,),
        ),
    ),
    DOIDemoDefinition(
        "doi-dedupe-review",
        "DEDUPE_CANDIDATE_INCOMPLETE_AND_REJECTED",
        "A synthetic DEDUPE source finding remains a governed review decision.",
        DOIApplicationOracle(
            DOIState.DOI_MONITOR,
            ("RC-038", "RC-039", "RC-058"),
            (),
        ),
    ),
    DOIDemoDefinition(
        "doi-zero-lines",
        "LARGE_AND_ZERO_RELEVANT_ORDERS",
        "A complete synthetic order explicitly proves zero relevant lines.",
        DOIApplicationOracle(DOIState.DOI_MONITOR, (), ()),
    ),
)
_DEMO_BY_ALIAS = {
    definition.alias: definition
    for definition in (*DOI_DEMOS, *DOI_APPLICATION_FIXTURES)
}
_SCENARIO_BY_KEY = {scenario.scenario_key: scenario for scenario in scenario_catalog()}
_INSTANCE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$", re.ASCII)


def _instance_token(instance_key: str) -> str:
    if type(instance_key) is not str or _INSTANCE_KEY.fullmatch(instance_key) is None:
        raise ValueError("DOI_DEMO_INSTANCE_KEY_INVALID")
    digest = hashlib.sha256(instance_key.encode("ascii")).hexdigest().upper()
    return digest[:16]


def _order_id(instance: str) -> OrderId:
    return OrderId(f"SYN-ORDER-DOI-DEMO-{instance}")


def _usd(amount: str) -> Money:
    return Money(Decimal(amount), "USD", CURRENCY_REGISTRY_VERSION, 2)


def _order_source(order_id: OrderId, instance: str) -> SourceRef:
    return SourceRef.create(
        source_ref_id=EvidenceId(
            f"SYN-EVIDENCE-DOI-DEMO-ORDER-SOURCE-{instance}"
        ),
        source_kind=SourceKind.SYNTHETIC_ORDER_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_ORDER,
        object_id=order_id,
    )


def _line(
    index: int,
    source: SourceRef,
    *,
    snapshot_suffix: str,
    instance: str,
    drop_ship: object = DropShipState.NON_DS,
    availability: object = LineAvailability.DELAYED,
    quantity_availability: object = QuantityAvailability.NONE,
    explicitly_available: int = 0,
    ordered_quantity: int = 2,
    active_quantity: int = 2,
    canceled_quantity: int = 0,
) -> DOILineItemSnapshot:
    stable_id = EvidenceId(
        f"SYN-EVIDENCE-DOI-DEMO-STABLE-LINE-{instance}-{index:04d}"
    )
    return DOILineItemSnapshot(
        line_snapshot_id=LineSnapshotId(
            EvidenceId(
                f"SYN-EVIDENCE-DOI-DEMO-LINE-{instance}-{snapshot_suffix}-{index:04d}"
            )
        ),
        stable_source_line_id=known_fact(stable_id),
        relevant_merchandise=True,
        activity=known_fact(LineActivity.ACTIVE),
        drop_ship_state=(
            drop_ship if hasattr(drop_ship, "to_mapping") else known_fact(drop_ship)
        ),
        availability=(
            availability
            if hasattr(availability, "to_mapping")
            else known_fact(availability)
        ),
        eta=known_fact(DEMO_OBSERVED_AT),
        ordered_quantity=known_fact(Quantity(ordered_quantity)),
        active_quantity=known_fact(Quantity(active_quantity)),
        canceled_quantity=known_fact(Quantity(canceled_quantity)),
        explicitly_available_quantity=known_fact(Quantity(explicitly_available)),
        quantity_availability=known_fact(quantity_availability),
        es_number=known_fact(
            SkuId(f"SYN-SKU-DOI-DEMO-ES-{instance}-{index:04d}")
        ),
        mfg_number=known_fact(
            SkuId(f"SYN-SKU-DOI-DEMO-MFG-{instance}-{index:04d}")
        ),
        unit_value=known_fact(_usd("10.00")),
        active_line_value=known_fact(_usd("20.00")),
        line_sales_rep=known_fact(RepId("SYN-REP-TARGET-REP")),
        continuity=LineContinuityProof(
            state=LineContinuityState.VERIFIED,
            proof_type=ContinuityProofType.STABLE_SOURCE_LINE_ID,
            stable_source_line_id=stable_id,
            composite_binding=None,
        ),
        source=source,
    )


def _snapshot(
    lines: tuple[DOILineItemSnapshot, ...],
    suffix: str,
    instance: str,
    *,
    dedupe_present: bool = False,
) -> DOIOrderSnapshot:
    order = _order_id(instance)
    source = _order_source(order, instance)
    if any(line.source != source for line in lines):
        raise RuntimeError("DOI_DEMO_SOURCE_BINDING_INVALID")
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
            observed_at=DEMO_OBSERVED_AT,
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
        extractor=VersionBinding(
            "extractor",
            WholeOrderCompletenessProof.EXTRACTOR_VERSION,
        ),
        fixture=VersionBinding("fixture", WholeOrderCompletenessProof.FIXTURE_VERSION),
        order_source_observed_at=DEMO_OBSERVED_AT,
        proof_source_observed_at=DEMO_OBSERVED_AT,
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
    return DOIOrderSnapshot(
        snapshot_id=DoiSnapshotId(
            SnapshotId(f"SYN-SNAPSHOT-DOI-DEMO-{instance}-{suffix}")
        ),
        run_id=DoiRunId(RunId(f"SYN-RUN-DOI-DEMO-{instance}-{suffix}")),
        order_id=DoiOrderId(order),
        source_observed_at=DEMO_OBSERVED_AT,
        completeness_proof=proof,
        source_presence=SourcePresence.PRESENT,
        order_state=known_fact(OrderState.ACTIVE),
        current_rep_value=known_fact(RepId("SYN-REP-TARGET-REP")),
        current_rep_relation=known_fact(RepRelation.TARGET_REP_OWNED),
        geography_class=known_fact(GeographyClass.DOMESTIC_STANDARD),
        payment_condition=known_fact(PaymentCondition.NONE_OBSERVED),
        order_total=known_fact(_usd("100.00")),
        wwc_finding=WWCFinding(
            finding_id=EvidenceId(
                f"SYN-EVIDENCE-DOI-DEMO-WWC-{instance}-{suffix}"
            ),
            presence=FindingPresenceV2.NOT_PRESENT,
            author_relation=not_applicable_fact(),
            timing_state=not_applicable_fact(),
            marker=not_applicable_fact(),
            observed_at=not_applicable_fact(),
            source=source,
        ),
        dedupe_finding=DedupeFinding(
            finding_id=EvidenceId(
                f"SYN-EVIDENCE-DOI-DEMO-DEDUPE-{instance}-{suffix}"
            ),
            presence=(
                FindingPresenceV2.PRESENT
                if dedupe_present
                else FindingPresenceV2.NOT_PRESENT
            ),
            observed_at=DEMO_OBSERVED_AT if dedupe_present else None,
            state=DedupeState.SOURCE_PRESENT if dedupe_present else DedupeState.NOT_PRESENT,
            source=source,
        ),
        lines=lines,
    )


def _input(
    lines: tuple[DOILineItemSnapshot, ...],
    suffix: str,
    instance: str,
    *,
    alternate_candidates: tuple[object, ...] = (),
    alternate_research_state: AlternateResearchState = AlternateResearchState.NOT_STARTED,
    dedupe_present: bool = False,
) -> DOIEvaluationInput:
    return DOIEvaluationInput(
        evaluation_id=EvaluationId(
            f"SYN-EVALUATION-DOI-DEMO-{instance}-{suffix}"
        ),
        snapshot=_snapshot(lines, suffix, instance, dedupe_present=dedupe_present),
        evaluated_at=DEMO_OBSERVED_AT,
        alternate_research_state=alternate_research_state,
        alternate_candidates=alternate_candidates,  # type: ignore[arg-type]
    )


def _split_lines(
    suffix: str,
    instance: str,
) -> tuple[DOILineItemSnapshot, ...]:
    source = _order_source(_order_id(instance), instance)
    return (
        _line(
            1,
            source,
            snapshot_suffix=suffix,
            instance=instance,
            availability=LineAvailability.IN_STOCK,
            quantity_availability=QuantityAvailability.FULL,
            explicitly_available=2,
        ),
        _line(2, source, snapshot_suffix=suffix, instance=instance),
    )


def _request(
    definition: DOIDemoDefinition,
    instance: str,
) -> DOIEvaluationInput:
    source = _order_source(_order_id(instance), instance)
    if definition.alias == "doi-fulfillment-split":
        request = _input(
            _split_lines("FULFILLMENT-SPLIT", instance),
            "FULFILLMENT-SPLIT",
            instance,
        )
    elif definition.alias == "doi-full-ds":
        request = _input(
            (
                _line(
                    1,
                    source,
                    snapshot_suffix="FULL-DS",
                    instance=instance,
                    drop_ship=DropShipState.DS,
                    availability=LineAvailability.IN_STOCK,
                    quantity_availability=QuantityAvailability.FULL,
                    explicitly_available=2,
                ),
            ),
            "FULL-DS",
            instance,
        )
    elif definition.alias == "doi-manual-review":
        request = _input(
            (
                _line(
                    1,
                    source,
                    snapshot_suffix="MANUAL-REVIEW",
                    instance=instance,
                    availability=LineAvailability.IN_STOCK,
                    quantity_availability=QuantityAvailability.FULL,
                    explicitly_available=2,
                ),
                _line(
                    2,
                    source,
                    snapshot_suffix="MANUAL-REVIEW",
                    instance=instance,
                    availability=unknown_fact("RC-016"),
                    quantity_availability=QuantityAvailability.NONE,
                ),
            ),
            "MANUAL-REVIEW",
            instance,
        )
    elif definition.alias == "doi-overlap":
        lines = _split_lines("OVERLAP", instance)
        base = _input(lines, "OVERLAP", instance)
        context = model_action_context_fixture()
        sku = SkuId(f"SYN-SKU-DOI-DEMO-ES-{instance}-0001")
        product_source = SourceRef.create(
            source_ref_id=EvidenceId(
                f"SYN-EVIDENCE-DOI-DEMO-EXACT-SOURCE-{instance}"
            ),
            source_kind=SourceKind.SYNTHETIC_PRODUCT_FIXTURE,
            object_namespace=SourceObjectNamespace.SYNTHETIC_PRODUCT,
            object_id=sku,
        )
        observation = DOIExactSKUObservation(
            observation_id=EvidenceId(
                f"SYN-EVIDENCE-DOI-DEMO-EXACT-OBSERVATION-{instance}"
            ),
            action_context_id=context.action_context_id,
            action_context_binding=context.hash_binding(),
            ordered_line_id=lines[0].line_snapshot_id,
            ordered_sku=sku,
            observed_sku=sku,
            state=AlternateObservationState.CURRENT,
            observed_availability=AlternateAvailability.IN_STOCK,
            potential_unit_value=_usd("10.00"),
            observed_at=DEMO_OBSERVED_AT,
            source=product_source,
        )
        candidate = exact_sku_candidate(
            candidate_id=EvidenceId(
                f"SYN-EVIDENCE-DOI-DEMO-EXACT-CANDIDATE-{instance}"
            ),
            quantity=PositiveQuantity(1),
            observation=observation,
        )
        request = _input(
            lines,
            "OVERLAP",
            instance,
            alternate_candidates=(candidate,),
        )
        if request.snapshot.hash_binding() != base.snapshot.hash_binding():
            raise RuntimeError("DOI_DEMO_OVERLAP_INPUT_DRIFT")
    elif definition.alias == "doi-long-order":
        lines = tuple(
            _line(
                index,
                source,
                snapshot_suffix="LONG-ORDER",
                instance=instance,
                availability=(
                    LineAvailability.IN_STOCK
                    if index % 2
                    else LineAvailability.DELAYED
                ),
                quantity_availability=(
                    QuantityAvailability.FULL
                    if index % 2
                    else QuantityAvailability.NONE
                ),
                explicitly_available=2 if index % 2 else 0,
            )
            for index in range(1, 65)
        )
        request = _input(lines, "LONG-ORDER", instance)
    elif definition.alias == "doi-partial-quantity":
        request = _input(
            (
                _line(
                    1,
                    source,
                    snapshot_suffix="PARTIAL-QUANTITY",
                    instance=instance,
                    availability=LineAvailability.IN_STOCK,
                    quantity_availability=QuantityAvailability.PARTIAL,
                    explicitly_available=1,
                    ordered_quantity=3,
                    active_quantity=3,
                ),
            ),
            "PARTIAL-QUANTITY",
            instance,
        )
    elif definition.alias == "doi-unknown-containment":
        lines = (*_split_lines("UNKNOWN-CONTAINMENT", instance),)
        request = _input(
            (
                *lines,
                _line(
                    3,
                    source,
                    snapshot_suffix="UNKNOWN-CONTAINMENT",
                    instance=instance,
                    availability=unknown_fact("RC-016"),
                    quantity_availability=QuantityAvailability.NONE,
                ),
            ),
            "UNKNOWN-CONTAINMENT",
            instance,
        )
    elif definition.alias == "doi-dedupe-review":
        request = _input(
            (
                _line(
                    1,
                    source,
                    snapshot_suffix="DEDUPE-REVIEW",
                    instance=instance,
                ),
            ),
            "DEDUPE-REVIEW",
            instance,
            alternate_research_state=AlternateResearchState.COMPLETE,
            dedupe_present=True,
        )
    elif definition.alias == "doi-zero-lines":
        request = _input((), "ZERO-LINES", instance)
    else:
        raise KeyError(definition.alias)
    return request


def build_doi_demo_fixture(
    alias: str,
    *,
    instance_key: str = "default",
) -> DOIDemoFixture:
    """Build a source-bound demo instance without executing business rules."""

    definition = _DEMO_BY_ALIAS.get(alias)
    if definition is None:
        raise KeyError(alias)
    instance = _instance_token(instance_key)
    scenario = _SCENARIO_BY_KEY[definition.scenario_key]
    request = _request(definition, instance)
    control = InMemoryDOIRunControl()
    run_start = control.begin_recheck_run(
        run_id=request.snapshot.run_id.value,
        invocation_id=RunInvocationId(
            InteractionId(
                f"SYN-INTERACTION-DOI-DEMO-RUN-{instance}-{alias.upper()}"
            )
        ),
        run_type=RunType.RECHECK_ORDER,
        order_id=request.snapshot.order_id.value,
        accepted_at=DEMO_OBSERVED_AT,
    )
    return DOIDemoFixture(definition, scenario, instance_key, run_start, request)


def execute_doi_demo(
    alias: str,
    *,
    instance_key: str = "default",
) -> DOIDemoExecution:
    """Execute one stable alias through the real evaluator and run-control boundaries."""

    fixture = build_doi_demo_fixture(alias, instance_key=instance_key)
    return fixture.evaluate()


__all__ = [
    "DEMO_OBSERVED_AT",
    "DOI_APPLICATION_FIXTURES",
    "DOIApplicationOracle",
    "DOI_DEMOS",
    "DOIDemoDefinition",
    "DOIDemoExecution",
    "DOIDemoFixture",
    "build_doi_demo_fixture",
    "execute_doi_demo",
]
