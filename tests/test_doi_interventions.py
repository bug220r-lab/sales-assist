from __future__ import annotations

import dataclasses
import unittest
from unittest.mock import patch

from synthetic_sales_assist.doi.identities import DoiOrderId, LineSnapshotId
from synthetic_sales_assist.doi.interventions import (
    AcceptedHumanFactProof,
    ActionVerificationEvent,
    AuthorizedHumanExactValueRecord,
    AuthorizedHumanResultingLinkEvidence,
    CompletedHumanActionProof,
    CompletedSystemActionProof,
    DOIIntervention,
    DOIResultingOrderLinkSearchHistory,
    DOIResultingOrderLinkSearch,
    EvidenceKeyKind,
    HumanValueInexactKind,
    INTERVENTION_HASH_KNOWN_ANSWERS,
    InterventionError,
    LogicalEvidenceKey,
    MovedLineMappingComponent,
    ResultingOrderLinkRevision,
    ResultingLinkSearchEvidence,
    SystemExactValueRecord,
    SystemResultingLinkEvidence,
    TARGET_REP_ID,
    TargetRepProofScope,
    TargetRepObservation,
    TargetRepVerificationProof,
    ValueCorrectionKind,
    ValueEvent,
    VerificationEvidence,
    append_resulting_link_revision,
    append_resulting_link_search,
    append_value_event,
    intervention_hash_contracts,
    intervention_hash_fixtures,
    record_verified_intervention,
    reject_inexact_human_value,
    require_verified_action,
    require_verified_reversal_record,
)
from synthetic_sales_assist.doi.models import (
    ActionContextKind,
    ActionContextCloseReason,
    ActionContextCompletionTrigger,
    ActionContextEventType,
    ActionContextState,
    ActionVerificationState,
    DOIActionContext,
    DOIActionContextEvent,
    DOIActionContextHistory,
    DOIHumanFactEvent,
    DOIHumanFactHistory,
    DOIOccurrenceGuard,
    InterventionStatus,
    InterventionType,
    AlternateRelationshipType,
    CompatibilityDecision,
    DropShipState,
    HumanFactEventType,
    HumanFactResultCode,
    HumanFactUsageKind,
    OpportunityType,
    RepRelation,
    StructuredHumanFact,
    ResultingOrderLinkSearchState,
    ResultingOrderLinkState,
    ValueEventType,
    ValueVerificationState,
    reduce_action_context,
    reduce_human_fact,
    verify_synthetic_human_authority,
)
from synthetic_sales_assist.domain.canonical import canonical_json_bytes, domain_hash
from synthetic_sales_assist.domain.identities import (
    EvidenceId,
    EvaluationId,
    InteractionId,
    OrderId,
    RepId,
)
from synthetic_sales_assist.domain.numeric import (
    CURRENCY_REGISTRY_VERSION,
    Money,
    PositiveQuantity,
)
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.domain.records import (
    SourceKind,
    SourceObjectNamespace,
    SourceRef,
)
from synthetic_sales_assist.safety.content import ProhibitedFinding, ProhibitedInputError
from synthetic_sales_assist.doi.evaluator import evaluate_doi
from tests.test_doi_evaluator import evaluation_input, relationship_candidate, split_lines
from tests.test_doi_models import make_line, open_context_fixture, order_source


NOW = CanonicalTimestamp("2026-08-20T16:00:00Z")
PARENT = DoiOrderId(OrderId("SYN-ORDER-DOI-0001"))
CHILD = DoiOrderId(OrderId("SYN-ORDER-CHILD-001"))
OPPORTUNITY_ID = EvidenceId("SYN-EVIDENCE-OPPORTUNITY-001")
INTERVENTION_ID = EvidenceId("SYN-EVIDENCE-INTERVENTION-001")
LINK_ID = EvidenceId("SYN-EVIDENCE-LINK-001")


def _money(cents: int, currency: str = "USD") -> Money:
    scale = 0 if currency == "JPY" else 2
    return Money.from_minor_units(
        cents,
        currency_code=currency,
        registry_version=CURRENCY_REGISTRY_VERSION,
        scale=scale,
    )


def _content(domain: str, marker: str):  # type: ignore[no-untyped-def]
    value = {"marker": marker}
    return domain_hash(domain, canonical_json_bytes(value, expected_members=set(value)))


def _tampered_action_event(
    event: DOIActionContextEvent,
    **changes: object,
) -> DOIActionContextEvent:
    """Simulate hostile deserialization without weakening the sealed production API."""

    clone = object.__new__(DOIActionContextEvent)
    for definition in dataclasses.fields(DOIActionContextEvent):
        object.__setattr__(
            clone,
            definition.name,
            changes.get(definition.name, getattr(event, definition.name)),
        )
    return clone


def _tampered_action_history(
    history: DOIActionContextHistory,
    events: tuple[DOIActionContextEvent, ...],
) -> DOIActionContextHistory:
    """Simulate a corrupted retained stream for proof-boundary rejection tests."""

    clone = object.__new__(DOIActionContextHistory)
    object.__setattr__(clone, "action_context_id", history.action_context_id)
    object.__setattr__(clone, "projection", history.projection)
    object.__setattr__(clone, "events", events)
    return clone


def _order_source(order: DoiOrderId, suffix: str) -> SourceRef:
    return SourceRef.create(
        source_ref_id=EvidenceId(f"SYN-EVIDENCE-SOURCE-{suffix}"),
        source_kind=SourceKind.SYNTHETIC_ORDER_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_ORDER,
        object_id=order.value,
    )


def _interaction_source(suffix: str) -> SourceRef:
    return SourceRef.create(
        source_ref_id=EvidenceId(f"SYN-EVIDENCE-SOURCE-{suffix}"),
        source_kind=SourceKind.SYNTHETIC_INTERACTION_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_INTERACTION,
        object_id=InteractionId(f"SYN-INTERACTION-{suffix}"),
    )


def _owner_context(
    intervention_type: InterventionType,
) -> tuple[DOIActionContext, object]:
    source = order_source(PARENT.value)
    if intervention_type is InterventionType.FULFILLMENT_SPLIT:
        request = evaluation_input(
            split_lines(),
            evaluation_suffix="INTERVENTION-SPLIT-OWNER",
        )
        kind = ActionContextKind.FULFILLMENT_SPLIT_REVIEW
        expected = OpportunityType.FULFILLMENT_SPLIT
    elif intervention_type is InterventionType.DS_SEPARATION:
        request = evaluation_input(
            (
                make_line(1, source, drop_ship=DropShipState.DS),
                make_line(2, source),
            ),
            evaluation_suffix="INTERVENTION-DS-OWNER",
        )
        kind = ActionContextKind.DS_SEPARATION_REVIEW
        expected = OpportunityType.DS_SEPARATION
    else:
        lines = (make_line(1, source),)
        base = evaluation_input(
            lines,
            evaluation_suffix="INTERVENTION-SUBSTITUTION-BASE",
        )
        candidate = relationship_candidate(
            base,
            relationship_type=AlternateRelationshipType.EXACT_MFG,
            compatibility=CompatibilityDecision.NOT_REQUIRED,
            suffix="INTERVENTION-SUBSTITUTION",
        )
        request = evaluation_input(
            lines,
            evaluation_suffix="INTERVENTION-SUBSTITUTION-OWNER",
            alternate_candidates=(candidate,),
        )
        kind = ActionContextKind.SUBSTITUTION
        expected = OpportunityType.EXACT_MFG_ALTERNATE
    evaluation = evaluate_doi(request)
    opportunity = next(
        item for item in evaluation.opportunities if item.opportunity_type is expected
    )
    context, opening, _, _, _, _ = open_context_fixture(
        request.snapshot,
        f"INTERVENTION-{intervention_type.value.replace('_', '-')}",
        evaluation=evaluation,
        opportunity=opportunity,
        context_kind=kind,
    )
    return context, opening


