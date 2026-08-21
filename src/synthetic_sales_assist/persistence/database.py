"""Explicit SQLite connection, transaction, and maintenance coordination."""

from __future__ import annotations

import os
import sqlite3
import weakref
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import BinaryIO, Final

from synthetic_sales_assist.persistence.faults import FaultInjector, FaultPoint
from synthetic_sales_assist.persistence.migrations import (
    DEFAULT_MIGRATIONS_DIRECTORY,
    PROJECT_ROOT,
    apply_migrations,
)
from synthetic_sales_assist.persistence.paths import validate_local_path
from synthetic_sales_assist.persistence.schema import (
    DatabaseVerification,
    verify_database,
)


class DatabaseError(RuntimeError):
    """Base non-payload persistence error."""


class DatabaseBusyError(DatabaseError):
    """The bounded SQLite or maintenance coordination window was unavailable."""


class DatabaseConfigurationError(DatabaseError):
    """A SQLite connection could not enforce the application policy."""


_ACTIVITY_LOCK_SLOT_COUNT: Final = 256


class _InterprocessActivityLock:
    """Crash-released shared-operation/exclusive-maintenance filesystem lock.

    POSIX supplies shared/exclusive ``flock`` directly. Windows ``msvcrt`` exposes
    only exclusive byte-range locks, so ordinary operations each retain one of a
    bounded set of one-byte slots while maintenance atomically locks the complete
    range. The operating system releases either form when a process exits.
    """

    def __init__(self, database_path: Path) -> None:
        self.path = database_path.with_name(f".{database_path.name}.activity.lock")

    def _open(self) -> BinaryIO:
        try:
            handle = self.path.open("a+b", buffering=0)
            handle.seek(0, os.SEEK_END)
            if handle.tell() < _ACTIVITY_LOCK_SLOT_COUNT:
                handle.seek(_ACTIVITY_LOCK_SLOT_COUNT - 1)
                handle.write(b"\0")
                handle.flush()
            return handle
        except OSError as exc:
            raise DatabaseConfigurationError("DATABASE_ACTIVITY_LOCK_UNAVAILABLE") from exc

    @contextmanager
    def operation(self) -> Iterator[None]:
        handle = self._open()
        try:
            if os.name == "nt":
                import msvcrt

                locked_slot: int | None = None
                for slot in range(_ACTIVITY_LOCK_SLOT_COUNT):
                    try:
                        handle.seek(slot)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    except OSError:
                        continue
                    locked_slot = slot
                    break
                if locked_slot is None:
                    raise DatabaseBusyError("DATABASE_MAINTENANCE_ACTIVE")
                try:
                    yield
                finally:
                    handle.seek(locked_slot)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            elif os.name == "posix":
                import fcntl

                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                except OSError:
                    raise DatabaseBusyError("DATABASE_MAINTENANCE_ACTIVE") from None
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            else:
                raise DatabaseConfigurationError("DATABASE_ACTIVITY_LOCK_UNSUPPORTED")
        finally:
            handle.close()

    @contextmanager
    def maintenance(self) -> Iterator[None]:
        handle = self._open()
        try:
            if os.name == "nt":
                import msvcrt

                try:
                    handle.seek(0)
                    msvcrt.locking(
                        handle.fileno(),
                        msvcrt.LK_NBLCK,
                        _ACTIVITY_LOCK_SLOT_COUNT,
                    )
                except OSError:
                    raise DatabaseBusyError("DATABASE_OPERATION_ACTIVE") from None
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(
                        handle.fileno(),
                        msvcrt.LK_UNLCK,
                        _ACTIVITY_LOCK_SLOT_COUNT,
                    )
            elif os.name == "posix":
                import fcntl

                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    raise DatabaseBusyError("DATABASE_OPERATION_ACTIVE") from None
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            else:
                raise DatabaseConfigurationError("DATABASE_ACTIVITY_LOCK_UNSUPPORTED")
        finally:
            handle.close()


@dataclass(frozen=True, slots=True)
class DatabaseConnectionPolicy:
    busy_timeout_ms: int = 5_000
    journal_mode: str = "wal"
    synchronous: str = "FULL"

    def __post_init__(self) -> None:
        if (
            type(self.busy_timeout_ms) is not int
            or not 1 <= self.busy_timeout_ms <= 60_000
            or self.journal_mode != "wal"
            or self.synchronous != "FULL"
        ):
            raise DatabaseConfigurationError("SQLITE_POLICY_INVALID")


