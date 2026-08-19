
# Sales Credit Acceptance Tests

Create real executable synthetic tests for every row below.

## Schema and normalization

- required/optional/conditional fields;
- timezone-aware timestamps and precision;
- exact decimal money;
- email trim/case behavior;
- valid synthetic phone normalization;
- malformed phone rejection;
- no guessed identifiers.

## Windows

- interaction date included;
- fourteen full calendar days after;
- DST boundaries;
- same-day timing uncertainty;
- cancellation replacement-window extension;
- once-per-local-day recheck and explicit force recheck.

## Discovery

- both email and phone searched;
- complete result-set combination;
- Order Number deduplication;
- no early exit after one candidate;
- incomplete enumeration blocks no-order conclusion.

## Rules

- both target-rep literals;
- unassigned-web evidence route;
- every other-rep and missing-rep branch;
- every contact-evidence class;
- canceled and replacement branches;
- exact ES and exact MFG/OE continuity;
- non-exact substitute human review;
- material changes;
- placed-value unavailable without estimation.

## Case identity

- multiple interactions attach to one case;
- totals and human outcomes are not duplicated;
- exact replay returns the same logical result;
- conflicting replay fails safely.

## Retention

- transactional closure minimization;
- active detail removed at closure;
- no contact identity retained;
- 90-day boundary;
- idempotent purge;
- temp/backup cleanup.

## Safety

- no portal write API;
- no non-localhost request;
- no write-control activation;
- malformed portal page fails closed;
- secret/session persistence remains zero.
