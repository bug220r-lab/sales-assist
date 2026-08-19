# Codex Launch Prompt — Synthetic Sales Assist v0.1

Build a new, standalone, synthetic-only proof of concept implementing the Sales Credit and DOI
business specifications contained in this repository.

This is a fresh implementation in an empty repository. Do not inspect, copy, import, or continue
any prior source repository or Git history.

## Read first

Before making any repository change:

1. read `AGENTS.md`;
2. read `specs/SPEC_INDEX.md`;
3. inventory every file under `specs/` and `reference/`;
4. calculate SHA-256 for every supplied specification file;
5. report any unreadable file or binding business-rule contradiction.

The curated files under `specs/` govern. `reference/` is sanitized supporting detail.

## Objective

Create a functioning local system proving this workflow:

```text
Synthetic Interaction Queue / Synthetic Order Portal
                        ↓
          Localhost-only Chrome extraction or API input
                        ↓
              Python validation and normalization
                        ↓
               Sales Credit or DOI rule engine
                        ↓
           Deterministic result, reasons, and explanation
                        ↓
                SQLite history and telemetry
                        ↓
                   Local dashboard
```

## Hard boundaries

- Synthetic data only.
- No real organization, customer, employee, order, product, communication, or source record.
- No production system, domain, URL, route, selector, API, credential, cookie, token, session,
  database, browser storage, or captured HTML.
- No file access outside this repository.
- Runtime networking is loopback-only.
- Chrome host permissions are limited to `http://127.0.0.1/*` and `http://localhost/*`.
- No portal write, mutation, submit, generic request, arbitrary click, or external action capability.
- Every executable identity must satisfy `specs/synthetic_data_policy.md`.
- Every safety counter in that file must remain zero.

## Engineering doctrine

Implement the business logic exactly as specified.

Codex owns normal internal engineering choices, including module organization, class/DTO
structure, physical SQLite design, indexes, migrations, transaction mechanism, locking,
repositories, test organization, and frontend components.

Create ADRs for consequential persistence, concurrency, replay, privacy, canonical-hash,
migration, and extension-security decisions.

Stop only when two binding specifications would produce different business results or protected
semantics. Do not stop for ordinary implementation choices.

## Recommended stack

Use a lightweight local stack unless an equivalent is clearly better:

- Python 3.12+
- FastAPI
- Pydantic
- SQLite with foreign keys enabled
- versioned migrations
- pytest
- structured JSON logging
- lightweight HTML/CSS/JavaScript
- Chrome Manifest V3

Do not use Electron, a local AI model, or GPU-only dependencies.

## Milestone 0 — Repository and safety foundation

Create:

- `pyproject.toml`;
- repository package structure;
- project README;
- formatter/linter/type-check baseline;
- test harness;
- synthetic identity firewall;
- prohibited-input scanner;
- secret scanner;
- localhost-only runtime guard;
- Chrome manifest safety test;
- structured logging foundation;
- initial migration framework;
- initial Git repository and commit.

Milestone 0 tests must prove:

- no production hostname or company identifier exists;
- no non-loopback runtime destination is accepted;
- no non-localhost Chrome permission exists;
- no credential-like material is committed;
- no executable non-synthetic identity exists;
- no external system call is required;
- all supplied JSON specifications parse;
- reason registry count is 138;
- reason ownership count is 138;
- transition count is 115.

Do not implement Milestone 1 or later during the first run.

At the end of Milestone 0 report:

- branch;
- commit and tree;
- exact created-file inventory;
- specification inventory and hashes;
- test commands/results;
- scanner results;
- extension/network permission inventory;
- any binding contradiction.

Stop after Milestone 0.

## Future Milestone 1 — Shared domain engine

After explicit continuation, implement:

- synthetic typed IDs;
- canonical timestamps;
- exact Money and Quantity;
- canonical JSON and versioned hashes;
- observed tagged values;
- snapshots;
- evaluations;
- reasons and transitions;
- evidence;
- human-review records;
- immutable events;
- idempotency and structured errors.

Every evaluation explains supplied facts, rules evaluated, rules fired, reasons, result, human
review, versions, and persistence effects.

## Future Milestone 2 — Sales Credit rule pack

Implement the files under `specs/sales_credit/`.

Required areas include review windows, dual-identifier discovery, order deduplication, target-rep
classification, pre-order evidence, cancellation/replacement, exact product continuity, placed
value/material changes, human outcomes, case identity, closure minimization, retention, and
metrics.

Every branch receives real executable synthetic tests.

## Future Milestone 3 — DOI rule pack

Implement the files under `specs/doi/` and `specs/shared/`.

Required areas include ingestion/run state, extraction and completeness, direct ship, fulfillment
split, partial quantity, payment, closures, uncertainty containment, alternate products, contact,
WWC, DEDUPE, opportunity scope, interventions, resulting orders, value/KPI, retention, and
purge.

Every reason and ownership reference must resolve to a real executable test. Do not preserve
stale test counts artificially.

## Future Milestone 4 — SQLite persistence

Design the physical schema while preserving logical invariants:

- append-only immutable facts/history;
- rebuildable projections;
- foreign-key integrity;
- exact replay idempotency;
- conflicting replay rejection;
- transaction atomicity;
- concurrency correctness;
- retention and purge;
- no unauthorized tombstone or identifying survivor;
- backup and restore.

## Future Milestone 5 — Synthetic portal and generator

Build a generic localhost order-management portal and deterministic synthetic scenario generator.

Example route:

`http://127.0.0.1:8080/orders/SYN-ORDER-000001`

The portal must not copy a real interface. It must expose only fictional facts and a completeness
marker sufficient for the localhost adapter.

## Future Milestone 6 — Chrome extension

Build a Manifest V3 extension limited to localhost.

It reads only allowlisted synthetic fields, verifies completeness, sends structured JSON to the
local API, and displays the returned result and explanation.

No mutation controls, generic automation, production selectors, or non-localhost permission.

## Future Milestone 7 — Dashboard and telemetry

Show processing history, classifications, reasons, evidence, human-review queue, failures,
versions, database health, latency, throughput, replay/conflict counts, and safety counters.

## Future Milestone 8 — Verification and packaging

Run unit, contract, integration, persistence, concurrency, rollback, browser, safety, backup,
restore, and performance tests.

Benchmark at least 1,000 and 10,000 synthetic orders. Report duration, median/P95 latency,
throughput, peak memory, and database size.

## Checkpoint policy

After each future milestone:

1. finish every candidate-tree-generating file;
2. record the candidate tree;
3. run scoped tests;
4. run the complete available regression suite;
5. run synthetic identity, prohibited-input, localhost-only, and secret scans;
6. commit only when all pass on the same tree;
7. verify the commit tree equals the gated tree.

Do not create release tags unless explicitly requested.

## Completion statement

The only valid final statement is:

```text
SYNTHETIC_SALES_ASSIST_V0_1 =
FUNCTIONAL_PROOF_OF_CONCEPT_COMPLETE
```

Do not claim validation or readiness for any real organization or production workflow.
