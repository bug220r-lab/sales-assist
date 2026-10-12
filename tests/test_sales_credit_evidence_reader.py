"""Synthetic fake-HTTP evidence tests; no live client, token, cache, or source data."""

from __future__ import annotations

import json
from copy import deepcopy
from urllib.parse import parse_qs, urlsplit

import pytest

from sales_credit_evidence.reader import EvidenceReader
from sales_credit_evidence.transport import (
    API_ORIGIN,
    MAILBOX_ID,
    TARGET_AUTHOR_ID,
    HttpResponse,
    ReadClient,
)

EMAIL = "review+synthetic@example.test"
ALIAS = "alias@example.test"
CUSTOMER = 10
CONVERSATION = 100
CREATED = "2026-10-01T14:00:00Z"


def page(key, records, *, number=1, total=None, size=50, next_url=None):
    total = len(records) if total is None else total
    return {
        "_embedded": {key: records},
        "page": {
            "number": number,
            "size": size,
            "totalElements": total,
            "totalPages": (total + size - 1) // size if total else 1,
        },
        "_links": {} if next_url is None else {"next": {"href": next_url}},
    }


def email_record(identifier=20, value=EMAIL):
    return {"id": identifier, "value": value, "type": "work"}


def email_collection(records, customer_id=CUSTOMER):
    """Official email endpoint returns an unpaginated HAL collection."""
    return {
        "_embedded": {"emails": records},
        "_links": {"self": {"href": f"{API_ORIGIN}/v2/customers/{customer_id}/emails"}},
    }


def conversation(identifier=CONVERSATION, **changes):
    result = {
        "id": identifier,
        "number": identifier + 1000,
        "mailboxId": MAILBOX_ID,
        "primaryCustomer": {"id": CUSTOMER, "email": EMAIL},
        "type": "email",
        "state": "published",
        "status": "closed",
        "threads": 2,
        "userUpdatedAt": "2026-10-01T16:00:00Z",
        "assignee": {"id": TARGET_AUTHOR_ID},
        "_links": {"web": {"href": f"https://secure.helpscout.net/conversation/{identifier}/"}},
    }
    result.update(changes)
    return result


def thread(identifier=1000, *, incoming=False, **changes):
    result = {
        "id": identifier,
        "type": "customer" if incoming else "message",
        "state": "published",
        "status": "active",
        "createdBy": {
            "id": CUSTOMER if incoming else TARGET_AUTHOR_ID,
            "type": "customer" if incoming else "user",
            "email": EMAIL if incoming else "rep@example.test",
        },
        "customer": {"id": CUSTOMER},
        "source": {"type": "email", "via": "customer" if incoming else "user"},
        "to": ["rep@example.test"] if incoming else [EMAIL],
        "createdAt": CREATED,
        "body": "<p>Synthetic confidential body for privacy verification.</p>",
    }
    result.update(changes)
    return result


class FakeHttp:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.unexpected = []

    def __call__(self, method, url, headers):
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        key = (parsed.path, int(query.get("page", [0])[0]))
        self.calls.append((method, parsed, query, headers))
        if key not in self.routes:
            self.unexpected.append(key)
            return HttpResponse(418, {}, b"{}")
        value = self.routes[key]
        if isinstance(value, list):
            value = value.pop(0)
        if isinstance(value, HttpResponse):
            return value
        return HttpResponse(200, {}, json.dumps(value).encode())


def setup_reader(*, threads=(), conversations=None, emails=None, **options):
    conversations = [conversation()] if conversations is None else conversations
    routes = {
        ("/v2/customers", 1): page("customers", [{"id": CUSTOMER}]),
        (f"/v2/customers/{CUSTOMER}/emails", 0): email_collection(
            [email_record()] if emails is None else emails,
        ),
        ("/v2/conversations", 1): page("conversations", conversations, size=25),
    }
    for item in conversations:
        identifier = item["id"]
        routes[(f"/v2/conversations/{identifier}", 0)] = item
        routes[(f"/v2/conversations/{identifier}/threads", 1)] = page(
            "threads",
            list(threads),
        )
    fake = FakeHttp(routes)
    client = ReadClient(EMAIL, transport=fake, max_attempts=1, sleeper=lambda _: None)
    return EvidenceReader(client, **options), fake


def all_threads(result):
    return [item for convo in result.conversations for item in convo.threads]


def codes(result):
    return {item.code for item in result.issues}


