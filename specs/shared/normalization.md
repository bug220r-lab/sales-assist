
# Identifier Normalization

## Shared edge trim

Apply `ASCII_FOUR` at outer edges only:

- TAB (`0x09`)
- LF (`0x0A`)
- CR (`0x0D`)
- SPACE (`0x20`)

No Unicode normalization, Unicode whitespace trimming, locale behavior, or internal-space
removal is allowed.

## Order Number

After edge trim, require a positive ASCII digit sequence. Exact provider integers are accepted
only when no binary-float ambiguity exists. Remove leading zeroes and output `[1-9][0-9]*`.

Reject zero, signs, fractions, exponents, booleans, dates/errors, Unicode digits, internal
whitespace, and precision-ambiguous numerics.

Raw source text is transient. Retain only the canonical identifier and a privacy-closed
source reference.

## ES Number

Policy: `ES_NUMERIC_CORE`.

- Apply ASCII_FOUR.
- Accept optional ASCII-case-insensitive `ES#` or `ES` prefix.
- Require a positive ASCII digit core.
- Remove leading zeroes.
- Canonical output is the digit core only.
- Maximum input length: 64 UTF-8 bytes.

Reject prefix-only, zero/all-zero, internal whitespace, other punctuation, signs, exponents,
Unicode, control bytes, provider numeric cells, and overlength values.

## MFG/OE Number

Policy: `MFG_SEPARATOR_PRESERVING_UPPER`.

- Apply ASCII_FOUR.
- Require 1–128 printable ASCII bytes.
- Uppercase ASCII `a-z`.
- Preserve internal spaces, hyphens, periods, underscores, slashes, repeated spaces, and
  leading zeroes.
- Treat compound source values as one opaque value.

Do not remove separators, remove leading zeroes, split components, fuzzy match, infer a
manufacturer, or create a manufacturer-specific normalization registry.
