"""Real coordinator components, synthetic HTTP/auth, and a temporary durable ledger.

Replay deliberately repeats the old empty search snapshot: the durable transfer
reservation, independently of remote search visibility, must prevent a second POST.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

from doi_draft_transfer import contract
from doi_draft_transfer.store import FILENAME, DraftTransferStore
from sales_credit_evidence.approved_draft import ApprovedDraft, make_approved_bundle
from sales_credit_evidence.coordinator import CoordinatorRequest, run_coordinator
from sales_credit_evidence.draft_preflight import DraftCustomerEvidence
from sales_credit_evidence.one_draft_client import OneDraftClient
from sales_credit_evidence.session_snapshot import SessionSnapshotOwner
from sales_credit_evidence.transport import (
    MAILBOX_ID,
    TARGET_AUTHOR_ID,
    HttpResponse,
    SuppliedCredential,
)
from tests.test_doi_draft_transfer import synthetic_row, verified_review

NOW = datetime(2026, 10, 12, 18, tzinfo=UTC)
CREDIT_EMAIL = "credit-e2e@example.test"
CREDIT_CUSTOMER = 99001001
DRAFT_CUSTOMER = 99001002
CREATED_CONVERSATION = 99001003
CONNECTION_PATH = r"C:\synthetic-e2e\snapshot.dpapi"
CLEANUP_LOCK = r"C:\synthetic-e2e\cleanup.lock"


def page(key: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "_embedded": {key: records},
        "page": {"number": 1, "size": 25, "totalElements": len(records), "totalPages": 1},
        "_links": {},
    }


class FakeLease:
    def __init__(self, harness: Harness, name: str) -> None:
        self.harness = harness
        self.name = name
        self.held = False

    def acquire(self) -> None:
        if self.name == "session":
            assert self.harness.cleanup is not None and self.harness.cleanup.held
        self.harness.events.append(self.name + ".acquire")
        self.held = True

    def close(self) -> None:
        if self.name == "cleanup":
            assert self.harness.session is not None and not self.harness.session.held
        self.harness.events.append(self.name + ".close")
        self.held = False


class Harness:
    def __init__(self, tmp_path: Path, *, unknown_post: bool = False) -> None:
        self.row = synthetic_row()
        approved_document = make_approved_bundle(
            self.row, verified_review(), version=2, source_approval_ref="SYN-E2E-APPROVAL-001"
        )
        raw = contract.encoded(approved_document)
        self.bundle_path = tmp_path / "synthetic-approved.json"
        self.bundle_path.write_bytes(raw)
        self.bundle_hash = hashlib.sha256(raw).hexdigest()
        self.ledger_path = tmp_path / FILENAME
        self.unknown_post = unknown_post
        self.events: list[str] = []
        self.cleanup: FakeLease | None = None
        self.session: FakeLease | None = None
        self.plaintexts: list[bytearray] = []
        self.owners: list[SessionSnapshotOwner] = []
        self.credentials: list[SuppliedCredential] = []
        self.post_payloads: list[dict[str, Any]] = []
        self.auth_reads = 0
        self.decryptions = 0
        self.issuer_calls = 0
        self.readback_calls = 0
        self.read_calls: list[tuple[str, str, dict[str, list[str]]]] = []

    def request(self) -> CoordinatorRequest:
        return CoordinatorRequest(
            credit_email=CREDIT_EMAIL,
            connection_path=CONNECTION_PATH,
            cleanup_lock_path=CLEANUP_LOCK,
            approval_bundle_path=str(self.bundle_path),
            approval_bundle_sha256=self.bundle_hash,
            ledger_path=str(self.ledger_path),
            enable_live=True,
            allow_issuance=False,
            allow_draft=True,
            ownership="cleanup-complete",
            sole_owner_confirmed=True,
        )

    def assert_held(self) -> None:
        assert self.cleanup is not None and self.cleanup.held
        assert self.session is not None and self.session.held

    def cleanup_factory(self, connection_path: str, cleanup_lock_path: str) -> FakeLease:
        assert connection_path == CONNECTION_PATH and cleanup_lock_path == CLEANUP_LOCK
        self.cleanup = FakeLease(self, "cleanup")
        return self.cleanup

    def session_factory(self) -> FakeLease:
        assert self.cleanup is not None and self.cleanup.held
        self.session = FakeLease(self, "session")
        return self.session

    def read_encrypted(self, path: str) -> bytes:
        self.assert_held()
        assert path == CONNECTION_PATH
        self.auth_reads += 1
        self.events.append("snapshot.read")
        return b"synthetic-encrypted"

    def decrypt(self, raw: bytes) -> bytearray:
        self.assert_held()
        assert raw == b"synthetic-encrypted"
        self.decryptions += 1
        value = {
            "client_id": "test-id",
            "client_secret": "test-secret",
            "access_token": "test-token",
            "expires_at": (NOW + timedelta(hours=1)).timestamp(),
            "user_id": TARGET_AUTHOR_ID,
        }
        plain = bytearray(json.dumps(value).encode())
        self.plaintexts.append(plain)
        return plain

    def issuer(self, _fields: dict[str, str]) -> dict[str, Any]:
        self.issuer_calls += 1
        raise AssertionError("valid cached snapshot must never issue")

    def snapshot_factory(self, path: str) -> SessionSnapshotOwner:
        self.assert_held()
        owner = SessionSnapshotOwner(
            path,
            clock=lambda: NOW,
            encrypted_loader=self.read_encrypted,
            decryptor=self.decrypt,
            issuer=self.issuer,
        )
        self.owners.append(owner)
        return owner

    def read_transport(self, method: str, url: str, headers: dict[str, str]) -> HttpResponse:
        self.assert_held()
        assert method == "GET" and headers["Authorization"] == "Bearer test-token"
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        self.read_calls.append((method, parsed.path, query))
        emails = {CREDIT_CUSTOMER: CREDIT_EMAIL, DRAFT_CUSTOMER: self.row["recipient_email"]}
        if parsed.path == "/v2/customers":
            assert query["mailbox"] == [str(MAILBOX_ID)] and query["page"] == ["1"]
            matching = [
                key for key, email in emails.items() if query["query"] == [f'(email:"{email}")']
            ]
            assert len(matching) == 1
            identifier = matching[0]
            self.events.append("credit.search" if identifier == CREDIT_CUSTOMER else "draft.search")
            value = page("customers", [{"id": identifier}])
        elif parsed.path.endswith("/emails"):
            identifier = int(parsed.path.split("/")[-2])
            assert not query and identifier in emails
            value = {
                "_embedded": {"emails": [{"id": identifier + 100, "value": emails[identifier]}]},
                "_links": {},
            }
        elif parsed.path == "/v2/conversations":
            assert query["mailbox"] == [str(MAILBOX_ID)] and query["status"] == ["all"]
            assert query["query"] in (
                [f"(customerIds:{CREDIT_CUSTOMER})"],
                [f"(customerIds:{DRAFT_CUSTOMER})"],
            )
            self.events.append(
                "credit.complete"
                if query["query"] == [f"(customerIds:{CREDIT_CUSTOMER})"]
                else "draft.preflight.complete"
            )
            # Repeat this old snapshot on replay to exercise the durable ledger,
            # even if remote search visibility has not caught up with creation.
            value = page("conversations", [])
        else:
            raise AssertionError("unexpected read endpoint")
        return HttpResponse(200, {}, json.dumps(value).encode())

    def draft_factory(
        self,
        bundle: ApprovedDraft,
        evidence: DraftCustomerEvidence,
        credential: SuppliedCredential,
    ) -> OneDraftClient:
        self.assert_held()
        assert type(bundle) is ApprovedDraft and type(evidence) is DraftCustomerEvidence
        assert evidence.customer_id == DRAFT_CUSTOMER
        assert evidence.summary()["complete"] is True
        assert "credit.complete" in self.events and "draft.preflight.complete" in self.events
        self.credentials.append(credential)
        return OneDraftClient(
            bundle, evidence, credential, clock=lambda: NOW, transport=self.draft_transport
        )

    def persisted(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        store = DraftTransferStore(self.ledger_path)
        with store.transaction() as connection:
            record = store.load(connection, self.row["order_id"])
            assert record is not None
            events = [
                json.loads(row[0])
                for row in connection.execute("SELECT event_json FROM audit ORDER BY sequence")
            ]
        return record, events

    def draft_transport(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        bearer: str,
    ) -> tuple[int, dict[str, str], bytes]:
        self.assert_held()
        assert bearer == "test-token"
        self.events.append("draft.http." + method)
        if method == "GET" and path in (
            f"/v2/mailboxes/{MAILBOX_ID}",
            f"/v2/users/{TARGET_AUTHOR_ID}",
        ):
            assert payload is None
            return 200, {}, json.dumps({"id": int(path.rsplit("/", 1)[1])}).encode()
        if method == "POST" and path == "/v2/conversations":
            assert payload is not None
            # A fresh connection sees the committed reservation BEFORE fake HTTP.
            persisted, audit = self.persisted()
            assert persisted["transfer"]["state"] == "IN_FLIGHT"
            assert persisted["transfer"]["attempt"] == 1
            assert sum(event["kind"] == "TRANSFER_RESERVED" for event in audit) == 1
            assert payload["customer"] == {"id": DRAFT_CUSTOMER}
            assert payload["threads"][0]["customer"] == {"id": DRAFT_CUSTOMER}
            assert payload["threads"][0]["draft"] is True and payload["autoReply"] is False
            assert len(payload["threads"]) == 1
            assert payload["threads"][0]["text"] == contract.rendered_body(
                self.row["selected_body_text"]
            )
            self.post_payloads.append(payload)
            if self.unknown_post:
                raise TimeoutError("synthetic response lost after POST")
            return 201, {"resource-id": str(CREATED_CONVERSATION)}, b""
        assert method == "GET" and path == f"/v2/conversations/{CREATED_CONVERSATION}?embed=threads"
        assert payload is None
        self.readback_calls += 1
        value = {
            "id": CREATED_CONVERSATION,
            "state": "draft",
            "mailboxId": MAILBOX_ID,
            "subject": self.row["subject"],
            "assignee": {"id": TARGET_AUTHOR_ID},
            "primaryCustomer": {"id": DRAFT_CUSTOMER, "email": self.row["recipient_email"]},
            "_embedded": {
                "threads": [
                    {
                        "type": "message",
                        "state": "draft",
                        "createdBy": {"id": TARGET_AUTHOR_ID},
                        "to": [self.row["recipient_email"]],
                        "body": contract.rendered_body(self.row["selected_body_text"]),
                    }
                ]
            },
        }
        return 200, {}, json.dumps(value).encode()

    def run(self, request: CoordinatorRequest | None = None) -> dict[str, Any]:
        with patch(
            "http.client.HTTPSConnection", side_effect=AssertionError("live HTTP forbidden")
        ):
            result = run_coordinator(
                self.request() if request is None else request,
                cleanup_lease_factory=self.cleanup_factory,
                session_lease_factory=self.session_factory,
                snapshot_owner_factory=self.snapshot_factory,
                draft_client_factory=self.draft_factory,
                transport=self.read_transport,
                clock=lambda: NOW,
            )
        if self.cleanup is not None:
            assert not self.cleanup.held and self.session is not None and not self.session.held
            assert self.events[-2:] == ["session.close", "cleanup.close"]
        assert all(not any(plain) for plain in self.plaintexts)
        assert self.issuer_calls == 0
        return result


@pytest.mark.parametrize("unknown_post", [False, True], ids=["verified-draft", "unknown-post"])
def test_real_coordinator_persists_one_attempt_and_replay_cannot_post_again(
    tmp_path: Path,
    unknown_post: bool,
) -> None:
    harness = Harness(tmp_path, unknown_post=unknown_post)
    first = harness.run()
    assert first["credit_summary"] is not None, first["issues"]
    expected_state = "UNKNOWN" if unknown_post else "CREATED"
    expected_code = "WRITE_OUTCOME_UNKNOWN" if unknown_post else "DRAFT_CREATED_VERIFIED"
    assert first["status"] == ("INCOMPLETE" if unknown_post else "COMPLETE"), first
    assert first["credit_summary"]["identity_status"] == "EXACT"
    assert first["credit_summary"]["complete"] is True
    assert first["credit_classification"] == "NOT_EVALUATED"
    assert first["draft_result"]["state"] == expected_state
    assert first["draft_result"]["code"] == expected_code
    assert first["draft_result"]["retry_allowed"] is False
    assert first["issuance_attempted"] is False
    assert len(harness.post_payloads) == 1
    assert harness.readback_calls == (0 if unknown_post else 1)
    assert len(harness.read_calls) == 6
    assert harness.events.index("credit.complete") < harness.events.index("draft.search")
    assert harness.events.index("draft.preflight.complete") < harness.events.index(
        "draft.http.POST"
    )
    stored, audit = harness.persisted()
    assert stored["transfer"]["state"] == expected_state
    assert stored["transfer"]["attempt"] == 1
    assert sum(event["kind"] == "TRANSFER_RESERVED" for event in audit) == 1
    assert sum(event["kind"] == "TRANSFER_RESULT" for event in audit) == 1

    # New coordinator, owner, reader, preflight, client, and store instances;
    # only the approved bundle and on-disk journal survive this replay.
    second = harness.run()
    assert second["draft_result"] == first["draft_result"]
    assert second["status"] == first["status"]
    assert len(harness.post_payloads) == 1
    assert harness.readback_calls == (0 if unknown_post else 1)
    assert harness.auth_reads == harness.decryptions == len(harness.owners) == 2
    assert len(harness.read_calls) == 12
    assert not any(owner.issuance_attempted for owner in harness.owners)
    final_record, final_audit = harness.persisted()
    assert final_record["transfer"] == stored["transfer"]
    assert final_audit == audit
    assert b"test-token" not in harness.ledger_path.read_bytes()
    assert b"test-secret" not in harness.ledger_path.read_bytes()


def test_coordinator_remains_default_off_before_auth_or_ledger_access(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    result = harness.run(replace(harness.request(), enable_live=False))
    assert result["status"] == "DISABLED"
    assert harness.events == [] and harness.auth_reads == 0
    assert harness.read_calls == [] and harness.post_payloads == []
    assert not harness.ledger_path.exists()
