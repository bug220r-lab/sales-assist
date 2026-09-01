# Milestone 7 dashboard API contract

All endpoints use the existing `synthetic-sales-assist-api/v1` response envelope. POST bodies carry
the existing `synthetic-sales-assist-api-request/v1` request version plus an action-specific closed
schema. Unknown members, wrong types, overlong values, duplicate JSON keys, noncanonical synthetic
IDs, or wrong versions fail closed.

Dashboard JSON GETs pass through the same route-specific closed shape/value validator as their
HTML page. Unknown response members, wrong subject bindings, or a route/view mismatch therefore
fail closed before serialization. The evidence inventory has its own exact four-member contract.

## Shared mutating-action members

Every human or backup-creation action body contains exactly:

- `schema_version` — the exact action schema;
- `request_schema_version` — `synthetic-sales-assist-api-request/v1`;
- `request_key` — 1–96 printable bounded ASCII characters;
- `confirmed` — literal `true`;
- action-specific closed members.

Human actions also require an exact reserved actor `SYN-REP-*`. They return a closed result with
`status` (`RECORDED`, `EXACT_REPLAY`, or safe conflict envelope), `command_id`, `recorded_at`, and
`replayed`. Changed material under the same natural request key returns HTTP `409` without mutation.
The success receipt also contains the exact route-bound synthetic subject, the result schema, and
an evaluation ID only for DOI selection. Unknown members and a mismatched subject/evaluation fail
closed. Deep-verification and backup-action results likewise use exact route-specific schemas.

Native queue GET forms may submit exactly empty `q=` and `state=` fields; those two values alone
normalize to absent filters. Empty sort, direction, page, page size, presentation, or time-window
values remain invalid, as do duplicate or unknown members.

## Sales Credit manager outcome

Schema `synthetic-sales-assist-manager-outcome-request/v1` admits outcome `APPROVED`, `DENIED`,
`PARTIAL`, `OTHER_REP`, or `NOT_PURSUED`. `PARTIAL` alone requires exact canonical amount and one
registered currency. The system classification object is not an input and remains unchanged.

## DOI overlap scenario selection

Schema `synthetic-sales-assist-doi-scenario-selection-request/v1` admits one current case ID and an
ordered, nonempty set of current overlapping opportunity IDs belonging to that case. The atomic
adapter records the committed structured human fact and selected reevaluation through existing
authorities. It cannot clear an unrelated cause or create an intervention, resulting link, or value.

## Maintenance

Deep verification is an explicit read-only click with a closed version-only body; it has no
idempotency key because it records no business outcome. Backup creation requires explicit
confirmation and a request key. Backup output contains a synthetic receipt ID, canonical time,
schema, hash, and privacy-safe location class; no absolute path is returned. Restore and reset are
not dashboard API routes.

All POSTs retain the exact same-origin Host/Origin/CSRF controls. GETs are loopback-only and
credential-free. Safe errors contain a closed code and generic local message, never a traceback,
SQL, raw payload, username, or filesystem path.

Detail responses are bound to their route context after closed-shape validation: Sales Credit
must return the requested synthetic order, DOI must return the requested synthetic case, and
audit must return the requested subject kind and ID. A different but otherwise valid synthetic
subject fails closed for both HTML and JSON instead of being emitted on the wrong URL.

## Read-only operational metadata

`/api/v1/dashboard/system` and `/api/v1/dashboard/system/telemetry` expose only closed,
privacy-safe operational summaries. Both include explicit UTC observation times for database
verification and the nine safety counters. System state includes the most recent restore receipt
as receipt ID, completion time, source-backup SHA-256, pre-restore backup receipt ID, schema,
status, and safe error code only. Recent errors contain exactly code, category, retryable, and UTC
time; raw payloads, SQL, tracebacks, commands, and paths are never returned.

“Latest verified backup” has a strict meaning: the newest receipt with `COMPLETED` status,
non-null completion time and SHA-256, `quick_check=ok`, and `foreign_key_check=ok`. A newer
`STARTED` or `FAILED` receipt can appear truthfully in `/system/backups`, but cannot replace this
verified summary.

Telemetry includes database-error request count, closed request/Sales Credit/DOI result
distributions, current database size, latest verified backup, latest restore, and observation
times. The fixed comparison reference is
`synthetic-sales-assist-milestone4-benchmark/v1`: 1,000 unique evaluations, 100 exact replays,
226.490150 ms median, 545.652600 ms P95, 4.409734 calls/second, 78,577,664 database bytes, and
verified backup SHA-256
`d2b30ebd3dc7daad6ccec65b46f1e6836a6463e5669a89beee02c8fb37ed073d`. It is labeled as a
committed baseline, never a live measurement. The telemetry page explicitly displays the signed
current database-byte delta from that fixed reference.
