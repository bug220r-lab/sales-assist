"""Synthetic draft replies use the documented customer association, not input To."""

import pytest

from doi_draft_transfer.helpscout import HelpScoutDraftClient, payload_for
from tests.test_sales_credit_evidence_one_draft_client import (
    CONVERSATION,
    CUSTOMER,
    ROW,
    Wire,
    client,
    draft_value,
    response,
)


def associated_draft():
    value = draft_value()
    value["_embedded"]["threads"][0].update(
        to=[], customer={"id": CUSTOMER, "email": ROW["recipient_email"]}
    )
    return value


def run_readback(value):
    wire = Wire()
    wire.replies[-1] = response(200, value)
    instance, wire = client(wire)
    instance.check_destination()
    result = instance.create_draft(ROW)
    assert len(wire.calls) == 4
    assert result["conversation_id"] == str(CONVERSATION)
    assert result["retry_allowed"] is False
    return result, wire


def test_customer_is_the_only_documented_reply_recipient_input():
    payload = payload_for(ROW)
    assert payload["customer"] == payload["threads"][0]["customer"] == {
        "email": ROW["recipient_email"]
    }
    assert "to" not in payload and "to" not in payload["threads"][0]
    result, wire = run_readback(associated_draft())
    assert result["state"] == "CREATED"
    posted = wire.calls[2][2]
    assert posted["customer"] == posted["threads"][0]["customer"] == {"id": CUSTOMER}
    assert "to" not in posted["threads"][0]
    assert posted["threads"][0]["draft"] is True and posted["autoReply"] is False


@pytest.mark.parametrize("omit_to", [False, True])
def test_empty_or_omitted_draft_to_needs_exact_customer_association(omit_to):
    value = associated_draft()
    if omit_to:
        value["_embedded"]["threads"][0].pop("to")
    result, _wire = run_readback(value)
    assert result["state"] == "CREATED"


@pytest.mark.parametrize(
    "customer",
    [
        None,
        {},
        [],
        {"id": CUSTOMER},
        {"email": ROW["recipient_email"]},
        {"id": str(CUSTOMER), "email": ROW["recipient_email"]},
        {"id": True, "email": ROW["recipient_email"]},
        {"id": CUSTOMER + 1, "email": ROW["recipient_email"]},
        {"id": CUSTOMER, "email": "different@example.test"},
        {"id": CUSTOMER, "email": None},
    ],
)
def test_empty_to_without_complete_matching_customer_remains_unverified(customer):
    value = associated_draft()
    value["_embedded"]["threads"][0]["customer"] = customer
    result, _wire = run_readback(value)
    assert result["state"] == "CREATED_UNVERIFIED"


@pytest.mark.parametrize(
    "recipients",
    [None, {}, "approved@example.test", ["different@example.test"],
     [ROW["recipient_email"], "extra@example.test"], [ROW["recipient_email"]] * 2],
)
def test_explicit_malformed_or_contradictory_to_is_never_ignored(recipients):
    value = associated_draft()
    value["_embedded"]["threads"][0]["to"] = recipients
    result, _wire = run_readback(value)
    assert result["state"] == "CREATED_UNVERIFIED"


def test_correct_to_cannot_override_contradictory_customer_association():
    value = associated_draft()
    value["_embedded"]["threads"][0].update(
        to=[ROW["recipient_email"]],
        customer={"id": CUSTOMER + 1, "email": ROW["recipient_email"]},
    )
    result, _wire = run_readback(value)
    assert result["state"] == "CREATED_UNVERIFIED"


def test_known_customer_guard_still_blocks_different_native_identity():
    value = associated_draft()
    value["primaryCustomer"]["id"] = CUSTOMER + 1
    value["_embedded"]["threads"][0]["customer"]["id"] = CUSTOMER + 1
    result, _wire = run_readback(value)
    assert result["state"] == "CREATED_UNVERIFIED"


@pytest.mark.parametrize("field,value", [
    ("state", "published"), ("cc", ["extra@example.test"]),
    ("bcc", ["extra@example.test"]), ("scheduled", {"scheduledFor": "2030-01-01T00:00:00Z"}),
    ("body", "Unapproved synthetic copy"),
])
def test_customer_association_preserves_all_other_draft_checks(field, value):
    document = associated_draft()
    document["_embedded"]["threads"][0][field] = value
    result, _wire = run_readback(document)
    assert result["state"] == "CREATED_UNVERIFIED"


def legacy_readback(value):
    instance = object.__new__(HelpScoutDraftClient)
    calls = []
    def request(method, path):
        calls.append((method, path))
        return response(200, value)
    instance._request = request
    result = instance.verify_draft(ROW, {"conversation_id": str(CONVERSATION)})
    assert calls == [("GET", f"/v2/conversations/{CONVERSATION}?embed=threads")]
    assert result["retry_allowed"] is False
    return result


def test_read_only_legacy_verification_uses_same_customer_predicate():
    assert legacy_readback(associated_draft())["state"] == "CREATED"


@pytest.mark.parametrize(
    "primary",
    [
        None,
        {},
        {"email": ROW["recipient_email"]},
        {"id": None, "email": ROW["recipient_email"]},
        {"id": 0, "email": ROW["recipient_email"]},
        {"id": -1, "email": ROW["recipient_email"]},
        {"id": 2**63, "email": ROW["recipient_email"]},
        {"id": True, "email": ROW["recipient_email"]},
        {"id": str(CUSTOMER), "email": ROW["recipient_email"]},
        {"id": CUSTOMER, "email": "different@example.test"},
        {"id": CUSTOMER, "email": None},
    ],
)
def test_legacy_empty_to_cannot_verify_missing_or_invalid_primary_customer(primary):
    value = associated_draft()
    value["primaryCustomer"] = primary
    assert legacy_readback(value)["state"] == "CREATED_UNVERIFIED"
