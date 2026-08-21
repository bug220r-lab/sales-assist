"""Transactional application services for durable Sales Credit operations."""

from __future__ import annotations

import hashlib

from synthetic_sales_assist.domain.idempotency import NaturalKey
from synthetic_sales_assist.domain.identities import EvidenceId, OrderId
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.persistence.database import SQLiteDatabase
from synthetic_sales_assist.persistence.faults import FaultInjector
from synthetic_sales_assist.persistence.idempotency import SQLiteIdempotencyRepository
from synthetic_sales_assist.persistence.records import (
    DurableCommandResult,
    SalesCreditPurgeResult,
    StoredSalesCreditCase,
    StoredSalesCreditEvent,
)
from synthetic_sales_assist.persistence.projections import (
    ProjectionVerification,
    verify_sales_credit_projections,
)
from synthetic_sales_assist.persistence.sales_credit_repository import SalesCreditRepository
from synthetic_sales_assist.sales_credit.accumulator import CaseMutation, _search_run_bytes
from synthetic_sales_assist.sales_credit.discovery import OrderSearchRun
from synthetic_sales_assist.sales_credit.models import ManagerOutcome
from synthetic_sales_assist.sales_credit.retention import (
    ClosureProjection,
    NoOrderClosureProjection,
)


def _synthetic_id(prefix: str, material: bytes) -> str:
    digest = hashlib.sha256(prefix.encode("ascii") + b"\n" + material).hexdigest().upper()
    return f"SYN-EVIDENCE-M4-{prefix}-{digest[:24]}"


def _request_component(value: str) -> str:
    if type(value) is not str or not 1 <= len(value) <= 128:
        raise ValueError("REQUEST_KEY_INVALID")
    return value


