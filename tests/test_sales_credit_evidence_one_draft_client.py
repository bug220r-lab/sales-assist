"""Synthetic one-draft boundary tests; all HTTP and credentials are injected."""

from __future__ import annotations

import copy
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from doi_draft_transfer.contract import TransferError, rendered_body
from sales_credit_evidence import one_draft_client as module
from sales_credit_evidence.one_draft_client import OneDraftClient
from sales_credit_evidence.transport import MAILBOX_ID, TARGET_AUTHOR_ID, SuppliedCredential

NOW = datetime(2026, 10, 12, 20, tzinfo=UTC)
TOKEN = "test-token"
CUSTOMER = 990001
CONVERSATION = 990002
ROW = {
    "recipient_email": "approved@example.test",
    "subject": "SYNTHETIC APPROVED DRAFT",
    "order_id": "90000001",
    "selected_body_text": "Hello!\n\nSynthetic approved copy.",
}


@dataclass
class Bundle:
    recipient: str = ROW["recipient_email"]
    subject: str = ROW["subject"]
    rendered_body_sha256: str = hashlib.sha256(
        rendered_body(ROW["selected_body_text"]).encode()
    ).hexdigest()
    order_id: str = ROW["order_id"]
    bundle_sha256: str = "a" * 64


@dataclass
class Evidence:
    customer_id: int = CUSTOMER
    valid: bool = True

    def assert_for(self, bundle: Any) -> None:
        if not self.valid or bundle.bundle_sha256 != "a" * 64:
            raise ValueError("synthetic private error")


def response(status: int, value: Any = None, headers: dict[str, str] | None = None) -> tuple:
    return status, headers or {}, b"" if value is None else json.dumps(value).encode()


def draft_value() -> dict[str, Any]:
    return {
        "id": CONVERSATION,
        "state": "draft",
        "mailboxId": MAILBOX_ID,
        "subject": ROW["subject"],
        "assignee": {"id": TARGET_AUTHOR_ID},
        "primaryCustomer": {"id": CUSTOMER, "email": ROW["recipient_email"]},
        "_embedded": {
            "threads": [
                {
                    "type": "message",
                    "state": "draft",
                    "createdBy": {"id": TARGET_AUTHOR_ID},
                    "to": [ROW["recipient_email"]],
                    "body": rendered_body(ROW["selected_body_text"]),
                }
            ]
        },
    }


class Wire:
    def __init__(self, replies: list[Any] | None = None) -> None:
        self.replies = replies or [
            response(200, {"id": MAILBOX_ID}),
            response(200, {"id": TARGET_AUTHOR_ID}),
            response(201, headers={"resource-id": str(CONVERSATION)}),
            response(200, draft_value()),
        ]
        self.calls: list[tuple] = []

    def __call__(self, method: str, path: str, payload: Any, bearer: str) -> tuple:
        self.calls.append((method, path, copy.deepcopy(payload), bearer))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def client(wire: Wire | None = None, **kwargs: Any) -> tuple[OneDraftClient, Wire]:
    wire = wire or Wire()
    credential = kwargs.pop("credential", SuppliedCredential(TOKEN, NOW + timedelta(hours=1)))
    instance = OneDraftClient(
        kwargs.pop("bundle", Bundle()),
        kwargs.pop("evidence", Evidence()),
        credential,
        clock=kwargs.pop("clock", lambda: NOW),
        transport=wire,
        **kwargs,
    )
    return instance, wire


def test_construction_has_no_io_and_exact_existing_customer_payload() -> None:
    instance, wire = client()
    assert not wire.calls
    assert instance.check_destination()["verified"] is True
    result = instance.create_draft(ROW)
    assert result["state"] == "CREATED"
    assert result["retry_allowed"] is False
    assert [call[0] for call in wire.calls] == ["GET", "GET", "POST", "GET"]
    assert {call[3] for call in wire.calls} == {TOKEN}
    payload = wire.calls[2][2]
    assert payload["customer"] == {"id": CUSTOMER}
    assert payload["threads"][0]["customer"] == {"id": CUSTOMER}
    assert payload["threads"][0]["draft"] is True
    assert payload["autoReply"] is False
    assert payload["threads"][0]["text"] == rendered_body(ROW["selected_body_text"])
    assert payload["assignTo"] == payload["user"] == TARGET_AUTHOR_ID
    assert payload["mailboxId"] == MAILBOX_ID
    assert len(payload["threads"]) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("recipient_email", "different@example.test"),
        ("subject", "Different"),
        ("order_id", "90000002"),
        ("selected_body_text", "Different"),
    ],
)
def test_row_mismatch_never_posts(field: str, value: str) -> None:
    instance, wire = client()
    instance.check_destination()
    result = instance.create_draft(dict(ROW, **{field: value}))
    assert result == {"state": "REJECTED", "code": "ONE_DRAFT_BLOCKED", "retry_allowed": False}
    assert len(wire.calls) == 2


