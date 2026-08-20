"""Pure deterministic Sales Credit evaluation with closed dimensional explanations."""

from __future__ import annotations

import re
from dataclasses import dataclass

from synthetic_sales_assist.domain.canonical import (
    HashBinding,
    canonical_json_bytes,
    domain_hash,
)
from synthetic_sales_assist.domain.identities import EvaluationId, InteractionId, OrderId
from synthetic_sales_assist.domain.numeric import Money
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.sales_credit.discovery import OrderSearchRun
from synthetic_sales_assist.sales_credit.models import (
    AttributionClassification,
    AttributionDecision,
    CustomerContinuityStatus,
    EvidenceClassification,
    EvidenceDirection,
    EvidenceEvent,
    EvidenceIdentifierKind,
    EvidenceSourceType,
    EvidenceTimingRelation,
    InteractionRecord,
    MaterialChangeKind,
    NotesScanStatus,
    OrderLifecycleStatus,
    OrderSnapshot,
    OrderValueStatus,
    ProductContinuityStatus,
    ReplacementCandidateInput,
    ReplacementCandidateResult,
    ReplacementDecision,
    ReplacementFacts,
    ReplacementStatus,
    SALES_CREDIT_RULE_PACK_VERSION,
    SalesCreditEffect,
    SalesCreditEvaluation,
    SalesCreditFact,
    SalesCreditReason,
    SalesCreditRule,
    SalesCreditValidation,
    SearchTriggerType,
    SnapshotStatus,
    TimestampPrecision,
    ValueDecision,
    WorkflowState,
    sorted_reasons,
)
from synthetic_sales_assist.sales_credit.windows import (
    EvidenceTiming,
    OrderTiming,
    WindowPosition,
    business_local_date,
    cancellation_replacement_window,
    classify_evidence_timing,
    classify_order_timing,
    window_position,
)


_RAW_REP = re.compile(r"\A[a-z][a-z0-9_]{0,63}\Z", re.ASCII)
_RESERVED_REP_TAGS = frozenset({"target_rep", "target_rep_web", "unassigned_web"})
KNOWN_OTHER_REP_CATALOG = frozenset({"synthetic_other_rep"})

RULE_SNAPSHOT_VALIDATION = SalesCreditRule.SNAPSHOT_VALIDATION
RULE_CANCELLATION_REPLACEMENT = SalesCreditRule.CANCELLATION
RULE_REPLACEMENT = SalesCreditRule.REPLACEMENT
RULE_ORDER_VALUE = SalesCreditRule.PLACED_VALUE
RULE_MATERIAL_CHANGE = SalesCreditRule.MATERIAL_CHANGE
RULE_ORDER_REP_ATTRIBUTION = SalesCreditRule.ORDER_REP_ATTRIBUTION
RULE_CONTACT_EVIDENCE = SalesCreditRule.CONTACT_EVIDENCE
RULE_AMBIGUITY_ROUTING = SalesCreditRule.AMBIGUITY_ROUTING


