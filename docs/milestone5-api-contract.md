# Milestone 5 local API contract

- API envelope: `synthetic-sales-assist-api/v1`
- Request body: `synthetic-sales-assist-api-request/v1`
- Application view: `synthetic-sales-assist-application/v1`
- Origin default: `http://127.0.0.1:8765`
- Data classification: reserved synthetic identities and privacy-safe derived results only
- Database schema: `4`

Every object below has an exact member set. Every array is bounded and contains only the
declared item schema. Extra or missing members, wrong exact JSON types, noncanonical values,
wrong synthetic-ID namespaces, and unsupported schema versions fail with HTTP 500 before a
success response is written. Client input failures use their documented 4xx status.

Success envelopes contain exactly `data` and `schema_version`. Error envelopes contain exactly
`error` and `schema_version`; `error` contains exactly `code` and the constant safe `message`.
No response may contain a filesystem path, SQL, canonical preimage, unrestricted metadata,
traceback, exception text, or control token.

## Route and response inventory

| Method | Route | Success | Exact `data` shape |
|---|---|---:|---|
| `GET` | `/health` | 200 or 503 | Health |
| `GET` | `/api/v1/scenarios` | 200 | array of ScenarioDescriptor |
| `POST` | `/api/v1/scenarios/{alias}/instantiate` | 201 | OrderDetail |
| `GET` | `/api/v1/orders` | 200 | array of OrderSummary |
| `GET` | `/api/v1/orders/{order_id}` | 200 | OrderDetail |
| `POST` | `/api/v1/orders/{order_id}/evaluate` | 200 | EvaluationResult |
| `GET` | `/api/v1/orders/{order_id}/history` | 200 | History |
| `GET` | `/api/v1/interactions/{interaction_id}` | 200 | Interaction |
| `GET` | `/api/v1/runs/{run_id}` | 200 | Run |
| `GET` | `/api/v1/metrics/summary` | 200 | MetricsSummary |
| `GET` | `/api/v1/system/status` | 200 | SystemStatus |
| `POST` | `/api/v1/system/shutdown` | 202 | ShutdownAck |

The supported method is part of each route. A known route with another method returns 405 and
an endpoint-specific `Allow`; an unknown path returns 404. No wildcard, debug, database,
filesystem, dashboard, control-center, connector, proxy, websocket, or extension route exists.
Route and method selection precede POST Origin/CSRF authentication, so a wrong method or unknown
path cannot be disguised as an authentication failure. Common Host/header validation remains
mandatory for every request.

Every resource response is context-bound as well as namespace-valid. Instantiate returns the
exact requested scenario alias and variant mode. Order detail, evaluation, and history return the
exact requested order ID. Interaction and run detail return the exact requested interaction or
run ID. The HTML resource routes enforce the same bindings before rendering.

## Exact top-level view members

- **ScenarioDescriptor:** `alias`, `allowed_modes`, `collected_scenario`, `complexity`,
  `description`, `expected_result`, `rule_pack`, `schema_version`.
- **OrderSummary:** `doi_state`, `evaluated`, `human_review_required`, `mode`, `order_id`,
  `order_status`, `relevant_line_count`, `rule_pack`, `sales_credit_state`, `scenario_alias`,
  `schema_version`, `updated_at`.
- **OrderDetail:** every OrderSummary member plus `completeness`, `created_at`,
  `interaction_ids`, `latest_evaluation`, `lines`, `source_status`.
- **EvaluationResult:** `aggregate_potential_status`, `aggregate_potential_value`, `case_id`,
  `closure_state`, `command_id`, `conflict`, `evaluation_id`, `explanation`, `fired_rules`,
  `handling_flags`, `human_review_required`, `opportunities`, `order_id`,
  `processing_duration_ns`, `processing_stages`, `reasons`, `replayed`, `rule_pack`,
  `rule_pack_version`, `run_id`, `scenario_alias`, `schema_version`, `snapshot_id`,
  `top_level_result`, `value`, `value_status`, `workflow_state`.
