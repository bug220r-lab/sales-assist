from __future__ import annotations

import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from synthetic_sales_assist.domain.identities import EvidenceId
from synthetic_sales_assist.persistence.database import DatabaseBusyError, SQLiteDatabase
from synthetic_sales_assist.persistence.faults import (
    FaultInjector,
    FaultPoint,
    InjectedPersistenceFault,
)
from synthetic_sales_assist.persistence.sales_credit_services import (
    SalesCreditPersistenceService,
)
from synthetic_sales_assist.sales_credit.fixtures import milestone2_case_mutation


FIXED_TIME = datetime(2026, 8, 21, 19, 0, tzinfo=timezone.utc)


class Milestone4SalesCreditConcurrencyFaultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ssa-m4-sc-races-")
        self.addCleanup(self.temporary.cleanup)
        self.database = SQLiteDatabase(
            Path(self.temporary.name) / "concurrency.sqlite3",
            clock=lambda: FIXED_TIME,
        )
        self.database.initialize()
        self.service = SalesCreditPersistenceService(self.database)

    def test_two_exact_concurrent_writers_commit_once_and_replay_once(self) -> None:
        mutation = milestone2_case_mutation()
        barrier = threading.Barrier(2)

        def persist():
            barrier.wait(timeout=5)
            return self.service.persist_case_mutation(
                mutation,
                request_key="concurrent-exact",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(executor.map(lambda _index: persist(), range(2)))

        self.assertEqual(sorted(result.replayed for result in results), [False, True])
        self.assertEqual(results[0].command_id, results[1].command_id)
        self.assertEqual(len(self.service.case_history(mutation.order_id)), 1)
        with self.database.read() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM durable_commands").fetchone()[0],
                1,
            )

    def test_concurrent_distinct_writers_preserve_sequence_and_predecessor(self) -> None:
        first = milestone2_case_mutation()
        second = replace(
            first,
            command_id=EvidenceId("SYN-EVIDENCE-M4-CONCURRENT-COMMAND-0002"),
        )
        barrier = threading.Barrier(2)

        def persist(item):
            mutation, key = item
            barrier.wait(timeout=5)
            return self.service.persist_case_mutation(mutation, request_key=key)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(
                executor.map(
                    persist,
                    ((first, "writer-one"), (second, "writer-two")),
                )
            )
        self.assertTrue(all(not result.replayed for result in results))
        history = self.service.case_history(first.order_id)
        self.assertEqual(tuple(item.sequence for item in history), (1, 2))
        self.assertEqual(history[1].predecessor_event_id, history[0].event_id)
        self.assertTrue(self.service.verify_projections().valid)

    def test_concurrent_readers_observe_valid_typed_projection(self) -> None:
        mutation = milestone2_case_mutation()
        self.service.persist_case_mutation(mutation)
        barrier = threading.Barrier(4)

        def read_case(_index: int):
            barrier.wait(timeout=5)
            return self.service.get_case(mutation.order_id)

        with ThreadPoolExecutor(max_workers=4) as executor:
            cases = tuple(executor.map(read_case, range(4)))
        self.assertTrue(all(case == cases[0] for case in cases))
        self.assertIsNotNone(cases[0])

    def test_bounded_busy_timeout_fails_closed_without_partial_write(self) -> None:
        mutation = milestone2_case_mutation()
        busy_database = SQLiteDatabase(
            self.database.path,
            busy_timeout_ms=20,
            clock=lambda: FIXED_TIME,
        )
        busy_service = SalesCreditPersistenceService(busy_database)
        with self.database.write():
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(busy_service.persist_case_mutation, mutation)
                with self.assertRaises(DatabaseBusyError):
                    future.result(timeout=5)
        self.assertIsNone(self.service.get_case(mutation.order_id))

    def test_bounded_busy_wait_retries_and_commits_once_after_lock_release(self) -> None:
        mutation = milestone2_case_mutation()
        busy_database = SQLiteDatabase(
            self.database.path,
            busy_timeout_ms=2_000,
            clock=lambda: FIXED_TIME,
        )
        busy_service = SalesCreditPersistenceService(busy_database)
        begin_attempted = threading.Event()
        worker_finished = threading.Event()
        original_connect = sqlite3.connect

        class ObservedConnection(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                if sql.strip().upper() == "BEGIN IMMEDIATE":
                    begin_attempted.set()
                return super().execute(sql, parameters)

        def observed_connect(*args, **kwargs):
            return original_connect(*args, factory=ObservedConnection, **kwargs)

        holder = original_connect(
            self.database.path,
            timeout=2.0,
            isolation_level=None,
        )
        try:
            holder.execute("BEGIN IMMEDIATE")

            def persist():
                try:
                    return busy_service.persist_case_mutation(
                        mutation,
                        request_key="busy-wait-success",
                    )
                finally:
                    worker_finished.set()

            with patch(
                "synthetic_sales_assist.persistence.database.sqlite3.connect",
                side_effect=observed_connect,
            ):
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(persist)
                    try:
                        self.assertTrue(begin_attempted.wait(timeout=2))
                        self.assertFalse(worker_finished.wait(timeout=0.05))
                    finally:
                        if holder.in_transaction:
                            holder.commit()
                    result = future.result(timeout=5)
        finally:
            if holder.in_transaction:
                holder.rollback()
            holder.close()

        self.assertFalse(result.replayed)
        replay = busy_service.persist_case_mutation(
            mutation,
            request_key="busy-wait-success",
        )
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.command_id, result.command_id)
        self.assertEqual(len(self.service.case_history(mutation.order_id)), 1)
        with self.database.read() as connection:
            counts = tuple(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "durable_commands",
                    "durable_command_receipts",
                    "sc_cases",
                    "sc_case_events",
                )
            )
        self.assertEqual(counts, (1, 1, 1, 1))

    def test_each_sales_credit_transaction_checkpoint_rolls_back_every_effect(self) -> None:
        mutation = milestone2_case_mutation()
        points = (
            FaultPoint.BEFORE_EVENT_APPEND,
            FaultPoint.AFTER_EVENT_BEFORE_PROJECTION,
            FaultPoint.AFTER_PROJECTION_BEFORE_RECEIPT,
            FaultPoint.BEFORE_COMMIT,
        )
        for index, point in enumerate(points, start=1):
            with self.subTest(point=point.value):
                database = SQLiteDatabase(
                    Path(self.temporary.name) / f"fault-{index}.sqlite3",
                    clock=lambda: FIXED_TIME,
                )
                database.initialize()
                service = SalesCreditPersistenceService(database)
                with self.assertRaises(InjectedPersistenceFault):
                    service.persist_case_mutation(
                        mutation,
                        request_key=f"fault-{index}",
                        fault_injector=FaultInjector(frozenset({point})),
                    )
                with database.read() as connection:
                    counts = tuple(
                        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                        for table in (
                            "durable_commands",
                            "durable_command_receipts",
                            "sc_cases",
                            "sc_case_events",
                            "sc_snapshots",
                            "sc_evaluations",
                        )
                    )
                self.assertEqual(counts, (0, 0, 0, 0, 0, 0))


if __name__ == "__main__":
    unittest.main()
