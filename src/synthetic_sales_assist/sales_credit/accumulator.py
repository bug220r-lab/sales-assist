"""Atomic process-local Sales Credit case accumulation and replay."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass, replace
from threading import RLock

from synthetic_sales_assist.domain.canonical import HashBinding, canonical_json_bytes, domain_hash
from synthetic_sales_assist.domain.identities import EvidenceId, OrderId, RunId, SnapshotId
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.sales_credit.discovery import (
    CandidateInteractionScope,
    InMemoryNoOrderStateLedger,
    InMemorySearchRunAuthority,
    NoOrderLedgerError,
    OrderSearchRun,
    PostEvaluationCommitResult,
    PostEvaluationNoOrderStage,
    SearchRunAuthorityClaim,
    SearchRunAuthorityError,
    SearchRunOwnerPartition,
    SearchRunPartitionTransfer,
    SearchRunPartitionKind,
    SearchRunSeal,
    SelectorOwnedCandidateEvaluation,
    plan_discovery,
)
from synthetic_sales_assist.sales_credit.evaluator import (
    KNOWN_OTHER_REP_CATALOG,
    evaluate_sales_credit,
)
from synthetic_sales_assist.sales_credit.models import (
    AttributionClassification,
    EvidenceEvent,
    HumanOutcomeType,
    InteractionRecord,
    ManagerOutcome,
    OrderSnapshot,
    OrderValueStatus,
    ReplacementCandidateInput,
    ReplacementStatus,
    SalesCreditCase,
    SalesCreditEvaluation,
    SalesCreditReason,
    SalesCreditValidationError,
    SearchTriggerType,
    WorkflowState,
)
from synthetic_sales_assist.sales_credit.retention import (
    ClosureProjection,
    build_closure_projection,
    purge_eligible,
)
from synthetic_sales_assist.sales_credit.windows import (
    WindowPosition,
    cancellation_replacement_window,
    window_position,
)
from synthetic_sales_assist.safety.content import scan_payload


_DIGEST_PATTERN = re.compile(r"\A[0-9a-f]{64}\Z", re.ASCII)
_TERMINAL_SYSTEM_STATES = frozenset(
    {
        WorkflowState.CANCELED_NO_REPLACEMENT,
        WorkflowState.REVIEW_WINDOW_CLOSED_NO_ORDER,
    }
)
_MANAGER_OUTCOME_STATES = frozenset(
    {
        WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
        WorkflowState.INBOUND_EVIDENCE_HUMAN_REVIEW,
        WorkflowState.MANUAL_REVIEW_REQUIRED,
        WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
        WorkflowState.OTHER_REP_HUMAN_REVIEW,
        WorkflowState.OUTBOUND_EVIDENCE_HUMAN_REVIEW,
        WorkflowState.POSSIBLE_REPLACEMENT_HUMAN_REVIEW,
        WorkflowState.TIMING_UNCERTAIN_HUMAN_REVIEW,
        WorkflowState.VERIFIED_PREORDER_EVIDENCE,
    }
)
class CaseAccumulatorError(RuntimeError):
    """Closed operation error with no retained command or active detail."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Sales Credit case operation rejected: {code}")


def _discovery_interactions_for_order(
    run: OrderSearchRun,
    order_id: OrderId,
) -> tuple[InteractionRecord, ...]:
    matching_identifiers = {
        result.identifier
        for result in run.native_result_sets
        if order_id in result.order_ids
    }
    selected: list[InteractionRecord] = []
    for interaction in run.interactions:
        plan = plan_discovery(
            email_values=(() if interaction.email is None else (interaction.email,)),
            phone_values=(() if interaction.phone is None else (interaction.phone,)),
        )
        if matching_identifiers.intersection(plan.identifiers):
            selected.append(interaction)
    return tuple(selected)


def _instant_key(value: CanonicalTimestamp) -> tuple[int, int]:
    return (value.epoch_seconds, value.nanosecond)


@dataclass(frozen=True, slots=True, repr=False, kw_only=True)
class CaseMutation:
    command_id: EvidenceId
    order_id: OrderId
    occurred_at: CanonicalTimestamp
    interactions: tuple[InteractionRecord, ...] = ()
    snapshots: tuple[OrderSnapshot, ...] = ()
    evidence: tuple[EvidenceEvent, ...] = ()
    evaluation: SalesCreditEvaluation | None = None
    discovery_run: OrderSearchRun | None = None
    replacement_run: OrderSearchRun | None = None
    replacement_candidates: tuple[ReplacementCandidateInput, ...] = ()
    active_note: str | None = None

    HASH_DOMAIN = "sales-credit-case-command/v1"

    def __post_init__(self) -> None:
        if type(self.command_id) is not EvidenceId:
            raise CaseAccumulatorError("mutation_command_id")
        if type(self.order_id) is not OrderId:
            raise CaseAccumulatorError("mutation_order_id")
        if type(self.occurred_at) is not CanonicalTimestamp:
            raise CaseAccumulatorError("mutation_occurred_at")
        for values, expected, code, identity in (
            (self.interactions, InteractionRecord, "mutation_interactions", "interaction_id"),
            (self.snapshots, OrderSnapshot, "mutation_snapshots", "snapshot_id"),
            (self.evidence, EvidenceEvent, "mutation_evidence", "evidence_id"),
        ):
            if type(values) is not tuple or any(type(value) is not expected for value in values):
                raise CaseAccumulatorError(code)
            keys = tuple(getattr(value, identity).value for value in values)
            if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
                raise CaseAccumulatorError(code)
        if self.evaluation is not None and type(self.evaluation) is not SalesCreditEvaluation:
            raise CaseAccumulatorError("mutation_evaluation")
        if self.evaluation is not None and self.evaluation.order_id != self.order_id:
            raise CaseAccumulatorError("mutation_evaluation_order")
        if self.discovery_run is not None and type(self.discovery_run) is not OrderSearchRun:
            raise CaseAccumulatorError("mutation_discovery_run")
        if self.replacement_run is not None and type(
            self.replacement_run
        ) is not OrderSearchRun:
            raise CaseAccumulatorError("mutation_replacement_run")
        if type(self.replacement_candidates) is not tuple or any(
            type(item) is not ReplacementCandidateInput
            for item in self.replacement_candidates
        ):
            raise CaseAccumulatorError("mutation_replacement_candidates")
        candidate_keys = tuple(
            (item.snapshot.order_id.value, item.snapshot.snapshot_id.value)
            for item in self.replacement_candidates
            if item.snapshot.order_id is not None
        )
        if (
            len(candidate_keys) != len(self.replacement_candidates)
            or candidate_keys != tuple(sorted(candidate_keys))
            or len({key[0] for key in candidate_keys}) != len(candidate_keys)
            or len({key[1] for key in candidate_keys}) != len(candidate_keys)
        ):
            raise CaseAccumulatorError("mutation_replacement_candidates")
        if any(item.snapshot.order_id == self.order_id for item in self.replacement_candidates):
            raise CaseAccumulatorError("mutation_replacement_identity")
        if self.replacement_run is None:
            if self.replacement_candidates:
                raise CaseAccumulatorError("mutation_replacement_run_missing")
        else:
            if self.evaluation is None:
                raise CaseAccumulatorError("mutation_replacement_without_evaluation")
            if self.replacement_run.trigger is not SearchTriggerType.REPLACEMENT_CHECK:
                raise CaseAccumulatorError("mutation_replacement_trigger")
            if self.replacement_run.interactions != self.interactions:
                raise CaseAccumulatorError("mutation_replacement_interactions")
            run_orders = tuple(
                item.value
                for item in self.replacement_run.result.order_ids
                if item != self.order_id
            )
            if run_orders != tuple(key[0] for key in candidate_keys):
                raise CaseAccumulatorError("mutation_replacement_parity")
        if self.discovery_run is not None:
            if self.discovery_run.trigger is SearchTriggerType.REPLACEMENT_CHECK:
                raise CaseAccumulatorError("mutation_discovery_trigger")
            native_interactions = {
                item.interaction_id.value: item
                for item in _discovery_interactions_for_order(
                    self.discovery_run,
                    self.order_id,
                )
            }
            if any(
                native_interactions.get(item.interaction_id.value) != item
                for item in self.interactions
            ):
                raise CaseAccumulatorError("mutation_discovery_interactions")
            if self.order_id not in self.discovery_run.result.order_ids:
                raise CaseAccumulatorError("mutation_discovery_order")
        if self.discovery_run is not None and self.replacement_run is not None:
            raise CaseAccumulatorError("mutation_search_role_conflict")
        authority_run = self.discovery_run or self.replacement_run
        if authority_run is not None and _instant_key(
            authority_run.completed_at
        ) > _instant_key(self.occurred_at):
            raise CaseAccumulatorError("mutation_search_not_completed")
        for snapshot in self.snapshots:
            if snapshot.order_id is not None and snapshot.order_id != self.order_id:
                raise CaseAccumulatorError("mutation_snapshot_order")
            if (
                self.discovery_run is not None
                and snapshot.placed_at is not None
                and _instant_key(snapshot.placed_at)
                > _instant_key(self.discovery_run.completed_at)
            ):
                raise CaseAccumulatorError("mutation_order_after_search")
        if self.replacement_run is not None and any(
            item.snapshot.placed_at is not None
            and _instant_key(item.snapshot.placed_at)
            > _instant_key(self.replacement_run.completed_at)
            for item in self.replacement_candidates
        ):
            raise CaseAccumulatorError("mutation_order_after_search")
        if any(item.order_id != self.order_id for item in self.evidence):
            raise CaseAccumulatorError("mutation_evidence_order")
        if self.active_note is not None and (
            type(self.active_note) is not str
            or not self.active_note.startswith("synthetic:")
            or not self.active_note.isascii()
            or len(self.active_note) > 256
        ):
            raise CaseAccumulatorError("mutation_note")
        if self.active_note is not None and scan_payload({"note": self.active_note}):
            raise CaseAccumulatorError("mutation_note")
        if not any((self.interactions, self.snapshots, self.evidence, self.evaluation)):
            raise CaseAccumulatorError("mutation_empty")

    def canonical_bytes(self) -> bytes:
        return _mutation_bytes(self)

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "CaseMutation(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class AcceptedCaseState:
    """Identity- and detail-free logical state returned by accepted commands."""

    workflow_state: WorkflowState
    attribution: AttributionClassification
    order_value_status: OrderValueStatus
    human_outcome: HumanOutcomeType | None

    def __post_init__(self) -> None:
        if type(self.workflow_state) is not WorkflowState:
            raise CaseAccumulatorError("accepted_state_workflow")
        if type(self.attribution) is not AttributionClassification:
            raise CaseAccumulatorError("accepted_state_attribution")
        if type(self.order_value_status) is not OrderValueStatus:
            raise CaseAccumulatorError("accepted_state_value")
        if self.human_outcome is not None and type(
            self.human_outcome
        ) is not HumanOutcomeType:
            raise CaseAccumulatorError("accepted_state_outcome")
        if (
            self.human_outcome is not None
            and self.workflow_state is not WorkflowState.CLOSED
        ):
            raise CaseAccumulatorError("accepted_state_outcome_workflow")

    def __repr__(self) -> str:
        return "AcceptedCaseState(<minimized>)"


