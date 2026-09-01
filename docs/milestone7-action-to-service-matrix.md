# Milestone 7 action-to-service matrix

Status: implemented M7 action/rendering parity inventory; manual acceptance remains pending
Machine-readable contract: `docs/milestone7-action-to-service-matrix.json`
Derived from M6 base commit `1ff8198e19af7cbcf9f153c36a66bcfef1c5a45f`, tree `d07f75737eb6a5e891d002cea8a89c6d0d146c67`.

## Decision rule

Every rendered action delegates to a committed application service or read-only query. The one
purpose-specific DOI addition, overlap selection, is an atomic M7 adapter over committed
authority, reducer, evaluator, repository, and idempotency boundaries. It adds no reason,
transition, or business rule. A low-level reducer or persistence method alone is not authority
for a generic UI action. Unsupported candidates are absent; their underlying facts remain
read-only.

UI routes and HTTP handlers validate closed transport schemas, require confirmation where this
matrix says so, and delegate. They do not classify, calculate outcomes, clear attention,
construct interventions, infer links, or calculate value.

## Rendered action inventory

| Action | Disposition | Exact service/reducer authority | Closed input and actor | Confirmation and request key | Receipt, replay, and conflict | Projection and immutable history |
|---|---|---|---|---|---|---|
| Sales Credit evaluate | `SUPPORTED_EXISTING_SERVICE` | `ScenarioApplication.evaluate`; `SalesCreditPersistenceService.persist_case_mutation` | Reserved synthetic `OrderId`; retained source; optional bounded key; actor is `SYSTEM` | Explicit click; no second dialog; dashboard supplies a 1..128 character key | `EvaluationResultView` and durable evaluation graph. Exact material replays; changed bound material conflicts before allocation | Current case changes once. Replay is request history, not a new evaluation; no manager outcome is created |
| Sales Credit manager outcome | `SUPPORTED_EXISTING_SERVICE` | `SalesCreditPersistenceService.record_manager_outcome`; `SalesCreditRepository.append_manager_outcome` | `OrderId` plus `ManagerOutcome`; closed outcome enum; reserved synthetic `RepId`; positive exact `Money` for `PARTIAL`; no note field | Confirmation required; required 1..96 character Control Center key | `DurableCommandResult`, immutable outcome, `OUTCOME_RECORDED`. Exact bytes replay; changed bytes under the key conflict before allocation | Authorized case closes and points to the outcome. System classification/evaluation and source facts remain unchanged |
| DOI evaluate | `SUPPORTED_EXISTING_SERVICE` | `ScenarioApplication.evaluate`; `DOIPersistenceService.persist_demo` | Reserved synthetic `OrderId`; retained complete source; bounded key; actor is `SYSTEM` | Explicit click; no second dialog | `EvaluationResultView`, DOI graph, `DurableCommandResult`. Exact replay; changed material conflict | Current DOI projection changes once. Evaluation cannot create a human fact, intervention, resulting link, or value |
| DOI overlap scenario selection | `SUPPORTED_BY_M7_THIN_ADAPTER` | `ControlCenterApplication.record_doi_overlap_selection`; `verify_synthetic_human_authority`; `StructuredHumanFact.create`; `DOIHumanFactEvent`; `reduce_human_fact`; `ScenarioSelection`; `evaluate_doi`; `DOIRepository.append_owner_event`; `DOIRepository.persist_evaluation`; `SQLiteIdempotencyRepository.resolve_or_record` | Current case/evaluation, selected opportunity, exact sorted option set, reserved synthetic actor, confirmation, bounded key. Context/source/time/authority come from retained synthetic state | Confirmation required and enumerates the exact choice/effect; key required and bound to all command material | One `DurableCommandResult`, human fact/owner event, and recomputed evaluation in one transaction. Exact replay appends nothing; any changed material conflicts before append | Prior unresolved evaluation remains history; new projection uses committed evaluator behavior. Opportunities remain separate; only defined selection/aggregate state changes |
| Health refresh | `SUPPORTED_READ_ONLY` | `ScenarioApplication.system_status(deep=False)` | Closed `deep=false`; no path/SQL/probe input; no actor | No confirmation; no key for GET | Current `SystemStatusView`; repeated reads mutate nothing | No projection or history effect |
| Deep database verification | `SUPPORTED_READ_ONLY` | `ScenarioApplication.system_status(deep=True)`; `verify_database`; both projection verifiers | Closed `deep=true`; no path/SQL/pragma input; no actor | No confirmation; no key | Current integrity, migration, projection, and safety result; busy/unhealthy fails safely | Verification never rebuilds or writes projections |
| Create verified backup | `SUPPORTED_BY_M7_THIN_ADAPTER` | `ControlCenterActions.create_verified_backup`; `create_backup`; `verify_backup` | Confirmation plus bounded key. The adapter derives a deterministic non-reparse path under the managed backup directory; the browser cannot supply a path or overwrite flag | Confirmation and key required | `BackupReceipt` must equal immediate `verify_backup` readback. Same key/material returns the verified receipt; there is no alternate command material | No business projection effect; first command creates one immutable receipt, replay creates none |
| View backup receipts | `SUPPORTED_READ_ONLY` | `ControlCenterApplication.backup_receipts` over immutable `backup_receipts` rows | Managed receipt projection only; no client path; no actor | No confirmation or key | Privacy-safe receipt summaries distinguish completed, started, and failed status; latest-verified selection additionally requires completed/quick-check/foreign-key/hash proof | No mutation |
| Ordinary local deep link | `SUPPORTED_READ_ONLY` | Closed loopback route normalizer and GET route; no business service | Closed route kind plus reserved synthetic ID; fixed loopback origin | No confirmation or key | Navigation only. Invalid origin/path/ID or missing destination fails safely | No mutation |

