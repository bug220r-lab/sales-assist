"""Transactional application services for durable DOI operations."""

from __future__ import annotations

import hashlib

from synthetic_sales_assist.doi.case_attention import CaseOwnerDecision
from synthetic_sales_assist.doi.demo import DOIDemoExecution
from synthetic_sales_assist.doi.extraction import DOIExtractionResult
from synthetic_sales_assist.doi.identities import (
    AcceptedCommandId,
    SourceImportAttemptId,
)
from synthetic_sales_assist.doi.interventions import (
    DOIIntervention,
    DOIResultingOrderLink,
    DOIResultingOrderLinkSearchHistory,
)
from synthetic_sales_assist.doi.knowledge import (
    DOIAlternateObservation,
    DOIAlternateRelationship,
    DOIExactSKUObservation,
)
from synthetic_sales_assist.doi.models import DOIEvaluation, DOIOrderSnapshot
from synthetic_sales_assist.doi.retention import (
    DoiRetentionProjection,
    KPIContributionEvent,
    RetainedKPIContribution,
)
from synthetic_sales_assist.doi.source import (
    DOIRun,
    DOIRunEvent,
    DOIRunWorkDisposition,
    DOIRunWorkItem,
    DOISourceImportAttempt,
    DOISourceImportAttemptEvent,
    ExtractionReservationReceipt,
    FinalizeFailedSourceImportNoRetryCommand,
    NoRetryCommandReceipt,
    PreExtractionRulesUnavailableReceipt,
    RunStartResult,
    SourceImportResult,
)
from synthetic_sales_assist.domain.canonical import (
    canonical_json_bytes,
    domain_hash,
)
from synthetic_sales_assist.domain.idempotency import NaturalKey
from synthetic_sales_assist.domain.identities import EvidenceId, RunId
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.persistence.database import SQLiteDatabase
from synthetic_sales_assist.persistence.doi_repository import (
    DOIRepository,
    PersistenceResult,
    ProjectionVerification,
    PurgeResult,
)
from synthetic_sales_assist.persistence.faults import FaultInjector
from synthetic_sales_assist.persistence.idempotency import SQLiteIdempotencyRepository
from synthetic_sales_assist.persistence.records import DurableCommandResult


def _request_component(value: str) -> str:
    if type(value) is not str or not 1 <= len(value) <= 128:
        raise ValueError("REQUEST_KEY_INVALID")
    return value


def _synthetic_id(prefix: str, material: bytes) -> str:
    digest = hashlib.sha256(prefix.encode("ascii") + b"\n" + material).hexdigest().upper()
    return f"SYN-EVIDENCE-M4-{prefix}-{digest[:24]}"


def _event_identity(event: object) -> str:
    for name in ("event_id", "fact_id", "observation_id", "revision_id"):
        value = getattr(event, name, None)
        if value is None:
            continue
        raw = getattr(value, "value", None)
        if type(raw) is str:
            return raw
        nested = getattr(raw, "value", None)
        if type(nested) is str:
            return nested
    binding = getattr(event, "hash_binding", None)
    if callable(binding):
        return f"SYN-EVIDENCE-M4-DOI-EVENT-{binding().sha256[:24].upper()}"
    raise TypeError("DOI_EVENT_IDENTITY_INVALID")