- **History:** `artifacts`, `attention_causes`, `attempt_receipts`, `conflict_count`, `events`,
  `exact_replay_count`, `intervention_events`, `manager_outcomes`, `order_id`, `receipts`,
  `schema_version`, `telemetry_event_count`, `value_events`.
- **Interaction:** `direction`, `evidence_classification`, `identifier_kind`, `interaction_id`,
  `order_id`, `schema_version`, `target_rep_participation`, `timestamp`,
  `timestamp_precision`.
- **Run:** `completed_at`, `event_count`, `order_id`, `rule_pack`, `run_id`, `run_type`,
  `schema_version`, `started_at`, `status`.
- **MetricsSummary:** `conflict_count`, `database_error_count`, `exact_replay_count`,
  `failed_closed_count`, `human_review_count`, `median_latency_ns`, `p95_latency_ns`,
  `safety_counters`, `schema_version`, `success_count`, `success_rate`,
  `throughput_per_second`, `total_processed`.
- **SystemStatus:** `app_version`, `build_version`, `database_schema_version`,
  `database_status`, `evaluated_count`, `expected_schema_version`, `integrity_check`,
  `migration_status`, `projection_status`, `quick_check`, `registry_capacity`,
  `registry_count`, `safety_counters`, `schema_version`.
- **Health:** every SystemStatus member plus `status`, which is exactly `PASS` or `FAIL`.
- **ShutdownAck:** `status`, which is exactly `SHUTDOWN_ACCEPTED`.

`schema_version` in every application view is exactly
`synthetic-sales-assist-application/v1`. Counts and durations are nonnegative exact JSON
integers; booleans are exact JSON booleans; timestamps are canonical UTC RFC 3339 strings.

## Exact nested view members

- **Money:** `amount`, `currency_code`, `currency_registry_version`, `currency_scale`.
  It must round-trip through the governed Money codec without normalization.
- **Fact:** `reason_code`, `tag`, `value`.
- **Line:** `activity`, `availability`, `drop_ship_state`, `eta`, `line_id`, `line_index`,
  `line_value`, `product_id`, `quantity`.
- **Completeness:** `declared_relevant_line_count`, `fixture_version`, `observed_order_id`,
  `ordered_line_manifest_digest`, `rendered_relevant_line_count`, `requested_order_id`,
  `source_observed_at`, `source_schema_version`, `state`.
- **Opportunity:** `line_ids`, `opportunity_type`, `potential_value`.
- **Explanation:** `normalized_facts`, `precedence_decision`, `reason_ownership`,
  `rules_evaluated`, `supplied_facts`, `unavailable_facts`.
- **ProcessingStage:** `duration_ns`, `stage`, `status`.
- **HistoryEvent:** `evaluation_id`, `event_id`, `event_kind`, `occurred_at`, `sequence`,
  `state`.
- **HistoryArtifact:** `artifact_id`, `artifact_type`, `occurred_at`, `reasons`, `state`,
  `transition_id`, `value`.
- **Receipt:** `command_id`, `recorded_at`, `replayed`.
- **AttemptReceipt:** `attempt_id`, `command_id`, `conflict`, `error_code`, `outcome`,
  `recorded_at`, `replayed`, `telemetry_operation_id`.
- **SuccessRate:** `defined`, `denominator`, `numerator`.

The exact safety-counter mapping contains:
`EXTERNAL_MUTATION_REQUEST_COUNT`, `EXTERNAL_PRODUCTION_SYSTEM_ACCESS_COUNT`,
`NON_LOCALHOST_RUNTIME_REQUEST_COUNT`, `NON_SYNTHETIC_FIXTURE_COUNT`,
`PRODUCTION_MUTATION_REQUEST_COUNT`, `PRODUCTION_SYSTEM_ACCESS_COUNT`,
`REAL_CUSTOMER_DATA_COUNT`, `REAL_CUSTOMER_IDENTITY_COUNT`, and `SECRET_MATERIAL_COUNT`.

