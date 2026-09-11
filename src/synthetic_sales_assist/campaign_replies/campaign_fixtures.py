"""Generated reserved-identity campaign fixtures; never copied customer records."""

from __future__ import annotations

from typing import Any


def demo_manifest(count: int = 5) -> dict[str, Any]:
    """The reusable v1 synthetic preparation contract (not a legacy sender manifest)."""
    return {
        "schema_version": 1,
        "profile": "synthetic",
        "synthetic_fixture": True,
        "scenario_id": "SYN-EVIDENCE-CAMPAIGN-DEMO",
        "rule_pack_version": "synthetic-campaign/v1",
        "expected_outcome": "SIMULATED_ACCEPTED",
        "expected_reasons": ["reserved_identity", "fresh_history"],
        "expected_persistence_effects": "immutable_intent_before_creation",
        "expected_human_review_state": "delivery_unverified",
        "expected_safety_counters": {
            "PRODUCTION_SYSTEM_ACCESS_COUNT": 0,
            "PRODUCTION_MUTATION_REQUEST_COUNT": 0,
            "REAL_CUSTOMER_IDENTITY_COUNT": 0,
            "NON_SYNTHETIC_FIXTURE_COUNT": 0,
            "SECRET_MATERIAL_COUNT": 0,
        },
        "campaign_id": "SYN-RUN-CAMPAIGN-DEMO",
        "sender_id": "SYN-REP-DEMO",
        "inbox_id": "SYN-INTERACTION-INBOX-DEMO",
        "subject": "Synthetic cart assistance",
        "template": "Hello,\n\nYour synthetic cart is available here:\n\n{cart_url}\n\n"
        "Reply if you would like help with these sample items.\n\nSynthetic Sales Assist",
        "records": [
            {
                "queue_key": f"SYN-EVIDENCE-QUEUE-{index:05d}",
                "customer_id": f"SYN-CUSTOMER-CAMPAIGN-{index:05d}",
                "email": f"synthetic-customer-{index}@example.test",
                "original_rank": index,
                "cart_total_cents": (count - index + 1) * 10000,
                "cart_url": f"http://localhost/cart?product=SYN-SKU-{index}&qty=1"
                "&pdk=SYN-EVIDENCE-OPTION&utm_source=synthetic&utm_medium=email"
                "&utm_content=link2cart&salesrep=SYN-REP-DEMO",
                "pilot_record": index == 1,
                "address_review": False,
                "excluded": False,
                "eligibility": "eligible",
            }
            for index in range(1, count + 1)
        ],
    }


def seed_demo(service: Any) -> str:
    manifest = demo_manifest()
    service.prepare_audience(manifest)
    return str(manifest["campaign_id"])
