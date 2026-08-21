# Milestone 3 DOI rule pack

Milestone 3 implements the deterministic, synthetic-only DOI domain. It consumes only immutable
in-memory facts supplied by tests, emits explainable rule results and logical events, and performs
no file, portal, browser, network, customer-message, or external-order operation.

The executable package is `synthetic_sales_assist.doi`. Its public facade is closed and
duplicate-free. Pure modules do not read a clock, allocate identities, use randomness, acquire a
lock, or perform I/O. The state coordinator is process-local test infrastructure and applies pure
reducers under one copy-on-write commit boundary.

## Base provenance

Milestone 3 continues from commit `44c4a5b0c782535d2f85e0be5b5f03073c76b8f8`, whose exact
tree is `d4fbe84f22e684ba9ae2b24c619a5064def8660e`.

## Layers

1. `identities` gives DOI semantic roles to existing reserved synthetic identity namespaces.
2. `source` validates a coherent in-memory queue, imports exact rows, computes count equations,
   and reduces review/recheck run control.
3. `extraction` constructs factual snapshots and whole-order/line-continuity proofs.
4. `case_attention` owns sealed case admission/refresh and cause-keyed attention decisions.
5. `models` closes DOI facts, states, opportunity scopes, coordination records, and results.
6. `knowledge` governs product-only alternate relationship revisions and observations.
7. `evaluator` applies DOI precedence and the approved uncertainty/overlap policy.
8. `lifecycle` binds all 115 transitions to typed owner evidence and immutable effects.
9. `interventions` maintains verified-action, link, value, and reversal histories.
10. `state` composes replay-safe run, case, transition, and retention effects in memory.
11. `retention` owns KPI contribution histories, calendar deadlines, and purge finalization.
12. `fixtures` and `traceability` publish deterministic KATs and collected-test ownership.

DEDUPE confirmation is grounded in a distinct later complete read-only snapshot and finding, not
in a caller-supplied timestamp over the pre-approval observation. Lifecycle authority proofs are
scope-bound capabilities issued from typed evidence; generic caller booleans cannot authorize a
protected transition.

## Closed milestone boundary

Milestone 3 adds no business table, migration, SQLite DOI repository, portal, API, server,
dashboard, browser, extension, connector, scheduler, worker, backup, restore, or external network
capability. Migration `0001_foundation.sql` remains the sole migration. Durable transaction and
adapter implementation is Milestone 4 work and is intentionally absent.

The supplied files under `specs/` and `reference/`, plus `BUNDLE_MANIFEST.json` and
`SHA256SUMS.txt`, remain byte-identical. The approved business reconciliation is recorded only in
`docs/product_decisions/0001-doi-opportunity-preservation-under-uncertainty.md` and in generated
implementation-side effective ownership.

## Generated release artifacts

The checked-in artifacts below are rendered from executable registries, KAT providers, and
collected-test selectors. Tests reject missing files or byte drift:

- `docs/milestone3-hash-preimages.md` — 94 distinct domain/LF/canonical-JSON known answers;
- `docs/milestone3-reason-owner-oracle-reconciliation.md` — 138 supplied reasons and ownership
  rows, approved effective routes, and independent owning-behavior selectors;
- `docs/milestone3-transition-implementation-matrix.md` — all 115 supplied transitions, exact
  guards/effects, and collected production-owner legal/invalid-from-state selectors; and
- `docs/milestone3-synthetic-scenario-inventory.md` — 77 named scenarios plus 230 registry-derived
  transition scenarios, 307 total rows, 290 distinct collected selectors, and nine zero safety
  counters per row.

The generated lifecycle inventory is acceptance coverage, not a substitute for reason ownership.
Every emitted reason must also be observed in an independently collected owning rule/service or
typed boundary test. Registry planning-oracle labels remain provenance only.