@dataclass(frozen=True, slots=True, repr=False)
class CaseMutationResult:
    state: AcceptedCaseState
    replayed: bool

    def __post_init__(self) -> None:
        if type(self.state) is not AcceptedCaseState:
            raise CaseAccumulatorError("mutation_result_state")
        if type(self.replayed) is not bool:
            raise CaseAccumulatorError("mutation_result_replay")

    def __repr__(self) -> str:
        return "CaseMutationResult(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class SearchEvaluationBatch:
    """One exact discovery result and one independent mutation per candidate."""

    run: OrderSearchRun
    mutations: tuple[CaseMutation, ...]

    def __post_init__(self) -> None:
        if type(self.run) is not OrderSearchRun:
            raise CaseAccumulatorError("search_batch_run")
        if self.run.trigger is SearchTriggerType.REPLACEMENT_CHECK:
            raise CaseAccumulatorError("search_batch_trigger")
        if type(self.mutations) is not tuple or any(
            type(item) is not CaseMutation for item in self.mutations
        ):
            raise CaseAccumulatorError("search_batch_mutations")
        mutation_orders = tuple(item.order_id.value for item in self.mutations)
        expected_orders = tuple(item.value for item in self.run.result.order_ids)
        if (
            mutation_orders != tuple(sorted(mutation_orders))
            or len(mutation_orders) != len(set(mutation_orders))
            or not set(mutation_orders).issubset(expected_orders)
        ):
            raise CaseAccumulatorError("search_batch_order_parity")
        if any(
            item.discovery_run != self.run or item.evaluation is None
            for item in self.mutations
        ):
            raise CaseAccumulatorError("search_batch_authority")

    def __repr__(self) -> str:
        return "SearchEvaluationBatch(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class CoordinatedDiscoveryResult:
    case_results: tuple[CaseMutationResult, ...]
    no_order_result: PostEvaluationCommitResult

    def __post_init__(self) -> None:
        if type(self.case_results) is not tuple or any(
            type(item) is not CaseMutationResult for item in self.case_results
        ):
            raise CaseAccumulatorError("coordinated_result_cases")
        if type(self.no_order_result) is not PostEvaluationCommitResult:
            raise CaseAccumulatorError("coordinated_result_no_order")

    def __repr__(self) -> str:
        return "CoordinatedDiscoveryResult(<minimized>)"


@dataclass(frozen=True, slots=True, repr=False)
class OutcomeResult:
    state: AcceptedCaseState
    replayed: bool

    def __post_init__(self) -> None:
        if type(self.state) is not AcceptedCaseState:
            raise CaseAccumulatorError("outcome_result_state")
        if type(self.replayed) is not bool:
            raise CaseAccumulatorError("outcome_result_replay")

    def __repr__(self) -> str:
        return "OutcomeResult(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ClosureResult:
    projection: ClosureProjection
    command_sha256: str
    replayed: bool

    def __post_init__(self) -> None:
        if type(self.projection) is not ClosureProjection:
            raise CaseAccumulatorError("closure_result_projection")
        if type(self.command_sha256) is not str or not _DIGEST_PATTERN.fullmatch(
            self.command_sha256
        ):
            raise CaseAccumulatorError("closure_result_digest")
        if type(self.replayed) is not bool:
            raise CaseAccumulatorError("closure_result_replay")

    def __repr__(self) -> str:
        return "ClosureResult(<redacted>)"


def _accepted_case_state(case: SalesCreditCase) -> AcceptedCaseState:
    return AcceptedCaseState(
        workflow_state=case.workflow_state,
        attribution=case.attribution,
        order_value_status=case.order_value_status,
        human_outcome=(
            None
            if case.manager_outcome is None
            else case.manager_outcome.outcome
        ),
    )


@dataclass(slots=True)
class _ActiveEntry:
    case: SalesCreditCase
    interactions: dict[str, InteractionRecord]
    snapshots: dict[str, OrderSnapshot]
    evidence: dict[str, EvidenceEvent]
    evaluations: dict[str, SalesCreditEvaluation]
    search_run_ids: tuple[str, ...]
    authorized_interaction_ids: tuple[str, ...]
    latest_evaluation_id: str | None
    latest_evaluation_at: CanonicalTimestamp | None
    system_workflow_before_close: WorkflowState


@dataclass(frozen=True, slots=True)
class _Receipt:
    order_id: OrderId
    material_authenticator: bytes
    result: CaseMutationResult | OutcomeResult


@dataclass(frozen=True, slots=True)
class _TransferredRunPartition:
    active_order_ids: tuple[str, ...]
    closed_order_ids: tuple[str, ...]
    partition: SearchRunOwnerPartition


@dataclass(frozen=True, slots=True)
class _RunReceipt:
    binding_authenticator: bytes | None
    order_ids: tuple[str, ...]
    partition: SearchRunOwnerPartition | None
    transferred_partitions: tuple[_TransferredRunPartition, ...] = ()


@dataclass(frozen=True, slots=True)
class _ClosedRunPartitionRef:
    run_id: RunId
    partition: SearchRunOwnerPartition


@dataclass(frozen=True, slots=True)
class _OutcomeOccurrenceReceipt:
    order_id: OrderId
    canonical_bytes: bytes
    result: OutcomeResult


@dataclass(frozen=True, slots=True)
class _ClosedOutcomeOccurrenceReceipt:
    order_id: OrderId
    material_authenticator: bytes
    result: OutcomeResult


@dataclass(frozen=True, slots=True)
class _ClosedCommandAuthenticator:
    order_id: OrderId
    authenticator: bytes
    result: CaseMutationResult | OutcomeResult | ClosureResult


def _replacement_window_holds_closure(
    entry: _ActiveEntry,
    authority: SalesCreditEvaluation,
) -> bool:
    snapshot = entry.snapshots.get(authority.snapshot_id.value)
    if snapshot is None or snapshot.canceled_at is None:
        return False
    if authority.replacement.status in {
        ReplacementStatus.EXACT_RELEVANT,
        ReplacementStatus.POSSIBLE_REVIEW,
    }:
        return False
    if entry.latest_evaluation_at is None:
        return True
    return window_position(
        cancellation_replacement_window(snapshot.canceled_at),
        entry.latest_evaluation_at,
    ) is WindowPosition.ACTIVE


def _hash_dict(value: object) -> dict[str, str]:
    return {"domain": value.domain, "sha256": value.sha256}  # type: ignore[attr-defined]


def _interaction_dict(value: InteractionRecord) -> dict[str, object]:
    return {
        "active_notes": value.active_notes,
        "corrected_at": None if value.corrected_at is None else value.corrected_at.value,
        "corrected_precision": (
            None if value.corrected_precision is None else value.corrected_precision.value
        ),
        "email": value.email,
        "interaction_id": value.interaction_id.value,
        "last_check_at": None if value.last_check_at is None else value.last_check_at.value,
        "next_eligible_check_at": (
            None
            if value.next_eligible_check_at is None
            else value.next_eligible_check_at.value
        ),
        "part_request": value.part_request,
        "phone": value.phone,
        "provenance": value.provenance.to_dict(),
        "recorded_at": value.recorded_at.value,
        "review_window_end": value.review_window_end.isoformat(),
        "review_window_start": value.review_window_start.isoformat(),
        "schema_version": value.schema_version,
        "source_ref": value.source_ref.value,
        "timestamp_precision": value.timestamp_precision.value,
        "vin_like_reference": value.vin_like_reference,
        "workflow_state": value.workflow_state.value,
    }


def _line_dict(value: object) -> dict[str, object]:
    return {
        "canonical_es_number": value.canonical_es_number,
        "canonical_mfg_oe_number": value.canonical_mfg_oe_number,
        "content": _hash_dict(value.content),
        "description": value.description,
        "line_id": value.line_id.value,
        "line_value": value.line_value.to_json_value(),
        "observed_availability": value.observed_availability,
        "observed_eta": None if value.observed_eta is None else value.observed_eta.value,
        "quantity": value.quantity.to_json_value(),
        "raw_es_number": value.raw_es_number,
        "raw_line_rep": value.raw_line_rep,
        "raw_mfg_oe_number": value.raw_mfg_oe_number,
        "sku_id": value.sku_id.value,
        "warnings": list(value.warnings),
    }


def _snapshot_dict(value: OrderSnapshot) -> dict[str, object]:
    return {
        "active_notes": value.active_notes,
        "canceled_at": None if value.canceled_at is None else value.canceled_at.value,
        "captured_at": value.captured_at.value,
        "current_value": (
            None if value.current_value is None else value.current_value.to_json_value()
        ),
        "customer_ids": [item.value for item in value.customer_ids],
        "extraction_status": value.extraction_status.value,
        "lifecycle_status": value.lifecycle_status.value,
        "lines": [_line_dict(item) for item in value.lines],
        "material_changes": [
            {
                "affects_commercial_value": item.affects_commercial_value,
                "change_id": item.change_id.value,
                "kind": item.kind.value,
            }
            for item in value.material_changes
        ],
        "notes_scan_status": value.notes_scan_status.value,
        "order_id": None if value.order_id is None else value.order_id.value,
        "parser": value.parser.to_dict(),
        "placed_at": None if value.placed_at is None else value.placed_at.value,
        "placed_at_precision": (
            None if value.placed_at_precision is None else value.placed_at_precision.value
        ),
        "placed_value": (
            None if value.placed_value is None else value.placed_value.to_json_value()
        ),
        "provenance": None if value.provenance is None else _hash_dict(value.provenance),
        "raw_order_rep": value.raw_order_rep,
        "raw_order_status": value.raw_order_status,
        "schema_version": value.schema_version,
        "snapshot_id": value.snapshot_id.value,
        "source_ref": None if value.source_ref is None else value.source_ref.value,
        "warnings": list(value.warnings),
    }


def _evidence_dict(value: EvidenceEvent) -> dict[str, object]:
    return {
        "active_excerpt": value.active_excerpt,
        "classification": value.classification.value,
        "connected": value.connected,
        "direction": value.direction.value,
        "evidence_id": value.evidence_id.value,
        "identifier_kind": value.identifier_kind.value,
        "interaction_id": value.interaction_id.value,
        "matched_identifier_ref": _hash_dict(value.matched_identifier_ref),
        "occurred_at": value.occurred_at.value,
        "order_id": value.order_id.value,
        "schema_version": value.schema_version,
        "source_ref": value.source_ref.value,
        "source_type": value.source_type.value,
        "target_rep_participated": value.target_rep_participated,
        "timestamp_precision": value.timestamp_precision.value,
        "timing": value.timing.value,
        "two_way": value.two_way,
    }


def _search_identifier_dict(value: object) -> dict[str, str]:
    return {
        "kind": value.kind.value,
        "value": value.value,
    }


def _search_run_dict(value: OrderSearchRun | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "adapter": value.adapter.to_dict(),
        "completed_at": value.completed_at.value,
        "force_explanation": value.force_explanation,
        "interaction_ids": [item.value for item in value.interaction_ids],
        "native_result_sets": [
            {
                "completeness": item.completeness.value,
                "identifier": _search_identifier_dict(item.identifier),
                "order_ids": [order_id.value for order_id in item.order_ids],
            }
            for item in value.native_result_sets
        ],
        "run_id": value.run_id.value,
        "schema_version": value.schema_version,
        "started_at": value.started_at.value,
        "trigger": value.trigger.value,
        "warnings": list(value.warnings),
    }