class DatabaseActivityCoordinator:
    """Reject restore/maintenance while a UoW is active, and vice versa."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._active_operations = 0
        self._maintenance_active = False

    @property
    def active_operations(self) -> int:
        with self._lock:
            return self._active_operations

    @contextmanager
    def operation(self) -> Iterator[None]:
        with self._lock:
            if self._maintenance_active:
                raise DatabaseBusyError("DATABASE_MAINTENANCE_ACTIVE")
            self._active_operations += 1
        try:
            yield
        finally:
            with self._lock:
                self._active_operations -= 1

    @contextmanager
    def maintenance(self) -> Iterator[None]:
        with self._lock:
            if self._maintenance_active or self._active_operations:
                raise DatabaseBusyError("DATABASE_OPERATION_ACTIVE")
            self._maintenance_active = True
        try:
            yield
        finally:
            with self._lock:
                self._maintenance_active = False


_COORDINATOR_REGISTRY_LOCK = RLock()
_COORDINATORS_BY_PATH: weakref.WeakValueDictionary[
    str, DatabaseActivityCoordinator
] = weakref.WeakValueDictionary()


def _coordinator_for_path(path: Path) -> DatabaseActivityCoordinator:
    """Share in-process activity state for every handle to one resolved file."""

    key = os.path.normcase(os.fspath(path))
    with _COORDINATOR_REGISTRY_LOCK:
        coordinator = _COORDINATORS_BY_PATH.get(key)
        if coordinator is None:
            coordinator = DatabaseActivityCoordinator()
            _COORDINATORS_BY_PATH[key] = coordinator
        return coordinator


TrustedClock = Callable[[], datetime]


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


class SQLiteDatabase:
    """One local SQLite file with connection-per-operation explicit UoWs."""

    def __init__(
        self,
        path: Path | str,
        *,
        migrations_directory: Path | str = DEFAULT_MIGRATIONS_DIRECTORY,
        repository_root: Path | str = PROJECT_ROOT,
        busy_timeout_ms: int = 5_000,
        clock: TrustedClock | None = None,
    ) -> None:
        self._repository_root = Path(repository_root).resolve(strict=True)
        self.path = validate_local_path(path, repository_root=self._repository_root)
        self._migrations_directory = Path(migrations_directory)
        self.policy = DatabaseConnectionPolicy(busy_timeout_ms=busy_timeout_ms)
        self.clock = _default_clock if clock is None else clock
        if not callable(self.clock):
            raise DatabaseConfigurationError("DATABASE_CLOCK_INVALID")
        self.coordinator = _coordinator_for_path(self.path)
        self.activity_lock_path = self.path.with_name(f".{self.path.name}.activity.lock")
        self._activity_lock = _InterprocessActivityLock(self.path)

    def _connect(self, *, query_only: bool = False) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(
                self.path,
                timeout=self.policy.busy_timeout_ms / 1_000,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA busy_timeout = {self.policy.busy_timeout_ms}")
            journal = connection.execute("PRAGMA journal_mode = WAL").fetchone()
            connection.execute("PRAGMA synchronous = FULL")
            if query_only:
                connection.execute("PRAGMA query_only = ON")
            foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()
            synchronous = connection.execute("PRAGMA synchronous").fetchone()
            if (
                journal is None
                or str(journal[0]).lower() != self.policy.journal_mode
                or foreign_keys is None
                or int(foreign_keys[0]) != 1
                or synchronous is None
                or int(synchronous[0]) != 2
            ):
                connection.close()
                raise DatabaseConfigurationError("SQLITE_CONNECTION_POLICY_FAILED")
            return connection
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                raise DatabaseBusyError("SQLITE_BUSY") from None
            raise DatabaseConfigurationError("SQLITE_CONNECTION_FAILED") from exc

    def initialize(self) -> DatabaseVerification:
        """Create the parent directory, migrate, and verify the exact current schema."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.coordinator.operation():
            with self._activity_lock.operation():
                connection = self._connect()
                try:
                    apply_migrations(
                        connection,
                        self._migrations_directory,
                        repository_root=self._repository_root,
                        clock=self.clock,
                    )
                    return verify_database(
                        connection,
                        migrations_directory=self._migrations_directory,
                        repository_root=self._repository_root,
                    )
                finally:
                    connection.close()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        """Open one read-only deferred transaction."""

        with self.coordinator.operation():
            with self._activity_lock.operation():
                connection = self._connect(query_only=True)
                try:
                    connection.execute("BEGIN")
                    yield connection
                    connection.commit()
                except Exception:
                    if connection.in_transaction:
                        connection.rollback()
                    raise
                finally:
                    connection.close()

    @contextmanager
    def write(
        self,
        *,
        fault_injector: FaultInjector | None = None,
    ) -> Iterator[sqlite3.Connection]:
        """Open one serialized writer transaction and commit only on clean exit."""

        injector = FaultInjector() if fault_injector is None else fault_injector
        if type(injector) is not FaultInjector:
            raise DatabaseConfigurationError("FAULT_INJECTOR_INVALID")
        with self.coordinator.operation():
            with self._activity_lock.operation():
                connection = self._connect()
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    yield connection
                    injector.hit(FaultPoint.BEFORE_COMMIT)
                    connection.commit()
                except sqlite3.OperationalError as exc:
                    if connection.in_transaction:
                        connection.rollback()
                    if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                        raise DatabaseBusyError("SQLITE_BUSY") from None
                    raise
                except Exception:
                    if connection.in_transaction:
                        connection.rollback()
                    raise
                finally:
                    connection.close()

    @contextmanager
    def maintenance(self) -> Iterator[None]:
        """Acquire nonblocking process-local and cross-process maintenance ownership."""

        with self.coordinator.maintenance():
            with self._activity_lock.maintenance():
                yield

    @contextmanager
    def snapshot(self) -> Iterator[None]:
        """Coordinate an online snapshot without excluding readers or writers."""

        with self.coordinator.operation():
            with self._activity_lock.operation():
                yield


__all__ = [
    "DatabaseActivityCoordinator",
    "DatabaseBusyError",
    "DatabaseConfigurationError",
    "DatabaseConnectionPolicy",
    "DatabaseError",
    "SQLiteDatabase",
    "TrustedClock",
]
