"""Offline owner tests; synthetic bytearrays and fake issuance only."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qs

import pytest

from doi_draft_transfer import local_auth
from sales_credit_evidence.session_snapshot import (
    SESSION_AUTH_ERROR_CODES,
    SessionSnapshotOwner,
)
from sales_credit_evidence.transport import TARGET_AUTHOR_ID, ReadError

NOW = datetime(2026, 10, 12, 18, tzinfo=UTC)
PATH = r"C:\synthetic\snapshot.dpapi"


def record(**changes: Any) -> dict[str, Any]:
    return {
        "client_id": "test-id",
        "client_secret": "test-secret",
        "access_token": "test-token",
        "expires_at": (NOW + timedelta(minutes=10)).timestamp(),
        "user_id": TARGET_AUTHOR_ID,
        **changes,
    }


def response(**changes: Any) -> dict[str, Any]:
    return {"access_token": "issued-token", "token_type": "bearer", "expires_in": 3600, **changes}


class FakeBoundaries:
    def __init__(
        self,
        source: dict[str, Any] | None = None,
        *,
        payload: bytes | None = None,
        result: Any = None,
    ) -> None:
        self.plain = bytearray(
            payload if payload is not None else json.dumps(source or record()).encode()
        )
        self.result = response() if result is None else result
        self.reads: list[str] = []
        self.decryptions: list[bytes] = []
        self.issues: list[dict[str, str]] = []
        self.request_references: list[dict[str, str]] = []

    def load(self, path: str) -> bytes:
        self.reads.append(path)
        return b"synthetic-encrypted"

    def decrypt(self, raw: bytes) -> bytearray:
        self.decryptions.append(raw)
        return self.plain

    def issue(self, fields: dict[str, str]) -> dict[str, Any]:
        self.issues.append(dict(fields))
        self.request_references.append(fields)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def owner(self, **kwargs: Any) -> SessionSnapshotOwner:
        return SessionSnapshotOwner(
            PATH,
            clock=lambda: NOW,
            encrypted_loader=self.load,
            decryptor=self.decrypt,
            issuer=self.issue,
            **kwargs,
        )

    def assert_cleared(self) -> None:
        assert self.plain == bytearray(len(self.plain))
        assert all(fields == {} for fields in self.request_references)


def test_default_off_and_explicit_issuance_gate_do_not_read_credentials() -> None:
    fake = FakeBoundaries(record(expires_at=NOW.timestamp() - 1))
    owner = fake.owner()
    for kwargs in ({}, {"allow_issuance": True}):
        with pytest.raises(ReadError, match="session_live_disabled"):
            owner.load(**kwargs)
    assert not fake.reads and not fake.decryptions and not fake.issues
    assert not owner.issuance_attempted
    with pytest.raises(ReadError, match="session_cached_expired"):
        owner.load(enable_live=True)
    assert len(fake.reads) == 1
    assert not fake.issues
    fake.assert_cleared()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"enable_live": "yes"},
        {"enable_live": 1},
        {"enable_live": True, "allow_issuance": "yes"},
    ],
)
def test_flags_must_be_literal_booleans(kwargs: dict[str, Any]) -> None:
    fake = FakeBoundaries()
    with pytest.raises(ReadError, match="session_gate_invalid"):
        fake.owner().load(**kwargs)
    assert fake.reads == []


@pytest.mark.parametrize("allow_issuance", [False, True])
def test_usable_cached_snapshot_preserves_expiry_without_issuance(allow_issuance: bool) -> None:
    source = record()
    fake = FakeBoundaries(source)
    owner = fake.owner()
    snapshot = owner.load(enable_live=True, allow_issuance=allow_issuance)
    assert snapshot.token == "test-token"
    assert snapshot.expires_at == datetime.fromtimestamp(source["expires_at"], UTC)
    assert not owner.issuance_attempted and not fake.issues
    with pytest.raises(ReadError, match="session_already_loaded"):
        owner.load(enable_live=True, allow_issuance=True)
    assert len(fake.reads) == len(fake.decryptions) == 1
    fake.assert_cleared()


@pytest.mark.parametrize("remaining", [0.001, 1, 119, 120])
def test_near_expiry_never_issues_even_with_both_gates(remaining: float) -> None:
    fake = FakeBoundaries(record(expires_at=NOW.timestamp() + remaining))
    owner = fake.owner()
    with pytest.raises(ReadError, match="session_cached_near_expiry"):
        owner.load(enable_live=True, allow_issuance=True)
    assert not owner.issuance_attempted and not fake.issues
    fake.assert_cleared()


@pytest.mark.parametrize("elapsed", [0, 1, 1000])
def test_actual_expiry_allows_exactly_one_issuance_and_preserves_response_lifetime(
    elapsed: int,
) -> None:
    fake = FakeBoundaries(record(expires_at=NOW.timestamp() - elapsed))
    times = iter([NOW, NOW + timedelta(seconds=5)])
    owner = SessionSnapshotOwner(
        PATH,
        clock=lambda: next(times),
        encrypted_loader=fake.load,
        decryptor=fake.decrypt,
        issuer=fake.issue,
    )
    snapshot = owner.load(enable_live=True, allow_issuance=True)
    assert snapshot.token == "issued-token"
    assert snapshot.expires_at == NOW + timedelta(seconds=3600)
    assert owner.issuance_attempted
    assert fake.issues == [
        {
            "grant_type": "client_credentials",
            "client_id": "test-id",
            "client_secret": "test-secret",
        }
    ]
    assert fake.result == {}
    with pytest.raises(ReadError, match="session_already_loaded"):
        owner.load(enable_live=True, allow_issuance=True)
    assert len(fake.reads) == len(fake.issues) == 1
    fake.assert_cleared()


@pytest.mark.parametrize(
    "error",
    [
        OSError("private-path test-secret"),
        ReadError("private-path test-secret"),
        ReadError("session_issuer_http_error", status=401),
        ReadError("session_issuer_http_error", status=403),
        ReadError("session_issuer_http_error", status=500),
    ],
)
def test_failed_or_rejected_issuance_never_retries(error: Exception) -> None:
    fake = FakeBoundaries(record(expires_at=NOW.timestamp() - 1), result=error)
    owner = fake.owner()
    with pytest.raises(ReadError) as caught:
        owner.load(enable_live=True, allow_issuance=True)
    assert caught.value.code in SESSION_AUTH_ERROR_CODES
    assert "test-secret" not in repr(caught.value)
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    with pytest.raises(ReadError, match="session_already_loaded"):
        owner.load(enable_live=True, allow_issuance=True)
    assert owner.issuance_attempted
    assert len(fake.issues) == len(fake.reads) == 1
    fake.assert_cleared()


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"extra": "field"}, "session_metadata_invalid"),
        ({"user_id": 1}, "session_author_mismatch"),
        ({"user_id": True}, "session_author_mismatch"),
        ({"user_id": "0897275"}, "session_author_mismatch"),
        ({"expires_at": "3600"}, "session_expiry_unverified"),
        ({"expires_in": 3600}, "session_expiry_unverified"),
        ({"expires_at": True}, "session_expiry_unverified"),
        ({"expires_at": 0}, "session_expiry_unverified"),
        ({"grant_type": "refresh_token"}, "session_grant_invalid"),
        ({"token_type": "basic"}, "session_token_type_invalid"),
        ({"token_type": None}, "session_metadata_invalid"),
        ({"client_secret": ""}, "session_application_metadata_invalid"),
        ({"client_id": None}, "session_application_metadata_invalid"),
        ({"access_token": "bad\nvalue"}, "session_token_invalid"),
    ],
)
def test_authoritative_schema_blocks_before_any_issuance(
    changes: dict[str, Any], code: str
) -> None:
    fake = (
        FakeBoundaries(record(expires_at=NOW.timestamp() - 1, **changes))
        if "expires_at" not in changes
        else FakeBoundaries(record(**changes))
    )
    owner = fake.owner()
    with pytest.raises(ReadError, match=code):
        owner.load(enable_live=True, allow_issuance=True)
    assert not fake.issues and not owner.issuance_attempted
    fake.assert_cleared()


@pytest.mark.parametrize(
    "field", ["client_id", "client_secret", "user_id", "expires_at", "access_token"]
)
def test_missing_required_metadata_cannot_issue(field: str) -> None:
    source = record(expires_at=NOW.timestamp() - 1)
    del source[field]
    fake = FakeBoundaries(source)
    with pytest.raises(ReadError):
        fake.owner().load(enable_live=True, allow_issuance=True)
    assert not fake.issues
    fake.assert_cleared()


@pytest.mark.parametrize(
    "payload",
    [
        b'{"access_token":"one","access_token":"two"}',
        b'{"expires_at":NaN}',
        b'{"expires_at":Infinity}',
        b"not-json",
        b"[]",
    ],
)
def test_duplicate_and_nonfinite_source_json_block_and_clear(payload: bytes) -> None:
    fake = FakeBoundaries(payload=payload)
    with pytest.raises(ReadError, match="session_snapshot_invalid") as caught:
        fake.owner().load(enable_live=True, allow_issuance=True)
    assert caught.value.__context__ is None
    assert not fake.issues
    fake.assert_cleared()


@pytest.mark.parametrize(
    "result,code",
    [
        ({}, "session_issuance_response_invalid"),
        (response(refresh_token="not-used"), "session_issuance_response_invalid"),
        (response(token_type="basic"), "session_issuance_response_invalid"),
        (response(access_token=""), "session_issuance_response_invalid"),
        (response(expires_in=True), "session_issuance_lifetime_invalid"),
        (response(expires_in="3600"), "session_issuance_lifetime_invalid"),
        (response(expires_in=float("inf")), "session_issuance_lifetime_invalid"),
        (response(expires_in=-1), "session_issuance_lifetime_invalid"),
        (response(expires_in=120), "session_issued_token_unusable"),
    ],
)
def test_issued_response_requires_exact_schema_and_authoritative_lifetime(
    result: Any, code: str
) -> None:
    fake = FakeBoundaries(record(expires_at=NOW.timestamp() - 1), result=dict(result))
    owner = fake.owner()
    with pytest.raises(ReadError, match=code):
        owner.load(enable_live=True, allow_issuance=True)
    assert owner.issuance_attempted and len(fake.issues) == 1
    assert fake.result == {}
    fake.assert_cleared()


@pytest.mark.parametrize(
    "elapsed,code", [(3500, "session_issued_token_unusable"), (-1, "session_clock_invalid")]
)
def test_network_elapsed_time_cannot_extend_token_lifetime(elapsed: int, code: str) -> None:
    fake = FakeBoundaries(record(expires_at=NOW.timestamp() - 1))
    times = iter([NOW, NOW + timedelta(seconds=elapsed)])
    owner = SessionSnapshotOwner(
        PATH,
        clock=lambda: next(times),
        encrypted_loader=fake.load,
        decryptor=fake.decrypt,
        issuer=fake.issue,
    )
    with pytest.raises(ReadError, match=code):
        owner.load(enable_live=True, allow_issuance=True)
    assert len(fake.issues) == 1
    fake.assert_cleared()


def test_close_is_idempotent_no_io_and_owner_repr_is_redacted() -> None:
    fake = FakeBoundaries()
    owner = fake.owner()
    assert repr(owner) == "<SessionSnapshotOwner redacted>"
    with pytest.raises(AttributeError):
        owner.issuance_attempted = True  # type: ignore[misc]
    owner.close()
    owner.close()
    with pytest.raises(ReadError, match="session_owner_closed"):
        owner.load(enable_live=True, allow_issuance=True)
    assert not fake.reads and not fake.issues


def test_invalid_path_consumes_enabled_attempt_without_io() -> None:
    fake = FakeBoundaries()
    owner = SessionSnapshotOwner(
        "relative.dpapi",
        encrypted_loader=fake.load,
        decryptor=fake.decrypt,
        issuer=fake.issue,
    )
    with pytest.raises(ReadError, match="session_path_invalid"):
        owner.load(enable_live=True, allow_issuance=True)
    with pytest.raises(ReadError, match="session_already_loaded"):
        owner.load(enable_live=True, allow_issuance=True)
    assert not fake.reads and not fake.issues


class FakeResponse:
    def __init__(self, status: int = 200, payload: bytes | None = None) -> None:
        self.status = status
        self.payload = json.dumps(response()).encode() if payload is None else payload
        self.reads: list[int] = []

    def read(self, bound: int) -> bytes:
        self.reads.append(bound)
        return self.payload


class FakeConnection:
    def __init__(self, result: FakeResponse) -> None:
        self.result = result
        self.requests: list[tuple[str, str]] = []
        self.body: bytearray | None = None
        self.closed = False

    def request(self, method: str, path: str, *, body: bytearray, headers: dict[str, str]) -> None:
        self.requests.append((method, path))
        self.body = body
        assert parse_qs(body.decode()) == {
            "grant_type": ["client_credentials"],
            "client_id": ["test-id"],
            "client_secret": ["test-secret"],
        }
        assert headers["Content-Type"] == "application/x-www-form-urlencoded"

    def getresponse(self) -> FakeResponse:
        return self.result

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize("status", [200, 301, 302, 307, 401, 403, 429, 500])
def test_default_issuer_is_fixed_post_without_redirects_or_retries(status: int) -> None:
    fake = FakeBoundaries(record(expires_at=NOW.timestamp() - 1))
    result = FakeResponse(status)
    connection = FakeConnection(result)
    with (
        patch("http.client.HTTPSConnection", return_value=connection) as factory,
        patch("ssl.create_default_context", return_value=object()),
    ):
        owner = SessionSnapshotOwner(
            PATH,
            clock=lambda: NOW,
            encrypted_loader=fake.load,
            decryptor=fake.decrypt,
        )
        if status == 200:
            assert owner.load(enable_live=True, allow_issuance=True).token == "issued-token"
        else:
            with pytest.raises(ReadError) as caught:
                owner.load(enable_live=True, allow_issuance=True)
            assert caught.value.status == status
        with pytest.raises(ReadError, match="session_already_loaded"):
            owner.load(enable_live=True, allow_issuance=True)
    assert factory.call_count == 1 and factory.call_args.args == ("api.helpscout.net",)
    assert factory.call_args.kwargs["timeout"] == 15.0
    assert connection.requests == [("POST", "/v2/oauth2/token")]
    assert connection.closed and owner.issuance_attempted
    assert connection.body is not None and not any(connection.body)
    assert result.reads == ([65537] if status == 200 else [])
    fake.assert_cleared()


@pytest.mark.parametrize(
    "payload",
    [
        b"x" * 65537,
        b'{"access_token":"one","access_token":"two"}',
        b'{"expires_in":NaN}',
        b"[]",
        b"not-json",
    ],
    ids=["oversized", "duplicate", "nonfinite", "list", "malformed"],
)
def test_default_issuer_bounds_and_json_fail_closed(payload: bytes) -> None:
    fake = FakeBoundaries(record(expires_at=NOW.timestamp() - 1))
    connection = FakeConnection(FakeResponse(payload=payload))
    with (
        patch("http.client.HTTPSConnection", return_value=connection),
        patch("ssl.create_default_context", return_value=object()),
    ):
        owner = SessionSnapshotOwner(
            PATH,
            clock=lambda: NOW,
            encrypted_loader=fake.load,
            decryptor=fake.decrypt,
        )
        with pytest.raises(ReadError) as caught:
            owner.load(enable_live=True, allow_issuance=True)
    assert caught.value.code in SESSION_AUTH_ERROR_CODES
    assert caught.value.__context__ is None
    assert len(connection.requests) == 1 and connection.closed
    assert connection.body is not None and not any(connection.body)
    fake.assert_cleared()


def test_default_read_helpers_are_lazy_without_creating_a_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeBoundaries()
    monkeypatch.setattr(local_auth, "_read_encrypted", fake.load)
    monkeypatch.setattr(local_auth, "_unprotect", fake.decrypt)
    with (
        patch("builtins.open", side_effect=AssertionError("filesystem forbidden")),
        patch("http.client.HTTPSConnection", side_effect=AssertionError("network forbidden")),
        patch.object(local_auth, "_dll", side_effect=AssertionError("DPAPI forbidden")),
        patch.object(
            local_auth, "CachedDPAPIToken", side_effect=AssertionError("provider forbidden")
        ),
    ):
        owner = SessionSnapshotOwner(PATH, clock=lambda: NOW)
        assert fake.reads == []
        assert owner.load(enable_live=True).token == "test-token"
    assert fake.reads == [PATH]
    fake.assert_cleared()