def test_exact_identity_uses_dedicated_emails_and_casefold_not_search_hit():
    reader, fake = setup_reader(conversations=[])
    fake.routes[("/v2/customers", 1)] = page(
        "customers",
        [
            {"id": CUSTOMER, "emails": [{"value": "untrusted@example.test"}]},
            {"id": 11, "email": EMAIL},
        ],
    )
    fake.routes[(f"/v2/customers/{CUSTOMER}/emails", 0)] = email_collection(
        [
            email_record(value="  REVIEW+SYNTHETIC@EXAMPLE.TEST  "),
            email_record(21, ALIAS),
        ],
    )
    fake.routes[("/v2/customers/11/emails", 0)] = email_collection(
        [
            email_record(22, "prefixreview+synthetic@example.test"),
        ],
        customer_id=11,
    )
    result = reader.read()
    assert result.identity_status == "EXACT"
    assert result.customers[0].emails == (ALIAS, EMAIL)
    assert result.customers[0].email_ids == (20, 21)
    assert result.complete and result.no_result
    assert result.summary()["no_scoped_conversations"] is True
    assert fake.unexpected == []
    for method, parsed, query, headers in fake.calls:
        assert method == "GET" and parsed.netloc == "api.helpscout.net"
        assert "Authorization" not in headers
        if parsed.path == "/v2/customers":
            assert query == {
                "mailbox": [str(MAILBOX_ID)],
                "query": [f'(email:"{EMAIL}")'],
                "page": ["1"],
            }
        if parsed.path == "/v2/conversations":
            assert query == {
                "mailbox": [str(MAILBOX_ID)],
                "status": ["all"],
                "query": ["(customerIds:10)"],
                "page": ["1"],
            }
        if parsed.path.endswith("/emails"):
            assert not parsed.query and query == {}


def test_substring_or_removed_plus_is_not_exact_identity():
    reader, fake = setup_reader(
        emails=[
            email_record(value="prefix" + EMAIL),
            email_record(21, "review@example.test"),
        ]
    )
    result = reader.read()
    assert result.identity_status == "NO_EXACT_CUSTOMER"
    assert result.complete and not result.no_result
    assert result.summary()["no_scoped_conversations"] is False
    assert not any(call[1].path == "/v2/conversations" for call in fake.calls)


def test_duplicate_exact_customers_are_ambiguous_and_block_conversation_reads():
    reader, fake = setup_reader()
    fake.routes[("/v2/customers", 1)] = page("customers", [{"id": 10}, {"id": 11}])
    fake.routes[("/v2/customers/11/emails", 0)] = email_collection(
        [email_record(21)], customer_id=11
    )
    result = reader.read()
    assert result.identity_status == "AMBIGUOUS"
    assert [item.customer_id for item in result.customers] == [10, 11]
    assert not result.complete and not result.no_result
    assert "MULTIPLE_EXACT_CUSTOMERS" in codes(result)
    assert not any("conversations" in call[1].path for call in fake.calls)


def test_multiple_emails_are_retrieved_from_unpaginated_dedicated_endpoint():
    reader, fake = setup_reader(conversations=[])
    path = f"/v2/customers/{CUSTOMER}/emails"
    aliases = [email_record(100 + i, f"alias{i}@example.test") for i in range(50)]
    fake.routes[(path, 0)] = email_collection(
        [*aliases, email_record()],
    )
    result = reader.read()
    assert result.identity_status == "EXACT" and result.complete
    assert len(result.customers[0].emails) == 51
    assert next(c for c in result.coverage if c.stage == "customer_emails").pages == 1
    email_calls = [call for call in fake.calls if call[1].path == path]
    assert len(email_calls) == 1 and not email_calls[0][1].query
    assert fake.unexpected == []


@pytest.mark.parametrize(
    "document",
    [
        {"_embedded": {"customers": []}},
        page("customers", [], total=1),
        {"_embedded": {"customers": []}, "page": None},
    ],
)
def test_no_result_requires_complete_successful_customer_search(document):
    reader, fake = setup_reader()
    fake.routes[("/v2/customers", 1)] = document
    result = reader.read()
    assert result.identity_status == "INCOMPLETE"
    assert not result.complete and not result.no_result and result.issues


def test_complete_zero_customer_search_reports_only_no_exact_identity():
    reader, fake = setup_reader()
    fake.routes[("/v2/customers", 1)] = page("customers", [])
    result = reader.read()
    assert result.identity_status == "NO_EXACT_CUSTOMER"
    assert result.complete and not result.no_result
    assert result.summary()["no_scoped_conversations"] is False
    assert len(fake.calls) == 1


