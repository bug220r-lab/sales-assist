"""Closed immutable DOI domain values for the Milestone 3 rule pack.

This module deliberately contains no repository, clock, browser, or network behavior.  Source
adapters may construct the observation records below, while :mod:`evaluator` consumes them as
facts.  Every collection is a canonical tuple and every hash uses the shared domain-separated
canonical JSON implementation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import ClassVar, TypeVar, cast

from synthetic_sales_assist.doi.identities import (
    DoiOrderId,
    DoiRunId,
    DoiSnapshotId,
    LineSnapshotId,
)
from synthetic_sales_assist.domain.canonical import (
    HashBinding,
    canonical_json_bytes,
    domain_hash,
)
from synthetic_sales_assist.domain.identities import (
    EvaluationId,
    EvidenceId,
    InteractionId,
    RepId,
    SkuId,
)
from synthetic_sales_assist.domain.numeric import Money, PositiveQuantity, Quantity
from synthetic_sales_assist.domain.observed import (
    OBSERVED_TAGGED_VALUE_VERSION,
    FindingPresenceV2,
    KnownObservedValue,
    NotApplicableObservedValue,
    ObservedTaggedValue,
    UnknownObservedValue,
    parse_observed_tagged_value,
)
from synthetic_sales_assist.domain.records import (
    ReasonSet,
    SourceKind,
    SourceObjectNamespace,
    SourceRef,
    VersionBinding,
    WholeOrderCompletenessProof,
)
from synthetic_sales_assist.domain.registries import ReasonRef, TransitionRef
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.domain.tokens import ImmutableStrEnum


DOI_RULE_PACK_VERSION = "synthetic-doi-rule-pack/v1"
DOI_MODEL_SCHEMA_VERSION = "synthetic-doi-models/v1"
DOI_RULE_PACK_HASH_DOMAIN = "doi-rule-pack-binding/v1"
M3_UNCERTAINTY_CONTAINMENT_POLICY = "PRESERVE_INDEPENDENTLY_PROVEN_OPPORTUNITIES"
M3_OVERLAP_POLICY = (
    "PRESERVE_SEPARATE_OPPORTUNITIES_AND_WITHHOLD_ONLY_AGGREGATE_POTENTIAL"
)
TR_037_MANUAL_REVIEW_POLICY = (
    "USE_ONLY_WHEN_NO_SAFE_OPPORTUNITY_OR_OTHER_HIGHER_PRECEDENCE_RESULT_IS_PROVABLE"
)

_UPPER_TOKEN = re.compile(r"\A[A-Z][A-Z0-9_]{0,95}\Z", re.ASCII)
_ALL_REASON_CODES = frozenset(f"RC-{number:03d}" for number in range(1, 139))
_T = TypeVar("_T")


class DOIModelError(ValueError):
    """Non-reflecting closed-model validation failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True, repr=False)
class HashKnownAnswer:
    record_name: str
    domain: str
    canonical_bytes: bytes = field(repr=False)
    sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.record_name) is not str
            or type(self.domain) is not str
            or type(self.canonical_bytes) is not bytes
            or type(self.sha256) is not str
        ):
            raise DOIModelError("HASH_KNOWN_ANSWER_INVALID")
        binding = domain_hash(self.domain, self.canonical_bytes)
        if binding.sha256 != self.sha256:
            raise DOIModelError("HASH_KNOWN_ANSWER_INVALID")

    @property
    def preimage(self) -> bytes:
        return self.domain.encode("ascii") + b"\n" + self.canonical_bytes

    def __repr__(self) -> str:
        return f"HashKnownAnswer(record_name={self.record_name!r})"


class CaseLifecycleState(ImmutableStrEnum):
    ACTIVE = "ACTIVE"
    CLOSED_HARD = "CLOSED_HARD"
    CLOSED_REVERSIBLE = "CLOSED_REVERSIBLE"


class TerminalClosureReason(ImmutableStrEnum):
    SHIPPED = "SHIPPED"
    CANCELED = "CANCELED"
    REP_TRANSFERRED = "REP_TRANSFERRED"
    DEDUPE_CONFIRMED = "DEDUPE_CONFIRMED"
    HUMAN_OUT_OF_SCOPE = "HUMAN_OUT_OF_SCOPE"


class DOIState(ImmutableStrEnum):
    DOI_MONITOR = "DOI_MONITOR"
    DOI_OPPORTUNITY = "DOI_OPPORTUNITY"
    DOI_MANUAL_REVIEW = "DOI_MANUAL_REVIEW"
    DOI_EXCLUDED = "DOI_EXCLUDED"


class OrderState(ImmutableStrEnum):
    ACTIVE = "ACTIVE"
    SHIPPED = "SHIPPED"
    CANCELED = "CANCELED"
    UNKNOWN = "UNKNOWN"


class RepRelation(ImmutableStrEnum):
    TARGET_REP_OWNED = "TARGET_REP_OWNED"
    OTHER_REP = "OTHER_REP"
    UNKNOWN = "UNKNOWN"


class GeographyClass(ImmutableStrEnum):
    DOMESTIC_STANDARD = "DOMESTIC_STANDARD"
    DOMESTIC_SPECIAL_REVIEW = "DOMESTIC_SPECIAL_REVIEW"
    INTERNATIONAL = "INTERNATIONAL"
    UNKNOWN = "UNKNOWN"


class PaymentCondition(ImmutableStrEnum):
    NONE_OBSERVED = "NONE_OBSERVED"
    PRESENT = "PRESENT"
    UNKNOWN = "UNKNOWN"


class LineActivity(ImmutableStrEnum):
    ACTIVE = "ACTIVE"
    CANCELED = "CANCELED"
    UNKNOWN = "UNKNOWN"


class DropShipState(ImmutableStrEnum):
    DS = "DS"
    NON_DS = "NON_DS"
    UNKNOWN = "UNKNOWN"


class LineAvailability(ImmutableStrEnum):
    IN_STOCK = "IN_STOCK"
    DELAYED = "DELAYED"
    UNKNOWN = "UNKNOWN"


