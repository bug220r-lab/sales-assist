"""Transient exact-recipient and duplicate checks for a single approved draft.

This checks the accessible, fixed-mailbox snapshot only. It is not an atomic or
global absence guarantee. The coordinator must retain its ownership guards and
the durable create ledger; this module neither creates nor persists anything.

The coordinator supplies the explicit live authorization and ownership gates.
Complete returned pages establish only the accessible mailbox snapshot; they do
not establish the absence of every historical draft or concurrent external work.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlsplit

from .reader import Coverage, EvidenceReader, Issue, _url
from .transport import (
    MAILBOX_ID,
    ReadClient,
    ReadError,
    SuppliedCredential,
    Transport,
    normalize_email,
)

EVIDENCE_MAX_AGE_SECONDS = 120
DRAFT_PREFLIGHT_ERROR_CODES = frozenset(
    {
        "draft_bundle_invalid",
        "draft_metadata_invalid",
        "draft_metadata_changed",
        "draft_primary_recipient_unproved",
        "draft_evidence_not_verified",
        "draft_evidence_bundle_mismatch",
        "draft_evidence_stale",
        "draft_existing_customer_missing",
        "draft_existing_customer_ambiguous",
        "draft_customer_email_ambiguous",
        "draft_preflight_incomplete",
        "draft_existing_draft",
        "draft_existing_order_conversation",
        "draft_customer_scope_invalid",
        "draft_known_customer_identity_mismatch",
        "draft_email_identity_ambiguous",
        "draft_email_creation_not_authorized",
    }
)
_STATES = frozenset({"published", "draft", "deleted"})
_STATUSES = frozenset({"active", "pending", "closed", "spam"})
_EMAIL_CREATION_AUTHORITY = object()


class DraftBundle(Protocol):
    @property
    def order_id(self) -> str: ...

    @property
    def subject(self) -> str: ...

    @property
    def recipient(self) -> str: ...

    @property
    def bundle_sha256(self) -> str: ...


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None
    )


def _subject(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 998
        or not value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ReadError("draft_metadata_invalid")
    return " ".join(value.split()).casefold()


def _bundle_values(bundle: DraftBundle) -> tuple[str, str, str, str]:
    try:
        order_id, subject, recipient, digest = (
            bundle.order_id,
            bundle.subject,
            normalize_email(bundle.recipient),
            bundle.bundle_sha256,
        )
        if (
            not isinstance(order_id, str)
            or re.fullmatch(r"[0-9]{1,20}", order_id) is None
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise ValueError
        normalized_subject = _subject(subject)
    except (AttributeError, TypeError, ValueError, ReadError):
        raise ReadError("draft_bundle_invalid") from None
    return order_id, normalized_subject, recipient, digest


@dataclass(frozen=True, init=False)
class DraftCustomerEvidence:
    """Only minted after complete checks; the proof contains no response bodies."""

    customer_id: int | None
    bundle_sha256: str
    recipient: str = field(repr=False)
    observed_at: datetime
    conversation_count: int
    thread_count: int
    _clock: Callable[[], datetime] = field(repr=False, compare=False)
    _email_creation_authority: object = field(default=None, repr=False, compare=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise ReadError("draft_evidence_not_verified")

    def assert_for(self, bundle: DraftBundle) -> None:
        _, _, recipient, digest = _bundle_values(bundle)
        if recipient != self.recipient or digest != self.bundle_sha256:
            raise ReadError("draft_evidence_bundle_mismatch")
        if (
            self.customer_id is None
            and self._email_creation_authority is not _EMAIL_CREATION_AUTHORITY
        ):
            raise ReadError("draft_email_creation_not_authorized")
        try:
            now = self._clock()
            if not _aware(now):
                raise ValueError
            age = (now - self.observed_at).total_seconds()
        except (TypeError, ValueError, OverflowError):
            raise ReadError("draft_evidence_stale") from None
        if not 0 <= age < EVIDENCE_MAX_AGE_SECONDS:
            raise ReadError("draft_evidence_stale")

    def summary(self) -> dict[str, object]:
        return {
            "identity_status": "EXACT" if self.customer_id is not None else "APPROVED_EMAIL_ONLY",
            "complete": True,
            "customer_count": int(self.customer_id is not None),
            "conversation_count": self.conversation_count,
            "thread_count": self.thread_count,
            "duplicate_check": "NO_MATCH_IN_ACCESSIBLE_MAILBOX_SNAPSHOT",
        }


class _KnownCustomerReader(EvidenceReader):
    """Resolve an explicitly selected ID through real GETs, without search rediscovery."""

    def __init__(self, client: ReadClient, known_customer_id: int) -> None:
        super().__init__(client, include_content=False, max_requests=50)
        self.known_customer_id = known_customer_id
        client.allow_customer(known_customer_id)

    def _pages(
        self, path: str, key: str, stage: str, record_id: int | None = None, **params: object
    ) -> tuple[list[dict[str, Any]], bool]:
        if path != "/v2/customers":
            return super()._pages(path, key, stage, record_id, **params)
        document = self._get(
            _url(f"/v2/customers/{self.known_customer_id}"),
            "known_customer_direct",
            self.known_customer_id,
        )
        valid = (
            document is not None
            and type(document.get("id")) is int
            and document["id"] == self.known_customer_id
        )
        if document is not None and not valid:
            self._issues.append(
                Issue("KNOWN_CUSTOMER_ID_MISMATCH", "known_customer_direct", self.known_customer_id)
            )
        self._coverage.append(
            Coverage(
                "known_customer_direct",
                self.known_customer_id,
                valid,
                int(document is not None),
                int(valid),
                1,
            )
        )
        # This is the actual direct customer document, not a synthetic search page.
        return ([document], True) if document is not None and valid else ([], False)


@dataclass(frozen=True)
class _Metadata:
    customer_id: int
    recipient: str = field(repr=False)
    subject: str = field(repr=False)
    state: str
    status: str
    thread_count: int


class _ObservingClient(ReadClient):
    """Inspect metadata before the ordinary evidence reader drops subject text."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.metadata: dict[int, _Metadata] = {}

    def get(self, url: str) -> dict[str, Any]:
        document = super().get(url)
        path = urlsplit(url).path
        if path == "/v2/conversations":
            embedded = document.get("_embedded")
            values = embedded.get("conversations") if isinstance(embedded, dict) else None
            if not isinstance(values, list) or len(values) > 5000:
                raise ReadError("draft_metadata_invalid")
            for value in values:
                self._observe(value)
        elif re.fullmatch(r"/v2/conversations/[0-9]+", path):
            self._observe(document)
        return document

    def _observe(self, value: object) -> None:
        if not isinstance(value, dict):
            raise ReadError("draft_metadata_invalid")
        identifier = value.get("id")
        primary = value.get("primaryCustomer")
        if (
            type(identifier) is not int
            or not 0 < identifier < 2**63
            or not isinstance(primary, dict)
            or type(primary.get("id")) is not int
            or not 0 < primary["id"] < 2**63
            or type(value.get("mailboxId")) is not int
            or value["mailboxId"] != MAILBOX_ID
            or not isinstance(value.get("state"), str)
            or value["state"] not in _STATES
            or not isinstance(value.get("status"), str)
            or value["status"] not in _STATUSES
            or type(value.get("threads")) is not int
            or not 0 <= value["threads"] <= 5000
        ):
            raise ReadError("draft_metadata_invalid")
        raw_recipient = primary.get("email")
        if not isinstance(raw_recipient, str):
            raise ReadError("draft_primary_recipient_unproved")
        try:
            recipient = normalize_email(raw_recipient)
        except ReadError:
            raise ReadError("draft_primary_recipient_unproved") from None
        if recipient != self.email:
            raise ReadError("draft_primary_recipient_unproved")
        _subject(value.get("subject"))
        metadata = _Metadata(
            primary["id"],
            recipient,
            value["subject"],
            value["state"],
            value["status"],
            value["threads"],
        )
        prior = self.metadata.get(identifier)
        if prior is not None and prior != metadata:
            raise ReadError("draft_metadata_changed")
        if prior is None and len(self.metadata) >= 5000:
            raise ReadError("draft_metadata_invalid")
        self.metadata[identifier] = metadata


