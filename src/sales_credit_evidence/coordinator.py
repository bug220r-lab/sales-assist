"""Default-off, single-owner credit read followed by one approved unsent draft.

No process startup, credential/cache write, renewal loop, or persistent activation.
Injected dependencies are exclusively for synthetic tests. The original cleanup
lock and the existing Sales Assist lease are held across the authorized session.
"""

from __future__ import annotations

import argparse
import json
import ntpath
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Never

from .pilot import OWNERSHIP_STATES, Lease, _new_lease
from .reader import EvidenceReader, EvidenceResult
from .transport import ReadClient, ReadError, SuppliedCredential, Transport, normalize_email


@dataclass(frozen=True)
class CoordinatorRequest:
    credit_email: str = field(repr=False)
    connection_path: str = field(repr=False)
    cleanup_lock_path: str = field(repr=False)
    approval_bundle_path: str = field(repr=False)
    approval_bundle_sha256: str = field(repr=False)
    ledger_path: str = field(repr=False)
    enable_live: bool = False
    allow_issuance: bool = False
    allow_draft: bool = False
    ownership: str = ""
    sole_owner_confirmed: bool = False


def _now() -> datetime:
    return datetime.now(UTC)


def _local_path(value: object, suffix: str | None = None) -> str:
    # Lexical only; disabled/invalid requests must not inspect any filesystem.
    if type(value) is not str or not value or value != value.strip():
        raise ReadError("coordinator_path_invalid")
    drive, tail = ntpath.splitdrive(value)
    if (
        re.fullmatch(r"[A-Za-z]:", drive) is None
        or not tail.startswith(("\\", "/"))
        or any(part in {".", ".."} for part in re.split(r"[\\/]", tail))
        or any(ord(char) < 32 for char in value)
        or any(char in tail for char in ':*?"<>|')
        or (suffix is not None and not value.lower().endswith(suffix))
    ):
        raise ReadError("coordinator_path_invalid")
    sync = re.compile(r"OneDrive(?: - .+)?|Dropbox|Google Drive|iCloudDrive", re.I)
    if any(sync.fullmatch(part) for part in re.split(r"[\\/]", tail)):
        raise ReadError("coordinator_path_invalid")
    normalized = ntpath.normcase(ntpath.normpath(value))
    for name in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        known = os.environ.get(name)
        if known:
            root = ntpath.normcase(ntpath.normpath(known)).rstrip("\\")
            if normalized == root or normalized.startswith(root + "\\"):
                raise ReadError("coordinator_path_invalid")
    return value


def _new_cleanup_lease(connection_path: str, cleanup_lock_path: str) -> Lease:
    from .cleanup_lock import new_cleanup_lease

    return new_cleanup_lease(connection_path, cleanup_lock_path)


def _report(status: str, code: str | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "complete": False,
        "credit_summary": None,
        "draft_preflight": None,
        "draft_result": None,
        "issuance_attempted": False,
        "credit_classification": "NOT_EVALUATED",
        "issues": [] if code is None else [code],
    }


_RESULT_STATES = frozenset(
    {
        "IN_FLIGHT",
        "UNKNOWN",
        "CREATED",
        "CREATED_UNVERIFIED",
        "AUTH_REQUIRED",
        "RATE_LIMITED",
        "REJECTED",
    }
)
_RESULT_CODES = frozenset(
    {
        "DRAFT_CREATED_VERIFIED",
        "DRAFT_READBACK_REQUIRED",
        "WRITE_OUTCOME_UNKNOWN",
        "CREATION_ID_MISSING",
        "HELP_SCOUT_AUTH_REQUIRED",
        "HELP_SCOUT_RATE_LIMITED",
        "HELP_SCOUT_REQUEST_REJECTED",
        "ONE_DRAFT_BLOCKED",
        "TRANSFER_RESERVED",
        "TRANSFER_RESULT_UNRECOGNIZED",
        "TRANSFER_RESULT_RECORDED",
    }
)


def _draft_summary(value: object) -> dict[str, object]:
    if type(value) is not dict:
        raise ReadError("draft_result_invalid")
    state = value.get("state")
    code = value.get("code")
    result: dict[str, object] = {
        "state": state if type(state) is str and state in _RESULT_STATES else "UNKNOWN",
        "code": code if type(code) is str and code in _RESULT_CODES else "TRANSFER_RESULT_RECORDED",
        "retry_allowed": False,
    }
    identifier = value.get("conversation_id")
    if type(identifier) is str and re.fullmatch(r"[1-9][0-9]{0,18}", identifier):
        result["conversation_id"] = identifier
    return result


