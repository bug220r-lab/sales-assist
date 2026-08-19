
# Privacy, Minimization, Retention, and Deletion

## General

The database is workflow/audit state, not a customer CRM or a copy of a source system.
Synthetic fixtures contain no real identity.

## Sales Credit closure

While a case is active, the synthetic proof may retain the fictional facts necessary to test the
workflow. Closure is transactional:

1. write a minimized closed audit record;
2. verify it;
3. remove disallowed active detail;
4. commit atomically.

The minimized record retains the case/order references, timestamps/precision, final
classification, evidence metadata, human outcome, versions, and concise synthetic notes.
It excludes full contact values, full snapshots, line details, raw notes, and message content.

Closed Sales Credit records expire 90 days after `closed_at` in the simulated retention clock.

## DOI retention

DOI detailed identity follows the calendar-90 policy in `America/New_York`, with exact policy
and timezone-database bindings. Reversible closure may cancel the exact retained deadline only
through a valid reopen transition. Hard closure cannot reopen.

Purge is atomic:

- finalize any permitted nonidentifying KPI aggregate;
- delete the complete case graph;
- leave no case/order tombstone, reversible identity hash, or drill-through reference;
- roll back both finalization and deletion on any mismatch.

Source-attempt and rejected-source identity have their own governed retention roots. Only the
explicitly allowed nonidentifying aggregates may survive.

## Logs and exports

Never log or export fictional contact values, note bodies, credentials, sessions, or unrestricted
source text. Temporary files, backups, and test artifacts follow the same minimization policy.
