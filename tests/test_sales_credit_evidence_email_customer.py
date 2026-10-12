"""Synthetic explicit-ID and one-POST email association regressions."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import pytest

from sales_credit_evidence import coordinator
from sales_credit_evidence.draft_preflight import (
    DraftCustomerEvidence,
    verify_customer_and_duplicates,
)
from sales_credit_evidence.one_draft_client import OneDraftClient
from sales_credit_evidence.transport import API_ORIGIN, HttpResponse, ReadError
from tests.test_sales_credit_evidence_coordinator import request
from tests.test_sales_credit_evidence_draft_preflight import (
    CREDENTIAL,
    EMAIL,
    NOW,
    Bundle,
    FakeHttp,
    conversation,
    page,
)
from tests.test_sales_credit_evidence_one_draft_client import (
    ROW,
    Evidence,
    Wire,
    draft_value,
    response,
)
from tests.test_sales_credit_evidence_one_draft_client import (
    Bundle as OutboundBundle,
)


def verify(fake, **kwargs):
    return verify_customer_and_duplicates(
        Bundle(), CREDENTIAL, transport=fake, clock=lambda: NOW, **kwargs
    )


def missing_customer_wire(conversations=()):
    fake = FakeHttp(conversations)
    fake.routes[("/v2/customers", 1)] = page("customers", [])
    return fake


def known_customer_wire(conversations=()):
    fake = FakeHttp(conversations)
    fake.routes[("/v2/customers/10", 0)] = {"id": 10}
    return fake


def test_explicit_id_uses_real_direct_get_and_email_verification_without_search():
    fake = known_customer_wire()
    evidence = verify(fake, known_customer_id=10)
    assert type(evidence) is DraftCustomerEvidence
    assert evidence.customer_id == 10
    assert [call[1] for call in fake.calls] == [
        "/v2/customers/10",
        "/v2/customers/10/emails",
        "/v2/conversations",
    ]
    assert fake.calls[-1][2]["query"] == ["(customerIds:10)"]
    assert fake.calls[-1][2]["mailbox"] == ["166170"]


@pytest.mark.parametrize("mode", ["wrong_id", "wrong_email", "http_error"])
def test_known_id_failure_never_falls_back_to_email_creation(mode):
    fake = known_customer_wire()
    expected = "draft_preflight_incomplete"
    if mode == "wrong_id":
        fake.routes[("/v2/customers/10", 0)] = {"id": 20}
    elif mode == "wrong_email":
        fake.routes[("/v2/customers/10/emails", 0)]["_embedded"]["emails"][0]["value"] = (
            "other@example.test"
        )
        expected = "draft_known_customer_identity_mismatch"
    else:
        fake.routes[("/v2/customers/10", 0)] = HttpResponse(403, {}, b"{}")
    with pytest.raises(ReadError, match=expected):
        verify(fake, known_customer_id=10)
    assert not any(call[1] == "/v2/customers" for call in fake.calls)
    assert all(call[0] == "GET" for call in fake.calls)


def test_empty_global_customer_and_complete_email_duplicates_need_explicit_row_grant():
    with pytest.raises(ReadError, match="draft_existing_customer_missing"):
        verify(missing_customer_wire())
    fake = missing_customer_wire()
    evidence = verify(fake, allow_email_customer=True)
    assert evidence.customer_id is None
    assert evidence.summary()["identity_status"] == "APPROVED_EMAIL_ONLY"
    assert evidence.summary()["customer_count"] == 0
    assert fake.calls[-1][2] == {
        "mailbox": ["166170"],
        "status": ["all"],
        "query": [f'(email:"{EMAIL}")'],
        "page": ["1"],
    }
    evidence.assert_for(Bundle())


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"state": "draft"}, "draft_existing_draft"),
        ({"subject": "Order 12345"}, "draft_existing_order_conversation"),
        ({}, "draft_email_identity_ambiguous"),
    ],
)
def test_missing_profile_with_existing_email_conversation_blocks(changes, code):
    with pytest.raises(ReadError, match=code):
        verify(missing_customer_wire([conversation(**changes)]), allow_email_customer=True)


def test_incomplete_duplicate_pages_do_not_authorize_email_mode():
    fake = missing_customer_wire()
    fake.routes[("/v2/conversations", 1)] = page("conversations", [], total=1)
    with pytest.raises(ReadError, match="draft_preflight_incomplete"):
        verify(fake, allow_email_customer=True)


def test_ambiguous_global_profiles_still_block_email_permission():
    fake = FakeHttp()
    fake.routes[("/v2/customers", 1)] = page("customers", [{"id": 10}, {"id": 11}])
    fake.routes[("/v2/customers/11/emails", 0)] = {
        "_embedded": {"emails": [{"id": 21, "value": EMAIL}]},
        "_links": {},
    }
    with pytest.raises(ReadError, match="draft_existing_customer_ambiguous"):
        verify(fake, allow_email_customer=True)


def email_evidence():
    bundle = OutboundBundle()

    def transport(method, url, headers):
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        assert method == "GET"
        if parsed.path == "/v2/customers":
            assert query == {"query": [f'(email:"{bundle.recipient}")'], "page": ["1"]}
            value = page("customers", [])
        else:
            assert parsed.path == "/v2/conversations"
            assert query["mailbox"] == ["166170"]
            value = page("conversations", [])
        return HttpResponse(200, {}, json.dumps(value).encode())

    evidence = verify_customer_and_duplicates(
        bundle, CREDENTIAL, transport=transport, clock=lambda: NOW, allow_email_customer=True
    )
    return bundle, evidence


def test_email_association_is_one_unsent_conversation_post_with_unchanged_copy():
    bundle, evidence = email_evidence()
    wire = Wire()
    client = OneDraftClient(bundle, evidence, CREDENTIAL, transport=wire, clock=lambda: NOW)
    client.check_destination()
    result = client.create_draft(ROW)
    assert result["state"] == "CREATED"
    assert result["retry_allowed"] is False
    assert [(call[0], call[1]) for call in wire.calls] == [
        ("GET", "/v2/mailboxes/166170"),
        ("GET", "/v2/users/897275"),
        ("POST", "/v2/conversations"),
        ("GET", "/v2/conversations/990002?embed=threads"),
    ]
    sent = wire.calls[2][2]
    assert sent["customer"] == {"email": ROW["recipient_email"]}
    assert sent["threads"][0]["customer"] == {"email": ROW["recipient_email"]}
    assert sent["threads"][0]["draft"] is True
    assert sent["autoReply"] is False
    assert sent["mailboxId"] == 166170
    assert sent["assignTo"] == sent["user"] == 897275
    assert not any(path == "/v2/customers" and method == "POST" for method, path, *_ in wire.calls)


def test_duck_typed_none_customer_does_not_grant_implicit_creation():
    with pytest.raises(Exception, match="ONE_DRAFT_SCOPE_INVALID"):
        OneDraftClient(OutboundBundle(), Evidence(customer_id=None), CREDENTIAL)


def test_existing_evidence_cannot_be_relabelled_as_email_creation_authority():
    evidence = verify(FakeHttp())
    object.__setattr__(evidence, "customer_id", None)
    with pytest.raises(ReadError, match="draft_email_creation_not_authorized"):
        evidence.assert_for(Bundle())


@pytest.mark.parametrize("outcome", [TimeoutError(), response(503), response(201)])
def test_uncertain_email_conversation_post_never_retries(outcome):
    bundle, evidence = email_evidence()
    wire = Wire([response(200, {"id": 166170}), response(200, {"id": 897275}), outcome])
    client = OneDraftClient(bundle, evidence, CREDENTIAL, transport=wire, clock=lambda: NOW)
    client.check_destination()
    result = client.create_draft(ROW)
    assert result["state"] == "UNKNOWN"
    assert result["retry_allowed"] is False
    assert client.create_draft(ROW)["retry_allowed"] is False
    assert sum(call[0] == "POST" for call in wire.calls) == 1


def test_email_readback_wrong_recipient_or_published_thread_is_not_success():
    bundle, evidence = email_evidence()
    for bad in ("recipient", "published"):
        value = copy.deepcopy(draft_value())
        if bad == "recipient":
            value["primaryCustomer"]["email"] = "different@example.test"
        else:
            value["_embedded"]["threads"][0]["state"] = "published"
        wire = Wire(
            [
                response(200, {"id": 166170}),
                response(200, {"id": 897275}),
                response(201, headers={"resource-id": "990002"}),
                response(200, value),
            ]
        )
        client = OneDraftClient(bundle, evidence, CREDENTIAL, transport=wire, clock=lambda: NOW)
        client.check_destination()
        assert client.create_draft(ROW)["state"] == "CREATED_UNVERIFIED"


@pytest.mark.parametrize(
    "changes",
    [
        {"known_customer_id": True},
        {"known_customer_id": 0},
        {"known_customer_id": 2**63},
        {"known_customer_id": 10, "allow_email_customer": True},
        {"allow_email_customer": "yes"},
    ],
)
def test_invalid_customer_selection_blocks_before_any_dependency(changes):
    result = coordinator.run_coordinator(replace(request(), **changes))
    assert result["issues"] == ["invalid_customer_scope"]
    assert result["issuance_attempted"] is False


def test_coordinator_returns_only_verified_safe_draft_link():
    value = {
        "state": "CREATED",
        "code": "DRAFT_CREATED_VERIFIED",
        "conversation_id": "990002",
        "web_link": API_ORIGIN.replace("api.", "secure.") + "/conversation/990002",
    }
    assert coordinator._draft_summary(value)["web_link"] == value["web_link"]
    assert "web_link" not in coordinator._draft_summary(dict(value, state="UNKNOWN"))
    assert "web_link" not in coordinator._draft_summary(
        dict(value, web_link=API_ORIGIN + "/conversation/990002")
    )


def test_cli_invalid_known_id_is_safe_and_default_off(capsys):
    assert coordinator.main(["--known-customer-id", "not-a-number"]) == 2
    assert json.loads(capsys.readouterr().out)["issues"] == ["invalid_arguments"]
    assert coordinator.main(["--known-customer-id", "10"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "DISABLED"


def test_transfer_review_discloses_contact_association_for_only_reviewed_row():
    from pathlib import Path

    text = (Path(__file__).parents[1] / "src/doi_draft_transfer/ui.html").read_text()
    assert 'id="transfer-customer-association"' in text
    assert "may create a contact for this approved email address" in text
    assert "only to this reviewed row" in text
