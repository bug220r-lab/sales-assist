"""Synthetic snapshot facts, companion-compatible lifecycle, and durable local review.

The schema-2 adapter deliberately requires reserved identities; schema-1 companion
exports are reference material and cannot be imported into this synthetic store.
No operation in this module has a network destination or remote write implementation.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from synthetic_sales_assist.domain.canonical import canonical_json_bytes, domain_hash
from synthetic_sales_assist.safety.content import assert_payload_safe
from synthetic_sales_assist.safety.identity import assert_reserved_identity, assert_synthetic_email

if TYPE_CHECKING:
    from synthetic_sales_assist.campaign_replies.store import Store


class ReplyValidationError(ValueError):
    """An import or local review failed a closed contract."""


class DraftConflict(ReplyValidationError):
    """The caller must reload source, style, and the current draft revision."""


CATEGORIES = {
    "optout": "Stop contact / wrong recipient", "complaint": "Complaint",
    "ready": "Order help", "fitment": "Fitment / parts",
    "commercial": "Shipping / stock / price", "service": "Existing order / shipping help",
    "alternative": "Alternative chosen", "verification": "Verification pending",
    "purchased": "Already purchased (reported)", "later": "Not now / not interested",
    "automated": "Possible automated reply", "general": "Other question",
    "bounce": "Bounced message", "exception": "Sync exception", "waiting": "Awaiting first reply",
}
_RULES = [
    ("optout", (
        '\\b(unsubscribe|remove me|stop (?:emailing|contacting|sending)|do not (?:email|'
        "contact)|don't (?:email|contact)|wrong (?:person|email|address)|never (?:email|"
        'contact))\\b'
    ), "Record and review the contact preference before any further outreach."),
    ("complaint", r"\b(complaint|unacceptable|angry|terrible|scam|fraud|furious|rip.?off)\b",
        "Read the full complaint and handle it personally."),
    ("automated", (
        '\\b(out of (?:the )?office|automatic reply|auto.?reply|automated (?:message|'
        'response)|on vacation|delivery status notification|undeliverable)\\b'
    ), "Check whether this is automated before preparing a response."),
    ("service", (
        '\\b(did my order go through|order status|check (?:the )?(?:shipping|order)|'
        "credit card hasn't|overnight shipping|shipped standard|tracking (?:number|"
        'information)|where is my order)\\b'
    ), (
        'Review the existing order or shipment. Payment and delivery facts require '
        'verification.'
    )),
    ("alternative", (
        '\\b(found (?:an? )?alternative|purchase at|bought .{0,30}elsewhere|bought (?:it|'
        'these|them) from another)\\b'
    ), "Acknowledge their alternative without another cart reminder."),
    ("purchased", (
        '\\b(already (?:ordered|purchased|bought)|placed (?:the |an |my )?order|bought '
        "(?:it|these|them) elsewhere|just bought|i bought|i ordered|i did order|i(?:'ve|"
        've) got my order|buying it already|they bought it)\\b'
    ), (
        'Customer-reported purchase only; no order or recovered revenue is verified.'
    )),
    ("later", (
        '\\b(not interested|no longer need|maybe later|contact me (?:next|in)|not '
        '(?:right )?now)\\b'
    ), "Review the stated preference and requested follow-up date."),
    ("fitment", (
        '\\b(fitment|will .{0,25}fit|does .{0,25}fit|compatible|compatibility|vin|part '
        'number|measurements|rotor dimensions)\\b'
    ), "Verify the part and vehicle details before making a fitment claim."),
    ("ready", (
        '\\b(ready to (?:buy|order)|place (?:an|my|the) order|checkout|check out|payment|'
        'pay for|buy (?:it|these|them))\\b'
    ), (
        'Review the order or checkout question. Do not request payment-card details.'
    )),
    ("commercial", (
        '\\b(shipping|delivery|ship|stock|available|availability|backorder|price|discount|'
        'coupon|cost)\\b'
    ), "Verify shipping, availability, or price information before replying."),
]
_COMPILED_RULES = [(category, re.compile(pattern), action) for category, pattern, action in _RULES]
_PRIORITY = {"optout": 0, "complaint": 1, "service": 1, "ready": 2, "fitment": 3,
             "commercial": 3, "general": 3, "purchased": 4, "alternative": 4, "later": 4,
             "automated": 5}
_STARTERS = {
    "purchased": (
        "Hello,\n\nThanks for letting me know you've already ordered, and I'm sorry for "
        'the confusion caused by the cart reminder. Please let me know if you need help '
        'with anything else.'
    ),
    "alternative": (
        "Hello,\n\nThanks for the update. I understand you've found another option, and I "
        'appreciate you letting me know. Feel free to reach out if you need help in the '
        'future.'
    ),
    "fitment": (
        "Hello,\n\nThanks for the update. Could you send the vehicle's year, make and "
        "model, along with the part you're checking and any relevant measurements or "
        'modifications? That will help me check the fitment before you order.'
    ),
    "later": "Hello,\n\nThanks for letting me know. I understand, and I appreciate the update.",
    "service": (
        "Hello,\n\nThanks for flagging this, and I'm sorry for the confusion. I'll review "
        'the order details before confirming the status or next steps.'
    ),
    "commercial": (
        "Hello,\n\nThanks for your question. I'll check the current information for the "
        "items you're considering before confirming the details."
    ),
    "ready": (
        "Hello,\n\nI'd be happy to help. What part of checkout is giving you trouble? "
        "Please don't send payment-card details by email."
    ),
}


def plain(value: str) -> str:
    """Return inert display text. Consumers must still render it as text, never HTML."""
    value = re.sub(r"<(script|style)\b[^>]*>[\s\S]*?</\1>", "", value, flags=re.I)
    value = re.sub(r"<br\s*/?\s*>|</p>|</div>|</li>", "\n", value, flags=re.I)
    value = html.unescape(re.sub(r"<[^>]*>", "", value)).replace("\r", "")
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"\n[ \t]+", "\n", value)).strip()


def fresh(value: str) -> str:
    value = re.sub(r"<blockquote\b[^>]*>[\s\S]*$", "", value, flags=re.I)
    value = re.sub(r"<div\b[^>]*(?:gmail_quote|yahoo_quoted)[^>]*>[\s\S]*$", "", value, flags=re.I)
    return re.split(r"\n(?:On .{5,200}wrote:|From:|_{5,}|-{3,}\s*Original Message)",
                    plain(value), maxsplit=1, flags=re.I)[0].strip()


def classify(value: str) -> dict[str, Any]:
    normalized = value.lower().replace("’", "'").replace("‘", "'")
    for category, pattern, action in _COMPILED_RULES:
        match = pattern.search(normalized)
        if match:
            return {"category": category, "action": action, "evidence": match.group(0)}
    return {"category": "general", "action": "Read the message and prepare a specific response.",
            "evidence": "No specific category rule matched."}


def _time(value: Any) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value
    ):
        raise ReplyValidationError("TIMESTAMP_MUST_BE_UTC")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReplyValidationError("INVALID_TIMESTAMP") from exc


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _thread_order(thread: dict[str, Any]) -> datetime:
    # Reserved IDs are nonnumeric. The companion comparator keeps source order
    # for equal timestamps when its BigInt ID comparison is unavailable.
    return _time(thread["createdAt"])


def derive(contact: dict[str, Any]) -> dict[str, Any]:
    """Port companion lifecycle; a timestamp index avoids its quadratic ambiguity scan."""
    conversation = contact.get("conversation") or {}
    unique = {thread["id"]: thread for thread in contact.get("threads", [])}
    base = dict(contact)
    base.update(owner=(conversation.get("assignee") or {}).get("id") or "Unassigned",
                status=conversation.get("status") or "Unknown", replied=False, needs=False,
                needs_reply=False, review=False, automated=False, waiting_since=None, reply_at=None,
                summary="No customer reply recorded.", category="waiting", priority=9,
                action="Waiting for a customer reply.", evidence="No published incoming reply.",
                latest_incoming_thread_id=None, latest_thread_id=None, pending_thread_ids=[],
                attachment_count=0, has_draft=False, stale_draft=False, blockers=[],
                accepted_outreach=any(
                    thread.get("id") == contact.get("anchor_thread_id")
                    and thread.get("type") == "message"
                    and thread.get("state") in ("published", "bounced")
                    and (thread.get("customer") or {}).get("id")
                    and (thread.get("customer") or {}).get("email") == contact.get("email")
                    for thread in unique.values()
                ), incoming_reply_count=0, customer_reported_purchase=False)

    def exception(reason: str) -> dict[str, Any]:
        base.update(category="exception", review=True, priority=0, summary=reason, evidence=reason,
                    action="Reconcile the saved conversation evidence before drafting.")
        base["blockers"].append(reason)
        return base

    if contact.get("sync_error"):
        if not contact.get("anchor_thread_id") and contact.get("sync_error") == "ANCHOR_PENDING":
            base.update(category="verification", review=True, priority=7,
                        summary="Waiting for a verified original message ID.",
                        action="Import a complete snapshot with a verified anchor.")
            base["blockers"].append("Original message is unverified.")
            return base
        return exception(contact["sync_error"])
    if contact.get("merge_unresolved") or conversation.get("id") != contact.get("conversation_id"):
        return exception("Unresolved conversation merge requires manual reconciliation.")
    try:
        threads = sorted(unique.values(), key=_thread_order)
    except (ReplyValidationError, KeyError):
        return exception("A thread has a missing or invalid timestamp.")
    base["threads"] = threads
    anchor = next((t for t in threads if t["id"] == contact.get("anchor_thread_id")), None)
    if not anchor or anchor["type"] != "message" or anchor["state"] not in ("published", "bounced"):
        return exception("The original campaign message could not be verified.")
    anchor_customer = anchor.get("customer") or {}
    if not anchor_customer.get("id") or not anchor_customer.get("email"):
        return exception("The original message lacks verified customer identity.")
    if anchor_customer["email"].lower() != contact["email"].lower():
        return exception("The original message identifies a different customer.")
    primary = conversation.get("primaryCustomer") or {}
    if primary and (primary.get("id") != anchor_customer["id"] or
                    primary.get("email") != anchor_customer["email"]):
        return exception("The conversation customer identity changed.")

    def belongs(thread: dict[str, Any]) -> bool:
        identity = thread.get("customer") or (
            thread.get("createdBy") if thread.get("type") == "customer" else {}) or {}
        email = str(identity.get("email") or "").lower()
        return email == contact["email"].lower() if email else (
            identity.get("id") == anchor_customer["id"])

    after_anchor = [t for t in threads if _thread_order(t) > _thread_order(anchor)]
    incoming = [t for t in after_anchor if t["type"] == "customer" and t["state"] == "published"]
    times: dict[datetime, set[str]] = {}
    for thread in threads:
        if thread["type"] in ("customer", "message") and thread["state"] == "published" and (
            _time(thread["createdAt"]) >= _time(anchor["createdAt"])
        ):
            kinds = times.setdefault(_time(thread["createdAt"]), set())
            kinds.add(thread["type"])
            if len(kinds) > 1:
                return exception((
                    'A customer and staff message share a timestamp; response order '
                    'needs review.'
                ))
    if any(not belongs(t) for t in incoming):
        return exception((
            'A later incoming message has a different or unverified customer identity.'
        ))
    staff = [t for t in after_anchor if t["type"] == "message" and t["state"] == "published"
             and (t.get("createdBy") or {}).get("type") == "user" and not t.get("scheduled")]
    if any(not belongs(t) for t in staff):
        return exception("A later staff message has a different or unverified recipient.")
    if any(t.get("to") and contact["email"].lower() not in
           [value.strip().lower() for value in t["to"]] for t in staff):
        return exception("A staff reply has an explicit To address that excludes this customer.")
    answered = staff[-1] if staff else None
    pending = [t for t in incoming if not answered or _thread_order(t) > _thread_order(answered)]
    human = [t for t in pending if classify(fresh(t.get("body", "")))["category"] != "automated"]
    meaningful = [t for t in human if fresh(t.get("body", ""))]
    latest = (meaningful or human or pending or incoming or [None])[-1]
    last = incoming[-1] if incoming else None
    purchase_rule = next(rule for category, rule, _ in _COMPILED_RULES if category == "purchased")
    base.update(replied=bool(incoming), reply_at=last["createdAt"] if last else None,
                incoming_reply_count=len(incoming),
                customer_reported_purchase=any(
                    purchase_rule.search(fresh(t.get("body", "")).lower()) for t in incoming
                ),
                latest_incoming_thread_id=last["id"] if last else None,
                pending_thread_ids=[t["id"] for t in pending],
                attachment_count=sum(len((t.get("_embedded") or {}).get("attachments", []))
                                     for t in pending))
    if latest:
        body = fresh(latest.get("body", ""))
        classification = classify(body)
        category = classification["category"]
        base.update(classification)
        base.update(summary=body[:220] or "Empty message or attachment: review source metadata.",
                    latest_thread_id=latest["id"], automated=category == "automated",
                    needs=bool(pending) and category != "automated",
                    waiting_since=pending[0]["createdAt"] if pending else None,
                    review=bool(pending) and category in (
                        "optout", "complaint", "service", "purchased", "alternative",
                            "later", "automated"),
                    priority=_PRIORITY[category])
        for thread in pending:
            earlier = classify(fresh(thread.get("body", "")))
            if earlier["category"] in ("optout", "complaint") and (
                _PRIORITY[earlier["category"]] < base["priority"]
            ):
                base.update(earlier)
                base.update(priority=_PRIORITY[earlier["category"]], review=True,
                            summary=fresh(thread.get("body", ""))[:220])
    if any(t["state"] == "bounced" and _thread_order(t) >= _thread_order(anchor) for t in threads):
        base.update(category="bounce", review=True, priority=0,
                    summary="The saved evidence reports a bounced outgoing message.",
                    action="Review the failed outgoing message before further outreach.")
        base["blockers"].append("A bounced message requires review.")
    drafts = [t for t in threads if t["type"] == "message" and t["state"] == "draft"]
    base["has_draft"] = bool(drafts)
    base["stale_draft"] = any(latest and _thread_order(t) <= _thread_order(latest) for t in drafts)
    if drafts:
        base["blockers"].append("An existing staff draft blocks a future remote draft.")
    if any(t["state"] in ("review", "underreview") or t.get("scheduled") for t in threads):
        base["blockers"].append("A review or scheduled message requires reconciliation.")
    if contact.get("write_outcome") not in (None, "none", "verified"):
        base["blockers"].append(
            "An unresolved write outcome is held; automatic retry is forbidden."
        )
    recipients = conversation.get("cc", []) + conversation.get("bcc", [])
    recipients += [value for t in threads for key in ("cc", "bcc") for value in t.get(key, [])]
    if recipients:
        base["blockers"].append("Additional recipients require manual review.")
    if base["needs"]:
        base["waiting_since"] = (human or pending)[0]["createdAt"]
    if not base["needs"] and not base["review"] and base["replied"]:
        base.update(priority=8,
            action="A published staff reply follows the latest customer message.")
    base["needs_reply"] = base["needs"]
    return base


def _natural(value: str) -> tuple[tuple[int, Any], ...]:
    return tuple((0, int(piece)) if piece.isdigit() else (1, piece)
                 for piece in re.split(r"(\d+)", value) if piece)


def prepare_evidence(contact: dict[str, Any]) -> list[dict[str, Any]]:
    """Match drafts-core.js evidence fields, including notes and attachment-only replies."""
    result = []
    unique = {thread["id"]: thread for thread in contact["threads"]}
    for thread in sorted(unique.values(), key=lambda t: _natural(str(t["id"]))):
        if thread["type"] not in ("customer", "message", "note"):
            continue
        customer, creator = thread.get("customer") or {}, thread.get("createdBy") or {}
        attachments = (thread.get("_embedded") or {}).get("attachments", [])
        result.append({
            "id": thread["id"], "type": thread["type"], "state": thread["state"],
            "created_at":
                _time(thread["createdAt"])
                .isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "body_sha256": hashlib.sha256(thread.get("body", "").encode("utf-8")).hexdigest(),
            "identity": "|".join(str(v or "") for v in (
                customer.get("id"), (customer.get("email") or "").lower(), creator.get("id"),
                creator.get("type"), (creator.get("email") or "").lower())),
            "recipients": "|".join(",".join(sorted(v.strip().lower() for v in thread.get(k, [])))
                                   for k in ("to", "cc", "bcc")),
            "attachments": sorted("|".join(str(a.get(k) or "") for k in
                                          ("id", "filename", "size", "state")) for a in
                                        attachments),
            "scheduled": bool(thread.get("scheduled")),
        })
    return result


def source_fingerprint(contact: dict[str, Any]) -> str:
    source = {key: value for key, value in contact.items() if key != "last_checked_utc"}
    return domain_hash("campaign-replies/source/v1", canonical_json_bytes(source)).sha256


def eligible(row: dict[str, Any]) -> bool:
    return bool(row["needs"] and row["category"] not in (
        "bounce", "exception", "verification", "automated") and not row["blockers"]
        and row["latest_incoming_thread_id"])


def proposal(row: dict[str, Any]) -> dict[str, Any] | None:
    if not eligible(row):
        return None
    notes = ["Starter wording: review the full conversation and supply a specific response."]
    if row["attachment_count"]:
        notes.append(
            f"{row['attachment_count']} attachment(s) require review; their contents are unseen."
        )
    return {"body": _STARTERS.get(row["category"], ""), "notes": notes,
            "source": "Reusable starter", "generator": "deterministic-companion-port",
            "analysis_status": "Not AI analysis"}


def _closed(value: Any, required: set[str], optional: set[str] | None = None) -> None:
    if not isinstance(value, dict) or not required <= value.keys() or (
        set(value) - required - (optional or set())
    ):
        raise ReplyValidationError("CLOSED_SCHEMA_MISMATCH")


def _text(value: Any, limit: int = 20000) -> None:
    if not isinstance(value, str) or len(value) > limit:
        raise ReplyValidationError("INVALID_TEXT")
    assert_payload_safe(value)


def _identity(value: Any, namespace: str, *, creator: bool = False) -> None:
    _closed(value, {"id"}, {"email", "type"} if creator else {"email"})
    assert_reserved_identity(value["id"], expected_namespace=namespace)
    if "email" in value:
        assert_synthetic_email(value["email"])
    if creator and value.get("type") not in ("user", "customer"):
        raise ReplyValidationError("INVALID_CREATOR_TYPE")


def _recipients(value: Any) -> None:
    if not isinstance(value, list) or len(value) > 100:
        raise ReplyValidationError("INVALID_RECIPIENTS")
    for email in value:
        assert_synthetic_email(email)


def validate_snapshot(snapshot: dict[str, Any]) -> bytes:
    _closed(snapshot, {"schema_version", "profile", "campaign_id", "last_success_utc", "last_error",
                       "sync_complete", "expected_contacts", "contacts", "fixture"})
    if snapshot["schema_version"] != 2 or snapshot["profile"] != "synthetic":
        raise ReplyValidationError("SYNTHETIC_SCHEMA_2_REQUIRED")
    assert_reserved_identity(snapshot["campaign_id"])
    _time(snapshot["last_success_utc"])
    if snapshot["last_error"] is not None:
        _text(snapshot["last_error"], 2000)
    contacts = snapshot["contacts"]
    if snapshot["sync_complete"] is not True or not isinstance(contacts, list) or (
        type(snapshot["expected_contacts"]) is not int or snapshot["expected_contacts"] !=
            len(contacts)
        or len(contacts) > 20000
    ):
        raise ReplyValidationError("INCOMPLETE_SNAPSHOT")
    fixture = snapshot["fixture"]
    _closed(fixture, {"scenario_id", "rule_pack_version", "expected_outcome", "expected_reasons",
                      "expected_persistence_effects", "expected_human_review_state",
                          "expected_safety_counters"})
    assert_reserved_identity(fixture["scenario_id"])
    assert_payload_safe(fixture)
    counters = fixture["expected_safety_counters"]
    if not isinstance(counters, dict) or set(counters) != {
        "PRODUCTION_SYSTEM_ACCESS_COUNT", "PRODUCTION_MUTATION_REQUEST_COUNT",
        "REAL_CUSTOMER_IDENTITY_COUNT", "NON_SYNTHETIC_FIXTURE_COUNT", "SECRET_MATERIAL_COUNT"
    } or any(type(value) is not int or value != 0 for value in counters.values()):
        raise ReplyValidationError("SYNTHETIC_COUNTERS_REQUIRED")
    keys: set[str] = set()
    conversations: set[str] = set()
    thread_owners: dict[str, str] = {}
    for contact in contacts:
        _closed(contact, {"queue_key", "rank", "email", "cart_total_cents", "currency", "cart_url",
                           "conversation_id", "anchor_thread_id", "accepted_at_utc", "conversation",
                           "threads", "last_checked_utc", "sync_error", "merge_unresolved",
                               "write_outcome"})
        assert_reserved_identity(contact["queue_key"])
        assert_reserved_identity(contact["conversation_id"], expected_namespace="CONVERSATION")
        if contact["queue_key"] in keys or contact["conversation_id"] in conversations:
            raise ReplyValidationError("DUPLICATE_CONTACT")
        keys.add(contact["queue_key"])
        conversations.add(contact["conversation_id"])
        assert_synthetic_email(contact["email"])
        if type(contact["rank"]) is not int or not 1 <= contact["rank"] <= 20000 or (
            type(contact["cart_total_cents"]) is not int or not 0 <=
                contact["cart_total_cents"] <= 10**12
        ) or contact["currency"] != "USD":
            raise ReplyValidationError("INVALID_RANK_OR_EXACT_MONEY")
        if contact["cart_url"] != "":
            raise ReplyValidationError("SYNTHETIC_OUTBOUND_LINK_DISABLED")
        for name in ("accepted_at_utc", "last_checked_utc"):
            _time(contact[name])
        if _time(contact["last_checked_utc"]) > _time(snapshot["last_success_utc"]):
            raise ReplyValidationError("CONTACT_NEWER_THAN_SNAPSHOT")
        if contact["anchor_thread_id"] is not None:
            assert_reserved_identity(contact["anchor_thread_id"], expected_namespace="INTERACTION")
        if contact["sync_error"] is not None:
            _text(contact["sync_error"], 2000)
        if type(contact["merge_unresolved"]) is not bool or contact["write_outcome"] not in (
            None, "none", "verified", "intent_unresolved", "accepted_unverified", "unknown"
        ):
            raise ReplyValidationError("INVALID_RECONCILIATION_STATE")
        conversation = contact["conversation"]
        _closed(conversation, {"id", "status", "assignee", "primaryCustomer", "cc", "bcc"})
        assert_reserved_identity(conversation["id"], expected_namespace="CONVERSATION")
        if conversation["status"] not in ("active", "pending", "closed", "spam"):
            raise ReplyValidationError("UNKNOWN_WORKFLOW_STATUS")
        if conversation["assignee"] is not None:
            _identity(conversation["assignee"], "REP")
        if conversation["primaryCustomer"] is not None:
            _identity(conversation["primaryCustomer"], "CUSTOMER")
        for key in ("cc", "bcc"):
            _recipients(conversation[key])
        if not isinstance(contact["threads"], list) or len(contact["threads"]) > 10000:
            raise ReplyValidationError("INVALID_THREADS")
        seen: dict[str, bytes] = {}
        for thread in contact["threads"]:
            _closed(thread, {"id", "type", "state", "createdAt", "body", "customer", "createdBy",
                              "to", "cc", "bcc", "_embedded", "scheduled"})
            assert_reserved_identity(thread["id"], expected_namespace="INTERACTION")
            if (
                thread["id"] in thread_owners and thread_owners[thread["id"]] !=
                    contact["queue_key"]
            ):
                raise ReplyValidationError("THREAD_OWNERSHIP_CONFLICT")
            thread_owners[thread["id"]] = contact["queue_key"]
            if thread["type"] not in ("customer", "message", "note") or thread["state"] not in (
                "published", "draft", "bounced", "review", "underreview"
            ):
                raise ReplyValidationError("UNKNOWN_THREAD_LIFECYCLE")
            _time(thread["createdAt"])
            if _time(thread["createdAt"]) > _time(snapshot["last_success_utc"]):
                raise ReplyValidationError("THREAD_NEWER_THAN_SNAPSHOT")
            _text(thread["body"], 100000)
            if thread["customer"] is not None:
                _identity(thread["customer"], "CUSTOMER")
            if thread["createdBy"] is not None:
                _identity(thread["createdBy"],
                          "CUSTOMER" if thread["createdBy"].get("type") == "customer" else "REP",
                          creator=True)
            for key in ("to", "cc", "bcc"):
                _recipients(thread[key])
            _closed(thread["_embedded"], {"attachments"})
            attachments = thread["_embedded"]["attachments"]
            if not isinstance(attachments, list) or len(attachments) > 100:
                raise ReplyValidationError("INVALID_ATTACHMENTS")
            for attachment in attachments:
                _closed(attachment, {"id", "filename", "size", "state"})
                assert_reserved_identity(attachment["id"], expected_namespace="EVIDENCE")
                # Filenames are inert metadata. Never interpret them as paths or URLs.
                if not isinstance(attachment["filename"],
                    str) or len(attachment["filename"]) > 255 or (
                    any(c in attachment["filename"] for c in ("/", "\\", "\x00", ":", "<", ">"))
                ):
                    raise ReplyValidationError("INVALID_ATTACHMENT_FILENAME")
                if type(attachment["size"]) is not int or not 0 <= attachment["size"] <= 10**9 or (
                    attachment["state"] not in ("valid", "pending", "unavailable")
                ):
                    raise ReplyValidationError("INVALID_ATTACHMENT_METADATA")
            if thread["scheduled"] is not False:
                _closed(thread["scheduled"], {"sendAt"})
                _time(thread["scheduled"]["sendAt"])
            encoded = canonical_json_bytes(thread)
            if thread["id"] in seen and seen[thread["id"]] != encoded:
                raise ReplyValidationError("CONFLICTING_THREAD_COPY")
            seen[thread["id"]] = encoded
    return canonical_json_bytes(snapshot)


class RepliesService:
    """One SQLite transaction publishes a validated snapshot and invalidates stale review."""

    def __init__(self, store: Store) -> None:
        self.store = store
        with store.transaction() as connection:
            for statement in (
                (
                    'CREATE TABLE IF NOT EXISTS cr_reply_schema (version INTEGER PRIMARY '
                    'KEY CHECK(version=1))'
                ),
                "INSERT OR IGNORE INTO cr_reply_schema VALUES(1)",
                (
                    'CREATE TABLE IF NOT EXISTS cr_snapshots (campaign_id TEXT NOT NULL, '
                    'synced_at TEXT NOT NULL, fingerprint TEXT NOT NULL, source_json '
                    'TEXT NOT NULL, imported_at TEXT NOT NULL, PRIMARY KEY(campaign_id,'
                    'synced_at))'
                ),
                (
                    'CREATE TABLE IF NOT EXISTS cr_reply_sync (campaign_id TEXT PRIMARY '
                    'KEY, synced_at TEXT NOT NULL, last_error TEXT)'
                ),
                (
                    'CREATE TABLE IF NOT EXISTS cr_reply_contacts (conversation_id TEXT '
                    'PRIMARY KEY, campaign_id TEXT NOT NULL, queue_key TEXT NOT NULL, '
                    'fingerprint TEXT NOT NULL, source_json TEXT NOT NULL, derived_json '
                    'TEXT NOT NULL, synced_at TEXT NOT NULL, priority INTEGER NOT NULL, '
                    'needs INTEGER NOT NULL, category TEXT NOT NULL, owner TEXT NOT NULL,'
                    ' waiting_since TEXT, reply_at TEXT, value_cents INTEGER NOT NULL, '
                    'rank INTEGER NOT NULL, UNIQUE(campaign_id,queue_key))'
                ),
                (
                    'CREATE INDEX IF NOT EXISTS cr_reply_queue ON '
                    'cr_reply_contacts(campaign_id,priority,waiting_since)'
                ),
                (
                    'CREATE TABLE IF NOT EXISTS cr_local_drafts (conversation_id TEXT '
                    'PRIMARY KEY, text TEXT NOT NULL, revision INTEGER NOT NULL, '
                    'source_fingerprint TEXT NOT NULL, style_version INTEGER NOT NULL, '
                    'reviewed INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at '
                    'TEXT NOT NULL, invalidation_reason TEXT)'
                ),
                (
                    'CREATE TABLE IF NOT EXISTS cr_draft_versions (conversation_id TEXT '
                    'NOT NULL, revision INTEGER NOT NULL, record_json TEXT NOT NULL, '
                    'superseded_at TEXT NOT NULL, reason TEXT NOT NULL, PRIMARY '
                    'KEY(conversation_id,revision))'
                ),
                (
                    'CREATE TABLE IF NOT EXISTS cr_style_profiles (version INTEGER '
                    'PRIMARY KEY, profile_json TEXT NOT NULL, created_at TEXT NOT NULL)'
                ),
                (
                    "CREATE TABLE IF NOT EXISTS cr_reply_projection_schema "
                    "(singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
                    "version INTEGER NOT NULL CHECK(version>=1))"
                ),
            ):
                connection.execute(statement)
            if not connection.execute("SELECT 1 FROM cr_style_profiles").fetchone():
                profile = {"version": 1, "status": "provisional",
                           "source_label": (
                               'Synthetic starter configuration; reference 13-message '
                               'profile is provisional'
                           ),
                           "rules": ["Use a concise, courteous greeting.",
                               "Verify facts independently of style."]}
                connection.execute("INSERT INTO cr_style_profiles VALUES(?,?,?)",
                                   (1, canonical_json_bytes(profile).decode(), _now()))
            projection = connection.execute(
                "SELECT version FROM cr_reply_projection_schema WHERE singleton=1"
            ).fetchone()
            if projection is None:
                # Earlier development stores already contain immutable facts and drafts.
                # Upgrade only their disposable cached summaries, once in this transaction.
                legacy = connection.execute(
                    "SELECT conversation_id,campaign_id,fingerprint,source_json "
                    "FROM cr_reply_contacts WHERE "
                    "json_type(derived_json,'$.accepted_outreach') IS NULL OR "
                    "json_type(derived_json,'$.incoming_reply_count') IS NULL OR "
                    "json_type(derived_json,'$.customer_reported_purchase') IS NULL"
                ).fetchall()
                for source in legacy:
                    derived = derive(json.loads(source["source_json"]))
                    summary = {
                        key: value for key, value in derived.items()
                        if key not in ("threads", "conversation")
                    }
                    summary.update(
                        source_fingerprint=source["fingerprint"],
                        campaign_id=source["campaign_id"],
                    )
                    connection.execute(
                        "UPDATE cr_reply_contacts SET derived_json=? WHERE conversation_id=?",
                        (canonical_json_bytes(summary).decode(), source["conversation_id"]),
                    )
                connection.execute("INSERT INTO cr_reply_projection_schema VALUES(1,1)")
            elif projection["version"] != 1:
                raise ReplyValidationError("UNSUPPORTED_REPLY_PROJECTION_VERSION")

    def import_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        raw = validate_snapshot(snapshot)
        fingerprint = domain_hash("campaign-replies/snapshot/v1", raw).sha256
        campaign, synced = snapshot["campaign_id"], snapshot["last_success_utc"]
        prepared = []
        for contact in snapshot["contacts"]:
            row = derive(contact)
            encoded = canonical_json_bytes(contact).decode()
            source = source_fingerprint(contact)
            summary = {key: value for key, value in row.items() if key not in ("threads",
                "conversation")}
            summary.update(source_fingerprint=source, campaign_id=campaign)
            prepared.append((contact, row, encoded, source, canonical_json_bytes(summary).decode()))
        with self.store.transaction() as connection:
            previous = connection.execute(
                (
                    'SELECT * FROM cr_snapshots WHERE campaign_id=? ORDER BY rowid DESC '
                    'LIMIT 1'
                ), (campaign,)
            ).fetchone()
            if previous:
                if previous["source_json"] == raw.decode():
                    return {"status": "IDEMPOTENT", "contacts": len(prepared), "fingerprint":
                        fingerprint}
                if _time(synced) <= _time(previous["synced_at"]):
                    raise ReplyValidationError("OLDER_OR_CONFLICTING_SNAPSHOT")
                old_contacts = {c["queue_key"]: c for c in
                    json.loads(previous["source_json"])["contacts"]}
                if set(old_contacts) - {c["queue_key"] for c in snapshot["contacts"]}:
                    raise ReplyValidationError("SNAPSHOT_REMOVES_PRIOR_CONTACTS")
                for contact in snapshot["contacts"]:
                    old = old_contacts.get(contact["queue_key"])
                    if old and (old["conversation_id"] != contact["conversation_id"] or
                                old["anchor_thread_id"] and old["anchor_thread_id"] !=
                                    contact["anchor_thread_id"]):
                        raise ReplyValidationError("ORIGINAL_ANCHOR_IDENTITY_CHANGED")
                    if old and _time(contact["last_checked_utc"]) < _time(old["last_checked_utc"]):
                        raise ReplyValidationError("OLDER_CONTACT_FACTS")
                    if (
                        old and {t["id"] for t in old["threads"]} - {t["id"] for t in
                            contact["threads"]}
                    ):
                        raise ReplyValidationError("SNAPSHOT_REMOVES_PRIOR_THREADS")
            connection.execute("INSERT INTO cr_snapshots VALUES(?,?,?,?,?)",
                               (campaign, synced, fingerprint, raw.decode(), _now()))
            connection.execute(
                (
                    'INSERT INTO cr_reply_sync VALUES(?,?,?) ON CONFLICT(campaign_id) DO '
                    'UPDATE SET synced_at=excluded.synced_at,'
                    'last_error=excluded.last_error'
                ),
                (campaign, synced, snapshot["last_error"])
            )
            invalidated = 0
            for contact, row, encoded, source, summary in prepared:
                existing = connection.execute(
                    "SELECT campaign_id,queue_key FROM cr_reply_contacts WHERE conversation_id=?",
                    (contact["conversation_id"],)
                ).fetchone()
                if (
                    existing and (existing["campaign_id"] != campaign or
                        existing["queue_key"] != contact["queue_key"])
                ):
                    raise ReplyValidationError("CONVERSATION_OWNERSHIP_CONFLICT")
                draft = connection.execute("SELECT * FROM cr_local_drafts WHERE conversation_id=?",
                                           (contact["conversation_id"],)).fetchone()
                if draft and draft["source_fingerprint"] != source and draft["reviewed"]:
                    self._supersede(connection, dict(draft), "Source evidence changed")
                    connection.execute(
                        (
                            'UPDATE cr_local_drafts SET reviewed=0,revision=revision+1,'
                            'updated_at=?,invalidation_reason=? WHERE conversation_id=?'
                        ),
                        (_now(), "Source evidence changed; re-review required",
                            contact["conversation_id"])
                    )
                    invalidated += 1
                connection.execute(
                    (
                        'INSERT INTO cr_reply_contacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'
                        '?,?) ON CONFLICT(conversation_id) DO UPDATE SET '
                        'fingerprint=excluded.fingerprint,'
                        'source_json=excluded.source_json,'
                        'derived_json=excluded.derived_json,synced_at=excluded.synced_at,'
                        'priority=excluded.priority,needs=excluded.needs,'
                        'category=excluded.category,owner=excluded.owner,'
                        'waiting_since=excluded.waiting_since,reply_at=excluded.reply_at,'
                        'value_cents=excluded.value_cents,rank=excluded.rank'
                    ),
                    (contact["conversation_id"], campaign, contact["queue_key"], source,
                        encoded, summary,
                     synced, row["priority"], int(row["needs"]), row["category"], row["owner"],
                     row["waiting_since"], row["reply_at"], contact["cart_total_cents"],
                         contact["rank"])
                )
        return {"status": "IMPORTED", "contacts": len(prepared), "fingerprint": fingerprint,
                "invalidated_reviews": invalidated}

    @staticmethod
    def _supersede(connection: Any, draft: dict[str, Any], reason: str) -> None:
        connection.execute("INSERT INTO cr_draft_versions VALUES(?,?,?,?,?)",
                           (draft["conversation_id"], draft["revision"],
                            canonical_json_bytes(draft).decode(), _now(), reason))

    def style_profile(self) -> dict[str, Any]:
        with self.store.read() as connection:
            row = connection.execute((
                'SELECT profile_json FROM cr_style_profiles ORDER BY version DESC LIMIT 1'
            )).fetchone()
            return dict(json.loads(row["profile_json"]))

    def set_style_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        _closed(profile, {"version", "status", "source_label", "rules"})
        if (
            type(profile["version"]) is not int or profile["status"] not in ("provisional",
                "approved")
        ):
            raise ReplyValidationError("INVALID_STYLE_PROFILE")
        _text(profile["source_label"], 1000)
        if not isinstance(profile["rules"], list) or len(profile["rules"]) > 50:
            raise ReplyValidationError("INVALID_STYLE_RULES")
        for rule in profile["rules"]:
            _text(rule, 2000)
        with self.store.transaction() as connection:
            previous = connection.execute((
                'SELECT version,profile_json FROM cr_style_profiles ORDER BY version '
                'DESC LIMIT 1'
            )).fetchone()
            encoded = canonical_json_bytes(profile).decode()
            if previous["profile_json"] == encoded:
                return profile
            if profile["version"] != previous["version"] + 1:
                raise DraftConflict("STYLE_VERSION_CONFLICT")
            connection.execute("INSERT INTO cr_style_profiles VALUES(?,?,?)",
                (profile["version"], encoded, _now()))
            for row in connection.execute(
                "SELECT * FROM cr_local_drafts WHERE reviewed=1"
            ).fetchall():
                self._supersede(connection, dict(row), "Style configuration changed")
            connection.execute((
                'UPDATE cr_local_drafts SET reviewed=0,revision=revision+1,updated_at=?,'
                "invalidation_reason='Style configuration changed; re-review required' "
                'WHERE reviewed=1'
            ), (_now(),))
        return profile

    def list_queue(self, campaign_id: str | None = None, needs_reply: bool | None = None,
                   category: str | None = None, owner: str | None = None, sort: str = "priority",
                   offset: int = 0, limit: int = 50) -> dict[str, Any]:
        ordering = {"priority":
            "priority,waiting_since IS NULL,waiting_since,value_cents DESC,rank",
                    "value": "value_cents DESC,rank", "newest": "reply_at DESC,rank",
                    "oldest": "waiting_since IS NULL,waiting_since,rank"}
        if (
            sort not in ordering or type(offset) is not int or offset < 0 or type(limit) is
                not int or not 1 <= limit <= 100
        ):
            raise ReplyValidationError("INVALID_QUEUE_PAGE_OR_SORT")
        where, values = [], []
        for field, value in (("campaign_id", campaign_id), ("needs", needs_reply),
                             ("category", category), ("owner", owner)):
            if value is not None:
                where.append(field + "=?")
                values.append(value)
        clause = " WHERE " + " AND ".join(where) if where else ""
        with self.store.read() as connection:
            total = connection.execute("SELECT COUNT(*) FROM cr_reply_contacts" + clause,
                values).fetchone()[0]
            records = connection.execute((
                'SELECT r.derived_json,d.revision,d.reviewed,d.invalidation_reason FROM '
                'cr_reply_contacts r LEFT JOIN cr_local_drafts d USING(conversation_id)'
            ) + clause + " ORDER BY " + ordering[sort] + " LIMIT ? OFFSET ?", (*values,
                limit, offset)).fetchall()
            items = []
            for record in records:
                item = json.loads(record["derived_json"])
                item["review_state"] = ("reviewed" if record["reviewed"] else
                                        "needs_review" if record["revision"] else "not_started")
                item["draft_revision"] = record["revision"] or 0
                item["invalidation_reason"] = record["invalidation_reason"]
                item["category_label"] = CATEGORIES[item["category"]]
                item["age_seconds"] = (
                    max(0, int((datetime.now(UTC) - _time(item["waiting_since"])).total_seconds()))
                    if item["waiting_since"] else None
                )
                items.append(item)
            sync = []
            for source in connection.execute("SELECT * FROM cr_reply_sync"):
                sync.append({"campaign_id": source["campaign_id"], "last_success_utc":
                    source["synced_at"],
                             "last_error": source["last_error"], "sync_age_seconds": max(0,
                                 int((datetime.now(UTC) -
                                     _time(source["synced_at"])).total_seconds()))})
            counts = {row[0]: row[1] for row in connection.execute((
                'SELECT category,COUNT(*) FROM cr_reply_contacts GROUP BY category'
            ))}
            metrics = dict(connection.execute(
                "SELECT COALESCE(SUM(json_extract(derived_json,'$.accepted_outreach')),0) "
                "AS accepted_outreach, "
                "COALESCE(SUM(json_extract(derived_json,'$.incoming_reply_count')),0) "
                "AS incoming_replies, COALESCE(SUM(needs),0) AS unanswered_requests, "
                "COALESCE(SUM(category='bounce'),0) AS bounces, "
                "COALESCE(SUM(json_extract(derived_json,'$.customer_reported_purchase')),0) "
                "AS customer_reported_purchases FROM cr_reply_contacts"
            ).fetchone())
        return {"items": items, "total": total, "offset": offset, "limit": limit,
                "counts": counts, "sync": sync, "mode": "synthetic", "categories": CATEGORIES,
                "metrics": metrics}

    def suppression_candidates(self) -> dict[str, Any]:
        """Read-only, versioned future adapter input; never claims worker enforcement."""
        with self.store.read() as connection:
            rows = connection.execute(
                'SELECT campaign_id,queue_key,conversation_id,category,fingerprint FROM '
                "cr_reply_contacts WHERE category IN ('optout','bounce') ORDER BY "
                'campaign_id,queue_key'
            ).fetchall()
        return {"schema_version": "synthetic-suppression-candidates/v1", "profile": "synthetic",
                "enforced_by_running_sender": False, "requires_adapter_review": True,
                "candidates": [dict(row) for row in rows]}

    def detail(self, conversation_id: str) -> dict[str, Any]:
        assert_reserved_identity(conversation_id, expected_namespace="CONVERSATION")
        with self.store.read() as connection:
            source = connection.execute(
                "SELECT * FROM cr_reply_contacts WHERE conversation_id=?", (conversation_id,)
            ).fetchone()
            if not source:
                raise ReplyValidationError("CONVERSATION_NOT_FOUND")
            draft = connection.execute(
                "SELECT * FROM cr_local_drafts WHERE conversation_id=?", (conversation_id,)
            ).fetchone()
            previous = connection.execute((
                'SELECT revision,reason,superseded_at FROM cr_draft_versions WHERE '
                'conversation_id=? ORDER BY revision'
            ), (conversation_id,)).fetchall()
            style = json.loads(connection.execute((
                'SELECT profile_json FROM cr_style_profiles ORDER BY version DESC LIMIT 1'
            )).fetchone()[0])
        contact = json.loads(source["source_json"])
        row = derive(contact)
        row.update(campaign_id=source["campaign_id"], source_fingerprint=source["fingerprint"],
                   source_threads=prepare_evidence(contact), proposal=proposal(row),
                   local_draft=dict(draft) if draft else None, style_profile=style,
                   last_success_utc=source["synced_at"], superseded_drafts=[dict(r) for r in
                       previous],
                   synthetic=True, outbound_links_enabled=False, remote_drafts_enabled=False)
        for thread in row["threads"]:
            thread["display_text"] = plain(thread["body"])
        if row["local_draft"]:
            row["local_draft"]["reviewed"] = bool(row["local_draft"]["reviewed"])
        return row

    def save_draft(
        self, conversation_id: str, text: str, expected_revision: int,
        source_fingerprint: str, style_version: int, reviewed: bool = False,
    ) -> dict[str, Any]:
        _text(text)
        if not text.strip() or type(expected_revision) is not int or expected_revision < 0 or (
            type(style_version) is not int or type(reviewed) is not bool
        ):
            raise ReplyValidationError("INVALID_LOCAL_DRAFT")
        assert_reserved_identity(conversation_id, expected_namespace="CONVERSATION")
        with self.store.transaction() as connection:
            source = connection.execute(
                "SELECT * FROM cr_reply_contacts WHERE conversation_id=?", (conversation_id,)
            ).fetchone()
            draft = connection.execute(
                "SELECT * FROM cr_local_drafts WHERE conversation_id=?", (conversation_id,)
            ).fetchone()
            style = connection.execute("SELECT MAX(version) FROM cr_style_profiles").fetchone()[0]
            if not source:
                raise ReplyValidationError("CONVERSATION_NOT_FOUND")
            if (draft["revision"] if draft else 0) != expected_revision:
                raise DraftConflict("DRAFT_REVISION_CONFLICT")
            if source["fingerprint"] != source_fingerprint:
                raise DraftConflict("SOURCE_EVIDENCE_CONFLICT")
            if style != style_version:
                raise DraftConflict("STYLE_VERSION_CONFLICT")
            if reviewed and not eligible(derive(json.loads(source["source_json"]))):
                raise ReplyValidationError("REVIEW_BLOCKED_BY_CURRENT_EVIDENCE")
            if draft:
                self._supersede(connection, dict(draft), "Local edit saved")
            timestamp = _now()
            connection.execute((
                'INSERT INTO cr_local_drafts VALUES(?,?,?,?,?,?,?,?,?) ON '
                'CONFLICT(conversation_id) DO UPDATE SET text=excluded.text,'
                'revision=excluded.revision,source_fingerprint=excluded.source_fingerprin'
                't,style_version=excluded.style_version,reviewed=excluded.reviewed,'
                'updated_at=excluded.updated_at,invalidation_reason=NULL'
            ),
                               (conversation_id, text, expected_revision + 1, source_fingerprint,
                                style_version, int(reviewed), draft["created_at"] if draft
                                    else timestamp,
                                timestamp, None))
            result = dict(connection.execute(
                "SELECT * FROM cr_local_drafts WHERE conversation_id=?", (conversation_id,)
            ).fetchone())
            result["reviewed"] = bool(result["reviewed"])
            return result

    def synthetic_job(self, conversation_id: str) -> dict[str, Any]:
        row = self.detail(conversation_id)
        draft = row["local_draft"]
        if not draft or not draft["reviewed"] or not eligible(row):
            raise ReplyValidationError("REVIEWED_ELIGIBLE_LOCAL_DRAFT_REQUIRED")
        if (
            draft["source_fingerprint"] != row["source_fingerprint"] or
                draft["style_version"] != row["style_profile"]["version"]
        ):
            raise DraftConflict("REVIEW_BINDING_STALE")
        anchor = next(t for t in row["threads"] if t["id"] == row["anchor_thread_id"])
        job = {"queue_key": row["queue_key"], "rank": row["rank"], "email": row["email"],
               "original_conversation_id": row["conversation_id"], "conversation_id":
                   row["conversation"]["id"],
               "conversation_status": row["status"], "anchor_thread_id": row["anchor_thread_id"],
               "latest_incoming_thread_id": row["latest_incoming_thread_id"],
               "customer_id": anchor["customer"]["id"], "reviewed": True,
               "body": draft["text"].strip(), "source_threads": row["source_threads"],
               "source_synced_at": row["last_success_utc"]}
        return {"schema_version": "synthetic-reviewed-job-v1", "profile": "synthetic",
                "synthetic_only": True, "production_writer_compatible": False,
                "draft": True, "remote_write_allowed": False, "campaign_id": row["campaign_id"],
                "job": job, "local_revision": draft["revision"],
                "source_fingerprint": row["source_fingerprint"], "style_version":
                    draft["style_version"]}
