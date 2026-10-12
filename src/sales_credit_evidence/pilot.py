"""Explicit one-customer cached-token pilot; no issuing provider or persistence."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, cast

from .reader import EvidenceReader
from .transport import (
    MAILBOX_ID,
    TARGET_AUTHOR_ID,
    ReadClient,
    ReadError,
    SuppliedCredential,
    Transport,
    normalize_email,
)

OWNERSHIP_STATES = frozenset({"cleanup-complete", "controlled-handoff-complete"})


class Lease(Protocol):
    def acquire(self) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class PilotRequest:
    email: str = field(repr=False)
    connection_path: str = field(repr=False)
    ownership: str = ""
    sole_owner_confirmed: bool = False
    enable_live: bool = False


def _now() -> datetime:
    return datetime.now(UTC)


def _new_lease() -> Lease:
    # Reuse the existing fixed-user ownership contract, never the issuing provider.
    from doi_draft_transfer.session_auth import SessionLease

    return cast(Lease, SessionLease())  # type: ignore[no-untyped-call]


def _blocked(code: str, *, status: str = "BLOCKED") -> dict[str, object]:
    return {
        "status": status,
        "mailbox_id": MAILBOX_ID,
        "target_author_id": TARGET_AUTHOR_ID,
        "identity_status": "NOT_READ",
        "complete": False,
        "no_scoped_conversations": False,
        "customer_count": 0,
        "conversation_count": 0,
        "thread_count": 0,
        "credit_classification": "NOT_EVALUATED",
        "issues": [code],
    }


def run_pilot(
    request: PilotRequest,
    *,
    snapshot_loader: Callable[[str], SuppliedCredential] | None = None,
    lease_factory: Callable[[], Lease] | None = None,
    transport: Transport | None = None,
    clock: Callable[[], datetime] = _now,
) -> dict[str, object]:
    """Return counts/codes only. Injection points are for synthetic offline tests.

    Ownership flags are an operator attestation, not a check of external cleanup.
    The existing lease excludes cooperating issuers while this reader runs. It
    does not prove that unrelated processes have stopped using the connection.
    """
    if not isinstance(request, PilotRequest):
        return _blocked("invalid_pilot_request")
    if type(request.enable_live) is not bool:
        return _blocked("invalid_live_activation")
    if not request.enable_live:
        return _blocked("live_access_disabled", status="DISABLED")
    if type(request.ownership) is not str or request.ownership not in OWNERSHIP_STATES:
        return _blocked("ownership_required")
    if request.sole_owner_confirmed is not True:
        return _blocked("sole_owner_confirmation_required")
    try:
        email = normalize_email(request.email)
    except ReadError:
        return _blocked("invalid_email")

    # These imports have no I/O. No default provider is constructed before gates.
    from .cached_auth import (
        CACHED_AUTH_ERROR_CODES,
        EXPIRY_MARGIN_SECONDS,
        load_cached_snapshot,
        validate_connection_path,
    )

    try:
        path = validate_connection_path(request.connection_path)
    except ReadError:
        return _blocked("invalid_connection_path")

    lease: Lease | None = None
    phase = "lease"
    report = _blocked("pilot_failed")
    try:
        lease = (lease_factory or _new_lease)()
        lease.acquire()
        phase = "snapshot"
        credential = (
            snapshot_loader(path)
            if snapshot_loader is not None
            else load_cached_snapshot(path, clock=clock)
        )
        if not isinstance(credential, SuppliedCredential):
            raise ReadError("invalid_credential")
        try:
            now = clock()
            if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
                raise ValueError("clock")
        except Exception:
            raise ReadError("cached_clock_invalid") from None
        if (credential.expires_at - now).total_seconds() <= EXPIRY_MARGIN_SECONDS:
            raise ReadError("stale_cached_snapshot")
        phase = "read"
        client = ReadClient(
            email,
            credential=credential,
            enable_live=True,
            transport=transport,
            clock=clock,
            max_attempts=1,
            expiry_margin_seconds=EXPIRY_MARGIN_SECONDS,
        )
        result = EvidenceReader(client, include_content=False, max_requests=50).read()
        report = result.summary()
        report.update(
            status="COMPLETE" if result.complete else "INCOMPLETE",
            mailbox_id=MAILBOX_ID,
            target_author_id=TARGET_AUTHOR_ID,
        )
    except ReadError as error:
        # A custom dependency may raise arbitrary errors; never print its message.
        allowed = CACHED_AUTH_ERROR_CODES | {
            "invalid_credential",
            "invalid_credential_expiry",
            "stale_credential",
        }
        report = _blocked(error.code if error.code in allowed else "cached_snapshot_unavailable")
    except Exception as error:
        code = "pilot_failed"
        if phase == "lease":
            code = (
                "credential_owner_conflict"
                if getattr(error, "code", None) == "HELP_SCOUT_RENEWAL_OWNER_CONFLICT"
                else "ownership_lease_unavailable"
            )
        elif phase == "snapshot":
            code = "cached_snapshot_unavailable"
        report = _blocked(code)
    finally:
        if lease is not None:
            try:
                lease.close()
            except Exception:
                report["status"] = "INCOMPLETE"
                report["complete"] = False
                report["no_scoped_conversations"] = False
                issues = report.get("issues")
                report["issues"] = (
                    [*issues, "ownership_release_failed"]
                    if isinstance(issues, list)
                    else ["ownership_release_failed"]
                )
    return report
