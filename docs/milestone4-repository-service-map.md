# Milestone 4 repository and service map

## Shared persistence

- Connection policy: configured SQLite connections and explicit read/write units of work.
- Migration/schema service: immutable migration discovery, checksum verification, schema
  inventory, quick/integrity checks, and foreign-key checks.
- Idempotency repository: natural-key lookup, complete-byte replay, conflict/collision rejection,
  and retained receipts.
- Telemetry repository: closed timing/result fields and the exact nine-counter safety snapshot.
- Backup service: online backup, receipt verification, pre-restore backup, atomic restore, and
  post-swap verification.

## Sales Credit

- Repository reads typed case, interaction, search, snapshot, evidence, evaluation, outcome, and
  minimized-audit views.
- Transactional service persists interaction/search results, appends snapshots and evaluations,
  attaches multiple interactions to one case, records a separate manager outcome, minimizes
  closure, and purges eligible retained detail.
- Projection verifier derives the current case state from immutable case events.

## DOI

- Repository reads typed run, attempt, case, snapshot, evaluation, opportunity, product,
  coordination, intervention, link, value, KPI, and retention histories.
- Transactional services serialize retry/finalization and extraction/RC-084 races, append exact
  histories, update projections, verify action/value evidence, and finalize KPI plus purge.
- Projection verification covers run, case lifecycle, attention, and intervention/value state.

All public repository reads return validated frozen records or existing domain types. No command
returns unrestricted database dictionaries or raw SQL rows.
