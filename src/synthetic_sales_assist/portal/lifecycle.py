"""Owned single-instance runtime receipt and process identity for the local portal."""

from __future__ import annotations

import os
import secrets
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import BinaryIO, Final

from synthetic_sales_assist.domain.canonical import (
    canonical_json_bytes,
    parse_canonical_json_bytes,
)
from synthetic_sales_assist.persistence.paths import (
    PathPolicyError,
    assert_real_local_directory,
)
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.portal.contracts import RUNTIME_RECEIPT_SCHEMA_VERSION


_MODULE_STARTED_AT: Final = datetime.now(timezone.utc)
_WINDOWS_EPOCH_100NS: Final = 116_444_736_000_000_000
_TOKEN_LENGTH: Final = 64
LOOPBACK_HOSTS: Final = frozenset({"127.0.0.1", "localhost", "::1"})
RUNTIME_RECEIPT_MEMBERS: Final = frozenset(
    {
        "app_version",
        "build_version",
        "csrf_token",
        "database_path",
        "database_schema_version",
        "host",
        "origin",
        "pid",
        "port",
        "process_identity_token",
        "process_start_time",
        "schema_version",
        "shutdown_token",
    }
)


class PortalLifecycleError(RuntimeError):
    """A local runtime receipt or single-instance ownership check failed."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def new_local_token() -> str:
    return secrets.token_hex(_TOKEN_LENGTH // 2)


def _canonical_process_start(value: datetime) -> str:
    rendered = value.astimezone(timezone.utc).isoformat(timespec="microseconds")
    return CanonicalTimestamp(rendered.replace("+00:00", "Z")).value


def process_start_time() -> str:
    """Return native Windows creation time; import time is only a non-Windows fallback."""

    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            native = ctypes.WinDLL("kernel32", use_last_error=True)
            native.GetCurrentProcess.argtypes = []
            native.GetCurrentProcess.restype = wintypes.HANDLE
            native.GetProcessTimes.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME),
            ]
            native.GetProcessTimes.restype = wintypes.BOOL
            creation = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            current = native.GetCurrentProcess()
            succeeded = native.GetProcessTimes(
                current,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel),
                ctypes.byref(user),
            )
            if not succeeded:
                raise PortalLifecycleError("PROCESS_START_TIME_UNAVAILABLE")
            ticks = (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
            unix_ticks = ticks - _WINDOWS_EPOCH_100NS
            seconds, remainder = divmod(unix_ticks, 10_000_000)
            created = datetime.fromtimestamp(seconds, timezone.utc) + timedelta(
                microseconds=remainder // 10
            )
            return _canonical_process_start(created)
        except (AttributeError, OSError, OverflowError, ValueError) as exc:
            raise PortalLifecycleError("PROCESS_START_TIME_UNAVAILABLE") from exc
    return _canonical_process_start(_MODULE_STARTED_AT)


def runtime_lock_path(receipt_path: Path) -> Path:
    return Path(f"{receipt_path}.lock")


@dataclass(frozen=True, slots=True)
class RuntimeReceipt:
    schema_version: str
    pid: int
    process_start_time: str
    process_identity_token: str
    csrf_token: str
    host: str
    port: int
    shutdown_token: str
    database_path: str
    app_version: str
    build_version: str
    database_schema_version: int
    origin: str

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_RECEIPT_SCHEMA_VERSION:
            raise PortalLifecycleError("RUNTIME_RECEIPT_SCHEMA_INVALID")
        if type(self.pid) is not int or self.pid <= 0:
            raise PortalLifecycleError("RUNTIME_RECEIPT_PID_INVALID")
        CanonicalTimestamp(self.process_start_time)
        tokens = (
            self.process_identity_token,
            self.csrf_token,
            self.shutdown_token,
        )
        for token in tokens:
            if (
                type(token) is not str
                or len(token) != _TOKEN_LENGTH
                or any(character not in "0123456789abcdef" for character in token)
            ):
                raise PortalLifecycleError("RUNTIME_RECEIPT_TOKEN_INVALID")
        if len(set(tokens)) != len(tokens):
            raise PortalLifecycleError("RUNTIME_RECEIPT_TOKENS_NOT_INDEPENDENT")
        if self.host not in LOOPBACK_HOSTS:
            raise PortalLifecycleError("RUNTIME_RECEIPT_HOST_INVALID")
        if type(self.port) is not int or not 1 <= self.port <= 65_535:
            raise PortalLifecycleError("RUNTIME_RECEIPT_PORT_INVALID")
        database = Path(self.database_path)
        if not database.is_absolute() or "\x00" in self.database_path:
            raise PortalLifecycleError("RUNTIME_RECEIPT_DATABASE_PATH_INVALID")
        if type(self.app_version) is not str or not self.app_version or len(self.app_version) > 64:
            raise PortalLifecycleError("RUNTIME_RECEIPT_APP_VERSION_INVALID")
        if (
            type(self.build_version) is not str
            or not self.build_version
            or len(self.build_version) > 128
        ):
            raise PortalLifecycleError("RUNTIME_RECEIPT_BUILD_VERSION_INVALID")
        if type(self.database_schema_version) is not int or self.database_schema_version <= 0:
            raise PortalLifecycleError("RUNTIME_RECEIPT_DATABASE_SCHEMA_INVALID")
        authority = f"[{self.host}]" if self.host == "::1" else self.host
        if self.origin != "http" + f"://{authority}:{self.port}":
            raise PortalLifecycleError("RUNTIME_RECEIPT_ORIGIN_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "app_version": self.app_version,
            "build_version": self.build_version,
            "csrf_token": self.csrf_token,
            "database_path": self.database_path,
            "database_schema_version": self.database_schema_version,
            "host": self.host,
            "origin": self.origin,
            "pid": self.pid,
            "port": self.port,
            "process_identity_token": self.process_identity_token,
            "process_start_time": self.process_start_time,
            "schema_version": self.schema_version,
            "shutdown_token": self.shutdown_token,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=RUNTIME_RECEIPT_MEMBERS)


class SingleInstanceLease:
    """Crash-released filesystem lock with an atomically published owned receipt."""

    def __init__(self, receipt_path: Path) -> None:
        if not isinstance(receipt_path, Path) or not receipt_path.is_absolute():
            raise PortalLifecycleError("RUNTIME_RECEIPT_PATH_INVALID")
        self.receipt_path = receipt_path
        self.lock_path = runtime_lock_path(receipt_path)
        self._handle: BinaryIO | None = None
        self._owner_token: str | None = None
        self._receipt_identity: str | None = None

    def acquire(self, owner_token: str) -> None:
        if self._handle is not None:
            raise PortalLifecycleError("RUNTIME_LEASE_ALREADY_ACQUIRED")
        if len(owner_token) != _TOKEN_LENGTH:
            raise PortalLifecycleError("RUNTIME_LEASE_TOKEN_INVALID")
        self.receipt_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            assert_real_local_directory(self.receipt_path.parent)
        except PathPolicyError as exc:
            raise PortalLifecycleError("RUNTIME_RECEIPT_PARENT_INVALID") from exc
        if self.receipt_path.is_symlink() or self.lock_path.is_symlink():
            raise PortalLifecycleError("RUNTIME_RECEIPT_LINK_PROHIBITED")
        handle: BinaryIO | None = None
        try:
            handle = self.lock_path.open("a+b")
            handle.seek(_TOKEN_LENGTH)
            if handle.read(1) == b"":
                handle.seek(_TOKEN_LENGTH)
                handle.write(b"0")
                handle.flush()
                os.fsync(handle.fileno())
            self._lock(handle)
            handle.seek(0)
            handle.truncate()
            handle.write(owner_token.encode("ascii"))
            handle.flush()
            os.fsync(handle.fileno())
        except PortalLifecycleError:
            if handle is not None:
                with suppress(Exception):
                    handle.close()
            raise
        except OSError as exc:
            if handle is not None:
                with suppress(Exception):
                    handle.close()
            raise PortalLifecycleError("RUNTIME_LEASE_UNAVAILABLE") from exc
        if handle is None:  # pragma: no cover - defensive type narrowing
            raise PortalLifecycleError("RUNTIME_LEASE_UNAVAILABLE")
        self._handle = handle
        self._owner_token = owner_token

    @staticmethod
    def _lock(handle: BinaryIO) -> None:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(_TOKEN_LENGTH)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, ImportError) as exc:
            raise PortalLifecycleError("RUNTIME_INSTANCE_ALREADY_ACTIVE") from exc

    @staticmethod
    def _unlock(handle: BinaryIO) -> None:
        if os.name == "nt":
            import msvcrt

            handle.seek(_TOKEN_LENGTH)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def publish(self, receipt: RuntimeReceipt) -> None:
        if self._handle is None or receipt.process_identity_token != self._owner_token:
            raise PortalLifecycleError("RUNTIME_LEASE_NOT_OWNED")
        payload = receipt.canonical_bytes()
        temporary = self.receipt_path.with_name(
            f".{self.receipt_path.name}.{receipt.process_identity_token}.tmp"
        )
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        descriptor: int | None = None
        try:
            descriptor = os.open(temporary, flags, 0o600)
            os.write(descriptor, payload)
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = None
            os.replace(temporary, self.receipt_path)
            with suppress(OSError):
                os.chmod(self.receipt_path, 0o600)
        except OSError as exc:
            if descriptor is not None:
                with suppress(OSError):
                    os.close(descriptor)
            with suppress(OSError):
                temporary.unlink()
            raise PortalLifecycleError("RUNTIME_RECEIPT_PUBLISH_FAILED") from exc
        self._receipt_identity = receipt.process_identity_token

    def _remove_owned_receipt(self) -> None:
        if self._receipt_identity is None or not self.receipt_path.is_file():
            return
        try:
            raw = self.receipt_path.read_bytes()
            value = parse_canonical_json_bytes(
                raw,
                expected_members=RUNTIME_RECEIPT_MEMBERS,
            )
        except (OSError, ValueError):
            return
        if (
            type(value) is dict
            and value.get("process_identity_token") == self._receipt_identity
        ):
            with suppress(OSError):
                self.receipt_path.unlink()

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        self._remove_owned_receipt()
        try:
            self._unlock(handle)
        except OSError:
            pass
        handle.close()
        self._handle = None
        owner = self._owner_token
        self._owner_token = None
        self._receipt_identity = None
        if owner is not None:
            try:
                if self.lock_path.read_text(encoding="ascii") == owner:
                    self.lock_path.unlink()
            except OSError:
                pass

    def __enter__(self) -> SingleInstanceLease:
        if self._owner_token is None:
            self.acquire(new_local_token())
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


__all__ = [
    "LOOPBACK_HOSTS",
    "PortalLifecycleError",
    "RUNTIME_RECEIPT_MEMBERS",
    "RuntimeReceipt",
    "SingleInstanceLease",
    "new_local_token",
    "process_start_time",
    "runtime_lock_path",
]
