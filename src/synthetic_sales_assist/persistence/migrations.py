"""Deterministic, transactional SQLite migration foundation.

Milestone 0 intentionally owns no Sales Credit or DOI tables.  This runner applies
numbered SQL files, records their raw-byte SHA-256 digests, rejects drift, and keeps
each migration plus its ledger entry in one SQLite transaction.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final


PROJECT_ROOT: Final = Path(__file__).resolve().parents[3]
DEFAULT_MIGRATIONS_DIRECTORY: Final = PROJECT_ROOT / "migrations"
MIGRATION_LEDGER_TABLE: Final = "_schema_migrations"

_MIGRATION_FILENAME = re.compile(
    r"\A(?P<version>[0-9]{4})_(?P<name>[a-z][a-z0-9_]*)\.sql\Z",
    re.ASCII,
)
_TOP_LEVEL_TRANSACTION_CONTROL = re.compile(
    r"(?i)\A\s*(?:BEGIN|COMMIT|END|ROLLBACK|SAVEPOINT|RELEASE)\b"
)
_UNSAFE_SQL_CAPABILITY = re.compile(
    r"(?im)^\s*(?:ATTACH|DETACH|VACUUM|PRAGMA)\b|\bload_extension\s*\("
)
_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)


class MigrationError(RuntimeError):
    """Base migration failure."""


class MigrationDefinitionError(MigrationError):
    """A migration file or migration inventory is malformed."""


class MigrationDriftError(MigrationError):
    """Applied ledger material differs from the immutable migration source."""


class MigrationApplyError(MigrationError):
    """A migration failed and was rolled back."""


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    path: Path
    sha256: str
    sql: str


def _within_root(path: Path, repository_root: Path) -> Path:
    try:
        root = repository_root.resolve(strict=True)
        candidate = path if path.is_absolute() else root / path
        if candidate.is_symlink():
            raise MigrationDefinitionError("symbolic migration paths are prohibited")
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise MigrationDefinitionError(
            "migration path is unavailable or outside repository"
        ) from exc
    return resolved


def discover_migrations(
    migrations_directory: Path | str = DEFAULT_MIGRATIONS_DIRECTORY,
    *,
    repository_root: Path | str = PROJECT_ROOT,
) -> tuple[Migration, ...]:
    """Load a closed, gap-free inventory ordered by its four-digit version."""

    root = Path(repository_root)
    directory = _within_root(Path(migrations_directory), root)
    if not directory.is_dir():
        raise MigrationDefinitionError("migration directory is not a directory")

    migrations: list[Migration] = []
    for candidate in sorted(directory.iterdir(), key=lambda item: item.name):
        if candidate.is_symlink():
            raise MigrationDefinitionError("symbolic migration paths are prohibited")
        if candidate.is_dir():
            continue
        if candidate.suffix.lower() != ".sql":
            continue
        match = _MIGRATION_FILENAME.fullmatch(candidate.name)
        if match is None:
            raise MigrationDefinitionError("migration filename is not canonical")
        resolved = _within_root(candidate, root)
        raw = resolved.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf") or b"\x00" in raw:
            raise MigrationDefinitionError("migration encoding is not canonical UTF-8")
        try:
            sql = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise MigrationDefinitionError("migration encoding is not canonical UTF-8") from exc
        if not _has_sql_content(sql):
            raise MigrationDefinitionError("migration contains no SQL")
        statements = tuple(_iter_statements(sql))
        if (
            any(_TOP_LEVEL_TRANSACTION_CONTROL.search(statement) for statement in statements)
            or _UNSAFE_SQL_CAPABILITY.search(sql)
        ):
            raise MigrationDefinitionError(
                "migration contains prohibited transaction or I/O control"
            )
        migrations.append(
            Migration(
                version=int(match.group("version")),
                name=match.group("name"),
                path=resolved,
                sha256=hashlib.sha256(raw).hexdigest(),
                sql=sql,
            )
        )

    expected_versions = list(range(1, len(migrations) + 1))
    actual_versions = [migration.version for migration in migrations]
    if actual_versions != expected_versions:
        raise MigrationDefinitionError("migration versions must be unique and gap-free from 0001")
    return tuple(migrations)


def _has_sql_content(sql: str) -> bool:
    without_blocks = _COMMENT_BLOCK.sub("", sql)
    without_line_comments = "\n".join(
        line.split("--", 1)[0] for line in without_blocks.splitlines()
    )
    return bool(without_line_comments.strip())


def _iter_statements(sql: str) -> Iterator[str]:
    """Yield complete SQLite statements while honoring SQLite quoting rules."""

    pending: list[str] = []
    for line in sql.splitlines(keepends=True):
        pending.append(line)
        candidate = "".join(pending)
        if sqlite3.complete_statement(candidate):
            if _has_sql_content(candidate):
                yield candidate
            pending.clear()
    remainder = "".join(pending)
    if _has_sql_content(remainder):
        raise MigrationDefinitionError("migration ends with an incomplete SQL statement")


def _enable_foreign_keys(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        raise MigrationError("migration connection must not have an active transaction")
    connection.execute("PRAGMA foreign_keys = ON")
    enabled = connection.execute("PRAGMA foreign_keys").fetchone()
    if enabled is None or enabled[0] != 1:
        raise MigrationError("SQLite foreign-key enforcement could not be enabled")


def _bootstrap_ledger(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {MIGRATION_LEDGER_TABLE} (
                version INTEGER PRIMARY KEY CHECK (version > 0),
                name TEXT NOT NULL UNIQUE,
                sha256 TEXT NOT NULL
                    CHECK (
                        length(sha256) = 64
                        AND sha256 NOT GLOB '*[^0-9a-f]*'
                    ),
                applied_at_utc TEXT NOT NULL
            )
            """
        )
        connection.commit()
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise

    columns = connection.execute(
        f"PRAGMA table_info({MIGRATION_LEDGER_TABLE})"
    ).fetchall()
    signature = tuple((row[1], row[2], row[3], row[5]) for row in columns)
    expected = (
        ("version", "INTEGER", 0, 1),
        ("name", "TEXT", 1, 0),
        ("sha256", "TEXT", 1, 0),
        ("applied_at_utc", "TEXT", 1, 0),
    )
    if signature != expected:
        raise MigrationDriftError("migration ledger schema drift detected")


