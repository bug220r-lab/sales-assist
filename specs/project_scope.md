
# Project Scope

## Purpose

Build a complete local proof of concept showing that the supplied Sales Credit and DOI
workflows can be implemented as deterministic Python rule packs with SQLite persistence,
a synthetic localhost order portal, a localhost-only Chrome extension, a dashboard, and
operational telemetry.

## Included

- Synthetic Interaction Queue intake.
- Synthetic order and line snapshots.
- Sales Credit review windows, attribution, evidence, cancellation/replacement, value,
  workflow, human outcome, minimization, and retention behavior.
- DOI ingestion, extraction, deterministic evaluation, opportunities, alternates, contact,
  WWC, DEDUPE, interventions, value/KPI, lifecycle, retention, and purge behavior.
- SQLite persistence, migrations, idempotency, concurrency, rollback, backup/restore.
- Synthetic portal, localhost API, localhost-only Chrome extension, dashboard, and tests.

## Excluded

- Any real organization, customer, employee, order, product, message, workbook, or source system.
- Any production URL, route, selector, API, credential, cookie, token, session, or database.
- Customer messaging or automated external action.
- A claim that the proof of concept is validated for a real workflow.

## Permanent source safety rule

The Synthetic Order Portal is read-only from the rule engine and extension. The program may
read and extract fictional facts. It must not create, modify, submit, or delete portal data
through the extension or adapter. This is enforced by absence of write capability.

## Architecture

```text
Synthetic Interaction Queue / Synthetic Order Portal
                        ↓
             Localhost-only extraction
                        ↓
             Validation / normalization
                        ↓
          Sales Credit or DOI rules engine
                        ↓
             SQLite event/audit history
                        ↓
            Dashboard / telemetry / review
```

## Success criteria

The proof of concept is complete only when both rule packs execute deterministically,
malformed input fails safely, retries are idempotent, concurrent operations preserve
invariants, telemetry is retained, browser permissions remain localhost-only, and every
executable identity is synthetic.
