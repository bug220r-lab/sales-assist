"""Exact-identity, mailbox-scoped evidence collection. Never decides sales credit.

Records are transient: this module has no filesystem, logging, auth-provider, or
business-engine dependency. Source creation times are not verified send times.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, cast
from urllib.parse import parse_qsl, urlencode, urlsplit

from .transport import (
    API_ORIGIN,
    MAILBOX_ID,
    TARGET_AUTHOR_ID,
    ReadClient,
    ReadError,
    normalize_email,
)


def _id(value: object) -> int | None:
    return value if type(value) is int and 0 < value < 2**63 else None


def _token(value: object) -> str:
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_-]{0,40}", value)
        else "unknown"
    )


def _object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _timestamp(value: object) -> datetime | None:
    # Help Scout documents UTC seconds. Do not manufacture precision for dates,
    # timezone-free strings, unexpected formats, or imported source timestamps.
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _email(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return normalize_email(value)
    except (ReadError, TypeError, ValueError):
        return None


def _emails(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(sorted({email for item in value if (email := _email(item)) is not None}))


def _url(path: str, **params: object) -> str:
    return API_ORIGIN + path + ("?" + urlencode(params) if params else "")


def _web_link(value: object, conversation_id: int) -> str | None:
    if not isinstance(value, str) or len(value) > 512:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if (
        parsed.scheme == "https"
        and parsed.netloc == "secure.helpscout.net"
        and re.fullmatch(rf"/conversation/{conversation_id}(?:/[0-9]+)?/?", parsed.path)
        and not parsed.query
        and not parsed.fragment
        and not any(ord(char) < 33 or char == "\\" for char in value)
    ):
        return value
    return None


@dataclass(frozen=True)
class Issue:
    code: str
    stage: str
    record_id: int | None = None
    http_status: int | None = None
    retry_after: float | None = None


@dataclass(frozen=True)
class Coverage:
    stage: str
    record_id: int | None
    complete: bool
    pages: int
    records: int
    expected_records: int | None


@dataclass(frozen=True)
class CustomerIdentity:
    customer_id: int
    emails: tuple[str, ...] = field(repr=False)
    email_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class ThreadEvidence:
    conversation_id: int
    customer_id: int
    thread_id: int
    source_link: str | None
    thread_type: str
    state: str
    status: str
    author_id: int | None
    author_type: str
    assigned_to_id: int | None
    source_type: str
    source_via: str
    created_at: str | None
    timestamp_precision: str
    observed_role: str
    identity_proved: bool
    matched_recipient_emails: tuple[str, ...] = field(repr=False)
    sender_email: str | None = field(repr=False)
    source_creation_vs_order: str = "NOT_COMPARED"
    prior_target_thread_ids: tuple[int, ...] = ()
    association_basis: str = "NONE"
    relevance: str = "NOT_ASSESSED"
    send_time_verified: bool = False
    delivery_verified: bool = False
    content_excerpt: str | None = field(default=None, repr=False)
    raw_created_at: str | None = field(default=None, repr=False)
    timestamp_parse_issue: str | None = None
    identity_issue: str | None = None


@dataclass(frozen=True)
class ConversationEvidence:
    conversation_id: int
    number: int | None
    customer_id: int
    mailbox_id: int
    conversation_type: str
    state: str
    status: str
    source_link: str | None
    history_complete: bool
    threads: tuple[ThreadEvidence, ...]


@dataclass(frozen=True)
class EvidenceResult:
    identity_status: str
    customers: tuple[CustomerIdentity, ...]
    conversations: tuple[ConversationEvidence, ...]
    coverage: tuple[Coverage, ...]
    issues: tuple[Issue, ...]
    matched_email: str = field(repr=False)
    mailbox_id: int = MAILBOX_ID
    target_author_id: int = TARGET_AUTHOR_ID
    credit_classification: str = "NOT_EVALUATED"

    @property
    def complete(self) -> bool:
        return (
            self.identity_status in {"EXACT", "NO_EXACT_CUSTOMER"}
            and bool(self.coverage)
            and all(item.complete for item in self.coverage)
            and not self.issues
        )

    @property
    def no_result(self) -> bool:
        """Only no scoped accessible conversations, never 'no contact' or 'no order'."""
        return self.complete and self.identity_status == "EXACT" and not self.conversations

    def summary(self) -> dict[str, object]:
        """PII/content-free operational summary; detailed facts stay in memory."""
        return {
            "identity_status": self.identity_status,
            "complete": self.complete,
            "no_scoped_conversations": self.no_result,
            "customer_count": len(self.customers),
            "conversation_count": len(self.conversations),
            "thread_count": sum(len(item.threads) for item in self.conversations),
            "credit_classification": self.credit_classification,
            "issues": [item.code for item in self.issues],
        }


class _Excerpt(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if sum(map(len, self.parts)) < 2000:
            self.parts.append(data[:2000])


class EvidenceReader:
    def __init__(
        self,
        client: ReadClient,
        *,
        include_content: bool = False,
        max_pages: int = 100,
        max_records: int = 5000,
        max_requests: int = 250,
    ) -> None:
        if not isinstance(client, ReadClient):
            raise ValueError("read client required")
        if any(
            type(n) is not int or n < 1 or n > 10000 for n in (max_pages, max_records, max_requests)
        ):
            raise ValueError("invalid read bounds")
        self.client = client
        self.include_content = include_content
        self.max_pages = max_pages
        self.max_records = max_records
        self.max_requests = max_requests
        self._issues: list[Issue] = []
        self._coverage: list[Coverage] = []
        self._requests = 0
        self._halt = False

    def _get(self, url: str, stage: str, record_id: int | None) -> dict[str, Any] | None:
        if self._halt or self._requests >= self.max_requests:
            self._issues.append(Issue("READ_BUDGET_OR_TERMINAL_STOP", stage, record_id))
            return None
        self._requests += 1
        try:
            return self.client.get(url)
        except ReadError as error:
            self._issues.append(
                Issue(error.code, stage, record_id, error.status, error.retry_after)
            )
            if (
                error.status in {401, 403, 429}
                or "credential" in error.code.lower()
                or "disabled" in error.code.lower()
            ):
                self._halt = True
            return None

    def _pages(
        self, path: str, key: str, stage: str, record_id: int | None = None, **params: object
    ) -> tuple[list[dict[str, Any]], bool]:
        """Follow validated HAL pagination without ever allowing query-scope drift."""
        records: dict[int, dict[str, Any]] = {}
        expected: tuple[int, int, int] | None = None
        pages = 0
        complete = False
        page_number = 1
        while pages < self.max_pages:
            document = self._get(_url(path, **params, page=page_number), stage, record_id)
            if document is None:
                break
            pages += 1
            info = _object(document.get("page"))
            values = _object(document.get("_embedded")).get(key)
            raw_page = tuple(info.get(n) for n in ("number", "size", "totalElements", "totalPages"))
            if any(type(n) is not int for n in raw_page):
                self._issues.append(Issue("PAGINATION_METADATA_INVALID", stage, record_id))
                break
            number, size, total, total_pages = cast(tuple[int, int, int, int], raw_page)
            links = _object(document.get("_links"))
            next_entry = links.get("next")
            empty_zero = number == 0 and page_number == 1 and total == 0 and total_pages == 0
            if (
                not isinstance(values, list)
                or not isinstance(document.get("_links"), dict)
                or size < 1
                or total < 0
                or total_pages < 0
                or (number != page_number and not empty_zero)
                or total > self.max_records
                or len(values) > size
                or (total == 0 and total_pages not in {0, 1})
                or (total > 0 and (total_pages < 1 or total_pages != (total + size - 1) // size))
            ):
                self._issues.append(Issue("PAGINATION_METADATA_INVALID", stage, record_id))
                break
            current = (size, total, total_pages)
            if expected is not None and expected != current:
                self._issues.append(Issue("PAGINATION_CHANGED", stage, record_id))
                break
            expected = current
            invalid = False
            for value in values:
                identifier = _id(_object(value).get("id"))
                if identifier is None or identifier in records:
                    invalid = True
                    continue
                records[identifier] = value
            if invalid or len(records) > self.max_records:
                self._issues.append(
                    Issue("PAGINATION_RECORD_INVALID_OR_DUPLICATE", stage, record_id)
                )
                break
            if next_entry is None:
                complete = len(records) == total and (
                    number == total_pages or (total == 0 and total_pages in {0, 1})
                )
                if not complete:
                    self._issues.append(Issue("PAGINATION_TRUNCATED", stage, record_id))
                break
            if page_number >= total_pages or not self._valid_next(
                next_entry, path, params, page_number + 1
            ):
                self._issues.append(Issue("PAGINATION_NEXT_INVALID", stage, record_id))
                break
            page_number += 1
        else:
            self._issues.append(Issue("PAGE_BUDGET_EXCEEDED", stage, record_id))
        self._coverage.append(
            Coverage(
                stage,
                record_id,
                complete,
                pages,
                len(records),
                None if expected is None else expected[1],
            )
        )
        return list(records.values()), complete

    @staticmethod
    def _valid_next(
        entry: object, path: str, params: dict[str, object], expected_page: int
    ) -> bool:
        link = _object(entry)
        href = link.get("href")
        if not isinstance(href, str) or len(href) > 2048 or link.get("templated", False):
            return False
        if any(ord(char) < 33 or ord(char) > 126 or char in "\\#" for char in href) or re.search(
            r"%(?![0-9A-Fa-f]{2})", href
        ):
            return False
        try:
            parsed = urlsplit(href)
            pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
        except ValueError:
            return False
        query = dict(pairs)
        # A server may omit unchanged filters in its link. Restore them from the
        # trusted request; never send that link directly or accept altered filters.
        allowed = {key: str(value) for key, value in params.items()}
        allowed["page"] = str(expected_page)
        return (
            parsed.scheme == "https"
            and parsed.netloc == "api.helpscout.net"
            and parsed.path == path
            and not parsed.fragment
            and len(pairs) == len(query)
            and query.get("page") == str(expected_page)
            and all(key in allowed and value == allowed[key] for key, value in query.items())
        )

    def _customer_emails(self, customer_id: int) -> tuple[list[dict[str, Any]], bool]:
        # List Emails is one unpaginated collection, with no page parameter.
        stage = "customer_emails"
        document = self._get(_url(f"/v2/customers/{customer_id}/emails"), stage, customer_id)
        if document is None:
            self._coverage.append(Coverage(stage, customer_id, False, 0, 0, None))
            return [], False
        items = _object(document.get("_embedded")).get("emails")
        links = document.get("_links")
        if (
            not isinstance(items, list)
            or not isinstance(links, dict)
            or len(items) > self.max_records
        ):
            self._issues.append(Issue("EMAIL_COLLECTION_INVALID", stage, customer_id))
            self._coverage.append(Coverage(stage, customer_id, False, 1, 0, None))
            return [], False
        complete = "page" not in document and not any(key in links for key in ("next", "page"))
        if not complete:
            self._issues.append(Issue("EMAIL_COLLECTION_UNEXPECTED_PAGINATION", stage, customer_id))
        unique = {}
        for item in items:
            identifier = _id(_object(item).get("id"))
            if identifier is None or identifier in unique:
                complete = False
                self._issues.append(
                    Issue("EMAIL_COLLECTION_INVALID_OR_DUPLICATE_ID", stage, customer_id)
                )
                continue
            unique[identifier] = item
        self._coverage.append(Coverage(stage, customer_id, complete, 1, len(unique), len(items)))
        return list(unique.values()), complete

    def read(self, *, order_placed_at: str | None = None) -> EvidenceResult:
        self._issues, self._coverage, self._requests, self._halt = [], [], 0, False
        order_time = _timestamp(order_placed_at)
        if order_placed_at is not None and order_time is None:
            raise ValueError("order placement requires source UTC timestamp with seconds")
        candidates, search_complete = self._pages(
            "/v2/customers",
            "customers",
            "customers",
            query=f'(email:"{self.client.email}")',
        )
        identities: list[CustomerIdentity] = []
        identity_complete = search_complete
        for candidate in candidates:
            customer_id = candidate["id"]
            self.client.allow_customer(customer_id)
            emails, email_complete = self._customer_emails(customer_id)
            identity_complete &= email_complete
            addresses = tuple(
                sorted(
                    {
                        address
                        for item in emails
                        if (address := _email(item.get("value"))) is not None
                    }
                )
            )
            # Duplicate address values are harmless. Malformed values leave
            # identity enumeration unresolved; never guess a corrected address.
            if any(_email(item.get("value")) is None for item in emails):
                identity_complete = False
                self._issues.append(Issue("CUSTOMER_EMAIL_INVALID", "customer_emails", customer_id))
            if self.client.email in addresses:
                identities.append(
                    CustomerIdentity(
                        customer_id, addresses, tuple(sorted(item["id"] for item in emails))
                    )
                )
        if not identity_complete:
            status = "INCOMPLETE"
        elif len(identities) > 1:
            status = "AMBIGUOUS"
            self._issues.append(Issue("MULTIPLE_EXACT_CUSTOMERS", "identity"))
        elif identities:
            status = "EXACT"
        else:
            status = "NO_EXACT_CUSTOMER"
        conversations: list[ConversationEvidence] = []
        if status == "EXACT":
            customer = identities[0]
            listed, _ = self._pages(
                "/v2/conversations",
                "conversations",
                "conversations",
                customer.customer_id,
                mailbox=MAILBOX_ID,
                status="all",
                query=f"(customerIds:{customer.customer_id})",
            )
            for conversation in listed:
                if not self._conversation_scope(conversation, customer):
                    continue
                conversation_id = conversation["id"]
                self.client.allow_conversation(conversation_id)
                detail = self._get(
                    _url(f"/v2/conversations/{conversation_id}"), "conversation", conversation_id
                )
                if (
                    detail is None
                    or detail.get("id") != conversation_id
                    or not self._conversation_scope(detail, customer)
                ):
                    if detail is not None and detail.get("id") != conversation_id:
                        self._issues.append(
                            Issue("CONVERSATION_ID_MISMATCH", "conversation", conversation_id)
                        )
                    self._coverage.append(Coverage("conversation", conversation_id, False, 0, 0, 1))
                    continue
                threads, history_complete = self._pages(
                    f"/v2/conversations/{conversation_id}/threads",
                    "threads",
                    "threads",
                    conversation_id,
                )
                refreshed = self._get(
                    _url(f"/v2/conversations/{conversation_id}"),
                    "conversation_recheck",
                    conversation_id,
                )
                stable = (
                    refreshed is not None
                    and refreshed.get("id") == conversation_id
                    and self._conversation_scope(refreshed, customer)
                    and type(detail.get("threads")) is int
                    and detail["threads"] >= 0
                    and type(refreshed.get("threads")) is int
                    and refreshed["threads"] >= 0
                    and _timestamp(detail.get("userUpdatedAt")) is not None
                    and all(
                        detail.get(key) == refreshed.get(key)
                        for key in (
                            "threads",
                            "userUpdatedAt",
                            "state",
                            "status",
                            "type",
                            "primaryCustomer",
                        )
                    )
                )
                if not stable:
                    self._issues.append(
                        Issue(
                            "CONVERSATION_CHANGED_OR_UNAVAILABLE",
                            "conversation_recheck",
                            conversation_id,
                        )
                    )
                history_complete &= stable
                self._coverage.append(
                    Coverage(
                        "conversation_recheck",
                        conversation_id,
                        stable,
                        1 if refreshed else 0,
                        1 if stable else 0,
                        1,
                    )
                )
                web = _web_link(
                    _object(_object(detail.get("_links")).get("web")).get("href"), conversation_id
                )
                facts = [self._thread(item, detail, customer, web, order_time) for item in threads]
                facts.sort(key=lambda item: (item.created_at or "", item.thread_id))
                if history_complete:
                    facts = self._associate(facts)
                conversations.append(
                    ConversationEvidence(
                        conversation_id,
                        _id(detail.get("number")),
                        customer.customer_id,
                        MAILBOX_ID,
                        _token(detail.get("type")),
                        _token(detail.get("state")),
                        _token(detail.get("status")),
                        web,
                        history_complete,
                        tuple(facts),
                    )
                )
        return EvidenceResult(
            status,
            tuple(identities),
            tuple(conversations),
            tuple(self._coverage),
            tuple(self._issues),
            self.client.email,
        )

    def _conversation_scope(self, value: dict[str, Any], customer: CustomerIdentity) -> bool:
        identifier = _id(value.get("id"))
        primary = _object(value.get("primaryCustomer"))
        if _id(value.get("mailboxId")) != MAILBOX_ID:
            self._issues.append(Issue("MAILBOX_SCOPE_MISMATCH", "conversation", identifier))
            return False
        if _id(primary.get("id")) != customer.customer_id or (
            primary.get("email") is not None and _email(primary.get("email")) not in customer.emails
        ):
            self._issues.append(Issue("CONVERSATION_IDENTITY_MISMATCH", "conversation", identifier))
            return False
        return True

    def _thread(
        self,
        item: dict[str, Any],
        conversation: dict[str, Any],
        customer: CustomerIdentity,
        web: str | None,
        order_time: datetime | None,
    ) -> ThreadEvidence:
        kind, state, status = (_token(item.get(key)) for key in ("type", "state", "status"))
        author, associated, source = (
            _object(item.get(key)) for key in ("createdBy", "customer", "source")
        )
        author_id, author_type = _id(author.get("id")), _token(author.get("type"))
        source_type, via = _token(source.get("type")), _token(source.get("via"))
        recipients = tuple(sorted(set(_emails(item.get("to"))) & set(customer.emails)))
        sender = _email(author.get("email")) if kind == "customer" else None
        identity = _id(associated.get("id")) == customer.customer_id
        associated_email_conflict = (
            associated.get("email") is not None
            and _email(associated.get("email")) not in customer.emails
        )
        identity &= not associated_email_conflict
        if kind == "customer":
            identity &= (
                author_id == customer.customer_id
                and author_type == "customer"
                and sender in customer.emails
            )
        elif kind == "message":
            identity &= bool(recipients)
        else:
            identity = False
        when = _timestamp(item.get("createdAt"))
        raw_time = item.get("createdAt") if when else None
        raw_source = item.get("createdAt")
        preserved_raw = (
            raw_source if isinstance(raw_source, str) and len(raw_source) <= 128 else None
        )
        parse_issue = None if when else "MISSING_OR_UNSUPPORTED_SOURCE_TIMESTAMP"
        role = "UNSUPPORTED_THREAD"
        if kind in {"note", "lineitem", "forwardchild", "forwardparent"}:
            role = "EXCLUDED_NON_REPLY"
        elif state != "published":
            role = "EXCLUDED_NOT_PUBLISHED"
        elif item.get("scheduled") is not None:
            role = "EXCLUDED_SCHEDULED_OR_UNCERTAIN"
        elif (
            source_type in {"workflows", "notification", "orchestration"}
            or item.get("autoReply") is True
        ):
            role = "EXCLUDED_AUTOMATED"
        elif source_type not in {"email", "web", "mobile", "manual"}:
            role = "IMPORTED_OR_UNKNOWN_PROVENANCE_REVIEW"
        elif not identity:
            role = "IDENTITY_UNPROVED"
        elif when is None:
            role = "TIMESTAMP_UNPROVED"
        elif conversation.get("type") != "email" or conversation.get("state") != "published":
            role = "EXCLUDED_NON_EMAIL_OR_UNPUBLISHED_CONVERSATION"
        elif kind == "message" and author_type == "user" and via == "user":
            role = (
                "TARGET_PUBLISHED_OUTBOUND_CANDIDATE"
                if author_id == TARGET_AUTHOR_ID
                else "OTHER_AUTHOR_OUTBOUND"
            )
        elif kind == "customer" and via == "customer":
            role = "CUSTOMER_INBOUND_CANDIDATE"
        relation = "NOT_COMPARED"
        if order_time is not None:
            relation = (
                "UNKNOWN"
                if when is None
                else "SOURCE_CREATED_BEFORE_ORDER"
                if when < order_time
                else "SOURCE_CREATED_AT_OR_AFTER_ORDER"
            )
        excerpt = None
        if self.include_content and isinstance(item.get("body"), str):
            parser = _Excerpt()
            parser.feed(item["body"][:20000])
            excerpt = " ".join(parser.parts)[:2000]
        return ThreadEvidence(
            conversation["id"],
            customer.customer_id,
            item["id"],
            web,
            kind,
            state,
            status,
            author_id,
            author_type,
            _id(_object(item.get("assignedTo")).get("id")),
            source_type,
            via,
            raw_time,
            "SOURCE_SECOND" if when else "UNKNOWN",
            role,
            bool(identity),
            recipients,
            sender,
            relation,
            content_excerpt=excerpt,
            raw_created_at=preserved_raw,
            timestamp_parse_issue=parse_issue,
            identity_issue=(
                "ASSOCIATED_CUSTOMER_EMAIL_CONFLICT"
                if associated_email_conflict
                else "SOURCE_CUSTOMER_OR_RECIPIENT_UNPROVED"
                if not identity
                else None
            ),
        )

    @staticmethod
    def _associate(facts: list[ThreadEvidence]) -> list[ThreadEvidence]:
        """Temporal associations only: no causal reply-parent or two-way inference."""
        outbound = [
            fact for fact in facts if fact.observed_role == "TARGET_PUBLISHED_OUTBOUND_CANDIDATE"
        ]
        result = []
        for fact in facts:
            if fact.observed_role == "CUSTOMER_INBOUND_CANDIDATE":
                prior = tuple(
                    item.thread_id
                    for item in outbound
                    if item.created_at is not None
                    and fact.created_at is not None
                    and item.created_at < fact.created_at
                )
                if prior:
                    fact = replace(
                        fact,
                        prior_target_thread_ids=prior,
                        association_basis="SAME_CUSTOMER_CONVERSATION_EARLIER_SOURCE_CREATION_ONLY",
                    )
            result.append(fact)
        return result
