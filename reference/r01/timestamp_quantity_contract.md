
> **Sanitized supporting reference.** This file is a mechanically sanitized derivative of
> source material supplied for the synthetic proof of concept. Historical status/freeze
> language is nonbinding. The curated files under `specs/` govern. No production-system
> access or real-data use is authorized by this reference.

# R01 Timestamp and Quantity Contract

Package: `doi-authority-remediation-r01-fact-normalization/v1.1`  
Status: `READY_FOR_INDEPENDENT_AUDIT`  
Date: 2026-08-11

## Timestamp

The predecessor `doi-timestamp/r01-v1` authority remains exact: RFC-3339-subset input with required `Z` or numeric offset, canonical UTC `Z`, up to nine fractional digits with trailing-zero removal, immutable JSON string, SQLite `TEXT COLLATE BINARY`, exact-instant equality, and primitive hash `SHA256("doi-timestamp/r01-v1" || LF || canonical UTF-8)`.

## Quantity — final B004 authority

Selected policy: `INTEGER_ONLY_ALL_FOUR_FIELDS_MAX_9_DIGITS`.

The four source fields share `doi-quantity/nonnegative-integer-max-9-digits/r01-v1` / `8d021f3460545fae638ce6df4b6cfcac46f693e7c5ad7a4cfd82f252fce4a5ca`. Their domain is nonnegative integer, minimum `0`, maximum `999999999`, total digits 9, scale 0, and canonical grammar `0|[1-9][0-9]{0,8}`. Immutable JSON is a string; SQLite is `TEXT COLLATE BINARY`. JSON numbers, SQLite REAL, binary float, sign, exponent, comma, nonzero fraction, rounding, truncation, ambiguity, and out-of-range values are forbidden.

Exact integer text and exact provider-integer proof normalize to the canonical integer string. Exact decimal text may normalize only if every fractional digit is zero and exactness is proved. Leading integer zeroes are removed only at the adapter boundary.

A parsed invalid numeric fails before a Quantity, wrapper, snapshot, downstream scope/mapping, persistence row, arithmetic result, or hash. It is not converted to `UNKNOWN`. RC-128..RC-131 remain only for readable opaque/uninterpretable facts for which no numeric is parsed.

`CreditScopeComponent.quantity`, group-scope quantities, and `MovedLineMappingComponent.quantity` reuse the primitive with an additional `1..999999999` guard. Counts are not Quantity. Money multiplication uses exact integer/decimal arithmetic without float or rounding.

Canonical vectors: `SYN-R01-QTY-001[...]`. Negatives: `SYN-R01-QTY-N001[...]`.