@pytest.mark.parametrize(
    "tamper",
    [
        lambda p: p.update(extra=True),
        lambda p: p.update(status="pending"),
        lambda p: p.update(mailboxId=990003),
        lambda p: p.update(autoReply=True),
        lambda p: p["threads"][0].update(draft=False),
        lambda p: p["threads"][0].update(cc=["copy@example.test"]),
        lambda p: p["threads"].append(dict(p["threads"][0])),
    ],
)
def test_payload_builder_tamper_blocks(monkeypatch: pytest.MonkeyPatch, tamper: Any) -> None:
    original = module.legacy.payload_for

    def changed(row: dict) -> dict:
        payload = original(row)
        tamper(payload)
        return payload

    monkeypatch.setattr(module.legacy, "payload_for", changed)
    instance, wire = client()
    instance.check_destination()
    assert instance.create_draft(ROW)["state"] == "REJECTED"
    assert len(wire.calls) == 2


def test_destination_is_required_before_post() -> None:
    instance, wire = client()
    assert instance.create_draft(ROW)["state"] == "REJECTED"
    assert not wire.calls


@pytest.mark.parametrize("value", [{"id": MAILBOX_ID + 1}, {"id": str(MAILBOX_ID)}, [], None])
def test_wrong_destination_stops_before_any_write(value: Any) -> None:
    instance, wire = client(Wire([response(200, value)]))
    with pytest.raises(TransferError, match="ONE_DRAFT_DESTINATION_UNVERIFIED"):
        instance.check_destination()
    assert instance.create_draft(ROW)["state"] == "REJECTED"
    assert len(wire.calls) == 1


@pytest.mark.parametrize("remaining", [-1, 0, 119, 120])
def test_expired_or_margin_token_performs_no_http(remaining: int) -> None:
    instance, wire = client(
        credential=SuppliedCredential(TOKEN, NOW + timedelta(seconds=remaining))
    )
    with pytest.raises(TransferError):
        instance.check_destination()
    assert not wire.calls


def test_121_seconds_is_usable_without_adjusting_expiry() -> None:
    snapshot = SuppliedCredential(TOKEN, NOW + timedelta(seconds=121))
    instance, wire = client(credential=snapshot)
    instance.check_destination()
    assert instance.create_draft(ROW)["state"] == "CREATED"
    assert snapshot.expires_at == NOW + timedelta(seconds=121)
    assert len(wire.calls) == 4


def test_expiry_between_destination_and_post_blocks_write() -> None:
    times = iter([NOW, NOW, NOW + timedelta(hours=1)])
    instance, wire = client(clock=lambda: next(times))
    instance.check_destination()
    assert instance.create_draft(ROW)["retry_allowed"] is False
    assert len(wire.calls) == 2


def test_expiry_before_readback_preserves_known_created_id() -> None:
    times = iter([NOW, NOW, NOW, NOW + timedelta(hours=1)])
    instance, wire = client(clock=lambda: next(times))
    instance.check_destination()
    result = instance.create_draft(ROW)
    assert result["state"] == "CREATED_UNVERIFIED"
    assert result["conversation_id"] == str(CONVERSATION)
    assert result["retry_allowed"] is False
    assert len(wire.calls) == 3


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_latches_no_further_http_or_retry(status: int) -> None:
    instance, wire = client(Wire([response(status, {})]))
    with pytest.raises(TransferError):
        instance.check_destination()
    with pytest.raises(TransferError):
        instance._request("GET", f"/v2/users/{TARGET_AUTHOR_ID}")
    assert instance.create_draft(ROW)["state"] == "REJECTED"
    assert len(wire.calls) == 1


