# ADR 0023: Control Center current-projection query boundary

- Status: Accepted
- Date: 2026-09-01
- Decision scope: Milestone 7 local Control Center reads only

## Context

Milestone 7 must present current Sales Credit and DOI work alongside immutable evaluations,
receipts, and events. The schema-4 database already stores both current projections and append-only
history. Counting historical rows as current work would inflate queues, while rebuilding purged
identity from old evidence would violate retention. Dashboard routes also need bounded search,
sorting, filtering, and pagination without exposing SQL or raw stored payloads.

## Decision

The Control Center uses a dedicated application query boundary over the existing schema-4
repositories. Current cards and queues read only the latest current projection population. Detail
and audit views may join that projection to immutable owner events and evaluation snapshots, but
history never contributes another current queue member.

Every list query accepts a closed query object: bounded reserved-synthetic identifier search,
allowlisted filters, allowlisted deterministic sort keys, and bounded page/page-size integers.
Handlers cannot accept SQL fragments, arbitrary operators, unrestricted full text, hidden payload
search, or raw table selection. Query results report population count, page count, and returned
count from the same filtered snapshot so cards and pagination can be reconciled.

Exact replay receipts remain historical request outcomes and do not create evaluations. Material
conflicts remain rejected requests and do not create successful cases. Closed, superseded,
invalidated, and purged records are excluded according to the owning committed projection state.
Purged identities are never reconstructed. Unknown source facts remain unknown.

No migration is introduced: schema 4 already contains the necessary projections, immutable
events, telemetry, backup receipts, and indexes for the bounded local dataset. New code is a query
and presentation adapter, not a second projection authority.

## Consequences

- Current counts reconcile directly to current list populations.
- Immutable timelines remain complete without inflating operational cards.
- The dashboard cannot invent a source fact or resurrect a purged identity.
- Any future query field, operator, sort key, or migration requires explicit contract and tests.

## Rejected alternatives

- Counting evaluation/event rows as active cases.
- Raw SQL or generic repository browsers in HTTP handlers.
- Rebuilding a second dashboard-owned projection store.
- A schema migration solely to cache values already available from schema 4.
