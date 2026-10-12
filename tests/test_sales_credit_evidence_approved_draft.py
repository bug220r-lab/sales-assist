"""Synthetic private bundles and temporary ledgers; no real auth or HTTP."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import threading
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from doi_draft_transfer import contract
from doi_draft_transfer.service import DraftTransferService
from doi_draft_transfer.store import FILENAME, DraftTransferStore
from sales_credit_evidence import approved_draft as component
from sales_credit_evidence.approved_draft import (
    ApprovedDraft,
    ApprovedDraftError,
    load_approved_bundle,
    make_approved_bundle,
    prepare_draft,
)
from tests.test_doi_draft_transfer import MockClient, synthetic_row, verified_review


def document(**changes: Any) -> dict[str, Any]:
    result = make_approved_bundle(
        synthetic_row(), verified_review(), version=2, source_approval_ref="SYN-APPROVAL-001"
    )
    result.update(changes)
    return result


def bundle_file(tmp_path: Path, value: dict[str, Any] | None = None) -> tuple[Path, str]:
    raw = contract.encoded(document() if value is None else value)
    path = tmp_path / "synthetic-approved-draft.json"
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def bundle(tmp_path: Path, value: dict[str, Any] | None = None) -> ApprovedDraft:
    return load_approved_bundle(*bundle_file(tmp_path, value))


class _SyntheticEvidence:
    """Replace only the coordinator's sealed boundary in these component tests."""

    def __init__(self, approved: ApprovedDraft) -> None:
        self.bundle_sha256 = approved.bundle_sha256
        self.recipient = approved.recipient
        self.customer_id = 99000001
        self.calls = 0
        self.valid = True

    def assert_for(self, approved: ApprovedDraft) -> None:
        self.calls += 1
        if (
            not self.valid
            or self.bundle_sha256 != approved.bundle_sha256
            or self.recipient != approved.recipient
        ):
            raise ApprovedDraftError("APPROVED_CUSTOMER_EVIDENCE_REQUIRED")


@pytest.fixture
def evidence_type(monkeypatch: pytest.MonkeyPatch) -> type[_SyntheticEvidence]:
    # The coordinator has its own real lookup/freshness/duplicate tests. No
    # production constructor or user-supplied success boolean is used here.
    replacement = types.ModuleType("sales_credit_evidence.draft_preflight")
    replacement.DraftCustomerEvidence = _SyntheticEvidence  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, replacement.__name__, replacement)
    return _SyntheticEvidence


def prepared(
    tmp_path: Path, evidence_type: type[_SyntheticEvidence], client: Any | None = None
) -> tuple[Any, ApprovedDraft, Any, _SyntheticEvidence]:
    approved = bundle(tmp_path)
    current_client = client if client is not None else MockClient()
    evidence = evidence_type(approved)
    result = prepare_draft(
        approved, tmp_path / FILENAME, client=current_client, customer_evidence=evidence
    )
    return result, approved, current_client, evidence


def test_exact_file_hash_and_canonical_hash_are_separate(tmp_path: Path) -> None:
    value = document()
    path, expected = bundle_file(tmp_path, value)
    approved = load_approved_bundle(path, expected)
    assert approved.bundle_sha256 == expected
    assert approved.canonical_sha256 == contract.digest(value)
    assert approved.rendered_body_sha256 == value["rendered_body_sha256"]
    assert approved.row_sha256 == contract.digest(value["row"])
    assert approved.review_sha256 == contract.digest(value["review"])
    pretty = json.dumps(value, indent=2).encode("utf-8")
    path.write_bytes(pretty)
    with pytest.raises(ApprovedDraftError, match="APPROVED_FILE_HASH_MISMATCH"):
        load_approved_bundle(path, expected)
    second = load_approved_bundle(path, hashlib.sha256(pretty).hexdigest())
    assert second.canonical_sha256 == approved.canonical_sha256
    assert second.bundle_sha256 != approved.bundle_sha256


