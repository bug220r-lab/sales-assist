from __future__ import annotations

import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

from synthetic_sales_assist.demos import DemoError
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.durable_demo_backend import DurableDemoAuditBackend
from synthetic_sales_assist.persistence.database import SQLiteDatabase
from synthetic_sales_assist.persistence.sales_credit_repository import (
    SalesCreditRepositoryError,
)
from synthetic_sales_assist.persistence.telemetry import (
    SAFETY_COUNTER_NAMES,
    ProcessingResultClass,
    ProcessingTelemetry,
    RulePack,
    TelemetryError,
    aggregate_processing_telemetry,
    record_processing_telemetry,
)


def _telemetry(index: int, *, replay: bool = False) -> ProcessingTelemetry:
    return ProcessingTelemetry(
        operation_id=f"SYN-EVIDENCE-M4-TELEMETRY-{index:04d}",
        rule_pack=RulePack.SALES_CREDIT if index % 2 else RulePack.DOI,
        demo_alias="sales-credit-target-rep" if index % 2 else "doi-full-ds",
        started_at=CanonicalTimestamp(f"2026-08-21T00:00:{index:02d}Z"),
        ended_at=CanonicalTimestamp(f"2026-08-21T00:00:{index:02d}.1Z"),
        extraction_ns=10,
        validation_ns=20,
        normalization_ns=30,
        rule_ns=40,
        database_ns=index * 10,
        total_ns=index * 100,
        result_class=ProcessingResultClass.SUCCESS,
        human_review=False,
        fail_closed=False,
        replay=replay,
        conflict=False,
        database_error=False,
        rule_version="m4/v1",
        schema_version="4",
        catalog_version="catalog/v1",
        error_code=None,
    )


class Milestone4TelemetryTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="synthetic-sales-assist-m4-telemetry-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_persisted_telemetry_has_exact_closed_counters_and_aggregates(self) -> None:
        database = SQLiteDatabase(self.root / "telemetry.sqlite3")
        database.initialize()
        with database.write() as connection:
            for index in range(1, 5):
                record_processing_telemetry(connection, _telemetry(index, replay=index == 4))

        with database.read() as connection:
            summary = aggregate_processing_telemetry(connection)
            columns = tuple(
                str(row[1])
                for row in connection.execute("PRAGMA table_info(processing_telemetry)")
            )
            counters = connection.execute(
                "SELECT counter_name, counter_value FROM telemetry_safety_counters "
                "ORDER BY operation_id, counter_name"
            ).fetchall()

        self.assertEqual(summary.total_processed, 4)
        self.assertEqual(summary.success_count, 4)
        self.assertEqual(summary.exact_replay_count, 1)
        self.assertEqual(summary.median_latency_ns, 250)
        self.assertEqual(summary.p95_latency_ns, 400)
        self.assertEqual(
            summary.safety_counters,
            tuple((name, 0) for name in SAFETY_COUNTER_NAMES),
        )
        self.assertNotIn("payload", columns)
        self.assertEqual(len(counters), 4 * 9)
        self.assertTrue(all(int(row[1]) == 0 for row in counters))

    def test_telemetry_is_append_only_and_rejects_nonzero_safety_snapshot(self) -> None:
        database = SQLiteDatabase(self.root / "telemetry.sqlite3")
        database.initialize()
        with database.write() as connection:
            record_processing_telemetry(connection, _telemetry(1))
        with self.assertRaisesRegex(sqlite3.IntegrityError, "IMMUTABLE_PROCESSING_TELEMETRY"):
            with database.write() as connection:
                connection.execute(
                    "UPDATE processing_telemetry SET total_ns = total_ns + 1 "
                    "WHERE operation_id = 'SYN-EVIDENCE-M4-TELEMETRY-0001'"
                )

        with self.assertRaisesRegex(TelemetryError, "SAFETY_COUNTER_SNAPSHOT_INVALID"):
            replace(
                _telemetry(2),
                safety_counters=((SAFETY_COUNTER_NAMES[0], 1),),
            )

    def test_recoverable_database_failure_records_closed_error_telemetry(self) -> None:
        database = SQLiteDatabase(self.root / "database-error.sqlite3")
        database.initialize()
        backend = DurableDemoAuditBackend(database)
        backend.sales_credit.persist_case_mutation = Mock(
            side_effect=SalesCreditRepositoryError("SYNTHETIC_DATABASE_FAILURE")
        )
        with self.assertRaisesRegex(DemoError, "DEMO_DATABASE_ERROR"):
            backend.run_demo("sales-credit-target-rep", "database-error")

        with database.read() as connection:
            row = connection.execute(
                """
                SELECT result_class, database_error, error_code
                FROM processing_telemetry
                ORDER BY operation_id
                """
            ).fetchone()
            summary = aggregate_processing_telemetry(connection)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(tuple(row), ("ERROR", 1, "DEMO_DATABASE_ERROR"))
        self.assertEqual(summary.database_error_count, 1)


if __name__ == "__main__":
    unittest.main()