def _search_run_bytes(value: OrderSearchRun) -> bytes:
    document = {
        "interactions": [_interaction_dict(item) for item in value.interactions],
        "run": _search_run_dict(value),
    }
    return canonical_json_bytes(document, expected_members=set(document))


def _replacement_candidate_dict(value: ReplacementCandidateInput) -> dict[str, object]:
    return {
        "line_universe_complete": value.line_universe_complete,
        "possible_nonexact_continuity": value.possible_nonexact_continuity,
        "snapshot": _snapshot_dict(value.snapshot),
    }


def _expected_evidence_identifier_ref(value: EvidenceEvent) -> HashBinding:
    document = {
        "identifier_kind": value.identifier_kind.value,
        "interaction_id": value.interaction_id.value,
    }
    return domain_hash(
        EvidenceEvent.IDENTIFIER_REF_DOMAIN,
        canonical_json_bytes(document, expected_members=set(document)),
    )


def _mutation_bytes(value: CaseMutation) -> bytes:
    document = {
        "active_note": value.active_note,
        "command_id": value.command_id.value,
        "evaluation": None if value.evaluation is None else value.evaluation.to_dict(),
        "evidence": [_evidence_dict(item) for item in value.evidence],
        "interactions": [_interaction_dict(item) for item in value.interactions],
        "occurred_at": value.occurred_at.value,
        "order_id": value.order_id.value,
        "discovery_run": _search_run_dict(value.discovery_run),
        "replacement_candidates": [
            _replacement_candidate_dict(item)
            for item in value.replacement_candidates
        ],
        "replacement_run": _search_run_dict(value.replacement_run),
        "snapshots": [_snapshot_dict(item) for item in value.snapshots],
    }
    return canonical_json_bytes(document, expected_members=set(document))


def _default_digest(value: bytes) -> str:
    return hashlib.sha256(CaseMutation.HASH_DOMAIN.encode("ascii") + b"\n" + value).hexdigest()


