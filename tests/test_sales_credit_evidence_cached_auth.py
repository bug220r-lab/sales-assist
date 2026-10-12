"""Synthetic-only snapshot bridge tests: no file, DPAPI, provider, or API access."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest

from doi_draft_transfer import local_auth
from sales_credit_evidence import cached_auth
from sales_credit_evidence.cached_auth import MAX_SNAPSHOT_BYTES, load_cached_snapshot
from sales_credit_evidence.transport import TARGET_AUTHOR_ID, ReadError

NOW = datetime(2026, 10, 12, 18, tzinfo=UTC)
PATH = r"C:\synthetic\snapshot.dpapi"
TOKEN = "test-token"


def valid_record(**changes: Any) -> dict[str, Any]:
    return {
        "client_id": "test-id",
        "client_secret": "test-secret",
        "access_token": TOKEN,
        "expires_at": (NOW + timedelta(minutes=10)).timestamp(),
        "user_id": TARGET_AUTHOR_ID,
        **changes,
    }


class FakeSnapshot:
    def __init__(self, record: Any = None, *, payload: bytes | None = None) -> None:
        self.encrypted = b"synthetic-encrypted"
        self.plain = bytearray(
            payload if payload is not None else json.dumps(record or valid_record()).encode()
        )
        self.reads: list[str] = []
        self.decryptions: list[bytes] = []

    def load(self, path: str) -> bytes:
        self.reads.append(path)
        return self.encrypted

    def decrypt(self, encrypted: bytes) -> bytearray:
        self.decryptions.append(encrypted)
        return self.plain

    def read(self, **kwargs: Any) -> Any:
        return load_cached_snapshot(
            PATH, clock=lambda: NOW, encrypted_loader=self.load, decryptor=self.decrypt, **kwargs
        )

    def assert_cleared(self) -> None:
        assert self.plain == bytearray(len(self.plain))


def test_snapshot_reads_and_decrypts_once_preserving_authoritative_expiry() -> None:
    source = valid_record()
    fake = FakeSnapshot(source)
    credential = fake.read()
    assert credential.token == TOKEN
    assert credential.expires_at == datetime.fromtimestamp(source["expires_at"], UTC)
    assert fake.reads == [PATH]
    assert fake.decryptions == [fake.encrypted]
    assert TOKEN not in repr(credential)
    assert "test-secret" not in repr(credential)
    assert not hasattr(credential, "client_secret")
    assert not hasattr(credential, "client_id")
    fake.assert_cleared()


def test_path_preflight_is_lexical_without_credential_access() -> None:
    with (
        patch.object(local_auth, "_read_encrypted", side_effect=AssertionError("read forbidden")),
        patch.object(local_auth, "_unprotect", side_effect=AssertionError("DPAPI forbidden")),
        patch("builtins.open", side_effect=AssertionError("filesystem forbidden")),
    ):
        assert cached_auth.validate_connection_path("C:/synthetic/snapshot.dpapi") == PATH


@pytest.mark.parametrize("user_id", [TARGET_AUTHOR_ID, str(TARGET_AUTHOR_ID)])
def test_author_supports_only_existing_canonical_id_forms(user_id: int | str) -> None:
    fake = FakeSnapshot(valid_record(user_id=user_id))
    assert fake.read().token == TOKEN
    fake.assert_cleared()


@pytest.mark.parametrize(
    "path",
    [
        "",
        "snapshot.dpapi",
        r"\\server\share\snapshot.dpapi",
        "C:relative.dpapi",
        r"C:\synthetic\snapshot.json",
        r"C:\synthetic\..\snapshot.dpapi",
        r"C:\synthetic\snapshot.dpapi:stream",
        r"C:\synthetic\CON.dpapi",
        "C:\\synthetic\\bad\n.dpapi",
        r"C:\synthetic.\snapshot.dpapi",
        None,
    ],
)
def test_invalid_path_fails_before_loader_or_decryptor(path: Any) -> None:
    fake = FakeSnapshot()
    with pytest.raises(ReadError, match="cached_path_invalid"):
        load_cached_snapshot(
            path, clock=lambda: NOW, encrypted_loader=fake.load, decryptor=fake.decrypt
        )
    assert fake.reads == []
    assert fake.decryptions == []


@pytest.mark.parametrize(
    "encrypted",
    [b"", b"x" * (MAX_SNAPSHOT_BYTES + 1), "not-bytes"],
    ids=["empty", "oversized", "wrong_type"],
)
def test_encrypted_bounds_fail_before_decryption(encrypted: Any) -> None:
    fake = FakeSnapshot()
    fake.encrypted = encrypted
    with pytest.raises(ReadError, match="cached_snapshot_size_invalid"):
        fake.read()
    assert len(fake.reads) == 1
    assert fake.decryptions == []


@pytest.mark.parametrize(
    "payload", [b"", b"x" * (MAX_SNAPSHOT_BYTES + 1)], ids=["empty", "oversized"]
)
def test_plaintext_bounds_are_rejected_and_mutable_buffer_is_cleared(payload: bytes) -> None:
    fake = FakeSnapshot(payload=payload)
    with pytest.raises(ReadError, match="cached_plaintext_invalid"):
        fake.read()
    fake.assert_cleared()


def test_immutable_decryptor_output_is_rejected() -> None:
    with pytest.raises(ReadError, match="cached_plaintext_invalid"):
        load_cached_snapshot(
            PATH,
            clock=lambda: NOW,
            encrypted_loader=lambda _: b"fake",
            decryptor=lambda _: b"immutable",  # type: ignore[arg-type,return-value]
        )


@pytest.mark.parametrize(
    "payload",
    [
        b'{"access_token":"first","access_token":"second"}',
        b'{"expires_at":1,"expires_at":2}',
        b'{"nested":{"same":1,"same":2}}',
        b'{"expires_at":NaN}',
        b'{"expires_at":Infinity}',
        b'{"expires_at":-Infinity}',
        b"not-json",
        b"\xff",
    ],
)
def test_invalid_duplicate_and_nonfinite_json_fails_and_clears(payload: bytes) -> None:
    fake = FakeSnapshot(payload=payload)
    with pytest.raises(ReadError, match="cached_snapshot_invalid") as caught:
        fake.read()
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None
    fake.assert_cleared()


@pytest.mark.parametrize("payload", [b"[]", b"null", b'"not-an-object"'])
def test_root_must_be_a_metadata_object(payload: bytes) -> None:
    fake = FakeSnapshot(payload=payload)
    with pytest.raises(ReadError, match="cached_metadata_invalid"):
        fake.read()
    fake.assert_cleared()


@pytest.mark.parametrize(
    "missing,code",
    [
        ("user_id", "cached_author_unverified"),
        ("expires_at", "cached_expiry_unverified"),
        ("access_token", "cached_metadata_invalid"),
        ("client_id", "cached_metadata_invalid"),
        ("client_secret", "cached_metadata_invalid"),
    ],
)
def test_missing_authoritative_fields_hold_without_inference(missing: str, code: str) -> None:
    source = valid_record()
    del source[missing]
    fake = FakeSnapshot(source)
    with pytest.raises(ReadError, match=code):
        fake.read()
    fake.assert_cleared()


@pytest.mark.parametrize("field", ["expires_in", "issued_at", "expiry", "expiration"])
def test_ambiguous_or_ttl_expiry_is_never_derived(field: str) -> None:
    fake = FakeSnapshot(valid_record(**{field: 3600}))
    with pytest.raises(ReadError, match="cached_expiry_unverified"):
        fake.read()
    fake.assert_cleared()


@pytest.mark.parametrize("epoch", [True, "1800000000", None, 0, -1, 1e300, 10**400])
def test_epoch_requires_finite_positive_numeric_seconds(epoch: Any) -> None:
    fake = FakeSnapshot(valid_record(expires_at=epoch))
    with pytest.raises(ReadError, match="cached_expiry_unverified"):
        fake.read()
    fake.assert_cleared()


@pytest.mark.parametrize("remaining", [-1, 0, 119, 120])
def test_expired_and_within_margin_snapshots_hold(remaining: int) -> None:
    fake = FakeSnapshot(valid_record(expires_at=NOW.timestamp() + remaining))
    with pytest.raises(ReadError, match="stale_cached_snapshot"):
        fake.read()
    fake.assert_cleared()


def test_just_outside_margin_preserves_source_expiry() -> None:
    epoch = NOW.timestamp() + 120.001
    fake = FakeSnapshot(valid_record(expires_at=epoch))
    assert fake.read().expires_at == datetime.fromtimestamp(epoch, UTC)
    fake.assert_cleared()


@pytest.mark.parametrize("user_id", [True, False, 1, "0897275", "897275 ", None, 897275.0])
def test_wrong_or_ambiguous_author_holds(user_id: Any) -> None:
    fake = FakeSnapshot(valid_record(user_id=user_id))
    with pytest.raises(ReadError, match="cached_author_mismatch"):
        fake.read()
    fake.assert_cleared()


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"unexpected": "value"}, "cached_metadata_invalid"),
        ({"grant_type": "refresh_token"}, "cached_grant_invalid"),
        ({"grant_type": "CLIENT_CREDENTIALS"}, "cached_grant_invalid"),
        ({"grant_type": None}, "cached_metadata_invalid"),
        ({"token_type": "basic"}, "cached_token_type_invalid"),
        ({"token_type": "bearer "}, "cached_token_type_invalid"),
        ({"token_type": 1}, "cached_metadata_invalid"),
        ({"client_id": ""}, "cached_application_metadata_invalid"),
        ({"client_secret": "bad\nvalue"}, "cached_application_metadata_invalid"),
        ({"client_secret": {"nested": "secret"}}, "cached_application_metadata_invalid"),
        ({"access_token": ""}, "cached_token_invalid"),
        ({"access_token": "bad\r\nvalue"}, "cached_token_invalid"),
        ({"access_token": "x" * 8193}, "cached_token_invalid"),
    ],
)
def test_optional_types_grant_and_token_shape_fail_closed(
    changes: dict[str, Any],
    code: str,
) -> None:
    fake = FakeSnapshot(valid_record(**changes))
    with pytest.raises(ReadError, match=code):
        fake.read()
    fake.assert_cleared()


def test_supported_optional_types_are_accepted_without_renewal() -> None:
    fake = FakeSnapshot(valid_record(grant_type="client_credentials", token_type="Bearer"))
    assert fake.read().token == TOKEN
    fake.assert_cleared()


@pytest.mark.parametrize("clock_value", [NOW.replace(tzinfo=None), "now", None])
def test_invalid_clock_fails_safely_and_clears(clock_value: Any) -> None:
    fake = FakeSnapshot()
    with pytest.raises(ReadError, match="cached_clock_invalid"):
        load_cached_snapshot(
            PATH,
            clock=lambda: clock_value,
            encrypted_loader=fake.load,
            decryptor=fake.decrypt,
        )
    fake.assert_cleared()


@pytest.mark.parametrize(
    "failure,code",
    [
        (FileNotFoundError, "cached_snapshot_missing"),
        (PermissionError, "cached_access_denied"),
        (OSError, "cached_snapshot_read_failed"),
    ],
)
def test_loader_failures_are_safe_and_never_retried(failure: type[Exception], code: str) -> None:
    calls: list[str] = []

    def fail(path: str) -> bytes:
        calls.append(path)
        raise failure(f"{PATH} {TOKEN} test-secret")

    with pytest.raises(ReadError) as caught:
        load_cached_snapshot(PATH, encrypted_loader=fail, decryptor=lambda _: bytearray())
    assert caught.value.code == code
    assert len(calls) == 1
    assert caught.value.__suppress_context__
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    for canary in (PATH, TOKEN, "test-secret"):
        assert canary not in str(caught.value)
        assert canary not in repr(caught.value)


def test_decryption_failure_does_not_expose_provider_exception() -> None:
    def fail(_raw: bytes) -> bytearray:
        raise RuntimeError(f"{PATH} {TOKEN} test-secret")

    with pytest.raises(ReadError, match="cached_snapshot_decrypt_failed") as caught:
        load_cached_snapshot(PATH, encrypted_loader=lambda _: b"fake", decryptor=fail)
    assert caught.value.__suppress_context__
    assert caught.value.__context__ is None
    assert TOKEN not in repr(caught.value)


@pytest.mark.parametrize(
    "source", [valid_record(), valid_record(client_secret={"nested": "secret"})]
)
def test_all_parsed_records_are_cleared_on_success_and_failure(
    source: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records: list[dict[str, Any]] = []
    original_loads = json.loads

    def capture(*args: Any, **kwargs: Any) -> Any:
        original_hook = kwargs["object_pairs_hook"]

        def hook(pairs: Any) -> Any:
            record = original_hook(pairs)
            records.append(record)
            return record

        kwargs["object_pairs_hook"] = hook
        return original_loads(*args, **kwargs)

    monkeypatch.setattr(cached_auth.json, "loads", capture)
    fake = FakeSnapshot(source)
    try:
        fake.read()
    except ReadError:
        assert isinstance(source["client_secret"], dict)
    assert records
    assert all(record == {} for record in records)
    fake.assert_cleared()


def test_default_boundaries_reuse_existing_helpers_without_file_dpapi_or_network(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = FakeSnapshot()
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
        credential = load_cached_snapshot(PATH, clock=lambda: NOW)
    assert credential.token == TOKEN
    assert fake.reads == [PATH]
    assert len(fake.decryptions) == 1
    assert capsys.readouterr() == ("", "")
    fake.assert_cleared()