@pytest.mark.parametrize(
    "changes,issue",
    [
        ({"mailboxId": 555}, "MAILBOX_SCOPE_MISMATCH"),
        ({"primaryCustomer": {"id": 11, "email": EMAIL}}, "CONVERSATION_IDENTITY_MISMATCH"),
        (
            {"primaryCustomer": {"id": CUSTOMER, "email": "other@example.test"}},
            "CONVERSATION_IDENTITY_MISMATCH",
        ),
    ],
)
def test_unrelated_conversation_is_excluded_before_detail_or_history(changes, issue):
    reader, fake = setup_reader(conversations=[conversation(**changes)])
    result = reader.read()
    assert not result.conversations and issue in codes(result)
    assert not result.no_result and not result.complete
    assert not any(call[1].path.startswith("/v2/conversations/") for call in fake.calls)


def test_detail_scope_is_revalidated_before_fetching_threads():
    reader, fake = setup_reader()
    fake.routes[("/v2/conversations/100", 0)] = conversation(mailboxId=555)
    result = reader.read()
    assert not result.conversations and "MAILBOX_SCOPE_MISMATCH" in codes(result)
    assert not any(call[1].path.endswith("/threads") for call in fake.calls)


def test_author_is_created_by_not_assignee_or_assigned_to():
    reader, _ = setup_reader(
        threads=[
            thread(
                1000, createdBy={"id": 888, "type": "user"}, assignedTo={"id": TARGET_AUTHOR_ID}
            ),
            thread(1001, assignedTo={"id": 888}),
        ]
    )
    result = reader.read()
    first, second = all_threads(result)
    assert first.observed_role == "OTHER_AUTHOR_OUTBOUND"
    assert first.author_id == 888 and first.assigned_to_id == TARGET_AUTHOR_ID
    assert second.observed_role == "TARGET_PUBLISHED_OUTBOUND_CANDIDATE"
    assert second.author_id == TARGET_AUTHOR_ID and second.assigned_to_id == 888
    assert result.credit_classification == "NOT_EVALUATED"


@pytest.mark.parametrize(
    "changes,role",
    [
        ({"state": "draft"}, "EXCLUDED_NOT_PUBLISHED"),
        ({"state": "bounced"}, "EXCLUDED_NOT_PUBLISHED"),
        ({"state": "hidden"}, "EXCLUDED_NOT_PUBLISHED"),
        ({"state": "review"}, "EXCLUDED_NOT_PUBLISHED"),
        ({"state": "underreview"}, "EXCLUDED_NOT_PUBLISHED"),
        ({"type": "note"}, "EXCLUDED_NON_REPLY"),
        ({"type": "lineitem"}, "EXCLUDED_NON_REPLY"),
        ({"type": "forwardchild"}, "EXCLUDED_NON_REPLY"),
        ({"type": "forwardparent"}, "EXCLUDED_NON_REPLY"),
        ({"autoReply": True}, "EXCLUDED_AUTOMATED"),
        ({"source": {"type": "workflows", "via": "user"}}, "EXCLUDED_AUTOMATED"),
        ({"source": {"type": "notification", "via": "user"}}, "EXCLUDED_AUTOMATED"),
        ({"source": {"type": "orchestration", "via": "user"}}, "EXCLUDED_AUTOMATED"),
        ({"source": {"type": "api", "via": "user"}}, "IMPORTED_OR_UNKNOWN_PROVENANCE_REVIEW"),
        ({"source": {}}, "IMPORTED_OR_UNKNOWN_PROVENANCE_REVIEW"),
        ({"scheduled": {"time": "2026-10-01T16:00:00Z"}}, "EXCLUDED_SCHEDULED_OR_UNCERTAIN"),
        ({"scheduled": False}, "EXCLUDED_SCHEDULED_OR_UNCERTAIN"),
    ],
)
def test_draft_note_automation_import_and_uncertain_threads_do_not_prove_outbound(changes, role):
    reader, _ = setup_reader(threads=[thread(**changes)])
    result = reader.read()
    evidence = all_threads(result)[0]
    assert evidence.observed_role == role
    assert not evidence.send_time_verified and not evidence.delivery_verified
    assert evidence.prior_target_thread_ids == ()
    assert result.credit_classification == "NOT_EVALUATED"


@pytest.mark.parametrize(
    "changes",
    [
        {"to": ["other@example.test"]},
        {"to": []},
        {"customer": {"id": 11}},
    ],
)
def test_outbound_requires_customer_and_exact_recipient_identity(changes):
    reader, _ = setup_reader(threads=[thread(**changes)])
    evidence = all_threads(reader.read())[0]
    assert evidence.observed_role == "IDENTITY_UNPROVED" and not evidence.identity_proved