def _completed_action_history(
    marker: str,
    completion_trigger: ActionContextCompletionTrigger,
    intervention_type: InterventionType = InterventionType.PRODUCT_SUBSTITUTION,
) -> DOIActionContextHistory:
    token = marker.upper()
    context, opening = _owner_context(intervention_type)
    opened = reduce_action_context(
        DOIActionContextHistory(action_context_id=context.action_context_id),
    opening,
    )
    open_context = opened.history.projection
    if open_context is None:
        raise AssertionError("action context did not open")
    completion_id = EvidenceId(
        f"SYN-EVIDENCE-ACTION-CONTEXT-COMPLETE-{token}"
    )
    completion_source = _interaction_source(
        f"ACTION-CONTEXT-COMPLETE-{token}"
    )
    authority = None
    if completion_trigger is ActionContextCompletionTrigger.HUMAN_ACCEPTED:
        authority = verify_synthetic_human_authority(
            grant_id=EvidenceId(
                f"SYN-EVIDENCE-ACTION-CONTEXT-AUTHORITY-{token}"
            ),
            actor=RepId("SYN-REP-AUTHORIZED-001"),
            action_context=open_context,
            granted_at=NOW,
            authority_source=completion_source,
        )
    completion = DOIActionContextEvent.completed(
        event_id=completion_id,
        action_context=open_context,
        completion_trigger=completion_trigger,
        occurred_at=NOW,
        authority=authority,
        close_reason=(
            ActionContextCloseReason.DECISION_RECORDED
            if completion_trigger is ActionContextCompletionTrigger.HUMAN_ACCEPTED
            else ActionContextCloseReason.ACTION_VERIFIED
        ),
        guard=DOIOccurrenceGuard(
            guard_id=completion_id,
            owner_id=context.action_context_id,
            occurrence_id=InteractionId(
                f"SYN-INTERACTION-ACTION-CONTEXT-COMPLETE-{token}"
            ),
            source=completion_source,
        ),
    )
    return reduce_action_context(opened.history, completion).history


def _human_action_history(marker: str) -> DOIActionContextHistory:
    return _completed_action_history(
        marker,
        ActionContextCompletionTrigger.HUMAN_ACCEPTED,
    )


def _action_context(marker: str = "context") -> DOIActionContext:
    context, opening = _owner_context(InterventionType.PRODUCT_SUBSTITUTION)
    reduced = reduce_action_context(
        DOIActionContextHistory(action_context_id=context.action_context_id),
        opening,
    )
    if reduced.history.projection is None:
        raise AssertionError(f"action context did not open: {marker}")
    return reduced.history.projection


def _system_action_history(
    marker: str,
    intervention_type: InterventionType = InterventionType.PRODUCT_SUBSTITUTION,
) -> DOIActionContextHistory:
    return _completed_action_history(
        marker,
        ActionContextCompletionTrigger.SYSTEM_VERIFIED,
        intervention_type,
    )


def _completed_system_action_proof(
    marker: str,
    intervention_type: InterventionType = InterventionType.PRODUCT_SUBSTITUTION,
) -> CompletedSystemActionProof:
    return CompletedSystemActionProof.from_history(
        history=_system_action_history(marker, intervention_type),
    )


def _completed_human_action_proof(
    marker: str,
    intervention_type: InterventionType = InterventionType.PRODUCT_SUBSTITUTION,
) -> CompletedHumanActionProof:
    history = _completed_action_history(
        marker,
        ActionContextCompletionTrigger.HUMAN_ACCEPTED,
        intervention_type,
    )
    authority_context = DOIActionContext.from_event(history.events[0])
    authority = verify_synthetic_human_authority(
        grant_id=EvidenceId(
            f"SYN-EVIDENCE-ACTION-CONTEXT-AUTHORITY-{marker.upper()}"
        ),
        actor=RepId("SYN-REP-AUTHORIZED-001"),
        action_context=authority_context,
        granted_at=NOW,
        authority_source=history.events[-1].guard.source,
    )
    return CompletedHumanActionProof.from_history(
        history=history,
        authority=authority,
    )


def _action(
    *,
    verification: ActionVerificationState = ActionVerificationState.SYSTEM_VERIFIED,
    event_id: str = "SYN-EVIDENCE-ACTION-EVENT-001",
    evidence_id: str = "SYN-EVIDENCE-ACTION-PROOF-001",
    key_id: str = "SYN-EVIDENCE-ACTION-KEY-001",
    intervention_type: InterventionType = InterventionType.PRODUCT_SUBSTITUTION,
    marker: str = "action",
    occurred_at: CanonicalTimestamp | None = NOW,
    intervention_id: EvidenceId = INTERVENTION_ID,
) -> ActionVerificationEvent:
    if verification is ActionVerificationState.SYSTEM_VERIFIED:
        proof = _completed_system_action_proof(marker, intervention_type)
        evidence = VerificationEvidence.from_system_observation(
            evidence_id=EvidenceId(evidence_id),
            intervention_id=intervention_id,
            opportunity_id=proof.completed_context.opportunity_id,
            intervention_type=intervention_type,
            completed_action_proof=proof,
            source=_order_source(proof.completed_context.order_id, "ACTION-ORDER"),
            occurred_at=occurred_at,
        )
    elif verification is ActionVerificationState.HUMAN_VERIFIED:
        proof = _completed_human_action_proof(marker, intervention_type)
        evidence = VerificationEvidence.from_authorized_human(
            evidence_id=EvidenceId(evidence_id),
            intervention_id=intervention_id,
            opportunity_id=proof.completed_context.opportunity_id,
            intervention_type=intervention_type,
            completed_action_proof=proof,
            source=proof.authority.source,
            occurred_at=occurred_at,
        )
    else:
        raise ValueError("test helper accepts verified actions only")
    return ActionVerificationEvent(
        event_id=EvidenceId(event_id),
        intervention_id=intervention_id,
        opportunity_id=evidence.material.opportunity_id,
        intervention_type=intervention_type,
        key=LogicalEvidenceKey(
            key_id=EvidenceId(key_id),
            owner_id=intervention_id,
            occurrence_id=evidence.evidence_id,
            kind=EvidenceKeyKind.ACTION,
        ),
        evidence=evidence,
    )


