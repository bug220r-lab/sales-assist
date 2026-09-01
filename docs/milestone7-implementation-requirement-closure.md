# Milestone 7 implementation-requirement closure

- Matrix version: `synthetic-sales-assist-m7-readiness-closure/v1`
- Authority: the ten binding implementation requirements in
  `tasks/milestone7_control_center_dashboard.txt`
- Status vocabulary: `CLOSED_M7` means current M7 code and collected executable tests prove the
  requirement; `OPEN_M7` means implementation or executable evidence is still missing
- Database schema: `4` (unchanged)
- Manual acceptance: `M7_MANUAL_ACCEPTANCE = PENDING`

This matrix closes implementation requirements only. It does not replace the final same-tree
candidate gate or the later user-visible manual acceptance session.

| # | Binding requirement | Status | Implemented boundary | Executable evidence |
|---|---|---|---|---|
| 1 | Bind every dashboard action to an existing committed application service or reducer. | `CLOSED_M7` | `ControlCenterApplication` delegates manager outcome, overlap selection, deep verification, and backup to the exact authorities in the Markdown/JSON action matrix. Rendering exposes only supported actions; unsupported DOI, restore, and reset controls are absent. | `test_sales_credit_manager_outcome_success_replay_conflict_and_separation`; `test_doi_overlap_selection_is_atomic_replayable_and_conflicting`; `test_deep_verify_is_read_only_and_backup_requires_confirmation_key`; `test_unsupported_high_authority_controls_are_absent`; `test_action_matrix_matches_rendered_mutation_surface` |
| 2 | Keep system classifications and human decisions visibly separate. | `CLOSED_M7` | Sales Credit detail uses separate system-classification and manager-outcome cards, separate application objects, and distinct immutable event types. Manager action leaves the retained evaluation/classification unchanged. | `test_sales_credit_manager_outcome_success_replay_conflict_and_separation`; `test_human_action_forms_are_explicit_confirmed_and_closed`; `test_current_projection_history_and_currency_labels_are_explicit` |
| 3 | Keep current queue counts separate from immutable historical event totals. | `CLOSED_M7` | Queue/card methods read current schema-4 projections; timeline/reconciliation methods read immutable events and receipts. Replay/conflict history is reported separately and does not allocate a new current item. | `test_metrics_separate_replay_conflict_and_current_projection_counts`; `test_queues_are_current_bounded_and_domain_aware`; `test_empty_schema_four_application_renders_every_fixed_dashboard` |
| 4 | Publish and enforce exact metric denominators. | `CLOSED_M7` | `synthetic-sales-assist-metric-denominators/v1` defines all 15 required metrics with basis, denominator, exclusions, time basis, and empty-denominator semantics; overview links resolve to anchored definitions on the window-labeled telemetry route. | `test_registry_is_versioned_and_exhaustive`; `test_empty_denominators_are_na_not_zero_percent`; `test_metric_window_is_half_open`; `test_denominator_documentation_reconciles_to_registry` |
| 5 | Segment all Money displays and totals by currency. | `CLOSED_M7` | Potential and realized values are grouped by registered currency. Unavailable and unresolved-overlap amounts are excluded and counted; no mixed-currency total or conversion exists. | `test_currency_totals_are_segmented_and_overlap_remains_unavailable`; `test_current_projection_history_and_currency_labels_are_explicit` |
| 6 | Use truthful extension-status semantics. | `CLOSED_M7` | Status is exactly `EXPECTED_PACKAGE_ONLY`, `LAST_SEEN_HEALTHY`, `LAST_SEEN_STALE`, `VERSION_MISMATCH`, or `UNKNOWN`. The version-only observation is process-local and event-bound; package presence never means installed. | `test_all_five_extension_states`; `test_all_five_extension_states_render_truthfully`; `test_extension_handshake_is_closed_same_origin_and_process_local`; `test_current_package_inventory_and_deterministic_bytes_are_exact` |
| 7 | Require confirmation, request keys, replay, and conflict feedback for human actions. | `CLOSED_M7` | Manager outcome and DOI overlap selection require explicit confirmation, reserved synthetic actor, closed material, and bounded key. First success appends once, exact replay returns its receipt, and changed material conflicts before append. | `test_sales_credit_manager_outcome_success_replay_conflict_and_separation`; `test_partial_requires_exact_currency_money`; `test_doi_overlap_selection_is_atomic_replayable_and_conflicting`; `test_manager_outcome_dispatch_is_closed_and_preserves_canonical_time`; `test_doi_scenario_selection_requires_exact_sorted_option_set` |
| 8 | Order explanations for nontechnical users. | `CLOSED_M7` | Detail pages present current state, plain-English why, required human action, completeness, evidence/opportunities, human outcome/facts, and immutable history in that order. Unknown/unavailable facts remain labeled rather than guessed. | `test_human_action_forms_are_explicit_confirmed_and_closed`; `test_every_dashboard_page_has_accessible_static_structure`; `test_empty_schema_four_application_renders_every_fixed_dashboard` |
| 9 | Use ordinary loopback deep links without new Chrome permissions. | `CLOSED_M7` | The extension builds only allowlisted `http://127.0.0.1:8765/` or normalized `localhost` GET destinations with reserved synthetic IDs. Manifest permissions remain exactly `sidePanel` plus the two accepted loopback host patterns. | `test_closed_dashboard_url_builder_accepts_only_loopback_routes_and_ids`; `test_panel_link_inventory_is_closed_and_nonprivileged`; `test_patch_version_and_permission_surface_are_exact`; `test_evidence_and_audit_evaluation_routes_are_closed_gets` |
| 10 | Expose stable screenshot-safe and machine-readable M8 evidence surfaces. | `CLOSED_M7` | Stable `data-ssa-dashboard-*` selectors, privacy-safe presentation mode, deterministic manager routes, and `/api/v1/dashboard/evidence` expose M8 inputs without implementing M8 packaging, screenshots, audit, or publication. | `test_presentation_mode_is_machine_readable_and_privacy_safe`; `test_evidence_and_audit_evaluation_routes_are_closed_gets`; `test_route_selector_and_m8_evidence_traceability`; `test_milestone_eight_release_artifacts_are_absent` |

## Deferred polish

The readiness review's six nonblocking polish items remain deferred: guided demo mode,
print-friendly manager summary, copy-ID controls, chart animation, saved filters, and theme
selection. Their absence does not weaken any binding requirement above. No live animation or
tooltip-only evidence was introduced.

## Boundary statement

Closure does not authorize production integration, non-loopback networking, external messaging,
source mutation, new Sales Credit or DOI behavior, a schema migration, remote assets, a new Chrome
permission, release packaging, store publication, a release tag, or any other Milestone 8 work.
