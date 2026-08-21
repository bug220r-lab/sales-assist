"""Product-only alternate knowledge and current-observation construction.

Relationship history contains only reserved synthetic product identities and minimized product
source references.  It cannot retain customer/order/contact material.  Exact-SKU rechecks bypass
the relationship model because the binding rules explicitly say that an exact SKU is not an
alternate relationship.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import ClassVar, cast

from synthetic_sales_assist.doi.identities import LineSnapshotId
from synthetic_sales_assist.doi.models import (
    AlternateAvailability,
    AlternateCandidate,
    AlternateObservationState,
    AlternateRelationshipState,
    AlternateRelationshipType,
    AlternateRevisionKind,
    AlternateValidityState,
    CompatibilityDecision,
    DOIActionContext,
    DOI_MODEL_SCHEMA_VERSION,
    HashKnownAnswer,
    OpportunityType,
    known_fact,
)
from synthetic_sales_assist.domain.canonical import (
    HashBinding,
    canonical_json_bytes,
    compare_retained_canonical_bytes,
    domain_hash,
    parse_canonical_json_bytes,
)
from synthetic_sales_assist.domain.identities import EvidenceId, SkuId
from synthetic_sales_assist.domain.numeric import Money, PositiveOrdinal, PositiveQuantity
from synthetic_sales_assist.domain.observed import (
    KnownObservedValue,
    NotApplicableObservedValue,
    ObservedTaggedValue,
    UnknownObservedValue,
)
from synthetic_sales_assist.domain.records import (
    ReasonSet,
    SourceKind,
    SourceObjectNamespace,
    SourceRef,
)
from synthetic_sales_assist.domain.registries import ReasonRef, load_doi_registries
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp


class ProductKnowledgeError(ValueError):
    """Non-reflecting product-knowledge rejection."""

    def __init__(self, code: str, *, reasons: ReasonSet | None = None) -> None:
        self.code = code
        self.reasons = reasons or ReasonSet()
        super().__init__(code)


def _reason_set(*codes: str) -> ReasonSet:
    registry = load_doi_registries()
    return ReasonSet(
        tuple(sorted((registry.reason_ref(code) for code in codes), key=lambda item: item.code))
    )


_SENSITIVE_PRODUCT_TOKENS = frozenset(
    {
        "ADDRESS",
        "CUSTOMER",
        "EMAIL",
        "FIRSTNAME",
        "JANE",
        "JOHN",
        "LASTNAME",
        "NAME",
        "PHONE",
        "SSN",
        "VIN",
    }
)
_PHONE_LIKE = re.compile(r"[0-9]{10,15}", re.ASCII)
_VIN_LIKE = re.compile(r"[A-HJ-NPR-Z0-9]{17}", re.ASCII)


def _require_privacy_safe_product_sku(value: object) -> SkuId:
    if type(value) is not SkuId:
        raise ProductKnowledgeError("PRODUCT_IDENTITY_INVALID")
    tokens = value.value.split("-")
    if (
        any(token in _SENSITIVE_PRODUCT_TOKENS for token in tokens)
        or any(_PHONE_LIKE.fullmatch(token) is not None for token in tokens)
        or any(_VIN_LIKE.fullmatch(token) is not None for token in tokens)
    ):
        raise ProductKnowledgeError("PRODUCT_IDENTITY_PRIVACY_REJECTED")
    return value


def _binding_json(binding: HashBinding) -> dict[str, str]:
    return {"domain": binding.domain, "sha256": binding.sha256}


def _require_product_source(source: object, *, candidate_sku: SkuId) -> SourceRef:
    _require_privacy_safe_product_sku(candidate_sku)
    if (
        type(source) is not SourceRef
        or source.source_kind is not SourceKind.SYNTHETIC_PRODUCT_FIXTURE
        or source.object_namespace is not SourceObjectNamespace.SYNTHETIC_PRODUCT
        or type(source.object_id) is not SkuId
        or source.object_id != candidate_sku
    ):
        raise ProductKnowledgeError("PRODUCT_ONLY_SOURCE_REQUIRED")
    return source


def _require_action_context_binding(
    binding: object,
    *,
    action_context_id: EvidenceId,
) -> HashBinding:
    if (
        type(binding) is not HashBinding
        or binding.domain != DOIActionContext.HASH_DOMAIN
    ):
        raise ProductKnowledgeError(
            "ACTION_CONTEXT_BINDING_INVALID",
            reasons=_reason_set("RC-110"),
        )
    decoded: object | None = None
    try:
        decoded = parse_canonical_json_bytes(binding.canonical_bytes)
    except (TypeError, ValueError):
        pass
    if (
        type(decoded) is not dict
        or decoded.get("action_context_id") != action_context_id.value
    ):
        raise ProductKnowledgeError(
            "ACTION_CONTEXT_BINDING_INVALID",
            reasons=_reason_set("RC-110"),
        )
    return binding


def _observed_json(value: ObservedTaggedValue[object]) -> dict[str, object]:
    result = value.to_mapping()
    known = result["value"]
    if type(known) is CanonicalTimestamp:
        result["value"] = cast(CanonicalTimestamp, known).value
    elif type(known) is Money:
        result["value"] = cast(Money, known).to_json_value()
    return result


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DOIAlternateRelationshipRevision:
    relationship_id: EvidenceId
    revision_id: EvidenceId
    revision_number: PositiveOrdinal
    predecessor_binding: HashBinding | None
    revision_kind: AlternateRevisionKind
    relationship_type: AlternateRelationshipType
    ordered_sku: SkuId
    candidate_sku: SkuId
    ordered_mfg: SkuId | None
    candidate_mfg: SkuId | None
    state: AlternateRelationshipState
    compatibility_review_required: bool
    evidence_source: SourceRef
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-alternate-relationship-revision/v1"

    def __post_init__(self) -> None:
        if (
            type(self.relationship_id) is not EvidenceId
            or type(self.revision_id) is not EvidenceId
            or type(self.revision_number) is not PositiveOrdinal
            or type(self.revision_kind) is not AlternateRevisionKind
            or type(self.relationship_type) is not AlternateRelationshipType
            or type(self.ordered_sku) is not SkuId
            or type(self.candidate_sku) is not SkuId
            or self.ordered_sku == self.candidate_sku
            or (self.ordered_mfg is not None and type(self.ordered_mfg) is not SkuId)
            or (self.candidate_mfg is not None and type(self.candidate_mfg) is not SkuId)
            or type(self.state) is not AlternateRelationshipState
            or type(self.compatibility_review_required) is not bool
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise ProductKnowledgeError("ALTERNATE_RELATIONSHIP_REVISION_INVALID")
        for product_id in (
            self.ordered_sku,
            self.candidate_sku,
            self.ordered_mfg,
            self.candidate_mfg,
        ):
            if product_id is not None:
                _require_privacy_safe_product_sku(product_id)
        _require_product_source(self.evidence_source, candidate_sku=self.candidate_sku)
        created = self.revision_number.value == 1
        if created != (self.predecessor_binding is None):
            raise ProductKnowledgeError("ALTERNATE_REVISION_PREDECESSOR_INVALID")
        if created != (self.revision_kind is AlternateRevisionKind.CREATED):
            raise ProductKnowledgeError("ALTERNATE_REVISION_KIND_INVALID")
        terminal_kind = {
            AlternateRevisionKind.SUPERSEDED: AlternateRelationshipState.SUPERSEDED,
            AlternateRevisionKind.INVALIDATED: AlternateRelationshipState.INVALIDATED,
        }
        expected_terminal = terminal_kind.get(self.revision_kind)
        if expected_terminal is not None and self.state is not expected_terminal:
            raise ProductKnowledgeError("ALTERNATE_REVISION_STATE_INVALID")
        if self.revision_kind in {AlternateRevisionKind.CREATED, AlternateRevisionKind.UPDATED}:
            if self.state is not AlternateRelationshipState.ACTIVE:
                raise ProductKnowledgeError("ALTERNATE_REVISION_STATE_INVALID")
        if self.relationship_type is AlternateRelationshipType.EXACT_MFG:
            if self.ordered_mfg is None or self.ordered_mfg != self.candidate_mfg:
                raise ProductKnowledgeError("EXACT_MFG_RELATIONSHIP_INVALID")
        if self.relationship_type is AlternateRelationshipType.FUNCTIONAL:
            if not self.compatibility_review_required:
                raise ProductKnowledgeError("FUNCTIONAL_COMPATIBILITY_REVIEW_REQUIRED")

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_mfg": self.candidate_mfg.value if self.candidate_mfg else None,
            "candidate_sku": self.candidate_sku.value,
            "compatibility_review_required": self.compatibility_review_required,
            "evidence_source": _binding_json(self.evidence_source.hash_binding()),
            "ordered_mfg": self.ordered_mfg.value if self.ordered_mfg else None,
            "ordered_sku": self.ordered_sku.value,
            "predecessor_binding": (
                _binding_json(self.predecessor_binding)
                if self.predecessor_binding is not None
                else None
            ),
            "relationship_id": self.relationship_id.value,
            "relationship_type": self.relationship_type.value,
            "revision_id": self.revision_id.value,
            "revision_kind": self.revision_kind.value,
            "revision_number": self.revision_number.to_json_value(),
            "schema_version": self.schema_version,
            "state": self.state.value,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), expected_members=set(self.to_dict()))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIAlternateRelationshipRevision(<closed>)"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DOIAlternateRelationship:
    relationship_id: EvidenceId
    relationship_type: AlternateRelationshipType
    ordered_sku: SkuId
    candidate_sku: SkuId
    revisions: tuple[DOIAlternateRelationshipRevision, ...]
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-alternate-relationship/v1"

    def __post_init__(self) -> None:
        if (
            type(self.relationship_id) is not EvidenceId
            or type(self.relationship_type) is not AlternateRelationshipType
            or type(self.ordered_sku) is not SkuId
            or type(self.candidate_sku) is not SkuId
            or type(self.revisions) is not tuple
            or not self.revisions
            or any(
                type(revision) is not DOIAlternateRelationshipRevision
                for revision in self.revisions
            )
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise ProductKnowledgeError("ALTERNATE_RELATIONSHIP_INVALID")
        for index, revision in enumerate(self.revisions, start=1):
            if (
                revision.relationship_id != self.relationship_id
                or revision.relationship_type is not self.relationship_type
                or revision.ordered_sku != self.ordered_sku
                or revision.candidate_sku != self.candidate_sku
                or revision.revision_number.value != index
            ):
                raise ProductKnowledgeError("ALTERNATE_RELATIONSHIP_HISTORY_INVALID")
            if index > 1:
                predecessor = self.revisions[index - 2]
                if revision.predecessor_binding != predecessor.hash_binding():
                    raise ProductKnowledgeError("ALTERNATE_RELATIONSHIP_HISTORY_INVALID")
                if predecessor.state is not AlternateRelationshipState.ACTIVE:
                    raise ProductKnowledgeError("ALTERNATE_RELATIONSHIP_TERMINAL")

    @property
    def current_revision(self) -> DOIAlternateRelationshipRevision:
        return self.revisions[-1]

    @property
    def last_mutation_reasons(self) -> ReasonSet:
        """Return the registered reason emitted by the creating/appending rule call."""

        return _reason_set("RC-107" if len(self.revisions) == 1 else "RC-108")

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_sku": self.candidate_sku.value,
            "ordered_sku": self.ordered_sku.value,
            "relationship_id": self.relationship_id.value,
            "relationship_type": self.relationship_type.value,
            "revision_bindings": [
                _binding_json(revision.hash_binding()) for revision in self.revisions
            ],
            "schema_version": self.schema_version,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), expected_members=set(self.to_dict()))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIAlternateRelationship(<closed>)"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DOIAlternateObservation:
    observation_id: EvidenceId
    action_context_id: EvidenceId
    action_context_binding: HashBinding
    relationship_revision_binding: HashBinding
    candidate_sku: SkuId
    state: AlternateObservationState
    observed_availability: ObservedTaggedValue[str]
    observed_eta: ObservedTaggedValue[CanonicalTimestamp]
    observed_price: ObservedTaggedValue[Money]
    observed_at: CanonicalTimestamp
    source: SourceRef
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-alternate-observation/v1"

    def __post_init__(self) -> None:
        if (
            type(self.observation_id) is not EvidenceId
            or type(self.action_context_id) is not EvidenceId
            or type(self.action_context_binding) is not HashBinding
            or self.action_context_binding.domain != DOIActionContext.HASH_DOMAIN
            or type(self.relationship_revision_binding) is not HashBinding
            or type(self.candidate_sku) is not SkuId
            or type(self.state) is not AlternateObservationState
            or type(self.observed_at) is not CanonicalTimestamp
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise ProductKnowledgeError("ALTERNATE_OBSERVATION_INVALID")
        _require_privacy_safe_product_sku(self.candidate_sku)
        _require_action_context_binding(
            self.action_context_binding,
            action_context_id=self.action_context_id,
        )
        _require_product_source(self.source, candidate_sku=self.candidate_sku)
        self._validate_observation(
            self.observed_availability,
            reason="RC-137",
            enum_type=AlternateAvailability,
            known_type=None,
        )
        self._validate_observation(
            self.observed_eta,
            reason="RC-138",
            enum_type=None,
            known_type=CanonicalTimestamp,
        )
        self._validate_observation(
            self.observed_price,
            reason="RC-136",
            enum_type=None,
            known_type=Money,
        )

    @staticmethod
    def _validate_observation(
        value: object,
        *,
        reason: str,
        enum_type: type[AlternateAvailability] | None,
        known_type: type[object] | None,
    ) -> None:
        if type(value) is UnknownObservedValue:
            if cast(UnknownObservedValue, value).reason_code != reason:
                raise ProductKnowledgeError("ALTERNATE_OBSERVATION_REASON_INVALID")
            return
        if type(value) is NotApplicableObservedValue:
            return
        if type(value) is not KnownObservedValue:
            raise ProductKnowledgeError("ALTERNATE_OBSERVATION_BRANCH_INVALID")
        known = cast(KnownObservedValue[object], value).value
        if enum_type is not None:
            enum_invalid = type(known) is not str
            if not enum_invalid:
                try:
                    enum_type(cast(str, known))
                except ValueError:
                    enum_invalid = True
            if enum_invalid:
                raise ProductKnowledgeError("ALTERNATE_OBSERVATION_VALUE_INVALID")
        elif type(known) is not known_type:
            raise ProductKnowledgeError("ALTERNATE_OBSERVATION_VALUE_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "action_context_binding": _binding_json(self.action_context_binding),
            "action_context_id": self.action_context_id.value,
            "candidate_sku": self.candidate_sku.value,
            "observation_id": self.observation_id.value,
            "observed_at": self.observed_at.value,
            "observed_availability": _observed_json(self.observed_availability),
            "observed_eta": _observed_json(self.observed_eta),
            "observed_price": _observed_json(self.observed_price),
            "relationship_revision_binding": _binding_json(
                self.relationship_revision_binding
            ),
            "schema_version": self.schema_version,
            "source": _binding_json(self.source.hash_binding()),
            "state": self.state.value,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), expected_members=set(self.to_dict()))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIAlternateObservation(<closed>)"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DOIExactSKUObservation:
    observation_id: EvidenceId
    action_context_id: EvidenceId
    action_context_binding: HashBinding
    ordered_line_id: LineSnapshotId
    ordered_sku: SkuId
    observed_sku: SkuId
    state: AlternateObservationState
    observed_availability: AlternateAvailability
    potential_unit_value: Money | None
    observed_at: CanonicalTimestamp
    source: SourceRef
    schema_version: str = DOI_MODEL_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-exact-sku-observation/v1"

    def __post_init__(self) -> None:
        if (
            type(self.observation_id) is not EvidenceId
            or type(self.action_context_id) is not EvidenceId
            or type(self.action_context_binding) is not HashBinding
            or self.action_context_binding.domain != DOIActionContext.HASH_DOMAIN
            or type(self.ordered_line_id) is not LineSnapshotId
            or type(self.ordered_sku) is not SkuId
            or type(self.observed_sku) is not SkuId
            or self.ordered_sku != self.observed_sku
            or type(self.state) is not AlternateObservationState
            or type(self.observed_availability) is not AlternateAvailability
            or (
                self.potential_unit_value is not None
                and type(self.potential_unit_value) is not Money
            )
            or type(self.observed_at) is not CanonicalTimestamp
            or self.schema_version != DOI_MODEL_SCHEMA_VERSION
        ):
            raise ProductKnowledgeError("EXACT_SKU_OBSERVATION_INVALID")
        _require_privacy_safe_product_sku(self.ordered_sku)
        _require_action_context_binding(
            self.action_context_binding,
            action_context_id=self.action_context_id,
        )
        _require_product_source(self.source, candidate_sku=self.observed_sku)

    def to_dict(self) -> dict[str, object]:
        return {
            "action_context_binding": _binding_json(self.action_context_binding),
            "action_context_id": self.action_context_id.value,
            "observation_id": self.observation_id.value,
            "observed_at": self.observed_at.value,
            "observed_availability": self.observed_availability.value,
            "observed_sku": self.observed_sku.value,
            "ordered_line_id": self.ordered_line_id.to_json_value(),
            "ordered_sku": self.ordered_sku.value,
            "potential_unit_value": (
                self.potential_unit_value.to_json_value()
                if self.potential_unit_value is not None
                else None
            ),
            "schema_version": self.schema_version,
            "source": _binding_json(self.source.hash_binding()),
            "state": self.state.value,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIExactSKUObservation(<closed>)"


def create_relationship(
    *,
    relationship_id: EvidenceId,
    revision_id: EvidenceId,
    relationship_type: AlternateRelationshipType,
    ordered_sku: SkuId,
    candidate_sku: SkuId,
    ordered_mfg: SkuId | None,
    candidate_mfg: SkuId | None,
    compatibility_review_required: bool,
    evidence_source: SourceRef,
) -> DOIAlternateRelationship:
    revision = DOIAlternateRelationshipRevision(
        relationship_id=relationship_id,
        revision_id=revision_id,
        revision_number=PositiveOrdinal(1),
        predecessor_binding=None,
        revision_kind=AlternateRevisionKind.CREATED,
        relationship_type=relationship_type,
        ordered_sku=ordered_sku,
        candidate_sku=candidate_sku,
        ordered_mfg=ordered_mfg,
        candidate_mfg=candidate_mfg,
        state=AlternateRelationshipState.ACTIVE,
        compatibility_review_required=compatibility_review_required,
        evidence_source=evidence_source,
    )
    return DOIAlternateRelationship(
        relationship_id=relationship_id,
        relationship_type=relationship_type,
        ordered_sku=ordered_sku,
        candidate_sku=candidate_sku,
        revisions=(revision,),
    )


def append_relationship_revision(
    relationship: DOIAlternateRelationship,
    *,
    revision_id: EvidenceId,
    revision_kind: AlternateRevisionKind,
    state: AlternateRelationshipState,
    compatibility_review_required: bool,
    evidence_source: SourceRef,
) -> DOIAlternateRelationship:
    if type(relationship) is not DOIAlternateRelationship:
        raise ProductKnowledgeError("ALTERNATE_RELATIONSHIP_INVALID")
    current = relationship.current_revision
    if current.state is not AlternateRelationshipState.ACTIVE:
        raise ProductKnowledgeError(
            "ALTERNATE_RELATIONSHIP_TERMINAL",
            reasons=_reason_set("RC-109"),
        )
    revision = DOIAlternateRelationshipRevision(
        relationship_id=relationship.relationship_id,
        revision_id=revision_id,
        revision_number=PositiveOrdinal(len(relationship.revisions) + 1),
        predecessor_binding=current.hash_binding(),
        revision_kind=revision_kind,
        relationship_type=relationship.relationship_type,
        ordered_sku=relationship.ordered_sku,
        candidate_sku=relationship.candidate_sku,
        ordered_mfg=current.ordered_mfg,
        candidate_mfg=current.candidate_mfg,
        state=state,
        compatibility_review_required=compatibility_review_required,
        evidence_source=evidence_source,
    )
    return DOIAlternateRelationship(
        relationship_id=relationship.relationship_id,
        relationship_type=relationship.relationship_type,
        ordered_sku=relationship.ordered_sku,
        candidate_sku=relationship.candidate_sku,
        revisions=relationship.revisions + (revision,),
    )


_OPPORTUNITY_BY_RELATIONSHIP = MappingProxyType(
    {
        AlternateRelationshipType.EXACT_MFG: OpportunityType.EXACT_MFG_ALTERNATE,
        AlternateRelationshipType.MFG_CROSS_REFERENCE: OpportunityType.MFG_CROSS_REFERENCE,
        AlternateRelationshipType.MFG_SUPERSESSION: OpportunityType.MFG_SUPERSESSION,
        AlternateRelationshipType.FUNCTIONAL: OpportunityType.FUNCTIONAL_ALTERNATE,
    }
)


def candidate_from_relationship(
    *,
    candidate_id: EvidenceId,
    relationship: DOIAlternateRelationship,
    observation: DOIAlternateObservation,
    ordered_line_id: LineSnapshotId,
    quantity: PositiveQuantity,
    compatibility_decision: CompatibilityDecision,
) -> AlternateCandidate:
    if (
        type(relationship) is not DOIAlternateRelationship
        or type(observation) is not DOIAlternateObservation
        or observation.relationship_revision_binding
        != relationship.current_revision.hash_binding()
        or observation.candidate_sku != relationship.candidate_sku
    ):
        raise ProductKnowledgeError("ALTERNATE_BINDING_INVALID")
    revision = relationship.current_revision
    if revision.state is not AlternateRelationshipState.ACTIVE:
        validity = AlternateValidityState.REJECTED
    elif compatibility_decision is CompatibilityDecision.REJECTED:
        validity = AlternateValidityState.REJECTED
    elif (
        revision.compatibility_review_required
        and compatibility_decision is not CompatibilityDecision.APPROVED
    ):
        validity = AlternateValidityState.COMPATIBILITY_REVIEW_REQUIRED
    else:
        validity = AlternateValidityState.VERIFIED
    price = (
        cast(Money, observation.observed_price.value)
        if type(observation.observed_price) is KnownObservedValue
        else None
    )
    unknown_codes = tuple(
        sorted(
            {
                cast(UnknownObservedValue, value).reason_code
                for value in (
                    observation.observed_availability,
                    observation.observed_eta,
                    observation.observed_price,
                )
                if type(value) is UnknownObservedValue
            }
        )
    )
    registries = load_doi_registries()
    availability = (
        AlternateAvailability(cast(str, observation.observed_availability.value))
        if type(observation.observed_availability) is KnownObservedValue
        else AlternateAvailability.UNKNOWN
    )
    return AlternateCandidate(
        candidate_id=candidate_id,
        opportunity_type=_OPPORTUNITY_BY_RELATIONSHIP[relationship.relationship_type],
        ordered_line_id=ordered_line_id,
        quantity=quantity,
        candidate_sku=relationship.candidate_sku,
        observed_availability=availability,
        validity=validity,
        compatibility_decision=compatibility_decision,
        relationship_revision_binding=revision.hash_binding(),
        observation_binding=observation.hash_binding(),
        current_observation=observation.state is AlternateObservationState.CURRENT,
        potential_value=price.multiply(quantity) if price is not None else None,
        unknown_reasons=tuple(registries.reason_ref(code) for code in unknown_codes),
    )


def exact_sku_candidate(
    *,
    candidate_id: EvidenceId,
    quantity: PositiveQuantity,
    observation: DOIExactSKUObservation,
) -> AlternateCandidate:
    if (
        type(observation) is not DOIExactSKUObservation
        or observation.state is not AlternateObservationState.CURRENT
        or observation.observed_availability is not AlternateAvailability.IN_STOCK
    ):
        raise ProductKnowledgeError("EXACT_SKU_RECHECK_INVALID")
    return AlternateCandidate(
        candidate_id=candidate_id,
        opportunity_type=OpportunityType.EXACT_SKU_RECHECK,
        ordered_line_id=observation.ordered_line_id,
        quantity=quantity,
        candidate_sku=observation.observed_sku,
        observed_availability=observation.observed_availability,
        validity=AlternateValidityState.VERIFIED,
        compatibility_decision=CompatibilityDecision.NOT_REQUIRED,
        relationship_revision_binding=None,
        observation_binding=observation.hash_binding(),
        current_observation=True,
        potential_value=(
            observation.potential_unit_value.multiply(quantity)
            if observation.potential_unit_value is not None
            else None
        ),
    )


def compare_knowledge_preimages(retained: HashBinding, candidate: HashBinding) -> bool:
    """Compare retained canonical bytes; digest equality alone never proves replay."""

    if type(retained) is not HashBinding or type(candidate) is not HashBinding:
        raise ProductKnowledgeError("KNOWLEDGE_HASH_BINDING_INVALID")
    if retained.domain != candidate.domain:
        return False
    return compare_retained_canonical_bytes(
        retained.sha256,
        retained.canonical_bytes,
        candidate.sha256,
        candidate.canonical_bytes,
    )


def knowledge_hash_contracts() -> MappingProxyType[str, str]:
    return MappingProxyType(
        {
            cls.__name__: cls.HASH_DOMAIN
            for cls in (
                DOIAlternateRelationshipRevision,
                DOIAlternateRelationship,
                DOIAlternateObservation,
                DOIExactSKUObservation,
            )
        }
    )


def knowledge_hash_fixtures() -> tuple[tuple[str, str, bytes, str], ...]:
    """Return actual representative-record KATs for every knowledge hash domain."""

    from decimal import Decimal

    from synthetic_sales_assist.doi.models import (
        model_action_context_fixture,
        not_applicable_fact,
    )
    from synthetic_sales_assist.domain.numeric import CURRENCY_REGISTRY_VERSION

    observed_at = CanonicalTimestamp("2026-08-20T14:15:16Z")
    context = model_action_context_fixture()
    ordered_sku = SkuId("SYN-SKU-DOI-KNOWLEDGE-KAT-ORDERED")
    candidate_sku = SkuId("SYN-SKU-DOI-KNOWLEDGE-KAT-CANDIDATE")
    canonical_mfg = SkuId("SYN-SKU-DOI-KNOWLEDGE-KAT-MFG")
    product_source = SourceRef.create(
        source_ref_id=EvidenceId("SYN-EVIDENCE-DOI-KNOWLEDGE-KAT-SOURCE"),
        source_kind=SourceKind.SYNTHETIC_PRODUCT_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_PRODUCT,
        object_id=candidate_sku,
    )
    relationship = create_relationship(
        relationship_id=EvidenceId("SYN-EVIDENCE-DOI-KNOWLEDGE-KAT-RELATIONSHIP"),
        revision_id=EvidenceId("SYN-EVIDENCE-DOI-KNOWLEDGE-KAT-REVISION"),
        relationship_type=AlternateRelationshipType.EXACT_MFG,
        ordered_sku=ordered_sku,
        candidate_sku=candidate_sku,
        ordered_mfg=canonical_mfg,
        candidate_mfg=canonical_mfg,
        compatibility_review_required=False,
        evidence_source=product_source,
    )
    observation = DOIAlternateObservation(
        observation_id=EvidenceId("SYN-EVIDENCE-DOI-KNOWLEDGE-KAT-OBSERVATION"),
        action_context_id=context.action_context_id,
        action_context_binding=context.hash_binding(),
        relationship_revision_binding=relationship.current_revision.hash_binding(),
        candidate_sku=candidate_sku,
        state=AlternateObservationState.CURRENT,
        observed_availability=known_fact(AlternateAvailability.IN_STOCK),
        observed_eta=not_applicable_fact(),
        observed_price=known_fact(
            Money(Decimal("10.00"), "USD", CURRENCY_REGISTRY_VERSION, 2)
        ),
        observed_at=observed_at,
        source=product_source,
    )
    exact_source = SourceRef.create(
        source_ref_id=EvidenceId("SYN-EVIDENCE-DOI-KNOWLEDGE-KAT-EXACT-SOURCE"),
        source_kind=SourceKind.SYNTHETIC_PRODUCT_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_PRODUCT,
        object_id=ordered_sku,
    )
    exact_observation = DOIExactSKUObservation(
        observation_id=EvidenceId(
            "SYN-EVIDENCE-DOI-KNOWLEDGE-KAT-EXACT-OBSERVATION"
        ),
        action_context_id=context.action_context_id,
        action_context_binding=context.hash_binding(),
        ordered_line_id=LineSnapshotId(
            EvidenceId("SYN-EVIDENCE-DOI-KNOWLEDGE-KAT-LINE")
        ),
        ordered_sku=ordered_sku,
        observed_sku=ordered_sku,
        state=AlternateObservationState.CURRENT,
        observed_availability=AlternateAvailability.IN_STOCK,
        potential_unit_value=Money(
            Decimal("10.00"),
            "USD",
            CURRENCY_REGISTRY_VERSION,
            2,
        ),
        observed_at=observed_at,
        source=exact_source,
    )
    records = (
        relationship.current_revision,
        relationship,
        observation,
        exact_observation,
    )
    rows = tuple(
        (
            type(record).__name__,
            record.hash_binding().domain,
            record.canonical_bytes(),
            record.hash_binding().sha256,
        )
        for record in records
    )
    contracts = knowledge_hash_contracts()
    if {name for name, _, _, _ in rows} != set(contracts):
        raise ProductKnowledgeError("KNOWLEDGE_KAT_INVENTORY_INVALID")
    return tuple(sorted(rows, key=lambda row: row[0]))


def knowledge_hash_known_answer(record: object) -> HashKnownAnswer:
    """Build a KAT row from one deterministic representative knowledge fixture."""

    contracts = knowledge_hash_contracts()
    record_name = type(record).__name__
    expected_domain = contracts.get(record_name)
    canonical_method = getattr(record, "canonical_bytes", None)
    binding_method = getattr(record, "hash_binding", None)
    if (
        expected_domain is None
        or not callable(canonical_method)
        or not callable(binding_method)
    ):
        raise ProductKnowledgeError("KNOWLEDGE_KAT_RECORD_INVALID")
    canonical = canonical_method()
    binding = binding_method()
    if (
        type(canonical) is not bytes
        or type(binding) is not HashBinding
        or binding.domain != expected_domain
        or binding.canonical_bytes != canonical
    ):
        raise ProductKnowledgeError("KNOWLEDGE_KAT_RECORD_INVALID")
    return HashKnownAnswer(record_name, binding.domain, canonical, binding.sha256)


__all__ = [
    "DOIAlternateObservation",
    "DOIAlternateRelationship",
    "DOIAlternateRelationshipRevision",
    "DOIExactSKUObservation",
    "ProductKnowledgeError",
    "append_relationship_revision",
    "candidate_from_relationship",
    "compare_knowledge_preimages",
    "create_relationship",
    "exact_sku_candidate",
    "knowledge_hash_contracts",
    "knowledge_hash_fixtures",
    "knowledge_hash_known_answer",
]