class SalesCreditPersistenceService:
    """Execute each accepted Sales Credit persistence effect in exactly one UoW."""

    def __init__(self, database: SQLiteDatabase) -> None:
        if type(database) is not SQLiteDatabase:
            raise TypeError("DATABASE_INVALID")
        self.database = database

    def persist_case_mutation(
        self,
        mutation: CaseMutation,
        *,
        request_key: str | None = None,
        fault_injector: FaultInjector | None = None,
    ) -> DurableCommandResult:
        if type(mutation) is not CaseMutation:
            raise TypeError("CASE_MUTATION_INVALID")
        material = mutation.canonical_bytes()
        key = _request_component(request_key or mutation.command_id.value)
        command_material = material + key.encode("utf-8")
        with self.database.write(fault_injector=fault_injector) as connection:
            repository = SalesCreditRepository(
                connection,
                fault_injector=fault_injector,
            )
            idempotency = SQLiteIdempotencyRepository(
                connection,
                command_id_factory=lambda: _synthetic_id(
                    "SC-COMMAND",
                    command_material,
                ),
                clock=self.database.clock,
                fault_injector=fault_injector,
            )

            def allocate(
                accepted_command_id: str,
                _recorded_at: CanonicalTimestamp,
            ) -> tuple[str, bytes]:
                repository.append_mutation(
                    mutation,
                    command_id=accepted_command_id,
                    event_id=EvidenceId(
                        _synthetic_id("SC-EVENT", accepted_command_id.encode("ascii"))
                    ),
                )
                if mutation.evaluation is not None:
                    return (
                        mutation.evaluation.HASH_DOMAIN,
                        mutation.evaluation.canonical_bytes(),
                    )
                return (mutation.HASH_DOMAIN, material)

            return idempotency.resolve_or_record(
                natural_key=NaturalKey("sales_credit.case_mutation", (key,)),
                command_domain=mutation.HASH_DOMAIN,
                command_bytes=material,
                owner_domain="SALES_CREDIT",
                owner_id=mutation.order_id.value,
                result_allocator=allocate,
            )

    def persist_interaction_search_result(
        self,
        run: OrderSearchRun,
        *,
        request_key: str | None = None,
        fault_injector: FaultInjector | None = None,
    ) -> DurableCommandResult:
        if type(run) is not OrderSearchRun:
            raise TypeError("SEARCH_RUN_INVALID")
        material = _search_run_bytes(run)
        key = _request_component(request_key or run.run_id.value)
        command_material = material + key.encode("utf-8")
        with self.database.write(fault_injector=fault_injector) as connection:
            repository = SalesCreditRepository(connection, fault_injector=fault_injector)
            idempotency = SQLiteIdempotencyRepository(
                connection,
                command_id_factory=lambda: _synthetic_id(
                    "SC-SEARCH",
                    command_material,
                ),
                clock=self.database.clock,
                fault_injector=fault_injector,
            )

            def allocate(
                _accepted_command_id: str,
                _recorded_at: CanonicalTimestamp,
            ) -> tuple[str, bytes]:
                repository.persist_search_run(run)
                return (run.schema_version, material)

            return idempotency.resolve_or_record(
                natural_key=NaturalKey("sales_credit.search_run", (key,)),
                command_domain=run.schema_version,
                command_bytes=material,
                owner_domain="SYSTEM",
                owner_id=run.run_id.value,
                result_allocator=allocate,
            )

    def record_manager_outcome(
        self,
        *,
        order_id: OrderId,
        outcome: ManagerOutcome,
        request_key: str | None = None,
        fault_injector: FaultInjector | None = None,
    ) -> DurableCommandResult:
        if type(order_id) is not OrderId or type(outcome) is not ManagerOutcome:
            raise TypeError("MANAGER_OUTCOME_INVALID")
        material = outcome.canonical_bytes()
        key = _request_component(request_key or outcome.occurrence_id.value)
        command_material = material + key.encode("utf-8")
        with self.database.write(fault_injector=fault_injector) as connection:
            repository = SalesCreditRepository(connection, fault_injector=fault_injector)
            idempotency = SQLiteIdempotencyRepository(
                connection,
                command_id_factory=lambda: _synthetic_id(
                    "SC-OUTCOME",
                    command_material,
                ),
                clock=self.database.clock,
                fault_injector=fault_injector,
            )

            def allocate(
                accepted_command_id: str,
                _recorded_at: CanonicalTimestamp,
            ) -> tuple[str, bytes]:
                repository.append_manager_outcome(
                    order_id=order_id,
                    outcome=outcome,
                    command_id=accepted_command_id,
                    event_id=EvidenceId(
                        _synthetic_id("SC-EVENT", accepted_command_id.encode("ascii"))
                    ),
                )
                return (outcome.HASH_DOMAIN, material)

            return idempotency.resolve_or_record(
                natural_key=NaturalKey("sales_credit.manager_outcome", (key,)),
                command_domain=outcome.HASH_DOMAIN,
                command_bytes=material,
                owner_domain="SALES_CREDIT",
                owner_id=order_id.value,
                result_allocator=allocate,
            )

    def close_and_minimize_case(
        self,
        *,
        projection: ClosureProjection,
        audit_id: EvidenceId,
        request_key: str | None = None,
        fault_injector: FaultInjector | None = None,
    ) -> DurableCommandResult:
        if type(projection) is not ClosureProjection or type(audit_id) is not EvidenceId:
            raise TypeError("CLOSURE_INVALID")
        material = projection.record.canonical_bytes()
        key = _request_component(request_key or audit_id.value)
        command_material = material + key.encode("utf-8")
        with self.database.write(fault_injector=fault_injector) as connection:
            repository = SalesCreditRepository(connection, fault_injector=fault_injector)
            idempotency = SQLiteIdempotencyRepository(
                connection,
                command_id_factory=lambda: _synthetic_id(
                    "SC-CLOSE",
                    command_material,
                ),
                clock=self.database.clock,
                fault_injector=fault_injector,
            )

            def allocate(
                accepted_command_id: str,
                _recorded_at: CanonicalTimestamp,
            ) -> tuple[str, bytes]:
                repository.close_and_minimize(
                    projection=projection,
                    audit_id=audit_id,
                    command_id=accepted_command_id,
                    event_id=EvidenceId(
                        _synthetic_id("SC-EVENT", accepted_command_id.encode("ascii"))
                    ),
                )
                return (projection.record.HASH_DOMAIN, material)

            return idempotency.resolve_or_record(
                natural_key=NaturalKey("sales_credit.close_case", (key,)),
                command_domain=projection.record.HASH_DOMAIN,
                command_bytes=material,
                owner_domain="SALES_CREDIT",
                owner_id=projection.record.order_id.value,
                result_allocator=allocate,
            )

    def purge_closed_case(
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

    def close_and_minimize_no_order_run(
        self,
        *,
        run: OrderSearchRun,
        projection: NoOrderClosureProjection,
        audit_id: EvidenceId,
        request_key: str | None = None,
        fault_injector: FaultInjector | None = None,
    ) -> DurableCommandResult:
        if (
            type(run) is not OrderSearchRun
            or type(projection) is not NoOrderClosureProjection
            or type(audit_id) is not EvidenceId
        ):
            raise TypeError("NO_ORDER_CLOSURE_INVALID")
        material = projection.record.canonical_bytes()
        key = _request_component(request_key or audit_id.value)
        command_material = material + key.encode("utf-8")
        with self.database.write(fault_injector=fault_injector) as connection:
            repository = SalesCreditRepository(
                connection,
                fault_injector=fault_injector,
            )
            idempotency = SQLiteIdempotencyRepository(
                connection,
                command_id_factory=lambda: _synthetic_id(
                    "SC-NO-ORDER-CLOSE",
                    command_material,
                ),
                clock=self.database.clock,
                fault_injector=fault_injector,
            )

            def allocate(
                accepted_command_id: str,
                _recorded_at: CanonicalTimestamp,
            ) -> tuple[str, bytes]:
                repository.close_no_order(
                    run=run,
                    projection=projection,
                    audit_id=audit_id,
                    command_id=accepted_command_id,
                )
                return (projection.record.HASH_DOMAIN, material)

            return idempotency.resolve_or_record(
                natural_key=NaturalKey("sales_credit.close_no_order", (key,)),
                command_domain=projection.record.HASH_DOMAIN,
                command_bytes=material,
                owner_domain="SYSTEM",
                owner_id=audit_id.value,
                result_allocator=allocate,
            )

    def purge_no_order_audit(
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

    def get_case(self, order_id: OrderId) -> StoredSalesCreditCase | None:
        with self.database.read() as connection:
            return SalesCreditRepository(connection).get_case(order_id)

    def case_history(self, order_id: OrderId) -> tuple[StoredSalesCreditEvent, ...]:
        with self.database.read() as connection:
            return SalesCreditRepository(connection).case_history(order_id)

    def manager_outcomes(
        self,
        order_id: OrderId,
        *,
        limit: int,
    ) -> tuple[ManagerOutcome, ...]:
        with self.database.read() as connection:
            return SalesCreditRepository(connection).manager_outcomes(
                order_id,
                limit=limit,
            )

    def verify_projections(self) -> ProjectionVerification:
        with self.database.read() as connection:
            return verify_sales_credit_projections(connection)


__all__ = ["SalesCreditPersistenceService"]
