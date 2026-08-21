"""Typed DOI case-admission and attention owner reducers.

The generic lifecycle registry reducer deliberately knows nothing about business evidence.
This module owns the production-side evidence replay for TR-007/TR-008 and the complete
cause-keyed attention family.  Its decisions are sealed outputs: callers choose occurrence
identities, but cannot supply a verdict, cause key, resolver binding, transition, or state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Protocol, cast

from synthetic_sales_assist.doi.evaluator import evaluate_doi
from synthetic_sales_assist.doi.extraction import (
    DOIExtractionAttempt,
    DOIExtractionResult,
    ExtractionStatus,
)
from synthetic_sales_assist.doi.identities import (
    DoiOrderId,
    DoiRunId,
    ExtractionAttemptId,
    RunWorkItemId,
    SourceBatchId,
    SourceIdentityId,
    SourceRowRefId,
)
from synthetic_sales_assist.doi.interventions import (
    CompletedHumanActionProof,
    CompletedSystemActionProof,
    DOIIntervention,
    DOIResultingOrderLink,
    DOIResultingOrderLinkSearchHistory,
    InterventionError,
    append_resulting_link_revision,
    append_resulting_link_search,
    record_verified_intervention,
)
from synthetic_sales_assist.doi.models import (
    ActionVerificationState,
    AttentionCondition,
    CaseLifecycleState,
    DOIEvaluation,
    DOIEvaluationInput,
    DOIHumanFactHistory,
    DOIModelError,
    DOIOrderCase,
    DOIWWCHistory,
    HumanFactResultCode,
    HumanFactUsageKind,
    ResultingOrderLinkSearchState,
    ResultingOrderLinkState,
    SourcePresence,
    WWCProjectionState,
    reduce_human_fact,
    reduce_wwc,
)
from synthetic_sales_assist.doi.source import (
    DOIRunWorkItem,
    DOISourceBatch,
    DOIStagedOrder,
    RunWorkOrigin,
    SOURCE_ANCHORS,
    SOURCE_MAPPING_VERSION,
    SourceImportResult,
    SourceImportResultKind,
    SyntheticQueueImage,
    SyntheticQueueRow,
    ingest_synthetic_queue,
)
from synthetic_sales_assist.domain.canonical import (
    HashBinding,
    canonical_json_bytes,
    domain_hash,
)
from synthetic_sales_assist.domain.identities import (
    EvidenceId,
    InteractionId,
    OrderId,
    RunId,
)
from synthetic_sales_assist.domain.numeric import NonNegativeCount
from synthetic_sales_assist.domain.records import ReasonSet
from synthetic_sales_assist.domain.registries import (
    TransitionRef,
    load_doi_registries,
)
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.domain.tokens import ImmutableStrEnum


class CaseAttentionOwnerError(ValueError):
    """Closed, non-reflecting owner rejection."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _CanonicalRecord(Protocol):
    def canonical_bytes(self) -> bytes: ...

    def hash_binding(self) -> HashBinding: ...


def _hash_json(binding: HashBinding | None) -> dict[str, str] | None:
    if binding is None:
        return None
    return {"domain": binding.domain, "sha256": binding.sha256}


def _instant(value: CanonicalTimestamp) -> tuple[int, int]:
    return value.epoch_seconds, value.nanosecond


def _case_json(case: DOIOrderCase) -> dict[str, object]:
    return {
        "case_id": case.case_id.value,
        "current_evaluation_id": (
            None
            if case.current_evaluation_id is None
            else case.current_evaluation_id.value
        ),
        "current_snapshot_id": (
            None
            if case.current_snapshot_id is None
            else case.current_snapshot_id.to_json_value()
        ),
        "lifecycle_state": case.lifecycle_state.value,
        "order_id": case.order_id.to_json_value(),
        "terminal_closure_reason": (
            None
            if case.terminal_closure_reason is None
            else case.terminal_closure_reason.value
        ),
    }


def _same_record(left: object, right: object) -> bool:
    left_canonical = getattr(left, "canonical_bytes", None)
    right_canonical = getattr(right, "canonical_bytes", None)
    return (
        type(left) is type(right)
        and callable(left_canonical)
        and callable(right_canonical)
        and left_canonical() == right_canonical()
    )


_CASE_SOURCE_ARTIFACT_TOKEN = object()
_CASE_EVENT_TOKEN = object()
_CASE_DECISION_TOKEN = object()