class DOIPersistenceService:
    """Execute each accepted DOI persistence effect in exactly one SQLite UoW."""

    def __init__(self, database: SQLiteDatabase) -> None:
        if type(database) is not SQLiteDatabase:
            raise TypeError("DATABASE_INVALID")
        self.database = database

    def invoke_run(
        self,
        start: RunStartResult,
        *,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        if type(start) is not RunStartResult:
            raise TypeError("DOI_RUN_START_INVALID")
        with self.database.write(fault_injector=fault_injector) as connection:
            repository = DOIRepository(connection)
            result = repository.persist_run(
                start.run,
                start.run_event,
                fault_injector=fault_injector,
            )
            for item in start.work_items:
                repository.persist_run_work_item(item)
            return result

    def append_snapshot_evaluation(
        self,
        *,
        case_id: EvidenceId,
        snapshot: DOIOrderSnapshot,
        evaluation: DOIEvaluation,
        created_at: CanonicalTimestamp,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        with self.database.write(fault_injector=fault_injector) as connection:
            return DOIRepository(connection).persist_evaluation(
                case_id=case_id,
                snapshot=snapshot,
                evaluation=evaluation,
                created_at=created_at,
                fault_injector=fault_injector,
            )

    def import_source_attempt(
        self,
        attempt: DOISourceImportAttempt,
        event: DOISourceImportAttemptEvent,
        *,
        result: SourceImportResult | None = None,
        run: DOIRun | None = None,
        work_items: tuple[DOIRunWorkItem, ...] = (),
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        with self.database.write(fault_injector=fault_injector) as connection:
            repository = DOIRepository(connection)
            if result is None and run is None and not work_items:
                return repository.persist_source_attempt(attempt, event)
            if result is None or run is None:
                raise TypeError("DOI_SOURCE_IMPORT_GRAPH_INVALID")
            return repository.persist_source_import(
                attempt=attempt,
                event=event,
                result=result,
                run=run,
                work_items=work_items,
            )

    def record_run_work_disposition(
        self,
        disposition: DOIRunWorkDisposition,
        *,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        if type(disposition) is not DOIRunWorkDisposition:
            raise TypeError("DOI_RUN_WORK_DISPOSITION_INVALID")
        with self.database.write(fault_injector=fault_injector) as connection:
            return DOIRepository(connection).persist_run_work_disposition(
                disposition
            )

    def finalize_run_processing(
        self,
        *,
        run: DOIRun,
        event: DOIRunEvent,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        with self.database.write(fault_injector=fault_injector) as connection:
            return DOIRepository(connection).finalize_run_processing(
                run,
                event,
                fault_injector=fault_injector,
            )

    def accept_retry(
        self,
        *,
        command_id: AcceptedCommandId,
        predecessor_attempt_id: SourceImportAttemptId,
        attempt: DOISourceImportAttempt,
        event: DOISourceImportAttemptEvent,
        run: DOIRun,
        accepted_at: CanonicalTimestamp,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        if (
            type(command_id) is not AcceptedCommandId
            or type(predecessor_attempt_id) is not SourceImportAttemptId
            or type(attempt) is not DOISourceImportAttempt
            or type(event) is not DOISourceImportAttemptEvent
            or type(run) is not DOIRun
            or run.run_id != attempt.run_id
            or type(accepted_at) is not CanonicalTimestamp
        ):
            raise TypeError("DOI_RETRY_ACCEPTANCE_INVALID")
        value = {
            "accepted_at": accepted_at.value,
            "command_id": command_id.to_json_value(),
            "predecessor_attempt_id": predecessor_attempt_id.to_json_value(),
            "retry_attempt": attempt.hash_binding().sha256,
            "run_id": attempt.run_id.value,
        }
        material = domain_hash(
            "doi-retry-command/v1",
            canonical_json_bytes(value, expected_members=set(value)),
        )
        with self.database.write(fault_injector=fault_injector) as connection:
            repository = DOIRepository(connection)
            attempt_result = repository.persist_source_attempt(attempt, event)
            receipt = repository.persist_run_control_receipt(
                receipt_id=command_id.to_json_value(),
                run_id=attempt.run_id.value,
                occurrence_key=predecessor_attempt_id.to_json_value(),
                operation="RETRY",
                material=material,
                result=attempt,
                committed_at=accepted_at,
            )
            repository.refresh_in_progress_run(
                run,
                cause_event=event,
                allow_cause_advance=not attempt_result.replayed,
            )
            return receipt

    def explicit_no_retry_finalization(
        self,
        *,
        command: FinalizeFailedSourceImportNoRetryCommand,
        receipt: NoRetryCommandReceipt,
        run: DOIRun,
        event: DOIRunEvent,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        if (
            type(command) is not FinalizeFailedSourceImportNoRetryCommand
            or type(receipt) is not NoRetryCommandReceipt
            or command.run_id != run.run_id
            or receipt.command != command.hash_binding()
            or receipt.run != run.hash_binding()
            or receipt.run_event != event.hash_binding()
        ):
            raise TypeError("DOI_NO_RETRY_FINALIZATION_INVALID")
        with self.database.write(fault_injector=fault_injector) as connection:
            repository = DOIRepository(connection)
            repository.persist_run(
                run,
                event,
                fault_injector=fault_injector,
            )
            return repository.persist_run_control_receipt(
                receipt_id=receipt.receipt_id.to_json_value(),
                run_id=run.run_id.value,
                occurrence_key=command.greatest_failed_attempt_id.to_json_value(),
                operation="NO_RETRY_FINALIZATION",
                material=command.hash_binding(),
                result=receipt,
                committed_at=receipt.accepted_at,
            )

    def reserve_extraction(
        self,
        receipt: ExtractionReservationReceipt,
        *,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        if type(receipt) is not ExtractionReservationReceipt:
            raise TypeError("DOI_EXTRACTION_RESERVATION_INVALID")
        with self.database.write(fault_injector=fault_injector) as connection:
            return DOIRepository(connection).persist_run_control_receipt(
                receipt_id=receipt.receipt_id.to_json_value(),
                run_id=receipt.run_id.value,
                occurrence_key="PRE_EXTRACTION",
                operation="EXTRACTION_RESERVED",
                material=receipt.hash_binding(),
                result=receipt,
                committed_at=receipt.reserved_at,
            )

    def pre_extraction_rules_unavailable(
        self,
        receipt: PreExtractionRulesUnavailableReceipt,
        *,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        if type(receipt) is not PreExtractionRulesUnavailableReceipt:
            raise TypeError("DOI_PRE_EXTRACTION_FAILURE_INVALID")
        with self.database.write(fault_injector=fault_injector) as connection:
            repository = DOIRepository(connection)
            repository.persist_run(
                receipt.run,
                receipt.event,
                fault_injector=fault_injector,
            )
            return repository.persist_run_control_receipt(
                receipt_id=receipt.receipt_id.to_json_value(),
                run_id=receipt.run.run_id.value,
                occurrence_key="PRE_EXTRACTION",
                operation="PRE_EXTRACTION_RULES_UNAVAILABLE",
                material=receipt.hash_binding(),
                result=receipt,
                committed_at=receipt.event.occurred_at,
            )

    def complete_extraction(
        self,
        *,
        case_id: EvidenceId,
        result: DOIExtractionResult,
        created_at: CanonicalTimestamp,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        with self.database.write(fault_injector=fault_injector) as connection:
            return DOIRepository(connection).persist_extraction(
                case_id=case_id,
                result=result,
                created_at=created_at,
            )

    def apply_case_owner_decision(
        self,
        decision: CaseOwnerDecision,
        *,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        if type(decision) is not CaseOwnerDecision:
            raise TypeError("DOI_CASE_OWNER_DECISION_INVALID")
        with self.database.write(fault_injector=fault_injector) as connection:
            return DOIRepository(connection).persist_case_owner_decision(decision)

    def append_relationship_revision(
        self,
        relationship: DOIAlternateRelationship,
        *,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        with self.database.write(fault_injector=fault_injector) as connection:
            return DOIRepository(connection).append_relationship_revision(relationship)

    def append_relationship_observation(
        self,
        observation: DOIAlternateObservation | DOIExactSKUObservation,
        *,
        relationship_id: EvidenceId | None = None,
        case_id: EvidenceId | None = None,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        with self.database.write(fault_injector=fault_injector) as connection:
            return DOIRepository(connection).append_product_observation(
                observation,
                relationship_id=relationship_id,
                case_id=case_id,
            )

    def record_intervention(
        self,
        *,
        case_id: EvidenceId,
        intervention: DOIIntervention,
        created_at: CanonicalTimestamp,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        with self.database.write(fault_injector=fault_injector) as connection:
            return DOIRepository(connection).persist_intervention(
                case_id=case_id,
                intervention=intervention,
                created_at=created_at,
            )

    def append_kpi_contribution(
        self,
        *,
        case_id: EvidenceId,
        event: KPIContributionEvent,
        contribution: RetainedKPIContribution,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        with self.database.write(fault_injector=fault_injector) as connection:
            return DOIRepository(connection).retain_kpi(
                case_id=case_id,
                event=event,
                contribution=contribution,
            )

    def schedule_retention(
        self,
        projection: DoiRetentionProjection,
        *,
        created_at: CanonicalTimestamp,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        with self.database.write(fault_injector=fault_injector) as connection:
            return DOIRepository(connection).schedule_retention(
                projection,
                created_at=created_at,
            )

    def reopen_case(
        self,
        *,
        case_id: EvidenceId,
        canceled_retention: DoiRetentionProjection,
        snapshot: DOIOrderSnapshot,
        evaluation: DOIEvaluation,
        created_at: CanonicalTimestamp,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        """Cancel one exact reversible deadline and append its recheck atomically."""

        reopen_event_id = canceled_retention.canceled_by_reopen_event_id
        if reopen_event_id is None:
            raise TypeError("DOI_REOPEN_EVENT_REQUIRED")
        with self.database.write(fault_injector=fault_injector) as connection:
            repository = DOIRepository(connection)
            repository.cancel_retention_on_reopen(canceled_retention)
            return repository.persist_evaluation(
                case_id=case_id,
                snapshot=snapshot,
                evaluation=evaluation,
                created_at=created_at,
                reopen_event_id=reopen_event_id,
                fault_injector=fault_injector,
            )

    def persist_demo(
        self,
        execution: DOIDemoExecution,
        *,
        request_key: str | None = None,
        fault_injector: FaultInjector | None = None,
    ) -> DurableCommandResult:
        """Atomically persist a real demo run, evaluation graph, and durable receipt."""

        if type(execution) is not DOIDemoExecution:
            raise TypeError("DOI_DEMO_EXECUTION_INVALID")
        evaluation = execution.evaluation
        key = _request_component(
            request_key
            or f"{execution.definition.alias}-{execution.instance_key}"
        )
        command_material = canonical_json_bytes(
            {
                "alias": execution.definition.alias,
                "evaluation": {
                    "domain": evaluation.hash_binding().domain,
                    "sha256": evaluation.hash_binding().sha256,
                },
                "scenario_key": execution.definition.scenario_key,
            },
            expected_members={"alias", "evaluation", "scenario_key"},
        )
        command_id = _synthetic_id(
            "DOI-COMMAND",
            command_material + key.encode("utf-8"),
        )
        case_id = EvidenceId(
            _synthetic_id("DOI-CASE", evaluation.order_id.to_json_value().encode("ascii"))
        )
        with self.database.write(fault_injector=fault_injector) as connection:
            repository = DOIRepository(connection)
            idempotency = SQLiteIdempotencyRepository(
                connection,
                command_id_factory=lambda: command_id,
                clock=self.database.clock,
                fault_injector=fault_injector,
            )

            def allocate(
                _accepted_command_id: str,
                recorded_at: CanonicalTimestamp,
            ) -> tuple[str, bytes]:
                repository.persist_run(
                    execution.run_start.run,
                    execution.run_start.run_event,
                    fault_injector=fault_injector,
                )
                for item in execution.run_start.work_items:
                    repository.persist_run_work_item(item)
                repository.persist_evaluation(
                    case_id=case_id,
                    snapshot=execution.snapshot,
                    evaluation=evaluation,
                    created_at=recorded_at,
                    fault_injector=fault_injector,
                )
                return evaluation.HASH_DOMAIN, evaluation.canonical_bytes()

            return idempotency.resolve_or_record(
                natural_key=NaturalKey("doi.demo", (key,)),
                command_domain="doi-demo-command/v1",
                command_bytes=command_material,
                owner_domain="DOI",
                owner_id=case_id.value,
                result_allocator=allocate,
            )

    def append_owner_operation(
        self,
        *,
        stream_family: str,
        stream_id: str,
        current_state: str,
        event: object,
        occurred_at: CanonicalTimestamp,
        transition_id: str | None = None,
        case_id: EvidenceId | None = None,
        run_id: str | None = None,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        with self.database.write(fault_injector=fault_injector) as connection:
            return DOIRepository(connection).append_owner_event(
                stream_family=stream_family,
                stream_id=stream_id,
                current_state=current_state,
                event_id=_event_identity(event),
                event=event,
                occurred_at=occurred_at,
                transition_id=transition_id,
                case_id=None if case_id is None else case_id.value,
                run_id=run_id,
            )

    def apply_lifecycle_transition(self, **kwargs: object) -> PersistenceResult:
        return self._named_owner_operation("LIFECYCLE", kwargs)

    def set_attention_cause(self, **kwargs: object) -> PersistenceResult:
        return self._named_owner_operation("ATTENTION", kwargs)

    def clear_attention_cause(self, **kwargs: object) -> PersistenceResult:
        return self._named_owner_operation("ATTENTION", kwargs)

    def record_human_fact(self, **kwargs: object) -> PersistenceResult:
        return self._named_owner_operation("HUMAN_FACT", kwargs)

    def record_contact_event(self, **kwargs: object) -> PersistenceResult:
        return self._named_owner_operation("CONTACT", kwargs)

    def record_wwc_event(self, **kwargs: object) -> PersistenceResult:
        return self._named_owner_operation("WWC", kwargs)

    def record_dedupe_event(self, **kwargs: object) -> PersistenceResult:
        return self._named_owner_operation("DEDUPE", kwargs)

    def verify_intervention_action(
        self,
        *,
        case_id: EvidenceId,
        intervention: DOIIntervention,
        created_at: CanonicalTimestamp,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        return self.record_intervention(
            case_id=case_id,
            intervention=intervention,
            created_at=created_at,
            fault_injector=fault_injector,
        )

    def append_value_event(
        self,
        *,
        case_id: EvidenceId,
        intervention: DOIIntervention,
        created_at: CanonicalTimestamp,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        return self.record_intervention(
            case_id=case_id,
            intervention=intervention,
            created_at=created_at,
            fault_injector=fault_injector,
        )

    def search_resulting_order(
        self,
        *,
        case_id: EvidenceId,
        history: DOIResultingOrderLinkSearchHistory,
        created_at: CanonicalTimestamp,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        with self.database.write(fault_injector=fault_injector) as connection:
            return DOIRepository(connection).persist_resulting_search(
                case_id=case_id,
                history=history,
                created_at=created_at,
            )

    def link_resulting_order(
        self,
        *,
        case_id: EvidenceId,
        link: DOIResultingOrderLink,
        created_at: CanonicalTimestamp,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        with self.database.write(fault_injector=fault_injector) as connection:
            return DOIRepository(connection).persist_resulting_link(
                case_id=case_id,
                link=link,
                created_at=created_at,
            )

    def _named_owner_operation(
        self,
        family: str,
        values: dict[str, object],
    ) -> PersistenceResult:
        accepted = dict(values)
        accepted["stream_family"] = family
        return self.append_owner_operation(**accepted)  # type: ignore[arg-type]

    def finalize_kpi_and_purge_case(
        self,
        case_id: EvidenceId,
        *,
        now: CanonicalTimestamp,
        fault_injector: FaultInjector | None = None,
    ) -> PurgeResult:
        with self.database.write(fault_injector=fault_injector) as connection:
            return DOIRepository(connection).purge_case(
                case_id,
                now=now,
                fault_injector=fault_injector,
            )

    def purge_terminal_run(
        self,
        run_id: RunId,
        *,
        now: CanonicalTimestamp,
        fault_injector: FaultInjector | None = None,
    ) -> PersistenceResult:
        if type(run_id) is not RunId:
            raise TypeError("DOI_RUN_PURGE_ID_INVALID")
        with self.database.write(fault_injector=fault_injector) as connection:
            return DOIRepository(connection).purge_terminal_run(
                run_id.value,
                now=now,
                fault_injector=fault_injector,
            )

    def get_evaluation(self, evaluation_id: str) -> DOIEvaluation | None:
        with self.database.read() as connection:
            return DOIRepository(connection).get_evaluation(evaluation_id)

    def get_case(self, order_id: str):  # type: ignore[no-untyped-def]
        with self.database.read() as connection:
            return DOIRepository(connection).get_case(order_id)

    def run_history(self, run_id: str):  # type: ignore[no-untyped-def]
        with self.database.read() as connection:
            return DOIRepository(connection).run_history(run_id)

    def verify_projections(self) -> ProjectionVerification:
        with self.database.read() as connection:
            return DOIRepository(connection).verify_projections()

    def identity_occurrences(self, value: str) -> int:
        with self.database.read() as connection:
            return DOIRepository(connection).identity_occurrences(value)
DOITransactionalService = DOIPersistenceService


__all__ = [
    "DOIPersistenceService",
    "DOITransactionalService",
]
