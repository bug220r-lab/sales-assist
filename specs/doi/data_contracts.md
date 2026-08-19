
# DOI Data Contracts

The physical database layout is Codex-owned. These logical entities and invariants are binding.

## Source/run graph

- Source batch
- Run projection and immutable run events
- Source-import attempt and immutable attempt events
- Staged order
- Rejected source record
- Source/run identity references
- Nonidentifying source-import aggregate

## Case and extraction graph

- Order case
- Case/source binding and admission proof
- Run work item
- Extraction attempt
- Order snapshot
- Line-item snapshot
- Order lifecycle event

## Evaluation and opportunity

- Evaluation with exact snapshot/rules/input/output/full-record hashes
- Relationship-revision bindings
- Observation bindings
- Human-fact bindings and usage kind
- Opportunity
- Opportunity scope components

## Product knowledge and human state

- Alternate relationship and immutable revisions
- Action Context and events
- Alternate observations
- Human facts and corrections
- Contact, DEDUPE, attention, and WWC event histories

## Result, evidence, and intervention

- Resulting-order searches, links, events, revisions, and mapping components
- Logical evidence keys
- Verification evidence and proof references
- Interventions
- Action-verification and value events
- Occurrence guards

## KPI

- Retained per-intervention contribution
- Nonidentifying aggregate daily bucket

## Invariants

- Snapshots, evaluations, events, evidence, and revisions are append-only.
- Mutable projections are rebuildable from immutable history.
- Exact replay is idempotent.
- Same logical key with different material effect fails closed.
- Every hash-bearing object has a closed canonical preimage.
- Every source reference is privacy-closed.
- No entity grants a portal write capability.
