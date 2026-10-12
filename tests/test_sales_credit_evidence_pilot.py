"""Offline pilot/CLI lifecycle tests: synthetic identities and injected I/O only."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from sales_credit_evidence import pilot
from sales_credit_evidence.__main__ import main
from sales_credit_evidence.transport import (
    API_ORIGIN,
    MAILBOX_ID,
    TARGET_AUTHOR_ID,
    HttpResponse,
    ReadError,
    SuppliedCredential,
)

EMAIL = "pilot-synthetic@example.test"
CONNECTION_PATH = r"C:\synthetic-test\connection.dpapi"
SYNTHETIC_TOKEN = "synthetic-pilot-token-not-valid"
NOW = datetime(2026, 10, 12, 18, tzinfo=UTC)


def request(**overrides):
    values = {
        "email": EMAIL,
        "connection_path": CONNECTION_PATH,
        "ownership": "cleanup-complete",
        "sole_owner_confirmed": True,
        "enable_live": True,
    }
    values.update(overrides)
    return pilot.PilotRequest(**values)


def paged(key, records):
    return {
        "_embedded": {key: records},
        "_links": {},
        "page": {"number": 1, "size": 50, "totalElements": len(records), "totalPages": 1},
    }


def emails(customer_id=10, address=EMAIL):
    return {
        "_embedded": {"emails": [{"id": customer_id + 500, "value": address}]},
        "_links": {"self": {"href": f"{API_ORIGIN}/v2/customers/{customer_id}/emails"}},
    }


def basic_routes():
    return {
        "/v2/customers": paged("customers", [{"id": 10}]),
        "/v2/customers/10/emails": emails(),
        "/v2/conversations": paged("conversations", []),
    }


class FakeIO:
    def __init__(self):
        self.events = []
        self.held = False
        self.loader_calls = 0
        self.http_calls = []
        self.close_calls = 0
        self.now = NOW
        self.expires_at = NOW + timedelta(hours=1)
        self.routes = basic_routes()
        self.acquire_error = None
        self.load_error = None
        self.close_error = None
        self.after_first_http = None

    def factory(self):
        self.events.append("factory")
        return self

    def acquire(self):
        self.events.append("acquire")
        if self.acquire_error is not None:
            raise self.acquire_error
        self.held = True

    def close(self):
        self.events.append("close")
        self.close_calls += 1
        self.held = False
        if self.close_error is not None:
            raise self.close_error

    def load(self, path):
        self.events.append("load")
        self.loader_calls += 1
        assert self.held, "lease must be acquired before reading snapshot"
        assert path == CONNECTION_PATH
        if self.load_error is not None:
            raise self.load_error
        return SuppliedCredential(SYNTHETIC_TOKEN, self.expires_at)

    def http(self, method, url, headers):
        self.events.append("http")
        assert self.held, "lease must remain held for the entire read"
        assert method == "GET"
        assert headers["Authorization"] == f"Bearer {SYNTHETIC_TOKEN}"
        parsed = urlsplit(url)
        assert parsed.scheme + "://" + parsed.netloc == API_ORIGIN
        self.http_calls.append((method, parsed.path, parse_qs(parsed.query)))
        if len(self.http_calls) == 1 and self.after_first_http is not None:
            self.after_first_http()
        value = self.routes[parsed.path]
        if isinstance(value, Exception):
            raise value
        if isinstance(value, HttpResponse):
            return value
        return HttpResponse(200, {}, json.dumps(value).encode())

    def run(self, value=None):
        return pilot.run_pilot(
            request() if value is None else value,
            snapshot_loader=self.load,
            lease_factory=self.factory,
            transport=self.http,
            clock=lambda: self.now,
        )


def assert_safe_summary(result):
    rendered = json.dumps(result)
    assert EMAIL not in rendered
    assert CONNECTION_PATH not in rendered
    assert SYNTHETIC_TOKEN not in rendered
    assert "synthetic-private-body" not in rendered
    assert result["mailbox_id"] == MAILBOX_ID
    assert result["target_author_id"] == TARGET_AUTHOR_ID
    assert result["credit_classification"] == "NOT_EVALUATED"


def assert_no_negative_finding(result):
    assert result["complete"] is False
    assert result["no_scoped_conversations"] is False


def test_request_is_frozen_and_repr_hides_email_and_connection_path():
    value = request()
    assert EMAIL not in repr(value) and CONNECTION_PATH not in repr(value)
    with pytest.raises(FrozenInstanceError):
        value.enable_live = False


def test_default_disabled_before_any_injected_dependency():
    fake = FakeIO()
    value = pilot.PilotRequest(email=EMAIL, connection_path=CONNECTION_PATH)
    result = fake.run(value)
    assert result["status"] == "DISABLED"
    assert fake.events == []
    assert_no_negative_finding(result)
    assert_safe_summary(result)


@pytest.mark.parametrize(
    "overrides",
    [
        {"ownership": ""},
        {"ownership": "cleanup-running"},
        {"ownership": "handoff-requested"},
        {"ownership": "synthetic-private-body"},
        {"sole_owner_confirmed": False},
        {"sole_owner_confirmed": 1},
        {"enable_live": 1},
        {"email": ""},
        {"email": "name"},
        {"email": "one@example.test,two@example.test"},
        {"email": 'one@example.test" OR email:"two@example.test'},
        {"connection_path": ""},
    ],
)
def test_unauthorized_or_invalid_request_is_blocked_before_dependencies(overrides):
    fake = FakeIO()
    result = fake.run(request(**overrides))
    assert result["status"] == "BLOCKED"
    assert fake.events == []
    assert_no_negative_finding(result)
    assert result["customer_count"] == result["conversation_count"] == result["thread_count"] == 0
    assert result["issues"]
    assert_safe_summary(result)


@pytest.mark.parametrize("ownership", ["cleanup-complete", "controlled-handoff-complete"])
def test_explicit_owner_read_holds_lease_through_snapshot_and_all_requests(ownership):
    fake = FakeIO()
    result = fake.run(request(ownership=ownership))
    assert result["status"] == "COMPLETE" and result["complete"] is True
    assert result["identity_status"] == "EXACT"
    assert result["no_scoped_conversations"] is True
    assert fake.events == ["factory", "acquire", "load", "http", "http", "http", "close"]
    assert fake.loader_calls == 1 and fake.close_calls == 1 and not fake.held
    assert_safe_summary(result)


def test_lease_acquisition_failure_blocks_snapshot_and_network():
    fake = FakeIO()
    fake.acquire_error = RuntimeError(f"synthetic-private-body {EMAIL} {SYNTHETIC_TOKEN}")
    result = fake.run()
    assert result["status"] == "BLOCKED"
    assert fake.loader_calls == 0 and fake.http_calls == [] and not fake.held
    assert fake.close_calls == 1
    assert_no_negative_finding(result)
    assert_safe_summary(result)


def test_lease_factory_failure_does_not_read_snapshot_or_attempt_close():
    fake = FakeIO()

    def broken_factory():
        fake.events.append("factory")
        raise RuntimeError(f"synthetic-private-body {SYNTHETIC_TOKEN}")

    result = pilot.run_pilot(
        request(),
        snapshot_loader=fake.load,
        lease_factory=broken_factory,
        transport=fake.http,
        clock=lambda: NOW,
    )
    assert result["status"] == "BLOCKED"
    assert fake.events == ["factory"]
    assert_no_negative_finding(result)
    assert_safe_summary(result)


@pytest.mark.parametrize("invalid", [None, {}, "synthetic-private-body"])
def test_invalid_snapshot_return_is_blocked_without_http_and_releases_lease(invalid):
    fake = FakeIO()

    def invalid_loader(path):
        assert fake.held and path == CONNECTION_PATH
        fake.events.append("load")
        return invalid

    result = pilot.run_pilot(
        request(),
        snapshot_loader=invalid_loader,
        lease_factory=fake.factory,
        transport=fake.http,
        clock=lambda: NOW,
    )
    assert result["status"] == "BLOCKED"
    assert fake.events == ["factory", "acquire", "load", "close"]
    assert fake.http_calls == []
    assert_no_negative_finding(result)
    assert_safe_summary(result)


@pytest.mark.parametrize(
    "error",
    [
        ReadError("cached_snapshot_missing"),
        ReadError("cached_snapshot_expired"),
        ReadError(f"synthetic-private-body {SYNTHETIC_TOKEN}"),
        RuntimeError(f"synthetic-private-body {EMAIL} {SYNTHETIC_TOKEN}"),
    ],
)
def test_snapshot_failure_releases_lease_and_returns_safe_blocked_result(error):
    fake = FakeIO()
    fake.load_error = error
    result = fake.run()
    assert result["status"] == "BLOCKED"
    assert fake.events == ["factory", "acquire", "load", "close"]
    assert fake.http_calls == [] and fake.close_calls == 1 and not fake.held
    assert_no_negative_finding(result)
    assert_safe_summary(result)


@pytest.mark.parametrize("seconds_left", [-1, 0, 119, 120])
def test_expired_or_within_margin_snapshot_blocks_first_http(seconds_left):
    fake = FakeIO()
    fake.expires_at = NOW + timedelta(seconds=seconds_left)
    result = fake.run()
    assert result["status"] == "BLOCKED"
    assert fake.http_calls == [] and fake.loader_calls == 1 and fake.close_calls == 1
    assert_no_negative_finding(result)
    assert_safe_summary(result)


def test_expiry_margin_is_rechecked_before_next_http_without_snapshot_reload():
    fake = FakeIO()
    fake.expires_at = NOW + timedelta(seconds=121)
    fake.after_first_http = lambda: setattr(fake, "now", NOW + timedelta(seconds=2))
    result = fake.run()
    assert result["status"] == "INCOMPLETE"
    assert len(fake.http_calls) == 1 and fake.loader_calls == 1 and fake.close_calls == 1
    assert_no_negative_finding(result)
    assert_safe_summary(result)


@pytest.mark.parametrize("clock_value", [None, NOW.replace(tzinfo=None), "synthetic-private-body"])
def test_invalid_preflight_clock_blocks_http_and_releases_lease(clock_value):
    fake = FakeIO()
    result = pilot.run_pilot(
        request(),
        snapshot_loader=fake.load,
        lease_factory=fake.factory,
        transport=fake.http,
        clock=lambda: clock_value,
    )
    assert result["status"] == "BLOCKED"
    assert fake.http_calls == [] and fake.loader_calls == fake.close_calls == 1
    assert_no_negative_finding(result)
    assert_safe_summary(result)


def test_throwing_preflight_clock_is_sanitized_and_releases_lease():
    fake = FakeIO()

    def broken_clock():
        raise RuntimeError(f"synthetic-private-body {EMAIL} {SYNTHETIC_TOKEN}")

    result = pilot.run_pilot(
        request(),
        snapshot_loader=fake.load,
        lease_factory=fake.factory,
        transport=fake.http,
        clock=broken_clock,
    )
    assert result["status"] == "BLOCKED"
    assert fake.http_calls == [] and fake.loader_calls == fake.close_calls == 1
    assert_no_negative_finding(result)
    assert_safe_summary(result)


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_pilot_http_failures_have_one_attempt_no_renewal_and_safe_incomplete_result(status):
    fake = FakeIO()
    fake.routes["/v2/customers"] = HttpResponse(
        status,
        {"X-RateLimit-Retry-After": "0"},
        json.dumps({"message": f"synthetic-private-body {EMAIL} {SYNTHETIC_TOKEN}"}).encode(),
    )
    result = fake.run()
    assert result["status"] == "INCOMPLETE"
    assert len(fake.http_calls) == 1 and fake.loader_calls == 1 and fake.close_calls == 1
    assert_no_negative_finding(result)
    assert result["issues"]
    assert_safe_summary(result)


def test_unexpected_transport_error_is_sanitized_and_lease_released():
    fake = FakeIO()
    fake.routes["/v2/customers"] = RuntimeError(
        f"synthetic-private-body {EMAIL} {SYNTHETIC_TOKEN} {CONNECTION_PATH}"
    )
    result = fake.run()
    assert result["status"] == "INCOMPLETE"
    assert len(fake.http_calls) == fake.loader_calls == fake.close_calls == 1
    assert_no_negative_finding(result)
    assert_safe_summary(result)


def test_lease_release_failure_cannot_report_complete_success():
    fake = FakeIO()
    fake.close_error = RuntimeError(f"synthetic-private-body {SYNTHETIC_TOKEN}")
    result = fake.run()
    assert result["status"] == "INCOMPLETE"
    assert fake.close_calls == 1
    assert_no_negative_finding(result)
    assert_safe_summary(result)


def test_ambiguous_identity_is_incomplete_and_does_not_search_conversations():
    fake = FakeIO()
    fake.routes["/v2/customers"] = paged("customers", [{"id": 10}, {"id": 11}])
    fake.routes["/v2/customers/11/emails"] = emails(11)
    result = fake.run()
    assert result["status"] == "INCOMPLETE" and result["identity_status"] == "AMBIGUOUS"
    assert result["customer_count"] == 2
    assert all(path != "/v2/conversations" for _, path, _ in fake.http_calls)
    assert_no_negative_finding(result)
    assert_safe_summary(result)


def test_complete_identity_search_without_match_is_not_conversation_absence():
    fake = FakeIO()
    fake.routes["/v2/customers"] = paged("customers", [])
    result = fake.run()
    assert result["status"] == "COMPLETE"
    assert result["identity_status"] == "NO_EXACT_CUSTOMER"
    assert result["complete"] is True and result["no_scoped_conversations"] is False
    assert len(fake.http_calls) == 1 and fake.close_calls == 1
    assert_safe_summary(result)


def test_partial_search_cannot_report_no_conversations():
    fake = FakeIO()
    fake.routes["/v2/conversations"] = {"_embedded": {"conversations": []}, "_links": {}}
    result = fake.run()
    assert result["status"] == "INCOMPLETE" and result["identity_status"] == "EXACT"
    assert_no_negative_finding(result)
    assert_safe_summary(result)


def test_complete_history_returns_only_safe_counts_and_no_credit_inference():
    fake = FakeIO()
    conversation = {
        "id": 100,
        "number": 200,
        "mailboxId": MAILBOX_ID,
        "primaryCustomer": {"id": 10, "email": EMAIL},
        "type": "email",
        "state": "published",
        "status": "closed",
        "threads": 2,
        "userUpdatedAt": "2026-10-01T16:00:00Z",
        "subject": "synthetic-private-body",
        "preview": "synthetic-private-body",
    }
    fake.routes["/v2/conversations"] = paged("conversations", [conversation])
    fake.routes["/v2/conversations/100"] = conversation
    fake.routes["/v2/conversations/100/threads"] = paged(
        "threads",
        [
            {
                "id": 1000,
                "type": "message",
                "state": "published",
                "status": "active",
                "createdAt": "2026-10-01T14:00:00Z",
                "createdBy": {"id": TARGET_AUTHOR_ID, "type": "user"},
                "customer": {"id": 10},
                "to": [EMAIL],
                "source": {"type": "web", "via": "user"},
                "body": "synthetic-private-body",
            },
            {
                "id": 1001,
                "type": "customer",
                "state": "published",
                "status": "active",
                "createdAt": "2026-10-01T14:01:00Z",
                "createdBy": {"id": 10, "type": "customer", "email": EMAIL},
                "customer": {"id": 10},
                "source": {"type": "email", "via": "customer"},
                "body": "synthetic-private-body",
            },
        ],
    )
    result = fake.run()
    assert result["status"] == "COMPLETE" and result["complete"] is True
    assert result["customer_count"] == result["conversation_count"] == 1
    assert result["thread_count"] == 2 and result["no_scoped_conversations"] is False
    assert len(fake.http_calls) == 6 and fake.close_calls == 1 and not fake.held
    assert_safe_summary(result)


def test_invalid_request_object_is_blocked_without_dependency_calls():
    fake = FakeIO()
    result = pilot.run_pilot(
        {"email": EMAIL},
        snapshot_loader=fake.load,
        lease_factory=fake.factory,
        transport=fake.http,
        clock=lambda: NOW,
    )
    assert result["status"] == "BLOCKED" and fake.events == []
    assert_no_negative_finding(result)
    assert_safe_summary(result)


def test_pilot_read_budget_is_fifty_requests_and_then_incomplete():
    fake = FakeIO()
    fake.routes["/v2/customers"] = paged("customers", [{"id": i} for i in range(10, 60)])
    for identifier in range(10, 60):
        fake.routes[f"/v2/customers/{identifier}/emails"] = emails(
            identifier, f"candidate{identifier}@example.test"
        )
    result = fake.run()
    assert result["status"] == "INCOMPLETE"
    assert len(fake.http_calls) == 50 and fake.loader_calls == fake.close_calls == 1
    assert_no_negative_finding(result)
    assert_safe_summary(result)


def cli_arguments():
    return [
        "--live",
        "--email",
        EMAIL,
        "--connection-path",
        CONNECTION_PATH,
        "--ownership",
        "cleanup-complete",
        "--confirm-sole-owner",
    ]


def safe_cli_result(status="COMPLETE"):
    return {
        "status": status,
        "complete": status == "COMPLETE",
        "mailbox_id": MAILBOX_ID,
        "target_author_id": TARGET_AUTHOR_ID,
        "customer_count": 1,
        "conversation_count": 0,
        "thread_count": 0,
        "credit_classification": "NOT_EVALUATED",
        "no_scoped_conversations": False,
        "issues": [],
    }


def test_cli_default_and_demo_never_invoke_pilot(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("pilot must not run for help or demo")

    monkeypatch.setattr(pilot, "run_pilot", forbidden)
    assert main([]) == 0
    assert "live access disabled" in capsys.readouterr().out
    assert main(["--demo"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["complete"] is True
    assert summary["credit_classification"] == "NOT_EVALUATED"


def test_cli_explicit_live_arguments_create_scoped_request_and_emit_only_safe_summary(
    monkeypatch, capsys
):
    received = []

    def fake_run(value):
        received.append(value)
        return safe_cli_result()

    monkeypatch.setattr(pilot, "run_pilot", fake_run)
    assert main(cli_arguments()) == 0
    assert len(received) == 1
    value = received[0]
    assert value.email == EMAIL and value.connection_path == CONNECTION_PATH
    assert value.ownership == "cleanup-complete"
    assert value.enable_live is True and value.sole_owner_confirmed is True
    output = capsys.readouterr()
    assert json.loads(output.out)["status"] == "COMPLETE" and output.err == ""
    assert EMAIL not in output.out and CONNECTION_PATH not in output.out


@pytest.mark.parametrize("status", ["BLOCKED", "INCOMPLETE", "DISABLED"])
def test_cli_unsuccessful_pilot_returns_nonzero_and_safe_summary(monkeypatch, capsys, status):
    monkeypatch.setattr(pilot, "run_pilot", lambda value: safe_cli_result(status))
    assert main(cli_arguments()) != 0
    output = capsys.readouterr()
    assert json.loads(output.out)["status"] == status
    assert EMAIL not in output.out + output.err
    assert CONNECTION_PATH not in output.out + output.err


@pytest.mark.parametrize(
    "extra",
    [
        ["--token", SYNTHETIC_TOKEN],
        ["--unknown-secret=" + SYNTHETIC_TOKEN],
        ["--email", "second@example.test"],
        ["--connection-path", r"C:\synthetic-test\second.json"],
        ["--ownership", "controlled-handoff-complete"],
        ["--ownership", SYNTHETIC_TOKEN],
        [SYNTHETIC_TOKEN],
    ],
)
def test_cli_rejects_duplicate_or_unsupported_arguments_without_echoing_values(
    monkeypatch, capsys, extra
):
    received = []
    monkeypatch.setattr(pilot, "run_pilot", lambda value: received.append(value))
    assert main(cli_arguments() + extra) != 0
    output = capsys.readouterr()
    rendered = output.out + output.err
    assert "invalid_arguments" in rendered
    assert SYNTHETIC_TOKEN not in rendered and EMAIL not in rendered
    assert CONNECTION_PATH not in rendered and "second@example.test" not in rendered
    assert received == []


@pytest.mark.parametrize(
    "arguments",
    [
        ["--demo", "--live"],
        ["--live", "--email"],
        ["--live", "--ownership", "unsupported-state"],
    ],
)
def test_cli_missing_or_conflicting_scope_is_redacted_before_pilot(monkeypatch, capsys, arguments):
    received = []
    monkeypatch.setattr(pilot, "run_pilot", lambda value: received.append(value))
    assert main(arguments) != 0
    output = capsys.readouterr()
    rendered = output.out + output.err
    assert "invalid_arguments" in rendered
    assert EMAIL not in rendered and "unsupported-state" not in rendered
    assert received == []


@pytest.mark.parametrize(
    "arguments,status,live",
    [(["--live"], "BLOCKED", True), (["--email", EMAIL], "DISABLED", False)],
)
def test_cli_incomplete_scope_is_delegated_to_non_io_pilot_gates(
    monkeypatch, capsys, arguments, status, live
):
    received = []

    def fake_run(value):
        received.append(value)
        return safe_cli_result(status)

    monkeypatch.setattr(pilot, "run_pilot", fake_run)
    assert main(arguments) != 0
    assert len(received) == 1
    assert received[0].enable_live is live
    assert received[0].sole_owner_confirmed is False and received[0].ownership == ""
    output = capsys.readouterr()
    assert json.loads(output.out)["status"] == status
    assert EMAIL not in output.out + output.err
