"""Immutable DOI intervention, value, and resulting-order histories.

These reducers record verified facts only.  They neither infer an action from an opportunity
nor expose an external mutation capability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import ClassVar

from synthetic_sales_assist.doi.identities import DoiOrderId, LineSnapshotId
from synthetic_sales_assist.doi.models import (
    ActionContextCompletionTrigger,
    ActionContextCloseReason,
    ActionContextEventType,
    ActionContextState,
    ActionVerificationState,
    DOIActionContext,
    DOIActionContextEvent,
    DOIActionContextHistory,
    DOIHumanFactEvent,
    DOIHumanFactHistory,
    DOIModelError,
    DOIOccurrenceGuard,
    HumanAuthorityGrant,
    HumanFactEventType,
    HumanFactResultCode,
    HumanFactUsageKind,
    InterventionStatus,
    InterventionType,
    RepRelation,
    ResultingOrderLinkSearchState,
    ResultingOrderLinkState,
    StructuredHumanFact,
    ValueEventType,
    ValueVerificationState,
    reduce_action_context,
    reduce_human_fact,
    model_action_context_fixture,
    verify_synthetic_human_authority,
)
from synthetic_sales_assist.domain.canonical import (
    HashBinding,
    canonical_json_bytes,
    domain_hash,
    parse_canonical_json_bytes,
)
from synthetic_sales_assist.domain.identities import (
    EvidenceId,
    InteractionId,
    OrderId,
    RepId,
)
from synthetic_sales_assist.domain.numeric import (
    CURRENCY_REGISTRY_VERSION,
    Money,
    PositiveQuantity,
)
from synthetic_sales_assist.domain.records import (
    ReasonSet,
    SourceKind,
    SourceObjectNamespace,
    SourceRef,
)
from synthetic_sales_assist.domain.registries import ReasonRef, load_doi_registries
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.domain.tokens import ImmutableStrEnum
from synthetic_sales_assist.safety.content import ProhibitedInputError, assert_payload_safe


INTERVENTION_SCHEMA_VERSION = "doi-intervention-history/v1"
INTERVENTION_HASH_KNOWN_ANSWERS = MappingProxyType(
    {
        "ActionVerificationEvent": (
            "acc8473252ca010d492d79441854ce6b6364d2d660387478d4b3cd82e170cfc5"
        ),
        "ActionVerificationMaterial": (
            "b017fe0c6083e0157d02f27657c9bb751c6bd34a2bce090e3e187f48040875ff"
        ),
        "AuthorizedHumanExactValueRecord": (
            "16149709eeedd581d7adcb351b812b6ed6bdbaab9df338f85c847e9a594ab400"
        ),
        "AuthorizedHumanResultingLinkEvidence": (
            "2b649297c8b0dc2604d5d7291a24b32ac82767e1c98279733b686366a1550fc0"
        ),
        "DOIIntervention": "2b612f69ade3da3131fb42bb46dbbf3bce5b9877b8946fd23e37f64b42f7764e",
        "DOIResultingOrderLink": (
            "b78f69800927dd7a30b9809147a863fb4bc907303fd644f93b134b22aa1131f8"
        ),
        "DOIResultingOrderLinkSearch": (
            "217d71dce5288d81d27b61afe470ac12250dbdeace587f764280640602cb9500"
        ),
        "LogicalEvidenceKey": "5731825247b8b7b96b19e4b5ea601758bbf0e8c858341ba36ad925b31c2d66e0",
        "ResultingLinkSearchEvent": (
            "0493447868bf2a839bd8f683c08df13bf264b90eba0b60839adee14c4c8ec8bc"
        ),
        "ResultingLinkSearchEvidence": (
            "0e6e1c8ee88dd8c9f4940e42474fbe9265c91cae6bec1464c9367cf28ac7c9cf"
        ),
        "ResultingOrderLinkRevision": (
            "d3fea5803855fa73794f90988e6152fc39b0b5e4a3ea9c2fd67df7f164f2e45d"
        ),
        "SystemExactValueRecord": (
            "dd3a9b2602334397f3602b074bd96975dbe41cb6cdf292d136ce3f37c6c1756a"
        ),
        "SystemResultingLinkEvidence": (
            "041a77cde24768af55739e918e0ad307e7e17f05927ded839d9f0945cbcb3dc3"
        ),
        "TargetRepObservation": (
            "e866d7aabeaef21336428f5c405ef38a6b23969759ad2624af42d279a873c303"
        ),
        "TargetRepVerificationProof": (
            "d9ec0e137fe883455a4d67dc236b0c2e578e7ba06aae4161b749b0f7fa4df559"
        ),
        "ValueEvent": (
            "8a5b9a46f910160655c3d67d0bc3240d6f407dc44dd854e8b4e9e3d7edab8e66"
        ),
        "VerificationEvidence": "635906a600e061798d1b8804f7b479c3248c2e61cbcbd8b7d97ac7141b9ad992",
    }
)


class InterventionError(RuntimeError):
    """A closed intervention-history rejection."""

    def __init__(self, code: str, *, reasons: ReasonSet | None = None) -> None:
        self.code = code
        self.reasons = reasons or ReasonSet()
        super().__init__(f"DOI intervention rejected: {code}")


class EvidenceKeyKind(ImmutableStrEnum):
    ACTION = "ACTION"
    ORIGINAL_VALUE = "ORIGINAL_VALUE"
    VALUE_CORRECTION = "VALUE_CORRECTION"
    REVERSAL = "REVERSAL"
    RESULTING_ORDER_LINK = "RESULTING_ORDER_LINK"
    RESULTING_ORDER_MAPPING = "RESULTING_ORDER_MAPPING"


class ValueCorrectionKind(ImmutableStrEnum):
    ORIGINAL_VALUE_CORRECTED = "ORIGINAL_VALUE_CORRECTED"
    REVERSAL_CORRECTED = "REVERSAL_CORRECTED"
    REVERSAL_VOIDED = "REVERSAL_VOIDED"


class HumanValueInexactKind(ImmutableStrEnum):
    """Closed input classifications that can never become verified value facts."""

    ESTIMATED = "ESTIMATED"
    ROUNDED = "ROUNDED"
    RANGED = "RANGED"
    OTHERWISE_INEXACT = "OTHERWISE_INEXACT"


def reject_inexact_human_value(kind: HumanValueInexactKind) -> None:
    """Reject a non-exact human amount before any value event is allocated."""

    if type(kind) is not HumanValueInexactKind:
        raise InterventionError("HUMAN_VALUE_INPUT_CLASSIFICATION_INVALID")
    raise InterventionError(
        "HUMAN_VALUE_NOT_EXACT",
        reasons=_reason_set("RC-067"),
    )


class TargetRepProofScope(ImmutableStrEnum):
    RESULTING_ORDER = "RESULTING_ORDER"
    REPLACEMENT_LINE = "REPLACEMENT_LINE"


TARGET_REP_ID = RepId("SYN-REP-TARGET-REP")


_ACCEPTED_HUMAN_FACT_TOKEN = object()


@dataclass(frozen=True, slots=True, init=False, repr=False)
class AcceptedHumanFactProof:
    """Sealed proof that a structured fact survived its owning history reducer."""

    history: DOIHumanFactHistory = field(repr=False)
    current_event: DOIHumanFactEvent = field(repr=False)
    fact: StructuredHumanFact = field(repr=False)
    _issuer_token: object = field(repr=False, compare=False)

    def __new__(cls) -> AcceptedHumanFactProof:
        raise InterventionError(
            "HUMAN_FACT_REDUCER_PROOF_REQUIRED",
            reasons=_reason_set("RC-112"),
        )

    @classmethod
    def from_history(cls, history: DOIHumanFactHistory) -> AcceptedHumanFactProof:
        if type(history) is not DOIHumanFactHistory or not history.events:
            raise InterventionError(
                "HUMAN_FACT_REDUCER_PROOF_REQUIRED",
                reasons=_reason_set("RC-112"),
            )
        try:
            rebuilt = DOIHumanFactHistory(stream_id=history.stream_id)
            for event in history.events:
                reduced = reduce_human_fact(rebuilt, event)
                if reduced.replayed:
                    raise DOIModelError("DOI_HUMAN_FACT_REPLAY_IN_SOURCE_HISTORY")
                rebuilt = reduced.history
        except (DOIModelError, TypeError, ValueError):
            raise InterventionError(
                "HUMAN_FACT_REDUCER_PROOF_REQUIRED",
                reasons=_reason_set("RC-112"),
            ) from None
        if rebuilt != history or history.projection is None:
            raise InterventionError(
                "HUMAN_FACT_REDUCER_PROOF_REQUIRED",
                reasons=_reason_set("RC-112"),
            )
        fact = history.projection.current_fact
        if fact.result_code is not HumanFactResultCode.APPROVED:
            raise InterventionError(
                "HUMAN_FACT_APPROVAL_REQUIRED",
                reasons=_reason_set("RC-112"),
            )
        instance = object.__new__(cls)
        object.__setattr__(instance, "history", history)
        object.__setattr__(instance, "current_event", history.events[-1])
        object.__setattr__(instance, "fact", fact)
        object.__setattr__(instance, "_issuer_token", _ACCEPTED_HUMAN_FACT_TOKEN)
        return instance

    def __repr__(self) -> str:
        return "AcceptedHumanFactProof(<redacted>)"


def _reason_set(*codes: str) -> ReasonSet:
    registries = load_doi_registries()
    return ReasonSet(
        tuple(
            sorted(
                (registries.reason_ref(code) for code in codes),
                key=lambda item: item.code,
            )
        )
    )


def _money(value: Money | None) -> dict[str, object] | None:
    return None if value is None else value.to_json_value()


def _hash(value: HashBinding) -> dict[str, str]:
    return {"domain": value.domain, "sha256": value.sha256}


def _assert_safe_binding(binding: HashBinding, *, domain: str, code: str) -> None:
    """Validate retained binding bytes before an intervention object can keep them."""

    if type(binding) is not HashBinding or binding.domain != domain:
        raise InterventionError(code)
    try:
        payload = parse_canonical_json_bytes(binding.canonical_bytes)
        assert_payload_safe(payload)
    except (ProhibitedInputError, TypeError, ValueError):
        raise InterventionError(code) from None


def require_verified_action(verification: ActionVerificationState) -> None:
    """Reject an unverified action before intervention allocation."""

    if verification not in {
        ActionVerificationState.SYSTEM_VERIFIED,
        ActionVerificationState.HUMAN_VERIFIED,
    }:
        raise InterventionError(
            "ACTION_EVIDENCE_VERIFICATION_INVALID",
            reasons=_reason_set("RC-060"),
        )


@dataclass(frozen=True, slots=True, repr=False)
class LogicalEvidenceKey:
    key_id: EvidenceId
    owner_id: EvidenceId
    occurrence_id: EvidenceId
    kind: EvidenceKeyKind
    schema_version: str = INTERVENTION_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-logical-evidence-key/v1"

    def __post_init__(self) -> None:
        if (
            type(self.key_id) is not EvidenceId
            or type(self.owner_id) is not EvidenceId
            or type(self.occurrence_id) is not EvidenceId
            or type(self.kind) is not EvidenceKeyKind
            or self.schema_version != INTERVENTION_SCHEMA_VERSION
        ):
            raise InterventionError("EVIDENCE_KEY_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "key_id": self.key_id.value,
            "kind": self.kind.value,
            "occurrence_id": self.occurrence_id.value,
            "owner_id": self.owner_id.value,
            "schema_version": self.schema_version,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "LogicalEvidenceKey(<redacted>)"


_ACTION_EVIDENCE_TOKEN = object()
_COMPLETED_HUMAN_ACTION_PROOF_TOKEN = object()
_COMPLETED_SYSTEM_ACTION_PROOF_TOKEN = object()


def _completion_required() -> InterventionError:
    return InterventionError(
        "HUMAN_ACTION_COMPLETION_PROOF_INVALID",
        reasons=_reason_set("RC-060"),
    )


def _system_completion_required() -> InterventionError:
    return InterventionError(
        "SYSTEM_ACTION_COMPLETION_PROOF_INVALID",
        reasons=_reason_set("RC-060"),
    )


def _replay_completed_action_history(
    *,
    history: DOIActionContextHistory,
    expected_trigger: ActionContextCompletionTrigger,
    system_proof: bool,
) -> tuple[DOIActionContext, DOIActionContext, DOIActionContextEvent]:
    """Replay one exact two-event action history from an empty reducer state."""

    def invalid() -> InterventionError:
        return _system_completion_required() if system_proof else _completion_required()

    if type(history) is not DOIActionContextHistory or len(history.events) < 2:
        raise invalid()
    opening_event = history.events[0]
    completion_event = history.events[-1]
    if (
        opening_event.event_type is not ActionContextEventType.OPENED
        or completion_event.event_type is not ActionContextEventType.COMPLETED
        or completion_event.completion_trigger is not expected_trigger
    ):
        raise invalid()
    try:
        rebuilt = DOIActionContextHistory(action_context_id=history.action_context_id)
        authority_context: DOIActionContext | None = None
        for event in history.events:
            if event is completion_event:
                authority_context = rebuilt.projection
            reduction = reduce_action_context(rebuilt, event)
            if reduction.replayed:
                raise DOIModelError("DOI_ACTION_CONTEXT_REPLAY_IN_SOURCE_HISTORY")
            rebuilt = reduction.history
    except (DOIModelError, TypeError, ValueError):
        raise invalid() from None
    completed_context = rebuilt.projection
    if (
        type(authority_context) is not DOIActionContext
        or type(completed_context) is not DOIActionContext
        or rebuilt != history
        or authority_context.state is not ActionContextState.OPEN
        or completed_context.state is not ActionContextState.CLOSED_COMPLETED
        or completed_context.completion_trigger is not expected_trigger
        or completion_event.predecessor_binding
        != history.events[-2].hash_binding()
        or completion_event.sequence != history.events[-2].sequence + 1
        or (
            completion_event.occurred_at.epoch_seconds,
            completion_event.occurred_at.nanosecond,
        )
        < (
            opening_event.occurred_at.epoch_seconds,
            opening_event.occurred_at.nanosecond,
        )
    ):
        raise invalid()
    return authority_context, completed_context, completion_event


@dataclass(frozen=True, slots=True, init=False, repr=False)
class CompletedSystemActionProof:
    """Closed proof of one reducer-accepted deterministic system completion."""

    history: DOIActionContextHistory = field(repr=False)
    opening_context: DOIActionContext = field(repr=False)
    completed_context: DOIActionContext = field(repr=False)
    completion_event: DOIActionContextEvent = field(repr=False)
    _issuer_token: object = field(repr=False, compare=False)

    def __new__(cls) -> CompletedSystemActionProof:
        raise _system_completion_required()

    @classmethod
    def from_history(
        cls,
        *,
        history: DOIActionContextHistory,
    ) -> CompletedSystemActionProof:
        opening_context, completed_context, completion_event = (
            _replay_completed_action_history(
                history=history,
                expected_trigger=ActionContextCompletionTrigger.SYSTEM_VERIFIED,
                system_proof=True,
            )
        )
        instance = object.__new__(cls)
        object.__setattr__(instance, "history", history)
        object.__setattr__(instance, "opening_context", opening_context)
        object.__setattr__(instance, "completed_context", completed_context)
        object.__setattr__(instance, "completion_event", completion_event)
        object.__setattr__(
            instance,
            "_issuer_token",
            _COMPLETED_SYSTEM_ACTION_PROOF_TOKEN,
        )
        return instance

    def __repr__(self) -> str:
        return "CompletedSystemActionProof(<redacted>)"


@dataclass(frozen=True, slots=True, init=False, repr=False)
class CompletedHumanActionProof:
    """Closed proof of one authority-bound, reducer-accepted human completion."""

    history: DOIActionContextHistory = field(repr=False)
    authority: HumanAuthorityGrant = field(repr=False)
    authority_context: DOIActionContext = field(repr=False)
    completed_context: DOIActionContext = field(repr=False)
    completion_event: DOIActionContextEvent = field(repr=False)
    _issuer_token: object = field(repr=False, compare=False)

    def __new__(cls) -> CompletedHumanActionProof:
        raise _completion_required()

    @classmethod
    def from_history(
        cls,
        *,
        history: DOIActionContextHistory,
        authority: HumanAuthorityGrant,
    ) -> CompletedHumanActionProof:
        if type(authority) is not HumanAuthorityGrant:
            raise _completion_required()
        authority_context, completed_context, completion_event = (
            _replay_completed_action_history(
                history=history,
                expected_trigger=ActionContextCompletionTrigger.HUMAN_ACCEPTED,
                system_proof=False,
            )
        )
        if (
            authority.action_context_id != authority_context.action_context_id
            or authority.action_context_binding != authority_context.hash_binding()
            or completion_event.human_authority_binding != authority.hash_binding()
            or (
                completion_event.occurred_at.epoch_seconds,
                completion_event.occurred_at.nanosecond,
            )
            < (
                authority.granted_at.epoch_seconds,
                authority.granted_at.nanosecond,
            )
        ):
            raise InterventionError(
                "HUMAN_VERIFICATION_UNAUTHORIZED",
                reasons=_reason_set("RC-112"),
            )
        instance = object.__new__(cls)
        object.__setattr__(instance, "history", history)
        object.__setattr__(instance, "authority", authority)
        object.__setattr__(instance, "authority_context", authority_context)
        object.__setattr__(instance, "completed_context", completed_context)
        object.__setattr__(instance, "completion_event", completion_event)
        object.__setattr__(
            instance,
            "_issuer_token",
            _COMPLETED_HUMAN_ACTION_PROOF_TOKEN,
        )
        return instance

    def __repr__(self) -> str:
        return "CompletedHumanActionProof(<redacted>)"


@dataclass(frozen=True, slots=True, init=False, repr=False)
class ActionVerificationMaterial:
    """Closed synthetic action fact bound to its context, source, and authority."""

    evidence_id: EvidenceId
    intervention_id: EvidenceId
    opportunity_id: EvidenceId
    intervention_type: InterventionType
    action_context_id: EvidenceId
    action_context_binding: HashBinding
    source: SourceRef
    verification: ActionVerificationState
    occurred_at: CanonicalTimestamp | None
    authority_binding: HashBinding | None
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-action-verification-material/v1"

    def __new__(cls) -> ActionVerificationMaterial:
        raise InterventionError("ACTION_EVIDENCE_FACTORY_REQUIRED")

    @classmethod
    def _create(
        cls,
        *,
        evidence_id: EvidenceId,
        intervention_id: EvidenceId,
        opportunity_id: EvidenceId,
        intervention_type: InterventionType,
        action_context: DOIActionContext,
        source: SourceRef,
        verification: ActionVerificationState,
        occurred_at: CanonicalTimestamp | None,
        authority: HumanAuthorityGrant | None,
        completed_action_proof: (
            CompletedSystemActionProof | CompletedHumanActionProof | None
        ),
        factory_capability: object,
    ) -> ActionVerificationMaterial:
        if factory_capability is not _ACTION_EVIDENCE_TOKEN:
            raise InterventionError("ACTION_EVIDENCE_FACTORY_REQUIRED")
        if (
            type(evidence_id) is not EvidenceId
            or type(intervention_id) is not EvidenceId
            or type(opportunity_id) is not EvidenceId
            or type(intervention_type) is not InterventionType
            or type(action_context) is not DOIActionContext
            or type(source) is not SourceRef
            or (
                occurred_at is not None
                and type(occurred_at) is not CanonicalTimestamp
            )
        ):
            raise InterventionError("ACTION_EVIDENCE_INPUT_INVALID")
        if (
            action_context.opportunity_id != opportunity_id
            or action_context.state is not ActionContextState.CLOSED_COMPLETED
        ):
            raise InterventionError("ACTION_EVIDENCE_CONTEXT_INVALID")
        require_verified_action(verification)
        expected_trigger = {
            ActionVerificationState.SYSTEM_VERIFIED: (
                ActionContextCompletionTrigger.SYSTEM_VERIFIED
            ),
            ActionVerificationState.HUMAN_VERIFIED: (
                ActionContextCompletionTrigger.HUMAN_ACCEPTED
            ),
        }.get(verification)
        if expected_trigger is None:
            raise InterventionError("ACTION_EVIDENCE_VERIFICATION_INVALID")
        authority_binding: HashBinding | None
        if verification is ActionVerificationState.SYSTEM_VERIFIED:
            if authority is not None:
                raise InterventionError("ACTION_EVIDENCE_AUTHORITY_INVALID")
            if (
                type(completed_action_proof) is not CompletedSystemActionProof
                or completed_action_proof._issuer_token
                is not _COMPLETED_SYSTEM_ACTION_PROOF_TOKEN
                or completed_action_proof.completed_context != action_context
            ):
                raise _system_completion_required()
            if (
                source.source_kind is not SourceKind.SYNTHETIC_ORDER_FIXTURE
                or source.object_namespace
                is not SourceObjectNamespace.SYNTHETIC_ORDER
                or source.object_id != action_context.order_id.value
            ):
                raise InterventionError("ACTION_EVIDENCE_SOURCE_INVALID")
            authority_binding = None
        else:
            if (
                type(completed_action_proof) is not CompletedHumanActionProof
                or completed_action_proof._issuer_token
                is not _COMPLETED_HUMAN_ACTION_PROOF_TOKEN
                or completed_action_proof.completed_context != action_context
                or completed_action_proof.authority != authority
            ):
                raise _completion_required()
            proof = completed_action_proof
            if (
                type(authority) is not HumanAuthorityGrant
                or authority.source != source
            ):
                raise InterventionError(
                    "HUMAN_VERIFICATION_UNAUTHORIZED",
                    reasons=_reason_set("RC-112"),
                )
            authority_binding = authority.hash_binding()
        instance = object.__new__(cls)
        object.__setattr__(instance, "evidence_id", evidence_id)
        object.__setattr__(instance, "intervention_id", intervention_id)
        object.__setattr__(instance, "opportunity_id", opportunity_id)
        object.__setattr__(instance, "intervention_type", intervention_type)
        object.__setattr__(instance, "action_context_id", action_context.action_context_id)
        object.__setattr__(instance, "action_context_binding", action_context.hash_binding())
        object.__setattr__(instance, "source", source)
        object.__setattr__(instance, "verification", verification)
        object.__setattr__(instance, "occurred_at", occurred_at)
        object.__setattr__(instance, "authority_binding", authority_binding)
        object.__setattr__(instance, "schema_version", INTERVENTION_SCHEMA_VERSION)
        instance.__post_init__()
        try:
            assert_payload_safe(
                {
                    "action_context_id": instance.action_context_id.value,
                    "evidence_id": instance.evidence_id.value,
                    "intervention_id": instance.intervention_id.value,
                    "opportunity_id": instance.opportunity_id.value,
                    "source_object_id": instance.source.object_id.value,
                }
            )
        except ProhibitedInputError:
            raise InterventionError("ACTION_EVIDENCE_PRIVACY_REJECTED") from None
        return instance

    def __post_init__(self) -> None:
        if (
            type(self.evidence_id) is not EvidenceId
            or type(self.intervention_id) is not EvidenceId
            or type(self.opportunity_id) is not EvidenceId
            or type(self.intervention_type) is not InterventionType
            or type(self.action_context_id) is not EvidenceId
            or type(self.action_context_binding) is not HashBinding
            or self.action_context_binding.domain != DOIActionContext.HASH_DOMAIN
            or type(self.source) is not SourceRef
            or self.verification
            not in {
                ActionVerificationState.SYSTEM_VERIFIED,
                ActionVerificationState.HUMAN_VERIFIED,
            }
            or (
                self.occurred_at is not None
                and type(self.occurred_at) is not CanonicalTimestamp
            )
            or (
                self.authority_binding is not None
                and (
                    type(self.authority_binding) is not HashBinding
                    or self.authority_binding.domain != HumanAuthorityGrant.HASH_DOMAIN
                )
            )
            or self.schema_version != INTERVENTION_SCHEMA_VERSION
        ):
            raise InterventionError("ACTION_EVIDENCE_INVALID")
        if (
            self.verification is ActionVerificationState.SYSTEM_VERIFIED
        ) != (self.authority_binding is None):
            raise InterventionError("ACTION_EVIDENCE_AUTHORITY_PARTITION_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "action_context_binding": _hash(self.action_context_binding),
            "action_context_id": self.action_context_id.value,
            "authority_binding": (
                None if self.authority_binding is None else _hash(self.authority_binding)
            ),
            "evidence_id": self.evidence_id.value,
            "intervention_id": self.intervention_id.value,
            "intervention_type": self.intervention_type.value,
            "occurred_at": None if self.occurred_at is None else self.occurred_at.value,
            "opportunity_id": self.opportunity_id.value,
            "schema_version": self.schema_version,
            "source": _hash(self.source.hash_binding()),
            "verification": self.verification.value,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "ActionVerificationMaterial(<redacted>)"


@dataclass(frozen=True, slots=True, init=False, repr=False)
class VerificationEvidence:
    material: ActionVerificationMaterial
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-verification-evidence/v1"

    def __new__(cls) -> VerificationEvidence:
        raise InterventionError("VERIFICATION_EVIDENCE_FACTORY_REQUIRED")

    @classmethod
    def _from_material(
        cls,
        material: ActionVerificationMaterial,
    ) -> VerificationEvidence:
        if type(material) is not ActionVerificationMaterial:
            raise InterventionError("VERIFICATION_EVIDENCE_MATERIAL_INVALID")
        instance = object.__new__(cls)
        object.__setattr__(instance, "material", material)
        object.__setattr__(instance, "schema_version", INTERVENTION_SCHEMA_VERSION)
        instance.__post_init__()
        return instance

    @classmethod
    def from_system_observation(
        cls,
        *,
        evidence_id: EvidenceId,
        intervention_id: EvidenceId,
        opportunity_id: EvidenceId,
        intervention_type: InterventionType,
        completed_action_proof: CompletedSystemActionProof,
        source: SourceRef,
        occurred_at: CanonicalTimestamp | None,
    ) -> VerificationEvidence:
        if (
            type(completed_action_proof) is not CompletedSystemActionProof
            or completed_action_proof._issuer_token
            is not _COMPLETED_SYSTEM_ACTION_PROOF_TOKEN
        ):
            raise _system_completion_required()
        return cls._from_material(
            ActionVerificationMaterial._create(
                evidence_id=evidence_id,
                intervention_id=intervention_id,
                opportunity_id=opportunity_id,
                intervention_type=intervention_type,
                action_context=completed_action_proof.completed_context,
                source=source,
                verification=ActionVerificationState.SYSTEM_VERIFIED,
                occurred_at=occurred_at,
                authority=None,
                completed_action_proof=completed_action_proof,
                factory_capability=_ACTION_EVIDENCE_TOKEN,
            )
        )

    @classmethod
    def from_authorized_human(
        cls,
        *,
        evidence_id: EvidenceId,
        intervention_id: EvidenceId,
        opportunity_id: EvidenceId,
        intervention_type: InterventionType,
        completed_action_proof: CompletedHumanActionProof,
        source: SourceRef,
        occurred_at: CanonicalTimestamp | None,
    ) -> VerificationEvidence:
        if (
            type(completed_action_proof) is not CompletedHumanActionProof
            or completed_action_proof._issuer_token
            is not _COMPLETED_HUMAN_ACTION_PROOF_TOKEN
        ):
            raise _completion_required()
        return cls._from_material(
            ActionVerificationMaterial._create(
                evidence_id=evidence_id,
                intervention_id=intervention_id,
                opportunity_id=opportunity_id,
                intervention_type=intervention_type,
                action_context=completed_action_proof.completed_context,
                source=source,
                verification=ActionVerificationState.HUMAN_VERIFIED,
                occurred_at=occurred_at,
                authority=completed_action_proof.authority,
                completed_action_proof=completed_action_proof,
                factory_capability=_ACTION_EVIDENCE_TOKEN,
            )
        )

    def __post_init__(self) -> None:
        if (
            type(self.material) is not ActionVerificationMaterial
            or self.schema_version != INTERVENTION_SCHEMA_VERSION
        ):
            raise InterventionError("VERIFICATION_EVIDENCE_INVALID")

    @property
    def evidence_id(self) -> EvidenceId:
        return self.material.evidence_id

    @property
    def verification(self) -> ActionVerificationState:
        return self.material.verification

    @property
    def occurred_at(self) -> CanonicalTimestamp | None:
        return self.material.occurred_at

    @property
    def content(self) -> HashBinding:
        return self.material.hash_binding()

    def to_dict(self) -> dict[str, object]:
        return {
            "material": _hash(self.material.hash_binding()),
            "schema_version": self.schema_version,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "VerificationEvidence(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ActionVerificationEvent:
    event_id: EvidenceId
    intervention_id: EvidenceId
    opportunity_id: EvidenceId
    intervention_type: InterventionType
    key: LogicalEvidenceKey
    evidence: VerificationEvidence
    schema_version: str = INTERVENTION_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-action-verification-event/v1"

    def __post_init__(self) -> None:
        if (
            type(self.event_id) is not EvidenceId
            or type(self.intervention_id) is not EvidenceId
            or type(self.opportunity_id) is not EvidenceId
            or type(self.intervention_type) is not InterventionType
            or type(self.key) is not LogicalEvidenceKey
            or type(self.evidence) is not VerificationEvidence
            or self.key.kind is not EvidenceKeyKind.ACTION
            or self.key.owner_id != self.intervention_id
            or self.key.occurrence_id != self.evidence.evidence_id
            or self.evidence.material.intervention_id != self.intervention_id
            or self.evidence.material.opportunity_id != self.opportunity_id
            or self.evidence.material.intervention_type is not self.intervention_type
            or self.schema_version != INTERVENTION_SCHEMA_VERSION
        ):
            raise InterventionError("ACTION_VERIFICATION_EVENT_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id.value,
            "evidence": _hash(self.evidence.hash_binding()),
            "intervention_id": self.intervention_id.value,
            "intervention_type": self.intervention_type.value,
            "key": _hash(self.key.hash_binding()),
            "opportunity_id": self.opportunity_id.value,
            "schema_version": self.schema_version,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "ActionVerificationEvent(<redacted>)"


def _validate_value_claim_shape(
    *,
    intervention: DOIIntervention,
    event_type: ValueEventType,
    amount: Money,
    predecessor_event: ValueEvent | None,
    correction_kind: ValueCorrectionKind | None,
) -> None:
    if (
        type(intervention) is not DOIIntervention
        or intervention.intervention_type is InterventionType.DS_SEPARATION
        or type(event_type) is not ValueEventType
        or type(amount) is not Money
        or amount.minor_units < 0
        or (
            predecessor_event is not None
            and type(predecessor_event) is not ValueEvent
        )
        or (
            correction_kind is not None
            and type(correction_kind) is not ValueCorrectionKind
        )
    ):
        raise InterventionError("VALUE_RECORD_INVALID")
    if event_type is ValueEventType.INITIAL_VERIFIED_VALUE:
        legal = predecessor_event is None and correction_kind is None
    elif event_type is ValueEventType.CORRECTION:
        legal = predecessor_event is not None and correction_kind is not None
    else:
        legal = predecessor_event is not None and correction_kind is None
    if not legal:
        raise InterventionError("VALUE_RECORD_PREDECESSOR_INVALID")


@dataclass(frozen=True, slots=True, init=False, repr=False)
class SystemExactValueRecord:
    """Exact Money observed by the synthetic order boundary, not caller-labelled proof."""

    record_id: EvidenceId
    intervention_id: EvidenceId
    intervention_action_binding: HashBinding
    action_context_binding: HashBinding
    subject_order_id: DoiOrderId
    event_type: ValueEventType
    amount: Money
    predecessor_event_id: EvidenceId | None
    predecessor_event_binding: HashBinding | None
    correction_kind: ValueCorrectionKind | None
    observed_at: CanonicalTimestamp
    source: SourceRef
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-system-exact-value-record/v1"

    def __new__(cls) -> SystemExactValueRecord:
        raise InterventionError("SYSTEM_VALUE_RECORD_FACTORY_REQUIRED")

    @classmethod
    def from_order_observation(
        cls,
        *,
        record_id: EvidenceId,
        intervention: DOIIntervention,
        completed_action_context: DOIActionContext,
        event_type: ValueEventType,
        amount: Money,
        predecessor_event: ValueEvent | None,
        correction_kind: ValueCorrectionKind | None,
        observed_at: CanonicalTimestamp,
        source: SourceRef,
    ) -> SystemExactValueRecord:
        _validate_value_claim_shape(
            intervention=intervention,
            event_type=event_type,
            amount=amount,
            predecessor_event=predecessor_event,
            correction_kind=correction_kind,
        )
        action_binding = intervention.action_events[0].hash_binding()
        expected_context_binding = (
            intervention.action_events[0].evidence.material.action_context_binding
        )
        if (
            type(record_id) is not EvidenceId
            or type(completed_action_context) is not DOIActionContext
            or completed_action_context.state is not ActionContextState.CLOSED_COMPLETED
            or completed_action_context.hash_binding() != expected_context_binding
            or completed_action_context.opportunity_id != intervention.opportunity_id
            or completed_action_context.intervention_type is not intervention.intervention_type
            or type(observed_at) is not CanonicalTimestamp
            or type(source) is not SourceRef
            or source.source_kind is not SourceKind.SYNTHETIC_ORDER_FIXTURE
            or source.object_namespace is not SourceObjectNamespace.SYNTHETIC_ORDER
            or source.object_id != completed_action_context.order_id.value
        ):
            raise InterventionError("SYSTEM_VALUE_RECORD_OWNER_INVALID")
        instance = object.__new__(cls)
        object.__setattr__(instance, "record_id", record_id)
        object.__setattr__(instance, "intervention_id", intervention.intervention_id)
        object.__setattr__(instance, "intervention_action_binding", action_binding)
        object.__setattr__(
            instance,
            "action_context_binding",
            completed_action_context.hash_binding(),
        )
        object.__setattr__(instance, "subject_order_id", completed_action_context.order_id)
        object.__setattr__(instance, "event_type", event_type)
        object.__setattr__(instance, "amount", amount)
        object.__setattr__(
            instance,
            "predecessor_event_id",
            None if predecessor_event is None else predecessor_event.event_id,
        )
        object.__setattr__(
            instance,
            "predecessor_event_binding",
            None if predecessor_event is None else predecessor_event.hash_binding(),
        )
        object.__setattr__(instance, "correction_kind", correction_kind)
        object.__setattr__(instance, "observed_at", observed_at)
        object.__setattr__(instance, "source", source)
        object.__setattr__(instance, "schema_version", INTERVENTION_SCHEMA_VERSION)
        instance.__post_init__()
        return instance

    def __post_init__(self) -> None:
        if (
            type(self.record_id) is not EvidenceId
            or type(self.intervention_id) is not EvidenceId
            or type(self.intervention_action_binding) is not HashBinding
            or self.intervention_action_binding.domain != ActionVerificationEvent.HASH_DOMAIN
            or type(self.action_context_binding) is not HashBinding
            or self.action_context_binding.domain != DOIActionContext.HASH_DOMAIN
            or type(self.subject_order_id) is not DoiOrderId
            or type(self.event_type) is not ValueEventType
            or type(self.amount) is not Money
            or type(self.observed_at) is not CanonicalTimestamp
            or type(self.source) is not SourceRef
            or self.source.source_kind is not SourceKind.SYNTHETIC_ORDER_FIXTURE
            or self.source.object_namespace is not SourceObjectNamespace.SYNTHETIC_ORDER
            or self.source.object_id != self.subject_order_id.value
            or self.schema_version != INTERVENTION_SCHEMA_VERSION
        ):
            raise InterventionError("SYSTEM_VALUE_RECORD_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "action_context_binding": _hash(self.action_context_binding),
            "amount": self.amount.to_json_value(),
            "correction_kind": (
                None if self.correction_kind is None else self.correction_kind.value
            ),
            "event_type": self.event_type.value,
            "intervention_action_binding": _hash(self.intervention_action_binding),
            "intervention_id": self.intervention_id.value,
            "observed_at": self.observed_at.value,
            "predecessor_event_binding": (
                None
                if self.predecessor_event_binding is None
                else _hash(self.predecessor_event_binding)
            ),
            "predecessor_event_id": (
                None
                if self.predecessor_event_id is None
                else self.predecessor_event_id.value
            ),
            "record_id": self.record_id.value,
            "schema_version": self.schema_version,
            "source": _hash(self.source.hash_binding()),
            "subject_order_id": self.subject_order_id.to_json_value(),
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "SystemExactValueRecord(<redacted>)"


@dataclass(frozen=True, slots=True, init=False, repr=False)
class AuthorizedHumanExactValueRecord:
    """Exact Money asserted through one reducer-retained structured human fact."""

    record_id: EvidenceId
    intervention_id: EvidenceId
    intervention_action_binding: HashBinding
    human_fact_binding: HashBinding
    human_fact_event_binding: HashBinding
    subject_order_id: DoiOrderId
    event_type: ValueEventType
    amount: Money
    predecessor_event_id: EvidenceId | None
    predecessor_event_binding: HashBinding | None
    correction_kind: ValueCorrectionKind | None
    occurred_at: CanonicalTimestamp
    source: SourceRef
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-authorized-human-exact-value-record/v1"

    def __new__(cls) -> AuthorizedHumanExactValueRecord:
        raise InterventionError("HUMAN_VALUE_RECORD_FACTORY_REQUIRED")

    @classmethod
    def from_reduced_human_fact(
        cls,
        *,
        record_id: EvidenceId,
        intervention: DOIIntervention,
        human_fact_proof: AcceptedHumanFactProof,
        event_type: ValueEventType,
        amount: Money,
        predecessor_event: ValueEvent | None,
        correction_kind: ValueCorrectionKind | None,
    ) -> AuthorizedHumanExactValueRecord:
        _validate_value_claim_shape(
            intervention=intervention,
            event_type=event_type,
            amount=amount,
            predecessor_event=predecessor_event,
            correction_kind=correction_kind,
        )
        if (
            type(record_id) is not EvidenceId
            or type(human_fact_proof) is not AcceptedHumanFactProof
            or human_fact_proof._issuer_token is not _ACCEPTED_HUMAN_FACT_TOKEN
        ):
            raise InterventionError(
                "HUMAN_VALUE_RECORD_AUTHORITY_INVALID",
                reasons=_reason_set("RC-112"),
            )
        fact = human_fact_proof.fact
        if (
            fact.action_context.opportunity_id != intervention.opportunity_id
            or fact.action_context.intervention_type is not intervention.intervention_type
            or fact.source != fact.authority_grant.source
        ):
            raise InterventionError(
                "HUMAN_VALUE_RECORD_OWNER_INVALID",
                reasons=_reason_set("RC-112"),
            )
        instance = object.__new__(cls)
        object.__setattr__(instance, "record_id", record_id)
        object.__setattr__(instance, "intervention_id", intervention.intervention_id)
        object.__setattr__(
            instance,
            "intervention_action_binding",
            intervention.action_events[0].hash_binding(),
        )
        object.__setattr__(instance, "human_fact_binding", fact.hash_binding())
        object.__setattr__(
            instance,
            "human_fact_event_binding",
            human_fact_proof.current_event.hash_binding(),
        )
        object.__setattr__(instance, "subject_order_id", fact.order_id)
        object.__setattr__(instance, "event_type", event_type)
        object.__setattr__(instance, "amount", amount)
        object.__setattr__(
            instance,
            "predecessor_event_id",
            None if predecessor_event is None else predecessor_event.event_id,
        )
        object.__setattr__(
            instance,
            "predecessor_event_binding",
            None if predecessor_event is None else predecessor_event.hash_binding(),
        )
        object.__setattr__(instance, "correction_kind", correction_kind)
        object.__setattr__(instance, "occurred_at", fact.occurred_at)
        object.__setattr__(instance, "source", fact.source)
        object.__setattr__(instance, "schema_version", INTERVENTION_SCHEMA_VERSION)
        instance.__post_init__()
        return instance

    def __post_init__(self) -> None:
        if (
            type(self.record_id) is not EvidenceId
            or type(self.intervention_id) is not EvidenceId
            or type(self.intervention_action_binding) is not HashBinding
            or self.intervention_action_binding.domain != ActionVerificationEvent.HASH_DOMAIN
            or type(self.human_fact_binding) is not HashBinding
            or self.human_fact_binding.domain != StructuredHumanFact.HASH_DOMAIN
            or type(self.human_fact_event_binding) is not HashBinding
            or self.human_fact_event_binding.domain != DOIHumanFactEvent.HASH_DOMAIN
            or type(self.subject_order_id) is not DoiOrderId
            or type(self.event_type) is not ValueEventType
            or type(self.amount) is not Money
            or type(self.occurred_at) is not CanonicalTimestamp
            or type(self.source) is not SourceRef
            or self.source.source_kind is not SourceKind.SYNTHETIC_INTERACTION_FIXTURE
            or self.source.object_namespace is not SourceObjectNamespace.SYNTHETIC_INTERACTION
            or self.schema_version != INTERVENTION_SCHEMA_VERSION
        ):
            raise InterventionError("HUMAN_VALUE_RECORD_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "amount": self.amount.to_json_value(),
            "correction_kind": (
                None if self.correction_kind is None else self.correction_kind.value
            ),
            "event_type": self.event_type.value,
            "human_fact_binding": _hash(self.human_fact_binding),
            "human_fact_event_binding": _hash(self.human_fact_event_binding),
            "intervention_action_binding": _hash(self.intervention_action_binding),
            "intervention_id": self.intervention_id.value,
            "occurred_at": self.occurred_at.value,
            "predecessor_event_binding": (
                None
                if self.predecessor_event_binding is None
                else _hash(self.predecessor_event_binding)
            ),
            "predecessor_event_id": (
                None
                if self.predecessor_event_id is None
                else self.predecessor_event_id.value
            ),
            "record_id": self.record_id.value,
            "schema_version": self.schema_version,
            "source": _hash(self.source.hash_binding()),
            "subject_order_id": self.subject_order_id.to_json_value(),
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "AuthorizedHumanExactValueRecord(<redacted>)"


type ExactValueRecord = SystemExactValueRecord | AuthorizedHumanExactValueRecord


_VALUE_EVENT_TOKEN = object()


@dataclass(frozen=True, slots=True, init=False, repr=False)
class ValueEvent:
    event_id: EvidenceId
    intervention_id: EvidenceId
    key: LogicalEvidenceKey
    event_type: ValueEventType
    amount: Money
    verification: ValueVerificationState
    predecessor_event_id: EvidenceId | None
    predecessor_event_binding: HashBinding | None
    correction_kind: ValueCorrectionKind | None
    record: ExactValueRecord = field(repr=False)
    occurred_at: CanonicalTimestamp
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-value-event/v1"

    def __new__(cls) -> ValueEvent:
        raise InterventionError("VALUE_EVENT_FACTORY_REQUIRED")

    @classmethod
    def from_system_record(
        cls,
        *,
        event_id: EvidenceId,
        key_id: EvidenceId,
        record: SystemExactValueRecord,
    ) -> ValueEvent:
        return cls._from_record(
            event_id=event_id,
            key_id=key_id,
            record=record,
            verification=ValueVerificationState.SYSTEM_VERIFIED,
            factory_capability=_VALUE_EVENT_TOKEN,
        )

    @classmethod
    def from_authorized_human_record(
        cls,
        *,
        event_id: EvidenceId,
        key_id: EvidenceId,
        record: AuthorizedHumanExactValueRecord,
    ) -> ValueEvent:
        return cls._from_record(
            event_id=event_id,
            key_id=key_id,
            record=record,
            verification=ValueVerificationState.HUMAN_VERIFIED,
            factory_capability=_VALUE_EVENT_TOKEN,
        )

    @classmethod
    def _from_record(
        cls,
        *,
        event_id: EvidenceId,
        key_id: EvidenceId,
        record: ExactValueRecord,
        verification: ValueVerificationState,
        factory_capability: object,
    ) -> ValueEvent:
        if (
            factory_capability is not _VALUE_EVENT_TOKEN
            or type(event_id) is not EvidenceId
            or type(key_id) is not EvidenceId
            or type(record)
            not in {SystemExactValueRecord, AuthorizedHumanExactValueRecord}
        ):
            raise InterventionError("VALUE_EVENT_FACTORY_REQUIRED")
        expected_verification = (
            ValueVerificationState.SYSTEM_VERIFIED
            if type(record) is SystemExactValueRecord
            else ValueVerificationState.HUMAN_VERIFIED
        )
        if verification is not expected_verification:
            raise InterventionError("VALUE_EVENT_VERIFICATION_INVALID")
        if record.event_type is ValueEventType.INITIAL_VERIFIED_VALUE:
            key_kind = EvidenceKeyKind.ORIGINAL_VALUE
        elif (
            record.event_type is ValueEventType.CORRECTION
            and record.correction_kind is ValueCorrectionKind.ORIGINAL_VALUE_CORRECTED
        ):
            key_kind = EvidenceKeyKind.VALUE_CORRECTION
        else:
            key_kind = EvidenceKeyKind.REVERSAL
        instance = object.__new__(cls)
        object.__setattr__(instance, "event_id", event_id)
        object.__setattr__(instance, "intervention_id", record.intervention_id)
        object.__setattr__(
            instance,
            "key",
            LogicalEvidenceKey(
                key_id=key_id,
                owner_id=record.intervention_id,
                occurrence_id=record.record_id,
                kind=key_kind,
            ),
        )
        object.__setattr__(instance, "event_type", record.event_type)
        object.__setattr__(instance, "amount", record.amount)
        object.__setattr__(instance, "verification", verification)
        object.__setattr__(
            instance,
            "predecessor_event_id",
            record.predecessor_event_id,
        )
        object.__setattr__(
            instance,
            "predecessor_event_binding",
            record.predecessor_event_binding,
        )
        object.__setattr__(instance, "correction_kind", record.correction_kind)
        object.__setattr__(instance, "record", record)
        object.__setattr__(
            instance,
            "occurred_at",
            record.observed_at
            if type(record) is SystemExactValueRecord
            else record.occurred_at,
        )
        object.__setattr__(instance, "schema_version", INTERVENTION_SCHEMA_VERSION)
        instance.__post_init__()
        return instance

    def __post_init__(self) -> None:
        if (
            type(self.event_id) is not EvidenceId
            or type(self.intervention_id) is not EvidenceId
            or type(self.key) is not LogicalEvidenceKey
            or type(self.event_type) is not ValueEventType
            or type(self.amount) is not Money
            or self.verification
            not in {
                ValueVerificationState.SYSTEM_VERIFIED,
                ValueVerificationState.HUMAN_VERIFIED,
            }
            or type(self.record)
            not in {SystemExactValueRecord, AuthorizedHumanExactValueRecord}
            or type(self.occurred_at) is not CanonicalTimestamp
            or self.schema_version != INTERVENTION_SCHEMA_VERSION
        ):
            raise InterventionError("VALUE_EVENT_INVALID")
        record = self.record
        expected_verification = (
            ValueVerificationState.SYSTEM_VERIFIED
            if type(record) is SystemExactValueRecord
            else ValueVerificationState.HUMAN_VERIFIED
        )
        if (
            self.intervention_id != record.intervention_id
            or self.key.owner_id != self.intervention_id
            or self.key.occurrence_id != record.record_id
            or self.event_type is not record.event_type
            or self.amount != record.amount
            or self.verification is not expected_verification
            or self.predecessor_event_id != record.predecessor_event_id
            or self.predecessor_event_binding != record.predecessor_event_binding
            or self.correction_kind is not record.correction_kind
        ):
            raise InterventionError("VALUE_EVENT_RECORD_BINDING_INVALID")

    @property
    def exact(self) -> bool:
        """All constructible value events are exact by construction."""

        return True

    @property
    def evidence(self) -> HashBinding:
        return self.record.hash_binding()

    def to_dict(self) -> dict[str, object]:
        return {
            "amount": self.amount.to_json_value(),
            "correction_kind": (
                None if self.correction_kind is None else self.correction_kind.value
            ),
            "event_id": self.event_id.value,
            "event_type": self.event_type.value,
            "evidence": _hash(self.evidence),
            "exact": True,
            "intervention_id": self.intervention_id.value,
            "key": _hash(self.key.hash_binding()),
            "occurred_at": self.occurred_at.value,
            "predecessor_event_binding": (
                None
                if self.predecessor_event_binding is None
                else _hash(self.predecessor_event_binding)
            ),
            "predecessor_event_id": (
                None
                if self.predecessor_event_id is None
                else self.predecessor_event_id.value
            ),
            "schema_version": self.schema_version,
            "verification": self.verification.value,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "ValueEvent(<redacted>)"


def require_verified_reversal_record(
    intervention: DOIIntervention,
    record: ExactValueRecord | None,
) -> ExactValueRecord:
    """Gate a detected removal on typed exact reversal evidence.

    ``None`` represents a potential removal/cancellation for which no exact system or
    reducer-authorized human record has yet been retained.  It cannot decrement value.
    """

    if type(intervention) is not DOIIntervention:
        raise InterventionError("REVERSAL_OWNER_INVALID")
    if record is None:
        raise InterventionError(
            "REVERSAL_VERIFICATION_REQUIRED",
            reasons=_reason_set("RC-077"),
        )
    if (
        type(record) not in {SystemExactValueRecord, AuthorizedHumanExactValueRecord}
        or record.intervention_id != intervention.intervention_id
        or record.intervention_action_binding
        != intervention.action_events[0].hash_binding()
        or record.event_type
        not in {
            ValueEventType.PARTIAL_REVERSAL,
            ValueEventType.FULL_REVERSAL,
            ValueEventType.CORRECTION,
        }
    ):
        raise InterventionError(
            "REVERSAL_VERIFICATION_REQUIRED",
            reasons=_reason_set("RC-077"),
        )
    return record


@dataclass(frozen=True, slots=True)
class InterventionValueProjection:
    verification: ValueVerificationState
    authoritative_original: Money | None
    reversed_value: Money | None
    net_value: Money | None
    authoritative_event_id: EvidenceId | None

    def __post_init__(self) -> None:
        for value in (self.authoritative_original, self.reversed_value, self.net_value):
            if value is not None and type(value) is not Money:
                raise InterventionError("VALUE_PROJECTION_INVALID")
        if (
            self.authoritative_event_id is not None
            and type(self.authoritative_event_id) is not EvidenceId
        ):
            raise InterventionError("VALUE_PROJECTION_INVALID")
        if self.verification is ValueVerificationState.NOT_APPLICABLE:
            if any(
                value is not None
                for value in (
                    self.authoritative_original,
                    self.reversed_value,
                    self.net_value,
                    self.authoritative_event_id,
                )
            ):
                raise InterventionError("VALUE_PROJECTION_INVALID")
        elif self.verification is ValueVerificationState.UNVERIFIED:
            if self.authoritative_original is not None or self.net_value is not None:
                raise InterventionError("VALUE_PROJECTION_INVALID")
        elif None in {
            self.authoritative_original,
            self.reversed_value,
            self.net_value,
            self.authoritative_event_id,
        }:
            raise InterventionError("VALUE_PROJECTION_INVALID")


@dataclass(frozen=True, slots=True, repr=False)
class DOIIntervention:
    intervention_id: EvidenceId
    opportunity_id: EvidenceId
    intervention_type: InterventionType
    status: InterventionStatus
    action_verification: ActionVerificationState
    action_occurred_at: CanonicalTimestamp | None
    action_events: tuple[ActionVerificationEvent, ...]
    value_events: tuple[ValueEvent, ...]
    value: InterventionValueProjection
    schema_version: str = INTERVENTION_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-intervention/v1"

    def __post_init__(self) -> None:
        if (
            type(self.intervention_id) is not EvidenceId
            or type(self.opportunity_id) is not EvidenceId
            or type(self.intervention_type) is not InterventionType
            or type(self.status) is not InterventionStatus
            or self.action_verification
            not in {
                ActionVerificationState.SYSTEM_VERIFIED,
                ActionVerificationState.HUMAN_VERIFIED,
            }
            or (
                self.action_occurred_at is not None
                and type(self.action_occurred_at) is not CanonicalTimestamp
            )
            or type(self.action_events) is not tuple
            or not self.action_events
            or any(type(event) is not ActionVerificationEvent for event in self.action_events)
            or type(self.value_events) is not tuple
            or any(type(event) is not ValueEvent for event in self.value_events)
            or type(self.value) is not InterventionValueProjection
            or self.schema_version != INTERVENTION_SCHEMA_VERSION
        ):
            raise InterventionError("INTERVENTION_INVALID")
        if any(
            event.intervention_id != self.intervention_id
            or event.opportunity_id != self.opportunity_id
            or event.intervention_type is not self.intervention_type
            for event in self.action_events
        ):
            raise InterventionError("INTERVENTION_ACTION_HISTORY_INVALID")
        if any(event.intervention_id != self.intervention_id for event in self.value_events):
            raise InterventionError("INTERVENTION_VALUE_HISTORY_INVALID")
        if self.intervention_type is InterventionType.DS_SEPARATION:
            if self.value.verification is not ValueVerificationState.NOT_APPLICABLE:
                raise InterventionError("DS_VALUE_MUST_BE_NOT_APPLICABLE")
        elif self.value.verification is ValueVerificationState.NOT_APPLICABLE:
            raise InterventionError("CREDIT_VALUE_PARTITION_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "action_event_hashes": [_hash(event.hash_binding()) for event in self.action_events],
            "action_occurred_at": (
                None if self.action_occurred_at is None else self.action_occurred_at.value
            ),
            "action_verification": self.action_verification.value,
            "intervention_id": self.intervention_id.value,
            "intervention_type": self.intervention_type.value,
            "opportunity_id": self.opportunity_id.value,
            "schema_version": self.schema_version,
            "status": self.status.value,
            "value": {
                "authoritative_event_id": (
                    None
                    if self.value.authoritative_event_id is None
                    else self.value.authoritative_event_id.value
                ),
                "authoritative_original": _money(self.value.authoritative_original),
                "net_value": _money(self.value.net_value),
                "reversed_value": _money(self.value.reversed_value),
                "verification": self.value.verification.value,
            },
            "value_event_hashes": [_hash(event.hash_binding()) for event in self.value_events],
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIIntervention(<redacted>)"


@dataclass(frozen=True, slots=True)
class InterventionResult:
    intervention: DOIIntervention
    reasons: ReasonSet
    replayed: bool


def record_verified_intervention(
    existing: DOIIntervention | None,
    event: ActionVerificationEvent,
) -> InterventionResult:
    """Create/reuse an intervention only from an exact verified action event."""

    if existing is not None and type(existing) is not DOIIntervention:
        raise InterventionError("INTERVENTION_EXISTING_INVALID")
    if type(event) is not ActionVerificationEvent:
        raise InterventionError("ACTION_EVENT_INVALID")
    reason = (
        "RC-061"
        if event.evidence.verification is ActionVerificationState.SYSTEM_VERIFIED
        else "RC-062"
    )
    if existing is None:
        value = InterventionValueProjection(
            verification=(
                ValueVerificationState.NOT_APPLICABLE
                if event.intervention_type is InterventionType.DS_SEPARATION
                else ValueVerificationState.UNVERIFIED
            ),
            authoritative_original=None,
            reversed_value=None,
            net_value=None,
            authoritative_event_id=None,
        )
        return InterventionResult(
            intervention=DOIIntervention(
                intervention_id=event.intervention_id,
                opportunity_id=event.opportunity_id,
                intervention_type=event.intervention_type,
                status=InterventionStatus.VERIFIED_ACTIVE,
                action_verification=event.evidence.verification,
                action_occurred_at=event.evidence.occurred_at,
                action_events=(event,),
                value_events=(),
                value=value,
            ),
            reasons=_reason_set(reason),
            replayed=False,
        )
    if (
        existing.intervention_id != event.intervention_id
        or existing.opportunity_id != event.opportunity_id
        or existing.intervention_type is not event.intervention_type
    ):
        raise InterventionError("INTERVENTION_NATURAL_KEY_CONFLICT", reasons=_reason_set("RC-102"))
    prior = next((item for item in existing.action_events if item.event_id == event.event_id), None)
    if prior is not None:
        if prior.canonical_bytes() != event.canonical_bytes():
            raise InterventionError("ACTION_OCCURRENCE_CONFLICT", reasons=_reason_set("RC-102"))
        return InterventionResult(existing, _reason_set(reason), True)
    duplicate = next(
        (
            item
            for item in existing.action_events
            if item.key.hash_binding().sha256 == event.key.hash_binding().sha256
            and item.evidence.content == event.evidence.content
        ),
        None,
    )
    if duplicate is not None:
        return InterventionResult(existing, _reason_set("RC-076"), True)
    raise InterventionError("ACTION_NATURAL_KEY_CONFLICT", reasons=_reason_set("RC-102"))


def _zero_like(value: Money) -> Money:
    return Money.from_minor_units(
        0,
        currency_code=value.currency_code,
        registry_version=value.registry_version,
        scale=value.scale,
    )


def _money_identity(value: Money) -> tuple[str, str, int]:
    return (value.currency_code, value.registry_version, value.scale)


def _reversal_ledger(
    events: tuple[ValueEvent, ...],
) -> tuple[
    dict[EvidenceId, Money],
    dict[EvidenceId, EvidenceId],
    dict[EvidenceId, EvidenceId],
]:
    """Return active root amounts, event-to-root, and current root tails."""

    active: dict[EvidenceId, Money] = {}
    event_roots: dict[EvidenceId, EvidenceId] = {}
    tails: dict[EvidenceId, EvidenceId] = {}
    for event in events:
        if event.event_type in {
            ValueEventType.PARTIAL_REVERSAL,
            ValueEventType.FULL_REVERSAL,
        }:
            root = event.event_id
            active[root] = event.amount
            event_roots[event.event_id] = root
            tails[root] = event.event_id
        elif (
            event.event_type is ValueEventType.CORRECTION
            and event.correction_kind
            in {
                ValueCorrectionKind.REVERSAL_CORRECTED,
                ValueCorrectionKind.REVERSAL_VOIDED,
            }
        ):
            predecessor = event.predecessor_event_id
            if predecessor is None or predecessor not in event_roots:
                raise InterventionError(
                    "REVERSAL_PREDECESSOR_CONFLICT",
                    reasons=_reason_set("RC-111"),
                )
            root = event_roots[predecessor]
            if tails.get(root) != predecessor:
                raise InterventionError(
                    "REVERSAL_PREDECESSOR_CONFLICT",
                    reasons=_reason_set("RC-111"),
                )
            event_roots[event.event_id] = root
            tails[root] = event.event_id
            if event.correction_kind is ValueCorrectionKind.REVERSAL_VOIDED:
                active.pop(root, None)
            else:
                active[root] = event.amount
    return active, event_roots, tails


def _sum_reversals(original: Money, events: tuple[ValueEvent, ...]) -> Money:
    active, _, _ = _reversal_ledger(events)
    result = _zero_like(original)
    for root in sorted(active, key=lambda item: item.value):
        result = result + active[root]
    return result


def _authoritative_original(
    events: tuple[ValueEvent, ...],
) -> tuple[ValueEvent, ValueVerificationState, tuple[str, ...]]:
    originals = tuple(
        event
        for event in events
        if event.event_type is ValueEventType.INITIAL_VERIFIED_VALUE
        or (
            event.event_type is ValueEventType.CORRECTION
            and event.correction_kind is ValueCorrectionKind.ORIGINAL_VALUE_CORRECTED
        )
    )
    if not originals:
        raise InterventionError("VALUE_ORIGINAL_MISSING")
    systems = tuple(
        event
        for event in originals
        if event.verification is ValueVerificationState.SYSTEM_VERIFIED
    )
    authoritative = systems[-1] if systems else originals[-1]
    conflict = bool(systems) and any(
        event.verification is ValueVerificationState.HUMAN_VERIFIED
        and event.amount != authoritative.amount
        for event in originals
    )
    verification = (
        ValueVerificationState.SYSTEM_AUTHORITATIVE_CONFLICT
        if conflict
        else authoritative.verification
    )
    reasons = ("RC-066",) if conflict else (
        "RC-064"
        if authoritative.verification is ValueVerificationState.SYSTEM_VERIFIED
        else "RC-065",
    )
    return authoritative, verification, reasons


def append_value_event(intervention: DOIIntervention, event: ValueEvent) -> InterventionResult:
    """Append an exact value/correction/reversal event and recompute the full ledger."""

    if type(intervention) is not DOIIntervention or type(event) is not ValueEvent:
        raise InterventionError("VALUE_APPEND_INPUT_INVALID")
    if intervention.intervention_type is InterventionType.DS_SEPARATION:
        raise InterventionError("DS_VALUE_NOT_APPLICABLE")
    if event.intervention_id != intervention.intervention_id:
        raise InterventionError("VALUE_EVENT_OWNER_CONFLICT", reasons=_reason_set("RC-102"))
    prior = next(
        (
            item
            for item in intervention.value_events
            if item.event_id == event.event_id
        ),
        None,
    )
    if prior is not None:
        if prior.canonical_bytes() != event.canonical_bytes():
            raise InterventionError("VALUE_OCCURRENCE_CONFLICT", reasons=_reason_set("RC-102"))
        return InterventionResult(intervention, _reason_set("RC-076"), True)
    duplicate_record = next(
        (
            item
            for item in intervention.value_events
            if item.evidence.sha256 == event.evidence.sha256
        ),
        None,
    )
    if duplicate_record is not None:
        if duplicate_record.evidence.canonical_bytes != event.evidence.canonical_bytes:
            raise InterventionError(
                "VALUE_EVIDENCE_FINGERPRINT_COLLISION",
                reasons=_reason_set("RC-103"),
            )
        return InterventionResult(intervention, _reason_set("RC-076"), True)

    predecessor = None
    if event.predecessor_event_id is not None:
        predecessor = next(
            (
                item
                for item in intervention.value_events
                if item.event_id == event.predecessor_event_id
            ),
            None,
        )
        if (
            predecessor is None
            or event.predecessor_event_binding != predecessor.hash_binding()
        ):
            raise InterventionError(
                "VALUE_PREDECESSOR_CONFLICT",
                reasons=_reason_set("RC-111"),
            )
        if (
            event.occurred_at.epoch_seconds,
            event.occurred_at.nanosecond,
        ) < (
            predecessor.occurred_at.epoch_seconds,
            predecessor.occurred_at.nanosecond,
        ):
            raise InterventionError(
                "VALUE_PREDECESSOR_TIME_CONFLICT",
                reasons=_reason_set("RC-111"),
            )

    if event.event_type is ValueEventType.INITIAL_VERIFIED_VALUE:
        if intervention.value_events:
            raise InterventionError(
                "VALUE_ORIGINAL_CONFLICT",
                reasons=_reason_set("RC-102"),
            )
    elif not intervention.value_events or predecessor is None:
        raise InterventionError(
            "VALUE_PREDECESSOR_CONFLICT",
            reasons=_reason_set("RC-111"),
        )

    if intervention.value_events:
        prior_authoritative, _, _ = _authoritative_original(intervention.value_events)
        if _money_identity(event.amount) != _money_identity(prior_authoritative.amount):
            raise InterventionError(
                "VALUE_CURRENCY_BINDING_CONFLICT",
                reasons=_reason_set("RC-094"),
            )
        if (
            event.event_type is ValueEventType.CORRECTION
            and event.correction_kind is ValueCorrectionKind.ORIGINAL_VALUE_CORRECTED
            and predecessor != prior_authoritative
        ):
            raise InterventionError(
                "VALUE_AUTHORITATIVE_PREDECESSOR_CONFLICT",
                reasons=_reason_set("RC-111"),
            )
        if event.event_type in {
            ValueEventType.PARTIAL_REVERSAL,
            ValueEventType.FULL_REVERSAL,
        }:
            if predecessor != prior_authoritative:
                raise InterventionError(
                    "REVERSAL_ORIGINAL_PREDECESSOR_CONFLICT",
                    reasons=_reason_set("RC-111"),
                )
            if event.amount.minor_units <= 0:
                raise InterventionError("REVERSAL_AMOUNT_INVALID")
            if (
                event.event_type is ValueEventType.FULL_REVERSAL
                and not (
                    0
                    < event.amount.minor_units
                    <= prior_authoritative.amount.minor_units
                )
            ) or (
                event.event_type is ValueEventType.PARTIAL_REVERSAL
                and not (
                    0
                    < event.amount.minor_units
                    < prior_authoritative.amount.minor_units
                )
            ):
                raise InterventionError("REVERSAL_TYPE_AMOUNT_MISMATCH")
        if (
            event.event_type is ValueEventType.CORRECTION
            and event.correction_kind
            in {
                ValueCorrectionKind.REVERSAL_CORRECTED,
                ValueCorrectionKind.REVERSAL_VOIDED,
            }
        ):
            _, event_roots, tails = _reversal_ledger(intervention.value_events)
            if predecessor.event_id not in event_roots:
                raise InterventionError(
                    "REVERSAL_PREDECESSOR_CONFLICT",
                    reasons=_reason_set("RC-111"),
                )
            root = event_roots[predecessor.event_id]
            if (
                tails[root] != predecessor.event_id
                or event.key.key_id != predecessor.key.key_id
            ):
                raise InterventionError(
                    "REVERSAL_PREDECESSOR_CONFLICT",
                    reasons=_reason_set("RC-111"),
                )
            if (
                event.correction_kind is ValueCorrectionKind.REVERSAL_VOIDED
            ) != (event.amount.minor_units == 0):
                raise InterventionError("REVERSAL_CORRECTION_AMOUNT_INVALID")

    same_natural_key = tuple(
        item for item in intervention.value_events if item.key.key_id == event.key.key_id
    )
    legal_reversal_correction = (
        event.event_type is ValueEventType.CORRECTION
        and event.correction_kind
        in {
            ValueCorrectionKind.REVERSAL_CORRECTED,
            ValueCorrectionKind.REVERSAL_VOIDED,
        }
    )
    if same_natural_key and not legal_reversal_correction:
        raise InterventionError(
            "VALUE_NATURAL_KEY_CONFLICT",
            reasons=_reason_set("RC-102"),
        )
    events = (*intervention.value_events, event)
    authoritative, verification, base_reasons = _authoritative_original(events)
    reversed_value = _sum_reversals(authoritative.amount, events)
    if reversed_value.minor_units > authoritative.amount.minor_units:
        raise InterventionError("REVERSAL_EXCEEDS_ORIGINAL", reasons=_reason_set("RC-102"))
    net_value = authoritative.amount - reversed_value
    if reversed_value.minor_units == 0:
        status = InterventionStatus.VERIFIED_ACTIVE
        status_reasons: tuple[str, ...] = ()
    elif net_value.minor_units == 0:
        status = InterventionStatus.REVERSED
        status_reasons = ("RC-069",)
    else:
        status = InterventionStatus.PARTIALLY_REVERSED
        status_reasons = ("RC-068",)
    updated = DOIIntervention(
        intervention_id=intervention.intervention_id,
        opportunity_id=intervention.opportunity_id,
        intervention_type=intervention.intervention_type,
        status=status,
        action_verification=intervention.action_verification,
        action_occurred_at=intervention.action_occurred_at,
        action_events=intervention.action_events,
        value_events=events,
        value=InterventionValueProjection(
            verification=verification,
            authoritative_original=authoritative.amount,
            reversed_value=reversed_value,
            net_value=net_value,
            authoritative_event_id=authoritative.event_id,
        ),
    )
    return InterventionResult(updated, _reason_set(*base_reasons, *status_reasons), False)


_TARGET_REP_PROOF_TOKEN = object()


@dataclass(frozen=True, slots=True, init=False, repr=False)
class TargetRepObservation:
    """Exact rep identity/relation observed at a governed resulting-order scope."""

    observation_id: EvidenceId
    link_id: EvidenceId
    intervention_id: EvidenceId
    intervention_type: InterventionType
    intervention_action_binding: HashBinding
    scope: TargetRepProofScope
    subject_order_id: DoiOrderId
    subject_line_id: LineSnapshotId | None
    observed_rep_id: RepId
    observed_relation: RepRelation
    observed_at: CanonicalTimestamp
    source: SourceRef
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-target-rep-observation/v1"

    def __new__(cls) -> TargetRepObservation:
        raise InterventionError("TARGET_REP_OBSERVATION_FACTORY_REQUIRED")

    @classmethod
    def from_order_observation(
        cls,
        *,
        observation_id: EvidenceId,
        link_id: EvidenceId,
        intervention: DOIIntervention,
        scope: TargetRepProofScope,
        subject_order_id: DoiOrderId,
        subject_line_id: LineSnapshotId | None,
        observed_rep_id: RepId,
        observed_relation: RepRelation,
        observed_at: CanonicalTimestamp,
        source: SourceRef,
    ) -> TargetRepObservation:
        expected_scope = (
            TargetRepProofScope.RESULTING_ORDER
            if intervention.intervention_type is InterventionType.FULFILLMENT_SPLIT
            else TargetRepProofScope.REPLACEMENT_LINE
        ) if type(intervention) is DOIIntervention else None
        if (
            type(observation_id) is not EvidenceId
            or type(link_id) is not EvidenceId
            or type(intervention) is not DOIIntervention
            or intervention.intervention_type
            not in {
                InterventionType.FULFILLMENT_SPLIT,
                InterventionType.PRODUCT_SUBSTITUTION,
            }
            or type(scope) is not TargetRepProofScope
            or scope is not expected_scope
            or type(subject_order_id) is not DoiOrderId
            or (
                subject_line_id is not None
                and type(subject_line_id) is not LineSnapshotId
            )
            or (subject_line_id is None)
            != (scope is TargetRepProofScope.RESULTING_ORDER)
            or type(observed_rep_id) is not RepId
            or type(observed_relation) is not RepRelation
            or type(observed_at) is not CanonicalTimestamp
            or type(source) is not SourceRef
            or source.source_kind is not SourceKind.SYNTHETIC_ORDER_FIXTURE
            or source.object_namespace is not SourceObjectNamespace.SYNTHETIC_ORDER
            or source.object_id != subject_order_id.value
        ):
            raise InterventionError("TARGET_REP_OBSERVATION_INVALID")
        instance = object.__new__(cls)
        object.__setattr__(instance, "observation_id", observation_id)
        object.__setattr__(instance, "link_id", link_id)
        object.__setattr__(instance, "intervention_id", intervention.intervention_id)
        object.__setattr__(instance, "intervention_type", intervention.intervention_type)
        object.__setattr__(
            instance,
            "intervention_action_binding",
            intervention.action_events[0].hash_binding(),
        )
        object.__setattr__(instance, "scope", scope)
        object.__setattr__(instance, "subject_order_id", subject_order_id)
        object.__setattr__(instance, "subject_line_id", subject_line_id)
        object.__setattr__(instance, "observed_rep_id", observed_rep_id)
        object.__setattr__(instance, "observed_relation", observed_relation)
        object.__setattr__(instance, "observed_at", observed_at)
        object.__setattr__(instance, "source", source)
        object.__setattr__(instance, "schema_version", INTERVENTION_SCHEMA_VERSION)
        instance.__post_init__()
        return instance

    def __post_init__(self) -> None:
        if (
            type(self.observation_id) is not EvidenceId
            or type(self.link_id) is not EvidenceId
            or type(self.intervention_id) is not EvidenceId
            or type(self.intervention_type) is not InterventionType
            or type(self.intervention_action_binding) is not HashBinding
            or self.intervention_action_binding.domain != ActionVerificationEvent.HASH_DOMAIN
            or type(self.scope) is not TargetRepProofScope
            or type(self.subject_order_id) is not DoiOrderId
            or type(self.observed_rep_id) is not RepId
            or type(self.observed_relation) is not RepRelation
            or type(self.observed_at) is not CanonicalTimestamp
            or type(self.source) is not SourceRef
            or self.source.object_id != self.subject_order_id.value
            or self.schema_version != INTERVENTION_SCHEMA_VERSION
        ):
            raise InterventionError("TARGET_REP_OBSERVATION_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "intervention_action_binding": _hash(self.intervention_action_binding),
            "intervention_id": self.intervention_id.value,
            "intervention_type": self.intervention_type.value,
            "link_id": self.link_id.value,
            "observation_id": self.observation_id.value,
            "observed_at": self.observed_at.value,
            "observed_relation": self.observed_relation.value,
            "observed_rep_id": self.observed_rep_id.value,
            "schema_version": self.schema_version,
            "scope": self.scope.value,
            "source": _hash(self.source.hash_binding()),
            "subject_line_id": (
                None if self.subject_line_id is None else self.subject_line_id.to_json_value()
            ),
            "subject_order_id": self.subject_order_id.to_json_value(),
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "TargetRepObservation(<redacted>)"


@dataclass(frozen=True, slots=True, init=False, repr=False)
class TargetRepVerificationProof:
    """Positive proof derived only from exact target-rep observation material."""

    proof_id: EvidenceId
    link_id: EvidenceId
    intervention_id: EvidenceId
    intervention_type: InterventionType
    intervention_action_binding: HashBinding
    scope: TargetRepProofScope
    subject_order_id: DoiOrderId
    subject_line_id: LineSnapshotId | None
    observed_rep_id: RepId
    observed_relation: RepRelation
    observation: TargetRepObservation = field(repr=False)
    verified_at: CanonicalTimestamp
    source: SourceRef
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-target-rep-verification-proof/v1"

    def __new__(cls) -> TargetRepVerificationProof:
        raise InterventionError("TARGET_REP_PROOF_FACTORY_REQUIRED")

    @classmethod
    def from_observation(
        cls,
        *,
        proof_id: EvidenceId,
        intervention: DOIIntervention,
        observation: TargetRepObservation,
    ) -> TargetRepVerificationProof:
        return cls._create(
            proof_id=proof_id,
            intervention=intervention,
            observation=observation,
            factory_capability=_TARGET_REP_PROOF_TOKEN,
        )

    @classmethod
    def _create(
        cls,
        *,
        proof_id: EvidenceId,
        intervention: DOIIntervention,
        observation: TargetRepObservation,
        factory_capability: object,
    ) -> TargetRepVerificationProof:
        if factory_capability is not _TARGET_REP_PROOF_TOKEN:
            raise InterventionError("TARGET_REP_PROOF_FACTORY_REQUIRED")
        if (
            type(proof_id) is not EvidenceId
            or type(intervention) is not DOIIntervention
            or type(observation) is not TargetRepObservation
            or observation.intervention_id != intervention.intervention_id
            or observation.intervention_type is not intervention.intervention_type
            or observation.intervention_action_binding
            != intervention.action_events[0].hash_binding()
            or observation.observed_rep_id != TARGET_REP_ID
            or observation.observed_relation is not RepRelation.TARGET_REP_OWNED
        ):
            raise InterventionError("TARGET_REP_PROOF_INTERVENTION_INVALID")
        instance = object.__new__(cls)
        object.__setattr__(instance, "proof_id", proof_id)
        object.__setattr__(instance, "link_id", observation.link_id)
        object.__setattr__(instance, "intervention_id", intervention.intervention_id)
        object.__setattr__(instance, "intervention_type", intervention.intervention_type)
        object.__setattr__(
            instance,
            "intervention_action_binding",
            intervention.action_events[0].hash_binding(),
        )
        object.__setattr__(instance, "scope", observation.scope)
        object.__setattr__(instance, "subject_order_id", observation.subject_order_id)
        object.__setattr__(instance, "subject_line_id", observation.subject_line_id)
        object.__setattr__(instance, "observed_rep_id", observation.observed_rep_id)
        object.__setattr__(instance, "observed_relation", observation.observed_relation)
        object.__setattr__(instance, "observation", observation)
        object.__setattr__(instance, "verified_at", observation.observed_at)
        object.__setattr__(instance, "source", observation.source)
        object.__setattr__(instance, "schema_version", INTERVENTION_SCHEMA_VERSION)
        instance.__post_init__()
        try:
            assert_payload_safe(
                {
                    "intervention_id": instance.intervention_id.value,
                    "link_id": instance.link_id.value,
                    "proof_id": instance.proof_id.value,
                    "observed_rep_id": instance.observed_rep_id.value,
                    "source_object_id": instance.source.object_id.value,
                    "subject_line_id": (
                        None
                        if instance.subject_line_id is None
                        else instance.subject_line_id.to_json_value()
                    ),
                    "subject_order_id": instance.subject_order_id.to_json_value(),
                }
            )
        except ProhibitedInputError:
            raise InterventionError("TARGET_REP_PROOF_PRIVACY_REJECTED") from None
        return instance

    def __post_init__(self) -> None:
        if (
            type(self.proof_id) is not EvidenceId
            or type(self.link_id) is not EvidenceId
            or type(self.intervention_id) is not EvidenceId
            or self.intervention_type
            not in {
                InterventionType.FULFILLMENT_SPLIT,
                InterventionType.PRODUCT_SUBSTITUTION,
            }
            or type(self.intervention_action_binding) is not HashBinding
            or self.intervention_action_binding.domain
            != ActionVerificationEvent.HASH_DOMAIN
            or type(self.scope) is not TargetRepProofScope
            or type(self.subject_order_id) is not DoiOrderId
            or (
                self.subject_line_id is not None
                and type(self.subject_line_id) is not LineSnapshotId
            )
            or type(self.verified_at) is not CanonicalTimestamp
            or self.observed_rep_id != TARGET_REP_ID
            or self.observed_relation is not RepRelation.TARGET_REP_OWNED
            or type(self.observation) is not TargetRepObservation
            or self.observation.hash_binding().domain != TargetRepObservation.HASH_DOMAIN
            or type(self.source) is not SourceRef
            or self.source.source_kind is not SourceKind.SYNTHETIC_ORDER_FIXTURE
            or self.source.object_namespace is not SourceObjectNamespace.SYNTHETIC_ORDER
            or self.source.object_id != self.subject_order_id.value
            or self.schema_version != INTERVENTION_SCHEMA_VERSION
        ):
            raise InterventionError("TARGET_REP_PROOF_INVALID")
        expected_scope = (
            TargetRepProofScope.RESULTING_ORDER
            if self.intervention_type is InterventionType.FULFILLMENT_SPLIT
            else TargetRepProofScope.REPLACEMENT_LINE
        )
        if self.scope is not expected_scope or (
            (self.subject_line_id is None)
            != (self.scope is TargetRepProofScope.RESULTING_ORDER)
        ):
            raise InterventionError("TARGET_REP_PROOF_SCOPE_INVALID")
        if (
            self.observation.link_id != self.link_id
            or self.observation.intervention_id != self.intervention_id
            or self.observation.intervention_action_binding
            != self.intervention_action_binding
            or self.observation.subject_order_id != self.subject_order_id
            or self.observation.subject_line_id != self.subject_line_id
            or self.observation.source != self.source
        ):
            raise InterventionError("TARGET_REP_PROOF_OBSERVATION_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "intervention_action_binding": _hash(self.intervention_action_binding),
            "intervention_id": self.intervention_id.value,
            "intervention_type": self.intervention_type.value,
            "link_id": self.link_id.value,
            "observation": _hash(self.observation.hash_binding()),
            "observed_relation": self.observed_relation.value,
            "observed_rep_id": self.observed_rep_id.value,
            "proof_id": self.proof_id.value,
            "schema_version": self.schema_version,
            "scope": self.scope.value,
            "source": _hash(self.source.hash_binding()),
            "subject_line_id": (
                None if self.subject_line_id is None else self.subject_line_id.to_json_value()
            ),
            "subject_order_id": self.subject_order_id.to_json_value(),
            "verified_at": self.verified_at.value,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "TargetRepVerificationProof(<redacted>)"


@dataclass(frozen=True, slots=True)
class MovedLineMappingComponent:
    parent_line_id: LineSnapshotId
    child_line_id: LineSnapshotId
    quantity: PositiveQuantity
    replacement_line_target_rep_proof: TargetRepVerificationProof | None

    def __post_init__(self) -> None:
        if (
            type(self.parent_line_id) is not LineSnapshotId
            or type(self.child_line_id) is not LineSnapshotId
            or type(self.quantity) is not PositiveQuantity
            or (
                self.replacement_line_target_rep_proof is not None
                and type(self.replacement_line_target_rep_proof)
                is not TargetRepVerificationProof
            )
        ):
            raise InterventionError("MOVED_LINE_MAPPING_INVALID")
        proof = self.replacement_line_target_rep_proof
        if proof is not None and (
            proof.scope is not TargetRepProofScope.REPLACEMENT_LINE
            or proof.subject_line_id != self.child_line_id
        ):
            raise InterventionError("MOVED_LINE_REP_PROOF_SCOPE_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "child_line_id": self.child_line_id.to_json_value(),
            "parent_line_id": self.parent_line_id.to_json_value(),
            "quantity": self.quantity.to_json_value(),
            "replacement_line_target_rep_proof": (
                None
                if self.replacement_line_target_rep_proof is None
                else _hash(self.replacement_line_target_rep_proof.hash_binding())
            ),
        }


def _validate_link_evidence_scope(
    *,
    intervention: DOIIntervention,
    link_id: EvidenceId,
    parent_order_id: DoiOrderId,
    child_order_id: DoiOrderId,
    mappings: tuple[MovedLineMappingComponent, ...],
    resulting_order_target_rep_proof: TargetRepVerificationProof | None,
    line_scope: tuple[LineSnapshotId, ...],
) -> None:
    if (
        type(intervention) is not DOIIntervention
        or intervention.intervention_type
        not in {
            InterventionType.FULFILLMENT_SPLIT,
            InterventionType.PRODUCT_SUBSTITUTION,
        }
        or type(link_id) is not EvidenceId
        or type(parent_order_id) is not DoiOrderId
        or type(child_order_id) is not DoiOrderId
        or parent_order_id == child_order_id
        or type(mappings) is not tuple
        or not mappings
        or any(type(item) is not MovedLineMappingComponent for item in mappings)
        or type(line_scope) is not tuple
        or any(type(item) is not LineSnapshotId for item in line_scope)
    ):
        raise InterventionError("RESULTING_LINK_EVIDENCE_SCOPE_INVALID")
    mapping_scope = tuple(item.parent_line_id for item in mappings)
    if mapping_scope != line_scope:
        raise InterventionError("RESULTING_LINK_MAPPING_SCOPE_INVALID")
    keys = tuple(
        (item.parent_line_id.to_json_value(), item.child_line_id.to_json_value())
        for item in mappings
    )
    if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
        raise InterventionError("RESULTING_LINK_MAPPING_ORDER_INVALID")
    if intervention.intervention_type is InterventionType.FULFILLMENT_SPLIT:
        if (
            resulting_order_target_rep_proof is not None
            and (
                type(resulting_order_target_rep_proof)
                is not TargetRepVerificationProof
                or resulting_order_target_rep_proof.scope
                is not TargetRepProofScope.RESULTING_ORDER
                or resulting_order_target_rep_proof.link_id != link_id
                or resulting_order_target_rep_proof.subject_order_id != child_order_id
            )
        ):
            raise InterventionError("RESULTING_LINK_ORDER_REP_PROOF_INVALID")
        if any(
            item.replacement_line_target_rep_proof is not None for item in mappings
        ):
            raise InterventionError("RESULTING_LINK_LINE_REP_PROOF_INVALID")
    else:
        if resulting_order_target_rep_proof is not None:
            raise InterventionError("RESULTING_LINK_ORDER_REP_PROOF_INVALID")
        if any(
            item.replacement_line_target_rep_proof is not None
            and (
                item.replacement_line_target_rep_proof.link_id != link_id
                or item.replacement_line_target_rep_proof.subject_order_id
                != child_order_id
                or item.replacement_line_target_rep_proof.subject_line_id
                != item.child_line_id
            )
            for item in mappings
        ):
            raise InterventionError("RESULTING_LINK_LINE_REP_PROOF_INVALID")


@dataclass(frozen=True, slots=True, init=False, repr=False)
class SystemResultingLinkEvidence:
    evidence_id: EvidenceId
    link_id: EvidenceId
    intervention_id: EvidenceId
    intervention_type: InterventionType
    intervention_action_binding: HashBinding
    parent_order_id: DoiOrderId
    child_order_id: DoiOrderId
    mappings: tuple[MovedLineMappingComponent, ...]
    resulting_order_target_rep_proof: TargetRepVerificationProof | None
    predecessor_revision_binding: HashBinding | None
    resolves_conflict_binding: HashBinding | None
    observed_at: CanonicalTimestamp
    source: SourceRef
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-system-resulting-link-evidence/v1"

    def __new__(cls) -> SystemResultingLinkEvidence:
        raise InterventionError("SYSTEM_RESULTING_LINK_EVIDENCE_FACTORY_REQUIRED")

    @classmethod
    def from_order_observation(
        cls,
        *,
        evidence_id: EvidenceId,
        link_id: EvidenceId,
        parent_order_id: DoiOrderId,
        child_order_id: DoiOrderId,
        intervention: DOIIntervention,
        completed_action_context: DOIActionContext,
        mappings: tuple[MovedLineMappingComponent, ...],
        resulting_order_target_rep_proof: TargetRepVerificationProof | None,
        predecessor_revision: ResultingOrderLinkRevision | None,
        resolves_conflict_revision: ResultingOrderLinkRevision | None,
        observed_at: CanonicalTimestamp,
        source: SourceRef,
    ) -> SystemResultingLinkEvidence:
        expected_context_binding = (
            intervention.action_events[0].evidence.material.action_context_binding
            if type(intervention) is DOIIntervention
            else None
        )
        if (
            type(evidence_id) is not EvidenceId
            or type(completed_action_context) is not DOIActionContext
            or completed_action_context.state is not ActionContextState.CLOSED_COMPLETED
            or completed_action_context.hash_binding() != expected_context_binding
            or completed_action_context.order_id != parent_order_id
            or completed_action_context.opportunity_id != intervention.opportunity_id
            or type(observed_at) is not CanonicalTimestamp
            or type(source) is not SourceRef
            or source.source_kind is not SourceKind.SYNTHETIC_ORDER_FIXTURE
            or source.object_namespace is not SourceObjectNamespace.SYNTHETIC_ORDER
            or source.object_id != child_order_id.value
            or (
                predecessor_revision is not None
                and type(predecessor_revision) is not ResultingOrderLinkRevision
            )
            or (
                resolves_conflict_revision is not None
                and type(resolves_conflict_revision) is not ResultingOrderLinkRevision
            )
        ):
            raise InterventionError("SYSTEM_RESULTING_LINK_EVIDENCE_OWNER_INVALID")
        _validate_link_evidence_scope(
            intervention=intervention,
            link_id=link_id,
            parent_order_id=parent_order_id,
            child_order_id=child_order_id,
            mappings=mappings,
            resulting_order_target_rep_proof=resulting_order_target_rep_proof,
            line_scope=completed_action_context.line_scope,
        )
        instance = object.__new__(cls)
        object.__setattr__(instance, "evidence_id", evidence_id)
        object.__setattr__(instance, "link_id", link_id)
        object.__setattr__(instance, "intervention_id", intervention.intervention_id)
        object.__setattr__(instance, "intervention_type", intervention.intervention_type)
        object.__setattr__(
            instance,
            "intervention_action_binding",
            intervention.action_events[0].hash_binding(),
        )
        object.__setattr__(instance, "parent_order_id", parent_order_id)
        object.__setattr__(instance, "child_order_id", child_order_id)
        object.__setattr__(instance, "mappings", mappings)
        object.__setattr__(
            instance,
            "resulting_order_target_rep_proof",
            resulting_order_target_rep_proof,
        )
        object.__setattr__(
            instance,
            "predecessor_revision_binding",
            None
            if predecessor_revision is None
            else predecessor_revision.hash_binding(),
        )
        object.__setattr__(
            instance,
            "resolves_conflict_binding",
            None
            if resolves_conflict_revision is None
            else resolves_conflict_revision.hash_binding(),
        )
        object.__setattr__(instance, "observed_at", observed_at)
        object.__setattr__(instance, "source", source)
        object.__setattr__(instance, "schema_version", INTERVENTION_SCHEMA_VERSION)
        instance.__post_init__()
        return instance

    def __post_init__(self) -> None:
        if (
            type(self.evidence_id) is not EvidenceId
            or type(self.link_id) is not EvidenceId
            or type(self.intervention_id) is not EvidenceId
            or type(self.intervention_type) is not InterventionType
            or type(self.intervention_action_binding) is not HashBinding
            or self.intervention_action_binding.domain != ActionVerificationEvent.HASH_DOMAIN
            or type(self.parent_order_id) is not DoiOrderId
            or type(self.child_order_id) is not DoiOrderId
            or type(self.mappings) is not tuple
            or type(self.observed_at) is not CanonicalTimestamp
            or type(self.source) is not SourceRef
            or self.source.object_id != self.child_order_id.value
            or self.schema_version != INTERVENTION_SCHEMA_VERSION
        ):
            raise InterventionError("SYSTEM_RESULTING_LINK_EVIDENCE_INVALID")

    def to_dict(self) -> dict[str, object]:
        return _resulting_link_evidence_dict(self)

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "SystemResultingLinkEvidence(<redacted>)"


@dataclass(frozen=True, slots=True, init=False, repr=False)
class AuthorizedHumanResultingLinkEvidence:
    evidence_id: EvidenceId
    link_id: EvidenceId
    intervention_id: EvidenceId
    intervention_type: InterventionType
    intervention_action_binding: HashBinding
    parent_order_id: DoiOrderId
    child_order_id: DoiOrderId
    mappings: tuple[MovedLineMappingComponent, ...]
    resulting_order_target_rep_proof: TargetRepVerificationProof | None
    predecessor_revision_binding: HashBinding | None
    resolves_conflict_binding: HashBinding | None
    human_fact_binding: HashBinding
    human_fact_event_binding: HashBinding
    observed_at: CanonicalTimestamp
    source: SourceRef
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-authorized-human-resulting-link-evidence/v1"

    def __new__(cls) -> AuthorizedHumanResultingLinkEvidence:
        raise InterventionError("HUMAN_RESULTING_LINK_EVIDENCE_FACTORY_REQUIRED")

    @classmethod
    def from_reduced_human_fact(
        cls,
        *,
        evidence_id: EvidenceId,
        link_id: EvidenceId,
        parent_order_id: DoiOrderId,
        child_order_id: DoiOrderId,
        intervention: DOIIntervention,
        human_fact_proof: AcceptedHumanFactProof,
        mappings: tuple[MovedLineMappingComponent, ...],
        resulting_order_target_rep_proof: TargetRepVerificationProof | None,
        predecessor_revision: ResultingOrderLinkRevision | None,
        resolves_conflict_revision: ResultingOrderLinkRevision | None,
    ) -> AuthorizedHumanResultingLinkEvidence:
        if (
            type(evidence_id) is not EvidenceId
            or type(human_fact_proof) is not AcceptedHumanFactProof
            or human_fact_proof._issuer_token is not _ACCEPTED_HUMAN_FACT_TOKEN
            or (
                predecessor_revision is not None
                and type(predecessor_revision) is not ResultingOrderLinkRevision
            )
            or (
                resolves_conflict_revision is not None
                and type(resolves_conflict_revision) is not ResultingOrderLinkRevision
            )
        ):
            raise InterventionError(
                "HUMAN_RESULTING_LINK_EVIDENCE_AUTHORITY_INVALID",
                reasons=_reason_set("RC-112"),
            )
        fact = human_fact_proof.fact
        if (
            fact.order_id != parent_order_id
            or fact.action_context.opportunity_id != intervention.opportunity_id
            or fact.action_context.intervention_type is not intervention.intervention_type
        ):
            raise InterventionError(
                "HUMAN_RESULTING_LINK_EVIDENCE_OWNER_INVALID",
                reasons=_reason_set("RC-112"),
            )
        _validate_link_evidence_scope(
            intervention=intervention,
            link_id=link_id,
            parent_order_id=parent_order_id,
            child_order_id=child_order_id,
            mappings=mappings,
            resulting_order_target_rep_proof=resulting_order_target_rep_proof,
            line_scope=fact.action_context.line_scope,
        )
        instance = object.__new__(cls)
        object.__setattr__(instance, "evidence_id", evidence_id)
        object.__setattr__(instance, "link_id", link_id)
        object.__setattr__(instance, "intervention_id", intervention.intervention_id)
        object.__setattr__(instance, "intervention_type", intervention.intervention_type)
        object.__setattr__(
            instance,
            "intervention_action_binding",
            intervention.action_events[0].hash_binding(),
        )
        object.__setattr__(instance, "parent_order_id", parent_order_id)
        object.__setattr__(instance, "child_order_id", child_order_id)
        object.__setattr__(instance, "mappings", mappings)
        object.__setattr__(
            instance,
            "resulting_order_target_rep_proof",
            resulting_order_target_rep_proof,
        )
        object.__setattr__(
            instance,
            "predecessor_revision_binding",
            None
            if predecessor_revision is None
            else predecessor_revision.hash_binding(),
        )
        object.__setattr__(
            instance,
            "resolves_conflict_binding",
            None
            if resolves_conflict_revision is None
            else resolves_conflict_revision.hash_binding(),
        )
        object.__setattr__(instance, "human_fact_binding", fact.hash_binding())
        object.__setattr__(
            instance,
            "human_fact_event_binding",
            human_fact_proof.current_event.hash_binding(),
        )
        object.__setattr__(instance, "observed_at", fact.occurred_at)
        object.__setattr__(instance, "source", fact.source)
        object.__setattr__(instance, "schema_version", INTERVENTION_SCHEMA_VERSION)
        instance.__post_init__()
        return instance

    def __post_init__(self) -> None:
        if (
            type(self.evidence_id) is not EvidenceId
            or type(self.link_id) is not EvidenceId
            or type(self.intervention_id) is not EvidenceId
            or type(self.intervention_type) is not InterventionType
            or type(self.intervention_action_binding) is not HashBinding
            or self.intervention_action_binding.domain != ActionVerificationEvent.HASH_DOMAIN
            or type(self.parent_order_id) is not DoiOrderId
            or type(self.child_order_id) is not DoiOrderId
            or type(self.mappings) is not tuple
            or type(self.human_fact_binding) is not HashBinding
            or self.human_fact_binding.domain != StructuredHumanFact.HASH_DOMAIN
            or type(self.human_fact_event_binding) is not HashBinding
            or self.human_fact_event_binding.domain != DOIHumanFactEvent.HASH_DOMAIN
            or type(self.observed_at) is not CanonicalTimestamp
            or type(self.source) is not SourceRef
            or self.source.source_kind is not SourceKind.SYNTHETIC_INTERACTION_FIXTURE
            or self.schema_version != INTERVENTION_SCHEMA_VERSION
        ):
            raise InterventionError("HUMAN_RESULTING_LINK_EVIDENCE_INVALID")

    def to_dict(self) -> dict[str, object]:
        value = _resulting_link_evidence_dict(self)
        value["human_fact_binding"] = _hash(self.human_fact_binding)
        value["human_fact_event_binding"] = _hash(self.human_fact_event_binding)
        return value

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "AuthorizedHumanResultingLinkEvidence(<redacted>)"


type ResultingLinkEvidence = (
    SystemResultingLinkEvidence | AuthorizedHumanResultingLinkEvidence
)


def _resulting_link_evidence_dict(
    evidence: ResultingLinkEvidence,
) -> dict[str, object]:
    return {
        "child_order_id": evidence.child_order_id.to_json_value(),
        "evidence_id": evidence.evidence_id.value,
        "intervention_action_binding": _hash(evidence.intervention_action_binding),
        "intervention_id": evidence.intervention_id.value,
        "intervention_type": evidence.intervention_type.value,
        "link_id": evidence.link_id.value,
        "mappings": [item.to_dict() for item in evidence.mappings],
        "observed_at": evidence.observed_at.value,
        "parent_order_id": evidence.parent_order_id.to_json_value(),
        "predecessor_revision_binding": (
            None
            if evidence.predecessor_revision_binding is None
            else _hash(evidence.predecessor_revision_binding)
        ),
        "resolves_conflict_binding": (
            None
            if evidence.resolves_conflict_binding is None
            else _hash(evidence.resolves_conflict_binding)
        ),
        "resulting_order_target_rep_proof": (
            None
            if evidence.resulting_order_target_rep_proof is None
            else _hash(evidence.resulting_order_target_rep_proof.hash_binding())
        ),
        "schema_version": evidence.schema_version,
        "source": _hash(evidence.source.hash_binding()),
    }


_RESULTING_LINK_REVISION_TOKEN = object()


@dataclass(frozen=True, slots=True, init=False, repr=False)
class ResultingOrderLinkRevision:
    revision_id: EvidenceId
    link_id: EvidenceId
    intervention_id: EvidenceId
    intervention_type: InterventionType
    intervention_action_binding: HashBinding
    revision: int
    state: ResultingOrderLinkState
    mappings: tuple[MovedLineMappingComponent, ...]
    resulting_order_target_rep_proof: TargetRepVerificationProof | None
    predecessor_sha256: str | None
    evidence_record: ResultingLinkEvidence = field(repr=False)
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-resulting-order-link-revision/v1"

    def __new__(cls) -> ResultingOrderLinkRevision:
        raise InterventionError("RESULTING_LINK_REVISION_REDUCER_REQUIRED")

    @classmethod
    def _from_evidence(
        cls,
        *,
        revision_id: EvidenceId,
        revision: int,
        state: ResultingOrderLinkState,
        predecessor_sha256: str | None,
        evidence_record: ResultingLinkEvidence,
        factory_capability: object,
    ) -> ResultingOrderLinkRevision:
        if (
            factory_capability is not _RESULTING_LINK_REVISION_TOKEN
            or type(revision_id) is not EvidenceId
            or type(evidence_record)
            not in {
                SystemResultingLinkEvidence,
                AuthorizedHumanResultingLinkEvidence,
            }
        ):
            raise InterventionError("RESULTING_LINK_REVISION_REDUCER_REQUIRED")
        instance = object.__new__(cls)
        object.__setattr__(instance, "revision_id", revision_id)
        object.__setattr__(instance, "link_id", evidence_record.link_id)
        object.__setattr__(instance, "intervention_id", evidence_record.intervention_id)
        object.__setattr__(instance, "intervention_type", evidence_record.intervention_type)
        object.__setattr__(
            instance,
            "intervention_action_binding",
            evidence_record.intervention_action_binding,
        )
        object.__setattr__(instance, "revision", revision)
        object.__setattr__(instance, "state", state)
        object.__setattr__(instance, "mappings", evidence_record.mappings)
        object.__setattr__(
            instance,
            "resulting_order_target_rep_proof",
            evidence_record.resulting_order_target_rep_proof,
        )
        object.__setattr__(instance, "predecessor_sha256", predecessor_sha256)
        object.__setattr__(instance, "evidence_record", evidence_record)
        object.__setattr__(instance, "schema_version", INTERVENTION_SCHEMA_VERSION)
        instance.__post_init__()
        return instance

    def __post_init__(self) -> None:
        if (
            type(self.revision_id) is not EvidenceId
            or type(self.link_id) is not EvidenceId
            or type(self.intervention_id) is not EvidenceId
            or self.intervention_type
            not in {
                InterventionType.FULFILLMENT_SPLIT,
                InterventionType.PRODUCT_SUBSTITUTION,
            }
            or type(self.intervention_action_binding) is not HashBinding
            or self.intervention_action_binding.domain
            != ActionVerificationEvent.HASH_DOMAIN
            or type(self.revision) is not int
            or self.revision < 1
            or type(self.state) is not ResultingOrderLinkState
            or type(self.mappings) is not tuple
            or not self.mappings
            or any(type(item) is not MovedLineMappingComponent for item in self.mappings)
            or (
                self.resulting_order_target_rep_proof is not None
                and type(self.resulting_order_target_rep_proof)
                is not TargetRepVerificationProof
            )
            or (
                self.predecessor_sha256 is not None
                and (
                    type(self.predecessor_sha256) is not str
                    or len(self.predecessor_sha256) != 64
                )
            )
            or type(self.evidence_record)
            not in {
                SystemResultingLinkEvidence,
                AuthorizedHumanResultingLinkEvidence,
            }
            or self.schema_version != INTERVENTION_SCHEMA_VERSION
        ):
            raise InterventionError("RESULTING_LINK_REVISION_INVALID")
        evidence = self.evidence_record
        if (
            evidence.link_id != self.link_id
            or evidence.intervention_id != self.intervention_id
            or evidence.intervention_type is not self.intervention_type
            or evidence.intervention_action_binding != self.intervention_action_binding
            or evidence.mappings != self.mappings
            or evidence.resulting_order_target_rep_proof
            != self.resulting_order_target_rep_proof
        ):
            raise InterventionError("RESULTING_LINK_REVISION_EVIDENCE_INVALID")
        keys = tuple(
            (item.parent_line_id.to_json_value(), item.child_line_id.to_json_value())
            for item in self.mappings
        )
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise InterventionError("RESULTING_LINK_MAPPING_ORDER_INVALID")
        if (self.revision == 1) != (self.predecessor_sha256 is None):
            raise InterventionError("RESULTING_LINK_PREDECESSOR_INVALID")
        order_proof = self.resulting_order_target_rep_proof
        expected_order_proof = self.intervention_type is InterventionType.FULFILLMENT_SPLIT
        if (order_proof is not None) and (
            not expected_order_proof
            or order_proof.link_id != self.link_id
            or order_proof.intervention_id != self.intervention_id
            or order_proof.intervention_type is not self.intervention_type
            or order_proof.intervention_action_binding != self.intervention_action_binding
            or order_proof.scope is not TargetRepProofScope.RESULTING_ORDER
        ):
            raise InterventionError("RESULTING_LINK_ORDER_REP_PROOF_INVALID")
        for mapping in self.mappings:
            line_proof = mapping.replacement_line_target_rep_proof
            if line_proof is not None and (
                self.intervention_type is not InterventionType.PRODUCT_SUBSTITUTION
                or line_proof.link_id != self.link_id
                or line_proof.intervention_id != self.intervention_id
                or line_proof.intervention_type is not self.intervention_type
                or line_proof.intervention_action_binding
                != self.intervention_action_binding
            ):
                raise InterventionError("RESULTING_LINK_LINE_REP_PROOF_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence": _hash(self.evidence),
            "intervention_action_binding": _hash(self.intervention_action_binding),
            "intervention_id": self.intervention_id.value,
            "intervention_type": self.intervention_type.value,
            "link_id": self.link_id.value,
            "mappings": [item.to_dict() for item in self.mappings],
            "predecessor_sha256": self.predecessor_sha256,
            "revision": self.revision,
            "revision_id": self.revision_id.value,
            "resulting_order_target_rep_proof": (
                None
                if self.resulting_order_target_rep_proof is None
                else _hash(self.resulting_order_target_rep_proof.hash_binding())
            ),
            "schema_version": self.schema_version,
            "state": self.state.value,
        }

    @property
    def evidence(self) -> HashBinding:
        return self.evidence_record.hash_binding()

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "ResultingOrderLinkRevision(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class DOIResultingOrderLink:
    link_id: EvidenceId
    intervention_id: EvidenceId
    intervention_action_binding: HashBinding
    parent_order_id: DoiOrderId
    child_order_id: DoiOrderId
    intervention_type: InterventionType
    state: ResultingOrderLinkState
    resulting_order_target_rep_proof: TargetRepVerificationProof | None
    revisions: tuple[ResultingOrderLinkRevision, ...]
    schema_version: str = INTERVENTION_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-resulting-order-link/v1"

    def __post_init__(self) -> None:
        if (
            type(self.link_id) is not EvidenceId
            or type(self.intervention_id) is not EvidenceId
            or type(self.intervention_action_binding) is not HashBinding
            or self.intervention_action_binding.domain
            != ActionVerificationEvent.HASH_DOMAIN
            or type(self.parent_order_id) is not DoiOrderId
            or type(self.child_order_id) is not DoiOrderId
            or self.parent_order_id == self.child_order_id
            or self.intervention_type
            not in {InterventionType.FULFILLMENT_SPLIT, InterventionType.PRODUCT_SUBSTITUTION}
            or type(self.state) is not ResultingOrderLinkState
            or (
                self.resulting_order_target_rep_proof is not None
                and type(self.resulting_order_target_rep_proof)
                is not TargetRepVerificationProof
            )
            or type(self.revisions) is not tuple
            or not self.revisions
            or any(type(item) is not ResultingOrderLinkRevision for item in self.revisions)
            or self.schema_version != INTERVENTION_SCHEMA_VERSION
        ):
            raise InterventionError("RESULTING_ORDER_LINK_INVALID")
        if self.state is not self.revisions[-1].state:
            raise InterventionError("RESULTING_ORDER_LINK_PROJECTION_INVALID")
        if self.resulting_order_target_rep_proof != (
            self.revisions[-1].resulting_order_target_rep_proof
        ):
            raise InterventionError("RESULTING_ORDER_LINK_REP_PROOF_PROJECTION_INVALID")
        for expected, revision in enumerate(self.revisions, start=1):
            predecessor = (
                None
                if expected == 1
                else self.revisions[expected - 2].hash_binding().sha256
            )
            if (
                revision.revision != expected
                or revision.predecessor_sha256 != predecessor
                or revision.link_id != self.link_id
                or revision.intervention_id != self.intervention_id
                or revision.intervention_type is not self.intervention_type
                or revision.intervention_action_binding
                != self.intervention_action_binding
                or revision.evidence_record.parent_order_id != self.parent_order_id
                or revision.evidence_record.child_order_id != self.child_order_id
            ):
                raise InterventionError("RESULTING_ORDER_LINK_SEQUENCE_INVALID")
            order_proof = revision.resulting_order_target_rep_proof
            if order_proof is not None and order_proof.subject_order_id != self.child_order_id:
                raise InterventionError("RESULTING_ORDER_LINK_REP_PROOF_SCOPE_INVALID")
            if any(
                mapping.replacement_line_target_rep_proof is not None
                and mapping.replacement_line_target_rep_proof.subject_order_id
                != self.child_order_id
                for mapping in revision.mappings
            ):
                raise InterventionError("RESULTING_ORDER_LINK_REP_PROOF_SCOPE_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "child_order_id": self.child_order_id.to_json_value(),
            "intervention_action_binding": _hash(self.intervention_action_binding),
            "intervention_id": self.intervention_id.value,
            "intervention_type": self.intervention_type.value,
            "link_id": self.link_id.value,
            "parent_order_id": self.parent_order_id.to_json_value(),
            "resulting_order_target_rep_proof": (
                None
                if self.resulting_order_target_rep_proof is None
                else _hash(self.resulting_order_target_rep_proof.hash_binding())
            ),
            "revision_hashes": [_hash(item.hash_binding()) for item in self.revisions],
            "schema_version": self.schema_version,
            "state": self.state.value,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOIResultingOrderLink(<redacted>)"


@dataclass(frozen=True, slots=True)
class ResultingLinkResult:
    link: DOIResultingOrderLink
    reasons: ReasonSet
    replayed: bool


def append_resulting_link_revision(
    existing: DOIResultingOrderLink | None,
    *,
    revision_id: EvidenceId,
    intervention: DOIIntervention,
    evidence: ResultingLinkEvidence,
) -> ResultingLinkResult:
    """Reduce typed owner evidence into one immutable exact-link revision."""

    if (
        type(revision_id) is not EvidenceId
        or type(intervention) is not DOIIntervention
        or type(evidence)
        not in {
            SystemResultingLinkEvidence,
            AuthorizedHumanResultingLinkEvidence,
        }
    ):
        raise InterventionError("RESULTING_LINK_INPUT_INVALID")
    action_binding = intervention.action_events[0].hash_binding()
    if (
        evidence.intervention_id != intervention.intervention_id
        or evidence.intervention_type is not intervention.intervention_type
        or evidence.intervention_action_binding != action_binding
    ):
        raise InterventionError(
            "RESULTING_LINK_INTERVENTION_BINDING_INVALID",
            reasons=_reason_set("RC-081"),
        )
    if existing is None:
        if (
            evidence.predecessor_revision_binding is not None
            or evidence.resolves_conflict_binding is not None
        ):
            raise InterventionError("RESULTING_LINK_INITIAL_REVISION_INVALID")
        state = (
            ResultingOrderLinkState.AUTO_LINKED
            if type(evidence) is SystemResultingLinkEvidence
            else ResultingOrderLinkState.HUMAN_CONFIRMED
        )
        revision = ResultingOrderLinkRevision._from_evidence(
            revision_id=revision_id,
            revision=1,
            state=state,
            predecessor_sha256=None,
            evidence_record=evidence,
            factory_capability=_RESULTING_LINK_REVISION_TOKEN,
        )
        link = DOIResultingOrderLink(
            link_id=evidence.link_id,
            intervention_id=intervention.intervention_id,
            intervention_action_binding=action_binding,
            parent_order_id=evidence.parent_order_id,
            child_order_id=evidence.child_order_id,
            intervention_type=intervention.intervention_type,
            state=state,
            resulting_order_target_rep_proof=revision.resulting_order_target_rep_proof,
            revisions=(revision,),
        )
        reason = "RC-070" if state is ResultingOrderLinkState.AUTO_LINKED else "RC-071"
        return ResultingLinkResult(link, _reason_set(reason), False)
    if (
        existing.link_id != evidence.link_id
        or existing.intervention_id != intervention.intervention_id
        or existing.intervention_action_binding != action_binding
        or existing.parent_order_id != evidence.parent_order_id
        or existing.child_order_id != evidence.child_order_id
        or existing.intervention_type is not intervention.intervention_type
    ):
        raise InterventionError(
            "RESULTING_LINK_DIFFERENT_NATURAL_KEY",
            reasons=_reason_set("RC-081"),
        )
    prior = next(
        (
            item
            for item in existing.revisions
            if item.revision_id == revision_id
        ),
        None,
    )
    if prior is not None:
        if prior.evidence.canonical_bytes != evidence.hash_binding().canonical_bytes:
            raise InterventionError(
                "RESULTING_LINK_REVISION_CONFLICT",
                reasons=_reason_set("RC-111"),
            )
        return ResultingLinkResult(existing, ReasonSet(), True)
    current_revision = existing.revisions[-1]
    current_binding = current_revision.hash_binding()
    if evidence.predecessor_revision_binding != current_binding:
        raise InterventionError(
            "RESULTING_LINK_PREDECESSOR_CONFLICT",
            reasons=_reason_set("RC-111"),
        )
    if evidence.resolves_conflict_binding is not None and (
        existing.state is not ResultingOrderLinkState.AMBIGUOUS
        or evidence.resolves_conflict_binding != current_binding
    ):
        raise InterventionError(
            "RESULTING_LINK_RESOLUTION_PREDECESSOR_CONFLICT",
            reasons=_reason_set("RC-111"),
        )

    duplicate_evidence = next(
        (
            item
            for item in existing.revisions
            if item.evidence.sha256 == evidence.hash_binding().sha256
        ),
        None,
    )
    if duplicate_evidence is not None:
        if duplicate_evidence.evidence.canonical_bytes != evidence.hash_binding().canonical_bytes:
            raise InterventionError(
                "RESULTING_LINK_EVIDENCE_COLLISION",
                reasons=_reason_set("RC-103"),
            )
        return ResultingLinkResult(existing, ReasonSet(), True)

    def mapping_signature(
        mappings: tuple[MovedLineMappingComponent, ...],
    ) -> tuple[tuple[LineSnapshotId, LineSnapshotId, PositiveQuantity], ...]:
        return tuple(
            (item.parent_line_id, item.child_line_id, item.quantity)
            for item in mappings
        )

    current_mapping = tuple(
        mapping_signature(current_revision.mappings)
    )
    candidate_mapping = mapping_signature(evidence.mappings)
    system_evidence = type(evidence) is SystemResultingLinkEvidence
    if existing.state is not ResultingOrderLinkState.AMBIGUOUS:
        if candidate_mapping == current_mapping:
            expected_state = (
                ResultingOrderLinkState.AUTO_LINKED
                if system_evidence
                else existing.state
            )
            reasons = _reason_set(
                "RC-070"
                if expected_state is ResultingOrderLinkState.AUTO_LINKED
                else "RC-071"
            )
        else:
            expected_state = ResultingOrderLinkState.AMBIGUOUS
            reasons = _reason_set("RC-072", "RC-104")
    else:
        if evidence.resolves_conflict_binding is None:
            expected_state = ResultingOrderLinkState.AMBIGUOUS
            reasons = _reason_set("RC-072")
        else:
            prior_candidates = {
                mapping_signature(item.mappings) for item in existing.revisions
            }
            if candidate_mapping not in prior_candidates:
                raise InterventionError(
                    "RESULTING_LINK_RESOLUTION_MAPPING_INVALID",
                    reasons=_reason_set("RC-081"),
                )
            expected_state = (
                ResultingOrderLinkState.AUTO_LINKED
                if system_evidence
                else ResultingOrderLinkState.HUMAN_CONFIRMED
            )
            reasons = _reason_set(
                "RC-070"
                if expected_state is ResultingOrderLinkState.AUTO_LINKED
                else "RC-071"
            )
    revision = ResultingOrderLinkRevision._from_evidence(
        revision_id=revision_id,
        revision=len(existing.revisions) + 1,
        state=expected_state,
        predecessor_sha256=current_binding.sha256,
        evidence_record=evidence,
        factory_capability=_RESULTING_LINK_REVISION_TOKEN,
    )
    link = DOIResultingOrderLink(
        link_id=existing.link_id,
        intervention_id=existing.intervention_id,
        intervention_action_binding=existing.intervention_action_binding,
        parent_order_id=existing.parent_order_id,
        child_order_id=existing.child_order_id,
        intervention_type=existing.intervention_type,
        state=expected_state,
        resulting_order_target_rep_proof=revision.resulting_order_target_rep_proof,
        revisions=(*existing.revisions, revision),
    )
    return ResultingLinkResult(link, reasons, False)


@dataclass(frozen=True, slots=True, init=False, repr=False)
class ResultingLinkSearchEvidence:
    """One complete, immutable synthetic resulting-order search observation."""

    evidence_id: EvidenceId
    search_id: EvidenceId
    parent_order_id: DoiOrderId
    intervention_type: InterventionType
    candidate_order_ids: tuple[DoiOrderId, ...]
    disproved_candidate_order_ids: tuple[DoiOrderId, ...]
    observed_at: CanonicalTimestamp
    source: SourceRef
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-resulting-link-search-evidence/v1"

    def __new__(cls) -> ResultingLinkSearchEvidence:
        raise InterventionError("RESULTING_LINK_SEARCH_EVIDENCE_FACTORY_REQUIRED")

    @classmethod
    def from_complete_search(
        cls,
        *,
        evidence_id: EvidenceId,
        search_id: EvidenceId,
        parent_order_id: DoiOrderId,
        intervention_type: InterventionType,
        candidate_order_ids: tuple[DoiOrderId, ...],
        disproved_candidate_order_ids: tuple[DoiOrderId, ...] = (),
        observed_at: CanonicalTimestamp,
        source: SourceRef,
    ) -> ResultingLinkSearchEvidence:
        if (
            type(evidence_id) is not EvidenceId
            or type(search_id) is not EvidenceId
            or type(parent_order_id) is not DoiOrderId
            or intervention_type
            not in {
                InterventionType.FULFILLMENT_SPLIT,
                InterventionType.PRODUCT_SUBSTITUTION,
            }
            or type(candidate_order_ids) is not tuple
            or any(type(item) is not DoiOrderId for item in candidate_order_ids)
            or type(disproved_candidate_order_ids) is not tuple
            or any(
                type(item) is not DoiOrderId
                for item in disproved_candidate_order_ids
            )
            or type(observed_at) is not CanonicalTimestamp
            or type(source) is not SourceRef
            or source.source_kind is not SourceKind.SYNTHETIC_ORDER_FIXTURE
            or source.object_namespace is not SourceObjectNamespace.SYNTHETIC_ORDER
            or source.object_id != parent_order_id.value
        ):
            raise InterventionError("RESULTING_LINK_SEARCH_EVIDENCE_INVALID")
        candidate_keys = tuple(item.to_json_value() for item in candidate_order_ids)
        disproved_keys = tuple(
            item.to_json_value() for item in disproved_candidate_order_ids
        )
        if (
            candidate_keys != tuple(sorted(candidate_keys))
            or len(candidate_keys) != len(set(candidate_keys))
            or disproved_keys != tuple(sorted(disproved_keys))
            or len(disproved_keys) != len(set(disproved_keys))
            or parent_order_id.to_json_value() in candidate_keys
            or parent_order_id.to_json_value() in disproved_keys
            or len(candidate_keys) == 1
            or (candidate_keys and disproved_keys)
        ):
            raise InterventionError("RESULTING_LINK_SEARCH_CANDIDATES_INVALID")
        instance = object.__new__(cls)
        object.__setattr__(instance, "evidence_id", evidence_id)
        object.__setattr__(instance, "search_id", search_id)
        object.__setattr__(instance, "parent_order_id", parent_order_id)
        object.__setattr__(instance, "intervention_type", intervention_type)
        object.__setattr__(instance, "candidate_order_ids", candidate_order_ids)
        object.__setattr__(
            instance,
            "disproved_candidate_order_ids",
            disproved_candidate_order_ids,
        )
        object.__setattr__(instance, "observed_at", observed_at)
        object.__setattr__(instance, "source", source)
        object.__setattr__(instance, "schema_version", INTERVENTION_SCHEMA_VERSION)
        instance.__post_init__()
        return instance

    def __post_init__(self) -> None:
        if (
            type(self.evidence_id) is not EvidenceId
            or type(self.search_id) is not EvidenceId
            or type(self.parent_order_id) is not DoiOrderId
            or type(self.intervention_type) is not InterventionType
            or type(self.candidate_order_ids) is not tuple
            or type(self.disproved_candidate_order_ids) is not tuple
            or type(self.observed_at) is not CanonicalTimestamp
            or type(self.source) is not SourceRef
            or self.source.object_id != self.parent_order_id.value
            or self.schema_version != INTERVENTION_SCHEMA_VERSION
        ):
            raise InterventionError("RESULTING_LINK_SEARCH_EVIDENCE_INVALID")

    @property
    def state(self) -> ResultingOrderLinkSearchState:
        return (
            ResultingOrderLinkSearchState.AMBIGUOUS
            if self.candidate_order_ids
            else ResultingOrderLinkSearchState.NOT_FOUND
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_order_ids": [
                item.to_json_value() for item in self.candidate_order_ids
            ],
            "disproved_candidate_order_ids": [
                item.to_json_value() for item in self.disproved_candidate_order_ids
            ],
            "evidence_id": self.evidence_id.value,
            "intervention_type": self.intervention_type.value,
            "observed_at": self.observed_at.value,
            "parent_order_id": self.parent_order_id.to_json_value(),
            "schema_version": self.schema_version,
            "search_id": self.search_id.value,
            "source": _hash(self.source.hash_binding()),
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "ResultingLinkSearchEvidence(<redacted>)"


_RESULTING_LINK_SEARCH_EVENT_TOKEN = object()


@dataclass(frozen=True, slots=True, init=False, repr=False)
class ResultingLinkSearchEvent:
    event_id: EvidenceId
    search_id: EvidenceId
    sequence: int
    predecessor_binding: HashBinding | None
    evidence: ResultingLinkSearchEvidence = field(repr=False)
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-resulting-link-search-event/v1"

    def __new__(cls) -> ResultingLinkSearchEvent:
        raise InterventionError("RESULTING_LINK_SEARCH_REDUCER_REQUIRED")

    @classmethod
    def _create(
        cls,
        *,
        event_id: EvidenceId,
        sequence: int,
        predecessor_binding: HashBinding | None,
        evidence: ResultingLinkSearchEvidence,
        factory_capability: object,
    ) -> ResultingLinkSearchEvent:
        if factory_capability is not _RESULTING_LINK_SEARCH_EVENT_TOKEN:
            raise InterventionError("RESULTING_LINK_SEARCH_REDUCER_REQUIRED")
        instance = object.__new__(cls)
        object.__setattr__(instance, "event_id", event_id)
        object.__setattr__(instance, "search_id", evidence.search_id)
        object.__setattr__(instance, "sequence", sequence)
        object.__setattr__(instance, "predecessor_binding", predecessor_binding)
        object.__setattr__(instance, "evidence", evidence)
        object.__setattr__(instance, "schema_version", INTERVENTION_SCHEMA_VERSION)
        instance.__post_init__()
        return instance

    def __post_init__(self) -> None:
        if (
            type(self.event_id) is not EvidenceId
            or type(self.search_id) is not EvidenceId
            or type(self.sequence) is not int
            or self.sequence < 1
            or type(self.evidence) is not ResultingLinkSearchEvidence
            or self.evidence.search_id != self.search_id
            or (self.sequence == 1) != (self.predecessor_binding is None)
            or (
                self.predecessor_binding is not None
                and (
                    type(self.predecessor_binding) is not HashBinding
                    or self.predecessor_binding.domain != self.HASH_DOMAIN
                )
            )
            or self.schema_version != INTERVENTION_SCHEMA_VERSION
        ):
            raise InterventionError("RESULTING_LINK_SEARCH_EVENT_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id.value,
            "evidence": _hash(self.evidence.hash_binding()),
            "predecessor_binding": (
                None
                if self.predecessor_binding is None
                else _hash(self.predecessor_binding)
            ),
            "schema_version": self.schema_version,
            "search_id": self.search_id.value,
            "sequence": self.sequence,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "ResultingLinkSearchEvent(<redacted>)"


@dataclass(frozen=True, slots=True, init=False, repr=False)
class DOIResultingOrderLinkSearch:
    search_id: EvidenceId
    parent_order_id: DoiOrderId
    intervention_type: InterventionType
    state: ResultingOrderLinkSearchState
    candidate_order_ids: tuple[DoiOrderId, ...]
    revision: int
    head_event_binding: HashBinding
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-resulting-order-link-search/v1"

    def __new__(cls) -> DOIResultingOrderLinkSearch:
        raise InterventionError("RESULTING_LINK_SEARCH_REDUCER_REQUIRED")

    @classmethod
    def _from_event(
        cls,
        event: ResultingLinkSearchEvent,
    ) -> DOIResultingOrderLinkSearch:
        instance = object.__new__(cls)
        object.__setattr__(instance, "search_id", event.search_id)
        object.__setattr__(instance, "parent_order_id", event.evidence.parent_order_id)
        object.__setattr__(
            instance,
            "intervention_type",
            event.evidence.intervention_type,
        )
        object.__setattr__(instance, "state", event.evidence.state)
        object.__setattr__(
            instance,
            "candidate_order_ids",
            event.evidence.candidate_order_ids,
        )
        object.__setattr__(instance, "revision", event.sequence)
        object.__setattr__(instance, "head_event_binding", event.hash_binding())
        object.__setattr__(instance, "schema_version", INTERVENTION_SCHEMA_VERSION)
        instance.__post_init__()
        return instance

    def __post_init__(self) -> None:
        keys = tuple(item.to_json_value() for item in self.candidate_order_ids)
        if (
            type(self.search_id) is not EvidenceId
            or type(self.parent_order_id) is not DoiOrderId
            or self.intervention_type
            not in {
                InterventionType.FULFILLMENT_SPLIT,
                InterventionType.PRODUCT_SUBSTITUTION,
            }
            or type(self.state) is not ResultingOrderLinkSearchState
            or type(self.candidate_order_ids) is not tuple
            or any(type(item) is not DoiOrderId for item in self.candidate_order_ids)
            or type(self.revision) is not int
            or self.revision < 1
            or type(self.head_event_binding) is not HashBinding
            or self.head_event_binding.domain != ResultingLinkSearchEvent.HASH_DOMAIN
            or self.schema_version != INTERVENTION_SCHEMA_VERSION
            or (self.state is ResultingOrderLinkSearchState.NOT_FOUND) != (not keys)
            or (
                self.state is ResultingOrderLinkSearchState.AMBIGUOUS
                and len(keys) < 2
            )
        ):
            raise InterventionError("RESULTING_LINK_SEARCH_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_order_ids": [
                item.to_json_value() for item in self.candidate_order_ids
            ],
            "head_event_binding": _hash(self.head_event_binding),
            "intervention_type": self.intervention_type.value,
            "parent_order_id": self.parent_order_id.to_json_value(),
            "revision": self.revision,
            "schema_version": self.schema_version,
            "search_id": self.search_id.value,
            "state": self.state.value,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    @property
    def reasons(self) -> ReasonSet:
        if self.state is ResultingOrderLinkSearchState.NOT_FOUND:
            return _reason_set("RC-073")
        return _reason_set("RC-072")

    def __repr__(self) -> str:
        return "DOIResultingOrderLinkSearch(<redacted>)"


@dataclass(frozen=True, slots=True)
class DOIResultingOrderLinkSearchHistory:
    search_id: EvidenceId
    parent_order_id: DoiOrderId
    intervention_type: InterventionType
    projection: DOIResultingOrderLinkSearch | None = None
    events: tuple[ResultingLinkSearchEvent, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.search_id) is not EvidenceId
            or type(self.parent_order_id) is not DoiOrderId
            or self.intervention_type
            not in {
                InterventionType.FULFILLMENT_SPLIT,
                InterventionType.PRODUCT_SUBSTITUTION,
            }
            or type(self.events) is not tuple
            or any(type(item) is not ResultingLinkSearchEvent for item in self.events)
        ):
            raise InterventionError("RESULTING_LINK_SEARCH_HISTORY_INVALID")
        for index, event in enumerate(self.events, start=1):
            expected_predecessor = (
                None if index == 1 else self.events[index - 2].hash_binding()
            )
            if (
                event.search_id != self.search_id
                or event.evidence.parent_order_id != self.parent_order_id
                or event.evidence.intervention_type is not self.intervention_type
                or event.sequence != index
                or event.predecessor_binding != expected_predecessor
            ):
                raise InterventionError("RESULTING_LINK_SEARCH_HISTORY_INVALID")
        if not self.events:
            if self.projection is not None:
                raise InterventionError("RESULTING_LINK_SEARCH_HISTORY_INVALID")
        elif (
            type(self.projection) is not DOIResultingOrderLinkSearch
            or self.projection.revision != len(self.events)
            or self.projection.head_event_binding != self.events[-1].hash_binding()
        ):
            raise InterventionError("RESULTING_LINK_SEARCH_HISTORY_INVALID")


@dataclass(frozen=True, slots=True)
class ResultingLinkSearchResult:
    history: DOIResultingOrderLinkSearchHistory
    event: ResultingLinkSearchEvent
    reasons: ReasonSet
    replayed: bool


def append_resulting_link_search(
    history: DOIResultingOrderLinkSearchHistory,
    *,
    event_id: EvidenceId,
    evidence: ResultingLinkSearchEvidence,
) -> ResultingLinkSearchResult:
    """Apply TR-088/TR-089 with exact predecessor and candidate-set semantics."""

    if (
        type(history) is not DOIResultingOrderLinkSearchHistory
        or type(event_id) is not EvidenceId
        or type(evidence) is not ResultingLinkSearchEvidence
        or evidence.search_id != history.search_id
        or evidence.parent_order_id != history.parent_order_id
        or evidence.intervention_type is not history.intervention_type
    ):
        raise InterventionError("RESULTING_LINK_SEARCH_REDUCER_INPUT_INVALID")
    for retained in history.events:
        if retained.event_id == event_id or (
            retained.evidence.evidence_id == evidence.evidence_id
        ):
            if retained.evidence.canonical_bytes() != evidence.canonical_bytes():
                raise InterventionError(
                    "RESULTING_LINK_SEARCH_EVENT_CONFLICT",
                    reasons=_reason_set("RC-111"),
                )
            return ResultingLinkSearchResult(
                history,
                retained,
                (
                    _reason_set("RC-073")
                    if retained.evidence.state
                    is ResultingOrderLinkSearchState.NOT_FOUND
                    else _reason_set("RC-072")
                ),
                True,
            )
    prior = history.projection
    if evidence.state is ResultingOrderLinkSearchState.NOT_FOUND:
        if prior is not None and prior.state is ResultingOrderLinkSearchState.AMBIGUOUS:
            if evidence.disproved_candidate_order_ids != prior.candidate_order_ids:
                raise InterventionError(
                    "RESULTING_LINK_SEARCH_DISPROOF_INCOMPLETE",
                    reasons=_reason_set("RC-081"),
                )
        elif evidence.disproved_candidate_order_ids:
            raise InterventionError(
                "RESULTING_LINK_SEARCH_DISPROOF_SCOPE_INVALID",
                reasons=_reason_set("RC-081"),
            )
    elif evidence.disproved_candidate_order_ids:
        raise InterventionError(
            "RESULTING_LINK_SEARCH_DISPROOF_SCOPE_INVALID",
            reasons=_reason_set("RC-081"),
        )
    event = ResultingLinkSearchEvent._create(
        event_id=event_id,
        sequence=len(history.events) + 1,
        predecessor_binding=(
            None if not history.events else history.events[-1].hash_binding()
        ),
        evidence=evidence,
        factory_capability=_RESULTING_LINK_SEARCH_EVENT_TOKEN,
    )
    projection = DOIResultingOrderLinkSearch._from_event(event)
    updated = DOIResultingOrderLinkSearchHistory(
        search_id=history.search_id,
        parent_order_id=history.parent_order_id,
        intervention_type=history.intervention_type,
        projection=projection,
        events=(*history.events, event),
    )
    reasons = (
        _reason_set("RC-073")
        if projection.state is ResultingOrderLinkSearchState.NOT_FOUND
        else _reason_set("RC-072")
    )
    return ResultingLinkSearchResult(updated, event, reasons, False)


def intervention_hash_contracts() -> dict[str, str]:
    """Return every hash-bearing domain implemented by this module."""

    contracts = {
        class_.__name__: class_.HASH_DOMAIN
        for class_ in (
            LogicalEvidenceKey,
            ActionVerificationMaterial,
            VerificationEvidence,
            ActionVerificationEvent,
            SystemExactValueRecord,
            AuthorizedHumanExactValueRecord,
            ValueEvent,
            DOIIntervention,
            TargetRepObservation,
            TargetRepVerificationProof,
            SystemResultingLinkEvidence,
            AuthorizedHumanResultingLinkEvidence,
            ResultingOrderLinkRevision,
            DOIResultingOrderLink,
            ResultingLinkSearchEvidence,
            ResultingLinkSearchEvent,
            DOIResultingOrderLinkSearch,
        )
    }
    return contracts


def _intervention_hash_fixture_records(
) -> tuple[dict[str, object], DOIActionContext, SourceRef]:
    """Build the typed intervention KAT graph for local and dependent providers."""

    open_context = model_action_context_fixture()
    opening_id = EvidenceId(
        "SYN-EVIDENCE-DOI-MODEL-KAT-ACTION-CONTEXT-EVENT"
    )
    opening = DOIActionContextEvent.opened(
        event_id=opening_id,
        action_context_id=open_context.action_context_id,
        opening_authorization=open_context.opening_authorization,
        created_at=open_context.created_at,
        guard=DOIOccurrenceGuard(
            guard_id=opening_id,
            owner_id=open_context.action_context_id,
            occurrence_id=open_context.opening_authorization.attempt_intent_id,
            source=open_context.opening_authorization.source,
        ),
    )
    opened = reduce_action_context(
        DOIActionContextHistory(action_context_id=open_context.action_context_id),
        opening,
    )
    if opened.history.projection != open_context:
        raise InterventionError("INTERVENTION_HASH_CONTEXT_FIXTURE_INVALID")
    completion_id = EvidenceId(
        "SYN-EVIDENCE-DOI-INTERVENTION-KAT-CONTEXT-COMPLETE"
    )
    completion_occurrence = InteractionId(
        "SYN-INTERACTION-DOI-INTERVENTION-KAT-CONTEXT-COMPLETE"
    )
    completion_source = SourceRef.create(
        source_ref_id=EvidenceId(
            "SYN-EVIDENCE-DOI-INTERVENTION-KAT-CONTEXT-COMPLETE-SOURCE"
        ),
        source_kind=SourceKind.SYNTHETIC_INTERACTION_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_INTERACTION,
        object_id=completion_occurrence,
    )
    action_time = CanonicalTimestamp("2026-08-20T14:16:00Z")
    completion = DOIActionContextEvent.completed(
        event_id=completion_id,
        action_context=open_context,
        completion_trigger=ActionContextCompletionTrigger.SYSTEM_VERIFIED,
        occurred_at=action_time,
        close_reason=ActionContextCloseReason.ACTION_VERIFIED,
        guard=DOIOccurrenceGuard(
            guard_id=completion_id,
            owner_id=open_context.action_context_id,
            occurrence_id=completion_occurrence,
            source=completion_source,
        ),
    )
    completed_history = reduce_action_context(opened.history, completion).history
    action_proof = CompletedSystemActionProof.from_history(
        history=completed_history,
    )
    action_source = SourceRef.create(
        source_ref_id=EvidenceId("SYN-EVIDENCE-DOI-INTERVENTION-KAT-ORDER-SOURCE"),
        source_kind=SourceKind.SYNTHETIC_ORDER_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_ORDER,
        object_id=open_context.order_id.value,
    )
    intervention_id = EvidenceId("SYN-EVIDENCE-DOI-INTERVENTION-KAT")
    evidence = VerificationEvidence.from_system_observation(
        evidence_id=EvidenceId("SYN-EVIDENCE-DOI-INTERVENTION-KAT-ACTION-PROOF"),
        intervention_id=intervention_id,
        opportunity_id=open_context.opportunity_id,
        intervention_type=open_context.intervention_type,
        completed_action_proof=action_proof,
        source=action_source,
        occurred_at=action_time,
    )
    key = LogicalEvidenceKey(
        key_id=EvidenceId("SYN-EVIDENCE-DOI-INTERVENTION-KAT-ACTION-KEY"),
        owner_id=intervention_id,
        occurrence_id=evidence.evidence_id,
        kind=EvidenceKeyKind.ACTION,
    )
    action = ActionVerificationEvent(
        event_id=EvidenceId("SYN-EVIDENCE-DOI-INTERVENTION-KAT-ACTION-EVENT"),
        intervention_id=intervention_id,
        opportunity_id=open_context.opportunity_id,
        intervention_type=open_context.intervention_type,
        key=key,
        evidence=evidence,
    )
    intervention = record_verified_intervention(None, action).intervention
    amount = Money.from_minor_units(
        1_234,
        currency_code="USD",
        registry_version=CURRENCY_REGISTRY_VERSION,
        scale=2,
    )
    system_value_record = SystemExactValueRecord.from_order_observation(
        record_id=EvidenceId("SYN-EVIDENCE-DOI-INTERVENTION-KAT-VALUE-RECORD"),
        intervention=intervention,
        completed_action_context=action_proof.completed_context,
        event_type=ValueEventType.INITIAL_VERIFIED_VALUE,
        amount=amount,
        predecessor_event=None,
        correction_kind=None,
        observed_at=CanonicalTimestamp("2026-08-20T14:16:01Z"),
        source=action_source,
    )
    value_event = ValueEvent.from_system_record(
        event_id=EvidenceId("SYN-EVIDENCE-DOI-INTERVENTION-KAT-VALUE-EVENT"),
        key_id=EvidenceId("SYN-EVIDENCE-DOI-INTERVENTION-KAT-VALUE-KEY"),
        record=system_value_record,
    )
    intervention = append_value_event(intervention, value_event).intervention

    human_occurrence = InteractionId(
        "SYN-INTERACTION-DOI-INTERVENTION-KAT-HUMAN-FACT"
    )
    human_source = SourceRef.create(
        source_ref_id=EvidenceId(
            "SYN-EVIDENCE-DOI-INTERVENTION-KAT-HUMAN-FACT-SOURCE"
        ),
        source_kind=SourceKind.SYNTHETIC_INTERACTION_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_INTERACTION,
        object_id=human_occurrence,
    )
    authority = verify_synthetic_human_authority(
        grant_id=EvidenceId("SYN-EVIDENCE-DOI-INTERVENTION-KAT-HUMAN-AUTHORITY"),
        actor=RepId("SYN-REP-DOI-INTERVENTION-KAT-AUTHORIZED"),
        action_context=open_context,
        granted_at=CanonicalTimestamp("2026-08-20T14:15:16Z"),
        authority_source=human_source,
    )
    human_fact = StructuredHumanFact.create(
        fact_id=EvidenceId("SYN-EVIDENCE-DOI-INTERVENTION-KAT-HUMAN-FACT"),
        action_context=open_context,
        evaluation_id=open_context.evaluation_id,
        usage_kind=HumanFactUsageKind.NO_ACTION_DECISION,
        result_code=HumanFactResultCode.APPROVED,
        authority_grant=authority,
        occurred_at=CanonicalTimestamp("2026-08-20T14:15:17Z"),
        source=human_source,
    )
    human_stream = EvidenceId("SYN-EVIDENCE-DOI-INTERVENTION-KAT-HUMAN-STREAM")
    human_event_id = EvidenceId(
        "SYN-EVIDENCE-DOI-INTERVENTION-KAT-HUMAN-EVENT"
    )
    human_event = DOIHumanFactEvent(
        event_id=human_event_id,
        stream_id=human_stream,
        event_type=HumanFactEventType.RECORDED,
        fact=human_fact,
        corrects_event_id=None,
        recorded_at=CanonicalTimestamp("2026-08-20T14:15:17Z"),
        sequence=1,
        predecessor_binding=None,
        guard=DOIOccurrenceGuard(
            guard_id=human_event_id,
            owner_id=human_stream,
            occurrence_id=human_occurrence,
            source=human_source,
        ),
    )
    human_history = reduce_human_fact(
        DOIHumanFactHistory(stream_id=human_stream),
        human_event,
    ).history
    human_proof = AcceptedHumanFactProof.from_history(human_history)
    human_value_record = AuthorizedHumanExactValueRecord.from_reduced_human_fact(
        record_id=EvidenceId(
            "SYN-EVIDENCE-DOI-INTERVENTION-KAT-HUMAN-VALUE-RECORD"
        ),
        intervention=intervention,
        human_fact_proof=human_proof,
        event_type=ValueEventType.CORRECTION,
        amount=amount,
        predecessor_event=value_event,
        correction_kind=ValueCorrectionKind.ORIGINAL_VALUE_CORRECTED,
    )

    link_id = EvidenceId("SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK")
    child = DoiOrderId(OrderId("SYN-ORDER-DOI-INTERVENTION-KAT-CHILD"))
    child_source = SourceRef.create(
        source_ref_id=EvidenceId(
            "SYN-EVIDENCE-DOI-INTERVENTION-KAT-CHILD-SOURCE"
        ),
        source_kind=SourceKind.SYNTHETIC_ORDER_FIXTURE,
        object_namespace=SourceObjectNamespace.SYNTHETIC_ORDER,
        object_id=child.value,
    )
    rep_observation = TargetRepObservation.from_order_observation(
        observation_id=EvidenceId(
            "SYN-EVIDENCE-DOI-INTERVENTION-KAT-REP-OBSERVATION"
        ),
        link_id=link_id,
        intervention=intervention,
        scope=TargetRepProofScope.RESULTING_ORDER,
        subject_order_id=child,
        subject_line_id=None,
        observed_rep_id=TARGET_REP_ID,
        observed_relation=RepRelation.TARGET_REP_OWNED,
        observed_at=CanonicalTimestamp("2026-08-20T14:17:00Z"),
        source=child_source,
    )
    rep_proof = TargetRepVerificationProof.from_observation(
        proof_id=EvidenceId("SYN-EVIDENCE-DOI-INTERVENTION-KAT-REP-PROOF"),
        intervention=intervention,
        observation=rep_observation,
    )
    mappings = tuple(
        MovedLineMappingComponent(
            parent_line_id=parent_line,
            child_line_id=LineSnapshotId(
                EvidenceId(
                    f"SYN-EVIDENCE-DOI-INTERVENTION-KAT-CHILD-LINE-{index:04d}"
                )
            ),
            quantity=PositiveQuantity(1),
            replacement_line_target_rep_proof=None,
        )
        for index, parent_line in enumerate(
            action_proof.completed_context.line_scope,
            start=1,
        )
    )
    system_link_evidence = SystemResultingLinkEvidence.from_order_observation(
        evidence_id=EvidenceId(
            "SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK-SYSTEM-EVIDENCE"
        ),
        link_id=link_id,
        parent_order_id=open_context.order_id,
        child_order_id=child,
        intervention=intervention,
        completed_action_context=action_proof.completed_context,
        mappings=mappings,
        resulting_order_target_rep_proof=rep_proof,
        predecessor_revision=None,
        resolves_conflict_revision=None,
        observed_at=CanonicalTimestamp("2026-08-20T14:17:00Z"),
        source=child_source,
    )
    link_result = append_resulting_link_revision(
        None,
        revision_id=EvidenceId(
            "SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK-REVISION"
        ),
        intervention=intervention,
        evidence=system_link_evidence,
    )
    revision = link_result.link.revisions[-1]
    human_link_evidence = AuthorizedHumanResultingLinkEvidence.from_reduced_human_fact(
        evidence_id=EvidenceId(
            "SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK-HUMAN-EVIDENCE"
        ),
        link_id=link_id,
        parent_order_id=open_context.order_id,
        child_order_id=child,
        intervention=intervention,
        human_fact_proof=human_proof,
        mappings=mappings,
        resulting_order_target_rep_proof=rep_proof,
        predecessor_revision=revision,
        resolves_conflict_revision=None,
    )

    search_id = EvidenceId("SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK-SEARCH")
    search_evidence = ResultingLinkSearchEvidence.from_complete_search(
        evidence_id=EvidenceId(
            "SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK-SEARCH-EVIDENCE"
        ),
        search_id=search_id,
        parent_order_id=open_context.order_id,
        intervention_type=intervention.intervention_type,
        candidate_order_ids=(),
        disproved_candidate_order_ids=(),
        observed_at=CanonicalTimestamp("2026-08-20T14:18:00Z"),
        source=action_source,
    )
    search_result = append_resulting_link_search(
        DOIResultingOrderLinkSearchHistory(
            search_id=search_id,
            parent_order_id=open_context.order_id,
            intervention_type=intervention.intervention_type,
        ),
        event_id=EvidenceId(
            "SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK-SEARCH-EVENT"
        ),
        evidence=search_evidence,
    )
    if search_result.history.projection is None:
        raise InterventionError("INTERVENTION_HASH_SEARCH_FIXTURE_INVALID")
    records = {
        "LogicalEvidenceKey": key,
        "ActionVerificationMaterial": evidence.material,
        "VerificationEvidence": evidence,
        "ActionVerificationEvent": action,
        "SystemExactValueRecord": system_value_record,
        "AuthorizedHumanExactValueRecord": human_value_record,
        "ValueEvent": value_event,
        "DOIIntervention": intervention,
        "TargetRepObservation": rep_observation,
        "TargetRepVerificationProof": rep_proof,
        "SystemResultingLinkEvidence": system_link_evidence,
        "AuthorizedHumanResultingLinkEvidence": human_link_evidence,
        "ResultingOrderLinkRevision": revision,
        "DOIResultingOrderLink": link_result.link,
        "ResultingLinkSearchEvidence": search_evidence,
        "ResultingLinkSearchEvent": search_result.event,
        "DOIResultingOrderLinkSearch": search_result.history.projection,
    }
    return records, action_proof.completed_context, action_source


def intervention_hash_fixtures() -> tuple[tuple[str, str, bytes, str], ...]:
    """Return one deterministic representative binding for every local hash record."""

    records, _, _ = _intervention_hash_fixture_records()
    fixtures = tuple(
        (
            name,
            record.hash_binding().domain,
            record.canonical_bytes(),
            record.hash_binding().sha256,
        )
        for name, record in sorted(records.items())
    )
    contracts = intervention_hash_contracts()
    if (
        set(records) != set(contracts)
        or any(records[name].HASH_DOMAIN != domain for name, domain in contracts.items())
    ):
        raise InterventionError("INTERVENTION_HASH_FIXTURE_INVENTORY_INVALID")
    if INTERVENTION_HASH_KNOWN_ANSWERS and {
        name: digest for name, _, _, digest in fixtures
    } != dict(INTERVENTION_HASH_KNOWN_ANSWERS):
        raise InterventionError("INTERVENTION_HASH_KNOWN_ANSWER_MISMATCH")
    return fixtures


__all__ = [
    "AcceptedHumanFactProof",
    "ActionVerificationMaterial",
    "ActionVerificationEvent",
    "AuthorizedHumanExactValueRecord",
    "AuthorizedHumanResultingLinkEvidence",
    "CompletedHumanActionProof",
    "CompletedSystemActionProof",
    "DOIIntervention",
    "DOIResultingOrderLink",
    "DOIResultingOrderLinkSearch",
    "EvidenceKeyKind",
    "ExactValueRecord",
    "HumanValueInexactKind",
    "INTERVENTION_HASH_KNOWN_ANSWERS",
    "INTERVENTION_SCHEMA_VERSION",
    "InterventionError",
    "InterventionResult",
    "InterventionValueProjection",
    "LogicalEvidenceKey",
    "MovedLineMappingComponent",
    "ResultingLinkResult",
    "ResultingLinkEvidence",
    "ResultingLinkSearchEvidence",
    "ResultingLinkSearchEvent",
    "ResultingLinkSearchResult",
    "ResultingOrderLinkRevision",
    "DOIResultingOrderLinkSearchHistory",
    "SystemExactValueRecord",
    "SystemResultingLinkEvidence",
    "TARGET_REP_ID",
    "TargetRepProofScope",
    "TargetRepObservation",
    "TargetRepVerificationProof",
    "ValueCorrectionKind",
    "ValueEvent",
    "VerificationEvidence",
    "append_resulting_link_revision",
    "append_resulting_link_search",
    "append_value_event",
    "intervention_hash_contracts",
    "intervention_hash_fixtures",
    "record_verified_intervention",
    "reject_inexact_human_value",
    "require_verified_action",
    "require_verified_reversal_record",
]