def _completed_context_for(
    intervention: DOIIntervention,
    marker: str = "action",
) -> DOIActionContext:
    proof = (
        _completed_human_action_proof(marker, intervention.intervention_type)
        if intervention.action_verification is ActionVerificationState.HUMAN_VERIFIED
        else _completed_system_action_proof(marker, intervention.intervention_type)
    )
    expected = intervention.action_events[0].evidence.material.action_context_binding
    if proof.completed_context.hash_binding() != expected:
        raise AssertionError("test intervention/action-context binding mismatch")
    return proof.completed_context


def _accepted_human_fact_proof(
    intervention: DOIIntervention,
    suffix: str,
) -> AcceptedHumanFactProof:
    context, _ = _owner_context(intervention.intervention_type)
    if context.opportunity_id != intervention.opportunity_id:
        raise AssertionError("test human fact/opportunity mismatch")
    source = _interaction_source(f"HUMAN-FACT-{suffix}")
    authority = verify_synthetic_human_authority(
        grant_id=EvidenceId(f"SYN-EVIDENCE-HUMAN-FACT-AUTH-{suffix}"),
        actor=RepId("SYN-REP-AUTHORIZED-001"),
        action_context=context,
        granted_at=NOW,
        authority_source=source,
    )
    fact = StructuredHumanFact.create(
        fact_id=EvidenceId(f"SYN-EVIDENCE-HUMAN-FACT-{suffix}"),
        action_context=context,
        evaluation_id=context.evaluation_id,
        usage_kind=HumanFactUsageKind.CUSTOMER_APPROVAL,
        result_code=HumanFactResultCode.APPROVED,
        authority_grant=authority,
        occurred_at=NOW,
        source=source,
    )
    stream_id = EvidenceId(f"SYN-EVIDENCE-HUMAN-FACT-STREAM-{suffix}")
    event_id = EvidenceId(f"SYN-EVIDENCE-HUMAN-FACT-EVENT-{suffix}")
    event = DOIHumanFactEvent(
        event_id=event_id,
        stream_id=stream_id,
        event_type=HumanFactEventType.RECORDED,
        fact=fact,
        corrects_event_id=None,
        recorded_at=NOW,
        sequence=1,
        predecessor_binding=None,
        guard=DOIOccurrenceGuard(
            guard_id=event_id,
            owner_id=stream_id,
            occurrence_id=source.object_id,
            source=source,
        ),
    )
    history = reduce_human_fact(DOIHumanFactHistory(stream_id=stream_id), event).history
    return AcceptedHumanFactProof.from_history(history)


def _value_event(
    *,
    intervention: DOIIntervention,
    event_id: str,
    event_type: ValueEventType,
    cents: int,
    predecessor: ValueEvent | None,
    verification: ValueVerificationState = ValueVerificationState.SYSTEM_VERIFIED,
    correction_kind: ValueCorrectionKind | None = None,
    currency: str = "USD",
    marker: str = "action",
) -> ValueEvent:
    record_id = EvidenceId(
        f"SYN-EVIDENCE-OCC-{event_id.removeprefix('SYN-EVIDENCE-')}"
    )
    key_id = (
        predecessor.key.key_id
        if predecessor is not None
        and correction_kind
        in {
            ValueCorrectionKind.REVERSAL_CORRECTED,
            ValueCorrectionKind.REVERSAL_VOIDED,
        }
        else EvidenceId(
            f"SYN-EVIDENCE-KEY-{event_id.removeprefix('SYN-EVIDENCE-')}"
        )
    )
    if verification is ValueVerificationState.SYSTEM_VERIFIED:
        context = _completed_context_for(intervention, marker=marker)
        record = SystemExactValueRecord.from_order_observation(
            record_id=record_id,
            intervention=intervention,
            completed_action_context=context,
            event_type=event_type,
            amount=_money(cents, currency),
            predecessor_event=predecessor,
            correction_kind=correction_kind,
            observed_at=NOW,
            source=_order_source(
                context.order_id,
                f"VALUE-{event_id[-12:].replace('-', '')}",
            ),
        )
        return ValueEvent.from_system_record(
            event_id=EvidenceId(event_id),
            key_id=key_id,
            record=record,
        )
    if verification is not ValueVerificationState.HUMAN_VERIFIED:
        raise ValueError("test helper accepts verified value records only")
    record = AuthorizedHumanExactValueRecord.from_reduced_human_fact(
        record_id=record_id,
        intervention=intervention,
        human_fact_proof=_accepted_human_fact_proof(
            intervention,
            event_id[-12:].replace("-", ""),
        ),
        event_type=event_type,
        amount=_money(cents, currency),
        predecessor_event=predecessor,
        correction_kind=correction_kind,
    )
    return ValueEvent.from_authorized_human_record(
        event_id=EvidenceId(event_id),
        key_id=key_id,
        record=record,
    )


def _mapping(
    *,
    intervention: DOIIntervention,
    link_id: EvidenceId = LINK_ID,
    child: DoiOrderId = CHILD,
    quantity: int = 1,
    rep_verified: bool = True,
    marker: str = "action",
) -> tuple[MovedLineMappingComponent, ...]:
    context = _completed_context_for(intervention, marker=marker)
    mappings: list[MovedLineMappingComponent] = []
    for index, parent_line in enumerate(context.line_scope, start=1):
        child_line = LineSnapshotId(
            EvidenceId(f"SYN-EVIDENCE-CHILD-LINE-{index:04d}")
        )
        proof = None
        if (
            rep_verified
            and intervention.intervention_type
            is InterventionType.PRODUCT_SUBSTITUTION
        ):
            observation = TargetRepObservation.from_order_observation(
                observation_id=EvidenceId(
                    f"SYN-EVIDENCE-LINE-REP-OBSERVATION-{index:04d}"
                ),
                link_id=link_id,
                intervention=intervention,
                scope=TargetRepProofScope.REPLACEMENT_LINE,
                subject_order_id=child,
                subject_line_id=child_line,
                observed_rep_id=TARGET_REP_ID,
                observed_relation=RepRelation.TARGET_REP_OWNED,
                observed_at=NOW,
                source=_order_source(child, f"LINE-REP-{index:04d}"),
            )
            proof = TargetRepVerificationProof.from_observation(
                proof_id=EvidenceId(
                    f"SYN-EVIDENCE-LINE-REP-PROOF-{index:04d}"
                ),
                intervention=intervention,
                observation=observation,
            )
        mappings.append(
            MovedLineMappingComponent(
                parent_line_id=parent_line,
                child_line_id=child_line,
                quantity=PositiveQuantity(quantity),
                replacement_line_target_rep_proof=proof,
            )
        )
    return tuple(mappings)


