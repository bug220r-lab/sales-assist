from __future__ import annotations

import hashlib
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from synthetic_sales_assist.persistence.migrations import (
    DEFAULT_MIGRATIONS_DIRECTORY,
    MIGRATION_LEDGER_TABLE,
    MigrationApplyError,
    MigrationDriftError,
    apply_migrations,
    discover_migrations,
)


class Milestone4SQLiteMigrationTests(unittest.TestCase):
    def test_closed_migration_inventory_is_exact_and_checksum_bound(self) -> None:
        inventory = discover_migrations()
        self.assertEqual(
            tuple((item.version, item.name) for item in inventory),
            (
                (1, "foundation"),
                (2, "shared_persistence"),
                (3, "sales_credit_persistence"),
                (4, "doi_persistence"),
            ),
        )
        for item in inventory:
            with self.subTest(migration=item.path.name):
                self.assertEqual(item.sha256, hashlib.sha256(item.path.read_bytes()).hexdigest())

    def test_current_migrations_apply_once_with_trigger_bodies(self) -> None:
        connection = sqlite3.connect(":memory:", isolation_level=None)
        self.addCleanup(connection.close)
        first = apply_migrations(connection)
        second = apply_migrations(connection)
        self.assertEqual(first, (1, 2, 3, 4))
        self.assertEqual(second, ())
        receipts = connection.execute(
            f"SELECT version, name FROM {MIGRATION_LEDGER_TABLE} ORDER BY version"
        ).fetchall()
        self.assertEqual(
            receipts,
            [
                (1, "foundation"),
                (2, "shared_persistence"),
                (3, "sales_credit_persistence"),
                (4, "doi_persistence"),
            ],
        )
        triggers = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'trigger'"
            )
        }
        self.assertIn("durable_commands_immutable_update", triggers)
        self.assertIn("sc_case_events_immutable_update", triggers)
        self.assertIn("doi_immutable_run_event", triggers)

    def test_changed_applied_milestone4_source_is_detected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ssa-m4-migration-drift-") as temporary:
            root = Path(temporary)
            directory = root / "migrations"
            shutil.copytree(DEFAULT_MIGRATIONS_DIRECTORY, directory)
            connection = sqlite3.connect(":memory:", isolation_level=None)
            self.addCleanup(connection.close)
            apply_migrations(connection, directory, repository_root=root)
            changed = directory / "0003_sales_credit_persistence.sql"
            changed.write_bytes(changed.read_bytes() + b"\n-- drift\n")
            with self.assertRaises(MigrationDriftError):
                apply_migrations(connection, directory, repository_root=root)

    def test_failed_pending_migration_rolls_back_its_schema_and_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ssa-m4-migration-failure-") as temporary:
            root = Path(temporary)
            directory = root / "migrations"
            directory.mkdir()
            for name in ("0001_foundation.sql", "0002_shared_persistence.sql"):
                shutil.copyfile(DEFAULT_MIGRATIONS_DIRECTORY / name, directory / name)
            (directory / "0003_broken.sql").write_text(
                "CREATE TABLE must_rollback (id INTEGER PRIMARY KEY);\n"
                "THIS IS NOT VALID SQL;\n",
                encoding="utf-8",
                newline="\n",
            )
            connection = sqlite3.connect(":memory:", isolation_level=None)
            self.addCleanup(connection.close)
            with self.assertRaises(MigrationApplyError):
                apply_migrations(connection, directory, repository_root=root)
            self.assertIsNone(
                connection.execute(
                    "SELECT name FROM sqlite_schema WHERE name = 'must_rollback'"
                ).fetchone()
            )
            self.assertEqual(
                connection.execute(
                    f"SELECT version FROM {MIGRATION_LEDGER_TABLE} ORDER BY version"
                ).fetchall(),
                [(1,), (2,)],
            )


if __name__ == "__main__":
    unittest.main()
