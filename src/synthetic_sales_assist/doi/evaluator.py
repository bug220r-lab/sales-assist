"""Pure deterministic DOI evaluator and effective reason-ownership overlay."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from types import MappingProxyType
from typing import TypeVar, cast

from synthetic_sales_assist.doi.models import (
    AlternateCandidate,
    AlternateAvailability,
    AlternateResearchState,
    AlternateValidityState,
    CaseLifecycleState,
    ClosureProposal,
    CompatibilityDecision,
    DOI_RULE_PACK_VERSION,
    DOIEvaluation,
    DOIEvaluationInput,
    DOIExplanation,
    DOILineItemSnapshot,
    DOIOpportunity,
    DOIOpportunityScope,
    DOIOpportunityScopeComponent,
    DOIState,
    DropShipState,
    GeographyClass,
    HandlingFlag,
    HumanReviewKind,
    HumanFactResultCode,
    HumanFactUsageKind,
    LineActivity,
    LineAvailability,
    OpportunityScopeRole,
    OpportunityType,
    OrderState,
    PaymentCondition,
    QuantityAvailability,
    ReasonEmissionRoute,
    RepRelation,
    ScenarioSelectionState,
    SourcePresence,
    TerminalClosureReason,
    ValueAvailabilityState,
    WWCAuthorRelation,
    WWCTimingState,
    rule_pack_hash_binding,
)
from synthetic_sales_assist.domain.canonical import (
    HashBinding,
    canonical_json_bytes,
    domain_hash,
    parse_canonical_json_bytes,
)
from synthetic_sales_assist.domain.identities import EvidenceId
from synthetic_sales_assist.domain.numeric import (
    CurrencyMismatch,
    Money,
    MoneyViolation,
    PositiveQuantity,
    Quantity,
)
from synthetic_sales_assist.domain.observed import (
    FindingPresenceV2,
    KnownObservedValue,
    ObservedTaggedValue,
    UnknownObservedValue,
)
from synthetic_sales_assist.domain.records import ReasonSet, VersionBinding
from synthetic_sales_assist.domain.registries import (
    DoiRegistries,
    ReasonRef,
    TransitionRef,
    load_doi_registries,
)


class DOIEvaluationError(ValueError):
    """Stable non-reflecting evaluator failure."""

    def __init__(self, code: str, *, reasons: ReasonSet | None = None) -> None:
        self.code = code
        self.reasons = reasons or ReasonSet()
        super().__init__(code)


class DOIRuleVersionUnavailable(DOIEvaluationError):
    """Closed evaluation-gate result proving that no substitute evaluation exists."""

    def __init__(self, registries: DoiRegistries) -> None:
        super().__init__(
            "RULE_VERSION_UNAVAILABLE",
            reasons=ReasonSet((registries.reason_ref("RC-084"),)),
        )
        self.reason = registries.reason_ref("RC-084")
        self.governed_transitions = (
            registries.transition_ref("TR-027"),
            registries.transition_ref("TR-037"),
        )
        self.evaluation = None


_E = TypeVar("_E")
OPPORTUNITY_ID_HASH_DOMAIN = "doi-opportunity-id/v1"

_OVERLAY_TRANSITIONS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "RC-016": ("TR-027", "TR-028", "TR-033", "TR-034", "TR-035"),
        "RC-017": ("TR-027", "TR-028", "TR-033", "TR-034", "TR-035"),
        "RC-018": ("TR-027", "TR-028", "TR-033", "TR-034", "TR-035"),
        "RC-115": ("TR-027", "TR-028", "TR-033", "TR-034", "TR-035"),
        "RC-116": ("TR-027", "TR-028", "TR-033", "TR-034", "TR-035"),
        "RC-087": ("TR-033", "TR-034", "TR-035"),
    }
)

_RULES_EVALUATED = (
    "ALTERNATE_HIERARCHY",
    "CLOSURE_PRECEDENCE",
    "DEDUPE",
    "DIRECT_SHIP",
    "FIELD_UNCERTAINTY_CONTAINMENT",
    "FULFILLMENT_SPLIT",
    "GEOGRAPHY_HANDLING",
    "OPPORTUNITY_OVERLAP",
    "ORDER_PROGRESSION",
    "PARTIAL_QUANTITY",
    "PAYMENT_HANDLING",
    "SOURCE_RECHECK",
    "WWC_COORDINATION",
)

_UNKNOWN_ENUM_REASON: Mapping[type[object], str] = MappingProxyType(
    {
        OrderState: "RC-116",
        RepRelation: "RC-118",
        GeographyClass: "RC-119",
        PaymentCondition: "RC-120",
        LineActivity: "RC-125",
        DropShipState: "RC-017",
        LineAvailability: "RC-016",
        QuantityAvailability: "RC-132",
    }
)

_ALTERNATE_REASON: Mapping[OpportunityType, str] = MappingProxyType(
    {
        OpportunityType.EXACT_SKU_RECHECK: "RC-033",
        OpportunityType.EXACT_MFG_ALTERNATE: "RC-034",
        OpportunityType.MFG_CROSS_REFERENCE: "RC-035",
        OpportunityType.MFG_SUPERSESSION: "RC-036",
        OpportunityType.FUNCTIONAL_ALTERNATE: "RC-037",
    }
)

_RELATIONSHIP_TYPE_BY_OPPORTUNITY: Mapping[OpportunityType, str] = MappingProxyType(
    {
        OpportunityType.EXACT_MFG_ALTERNATE: "EXACT_MFG",
        OpportunityType.MFG_CROSS_REFERENCE: "MFG_CROSS_REFERENCE",
        OpportunityType.MFG_SUPERSESSION: "MFG_SUPERSESSION",
        OpportunityType.FUNCTIONAL_ALTERNATE: "FUNCTIONAL",
    }
)


def _error_reasons(*codes: str) -> ReasonSet:
    registry = load_doi_registries()
    return ReasonSet(
        tuple(sorted((registry.reason_ref(code) for code in codes), key=lambda item: item.code))
    )


def construct_doi_money(
    amount: object,
    currency_code: object,
    registry_version: object,
    scale: object,
) -> Money:
    """Construct an exact monetary fact and map any binding failure to RC-094."""

    try:
        return Money(
            cast(Decimal, amount),
            cast(str, currency_code),
            cast(str, registry_version),
            cast(int, scale),
        )
    except (MoneyViolation, TypeError):
        raise DOIEvaluationError(
            "CURRENCY_CODE_INVALID",
            reasons=_error_reasons("RC-094"),
        ) from None


def effective_reason_routes(
    registries: DoiRegistries | None = None,
) -> Mapping[str, tuple[TransitionRef, ...]]:
    """Return supplied ownership plus the approved M3 opportunity-preservation overlay.

    The supplied registry remains byte-identical.  Existing routes remain legal and the three
    affected field-uncertainty and overlap rows gain their approved actual routes.
    """

    registry = registries or load_doi_registries()
    result: dict[str, tuple[TransitionRef, ...]] = {}
    for reason in registry.reason_refs:
        supplied = (
            ()
            if reason.code == "RC-087"
            else registry.ownership_transition_refs(reason)
        )
        additions = tuple(
            registry.transition_ref(transition_id)
            for transition_id in _OVERLAY_TRANSITIONS.get(reason.code, ())
        )
        by_id = {item.transition_id: item for item in (*supplied, *additions)}
        result[reason.code] = tuple(by_id[key] for key in sorted(by_id))
    return MappingProxyType(result)


def assert_reason_route_legal(
    reason: ReasonRef | str,
    transition: TransitionRef | None,
    *,
    registries: DoiRegistries | None = None,
) -> None:
    """Reject a reason emission that has no exact effective ownership route."""

    registry = registries or load_doi_registries()
    ref = reason if type(reason) is ReasonRef else registry.reason_ref(reason)
    routes = effective_reason_routes(registry)[ref.code]
    if transition is None:
        if routes or not registry.is_rule_or_boundary_only(ref):
            raise DOIEvaluationError("REASON_ROUTE_ILLEGAL")
        return
    if type(transition) is not TransitionRef or transition not in routes:
        raise DOIEvaluationError("REASON_ROUTE_ILLEGAL")


def _known_enum(
    value: ObservedTaggedValue[str],
    enum_type: type[_E],
) -> _E | None:
    if type(value) is not KnownObservedValue:
        return None
    raw = value.value
    if type(raw) is not str:
        return None
    parsed: _E | None = None
    try:
        parsed = enum_type(raw)
    except ValueError:
        pass
    return parsed


def _known_exact(
    value: ObservedTaggedValue[object], expected_type: type[_E]
) -> _E | None:
    if type(value) is KnownObservedValue and type(value.value) is expected_type:
        return cast(_E, value.value)
    return None


def _unknown_reason(value: ObservedTaggedValue[object]) -> str | None:
    if type(value) is UnknownObservedValue:
        return value.reason_code
    return None


def _enum_unknown_reason(
    value: ObservedTaggedValue[str], enum_type: type[object]
) -> str | None:
    direct = _unknown_reason(cast(ObservedTaggedValue[object], value))
    if direct is not None:
        return direct
    known = _known_enum(value, cast(type[object], enum_type))
    if known is not None and getattr(known, "value", None) == "UNKNOWN":
        return _UNKNOWN_ENUM_REASON[enum_type]
    return None


def _line_unknown_codes(line: DOILineItemSnapshot) -> set[str]:
    fields: tuple[ObservedTaggedValue[object], ...] = (
        cast(ObservedTaggedValue[object], line.stable_source_line_id),
        cast(ObservedTaggedValue[object], line.activity),
        cast(ObservedTaggedValue[object], line.drop_ship_state),
        cast(ObservedTaggedValue[object], line.availability),
        cast(ObservedTaggedValue[object], line.eta),
        cast(ObservedTaggedValue[object], line.ordered_quantity),
        cast(ObservedTaggedValue[object], line.active_quantity),
        cast(ObservedTaggedValue[object], line.canceled_quantity),
        cast(ObservedTaggedValue[object], line.explicitly_available_quantity),
        cast(ObservedTaggedValue[object], line.quantity_availability),
        cast(ObservedTaggedValue[object], line.es_number),
        cast(ObservedTaggedValue[object], line.mfg_number),
        cast(ObservedTaggedValue[object], line.unit_value),
        cast(ObservedTaggedValue[object], line.active_line_value),
        cast(ObservedTaggedValue[object], line.line_sales_rep),
    )
    codes = {code for value in fields if (code := _unknown_reason(value)) is not None}
    for value, enum_type in (
        (line.activity, LineActivity),
        (line.drop_ship_state, DropShipState),
        (line.availability, LineAvailability),
        (line.quantity_availability, QuantityAvailability),
    ):
        if (code := _enum_unknown_reason(value, enum_type)) is not None:
            codes.add(code)
    if line.continuity.state.value == "UNVERIFIED":
        codes.add("RC-018")
    return codes


def _all_unknown_codes(request: DOIEvaluationInput) -> set[str]:
    snapshot = request.snapshot
    fields: tuple[ObservedTaggedValue[object], ...] = (
        cast(ObservedTaggedValue[object], snapshot.order_state),
        cast(ObservedTaggedValue[object], snapshot.current_rep_value),
        cast(ObservedTaggedValue[object], snapshot.current_rep_relation),
        cast(ObservedTaggedValue[object], snapshot.geography_class),
        cast(ObservedTaggedValue[object], snapshot.payment_condition),
        cast(ObservedTaggedValue[object], snapshot.order_total),
        cast(ObservedTaggedValue[object], snapshot.wwc_finding.author_relation),
        cast(ObservedTaggedValue[object], snapshot.wwc_finding.timing_state),
        cast(ObservedTaggedValue[object], snapshot.wwc_finding.marker),
        cast(ObservedTaggedValue[object], snapshot.wwc_finding.observed_at),
    )
    codes = {code for value in fields if (code := _unknown_reason(value)) is not None}
    for value, enum_type in (
        (snapshot.order_state, OrderState),
        (snapshot.current_rep_relation, RepRelation),
        (snapshot.geography_class, GeographyClass),
        (snapshot.payment_condition, PaymentCondition),
    ):
        if (code := _enum_unknown_reason(value, enum_type)) is not None:
            codes.add(code)
    if snapshot.wwc_finding.presence is FindingPresenceV2.UNKNOWN:
        codes.add("RC-122")
    if snapshot.dedupe_finding.presence is FindingPresenceV2.UNKNOWN:
        codes.add("RC-123")
    for line in snapshot.lines:
        codes.update(_line_unknown_codes(line))
    for candidate in request.alternate_candidates:
        codes.update(reason.code for reason in candidate.unknown_reasons)
    return codes


def _line_active(line: DOILineItemSnapshot) -> bool:
    return _known_enum(line.activity, LineActivity) is LineActivity.ACTIVE


def _line_quantity(line: DOILineItemSnapshot) -> PositiveQuantity | None:
    quantity = _known_exact(
        cast(ObservedTaggedValue[object], line.active_quantity), Quantity
    )
    if quantity is None or quantity.value <= 0:
        return None
    return PositiveQuantity(quantity.value)


def _scope(
    components: list[DOIOpportunityScopeComponent],
) -> DOIOpportunityScope:
    return DOIOpportunityScope(
        tuple(
            sorted(
                components,
                key=lambda item: (
                    item.line_snapshot_id.to_json_value(),
                    item.role.value,
                ),
            )
        )
    )


def _line_value(line: DOILineItemSnapshot, quantity: PositiveQuantity) -> Money | None:
    unit_value = _known_exact(
        cast(ObservedTaggedValue[object], line.unit_value), Money
    )
    if unit_value is not None:
        return unit_value.multiply(quantity)
    active_quantity = _line_quantity(line)
    active_value = _known_exact(
        cast(ObservedTaggedValue[object], line.active_line_value), Money
    )
    if active_quantity == quantity and active_value is not None:
        return active_value
    return None


def _sum_money(values: list[Money]) -> Money | None:
    if not values:
        return None
    result = values[0]
    try:
        for value in values[1:]:
            result = result + value
    except CurrencyMismatch:
        return None
    return result


def opportunity_identity_binding(
    request: DOIEvaluationInput,
    opportunity_type: OpportunityType,
    scope: DOIOpportunityScope,
    discriminator: str,
) -> HashBinding:
    material = canonical_json_bytes(
        {
            "discriminator": discriminator,
            "evaluation_id": request.evaluation_id.value,
            "opportunity_type": opportunity_type.value,
            "scope_sha256": scope.hash_binding().sha256,
        },
        expected_members={
            "discriminator",
            "evaluation_id",
            "opportunity_type",
            "scope_sha256",
        },
    )
    return domain_hash(OPPORTUNITY_ID_HASH_DOMAIN, material)


def _opportunity_id(
    request: DOIEvaluationInput,
    opportunity_type: OpportunityType,
    scope: DOIOpportunityScope,
    discriminator: str,
) -> EvidenceId:
    binding = opportunity_identity_binding(
        request,
        opportunity_type,
        scope,
        discriminator,
    )
    return EvidenceId(f"SYN-EVIDENCE-DOI-OPPORTUNITY-{binding.sha256.upper()}")


def _make_opportunity(
    *,
    request: DOIEvaluationInput,
    opportunity_type: OpportunityType,
    scope: DOIOpportunityScope,
    potential_value: Money | None,
    discriminator: str,
    relationship_binding: HashBinding | None = None,
    observation_binding: HashBinding | None = None,
    mutual_exclusion_group: EvidenceId | None = None,
) -> DOIOpportunity:
    return DOIOpportunity(
        opportunity_id=_opportunity_id(request, opportunity_type, scope, discriminator),
        opportunity_type=opportunity_type,
        scope=scope,
        potential_value_state=(
            ValueAvailabilityState.AVAILABLE
            if potential_value is not None
            else ValueAvailabilityState.UNAVAILABLE
        ),
        potential_value=potential_value,
        relationship_revision_binding=relationship_binding,
        alternate_observation_binding=observation_binding,
        mutual_exclusion_group=mutual_exclusion_group,
    )


def _closure(request: DOIEvaluationInput) -> tuple[
    TerminalClosureReason | None, str | None
]:
    order = request.snapshot
    order_state = _known_enum(order.order_state, OrderState)
    if order_state is OrderState.SHIPPED:
        return TerminalClosureReason.SHIPPED, "RC-021"
    if order_state is OrderState.CANCELED:
        return TerminalClosureReason.CANCELED, "RC-022"
    relation = _known_enum(order.current_rep_relation, RepRelation)
    if relation is RepRelation.OTHER_REP:
        return TerminalClosureReason.REP_TRANSFERRED, "RC-023"
    if request.dedupe_verification is not None:
        return TerminalClosureReason.DEDUPE_CONFIRMED, "RC-024"
    if any(
        fact.usage_kind is HumanFactUsageKind.OUT_OF_SCOPE_CLOSURE
        and fact.result_code is HumanFactResultCode.OUT_OF_SCOPE
        for fact in request.human_facts
    ):
        return TerminalClosureReason.HUMAN_OUT_OF_SCOPE, "RC-025"
    return None, None


def _active_relevant_lines(request: DOIEvaluationInput) -> tuple[DOILineItemSnapshot, ...]:
    return tuple(
        line
        for line in request.snapshot.lines
        if line.relevant_merchandise and _line_active(line)
    )


def _direct_ship_opportunity(
    request: DOIEvaluationInput,
    lines: tuple[DOILineItemSnapshot, ...],
) -> DOIOpportunity | None:
    ds_lines = [
        line
        for line in lines
        if _known_enum(line.drop_ship_state, DropShipState) is DropShipState.DS
    ]
    non_ds_lines = [
        line
        for line in lines
        if _known_enum(line.drop_ship_state, DropShipState) is DropShipState.NON_DS
    ]
    if not ds_lines or not non_ds_lines:
        return None
    components: list[DOIOpportunityScopeComponent] = []
    values: list[Money] = []
    for line, role in (
        *((item, OpportunityScopeRole.DIRECT_SHIP) for item in ds_lines),
        *((item, OpportunityScopeRole.NON_DIRECT_SHIP) for item in non_ds_lines),
    ):
        quantity = _line_quantity(line)
        if quantity is None:
            return None
        components.append(DOIOpportunityScopeComponent(line.line_snapshot_id, quantity, role))
        line_value = _line_value(line, quantity)
        if line_value is not None:
            values.append(line_value)
    scope = _scope(components)
    potential = _sum_money(values) if len(values) == len(components) else None
    return _make_opportunity(
        request=request,
        opportunity_type=OpportunityType.DS_SEPARATION,
        scope=scope,
        potential_value=potential,
        discriminator="MIXED_DS",
    )


def _split_opportunity(
    request: DOIEvaluationInput,
    lines: tuple[DOILineItemSnapshot, ...],
) -> DOIOpportunity | None:
    available: list[DOILineItemSnapshot] = []
    delayed: list[DOILineItemSnapshot] = []
    for line in lines:
        if (
            _known_enum(line.drop_ship_state, DropShipState)
            is not DropShipState.NON_DS
            or _line_quantity(line) is None
        ):
            continue
        availability = _known_enum(line.availability, LineAvailability)
        quantity_state = _known_enum(line.quantity_availability, QuantityAvailability)
        if (
            availability is LineAvailability.IN_STOCK
            and quantity_state is QuantityAvailability.FULL
        ):
            available.append(line)
        elif availability is LineAvailability.DELAYED:
            delayed.append(line)
    if not available or not delayed:
        return None
    components: list[DOIOpportunityScopeComponent] = []
    values: list[Money] = []
    for line, role in (
        *((item, OpportunityScopeRole.AVAILABLE) for item in available),
        *((item, OpportunityScopeRole.DELAYED) for item in delayed),
    ):
        quantity = _line_quantity(line)
        if quantity is None:
            raise DOIEvaluationError("INTERNAL_SPLIT_SCOPE_INCONSISTENT")
        components.append(DOIOpportunityScopeComponent(line.line_snapshot_id, quantity, role))
        if role is OpportunityScopeRole.AVAILABLE:
            value = _line_value(line, quantity)
            if value is not None:
                values.append(value)
    scope = _scope(components)
    potential = _sum_money(values) if len(values) == len(available) else None
    return _make_opportunity(
        request=request,
        opportunity_type=OpportunityType.FULFILLMENT_SPLIT,
        scope=scope,
        potential_value=potential,
        discriminator="FULFILLMENT_SPLIT",
    )


def _partial_opportunities(
    request: DOIEvaluationInput,
    lines: tuple[DOILineItemSnapshot, ...],
) -> list[DOIOpportunity]:
    result: list[DOIOpportunity] = []
    for line in lines:
        if _known_enum(line.drop_ship_state, DropShipState) is not DropShipState.NON_DS:
            continue
        active = _known_exact(cast(ObservedTaggedValue[object], line.active_quantity), Quantity)
        available = _known_exact(
            cast(ObservedTaggedValue[object], line.explicitly_available_quantity),
            Quantity,
        )
        if active is None or available is None or not 0 < available.value < active.value:
            continue
        quantity = PositiveQuantity(available.value)
        scope = _scope(
            [
                DOIOpportunityScopeComponent(
                    line.line_snapshot_id,
                    quantity,
                    OpportunityScopeRole.PARTIAL_AVAILABLE,
                )
            ]
        )
        result.append(
            _make_opportunity(
                request=request,
                opportunity_type=OpportunityType.PARTIAL_QUANTITY_REVIEW,
                scope=scope,
                potential_value=_line_value(line, quantity),
                discriminator=line.line_snapshot_id.to_json_value(),
            )
        )
    return result


def _alternate_opportunities(
    request: DOIEvaluationInput,
) -> tuple[list[DOIOpportunity], set[str], set[HandlingFlag], set[HumanReviewKind]]:
    opportunities: list[DOIOpportunity] = []
    reasons: set[str] = set()
    flags: set[HandlingFlag] = set()
    reviews: set[HumanReviewKind] = set()
    if request.alternate_research_state is AlternateResearchState.MANUAL_IDENTIFICATION_REQUIRED:
        reasons.update(("RC-040", "RC-059"))
        reviews.add(HumanReviewKind.UNKNOWN_FACT)
        return opportunities, reasons, flags, reviews
    for candidate in request.alternate_candidates:
        relationship_state: object | None = None
        if candidate.relationship_revision_binding is not None:
            relationship_state = _closed_binding_object(
                candidate.relationship_revision_binding
            ).get("state")
        if relationship_state == "SUPERSEDED":
            reasons.add("RC-046")
            continue
        if relationship_state == "INVALIDATED":
            reasons.add("RC-047")
            continue
        if not candidate.current_observation:
            reasons.add("RC-045" if candidate.observation_binding is not None else "RC-044")
            continue
        if candidate.observed_availability is not AlternateAvailability.IN_STOCK:
            continue
        if candidate.validity is AlternateValidityState.REJECTED:
            continue
        scope = _scope(
            [
                DOIOpportunityScopeComponent(
                    candidate.ordered_line_id,
                    candidate.quantity,
                    OpportunityScopeRole.ALTERNATE_PRODUCT,
                )
            ]
        )
        opportunities.append(
            _make_opportunity(
                request=request,
                opportunity_type=candidate.opportunity_type,
                scope=scope,
                potential_value=candidate.potential_value,
                discriminator=candidate.candidate_id.value,
                relationship_binding=candidate.relationship_revision_binding,
                observation_binding=candidate.observation_binding,
                mutual_exclusion_group=candidate.mutual_exclusion_group,
            )
        )
        reasons.add(_ALTERNATE_REASON[candidate.opportunity_type])
        if candidate.opportunity_type is not OpportunityType.EXACT_SKU_RECHECK:
            reasons.add("RC-042")
            flags.add(HandlingFlag.CUSTOMER_APPROVAL_REQUIRED)
            reviews.add(HumanReviewKind.CUSTOMER_APPROVAL)
        if (
            candidate.validity is AlternateValidityState.COMPATIBILITY_REVIEW_REQUIRED
            or candidate.compatibility_decision
            is CompatibilityDecision.MORE_EVIDENCE_REQUIRED
        ):
            reasons.add("RC-043")
            flags.add(HandlingFlag.COMPATIBILITY_REVIEW_REQUIRED)
            reviews.add(HumanReviewKind.COMPATIBILITY)
        if (
            candidate.opportunity_type is OpportunityType.FUNCTIONAL_ALTERNATE
            and candidate.compatibility_decision is not CompatibilityDecision.APPROVED
        ):
            reasons.add("RC-048")
    if request.alternate_research_state is AlternateResearchState.IN_PROGRESS:
        reasons.add("RC-059")
    if request.alternate_research_state is AlternateResearchState.COMPLETE:
        verified = tuple(
            candidate
            for candidate in request.alternate_candidates
            if candidate.validity is AlternateValidityState.VERIFIED
            and candidate.current_observation
            and candidate.observed_availability is AlternateAvailability.IN_STOCK
        )
        if not any(
            candidate.opportunity_type is OpportunityType.EXACT_MFG_ALTERNATE
            for candidate in verified
        ):
            reasons.add("RC-038")
        if not verified:
            reasons.add("RC-039")
        if any(
            fact.usage_kind is HumanFactUsageKind.ALTERNATE_RESEARCH
            and fact.result_code is HumanFactResultCode.NO_VIABLE_ALTERNATE
            for fact in request.human_facts
        ):
            reasons.add("RC-041")
    return opportunities, reasons, flags, reviews


def _closed_binding_object(binding: HashBinding) -> dict[str, object]:
    try:
        decoded = parse_canonical_json_bytes(binding.canonical_bytes)
    except (TypeError, ValueError):
        raise DOIEvaluationError(
            "ALTERNATE_PROVENANCE_INVALID",
            reasons=_error_reasons("RC-106"),
        ) from None
    if type(decoded) is not dict:
        raise DOIEvaluationError(
            "ALTERNATE_PROVENANCE_INVALID",
            reasons=_error_reasons("RC-106"),
        )
    return cast(dict[str, object], decoded)


def _validate_alternate_candidates(request: DOIEvaluationInput) -> None:
    lines = {line.line_snapshot_id: line for line in request.snapshot.lines}
    for candidate in request.alternate_candidates:
        line = lines.get(candidate.ordered_line_id)
        if line is None:
            raise DOIEvaluationError(
                "ALTERNATE_WRONG_SNAPSHOT_SCOPE",
                reasons=_error_reasons("RC-097"),
            )
        active_quantity = _line_quantity(line)
        ordered_sku = _known_exact(
            cast(ObservedTaggedValue[object], line.es_number),
            type(candidate.candidate_sku),
        )
        if (
            active_quantity is None
            or candidate.quantity.value > active_quantity.value
            or ordered_sku is None
        ):
            raise DOIEvaluationError(
                "ALTERNATE_ORDERED_LINE_BINDING_INVALID",
                reasons=_error_reasons("RC-097"),
            )
        if candidate.opportunity_type is OpportunityType.EXACT_SKU_RECHECK:
            if (
                candidate.candidate_sku != ordered_sku
                or candidate.relationship_revision_binding is not None
                or candidate.observation_binding is None
                or candidate.observation_binding.domain
                != "doi-exact-sku-observation/v1"
                or candidate.validity is not AlternateValidityState.VERIFIED
                or candidate.compatibility_decision
                is not CompatibilityDecision.NOT_REQUIRED
                or candidate.unknown_reasons
            ):
                raise DOIEvaluationError(
                    "EXACT_SKU_CANDIDATE_PROVENANCE_INVALID",
                    reasons=_error_reasons("RC-105"),
                )
            observation = _closed_binding_object(candidate.observation_binding)
            if (
                observation.get("ordered_line_id")
                != candidate.ordered_line_id.to_json_value()
                or observation.get("ordered_sku") != ordered_sku.value
                or observation.get("observed_sku") != candidate.candidate_sku.value
                or observation.get("state") != "CURRENT"
                or observation.get("observed_availability") != "IN_STOCK"
                or candidate.observed_availability is not AlternateAvailability.IN_STOCK
            ):
                raise DOIEvaluationError(
                    "EXACT_SKU_CANDIDATE_PROVENANCE_INVALID",
                    reasons=_error_reasons("RC-106"),
                )
            continue
        relationship = candidate.relationship_revision_binding
        if (
            relationship is None
            or relationship.domain != "doi-alternate-relationship-revision/v1"
        ):
            raise DOIEvaluationError(
                "ALTERNATE_RELATIONSHIP_PROVENANCE_INVALID",
                reasons=_error_reasons("RC-105"),
            )
        revision = _closed_binding_object(relationship)
        expected_type = _RELATIONSHIP_TYPE_BY_OPPORTUNITY.get(
            candidate.opportunity_type
        )
        if (
            revision.get("ordered_sku") != ordered_sku.value
            or revision.get("candidate_sku") != candidate.candidate_sku.value
            or revision.get("relationship_type") != expected_type
            or revision.get("state")
            not in {"ACTIVE", "SUPERSEDED", "INVALIDATED"}
        ):
            raise DOIEvaluationError(
                "ALTERNATE_RELATIONSHIP_PROVENANCE_INVALID",
                reasons=_error_reasons("RC-106"),
            )
        relationship_active = revision.get("state") == "ACTIVE"
        review_required = revision.get("compatibility_review_required") is True
        if (
            not relationship_active
            or candidate.compatibility_decision is CompatibilityDecision.REJECTED
        ):
            expected_validity = AlternateValidityState.REJECTED
        elif not review_required or (
            candidate.compatibility_decision is CompatibilityDecision.APPROVED
        ):
            expected_validity = AlternateValidityState.VERIFIED
        else:
            expected_validity = AlternateValidityState.COMPATIBILITY_REVIEW_REQUIRED
        if candidate.validity is not expected_validity:
            raise DOIEvaluationError(
                "ALTERNATE_COMPATIBILITY_PROVENANCE_INVALID",
                reasons=_error_reasons("RC-106"),
            )
        observation_binding = candidate.observation_binding
        if observation_binding is not None:
            if (
                observation_binding.domain != "doi-alternate-observation/v1"
            ):
                raise DOIEvaluationError(
                    "ALTERNATE_OBSERVATION_PROVENANCE_INVALID",
                    reasons=_error_reasons("RC-106"),
                )
            observation = _closed_binding_object(observation_binding)
            relationship_ref = observation.get("relationship_revision_binding")
            if (
                observation.get("candidate_sku") != candidate.candidate_sku.value
                or observation.get("state")
                != ("CURRENT" if candidate.current_observation else "STALE")
                or relationship_ref
                != {"domain": relationship.domain, "sha256": relationship.sha256}
            ):
                raise DOIEvaluationError(
                    "ALTERNATE_OBSERVATION_PROVENANCE_INVALID",
                    reasons=_error_reasons("RC-106"),
                )
            availability = observation.get("observed_availability")
            observed_fields = {
                "observed_availability": "RC-137",
                "observed_eta": "RC-138",
                "observed_price": "RC-136",
            }
            derived_unknowns = tuple(
                sorted(
                    reason
                    for field_name, reason in observed_fields.items()
                    if type(observation.get(field_name)) is dict
                    and cast(dict[str, object], observation[field_name]).get("tag")
                    == "UNKNOWN"
                )
            )
            candidate_unknowns = tuple(reason.code for reason in candidate.unknown_reasons)
            availability_known = (
                type(availability) is dict
                and availability.get("tag") == "KNOWN"
                and availability.get("value") == candidate.observed_availability.value
            )
            availability_unknown = (
                type(availability) is dict
                and availability.get("tag") in {"UNKNOWN", "NOT_APPLICABLE"}
                and candidate.observed_availability is AlternateAvailability.UNKNOWN
            )
            if (
                candidate_unknowns != derived_unknowns
                or not (availability_known or availability_unknown)
            ):
                raise DOIEvaluationError(
                    "ALTERNATE_OBSERVATION_PROVENANCE_INVALID",
                    reasons=_error_reasons("RC-106"),
                )
        elif candidate.unknown_reasons:
            raise DOIEvaluationError(
                "ALTERNATE_OBSERVATION_PROVENANCE_INVALID",
                reasons=_error_reasons("RC-105"),
            )
    grouped: dict[EvidenceId, list[AlternateCandidate]] = {}
    for candidate in request.alternate_candidates:
        if candidate.mutual_exclusion_group is not None:
            grouped.setdefault(candidate.mutual_exclusion_group, []).append(candidate)
    for group_id, candidates in grouped.items():
        evidence = candidates[0].mutual_exclusion_evidence
        if evidence is None:
            raise DOIEvaluationError(
                "MUTUAL_EXCLUSION_EVIDENCE_REQUIRED",
                reasons=_error_reasons("RC-105"),
            )
        candidate_ids = tuple(
            sorted(
                (item.candidate_id for item in candidates),
                key=lambda item: item.value,
            )
        )
        matching_facts = tuple(
            fact
            for fact in request.human_facts
            if fact == evidence.human_fact
            and fact.order_id == request.snapshot.order_id
            and fact.evaluation_id == request.evaluation_id
        )
        if (
            len(candidates) < 2
            or evidence.group_id != group_id
            or evidence.candidate_ids != candidate_ids
            or len(matching_facts) != 1
            or any(
                item.mutual_exclusion_evidence != evidence for item in candidates
            )
        ):
            raise DOIEvaluationError(
                "MUTUAL_EXCLUSION_EVIDENCE_INVALID",
                reasons=_error_reasons("RC-105"),
            )


def _opportunities_conflict(
    left: DOIOpportunity,
    right: DOIOpportunity,
) -> bool:
    same_group = (
        left.mutual_exclusion_group is not None
        and left.mutual_exclusion_group == right.mutual_exclusion_group
    )
    return bool(left.scope.line_ids & right.scope.line_ids) or same_group


def _overlap(opportunities: list[DOIOpportunity]) -> bool:
    for index, left in enumerate(opportunities):
        for right in opportunities[index + 1 :]:
            if _opportunities_conflict(left, right):
                return True
    return False


def _overlap_component(
    opportunities: list[DOIOpportunity],
    selected: DOIOpportunity,
) -> set[EvidenceId]:
    by_id = {item.opportunity_id: item for item in opportunities}
    component = {selected.opportunity_id}
    changed = True
    while changed:
        changed = False
        for item in opportunities:
            if (
                item.opportunity_id not in component
                and any(
                    _opportunities_conflict(item, by_id[item_id])
                    for item_id in component
                )
            ):
                component.add(item.opportunity_id)
                changed = True
    return component


def _aggregate_potential(
    request: DOIEvaluationInput,
    opportunities: list[DOIOpportunity],
    reasons: set[str],
    flags: set[HandlingFlag],
    reviews: set[HumanReviewKind],
) -> tuple[ValueAvailabilityState, Money | None, ScenarioSelectionState]:
    overlapping = _overlap(opportunities)
    selection = request.scenario_selection
    if overlapping and selection is None:
        reasons.add("RC-087")
        flags.add(HandlingFlag.HUMAN_SCENARIO_SELECTION_REQUIRED)
        reviews.add(HumanReviewKind.SCENARIO_SELECTION)
        return ValueAvailabilityState.UNAVAILABLE, None, ScenarioSelectionState.REQUIRED
    selected = opportunities
    selection_state = ScenarioSelectionState.NOT_REQUIRED
    if selection is not None:
        matches = [
            item
            for item in opportunities
            if item.opportunity_id == selection.selected_opportunity_id
        ]
        if len(matches) != 1 or not overlapping:
            raise DOIEvaluationError(
                "SCENARIO_OPTION_SELECTION_CONFLICT",
                reasons=_error_reasons("RC-098"),
            )
        selected_option = matches[0]
        component = _overlap_component(opportunities, selected_option)
        supplied_options = set(selection.option_opportunity_ids)
        if supplied_options != component or len(component) < 2:
            raise DOIEvaluationError(
                "SCENARIO_OPTION_SELECTION_CONFLICT",
                reasons=_error_reasons("RC-098"),
            )
        selected = [
            item
            for item in opportunities
            if item.opportunity_id == selected_option.opportunity_id
            or item.opportunity_id not in component
        ]
        selection_state = ScenarioSelectionState.SELECTED
    values = [
        item.potential_value
        for item in selected
        if item.potential_value_state is ValueAvailabilityState.AVAILABLE
        and item.potential_value is not None
    ]
    if len(values) != len(selected):
        reasons.add("RC-085")
        return ValueAvailabilityState.UNAVAILABLE, None, selection_state
    aggregate = _sum_money(cast(list[Money], values))
    if aggregate is None:
        reasons.add("RC-095")
        return ValueAvailabilityState.UNAVAILABLE, None, selection_state
    return ValueAvailabilityState.AVAILABLE, aggregate, selection_state


def _reason_route(
    reason: ReasonRef,
    top_level_transition: TransitionRef,
    registries: DoiRegistries,
) -> ReasonEmissionRoute:
    supplied = registries.ownership_transition_refs(reason)
    effective = effective_reason_routes(registries)[reason.code]
    chosen: TransitionRef | None
    if top_level_transition in effective:
        chosen = top_level_transition
    else:
        append = registries.transition_ref("TR-027")
        chosen = append if append in effective else (effective[0] if effective else None)
    assert_reason_route_legal(reason, chosen, registries=registries)
    return ReasonEmissionRoute(
        reason=reason,
        owning_transition=chosen,
        rule_or_boundary_only=chosen is None,
        effective_overlay=chosen is not None and chosen not in supplied,
    )


def _output_binding(
    *,
    state: DOIState,
    transition: TransitionRef,
    append_transitions: tuple[TransitionRef, ...],
    reasons: ReasonSet,
    reason_routes: tuple[ReasonEmissionRoute, ...],
    opportunities: tuple[DOIOpportunity, ...],
    flags: tuple[HandlingFlag, ...],
    reviews: tuple[HumanReviewKind, ...],
    closure: ClosureProposal | None,
    aggregate_state: ValueAvailabilityState,
    aggregate: Money | None,
    selection_state: ScenarioSelectionState,
    explanation: DOIExplanation,
) -> HashBinding:
    payload = {
        "aggregate_potential": aggregate.to_json_value() if aggregate is not None else None,
        "aggregate_potential_state": aggregate_state.value,
        "append_transitions": [item.transition_id for item in append_transitions],
        "closure_proposal": closure.to_dict() if closure is not None else None,
        "explanation": {
            "domain": explanation.hash_binding().domain,
            "sha256": explanation.hash_binding().sha256,
        },
        "handling_flags": [item.value for item in flags],
        "human_review_requirements": [item.value for item in reviews],
        "opportunities": [
            {"domain": item.hash_binding().domain, "sha256": item.hash_binding().sha256}
            for item in opportunities
        ],
        "reason_routes": [item.to_dict() for item in reason_routes],
        "reasons": reasons.to_json_value(),
        "scenario_selection_state": selection_state.value,
        "state": state.value,
        "transition": transition.transition_id,
    }
    return domain_hash(
        DOIEvaluation.OUTPUT_DOMAIN,
        canonical_json_bytes(payload, expected_members=set(payload)),
    )


def evaluate_doi(request: DOIEvaluationInput) -> DOIEvaluation:
    """Evaluate one complete immutable DOI snapshot without I/O, allocation, or clock reads."""

    if type(request) is not DOIEvaluationInput:
        raise DOIEvaluationError("DOI_EVALUATION_INPUT_INVALID")
    registries = load_doi_registries()
    if (
        request.required_rule_pack.version != DOI_RULE_PACK_VERSION
        or request.available_rule_pack_binding is None
    ):
        raise DOIRuleVersionUnavailable(registries)
    if request.available_rule_pack_binding != rule_pack_hash_binding():
        raise DOIEvaluationError(
            "EVALUATION_PROVENANCE_HASH_MISMATCH",
            reasons=_error_reasons("RC-106"),
        )
    _validate_alternate_candidates(request)
    source_absent = (
        request.snapshot.source_presence is SourcePresence.ABSENT_RECHECK_REQUIRED
    )
    field_unknowns = set() if source_absent else _all_unknown_codes(request)
    reasons = {"RC-010"} if source_absent else set(field_unknowns)
    rules_fired: set[str] = set()
    flags: set[HandlingFlag] = set()
    reviews: set[HumanReviewKind] = set()
    opportunities: list[DOIOpportunity] = []
    closure: ClosureProposal | None = None

    closure_reason, closure_code = (None, None) if source_absent else _closure(request)
    if source_absent:
        flags.add(HandlingFlag.SOURCE_ABSENCE_RECHECK_REQUIRED)
        state = DOIState.DOI_MONITOR
        transition = registries.transition_ref("TR-038")
        rules_fired.add("SOURCE_RECHECK")
        aggregate_state = ValueAvailabilityState.UNAVAILABLE
        aggregate = None
        selection_state = ScenarioSelectionState.NOT_REQUIRED
    elif closure_reason is not None and closure_code is not None:
        reasons.add(closure_code)
        hard = closure_reason in {TerminalClosureReason.SHIPPED, TerminalClosureReason.CANCELED}
        closure = ClosureProposal(
            closure_reason,
            CaseLifecycleState.CLOSED_HARD if hard else CaseLifecycleState.CLOSED_REVERSIBLE,
        )
        state = DOIState.DOI_EXCLUDED
        transition = registries.transition_ref("TR-029" if hard else "TR-030")
        rules_fired.add("CLOSURE_PRECEDENCE")
        aggregate_state = ValueAvailabilityState.UNAVAILABLE
        aggregate = None
        selection_state = ScenarioSelectionState.NOT_REQUIRED
    else:
        lines = _active_relevant_lines(request)
        relevant_lines = tuple(
            line for line in request.snapshot.lines if line.relevant_merchandise
        )
        complete_activity = all(
            _known_enum(line.activity, LineActivity)
            in {LineActivity.ACTIVE, LineActivity.CANCELED}
            for line in relevant_lines
        )
        all_ds = bool(lines) and complete_activity and all(
            _known_enum(line.drop_ship_state, DropShipState) is DropShipState.DS
            for line in lines
        )
        if all_ds:
            reasons.add("RC-019")
            state = DOIState.DOI_EXCLUDED
            transition = registries.transition_ref("TR-031")
            rules_fired.add("DIRECT_SHIP")
            aggregate_state = ValueAvailabilityState.UNAVAILABLE
            aggregate = None
            selection_state = ScenarioSelectionState.NOT_REQUIRED
        else:
            ds_opportunity = _direct_ship_opportunity(request, lines)
            if ds_opportunity is not None:
                opportunities.append(ds_opportunity)
                reasons.update(("RC-020", "RC-030"))
                reviews.add(HumanReviewKind.COMMERCIAL_DECISION)
                rules_fired.add("DIRECT_SHIP")
            split = _split_opportunity(request, lines)
            if split is not None:
                opportunities.append(split)
                reasons.update(("RC-031", "RC-052"))
                reviews.add(HumanReviewKind.COMMERCIAL_DECISION)
                rules_fired.add("FULFILLMENT_SPLIT")
                geography = _known_enum(request.snapshot.geography_class, GeographyClass)
                if geography is GeographyClass.DOMESTIC_SPECIAL_REVIEW:
                    reasons.add("RC-049")
                    flags.add(HandlingFlag.AK_HI_SHIPPING_REVIEW)
                    reviews.add(HumanReviewKind.SHIPPING)
                elif geography is GeographyClass.INTERNATIONAL:
                    reasons.update(("RC-050", "RC-051"))
                    flags.update(
                        {
                            HandlingFlag.INTERNATIONAL_REVIEW,
                            HandlingFlag.CUSTOMER_CONTACT_BEFORE_SPLIT,
                        }
                    )
                    reviews.update(
                        {HumanReviewKind.SHIPPING, HumanReviewKind.CUSTOMER_CONTACT}
                    )
                elif "RC-119" in reasons:
                    flags.add(
                        HandlingFlag.GEOGRAPHY_ACTION_READINESS_REVIEW_REQUIRED
                    )
                    reviews.add(HumanReviewKind.SHIPPING)
                if "RC-115" in reasons:
                    flags.add(HandlingFlag.ETA_RANKING_UNAVAILABLE)
                rules_fired.add("GEOGRAPHY_HANDLING")
            partial = _partial_opportunities(request, lines)
            if partial:
                opportunities.extend(partial)
                reasons.update(("RC-032", "RC-052"))
                reviews.add(HumanReviewKind.COMMERCIAL_DECISION)
                rules_fired.add("PARTIAL_QUANTITY")
            alternate, alternate_reasons, alternate_flags, alternate_reviews = (
                _alternate_opportunities(request)
            )
            opportunities.extend(alternate)
            reasons.update(alternate_reasons)
            flags.update(alternate_flags)
            reviews.update(alternate_reviews)
            if alternate:
                rules_fired.add("ALTERNATE_HIERARCHY")

            wwc = request.snapshot.wwc_finding
            if wwc.presence is FindingPresenceV2.PRESENT:
                author = _known_enum(wwc.author_relation, WWCAuthorRelation)
                timing = _known_enum(wwc.timing_state, WWCTimingState)
                if author is WWCAuthorRelation.TARGET_REP and timing is WWCTimingState.ACTIVE:
                    reasons.add("RC-053")
                    flags.add(HandlingFlag.OUTREACH_SUPPRESSED)
                elif author is WWCAuthorRelation.OTHER_REP and timing is WWCTimingState.ACTIVE:
                    reasons.add("RC-054")
                    flags.add(HandlingFlag.OUTREACH_SUPPRESSED)
                    reviews.add(HumanReviewKind.COORDINATION)
                if author is WWCAuthorRelation.UNCERTAIN or "RC-055" in reasons:
                    reasons.update(("RC-055", "RC-057"))
                    reviews.add(HumanReviewKind.COORDINATION)
                if timing is WWCTimingState.UNCERTAIN or "RC-056" in reasons:
                    reasons.update(("RC-056", "RC-057"))
                    reviews.add(HumanReviewKind.COORDINATION)
                rules_fired.add("WWC_COORDINATION")

            payment = _known_enum(request.snapshot.payment_condition, PaymentCondition)
            product_uncertainty = bool(
                reasons
                & {
                    "RC-016",
                    "RC-017",
                    "RC-018",
                    "RC-124",
                    "RC-125",
                    "RC-128",
                    "RC-129",
                    "RC-131",
                    "RC-132",
                    "RC-136",
                    "RC-137",
                    "RC-138",
                }
            )
            conclusion_uncertainty = product_uncertainty or bool(
                reasons & {"RC-116", "RC-118", "RC-120"}
            )
            active_other_wwc = (
                request.snapshot.wwc_finding.presence is FindingPresenceV2.PRESENT
                and _known_enum(
                    request.snapshot.wwc_finding.author_relation,
                    WWCAuthorRelation,
                )
                is WWCAuthorRelation.OTHER_REP
                and _known_enum(
                    request.snapshot.wwc_finding.timing_state,
                    WWCTimingState,
                )
                is WWCTimingState.ACTIVE
            )
            dedupe_complete = (
                request.alternate_research_state is AlternateResearchState.COMPLETE
            )
            all_progress = (
                bool(lines)
                and complete_activity
                and _known_enum(request.snapshot.order_state, OrderState)
                is OrderState.ACTIVE
                and _known_enum(
                    request.snapshot.current_rep_relation,
                    RepRelation,
                )
                is RepRelation.TARGET_REP_OWNED
                and all(
                    _known_enum(line.drop_ship_state, DropShipState)
                    is DropShipState.NON_DS
                    and _known_enum(line.availability, LineAvailability)
                    is LineAvailability.IN_STOCK
                    and _known_enum(
                        line.quantity_availability,
                        QuantityAvailability,
                    )
                    is QuantityAvailability.FULL
                    for line in lines
                )
            )
            dedupe_blocked = (
                bool(opportunities)
                or conclusion_uncertainty
                or active_other_wwc
                or payment is PaymentCondition.PRESENT
                or all_progress
                or "RC-040" in reasons
            )
            if dedupe_complete and dedupe_blocked:
                reasons.add("RC-059")
                rules_fired.add("DEDUPE")
            elif dedupe_complete:
                reasons.add("RC-058")
                reviews.add(HumanReviewKind.DEDUPE_DECISION)
                rules_fired.add("DEDUPE")
            if opportunities:
                if payment is PaymentCondition.PRESENT:
                    reasons.add("RC-027")
                    flags.add(HandlingFlag.PAYMENT_BEFORE_ACTION)
                    rules_fired.add("PAYMENT_HANDLING")
                opportunities.sort(key=lambda item: item.opportunity_id.value)
                aggregate_state, aggregate, selection_state = _aggregate_potential(
                    request,
                    opportunities,
                    reasons,
                    flags,
                    reviews,
                )
                if _overlap(opportunities):
                    rules_fired.add("OPPORTUNITY_OVERLAP")
                state = DOIState.DOI_OPPORTUNITY
                types = {item.opportunity_type for item in opportunities}
                if OpportunityType.DS_SEPARATION in types:
                    transition = registries.transition_ref("TR-033")
                elif types & {
                    OpportunityType.FULFILLMENT_SPLIT,
                    OpportunityType.PARTIAL_QUANTITY_REVIEW,
                }:
                    transition = registries.transition_ref("TR-034")
                else:
                    transition = registries.transition_ref("TR-035")
            elif payment is PaymentCondition.PRESENT and not product_uncertainty:
                reasons.add("RC-026")
                state = DOIState.DOI_EXCLUDED
                transition = registries.transition_ref("TR-032")
                rules_fired.add("PAYMENT_HANDLING")
                aggregate_state = ValueAvailabilityState.UNAVAILABLE
                aggregate = None
                selection_state = ScenarioSelectionState.NOT_REQUIRED
            else:
                no_action_confirmed = any(
                    fact.usage_kind is HumanFactUsageKind.NO_ACTION_DECISION
                    and fact.result_code is HumanFactResultCode.APPROVED
                    for fact in request.human_facts
                )
                if all_progress and payment is PaymentCondition.NONE_OBSERVED:
                    reasons.add("RC-028")
                    reviews.add(HumanReviewKind.ORDER_PROGRESS)
                    state = DOIState.DOI_MANUAL_REVIEW
                    transition = registries.transition_ref("TR-036")
                    rules_fired.add("ORDER_PROGRESSION")
                elif no_action_confirmed and not product_uncertainty:
                    reasons.add("RC-029")
                    state = DOIState.DOI_MONITOR
                    transition = registries.transition_ref("TR-039")
                    rules_fired.add("ORDER_PROGRESSION")
                elif (
                    conclusion_uncertainty
                    or "RC-040" in reasons
                    or "RC-059" in reasons
                ):
                    reviews.add(HumanReviewKind.UNKNOWN_FACT)
                    state = DOIState.DOI_MANUAL_REVIEW
                    transition = registries.transition_ref("TR-037")
                    rules_fired.add("FIELD_UNCERTAINTY_CONTAINMENT")
                else:
                    state = DOIState.DOI_MONITOR
                    transition = registries.transition_ref("TR-038")
                    rules_fired.add("ORDER_PROGRESSION")
                aggregate_state = ValueAvailabilityState.UNAVAILABLE
                aggregate = None
                selection_state = ScenarioSelectionState.NOT_REQUIRED

    if field_unknowns:
        reviews.add(HumanReviewKind.UNKNOWN_FACT)
    reason_refs = tuple(registries.reason_ref(code) for code in sorted(reasons))
    reason_set = ReasonSet(reason_refs)
    reason_routes = tuple(
        _reason_route(reason, transition, registries) for reason in reason_refs
    )
    append_by_id = {"TR-027": registries.transition_ref("TR-027")}
    for route in reason_routes:
        owner = route.owning_transition
        if owner is not None and owner != transition:
            append_by_id[owner.transition_id] = owner
    append_transitions = tuple(append_by_id[key] for key in sorted(append_by_id))
    opportunity_tuple = tuple(opportunities)
    flag_tuple = tuple(sorted(flags, key=lambda item: item.value))
    review_tuple = tuple(sorted(reviews, key=lambda item: item.value))
    unavailable = tuple(
        sorted(
            reason.code
            for reason in reason_refs
            if reason.code.startswith("RC-1") or reason.code in {"RC-016", "RC-017", "RC-018"}
        )
    )
    explanation = DOIExplanation(
        supplied_facts=tuple(
            sorted(
                {
                    "ALTERNATE_CANDIDATES",
                    "COMPLETE_ORDER_SNAPSHOT",
                    "DEDUPE_FINDING",
                    "LINE_FACTS",
                    "PAYMENT_FACT",
                    "WWC_FINDING",
                }
            )
        ),
        normalized_facts=tuple(
            sorted(
                {
                    "ALTERNATE_RESEARCH_STATE="
                    + request.alternate_research_state.value,
                    "SOURCE_PRESENCE=" + request.snapshot.source_presence.value,
                    "TOP_LEVEL_STATE=" + state.value,
                }
            )
        ),
        unavailable_facts=unavailable,
        rules_evaluated=_RULES_EVALUATED,
        rules_fired=tuple(sorted(rules_fired)),
        precedence_decision=state.value,
        reason_codes=tuple(reason.code for reason in reason_refs),
        reason_ownership=tuple(
            sorted(
                route.reason.code
                + "@"
                + (
                    route.owning_transition.transition_id
                    if route.owning_transition is not None
                    else "RULE_OR_BOUNDARY"
                )
                for route in reason_routes
            )
        ),
        opportunity_ids=tuple(item.opportunity_id.value for item in opportunity_tuple),
        opportunity_scopes=tuple(
            sorted(
                item.opportunity_id.value + "@" + item.scope.hash_binding().sha256
                for item in opportunity_tuple
            )
        ),
        opportunity_values=tuple(
            sorted(
                item.opportunity_id.value
                + "@"
                + canonical_json_bytes(
                    {
                        "state": item.potential_value_state.value,
                        "value": (
                            item.potential_value.to_json_value()
                            if item.potential_value is not None
                            else None
                        ),
                    },
                    expected_members={"state", "value"},
                ).decode("ascii")
                for item in opportunity_tuple
            )
        ),
        handling_flags=tuple(item.value for item in flag_tuple),
        human_review_requirements=tuple(item.value for item in review_tuple),
        closure_state=(closure.reason.value if closure is not None else "NONE"),
        rule_pack_binding=rule_pack_hash_binding(),
        reason_registry_version=registries.reason_registry_version,
        transition_registry_version=registries.transition_registry_version,
    )
    output_binding = _output_binding(
        state=state,
        transition=transition,
        append_transitions=append_transitions,
        reasons=reason_set,
        reason_routes=reason_routes,
        opportunities=opportunity_tuple,
        flags=flag_tuple,
        reviews=review_tuple,
        closure=closure,
        aggregate_state=aggregate_state,
        aggregate=aggregate,
        selection_state=selection_state,
        explanation=explanation,
    )
    return DOIEvaluation(
        evaluation_id=request.evaluation_id,
        snapshot_id=request.snapshot.snapshot_id,
        run_id=request.snapshot.run_id,
        order_id=request.snapshot.order_id,
        state=state,
        transition=transition,
        append_transition=registries.transition_ref("TR-027"),
        append_transitions=append_transitions,
        reasons=reason_set,
        reason_routes=reason_routes,
        opportunities=opportunity_tuple,
        handling_flags=flag_tuple,
        human_review_requirements=review_tuple,
        closure_proposal=closure,
        aggregate_potential_state=aggregate_state,
        aggregate_potential=aggregate,
        scenario_selection_state=selection_state,
        explanation=explanation,
        input_binding=request.hash_binding(),
        output_binding=output_binding,
        rule_pack=VersionBinding("rule_pack", DOI_RULE_PACK_VERSION),
        rule_pack_binding=rule_pack_hash_binding(),
    )


__all__ = [
    "DOIEvaluationError",
    "DOIRuleVersionUnavailable",
    "OPPORTUNITY_ID_HASH_DOMAIN",
    "assert_reason_route_legal",
    "effective_reason_routes",
    "evaluate_doi",
    "opportunity_identity_binding",
]