def test_private_values_never_appear_in_repr_or_errors(tmp_path: Path) -> None:
    approved = bundle(tmp_path)
    rendered = repr(approved)
    for private in (approved.recipient, approved.subject, approved.order_id, approved.binding):
        assert private not in rendered
    with pytest.raises(ApprovedDraftError) as error:
        load_approved_bundle(tmp_path / "missing-private-file.json", "f" * 64)
    assert str(error.value) == "APPROVED_BUNDLE_UNAVAILABLE"
    assert str(tmp_path) not in str(error.value)


@pytest.mark.parametrize("bad_hash", [None, True, "", "f" * 63, "F" * 64, "z" * 64])
def test_invalid_expected_hash_precedes_file_access(
    monkeypatch: pytest.MonkeyPatch, bad_hash: Any
) -> None:
    read = Mock(side_effect=AssertionError("file access forbidden"))
    monkeypatch.setattr(component, "_read_private_bundle", read)
    with pytest.raises(ApprovedDraftError, match="APPROVED_FILE_HASH_REQUIRED"):
        load_approved_bundle("unused", bad_hash)
    read.assert_not_called()


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("source_approval_ref", "", "APPROVED_SOURCE_APPROVAL_REQUIRED"),
        ("version", True, "APPROVED_BUNDLE_VERSION_INVALID"),
        ("version", 0, "APPROVED_BUNDLE_VERSION_INVALID"),
        ("recipient", "different@example.test", "APPROVED_RECIPIENT_MISMATCH"),
        ("subject", "SYN DIFFERENT SUBJECT", "APPROVED_SUBJECT_MISMATCH"),
        ("body_sha256", "f" * 64, "APPROVED_BODY_MISMATCH"),
        ("rendered_body_sha256", "f" * 64, "APPROVED_RENDERING_MISMATCH"),
        ("approval_binding", "f" * 64, "APPROVED_BINDING_MISMATCH"),
        ("schema", "unknown/v1", "APPROVED_BUNDLE_SCHEMA_INVALID"),
    ],
)
def test_approval_fields_are_exact_despite_rehashed_file(
    tmp_path: Path, field: str, value: Any, code: str
) -> None:
    with pytest.raises(ApprovedDraftError, match=code):
        bundle(tmp_path, document(**{field: value}))


def test_changed_copy_cannot_carry_approval_forward(tmp_path: Path) -> None:
    value = document()
    value["row"]["selected_body_text"] += "\nSYN changed after approval"
    value["row"]["selected_body_sha256"] = contract.text_hash(value["row"]["selected_body_text"])
    value["body_sha256"] = value["row"]["selected_body_sha256"]
    value["rendered_body_sha256"] = contract.text_hash(
        contract.rendered_body(value["row"]["selected_body_text"])
    )
    with pytest.raises(ApprovedDraftError, match="APPROVED_BINDING_MISMATCH"):
        bundle(tmp_path, value)


def test_one_complete_row_and_real_review_are_required(tmp_path: Path) -> None:
    for value in ([], {"rows": [synthetic_row()]}, {**document(), "extra": "SYN"}):
        raw = contract.encoded(value)
        path = tmp_path / "invalid.json"
        path.write_bytes(raw)
        with pytest.raises(ApprovedDraftError, match="APPROVED_BUNDLE_FIELDS_INVALID"):
            load_approved_bundle(path, hashlib.sha256(raw).hexdigest())
    missing_review = document()
    missing_review.pop("review")
    with pytest.raises(ApprovedDraftError, match="APPROVED_BUNDLE_FIELDS_INVALID"):
        bundle(tmp_path, missing_review)
    with pytest.raises(ApprovedDraftError, match="APPROVED_REVIEW_HOLDS"):
        make_approved_bundle(
            synthetic_row(),
            contract.fresh_review(),
            version=2,
            source_approval_ref="SYN-APPROVAL-001",
        )


def test_pure_packaging_does_not_mutate_inputs() -> None:
    row, review = synthetic_row(), verified_review()
    original = copy.deepcopy((row, review))
    result = make_approved_bundle(row, review, version=2, source_approval_ref="SYN-APPROVAL-001")
    result["review"]["recipient_verified"] = False
    result["row"]["reviewer_notes"] = "SYN changed caller copy"
    assert (row, review) == original


