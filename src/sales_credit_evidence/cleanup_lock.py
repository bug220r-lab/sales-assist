"""Lazy adapter for the reviewed cleanup owner's existing Windows byte lock.

The cleanup release's ``execute_release.OperationLock`` locks byte zero with
``msvcrt.LK_NBLCK`` and retains ``operation-v1.lock`` after release. Its
``batch_runner.live_reader`` binds the connection to the suffix below. Only
that reviewed pairing under the same explicit Documents root is accepted.
No source module, connection, configuration, or process is loaded here.

Unlike the owner's initialization route, this adapter requires the existing
nonempty file and opens r+b: it never creates, seeds, truncates, or deletes it.
The caller must complete its activation/ownership gates before ``acquire``.
"""

from __future__ import annotations

import ntpath
import os
import stat
from pathlib import Path, PureWindowsPath
from typing import Any, BinaryIO

from .transport import ReadError

_CONNECTION_SUFFIX = (
    "HelpScout",
    "ECS_Campaign_Replies_2026-09-11",
    "local-review",
    "helpscout-auth.dpapi",
)
_LOCK_SUFFIX = (
    "Codex",
    "2026-10-10",
    "task-3",
    "helpscout_one_outbound_candidate",
    "operation-v1.lock",
)
CLEANUP_LOCK_ERROR_CODES = frozenset(
    {
        "cleanup_lock_scope_invalid",
        "cleanup_lock_windows_required",
        "cleanup_lock_missing",
        "cleanup_lock_invalid",
        "cleanup_lock_unavailable",
        "cleanup_lock_already_attempted",
        "cleanup_lock_closed",
        "cleanup_lock_release_failed",
    }
)


def _lexical_path(value: str) -> PureWindowsPath:
    if type(value) is not str or not value or len(value) > 1000:
        raise ReadError("cleanup_lock_scope_invalid")
    path = PureWindowsPath(value)
    if (
        len(path.drive) != 2
        or not path.drive[0].isascii()
        or not path.drive[0].isalpha()
        or path.drive[1] != ":"
        or not path.root
        or any(ord(char) < 32 for char in value)
        or any(char in value[2:] for char in ':*?"<>|')
        or any(part in {".", ".."} for part in value.replace("/", "\\").split("\\"))
        or any(part.endswith((" ", ".")) for part in path.parts[1:])
        or any(PureWindowsPath(part).is_reserved() for part in path.parts[1:])
        or ntpath.normcase(value) != ntpath.normcase(str(path))
    ):
        raise ReadError("cleanup_lock_scope_invalid")
    return path


def _bound_lock_path(connection_path: str, cleanup_lock_path: str) -> str:
    connection = _lexical_path(connection_path)
    lock = _lexical_path(cleanup_lock_path)
    parts = connection.parts
    if (
        len(parts) != 8
        or parts[1].casefold() != "users"
        or parts[3].casefold() != "documents"
        or tuple(part.casefold() for part in parts[4:])
        != tuple(part.casefold() for part in _CONNECTION_SUFFIX)
    ):
        raise ReadError("cleanup_lock_scope_invalid")
    documents = PureWindowsPath(*parts[:4])
    expected = documents.joinpath(*_LOCK_SUFFIX)
    if lock != expected:
        raise ReadError("cleanup_lock_scope_invalid")
    return str(expected)


def _is_windows() -> bool:
    return os.name == "nt"


def _inspect_lock(path: Path) -> os.stat_result:
    # Reuse the existing fixed-drive and ancestor-reparse checks, without ever
    # inspecting the connection path or reading file contents.
    from doi_draft_transfer import local_auth as local_auth_module

    local_auth: Any = local_auth_module
    info: os.stat_result = local_auth._local_regular_path(path)
    return info


def _identity(info: os.stat_result) -> tuple[int, int, int, int]:
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_size < 1
        or info.st_nlink != 1
        or info.st_ino <= 0
        or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    ):
        raise ValueError
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _open_existing_lock(path: Path) -> BinaryIO:
    return path.open("r+b", buffering=0)


def _lock_fd(descriptor: int, *, release: bool) -> None:
    import msvcrt

    msvcrt.locking(descriptor, msvcrt.LK_UNLCK if release else msvcrt.LK_NBLCK, 1)


class CleanupLease:
    """One nonblocking acquisition; construction and repr perform no I/O."""

    def __init__(self, connection_path: str, cleanup_lock_path: str) -> None:
        self._path = Path(_bound_lock_path(connection_path, cleanup_lock_path))
        self._handle: BinaryIO | None = None
        self._locked = False
        self._attempted = False
        self._closed = False

    def __repr__(self) -> str:
        return "<CleanupLease redacted>"

    def acquire(self) -> None:
        if self._closed:
            raise ReadError("cleanup_lock_closed")
        if self._attempted:
            raise ReadError("cleanup_lock_already_attempted")
        self._attempted = True
        if not _is_windows():
            raise ReadError("cleanup_lock_windows_required")
        code: str | None = "cleanup_lock_invalid"
        try:
            before = _identity(_inspect_lock(self._path))
            code = "cleanup_lock_unavailable"
            self._handle = _open_existing_lock(self._path)
            code = "cleanup_lock_invalid"
            if _identity(os.fstat(self._handle.fileno())) != before:
                raise ValueError
            self._handle.seek(0)
            code = "cleanup_lock_unavailable"
            _lock_fd(self._handle.fileno(), release=False)
            self._locked = True
            code = "cleanup_lock_invalid"
            if (
                _identity(os.fstat(self._handle.fileno())) != before
                or _identity(_inspect_lock(self._path)) != before
            ):
                raise ValueError
            code = None
        except FileNotFoundError:
            code = "cleanup_lock_missing"
        except Exception:
            pass
        if code is not None:
            if not self._release_handle():
                code = "cleanup_lock_release_failed"
            # Outside the handler: no raw path-bearing cause or context escapes.
            raise ReadError(code)

    def _release_handle(self) -> bool:
        handle, self._handle = self._handle, None
        locked, self._locked = self._locked, False
        if handle is None:
            return True
        success = True
        try:
            if locked:
                handle.seek(0)
                _lock_fd(handle.fileno(), release=True)
        except Exception:
            success = False
        finally:
            try:
                handle.close()
            except Exception:
                success = False
        return success

    def close(self) -> None:
        self._closed = True
        if not self._release_handle():
            raise ReadError("cleanup_lock_release_failed")


def new_cleanup_lease(connection_path: str, cleanup_lock_path: str) -> CleanupLease:
    """Construct inertly; the coordinator acquires only after explicit gates."""
    return CleanupLease(connection_path, cleanup_lock_path)
