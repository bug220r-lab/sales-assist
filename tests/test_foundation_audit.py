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
        self.assertEqual(self.report["milestone"], 6)
        self.assertEqual(
            self.report["schema_version"],
            "synthetic-sales-assist-repository-audit/v3",
        )

    def test_external_calls_are_zero_and_business_rule_inventory_is_truthful(self) -> None:
        self.assertEqual(self.report["external_system_calls_required"], 0)
        self.assertEqual(self.report["business_rule_modules"], 26)
        self.assertEqual(
            self.report["business_rule_module_roots"],
            [
                "src/synthetic_sales_assist/sales_credit",
                "src/synthetic_sales_assist/doi",
            ],
        )

    def test_exact_milestone6_extension_inventory_is_admitted(self) -> None:
        inventory = self.report["chrome_permission_inventory"]
        self.assertEqual(inventory["manifest_count"], 1)
        self.assertEqual(inventory["extension_artifacts_created"], 13)
        self.assertEqual(inventory["extension_root_file_count"], 13)
        self.assertEqual(inventory["api_permission_inventory"], ["sidePanel"])
        self.assertEqual(
            inventory["allowed_host_patterns"],
            ["http://127.0.0.1/*", "http://localhost/*"],
        )
        self.assertEqual(
            inventory["manifests"],
            [
                {
                    "path": "chrome_extension/manifest.json",
                    "host_patterns": [
                        "http://127.0.0.1/*",
                        "http://localhost/*",
                    ],
                    "content_match_patterns": [
                        "http://127.0.0.1/interactions/*",
                        "http://127.0.0.1/orders/*",
                        "http://localhost/interactions/*",
                        "http://localhost/orders/*",
                    ],
                    "api_permissions": ["sidePanel"],
                }
            ],
        )

    def test_no_second_extension_is_created_through_milestone_six(self) -> None:
        """Preserve the old collected selector as an exact one-extension gate."""

        self.test_exact_milestone6_extension_inventory_is_admitted()

    def test_no_unbounded_extension_is_created_during_milestone_six(self) -> None:
        """Preserve the foundation selector at the advanced boundary."""

        self.test_exact_milestone6_extension_inventory_is_admitted()

    def test_all_safety_counters_are_zero(self) -> None:
        counters = self.report["safety_counters"]
        self.assertTrue(counters["all_zero"])
        self.assertEqual(counters["counter_count"], 9)

    def test_no_binding_contradiction_remains(self) -> None:
        self.assertEqual(self.report["remaining_binding_contradictions"], [])


if __name__ == "__main__":
    unittest.main()
