"""Opt-in, one-renewal session using an existing client-credentials connection."""

from __future__ import annotations

import ctypes
import http.client
import json
import math
import os
import ssl
import threading
import time
from ctypes import wintypes
from urllib.parse import urlencode

from . import local_auth
from .contract import USER_ID, TransferError

MODE = "dpapi-session-client-credentials"
OWNERSHIP_STATES = {"cleanup-complete", "controlled-handoff-complete"}
HOST = "api.helpscout.net"
TOKEN_PATH = "/v2/oauth2/token"
MAX_TOKEN_RESPONSE = 64 * 1024
REQUIRED_FIELDS = {"client_id", "client_secret", "access_token", "expires_at", "user_id"}


class SessionLease:
    """Exclusive named-object lifetime, independent of the caller's thread.

    CreateMutex without ownership atomically reports an existing object. Denied
    callers close their extra handle; the sole accepted handle lasts for the
    session and the OS closes it on process death. No files or ACLs are written.
    This coordinates this provider only; cleanup requires an explicit handoff.
    """

    def __init__(self):
        # Fixed integration identity excludes aliases and different private roots.
        self._name = "Global\\SalesAssist.HelpScout.Session.User." + str(USER_ID)
        self._handle = None
        self._kernel = None

    def acquire(self):
        if os.name != "nt" or self._handle is not None:
            raise TransferError("HELP_SCOUT_RENEWAL_LEASE_UNAVAILABLE", 503)
        kernel = local_auth._dll("kernel32.dll")
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        ctypes.set_last_error(0)
        handle = kernel.CreateMutexW(None, False, self._name)
        error = ctypes.get_last_error()
        if not handle:
            raise TransferError("HELP_SCOUT_RENEWAL_LEASE_UNAVAILABLE", 503)
        if error == 183:  # ERROR_ALREADY_EXISTS, including another local instance.
            kernel.CloseHandle(handle)
            raise TransferError("HELP_SCOUT_RENEWAL_OWNER_CONFLICT", 503)
        self._kernel, self._handle = kernel, handle

    def close(self):
        if self._handle is not None:
            self._kernel.CloseHandle(self._handle)
            self._handle = None


