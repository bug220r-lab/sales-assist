"""One gated auth snapshot, with optional issuance only after actual expiry.

The coordinator owns both external leases. This object never discovers paths,
loads configuration, renews after a request failure, or persists credentials.
All tests must inject readers/decryptors/issuers; the default boundaries are lazy.
"""

from __future__ import annotations

import http.client
import json
import math
import ssl
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from .cached_auth import EXPIRY_MARGIN_SECONDS, MAX_SNAPSHOT_BYTES, validate_connection_path
from .transport import TARGET_AUTHOR_ID, ReadError, SuppliedCredential

SESSION_AUTH_ERROR_CODES = frozenset(
    {
        "session_live_disabled",
        "session_gate_invalid",
        "session_owner_closed",
        "session_already_loaded",
        "session_path_invalid",
        "session_snapshot_missing",
        "session_access_denied",
        "session_snapshot_read_failed",
        "session_snapshot_size_invalid",
        "session_snapshot_decrypt_failed",
        "session_plaintext_invalid",
        "session_snapshot_invalid",
        "session_metadata_invalid",
        "session_author_unverified",
        "session_author_mismatch",
        "session_application_metadata_invalid",
        "session_grant_invalid",
        "session_token_type_invalid",
        "session_expiry_unverified",
        "session_token_invalid",
        "session_clock_invalid",
        "session_cached_near_expiry",
        "session_cached_expired",
        "session_issuer_failed",
        "session_issuer_redirect",
        "session_issuer_http_error",
        "session_issuer_response_too_large",
        "session_issuance_response_invalid",
        "session_issuance_lifetime_invalid",
        "session_issued_token_unusable",
        "session_snapshot_failed",
    }
)
_REQUIRED_FIELDS = {"client_id", "client_secret", "access_token", "expires_at", "user_id"}
_OPTIONAL_FIELDS = {"grant_type", "token_type"}
_RESPONSE_FIELDS = {"access_token", "token_type", "expires_in"}
_TOKEN_HOST = "api.helpscout.net"
_TOKEN_PATH = "/v2/oauth2/token"
_TIMEOUT_SECONDS = 15.0
Issuer = Callable[[dict[str, str]], dict[str, Any]]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _clear_json(value: Any) -> None:
    """Discard nested mutable containers without recursive cleanup or cycles."""
    pending = [value]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if type(current) is dict:
            pending.extend(current.values())
            current.clear()
        elif type(current) is list:
            pending.extend(current)
            current.clear()


def _decode_json(
    plain: bytearray,
    records: list[dict[str, Any]],
    error_code: str,
) -> dict[str, Any]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        records.append(result)
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result

    def invalid_constant(_value: str) -> None:
        raise ValueError("nonfinite_json")

    try:
        data = json.loads(plain, object_pairs_hook=unique_object, parse_constant=invalid_constant)
        if type(data) is not dict:
            raise ValueError("object_required")
    except (ValueError, UnicodeError, RecursionError):
        raise ReadError(error_code) from None
    return data


def _default_issuer(fields: dict[str, str]) -> dict[str, Any]:
    """Only the owner's explicitly authorized expired-token path calls this."""
    body = bytearray(urlencode(fields).encode("ascii"))
    plain: bytearray | None = None
    records: list[dict[str, Any]] = []
    result: dict[str, Any] | None = None
    connection: http.client.HTTPSConnection | None = None
    try:
        if not 0 < len(body) <= MAX_SNAPSHOT_BYTES:
            raise ReadError("session_application_metadata_invalid")
        connection = http.client.HTTPSConnection(
            _TOKEN_HOST, timeout=_TIMEOUT_SECONDS, context=ssl.create_default_context()
        )
        connection.request(
            "POST",
            _TOKEN_PATH,
            body=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        )
        response = connection.getresponse()
        if 300 <= response.status < 400:
            raise ReadError("session_issuer_redirect", status=response.status, attempts=1)
        if response.status != 200:
            raise ReadError("session_issuer_http_error", status=response.status, attempts=1)
        plain = bytearray(response.read(MAX_SNAPSHOT_BYTES + 1))
        if not 0 < len(plain) <= MAX_SNAPSHOT_BYTES:
            raise ReadError("session_issuer_response_too_large", status=200, attempts=1)
        result = _decode_json(plain, records, "session_issuance_response_invalid")
        return result
    finally:
        body[:] = b"\0" * len(body)
        if plain is not None:
            plain[:] = b"\0" * len(plain)
        for record in records:
            if record is not result:
                record.clear()
        if connection is not None:
            connection.close()


