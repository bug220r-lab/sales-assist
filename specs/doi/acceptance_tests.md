
# DOI Acceptance Tests

All tests use fictional identifiers and localhost-only sources.

## Required families

- source ingestion and failed-attempt retention;
- batch/run references;
- currency and exact money;
- extraction and whole-order completeness;
- line continuity;
- core rules and geography;
- WWC and DEDUPE;
- alternates and relationship revisions;
- evaluation provenance;
- Action Context;
- immutable state histories and lifecycle payloads;
- resulting-order and intervention histories;
- opportunity scope and overlap;
- KPI;
- reason ownership;
- idempotency;
- retention and purge edges;
- privacy;
- read-only portal and capability safety.

## Core rule coverage

At minimum:

- full direct ship;
- mixed direct ship;
- fulfillment split;
- partial quantity;
- all-in-stock progress review;
- payment only and payment + product;
- shipped/canceled/transferred closures;
- exact SKU and every alternate type;
- no verified alternate;
- manual identification;
- unknown availability/direct-ship/ETA and multi-unknown containment;
- source disappearance/recheck;
- contact, WWC, DEDUPE;
- opportunity overlap;
- action verification, value, corrections, reversals;
- resulting-order link states;
- KPI finalization;
- retention/reopen/purge;
- every invalid transition.

## Audit-derived mandatory tests

Every item in `../advisory/known_audit_findings.md` is release-blocking.

## Oracle rule

A test ID or bracketed selector is valid only when it maps to an actual executable collected
case. Generated inventories must be derived from the test runner, not copied from a document.
