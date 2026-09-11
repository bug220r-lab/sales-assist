"""An isolated, durable SQLite feature store using the application's path policy."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from synthetic_sales_assist.persistence.paths import validate_local_path

_FORMAT = "synthetic-campaign-workspace/v1"
_INITIALIZE_LOCK = threading.RLock()


def _verify_format(connection: sqlite3.Connection) -> None:
    """Identify an existing feature store before any writable pragma or statement."""
    try:
        kind = connection.execute(
            "SELECT type FROM sqlite_master WHERE name='workspace_metadata'"
        ).fetchone()
        if kind is None or kind[0] != "table":
            raise ValueError("WORKSPACE_FORMAT_INVALID")
        metadata = connection.execute("SELECT singleton,format FROM workspace_metadata").fetchall()
        if [tuple(row) for row in metadata] != [(1, _FORMAT)]:
            raise ValueError("WORKSPACE_FORMAT_INVALID")
    except sqlite3.Error:
        raise ValueError("WORKSPACE_FORMAT_INVALID") from None


class Store:
    """Connection-per-operation, bounded locking and explicit atomic transactions.

    This separate store cannot migrate or write the Sales Credit/DOI database.
    It is backed up separately with SQLite's backup API while writers are quiescent.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = validate_local_path(path)
        with _INITIALIZE_LOCK:
            if self.path.exists():
                self._preflight()
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation prevents claiming an unrelated file created during preflight.
            try:
                with self.path.open("xb"):
                    pass
            except FileExistsError:
                self._preflight()
                return
            connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
            try:
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "CREATE TABLE workspace_metadata "
                    "(singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
                    "format TEXT NOT NULL CHECK(format='synthetic-campaign-workspace/v1'))"
                )
                connection.execute("INSERT INTO workspace_metadata VALUES (1, ?)", (_FORMAT,))
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                connection.close()

    def _preflight(self) -> None:
        validate_local_path(self.path)
        try:
            connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
        except sqlite3.Error:
            raise ValueError("WORKSPACE_STORE_UNAVAILABLE") from None
        try:
            _verify_format(connection)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        self._preflight()
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            connection.row_factory = sqlite3.Row
            _verify_format(connection)
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA busy_timeout=5000")
        except BaseException:
            connection.close()
            raise
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")
            yield connection
        finally:
            connection.rollback()
            connection.close()
