"""Recursive, non-leaking prohibited-input validation.

The scanner accepts JSON-like values and fails closed for opaque or cyclic objects.  A
scalar produces at most one finding: when several signatures overlap, the first member
of :data:`VALIDATION_PRECEDENCE` wins.  Findings contain only a closed category and a
structural path made from numeric positions; neither values nor mapping keys are copied.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from synthetic_sales_assist.safety.identity import (
    is_fictional_555_phone,
    is_reserved_identity,
    is_synthetic_email,
)


class ProhibitedCategory:
    """Closed prohibited-input categories used by :class:`ProhibitedFinding`."""

    CREDENTIAL = "credential_material"
    COOKIE = "cookie_material"
    TOKEN = "token_material"
    SESSION = "session_material"
    BROWSER_STORAGE = "browser_storage"
    SCREENSHOT = "screenshot_or_image"
    HTML_DUMP = "html_dump"
    PRODUCTION_LOG = "production_log"
    PRODUCTION_SELECTOR = "production_selector"
    CLOUD_DOCUMENT_ID = "cloud_document_id"
    NON_SYNTHETIC_EMAIL = "non_synthetic_email"
    NON_FICTIONAL_PHONE = "non_fictional_phone"
    VIN = "vin"
    REAL_LOOKING_ADDRESS = "real_looking_address"
    REAL_LOOKING_CUSTOMER_NAME = "real_looking_customer_name"
    UNWRAPPED_NUMERIC_ORDER_ID = "unwrapped_numeric_order_id"
    REAL_PRODUCT_OR_MANUFACTURER_ID = "real_product_or_manufacturer_identifier"
    NON_SYNTHETIC_IDENTITY = "non_synthetic_identity"
    COPIED_NOTES = "copied_notes"
    INTERNAL_HOSTNAME = "internal_hostname"
    COMPANY_DOMAIN = "company_domain"
    OPAQUE_BINARY = "opaque_binary_input"
    CYCLIC_INPUT = "cyclic_input"
    UNSUPPORTED_INPUT = "unsupported_input_type"


# Field-specific secret/artifact categories precede patterns that the same value may
# incidentally resemble.  More specific business-safety categories precede the generic
# non-synthetic-identity fallback.
VALIDATION_PRECEDENCE = (
    ProhibitedCategory.CREDENTIAL,
    ProhibitedCategory.COOKIE,
    ProhibitedCategory.TOKEN,
    ProhibitedCategory.SESSION,
    ProhibitedCategory.BROWSER_STORAGE,
    ProhibitedCategory.SCREENSHOT,
    ProhibitedCategory.HTML_DUMP,
    ProhibitedCategory.PRODUCTION_LOG,
    ProhibitedCategory.PRODUCTION_SELECTOR,
    ProhibitedCategory.CLOUD_DOCUMENT_ID,
    ProhibitedCategory.NON_SYNTHETIC_EMAIL,
    ProhibitedCategory.NON_FICTIONAL_PHONE,
    ProhibitedCategory.VIN,
    ProhibitedCategory.REAL_LOOKING_ADDRESS,
    ProhibitedCategory.REAL_LOOKING_CUSTOMER_NAME,
    ProhibitedCategory.UNWRAPPED_NUMERIC_ORDER_ID,
    ProhibitedCategory.REAL_PRODUCT_OR_MANUFACTURER_ID,
    ProhibitedCategory.NON_SYNTHETIC_IDENTITY,
    ProhibitedCategory.COPIED_NOTES,
    ProhibitedCategory.INTERNAL_HOSTNAME,
    ProhibitedCategory.COMPANY_DOMAIN,
    ProhibitedCategory.OPAQUE_BINARY,
    ProhibitedCategory.CYCLIC_INPUT,
    ProhibitedCategory.UNSUPPORTED_INPUT,
)
_PRECEDENCE = {category: index for index, category in enumerate(VALIDATION_PRECEDENCE)}

_EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@"
    r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?![A-Za-z0-9.-])",
    re.ASCII,
)
_URL_PATTERN = re.compile(r"\bhttps?://[^\s\"'<>`]+", re.IGNORECASE | re.ASCII)
_DOMAIN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9.-])(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63}(?![A-Za-z0-9.-])",
    re.ASCII,
)
_VIN_PATTERN = re.compile(
    r"(?<![A-Z0-9])[A-HJ-NPR-Z0-9]{17}(?![A-Z0-9])",
    re.IGNORECASE | re.ASCII,
)
_ADDRESS_PATTERN = re.compile(
    r"\b\d{1,6}\s+[A-Za-z0-9.' -]{2,48}\s+"
    r"(?:street|st|avenue|ave|road|rd|boulevard|blvd|lane|ln|drive|dr|court|ct|way)\b",
    re.IGNORECASE | re.ASCII,
)
_HTML_PATTERN = re.compile(
    r"<\s*(?:!doctype\s+html|html\b|head\b|body\b|script\b)",
    re.IGNORECASE | re.ASCII,
)
_PHONE_SHAPE_PATTERN = re.compile(r"\A[+()0-9 .-]{7,24}\Z", re.ASCII)
_JWT_PATTERN = re.compile(
    r"\be" + r"yJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b",
    re.ASCII,
)
_PRIVATE_KEY_MARKER = "-" * 5 + "BEGIN " + "PRIVATE" + " KEY" + "-" * 5
_CREDENTIAL_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(?:pass" + r"word|pass" + r"wd|sec" + r"ret|api[_-]?key)\b\s*[:=]"
)
_COOKIE_HEADER_PATTERN = re.compile(
    r"(?i)\b(?:set" + r"-cookie|cookie)\s*:"
)
_AUTHORIZATION_PATTERN = re.compile(
    r"(?i)\bauthorization\s*:\s*(?:basic|bearer)\s+"
)
_PRODUCTION_LOG_PATTERN = re.compile(
    r"(?im)(?:\bprod(?:uction)?\b.{0,32}\blog\b|"
    r"\b(?:error|warn|info)\b.{0,40}\bprod(?:uction)?\b)"
)
_SAFE_PATH_PATTERN = re.compile(
    r"\A\$(?:(?:\[entry:\d+\]\.(?:key|value))|(?:\[item:\d+\]))*\Z",
    re.ASCII,
)
_FIELD_NORMALIZER = re.compile(r"[^a-z0-9]+", re.ASCII)

_CREDENTIAL_FIELDS = frozenset(
    {
        "api_key",
        "auth_secret",
        "client_secret",
        "credential",
        "credentials",
        "password",
        "passwd",
        "passphrase",
        "private_key",
        "secret",
    }
)
_COOKIE_FIELDS = frozenset({"cookie", "cookies", "set_cookie"})
_TOKEN_FIELDS = frozenset(
    {
        "access_token",
        "authorization",
        "bearer_token",
        "id_token",
        "refresh_token",
        "token",
        "tokens",
    }
)
_SESSION_FIELDS = frozenset({"browser_session", "session", "session_id", "sessions"})
_BROWSER_STORAGE_FIELDS = frozenset(
    {
        "browser_storage",
        "indexed_db",
        "indexeddb",
        "local_storage",
        "session_storage",
        "storage_dump",
    }
)
_SCREENSHOT_FIELDS = frozenset(
    {"capture", "image", "image_data", "screen_capture", "screenshot", "screenshots"}
)
_HTML_FIELDS = frozenset({"dom_dump", "html", "html_dump", "page_source", "raw_html"})
_LOG_FIELDS = frozenset({"log_dump", "prod_log", "production_log", "raw_log"})
_SELECTOR_FIELDS = frozenset(
    {"css_selector", "portal_selector", "production_selector", "selector", "xpath"}
)
_CLOUD_DOCUMENT_FIELDS = frozenset(
    {"cloud_document_id", "document_id", "drive_id", "sheet_id", "spreadsheet_id"}
)
_EMAIL_FIELDS = frozenset({"customer_email", "email", "email_address"})
_PHONE_FIELDS = frozenset({"customer_phone", "mobile", "phone", "phone_number", "telephone"})
_ADDRESS_FIELDS = frozenset(
    {
        "address",
        "billing_address",
        "customer_address",
        "postal_address",
        "shipping_address",
        "street_address",
    }
)
_CUSTOMER_NAME_FIELDS = frozenset(
    {"buyer_name", "contact_name", "customer_name", "recipient_name"}
)
_NOTE_FIELDS = frozenset(
    {"copied_note", "copied_notes", "customer_note", "note", "notes", "raw_note"}
)
_HOST_FIELDS = frozenset(
    {"company_domain", "domain", "host", "hostname", "internal_hostname", "server", "url"}
)
_PRODUCT_FIELDS = frozenset(
    {
        "manufacturer",
        "manufacturer_id",
        "manufacturer_part_number",
        "mfg",
        "mfg_id",
        "oe_number",
        "oem",
        "part_number",
        "product_code",
        "product_id",
        "sku",
    }
)


@dataclass(frozen=True, slots=True, order=True)
class ProhibitedFinding:
    """A safe finding that deliberately excludes the rejected value and field name."""

    category: str
    path: str

    def to_dict(self) -> dict[str, str]:
        return {"category": self.category, "path": self.path}


class ProhibitedInputError(ValueError):
    """Raised by :func:`assert_payload_safe` without echoing prohibited material."""

    def __init__(self, findings: tuple[ProhibitedFinding, ...]) -> None:
        self.findings = findings
        summary = ", ".join(f"{item.category}@{item.path}" for item in findings)
        super().__init__(f"prohibited input rejected ({len(findings)} finding(s)): {summary}")


def _normalized_field(field_name: str | None) -> str:
    if field_name is None:
        return ""
    return _FIELD_NORMALIZER.sub("_", field_name.casefold()).strip("_")


def _safe_path(path: str) -> str:
    if isinstance(path, str) and _SAFE_PATH_PATTERN.fullmatch(path) is not None:
        return path
    return "$"


def _identity_namespace(field: str) -> str | None:
    checks = (
        ("CUSTOMER", ("customer_id",)),
        ("ORDER", ("order_id", "order_number")),
        ("SKU", ("sku", "sku_id")),
        ("INTERACTION", ("interaction_id",)),
        ("CONVERSATION", ("conversation_id",)),
        ("SNAPSHOT", ("snapshot_id",)),
        ("EVALUATION", ("evaluation_id",)),
        ("RUN", ("run_id",)),
        ("REP", ("rep_id", "representative_id")),
        ("EVIDENCE", ("evidence_id",)),
    )
    for namespace, suffixes in checks:
        if any(field == suffix or field.endswith(f"_{suffix}") for suffix in suffixes):
            return namespace
    return None


def _is_obviously_synthetic_text(value: str) -> bool:
    candidate = value.strip()
    if re.fullmatch(
        r"(?i)(?:synthetic|fictional|test)(?:[ _-][A-Za-z0-9]+)+",
        candidate,
        re.ASCII,
    ):
        return True
    return re.fullmatch(r"SYN-[A-Z0-9]+(?:-[A-Z0-9]+)+", candidate, re.ASCII) is not None


def _is_safe_synthetic_selector(value: str) -> bool:
    lowered = value.casefold()
    return "data-syn-" in lowered or "#syn-" in lowered or ".syn-" in lowered


def _is_permitted_synthetic_host(host: str | None) -> bool:
    if host is None:
        return False
    candidate = host.casefold().rstrip(".")
    if candidate in {"127.0.0.1", "localhost", "::1"}:
        return True
    return candidate.endswith((".test", ".example", ".invalid"))


def _host_from_text(value: str) -> str | None:
    candidate = value.strip()
    if "://" in candidate:
        try:
            return urlsplit(candidate).hostname
        except ValueError:
            return None
    if re.fullmatch(r"\[[0-9A-Fa-f:]+\](?::\d+)?", candidate, re.ASCII):
        return candidate.partition("]")[0].removeprefix("[")
    return candidate.partition(":")[0]


def _context_category(field: str) -> str | None:
    if field in _CREDENTIAL_FIELDS:
        return ProhibitedCategory.CREDENTIAL
    if field in _COOKIE_FIELDS:
        return ProhibitedCategory.COOKIE
    if field in _TOKEN_FIELDS:
        return ProhibitedCategory.TOKEN
    if field in _SESSION_FIELDS:
        return ProhibitedCategory.SESSION
    if field in _BROWSER_STORAGE_FIELDS:
        return ProhibitedCategory.BROWSER_STORAGE
    if field in _SCREENSHOT_FIELDS:
        return ProhibitedCategory.SCREENSHOT
    if field in _HTML_FIELDS:
        return ProhibitedCategory.HTML_DUMP
    if field in _LOG_FIELDS:
        return ProhibitedCategory.PRODUCTION_LOG
    if field in _SELECTOR_FIELDS:
        return ProhibitedCategory.PRODUCTION_SELECTOR
    if field in _CLOUD_DOCUMENT_FIELDS:
        return ProhibitedCategory.CLOUD_DOCUMENT_ID
    return None


def _winning_category(candidates: set[str]) -> str | None:
    if not candidates:
        return None
    return min(candidates, key=_PRECEDENCE.__getitem__)


def _scan_text_candidates(text: str, field_name: str | None) -> set[str]:
    field = _normalized_field(field_name)
    candidates: set[str] = set()

    context_category = _context_category(field)
    if context_category is not None:
        if context_category != ProhibitedCategory.PRODUCTION_SELECTOR or not (
            _is_safe_synthetic_selector(text)
        ):
            candidates.add(context_category)

    if _PRIVATE_KEY_MARKER in text or _CREDENTIAL_ASSIGNMENT_PATTERN.search(text):
        candidates.add(ProhibitedCategory.CREDENTIAL)
    if _COOKIE_HEADER_PATTERN.search(text):
        candidates.add(ProhibitedCategory.COOKIE)
    if _JWT_PATTERN.search(text) or _AUTHORIZATION_PATTERN.search(text):
        candidates.add(ProhibitedCategory.TOKEN)
    if _HTML_PATTERN.search(text):
        candidates.add(ProhibitedCategory.HTML_DUMP)
    if _PRODUCTION_LOG_PATTERN.search(text):
        candidates.add(ProhibitedCategory.PRODUCTION_LOG)

    for match in _EMAIL_PATTERN.finditer(text):
        if not is_synthetic_email(match.group(0)):
            candidates.add(ProhibitedCategory.NON_SYNTHETIC_EMAIL)
            break
    if field in _EMAIL_FIELDS and text and not is_synthetic_email(text):
        candidates.add(ProhibitedCategory.NON_SYNTHETIC_EMAIL)

    phone_context = field in _PHONE_FIELDS
    phone_shaped = _PHONE_SHAPE_PATTERN.fullmatch(text) is not None
    has_phone_formatting = any(character in text for character in "+() .-")
    if text and (phone_context or (phone_shaped and has_phone_formatting)):
        digit_count = sum(character.isdigit() for character in text)
        if digit_count >= 7 and not is_fictional_555_phone(text):
            candidates.add(ProhibitedCategory.NON_FICTIONAL_PHONE)

    if _VIN_PATTERN.search(text):
        candidates.add(ProhibitedCategory.VIN)
    if _ADDRESS_PATTERN.search(text):
        candidates.add(ProhibitedCategory.REAL_LOOKING_ADDRESS)
    if field in _ADDRESS_FIELDS and text and not _is_obviously_synthetic_text(text):
        candidates.add(ProhibitedCategory.REAL_LOOKING_ADDRESS)
    if field in _CUSTOMER_NAME_FIELDS and text and not _is_obviously_synthetic_text(text):
        candidates.add(ProhibitedCategory.REAL_LOOKING_CUSTOMER_NAME)

    namespace = _identity_namespace(field)
    if namespace == "ORDER" and text.isascii() and text.isdigit():
        candidates.add(ProhibitedCategory.UNWRAPPED_NUMERIC_ORDER_ID)
    if field in _PRODUCT_FIELDS and text:
        product_is_safe = (
            is_reserved_identity(text, expected_namespace="SKU")
            if namespace == "SKU" or field in {"product_id", "product_code"}
            else _is_obviously_synthetic_text(text)
        )
        if not product_is_safe:
            candidates.add(ProhibitedCategory.REAL_PRODUCT_OR_MANUFACTURER_ID)
    if namespace is not None and not is_reserved_identity(text, expected_namespace=namespace):
        candidates.add(ProhibitedCategory.NON_SYNTHETIC_IDENTITY)
    if text.startswith("SYN-") and not is_reserved_identity(text):
        candidates.add(ProhibitedCategory.NON_SYNTHETIC_IDENTITY)

    if field in _NOTE_FIELDS and text and not text.casefold().startswith(
        ("synthetic:", "fictional:", "test:")
    ):
        candidates.add(ProhibitedCategory.COPIED_NOTES)

    for match in _URL_PATTERN.finditer(text):
        try:
            host = urlsplit(match.group(0).rstrip(".,);]")).hostname
        except ValueError:
            host = None
        if not _is_permitted_synthetic_host(host):
            candidates.add(ProhibitedCategory.COMPANY_DOMAIN)
            break

    if field in _HOST_FIELDS and text:
        host = _host_from_text(text)
        if host is not None:
            normalized_host = host.casefold().rstrip(".")
            is_internal = (
                normalized_host.endswith((".corp", ".internal", ".lan", ".local"))
                or (
                    "." not in normalized_host
                    and ":" not in normalized_host
                    and normalized_host != "localhost"
                )
            )
            if is_internal:
                candidates.add(ProhibitedCategory.INTERNAL_HOSTNAME)
            elif not _is_permitted_synthetic_host(host):
                candidates.add(ProhibitedCategory.COMPANY_DOMAIN)

    for match in _DOMAIN_PATTERN.finditer(text):
        if not _is_permitted_synthetic_host(match.group(0)):
            candidates.add(ProhibitedCategory.COMPANY_DOMAIN)
            break

    return candidates


def scan_text(
    text: str,
    *,
    path: str = "$",
    field_name: str | None = None,
) -> tuple[ProhibitedFinding, ...]:
    """Scan one text value, returning at most its highest-precedence finding."""

    if not isinstance(text, str):
        raise TypeError("text must be a string")
    category = _winning_category(_scan_text_candidates(text, field_name))
    if category is None:
        return ()
    return (ProhibitedFinding(category=category, path=_safe_path(path)),)


def _non_text_scalar_category(value: object, field_name: str | None) -> str | None:
    field = _normalized_field(field_name)
    context_category = _context_category(field)
    if context_category is not None:
        return context_category
    namespace = _identity_namespace(field)
    if namespace == "ORDER" and isinstance(value, (int, float)) and not isinstance(value, bool):
        return ProhibitedCategory.UNWRAPPED_NUMERIC_ORDER_ID
    if field in _PRODUCT_FIELDS and isinstance(value, (int, float)) and not isinstance(value, bool):
        return ProhibitedCategory.REAL_PRODUCT_OR_MANUFACTURER_ID
    if namespace is not None:
        return ProhibitedCategory.NON_SYNTHETIC_IDENTITY
    if field in _EMAIL_FIELDS:
        return ProhibitedCategory.NON_SYNTHETIC_EMAIL
    if field in _PHONE_FIELDS:
        return ProhibitedCategory.NON_FICTIONAL_PHONE
    if field in _ADDRESS_FIELDS:
        return ProhibitedCategory.REAL_LOOKING_ADDRESS
    if field in _CUSTOMER_NAME_FIELDS:
        return ProhibitedCategory.REAL_LOOKING_CUSTOMER_NAME
    if field in _NOTE_FIELDS:
        return ProhibitedCategory.COPIED_NOTES
    return None


def scan_payload(payload: object) -> tuple[ProhibitedFinding, ...]:
    """Recursively scan a JSON-like payload without retaining prohibited material."""

    findings: list[ProhibitedFinding] = []
    active_containers: set[int] = set()

    def add(category: str, path: str) -> None:
        findings.append(ProhibitedFinding(category=category, path=_safe_path(path)))

    def visit(value: object, path: str, field_name: str | None, depth: int) -> None:
        if depth > 64:
            add(ProhibitedCategory.UNSUPPORTED_INPUT, path)
            return

        normalized_field = _normalized_field(field_name)
        container_context = _context_category(normalized_field)
        if container_context is not None and isinstance(
            value, (Mapping, list, tuple, set, frozenset, bytes, bytearray, memoryview)
        ):
            add(container_context, path)
            return

        if value is None or isinstance(value, bool):
            category = _non_text_scalar_category(value, field_name)
            if category is not None:
                add(category, path)
            return
        if isinstance(value, str):
            findings.extend(scan_text(value, path=path, field_name=field_name))
            return
        if isinstance(value, (bytes, bytearray, memoryview)):
            add(ProhibitedCategory.OPAQUE_BINARY, path)
            return
        if isinstance(value, (int, float)):
            if isinstance(value, float) and not math.isfinite(value):
                add(ProhibitedCategory.UNSUPPORTED_INPUT, path)
                return
            category = _non_text_scalar_category(value, field_name)
            if category is not None:
                add(category, path)
            return

        if isinstance(value, Mapping):
            identity = id(value)
            if identity in active_containers:
                add(ProhibitedCategory.CYCLIC_INPUT, path)
                return
            active_containers.add(identity)
            try:
                for index, (key, item) in enumerate(value.items()):
                    key_path = f"{path}[entry:{index}].key"
                    value_path = f"{path}[entry:{index}].value"
                    if isinstance(key, str):
                        findings.extend(scan_text(key, path=key_path))
                        child_field = key
                    else:
                        visit(key, key_path, None, depth + 1)
                        child_field = None
                    visit(item, value_path, child_field, depth + 1)
            finally:
                active_containers.remove(identity)
            return

        if isinstance(value, (list, tuple)):
            identity = id(value)
            if identity in active_containers:
                add(ProhibitedCategory.CYCLIC_INPUT, path)
                return
            active_containers.add(identity)
            try:
                for index, item in enumerate(value):
                    visit(item, f"{path}[item:{index}]", field_name, depth + 1)
            finally:
                active_containers.remove(identity)
            return

        if isinstance(value, (set, frozenset)):
            add(ProhibitedCategory.UNSUPPORTED_INPUT, path)
            return
        add(ProhibitedCategory.UNSUPPORTED_INPUT, path)

    visit(payload, "$", None, 0)
    return tuple(dict.fromkeys(findings))


def assert_payload_safe(payload: object) -> None:
    """Raise :class:`ProhibitedInputError` if ``payload`` is not synthetic-safe."""

    findings = scan_payload(payload)
    if findings:
        raise ProhibitedInputError(findings)


__all__ = [
    "ProhibitedCategory",
    "ProhibitedFinding",
    "ProhibitedInputError",
    "VALIDATION_PRECEDENCE",
    "assert_payload_safe",
    "scan_payload",
    "scan_text",
]