## Line and completeness contract

`line_id` is a `SYN-EVIDENCE-*` identity, `product_id` is a `SYN-SKU-*` identity, and line
indices are one-based. A COMPLETE representation requires a contiguous ordered index sequence,
unique line IDs, exact order/count/timestamp coherence, and an exact recomputation of the
published ordered-line manifest digest.

INCOMPLETE and MALFORMED representations preserve every closed typed member but may advertise
the deliberate structural defect represented by their scenario. They never masquerade as
COMPLETE and never expose an evaluation action in the browser. A MALFORMED fact has null value
and reason and is legal only in a MALFORMED representation.

The `missing-required-section`, `dom-payload-mismatch`, and `stale-source-changed` modes are
exactly INCOMPLETE. A backend view that pairs any of those modes with COMPLETE is rejected before
HTML or an embedded payload is emitted; the renderer also independently withholds Evaluate for
those modes.

Known facts use these exact codecs or enums, and UNKNOWN facts use only the bound reason:

| Line field | KNOWN value | UNKNOWN reason |
|---|---|---|
| `activity` | `ACTIVE`, `CANCELED`, or `UNKNOWN` | `RC-125` |
| `availability` | `IN_STOCK`, `DELAYED`, or `UNKNOWN` | `RC-016` |
| `drop_ship_state` | `DS`, `NON_DS`, or `UNKNOWN` | `RC-017` |
| `eta` | canonical UTC timestamp | `RC-115` |
| `quantity` | governed Quantity canonical JSON string | `RC-129` |
| `line_value` | exact Money object | `RC-134` |

KNOWN requires a non-null governed value and null reason. UNKNOWN requires a null value and the
field-specific reason above. NOT_APPLICABLE requires both null. Cross-field reason substitution
is invalid.

## Synthetic identity namespaces

- Orders and completeness order bindings: `SYN-ORDER-*`.
- Products: `SYN-SKU-*`.
- Lines, commands, durable attempts, and telemetry operations: `SYN-EVIDENCE-*`.
- Interactions: `SYN-INTERACTION-*`.
- Runs: `SYN-RUN-*`.
- Snapshots: `SYN-SNAPSHOT-*`.
- Evaluations: `SYN-EVALUATION-*`.
- A Sales Credit case is the exact `SYN-ORDER-*` evaluation order. A DOI case, when one is
  created, is a `SYN-EVIDENCE-*` identity; a fail-closed DOI result may have no case.

Every opportunity `line_id` is a `SYN-EVIDENCE-*` identity and, for an order evaluation or
nested rendered result, must belong to that exact order's validated relevant-line universe.

## Request and action policy

Instantiate request objects contain exactly `mode`, `request_key`, and `schema_version`.
Evaluate requests contain exactly `request_key` and `schema_version`. Shutdown requests contain
exactly `schema_version`. Request keys are nullable bounded canonical strings. Duplicate JSON
members, floats, nonfinite numbers, unknown members, invalid UTF-8, and bodies over 16,384 bytes
are rejected.

Every POST requires exact Host, same-origin Origin, and the receipt's independent `csrf_token`
in `X-SSA-CSRF-Token`. Shutdown additionally requires the distinct `shutdown_token` in
`X-SSA-Shutdown-Token`; no PID-only shutdown exists. Evaluation performs a fresh local
database/schema/projection/safety health check before dispatch, obtains the already-instantiated
order detail without re-evaluating it, and binds the single evaluation response to that order's
ID, scenario alias, rule pack, and relevant-line IDs. Evaluation never mutates source facts or
creates an intervention, manager outcome, or human decision.

Every JSON or HTML response and every embedded canonical DOM payload is bounded to 524,288
bytes. Evaluation results retain exact rule-pack versions, explanations, separately scoped
opportunities, aggregate-potential state, replay/conflict state, durable synthetic identifiers,
and trusted processing duration. Unknown facts are never replaced by guessed values.