class SalesCreditEvaluationError(ValueError):
    """Reject an evaluator invocation without reflecting supplied material."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Sales Credit evaluation rejected: {code}")


@dataclass(frozen=True, slots=True)
class EvidenceDecision:
    """One derived evidence dimension, separate from a manager outcome."""

    classification: EvidenceClassification | None
    reasons: tuple[SalesCreditReason, ...]
    contradictory: bool


def _instant_key(value: CanonicalTimestamp) -> tuple[int, int]:
    return value.epoch_seconds, value.nanosecond


def _canonical_prior_snapshots(
    *,
    current: OrderSnapshot,
    prior_snapshots: tuple[OrderSnapshot, ...],
) -> tuple[OrderSnapshot, ...]:
    if type(prior_snapshots) is not tuple or any(
        type(item) is not OrderSnapshot for item in prior_snapshots
    ):
        raise SalesCreditEvaluationError("prior_snapshots_shape")
    if current.order_id is None and prior_snapshots:
        raise SalesCreditEvaluationError("prior_snapshot_identity")
    snapshot_ids = tuple(item.snapshot_id for item in prior_snapshots)
    if (
        len(set(snapshot_ids)) != len(snapshot_ids)
        or current.snapshot_id in snapshot_ids
    ):
        raise SalesCreditEvaluationError("prior_snapshots_duplicate")
    current_captured = _instant_key(current.captured_at)
    for item in prior_snapshots:
        if item.order_id != current.order_id:
            raise SalesCreditEvaluationError("prior_snapshot_identity")
        if _instant_key(item.captured_at) > current_captured:
            raise SalesCreditEvaluationError("prior_snapshot_chronology")
    return tuple(
        sorted(
            prior_snapshots,
            key=lambda item: (*_instant_key(item.captured_at), item.snapshot_id.value),
        )
    )


def _require_known_other_reps(value: object) -> frozenset[str]:
    if type(value) is not frozenset:
        raise SalesCreditEvaluationError("known_other_reps_shape")
    accepted = value
    if any(
        type(tag) is not str
        or _RAW_REP.fullmatch(tag) is None
        or not tag.startswith("synthetic_")
        or tag in _RESERVED_REP_TAGS
        for tag in accepted
    ):
        raise SalesCreditEvaluationError("known_other_reps_value")
    if accepted != KNOWN_OTHER_REP_CATALOG:
        raise SalesCreditEvaluationError("known_other_reps_version")
    return accepted


def _candidate_timing(
    *,
    snapshot: OrderSnapshot,
    interactions: tuple[InteractionRecord, ...],
) -> tuple[bool, tuple[SalesCreditReason, ...]]:
    """Require one attached interaction to qualify the candidate order."""

    if snapshot.placed_at is None or snapshot.placed_at_precision is None:
        return False, (SalesCreditReason.MISSING_REQUIRED_FIELD,)
    if not interactions:
        return False, (SalesCreditReason.MISSING_REQUIRED_FIELD,)
    observed = {
        classify_order_timing(
            interaction_at=interaction.effective_at,
            order_at=snapshot.placed_at,
            interaction_precision=interaction.effective_precision,
            order_precision=snapshot.placed_at_precision,
        )
        for interaction in interactions
    }
    if OrderTiming.QUALIFYING_ON_OR_AFTER_INTERACTION in observed:
        return True, ()
    reasons: list[SalesCreditReason] = []
    if OrderTiming.SAME_DAY_UNCERTAIN in observed:
        reasons.append(SalesCreditReason.ORDER_TIMING_UNCERTAIN)
    if OrderTiming.BEFORE_INTERACTION in observed:
        reasons.append(SalesCreditReason.ORDER_BEFORE_INTERACTION)
    if OrderTiming.AFTER_REVIEW_WINDOW in observed:
        reasons.append(SalesCreditReason.ORDER_AFTER_REVIEW_WINDOW)
    if not reasons:
        reasons.append(SalesCreditReason.AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW)
    return False, sorted_reasons(*reasons)


def _zero_like(value: Money | None) -> Money | None:
    if value is None:
        return None
    return Money.from_minor_units(
        0,
        currency_code=value.currency_code,
        registry_version=value.registry_version,
        scale=value.scale,
    )


def evidence_identifier_binding(
    *,
    interaction_id: InteractionId,
    identifier_kind: EvidenceIdentifierKind,
) -> HashBinding:
    """Bind evidence to an interaction and identifier kind without contact material."""

    if type(interaction_id) is not InteractionId:
        raise SalesCreditEvaluationError("evidence_interaction_id_type")
    if type(identifier_kind) is not EvidenceIdentifierKind:
        raise SalesCreditEvaluationError("evidence_identifier_kind_type")
    document = {
        "identifier_kind": identifier_kind.value,
        "interaction_id": interaction_id.value,
    }
    return domain_hash(
        EvidenceEvent.IDENTIFIER_REF_DOMAIN,
        canonical_json_bytes(document, expected_members=set(document)),
    )


def _interaction_map(
    interactions: tuple[InteractionRecord, ...],
) -> dict[InteractionId, InteractionRecord]:
    if type(interactions) is not tuple or any(
        type(interaction) is not InteractionRecord for interaction in interactions
    ):
        raise SalesCreditEvaluationError("interactions_shape")
    identities = tuple(interaction.interaction_id.value for interaction in interactions)
    if identities != tuple(sorted(identities)) or len(identities) != len(set(identities)):
        raise SalesCreditEvaluationError("interactions_order_or_duplicate")
    return {interaction.interaction_id: interaction for interaction in interactions}


def _evidence_bindings_resolve(
    events: tuple[EvidenceEvent, ...],
    interactions: dict[InteractionId, InteractionRecord],
) -> bool:
    for event in events:
        interaction = interactions.get(event.interaction_id)
        if interaction is None:
            return False
        if event.identifier_kind is EvidenceIdentifierKind.EMAIL:
            usable = interaction.email is not None
        else:
            usable = interaction.phone is not None
        if not usable:
            return False
        expected = evidence_identifier_binding(
            interaction_id=event.interaction_id,
            identifier_kind=event.identifier_kind,
        )
        if event.matched_identifier_ref != expected:
            return False
    return True


def classify_order_rep(
    raw_order_rep: str | None,
    *,
    known_other_reps: frozenset[str],
) -> tuple[AttributionDecision, tuple[SalesCreditReason, ...], WorkflowState]:
    """Apply only the exact order-level rep branches; line rep is never consulted."""

    known = _require_known_other_reps(known_other_reps)
    if raw_order_rep == "target_rep":
        return (
            AttributionDecision(AttributionClassification.TARGET_REP, True),
            (SalesCreditReason.TARGET_REP,),
            WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
        )
    if raw_order_rep == "target_rep_web":
        return (
            AttributionDecision(AttributionClassification.TARGET_REP, True),
            (SalesCreditReason.TARGET_REP_WEB,),
            WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
        )
    if raw_order_rep == "unassigned_web":
        return (
            AttributionDecision(AttributionClassification.UNASSIGNED_WEB, True),
            (SalesCreditReason.UNASSIGNED_WEB,),
            WorkflowState.EVIDENCE_NEEDED,
        )
    if raw_order_rep is None or raw_order_rep == "":
        return (
            AttributionDecision(AttributionClassification.UNKNOWN, False),
            (SalesCreditReason.REP_MISSING,),
            WorkflowState.MANUAL_REVIEW_REQUIRED,
        )
    if type(raw_order_rep) is not str or _RAW_REP.fullmatch(raw_order_rep) is None:
        raise SalesCreditEvaluationError("raw_order_rep_shape")
    if raw_order_rep in known:
        return (
            AttributionDecision(AttributionClassification.OTHER_REP, True),
            (SalesCreditReason.OTHER_KNOWN_REP,),
            WorkflowState.OTHER_REP_HUMAN_REVIEW,
        )
    return (
        AttributionDecision(AttributionClassification.UNKNOWN, True),
        (SalesCreditReason.REP_UNRECOGNIZED,),
        WorkflowState.MANUAL_REVIEW_REQUIRED,
    )


def _timing_is_coherent(
    event: EvidenceEvent,
    order_at: CanonicalTimestamp,
    order_precision: TimestampPrecision,
) -> bool:
    derived = classify_evidence_timing(
        evidence_at=event.occurred_at,
        order_at=order_at,
        evidence_precision=event.timestamp_precision,
        order_precision=order_precision,
    )
    expected = {
        EvidenceTiming.PRE_ORDER: EvidenceTimingRelation.PRE_ORDER,
        EvidenceTiming.POST_ORDER: EvidenceTimingRelation.POST_ORDER,
        EvidenceTiming.TIMING_UNCERTAIN: EvidenceTimingRelation.SAME_DAY_UNCERTAIN,
    }[derived]
    return event.timing is expected


def classify_evidence_event(
    event: EvidenceEvent,
    *,
    order_at: CanonicalTimestamp,
    order_precision: TimestampPrecision,
) -> EvidenceDecision:
    """Derive one evidence class and reject declared/observed contradictions safely."""

    if type(event) is not EvidenceEvent:
        raise SalesCreditEvaluationError("evidence_event_type")
    if type(order_at) is not CanonicalTimestamp:
        raise SalesCreditEvaluationError("evidence_order_time_type")
    if type(order_precision) is not TimestampPrecision:
        raise SalesCreditEvaluationError("evidence_order_precision_type")

    classification: EvidenceClassification
    reasons: tuple[SalesCreditReason, ...]
    contradictory = False

    if not _timing_is_coherent(event, order_at, order_precision):
        classification = EvidenceClassification.UNKNOWN_OR_CONTRADICTORY
        reasons = (SalesCreditReason.CONTRADICTORY_FACTS,)
        contradictory = True
    elif event.timing is EvidenceTimingRelation.SAME_DAY_UNCERTAIN:
        classification = EvidenceClassification.TIMING_UNCERTAIN_HUMAN_REVIEW
        reasons = (SalesCreditReason.EVIDENCE_TIMING_UNCERTAIN,)
    elif event.timing is EvidenceTimingRelation.POST_ORDER:
        classification = EvidenceClassification.POST_ORDER_CONTACT_ONLY
        reasons = (SalesCreditReason.POST_ORDER_CONTACT_ONLY,)
    elif event.timing is EvidenceTimingRelation.UNKNOWN:
        classification = EvidenceClassification.UNKNOWN_OR_CONTRADICTORY
        reasons = (SalesCreditReason.NO_QUALIFYING_PREORDER_EVIDENCE,)
    elif (
        event.direction is EvidenceDirection.UNKNOWN
        or event.target_rep_participated is None
        or event.connected is None
        or event.two_way is None
    ):
        classification = EvidenceClassification.UNKNOWN_OR_CONTRADICTORY
        reasons = (SalesCreditReason.EVIDENCE_IDENTITY_UNPROVED,)
    elif event.direction is EvidenceDirection.TWO_WAY:
        if event.two_way is True and event.target_rep_participated is True:
            classification = EvidenceClassification.VERIFIED_PREORDER_EVIDENCE
            reasons = (SalesCreditReason.TWO_WAY_PREORDER_INTERACTION,)
        else:
            classification = EvidenceClassification.UNKNOWN_OR_CONTRADICTORY
            reasons = (SalesCreditReason.CONTRADICTORY_FACTS,)
            contradictory = True
    elif event.two_way is True:
        classification = EvidenceClassification.UNKNOWN_OR_CONTRADICTORY
        reasons = (SalesCreditReason.CONTRADICTORY_FACTS,)
        contradictory = True
    elif (
        event.source_type is EvidenceSourceType.SYNTHETIC_PHONE_CALL
        and event.connected is True
    ):
        if event.target_rep_participated is True:
            classification = EvidenceClassification.VERIFIED_PREORDER_EVIDENCE
            reasons = (SalesCreditReason.CONNECTED_PREORDER_CALL,)
        else:
            classification = EvidenceClassification.UNKNOWN_OR_CONTRADICTORY
            reasons = (SalesCreditReason.EVIDENCE_IDENTITY_UNPROVED,)
    elif event.connected is True:
        classification = EvidenceClassification.UNKNOWN_OR_CONTRADICTORY
        reasons = (SalesCreditReason.CONTRADICTORY_FACTS,)
        contradictory = True
    elif event.direction is EvidenceDirection.INBOUND:
        if event.target_rep_participated is False:
            classification = EvidenceClassification.INBOUND_EVIDENCE_HUMAN_REVIEW
            reason = (
                SalesCreditReason.MISSED_OR_UNANSWERED_INBOUND_CALL
                if event.source_type is EvidenceSourceType.SYNTHETIC_PHONE_CALL
                else SalesCreditReason.INBOUND_ONLY_PREORDER_CONTACT
            )
            reasons = (reason,)
        else:
            classification = EvidenceClassification.UNKNOWN_OR_CONTRADICTORY
            reasons = (SalesCreditReason.CONTRADICTORY_FACTS,)
            contradictory = True
    elif event.direction is EvidenceDirection.OUTBOUND:
        if event.target_rep_participated is True:
            classification = EvidenceClassification.OUTBOUND_EVIDENCE_HUMAN_REVIEW
            reasons = (SalesCreditReason.OUTBOUND_ONLY_PREORDER_CONTACT,)
        else:
            classification = EvidenceClassification.UNKNOWN_OR_CONTRADICTORY
            reasons = (SalesCreditReason.EVIDENCE_IDENTITY_UNPROVED,)
    else:
        classification = EvidenceClassification.UNKNOWN_OR_CONTRADICTORY
        reasons = (SalesCreditReason.NO_QUALIFYING_PREORDER_EVIDENCE,)

    if event.classification is not classification:
        classification = EvidenceClassification.UNKNOWN_OR_CONTRADICTORY
        reasons = sorted_reasons(*reasons, SalesCreditReason.CONTRADICTORY_FACTS)
        contradictory = True
    return EvidenceDecision(classification, sorted_reasons(*reasons), contradictory)


def classify_evidence(
    events: tuple[EvidenceEvent, ...],
    *,
    order_at: CanonicalTimestamp,
    order_precision: TimestampPrecision,
) -> EvidenceDecision:
    """Aggregate evidence without inferring two-way contact across distinct events."""

    if type(events) is not tuple or any(type(event) is not EvidenceEvent for event in events):
        raise SalesCreditEvaluationError("evidence_events_shape")
    identities = tuple(event.evidence_id.value for event in events)
    if identities != tuple(sorted(identities)) or len(identities) != len(set(identities)):
        raise SalesCreditEvaluationError("evidence_events_order_or_duplicate")
    if not events:
        return EvidenceDecision(
            None,
            (SalesCreditReason.NO_QUALIFYING_PREORDER_EVIDENCE,),
            False,
        )

    assessments = tuple(
        classify_evidence_event(
            event,
            order_at=order_at,
            order_precision=order_precision,
        )
        for event in events
    )
    reasons = sorted_reasons(
        *(reason for assessment in assessments for reason in assessment.reasons)
    )
    classifications = {assessment.classification for assessment in assessments}
    if any(assessment.contradictory for assessment in assessments):
        return EvidenceDecision(
            EvidenceClassification.UNKNOWN_OR_CONTRADICTORY,
            sorted_reasons(*reasons, SalesCreditReason.CONTRADICTORY_FACTS),
            True,
        )
    if EvidenceClassification.VERIFIED_PREORDER_EVIDENCE in classifications:
        return EvidenceDecision(
            EvidenceClassification.VERIFIED_PREORDER_EVIDENCE,
            reasons,
            False,
        )
    if EvidenceClassification.TIMING_UNCERTAIN_HUMAN_REVIEW in classifications:
        return EvidenceDecision(
            EvidenceClassification.TIMING_UNCERTAIN_HUMAN_REVIEW,
            reasons,
            False,
        )
    directional = classifications & {
        EvidenceClassification.INBOUND_EVIDENCE_HUMAN_REVIEW,
        EvidenceClassification.OUTBOUND_EVIDENCE_HUMAN_REVIEW,
    }
    if len(directional) == 1 and classifications == directional:
        return EvidenceDecision(next(iter(directional)), reasons, False)
    return EvidenceDecision(
        EvidenceClassification.UNKNOWN_OR_CONTRADICTORY,
        sorted_reasons(
            *reasons,
            SalesCreditReason.AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW,
        ),
        False,
    )


def _evidence_workflow(decision: EvidenceDecision) -> WorkflowState:
    if decision.classification is None:
        return WorkflowState.EVIDENCE_NEEDED
    mapping = {
        EvidenceClassification.VERIFIED_PREORDER_EVIDENCE: (
            WorkflowState.VERIFIED_PREORDER_EVIDENCE
        ),
        EvidenceClassification.INBOUND_EVIDENCE_HUMAN_REVIEW: (
            WorkflowState.INBOUND_EVIDENCE_HUMAN_REVIEW
        ),
        EvidenceClassification.OUTBOUND_EVIDENCE_HUMAN_REVIEW: (
            WorkflowState.OUTBOUND_EVIDENCE_HUMAN_REVIEW
        ),
        EvidenceClassification.TIMING_UNCERTAIN_HUMAN_REVIEW: (
            WorkflowState.TIMING_UNCERTAIN_HUMAN_REVIEW
        ),
        EvidenceClassification.POST_ORDER_CONTACT_ONLY: (
            WorkflowState.MANUAL_REVIEW_REQUIRED
        ),
        EvidenceClassification.UNKNOWN_OR_CONTRADICTORY: (
            WorkflowState.MANUAL_REVIEW_REQUIRED
        ),
    }
    return mapping[decision.classification]


def derive_replacement_facts(
    *,
    parent: OrderSnapshot,
    candidate: OrderSnapshot,
    line_universe_complete: bool,
    possible_nonexact_continuity: bool = False,
) -> ReplacementFacts:
    """Derive customer and exact ES/MFG continuity from two factual snapshots."""

    if type(parent) is not OrderSnapshot or type(candidate) is not OrderSnapshot:
        raise SalesCreditEvaluationError("replacement_snapshot_type")
    if type(line_universe_complete) is not bool:
        raise SalesCreditEvaluationError("replacement_line_completeness_type")
    if type(possible_nonexact_continuity) is not bool:
        raise SalesCreditEvaluationError("replacement_nonexact_type")
    if parent.order_id is None or candidate.order_id is None:
        raise SalesCreditEvaluationError("replacement_order_identity")
    if parent.order_id == candidate.order_id:
        raise SalesCreditEvaluationError("replacement_same_order")

    parent_customers = set(parent.customer_ids)
    candidate_customers = set(candidate.customer_ids)
    if not parent_customers or not candidate_customers:
        customer = CustomerContinuityStatus.UNKNOWN
    elif parent_customers & candidate_customers:
        customer = CustomerContinuityStatus.PROVED
    else:
        customer = CustomerContinuityStatus.ABSENT

    if not line_universe_complete:
        product = ProductContinuityStatus.UNKNOWN
    else:
        parent_es = {
            line.canonical_es_number
            for line in parent.lines
            if line.canonical_es_number is not None
        }
        candidate_es = {
            line.canonical_es_number
            for line in candidate.lines
            if line.canonical_es_number is not None
        }
        parent_mfg = {
            line.canonical_mfg_oe_number
            for line in parent.lines
            if line.canonical_mfg_oe_number is not None
        }
        candidate_mfg = {
            line.canonical_mfg_oe_number
            for line in candidate.lines
            if line.canonical_mfg_oe_number is not None
        }
        if parent_es & candidate_es:
            product = ProductContinuityStatus.EXACT_ES
        elif parent_mfg & candidate_mfg:
            product = ProductContinuityStatus.EXACT_MFG_OE
        elif possible_nonexact_continuity:
            product = ProductContinuityStatus.NONEXACT
        else:
            product = ProductContinuityStatus.ABSENT
    return ReplacementFacts(
        customer_continuity=customer,
        product_continuity=product,
        parent_order_id=parent.order_id,
        replacement_order_id=candidate.order_id,
        line_universe_complete=line_universe_complete,
    )


def _history_immutable_conflict(
    snapshot: OrderSnapshot,
    *,
    prior_snapshots: tuple[OrderSnapshot, ...],
) -> bool:
    snapshots = (*prior_snapshots, snapshot)
    placed_facts = {
        (_instant_key(item.placed_at), item.placed_at_precision)
        for item in snapshots
        if item.placed_at is not None and item.placed_at_precision is not None
    }
    canceled_facts = {
        _instant_key(item.canceled_at)
        for item in snapshots
        if item.canceled_at is not None
    }
    return len(placed_facts) > 1 or len(canceled_facts) > 1


def _derive_line_material_changes(
    snapshots: tuple[OrderSnapshot, ...],
) -> frozenset[MaterialChangeKind]:
    complete = tuple(
        item
        for item in snapshots
        if item.extraction_status is not SnapshotStatus.INVALID
        and "LINES_INCOMPLETE" not in item.warnings
    )
    changes: set[MaterialChangeKind] = set()
    for previous, current in zip(complete, complete[1:], strict=False):
        previous_lines = {line.line_id: line for line in previous.lines}
        current_lines = {line.line_id: line for line in current.lines}
        previous_ids = set(previous_lines)
        current_ids = set(current_lines)
        if current_ids - previous_ids:
            changes.add(MaterialChangeKind.PRODUCT_ADDITION)
        if previous_ids - current_ids:
            changes.add(MaterialChangeKind.PRODUCT_REMOVAL)
        for line_id in previous_ids & current_ids:
            old = previous_lines[line_id]
            new = current_lines[line_id]
            if (
                old.sku_id,
                old.canonical_es_number,
                old.canonical_mfg_oe_number,
            ) != (
                new.sku_id,
                new.canonical_es_number,
                new.canonical_mfg_oe_number,
            ):
                changes.add(MaterialChangeKind.SUBSTITUTION)
            if old.quantity != new.quantity:
                changes.add(MaterialChangeKind.QUANTITY_CHANGE)
            if old.line_value != new.line_value:
                changes.add(MaterialChangeKind.PRICE_ADJUSTMENT)
    return frozenset(changes)


def _evaluate_value(
    snapshot: OrderSnapshot,
    *,
    prior_snapshots: tuple[OrderSnapshot, ...],
) -> tuple[ValueDecision, tuple[SalesCreditReason, ...], bool]:
    derived_line_changes = _derive_line_material_changes(
        (*prior_snapshots, snapshot)
    )
    material_kinds = tuple(
        sorted(
            derived_line_changes
            | {
                change.kind
                for item in (*prior_snapshots, snapshot)
                for change in item.material_changes
                if change.kind.is_material
            },
            key=lambda item: item.value,
        )
    )
    routine_present = any(
        not change.kind.is_material
        for item in (*prior_snapshots, snapshot)
        for change in item.material_changes
    )
    placed_values = tuple(
        item.placed_value
        for item in (*prior_snapshots, snapshot)
        if item.extraction_status is not SnapshotStatus.INVALID
        and item.placed_value is not None
    )
    placed_value_conflict = bool(placed_values) and any(
        value != placed_values[0] for value in placed_values[1:]
    )
    stable_placed_value = (
        None if placed_value_conflict or not placed_values else placed_values[0]
    )
    reasons: list[SalesCreditReason] = []

    if material_kinds:
        status = OrderValueStatus.CHANGED_REVIEW
        reasons.append(SalesCreditReason.MATERIAL_CHANGE_DETECTED)
    elif placed_value_conflict:
        status = OrderValueStatus.UNKNOWN
        reasons.extend(
            (
                SalesCreditReason.CONTRADICTORY_FACTS,
                SalesCreditReason.PLACED_VALUE_UNAVAILABLE,
            )
        )
    elif stable_placed_value is not None:
        status = OrderValueStatus.PLACED_VALUE_VERIFIED
        reasons.append(SalesCreditReason.PLACED_VALUE_PROVED)
    elif snapshot.current_value is not None:
        status = OrderValueStatus.CURRENT_ONLY
        reasons.append(SalesCreditReason.PLACED_VALUE_UNAVAILABLE)
    else:
        status = OrderValueStatus.UNKNOWN
        reasons.append(SalesCreditReason.PLACED_VALUE_UNAVAILABLE)
    if (
        placed_value_conflict
        and SalesCreditReason.CONTRADICTORY_FACTS not in reasons
    ):
        reasons.extend(
            (
                SalesCreditReason.CONTRADICTORY_FACTS,
                SalesCreditReason.PLACED_VALUE_UNAVAILABLE,
            )
        )
    if routine_present:
        reasons.append(SalesCreditReason.ROUTINE_LIFECYCLE_CHANGE_NONMATERIAL)

    dependency_blocked = snapshot.notes_scan_status is not NotesScanStatus.COMPLETE
    if dependency_blocked:
        reasons.extend(
            (
                SalesCreditReason.SNAPSHOT_PARTIAL_DEPENDENCY_BLOCKED,
                SalesCreditReason.AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW,
            )
        )
    value_requires_review = (
        bool(material_kinds)
        or stable_placed_value is None
        or placed_value_conflict
        or dependency_blocked
    )
    active_value = (
        stable_placed_value
        if status is OrderValueStatus.PLACED_VALUE_VERIFIED
        else None
    )
    return (
        ValueDecision(
            status=status,
            placed_value=stable_placed_value,
            active_value=active_value,
            material_changes=material_kinds,
        ),
        sorted_reasons(*reasons),
        value_requires_review,
    )


_REPLACEMENT_RESULT_PRIORITY = {
    ReplacementStatus.NOT_CONTINUATION: 0,
    ReplacementStatus.BLOCKED: 1,
    ReplacementStatus.POSSIBLE_REVIEW: 2,
    ReplacementStatus.EXACT_RELEVANT: 3,
}


def _blocked_replacement_authority(
    *,
    run: OrderSearchRun | None,
    candidate_results: tuple[ReplacementCandidateResult, ...] = (),
    reasons: tuple[SalesCreditReason, ...],
) -> tuple[ReplacementDecision, tuple[SalesCreditReason, ...], WorkflowState]:
    return (
        ReplacementDecision(
            status=ReplacementStatus.BLOCKED,
            customer_continuity=CustomerContinuityStatus.UNKNOWN,
            product_continuity=ProductContinuityStatus.UNKNOWN,
            search_run_id=None if run is None else run.run_id,
            enumeration_complete=False,
            candidate_results=candidate_results,
        ),
        sorted_reasons(
            *reasons,
            SalesCreditReason.AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW,
        ),
        WorkflowState.MANUAL_REVIEW_REQUIRED,
    )


def _blocked_candidate_result(
    *,
    candidate: OrderSnapshot,
    customer: CustomerContinuityStatus = CustomerContinuityStatus.UNKNOWN,
    product: ProductContinuityStatus = ProductContinuityStatus.UNKNOWN,
    reasons: tuple[SalesCreditReason, ...],
) -> ReplacementCandidateResult:
    if candidate.order_id is None:
        raise SalesCreditEvaluationError("replacement_candidate_identity")
    return ReplacementCandidateResult(
        order_id=candidate.order_id,
        snapshot_id=candidate.snapshot_id,
        status=ReplacementStatus.BLOCKED,
        customer_continuity=customer,
        product_continuity=product,
        reasons=sorted_reasons(*reasons),
    )


def _evaluate_replacement_candidate(
    *,
    parent: OrderSnapshot,
    candidate_input: ReplacementCandidateInput,
    search_completed_at: CanonicalTimestamp,
    evaluated_at: CanonicalTimestamp,
) -> ReplacementCandidateResult:
    candidate = candidate_input.snapshot
    if parent.canceled_at is None or candidate.order_id is None:
        return _blocked_candidate_result(
            candidate=candidate,
            reasons=(SalesCreditReason.MISSING_REQUIRED_FIELD,),
        )
    if (
        candidate.placed_at is not None
        and _instant_key(candidate.placed_at) > _instant_key(search_completed_at)
    ):
        return _blocked_candidate_result(
            candidate=candidate,
            reasons=(SalesCreditReason.CONTRADICTORY_FACTS,),
        )
    if candidate.extraction_status is SnapshotStatus.INVALID:
        return _blocked_candidate_result(
            candidate=candidate,
            reasons=(SalesCreditReason.SNAPSHOT_INVALID,),
        )
    missing, contradictory = _core_snapshot_failures(
        candidate,
        expected_order_id=candidate.order_id,
        evaluated_at=evaluated_at,
    )
    if missing or contradictory:
        reasons: list[SalesCreditReason] = []
        if missing:
            reasons.append(SalesCreditReason.MISSING_REQUIRED_FIELD)
        if contradictory:
            reasons.append(SalesCreditReason.CONTRADICTORY_FACTS)
        return _blocked_candidate_result(candidate=candidate, reasons=tuple(reasons))
    if candidate.placed_at is None:
        return _blocked_candidate_result(
            candidate=candidate,
            reasons=(SalesCreditReason.MISSING_REQUIRED_FIELD,),
        )
    if (
        business_local_date(candidate.placed_at)
        == business_local_date(parent.canceled_at)
        and candidate.placed_at_precision is not None
        and not candidate.placed_at_precision.proves_same_day_ordering
    ):
        return _blocked_candidate_result(
            candidate=candidate,
            reasons=(
                SalesCreditReason.AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW,
                SalesCreditReason.ORDER_TIMING_UNCERTAIN,
            ),
        )
    candidate_position = window_position(
        cancellation_replacement_window(parent.canceled_at),
        candidate.placed_at,
    )
    if (
        candidate_position is WindowPosition.BEFORE
        or _instant_key(candidate.placed_at) < _instant_key(parent.canceled_at)
    ):
        return ReplacementCandidateResult(
            order_id=candidate.order_id,
            snapshot_id=candidate.snapshot_id,
            status=ReplacementStatus.NOT_CONTINUATION,
            customer_continuity=CustomerContinuityStatus.UNKNOWN,
            product_continuity=ProductContinuityStatus.UNKNOWN,
            reasons=(SalesCreditReason.ORDER_BEFORE_CANCELLATION,),
        )
    if candidate_position is WindowPosition.AFTER:
        return ReplacementCandidateResult(
            order_id=candidate.order_id,
            snapshot_id=candidate.snapshot_id,
            status=ReplacementStatus.NOT_CONTINUATION,
            customer_continuity=CustomerContinuityStatus.UNKNOWN,
            product_continuity=ProductContinuityStatus.UNKNOWN,
            reasons=(SalesCreditReason.ORDER_AFTER_REPLACEMENT_WINDOW,),
        )
    facts = derive_replacement_facts(
        parent=parent,
        candidate=candidate,
        line_universe_complete=candidate_input.line_universe_complete,
        possible_nonexact_continuity=(
            candidate_input.possible_nonexact_continuity
        ),
    )
    line_dependency_incomplete = (
        not candidate_input.line_universe_complete
        or "LINES_INCOMPLETE" in parent.warnings
        or "LINES_INCOMPLETE" in candidate.warnings
    )
    customer_dependency_incomplete = (
        "CUSTOMERS_INCOMPLETE" in parent.warnings
        or "CUSTOMERS_INCOMPLETE" in candidate.warnings
    )
    customer_unknown = (
        facts.customer_continuity is CustomerContinuityStatus.UNKNOWN
    )
    product_unknown = facts.product_continuity is ProductContinuityStatus.UNKNOWN
    if (
        line_dependency_incomplete
        or customer_dependency_incomplete
        or customer_unknown
        or product_unknown
    ):
        reasons = [SalesCreditReason.SNAPSHOT_PARTIAL_DEPENDENCY_BLOCKED]
        if customer_dependency_incomplete or customer_unknown:
            reasons.append(SalesCreditReason.CUSTOMER_CONTINUITY_UNPROVED)
        if line_dependency_incomplete or product_unknown:
            reasons.append(SalesCreditReason.NO_PRODUCT_CONTINUITY)
        return _blocked_candidate_result(
            candidate=candidate,
            customer=facts.customer_continuity,
            product=facts.product_continuity,
            reasons=tuple(reasons),
        )
    if facts.customer_continuity is CustomerContinuityStatus.ABSENT:
        reasons = [SalesCreditReason.CUSTOMER_CONTINUITY_MISMATCH]
        if facts.product_continuity is ProductContinuityStatus.ABSENT:
            reasons.append(SalesCreditReason.NO_PRODUCT_CONTINUITY)
        return ReplacementCandidateResult(
            order_id=candidate.order_id,
            snapshot_id=candidate.snapshot_id,
            status=ReplacementStatus.NOT_CONTINUATION,
            customer_continuity=facts.customer_continuity,
            product_continuity=facts.product_continuity,
            reasons=sorted_reasons(*reasons),
        )
    if facts.product_continuity is ProductContinuityStatus.ABSENT:
        reasons = [SalesCreditReason.NO_PRODUCT_CONTINUITY]
        return ReplacementCandidateResult(
            order_id=candidate.order_id,
            snapshot_id=candidate.snapshot_id,
            status=ReplacementStatus.NOT_CONTINUATION,
            customer_continuity=facts.customer_continuity,
            product_continuity=facts.product_continuity,
            reasons=sorted_reasons(*reasons),
        )
    if facts.product_continuity is ProductContinuityStatus.NONEXACT:
        return ReplacementCandidateResult(
            order_id=candidate.order_id,
            snapshot_id=candidate.snapshot_id,
            status=ReplacementStatus.POSSIBLE_REVIEW,
            customer_continuity=facts.customer_continuity,
            product_continuity=facts.product_continuity,
            reasons=(
                SalesCreditReason.NONEXACT_PRODUCT_CONTINUITY_REQUIRES_REVIEW,
            ),
        )
    exact_reason = (
        SalesCreditReason.EXACT_ES_PRODUCT_CONTINUITY
        if facts.product_continuity is ProductContinuityStatus.EXACT_ES
        else SalesCreditReason.EXACT_MFG_OE_PRODUCT_CONTINUITY
    )
    return ReplacementCandidateResult(
        order_id=candidate.order_id,
        snapshot_id=candidate.snapshot_id,
        status=ReplacementStatus.EXACT_RELEVANT,
        customer_continuity=facts.customer_continuity,
        product_continuity=facts.product_continuity,
        reasons=(exact_reason,),
    )


def _evaluate_replacement(
    snapshot: OrderSnapshot,
    *,
    run: OrderSearchRun | None,
    candidates: tuple[ReplacementCandidateInput, ...],
    interactions: tuple[InteractionRecord, ...],
    evaluated_at: CanonicalTimestamp,
) -> tuple[
    ReplacementDecision,
    tuple[SalesCreditReason, ...],
    WorkflowState | None,
]:
    supplied = run is not None or bool(candidates)
    if snapshot.lifecycle_status is not OrderLifecycleStatus.CANCELED:
        if supplied:
            return _blocked_replacement_authority(
                run=run,
                reasons=(SalesCreditReason.CONTRADICTORY_FACTS,),
            )
        return (
            ReplacementDecision(
                ReplacementStatus.NOT_APPLICABLE,
                CustomerContinuityStatus.UNKNOWN,
                ProductContinuityStatus.UNKNOWN,
            ),
            (),
            None,
        )
    if snapshot.canceled_at is None:
        return _blocked_replacement_authority(
            run=run,
            reasons=(SalesCreditReason.MISSING_REQUIRED_FIELD,),
        )
    if _instant_key(evaluated_at) < _instant_key(snapshot.canceled_at):
        return _blocked_replacement_authority(
            run=run,
            reasons=(SalesCreditReason.CONTRADICTORY_FACTS,),
        )

    cancellation_window = cancellation_replacement_window(snapshot.canceled_at)
    evaluation_position = window_position(cancellation_window, evaluated_at)
    if run is None:
        if candidates:
            return _blocked_replacement_authority(
                run=None,
                reasons=(SalesCreditReason.CONTRADICTORY_FACTS,),
            )
        if evaluation_position is WindowPosition.ACTIVE:
            return (
                ReplacementDecision(
                    ReplacementStatus.WINDOW_ACTIVE,
                    CustomerContinuityStatus.UNKNOWN,
                    ProductContinuityStatus.UNKNOWN,
                ),
                (SalesCreditReason.REPLACEMENT_WINDOW_ACTIVE,),
                WorkflowState.CANCELED_REPLACEMENT_WINDOW_ACTIVE,
            )
        return _blocked_replacement_authority(
            run=None,
            reasons=(SalesCreditReason.IDENTIFIER_SEARCH_INCOMPLETE,),
        )

    run_time_valid = (
        _instant_key(snapshot.canceled_at) <= _instant_key(run.started_at)
        and _instant_key(run.started_at) <= _instant_key(run.completed_at)
        and _instant_key(run.completed_at) <= _instant_key(evaluated_at)
    )
    if (
        run.trigger is not SearchTriggerType.REPLACEMENT_CHECK
        or run.interactions != interactions
        or not run_time_valid
    ):
        return _blocked_replacement_authority(
            run=run,
            reasons=(SalesCreditReason.CONTRADICTORY_FACTS,),
        )

    expected_order_ids = tuple(
        order_id
        for order_id in run.result.order_ids
        if order_id != snapshot.order_id
    )
    candidate_order_ids = tuple(item.snapshot.order_id for item in candidates)
    if candidate_order_ids != expected_order_ids:
        return _blocked_replacement_authority(
            run=run,
            reasons=(SalesCreditReason.CONTRADICTORY_FACTS,),
        )

    candidate_results = tuple(
        sorted(
            (
                _evaluate_replacement_candidate(
                    parent=snapshot,
                    candidate_input=item,
                    search_completed_at=run.completed_at,
                    evaluated_at=evaluated_at,
                )
                for item in candidates
            ),
            key=lambda item: (item.order_id.value, item.snapshot_id.value),
        )
    )
    candidate_reasons = tuple(
        reason for result in candidate_results for reason in result.reasons
    )
    if not run.result.enumeration_complete:
        return _blocked_replacement_authority(
            run=run,
            candidate_results=candidate_results,
            reasons=sorted_reasons(
                *candidate_reasons,
                SalesCreditReason.IDENTIFIER_SEARCH_INCOMPLETE,
            ),
        )

    nonmatches_only = all(
        item.status is ReplacementStatus.NOT_CONTINUATION
        for item in candidate_results
    )
    run_position = window_position(cancellation_window, run.completed_at)
    if nonmatches_only:
        run_start_position = window_position(cancellation_window, run.started_at)
        crossing_expiry = (
            run_position is WindowPosition.AFTER
            and run_start_position is not WindowPosition.AFTER
        )
        if crossing_expiry:
            return _blocked_replacement_authority(
                run=run,
                candidate_results=candidate_results,
                reasons=sorted_reasons(
                    *candidate_reasons,
                    SalesCreditReason.IDENTIFIER_SEARCH_INCOMPLETE,
                ),
            )
        expired = (
            run_start_position is WindowPosition.AFTER
            and run_position is WindowPosition.AFTER
        )
        status = (
            ReplacementStatus.WINDOW_EXPIRED
            if expired
            else ReplacementStatus.WINDOW_ACTIVE
        )
        reason = (
            SalesCreditReason.REPLACEMENT_WINDOW_EXPIRED
            if expired
            else SalesCreditReason.REPLACEMENT_WINDOW_ACTIVE
        )
        workflow = (
            WorkflowState.CANCELED_NO_REPLACEMENT
            if expired
            else WorkflowState.CANCELED_REPLACEMENT_WINDOW_ACTIVE
        )
        return (
            ReplacementDecision(
                status=status,
                customer_continuity=CustomerContinuityStatus.UNKNOWN,
                product_continuity=ProductContinuityStatus.UNKNOWN,
                search_run_id=run.run_id,
                enumeration_complete=True,
                candidate_results=candidate_results,
            ),
            sorted_reasons(*candidate_reasons, reason),
            workflow,
        )

    highest = max(
        _REPLACEMENT_RESULT_PRIORITY[item.status] for item in candidate_results
    )
    winner = next(
        item
        for item in candidate_results
        if _REPLACEMENT_RESULT_PRIORITY[item.status] == highest
    )
    reasons = list(candidate_reasons)
    if winner.status is ReplacementStatus.BLOCKED:
        reasons.append(SalesCreditReason.AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW)
    return (
        ReplacementDecision(
            status=winner.status,
            customer_continuity=winner.customer_continuity,
            product_continuity=winner.product_continuity,
            search_run_id=run.run_id,
            enumeration_complete=True,
            candidate_results=candidate_results,
        ),
        sorted_reasons(*reasons),
        WorkflowState.POSSIBLE_REPLACEMENT_HUMAN_REVIEW,
    )


def _supplied_fact_tokens(
    snapshot: OrderSnapshot,
    *,
    evidence_events: tuple[EvidenceEvent, ...],
    replacement_run: OrderSearchRun | None,
    replacement_candidates: tuple[ReplacementCandidateInput, ...],
    prior_snapshots: tuple[OrderSnapshot, ...],
) -> tuple[SalesCreditFact, ...]:
    facts = {SalesCreditFact.SNAPSHOT, SalesCreditFact.ORDER_LIFECYCLE}
    for present, fact in (
        (snapshot.order_id is not None, SalesCreditFact.ORDER_IDENTITY),
        (snapshot.placed_at is not None, SalesCreditFact.ORDER_TIMING),
        (snapshot.raw_order_rep is not None, SalesCreditFact.ORDER_REP),
        (
            snapshot.current_value is not None or snapshot.placed_value is not None,
            SalesCreditFact.ORDER_VALUE,
        ),
        (
            any(item.material_changes for item in (*prior_snapshots, snapshot)),
            SalesCreditFact.MATERIAL_CHANGES,
        ),
        (bool(evidence_events), SalesCreditFact.CONTACT_EVIDENCE),
        (
            replacement_run is not None or bool(replacement_candidates),
            SalesCreditFact.REPLACEMENT_CONTINUITY,
        ),
    ):
        if present:
            facts.add(fact)
    return tuple(sorted(facts, key=lambda item: item.value))


def _core_snapshot_failures(
    snapshot: OrderSnapshot,
    *,
    expected_order_id: OrderId,
    evaluated_at: CanonicalTimestamp,
) -> tuple[bool, bool]:
    missing = any(
        value is None
        for value in (
            snapshot.order_id,
            snapshot.source_ref,
            snapshot.placed_at,
            snapshot.placed_at_precision,
            snapshot.raw_order_status,
            snapshot.current_value,
            snapshot.provenance,
        )
    )
    contradictory = snapshot.order_id is not None and snapshot.order_id != expected_order_id
    derived_lifecycle = {
        "active": OrderLifecycleStatus.ACTIVE,
        "canceled": OrderLifecycleStatus.CANCELED,
    }.get(snapshot.raw_order_status, OrderLifecycleStatus.UNKNOWN)
    contradictory = contradictory or snapshot.lifecycle_status is not derived_lifecycle
    captured_key = _instant_key(snapshot.captured_at)
    if snapshot.placed_at is not None:
        contradictory = contradictory or _instant_key(snapshot.placed_at) > captured_key
    if snapshot.canceled_at is not None:
        contradictory = contradictory or _instant_key(snapshot.canceled_at) > captured_key
        if snapshot.placed_at is not None:
            contradictory = contradictory or (
                _instant_key(snapshot.canceled_at) < _instant_key(snapshot.placed_at)
            )
    contradictory = contradictory or _instant_key(evaluated_at) < captured_key
    return missing, contradictory


def evaluate_sales_credit(
    *,
    evaluation_id: EvaluationId,
    expected_order_id: OrderId,
    snapshot: OrderSnapshot,
    evaluated_at: CanonicalTimestamp,
    known_other_reps: frozenset[str],
    interactions: tuple[InteractionRecord, ...] = (),
    evidence_events: tuple[EvidenceEvent, ...] = (),
    replacement_run: OrderSearchRun | None = None,
    replacement_candidates: tuple[ReplacementCandidateInput, ...] = (),
    prior_snapshots: tuple[OrderSnapshot, ...] = (),
) -> SalesCreditEvaluation:
    """Evaluate one captured candidate without I/O, clock reads, or state mutation."""

    if type(evaluation_id) is not EvaluationId:
        raise SalesCreditEvaluationError("evaluation_id_type")
    if type(expected_order_id) is not OrderId:
        raise SalesCreditEvaluationError("expected_order_id_type")
    if type(snapshot) is not OrderSnapshot:
        raise SalesCreditEvaluationError("snapshot_type")
    if type(evaluated_at) is not CanonicalTimestamp:
        raise SalesCreditEvaluationError("evaluated_at_type")
    history = _canonical_prior_snapshots(
        current=snapshot,
        prior_snapshots=prior_snapshots,
    )
    known = _require_known_other_reps(known_other_reps)
    interaction_by_id = _interaction_map(interactions)
    if type(evidence_events) is not tuple or any(
        type(event) is not EvidenceEvent for event in evidence_events
    ):
        raise SalesCreditEvaluationError("evidence_events_shape")
    evidence_ids = tuple(event.evidence_id.value for event in evidence_events)
    if evidence_ids != tuple(sorted(evidence_ids)) or len(evidence_ids) != len(
        set(evidence_ids)
    ):
        raise SalesCreditEvaluationError("evidence_events_order_or_duplicate")
    if replacement_run is not None and type(replacement_run) is not OrderSearchRun:
        raise SalesCreditEvaluationError("replacement_run_type")
    if type(replacement_candidates) is not tuple or any(
        type(item) is not ReplacementCandidateInput
        for item in replacement_candidates
    ):
        raise SalesCreditEvaluationError("replacement_candidates_shape")
    candidate_order_ids = tuple(
        item.snapshot.order_id for item in replacement_candidates
    )
    candidate_snapshot_ids = tuple(
        item.snapshot.snapshot_id for item in replacement_candidates
    )
    if (
        len(set(candidate_order_ids)) != len(candidate_order_ids)
        or len(set(candidate_snapshot_ids)) != len(candidate_snapshot_ids)
    ):
        raise SalesCreditEvaluationError("replacement_candidates_duplicate")
    candidates = tuple(
        sorted(
            replacement_candidates,
            key=lambda item: (
                item.snapshot.order_id.value
                if item.snapshot.order_id is not None
                else "",
                item.snapshot.snapshot_id.value,
            ),
        )
    )

    supplied_facts = _supplied_fact_tokens(
        snapshot,
        evidence_events=evidence_events,
        replacement_run=replacement_run,
        replacement_candidates=candidates,
        prior_snapshots=history,
    )
    missing, contradictory = _core_snapshot_failures(
        snapshot,
        expected_order_id=expected_order_id,
        evaluated_at=evaluated_at,
    )
    invalid = (
        snapshot.extraction_status is SnapshotStatus.INVALID
        or missing
        or contradictory
    )
    if invalid:
        reasons = [SalesCreditReason.SNAPSHOT_INVALID]
        validations = [SalesCreditValidation.SNAPSHOT_REJECTED]
        if missing:
            reasons.append(SalesCreditReason.MISSING_REQUIRED_FIELD)
        if contradictory:
            reasons.append(SalesCreditReason.CONTRADICTORY_FACTS)
        return SalesCreditEvaluation(
            evaluation_id=evaluation_id,
            order_id=expected_order_id,
            snapshot_id=snapshot.snapshot_id,
            workflow_state=WorkflowState.MANUAL_REVIEW_REQUIRED,
            attribution=AttributionDecision(AttributionClassification.UNKNOWN, False),
            value=ValueDecision(
                status=OrderValueStatus.UNKNOWN,
                placed_value=None,
                active_value=None,
                material_changes=(),
            ),
            replacement=ReplacementDecision(
                ReplacementStatus.BLOCKED,
                CustomerContinuityStatus.UNKNOWN,
                ProductContinuityStatus.UNKNOWN,
            ),
            reasons=sorted_reasons(*reasons),
            human_review_required=True,
            supplied_facts=supplied_facts,
            validations=tuple(sorted(set(validations), key=lambda item: item.value)),
            rules_evaluated=(RULE_SNAPSHOT_VALIDATION,),
            rules_fired=(RULE_SNAPSHOT_VALIDATION,),
            persistence_effects=(
                SalesCreditEffect.HUMAN_REVIEW_REQUIRED,
                SalesCreditEffect.NO_PERSISTENCE_MILESTONE_2,
            ),
            rule_pack_version=SALES_CREDIT_RULE_PACK_VERSION,
        )

    history_immutable_contradictory = _history_immutable_conflict(
        snapshot,
        prior_snapshots=history,
    )
    history_lifecycle_contradictory = (
        snapshot.lifecycle_status is OrderLifecycleStatus.ACTIVE
        and any(
            item.lifecycle_status is OrderLifecycleStatus.CANCELED
            for item in history
        )
    )
    history_contradictory = (
        history_immutable_contradictory or history_lifecycle_contradictory
    )
    timing_accepted, timing_reasons = _candidate_timing(
        snapshot=snapshot,
        interactions=interactions,
    )
    if not timing_accepted:
        reasons = sorted_reasons(
            *timing_reasons,
            SalesCreditReason.AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW,
            *(
                (SalesCreditReason.CONTRADICTORY_FACTS,)
                if history_contradictory
                else ()
            ),
        )
        workflow_state = (
            WorkflowState.TIMING_UNCERTAIN_HUMAN_REVIEW
            if SalesCreditReason.ORDER_TIMING_UNCERTAIN in timing_reasons
            else WorkflowState.MANUAL_REVIEW_REQUIRED
        )
        validations = [SalesCreditValidation.SNAPSHOT_ACCEPTED]
        if snapshot.extraction_status is SnapshotStatus.PARTIAL:
            validations.append(SalesCreditValidation.SNAPSHOT_PARTIAL)
        return SalesCreditEvaluation(
            evaluation_id=evaluation_id,
            order_id=expected_order_id,
            snapshot_id=snapshot.snapshot_id,
            workflow_state=workflow_state,
            attribution=AttributionDecision(AttributionClassification.UNKNOWN, False),
            value=ValueDecision(
                status=OrderValueStatus.UNKNOWN,
                placed_value=None,
                active_value=None,
                material_changes=(),
            ),
            replacement=ReplacementDecision(
                ReplacementStatus.BLOCKED,
                CustomerContinuityStatus.UNKNOWN,
                ProductContinuityStatus.UNKNOWN,
            ),
            reasons=reasons,
            human_review_required=True,
            supplied_facts=supplied_facts,
            validations=tuple(sorted(validations, key=lambda item: item.value)),
            rules_evaluated=tuple(
                sorted(
                    {
                        RULE_AMBIGUITY_ROUTING,
                        RULE_SNAPSHOT_VALIDATION,
                        SalesCreditRule.ORDER_WINDOW,
                    },
                    key=lambda item: item.value,
                )
            ),
            rules_fired=tuple(
                sorted(
                    {RULE_AMBIGUITY_ROUTING, SalesCreditRule.ORDER_WINDOW},
                    key=lambda item: item.value,
                )
            ),
            persistence_effects=(
                SalesCreditEffect.HUMAN_REVIEW_REQUIRED,
                SalesCreditEffect.NO_PERSISTENCE_MILESTONE_2,
            ),
            rule_pack_version=SALES_CREDIT_RULE_PACK_VERSION,
        )

    validations = [
        SalesCreditValidation.ORDER_ID_MATCHED,
        SalesCreditValidation.ORDER_TIMING_ACCEPTED,
        SalesCreditValidation.SNAPSHOT_ACCEPTED,
    ]
    fired: list[SalesCreditRule] = [RULE_SNAPSHOT_VALIDATION]
    reasons: list[SalesCreditReason] = []
    if snapshot.extraction_status is SnapshotStatus.PARTIAL:
        validations.append(SalesCreditValidation.SNAPSHOT_PARTIAL)

    replacement, replacement_reasons, replacement_workflow = _evaluate_replacement(
        snapshot,
        run=replacement_run,
        candidates=candidates,
        interactions=interactions,
        evaluated_at=evaluated_at,
    )
    reasons.extend(replacement_reasons)
    if replacement_reasons:
        fired.append(RULE_CANCELLATION_REPLACEMENT)
    if replacement_run is not None or candidates:
        fired.append(RULE_REPLACEMENT)

    value, value_reasons, value_requires_review = _evaluate_value(
        snapshot,
        prior_snapshots=history,
    )
    reasons.extend(value_reasons)
    fired.append(RULE_ORDER_VALUE)
    if history_contradictory:
        reasons.extend(
            (
                SalesCreditReason.AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW,
                SalesCreditReason.CONTRADICTORY_FACTS,
            )
        )
    if (
        SalesCreditReason.SNAPSHOT_PARTIAL_DEPENDENCY_BLOCKED
        in replacement_reasons + value_reasons
    ):
        validations.append(SalesCreditValidation.DEPENDENCY_BLOCKED)
    if snapshot.lifecycle_status is OrderLifecycleStatus.CANCELED:
        base = snapshot.placed_value or snapshot.current_value
        canceled_active_value = (
            _zero_like(base)
            if value.status is OrderValueStatus.PLACED_VALUE_VERIFIED
            else None
        )
        value = ValueDecision(
            status=value.status,
            placed_value=value.placed_value,
            active_value=canceled_active_value,
            material_changes=value.material_changes,
        )
        reasons.append(SalesCreditReason.CANCELED_ORDER_ZERO_ACTIVE_VALUE)

    attribution, attribution_reasons, attribution_workflow = classify_order_rep(
        snapshot.raw_order_rep,
        known_other_reps=known,
    )
    reasons.extend(attribution_reasons)
    fired.append(RULE_ORDER_REP_ATTRIBUTION)

    rules_evaluated: list[SalesCreditRule] = [
        RULE_SNAPSHOT_VALIDATION,
        SalesCreditRule.ORDER_WINDOW,
        RULE_CANCELLATION_REPLACEMENT,
        RULE_REPLACEMENT,
        RULE_ORDER_VALUE,
        RULE_MATERIAL_CHANGE,
        RULE_ORDER_REP_ATTRIBUTION,
        RULE_AMBIGUITY_ROUTING,
    ]
    fired.append(SalesCreditRule.ORDER_WINDOW)
    if snapshot.lifecycle_status is OrderLifecycleStatus.CANCELED:
        fired.extend((RULE_CANCELLATION_REPLACEMENT, RULE_REPLACEMENT))
    if (
        value.material_changes
        or snapshot.notes_scan_status is not NotesScanStatus.COMPLETE
    ):
        fired.append(RULE_MATERIAL_CHANGE)
    evidence_workflow = attribution_workflow
    if attribution.classification is AttributionClassification.UNASSIGNED_WEB:
        rules_evaluated.append(RULE_CONTACT_EVIDENCE)
        if any(event.order_id != expected_order_id for event in evidence_events):
            evidence = EvidenceDecision(
                EvidenceClassification.UNKNOWN_OR_CONTRADICTORY,
                (SalesCreditReason.CONTRADICTORY_FACTS,),
                True,
            )
        elif not _evidence_bindings_resolve(evidence_events, interaction_by_id):
            evidence = EvidenceDecision(
                EvidenceClassification.UNKNOWN_OR_CONTRADICTORY,
                (SalesCreditReason.EVIDENCE_IDENTITY_UNPROVED,),
                False,
            )
        else:
            evidence = classify_evidence(
                evidence_events,
                order_at=snapshot.placed_at,
                order_precision=snapshot.placed_at_precision,
            )
        reasons.extend(evidence.reasons)
        evidence_workflow = _evidence_workflow(evidence)
        if evidence.classification is not None:
            fired.append(RULE_CONTACT_EVIDENCE)

    lifecycle_unknown = snapshot.lifecycle_status is OrderLifecycleStatus.UNKNOWN
    if lifecycle_unknown:
        reasons.extend(
            (
                SalesCreditReason.AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW,
                SalesCreditReason.UNSUPPORTED_SCHEMA_OR_SNAPSHOT,
            )
        )
    if value_requires_review:
        workflow = WorkflowState.ORDER_CHANGED_HUMAN_REVIEW
    elif history_contradictory:
        workflow = WorkflowState.MANUAL_REVIEW_REQUIRED
    elif lifecycle_unknown:
        workflow = WorkflowState.MANUAL_REVIEW_REQUIRED
    elif replacement_workflow is not None:
        workflow = replacement_workflow
    else:
        workflow = evidence_workflow

    human_review_states = {
        WorkflowState.INBOUND_EVIDENCE_HUMAN_REVIEW,
        WorkflowState.MANUAL_REVIEW_REQUIRED,
        WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
        WorkflowState.OTHER_REP_HUMAN_REVIEW,
        WorkflowState.OUTBOUND_EVIDENCE_HUMAN_REVIEW,
        WorkflowState.POSSIBLE_REPLACEMENT_HUMAN_REVIEW,
        WorkflowState.TIMING_UNCERTAIN_HUMAN_REVIEW,
    }
    human_review = workflow in human_review_states
    if human_review:
        fired.append(RULE_AMBIGUITY_ROUTING)

    effects = {SalesCreditEffect.NO_PERSISTENCE_MILESTONE_2}
    if human_review:
        effects.add(SalesCreditEffect.HUMAN_REVIEW_REQUIRED)
    else:
        effects.add(SalesCreditEffect.ACTIVE_CASE_CLASSIFICATION)
    if snapshot.lifecycle_status is OrderLifecycleStatus.CANCELED:
        effects.add(SalesCreditEffect.ZERO_ACTIVE_VALUE)

    return SalesCreditEvaluation(
        evaluation_id=evaluation_id,
        order_id=expected_order_id,
        snapshot_id=snapshot.snapshot_id,
        workflow_state=workflow,
        attribution=attribution,
        value=value,
        replacement=replacement,
        reasons=sorted_reasons(*reasons),
        human_review_required=human_review,
        supplied_facts=supplied_facts,
        validations=tuple(sorted(set(validations), key=lambda item: item.value)),
        rules_evaluated=tuple(
            sorted(set(rules_evaluated), key=lambda item: item.value)
        ),
        rules_fired=tuple(sorted(set(fired), key=lambda item: item.value)),
        persistence_effects=tuple(sorted(effects, key=lambda item: item.value)),
        rule_pack_version=SALES_CREDIT_RULE_PACK_VERSION,
    )


__all__ = [
    "EvidenceDecision",
    "KNOWN_OTHER_REP_CATALOG",
    "RULE_AMBIGUITY_ROUTING",
    "RULE_CANCELLATION_REPLACEMENT",
    "RULE_CONTACT_EVIDENCE",
    "RULE_MATERIAL_CHANGE",
    "RULE_ORDER_REP_ATTRIBUTION",
    "RULE_ORDER_VALUE",
    "RULE_REPLACEMENT",
    "RULE_SNAPSHOT_VALIDATION",
    "SalesCreditEvaluationError",
    "classify_evidence",
    "classify_evidence_event",
    "classify_order_rep",
    "derive_replacement_facts",
    "evidence_identifier_binding",
    "evaluate_sales_credit",
]
