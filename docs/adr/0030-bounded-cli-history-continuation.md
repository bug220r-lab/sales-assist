# ADR 0030: Bounded CLI history continuation

Status: accepted for the M8 corrective successor.

The 10,000-call measurement exposed a valid persisted Sales Credit history that exceeded
the CLI AuditView response ceiling of 1,000 events. The two Sales Credit demo aliases share
one fixture order; DOI demo orders vary by alias and request key. Accepted commands must
not make retained history inaccessible. Increasing the response ceiling or silently slicing
the history would weaken the safety bound or conceal events.

Keep the existing complete history service for internal consumers. Add a separate read-only
repository/service query for the CLI with a sequence cursor, a 1..1,000 page size, and a
captured through-sequence and endpoint event ID. SQLite counts, captures the endpoint/state,
and reads at most
limit+1 rows in one read transaction using the existing order/sequence index. Later appends
cannot enter subsequent pages of the captured prefix. The endpoint ID detects closure's
sequence reset and purge/reuse with a different retained endpoint. Missing or changed endpoints
and invalid cursors fail closed;
this cursor does not preserve data against authorized retention or purge.

The CLI exposes total and returned event counts, sequences, captured endpoint, has-more,
and next-after-sequence. Its existing envelope is unchanged. The state describes the last
event of the captured prefix, not the last event on the current page. DOI's existing reduced
CLI projection remains unchanged; the new continuation is for Sales Credit events only.
No browser/API contract, business outcome, persistent schema, migration, canonical material,
idempotency allocation, retention, or extension permission changes.

`tests.test_m8_history_paging.HistoryPagingTests` exercises the real 1,000/1,001-event
boundary, complete traversal, append-between-pages isolation, closure/purge cursor invalidation,
replay/conflict, predecessor
continuity, projections, invalid values before SQL, and unchanged durable counts on reads.
The workload still counts one bounded history-page read as one query. Its untimed verification
traverses every retained Sales Credit event and checks sequence/identity completeness.

Preserve the failed 0.1.2 workload and all earlier evidence. Ship this correction in application
0.1.3 with unchanged extension 0.1.2, then run the final gate and exact-package measurements
against the successor commit. The earlier passing 1,000-call measurement is historical.
