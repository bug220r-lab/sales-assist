from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synthetic_sales_assist.foundation_audit import run_foundation_audit  # noqa: E402


class FoundationAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_foundation_audit(ROOT)

    def test_complete_audit_passes(self) -> None:
        self.assertEqual(self.report["status"], "PASS")
        self.assertEqual(self.report["milestone"], 0)

    def test_no_external_or_business_capability_exists(self) -> None:
        self.assertEqual(self.report["external_system_calls_required"], 0)
        self.assertEqual(self.report["business_rule_modules"], 0)

    def test_no_extension_is_created_during_milestone_zero(self) -> None:
        inventory = self.report["chrome_permission_inventory"]
        self.assertEqual(inventory["manifest_count"], 0)
        self.assertEqual(inventory["extension_artifacts_created"], 0)

    def test_all_safety_counters_are_zero(self) -> None:
        counters = self.report["safety_counters"]
        self.assertTrue(counters["all_zero"])
        self.assertEqual(counters["counter_count"], 9)

    def test_no_binding_contradiction_remains(self) -> None:
        self.assertEqual(self.report["remaining_binding_contradictions"], [])


if __name__ == "__main__":
    unittest.main()
