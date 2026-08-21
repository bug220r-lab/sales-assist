# ADR 0020: Retention and identity-graph deletion

- Status: accepted for Milestone 4
- Scope: executable Sales Credit and DOI minimization and purge transactions

## Decision

Sales Credit closure creates and verifies the minimized audit record, changes the case projection,
and deletes disallowed active contact, snapshot, line, evidence, and replay material in one
transaction. Its elapsed 90-day purge removes the remaining identity root while updating only
identity-free diagnostics.

DOI closure stores the exact calendar-90 deadline with the governing timezone and policy
bindings. A reversible reopen cancels only its exact active deadline; hard closure cannot reopen.
Case purge first reconciles and transfers every current KPI contribution into a currency-segmented,
identity-free daily bucket, then deletes the entire case-owned graph and owned receipts in the same
transaction. No case, order, link, reversible digest, or durable purge tombstone survives. A retry
against an absent graph is an idempotent no-op.

Source attempts, rejected source records, and managed backups retain their separate governed roots.
Secure deletion and WAL checkpointing reduce residual local pages after committed destructive
maintenance but do not substitute for relational graph deletion and survivor scans.

## Consequences

Every injected failure leaves either the complete pre-operation graph or the complete authorized
survivor state. Aggregate rows cannot drill back to a case. Concurrent purge attempts transfer a
contribution at most once. Retention changes neither Sales Credit classification nor DOI outcomes.
