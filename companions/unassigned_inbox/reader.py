"""Read-only Help Scout transport and complete, scoped inbox acquisition.

No conversation mutation is supported. OAuth renewal is a separate, fixed
operation; renewed credentials remain in memory and never change existing tools.
"""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import ctypes
from ctypes import wintypes
import http.client
import json
import math
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request


API_ORIGIN = "https://api.helpscout.net"
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
UNASSIGNED_QUERY = '(assigned:"Unassigned")'


class ReaderError(RuntimeError):
    """A sanitized error that contains no server body, headers, or credentials."""


class AuthenticationError(ReaderError):
    pass


class IncompleteRead(ReaderError):
    pass


class ApiReadError(ReaderError):
    def __init__(self, status):
        self.status = status
        super().__init__(f"Help Scout read failed ({status}); no conversation change attempted")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def decrypt_dpapi(data):
    """Read an existing Windows DPAPI blob for the current user, without saving it."""
    if not isinstance(data, bytes) or not data:
        raise ValueError("An encrypted connection is required")
    source_buffer = ctypes.create_string_buffer(data)
    source = _DataBlob(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = _DataBlob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = crypt.CryptUnprotectData
    fn.argtypes = [ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob)]
    fn.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise AuthenticationError("Existing Help Scout connection could not be opened for this Windows account")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel.LocalFree(result.pbData)


def positive_id(value):
    """Reject coercions (especially booleans) before forming a request path."""
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value):
        return int(value)
    raise ValueError("A positive integer identifier is required")


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def unassigned_scope_issues(conversation, mailbox_id):
    """Validate active, unassigned scope without trusting the search filter.

    Help Scout can omit ``assignee`` or return null/{} for an unassigned
    conversation. These representations are accepted only when there is no
    conflicting assignee/team object, identifier, or assignment link. Every
    nonempty or malformed assignee is rejected, including team assignments.
    Historical timestamps such as ``assignedAt`` do not establish an owner.
    This checks current response metadata; it is not a frozen inbox snapshot.
    """
    mailbox_id = positive_id(mailbox_id)
    if not isinstance(conversation, dict):
        return ["Conversation is not an object"]
    issues = []
    if type(conversation.get("mailboxId")) is not int or conversation["mailboxId"] != mailbox_id:
        issues.append("Conversation mailbox does not match the selected mailbox")
    if conversation.get("status") != "active":
        issues.append("Conversation is not active")

    assignment_fields = {
        "assignee", "assigneeid", "assignedto", "assignedtoid", "assignment",
        "team", "teamid", "teams", "assignedteam", "assignedteamid",
        "assignedtoteam", "assignedtoteamid", "assigneduser", "assigneduserid",
    }

    def has_assignment(record, *, links=False):
        for key, value in record.items():
            normalized = re.sub(r"[^a-z]", "", str(key).lower())
            if normalized in assignment_fields:
                # An empty object/null is an absent relationship, but scalar
                # zero/False/empty strings and malformed lists are ambiguous.
                if value is not None and not (isinstance(value, dict) and not value):
                    return True
                # A named relationship link itself is suspicious even if its
                # payload is empty; omitted links are the normal absent shape.
                if links:
                    return True
        return False

    if has_assignment(conversation):
        issues.append("Conversation has assigned or ambiguous user/team metadata")
    for field in ("_links", "_embedded"):
        metadata = conversation.get(field)
        if metadata is None:
            continue
        if not isinstance(metadata, dict):
            issues.append(f"Conversation {field} metadata is malformed")
        elif has_assignment(metadata, links=(field == "_links")):
            issues.append("Conversation has an assignee/team relationship")
    return list(dict.fromkeys(issues))


def _response_json(response, expected_url):
    # A custom opener must not quietly return a redirected response either.
    if response.geturl() != expected_url:
        raise ReaderError("Unexpected response URL; redirect refused")
    raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ReaderError("Help Scout response exceeded the safe read limit")
    body = json.loads(raw)
    if not isinstance(body, dict):
        raise ReaderError("Help Scout returned an invalid object")
    return body


def _safe_exception_details(exc, http_status=None):
    """Diagnostics use exception types and numeric codes, never error text.

    ``URLError.reason`` can wrap an OSError. Reading its numeric codes exposes
    local network denial without disclosing proxy addresses or server bodies.
    """
    parts = [type(exc).__name__]
    if isinstance(exc, urllib.error.HTTPError):
        http_status = exc.code
    if type(http_status) is int:
        parts.append(f"http_status={http_status}")
    errors = [exc]
    if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, OSError):
        parts.append("reason=" + type(exc.reason).__name__)
        errors.append(exc.reason)
    for error in errors:
        if isinstance(error, OSError):
            for code in ("errno", "winerror"):
                value = getattr(error, code, None)
                if type(value) is int:
                    parts.append(f"{code}={value}")
    return "; ".join(parts)


