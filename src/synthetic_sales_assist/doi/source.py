"""Pure synthetic DOI queue ingestion and in-memory run-control reducers.

This module has no file, network, portal, persistence, timer, or background-worker capability.
Inputs are complete in-memory synthetic queue images.  The run coordinator exists only to make
the binding replay and serialization semantics executable before Milestone 4 persistence.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from threading import RLock
from typing import ClassVar, cast

from synthetic_sales_assist.doi.identities import (
    AcceptedCommandId,
    CommandReceiptId,
    ExtractionOccurrenceId,
    RunInvocationId,
    RunWorkItemId,
    SourceBatchId,
    SourceIdentityId,
    SourceImportAttemptId,
    SourceRowRefId,
)
from synthetic_sales_assist.domain.canonical import (
    CanonicalHashCollision,
    HashBinding,
    canonical_json_bytes,
    compare_retained_canonical_bytes,
    domain_hash,
)
from synthetic_sales_assist.domain.identities import (
    EvidenceId,
    InteractionId,
    OrderId,
    RepId,
    RunId,
)
from synthetic_sales_assist.domain.normalization import (
    NormalizationError,
    ascii_four_trim,
    normalize_order_number,
)
from synthetic_sales_assist.domain.numeric import NonNegativeCount, PositiveOrdinal
from synthetic_sales_assist.domain.records import ReasonSet
from synthetic_sales_assist.domain.registries import load_doi_registries
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.domain.tokens import ImmutableStrEnum
from synthetic_sales_assist.safety.content import (
    ProhibitedCategory,
    scan_payload,
)


SOURCE_QUEUE_SCHEMA_VERSION = "synthetic-doi-queue-v0.1"
SOURCE_MAPPING_VERSION = "synthetic-doi-queue-mapping/v1"
SOURCE_IDENTITY_POLICY_VERSION = "doi-source-identity/v1"
ORDER_NUMBER_POLICY_VERSION = "doi-synthetic-order-number/v1"
RUN_SCHEMA_VERSION = "doi-run/v1"
SOURCE_ATTEMPT_SCHEMA_VERSION = "doi-source-import-attempt/v1"
SOURCE_ANCHORS = ("ORDER_NUMBER", "ASSIGNED_REP")
TARGET_ASSIGNEE = "TARGET_REP"

_ASSIGNEE = re.compile(r"\A[A-Za-z][A-Za-z0-9_]{0,63}\Z", re.ASCII)
_REVISION = re.compile(r"\A[A-Z0-9][A-Z0-9_.-]{0,63}\Z", re.ASCII)
_ASCII_UPPER = str.maketrans("abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
_SPECIFIC_SOURCE_FAILURES = frozenset({"RC-002", "RC-009", "RC-089", "RC-091"})


class DOISourceError(ValueError):
    """A non-reflecting source/run validation or conflict error."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"DOI source operation rejected: {code}")


class RunControlConflict(DOISourceError):
    """A replay, state, predecessor, or serialization conflict."""


class RunType(ImmutableStrEnum):
    RUN_DOI_REVIEW = "RUN_DOI_REVIEW"
    RECHECK_ORDER = "RECHECK_ORDER"
    RECHECK_DEDUPE_ORDER = "RECHECK_DEDUPE_ORDER"


