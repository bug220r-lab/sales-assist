from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synthetic_sales_assist.audit import audit_bundle  # noqa: E402


class BundleIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit_bundle(ROOT)

    def test_checksum_and_manifest_inventories_verify(self) -> None:
        self.assertEqual(self.report.checksum_entries, 66)
        self.assertEqual(self.report.manifest_entries, 65)
        self.assertEqual(self.report.specification_files, 34)
        self.assertEqual(self.report.reference_files, 28)

    def test_all_supplied_json_parses_strictly(self) -> None:
        self.assertEqual(self.report.json_files, 11)

    def test_closed_doi_inventory_counts(self) -> None:
        self.assertEqual(self.report.reasons, 138)
        self.assertEqual(self.report.ownership_rows, 138)
        self.assertEqual(self.report.transitions, 115)

    def test_all_sanitized_reference_hashes_are_current(self) -> None:
        self.assertEqual(self.report.provenance_rows, 28)

    def test_source_derived_manifest_counts(self) -> None:
        self.assertEqual(self.report.base_test_ids, 312)
        self.assertEqual(self.report.test_families, 29)

    def test_only_absent_predecessor_artifacts_are_not_recomputable(self) -> None:
        self.assertEqual(self.report.unverifiable_predecessor_fields, 2)


if __name__ == "__main__":
    unittest.main()
