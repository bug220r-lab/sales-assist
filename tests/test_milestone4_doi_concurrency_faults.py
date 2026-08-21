from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from synthetic_sales_assist.doi.demo import execute_doi_demo
from synthetic_sales_assist.doi.evaluator import evaluate_doi
from synthetic_sales_assist.doi.identities import RunInvocationId
from synthetic_sales_assist.doi.models import OrderState
from synthetic_sales_assist.doi.retention import calendar90, schedule_retention
from synthetic_sales_assist.doi.source import (
    InMemoryDOIRunControl,
    RunType,
)
from synthetic_sales_assist.domain.idempotency import IdempotencyConflictError
from synthetic_sales_assist.domain.identities import (
    EvidenceId,
    InteractionId,
)
from synthetic_sales_assist.persistence.database import SQLiteDatabase
from synthetic_sales_assist.persistence.doi_services import DOIPersistenceService
from synthetic_sales_assist.persistence.faults import (
    FaultInjector,
    FaultPoint,
    InjectedPersistenceFault,
)
from tests.test_doi_evaluator import evaluation_input, split_lines


class Milestone4DOIConcurrencyFaultTests(unittest.TestCase):
    def _database(self) -> tuple[tempfile.TemporaryDirectory[str], SQLiteDatabase]:
        temporary = tempfile.TemporaryDirectory()
        path = Path(temporary.name) / "doi.sqlite3"
        database = SQLiteDatabase(path, busy_timeout_ms=10_000)
        database.initialize()
        return temporary, database

    def test_two_exact_concurrent_requests_commit_one_evaluation(self) -> None:
        temporary, database = self._database()
        self.addCleanup(temporary.cleanup)
        execution = execute_doi_demo(
            "doi-overlap",
            instance_key="concurrent-exact",
        )

        def persist() -> bool:
            service = DOIPersistenceService(SQLiteDatabase(database.path))
            return service.persist_demo(
                execution,
                request_key="concurrent-request",
            ).replayed

        with ThreadPoolExecutor(max_workers=2) as pool:
            replay_flags = sorted(pool.map(lambda _: persist(), range(2)))
        self.assertEqual(replay_flags, [False, True])
        with database.read() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM doi_evaluations").fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM durable_commands").fetchone()[0],
                1,
            )

    def test_same_request_key_with_changed_material_fails(self) -> None:
        temporary, database = self._database()
        self.addCleanup(temporary.cleanup)
        service = DOIPersistenceService(database)
        service.persist_demo(
            execute_doi_demo("doi-full-ds", instance_key="conflict-a"),
            request_key="same-key",
        )
        with self.assertRaises(IdempotencyConflictError):
            service.persist_demo(
                execute_doi_demo("doi-overlap", instance_key="conflict-b"),
                request_key="same-key",
            )

    def test_distinct_instance_keys_persist_distinct_evaluations(self) -> None:
        temporary, database = self._database()
        self.addCleanup(temporary.cleanup)
        service = DOIPersistenceService(database)
        for index in range(20):
            execution = execute_doi_demo(
                "doi-fulfillment-split",
                instance_key=f"benchmark-{index:04d}",
            )
            self.assertFalse(service.persist_demo(execution).replayed)
        with database.read() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM doi_evaluations").fetchone()[0],
                20,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM doi_cases").fetchone()[0],
                20,
            )

    def test_each_major_fault_checkpoint_rolls_back_all_rows(self) -> None:
        checkpoints = (
            FaultPoint.AFTER_FIRST_INSERT,
            FaultPoint.BEFORE_EVENT_APPEND,
            FaultPoint.AFTER_EVENT_BEFORE_PROJECTION,
            FaultPoint.AFTER_PROJECTION_BEFORE_RECEIPT,
            FaultPoint.BEFORE_COMMIT,
        )
        for checkpoint in checkpoints:
            with self.subTest(checkpoint=checkpoint.value):
                temporary, database = self._database()
                try:
                    service = DOIPersistenceService(database)
                    with self.assertRaises(InjectedPersistenceFault):
                        service.persist_demo(
                            execute_doi_demo(
                                "doi-fulfillment-split",
                                instance_key=f"fault-{checkpoint.value.lower()}",
                            ),
                            fault_injector=FaultInjector(frozenset({checkpoint})),
                        )
                    with database.read() as connection:
                        for table in (
                            "durable_commands",
                            "doi_runs",
                            "doi_run_events",
                            "doi_cases",
                            "doi_evaluations",
                        ):
                            self.assertEqual(
                                connection.execute(
                                    f'SELECT COUNT(*) FROM "{table}"'
                                ).fetchone()[0],
                                0,
                                table,
                            )
                finally:
                    temporary.cleanup()

    def _closed_case(
        self,
        database: SQLiteDatabase,
    ) -> tuple[DOIPersistenceService, EvidenceId, str]:
        request = evaluation_input(
            split_lines(),
            evaluation_suffix="M4-PURGE",
            order_state=OrderState.SHIPPED,
        )
        evaluation = evaluate_doi(request)
        control = InMemoryDOIRunControl()
        start = control.begin_recheck_run(
            run_id=evaluation.run_id.value,
            invocation_id=RunInvocationId(
                InteractionId("SYN-INTERACTION-DOI-M4-PURGE-RUN")
            ),
            run_type=RunType.RECHECK_ORDER,
            order_id=evaluation.order_id.value,
            accepted_at=request.evaluated_at,
        )
        service = DOIPersistenceService(database)
        service.invoke_run(start)
        case_id = EvidenceId("SYN-EVIDENCE-DOI-M4-PURGE-CASE")
        service.append_snapshot_evaluation(
            case_id=case_id,
            snapshot=request.snapshot,
            evaluation=evaluation,
            created_at=request.evaluated_at,
        )
        assert evaluation.closure_proposal is not None
        retention = schedule_retention(
            case_id=case_id,
            closure_event_id=EvidenceId("SYN-EVIDENCE-DOI-M4-PURGE-CLOSURE"),
            lifecycle_state=evaluation.closure_proposal.lifecycle_state,
            closure_reason=evaluation.closure_proposal.reason,
            closed_at=request.evaluated_at,
            projection_revision=1,
            projection_sha256=evaluation.hash_binding().sha256,
        )
        service.schedule_retention(retention, created_at=request.evaluated_at)
        return service, case_id, evaluation.order_id.to_json_value()

    def test_purge_fault_rolls_back_then_retry_removes_identity_graph(self) -> None:
        temporary, database = self._database()
        self.addCleanup(temporary.cleanup)
        service, case_id, order_id = self._closed_case(database)
        deadline = calendar90(
            evaluation_input(
                split_lines(),
                evaluation_suffix="M4-PURGE",
            ).evaluated_at
        )
        self.assertGreater(service.identity_occurrences(order_id), 0)
        with self.assertRaises(InjectedPersistenceFault):
            service.finalize_kpi_and_purge_case(
                case_id,
                now=deadline,
                fault_injector=FaultInjector(
                    frozenset({FaultPoint.DURING_CASE_PURGE})
                ),
            )
        self.assertGreater(service.identity_occurrences(order_id), 0)
        purged = service.finalize_kpi_and_purge_case(case_id, now=deadline)
        self.assertTrue(purged.deleted)
        self.assertEqual(service.identity_occurrences(order_id), 0)
        replay = service.finalize_kpi_and_purge_case(case_id, now=deadline)
        self.assertFalse(replay.deleted)


if __name__ == "__main__":
    unittest.main()
