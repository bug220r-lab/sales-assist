# ADR 0002: Synthetic identity, privacy, and logging boundary

- Status: accepted for Milestone 0
- Scope: executable input and diagnostic foundations

## Decision

Executable identifiers use one of the ten reserved `SYN-*` namespaces and a bounded uppercase
ASCII suffix. Email values must use `example.test`; phone values must be in the clearly fictional
North American 555-01xx range. Unicode confusables, whitespace, empty suffixes, and values outside
those forms fail closed.

The prohibited-input firewall walks closed in-memory payloads before future persistence or rule
execution. Findings contain only category and structural path, never rejected values. Structured
logging accepts a small field allowlist, emits one JSON object per line, and rejects sensitive or
unbounded fields instead of attempting to preserve their content.

## Consequences

This deliberately narrow grammar may reject harmless fictional-looking values; callers must use
the reserved generators instead of weakening the firewall. The choice reduces privacy ambiguity
without deciding any Sales Credit or DOI outcome. Later domain schemas must invoke this boundary
and add their own executable privacy-canary precedence tests.
