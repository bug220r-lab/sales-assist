"""Opt-in server-only HTTPS adapter with one closed draft-create operation.

No send, publish, status mutation, OAuth grant creation, redirect or retry endpoint.
Official API semantics are recorded in docs/doi-draft-transfer.md.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import ssl
from html.parser import HTMLParser
from urllib.parse import urlsplit

from .contract import MAILBOX_ID, USER_ID, TransferError, encoded, rendered_body

HOST = "api.helpscout.net"
MAX_RESPONSE = 512 * 1024


def payload_for(row):
    return {
        "subject": row["subject"],
        "customer": {"email": row["recipient_email"]},
        "mailboxId": MAILBOX_ID,
        "type": "email",
        "status": "active",
        "assignTo": USER_ID,
        "user": USER_ID,
        "autoReply": False,
        "threads": [
            {
                "type": "reply",
                "draft": True,
                "user": USER_ID,
                "customer": {"email": row["recipient_email"]},
                "text": rendered_body(row["selected_body_text"]),
            }
        ],
    }


def safe_web_link(value, conversation_id):
    if type(value) is not str or len(value) > 512:
        return None
    try:
        url = urlsplit(value)
        if (
            url.scheme == "https"
            and url.netloc == "secure.helpscout.net"
            and re.fullmatch(rf"/conversation/{conversation_id}(?:/[0-9]+)?/?", url.path)
            and not url.query
            and not url.fragment
        ):
            return value
    except ValueError:
        pass
    return None


class HelpScoutDraftClient:
    def __init__(self, token):
        if (
            type(token) is not str
            or not token
            or any(c.isspace() for c in token)
            or any(ord(c) < 33 or ord(c) > 126 for c in token)
        ):
            raise TransferError("HELP_SCOUT_CONFIGURATION_REQUIRED", 503)
        self._token = token

    @classmethod
    def from_environment(cls):
        # Existing operator-managed secret injection only. No persisted grant or token files.
        if os.environ.get("SSA_HELPSCOUT_DRAFT_TRANSFER") != "1":
            return None
        token = os.environ.get("SSA_HELPSCOUT_ACCESS_TOKEN")
        return cls(token) if token else None

    def _request(self, method, path, payload=None):
        allowed_get = path in {
            f"/v2/mailboxes/{MAILBOX_ID}",
            f"/v2/users/{USER_ID}",
        } or re.fullmatch(r"/v2/conversations/[1-9][0-9]*\?embed=threads", path)
        if not (
            method == "POST" and path == "/v2/conversations" or method == "GET" and allowed_get
        ):
            raise TransferError("HELP_SCOUT_OPERATION_PROHIBITED", 403)
        connection = http.client.HTTPSConnection(
            HOST, timeout=15, context=ssl.create_default_context()
        )
        try:
            connection.request(
                method,
                path,
                body=encoded(payload) if payload is not None else None,
                headers={
                    "Authorization": "Bearer " + self._token,
                    "Content-Type": "application/json; charset=utf-8",
                    "Accept": "application/hal+json",
                },
            )
            response = connection.getresponse()
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise OSError("response bound")
            return response.status, {k.lower(): v for k, v in response.getheaders()}, raw
        finally:
            connection.close()

    def check_destination(self):
        """Explicit read-only check; never enumerates or fetches customer contacts."""
        for kind, identifier in (("mailboxes", MAILBOX_ID), ("users", USER_ID)):
            try:
                status, _, raw = self._request("GET", f"/v2/{kind}/{identifier}")
                if status == 401:
                    raise TransferError("HELP_SCOUT_AUTH_EXPIRED", 503)
                if status != 200 or json.loads(raw).get("id") != identifier:
                    raise TransferError("HELP_SCOUT_DESTINATION_UNVERIFIED", 503)
            except TransferError:
                raise
            except (OSError, ValueError, AttributeError, http.client.HTTPException):
                raise TransferError("HELP_SCOUT_DESTINATION_UNVERIFIED", 503) from None
        return {"verified": True, "mailbox_id": MAILBOX_ID, "user_id": USER_ID}

    def create_draft(self, row):
        payload = payload_for(row)
        # These invariants cannot be supplied/overridden by CSV or browser request fields.
        assert payload["threads"][0]["draft"] is True
        assert payload["autoReply"] is False and payload["mailboxId"] == MAILBOX_ID
        try:
            status, headers, _ = self._request("POST", "/v2/conversations", payload)
        except (OSError, http.client.HTTPException, TimeoutError):
            return {"state": "UNKNOWN", "code": "WRITE_OUTCOME_UNKNOWN", "retry_allowed": False}
        if status in {401, 403}:
            return {
                "state": "AUTH_REQUIRED",
                "code": "HELP_SCOUT_AUTH_REQUIRED",
                "retry_allowed": True,
            }
        if status == 429:
            wait = headers.get("x-ratelimit-retry-after", headers.get("retry-after", "60"))
            seconds = int(wait) if re.fullmatch(r"[0-9]{1,6}", wait) else 60
            return {
                "state": "RATE_LIMITED",
                "code": "HELP_SCOUT_RATE_LIMITED",
                "retry_after_seconds": max(1, min(seconds, 86400)),
                "retry_allowed": True,
            }
        if 400 <= status < 500 and status not in {408, 409, 425}:
            return {
                "state": "REJECTED",
                "code": "HELP_SCOUT_REQUEST_REJECTED",
                "retry_allowed": True,
                "http_status": status,
            }
        if status != 201:
            return {"state": "UNKNOWN", "code": "WRITE_OUTCOME_UNKNOWN", "retry_allowed": False}
        identifier = headers.get("resource-id", "")
        if not re.fullmatch(r"[1-9][0-9]{0,18}", identifier):
            return {"state": "UNKNOWN", "code": "CREATION_ID_MISSING", "retry_allowed": False}
        result = {
            "state": "CREATED_UNVERIFIED",
            "code": "DRAFT_READBACK_REQUIRED",
            "conversation_id": identifier,
            "web_link": safe_web_link(headers.get("web-location"), identifier),
            "api_location": f"https://{HOST}/v2/conversations/{identifier}",
            "retry_allowed": False,
        }
        return self.verify_draft(row, result)

    def verify_draft(self, row, result):
        """A readback never retries a write, including after a timeout or restart."""
        result = dict(result)
        identifier = result.get("conversation_id", "")
        if not re.fullmatch(r"[1-9][0-9]{0,18}", identifier):
            raise TransferError("KNOWN_CONVERSATION_REQUIRED", 409)
        # Prior verification describes an earlier read, never the current remote state.
        result.update(
            state="CREATED_UNVERIFIED", code="DRAFT_READBACK_REQUIRED", retry_allowed=False
        )
        try:
            status, _, raw = self._request("GET", f"/v2/conversations/{identifier}?embed=threads")
            if status != 200:
                return result
            value = json.loads(raw)
            threads = value.get("_embedded", {}).get("threads", [])
            messages = [t for t in threads if t.get("type") == "message"]
            verified = (
                value.get("id") == int(identifier)
                and value.get("state") == "draft"
                and value.get("mailboxId") == MAILBOX_ID
                and value.get("subject") == row["subject"]
                and value.get("assignee", {}).get("id") == USER_ID
                and value.get("primaryCustomer", {}).get("email", "").casefold()
                == row["recipient_email"].casefold()
                and len(messages) == 1
                and messages[0].get("state") == "draft"
                and messages[0].get("createdBy", {}).get("id") == USER_ID
                and messages[0].get("to") == [row["recipient_email"]]
                and not messages[0].get("cc")
                and not messages[0].get("bcc")
                and not messages[0].get("scheduled")
                and body_text(messages[0].get("body", ""))
                == row["selected_body_text"].replace("\r\n", "\n").replace("\r", "\n")
                and body_links(messages[0].get("body", ""))
                == body_links(rendered_body(row["selected_body_text"]))
            )
            result["web_link"] = safe_web_link(
                value.get("_links", {}).get("web", {}).get("href"), identifier
            ) or result.get("web_link")
            if verified:
                result.update(state="CREATED", code="DRAFT_CREATED_VERIFIED")
        except (OSError, ValueError, TypeError, AttributeError, http.client.HTTPException):
            pass
        return result


def body_text(body):
    class Plain(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts = []

        def handle_data(self, data):
            self.parts.append(data)

        def handle_starttag(self, tag, attrs):
            if tag.lower() == "br":
                self.parts.append("\n")

    parser = Plain()
    parser.feed(body)
    return "".join(parser.parts)


def body_links(body):
    """Visible copy alone cannot prove that the returned cart destinations match."""

    class Links(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.targets = []

        def handle_starttag(self, tag, attrs):
            if tag.lower() == "a":
                values = [value for name, value in attrs if name == "href"]
                self.targets.append(values)

    parser = Links()
    parser.feed(body)
    return parser.targets