## Sales Credit manager outcome contract

- Outcomes are exactly `APPROVED`, `DENIED`, `PARTIAL`, `OTHER_REP`, and `NOT_PURSUED`.
- `PARTIAL` requires positive exact `Money` and a registered currency. The UI does not expose
  `active_note`.
- The repository independently requires an eligible current workflow, matching retained
  evaluation, monotonic timestamps, and no pending replacement-child authority conflict.
- The actor is a reserved synthetic `RepId`. Confirmation repeats order, actor, outcome, and
  amount/currency when present.
- `SQLiteIdempotencyRepository` binds the request key to canonical `ManagerOutcome` bytes. Exact
  replay returns the retained receipt. Changed material raises
  `IDEMPOTENCY_KEY_MATERIAL_CONFLICT` before an outcome/event append.
- The `OUTCOME_RECORDED` event is separate from every system-classification event. Recording the
  human outcome does not rewrite attribution, evaluation, evidence, interactions, or source
  order facts.

Executable authority:

- `tests/test_milestone4_sales_credit_persistence.py::test_manager_outcome_replay_conflict_and_authority_are_enforced`
- `tests/test_milestone4_sales_credit_concurrency_faults.py::test_two_exact_concurrent_writers_commit_once_and_replay_once`
- `tests/test_milestone4_sqlite_idempotency.py::test_same_key_changed_material_conflicts_before_allocation`

M7 executable evidence adds confirmation, all five enum paths, `PARTIAL` Money validation,
success/replay/conflict behavior, unchanged classification, and unchanged source facts in
`test_sales_credit_manager_outcome_success_replay_conflict_and_separation`,
`test_partial_requires_exact_currency_money`, and
`test_manager_outcome_dispatch_is_closed_and_preserves_canonical_time`.

## DOI overlap-selection adapter contract

`ControlCenterApplication.record_doi_overlap_selection` is the only M7 DOI human-action
command. It performs one atomic transaction:

1. Load the exact retained unresolved overlap evaluation and open action context.
2. Require that case, evaluation, selected opportunity, and complete sorted option set match.
3. Cross `verify_synthetic_human_authority` with a reserved actor and retained synthetic
   interaction source.
4. Create the closed `StructuredHumanFact` with usage `SCENARIO_SELECTION` and result
   `SCENARIO_SELECTED`, then accept its `DOIHumanFactEvent` through `reduce_human_fact`.
5. Construct `ScenarioSelection` and call the existing `evaluate_doi` with otherwise unchanged
   retained facts.
6. Within the same unit of work, use `SQLiteIdempotencyRepository.resolve_or_record` to append
   the human-fact owner event and durable evaluation through `DOIRepository` and publish the
   durable receipt.

The adapter does not merge/delete opportunities, synthesize Money, invent an action context,
clear unrelated attention, or add reasons/transitions. Same key and byte-identical command
returns the original receipt without invoking the allocator. A different selected opportunity,
option set, case/evaluation, actor, or confirmation value under that key conflicts before any
append.

Executable underlying authority:

- `tests/test_doi_evaluator.py::test_overlapping_opportunities_survive_and_withhold_aggregate`
- `tests/test_doi_evaluator.py::test_scenario_selection_rejects_invalid_human_fact_provenance`
- `tests/test_doi_models.py::test_wwc_and_human_fact_correction_histories_are_exact`
- `tests/test_doi_lifecycle.py::test_dedupe_and_human_fact_owner_reducers_cover_tr060_064_and_tr096_097`
- `tests/test_milestone4_sqlite_idempotency.py::test_exact_replay_returns_retained_result_without_new_allocation`
- `tests/test_milestone4_sqlite_idempotency.py::test_same_key_changed_material_conflicts_before_allocation`

M7 executable evidence proves atomic success, exact replay, changed-material conflict, required
confirmation/authority, cross-case/evaluation/option rejection, immutable timeline, projection
update, and unchanged source/unrelated opportunities in
`test_doi_overlap_selection_is_atomic_replayable_and_conflicting` and
`test_doi_scenario_selection_requires_exact_sorted_option_set`.

## Unsupported DOI candidates

