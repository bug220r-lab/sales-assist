"""Closed deterministic fault checkpoints for transactional persistence tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from synthetic_sales_assist.domain.tokens import ImmutableStrEnum


class FaultPoint(ImmutableStrEnum):
    AFTER_FIRST_INSERT = "AFTER_FIRST_INSERT"
    BEFORE_EVENT_APPEND = "BEFORE_EVENT_APPEND"
    AFTER_EVENT_BEFORE_PROJECTION = "AFTER_EVENT_BEFORE_PROJECTION"
    AFTER_PROJECTION_BEFORE_RECEIPT = "AFTER_PROJECTION_BEFORE_RECEIPT"
    BEFORE_COMMIT = "BEFORE_COMMIT"
    DURING_KPI_FINALIZATION = "DURING_KPI_FINALIZATION"
    DURING_CASE_PURGE = "DURING_CASE_PURGE"
    DURING_BACKUP_RECEIPT = "DURING_BACKUP_RECEIPT"
    DURING_RESTORE_SWAP = "DURING_RESTORE_SWAP"


class InjectedPersistenceFault(RuntimeError):
    """Raised without payload when a configured deterministic checkpoint is hit."""

    def __init__(self, point: FaultPoint) -> None:
        self.point = point
        super().__init__(f"INJECTED_{point.value}")


@dataclass(slots=True)
class FaultInjector:
    """Inject each configured point once and retain only closed checkpoint names."""

    points: frozenset[FaultPoint] = frozenset()
    _triggered: set[FaultPoint] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.points) is not frozenset or any(
            type(point) is not FaultPoint for point in self.points
        ):
            raise TypeError("FAULT_INJECTOR_POINTS_INVALID")

    def hit(self, point: FaultPoint) -> None:
        if type(point) is not FaultPoint:
            raise TypeError("FAULT_POINT_INVALID")
        if point in self.points and point not in self._triggered:
            self._triggered.add(point)
            raise InjectedPersistenceFault(point)


NO_FAULTS = FaultInjector()


__all__ = [
    "FaultInjector",
    "FaultPoint",
    "InjectedPersistenceFault",
    "NO_FAULTS",
]
