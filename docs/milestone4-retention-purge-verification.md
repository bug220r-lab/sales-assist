# Milestone 4 retention and purge verification

## Sales Credit

Closure writes and verifies the minimized closed audit representation and removes active-only
contact, snapshot, line, evidence, note, and replay material in one transaction. Eligibility is
the exact elapsed boundary `closed_at + 90 * 24 hours`. Purge is idempotent; a fault before commit
leaves the complete prior representation.

## DOI

Hard and governed reversible closures retain the exact calendar-90 deadline, timezone, policy,
and timezone-database bindings. Reopen cancels only its exact active reversible deadline. Hard
closures never reopen.

DOI purge reconciles current intervention contributions, transfers them exactly once to
currency-segmented identity-free daily buckets, and deletes the complete case-owned graph and
receipts in the same transaction. A residual scan rejects any surviving case, order, link,
identity-bearing canonical material, or drill-through digest. Absence is success; no purge
tombstone is created.

Deterministic tests inject failures during KPI finalization and graph deletion, restart and retry,
race two purge callers, and verify `quick_check`, `foreign_key_check`, projection consistency, and
the exact survivor inventory after every outcome.

## Backup artifacts

Every verified backup receipt carries the earliest governed identity deadline represented in its
image, conservatively bounded to 89 days when no earlier deadline exists. Restore rejects at the
exact expiry instant. Managed cleanup at that same boundary directly unlinks the database before
its receipt and creates no alternate identity-bearing path. It preserves the pair on pre-unlink
fault, completes receipt cleanup forward after unlink, removes a hard-exit orphan receipt on
retry, and treats complete absence as a no-op. Tests cover the nanosecond before/exact boundary,
restore rejection, both fault directions, orphan-sidecar retry, absence of `.expired` database
artifacts, and directory-wide cleanup. Directory cleanup also removes only strictly UUID-named
backup `.tmp` and legacy `.previous` crash remnants, deleting identity-bearing files before
nonidentity receipt metadata and recovering a matching prior receipt when an overwrite stopped
before its database replacement.