@pytest.mark.parametrize("raw", [b"{}{}", b'{"schema":1,"schema":2}', b"\xff", b"NaN"])
def test_invalid_or_duplicate_json_is_rejected(tmp_path: Path, raw: bytes) -> None:
    path = tmp_path / "invalid.json"
    path.write_bytes(raw)
    with pytest.raises(ApprovedDraftError):
        load_approved_bundle(path, hashlib.sha256(raw).hexdigest())


def test_file_bounds_and_hard_links_are_rejected(tmp_path: Path) -> None:
    path, expected = bundle_file(tmp_path)
    linked = tmp_path / "linked.json"
    os.link(path, linked)
    with pytest.raises(ApprovedDraftError, match="APPROVED_BUNDLE_UNAVAILABLE"):
        load_approved_bundle(path, expected)
    linked.unlink()
    path.write_bytes(b"x" * (component.MAX_BUNDLE_BYTES + 1))
    with pytest.raises(ApprovedDraftError, match="APPROVED_BUNDLE_FILE_INVALID"):
        load_approved_bundle(path, expected)


def test_changed_file_metadata_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, expected = bundle_file(tmp_path)
    read_metadata = component._metadata
    count = 0

    def changed(info: os.stat_result) -> tuple[int, int, int, int, int]:
        nonlocal count
        count += 1
        result = read_metadata(info)
        return (result[0], result[1], result[2], result[3] + count, result[4])

    monkeypatch.setattr(component, "_metadata", changed)
    with pytest.raises(ApprovedDraftError, match="APPROVED_BUNDLE_CHANGED"):
        load_approved_bundle(path, expected)


@pytest.mark.parametrize("untrusted", [None, True, {"complete": True}, object()])
def test_untrusted_evidence_cannot_create_ledger(
    tmp_path: Path, evidence_type: type[_SyntheticEvidence], untrusted: object
) -> None:
    approved = bundle(tmp_path)
    ledger = tmp_path / FILENAME
    with pytest.raises(ApprovedDraftError, match="APPROVED_CUSTOMER_EVIDENCE_REQUIRED"):
        prepare_draft(approved, ledger, client=MockClient(), customer_evidence=untrusted)
    assert not ledger.exists()


def test_new_ledger_uses_normal_import_review_approve_then_one_transfer(
    tmp_path: Path, evidence_type: type[_SyntheticEvidence]
) -> None:
    ready, approved, client, evidence = prepared(tmp_path, evidence_type)
    assert client.calls == []
    record = ready.service.detail(approved.order_id)
    assert record["row"] == document()["row"]
    assert record["review"] == document()["review"]
    assert record["approved"] is True
    assert ready.version == 2
    assert ready.binding == approved.binding
    assert len(record["history"]) == 2
    with ready.service.store.transaction() as connection:
        events = [
            json.loads(row[0])["kind"]
            for row in connection.execute("SELECT event_json FROM audit ORDER BY sequence")
        ]
    assert events == ["IMPORTED", "EDIT_APPROVAL_INVALIDATED", "EXACT_DRAFT_APPROVED"]
    transfer = Mock(wraps=ready.service.transfer)
    ready.service.transfer = transfer
    first = ready.execute_once()
    assert first["state"] == "CREATED"
    assert ready.execute_once() == first
    assert transfer.call_count == 1
    assert len(client.calls) == 1
    assert evidence.calls == 2
    assert approved.recipient not in repr(ready)
    assert approved.recipient not in json.dumps(first)
    assert approved.subject not in json.dumps(first)
    assert approved.binding not in json.dumps(first)


def test_new_row_requires_explicit_final_version_before_writes(
    tmp_path: Path, evidence_type: type[_SyntheticEvidence]
) -> None:
    value = make_approved_bundle(
        synthetic_row(), verified_review(), version=3, source_approval_ref="SYN-APPROVAL-001"
    )
    approved = bundle(tmp_path, value)
    with pytest.raises(ApprovedDraftError, match="APPROVED_NEW_ROW_VERSION_REQUIRED"):
        prepare_draft(
            approved,
            tmp_path / FILENAME,
            client=MockClient(),
            customer_evidence=evidence_type(approved),
        )
    assert not (tmp_path / FILENAME).exists()


