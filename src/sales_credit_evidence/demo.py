"""Small synthetic transcript for the offline entry point. No network or auth."""

import json
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .reader import EvidenceReader, EvidenceResult
from .transport import MAILBOX_ID, TARGET_AUTHOR_ID, HttpResponse, ReadClient


def run_demo() -> EvidenceResult:
    email = "customer@example.test"
    customer_id, conversation_id = 10001, 20001
    conversation: dict[str, Any] = {
        "id": conversation_id,
        "number": 40001,
        "mailboxId": MAILBOX_ID,
        "primaryCustomer": {"id": customer_id, "email": email},
        "type": "email",
        "state": "published",
        "status": "closed",
        "threads": 2,
        "userUpdatedAt": "2026-10-01T12:00:00Z",
        "_links": {
            "web": {"href": f"https://secure.helpscout.net/conversation/{conversation_id}/40001/"}
        },
    }
    threads: list[dict[str, Any]] = [
        {
            "id": 30001,
            "type": "message",
            "state": "published",
            "status": "active",
            "createdAt": "2026-09-30T14:00:00Z",
            "createdBy": {"id": TARGET_AUTHOR_ID, "type": "user"},
            "customer": {"id": customer_id},
            "source": {"type": "web", "via": "user"},
            "to": [email],
        },
        {
            "id": 30002,
            "type": "customer",
            "state": "published",
            "status": "active",
            "createdAt": "2026-09-30T15:00:00Z",
            "createdBy": {"id": customer_id, "type": "customer", "email": email},
            "customer": {"id": customer_id},
            "source": {"type": "email", "via": "customer"},
        },
    ]

    def page(key: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "_embedded": {key: records},
            "_links": {},
            "page": {"number": 1, "size": 50, "totalElements": len(records), "totalPages": 1},
        }

    def fake_http(method: str, url: str, headers: dict[str, str]) -> HttpResponse:
        if method != "GET" or headers.get("Authorization"):
            raise AssertionError("offline demo must not authenticate or write")
        parsed = urlsplit(url)
        if parse_qs(parsed.query).get("page", ["1"]) != ["1"]:
            raise AssertionError("unexpected demo pagination")
        routes = {
            "/v2/customers": page("customers", [{"id": customer_id}]),
            f"/v2/customers/{customer_id}/emails": {
                "_embedded": {"emails": [{"id": 50001, "value": email}]},
                "_links": {},
            },
            "/v2/conversations": page("conversations", [conversation]),
            f"/v2/conversations/{conversation_id}": conversation,
            f"/v2/conversations/{conversation_id}/threads": page("threads", threads),
        }
        return HttpResponse(200, {}, json.dumps(routes[parsed.path]).encode())

    return EvidenceReader(ReadClient(email, transport=fake_http)).read(
        order_placed_at="2026-10-01T16:00:00Z"
    )
