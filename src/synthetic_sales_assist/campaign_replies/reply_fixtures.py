"""Generated synthetic reply fixtures and the simulated campaign-to-reply bridge."""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from typing import Any


def fixture_metadata() -> dict[str, Any]:
    return {
        "scenario_id": "SYN-EVALUATION-CAMPAIGN-REPLY-DEMO",
        "rule_pack_version": "campaign-replies-v1",
        "expected_outcome": "Synthetic lifecycle classifications with durable local review",
        "expected_reasons": ["Generated fixture; all factual answers require review"],
        "expected_persistence_effects": "Atomic snapshot facts and separate versioned drafts",
        "expected_human_review_state": "Required before any future external action",
        "expected_safety_counters": {name: 0 for name in (
            "PRODUCTION_SYSTEM_ACCESS_COUNT", "PRODUCTION_MUTATION_REQUEST_COUNT",
            "REAL_CUSTOMER_IDENTITY_COUNT", "NON_SYNTHETIC_FIXTURE_COUNT",
                "SECRET_MATERIAL_COUNT")},
    }


def demo_thread(index: int, sequence: int, kind: str = "customer", body: str =
    "Can you help with checkout?",
                *, state: str = "published", minute: int | None = None) -> dict[str, Any]:
    customer = {"id": f"SYN-CUSTOMER-REPLIES-{index:05}", "email":
        f"customer{index:05}@example.test"}
    return {
        "id": f"SYN-INTERACTION-REPLIES-{index:05}-{sequence:03}", "type": kind, "state": state,
        "createdAt": (datetime(2026, 9, 11, 12, tzinfo=UTC) + timedelta(
            minutes=sequence if minute is None else minute)).isoformat().replace("+00:00", "Z"),
        "body": body, "customer": customer,
        "createdBy": ({**customer, "type": "customer"} if kind == "customer" else
                      {"id": "SYN-REP-DEMO", "type": "user", "email": "rep@example.test"}),
        "to": [customer["email"]], "cc": [], "bcc": [], "_embedded": {"attachments": []},
        "scheduled": False,
    }


def demo_contact(index: int = 1, *, variation: bool = False) -> dict[str, Any]:
    anchor = demo_thread(index, 0, "message", "Hello, this is a generated synthetic cart reminder.")
    bodies = ["Can you help me with checkout?", "Please stop emailing me.",
        "Will these fit my car?",
              "Where is my order?", "I already purchased the item.", "What is the shipping cost?",
              "Automatic reply: out of office", "Can you check availability?"]
    contact = {
        "queue_key": f"SYN-EVIDENCE-REPLIES-QUEUE-{index:05}", "rank": index,
        "email": anchor["customer"]["email"], "cart_total_cents": 12500 + index * 2300,
        "currency": "USD", "cart_url": "", "conversation_id":
            f"SYN-CONVERSATION-REPLIES-{index:05}",
        "anchor_thread_id": anchor["id"], "accepted_at_utc": anchor["createdAt"],
        "conversation": {"id": f"SYN-CONVERSATION-REPLIES-{index:05}", "status": "pending",
                         "assignee": {"id": "SYN-REP-DEMO"}, "primaryCustomer": anchor["customer"],
                         "cc": [], "bcc": []},
        "threads": [anchor, demo_thread(index, 1, body=bodies[(index - 1) % len(bodies)] if
            variation else bodies[0])],
        "last_checked_utc": "2026-09-11T16:00:00Z", "sync_error": None,
        "merge_unresolved": False, "write_outcome": "none",
    }
    if variation and index % 8 == 0:
        contact["threads"].append(demo_thread(index, 2, "message",
            "I will check the recorded details."))
    if variation and index % 8 == 3:
        followup = demo_thread(index, 2, body="")
        followup["_embedded"]["attachments"] = [
            {"id": f"SYN-EVIDENCE-ATTACHMENT-{index:05}", "filename": "synthetic-part.png",
                "size": 321, "state": "valid"}]
        contact["threads"].append(followup)
    return contact


def demo_snapshot(count: int = 8) -> dict[str, Any]:
    return {"schema_version": 2, "profile": "synthetic", "campaign_id": "SYN-RUN-REPLIES-DEMO",
            "last_success_utc": "2026-09-11T16:00:00Z", "last_error": None, "sync_complete": True,
            "expected_contacts": count, "contacts": [demo_contact(i, variation=True) for i in
                range(1, count + 1)],
            "fixture": fixture_metadata()}


def snapshot_from_campaign_records(records: list[dict[str, Any]],
                                   reply_text: str =
                                       "Can you help me with checkout?") -> dict[str, Any]:
    """Generate an explicit simulated reply snapshot from all accepted synthetic records.

    Inputs are campaign-service output, not a production-state import. This builder
    preserves campaign, queue, original conversation and anchor identifiers verbatim.
    """
    if not records:
        raise ValueError("At least one simulated accepted campaign record is required")
    campaign_id = records[0]["campaign_id"]
    now = datetime.now(UTC)
    contacts = []
    for index, record in enumerate(records, 1):
        if record["campaign_id"] != campaign_id:
            raise ValueError("A reply snapshot must contain one campaign")
        contact = demo_contact(index)
        customer = {"id": record["customer_id"], "email": record["email"]}
        accepted = datetime.fromisoformat(record["accepted_at"].replace("Z", "+00:00"))
        incoming_time = accepted + timedelta(microseconds=1)
        now = max(now, incoming_time)
        creator = {"id": record["sender_id"], "type": "user", "email": "rep@example.test"}
        anchor = copy.deepcopy(contact["threads"][0])
        anchor.update(id=record["anchor_thread_id"], body=record["body_text"],
                      customer=customer, createdBy=creator, to=[record["email"]],
                          createdAt=record["accepted_at"])
        incoming = copy.deepcopy(anchor)
        incoming.update(id=record["anchor_thread_id"] + "-REPLY", type="customer", body=reply_text,
                        createdBy={**customer, "type": "customer"},
                        createdAt=incoming_time.isoformat(timespec="microseconds")
                        .replace("+00:00", "Z"))
        contact.update(queue_key=record["queue_key"], rank=record["original_rank"],
            email=record["email"],
                       cart_total_cents=record["cart_total_cents"],
                           conversation_id=record["conversation_id"],
                       anchor_thread_id=record["anchor_thread_id"],
                           accepted_at_utc=record["accepted_at"],
                       threads=[anchor, incoming])
        contact["conversation"].update(id=record["conversation_id"], assignee={"id":
            record["sender_id"]},
                                       primaryCustomer=customer)
        contacts.append(contact)
    synced = now.isoformat(timespec="microseconds").replace("+00:00", "Z")
    for contact in contacts:
        contact["last_checked_utc"] = synced
    return {"schema_version": 2, "profile": "synthetic", "campaign_id": campaign_id,
            "last_success_utc": synced, "last_error": None, "sync_complete": True,
            "expected_contacts": len(contacts), "contacts": contacts, "fixture": fixture_metadata()}