def test_existing_different_row_or_review_is_not_overwritten(
    tmp_path: Path, evidence_type: type[_SyntheticEvidence]
) -> None:
    ready, approved, client, _ = prepared(tmp_path, evidence_type)
    changed = copy.deepcopy(document())
    changed["row"]["reviewer_notes"] = "SYN different approved notes"
    changed = make_approved_bundle(
        changed["row"], changed["review"], version=2, source_approval_ref="SYN-APPROVAL-002"
    )
    incoming = bundle(tmp_path, changed)
    original = ready.service.detail(approved.order_id)
    with pytest.raises(ApprovedDraftError, match="APPROVED_LEDGER_CONFLICT"):
        prepare_draft(
            incoming,
            tmp_path / FILENAME,
            client=client,
            customer_evidence=evidence_type(incoming),
        )
    assert ready.service.detail(approved.order_id) == original
    assert client.calls == []


def test_existing_conflicting_approval_is_not_replaced(
    tmp_path: Path, evidence_type: type[_SyntheticEvidence]
) -> None:
    ready, approved, client, _ = prepared(tmp_path, evidence_type)
    with ready.service.store.transaction(write=True) as connection:
        record = ready.service.store.load(connection, approved.order_id)
        conflict = {**record["approval"], "binding": "f" * 64}
        connection.execute(
            "UPDATE drafts SET approval_json=? WHERE order_id=?",
            (json.dumps(conflict), approved.order_id),
        )
    before = ready.service.detail(approved.order_id)
    with pytest.raises(ApprovedDraftError, match="APPROVED_LEDGER_APPROVAL_CONFLICT"):
        prepare_draft(
            approved,
            tmp_path / FILENAME,
            client=client,
            customer_evidence=evidence_type(approved),
        )
    assert ready.service.detail(approved.order_id) == before
    assert client.calls == []


@pytest.mark.parametrize("state", ["CREATED", "CREATED_UNVERIFIED", "UNKNOWN", "IN_FLIGHT"])
def test_known_or_uncertain_ledger_outcomes_never_repeat_post_after_restart(
    tmp_path: Path, evidence_type: type[_SyntheticEvidence], state: str
) -> None:
    client = MockClient()
    client.result = {"state": state, "code": "SYN_RESULT", "retry_allowed": False}
    if state == "CREATED_UNVERIFIED":
        client.result["conversation_id"] = "99000001"
    ready, approved, _, _ = prepared(tmp_path, evidence_type, client)
    result = ready.execute_once()
    restarted = prepare_draft(
        approved,
        tmp_path / FILENAME,
        client=client,
        customer_evidence=evidence_type(approved),
    )
    assert restarted.execute_once() == result
    assert len(client.calls) == 1
    if state == "CREATED_UNVERIFIED":
        assert result["conversation_id"] == "99000001"


@pytest.mark.parametrize("state", ["AUTH_REQUIRED", "RATE_LIMITED", "REJECTED"])
def test_one_shot_wrapper_never_enables_service_retry(
    tmp_path: Path, evidence_type: type[_SyntheticEvidence], state: str
) -> None:
    client = MockClient()
    client.result = {"state": state, "code": "SYN_RESULT", "retry_allowed": True}
    ready, approved, _, _ = prepared(tmp_path, evidence_type, client)
    assert ready.execute_once()["retry_allowed"] is False
    with pytest.raises(ApprovedDraftError, match="APPROVED_PRIOR_ATTEMPT_BLOCKED"):
        prepare_draft(
            approved,
            tmp_path / FILENAME,
            client=client,
            customer_evidence=evidence_type(approved),
        )
    assert len(client.calls) == 1


def test_unknown_exception_preserves_one_durable_attempt(
    tmp_path: Path, evidence_type: type[_SyntheticEvidence]
) -> None:
    client = Mock()
    client.create_draft.side_effect = TimeoutError("SYN unknown write result")
    ready, approved, _, _ = prepared(tmp_path, evidence_type, client)
    assert ready.execute_once()["state"] == "UNKNOWN"
    restarted = prepare_draft(
        approved,
        tmp_path / FILENAME,
        client=client,
        customer_evidence=evidence_type(approved),
    )
    assert restarted.execute_once()["state"] == "UNKNOWN"
    assert client.create_draft.call_count == 1


