
# Specification Index

## Project

`Synthetic Sales Assist v0.1`

## Authority order

1. `project_scope.md`
2. `synthetic_data_policy.md`
3. `advisory/approved_product_decisions.md`
4. `advisory/pre_milestone0_reconciliation_v1.0.1.md`
5. `shared/` contracts
6. `sales_credit/` business specifications
7. `doi/` business specifications
8. `advisory/known_audit_findings.md` as mandatory implementation acceptance criteria
9. Codex ADRs for bounded internal engineering decisions
10. `reference/` supporting documents

## Interpretation rules

- Business outcomes must preserve the supplied Sales Credit and DOI logic.
- Only fictional synthetic records may be executable.
- No production-system access is permitted.
- Unknown or incomplete facts block only conclusions that depend on them, unless the
  specification requires complete-snapshot failure.
- Extraction/observation is factual; interpretation belongs to the rules engine.
- Human outcomes remain separate from system classifications.
- Audit findings are mandatory implementation tests, not permission to change business logic.
- When two binding files conflict on business behavior, stop and cite both.
- When files differ only on internal implementation, choose the simplest sound design,
  document it in an ADR, and prove it through tests.
- Filenames and modification timestamps never establish precedence.
- Every reason, transition, selector, and oracle reference must resolve exactly.

## Binding file inventory

| File | Role |
|---|---|
| `project_scope.md` | Product boundary and proof-of-concept definition |
| `synthetic_data_policy.md` | Executable identity, privacy, and network firewall |
| `shared/primitive_types.md` | Common identifiers, canonical JSON, hashes, money |
| `shared/timestamps.md` | Timestamp semantics and canonicalization |
| `shared/money_quantity.md` | Exact money and quantity behavior |
| `shared/normalization.md` | Order, ES, MFG/OE and edge-trim behavior |
| `shared/observed_values.md` | KNOWN/UNKNOWN/NOT_APPLICABLE tagged values |
| `shared/whole_order_completeness.md` | Snapshot completeness proof |
| `shared/idempotency_runs.md` | Run, command, replay, and concurrency semantics |
| `shared/privacy_retention.md` | Minimization, retention, deletion, and safety |
| `shared/telemetry.md` | Performance, health, safety, and business metrics |
| `sales_credit/business_rules.md` | Sales Credit deterministic behavior |
| `sales_credit/data_contracts.md` | Sales Credit logical models |
| `sales_credit/workflow_states.json` | Closed Sales Credit workflow states |
| `sales_credit/acceptance_tests.md` | Required synthetic Sales Credit tests |
| `sales_credit/retention_and_metrics.md` | Closure, human outcome, and metrics |
| `doi/business_rules.md` | DOI precedence and core rules |
| `doi/data_contracts.md` | DOI logical models |
| `doi/reason_registry.json` | Closed 138-reason registry |
| `doi/reason_ownership.json` | Closed ownership and test obligations |
| `doi/state_transitions.json` | Closed 115-transition registry |
| `doi/lifecycle_contract.md` | Event/projection and closure lifecycle |
| `doi/run_ingestion_contract.md` | Synthetic queue ingestion and run machines |
| `doi/alternate_products.md` | Exact SKU, exact MFG, cross-reference, supersession, functional alternates |
| `doi/contact_wwc_dedupe.md` | Contact, WWC, DEDUPE and attention behavior |
| `doi/interventions_kpi.md` | Opportunity scope, intervention, verification, resulting-order, and KPI logic |
| `doi/acceptance_tests.md` | Required DOI synthetic and persistence tests |
| `doi/synthetic_test_catalog.md` | Test-family inventory and real-selector rule |
| `advisory/approved_product_decisions.md` | User-approved semantic decisions |
| `advisory/pre_milestone0_reconciliation_v1.0.1.md` | Closed reconciliation of TR-004/TR-100 and RC-084 |
| `advisory/known_audit_findings.md` | Mandatory implementation closure items |
| `advisory/implementation_doctrine.md` | Bounded engineering discretion |
