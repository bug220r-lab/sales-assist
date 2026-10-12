"""Offline transport/security checks; every identity and credential is synthetic."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from urllib.parse import urlencode

import pytest

from sales_credit_evidence.transport import (
    API_ORIGIN,
    MAILBOX_ID,
    MAX_BODY_BYTES,
    HttpResponse,
    ReadClient,
    ReadError,
    SuppliedCredential,
    normalize_email,
)

NOW = datetime(2026, 10, 12, 18, tzinfo=UTC)
EMAIL = "review+synthetic@example.test"
TOKEN = "test-token"


def customer_url(**extra: str) -> str:
    query = {"mailbox": str(MAILBOX_ID), "query": f'(email:"{EMAIL}")', **extra}
    return f"{API_ORIGIN}/v2/customers?{urlencode(query)}"


def conversation_url(customer_id: int = 10, **extra: str) -> str:
    query = {
        "mailbox": str(MAILBOX_ID),
        "status": "all",
        "query": f"(customerIds:{customer_id})",
        **extra,
    }
    return f"{API_ORIGIN}/v2/conversations?{urlencode(query)}"


def response(status: int = 200, headers: dict[str, str] | None = None) -> HttpResponse:
    return HttpResponse(status, headers or {}, b'{"ok": true}')


class FakeTransport:
    def __init__(self, *results: HttpResponse | Exception) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, str, dict[str, str]]] = []

    def __call__(self, method: str, url: str, headers: dict[str, str]) -> HttpResponse:
        self.calls.append((method, url, headers))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_normalization_preserves_plus_and_is_case_insensitive() -> None:
    assert normalize_email("  Review+Synthetic@EXAMPLE.TEST  ") == EMAIL


@pytest.mark.parametrize(
    "email",
    [
        "",
        "a",
        "a@",
        "@example.test",
        "a@@example.test",
        "a@localhost",
        "* @example.test",
        "*@example.test",
        "?@example.test",
        "a b@example.test",
        'a" OR email:"b@example.test',
        "a\n@example.test",
        "a@example..test",
        "a@-bad.example.test",
        "a@bad-.example.test",
        ".a@example.test",
        "a.@example.test",
        "a..b@example.test",
        "a@exämple.test",
        "\u212a@example.test",
        "a" * 65 + "@example.test",
    ],
)
def test_malformed_email_never_reaches_transport(email: str) -> None:
    fake = FakeTransport()
    with pytest.raises(ReadError, match="invalid_email"):
        ReadClient(email, transport=fake)
    assert fake.calls == []


def test_no_network_or_auth_by_default() -> None:
    with patch("http.client.HTTPSConnection", side_effect=AssertionError("network forbidden")):
        client = ReadClient(EMAIL)
        with pytest.raises(ReadError, match="live_access_disabled"):
            client.get(customer_url())


def test_explicit_live_activation_requires_supplied_credential() -> None:
    with patch("http.client.HTTPSConnection", side_effect=AssertionError("network forbidden")):
        client = ReadClient(EMAIL, enable_live=True)
        with pytest.raises(ReadError, match="credential_required"):
            client.get(customer_url())


def test_email_scope_is_read_only_and_grants_stay_with_the_original_client() -> None:
    fake = FakeTransport()
    original = ReadClient(EMAIL, transport=fake)
    original.allow_customer(10)
    original.allow_conversation(20)
    with pytest.raises(AttributeError):
        original.email = "other@example.test"  # type: ignore[misc]
    assert original.email == EMAIL
    other = ReadClient("other@example.test", transport=fake)
    for url in (
        customer_url(),
        conversation_url(),
        f"{API_ORIGIN}/v2/customers/10/emails",
        f"{API_ORIGIN}/v2/conversations/20",
        f"{API_ORIGIN}/v2/conversations/20/threads",
    ):
        with pytest.raises(ReadError, match="unsafe_url"):
            other.get(url)
    assert fake.calls == []


def test_supported_paths_are_all_get_only_and_require_discovered_ids() -> None:
    fake = FakeTransport(*(response() for _ in range(5)))
    client = ReadClient(EMAIL, transport=fake)
    assert client.get(customer_url()) == {"ok": True}
    with pytest.raises(ReadError, match="unsafe_url"):
        client.get(conversation_url())
    client.allow_customer(10)
    client.get(f"{API_ORIGIN}/v2/customers/10/emails")
    client.get(conversation_url(page="2"))
    with pytest.raises(ReadError, match="unsafe_url"):
        client.get(f"{API_ORIGIN}/v2/conversations/20")
    client.allow_conversation(20)
    client.get(f"{API_ORIGIN}/v2/conversations/20")
    client.get(f"{API_ORIGIN}/v2/conversations/20/threads?page=3")
    assert len(fake.calls) == 5
    assert {call[0] for call in fake.calls} == {"GET"}
    assert all("Authorization" not in call[2] for call in fake.calls)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.helpscout.net/v2/customers",
        "https://api.helpscout.net.evil.test/v2/customers",
        "https://api.helpscout.net@example.test/v2/customers",
        "https://user@api.helpscout.net/v2/customers",
        "https://api.helpscout.net:443/v2/customers",
        "https://API.helpscout.net/v2/customers",
        "https://api.helpscout.net\\evil.test/v2/customers",
        "/v2/customers",
        "//api.helpscout.net/v2/customers",
        "https://api.helpscout.net/v2/%63ustomers",
        "https://api.helpscout.net/v2/../v2/customers",
        "https://api.helpscout.net/v2//customers",
        "https://api.helpscout.net/v2/customers#",
        "https://api.helpscout.net/v2/customers#fragment",
        "https://api.helpscout.net/v2/oauth2/token",
        "https://api.helpscout.net/v2/users",
        "https://api.helpscout.net/v2/conversations/20/drafts",
        "https://api.helpscout.net/v2/conversations/20?embed=threads",
        "https://api.helpscout.net/v2/conversations/20?page=1",
        "https://api.helpscout.net/v2/customers/11/emails",
        "https://api.helpscout.net/v2/conversations/21/threads",
        "https://api.helpscout.net/v2/customers/10/emails?mailbox=166170",
        "https://api.helpscout.net/v2/customers/10/emails?page=1",
        "https://api.helpscout.net/v2/customers/10/emails?page=2",
        "https://api.helpscout.net/v2/customers/10/emails?",
        customer_url() + "&mailbox=166170",
        customer_url() + "&extra=value",
        customer_url() + "&invalid=%",
        customer_url() + "&broken",
        customer_url().replace("166170", "999999"),
        customer_url().replace("review%2Bsynthetic", "different"),
        customer_url(page="0"),
        customer_url(page="-1"),
        customer_url(page="01"),
        customer_url(page="10001"),
        customer_url(page="1.0"),
        customer_url(page=""),
        conversation_url(11),
        conversation_url(status="active"),
    ],
)
def test_scope_and_malformed_url_rejection_precedes_any_http(url: str) -> None:
    fake = FakeTransport()
    client = ReadClient(EMAIL, transport=fake)
    client.allow_customer(10)
    client.allow_conversation(20)
    with pytest.raises(ReadError, match="unsafe_url"):
        client.get(url)
    assert fake.calls == []


@pytest.mark.parametrize("native_id", [0, -1, True, "10", 2**64])
def test_native_id_grants_are_strict(native_id: object) -> None:
    client = ReadClient(EMAIL, transport=FakeTransport())
    for grant in (client.allow_customer, client.allow_conversation):
        with pytest.raises(ReadError, match="invalid_native_id"):
            grant(native_id)  # type: ignore[arg-type]


@pytest.mark.parametrize("status,code", [(401, "unauthorized"), (403, "forbidden")])
def test_unauthorized_is_terminal_without_retry_or_renewal(status: int, code: str) -> None:
    fake = FakeTransport(response(status), response())
    waits: list[float] = []
    client = ReadClient(
        EMAIL,
        transport=fake,
        sleeper=waits.append,
        credential=SuppliedCredential(TOKEN, NOW + timedelta(minutes=5)),
        clock=lambda: NOW,
    )
    with pytest.raises(ReadError) as caught:
        client.get(customer_url())
    assert (caught.value.code, caught.value.status, caught.value.attempts) == (code, status, 1)
    assert len(fake.calls) == 1
    assert waits == []
    assert fake.calls[0][2]["Authorization"] == f"Bearer {TOKEN}"
    assert not hasattr(client, "refresh")


def test_stale_credentials_do_not_send_any_request() -> None:
    fake = FakeTransport()
    credential = SuppliedCredential(TOKEN, NOW)
    client = ReadClient(EMAIL, transport=fake, credential=credential, clock=lambda: NOW)
    with pytest.raises(ReadError, match="stale_credential") as caught:
        client.get(customer_url())
    assert caught.value.attempts == 0
    assert fake.calls == []
    assert TOKEN not in repr(credential)
    assert TOKEN not in str(caught.value)


def test_expiration_rechecked_before_retry() -> None:
    fake = FakeTransport(response(500), response())
    times = iter([NOW, NOW + timedelta(seconds=2)])
    client = ReadClient(
        EMAIL,
        transport=fake,
        sleeper=lambda _: None,
        clock=lambda: next(times),
        credential=SuppliedCredential(TOKEN, NOW + timedelta(seconds=1)),
    )
    with pytest.raises(ReadError, match="stale_credential"):
        client.get(customer_url())
    assert len(fake.calls) == 1


@pytest.mark.parametrize(
    "headers,expected",
    [
        ({"X-RateLimit-Retry-After": "2"}, 2.0),
        ({"retry-after": "1"}, 1.0),
        ({"X-RateLimit-Retry-After": "1", "Retry-After": "3"}, 3.0),
        ({"Retry-After": "Mon, 12 Oct 2026 18:00:04 GMT"}, 4.0),
    ],
)
def test_rate_limit_respects_server_wait(headers: dict[str, str], expected: float) -> None:
    fake = FakeTransport(response(429, headers), response())
    waits: list[float] = []
    client = ReadClient(EMAIL, transport=fake, clock=lambda: NOW, sleeper=waits.append)
    assert client.get(customer_url()) == {"ok": True}
    assert waits == [expected]
    assert len(fake.calls) == 2


def test_long_rate_limit_returns_pending_delay_without_shortening_it() -> None:
    fake = FakeTransport(response(429, {"X-RateLimit-Retry-After": "60"}))
    waits: list[float] = []
    client = ReadClient(EMAIL, transport=fake, sleeper=waits.append)
    with pytest.raises(ReadError) as caught:
        client.get(customer_url())
    assert caught.value.code == "rate_limited"
    assert caught.value.retry_after == 60.0
    assert waits == []


@pytest.mark.parametrize("header", ["nan", "inf", "-1", "invalid"])
def test_invalid_retry_header_is_terminal(header: str) -> None:
    fake = FakeTransport(response(429, {"X-RateLimit-Retry-After": header}))
    waits: list[float] = []
    client = ReadClient(EMAIL, transport=fake, sleeper=waits.append)
    with pytest.raises(ReadError, match="rate_limited"):
        client.get(customer_url())
    assert len(fake.calls) == 1
    assert waits == []


@pytest.mark.parametrize(
    "status,code", [(429, "rate_limited"), (500, "server_error"), (503, "server_error")]
)
def test_retry_is_bounded(status: int, code: str) -> None:
    fake = FakeTransport(*(response(status) for _ in range(3)))
    waits: list[float] = []
    client = ReadClient(EMAIL, transport=fake, sleeper=waits.append)
    with pytest.raises(ReadError) as caught:
        client.get(customer_url())
    assert (caught.value.code, caught.value.attempts) == (code, 3)
    assert len(fake.calls) == 3
    assert waits == [1.0, 2.0]


def test_network_errors_are_bounded_and_redacted() -> None:
    secret_message = f"GET {customer_url()} Authorization: {TOKEN} private-body"
    fake = FakeTransport(*(OSError(secret_message) for _ in range(3)))
    waits: list[float] = []
    client = ReadClient(EMAIL, transport=fake, sleeper=waits.append)
    with pytest.raises(ReadError) as caught:
        client.get(customer_url())
    assert caught.value.code == "network_error"
    assert caught.value.attempts == 3
    assert waits == [1.0, 2.0]
    assert caught.value.__suppress_context__
    assert EMAIL not in repr(caught.value)
    assert TOKEN not in str(caught.value)
    assert "private-body" not in str(caught.value)


@pytest.mark.parametrize(
    "status,code",
    [
        (301, "redirect_not_followed"),
        (302, "redirect_not_followed"),
        (307, "redirect_not_followed"),
        (404, "http_error"),
    ],
)
def test_redirect_or_missing_resource_is_not_followed_or_a_negative_finding(
    status: int,
    code: str,
) -> None:
    fake = FakeTransport(response(status, {"Location": "https://external.example.test"}))
    client = ReadClient(EMAIL, transport=fake)
    with pytest.raises(ReadError) as caught:
        client.get(customer_url())
    assert caught.value.code == code
    assert caught.value.status == status
    assert len(fake.calls) == 1


@pytest.mark.parametrize(
    "body",
    [
        b"<private-html>",
        b"[]",
        b"null",
        b"\xff",
        b'{"same":1,"same":2}',
        b'{"n":NaN}',
        b'{"n":Infinity}',
    ],
)
def test_invalid_json_is_redacted(body: bytes) -> None:
    fake = FakeTransport(HttpResponse(200, {}, body))
    with pytest.raises(ReadError, match="invalid_json") as caught:
        ReadClient(EMAIL, transport=fake).get(customer_url())
    assert caught.value.status == 200
    assert "private" not in repr(caught.value)


def test_large_body_fails_explicitly() -> None:
    fake = FakeTransport(HttpResponse(200, {}, b"x" * (MAX_BODY_BYTES + 1)))
    with pytest.raises(ReadError, match="response_too_large"):
        ReadClient(EMAIL, transport=fake).get(customer_url())


def test_builtin_https_transport_fixed_host_and_bounded_read_with_fake_connection() -> None:
    class FakeResponse:
        status = 200

        def getheaders(self) -> list[tuple[str, str]]:
            return [("Content-Type", "application/hal+json")]

        def read(self, size: int) -> bytes:
            assert size == MAX_BODY_BYTES + 1
            return json.dumps({"ok": True}).encode()

    class FakeConnection:
        closed = False

        def request(self, method: str, target: str, *, headers: dict[str, str]) -> None:
            assert method == "GET"
            assert target.startswith("/v2/customers?")
            assert headers["Authorization"] == f"Bearer {TOKEN}"

        def getresponse(self) -> FakeResponse:
            return FakeResponse()

        def close(self) -> None:
            self.closed = True

    connection = FakeConnection()
    with patch("http.client.HTTPSConnection", return_value=connection) as factory:
        client = ReadClient(
            EMAIL,
            enable_live=True,
            clock=lambda: NOW,
            credential=SuppliedCredential(TOKEN, NOW + timedelta(minutes=5)),
        )
        assert client.get(customer_url()) == {"ok": True}
    assert factory.call_args.args == ("api.helpscout.net",)
    assert factory.call_args.kwargs["timeout"] == 15.0
    assert connection.closed


@pytest.mark.parametrize("token", ["", "bad\r\nInjected: value", "has space", "x" * 8193])
def test_credential_header_injection_is_rejected_without_exposure(token: str) -> None:
    with pytest.raises(ReadError, match="invalid_credential"):
        SuppliedCredential(token, NOW)


def test_naive_credential_expiry_rejected() -> None:
    with pytest.raises(ReadError, match="invalid_credential_expiry"):
        SuppliedCredential(TOKEN, datetime(2026, 10, 12))


def test_response_repr_omits_sensitive_fields() -> None:
    result = HttpResponse(200, {"Authorization": TOKEN}, EMAIL.encode())
    assert TOKEN not in repr(result)
    assert EMAIL not in repr(result)


@pytest.mark.parametrize("margin", [-1, 121, True, 1.0, "120", None])
def test_invalid_expiry_margin_is_rejected_before_transport(margin: object) -> None:
    fake = FakeTransport()
    with pytest.raises(ReadError, match="invalid_expiry_margin"):
        ReadClient(EMAIL, transport=fake, expiry_margin_seconds=margin)  # type: ignore[arg-type]
    assert fake.calls == []


@pytest.mark.parametrize("remaining_seconds", [-1, 0, 119, 120])
def test_expiry_margin_withholds_bearer_before_first_request(remaining_seconds: int) -> None:
    fake = FakeTransport()
    expiry = NOW + timedelta(seconds=remaining_seconds)
    credential = SuppliedCredential(TOKEN, expiry)
    client = ReadClient(
        EMAIL,
        credential=credential,
        transport=fake,
        clock=lambda: NOW,
        expiry_margin_seconds=120,
    )
    with pytest.raises(ReadError, match="stale_credential") as caught:
        client.get(customer_url())
    assert caught.value.attempts == 0
    assert fake.calls == []
    assert credential.expires_at == expiry


def test_expiry_margin_is_checked_for_each_request_without_changing_source_expiry() -> None:
    fake = FakeTransport(response())
    now = NOW
    expiry = NOW + timedelta(seconds=121)
    credential = SuppliedCredential(TOKEN, expiry)
    client = ReadClient(
        EMAIL,
        credential=credential,
        transport=fake,
        clock=lambda: now,
        expiry_margin_seconds=120,
    )
    assert client.get(customer_url()) == {"ok": True}
    assert fake.calls[0][2]["Authorization"] == f"Bearer {TOKEN}"
    now += timedelta(seconds=1)
    with pytest.raises(ReadError, match="stale_credential"):
        client.get(customer_url())
    assert len(fake.calls) == 1
    assert credential.expires_at == expiry
