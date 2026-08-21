from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from synthetic_sales_assist.benchmark import run_persistence_benchmark
from synthetic_sales_assist.durable_demo_backend import DurableDemoAuditBackend
from synthetic_sales_assist.persistence.backup import verify_backup
from synthetic_sales_assist.persistence.database import SQLiteDatabase


class Milestone4BenchmarkTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="synthetic-sales-assist-m4-benchmark-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_mixed_persistence_replay_reads_metrics_and_backup(self) -> None:
        database = SQLiteDatabase(self.root / "data" / "benchmark.sqlite3")
        database.initialize()
        backend = DurableDemoAuditBackend(database)
        backup = self.root / "benchmark-backup.sqlite3"
        report = run_persistence_benchmark(
            database,
            backend,
            backup,
            operation_count=12,
            replay_count=3,
            history_sample_count=2,
        )
        self.assertEqual(report.unique_operation_count, 12)
        self.assertEqual(report.replay_operation_count, 3)
        self.assertEqual(dict(report.rule_pack_counts), {"DOI": 8, "SALES_CREDIT": 4})
        self.assertEqual(report.history_query_count, 6)
        self.assertGreater(report.database_size_bytes, 0)
        self.assertGreater(report.peak_python_bytes, 0)
        self.assertTrue(backup.is_file())
        self.assertEqual(verify_backup(backup).backup_sha256, report.backup_sha256)
        self.assertEqual(set(dict(report.safety_counters).values()), {0})
        with database.read() as connection:
            sales_credit_evaluations = int(
                connection.execute("SELECT COUNT(*) FROM sc_evaluations").fetchone()[0]
            )
            doi_evaluations = int(
                connection.execute("SELECT COUNT(*) FROM doi_evaluations").fetchone()[0]
            )
            durable_receipts = int(
                connection.execute(
                    "SELECT COUNT(*) FROM durable_command_receipts"
                ).fetchone()[0]
            )
            replay_rows = int(
                connection.execute(
                    "SELECT COUNT(*) FROM processing_telemetry WHERE replay = 1"
                ).fetchone()[0]
            )
        self.assertEqual(sales_credit_evaluations, 4)
        self.assertEqual(doi_evaluations, 8)
        self.assertEqual(durable_receipts, 12)
        self.assertEqual(replay_rows, 3)


if __name__ == "__main__":
    unittest.main()
