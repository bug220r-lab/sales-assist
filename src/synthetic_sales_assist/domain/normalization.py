"""Exact shared identifier normalization primitives."""

from __future__ import annotations

import re


ASCII_FOUR_CHARACTERS = "\t\n\r "
MAX_EXACT_PROVIDER_INTEGER = (1 << 53) - 1
MAX_ES_INPUT_UTF8_BYTES = 64
MAX_MFG_OE_CANONICAL_BYTES = 128

_ASCII_DIGITS_PATTERN = re.compile(r"\A[0-9]+\Z", re.ASCII)
_ASCII_UPPER_TRANSLATION = str.maketrans(
    "abcdefghijklmnopqrstuvwxyz",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
)


class NormalizationError(ValueError):
    """Reject invalid source material without retaining or echoing it."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"identifier normalization rejected: {code}")


def _require_exact_text(value: object) -> str:
    if type(value) is not str:
        raise NormalizationError("input_type")
    return value


def ascii_four_trim(value: object) -> str:
    """Remove only TAB, LF, CR, and SPACE from the two outer edges."""

    text = _require_exact_text(value)
    start = 0
    end = len(text)
    while start < end and text[start] in ASCII_FOUR_CHARACTERS:
        start += 1
    while end > start and text[end - 1] in ASCII_FOUR_CHARACTERS:
        end -= 1
    return text[start:end]


def _canonical_positive_ascii_digits(value: str, *, code: str) -> str:
    if _ASCII_DIGITS_PATTERN.fullmatch(value) is None:
        raise NormalizationError(code)
    canonical = value.lstrip("0")
    if not canonical:
        raise NormalizationError(code)
    return canonical


def normalize_order_number(value: object) -> str:
    """Normalize source text or one exact safe provider integer to an Order Number."""

    if type(value) is int:
        if not 1 <= value <= MAX_EXACT_PROVIDER_INTEGER:
            raise NormalizationError("order_provider_integer")
        return str(value)
    if type(value) is not str:
        raise NormalizationError("order_input_type")
    candidate = ascii_four_trim(value)
    return _canonical_positive_ascii_digits(candidate, code="order_grammar")


def normalize_es_number(value: object) -> str:
    """Apply ES_NUMERIC_CORE and return only the positive canonical digit core."""

    text = _require_exact_text(value)
    encoding_failed = False
    try:
        input_length = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        encoding_failed = True
        input_length = 0
    if encoding_failed:
        raise NormalizationError("es_encoding")
    if input_length > MAX_ES_INPUT_UTF8_BYTES:
        raise NormalizationError("es_input_length")

    candidate = ascii_four_trim(text)
    if not candidate.isascii():
        raise NormalizationError("es_grammar")
    if candidate[:3].lower() == "es#":
        core = candidate[3:]
    elif candidate[:2].lower() == "es":
        core = candidate[2:]
    else:
        core = candidate
    return _canonical_positive_ascii_digits(core, code="es_grammar")


def normalize_mfg_oe_number(value: object) -> str:
    """Apply MFG_SEPARATOR_PRESERVING_UPPER to one opaque compound value."""

    candidate = ascii_four_trim(value)
    if not candidate or len(candidate) > MAX_MFG_OE_CANONICAL_BYTES:
        raise NormalizationError("mfg_oe_length")
    if not candidate.isascii() or any(
        not 0x20 <= ord(character) <= 0x7E for character in candidate
    ):
        raise NormalizationError("mfg_oe_grammar")
    return candidate.translate(_ASCII_UPPER_TRANSLATION)


# The binding contract names the canonical value MFGNumber while its policy section is
# MFG/OE Number.  Both spellings intentionally route to the same exact primitive.
normalize_mfg_number = normalize_mfg_oe_number


__all__ = [
    "ASCII_FOUR_CHARACTERS",
    "MAX_ES_INPUT_UTF8_BYTES",
    "MAX_EXACT_PROVIDER_INTEGER",
    "MAX_MFG_OE_CANONICAL_BYTES",
    "NormalizationError",
    "ascii_four_trim",
    "normalize_es_number",
    "normalize_mfg_number",
    "normalize_mfg_oe_number",
    "normalize_order_number",
]