class SessionClientCredentials:
    """Lazy read, explicit ownership, at most one token POST, no persistent writes."""

    def __init__(self, path, *, ownership, clock=time.time):
        if type(ownership) is not str or ownership not in OWNERSHIP_STATES:
            raise TransferError("HELP_SCOUT_RENEWAL_OWNERSHIP_REQUIRED", 503)
        self._path = local_auth.connection_path(path)
        self._clock = clock
        self._lock = threading.Lock()
        self._lease = SessionLease()
        self._loaded = self._renewed = self._rejected = False
        self._token = self._client_id = self._client_secret = None
        self._expires_at = 0
        self._failure = None

    def __repr__(self):
        return "<SessionClientCredentials redacted>"

    def _clear(self):
        self._token = self._client_id = self._client_secret = None
        self._expires_at = 0

    def _fail(self, code):
        self._failure = code
        self._clear()
        raise TransferError(code, 503) from None

    def _load(self):
        self._lease.acquire()
        plain, record = None, None
        try:
            raw = local_auth._read_encrypted(self._path)
            if not 0 < len(raw) <= local_auth.MAX_CONNECTION_BYTES:
                raise ValueError()
            plain = local_auth._unprotect(raw)
            if not 0 < len(plain) <= local_auth.MAX_CONNECTION_BYTES:
                raise ValueError()
            record = json.loads(plain, object_pairs_hook=local_auth._unique_object)
            if (
                type(record) is not dict or not REQUIRED_FIELDS <= set(record)
                or set(record) - REQUIRED_FIELDS - {"grant_type", "token_type"}
                or record.get("grant_type", "client_credentials") != "client_credentials"
            ):
                self._fail("HELP_SCOUT_CONNECTION_GRANT_AMBIGUOUS")
            if (
                type(record["user_id"]) not in (str, int)
                or str(record["user_id"]) != str(USER_ID)
                or not all(local_auth.valid_token(record[key]) for key in (
                    "client_id", "client_secret", "access_token"
                ))
                or type(record["expires_at"]) not in (int, float)
                or not math.isfinite(record["expires_at"]) or record["expires_at"] <= 0
                or type(record.get("token_type", "bearer")) is not str
                or record.get("token_type", "bearer").lower() != "bearer"
            ):
                raise ValueError()
            self._client_id, self._client_secret = record["client_id"], record["client_secret"]
            self._token, self._expires_at = record["access_token"], record["expires_at"]
            self._loaded = True
        finally:
            if isinstance(record, dict):
                record.clear()
            if isinstance(plain, bytearray):
                plain[:] = b"\0" * len(plain)

    def _renew(self, now):
        if self._renewed:
            self._fail("HELP_SCOUT_SESSION_RENEWAL_LIMIT")
        # Reserve the only attempt before any socket/POST. Unknown outcomes stop.
        self._renewed = True
        connection = None
        try:
            body = urlencode({"grant_type": "client_credentials",
                              "client_id": self._client_id,
                              "client_secret": self._client_secret}).encode("ascii")
            connection = http.client.HTTPSConnection(
                HOST, timeout=15, context=ssl.create_default_context()
            )
            connection.request("POST", TOKEN_PATH, body=body, headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            })
            response = connection.getresponse()
            if response.status != 200:
                self._fail("HELP_SCOUT_SESSION_RENEWAL_STOPPED")
            raw = response.read(MAX_TOKEN_RESPONSE + 1)
            if len(raw) > MAX_TOKEN_RESPONSE:
                raise ValueError()
            value = json.loads(raw, object_pairs_hook=local_auth._unique_object)
            if (
                type(value) is not dict
                or set(value) != {"access_token", "token_type", "expires_in"}
                or not local_auth.valid_token(value["access_token"])
                or value["access_token"] == self._token
                or type(value["token_type"]) is not str
                or value["token_type"].lower() != "bearer"
                or type(value["expires_in"]) is not int
                or not local_auth.EXPIRY_MARGIN_SECONDS < value["expires_in"] <= 172800
            ):
                raise ValueError()
            expires = now + value["expires_in"]
            after = self._now()
            if after < now or after >= expires - local_auth.EXPIRY_MARGIN_SECONDS:
                raise ValueError()
            self._token, self._expires_at, self._rejected = value["access_token"], expires, False
            # No further issuance in this session, so discard application credentials.
            self._client_id = self._client_secret = None
        except TransferError:
            raise
        except Exception:
            self._fail("HELP_SCOUT_SESSION_RENEWAL_STOPPED")
        finally:
            if connection is not None:
                connection.close()

    def _now(self):
        now = self._clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise ValueError()
        return now

    def __call__(self):
        with self._lock:
            if self._failure:
                raise TransferError(self._failure, 503)
            try:
                if not self._loaded:
                    self._load()
                now = self._now()
                if now >= self._expires_at or self._rejected:
                    self._renew(now)
                elif now >= self._expires_at - local_auth.EXPIRY_MARGIN_SECONDS:
                    # A later explicit action may run after actual expiry; no early renewal.
                    raise TransferError("HELP_SCOUT_SESSION_TOKEN_MARGIN_HOLD", 503)
                return self._token
            except PermissionError:
                self._fail("HELP_SCOUT_CONNECTION_ACCESS_DENIED")
            except TransferError as exc:
                if exc.code != "HELP_SCOUT_SESSION_TOKEN_MARGIN_HOLD":
                    self._failure = exc.code
                    self._clear()
                raise
            except Exception:
                self._fail("HELP_SCOUT_SESSION_AUTH_REQUIRED")

    def note_unauthorized(self, bearer):
        """Record a 401; never issue a request here or reject a newer generation."""
        with self._lock:
            if not self._failure and bearer == self._token:
                if self._renewed:
                    self._failure = "HELP_SCOUT_SESSION_RENEWED_TOKEN_REJECTED"
                    self._clear()
                else:
                    self._rejected = True

    def close(self):
        with self._lock:
            self._failure = "HELP_SCOUT_SESSION_AUTH_CLOSED"
            self._clear()
            self._lease.close()