@pytest.mark.parametrize(
    "reply,expected",
    [
        (response(401), "AUTH_REQUIRED"),
        (response(403), "AUTH_REQUIRED"),
        (response(429), "RATE_LIMITED"),
        (response(400), "REJECTED"),
        (response(408), "UNKNOWN"),
        (response(409), "UNKNOWN"),
        (response(425), "UNKNOWN"),
        (response(500), "UNKNOWN"),
        (response(302), "UNKNOWN"),
        (TimeoutError("private"), "UNKNOWN"),
        (RuntimeError("private"), "UNKNOWN"),
        (response(201), "UNKNOWN"),
        (response(201, headers={"resource-id": "0"}), "UNKNOWN"),
    ],
)
def test_write_outcomes_never_allow_second_post(reply: Any, expected: str) -> None:
    wire = Wire([response(200, {"id": MAILBOX_ID}), response(200, {"id": TARGET_AUTHOR_ID}), reply])
    instance, wire = client(wire)
    instance.check_destination()
    result = instance.create_draft(ROW)
    assert result["state"] == expected
    assert result["retry_allowed"] is False
    assert instance.create_draft(ROW)["retry_allowed"] is False
    assert [call[0] for call in wire.calls] == ["GET", "GET", "POST"]
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize(
    "change",
    [
        lambda v: v["primaryCustomer"].update(id=CUSTOMER + 1),
        lambda v: v["primaryCustomer"].update(id=str(CUSTOMER)),
        lambda v: v["primaryCustomer"].update(email="different@example.test"),
        lambda v: v.update(state="published"),
        lambda v: v.update(subject="Different"),
        lambda v: v.update(mailboxId=MAILBOX_ID + 1),
        lambda v: v["assignee"].update(id=TARGET_AUTHOR_ID + 1),
        lambda v: v["_embedded"]["threads"][0].update(state="published"),
        lambda v: v["_embedded"]["threads"][0].update(body="Different"),
        lambda v: v["_embedded"]["threads"][0].update(cc=["copy@example.test"]),
        lambda v: v["_embedded"]["threads"][0].update(scheduled=True),
    ],
)
def test_readback_mismatch_preserves_id_and_blocks_retry(change: Any) -> None:
    value = draft_value()
    change(value)
    wire = Wire()
    wire.replies[-1] = response(200, value)
    instance, wire = client(wire)
    instance.check_destination()
    result = instance.create_draft(ROW)
    assert result["state"] == "CREATED_UNVERIFIED"
    assert result["conversation_id"] == str(CONVERSATION)
    assert result["retry_allowed"] is False
    assert instance.verify_draft(ROW, result)["state"] == "CREATED_UNVERIFIED"
    assert instance.create_draft(ROW)["retry_allowed"] is False
    assert len(wire.calls) == 4


@pytest.mark.parametrize(
    "reply",
    [
        response(401),
        response(500),
        TimeoutError("private"),
        (200, {}, b'{"primaryCustomer":{"id":1,"id":2}}'),
    ],
)
def test_readback_failure_never_repeats_write(reply: Any) -> None:
    wire = Wire()
    wire.replies[-1] = reply
    instance, wire = client(wire)
    instance.check_destination()
    result = instance.create_draft(ROW)
    assert result["state"] == "CREATED_UNVERIFIED"
    assert result["conversation_id"] == str(CONVERSATION)
    assert result["retry_allowed"] is False
    assert len(wire.calls) == 4


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", "/v2/conversations/990005?embed=threads", None),
        ("POST", "/v2/customers", {}),
        ("PATCH", "/v2/conversations/990002", {}),
        ("DELETE", "/v2/conversations/990002", None),
        ("GET", f"/v2/mailboxes/{MAILBOX_ID}", {}),
        ("POST", "/v2/conversations", {"extra": True}),
    ],
)
def test_forbidden_requests_never_reach_transport(method: str, path: str, payload: Any) -> None:
    instance, wire = client()
    with pytest.raises(TransferError):
        instance._request(method, path, payload)
    assert not wire.calls


