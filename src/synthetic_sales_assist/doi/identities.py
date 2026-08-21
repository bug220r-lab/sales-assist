"""Semantic DOI identities over the reserved synthetic identity namespaces.

The bundle deliberately reserves only the shared synthetic namespaces.  DOI records therefore
use small semantic wrappers around those primitives instead of inventing new executable
namespaces.  Construction is strict, bounded, and never normalizes rejected material.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Generic, TypeVar

from synthetic_sales_assist.domain.identities import (
    EvidenceId,
    InteractionId,
    OrderId,
    RunId,
    SnapshotId,
)


class DOIIdentityError(ValueError):
    """Reject a semantically mis-namespaced identity without reflecting its value."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"DOI identity rejected: {code}")


_IdentityT = TypeVar(
    "_IdentityT",
    EvidenceId,
    InteractionId,
    OrderId,
    RunId,
    SnapshotId,
)


@dataclass(frozen=True, slots=True, repr=False)
class _SemanticId(Generic[_IdentityT]):
    value: _IdentityT = field(repr=False)

    PRIMITIVE: ClassVar[type[object]]

    def __post_init__(self) -> None:
        if type(self.value) is not self.PRIMITIVE:
            raise DOIIdentityError("semantic_identity_namespace")

    def __str__(self) -> str:
        return self.value.value

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted>)"

    def to_json_value(self) -> str:
        return self.value.value


@dataclass(frozen=True, slots=True, repr=False)
class SourceIdentityId(_SemanticId[EvidenceId]):
    PRIMITIVE: ClassVar[type[object]] = EvidenceId


@dataclass(frozen=True, slots=True, repr=False)
class SourceBatchId(_SemanticId[EvidenceId]):
    PRIMITIVE: ClassVar[type[object]] = EvidenceId


@dataclass(frozen=True, slots=True, repr=False)
class SourceRowRefId(_SemanticId[EvidenceId]):
    PRIMITIVE: ClassVar[type[object]] = EvidenceId


@dataclass(frozen=True, slots=True, repr=False)
class SourceImportAttemptId(_SemanticId[InteractionId]):
    PRIMITIVE: ClassVar[type[object]] = InteractionId


@dataclass(frozen=True, slots=True, repr=False)
class RunInvocationId(_SemanticId[InteractionId]):
    PRIMITIVE: ClassVar[type[object]] = InteractionId


@dataclass(frozen=True, slots=True, repr=False)
class RunWorkItemId(_SemanticId[InteractionId]):
    PRIMITIVE: ClassVar[type[object]] = InteractionId


@dataclass(frozen=True, slots=True, repr=False)
class ExtractionAttemptId(_SemanticId[InteractionId]):
    PRIMITIVE: ClassVar[type[object]] = InteractionId


@dataclass(frozen=True, slots=True, repr=False)
class ExtractionOccurrenceId(_SemanticId[InteractionId]):
    PRIMITIVE: ClassVar[type[object]] = InteractionId


@dataclass(frozen=True, slots=True, repr=False)
class AcceptedCommandId(_SemanticId[InteractionId]):
    PRIMITIVE: ClassVar[type[object]] = InteractionId


@dataclass(frozen=True, slots=True, repr=False)
class CommandReceiptId(_SemanticId[EvidenceId]):
    PRIMITIVE: ClassVar[type[object]] = EvidenceId


@dataclass(frozen=True, slots=True, repr=False)
class LineSnapshotId(_SemanticId[EvidenceId]):
    PRIMITIVE: ClassVar[type[object]] = EvidenceId


@dataclass(frozen=True, slots=True, repr=False)
class DoiOrderId(_SemanticId[OrderId]):
    PRIMITIVE: ClassVar[type[object]] = OrderId


@dataclass(frozen=True, slots=True, repr=False)
class DoiRunId(_SemanticId[RunId]):
    PRIMITIVE: ClassVar[type[object]] = RunId


@dataclass(frozen=True, slots=True, repr=False)
class DoiSnapshotId(_SemanticId[SnapshotId]):
    PRIMITIVE: ClassVar[type[object]] = SnapshotId


__all__ = [
    "AcceptedCommandId",
    "CommandReceiptId",
    "DOIIdentityError",
    "DoiOrderId",
    "DoiRunId",
    "DoiSnapshotId",
    "ExtractionAttemptId",
    "ExtractionOccurrenceId",
    "LineSnapshotId",
    "RunInvocationId",
    "RunWorkItemId",
    "SourceBatchId",
    "SourceIdentityId",
    "SourceImportAttemptId",
    "SourceRowRefId",
]
