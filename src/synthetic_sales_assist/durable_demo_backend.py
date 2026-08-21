"""Concrete local durable backend for every required CLI demonstration alias."""

from __future__ import annotations

import hashlib
import sqlite3
import time
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from threading import Lock

from synthetic_sales_assist.demos import (
    DEMO_CATALOG_VERSION,
    AuditView,
    DemoError,
    DemoRunView,
    demo_descriptor,
    validate_request_key,
)
from synthetic_sales_assist.doi.demo import execute_doi_demo
from synthetic_sales_assist.domain.idempotency import IdempotencyConflictError
from synthetic_sales_assist.domain.identities import (
    EvaluationId,
    EvidenceId,
    OrderId,
    SnapshotId,
)
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.persistence.database import DatabaseError, SQLiteDatabase
from synthetic_sales_assist.persistence.doi_repository import (
    DOIPersistenceConflict,
    DOIPersistenceError,
)
from synthetic_sales_assist.persistence.doi_services import DOIPersistenceService
from synthetic_sales_assist.persistence.sales_credit_repository import (
    SalesCreditPersistenceConflict,
    SalesCreditRepositoryError,
)
from synthetic_sales_assist.persistence.sales_credit_services import (
    SalesCreditPersistenceService,
)
from synthetic_sales_assist.persistence.telemetry import (
    ProcessingResultClass,
    ProcessingTelemetry,
    RulePack,
    TelemetryError,
    record_processing_telemetry,
)
from synthetic_sales_assist.safety.identity import is_reserved_identity
from synthetic_sales_assist.sales_credit.accumulator import CaseMutation
from synthetic_sales_assist.sales_credit.evaluator import (
    KNOWN_OTHER_REP_CATALOG,
    evaluate_sales_credit,
)
from synthetic_sales_assist.sales_credit.fixtures import milestone2_case_mutation
from synthetic_sales_assist.sales_credit.models import SALES_CREDIT_RULE_PACK_VERSION


_DOI_ALIASES = frozenset(
    {
        "doi-fulfillment-split",
        "doi-full-ds",
        "doi-manual-review",
        "doi-overlap",
    }
)
_CONFLICT_ERRORS = (
    IdempotencyConflictError,
    SalesCreditPersistenceConflict,
    DOIPersistenceConflict,
)
_DATABASE_ERRORS = (
    DatabaseError,
    DOIPersistenceError,
    SalesCreditRepositoryError,
    sqlite3.DatabaseError,
)


def _timestamp(value: datetime) -> CanonicalTimestamp:
    if type(value) is not datetime or value.tzinfo is None:
        raise DemoError("DEMO_CLOCK_INVALID")
    rendered = value.astimezone(timezone.utc).isoformat(timespec="microseconds")
    return CanonicalTimestamp(rendered.replace("+00:00", "Z"))


def _instance_digest(alias: str, request_key: str | None) -> str:
    key = alias if request_key is None else request_key
    return hashlib.sha256(f"{alias}\n{key}".encode("ascii")).hexdigest()[:20].upper()


def _sales_credit_mutation(alias: str, instance: str) -> CaseMutation:
    base = milestone2_case_mutation()
    source = base.snapshots[0]
    snapshot = replace(
        source,
        snapshot_id=SnapshotId(f"SYN-SNAPSHOT-M4-SC-{instance}"),
        raw_order_rep=(
            "target_rep"
            if alias == "sales-credit-target-rep"
            else "synthetic_unrecognized_rep"
        ),
    )
    evaluation = evaluate_sales_credit(
        evaluation_id=EvaluationId(f"SYN-EVALUATION-M4-SC-{instance}"),
        expected_order_id=base.order_id,
        snapshot=snapshot,
        evaluated_at=base.occurred_at,
        known_other_reps=KNOWN_OTHER_REP_CATALOG,
        interactions=base.interactions,
    )
    return replace(
        base,
        command_id=EvidenceId(f"SYN-EVIDENCE-M4-SC-COMMAND-{instance}"),
        snapshots=(snapshot,),
        evaluation=evaluation,
    )