def test_source_proven_customer_alias_is_allowed_as_recipient():
    reader, _ = setup_reader(
        emails=[email_record(), email_record(21, ALIAS)],
        threads=[thread(to=[ALIAS])],
    )
    evidence = all_threads(reader.read())[0]
    assert evidence.observed_role == "TARGET_PUBLISHED_OUTBOUND_CANDIDATE"
    assert evidence.matched_recipient_emails == (ALIAS,)


def test_incoming_association_requires_strictly_earlier_same_conversation():
    reader, fake = setup_reader(
        threads=[
            thread(1000),
            thread(1001, incoming=True, createdAt="2026-10-01T13:59:59Z"),
            thread(1002, incoming=True),
            thread(1003, incoming=True, createdAt="2026-10-01T14:00:01Z"),
        ],
        conversations=[conversation(), conversation(101)],
    )
    fake.routes[("/v2/conversations/101/threads", 1)] = page(
        "threads",
        [
            thread(1004, incoming=True, createdAt="2026-10-01T15:00:00Z"),
        ],
    )
    result = reader.read(order_placed_at="2026-10-01T14:00:01Z")
    facts = {item.thread_id: item for item in all_threads(result)}
    assert result.complete
    assert facts[1003].prior_target_thread_ids == (1000,)
    assert (
        facts[1003].association_basis == "SAME_CUSTOMER_CONVERSATION_EARLIER_SOURCE_CREATION_ONLY"
    )
    for identifier in (1000, 1001, 1002, 1004):
        assert facts[identifier].prior_target_thread_ids == ()
    assert facts[1000].source_creation_vs_order == "SOURCE_CREATED_BEFORE_ORDER"
    assert facts[1003].source_creation_vs_order == "SOURCE_CREATED_AT_OR_AFTER_ORDER"
    assert all(item.relevance == "NOT_ASSESSED" for item in facts.values())
    assert all(
        not item.send_time_verified and not item.delivery_verified for item in facts.values()
    )
    assert result.credit_classification == "NOT_EVALUATED"


@pytest.mark.parametrize(
    "created_by",
    [
        {"id": 11, "type": "customer", "email": EMAIL},
        {"id": CUSTOMER, "type": "user", "email": EMAIL},
        {"id": CUSTOMER, "type": "customer", "email": "other@example.test"},
        {"id": CUSTOMER, "type": "customer"},
    ],
)
def test_incoming_requires_author_identity_not_only_conversation_membership(created_by):
    reader, _ = setup_reader(threads=[thread(incoming=True, createdBy=created_by)])
    evidence = all_threads(reader.read())[0]
    assert evidence.observed_role == "IDENTITY_UNPROVED" and not evidence.identity_proved


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "2026-10-01",
        "2026-10-01T14:00:00",
        "2026-10-01T10:00:00-04:00",
        "2026-10-01T14:00:00.123Z",
        "2026-02-30T14:00:00Z",
        "not-a-time",
    ],
)
def test_missing_or_noncontract_timestamp_never_gains_precision(raw):
    reader, _ = setup_reader(threads=[thread(createdAt=raw)])
    evidence = all_threads(reader.read(order_placed_at=CREATED))[0]
    assert evidence.timestamp_precision == "UNKNOWN"
    assert evidence.raw_created_at == raw
    assert evidence.timestamp_parse_issue is not None
    assert evidence.observed_role == "TIMESTAMP_UNPROVED"
    assert evidence.source_creation_vs_order == "UNKNOWN"
    assert not evidence.send_time_verified and not evidence.delivery_verified


def test_valid_timestamp_preserves_seconds_but_never_claims_send_verification():
    reader, _ = setup_reader(threads=[thread()])
    evidence = all_threads(reader.read())[0]
    assert evidence.created_at == CREATED and evidence.timestamp_precision == "SOURCE_SECOND"
    assert evidence.raw_created_at == CREATED and evidence.timestamp_parse_issue is None
    assert evidence.source_creation_vs_order == "NOT_COMPARED"
    assert not evidence.send_time_verified
    assert evidence.source_link == "https://secure.helpscout.net/conversation/100/"


def test_invalid_order_timestamp_fails_before_any_source_read():
    reader, fake = setup_reader()
    with pytest.raises(ValueError, match="source UTC timestamp"):
        reader.read(order_placed_at="2026-10-01")
    assert not fake.calls