def test_freshness_is_rechecked_before_transfer(
    tmp_path: Path, evidence_type: type[_SyntheticEvidence]
) -> None:
    ready, _, client, evidence = prepared(tmp_path, evidence_type)
    evidence.valid = False
    with pytest.raises(ApprovedDraftError, match="APPROVED_CUSTOMER_EVIDENCE_REQUIRED"):
        ready.execute_once()
    assert client.calls == []


def test_concurrent_execute_invokes_service_only_once(
    tmp_path: Path, evidence_type: type[_SyntheticEvidence]
) -> None:
    ready, _, client, _ = prepared(tmp_path, evidence_type)
    start = threading.Barrier(2)
    transfer = Mock(wraps=ready.service.transfer)
    ready.service.transfer = transfer

    def execute() -> dict[str, object]:
        start.wait(timeout=5)
        return ready.execute_once()

    with ThreadPoolExecutor(max_workers=2) as pool:
        one, two = pool.submit(execute), pool.submit(execute)
        assert one.result(timeout=10) == two.result(timeout=10)
    assert transfer.call_count == 1
    assert len(client.calls) == 1


def test_existing_unrelated_ledger_history_is_preserved(
    tmp_path: Path, evidence_type: type[_SyntheticEvidence]
) -> None:
    ledger = DraftTransferStore(tmp_path / FILENAME)
    existing_service = DraftTransferService(ledger, MockClient())
    from tests.test_doi_draft_transfer import csv_text

    imported = existing_service.preview_import(csv_text([synthetic_row("90000002")]))
    existing_service.commit_import(imported["preview_token"], imported["revision"])
    before = existing_service.detail("90000002")
    ready, _, _, _ = prepared(tmp_path, evidence_type)
    assert ready.service.detail("90000002") == before


def test_error_code_registry_contains_every_component_error() -> None:
    source = Path(component.__file__).read_text(encoding="utf-8")
    import re

    raised = set(re.findall(r'ApprovedDraftError\("([A-Z_]+)"\)', source))
    assert raised <= component.APPROVED_DRAFT_ERROR_CODES


def preparation_args(tmp_path: Path) -> tuple[list[str], Path]:
    row_path, review_path = tmp_path / "row.json", tmp_path / "review.json"
    row_path.write_bytes(contract.encoded(synthetic_row()))
    review_path.write_bytes(contract.encoded(verified_review()))
    output = tmp_path / "approved.json"
    return [
        "--row-json",
        str(row_path),
        "--review-json",
        str(review_path),
        "--version",
        "2",
        "--source-approval-ref",
        "SYN-APPROVAL-001",
        "--output",
        str(output),
    ], output


def test_preparation_default_help_has_no_file_io(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    read = Mock(side_effect=AssertionError("no file access"))
    write = Mock(side_effect=AssertionError("no file access"))
    monkeypatch.setattr(component, "_read_component_json", read)
    monkeypatch.setattr(component, "_write_new_bundle", write)
    assert component.main([]) == 0
    assert "--row-json" in capsys.readouterr().out
    read.assert_not_called()
    write.assert_not_called()


@pytest.mark.parametrize(
    "args",
    [
        ["--row-json", "SYN-private-input"],
        ["--row-json", "SYN-private-input", "--row-json", "SYN-other-private-input"],
        ["--version", "SYN-private-invalid-integer"],
        ["--unknown", "SYN-private-argument"],
    ],
)
def test_preparation_invalid_arguments_are_closed_before_io(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], args: list[str]
) -> None:
    read = Mock(side_effect=AssertionError("no file access"))
    monkeypatch.setattr(component, "_read_component_json", read)
    assert component.main(args) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "status": "BLOCKED",
        "code": "APPROVED_PREPARE_ARGUMENTS_INVALID",
    }
    assert captured.err == ""
    assert "SYN-private" not in captured.out
    read.assert_not_called()