class SessionSnapshotOwner:
    """Single enabled load; optional single issuance; no reload or automatic refresh.

    Default-off calls perform no credential I/O and do not consume the load.
    The first enabled load consumes it even if validation or issuance fails.
    Returned credentials preserve authoritative expiry. Request callers must
    continue applying the 120-second margin and treat 401/403 as terminal.
    """

    def __init__(
        self,
        path: str,
        *,
        clock: Callable[[], datetime] = _utcnow,
        encrypted_loader: Callable[[str], bytes] | None = None,
        decryptor: Callable[[bytes], bytearray] | None = None,
        issuer: Issuer | None = None,
    ) -> None:
        self._path: str | None = path
        self._clock: Callable[[], datetime] | None = clock
        self._loader = encrypted_loader
        self._decryptor = decryptor
        self._issuer = issuer
        self._used = False
        self._closed = False
        self._issuance_attempted = False
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return "<SessionSnapshotOwner redacted>"

    @property
    def issuance_attempted(self) -> bool:
        return self._issuance_attempted

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._path = None
            self._clock = None
            self._loader = None
            self._decryptor = None
            self._issuer = None

    def _now(self) -> datetime:
        try:
            if self._clock is None:
                raise ValueError("clock")
            now = self._clock()
            if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
                raise ValueError("clock")
            return now.astimezone(UTC)
        except Exception:
            raise ReadError("session_clock_invalid") from None

    def load(
        self,
        *,
        enable_live: bool = False,
        allow_issuance: bool = False,
    ) -> SuppliedCredential:
        with self._lock:
            if self._closed:
                raise ReadError("session_owner_closed")
            if type(enable_live) is not bool or type(allow_issuance) is not bool:
                raise ReadError("session_gate_invalid")
            if not enable_live:
                raise ReadError("session_live_disabled")
            if self._used:
                raise ReadError("session_already_loaded")
            self._used = True
            try:
                return self._load_once(allow_issuance)
            except ReadError as error:
                code = (
                    error.code
                    if error.code in SESSION_AUTH_ERROR_CODES
                    else "session_snapshot_failed"
                )
                status = (
                    error.status
                    if type(error.status) is int and 100 <= error.status <= 599
                    else None
                )
                # Copy only safe diagnostics, discarding inner tracebacks and
                # exception contexts that can retain plaintext or private paths.
                failure = ReadError(code, status=status, attempts=int(self._issuance_attempted))
            except Exception:
                failure = ReadError("session_snapshot_failed")
            failure.__context__ = None
            failure.__cause__ = None
            raise failure from None

    def _load_once(self, allow_issuance: bool) -> SuppliedCredential:
        from doi_draft_transfer import local_auth as local_auth_module

        local_auth: Any = local_auth_module
        try:
            if self._path is None:
                raise ValueError("path")
            path = validate_connection_path(self._path)
        except Exception:
            raise ReadError("session_path_invalid") from None
        loader: Callable[[str], bytes] = (
            self._loader if self._loader is not None else local_auth._read_encrypted
        )
        decryptor: Callable[[bytes], bytearray] = (
            self._decryptor if self._decryptor is not None else local_auth._unprotect
        )
        plain: bytearray | None = None
        records: list[dict[str, Any]] = []
        fields: dict[str, str] = {}
        issued: dict[str, Any] | None = None
        try:
            try:
                encrypted = loader(path)
            except FileNotFoundError:
                raise ReadError("session_snapshot_missing") from None
            except PermissionError:
                raise ReadError("session_access_denied") from None
            except Exception:
                raise ReadError("session_snapshot_read_failed") from None
            if type(encrypted) is not bytes or not 0 < len(encrypted) <= MAX_SNAPSHOT_BYTES:
                raise ReadError("session_snapshot_size_invalid")
            try:
                plain = decryptor(encrypted)
            except Exception:
                raise ReadError("session_snapshot_decrypt_failed") from None
            if type(plain) is not bytearray or not 0 < len(plain) <= MAX_SNAPSHOT_BYTES:
                raise ReadError("session_plaintext_invalid")
            record = _decode_json(plain, records, "session_snapshot_invalid")
            expiry = self._validate_record(record, local_auth)
            now = self._now()
            if now < expiry:
                if now >= expiry - timedelta(seconds=EXPIRY_MARGIN_SECONDS):
                    raise ReadError("session_cached_near_expiry")
                return SuppliedCredential(record["access_token"], expiry)
            if not allow_issuance:
                raise ReadError("session_cached_expired")
            fields.update(
                {
                    "grant_type": "client_credentials",
                    "client_id": record["client_id"],
                    "client_secret": record["client_secret"],
                }
            )
            self._issuance_attempted = True
            issuer = self._issuer if self._issuer is not None else _default_issuer
            try:
                issued = issuer(fields)
            except ReadError as error:
                if error.code in SESSION_AUTH_ERROR_CODES:
                    raise
                raise ReadError("session_issuer_failed") from None
            except Exception:
                raise ReadError("session_issuer_failed") from None
            return self._issued_credential(issued, now)
        finally:
            for record in records:
                record.clear()
            fields.clear()
            _clear_json(issued)
            if type(plain) is bytearray:
                plain[:] = b"\0" * len(plain)

    @staticmethod
    def _validate_record(record: dict[str, Any], local_auth: Any) -> datetime:
        if "user_id" not in record:
            raise ReadError("session_author_unverified")
        if "expires_at" not in record or any(
            key in record for key in ("expires_in", "issued_at", "expiry", "expiration")
        ):
            raise ReadError("session_expiry_unverified")
        if not set(record) >= _REQUIRED_FIELDS or set(record) - (
            _REQUIRED_FIELDS | _OPTIONAL_FIELDS
        ):
            raise ReadError("session_metadata_invalid")
        if type(record["user_id"]) not in (int, str) or str(record["user_id"]) != str(
            TARGET_AUTHOR_ID
        ):
            raise ReadError("session_author_mismatch")
        if any(type(record[key]) is not str for key in _OPTIONAL_FIELDS if key in record):
            raise ReadError("session_metadata_invalid")
        if record.get("grant_type", "client_credentials") != "client_credentials":
            raise ReadError("session_grant_invalid")
        if not all(local_auth.valid_token(record[key]) for key in ("client_id", "client_secret")):
            raise ReadError("session_application_metadata_invalid")
        if record.get("token_type", "bearer").casefold() != "bearer":
            raise ReadError("session_token_type_invalid")
        epoch = record["expires_at"]
        try:
            if type(epoch) not in (int, float) or not math.isfinite(epoch) or epoch <= 0:
                raise ValueError("expiry")
            expiry = datetime.fromtimestamp(epoch, UTC)
        except (ValueError, OverflowError, OSError):
            raise ReadError("session_expiry_unverified") from None
        try:
            SuppliedCredential(record["access_token"], expiry)
        except ReadError:
            raise ReadError("session_token_invalid") from None
        return expiry

    def _issued_credential(
        self, issued: dict[str, Any], started_at: datetime
    ) -> SuppliedCredential:
        if type(issued) is not dict or set(issued) != _RESPONSE_FIELDS:
            raise ReadError("session_issuance_response_invalid")
        if type(issued["token_type"]) is not str or issued["token_type"].casefold() != "bearer":
            raise ReadError("session_issuance_response_invalid")
        lifetime = issued["expires_in"]
        try:
            if type(lifetime) not in (int, float) or not math.isfinite(lifetime) or lifetime <= 0:
                raise ValueError("lifetime")
            expiry = started_at + timedelta(seconds=lifetime)
        except (ValueError, OverflowError):
            raise ReadError("session_issuance_lifetime_invalid") from None
        now = self._now()
        if now < started_at:
            raise ReadError("session_clock_invalid")
        if now >= expiry - timedelta(seconds=EXPIRY_MARGIN_SECONDS):
            raise ReadError("session_issued_token_unusable")
        try:
            return SuppliedCredential(issued["access_token"], expiry)
        except ReadError:
            raise ReadError("session_issuance_response_invalid") from None