@dataclass(frozen=True, slots=True, init=False, repr=False)
class DOICaseSourceAdmissionProofV1:
    """Privacy-minimized case-owned proof produced before source-attempt deletion."""

    proof_id: EvidenceId
    case_id: EvidenceId
    order_id: DoiOrderId
    target_assignee: str
    source_batch_id: SourceBatchId
    case_source_binding_id: EvidenceId
    admitted_at: CanonicalTimestamp
    content_binding: HashBinding
    schema_version: str
    _issuer_token: object = field(repr=False, compare=False)

    HASH_DOMAIN: ClassVar[str] = "doi-case-source-admission-proof/v1"

    def __new__(cls) -> DOICaseSourceAdmissionProofV1:
        raise CaseAttentionOwnerError("CASE_ADMISSION_FACTORY_REQUIRED")

    @classmethod
    def _create(
        cls,
        *,
        proof_id: EvidenceId,
        case_id: EvidenceId,
        order_id: DoiOrderId,
        source_batch_id: SourceBatchId,
        case_source_binding_id: EvidenceId,
        admitted_at: CanonicalTimestamp,
        content_binding: HashBinding,
        factory_capability: object,
    ) -> DOICaseSourceAdmissionProofV1:
        if factory_capability is not _CASE_SOURCE_ARTIFACT_TOKEN:
            raise CaseAttentionOwnerError("CASE_ADMISSION_FACTORY_REQUIRED")
        instance = object.__new__(cls)
        for name, value in (
            ("proof_id", proof_id),
            ("case_id", case_id),
            ("order_id", order_id),
            ("target_assignee", "TARGET_REP"),
            ("source_batch_id", source_batch_id),
            ("case_source_binding_id", case_source_binding_id),
            ("admitted_at", admitted_at),
            ("content_binding", content_binding),
            ("schema_version", cls.HASH_DOMAIN),
            ("_issuer_token", _CASE_SOURCE_ARTIFACT_TOKEN),
        ):
            object.__setattr__(instance, name, value)
        instance.__post_init__()
        return instance

    def __post_init__(self) -> None:
        if (
            type(self.proof_id) is not EvidenceId
            or type(self.case_id) is not EvidenceId
            or type(self.order_id) is not DoiOrderId
            or self.target_assignee != "TARGET_REP"
            or type(self.source_batch_id) is not SourceBatchId
            or type(self.case_source_binding_id) is not EvidenceId
            or type(self.admitted_at) is not CanonicalTimestamp
            or type(self.content_binding) is not HashBinding
            or self.content_binding.domain != DOISourceBatch.IDENTITY_DOMAIN
            or self.schema_version != self.HASH_DOMAIN
            or self._issuer_token is not _CASE_SOURCE_ARTIFACT_TOKEN
        ):
            raise CaseAttentionOwnerError("CASE_ADMISSION_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "admitted_at": self.admitted_at.value,
            "case_id": self.case_id.value,
            "case_source_binding_id": self.case_source_binding_id.value,
            "content_binding": _hash_json(self.content_binding),
            "order_id": self.order_id.to_json_value(),
            "proof_id": self.proof_id.value,
            "schema_version": self.schema_version,
            "source_batch_id": self.source_batch_id.to_json_value(),
            "target_assignee": self.target_assignee,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "DOICaseSourceAdmissionProofV1(<closed>)"


@dataclass(frozen=True, slots=True, init=False, repr=False)
class OwnedCaseSourceBinding:
    binding_id: EvidenceId
    case_id: EvidenceId
    order_id: DoiOrderId
    source_batch_id: SourceBatchId
    batch_identity: HashBinding
    admission_proof: DOICaseSourceAdmissionProofV1
    schema_version: str
    _issuer_token: object = field(repr=False, compare=False)

    HASH_DOMAIN: ClassVar[str] = "doi-case-source-binding/v2"

    def __new__(cls) -> OwnedCaseSourceBinding:
        raise CaseAttentionOwnerError("CASE_SOURCE_BINDING_FACTORY_REQUIRED")

    @classmethod
    def _create(
        cls,
        *,
        admission_proof: DOICaseSourceAdmissionProofV1,
        factory_capability: object,
    ) -> OwnedCaseSourceBinding:
        if factory_capability is not _CASE_SOURCE_ARTIFACT_TOKEN:
            raise CaseAttentionOwnerError("CASE_SOURCE_BINDING_FACTORY_REQUIRED")
        instance = object.__new__(cls)
        for name, value in (
            ("binding_id", admission_proof.case_source_binding_id),
            ("case_id", admission_proof.case_id),
            ("order_id", admission_proof.order_id),
            ("source_batch_id", admission_proof.source_batch_id),
            ("batch_identity", admission_proof.content_binding),
            ("admission_proof", admission_proof),
            ("schema_version", cls.HASH_DOMAIN),
            ("_issuer_token", _CASE_SOURCE_ARTIFACT_TOKEN),
        ):
            object.__setattr__(instance, name, value)
        instance.__post_init__()
        return instance

    def __post_init__(self) -> None:
        proof = self.admission_proof
        if (
            type(self.binding_id) is not EvidenceId
            or type(self.case_id) is not EvidenceId
            or type(self.order_id) is not DoiOrderId
            or type(self.source_batch_id) is not SourceBatchId
            or type(self.batch_identity) is not HashBinding
            or type(proof) is not DOICaseSourceAdmissionProofV1
            or proof._issuer_token is not _CASE_SOURCE_ARTIFACT_TOKEN
            or proof.case_source_binding_id != self.binding_id
            or proof.case_id != self.case_id
            or proof.order_id != self.order_id
            or proof.source_batch_id != self.source_batch_id
            or proof.content_binding != self.batch_identity
            or self.schema_version != self.HASH_DOMAIN
            or self._issuer_token is not _CASE_SOURCE_ARTIFACT_TOKEN
        ):
            raise CaseAttentionOwnerError("CASE_SOURCE_BINDING_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "admission_proof": _hash_json(self.admission_proof.hash_binding()),
            "batch_identity": _hash_json(self.batch_identity),
            "binding_id": self.binding_id.value,
            "case_id": self.case_id.value,
            "order_id": self.order_id.to_json_value(),
            "schema_version": self.schema_version,
            "source_batch_id": self.source_batch_id.to_json_value(),
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "OwnedCaseSourceBinding(<closed>)"


class CaseOwnerEventKind(ImmutableStrEnum):
    CASE_CREATED = "CASE_CREATED"
    SOURCE_PRESENT = "SOURCE_PRESENT"


@dataclass(frozen=True, slots=True, init=False, repr=False)
class CaseOwnerEvent:
    event_id: EvidenceId
    case_id: EvidenceId
    order_id: DoiOrderId
    event_kind: CaseOwnerEventKind
    transition: TransitionRef
    source_binding: OwnedCaseSourceBinding
    case_projection: DOIOrderCase
    snapshot_binding: HashBinding | None
    evaluation_binding: HashBinding | None
    sequence: int
    predecessor_binding: HashBinding | None
    occurred_at: CanonicalTimestamp
    schema_version: str
    _issuer_token: object = field(repr=False, compare=False)

    HASH_DOMAIN: ClassVar[str] = "doi-case-owner-event/v1"

    def __new__(cls) -> CaseOwnerEvent:
        raise CaseAttentionOwnerError("CASE_EVENT_FACTORY_REQUIRED")

    @classmethod
    def _create(
        cls,
        *,
        event_id: EvidenceId,
        event_kind: CaseOwnerEventKind,
        source_binding: OwnedCaseSourceBinding,
        case_projection: DOIOrderCase,
        snapshot_binding: HashBinding | None,
        evaluation_binding: HashBinding | None,
        sequence: int,
        predecessor_binding: HashBinding | None,
        occurred_at: CanonicalTimestamp,
        factory_capability: object,
    ) -> CaseOwnerEvent:
        if factory_capability is not _CASE_EVENT_TOKEN:
            raise CaseAttentionOwnerError("CASE_EVENT_FACTORY_REQUIRED")
        transition_id = (
            "TR-007"
            if event_kind is CaseOwnerEventKind.CASE_CREATED
            else "TR-008"
        )
        instance = object.__new__(cls)
        for name, value in (
            ("event_id", event_id),
            ("case_id", case_projection.case_id),
            ("order_id", case_projection.order_id),
            ("event_kind", event_kind),
            ("transition", load_doi_registries().transition_ref(transition_id)),
            ("source_binding", source_binding),
            ("case_projection", case_projection),
            ("snapshot_binding", snapshot_binding),
            ("evaluation_binding", evaluation_binding),
            ("sequence", sequence),
            ("predecessor_binding", predecessor_binding),
            ("occurred_at", occurred_at),
            ("schema_version", cls.HASH_DOMAIN),
            ("_issuer_token", _CASE_EVENT_TOKEN),
        ):
            object.__setattr__(instance, name, value)
        instance.__post_init__()
        return instance

    def __post_init__(self) -> None:
        created = self.event_kind is CaseOwnerEventKind.CASE_CREATED
        if (
            type(self.event_id) is not EvidenceId
            or type(self.case_id) is not EvidenceId
            or type(self.order_id) is not DoiOrderId
            or type(self.event_kind) is not CaseOwnerEventKind
            or type(self.transition) is not TransitionRef
            or type(self.source_binding) is not OwnedCaseSourceBinding
            or type(self.case_projection) is not DOIOrderCase
            or self.case_projection.case_id != self.case_id
            or self.case_projection.order_id != self.order_id
            or self.source_binding.case_id != self.case_id
            or self.source_binding.order_id != self.order_id
            or type(self.sequence) is not int
            or self.sequence < 1
            or type(self.occurred_at) is not CanonicalTimestamp
            or self.schema_version != self.HASH_DOMAIN
            or self._issuer_token is not _CASE_EVENT_TOKEN
            or (self.sequence == 1) != (self.predecessor_binding is None)
            or (
                self.predecessor_binding is not None
                and (
                    type(self.predecessor_binding) is not HashBinding
                    or self.predecessor_binding.domain != self.HASH_DOMAIN
                )
            )
        ):
            raise CaseAttentionOwnerError("CASE_EVENT_INVALID")
        if created:
            if (
                self.transition.transition_id != "TR-007"
                or self.sequence != 1
                or self.snapshot_binding is not None
                or self.evaluation_binding is not None
                or self.case_projection.current_snapshot_id is not None
                or self.case_projection.current_evaluation_id is not None
            ):
                raise CaseAttentionOwnerError("CASE_CREATED_PARTITION_INVALID")
        elif (
            self.transition.transition_id != "TR-008"
            or type(self.snapshot_binding) is not HashBinding
            or type(self.evaluation_binding) is not HashBinding
            or self.case_projection.current_snapshot_id is None
            or self.case_projection.current_evaluation_id is None
        ):
            raise CaseAttentionOwnerError("CASE_REFRESH_PARTITION_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id.value,
            "case_projection": _case_json(self.case_projection),
            "evaluation_binding": _hash_json(self.evaluation_binding),
            "event_id": self.event_id.value,
            "event_kind": self.event_kind.value,
            "occurred_at": self.occurred_at.value,
            "order_id": self.order_id.to_json_value(),
            "predecessor_binding": _hash_json(self.predecessor_binding),
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "snapshot_binding": _hash_json(self.snapshot_binding),
            "source_binding": _hash_json(self.source_binding.hash_binding()),
            "transition_id": self.transition.transition_id,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "CaseOwnerEvent(<closed>)"


@dataclass(frozen=True, slots=True)
class CaseOwnerHistory:
    case_id: EvidenceId
    order_id: DoiOrderId
    projection: DOIOrderCase | None = None
    source_binding: OwnedCaseSourceBinding | None = None
    events: tuple[CaseOwnerEvent, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.case_id) is not EvidenceId
            or type(self.order_id) is not DoiOrderId
            or type(self.events) is not tuple
            or any(type(event) is not CaseOwnerEvent for event in self.events)
            or any(
                event.case_id != self.case_id or event.order_id != self.order_id
                for event in self.events
            )
        ):
            raise CaseAttentionOwnerError("CASE_HISTORY_INVALID")
        if not self.events:
            if self.projection is not None or self.source_binding is not None:
                raise CaseAttentionOwnerError("CASE_HISTORY_INVALID")
        elif (
            type(self.projection) is not DOIOrderCase
            or type(self.source_binding) is not OwnedCaseSourceBinding
            or self.projection != self.events[-1].case_projection
            or self.source_binding != self.events[-1].source_binding
        ):
            raise CaseAttentionOwnerError("CASE_HISTORY_INVALID")


@dataclass(frozen=True, slots=True)
class CaseOwnerResult:
    history: CaseOwnerHistory
    event: CaseOwnerEvent
    replayed: bool


def _reduce_case_owner(
    history: CaseOwnerHistory,
    event: CaseOwnerEvent,
) -> CaseOwnerResult:
    if (
        type(history) is not CaseOwnerHistory
        or type(event) is not CaseOwnerEvent
        or event._issuer_token is not _CASE_EVENT_TOKEN
        or event.case_id != history.case_id
        or event.order_id != history.order_id
    ):
        raise CaseAttentionOwnerError("CASE_REDUCER_INPUT_INVALID")
    prior = next((item for item in history.events if item.event_id == event.event_id), None)
    if prior is not None:
        if prior.canonical_bytes() != event.canonical_bytes():
            raise CaseAttentionOwnerError("CASE_EVENT_REPLAY_CONFLICT")
        return CaseOwnerResult(history, prior, True)
    expected_sequence = len(history.events) + 1
    expected_predecessor = (
        None if not history.events else history.events[-1].hash_binding()
    )
    if (
        event.sequence != expected_sequence
        or event.predecessor_binding != expected_predecessor
    ):
        raise CaseAttentionOwnerError("CASE_EVENT_PREDECESSOR_CONFLICT")
    if not history.events:
        if event.event_kind is not CaseOwnerEventKind.CASE_CREATED:
            raise CaseAttentionOwnerError("CASE_CREATE_REQUIRED")
    elif (
        event.event_kind is not CaseOwnerEventKind.SOURCE_PRESENT
        or history.projection is None
        or history.projection.lifecycle_state is not CaseLifecycleState.ACTIVE
    ):
        raise CaseAttentionOwnerError("CASE_REFRESH_STATE_INVALID")
    updated = CaseOwnerHistory(
        case_id=history.case_id,
        order_id=history.order_id,
        projection=event.case_projection,
        source_binding=event.source_binding,
        events=(*history.events, event),
    )
    return CaseOwnerResult(updated, event, False)


def _replay_case_history(history: CaseOwnerHistory) -> CaseOwnerHistory:
    rebuilt = CaseOwnerHistory(history.case_id, history.order_id)
    for event in history.events:
        result = _reduce_case_owner(rebuilt, event)
        if result.replayed:
            raise CaseAttentionOwnerError("CASE_HISTORY_REPLAY_INVALID")
        rebuilt = result.history
    if rebuilt != history:
        raise CaseAttentionOwnerError("CASE_HISTORY_REPLAY_INVALID")
    return rebuilt


def _source_artifacts(
    *,
    case_id: EvidenceId,
    binding_id: EvidenceId,
    proof_id: EvidenceId,
    source_result: SourceImportResult,
    staged_order: DOIStagedOrder,
    work_item: DOIRunWorkItem,
    admitted_at: CanonicalTimestamp,
) -> OwnedCaseSourceBinding:
    if (
        type(source_result) is not SourceImportResult
        or source_result.kind is not SourceImportResultKind.SUCCEEDED
        or type(source_result.batch) is not DOISourceBatch
        or type(staged_order) is not DOIStagedOrder
        or type(work_item) is not DOIRunWorkItem
        or work_item.origin is not RunWorkOrigin.SOURCE_IMPORT
        or work_item.source_batch_id != source_result.batch.batch_id
        or work_item.order_id != staged_order.order_id
        or type(admitted_at) is not CanonicalTimestamp
    ):
        raise CaseAttentionOwnerError("CASE_SOURCE_ADMISSION_INVALID")
    retained = tuple(
        item
        for item in source_result.batch.staged_orders
        if item.order_id == staged_order.order_id
    )
    if (
        len(retained) != 1
        or not _same_record(retained[0], staged_order)
        or source_result.counts != source_result.batch.counts
    ):
        raise CaseAttentionOwnerError("CASE_STAGED_ORDER_NOT_IN_BATCH")
    order_id = DoiOrderId(staged_order.order_id)
    proof = DOICaseSourceAdmissionProofV1._create(
        proof_id=proof_id,
        case_id=case_id,
        order_id=order_id,
        source_batch_id=source_result.batch.batch_id,
        case_source_binding_id=binding_id,
        admitted_at=admitted_at,
        content_binding=source_result.batch.identity,
        factory_capability=_CASE_SOURCE_ARTIFACT_TOKEN,
    )
    return OwnedCaseSourceBinding._create(
        admission_proof=proof,
        factory_capability=_CASE_SOURCE_ARTIFACT_TOKEN,
    )


def _accepted_evaluation(
    evaluation_input: DOIEvaluationInput,
    evaluation: DOIEvaluation,
) -> None:
    if (
        type(evaluation_input) is not DOIEvaluationInput
        or type(evaluation) is not DOIEvaluation
    ):
        raise CaseAttentionOwnerError("ACCEPTED_EVALUATION_REQUIRED")
    try:
        replayed = evaluate_doi(evaluation_input)
    except (DOIModelError, ValueError, TypeError):
        raise CaseAttentionOwnerError("ACCEPTED_EVALUATION_REQUIRED") from None
    if replayed.canonical_bytes() != evaluation.canonical_bytes():
        raise CaseAttentionOwnerError("ACCEPTED_EVALUATION_MISMATCH")


@dataclass(frozen=True, slots=True, init=False, repr=False)
class CaseOwnerDecision:
    transition: TransitionRef
    stream_id: EvidenceId
    occurrence_id: EvidenceId
    occurred_at: CanonicalTimestamp
    owner_binding: HashBinding
    prior_history: CaseOwnerHistory = field(repr=False)
    result: CaseOwnerResult = field(repr=False)
    _inputs: tuple[object, ...] = field(repr=False)
    _issuer_token: object = field(repr=False, compare=False)
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-case-owner-decision/v1"

    def __new__(cls) -> CaseOwnerDecision:
        raise CaseAttentionOwnerError("CASE_OWNER_DECISION_FACTORY_REQUIRED")

    @classmethod
    def _issue(
        cls,
        *,
        prior_history: CaseOwnerHistory,
        result: CaseOwnerResult,
        inputs: tuple[object, ...],
        factory_capability: object,
    ) -> CaseOwnerDecision:
        if factory_capability is not _CASE_DECISION_TOKEN or result.replayed:
            raise CaseAttentionOwnerError("CASE_OWNER_DECISION_FACTORY_REQUIRED")
        event = result.event
        instance = object.__new__(cls)
        for name, value in (
            ("transition", event.transition),
            ("stream_id", event.case_id),
            ("occurrence_id", event.event_id),
            ("occurred_at", event.occurred_at),
            ("owner_binding", event.hash_binding()),
            ("prior_history", prior_history),
            ("result", result),
            ("_inputs", inputs),
            ("_issuer_token", _CASE_DECISION_TOKEN),
            ("schema_version", cls.HASH_DOMAIN),
        ):
            object.__setattr__(instance, name, value)
        return instance

    @property
    def transition_id(self) -> str:
        return self.transition.transition_id

    @property
    def evidence_binding(self) -> HashBinding:
        return self.owner_binding

    def to_dict(self) -> dict[str, object]:
        return {
            "occurred_at": self.occurred_at.value,
            "occurrence_id": self.occurrence_id.value,
            "owner_binding": _hash_json(self.owner_binding),
            "prior_head": (
                None
                if not self.prior_history.events
                else _hash_json(self.prior_history.events[-1].hash_binding())
            ),
            "result_head": _hash_json(self.result.event.hash_binding()),
            "schema_version": self.schema_version,
            "stream_id": self.stream_id.value,
            "transition_id": self.transition_id,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "CaseOwnerDecision(<sealed>)"


def issue_case_creation_decision(
    *,
    history: CaseOwnerHistory,
    event_id: EvidenceId,
    binding_id: EvidenceId,
    admission_proof_id: EvidenceId,
    source_result: SourceImportResult,
    staged_order: DOIStagedOrder,
    work_item: DOIRunWorkItem,
    admitted_at: CanonicalTimestamp,
) -> CaseOwnerDecision:
    """Issue TR-007 only from an empty owner stream and an exact staged batch row."""

    if type(history) is not CaseOwnerHistory or history.events:
        raise CaseAttentionOwnerError("CASE_ALREADY_RETAINED")
    if history.order_id != DoiOrderId(staged_order.order_id):
        raise CaseAttentionOwnerError("CASE_ORDER_SCOPE_INVALID")
    source_binding = _source_artifacts(
        case_id=history.case_id,
        binding_id=binding_id,
        proof_id=admission_proof_id,
        source_result=source_result,
        staged_order=staged_order,
        work_item=work_item,
        admitted_at=admitted_at,
    )
    case = DOIOrderCase(
        case_id=history.case_id,
        order_id=history.order_id,
        lifecycle_state=CaseLifecycleState.ACTIVE,
        current_snapshot_id=None,
        current_evaluation_id=None,
        terminal_closure_reason=None,
    )
    event = CaseOwnerEvent._create(
        event_id=event_id,
        event_kind=CaseOwnerEventKind.CASE_CREATED,
        source_binding=source_binding,
        case_projection=case,
        snapshot_binding=None,
        evaluation_binding=None,
        sequence=1,
        predecessor_binding=None,
        occurred_at=admitted_at,
        factory_capability=_CASE_EVENT_TOKEN,
    )
    result = _reduce_case_owner(history, event)
    return CaseOwnerDecision._issue(
        prior_history=history,
        result=result,
        inputs=(source_result, staged_order, work_item),
        factory_capability=_CASE_DECISION_TOKEN,
    )


def issue_case_refresh_decision(
    *,
    history: CaseOwnerHistory,
    event_id: EvidenceId,
    work_item: DOIRunWorkItem,
    extraction_result: DOIExtractionResult,
    evaluation_input: DOIEvaluationInput,
    evaluation: DOIEvaluation,
    source_result: SourceImportResult | None = None,
    staged_order: DOIStagedOrder | None = None,
    binding_id: EvidenceId | None = None,
    admission_proof_id: EvidenceId | None = None,
    admitted_at: CanonicalTimestamp | None = None,
) -> CaseOwnerDecision:
    """Issue TR-008 from an active case and a replayed complete later evaluation."""

    _replay_case_history(history)
    current = history.projection
    if (
        type(current) is not DOIOrderCase
        or current.lifecycle_state is not CaseLifecycleState.ACTIVE
        or type(history.source_binding) is not OwnedCaseSourceBinding
        or type(work_item) is not DOIRunWorkItem
        or work_item.order_id != history.order_id.value
        or type(extraction_result) is not DOIExtractionResult
        or extraction_result.attempt.status is not ExtractionStatus.SUCCEEDED
        or extraction_result.snapshot is None
        or extraction_result.attention_conditions
    ):
        raise CaseAttentionOwnerError("CASE_REFRESH_OWNER_INPUT_INVALID")
    snapshot = extraction_result.snapshot
    if (
        snapshot.order_id != history.order_id
        or snapshot.hash_binding() != evaluation_input.snapshot.hash_binding()
        or extraction_result.attempt.snapshot_id != snapshot.snapshot_id
        or extraction_result.attempt.order_id != snapshot.order_id
        or extraction_result.attempt.run_id != snapshot.run_id
        or work_item.run_id != snapshot.run_id.value
    ):
        raise CaseAttentionOwnerError("CASE_REFRESH_SNAPSHOT_SCOPE_INVALID")
    _accepted_evaluation(evaluation_input, evaluation)
    if (
        evaluation.order_id != history.order_id
        or evaluation.snapshot_id != snapshot.snapshot_id
        or evaluation.run_id != snapshot.run_id
        or evaluation.input_binding != evaluation_input.hash_binding()
    ):
        raise CaseAttentionOwnerError("CASE_REFRESH_EVALUATION_SCOPE_INVALID")
    create_new_binding = any(
        item is not None
        for item in (
            source_result,
            staged_order,
            binding_id,
            admission_proof_id,
            admitted_at,
        )
    )
    if create_new_binding:
        if any(
            item is None
            for item in (
                source_result,
                staged_order,
                binding_id,
                admission_proof_id,
                admitted_at,
            )
        ):
            raise CaseAttentionOwnerError("CASE_REFRESH_ADMISSION_PARTITION_INVALID")
        source_binding = _source_artifacts(
            case_id=history.case_id,
            binding_id=cast(EvidenceId, binding_id),
            proof_id=cast(EvidenceId, admission_proof_id),
            source_result=cast(SourceImportResult, source_result),
            staged_order=cast(DOIStagedOrder, staged_order),
            work_item=work_item,
            admitted_at=cast(CanonicalTimestamp, admitted_at),
        )
        if (
            _instant(cast(CanonicalTimestamp, admitted_at))
            < _instant(history.events[-1].occurred_at)
            or _instant(cast(CanonicalTimestamp, admitted_at))
            > _instant(evaluation_input.evaluated_at)
        ):
            raise CaseAttentionOwnerError("CASE_REFRESH_ADMISSION_TIME_INVALID")
    else:
        if (
            work_item.origin is not RunWorkOrigin.ORDER_RECHECK
            or work_item.source_batch_id is not None
        ):
            raise CaseAttentionOwnerError("CASE_REFRESH_REUSE_ADMISSION_INVALID")
        source_binding = history.source_binding
    if _instant(evaluation_input.evaluated_at) < _instant(history.events[-1].occurred_at):
        raise CaseAttentionOwnerError("CASE_REFRESH_TIME_INVALID")
    case = DOIOrderCase(
        case_id=history.case_id,
        order_id=history.order_id,
        lifecycle_state=CaseLifecycleState.ACTIVE,
        current_snapshot_id=snapshot.snapshot_id,
        current_evaluation_id=evaluation.evaluation_id,
        terminal_closure_reason=None,
    )
    event = CaseOwnerEvent._create(
        event_id=event_id,
        event_kind=CaseOwnerEventKind.SOURCE_PRESENT,
        source_binding=source_binding,
        case_projection=case,
        snapshot_binding=snapshot.hash_binding(),
        evaluation_binding=evaluation.hash_binding(),
        sequence=len(history.events) + 1,
        predecessor_binding=history.events[-1].hash_binding(),
        occurred_at=evaluation_input.evaluated_at,
        factory_capability=_CASE_EVENT_TOKEN,
    )
    result = _reduce_case_owner(history, event)
    inputs: tuple[object, ...] = (
        work_item,
        extraction_result,
        evaluation_input,
        evaluation,
        source_result,
        staged_order,
    )
    return CaseOwnerDecision._issue(
        prior_history=history,
        result=result,
        inputs=inputs,
        factory_capability=_CASE_DECISION_TOKEN,
    )


def _validate_case_owner_decision(decision: CaseOwnerDecision) -> CaseOwnerDecision:
    """Rebuild the owner history and recompute every retained typed binding."""

    if (
        type(decision) is not CaseOwnerDecision
        or decision._issuer_token is not _CASE_DECISION_TOKEN
        or decision.schema_version != CaseOwnerDecision.HASH_DOMAIN
        or decision.transition_id not in case_owner_transition_ids()
        or decision.stream_id != decision.result.event.case_id
        or decision.occurrence_id != decision.result.event.event_id
        or decision.occurred_at != decision.result.event.occurred_at
        or decision.owner_binding != decision.result.event.hash_binding()
    ):
        raise CaseAttentionOwnerError("CASE_OWNER_DECISION_INVALID")
    _replay_case_history(decision.prior_history)
    replayed_result = _reduce_case_owner(decision.prior_history, decision.result.event)
    if replayed_result != decision.result or replayed_result.replayed:
        raise CaseAttentionOwnerError("CASE_OWNER_DECISION_RESULT_INVALID")
    event = decision.result.event
    if decision.transition_id == "TR-007":
        source_result, staged_order, work_item = decision._inputs
        recomputed = _source_artifacts(
            case_id=event.case_id,
            binding_id=event.source_binding.binding_id,
            proof_id=event.source_binding.admission_proof.proof_id,
            source_result=cast(SourceImportResult, source_result),
            staged_order=cast(DOIStagedOrder, staged_order),
            work_item=cast(DOIRunWorkItem, work_item),
            admitted_at=event.occurred_at,
        )
        if recomputed.hash_binding() != event.source_binding.hash_binding():
            raise CaseAttentionOwnerError("CASE_OWNER_DECISION_EVIDENCE_INVALID")
    else:
        (
            work_item,
            extraction_result,
            evaluation_input,
            evaluation,
            source_result,
            staged_order,
        ) = decision._inputs
        extraction = cast(DOIExtractionResult, extraction_result)
        request = cast(DOIEvaluationInput, evaluation_input)
        accepted = cast(DOIEvaluation, evaluation)
        _accepted_evaluation(request, accepted)
        if (
            extraction.snapshot is None
            or extraction.snapshot.hash_binding() != event.snapshot_binding
            or accepted.hash_binding() != event.evaluation_binding
            or cast(DOIRunWorkItem, work_item).order_id != event.order_id.value
        ):
            raise CaseAttentionOwnerError("CASE_OWNER_DECISION_EVIDENCE_INVALID")
        if source_result is not None:
            recomputed = _source_artifacts(
                case_id=event.case_id,
                binding_id=event.source_binding.binding_id,
                proof_id=event.source_binding.admission_proof.proof_id,
                source_result=cast(SourceImportResult, source_result),
                staged_order=cast(DOIStagedOrder, staged_order),
                work_item=cast(DOIRunWorkItem, work_item),
                admitted_at=event.source_binding.admission_proof.admitted_at,
            )
            if recomputed.hash_binding() != event.source_binding.hash_binding():
                raise CaseAttentionOwnerError("CASE_OWNER_DECISION_EVIDENCE_INVALID")
        elif event.source_binding != decision.prior_history.source_binding:
            raise CaseAttentionOwnerError("CASE_OWNER_DECISION_EVIDENCE_INVALID")
    return decision


def validate_case_owner_decision(decision: CaseOwnerDecision) -> CaseOwnerDecision:
    """Fail closed for malformed objects before replaying a sealed decision."""

    try:
        return _validate_case_owner_decision(decision)
    except CaseAttentionOwnerError:
        raise
    except (AttributeError, TypeError):
        raise CaseAttentionOwnerError("CASE_OWNER_DECISION_INVALID") from None


def case_owner_transition_ids() -> tuple[str, ...]:
    return ("TR-007", "TR-008")


_ATTENTION_EVENT_TOKEN = object()
_ATTENTION_DECISION_TOKEN = object()


class AttentionOwnerAction(ImmutableStrEnum):
    SET = "SET"
    CLEAR = "CLEAR"
    REPLACE = "REPLACE"


@dataclass(frozen=True, slots=True)
class ActiveAttentionCause:
    condition: AttentionCondition
    cause_key: HashBinding
    cause_evidence_binding: HashBinding
    cause_subject: tuple[str, ...]
    set_event_id: EvidenceId
    set_event_binding: HashBinding
    set_at: CanonicalTimestamp

    def __post_init__(self) -> None:
        if (
            type(self.condition) is not AttentionCondition
            or type(self.cause_key) is not HashBinding
            or self.cause_key.domain != "doi-attention-cause-key/v2"
            or type(self.cause_evidence_binding) is not HashBinding
            or type(self.cause_subject) is not tuple
            or not self.cause_subject
            or any(type(item) is not str or not item for item in self.cause_subject)
            or type(self.set_event_id) is not EvidenceId
            or type(self.set_event_binding) is not HashBinding
            or self.set_event_binding.domain != AttentionOwnerEvent.HASH_DOMAIN
            or type(self.set_at) is not CanonicalTimestamp
        ):
            raise CaseAttentionOwnerError("ACTIVE_ATTENTION_CAUSE_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "cause_evidence_binding": _hash_json(self.cause_evidence_binding),
            "cause_key": _hash_json(self.cause_key),
            "cause_subject": list(self.cause_subject),
            "condition": self.condition.value,
            "set_at": self.set_at.value,
            "set_event_binding": _hash_json(self.set_event_binding),
            "set_event_id": self.set_event_id.value,
        }


@dataclass(frozen=True, slots=True, init=False, repr=False)
class AttentionOwnerEvent:
    event_id: EvidenceId
    case_id: EvidenceId
    order_id: DoiOrderId
    action: AttentionOwnerAction
    condition: AttentionCondition
    cause_key: HashBinding
    cause_evidence_binding: HashBinding
    cause_subject: tuple[str, ...]
    active_set_event_id: EvidenceId | None
    active_set_event_binding: HashBinding | None
    resolver_binding: HashBinding | None
    resulting_projection_binding: HashBinding | None
    replacement_condition: AttentionCondition | None
    replacement_cause_key: HashBinding | None
    replacement_evidence_binding: HashBinding | None
    replacement_subject: tuple[str, ...] | None
    transition: TransitionRef
    sequence: int
    predecessor_binding: HashBinding | None
    occurred_at: CanonicalTimestamp
    schema_version: str
    _issuer_token: object = field(repr=False, compare=False)

    HASH_DOMAIN: ClassVar[str] = "doi-attention-event/v2"
    CAUSE_KEY_DOMAIN: ClassVar[str] = "doi-attention-cause-key/v2"

    def __new__(cls) -> AttentionOwnerEvent:
        raise CaseAttentionOwnerError("ATTENTION_EVENT_FACTORY_REQUIRED")

    @classmethod
    def _create(
        cls,
        *,
        event_id: EvidenceId,
        case_id: EvidenceId,
        order_id: DoiOrderId,
        action: AttentionOwnerAction,
        condition: AttentionCondition,
        cause_key: HashBinding,
        cause_evidence_binding: HashBinding,
        cause_subject: tuple[str, ...],
        active_set_event_id: EvidenceId | None,
        active_set_event_binding: HashBinding | None,
        resolver_binding: HashBinding | None,
        resulting_projection_binding: HashBinding | None,
        replacement_condition: AttentionCondition | None,
        replacement_cause_key: HashBinding | None,
        replacement_evidence_binding: HashBinding | None,
        replacement_subject: tuple[str, ...] | None,
        transition_id: str,
        sequence: int,
        predecessor_binding: HashBinding | None,
        occurred_at: CanonicalTimestamp,
        factory_capability: object,
    ) -> AttentionOwnerEvent:
        if factory_capability is not _ATTENTION_EVENT_TOKEN:
            raise CaseAttentionOwnerError("ATTENTION_EVENT_FACTORY_REQUIRED")
        instance = object.__new__(cls)
        for name, value in (
            ("event_id", event_id),
            ("case_id", case_id),
            ("order_id", order_id),
            ("action", action),
            ("condition", condition),
            ("cause_key", cause_key),
            ("cause_evidence_binding", cause_evidence_binding),
            ("cause_subject", cause_subject),
            ("active_set_event_id", active_set_event_id),
            ("active_set_event_binding", active_set_event_binding),
            ("resolver_binding", resolver_binding),
            ("resulting_projection_binding", resulting_projection_binding),
            ("replacement_condition", replacement_condition),
            ("replacement_cause_key", replacement_cause_key),
            ("replacement_evidence_binding", replacement_evidence_binding),
            ("replacement_subject", replacement_subject),
            ("transition", load_doi_registries().transition_ref(transition_id)),
            ("sequence", sequence),
            ("predecessor_binding", predecessor_binding),
            ("occurred_at", occurred_at),
            ("schema_version", cls.HASH_DOMAIN),
            ("_issuer_token", _ATTENTION_EVENT_TOKEN),
        ):
            object.__setattr__(instance, name, value)
        instance.__post_init__()
        return instance

    def __post_init__(self) -> None:
        if (
            type(self.event_id) is not EvidenceId
            or type(self.case_id) is not EvidenceId
            or type(self.order_id) is not DoiOrderId
            or type(self.action) is not AttentionOwnerAction
            or type(self.condition) is not AttentionCondition
            or type(self.cause_key) is not HashBinding
            or self.cause_key.domain != self.CAUSE_KEY_DOMAIN
            or type(self.cause_evidence_binding) is not HashBinding
            or type(self.cause_subject) is not tuple
            or not self.cause_subject
            or any(type(item) is not str or not item for item in self.cause_subject)
            or type(self.transition) is not TransitionRef
            or self.transition.transition_id not in attention_owner_transition_ids()
            or type(self.sequence) is not int
            or self.sequence < 1
            or (self.sequence == 1) != (self.predecessor_binding is None)
            or (
                self.predecessor_binding is not None
                and (
                    type(self.predecessor_binding) is not HashBinding
                    or self.predecessor_binding.domain != self.HASH_DOMAIN
                )
            )
            or type(self.occurred_at) is not CanonicalTimestamp
            or self.schema_version != self.HASH_DOMAIN
            or self._issuer_token is not _ATTENTION_EVENT_TOKEN
        ):
            raise CaseAttentionOwnerError("ATTENTION_EVENT_INVALID")
        resolution = (
            self.active_set_event_id,
            self.active_set_event_binding,
            self.resolver_binding,
        )
        replacement = (
            self.replacement_condition,
            self.replacement_cause_key,
            self.replacement_evidence_binding,
            self.replacement_subject,
        )
        if self.action is AttentionOwnerAction.SET:
            if any(item is not None for item in (*resolution, *replacement)):
                raise CaseAttentionOwnerError("ATTENTION_SET_PARTITION_INVALID")
        elif self.action is AttentionOwnerAction.CLEAR:
            if (
                any(item is None for item in resolution)
                or any(item is not None for item in replacement)
            ):
                raise CaseAttentionOwnerError("ATTENTION_CLEAR_PARTITION_INVALID")
        elif (
            any(item is None for item in resolution)
            or any(item is None for item in replacement)
            or self.transition.transition_id != "TR-022"
            or self.condition
            is not AttentionCondition.SOURCE_ABSENCE_RECHECK_REQUIRED
            or self.replacement_condition is not AttentionCondition.RECHECK_REQUIRED
            or cast(HashBinding, self.replacement_cause_key).domain
            != self.CAUSE_KEY_DOMAIN
        ):
            raise CaseAttentionOwnerError("ATTENTION_REPLACE_PARTITION_INVALID")
        if self.active_set_event_binding is not None and (
            type(self.active_set_event_binding) is not HashBinding
            or self.active_set_event_binding.domain != self.HASH_DOMAIN
        ):
            raise CaseAttentionOwnerError("ATTENTION_ACTIVE_SET_BINDING_INVALID")
        if self.resulting_projection_binding is not None and (
            type(self.resulting_projection_binding) is not HashBinding
            or self.transition.transition_id != "TR-095"
        ):
            raise CaseAttentionOwnerError("ATTENTION_RESULT_PROJECTION_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action.value,
            "active_set_event_binding": _hash_json(self.active_set_event_binding),
            "active_set_event_id": (
                None
                if self.active_set_event_id is None
                else self.active_set_event_id.value
            ),
            "case_id": self.case_id.value,
            "cause_evidence_binding": _hash_json(self.cause_evidence_binding),
            "cause_key": _hash_json(self.cause_key),
            "cause_subject": list(self.cause_subject),
            "condition": self.condition.value,
            "event_id": self.event_id.value,
            "occurred_at": self.occurred_at.value,
            "order_id": self.order_id.to_json_value(),
            "predecessor_binding": _hash_json(self.predecessor_binding),
            "replacement_cause_key": _hash_json(self.replacement_cause_key),
            "replacement_condition": (
                None
                if self.replacement_condition is None
                else self.replacement_condition.value
            ),
            "replacement_evidence_binding": _hash_json(
                self.replacement_evidence_binding
            ),
            "replacement_subject": (
                None
                if self.replacement_subject is None
                else list(self.replacement_subject)
            ),
            "resolver_binding": _hash_json(self.resolver_binding),
            "resulting_projection_binding": _hash_json(
                self.resulting_projection_binding
            ),
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "transition_id": self.transition.transition_id,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "AttentionOwnerEvent(<closed>)"


@dataclass(frozen=True, slots=True)
class AttentionOwnerHistory:
    case_id: EvidenceId
    order_id: DoiOrderId
    active: tuple[ActiveAttentionCause, ...] = ()
    events: tuple[AttentionOwnerEvent, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.case_id) is not EvidenceId
            or type(self.order_id) is not DoiOrderId
            or type(self.active) is not tuple
            or any(type(item) is not ActiveAttentionCause for item in self.active)
            or type(self.events) is not tuple
            or any(type(item) is not AttentionOwnerEvent for item in self.events)
            or any(
                item.case_id != self.case_id or item.order_id != self.order_id
                for item in self.events
            )
        ):
            raise CaseAttentionOwnerError("ATTENTION_HISTORY_INVALID")
        keys = tuple(
            (item.condition.value, item.cause_key.sha256) for item in self.active
        )
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise CaseAttentionOwnerError("ATTENTION_ACTIVE_SET_INVALID")


@dataclass(frozen=True, slots=True)
class AttentionOwnerResult:
    history: AttentionOwnerHistory
    event: AttentionOwnerEvent
    replayed: bool


def _active_from_event(
    event: AttentionOwnerEvent,
    *,
    replacement: bool = False,
) -> ActiveAttentionCause:
    if replacement:
        condition = cast(AttentionCondition, event.replacement_condition)
        cause_key = cast(HashBinding, event.replacement_cause_key)
        evidence = cast(HashBinding, event.replacement_evidence_binding)
        subject = cast(tuple[str, ...], event.replacement_subject)
    else:
        condition = event.condition
        cause_key = event.cause_key
        evidence = event.cause_evidence_binding
        subject = event.cause_subject
    return ActiveAttentionCause(
        condition=condition,
        cause_key=cause_key,
        cause_evidence_binding=evidence,
        cause_subject=subject,
        set_event_id=event.event_id,
        set_event_binding=event.hash_binding(),
        set_at=event.occurred_at,
    )


def _reduce_attention_owner(
    history: AttentionOwnerHistory,
    event: AttentionOwnerEvent,
) -> AttentionOwnerResult:
    if (
        type(history) is not AttentionOwnerHistory
        or type(event) is not AttentionOwnerEvent
        or event._issuer_token is not _ATTENTION_EVENT_TOKEN
        or event.case_id != history.case_id
        or event.order_id != history.order_id
    ):
        raise CaseAttentionOwnerError("ATTENTION_REDUCER_INPUT_INVALID")
    prior_event = next(
        (item for item in history.events if item.event_id == event.event_id),
        None,
    )
    if prior_event is not None:
        if prior_event.canonical_bytes() != event.canonical_bytes():
            raise CaseAttentionOwnerError("ATTENTION_EVENT_REPLAY_CONFLICT")
        return AttentionOwnerResult(history, prior_event, True)
    expected_sequence = len(history.events) + 1
    expected_predecessor = (
        None if not history.events else history.events[-1].hash_binding()
    )
    if (
        event.sequence != expected_sequence
        or event.predecessor_binding != expected_predecessor
        or (
            history.events
            and _instant(event.occurred_at) < _instant(history.events[-1].occurred_at)
        )
    ):
        raise CaseAttentionOwnerError("ATTENTION_EVENT_PREDECESSOR_CONFLICT")
    active = {(item.condition, item.cause_key.sha256): item for item in history.active}
    key = (event.condition, event.cause_key.sha256)
    if event.action is AttentionOwnerAction.SET:
        if key in active:
            raise CaseAttentionOwnerError("ATTENTION_CAUSE_ALREADY_ACTIVE")
        active[key] = _active_from_event(event)
    else:
        retained = active.get(key)
        if (
            retained is None
            or retained.set_event_id != event.active_set_event_id
            or retained.set_event_binding != event.active_set_event_binding
            or retained.cause_evidence_binding != event.cause_evidence_binding
            or retained.cause_subject != event.cause_subject
            or _instant(event.occurred_at) < _instant(retained.set_at)
        ):
            raise CaseAttentionOwnerError("ATTENTION_CLEAR_SET_CONFLICT")
        del active[key]
        if event.action is AttentionOwnerAction.REPLACE:
            replacement_key = (
                cast(AttentionCondition, event.replacement_condition),
                cast(HashBinding, event.replacement_cause_key).sha256,
            )
            if replacement_key in active:
                raise CaseAttentionOwnerError("ATTENTION_CAUSE_ALREADY_ACTIVE")
            active[replacement_key] = _active_from_event(event, replacement=True)
    updated = AttentionOwnerHistory(
        case_id=history.case_id,
        order_id=history.order_id,
        active=tuple(
            sorted(
                active.values(),
                key=lambda item: (item.condition.value, item.cause_key.sha256),
            )
        ),
        events=(*history.events, event),
    )
    return AttentionOwnerResult(updated, event, False)


def _replay_attention_history(history: AttentionOwnerHistory) -> AttentionOwnerHistory:
    if type(history) is not AttentionOwnerHistory:
        raise CaseAttentionOwnerError("ATTENTION_HISTORY_INVALID")
    rebuilt = AttentionOwnerHistory(history.case_id, history.order_id)
    for event in history.events:
        result = _reduce_attention_owner(rebuilt, event)
        if result.replayed:
            raise CaseAttentionOwnerError("ATTENTION_HISTORY_REPLAY_INVALID")
        rebuilt = result.history
    if rebuilt != history:
        raise CaseAttentionOwnerError("ATTENTION_HISTORY_REPLAY_INVALID")
    return rebuilt


def _cause_key(
    *,
    case_id: EvidenceId,
    order_id: DoiOrderId,
    condition: AttentionCondition,
    evidence: HashBinding,
    subject: tuple[str, ...],
) -> HashBinding:
    value = {
        "case_id": case_id.value,
        "cause_evidence": _hash_json(evidence),
        "cause_subject": list(subject),
        "condition": condition.value,
        "order_id": order_id.to_json_value(),
        "schema_version": AttentionOwnerEvent.CAUSE_KEY_DOMAIN,
    }
    return domain_hash(
        AttentionOwnerEvent.CAUSE_KEY_DOMAIN,
        canonical_json_bytes(value, expected_members=set(value)),
    )


def _require_active_case(
    history: AttentionOwnerHistory,
    case: DOIOrderCase,
) -> None:
    _replay_attention_history(history)
    if (
        type(case) is not DOIOrderCase
        or case.lifecycle_state is not CaseLifecycleState.ACTIVE
        or case.case_id != history.case_id
        or case.order_id != history.order_id
    ):
        raise CaseAttentionOwnerError("ATTENTION_CASE_SCOPE_INVALID")


def _find_active_set(
    history: AttentionOwnerHistory,
    *,
    condition: AttentionCondition,
    active_set_event_id: EvidenceId,
) -> ActiveAttentionCause:
    matches = tuple(
        item
        for item in history.active
        if item.condition is condition and item.set_event_id == active_set_event_id
    )
    if len(matches) != 1:
        raise CaseAttentionOwnerError("ATTENTION_ACTIVE_SET_REQUIRED")
    return matches[0]


@dataclass(frozen=True, slots=True, init=False, repr=False)
class AttentionOwnerDecision:
    transition: TransitionRef
    stream_id: EvidenceId
    occurrence_id: EvidenceId
    occurred_at: CanonicalTimestamp
    owner_binding: HashBinding
    prior_history: AttentionOwnerHistory = field(repr=False)
    result: AttentionOwnerResult = field(repr=False)
    _validator_tag: str = field(repr=False)
    _inputs: tuple[object, ...] = field(repr=False)
    _issuer_token: object = field(repr=False, compare=False)
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-attention-owner-decision/v1"

    def __new__(cls) -> AttentionOwnerDecision:
        raise CaseAttentionOwnerError("ATTENTION_DECISION_FACTORY_REQUIRED")

    @classmethod
    def _issue(
        cls,
        *,
        prior_history: AttentionOwnerHistory,
        result: AttentionOwnerResult,
        validator_tag: str,
        inputs: tuple[object, ...],
        factory_capability: object,
    ) -> AttentionOwnerDecision:
        if factory_capability is not _ATTENTION_DECISION_TOKEN or result.replayed:
            raise CaseAttentionOwnerError("ATTENTION_DECISION_FACTORY_REQUIRED")
        event = result.event
        instance = object.__new__(cls)
        for name, value in (
            ("transition", event.transition),
            ("stream_id", event.case_id),
            ("occurrence_id", event.event_id),
            ("occurred_at", event.occurred_at),
            ("owner_binding", event.hash_binding()),
            ("prior_history", prior_history),
            ("result", result),
            ("_validator_tag", validator_tag),
            ("_inputs", inputs),
            ("_issuer_token", _ATTENTION_DECISION_TOKEN),
            ("schema_version", cls.HASH_DOMAIN),
        ):
            object.__setattr__(instance, name, value)
        return instance

    @property
    def transition_id(self) -> str:
        return self.transition.transition_id

    @property
    def evidence_binding(self) -> HashBinding:
        return self.owner_binding

    def to_dict(self) -> dict[str, object]:
        return {
            "occurred_at": self.occurred_at.value,
            "occurrence_id": self.occurrence_id.value,
            "owner_binding": _hash_json(self.owner_binding),
            "prior_head": (
                None
                if not self.prior_history.events
                else _hash_json(self.prior_history.events[-1].hash_binding())
            ),
            "result_head": _hash_json(self.result.event.hash_binding()),
            "schema_version": self.schema_version,
            "stream_id": self.stream_id.value,
            "transition_id": self.transition_id,
            "validator_tag": self._validator_tag,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "AttentionOwnerDecision(<sealed>)"


def _set_attention(
    *,
    history: AttentionOwnerHistory,
    case: DOIOrderCase,
    event_id: EvidenceId,
    condition: AttentionCondition,
    evidence: HashBinding,
    subject: tuple[str, ...],
    transition_id: str,
    occurred_at: CanonicalTimestamp,
    validator_tag: str,
    inputs: tuple[object, ...],
) -> AttentionOwnerDecision:
    _require_active_case(history, case)
    cause_key = _cause_key(
        case_id=history.case_id,
        order_id=history.order_id,
        condition=condition,
        evidence=evidence,
        subject=subject,
    )
    event = AttentionOwnerEvent._create(
        event_id=event_id,
        case_id=history.case_id,
        order_id=history.order_id,
        action=AttentionOwnerAction.SET,
        condition=condition,
        cause_key=cause_key,
        cause_evidence_binding=evidence,
        cause_subject=subject,
        active_set_event_id=None,
        active_set_event_binding=None,
        resolver_binding=None,
        resulting_projection_binding=None,
        replacement_condition=None,
        replacement_cause_key=None,
        replacement_evidence_binding=None,
        replacement_subject=None,
        transition_id=transition_id,
        sequence=len(history.events) + 1,
        predecessor_binding=(
            None if not history.events else history.events[-1].hash_binding()
        ),
        occurred_at=occurred_at,
        factory_capability=_ATTENTION_EVENT_TOKEN,
    )
    result = _reduce_attention_owner(history, event)
    return AttentionOwnerDecision._issue(
        prior_history=history,
        result=result,
        validator_tag=validator_tag,
        inputs=(case, *inputs),
        factory_capability=_ATTENTION_DECISION_TOKEN,
    )


def _clear_attention(
    *,
    history: AttentionOwnerHistory,
    case: DOIOrderCase,
    event_id: EvidenceId,
    condition: AttentionCondition,
    active_set_event_id: EvidenceId,
    resolver: HashBinding,
    resulting_projection: HashBinding | None,
    transition_id: str,
    occurred_at: CanonicalTimestamp,
    validator_tag: str,
    inputs: tuple[object, ...],
) -> AttentionOwnerDecision:
    _require_active_case(history, case)
    active = _find_active_set(
        history,
        condition=condition,
        active_set_event_id=active_set_event_id,
    )
    event = AttentionOwnerEvent._create(
        event_id=event_id,
        case_id=history.case_id,
        order_id=history.order_id,
        action=AttentionOwnerAction.CLEAR,
        condition=condition,
        cause_key=active.cause_key,
        cause_evidence_binding=active.cause_evidence_binding,
        cause_subject=active.cause_subject,
        active_set_event_id=active.set_event_id,
        active_set_event_binding=active.set_event_binding,
        resolver_binding=resolver,
        resulting_projection_binding=resulting_projection,
        replacement_condition=None,
        replacement_cause_key=None,
        replacement_evidence_binding=None,
        replacement_subject=None,
        transition_id=transition_id,
        sequence=len(history.events) + 1,
        predecessor_binding=(
            None if not history.events else history.events[-1].hash_binding()
        ),
        occurred_at=occurred_at,
        factory_capability=_ATTENTION_EVENT_TOKEN,
    )
    result = _reduce_attention_owner(history, event)
    return AttentionOwnerDecision._issue(
        prior_history=history,
        result=result,
        validator_tag=validator_tag,
        inputs=(case, active_set_event_id, *inputs),
        factory_capability=_ATTENTION_DECISION_TOKEN,
    )


def attention_owner_transition_ids() -> tuple[str, ...]:
    return (
        "TR-020",
        "TR-021",
        "TR-022",
        "TR-023",
        "TR-024",
        "TR-025",
        "TR-026",
        "TR-092",
        "TR-093",
        "TR-094",
        "TR-095",
    )


def _reason_codes(evaluation: DOIEvaluation) -> frozenset[str]:
    return frozenset(reason.code for reason in evaluation.reasons.reasons)


def _evaluation_for_case(
    *,
    case: DOIOrderCase,
    evaluation_input: DOIEvaluationInput,
    evaluation: DOIEvaluation,
    current: bool,
) -> None:
    _accepted_evaluation(evaluation_input, evaluation)
    snapshot = evaluation_input.snapshot
    if (
        evaluation.order_id != case.order_id
        or snapshot.order_id != case.order_id
        or evaluation.snapshot_id != snapshot.snapshot_id
        or evaluation.run_id != snapshot.run_id
        or evaluation.input_binding != evaluation_input.hash_binding()
        or (current and case.current_snapshot_id != snapshot.snapshot_id)
        or (current and case.current_evaluation_id != evaluation.evaluation_id)
    ):
        raise CaseAttentionOwnerError("ATTENTION_EVALUATION_SCOPE_INVALID")


def _successful_extraction_for_evaluation(
    *,
    case: DOIOrderCase,
    extraction_result: DOIExtractionResult,
    evaluation_input: DOIEvaluationInput,
    evaluation: DOIEvaluation,
) -> None:
    if (
        type(extraction_result) is not DOIExtractionResult
        or extraction_result.attempt.status is not ExtractionStatus.SUCCEEDED
        or extraction_result.snapshot is None
        or extraction_result.attention_conditions
        or extraction_result.snapshot.order_id != case.order_id
        or extraction_result.snapshot.hash_binding()
        != evaluation_input.snapshot.hash_binding()
        or extraction_result.attempt.snapshot_id
        != extraction_result.snapshot.snapshot_id
        or extraction_result.attempt.order_id != case.order_id
        or extraction_result.attempt.run_id != extraction_result.snapshot.run_id
    ):
        raise CaseAttentionOwnerError("ATTENTION_COMPLETE_EXTRACTION_REQUIRED")
    _evaluation_for_case(
        case=case,
        evaluation_input=evaluation_input,
        evaluation=evaluation,
        current=True,
    )


def set_recheck_from_failed_extraction(
    *,
    history: AttentionOwnerHistory,
    case: DOIOrderCase,
    event_id: EvidenceId,
    extraction_result: DOIExtractionResult,
) -> AttentionOwnerDecision:
    """TR-020: derive one recheck cause from the exact failed extraction result."""

    if (
        type(extraction_result) is not DOIExtractionResult
        or extraction_result.attempt.status is not ExtractionStatus.FAILED
        or extraction_result.snapshot is not None
        or extraction_result.attention_conditions
        != (AttentionCondition.RECHECK_REQUIRED,)
        or extraction_result.attempt.order_id != case.order_id
    ):
        raise CaseAttentionOwnerError("FAILED_EXTRACTION_CAUSE_REQUIRED")
    attempt = extraction_result.attempt
    return _set_attention(
        history=history,
        case=case,
        event_id=event_id,
        condition=AttentionCondition.RECHECK_REQUIRED,
        evidence=attempt.hash_binding(),
        subject=(
            "FAILED_EXTRACTION",
            attempt.attempt_id.to_json_value(),
            attempt.run_id.to_json_value(),
            attempt.order_id.to_json_value(),
        ),
        transition_id="TR-020",
        occurred_at=attempt.completed_at,
        validator_tag="FAILED_EXTRACTION_SET",
        inputs=(extraction_result,),
    )


def set_source_absence_from_evaluation(
    *,
    history: AttentionOwnerHistory,
    case: DOIOrderCase,
    event_id: EvidenceId,
    evaluation_input: DOIEvaluationInput,
    evaluation: DOIEvaluation,
) -> AttentionOwnerDecision:
    """TR-021: bind the source-absence cause to one replayed current evaluation."""

    _evaluation_for_case(
        case=case,
        evaluation_input=evaluation_input,
        evaluation=evaluation,
        current=True,
    )
    snapshot = evaluation_input.snapshot
    if (
        snapshot.source_presence is not SourcePresence.ABSENT_RECHECK_REQUIRED
        or _reason_codes(evaluation) != frozenset({"RC-010"})
    ):
        raise CaseAttentionOwnerError("SOURCE_ABSENCE_EVALUATION_REQUIRED")
    return _set_attention(
        history=history,
        case=case,
        event_id=event_id,
        condition=AttentionCondition.SOURCE_ABSENCE_RECHECK_REQUIRED,
        evidence=evaluation.hash_binding(),
        subject=(
            "SOURCE_ABSENCE",
            evaluation.evaluation_id.value,
            snapshot.snapshot_id.to_json_value(),
            snapshot.run_id.to_json_value(),
        ),
        transition_id="TR-021",
        occurred_at=evaluation_input.evaluated_at,
        validator_tag="SOURCE_ABSENCE_SET",
        inputs=(evaluation_input, evaluation),
    )


def replace_source_absence_with_failed_recheck(
    *,
    history: AttentionOwnerHistory,
    case: DOIOrderCase,
    event_id: EvidenceId,
    active_set_event_id: EvidenceId,
    extraction_result: DOIExtractionResult,
) -> AttentionOwnerDecision:
    """TR-022: atomically clear absence and set a distinct failed-recheck cause."""

    _require_active_case(history, case)
    active = _find_active_set(
        history,
        condition=AttentionCondition.SOURCE_ABSENCE_RECHECK_REQUIRED,
        active_set_event_id=active_set_event_id,
    )
    if (
        type(extraction_result) is not DOIExtractionResult
        or extraction_result.attempt.status is not ExtractionStatus.FAILED
        or extraction_result.snapshot is not None
        or extraction_result.attention_conditions
        != (AttentionCondition.RECHECK_REQUIRED,)
        or extraction_result.attempt.order_id != case.order_id
        or _instant(extraction_result.attempt.completed_at) < _instant(active.set_at)
    ):
        raise CaseAttentionOwnerError("FAILED_DISAPPEARANCE_RECHECK_REQUIRED")
    attempt = extraction_result.attempt
    replacement_subject = (
        "FAILED_DISAPPEARANCE_RECHECK",
        attempt.attempt_id.to_json_value(),
        attempt.run_id.to_json_value(),
        attempt.order_id.to_json_value(),
    )
    replacement_key = _cause_key(
        case_id=history.case_id,
        order_id=history.order_id,
        condition=AttentionCondition.RECHECK_REQUIRED,
        evidence=attempt.hash_binding(),
        subject=replacement_subject,
    )
    event = AttentionOwnerEvent._create(
        event_id=event_id,
        case_id=history.case_id,
        order_id=history.order_id,
        action=AttentionOwnerAction.REPLACE,
        condition=active.condition,
        cause_key=active.cause_key,
        cause_evidence_binding=active.cause_evidence_binding,
        cause_subject=active.cause_subject,
        active_set_event_id=active.set_event_id,
        active_set_event_binding=active.set_event_binding,
        resolver_binding=attempt.hash_binding(),
        resulting_projection_binding=None,
        replacement_condition=AttentionCondition.RECHECK_REQUIRED,
        replacement_cause_key=replacement_key,
        replacement_evidence_binding=attempt.hash_binding(),
        replacement_subject=replacement_subject,
        transition_id="TR-022",
        sequence=len(history.events) + 1,
        predecessor_binding=history.events[-1].hash_binding(),
        occurred_at=attempt.completed_at,
        factory_capability=_ATTENTION_EVENT_TOKEN,
    )
    result = _reduce_attention_owner(history, event)
    return AttentionOwnerDecision._issue(
        prior_history=history,
        result=result,
        validator_tag="SOURCE_ABSENCE_REPLACED",
        inputs=(case, active_set_event_id, extraction_result),
        factory_capability=_ATTENTION_DECISION_TOKEN,
    )


def clear_source_absence_from_complete_evaluation(
    *,
    history: AttentionOwnerHistory,
    case: DOIOrderCase,
    event_id: EvidenceId,
    active_set_event_id: EvidenceId,
    extraction_result: DOIExtractionResult,
    evaluation_input: DOIEvaluationInput,
    evaluation: DOIEvaluation,
) -> AttentionOwnerDecision:
    """TR-023: clear only the named absence cause with a present complete result."""

    _successful_extraction_for_evaluation(
        case=case,
        extraction_result=extraction_result,
        evaluation_input=evaluation_input,
        evaluation=evaluation,
    )
    if evaluation_input.snapshot.source_presence is not SourcePresence.PRESENT:
        raise CaseAttentionOwnerError("SOURCE_REAPPEARANCE_REQUIRED")
    return _clear_attention(
        history=history,
        case=case,
        event_id=event_id,
        condition=AttentionCondition.SOURCE_ABSENCE_RECHECK_REQUIRED,
        active_set_event_id=active_set_event_id,
        resolver=evaluation.hash_binding(),
        resulting_projection=None,
        transition_id="TR-023",
        occurred_at=evaluation_input.evaluated_at,
        validator_tag="SOURCE_ABSENCE_CLEAR",
        inputs=(extraction_result, evaluation_input, evaluation),
    )


def clear_recheck_from_complete_evaluation(
    *,
    history: AttentionOwnerHistory,
    case: DOIOrderCase,
    event_id: EvidenceId,
    active_set_event_id: EvidenceId,
    extraction_result: DOIExtractionResult,
    evaluation_input: DOIEvaluationInput,
    evaluation: DOIEvaluation,
) -> AttentionOwnerDecision:
    """TR-024: clear only the named recheck cause with a later complete result."""

    _successful_extraction_for_evaluation(
        case=case,
        extraction_result=extraction_result,
        evaluation_input=evaluation_input,
        evaluation=evaluation,
    )
    return _clear_attention(
        history=history,
        case=case,
        event_id=event_id,
        condition=AttentionCondition.RECHECK_REQUIRED,
        active_set_event_id=active_set_event_id,
        resolver=evaluation.hash_binding(),
        resulting_projection=None,
        transition_id="TR-024",
        occurred_at=evaluation_input.evaluated_at,
        validator_tag="RECHECK_CLEAR",
        inputs=(extraction_result, evaluation_input, evaluation),
    )


def set_intervention_verification_from_changed_evaluation(
    *,
    history: AttentionOwnerHistory,
    case: DOIOrderCase,
    event_id: EvidenceId,
    prior_evaluation_input: DOIEvaluationInput,
    prior_evaluation: DOIEvaluation,
    changed_evaluation_input: DOIEvaluationInput,
    changed_evaluation: DOIEvaluation,
) -> AttentionOwnerDecision:
    """TR-025: derive the cause from one exact changed opportunity evaluation."""

    _evaluation_for_case(
        case=case,
        evaluation_input=changed_evaluation_input,
        evaluation=changed_evaluation,
        current=True,
    )
    _accepted_evaluation(prior_evaluation_input, prior_evaluation)
    if (
        prior_evaluation.order_id != case.order_id
        or prior_evaluation.evaluation_id == changed_evaluation.evaluation_id
        or prior_evaluation.snapshot_id == changed_evaluation.snapshot_id
        or prior_evaluation.output_binding == changed_evaluation.output_binding
        or not changed_evaluation.opportunities
        or _instant(changed_evaluation_input.evaluated_at)
        < _instant(prior_evaluation_input.evaluated_at)
    ):
        raise CaseAttentionOwnerError("CHANGED_EVALUATION_REQUIRED")
    opportunity_ids = tuple(
        item.opportunity_id.value for item in changed_evaluation.opportunities
    )
    return _set_attention(
        history=history,
        case=case,
        event_id=event_id,
        condition=AttentionCondition.INTERVENTION_VERIFICATION_REQUIRED,
        evidence=changed_evaluation.hash_binding(),
        subject=(
            "CHANGED_EVALUATION",
            prior_evaluation.evaluation_id.value,
            changed_evaluation.evaluation_id.value,
            *opportunity_ids,
        ),
        transition_id="TR-025",
        occurred_at=changed_evaluation_input.evaluated_at,
        validator_tag="INTERVENTION_VERIFICATION_SET",
        inputs=(
            prior_evaluation_input,
            prior_evaluation,
            changed_evaluation_input,
            changed_evaluation,
        ),
    )


def _validated_action_resolution(
    *,
    action_event: object,
    intervention: DOIIntervention,
    completion_proof: CompletedSystemActionProof | CompletedHumanActionProof,
) -> CanonicalTimestamp:
    from synthetic_sales_assist.doi.interventions import ActionVerificationEvent

    if (
        type(action_event) is not ActionVerificationEvent
        or type(intervention) is not DOIIntervention
        or len(intervention.action_events) != 1
        or intervention.action_events[0].canonical_bytes()
        != action_event.canonical_bytes()
    ):
        raise CaseAttentionOwnerError("VERIFIED_ACTION_HISTORY_REQUIRED")
    if type(completion_proof) is CompletedSystemActionProof:
        replayed_proof = CompletedSystemActionProof.from_history(
            history=completion_proof.history
        )
        expected = ActionVerificationState.SYSTEM_VERIFIED
    elif type(completion_proof) is CompletedHumanActionProof:
        replayed_proof = CompletedHumanActionProof.from_history(
            history=completion_proof.history,
            authority=completion_proof.authority,
        )
        expected = ActionVerificationState.HUMAN_VERIFIED
    else:
        raise CaseAttentionOwnerError("VERIFIED_ACTION_HISTORY_REQUIRED")
    material = action_event.evidence.material
    if (
        material.verification is not expected
        or material.action_context_binding
        != replayed_proof.completed_context.hash_binding()
        or material.opportunity_id != replayed_proof.completed_context.opportunity_id
    ):
        raise CaseAttentionOwnerError("VERIFIED_ACTION_SCOPE_INVALID")
    try:
        rebuilt = record_verified_intervention(None, action_event).intervention
    except InterventionError:
        raise CaseAttentionOwnerError("VERIFIED_ACTION_HISTORY_REQUIRED") from None
    if rebuilt.canonical_bytes() != intervention.canonical_bytes():
        raise CaseAttentionOwnerError("VERIFIED_ACTION_INTERVENTION_MISMATCH")
    return replayed_proof.completion_event.occurred_at


def clear_intervention_verification_from_action(
    *,
    history: AttentionOwnerHistory,
    case: DOIOrderCase,
    event_id: EvidenceId,
    active_set_event_id: EvidenceId,
    action_event: object,
    intervention: DOIIntervention,
    completion_proof: CompletedSystemActionProof | CompletedHumanActionProof,
) -> AttentionOwnerDecision:
    """TR-026: clear one changed-evaluation cause from a replayed verified action."""

    resolved_at = _validated_action_resolution(
        action_event=action_event,
        intervention=intervention,
        completion_proof=completion_proof,
    )
    active = _find_active_set(
        history,
        condition=AttentionCondition.INTERVENTION_VERIFICATION_REQUIRED,
        active_set_event_id=active_set_event_id,
    )
    typed_event = intervention.action_events[0]
    if (
        typed_event.opportunity_id.value not in active.cause_subject
        or typed_event.evidence.material.action_context_binding
        != completion_proof.completed_context.hash_binding()
        or completion_proof.completed_context.order_id != case.order_id
    ):
        raise CaseAttentionOwnerError("VERIFIED_ACTION_CAUSE_SCOPE_INVALID")
    return _clear_attention(
        history=history,
        case=case,
        event_id=event_id,
        condition=AttentionCondition.INTERVENTION_VERIFICATION_REQUIRED,
        active_set_event_id=active_set_event_id,
        resolver=typed_event.hash_binding(),
        resulting_projection=None,
        transition_id="TR-026",
        occurred_at=resolved_at,
        validator_tag="INTERVENTION_VERIFICATION_CLEAR",
        inputs=(action_event, intervention, completion_proof),
    )


def _replay_search_history(
    history: DOIResultingOrderLinkSearchHistory,
) -> DOIResultingOrderLinkSearchHistory:
    if type(history) is not DOIResultingOrderLinkSearchHistory:
        raise CaseAttentionOwnerError("RESULTING_SEARCH_HISTORY_REQUIRED")
    rebuilt = DOIResultingOrderLinkSearchHistory(
        search_id=history.search_id,
        parent_order_id=history.parent_order_id,
        intervention_type=history.intervention_type,
    )
    try:
        for event in history.events:
            result = append_resulting_link_search(
                rebuilt,
                event_id=event.event_id,
                evidence=event.evidence,
            )
            if result.replayed:
                raise InterventionError("RESULTING_SEARCH_SOURCE_REPLAY")
            rebuilt = result.history
    except (InterventionError, TypeError, ValueError):
        raise CaseAttentionOwnerError("RESULTING_SEARCH_HISTORY_REQUIRED") from None
    if rebuilt != history:
        raise CaseAttentionOwnerError("RESULTING_SEARCH_HISTORY_REQUIRED")
    return rebuilt


def _replay_resulting_link(
    *,
    intervention: DOIIntervention,
    link: DOIResultingOrderLink,
) -> tuple[DOIResultingOrderLink, frozenset[str]]:
    if type(intervention) is not DOIIntervention or type(link) is not DOIResultingOrderLink:
        raise CaseAttentionOwnerError("RESULTING_LINK_HISTORY_REQUIRED")
    rebuilt: DOIResultingOrderLink | None = None
    final_codes: frozenset[str] = frozenset()
    try:
        for revision in link.revisions:
            result = append_resulting_link_revision(
                rebuilt,
                revision_id=revision.revision_id,
                intervention=intervention,
                evidence=revision.evidence_record,
            )
            if result.replayed:
                raise InterventionError("RESULTING_LINK_SOURCE_REPLAY")
            rebuilt = result.link
            final_codes = frozenset(item.code for item in result.reasons.reasons)
    except (InterventionError, TypeError, ValueError):
        raise CaseAttentionOwnerError("RESULTING_LINK_HISTORY_REQUIRED") from None
    if rebuilt is None or rebuilt.canonical_bytes() != link.canonical_bytes():
        raise CaseAttentionOwnerError("RESULTING_LINK_HISTORY_REQUIRED")
    return rebuilt, final_codes


def set_resulting_link_review_from_ambiguous_search(
    *,
    history: AttentionOwnerHistory,
    case: DOIOrderCase,
    event_id: EvidenceId,
    search_history: DOIResultingOrderLinkSearchHistory,
) -> AttentionOwnerDecision:
    """TR-092 ordinary branch: set review from an exact ambiguous search history."""

    rebuilt = _replay_search_history(search_history)
    projection = rebuilt.projection
    if (
        projection is None
        or projection.state is not ResultingOrderLinkSearchState.AMBIGUOUS
        or projection.parent_order_id != case.order_id
        or not rebuilt.events
    ):
        raise CaseAttentionOwnerError("AMBIGUOUS_RESULTING_SEARCH_REQUIRED")
    latest = rebuilt.events[-1]
    return _set_attention(
        history=history,
        case=case,
        event_id=event_id,
        condition=AttentionCondition.RESULTING_ORDER_LINK_REVIEW,
        evidence=projection.hash_binding(),
        subject=(
            "RESULTING_SEARCH",
            rebuilt.search_id.value,
            rebuilt.parent_order_id.to_json_value(),
            rebuilt.intervention_type.value,
            latest.hash_binding().sha256,
        ),
        transition_id="TR-092",
        occurred_at=latest.evidence.observed_at,
        validator_tag="RESULTING_SEARCH_SET",
        inputs=(search_history,),
    )


def set_resulting_link_review_from_mapping_conflict(
    *,
    history: AttentionOwnerHistory,
    case: DOIOrderCase,
    event_id: EvidenceId,
    intervention: DOIIntervention,
    link: DOIResultingOrderLink,
) -> AttentionOwnerDecision:
    """TR-092 conflict branch: set review only from reducer-proved mapping conflict."""

    rebuilt, codes = _replay_resulting_link(intervention=intervention, link=link)
    if (
        rebuilt.state is not ResultingOrderLinkState.AMBIGUOUS
        or rebuilt.parent_order_id != case.order_id
        or codes != frozenset({"RC-072", "RC-104"})
    ):
        raise CaseAttentionOwnerError("RESULTING_MAPPING_CONFLICT_REQUIRED")
    latest = rebuilt.revisions[-1]
    return _set_attention(
        history=history,
        case=case,
        event_id=event_id,
        condition=AttentionCondition.RESULTING_ORDER_LINK_REVIEW,
        evidence=rebuilt.hash_binding(),
        subject=(
            "RESULTING_LINK",
            rebuilt.link_id.value,
            rebuilt.intervention_id.value,
            rebuilt.parent_order_id.to_json_value(),
            rebuilt.child_order_id.to_json_value(),
            rebuilt.intervention_type.value,
        ),
        transition_id="TR-092",
        occurred_at=latest.evidence_record.observed_at,
        validator_tag="RESULTING_MAPPING_SET",
        inputs=(intervention, link),
    )


def clear_resulting_link_review_from_not_found_search(
    *,
    history: AttentionOwnerHistory,
    case: DOIOrderCase,
    event_id: EvidenceId,
    active_set_event_id: EvidenceId,
    search_history: DOIResultingOrderLinkSearchHistory,
) -> AttentionOwnerDecision:
    """TR-093 negative branch: clear a search cause only after complete disproof."""

    rebuilt = _replay_search_history(search_history)
    projection = rebuilt.projection
    active = _find_active_set(
        history,
        condition=AttentionCondition.RESULTING_ORDER_LINK_REVIEW,
        active_set_event_id=active_set_event_id,
    )
    if (
        projection is None
        or projection.state is not ResultingOrderLinkSearchState.NOT_FOUND
        or projection.parent_order_id != case.order_id
        or not rebuilt.events
        or active.cause_subject[0] != "RESULTING_SEARCH"
        or rebuilt.search_id.value != active.cause_subject[1]
        or rebuilt.parent_order_id.to_json_value() != active.cause_subject[2]
        or rebuilt.intervention_type.value != active.cause_subject[3]
        or active.cause_subject[4]
        not in {event.hash_binding().sha256 for event in rebuilt.events}
    ):
        raise CaseAttentionOwnerError("NEGATIVE_RESULTING_SEARCH_REQUIRED")
    latest = rebuilt.events[-1]
    return _clear_attention(
        history=history,
        case=case,
        event_id=event_id,
        condition=AttentionCondition.RESULTING_ORDER_LINK_REVIEW,
        active_set_event_id=active_set_event_id,
        resolver=latest.hash_binding(),
        resulting_projection=None,
        transition_id="TR-093",
        occurred_at=latest.evidence.observed_at,
        validator_tag="RESULTING_SEARCH_CLEAR",
        inputs=(search_history,),
    )


def clear_resulting_link_review_from_exact_link(
    *,
    history: AttentionOwnerHistory,
    case: DOIOrderCase,
    event_id: EvidenceId,
    active_set_event_id: EvidenceId,
    intervention: DOIIntervention,
    link: DOIResultingOrderLink,
) -> AttentionOwnerDecision:
    """TR-093 positive branch: bind an exact system/human link for the same subject."""

    rebuilt, codes = _replay_resulting_link(intervention=intervention, link=link)
    active = _find_active_set(
        history,
        condition=AttentionCondition.RESULTING_ORDER_LINK_REVIEW,
        active_set_event_id=active_set_event_id,
    )
    if (
        rebuilt.state
        not in {
            ResultingOrderLinkState.AUTO_LINKED,
            ResultingOrderLinkState.HUMAN_CONFIRMED,
        }
        or rebuilt.parent_order_id != case.order_id
        or codes not in {frozenset({"RC-070"}), frozenset({"RC-071"})}
    ):
        raise CaseAttentionOwnerError("EXACT_RESULTING_LINK_REQUIRED")
    if active.cause_subject[0] == "RESULTING_SEARCH":
        same_subject = (
            rebuilt.parent_order_id.to_json_value() == active.cause_subject[2]
            and rebuilt.intervention_type.value == active.cause_subject[3]
        )
    else:
        same_subject = (
            active.cause_subject[0] == "RESULTING_LINK"
            and rebuilt.link_id.value == active.cause_subject[1]
            and rebuilt.intervention_id.value == active.cause_subject[2]
            and rebuilt.parent_order_id.to_json_value() == active.cause_subject[3]
            and rebuilt.child_order_id.to_json_value() == active.cause_subject[4]
            and rebuilt.intervention_type.value == active.cause_subject[5]
        )
    if not same_subject:
        raise CaseAttentionOwnerError("RESULTING_LINK_RESOLVER_SCOPE_INVALID")
    latest = rebuilt.revisions[-1]
    return _clear_attention(
        history=history,
        case=case,
        event_id=event_id,
        condition=AttentionCondition.RESULTING_ORDER_LINK_REVIEW,
        active_set_event_id=active_set_event_id,
        resolver=latest.hash_binding(),
        resulting_projection=None,
        transition_id="TR-093",
        occurred_at=latest.evidence_record.observed_at,
        validator_tag="RESULTING_LINK_CLEAR",
        inputs=(intervention, link),
    )


def _replay_wwc_history(history: DOIWWCHistory) -> DOIWWCHistory:
    if type(history) is not DOIWWCHistory:
        raise CaseAttentionOwnerError("WWC_HISTORY_REQUIRED")
    rebuilt = DOIWWCHistory(stream_id=history.stream_id, order_id=history.order_id)
    try:
        for event in history.events:
            result = reduce_wwc(rebuilt, event)
            if result.replayed:
                raise DOIModelError("WWC_SOURCE_REPLAY")
            rebuilt = result.history
    except (DOIModelError, TypeError, ValueError):
        raise CaseAttentionOwnerError("WWC_HISTORY_REQUIRED") from None
    if rebuilt != history:
        raise CaseAttentionOwnerError("WWC_HISTORY_REQUIRED")
    return rebuilt


def _replay_human_fact_history(history: DOIHumanFactHistory) -> DOIHumanFactHistory:
    if type(history) is not DOIHumanFactHistory:
        raise CaseAttentionOwnerError("HUMAN_FACT_HISTORY_REQUIRED")
    rebuilt = DOIHumanFactHistory(stream_id=history.stream_id)
    try:
        for event in history.events:
            result = reduce_human_fact(rebuilt, event)
            if result.replayed:
                raise DOIModelError("HUMAN_FACT_SOURCE_REPLAY")
            rebuilt = result.history
    except (DOIModelError, TypeError, ValueError):
        raise CaseAttentionOwnerError("HUMAN_FACT_HISTORY_REQUIRED") from None
    if rebuilt != history:
        raise CaseAttentionOwnerError("HUMAN_FACT_HISTORY_REQUIRED")
    return rebuilt


_UNCERTAIN_WWC_STATES = frozenset(
    {
        WWCProjectionState.AUTHOR_UNCERTAIN,
        WWCProjectionState.TIMING_UNCERTAIN,
        WWCProjectionState.AUTHOR_AND_TIMING_UNCERTAIN,
    }
)
_RESOLVED_WWC_STATES = frozenset(
    {
        WWCProjectionState.ACTIVE_SELF,
        WWCProjectionState.ACTIVE_OTHER_REP,
        WWCProjectionState.NOT_APPLICABLE,
        WWCProjectionState.EXPIRED_OTHER_REP,
    }
)


def set_human_coordination_review_from_wwc(
    *,
    history: AttentionOwnerHistory,
    case: DOIOrderCase,
    event_id: EvidenceId,
    evaluation_input: DOIEvaluationInput,
    evaluation: DOIEvaluation,
    wwc_history: DOIWWCHistory,
) -> AttentionOwnerDecision:
    """TR-094: set coordination from the exact uncertain WWC event/evaluation pair."""

    _evaluation_for_case(
        case=case,
        evaluation_input=evaluation_input,
        evaluation=evaluation,
        current=True,
    )
    rebuilt = _replay_wwc_history(wwc_history)
    projection = rebuilt.projection
    codes = _reason_codes(evaluation)
    if (
        projection is None
        or projection.state not in _UNCERTAIN_WWC_STATES
        or projection.order_id != case.order_id
        or projection.current_finding.hash_binding()
        != evaluation_input.snapshot.wwc_finding.hash_binding()
        or "RC-057" not in codes
        or not codes.intersection({"RC-055", "RC-056"})
        or not rebuilt.events
    ):
        raise CaseAttentionOwnerError("UNCERTAIN_WWC_EVALUATION_REQUIRED")
    latest = rebuilt.events[-1]
    return _set_attention(
        history=history,
        case=case,
        event_id=event_id,
        condition=AttentionCondition.HUMAN_COORDINATION_REVIEW_REQUIRED,
        evidence=projection.hash_binding(),
        subject=(
            "WWC",
            rebuilt.stream_id.value,
            latest.hash_binding().sha256,
            evaluation.evaluation_id.value,
        ),
        transition_id="TR-094",
        occurred_at=latest.recorded_at,
        validator_tag="WWC_COORDINATION_SET",
        inputs=(evaluation_input, evaluation, wwc_history),
    )


def _validate_resolved_wwc_result(
    *,
    active: ActiveAttentionCause,
    case: DOIOrderCase,
    wwc_history: DOIWWCHistory,
) -> DOIWWCHistory:
    rebuilt = _replay_wwc_history(wwc_history)
    projection = rebuilt.projection
    if (
        active.cause_subject[0] != "WWC"
        or projection is None
        or projection.state not in _RESOLVED_WWC_STATES
        or projection.order_id != case.order_id
        or rebuilt.stream_id.value != active.cause_subject[1]
        or active.cause_subject[2]
        not in {event.hash_binding().sha256 for event in rebuilt.events}
        or not rebuilt.events
    ):
        raise CaseAttentionOwnerError("RESOLVED_WWC_PROJECTION_REQUIRED")
    return rebuilt


def clear_human_coordination_review_from_evaluation(
    *,
    history: AttentionOwnerHistory,
    case: DOIOrderCase,
    event_id: EvidenceId,
    active_set_event_id: EvidenceId,
    evaluation_input: DOIEvaluationInput,
    evaluation: DOIEvaluation,
    resulting_wwc_history: DOIWWCHistory,
) -> AttentionOwnerDecision:
    """TR-095 evaluation branch with a separate atomic WWC projection binding."""

    _evaluation_for_case(
        case=case,
        evaluation_input=evaluation_input,
        evaluation=evaluation,
        current=True,
    )
    active = _find_active_set(
        history,
        condition=AttentionCondition.HUMAN_COORDINATION_REVIEW_REQUIRED,
        active_set_event_id=active_set_event_id,
    )
    rebuilt = _validate_resolved_wwc_result(
        active=active,
        case=case,
        wwc_history=resulting_wwc_history,
    )
    projection = rebuilt.projection
    if projection is None:
        raise CaseAttentionOwnerError("RESOLVED_WWC_PROJECTION_REQUIRED")
    if (
        projection.current_finding.hash_binding()
        != evaluation_input.snapshot.wwc_finding.hash_binding()
    ):
        raise CaseAttentionOwnerError("WWC_RESOLVER_EVALUATION_MISMATCH")
    state = projection.state
    codes = _reason_codes(evaluation)
    expected_code = {
        WWCProjectionState.ACTIVE_SELF: "RC-053",
        WWCProjectionState.ACTIVE_OTHER_REP: "RC-054",
    }.get(state)
    if (
        (expected_code is not None and expected_code not in codes)
        or (
            expected_code is None
            and codes.intersection({"RC-053", "RC-054", "RC-055", "RC-056", "RC-057"})
        )
    ):
        raise CaseAttentionOwnerError("WWC_REGISTERED_PARTITION_MISMATCH")
    return _clear_attention(
        history=history,
        case=case,
        event_id=event_id,
        condition=AttentionCondition.HUMAN_COORDINATION_REVIEW_REQUIRED,
        active_set_event_id=active_set_event_id,
        resolver=evaluation.hash_binding(),
        resulting_projection=projection.hash_binding(),
        transition_id="TR-095",
        occurred_at=evaluation_input.evaluated_at,
        validator_tag="WWC_COORDINATION_EVALUATION_CLEAR",
        inputs=(evaluation_input, evaluation, resulting_wwc_history),
    )


def clear_human_coordination_review_from_human_fact(
    *,
    history: AttentionOwnerHistory,
    case: DOIOrderCase,
    event_id: EvidenceId,
    active_set_event_id: EvidenceId,
    human_fact_history: DOIHumanFactHistory,
    resulting_wwc_history: DOIWWCHistory,
) -> AttentionOwnerDecision:
    """TR-095 human branch; the fact is resolver and WWC projection is separate output."""

    active = _find_active_set(
        history,
        condition=AttentionCondition.HUMAN_COORDINATION_REVIEW_REQUIRED,
        active_set_event_id=active_set_event_id,
    )
    facts = _replay_human_fact_history(human_fact_history)
    if facts.projection is None or not facts.events:
        raise CaseAttentionOwnerError("COORDINATION_HUMAN_FACT_REQUIRED")
    fact = facts.projection.current_fact
    current_event = facts.events[-1]
    if (
        fact.usage_kind is not HumanFactUsageKind.COORDINATION_RESOLUTION
        or fact.result_code
        is not HumanFactResultCode.COORDINATION_RESOLUTION_RECORDED
        or fact.order_id != case.order_id
        or fact.action_context.case_id != case.case_id
        or fact.action_context.evaluation_id != case.current_evaluation_id
        or fact.evaluation_id != case.current_evaluation_id
        or current_event.fact.hash_binding() != fact.hash_binding()
        or current_event.recorded_at != fact.occurred_at
    ):
        raise CaseAttentionOwnerError("COORDINATION_HUMAN_FACT_REQUIRED")
    rebuilt = _validate_resolved_wwc_result(
        active=active,
        case=case,
        wwc_history=resulting_wwc_history,
    )
    projection = rebuilt.projection
    if projection is None:
        raise CaseAttentionOwnerError("RESOLVED_WWC_PROJECTION_REQUIRED")
    latest_wwc = rebuilt.events[-1]
    if (
        latest_wwc.guard.source != fact.source
        or latest_wwc.recorded_at != fact.occurred_at
        or _instant(fact.occurred_at) < _instant(active.set_at)
    ):
        raise CaseAttentionOwnerError("COORDINATION_HUMAN_FACT_WWC_MISMATCH")
    return _clear_attention(
        history=history,
        case=case,
        event_id=event_id,
        condition=AttentionCondition.HUMAN_COORDINATION_REVIEW_REQUIRED,
        active_set_event_id=active_set_event_id,
        resolver=current_event.hash_binding(),
        resulting_projection=projection.hash_binding(),
        transition_id="TR-095",
        occurred_at=fact.occurred_at,
        validator_tag="WWC_COORDINATION_HUMAN_CLEAR",
        inputs=(human_fact_history, resulting_wwc_history),
    )


def _validate_attention_owner_decision(
    decision: AttentionOwnerDecision,
) -> AttentionOwnerDecision:
    """Reissue a sealed decision from its retained typed owner inputs."""

    if (
        type(decision) is not AttentionOwnerDecision
        or decision._issuer_token is not _ATTENTION_DECISION_TOKEN
        or decision.schema_version != AttentionOwnerDecision.HASH_DOMAIN
        or decision.transition_id not in attention_owner_transition_ids()
        or decision.stream_id != decision.result.event.case_id
        or decision.occurrence_id != decision.result.event.event_id
        or decision.occurred_at != decision.result.event.occurred_at
        or decision.owner_binding != decision.result.event.hash_binding()
    ):
        raise CaseAttentionOwnerError("ATTENTION_DECISION_INVALID")
    _replay_attention_history(decision.prior_history)
    event = decision.result.event
    args = decision._inputs
    tag = decision._validator_tag
    if tag == "FAILED_EXTRACTION_SET":
        case, extraction = args
        rebuilt = set_recheck_from_failed_extraction(
            history=decision.prior_history,
            case=cast(DOIOrderCase, case),
            event_id=event.event_id,
            extraction_result=cast(DOIExtractionResult, extraction),
        )
    elif tag == "SOURCE_ABSENCE_SET":
        case, request, evaluation = args
        rebuilt = set_source_absence_from_evaluation(
            history=decision.prior_history,
            case=cast(DOIOrderCase, case),
            event_id=event.event_id,
            evaluation_input=cast(DOIEvaluationInput, request),
            evaluation=cast(DOIEvaluation, evaluation),
        )
    elif tag == "SOURCE_ABSENCE_REPLACED":
        case, active_set_id, extraction = args
        rebuilt = replace_source_absence_with_failed_recheck(
            history=decision.prior_history,
            case=cast(DOIOrderCase, case),
            event_id=event.event_id,
            active_set_event_id=cast(EvidenceId, active_set_id),
            extraction_result=cast(DOIExtractionResult, extraction),
        )
    elif tag in {"SOURCE_ABSENCE_CLEAR", "RECHECK_CLEAR"}:
        case, active_set_id, extraction, request, evaluation = args
        factory = (
            clear_source_absence_from_complete_evaluation
            if tag == "SOURCE_ABSENCE_CLEAR"
            else clear_recheck_from_complete_evaluation
        )
        rebuilt = factory(
            history=decision.prior_history,
            case=cast(DOIOrderCase, case),
            event_id=event.event_id,
            active_set_event_id=cast(EvidenceId, active_set_id),
            extraction_result=cast(DOIExtractionResult, extraction),
            evaluation_input=cast(DOIEvaluationInput, request),
            evaluation=cast(DOIEvaluation, evaluation),
        )
    elif tag == "INTERVENTION_VERIFICATION_SET":
        case, prior_request, prior, changed_request, changed = args
        rebuilt = set_intervention_verification_from_changed_evaluation(
            history=decision.prior_history,
            case=cast(DOIOrderCase, case),
            event_id=event.event_id,
            prior_evaluation_input=cast(DOIEvaluationInput, prior_request),
            prior_evaluation=cast(DOIEvaluation, prior),
            changed_evaluation_input=cast(DOIEvaluationInput, changed_request),
            changed_evaluation=cast(DOIEvaluation, changed),
        )
    elif tag == "INTERVENTION_VERIFICATION_CLEAR":
        case, active_set_id, action, intervention, proof = args
        rebuilt = clear_intervention_verification_from_action(
            history=decision.prior_history,
            case=cast(DOIOrderCase, case),
            event_id=event.event_id,
            active_set_event_id=cast(EvidenceId, active_set_id),
            action_event=action,
            intervention=cast(DOIIntervention, intervention),
            completion_proof=cast(
                CompletedSystemActionProof | CompletedHumanActionProof,
                proof,
            ),
        )
    elif tag == "RESULTING_SEARCH_SET":
        case, search = args
        rebuilt = set_resulting_link_review_from_ambiguous_search(
            history=decision.prior_history,
            case=cast(DOIOrderCase, case),
            event_id=event.event_id,
            search_history=cast(DOIResultingOrderLinkSearchHistory, search),
        )
    elif tag == "RESULTING_MAPPING_SET":
        case, intervention, link = args
        rebuilt = set_resulting_link_review_from_mapping_conflict(
            history=decision.prior_history,
            case=cast(DOIOrderCase, case),
            event_id=event.event_id,
            intervention=cast(DOIIntervention, intervention),
            link=cast(DOIResultingOrderLink, link),
        )
    elif tag == "RESULTING_SEARCH_CLEAR":
        case, active_set_id, search = args
        rebuilt = clear_resulting_link_review_from_not_found_search(
            history=decision.prior_history,
            case=cast(DOIOrderCase, case),
            event_id=event.event_id,
            active_set_event_id=cast(EvidenceId, active_set_id),
            search_history=cast(DOIResultingOrderLinkSearchHistory, search),
        )
    elif tag == "RESULTING_LINK_CLEAR":
        case, active_set_id, intervention, link = args
        rebuilt = clear_resulting_link_review_from_exact_link(
            history=decision.prior_history,
            case=cast(DOIOrderCase, case),
            event_id=event.event_id,
            active_set_event_id=cast(EvidenceId, active_set_id),
            intervention=cast(DOIIntervention, intervention),
            link=cast(DOIResultingOrderLink, link),
        )
    elif tag == "WWC_COORDINATION_SET":
        case, request, evaluation, wwc = args
        rebuilt = set_human_coordination_review_from_wwc(
            history=decision.prior_history,
            case=cast(DOIOrderCase, case),
            event_id=event.event_id,
            evaluation_input=cast(DOIEvaluationInput, request),
            evaluation=cast(DOIEvaluation, evaluation),
            wwc_history=cast(DOIWWCHistory, wwc),
        )
    elif tag == "WWC_COORDINATION_EVALUATION_CLEAR":
        case, active_set_id, request, evaluation, wwc = args
        rebuilt = clear_human_coordination_review_from_evaluation(
            history=decision.prior_history,
            case=cast(DOIOrderCase, case),
            event_id=event.event_id,
            active_set_event_id=cast(EvidenceId, active_set_id),
            evaluation_input=cast(DOIEvaluationInput, request),
            evaluation=cast(DOIEvaluation, evaluation),
            resulting_wwc_history=cast(DOIWWCHistory, wwc),
        )
    elif tag == "WWC_COORDINATION_HUMAN_CLEAR":
        case, active_set_id, facts, wwc = args
        rebuilt = clear_human_coordination_review_from_human_fact(
            history=decision.prior_history,
            case=cast(DOIOrderCase, case),
            event_id=event.event_id,
            active_set_event_id=cast(EvidenceId, active_set_id),
            human_fact_history=cast(DOIHumanFactHistory, facts),
            resulting_wwc_history=cast(DOIWWCHistory, wwc),
        )
    else:
        raise CaseAttentionOwnerError("ATTENTION_DECISION_VALIDATOR_UNKNOWN")
    if (
        rebuilt.canonical_bytes() != decision.canonical_bytes()
        or rebuilt.result != decision.result
    ):
        raise CaseAttentionOwnerError("ATTENTION_DECISION_REISSUE_MISMATCH")
    return decision


def validate_attention_owner_decision(
    decision: AttentionOwnerDecision,
) -> AttentionOwnerDecision:
    """Fail closed for malformed objects before replaying a sealed decision."""

    try:
        return _validate_attention_owner_decision(decision)
    except CaseAttentionOwnerError:
        raise
    except (AttributeError, TypeError):
        raise CaseAttentionOwnerError("ATTENTION_DECISION_INVALID") from None


def case_attention_hash_contracts() -> dict[str, str]:
    """Return every new canonical domain owned by this module."""

    return {
        "DOICaseSourceAdmissionProofV1": DOICaseSourceAdmissionProofV1.HASH_DOMAIN,
        "OwnedCaseSourceBinding": OwnedCaseSourceBinding.HASH_DOMAIN,
        "CaseOwnerEvent": CaseOwnerEvent.HASH_DOMAIN,
        "CaseOwnerDecision": CaseOwnerDecision.HASH_DOMAIN,
        "AttentionCauseKey": AttentionOwnerEvent.CAUSE_KEY_DOMAIN,
        "AttentionOwnerEvent": AttentionOwnerEvent.HASH_DOMAIN,
        "AttentionOwnerDecision": AttentionOwnerDecision.HASH_DOMAIN,
    }


def case_attention_hash_fixtures() -> tuple[tuple[str, str, bytes, str], ...]:
    """Return deterministic synthetic representatives for every owner hash domain."""

    order = OrderId("SYN-ORDER-1")
    doi_order = DoiOrderId(order)
    case_id = EvidenceId("SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-CASE")
    observed_at = CanonicalTimestamp("2026-08-20T12:00:00Z")
    source_row = SyntheticQueueRow(
        order,
        "TARGET_REP",
        SourceRowRefId(
            EvidenceId("SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-ROW")
        ),
    )
    image = SyntheticQueueImage(
        source_identity_id=SourceIdentityId(
            EvidenceId("SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-SOURCE")
        ),
        mapping_version=SOURCE_MAPPING_VERSION,
        structural_anchors=SOURCE_ANCHORS,
        finite_extent=NonNegativeCount(1),
        rows=(source_row,),
        revision="REV-KAT-CASE-ATTENTION",
        accessible=True,
    )
    source_result = ingest_synthetic_queue(
        image,
        image,
        candidate_batch_id=SourceBatchId(
            EvidenceId("SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-BATCH")
        ),
    )
    if source_result.batch is None or len(source_result.batch.staged_orders) != 1:
        raise CaseAttentionOwnerError("CASE_ATTENTION_KAT_SOURCE_INVALID")
    work_item = DOIRunWorkItem(
        work_item_id=RunWorkItemId(
            InteractionId("SYN-INTERACTION-DOI-CASE-ATTENTION-KAT-WORK")
        ),
        run_id=RunId("SYN-RUN-DOI-CASE-ATTENTION-KAT-SOURCE"),
        order_id=order,
        origin=RunWorkOrigin.SOURCE_IMPORT,
        source_batch_id=source_result.batch.batch_id,
    )
    case_decision = issue_case_creation_decision(
        history=CaseOwnerHistory(case_id=case_id, order_id=doi_order),
        event_id=EvidenceId("SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-CREATE"),
        binding_id=EvidenceId(
            "SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-SOURCE-BINDING"
        ),
        admission_proof_id=EvidenceId(
            "SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-ADMISSION"
        ),
        source_result=source_result,
        staged_order=source_result.batch.staged_orders[0],
        work_item=work_item,
        admitted_at=observed_at,
    )
    case = case_decision.result.history.projection
    if case is None:
        raise CaseAttentionOwnerError("CASE_ATTENTION_KAT_CASE_INVALID")
    registry = load_doi_registries()
    failed_at = CanonicalTimestamp("2026-08-20T12:01:00Z")
    failed_attempt = DOIExtractionAttempt(
        attempt_id=ExtractionAttemptId(
            InteractionId("SYN-INTERACTION-DOI-CASE-ATTENTION-KAT-EXTRACTION")
        ),
        run_id=DoiRunId(RunId("SYN-RUN-DOI-CASE-ATTENTION-KAT-EXTRACTION")),
        order_id=doi_order,
        started_at=CanonicalTimestamp("2026-08-20T12:00:30Z"),
        completed_at=failed_at,
        status=ExtractionStatus.FAILED,
        snapshot_id=None,
        reasons=ReasonSet(
            tuple(
                registry.reason_ref(code)
                for code in ("RC-011", "RC-014", "RC-015")
            )
        ),
        portal_read_count=NonNegativeCount(1),
    )
    attention_decision = set_recheck_from_failed_extraction(
        history=AttentionOwnerHistory(case_id=case_id, order_id=doi_order),
        case=case,
        event_id=EvidenceId("SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-SET"),
        extraction_result=DOIExtractionResult(
            attempt=failed_attempt,
            snapshot=None,
            attention_conditions=(AttentionCondition.RECHECK_REQUIRED,),
        ),
    )
    case_event = case_decision.result.event
    admission = case_event.source_binding.admission_proof
    attention_event = attention_decision.result.event
    records: dict[str, _CanonicalRecord] = {
        "DOICaseSourceAdmissionProofV1": admission,
        "OwnedCaseSourceBinding": case_event.source_binding,
        "CaseOwnerEvent": case_event,
        "CaseOwnerDecision": case_decision,
        "AttentionOwnerEvent": attention_event,
        "AttentionOwnerDecision": attention_decision,
    }
    rows = []
    for name, record in records.items():
        binding = record.hash_binding()
        rows.append((name, binding.domain, record.canonical_bytes(), binding.sha256))
    cause_key = attention_event.cause_key
    rows.append(
        (
            "AttentionCauseKey",
            cause_key.domain,
            cause_key.canonical_bytes,
            cause_key.sha256,
        )
    )
    contracts = case_attention_hash_contracts()
    if (
        {name for name, _, _, _ in rows} != set(contracts)
        or any(domain != contracts[name] for name, domain, _, _ in rows)
    ):
        raise CaseAttentionOwnerError("CASE_ATTENTION_KAT_INVENTORY_INVALID")
    return tuple(sorted(rows, key=lambda row: row[0]))


__all__ = [
    "ActiveAttentionCause",
    "AttentionOwnerAction",
    "AttentionOwnerDecision",
    "AttentionOwnerEvent",
    "AttentionOwnerHistory",
    "AttentionOwnerResult",
    "CaseAttentionOwnerError",
    "CaseOwnerDecision",
    "CaseOwnerEvent",
    "CaseOwnerEventKind",
    "CaseOwnerHistory",
    "CaseOwnerResult",
    "DOICaseSourceAdmissionProofV1",
    "OwnedCaseSourceBinding",
    "attention_owner_transition_ids",
    "case_attention_hash_contracts",
    "case_attention_hash_fixtures",
    "case_owner_transition_ids",
    "clear_human_coordination_review_from_evaluation",
    "clear_human_coordination_review_from_human_fact",
    "clear_intervention_verification_from_action",
    "clear_recheck_from_complete_evaluation",
    "clear_resulting_link_review_from_exact_link",
    "clear_resulting_link_review_from_not_found_search",
    "clear_source_absence_from_complete_evaluation",
    "issue_case_creation_decision",
    "issue_case_refresh_decision",
    "replace_source_absence_with_failed_recheck",
    "set_human_coordination_review_from_wwc",
    "set_intervention_verification_from_changed_evaluation",
    "set_recheck_from_failed_extraction",
    "set_resulting_link_review_from_ambiguous_search",
    "set_resulting_link_review_from_mapping_conflict",
    "set_source_absence_from_evaluation",
    "validate_attention_owner_decision",
    "validate_case_owner_decision",
]