def _revision(
    *,
    revision_id: str,
    mappings: tuple[MovedLineMappingComponent, ...],
    predecessor: ResultingOrderLinkRevision | None,
    intervention: DOIIntervention,
    link_id: EvidenceId = LINK_ID,
    child: DoiOrderId = CHILD,
    rep_verified: bool = True,
    human: bool = False,
    resolves_conflict: ResultingOrderLinkRevision | None = None,
    marker: str = "action",
) -> SystemResultingLinkEvidence | AuthorizedHumanResultingLinkEvidence:
    order_proof = None
    if (
        rep_verified
        and intervention.intervention_type is InterventionType.FULFILLMENT_SPLIT
    ):
        suffix = revision_id[-3:]
        observation = TargetRepObservation.from_order_observation(
            observation_id=EvidenceId(
                f"SYN-EVIDENCE-ORDER-REP-OBSERVATION-{suffix}"
            ),
            link_id=link_id,
            intervention=intervention,
            scope=TargetRepProofScope.RESULTING_ORDER,
            subject_order_id=child,
            subject_line_id=None,
            observed_rep_id=TARGET_REP_ID,
            observed_relation=RepRelation.TARGET_REP_OWNED,
            observed_at=NOW,
            source=_order_source(child, f"ORDER-REP-{suffix}"),
        )
        order_proof = TargetRepVerificationProof.from_observation(
            proof_id=EvidenceId(f"SYN-EVIDENCE-ORDER-REP-PROOF-{suffix}"),
            intervention=intervention,
            observation=observation,
        )
    evidence_id = EvidenceId(
        f"SYN-EVIDENCE-LINK-RECORD-{revision_id[-3:]}"
    )
    if human:
        return AuthorizedHumanResultingLinkEvidence.from_reduced_human_fact(
            evidence_id=evidence_id,
            link_id=link_id,
            parent_order_id=PARENT,
            child_order_id=child,
            intervention=intervention,
            human_fact_proof=_accepted_human_fact_proof(
                intervention,
                f"LINK{revision_id[-3:]}",
            ),
            mappings=mappings,
            resulting_order_target_rep_proof=order_proof,
            predecessor_revision=predecessor,
            resolves_conflict_revision=resolves_conflict,
        )
    return SystemResultingLinkEvidence.from_order_observation(
        evidence_id=evidence_id,
        link_id=link_id,
        parent_order_id=PARENT,
        child_order_id=child,
        intervention=intervention,
        completed_action_context=_completed_context_for(intervention, marker=marker),
        mappings=mappings,
        resulting_order_target_rep_proof=order_proof,
        predecessor_revision=predecessor,
        resolves_conflict_revision=resolves_conflict,
        observed_at=NOW,
        source=_order_source(child, f"LINK-RECORD-{revision_id[-3:]}"),
    )


