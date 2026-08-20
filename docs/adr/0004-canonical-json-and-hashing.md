# ADR 0004: Canonical JSON and domain-separated hashing

- Status: accepted for Milestone 1
- Scope: shared canonical bytes, SHA-256 bindings, and collision detection only

## Decision

Canonical JSON v1 is UTF-8 with no BOM, sorted object member names, compact separators, JSON
booleans/null, and unescaped non-ASCII Unicode scalar values. The encoder accepts only ordinary
JSON types and rejects every binary floating-point value, invalid Unicode, and implicit Python
aliases. JSON integers are limited to the exactly interoperable range
`[-9007199254740991, 9007199254740991]`; exact decimal and quantity values use their governed
string forms. A caller
may provide the exact expected top-level member set; missing and unknown members both fail.
Nested closed objects are validated by their owning object contract before embedding.

The strict byte decoder rejects invalid UTF-8, duplicate members at every object depth,
non-finite constants, malformed input, and any byte representation that differs from a fresh
canonical encoding. This makes whitespace, alternate member order, escape aliases, and numeric
lexeme aliases invalid before persistence or hashing.

Every hash domain is a lowercase versioned identifier ending in `/vN`. Its preimage is exactly:

```text
ASCII(domain) || LF || canonical_json_bytes
```

There is no trailing LF. SHA-256 is rendered as 64 lowercase hexadecimal characters.
`HashBinding` is immutable and retains `domain`, `sha256`, and non-repr `canonical_bytes`; its
`preimage` property reconstructs the exact bytes. Construction verifies the digest rather than
trusting a supplied value.

Digest equality is never accepted as replay proof by itself. Retained and candidate canonical
bytes are compared whenever their digests match. Equal digests with different bytes raise a
closed collision error before any caller can treat the candidate as idempotent. Rejection errors
contain categories only and never echo domains or payload bytes.

## Consequences

Hash-bearing record definitions can share one deterministic implementation without importing
persistence or business rules. Callers must retain canonical bytes beside a digest wherever
collision protection is required. New or changed preimage domains require a new versioned domain
and executable vectors; they may not silently reinterpret an existing digest.