def verify_customer_and_duplicates(
    bundle: DraftBundle,
    credential: SuppliedCredential,
    *,
    transport: Transport | None = None,
    clock: Callable[[], datetime] = _now,
    known_customer_id: int | None = None,
    allow_email_customer: bool = False,
) -> DraftCustomerEvidence:
    """Verify one selected identity and complete duplicates before any draft side effect."""
    if (
        type(allow_email_customer) is not bool
        or (
            known_customer_id is not None
            and (type(known_customer_id) is not int or not 1 <= known_customer_id < 2**63)
        )
        or (known_customer_id is not None and allow_email_customer)
    ):
        raise ReadError("draft_customer_scope_invalid")
    order_id, subject, recipient, digest = _bundle_values(bundle)
    observed_at = clock()
    if not _aware(observed_at):
        raise ReadError("draft_evidence_stale")
    client = _ObservingClient(
        recipient,
        credential=credential,
        transport=transport,
        clock=clock,
        enable_live=True,
        max_attempts=1,
        expiry_margin_seconds=120,
    )
    reader = (
        _KnownCustomerReader(client, known_customer_id)
        if known_customer_id is not None
        else EvidenceReader(client, include_content=False, max_requests=50)
    )
    result = reader.read()
    if result.identity_status == "NO_EXACT_CUSTOMER":
        if known_customer_id is not None:
            raise ReadError("draft_known_customer_identity_mismatch")
        if not allow_email_customer:
            raise ReadError("draft_existing_customer_missing")
        if not result.complete:
            raise ReadError("draft_preflight_incomplete")
        candidates, complete = reader._pages(
            "/v2/conversations",
            "conversations",
            "email_duplicate_check",
            mailbox=MAILBOX_ID,
            status="all",
            query=f'(email:"{recipient}")',
        )
        if not complete or reader._issues:
            raise ReadError("draft_preflight_incomplete")
        order_pattern = re.compile(rf"(?<![0-9]){re.escape(order_id)}(?![0-9])")
        for metadata in client.metadata.values():
            if metadata.state == "draft":
                raise ReadError("draft_existing_draft")
            if _subject(metadata.subject) == subject or order_pattern.search(metadata.subject):
                raise ReadError("draft_existing_order_conversation")
        if candidates:
            # A conversation with an unresolved profile is an identity hold.
            raise ReadError("draft_email_identity_ambiguous")
        evidence = object.__new__(DraftCustomerEvidence)
        for name, value in {
            "customer_id": None,
            "bundle_sha256": digest,
            "recipient": recipient,
            "observed_at": observed_at,
            "conversation_count": 0,
            "thread_count": 0,
            "_clock": clock,
            "_email_creation_authority": _EMAIL_CREATION_AUTHORITY,
        }.items():
            object.__setattr__(evidence, name, value)
        evidence.assert_for(bundle)
        return evidence
    if result.identity_status == "AMBIGUOUS":
        raise ReadError("draft_existing_customer_ambiguous")
    if result.identity_status != "EXACT" or not result.complete or len(result.customers) != 1:
        raise ReadError("draft_preflight_incomplete")
    customer = result.customers[0]
    if customer.emails != (recipient,):
        raise ReadError("draft_customer_email_ambiguous")
    if set(client.metadata) != {item.conversation_id for item in result.conversations}:
        raise ReadError("draft_preflight_incomplete")
    order_pattern = re.compile(rf"(?<![0-9]){re.escape(order_id)}(?![0-9])")
    for metadata in client.metadata.values():
        if metadata.customer_id != customer.customer_id:
            raise ReadError("draft_preflight_incomplete")
        if metadata.state == "draft":
            raise ReadError("draft_existing_draft")
        if _subject(metadata.subject) == subject or order_pattern.search(metadata.subject):
            raise ReadError("draft_existing_order_conversation")
    for conversation in result.conversations:
        for thread in conversation.threads:
            if thread.state == "draft":
                raise ReadError("draft_existing_draft")
    for conversation in result.conversations:
        if not conversation.history_complete:
            raise ReadError("draft_preflight_incomplete")
        for thread in conversation.threads:
            if thread.state not in _STATES:
                raise ReadError("draft_preflight_incomplete")
        # Native `threads` counts published threads excluding notes, while the
        # independently paginated collection can also contain notes and drafts.
        published_non_notes = sum(
            thread.state == "published" and thread.thread_type != "note"
            for thread in conversation.threads
        )
        if published_non_notes != client.metadata[conversation.conversation_id].thread_count:
            raise ReadError("draft_preflight_incomplete")
    # A private mint prevents callers from skipping preflight through the public
    # constructor. It is an API invariant, not a boundary against hostile Python.
    evidence = object.__new__(DraftCustomerEvidence)
    values = {
        "customer_id": customer.customer_id,
        "bundle_sha256": digest,
        "recipient": recipient,
        "observed_at": observed_at,
        "conversation_count": len(result.conversations),
        "thread_count": sum(len(item.threads) for item in result.conversations),
        "_clock": clock,
    }
    for key, value in values.items():
        object.__setattr__(evidence, key, value)
    evidence.assert_for(bundle)
    return evidence