class DPAPICredentials:
    """Decrypt an existing connection; renewal is memory-only."""

    def __init__(self, auth_path, *, opener=None, clock=time.time):
        self._clock = clock
        self._opener = opener or urllib.request.build_opener(NoRedirect)
        path = Path(auth_path)
        if not path.is_file():
            raise AuthenticationError("Existing approved Help Scout connection is unavailable")
        try:
            self._auth = json.loads(decrypt_dpapi(path.read_bytes()))
            if not isinstance(self._auth, dict):
                raise ValueError()
        except Exception:
            raise AuthenticationError("Existing Help Scout connection could not be opened for this Windows account") from None

    def __repr__(self):
        return "<DPAPICredentials redacted>"

    def token(self, force_refresh=False):
        try:
            expires = float(self._auth.get("expires_at", 0))
            if not math.isfinite(expires):
                raise ValueError()
            token = self._auth.get("access_token")
            if force_refresh or not isinstance(token, str) or not token or self._clock() >= expires - 120:
                self._renew()
            token = self._auth["access_token"]
            if not isinstance(token, str) or not token or any(c in token for c in "\r\n"):
                raise ValueError()
            return token
        except AuthenticationError:
            raise
        except Exception:
            raise AuthenticationError("Help Scout authentication data is unavailable or invalid") from None

    def _renew(self):
        # This is intentionally independent of the read transport's allowlist.
        # No retry and no token-file write: other running workers are untouched.
        http_status = None
        try:
            client_id = self._auth["client_id"]
            client_secret = self._auth["client_secret"]
            if not all(isinstance(v, str) and v for v in (client_id, client_secret)):
                raise ValueError()
            data = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}).encode("ascii")
            url = API_ORIGIN + "/v2/oauth2/token"
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}, method="POST")
            with self._opener.open(req, timeout=30) as response:
                http_status = response.status
                if response.status != 200:
                    raise ValueError()
                body = _response_json(response, url)
            token, expires = body.get("access_token"), body.get("expires_in")
            if body.get("token_type", "").lower() != "bearer" or not isinstance(token, str) or not token or any(c in token for c in "\r\n"):
                raise ValueError()
            if type(expires) not in (int, float) or not math.isfinite(expires) or expires <= 120:
                raise ValueError()
            self._auth.update(access_token=token, expires_at=self._clock() + expires)
        except Exception as exc:
            details = _safe_exception_details(exc, http_status)
            raise AuthenticationError(f"Help Scout token renewal failed ({details}); authentication or connection needs local review") from None


def _validate_read_path(path):
    if not isinstance(path, str) or len(path) > 1000:
        raise ValueError("Blocked read endpoint")
    parsed = urllib.parse.urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.fragment or "%" in parsed.path or "\\" in path:
        raise ValueError("Blocked read endpoint")
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    if any(len(values) != 1 for values in query.values()):
        raise ValueError("Duplicate read parameters are not allowed")
    values = {key: value[0] for key, value in query.items()}
    if parsed.path == "/v2/users/me" or re.fullmatch(r"/v2/(?:users|mailboxes|conversations)/[1-9][0-9]*", parsed.path):
        if query:
            raise ValueError("Blocked read parameters")
        return
    if re.fullmatch(r"/v2/conversations/[1-9][0-9]*/threads", parsed.path):
        if set(values) != {"page"}:
            raise ValueError("A single page parameter is required")
        positive_id(values["page"])
        return
    if parsed.path == "/v2/conversations":
        unassigned_fields = {"mailbox", "query", "status", "sortField", "sortOrder", "page"}
        if set(values) != unassigned_fields:
            raise ValueError("An explicit mailbox and active Unassigned scope are required")
        for field in ("mailbox", "page"):
            positive_id(values[field])
        if values["query"] != UNASSIGNED_QUERY or values["status"] != "active":
            raise ValueError("Only the exact active Unassigned query is allowed")
        if values["sortField"] != "createdAt" or values["sortOrder"] != "asc":
            raise ValueError("Blocked conversation-list parameters")
        return
    raise ValueError("Blocked read endpoint")


