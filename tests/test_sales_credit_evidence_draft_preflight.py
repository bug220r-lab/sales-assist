"""Synthetic GET-only draft preflight: no credentials, files, or network."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from sales_credit_evidence.draft_preflight import (
    DraftCustomerEvidence,
    verify_customer_and_duplicates,
)
from sales_credit_evidence.transport import (
    API_ORIGIN,
    MAILBOX_ID,
    HttpResponse,
    ReadError,
    SuppliedCredential,
)

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)
EMAIL = "pilot@example.test"
SECRET = "synthetic-token"
CREDENTIAL = SuppliedCredential(SECRET, NOW + timedelta(hours=1))


@dataclass(frozen=True)
class Bundle:
    order_id: str = "12345"
    subject: str = "ORDER #12345 DELAY - SYNTHETIC"
    recipient: str = EMAIL
    bundle_sha256: str = "a" * 64


def page(key, records, *, number=1, total=None, size=25, next_page=False):
    total = len(records) if total is None else total
    return {
        "_embedded": {key: records},
        "page": {
            "number": number,
            "size": size,
            "totalElements": total,
            "totalPages": (total + size - 1) // size if total else 1,
        },
        "_links": (
            {"next": {"href": f"{API_ORIGIN}/v2/conversations?page={number + 1}"}}
            if next_page
            else {}
        ),
    }


def conversation(identifier=100, **changes):
    result = {
        "id": identifier,
        "subject": "Earlier synthetic inquiry",
        "number": identifier + 1000,
        "mailboxId": MAILBOX_ID,
        "primaryCustomer": {"id": 10, "email": EMAIL},
        "type": "email",
        "state": "published",
        "status": "closed",
        "threads": 0,
        "userUpdatedAt": "2026-10-01T16:00:00Z",
        "_links": {},
    }
    result.update(changes)
    return result


def thread(identifier=1000, **changes):
    result = {
        "id": identifier,
        "type": "note",
        "state": "published",
        "status": "active",
        "createdAt": "2026-10-01T14:00:00Z",
        "body": "Private synthetic text that must not escape.",
    }
    result.update(changes)
    return result


class FakeHttp:
    def __init__(self, conversations=()):
        self.calls = []
        self.routes = {
            ("/v2/customers", 1): page("customers", [{"id": 10}]),
            ("/v2/customers/10/emails", 0): {
                "_embedded": {"emails": [{"id": 20, "value": EMAIL}]},
                "_links": {},
            },
            ("/v2/conversations", 1): page("conversations", list(conversations)),
        }
        for item in conversations:
            self.add_conversation(item)

    def add_conversation(self, item, threads=()):
        identifier = item["id"]
        self.routes[(f"/v2/conversations/{identifier}", 0)] = item
        self.routes[(f"/v2/conversations/{identifier}/threads", 1)] = page("threads", list(threads))

    def __call__(self, method, url, headers):
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        key = parsed.path, int(query.get("page", [0])[0])
        self.calls.append((method, parsed.path, query))
        assert method == "GET"
        assert headers["Authorization"] == f"Bearer {SECRET}"
        value = self.routes[key]
        if isinstance(value, list):
            value = value.pop(0)
        if isinstance(value, HttpResponse):
            return value
        return HttpResponse(200, {}, json.dumps(value).encode())


def verify(fake, *, bundle=None, clock=lambda: NOW, credential=CREDENTIAL):
    return verify_customer_and_duplicates(
        Bundle() if bundle is None else bundle,
        credential,
        transport=fake,
        clock=clock,
    )


def blocked(fake, code, **options):
    with pytest.raises(ReadError, match=f"^{code}$") as caught:
        verify(fake, **options)
    assert EMAIL not in repr(caught.value)
    assert SECRET not in repr(caught.value)
    return caught.value


def test_exact_existing_customer_no_conversations_mints_scoped_proof():
    fake = FakeHttp()
    evidence = verify(fake)
    assert type(evidence) is DraftCustomerEvidence
    assert evidence.customer_id == 10
    assert evidence.recipient == EMAIL
    assert evidence.bundle_sha256 == Bundle().bundle_sha256
    evidence.assert_for(Bundle())
    assert evidence.summary() == {
        "identity_status": "EXACT",
        "complete": True,
        "customer_count": 1,
        "conversation_count": 0,
        "thread_count": 0,
        "duplicate_check": "NO_MATCH_IN_ACCESSIBLE_MAILBOX_SNAPSHOT",
    }
    assert EMAIL not in repr(evidence)
    assert SECRET not in repr(evidence)
    assert len(fake.calls) == 3
    assert fake.calls[-1][2]["status"] == ["all"]


def test_direct_construction_cannot_skip_verified_customer_checks():
    with pytest.raises(ReadError, match="draft_evidence_not_verified"):
        DraftCustomerEvidence()
    with pytest.raises(ReadError, match="draft_evidence_not_verified"):
        DraftCustomerEvidence(customer_id=10, recipient=EMAIL)


def test_nonmatching_history_keeps_full_thread_count_without_private_content():
    item = conversation(threads=1)
    fake = FakeHttp([item])
    fake.add_conversation(item, [thread(), thread(1001, type="lineitem")])
    evidence = verify(fake)
    assert evidence.summary()["conversation_count"] == 1
    assert evidence.summary()["thread_count"] == 2
    assert "Private synthetic" not in repr(evidence)
    assert "Earlier synthetic" not in repr(evidence)
    assert len(fake.calls) == 6


def test_existing_customer_must_exist_and_no_mutation_occurs():
    fake = FakeHttp()
    fake.routes[("/v2/customers", 1)] = page("customers", [])
    blocked(fake, "draft_existing_customer_missing")
    assert len(fake.calls) == 1


def test_substring_search_hit_is_not_exact_customer():
    fake = FakeHttp()
    fake.routes[("/v2/customers/10/emails", 0)]["_embedded"]["emails"][0]["value"] = (
        "prefix" + EMAIL
    )
    blocked(fake, "draft_existing_customer_missing")
    assert len(fake.calls) == 2


def test_multiple_exact_native_customers_are_blocked():
    fake = FakeHttp()
    fake.routes[("/v2/customers", 1)] = page("customers", [{"id": 10}, {"id": 11}])
    fake.routes[("/v2/customers/11/emails", 0)] = {
        "_embedded": {"emails": [{"id": 21, "value": EMAIL}]},
        "_links": {},
    }
    blocked(fake, "draft_existing_customer_ambiguous")
    assert len(fake.calls) == 3


def test_aliases_cannot_silently_change_id_based_draft_recipient():
    fake = FakeHttp()
    fake.routes[("/v2/customers/10/emails", 0)]["_embedded"]["emails"].append(
        {"id": 21, "value": "alias@example.test"}
    )
    blocked(fake, "draft_customer_email_ambiguous")


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_http_failures_never_retry_or_mint_evidence(status):
    fake = FakeHttp()
    fake.routes[("/v2/customers", 1)] = HttpResponse(status, {}, b"{}")
    blocked(fake, "draft_preflight_incomplete")
    assert len(fake.calls) == 1


def test_incomplete_conversation_pagination_blocks_absence_claim():
    fake = FakeHttp([conversation()])
    fake.routes[("/v2/conversations", 1)] = page("conversations", [conversation()], total=2)
    blocked(fake, "draft_preflight_incomplete")


@pytest.mark.parametrize("state", ["draft", "published", "deleted"])
def test_all_conversation_states_checked_for_order_subjects(state):
    fake = FakeHttp([conversation(state=state, subject="Re: Order 12345")])
    code = "draft_existing_draft" if state == "draft" else "draft_existing_order_conversation"
    blocked(fake, code)


def test_approved_subject_matches_casefold_and_whitespace_even_without_order():
    fake = FakeHttp([conversation(subject="  A CUSTOM   SUBJECT  ")])
    blocked(
        fake,
        "draft_existing_order_conversation",
        bundle=replace(Bundle(), subject="a custom subject"),
    )


def test_order_digits_do_not_match_part_of_an_unrelated_longer_number():
    fake = FakeHttp([conversation(subject="Earlier order 9123456")])
    verify(fake)


def test_any_existing_draft_blocks_even_with_different_subject():
    blocked(FakeHttp([conversation(state="draft")]), "draft_existing_draft")


def test_duplicate_on_later_conversation_page_blocks():
    first = conversation()
    second = conversation(101, subject="ORDER #12345 FOLLOW UP")
    fake = FakeHttp([first, second])
    fake.routes[("/v2/conversations", 1)] = page(
        "conversations", [first], total=2, size=1, next_page=True
    )
    fake.routes[("/v2/conversations", 2)] = page(
        "conversations", [second], number=2, total=2, size=1
    )
    blocked(fake, "draft_existing_order_conversation")
    assert any(
        path == "/v2/conversations" and query["page"] == ["2"] for _, path, query in fake.calls
    )


@pytest.mark.parametrize("kind", ["message", "note", "forwardchild", "unknown"])
def test_draft_thread_blocks_without_credit_filtering(kind):
    item = conversation(threads=1)
    fake = FakeHttp([item])
    fake.add_conversation(item, [thread(type=kind, state="draft")])
    blocked(fake, "draft_existing_draft")


def test_draft_on_later_thread_page_blocks():
    item = conversation(threads=2)
    fake = FakeHttp([item])
    first = page("threads", [thread()], total=2, size=1)
    first["_links"] = {"next": {"href": f"{API_ORIGIN}/v2/conversations/100/threads?page=2"}}
    fake.routes[("/v2/conversations/100/threads", 1)] = first
    fake.routes[("/v2/conversations/100/threads", 2)] = page(
        "threads", [thread(1001, state="draft")], number=2, total=2, size=1
    )
    blocked(fake, "draft_existing_draft")


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("subject", None),
        ("subject", ""),
        ("subject", "\r\nInjected"),
        ("subject", "a" * 999),
        ("subject", 12345),
        ("state", None),
        ("state", "unknown"),
        ("state", []),
        ("status", "unknown"),
        ("mailboxId", True),
        ("id", True),
        ("primaryCustomer", {"id": True, "email": EMAIL}),
        ("primaryCustomer", {"id": 10}),
        ("primaryCustomer", {"id": 10, "email": "alias@example.test"}),
    ],
)
def test_invalid_conversation_metadata_never_proves_duplicate_absence(key, value):
    fake = FakeHttp([conversation(**{key: value})])
    blocked(fake, "draft_preflight_incomplete")


@pytest.mark.parametrize("phase", ["detail", "recheck"])
def test_subject_changes_between_list_detail_and_recheck_block(phase):
    item = conversation()
    fake = FakeHttp([item])
    changed = deepcopy(item)
    changed["subject"] = "Changed subject"
    fake.routes[("/v2/conversations/100", 0)] = changed if phase == "detail" else [item, changed]
    blocked(fake, "draft_preflight_incomplete")


def test_unknown_thread_state_blocks_duplicate_absence():
    item = conversation(threads=1)
    fake = FakeHttp([item])
    fake.add_conversation(item, [thread(state=None)])
    blocked(fake, "draft_preflight_incomplete")


def test_published_non_note_count_must_match_native_conversation_count():
    item = conversation(threads=2)
    fake = FakeHttp([item])
    fake.add_conversation(item, [thread(type="message")])
    blocked(fake, "draft_preflight_incomplete")


def test_notes_and_deleted_threads_do_not_inflate_native_published_count():
    item = conversation(threads=1)
    fake = FakeHttp([item])
    fake.add_conversation(
        item,
        [
            thread(type="message"),
            thread(1001, type="note"),
            thread(1002, type="message", state="deleted"),
        ],
    )
    assert verify(fake).summary()["thread_count"] == 3


def test_draft_detection_precedes_a_native_thread_count_mismatch():
    item = conversation(threads=7)
    fake = FakeHttp([item])
    fake.add_conversation(item, [thread(state="draft")])
    blocked(fake, "draft_existing_draft")


def test_default_transport_wires_scoped_live_client_without_network(monkeypatch):
    import sales_credit_evidence.draft_preflight as preflight

    original_client = preflight._ObservingClient
    fake = FakeHttp()
    constructed = []

    def controlled_client(*args, **kwargs):
        constructed.append((args, kwargs.copy()))
        assert kwargs["transport"] is None
        kwargs["transport"] = fake
        return original_client(*args, **kwargs)

    monkeypatch.setattr(preflight, "_ObservingClient", controlled_client)
    evidence = verify_customer_and_duplicates(Bundle(), CREDENTIAL, clock=lambda: NOW)
    assert len(constructed) == 1
    args, options = constructed[0]
    assert args == (EMAIL,)
    assert options["credential"] is CREDENTIAL
    assert options["enable_live"] is True
    assert options["max_attempts"] == 1
    assert options["expiry_margin_seconds"] == 120
    assert evidence.summary()["duplicate_check"] == "NO_MATCH_IN_ACCESSIBLE_MAILBOX_SNAPSHOT"
    assert len(fake.calls) == 3


def test_request_budget_is_bounded_and_cannot_claim_complete():
    fake = FakeHttp([conversation(100 + index) for index in range(17)])
    blocked(fake, "draft_preflight_incomplete")
    assert len(fake.calls) == 50


def test_expiry_margin_blocks_first_http():
    fake = FakeHttp()
    blocked(
        fake,
        "draft_preflight_incomplete",
        credential=SuppliedCredential(SECRET, NOW + timedelta(seconds=120)),
    )
    assert not fake.calls


def test_expiry_margin_during_reads_halts_further_http():
    times = iter([NOW, NOW, NOW + timedelta(seconds=1), NOW + timedelta(hours=1)])
    fake = FakeHttp()
    blocked(fake, "draft_preflight_incomplete", clock=lambda: next(times))
    assert len(fake.calls) == 2


def test_slow_snapshot_cannot_mint_recent_evidence_from_old_identity_read():
    now = [NOW]
    fake = FakeHttp()

    def slow_transport(method, url, headers):
        response = fake(method, url, headers)
        now[0] += timedelta(seconds=50)
        return response

    blocked(slow_transport, "draft_evidence_stale", clock=lambda: now[0])
    assert len(fake.calls) == 3


@pytest.mark.parametrize("delta", [-1, 120, 121])
def test_minted_evidence_expiry_and_clock_rollback_block(delta):
    now = [NOW]
    evidence = verify(FakeHttp(), clock=lambda: now[0])
    now[0] = NOW + timedelta(seconds=delta)
    with pytest.raises(ReadError, match="draft_evidence_stale"):
        evidence.assert_for(Bundle())


def test_minted_evidence_naive_clock_blocks():
    now = [NOW]
    evidence = verify(FakeHttp(), clock=lambda: now[0])
    now[0] = NOW.replace(tzinfo=None)
    with pytest.raises(ReadError, match="draft_evidence_stale"):
        evidence.assert_for(Bundle())


@pytest.mark.parametrize(
    "bundle",
    [replace(Bundle(), bundle_sha256="b" * 64), replace(Bundle(), recipient="other@example.test")],
)
def test_evidence_is_bound_to_exact_bundle_digest_and_recipient(bundle):
    evidence = verify(FakeHttp())
    with pytest.raises(ReadError, match="draft_evidence_bundle_mismatch"):
        evidence.assert_for(bundle)


@pytest.mark.parametrize(
    "bundle",
    [
        None,
        {},
        replace(Bundle(), recipient="invalid"),
        replace(Bundle(), order_id=""),
        replace(Bundle(), order_id=True),
        replace(Bundle(), bundle_sha256="A" * 64),
        replace(Bundle(), bundle_sha256="short"),
        replace(Bundle(), subject=""),
    ],
)
def test_invalid_bundle_blocks_before_any_http(bundle):
    fake = FakeHttp()
    with pytest.raises(ReadError, match="draft_bundle_invalid"):
        verify_customer_and_duplicates(bundle, CREDENTIAL, transport=fake, clock=lambda: NOW)
    assert not fake.calls
