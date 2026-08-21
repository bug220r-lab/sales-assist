"""Durable retention facades; policy decisions remain in the pure domain reducers."""

from __future__ import annotations

from synthetic_sales_assist.domain.identities import EvidenceId, OrderId
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.persistence.database import SQLiteDatabase
from synthetic_sales_assist.persistence.faults import FaultInjector
from synthetic_sales_assist.persistence.records import SalesCreditPurgeResult
from synthetic_sales_assist.persistence.sales_credit_repository import SalesCreditRepository


class SalesCreditRetentionService:
    def __init__(self, database: SQLiteDatabase) -> None:
        if type(database) is not SQLiteDatabase:
            raise TypeError("DATABASE_INVALID")
        self.database = database

    def purge_eligible_case(
        self,
        *,
        order_id: OrderId,
        now: CanonicalTimestamp,
        fault_injector: FaultInjector | None = None,
    ) -> SalesCreditPurgeResult:
        with self.database.write(fault_injector=fault_injector) as connection:
            return SalesCreditRepository(
                connection,
                fault_injector=fault_injector,
            ).purge_case(order_id=order_id, now=now)

    def purge_eligible_no_order_audit(
        self,
        *,
        audit_id: EvidenceId,
        now: CanonicalTimestamp,
        fault_injector: FaultInjector | None = None,
    ) -> int:
        with self.database.write(fault_injector=fault_injector) as connection:
            return SalesCreditRepository(
                connection,
                fault_injector=fault_injector,
            ).purge_no_order_audit(audit_id=audit_id, now=now)


__all__ = ["SalesCreditRetentionService"]