class ReadOnlyTransport:
    """Only allowlisted GETs, with bounded retries on safely repeatable reads."""

    def __init__(self, credentials, *, opener=None, sleeper=time.sleep, clock=time.time, max_attempts=4, max_wait_seconds=60):
        if type(max_attempts) is not int or not 1 <= max_attempts <= 6:
            raise ValueError("Read attempt limit must be from one to six")
        if not 0 <= max_wait_seconds <= 60:
            raise ValueError("Read wait budget must be at most sixty seconds")
        self.credentials = credentials
        self._opener = opener or urllib.request.build_opener(NoRedirect)
        self._sleeper, self._clock = sleeper, clock
        self.max_attempts, self.max_wait_seconds = max_attempts, max_wait_seconds
        self._not_before = 0.0

    def _retry_after(self, headers, default):
        lower = {str(k).lower(): str(v) for k, v in headers.items()}
        delays = []
        for key in ("x-ratelimit-retry-after", "retry-after"):
            value = lower.get(key)
            if value is None:
                continue
            try:
                seconds = float(value)
            except ValueError:
                try:
                    seconds = parsedate_to_datetime(value).timestamp() - self._clock()
                except (ValueError, TypeError, OverflowError):
                    continue
            if math.isfinite(seconds):
                delays.append(max(0.0, seconds))
        return max(delays) if delays else float(default)

    def request(self, method, path, payload=None):
        if method != "GET" or payload is not None:
            raise ValueError("Read-only transport accepts only GET without a payload")
        _validate_read_path(path)
        url = API_ORIGIN + path
        refreshed, waited = False, 0.0
        for attempt in range(self.max_attempts):
            delay = max(0.0, self._not_before - self._clock())
            if delay:
                if waited + delay > self.max_wait_seconds:
                    raise ApiReadError("rate_limit_wait_exceeds_budget")
                self._sleeper(delay)
                waited += delay
            bearer = self.credentials.token()
            req = urllib.request.Request(url, headers={"Authorization": "Bearer " + bearer, "Accept": "application/json"}, method="GET")
            try:
                with self._opener.open(req, timeout=35) as response:
                    if response.status != 200:
                        raise ApiReadError(response.status)
                    headers = dict(response.headers)
                    body = _response_json(response, url)
                lower = {str(k).lower(): str(v) for k, v in headers.items()}
                if lower.get("x-ratelimit-remaining-minute") == "0":
                    self._not_before = self._clock() + self._retry_after(headers, 60)
                return {"status": 200, "headers": headers, "body": body}
            except urllib.error.HTTPError as exc:
                status, headers = exc.code, dict(exc.headers or {})
                exc.close()
                if status == 401:
                    if refreshed or attempt == self.max_attempts - 1:
                        raise AuthenticationError("Help Scout rejected authentication; live reads stopped") from None
                    self.credentials.token(force_refresh=True)
                    refreshed = True
                    continue
                if status not in {429, 500, 502, 503, 504} or attempt == self.max_attempts - 1:
                    raise ApiReadError(status) from None
                delay = self._retry_after(headers, 2 ** attempt)
            except (OSError, TimeoutError, http.client.HTTPException):
                if attempt == self.max_attempts - 1:
                    raise ApiReadError("network_error") from None
                delay = float(2 ** attempt)
            except (ValueError, UnicodeError):
                raise ApiReadError("invalid_response") from None
            self._not_before = self._clock() + delay
        raise ApiReadError("attempt_limit")


