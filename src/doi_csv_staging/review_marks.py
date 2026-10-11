"""Private local attention markers; never a fulfillment or eligibility decision."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat

from synthetic_sales_assist.persistence.paths import validate_local_path
from .staging import StagedOrder


SCHEMA = "doi-reviewed-split-store/v1"
MAX_MARKS = 10000
MAX_BYTES = 2 * 1024 * 1024
HASH = re.compile(r"[0-9a-f]{64}\Z")
AMBIGUOUS = frozenset(
    {
        "DUPLICATE_SUMMARY",
        "CONFLICTING_SUMMARY",
        "DUPLICATE_LINE_ID",
        "CONFLICTING_LINE",
        "DISPLAYED_ORDER_ID_UNVERIFIED",
        "SOURCE_JOIN_MISMATCH",
        "MISSING_SUMMARY",
        "MISSING_LINES",
        "MISSING_LINE_ID",
    }
)


class ReviewMarkError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _encoded(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def order_key(order_id: str) -> str:
    return hashlib.sha256(("doi-reviewed-order/v1:" + order_id).encode()).hexdigest()


def evidence_key(order: StagedOrder, *, global_held: bool = False) -> str | None:
    """Bind one unambiguous record and its capture; never store the source fields."""
    if (
        global_held
        or len(order.summary_occurrences) != 1
        or not order.line_occurrences
        or set(order.holds) & AMBIGUOUS
    ):
        return None

    def fields(row):
        # Contact email is irrelevant to whether this split evidence was reviewed.
        return {key: value for key, value in row.raw_fields if key != "customer_info_email"}

    payload = {
        "schema": "doi-reviewed-evidence/v1",
        "order_id": order.canonical_order_id,
        "summary": fields(order.summary_occurrences[0]),
        "lines": sorted((fields(row) for row in order.line_occurrences), key=_encoded),
    }
    return hashlib.sha256(_encoded(payload)).hexdigest()


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ReviewMarkError("REVIEW_MARKS_UNAVAILABLE")
        value[key] = item
    return value


class ReviewMarkStore:
    """One file under the existing owned, user-local application data directory.

    The portal's existing process lease supplies the single writer. A separate
    store revision rejects stale tabs. The file contains only two hashes per
    checked order; an unchecked order has no entry. Clear/load/expiry never erase it.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def _path(self) -> Path:
        try:
            path = self.path
            if (
                not path.is_absolute()
                or ".." in path.parts
                or path.name != "doi-reviewed-split.json"
            ):
                raise ValueError()
            # Inspect ancestors before descendants; never follow a reparse path.
            for node in (*reversed(path.parents), path):
                try:
                    info = node.lstat()
                except FileNotFoundError:
                    if node != path:
                        raise ValueError()
                    continue
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise ValueError()
                if node == path and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                    raise ValueError()
            return validate_local_path(path)
        except (OSError, ValueError, RuntimeError):
            raise ReviewMarkError("REVIEW_MARKS_UNAVAILABLE") from None

    def read(self) -> tuple[int, dict[str, str]]:
        try:
            path = self._path()
            try:
                with path.open("rb") as stream:
                    raw = stream.read(MAX_BYTES + 1)
            except FileNotFoundError:
                return 0, {}
            if len(raw) > MAX_BYTES:
                raise ValueError()
            value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
            if (
                type(value) is not dict
                or set(value) != {"schema", "revision", "records"}
                or value["schema"] != SCHEMA
                or type(value["revision"]) is not int
                or not 0 <= value["revision"] < 2**53 - 1
                or type(value["records"]) is not dict
                or len(value["records"]) > MAX_MARKS
                or any(
                    type(key) is not str
                    or not HASH.fullmatch(key)
                    or type(item) is not str
                    or not HASH.fullmatch(item)
                    for key, item in value["records"].items()
                )
            ):
                raise ValueError()
            return value["revision"], value["records"]
        except (OSError, ValueError, UnicodeError, RecursionError):
            raise ReviewMarkError("REVIEW_MARKS_UNAVAILABLE") from None

    def set(self, key: str, evidence: str, reviewed: bool, expected_revision: int) -> None:
        if (
            type(reviewed) is not bool
            or type(expected_revision) is not int
            or not 0 <= expected_revision < 2**53 - 1
            or type(key) is not str
            or not HASH.fullmatch(key)
            or type(evidence) is not str
            or not HASH.fullmatch(evidence)
        ):
            raise ReviewMarkError("REVIEW_MARK_REQUEST_INVALID")
        revision, records = self.read()
        if revision != expected_revision:
            raise ReviewMarkError("REVIEW_MARK_REVISION_MISMATCH")
        updated = dict(records)
        if reviewed:
            updated[key] = evidence
        else:
            updated.pop(key, None)
        if updated == records:
            return
        if len(updated) > MAX_MARKS:
            raise ReviewMarkError("REVIEW_MARKS_FULL")
        raw = _encoded({"schema": SCHEMA, "revision": revision + 1, "records": updated})
        if len(raw) > MAX_BYTES:
            raise ReviewMarkError("REVIEW_MARKS_FULL")
        temporary = None
        try:
            path = self._path()
            temporary = path.with_name(".doi-reviewed-" + secrets.token_hex(12) + ".tmp")
            with temporary.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            # Detect an intervening edit before publishing the next revision.
            if self.read() != (revision, records):
                raise ReviewMarkError("REVIEW_MARK_REVISION_MISMATCH")
            self._path()
            os.replace(temporary, path)
            temporary = None
        except ReviewMarkError:
            raise
        except (OSError, ValueError):
            raise ReviewMarkError("REVIEW_MARKS_UNAVAILABLE") from None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
