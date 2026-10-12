"""One exact approved private draft, using the existing durable transfer service.

No import-time file, credential, network, or ledger access. This component accepts
only a hash-bound approval document and a sealed coordinator preflight result.
Only the duplicate check may await preflight; factual reviews are never inferred.
It never sends or publishes a message.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import io
import json
import os
import re
import stat
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, cast

from doi_draft_transfer import contract as contract_module
from doi_draft_transfer import service as service_module
from doi_draft_transfer import store as store_module
from doi_draft_transfer.contract import TransferError

contract: Any = contract_module
service_api: Any = service_module
store_api: Any = store_module

BUNDLE_SCHEMA = "approved-help-scout-draft/v1"
MAX_BUNDLE_BYTES = 5 * 1024 * 1024
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:#-]{0,255}\Z")
_FIELDS = frozenset(
    {
        "schema",
        "row",
        "review",
        "version",
        "source_approval_ref",
        "approval_binding",
        "recipient",
        "subject",
        "body_sha256",
        "rendered_body_sha256",
    }
)
_BUNDLE_AUTHORITY = object()
_PREPARED_AUTHORITY = object()
APPROVED_DRAFT_ERROR_CODES = frozenset(
    {
        "APPROVED_BINDING_MISMATCH",
        "APPROVED_BODY_MISMATCH",
        "APPROVED_BUNDLE_AUTHORITY_REQUIRED",
        "APPROVED_BUNDLE_CHANGED",
        "APPROVED_BUNDLE_FIELDS_INVALID",
        "APPROVED_BUNDLE_FILE_INVALID",
        "APPROVED_BUNDLE_JSON_INVALID",
        "APPROVED_BUNDLE_SCHEMA_INVALID",
        "APPROVED_BUNDLE_UNAVAILABLE",
        "APPROVED_BUNDLE_VERSION_INVALID",
        "APPROVED_COMMAND_ALREADY_USED",
        "APPROVED_CUSTOMER_EVIDENCE_REQUIRED",
        "APPROVED_DRAFT_CLIENT_REQUIRED",
        "APPROVED_FILE_HASH_MISMATCH",
        "APPROVED_FILE_HASH_REQUIRED",
        "APPROVED_HASH_INVALID",
        "APPROVED_IMPORT_CONFLICT",
        "APPROVED_LEDGER_APPROVAL_CONFLICT",
        "APPROVED_LEDGER_APPROVAL_REQUIRED",
        "APPROVED_LEDGER_CONFLICT",
        "APPROVED_LEDGER_UNAVAILABLE",
        "APPROVED_NEW_ROW_VERSION_REQUIRED",
        "APPROVED_PREPARATION_REQUIRED",
        "APPROVED_PRIOR_ATTEMPT_BLOCKED",
        "APPROVED_RECIPIENT_MISMATCH",
        "APPROVED_RENDERING_MISMATCH",
        "APPROVED_REVIEW_HOLDS",
        "APPROVED_REVIEW_INVALID",
        "APPROVED_ROW_INVALID",
        "APPROVED_SOURCE_APPROVAL_REQUIRED",
        "APPROVED_SUBJECT_MISMATCH",
        "APPROVED_INPUT_JSON_INVALID",
        "APPROVED_OUTPUT_EXISTS",
        "APPROVED_OUTPUT_UNAVAILABLE",
        "APPROVED_PREPARE_ARGUMENTS_INVALID",
        "APPROVED_PREPARATION_FAILED",
        # Closed errors propagated by the unchanged durable service/store.
        "TRANSFER_STORAGE_UNAVAILABLE",
        "TRANSFER_STORAGE_SCHEMA",
        "TRANSFER_ROW_CAPACITY",
        "TRANSFER_AUDIT_CAPACITY",
        "IMPORT_REVISION_CONFLICT",
        "IMPORT_PREVIEW_EXPIRED",
        "DRAFT_NOT_FOUND",
        "DRAFT_VERSION_CONFLICT",
        "TRANSFER_RECORD_FROZEN",
        "CURRENT_EXACT_APPROVAL_REQUIRED",
        "TRANSFER_ALREADY_RESERVED",
        "EXPLICIT_RETRY_REQUIRED",
    }
)


class ApprovedDraftError(TransferError):
    """Closed codes only; private document contents never enter diagnostics."""

    def __init__(self, code: str) -> None:
        super().__init__(code, 409)  # type: ignore[no-untyped-call]


def _metadata(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _private_path(path: str | Path) -> Path:
    # Reuse the established non-synchronized, non-repository, fixed local disk
    # and linked-ancestor policy. Importing it does not activate a launcher.
    from doi_draft_transfer import launch

    policy: Any = launch
    return cast(Path, policy.private_path(path))


def _check_file(info: os.stat_result) -> None:
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or getattr(info, "st_file_attributes", 0) & 0x400
        or not 0 < info.st_size <= MAX_BUNDLE_BYTES
    ):
        raise ApprovedDraftError("APPROVED_BUNDLE_FILE_INVALID")


def _read_private_bundle(path: str | Path) -> bytes:
    try:
        checked = _private_path(path)
        before = checked.lstat()
        _check_file(before)
        with checked.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            _check_file(opened)
            # Python on Windows can expose different ctime semantics for path
            # and handle stats. Compare identity/size/mtime across APIs, then
            # compare each API's complete metadata before/after its own read.
            if _metadata(before)[:4] != _metadata(opened)[:4]:
                raise ApprovedDraftError("APPROVED_BUNDLE_CHANGED")
            raw = handle.read(MAX_BUNDLE_BYTES + 1)
            final_open = os.fstat(handle.fileno())
        final_path = checked.lstat()
        if (
            _metadata(opened) != _metadata(final_open)
            or _metadata(before) != _metadata(final_path)
            or len(raw) != opened.st_size
        ):
            raise ApprovedDraftError("APPROVED_BUNDLE_CHANGED")
        return raw
    except ApprovedDraftError:
        raise
    except (OSError, ValueError, RuntimeError, TypeError):
        raise ApprovedDraftError("APPROVED_BUNDLE_UNAVAILABLE") from None


def _validate_document(value: object) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _FIELDS:
        raise ApprovedDraftError("APPROVED_BUNDLE_FIELDS_INVALID")
    document = cast(dict[str, Any], value)
    if document["schema"] != BUNDLE_SCHEMA:
        raise ApprovedDraftError("APPROVED_BUNDLE_SCHEMA_INVALID")
    if type(document["version"]) is not int or not 1 <= document["version"] <= 2**31 - 1:
        raise ApprovedDraftError("APPROVED_BUNDLE_VERSION_INVALID")
    reference = document["source_approval_ref"]
    if type(reference) is not str or _REFERENCE.fullmatch(reference) is None:
        raise ApprovedDraftError("APPROVED_SOURCE_APPROVAL_REQUIRED")
    row, review = document["row"], document["review"]
    try:
        if contract.validate_row(row):
            raise ApprovedDraftError("APPROVED_ROW_INVALID")
        contract.validate_review(review)
        holds = contract.review_holds(row, review)
        if holds and not (
            holds == ["DUPLICATE_RECONCILIATION_REQUIRED"]
            and review["duplicate_status"] == "unresolved"
        ):
            raise ApprovedDraftError("APPROVED_REVIEW_HOLDS")
    except ApprovedDraftError:
        raise
    except (TransferError, ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        raise ApprovedDraftError("APPROVED_REVIEW_INVALID") from None
    for name in ("approval_binding", "body_sha256", "rendered_body_sha256"):
        if type(document[name]) is not str or _HASH.fullmatch(document[name]) is None:
            raise ApprovedDraftError("APPROVED_HASH_INVALID")
    if document["recipient"] != row["recipient_email"]:
        raise ApprovedDraftError("APPROVED_RECIPIENT_MISMATCH")
    if document["subject"] != row["subject"]:
        raise ApprovedDraftError("APPROVED_SUBJECT_MISMATCH")
    if not hmac.compare_digest(document["body_sha256"], row["selected_body_sha256"]):
        raise ApprovedDraftError("APPROVED_BODY_MISMATCH")
    rendered_hash = contract.text_hash(contract.rendered_body(row["selected_body_text"]))
    if not hmac.compare_digest(document["rendered_body_sha256"], rendered_hash):
        raise ApprovedDraftError("APPROVED_RENDERING_MISMATCH")
    expected = contract.approval_binding(row, document["version"], review)
    if not hmac.compare_digest(document["approval_binding"], expected):
        raise ApprovedDraftError("APPROVED_BINDING_MISMATCH")
    return document


@dataclass(frozen=True, slots=True, repr=False, init=False)
class ApprovedDraft:
    """Immutable private content; every accessor derives from validated canonical bytes."""

    _canonical: bytes
    _file_sha256: str
    _authority: object

    def __init__(self, canonical: bytes, file_sha256: str, *, _authority: object) -> None:
        if _authority is not _BUNDLE_AUTHORITY:
            raise ApprovedDraftError("APPROVED_BUNDLE_AUTHORITY_REQUIRED")
        object.__setattr__(self, "_canonical", canonical)
        object.__setattr__(self, "_file_sha256", file_sha256)
        object.__setattr__(self, "_authority", _authority)

    def __repr__(self) -> str:
        return "ApprovedDraft(<redacted>)"

    def _document(self) -> dict[str, Any]:
        if self._authority is not _BUNDLE_AUTHORITY:
            raise ApprovedDraftError("APPROVED_BUNDLE_AUTHORITY_REQUIRED")
        return _validate_document(contract.unique_json(self._canonical.decode("utf-8")))

    @property
    def order_id(self) -> str:
        return cast(str, self._document()["row"]["order_id"])

    @property
    def recipient(self) -> str:
        return cast(str, self._document()["recipient"])

    @property
    def subject(self) -> str:
        return cast(str, self._document()["subject"])

    @property
    def version(self) -> int:
        return cast(int, self._document()["version"])

    @property
    def binding(self) -> str:
        return cast(str, self._document()["approval_binding"])

    @property
    def bundle_sha256(self) -> str:
        """SHA256 of the exact approved file bytes, including its formatting."""
        return self._file_sha256

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(self._canonical).hexdigest()

    @property
    def row_sha256(self) -> str:
        return cast(str, contract.digest(self._document()["row"]))

    @property
    def review_sha256(self) -> str:
        return cast(str, contract.digest(self._document()["review"]))

    @property
    def rendered_body_sha256(self) -> str:
        return cast(str, self._document()["rendered_body_sha256"])


def make_approved_bundle(
    row: dict[str, Any],
    review: dict[str, Any],
    *,
    version: int,
    source_approval_ref: str,
) -> dict[str, Any]:
    """Pure packaging of approved copy and supplied factual review.

    This does not grant approval or write a file. The caller supplies an existing
    genuine approval; only an unresolved duplicate check may await coordinator
    preflight. Later activation requires the exact resulting file hash.
    """
    try:
        if contract.validate_row(row):
            raise ApprovedDraftError("APPROVED_ROW_INVALID")
        contract.validate_review(review)
        document = {
            "schema": BUNDLE_SCHEMA,
            "row": row,
            "review": review,
            "version": version,
            "source_approval_ref": source_approval_ref,
            "approval_binding": contract.approval_binding(row, version, review),
            "recipient": row["recipient_email"],
            "subject": row["subject"],
            "body_sha256": row["selected_body_sha256"],
            "rendered_body_sha256": contract.text_hash(
                contract.rendered_body(row["selected_body_text"])
            ),
        }
        validated = _validate_document(document)
        copied = contract.unique_json(contract.encoded(validated).decode("utf-8"))
        return cast(dict[str, Any], copied)
    except ApprovedDraftError:
        raise
    except (TransferError, ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        raise ApprovedDraftError("APPROVED_REVIEW_INVALID") from None


def load_approved_bundle(path: str | Path, expected_sha256: str) -> ApprovedDraft:
    """Explicit local read only: require an out-of-band hash of one approved file."""
    if type(expected_sha256) is not str or _HASH.fullmatch(expected_sha256) is None:
        raise ApprovedDraftError("APPROVED_FILE_HASH_REQUIRED")
    raw = _read_private_bundle(path)
    actual_hash = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(actual_hash, expected_sha256):
        raise ApprovedDraftError("APPROVED_FILE_HASH_MISMATCH")
    try:
        value = contract.unique_json(raw.decode("utf-8"))
        document = _validate_document(value)
        canonical = contract.encoded(document)
    except ApprovedDraftError:
        raise
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise ApprovedDraftError("APPROVED_BUNDLE_JSON_INVALID") from None
    return ApprovedDraft(canonical, actual_hash, _authority=_BUNDLE_AUTHORITY)


def _require_customer_evidence(bundle: ApprovedDraft, evidence: object) -> None:
    # The coordinator seals evidence only after complete exact identity and
    # duplicate discovery. Duck typing and JSON booleans are not authority.
    from .draft_preflight import DraftCustomerEvidence

    if type(evidence) is not DraftCustomerEvidence:
        raise ApprovedDraftError("APPROVED_CUSTOMER_EVIDENCE_REQUIRED")
    evidence.assert_for(bundle)


@dataclass(frozen=True, slots=True, repr=False)
class _ExecutionApproval:
    """Completed review separate from the immutable source approval document."""

    review_bytes: bytes
    binding: str
    provenance_bytes: bytes | None = None

    def review(self) -> dict[str, Any]:
        return cast(dict[str, Any], contract.unique_json(self.review_bytes.decode("utf-8")))


def _execution_approval(bundle: ApprovedDraft, evidence: Any) -> _ExecutionApproval:
    # The caller has required exact sealed, fresh evidence before this function.
    document = bundle._document()
    review = document["review"]
    if review["duplicate_status"] != "unresolved":
        return _ExecutionApproval(contract.encoded(review), bundle.binding)
    finding = {
        "schema": "coordinator-duplicate-preflight/v1",
        "source_bundle_sha256": bundle.bundle_sha256,
        "source_approval_binding": bundle.binding,
        "source_approval_ref": document["source_approval_ref"],
        "duplicate_check": "NO_MATCH_IN_ACCESSIBLE_MAILBOX_SNAPSHOT",
        "global_draft_absence_proved": False,
        "mailbox_id": contract.MAILBOX_ID,
        "customer_id": evidence.customer_id,
    }
    review["duplicate_status"] = "no_existing_draft"
    review["duplicate_evidence"] = contract.encoded(finding).decode("utf-8")
    contract.validate_review(review)
    if contract.review_holds(document["row"], review):
        raise ApprovedDraftError("APPROVED_REVIEW_HOLDS")
    binding = cast(str, contract.approval_binding(document["row"], bundle.version, review))
    # Dynamic snapshot metadata belongs in the original audit event, not the
    # execution binding. Later fresh checks may reopen the identical approval
    # and recover an uncertain result without changing it or posting again.
    provenance = {
        **finding,
        "execution_approval_binding": binding,
        "observed_at": evidence.observed_at.isoformat(),
        "conversation_count": evidence.conversation_count,
        "thread_count": evidence.thread_count,
    }
    return _ExecutionApproval(contract.encoded(review), binding, contract.encoded(provenance))


def _matches_provenance(actual: object, expected: dict[str, Any]) -> bool:
    if type(actual) is not dict or set(actual) != set(expected):
        return False
    snapshot_fields = {"observed_at", "conversation_count", "thread_count"}
    return (
        all(
            type(actual[key]) is type(expected[key]) and actual[key] == expected[key]
            for key in expected.keys() - snapshot_fields
        )
        and contract.timestamp(actual["observed_at"]) is not None
        and all(
            type(actual[key]) is int and actual[key] >= 0
            for key in ("conversation_count", "thread_count")
        )
    )


def _current_exact(
    service: Any, bundle: ApprovedDraft, execution: _ExecutionApproval
) -> dict[str, Any]:
    document = bundle._document()
    try:
        _private_path(service.store.path)
    except (OSError, ValueError, RuntimeError, TypeError):
        raise ApprovedDraftError("APPROVED_LEDGER_UNAVAILABLE") from None
    record: dict[str, Any] = service.detail(bundle.order_id)
    if (
        record["version"] != bundle.version
        or record["row"] != document["row"]
        or record["review"] != execution.review()
        or record["approval_binding"] != execution.binding
    ):
        raise ApprovedDraftError("APPROVED_LEDGER_CONFLICT")
    approval = record["approval"]
    if approval is not None and (
        type(approval) is not dict
        or approval.get("binding") != execution.binding
        or approval.get("version") != bundle.version
        or approval.get("recipient_email") != bundle.recipient
        or approval.get("selected_body_sha256") != document["body_sha256"]
        or approval.get("mailbox_id") != contract.MAILBOX_ID
        or approval.get("user_id") != contract.USER_ID
    ):
        raise ApprovedDraftError("APPROVED_LEDGER_APPROVAL_CONFLICT")
    if execution.provenance_bytes is not None:
        expected = contract.unique_json(execution.provenance_bytes.decode("utf-8"))
        with service.store.transaction() as connection:
            events = connection.execute("SELECT event_json FROM audit ORDER BY sequence")
            if not any(
                event.get("kind") == "COORDINATOR_DUPLICATE_PREFLIGHT"
                and event.get("order_id") == bundle.order_id
                and event.get("version") == bundle.version
                and _matches_provenance(event.get("details"), expected)
                for event in (contract.unique_json(row[0]) for row in events)
            ):
                raise ApprovedDraftError("APPROVED_LEDGER_APPROVAL_CONFLICT")
    return record


def _safe_result(value: object) -> dict[str, object]:
    states = {
        "IN_FLIGHT",
        "UNKNOWN",
        "CREATED",
        "CREATED_UNVERIFIED",
        "AUTH_REQUIRED",
        "RATE_LIMITED",
        "REJECTED",
    }
    if (
        type(value) is not dict
        or type(value.get("state")) is not str
        or value.get("state") not in states
    ):
        return {"state": "UNKNOWN", "code": "TRANSFER_RESULT_UNRECOGNIZED", "retry_allowed": False}
    code = value.get("code")
    result: dict[str, object] = {
        "state": value["state"],
        "code": code
        if type(code) is str and re.fullmatch(r"[A-Z][A-Z0-9_]{0,95}", code)
        else "TRANSFER_RESULT_RECORDED",
        "retry_allowed": False,
    }
    identifier = value.get("conversation_id")
    if type(identifier) is str and re.fullmatch(r"[1-9][0-9]{0,18}", identifier):
        result["conversation_id"] = identifier
    return result


class PreparedDraft:
    """Exact ledger binding and one service transfer invocation; repr is private."""

    __slots__ = ("_bundle", "_evidence", "_executed", "_execution", "_lock", "_result", "service")

    def __init__(
        self,
        service: Any,
        bundle: ApprovedDraft,
        evidence: object,
        execution: _ExecutionApproval,
        *,
        _authority: object,
    ) -> None:
        if _authority is not _PREPARED_AUTHORITY:
            raise ApprovedDraftError("APPROVED_PREPARATION_REQUIRED")
        self.service = service
        self._bundle = bundle
        self._evidence = evidence
        self._execution = execution
        self._executed = False
        self._lock = threading.Lock()
        self._result: dict[str, object] | None = None

    def __repr__(self) -> str:
        return "PreparedDraft(<redacted>)"

    @property
    def version(self) -> int:
        return self._bundle.version

    @property
    def binding(self) -> str:
        return self._execution.binding

    @property
    def source_binding(self) -> str:
        return self._bundle.binding

    def execute_once(self) -> dict[str, object]:
        with self._lock:
            return self._execute_once()

    def _execute_once(self) -> dict[str, object]:
        if self._executed:
            if self._result is None:
                raise ApprovedDraftError("APPROVED_COMMAND_ALREADY_USED")
            return dict(self._result)
        _require_customer_evidence(self._bundle, self._evidence)
        record = _current_exact(self.service, self._bundle, self._execution)
        if not record["approved"]:
            raise ApprovedDraftError("APPROVED_LEDGER_APPROVAL_REQUIRED")
        if record["transfer"] and record["transfer"]["state"] not in service_api.FINAL_WRITE_STATES:
            raise ApprovedDraftError("APPROVED_PRIOR_ATTEMPT_BLOCKED")
        # Set before invoking the existing service; failures never open a retry.
        self._executed = True
        result = self.service.transfer(
            self._bundle.order_id, self.version, self.binding, retry=False
        )
        self._result = _safe_result(result)
        return dict(self._result)


def prepare_draft(
    bundle: ApprovedDraft,
    ledger_path: str | Path,
    *,
    client: object,
    customer_evidence: object,
) -> PreparedDraft:
    """Use normal service commands after sealed live preflight; never overwrite a row.

    A new row must explicitly approve version 2: import makes version 1, and
    recording the execution review through edit makes version 2. Only sealed
    preflight may complete a pending duplicate check, with source provenance
    recorded separately. An existing record must match the entire execution
    review, version, binding and (when deferred) provenance without edits.
    """
    if type(bundle) is not ApprovedDraft:
        raise ApprovedDraftError("APPROVED_BUNDLE_AUTHORITY_REQUIRED")
    document = bundle._document()
    _require_customer_evidence(bundle, customer_evidence)
    execution = _execution_approval(bundle, customer_evidence)
    if client is None or not callable(getattr(client, "create_draft", None)):
        raise ApprovedDraftError("APPROVED_DRAFT_CLIENT_REQUIRED")
    try:
        checked_ledger = _private_path(ledger_path)
    except (OSError, ValueError, RuntimeError, TypeError):
        raise ApprovedDraftError("APPROVED_LEDGER_UNAVAILABLE") from None
    store = store_api.DraftTransferStore(checked_ledger)
    service = service_api.DraftTransferService(store, client)
    with store.transaction() as connection:
        existing = store.load(connection, bundle.order_id)
    if existing is None:
        if bundle.version != 2:
            raise ApprovedDraftError("APPROVED_NEW_ROW_VERSION_REQUIRED")
        output = io.StringIO(newline="")
        writer = csv.writer(output, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
        writer.writerow(contract.HEADERS)
        writer.writerow([document["row"][field] for field in contract.HEADERS])
        preview = service.preview_import(output.getvalue())
        if (
            not preview.get("can_commit")
            or preview.get("errors")
            or len(preview.get("rows", [])) != 1
            or preview["rows"][0]["action"] != "ADD"
        ):
            raise ApprovedDraftError("APPROVED_IMPORT_CONFLICT")
        service.commit_import(preview["preview_token"], preview["revision"])
        service.edit(
            bundle.order_id,
            1,
            {field: document["row"][field] for field in service_api.EDITABLE},
            execution.review(),
        )
        if execution.provenance_bytes is not None:
            with store.transaction(write=True) as connection:
                record = store.load(connection, bundle.order_id)
                if (
                    record is None
                    or record["version"] != bundle.version
                    or record["row"] != document["row"]
                    or record["review"] != execution.review()
                    or record["transfer"] is not None
                ):
                    raise ApprovedDraftError("APPROVED_LEDGER_CONFLICT")
                store.event(
                    connection,
                    "COORDINATOR_DUPLICATE_PREFLIGHT",
                    bundle.order_id,
                    bundle.version,
                    contract.unique_json(execution.provenance_bytes.decode("utf-8")),
                )
                store.bump(connection)
    record = _current_exact(service, bundle, execution)
    if record["transfer"]:
        if record["transfer"]["state"] not in service_api.FINAL_WRITE_STATES:
            raise ApprovedDraftError("APPROVED_PRIOR_ATTEMPT_BLOCKED")
        if not record["approved"]:
            raise ApprovedDraftError("APPROVED_LEDGER_APPROVAL_REQUIRED")
    elif record["approval"] is None:
        if execution.provenance_bytes is not None:
            _require_customer_evidence(bundle, customer_evidence)
        service.approve(
            bundle.order_id,
            bundle.version,
            execution.binding,
            "I_APPROVE_THIS_EXACT_HELP_SCOUT_DRAFT",
        )
    return PreparedDraft(
        service, bundle, customer_evidence, execution, _authority=_PREPARED_AUTHORITY
    )


def _read_component_json(path: str) -> dict[str, Any]:
    raw = _read_private_bundle(path)
    try:
        value = contract.unique_json(raw.decode("utf-8"))
        if type(value) is not dict:
            raise ValueError()
        return cast(dict[str, Any], value)
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise ApprovedDraftError("APPROVED_INPUT_JSON_INVALID") from None


def _write_new_bundle(path: str, raw: bytes) -> None:
    """Exclusive local create only; never replace a prior private artifact."""
    try:
        destination = _private_path(path)
        if destination.exists():
            raise ApprovedDraftError("APPROVED_OUTPUT_EXISTS")
        parent_before = destination.parent.lstat()
        if not stat.S_ISDIR(parent_before.st_mode):
            raise ApprovedDraftError("APPROVED_OUTPUT_UNAVAILABLE")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        descriptor = os.open(destination, flags, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            opened = os.fstat(handle.fileno())
            observed = destination.lstat()
            parent_after = destination.parent.lstat()
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or getattr(observed, "st_file_attributes", 0) & 0x400
                or (opened.st_dev, opened.st_ino) != (observed.st_dev, observed.st_ino)
                or (parent_before.st_dev, parent_before.st_ino)
                != (parent_after.st_dev, parent_after.st_ino)
            ):
                raise ApprovedDraftError("APPROVED_OUTPUT_UNAVAILABLE")
            # Recheck the controlled path after exclusive creation, before
            # putting private bytes in the new file. No cleanup overwrites or
            # deletes a partial artifact if any later write step fails.
            _private_path(destination)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except ApprovedDraftError:
        raise
    except FileExistsError:
        raise ApprovedDraftError("APPROVED_OUTPUT_EXISTS") from None
    except (OSError, ValueError, RuntimeError, TypeError):
        raise ApprovedDraftError("APPROVED_OUTPUT_UNAVAILABLE") from None


class _PreparationParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # argparse's default diagnostic echoes rejected private argument values.
        raise ApprovedDraftError("APPROVED_PREPARE_ARGUMENTS_INVALID")


def main(argv: list[str] | None = None) -> int:
    """Package supplied content approval; no auth, lease, ledger or HTTP."""
    parser = _PreparationParser(
        description="Package one supplied approved draft; local files only.", allow_abbrev=False
    )
    parser.add_argument("--row-json", action="append", help="private complete DOI row JSON")
    parser.add_argument(
        "--review-json", action="append", help="private factual review; duplicate may be unresolved"
    )
    parser.add_argument("--version", action="append", type=int, help="exact approved final version")
    parser.add_argument(
        "--source-approval-ref", action="append", help="existing approval reference"
    )
    parser.add_argument(
        "--output", action="append", help="new private output file; never overwrite"
    )
    try:
        args = parser.parse_args(argv)
        values = (
            args.row_json,
            args.review_json,
            args.version,
            args.source_approval_ref,
            args.output,
        )
        if not any(values):
            parser.print_help()
            return 0
        if any(value is None or len(value) != 1 for value in values):
            raise ApprovedDraftError("APPROVED_PREPARE_ARGUMENTS_INVALID")
        row = _read_component_json(args.row_json[0])
        review = _read_component_json(args.review_json[0])
        document = make_approved_bundle(
            row, review, version=args.version[0], source_approval_ref=args.source_approval_ref[0]
        )
        raw = cast(bytes, contract.encoded(document))
        if len(raw) > MAX_BUNDLE_BYTES:
            raise ApprovedDraftError("APPROVED_BUNDLE_FILE_INVALID")
        _write_new_bundle(args.output[0], raw)
        print(
            json.dumps(
                {
                    "status": "PREPARED",
                    "bundle_sha256": hashlib.sha256(raw).hexdigest(),
                    "version": document["version"],
                },
                sort_keys=True,
            )
        )
        return 0
    except ApprovedDraftError as error:
        code = (
            error.code
            if error.code in APPROVED_DRAFT_ERROR_CODES
            else "APPROVED_PREPARATION_FAILED"
        )
        print(json.dumps({"status": "BLOCKED", "code": code}, sort_keys=True))
        return 2


__all__ = [
    "APPROVED_DRAFT_ERROR_CODES",
    "BUNDLE_SCHEMA",
    "MAX_BUNDLE_BYTES",
    "ApprovedDraft",
    "ApprovedDraftError",
    "PreparedDraft",
    "load_approved_bundle",
    "make_approved_bundle",
    "prepare_draft",
]


if __name__ == "__main__":
    raise SystemExit(main())