class RunStatus(ImmutableStrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_EXCEPTIONS = "COMPLETED_WITH_EXCEPTIONS"
    FAILED = "FAILED"


class RunWorkOrigin(ImmutableStrEnum):
    SOURCE_IMPORT = "SOURCE_IMPORT"
    ORDER_RECHECK = "ORDER_RECHECK"
    DEDUPE_RECHECK = "DEDUPE_RECHECK"


class SourceImportAttemptOutcome(ImmutableStrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class SourceImportAttemptState(ImmutableStrEnum):
    STARTED = "STARTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class SourceChangeState(ImmutableStrEnum):
    UNCHANGED = "UNCHANGED"
    CHANGED = "CHANGED"
    UNPROVED = "UNPROVED"


class SourceCoherenceState(ImmutableStrEnum):
    COHERENT = "COHERENT"
    INCOHERENT = "INCOHERENT"


class SourceBatchStatus(ImmutableStrEnum):
    READY = "READY"


class StagedOrderStatus(ImmutableStrEnum):
    READY = "READY"


class RunTerminalResult(ImmutableStrEnum):
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_EXCEPTIONS = "COMPLETED_WITH_EXCEPTIONS"
    FAILED = "FAILED"


class SourceAttemptEventKind(ImmutableStrEnum):
    SOURCE_IMPORT_STARTED = "SOURCE_IMPORT_STARTED"
    SOURCE_IMPORT_SUCCEEDED = "SOURCE_IMPORT_SUCCEEDED"
    SOURCE_IMPORT_FAILED = "SOURCE_IMPORT_FAILED"
    SOURCE_IMPORT_ABORTED = "SOURCE_IMPORT_ABORTED"


class RunEventKind(ImmutableStrEnum):
    RUN_STARTED = "RUN_STARTED"
    RUN_TERMINAL = "RUN_TERMINAL"


class SourceRejectionOutcome(ImmutableStrEnum):
    ASSIGNEE_CONFLICT = "ASSIGNEE_CONFLICT"


class RunWorkDispositionKind(ImmutableStrEnum):
    SUCCESSFUL_EVALUATION = "SUCCESSFUL_EVALUATION"
    ORDER_EXCEPTION = "ORDER_EXCEPTION"
    BLOCKED_ORDER = "BLOCKED_ORDER"


class AcceptedActionCommandKind(ImmutableStrEnum):
    FINALIZE_FAILED_SOURCE_IMPORT_NO_RETRY = (
        "FINALIZE_FAILED_SOURCE_IMPORT_NO_RETRY"
    )


class SourceImportResultKind(ImmutableStrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class SyntheticQueueTab(ImmutableStrEnum):
    MONDAY = "MONDAY"
    WEDNESDAY = "WEDNESDAY"
    FRIDAY = "FRIDAY"


class RunControlOperation(ImmutableStrEnum):
    EXTRACTION_RESERVED = "EXTRACTION_RESERVED"
    PRE_EXTRACTION_RULES_UNAVAILABLE = "PRE_EXTRACTION_RULES_UNAVAILABLE"


def _reason_set(*codes: str) -> ReasonSet:
    registries = load_doi_registries()
    refs = tuple(sorted((registries.reason_ref(code) for code in codes), key=lambda ref: ref.code))
    return ReasonSet(refs)


def _binding_dict(binding: HashBinding) -> dict[str, str]:
    return {"domain": binding.domain, "sha256": binding.sha256}


def _hash_record(record: object, *, domain: str) -> HashBinding:
    to_dict = getattr(record, "to_dict", None)
    if not callable(to_dict):
        raise DOISourceError("hash_record_shape")
    value = to_dict()
    if type(value) is not dict:
        raise DOISourceError("hash_record_shape")
    return domain_hash(domain, canonical_json_bytes(value, expected_members=set(value)))


def _canonical_record_bytes(record: object) -> bytes:
    to_dict = getattr(record, "to_dict", None)
    if not callable(to_dict):
        raise DOISourceError("canonical_record_shape")
    value = to_dict()
    if type(value) is not dict:
        raise DOISourceError("canonical_record_shape")
    return canonical_json_bytes(value, expected_members=set(value))


def normalize_synthetic_order_number(value: object) -> OrderId:
    """Normalize a synthetic wrapper while applying the shared numeric-core contract.

    Plain numeric source cells are intentionally rejected: executable order identities must
    remain inside the reserved ``SYN-ORDER-*`` namespace even in transient fixtures.
    """

    if type(value) is OrderId:
        return value
    if type(value) is not str:
        raise DOISourceError("source_order_number")
    candidate = ascii_four_trim(value)
    prefix = "SYN-ORDER-"
    if not candidate.startswith(prefix):
        raise DOISourceError("source_order_number")
    try:
        numeric_core = normalize_order_number(candidate[len(prefix) :])
        return OrderId(prefix + numeric_core)
    except (NormalizationError, ValueError):
        raise DOISourceError("source_order_number") from None


def classify_assignee(value: object) -> str | None:
    """Return one uppercase ASCII scalar, or ``None`` for unrecognized input."""

    if type(value) is not str:
        return None
    candidate = ascii_four_trim(value)
    if not candidate.isascii() or _ASSIGNEE.fullmatch(candidate) is None:
        return None
    return candidate.translate(_ASCII_UPPER)


@dataclass(frozen=True, slots=True, repr=False)
class SyntheticQueueRow:
    """One transient in-memory queue row; raw cells are never copied to result records."""

    order_number: object = field(repr=False, compare=False)
    assignee: object = field(repr=False, compare=False)
    source_ref_id: SourceRowRefId

    def __post_init__(self) -> None:
        if type(self.source_ref_id) is not SourceRowRefId:
            raise DOISourceError("source_row_reference")
        order_scan_value = (
            self.order_number.value
            if type(self.order_number) is OrderId
            else self.order_number
        )
        order_findings = scan_payload({"synthetic_source_cell": order_scan_value})
        allowed_invalid_synthetic_order = (
            type(self.order_number) is str
            and self.order_number.startswith("SYN-ORDER-")
            and all(
                item.category == ProhibitedCategory.NON_SYNTHETIC_IDENTITY
                for item in order_findings
            )
        )
        assignee_findings = scan_payload({"synthetic_source_cell": self.assignee})
        if (order_findings and not allowed_invalid_synthetic_order) or assignee_findings:
            raise DOISourceError("prohibited_source_cell")

    def __repr__(self) -> str:
        return "SyntheticQueueRow(<transient>)"

    def _fingerprint_value(self) -> dict[str, object]:
        try:
            order_value = normalize_synthetic_order_number(self.order_number).value
        except DOISourceError:
            order_value = "INVALID_ORDER_CELL"
        assignee = classify_assignee(self.assignee)
        if assignee == TARGET_ASSIGNEE:
            assignee_value = TARGET_ASSIGNEE
        elif assignee is None:
            assignee_value = "UNRECOGNIZED_ASSIGNEE_CELL"
        else:
            assignee_value = "OTHER_ASSIGNEE"
        return {
            "assignee_class": assignee_value,
            "order_number_class": order_value,
            "source_ref_id": self.source_ref_id.to_json_value(),
        }


@dataclass(frozen=True, slots=True, repr=False)
class SyntheticQueueImage:
    """One finite, ordered, transient source image used for before/after coherence."""

    source_identity_id: SourceIdentityId
    mapping_version: str
    structural_anchors: tuple[str, ...]
    finite_extent: NonNegativeCount
    rows: tuple[SyntheticQueueRow, ...] = field(repr=False)
    revision: str | None
    accessible: bool = True

    CONTENT_DOMAIN: ClassVar[str] = "doi-source-image-content/v1"

    def __post_init__(self) -> None:
        if (
            type(self.source_identity_id) is not SourceIdentityId
            or type(self.mapping_version) is not str
            or type(self.structural_anchors) is not tuple
            or any(type(anchor) is not str for anchor in self.structural_anchors)
            or type(self.finite_extent) is not NonNegativeCount
            or type(self.rows) is not tuple
            or any(type(row) is not SyntheticQueueRow for row in self.rows)
            or type(self.accessible) is not bool
        ):
            raise DOISourceError("source_image_shape")
        if self.revision is not None and (
            type(self.revision) is not str or _REVISION.fullmatch(self.revision) is None
        ):
            raise DOISourceError("source_revision")
        row_refs = tuple(row.source_ref_id.to_json_value() for row in self.rows)
        if len(row_refs) != len(set(row_refs)):
            raise DOISourceError("source_row_reference_duplicate")

    def content_binding(self) -> HashBinding:
        value = {
            "finite_extent": self.finite_extent.to_json_value(),
            "mapping_version": self.mapping_version,
            "rows": [row._fingerprint_value() for row in self.rows],
            "source_identity_id": self.source_identity_id.to_json_value(),
            "structural_anchors": list(self.structural_anchors),
        }
        return domain_hash(
            self.CONTENT_DOMAIN,
            canonical_json_bytes(value, expected_members=set(value)),
        )

    def __repr__(self) -> str:
        return "SyntheticQueueImage(<transient>)"


@dataclass(frozen=True, slots=True)
class DOISourceRowCounts:
    source_row_count: NonNegativeCount
    accepted_row_count: NonNegativeCount
    invalid_row_count: NonNegativeCount
    unrecognized_assignee_row_count: NonNegativeCount
    out_of_scope_row_count: NonNegativeCount
    conflict_row_count: NonNegativeCount
    staged_order_count: NonNegativeCount
    duplicate_row_count: NonNegativeCount
    rejected_order_count: NonNegativeCount

    def __post_init__(self) -> None:
        values = tuple(getattr(self, name) for name in self.__dataclass_fields__)
        if any(type(value) is not NonNegativeCount for value in values):
            raise DOISourceError("source_count_type")
        if self.source_row_count.value != (
            self.accepted_row_count.value
            + self.invalid_row_count.value
            + self.unrecognized_assignee_row_count.value
            + self.out_of_scope_row_count.value
            + self.conflict_row_count.value
        ):
            raise DOISourceError("source_row_count_equation")
        if self.staged_order_count.value > self.accepted_row_count.value:
            raise DOISourceError("staged_order_count_equation")
        if self.duplicate_row_count.value != (
            self.accepted_row_count.value - self.staged_order_count.value
        ):
            raise DOISourceError("duplicate_row_count_equation")

    @classmethod
    def zero(cls) -> DOISourceRowCounts:
        zero = NonNegativeCount(0)
        return cls(zero, zero, zero, zero, zero, zero, zero, zero, zero)

    def to_dict(self) -> dict[str, int]:
        return {
            name: cast(NonNegativeCount, getattr(self, name)).to_json_value()
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class DOIRunCounts:
    source_rows: DOISourceRowCounts
    source_attempt_count: NonNegativeCount
    work_item_count: NonNegativeCount
    disposition_subject_count: NonNegativeCount
    successful_evaluation_count: NonNegativeCount
    order_exception_count: NonNegativeCount
    blocked_order_count: NonNegativeCount
    portal_read_count: NonNegativeCount

    def __post_init__(self) -> None:
        if type(self.source_rows) is not DOISourceRowCounts:
            raise DOISourceError("run_count_type")
        rest = (
            self.source_attempt_count,
            self.work_item_count,
            self.disposition_subject_count,
            self.successful_evaluation_count,
            self.order_exception_count,
            self.blocked_order_count,
            self.portal_read_count,
        )
        if any(type(value) is not NonNegativeCount for value in rest):
            raise DOISourceError("run_count_type")
        if self.disposition_subject_count.value > self.work_item_count.value:
            raise DOISourceError("disposition_subset_equation")
        if self.disposition_subject_count.value != (
            self.successful_evaluation_count.value
            + self.order_exception_count.value
            + self.blocked_order_count.value
        ):
            raise DOISourceError("terminal_disposition_equation")
        if self.portal_read_count.value > self.work_item_count.value:
            raise DOISourceError("portal_read_count_equation")

    @classmethod
    def empty(cls, *, source_attempt_count: int = 0, work_item_count: int = 0) -> DOIRunCounts:
        zero = NonNegativeCount(0)
        return cls(
            source_rows=DOISourceRowCounts.zero(),
            source_attempt_count=NonNegativeCount(source_attempt_count),
            work_item_count=NonNegativeCount(work_item_count),
            disposition_subject_count=zero,
            successful_evaluation_count=zero,
            order_exception_count=zero,
            blocked_order_count=zero,
            portal_read_count=zero,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "blocked_order_count": self.blocked_order_count.to_json_value(),
            "disposition_subject_count": self.disposition_subject_count.to_json_value(),
            "order_exception_count": self.order_exception_count.to_json_value(),
            "portal_read_count": self.portal_read_count.to_json_value(),
            "source_attempt_count": self.source_attempt_count.to_json_value(),
            "source_rows": self.source_rows.to_dict(),
            "successful_evaluation_count": self.successful_evaluation_count.to_json_value(),
            "work_item_count": self.work_item_count.to_json_value(),
        }


@dataclass(frozen=True, slots=True)
class DOIStagedOrder:
    order_id: OrderId
    source_ref_ids: tuple[SourceRowRefId, ...]
    status: StagedOrderStatus
    reasons: ReasonSet
    raw_source_policy_version: str = ORDER_NUMBER_POLICY_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-staged-order/v1"

    def __post_init__(self) -> None:
        if (
            type(self.order_id) is not OrderId
            or type(self.source_ref_ids) is not tuple
            or not self.source_ref_ids
            or any(type(ref) is not SourceRowRefId for ref in self.source_ref_ids)
            or len(set(self.source_ref_ids)) != len(self.source_ref_ids)
            or type(self.status) is not StagedOrderStatus
            or self.status is not StagedOrderStatus.READY
            or type(self.reasons) is not ReasonSet
            or self.raw_source_policy_version != ORDER_NUMBER_POLICY_VERSION
        ):
            raise DOISourceError("staged_order_shape")
        expected = _reason_set("RC-006") if len(self.source_ref_ids) > 1 else ReasonSet()
        if self.reasons != expected:
            raise DOISourceError("staged_order_reason_set")

    def to_dict(self) -> dict[str, object]:
        return {
            "order_id": self.order_id.value,
            "raw_source_policy_version": self.raw_source_policy_version,
            "reasons": self.reasons.to_json_value(),
            "source_ref_ids": [ref.to_json_value() for ref in self.source_ref_ids],
            "status": self.status.value,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_record_bytes(self)

    def hash_binding(self) -> HashBinding:
        return _hash_record(self, domain=self.HASH_DOMAIN)


@dataclass(frozen=True, slots=True)
class DOIRejectedSourceRecord:
    order_id: OrderId
    target_source_ref_ids: tuple[SourceRowRefId, ...]
    outcome: SourceRejectionOutcome
    reasons: ReasonSet

    HASH_DOMAIN: ClassVar[str] = "doi-rejected-source-record/v1"

    def __post_init__(self) -> None:
        if (
            type(self.order_id) is not OrderId
            or type(self.target_source_ref_ids) is not tuple
            or not self.target_source_ref_ids
            or any(type(ref) is not SourceRowRefId for ref in self.target_source_ref_ids)
            or len(set(self.target_source_ref_ids)) != len(self.target_source_ref_ids)
            or type(self.outcome) is not SourceRejectionOutcome
            or self.outcome is not SourceRejectionOutcome.ASSIGNEE_CONFLICT
            or self.reasons != _reason_set("RC-008")
        ):
            raise DOISourceError("rejected_source_shape")

    def to_dict(self) -> dict[str, object]:
        return {
            "order_id": self.order_id.value,
            "outcome": self.outcome.value,
            "reasons": self.reasons.to_json_value(),
            "target_source_ref_ids": [ref.to_json_value() for ref in self.target_source_ref_ids],
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_record_bytes(self)

    def hash_binding(self) -> HashBinding:
        return _hash_record(self, domain=self.HASH_DOMAIN)


@dataclass(frozen=True, slots=True)
class DOISourceBatch:
    batch_id: SourceBatchId
    source_identity_id: SourceIdentityId
    mapping_version: str
    structural_anchors: tuple[str, ...]
    finite_extent: NonNegativeCount
    ordered_source_row_sha256: str
    coherence_state: SourceCoherenceState
    change_state: SourceChangeState
    status: SourceBatchStatus
    counts: DOISourceRowCounts
    staged_orders: tuple[DOIStagedOrder, ...]
    rejected_records: tuple[DOIRejectedSourceRecord, ...]
    aggregate_reasons: ReasonSet
    identity: HashBinding = field(init=False, repr=False)

    HASH_DOMAIN: ClassVar[str] = "doi-source-batch/v1"
    IDENTITY_DOMAIN: ClassVar[str] = "doi-source-batch-identity/v1"

    def __post_init__(self) -> None:
        if (
            type(self.batch_id) is not SourceBatchId
            or type(self.source_identity_id) is not SourceIdentityId
            or self.mapping_version != SOURCE_MAPPING_VERSION
            or self.structural_anchors != SOURCE_ANCHORS
            or type(self.finite_extent) is not NonNegativeCount
            or not re.fullmatch(r"[0-9a-f]{64}", self.ordered_source_row_sha256)
            or self.coherence_state is not SourceCoherenceState.COHERENT
            or self.change_state is not SourceChangeState.UNCHANGED
            or self.status is not SourceBatchStatus.READY
            or type(self.counts) is not DOISourceRowCounts
            or type(self.staged_orders) is not tuple
            or any(type(item) is not DOIStagedOrder for item in self.staged_orders)
            or type(self.rejected_records) is not tuple
            or any(type(item) is not DOIRejectedSourceRecord for item in self.rejected_records)
            or type(self.aggregate_reasons) is not ReasonSet
        ):
            raise DOISourceError("source_batch_shape")
        staged_ids = tuple(item.order_id.value for item in self.staged_orders)
        rejected_ids = tuple(item.order_id.value for item in self.rejected_records)
        if staged_ids != tuple(sorted(staged_ids)) or len(staged_ids) != len(set(staged_ids)):
            raise DOISourceError("source_batch_staged_order_set")
        if rejected_ids != tuple(sorted(rejected_ids)) or len(rejected_ids) != len(
            set(rejected_ids)
        ):
            raise DOISourceError("source_batch_rejected_order_set")
        if set(staged_ids) & set(rejected_ids):
            raise DOISourceError("source_batch_order_partition")
        if self.counts.staged_order_count.value != len(self.staged_orders):
            raise DOISourceError("source_batch_staged_count")
        if self.counts.rejected_order_count.value != len(self.rejected_records):
            raise DOISourceError("source_batch_rejected_count")
        expected_aggregate_codes: list[str] = []
        if self.counts.unrecognized_assignee_row_count.value:
            expected_aggregate_codes.append("RC-004")
        if self.counts.out_of_scope_row_count.value:
            expected_aggregate_codes.append("RC-005")
        if self.aggregate_reasons != _reason_set(*expected_aggregate_codes):
            raise DOISourceError("source_batch_aggregate_reasons")
        identity_value = {
            "counts": self.counts.to_dict(),
            "finite_extent": self.finite_extent.to_json_value(),
            "mapping_version": self.mapping_version,
            "order_number_policy_version": ORDER_NUMBER_POLICY_VERSION,
            "ordered_source_row_sha256": self.ordered_source_row_sha256,
            "rejected_records": [
                _binding_dict(item.hash_binding()) for item in self.rejected_records
            ],
            "source_identity_id": self.source_identity_id.to_json_value(),
            "staged_orders": [_binding_dict(item.hash_binding()) for item in self.staged_orders],
            "structural_anchors": list(self.structural_anchors),
        }
        object.__setattr__(
            self,
            "identity",
            domain_hash(
                self.IDENTITY_DOMAIN,
                canonical_json_bytes(identity_value, expected_members=set(identity_value)),
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "batch_id": self.batch_id.to_json_value(),
            "aggregate_reasons": self.aggregate_reasons.to_json_value(),
            "change_state": self.change_state.value,
            "coherence_state": self.coherence_state.value,
            "counts": self.counts.to_dict(),
            "finite_extent": self.finite_extent.to_json_value(),
            "identity": _binding_dict(self.identity),
            "mapping_version": self.mapping_version,
            "ordered_source_row_sha256": self.ordered_source_row_sha256,
            "rejected_records": [item.to_dict() for item in self.rejected_records],
            "source_identity_id": self.source_identity_id.to_json_value(),
            "staged_orders": [item.to_dict() for item in self.staged_orders],
            "status": self.status.value,
            "structural_anchors": list(self.structural_anchors),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_record_bytes(self)

    def hash_binding(self) -> HashBinding:
        return _hash_record(self, domain=self.HASH_DOMAIN)


@dataclass(frozen=True, slots=True)
class SourceImportResult:
    kind: SourceImportResultKind
    reasons: ReasonSet
    counts: DOISourceRowCounts
    batch: DOISourceBatch | None

    HASH_DOMAIN: ClassVar[str] = "doi-source-import-result/v1"

    def __post_init__(self) -> None:
        if (
            type(self.kind) is not SourceImportResultKind
            or type(self.reasons) is not ReasonSet
            or type(self.counts) is not DOISourceRowCounts
        ):
            raise DOISourceError("source_import_result_shape")
        if self.kind is SourceImportResultKind.SUCCEEDED:
            if type(self.batch) is not DOISourceBatch or self.reasons != ReasonSet():
                raise DOISourceError("source_import_success_shape")
        elif self.batch is not None or "RC-090" not in {
            reason.code for reason in self.reasons.reasons
        }:
            raise DOISourceError("source_import_failure_shape")

    def canonical_bytes(self) -> bytes:
        value = {
            "batch": None if self.batch is None else self.batch.to_dict(),
            "counts": self.counts.to_dict(),
            "kind": self.kind.value,
            "reasons": self.reasons.to_json_value(),
        }
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())


def _failed_import(*specific_codes: str, source_row_count: int = 0) -> SourceImportResult:
    if not specific_codes or any(code not in _SPECIFIC_SOURCE_FAILURES for code in specific_codes):
        raise DOISourceError("source_failure_reason")
    zero = NonNegativeCount(0)
    counts = DOISourceRowCounts(
        source_row_count=NonNegativeCount(source_row_count),
        accepted_row_count=zero,
        invalid_row_count=NonNegativeCount(source_row_count),
        unrecognized_assignee_row_count=zero,
        out_of_scope_row_count=zero,
        conflict_row_count=zero,
        staged_order_count=zero,
        duplicate_row_count=zero,
        rejected_order_count=zero,
    )
    return SourceImportResult(
        SourceImportResultKind.FAILED,
        _reason_set(*specific_codes, "RC-090"),
        counts,
        None,
    )


def ingest_synthetic_queue(
    before: SyntheticQueueImage,
    after: SyntheticQueueImage,
    *,
    candidate_batch_id: SourceBatchId,
) -> SourceImportResult:
    """Classify one coherent synthetic queue read with no external I/O or mutation."""

    if (
        type(before) is not SyntheticQueueImage
        or type(after) is not SyntheticQueueImage
        or type(candidate_batch_id) is not SourceBatchId
    ):
        raise DOISourceError("source_import_input")
    source_row_count = len(before.rows)
    if not before.accessible or not after.accessible:
        return _failed_import("RC-089", source_row_count=source_row_count)
    structural_valid = (
        before.source_identity_id == after.source_identity_id
        and before.mapping_version == SOURCE_MAPPING_VERSION
        and after.mapping_version == SOURCE_MAPPING_VERSION
        and before.structural_anchors == SOURCE_ANCHORS
        and after.structural_anchors == SOURCE_ANCHORS
        and before.finite_extent.value == len(before.rows)
        and after.finite_extent.value == len(after.rows)
    )
    if not structural_valid:
        return _failed_import("RC-002", source_row_count=source_row_count)

    before_binding = before.content_binding()
    after_binding = after.content_binding()
    revision_partition_valid = (before.revision is None) == (after.revision is None)
    revision_unchanged = before.revision is None or before.revision == after.revision
    exact_content_replay = compare_retained_canonical_bytes(
        before_binding.sha256,
        before_binding.canonical_bytes,
        after_binding.sha256,
        after_binding.canonical_bytes,
    )
    if not revision_partition_valid or not revision_unchanged or not exact_content_replay:
        return _failed_import("RC-009", source_row_count=source_row_count)

    normalized_rows: list[tuple[OrderId, str | None, SourceRowRefId]] = []
    for row in before.rows:
        try:
            order_id = normalize_synthetic_order_number(row.order_number)
        except DOISourceError:
            # RC-003 is deliberately unreachable in the locked v0.1 row schema.
            return _failed_import("RC-002", source_row_count=source_row_count)
        normalized_rows.append((order_id, classify_assignee(row.assignee), row.source_ref_id))

    recognized_by_order: dict[OrderId, list[tuple[str, SourceRowRefId]]] = {}
    unrecognized_count = 0
    for order_id, assignee, source_ref_id in normalized_rows:
        if assignee is None:
            unrecognized_count += 1
            continue
        recognized_by_order.setdefault(order_id, []).append((assignee, source_ref_id))

    staged: list[DOIStagedOrder] = []
    rejected: list[DOIRejectedSourceRecord] = []
    accepted_count = 0
    out_of_scope_count = 0
    conflict_count = 0
    duplicate_count = 0
    for order_id in sorted(recognized_by_order, key=lambda item: item.value):
        entries = recognized_by_order[order_id]
        target_refs = tuple(ref for assignee, ref in entries if assignee == TARGET_ASSIGNEE)
        other_entries = tuple(
            (assignee, ref)
            for assignee, ref in entries
            if assignee != TARGET_ASSIGNEE
        )
        if target_refs and other_entries:
            conflict_count += len(entries)
            rejected.append(
                DOIRejectedSourceRecord(
                    order_id=order_id,
                    target_source_ref_ids=target_refs,
                    outcome=SourceRejectionOutcome.ASSIGNEE_CONFLICT,
                    reasons=_reason_set("RC-008"),
                )
            )
        elif target_refs:
            accepted_count += len(target_refs)
            duplicate_count += len(target_refs) - 1
            staged.append(
                DOIStagedOrder(
                    order_id=order_id,
                    source_ref_ids=target_refs,
                    status=StagedOrderStatus.READY,
                    reasons=_reason_set("RC-006") if len(target_refs) > 1 else ReasonSet(),
                )
            )
        else:
            out_of_scope_count += len(other_entries)

    counts = DOISourceRowCounts(
        source_row_count=NonNegativeCount(source_row_count),
        accepted_row_count=NonNegativeCount(accepted_count),
        invalid_row_count=NonNegativeCount(0),
        unrecognized_assignee_row_count=NonNegativeCount(unrecognized_count),
        out_of_scope_row_count=NonNegativeCount(out_of_scope_count),
        conflict_row_count=NonNegativeCount(conflict_count),
        staged_order_count=NonNegativeCount(len(staged)),
        duplicate_row_count=NonNegativeCount(duplicate_count),
        rejected_order_count=NonNegativeCount(len(rejected)),
    )
    aggregate_codes: list[str] = []
    if unrecognized_count:
        aggregate_codes.append("RC-004")
    if out_of_scope_count:
        aggregate_codes.append("RC-005")
    batch = DOISourceBatch(
        batch_id=candidate_batch_id,
        source_identity_id=before.source_identity_id,
        mapping_version=SOURCE_MAPPING_VERSION,
        structural_anchors=SOURCE_ANCHORS,
        finite_extent=before.finite_extent,
        ordered_source_row_sha256=before_binding.sha256,
        coherence_state=SourceCoherenceState.COHERENT,
        change_state=SourceChangeState.UNCHANGED,
        status=SourceBatchStatus.READY,
        counts=counts,
        staged_orders=tuple(staged),
        rejected_records=tuple(rejected),
        aggregate_reasons=_reason_set(*aggregate_codes),
    )
    return SourceImportResult(SourceImportResultKind.SUCCEEDED, ReasonSet(), counts, batch)


class InMemorySourceBatchRegistry:
    """Collision-safe identity reuse for immutable in-memory source batches."""

    def __init__(self) -> None:
        self._by_digest: dict[str, DOISourceBatch] = {}

    def register(self, candidate: DOISourceBatch) -> DOISourceBatch:
        retained, _ = self.register_with_disposition(candidate)
        return retained

    def register_with_disposition(
        self,
        candidate: DOISourceBatch,
    ) -> tuple[DOISourceBatch, bool]:
        """Register one batch and report whether this call created its identity row."""

        if type(candidate) is not DOISourceBatch:
            raise DOISourceError("source_batch_candidate")
        retained = self._by_digest.get(candidate.identity.sha256)
        if retained is None:
            self._by_digest[candidate.identity.sha256] = candidate
            return candidate, True
        try:
            replay = compare_retained_canonical_bytes(
                retained.identity.sha256,
                retained.identity.canonical_bytes,
                candidate.identity.sha256,
                candidate.identity.canonical_bytes,
            )
        except CanonicalHashCollision:
            raise DOISourceError("RC-091") from None
        if not replay:
            raise DOISourceError("source_batch_registry_corrupt")
        return retained, False

    def by_id(self, batch_id: SourceBatchId) -> DOISourceBatch:
        """Return the one retained batch with this exact opaque identity."""

        if type(batch_id) is not SourceBatchId:
            raise DOISourceError("source_batch_id")
        matches = tuple(
            batch for batch in self._by_digest.values() if batch.batch_id == batch_id
        )
        if len(matches) != 1:
            raise DOISourceError("source_batch_missing_or_ambiguous")
        return matches[0]


@dataclass(frozen=True, slots=True)
class DOIRunWorkItem:
    work_item_id: RunWorkItemId
    run_id: RunId
    order_id: OrderId
    origin: RunWorkOrigin
    source_batch_id: SourceBatchId | None

    HASH_DOMAIN: ClassVar[str] = "doi-run-work-item/v1"

    def __post_init__(self) -> None:
        if (
            type(self.work_item_id) is not RunWorkItemId
            or type(self.run_id) is not RunId
            or type(self.order_id) is not OrderId
            or type(self.origin) is not RunWorkOrigin
        ):
            raise DOISourceError("run_work_item_shape")
        source_origin = self.origin is RunWorkOrigin.SOURCE_IMPORT
        if source_origin != (type(self.source_batch_id) is SourceBatchId):
            raise DOISourceError("run_work_item_source_binding")

    def to_dict(self) -> dict[str, object]:
        return {
            "order_id": self.order_id.value,
            "origin": self.origin.value,
            "run_id": self.run_id.value,
            "source_batch_id": (
                None if self.source_batch_id is None else self.source_batch_id.to_json_value()
            ),
            "work_item_id": self.work_item_id.to_json_value(),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_record_bytes(self)

    def hash_binding(self) -> HashBinding:
        return _hash_record(self, domain=self.HASH_DOMAIN)


_RUN_WORK_DISPOSITION_TOKEN = object()


@dataclass(frozen=True, slots=True, init=False, repr=False)
class DOIRunWorkDisposition:
    """One immutable terminal classification for one accepted run work item."""

    work_item_id: RunWorkItemId
    run_id: RunId
    work_item_sha256: str
    kind: RunWorkDispositionKind
    portal_read_performed: bool
    evidence: HashBinding
    occurred_at: CanonicalTimestamp
    reasons: ReasonSet

    HASH_DOMAIN: ClassVar[str] = "doi-run-work-disposition/v1"
    _EVIDENCE_DOMAINS: ClassVar[frozenset[str]] = frozenset(
        {
            "doi-evaluation-record/v1",
            "doi-lifecycle-event/v1",
        }
    )
    _EVIDENCE_MEMBERS: ClassVar[dict[str, frozenset[str]]] = {
        "doi-evaluation-record/v1": frozenset(
            {
                "append_transition",
                "append_transitions",
                "evaluation_id",
                "input_binding",
                "order_id",
                "output",
                "output_binding",
                "rule_pack",
                "rule_pack_binding",
                "run_id",
                "schema_version",
                "snapshot_id",
            }
        ),
        "doi-lifecycle-event/v1": frozenset(
            {
                "command",
                "event_id",
                "from_state",
                "occurred_at",
                "predecessor_sha256",
                "reasons",
                "schema_version",
                "sequence",
                "stream_id",
                "to_state",
                "transition_id",
                "transition_registry_version",
            }
        ),
    }

    def __new__(cls) -> DOIRunWorkDisposition:
        raise DOISourceError("run_work_disposition_factory_required")

    def __post_init__(self) -> None:
        if (
            type(self.work_item_id) is not RunWorkItemId
            or type(self.run_id) is not RunId
            or not re.fullmatch(r"[0-9a-f]{64}", self.work_item_sha256)
            or type(self.kind) is not RunWorkDispositionKind
            or type(self.portal_read_performed) is not bool
            or type(self.evidence) is not HashBinding
            or self.evidence.domain not in self._EVIDENCE_DOMAINS
            or type(self.occurred_at) is not CanonicalTimestamp
            or type(self.reasons) is not ReasonSet
        ):
            raise DOISourceError("run_work_disposition_shape")
        if self.kind is RunWorkDispositionKind.SUCCESSFUL_EVALUATION:
            if (
                not self.portal_read_performed
                or self.evidence.domain != "doi-evaluation-record/v1"
                or self.reasons != ReasonSet()
            ):
                raise DOISourceError("successful_disposition_evidence")
        elif self.reasons == ReasonSet():
            raise DOISourceError("exception_disposition_reason_required")
        try:
            evidence_value = json.loads(self.evidence.canonical_bytes.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise DOISourceError("run_work_disposition_evidence") from None
        if (
            type(evidence_value) is not dict
            or set(evidence_value) != self._EVIDENCE_MEMBERS[self.evidence.domain]
        ):
            raise DOISourceError("run_work_disposition_evidence")

    @classmethod
    def _create(
        cls,
        *,
        work_item: DOIRunWorkItem,
        kind: RunWorkDispositionKind,
        portal_read_performed: bool,
        evidence: HashBinding,
        occurred_at: CanonicalTimestamp,
        reasons: ReasonSet,
        factory_capability: object,
    ) -> DOIRunWorkDisposition:
        if factory_capability is not _RUN_WORK_DISPOSITION_TOKEN:
            raise DOISourceError("run_work_disposition_evidence")
        instance = object.__new__(cls)
        for name, value in (
            ("work_item_id", work_item.work_item_id),
            ("run_id", work_item.run_id),
            ("work_item_sha256", work_item.hash_binding().sha256),
            ("kind", kind),
            ("portal_read_performed", portal_read_performed),
            ("evidence", evidence),
            ("occurred_at", occurred_at),
            ("reasons", reasons),
        ):
            object.__setattr__(instance, name, value)
        instance.__post_init__()
        return instance

    @classmethod
    def successful_evaluation(
        cls,
        *,
        work_item: DOIRunWorkItem,
        evaluation: object,
        occurred_at: CanonicalTimestamp,
    ) -> DOIRunWorkDisposition:
        from synthetic_sales_assist.doi.models import DOIEvaluation

        if type(evaluation) is not DOIEvaluation:
            raise DOISourceError("run_work_disposition_evidence")
        return cls._create(
            work_item=work_item,
            kind=RunWorkDispositionKind.SUCCESSFUL_EVALUATION,
            portal_read_performed=True,
            evidence=evaluation.hash_binding(),
            occurred_at=occurred_at,
            reasons=ReasonSet(),
            factory_capability=_RUN_WORK_DISPOSITION_TOKEN,
        )

    @classmethod
    def exception_or_block(
        cls,
        *,
        work_item: DOIRunWorkItem,
        kind: RunWorkDispositionKind,
        portal_read_performed: bool,
        lifecycle_event: object,
        occurred_at: CanonicalTimestamp,
        reasons: ReasonSet,
    ) -> DOIRunWorkDisposition:
        from synthetic_sales_assist.doi.lifecycle import TransitionEvent

        if (
            kind not in {
                RunWorkDispositionKind.ORDER_EXCEPTION,
                RunWorkDispositionKind.BLOCKED_ORDER,
            }
            or type(lifecycle_event) is not TransitionEvent
        ):
            raise DOISourceError("run_work_disposition_evidence")
        return cls._create(
            work_item=work_item,
            kind=kind,
            portal_read_performed=portal_read_performed,
            evidence=lifecycle_event.hash_binding(),
            occurred_at=occurred_at,
            reasons=reasons,
            factory_capability=_RUN_WORK_DISPOSITION_TOKEN,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence": {
                "canonical_json": json.loads(self.evidence.canonical_bytes.decode("utf-8")),
                "domain": self.evidence.domain,
                "sha256": self.evidence.sha256,
            },
            "kind": self.kind.value,
            "occurred_at": self.occurred_at.value,
            "portal_read_performed": self.portal_read_performed,
            "reasons": self.reasons.to_json_value(),
            "run_id": self.run_id.value,
            "work_item_id": self.work_item_id.to_json_value(),
            "work_item_sha256": self.work_item_sha256,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_record_bytes(self)

    def hash_binding(self) -> HashBinding:
        return _hash_record(self, domain=self.HASH_DOMAIN)

    def __repr__(self) -> str:
        return "DOIRunWorkDisposition(<closed>)"


@dataclass(frozen=True, slots=True)
class DOIRun:
    run_id: RunId
    invocation_id: RunInvocationId
    run_type: RunType
    status: RunStatus
    started_at: CanonicalTimestamp
    completed_at: CanonicalTimestamp | None
    purge_eligible_at: CanonicalTimestamp | None
    source_batch_id: SourceBatchId | None
    recheck_order_id: OrderId | None
    counts: DOIRunCounts
    terminal_reasons: ReasonSet
    schema_version: str = RUN_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-run/v1"

    def __post_init__(self) -> None:
        if (
            type(self.run_id) is not RunId
            or type(self.invocation_id) is not RunInvocationId
            or type(self.run_type) is not RunType
            or type(self.status) is not RunStatus
            or type(self.started_at) is not CanonicalTimestamp
            or type(self.counts) is not DOIRunCounts
            or type(self.terminal_reasons) is not ReasonSet
            or self.schema_version != RUN_SCHEMA_VERSION
        ):
            raise DOISourceError("run_shape")
        review = self.run_type is RunType.RUN_DOI_REVIEW
        if review != (self.recheck_order_id is None):
            raise DOISourceError("run_type_binding")
        if not review and type(self.recheck_order_id) is not OrderId:
            raise DOISourceError("run_type_binding")
        terminal = self.status is not RunStatus.IN_PROGRESS
        if terminal != (type(self.completed_at) is CanonicalTimestamp):
            raise DOISourceError("run_completion_partition")
        if terminal != (type(self.purge_eligible_at) is CanonicalTimestamp):
            raise DOISourceError("run_purge_partition")
        if terminal and self.purge_eligible_at != _run_purge_deadline(
            cast(CanonicalTimestamp, self.completed_at)
        ):
            raise DOISourceError("run_purge_deadline")
        if not terminal and self.terminal_reasons != ReasonSet():
            raise DOISourceError("run_terminal_reason_partition")
        if self.status is RunStatus.COMPLETED and (
            self.counts.order_exception_count.value or self.counts.blocked_order_count.value
        ):
            raise DOISourceError("run_completed_count_result")
        if self.status is RunStatus.COMPLETED_WITH_EXCEPTIONS and not (
            self.counts.order_exception_count.value or self.counts.blocked_order_count.value
        ):
            raise DOISourceError("run_exception_count_result")
        if self.status is RunStatus.FAILED and not self.terminal_reasons.reasons:
            raise DOISourceError("run_failed_reason_set")

    def to_dict(self) -> dict[str, object]:
        return {
            "completed_at": None if self.completed_at is None else self.completed_at.value,
            "counts": self.counts.to_dict(),
            "invocation_id": self.invocation_id.to_json_value(),
            "purge_eligible_at": (
                None
                if self.purge_eligible_at is None
                else self.purge_eligible_at.value
            ),
            "recheck_order_id": (
                None if self.recheck_order_id is None else self.recheck_order_id.value
            ),
            "run_id": self.run_id.value,
            "run_type": self.run_type.value,
            "schema_version": self.schema_version,
            "source_batch_id": (
                None
                if self.source_batch_id is None
                else self.source_batch_id.to_json_value()
            ),
            "started_at": self.started_at.value,
            "status": self.status.value,
            "terminal_reasons": self.terminal_reasons.to_json_value(),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_record_bytes(self)

    def hash_binding(self) -> HashBinding:
        return _hash_record(self, domain=self.HASH_DOMAIN)


def _run_purge_deadline(completed_at: CanonicalTimestamp) -> CanonicalTimestamp:
    from synthetic_sales_assist.doi.retention import calendar90

    return calendar90(completed_at)


@dataclass(frozen=True, slots=True)
class DOIRunEvent:
    run_id: RunId
    sequence: PositiveOrdinal
    event_kind: RunEventKind
    occurred_at: CanonicalTimestamp
    status: RunStatus
    reasons: ReasonSet

    HASH_DOMAIN: ClassVar[str] = "doi-run-event/v1"

    def __post_init__(self) -> None:
        if (
            type(self.run_id) is not RunId
            or type(self.sequence) is not PositiveOrdinal
            or type(self.event_kind) is not RunEventKind
            or type(self.occurred_at) is not CanonicalTimestamp
            or type(self.status) is not RunStatus
            or type(self.reasons) is not ReasonSet
        ):
            raise DOISourceError("run_event_shape")
        if self.event_kind is RunEventKind.RUN_STARTED:
            if (
                self.sequence.value != 1
                or self.status is not RunStatus.IN_PROGRESS
                or self.reasons.reasons
            ):
                raise DOISourceError("run_start_event_shape")
        elif self.status is RunStatus.IN_PROGRESS:
            raise DOISourceError("run_terminal_event_shape")

    def to_dict(self) -> dict[str, object]:
        return {
            "event_kind": self.event_kind.value,
            "occurred_at": self.occurred_at.value,
            "reasons": self.reasons.to_json_value(),
            "run_id": self.run_id.value,
            "sequence": self.sequence.to_json_value(),
            "status": self.status.value,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_record_bytes(self)

    def hash_binding(self) -> HashBinding:
        return _hash_record(self, domain=self.HASH_DOMAIN)


@dataclass(frozen=True, slots=True)
class DOISourceImportAttempt:
    attempt_id: SourceImportAttemptId
    run_id: RunId
    ordinal: PositiveOrdinal
    source_identity_id: SourceIdentityId
    state: SourceImportAttemptState
    started_at: CanonicalTimestamp
    completed_at: CanonicalTimestamp | None
    source_batch_id: SourceBatchId | None
    reasons: ReasonSet
    portal_read_count: NonNegativeCount
    schema_version: str = SOURCE_ATTEMPT_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-source-import-attempt/v1"

    def __post_init__(self) -> None:
        if (
            type(self.attempt_id) is not SourceImportAttemptId
            or type(self.run_id) is not RunId
            or type(self.ordinal) is not PositiveOrdinal
            or type(self.source_identity_id) is not SourceIdentityId
            or type(self.state) is not SourceImportAttemptState
            or type(self.started_at) is not CanonicalTimestamp
            or type(self.reasons) is not ReasonSet
            or type(self.portal_read_count) is not NonNegativeCount
            or self.portal_read_count.value != 0
            or self.schema_version != SOURCE_ATTEMPT_SCHEMA_VERSION
        ):
            raise DOISourceError("source_attempt_shape")
        terminal = self.state is not SourceImportAttemptState.STARTED
        if terminal != (type(self.completed_at) is CanonicalTimestamp):
            raise DOISourceError("source_attempt_completion_partition")
        if self.state is SourceImportAttemptState.SUCCEEDED:
            if type(self.source_batch_id) is not SourceBatchId or self.reasons.reasons:
                raise DOISourceError("source_attempt_success_partition")
        elif self.source_batch_id is not None:
            raise DOISourceError("source_attempt_batch_partition")
        if self.state is SourceImportAttemptState.FAILED:
            codes = {reason.code for reason in self.reasons.reasons}
            if "RC-090" not in codes or not codes.intersection(_SPECIFIC_SOURCE_FAILURES):
                raise DOISourceError("source_attempt_failure_reasons")
        elif self.state is not SourceImportAttemptState.SUCCEEDED and self.reasons.reasons:
            raise DOISourceError("source_attempt_reason_partition")

    def to_dict(self) -> dict[str, object]:
        return {
            "attempt_id": self.attempt_id.to_json_value(),
            "completed_at": None if self.completed_at is None else self.completed_at.value,
            "ordinal": self.ordinal.to_json_value(),
            "portal_read_count": self.portal_read_count.to_json_value(),
            "reasons": self.reasons.to_json_value(),
            "run_id": self.run_id.value,
            "schema_version": self.schema_version,
            "source_batch_id": (
                None
                if self.source_batch_id is None
                else self.source_batch_id.to_json_value()
            ),
            "source_identity_id": self.source_identity_id.to_json_value(),
            "started_at": self.started_at.value,
            "state": self.state.value,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_record_bytes(self)

    def hash_binding(self) -> HashBinding:
        return _hash_record(self, domain=self.HASH_DOMAIN)


@dataclass(frozen=True, slots=True)
class DOISourceImportAttemptEvent:
    attempt_id: SourceImportAttemptId
    sequence: PositiveOrdinal
    event_kind: SourceAttemptEventKind
    occurred_at: CanonicalTimestamp
    reasons: ReasonSet
    source_batch_id: SourceBatchId | None

    HASH_DOMAIN: ClassVar[str] = "doi-source-import-attempt-event/v1"

    def __post_init__(self) -> None:
        if (
            type(self.attempt_id) is not SourceImportAttemptId
            or type(self.sequence) is not PositiveOrdinal
            or type(self.event_kind) is not SourceAttemptEventKind
            or type(self.occurred_at) is not CanonicalTimestamp
            or type(self.reasons) is not ReasonSet
        ):
            raise DOISourceError("source_attempt_event_shape")
        if self.event_kind is SourceAttemptEventKind.SOURCE_IMPORT_STARTED:
            if self.sequence.value != 1 or self.reasons.reasons or self.source_batch_id is not None:
                raise DOISourceError("source_attempt_start_event")
        elif self.event_kind is SourceAttemptEventKind.SOURCE_IMPORT_SUCCEEDED:
            if type(self.source_batch_id) is not SourceBatchId or self.reasons.reasons:
                raise DOISourceError("source_attempt_success_event")
        elif self.event_kind is SourceAttemptEventKind.SOURCE_IMPORT_FAILED:
            if self.source_batch_id is not None or "RC-090" not in {
                reason.code for reason in self.reasons.reasons
            }:
                raise DOISourceError("source_attempt_failure_event")
        elif self.source_batch_id is not None or self.reasons.reasons:
            raise DOISourceError("source_attempt_abort_event")

    def to_dict(self) -> dict[str, object]:
        return {
            "attempt_id": self.attempt_id.to_json_value(),
            "event_kind": self.event_kind.value,
            "occurred_at": self.occurred_at.value,
            "reasons": self.reasons.to_json_value(),
            "sequence": self.sequence.to_json_value(),
            "source_batch_id": (
                None
                if self.source_batch_id is None
                else self.source_batch_id.to_json_value()
            ),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_record_bytes(self)

    def hash_binding(self) -> HashBinding:
        return _hash_record(self, domain=self.HASH_DOMAIN)


_NO_RETRY_COMMAND_TOKEN = object()
_SYNTHETIC_NO_RETRY_ACTOR = RepId("SYN-REP-AUTHORIZED-0001")


@dataclass(frozen=True, slots=True, init=False, repr=False)
class FinalizeFailedSourceImportNoRetryCommand:
    command_id: AcceptedCommandId
    run_id: RunId
    greatest_failed_attempt_id: SourceImportAttemptId
    accepted_actor_id: RepId
    accepted_at: CanonicalTimestamp
    kind: AcceptedActionCommandKind
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-finalize-failed-source-no-retry-command/v1"

    @classmethod
    def _accepted(
        cls,
        *,
        command_id: AcceptedCommandId,
        run_id: RunId,
        greatest_failed_attempt_id: SourceImportAttemptId,
        accepted_actor_id: RepId,
        accepted_at: CanonicalTimestamp,
        factory_capability: object,
    ) -> FinalizeFailedSourceImportNoRetryCommand:
        if factory_capability is not _NO_RETRY_COMMAND_TOKEN:
            raise DOISourceError("no_retry_command_factory_required")
        instance = object.__new__(cls)
        object.__setattr__(instance, "command_id", command_id)
        object.__setattr__(instance, "run_id", run_id)
        object.__setattr__(
            instance,
            "greatest_failed_attempt_id",
            greatest_failed_attempt_id,
        )
        object.__setattr__(instance, "accepted_actor_id", accepted_actor_id)
        object.__setattr__(instance, "accepted_at", accepted_at)
        object.__setattr__(
            instance,
            "kind",
            AcceptedActionCommandKind.FINALIZE_FAILED_SOURCE_IMPORT_NO_RETRY,
        )
        object.__setattr__(instance, "schema_version", cls.HASH_DOMAIN)
        instance.__post_init__()
        return instance

    def __post_init__(self) -> None:
        if (
            type(self.command_id) is not AcceptedCommandId
            or type(self.run_id) is not RunId
            or type(self.greatest_failed_attempt_id) is not SourceImportAttemptId
            or type(self.accepted_actor_id) is not RepId
            or type(self.accepted_at) is not CanonicalTimestamp
            or type(self.kind) is not AcceptedActionCommandKind
            or self.schema_version != self.HASH_DOMAIN
        ):
            raise DOISourceError("no_retry_command_shape")

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted_actor_id": self.accepted_actor_id.value,
            "accepted_at": self.accepted_at.value,
            "command_id": self.command_id.to_json_value(),
            "greatest_failed_attempt_id": self.greatest_failed_attempt_id.to_json_value(),
            "kind": self.kind.value,
            "run_id": self.run_id.value,
            "schema_version": self.schema_version,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_record_bytes(self)

    def hash_binding(self) -> HashBinding:
        return _hash_record(self, domain=self.HASH_DOMAIN)

    def __repr__(self) -> str:
        return "FinalizeFailedSourceImportNoRetryCommand(<accepted>)"


def accept_no_retry_command(
    *,
    command_id: AcceptedCommandId,
    run_id: RunId,
    greatest_failed_attempt_id: SourceImportAttemptId,
    accepted_actor_id: RepId,
    accepted_at: CanonicalTimestamp,
) -> FinalizeFailedSourceImportNoRetryCommand:
    """Synthetic Milestone 3 acceptance boundary for the one authorized test actor."""

    if accepted_actor_id != _SYNTHETIC_NO_RETRY_ACTOR:
        raise DOISourceError("no_retry_actor_unauthorized")
    return FinalizeFailedSourceImportNoRetryCommand._accepted(
        command_id=command_id,
        run_id=run_id,
        greatest_failed_attempt_id=greatest_failed_attempt_id,
        accepted_actor_id=accepted_actor_id,
        accepted_at=accepted_at,
        factory_capability=_NO_RETRY_COMMAND_TOKEN,
    )


@dataclass(frozen=True, slots=True)
class NoRetryCommandReceipt:
    receipt_id: CommandReceiptId
    command: HashBinding
    run: HashBinding
    run_event: HashBinding
    accepted_at: CanonicalTimestamp

    HASH_DOMAIN: ClassVar[str] = "doi-no-retry-command-receipt/v1"

    def __post_init__(self) -> None:
        if (
            type(self.receipt_id) is not CommandReceiptId
            or type(self.command) is not HashBinding
            or self.command.domain != FinalizeFailedSourceImportNoRetryCommand.HASH_DOMAIN
            or type(self.run) is not HashBinding
            or self.run.domain != DOIRun.HASH_DOMAIN
            or type(self.run_event) is not HashBinding
            or self.run_event.domain != DOIRunEvent.HASH_DOMAIN
            or type(self.accepted_at) is not CanonicalTimestamp
        ):
            raise DOISourceError("no_retry_receipt_shape")

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted_at": self.accepted_at.value,
            "command": _binding_dict(self.command),
            "receipt_id": self.receipt_id.to_json_value(),
            "run": _binding_dict(self.run),
            "run_event": _binding_dict(self.run_event),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_record_bytes(self)

    def hash_binding(self) -> HashBinding:
        return _hash_record(self, domain=self.HASH_DOMAIN)


@dataclass(frozen=True, slots=True)
class ExtractionReservationReceipt:
    receipt_id: CommandReceiptId
    run_id: RunId
    occurrence_id: ExtractionOccurrenceId
    reserved_at: CanonicalTimestamp
    operation: RunControlOperation = field(
        default=RunControlOperation.EXTRACTION_RESERVED,
        init=False,
    )

    HASH_DOMAIN: ClassVar[str] = "doi-extraction-reservation-receipt/v1"

    def __post_init__(self) -> None:
        if (
            type(self.receipt_id) is not CommandReceiptId
            or type(self.run_id) is not RunId
            or type(self.occurrence_id) is not ExtractionOccurrenceId
            or type(self.reserved_at) is not CanonicalTimestamp
        ):
            raise DOISourceError("extraction_reservation_shape")

    def to_dict(self) -> dict[str, object]:
        return {
            "occurrence_id": self.occurrence_id.to_json_value(),
            "operation": self.operation.value,
            "receipt_id": self.receipt_id.to_json_value(),
            "reserved_at": self.reserved_at.value,
            "run_id": self.run_id.value,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_record_bytes(self)

    def hash_binding(self) -> HashBinding:
        return _hash_record(self, domain=self.HASH_DOMAIN)


@dataclass(frozen=True, slots=True)
class PreExtractionRulesUnavailableReceipt:
    receipt_id: CommandReceiptId
    run: DOIRun
    event: DOIRunEvent
    operation: RunControlOperation = field(
        default=RunControlOperation.PRE_EXTRACTION_RULES_UNAVAILABLE,
        init=False,
    )

    HASH_DOMAIN: ClassVar[str] = "doi-pre-extraction-rules-unavailable-receipt/v1"

    def __post_init__(self) -> None:
        if (
            type(self.receipt_id) is not CommandReceiptId
            or type(self.run) is not DOIRun
            or self.run.status is not RunStatus.FAILED
            or self.run.terminal_reasons != _reason_set("RC-084")
            or type(self.event) is not DOIRunEvent
            or self.event.reasons != _reason_set("RC-084")
        ):
            raise DOISourceError("pre_extraction_rules_receipt_shape")

    def to_dict(self) -> dict[str, object]:
        return {
            "event": _binding_dict(self.event.hash_binding()),
            "operation": self.operation.value,
            "receipt_id": self.receipt_id.to_json_value(),
            "run": _binding_dict(self.run.hash_binding()),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_record_bytes(self)

    def hash_binding(self) -> HashBinding:
        return _hash_record(self, domain=self.HASH_DOMAIN)


@dataclass(frozen=True, slots=True)
class RunStartResult:
    run: DOIRun
    run_event: DOIRunEvent
    source_attempt: DOISourceImportAttempt | None
    source_attempt_event: DOISourceImportAttemptEvent | None
    work_items: tuple[DOIRunWorkItem, ...]


@dataclass(frozen=True, slots=True)
class RunTerminalizationResult:
    run: DOIRun
    run_event: DOIRunEvent
    terminal_result: RunTerminalResult
    replayed: bool

    def __post_init__(self) -> None:
        if (
            type(self.run) is not DOIRun
            or self.run.status is RunStatus.IN_PROGRESS
            or type(self.run_event) is not DOIRunEvent
            or type(self.terminal_result) is not RunTerminalResult
            or self.terminal_result.value != self.run.status.value
            or type(self.replayed) is not bool
        ):
            raise DOISourceError("run_terminalization_result_shape")


class InMemoryDOIRunControl:
    """One-lock, copy-on-write simulation of source/retry/systemic run control."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._runs: dict[RunId, DOIRun] = {}
        self._run_events: dict[RunId, tuple[DOIRunEvent, ...]] = {}
        self._attempts: dict[SourceImportAttemptId, DOISourceImportAttempt] = {}
        self._attempt_events: dict[
            SourceImportAttemptId, tuple[DOISourceImportAttemptEvent, ...]
        ] = {}
        self._attempt_ids_by_run: dict[RunId, tuple[SourceImportAttemptId, ...]] = {}
        self._work_items: dict[RunId, tuple[DOIRunWorkItem, ...]] = {}
        self._work_dispositions: dict[
            RunId, dict[RunWorkItemId, DOIRunWorkDisposition]
        ] = {}
        self._invocation_material: dict[RunId, tuple[bytes, RunStartResult]] = {}
        self._retry_material: dict[AcceptedCommandId, tuple[bytes, DOISourceImportAttempt]] = {}
        self._attempt_commit_material: dict[
            SourceImportAttemptId,
            tuple[bytes, HashBinding | None],
        ] = {}
        self._attempt_batch_created: dict[SourceImportAttemptId, bool] = {}
        self._terminal_material: dict[
            RunId,
            tuple[bytes, RunTerminalizationResult],
        ] = {}
        self._no_retry_receipts: dict[AcceptedCommandId, tuple[bytes, NoRetryCommandReceipt]] = {}
        self._reservation_receipts: dict[
            tuple[RunId, ExtractionOccurrenceId],
            tuple[bytes, ExtractionReservationReceipt],
        ] = {}
        self._systemic_receipts: dict[
            tuple[RunId, AcceptedCommandId],
            tuple[bytes, PreExtractionRulesUnavailableReceipt],
        ] = {}
        self._extraction_reserved_runs: set[RunId] = set()
        self._source_batches = InMemorySourceBatchRegistry()
        self._attempt_counter = 0
        self._work_counter = 0
        self._receipt_counter = 0

    def _allocate_attempt_id(self) -> SourceImportAttemptId:
        self._attempt_counter += 1
        return SourceImportAttemptId(
            InteractionId(f"SYN-INTERACTION-DOI-ATTEMPT-{self._attempt_counter:06d}")
        )

    def _allocate_work_id(self) -> RunWorkItemId:
        self._work_counter += 1
        return RunWorkItemId(
            InteractionId(f"SYN-INTERACTION-DOI-WORK-{self._work_counter:06d}")
        )

    def _allocate_receipt_id(self) -> CommandReceiptId:
        self._receipt_counter += 1
        return CommandReceiptId(EvidenceId(f"SYN-EVIDENCE-DOI-RECEIPT-{self._receipt_counter:06d}"))

    def begin_review_run(
        self,
        *,
        run_id: RunId,
        invocation_id: RunInvocationId,
        source_identity_id: SourceIdentityId,
        locked_tab: SyntheticQueueTab,
        tab_confirmed: bool,
        accepted_at: CanonicalTimestamp,
    ) -> RunStartResult:
        if type(locked_tab) is not SyntheticQueueTab or tab_confirmed is not True:
            raise DOISourceError("RC-001")
        value = {
            "accepted_at": accepted_at.value,
            "invocation_id": invocation_id.to_json_value(),
            "run_id": run_id.value,
            "run_type": RunType.RUN_DOI_REVIEW.value,
            "source_identity_id": source_identity_id.to_json_value(),
            "locked_tab": locked_tab.value,
            "tab_confirmed": tab_confirmed,
        }
        material = canonical_json_bytes(value, expected_members=set(value))
        with self._lock:
            retained = self._invocation_material.get(run_id)
            if retained is not None:
                if retained[0] != material:
                    raise RunControlConflict("run_invocation_conflict")
                return retained[1]
            if run_id in self._runs:
                raise RunControlConflict("run_identity_conflict")
            attempt_id = self._allocate_attempt_id()
            run = DOIRun(
                run_id=run_id,
                invocation_id=invocation_id,
                run_type=RunType.RUN_DOI_REVIEW,
                status=RunStatus.IN_PROGRESS,
                started_at=accepted_at,
                completed_at=None,
                purge_eligible_at=None,
                source_batch_id=None,
                recheck_order_id=None,
                counts=DOIRunCounts.empty(source_attempt_count=1),
                terminal_reasons=ReasonSet(),
            )
            event = DOIRunEvent(
                run_id,
                PositiveOrdinal(1),
                RunEventKind.RUN_STARTED,
                accepted_at,
                RunStatus.IN_PROGRESS,
                ReasonSet(),
            )
            attempt = DOISourceImportAttempt(
                attempt_id=attempt_id,
                run_id=run_id,
                ordinal=PositiveOrdinal(1),
                source_identity_id=source_identity_id,
                state=SourceImportAttemptState.STARTED,
                started_at=accepted_at,
                completed_at=None,
                source_batch_id=None,
                reasons=ReasonSet(),
                portal_read_count=NonNegativeCount(0),
            )
            attempt_event = DOISourceImportAttemptEvent(
                attempt_id,
                PositiveOrdinal(1),
                SourceAttemptEventKind.SOURCE_IMPORT_STARTED,
                accepted_at,
                ReasonSet(),
                None,
            )
            result = RunStartResult(run, event, attempt, attempt_event, ())
            self._runs[run_id] = run
            self._run_events[run_id] = (event,)
            self._attempts[attempt_id] = attempt
            self._attempt_events[attempt_id] = (attempt_event,)
            self._attempt_ids_by_run[run_id] = (attempt_id,)
            self._work_items[run_id] = ()
            self._invocation_material[run_id] = (material, result)
            return result

    def begin_recheck_run(
        self,
        *,
        run_id: RunId,
        invocation_id: RunInvocationId,
        run_type: RunType,
        order_id: OrderId,
        accepted_at: CanonicalTimestamp,
    ) -> RunStartResult:
        if run_type not in {RunType.RECHECK_ORDER, RunType.RECHECK_DEDUPE_ORDER}:
            raise DOISourceError("recheck_run_type")
        value = {
            "accepted_at": accepted_at.value,
            "invocation_id": invocation_id.to_json_value(),
            "order_id": order_id.value,
            "run_id": run_id.value,
            "run_type": run_type.value,
        }
        material = canonical_json_bytes(value, expected_members=set(value))
        with self._lock:
            retained = self._invocation_material.get(run_id)
            if retained is not None:
                if retained[0] != material:
                    raise RunControlConflict("run_invocation_conflict")
                return retained[1]
            if run_id in self._runs:
                raise RunControlConflict("run_identity_conflict")
            origin = (
                RunWorkOrigin.ORDER_RECHECK
                if run_type is RunType.RECHECK_ORDER
                else RunWorkOrigin.DEDUPE_RECHECK
            )
            work_item = DOIRunWorkItem(
                self._allocate_work_id(), run_id, order_id, origin, None
            )
            run = DOIRun(
                run_id=run_id,
                invocation_id=invocation_id,
                run_type=run_type,
                status=RunStatus.IN_PROGRESS,
                started_at=accepted_at,
                completed_at=None,
                purge_eligible_at=None,
                source_batch_id=None,
                recheck_order_id=order_id,
                counts=DOIRunCounts.empty(work_item_count=1),
                terminal_reasons=ReasonSet(),
            )
            event = DOIRunEvent(
                run_id,
                PositiveOrdinal(1),
                RunEventKind.RUN_STARTED,
                accepted_at,
                RunStatus.IN_PROGRESS,
                ReasonSet(),
            )
            result = RunStartResult(run, event, None, None, (work_item,))
            self._runs[run_id] = run
            self._run_events[run_id] = (event,)
            self._attempt_ids_by_run[run_id] = ()
            self._work_items[run_id] = (work_item,)
            self._invocation_material[run_id] = (material, result)
            return result

    def commit_import_result(
        self,
        *,
        attempt_id: SourceImportAttemptId,
        result: SourceImportResult,
        completed_at: CanonicalTimestamp,
    ) -> DOISourceImportAttempt:
        result_binding = result.hash_binding()
        material_value = {
            "attempt_id": attempt_id.to_json_value(),
            "completed_at": completed_at.value,
            "result_sha256": result_binding.sha256,
        }
        material = canonical_json_bytes(material_value, expected_members=set(material_value))
        with self._lock:
            attempt = self._attempts.get(attempt_id)
            if attempt is None:
                raise RunControlConflict("source_attempt_missing")
            retained_material = self._attempt_commit_material.get(attempt_id)
            if retained_material is not None:
                if retained_material[0] != material or retained_material[1] is None:
                    raise RunControlConflict("source_attempt_commit_conflict")
                try:
                    replay = compare_retained_canonical_bytes(
                        retained_material[1].sha256,
                        retained_material[1].canonical_bytes,
                        result_binding.sha256,
                        result_binding.canonical_bytes,
                    )
                except CanonicalHashCollision:
                    raise RunControlConflict("RC-103") from None
                if not replay:
                    raise RunControlConflict("source_attempt_commit_conflict")
                return attempt
            run = self._runs[attempt.run_id]
            if (
                run.status is not RunStatus.IN_PROGRESS
                or attempt.state is not SourceImportAttemptState.STARTED
            ):
                raise RunControlConflict("source_attempt_state")
            event_sequence = PositiveOrdinal(2)
            if result.kind is SourceImportResultKind.FAILED:
                updated_attempt = replace(
                    attempt,
                    state=SourceImportAttemptState.FAILED,
                    completed_at=completed_at,
                    reasons=result.reasons,
                )
                event = DOISourceImportAttemptEvent(
                    attempt_id,
                    event_sequence,
                    SourceAttemptEventKind.SOURCE_IMPORT_FAILED,
                    completed_at,
                    result.reasons,
                    None,
                )
            else:
                assert result.batch is not None
                batch, batch_created = self._source_batches.register_with_disposition(
                    result.batch
                )
                work_items = tuple(
                    DOIRunWorkItem(
                        self._allocate_work_id(),
                        run.run_id,
                        staged.order_id,
                        RunWorkOrigin.SOURCE_IMPORT,
                        batch.batch_id,
                    )
                    for staged in batch.staged_orders
                )
                updated_attempt = replace(
                    attempt,
                    state=SourceImportAttemptState.SUCCEEDED,
                    completed_at=completed_at,
                    source_batch_id=batch.batch_id,
                )
                event = DOISourceImportAttemptEvent(
                    attempt_id,
                    event_sequence,
                    SourceAttemptEventKind.SOURCE_IMPORT_SUCCEEDED,
                    completed_at,
                    ReasonSet(),
                    batch.batch_id,
                )
                updated_counts = replace(
                    run.counts,
                    source_rows=batch.counts,
                    work_item_count=NonNegativeCount(len(work_items)),
                )
                updated_run = replace(
                    run,
                    source_batch_id=batch.batch_id,
                    counts=updated_counts,
                )
                self._runs[run.run_id] = updated_run
                self._work_items[run.run_id] = work_items
                self._attempt_batch_created[attempt_id] = batch_created
            self._attempts[attempt_id] = updated_attempt
            self._attempt_events[attempt_id] = self._attempt_events[attempt_id] + (event,)
            self._attempt_commit_material[attempt_id] = (material, result_binding)
            return updated_attempt

    def abort_import_attempt(
        self,
        *,
        attempt_id: SourceImportAttemptId,
        completed_at: CanonicalTimestamp,
    ) -> DOISourceImportAttempt:
        # Deliberate abort has an exact empty reason set, unlike a failure result.
        with self._lock:
            attempt = self._attempts.get(attempt_id)
            if attempt is None:
                raise RunControlConflict("source_attempt_state")
            material_value = {
                "attempt_id": attempt_id.to_json_value(),
                "completed_at": completed_at.value,
                "kind": "ABORT",
            }
            material = canonical_json_bytes(material_value, expected_members=set(material_value))
            retained_material = self._attempt_commit_material.get(attempt_id)
            if retained_material is not None:
                if (
                    retained_material != (material, None)
                    or attempt.state is not SourceImportAttemptState.ABORTED
                ):
                    raise RunControlConflict("source_attempt_commit_conflict")
                return attempt
            run = self._runs[attempt.run_id]
            if (
                run.status is not RunStatus.IN_PROGRESS
                or attempt.state is not SourceImportAttemptState.STARTED
            ):
                raise RunControlConflict("source_attempt_state")
            updated = replace(
                attempt,
                state=SourceImportAttemptState.ABORTED,
                completed_at=completed_at,
                reasons=ReasonSet(),
            )
            event = DOISourceImportAttemptEvent(
                attempt_id,
                PositiveOrdinal(2),
                SourceAttemptEventKind.SOURCE_IMPORT_ABORTED,
                completed_at,
                ReasonSet(),
                None,
            )
            self._attempts[attempt_id] = updated
            self._attempt_events[attempt_id] += (event,)
            self._attempt_commit_material[attempt_id] = (material, None)
            return updated

    def record_work_disposition(
        self,
        disposition: DOIRunWorkDisposition,
    ) -> DOIRunWorkDisposition:
        """Append exactly one terminal disposition per accepted work item."""

        if type(disposition) is not DOIRunWorkDisposition:
            raise DOISourceError("run_work_disposition_input")
        with self._lock:
            run = self._runs.get(disposition.run_id)
            if run is None or run.status is not RunStatus.IN_PROGRESS:
                raise RunControlConflict("run_work_disposition_state")
            work = {
                item.work_item_id: item
                for item in self._work_items.get(disposition.run_id, ())
            }
            item = work.get(disposition.work_item_id)
            if (
                item is None
                or item.hash_binding().sha256 != disposition.work_item_sha256
            ):
                raise RunControlConflict("run_work_disposition_item_binding")
            retained = self._work_dispositions.setdefault(disposition.run_id, {}).get(
                disposition.work_item_id
            )
            if retained is not None:
                try:
                    replay = compare_retained_canonical_bytes(
                        retained.hash_binding().sha256,
                        retained.canonical_bytes(),
                        disposition.hash_binding().sha256,
                        disposition.canonical_bytes(),
                    )
                except CanonicalHashCollision:
                    raise RunControlConflict("RC-103") from None
                if not replay:
                    raise RunControlConflict("run_work_disposition_conflict")
                return retained
            self._work_dispositions[disposition.run_id][
                disposition.work_item_id
            ] = disposition
            return disposition

    def finalize_processing(
        self,
        *,
        run_id: RunId,
        completed_at: CanonicalTimestamp,
    ) -> RunTerminalizationResult:
        """Terminalize coherent work as COMPLETED or COMPLETED_WITH_EXCEPTIONS.

        Counts are derived only from retained per-work-item dispositions.  This method owns
        conservation, exact replay, and the terminal run event; it cannot produce FAILED,
        which remains restricted to the two TR-004 branches.
        """

        if (
            type(run_id) is not RunId
            or type(completed_at) is not CanonicalTimestamp
        ):
            raise DOISourceError("run_finalization_input")
        with self._lock:
            dispositions = tuple(
                sorted(
                    self._work_dispositions.get(run_id, {}).values(),
                    key=lambda item: str(item.work_item_id),
                )
            )
            value = {
                "completed_at": completed_at.value,
                "disposition_sha256s": [
                    item.hash_binding().sha256 for item in dispositions
                ],
                "run_id": run_id.value,
            }
            material = canonical_json_bytes(value, expected_members=set(value))
            replay = self._terminal_material.get(run_id)
            if replay is not None:
                if replay[0] != material:
                    raise RunControlConflict("run_terminalization_conflict")
                return replace(replay[1], replayed=True)
            run = self._runs.get(run_id)
            if run is None or run.status is not RunStatus.IN_PROGRESS:
                raise RunControlConflict("run_terminalization_state")
            work_items = self._work_items.get(run_id, ())
            if run.run_type is RunType.RUN_DOI_REVIEW and run.source_batch_id is None:
                raise RunControlConflict("run_terminal_batch_required")
            if len(dispositions) != len(work_items) or {
                item.work_item_id for item in dispositions
            } != {item.work_item_id for item in work_items}:
                raise RunControlConflict("run_terminal_count_conservation")
            successes = sum(
                item.kind is RunWorkDispositionKind.SUCCESSFUL_EVALUATION
                for item in dispositions
            )
            exceptions = sum(
                item.kind is RunWorkDispositionKind.ORDER_EXCEPTION
                for item in dispositions
            )
            blocked = sum(
                item.kind is RunWorkDispositionKind.BLOCKED_ORDER
                for item in dispositions
            )
            portal_reads = sum(item.portal_read_performed for item in dispositions)
            final_counts = replace(
                run.counts,
                disposition_subject_count=NonNegativeCount(len(dispositions)),
                successful_evaluation_count=NonNegativeCount(successes),
                order_exception_count=NonNegativeCount(exceptions),
                blocked_order_count=NonNegativeCount(blocked),
                portal_read_count=NonNegativeCount(portal_reads),
            )
            has_exceptions = bool(
                final_counts.order_exception_count.value
                or final_counts.blocked_order_count.value
            )
            status = (
                RunStatus.COMPLETED_WITH_EXCEPTIONS
                if has_exceptions
                else RunStatus.COMPLETED
            )
            terminal = replace(
                run,
                status=status,
                completed_at=completed_at,
                purge_eligible_at=_run_purge_deadline(completed_at),
                counts=final_counts,
                terminal_reasons=ReasonSet(),
            )
            event = DOIRunEvent(
                run_id,
                PositiveOrdinal(len(self._run_events[run_id]) + 1),
                RunEventKind.RUN_TERMINAL,
                completed_at,
                status,
                ReasonSet(),
            )
            result = RunTerminalizationResult(
                run=terminal,
                run_event=event,
                terminal_result=RunTerminalResult(status.value),
                replayed=False,
            )
            self._runs[run_id] = terminal
            self._run_events[run_id] += (event,)
            self._terminal_material[run_id] = (material, result)
            return result

    def retry_source_import(
        self,
        *,
        run_id: RunId,
        command_id: AcceptedCommandId,
        source_identity_id: SourceIdentityId,
        accepted_at: CanonicalTimestamp,
    ) -> DOISourceImportAttempt:
        value = {
            "accepted_at": accepted_at.value,
            "command_id": command_id.to_json_value(),
            "run_id": run_id.value,
            "source_identity_id": source_identity_id.to_json_value(),
        }
        material = canonical_json_bytes(value, expected_members=set(value))
        with self._lock:
            replay = self._retry_material.get(command_id)
            if replay is not None:
                if replay[0] != material:
                    raise RunControlConflict("retry_command_conflict")
                return replay[1]
            run = self._runs.get(run_id)
            if run is None or run.status is not RunStatus.IN_PROGRESS:
                raise RunControlConflict("retry_run_state")
            ids = self._attempt_ids_by_run.get(run_id, ())
            if not ids:
                raise RunControlConflict("retry_predecessor_missing")
            greatest = self._attempts[ids[-1]]
            if greatest.state not in {
                SourceImportAttemptState.FAILED,
                SourceImportAttemptState.ABORTED,
            }:
                raise RunControlConflict("retry_predecessor_state")
            attempt_id = self._allocate_attempt_id()
            attempt = DOISourceImportAttempt(
                attempt_id=attempt_id,
                run_id=run_id,
                ordinal=PositiveOrdinal(greatest.ordinal.value + 1),
                source_identity_id=source_identity_id,
                state=SourceImportAttemptState.STARTED,
                started_at=accepted_at,
                completed_at=None,
                source_batch_id=None,
                reasons=ReasonSet(),
                portal_read_count=NonNegativeCount(0),
            )
            event = DOISourceImportAttemptEvent(
                attempt_id,
                PositiveOrdinal(1),
                SourceAttemptEventKind.SOURCE_IMPORT_STARTED,
                accepted_at,
                ReasonSet(),
                None,
            )
            self._attempts[attempt_id] = attempt
            self._attempt_events[attempt_id] = (event,)
            self._attempt_ids_by_run[run_id] = ids + (attempt_id,)
            self._runs[run_id] = replace(
                run,
                counts=replace(
                    run.counts,
                    source_attempt_count=NonNegativeCount(
                        run.counts.source_attempt_count.value + 1
                    ),
                ),
            )
            self._retry_material[command_id] = (material, attempt)
            return attempt

    def finalize_failed_source_import_no_retry(
        self, command: FinalizeFailedSourceImportNoRetryCommand
    ) -> NoRetryCommandReceipt:
        material = command.canonical_bytes()
        with self._lock:
            replay = self._no_retry_receipts.get(command.command_id)
            if replay is not None:
                if replay[0] != material:
                    raise RunControlConflict("no_retry_command_conflict")
                return replay[1]
            run = self._runs.get(command.run_id)
            if run is None or run.status is not RunStatus.IN_PROGRESS:
                raise RunControlConflict("no_retry_run_state")
            ids = self._attempt_ids_by_run.get(command.run_id, ())
            if not ids or ids[-1] != command.greatest_failed_attempt_id:
                raise RunControlConflict("no_retry_greatest_attempt")
            attempt = self._attempts[ids[-1]]
            if attempt.state is not SourceImportAttemptState.FAILED:
                raise RunControlConflict("no_retry_attempt_state")
            if run.source_batch_id is not None or self._work_items.get(run.run_id):
                raise RunControlConflict("no_retry_executable_work_exists")
            terminal = replace(
                run,
                status=RunStatus.FAILED,
                completed_at=command.accepted_at,
                purge_eligible_at=_run_purge_deadline(command.accepted_at),
                terminal_reasons=attempt.reasons,
            )
            event = DOIRunEvent(
                run.run_id,
                PositiveOrdinal(len(self._run_events[run.run_id]) + 1),
                RunEventKind.RUN_TERMINAL,
                command.accepted_at,
                RunStatus.FAILED,
                attempt.reasons,
            )
            receipt = NoRetryCommandReceipt(
                self._allocate_receipt_id(),
                command.hash_binding(),
                terminal.hash_binding(),
                event.hash_binding(),
                command.accepted_at,
            )
            self._runs[run.run_id] = terminal
            self._run_events[run.run_id] += (event,)
            self._no_retry_receipts[command.command_id] = (material, receipt)
            return receipt

    def reserve_extraction(
        self,
        *,
        run_id: RunId,
        occurrence_id: ExtractionOccurrenceId,
        reserved_at: CanonicalTimestamp,
    ) -> ExtractionReservationReceipt:
        value = {
            "occurrence_id": occurrence_id.to_json_value(),
            "reserved_at": reserved_at.value,
            "run_id": run_id.value,
        }
        material = canonical_json_bytes(value, expected_members=set(value))
        key = (run_id, occurrence_id)
        with self._lock:
            replay = self._reservation_receipts.get(key)
            if replay is not None:
                if replay[0] != material:
                    raise RunControlConflict("extraction_reservation_conflict")
                return replay[1]
            run = self._runs.get(run_id)
            if run is None or run.status is not RunStatus.IN_PROGRESS:
                raise RunControlConflict("extraction_reservation_run_state")
            receipt = ExtractionReservationReceipt(
                self._allocate_receipt_id(), run_id, occurrence_id, reserved_at
            )
            self._extraction_reserved_runs.add(run_id)
            self._reservation_receipts[key] = (material, receipt)
            return receipt

    def fail_pre_extraction_rules_unavailable(
        self,
        *,
        run_id: RunId,
        command_id: AcceptedCommandId,
        occurred_at: CanonicalTimestamp,
    ) -> PreExtractionRulesUnavailableReceipt:
        value = {
            "command_id": command_id.to_json_value(),
            "occurred_at": occurred_at.value,
            "operation": RunControlOperation.PRE_EXTRACTION_RULES_UNAVAILABLE.value,
            "run_id": run_id.value,
        }
        material = canonical_json_bytes(value, expected_members=set(value))
        key = (run_id, command_id)
        with self._lock:
            replay = self._systemic_receipts.get(key)
            if replay is not None:
                if replay[0] != material:
                    raise RunControlConflict("systemic_terminalization_conflict")
                return replay[1]
            run = self._runs.get(run_id)
            if run is None or run.status is not RunStatus.IN_PROGRESS:
                raise RunControlConflict("systemic_terminalization_run_state")
            if run_id in self._extraction_reserved_runs:
                raise RunControlConflict("extraction_reservation_won")
            if (
                run.counts.portal_read_count.value
                or run.counts.disposition_subject_count.value
                or run.counts.successful_evaluation_count.value
            ):
                raise RunControlConflict("pre_extraction_zero_count_guard")
            reasons = _reason_set("RC-084")
            terminal = replace(
                run,
                status=RunStatus.FAILED,
                completed_at=occurred_at,
                purge_eligible_at=_run_purge_deadline(occurred_at),
                terminal_reasons=reasons,
            )
            event = DOIRunEvent(
                run_id,
                PositiveOrdinal(len(self._run_events[run_id]) + 1),
                RunEventKind.RUN_TERMINAL,
                occurred_at,
                RunStatus.FAILED,
                reasons,
            )
            receipt = PreExtractionRulesUnavailableReceipt(
                self._allocate_receipt_id(), terminal, event
            )
            self._runs[run_id] = terminal
            self._run_events[run_id] += (event,)
            self._systemic_receipts[key] = (material, receipt)
            return receipt

    def run(self, run_id: RunId) -> DOIRun:
        with self._lock:
            try:
                return self._runs[run_id]
            except KeyError:
                raise RunControlConflict("run_missing") from None

    def attempt(self, attempt_id: SourceImportAttemptId) -> DOISourceImportAttempt:
        with self._lock:
            try:
                return self._attempts[attempt_id]
            except KeyError:
                raise RunControlConflict("source_attempt_missing") from None

    def attempt_events(
        self,
        attempt_id: SourceImportAttemptId,
    ) -> tuple[DOISourceImportAttemptEvent, ...]:
        """Return the immutable retained event history for one import attempt."""

        with self._lock:
            try:
                return self._attempt_events[attempt_id]
            except KeyError:
                raise RunControlConflict("source_attempt_missing") from None

    def attempts_for_run(self, run_id: RunId) -> tuple[DOISourceImportAttempt, ...]:
        """Return every retained attempt for a run in exact ordinal order."""

        with self._lock:
            try:
                attempt_ids = self._attempt_ids_by_run[run_id]
            except KeyError:
                raise RunControlConflict("run_missing") from None
            return tuple(self._attempts[attempt_id] for attempt_id in attempt_ids)

    def run_start_result(self, run_id: RunId) -> RunStartResult:
        """Return the accepted immutable invocation result for one run."""

        with self._lock:
            try:
                return self._invocation_material[run_id][1]
            except KeyError:
                raise RunControlConflict("run_missing") from None

    def retry_attempt(self, command_id: AcceptedCommandId) -> DOISourceImportAttempt:
        """Return the exact attempt minted by one accepted retry command."""

        if type(command_id) is not AcceptedCommandId:
            raise DOISourceError("retry_command_id")
        with self._lock:
            try:
                return self._retry_material[command_id][1]
            except KeyError:
                raise RunControlConflict("retry_command_missing") from None

    def attempt_commit_binding(
        self,
        attempt_id: SourceImportAttemptId,
    ) -> HashBinding | None:
        """Return the retained pure import-result binding, or None for an abort."""

        with self._lock:
            try:
                return self._attempt_commit_material[attempt_id][1]
            except KeyError:
                raise RunControlConflict("source_attempt_not_committed") from None

    def attempt_created_source_batch(
        self,
        attempt_id: SourceImportAttemptId,
    ) -> bool:
        """Return the retained CREATED/REUSED decision for a successful attempt."""

        with self._lock:
            try:
                return self._attempt_batch_created[attempt_id]
            except KeyError:
                raise RunControlConflict("source_attempt_batch_disposition_missing") from None

    def work_items(self, run_id: RunId) -> tuple[DOIRunWorkItem, ...]:
        with self._lock:
            return self._work_items.get(run_id, ())

    def run_events(self, run_id: RunId) -> tuple[DOIRunEvent, ...]:
        """Return the immutable event history retained by this run owner."""

        with self._lock:
            try:
                return self._run_events[run_id]
            except KeyError:
                raise RunControlConflict("run_missing") from None

    def source_batch(self, batch_id: SourceBatchId) -> DOISourceBatch:
        """Read one batch from this owning run-control service."""

        with self._lock:
            return self._source_batches.by_id(batch_id)

    def runs_for_source_batch(self, batch_id: SourceBatchId) -> tuple[DOIRun, ...]:
        """Return the complete retained explicit owner set for one source batch."""

        if type(batch_id) is not SourceBatchId:
            raise DOISourceError("source_batch_id")
        with self._lock:
            return tuple(
                sorted(
                    (
                        run
                        for run in self._runs.values()
                        if run.source_batch_id == batch_id
                    ),
                    key=lambda run: run.run_id.value,
                )
            )

    def source_batch_creator_run(self, batch_id: SourceBatchId) -> DOIRun:
        """Return the sole run whose successful attempt created this batch identity."""

        if type(batch_id) is not SourceBatchId:
            raise DOISourceError("source_batch_id")
        with self._lock:
            creator_attempts = tuple(
                attempt
                for attempt_id, created in self._attempt_batch_created.items()
                if created
                for attempt in (self._attempts[attempt_id],)
                if attempt.source_batch_id == batch_id
            )
            if len(creator_attempts) != 1:
                raise RunControlConflict("source_batch_creator_missing_or_ambiguous")
            return self._runs[creator_attempts[0].run_id]


def source_hash_fixture_records() -> tuple[tuple[str, str, bytes, str], ...]:
    """Return deterministic representative source records for central KAT generation."""

    source = SourceIdentityId(EvidenceId("SYN-EVIDENCE-DOI-SOURCE-0001"))
    rows = (
        SyntheticQueueRow(
            OrderId("SYN-ORDER-1"),
            TARGET_ASSIGNEE,
            SourceRowRefId(EvidenceId("SYN-EVIDENCE-DOI-ROW-0001")),
        ),
        SyntheticQueueRow(
            OrderId("SYN-ORDER-2"),
            TARGET_ASSIGNEE,
            SourceRowRefId(EvidenceId("SYN-EVIDENCE-DOI-ROW-0002")),
        ),
        SyntheticQueueRow(
            OrderId("SYN-ORDER-2"),
            "OTHER_REP",
            SourceRowRefId(EvidenceId("SYN-EVIDENCE-DOI-ROW-0003")),
        ),
    )
    image = SyntheticQueueImage(
        source,
        SOURCE_MAPPING_VERSION,
        SOURCE_ANCHORS,
        NonNegativeCount(3),
        rows,
        "REV-0001",
    )
    result = ingest_synthetic_queue(
        image,
        image,
        candidate_batch_id=SourceBatchId(EvidenceId("SYN-EVIDENCE-DOI-BATCH-0001")),
    )
    assert result.batch is not None
    batch = result.batch
    now = CanonicalTimestamp("2026-08-10T12:00:00Z")
    run_id = RunId("SYN-RUN-DOI-SOURCE-0001")
    invocation_id = RunInvocationId(
        InteractionId("SYN-INTERACTION-DOI-RUN-SOURCE-0001")
    )
    run = DOIRun(
        run_id=run_id,
        invocation_id=invocation_id,
        run_type=RunType.RUN_DOI_REVIEW,
        status=RunStatus.IN_PROGRESS,
        started_at=now,
        completed_at=None,
        purge_eligible_at=None,
        source_batch_id=None,
        recheck_order_id=None,
        counts=DOIRunCounts.empty(source_attempt_count=1),
        terminal_reasons=ReasonSet(),
    )
    run_event = DOIRunEvent(
        run_id,
        PositiveOrdinal(1),
        RunEventKind.RUN_STARTED,
        now,
        RunStatus.IN_PROGRESS,
        ReasonSet(),
    )
    attempt_id = SourceImportAttemptId(
        InteractionId("SYN-INTERACTION-DOI-ATTEMPT-000001")
    )
    attempt = DOISourceImportAttempt(
        attempt_id=attempt_id,
        run_id=run_id,
        ordinal=PositiveOrdinal(1),
        source_identity_id=source,
        state=SourceImportAttemptState.STARTED,
        started_at=now,
        completed_at=None,
        source_batch_id=None,
        reasons=ReasonSet(),
        portal_read_count=NonNegativeCount(0),
    )
    attempt_event = DOISourceImportAttemptEvent(
        attempt_id,
        PositiveOrdinal(1),
        SourceAttemptEventKind.SOURCE_IMPORT_STARTED,
        now,
        ReasonSet(),
        None,
    )
    work_item = DOIRunWorkItem(
        RunWorkItemId(InteractionId("SYN-INTERACTION-DOI-WORK-000001")),
        run_id,
        OrderId("SYN-ORDER-1"),
        RunWorkOrigin.SOURCE_IMPORT,
        batch.batch_id,
    )
    from synthetic_sales_assist.doi.lifecycle import (
        TransitionFixture,
        reduce_fixture_transition,
    )

    lifecycle_fixture = TransitionFixture.legal(
        load_doi_registries().transition_ref("TR-044")
    )
    lifecycle_event = reduce_fixture_transition(
        lifecycle_fixture.stream,
        lifecycle_fixture.command,
        occurred_at=lifecycle_fixture.occurred_at,
    )
    disposition = DOIRunWorkDisposition.exception_or_block(
        work_item=work_item,
        kind=RunWorkDispositionKind.BLOCKED_ORDER,
        portal_read_performed=False,
        lifecycle_event=lifecycle_event.event,
        occurred_at=CanonicalTimestamp("2026-08-10T12:00:45Z"),
        reasons=_reason_set("RC-011"),
    )
    failure_reasons = _reason_set("RC-002", "RC-090")
    terminal_run = replace(
        run,
        status=RunStatus.FAILED,
        completed_at=CanonicalTimestamp("2026-08-10T12:01:00Z"),
        purge_eligible_at=_run_purge_deadline(
            CanonicalTimestamp("2026-08-10T12:01:00Z")
        ),
        terminal_reasons=failure_reasons,
    )
    terminal_event = DOIRunEvent(
        run_id,
        PositiveOrdinal(2),
        RunEventKind.RUN_TERMINAL,
        cast(CanonicalTimestamp, terminal_run.completed_at),
        RunStatus.FAILED,
        failure_reasons,
    )
    command = accept_no_retry_command(
        command_id=AcceptedCommandId(
            InteractionId("SYN-INTERACTION-DOI-COMMAND-NORETRY-0001")
        ),
        run_id=run_id,
        greatest_failed_attempt_id=attempt_id,
        accepted_actor_id=RepId("SYN-REP-AUTHORIZED-0001"),
        accepted_at=cast(CanonicalTimestamp, terminal_run.completed_at),
    )
    no_retry_receipt = NoRetryCommandReceipt(
        CommandReceiptId(EvidenceId("SYN-EVIDENCE-DOI-RECEIPT-000001")),
        command.hash_binding(),
        terminal_run.hash_binding(),
        terminal_event.hash_binding(),
        cast(CanonicalTimestamp, terminal_run.completed_at),
    )
    reservation = ExtractionReservationReceipt(
        CommandReceiptId(EvidenceId("SYN-EVIDENCE-DOI-RECEIPT-000002")),
        run_id,
        ExtractionOccurrenceId(
            InteractionId("SYN-INTERACTION-DOI-OCCURRENCE-0001")
        ),
        CanonicalTimestamp("2026-08-10T12:00:30Z"),
    )
    systemic_reasons = _reason_set("RC-084")
    systemic_run = replace(
        run,
        status=RunStatus.FAILED,
        completed_at=CanonicalTimestamp("2026-08-10T12:00:30Z"),
        purge_eligible_at=_run_purge_deadline(
            CanonicalTimestamp("2026-08-10T12:00:30Z")
        ),
        terminal_reasons=systemic_reasons,
    )
    systemic_event = DOIRunEvent(
        run_id,
        PositiveOrdinal(2),
        RunEventKind.RUN_TERMINAL,
        cast(CanonicalTimestamp, systemic_run.completed_at),
        RunStatus.FAILED,
        systemic_reasons,
    )
    systemic_receipt = PreExtractionRulesUnavailableReceipt(
        CommandReceiptId(EvidenceId("SYN-EVIDENCE-DOI-RECEIPT-000003")),
        systemic_run,
        systemic_event,
    )
    records: tuple[tuple[str, object], ...] = (
        ("DOIStagedOrder", batch.staged_orders[0]),
        ("DOIRejectedSourceRecord", batch.rejected_records[0]),
        ("DOISourceBatch", batch),
        ("SourceImportResult", result),
        ("DOIRunWorkItem", work_item),
        ("DOIRunWorkDisposition", disposition),
        ("DOIRun", run),
        ("DOIRunEvent", run_event),
        ("DOISourceImportAttempt", attempt),
        ("DOISourceImportAttemptEvent", attempt_event),
        ("FinalizeFailedSourceImportNoRetryCommand", command),
        ("NoRetryCommandReceipt", no_retry_receipt),
        ("ExtractionReservationReceipt", reservation),
        ("PreExtractionRulesUnavailableReceipt", systemic_receipt),
    )
    ordinary = tuple(
        (
            name,
            cast(str, getattr(record, "HASH_DOMAIN")),
            record.canonical_bytes(),
            record.hash_binding().sha256,
        )
        for name, record in records
    )
    image_binding = image.content_binding()
    return ordinary + (
        (
            "SyntheticQueueImageContent",
            image_binding.domain,
            image_binding.canonical_bytes,
            image_binding.sha256,
        ),
        (
            "DOISourceBatchIdentity",
            batch.identity.domain,
            batch.identity.canonical_bytes,
            batch.identity.sha256,
        ),
    )


__all__ = [
    "AcceptedActionCommandKind",
    "DOIRejectedSourceRecord",
    "DOIRun",
    "DOIRunCounts",
    "DOIRunEvent",
    "DOIRunWorkDisposition",
    "DOIRunWorkItem",
    "DOISourceBatch",
    "DOISourceError",
    "DOISourceImportAttempt",
    "DOISourceImportAttemptEvent",
    "DOISourceRowCounts",
    "DOIStagedOrder",
    "ExtractionReservationReceipt",
    "FinalizeFailedSourceImportNoRetryCommand",
    "InMemoryDOIRunControl",
    "InMemorySourceBatchRegistry",
    "NoRetryCommandReceipt",
    "ORDER_NUMBER_POLICY_VERSION",
    "PreExtractionRulesUnavailableReceipt",
    "RUN_SCHEMA_VERSION",
    "RunControlConflict",
    "RunControlOperation",
    "RunEventKind",
    "RunStartResult",
    "RunStatus",
    "RunTerminalResult",
    "RunTerminalizationResult",
    "RunType",
    "RunWorkDispositionKind",
    "RunWorkOrigin",
    "SOURCE_ANCHORS",
    "SOURCE_MAPPING_VERSION",
    "SOURCE_QUEUE_SCHEMA_VERSION",
    "SourceAttemptEventKind",
    "SourceBatchStatus",
    "SourceChangeState",
    "SourceCoherenceState",
    "SourceImportAttemptOutcome",
    "SourceImportAttemptState",
    "SourceImportResult",
    "SourceImportResultKind",
    "SourceRejectionOutcome",
    "StagedOrderStatus",
    "SyntheticQueueImage",
    "SyntheticQueueRow",
    "SyntheticQueueTab",
    "TARGET_ASSIGNEE",
    "classify_assignee",
    "accept_no_retry_command",
    "ingest_synthetic_queue",
    "normalize_synthetic_order_number",
    "source_hash_fixture_records",
]
