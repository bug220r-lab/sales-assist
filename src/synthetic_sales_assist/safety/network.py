"""Pure validation for the localhost-only runtime boundary.

The functions in this module perform no DNS lookup and open no socket.  A destination
is accepted only when the URL contains one of the three spellings explicitly reserved
by the synthetic-data policy.  Avoiding address resolution is intentional: permissive
ideas such as "anything that resolves to loopback" admit aliases and DNS-rebinding
surfaces that are outside the closed policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit


ALLOWED_RUNTIME_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
ALLOWED_RUNTIME_URL_SCHEMES = frozenset({"http", "https"})


class NetworkPolicyViolation(ValueError):
    """Raised when a proposed runtime destination crosses the safety boundary."""


@dataclass(frozen=True, slots=True)
class RuntimeDestination:
    """Validated, normalized components of a local HTTP(S) destination."""

    url: str
    scheme: str
    host: str
    port: int | None


def _require_clean_text(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise NetworkPolicyViolation(f"{field} must be a string")
    if not value:
        raise NetworkPolicyViolation(f"{field} must not be empty")
    if value != value.strip():
        raise NetworkPolicyViolation(f"{field} must not have surrounding whitespace")
    if any(ord(character) <= 0x20 or ord(character) == 0x7F for character in value):
        raise NetworkPolicyViolation(f"{field} must not contain whitespace or controls")
    return value


def validate_runtime_host(host: object) -> str:
    """Return the canonical spelling of an explicitly allowed runtime host.

    DNS names are case-insensitive, so ASCII case variants of ``localhost`` normalize
    to the one canonical value.  Every other alias, numeric shorthand, address range,
    suffix, trailing dot, bracketed value, port, zone ID, and wildcard is rejected.
    Brackets belong only to the URL authority syntax and are handled by
    :func:`validate_runtime_url`.
    """

    candidate = _require_clean_text(host, field="runtime host")
    normalized = candidate.casefold() if candidate.isascii() else candidate
    if normalized not in ALLOWED_RUNTIME_HOSTS:
        raise NetworkPolicyViolation(
            "runtime host must be exactly 127.0.0.1, localhost, or ::1"
        )
    return normalized


def is_runtime_host_allowed(host: object) -> bool:
    """Return ``True`` only for a host accepted by :func:`validate_runtime_host`."""

    try:
        validate_runtime_host(host)
    except NetworkPolicyViolation:
        return False
    return True


def _validate_port_syntax(authority: str, host: str, parsed: SplitResult) -> int | None:
    try:
        port = parsed.port
    except ValueError as exc:
        raise NetworkPolicyViolation("runtime URL has an invalid port") from exc

    if host == "::1":
        if not authority.startswith("[") or "]" not in authority:
            raise NetworkPolicyViolation("IPv6 loopback must use bracketed URL syntax")
        suffix = authority[authority.index("]") + 1 :]
        if suffix:
            if not suffix.startswith(":") or not suffix[1:].isascii() or not suffix[1:].isdigit():
                raise NetworkPolicyViolation("runtime URL has a non-decimal or empty port")
    else:
        if "[" in authority or "]" in authority:
            raise NetworkPolicyViolation("brackets are permitted only around ::1")
        if ":" in authority:
            port_text = authority.rsplit(":", maxsplit=1)[1]
            if not port_text.isascii() or not port_text.isdigit():
                raise NetworkPolicyViolation("runtime URL has a non-decimal or empty port")

    if port is not None and not 1 <= port <= 65535:
        raise NetworkPolicyViolation("runtime URL port must be between 1 and 65535")
    return port


def validate_runtime_url(url: object) -> RuntimeDestination:
    """Validate an HTTP(S) URL without resolving or contacting its host.

    User information, percent-encoded authorities, wildcards, backslashes, malformed
    ports, and non-canonical loopback aliases are rejected before the normalized
    destination is returned.
    """

    candidate = _require_clean_text(url, field="runtime URL")
    if "\\" in candidate:
        raise NetworkPolicyViolation("runtime URL must not contain a backslash")

    try:
        parsed = urlsplit(candidate)
    except (TypeError, ValueError) as exc:
        raise NetworkPolicyViolation("runtime URL is malformed") from exc

    if parsed.scheme not in ALLOWED_RUNTIME_URL_SCHEMES:
        raise NetworkPolicyViolation("runtime URL scheme must be http or https")
    if not parsed.netloc:
        raise NetworkPolicyViolation("runtime URL must contain an authority")
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        raise NetworkPolicyViolation("runtime URL must not contain user information")
    if "%" in parsed.netloc:
        raise NetworkPolicyViolation("runtime URL authority must not be percent encoded")
    if "*" in parsed.netloc:
        raise NetworkPolicyViolation("runtime URL authority must not contain a wildcard")

    try:
        parsed_host = parsed.hostname
    except ValueError as exc:
        raise NetworkPolicyViolation("runtime URL has an invalid host") from exc
    if parsed_host is None:
        raise NetworkPolicyViolation("runtime URL must contain a host")

    host = validate_runtime_host(parsed_host)
    port = _validate_port_syntax(parsed.netloc, host, parsed)
    return RuntimeDestination(
        url=candidate,
        scheme=parsed.scheme,
        host=host,
        port=port,
    )


def is_runtime_url_allowed(url: object) -> bool:
    """Return ``True`` only for a URL accepted by :func:`validate_runtime_url`."""

    try:
        validate_runtime_url(url)
    except NetworkPolicyViolation:
        return False
    return True


# Readable aliases for callers that prefer an imperative policy name.
require_loopback_host = validate_runtime_host
require_loopback_url = validate_runtime_url


__all__ = [
    "ALLOWED_RUNTIME_HOSTS",
    "ALLOWED_RUNTIME_URL_SCHEMES",
    "NetworkPolicyViolation",
    "RuntimeDestination",
    "is_runtime_host_allowed",
    "is_runtime_url_allowed",
    "require_loopback_host",
    "require_loopback_url",
    "validate_runtime_host",
    "validate_runtime_url",
]