class DurableDemoAuditBackend:
    """Compose pure rule execution with SQLite services and closed audit views."""

    def __init__(self, database: SQLiteDatabase) -> None:
        if type(database) is not SQLiteDatabase:
            raise DemoError("DEMO_DATABASE_INVALID")
        self.database = database
        self.sales_credit = SalesCreditPersistenceService(database)
        self.doi = DOIPersistenceService(database)
        self._initialization_lock = Lock()
        self._schema_version: str | None = None

    def _ensure_initialized(self) -> str:
        schema_version = self._schema_version
        if schema_version is not None:
            return schema_version
        with self._initialization_lock:
            schema_version = self._schema_version
            if schema_version is None:
                verification = self.database.initialize()
                schema_version = str(verification.schema_version)
                self._schema_version = schema_version
        return schema_version

    def _record_telemetry(
        self,
        *,
        alias: str,
        rule_pack: RulePack,
        started_at: CanonicalTimestamp,
        ended_at: CanonicalTimestamp,
        extraction_ns: int,
        validation_ns: int,
        rule_ns: int,
        database_ns: int,
        total_ns: int,
        human_review: bool,
        replay: bool,
        result_class: ProcessingResultClass,
        rule_version: str,
        schema_version: str,
        database_error: bool = False,
        error_code: str | None = None,
        operation_id: str | None = None,
    ) -> ProcessingTelemetry:
        telemetry = ProcessingTelemetry(
            operation_id=(
                operation_id
                or f"SYN-EVIDENCE-M4-OPERATION-{uuid.uuid4().hex.upper()}"
            ),
            rule_pack=rule_pack,
            demo_alias=alias,
            started_at=started_at,
            ended_at=ended_at,
            extraction_ns=extraction_ns,
            validation_ns=validation_ns,
            normalization_ns=0,
            rule_ns=rule_ns,
            database_ns=database_ns,
            total_ns=total_ns,
            result_class=result_class,
            human_review=human_review,
            fail_closed=result_class is ProcessingResultClass.FAILED_CLOSED,
            replay=replay,
            conflict=result_class is ProcessingResultClass.CONFLICT,
            database_error=database_error,
            rule_version=rule_version,
            schema_version=schema_version,
            catalog_version=DEMO_CATALOG_VERSION,
            error_code=error_code,
        )
        if operation_id is None:
            with self.database.write() as connection:
                record_processing_telemetry(connection, telemetry)
            return telemetry
        with self.database.write() as connection:
            retained = self._processing_telemetry(connection, operation_id)
            if retained is None:
                record_processing_telemetry(connection, telemetry)
                return telemetry
            expected = replace(
                telemetry,
                started_at=retained.started_at,
                ended_at=retained.ended_at,
                extraction_ns=(
                    telemetry.extraction_ns
                    if alias == "malformed-input"
                    else retained.extraction_ns
                ),
                validation_ns=retained.validation_ns,
                rule_ns=(
                    telemetry.rule_ns
                    if alias == "malformed-input"
                    else retained.rule_ns
                ),
                database_ns=retained.database_ns,
                total_ns=retained.total_ns,
            )
            if retained != expected:
                raise TelemetryError("TELEMETRY_CONFLICT")
            return retained

    @staticmethod
    def _processing_telemetry(
        connection: sqlite3.Connection,
        operation_id: str,
    ) -> ProcessingTelemetry | None:
        rows = connection.execute(
            "SELECT operation_id, rule_pack, demo_alias, started_at, ended_at, "
            "extraction_ns, validation_ns, normalization_ns, rule_ns, "
            "database_ns, total_ns, result_class, human_review, fail_closed, "
            "replay, conflict, database_error, rule_version, schema_version, "
            "catalog_version, error_code FROM processing_telemetry "
            "WHERE operation_id=? LIMIT 2",
            (operation_id,),
        ).fetchall()
        counter_rows = connection.execute(
            "SELECT counter_name, counter_value FROM telemetry_safety_counters "
            "WHERE operation_id=? ORDER BY counter_name",
            (operation_id,),
        ).fetchall()
        if not rows:
            if counter_rows:
                raise TelemetryError("TELEMETRY_RETAINED_INVALID")
            return None
        if len(rows) != 1:
            raise TelemetryError("TELEMETRY_RETAINED_INVALID")
        row = rows[0]
        required_text_indexes = (0, 1, 3, 4, 11, 17, 18)
        optional_text_indexes = (2, 19, 20)
        if (
            any(type(row[index]) is not str for index in required_text_indexes)
            or any(
                row[index] is not None and type(row[index]) is not str
                for index in optional_text_indexes
            )
            or any(
                type(row[index]) is not int or row[index] < 0
                for index in range(5, 11)
            )
            or any(
                type(row[index]) is not int or row[index] not in {0, 1}
                for index in range(12, 17)
            )
            or any(
                type(counter[0]) is not str or type(counter[1]) is not int
                for counter in counter_rows
            )
        ):
            raise TelemetryError("TELEMETRY_RETAINED_INVALID")
        try:
            return ProcessingTelemetry(
                operation_id=row[0],
                rule_pack=RulePack(row[1]),
                demo_alias=row[2],
                started_at=CanonicalTimestamp(row[3]),
                ended_at=CanonicalTimestamp(row[4]),
                extraction_ns=row[5],
                validation_ns=row[6],
                normalization_ns=row[7],
                rule_ns=row[8],
                database_ns=row[9],
                total_ns=row[10],
                result_class=ProcessingResultClass(row[11]),
                human_review=bool(row[12]),
                fail_closed=bool(row[13]),
                replay=bool(row[14]),
                conflict=bool(row[15]),
                database_error=bool(row[16]),
                rule_version=row[17],
                schema_version=row[18],
                catalog_version=row[19],
                error_code=row[20],
                safety_counters=tuple(
                    (counter[0], counter[1]) for counter in counter_rows
                ),
            )
        except (TelemetryError, TypeError, ValueError):
            raise TelemetryError("TELEMETRY_RETAINED_INVALID") from None

    def run_demo(
        self,
        alias: str,
        request_key: str | None,
        *,
        telemetry_operation_id: str | None = None,
        replay_override: bool | None = None,
    ) -> DemoRunView:
        descriptor = demo_descriptor(alias)
        request_key = validate_request_key(request_key)
        if telemetry_operation_id is not None and not is_reserved_identity(
            telemetry_operation_id,
            expected_namespace="EVIDENCE",
        ):
            raise DemoError("DEMO_TELEMETRY_OPERATION_INVALID")
        if replay_override is not None and type(replay_override) is not bool:
            raise DemoError("DEMO_TELEMETRY_REPLAY_INVALID")
        schema_version = self._ensure_initialized()
        started_at = _timestamp(self.database.clock())
        started = time.perf_counter_ns()
        extraction_started = time.perf_counter_ns()
        instance = _instance_digest(alias, request_key)
        extraction_ns = time.perf_counter_ns() - extraction_started
        validation_ns = 0
        rule_ns = 0
        database_ns = 0
        try:
            if alias in {"sales-credit-target-rep", "sales-credit-human-review"}:
                rule_started = time.perf_counter_ns()
                mutation = _sales_credit_mutation(alias, instance)
                rule_ns = time.perf_counter_ns() - rule_started
                evaluation = mutation.evaluation
                if evaluation is None:
                    raise DemoError("SALES_CREDIT_DEMO_EVALUATION_MISSING")
                database_started = time.perf_counter_ns()
                persisted = self.sales_credit.persist_case_mutation(
                    mutation,
                    request_key=request_key or alias,
                )
                database_ns = time.perf_counter_ns() - database_started
                view = DemoRunView(
                    scenario=alias,
                    rule_pack="SALES_CREDIT",
                    synthetic_ids=tuple(
                        sorted(
                            (
                                mutation.order_id.value,
                                *(item.interaction_id.value for item in mutation.interactions),
                            )
                        )
                    ),
                    top_level_result=evaluation.workflow_state.value,
                    workflow_state=evaluation.workflow_state.value,
                    reasons=tuple(item.value for item in evaluation.reasons),
                    opportunities=(),
                    human_review_required=evaluation.human_review_required,
                    run_id=(
                        None
                        if mutation.discovery_run is None
                        else mutation.discovery_run.run_id.value
                    ),
                    evaluation_id=evaluation.evaluation_id.value,
                    case_id=mutation.order_id.value,
                    exact_replay=persisted.replayed,
                    conflict=False,
                    processing_duration_ns=0,
                )
                rule_version = SALES_CREDIT_RULE_PACK_VERSION
            elif alias in _DOI_ALIASES:
                rule_started = time.perf_counter_ns()
                execution = execute_doi_demo(alias, instance_key=instance)
                rule_ns = time.perf_counter_ns() - rule_started
                database_started = time.perf_counter_ns()
                persisted = self.doi.persist_demo(
                    execution,
                    request_key=request_key,
                )
                database_ns = time.perf_counter_ns() - database_started
                evaluation = execution.evaluation
                case = self.doi.get_case(evaluation.order_id.to_json_value())
                if case is None:
                    raise DemoError("DOI_DEMO_CASE_MISSING")
                view = DemoRunView(
                    scenario=alias,
                    rule_pack="DOI",
                    synthetic_ids=(
                        evaluation.order_id.to_json_value(),
                        execution.run_start.run.invocation_id.value.value,
                    ),
                    top_level_result=evaluation.state.value,
                    workflow_state=case.lifecycle_state.value,
                    reasons=tuple(item.code for item in evaluation.reasons.reasons),
                    opportunities=tuple(
                        item.opportunity_type.value for item in evaluation.opportunities
                    ),
                    human_review_required=bool(evaluation.human_review_requirements),
                    run_id=evaluation.run_id.to_json_value(),
                    evaluation_id=evaluation.evaluation_id.value,
                    case_id=case.case_id.value,
                    exact_replay=persisted.replayed,
                    conflict=False,
                    processing_duration_ns=0,
                )
                rule_version = execution.evaluation.rule_pack.version
            elif alias == "malformed-input":
                return self._run_malformed(
                    alias=alias,
                    request_key=request_key,
                    instance=instance,
                    schema_version=schema_version,
                    started=started,
                    started_at=started_at,
                    telemetry_operation_id=telemetry_operation_id,
                    replay_override=replay_override,
                )
            else:
                raise DemoError("DEMO_ALIAS_UNKNOWN")
        except _CONFLICT_ERRORS:
            ended_at = _timestamp(self.database.clock())
            total_ns = time.perf_counter_ns() - started
            self._record_telemetry(
                alias=alias,
                rule_pack=RulePack(descriptor.rule_pack),
                started_at=started_at,
                ended_at=ended_at,
                extraction_ns=extraction_ns,
                validation_ns=validation_ns,
                rule_ns=rule_ns,
                database_ns=database_ns,
                total_ns=total_ns,
                human_review=False,
                replay=False if replay_override is None else replay_override,
                result_class=ProcessingResultClass.CONFLICT,
                rule_version="m4/conflict",
                schema_version=schema_version,
                error_code="IDEMPOTENCY_KEY_MATERIAL_CONFLICT",
                operation_id=telemetry_operation_id,
            )
            raise DemoError("IDEMPOTENCY_KEY_MATERIAL_CONFLICT") from None
        except _DATABASE_ERRORS:
            ended_at = _timestamp(self.database.clock())
            total_ns = time.perf_counter_ns() - started
            try:
                self._record_telemetry(
                    alias=alias,
                    rule_pack=RulePack(descriptor.rule_pack),
                    started_at=started_at,
                    ended_at=ended_at,
                    extraction_ns=extraction_ns,
                    validation_ns=validation_ns,
                    rule_ns=rule_ns,
                    database_ns=database_ns,
                    total_ns=total_ns,
                    human_review=False,
                    replay=False if replay_override is None else replay_override,
                    result_class=ProcessingResultClass.ERROR,
                    rule_version="m4/database-error",
                    schema_version=schema_version,
                    database_error=True,
                    error_code="DEMO_DATABASE_ERROR",
                    operation_id=telemetry_operation_id,
                )
            except (DatabaseError, sqlite3.DatabaseError):
                pass
            raise DemoError("DEMO_DATABASE_ERROR") from None

        ended_at = _timestamp(self.database.clock())
        total_ns = time.perf_counter_ns() - started
        telemetry = self._record_telemetry(
            alias=alias,
            rule_pack=RulePack(descriptor.rule_pack),
            started_at=started_at,
            ended_at=ended_at,
            extraction_ns=extraction_ns,
            validation_ns=validation_ns,
            rule_ns=rule_ns,
            database_ns=database_ns,
            total_ns=total_ns,
            human_review=view.human_review_required,
            replay=(
                view.exact_replay if replay_override is None else replay_override
            ),
            result_class=(
                ProcessingResultClass.HUMAN_REVIEW
                if view.human_review_required
                else ProcessingResultClass.SUCCESS
            ),
            rule_version=rule_version,
            schema_version=schema_version,
            operation_id=telemetry_operation_id,
        )
        return replace(
            view,
            exact_replay=telemetry.replay,
            processing_duration_ns=telemetry.total_ns,
        )

    def _run_malformed(
        self,
        *,
        alias: str,
        request_key: str | None,
        instance: str,
        schema_version: str,
        started: int,
        started_at: CanonicalTimestamp,
        telemetry_operation_id: str | None,
        replay_override: bool | None,
    ) -> DemoRunView:
        validation_started = time.perf_counter_ns()
        try:
            OrderId("not-a-synthetic-order")
        except ValueError:
            pass
        else:
            raise DemoError("MALFORMED_DEMO_VALIDATION_MISSING")
        validation_ns = time.perf_counter_ns() - validation_started
        failure_id = f"SYN-EVIDENCE-M4-MALFORMED-{instance}"
        database_started = time.perf_counter_ns()
        with self.database.write() as connection:
            retained = connection.execute(
                "SELECT error_code FROM structured_domain_failures WHERE failure_id = ?",
                (failure_id,),
            ).fetchone()
            replay = retained is not None
            if retained is not None and str(retained[0]) != "INVALID_ORDER_NUMBER":
                raise DemoError("MALFORMED_FAILURE_CONFLICT")
            if retained is None:
                connection.execute(
                    """
                    INSERT INTO structured_domain_failures (
                        failure_id, command_id, error_code, error_category,
                        retryable, occurred_at
                    ) VALUES (?, NULL, 'INVALID_ORDER_NUMBER', 'VALIDATION', 0, ?)
                    """,
                    (failure_id, started_at.value),
                )
        database_ns = time.perf_counter_ns() - database_started
        ended_at = _timestamp(self.database.clock())
        total_ns = time.perf_counter_ns() - started
        telemetry = self._record_telemetry(
            alias=alias,
            rule_pack=RulePack.DOI,
            started_at=started_at,
            ended_at=ended_at,
            extraction_ns=0,
            validation_ns=validation_ns,
            rule_ns=0,
            database_ns=database_ns,
            total_ns=total_ns,
            human_review=False,
            replay=replay if replay_override is None else replay_override,
            result_class=ProcessingResultClass.FAILED_CLOSED,
            rule_version="doi-malformed-input/v1",
            schema_version=schema_version,
            error_code="INVALID_ORDER_NUMBER",
            operation_id=telemetry_operation_id,
        )
        return DemoRunView(
            scenario=alias,
            rule_pack="DOI",
            synthetic_ids=(failure_id,),
            top_level_result="INVALID_INPUT",
            workflow_state="REJECTED_NO_BUSINESS_PERSISTENCE",
            reasons=("RC-002", "RC-090"),
            opportunities=(),
            human_review_required=False,
            run_id=None,
            evaluation_id=None,
            case_id=None,
            exact_replay=telemetry.replay,
            conflict=False,
            processing_duration_ns=telemetry.total_ns,
        )

    def order_show(self, synthetic_order_id: str) -> AuditView:
        order_id = OrderId(synthetic_order_id)
        sales_case = self.sales_credit.get_case(order_id)
        if sales_case is not None:
            summary = {
                "attribution": sales_case.attribution.value,
                "current_evaluation_id": (
                    None
                    if sales_case.current_evaluation_id is None
                    else sales_case.current_evaluation_id.value
                ),
                "order_id": sales_case.order_id.value,
                "projection_version": sales_case.projection_version,
                "rule_pack": "SALES_CREDIT",
                "state": sales_case.workflow_state.value,
                "updated_at": sales_case.updated_at.value,
                "value_status": sales_case.order_value_status.value,
            }
            return AuditView("ORDER", synthetic_order_id, tuple(sorted(summary.items())))
        doi_case = self.doi.get_case(synthetic_order_id)
        if doi_case is None:
            raise DemoError("ORDER_NOT_FOUND")
        summary = {
            "case_id": doi_case.case_id.value,
            "current_evaluation_id": (
                None
                if doi_case.current_evaluation_id is None
                else doi_case.current_evaluation_id.value
            ),
            "current_snapshot_id": (
                None
                if doi_case.current_snapshot_id is None
                else doi_case.current_snapshot_id.to_json_value()
            ),
            "order_id": doi_case.order_id.to_json_value(),
            "rule_pack": "DOI",
            "state": doi_case.lifecycle_state.value,
            "terminal_closure_reason": (
                None
                if doi_case.terminal_closure_reason is None
                else doi_case.terminal_closure_reason.value
            ),
        }
        return AuditView("ORDER", synthetic_order_id, tuple(sorted(summary.items())))

    def case_history(self, synthetic_order_id: str) -> AuditView:
        order_id = OrderId(synthetic_order_id)
        events = self.sales_credit.case_history(order_id)
        if events:
            rendered = tuple(
                tuple(
                    sorted(
                        {
                            "event_id": item.event_id.value,
                            "event_type": item.event_kind,
                            "state": item.workflow_state.value,
                            "updated_at": item.occurred_at.value,
                        }.items()
                    )
                )
                for item in events
            )
            summary = tuple(
                sorted(
                    {
                        "event_count": len(events),
                        "order_id": synthetic_order_id,
                        "rule_pack": "SALES_CREDIT",
                        "state": events[-1].workflow_state.value,
                    }.items()
                )
            )
            return AuditView("CASE_HISTORY", synthetic_order_id, summary, rendered)
        doi_case = self.doi.get_case(synthetic_order_id)
        if doi_case is None:
            raise DemoError("CASE_NOT_FOUND")
        evaluation = (
            None
            if doi_case.current_evaluation_id is None
            else self.doi.get_evaluation(doi_case.current_evaluation_id.value)
        )
        rendered = ()
        if evaluation is not None:
            rendered = (
                tuple(
                    sorted(
                        {
                            "evaluation_id": evaluation.evaluation_id.value,
                            "event_type": "DOI_EVALUATION",
                            "state": evaluation.state.value,
                            "transition_id": evaluation.transition.transition_id,
                        }.items()
                    )
                ),
            )
        summary = tuple(
            sorted(
                {
                    "case_id": doi_case.case_id.value,
                    "event_count": len(rendered),
                    "order_id": synthetic_order_id,
                    "rule_pack": "DOI",
                    "state": doi_case.lifecycle_state.value,
                }.items()
            )
        )
        return AuditView("CASE_HISTORY", synthetic_order_id, summary, rendered)

    def run_show(self, synthetic_run_id: str) -> AuditView:
        doi_events = self.doi.run_history(synthetic_run_id)
        if doi_events:
            rendered = tuple(
                tuple(
                    sorted(
                        {
                            "event_id": (
                                "SYN-EVIDENCE-M4-DOI-RUN-EVENT-"
                                + item.hash_binding().sha256[:24].upper()
                            ),
                            "event_type": item.event_kind.value,
                            "state": item.status.value,
                            "updated_at": item.occurred_at.value,
                        }.items()
                    )
                )
                for item in doi_events
            )
            summary = tuple(
                sorted(
                    {
                        "event_count": len(rendered),
                        "rule_pack": "DOI",
                        "run_id": synthetic_run_id,
                        "state": doi_events[-1].status.value,
                    }.items()
                )
            )
            return AuditView("RUN", synthetic_run_id, summary, rendered)
        with self.database.read() as connection:
            row = connection.execute(
                """
                SELECT trigger_type, completed_at, enumeration_complete, terminal_outcome
                FROM sc_search_runs WHERE run_id = ?
                """,
                (synthetic_run_id,),
            ).fetchone()
        if row is None:
            raise DemoError("RUN_NOT_FOUND")
        summary = tuple(
            sorted(
                {
                    "event_count": 0,
                    "rule_pack": "SALES_CREDIT",
                    "run_id": synthetic_run_id,
                    "state": str(row[3]),
                    "status": "COMPLETE" if int(row[2]) else "INCOMPLETE",
                    "updated_at": str(row[1]),
                }.items()
            )
        )
        return AuditView("RUN", synthetic_run_id, summary)


__all__ = ["DurableDemoAuditBackend"]
