
# Sales Credit Retention and Metrics

## Closure

Closure writes and verifies a minimized ClosedAuditRecord, removes disallowed active data, and
commits atomically.

## Retention

The minimized record expires 90 days after `closed_at` in the simulated clock. Purge runs on
startup and at least daily, is idempotent, and retains only aggregate diagnostics that contain no
customer identity.

## Outcome metrics

Permitted metrics include:

- case volume;
- time to review;
- percent routed to human review;
- system/human agreement;
- false automatic-confirmation count;
- processing latency;
- fail-closed rate.

System classification and human outcome are separate. Metrics may not reintroduce contact
identity or raw communications.
