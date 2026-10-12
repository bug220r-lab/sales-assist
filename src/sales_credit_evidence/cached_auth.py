"""Read one authorized cached snapshot without renewal or persistence.

The caller must complete authorization and scope preflight before invoking this
bridge. No path discovery, environment access, config lookup, provider creation,
token exchange, or cache writing occurs here. The existing local-auth helpers
validate fixed-drive/non-reparse paths and a stable bounded file read.

Only an authoritative numeric epoch ``expires_at`` and canonical ``user_id`` for
the intended author are accepted. Older cache shapes lacking author/application
metadata remain on hold; neither ownership nor a fresh TTL is inferred. The
source expiry is preserved; the caller must also apply the 120-second margin
at request boundaries.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any

from .transport import TARGET_AUTHOR_ID, ReadError, SuppliedCredential

MAX_SNAPSHOT_BYTES = 64 * 1024
EXPIRY_MARGIN_SECONDS = 120
_REQUIRED_FIELDS = frozenset(
    {"client_id", "client_secret", "access_token", "expires_at", "user_id"}
)
_OPTIONAL_FIELDS = frozenset({"grant_type", "token_type"})
CACHED_AUTH_ERROR_CODES = frozenset(
    {
        "cached_path_invalid",
        "cached_snapshot_missing",
        "cached_access_denied",
        "cached_snapshot_read_failed",
        "cached_snapshot_size_invalid",
        "cached_snapshot_decrypt_failed",
        "cached_plaintext_invalid",
        "cached_snapshot_invalid",
        "cached_metadata_invalid",
        "cached_expiry_unverified",
        "cached_author_unverified",
        "cached_author_mismatch",
        "cached_grant_invalid",
        "cached_application_metadata_invalid",
        "cached_token_type_invalid",
        "cached_clock_invalid",
        "stale_cached_snapshot",
        "cached_token_invalid",
    }
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def validate_connection_path(path: str) -> str:
    """Validate only path spelling, without probing a file or invoking DPAPI."""
    from doi_draft_transfer import local_auth as local_auth_module

    local_auth: Any = local_auth_module
    validated_path: str | None = None
    with suppress(Exception):
        validated_path = local_auth.connection_path(path)
    if validated_path is None:
        raise ReadError("cached_path_invalid")
    return validated_path


def load_cached_snapshot(
    path: str,
    *,
    clock: Callable[[], datetime] = _utcnow,
    encrypted_loader: Callable[[str], bytes] | None = None,
    decryptor: Callable[[bytes], bytearray] | None = None,
) -> SuppliedCredential:
    """Read and decrypt once; return only the already-issued token and deadline.

    Injectable boundaries support entirely synthetic offline testing. A decryptor
    must return a bytearray, which this function zeros on both success and failure.
    Parsed dictionaries are cleared in the same finally block; Python cannot
    guarantee erasure of temporary immutable JSON strings. No client secret is
    retained in the result, exceptions, or a provider.
    """
    validated_path = validate_connection_path(path)
    # These are existing untyped helpers, not a token-provider instance. Importing
    # them is lazy and does not load cache/config data or invoke Windows DPAPI.
    from doi_draft_transfer import local_auth as local_auth_module

    local_auth: Any = local_auth_module
    load: Callable[[str], bytes] = (
        encrypted_loader if encrypted_loader is not None else local_auth._read_encrypted
    )
    decrypt: Callable[[bytes], bytearray] = (
        decryptor if decryptor is not None else local_auth._unprotect
    )
    plain: bytearray | None = None
    parsed_records: list[dict[str, Any]] = []

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        parsed_records.append(result)
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result

    def invalid_constant(_value: str) -> None:
        raise ValueError("nonfinite_json")

    try:
        try:
            encrypted = load(validated_path)
        except FileNotFoundError:
            raise ReadError("cached_snapshot_missing") from None
        except PermissionError:
            raise ReadError("cached_access_denied") from None
        except Exception:
            raise ReadError("cached_snapshot_read_failed") from None
        if type(encrypted) is not bytes or not 0 < len(encrypted) <= MAX_SNAPSHOT_BYTES:
            raise ReadError("cached_snapshot_size_invalid")
        try:
            plain = decrypt(encrypted)
        except Exception:
            raise ReadError("cached_snapshot_decrypt_failed") from None
        if type(plain) is not bytearray or not 0 < len(plain) <= MAX_SNAPSHOT_BYTES:
            raise ReadError("cached_plaintext_invalid")
        try:
            record = json.loads(
                plain, object_pairs_hook=unique_object, parse_constant=invalid_constant
            )
        except (ValueError, UnicodeError, RecursionError):
            raise ReadError("cached_snapshot_invalid") from None
        if not isinstance(record, dict):
            raise ReadError("cached_metadata_invalid")
        if "expires_at" not in record or any(
            name in record for name in ("expires_in", "issued_at", "expiry", "expiration")
        ):
            raise ReadError("cached_expiry_unverified")
        if "user_id" not in record:
            raise ReadError("cached_author_unverified")
        if set(record) - (_REQUIRED_FIELDS | _OPTIONAL_FIELDS) or not (
            set(record) >= _REQUIRED_FIELDS
        ):
            raise ReadError("cached_metadata_invalid")
        if type(record["user_id"]) not in (int, str) or str(record["user_id"]) != str(
            TARGET_AUTHOR_ID
        ):
            raise ReadError("cached_author_mismatch")
        if any(type(record[key]) is not str for key in _OPTIONAL_FIELDS if key in record):
            raise ReadError("cached_metadata_invalid")
        if record.get("grant_type", "client_credentials") != "client_credentials":
            raise ReadError("cached_grant_invalid")
        if not all(local_auth.valid_token(record[key]) for key in ("client_id", "client_secret")):
            raise ReadError("cached_application_metadata_invalid")
        if record.get("token_type", "bearer").casefold() != "bearer":
            raise ReadError("cached_token_type_invalid")
        epoch = record["expires_at"]
        try:
            if type(epoch) not in (int, float) or not math.isfinite(epoch) or epoch <= 0:
                raise ValueError("expiry")
            expiry = datetime.fromtimestamp(epoch, UTC)
            deadline = expiry - timedelta(seconds=EXPIRY_MARGIN_SECONDS)
        except (ValueError, OverflowError, OSError):
            raise ReadError("cached_expiry_unverified") from None
        try:
            now = clock()
            if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
                raise ValueError("clock")
        except Exception:
            raise ReadError("cached_clock_invalid") from None
        if now >= deadline:
            raise ReadError("stale_cached_snapshot")
        try:
            return SuppliedCredential(record["access_token"], expiry)
        except ReadError:
            raise ReadError("cached_token_invalid") from None
    except ReadError as error:
        # Suppressing printed context alone would retain e.g. JSONDecodeError.doc
        # or an OS exception containing the private path. Detach it entirely.
        error.__context__ = None
        error.__cause__ = None
        raise
    finally:
        for parsed_record in parsed_records:
            parsed_record.clear()
        if type(plain) is bytearray:
            plain[:] = b"\0" * len(plain)