def run_coordinator(
    request: CoordinatorRequest,
    *,
    cleanup_lease_factory: Callable[[str, str], Lease] | None = None,
    session_lease_factory: Callable[[], Lease] | None = None,
    private_path_validator: Callable[[str], object] | None = None,
    snapshot_owner_factory: Callable[[str], Any] | None = None,
    bundle_loader: Callable[[str, str], Any] | None = None,
    reader_factory: Callable[[str, SuppliedCredential], EvidenceResult] | None = None,
    preflight: Callable[[Any, SuppliedCredential], Any] | None = None,
    draft_client_factory: Callable[[Any, Any, SuppliedCredential], Any] | None = None,
    draft_runner: Callable[..., Any] | None = None,
    transport: Transport | None = None,
    clock: Callable[[], datetime] = _now,
) -> dict[str, Any]:
    """Hold both leases across all I/O; report observed scope, never assign credit."""
    if type(request) is not CoordinatorRequest:
        return _report("BLOCKED", "invalid_coordinator_request")
    if type(request.enable_live) is not bool:
        return _report("BLOCKED", "invalid_live_activation")
    if not request.enable_live:
        return _report("DISABLED", "live_access_disabled")
    if request.allow_draft is not True:
        return _report("BLOCKED", "one_draft_authorization_required")
    if type(request.allow_issuance) is not bool:
        return _report("BLOCKED", "invalid_issuance_activation")
    if type(request.ownership) is not str or request.ownership not in OWNERSHIP_STATES:
        return _report("BLOCKED", "ownership_required")
    if request.sole_owner_confirmed is not True:
        return _report("BLOCKED", "sole_owner_confirmation_required")

    from .approved_draft import APPROVED_DRAFT_ERROR_CODES, load_approved_bundle, prepare_draft
    from .cached_auth import validate_connection_path
    from .draft_preflight import verify_customer_and_duplicates
    from .one_draft_client import OneDraftClient
    from .session_snapshot import SESSION_AUTH_ERROR_CODES, SessionSnapshotOwner

    try:
        email = normalize_email(request.credit_email)
        path = validate_connection_path(request.connection_path)
        _local_path(request.cleanup_lock_path)
        _local_path(request.approval_bundle_path, ".json")
        _local_path(request.ledger_path, ".sqlite3")
        if ntpath.basename(request.ledger_path) != "doi-draft-transfer.sqlite3":
            raise ReadError("coordinator_path_invalid")
        if (
            type(request.approval_bundle_sha256) is not str
            or re.fullmatch(r"[a-f0-9]{64}", request.approval_bundle_sha256) is None
        ):
            raise ReadError("approved_file_hash_required")
    except Exception:
        return _report("BLOCKED", "invalid_coordinator_scope")

    def read_credit(target: str, credential: SuppliedCredential) -> EvidenceResult:
        client = ReadClient(
            target,
            credential=credential,
            enable_live=True,
            transport=transport,
            clock=clock,
            max_attempts=1,
            expiry_margin_seconds=120,
        )
        return EvidenceReader(client, include_content=False, max_requests=50).read()

    def check_draft(bundle: Any, credential: SuppliedCredential) -> Any:
        return verify_customer_and_duplicates(bundle, credential, transport=transport, clock=clock)

    # Imports are inert; all default resource construction below follows gates.
    leases: list[tuple[str, Any]] = []
    owner: Any = None
    report = _report("BLOCKED")
    phase = "cleanup_lease"
    try:
        cleanup = (cleanup_lease_factory or _new_cleanup_lease)(path, request.cleanup_lock_path)
        leases.append(("cleanup_lease", cleanup))
        cleanup.acquire()
        phase = "session_lease"
        session = (session_lease_factory or _new_lease)()
        leases.append(("session_lease", session))
        session.acquire()
        phase = "private_storage"
        if private_path_validator is None:
            from doi_draft_transfer import launch

            path_policy: Any = launch.private_path
        else:
            path_policy = private_path_validator
        path_policy(request.approval_bundle_path)
        path_policy(request.ledger_path)
        phase = "approved_bundle"
        bundle = (bundle_loader or load_approved_bundle)(
            request.approval_bundle_path, request.approval_bundle_sha256
        )
        phase = "snapshot"
        owner = (snapshot_owner_factory or (lambda p: SessionSnapshotOwner(p, clock=clock)))(path)
        leases.append(("snapshot", owner))
        credential = owner.load(enable_live=True, allow_issuance=request.allow_issuance)
        if not isinstance(credential, SuppliedCredential):
            raise ReadError("invalid_credential")
        now = clock()
        if (
            not isinstance(now, datetime)
            or now.tzinfo is None
            or now.utcoffset() is None
            or (credential.expires_at - now).total_seconds() <= 120
        ):
            raise ReadError("session_issued_token_unusable")
        phase = "credit_read"
        credit = (reader_factory or read_credit)(email, credential)
        if type(credit) is not EvidenceResult:
            raise ReadError("credit_result_invalid")
        report["credit_summary"] = credit.summary()
        if not credit.complete:
            report["status"] = "INCOMPLETE"
            report["issues"].append("credit_read_incomplete")
        else:
            phase = "draft_preflight"
            evidence = (preflight or check_draft)(bundle, credential)
            observed = evidence.summary()
            if type(observed) is not dict or any(
                type(observed.get(key)) is not int or observed[key] < 0
                for key in ("customer_count", "conversation_count", "thread_count")
            ):
                raise ReadError("draft_preflight_incomplete")
            report["draft_preflight"] = {
                "duplicate_check": "NO_MATCH_IN_ACCESSIBLE_MAILBOX_SNAPSHOT",
                "global_draft_absence_proved": False,
                **{
                    key: observed[key]
                    for key in ("customer_count", "conversation_count", "thread_count")
                },
            }
            phase = "draft_client"
            client = (
                draft_client_factory(bundle, evidence, credential)
                if draft_client_factory is not None
                else OneDraftClient(bundle, evidence, credential, clock=clock)
            )
            leases.append(("draft_client", client))
            phase = "draft_destination"
            client.check_destination()
            phase = "draft_prepare"
            prepared = (draft_runner or prepare_draft)(
                bundle, request.ledger_path, client=client, customer_evidence=evidence
            )
            phase = "draft_execute"
            result = _draft_summary(prepared.execute_once())
            report["draft_result"] = result
            complete = result["state"] == "CREATED" and result["code"] == "DRAFT_CREATED_VERIFIED"
            report.update(status="COMPLETE" if complete else "INCOMPLETE", complete=complete)
            if not complete:
                report["issues"].append("draft_outcome_unverified_no_retry")
    except Exception as error:
        # Only explicitly enumerated codes may escape; never stringify an error.
        from .cleanup_lock import CLEANUP_LOCK_ERROR_CODES
        from .draft_preflight import DRAFT_PREFLIGHT_ERROR_CODES
        from .one_draft_client import ONE_DRAFT_ERROR_CODES

        code = getattr(error, "code", None)
        allowed = (
            SESSION_AUTH_ERROR_CODES
            | APPROVED_DRAFT_ERROR_CODES
            | DRAFT_PREFLIGHT_ERROR_CODES
            | ONE_DRAFT_ERROR_CODES
            | CLEANUP_LOCK_ERROR_CODES
            | {
                "invalid_credential",
                "credit_result_invalid",
                "draft_result_invalid",
                "HELP_SCOUT_RENEWAL_OWNER_CONFLICT",
            }
        )
        report["issues"].append(
            code if type(code) is str and code in allowed else phase + "_failed"
        )
        report["status"] = "INCOMPLETE" if report["credit_summary"] is not None else "BLOCKED"
    finally:
        if owner is not None:
            try:
                report["issuance_attempted"] = owner.issuance_attempted is True
            except Exception:
                report["issues"].append("issuance_status_unavailable")
                report.update(status="INCOMPLETE", complete=False)
        for name, resource in reversed(leases):
            try:
                resource.close()
            except Exception:
                report["issues"].append(name + "_release_failed")
                report.update(status="INCOMPLETE", complete=False)
    return report


