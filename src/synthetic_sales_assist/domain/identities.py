"""Immutable, namespace-distinct synthetic identity primitives."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import ClassVar

from synthetic_sales_assist.safety.identity import (
    IdentityFirewallError,
    assert_reserved_identity,
)


MAX_TYPED_ID_LENGTH = 128


class DomainIdentityError(ValueError):
    """Reject invalid identity material without retaining or echoing the input."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"typed synthetic identity rejected: {code}")


@dataclass(frozen=True, slots=True, repr=False)
class _TypedId:
    value: str = field(repr=False)

    NAMESPACE: ClassVar[str]

    def __post_init__(self) -> None:
        if type(self.value) is not str:
            raise DomainIdentityError("identity_type")
        if len(self.value) > MAX_TYPED_ID_LENGTH:
            raise DomainIdentityError("identity_length")
        identity_invalid = False
        try:
            assert_reserved_identity(self.value, expected_namespace=self.NAMESPACE)
        except IdentityFirewallError:
            identity_invalid = True
        if identity_invalid:
            raise DomainIdentityError("identity_format_or_namespace")

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted>)"

    def to_json_value(self) -> str:
        """Return the immutable JSON string representation."""

        return self.value

    def to_sqlite_value(self) -> str:
        """Return the bounded SQLite text representation."""

        return self.value


@dataclass(frozen=True, slots=True, repr=False)
class CustomerId(_TypedId):
    NAMESPACE: ClassVar[str] = "CUSTOMER"


@dataclass(frozen=True, slots=True, repr=False)
class OrderId(_TypedId):
    NAMESPACE: ClassVar[str] = "ORDER"


@dataclass(frozen=True, slots=True, repr=False)
class SkuId(_TypedId):
    NAMESPACE: ClassVar[str] = "SKU"


@dataclass(frozen=True, slots=True, repr=False)
class InteractionId(_TypedId):
    NAMESPACE: ClassVar[str] = "INTERACTION"


@dataclass(frozen=True, slots=True, repr=False)
class ConversationId(_TypedId):
    NAMESPACE: ClassVar[str] = "CONVERSATION"


@dataclass(frozen=True, slots=True, repr=False)
class SnapshotId(_TypedId):
    NAMESPACE: ClassVar[str] = "SNAPSHOT"


@dataclass(frozen=True, slots=True, repr=False)
class EvaluationId(_TypedId):
    NAMESPACE: ClassVar[str] = "EVALUATION"


@dataclass(frozen=True, slots=True, repr=False)
class RunId(_TypedId):
    NAMESPACE: ClassVar[str] = "RUN"


@dataclass(frozen=True, slots=True, repr=False)
class RepId(_TypedId):
    NAMESPACE: ClassVar[str] = "REP"


@dataclass(frozen=True, slots=True, repr=False)
class EvidenceId(_TypedId):
    NAMESPACE: ClassVar[str] = "EVIDENCE"


type TypedId = (
    CustomerId
    | OrderId
    | SkuId
    | InteractionId
    | ConversationId
    | SnapshotId
    | EvaluationId
    | RunId
    | RepId
    | EvidenceId
)

TYPED_ID_CLASSES: tuple[type[_TypedId], ...] = (
    CustomerId,
    OrderId,
    SkuId,
    InteractionId,
    ConversationId,
    SnapshotId,
    EvaluationId,
    RunId,
    RepId,
    EvidenceId,
)
ID_CLASS_BY_NAMESPACE: Mapping[str, type[_TypedId]] = MappingProxyType(
    {identity_type.NAMESPACE: identity_type for identity_type in TYPED_ID_CLASSES}
)


__all__ = [
    "ConversationId",
    "CustomerId",
    "DomainIdentityError",
    "EvaluationId",
    "EvidenceId",
    "ID_CLASS_BY_NAMESPACE",
    "InteractionId",
    "MAX_TYPED_ID_LENGTH",
    "OrderId",
    "RepId",
    "RunId",
    "SkuId",
    "SnapshotId",
    "TYPED_ID_CLASSES",
    "TypedId",
]