class Reader:
    def __init__(self, transport, *, max_pages=1000):
        if type(max_pages) is not int or not 1 <= max_pages <= 1000:
            raise ValueError("Page safety limit must be between one and one thousand")
        self.transport, self.max_pages = transport, max_pages
        self.last_thread_coverage = None

    def _get(self, path):
        result = self.transport.request("GET", path)
        if result.get("status") != 200 or not isinstance(result.get("body"), dict):
            raise IncompleteRead("Help Scout read did not return a complete object")
        return result["body"]

    def _object(self, path, expected_id=None):
        body = self._get(path)
        try:
            found_id = positive_id(body.get("id"))
        except ValueError:
            raise IncompleteRead("Help Scout object has no valid identifier") from None
        if expected_id is not None and found_id != expected_id:
            raise IncompleteRead("Help Scout returned a different object identifier")
        return body

    def get_identity(self):
        # Returns the live resource owner; caller must verify intended author
        # against configured name/email and a live user record, never ID alone.
        return self._object("/v2/users/me")

    def get_user(self, uid):
        uid = positive_id(uid)
        return self._object(f"/v2/users/{uid}", uid)

    def get_mailbox(self, mid):
        mid = positive_id(mid)
        return self._object(f"/v2/mailboxes/{mid}", mid)

    def get_conversation(self, cid):
        cid = positive_id(cid)
        return self._object(f"/v2/conversations/{cid}", cid)

    def _collection(self, path, key, *, tolerant=False):
        started, rows, seen, issues, page_reads = utc_now(), [], set(), [], []
        expected = None
        highest_pages = 1
        for number in range(1, self.max_pages + 1):
            separator = "&" if "?" in path else "?"
            body = self._get(f"{path}{separator}page={number}")
            page = body.get("page")
            embedded = body.get("_embedded", {})
            if not isinstance(page, dict) or not isinstance(embedded, dict):
                raise IncompleteRead("Missing pagination or embedded collection")
            total, pages, returned = page.get("totalElements"), page.get("totalPages"), page.get("number")
            batch = embedded.get(key, [] if total == 0 else None)
            valid_empty = total == 0 and pages == 0 and number == 1 and returned in {0, 1}
            if (type(total) is not int or total < 0 or type(pages) is not int or not 0 <= pages <= self.max_pages
                    or type(returned) is not int or (returned != number and not valid_empty)
                    or not isinstance(batch, list) or (pages == 0 and not valid_empty) or (total > 0 and not batch)):
                raise IncompleteRead("Invalid or incomplete collection pagination")
            if expected is None:
                expected = (total, pages)
            elif expected != (total, pages):
                issues.append("Collection totals changed during acquisition")
                if not tolerant:
                    raise IncompleteRead(issues[-1])
            highest_pages = max(highest_pages, pages)
            page_reads.append({"page": number, "acquired_at_utc": utc_now(), "row_count": len(batch), "total_elements": total, "total_pages": pages})
            for item in batch:
                if not isinstance(item, dict):
                    raise IncompleteRead("Invalid collection item")
                try:
                    item_id = positive_id(item.get("id"))
                except ValueError:
                    raise IncompleteRead("Collection item has no valid identifier") from None
                if item_id in seen:
                    issues.append("Duplicate identifier encountered across pages")
                    if not tolerant:
                        raise IncompleteRead(issues[-1])
                    continue
                seen.add(item_id)
                rows.append(item)
            if number >= highest_pages:
                if len(rows) != total or (expected and len(rows) != expected[0]):
                    issues.append("Unique item count differs from reported collection count")
                    if not tolerant:
                        raise IncompleteRead(issues[-1])
                coverage = {"started_at_utc": started, "finished_at_utc": utc_now(), "complete": not issues,
                            "unique_count": len(rows), "ids": [positive_id(row["id"]) for row in rows],
                            "pages_read": page_reads, "limitations": list(dict.fromkeys(issues)),
                            "snapshot_semantics": "Observed across paginated reads; not a frozen server snapshot"}
                return rows, coverage
        raise IncompleteRead("Collection exceeds the page safety limit")

    def list_unassigned_conversations(self, mailbox_id):
        """Read every page of one mailbox's active Unassigned search.

        All observed IDs are retained for accounting. Out-of-scope rows make
        coverage incomplete and must not be treated as Unassigned candidates.
        """
        mailbox_id = positive_id(mailbox_id)
        query = urllib.parse.urlencode({"mailbox": mailbox_id, "query": UNASSIGNED_QUERY,
                                       "status": "active", "sortField": "createdAt", "sortOrder": "asc"})
        rows, coverage = self._collection("/v2/conversations?" + query, "conversations", tolerant=True)
        mismatches = {str(row["id"]): issues for row in rows
                      if (issues := unassigned_scope_issues(row, mailbox_id))}
        if mismatches:
            coverage["complete"] = False
            coverage["out_of_scope_ids"] = [row["id"] for row in rows if str(row["id"]) in mismatches]
            coverage["scope_issues"] = mismatches
            coverage["limitations"].append("Some listed records did not match the active Unassigned mailbox scope")
        coverage.update(mailbox_id=mailbox_id, assignment="unassigned", status="active", query=UNASSIGNED_QUERY)
        return rows, coverage

    def get_threads(self, cid):
        cid = positive_id(cid)
        rows, coverage = self._collection(f"/v2/conversations/{cid}/threads", "threads")
        def chronology(item):
            try:
                stamp = item.get("createdAt")
                parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError()
                return (parsed.timestamp(), positive_id(item["id"]))
            except (ValueError, TypeError, AttributeError, OverflowError):
                raise IncompleteRead("Thread chronology is missing or invalid") from None
        rows.sort(key=chronology)
        self.last_thread_coverage = coverage
        return rows

    def get_context(self, cid):
        cid = positive_id(cid)
        before = self.get_conversation(cid)
        threads = self.get_threads(cid)
        after = self.get_conversation(cid)
        if before != after:
            raise IncompleteRead("Conversation changed while full context was being read")
        return {"conversation": after, "threads": threads, "complete": True,
                "checked_at_utc": utc_now(), "thread_coverage": self.last_thread_coverage}


def create_reader(auth_path, **transport_options):
    return Reader(ReadOnlyTransport(DPAPICredentials(auth_path), **transport_options))