def paged_threads(reader, fake, *, second=None, next_url=None):
    path = "/v2/conversations/100/threads"
    first = [thread(1000), thread(1001, incoming=True, createdAt="2026-10-01T14:01:00Z")]
    first += [thread(1002 + i, type="note") for i in range(48)]
    fake.routes[(path, 1)] = page(
        "threads",
        first,
        total=51,
        next_url=API_ORIGIN + path + "?page=2" if next_url is None else next_url,
    )
    fake.routes[(path, 2)] = (
        page("threads", [thread(1050, type="note")], number=2, total=51)
        if second is None
        else second
    )
    return reader


def test_complete_thread_pages_retain_every_native_id_and_enable_association():
    reader, fake = setup_reader()
    result = paged_threads(reader, fake).read()
    assert result.complete and result.conversations[0].history_complete
    assert len(all_threads(result)) == 51
    assert {item.thread_id for item in all_threads(result)} == set(range(1000, 1051))
    assert next(
        item for item in all_threads(result) if item.thread_id == 1001
    ).prior_target_thread_ids == (1000,)
    assert fake.unexpected == []


@pytest.mark.parametrize("status", [301, 404, 401, 403, 429, 500])
def test_later_history_failure_preserves_facts_but_blocks_association_and_negative_findings(status):
    reader, fake = setup_reader()
    failure = HttpResponse(status, {"Location": "https://other.example.test/"}, b"{}")
    result = paged_threads(reader, fake, second=failure).read()
    assert not result.complete and not result.no_result
    assert len(all_threads(result)) == 50
    assert not result.conversations[0].history_complete
    assert all(item.prior_target_thread_ids == () for item in all_threads(result))
    assert any(issue.http_status == status for issue in result.issues)
    assert all(call[1].netloc == "api.helpscout.net" for call in fake.calls)


@pytest.mark.parametrize(
    "next_url",
    [
        "https://other.example.test/v2/conversations/100/threads?page=2",
        "http://api.helpscout.net/v2/conversations/100/threads?page=2",
        "https://api.helpscout.net/v2/conversations/101/threads?page=2",
        "https://api.helpscout.net/v2/conversations/100/threads?page=1",
        "https://api.helpscout.net/v2/conversations/100/threads?page=2&page=2",
        "https://api.helpscout.net/v2/conversations/100/threads?page=2&mailbox=555",
        "https://api.helpscout.net/v2/conversations/100/threads?page=2#fragment",
        "".join(
            (
                "https://",
                "synthetic-user",
                ":",
                "synthetic-password",
                "@api.helpscout.net/v2/conversations/100/threads?page=2",
            )
        ),
        "/v2/conversations/100/threads?page=2",
        "https://api.helpscout.net/v2/conversations/100/threads?page=3",
    ],
)
def test_bad_or_looping_next_link_is_refused_before_http(next_url):
    reader, fake = setup_reader()
    result = paged_threads(reader, fake, next_url=next_url).read()
    assert "PAGINATION_NEXT_INVALID" in codes(result)
    assert not result.complete and not result.no_result
    assert len(all_threads(result)) == 50
    assert not any(call[2].get("page") == ["2"] for call in fake.calls)


def test_omitted_pagination_filters_are_restored_from_trusted_scope():
    reader, fake = setup_reader(conversations=[])
    first = [conversation(i, mailboxId=555) for i in range(100, 125)]
    fake.routes[("/v2/conversations", 1)] = page(
        "conversations",
        first,
        size=25,
        total=26,
        next_url=API_ORIGIN + "/v2/conversations?page=2",
    )
    fake.routes[("/v2/conversations", 2)] = page(
        "conversations",
        [conversation(125, mailboxId=555)],
        number=2,
        size=25,
        total=26,
    )
    result = reader.read()
    search = next(c for c in result.coverage if c.stage == "conversations")
    assert search.complete and search.pages == 2
    query = next(call[2] for call in fake.calls if call[2].get("page") == ["2"])
    assert query == {
        "page": ["2"],
        "mailbox": [str(MAILBOX_ID)],
        "query": ["(customerIds:10)"],
        "status": ["all"],
    }


@pytest.mark.parametrize(
    "mutation,issue",
    [
        ("total", "PAGINATION_CHANGED"),
        ("duplicate", "PAGINATION_RECORD_INVALID_OR_DUPLICATE"),
        ("missing", "PAGINATION_METADATA_INVALID"),
        ("missing_next", "PAGINATION_TRUNCATED"),
    ],
)
def test_inconsistent_pagination_is_partial(mutation, issue):
    reader, fake = setup_reader()
    paged_threads(reader, fake)
    path = "/v2/conversations/100/threads"
    if mutation == "total":
        fake.routes[(path, 2)]["page"]["totalElements"] = 52
    elif mutation == "duplicate":
        fake.routes[(path, 2)]["_embedded"]["threads"][0]["id"] = 1000
    elif mutation == "missing":
        del fake.routes[(path, 2)]["page"]["totalPages"]
    else:
        fake.routes[(path, 1)]["_links"] = {}
    result = reader.read()
    assert issue in codes(result)
    assert not result.complete and not result.no_result
    assert not result.conversations[0].history_complete
    assert all(item.prior_target_thread_ids == () for item in all_threads(result))


