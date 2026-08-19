
# Telemetry and System Health

## Per-processing timing

Record monotonic duration for:

- source extraction;
- schema validation;
- normalization;
- rules evaluation;
- database transaction;
- total processing.

## Health and performance aggregates

At minimum report:

- records/orders processed;
- successful, failed-closed, and human-review counts;
- median and P95 latency;
- throughput;
- replay and conflict counts;
- database errors;
- backup/restore status;
- rule-pack and schema versions;
- peak memory during benchmarks;
- database size.

## Safety counters

These must remain zero:

```text
EXTERNAL_PRODUCTION_SYSTEM_ACCESS_COUNT
EXTERNAL_MUTATION_REQUEST_COUNT
NON_LOCALHOST_RUNTIME_REQUEST_COUNT
REAL_CUSTOMER_DATA_COUNT
SECRET_MATERIAL_COUNT
```

Any nonzero value is a critical health failure and blocks milestone commit.

## Correctness telemetry

Performance is separate from correctness. Persist the evidence needed to explain:

- supplied facts;
- completeness status;
- rules evaluated;
- rules fired;
- reasons;
- top-level result;
- opportunities;
- human-review requirement;
- persistence effects;
- rule-pack version.

Human outcomes remain separate from system results so agreement and disagreement can be
measured without redefining ground truth.