class InMemoryCaseAccumulator:
    """One-lock state/receipt boundary for process-local Milestone 2 behavior."""

    def __init__(
        self,
        *,
        digest_function: Callable[[bytes], str] = _default_digest,
        search_run_authority: InMemorySearchRunAuthority,
    ) -> None:
        if not callable(digest_function):
            raise CaseAccumulatorError("digest_function")
        if type(search_run_authority) is not InMemorySearchRunAuthority:
            raise CaseAccumulatorError("search_run_authority")
        self._digest_function = digest_function
        self._lock = RLock()
        self._search_run_authority = search_run_authority
        self._search_run_owner = search_run_authority.new_owner()
        self._active: dict[str, _ActiveEntry] = {}
        self._closed: dict[str, ClosureProjection] = {}
        self._receipts: dict[str, _Receipt] = {}
        self._run_receipts: dict[str, _RunReceipt] = {}
        self._outcome_occurrences: dict[str, _OutcomeOccurrenceReceipt] = {}
        self._closed_outcome_occurrences: dict[
            bytes, _ClosedOutcomeOccurrenceReceipt
        ] = {}
        self._closed_order_run_ids: dict[str, tuple[str, ...]] = {}
        self._closed_run_receipt_ids: dict[str, tuple[str, ...]] = {}
        self._closed_run_partitions: dict[
            str, tuple[_ClosedRunPartitionRef, ...]
        ] = {}
        self._closed_command_authenticators: dict[
            bytes, _ClosedCommandAuthenticator
        ] = {}
        self._closure_replay_key = secrets.token_bytes(32)

    @property
    def search_run_authority(self) -> InMemorySearchRunAuthority:
        return self._search_run_authority

    def _claim_search_runs(
        self,
        runs: tuple[OrderSearchRun, ...],
    ) -> tuple[SearchRunAuthorityClaim, ...]:
        claims: list[SearchRunAuthorityClaim] = []
        try:
            for run in runs:
                claims.append(
                    self._search_run_authority.claim(
                        run,
                        owner=self._search_run_owner,
                    )
                )
        except SearchRunAuthorityError as error:
            for claim in reversed(claims):
                self._search_run_authority.rollback(claim)
            if error.code == "search_run_material_conflict":
                raise CaseAccumulatorError("search_run_material_conflict") from None
            if error.code == "search_run_retired":
                raise CaseAccumulatorError("search_run_retired") from None
            raise CaseAccumulatorError("search_run_authority") from None
        return tuple(claims)

    def _rollback_search_claims(
        self,
        claims: tuple[SearchRunAuthorityClaim, ...],
    ) -> None:
        for claim in reversed(claims):
            self._search_run_authority.rollback(claim)

    def _digest(self, value: bytes) -> str:
        failed = False
        digest: object = None
        try:
            digest = self._digest_function(value)
        except Exception:
            failed = True
        if failed:
            raise CaseAccumulatorError("digest_failure") from None
        if type(digest) is not str or _DIGEST_PATTERN.fullmatch(digest) is None:
            raise CaseAccumulatorError("digest_invalid")
        return digest

    def _closure_authenticator(self, canonical_bytes: bytes) -> bytes:
        return hmac.digest(
            self._closure_replay_key,
            canonical_bytes,
            "sha256",
        )

    def _identity_authenticator(self, *, domain: str, value: str) -> bytes:
        return self._closure_authenticator(
            domain.encode("ascii") + b"\n" + value.encode("ascii")
        )

    def _closed_command_key(self, command_id: EvidenceId | str) -> bytes:
        value = command_id.value if type(command_id) is EvidenceId else command_id
        return self._identity_authenticator(
            domain="sales-credit-closed-command-identity/v1",
            value=value,
        )

    def _closed_occurrence_key(self, occurrence_id: EvidenceId | str) -> bytes:
        value = (
            occurrence_id.value
            if type(occurrence_id) is EvidenceId
            else occurrence_id
        )
        return self._identity_authenticator(
            domain="sales-credit-closed-outcome-occurrence/v1",
            value=value,
        )

    def _run_binding_authenticator(
        self,
        *,
        run: OrderSearchRun,
        command_ids: tuple[str, ...],
        order_ids: tuple[str, ...],
    ) -> bytes:
        document = {
            "command_ids": list(command_ids),
            "order_ids": list(order_ids),
        }
        return self._closure_authenticator(
            b"sales-credit-case-run-binding/v1\n"
            + _search_run_bytes(run)
            + b"\n"
            + canonical_json_bytes(document, expected_members=set(document))
        )

    def _existing_closed_replay(
        self,
        command_id: EvidenceId,
        canonical: bytes,
        digest: str,
    ) -> CaseMutationResult | OutcomeResult | ClosureResult | None:
        retained = self._closed_command_authenticators.get(
            self._closed_command_key(command_id)
        )
        if retained is None:
            return None
        if not hmac.compare_digest(
            retained.authenticator,
            self._closure_authenticator(canonical),
        ):
            raise CaseAccumulatorError("command_material_conflict")
        if type(retained.result) is ClosureResult:
            return replace(
                retained.result,
                command_sha256=digest,
                replayed=True,
            )
        return replace(retained.result, replayed=True)

    def _existing_receipt(
        self,
        command_id: EvidenceId,
        canonical: bytes,
    ) -> _Receipt | None:
        receipt = self._receipts.get(command_id.value)
        if receipt is None:
            return None
        if not hmac.compare_digest(
            receipt.material_authenticator,
            self._closure_authenticator(canonical),
        ):
            raise CaseAccumulatorError("command_material_conflict")
        return receipt

    def _bind_run_receipt(
        self,
        target: dict[str, _RunReceipt],
        *,
        run: OrderSearchRun,
        command_ids: tuple[str, ...],
        order_ids: tuple[str, ...],
        partition: SearchRunOwnerPartition | None = None,
    ) -> None:
        expected_commands = tuple(sorted(command_ids))
        expected_orders = tuple(sorted(order_ids))
        if (
            not expected_commands
            or len(expected_commands) != len(set(expected_commands))
            or not expected_orders
            or len(expected_orders) != len(set(expected_orders))
        ):
            raise CaseAccumulatorError("search_run_receipt_shape")
        binding_authenticator = self._run_binding_authenticator(
            run=run,
            command_ids=expected_commands,
            order_ids=expected_orders,
        )
        prior = target.get(run.run_id.value)
        if prior is not None:
            if prior.binding_authenticator is None or not hmac.compare_digest(
                prior.binding_authenticator,
                binding_authenticator,
            ) or prior.partition is not partition:
                raise CaseAccumulatorError("search_run_reuse_conflict")
            return
        target[run.run_id.value] = _RunReceipt(
            binding_authenticator,
            expected_orders,
            partition,
        )

    def _bind_transferred_run_partitions(
        self,
        assignments: tuple[
            tuple[RunId, tuple[OrderId, ...], SearchRunOwnerPartition], ...
        ],
    ) -> None:
        """Attach opaque prior-run partition ownership to active case roots."""

        next_receipts = dict(self._run_receipts)
        observed_partition_ids = {
            transferred.partition.partition_id
            for receipt in next_receipts.values()
            for transferred in receipt.transferred_partitions
        }
        for run_id, order_ids, partition in assignments:
            order_values = tuple(order_id.value for order_id in order_ids)
            if (
                not order_values
                or order_values != tuple(sorted(set(order_values)))
                or any(value not in self._active for value in order_values)
            ):
                raise CaseAccumulatorError("search_run_transfer_case_missing")
            if partition.partition_id in observed_partition_ids:
                raise CaseAccumulatorError("search_run_transfer_duplicate")
            observed_partition_ids.add(partition.partition_id)
            prior = next_receipts.get(run_id.value)
            transferred = _TransferredRunPartition(
                order_values,
                (),
                partition,
            )
            if prior is None:
                next_receipts[run_id.value] = _RunReceipt(
                    None,
                    (),
                    None,
                    (transferred,),
                )
                continue
            next_receipts[run_id.value] = _RunReceipt(
                prior.binding_authenticator,
                prior.order_ids,
                prior.partition,
                tuple(
                    sorted(
                        (*prior.transferred_partitions, transferred),
                        key=lambda item: item.partition.partition_id,
                    )
                ),
            )
        self._run_receipts = next_receipts

    def _stage_replacement_candidate(
        self,
        *,
        active: dict[str, _ActiveEntry],
        authority_run_id: str,
        parent_order_id: OrderId | None,
        candidate: OrderSnapshot,
        interactions: dict[str, InteractionRecord],
        occurred_at: CanonicalTimestamp,
    ) -> tuple[str, _ActiveEntry]:
        candidate_order_id = candidate.order_id
        if candidate_order_id is None or candidate_order_id == parent_order_id:
            raise CaseAccumulatorError("replacement_link_identity")
        candidate_key = candidate_order_id.value
        if candidate_key in self._closed:
            raise CaseAccumulatorError("replacement_link_closed")
        for owner_key, owner in active.items():
            if (
                owner_key != candidate_key
                and candidate.snapshot_id.value in owner.snapshots
            ):
                raise CaseAccumulatorError("replacement_snapshot_owner_conflict")
        current = active.get(candidate_key)
        if current is None:
            linked_case = SalesCreditCase(
                order_id=candidate_order_id,
                interaction_ids=tuple(
                    item.interaction_id
                    for item in sorted(
                        interactions.values(),
                        key=lambda item: item.interaction_id.value,
                    )
                ),
                snapshot_ids=(candidate.snapshot_id,),
                evidence_ids=(),
                evaluation_ids=(),
                attribution=AttributionClassification.UNKNOWN,
                order_value_status=OrderValueStatus.UNKNOWN,
                placed_value=None,
                workflow_state=WorkflowState.AWAITING_SOURCE_REVIEW,
                replacement_parent=parent_order_id,
                manager_outcome=None,
                created_at=occurred_at,
                updated_at=occurred_at,
                active_note=None,
            )
            return (
                candidate_key,
                _ActiveEntry(
                    linked_case,
                    dict(interactions),
                    {candidate.snapshot_id.value: candidate},
                    {},
                    {},
                    (authority_run_id,),
                    tuple(sorted(interactions)),
                    None,
                    None,
                    linked_case.workflow_state,
                ),
            )
        current_time = (
            current.case.updated_at.epoch_seconds,
            current.case.updated_at.nanosecond,
        )
        link_time = (occurred_at.epoch_seconds, occurred_at.nanosecond)
        if link_time < current_time:
            raise CaseAccumulatorError("replacement_link_time_regression")
        if (
            current.case.manager_outcome is not None
            or current.case.workflow_state in _TERMINAL_SYSTEM_STATES
        ):
            raise CaseAccumulatorError("replacement_link_resolved")
        if (
            parent_order_id is not None
            and current.case.replacement_parent not in {None, parent_order_id}
        ):
            raise CaseAccumulatorError("replacement_parent_conflict")
        linked_interactions = dict(current.interactions)
        for key, item in interactions.items():
            if key in linked_interactions and linked_interactions[key] != item:
                raise CaseAccumulatorError("replacement_link_interaction_conflict")
            linked_interactions[key] = item
        linked_snapshots = dict(current.snapshots)
        snapshot_key = candidate.snapshot_id.value
        if snapshot_key in linked_snapshots and linked_snapshots[snapshot_key] != candidate:
            raise CaseAccumulatorError("replacement_link_snapshot_conflict")
        linked_snapshots[snapshot_key] = candidate
        linked_case = replace(
            current.case,
            interaction_ids=tuple(
                item.interaction_id
                for item in sorted(
                    linked_interactions.values(),
                    key=lambda item: item.interaction_id.value,
                )
            ),
            snapshot_ids=tuple(
                item.snapshot_id
                for item in sorted(
                    linked_snapshots.values(),
                    key=lambda item: item.snapshot_id.value,
                )
            ),
            replacement_parent=current.case.replacement_parent or parent_order_id,
            updated_at=occurred_at,
        )
        return (
            candidate_key,
            _ActiveEntry(
                linked_case,
                linked_interactions,
                linked_snapshots,
                dict(current.evidence),
                dict(current.evaluations),
                tuple(sorted({*current.search_run_ids, authority_run_id})),
                tuple(
                    sorted(
                        {
                            *current.authorized_interaction_ids,
                            *interactions,
                        }
                    )
                ),
                current.latest_evaluation_id,
                current.latest_evaluation_at,
                current.system_workflow_before_close,
            ),
        )

    def apply_mutation(
        self,
        mutation: CaseMutation,
    ) -> CaseMutationResult:
        if type(mutation) is CaseMutation and mutation.discovery_run is not None:
            raise CaseAccumulatorError("discovery_coordinator_required")
        if type(mutation) is not CaseMutation:
            raise CaseAccumulatorError("mutation_type")
        runs = tuple(
            run
            for run in (mutation.discovery_run, mutation.replacement_run)
            if run is not None
        )
        canonical = _mutation_bytes(mutation)
        digest = self._digest(canonical)
        with self._lock:
            closed_replay = self._existing_closed_replay(
                mutation.command_id,
                canonical,
                digest,
            )
            if closed_replay is not None:
                if type(closed_replay) is not CaseMutationResult:
                    raise CaseAccumulatorError("receipt_kind_conflict")
                return closed_replay
            claims = self._claim_search_runs(runs)
            try:
                return self._apply_mutation(mutation, discovery_batch=None)
            except Exception:
                self._rollback_search_claims(claims)
                raise

    def _apply_mutation(
        self,
        mutation: CaseMutation,
        *,
        discovery_batch: SearchEvaluationBatch | None,
        discovery_case_mutations: tuple[CaseMutation, ...] | None = None,
        run_partition: SearchRunOwnerPartition | None = None,
    ) -> CaseMutationResult:
        if type(mutation) is not CaseMutation:
            raise CaseAccumulatorError("mutation_type")
        canonical = _mutation_bytes(mutation)
        digest = self._digest(canonical)
        with self._lock:
            closed_replay = self._existing_closed_replay(
                mutation.command_id,
                canonical,
                digest,
            )
            if closed_replay is not None:
                if type(closed_replay) is not CaseMutationResult:
                    raise CaseAccumulatorError("receipt_kind_conflict")
                return closed_replay
            prior_receipt = self._existing_receipt(
                mutation.command_id,
                canonical,
            )
            if prior_receipt is not None:
                if type(prior_receipt.result) is not CaseMutationResult:
                    raise CaseAccumulatorError("receipt_kind_conflict")
                return replace(
                    prior_receipt.result,
                    replayed=True,
                )
            next_run_receipts = dict(self._run_receipts)
            if mutation.discovery_run is not None:
                if discovery_batch is None:
                    command_ids = (mutation.command_id.value,)
                    order_ids = (mutation.order_id.value,)
                else:
                    receipt_mutations = (
                        discovery_batch.mutations
                        if discovery_case_mutations is None
                        else discovery_case_mutations
                    )
                    command_ids = tuple(
                        item.command_id.value for item in receipt_mutations
                    )
                    order_ids = tuple(
                        item.order_id.value for item in receipt_mutations
                    )
                self._bind_run_receipt(
                    next_run_receipts,
                    run=mutation.discovery_run,
                    command_ids=command_ids,
                    order_ids=order_ids,
                    partition=run_partition,
                )
            replacement_result_by_order = (
                {
                    item.order_id: item
                    for item in mutation.evaluation.replacement.candidate_results
                }
                if mutation.evaluation is not None
                else {}
            )
            if mutation.replacement_run is not None:
                replacement_order_ids = [mutation.order_id.value]
                for candidate_input in mutation.replacement_candidates:
                    candidate_order_id = candidate_input.snapshot.order_id
                    result = replacement_result_by_order.get(candidate_order_id)
                    if (
                        candidate_order_id is not None
                        and result is not None
                        and result.status
                        in {
                            ReplacementStatus.EXACT_RELEVANT,
                            ReplacementStatus.POSSIBLE_REVIEW,
                        }
                        and candidate_order_id.value not in self._closed
                    ):
                        replacement_order_ids.append(candidate_order_id.value)
                self._bind_run_receipt(
                    next_run_receipts,
                    run=mutation.replacement_run,
                    command_ids=(mutation.command_id.value,),
                    order_ids=tuple(replacement_order_ids),
                )
            if mutation.order_id.value in self._closed:
                raise CaseAccumulatorError("closed_case_mutation")
            current = self._active.get(mutation.order_id.value)
            if current is None:
                if mutation.replacement_run is not None:
                    raise CaseAccumulatorError("replacement_parent_case_missing")
                if mutation.evaluation is not None:
                    if mutation.discovery_run is None:
                        raise CaseAccumulatorError("discovery_authority_missing")
                    if discovery_batch is None:
                        if mutation.discovery_run.result.order_ids != (
                            mutation.order_id,
                        ):
                            raise CaseAccumulatorError("discovery_batch_required")
                    elif mutation.discovery_run != discovery_batch.run:
                        raise CaseAccumulatorError("discovery_batch_authority")
                case = SalesCreditCase(
                    order_id=mutation.order_id,
                    interaction_ids=(),
                    snapshot_ids=(),
                    evidence_ids=(),
                    evaluation_ids=(),
                    attribution=AttributionClassification.UNKNOWN,
                    order_value_status=OrderValueStatus.UNKNOWN,
                    placed_value=None,
                    workflow_state=WorkflowState.AWAITING_SOURCE_REVIEW,
                    replacement_parent=None,
                    manager_outcome=None,
                    created_at=mutation.occurred_at,
                    updated_at=mutation.occurred_at,
                    active_note=mutation.active_note,
                )
                current = _ActiveEntry(
                    case,
                    {},
                    {},
                    {},
                    {},
                    (),
                    (),
                    None,
                    None,
                    case.workflow_state,
                )
            current_time = (
                current.case.updated_at.epoch_seconds,
                current.case.updated_at.nanosecond,
            )
            mutation_time = (
                mutation.occurred_at.epoch_seconds,
                mutation.occurred_at.nanosecond,
            )
            if mutation_time < current_time:
                raise CaseAccumulatorError("mutation_time_regression")
            if current.case.manager_outcome is not None:
                raise CaseAccumulatorError("resolved_case_mutation")
            if current.case.replacement_parent is not None:
                raise CaseAccumulatorError("replacement_child_pending_parent")
            if current.case.workflow_state in _TERMINAL_SYSTEM_STATES:
                raise CaseAccumulatorError("terminal_case_mutation")
            if (
                mutation.evaluation is not None
                and mutation.discovery_run is None
                and not current.search_run_ids
            ):
                raise CaseAccumulatorError("discovery_authority_missing")
            if mutation.evaluation is None and current.latest_evaluation_id is not None:
                classification_fact_added = any(
                    item.interaction_id.value not in current.interactions
                    for item in mutation.interactions
                ) or any(
                    item.snapshot_id.value not in current.snapshots
                    for item in mutation.snapshots
                ) or any(
                    item.evidence_id.value not in current.evidence
                    for item in mutation.evidence
                )
                if classification_fact_added:
                    raise CaseAccumulatorError("evaluation_required_for_facts")
            new_interaction_ids = {
                item.interaction_id.value
                for item in mutation.interactions
                if item.interaction_id.value not in current.interactions
            }
            if (
                new_interaction_ids
                and (current.search_run_ids or current.snapshots or current.evaluations)
                and mutation.discovery_run is None
            ):
                raise CaseAccumulatorError("discovery_interaction_unauthorized")
            if mutation.evaluation is not None:
                proposed_interaction_ids = {
                    *current.interactions,
                    *(item.interaction_id.value for item in mutation.interactions),
                }
                authorized_interaction_ids = {
                    *current.authorized_interaction_ids,
                    *(
                        ()
                        if mutation.discovery_run is None
                        else (
                            item.interaction_id.value
                            for item in mutation.interactions
                        )
                    ),
                }
                if not proposed_interaction_ids.issubset(
                    authorized_interaction_ids
                ):
                    raise CaseAccumulatorError("discovery_interaction_unauthorized")

            for owner_key, owner in self._active.items():
                if owner_key == mutation.order_id.value:
                    continue
                for item in mutation.interactions:
                    prior = owner.interactions.get(item.interaction_id.value)
                    if prior is not None and prior != item:
                        raise CaseAccumulatorError("interaction_conflict")
                for item in mutation.evidence:
                    prior = owner.evidence.get(item.evidence_id.value)
                    if prior is not None:
                        raise CaseAccumulatorError(
                            "evidence_conflict"
                            if prior != item
                            else "evidence_owner_conflict"
                        )
                if mutation.evaluation is not None:
                    prior = owner.evaluations.get(
                        mutation.evaluation.evaluation_id.value
                    )
                    if prior is not None:
                        raise CaseAccumulatorError(
                            "evaluation_conflict"
                            if prior != mutation.evaluation
                            else "evaluation_owner_conflict"
                        )

            interactions = dict(current.interactions)
            snapshots = dict(current.snapshots)
            evidence = dict(current.evidence)
            evaluations = dict(current.evaluations)
            for snapshot in mutation.snapshots:
                for owner_key, owner in self._active.items():
                    if (
                        owner_key != mutation.order_id.value
                        and snapshot.snapshot_id.value in owner.snapshots
                    ):
                        raise CaseAccumulatorError("snapshot_owner_conflict")
            for items, destination, identity, code in (
                (mutation.interactions, interactions, "interaction_id", "interaction_conflict"),
                (mutation.snapshots, snapshots, "snapshot_id", "snapshot_conflict"),
                (mutation.evidence, evidence, "evidence_id", "evidence_conflict"),
            ):
                for item in items:
                    key = getattr(item, identity).value
                    if key in destination and destination[key] != item:
                        raise CaseAccumulatorError(code)
                    destination[key] = item
            if mutation.evaluation is not None:
                key = mutation.evaluation.evaluation_id.value
                if key in evaluations and evaluations[key] != mutation.evaluation:
                    raise CaseAccumulatorError("evaluation_conflict")
            for item in evidence.values():
                interaction = interactions.get(item.interaction_id.value)
                if interaction is None:
                    raise CaseAccumulatorError("evidence_interaction_missing")
                contact_present = (
                    interaction.email is not None
                    if item.identifier_kind.value == "EMAIL"
                    else interaction.phone is not None
                )
                if (
                    not contact_present
                    or item.matched_identifier_ref
                    != _expected_evidence_identifier_ref(item)
                ):
                    raise CaseAccumulatorError("evidence_identifier_mismatch")
            for item in evaluations.values():
                snapshot = snapshots.get(item.snapshot_id.value)
                if snapshot is None:
                    raise CaseAccumulatorError("evaluation_snapshot_missing")
                if snapshot.order_id is not None and snapshot.order_id != item.order_id:
                    raise CaseAccumulatorError("evaluation_snapshot_order")
            latest_evaluation_id = current.latest_evaluation_id
            latest_evaluation_at = current.latest_evaluation_at
            linked_replacements: list[tuple[str, _ActiveEntry]] = []
            if mutation.evaluation is not None:
                evaluation_snapshot = snapshots.get(
                    mutation.evaluation.snapshot_id.value
                )
                if evaluation_snapshot is None:
                    raise CaseAccumulatorError("evaluation_snapshot_missing")
                evaluation_capture = (
                    evaluation_snapshot.captured_at.epoch_seconds,
                    evaluation_snapshot.captured_at.nanosecond,
                )
                if any(
                    (
                        prior.captured_at.epoch_seconds,
                        prior.captured_at.nanosecond,
                    ) > evaluation_capture
                    for prior in snapshots.values()
                ):
                    raise CaseAccumulatorError("evaluation_snapshot_stale")
                recompute_failed = False
                recomputed: SalesCreditEvaluation | None = None
                try:
                    recomputed = evaluate_sales_credit(
                        evaluation_id=mutation.evaluation.evaluation_id,
                        expected_order_id=mutation.order_id,
                        snapshot=evaluation_snapshot,
                        evaluated_at=mutation.occurred_at,
                        known_other_reps=KNOWN_OTHER_REP_CATALOG,
                        interactions=tuple(
                            sorted(
                                interactions.values(),
                                key=lambda item: item.interaction_id.value,
                            )
                        ),
                        evidence_events=tuple(
                            sorted(
                                evidence.values(),
                                key=lambda item: item.evidence_id.value,
                            )
                        ),
                        replacement_run=mutation.replacement_run,
                        replacement_candidates=mutation.replacement_candidates,
                        prior_snapshots=tuple(
                            sorted(
                                (
                                    item
                                    for item in snapshots.values()
                                    if item.snapshot_id
                                    != evaluation_snapshot.snapshot_id
                                ),
                                key=lambda item: (
                                    item.captured_at.epoch_seconds,
                                    item.captured_at.nanosecond,
                                    item.snapshot_id.value,
                                ),
                            )
                        ),
                    )
                except Exception:
                    recompute_failed = True
                if recompute_failed or recomputed is None:
                    raise CaseAccumulatorError("evaluation_recompute_failed") from None
                if recomputed.canonical_bytes() != mutation.evaluation.canonical_bytes():
                    raise CaseAccumulatorError("evaluation_material_mismatch")
                evaluations[key] = mutation.evaluation
                latest_evaluation_id = key
                latest_evaluation_at = mutation.occurred_at
                attribution = mutation.evaluation.attribution.classification
                value_status = mutation.evaluation.value.status
                placed_value = mutation.evaluation.value.placed_value
                workflow = mutation.evaluation.workflow_state
            else:
                attribution = current.case.attribution
                value_status = current.case.order_value_status
                placed_value = current.case.placed_value
                workflow = current.case.workflow_state
            next_case = replace(
                current.case,
                interaction_ids=tuple(
                    item.interaction_id
                    for item in sorted(
                        interactions.values(),
                        key=lambda item: item.interaction_id.value,
                    )
                ),
                snapshot_ids=tuple(
                    item.snapshot_id
                    for item in sorted(
                        snapshots.values(),
                        key=lambda item: item.snapshot_id.value,
                    )
                ),
                evidence_ids=tuple(
                    item.evidence_id
                    for item in sorted(
                        evidence.values(),
                        key=lambda item: item.evidence_id.value,
                    )
                ),
                evaluation_ids=tuple(
                    item.evaluation_id
                    for item in sorted(
                        evaluations.values(),
                        key=lambda item: item.evaluation_id.value,
                    )
                ),
                attribution=attribution,
                order_value_status=value_status,
                placed_value=placed_value,
                workflow_state=workflow,
                replacement_parent=current.case.replacement_parent,
                updated_at=mutation.occurred_at,
                active_note=mutation.active_note or current.case.active_note,
            )
            next_entry = _ActiveEntry(
                next_case,
                interactions,
                snapshots,
                evidence,
                evaluations,
                tuple(
                    sorted(
                        {
                            *current.search_run_ids,
                            *(
                                ()
                                if mutation.discovery_run is None
                                else (mutation.discovery_run.run_id.value,)
                            ),
                        }
                    )
                ),
                tuple(
                    sorted(
                        {
                            *current.authorized_interaction_ids,
                            *(
                                ()
                                if mutation.discovery_run is None
                                else (
                                    item.interaction_id.value
                                    for item in mutation.interactions
                                )
                            ),
                        }
                    )
                ),
                latest_evaluation_id,
                latest_evaluation_at,
                workflow,
            )
            public_result = CaseMutationResult(
                _accepted_case_state(next_case),
                False,
            )
            receipt = _Receipt(
                mutation.order_id,
                self._closure_authenticator(canonical),
                public_result,
            )
            next_active = dict(self._active)
            next_active[mutation.order_id.value] = next_entry
            for candidate_input in mutation.replacement_candidates:
                candidate = candidate_input.snapshot
                result = replacement_result_by_order.get(candidate.order_id)
                if result is None:
                    raise CaseAccumulatorError("replacement_result_missing")
                if result.status not in {
                    ReplacementStatus.EXACT_RELEVANT,
                    ReplacementStatus.POSSIBLE_REVIEW,
                }:
                    continue
                # A previously closed one-order case remains immutable.  The
                # parent still retains the verified candidate decision, but a
                # later replacement search must not reopen or duplicate the
                # candidate's closed case merely to add the relationship.
                if candidate.order_id.value in self._closed:
                    continue
                parent = (
                    mutation.order_id
                )
                linked_replacements.append(
                    self._stage_replacement_candidate(
                        active=next_active,
                        authority_run_id=mutation.replacement_run.run_id.value,
                        parent_order_id=parent,
                        candidate=candidate,
                        interactions={
                            item.interaction_id.value: item
                            for item in _discovery_interactions_for_order(
                                mutation.replacement_run,
                                candidate.order_id,
                            )
                        },
                        occurred_at=mutation.occurred_at,
                    )
                )
            for linked_key, linked_entry in linked_replacements:
                next_active[linked_key] = linked_entry
            next_receipts = dict(self._receipts)
            next_receipts[mutation.command_id.value] = receipt
            self._active = next_active
            self._receipts = next_receipts
            self._run_receipts = next_run_receipts
            return public_result

    def apply_discovery_batch(
        self,
        batch: SearchEvaluationBatch,
    ) -> tuple[CaseMutationResult, ...]:
        if type(batch) is not SearchEvaluationBatch:
            raise CaseAccumulatorError("search_batch_type")
        raise CaseAccumulatorError("discovery_coordinator_required")

    def _apply_scoped_discovery_batch(
        self,
        *,
        batch: SearchEvaluationBatch,
        case_mutations: tuple[CaseMutation, ...],
        partition: SearchRunOwnerPartition | None,
    ) -> tuple[CaseMutationResult, ...]:
        with self._lock:
            retired_results = tuple(
                self._existing_closed_replay(
                    mutation.command_id,
                    _mutation_bytes(mutation),
                    self._digest(_mutation_bytes(mutation)),
                )
                for mutation in case_mutations
            )
            if all(result is not None for result in retired_results):
                if any(
                    type(result) is not CaseMutationResult
                    for result in retired_results
                ):
                    raise CaseAccumulatorError("receipt_kind_conflict")
                return tuple(
                    result for result in retired_results if result is not None
                )
            prior_active = self._active
            prior_closed = self._closed
            prior_receipts = self._receipts
            prior_run_receipts = self._run_receipts
            try:
                return tuple(
                    self._apply_mutation(
                        mutation,
                        discovery_batch=batch,
                        discovery_case_mutations=case_mutations,
                        run_partition=partition,
                    )
                    for mutation in case_mutations
                )
            except Exception:
                self._active = prior_active
                self._closed = prior_closed
                self._receipts = prior_receipts
                self._run_receipts = prior_run_receipts
                raise

    def apply_manager_outcome(
        self,
        *,
        command_id: EvidenceId,
        order_id: OrderId,
        outcome: ManagerOutcome,
    ) -> OutcomeResult:
        if type(command_id) is not EvidenceId or type(order_id) is not OrderId:
            raise CaseAccumulatorError("outcome_identity")
        if type(outcome) is not ManagerOutcome:
            raise CaseAccumulatorError("outcome_type")
        document = {
            "command_id": command_id.value,
            "order_id": order_id.value,
            "outcome": outcome.to_dict(),
        }
        canonical = canonical_json_bytes(document, expected_members=set(document))
        outcome_document = outcome.to_dict()
        outcome_canonical = canonical_json_bytes(
            outcome_document,
            expected_members=set(outcome_document),
        )
        digest = self._digest(canonical)
        with self._lock:
            closed_replay = self._existing_closed_replay(
                command_id,
                canonical,
                digest,
            )
            if closed_replay is not None:
                if type(closed_replay) is not OutcomeResult:
                    raise CaseAccumulatorError("receipt_kind_conflict")
                return closed_replay
            receipt = self._existing_receipt(command_id, canonical)
            if receipt is not None:
                if type(receipt.result) is not OutcomeResult:
                    raise CaseAccumulatorError("receipt_kind_conflict")
                return replace(
                    receipt.result,
                    replayed=True,
                )
            closed_occurrence = self._closed_outcome_occurrences.get(
                self._closed_occurrence_key(outcome.occurrence_id)
            )
            if closed_occurrence is not None:
                if (
                    closed_occurrence.order_id != order_id
                    or not hmac.compare_digest(
                        closed_occurrence.material_authenticator,
                        self._closure_authenticator(outcome_canonical),
                    )
                ):
                    raise CaseAccumulatorError("outcome_occurrence_conflict")
                return replace(
                    closed_occurrence.result,
                    replayed=True,
                )
            entry = self._active.get(order_id.value)
            if entry is None:
                raise CaseAccumulatorError("outcome_case_missing")
            prior_occurrence = self._outcome_occurrences.get(
                outcome.occurrence_id.value
            )
            if prior_occurrence is not None:
                if prior_occurrence.order_id != order_id:
                    raise CaseAccumulatorError("outcome_occurrence_conflict")
                if prior_occurrence.canonical_bytes != outcome_canonical:
                    raise CaseAccumulatorError("outcome_occurrence_conflict")
                if entry.case.manager_outcome != outcome:
                    raise CaseAccumulatorError("outcome_occurrence_conflict")
                replay_result = replace(
                    prior_occurrence.result,
                    replayed=True,
                )
                self._receipts[command_id.value] = _Receipt(
                    order_id,
                    self._closure_authenticator(canonical),
                    replay_result,
                )
                return replay_result
            if entry.case.manager_outcome is not None:
                raise CaseAccumulatorError("outcome_already_recorded")
            if entry.case.replacement_parent is not None:
                raise CaseAccumulatorError("replacement_child_pending_parent")
            if entry.case.workflow_state not in _MANAGER_OUTCOME_STATES:
                raise CaseAccumulatorError("outcome_workflow_not_authorized")
            if entry.latest_evaluation_id is None:
                raise CaseAccumulatorError("outcome_evaluation_missing")
            authority = entry.evaluations.get(entry.latest_evaluation_id)
            if (
                authority is None
                or authority.workflow_state is not entry.case.workflow_state
            ):
                raise CaseAccumulatorError("outcome_evaluation_mismatch")
            if _replacement_window_holds_closure(entry, authority):
                raise CaseAccumulatorError("outcome_replacement_window_active")
            current_time = (
                entry.case.updated_at.epoch_seconds,
                entry.case.updated_at.nanosecond,
            )
            decision_time = (
                outcome.decided_at.epoch_seconds,
                outcome.decided_at.nanosecond,
            )
            outcome_time = (
                outcome.recorded_at.epoch_seconds,
                outcome.recorded_at.nanosecond,
            )
            if decision_time < current_time or outcome_time < current_time:
                raise CaseAccumulatorError("outcome_time_regression")
            next_case = replace(
                entry.case,
                manager_outcome=outcome,
                workflow_state=WorkflowState.CLOSED,
                updated_at=outcome.recorded_at,
            )
            self._active[order_id.value] = _ActiveEntry(
                next_case,
                entry.interactions,
                entry.snapshots,
                entry.evidence,
                entry.evaluations,
                entry.search_run_ids,
                entry.authorized_interaction_ids,
                entry.latest_evaluation_id,
                entry.latest_evaluation_at,
                entry.system_workflow_before_close,
            )
            public_result = OutcomeResult(
                _accepted_case_state(next_case),
                False,
            )
            self._receipts[command_id.value] = _Receipt(
                order_id,
                self._closure_authenticator(canonical),
                public_result,
            )
            self._outcome_occurrences[outcome.occurrence_id.value] = (
                _OutcomeOccurrenceReceipt(
                    order_id,
                    outcome_canonical,
                    public_result,
                )
            )
            return public_result

    def close_and_minimize(
        self,
        *,
        command_id: EvidenceId,
        order_id: OrderId,
        closed_at: CanonicalTimestamp,
        reasons: tuple[SalesCreditReason, ...],
    ) -> ClosureResult:
        if type(command_id) is not EvidenceId or type(order_id) is not OrderId:
            raise CaseAccumulatorError("closure_identity")
        if type(closed_at) is not CanonicalTimestamp:
            raise CaseAccumulatorError("closure_timestamp")
        if type(reasons) is not tuple or any(
            type(item) is not SalesCreditReason for item in reasons
        ):
            raise CaseAccumulatorError("closure_reasons")
        ordered_reasons = tuple(sorted(set(reasons), key=lambda item: item.value))
        if reasons != ordered_reasons:
            raise CaseAccumulatorError("closure_reasons_order_or_duplicate")
        document = {
            "closed_at": closed_at.value,
            "command_id": command_id.value,
            "order_id": order_id.value,
            "reasons": [item.value for item in ordered_reasons],
        }
        canonical = canonical_json_bytes(document, expected_members=set(document))
        digest = self._digest(canonical)
        with self._lock:
            closed_replay = self._existing_closed_replay(
                command_id,
                canonical,
                digest,
            )
            if closed_replay is not None:
                if type(closed_replay) is not ClosureResult:
                    raise CaseAccumulatorError("receipt_kind_conflict")
                return closed_replay
            receipt = self._existing_receipt(command_id, canonical)
            if receipt is not None:
                raise CaseAccumulatorError("receipt_kind_conflict")
            entry = self._active.get(order_id.value)
            if entry is None:
                raise CaseAccumulatorError("closure_case_missing")
            if entry.case.replacement_parent is not None:
                raise CaseAccumulatorError("replacement_child_pending_parent")
            if entry.latest_evaluation_id is None:
                raise CaseAccumulatorError("closure_evaluation_missing")
            authority = entry.evaluations.get(entry.latest_evaluation_id)
            if authority is None:
                raise CaseAccumulatorError("closure_evaluation_missing")
            if authority.workflow_state is not entry.system_workflow_before_close:
                raise CaseAccumulatorError("closure_evaluation_mismatch")
            if _replacement_window_holds_closure(entry, authority):
                raise CaseAccumulatorError("closure_replacement_window_active")
            if ordered_reasons != authority.reasons:
                raise CaseAccumulatorError("closure_reason_mismatch")
            projection = build_closure_projection(
                case=entry.case,
                interactions=tuple(
                    sorted(
                        entry.interactions.values(),
                        key=lambda item: item.interaction_id.value,
                    )
                ),
                evidence=tuple(
                    sorted(
                        entry.evidence.values(),
                        key=lambda item: item.evidence_id.value,
                    )
                ),
                evaluation=authority,
                closed_at=closed_at,
            )
            next_active = dict(self._active)
            next_receipts = dict(self._receipts)
            next_closed_authenticators = dict(
                self._closed_command_authenticators
            )
            for key, prior in tuple(next_receipts.items()):
                if prior.order_id == order_id:
                    next_closed_authenticators[self._closed_command_key(key)] = (
                        _ClosedCommandAuthenticator(
                            order_id=order_id,
                            authenticator=prior.material_authenticator,
                            result=prior.result,
                        )
                    )
                    del next_receipts[key]
            next_run_receipts = dict(self._run_receipts)
            retired_run_receipts: dict[str, _RunReceipt] = {}
            sealed_run_receipts: dict[str, _RunReceipt] = {}
            transferred_partition_refs: list[_ClosedRunPartitionRef] = []
            transferred_partition_orders: dict[str, tuple[str, ...]] = {}
            case_run_ids: list[str] = []
            for key, run_receipt in tuple(next_run_receipts.items()):
                base_order = order_id.value in run_receipt.order_ids
                matched_transfers = tuple(
                    item
                    for item in run_receipt.transferred_partitions
                    if order_id.value in item.active_order_ids
                )
                if not base_order and not matched_transfers:
                    continue
                if base_order:
                    case_run_ids.append(key)
                remaining_orders = tuple(
                    item
                    for item in run_receipt.order_ids
                    if item != order_id.value
                )
                remaining_transfers: list[_TransferredRunPartition] = []
                for item in run_receipt.transferred_partitions:
                    if item not in matched_transfers:
                        remaining_transfers.append(item)
                        continue
                    active_orders = tuple(
                        value
                        for value in item.active_order_ids
                        if value != order_id.value
                    )
                    closed_orders = tuple(
                        sorted({*item.closed_order_ids, order_id.value})
                    )
                    if active_orders:
                        remaining_transfers.append(
                            _TransferredRunPartition(
                                active_orders,
                                closed_orders,
                                item.partition,
                            )
                        )
                    else:
                        transferred_partition_refs.append(
                            _ClosedRunPartitionRef(
                                RunId(key),
                                item.partition,
                            )
                        )
                        transferred_partition_orders[
                            item.partition.partition_id
                        ] = closed_orders
                if remaining_orders or remaining_transfers:
                    next_run_receipts[key] = _RunReceipt(
                        run_receipt.binding_authenticator,
                        remaining_orders,
                        (
                            run_receipt.partition
                            if remaining_orders
                            else None
                        ),
                        tuple(remaining_transfers),
                    )
                else:
                    del next_run_receipts[key]
                if base_order and not remaining_orders:
                    if run_receipt.partition is None:
                        if run_receipt.binding_authenticator is None:
                            raise CaseAccumulatorError(
                                "search_run_transfer_binding"
                            )
                        retired_run_receipts[key] = run_receipt
                    else:
                        sealed_run_receipts[key] = run_receipt
            next_closed = dict(self._closed)
            next_closed[order_id.value] = projection
            del next_active[order_id.value]
            next_occurrences = dict(self._outcome_occurrences)
            next_closed_occurrences = dict(self._closed_outcome_occurrences)
            for occurrence_id, occurrence in tuple(
                next_occurrences.items()
            ):
                if occurrence.order_id == order_id:
                    next_closed_occurrences[
                        self._closed_occurrence_key(occurrence_id)
                    ] = _ClosedOutcomeOccurrenceReceipt(
                        order_id=order_id,
                        material_authenticator=self._closure_authenticator(
                            occurrence.canonical_bytes
                        ),
                        result=occurrence.result,
                    )
                    del next_occurrences[occurrence_id]
            public_result = ClosureResult(projection, digest, False)
            next_closed_authenticators[self._closed_command_key(command_id)] = (
                _ClosedCommandAuthenticator(
                    order_id=order_id,
                    authenticator=self._closure_authenticator(canonical),
                    result=public_result,
                )
            )
            next_closed_order_runs = dict(self._closed_order_run_ids)
            if case_run_ids:
                next_closed_order_runs[order_id.value] = tuple(
                    sorted(
                        {
                            *next_closed_order_runs.get(order_id.value, ()),
                            *case_run_ids,
                        }
                    )
                )
            next_closed_run_receipts = dict(self._closed_run_receipt_ids)
            next_closed_run_partitions = dict(self._closed_run_partitions)
            for reference in transferred_partition_refs:
                for related_order in transferred_partition_orders[
                    reference.partition.partition_id
                ]:
                    if related_order not in next_closed:
                        continue
                    references = {
                        item.partition.partition_id: item
                        for item in next_closed_run_partitions.get(
                            related_order,
                            (),
                        )
                    }
                    references[reference.partition.partition_id] = reference
                    next_closed_run_partitions[related_order] = tuple(
                        references[item] for item in sorted(references)
                    )
            if retired_run_receipts:
                try:
                    receipt_id = (
                        self._search_run_authority.allocate_closure_receipt_id(
                            owner=self._search_run_owner
                        )
                    )
                    self._search_run_authority.retire_runs(
                        tuple(
                            (
                                RunId(key),
                                retired_run_receipts[key].binding_authenticator,
                                False,
                            )
                            for key in sorted(retired_run_receipts)
                        ),
                        owner=self._search_run_owner,
                        receipt_id=receipt_id,
                    )
                except SearchRunAuthorityError:
                    raise CaseAccumulatorError(
                        "search_run_authority_retire"
                    ) from None
                retired_keys = set(retired_run_receipts)
                related_closed_orders = tuple(
                    key
                    for key, run_ids in next_closed_order_runs.items()
                    if not retired_keys.isdisjoint(run_ids)
                    and key in next_closed
                )
                for key in related_closed_orders:
                    next_closed_run_receipts[key] = tuple(
                        sorted(
                            {
                                *next_closed_run_receipts.get(key, ()),
                                receipt_id,
                            }
                        )
                    )
                    remaining_run_ids = tuple(
                        run_id
                        for run_id in next_closed_order_runs[key]
                        if run_id not in retired_keys
                    )
                    if remaining_run_ids:
                        next_closed_order_runs[key] = remaining_run_ids
                    else:
                        del next_closed_order_runs[key]
            if sealed_run_receipts:
                sealed_keys = set(sealed_run_receipts)
                related_closed_orders = tuple(
                    key
                    for key, run_ids in next_closed_order_runs.items()
                    if not sealed_keys.isdisjoint(run_ids)
                    and key in next_closed
                )
                for key in related_closed_orders:
                    references = {
                        reference.partition.partition_id: reference
                        for reference in next_closed_run_partitions.get(key, ())
                    }
                    for run_id in sorted(
                        sealed_keys.intersection(next_closed_order_runs[key])
                    ):
                        partition = sealed_run_receipts[run_id].partition
                        if partition is None:
                            raise CaseAccumulatorError(
                                "search_run_partition_missing"
                            )
                        reference = _ClosedRunPartitionRef(
                            RunId(run_id),
                            partition,
                        )
                        references[partition.partition_id] = reference
                    next_closed_run_partitions[key] = tuple(
                        references[item] for item in sorted(references)
                    )
                    remaining_run_ids = tuple(
                        run_id
                        for run_id in next_closed_order_runs[key]
                        if run_id not in sealed_keys
                    )
                    if remaining_run_ids:
                        next_closed_order_runs[key] = remaining_run_ids
                    else:
                        del next_closed_order_runs[key]
            self._active = next_active
            self._closed = next_closed
            self._receipts = next_receipts
            self._run_receipts = next_run_receipts
            self._outcome_occurrences = next_occurrences
            self._closed_outcome_occurrences = next_closed_occurrences
            self._closed_order_run_ids = next_closed_order_runs
            self._closed_run_receipt_ids = next_closed_run_receipts
            self._closed_run_partitions = next_closed_run_partitions
            self._closed_command_authenticators = next_closed_authenticators
            return public_result

    def purge(self, *, now: CanonicalTimestamp) -> int:
        if type(now) is not CanonicalTimestamp:
            raise CaseAccumulatorError("purge_timestamp")
        with self._lock:
            removed_orders = {
                key
                for key, projection in self._closed.items()
                if purge_eligible(closed_at=projection.record.closed_at, now=now)
            }
            if not removed_orders:
                return 0
            next_active = dict(self._active)
            next_closed = dict(self._closed)
            next_receipts = dict(self._receipts)
            next_run_receipts = dict(self._run_receipts)
            next_occurrences = dict(self._outcome_occurrences)
            next_closed_occurrences = dict(self._closed_outcome_occurrences)
            next_closed_order_runs = dict(self._closed_order_run_ids)
            next_closed_run_receipts = dict(self._closed_run_receipt_ids)
            next_closed_run_partitions = dict(self._closed_run_partitions)
            next_closed_authenticators = dict(
                self._closed_command_authenticators
            )
            for run_id, receipt in tuple(next_run_receipts.items()):
                retained_transfers = tuple(
                    _TransferredRunPartition(
                        item.active_order_ids,
                        tuple(
                            value
                            for value in item.closed_order_ids
                            if value not in removed_orders
                        ),
                        item.partition,
                    )
                    for item in receipt.transferred_partitions
                )
                if retained_transfers != receipt.transferred_partitions:
                    next_run_receipts[run_id] = _RunReceipt(
                        receipt.binding_authenticator,
                        receipt.order_ids,
                        receipt.partition,
                        retained_transfers,
                    )
            released_run_ids: set[str] = set()
            released_partitions: dict[str, _ClosedRunPartitionRef] = {}
            for key, child in tuple(next_active.items()):
                parent = child.case.replacement_parent
                if parent is None or parent.value not in removed_orders:
                    continue
                parent_run_ids = set(
                    next_closed_order_runs.get(parent.value, ())
                )
                detached_run_ids = tuple(
                    run_id
                    for run_id in child.search_run_ids
                    if run_id in parent_run_ids
                )
                next_active[key] = _ActiveEntry(
                    replace(child.case, replacement_parent=None),
                    child.interactions,
                    child.snapshots,
                    child.evidence,
                    child.evaluations,
                    tuple(
                        run_id
                        for run_id in child.search_run_ids
                        if run_id not in detached_run_ids
                    ),
                    child.authorized_interaction_ids,
                    child.latest_evaluation_id,
                    child.latest_evaluation_at,
                    child.system_workflow_before_close,
                )
                for run_id in detached_run_ids:
                    run_receipt = next_run_receipts.get(run_id)
                    if run_receipt is None or key not in run_receipt.order_ids:
                        raise CaseAccumulatorError("search_run_receipt_link")
                    remaining_orders = tuple(
                        item for item in run_receipt.order_ids if item != key
                    )
                    if remaining_orders:
                        next_run_receipts[run_id] = _RunReceipt(
                            run_receipt.binding_authenticator,
                            remaining_orders,
                            run_receipt.partition,
                            run_receipt.transferred_partitions,
                        )
                    else:
                        del next_run_receipts[run_id]
                        if run_receipt.partition is None:
                            released_run_ids.add(run_id)
                        else:
                            released_partitions[
                                run_receipt.partition.partition_id
                            ] = _ClosedRunPartitionRef(
                                RunId(run_id),
                                run_receipt.partition,
                            )
            for key in removed_orders:
                del next_closed[key]
                next_closed_run_receipts.pop(key, None)
                next_closed_run_partitions.pop(key, None)
                next_closed_order_runs.pop(key, None)
            if released_run_ids:
                for key, run_ids in tuple(next_closed_order_runs.items()):
                    retained = tuple(
                        run_id
                        for run_id in run_ids
                        if run_id not in released_run_ids
                    )
                    if retained:
                        next_closed_order_runs[key] = retained
                    else:
                        del next_closed_order_runs[key]
            for key, receipt in tuple(next_receipts.items()):
                if receipt.order_id.value in removed_orders:
                    del next_receipts[key]
            for key, receipt in tuple(next_occurrences.items()):
                if receipt.order_id.value in removed_orders:
                    del next_occurrences[key]
            for key, occurrence in tuple(
                next_closed_occurrences.items()
            ):
                if occurrence.order_id.value in removed_orders:
                    del next_closed_occurrences[key]
            for key, receipt in tuple(next_closed_authenticators.items()):
                if receipt.order_id.value in removed_orders:
                    del next_closed_authenticators[key]
            removed_receipt_ids = {
                receipt_id
                for key in removed_orders
                for receipt_id in self._closed_run_receipt_ids.get(key, ())
            }
            surviving_receipt_ids = {
                receipt_id
                for receipt_ids in next_closed_run_receipts.values()
                for receipt_id in receipt_ids
            }
            purge_receipt_ids = tuple(
                sorted(removed_receipt_ids - surviving_receipt_ids)
            )
            removed_partition_refs = {
                reference.partition.partition_id: reference
                for key in removed_orders
                for reference in self._closed_run_partitions.get(key, ())
            }
            surviving_partition_ids = {
                reference.partition.partition_id
                for references in next_closed_run_partitions.values()
                for reference in references
            }
            for partition_id, reference in removed_partition_refs.items():
                if partition_id not in surviving_partition_ids:
                    released_partitions[partition_id] = reference
            try:
                for run_id in sorted(released_run_ids):
                    self._search_run_authority.release_run(
                        RunId(run_id),
                        owner=self._search_run_owner,
                    )
                for partition_id in sorted(released_partitions):
                    reference = released_partitions[partition_id]
                    self._search_run_authority.release_partition(
                        reference.run_id,
                        reference.partition,
                        owner=self._search_run_owner,
                    )
                for receipt_id in purge_receipt_ids:
                    self._search_run_authority.purge_retired(
                        receipt_id=receipt_id,
                        owner=self._search_run_owner,
                    )
            except SearchRunAuthorityError:
                raise CaseAccumulatorError("search_run_authority_purge") from None
            self._active = next_active
            self._closed = next_closed
            self._receipts = next_receipts
            self._run_receipts = next_run_receipts
            self._outcome_occurrences = next_occurrences
            self._closed_outcome_occurrences = next_closed_occurrences
            self._closed_order_run_ids = next_closed_order_runs
            self._closed_run_receipt_ids = next_closed_run_receipts
            self._closed_run_partitions = next_closed_run_partitions
            self._closed_command_authenticators = next_closed_authenticators
            return len(removed_orders)

    def get_active_case(self, order_id: OrderId) -> SalesCreditCase | None:
        if type(order_id) is not OrderId:
            raise CaseAccumulatorError("lookup_order_id")
        with self._lock:
            entry = self._active.get(order_id.value)
            return None if entry is None else entry.case

    def get_closed_projection(self, order_id: OrderId) -> ClosureProjection | None:
        if type(order_id) is not OrderId:
            raise CaseAccumulatorError("lookup_order_id")
        with self._lock:
            return self._closed.get(order_id.value)

    @property
    def active_case_count(self) -> int:
        with self._lock:
            return len(self._active)

    @property
    def closed_case_count(self) -> int:
        with self._lock:
            return len(self._closed)

    def _retained_partition_for_run(
        self,
        run_id: RunId,
    ) -> SearchRunOwnerPartition | None:
        with self._lock:
            partitions: dict[str, SearchRunOwnerPartition] = {}
            receipt = self._run_receipts.get(run_id.value)
            if receipt is not None and receipt.partition is not None:
                partitions[receipt.partition.partition_id] = receipt.partition
            for references in self._closed_run_partitions.values():
                for reference in references:
                    if reference.run_id == run_id:
                        partitions[
                            reference.partition.partition_id
                        ] = reference.partition
            if len(partitions) > 1:
                raise CaseAccumulatorError("search_run_partition_conflict")
            return next(iter(partitions.values()), None)