@pytest.mark.parametrize("status", [301, 404])
def test_merged_or_missing_detail_is_partial_and_never_redirected(status):
    reader, fake = setup_reader()
    fake.routes[("/v2/conversations/100", 0)] = HttpResponse(
        status,
        {"Location": API_ORIGIN + "/v2/conversations/101"},
        b"{}",
    )
    result = reader.read()
    assert not result.complete and not result.no_result and not result.conversations
    assert any(issue.http_status == status for issue in result.issues)
    assert not any(call[1].path.endswith("/101") for call in fake.calls)


def test_history_change_during_read_preserves_threads_but_blocks_association():
    reader, fake = setup_reader(threads=[thread(), thread(1001, incoming=True)])
    detail = conversation()
    changed = deepcopy(detail)
    changed["userUpdatedAt"] = "2026-10-01T17:00:00Z"
    fake.routes[("/v2/conversations/100", 0)] = [detail, changed]
    result = reader.read()
    assert "CONVERSATION_CHANGED_OR_UNAVAILABLE" in codes(result)
    assert len(all_threads(result)) == 2 and not result.conversations[0].history_complete
    assert all(item.prior_target_thread_ids == () for item in all_threads(result))


@pytest.mark.parametrize("field", ["threads", "userUpdatedAt"])
def test_missing_conversation_snapshot_metadata_blocks_association(field):
    detail = conversation()
    del detail[field]
    reader, _ = setup_reader(
        threads=[thread(), thread(1001, incoming=True, createdAt="2026-10-01T14:01:00Z")],
        conversations=[detail],
    )
    result = reader.read()
    assert not result.complete and not result.conversations[0].history_complete
    assert len(all_threads(result)) == 2
    assert "CONVERSATION_CHANGED_OR_UNAVAILABLE" in codes(result)
    assert all(item.prior_target_thread_ids == () for item in all_threads(result))


@pytest.mark.parametrize(
    "metadata",
    [
        {"threads": True},
        {"threads": -1},
        {"threads": "2"},
        {"userUpdatedAt": "2026-10-01"},
        {"userUpdatedAt": "2026-10-01T16:00:00"},
    ],
)
def test_invalid_snapshot_metadata_cannot_establish_stable_history(metadata):
    reader, _ = setup_reader(
        threads=[thread(), thread(1001, incoming=True, createdAt="2026-10-01T14:01:00Z")],
        conversations=[conversation(**metadata)],
    )
    result = reader.read()
    assert not result.complete and not result.conversations[0].history_complete
    assert all(item.prior_target_thread_ids == () for item in all_threads(result))


@pytest.mark.parametrize("original_count,refreshed_count", [(0, False), (1, True), (2, 2.0)])
def test_refreshed_thread_count_requires_integer_even_when_numerically_equal(
    original_count, refreshed_count
):
    threads = [
        thread(),
        thread(1001, incoming=True, createdAt="2026-10-01T14:01:00Z"),
    ][:original_count]
    detail = conversation(threads=original_count)
    reader, fake = setup_reader(threads=threads, conversations=[detail])
    refreshed = deepcopy(detail)
    refreshed["threads"] = refreshed_count
    assert detail["threads"] == refreshed["threads"]
    fake.routes[("/v2/conversations/100", 0)] = [detail, refreshed]

    result = reader.read()

    assert not result.complete and not result.conversations[0].history_complete
    assert "CONVERSATION_CHANGED_OR_UNAVAILABLE" in codes(result)
    assert len(all_threads(result)) == original_count
    assert all(item.prior_target_thread_ids == () for item in all_threads(result))


@pytest.mark.parametrize(
    "changed",
    [
        {"type": "chat"},
        {"primaryCustomer": {"id": CUSTOMER, "email": ALIAS}},
    ],
)
def test_conversation_type_or_primary_customer_change_blocks_association(changed):
    reader, fake = setup_reader(
        emails=[email_record(), email_record(21, ALIAS)],
        threads=[thread(), thread(1001, incoming=True, createdAt="2026-10-01T14:01:00Z")],
    )
    detail = conversation()
    refreshed = deepcopy(detail)
    refreshed.update(changed)
    fake.routes[("/v2/conversations/100", 0)] = [detail, refreshed]
    result = reader.read()
    assert not result.complete and not result.conversations[0].history_complete
    assert "CONVERSATION_CHANGED_OR_UNAVAILABLE" in codes(result)
    assert all(item.prior_target_thread_ids == () for item in all_threads(result))


