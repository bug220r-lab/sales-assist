# Milestone 4 CLI reference

Invoke the local synthetic CLI with:

```powershell
python -m synthetic_sales_assist.cli [--data-dir PATH] [--json] COMMAND
```

Required commands:

```text
doctor
db init
db status
db verify [--deep]
db backup <path> [--overwrite]
db restore <path> --confirm
db purge-expired-backups [<path>]
demo list
demo run <alias> [--request-key <bounded-key>]
order show <synthetic-order-id>
case history <synthetic-order-id> [--limit N]
  [--after-sequence N --through-sequence N --through-event-id <synthetic-evidence-id>]
run show <synthetic-run-id>
metrics summary
```

JSON mode returns one closed, sorted-key envelope containing schema version, command, success,
result, and closed error codes. Inspection commands return fictional privacy-safe audit views;
they never dump raw rows, unrestricted notes, contact values, credentials, or canonical payloads.

Sales Credit history returns at most 1,000 events (default; `--limit` accepts 1..1,000).
The summary includes `event_count` for the captured prefix, `returned_event_count`,
`after_sequence`, `through_sequence`, `through_event_id`, `has_more`, and `next_after_sequence`.
Events include
their immutable `sequence`. To continue, supply the returned next-after and the original
through-sequence and through-event-id; repeat until `has_more` is false. The two endpoint
fields must be supplied together. Later appends remain outside that prefix.
The summary state is the final state at the captured endpoint. Cursors cannot retain purged
data. Invalid/stale cursors fail closed. DOI keeps its existing reduced CLI projection and
does not support Sales Credit sequence continuation. Browser/API history contracts are unchanged.

Before database initialization, `doctor` still reports the exact nine named zero safety counters
and labels their source `CLOSED_BASELINE_DATABASE_NOT_INITIALIZED`. After initialization it reports
the persisted database counters. `db purge-expired-backups` removes due backup/receipt pairs from
the managed directory; its optional path form applies the same local-path and exact-expiry policy
to one explicitly selected backup.

Demo aliases are `sales-credit-target-rep`, `sales-credit-human-review`,
`doi-fulfillment-split`, `doi-full-ds`, `doi-manual-review`, `doi-overlap`, and
`malformed-input`. Each maps to an existing collected synthetic scenario. The malformed alias
fails validation before rule execution and persists only a sanitized failure receipt and
telemetry code.
