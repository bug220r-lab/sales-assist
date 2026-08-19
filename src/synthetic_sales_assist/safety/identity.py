"""Fail-closed validation for executable synthetic identities.

The validators in this module are deliberately lexical.  They do not look up, infer,
or transform identities, and their exceptions never echo rejected input.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


RESERVED_IDENTITY_NAMESPACES = (
    "CUSTOMER",
    "ORDER",
    "SKU",
    "INTERACTION",
    "CONVERSATION",
    "SNAPSHOT",
    "EVALUATION",
    "RUN",
    "REP",
    "EVIDENCE",
)
SYNTHETIC_EMAIL_DOMAIN = "example.test"

_NAMESPACE_ALTERNATION = "|".join(RESERVED_IDENTITY_NAMESPACES)
_RESERVED_IDENTITY_PATTERN = re.compile(
    rf"\ASYN-(?P<namespace>{_NAMESPACE_ALTERNATION})-"
    r"(?P<suffix>[A-Z0-9]+(?:-[A-Z0-9]+)*)\Z",
    re.ASCII,
)
_GENERIC_SYNTHETIC_IDENTITY_PATTERN = re.compile(
    r"\ASYN-(?P<namespace>[A-Z0-9]+)-(?P<suffix>.*)\Z",
    re.ASCII,
)
_SYNTHETIC_EMAIL_PATTERN = re.compile(
    r"\A(?=.{3,254}\Z)[a-z0-9](?:[a-z0-9._+-]{0,62}[a-z0-9])?@example\.test\Z",
    re.ASCII,
)
_FICTIONAL_PHONE_PATTERNS = (
    re.compile(r"\A555-(?P<subscriber>01\d{2})\Z", re.ASCII),
    re.compile(r"\A(?P<area>[2-9]\d{2})-555-(?P<subscriber>01\d{2})\Z", re.ASCII),
    re.compile(r"\A\((?P<area>[2-9]\d{2})\) 555-(?P<subscriber>01\d{2})\Z", re.ASCII),
    re.compile(r"\A\+1 (?P<area>[2-9]\d{2}) 555 (?P<subscriber>01\d{2})\Z", re.ASCII),
)


class IdentityFirewallError(ValueError):
    """Raised when executable identity material is not explicitly synthetic.

    ``code`` is intentionally drawn from a closed set and the rejected value is not
    retained in either the exception attributes or its message.
    """

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"synthetic identity rejected: {code}")


@dataclass(frozen=True, slots=True)
class ReservedIdentity:
    """A syntactically validated reserved identity."""

    value: str
    namespace: str


def _normalize_expected_namespace(expected_namespace: str | None) -> str | None:
    if expected_namespace is None:
        return None
    if not isinstance(expected_namespace, str):
        raise ValueError("expected namespace must be a string")
    normalized = expected_namespace.removeprefix("SYN-").removesuffix("-")
    if normalized not in RESERVED_IDENTITY_NAMESPACES:
        raise ValueError("expected namespace is not reserved")
    return normalized


def parse_reserved_identity(
    value: object,
    *,
    expected_namespace: str | None = None,
) -> ReservedIdentity:
    """Validate and return one identity from the closed reserved namespaces.

    Values are canonical ASCII with no trimming or case normalization.  The suffix
    consists of nonempty uppercase-alphanumeric segments separated by one hyphen.
    """

    expected = _normalize_expected_namespace(expected_namespace)
    if not isinstance(value, str):
        raise IdentityFirewallError("identity_type")
    if not value or len(value) > 128 or not value.isascii():
        raise IdentityFirewallError("identity_format")

    match = _RESERVED_IDENTITY_PATTERN.fullmatch(value)
    if match is None:
        generic_match = _GENERIC_SYNTHETIC_IDENTITY_PATTERN.fullmatch(value)
        if (
            generic_match is not None
            and generic_match.group("namespace") not in RESERVED_IDENTITY_NAMESPACES
        ):
            raise IdentityFirewallError("identity_namespace")
        raise IdentityFirewallError("identity_format")

    namespace = match.group("namespace")
    if expected is not None and namespace != expected:
        raise IdentityFirewallError("identity_namespace_mismatch")
    return ReservedIdentity(value=value, namespace=namespace)


def assert_reserved_identity(
    value: object,
    *,
    expected_namespace: str | None = None,
) -> str:
    """Return ``value`` only after reserved-identity validation succeeds."""

    return parse_reserved_identity(value, expected_namespace=expected_namespace).value


def is_reserved_identity(value: object, *, expected_namespace: str | None = None) -> bool:
    """Return whether ``value`` is a canonical identity in the expected namespace."""

    try:
        parse_reserved_identity(value, expected_namespace=expected_namespace)
    except (IdentityFirewallError, ValueError):
        return False
    return True


def assert_synthetic_email(value: object) -> str:
    """Require a canonical mailbox whose domain is exactly ``example.test``."""

    if not isinstance(value, str) or _SYNTHETIC_EMAIL_PATTERN.fullmatch(value) is None:
        raise IdentityFirewallError("email_not_exact_example_test")
    local_part = value.partition("@")[0]
    if ".." in local_part:
        raise IdentityFirewallError("email_format")
    return value


def is_synthetic_email(value: object) -> bool:
    """Return whether ``value`` is a canonical ``example.test`` email address."""

    try:
        assert_synthetic_email(value)
    except IdentityFirewallError:
        return False
    return True


def _fictional_phone_digits(value: object) -> str:
    if not isinstance(value, str):
        raise IdentityFirewallError("phone_type")
    if not value or len(value) > 32 or value != value.strip():
        raise IdentityFirewallError("phone_format")
    if not value.isascii():
        raise IdentityFirewallError("phone_format")
    if not any(pattern.fullmatch(value) for pattern in _FICTIONAL_PHONE_PATTERNS):
        raise IdentityFirewallError("phone_not_fictional_555")
    return "".join(character for character in value if character.isdigit())


def assert_fictional_555_phone(value: object) -> str:
    """Require the conservative fictional 555-0100 through 555-0199 range."""

    _fictional_phone_digits(value)
    assert isinstance(value, str)
    return value


def is_fictional_555_phone(value: object) -> bool:
    """Return whether ``value`` is in the conservative fictional 555 range."""

    try:
        _fictional_phone_digits(value)
    except IdentityFirewallError:
        return False
    return True


__all__ = [
    "IdentityFirewallError",
    "RESERVED_IDENTITY_NAMESPACES",
    "ReservedIdentity",
    "SYNTHETIC_EMAIL_DOMAIN",
    "assert_fictional_555_phone",
    "assert_reserved_identity",
    "assert_synthetic_email",
    "is_fictional_555_phone",
    "is_reserved_identity",
    "is_synthetic_email",
    "parse_reserved_identity",
]