@pytest.mark.parametrize("incoming", [True, False])
def test_conflicting_associated_customer_email_blocks_inbound_and_outbound_identity(incoming):
    reader, _ = setup_reader(
        threads=[
            thread(incoming=incoming, customer={"id": CUSTOMER, "email": "other@example.test"})
        ]
    )
    evidence = all_threads(reader.read())[0]
    assert not evidence.identity_proved
    assert evidence.observed_role == "IDENTITY_UNPROVED"
    assert evidence.identity_issue == "ASSOCIATED_CUSTOMER_EMAIL_CONFLICT"
    assert evidence.prior_target_thread_ids == ()


def test_default_evidence_and_summary_exclude_content_and_pii_from_repr(capsys):
    reader, _ = setup_reader(threads=[thread()])
    result = reader.read()
    evidence = all_threads(result)[0]
    assert evidence.content_excerpt is None
    for representation in (
        repr(result),
        repr(evidence),
        repr(result.customers[0]),
        json.dumps(result.summary()),
    ):
        assert EMAIL not in representation
        assert "rep@example.test" not in representation
        assert "Synthetic confidential body" not in representation
    assert capsys.readouterr().out == "" and capsys.readouterr().err == ""


def test_explicit_content_is_transient_bounded_and_not_in_repr():
    reader, _ = setup_reader(
        threads=[thread(body="<p>" + "synthetic " * 1000 + "</p>")], include_content=True
    )
    result = reader.read()
    evidence = all_threads(result)[0]
    assert evidence.content_excerpt and len(evidence.content_excerpt) <= 2000
    assert "synthetic synthetic" not in repr(evidence)
    assert "synthetic synthetic" not in repr(result)


@pytest.mark.parametrize(
    "source_link",
    [
        "https://other.example.test/conversation/100/",
        "https://secure.helpscout.net/conversation/101/",
        "https://secure.helpscout.net/conversation/100/?secret=synthetic",
    ],
)
def test_source_link_must_match_native_conversation_and_safe_origin(source_link):
    reader, _ = setup_reader(
        threads=[thread()],
        conversations=[
            conversation(_links={"web": {"href": source_link}}),
        ],
    )
    result = reader.read()
    assert result.conversations[0].source_link is None
    assert all_threads(result)[0].source_link is None


def test_page_budget_is_explicit_partial_coverage():
    reader, fake = setup_reader(max_pages=1)
    result = paged_threads(reader, fake).read()
    assert "PAGE_BUDGET_EXCEEDED" in codes(result)
    assert not result.complete and len(all_threads(result)) == 50
    assert not result.conversations[0].history_complete


def test_request_budget_is_explicit_partial_coverage():
    reader, fake = setup_reader(max_requests=1)
    result = reader.read()
    assert "READ_BUDGET_OR_TERMINAL_STOP" in codes(result)
    assert result.identity_status == "INCOMPLETE" and not result.no_result
    assert len(fake.calls) == 1


@pytest.mark.parametrize("unexpected", ["next", "page"])
def test_unexpected_email_pagination_is_partial_and_blocks_discovery(unexpected):
    reader, fake = setup_reader()
    path = f"/v2/customers/{CUSTOMER}/emails"
    document = email_collection([email_record(), email_record(21, ALIAS)])
    if unexpected == "next":
        document["_links"]["next"] = {"href": API_ORIGIN + path + "?page=2"}
    else:
        document["page"] = {"number": 1, "size": 50, "totalElements": 2, "totalPages": 1}
    fake.routes[(path, 0)] = document
    result = reader.read()
    assert result.identity_status == "INCOMPLETE" and not result.complete
    assert not result.no_result and not result.conversations
    assert not any(call[1].path == "/v2/conversations" for call in fake.calls)
    assert len([call for call in fake.calls if call[1].path == path]) == 1
    assert not any(call[2].get("page") == ["2"] for call in fake.calls)


def test_malformed_customer_email_makes_identity_enumeration_incomplete():
    reader, fake = setup_reader(emails=[email_record(), email_record(21, "not-an-email")])
    result = reader.read()
    assert result.identity_status == "INCOMPLETE"
    assert "CUSTOMER_EMAIL_INVALID" in codes(result)
    assert not result.complete and not result.no_result
    assert not any(call[1].path == "/v2/conversations" for call in fake.calls)


