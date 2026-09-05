"""Small denominator and durable-effect regression for the release workload harness."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.measure_demo_release import distribution, run_workload


class ReleaseMeasurementTests(unittest.TestCase):
    def test_mixed_calls_reconcile_and_backup_verifies(self) -> None:
        with tempfile.TemporaryDirectory(prefix="synthetic-sales-assist-m8-measure-") as root:
            report = run_workload(Path(root) / "new-data", 20)
        self.assertEqual(report["total_calls"], 20)
        self.assertEqual(report["operation_counts"], {
            "new": 12, "replay": 4, "conflict": 2, "query": 2,
        })
        self.assertEqual(report["durable_counts"]["durable_command_receipts"], 12)
        self.assertEqual(report["replay_telemetry_rows"], 4)
        self.assertEqual(report["conflict_telemetry_rows"], 2)
        self.assertEqual(set(report["safety_counters"].values()), {0})
        self.assertGreater(report["backup_bytes"], 0)

    def test_nearest_rank_percentile_and_even_median(self) -> None:
        self.assertEqual(distribution(list(range(1, 21))), {
            "count": 20, "median_ns": 10, "p95_ns": 19, "max_ns": 20,
        })

    def test_network_input_is_rejected_before_filesystem_probe(self) -> None:
        with patch.object(Path, "exists", side_effect=AssertionError("filesystem probe")):
            with self.assertRaisesRegex(ValueError, "LOCAL_PATH_REQUIRED"):
                run_workload(Path("\\\\forbidden.invalid\\share\\synthetic-test"), 20)
