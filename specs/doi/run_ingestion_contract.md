
# DOI Synthetic Queue Ingestion and Run Contract

## Synthetic source

The proof uses a local synthetic DOI queue. It contains fictional Order Numbers and a synthetic
assignee field. No workbook, cloud document, employee name, or production connector is used.

## Assignee classification

The in-scope assignee is `TARGET_REP`. Classification is byte-deterministic, using the shared
ASCII_FOUR edge trim and explicit ASCII case handling. Confusables and unsupported Unicode fail
closed.

## Coherent read

A read must bind its source identity, schema/mapping version, structural anchors, finite extent,
before/after revision evidence or content digests, and privacy-safe counts. Change during read
fails the current attempt.

## Duplicates and conflicts

- Duplicate in-scope rows with the same exact canonical Order Number merge into one staged
  order and preserve source references.
- The same Order Number assigned to the target rep and a nonblank other rep is rejected with no
  work item or portal read.
- Malformed source schema fails the attempt before executable work.

## Run types

- `RUN_DOI_REVIEW`
- `RECHECK_ORDER`
- `RECHECK_DEDUPE_ORDER`

Review runs use source-import attempts. Rechecks create one run work item without a manager
source-import attempt.

## Run results

- COMPLETED: zero order exceptions/blocks.
- COMPLETED_WITH_EXCEPTIONS: one or more order exceptions/blocks; success count may be zero.
- FAILED: a closed run-global fatal gate.

## Failed source attempts

A terminal failed attempt does not automatically fail the run. A human explicitly retries or
accepts `FINALIZE_FAILED_SOURCE_IMPORT_NO_RETRY`.

No timer, expiry, background process, implicit finalization, or automatic failure exists. If neither a retry nor the explicit no-retry command is accepted, the run remains `IN_PROGRESS`.

## Counts

Source, attempt, work-item, disposition, success, exception, blocked, and portal-read counts have
separate equations and owners. `W(run)` and terminal disposition subjects `D(run)` are distinct.
A systemic pre-read failure can have one work item and zero disposition counts.
