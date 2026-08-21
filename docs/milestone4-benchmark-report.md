# Milestone 4 persistence benchmark baseline

- Benchmark version: `synthetic-sales-assist-milestone4-benchmark/v1`
- Run date: 2026-08-21
- Storage: isolated local SQLite database outside the repository
- Unique persisted evaluations: 1,000
- Exact replays: 100
- Sampled order/case/run history queries: 75
- Verification: persisted metrics aggregation plus online backup and backup verification

The workload cycled the six valid durable demonstration aliases across both rule packs. It used a
unique bounded request key for every initial evaluation, replayed the first 100 keys exactly,
queried 25 result groups, aggregated persisted telemetry, created a SQLite online backup, and
verified the backup receipt, digest, schema, row summary, quick check, and foreign keys. The total
duration and throughput include all of those steps.

## Measurements

| Measurement | Result |
|---|---:|
| Total duration | 249.448144600 seconds |
| Median end-to-end duration | 226.490150 ms |
| P95 end-to-end duration | 545.652600 ms |
| Median database duration | 122.692500 ms |
| P95 database duration | 183.573600 ms |
| Throughput | 4.409734 calls/second |
| SQLite database size | 78,577,664 bytes |
| Peak traced Python memory | 4,427,992 bytes |
| Verified backup SHA-256 | `d2b30ebd3dc7daad6ccec65b46f1e6836a6463e5669a89beee02c8fb37ed073d` |

## Persisted result counts

| Dimension | Value | Count |
|---|---|---:|
| Rule pack | DOI | 666 |
| Rule pack | Sales Credit | 334 |
| Result | `CREDIT_CONFIRMED_TARGET_REP` | 167 |
| Result | `MANUAL_REVIEW_REQUIRED` | 167 |
| Result | `DOI_OPPORTUNITY` | 333 |
| Result | `DOI_EXCLUDED` | 167 |
| Result | `DOI_MANUAL_REVIEW` | 166 |

## Safety counters

All persisted benchmark snapshots remained zero:

| Counter | Value |
|---|---:|
| `EXTERNAL_MUTATION_REQUEST_COUNT` | 0 |
| `EXTERNAL_PRODUCTION_SYSTEM_ACCESS_COUNT` | 0 |
| `NON_LOCALHOST_RUNTIME_REQUEST_COUNT` | 0 |
| `NON_SYNTHETIC_FIXTURE_COUNT` | 0 |
| `PRODUCTION_MUTATION_REQUEST_COUNT` | 0 |
| `PRODUCTION_SYSTEM_ACCESS_COUNT` | 0 |
| `REAL_CUSTOMER_DATA_COUNT` | 0 |
| `REAL_CUSTOMER_IDENTITY_COUNT` | 0 |
| `SECRET_MATERIAL_COUNT` | 0 |

This is the Milestone 4 baseline for later milestone comparisons. The rule pack sets no fixed
performance threshold; regression evaluation should compare like-for-like durable workloads and
must never trade away replay, integrity, retention, or safety enforcement for throughput.
