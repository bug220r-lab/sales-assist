# ADR 0015: DOI scope, intervention, KPI retention, and Milestone 4 boundary

- Status: accepted for Milestone 3
- Scope: opportunity identity, verified actions, value histories, and pure retention

## Decision

Each opportunity binds an immutable, canonically ordered scope of exact line snapshot identities,
quantities, and roles. Product relationship revisions, current observations, Action Context, and
structured human facts are separate bindings. Similar descriptions, recommendations, or UI-like
actions cannot establish a relationship or intervention.

Overlapping and mutually exclusive opportunities remain separate. Before an explicit scenario
selection, their aggregate potential is unavailable and values are not added. Selection binds the
exact retained opportunity set and produces a new aggregate projection without rewriting any
opportunity.

Mutual exclusivity itself is trusted only through a domain-separated immutable evidence record
that binds the exact evaluation, order, group, complete candidate option set, and an authorized
structured human fact. A bare caller-supplied group identifier, missing human fact, partial option
partition, cross-order binding, or mixed evidence cannot suppress aggregation.

An intervention exists only after exact system or authorized-human verification. Initial value,
correction, partial reversal, and full reversal are append-only events. Occurrence and evidence
natural keys enforce exact replay and conflict detection. Resulting-order searches, exact links,
mapping revisions, and rep verification remain distinct. Ambiguous links and unverified actions
contribute zero realized value.

Each verified intervention has at most one current retained KPI contribution. Contributions are
exact, action-date and currency bound, and never mixed across currencies. At case purge, the pure
retention reducer atomically reconciles and transfers the exact contribution into an identity-free
bucket, deletes the complete case graph and owner receipts, and leaves no order/case/link drill
through or reversible identity hash. Retention uses 90 New York calendar dates, preserving local
wall time, moving a spring-gap target to the first valid instant, and choosing the later instant in
a fall overlap.

## Milestone 4 deferral

Milestone 3 creates no DOI SQLite table, migration, durable repository, portal, API, server,
dashboard, browser or Chrome extension, connector, scheduler, worker, backup, restore, or network
operation. Those physical concerns are Milestone 4 work and must preserve this deterministic model.