class QuantityAvailability(ImmutableStrEnum):
    FULL = "FULL"
    NONE = "NONE"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class LineContinuityState(ImmutableStrEnum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"


class ContinuityProofType(ImmutableStrEnum):
    STABLE_SOURCE_LINE_ID = "STABLE_SOURCE_LINE_ID"
    CLOSED_COMPOSITE = "CLOSED_COMPOSITE"
    NONE = "NONE"


class SourcePresence(ImmutableStrEnum):
    PRESENT = "PRESENT"
    ABSENT_RECHECK_REQUIRED = "ABSENT_RECHECK_REQUIRED"


class OpportunityType(ImmutableStrEnum):
    FULFILLMENT_SPLIT = "FULFILLMENT_SPLIT"
    DS_SEPARATION = "DS_SEPARATION"
    EXACT_SKU_RECHECK = "EXACT_SKU_RECHECK"
    EXACT_MFG_ALTERNATE = "EXACT_MFG_ALTERNATE"
    MFG_CROSS_REFERENCE = "MFG_CROSS_REFERENCE"
    MFG_SUPERSESSION = "MFG_SUPERSESSION"
    FUNCTIONAL_ALTERNATE = "FUNCTIONAL_ALTERNATE"
    PARTIAL_QUANTITY_REVIEW = "PARTIAL_QUANTITY_REVIEW"


class OpportunityScopeRole(ImmutableStrEnum):
    AVAILABLE = "AVAILABLE"
    DELAYED = "DELAYED"
    DIRECT_SHIP = "DIRECT_SHIP"
    NON_DIRECT_SHIP = "NON_DIRECT_SHIP"
    PARTIAL_AVAILABLE = "PARTIAL_AVAILABLE"
    ORDERED_PRODUCT = "ORDERED_PRODUCT"
    ALTERNATE_PRODUCT = "ALTERNATE_PRODUCT"


class ValueAvailabilityState(ImmutableStrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class ScenarioSelectionState(ImmutableStrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    REQUIRED = "REQUIRED"
    SELECTED = "SELECTED"


class HandlingFlag(ImmutableStrEnum):
    PAYMENT_BEFORE_ACTION = "PAYMENT_BEFORE_ACTION"
    AK_HI_SHIPPING_REVIEW = "AK_HI_SHIPPING_REVIEW"
    INTERNATIONAL_REVIEW = "INTERNATIONAL_REVIEW"
    GEOGRAPHY_ACTION_READINESS_REVIEW_REQUIRED = (
        "GEOGRAPHY_ACTION_READINESS_REVIEW_REQUIRED"
    )
    CUSTOMER_CONTACT_BEFORE_SPLIT = "CUSTOMER_CONTACT_BEFORE_SPLIT"
    CUSTOMER_APPROVAL_REQUIRED = "CUSTOMER_APPROVAL_REQUIRED"
    COMPATIBILITY_REVIEW_REQUIRED = "COMPATIBILITY_REVIEW_REQUIRED"
    HUMAN_SCENARIO_SELECTION_REQUIRED = "HUMAN_SCENARIO_SELECTION_REQUIRED"
    ETA_RANKING_UNAVAILABLE = "ETA_RANKING_UNAVAILABLE"
    OUTREACH_SUPPRESSED = "OUTREACH_SUPPRESSED"
    SOURCE_ABSENCE_RECHECK_REQUIRED = "SOURCE_ABSENCE_RECHECK_REQUIRED"


class HumanReviewKind(ImmutableStrEnum):
    COMMERCIAL_DECISION = "COMMERCIAL_DECISION"
    ORDER_PROGRESS = "ORDER_PROGRESS"
    UNKNOWN_FACT = "UNKNOWN_FACT"
    SHIPPING = "SHIPPING"
    CUSTOMER_CONTACT = "CUSTOMER_CONTACT"
    CUSTOMER_APPROVAL = "CUSTOMER_APPROVAL"
    COMPATIBILITY = "COMPATIBILITY"
    SCENARIO_SELECTION = "SCENARIO_SELECTION"
    COORDINATION = "COORDINATION"
    DEDUPE_DECISION = "DEDUPE_DECISION"


class AlternateResearchState(ImmutableStrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"
    MANUAL_IDENTIFICATION_REQUIRED = "MANUAL_IDENTIFICATION_REQUIRED"


class AlternateRelationshipType(ImmutableStrEnum):
    EXACT_MFG = "EXACT_MFG"
    MFG_CROSS_REFERENCE = "MFG_CROSS_REFERENCE"
    MFG_SUPERSESSION = "MFG_SUPERSESSION"
    FUNCTIONAL = "FUNCTIONAL"


class AlternateRelationshipState(ImmutableStrEnum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    INVALIDATED = "INVALIDATED"


class AlternateRevisionKind(ImmutableStrEnum):
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    SUPERSEDED = "SUPERSEDED"
    INVALIDATED = "INVALIDATED"


class AlternateObservationState(ImmutableStrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"


class AlternateAvailability(ImmutableStrEnum):
    IN_STOCK = "IN_STOCK"
    DELAYED = "DELAYED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class AlternateValidityState(ImmutableStrEnum):
    VERIFIED = "VERIFIED"
    COMPATIBILITY_REVIEW_REQUIRED = "COMPATIBILITY_REVIEW_REQUIRED"
    REJECTED = "REJECTED"


class CompatibilityDecision(ImmutableStrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MORE_EVIDENCE_REQUIRED = "MORE_EVIDENCE_REQUIRED"


class ContactState(ImmutableStrEnum):
    NONE_OBSERVED = "NONE_OBSERVED"
    INBOUND_OBSERVED = "INBOUND_OBSERVED"
    OUTBOUND_OBSERVED = "OUTBOUND_OBSERVED"
    BIDIRECTIONAL_OBSERVED = "BIDIRECTIONAL_OBSERVED"
    UNKNOWN = "UNKNOWN"


class ContactEventType(ImmutableStrEnum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"
    UNKNOWN = "UNKNOWN"
    CORRECTION = "CORRECTION"


class ContactWorkflowState(ImmutableStrEnum):
    NOT_CONTACTED = "NOT_CONTACTED"
    CONTACT_REQUIRED = "CONTACT_REQUIRED"
    CONTACT_ATTEMPTED = "CONTACT_ATTEMPTED"
    AWAITING_CUSTOMER = "AWAITING_CUSTOMER"
    CUSTOMER_APPROVED = "CUSTOMER_APPROVED"
    CUSTOMER_DECLINED = "CUSTOMER_DECLINED"
    NO_RESPONSE = "NO_RESPONSE"


class ContactWorkflowEventType(ImmutableStrEnum):
    CONTACT_REQUIRED_DERIVED = "CONTACT_REQUIRED_DERIVED"
    CONTACT_ATTEMPT_RECORDED = "CONTACT_ATTEMPT_RECORDED"
    AWAITING_CUSTOMER_RECORDED = "AWAITING_CUSTOMER_RECORDED"
    CUSTOMER_APPROVAL_RECORDED = "CUSTOMER_APPROVAL_RECORDED"
    CUSTOMER_DECLINE_RECORDED = "CUSTOMER_DECLINE_RECORDED"
    NO_RESPONSE_RECORDED = "NO_RESPONSE_RECORDED"


class WWCAuthorRelation(ImmutableStrEnum):
    TARGET_REP = "TARGET_REP"
    OTHER_REP = "OTHER_REP"
    UNCERTAIN = "UNCERTAIN"


class WWCTimingState(ImmutableStrEnum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    UNCERTAIN = "UNCERTAIN"


class WWCProjectionState(ImmutableStrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    ACTIVE_SELF = "ACTIVE_SELF"
    ACTIVE_OTHER_REP = "ACTIVE_OTHER_REP"
    EXPIRED_OTHER_REP = "EXPIRED_OTHER_REP"
    AUTHOR_UNCERTAIN = "AUTHOR_UNCERTAIN"
    TIMING_UNCERTAIN = "TIMING_UNCERTAIN"
    AUTHOR_AND_TIMING_UNCERTAIN = "AUTHOR_AND_TIMING_UNCERTAIN"


class DedupeState(ImmutableStrEnum):
    NOT_PRESENT = "NOT_PRESENT"
    SOURCE_PRESENT = "SOURCE_PRESENT"
    NOT_CANDIDATE = "NOT_CANDIDATE"
    CANDIDATE = "CANDIDATE"
    INCOMPLETE = "INCOMPLETE"
    APPROVED_AWAITING_VERIFICATION = "APPROVED_AWAITING_VERIFICATION"
    REJECTED = "REJECTED"
    CONFIRMED = "CONFIRMED"


class HumanFactResultCode(ImmutableStrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NO_VIABLE_ALTERNATE = "NO_VIABLE_ALTERNATE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    SCENARIO_SELECTED = "SCENARIO_SELECTED"
    SCENARIO_GROUPED = "SCENARIO_GROUPED"
    COORDINATION_RESOLUTION_RECORDED = "COORDINATION_RESOLUTION_RECORDED"
    CORRECTED = "CORRECTED"


class HumanFactUsageKind(ImmutableStrEnum):
    ALTERNATE_RESEARCH = "ALTERNATE_RESEARCH"
    COMPATIBILITY_DECISION = "COMPATIBILITY_DECISION"
    CUSTOMER_APPROVAL = "CUSTOMER_APPROVAL"
    DEDUPE_DECISION = "DEDUPE_DECISION"
    NO_ACTION_DECISION = "NO_ACTION_DECISION"
    OUT_OF_SCOPE_CLOSURE = "OUT_OF_SCOPE_CLOSURE"
    SCENARIO_SELECTION = "SCENARIO_SELECTION"
    SCENARIO_GROUPING = "SCENARIO_GROUPING"
    COORDINATION_RESOLUTION = "COORDINATION_RESOLUTION"


class ActionContextKind(ImmutableStrEnum):
    SUBSTITUTION = "SUBSTITUTION"
    CUSTOMER_CONTACT = "CUSTOMER_CONTACT"
    FULFILLMENT_SPLIT_REVIEW = "FULFILLMENT_SPLIT_REVIEW"
    DS_SEPARATION_REVIEW = "DS_SEPARATION_REVIEW"
    RESULTING_ORDER_LINK_REVIEW = "RESULTING_ORDER_LINK_REVIEW"
    INTERVENTION_VERIFICATION = "INTERVENTION_VERIFICATION"


class ActionContextState(ImmutableStrEnum):
    OPEN = "OPEN"
    CLOSED_COMPLETED = "CLOSED_COMPLETED"
    CLOSED_ABANDONED = "CLOSED_ABANDONED"
    CLOSED_SUPERSEDED = "CLOSED_SUPERSEDED"


class ActionContextCompletionTrigger(ImmutableStrEnum):
    HUMAN_ACCEPTED = "HUMAN_ACCEPTED"
    SYSTEM_VERIFIED = "SYSTEM_VERIFIED"


class ActionContextCloseReason(ImmutableStrEnum):
    ACTION_VERIFIED = "ACTION_VERIFIED"
    DECISION_RECORDED = "DECISION_RECORDED"
    REVIEW_FINISHED = "REVIEW_FINISHED"
    HUMAN_ABANDONED = "HUMAN_ABANDONED"
    SUPERSEDED_BY_LATER_ATTEMPT = "SUPERSEDED_BY_LATER_ATTEMPT"


class ActionContextEventType(ImmutableStrEnum):
    OPENED = "ACTION_CONTEXT_OPENED"
    OBSERVATION_LINKED = "ACTION_CONTEXT_OBSERVATION_LINKED"
    COMPLETED = "ACTION_CONTEXT_COMPLETED"
    ABANDONED = "ACTION_CONTEXT_ABANDONED"
    SUPERSEDED = "ACTION_CONTEXT_SUPERSEDED"


class WWCEventType(ImmutableStrEnum):
    OBSERVED = "OBSERVED"
    CORRECTED = "CORRECTED"


class DedupeEventType(ImmutableStrEnum):
    SOURCE_OBSERVED = "SOURCE_OBSERVED"
    CANDIDATE_IDENTIFIED = "CANDIDATE_IDENTIFIED"
    ANALYSIS_INCOMPLETE = "ANALYSIS_INCOMPLETE"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    HUMAN_REJECTED = "HUMAN_REJECTED"
    VERIFIED_SOURCE_CONFIRMED = "VERIFIED_SOURCE_CONFIRMED"
    CANDIDATE_WITHDRAWN = "CANDIDATE_WITHDRAWN"
    ELIGIBILITY_RETURNED = "ELIGIBILITY_RETURNED"


class HumanFactEventType(ImmutableStrEnum):
    RECORDED = "RECORDED"
    CORRECTED = "CORRECTED"


class AttentionCondition(ImmutableStrEnum):
    RECHECK_REQUIRED = "RECHECK_REQUIRED"
    INTERVENTION_VERIFICATION_REQUIRED = "INTERVENTION_VERIFICATION_REQUIRED"
    SOURCE_ABSENCE_RECHECK_REQUIRED = "SOURCE_ABSENCE_RECHECK_REQUIRED"
    RESULTING_ORDER_LINK_REVIEW = "RESULTING_ORDER_LINK_REVIEW"
    HUMAN_COORDINATION_REVIEW_REQUIRED = "HUMAN_COORDINATION_REVIEW_REQUIRED"


class InterventionType(ImmutableStrEnum):
    FULFILLMENT_SPLIT = "FULFILLMENT_SPLIT"
    PRODUCT_SUBSTITUTION = "PRODUCT_SUBSTITUTION"
    DS_SEPARATION = "DS_SEPARATION"


class InterventionStatus(ImmutableStrEnum):
    VERIFIED_ACTIVE = "VERIFIED_ACTIVE"
    PARTIALLY_REVERSED = "PARTIALLY_REVERSED"
    REVERSED = "REVERSED"


class ActionVerificationState(ImmutableStrEnum):
    UNVERIFIED = "UNVERIFIED"
    SYSTEM_VERIFIED = "SYSTEM_VERIFIED"
    HUMAN_VERIFIED = "HUMAN_VERIFIED"


class ValueVerificationState(ImmutableStrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNVERIFIED = "UNVERIFIED"
    SYSTEM_VERIFIED = "SYSTEM_VERIFIED"
    HUMAN_VERIFIED = "HUMAN_VERIFIED"
    SYSTEM_AUTHORITATIVE_CONFLICT = "SYSTEM_AUTHORITATIVE_CONFLICT"


class ResultingOrderLinkState(ImmutableStrEnum):
    AUTO_LINKED = "AUTO_LINKED"
    HUMAN_CONFIRMED = "HUMAN_CONFIRMED"
    AMBIGUOUS = "AMBIGUOUS"


class ResultingOrderLinkSearchState(ImmutableStrEnum):
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"


class ValueEventType(ImmutableStrEnum):
    INITIAL_VERIFIED_VALUE = "INITIAL_VERIFIED_VALUE"
    CORRECTION = "CORRECTION"
    PARTIAL_REVERSAL = "PARTIAL_REVERSAL"
    FULL_REVERSAL = "FULL_REVERSAL"


class KPIContributionState(ImmutableStrEnum):
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    RETAINED = "RETAINED"
    FINALIZED = "FINALIZED"


def known_fact(value: _T) -> ObservedTaggedValue[_T]:
    """Construct a KNOWN shared tagged value without accepting an alias or float."""

    source: object = value.value if isinstance(value, ImmutableStrEnum) else value

    def parse_known(candidate: object) -> _T:
        if candidate is not source:
            raise DOIModelError("OBSERVATION_ALIAS")
        return cast(_T, candidate)

    return parse_observed_tagged_value(
        {"raw_hint": None, "reason_code": None, "tag": "KNOWN", "value": source},
        version=OBSERVED_TAGGED_VALUE_VERSION,
        known_value_parser=parse_known,
        allowed_unknown_reasons=_ALL_REASON_CODES,
    )


def unknown_fact(reason_code: str, *, raw_hint: str | None = None) -> ObservedTaggedValue[None]:
    """Construct an UNKNOWN value; the owning record enforces the field-specific code."""

    return cast(
        ObservedTaggedValue[None],
        parse_observed_tagged_value(
            {
                "raw_hint": raw_hint,
                "reason_code": reason_code,
                "tag": "UNKNOWN",
                "value": None,
            },
            version=OBSERVED_TAGGED_VALUE_VERSION,
            known_value_parser=lambda _: None,
            allowed_unknown_reasons=_ALL_REASON_CODES,
            allowed_raw_hints=frozenset(
                {
                    "CONTRADICTORY_AVAILABILITY_TOKENS",
                    "CONTRADICTORY_DS_TOKENS",
                    "CONTRADICTORY_ETA_TOKENS",
                    "ETA_OUT_OF_RANGE",
                    "UNRECOGNIZED_AVAILABILITY_TOKEN",
                    "UNRECOGNIZED_DS_TOKEN",
                    "UNRECOGNIZED_ETA_TOKEN",
                    "UNSUPPORTED_ETA_FORMAT",
                }
            ),
        ),
    )


def not_applicable_fact() -> ObservedTaggedValue[None]:
    return NotApplicableObservedValue()


def _known_value(value: ObservedTaggedValue[object]) -> object | None:
    return value.value if type(value) is KnownObservedValue else None


def _validate_observed(
    value: object,
    *,
    known_types: tuple[type[object], ...],
    unknown_reason: str,
    known_enum: type[ImmutableStrEnum] | None = None,
    allow_not_applicable: bool = True,
    code: str,
) -> None:
    if type(value) is KnownObservedValue:
        observed = cast(KnownObservedValue[object], value).value
        if known_enum is not None:
            if type(observed) is not str:
                raise DOIModelError(code)
            enum_invalid = False
            try:
                known_enum(observed)
            except ValueError:
                enum_invalid = True
            if enum_invalid:
                raise DOIModelError(code)
        elif type(observed) not in known_types:
            raise DOIModelError(code)
        return
    if type(value) is UnknownObservedValue:
        if cast(UnknownObservedValue, value).reason_code != unknown_reason:
            raise DOIModelError(code)
        return
    if type(value) is NotApplicableObservedValue and allow_not_applicable:
        return
    raise DOIModelError(code)


def _observation_json(value: ObservedTaggedValue[object]) -> dict[str, object]:
    mapped = value.to_mapping()
    known = mapped["value"]
    if type(known) in {EvidenceId, RepId, SkuId}:
        mapped["value"] = cast(EvidenceId | RepId | SkuId, known).value
    elif type(known) is CanonicalTimestamp:
        mapped["value"] = cast(CanonicalTimestamp, known).value
    elif type(known) in {Quantity, PositiveQuantity}:
        mapped["value"] = cast(Quantity, known).to_json_value()
    elif type(known) is Money:
        mapped["value"] = cast(Money, known).to_json_value()
    return mapped


def _binding_json(binding: HashBinding) -> dict[str, str]:
    return {"domain": binding.domain, "sha256": binding.sha256}


def rule_pack_hash_binding() -> HashBinding:
    value = {
        "model_schema_version": DOI_MODEL_SCHEMA_VERSION,
        "overlap_policy": M3_OVERLAP_POLICY,
        "rule_pack_version": DOI_RULE_PACK_VERSION,
        "tr_037_policy": TR_037_MANUAL_REVIEW_POLICY,
        "uncertainty_containment_policy": M3_UNCERTAINTY_CONTAINMENT_POLICY,
    }
    return domain_hash(
        DOI_RULE_PACK_HASH_DOMAIN,
        canonical_json_bytes(value, expected_members=set(value)),
    )


def _require_sorted_unique_tokens(values: object, *, code: str) -> None:
    if type(values) is not tuple or any(
        not isinstance(value, ImmutableStrEnum) for value in values
    ):
        raise DOIModelError(code)
    tokens = [cast(ImmutableStrEnum, value).value for value in values]
    if tokens != sorted(tokens) or len(tokens) != len(set(tokens)):
        raise DOIModelError(code)


@dataclass(frozen=True, slots=True, repr=False)
class LineContinuityProof:
    state: LineContinuityState
    proof_type: ContinuityProofType
    stable_source_line_id: EvidenceId | None
    composite_binding: HashBinding | None
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-line-continuity-proof/v1"
    COMPOSITE_DOMAIN: ClassVar[str] = "doi-line-continuity-composite/v1"

    def __post_init__(self) -> None:
        if (
            type(self.state) is not LineContinuityState
            or type(self.proof_type) is not ContinuityProofType
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("LINE_CONTINUITY_INVALID")
        stable = self.proof_type is ContinuityProofType.STABLE_SOURCE_LINE_ID
        composite = self.proof_type is ContinuityProofType.CLOSED_COMPOSITE
        if stable:
            valid = (
                type(self.stable_source_line_id) is EvidenceId
                and self.composite_binding is None
            )
        elif composite:
            valid = (
                self.stable_source_line_id is None
                and type(self.composite_binding) is HashBinding
                and self.composite_binding.domain == self.COMPOSITE_DOMAIN
            )
        else:
            valid = self.stable_source_line_id is None and self.composite_binding is None
        if not valid or (self.state is LineContinuityState.VERIFIED) != (stable or composite):
            raise DOIModelError("LINE_CONTINUITY_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "composite_binding": (
                _binding_json(self.composite_binding)
                if self.composite_binding is not None
                else None
            ),
            "proof_type": self.proof_type.value,
            "schema_version": self.schema_version,
            "stable_source_line_id": (
                self.stable_source_line_id.value
                if self.stable_source_line_id is not None
                else None
            ),
            "state": self.state.value,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), expected_members=set(self.to_dict()))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "LineContinuityProof(<closed>)"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DOILineItemSnapshot:
    line_snapshot_id: LineSnapshotId
    stable_source_line_id: ObservedTaggedValue[EvidenceId]
    relevant_merchandise: bool
    activity: ObservedTaggedValue[str]
    drop_ship_state: ObservedTaggedValue[str]
    availability: ObservedTaggedValue[str]
    eta: ObservedTaggedValue[CanonicalTimestamp]
    ordered_quantity: ObservedTaggedValue[Quantity]
    active_quantity: ObservedTaggedValue[Quantity]
    canceled_quantity: ObservedTaggedValue[Quantity]
    explicitly_available_quantity: ObservedTaggedValue[Quantity]
    quantity_availability: ObservedTaggedValue[str]
    es_number: ObservedTaggedValue[SkuId]
    mfg_number: ObservedTaggedValue[SkuId]
    unit_value: ObservedTaggedValue[Money]
    active_line_value: ObservedTaggedValue[Money]
    line_sales_rep: ObservedTaggedValue[RepId]
    continuity: LineContinuityProof
    source: SourceRef
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-line-item-snapshot/v1"

    def __post_init__(self) -> None:
        if (
            type(self.line_snapshot_id) is not LineSnapshotId
            or type(self.relevant_merchandise) is not bool
            or type(self.continuity) is not LineContinuityProof
            or type(self.source) is not SourceRef
            or self.source.source_kind is not SourceKind.SYNTHETIC_ORDER_FIXTURE
            or self.source.object_namespace is not SourceObjectNamespace.SYNTHETIC_ORDER
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_LINE_INVALID")
        enum_fields = (
            (self.activity, LineActivity, "RC-125"),
            (self.drop_ship_state, DropShipState, "RC-017"),
            (self.availability, LineAvailability, "RC-016"),
            (self.quantity_availability, QuantityAvailability, "RC-132"),
        )
        for observed, enum_type, reason in enum_fields:
            _validate_observed(
                observed,
                known_types=(),
                unknown_reason=reason,
                known_enum=enum_type,
                code="DOI_LINE_OBSERVATION_INVALID",
            )
        for observed, known_types, reason in (
            (self.stable_source_line_id, (EvidenceId,), "RC-124"),
            (self.eta, (CanonicalTimestamp,), "RC-115"),
            (self.ordered_quantity, (Quantity,), "RC-128"),
            (self.active_quantity, (Quantity,), "RC-129"),
            (self.canceled_quantity, (Quantity,), "RC-130"),
            (self.explicitly_available_quantity, (Quantity,), "RC-131"),
            (self.es_number, (SkuId,), "RC-126"),
            (self.mfg_number, (SkuId,), "RC-127"),
            (self.unit_value, (Money,), "RC-133"),
            (self.active_line_value, (Money,), "RC-134"),
            (self.line_sales_rep, (RepId,), "RC-135"),
        ):
            _validate_observed(
                observed,
                known_types=known_types,
                unknown_reason=reason,
                code="DOI_LINE_OBSERVATION_INVALID",
            )
        stable_value = _known_value(cast(ObservedTaggedValue[object], self.stable_source_line_id))
        if self.continuity.proof_type is ContinuityProofType.STABLE_SOURCE_LINE_ID:
            if stable_value != self.continuity.stable_source_line_id:
                raise DOIModelError("DOI_LINE_CONTINUITY_MISMATCH")

    def to_dict(self) -> dict[str, object]:
        return {
            "active_line_value": _observation_json(self.active_line_value),
            "active_quantity": _observation_json(self.active_quantity),
            "activity": _observation_json(self.activity),
            "availability": _observation_json(self.availability),
            "canceled_quantity": _observation_json(self.canceled_quantity),
            "continuity": _binding_json(self.continuity.hash_binding()),
            "drop_ship_state": _observation_json(self.drop_ship_state),
            "es_number": _observation_json(self.es_number),
            "eta": _observation_json(self.eta),
            "explicitly_available_quantity": _observation_json(
                self.explicitly_available_quantity
            ),
            "line_sales_rep": _observation_json(self.line_sales_rep),
            "line_snapshot_id": self.line_snapshot_id.to_json_value(),
            "mfg_number": _observation_json(self.mfg_number),
            "ordered_quantity": _observation_json(self.ordered_quantity),
            "quantity_availability": _observation_json(self.quantity_availability),
            "relevant_merchandise": self.relevant_merchandise,
            "schema_version": self.schema_version,
            "source": _binding_json(self.source.hash_binding()),
            "source_ref_id": self.source.source_ref_id.value,
            "stable_source_line_id": _observation_json(self.stable_source_line_id),
            "unit_value": _observation_json(self.unit_value),
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOILineItemSnapshot(<closed>)"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class WWCFinding:
    finding_id: EvidenceId
    presence: FindingPresenceV2
    author_relation: ObservedTaggedValue[str]
    timing_state: ObservedTaggedValue[str]
    marker: ObservedTaggedValue[str]
    observed_at: ObservedTaggedValue[CanonicalTimestamp]
    source: SourceRef
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-wwc-finding/v1"

    def __post_init__(self) -> None:
        if (
            type(self.finding_id) is not EvidenceId
            or type(self.presence) is not FindingPresenceV2
            or type(self.source) is not SourceRef
            or self.source.object_namespace is not SourceObjectNamespace.SYNTHETIC_ORDER
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("WWC_FINDING_INVALID")
        _validate_observed(
            self.author_relation,
            known_types=(),
            unknown_reason="RC-055",
            known_enum=WWCAuthorRelation,
            code="WWC_AUTHOR_INVALID",
        )
        _validate_observed(
            self.timing_state,
            known_types=(),
            unknown_reason="RC-056",
            known_enum=WWCTimingState,
            code="WWC_TIMING_INVALID",
        )
        _validate_observed(
            self.marker,
            known_types=(str,),
            unknown_reason="RC-122",
            code="WWC_MARKER_INVALID",
        )
        _validate_observed(
            self.observed_at,
            known_types=(CanonicalTimestamp,),
            unknown_reason="RC-056",
            code="WWC_TIMESTAMP_INVALID",
        )
        if type(self.marker) is KnownObservedValue:
            marker = cast(str, self.marker.value)
            if _UPPER_TOKEN.fullmatch(marker) is None:
                raise DOIModelError("WWC_MARKER_INVALID")
        if self.presence is FindingPresenceV2.PRESENT:
            if any(
                type(value) is NotApplicableObservedValue
                for value in (
                    self.author_relation,
                    self.timing_state,
                    self.marker,
                    self.observed_at,
                )
            ):
                raise DOIModelError("WWC_PRESENT_PARTITION_INVALID")
        elif any(
            type(value) is not NotApplicableObservedValue
            for value in (self.author_relation, self.timing_state, self.marker, self.observed_at)
        ):
            raise DOIModelError("WWC_NONPRESENT_PARTITION_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "author_relation": _observation_json(self.author_relation),
            "finding_id": self.finding_id.value,
            "marker": _observation_json(self.marker),
            "observed_at": _observation_json(self.observed_at),
            "presence": self.presence.value,
            "schema_version": self.schema_version,
            "source": _binding_json(self.source.hash_binding()),
            "timing_state": _observation_json(self.timing_state),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), expected_members=set(self.to_dict()))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "WWCFinding(<closed>)"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DedupeFinding:
    finding_id: EvidenceId
    presence: FindingPresenceV2
    observed_at: CanonicalTimestamp | None
    state: DedupeState
    source: SourceRef
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-dedupe-finding/v1"

    def __post_init__(self) -> None:
        if (
            type(self.finding_id) is not EvidenceId
            or type(self.presence) is not FindingPresenceV2
            or type(self.state) is not DedupeState
            or type(self.source) is not SourceRef
            or self.source.object_namespace is not SourceObjectNamespace.SYNTHETIC_ORDER
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DEDUPE_FINDING_INVALID")
        present = self.presence is FindingPresenceV2.PRESENT
        if present != (type(self.observed_at) is CanonicalTimestamp):
            raise DOIModelError("DEDUPE_TIMESTAMP_PARTITION_INVALID")
        expected_state = (
            DedupeState.SOURCE_PRESENT if present else DedupeState.NOT_PRESENT
        )
        if self.state is not expected_state:
            raise DOIModelError("DEDUPE_SOURCE_FINDING_STATE_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "finding_id": self.finding_id.value,
            "observed_at": self.observed_at.value if self.observed_at is not None else None,
            "presence": self.presence.value,
            "schema_version": self.schema_version,
            "source": _binding_json(self.source.hash_binding()),
            "state": self.state.value,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), expected_members=set(self.to_dict()))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DedupeFinding(<closed>)"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class StructuredHumanFact:
    fact_id: EvidenceId
    action_context_id: EvidenceId
    action_context: DOIActionContext
    order_id: DoiOrderId
    evaluation_id: EvaluationId
    usage_kind: HumanFactUsageKind
    result_code: HumanFactResultCode
    actor: RepId
    occurred_at: CanonicalTimestamp
    authority_grant: HumanAuthorityGrant
    source: SourceRef
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-structured-human-fact/v1"

    def __post_init__(self) -> None:
        if (
            type(self.fact_id) is not EvidenceId
            or type(self.action_context_id) is not EvidenceId
            or type(self.action_context) is not DOIActionContext
            or self.action_context.action_context_id != self.action_context_id
            or self.action_context.state is not ActionContextState.OPEN
            or type(self.order_id) is not DoiOrderId
            or self.action_context.order_id != self.order_id
            or type(self.evaluation_id) is not EvaluationId
            or self.action_context.evaluation_id != self.evaluation_id
            or type(self.usage_kind) is not HumanFactUsageKind
            or type(self.result_code) is not HumanFactResultCode
            or type(self.actor) is not RepId
            or type(self.occurred_at) is not CanonicalTimestamp
            or type(self.authority_grant) is not HumanAuthorityGrant
            or self.authority_grant.actor != self.actor
            or self.authority_grant.action_context_id != self.action_context_id
            or self.authority_grant.action_context_binding
            != self.action_context.hash_binding()
            or type(self.source) is not SourceRef
            or self.source != self.authority_grant.source
            or self.source.source_kind is not SourceKind.SYNTHETIC_INTERACTION_FIXTURE
            or self.source.object_namespace
            is not SourceObjectNamespace.SYNTHETIC_INTERACTION
            or type(self.source.object_id) is not InteractionId
            or (
                self.occurred_at.epoch_seconds,
                self.occurred_at.nanosecond,
            )
            < (
                self.authority_grant.granted_at.epoch_seconds,
                self.authority_grant.granted_at.nanosecond,
            )
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("STRUCTURED_HUMAN_FACT_INVALID")
        expected_results = {
            HumanFactUsageKind.ALTERNATE_RESEARCH: frozenset(
                {HumanFactResultCode.NO_VIABLE_ALTERNATE}
            ),
            HumanFactUsageKind.COMPATIBILITY_DECISION: frozenset(
                {HumanFactResultCode.APPROVED, HumanFactResultCode.REJECTED}
            ),
            HumanFactUsageKind.CUSTOMER_APPROVAL: frozenset(
                {HumanFactResultCode.APPROVED, HumanFactResultCode.REJECTED}
            ),
            HumanFactUsageKind.DEDUPE_DECISION: frozenset(
                {HumanFactResultCode.APPROVED, HumanFactResultCode.REJECTED}
            ),
            HumanFactUsageKind.NO_ACTION_DECISION: frozenset(
                {HumanFactResultCode.APPROVED}
            ),
            HumanFactUsageKind.OUT_OF_SCOPE_CLOSURE: frozenset(
                {HumanFactResultCode.OUT_OF_SCOPE}
            ),
            HumanFactUsageKind.SCENARIO_SELECTION: frozenset(
                {HumanFactResultCode.SCENARIO_SELECTED}
            ),
            HumanFactUsageKind.SCENARIO_GROUPING: frozenset(
                {HumanFactResultCode.SCENARIO_GROUPED}
            ),
            HumanFactUsageKind.COORDINATION_RESOLUTION: frozenset(
                {HumanFactResultCode.COORDINATION_RESOLUTION_RECORDED}
            ),
        }
        if self.result_code not in expected_results[self.usage_kind]:
            raise DOIModelError("STRUCTURED_HUMAN_FACT_RESULT_INVALID")

    @classmethod
    def create(
        cls,
        *,
        fact_id: EvidenceId,
        action_context: DOIActionContext,
        evaluation_id: EvaluationId,
        usage_kind: HumanFactUsageKind,
        result_code: HumanFactResultCode,
        authority_grant: HumanAuthorityGrant,
        occurred_at: CanonicalTimestamp,
        source: SourceRef,
    ) -> StructuredHumanFact:
        return cls(
            fact_id=fact_id,
            action_context_id=action_context.action_context_id,
            action_context=action_context,
            order_id=action_context.order_id,
            evaluation_id=evaluation_id,
            usage_kind=usage_kind,
            result_code=result_code,
            actor=authority_grant.actor,
            occurred_at=occurred_at,
            authority_grant=authority_grant,
            source=source,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "action_context": _binding_json(self.action_context.hash_binding()),
            "action_context_id": self.action_context_id.value,
            "actor": self.actor.value,
            "authority_grant": _binding_json(self.authority_grant.hash_binding()),
            "fact_id": self.fact_id.value,
            "evaluation_id": self.evaluation_id.value,
            "occurred_at": self.occurred_at.value,
            "order_id": self.order_id.to_json_value(),
            "result_code": self.result_code.value,
            "schema_version": self.schema_version,
            "source": _binding_json(self.source.hash_binding()),
            "usage_kind": self.usage_kind.value,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), expected_members=set(self.to_dict()))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "StructuredHumanFact(<closed>)"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DedupeVerificationFact:
    verification_id: EvidenceId
    order_id: DoiOrderId
    prior_snapshot: DOIOrderSnapshot
    verified_snapshot: DOIOrderSnapshot
    approved_human_fact_binding: HashBinding
    prior_projection_binding: HashBinding
    approved_at: CanonicalTimestamp
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-dedupe-verification-fact/v1"

    def __post_init__(self) -> None:
        if (
            type(self.verification_id) is not EvidenceId
            or type(self.order_id) is not DoiOrderId
            or type(self.prior_snapshot) is not DOIOrderSnapshot
            or type(self.verified_snapshot) is not DOIOrderSnapshot
            or self.prior_snapshot.order_id != self.order_id
            or self.verified_snapshot.order_id != self.order_id
            or self.prior_snapshot.source_presence is not SourcePresence.PRESENT
            or self.verified_snapshot.source_presence is not SourcePresence.PRESENT
            or self.prior_snapshot.dedupe_finding.presence
            is not FindingPresenceV2.PRESENT
            or self.verified_snapshot.dedupe_finding.presence
            is not FindingPresenceV2.PRESENT
            or type(self.approved_human_fact_binding) is not HashBinding
            or self.approved_human_fact_binding.domain
            != StructuredHumanFact.HASH_DOMAIN
            or type(self.prior_projection_binding) is not HashBinding
            or self.prior_projection_binding.domain != "doi-dedupe-projection/v1"
            or type(self.approved_at) is not CanonicalTimestamp
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DEDUPE_VERIFICATION_FACT_INVALID")
        prior_finding = self.prior_snapshot.dedupe_finding
        verified_finding = self.verified_snapshot.dedupe_finding
        if (
            self.prior_snapshot.snapshot_id == self.verified_snapshot.snapshot_id
            or self.prior_snapshot.run_id == self.verified_snapshot.run_id
            or self.prior_snapshot.hash_binding()
            == self.verified_snapshot.hash_binding()
            or prior_finding.finding_id == verified_finding.finding_id
            or prior_finding.hash_binding() == verified_finding.hash_binding()
            or prior_finding.source != verified_finding.source
        ):
            raise DOIModelError("DEDUPE_VERIFICATION_REUSED_SOURCE_OBSERVATION")
        approved_instant = (self.approved_at.epoch_seconds, self.approved_at.nanosecond)
        prior_snapshot_instant = (
            self.prior_snapshot.source_observed_at.epoch_seconds,
            self.prior_snapshot.source_observed_at.nanosecond,
        )
        prior_finding_at = cast(CanonicalTimestamp, prior_finding.observed_at)
        prior_finding_instant = (
            prior_finding_at.epoch_seconds,
            prior_finding_at.nanosecond,
        )
        verified_snapshot_instant = (
            self.verified_snapshot.source_observed_at.epoch_seconds,
            self.verified_snapshot.source_observed_at.nanosecond,
        )
        verified_finding_at = cast(CanonicalTimestamp, verified_finding.observed_at)
        verified_finding_instant = (
            verified_finding_at.epoch_seconds,
            verified_finding_at.nanosecond,
        )
        if (
            prior_snapshot_instant > approved_instant
            or prior_finding_instant > approved_instant
            or verified_snapshot_instant <= approved_instant
            or verified_finding_instant <= approved_instant
        ):
            raise DOIModelError("DEDUPE_VERIFICATION_NOT_LATER_THAN_APPROVAL")

    def to_dict(self) -> dict[str, object]:
        return {
            "approved_at": self.approved_at.value,
            "approved_human_fact_binding": _binding_json(
                self.approved_human_fact_binding
            ),
            "order_id": self.order_id.to_json_value(),
            "prior_finding": _binding_json(
                self.prior_snapshot.dedupe_finding.hash_binding()
            ),
            "prior_projection_binding": _binding_json(
                self.prior_projection_binding
            ),
            "prior_snapshot": _binding_json(self.prior_snapshot.hash_binding()),
            "schema_version": self.schema_version,
            "verification_id": self.verification_id.value,
            "verified_finding": _binding_json(
                self.verified_snapshot.dedupe_finding.hash_binding()
            ),
            "verified_snapshot": _binding_json(
                self.verified_snapshot.hash_binding()
            ),
            "verified_source_observed_at": (
                self.verified_snapshot.source_observed_at.value
            ),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), expected_members=set(self.to_dict()))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DedupeVerificationFact(<closed>)"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DOIOrderSnapshot:
    snapshot_id: DoiSnapshotId
    run_id: DoiRunId
    order_id: DoiOrderId
    source_observed_at: CanonicalTimestamp
    completeness_proof: WholeOrderCompletenessProof
    source_presence: SourcePresence
    order_state: ObservedTaggedValue[str]
    current_rep_value: ObservedTaggedValue[RepId]
    current_rep_relation: ObservedTaggedValue[str]
    geography_class: ObservedTaggedValue[str]
    payment_condition: ObservedTaggedValue[str]
    order_total: ObservedTaggedValue[Money]
    wwc_finding: WWCFinding
    dedupe_finding: DedupeFinding
    lines: tuple[DOILineItemSnapshot, ...]
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-order-snapshot/v1"

    def __post_init__(self) -> None:
        if (
            type(self.snapshot_id) is not DoiSnapshotId
            or type(self.run_id) is not DoiRunId
            or type(self.order_id) is not DoiOrderId
            or type(self.source_observed_at) is not CanonicalTimestamp
            or type(self.completeness_proof) is not WholeOrderCompletenessProof
            or type(self.source_presence) is not SourcePresence
            or type(self.wwc_finding) is not WWCFinding
            or type(self.dedupe_finding) is not DedupeFinding
            or type(self.lines) is not tuple
            or any(type(line) is not DOILineItemSnapshot for line in self.lines)
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_SNAPSHOT_INVALID")
        if (
            self.completeness_proof.requested_order_id != self.order_id.value
            or self.completeness_proof.observed_order_id != self.order_id.value
            or self.completeness_proof.order_source_observed_at != self.source_observed_at
        ):
            raise DOIModelError("DOI_SNAPSHOT_PROOF_MISMATCH")
        expected_manifest_ids = tuple(
            entry.line_id for entry in self.completeness_proof.ordered_line_manifest
        )
        line_ids = tuple(line.line_snapshot_id.value for line in self.lines)
        if line_ids != expected_manifest_ids or len(line_ids) != len(set(line_ids)):
            raise DOIModelError("DOI_SNAPSHOT_LINE_MANIFEST_MISMATCH")
        for observed, enum_type, reason in (
            (self.order_state, OrderState, "RC-116"),
            (self.current_rep_relation, RepRelation, "RC-118"),
            (self.geography_class, GeographyClass, "RC-119"),
            (self.payment_condition, PaymentCondition, "RC-120"),
        ):
            _validate_observed(
                observed,
                known_types=(),
                unknown_reason=reason,
                known_enum=enum_type,
                allow_not_applicable=False,
                code="DOI_SNAPSHOT_OBSERVATION_INVALID",
            )
        _validate_observed(
            self.current_rep_value,
            known_types=(RepId,),
            unknown_reason="RC-117",
            allow_not_applicable=False,
            code="DOI_SNAPSHOT_OBSERVATION_INVALID",
        )
        _validate_observed(
            self.order_total,
            known_types=(Money,),
            unknown_reason="RC-121",
            code="DOI_SNAPSHOT_OBSERVATION_INVALID",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "completeness_proof": _binding_json(self.completeness_proof.hash_binding()),
            "current_rep_relation": _observation_json(self.current_rep_relation),
            "current_rep_value": _observation_json(self.current_rep_value),
            "dedupe_finding": _binding_json(self.dedupe_finding.hash_binding()),
            "geography_class": _observation_json(self.geography_class),
            "lines": [_binding_json(line.hash_binding()) for line in self.lines],
            "order_id": self.order_id.to_json_value(),
            "order_state": _observation_json(self.order_state),
            "order_total": _observation_json(self.order_total),
            "payment_condition": _observation_json(self.payment_condition),
            "run_id": self.run_id.to_json_value(),
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id.to_json_value(),
            "source_observed_at": self.source_observed_at.value,
            "source_presence": self.source_presence.value,
            "wwc_finding": _binding_json(self.wwc_finding.hash_binding()),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), expected_members=set(self.to_dict()))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIOrderSnapshot(<closed>)"


@dataclass(frozen=True, slots=True, repr=False)
class DOIOpportunityScopeComponent:
    line_snapshot_id: LineSnapshotId
    quantity: PositiveQuantity
    role: OpportunityScopeRole

    def __post_init__(self) -> None:
        if (
            type(self.line_snapshot_id) is not LineSnapshotId
            or type(self.quantity) is not PositiveQuantity
            or type(self.role) is not OpportunityScopeRole
        ):
            raise DOIModelError("OPPORTUNITY_SCOPE_COMPONENT_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "line_snapshot_id": self.line_snapshot_id.to_json_value(),
            "quantity": self.quantity.to_json_value(),
            "role": self.role.value,
        }

    def __repr__(self) -> str:
        return "DOIOpportunityScopeComponent(<closed>)"


@dataclass(frozen=True, slots=True, repr=False)
class DOIOpportunityScope:
    components: tuple[DOIOpportunityScopeComponent, ...]
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-opportunity-scope/v1"

    def __post_init__(self) -> None:
        if (
            type(self.components) is not tuple
            or not self.components
            or any(type(item) is not DOIOpportunityScopeComponent for item in self.components)
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("OPPORTUNITY_SCOPE_INVALID")
        keys = [
            (item.line_snapshot_id.to_json_value(), item.role.value)
            for item in self.components
        ]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise DOIModelError("OPPORTUNITY_SCOPE_ORDER_INVALID")

    @property
    def line_ids(self) -> frozenset[LineSnapshotId]:
        return frozenset(item.line_snapshot_id for item in self.components)

    def to_dict(self) -> dict[str, object]:
        return {
            "components": [item.to_dict() for item in self.components],
            "schema_version": self.schema_version,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), expected_members=set(self.to_dict()))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIOpportunityScope(<closed>)"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DOIMutualExclusionEvidence:
    evidence_id: EvidenceId
    group_id: EvidenceId
    candidate_ids: tuple[EvidenceId, ...]
    human_fact: StructuredHumanFact
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-mutual-exclusion-evidence/v1"

    def __post_init__(self) -> None:
        if (
            type(self.evidence_id) is not EvidenceId
            or type(self.group_id) is not EvidenceId
            or type(self.candidate_ids) is not tuple
            or any(type(item) is not EvidenceId for item in self.candidate_ids)
            or type(self.human_fact) is not StructuredHumanFact
            or self.human_fact.usage_kind is not HumanFactUsageKind.SCENARIO_GROUPING
            or self.human_fact.result_code is not HumanFactResultCode.SCENARIO_GROUPED
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_MUTUAL_EXCLUSION_EVIDENCE_INVALID")
        candidate_keys = tuple(item.value for item in self.candidate_ids)
        if (
            candidate_keys != tuple(sorted(candidate_keys))
            or len(candidate_keys) < 2
            or len(candidate_keys) != len(set(candidate_keys))
        ):
            raise DOIModelError("DOI_MUTUAL_EXCLUSION_OPTIONS_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_ids": [item.value for item in self.candidate_ids],
            "evidence_id": self.evidence_id.value,
            "group_id": self.group_id.value,
            "human_fact": _binding_json(self.human_fact.hash_binding()),
            "schema_version": self.schema_version,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIMutualExclusionEvidence(<closed>)"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class AlternateCandidate:
    candidate_id: EvidenceId
    opportunity_type: OpportunityType
    ordered_line_id: LineSnapshotId
    quantity: PositiveQuantity
    candidate_sku: SkuId
    observed_availability: AlternateAvailability
    validity: AlternateValidityState
    compatibility_decision: CompatibilityDecision
    relationship_revision_binding: HashBinding | None
    observation_binding: HashBinding | None
    current_observation: bool
    potential_value: Money | None
    unknown_reasons: tuple[ReasonRef, ...] = ()
    mutual_exclusion_group: EvidenceId | None = None
    mutual_exclusion_evidence: DOIMutualExclusionEvidence | None = None
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-alternate-candidate/v1"

    def __post_init__(self) -> None:
        if (
            type(self.candidate_id) is not EvidenceId
            or type(self.opportunity_type) is not OpportunityType
            or self.opportunity_type
            not in {
                OpportunityType.EXACT_SKU_RECHECK,
                OpportunityType.EXACT_MFG_ALTERNATE,
                OpportunityType.MFG_CROSS_REFERENCE,
                OpportunityType.MFG_SUPERSESSION,
                OpportunityType.FUNCTIONAL_ALTERNATE,
            }
            or type(self.ordered_line_id) is not LineSnapshotId
            or type(self.quantity) is not PositiveQuantity
            or type(self.candidate_sku) is not SkuId
            or type(self.observed_availability) is not AlternateAvailability
            or type(self.validity) is not AlternateValidityState
            or type(self.compatibility_decision) is not CompatibilityDecision
            or type(self.current_observation) is not bool
            or (self.potential_value is not None and type(self.potential_value) is not Money)
            or type(self.unknown_reasons) is not tuple
            or any(type(reason) is not ReasonRef for reason in self.unknown_reasons)
            or (
                self.mutual_exclusion_group is not None
                and type(self.mutual_exclusion_group) is not EvidenceId
            )
            or (
                self.mutual_exclusion_evidence is not None
                and type(self.mutual_exclusion_evidence)
                is not DOIMutualExclusionEvidence
            )
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("ALTERNATE_CANDIDATE_INVALID")
        codes = [reason.code for reason in self.unknown_reasons]
        if codes != sorted(codes) or len(codes) != len(set(codes)):
            raise DOIModelError("ALTERNATE_CANDIDATE_REASONS_INVALID")
        grouped = self.mutual_exclusion_group is not None
        if grouped != (self.mutual_exclusion_evidence is not None):
            raise DOIModelError("ALTERNATE_MUTUAL_EXCLUSION_EVIDENCE_REQUIRED")
        if grouped and (
            self.mutual_exclusion_evidence.group_id
            != self.mutual_exclusion_group
            or self.candidate_id
            not in self.mutual_exclusion_evidence.candidate_ids
        ):
            raise DOIModelError("ALTERNATE_MUTUAL_EXCLUSION_EVIDENCE_INVALID")
        exact_sku = self.opportunity_type is OpportunityType.EXACT_SKU_RECHECK
        if exact_sku:
            if self.relationship_revision_binding is not None:
                raise DOIModelError("EXACT_SKU_IS_NOT_RELATIONSHIP")
        elif type(self.relationship_revision_binding) is not HashBinding:
            raise DOIModelError("ALTERNATE_RELATIONSHIP_BINDING_REQUIRED")
        if self.current_observation != (self.observation_binding is not None):
            if self.current_observation or self.observation_binding is None:
                raise DOIModelError("ALTERNATE_OBSERVATION_BINDING_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id.value,
            "candidate_sku": self.candidate_sku.value,
            "compatibility_decision": self.compatibility_decision.value,
            "current_observation": self.current_observation,
            "mutual_exclusion_group": (
                self.mutual_exclusion_group.value
                if self.mutual_exclusion_group is not None
                else None
            ),
            "mutual_exclusion_evidence": (
                _binding_json(self.mutual_exclusion_evidence.hash_binding())
                if self.mutual_exclusion_evidence is not None
                else None
            ),
            "observation_binding": (
                _binding_json(self.observation_binding)
                if self.observation_binding is not None
                else None
            ),
            "observed_availability": self.observed_availability.value,
            "opportunity_type": self.opportunity_type.value,
            "ordered_line_id": self.ordered_line_id.to_json_value(),
            "potential_value": (
                self.potential_value.to_json_value()
                if self.potential_value is not None
                else None
            ),
            "quantity": self.quantity.to_json_value(),
            "relationship_revision_binding": (
                _binding_json(self.relationship_revision_binding)
                if self.relationship_revision_binding is not None
                else None
            ),
            "schema_version": self.schema_version,
            "unknown_reasons": [reason.code for reason in self.unknown_reasons],
            "validity": self.validity.value,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), expected_members=set(self.to_dict()))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "AlternateCandidate(<closed>)"


@dataclass(frozen=True, slots=True, repr=False)
class ScenarioSelection:
    selection_id: EvidenceId
    selected_opportunity_id: EvidenceId
    option_opportunity_ids: tuple[EvidenceId, ...]
    human_fact_binding: HashBinding

    def __post_init__(self) -> None:
        if (
            type(self.selection_id) is not EvidenceId
            or type(self.selected_opportunity_id) is not EvidenceId
            or type(self.option_opportunity_ids) is not tuple
            or any(
                type(opportunity_id) is not EvidenceId
                for opportunity_id in self.option_opportunity_ids
            )
            or type(self.human_fact_binding) is not HashBinding
        ):
            raise DOIModelError("SCENARIO_SELECTION_INVALID")
        option_keys = tuple(item.value for item in self.option_opportunity_ids)
        if (
            option_keys != tuple(sorted(option_keys))
            or len(option_keys) < 2
            or len(option_keys) != len(set(option_keys))
            or self.selected_opportunity_id not in self.option_opportunity_ids
        ):
            raise DOIModelError("SCENARIO_SELECTION_OPTIONS_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "human_fact_binding": _binding_json(self.human_fact_binding),
            "option_opportunity_ids": [
                item.value for item in self.option_opportunity_ids
            ],
            "selected_opportunity_id": self.selected_opportunity_id.value,
            "selection_id": self.selection_id.value,
        }

    def __repr__(self) -> str:
        return "ScenarioSelection(<closed>)"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DOIOpportunity:
    opportunity_id: EvidenceId
    opportunity_type: OpportunityType
    scope: DOIOpportunityScope
    potential_value_state: ValueAvailabilityState
    potential_value: Money | None
    relationship_revision_binding: HashBinding | None = None
    alternate_observation_binding: HashBinding | None = None
    human_fact_binding: HashBinding | None = None
    mutual_exclusion_group: EvidenceId | None = None
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-opportunity/v1"

    def __post_init__(self) -> None:
        if (
            type(self.opportunity_id) is not EvidenceId
            or type(self.opportunity_type) is not OpportunityType
            or type(self.scope) is not DOIOpportunityScope
            or type(self.potential_value_state) is not ValueAvailabilityState
            or (
                self.mutual_exclusion_group is not None
                and type(self.mutual_exclusion_group) is not EvidenceId
            )
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_OPPORTUNITY_INVALID")
        available = self.potential_value_state is ValueAvailabilityState.AVAILABLE
        if available != (type(self.potential_value) is Money):
            raise DOIModelError("DOI_OPPORTUNITY_VALUE_PARTITION_INVALID")
        for binding in (
            self.relationship_revision_binding,
            self.alternate_observation_binding,
            self.human_fact_binding,
        ):
            if binding is not None and type(binding) is not HashBinding:
                raise DOIModelError("DOI_OPPORTUNITY_BINDING_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "alternate_observation_binding": (
                _binding_json(self.alternate_observation_binding)
                if self.alternate_observation_binding is not None
                else None
            ),
            "human_fact_binding": (
                _binding_json(self.human_fact_binding)
                if self.human_fact_binding is not None
                else None
            ),
            "mutual_exclusion_group": (
                self.mutual_exclusion_group.value
                if self.mutual_exclusion_group is not None
                else None
            ),
            "opportunity_id": self.opportunity_id.value,
            "opportunity_type": self.opportunity_type.value,
            "potential_value": (
                self.potential_value.to_json_value()
                if self.potential_value is not None
                else None
            ),
            "potential_value_state": self.potential_value_state.value,
            "relationship_revision_binding": (
                _binding_json(self.relationship_revision_binding)
                if self.relationship_revision_binding is not None
                else None
            ),
            "schema_version": self.schema_version,
            "scope": _binding_json(self.scope.hash_binding()),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), expected_members=set(self.to_dict()))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIOpportunity(<closed>)"


@dataclass(frozen=True, slots=True, repr=False)
class ClosureProposal:
    reason: TerminalClosureReason
    lifecycle_state: CaseLifecycleState

    def __post_init__(self) -> None:
        if (
            type(self.reason) is not TerminalClosureReason
            or type(self.lifecycle_state) is not CaseLifecycleState
            or self.lifecycle_state is CaseLifecycleState.ACTIVE
        ):
            raise DOIModelError("CLOSURE_PROPOSAL_INVALID")
        hard = self.reason in {TerminalClosureReason.SHIPPED, TerminalClosureReason.CANCELED}
        if hard != (self.lifecycle_state is CaseLifecycleState.CLOSED_HARD):
            raise DOIModelError("CLOSURE_PROPOSAL_CLASS_INVALID")

    def to_dict(self) -> dict[str, str]:
        return {"lifecycle_state": self.lifecycle_state.value, "reason": self.reason.value}


@dataclass(frozen=True, slots=True, repr=False)
class ReasonEmissionRoute:
    reason: ReasonRef
    owning_transition: TransitionRef | None
    rule_or_boundary_only: bool
    effective_overlay: bool

    def __post_init__(self) -> None:
        if (
            type(self.reason) is not ReasonRef
            or (
                self.owning_transition is not None
                and type(self.owning_transition) is not TransitionRef
            )
            or type(self.rule_or_boundary_only) is not bool
            or type(self.effective_overlay) is not bool
            or self.rule_or_boundary_only != (self.owning_transition is None)
        ):
            raise DOIModelError("REASON_EMISSION_ROUTE_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "effective_overlay": self.effective_overlay,
            "owning_transition": (
                self.owning_transition.transition_id
                if self.owning_transition is not None
                else None
            ),
            "reason": self.reason.code,
            "rule_or_boundary_only": self.rule_or_boundary_only,
        }


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DOIEvaluationInput:
    evaluation_id: EvaluationId
    snapshot: DOIOrderSnapshot
    evaluated_at: CanonicalTimestamp
    alternate_research_state: AlternateResearchState = AlternateResearchState.NOT_STARTED
    alternate_candidates: tuple[AlternateCandidate, ...] = ()
    scenario_selection: ScenarioSelection | None = None
    human_facts: tuple[StructuredHumanFact, ...] = ()
    dedupe_history: DOIDedupeHistory | None = None
    dedupe_verification: DedupeVerificationFact | None = None
    required_rule_pack: VersionBinding = field(
        default_factory=lambda: VersionBinding(
            "rule_pack",
            DOI_RULE_PACK_VERSION,
        )
    )
    available_rule_pack_binding: HashBinding | None = field(
        default_factory=rule_pack_hash_binding
    )
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-evaluation-input/v1"

    def __post_init__(self) -> None:
        if (
            type(self.evaluation_id) is not EvaluationId
            or type(self.snapshot) is not DOIOrderSnapshot
            or type(self.evaluated_at) is not CanonicalTimestamp
            or type(self.alternate_research_state) is not AlternateResearchState
            or type(self.alternate_candidates) is not tuple
            or any(type(item) is not AlternateCandidate for item in self.alternate_candidates)
            or (
                self.scenario_selection is not None
                and type(self.scenario_selection) is not ScenarioSelection
            )
            or type(self.human_facts) is not tuple
            or any(type(item) is not StructuredHumanFact for item in self.human_facts)
            or (
                self.dedupe_history is not None
                and type(self.dedupe_history) is not DOIDedupeHistory
            )
            or (
                self.dedupe_verification is not None
                and type(self.dedupe_verification) is not DedupeVerificationFact
            )
            or type(self.required_rule_pack) is not VersionBinding
            or self.required_rule_pack.component != "rule_pack"
            or (
                self.available_rule_pack_binding is not None
                and (
                    type(self.available_rule_pack_binding) is not HashBinding
                    or self.available_rule_pack_binding.domain
                    != DOI_RULE_PACK_HASH_DOMAIN
                )
            )
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_EVALUATION_INPUT_INVALID")
        keys = [item.candidate_id.value for item in self.alternate_candidates]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise DOIModelError("DOI_ALTERNATE_CANDIDATE_ORDER_INVALID")
        human_keys = [item.fact_id.value for item in self.human_facts]
        if human_keys != sorted(human_keys) or len(human_keys) != len(set(human_keys)):
            raise DOIModelError("DOI_HUMAN_FACT_ORDER_INVALID")
        if any(
            item.order_id != self.snapshot.order_id
            or item.evaluation_id != self.evaluation_id
            for item in self.human_facts
        ):
            raise DOIModelError("DOI_HUMAN_FACT_SCOPE_INVALID")
        if self.dedupe_verification is not None:
            verification = self.dedupe_verification
            matching_approvals = tuple(
                fact
                for fact in self.human_facts
                if fact.usage_kind is HumanFactUsageKind.DEDUPE_DECISION
                and fact.result_code is HumanFactResultCode.APPROVED
                and fact.hash_binding()
                == verification.approved_human_fact_binding
                and fact.occurred_at == verification.approved_at
            )
            evaluated_instant = (
                self.evaluated_at.epoch_seconds,
                self.evaluated_at.nanosecond,
            )
            verified_instant = (
                verification.verified_snapshot.source_observed_at.epoch_seconds,
                verification.verified_snapshot.source_observed_at.nanosecond,
            )
            if (
                type(self.dedupe_history) is not DOIDedupeHistory
                or self.dedupe_history.projection.order_id != self.snapshot.order_id
                or self.dedupe_history.projection.state
                is not DedupeState.APPROVED_AWAITING_VERIFICATION
                or self.dedupe_history.projection.source_finding_binding
                != verification.prior_snapshot.dedupe_finding.hash_binding()
                or self.dedupe_history.projection.human_fact_binding
                != verification.approved_human_fact_binding
                or self.dedupe_history.projection.hash_binding()
                != verification.prior_projection_binding
                or verification.order_id != self.snapshot.order_id
                or verification.verified_snapshot.hash_binding()
                != self.snapshot.hash_binding()
                or len(matching_approvals) != 1
                or verified_instant > evaluated_instant
            ):
                raise DOIModelError("DOI_DEDUPE_VERIFICATION_BINDING_INVALID")
        if self.scenario_selection is not None:
            matching_selection_facts = tuple(
                item
                for item in self.human_facts
                if item.usage_kind is HumanFactUsageKind.SCENARIO_SELECTION
                and item.result_code is HumanFactResultCode.SCENARIO_SELECTED
                and item.hash_binding()
                == self.scenario_selection.human_fact_binding
            )
            if len(matching_selection_facts) != 1:
                raise DOIModelError("DOI_SCENARIO_SELECTION_FACT_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "available_rule_pack_binding": (
                _binding_json(self.available_rule_pack_binding)
                if self.available_rule_pack_binding is not None
                else None
            ),
            "alternate_research_state": self.alternate_research_state.value,
            "alternate_candidates": [
                _binding_json(candidate.hash_binding())
                for candidate in self.alternate_candidates
            ],
            "dedupe_verification": (
                _binding_json(self.dedupe_verification.hash_binding())
                if self.dedupe_verification is not None
                else None
            ),
            "dedupe_history_projection": (
                _binding_json(self.dedupe_history.projection.hash_binding())
                if self.dedupe_history is not None
                else None
            ),
            "evaluated_at": self.evaluated_at.value,
            "evaluation_id": self.evaluation_id.value,
            "human_facts": [
                _binding_json(item.hash_binding()) for item in self.human_facts
            ],
            "required_rule_pack": self.required_rule_pack.to_dict(),
            "scenario_selection": (
                self.scenario_selection.to_dict()
                if self.scenario_selection is not None
                else None
            ),
            "schema_version": self.schema_version,
            "snapshot": _binding_json(self.snapshot.hash_binding()),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), expected_members=set(self.to_dict()))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIEvaluationInput(<closed>)"


@dataclass(frozen=True, slots=True, repr=False)
class DOIExplanation:
    supplied_facts: tuple[str, ...]
    normalized_facts: tuple[str, ...]
    unavailable_facts: tuple[str, ...]
    rules_evaluated: tuple[str, ...]
    rules_fired: tuple[str, ...]
    precedence_decision: str
    reason_codes: tuple[str, ...]
    reason_ownership: tuple[str, ...]
    opportunity_ids: tuple[str, ...]
    opportunity_scopes: tuple[str, ...]
    opportunity_values: tuple[str, ...]
    handling_flags: tuple[str, ...]
    human_review_requirements: tuple[str, ...]
    closure_state: str
    rule_pack_binding: HashBinding
    reason_registry_version: str
    transition_registry_version: str
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-evaluation-explanation/v1"

    def __post_init__(self) -> None:
        for values in (
            self.supplied_facts,
            self.normalized_facts,
            self.unavailable_facts,
            self.rules_evaluated,
            self.rules_fired,
            self.reason_codes,
            self.reason_ownership,
            self.opportunity_ids,
            self.opportunity_scopes,
            self.opportunity_values,
            self.handling_flags,
            self.human_review_requirements,
        ):
            if type(values) is not tuple or any(type(value) is not str for value in values):
                raise DOIModelError("DOI_EXPLANATION_INVALID")
            if list(values) != sorted(values) or len(values) != len(set(values)):
                raise DOIModelError("DOI_EXPLANATION_ORDER_INVALID")
        if (
            type(self.precedence_decision) is not str
            or _UPPER_TOKEN.fullmatch(self.precedence_decision) is None
            or type(self.closure_state) is not str
            or _UPPER_TOKEN.fullmatch(self.closure_state) is None
            or not set(self.rules_fired).issubset(self.rules_evaluated)
            or type(self.rule_pack_binding) is not HashBinding
            or self.rule_pack_binding.domain != DOI_RULE_PACK_HASH_DOMAIN
            or type(self.reason_registry_version) is not str
            or not self.reason_registry_version
            or type(self.transition_registry_version) is not str
            or not self.transition_registry_version
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_EXPLANATION_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "closure_state": self.closure_state,
            "handling_flags": list(self.handling_flags),
            "human_review_requirements": list(
                self.human_review_requirements
            ),
            "normalized_facts": list(self.normalized_facts),
            "opportunity_ids": list(self.opportunity_ids),
            "opportunity_scopes": list(self.opportunity_scopes),
            "opportunity_values": list(self.opportunity_values),
            "precedence_decision": self.precedence_decision,
            "reason_codes": list(self.reason_codes),
            "reason_ownership": list(self.reason_ownership),
            "reason_registry_version": self.reason_registry_version,
            "rule_pack_binding": _binding_json(self.rule_pack_binding),
            "rules_evaluated": list(self.rules_evaluated),
            "rules_fired": list(self.rules_fired),
            "schema_version": self.schema_version,
            "supplied_facts": list(self.supplied_facts),
            "transition_registry_version": self.transition_registry_version,
            "unavailable_facts": list(self.unavailable_facts),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), expected_members=set(self.to_dict()))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIExplanation(<closed>)"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DOIEvaluation:
    evaluation_id: EvaluationId
    snapshot_id: DoiSnapshotId
    run_id: DoiRunId
    order_id: DoiOrderId
    state: DOIState
    transition: TransitionRef
    append_transition: TransitionRef
    append_transitions: tuple[TransitionRef, ...]
    reasons: ReasonSet
    reason_routes: tuple[ReasonEmissionRoute, ...]
    opportunities: tuple[DOIOpportunity, ...]
    handling_flags: tuple[HandlingFlag, ...]
    human_review_requirements: tuple[HumanReviewKind, ...]
    closure_proposal: ClosureProposal | None
    aggregate_potential_state: ValueAvailabilityState
    aggregate_potential: Money | None
    scenario_selection_state: ScenarioSelectionState
    explanation: DOIExplanation
    input_binding: HashBinding
    output_binding: HashBinding
    rule_pack: VersionBinding
    rule_pack_binding: HashBinding
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-evaluation-record/v1"
    OUTPUT_DOMAIN: ClassVar[str] = "doi-evaluation-output/v1"

    def __post_init__(self) -> None:
        if (
            type(self.evaluation_id) is not EvaluationId
            or type(self.snapshot_id) is not DoiSnapshotId
            or type(self.run_id) is not DoiRunId
            or type(self.order_id) is not DoiOrderId
            or type(self.state) is not DOIState
            or type(self.transition) is not TransitionRef
            or type(self.append_transition) is not TransitionRef
            or self.append_transition.transition_id != "TR-027"
            or type(self.append_transitions) is not tuple
            or any(
                type(item) is not TransitionRef for item in self.append_transitions
            )
            or self.append_transition not in self.append_transitions
            or type(self.reasons) is not ReasonSet
            or type(self.reason_routes) is not tuple
            or any(type(route) is not ReasonEmissionRoute for route in self.reason_routes)
            or type(self.opportunities) is not tuple
            or any(type(item) is not DOIOpportunity for item in self.opportunities)
            or type(self.closure_proposal) not in {ClosureProposal, type(None)}
            or type(self.aggregate_potential_state) is not ValueAvailabilityState
            or type(self.scenario_selection_state) is not ScenarioSelectionState
            or type(self.explanation) is not DOIExplanation
            or type(self.input_binding) is not HashBinding
            or self.input_binding.domain != DOIEvaluationInput.HASH_DOMAIN
            or type(self.output_binding) is not HashBinding
            or self.output_binding.domain != self.OUTPUT_DOMAIN
            or type(self.rule_pack) is not VersionBinding
            or self.rule_pack.component != "rule_pack"
            or self.rule_pack.version != DOI_RULE_PACK_VERSION
            or type(self.rule_pack_binding) is not HashBinding
            or self.rule_pack_binding != rule_pack_hash_binding()
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_EVALUATION_INVALID")
        append_ids = tuple(item.transition_id for item in self.append_transitions)
        if append_ids != tuple(sorted(set(append_ids))):
            raise DOIModelError("DOI_APPEND_TRANSITION_ORDER_INVALID")
        _require_sorted_unique_tokens(self.handling_flags, code="HANDLING_FLAGS_INVALID")
        _require_sorted_unique_tokens(
            self.human_review_requirements,
            code="HUMAN_REVIEW_REQUIREMENTS_INVALID",
        )
        opportunity_ids = [item.opportunity_id.value for item in self.opportunities]
        if opportunity_ids != sorted(opportunity_ids) or len(opportunity_ids) != len(
            set(opportunity_ids)
        ):
            raise DOIModelError("DOI_OPPORTUNITY_ORDER_INVALID")
        reason_codes = [reason.code for reason in self.reasons.reasons]
        route_codes = [route.reason.code for route in self.reason_routes]
        if route_codes != reason_codes:
            raise DOIModelError("DOI_REASON_ROUTE_MISMATCH")
        executed_routes = {self.transition, *self.append_transitions}
        if any(
            route.owning_transition is not None
            and route.owning_transition not in executed_routes
            for route in self.reason_routes
        ):
            raise DOIModelError("DOI_REASON_ROUTE_NOT_EXECUTED")
        has_value = type(self.aggregate_potential) is Money
        if (self.aggregate_potential_state is ValueAvailabilityState.AVAILABLE) != has_value:
            raise DOIModelError("DOI_AGGREGATE_VALUE_PARTITION_INVALID")
        if self.state is DOIState.DOI_OPPORTUNITY and not self.opportunities:
            raise DOIModelError("DOI_OPPORTUNITY_STATE_WITHOUT_OPPORTUNITY")
        if self.state is not DOIState.DOI_OPPORTUNITY and self.opportunities:
            raise DOIModelError("DOI_NONOPPORTUNITY_STATE_WITH_OPPORTUNITY")
        if (self.closure_proposal is not None) != (
            self.state is DOIState.DOI_EXCLUDED
            and self.transition.transition_id in {"TR-029", "TR-030"}
        ):
            raise DOIModelError("DOI_CLOSURE_PARTITION_INVALID")
        expected_output = domain_hash(
            self.OUTPUT_DOMAIN,
            canonical_json_bytes(
                self.output_dict(),
                expected_members=set(self.output_dict()),
            ),
        )
        if self.output_binding != expected_output:
            raise DOIModelError("DOI_EVALUATION_OUTPUT_HASH_MISMATCH")

    def output_dict(self) -> dict[str, object]:
        return {
            "aggregate_potential": (
                self.aggregate_potential.to_json_value()
                if self.aggregate_potential is not None
                else None
            ),
            "aggregate_potential_state": self.aggregate_potential_state.value,
            "append_transitions": [
                item.transition_id for item in self.append_transitions
            ],
            "closure_proposal": (
                self.closure_proposal.to_dict()
                if self.closure_proposal is not None
                else None
            ),
            "explanation": _binding_json(self.explanation.hash_binding()),
            "handling_flags": [item.value for item in self.handling_flags],
            "human_review_requirements": [
                item.value for item in self.human_review_requirements
            ],
            "opportunities": [
                _binding_json(item.hash_binding()) for item in self.opportunities
            ],
            "reason_routes": [route.to_dict() for route in self.reason_routes],
            "reasons": self.reasons.to_json_value(),
            "scenario_selection_state": self.scenario_selection_state.value,
            "state": self.state.value,
            "transition": self.transition.transition_id,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "append_transition": self.append_transition.transition_id,
            "append_transitions": [
                item.transition_id for item in self.append_transitions
            ],
            "evaluation_id": self.evaluation_id.value,
            "input_binding": _binding_json(self.input_binding),
            "order_id": self.order_id.to_json_value(),
            "output": self.output_dict(),
            "output_binding": _binding_json(self.output_binding),
            "rule_pack": self.rule_pack.to_dict(),
            "rule_pack_binding": _binding_json(self.rule_pack_binding),
            "run_id": self.run_id.to_json_value(),
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id.to_json_value(),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), expected_members=set(self.to_dict()))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIEvaluation(<closed>)"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DOIOrderCase:
    case_id: EvidenceId
    order_id: DoiOrderId
    lifecycle_state: CaseLifecycleState
    current_snapshot_id: DoiSnapshotId | None
    current_evaluation_id: EvaluationId | None
    terminal_closure_reason: TerminalClosureReason | None
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.case_id) is not EvidenceId
            or type(self.order_id) is not DoiOrderId
            or type(self.lifecycle_state) is not CaseLifecycleState
            or (
                self.current_snapshot_id is not None
                and type(self.current_snapshot_id) is not DoiSnapshotId
            )
            or (
                self.current_evaluation_id is not None
                and type(self.current_evaluation_id) is not EvaluationId
            )
            or (
                self.terminal_closure_reason is not None
                and type(self.terminal_closure_reason) is not TerminalClosureReason
            )
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_CASE_INVALID")
        active = self.lifecycle_state is CaseLifecycleState.ACTIVE
        if active != (self.terminal_closure_reason is None):
            raise DOIModelError("DOI_CASE_CLOSURE_PARTITION_INVALID")


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DOICaseAdmissionProof:
    proof_id: EvidenceId
    case_id: EvidenceId
    order_id: DoiOrderId
    source: SourceRef
    completeness_proof: WholeOrderCompletenessProof
    admitted_at: CanonicalTimestamp
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-case-admission-proof/v1"

    def __post_init__(self) -> None:
        valid = (
            type(self.proof_id) is EvidenceId
            and type(self.case_id) is EvidenceId
            and type(self.order_id) is DoiOrderId
            and type(self.source) is SourceRef
            and self.source.source_kind is SourceKind.SYNTHETIC_ORDER_FIXTURE
            and self.source.object_namespace is SourceObjectNamespace.SYNTHETIC_ORDER
            and self.source.object_id == self.order_id.value
            and type(self.completeness_proof) is WholeOrderCompletenessProof
            and self.completeness_proof.requested_order_id == self.order_id.value
            and self.completeness_proof.observed_order_id == self.order_id.value
            and self.source in self.completeness_proof.source_refs
            and type(self.admitted_at) is CanonicalTimestamp
            and self.schema_version == DOI_MODEL_SCHEMA_VERSION
        )
        if not valid:
            raise DOIModelError("DOI_CASE_ADMISSION_PROOF_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "admitted_at": self.admitted_at.value,
            "case_id": self.case_id.value,
            "completeness_proof": _binding_json(
                self.completeness_proof.hash_binding()
            ),
            "order_id": self.order_id.to_json_value(),
            "proof_id": self.proof_id.value,
            "schema_version": self.schema_version,
            "source": _binding_json(self.source.hash_binding()),
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOICaseAdmissionProof(<closed>)"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DOICaseSourceBinding:
    binding_id: EvidenceId
    case_id: EvidenceId
    order_id: DoiOrderId
    source: SourceRef
    admission_proof: DOICaseAdmissionProof
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-case-source-binding/v1"

    def __post_init__(self) -> None:
        if (
            type(self.binding_id) is not EvidenceId
            or type(self.case_id) is not EvidenceId
            or type(self.order_id) is not DoiOrderId
            or type(self.source) is not SourceRef
            or type(self.admission_proof) is not DOICaseAdmissionProof
            or self.admission_proof.case_id != self.case_id
            or self.admission_proof.order_id != self.order_id
            or self.admission_proof.source != self.source
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_CASE_SOURCE_BINDING_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "admission_proof": _binding_json(self.admission_proof.hash_binding()),
            "binding_id": self.binding_id.value,
            "case_id": self.case_id.value,
            "order_id": self.order_id.to_json_value(),
            "schema_version": self.schema_version,
            "source": _binding_json(self.source.hash_binding()),
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOICaseSourceBinding(<closed>)"


_ACTION_CONTEXT_OPENING_AUTHORITY_TOKEN = object()


def _action_context_intervention_type(
    opportunity_type: OpportunityType,
) -> InterventionType:
    if opportunity_type is OpportunityType.FULFILLMENT_SPLIT:
        return InterventionType.FULFILLMENT_SPLIT
    if opportunity_type is OpportunityType.DS_SEPARATION:
        return InterventionType.DS_SEPARATION
    if opportunity_type in {
        OpportunityType.EXACT_MFG_ALTERNATE,
        OpportunityType.MFG_CROSS_REFERENCE,
        OpportunityType.MFG_SUPERSESSION,
        OpportunityType.FUNCTIONAL_ALTERNATE,
    }:
        return InterventionType.PRODUCT_SUBSTITUTION
    raise DOIModelError("DOI_ACTION_CONTEXT_OPPORTUNITY_INVALID")


def _validate_action_context_kind(
    *,
    context_kind: ActionContextKind,
    opportunity: DOIOpportunity,
    evaluation: DOIEvaluation,
) -> InterventionType:
    opportunity_type = opportunity.opportunity_type
    substitution_types = {
        OpportunityType.EXACT_MFG_ALTERNATE,
        OpportunityType.MFG_CROSS_REFERENCE,
        OpportunityType.MFG_SUPERSESSION,
        OpportunityType.FUNCTIONAL_ALTERNATE,
    }
    legal = {
        ActionContextKind.SUBSTITUTION: substitution_types,
        ActionContextKind.CUSTOMER_CONTACT: {
            OpportunityType.FULFILLMENT_SPLIT,
            *substitution_types,
        },
        ActionContextKind.FULFILLMENT_SPLIT_REVIEW: {
            OpportunityType.FULFILLMENT_SPLIT
        },
        ActionContextKind.DS_SEPARATION_REVIEW: {OpportunityType.DS_SEPARATION},
        ActionContextKind.RESULTING_ORDER_LINK_REVIEW: {
            OpportunityType.FULFILLMENT_SPLIT
        },
        ActionContextKind.INTERVENTION_VERIFICATION: {
            OpportunityType.FULFILLMENT_SPLIT,
            OpportunityType.DS_SEPARATION,
            *substitution_types,
        },
    }
    if opportunity_type not in legal[context_kind]:
        raise DOIModelError("DOI_ACTION_CONTEXT_KIND_INVALID")
    if context_kind is ActionContextKind.CUSTOMER_CONTACT:
        if opportunity_type is OpportunityType.FULFILLMENT_SPLIT:
            gate_present = (
                HandlingFlag.CUSTOMER_CONTACT_BEFORE_SPLIT
                in evaluation.handling_flags
                or HumanReviewKind.CUSTOMER_CONTACT
                in evaluation.human_review_requirements
            )
        else:
            gate_present = (
                HandlingFlag.CUSTOMER_APPROVAL_REQUIRED in evaluation.handling_flags
                or HumanReviewKind.CUSTOMER_APPROVAL
                in evaluation.human_review_requirements
            )
        if not gate_present:
            raise DOIModelError("DOI_ACTION_CONTEXT_GATE_INVALID")
    return _action_context_intervention_type(opportunity_type)


@dataclass(frozen=True, slots=True, init=False, repr=False)
class ActionContextOpeningAuthorization:
    """Sealed proof that one admitted case owner authorized one exact attempt."""

    authorization_id: EvidenceId
    attempt_intent_id: InteractionId
    case_id: EvidenceId
    case_source_binding: HashBinding
    order_id: DoiOrderId
    snapshot_id: DoiSnapshotId
    evaluation_id: EvaluationId
    evaluation_binding: HashBinding
    opportunity_id: EvidenceId
    opportunity_binding: HashBinding
    context_kind: ActionContextKind
    intervention_type: InterventionType
    actor: RepId
    granted_at: CanonicalTimestamp
    source: SourceRef
    request_canonical_bytes: bytes = field(repr=False)
    request_binding: HashBinding
    _line_scope: frozenset[LineSnapshotId] = field(repr=False)
    _relationship_revision_binding: HashBinding | None = field(repr=False)
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-action-context-opening-authorization/v1"
    REQUEST_SCHEMA_VERSION: ClassVar[str] = "doi-action-context-request/v1"
    REQUEST_HASH_DOMAIN: ClassVar[str] = "doi-action-context-request/v1"

    def __new__(cls) -> ActionContextOpeningAuthorization:
        raise DOIModelError("DOI_ACTION_CONTEXT_OPENING_AUTHORITY_FACTORY_REQUIRED")

    @classmethod
    def _verified(
        cls,
        *,
        authorization_id: EvidenceId,
        attempt_intent_id: InteractionId,
        case: DOIOrderCase,
        case_source_binding: DOICaseSourceBinding,
        evaluation: DOIEvaluation,
        opportunity: DOIOpportunity,
        context_kind: ActionContextKind,
        actor: RepId,
        granted_at: CanonicalTimestamp,
        source: SourceRef,
        factory_capability: object,
    ) -> ActionContextOpeningAuthorization:
        if factory_capability is not _ACTION_CONTEXT_OPENING_AUTHORITY_TOKEN:
            raise DOIModelError(
                "DOI_ACTION_CONTEXT_OPENING_AUTHORITY_FACTORY_REQUIRED"
            )
        if (
            type(case) is not DOIOrderCase
            or case.lifecycle_state is not CaseLifecycleState.ACTIVE
            or type(case_source_binding) is not DOICaseSourceBinding
            or case_source_binding.case_id != case.case_id
            or case_source_binding.order_id != case.order_id
            or type(evaluation) is not DOIEvaluation
            or evaluation.order_id != case.order_id
            or case.current_snapshot_id != evaluation.snapshot_id
            or case.current_evaluation_id != evaluation.evaluation_id
            or evaluation.state is not DOIState.DOI_OPPORTUNITY
            or type(opportunity) is not DOIOpportunity
            or not any(
                retained == opportunity
                and retained.hash_binding() == opportunity.hash_binding()
                for retained in evaluation.opportunities
            )
            or type(context_kind) is not ActionContextKind
            or type(actor) is not RepId
            or type(granted_at) is not CanonicalTimestamp
            or type(source) is not SourceRef
            or source.source_kind is not SourceKind.SYNTHETIC_INTERACTION_FIXTURE
            or source.object_namespace
            is not SourceObjectNamespace.SYNTHETIC_INTERACTION
            or source.object_id != attempt_intent_id
        ):
            raise DOIModelError("DOI_ACTION_CONTEXT_OPENING_OWNER_INVALID")
        intervention_type = _validate_action_context_kind(
            context_kind=context_kind,
            opportunity=opportunity,
            evaluation=evaluation,
        )
        request = {
            "action_context_request_schema_version": cls.REQUEST_SCHEMA_VERSION,
            "attempt_intent_id": attempt_intent_id.value,
            "case_id": case.case_id.value,
            "context_kind": context_kind.value,
            "created_by_actor_id": actor.value,
            "evaluation_id": evaluation.evaluation_id.value,
            "opportunity_id": opportunity.opportunity_id.value,
        }
        request_bytes = canonical_json_bytes(request, expected_members=set(request))
        request_binding = domain_hash(cls.REQUEST_HASH_DOMAIN, request_bytes)
        instance = object.__new__(cls)
        object.__setattr__(instance, "authorization_id", authorization_id)
        object.__setattr__(instance, "attempt_intent_id", attempt_intent_id)
        object.__setattr__(instance, "case_id", case.case_id)
        object.__setattr__(
            instance,
            "case_source_binding",
            case_source_binding.hash_binding(),
        )
        object.__setattr__(instance, "order_id", case.order_id)
        object.__setattr__(instance, "snapshot_id", evaluation.snapshot_id)
        object.__setattr__(instance, "evaluation_id", evaluation.evaluation_id)
        object.__setattr__(instance, "evaluation_binding", evaluation.hash_binding())
        object.__setattr__(instance, "opportunity_id", opportunity.opportunity_id)
        object.__setattr__(instance, "opportunity_binding", opportunity.hash_binding())
        object.__setattr__(instance, "context_kind", context_kind)
        object.__setattr__(instance, "intervention_type", intervention_type)
        object.__setattr__(instance, "actor", actor)
        object.__setattr__(instance, "granted_at", granted_at)
        object.__setattr__(instance, "source", source)
        object.__setattr__(instance, "request_canonical_bytes", request_bytes)
        object.__setattr__(instance, "request_binding", request_binding)
        object.__setattr__(instance, "_line_scope", opportunity.scope.line_ids)
        object.__setattr__(
            instance,
            "_relationship_revision_binding",
            opportunity.relationship_revision_binding,
        )
        object.__setattr__(instance, "schema_version", DOI_MODEL_SCHEMA_VERSION)
        instance.__post_init__()
        return instance

    def __post_init__(self) -> None:
        if (
            type(self.authorization_id) is not EvidenceId
            or type(self.attempt_intent_id) is not InteractionId
            or type(self.case_id) is not EvidenceId
            or type(self.case_source_binding) is not HashBinding
            or self.case_source_binding.domain != DOICaseSourceBinding.HASH_DOMAIN
            or type(self.order_id) is not DoiOrderId
            or type(self.snapshot_id) is not DoiSnapshotId
            or type(self.evaluation_id) is not EvaluationId
            or type(self.evaluation_binding) is not HashBinding
            or self.evaluation_binding.domain != DOIEvaluation.HASH_DOMAIN
            or type(self.opportunity_id) is not EvidenceId
            or type(self.opportunity_binding) is not HashBinding
            or self.opportunity_binding.domain != DOIOpportunity.HASH_DOMAIN
            or type(self.context_kind) is not ActionContextKind
            or type(self.intervention_type) is not InterventionType
            or type(self.actor) is not RepId
            or type(self.granted_at) is not CanonicalTimestamp
            or type(self.source) is not SourceRef
            or self.source.source_kind
            is not SourceKind.SYNTHETIC_INTERACTION_FIXTURE
            or self.source.object_namespace
            is not SourceObjectNamespace.SYNTHETIC_INTERACTION
            or self.source.object_id != self.attempt_intent_id
            or type(self.request_canonical_bytes) is not bytes
            or type(self.request_binding) is not HashBinding
            or self.request_binding.domain != self.REQUEST_HASH_DOMAIN
            or self.request_binding.canonical_bytes != self.request_canonical_bytes
            or type(self._line_scope) is not frozenset
            or not self._line_scope
            or any(type(item) is not LineSnapshotId for item in self._line_scope)
            or (
                self._relationship_revision_binding is not None
                and (
                    type(self._relationship_revision_binding) is not HashBinding
                    or self._relationship_revision_binding.domain
                    != "doi-alternate-relationship-revision/v1"
                )
            )
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_ACTION_CONTEXT_OPENING_AUTHORITY_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "actor": self.actor.value,
            "attempt_intent_id": self.attempt_intent_id.value,
            "authorization_id": self.authorization_id.value,
            "case_id": self.case_id.value,
            "case_source_binding": _binding_json(self.case_source_binding),
            "context_kind": self.context_kind.value,
            "evaluation_binding": _binding_json(self.evaluation_binding),
            "evaluation_id": self.evaluation_id.value,
            "granted_at": self.granted_at.value,
            "intervention_type": self.intervention_type.value,
            "line_scope": [
                item.to_json_value()
                for item in sorted(
                    self._line_scope,
                    key=lambda line: line.to_json_value(),
                )
            ],
            "opportunity_binding": _binding_json(self.opportunity_binding),
            "opportunity_id": self.opportunity_id.value,
            "order_id": self.order_id.to_json_value(),
            "request_canonical_bytes": self.request_canonical_bytes.decode("utf-8"),
            "request_binding": _binding_json(self.request_binding),
            "relationship_revision_binding": (
                _binding_json(self._relationship_revision_binding)
                if self._relationship_revision_binding is not None
                else None
            ),
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id.to_json_value(),
            "source": _binding_json(self.source.hash_binding()),
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "ActionContextOpeningAuthorization(<closed>)"


def verify_action_context_opening_authority(
    *,
    authorization_id: EvidenceId,
    attempt_intent_id: InteractionId,
    case: DOIOrderCase,
    case_source_binding: DOICaseSourceBinding,
    evaluation: DOIEvaluation,
    opportunity: DOIOpportunity,
    context_kind: ActionContextKind,
    actor: RepId,
    granted_at: CanonicalTimestamp,
    authority_source: SourceRef,
) -> ActionContextOpeningAuthorization:
    """Issue one sealed opening authorization from exact retained typed owners."""

    return ActionContextOpeningAuthorization._verified(
        authorization_id=authorization_id,
        attempt_intent_id=attempt_intent_id,
        case=case,
        case_source_binding=case_source_binding,
        evaluation=evaluation,
        opportunity=opportunity,
        context_kind=context_kind,
        actor=actor,
        granted_at=granted_at,
        source=authority_source,
        factory_capability=_ACTION_CONTEXT_OPENING_AUTHORITY_TOKEN,
    )


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DOIOccurrenceGuard:
    guard_id: EvidenceId
    owner_id: EvidenceId
    occurrence_id: InteractionId
    source: SourceRef
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-occurrence-guard/v1"

    def __post_init__(self) -> None:
        if (
            type(self.guard_id) is not EvidenceId
            or type(self.owner_id) is not EvidenceId
            or type(self.occurrence_id) is not InteractionId
            or type(self.source) is not SourceRef
            or self.source.source_kind is not SourceKind.SYNTHETIC_INTERACTION_FIXTURE
            or self.source.object_namespace
            is not SourceObjectNamespace.SYNTHETIC_INTERACTION
            or self.source.object_id != self.occurrence_id
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_OCCURRENCE_GUARD_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "guard_id": self.guard_id.value,
            "occurrence_id": self.occurrence_id.value,
            "owner_id": self.owner_id.value,
            "schema_version": self.schema_version,
            "source": _binding_json(self.source.hash_binding()),
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIOccurrenceGuard(<closed>)"


def _validate_event_position(
    sequence: object,
    predecessor: object,
    *,
    event_domain: str,
    code: str,
) -> None:
    if type(sequence) is not int or sequence < 1:
        raise DOIModelError(code)
    if sequence == 1:
        if predecessor is not None:
            raise DOIModelError(code)
    elif type(predecessor) is not HashBinding or predecessor.domain != event_domain:
        raise DOIModelError(code)


def _require_event_append(
    *,
    events: tuple[object, ...],
    event: object,
    event_type: type[object],
    event_id: EvidenceId,
    guard: DOIOccurrenceGuard,
    sequence: int,
    predecessor: HashBinding | None,
    code: str,
) -> bool:
    for retained in events:
        if type(retained) is not event_type:
            raise DOIModelError(code)
        retained_guard = cast(DOIOccurrenceGuard, getattr(retained, "guard"))
        retained_event_id = cast(EvidenceId, getattr(retained, "event_id"))
        if (
            retained_event_id == event_id
            or retained_guard.occurrence_id == guard.occurrence_id
        ):
            retained_bytes = cast(object, retained).canonical_bytes()  # type: ignore[attr-defined]
            event_bytes = cast(object, event).canonical_bytes()  # type: ignore[attr-defined]
            if retained_bytes != event_bytes:
                raise DOIModelError("DOI_EVENT_REPLAY_CONFLICT")
            return True
    expected_sequence = len(events) + 1
    expected_predecessor = (
        None
        if not events
        else cast(object, events[-1]).hash_binding()  # type: ignore[attr-defined]
    )
    if sequence != expected_sequence or predecessor != expected_predecessor:
        raise DOIModelError(code)
    return False


_ACTION_CONTEXT_EVENT_TOKEN = object()
_ACTION_CONTEXT_LINK_TOKEN = object()


def _timestamp_key(value: CanonicalTimestamp) -> tuple[int, int]:
    return value.epoch_seconds, value.nanosecond


@dataclass(frozen=True, slots=True, init=False, repr=False)
class DOIActionContextObservationLink:
    link_id: EvidenceId
    action_context_id: EvidenceId
    action_context_binding: HashBinding
    case_id: EvidenceId
    evaluation_id: EvaluationId
    opportunity_id: EvidenceId
    alternate_observation_id: EvidenceId
    alternate_observation_binding: HashBinding
    relationship_revision_id: EvidenceId
    relationship_revision_binding: HashBinding
    linked_at: CanonicalTimestamp
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-action-context-observation-link/v1"

    def __new__(cls) -> DOIActionContextObservationLink:
        raise DOIModelError("DOI_ACTION_CONTEXT_LINK_FACTORY_REQUIRED")

    @classmethod
    def _create(
        cls,
        *,
        link_id: EvidenceId,
        action_context: DOIActionContext,
        observation: object,
        relationship_revision: object,
        linked_at: CanonicalTimestamp,
        factory_capability: object,
    ) -> DOIActionContextObservationLink:
        if factory_capability is not _ACTION_CONTEXT_LINK_TOKEN:
            raise DOIModelError("DOI_ACTION_CONTEXT_LINK_FACTORY_REQUIRED")
        from synthetic_sales_assist.doi.knowledge import (
            DOIAlternateObservation,
            DOIAlternateRelationshipRevision,
        )

        if (
            type(link_id) is not EvidenceId
            or type(action_context) is not DOIActionContext
            or action_context.state is not ActionContextState.OPEN
            or type(observation) is not DOIAlternateObservation
            or type(relationship_revision) is not DOIAlternateRelationshipRevision
            or type(linked_at) is not CanonicalTimestamp
            or observation.action_context_id != action_context.action_context_id
            or observation.action_context_binding != action_context.hash_binding()
            or observation.relationship_revision_binding
            != relationship_revision.hash_binding()
            or action_context.relationship_revision_binding
            != relationship_revision.hash_binding()
            or observation.state is not AlternateObservationState.CURRENT
            or _timestamp_key(observation.observed_at)
            < _timestamp_key(action_context.created_at)
            or _timestamp_key(linked_at) < _timestamp_key(observation.observed_at)
        ):
            raise DOIModelError("DOI_ACTION_CONTEXT_LINK_OWNER_INVALID")
        instance = object.__new__(cls)
        object.__setattr__(instance, "link_id", link_id)
        object.__setattr__(
            instance,
            "action_context_id",
            action_context.action_context_id,
        )
        object.__setattr__(
            instance,
            "action_context_binding",
            action_context.hash_binding(),
        )
        object.__setattr__(instance, "case_id", action_context.case_id)
        object.__setattr__(instance, "evaluation_id", action_context.evaluation_id)
        object.__setattr__(instance, "opportunity_id", action_context.opportunity_id)
        object.__setattr__(
            instance,
            "alternate_observation_id",
            observation.observation_id,
        )
        object.__setattr__(
            instance,
            "alternate_observation_binding",
            observation.hash_binding(),
        )
        object.__setattr__(
            instance,
            "relationship_revision_id",
            relationship_revision.revision_id,
        )
        object.__setattr__(
            instance,
            "relationship_revision_binding",
            relationship_revision.hash_binding(),
        )
        object.__setattr__(instance, "linked_at", linked_at)
        object.__setattr__(instance, "schema_version", DOI_MODEL_SCHEMA_VERSION)
        instance.__post_init__()
        return instance

    def __post_init__(self) -> None:
        if (
            type(self.link_id) is not EvidenceId
            or type(self.action_context_id) is not EvidenceId
            or type(self.action_context_binding) is not HashBinding
            or self.action_context_binding.domain != DOIActionContext.HASH_DOMAIN
            or type(self.case_id) is not EvidenceId
            or type(self.evaluation_id) is not EvaluationId
            or type(self.opportunity_id) is not EvidenceId
            or type(self.alternate_observation_id) is not EvidenceId
            or type(self.alternate_observation_binding) is not HashBinding
            or self.alternate_observation_binding.domain
            != "doi-alternate-observation/v1"
            or type(self.relationship_revision_id) is not EvidenceId
            or type(self.relationship_revision_binding) is not HashBinding
            or self.relationship_revision_binding.domain
            != "doi-alternate-relationship-revision/v1"
            or type(self.linked_at) is not CanonicalTimestamp
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_ACTION_CONTEXT_LINK_INVALID")

    @property
    def natural_key(self) -> tuple[str, str, str]:
        return (
            self.action_context_id.value,
            self.alternate_observation_id.value,
            self.relationship_revision_id.value,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "action_context_binding": _binding_json(self.action_context_binding),
            "action_context_id": self.action_context_id.value,
            "alternate_observation_binding": _binding_json(
                self.alternate_observation_binding
            ),
            "alternate_observation_id": self.alternate_observation_id.value,
            "case_id": self.case_id.value,
            "evaluation_id": self.evaluation_id.value,
            "link_id": self.link_id.value,
            "linked_at": self.linked_at.value,
            "opportunity_id": self.opportunity_id.value,
            "relationship_revision_binding": _binding_json(
                self.relationship_revision_binding
            ),
            "relationship_revision_id": self.relationship_revision_id.value,
            "schema_version": self.schema_version,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIActionContextObservationLink(<closed>)"


@dataclass(frozen=True, slots=True, init=False, repr=False)
class DOIActionContextEvent:
    event_id: EvidenceId
    action_context_id: EvidenceId
    opening_authorization: ActionContextOpeningAuthorization
    event_type: ActionContextEventType
    observation_link: DOIActionContextObservationLink | None
    completion_trigger: ActionContextCompletionTrigger | None
    close_reason: ActionContextCloseReason | None
    source_entity_binding: HashBinding
    human_authority_binding: HashBinding | None
    superseding_context_binding: HashBinding | None
    occurred_at: CanonicalTimestamp
    sequence: int
    predecessor_binding: HashBinding | None
    guard: DOIOccurrenceGuard
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-action-context-event/v1"
    COMPLETION_SOURCE_DOMAIN: ClassVar[str] = "doi-action-context-completion-source/v1"

    def __new__(cls) -> DOIActionContextEvent:
        raise DOIModelError("DOI_ACTION_CONTEXT_EVENT_FACTORY_REQUIRED")

    @classmethod
    def _build(
        cls,
        *,
        event_id: EvidenceId,
        action_context_id: EvidenceId,
        opening_authorization: ActionContextOpeningAuthorization,
        event_type: ActionContextEventType,
        observation_link: DOIActionContextObservationLink | None,
        completion_trigger: ActionContextCompletionTrigger | None,
        close_reason: ActionContextCloseReason | None,
        source_entity_binding: HashBinding,
        human_authority_binding: HashBinding | None,
        superseding_context_binding: HashBinding | None,
        occurred_at: CanonicalTimestamp,
        sequence: int,
        predecessor_binding: HashBinding | None,
        guard: DOIOccurrenceGuard,
        factory_capability: object,
    ) -> DOIActionContextEvent:
        if factory_capability is not _ACTION_CONTEXT_EVENT_TOKEN:
            raise DOIModelError("DOI_ACTION_CONTEXT_EVENT_FACTORY_REQUIRED")
        instance = object.__new__(cls)
        object.__setattr__(instance, "event_id", event_id)
        object.__setattr__(instance, "action_context_id", action_context_id)
        object.__setattr__(instance, "opening_authorization", opening_authorization)
        object.__setattr__(instance, "event_type", event_type)
        object.__setattr__(instance, "observation_link", observation_link)
        object.__setattr__(instance, "completion_trigger", completion_trigger)
        object.__setattr__(instance, "close_reason", close_reason)
        object.__setattr__(instance, "source_entity_binding", source_entity_binding)
        object.__setattr__(instance, "human_authority_binding", human_authority_binding)
        object.__setattr__(
            instance,
            "superseding_context_binding",
            superseding_context_binding,
        )
        object.__setattr__(instance, "occurred_at", occurred_at)
        object.__setattr__(instance, "sequence", sequence)
        object.__setattr__(instance, "predecessor_binding", predecessor_binding)
        object.__setattr__(instance, "guard", guard)
        object.__setattr__(instance, "schema_version", DOI_MODEL_SCHEMA_VERSION)
        instance.__post_init__()
        return instance

    @classmethod
    def opened(
        cls,
        *,
        event_id: EvidenceId,
        action_context_id: EvidenceId,
        opening_authorization: ActionContextOpeningAuthorization,
        created_at: CanonicalTimestamp,
        guard: DOIOccurrenceGuard,
    ) -> DOIActionContextEvent:
        return cls._build(
            event_id=event_id,
            action_context_id=action_context_id,
            opening_authorization=opening_authorization,
            event_type=ActionContextEventType.OPENED,
            observation_link=None,
            completion_trigger=None,
            close_reason=None,
            source_entity_binding=opening_authorization.hash_binding(),
            human_authority_binding=None,
            superseding_context_binding=None,
            occurred_at=created_at,
            sequence=1,
            predecessor_binding=None,
            guard=guard,
            factory_capability=_ACTION_CONTEXT_EVENT_TOKEN,
        )

    @classmethod
    def observation_linked(
        cls,
        *,
        event_id: EvidenceId,
        action_context: DOIActionContext,
        link_id: EvidenceId,
        observation: object,
        relationship_revision: object,
        authority: HumanAuthorityGrant,
        linked_at: CanonicalTimestamp,
        guard: DOIOccurrenceGuard,
    ) -> DOIActionContextEvent:
        cls._require_current_authority(action_context, authority, guard, linked_at)
        link = DOIActionContextObservationLink._create(
            link_id=link_id,
            action_context=action_context,
            observation=observation,
            relationship_revision=relationship_revision,
            linked_at=linked_at,
            factory_capability=_ACTION_CONTEXT_LINK_TOKEN,
        )
        return cls._build(
            event_id=event_id,
            action_context_id=action_context.action_context_id,
            opening_authorization=action_context.opening_authorization,
            event_type=ActionContextEventType.OBSERVATION_LINKED,
            observation_link=link,
            completion_trigger=None,
            close_reason=None,
            source_entity_binding=link.hash_binding(),
            human_authority_binding=authority.hash_binding(),
            superseding_context_binding=None,
            occurred_at=linked_at,
            sequence=action_context.sequence + 1,
            predecessor_binding=action_context.head_event_binding,
            guard=guard,
            factory_capability=_ACTION_CONTEXT_EVENT_TOKEN,
        )

    @classmethod
    def completed(
        cls,
        *,
        event_id: EvidenceId,
        action_context: DOIActionContext,
        completion_trigger: ActionContextCompletionTrigger,
        occurred_at: CanonicalTimestamp,
        guard: DOIOccurrenceGuard,
        authority: HumanAuthorityGrant | None = None,
        close_reason: ActionContextCloseReason | None = None,
    ) -> DOIActionContextEvent:
        if (
            type(action_context) is not DOIActionContext
            or action_context.state is not ActionContextState.OPEN
            or completion_trigger
            not in {
                ActionContextCompletionTrigger.HUMAN_ACCEPTED,
                ActionContextCompletionTrigger.SYSTEM_VERIFIED,
            }
        ):
            raise DOIModelError("DOI_ACTION_CONTEXT_COMPLETION_INVALID")
        if completion_trigger is ActionContextCompletionTrigger.HUMAN_ACCEPTED:
            if type(authority) is not HumanAuthorityGrant:
                raise DOIModelError("DOI_ACTION_CONTEXT_COMPLETION_AUTHORITY_REQUIRED")
            cls._require_current_authority(action_context, authority, guard, occurred_at)
        elif authority is not None:
            raise DOIModelError("DOI_ACTION_CONTEXT_COMPLETION_AUTHORITY_INVALID")
        elif (
            type(guard) is not DOIOccurrenceGuard
            or guard.owner_id != action_context.action_context_id
        ):
            raise DOIModelError("DOI_ACTION_CONTEXT_COMPLETION_SOURCE_INVALID")
        expected_close_reason = (
            ActionContextCloseReason.REVIEW_FINISHED
            if action_context.context_kind
            is ActionContextKind.RESULTING_ORDER_LINK_REVIEW
            else (
                ActionContextCloseReason.DECISION_RECORDED
                if completion_trigger is ActionContextCompletionTrigger.HUMAN_ACCEPTED
                else ActionContextCloseReason.ACTION_VERIFIED
            )
        )
        selected_close_reason = close_reason or expected_close_reason
        if selected_close_reason is not expected_close_reason:
            raise DOIModelError("DOI_ACTION_CONTEXT_CLOSE_REASON_INVALID")
        source_bytes = canonical_json_bytes(
            {
                "action_context_binding": _binding_json(
                    action_context.hash_binding()
                ),
                "action_context_id": action_context.action_context_id.value,
                "completion_trigger": completion_trigger.value,
                "occurred_at": occurred_at.value,
                "source": _binding_json(guard.source.hash_binding()),
            },
            expected_members={
                "action_context_binding",
                "action_context_id",
                "completion_trigger",
                "occurred_at",
                "source",
            },
        )
        source_binding = domain_hash(cls.COMPLETION_SOURCE_DOMAIN, source_bytes)
        return cls._build(
            event_id=event_id,
            action_context_id=action_context.action_context_id,
            opening_authorization=action_context.opening_authorization,
            event_type=ActionContextEventType.COMPLETED,
            observation_link=None,
            completion_trigger=completion_trigger,
            close_reason=selected_close_reason,
            source_entity_binding=source_binding,
            human_authority_binding=(
                authority.hash_binding() if authority is not None else None
            ),
            superseding_context_binding=None,
            occurred_at=occurred_at,
            sequence=action_context.sequence + 1,
            predecessor_binding=action_context.head_event_binding,
            guard=guard,
            factory_capability=_ACTION_CONTEXT_EVENT_TOKEN,
        )

    @classmethod
    def abandoned(
        cls,
        *,
        event_id: EvidenceId,
        action_context: DOIActionContext,
        authority: HumanAuthorityGrant,
        occurred_at: CanonicalTimestamp,
        guard: DOIOccurrenceGuard,
    ) -> DOIActionContextEvent:
        cls._require_current_authority(action_context, authority, guard, occurred_at)
        return cls._build(
            event_id=event_id,
            action_context_id=action_context.action_context_id,
            opening_authorization=action_context.opening_authorization,
            event_type=ActionContextEventType.ABANDONED,
            observation_link=None,
            completion_trigger=None,
            close_reason=ActionContextCloseReason.HUMAN_ABANDONED,
            source_entity_binding=authority.hash_binding(),
            human_authority_binding=authority.hash_binding(),
            superseding_context_binding=None,
            occurred_at=occurred_at,
            sequence=action_context.sequence + 1,
            predecessor_binding=action_context.head_event_binding,
            guard=guard,
            factory_capability=_ACTION_CONTEXT_EVENT_TOKEN,
        )

    @classmethod
    def superseded(
        cls,
        *,
        event_id: EvidenceId,
        action_context: DOIActionContext,
        superseding_open_event: DOIActionContextEvent,
        occurred_at: CanonicalTimestamp,
        guard: DOIOccurrenceGuard,
    ) -> DOIActionContextEvent:
        if (
            type(action_context) is not DOIActionContext
            or action_context.state is not ActionContextState.OPEN
            or type(superseding_open_event) is not DOIActionContextEvent
            or superseding_open_event.event_type is not ActionContextEventType.OPENED
            or superseding_open_event.action_context_id
            == action_context.action_context_id
            or superseding_open_event.attempt_intent_id
            == action_context.attempt_intent_id
            or superseding_open_event.case_id != action_context.case_id
            or superseding_open_event.evaluation_id != action_context.evaluation_id
            or superseding_open_event.opportunity_id != action_context.opportunity_id
            or superseding_open_event.context_kind is not action_context.context_kind
            or superseding_open_event.line_scope != action_context.line_scope
            or _timestamp_key(superseding_open_event.occurred_at)
            <= _timestamp_key(action_context.created_at)
            or _timestamp_key(occurred_at)
            < _timestamp_key(superseding_open_event.occurred_at)
            or guard.owner_id != action_context.action_context_id
            or guard.source != superseding_open_event.opening_authorization.source
        ):
            raise DOIModelError("DOI_ACTION_CONTEXT_SUPERSESSION_INVALID")
        superseding_binding = superseding_open_event.hash_binding()
        return cls._build(
            event_id=event_id,
            action_context_id=action_context.action_context_id,
            opening_authorization=action_context.opening_authorization,
            event_type=ActionContextEventType.SUPERSEDED,
            observation_link=None,
            completion_trigger=None,
            close_reason=ActionContextCloseReason.SUPERSEDED_BY_LATER_ATTEMPT,
            source_entity_binding=superseding_binding,
            human_authority_binding=None,
            superseding_context_binding=superseding_binding,
            occurred_at=occurred_at,
            sequence=action_context.sequence + 1,
            predecessor_binding=action_context.head_event_binding,
            guard=guard,
            factory_capability=_ACTION_CONTEXT_EVENT_TOKEN,
        )

    @staticmethod
    def _require_current_authority(
        action_context: DOIActionContext,
        authority: HumanAuthorityGrant,
        guard: DOIOccurrenceGuard,
        occurred_at: CanonicalTimestamp,
    ) -> None:
        if (
            type(action_context) is not DOIActionContext
            or action_context.state is not ActionContextState.OPEN
            or type(authority) is not HumanAuthorityGrant
            or authority.action_context_id != action_context.action_context_id
            or authority.action_context_binding != action_context.hash_binding()
            or type(guard) is not DOIOccurrenceGuard
            or guard.owner_id != action_context.action_context_id
            or guard.source != authority.source
            or _timestamp_key(occurred_at) < _timestamp_key(authority.granted_at)
        ):
            raise DOIModelError("DOI_ACTION_CONTEXT_EVENT_AUTHORITY_INVALID")

    def __post_init__(self) -> None:
        if (
            type(self.event_id) is not EvidenceId
            or type(self.action_context_id) is not EvidenceId
            or type(self.opening_authorization)
            is not ActionContextOpeningAuthorization
            or type(self.event_type) is not ActionContextEventType
            or type(self.source_entity_binding) is not HashBinding
            or type(self.occurred_at) is not CanonicalTimestamp
            or type(self.guard) is not DOIOccurrenceGuard
            or self.guard.guard_id != self.event_id
            or self.guard.owner_id != self.action_context_id
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
            or _timestamp_key(self.occurred_at)
            < _timestamp_key(self.opening_authorization.granted_at)
        ):
            raise DOIModelError("DOI_ACTION_CONTEXT_EVENT_INVALID")
        partitions = {
            ActionContextEventType.OPENED: (
                self.observation_link is None
                and self.completion_trigger is None
                and self.close_reason is None
                and self.source_entity_binding
                == self.opening_authorization.hash_binding()
                and self.human_authority_binding is None
                and self.superseding_context_binding is None
                and self.sequence == 1
                and self.predecessor_binding is None
                and self.guard.source == self.opening_authorization.source
                and self.guard.occurrence_id
                == self.opening_authorization.attempt_intent_id
            ),
            ActionContextEventType.OBSERVATION_LINKED: (
                type(self.observation_link) is DOIActionContextObservationLink
                and self.observation_link.action_context_id == self.action_context_id
                and self.source_entity_binding == self.observation_link.hash_binding()
                and self.completion_trigger is None
                and self.close_reason is None
                and type(self.human_authority_binding) is HashBinding
                and self.human_authority_binding.domain
                == HumanAuthorityGrant.HASH_DOMAIN
                and self.superseding_context_binding is None
            ),
            ActionContextEventType.COMPLETED: (
                self.observation_link is None
                and self.completion_trigger
                in {
                    ActionContextCompletionTrigger.HUMAN_ACCEPTED,
                    ActionContextCompletionTrigger.SYSTEM_VERIFIED,
                }
                and self.close_reason
                in {
                    ActionContextCloseReason.ACTION_VERIFIED,
                    ActionContextCloseReason.DECISION_RECORDED,
                    ActionContextCloseReason.REVIEW_FINISHED,
                }
                and self.source_entity_binding.domain
                == self.COMPLETION_SOURCE_DOMAIN
                and (
                    (self.completion_trigger
                    is ActionContextCompletionTrigger.HUMAN_ACCEPTED)
                    == (type(self.human_authority_binding) is HashBinding)
                )
                and self.superseding_context_binding is None
            ),
            ActionContextEventType.ABANDONED: (
                self.observation_link is None
                and self.completion_trigger is None
                and self.close_reason is ActionContextCloseReason.HUMAN_ABANDONED
                and type(self.human_authority_binding) is HashBinding
                and self.source_entity_binding == self.human_authority_binding
                and self.superseding_context_binding is None
            ),
            ActionContextEventType.SUPERSEDED: (
                self.observation_link is None
                and self.completion_trigger is None
                and self.close_reason
                is ActionContextCloseReason.SUPERSEDED_BY_LATER_ATTEMPT
                and self.human_authority_binding is None
                and type(self.superseding_context_binding) is HashBinding
                and self.source_entity_binding == self.superseding_context_binding
                and self.superseding_context_binding.domain == self.HASH_DOMAIN
            ),
        }
        if not partitions[self.event_type]:
            raise DOIModelError("DOI_ACTION_CONTEXT_EVENT_PARTITION_INVALID")
        _validate_event_position(
            self.sequence,
            self.predecessor_binding,
            event_domain=self.HASH_DOMAIN,
            code="DOI_ACTION_CONTEXT_EVENT_POSITION_INVALID",
        )

    @property
    def attempt_intent_id(self) -> InteractionId:
        return self.opening_authorization.attempt_intent_id

    @property
    def case_id(self) -> EvidenceId:
        return self.opening_authorization.case_id

    @property
    def evaluation_id(self) -> EvaluationId:
        return self.opening_authorization.evaluation_id

    @property
    def order_id(self) -> DoiOrderId:
        return self.opening_authorization.order_id

    @property
    def opportunity_id(self) -> EvidenceId:
        return self.opening_authorization.opportunity_id

    @property
    def context_kind(self) -> ActionContextKind:
        return self.opening_authorization.context_kind

    @property
    def line_scope(self) -> tuple[LineSnapshotId, ...]:
        return tuple(
            sorted(
                self._opportunity_scope_line_ids(),
                key=lambda item: item.to_json_value(),
            )
        )

    def _opportunity_scope_line_ids(self) -> frozenset[LineSnapshotId]:
        decoded = self.opening_authorization.opportunity_binding.canonical_bytes
        # The sealed authorization was issued from the typed opportunity. Its canonical
        # bytes bind a scope digest, while the exact line set is retained in the request
        # owner's evaluation. Events therefore persist the canonical line set separately
        # through the authorization's private retained value below.
        del decoded
        return cast(
            frozenset[LineSnapshotId],
            getattr(self.opening_authorization, "_line_scope"),
        )

    @property
    def relationship_revision_binding(self) -> HashBinding | None:
        return cast(
            HashBinding | None,
            getattr(self.opening_authorization, "_relationship_revision_binding"),
        )

    @property
    def alternate_observation_binding(self) -> HashBinding | None:
        if self.observation_link is None:
            return None
        return self.observation_link.alternate_observation_binding

    def to_dict(self) -> dict[str, object]:
        return {
            "action_context_id": self.action_context_id.value,
            "close_reason": (
                self.close_reason.value if self.close_reason is not None else None
            ),
            "completion_trigger": (
                self.completion_trigger.value
                if self.completion_trigger is not None
                else None
            ),
            "event_id": self.event_id.value,
            "event_type": self.event_type.value,
            "guard": _binding_json(self.guard.hash_binding()),
            "human_authority_binding": (
                _binding_json(self.human_authority_binding)
                if self.human_authority_binding is not None
                else None
            ),
            "occurred_at": self.occurred_at.value,
            "observation_link": (
                _binding_json(self.observation_link.hash_binding())
                if self.observation_link is not None
                else None
            ),
            "opening_authorization": _binding_json(
                self.opening_authorization.hash_binding()
            ),
            "predecessor_binding": (
                _binding_json(self.predecessor_binding)
                if self.predecessor_binding is not None
                else None
            ),
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "source_entity_binding": _binding_json(self.source_entity_binding),
            "superseding_context_binding": (
                _binding_json(self.superseding_context_binding)
                if self.superseding_context_binding is not None
                else None
            ),
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIActionContextEvent(<closed>)"


@dataclass(frozen=True, slots=True, init=False, repr=False)
class DOIActionContext:
    action_context_id: EvidenceId
    opening_authorization: ActionContextOpeningAuthorization
    created_at: CanonicalTimestamp
    state: ActionContextState
    completion_trigger: ActionContextCompletionTrigger | None
    close_reason: ActionContextCloseReason | None
    observation_links: tuple[DOIActionContextObservationLink, ...]
    terminal_source_binding: HashBinding | None
    sequence: int
    head_event_binding: HashBinding
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-action-context/v1"

    def __new__(cls) -> DOIActionContext:
        raise DOIModelError("DOI_ACTION_CONTEXT_REDUCER_REQUIRED")

    @classmethod
    def _project(
        cls,
        *,
        event: DOIActionContextEvent,
        prior: DOIActionContext | None,
    ) -> DOIActionContext:
        state = {
            ActionContextEventType.OPENED: ActionContextState.OPEN,
            ActionContextEventType.OBSERVATION_LINKED: ActionContextState.OPEN,
            ActionContextEventType.COMPLETED: ActionContextState.CLOSED_COMPLETED,
            ActionContextEventType.ABANDONED: ActionContextState.CLOSED_ABANDONED,
            ActionContextEventType.SUPERSEDED: ActionContextState.CLOSED_SUPERSEDED,
        }[event.event_type]
        links = () if prior is None else prior.observation_links
        if event.observation_link is not None:
            links = (*links, event.observation_link)
        instance = object.__new__(cls)
        object.__setattr__(instance, "action_context_id", event.action_context_id)
        object.__setattr__(
            instance,
            "opening_authorization",
            event.opening_authorization,
        )
        object.__setattr__(
            instance,
            "created_at",
            event.occurred_at if prior is None else prior.created_at,
        )
        object.__setattr__(instance, "state", state)
        object.__setattr__(instance, "completion_trigger", event.completion_trigger)
        object.__setattr__(instance, "close_reason", event.close_reason)
        object.__setattr__(instance, "observation_links", links)
        object.__setattr__(
            instance,
            "terminal_source_binding",
            None if state is ActionContextState.OPEN else event.source_entity_binding,
        )
        object.__setattr__(instance, "sequence", event.sequence)
        object.__setattr__(instance, "head_event_binding", event.hash_binding())
        object.__setattr__(instance, "schema_version", DOI_MODEL_SCHEMA_VERSION)
        instance.__post_init__()
        return instance

    @classmethod
    def from_event(cls, event: DOIActionContextEvent) -> DOIActionContext:
        if event.event_type is not ActionContextEventType.OPENED:
            raise DOIModelError("DOI_ACTION_CONTEXT_OPEN_REQUIRED")
        return cls._project(event=event, prior=None)

    def __post_init__(self) -> None:
        if (
            type(self.action_context_id) is not EvidenceId
            or type(self.opening_authorization)
            is not ActionContextOpeningAuthorization
            or type(self.created_at) is not CanonicalTimestamp
            or type(self.state) is not ActionContextState
            or type(self.observation_links) is not tuple
            or any(
                type(link) is not DOIActionContextObservationLink
                or link.action_context_id != self.action_context_id
                for link in self.observation_links
            )
            or type(self.sequence) is not int
            or self.sequence < 1
            or type(self.head_event_binding) is not HashBinding
            or self.head_event_binding.domain != DOIActionContextEvent.HASH_DOMAIN
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_ACTION_CONTEXT_INVALID")
        keys = tuple(link.natural_key for link in self.observation_links)
        if len(keys) != len(set(keys)):
            raise DOIModelError("DOI_ACTION_CONTEXT_LINK_CONFLICT")
        if self.state is ActionContextState.OPEN:
            partition = (
                self.completion_trigger is None
                and self.close_reason is None
                and self.terminal_source_binding is None
            )
        elif self.state is ActionContextState.CLOSED_COMPLETED:
            partition = (
                self.completion_trigger
                in {
                    ActionContextCompletionTrigger.HUMAN_ACCEPTED,
                    ActionContextCompletionTrigger.SYSTEM_VERIFIED,
                }
                and self.close_reason
                in {
                    ActionContextCloseReason.ACTION_VERIFIED,
                    ActionContextCloseReason.DECISION_RECORDED,
                    ActionContextCloseReason.REVIEW_FINISHED,
                }
                and type(self.terminal_source_binding) is HashBinding
            )
        elif self.state is ActionContextState.CLOSED_ABANDONED:
            partition = (
                self.completion_trigger is None
                and self.close_reason is ActionContextCloseReason.HUMAN_ABANDONED
                and type(self.terminal_source_binding) is HashBinding
            )
        else:
            partition = (
                self.completion_trigger is None
                and self.close_reason
                is ActionContextCloseReason.SUPERSEDED_BY_LATER_ATTEMPT
                and type(self.terminal_source_binding) is HashBinding
            )
        if not partition:
            raise DOIModelError("DOI_ACTION_CONTEXT_STATE_PARTITION_INVALID")

    @property
    def attempt_intent_id(self) -> InteractionId:
        return self.opening_authorization.attempt_intent_id

    @property
    def case_id(self) -> EvidenceId:
        return self.opening_authorization.case_id

    @property
    def evaluation_id(self) -> EvaluationId:
        return self.opening_authorization.evaluation_id

    @property
    def order_id(self) -> DoiOrderId:
        return self.opening_authorization.order_id

    @property
    def opportunity_id(self) -> EvidenceId:
        return self.opening_authorization.opportunity_id

    @property
    def context_kind(self) -> ActionContextKind:
        return self.opening_authorization.context_kind

    @property
    def intervention_type(self) -> InterventionType:
        return self.opening_authorization.intervention_type

    @property
    def line_scope(self) -> tuple[LineSnapshotId, ...]:
        return tuple(
            sorted(
                cast(
                    frozenset[LineSnapshotId],
                    getattr(self.opening_authorization, "_line_scope"),
                ),
                key=lambda item: item.to_json_value(),
            )
        )

    @property
    def relationship_revision_binding(self) -> HashBinding | None:
        return cast(
            HashBinding | None,
            getattr(self.opening_authorization, "_relationship_revision_binding"),
        )

    @property
    def alternate_observation_binding(self) -> HashBinding | None:
        if not self.observation_links:
            return None
        return self.observation_links[-1].alternate_observation_binding

    def to_dict(self) -> dict[str, object]:
        return {
            "action_context_id": self.action_context_id.value,
            "close_reason": (
                self.close_reason.value if self.close_reason is not None else None
            ),
            "completion_trigger": (
                self.completion_trigger.value
                if self.completion_trigger is not None
                else None
            ),
            "created_at": self.created_at.value,
            "head_event_binding": _binding_json(self.head_event_binding),
            "observation_links": [
                _binding_json(link.hash_binding()) for link in self.observation_links
            ],
            "opening_authorization": _binding_json(
                self.opening_authorization.hash_binding()
            ),
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "state": self.state.value,
            "terminal_source_binding": (
                _binding_json(self.terminal_source_binding)
                if self.terminal_source_binding is not None
                else None
            ),
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIActionContext(<closed>)"


@dataclass(frozen=True, slots=True)
class DOIActionContextHistory:
    action_context_id: EvidenceId
    projection: DOIActionContext | None = None
    events: tuple[DOIActionContextEvent, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.action_context_id) is not EvidenceId
            or type(self.events) is not tuple
            or any(type(event) is not DOIActionContextEvent for event in self.events)
            or any(event.action_context_id != self.action_context_id for event in self.events)
        ):
            raise DOIModelError("DOI_ACTION_CONTEXT_HISTORY_INVALID")
        if not self.events:
            if self.projection is not None:
                raise DOIModelError("DOI_ACTION_CONTEXT_HISTORY_INVALID")
            return
        if (
            self.events[0].event_type is not ActionContextEventType.OPENED
            or any(
                event.sequence != index
                or event.predecessor_binding
                != (None if index == 1 else self.events[index - 2].hash_binding())
                or event.opening_authorization != self.events[0].opening_authorization
                for index, event in enumerate(self.events, start=1)
            )
            or type(self.projection) is not DOIActionContext
            or self.projection.action_context_id != self.action_context_id
            or self.projection.sequence != len(self.events)
            or self.projection.head_event_binding != self.events[-1].hash_binding()
        ):
            raise DOIModelError("DOI_ACTION_CONTEXT_HISTORY_INVALID")


@dataclass(frozen=True, slots=True)
class DOIActionContextReduction:
    history: DOIActionContextHistory
    event: DOIActionContextEvent
    replayed: bool


def reduce_action_context(
    history: DOIActionContextHistory,
    event: DOIActionContextEvent,
) -> DOIActionContextReduction:
    if (
        type(history) is not DOIActionContextHistory
        or type(event) is not DOIActionContextEvent
        or event.action_context_id != history.action_context_id
    ):
        raise DOIModelError("DOI_ACTION_CONTEXT_REDUCER_INPUT_INVALID")
    replayed = _require_event_append(
        events=cast(tuple[object, ...], history.events),
        event=event,
        event_type=DOIActionContextEvent,
        event_id=event.event_id,
        guard=event.guard,
        sequence=event.sequence,
        predecessor=event.predecessor_binding,
        code="DOI_ACTION_CONTEXT_EVENT_CONFLICT",
    )
    if replayed:
        return DOIActionContextReduction(history, event, True)
    prior = history.projection
    if prior is None:
        if event.event_type is not ActionContextEventType.OPENED:
            raise DOIModelError("DOI_ACTION_CONTEXT_OPEN_REQUIRED")
    else:
        if prior.state is not ActionContextState.OPEN:
            raise DOIModelError("DOI_ACTION_CONTEXT_TERMINAL")
        if event.event_type is ActionContextEventType.OPENED:
            raise DOIModelError("DOI_ACTION_CONTEXT_ALREADY_OPEN")
        if event.opening_authorization != prior.opening_authorization:
            raise DOIModelError("DOI_ACTION_CONTEXT_SCOPE_CONFLICT")
        if event.observation_link is not None:
            for retained in prior.observation_links:
                if retained.natural_key == event.observation_link.natural_key:
                    if retained.canonical_bytes() != event.observation_link.canonical_bytes():
                        raise DOIModelError("DOI_ACTION_CONTEXT_LINK_CONFLICT")
                    return DOIActionContextReduction(history, event, True)
    projection = DOIActionContext._project(event=event, prior=prior)
    updated = DOIActionContextHistory(
        action_context_id=history.action_context_id,
        projection=projection,
        events=(*history.events, event),
    )
    return DOIActionContextReduction(updated, event, False)


@dataclass(frozen=True, slots=True)
class DOIActionContextStore:
    histories: tuple[DOIActionContextHistory, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.histories) is not tuple
            or any(type(item) is not DOIActionContextHistory for item in self.histories)
        ):
            raise DOIModelError("DOI_ACTION_CONTEXT_STORE_INVALID")
        context_keys = tuple(item.action_context_id.value for item in self.histories)
        if context_keys != tuple(sorted(context_keys)) or len(context_keys) != len(
            set(context_keys)
        ):
            raise DOIModelError("DOI_ACTION_CONTEXT_STORE_INVALID")
        attempts = tuple(
            item.events[0].attempt_intent_id.value
            for item in self.histories
            if item.events
        )
        if len(attempts) != len(set(attempts)):
            raise DOIModelError("DOI_ACTION_CONTEXT_ATTEMPT_CONFLICT")


@dataclass(frozen=True, slots=True)
class DOIActionContextStoreReduction:
    store: DOIActionContextStore
    history: DOIActionContextHistory
    event: DOIActionContextEvent
    replayed: bool


def reduce_action_context_store(
    store: DOIActionContextStore,
    event: DOIActionContextEvent,
) -> DOIActionContextStoreReduction:
    if type(store) is not DOIActionContextStore or type(event) is not DOIActionContextEvent:
        raise DOIModelError("DOI_ACTION_CONTEXT_STORE_INPUT_INVALID")
    by_id = {item.action_context_id: item for item in store.histories}
    if event.event_type is ActionContextEventType.OPENED:
        for retained in store.histories:
            if not retained.events:
                continue
            opening = retained.events[0]
            if opening.attempt_intent_id == event.attempt_intent_id:
                if (
                    opening.opening_authorization.request_canonical_bytes
                    != event.opening_authorization.request_canonical_bytes
                ):
                    raise DOIModelError("DOI_ACTION_CONTEXT_ATTEMPT_CONFLICT")
                return DOIActionContextStoreReduction(
                    store,
                    retained,
                    opening,
                    True,
                )
    history = by_id.get(
        event.action_context_id,
        DOIActionContextHistory(action_context_id=event.action_context_id),
    )
    reduced = reduce_action_context(history, event)
    histories = tuple(
        sorted(
            (
                reduced.history if item.action_context_id == event.action_context_id else item
                for item in (
                    store.histories
                    if event.action_context_id in by_id
                    else (*store.histories, history)
                )
            ),
            key=lambda item: item.action_context_id.value,
        )
    )
    updated = DOIActionContextStore(histories=histories)
    return DOIActionContextStoreReduction(
        updated,
        reduced.history,
        reduced.event,
        reduced.replayed,
    )


_HUMAN_AUTHORITY_TOKEN = object()


@dataclass(frozen=True, slots=True, init=False, repr=False)
class HumanAuthorityGrant:
    grant_id: EvidenceId
    actor: RepId
    action_context_id: EvidenceId
    action_context_binding: HashBinding
    granted_at: CanonicalTimestamp
    source: SourceRef
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-human-authority-grant/v1"

    @classmethod
    def _verified(
        cls,
        *,
        grant_id: EvidenceId,
        actor: RepId,
        action_context: DOIActionContext,
        granted_at: CanonicalTimestamp,
        source: SourceRef,
        factory_capability: object,
    ) -> HumanAuthorityGrant:
        if factory_capability is not _HUMAN_AUTHORITY_TOKEN:
            raise DOIModelError("DOI_HUMAN_AUTHORITY_FACTORY_REQUIRED")
        instance = object.__new__(cls)
        object.__setattr__(instance, "grant_id", grant_id)
        object.__setattr__(instance, "actor", actor)
        object.__setattr__(instance, "action_context_id", action_context.action_context_id)
        object.__setattr__(
            instance,
            "action_context_binding",
            action_context.hash_binding(),
        )
        object.__setattr__(instance, "granted_at", granted_at)
        object.__setattr__(instance, "source", source)
        object.__setattr__(instance, "schema_version", DOI_MODEL_SCHEMA_VERSION)
        instance.__post_init__()
        return instance

    def __post_init__(self) -> None:
        if (
            type(self.grant_id) is not EvidenceId
            or type(self.actor) is not RepId
            or type(self.action_context_id) is not EvidenceId
            or type(self.action_context_binding) is not HashBinding
            or self.action_context_binding.domain != DOIActionContext.HASH_DOMAIN
            or type(self.granted_at) is not CanonicalTimestamp
            or type(self.source) is not SourceRef
            or self.source.source_kind
            is not SourceKind.SYNTHETIC_INTERACTION_FIXTURE
            or self.source.object_namespace
            is not SourceObjectNamespace.SYNTHETIC_INTERACTION
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_HUMAN_AUTHORITY_GRANT_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "action_context_binding": _binding_json(self.action_context_binding),
            "action_context_id": self.action_context_id.value,
            "actor": self.actor.value,
            "grant_id": self.grant_id.value,
            "granted_at": self.granted_at.value,
            "schema_version": self.schema_version,
            "source": _binding_json(self.source.hash_binding()),
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "HumanAuthorityGrant(<closed>)"


def verify_synthetic_human_authority(
    *,
    grant_id: EvidenceId,
    actor: RepId,
    action_context: DOIActionContext,
    granted_at: CanonicalTimestamp,
    authority_source: SourceRef,
) -> HumanAuthorityGrant:
    """Cross the explicit synthetic authority-verification boundary."""

    if (
        type(action_context) is not DOIActionContext
        or action_context.state is not ActionContextState.OPEN
    ):
        raise DOIModelError("DOI_HUMAN_AUTHORITY_CONTEXT_INVALID")
    return HumanAuthorityGrant._verified(
        grant_id=grant_id,
        actor=actor,
        action_context=action_context,
        granted_at=granted_at,
        source=authority_source,
        factory_capability=_HUMAN_AUTHORITY_TOKEN,
    )


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DOIContactEvent:
    event_id: EvidenceId
    stream_id: EvidenceId
    order_id: DoiOrderId
    action_context: DOIActionContext
    event_type: ContactEventType
    corrected_direction: ContactEventType | None
    corrects_event_id: EvidenceId | None
    target_rep_participated: bool
    contact_occurred_at: CanonicalTimestamp
    recorded_at: CanonicalTimestamp
    sequence: int
    predecessor_binding: HashBinding | None
    guard: DOIOccurrenceGuard
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-contact-event/v1"

    def __post_init__(self) -> None:
        if (
            type(self.event_id) is not EvidenceId
            or type(self.stream_id) is not EvidenceId
            or type(self.order_id) is not DoiOrderId
            or type(self.action_context) is not DOIActionContext
            or self.action_context.order_id != self.order_id
            or type(self.event_type) is not ContactEventType
            or type(self.target_rep_participated) is not bool
            or type(self.contact_occurred_at) is not CanonicalTimestamp
            or type(self.recorded_at) is not CanonicalTimestamp
            or type(self.guard) is not DOIOccurrenceGuard
            or self.guard.guard_id != self.event_id
            or self.guard.owner_id != self.stream_id
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_CONTACT_EVENT_INVALID")
        corrected = self.event_type is ContactEventType.CORRECTION
        if corrected:
            if (
                self.corrected_direction
                not in {ContactEventType.INBOUND, ContactEventType.OUTBOUND}
                or type(self.corrects_event_id) is not EvidenceId
            ):
                raise DOIModelError("DOI_CONTACT_CORRECTION_INVALID")
        elif self.corrected_direction is not None or self.corrects_event_id is not None:
            raise DOIModelError("DOI_CONTACT_CORRECTION_INVALID")
        _validate_event_position(
            self.sequence,
            self.predecessor_binding,
            event_domain=self.HASH_DOMAIN,
            code="DOI_CONTACT_EVENT_POSITION_INVALID",
        )

    @property
    def direction(self) -> ContactEventType:
        if self.event_type is ContactEventType.CORRECTION:
            return cast(ContactEventType, self.corrected_direction)
        return self.event_type

    def to_dict(self) -> dict[str, object]:
        return {
            "action_context": _binding_json(self.action_context.hash_binding()),
            "contact_occurred_at": self.contact_occurred_at.value,
            "corrected_direction": (
                self.corrected_direction.value
                if self.corrected_direction is not None
                else None
            ),
            "corrects_event_id": (
                self.corrects_event_id.value
                if self.corrects_event_id is not None
                else None
            ),
            "event_id": self.event_id.value,
            "event_type": self.event_type.value,
            "guard": _binding_json(self.guard.hash_binding()),
            "order_id": self.order_id.to_json_value(),
            "predecessor_binding": (
                _binding_json(self.predecessor_binding)
                if self.predecessor_binding is not None
                else None
            ),
            "recorded_at": self.recorded_at.value,
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "stream_id": self.stream_id.value,
            "target_rep_participated": self.target_rep_participated,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIContactEvent(<closed>)"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DOIContactProjection:
    stream_id: EvidenceId
    order_id: DoiOrderId
    state: ContactState
    sequence: int
    head_event_binding: HashBinding | None
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-contact-projection/v1"

    def __post_init__(self) -> None:
        if (
            type(self.stream_id) is not EvidenceId
            or type(self.order_id) is not DoiOrderId
            or type(self.state) is not ContactState
            or type(self.sequence) is not int
            or self.sequence < 0
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_CONTACT_PROJECTION_INVALID")
        if self.sequence == 0:
            valid_head = self.head_event_binding is None
            valid_state = self.state is ContactState.NONE_OBSERVED
        else:
            valid_head = (
                type(self.head_event_binding) is HashBinding
                and self.head_event_binding.domain == DOIContactEvent.HASH_DOMAIN
            )
            valid_state = self.state is not ContactState.NONE_OBSERVED
        if not valid_head or not valid_state:
            raise DOIModelError("DOI_CONTACT_PROJECTION_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "head_event_binding": (
                _binding_json(self.head_event_binding)
                if self.head_event_binding is not None
                else None
            ),
            "order_id": self.order_id.to_json_value(),
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "state": self.state.value,
            "stream_id": self.stream_id.value,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIContactProjection(<closed>)"


@dataclass(frozen=True, slots=True)
class DOIContactHistory:
    projection: DOIContactProjection
    events: tuple[DOIContactEvent, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.projection) is not DOIContactProjection
            or type(self.events) is not tuple
            or any(type(event) is not DOIContactEvent for event in self.events)
            or any(
                event.stream_id != self.projection.stream_id
                or event.order_id != self.projection.order_id
                for event in self.events
            )
            or self.projection.sequence != len(self.events)
        ):
            raise DOIModelError("DOI_CONTACT_HISTORY_INVALID")
        expected_head = None if not self.events else self.events[-1].hash_binding()
        if self.projection.head_event_binding != expected_head:
            raise DOIModelError("DOI_CONTACT_HISTORY_INVALID")

    @classmethod
    def empty(
        cls,
        *,
        stream_id: EvidenceId,
        order_id: DoiOrderId,
    ) -> DOIContactHistory:
        return cls(
            DOIContactProjection(
                stream_id=stream_id,
                order_id=order_id,
                state=ContactState.NONE_OBSERVED,
                sequence=0,
                head_event_binding=None,
            )
        )


@dataclass(frozen=True, slots=True)
class DOIContactReduction:
    history: DOIContactHistory
    event: DOIContactEvent
    replayed: bool


def _contact_state(events: tuple[DOIContactEvent, ...]) -> ContactState:
    directions = {
        event.event_id: event.direction
        for event in events
        if event.event_type is not ContactEventType.CORRECTION
    }
    corrected: set[EvidenceId] = set()
    for event in events:
        if event.event_type is ContactEventType.CORRECTION:
            target = cast(EvidenceId, event.corrects_event_id)
            if target not in directions or target in corrected:
                raise DOIModelError("DOI_CONTACT_CORRECTION_TARGET_INVALID")
            directions[target] = event.direction
            corrected.add(target)
    values = set(directions.values())
    if ContactEventType.UNKNOWN in values:
        return ContactState.UNKNOWN
    if values == {ContactEventType.INBOUND, ContactEventType.OUTBOUND}:
        return ContactState.BIDIRECTIONAL_OBSERVED
    if values == {ContactEventType.INBOUND}:
        return ContactState.INBOUND_OBSERVED
    if values == {ContactEventType.OUTBOUND}:
        return ContactState.OUTBOUND_OBSERVED
    raise DOIModelError("DOI_CONTACT_PROJECTION_EMPTY_INVALID")


def reduce_contact(
    history: DOIContactHistory,
    event: DOIContactEvent,
) -> DOIContactReduction:
    if (
        type(history) is not DOIContactHistory
        or type(event) is not DOIContactEvent
        or event.stream_id != history.projection.stream_id
        or event.order_id != history.projection.order_id
    ):
        raise DOIModelError("DOI_CONTACT_REDUCER_INPUT_INVALID")
    replayed = _require_event_append(
        events=cast(tuple[object, ...], history.events),
        event=event,
        event_type=DOIContactEvent,
        event_id=event.event_id,
        guard=event.guard,
        sequence=event.sequence,
        predecessor=event.predecessor_binding,
        code="DOI_CONTACT_EVENT_CONFLICT",
    )
    if replayed:
        return DOIContactReduction(history, event, True)
    events = (*history.events, event)
    projection = DOIContactProjection(
        stream_id=event.stream_id,
        order_id=event.order_id,
        state=_contact_state(events),
        sequence=event.sequence,
        head_event_binding=event.hash_binding(),
    )
    return DOIContactReduction(DOIContactHistory(projection, events), event, False)


_CONTACT_WORKFLOW_EFFECTS = MappingProxyType(
    {
        ContactWorkflowEventType.CONTACT_REQUIRED_DERIVED: frozenset(
            {
                (
                    ContactWorkflowState.NOT_CONTACTED,
                    ContactWorkflowState.CONTACT_REQUIRED,
                )
            }
        ),
        ContactWorkflowEventType.CONTACT_ATTEMPT_RECORDED: frozenset(
            (
                state,
                ContactWorkflowState.CONTACT_ATTEMPTED,
            )
            for state in (
                ContactWorkflowState.NOT_CONTACTED,
                ContactWorkflowState.CONTACT_REQUIRED,
                ContactWorkflowState.CONTACT_ATTEMPTED,
                ContactWorkflowState.AWAITING_CUSTOMER,
                ContactWorkflowState.CUSTOMER_DECLINED,
                ContactWorkflowState.NO_RESPONSE,
            )
        ),
        ContactWorkflowEventType.AWAITING_CUSTOMER_RECORDED: frozenset(
            {
                (
                    ContactWorkflowState.CONTACT_ATTEMPTED,
                    ContactWorkflowState.AWAITING_CUSTOMER,
                )
            }
        ),
        ContactWorkflowEventType.CUSTOMER_APPROVAL_RECORDED: frozenset(
            (
                state,
                ContactWorkflowState.CUSTOMER_APPROVED,
            )
            for state in (
                ContactWorkflowState.CONTACT_ATTEMPTED,
                ContactWorkflowState.AWAITING_CUSTOMER,
            )
        ),
        ContactWorkflowEventType.CUSTOMER_DECLINE_RECORDED: frozenset(
            (
                state,
                ContactWorkflowState.CUSTOMER_DECLINED,
            )
            for state in (
                ContactWorkflowState.CONTACT_ATTEMPTED,
                ContactWorkflowState.AWAITING_CUSTOMER,
                ContactWorkflowState.CUSTOMER_APPROVED,
            )
        ),
        ContactWorkflowEventType.NO_RESPONSE_RECORDED: frozenset(
            {
                (
                    ContactWorkflowState.AWAITING_CUSTOMER,
                    ContactWorkflowState.NO_RESPONSE,
                )
            }
        ),
    }
)

@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class ContactWorkflowEvent:
    event_id: EvidenceId
    stream_id: EvidenceId
    action_context: DOIActionContext
    prior_state: ContactWorkflowState
    resulting_state: ContactWorkflowState
    event_type: ContactWorkflowEventType
    evaluation: DOIEvaluation | None
    human_authority: HumanAuthorityGrant | None
    contact_occurred_at: CanonicalTimestamp | None
    recorded_at: CanonicalTimestamp
    sequence: int
    predecessor_binding: HashBinding | None
    guard: DOIOccurrenceGuard
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-contact-state-event/v1"

    def __post_init__(self) -> None:
        if (
            type(self.event_id) is not EvidenceId
            or type(self.stream_id) is not EvidenceId
            or type(self.action_context) is not DOIActionContext
            or self.action_context.state is not ActionContextState.OPEN
            or self.action_context.opportunity_id is None
            or type(self.prior_state) is not ContactWorkflowState
            or type(self.resulting_state) is not ContactWorkflowState
            or type(self.event_type) is not ContactWorkflowEventType
            or (
                self.prior_state,
                self.resulting_state,
            )
            not in _CONTACT_WORKFLOW_EFFECTS[self.event_type]
            or type(self.recorded_at) is not CanonicalTimestamp
            or type(self.guard) is not DOIOccurrenceGuard
            or self.guard.guard_id != self.event_id
            or self.guard.owner_id != self.stream_id
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_CONTACT_WORKFLOW_EVENT_INVALID")
        if self.event_type is ContactWorkflowEventType.CONTACT_REQUIRED_DERIVED:
            if (
                type(self.evaluation) is not DOIEvaluation
                or self.human_authority is not None
                or self.contact_occurred_at is not None
                or self.evaluation.order_id != self.action_context.order_id
                or self.evaluation.evaluation_id
                != self.action_context.evaluation_id
                or self.action_context.opportunity_id
                not in {
                    opportunity.opportunity_id
                    for opportunity in self.evaluation.opportunities
                }
            ):
                raise DOIModelError("DOI_CONTACT_WORKFLOW_SYSTEM_EVIDENCE_INVALID")
        else:
            if (
                self.evaluation is not None
                or type(self.human_authority) is not HumanAuthorityGrant
                or type(self.contact_occurred_at) is not CanonicalTimestamp
                or self.human_authority.action_context_id
                != self.action_context.action_context_id
                or self.human_authority.action_context_binding
                != self.action_context.hash_binding()
                or self.guard.source != self.human_authority.source
                or _timestamp_key(self.contact_occurred_at)
                < _timestamp_key(self.human_authority.granted_at)
            ):
                raise DOIModelError("DOI_CONTACT_WORKFLOW_HUMAN_EVIDENCE_INVALID")
            if _timestamp_key(self.recorded_at) < _timestamp_key(
                self.contact_occurred_at
            ):
                raise DOIModelError("DOI_CONTACT_WORKFLOW_TIME_INVALID")
        _validate_event_position(
            self.sequence,
            self.predecessor_binding,
            event_domain=self.HASH_DOMAIN,
            code="DOI_CONTACT_WORKFLOW_EVENT_POSITION_INVALID",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "action_context": _binding_json(self.action_context.hash_binding()),
            "contact_occurred_at": (
                self.contact_occurred_at.value
                if self.contact_occurred_at is not None
                else None
            ),
            "evaluation": (
                _binding_json(self.evaluation.hash_binding())
                if self.evaluation is not None
                else None
            ),
            "event_id": self.event_id.value,
            "event_type": self.event_type.value,
            "guard": _binding_json(self.guard.hash_binding()),
            "human_authority": (
                _binding_json(self.human_authority.hash_binding())
                if self.human_authority is not None
                else None
            ),
            "predecessor_binding": (
                _binding_json(self.predecessor_binding)
                if self.predecessor_binding is not None
                else None
            ),
            "prior_state": self.prior_state.value,
            "recorded_at": self.recorded_at.value,
            "resulting_state": self.resulting_state.value,
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "stream_id": self.stream_id.value,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "ContactWorkflowEvent(<closed>)"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class ContactWorkflowProjection:
    stream_id: EvidenceId
    action_context_id: EvidenceId
    action_context_binding: HashBinding
    state: ContactWorkflowState
    sequence: int
    head_event_binding: HashBinding | None
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-contact-state-projection/v1"

    def __post_init__(self) -> None:
        if (
            type(self.stream_id) is not EvidenceId
            or type(self.action_context_id) is not EvidenceId
            or type(self.action_context_binding) is not HashBinding
            or self.action_context_binding.domain != DOIActionContext.HASH_DOMAIN
            or type(self.state) is not ContactWorkflowState
            or type(self.sequence) is not int
            or self.sequence < 0
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_CONTACT_WORKFLOW_PROJECTION_INVALID")
        if self.sequence == 0:
            if (
                self.state is not ContactWorkflowState.NOT_CONTACTED
                or self.head_event_binding is not None
            ):
                raise DOIModelError("DOI_CONTACT_WORKFLOW_PROJECTION_INVALID")
        elif (
            type(self.head_event_binding) is not HashBinding
            or self.head_event_binding.domain != ContactWorkflowEvent.HASH_DOMAIN
        ):
            raise DOIModelError("DOI_CONTACT_WORKFLOW_PROJECTION_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "action_context_binding": _binding_json(self.action_context_binding),
            "action_context_id": self.action_context_id.value,
            "head_event_binding": (
                _binding_json(self.head_event_binding)
                if self.head_event_binding is not None
                else None
            ),
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "state": self.state.value,
            "stream_id": self.stream_id.value,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "ContactWorkflowProjection(<closed>)"


@dataclass(frozen=True, slots=True)
class ContactWorkflowHistory:
    stream_id: EvidenceId
    action_context: DOIActionContext
    projection: ContactWorkflowProjection
    events: tuple[ContactWorkflowEvent, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.stream_id) is not EvidenceId
            or type(self.action_context) is not DOIActionContext
            or self.action_context.state is not ActionContextState.OPEN
            or type(self.projection) is not ContactWorkflowProjection
            or self.projection.stream_id != self.stream_id
            or self.projection.action_context_id
            != self.action_context.action_context_id
            or self.projection.action_context_binding
            != self.action_context.hash_binding()
            or type(self.events) is not tuple
            or any(type(event) is not ContactWorkflowEvent for event in self.events)
            or any(
                event.stream_id != self.stream_id
                or event.action_context != self.action_context
                for event in self.events
            )
            or self.projection.sequence != len(self.events)
        ):
            raise DOIModelError("DOI_CONTACT_WORKFLOW_HISTORY_INVALID")
        expected_head = None if not self.events else self.events[-1].hash_binding()
        if self.projection.head_event_binding != expected_head:
            raise DOIModelError("DOI_CONTACT_WORKFLOW_HISTORY_INVALID")

    @classmethod
    def empty(
        cls,
        *,
        stream_id: EvidenceId,
        action_context: DOIActionContext,
    ) -> ContactWorkflowHistory:
        return cls(
            stream_id=stream_id,
            action_context=action_context,
            projection=ContactWorkflowProjection(
                stream_id=stream_id,
                action_context_id=action_context.action_context_id,
                action_context_binding=action_context.hash_binding(),
                state=ContactWorkflowState.NOT_CONTACTED,
                sequence=0,
                head_event_binding=None,
            ),
        )


@dataclass(frozen=True, slots=True)
class ContactWorkflowReduction:
    history: ContactWorkflowHistory
    event: ContactWorkflowEvent
    replayed: bool


def reduce_contact_workflow(
    history: ContactWorkflowHistory,
    event: ContactWorkflowEvent,
) -> ContactWorkflowReduction:
    if (
        type(history) is not ContactWorkflowHistory
        or type(event) is not ContactWorkflowEvent
        or event.stream_id != history.stream_id
        or event.action_context != history.action_context
    ):
        raise DOIModelError("DOI_CONTACT_WORKFLOW_REDUCER_INPUT_INVALID")
    replayed = _require_event_append(
        events=cast(tuple[object, ...], history.events),
        event=event,
        event_type=ContactWorkflowEvent,
        event_id=event.event_id,
        guard=event.guard,
        sequence=event.sequence,
        predecessor=event.predecessor_binding,
        code="DOI_CONTACT_WORKFLOW_EVENT_CONFLICT",
    )
    if replayed:
        return ContactWorkflowReduction(history, event, True)
    if event.prior_state is not history.projection.state:
        raise DOIModelError("DOI_CONTACT_WORKFLOW_PRIOR_STATE_INVALID")
    projection = ContactWorkflowProjection(
        stream_id=history.stream_id,
        action_context_id=history.action_context.action_context_id,
        action_context_binding=history.action_context.hash_binding(),
        state=event.resulting_state,
        sequence=event.sequence,
        head_event_binding=event.hash_binding(),
    )
    updated = ContactWorkflowHistory(
        stream_id=history.stream_id,
        action_context=history.action_context,
        projection=projection,
        events=(*history.events, event),
    )
    return ContactWorkflowReduction(updated, event, False)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DOIWWCEvent:
    event_id: EvidenceId
    stream_id: EvidenceId
    order_id: DoiOrderId
    event_type: WWCEventType
    finding: WWCFinding
    corrects_event_id: EvidenceId | None
    recorded_at: CanonicalTimestamp
    sequence: int
    predecessor_binding: HashBinding | None
    guard: DOIOccurrenceGuard
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-wwc-event/v1"

    def __post_init__(self) -> None:
        if (
            type(self.event_id) is not EvidenceId
            or type(self.stream_id) is not EvidenceId
            or type(self.order_id) is not DoiOrderId
            or type(self.event_type) is not WWCEventType
            or type(self.finding) is not WWCFinding
            or self.finding.source.object_id != self.order_id.value
            or type(self.recorded_at) is not CanonicalTimestamp
            or type(self.guard) is not DOIOccurrenceGuard
            or self.guard.guard_id != self.event_id
            or self.guard.owner_id != self.stream_id
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_WWC_EVENT_INVALID")
        if self.event_type is WWCEventType.OBSERVED:
            if self.corrects_event_id is not None:
                raise DOIModelError("DOI_WWC_CORRECTION_INVALID")
        elif type(self.corrects_event_id) is not EvidenceId:
            raise DOIModelError("DOI_WWC_CORRECTION_INVALID")
        _validate_event_position(
            self.sequence,
            self.predecessor_binding,
            event_domain=self.HASH_DOMAIN,
            code="DOI_WWC_EVENT_POSITION_INVALID",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "corrects_event_id": (
                self.corrects_event_id.value
                if self.corrects_event_id is not None
                else None
            ),
            "event_id": self.event_id.value,
            "event_type": self.event_type.value,
            "finding": _binding_json(self.finding.hash_binding()),
            "guard": _binding_json(self.guard.hash_binding()),
            "order_id": self.order_id.to_json_value(),
            "predecessor_binding": (
                _binding_json(self.predecessor_binding)
                if self.predecessor_binding is not None
                else None
            ),
            "recorded_at": self.recorded_at.value,
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "stream_id": self.stream_id.value,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIWWCEvent(<closed>)"


def _wwc_projection_state(finding: WWCFinding) -> WWCProjectionState:
    if finding.presence is FindingPresenceV2.UNKNOWN:
        return WWCProjectionState.AUTHOR_AND_TIMING_UNCERTAIN
    if finding.presence in {
        FindingPresenceV2.NOT_PRESENT,
        FindingPresenceV2.NOT_APPLICABLE,
    }:
        return WWCProjectionState.NOT_APPLICABLE
    author = _known_value(cast(ObservedTaggedValue[object], finding.author_relation))
    timing = _known_value(cast(ObservedTaggedValue[object], finding.timing_state))
    marker_known = type(finding.marker) is KnownObservedValue
    observed_at_known = type(finding.observed_at) is KnownObservedValue
    author_uncertain = author not in {
        WWCAuthorRelation.TARGET_REP.value,
        WWCAuthorRelation.OTHER_REP.value,
    }
    timing_uncertain = (
        timing not in {WWCTimingState.ACTIVE.value, WWCTimingState.EXPIRED.value}
        or not observed_at_known
    )
    if not marker_known:
        author_uncertain = True
        timing_uncertain = True
    if author_uncertain and timing_uncertain:
        return WWCProjectionState.AUTHOR_AND_TIMING_UNCERTAIN
    if author_uncertain:
        return WWCProjectionState.AUTHOR_UNCERTAIN
    if timing_uncertain:
        return WWCProjectionState.TIMING_UNCERTAIN
    if timing == WWCTimingState.ACTIVE.value:
        if author == WWCAuthorRelation.TARGET_REP.value:
            return WWCProjectionState.ACTIVE_SELF
        return WWCProjectionState.ACTIVE_OTHER_REP
    if author == WWCAuthorRelation.OTHER_REP.value:
        return WWCProjectionState.EXPIRED_OTHER_REP
    return WWCProjectionState.NOT_APPLICABLE


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DOIWWCProjection:
    stream_id: EvidenceId
    order_id: DoiOrderId
    state: WWCProjectionState
    current_finding: WWCFinding
    sequence: int
    head_event_binding: HashBinding
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-wwc-projection/v1"

    def __post_init__(self) -> None:
        if (
            type(self.stream_id) is not EvidenceId
            or type(self.order_id) is not DoiOrderId
            or type(self.state) is not WWCProjectionState
            or type(self.current_finding) is not WWCFinding
            or self.current_finding.source.object_id != self.order_id.value
            or self.state is not _wwc_projection_state(self.current_finding)
            or type(self.sequence) is not int
            or self.sequence < 1
            or type(self.head_event_binding) is not HashBinding
            or self.head_event_binding.domain != DOIWWCEvent.HASH_DOMAIN
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_WWC_PROJECTION_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "current_finding": _binding_json(self.current_finding.hash_binding()),
            "head_event_binding": _binding_json(self.head_event_binding),
            "order_id": self.order_id.to_json_value(),
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "state": self.state.value,
            "stream_id": self.stream_id.value,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIWWCProjection(<closed>)"


@dataclass(frozen=True, slots=True)
class DOIWWCHistory:
    stream_id: EvidenceId
    order_id: DoiOrderId
    projection: DOIWWCProjection | None = None
    events: tuple[DOIWWCEvent, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.stream_id) is not EvidenceId
            or type(self.order_id) is not DoiOrderId
            or type(self.events) is not tuple
            or any(type(event) is not DOIWWCEvent for event in self.events)
            or any(
                event.stream_id != self.stream_id or event.order_id != self.order_id
                for event in self.events
            )
        ):
            raise DOIModelError("DOI_WWC_HISTORY_INVALID")
        if not self.events:
            if self.projection is not None:
                raise DOIModelError("DOI_WWC_HISTORY_INVALID")
        elif (
            type(self.projection) is not DOIWWCProjection
            or self.projection.sequence != len(self.events)
            or self.projection.head_event_binding != self.events[-1].hash_binding()
        ):
            raise DOIModelError("DOI_WWC_HISTORY_INVALID")


@dataclass(frozen=True, slots=True)
class DOIWWCReduction:
    history: DOIWWCHistory
    event: DOIWWCEvent
    replayed: bool


def reduce_wwc(history: DOIWWCHistory, event: DOIWWCEvent) -> DOIWWCReduction:
    if (
        type(history) is not DOIWWCHistory
        or type(event) is not DOIWWCEvent
        or event.stream_id != history.stream_id
        or event.order_id != history.order_id
    ):
        raise DOIModelError("DOI_WWC_REDUCER_INPUT_INVALID")
    replayed = _require_event_append(
        events=cast(tuple[object, ...], history.events),
        event=event,
        event_type=DOIWWCEvent,
        event_id=event.event_id,
        guard=event.guard,
        sequence=event.sequence,
        predecessor=event.predecessor_binding,
        code="DOI_WWC_EVENT_CONFLICT",
    )
    if replayed:
        return DOIWWCReduction(history, event, True)
    if event.event_type is WWCEventType.CORRECTED:
        if not history.events or event.corrects_event_id != history.events[-1].event_id:
            raise DOIModelError("DOI_WWC_CORRECTION_TARGET_INVALID")
    projection = DOIWWCProjection(
        stream_id=event.stream_id,
        order_id=event.order_id,
        state=_wwc_projection_state(event.finding),
        current_finding=event.finding,
        sequence=event.sequence,
        head_event_binding=event.hash_binding(),
    )
    updated = DOIWWCHistory(
        stream_id=history.stream_id,
        order_id=history.order_id,
        projection=projection,
        events=(*history.events, event),
    )
    return DOIWWCReduction(updated, event, False)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DOIDedupeEvent:
    event_id: EvidenceId
    stream_id: EvidenceId
    order_id: DoiOrderId
    event_type: DedupeEventType
    finding: DedupeFinding | None
    evaluation: DOIEvaluation | None
    human_fact: StructuredHumanFact | None
    verification: DedupeVerificationFact | None
    recorded_at: CanonicalTimestamp
    sequence: int
    predecessor_binding: HashBinding | None
    guard: DOIOccurrenceGuard
    corrects_event_id: EvidenceId | None = None
    corrected_human_fact_binding: HashBinding | None = None
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-dedupe-event/v1"

    def __post_init__(self) -> None:
        if (
            type(self.event_id) is not EvidenceId
            or type(self.stream_id) is not EvidenceId
            or type(self.order_id) is not DoiOrderId
            or type(self.event_type) is not DedupeEventType
            or type(self.recorded_at) is not CanonicalTimestamp
            or type(self.guard) is not DOIOccurrenceGuard
            or self.guard.guard_id != self.event_id
            or self.guard.owner_id != self.stream_id
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_DEDUPE_EVENT_INVALID")
        payload_types = (
            self.finding is not None,
            self.evaluation is not None,
            self.human_fact is not None,
            self.verification is not None,
        )
        if sum(payload_types) != 1:
            raise DOIModelError("DOI_DEDUPE_EVENT_PAYLOAD_INVALID")
        if self.event_type is DedupeEventType.SOURCE_OBSERVED:
            valid_payload = (
                type(self.finding) is DedupeFinding
                and self.finding.source.object_id == self.order_id.value
            )
        elif self.event_type in {
            DedupeEventType.CANDIDATE_IDENTIFIED,
            DedupeEventType.ANALYSIS_INCOMPLETE,
            DedupeEventType.CANDIDATE_WITHDRAWN,
            DedupeEventType.ELIGIBILITY_RETURNED,
        }:
            valid_payload = (
                type(self.evaluation) is DOIEvaluation
                and self.evaluation.order_id == self.order_id
            )
            expected_reason = {
                DedupeEventType.CANDIDATE_IDENTIFIED: "RC-058",
                DedupeEventType.ANALYSIS_INCOMPLETE: "RC-059",
                DedupeEventType.CANDIDATE_WITHDRAWN: "RC-059",
            }.get(self.event_type)
            if expected_reason is not None:
                valid_payload = valid_payload and expected_reason in {
                    reason.code for reason in self.evaluation.reasons.reasons
                }
        elif self.event_type in {
            DedupeEventType.HUMAN_APPROVED,
            DedupeEventType.HUMAN_REJECTED,
        }:
            expected_result = (
                HumanFactResultCode.APPROVED
                if self.event_type is DedupeEventType.HUMAN_APPROVED
                else HumanFactResultCode.REJECTED
            )
            valid_payload = (
                type(self.human_fact) is StructuredHumanFact
                and self.human_fact.order_id == self.order_id
                and self.human_fact.usage_kind is HumanFactUsageKind.DEDUPE_DECISION
                and self.human_fact.result_code is expected_result
            )
        else:
            valid_payload = (
                type(self.verification) is DedupeVerificationFact
                and self.verification.order_id == self.order_id
                and (
                    self.recorded_at.epoch_seconds,
                    self.recorded_at.nanosecond,
                )
                >= (
                    self.verification.verified_snapshot.source_observed_at.epoch_seconds,
                    self.verification.verified_snapshot.source_observed_at.nanosecond,
                )
            )
        if not valid_payload:
            raise DOIModelError("DOI_DEDUPE_EVENT_PAYLOAD_INVALID")
        correction_binding = self.corrected_human_fact_binding
        correction_partition_valid = (
            self.event_type is DedupeEventType.HUMAN_REJECTED
            and (
                (
                    self.corrects_event_id is None
                    and correction_binding is None
                )
                or (
                    type(self.corrects_event_id) is EvidenceId
                    and type(correction_binding) is HashBinding
                    and correction_binding.domain
                    == StructuredHumanFact.HASH_DOMAIN
                )
            )
        ) or (
            self.event_type is not DedupeEventType.HUMAN_REJECTED
            and self.corrects_event_id is None
            and correction_binding is None
        )
        if not correction_partition_valid:
            raise DOIModelError("DOI_DEDUPE_CORRECTION_BINDING_INVALID")
        _validate_event_position(
            self.sequence,
            self.predecessor_binding,
            event_domain=self.HASH_DOMAIN,
            code="DOI_DEDUPE_EVENT_POSITION_INVALID",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "corrected_human_fact_binding": (
                _binding_json(self.corrected_human_fact_binding)
                if self.corrected_human_fact_binding is not None
                else None
            ),
            "corrects_event_id": (
                self.corrects_event_id.value
                if self.corrects_event_id is not None
                else None
            ),
            "evaluation": (
                _binding_json(self.evaluation.hash_binding())
                if self.evaluation is not None
                else None
            ),
            "event_id": self.event_id.value,
            "event_type": self.event_type.value,
            "finding": (
                _binding_json(self.finding.hash_binding())
                if self.finding is not None
                else None
            ),
            "guard": _binding_json(self.guard.hash_binding()),
            "human_fact": (
                _binding_json(self.human_fact.hash_binding())
                if self.human_fact is not None
                else None
            ),
            "order_id": self.order_id.to_json_value(),
            "predecessor_binding": (
                _binding_json(self.predecessor_binding)
                if self.predecessor_binding is not None
                else None
            ),
            "recorded_at": self.recorded_at.value,
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "stream_id": self.stream_id.value,
            "verification": (
                _binding_json(self.verification.hash_binding())
                if self.verification is not None
                else None
            ),
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIDedupeEvent(<closed>)"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DOIDedupeProjection:
    stream_id: EvidenceId
    order_id: DoiOrderId
    state: DedupeState
    source_finding_binding: HashBinding | None
    decision_evaluation_binding: HashBinding | None
    human_fact_binding: HashBinding | None
    verification_binding: HashBinding | None
    sequence: int
    head_event_binding: HashBinding | None
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-dedupe-projection/v1"

    def __post_init__(self) -> None:
        if (
            type(self.stream_id) is not EvidenceId
            or type(self.order_id) is not DoiOrderId
            or self.state not in {
                DedupeState.NOT_PRESENT,
                DedupeState.NOT_CANDIDATE,
                DedupeState.CANDIDATE,
                DedupeState.INCOMPLETE,
                DedupeState.APPROVED_AWAITING_VERIFICATION,
                DedupeState.REJECTED,
                DedupeState.CONFIRMED,
            }
            or type(self.sequence) is not int
            or self.sequence < 0
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_DEDUPE_PROJECTION_INVALID")
        domains = (
            (self.source_finding_binding, DedupeFinding.HASH_DOMAIN),
            (self.decision_evaluation_binding, DOIEvaluation.HASH_DOMAIN),
            (self.human_fact_binding, StructuredHumanFact.HASH_DOMAIN),
            (self.verification_binding, DedupeVerificationFact.HASH_DOMAIN),
        )
        if any(
            binding is not None
            and (type(binding) is not HashBinding or binding.domain != domain)
            for binding, domain in domains
        ):
            raise DOIModelError("DOI_DEDUPE_PROJECTION_BINDING_INVALID")
        if self.sequence == 0:
            valid_head = self.head_event_binding is None
            empty = all(binding is None for binding, _ in domains)
            if (
                not valid_head
                or not empty
                or self.state is not DedupeState.NOT_CANDIDATE
            ):
                raise DOIModelError("DOI_DEDUPE_PROJECTION_PARTITION_INVALID")
        elif (
            type(self.head_event_binding) is not HashBinding
            or self.head_event_binding.domain != DOIDedupeEvent.HASH_DOMAIN
        ):
            raise DOIModelError("DOI_DEDUPE_PROJECTION_PARTITION_INVALID")

    def to_dict(self) -> dict[str, object]:
        def optional(binding: HashBinding | None) -> dict[str, str] | None:
            return None if binding is None else _binding_json(binding)

        return {
            "decision_evaluation_binding": optional(
                self.decision_evaluation_binding
            ),
            "head_event_binding": optional(self.head_event_binding),
            "human_fact_binding": optional(self.human_fact_binding),
            "order_id": self.order_id.to_json_value(),
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "source_finding_binding": optional(self.source_finding_binding),
            "state": self.state.value,
            "stream_id": self.stream_id.value,
            "verification_binding": optional(self.verification_binding),
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIDedupeProjection(<closed>)"


@dataclass(frozen=True, slots=True)
class DOIDedupeHistory:
    projection: DOIDedupeProjection
    events: tuple[DOIDedupeEvent, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.projection) is not DOIDedupeProjection
            or type(self.events) is not tuple
            or any(type(event) is not DOIDedupeEvent for event in self.events)
            or any(
                event.stream_id != self.projection.stream_id
                or event.order_id != self.projection.order_id
                for event in self.events
            )
            or self.projection.sequence != len(self.events)
        ):
            raise DOIModelError("DOI_DEDUPE_HISTORY_INVALID")
        expected_head = None if not self.events else self.events[-1].hash_binding()
        if self.projection.head_event_binding != expected_head:
            raise DOIModelError("DOI_DEDUPE_HISTORY_INVALID")

    @classmethod
    def empty(
        cls,
        *,
        stream_id: EvidenceId,
        order_id: DoiOrderId,
    ) -> DOIDedupeHistory:
        return cls(
            DOIDedupeProjection(
                stream_id=stream_id,
                order_id=order_id,
                state=DedupeState.NOT_CANDIDATE,
                source_finding_binding=None,
                decision_evaluation_binding=None,
                human_fact_binding=None,
                verification_binding=None,
                sequence=0,
                head_event_binding=None,
            )
        )


@dataclass(frozen=True, slots=True)
class DOIDedupeReduction:
    history: DOIDedupeHistory
    event: DOIDedupeEvent
    replayed: bool


def reduce_dedupe(
    history: DOIDedupeHistory,
    event: DOIDedupeEvent,
) -> DOIDedupeReduction:
    if (
        type(history) is not DOIDedupeHistory
        or type(event) is not DOIDedupeEvent
        or event.stream_id != history.projection.stream_id
        or event.order_id != history.projection.order_id
    ):
        raise DOIModelError("DOI_DEDUPE_REDUCER_INPUT_INVALID")
    replayed = _require_event_append(
        events=cast(tuple[object, ...], history.events),
        event=event,
        event_type=DOIDedupeEvent,
        event_id=event.event_id,
        guard=event.guard,
        sequence=event.sequence,
        predecessor=event.predecessor_binding,
        code="DOI_DEDUPE_EVENT_CONFLICT",
    )
    if replayed:
        return DOIDedupeReduction(history, event, True)
    prior = history.projection
    next_state = prior.state
    finding = prior.source_finding_binding
    evaluation = prior.decision_evaluation_binding
    human = prior.human_fact_binding
    verification = prior.verification_binding
    if event.event_type is DedupeEventType.SOURCE_OBSERVED:
        finding = cast(DedupeFinding, event.finding).hash_binding()
    elif event.event_type is DedupeEventType.CANDIDATE_IDENTIFIED:
        if prior.state not in {
            DedupeState.NOT_CANDIDATE,
            DedupeState.INCOMPLETE,
            DedupeState.REJECTED,
        }:
            raise DOIModelError("DOI_DEDUPE_STATE_CONFLICT")
        candidate_evaluation = cast(DOIEvaluation, event.evaluation).hash_binding()
        if (
            prior.state is DedupeState.REJECTED
            and candidate_evaluation == prior.decision_evaluation_binding
        ):
            raise DOIModelError("DOI_DEDUPE_FRESH_EVALUATION_REQUIRED")
        next_state = DedupeState.CANDIDATE
        evaluation = candidate_evaluation
        human = None
        verification = None
    elif event.event_type is DedupeEventType.ANALYSIS_INCOMPLETE:
        if prior.state is DedupeState.CONFIRMED:
            raise DOIModelError("DOI_DEDUPE_STATE_CONFLICT")
        next_state = DedupeState.INCOMPLETE
        evaluation = cast(DOIEvaluation, event.evaluation).hash_binding()
    elif event.event_type is DedupeEventType.HUMAN_APPROVED:
        if prior.state is not DedupeState.CANDIDATE:
            raise DOIModelError("DOI_DEDUPE_HUMAN_DECISION_PREMATURE")
        next_state = DedupeState.APPROVED_AWAITING_VERIFICATION
        human = cast(StructuredHumanFact, event.human_fact).hash_binding()
    elif event.event_type is DedupeEventType.HUMAN_REJECTED:
        prior_decision = (
            history.events[-1].human_fact if history.events else None
        )
        new_decision = cast(StructuredHumanFact, event.human_fact)
        corrected_approval = (
            prior.state is DedupeState.APPROVED_AWAITING_VERIFICATION
            and bool(history.events)
            and history.events[-1].event_type is DedupeEventType.HUMAN_APPROVED
            and type(prior_decision) is StructuredHumanFact
            and event.corrects_event_id == history.events[-1].event_id
            and event.corrected_human_fact_binding == human
            and new_decision.action_context_id
            == prior_decision.action_context_id
            and new_decision.action_context.hash_binding()
            == prior_decision.action_context.hash_binding()
            and new_decision.evaluation_id == prior_decision.evaluation_id
            and new_decision.order_id == prior_decision.order_id
            and new_decision.usage_kind
            is HumanFactUsageKind.DEDUPE_DECISION
            and prior_decision.usage_kind
            is HumanFactUsageKind.DEDUPE_DECISION
        )
        initial_rejection = (
            prior.state is DedupeState.CANDIDATE
            and event.corrects_event_id is None
            and event.corrected_human_fact_binding is None
        )
        if not initial_rejection and not corrected_approval:
            raise DOIModelError("DOI_DEDUPE_HUMAN_DECISION_PREMATURE")
        next_state = DedupeState.REJECTED
        human = cast(StructuredHumanFact, event.human_fact).hash_binding()
        verification = None
    elif event.event_type is DedupeEventType.CANDIDATE_WITHDRAWN:
        if prior.state not in {
            DedupeState.CANDIDATE,
            DedupeState.APPROVED_AWAITING_VERIFICATION,
            DedupeState.REJECTED,
        }:
            raise DOIModelError("DOI_DEDUPE_STATE_CONFLICT")
        next_state = DedupeState.NOT_CANDIDATE
        evaluation = cast(DOIEvaluation, event.evaluation).hash_binding()
        human = None
        verification = None
    elif event.event_type is DedupeEventType.ELIGIBILITY_RETURNED:
        if prior.state is not DedupeState.CONFIRMED:
            raise DOIModelError("DOI_DEDUPE_STATE_CONFLICT")
        next_state = DedupeState.NOT_CANDIDATE
        evaluation = cast(DOIEvaluation, event.evaluation).hash_binding()
        human = None
        verification = None
    else:
        verified = cast(DedupeVerificationFact, event.verification)
        if (
            prior.state is not DedupeState.APPROVED_AWAITING_VERIFICATION
            or finding is None
            or verified.prior_snapshot.dedupe_finding.hash_binding() != finding
            or verified.prior_projection_binding != prior.hash_binding()
            or verified.approved_human_fact_binding != human
        ):
            raise DOIModelError("DOI_DEDUPE_VERIFICATION_PREMATURE")
        next_state = DedupeState.CONFIRMED
        finding = verified.verified_snapshot.dedupe_finding.hash_binding()
        verification = verified.hash_binding()
    projection = DOIDedupeProjection(
        stream_id=event.stream_id,
        order_id=event.order_id,
        state=next_state,
        source_finding_binding=finding,
        decision_evaluation_binding=evaluation,
        human_fact_binding=human,
        verification_binding=verification,
        sequence=event.sequence,
        head_event_binding=event.hash_binding(),
    )
    updated = DOIDedupeHistory(projection, (*history.events, event))
    return DOIDedupeReduction(updated, event, False)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DOIHumanFactEvent:
    event_id: EvidenceId
    stream_id: EvidenceId
    event_type: HumanFactEventType
    fact: StructuredHumanFact
    corrects_event_id: EvidenceId | None
    recorded_at: CanonicalTimestamp
    sequence: int
    predecessor_binding: HashBinding | None
    guard: DOIOccurrenceGuard
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-human-fact-event/v1"

    def __post_init__(self) -> None:
        if (
            type(self.event_id) is not EvidenceId
            or type(self.stream_id) is not EvidenceId
            or type(self.event_type) is not HumanFactEventType
            or type(self.fact) is not StructuredHumanFact
            or type(self.recorded_at) is not CanonicalTimestamp
            or type(self.guard) is not DOIOccurrenceGuard
            or self.guard.guard_id != self.event_id
            or self.guard.owner_id != self.stream_id
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_HUMAN_FACT_EVENT_INVALID")
        if self.event_type is HumanFactEventType.RECORDED:
            if self.corrects_event_id is not None:
                raise DOIModelError("DOI_HUMAN_FACT_CORRECTION_INVALID")
        elif type(self.corrects_event_id) is not EvidenceId:
            raise DOIModelError("DOI_HUMAN_FACT_CORRECTION_INVALID")
        _validate_event_position(
            self.sequence,
            self.predecessor_binding,
            event_domain=self.HASH_DOMAIN,
            code="DOI_HUMAN_FACT_EVENT_POSITION_INVALID",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "corrects_event_id": (
                self.corrects_event_id.value
                if self.corrects_event_id is not None
                else None
            ),
            "event_id": self.event_id.value,
            "event_type": self.event_type.value,
            "fact": _binding_json(self.fact.hash_binding()),
            "guard": _binding_json(self.guard.hash_binding()),
            "predecessor_binding": (
                _binding_json(self.predecessor_binding)
                if self.predecessor_binding is not None
                else None
            ),
            "recorded_at": self.recorded_at.value,
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "stream_id": self.stream_id.value,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIHumanFactEvent(<closed>)"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DOIHumanFactProjection:
    stream_id: EvidenceId
    current_fact: StructuredHumanFact
    sequence: int
    head_event_binding: HashBinding
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-human-fact-projection/v1"

    def __post_init__(self) -> None:
        if (
            type(self.stream_id) is not EvidenceId
            or type(self.current_fact) is not StructuredHumanFact
            or type(self.sequence) is not int
            or self.sequence < 1
            or type(self.head_event_binding) is not HashBinding
            or self.head_event_binding.domain != DOIHumanFactEvent.HASH_DOMAIN
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise DOIModelError("DOI_HUMAN_FACT_PROJECTION_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "current_fact": _binding_json(self.current_fact.hash_binding()),
            "head_event_binding": _binding_json(self.head_event_binding),
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "stream_id": self.stream_id.value,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIHumanFactProjection(<closed>)"


@dataclass(frozen=True, slots=True)
class DOIHumanFactHistory:
    stream_id: EvidenceId
    projection: DOIHumanFactProjection | None = None
    events: tuple[DOIHumanFactEvent, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.stream_id) is not EvidenceId
            or type(self.events) is not tuple
            or any(type(event) is not DOIHumanFactEvent for event in self.events)
            or any(event.stream_id != self.stream_id for event in self.events)
        ):
            raise DOIModelError("DOI_HUMAN_FACT_HISTORY_INVALID")
        if not self.events:
            if self.projection is not None:
                raise DOIModelError("DOI_HUMAN_FACT_HISTORY_INVALID")
        elif (
            type(self.projection) is not DOIHumanFactProjection
            or self.projection.sequence != len(self.events)
            or self.projection.head_event_binding != self.events[-1].hash_binding()
        ):
            raise DOIModelError("DOI_HUMAN_FACT_HISTORY_INVALID")


@dataclass(frozen=True, slots=True)
class DOIHumanFactReduction:
    history: DOIHumanFactHistory
    event: DOIHumanFactEvent
    replayed: bool


def reduce_human_fact(
    history: DOIHumanFactHistory,
    event: DOIHumanFactEvent,
) -> DOIHumanFactReduction:
    if (
        type(history) is not DOIHumanFactHistory
        or type(event) is not DOIHumanFactEvent
        or event.stream_id != history.stream_id
    ):
        raise DOIModelError("DOI_HUMAN_FACT_REDUCER_INPUT_INVALID")
    replayed = _require_event_append(
        events=cast(tuple[object, ...], history.events),
        event=event,
        event_type=DOIHumanFactEvent,
        event_id=event.event_id,
        guard=event.guard,
        sequence=event.sequence,
        predecessor=event.predecessor_binding,
        code="DOI_HUMAN_FACT_EVENT_CONFLICT",
    )
    if replayed:
        return DOIHumanFactReduction(history, event, True)
    prior = history.projection
    if prior is None:
        if event.event_type is not HumanFactEventType.RECORDED:
            raise DOIModelError("DOI_HUMAN_FACT_INITIAL_RECORD_REQUIRED")
    else:
        if (
            event.event_type is not HumanFactEventType.CORRECTED
            or event.corrects_event_id != history.events[-1].event_id
            or event.fact.fact_id == prior.current_fact.fact_id
            or event.fact.order_id != prior.current_fact.order_id
            or event.fact.evaluation_id != prior.current_fact.evaluation_id
            or event.fact.action_context_id != prior.current_fact.action_context_id
            or event.fact.usage_kind is not prior.current_fact.usage_kind
        ):
            raise DOIModelError("DOI_HUMAN_FACT_CORRECTION_CONFLICT")
    projection = DOIHumanFactProjection(
        stream_id=event.stream_id,
        current_fact=event.fact,
        sequence=event.sequence,
        head_event_binding=event.hash_binding(),
    )
    updated = DOIHumanFactHistory(
        stream_id=history.stream_id,
        projection=projection,
        events=(*history.events, event),
    )
    return DOIHumanFactReduction(updated, event, False)


def model_hash_contracts() -> MappingProxyType[str, str]:
    """Return the exact hash domain inventory for traceability/KAT generation."""

    return MappingProxyType(
        {
            cls.__name__: cls.HASH_DOMAIN
            for cls in (
                LineContinuityProof,
                DOILineItemSnapshot,
                WWCFinding,
                DedupeFinding,
                StructuredHumanFact,
                DedupeVerificationFact,
                DOIOrderSnapshot,
                DOIOpportunityScope,
                DOIMutualExclusionEvidence,
                AlternateCandidate,
                DOIOpportunity,
                DOIEvaluationInput,
                DOIExplanation,
                DOIEvaluation,
                DOICaseAdmissionProof,
                DOICaseSourceBinding,
                ActionContextOpeningAuthorization,
                DOIOccurrenceGuard,
                DOIActionContextObservationLink,
                DOIActionContextEvent,
                DOIActionContext,
                HumanAuthorityGrant,
                DOIContactEvent,
                DOIContactProjection,
                ContactWorkflowEvent,
                ContactWorkflowProjection,
                DOIWWCEvent,
                DOIWWCProjection,
                DOIDedupeEvent,
                DOIDedupeProjection,
                DOIHumanFactEvent,
                DOIHumanFactProjection,
            )
        }
        | {
            "ActionContextCompletionSource": (
                DOIActionContextEvent.COMPLETION_SOURCE_DOMAIN
            ),
            "ActionContextOpeningRequest": (
                ActionContextOpeningAuthorization.REQUEST_HASH_DOMAIN
            ),
            "DOIEvaluationOutput": DOIEvaluation.OUTPUT_DOMAIN,
            "DOIOpportunityIdentity": "doi-opportunity-id/v1",
            "DOIRulePackBinding": DOI_RULE_PACK_HASH_DOMAIN,
        }
    )


def _build_model_hash_fixture(
    *,
    action_context_only: bool,
) -> DOIActionContext | tuple[tuple[str, str, bytes, str], ...]:
    """Build the deterministic model KAT graph, optionally stopping at its exact context."""

    from dataclasses import replace
    from decimal import Decimal

    from synthetic_sales_assist.doi.evaluator import (
        evaluate_doi,
        opportunity_identity_binding,
    )
    from synthetic_sales_assist.doi.knowledge import (
        DOIAlternateObservation,
        DOIExactSKUObservation,
        candidate_from_relationship,
        create_relationship,
        exact_sku_candidate,
    )
    from synthetic_sales_assist.domain.identities import OrderId, RunId, SnapshotId
    from synthetic_sales_assist.domain.numeric import (
        CURRENCY_REGISTRY_VERSION,
        NonNegativeCount,
        PositiveOrdinal,
    )
    from synthetic_sales_assist.domain.records import (
        LineManifestEntry,
        RequiredSectionProof,
    )

    observed_at = CanonicalTimestamp("2026-08-20T14:15:16Z")
    verified_at = CanonicalTimestamp("2026-08-20T14:15:17Z")
    order_value = OrderId("SYN-ORDER-DOI-MODEL-KAT-0001")
    order_id = DoiOrderId(order_value)
    order_source = SourceRef.create(
        source_ref_id=EvidenceId("SYN-EVIDENCE-DOI-MODEL-KAT-ORDER-SOURCE"),
        source_kind=SourceKind.SYNTHETIC_ORDER_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_ORDER,
        object_id=order_value,
    )
    money = Money(Decimal("10.00"), "USD", CURRENCY_REGISTRY_VERSION, 2)

    def line_fixture(
        ordinal: int,
        availability: LineAvailability,
        quantity_state: QuantityAvailability,
        available_quantity: int,
    ) -> DOILineItemSnapshot:
        line_id = LineSnapshotId(
            EvidenceId(f"SYN-EVIDENCE-DOI-MODEL-KAT-LINE-{ordinal:04d}")
        )
        stable_id = EvidenceId(
            f"SYN-EVIDENCE-DOI-MODEL-KAT-STABLE-LINE-{ordinal:04d}"
        )
        return DOILineItemSnapshot(
            line_snapshot_id=line_id,
            stable_source_line_id=known_fact(stable_id),
            relevant_merchandise=True,
            activity=known_fact(LineActivity.ACTIVE),
            drop_ship_state=known_fact(DropShipState.NON_DS),
            availability=known_fact(availability),
            eta=known_fact(observed_at),
            ordered_quantity=known_fact(Quantity(2)),
            active_quantity=known_fact(Quantity(2)),
            canceled_quantity=known_fact(Quantity(0)),
            explicitly_available_quantity=known_fact(
                Quantity(available_quantity)
            ),
            quantity_availability=known_fact(quantity_state),
            es_number=known_fact(
                SkuId(f"SYN-SKU-DOI-MODEL-KAT-ES-{ordinal:04d}")
            ),
            mfg_number=known_fact(
                SkuId(f"SYN-SKU-DOI-MODEL-KAT-MFG-{ordinal:04d}")
            ),
            unit_value=known_fact(money),
            active_line_value=known_fact(money.multiply(PositiveQuantity(2))),
            line_sales_rep=known_fact(RepId("SYN-REP-DOI-MODEL-KAT-TARGET")),
            continuity=LineContinuityProof(
                state=LineContinuityState.VERIFIED,
                proof_type=ContinuityProofType.STABLE_SOURCE_LINE_ID,
                stable_source_line_id=stable_id,
                composite_binding=None,
            ),
            source=order_source,
        )

    lines = (
        line_fixture(
            1,
            LineAvailability.IN_STOCK,
            QuantityAvailability.FULL,
            2,
        ),
        line_fixture(
            2,
            LineAvailability.DELAYED,
            QuantityAvailability.NONE,
            0,
        ),
    )
    manifest = tuple(
        LineManifestEntry(
            line.line_snapshot_id.value,
            PositiveOrdinal(index),
            order_source,
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
    section_proofs = tuple(
        RequiredSectionProof.complete(
            section=section,
            source=order_source,
            observed_at=observed_at,
        )
        for section in WholeOrderCompletenessProof.REQUIRED_SECTIONS
    )
    completeness = WholeOrderCompletenessProof(
        requested_order_id=order_value,
        observed_order_id=order_value,
        schema=VersionBinding(
            "whole_order_completeness",
            WholeOrderCompletenessProof.SCHEMA_VERSION,
        ),
        extractor=VersionBinding(
            "extractor",
            WholeOrderCompletenessProof.EXTRACTOR_VERSION,
        ),
        fixture=VersionBinding(
            "fixture",
            WholeOrderCompletenessProof.FIXTURE_VERSION,
        ),
        order_source_observed_at=observed_at,
        proof_source_observed_at=observed_at,
        required_sections=WholeOrderCompletenessProof.REQUIRED_SECTIONS,
        section_proofs=section_proofs,
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
        source_refs=(order_source,),
        coherence_state="COHERENT",
        change_detection_state="UNCHANGED",
        empty_universe_proved=False,
    )
    wwc_finding = WWCFinding(
        finding_id=EvidenceId("SYN-EVIDENCE-DOI-MODEL-KAT-WWC-FINDING"),
        presence=FindingPresenceV2.NOT_PRESENT,
        author_relation=not_applicable_fact(),
        timing_state=not_applicable_fact(),
        marker=not_applicable_fact(),
        observed_at=not_applicable_fact(),
        source=order_source,
    )
    dedupe_finding = DedupeFinding(
        finding_id=EvidenceId("SYN-EVIDENCE-DOI-MODEL-KAT-DEDUPE-FINDING"),
        presence=FindingPresenceV2.NOT_PRESENT,
        observed_at=None,
        state=DedupeState.NOT_PRESENT,
        source=order_source,
    )
    snapshot = DOIOrderSnapshot(
        snapshot_id=DoiSnapshotId(SnapshotId("SYN-SNAPSHOT-DOI-MODEL-KAT-0001")),
        run_id=DoiRunId(RunId("SYN-RUN-DOI-MODEL-KAT-0001")),
        order_id=order_id,
        source_observed_at=observed_at,
        completeness_proof=completeness,
        source_presence=SourcePresence.PRESENT,
        order_state=known_fact(OrderState.ACTIVE),
        current_rep_value=known_fact(RepId("SYN-REP-DOI-MODEL-KAT-TARGET")),
        current_rep_relation=known_fact(RepRelation.TARGET_REP_OWNED),
        geography_class=known_fact(GeographyClass.DOMESTIC_STANDARD),
        payment_condition=known_fact(PaymentCondition.NONE_OBSERVED),
        order_total=known_fact(money.multiply(PositiveQuantity(4))),
        wwc_finding=wwc_finding,
        dedupe_finding=dedupe_finding,
        lines=lines,
    )
    request = DOIEvaluationInput(
        evaluation_id=EvaluationId("SYN-EVALUATION-DOI-MODEL-KAT-0001"),
        snapshot=snapshot,
        evaluated_at=observed_at,
    )
    evaluation = evaluate_doi(request)
    opportunity = evaluation.opportunities[0]
    case_id = EvidenceId("SYN-EVIDENCE-DOI-MODEL-KAT-CASE")
    admission = DOICaseAdmissionProof(
        proof_id=EvidenceId("SYN-EVIDENCE-DOI-MODEL-KAT-ADMISSION"),
        case_id=case_id,
        order_id=order_id,
        source=order_source,
        completeness_proof=completeness,
        admitted_at=observed_at,
    )
    case_source = DOICaseSourceBinding(
        binding_id=EvidenceId("SYN-EVIDENCE-DOI-MODEL-KAT-CASE-SOURCE"),
        case_id=case_id,
        order_id=order_id,
        source=order_source,
        admission_proof=admission,
    )
    order_case = DOIOrderCase(
        case_id=case_id,
        order_id=order_id,
        lifecycle_state=CaseLifecycleState.ACTIVE,
        current_snapshot_id=snapshot.snapshot_id,
        current_evaluation_id=evaluation.evaluation_id,
        terminal_closure_reason=None,
    )

    context_id = EvidenceId("SYN-EVIDENCE-DOI-MODEL-KAT-ACTION-CONTEXT")
    context_event_id = EvidenceId(
        "SYN-EVIDENCE-DOI-MODEL-KAT-ACTION-CONTEXT-EVENT"
    )
    context_occurrence = InteractionId(
        "SYN-INTERACTION-DOI-MODEL-KAT-ACTION-CONTEXT"
    )
    interaction_source = SourceRef.create(
        source_ref_id=EvidenceId(
            "SYN-EVIDENCE-DOI-MODEL-KAT-INTERACTION-SOURCE"
        ),
        source_kind=SourceKind.SYNTHETIC_INTERACTION_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_INTERACTION,
        object_id=context_occurrence,
    )
    occurrence_guard = DOIOccurrenceGuard(
        guard_id=context_event_id,
        owner_id=context_id,
        occurrence_id=context_occurrence,
        source=interaction_source,
    )
    opening_authorization = verify_action_context_opening_authority(
        authorization_id=EvidenceId(
            "SYN-EVIDENCE-DOI-MODEL-KAT-OPENING-AUTHORITY"
        ),
        attempt_intent_id=context_occurrence,
        case=order_case,
        case_source_binding=case_source,
        evaluation=evaluation,
        opportunity=opportunity,
        context_kind=ActionContextKind.FULFILLMENT_SPLIT_REVIEW,
        actor=RepId("SYN-REP-DOI-MODEL-KAT-AUTHORIZED"),
        granted_at=observed_at,
        authority_source=interaction_source,
    )
    context_event = DOIActionContextEvent.opened(
        event_id=context_event_id,
        action_context_id=context_id,
        opening_authorization=opening_authorization,
        created_at=observed_at,
        guard=occurrence_guard,
    )
    context = DOIActionContext.from_event(context_event)
    if action_context_only:
        return context
    authority = verify_synthetic_human_authority(
        grant_id=EvidenceId("SYN-EVIDENCE-DOI-MODEL-KAT-AUTHORITY"),
        actor=RepId("SYN-REP-DOI-MODEL-KAT-AUTHORIZED"),
        action_context=context,
        granted_at=observed_at,
        authority_source=interaction_source,
    )
    human_fact = StructuredHumanFact.create(
        fact_id=EvidenceId("SYN-EVIDENCE-DOI-MODEL-KAT-HUMAN-FACT"),
        action_context=context,
        evaluation_id=request.evaluation_id,
        usage_kind=HumanFactUsageKind.NO_ACTION_DECISION,
        result_code=HumanFactResultCode.APPROVED,
        authority_grant=authority,
        occurred_at=observed_at,
        source=interaction_source,
    )

    def event_guard(label: str, owner: EvidenceId) -> DOIOccurrenceGuard:
        event_id = EvidenceId(f"SYN-EVIDENCE-DOI-MODEL-KAT-{label}-EVENT")
        occurrence = InteractionId(f"SYN-INTERACTION-DOI-MODEL-KAT-{label}")
        source = SourceRef.create(
            source_ref_id=EvidenceId(
                f"SYN-EVIDENCE-DOI-MODEL-KAT-{label}-SOURCE"
            ),
            source_kind=SourceKind.SYNTHETIC_INTERACTION_FIXTURE,
            object_namespace=SourceObjectNamespace.SYNTHETIC_INTERACTION,
            object_id=occurrence,
        )
        return DOIOccurrenceGuard(
            guard_id=event_id,
            owner_id=owner,
            occurrence_id=occurrence,
            source=source,
        )

    ordered_sku = cast(SkuId, lines[0].es_number.value)
    ordered_mfg = cast(SkuId, lines[0].mfg_number.value)
    alternate_sku = SkuId("SYN-SKU-DOI-MODEL-KAT-ALTERNATE")
    relationship_source = SourceRef.create(
        source_ref_id=EvidenceId(
            "SYN-EVIDENCE-DOI-MODEL-KAT-RELATIONSHIP-SOURCE"
        ),
        source_kind=SourceKind.SYNTHETIC_PRODUCT_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_PRODUCT,
        object_id=alternate_sku,
    )
    relationship = create_relationship(
        relationship_id=EvidenceId(
            "SYN-EVIDENCE-DOI-MODEL-KAT-RELATIONSHIP"
        ),
        revision_id=EvidenceId(
            "SYN-EVIDENCE-DOI-MODEL-KAT-RELATIONSHIP-REVISION"
        ),
        relationship_type=AlternateRelationshipType.EXACT_MFG,
        ordered_sku=ordered_sku,
        candidate_sku=alternate_sku,
        ordered_mfg=ordered_mfg,
        candidate_mfg=ordered_mfg,
        compatibility_review_required=False,
        evidence_source=relationship_source,
    )
    candidate_observation = DOIAlternateObservation(
        observation_id=EvidenceId(
            "SYN-EVIDENCE-DOI-MODEL-KAT-CANDIDATE-OBSERVATION"
        ),
        action_context_id=context.action_context_id,
        action_context_binding=context.hash_binding(),
        relationship_revision_binding=(
            relationship.current_revision.hash_binding()
        ),
        candidate_sku=alternate_sku,
        state=AlternateObservationState.CURRENT,
        observed_availability=known_fact(AlternateAvailability.IN_STOCK),
        observed_eta=not_applicable_fact(),
        observed_price=known_fact(money),
        observed_at=observed_at,
        source=relationship_source,
    )
    relationship_candidate = candidate_from_relationship(
        candidate_id=EvidenceId(
            "SYN-EVIDENCE-DOI-MODEL-KAT-RELATIONSHIP-CANDIDATE"
        ),
        relationship=relationship,
        observation=candidate_observation,
        ordered_line_id=lines[0].line_snapshot_id,
        quantity=PositiveQuantity(1),
        compatibility_decision=CompatibilityDecision.NOT_REQUIRED,
    )
    alternate_request = DOIEvaluationInput(
        evaluation_id=EvaluationId(
            "SYN-EVALUATION-DOI-MODEL-KAT-ALTERNATE"
        ),
        snapshot=snapshot,
        evaluated_at=observed_at,
        alternate_research_state=AlternateResearchState.COMPLETE,
        alternate_candidates=(relationship_candidate,),
    )
    alternate_evaluation = evaluate_doi(alternate_request)
    alternate_opportunity = next(
        retained
        for retained in alternate_evaluation.opportunities
        if retained.opportunity_type is OpportunityType.EXACT_MFG_ALTERNATE
    )
    alternate_case = replace(
        order_case,
        current_evaluation_id=alternate_evaluation.evaluation_id,
    )
    alternate_context_id = EvidenceId(
        "SYN-EVIDENCE-DOI-MODEL-KAT-ALTERNATE-CONTEXT"
    )
    alternate_open_event_id = EvidenceId(
        "SYN-EVIDENCE-DOI-MODEL-KAT-ALTERNATE-CONTEXT-OPEN-EVENT"
    )
    alternate_occurrence = InteractionId(
        "SYN-INTERACTION-DOI-MODEL-KAT-ALTERNATE-CONTEXT"
    )
    alternate_source = SourceRef.create(
        source_ref_id=EvidenceId(
            "SYN-EVIDENCE-DOI-MODEL-KAT-ALTERNATE-CONTEXT-SOURCE"
        ),
        source_kind=SourceKind.SYNTHETIC_INTERACTION_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_INTERACTION,
        object_id=alternate_occurrence,
    )
    alternate_opening_authorization = verify_action_context_opening_authority(
        authorization_id=EvidenceId(
            "SYN-EVIDENCE-DOI-MODEL-KAT-ALTERNATE-CONTEXT-AUTHORIZATION"
        ),
        attempt_intent_id=alternate_occurrence,
        case=alternate_case,
        case_source_binding=case_source,
        evaluation=alternate_evaluation,
        opportunity=alternate_opportunity,
        context_kind=ActionContextKind.SUBSTITUTION,
        actor=RepId("SYN-REP-DOI-MODEL-KAT-ALTERNATE-AUTHORIZED"),
        granted_at=observed_at,
        authority_source=alternate_source,
    )
    alternate_open_event = DOIActionContextEvent.opened(
        event_id=alternate_open_event_id,
        action_context_id=alternate_context_id,
        opening_authorization=alternate_opening_authorization,
        created_at=observed_at,
        guard=DOIOccurrenceGuard(
            guard_id=alternate_open_event_id,
            owner_id=alternate_context_id,
            occurrence_id=alternate_occurrence,
            source=alternate_source,
        ),
    )
    alternate_context = DOIActionContext.from_event(alternate_open_event)
    current_observation = DOIAlternateObservation(
        observation_id=EvidenceId(
            "SYN-EVIDENCE-DOI-MODEL-KAT-CURRENT-OBSERVATION"
        ),
        action_context_id=alternate_context.action_context_id,
        action_context_binding=alternate_context.hash_binding(),
        relationship_revision_binding=(
            relationship.current_revision.hash_binding()
        ),
        candidate_sku=alternate_sku,
        state=AlternateObservationState.CURRENT,
        observed_availability=known_fact(AlternateAvailability.IN_STOCK),
        observed_eta=not_applicable_fact(),
        observed_price=known_fact(money),
        observed_at=verified_at,
        source=relationship_source,
    )
    observation_link_guard = event_guard(
        "ACTION-CONTEXT-OBSERVATION-LINK",
        alternate_context.action_context_id,
    )
    observation_link_authority = verify_synthetic_human_authority(
        grant_id=EvidenceId(
            "SYN-EVIDENCE-DOI-MODEL-KAT-OBSERVATION-LINK-AUTHORITY"
        ),
        actor=RepId("SYN-REP-DOI-MODEL-KAT-OBSERVATION-LINK"),
        action_context=alternate_context,
        granted_at=verified_at,
        authority_source=observation_link_guard.source,
    )
    observation_link_event = DOIActionContextEvent.observation_linked(
        event_id=observation_link_guard.guard_id,
        action_context=alternate_context,
        link_id=EvidenceId(
            "SYN-EVIDENCE-DOI-MODEL-KAT-ACTION-CONTEXT-OBSERVATION-LINK"
        ),
        observation=current_observation,
        relationship_revision=relationship.current_revision,
        authority=observation_link_authority,
        linked_at=verified_at,
        guard=observation_link_guard,
    )
    observation_link = observation_link_event.observation_link
    if observation_link is None:
        raise DOIModelError("MODEL_ACTION_CONTEXT_LINK_FIXTURE_INVALID")

    completion_guard = event_guard(
        "ACTION-CONTEXT-COMPLETION",
        context.action_context_id,
    )
    completion_event = DOIActionContextEvent.completed(
        event_id=completion_guard.guard_id,
        action_context=context,
        completion_trigger=ActionContextCompletionTrigger.SYSTEM_VERIFIED,
        occurred_at=verified_at,
        guard=completion_guard,
    )

    contact_workflow_stream = EvidenceId(
        "SYN-EVIDENCE-DOI-MODEL-KAT-CONTACT-WORKFLOW-STREAM"
    )
    contact_workflow_guard = event_guard(
        "CONTACT-WORKFLOW",
        contact_workflow_stream,
    )
    contact_workflow_event = ContactWorkflowEvent(
        event_id=contact_workflow_guard.guard_id,
        stream_id=contact_workflow_stream,
        action_context=alternate_context,
        prior_state=ContactWorkflowState.NOT_CONTACTED,
        resulting_state=ContactWorkflowState.CONTACT_REQUIRED,
        event_type=ContactWorkflowEventType.CONTACT_REQUIRED_DERIVED,
        evaluation=alternate_evaluation,
        human_authority=None,
        contact_occurred_at=None,
        recorded_at=verified_at,
        sequence=1,
        predecessor_binding=None,
        guard=contact_workflow_guard,
    )
    contact_workflow_projection = reduce_contact_workflow(
        ContactWorkflowHistory.empty(
            stream_id=contact_workflow_stream,
            action_context=alternate_context,
        ),
        contact_workflow_event,
    ).history.projection

    contact_stream = EvidenceId("SYN-EVIDENCE-DOI-MODEL-KAT-CONTACT-STREAM")
    contact_guard = event_guard("CONTACT", contact_stream)
    contact_event = DOIContactEvent(
        event_id=contact_guard.guard_id,
        stream_id=contact_stream,
        order_id=order_id,
        action_context=context,
        event_type=ContactEventType.INBOUND,
        corrected_direction=None,
        corrects_event_id=None,
        target_rep_participated=True,
        contact_occurred_at=observed_at,
        recorded_at=observed_at,
        sequence=1,
        predecessor_binding=None,
        guard=contact_guard,
    )
    contact_projection = reduce_contact(
        DOIContactHistory.empty(stream_id=contact_stream, order_id=order_id),
        contact_event,
    ).history.projection

    wwc_stream = EvidenceId("SYN-EVIDENCE-DOI-MODEL-KAT-WWC-STREAM")
    wwc_guard = event_guard("WWC", wwc_stream)
    wwc_event = DOIWWCEvent(
        event_id=wwc_guard.guard_id,
        stream_id=wwc_stream,
        order_id=order_id,
        event_type=WWCEventType.OBSERVED,
        finding=wwc_finding,
        corrects_event_id=None,
        recorded_at=observed_at,
        sequence=1,
        predecessor_binding=None,
        guard=wwc_guard,
    )
    wwc_projection = reduce_wwc(
        DOIWWCHistory(stream_id=wwc_stream, order_id=order_id),
        wwc_event,
    ).history.projection

    dedupe_stream = EvidenceId("SYN-EVIDENCE-DOI-MODEL-KAT-DEDUPE-STREAM")
    dedupe_guard = event_guard("DEDUPE", dedupe_stream)
    dedupe_event = DOIDedupeEvent(
        event_id=dedupe_guard.guard_id,
        stream_id=dedupe_stream,
        order_id=order_id,
        event_type=DedupeEventType.SOURCE_OBSERVED,
        finding=dedupe_finding,
        evaluation=None,
        human_fact=None,
        verification=None,
        recorded_at=observed_at,
        sequence=1,
        predecessor_binding=None,
        guard=dedupe_guard,
    )
    dedupe_projection = reduce_dedupe(
        DOIDedupeHistory.empty(stream_id=dedupe_stream, order_id=order_id),
        dedupe_event,
    ).history.projection

    human_stream = EvidenceId("SYN-EVIDENCE-DOI-MODEL-KAT-HUMAN-STREAM")
    human_guard = event_guard("HUMAN", human_stream)
    human_event = DOIHumanFactEvent(
        event_id=human_guard.guard_id,
        stream_id=human_stream,
        event_type=HumanFactEventType.RECORDED,
        fact=human_fact,
        corrects_event_id=None,
        recorded_at=observed_at,
        sequence=1,
        predecessor_binding=None,
        guard=human_guard,
    )
    human_projection = reduce_human_fact(
        DOIHumanFactHistory(stream_id=human_stream),
        human_event,
    ).history.projection

    exact_sku = cast(SkuId, lines[0].es_number.value)
    product_source = SourceRef.create(
        source_ref_id=EvidenceId("SYN-EVIDENCE-DOI-MODEL-KAT-PRODUCT-SOURCE"),
        source_kind=SourceKind.SYNTHETIC_PRODUCT_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_PRODUCT,
        object_id=exact_sku,
    )
    exact_observation = DOIExactSKUObservation(
        observation_id=EvidenceId("SYN-EVIDENCE-DOI-MODEL-KAT-EXACT-OBSERVATION"),
        action_context_id=context.action_context_id,
        action_context_binding=context.hash_binding(),
        ordered_line_id=lines[0].line_snapshot_id,
        ordered_sku=exact_sku,
        observed_sku=exact_sku,
        state=AlternateObservationState.CURRENT,
        observed_availability=AlternateAvailability.IN_STOCK,
        potential_unit_value=money,
        observed_at=observed_at,
        source=product_source,
    )
    alternate_candidate = exact_sku_candidate(
        candidate_id=EvidenceId("SYN-EVIDENCE-DOI-MODEL-KAT-CANDIDATE"),
        quantity=PositiveQuantity(1),
        observation=exact_observation,
    )
    grouping_fact = StructuredHumanFact.create(
        fact_id=EvidenceId("SYN-EVIDENCE-DOI-MODEL-KAT-GROUPING-FACT"),
        action_context=context,
        evaluation_id=request.evaluation_id,
        usage_kind=HumanFactUsageKind.SCENARIO_GROUPING,
        result_code=HumanFactResultCode.SCENARIO_GROUPED,
        authority_grant=authority,
        occurred_at=observed_at,
        source=interaction_source,
    )
    mutual_exclusion_evidence = DOIMutualExclusionEvidence(
        evidence_id=EvidenceId(
            "SYN-EVIDENCE-DOI-MODEL-KAT-MUTUAL-EXCLUSION"
        ),
        group_id=EvidenceId("SYN-EVIDENCE-DOI-MODEL-KAT-SCENARIO-GROUP"),
        candidate_ids=tuple(
            sorted(
                (
                    alternate_candidate.candidate_id,
                    EvidenceId("SYN-EVIDENCE-DOI-MODEL-KAT-CANDIDATE-OTHER"),
                ),
                key=lambda item: item.value,
            )
        ),
        human_fact=grouping_fact,
    )

    present_finding = DedupeFinding(
        finding_id=EvidenceId(
            "SYN-EVIDENCE-DOI-MODEL-KAT-DEDUPE-PRESENT-FINDING"
        ),
        presence=FindingPresenceV2.PRESENT,
        observed_at=observed_at,
        state=DedupeState.SOURCE_PRESENT,
        source=order_source,
    )
    prior_snapshot = replace(
        snapshot,
        snapshot_id=DoiSnapshotId(
            SnapshotId("SYN-SNAPSHOT-DOI-MODEL-KAT-DEDUPE-PRIOR")
        ),
        run_id=DoiRunId(RunId("SYN-RUN-DOI-MODEL-KAT-DEDUPE-PRIOR")),
        dedupe_finding=present_finding,
    )
    verified_section_proofs = tuple(
        RequiredSectionProof.complete(
            section=section,
            source=order_source,
            observed_at=verified_at,
        )
        for section in WholeOrderCompletenessProof.REQUIRED_SECTIONS
    )
    verified_completeness = replace(
        completeness,
        order_source_observed_at=verified_at,
        proof_source_observed_at=verified_at,
        section_proofs=verified_section_proofs,
    )
    verified_finding = DedupeFinding(
        finding_id=EvidenceId(
            "SYN-EVIDENCE-DOI-MODEL-KAT-DEDUPE-VERIFIED-FINDING"
        ),
        presence=FindingPresenceV2.PRESENT,
        observed_at=verified_at,
        state=DedupeState.SOURCE_PRESENT,
        source=order_source,
    )
    verified_snapshot = replace(
        prior_snapshot,
        snapshot_id=DoiSnapshotId(
            SnapshotId("SYN-SNAPSHOT-DOI-MODEL-KAT-DEDUPE-VERIFIED")
        ),
        run_id=DoiRunId(RunId("SYN-RUN-DOI-MODEL-KAT-DEDUPE-VERIFIED")),
        source_observed_at=verified_at,
        completeness_proof=verified_completeness,
        dedupe_finding=verified_finding,
    )
    dedupe_approval_fact = StructuredHumanFact.create(
        fact_id=EvidenceId(
            "SYN-EVIDENCE-DOI-MODEL-KAT-DEDUPE-APPROVAL-FACT"
        ),
        action_context=context,
        evaluation_id=request.evaluation_id,
        usage_kind=HumanFactUsageKind.DEDUPE_DECISION,
        result_code=HumanFactResultCode.APPROVED,
        authority_grant=authority,
        occurred_at=observed_at,
        source=interaction_source,
    )
    awaiting_projection = DOIDedupeProjection(
        stream_id=dedupe_stream,
        order_id=order_id,
        state=DedupeState.APPROVED_AWAITING_VERIFICATION,
        source_finding_binding=present_finding.hash_binding(),
        decision_evaluation_binding=evaluation.hash_binding(),
        human_fact_binding=dedupe_approval_fact.hash_binding(),
        verification_binding=None,
        sequence=1,
        head_event_binding=dedupe_event.hash_binding(),
    )
    verification = DedupeVerificationFact(
        verification_id=EvidenceId("SYN-EVIDENCE-DOI-MODEL-KAT-DEDUPE-VERIFY"),
        order_id=order_id,
        prior_snapshot=prior_snapshot,
        verified_snapshot=verified_snapshot,
        approved_human_fact_binding=dedupe_approval_fact.hash_binding(),
        prior_projection_binding=awaiting_projection.hash_binding(),
        approved_at=observed_at,
    )
    records: dict[str, object] = {
        "ActionContextOpeningAuthorization": opening_authorization,
        "AlternateCandidate": alternate_candidate,
        "DOIActionContext": context,
        "DOIActionContextEvent": context_event,
        "DOIActionContextObservationLink": observation_link,
        "DOICaseAdmissionProof": admission,
        "DOICaseSourceBinding": case_source,
        "DOIContactEvent": contact_event,
        "DOIContactProjection": contact_projection,
        "DOIDedupeEvent": dedupe_event,
        "DOIDedupeProjection": dedupe_projection,
        "DOIEvaluation": evaluation,
        "DOIEvaluationInput": request,
        "DOIExplanation": evaluation.explanation,
        "DOIHumanFactEvent": human_event,
        "DOIHumanFactProjection": human_projection,
        "DOILineItemSnapshot": lines[0],
        "DOIMutualExclusionEvidence": mutual_exclusion_evidence,
        "DOIOccurrenceGuard": occurrence_guard,
        "DOIOpportunity": opportunity,
        "DOIOpportunityScope": opportunity.scope,
        "DOIOrderSnapshot": snapshot,
        "DOIWWCEvent": wwc_event,
        "DOIWWCProjection": wwc_projection,
        "DedupeFinding": present_finding,
        "DedupeVerificationFact": verification,
        "HumanAuthorityGrant": authority,
        "LineContinuityProof": lines[0].continuity,
        "StructuredHumanFact": human_fact,
        "WWCFinding": wwc_finding,
        "ContactWorkflowEvent": contact_workflow_event,
        "ContactWorkflowProjection": contact_workflow_projection,
    }
    rows = [
        (
            name,
            cast(HashBinding, record.hash_binding()).domain,  # type: ignore[attr-defined]
            cast(bytes, record.canonical_bytes()),  # type: ignore[attr-defined]
            cast(HashBinding, record.hash_binding()).sha256,  # type: ignore[attr-defined]
        )
        for name, record in records.items()
    ]
    special_bindings = {
        "ActionContextCompletionSource": completion_event.source_entity_binding,
        "ActionContextOpeningRequest": opening_authorization.request_binding,
        "DOIEvaluationOutput": evaluation.output_binding,
        "DOIOpportunityIdentity": opportunity_identity_binding(
            request,
            opportunity.opportunity_type,
            opportunity.scope,
            "FULFILLMENT_SPLIT",
        ),
        "DOIRulePackBinding": rule_pack_hash_binding(),
    }
    rows.extend(
        (name, binding.domain, binding.canonical_bytes, binding.sha256)
        for name, binding in special_bindings.items()
    )
    expected = model_hash_contracts()
    by_name = {name: (domain, canonical, digest) for name, domain, canonical, digest in rows}
    if set(by_name) != set(expected) or any(
        by_name[name][0] != domain for name, domain in expected.items()
    ):
        raise DOIModelError("MODEL_HASH_FIXTURE_INVENTORY_INVALID")
    return tuple(
        (name, *by_name[name])
        for name in sorted(by_name)
    )


def model_action_context_fixture() -> DOIActionContext:
    """Return the KAT graph's exact typed-owner Action Context for dependent KATs."""

    record = _build_model_hash_fixture(action_context_only=True)
    if type(record) is not DOIActionContext:
        raise DOIModelError("MODEL_ACTION_CONTEXT_FIXTURE_INVALID")
    return record


def model_hash_fixtures() -> tuple[tuple[str, str, bytes, str], ...]:
    """Return actual representative-record KATs for every DOI model hash domain."""

    rows = _build_model_hash_fixture(action_context_only=False)
    if type(rows) is not tuple:
        raise DOIModelError("MODEL_HASH_FIXTURE_INVENTORY_INVALID")
    return rows


def model_hash_known_answer(record: object) -> HashKnownAnswer:
    """Build a KAT row from one deterministic representative DOI model fixture."""

    contracts = model_hash_contracts()
    record_name = type(record).__name__
    expected_domain = contracts.get(record_name)
    canonical_method = getattr(record, "canonical_bytes", None)
    binding_method = getattr(record, "hash_binding", None)
    if (
        expected_domain is None
        or not callable(canonical_method)
        or not callable(binding_method)
    ):
        raise DOIModelError("HASH_KNOWN_ANSWER_RECORD_INVALID")
    canonical = canonical_method()
    binding = binding_method()
    if (
        type(canonical) is not bytes
        or type(binding) is not HashBinding
        or binding.domain != expected_domain
        or binding.canonical_bytes != canonical
    ):
        raise DOIModelError("HASH_KNOWN_ANSWER_RECORD_INVALID")
    return HashKnownAnswer(record_name, binding.domain, canonical, binding.sha256)


__all__ = [
    "ActionContextCloseReason",
    "ActionContextCompletionTrigger",
    "ActionContextEventType",
    "ActionContextKind",
    "ActionContextOpeningAuthorization",
    "ActionContextState",
    "ActionVerificationState",
    "AlternateAvailability",
    "AlternateCandidate",
    "AlternateObservationState",
    "AlternateRelationshipState",
    "AlternateRelationshipType",
    "AlternateResearchState",
    "AlternateRevisionKind",
    "AlternateValidityState",
    "AttentionCondition",
    "CaseLifecycleState",
    "ClosureProposal",
    "CompatibilityDecision",
    "ContactEventType",
    "ContactState",
    "ContactWorkflowEvent",
    "ContactWorkflowEventType",
    "ContactWorkflowHistory",
    "ContactWorkflowProjection",
    "ContactWorkflowReduction",
    "ContactWorkflowState",
    "ContinuityProofType",
    "DOIActionContext",
    "DOIActionContextEvent",
    "DOIActionContextHistory",
    "DOIActionContextObservationLink",
    "DOIActionContextReduction",
    "DOIActionContextStore",
    "DOIActionContextStoreReduction",
    "DOICaseAdmissionProof",
    "DOICaseSourceBinding",
    "DOIContactEvent",
    "DOIContactHistory",
    "DOIContactProjection",
    "DOIContactReduction",
    "DOIDedupeEvent",
    "DOIDedupeHistory",
    "DOIDedupeProjection",
    "DOIDedupeReduction",
    "DOIEvaluation",
    "DOIEvaluationInput",
    "DOIExplanation",
    "DOIHumanFactEvent",
    "DOIHumanFactHistory",
    "DOIHumanFactProjection",
    "DOIHumanFactReduction",
    "DOILineItemSnapshot",
    "DOIModelError",
    "DOIMutualExclusionEvidence",
    "DOIOccurrenceGuard",
    "DOIOpportunity",
    "DOIOpportunityScope",
    "DOIOpportunityScopeComponent",
    "DOIOrderCase",
    "DOIOrderSnapshot",
    "DOIState",
    "DOIWWCEvent",
    "DOIWWCHistory",
    "DOIWWCProjection",
    "DOIWWCReduction",
    "DOI_MODEL_SCHEMA_VERSION",
    "DOI_RULE_PACK_VERSION",
    "DOI_RULE_PACK_HASH_DOMAIN",
    "DedupeFinding",
    "DedupeEventType",
    "DedupeState",
    "DedupeVerificationFact",
    "DropShipState",
    "GeographyClass",
    "HandlingFlag",
    "HumanAuthorityGrant",
    "HumanFactResultCode",
    "HumanFactEventType",
    "HumanFactUsageKind",
    "HumanReviewKind",
    "HashKnownAnswer",
    "InterventionStatus",
    "InterventionType",
    "KPIContributionState",
    "LineActivity",
    "LineAvailability",
    "LineContinuityProof",
    "M3_OVERLAP_POLICY",
    "M3_UNCERTAINTY_CONTAINMENT_POLICY",
    "OpportunityScopeRole",
    "OpportunityType",
    "OrderState",
    "PaymentCondition",
    "QuantityAvailability",
    "ReasonEmissionRoute",
    "RepRelation",
    "ResultingOrderLinkSearchState",
    "ResultingOrderLinkState",
    "ScenarioSelection",
    "ScenarioSelectionState",
    "SourcePresence",
    "TR_037_MANUAL_REVIEW_POLICY",
    "TerminalClosureReason",
    "StructuredHumanFact",
    "ValueAvailabilityState",
    "ValueEventType",
    "ValueVerificationState",
    "WWCAuthorRelation",
    "WWCEventType",
    "WWCFinding",
    "WWCProjectionState",
    "WWCTimingState",
    "known_fact",
    "model_hash_contracts",
    "model_hash_fixtures",
    "model_hash_known_answer",
    "not_applicable_fact",
    "rule_pack_hash_binding",
    "unknown_fact",
    "reduce_action_context",
    "reduce_action_context_store",
    "reduce_contact",
    "reduce_contact_workflow",
    "reduce_dedupe",
    "reduce_human_fact",
    "reduce_wwc",
    "verify_action_context_opening_authority",
    "verify_synthetic_human_authority",
]
