from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from synthetic_sales_assist.domain.registries import load_doi_registries
from synthetic_sales_assist.persistence.migrations import apply_migrations
from synthetic_sales_assist.persistence.schema import schema_inventory
from tools.generate_milestone4_artifacts import generated_documents


ROOT = Path(__file__).resolve().parents[1]


class Milestone4ArtifactTests(unittest.TestCase):
    def test_generated_migration_and_schema_documents_have_no_drift(self) -> None:
        for path, expected in generated_documents():
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file())
                self.assertEqual(path.read_bytes(), expected.encode("utf-8"))

    def test_schema_has_no_sales_credit_doi_cross_domain_foreign_key(self) -> None:
        with sqlite3.connect(":memory:") as connection:
            self.assertEqual(apply_migrations(connection), (1, 2, 3, 4))
            tables = tuple(
                item.name
                for item in schema_inventory(connection)
                if item.object_type == "table"
            )
            violations: list[str] = []
            for table in tables:
                quoted = '"' + table.replace('"', '""') + '"'
                for foreign_key in connection.execute(
                    f"PRAGMA foreign_key_list({quoted})"
                ).fetchall():
                    target = str(foreign_key[2])
                    if (table.startswith("sc_") and target.startswith("doi_")) or (
                        table.startswith("doi_") and target.startswith("sc_")
                    ):
                        violations.append(f"{table}->{target}")
            self.assertEqual(violations, [])
            self.assertEqual(connection.execute("PRAGMA quick_check").fetchone(), ("ok",))
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_required_milestone4_documents_and_adrs_exist(self) -> None:
        required = {
            "docs/adr/0016-sqlite-wal-transactions-and-concurrency.md",
            "docs/adr/0017-physical-persistence-decomposition.md",
            "docs/adr/0018-backup-restore-atomicity-and-retention.md",
            "docs/adr/0019-projection-verification-and-rebuild.md",
            "docs/adr/0020-retention-and-identity-graph-deletion.md",
            "docs/milestone4-backup-restore-guide.md",
            "docs/milestone4-benchmark-report.md",
            "docs/milestone4-cli-reference.md",
            "docs/milestone4-data-location-guide.md",
            "docs/milestone4-manual-acceptance.md",
            "docs/milestone4-migration-verification.md",
            "docs/milestone4-persistence-architecture.md",
            "docs/milestone4-repository-service-map.md",
            "docs/milestone4-retention-purge-verification.md",
            "docs/milestone4-schema-inventory.md",
            "docs/milestone4-schema-map.md",
        }
        missing = sorted(path for path in required if not (ROOT / path).is_file())
        self.assertEqual(missing, [])

    def test_doi_registry_cardinalities_remain_exactly_unchanged(self) -> None:
        registries = load_doi_registries()
        self.assertEqual(registries.reason_count, 138)
        self.assertEqual(registries.ownership_count, 138)
        self.assertEqual(registries.transition_count, 115)


if __name__ == "__main__":
    unittest.main()
