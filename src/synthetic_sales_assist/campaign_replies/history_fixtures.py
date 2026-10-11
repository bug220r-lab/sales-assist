"""Handcrafted exporter-shaped examples; no supplied customer records are converted."""

from __future__ import annotations

import copy
import html
from typing import Any

SIGNATURE = "Synthetic Sales Assist — SYN-REP-WRITER\nSynthetic assistance is available here."
TEMPLATE = (
    "Here is the saved cart for your synthetic project:\n{link}\n\n"
    "Let me know if you need help with the synthetic order!"
)


def demo_history_export() -> dict[str, Any]:
    """Return ten unique examples and one exact cross-file ID duplicate."""
    bodies = [
        SIGNATURE,
        "Can you send the part number from the label? That will help me check it.",
        TEMPLATE.format(link="http://127.0.0.1/cart?item=SYN-SKU-A"),
        TEMPLATE.format(link="http://127.0.0.1/cart?item=SYN-SKU-B"),
        TEMPLATE.format(link="http://127.0.0.1/cart?item=SYN-SKU-C")
        + "\n\nThe photo is a little blurry. Could you send another picture of the connector?",
        "Perfect, thanks! Send that over when you get a chance.",
        "Could someone review the attached synthetic example before I follow up?",
        "Could you confirm which synthetic item you meant?",
        "The label would help here. Can you send a clear photo?",
        "I have two possibilities to check. What year is the synthetic car, "
        "and has the connector been changed?",
    ]
    messages = []
    for number, body in enumerate(bodies, 1):
        if number not in (1, 6):
            body = "Hello,\n\n" + body + "\n\n" + SIGNATURE
        body_html = "<p>" + html.escape(body).replace("\n", "<br>") + "</p>"
        if number == 9:
            body_html += (
                "<blockquote>From: synthetic-customer@example.test<br>"
                "Synthetic quoted customer text is not staff writing.</blockquote>"
            )
        messages.append({
            "conversation_id": f"SYN-CONVERSATION-HISTORY-{number:03d}",
            "thread_id": f"SYN-INTERACTION-HISTORY-{number:03d}",
            "author_user_id": "SYN-REP-WRITER",
            "sent_at_utc": f"2026-09-{number:02d}T12:00:00.0000000Z",
            "mailbox_id": "SYN-EVIDENCE-MAILBOX",
            "conversation_type": "email", "conversation_status": "closed",
            "conversation_state": "published", "subject": "Synthetic writing example",
            "source_url": "", "thread_type": "forwardparent" if number == 7 else "message",
            "thread_state": "bounced" if number == 8 else "published",
            "saved_reply_id": 99000101 if number in (1, 2) else None,
            "source_type": "api" if number == 10 else "web", "source_via": "user",
            "body_text": body, "body_html": body_html,
            "attachments": [{"id": "SYN-EVIDENCE-HISTORY-ATTACHMENT",
                             "filename": "synthetic-label.png", "mime_type": "image/png"}]
            if number == 7 else [],
        })
    through = "2026-09-11T04:00:00Z"
    report = {
        "schema_version": 1, "exporter_version": "2.1.0", "profile": "synthetic",
        "synthetic_fixture": True, "user_id": "SYN-REP-WRITER",
        "scope_id": "SYN-EVIDENCE-HISTORY-SCOPE",
        "server_filter": "replyUserIds:SYN-REP-WRITER",
        "history_through_utc": through, "created_at_utc": "2026-09-11T04:01:00Z",
        "run_completed": True, "coverage_status": "completed_two_pass_scan",
        "complete_all_sent_history": False, "exported_messages": 10,
        "published_messages": 9, "bounced_attempts": 1,
        "error": None, "diagnostic": None, "next_phase": "complete", "next_page": 0,
        "conversations_observed": 10, "conversations_first_pass": 10,
        "conversations_verification_pass": 10,
        "counts_by_mailbox": {"SYN-EVIDENCE-MAILBOX": 10},
        "purpose": "Generated synthetic writing examples; no personal style analysis",
        "scope": "Synthetic filtered conversation index",
        "limitations": ["Initial outbound-only coverage unverified; not all sent history"],
        "fixture_metadata": {
            "scenario_id": "SYN-EVIDENCE-HISTORY-PREPARATION",
            "rule_pack_version": "campaign-replies-1",
            "expected_outcome": "five candidate writing examples",
            "expected_reasons": ["repeated_template", "signature", "forward", "bounced"],
            "expected_persistence_effects": "ten unique records and one duplicate",
            "expected_human_review_state": "candidate corpus requires review",
            "expected_safety_counters": {
                "PRODUCTION_SYSTEM_ACCESS_COUNT": 0, "PRODUCTION_MUTATION_REQUEST_COUNT": 0,
                "REAL_CUSTOMER_IDENTITY_COUNT": 0, "NON_SYNTHETIC_FIXTURE_COUNT": 0,
                "SECRET_MATERIAL_COUNT": 0,
            },
        },
    }

    def chunk(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {"schema_version": 1, "profile": "synthetic", "synthetic_fixture": True,
                "user_id": "SYN-REP-WRITER", "history_through_utc": through,
                "messages": rows}

    return {"report": report, "files": {
        "sent-emails-00001.json": chunk(messages),
        "sent-emails-00002.json": chunk([copy.deepcopy(messages[5])]),
    }}
