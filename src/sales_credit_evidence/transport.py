"""Bounded GET-only transport for one explicitly scoped Help Scout evidence read.

This module never loads credentials, reads environment variables, renews tokens, or
follows redirects. Injected transports are for controlled offline tests. Network
access requires both ``enable_live=True`` and a caller-supplied, expiring credential.
"""

from __future__ import annotations

import http.client
import json
import re
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qsl, urlsplit

API_ORIGIN = "https://api.helpscout.net"
MAILBOX_ID = 166170
TARGET_AUTHOR_ID = 897275
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_PAGE = 10_000
MAX_RETRY_WAIT_SECONDS = 5.0
MAX_RETRY_TOTAL_SECONDS = 10.0
HTTP_TIMEOUT_SECONDS = 15.0


class ReadError(Exception):
    """Safe diagnostic: never includes URL, request headers, body, or token."""

    def __init__(
        self,
        code: str,
        status: int | None = None,
        attempts: int = 0,
        retry_after: float | None = None,
    ) -> None:
        self.code = code
        self.status = status
        self.attempts = attempts
        self.retry_after = retry_after
        super().__init__(code)

    def __repr__(self) -> str:
        return (
            f"ReadError(code={self.code!r}, status={self.status!r}, "
            f"attempts={self.attempts!r}, retry_after={self.retry_after!r})"
        )


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str] = field(repr=False)
    body: bytes = field(repr=False)


@dataclass(frozen=True)
class SuppliedCredential:
    """An already-authorized in-memory token, with no renewal or storage hook."""

    token: str = field(repr=False)
    expires_at: datetime

    def __post_init__(self) -> None:
        if (
            not isinstance(self.token, str)
            or not 1 <= len(self.token) <= 8192
            or any(ord(char) < 33 or ord(char) > 126 for char in self.token)
        ):
            raise ReadError("invalid_credential")
        if not _aware_datetime(self.expires_at):
            raise ReadError("invalid_credential_expiry")


Transport = Callable[[str, str, dict[str, str]], HttpResponse]


def _aware_datetime(value: Any) -> bool:
    return (
        isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None
    )


def normalize_email(value: str) -> str:
    """Conservative address normalization, without wildcard/query operators.

    This intentionally rejects quoted local parts and non-ASCII addresses rather
    than guessing how the remote search parser will interpret them.
    """
    if not isinstance(value, str):
        raise ReadError("invalid_email")
    trimmed = value.strip()
    if not trimmed.isascii():
        raise ReadError("invalid_email")
    normalized = trimmed.casefold()
    if len(normalized) > 254 or normalized.count("@") != 1:
        raise ReadError("invalid_email")
    local, domain = normalized.split("@")
    if (
        not 1 <= len(local) <= 64
        or re.fullmatch(r"[a-z0-9.!#$%&'+/=^_`{|}~-]+", local) is None
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
        or len(domain) > 253
        or "." not in domain
    ):
        raise ReadError("invalid_email")
    labels = domain.split(".")
    if any(
        not 1 <= len(label) <= 63 or re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label) is None
        for label in labels
    ):
        raise ReadError("invalid_email")
    return normalized


def _positive_id(value: int) -> int:
    if type(value) is not int or not 1 <= value <= 2**63 - 1:
        raise ReadError("invalid_native_id")
    return value


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


def _invalid_constant(_value: str) -> None:
    raise ValueError("invalid_constant")