def test_no_grant_for_arbitrary_known_conversation() -> None:
    instance, wire = client()
    with pytest.raises(TransferError, match="ONE_DRAFT_KNOWN_CONVERSATION_REQUIRED"):
        instance.verify_draft(ROW, {"conversation_id": str(CONVERSATION)})
    assert not wire.calls


def test_changed_evidence_invalidates_write() -> None:
    evidence = Evidence()
    instance, wire = client(evidence=evidence)
    instance.check_destination()
    evidence.valid = False
    assert instance.create_draft(ROW)["state"] == "REJECTED"
    assert len(wire.calls) == 2


def test_changed_bundle_invalidates_write() -> None:
    bundle = Bundle()
    instance, wire = client(bundle=bundle)
    instance.check_destination()
    bundle.subject = "Different"
    assert instance.create_draft(ROW)["state"] == "REJECTED"
    assert len(wire.calls) == 2


@pytest.mark.parametrize("customer_id", [True, 0, -1, "990001", 2**63])
def test_invalid_customer_id_never_constructs(customer_id: Any) -> None:
    with pytest.raises(TransferError, match="ONE_DRAFT_SCOPE_INVALID"):
        client(evidence=Evidence(customer_id=customer_id))


def test_close_discards_snapshot_and_blocks_requests() -> None:
    instance, wire = client()
    instance.close()
    instance.close()
    with pytest.raises(TransferError):
        instance.check_destination()
    assert instance._credential is None
    assert not wire.calls


def test_environment_provider_selection_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("environment must not be read")

    monkeypatch.setattr(module.legacy.os.environ, "get", forbidden)
    with pytest.raises(TransferError, match="ONE_DRAFT_ENVIRONMENT_PROHIBITED"):
        OneDraftClient.from_environment()


def test_concurrent_create_calls_reserve_only_one_post() -> None:
    instance, wire = client()
    instance.check_destination()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(instance.create_draft, [ROW, ROW]))
    assert sum(call[0] == "POST" for call in wire.calls) == 1
    assert len(wire.calls) == 4
    assert all(result["retry_allowed"] is False for result in results)


def test_destination_checks_cannot_repeat_or_exceed_budget() -> None:
    instance, wire = client()
    instance.check_destination()
    with pytest.raises(TransferError):
        instance.check_destination()
    assert len(wire.calls) == 2


@pytest.mark.parametrize(
    "reply",
    [
        (200, {}, "not bytes"),
        (True, {}, b"{}"),
        (200, [], b"{}"),
        (200, {"x": object()}, b"{}"),
        (200, {}, b"x" * (module.legacy.MAX_RESPONSE + 1)),
    ],
)
def test_invalid_destination_responses_are_closed_and_safe(reply: Any) -> None:
    instance, wire = client(Wire([reply]))
    with pytest.raises(TransferError, match="ONE_DRAFT_DESTINATION_UNVERIFIED"):
        instance.check_destination()
    assert len(wire.calls) == 1


@pytest.mark.parametrize("status", [401, 403])
def test_malformed_auth_failure_also_revokes_further_http(status: int) -> None:
    instance, wire = client(Wire([(status, {}, "private invalid body")]))
    with pytest.raises(TransferError):
        instance.check_destination()
    with pytest.raises(TransferError):
        instance._request("GET", f"/v2/users/{TARGET_AUTHOR_ID}")
    assert len(wire.calls) == 1


@pytest.mark.parametrize("clock_value", [None, NOW.replace(tzinfo=None), "invalid"])
def test_invalid_clock_performs_no_http(clock_value: Any) -> None:
    instance, wire = client(clock=lambda: clock_value)
    with pytest.raises(TransferError):
        instance.check_destination()
    assert not wire.calls


def test_successful_readback_contains_only_known_fields_and_codes() -> None:
    instance, wire = client()
    instance.check_destination()
    result = instance.create_draft(ROW)
    assert result["code"] in module.ONE_DRAFT_ERROR_CODES
    assert set(result) == {
        "state",
        "code",
        "conversation_id",
        "web_link",
        "api_location",
        "retry_allowed",
    }
    assert ROW["recipient_email"] not in json.dumps(result)
    assert TOKEN not in json.dumps(result)
    assert len(wire.calls) == 4
