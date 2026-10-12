"""Synthetic deferred duplicate review through sealed preflight and the durable journal."""

from __future__ import annotations

import copy
import hashlib
import json
import socket
from datetime import timedelta
from types import SimpleNamespace

import pytest

from doi_draft_transfer import contract
from doi_draft_transfer.service import DraftTransferService
from doi_draft_transfer.store import FILENAME, DraftTransferStore
from sales_credit_evidence import approved_draft, coordinator
from sales_credit_evidence.approved_draft import (
    ApprovedDraftError,
    load_approved_bundle,
    make_approved_bundle,
    prepare_draft,
)
from sales_credit_evidence.draft_preflight import verify_customer_and_duplicates
from sales_credit_evidence.transport import ReadError, SuppliedCredential
from tests.test_doi_draft_transfer import MockClient, csv_text, synthetic_row, verified_review
from tests.test_sales_credit_evidence_coordinator import Harness, request
from tests.test_sales_credit_evidence_draft_preflight import (
    NOW,
    SECRET,
    FakeHttp,
    conversation,
    thread,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Synthetic deferred-review tests cannot open sockets")

    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


def document(pending="SYN pending the coordinator's accessible-mailbox check"):
    review = verified_review()
    review.update(duplicate_status="unresolved", duplicate_evidence=pending)
    return make_approved_bundle(
        synthetic_row(), review, version=2, source_approval_ref="SYN-DEFERRED-APPROVAL"
    )


def write_bundle(tmp_path, value):
    path = tmp_path / "synthetic-deferred-bundle.json"
    raw = contract.encoded(value)
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def bundle(tmp_path, value=None):
    return load_approved_bundle(*write_bundle(tmp_path, document() if value is None else value))


def preflight(approved, now, *, history=False, customer_id=10):
    items = []
    if history:
        items = [
            conversation(
                threads=1, primaryCustomer={"id": customer_id, "email": approved.recipient}
            )
        ]
    fake = FakeHttp(items)
    emails = fake.routes.pop(("/v2/customers/10/emails", 0))
    emails["_embedded"]["emails"][0]["value"] = approved.recipient
    fake.routes[(f"/v2/customers/{customer_id}/emails", 0)] = emails
    fake.routes[("/v2/customers", 1)]["_embedded"]["customers"][0]["id"] = customer_id
    if history:
        fake.add_conversation(items[0], [thread(), thread(1001, type="lineitem")])
    credential = SuppliedCredential(SECRET, NOW + timedelta(hours=1))
    evidence = verify_customer_and_duplicates(
        approved, credential, transport=fake, clock=lambda: now[0]
    )
    assert all(method == "GET" for method, _, _ in fake.calls)
    return evidence


def audit(ready):
    with ready.service.store.transaction() as connection:
        return [
            json.loads(row[0])
            for row in connection.execute("SELECT event_json FROM audit ORDER BY sequence")
        ]


@pytest.mark.parametrize("pending", ["", "SYN duplicate review awaits authenticated preflight"])
def test_ordinary_transfer_service_still_rejects_unresolved_duplicate_approval(tmp_path, pending):
    value = document(pending)
    row, review = value["row"], value["review"]
    client = MockClient()
    service = DraftTransferService(DraftTransferStore(tmp_path / FILENAME), client)
    preview = service.preview_import(csv_text([row]))
    assert preview["can_commit"] and not preview["errors"]
    service.commit_import(preview["preview_token"], preview["revision"])
    item = service.detail(row["order_id"])
    service.edit(
        item["order_id"],
        item["version"],
        {key: row[key] for key in ("selected_body_text", "recipient_email", "reviewer_notes")},
        review,
    )
    item = service.detail(row["order_id"])
    with pytest.raises(contract.TransferError, match="UNRESOLVED_REVIEW_HOLDS"):
        service.approve(
            item["order_id"],
            item["version"],
            item["approval_binding"],
            "I_APPROVE_THIS_EXACT_HELP_SCOUT_DRAFT",
        )
    current = service.detail(row["order_id"])
    assert current["review"] == review and current["approval"] is None
    assert current["transfer"] is None and not client.calls


class _DeferredHarness(Harness):
    """Real bundle, preflight, and transfer service; fake ownership/auth and HTTP only."""

    def __init__(self, tmp_path, value):
        super().__init__()
        self.path, self.digest = write_bundle(tmp_path, value)
        self.ledger = tmp_path / FILENAME
        self.now = [NOW]
        self.credential = SuppliedCredential(SECRET, NOW + timedelta(hours=1))
        self.bundle = None

        owner = self

        class Client(MockClient):
            def check_destination(self):
                owner.assert_held()
                owner.events.append("destination.check")
                return super().check_destination()

            def create_draft(self, row):
                owner.assert_held()
                owner.events.append("draft.post")
                return super().create_draft(row)

            def close(self):
                owner.assert_held()
                owner.events.append("client.close")

        self.client = Client()

    def private_path_validator(self, path):
        self.assert_held()
        assert path in {str(self.path), str(self.ledger)}
        self.private_paths.append(path)
        return path

    def bundle_loader(self, path, digest):
        self.assert_held()
        self.events.append("bundle.load")
        self.bundle = load_approved_bundle(path, digest)
        return self.bundle

    def preflight(self, approved, credential):
        self.assert_held()
        assert self.credit.complete and credential is self.credential
        assert "credit.read" in self.events and "draft.prepare" not in self.events
        self.events.append("draft.preflight")
        self.evidence = preflight(approved, self.now)
        return self.evidence

    def draft_runner(self, approved, ledger_path, *, client, customer_evidence):
        self.assert_held()
        assert "destination.check" in self.events
        self.events.append("draft.prepare")
        self.prepared = prepare_draft(
            approved, ledger_path, client=client, customer_evidence=customer_evidence
        )
        return self.prepared

    def run(self):
        return coordinator.run_coordinator(
            request(
                approval_bundle_path=str(self.path),
                approval_bundle_sha256=self.digest,
                ledger_path=str(self.ledger),
            ),
            cleanup_lease_factory=self.cleanup_factory,
            session_lease_factory=self.session_factory,
            snapshot_owner_factory=self.snapshot_factory,
            bundle_loader=self.bundle_loader,
            reader_factory=self.reader_factory,
            preflight=self.preflight,
            draft_client_factory=self.client_factory,
            draft_runner=self.draft_runner,
            private_path_validator=self.private_path_validator,
            clock=lambda: self.now[0],
        )


@pytest.mark.parametrize("pending", ["", "SYN duplicate review awaits authenticated preflight"])
def test_honest_pending_duplicate_review_completes_only_after_preflight(
    tmp_path, monkeypatch, pending
):
    value = document(pending)
    assert contract.review_holds(value["row"], value["review"]) == [
        "DUPLICATE_RECONCILIATION_REQUIRED"
    ]
    harness = _DeferredHarness(tmp_path, value)
    raw = harness.path.read_bytes()

    class ObservedService(DraftTransferService):
        def preview_import(self, csv_text):
            harness.events.append("import.preview")
            return super().preview_import(csv_text)

        def commit_import(self, token, revision):
            harness.events.append("import.commit")
            return super().commit_import(token, revision)

        def edit(self, oid, version, fields, review):
            harness.events.append("review.edit")
            return super().edit(oid, version, fields, review)

        def approve(self, oid, version, binding, confirmation):
            harness.events.append("draft.approve")
            return super().approve(oid, version, binding, confirmation)

    monkeypatch.setattr(approved_draft.service_api, "DraftTransferService", ObservedService)
    result = harness.run()
    assert result["status"] == "COMPLETE", result
    phases = [
        "bundle.load",
        "snapshot.load",
        "credit.read",
        "draft.preflight",
        "destination.check",
        "draft.prepare",
        "import.preview",
        "import.commit",
        "review.edit",
        "draft.approve",
        "draft.post",
    ]
    positions = [harness.events.index(phase) for phase in phases]
    assert positions == sorted(positions)
    assert harness.snapshot.loads == [(True, False)]
    assert len(harness.client.calls) == 1
    assert harness.path.read_bytes() == raw
    assert harness.bundle._document() == value
    assert harness.prepared.source_binding == value["approval_binding"]
    assert harness.prepared.binding != harness.prepared.source_binding
    assert [event["kind"] for event in audit(harness.prepared)] == [
        "IMPORTED",
        "EDIT_APPROVAL_INVALIDATED",
        "COORDINATOR_DUPLICATE_PREFLIGHT",
        "EXACT_DRAFT_APPROVED",
        "TRANSFER_RESERVED",
        "TRANSFER_RESULT",
    ]
    assert result["draft_preflight"]["global_draft_absence_proved"] is False
    for private in (value["recipient"], value["subject"], pending or "SYN-DEFERRED-APPROVAL"):
        assert private not in json.dumps(result)


@pytest.mark.parametrize(
    "held",
    [
        "fitment",
        "recipient",
        "cart",
        "customer_approval",
        "owner",
        "closed",
        "existing_draft",
        "empty_success",
    ],
)
def test_other_holds_and_unsupported_duplicate_claims_block_before_auth(tmp_path, held):
    value = document()
    review, row = value["review"], value["row"]
    if held == "fitment":
        review["checks"]["fitment"]["resolved"] = False
    elif held == "recipient":
        review["recipient_verified"] = False
    elif held == "cart":
        review["carts"]["SYN-OPTION-1"]["verified"] = False
    elif held == "customer_approval":
        review["checks"]["customer_approval"]["decision"] = "unreviewed"
    elif held == "owner":
        row["current_rep"] = "SYN-another-rep"
    elif held == "closed":
        row["current_order_status"] = "Closed"
    elif held == "existing_draft":
        review["duplicate_status"] = "existing_draft_found"
    else:
        review.update(duplicate_status="no_existing_draft", duplicate_evidence="")
    with pytest.raises(ApprovedDraftError, match="APPROVED_REVIEW_HOLDS"):
        make_approved_bundle(
            row, review, version=2, source_approval_ref=value["source_approval_ref"]
        )
    value["approval_binding"] = contract.approval_binding(row, 2, review)
    harness = _DeferredHarness(tmp_path, value)
    result = harness.run()
    assert result["status"] == "BLOCKED"
    assert result["issues"] == ["APPROVED_REVIEW_HOLDS"]
    assert not harness.snapshot.loads
    assert "snapshot.factory" not in harness.events and "credit.read" not in harness.events
    assert not harness.client.calls and not harness.ledger.exists()


@pytest.mark.parametrize(
    "untrusted", [None, True, {"complete": True}, SimpleNamespace(complete=True)]
)
def test_pending_review_requires_sealed_customer_evidence_before_ledger(tmp_path, untrusted):
    approved = bundle(tmp_path)
    with pytest.raises(ApprovedDraftError, match="APPROVED_CUSTOMER_EVIDENCE_REQUIRED"):
        prepare_draft(
            approved, tmp_path / FILENAME, client=MockClient(), customer_evidence=untrusted
        )
    assert not (tmp_path / FILENAME).exists()


@pytest.mark.parametrize("issue", ["draft_existing_draft", "draft_preflight_incomplete"])
def test_failed_live_preflight_cannot_clear_pending_duplicate_review(tmp_path, issue):
    harness = _DeferredHarness(tmp_path, document())
    original = harness.path.read_bytes()

    def rejected(approved, credential):
        harness.assert_held()
        harness.events.append("draft.preflight")
        fake = FakeHttp(
            [conversation(state="draft", primaryCustomer={"id": 10, "email": approved.recipient})]
            if issue == "draft_existing_draft"
            else []
        )
        fake.routes[("/v2/customers/10/emails", 0)]["_embedded"]["emails"][0]["value"] = (
            approved.recipient
        )
        if issue == "draft_preflight_incomplete":
            fake.routes[("/v2/conversations", 1)]["page"]["totalElements"] = 1
        return verify_customer_and_duplicates(
            approved, credential, transport=fake, clock=lambda: harness.now[0]
        )

    harness.preflight = rejected
    result = harness.run()
    assert result["status"] == "INCOMPLETE" and result["issues"] == [issue]
    assert "credit.read" in harness.events and "draft.prepare" not in harness.events
    assert not harness.ledger.exists() and not harness.client.calls
    assert harness.path.read_bytes() == original


@pytest.mark.parametrize("prepared_first", [False, True])
def test_stale_real_proof_cannot_complete_pending_review_or_transfer(tmp_path, prepared_first):
    approved = bundle(tmp_path)
    now, client = [NOW], MockClient()
    evidence = preflight(approved, now)
    if prepared_first:
        ready = prepare_draft(
            approved, tmp_path / FILENAME, client=client, customer_evidence=evidence
        )
    now[0] += timedelta(seconds=120)
    with pytest.raises(ReadError, match="draft_evidence_stale"):
        if prepared_first:
            ready.execute_once()
        else:
            prepare_draft(approved, tmp_path / FILENAME, client=client, customer_evidence=evidence)
    assert not client.calls
    if not prepared_first:
        assert not (tmp_path / FILENAME).exists()


def test_real_proof_is_bound_to_exact_source_file(tmp_path):
    original = bundle(tmp_path)
    evidence = preflight(original, [NOW])
    changed = document("SYN a different pending explanation")
    incoming = bundle(tmp_path, changed)
    with pytest.raises(ReadError, match="draft_evidence_bundle_mismatch"):
        prepare_draft(
            incoming, tmp_path / FILENAME, client=MockClient(), customer_evidence=evidence
        )
    assert not (tmp_path / FILENAME).exists()


def test_proof_expiring_during_import_cannot_record_final_approval(tmp_path, monkeypatch):
    approved = bundle(tmp_path)
    now, client = [NOW], MockClient()
    evidence = preflight(approved, now)
    services = []

    class ExpiringService(DraftTransferService):
        def edit(self, oid, version, fields, review):
            result = super().edit(oid, version, fields, review)
            services.append(self)
            now[0] += timedelta(seconds=120)
            return result

    monkeypatch.setattr(approved_draft.service_api, "DraftTransferService", ExpiringService)
    with pytest.raises(ReadError, match="draft_evidence_stale"):
        prepare_draft(approved, tmp_path / FILENAME, client=client, customer_evidence=evidence)
    assert len(services) == 1 and not client.calls
    record = services[0].detail(approved.order_id)
    assert record["approval"] is None and record["transfer"] is None
    with services[0].store.transaction() as connection:
        kinds = [
            json.loads(row[0])["kind"]
            for row in connection.execute("SELECT event_json FROM audit ORDER BY sequence")
        ]
    assert "EXACT_DRAFT_APPROVED" not in kinds and "TRANSFER_RESERVED" not in kinds


def test_completed_review_changes_only_duplicate_fields_and_audits_scoped_proof(tmp_path):
    value = document()
    original = copy.deepcopy(value)
    approved = bundle(tmp_path, value)
    now = [NOW]
    evidence = preflight(approved, now, history=True)
    ready = prepare_draft(
        approved, tmp_path / FILENAME, client=MockClient(), customer_evidence=evidence
    )
    record = ready.service.detail(approved.order_id)
    assert record["row"] == original["row"]
    expected_review = copy.deepcopy(original["review"])
    expected_review.update(
        duplicate_status="no_existing_draft",
        duplicate_evidence=record["review"]["duplicate_evidence"],
    )
    assert record["review"] == expected_review
    assert contract.review_holds(record["row"], record["review"]) == []
    assert record["approval"]["binding"] == ready.binding
    assert ready.binding == contract.approval_binding(record["row"], 2, record["review"])
    assert approved.binding == ready.source_binding == original["approval_binding"]
    assert approved._document() == original == value
    finding = json.loads(record["review"]["duplicate_evidence"])
    assert finding == {
        "schema": "coordinator-duplicate-preflight/v1",
        "source_bundle_sha256": approved.bundle_sha256,
        "source_approval_binding": approved.binding,
        "source_approval_ref": original["source_approval_ref"],
        "duplicate_check": "NO_MATCH_IN_ACCESSIBLE_MAILBOX_SNAPSHOT",
        "global_draft_absence_proved": False,
        "mailbox_id": contract.MAILBOX_ID,
        "customer_id": evidence.customer_id,
    }
    events = audit(ready)
    assert events[2]["kind"] == "COORDINATOR_DUPLICATE_PREFLIGHT"
    assert events[2]["details"] == {
        **finding,
        "execution_approval_binding": ready.binding,
        "observed_at": NOW.isoformat(),
        "conversation_count": 1,
        "thread_count": 2,
    }
    assert events[3]["kind"] == "EXACT_DRAFT_APPROVED"
    assert original["row"]["selected_body_text"] not in json.dumps(events[2])
    assert original["recipient"] not in json.dumps(events[2])


@pytest.mark.parametrize(
    "conflict", ["changed_identity", "changed_source", "missing_audit", "invalid_audit"]
)
def test_existing_ledger_requires_exact_execution_and_source_provenance(tmp_path, conflict):
    approved = bundle(tmp_path)
    now, client = [NOW], MockClient()
    ready = prepare_draft(
        approved, tmp_path / FILENAME, client=client, customer_evidence=preflight(approved, now)
    )
    customer_id = 10
    if conflict == "changed_identity":
        customer_id = 11
    elif conflict == "changed_source":
        value = document()
        value = make_approved_bundle(
            value["row"], value["review"], version=2, source_approval_ref="SYN-OTHER-APPROVAL"
        )
        approved = bundle(tmp_path, value)
    elif conflict == "missing_audit":
        with ready.service.store.transaction(write=True) as connection:
            connection.execute("DELETE FROM audit WHERE sequence=3")
    else:
        event = audit(ready)[2]
        event["details"]["observed_at"] = "SYN invalid observation time"
        with ready.service.store.transaction(write=True) as connection:
            connection.execute(
                "UPDATE audit SET event_json=? WHERE sequence=3",
                (contract.encoded(event).decode(),),
            )
    before = (tmp_path / FILENAME).read_bytes()
    with pytest.raises(ApprovedDraftError, match=r"APPROVED_LEDGER_(APPROVAL_)?CONFLICT"):
        prepare_draft(
            approved,
            tmp_path / FILENAME,
            client=client,
            customer_evidence=preflight(approved, now, customer_id=customer_id),
        )
    assert not client.calls
    assert (tmp_path / FILENAME).read_bytes() == before


def test_unattempted_exact_row_reopens_with_later_fresh_proof_without_reapproving(tmp_path):
    approved = bundle(tmp_path)
    now, client = [NOW], MockClient()
    ready = prepare_draft(
        approved, tmp_path / FILENAME, client=client, customer_evidence=preflight(approved, now)
    )
    before = audit(ready)
    now[0] += timedelta(seconds=1)
    reopened = prepare_draft(
        approved, tmp_path / FILENAME, client=client, customer_evidence=preflight(approved, now)
    )
    assert reopened.binding == ready.binding and audit(reopened) == before
    assert reopened.execute_once()["state"] == "CREATED"
    assert len(client.calls) == 1


@pytest.mark.parametrize("state", ["UNKNOWN", "IN_FLIGHT"])
def test_deferred_review_terminal_journal_outcomes_never_repeat_after_reopen(tmp_path, state):
    approved = bundle(tmp_path)
    now, client = [NOW], MockClient()
    ready = prepare_draft(
        approved, tmp_path / FILENAME, client=client, customer_evidence=preflight(approved, now)
    )
    if state == "UNKNOWN":
        client.result = {"state": state, "code": "WRITE_OUTCOME_UNKNOWN", "retry_allowed": False}
        assert ready.execute_once()["state"] == state
    else:
        with ready.service.store.transaction(write=True) as connection:
            ready.service.store.transfer(
                connection, approved.order_id, {"state": state, "retry_allowed": False}
            )
    calls = len(client.calls)
    events_before = audit(ready)
    now[0] += timedelta(seconds=1)
    reopened = prepare_draft(
        approved, tmp_path / FILENAME, client=client, customer_evidence=preflight(approved, now)
    )
    assert reopened.binding == ready.binding
    for _ in range(3):
        outcome = reopened.execute_once()
        assert outcome["state"] == state and outcome["retry_allowed"] is False
    assert len(client.calls) == calls == (1 if state == "UNKNOWN" else 0)
    assert audit(reopened) == events_before
