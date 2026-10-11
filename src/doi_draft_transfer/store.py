"""Separate private SQLite journal; never reads or updates existing review stores."""

from __future__ import annotations

import json
import sqlite3
import stat
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from synthetic_sales_assist.persistence.paths import validate_local_path

from .contract import TransferError, digest, encoded

FILENAME = "doi-draft-transfer.sqlite3"
MAX_DATABASE = 256 * 1024 * 1024
MAX_EVENTS = 20000


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class DraftTransferStore:
    """BEGIN IMMEDIATE serializes edits, approvals and pre-write reservations."""

    def __init__(self, path):
        self.path = Path(path)

    def checked_path(self):
        try:
            path = self.path
            if not path.is_absolute() or path.name != FILENAME or ".." in path.parts:
                raise ValueError()
            for candidate in (
                *reversed(path.parents),
                path,
                path.with_name(path.name + "-journal"),
                path.with_name(path.name + "-wal"),
                path.with_name(path.name + "-shm"),
            ):
                try:
                    info = candidate.lstat()
                except FileNotFoundError:
                    continue
                if (
                    stat.S_ISLNK(info.st_mode)
                    or getattr(info, "st_file_attributes", 0) & 0x400
                    or stat.S_ISREG(info.st_mode)
                    and info.st_nlink != 1
                ):
                    raise ValueError()
            validate_local_path(path)
            if not path.parent.is_dir():
                raise ValueError()
            if path.exists() and (not path.is_file() or path.stat().st_size > MAX_DATABASE):
                raise ValueError()
            return path
        except (OSError, ValueError, RuntimeError):
            raise TransferError("TRANSFER_STORAGE_UNAVAILABLE", 503) from None

    @contextmanager
    def transaction(self, *, write=False):
        path = self.checked_path()
        if not write and not path.exists():
            yield None
            return
        con = None
        try:
            uri = path.as_uri() + ("?mode=rwc" if write else "?mode=ro")
            con = sqlite3.connect(uri, uri=True, timeout=3, isolation_level=None)
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA trusted_schema=OFF")
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("PRAGMA synchronous=FULL")
            con.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if write and version == 0:
                for statement in SCHEMA:
                    con.execute(statement)
                con.execute("PRAGMA user_version=1")
                version = 1
            if version != 1:
                raise TransferError("TRANSFER_STORAGE_SCHEMA", 503)
            yield con
            con.commit()
        except TransferError:
            if con:
                con.rollback()
            raise
        except (sqlite3.Error, OSError, ValueError, KeyError, TypeError):
            if con:
                con.rollback()
            raise TransferError("TRANSFER_STORAGE_UNAVAILABLE", 503) from None
        finally:
            if con:
                con.close()

    @staticmethod
    def revision(con):
        return con.execute("SELECT revision FROM meta WHERE id=1").fetchone()[0] if con else 0

    @staticmethod
    def bump(con):
        con.execute("UPDATE meta SET revision=revision+1 WHERE id=1")

    @staticmethod
    def load(con, oid):
        if con is None:
            return None
        record = con.execute("SELECT * FROM drafts WHERE order_id=?", (oid,)).fetchone()
        if record is None:
            return None
        result = dict(record)
        for key in ("row_json", "review_json", "approval_json"):
            result[key.removesuffix("_json")] = json.loads(result.pop(key))
        transfer = con.execute(
            "SELECT result_json FROM transfers WHERE order_id=?", (oid,)
        ).fetchone()
        result["transfer"] = json.loads(transfer[0]) if transfer else None
        return result

    @staticmethod
    def put(con, oid, version, row, review, approval):
        con.execute(
            "INSERT INTO drafts VALUES (?,?,?,?,?,?) ON CONFLICT(order_id) DO UPDATE SET "
            "version=excluded.version,row_json=excluded.row_json,review_json=excluded.review_json,"
            "approval_json=excluded.approval_json,updated_at=excluded.updated_at",
            (
                oid,
                version,
                encoded(row).decode(),
                encoded(review).decode(),
                encoded(approval).decode(),
                utc_now(),
            ),
        )
        # A version is immutable; approval events are recorded separately.
        con.execute(
            "INSERT OR IGNORE INTO versions VALUES (?,?,?,?,?)",
            (oid, version, encoded(row).decode(), encoded(review).decode(), utc_now()),
        )

    @staticmethod
    def event(con, kind, oid, version, details):
        previous = con.execute(
            "SELECT sequence,event_hash FROM audit ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        sequence = previous[0] + 1 if previous else 1
        if sequence > MAX_EVENTS:
            raise TransferError("TRANSFER_AUDIT_CAPACITY", 503)
        event = {
            "sequence": sequence,
            "previous_hash": previous[1] if previous else "",
            "at_utc": utc_now(),
            "kind": kind,
            "order_id": oid,
            "version": version,
            "details": details,
        }
        con.execute(
            "INSERT INTO audit VALUES (?,?,?)", (sequence, encoded(event).decode(), digest(event))
        )

    @staticmethod
    def transfer(con, oid, result):
        con.execute(
            "INSERT INTO transfers VALUES (?,?) ON CONFLICT(order_id) DO UPDATE SET "
            "result_json=excluded.result_json",
            (oid, encoded(result).decode()),
        )


SCHEMA = (
    "CREATE TABLE meta (id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL)",
    "INSERT INTO meta VALUES (1,0)",
    "CREATE TABLE drafts (order_id TEXT PRIMARY KEY,version INTEGER NOT NULL,"
    "row_json TEXT NOT NULL,review_json TEXT NOT NULL,approval_json TEXT NOT NULL,"
    "updated_at TEXT NOT NULL)",
    "CREATE TABLE versions (order_id TEXT NOT NULL,version INTEGER NOT NULL,"
    "row_json TEXT NOT NULL,review_json TEXT NOT NULL,created_at TEXT NOT NULL,"
    "PRIMARY KEY(order_id,version))",
    "CREATE TABLE transfers (order_id TEXT PRIMARY KEY,result_json TEXT NOT NULL)",
    (
        "CREATE TABLE audit (sequence INTEGER PRIMARY KEY,event_json TEXT "
        "NOT NULL,event_hash TEXT NOT NULL)"
    ),
)
