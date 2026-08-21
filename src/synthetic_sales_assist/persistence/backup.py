"""Safe local SQLite online backup and verified atomic restore."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import re
import sqlite3
import stat
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final, Protocol

from synthetic_sales_assist import __version__
from synthetic_sales_assist.domain.canonical import canonical_json_bytes
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.persistence.migrations import discover_migrations
from synthetic_sales_assist.persistence.paths import PathPolicyError, validate_local_path


BACKUP_RECEIPT_VERSION: Final = "synthetic-sales-assist-backup-receipt/v1"
_SAFE_BACKUP_NAME = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,126}\.sqlite3\Z", re.ASCII)
_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z", re.ASCII)
_DEVICE_PREFIXES = ("\\\\?\\", "\\\\.\\", "\\??\\", "//?/", "//./")
_ATOMIC_REPLACE_ATTEMPTS: Final = 200
_ATOMIC_REPLACE_RETRY_SECONDS: Final = 0.002


class BackupError(RuntimeError):
    """Fail closed without exposing database content or unsafe paths."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"backup operation rejected: {code}")


class _Database(Protocol):
    path: Path

    def maintenance(self) -> AbstractContextManager[None]: ...

    def snapshot(self) -> AbstractContextManager[None]: ...


FaultInjector = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class BackupReceipt:
    backup_id: str
    application_version: str
    schema_version: int
    migration_checksums: tuple[tuple[int, str], ...]
    created_at: CanonicalTimestamp
    expires_at: CanonicalTimestamp
    source_database_sha256: str
    backup_sha256: str
    table_rows: tuple[tuple[str, int], ...]
    quick_check: str
    foreign_key_check: str
    receipt_version: str = BACKUP_RECEIPT_VERSION

    def __post_init__(self) -> None:
        if not self.backup_id.startswith("SYN-EVIDENCE-BACKUP-"):
            raise BackupError("BACKUP_RECEIPT_INVALID")
        if (
            type(self.application_version) is not str
            or not 1 <= len(self.application_version) <= 64
            or not self.application_version.isascii()
        ):
            raise BackupError("BACKUP_RECEIPT_INVALID")
        if type(self.schema_version) is not int or self.schema_version < 1:
            raise BackupError("BACKUP_RECEIPT_INVALID")
        if type(self.created_at) is not CanonicalTimestamp or type(
            self.expires_at
        ) is not CanonicalTimestamp:
            raise BackupError("BACKUP_RECEIPT_INVALID")
        if (self.expires_at.epoch_seconds, self.expires_at.nanosecond) <= (
            self.created_at.epoch_seconds,
            self.created_at.nanosecond,
        ):
            raise BackupError("BACKUP_RECEIPT_INVALID")
        if _SHA256.fullmatch(self.source_database_sha256) is None or _SHA256.fullmatch(
            self.backup_sha256
        ) is None:
            raise BackupError("BACKUP_RECEIPT_INVALID")
        if self.quick_check != "ok" or self.foreign_key_check != "ok":
            raise BackupError("BACKUP_RECEIPT_INVALID")
        if (
            type(self.migration_checksums) is not tuple
            or self.migration_checksums != tuple(sorted(self.migration_checksums))
            or any(
                type(version) is not int
                or version < 1
                or type(digest) is not str
                or _SHA256.fullmatch(digest) is None
                for version, digest in self.migration_checksums
            )
            or tuple(version for version, _ in self.migration_checksums)
            != tuple(range(1, self.schema_version + 1))
        ):
            raise BackupError("BACKUP_RECEIPT_INVALID")
        if (
            type(self.table_rows) is not tuple
            or self.table_rows != tuple(sorted(self.table_rows))
            or any(
                type(table) is not str
                or not table
                or len(table) > 128
                or not table.isascii()
                or type(count) is not int
                or count < 0
                for table, count in self.table_rows
            )
        ):
            raise BackupError("BACKUP_RECEIPT_INVALID")
        if self.receipt_version != BACKUP_RECEIPT_VERSION:
            raise BackupError("BACKUP_RECEIPT_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "application_version": self.application_version,
            "backup_id": self.backup_id,
            "backup_sha256": self.backup_sha256,
            "created_at": self.created_at.value,
            "expires_at": self.expires_at.value,
            "foreign_key_check": self.foreign_key_check,
            "migration_checksums": [
                {"sha256": digest, "version": version}
                for version, digest in self.migration_checksums
            ],
            "quick_check": self.quick_check,
            "receipt_version": self.receipt_version,
            "schema_version": self.schema_version,
            "source_database_sha256": self.source_database_sha256,
            "table_rows": [
                {"row_count": count, "table": table} for table, count in self.table_rows
            ],
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    @classmethod
    def from_bytes(cls, value: bytes) -> BackupReceipt:
        try:
            parsed = json.loads(value.decode("utf-8"))
            if type(parsed) is not dict:
                raise ValueError
            expected = {
                "application_version",
                "backup_id",
                "backup_sha256",
                "created_at",
                "expires_at",
                "foreign_key_check",
                "migration_checksums",
                "quick_check",
                "receipt_version",
                "schema_version",
                "source_database_sha256",
                "table_rows",
            }
            if set(parsed) != expected:
                raise ValueError
            migrations = parsed["migration_checksums"]
            tables = parsed["table_rows"]
            if type(migrations) is not list or type(tables) is not list:
                raise ValueError
            receipt = cls(
                backup_id=parsed["backup_id"],
                application_version=parsed["application_version"],
                schema_version=parsed["schema_version"],
                migration_checksums=tuple(
                    (item["version"], item["sha256"]) for item in migrations
                ),
                created_at=CanonicalTimestamp.from_sqlite_text(parsed["created_at"]),
                expires_at=CanonicalTimestamp.from_sqlite_text(parsed["expires_at"]),
                source_database_sha256=parsed["source_database_sha256"],
                backup_sha256=parsed["backup_sha256"],
                table_rows=tuple((item["table"], item["row_count"]) for item in tables),
                quick_check=parsed["quick_check"],
                foreign_key_check=parsed["foreign_key_check"],
                receipt_version=parsed["receipt_version"],
            )
        except (KeyError, TypeError, ValueError, UnicodeError):
            raise BackupError("BACKUP_RECEIPT_INVALID") from None
        if receipt.canonical_bytes() != value:
            raise BackupError("BACKUP_RECEIPT_NOT_CANONICAL")
        return receipt


@dataclass(frozen=True, slots=True)
class RestoreResult:
    restore_id: str
    backup: BackupReceipt
    pre_restore_backup: BackupReceipt


@dataclass(frozen=True, slots=True)
class ExpiredBackupPurgeSummary:
    evaluated_count: int
    purged_count: int

    def __post_init__(self) -> None:
        if (
            type(self.evaluated_count) is not int
            or type(self.purged_count) is not int
            or self.evaluated_count < 0
            or not 0 <= self.purged_count <= self.evaluated_count
        ):
            raise BackupError("BACKUP_PURGE_SUMMARY_INVALID")

    def to_dict(self) -> dict[str, int]:
        return {
            "evaluated_count": self.evaluated_count,
            "purged_count": self.purged_count,
        }


def receipt_path(backup_path: Path) -> Path:
    return backup_path.with_name(backup_path.name + ".receipt.json")


def _is_reparse(path: Path) -> bool:
    try:
        information = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(information, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return path.is_symlink() or bool(attributes & reparse_flag)


def _has_reparse_ancestor(path: Path) -> bool:
    candidate = path
    while True:
        if candidate.exists() and _is_reparse(candidate):
            return True
        if candidate == candidate.parent:
            return False
        candidate = candidate.parent


def _drive_is_local(path: Path) -> bool:
    if os.name != "nt":
        return True
    drive = path.drive
    if not drive:
        return False
    get_drive_type = ctypes.windll.kernel32.GetDriveTypeW  # type: ignore[attr-defined]
    get_drive_type.argtypes = [ctypes.c_wchar_p]
    get_drive_type.restype = ctypes.c_uint
    drive_type = int(get_drive_type(drive + "\\"))
    return drive_type in {2, 3, 6}  # removable, fixed, RAM disk


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def resolve_backup_path(
    requested: Path | str,
    *,
    backups_directory: Path,
    repository_root: Path,
    active_database: Path,
    for_write: bool,
    create_parent: bool = False,
) -> Path:
    """Resolve one explicit local backup file without URL/UNC/device/traversal escape."""

    if not isinstance(requested, (str, os.PathLike)):
        raise BackupError("BACKUP_PATH_INVALID")
    raw = os.fspath(requested)
    if (
        type(raw) is not str
        or not raw
        or "\x00" in raw
        or "://" in raw
        or raw.lower().startswith("file:")
    ):
        raise BackupError("BACKUP_PATH_INVALID")
    normalized = raw.replace("/", "\\") if os.name == "nt" else raw
    if normalized.startswith(("\\\\", "//", *_DEVICE_PREFIXES)):
        raise BackupError("BACKUP_PATH_NOT_LOCAL")
    source = Path(raw)
    if any(part == ".." for part in source.parts):
        raise BackupError("BACKUP_PATH_TRAVERSAL")
    if source.is_absolute():
        candidate = source
    elif len(source.parts) == 1:
        candidate = backups_directory / source
    else:
        raise BackupError("BACKUP_PATH_RELATIVE")
    if _SAFE_BACKUP_NAME.fullmatch(candidate.name) is None:
        raise BackupError("BACKUP_FILENAME_INVALID")
    if _has_reparse_ancestor(candidate):
        raise BackupError("BACKUP_PATH_REPARSE_POINT")
    resolved = candidate.resolve(strict=False)
    repo = repository_root.resolve(strict=True)
    active = active_database.resolve(strict=False)
    if resolved == active or _is_within(resolved, repo):
        raise BackupError("BACKUP_PATH_PROTECTED")
    if not _drive_is_local(resolved):
        raise BackupError("BACKUP_PATH_NOT_LOCAL")
    existing = resolved
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    if _is_reparse(existing):
        raise BackupError("BACKUP_PATH_REPARSE_POINT")
    if resolved.exists() and (_is_reparse(resolved) or not resolved.is_file()):
        raise BackupError("BACKUP_PATH_INVALID")
    parent = resolved.parent
    if not parent.exists():
        if not for_write or not create_parent:
            raise BackupError("BACKUP_PARENT_MISSING")
        parent.mkdir(parents=True, exist_ok=False)
    if _is_reparse(parent) or not parent.is_dir():
        raise BackupError("BACKUP_PATH_REPARSE_POINT")
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _connect(path: Path) -> sqlite3.Connection:
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(path, timeout=5.0, isolation_level=None)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection
    except Exception:
        if connection is not None:
            connection.close()
        raise


@contextmanager
def _cleanup_paths(*paths: Path) -> Iterator[None]:
    try:
        yield
    finally:
        for path in paths:
            with suppress(FileNotFoundError):
                path.unlink()


def _generated_backup_artifact(name: str) -> tuple[str, bool] | None:
    """Return (backup filename, is_identity_database) for our stale temp names."""

    for suffix in (".tmp", ".previous"):
        if not name.startswith(".") or not name.endswith(suffix):
            continue
        body = name[1 : -len(suffix)]
        base, separator, identifier = body.rpartition(".")
        if (
            separator != "."
            or len(identifier) != 32
            or any(character not in "0123456789ABCDEF" for character in identifier)
        ):
            continue
        if base.endswith(".receipt.json"):
            backup_name = base.removesuffix(".receipt.json")
            if _SAFE_BACKUP_NAME.fullmatch(backup_name) is not None:
                return backup_name, False
        elif _SAFE_BACKUP_NAME.fullmatch(base) is not None:
            return base, True
    return None


def _scavenge_generated_backup_artifacts(
    directory: Path,
    *,
    backup_name: str | None = None,
) -> int:
    """Recover a prior receipt when needed, then remove strict crash remnants."""

    identity_paths: list[tuple[Path, str]] = []
    receipt_paths: list[tuple[Path, str]] = []
    for item in directory.iterdir():
        if not item.is_file() or _is_reparse(item):
            continue
        parsed = _generated_backup_artifact(item.name)
        if parsed is None or (backup_name is not None and parsed[0] != backup_name):
            continue
        (identity_paths if parsed[1] else receipt_paths).append((item, parsed[0]))
    removed = 0
    affected = {name for _, name in (*identity_paths, *receipt_paths)}
    # Privacy ordering is deliberate: remove every noncanonical identity copy
    # before handling its nonidentity receipt metadata.
    for item, _ in sorted(identity_paths):
        try:
            item.unlink()
        except FileNotFoundError:
            continue
        removed += 1
    for name in sorted(affected):
        destination = directory / name
        sidecar = receipt_path(destination)
        prior_sidecars = tuple(
            item
            for item, artifact_name in receipt_paths
            if artifact_name == name and item.name.endswith(".previous")
        )
        if destination.is_file() and not _is_reparse(destination):
            digest = _sha256(destination)

            def matches(candidate: Path) -> bool:
                if not candidate.is_file() or _is_reparse(candidate):
                    return False
                try:
                    return (
                        BackupReceipt.from_bytes(candidate.read_bytes()).backup_sha256
                        == digest
                    )
                except (BackupError, OSError):
                    return False

            if not matches(sidecar):
                matching_prior = next(
                    (candidate for candidate in prior_sidecars if matches(candidate)),
                    None,
                )
                if matching_prior is not None:
                    os.replace(matching_prior, sidecar)
                    removed += 1
        elif any(artifact_name == name for _, artifact_name in identity_paths):
            # A crash after receipt-first publication but before the identity
            # replacement can leave this orphan. The identity temp is already
            # gone, so complete cleanup forward.
            with suppress(FileNotFoundError):
                sidecar.unlink()
                removed += 1
    for item, _ in sorted(receipt_paths):
        if not item.exists():
            continue
        try:
            item.unlink()
        except FileNotFoundError:
            continue
        removed += 1
    return removed


def _health(connection: sqlite3.Connection, *, deep: bool = False) -> tuple[str, str]:
    check = "integrity_check" if deep else "quick_check"
    integrity = connection.execute(f"PRAGMA {check}").fetchone()
    foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
    if integrity != ("ok",) or foreign:
        raise BackupError("BACKUP_DATABASE_INTEGRITY_INVALID")
    return "ok", "ok"


def _migration_inventory(connection: sqlite3.Connection) -> tuple[tuple[int, str], ...]:
    try:
        rows = connection.execute(
            "SELECT version, sha256 FROM _schema_migrations ORDER BY version"
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        raise BackupError("BACKUP_SCHEMA_INVALID") from exc
    inventory = tuple((int(row[0]), str(row[1])) for row in rows)
    if not inventory or [version for version, _ in inventory] != list(
        range(1, len(inventory) + 1)
    ):
        raise BackupError("BACKUP_SCHEMA_INVALID")
    if any(_SHA256.fullmatch(digest) is None for _, digest in inventory):
        raise BackupError("BACKUP_SCHEMA_INVALID")
    return inventory


def _table_rows(connection: sqlite3.Connection) -> tuple[tuple[str, int], ...]:
    names = tuple(
        str(row[0])
        for row in connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    )
    rows: list[tuple[str, int]] = []
    for name in names:
        quoted = '"' + name.replace('"', '""') + '"'
        result = connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()
        if result is None:
            raise BackupError("BACKUP_TABLE_SUMMARY_INVALID")
        rows.append((name, int(result[0])))
    return tuple(rows)


def _trusted_now(clock: Callable[[], datetime] | None) -> tuple[datetime, CanonicalTimestamp]:
    value = (clock or (lambda: datetime.now(timezone.utc)))()
    if type(value) is not datetime or value.tzinfo is None:
        raise BackupError("BACKUP_CLOCK_INVALID")
    utc = value.astimezone(timezone.utc)
    rendered = utc.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return utc, CanonicalTimestamp(rendered)


def _backup_expiry(
    connection: sqlite3.Connection,
    *,
    created_at: CanonicalTimestamp,
    operational_maximum: CanonicalTimestamp,
) -> CanonicalTimestamp:
    rows = connection.execute(
        """
        SELECT purge_eligible_at FROM sc_closed_audits
        UNION ALL
        SELECT purge_eligible_at FROM sc_no_order_closed_audits
        UNION ALL
        SELECT purge_eligible_at FROM doi_run_projections
            WHERE purge_eligible_at IS NOT NULL
        UNION ALL
        SELECT purge_eligible_at FROM doi_rejected_source_records
            WHERE purge_eligible_at IS NOT NULL
        UNION ALL
        SELECT purge_eligible_at FROM doi_retention_deadlines
            WHERE canceled_by_reopen_event_id IS NULL
        """
    ).fetchall()
    deadlines = tuple(CanonicalTimestamp.from_sqlite_text(row[0]) for row in rows)
    if any(
        (item.epoch_seconds, item.nanosecond)
        <= (created_at.epoch_seconds, created_at.nanosecond)
        for item in deadlines
    ):
        raise BackupError("BACKUP_RETENTION_DUE")
    return min(
        (operational_maximum, *deadlines),
        key=lambda item: (item.epoch_seconds, item.nanosecond),
    )


def _inject(fault_injector: FaultInjector | None, stage: str) -> None:
    if fault_injector is not None:
        fault_injector(stage)


def _atomic_replace(source: Path, destination: Path) -> None:
    """Perform one pathname replacement with a bounded Windows sharing retry."""

    retryable = {errno.EACCES, errno.EBUSY, errno.EPERM}
    for attempt in range(_ATOMIC_REPLACE_ATTEMPTS):
        try:
            os.replace(source, destination)
            return
        except OSError as exc:
            if attempt + 1 == _ATOMIC_REPLACE_ATTEMPTS or exc.errno not in retryable:
                raise
            time.sleep(_ATOMIC_REPLACE_RETRY_SECONDS)
    raise AssertionError("atomic replacement retry loop did not terminate")


def _insert_backup_receipt(connection: sqlite3.Connection, receipt: BackupReceipt) -> None:
    connection.execute(
        """
        INSERT INTO backup_receipts (
            backup_id, created_at, completed_at, schema_version, application_version,
            source_sha256, backup_sha256, table_count, row_count, quick_check,
            foreign_key_check, status, error_code
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'COMPLETED', NULL)
        """,
        (
            receipt.backup_id,
            receipt.created_at.value,
            receipt.created_at.value,
            receipt.schema_version,
            receipt.application_version,
            receipt.source_database_sha256,
            receipt.backup_sha256,
            len(receipt.table_rows),
            sum(count for _, count in receipt.table_rows),
            receipt.quick_check,
            receipt.foreign_key_check,
        ),
    )


def _create_backup_locked(
    database: _Database,
    destination: Path,
    *,
    clock: Callable[[], datetime] | None,
    overwrite: bool,
    fault_injector: FaultInjector | None,
) -> BackupReceipt:
    sidecar = receipt_path(destination)
    if destination.exists() != sidecar.exists():
        raise BackupError("BACKUP_PAIR_INVALID")
    if (destination.exists() or sidecar.exists()) and not overwrite:
        raise BackupError("BACKUP_EXISTS")
    identifier = uuid.uuid4().hex.upper()
    backup_id = f"SYN-EVIDENCE-BACKUP-{identifier}"
    temporary = destination.with_name(f".{destination.name}.{identifier}.tmp")
    sidecar_temporary = sidecar.with_name(f".{sidecar.name}.{identifier}.tmp")
    sidecar_previous = sidecar.with_name(f".{sidecar.name}.{identifier}.previous")
    utc, created_at = _trusted_now(clock)
    operational_maximum = CanonicalTimestamp(
        (utc + timedelta(days=89)).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )
    source: sqlite3.Connection | None = None
    target: sqlite3.Connection | None = None
    receipt: BackupReceipt | None = None
    completed = False
    sidecar_staged = False
    destination_published = False
    sidecar_published = False
    try:
        source = _connect(database.path)
        target = _connect(temporary)
        _inject(fault_injector, "before_online_backup")
        source.backup(target)
        _inject(fault_injector, "after_online_backup")
        target.close()
        target = None
        verification = _connect(temporary)
        try:
            expires_at = _backup_expiry(
                verification,
                created_at=created_at,
                operational_maximum=operational_maximum,
            )
            quick, foreign = _health(verification)
            migrations = _migration_inventory(verification)
            table_rows = _table_rows(verification)
        finally:
            verification.close()
        backup_digest = _sha256(temporary)
        receipt = BackupReceipt(
            backup_id=backup_id,
            application_version=__version__,
            schema_version=migrations[-1][0],
            migration_checksums=migrations,
            created_at=created_at,
            expires_at=expires_at,
            source_database_sha256=backup_digest,
            backup_sha256=backup_digest,
            table_rows=table_rows,
            quick_check=quick,
            foreign_key_check=foreign,
        )
        sidecar_temporary.write_bytes(receipt.canonical_bytes())
        _inject(fault_injector, "before_backup_publish")
        if sidecar.exists():
            os.replace(sidecar, sidecar_previous)
            sidecar_staged = True
        os.replace(sidecar_temporary, sidecar)
        sidecar_published = True
        _inject(fault_injector, "after_backup_sidecar_publish")
        # The existing identity database remains canonical until this one
        # pathname replacement. We never stage it under a `.previous` name.
        _atomic_replace(temporary, destination)
        destination_published = True
        _inject(fault_injector, "before_backup_receipt")
        source.execute("BEGIN IMMEDIATE")
        _insert_backup_receipt(source, receipt)
        source.commit()
        completed = True
        return receipt
    except Exception as exc:
        if source is not None and source.in_transaction:
            source.rollback()
        # Once the database replacement succeeds, rolling back would require
        # retaining a second identity-bearing database. Complete the durable
        # receipt forward instead; the already-published file/sidecar pair is
        # independently verifiable throughout this recovery.
        if destination_published and receipt is not None and source is not None:
            try:
                source.execute("BEGIN IMMEDIATE")
                _insert_backup_receipt(source, receipt)
                source.commit()
                completed = True
                return receipt
            except Exception as recovery_error:
                if source.in_transaction:
                    source.rollback()
                raise BackupError("BACKUP_RECEIPT_RECOVERY_FAILED") from recovery_error
        if type(exc) is BackupError:
            raise
        raise BackupError("BACKUP_FAILED") from None
    finally:
        if target is not None:
            target.close()
        if source is not None:
            source.close()
        if not completed and not destination_published:
            if sidecar_published:
                with suppress(FileNotFoundError):
                    sidecar.unlink()
            if sidecar_staged and sidecar_previous.exists():
                os.replace(sidecar_previous, sidecar)
        for artifact in (
            temporary,
            sidecar_temporary,
            sidecar_previous,
        ):
            with suppress(FileNotFoundError):
                artifact.unlink()


def create_backup(
    database: _Database,
    destination: Path,
    *,
    clock: Callable[[], datetime] | None = None,
    overwrite: bool = False,
    fault_injector: FaultInjector | None = None,
) -> BackupReceipt:
    """Create, verify, publish, and receipt one consistent SQLite online backup."""

    if not isinstance(destination, Path):
        raise BackupError("BACKUP_PATH_INVALID")
    try:
        safe_destination = validate_local_path(destination)
    except PathPolicyError:
        raise BackupError("BACKUP_PATH_INVALID") from None
    if safe_destination != destination.resolve(strict=False):
        raise BackupError("BACKUP_PATH_INVALID")
    if (
        _SAFE_BACKUP_NAME.fullmatch(destination.name) is None
        or not destination.parent.is_dir()
        or _has_reparse_ancestor(destination)
        or destination.resolve(strict=False) == database.path.resolve(strict=False)
    ):
        raise BackupError("BACKUP_PATH_INVALID")
    if not database.path.is_file():
        raise BackupError("ACTIVE_DATABASE_MISSING")
    with database.snapshot():
        return _create_backup_locked(
            database,
            destination,
            clock=clock,
            overwrite=overwrite,
            fault_injector=fault_injector,
        )


def read_backup_receipt(path: Path) -> BackupReceipt:
    sidecar = receipt_path(path)
    if not sidecar.is_file() or _is_reparse(sidecar):
        raise BackupError("BACKUP_RECEIPT_MISSING")
    try:
        return BackupReceipt.from_bytes(sidecar.read_bytes())
    except OSError:
        raise BackupError("BACKUP_RECEIPT_MISSING") from None


def verify_backup(
    path: Path,
    *,
    clock: Callable[[], datetime] | None = None,
) -> BackupReceipt:
    if not isinstance(path, Path):
        raise BackupError("BACKUP_FILE_INVALID")
    try:
        safe_path = validate_local_path(path)
    except PathPolicyError:
        raise BackupError("BACKUP_FILE_INVALID") from None
    if safe_path != path.resolve(strict=False) or not path.is_file() or _is_reparse(path):
        raise BackupError("BACKUP_FILE_INVALID")
    receipt = read_backup_receipt(path)
    if _sha256(path) != receipt.backup_sha256:
        raise BackupError("BACKUP_CHECKSUM_MISMATCH")
    _, now = _trusted_now(clock)
    if (now.epoch_seconds, now.nanosecond) >= (
        receipt.expires_at.epoch_seconds,
        receipt.expires_at.nanosecond,
    ):
        raise BackupError("BACKUP_EXPIRED")
    expected_migrations = tuple(
        (item.version, item.sha256) for item in discover_migrations()
    )
    if receipt.migration_checksums != expected_migrations:
        raise BackupError("BACKUP_SCHEMA_UNSUPPORTED")
    try:
        connection = _connect(path)
    except sqlite3.DatabaseError:
        raise BackupError("BACKUP_DATABASE_INVALID") from None
    try:
        try:
            _health(connection, deep=True)
            migrations = _migration_inventory(connection)
            if migrations != receipt.migration_checksums:
                raise BackupError("BACKUP_MIGRATION_MISMATCH")
            if _table_rows(connection) != receipt.table_rows:
                raise BackupError("BACKUP_ROW_SUMMARY_MISMATCH")
        except sqlite3.DatabaseError:
            raise BackupError("BACKUP_DATABASE_INVALID") from None
    finally:
        connection.close()
    return receipt


def purge_expired_backup(
    path: Path,
    *,
    clock: Callable[[], datetime] | None = None,
    fault_injector: FaultInjector | None = None,
) -> bool:
    """Delete one expired managed backup/receipt pair at its exact bound.

    The identity-bearing database is unlinked directly; it is never moved to an
    alternate retained pathname. A failure before unlink preserves the pair. Once
    unlink succeeds, receipt cleanup completes forward. An orphan receipt from a
    hard exit in that narrow interval is itself removed idempotently.
    """

    if not isinstance(path, Path):
        raise BackupError("BACKUP_FILE_INVALID")
    try:
        safe_path = validate_local_path(path)
    except PathPolicyError:
        raise BackupError("BACKUP_FILE_INVALID") from None
    sidecar = receipt_path(path)
    backup_exists = path.exists()
    sidecar_exists = sidecar.exists()
    if not backup_exists and not sidecar_exists:
        return False
    if (
        safe_path != path.resolve(strict=False)
        or _SAFE_BACKUP_NAME.fullmatch(path.name) is None
    ):
        raise BackupError("BACKUP_PAIR_INVALID")
    if not sidecar_exists or not sidecar.is_file() or _is_reparse(sidecar):
        raise BackupError("BACKUP_PAIR_INVALID")
    if backup_exists and (not path.is_file() or _is_reparse(path)):
        raise BackupError("BACKUP_PAIR_INVALID")
    receipt = read_backup_receipt(path)
    _, now = _trusted_now(clock)
    if (now.epoch_seconds, now.nanosecond) < (
        receipt.expires_at.epoch_seconds,
        receipt.expires_at.nanosecond,
    ):
        if not backup_exists:
            raise BackupError("BACKUP_PAIR_INVALID")
        return False
    if not backup_exists:
        try:
            sidecar.unlink()
        except OSError as exc:
            raise BackupError("BACKUP_PURGE_FAILED") from exc
        return False

    try:
        _inject(fault_injector, "before_expired_backup_delete")
    except Exception as exc:
        raise BackupError("BACKUP_PURGE_FAILED") from exc
    try:
        path.unlink()
    except OSError as exc:
        raise BackupError("BACKUP_PURGE_FAILED") from exc
    try:
        _inject(fault_injector, "after_expired_backup_deleted")
        sidecar.unlink()
        return True
    except Exception as exc:
        try:
            sidecar.unlink()
        except FileNotFoundError:
            pass
        except OSError as cleanup_error:
            raise BackupError("BACKUP_PURGE_FORWARD_CLEANUP_FAILED") from cleanup_error
        raise BackupError("BACKUP_PURGE_FAILED") from exc


def purge_expired_backups(
    backups_directory: Path,
    *,
    clock: Callable[[], datetime] | None = None,
    fault_injector: FaultInjector | None = None,
) -> ExpiredBackupPurgeSummary:
    """Evaluate and purge every top-level managed backup in one safe directory."""

    if not isinstance(backups_directory, Path):
        raise BackupError("BACKUP_DIRECTORY_INVALID")
    try:
        safe_directory = validate_local_path(backups_directory)
    except PathPolicyError:
        raise BackupError("BACKUP_DIRECTORY_INVALID") from None
    if (
        safe_directory != backups_directory.resolve(strict=False)
        or not backups_directory.is_dir()
        or _is_reparse(backups_directory)
    ):
        raise BackupError("BACKUP_DIRECTORY_INVALID")
    try:
        _scavenge_generated_backup_artifacts(backups_directory)
    except OSError as exc:
        raise BackupError("BACKUP_PURGE_FAILED") from exc
    candidate_set: set[Path] = set()
    for item in backups_directory.iterdir():
        if not item.is_file():
            continue
        if _SAFE_BACKUP_NAME.fullmatch(item.name) is not None:
            candidate_set.add(item)
            continue
        if item.name.endswith(".receipt.json"):
            backup_name = item.name.removesuffix(".receipt.json")
            if _SAFE_BACKUP_NAME.fullmatch(backup_name) is not None:
                candidate_set.add(item.with_name(backup_name))
    candidates = tuple(sorted(candidate_set, key=lambda item: item.name))
    purged = sum(
        purge_expired_backup(
            item,
            clock=clock,
            fault_injector=fault_injector,
        )
        for item in candidates
    )
    return ExpiredBackupPurgeSummary(len(candidates), purged)


def _automatic_backup_path(backups_directory: Path) -> Path:
    return backups_directory / f"pre-restore-{uuid.uuid4().hex.lower()}.sqlite3"


def _insert_restore_receipt(
    connection: sqlite3.Connection,
    *,
    restore_id: str,
    receipt: BackupReceipt,
    pre_restore: BackupReceipt,
    occurred_at: CanonicalTimestamp,
) -> None:
    connection.execute(
        """
        INSERT INTO restore_receipts (
            restore_id, started_at, completed_at, backup_sha256,
            pre_restore_backup_id, schema_version, status, error_code
        ) VALUES (?, ?, ?, ?, ?, ?, 'COMPLETED', NULL)
        """,
        (
            restore_id,
            occurred_at.value,
            occurred_at.value,
            receipt.backup_sha256,
            pre_restore.backup_id,
            receipt.schema_version,
        ),
    )


def restore_backup(
    database: _Database,
    source_backup: Path,
    *,
    backups_directory: Path,
    confirmed: bool,
    clock: Callable[[], datetime] | None = None,
    fault_injector: FaultInjector | None = None,
) -> RestoreResult:
    """Verify, pre-back up, atomically swap, and post-verify one local database restore."""

    if confirmed is not True:
        raise BackupError("RESTORE_CONFIRMATION_REQUIRED")
    try:
        safe_source = validate_local_path(source_backup)
        safe_backups = validate_local_path(backups_directory)
    except (PathPolicyError, TypeError):
        raise BackupError("RESTORE_PATH_INVALID") from None
    if (
        not isinstance(source_backup, Path)
        or not isinstance(backups_directory, Path)
        or safe_source != source_backup.resolve(strict=False)
        or safe_backups != backups_directory.resolve(strict=False)
        or not backups_directory.is_dir()
        or _has_reparse_ancestor(source_backup)
        or _has_reparse_ancestor(backups_directory)
    ):
        raise BackupError("RESTORE_PATH_INVALID")
    receipt = verify_backup(source_backup, clock=clock)
    restore_id = f"SYN-EVIDENCE-RESTORE-{uuid.uuid4().hex.upper()}"
    temporary = database.path.with_name(f".{database.path.name}.{restore_id}.restore.tmp")
    rollback_temporary = database.path.with_name(
        f".{database.path.name}.{restore_id}.rollback.tmp"
    )
    pre_restore_path = _automatic_backup_path(backups_directory)
    with database.maintenance(), _cleanup_paths(temporary, rollback_temporary):
        pre_restore = _create_backup_locked(
            database,
            pre_restore_path,
            clock=clock,
            overwrite=False,
            fault_injector=fault_injector,
        )
        checkpoint = _connect(database.path)
        try:
            result = checkpoint.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if result is None or int(result[0]) != 0:
                raise BackupError("RESTORE_CHECKPOINT_FAILED")
        finally:
            checkpoint.close()
        try:
            rebound_receipt = verify_backup(source_backup, clock=clock)
        except BackupError:
            raise BackupError("RESTORE_SOURCE_CHANGED") from None
        if rebound_receipt != receipt:
            raise BackupError("RESTORE_SOURCE_CHANGED")
        source = _connect(source_backup)
        try:
            target = _connect(temporary)
        except Exception:
            source.close()
            raise BackupError("RESTORE_COPY_FAILED") from None
        copy_completed = False
        try:
            _inject(fault_injector, "before_restore_copy")
            source.backup(target)
            _inject(fault_injector, "after_restore_copy")
            copy_completed = True
        except Exception:
            raise BackupError("RESTORE_COPY_FAILED") from None
        finally:
            source.close()
            target.close()
            if not copy_completed:
                with suppress(FileNotFoundError):
                    temporary.unlink()
        if _sha256(temporary) != receipt.backup_sha256:
            with suppress(FileNotFoundError):
                temporary.unlink()
            raise BackupError("RESTORE_SOURCE_CHANGED")
        candidate = _connect(temporary)
        candidate_verified = False
        try:
            _health(candidate, deep=True)
            if _migration_inventory(candidate) != receipt.migration_checksums:
                raise BackupError("RESTORE_SCHEMA_MISMATCH")
            if _table_rows(candidate) != receipt.table_rows:
                raise BackupError("RESTORE_CONTENT_MISMATCH")
            candidate_verified = True
        finally:
            candidate.close()
            if not candidate_verified:
                with suppress(FileNotFoundError):
                    temporary.unlink()

        rollback_source: sqlite3.Connection | None = None
        rollback_target: sqlite3.Connection | None = None
        rollback_candidate: sqlite3.Connection | None = None
        rollback_staged = False
        try:
            _inject(fault_injector, "before_rollback_stage_copy")
            rollback_source = _connect(pre_restore_path)
            rollback_target = _connect(rollback_temporary)
            rollback_source.backup(rollback_target)
            _inject(fault_injector, "after_rollback_stage_copy")
            rollback_source.close()
            rollback_source = None
            rollback_target.close()
            rollback_target = None
            _inject(fault_injector, "before_rollback_stage_digest")
            if _sha256(rollback_temporary) != pre_restore.backup_sha256:
                raise BackupError("RESTORE_ROLLBACK_STAGE_FAILED")
            _inject(fault_injector, "before_rollback_stage_connect")
            rollback_candidate = _connect(rollback_temporary)
            _inject(fault_injector, "before_rollback_stage_verify")
            _health(rollback_candidate, deep=True)
            if _migration_inventory(rollback_candidate) != pre_restore.migration_checksums:
                raise BackupError("RESTORE_ROLLBACK_STAGE_FAILED")
            if _table_rows(rollback_candidate) != pre_restore.table_rows:
                raise BackupError("RESTORE_ROLLBACK_STAGE_FAILED")
            rollback_staged = True
        except Exception as exc:
            if type(exc) is BackupError and exc.code == "RESTORE_ROLLBACK_STAGE_FAILED":
                raise
            raise BackupError("RESTORE_ROLLBACK_STAGE_FAILED") from exc
        finally:
            if rollback_source is not None:
                rollback_source.close()
            if rollback_target is not None:
                rollback_target.close()
            if rollback_candidate is not None:
                rollback_candidate.close()

        restore_swapped = False
        try:
            _inject(fault_injector, "before_restore_swap")
            for suffix in ("-wal", "-shm"):
                with suppress(FileNotFoundError):
                    database.path.with_name(database.path.name + suffix).unlink()
            _atomic_replace(temporary, database.path)
            restore_swapped = True
            _inject(fault_injector, "after_restore_swap")
            active = _connect(database.path)
            try:
                _health(active, deep=True)
                if _migration_inventory(active) != receipt.migration_checksums:
                    raise BackupError("RESTORE_SCHEMA_MISMATCH")
                _, occurred_at = _trusted_now(clock)
                active.execute("BEGIN IMMEDIATE")
                _insert_backup_receipt(active, receipt)
                _insert_backup_receipt(active, pre_restore)
                _insert_restore_receipt(
                    active,
                    restore_id=restore_id,
                    receipt=receipt,
                    pre_restore=pre_restore,
                    occurred_at=occurred_at,
                )
                active.commit()
            finally:
                active.close()
        except Exception as exc:
            if restore_swapped:
                try:
                    for suffix in ("-wal", "-shm"):
                        with suppress(FileNotFoundError):
                            database.path.with_name(database.path.name + suffix).unlink()
                    _atomic_replace(rollback_temporary, database.path)
                    rollback_staged = False
                    restore_swapped = False
                    rollback = _connect(database.path)
                    try:
                        _health(rollback, deep=True)
                        if (
                            _migration_inventory(rollback)
                            != pre_restore.migration_checksums
                            or _table_rows(rollback) != pre_restore.table_rows
                        ):
                            raise BackupError("RESTORE_ROLLBACK_FAILED")
                    finally:
                        rollback.close()
                except Exception:
                    raise BackupError("RESTORE_ROLLBACK_FAILED") from exc
            if type(exc) is BackupError:
                raise
            raise BackupError("RESTORE_POST_SWAP_FAILED") from None
        finally:
            with suppress(FileNotFoundError):
                temporary.unlink()
            with suppress(FileNotFoundError):
                rollback_temporary.unlink()
    return RestoreResult(
        restore_id=restore_id,
        backup=receipt,
        pre_restore_backup=pre_restore,
    )


__all__ = [
    "BACKUP_RECEIPT_VERSION",
    "BackupError",
    "BackupReceipt",
    "ExpiredBackupPurgeSummary",
    "FaultInjector",
    "RestoreResult",
    "create_backup",
    "purge_expired_backup",
    "purge_expired_backups",
    "read_backup_receipt",
    "receipt_path",
    "resolve_backup_path",
    "restore_backup",
    "verify_backup",
]
