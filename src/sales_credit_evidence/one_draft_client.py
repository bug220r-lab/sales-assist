"""One approved unsent draft using one existing customer and expiring snapshot.

The coordinator supplies the live/ownership gates and durable reservation. This
client adds an independent one-POST limit and never renews, retries, or persists
credentials. Construction performs no I/O; tests inject the complete transport.
"""

from __future__ import annotations

import hashlib
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from doi_draft_transfer import helpscout as helpscout_module
from doi_draft_transfer.contract import TransferError

from .transport import API_ORIGIN, MAILBOX_ID, TARGET_AUTHOR_ID, SuppliedCredential

legacy: Any = helpscout_module
DraftTransport = Callable[[str, str, dict[str, Any] | None, str], tuple[int, dict[str, str], bytes]]
_ID = re.compile(r"[1-9][0-9]{0,18}\Z")
ONE_DRAFT_ERROR_CODES = frozenset(
    {
        "ONE_DRAFT_SCOPE_INVALID",
        "ONE_DRAFT_PAYLOAD_MISMATCH",
        "ONE_DRAFT_AUTH_UNAVAILABLE",
        "ONE_DRAFT_CREDENTIAL_EXPIRED",
        "ONE_DRAFT_WRITE_PROHIBITED",
        "ONE_DRAFT_READ_PROHIBITED",
        "ONE_DRAFT_OPERATION_PROHIBITED",
        "ONE_DRAFT_RESPONSE_UNVERIFIED",
        "ONE_DRAFT_DESTINATION_UNVERIFIED",
        "ONE_DRAFT_BLOCKED",
        "ONE_DRAFT_KNOWN_CONVERSATION_REQUIRED",
        "ONE_DRAFT_ENVIRONMENT_PROHIBITED",
        "WRITE_OUTCOME_UNKNOWN",
        "HELP_SCOUT_AUTH_REQUIRED",
        "HELP_SCOUT_RATE_LIMITED",
        "HELP_SCOUT_REQUEST_REJECTED",
        "CREATION_ID_MISSING",
        "DRAFT_READBACK_REQUIRED",
        "DRAFT_CREATED_VERIFIED",
    }
)


class DraftBundle(Protocol):
    @property
    def recipient(self) -> str: ...

    @property
    def subject(self) -> str: ...

    @property
    def rendered_body_sha256(self) -> str: ...

    @property
    def order_id(self) -> str: ...

    @property
    def bundle_sha256(self) -> str: ...


class CustomerEvidence(Protocol):
    @property
    def customer_id(self) -> int: ...

    def assert_for(self, bundle: DraftBundle) -> None: ...


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _error(code: str) -> TransferError:
    return TransferError(code, 409)  # type: ignore[no-untyped-call]