class TestDoiInterventions(unittest.TestCase):
    def test_only_verified_action_creates_intervention(self) -> None:
        result = record_verified_intervention(None, _action())
        self.assertEqual(result.intervention.status, InterventionStatus.VERIFIED_ACTIVE)
        self.assertEqual(
            result.intervention.action_verification,
            ActionVerificationState.SYSTEM_VERIFIED,
        )
        self.assertEqual(tuple(reason.code for reason in result.reasons.reasons), ("RC-061",))
        self.assertFalse(hasattr(VerificationEvidence, "create"))
        with self.assertRaisesRegex(InterventionError, "FACTORY_REQUIRED"):
            VerificationEvidence()

    def test_system_action_requires_reducer_valid_completed_history(self) -> None:
        source = _order_source(PARENT, "SYSTEM-COMPLETION-PROOF")
        with self.assertRaisesRegex(
            InterventionError,
            "SYSTEM_ACTION_COMPLETION_PROOF_INVALID",
        ) as projection_only:
            VerificationEvidence.from_system_observation(
                evidence_id=EvidenceId("SYN-EVIDENCE-SYSTEM-OPEN-PROJECTION"),
                intervention_id=INTERVENTION_ID,
                opportunity_id=OPPORTUNITY_ID,
                intervention_type=InterventionType.PRODUCT_SUBSTITUTION,
                completed_action_proof=_action_context(),  # type: ignore[arg-type]
                source=source,
                occurred_at=NOW,
            )
        self.assertEqual(
            tuple(reason.code for reason in projection_only.exception.reasons.reasons),
            ("RC-060",),
        )

        history = _system_action_history("system-completion-proof")
        opening, completion = history.events
        with self.assertRaisesRegex(
            InterventionError,
            "SYSTEM_ACTION_COMPLETION_PROOF_INVALID",
        ) as absent:
            CompletedSystemActionProof.from_history(
                history=DOIActionContextHistory(
                    action_context_id=history.action_context_id,
                )
            )
        self.assertEqual(
            tuple(reason.code for reason in absent.exception.reasons.reasons),
            ("RC-060",),
        )

        forged_completion = _tampered_action_event(
            completion,
            predecessor_binding=_content(
                "doi-action-context-event/v1",
                "system-wrong-predecessor",
            ),
        )
        forged_history = _tampered_action_history(
            history,
            (opening, forged_completion),
        )
        with self.assertRaisesRegex(
            InterventionError,
            "SYSTEM_ACTION_COMPLETION_PROOF_INVALID",
        ) as forged:
            CompletedSystemActionProof.from_history(history=forged_history)
        self.assertEqual(
            tuple(reason.code for reason in forged.exception.reasons.reasons),
            ("RC-060",),
        )

        real_proof = CompletedSystemActionProof.from_history(history=history)
        evidence = VerificationEvidence.from_system_observation(
            evidence_id=EvidenceId("SYN-EVIDENCE-SYSTEM-REAL-HISTORY"),
            intervention_id=INTERVENTION_ID,
            opportunity_id=real_proof.completed_context.opportunity_id,
            intervention_type=InterventionType.PRODUCT_SUBSTITUTION,
            completed_action_proof=real_proof,
            source=_order_source(
                real_proof.completed_context.order_id,
                "SYSTEM-REAL-HISTORY",
            ),
            occurred_at=NOW,
        )
        self.assertEqual(
            evidence.material.action_context_binding,
            history.projection.hash_binding(),
        )

    def test_verified_completion_proof_keeps_business_action_time_nullable(self) -> None:
        for verification in (
            ActionVerificationState.SYSTEM_VERIFIED,
            ActionVerificationState.HUMAN_VERIFIED,
        ):
            with self.subTest(verification=verification.value):
                result = record_verified_intervention(
                    None,
                    _action(
                        verification=verification,
                        marker=(
                            "sys-null"
                            if verification is ActionVerificationState.SYSTEM_VERIFIED
                            else "human-null"
                        ),
                        occurred_at=None,
                    ),
                )
                self.assertIsNone(result.intervention.action_occurred_at)
                self.assertEqual(
                    result.intervention.action_verification,
                    verification,
                )

    def test_human_action_requires_authority_and_emits_exact_reason(self) -> None:
        event = _action(verification=ActionVerificationState.HUMAN_VERIFIED)
        result = record_verified_intervention(None, event)
        self.assertEqual(tuple(reason.code for reason in result.reasons.reasons), ("RC-062",))
        human_source = _interaction_source("UNAUTHORIZED-HUMAN")
        context = _action_context()
        authority = verify_synthetic_human_authority(
            grant_id=EvidenceId("SYN-EVIDENCE-HUMAN-AUTHORITY-WRONG-CONTEXT"),
            actor=RepId("SYN-REP-AUTHORIZED-002"),
            action_context=context,
            granted_at=NOW,
            authority_source=human_source,
        )
        with self.assertRaisesRegex(
            InterventionError,
            "HUMAN_VERIFICATION_UNAUTHORIZED",
        ) as raised:
            CompletedHumanActionProof.from_history(
                history=_human_action_history("different-context"),
                authority=authority,
            )
        self.assertEqual(
            tuple(reason.code for reason in raised.exception.reasons.reasons),
            ("RC-112",),
        )

        forged_projection = _action_context("forged-projection")
        with self.assertRaisesRegex(
            InterventionError,
            "HUMAN_ACTION_COMPLETION_PROOF_INVALID",
        ) as forged_raised:
            VerificationEvidence.from_authorized_human(
                evidence_id=EvidenceId("SYN-EVIDENCE-HUMAN-FORGED-PROJECTION"),
                intervention_id=INTERVENTION_ID,
                opportunity_id=OPPORTUNITY_ID,
                intervention_type=InterventionType.PRODUCT_SUBSTITUTION,
                completed_action_proof=forged_projection,  # type: ignore[arg-type]
                source=human_source,
                occurred_at=NOW,
            )
        self.assertEqual(
            tuple(reason.code for reason in forged_raised.exception.reasons.reasons),
            ("RC-060",),
        )

    def test_human_action_completion_proof_rejects_absent_or_forged_history(self) -> None:
        valid_history = _human_action_history("history-proof")
        opening_context = DOIActionContext.from_event(valid_history.events[0])
        authority = verify_synthetic_human_authority(
            grant_id=EvidenceId(
                "SYN-EVIDENCE-ACTION-CONTEXT-AUTHORITY-HISTORY-PROOF"
            ),
            actor=RepId("SYN-REP-AUTHORIZED-001"),
            action_context=opening_context,
            granted_at=NOW,
            authority_source=valid_history.events[-1].guard.source,
        )
        with self.assertRaisesRegex(
            InterventionError,
            "HUMAN_ACTION_COMPLETION_PROOF_INVALID",
        ) as absent:
            CompletedHumanActionProof.from_history(
                history=DOIActionContextHistory(
                    action_context_id=opening_context.action_context_id,
                ),
                authority=authority,
            )
        self.assertEqual(
            tuple(reason.code for reason in absent.exception.reasons.reasons),
            ("RC-060",),
        )

        opening, completion = valid_history.events
        malformed_events = (
            _tampered_action_event(
                completion,
                predecessor_binding=_content(
                    "doi-action-context-event/v1",
                    "wrong-predecessor",
                ),
            ),
        )
        for malformed in malformed_events:
            with self.subTest(malformed=malformed.event_id.value):
                forged_history = _tampered_action_history(
                    valid_history,
                    (opening, malformed),
                )
                with self.assertRaisesRegex(
                    InterventionError,
                    "HUMAN_ACTION_COMPLETION_PROOF_INVALID",
                ) as malformed_raised:
                    CompletedHumanActionProof.from_history(
                        history=forged_history,
                        authority=authority,
                    )
                self.assertEqual(
                    tuple(
                        reason.code
                        for reason in malformed_raised.exception.reasons.reasons
                    ),
                    ("RC-060",),
                )

        proof = CompletedHumanActionProof.from_history(
            history=valid_history,
            authority=authority,
        )
        evidence = VerificationEvidence.from_authorized_human(
            evidence_id=EvidenceId("SYN-EVIDENCE-HUMAN-REAL-HISTORY"),
            intervention_id=INTERVENTION_ID,
            opportunity_id=proof.completed_context.opportunity_id,
            intervention_type=InterventionType.PRODUCT_SUBSTITUTION,
            completed_action_proof=proof,
            source=authority.source,
            occurred_at=proof.completion_event.occurred_at,
        )
        self.assertEqual(
            evidence.material.action_context_binding,
            valid_history.projection.hash_binding(),
        )
        self.assertEqual(
            evidence.material.authority_binding,
            authority.hash_binding(),
        )

    def test_unverified_action_and_reversal_emit_verification_requirements(self) -> None:
        with self.assertRaisesRegex(
            InterventionError,
            "ACTION_EVIDENCE_VERIFICATION_INVALID",
        ) as action_error:
            require_verified_action(ActionVerificationState.UNVERIFIED)
        self.assertEqual(
            tuple(reason.code for reason in action_error.exception.reasons.reasons),
            ("RC-060",),
        )
        intervention = record_verified_intervention(None, _action()).intervention
        with self.assertRaisesRegex(
            InterventionError,
            "REVERSAL_VERIFICATION_REQUIRED",
        ) as reversal_error:
            require_verified_reversal_record(intervention, None)
        self.assertEqual(
            tuple(reason.code for reason in reversal_error.exception.reasons.reasons),
            ("RC-077",),
        )

    def test_action_evidence_privacy_scan_runs_before_hash_retention(self) -> None:
        finding = ProhibitedFinding(category="email", path="$[entry:0]")
        proof = _completed_system_action_proof("privacy")
        with patch(
            "synthetic_sales_assist.doi.interventions.assert_payload_safe",
            side_effect=ProhibitedInputError((finding,)),
        ), self.assertRaisesRegex(InterventionError, "ACTION_EVIDENCE_PRIVACY_REJECTED"):
            VerificationEvidence.from_system_observation(
                evidence_id=EvidenceId("SYN-EVIDENCE-PRIVACY-ACTION"),
                intervention_id=INTERVENTION_ID,
                opportunity_id=proof.completed_context.opportunity_id,
                intervention_type=InterventionType.PRODUCT_SUBSTITUTION,
                completed_action_proof=proof,
                source=_order_source(PARENT, "PRIVACY-ACTION"),
                occurred_at=NOW,
            )

    def test_action_exact_replay_and_changed_occurrence_conflict(self) -> None:
        event = _action()
        first = record_verified_intervention(None, event)
        replay = record_verified_intervention(first.intervention, event)
        self.assertTrue(replay.replayed)
        duplicate = record_verified_intervention(
            first.intervention,
            _action(event_id="SYN-EVIDENCE-ACTION-EVENT-DUPLICATE"),
        )
        self.assertTrue(duplicate.replayed)
        self.assertEqual(
            tuple(reason.code for reason in duplicate.reasons.reasons),
            ("RC-076",),
        )
        changed = _action(marker="changed")
        with self.assertRaisesRegex(
            InterventionError,
            "ACTION_OCCURRENCE_CONFLICT",
        ) as raised:
            record_verified_intervention(first.intervention, changed)
        self.assertEqual(
            tuple(reason.code for reason in raised.exception.reasons.reasons),
            ("RC-102",),
        )
        unretained_original = _value_event(
            intervention=first.intervention,
            event_id="SYN-EVIDENCE-VALUE-NOT-RETAINED",
            event_type=ValueEventType.INITIAL_VERIFIED_VALUE,
            cents=1_000,
            predecessor=None,
        )
        bad_predecessor = _value_event(
            intervention=first.intervention,
            event_id="SYN-EVIDENCE-VALUE-BAD-PREDECESSOR",
            event_type=ValueEventType.PARTIAL_REVERSAL,
            cents=100,
            predecessor=unretained_original,
        )
        with self.assertRaisesRegex(
            InterventionError,
            "VALUE_PREDECESSOR_CONFLICT",
        ) as predecessor_raised:
            append_value_event(first.intervention, bad_predecessor)
        self.assertEqual(
            tuple(reason.code for reason in predecessor_raised.exception.reasons.reasons),
            ("RC-111",),
        )

    def test_ds_separation_has_no_value_or_kpi_money(self) -> None:
        result = record_verified_intervention(
            None,
            _action(intervention_type=InterventionType.DS_SEPARATION),
        )
        self.assertEqual(
            result.intervention.value.verification,
            ValueVerificationState.NOT_APPLICABLE,
        )
        self.assertIsNone(result.intervention.value.net_value)

    def test_system_value_and_append_only_partial_full_reversal(self) -> None:
        intervention = record_verified_intervention(None, _action()).intervention
        initial = _value_event(
            intervention=intervention,
            event_id="SYN-EVIDENCE-VALUE-INITIAL",
            event_type=ValueEventType.INITIAL_VERIFIED_VALUE,
            cents=10_000,
            predecessor=None,
        )
        verified = append_value_event(intervention, initial)
        self.assertEqual(verified.intervention.value.net_value, _money(10_000))
        partial = _value_event(
            intervention=verified.intervention,
            event_id="SYN-EVIDENCE-VALUE-REVERSAL-001",
            event_type=ValueEventType.PARTIAL_REVERSAL,
            cents=3_000,
            predecessor=initial,
        )
        partial_result = append_value_event(verified.intervention, partial)
        self.assertEqual(partial_result.intervention.status, InterventionStatus.PARTIALLY_REVERSED)
        self.assertEqual(partial_result.intervention.value.net_value, _money(7_000))
        self.assertEqual(
            tuple(reason.code for reason in partial_result.reasons.reasons),
            ("RC-064", "RC-068"),
        )
        full = _value_event(
            intervention=partial_result.intervention,
            event_id="SYN-EVIDENCE-VALUE-REVERSAL-002",
            event_type=ValueEventType.FULL_REVERSAL,
            cents=7_000,
            predecessor=initial,
        )
        full_result = append_value_event(partial_result.intervention, full)
        self.assertEqual(full_result.intervention.status, InterventionStatus.REVERSED)
        self.assertEqual(full_result.intervention.value.net_value, _money(0))
        self.assertEqual(len(full_result.intervention.value_events), 3)
        self.assertEqual(
            tuple(reason.code for reason in full_result.reasons.reasons),
            ("RC-064", "RC-069"),
        )

    def test_human_estimate_is_rejected_and_history_unchanged(self) -> None:
        intervention = record_verified_intervention(None, _action()).intervention
        with self.assertRaisesRegex(
            InterventionError,
            "SYSTEM_VALUE_RECORD_FACTORY_REQUIRED",
        ):
            SystemExactValueRecord()
        with self.assertRaisesRegex(
            InterventionError,
            "HUMAN_VALUE_RECORD_FACTORY_REQUIRED",
        ):
            AuthorizedHumanExactValueRecord()
        with self.assertRaisesRegex(
            InterventionError,
            "VALUE_EVENT_FACTORY_REQUIRED",
        ):
            ValueEvent()
        with self.assertRaisesRegex(InterventionError, "HUMAN_VALUE_NOT_EXACT") as raised:
            reject_inexact_human_value(HumanValueInexactKind.ESTIMATED)
        self.assertEqual(
            tuple(reason.code for reason in raised.exception.reasons.reasons),
            ("RC-067",),
        )
        self.assertEqual(intervention.value_events, ())

    def test_system_value_controls_conflicting_human_history(self) -> None:
        intervention = record_verified_intervention(None, _action()).intervention
        human = _value_event(
            intervention=intervention,
            event_id="SYN-EVIDENCE-HUMAN-VALUE",
            event_type=ValueEventType.INITIAL_VERIFIED_VALUE,
            cents=10_000,
            predecessor=None,
            verification=ValueVerificationState.HUMAN_VERIFIED,
        )
        human_result = append_value_event(intervention, human)
        self.assertEqual(
            tuple(reason.code for reason in human_result.reasons.reasons),
            ("RC-065",),
        )
        system = _value_event(
            intervention=human_result.intervention,
            event_id="SYN-EVIDENCE-SYSTEM-CORRECTION",
            event_type=ValueEventType.CORRECTION,
            cents=9_000,
            predecessor=human,
            correction_kind=ValueCorrectionKind.ORIGINAL_VALUE_CORRECTED,
        )
        result = append_value_event(human_result.intervention, system)
        self.assertEqual(
            result.intervention.value.verification,
            ValueVerificationState.SYSTEM_AUTHORITATIVE_CONFLICT,
        )
        self.assertEqual(result.intervention.value.net_value, _money(9_000))
        self.assertEqual(len(result.intervention.value_events), 2)
        self.assertEqual(tuple(reason.code for reason in result.reasons.reasons), ("RC-066",))

    def test_reversal_void_recomputes_without_rewriting_history(self) -> None:
        intervention = record_verified_intervention(None, _action()).intervention
        initial = _value_event(
            intervention=intervention,
            event_id="SYN-EVIDENCE-VOID-INITIAL",
            event_type=ValueEventType.INITIAL_VERIFIED_VALUE,
            cents=5_000,
            predecessor=None,
        )
        first = append_value_event(intervention, initial)
        reversal = _value_event(
            intervention=first.intervention,
            event_id="SYN-EVIDENCE-VOID-REVERSAL",
            event_type=ValueEventType.PARTIAL_REVERSAL,
            cents=2_000,
            predecessor=initial,
        )
        second = append_value_event(first.intervention, reversal)
        void = _value_event(
            intervention=second.intervention,
            event_id="SYN-EVIDENCE-VOID-CORRECTION",
            event_type=ValueEventType.CORRECTION,
            cents=0,
            predecessor=reversal,
            correction_kind=ValueCorrectionKind.REVERSAL_VOIDED,
        )
        result = append_value_event(second.intervention, void)
        self.assertEqual(result.intervention.value.net_value, _money(5_000))
        self.assertEqual(result.intervention.status, InterventionStatus.VERIFIED_ACTIVE)
        self.assertEqual(len(result.intervention.value_events), 3)

    def test_value_exact_replay_and_occurrence_conflict(self) -> None:
        intervention = record_verified_intervention(None, _action()).intervention
        event = _value_event(
            intervention=intervention,
            event_id="SYN-EVIDENCE-REPLAY-VALUE",
            event_type=ValueEventType.INITIAL_VERIFIED_VALUE,
            cents=1_000,
            predecessor=None,
        )
        first = append_value_event(intervention, event)
        replay = append_value_event(first.intervention, event)
        self.assertTrue(replay.replayed)
        self.assertEqual(
            tuple(reason.code for reason in replay.reasons.reasons),
            ("RC-076",),
        )
        changed = _value_event(
            intervention=intervention,
            event_id="SYN-EVIDENCE-REPLAY-VALUE",
            event_type=ValueEventType.INITIAL_VERIFIED_VALUE,
            cents=2_000,
            predecessor=None,
        )
        with self.assertRaisesRegex(
            InterventionError,
            "VALUE_OCCURRENCE_CONFLICT",
        ) as raised:
            append_value_event(first.intervention, changed)
        self.assertEqual(
            tuple(reason.code for reason in raised.exception.reasons.reasons),
            ("RC-102",),
        )

    def test_resulting_link_conflict_and_resolution_preserve_revisions(self) -> None:
        intervention = record_verified_intervention(
            None,
            _action(intervention_type=InterventionType.FULFILLMENT_SPLIT),
        ).intervention
        evidence1 = _revision(
            revision_id="SYN-EVIDENCE-LINK-REVISION-001",
            mappings=_mapping(intervention=intervention, quantity=1),
            predecessor=None,
            intervention=intervention,
        )
        first = append_resulting_link_revision(
            None,
            revision_id=EvidenceId("SYN-EVIDENCE-LINK-REVISION-001"),
            intervention=intervention,
            evidence=evidence1,
        )
        self.assertEqual(
            tuple(reason.code for reason in first.reasons.reasons),
            ("RC-070",),
        )
        revision1 = first.link.revisions[-1]
        evidence2 = _revision(
            revision_id="SYN-EVIDENCE-LINK-REVISION-002",
            mappings=_mapping(intervention=intervention, quantity=2),
            predecessor=revision1,
            intervention=intervention,
            rep_verified=False,
        )
        conflicted = append_resulting_link_revision(
            first.link,
            revision_id=EvidenceId("SYN-EVIDENCE-LINK-REVISION-002"),
            intervention=intervention,
            evidence=evidence2,
        )
        self.assertEqual(conflicted.link.state, ResultingOrderLinkState.AMBIGUOUS)
        self.assertEqual(
            tuple(reason.code for reason in conflicted.reasons.reasons),
            ("RC-072", "RC-104"),
        )
        revision2 = conflicted.link.revisions[-1]
        evidence3 = _revision(
            revision_id="SYN-EVIDENCE-LINK-REVISION-003",
            mappings=_mapping(intervention=intervention, quantity=1),
            predecessor=revision2,
            intervention=intervention,
            human=True,
            resolves_conflict=revision2,
        )
        resolved = append_resulting_link_revision(
            conflicted.link,
            revision_id=EvidenceId("SYN-EVIDENCE-LINK-REVISION-003"),
            intervention=intervention,
            evidence=evidence3,
        )
        self.assertEqual(resolved.link.state, ResultingOrderLinkState.HUMAN_CONFIRMED)
        self.assertEqual(len(resolved.link.revisions), 3)
        self.assertEqual(
            tuple(reason.code for reason in resolved.reasons.reasons),
            ("RC-071",),
        )

    def test_rep_proof_cannot_cross_link_intervention_or_scope(self) -> None:
        substitution = record_verified_intervention(None, _action()).intervention
        child_line = LineSnapshotId(EvidenceId("SYN-EVIDENCE-CHILD-LINE-0001"))
        observation = TargetRepObservation.from_order_observation(
            observation_id=EvidenceId("SYN-EVIDENCE-CROSS-LINK-OBSERVATION"),
            link_id=LINK_ID,
            intervention=substitution,
            scope=TargetRepProofScope.REPLACEMENT_LINE,
            subject_order_id=CHILD,
            subject_line_id=child_line,
            observed_rep_id=TARGET_REP_ID,
            observed_relation=RepRelation.TARGET_REP_OWNED,
            observed_at=NOW,
            source=_order_source(CHILD, "CROSS-LINK"),
        )
        proof = TargetRepVerificationProof.from_observation(
            proof_id=EvidenceId("SYN-EVIDENCE-CROSS-LINK-PROOF"),
            intervention=substitution,
            observation=observation,
        )
        wrong_link_mapping = MovedLineMappingComponent(
            parent_line_id=_completed_context_for(substitution).line_scope[0],
            child_line_id=child_line,
            quantity=PositiveQuantity(1),
            replacement_line_target_rep_proof=proof,
        )
        with self.assertRaisesRegex(InterventionError, "RESULTING_LINK_LINE_REP_PROOF_INVALID"):
            SystemResultingLinkEvidence.from_order_observation(
                evidence_id=EvidenceId("SYN-EVIDENCE-CROSS-LINK-EVIDENCE"),
                link_id=EvidenceId("SYN-EVIDENCE-DIFFERENT-LINK"),
                parent_order_id=PARENT,
                child_order_id=CHILD,
                intervention=substitution,
                completed_action_context=_completed_context_for(substitution),
                mappings=(wrong_link_mapping,),
                resulting_order_target_rep_proof=None,
                predecessor_revision=None,
                resolves_conflict_revision=None,
                observed_at=NOW,
                source=_order_source(CHILD, "CROSS-LINK-EVIDENCE"),
            )

    def test_search_not_found_and_ambiguous_are_not_exact_links(self) -> None:
        parent = DoiOrderId(OrderId("SYN-ORDER-SEARCH-PARENT"))
        search_id = EvidenceId("SYN-EVIDENCE-SEARCH-HISTORY")
        candidates = (
            DoiOrderId(OrderId("SYN-ORDER-SEARCH-CHILD-001")),
            DoiOrderId(OrderId("SYN-ORDER-SEARCH-CHILD-002")),
        )
        history = DOIResultingOrderLinkSearchHistory(
            search_id=search_id,
            parent_order_id=parent,
            intervention_type=InterventionType.FULFILLMENT_SPLIT,
        )
        ambiguous_evidence = ResultingLinkSearchEvidence.from_complete_search(
            evidence_id=EvidenceId("SYN-EVIDENCE-SEARCH-AMBIGUOUS-EVIDENCE"),
            search_id=search_id,
            parent_order_id=parent,
            intervention_type=InterventionType.FULFILLMENT_SPLIT,
            candidate_order_ids=candidates,
            disproved_candidate_order_ids=(),
            observed_at=NOW,
            source=_order_source(parent, "SEARCH-AMBIGUOUS"),
        )
        ambiguous_result = append_resulting_link_search(
            history,
            event_id=EvidenceId("SYN-EVIDENCE-SEARCH-AMBIGUOUS-EVENT"),
            evidence=ambiguous_evidence,
        )
        ambiguous = ambiguous_result.history.projection
        self.assertIsNotNone(ambiguous)
        incomplete_disproof = ResultingLinkSearchEvidence.from_complete_search(
            evidence_id=EvidenceId("SYN-EVIDENCE-SEARCH-INCOMPLETE-DISPROOF"),
            search_id=search_id,
            parent_order_id=parent,
            intervention_type=InterventionType.FULFILLMENT_SPLIT,
            candidate_order_ids=(),
            disproved_candidate_order_ids=(candidates[0],),
            observed_at=NOW,
            source=_order_source(parent, "SEARCH-INCOMPLETE-DISPROOF"),
        )
        with self.assertRaisesRegex(
            InterventionError,
            "RESULTING_LINK_SEARCH_DISPROOF_INCOMPLETE",
        ) as incomplete:
            append_resulting_link_search(
                ambiguous_result.history,
                event_id=EvidenceId("SYN-EVIDENCE-SEARCH-INCOMPLETE-EVENT"),
                evidence=incomplete_disproof,
            )
        self.assertEqual(
            tuple(reason.code for reason in incomplete.exception.reasons.reasons),
            ("RC-081",),
        )
        complete_disproof = ResultingLinkSearchEvidence.from_complete_search(
            evidence_id=EvidenceId("SYN-EVIDENCE-SEARCH-COMPLETE-DISPROOF"),
            search_id=search_id,
            parent_order_id=parent,
            intervention_type=InterventionType.FULFILLMENT_SPLIT,
            candidate_order_ids=(),
            disproved_candidate_order_ids=candidates,
            observed_at=NOW,
            source=_order_source(parent, "SEARCH-COMPLETE-DISPROOF"),
        )
        disproved = append_resulting_link_search(
            ambiguous_result.history,
            event_id=EvidenceId("SYN-EVIDENCE-SEARCH-COMPLETE-EVENT"),
            evidence=complete_disproof,
        )
        self.assertEqual(
            disproved.history.projection.state,
            ResultingOrderLinkSearchState.NOT_FOUND,
        )
        self.assertEqual(disproved.history.projection.revision, 2)
        self.assertEqual(
            disproved.event.predecessor_binding,
            ambiguous_result.event.hash_binding(),
        )
        replay = append_resulting_link_search(
            disproved.history,
            event_id=EvidenceId("SYN-EVIDENCE-SEARCH-COMPLETE-EVENT"),
            evidence=complete_disproof,
        )
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.history, disproved.history)
        changed_replay = ResultingLinkSearchEvidence.from_complete_search(
            evidence_id=complete_disproof.evidence_id,
            search_id=search_id,
            parent_order_id=parent,
            intervention_type=InterventionType.FULFILLMENT_SPLIT,
            candidate_order_ids=(
                DoiOrderId(OrderId("SYN-ORDER-SEARCH-CHILD-003")),
                DoiOrderId(OrderId("SYN-ORDER-SEARCH-CHILD-004")),
            ),
            disproved_candidate_order_ids=(),
            observed_at=NOW,
            source=_order_source(parent, "SEARCH-CHANGED-REPLAY"),
        )
        with self.assertRaisesRegex(
            InterventionError,
            "RESULTING_LINK_SEARCH_EVENT_CONFLICT",
        ) as conflict:
            append_resulting_link_search(
                disproved.history,
                event_id=EvidenceId("SYN-EVIDENCE-SEARCH-COMPLETE-EVENT"),
                evidence=changed_replay,
            )
        self.assertEqual(
            tuple(reason.code for reason in conflict.exception.reasons.reasons),
            ("RC-111",),
        )
        with self.assertRaisesRegex(
            InterventionError,
            "RESULTING_LINK_SEARCH_EVIDENCE_FACTORY_REQUIRED",
        ):
            ResultingLinkSearchEvidence()
        with self.assertRaisesRegex(
            InterventionError,
            "RESULTING_LINK_SEARCH_REDUCER_REQUIRED",
        ):
            DOIResultingOrderLinkSearch()
        not_found_evidence = ResultingLinkSearchEvidence.from_complete_search(
            evidence_id=EvidenceId("SYN-EVIDENCE-SEARCH-NOT-FOUND-EVIDENCE"),
            search_id=EvidenceId("SYN-EVIDENCE-SEARCH-NOT-FOUND"),
            parent_order_id=parent,
            intervention_type=InterventionType.FULFILLMENT_SPLIT,
            candidate_order_ids=(),
            disproved_candidate_order_ids=(),
            observed_at=NOW,
            source=_order_source(parent, "SEARCH-NOT-FOUND"),
        )
        not_found_history = DOIResultingOrderLinkSearchHistory(
            search_id=EvidenceId("SYN-EVIDENCE-SEARCH-NOT-FOUND"),
            parent_order_id=parent,
            intervention_type=InterventionType.FULFILLMENT_SPLIT,
        )
        not_found_result = append_resulting_link_search(
            not_found_history,
            event_id=EvidenceId("SYN-EVIDENCE-SEARCH-NOT-FOUND-EVENT"),
            evidence=not_found_evidence,
        )
        not_found = not_found_result.history.projection
        self.assertIsNotNone(not_found)
        self.assertEqual(not_found.candidate_order_ids, ())
        self.assertEqual(
            tuple(reason.code for reason in not_found.reasons.reasons),
            ("RC-073",),
        )
        self.assertEqual(len(ambiguous.candidate_order_ids), 2)

    def test_hash_domain_inventory_and_local_enums_are_immutable(self) -> None:
        self.assertEqual(len(intervention_hash_contracts()), 17)
        with self.assertRaises(AttributeError):
            EvidenceKeyKind.ACTION._value_ = "CHANGED"  # type: ignore[misc]
        with self.assertRaises(AttributeError):
            ValueCorrectionKind.REVERSAL_VOIDED._value_ = "CHANGED"  # type: ignore[misc]
        with self.assertRaises(AttributeError):
            TargetRepProofScope.RESULTING_ORDER._value_ = "CHANGED"  # type: ignore[misc]

    def test_hash_fixtures_cover_every_intervention_hash_record(self) -> None:
        fixtures = intervention_hash_fixtures()
        self.assertEqual(
            {name for name, _, _, _ in fixtures},
            set(intervention_hash_contracts()),
        )
        self.assertEqual(len(fixtures), 17)
        self.assertEqual(
            {name: digest for name, _, _, digest in fixtures},
            dict(INTERVENTION_HASH_KNOWN_ANSWERS),
        )
        for _, domain, canonical_bytes, digest in fixtures:
            self.assertEqual(domain_hash(domain, canonical_bytes).sha256, digest)


if __name__ == "__main__":
    unittest.main()
