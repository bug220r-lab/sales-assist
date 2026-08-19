from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from synthetic_sales_assist.persistence.migrations import (
    MIGRATION_LEDGER_TABLE,
    MigrationApplyError,
    MigrationDefinitionError,
    MigrationDriftError,
    apply_migrations,
    discover_migrations,
)
from synthetic_sales_assist.structured_logging import SAFETY_COUNTER_NAMES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIRECTORY = PROJECT_ROOT / "migrations"
FIXED_TIME = datetime(2026, 8, 19, 13, 0, 0, tzinfo=timezone.utc)


class MigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.addCleanup(self.connection.close)

    def temporary_migration_directory(self) -> tempfile.TemporaryDirectory[str]:
        temporary = tempfile.TemporaryDirectory(
            prefix=".test-migrations-",
            dir=PROJECT_ROOT,
        )
        self.addCleanup(temporary.cleanup)
        return temporary

    def test_initial_migration_is_atomic_hash_bound_and_neutral(self) -> None:
        applied = apply_migrations(
            self.connection,
            MIGRATIONS_DIRECTORY,
            repository_root=PROJECT_ROOT,
            clock=lambda: FIXED_TIME,
        )

        self.assertEqual(applied, (1,))
        self.assertEqual(self.connection.execute("PRAGMA foreign_keys").fetchone(), (1,))

        expected_hash = hashlib.sha256(
            (MIGRATIONS_DIRECTORY / "0001_foundation.sql").read_bytes()
        ).hexdigest()
        ledger = self.connection.execute(
            f"SELECT version, name, sha256, applied_at_utc FROM {MIGRATION_LEDGER_TABLE}"
        ).fetchall()
        self.assertEqual(
            ledger,
            [(1, "foundation", expected_hash, "2026-08-19T13:00:00.000000Z")],
        )

        rows = self.connection.execute(
            "SELECT counter_name, counter_value FROM system_safety_counters ORDER BY rowid"
        ).fetchall()
        self.assertEqual(tuple(name for name, _ in rows), SAFETY_COUNTER_NAMES)
        self.assertTrue(all(value == 0 for _, value in rows))

        tables = {
            row[0]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        self.assertEqual(
            tables,
            {MIGRATION_LEDGER_TABLE, "system_safety_counters"},
        )

    def test_exact_reapplication_is_a_noop(self) -> None:
        first = apply_migrations(
            self.connection,
            MIGRATIONS_DIRECTORY,
            repository_root=PROJECT_ROOT,
        )
        second = apply_migrations(
            self.connection,
            MIGRATIONS_DIRECTORY,
            repository_root=PROJECT_ROOT,
        )

        self.assertEqual(first, (1,))
        self.assertEqual(second, ())
        count = self.connection.execute(
            f"SELECT COUNT(*) FROM {MIGRATION_LEDGER_TABLE}"
        ).fetchone()
        self.assertEqual(count, (1,))

    def test_source_tamper_after_application_is_rejected(self) -> None:
        temporary = self.temporary_migration_directory()
        directory = Path(temporary.name)
        source = MIGRATIONS_DIRECTORY / "0001_foundation.sql"
        target = directory / source.name
        target.write_bytes(source.read_bytes())

        apply_migrations(
            self.connection,
            directory,
            repository_root=PROJECT_ROOT,
        )
        target.write_bytes(target.read_bytes() + b"\n-- post-application drift\n")

        with self.assertRaises(MigrationDriftError):
            apply_migrations(
                self.connection,
                directory,
                repository_root=PROJECT_ROOT,
            )
        self.assertEqual(
            self.connection.execute(
                f"SELECT COUNT(*) FROM {MIGRATION_LEDGER_TABLE}"
            ).fetchone(),
            (1,),
        )

    def test_failed_migration_rolls_back_schema_and_ledger_row(self) -> None:
        temporary = self.temporary_migration_directory()
        directory = Path(temporary.name)
        (directory / "0001_broken.sql").write_text(
            "CREATE TABLE must_rollback (id INTEGER PRIMARY KEY);\n"
            "THIS IS NOT VALID SQL;\n",
            encoding="utf-8",
            newline="\n",
        )

        with self.assertRaises(MigrationApplyError):
            apply_migrations(
                self.connection,
                directory,
                repository_root=PROJECT_ROOT,
            )

        self.assertIsNone(
            self.connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'must_rollback'"
            ).fetchone()
        )
        self.assertEqual(
            self.connection.execute(
                f"SELECT COUNT(*) FROM {MIGRATION_LEDGER_TABLE}"
            ).fetchone(),
            (0,),
        )

    def test_discovery_is_numeric_and_rejects_version_gaps(self) -> None:
        temporary = self.temporary_migration_directory()
        directory = Path(temporary.name)
        (directory / "0002_later.sql").write_text(
            "CREATE TABLE later_table (id INTEGER PRIMARY KEY);\n",
            encoding="utf-8",
            newline="\n",
        )

        with self.assertRaises(MigrationDefinitionError):
            discover_migrations(directory, repository_root=PROJECT_ROOT)

    def test_transaction_and_io_control_in_migration_are_rejected(self) -> None:
        unsafe_sources = (
            "BEGIN;\nCREATE TABLE unsafe_table (id INTEGER);\nCOMMIT;\n",
            "ATTACH DATABASE 'elsewhere.sqlite3' AS external;\n",
            "PRAGMA foreign_keys = OFF;\n",
        )
        for sql in unsafe_sources:
            with self.subTest(first_word=sql.split()[0]):
                temporary = self.temporary_migration_directory()
                directory = Path(temporary.name)
                (directory / "0001_unsafe.sql").write_text(
                    sql,
                    encoding="utf-8",
                    newline="\n",
                )
                with self.assertRaises(MigrationDefinitionError):
                    discover_migrations(directory, repository_root=PROJECT_ROOT)

    def test_applied_source_may_not_be_deleted(self) -> None:
        temporary = self.temporary_migration_directory()
        directory = Path(temporary.name)
        source = MIGRATIONS_DIRECTORY / "0001_foundation.sql"
        target = directory / source.name
        target.write_bytes(source.read_bytes())
        apply_migrations(
            self.connection,
            directory,
            repository_root=PROJECT_ROOT,
        )
        target.unlink()

        with self.assertRaises(MigrationDriftError):
            apply_migrations(
                self.connection,
                directory,
                repository_root=PROJECT_ROOT,
            )


if __name__ == "__main__":
    unittest.main()