| Candidate | Existing lower-level authority | Why no M7 action is rendered | Required absence/invariant test |
|---|---|---|---|
| Generic structured human fact | `reduce_human_fact`; `DOIPersistenceService.record_human_fact` | No closed purpose-specific context, authority, reevaluation, and request-material command | Generic fact control absent; only overlap selection is actionable |
| Compatibility approve/reject | Closed `COMPATIBILITY_DECISION` fact and human-fact reducer | No committed purpose-specific application/idempotency command | Compatibility state is read-only |
| Confirm no viable alternate | Closed `NO_VIABLE_ALTERNATE` fact and human-fact reducer | No committed purpose-specific application/idempotency command | Alternate state is read-only |
| Human out-of-scope closure | `make_out_of_scope_closure_guard_proof`; lifecycle reducer/persistence | Protected closure needs an exact authorized fact and proof graph; no dashboard command assembles it | Closure control absent |
| Resolve one attention cause | Cause-specific `case_attention` reducers; `reduce_attention`; `clear_attention_cause` persistence surface | There is deliberately no generic clear-by-ID authority. Each cause has different exact evidence | Generic clear absent; unrelated causes remain visible |
| Trigger local recheck | `make_case_recheck_transition_guard_proof`; `DOIPersistenceService.reopen_case` | Ordinary evaluation replay is not a domain recheck; reopen requires a complete precomputed graph | Recheck control absent |
| Verify intervention/action | `record_verified_intervention`; `verify_intervention_action` persistence surface | Persistence accepts an already verified `DOIIntervention`; it is not action authority | Control absent; opportunity cannot create intervention |
| Confirm resulting-order link | `append_resulting_link_revision`; `link_resulting_order` persistence surface | Persistence accepts an already authorized exact link and cannot infer one from a UI choice | Control absent; evaluation cannot create link |
| Append value correction/reversal | `append_value_event`; `DOIPersistenceService.append_value_event` persistence surface | Persistence accepts a fully reduced graph and cannot authorize arbitrary form Money/value state | Control absent; opportunity cannot create realized value |

Relevant executable guards include:

- `tests/test_doi_lifecycle.py::test_attention_causes_coexist_and_clear_references_exact_set`
- `tests/test_doi_lifecycle.py::test_attention_wrong_set_cannot_clear_and_replay_is_exact`
- `tests/test_doi_case_attention.py::test_tr020_tr021_tr022_and_tr024_are_typed_and_preserve_unrelated_causes`
- `tests/test_doi_lifecycle.py::test_tr013_requires_real_authorized_out_of_scope_fact`
- `tests/test_doi_lifecycle.py::test_tr014_and_tr015_require_exact_case_recheck_and_retention`
- `tests/test_doi_interventions.py::test_only_verified_action_creates_intervention`
- `tests/test_doi_interventions.py::test_action_exact_replay_and_changed_occurrence_conflict`
- `tests/test_doi_interventions.py::test_resulting_link_conflict_and_resolution_preserve_revisions`
- `tests/test_doi_interventions.py::test_search_not_found_and_ambiguous_are_not_exact_links`
- `tests/test_doi_interventions.py::test_system_value_and_append_only_partial_full_reversal`
- `tests/test_doi_interventions.py::test_reversal_void_recomputes_without_rewriting_history`
- `tests/test_doi_interventions.py::test_value_exact_replay_and_occurrence_conflict`

## System operation boundary

Health and deep verification are read-only and do not need a request key. Deep verification calls
the existing deep SQLite check and both projection verifiers; it never rebuilds.

Backup creation requires a confirmation and bounded key. The browser never supplies an absolute
path. The server derives a managed local destination, sets `overwrite=False`, creates the backup,
and requires an equal `verify_backup` receipt before reporting success. Exact replay returns that
verified receipt. Receipt views read the immutable `backup_receipts` projection and omit ordinary
absolute paths and usernames.

Executable authority:

- `tests/test_milestone5_application.py::test_status_metrics_and_exact_closed_versions`
- `tests/test_milestone5_application.py::test_status_fails_for_nonzero_system_or_incomplete_telemetry_counter_set`
- `tests/test_milestone4_sqlite_core.py::test_fresh_database_migrates_and_inventory_is_deterministic`
- `tests/test_milestone4_doi_repository.py::test_projection_verifier_detects_drift_without_rebuilding`
- `tests/test_milestone4_backup_restore.py::test_online_backup_and_exact_restore_preserve_active_validity`
- `tests/test_milestone4_backup_restore.py::test_backup_path_policy_rejects_nonlocal_or_ambiguous_paths`
- `tests/test_milestone4_backup_restore.py::test_new_backup_publishes_sidecar_before_identity_database`

Restore and reset are `OUT_OF_SCOPE_M7_NOT_RENDERED`. Restore remains available only through its
separate existing maintenance/CLI workflow and strong confirmation boundary; reset likewise is
not a Control Center action. `test_unsupported_high_authority_controls_are_absent` and
`test_action_matrix_matches_rendered_mutation_surface` prove that neither control appears.

## Parity gate

The machine-readable file is normative for UI parity.
`test_action_matrix_matches_rendered_mutation_surface` enumerates every rendered mutation form,
requires its supported entry and callable facade symbol, and checks the prohibited high-authority
controls are absent. Links, filters, pagination, refresh GETs, and ordinary loopback navigation
remain read-only and never cross a business reducer.
