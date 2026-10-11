"""Explicit, lazy Windows DPAPI access to one existing cached token; never renews."""

from __future__ import annotations

import ctypes
import json
import math
import os
import re
import stat
import threading
import time
from ctypes import wintypes
from pathlib import Path, PureWindowsPath

from .contract import TransferError

MAX_CONNECTION_BYTES = 64 * 1024
EXPIRY_MARGIN_SECONDS = 120
SYSTEM_DLL_ONLY = 0x800


def valid_token(value):
    return (
        type(value) is str
        and bool(value)
        and len(value) <= MAX_CONNECTION_BYTES
        and all(33 <= ord(char) <= 126 for char in value)
    )


def connection_path(value):
    """Validate spelling without probing any file or expanding an environment variable."""
    if type(value) is not str or not value or len(value) > 1000:
        raise TransferError("HELP_SCOUT_CONNECTION_PATH_INVALID", 503)
    path = PureWindowsPath(value)
    if (
        not re.fullmatch(r"[A-Za-z]:", path.drive)
        or not path.root
        or path.suffix.lower() != ".dpapi"
        or any(ord(char) < 32 for char in value)
        or any(char in value[2:] for char in ':*?"<>|')
        or any(part in {".", ".."} for part in value.replace("/", "\\").split("\\"))
        or any(part.endswith((" ", ".")) for part in path.parts[1:])
        or path.is_reserved()
    ):
        raise TransferError("HELP_SCOUT_CONNECTION_PATH_INVALID", 503)
    return str(path)


def _dll(name):
    return ctypes.WinDLL(name, use_last_error=True, winmode=SYSTEM_DLL_ONLY)


def _local_regular_path(path):
    kernel = _dll("kernel32.dll")
    kernel.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    kernel.GetDriveTypeW.restype = wintypes.UINT
    if kernel.GetDriveTypeW(path.anchor) != 3:  # DRIVE_FIXED; includes no mapped shares.
        raise ValueError()
    for part in (*reversed(path.parents), path):
        info = part.lstat()
        if info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError()
    return info


def _fingerprint(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _read_encrypted(value):
    if os.name != "nt":
        raise TransferError("HELP_SCOUT_DPAPI_UNAVAILABLE", 503)
    path = Path(value)
    before = _local_regular_path(path)
    if not 0 < before.st_size <= MAX_CONNECTION_BYTES:
        raise ValueError()
    with path.open("rb") as handle:
        if _fingerprint(os.fstat(handle.fileno())) != _fingerprint(before):
            raise ValueError()
        raw = handle.read(MAX_CONNECTION_BYTES + 1)
        after = os.fstat(handle.fileno())
    if (
        len(raw) != before.st_size
        or _fingerprint(after) != _fingerprint(before)
        or _fingerprint(_local_regular_path(path)) != _fingerprint(before)
    ):
        raise ValueError()
    return raw


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _unprotect(raw):
    """No UI, optional entropy, protection/write API, subprocess, or network route."""
    if os.name != "nt":
        raise TransferError("HELP_SCOUT_DPAPI_UNAVAILABLE", 503)
    source_buffer = ctypes.create_string_buffer(raw)
    source = _Blob(len(raw), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = _Blob()
    crypt, kernel = _dll("crypt32.dll"), _dll("kernel32.dll")
    crypt.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob),
    ]
    crypt.CryptUnprotectData.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        if not crypt.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)
        ):  # CRYPTPROTECT_UI_FORBIDDEN
            raise ValueError()
        if not output.data or not 0 < output.size <= MAX_CONNECTION_BYTES:
            raise ValueError()
        return bytearray(ctypes.string_at(output.data, output.size))
    finally:
        if output.data:
            if 0 < output.size <= MAX_CONNECTION_BYTES:
                ctypes.memset(output.data, 0, output.size)
            kernel.LocalFree(output.data)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


class CachedDPAPIToken:
    """One lazy read per instance, with terminal failure and no automatic reload."""

    def __init__(self, path, *, clock=time.time):
        self._path = connection_path(path)
        self._clock = clock
        self._lock = threading.Lock()
        self._token = None
        self._expires_at = 0
        self._failure = None

    def __repr__(self):
        return "<CachedDPAPIToken redacted>"

    def __call__(self):
        with self._lock:
            if self._failure:
                raise TransferError(self._failure, 503)
            plain = None
            try:
                if self._token is None:
                    raw = _read_encrypted(self._path)
                    if not 0 < len(raw) <= MAX_CONNECTION_BYTES:
                        raise ValueError()
                    plain = _unprotect(raw)
                    if not 0 < len(plain) <= MAX_CONNECTION_BYTES:
                        raise ValueError()
                    record = json.loads(plain, object_pairs_hook=_unique_object)
                    token, expires = record.get("access_token"), record.get("expires_at")
                    if (
                        not valid_token(token)
                        or type(expires) not in (int, float)
                        or not math.isfinite(expires)
                        or record.get("token_type", "bearer").lower() != "bearer"
                    ):
                        raise ValueError()
                    # Other fields (including OAuth application secrets) are never retained.
                    self._token, self._expires_at = token, expires
                now = self._clock()
                if not math.isfinite(now) or now >= self._expires_at - EXPIRY_MARGIN_SECONDS:
                    raise TransferError("HELP_SCOUT_CACHED_TOKEN_EXPIRED", 503)
                return self._token
            except PermissionError:
                self._failure = "HELP_SCOUT_CONNECTION_ACCESS_DENIED"
            except TransferError as exc:
                self._failure = exc.code
            except Exception:
                self._failure = "HELP_SCOUT_LOCAL_AUTH_REQUIRED"
            finally:
                if isinstance(plain, bytearray):
                    plain[:] = b"\0" * len(plain)
            self._token, self._expires_at = None, 0
            raise TransferError(self._failure, 503) from None