class InMemorySalesCreditState:
    """Supported M2 composition sharing one natural-key authority."""

    __slots__ = (
        "_lock",
        "case_accumulator",
        "no_order_ledger",
        "search_run_authority",
    )

    def __init__(
        self,
        *,
        digest_function: Callable[[bytes], str] = _default_digest,
        search_run_authority: InMemorySearchRunAuthority | None = None,
    ) -> None:
        authority = search_run_authority or InMemorySearchRunAuthority()
        if type(authority) is not InMemorySearchRunAuthority:
            raise CaseAccumulatorError("search_run_authority")
        self._lock = RLock()
        self.search_run_authority = authority
        self.case_accumulator = InMemoryCaseAccumulator(
            digest_function=digest_function,
            search_run_authority=authority,
        )
        self.no_order_ledger = InMemoryNoOrderStateLedger(
            search_run_authority=authority,
            coordinator_required=True,
        )

    def apply_no_order_run(
        self,
        run: OrderSearchRun,
    ) -> PostEvaluationCommitResult:
        """Apply one truly empty native search through the atomic coordinator."""

        if type(run) is not OrderSearchRun:
            raise CaseAccumulatorError("search_batch_run")
        return self.apply_discovery_batch(
            SearchEvaluationBatch(run, ()),
            candidate_evaluations=(),
        ).no_order_result

    def apply_discovery_batch(
        self,
        batch: SearchEvaluationBatch,
        *,
        candidate_evaluations: tuple[
            SelectorOwnedCandidateEvaluation, ...
        ],
    ) -> CoordinatedDiscoveryResult:
        if type(batch) is not SearchEvaluationBatch:
            raise CaseAccumulatorError("search_batch_type")
        if type(candidate_evaluations) is not tuple or any(
            type(item) is not SelectorOwnedCandidateEvaluation
            for item in candidate_evaluations
        ):
            raise CaseAccumulatorError("candidate_evaluations_shape")
        with self._lock, self.case_accumulator._lock, self.no_order_ledger._lock:
            was_sealed = self.search_run_authority.is_sealed_run(
                batch.run.run_id
            )
            claim: SearchRunAuthorityClaim | None = None
            try:
                if was_sealed:
                    self.search_run_authority.verify_sealed(batch.run)
                else:
                    claim = self.search_run_authority.claim(
                        batch.run,
                        owner=self.case_accumulator._search_run_owner,
                    )
            except SearchRunAuthorityError as error:
                if error.code == "search_run_material_conflict":
                    raise CaseAccumulatorError(
                        "search_run_material_conflict"
                    ) from None
                if error.code == "search_run_retired":
                    raise CaseAccumulatorError("search_run_retired") from None
                raise CaseAccumulatorError("search_run_authority") from error
            stage: PostEvaluationNoOrderStage | None = None
            case_partition: SearchRunOwnerPartition | None = None
            seal: SearchRunSeal | None = None
            transfer_partitions: list[SearchRunOwnerPartition] = []
            partition_transfers: list[SearchRunPartitionTransfer] = []
            case_checkpoint = (
                self.case_accumulator._active,
                self.case_accumulator._closed,
                self.case_accumulator._receipts,
                self.case_accumulator._run_receipts,
                self.case_accumulator._outcome_occurrences,
                self.case_accumulator._closed_outcome_occurrences,
                self.case_accumulator._closed_order_run_ids,
                self.case_accumulator._closed_run_receipt_ids,
                self.case_accumulator._closed_run_partitions,
                self.case_accumulator._closed_command_authenticators,
            )
            try:
                stage = self.no_order_ledger.stage_post_evaluation_run(
                    batch.run,
                    candidate_evaluations,
                    authority_claim=claim,
                )
                scope_by_order = {
                    scope.order_id: scope for scope in stage.candidate_scopes
                }
                if tuple(scope_by_order) != batch.run.result.order_ids:
                    raise CaseAccumulatorError("search_batch_scope_parity")
                required_orders = tuple(
                    scope.order_id
                    for scope in stage.candidate_scopes
                    if scope.positive_interaction_ids
                    or scope.preserved_interaction_ids
                )
                if tuple(
                    mutation.order_id for mutation in batch.mutations
                ) != required_orders:
                    raise CaseAccumulatorError("search_batch_scope_order_parity")
                interactions_by_id = {
                    item.interaction_id: item for item in batch.run.interactions
                }
                selector_snapshots: dict[OrderId, OrderSnapshot] = {}
                for candidate in candidate_evaluations:
                    order_id = candidate.evaluation.order_id
                    prior = selector_snapshots.setdefault(
                        order_id,
                        candidate.snapshot,
                    )
                    if prior != candidate.snapshot:
                        raise CaseAccumulatorError(
                            "search_batch_selector_snapshot_conflict"
                        )
                for mutation in batch.mutations:
                    scope = scope_by_order[mutation.order_id]
                    expected_ids = (
                        scope.positive_interaction_ids
                        if scope.positive_interaction_ids
                        else scope.preserved_interaction_ids
                    )
                    expected_interactions = tuple(
                        interactions_by_id[item] for item in expected_ids
                    )
                    if mutation.interactions != expected_interactions:
                        raise CaseAccumulatorError(
                            "search_batch_interaction_scope"
                        )
                    selector_snapshot = selector_snapshots.get(
                        mutation.order_id
                    )
                    if (
                        selector_snapshot is None
                        or mutation.evaluation is None
                        or mutation.evaluation.snapshot_id
                        != selector_snapshot.snapshot_id
                        or not any(
                            snapshot == selector_snapshot
                            for snapshot in mutation.snapshots
                        )
                    ):
                        raise CaseAccumulatorError(
                            "search_batch_snapshot_binding"
                        )

                if was_sealed:
                    if batch.mutations:
                        case_partition = (
                            self.case_accumulator._retained_partition_for_run(
                                batch.run.run_id
                            )
                        )
                        if case_partition is None:
                            raise CaseAccumulatorError(
                                "coordinated_replay_case_partition_missing"
                            )
                    case_results = (
                        self.case_accumulator._apply_scoped_discovery_batch(
                            batch=batch,
                            case_mutations=batch.mutations,
                            partition=case_partition,
                        )
                    )
                    if any(not item.replayed for item in case_results):
                        raise CaseAccumulatorError(
                            "coordinated_replay_case_missing"
                        )
                    no_order_result = (
                        self.no_order_ledger.commit_post_evaluation_stage(
                            stage,
                            seal=None,
                        )
                    )
                    if not no_order_result.replayed:
                        raise CaseAccumulatorError(
                            "coordinated_replay_ledger_missing"
                        )
                    return CoordinatedDiscoveryResult(
                        case_results,
                        no_order_result,
                    )

                if claim is None:
                    raise CaseAccumulatorError("search_run_authority")
                if batch.mutations:
                    case_partition = self.search_run_authority.new_partition(
                        owner=self.case_accumulator._search_run_owner,
                        kind=SearchRunPartitionKind.POSITIVE_CASE_ACTIVE,
                    )
                case_results = (
                    self.case_accumulator._apply_scoped_discovery_batch(
                        batch=batch,
                        case_mutations=batch.mutations,
                        partition=case_partition,
                    )
                )
                transfer_assignments: list[
                    tuple[RunId, tuple[OrderId, ...], SearchRunOwnerPartition]
                ] = []
                for transfer in stage.positive_transfers:
                    incoming = tuple(
                        self.search_run_authority.new_partition(
                            owner=self.case_accumulator._search_run_owner,
                            kind=SearchRunPartitionKind.POSITIVE_CASE_ACTIVE,
                        )
                        for _ in transfer.roots
                    )
                    transfer_partitions.extend(incoming)
                    transfer_assignments.extend(
                        (
                            transfer.source_run_id,
                            root.target_order_ids,
                            partition,
                        )
                        for root, partition in zip(
                            transfer.roots,
                            incoming,
                            strict=True,
                        )
                    )
                    partition_transfers.append(
                        self.search_run_authority.stage_partition_transfer(
                            transfer.source_run_id,
                            outgoing_partition=transfer.outgoing_partition,
                            incoming_partitions=incoming,
                            retain_outgoing=transfer.retain_outgoing,
                        )
                    )
                if transfer_assignments:
                    self.case_accumulator._bind_transferred_run_partitions(
                        tuple(transfer_assignments)
                    )

                partitions: tuple[SearchRunOwnerPartition, ...] = ()
                if case_partition is not None:
                    partitions = (case_partition,)
                if stage.required_partition is not None:
                    partitions = (*partitions, stage.required_partition)
                if not partitions:
                    raise CaseAccumulatorError(
                        "coordinated_run_partition_missing"
                    )
                seal = self.search_run_authority.seal_run(
                    (claim,),
                    partitions=partitions,
                )
                no_order_result = (
                    self.no_order_ledger.commit_post_evaluation_stage(
                        stage,
                        seal=seal,
                        partition_transfers=tuple(partition_transfers),
                    )
                )
                self.search_run_authority.commit_seal(seal)
                seal = None
                for transfer in partition_transfers:
                    self.search_run_authority.commit_partition_transfer(
                        transfer
                    )
                partition_transfers.clear()
                self.no_order_ledger.finalize_post_evaluation_stage(stage)
                return CoordinatedDiscoveryResult(
                    case_results,
                    no_order_result,
                )
            except Exception:
                (
                    self.case_accumulator._active,
                    self.case_accumulator._closed,
                    self.case_accumulator._receipts,
                    self.case_accumulator._run_receipts,
                    self.case_accumulator._outcome_occurrences,
                    self.case_accumulator._closed_outcome_occurrences,
                    self.case_accumulator._closed_order_run_ids,
                    self.case_accumulator._closed_run_receipt_ids,
                    self.case_accumulator._closed_run_partitions,
                    self.case_accumulator._closed_command_authenticators,
                ) = case_checkpoint
                for transfer in reversed(partition_transfers):
                    try:
                        self.search_run_authority.rollback_partition_transfer(
                            transfer
                        )
                    except SearchRunAuthorityError:
                        pass
                if seal is not None:
                    try:
                        self.search_run_authority.rollback_seal(seal)
                    except SearchRunAuthorityError:
                        pass
                if stage is not None:
                    try:
                        self.no_order_ledger.rollback_post_evaluation_stage(stage)
                    except NoOrderLedgerError:
                        pass
                if case_partition is not None and not was_sealed:
                    try:
                        self.search_run_authority.discard_partition(
                            case_partition,
                            owner=self.case_accumulator._search_run_owner,
                        )
                    except SearchRunAuthorityError:
                        pass
                for partition in transfer_partitions:
                    try:
                        self.search_run_authority.discard_partition(
                            partition,
                            owner=self.case_accumulator._search_run_owner,
                        )
                    except SearchRunAuthorityError:
                        pass
                if claim is not None:
                    try:
                        self.search_run_authority.rollback(claim)
                    except SearchRunAuthorityError:
                        pass
                raise

    def __repr__(self) -> str:
        return "InMemorySalesCreditState(<redacted>)"


__all__ = [
    "AcceptedCaseState",
    "CaseAccumulatorError",
    "CaseMutation",
    "CaseMutationResult",
    "ClosureResult",
    "CoordinatedDiscoveryResult",
    "InMemoryCaseAccumulator",
    "InMemorySalesCreditState",
    "OutcomeResult",
    "SearchEvaluationBatch",
]
