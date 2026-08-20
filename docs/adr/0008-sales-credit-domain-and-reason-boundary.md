# ADR 0008: Sales Credit domain and reason boundary

- Status: accepted for Milestone 2
- Scope: pure synthetic Sales Credit values, reasons, and hash-bearing records

## Decision

Milestone 2 has a dedicated `synthetic_sales_assist.sales_credit` package. Its records are
immutable, slotted, version-bound values composed from the Shared Domain Engine primitives.
Every identity remains in a reserved `SYN-*` namespace. Exact money and quantity values reuse
the governed shared types. Caller input is validated without coercion and rejection errors expose
only closed codes.

Sales Credit workflow states are the exact 16 values in
`specs/sales_credit/workflow_states.json`. Sales Credit reasons form a separate closed catalog.
DOI `ReasonRef`, DOI reason codes, and DOI evaluation/snapshot envelopes are not valid Sales
Credit values. A reason is explanatory metadata, never an authorization or manager outcome.

Hash-bearing Sales Credit records use ADR 0004 canonical JSON and versioned domain separation.
Each accepted object retains or can reproduce its exact canonical preimage, and every M2 domain
has an executable known-answer vector. Any domain or member-shape change requires a new version,
updated vector, and closure-matrix re-audit.

Active-only descriptions, notes, and evidence excerpts are bounded synthetic text. They are
redacted from representations and excluded from closed audit records, metrics, errors, and logs.
Raw ES and MFG/OE fixture values carry an exact `synthetic:` source-envelope marker that is
retained and hash-bound; only the post-marker payload is passed to the governed shared
normalizer. Raw rep observations are limited to the three binding literals or an explicit
`synthetic_` fixture handle. These are M2 fixture-envelope rules, not changes to the shared
normalization algorithms.

## Consequences

The Sales Credit pack can explain its decisions without importing DOI semantics or persistence.
It is intentionally a pure rule pack: no database table, adapter, browser, API, network client, or
manager authority is introduced in Milestone 2.