def _utc_timestamp(clock: Callable[[], datetime]) -> str:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise MigrationError("migration clock must return an aware datetime")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _read_ledger(connection: sqlite3.Connection) -> tuple[tuple[int, str, str], ...]:
    rows = connection.execute(
        f"SELECT version, name, sha256 FROM {MIGRATION_LEDGER_TABLE} ORDER BY version"
    ).fetchall()
    try:
        return tuple((int(row[0]), str(row[1]), str(row[2])) for row in rows)
    except (TypeError, ValueError, IndexError) as exc:
        raise MigrationDriftError("migration ledger row is malformed") from exc


def _validate_ledger(
    ledger: tuple[tuple[int, str, str], ...], migrations: tuple[Migration, ...]
) -> None:
    if [row[0] for row in ledger] != list(range(1, len(ledger) + 1)):
        raise MigrationDriftError("applied migration versions are not a contiguous prefix")
    if len(ledger) > len(migrations):
        raise MigrationDriftError("an applied migration source is missing")
    for row, migration in zip(ledger, migrations[: len(ledger)], strict=True):
        if row != (migration.version, migration.name, migration.sha256):
            raise MigrationDriftError("applied migration source drift detected")


def apply_migrations(
    connection: sqlite3.Connection,
    migrations_directory: Path | str = DEFAULT_MIGRATIONS_DIRECTORY,
    *,
    repository_root: Path | str = PROJECT_ROOT,
    clock: Callable[[], datetime] | None = None,
) -> tuple[int, ...]:
    """Apply pending migrations and return the versions committed by this call."""

    migrations = discover_migrations(
        migrations_directory,
        repository_root=repository_root,
    )
    _enable_foreign_keys(connection)
    _bootstrap_ledger(connection)
    _validate_ledger(_read_ledger(connection), migrations)

    utc_clock = clock or (lambda: datetime.now(timezone.utc))
    applied: list[int] = []
    for migration in migrations:
        connection.execute("BEGIN IMMEDIATE")
        try:
            existing = connection.execute(
                f"SELECT name, sha256 FROM {MIGRATION_LEDGER_TABLE} WHERE version = ?",
                (migration.version,),
            ).fetchone()
            if existing is not None:
                if tuple(existing) != (migration.name, migration.sha256):
                    raise MigrationDriftError("applied migration source drift detected")
                connection.commit()
                continue

            previous = connection.execute(
                f"SELECT COALESCE(MAX(version), 0) FROM {MIGRATION_LEDGER_TABLE}"
            ).fetchone()
            if previous is None or previous[0] != migration.version - 1:
                raise MigrationDriftError("migration application order is invalid")

            for statement in _iter_statements(migration.sql):
                connection.execute(statement)
            connection.execute(
                f"""
                INSERT INTO {MIGRATION_LEDGER_TABLE}
                    (version, name, sha256, applied_at_utc)
                VALUES (?, ?, ?, ?)
                """,
                (
                    migration.version,
                    migration.name,
                    migration.sha256,
                    _utc_timestamp(utc_clock),
                ),
            )
            connection.commit()
            applied.append(migration.version)
        except MigrationError:
            if connection.in_transaction:
                connection.rollback()
            raise
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise MigrationApplyError(
                f"migration {migration.version:04d} failed and was rolled back"
            ) from None
    return tuple(applied)


__all__ = [
    "DEFAULT_MIGRATIONS_DIRECTORY",
    "MIGRATION_LEDGER_TABLE",
    "PROJECT_ROOT",
    "Migration",
    "MigrationApplyError",
    "MigrationDefinitionError",
    "MigrationDriftError",
    "MigrationError",
    "apply_migrations",
    "discover_migrations",
]