class OneDraftClient(helpscout_module.HelpScoutDraftClient):
    """A request capability limited to the already-approved bundle and customer."""

    def __init__(
        self,
        bundle: DraftBundle,
        customer_evidence: CustomerEvidence,
        credential: SuppliedCredential,
        *,
        clock: Callable[[], datetime] = _utcnow,
        transport: DraftTransport | None = None,
    ) -> None:
        try:
            customer_evidence.assert_for(bundle)
            if (
                type(customer_evidence.customer_id) is not int
                or not 1 <= customer_evidence.customer_id <= 2**63 - 1
                or not isinstance(credential, SuppliedCredential)
            ):
                raise ValueError()
            self._scope = (
                bundle.recipient,
                bundle.subject,
                bundle.rendered_body_sha256,
                bundle.order_id,
                bundle.bundle_sha256,
            )
            if any(type(value) is not str or not value for value in self._scope):
                raise ValueError()
        except Exception:
            raise _error("ONE_DRAFT_SCOPE_INVALID") from None
        self._bundle = bundle
        self._evidence = customer_evidence
        self._customer_id = customer_evidence.customer_id
        self._credential: SuppliedCredential | None = credential
        self._clock = clock
        self._transport: DraftTransport = (
            transport
            if transport is not None
            else cast(DraftTransport, legacy.HelpScoutDraftClient._send)
        )
        self._guard = threading.RLock()
        self._get_paths: set[str] = set()
        self._post_reserved = False
        self._post_attempted = False
        self._destination_verified = False
        self._auth_failed = False
        self._closed = False
        self._created_id: str | None = None
        self._approved_payload: dict[str, Any] | None = None

    @classmethod
    def from_environment(cls) -> None:
        """Never inherit the ordinary draft client's environment/auth selection."""
        raise _error("ONE_DRAFT_ENVIRONMENT_PROHIBITED")

    def _assert_scope(self) -> None:
        try:
            self._evidence.assert_for(self._bundle)
            current = (
                self._bundle.recipient,
                self._bundle.subject,
                self._bundle.rendered_body_sha256,
                self._bundle.order_id,
                self._bundle.bundle_sha256,
            )
            if current != self._scope or self._evidence.customer_id != self._customer_id:
                raise ValueError()
        except Exception:
            raise _error("ONE_DRAFT_SCOPE_INVALID") from None

    def _payload(self, row: dict[str, Any]) -> dict[str, Any]:
        self._assert_scope()
        try:
            recipient, subject, body_hash, order_id, _ = self._scope
            if (
                type(row) is not dict
                or row.get("recipient_email") != recipient
                or row.get("subject") != subject
                or row.get("order_id") != order_id
                or type(row.get("selected_body_text")) is not str
            ):
                raise ValueError()
            body = legacy.rendered_body(row["selected_body_text"])
            if hashlib.sha256(body.encode("utf-8")).hexdigest() != body_hash:
                raise ValueError()
            expected = {
                "subject": subject,
                "customer": {"email": recipient},
                "mailboxId": MAILBOX_ID,
                "type": "email",
                "status": "active",
                "assignTo": TARGET_AUTHOR_ID,
                "user": TARGET_AUTHOR_ID,
                "autoReply": False,
                "threads": [
                    {
                        "type": "reply",
                        "draft": True,
                        "user": TARGET_AUTHOR_ID,
                        "customer": {"email": recipient},
                        "text": body,
                    }
                ],
            }
            candidate = legacy.payload_for(row)
            if legacy.encoded(candidate) != legacy.encoded(expected):
                raise ValueError()
            expected["customer"] = {"id": self._customer_id}
            expected["threads"][0]["customer"] = {"id": self._customer_id}  # type: ignore[index]
            return expected
        except Exception:
            raise _error("ONE_DRAFT_PAYLOAD_MISMATCH") from None

    def _bearer(self) -> str:
        if self._closed or self._auth_failed:
            raise _error("ONE_DRAFT_AUTH_UNAVAILABLE")
        try:
            now = self._clock()
            credential = self._credential
            if (
                credential is None
                or not isinstance(now, datetime)
                or now.tzinfo is None
                or now.utcoffset() is None
                or (credential.expires_at - now).total_seconds() <= 120
            ):
                raise ValueError()
            return credential.token
        except Exception:
            raise _error("ONE_DRAFT_CREDENTIAL_EXPIRED") from None

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> tuple[int, dict[str, str], bytes]:
        with self._guard:
            if method == "POST" and path == "/v2/conversations":
                if self._post_reserved or not self._destination_verified:
                    raise _error("ONE_DRAFT_WRITE_PROHIBITED")
                self._assert_scope()
                try:
                    matches = (
                        type(payload) is dict
                        and self._approved_payload is not None
                        and legacy.encoded(payload) == legacy.encoded(self._approved_payload)
                    )
                except Exception:
                    matches = False
                if not matches:
                    raise _error("ONE_DRAFT_PAYLOAD_MISMATCH")
                self._post_reserved = True
            elif method == "GET" and payload is None:
                allowed = {f"/v2/mailboxes/{MAILBOX_ID}", f"/v2/users/{TARGET_AUTHOR_ID}"}
                if self._created_id is not None:
                    allowed.add(f"/v2/conversations/{self._created_id}?embed=threads")
                if path not in allowed or path in self._get_paths or len(self._get_paths) >= 3:
                    raise _error("ONE_DRAFT_READ_PROHIBITED")
                self._get_paths.add(path)
            else:
                raise _error("ONE_DRAFT_OPERATION_PROHIBITED")
            bearer = self._bearer()
            if method == "POST":
                self._post_attempted = True
            try:
                status, headers, raw = self._transport(method, path, payload, bearer)
                if status in (401, 403):
                    self._auth_failed = True
                if (
                    type(status) is not int
                    or not 100 <= status <= 599
                    or type(headers) is not dict
                    or any(type(k) is not str or type(v) is not str for k, v in headers.items())
                    or type(raw) is not bytes
                    or len(raw) > legacy.MAX_RESPONSE
                ):
                    raise ValueError()
                if (
                    method == "GET"
                    and self._created_id is not None
                    and "conversations" in path
                    and status == 200
                ):
                    value = legacy.json.loads(raw, object_pairs_hook=_unique_object)
                    customer = value.get("primaryCustomer", {})
                    if type(customer.get("id")) is not int or customer["id"] != self._customer_id:
                        raise ValueError()
                return status, headers, raw
            except Exception:
                raise _error("ONE_DRAFT_RESPONSE_UNVERIFIED") from None

    def check_destination(self) -> dict[str, Any]:
        with self._guard:
            self._destination_verified = False
            try:
                for kind, identifier in (("mailboxes", MAILBOX_ID), ("users", TARGET_AUTHOR_ID)):
                    status, _, raw = self._request("GET", f"/v2/{kind}/{identifier}")
                    value = legacy.json.loads(raw, object_pairs_hook=_unique_object)
                    if (
                        status != 200
                        or type(value.get("id")) is not int
                        or value["id"] != identifier
                    ):
                        raise ValueError()
            except Exception:
                raise _error("ONE_DRAFT_DESTINATION_UNVERIFIED") from None
            self._destination_verified = True
            return {"verified": True, "mailbox_id": MAILBOX_ID, "user_id": TARGET_AUTHOR_ID}

    def create_draft(self, row: dict[str, Any]) -> dict[str, Any]:
        with self._guard:
            try:
                payload = self._payload(row)
                self._approved_payload = payload
                status, headers, _ = self._request("POST", "/v2/conversations", payload)
            except Exception:
                return {
                    "state": "UNKNOWN" if self._post_attempted else "REJECTED",
                    "code": "WRITE_OUTCOME_UNKNOWN"
                    if self._post_attempted
                    else "ONE_DRAFT_BLOCKED",
                    "retry_allowed": False,
                }
            finally:
                self._approved_payload = None
            if status != 201:
                state, code = ("UNKNOWN", "WRITE_OUTCOME_UNKNOWN")
                if status in {401, 403}:
                    state, code = "AUTH_REQUIRED", "HELP_SCOUT_AUTH_REQUIRED"
                elif status == 429:
                    state, code = "RATE_LIMITED", "HELP_SCOUT_RATE_LIMITED"
                elif 400 <= status < 500 and status not in {408, 409, 425}:
                    state, code = "REJECTED", "HELP_SCOUT_REQUEST_REJECTED"
                return {"state": state, "code": code, "retry_allowed": False}
            identifier = headers.get("resource-id", "")
            if _ID.fullmatch(identifier) is None:
                return {"state": "UNKNOWN", "code": "CREATION_ID_MISSING", "retry_allowed": False}
            self._created_id = identifier
            result = {
                "state": "CREATED_UNVERIFIED",
                "code": "DRAFT_READBACK_REQUIRED",
                "conversation_id": identifier,
                "web_link": legacy.safe_web_link(headers.get("web-location"), identifier),
                "api_location": f"{API_ORIGIN}/v2/conversations/{identifier}",
                "retry_allowed": False,
            }
            return self.verify_draft(row, result)

    def verify_draft(self, row: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        with self._guard:
            if self._created_id is None or result.get("conversation_id") != self._created_id:
                raise _error("ONE_DRAFT_KNOWN_CONVERSATION_REQUIRED")
            safe = {
                "conversation_id": self._created_id,
                "web_link": legacy.safe_web_link(result.get("web_link"), self._created_id),
                "api_location": f"{API_ORIGIN}/v2/conversations/{self._created_id}",
            }
            safe.update(
                state="CREATED_UNVERIFIED", code="DRAFT_READBACK_REQUIRED", retry_allowed=False
            )
            try:
                self._payload(row)
                return cast(
                    dict[str, Any], legacy.HelpScoutDraftClient.verify_draft(self, row, safe)
                )
            except Exception:
                return safe

    def close(self) -> None:
        with self._guard:
            self._closed = True
            self._credential = None


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result
