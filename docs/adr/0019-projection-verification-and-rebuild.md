# ADR 0019: Projection verification and rebuild

- Status: accepted for Milestone 4
- Scope: persisted current projections derived from immutable history

## Decision

Persist current projections as versioned accelerators whose authoritative inputs remain immutable
events and records. Each update appends the exact event and then performs a compare-and-set using
the expected prior projection version and event head in one transaction. Readback must equal the
domain reducer's expected state before the receipt can be inserted.

Provide read-only verification for the Sales Credit case projection, DOI run projection, DOI case
lifecycle, DOI attention cause set, and DOI intervention/value projection. Verification replays or
otherwise deterministically reduces the retained event history and compares the complete governed
projection. The Milestone 4 CLI reports drift and does not silently repair it.

Any later rebuild mode must require an explicit maintenance command, verify the expected prior
version, preserve immutable history, and append an audit receipt. That mutation surface is not
included in Milestone 4.

## Consequences

A corrupted or stale projection cannot masquerade as authoritative history. Normal reads remain
efficient, while verification proves rebuildability. Direct SQL updates to immutable inputs are
rejected by triggers; projection corruption is detected before health verification succeeds.