def test_preparation_cli_packages_exact_inputs_and_prints_only_digest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args, output = preparation_args(tmp_path)
    inputs_before = [Path(args[index]).read_bytes() for index in (1, 3)]
    assert component.main(args) == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result == {
        "status": "PREPARED",
        "version": 2,
        "bundle_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }
    approved = load_approved_bundle(output, result["bundle_sha256"])
    assert approved.recipient == synthetic_row()["recipient_email"]
    assert approved._document() == document()
    assert [Path(args[index]).read_bytes() for index in (1, 3)] == inputs_before
    for private in (str(tmp_path), approved.recipient, approved.subject, approved.order_id):
        assert private not in captured.out
    assert captured.err == ""
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "approved.json",
        "review.json",
        "row.json",
    ]


def test_preparation_refuses_existing_output_without_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args, output = preparation_args(tmp_path)
    output.write_bytes(b"SYN-existing-private-document")
    assert component.main(args) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "APPROVED_OUTPUT_EXISTS"
    assert output.read_bytes() == b"SYN-existing-private-document"


@pytest.mark.parametrize("invalid_review", [True, False])
def test_preparation_requires_valid_completed_review_before_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], invalid_review: bool
) -> None:
    args, output = preparation_args(tmp_path)
    if invalid_review:
        Path(args[3]).write_bytes(b'{"SYN-private-data":')
        expected = "APPROVED_INPUT_JSON_INVALID"
    else:
        review = verified_review()
        review["recipient_verified"] = False
        Path(args[3]).write_bytes(contract.encoded(review))
        expected = "APPROVED_REVIEW_HOLDS"
    assert component.main(args) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["code"] == expected
    assert "SYN-private" not in captured.out
    assert not output.exists()


def blocked_private_root(tmp_path: Path, kind: str, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / kind
    root.mkdir()
    if kind == "repository":
        (root / ".git").mkdir()
    if kind == "configured-sync-root":
        monkeypatch.setenv("OneDriveCommercial", str(root))
    return root


@pytest.mark.parametrize(
    "kind",
    ["OneDrive", "Dropbox", "Google Drive", "iCloudDrive", "repository", "configured-sync-root"],
)
@pytest.mark.parametrize("operation", ["read", "output", "ledger"])
def test_private_storage_policy_covers_all_component_entry_points(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evidence_type: type[_SyntheticEvidence],
    capsys: pytest.CaptureFixture[str],
    kind: str,
    operation: str,
) -> None:
    approved = bundle(tmp_path)
    args, output = preparation_args(tmp_path)
    blocked = blocked_private_root(tmp_path, kind, monkeypatch)
    if operation == "read":
        path, expected = bundle_file(blocked)
        with pytest.raises(ApprovedDraftError, match="APPROVED_BUNDLE_UNAVAILABLE"):
            load_approved_bundle(path, expected)
    elif operation == "output":
        output = blocked / output.name
        args[-1] = str(output)
        assert component.main(args) == 2
        assert json.loads(capsys.readouterr().out)["code"] == "APPROVED_OUTPUT_UNAVAILABLE"
        assert not output.exists()
    else:
        ledger = blocked / FILENAME
        with pytest.raises(ApprovedDraftError, match="APPROVED_LEDGER_UNAVAILABLE"):
            prepare_draft(
                approved, ledger, client=MockClient(), customer_evidence=evidence_type(approved)
            )
        assert not ledger.exists()


def test_linked_ledger_is_rejected_without_open_or_mutation(
    tmp_path: Path, evidence_type: type[_SyntheticEvidence]
) -> None:
    approved = bundle(tmp_path)
    original, ledger = tmp_path / "synthetic-other-file", tmp_path / FILENAME
    original.write_bytes(b"SYN-unrelated-private-data")
    os.link(original, ledger)
    with pytest.raises(ApprovedDraftError, match="APPROVED_LEDGER_UNAVAILABLE"):
        prepare_draft(
            approved, ledger, client=MockClient(), customer_evidence=evidence_type(approved)
        )
    assert original.read_bytes() == b"SYN-unrelated-private-data"


def test_private_storage_is_rechecked_before_transfer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, evidence_type: type[_SyntheticEvidence]
) -> None:
    ready, _, client, _ = prepared(tmp_path, evidence_type)
    monkeypatch.setenv("OneDriveCommercial", str(tmp_path))
    with pytest.raises(ApprovedDraftError, match="APPROVED_LEDGER_UNAVAILABLE"):
        ready.execute_once()
    assert client.calls == []
