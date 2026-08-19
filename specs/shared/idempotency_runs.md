
# Idempotency, Runs, and Concurrency

## Run status

```text
IN_PROGRESS
COMPLETED
COMPLETED_WITH_EXCEPTIONS
FAILED
```

Only the governed terminal transitions may leave IN_PROGRESS. A terminal run never returns to
IN_PROGRESS.

## Command processing

For every accepted command:

1. validate closed shape and version;
2. compute natural key and full canonical token;
3. look up retained receipts before allocating IDs or timestamps;
4. compare canonical preimages;
5. return the prior result on exact replay;
6. reject same-key/different-material conflicts;
7. acquire the required transaction/lock boundary;
8. validate current-state guards;
9. append atomically.

## Explicit failed-source finalization

The only no-retry finalization command is:

`FINALIZE_FAILED_SOURCE_IMPORT_NO_RETRY`

It is an explicit accepted human action. There is no timeout, retry-window expiry, background
worker, automatic failure, or implicit branch.

A terminal failed source attempt leaves its parent review run IN_PROGRESS until either:

- a legal next-ordinal retry commits; or
- the explicit no-retry command commits.

Commit order under one shared run-control boundary determines the winner. Both cannot commit.

## Work versus disposition subjects

`W(run)` contains all accepted work items.

`D(run)` contains only subjects that reached a governed order-disposition boundary or an
explicit pre-portal order block/no-work conflict.

Every member of `D(run)` has exactly one terminal disposition class. A systemic pre-read
failure may retain one work item while contributing zero disposition subjects and zero
disposition counts.

## Rules unavailable

RC-084 is legal at:

- the evaluation rules-version gate; and
- a pre-extraction systemic run gate when a valid run exists but required rules become
  unavailable before extraction reservation.

The run-level branch appends no evaluation, performs zero portal reads, records zero order
dispositions, and terminalizes the run FAILED through the governed run-failure route.

## Concurrency

Extraction-occurrence reservation and pre-read systemic terminalization must share one
serializable run-control boundary or equivalent compare-and-set. Tests cover both commit
orders, exact replay, rollback, and crossed races.
