from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from synthetic_sales_assist.persistence.database import (
    DatabaseBusyError,
    SQLiteDatabase,
)
from synthetic_sales_assist.persistence.migrations import (
    DEFAULT_MIGRATIONS_DIRECTORY,
    PROJECT_ROOT,
    apply_migrations,
    discover_migrations,
)
from synthetic_sales_assist.persistence.paths import (
    APPLICATION_DIRECTORY_NAME,
    DATABASE_FILENAME,
    PathPolicyError,
    resolve_data_paths,
    validate_local_path,
)
from synthetic_sales_assist.persistence.schema import (
    DatabaseVerificationError,
    schema_inventory,
    verify_database,
)


FIXED_TIME = datetime(2026, 8, 21, 16, 0, tzinfo=timezone.utc)


class Milestone4SQLiteCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ssa-m4-core-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.database = SQLiteDatabase(
            self.root / "data" / DATABASE_FILENAME,
            clock=lambda: FIXED_TIME,
        )

    def test_fresh_database_migrates_and_inventory_is_deterministic(self) -> None:
        verification = self.database.initialize()
        expected = discover_migrations()

        self.assertTrue(verification.healthy)
        self.assertEqual(verification.schema_version, len(expected))
        self.assertEqual(
            tuple(receipt.version for receipt in verification.migration_receipts),
            tuple(item.version for item in expected),
        )
        with self.database.read() as connection:
            first = schema_inventory(connection)
            second = schema_inventory(connection)
            deep = verify_database(connection, deep=True)
        self.assertEqual(first, second)
        self.assertEqual(deep.integrity_check, "ok")
        names = {item.name for item in first}
        self.assertTrue(
            {
                "application_metadata",
                "durable_commands",
                "sc_cases",
                "sc_case_events",
            }.issubset(names)
        )

    def test_exact_foundation_database_upgrades_through_current_schema(self) -> None:
        migration_root = self.root / "foundation-source"
        migration_dir = migration_root / "migrations"
        migration_dir.mkdir(parents=True)
        shutil.copyfile(
            DEFAULT_MIGRATIONS_DIRECTORY / "0001_foundation.sql",
            migration_dir / "0001_foundation.sql",
        )
        self.database.path.parent.mkdir(parents=True)
        connection = sqlite3.connect(self.database.path, isolation_level=None)
        try:
            self.assertEqual(
                apply_migrations(
                    connection,
                    migration_dir,
                    repository_root=migration_root,
                    clock=lambda: FIXED_TIME,
                ),
                (1,),
            )
        finally:
            connection.close()

        verification = self.database.initialize()

        self.assertEqual(
            verification.schema_version,
            len(discover_migrations()),
        )
        self.assertTrue(verification.healthy)

    def test_migration_replay_is_a_noop(self) -> None:
        self.database.initialize()
        connection = sqlite3.connect(self.database.path, isolation_level=None)
        try:
            self.assertEqual(
                apply_migrations(
                    connection,
                    DEFAULT_MIGRATIONS_DIRECTORY,
                    repository_root=PROJECT_ROOT,
                    clock=lambda: FIXED_TIME,
                ),
                (),
            )
        finally:
            connection.close()

    def test_every_application_connection_enforces_policy_and_read_is_query_only(self) -> None:
        self.database.initialize()
        with self.database.read() as connection:
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(str(connection.execute("PRAGMA journal_mode").fetchone()[0]), "wal")
            self.assertEqual(connection.execute("PRAGMA synchronous").fetchone()[0], 2)
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute(
                    "UPDATE system_safety_counters SET counter_value = 1"
                )
        with self.database.write() as connection:
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            connection.execute(
                """
                UPDATE system_safety_counters
                SET counter_value = counter_value
                WHERE counter_name = 'PRODUCTION_SYSTEM_ACCESS_COUNT'
                """
            )

    def test_unit_of_work_rolls_back_and_maintenance_rejects_active_operation(self) -> None:
        self.database.initialize()
        with self.assertRaisesRegex(RuntimeError, "rollback"):
            with self.database.write() as connection:
                connection.execute(
                    """
                    UPDATE system_safety_counters SET counter_value = 1
                    WHERE counter_name = 'PRODUCTION_SYSTEM_ACCESS_COUNT'
                    """
                )
                raise RuntimeError("rollback")
        with self.database.read() as connection:
            value = connection.execute(
                """
                SELECT counter_value FROM system_safety_counters
                WHERE counter_name = 'PRODUCTION_SYSTEM_ACCESS_COUNT'
                """
            ).fetchone()[0]
            with self.assertRaises(DatabaseBusyError):
                with self.database.maintenance():
                    self.fail("maintenance must not start")
        self.assertEqual(value, 0)

    def test_online_snapshot_boundary_allows_activity_but_blocks_maintenance(self) -> None:
        self.database.initialize()
        with self.database.write():
            with self.database.snapshot():
                self.assertGreaterEqual(self.database.coordinator.active_operations, 2)
            with self.assertRaises(DatabaseBusyError):
                with self.database.maintenance():
                    self.fail("restore maintenance must not overlap a writer")

    def test_separate_handles_share_same_path_coordinator(self) -> None:
        self.database.initialize()
        second = SQLiteDatabase(
            self.database.path,
            clock=lambda: FIXED_TIME,
        )
        self.assertIs(self.database.coordinator, second.coordinator)
        with self.database.read() as first_connection:
            with second.read() as second_connection:
                self.assertEqual(
                    first_connection.execute("SELECT 1").fetchone()[0],
                    second_connection.execute("SELECT 1").fetchone()[0],
                )
            with self.assertRaises(DatabaseBusyError):
                with second.maintenance():
                    self.fail("maintenance must coordinate across database handles")
        with self.database.write():
            with self.assertRaises(DatabaseBusyError):
                with second.maintenance():
                    self.fail("restore must reject an active writer on another handle")

    def test_unsupported_future_schema_fails_closed(self) -> None:
        self.database.initialize()
        with self.database.write() as connection:
            connection.execute(
                "UPDATE application_metadata SET latest_schema_version = 999 WHERE singleton = 1"
            )
        with self.database.read() as connection:
            with self.assertRaisesRegex(
                DatabaseVerificationError,
                "SCHEMA_VERSION_UNSUPPORTED",
            ):
                verify_database(connection)

    def test_data_path_layout_is_local_and_rejects_escape_surfaces(self) -> None:
        local_root = self.root / "LocalAppData"
        paths = resolve_data_paths(
            environ={"LOCALAPPDATA": str(local_root)},
        )
        self.assertEqual(paths.root, local_root / APPLICATION_DIRECTORY_NAME)
        self.assertEqual(paths.database, paths.root / "data" / DATABASE_FILENAME)
        paths.ensure_directories()
        self.assertTrue(paths.runtime.is_dir())

        invalid = (
            "https:" + "//example.test/database.sqlite3",
            "\\\\server\\share\\database.sqlite3",
            "\\\\?\\C:\\database.sqlite3",
            "C:\\data\\database.sqlite3:stream",
            "..\\database.sqlite3",
            str(PROJECT_ROOT / "runtime" / "database.sqlite3"),
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                with self.assertRaises(PathPolicyError):
                    validate_local_path(candidate)


if __name__ == "__main__":
    unittest.main()