class _ArgumentError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise _ArgumentError from None


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(
        description="Single-owner pilots. Default off; fresh external handoff required.",
        allow_abbrev=False,
    )
    for flag in ("live", "allow-one-issuance", "allow-one-draft", "confirm-sole-owner"):
        parser.add_argument("--" + flag, action="count", default=0)
    for flag in (
        "credit-email",
        "connection-path",
        "cleanup-lock-path",
        "approval-bundle-path",
        "approval-bundle-sha256",
        "ledger-path",
        "ownership",
    ):
        parser.add_argument("--" + flag, action="append")
    try:
        args = vars(parser.parse_args(argv))
        if any(
            value > 1 if type(value) is int else len(value) != 1
            for value in args.values()
            if value is not None
        ):
            raise _ArgumentError
        result = run_coordinator(
            CoordinatorRequest(
                **{
                    key: (args[key] or [""])[0]
                    for key in (
                        "credit_email",
                        "connection_path",
                        "cleanup_lock_path",
                        "approval_bundle_path",
                        "approval_bundle_sha256",
                        "ledger_path",
                        "ownership",
                    )
                },
                enable_live=bool(args["live"]),
                allow_issuance=bool(args["allow_one_issuance"]),
                allow_draft=bool(args["allow_one_draft"]),
                sole_owner_confirmed=bool(args["confirm_sole_owner"]),
            )
        )
    except _ArgumentError:
        result = _report("BLOCKED", "invalid_arguments")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"COMPLETE", "DISABLED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