def test_duplicate_email_values_with_distinct_native_ids_are_harmless():
    reader, _ = setup_reader(
        emails=[email_record(), email_record(21, EMAIL.upper())], conversations=[]
    )
    result = reader.read()
    assert result.complete and result.identity_status == "EXACT"
    assert result.customers[0].emails == (EMAIL,)
    assert result.customers[0].email_ids == (20, 21)


@pytest.mark.parametrize(
    "records",
    [
        [email_record(), email_record(20, ALIAS)],
        [email_record(), {"value": ALIAS, "type": "work"}],
        [email_record(), {"id": True, "value": ALIAS, "type": "work"}],
        [email_record(), {"id": -1, "value": ALIAS, "type": "work"}],
        [email_record(), "not-an-email-object"],
    ],
)
def test_invalid_or_duplicate_email_native_ids_make_collection_incomplete(records):
    reader, fake = setup_reader(emails=records)
    result = reader.read()
    assert result.identity_status == "INCOMPLETE" and not result.complete
    assert result.issues and not result.no_result
    assert not any(call[1].path == "/v2/conversations" for call in fake.calls)


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"_embedded": {"emails": None}, "_links": {}},
        {"_embedded": {"emails": {}}, "_links": {}},
        {"_embedded": {"other": []}, "_links": {}},
    ],
)
def test_malformed_unpaginated_email_collection_is_incomplete(document):
    reader, fake = setup_reader()
    fake.routes[(f"/v2/customers/{CUSTOMER}/emails", 0)] = document
    result = reader.read()
    assert result.identity_status == "INCOMPLETE" and not result.complete
    assert result.issues and not result.no_result
    assert not any(call[1].path == "/v2/conversations" for call in fake.calls)


def test_complete_empty_unpaginated_email_collection_has_no_exact_identity():
    reader, fake = setup_reader(emails=[])
    result = reader.read()
    assert result.identity_status == "NO_EXACT_CUSTOMER" and result.complete
    assert not result.no_result and not result.customers
    assert result.summary()["no_scoped_conversations"] is False
    assert not any(call[1].path == "/v2/conversations" for call in fake.calls)


def test_unpaginated_email_collection_obeys_record_bound():
    reader, fake = setup_reader(emails=[email_record(), email_record(21, ALIAS)], max_records=1)
    result = reader.read()
    assert result.identity_status == "INCOMPLETE" and not result.complete
    assert result.issues and not result.no_result
    assert not any(call[1].path == "/v2/conversations" for call in fake.calls)


@pytest.mark.parametrize(
    "next_url",
    [
        "https://api.helpscout.net/v2/conversations/100/threads?page=2%",
        "https://api.helpscout.net/v2/conversations/100/threads?page=2#",
        "https://api.helpscout.net/v2/conversations/100/threads?page=2&unexpected=1",
    ],
)
def test_malformed_or_extended_pagination_link_never_reaches_transport(next_url):
    reader, fake = setup_reader()
    result = paged_threads(reader, fake, next_url=next_url).read()
    assert "PAGINATION_NEXT_INVALID" in codes(result)
    assert not result.complete
    assert not any(call[2].get("page") == ["2"] for call in fake.calls)


@pytest.mark.parametrize("links", [None, [], "not-links"])
def test_malformed_links_cannot_be_mistaken_for_successful_last_page(links):
    reader, fake = setup_reader()
    document = page("customers", [])
    document["_links"] = links
    fake.routes[("/v2/customers", 1)] = document
    result = reader.read()
    assert result.identity_status == "INCOMPLETE"
    assert not result.complete and not result.no_result
    assert "PAGINATION_METADATA_INVALID" in codes(result)


def test_contradictory_empty_pagination_cannot_claim_no_result():
    reader, fake = setup_reader()
    document = page("customers", [])
    document["page"]["totalPages"] = 2
    fake.routes[("/v2/customers", 1)] = document
    result = reader.read()
    assert result.identity_status == "INCOMPLETE"
    assert not result.complete and not result.no_result


def test_terminal_auth_error_stops_other_customer_email_reads():
    reader, fake = setup_reader()
    fake.routes[("/v2/customers", 1)] = page("customers", [{"id": 10}, {"id": 11}])
    fake.routes[("/v2/customers/10/emails", 0)] = HttpResponse(401, {}, b"{}")
    result = reader.read()
    assert result.identity_status == "INCOMPLETE" and not result.complete
    assert not any(call[1].path == "/v2/customers/11/emails" for call in fake.calls)
    assert "unauthorized" in codes(result)
    assert "READ_BUDGET_OR_TERMINAL_STOP" in codes(result)