class ReadClient:
    """One exact email, fixed inbox, and only source-discovered native IDs.

    ``allow_customer`` and ``allow_conversation`` must be called only after the
    evidence reader validates identities and inbox membership. There is no public
    request method accepting an HTTP verb, body, or arbitrary authorization header.
    """

    def __init__(
        self,
        email: str,
        *,
        transport: Transport | None = None,
        credential: SuppliedCredential | None = None,
        enable_live: bool = False,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleeper: Callable[[float], None] = time.sleep,
        max_attempts: int = 3,
        expiry_margin_seconds: int = 0,
    ) -> None:
        self._email = normalize_email(email)
        if type(max_attempts) is not int or not 1 <= max_attempts <= 3:
            raise ReadError("invalid_retry_limit")
        if type(enable_live) is not bool:
            raise ReadError("invalid_live_activation")
        if type(expiry_margin_seconds) is not int or not 0 <= expiry_margin_seconds <= 120:
            raise ReadError("invalid_expiry_margin")
        if credential is not None and not isinstance(credential, SuppliedCredential):
            raise ReadError("invalid_credential")
        self._credential = credential
        self._transport = (
            transport if transport is not None else (self._https_get if enable_live else None)
        )
        self._uses_live_transport = transport is None and enable_live
        self._clock = clock
        self._sleeper = sleeper
        self._max_attempts = max_attempts
        self._expiry_margin_seconds = expiry_margin_seconds
        self._customer_ids: set[int] = set()
        self._conversation_ids: set[int] = set()

    @property
    def email(self) -> str:
        """The immutable exact email scope for this client's native-ID grants."""
        return self._email

    def allow_customer(self, customer_id: int) -> None:
        self._customer_ids.add(_positive_id(customer_id))

    def allow_conversation(self, conversation_id: int) -> None:
        self._conversation_ids.add(_positive_id(conversation_id))

    def validate_url(self, url: str) -> None:
        """Validate before transport; reject endpoint and query scope changes."""
        if (
            not isinstance(url, str)
            or len(url) > 4096
            or any(ord(char) <= 32 or ord(char) > 126 for char in url)
            or "\\" in url
            or "#" in url
            or re.search(r"%(?![0-9A-Fa-f]{2})", url)
        ):
            raise ReadError("unsafe_url")
        try:
            parsed = urlsplit(url)
            if parsed.scheme != "https" or parsed.netloc != "api.helpscout.net":
                raise ValueError("origin")
            if "%" in parsed.path or "//" in parsed.path:
                raise ValueError("path")
            pairs = parse_qsl(
                parsed.query,
                keep_blank_values=True,
                strict_parsing=True,
                encoding="utf-8",
                errors="strict",
                max_num_fields=4,
            )
            query = dict(pairs)
            if len(query) != len(pairs):
                raise ValueError("duplicates")
            page = query.pop("page", None)
            if page is not None and (
                re.fullmatch(r"[1-9][0-9]{0,4}", page) is None or int(page) > MAX_PAGE
            ):
                raise ValueError("page")
            if parsed.path == "/v2/customers":
                allowed = query == {"mailbox": str(MAILBOX_ID), "query": f'(email:"{self.email}")'}
            elif parsed.path == "/v2/conversations":
                allowed = any(
                    query
                    == {
                        "mailbox": str(MAILBOX_ID),
                        "status": "all",
                        "query": f"(customerIds:{customer_id})",
                    }
                    for customer_id in self._customer_ids
                )
            elif match := re.fullmatch(r"/v2/customers/([1-9][0-9]*)/emails", parsed.path):
                allowed = "?" not in url and int(match[1]) in self._customer_ids
            elif match := re.fullmatch(r"/v2/conversations/([1-9][0-9]*)(/threads)?", parsed.path):
                allowed = (
                    not query
                    and int(match[1]) in self._conversation_ids
                    and (bool(match[2]) or (page is None and not parsed.query))
                )
            else:
                allowed = False
            if not allowed:
                raise ValueError("scope")
        except (ValueError, UnicodeError):
            raise ReadError("unsafe_url") from None

    def _headers(self, attempt: int) -> dict[str, str]:
        headers = {"Accept": "application/hal+json, application/json"}
        if self._uses_live_transport and self._credential is None:
            raise ReadError("credential_required", attempts=attempt - 1)
        if self._credential is not None:
            now = self._clock()
            if not _aware_datetime(now):
                raise ReadError("invalid_clock", attempts=attempt - 1)
            if (self._credential.expires_at - now).total_seconds() <= self._expiry_margin_seconds:
                raise ReadError("stale_credential", attempts=attempt - 1)
            headers["Authorization"] = f"Bearer {self._credential.token}"
        return headers

    @staticmethod
    def _https_get(method: str, url: str, headers: dict[str, str]) -> HttpResponse:
        # get() has already validated origin/path. Fixed host prevents a second
        # parser from interpreting a supplied netloc differently.
        if method != "GET":
            raise ReadError("method_not_allowed")
        parsed = urlsplit(url)
        target = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        connection = http.client.HTTPSConnection(
            "api.helpscout.net", timeout=HTTP_TIMEOUT_SECONDS, context=ssl.create_default_context()
        )
        try:
            connection.request("GET", target, headers=headers)
            response = connection.getresponse()
            # Read one byte beyond the bound to distinguish truncation.
            body = response.read(MAX_BODY_BYTES + 1)
            return HttpResponse(response.status, dict(response.getheaders()), body)
        finally:
            connection.close()

    def _retry_delay(self, response: HttpResponse, attempt: int) -> float | None:
        values: list[float] = []
        for key, raw in response.headers.items():
            if key.casefold() not in {"x-ratelimit-retry-after", "retry-after"}:
                continue
            try:
                value = float(raw)
                if not 0 <= value <= 365 * 24 * 60 * 60:
                    return None
            except (ValueError, TypeError):
                if key.casefold() != "retry-after":
                    return None
                try:
                    deadline = parsedate_to_datetime(raw)
                    now = self._clock()
                    if not _aware_datetime(deadline) or not _aware_datetime(now):
                        return None
                    value = max(0.0, (deadline - now).total_seconds())
                except (ValueError, TypeError, OverflowError):
                    return None
            values.append(value)
        return max(values) if values else float(attempt)

    def get(self, url: str) -> dict[str, Any]:
        self.validate_url(url)
        if self._transport is None:
            raise ReadError("live_access_disabled")
        waited = 0.0
        for attempt in range(1, self._max_attempts + 1):
            headers = self._headers(attempt)
            try:
                response = self._transport("GET", url, headers)
            except Exception:
                # Never expose arbitrary transport exception strings or chains.
                if attempt == self._max_attempts:
                    raise ReadError("network_error", attempts=attempt) from None
                self._sleeper(float(attempt))
                waited += attempt
                continue
            if (
                not isinstance(response, HttpResponse)
                or type(response.status) is not int
                or not 100 <= response.status <= 599
                or not isinstance(response.body, bytes)
                or not isinstance(response.headers, dict)
                or any(
                    not isinstance(k, str) or not isinstance(v, str)
                    for k, v in response.headers.items()
                )
            ):
                raise ReadError("invalid_response", attempts=attempt)
            status = response.status
            if len(response.body) > MAX_BODY_BYTES:
                raise ReadError("response_too_large", status=status, attempts=attempt)
            if status in {401, 403}:
                code = "unauthorized" if status == 401 else "forbidden"
                raise ReadError(code, status=status, attempts=attempt)
            if 300 <= status < 400:
                raise ReadError("redirect_not_followed", status=status, attempts=attempt)
            if status == 429 or 500 <= status <= 599:
                delay = self._retry_delay(response, attempt)
                code = "rate_limited" if status == 429 else "server_error"
                if (
                    attempt == self._max_attempts
                    or delay is None
                    or delay > MAX_RETRY_WAIT_SECONDS
                    or waited + delay > MAX_RETRY_TOTAL_SECONDS
                ):
                    raise ReadError(code, status=status, attempts=attempt, retry_after=delay)
                self._sleeper(delay)
                waited += delay
                continue
            if status != 200:
                raise ReadError("http_error", status=status, attempts=attempt)
            try:
                data = json.loads(
                    response.body.decode("utf-8"),
                    object_pairs_hook=_json_object,
                    parse_constant=_invalid_constant,
                )
                if not isinstance(data, dict):
                    raise ValueError("object_required")
            except (ValueError, UnicodeError, RecursionError):
                raise ReadError("invalid_json", status=status, attempts=attempt) from None
            return data
        raise AssertionError("bounded retry loop exhausted")
