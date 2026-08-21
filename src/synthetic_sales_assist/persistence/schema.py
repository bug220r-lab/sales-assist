"""Deterministic SQLite schema inventory and integrity verification."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from synthetic_sales_assist.persistence.migrations import (
    DEFAULT_MIGRATIONS_DIRECTORY,
    MIGRATION_LEDGER_TABLE,
    PROJECT_ROOT,
    MigrationDriftError,
    discover_migrations,
)


class DatabaseVerificationError(RuntimeError):
    """The opened database is corrupt, drifted, or version-incompatible."""


@dataclass(frozen=True, slots=True)
class SchemaObject:
    object_type: str
    name: str
    table_name: str
    sql: str | None


@dataclass(frozen=True, slots=True)
class MigrationReceipt:
    version: int
    name: str
    sha256: str
    applied_at_utc: str


@dataclass(frozen=True, slots=True)
class DatabaseVerification:
    schema_version: int
    expected_schema_version: int
    migration_receipts: tuple[MigrationReceipt, ...]
    schema_objects: tuple[SchemaObject, ...]
    quick_check: str
    integrity_check: str | None
    foreign_key_violations: tuple[tuple[object, ...], ...]

    @property
    def healthy(self) -> bool:
        return (
            self.schema_version == self.expected_schema_version
            and self.quick_check == "ok"
            and self.integrity_check in {None, "ok"}
            and not self.foreign_key_violations
        )


def schema_inventory(connection: sqlite3.Connection) -> tuple[SchemaObject, ...]:
    """Return all application-owned tables, indexes, triggers, and views."""

    rows = connection.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_schema
        WHERE name NOT LIKE 'sqlite_%'
        ORDER BY type, name
        """
    ).fetchall()
    return tuple(
        SchemaObject(str(row[0]), str(row[1]), str(row[2]), row[3])
        for row in rows
    )


def migration_receipts(connection: sqlite3.Connection) -> tuple[MigrationReceipt, ...]:
    try:
        rows = connection.execute(
            f"""
            SELECT version, name, sha256, applied_at_utc
            FROM {MIGRATION_LEDGER_TABLE}
            ORDER BY version
            """
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        raise DatabaseVerificationError("MIGRATION_LEDGER_UNAVAILABLE") from exc
    try:
        return tuple(
            MigrationReceipt(int(row[0]), str(row[1]), str(row[2]), str(row[3]))
            for row in rows
        )
    except (IndexError, TypeError, ValueError) as exc:
        raise DatabaseVerificationError("MIGRATION_LEDGER_MALFORMED") from exc


def _single_check(connection: sqlite3.Connection, pragma: str) -> str:
    rows = connection.execute(f"PRAGMA {pragma}").fetchall()
    if len(rows) == 1 and tuple(rows[0]) == ("ok",):
        return "ok"
    raise DatabaseVerificationError(f"SQLITE_{pragma.upper()}_FAILED")


def verify_database(
    connection: sqlite3.Connection,
    *,
    deep: bool = False,
    migrations_directory: Path | str = DEFAULT_MIGRATIONS_DIRECTORY,
    repository_root: Path | str = PROJECT_ROOT,
) -> DatabaseVerification:
    """Verify migration bytes, current version, FK integrity, and SQLite health."""

    migrations = discover_migrations(
        migrations_directory,
        repository_root=repository_root,
    )
    receipts = migration_receipts(connection)
    expected = tuple(
        (item.version, item.name, item.sha256)
        for item in migrations
    )
    actual = tuple((item.version, item.name, item.sha256) for item in receipts)
    if actual != expected:
        raise MigrationDriftError("applied migration source drift detected")
    expected_version = len(migrations)
    try:
        metadata = connection.execute(
            """
            SELECT application_id, database_format, latest_schema_version
            FROM application_metadata
            WHERE singleton = 1
            """
        ).fetchone()
    except sqlite3.DatabaseError as exc:
        raise DatabaseVerificationError("APPLICATION_METADATA_UNAVAILABLE") from exc
    if metadata is None or tuple(metadata[:2]) != (
        "synthetic-sales-assist",
        "synthetic-sales-assist-sqlite/v1",
    ):
        raise DatabaseVerificationError("APPLICATION_METADATA_INVALID")
    schema_version = int(metadata[2])
    if schema_version != expected_version:
        raise DatabaseVerificationError("SCHEMA_VERSION_UNSUPPORTED")
    quick = _single_check(connection, "quick_check")
    integrity = _single_check(connection, "integrity_check") if deep else None
    foreign_keys = tuple(
        tuple(row) for row in connection.execute("PRAGMA foreign_key_check").fetchall()
    )
    if foreign_keys:
        raise DatabaseVerificationError("SQLITE_FOREIGN_KEY_CHECK_FAILED")
    verification = DatabaseVerification(
        schema_version=schema_version,
        expected_schema_version=expected_version,
        migration_receipts=receipts,
        schema_objects=schema_inventory(connection),
        quick_check=quick,
        integrity_check=integrity,
        foreign_key_violations=foreign_keys,
    )
    if not verification.healthy:
        raise DatabaseVerificationError("DATABASE_UNHEALTHY")
    return verification


__all__ = [
    "DatabaseVerification",
    "DatabaseVerificationError",
    "MigrationReceipt",
    "SchemaObject",
    "migration_receipts",
    "schema_inventory",
    "verify_database",
]
