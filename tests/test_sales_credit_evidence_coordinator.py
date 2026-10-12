"""Coordinator integration with synthetic, in-memory ownership and I/O boundaries."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from sales_credit_evidence import coordinator
from sales_credit_evidence.reader import Coverage, CustomerIdentity, EvidenceResult, Issue
from sales_credit_evidence.transport import ReadError, SuppliedCredential

EMAIL = "credit-synthetic@example.test"
DRAFT_EMAIL = "draft-synthetic@example.test"
CONNECTION = r"C:\synthetic-coordinator\connection.dpapi"
CLEANUP_LOCK = r"C:\synthetic-coordinator\cleanup.lock"
BUNDLE = r"C:\synthetic-coordinator\approved.json"
LEDGER = r"C:\synthetic-coordinator\doi-draft-transfer.sqlite3"
DIGEST = "a" * 64
PRIVATE = "synthetic-private-content"
TOKEN = "test-token"
NOW = datetime(2026, 10, 12, 18, tzinfo=UTC)


def request(**changes):
    values = {
        "credit_email": EMAIL,
        "connection_path": CONNECTION,
        "cleanup_lock_path": CLEANUP_LOCK,
        "approval_bundle_path": BUNDLE,
        "approval_bundle_sha256": DIGEST,
        "ledger_path": LEDGER,
        "enable_live": True,
        "allow_issuance": False,
        "allow_draft": True,
        "ownership": "cleanup-complete",
        "sole_owner_confirmed": True,
    }
    values.update(changes)
    return coordinator.CoordinatorRequest(**values)


def credit_result(identity_status="EXACT", complete=True):
    customers = (
        () if identity_status == "NO_EXACT_CUSTOMER" else (CustomerIdentity(10, (EMAIL,), (110,)),)
    )
    return EvidenceResult(
        identity_status,
        customers,
        (),
        (Coverage("customers", None, complete, 1, len(customers), len(customers)),),
        () if complete else (Issue("SYNTHETIC_PARTIAL", "customers"),),
        EMAIL,
    )


class FakeLease:
    def __init__(self, owner, name):
        self.owner = owner
        self.name = name
        self.held = False
        self.close_calls = 0

    def acquire(self):
        self.owner.events.append(self.name + ".acquire")
        if self.name == "session":
            assert self.owner.cleanup.held
        if error := self.owner.failures.get(self.name + ".acquire"):
            raise error
        self.held = True

    def close(self):
        self.owner.events.append(self.name + ".close")
        self.close_calls += 1
        self.held = False
        if error := self.owner.failures.get(self.name + ".close"):
            raise error


class FakeSnapshot:
    def __init__(self, owner):
        self.owner = owner
        self.loads = []
        self.close_calls = 0
        self.issuance_attempted = False

    def load(self, *, enable_live, allow_issuance):
        self.owner.assert_held()
        self.owner.events.append("snapshot.load")
        assert enable_live is True
        self.loads.append((enable_live, allow_issuance))
        self.issuance_attempted = self.owner.simulated_issuance
        if error := self.owner.failures.get("snapshot.load"):
            raise error
        return self.owner.credential

    def close(self):
        self.owner.assert_held()
        self.owner.events.append("snapshot.close")
        self.close_calls += 1
        if error := self.owner.failures.get("snapshot.close"):
            raise error


class FakeEvidence:
    customer_id = 20

    def __init__(self, owner):
        self.owner = owner

    def assert_for(self, bundle):
        assert bundle is self.owner.bundle

    def summary(self):
        return {
            "identity_status": "EXACT",
            "complete": True,
            "customer_count": 1,
            "conversation_count": 0,
            "thread_count": 0,
        }


class FakeClient:
    def __init__(self, owner):
        self.owner = owner
        self.close_calls = 0

    def check_destination(self):
        self.owner.assert_held()
        self.owner.events.append("destination.check")
        if error := self.owner.failures.get("destination.check"):
            raise error
        return None

    def close(self):
        self.owner.assert_held()
        self.owner.events.append("client.close")
        self.close_calls += 1
        if error := self.owner.failures.get("client.close"):
            raise error


class FakePrepared:
    def __init__(self, owner):
        self.owner = owner
        self.execute_calls = 0

    def execute_once(self):
        self.owner.assert_held()
        self.owner.events.append("draft.execute")
        self.execute_calls += 1
        assert self.execute_calls == 1, "coordinator must never replay a write attempt"
        if error := self.owner.failures.get("draft.execute"):
            raise error
        return dict(self.owner.draft_result)


class Harness:
    def __init__(self):
        self.events = []
        self.failures = {}
        self.cleanup = FakeLease(self, "cleanup")
        self.session = FakeLease(self, "session")
        self.snapshot = FakeSnapshot(self)
        self.client = FakeClient(self)
        self.prepared = FakePrepared(self)
        self.evidence = FakeEvidence(self)
        self.bundle = SimpleNamespace(
            order_id="12345",
            recipient=DRAFT_EMAIL,
            subject="Synthetic review",
            bundle_sha256=DIGEST,
        )
        self.credential = SuppliedCredential(TOKEN, NOW + timedelta(hours=1))
        self.credit = credit_result()
        self.draft_result = {
            "state": "CREATED",
            "code": "DRAFT_CREATED_VERIFIED",
            "conversation_id": "12345",
            "retry_allowed": False,
        }
        self.simulated_issuance = False
        self.read_credentials = []
        self.private_paths = []

    def assert_held(self):
        assert self.cleanup.held and self.session.held

    def _factory_failure(self, name):
        self.events.append(name)
        if error := self.failures.get(name):
            raise error

    def cleanup_factory(self, connection_path, cleanup_lock_path):
        assert connection_path == CONNECTION and cleanup_lock_path == CLEANUP_LOCK
        self._factory_failure("cleanup.factory")
        return self.cleanup

    def session_factory(self):
        assert self.cleanup.held
        self._factory_failure("session.factory")
        return self.session

    def bundle_loader(self, bundle_path, bundle_sha256):
        self.assert_held()
        assert self.private_paths == [BUNDLE, LEDGER]
        assert bundle_path == BUNDLE and bundle_sha256 == DIGEST
        self._factory_failure("bundle.load")
        return self.bundle

    def private_path_validator(self, path):
        self.assert_held()
        assert path in {BUNDLE, LEDGER}
        assert "bundle.load" not in self.events and not self.snapshot.loads
        self.private_paths.append(path)
        if error := self.failures.get("private_path:" + path):
            raise error
        return path

    def snapshot_factory(self, connection_path):
        self.assert_held()
        assert connection_path == CONNECTION
        assert "bundle.load" in self.events
        self._factory_failure("snapshot.factory")
        return self.snapshot

    def reader_factory(self, email, credential):
        self.assert_held()
        assert email == EMAIL and credential is self.credential
        self.read_credentials.append(credential)
        self._factory_failure("credit.read")
        return self.credit

    def preflight(self, bundle, credential):
        self.assert_held()
        assert bundle is self.bundle and credential is self.credential
        assert self.credit.complete
        self.read_credentials.append(credential)
        self._factory_failure("draft.preflight")
        return self.evidence

    def client_factory(self, bundle, evidence, credential):
        self.assert_held()
        assert bundle is self.bundle and evidence is self.evidence
        assert credential is self.credential
        self.read_credentials.append(credential)
        self._factory_failure("client.factory")
        return self.client

    def draft_runner(self, bundle, ledger_path, *, client, customer_evidence):
        self.assert_held()
        assert bundle is self.bundle and ledger_path == LEDGER
        assert client is self.client and customer_evidence is self.evidence
        assert "draft.preflight" in self.events and "destination.check" in self.events
        self._factory_failure("draft.prepare")
        return self.prepared

    def run(self, value=None):
        return coordinator.run_coordinator(
            request() if value is None else value,
            cleanup_lease_factory=self.cleanup_factory,
            session_lease_factory=self.session_factory,
            snapshot_owner_factory=self.snapshot_factory,
            bundle_loader=self.bundle_loader,
            reader_factory=self.reader_factory,
            preflight=self.preflight,
            draft_client_factory=self.client_factory,
            draft_runner=self.draft_runner,
            private_path_validator=self.private_path_validator,
            clock=lambda: NOW,
        )


def assert_private(result):
    output = json.dumps(result)
    for private in (EMAIL, DRAFT_EMAIL, CONNECTION, CLEANUP_LOCK, BUNDLE, LEDGER, TOKEN, PRIVATE):
        assert private not in output
    assert result["credit_classification"] == "NOT_EVALUATED"


def test_request_is_frozen_with_sensitive_fields_hidden_from_repr():
    value = request()
    for private in (EMAIL, CONNECTION, CLEANUP_LOCK, BUNDLE, DIGEST, LEDGER):
        assert private not in repr(value)
    with pytest.raises(FrozenInstanceError):
        value.enable_live = False


def test_disabled_coordinator_has_no_factory_or_io_calls():
    harness = Harness()
    result = harness.run(request(enable_live=False, allow_draft=False))
    assert result["status"] == "DISABLED" and harness.events == []
    assert harness.private_paths == []
    assert_private(result)


@pytest.mark.parametrize(
    "changes",
    [
        {"ownership": ""},
        {"ownership": "cleanup-running"},
        {"sole_owner_confirmed": False},
        {"sole_owner_confirmed": 1},
        {"allow_draft": False},
        {"allow_draft": 1},
        {"allow_issuance": 1},
        {"enable_live": 1},
        {"credit_email": ""},
        {"credit_email": "first@example.test,second@example.test"},
        {"connection_path": ""},
        {"cleanup_lock_path": ""},
        {"approval_bundle_path": ""},
        {"ledger_path": ""},
        {"ledger_path": r"C:\synthetic-coordinator\ledger.sqlite3"},
        {"approval_bundle_sha256": ""},
        {"approval_bundle_sha256": "not-a-hash"},
    ],
)
def test_invalid_authorization_or_scope_stops_before_factories(changes):
    harness = Harness()
    result = harness.run(request(**changes))
    assert result["status"] == "BLOCKED" and harness.events == []
    assert harness.private_paths == []
    assert harness.prepared.execute_calls == 0
    assert_private(result)


@pytest.mark.parametrize("ownership", ["cleanup-complete", "controlled-handoff-complete"])
def test_one_snapshot_is_shared_in_sequential_read_then_draft_and_reverse_cleanup(ownership):
    harness = Harness()
    result = harness.run(request(ownership=ownership))
    assert result["status"] == "COMPLETE"
    assert harness.events == [
        "cleanup.factory",
        "cleanup.acquire",
        "session.factory",
        "session.acquire",
        "bundle.load",
        "snapshot.factory",
        "snapshot.load",
        "credit.read",
        "draft.preflight",
        "client.factory",
        "destination.check",
        "draft.prepare",
        "draft.execute",
        "client.close",
        "snapshot.close",
        "session.close",
        "cleanup.close",
    ]
    assert harness.snapshot.loads == [(True, False)] and harness.snapshot.close_calls == 1
    assert harness.private_paths == [BUNDLE, LEDGER]
    assert harness.read_credentials == [harness.credential] * 3
    assert harness.prepared.execute_calls == 1
    assert result["credit_summary"]["complete"] is True
    assert result["draft_result"]["state"] == "CREATED"
    assert result["draft_result"]["retry_allowed"] is False
    assert result["issuance_attempted"] is False
    assert_private(result)


@pytest.mark.parametrize("rejected_path", [BUNDLE, LEDGER])
def test_private_storage_failure_closes_leases_before_bundle_or_credential_access(rejected_path):
    harness = Harness()
    harness.failures["private_path:" + rejected_path] = RuntimeError(f"{PRIVATE} {TOKEN}")
    result = harness.run()
    assert result["status"] == "BLOCKED"
    expected_paths = [BUNDLE] if rejected_path == BUNDLE else [BUNDLE, LEDGER]
    assert harness.private_paths == expected_paths
    assert harness.events == [
        "cleanup.factory",
        "cleanup.acquire",
        "session.factory",
        "session.acquire",
        "session.close",
        "cleanup.close",
    ]
    assert not harness.snapshot.loads and harness.prepared.execute_calls == 0
    assert "bundle.load" not in harness.events and "snapshot.factory" not in harness.events
    assert_private(result)


@pytest.mark.parametrize("field", ["approval_bundle_path", "ledger_path"])
@pytest.mark.parametrize(
    "sync_folder",
    [
        "OneDrive",
        "OneDrive - Synthetic Org",
        "dRoPbOx",
        "Google Drive",
        "iCloudDrive",
    ],
)
def test_synchronized_bundle_or_ledger_path_is_rejected_lexically_before_leases(field, sync_folder):
    harness = Harness()
    filename = "approved.json" if field == "approval_bundle_path" else "doi-draft-transfer.sqlite3"
    path = "C:\\synthetic-coordinator\\" + sync_folder + "\\" + filename
    result = harness.run(request(**{field: path}))
    assert result["status"] == "BLOCKED"
    assert harness.events == [] and harness.private_paths == []
    assert not harness.snapshot.loads and harness.prepared.execute_calls == 0
    assert_private(result)


@pytest.mark.parametrize(
    "phase,closed",
    [
        ("cleanup.factory", []),
        ("cleanup.acquire", ["cleanup.close"]),
        ("session.factory", ["cleanup.close"]),
        ("session.acquire", ["session.close", "cleanup.close"]),
        ("bundle.load", ["session.close", "cleanup.close"]),
        ("snapshot.factory", ["session.close", "cleanup.close"]),
        ("snapshot.load", ["snapshot.close", "session.close", "cleanup.close"]),
    ],
)
def test_failed_owner_or_bundle_phase_closes_constructed_resources_and_never_drafts(phase, closed):
    harness = Harness()
    harness.failures[phase] = RuntimeError(f"{PRIVATE} {TOKEN}")
    result = harness.run()
    assert result["status"] in {"BLOCKED", "INCOMPLETE"}
    assert [event for event in harness.events if event.endswith(".close")] == closed
    assert harness.prepared.execute_calls == 0 and "credit.read" not in harness.events
    if phase in {
        "cleanup.factory",
        "cleanup.acquire",
        "session.factory",
        "session.acquire",
        "bundle.load",
    }:
        assert harness.snapshot.loads == []
    assert_private(result)


@pytest.mark.parametrize(
    "phase", ["client.close", "snapshot.close", "session.close", "cleanup.close"]
)
def test_release_failure_is_incomplete_and_remaining_resources_still_close(phase):
    harness = Harness()
    harness.failures[phase] = RuntimeError(f"{PRIVATE} {TOKEN}")
    result = harness.run()
    assert result["status"] == "INCOMPLETE"
    assert harness.events[-4:] == [
        "client.close",
        "snapshot.close",
        "session.close",
        "cleanup.close",
    ]
    assert harness.prepared.execute_calls == 1
    assert_private(result)


def test_expired_snapshot_without_issuance_stops_before_any_reader_or_draft():
    harness = Harness()
    harness.failures["snapshot.load"] = ReadError("session_cached_expired")
    result = harness.run()
    assert result["status"] == "BLOCKED"
    assert harness.snapshot.loads == [(True, False)]
    assert "credit.read" not in harness.events and harness.prepared.execute_calls == 0
    assert result["issuance_attempted"] is False
    assert_private(result)


@pytest.mark.parametrize("seconds_left", [-1, 0, 119, 120])
def test_unusable_supplied_snapshot_is_rejected_before_read_even_if_owner_returns_it(seconds_left):
    harness = Harness()
    harness.credential = SuppliedCredential(TOKEN, NOW + timedelta(seconds=seconds_left))
    result = harness.run()
    assert result["status"] == "BLOCKED"
    assert "credit.read" not in harness.events and harness.prepared.execute_calls == 0
    assert harness.snapshot.loads == [(True, False)]
    assert harness.events[-3:] == ["snapshot.close", "session.close", "cleanup.close"]
    assert_private(result)


def test_explicit_issuance_gate_is_forwarded_once_and_snapshot_still_shared():
    harness = Harness()
    harness.simulated_issuance = True
    result = harness.run(request(allow_issuance=True))
    assert result["status"] == "COMPLETE" and result["issuance_attempted"] is True
    assert harness.snapshot.loads == [(True, True)]
    assert harness.read_credentials == [harness.credential] * 3
    assert harness.prepared.execute_calls == 1
    assert_private(result)


def test_issuance_failure_is_reported_without_second_load_or_read():
    harness = Harness()
    harness.simulated_issuance = True
    harness.failures["snapshot.load"] = ReadError("session_issuer_failed")
    result = harness.run(request(allow_issuance=True))
    assert result["status"] == "BLOCKED" and result["issuance_attempted"] is True
    assert harness.snapshot.loads == [(True, True)]
    assert "credit.read" not in harness.events and harness.prepared.execute_calls == 0
    assert_private(result)


@pytest.mark.parametrize("identity", ["EXACT", "AMBIGUOUS", "INCOMPLETE"])
def test_incomplete_credit_read_preserves_report_but_blocks_draft_preflight(identity):
    harness = Harness()
    harness.credit = credit_result(identity, complete=False)
    result = harness.run()
    assert result["status"] == "INCOMPLETE"
    assert result["credit_summary"]["complete"] is False
    assert "draft.preflight" not in harness.events and harness.prepared.execute_calls == 0
    assert harness.snapshot.loads == [(True, False)]
    assert_private(result)


def test_complete_credit_no_exact_customer_does_not_block_separate_approved_recipient():
    harness = Harness()
    harness.credit = credit_result("NO_EXACT_CUSTOMER")
    result = harness.run()
    assert result["status"] == "COMPLETE"
    assert result["credit_summary"]["identity_status"] == "NO_EXACT_CUSTOMER"
    assert result["credit_summary"]["no_scoped_conversations"] is False
    assert harness.prepared.execute_calls == 1
    assert_private(result)


@pytest.mark.parametrize(
    "code",
    [
        "draft_existing_customer_missing",
        "draft_existing_customer_ambiguous",
        "draft_preflight_incomplete",
        "draft_customer_email_ambiguous",
        "draft_existing_draft",
        "draft_existing_order_conversation",
        "draft_evidence_stale",
    ],
)
def test_recipient_or_duplicate_failure_preserves_credit_and_never_creates_draft(code):
    harness = Harness()
    harness.failures["draft.preflight"] = ReadError(code)
    result = harness.run()
    assert result["status"] in {"BLOCKED", "INCOMPLETE"}
    assert result["credit_summary"]["complete"] is True
    assert "client.factory" not in harness.events and harness.prepared.execute_calls == 0
    assert harness.snapshot.loads == [(True, False)]
    assert_private(result)


@pytest.mark.parametrize(
    "phase",
    ["credit.read", "draft.preflight", "client.factory", "destination.check", "draft.prepare"],
)
def test_unexpected_read_preflight_or_preparation_failure_has_no_execute_or_retry(phase):
    harness = Harness()
    harness.failures[phase] = RuntimeError(f"{PRIVATE} {TOKEN} {EMAIL}")
    result = harness.run()
    assert result["status"] in {"BLOCKED", "INCOMPLETE"}
    assert harness.prepared.execute_calls == 0 and harness.snapshot.loads == [(True, False)]
    assert harness.events[-3:] == ["snapshot.close", "session.close", "cleanup.close"]
    assert_private(result)


def test_unknown_prior_ledger_outcome_blocks_execute_without_new_write_attempt():
    harness = Harness()
    harness.failures["draft.prepare"] = ReadError("APPROVED_PRIOR_ATTEMPT_BLOCKED")
    result = harness.run()
    assert result["status"] in {"BLOCKED", "INCOMPLETE"}
    assert harness.prepared.execute_calls == 0
    assert harness.client.close_calls == 1
    assert result["credit_summary"]["complete"] is True
    assert_private(result)


@pytest.mark.parametrize(
    "state", ["UNKNOWN", "CREATED_UNVERIFIED", "AUTH_REQUIRED", "RATE_LIMITED", "REJECTED"]
)
def test_nonverified_draft_outcome_is_not_complete_and_never_replayed(state):
    harness = Harness()
    harness.draft_result.update(state=state, code="SYNTHETIC_UNVERIFIED", retry_allowed=True)
    result = harness.run()
    assert result["status"] == "INCOMPLETE"
    assert result["draft_result"]["state"] == state
    assert result["draft_result"]["retry_allowed"] is False
    assert harness.prepared.execute_calls == 1
    assert harness.snapshot.loads == [(True, False)]
    assert_private(result)


def test_created_state_without_verified_code_cannot_report_success():
    harness = Harness()
    harness.draft_result.update(state="CREATED", code="SYNTHETIC_NOT_VERIFIED")
    result = harness.run()
    assert result["status"] == "INCOMPLETE"
    assert harness.prepared.execute_calls == 1
    assert result["draft_result"]["retry_allowed"] is False
    assert_private(result)


def test_exception_after_execute_attempt_does_not_retry_or_renew():
    harness = Harness()
    harness.failures["draft.execute"] = RuntimeError(f"{PRIVATE} {TOKEN}")
    result = harness.run()
    assert result["status"] in {"BLOCKED", "INCOMPLETE"}
    assert harness.prepared.execute_calls == 1
    assert harness.snapshot.loads == [(True, False)]
    assert harness.events[-4:] == [
        "client.close",
        "snapshot.close",
        "session.close",
        "cleanup.close",
    ]
    assert_private(result)


def test_draft_result_projects_only_safe_fields():
    harness = Harness()
    harness.draft_result.update(
        body=PRIVATE,
        recipient=DRAFT_EMAIL,
        access_token=TOKEN,
        error=f"{PRIVATE} {TOKEN}",
        retry_allowed=True,
    )
    result = harness.run()
    assert result["status"] == "COMPLETE"
    assert result["draft_result"]["retry_allowed"] is False
    assert set(result["draft_result"]) <= {
        "state",
        "code",
        "conversation_id",
        "web_link",
        "retry_allowed",
    }
    assert_private(result)


def cli_arguments():
    return [
        "--live",
        "--allow-one-draft",
        "--confirm-sole-owner",
        "--credit-email",
        EMAIL,
        "--connection-path",
        CONNECTION,
        "--cleanup-lock-path",
        CLEANUP_LOCK,
        "--approval-bundle-path",
        BUNDLE,
        "--approval-bundle-sha256",
        DIGEST,
        "--ledger-path",
        LEDGER,
        "--ownership",
        "cleanup-complete",
    ]


def test_coordinator_cli_default_off_never_constructs_real_resources(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("default-off CLI must not construct ownership resources")

    monkeypatch.setattr(coordinator, "_new_cleanup_lease", forbidden)
    monkeypatch.setattr(coordinator, "_new_lease", forbidden)
    assert coordinator.main([]) == 0
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result["status"] == "DISABLED" and result["complete"] is False
    assert result["issuance_attempted"] is False
    assert result["credit_summary"] is None and result["draft_result"] is None
    assert output.err == ""
    assert_private(result)


@pytest.mark.parametrize("issuance", [False, True])
def test_coordinator_cli_preserves_explicit_scope_and_issuance_gate(monkeypatch, capsys, issuance):
    received = []

    def fake_run(value):
        received.append(value)
        return {"status": "COMPLETE", "credit_classification": "NOT_EVALUATED"}

    monkeypatch.setattr(coordinator, "run_coordinator", fake_run)
    arguments = cli_arguments() + (["--allow-one-issuance"] if issuance else [])
    assert coordinator.main(arguments) == 0
    assert len(received) == 1
    value = received[0]
    assert value.credit_email == EMAIL and value.connection_path == CONNECTION
    assert value.cleanup_lock_path == CLEANUP_LOCK and value.approval_bundle_path == BUNDLE
    assert value.approval_bundle_sha256 == DIGEST and value.ledger_path == LEDGER
    assert value.allow_issuance is issuance and value.enable_live is True
    assert value.allow_draft is True and value.sole_owner_confirmed is True
    assert value.ownership == "cleanup-complete"
    output = capsys.readouterr()
    assert output.err == ""
    assert_private(json.loads(output.out))


@pytest.mark.parametrize(
    "extra",
    [
        ["--live"],
        ["--allow-one-draft"],
        ["--confirm-sole-owner"],
        ["--allow-one-issuance", "--allow-one-issuance"],
        ["--credit-email", "second@example.test"],
        ["--connection-path", r"C:\synthetic-coordinator\second.dpapi"],
        ["--cleanup-lock-path", r"C:\synthetic-coordinator\second.lock"],
        ["--approval-bundle-path", r"C:\synthetic-coordinator\second.json"],
        ["--approval-bundle-sha256", "b" * 64],
        ["--ledger-path", r"C:\synthetic-coordinator\second.sqlite3"],
        ["--ownership", "controlled-handoff-complete"],
        ["--token", TOKEN],
        ["--unknown-secret=" + TOKEN],
        [TOKEN],
    ],
)
def test_coordinator_cli_duplicates_and_unknown_values_are_redacted(monkeypatch, capsys, extra):
    received = []
    monkeypatch.setattr(coordinator, "run_coordinator", lambda value: received.append(value))
    assert coordinator.main(cli_arguments() + extra) != 0
    assert received == []
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result["status"] == "BLOCKED" and result["issues"] == ["invalid_arguments"]
    assert "second@example.test" not in output.out + output.err
    assert TOKEN not in output.out + output.err
    assert_private(result)


@pytest.mark.parametrize("arguments", [["--credit-email"], ["--approval-bundle-sha256"]])
def test_coordinator_cli_missing_argument_values_are_redacted_before_dispatch(
    monkeypatch, capsys, arguments
):
    received = []
    monkeypatch.setattr(coordinator, "run_coordinator", lambda value: received.append(value))
    assert coordinator.main(arguments) != 0
    assert received == []
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result["status"] == "BLOCKED" and result["issues"] == ["invalid_arguments"]
    assert_private(result)


@pytest.mark.parametrize("status", ["BLOCKED", "INCOMPLETE"])
def test_coordinator_cli_unsuccessful_result_is_nonzero_without_sensitive_output(
    monkeypatch, capsys, status
):
    monkeypatch.setattr(
        coordinator,
        "run_coordinator",
        lambda value: {
            "status": status,
            "credit_classification": "NOT_EVALUATED",
        },
    )
    assert coordinator.main(cli_arguments()) != 0
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result["status"] == status and output.err == ""
    assert_private(result)
