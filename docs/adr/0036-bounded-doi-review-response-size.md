# ADR 0036: DOI-specific 4 MiB review-response bound

The previous 512 KiB response bound rejected a valid local capture pair after
CSV parsing. Input limits alone cannot predict output size: the closed review
projection adds evidence references, classifications and repeated JSON keys.

Use one 4 MiB constant for the DOI serializer, the narrowly scoped HTTP transport
override (state/load/clear only), and the frontend's bounded stream reader.
The generic portal limit remains 512 KiB. CSV inputs remain 1 MiB and 5,000
records per file, 500 joined orders and 8 MiB maximum JSON request body. The
frontend counts streamed bytes before parsing and cancels oversized streams;
Content-Length is an early rejection only, never the sole bound.

This is an eightfold finite expansion for the larger closed projection, not an
unbounded response or a promise that every possible hostile input fits. A
synthetic 500-order/5,000-detail shape under both input-byte limits must pass
HTTP and frontend tests. Keep output field limits, schema validation, source
minimization, order/record limits, authorization, TTL and persistence unchanged.
The raw stream plus one joined buffer is bounded to about 8 MiB; decoded text,
objects and DOM add overhead, which is measured separately. Chrome visual QA
is distinct from a DOM-harness rendering/performance check.

Over-limit responses remain rejected. Existing failed-load behavior clears the
transient displayed review; durable evidence-bound checkboxes remain unchanged.
The error message distinguishes those states and recommends smaller matching
pairs for captures that still exceed the bound. Large files are never silently
truncated and no capture facts are omitted to meet a size limit.

Executable checks: tests.test_doi_response_limit, existing DOI HTTP/ownership/
marker/workday tests, and the separate localhost frontend boundary harness.
Customer capture validation stays outside this synthetic source package.
