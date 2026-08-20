# ADR 0005: Immutable shared-domain values

- Status: accepted for Milestone 1
- Scope: shared value objects and neutral envelopes only

## Decision

Represent shared-domain values as frozen, slotted Python data classes with tuple-based
collections. Construction validates the complete closed shape; no setter, mutation helper,
silent coercion, or mutable collection is exposed. Synthetic identifiers remain distinct types
even when their wire representations are strings. Version and hash bindings travel with every
generic hash-bearing envelope. Closed string enumerations expose a read-only state view and
derive their serialized value from their immutable string payload, so Enum bookkeeping cannot
change a retained record after hashing. Counts and ordinals use distinct JSON-safe integer types;
they are not aliases for source quantities.

Retained canonical bytes are immutable `bytes` and are excluded from diagnostic
representations. Structured errors contain only a closed error code and structural field path;
they never retain or echo a rejected value. Generic envelopes reference source, evidence,
snapshot, evaluation, run, and event identities without deciding a Sales Credit or DOI outcome.
The generic snapshot requires a typed whole-order completeness proof. That proof binds the exact
requested and observed synthetic order, supported shared versions, source time, the exact five
required sections, readable/exhausted section proofs, count/manifest parity, and bidirectional
source-reference resolution. Each required section resolves to the exact requested order fixture;
the proof performs no extraction itself.

The generic evaluation explicitly binds supplied facts, rules evaluated, rules fired, reasons,
result, human review, versions, and persistence effects. Explanation items are enumerable by a
synthetic evidence ID, role-separated, versioned, and backed by nonempty canonical objects whose
exact member closure is required at construction. These records explain neutral structure but
execute no rule, transition, reason emission, or persistence effect.

## Consequences

Accepted records cannot change after hashing, dictionary keys remain stable, and callers must
construct a new validated value for every change. Tuple conversion is explicit at a construction
boundary rather than an implicit coercion of arbitrary input. Business entities, workflow state,
rules, adapter behavior, and database tables remain outside Milestone 1.
