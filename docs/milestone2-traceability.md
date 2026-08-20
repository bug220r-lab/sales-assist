# Milestone 2 Sales Credit traceability

Generated from `sales_credit.traceability`; manual edits are rejected by tests.

- Catalog version: `synthetic-sales-credit-traceability/v1`
- Synthetic scenarios: 66
- Owned decision reasons: 45
- Workflow states: 16
- Collected test selectors: 55
- Safety expectation: all nine counters are zero for every scenario

## Reason ownership

| Scenario | Branch | Workflow | Human review | Reasons | Effects | Test selectors |
|---|---|---|---:|---|---|---|
| `SYN-EVIDENCE-M2-SCENARIO-001` | `NO_USABLE_SEARCH_IDENTIFIER` | `MANUAL_REVIEW_REQUIRED` | `true` | `NO_USABLE_SEARCH_IDENTIFIER` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_no_order_closure.PostEvaluationNoOrderReducerTests.test_identifierless_manual_transition_is_applied_and_replay_safe` |
| `SYN-EVIDENCE-M2-SCENARIO-002` | `IDENTIFIER_SEARCH_INCOMPLETE` | `MANUAL_REVIEW_REQUIRED` | `true` | `IDENTIFIER_SEARCH_INCOMPLETE` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_no_order_closure.PostEvaluationNoOrderReducerTests.test_incomplete_enumeration_applies_governed_manual_state` |
| `SYN-EVIDENCE-M2-SCENARIO-003` | `NO_ORDER_WINDOW_ACTIVE` | `CHECKED_NO_ORDER_WINDOW_ACTIVE` | `false` | `NO_ORDER_WINDOW_ACTIVE` | `NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_search_run.OrderSearchRunTests.test_ledger_commits_active_state_exact_replay_and_conflict_atomically` |
| `SYN-EVIDENCE-M2-SCENARIO-004` | `NO_ORDER_WINDOW_CLOSED` | `REVIEW_WINDOW_CLOSED_NO_ORDER` | `false` | `NO_ORDER_WINDOW_CLOSED` | `NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_no_order_closure.NoOrderClosureProjectionTests.test_terminal_run_derives_the_identity_free_minimized_root` |
| `SYN-EVIDENCE-M2-SCENARIO-005` | `ORDER_BEFORE_INTERACTION` | `MANUAL_REVIEW_REQUIRED` | `true` | `ORDER_BEFORE_INTERACTION` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.SnapshotPrecedenceTests.test_candidate_order_must_qualify_against_an_attached_interaction` |
| `SYN-EVIDENCE-M2-SCENARIO-006` | `ORDER_AFTER_REVIEW_WINDOW` | `MANUAL_REVIEW_REQUIRED` | `true` | `ORDER_AFTER_REVIEW_WINDOW` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.SnapshotPrecedenceTests.test_candidate_order_must_qualify_against_an_attached_interaction` |
| `SYN-EVIDENCE-M2-SCENARIO-007` | `ORDER_BEFORE_CANCELLATION` | `CANCELED_REPLACEMENT_WINDOW_ACTIVE` | `false` | `ORDER_BEFORE_CANCELLATION` | `ACTIVE_CASE_CLASSIFICATION, NO_PERSISTENCE_MILESTONE_2, ZERO_ACTIVE_VALUE` | `tests.test_sales_credit_evaluator.CancellationAndReplacementTests.test_forged_or_out_of_window_replacement_facts_fail_closed` |
| `SYN-EVIDENCE-M2-SCENARIO-008` | `ORDER_AFTER_REPLACEMENT_WINDOW` | `CANCELED_NO_REPLACEMENT` | `false` | `ORDER_AFTER_REPLACEMENT_WINDOW` | `ACTIVE_CASE_CLASSIFICATION, NO_PERSISTENCE_MILESTONE_2, ZERO_ACTIVE_VALUE` | `tests.test_sales_credit_evaluator.CancellationAndReplacementTests.test_forged_or_out_of_window_replacement_facts_fail_closed` |
| `SYN-EVIDENCE-M2-SCENARIO-009` | `ORDER_TIMING_UNCERTAIN` | `TIMING_UNCERTAIN_HUMAN_REVIEW` | `true` | `ORDER_TIMING_UNCERTAIN` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.SnapshotPrecedenceTests.test_candidate_order_must_qualify_against_an_attached_interaction` |
| `SYN-EVIDENCE-M2-SCENARIO-010` | `AUTOMATIC_RECHECK_THROTTLED_LOCAL_DAY` | `CHECKED_NO_ORDER_WINDOW_ACTIVE` | `false` | `AUTOMATIC_RECHECK_THROTTLED_LOCAL_DAY` | `NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_windows.RecheckEligibilityTests.test_automatic_check_is_eligible_once_per_new_york_date` |
| `SYN-EVIDENCE-M2-SCENARIO-011` | `FORCE_RECHECK_ACCEPTED` | `CHECKED_NO_ORDER_WINDOW_ACTIVE` | `false` | `FORCE_RECHECK_ACCEPTED` | `NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_windows.RecheckEligibilityTests.test_selected_force_bypasses_only_daily_throttle_and_is_audited` |
| `SYN-EVIDENCE-M2-SCENARIO-012` | `SNAPSHOT_INVALID` | `MANUAL_REVIEW_REQUIRED` | `true` | `SNAPSHOT_INVALID` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.SnapshotPrecedenceTests.test_invalid_or_missing_core_fact_stops_all_favorable_rules` |
| `SYN-EVIDENCE-M2-SCENARIO-013` | `SNAPSHOT_PARTIAL_DEPENDENCY_BLOCKED` | `ORDER_CHANGED_HUMAN_REVIEW` | `true` | `SNAPSHOT_PARTIAL_DEPENDENCY_BLOCKED` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.SnapshotPrecedenceTests.test_partial_snapshot_blocks_only_its_dependent_dimension` |
| `SYN-EVIDENCE-M2-SCENARIO-014` | `MISSING_REQUIRED_FIELD` | `MANUAL_REVIEW_REQUIRED` | `true` | `MISSING_REQUIRED_FIELD` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.SnapshotPrecedenceTests.test_invalid_or_missing_core_fact_stops_all_favorable_rules` |
| `SYN-EVIDENCE-M2-SCENARIO-015` | `UNSUPPORTED_SCHEMA_OR_SNAPSHOT` | `MANUAL_REVIEW_REQUIRED` | `true` | `UNSUPPORTED_SCHEMA_OR_SNAPSHOT` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.SnapshotPrecedenceTests.test_lifecycle_raw_fact_contradiction_fails_before_rules` |
| `SYN-EVIDENCE-M2-SCENARIO-016` | `CONTRADICTORY_FACTS` | `MANUAL_REVIEW_REQUIRED` | `true` | `CONTRADICTORY_FACTS` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.SnapshotPrecedenceTests.test_lifecycle_raw_fact_contradiction_fails_before_rules` |
| `SYN-EVIDENCE-M2-SCENARIO-017` | `TARGET_REP` | `CREDIT_CONFIRMED_TARGET_REP` | `false` | `TARGET_REP` | `ACTIVE_CASE_CLASSIFICATION, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_every_exact_order_rep_branch_and_no_line_rep_substitution` |
| `SYN-EVIDENCE-M2-SCENARIO-018` | `TARGET_REP_WEB` | `CREDIT_CONFIRMED_TARGET_REP` | `false` | `TARGET_REP_WEB` | `ACTIVE_CASE_CLASSIFICATION, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_every_exact_order_rep_branch_and_no_line_rep_substitution` |
| `SYN-EVIDENCE-M2-SCENARIO-019` | `UNASSIGNED_WEB` | `EVIDENCE_NEEDED` | `false` | `UNASSIGNED_WEB` | `ACTIVE_CASE_CLASSIFICATION, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_every_exact_order_rep_branch_and_no_line_rep_substitution` |
| `SYN-EVIDENCE-M2-SCENARIO-020` | `OTHER_KNOWN_REP` | `OTHER_REP_HUMAN_REVIEW` | `true` | `OTHER_KNOWN_REP` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_every_exact_order_rep_branch_and_no_line_rep_substitution` |
| `SYN-EVIDENCE-M2-SCENARIO-021` | `REP_MISSING` | `MANUAL_REVIEW_REQUIRED` | `true` | `REP_MISSING` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_every_exact_order_rep_branch_and_no_line_rep_substitution` |
| `SYN-EVIDENCE-M2-SCENARIO-022` | `REP_UNRECOGNIZED` | `MANUAL_REVIEW_REQUIRED` | `true` | `REP_UNRECOGNIZED` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_every_exact_order_rep_branch_and_no_line_rep_substitution` |
| `SYN-EVIDENCE-M2-SCENARIO-023` | `TWO_WAY_PREORDER_INTERACTION` | `VERIFIED_PREORDER_EVIDENCE` | `false` | `TWO_WAY_PREORDER_INTERACTION` | `ACTIVE_CASE_CLASSIFICATION, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.EvidenceClassificationTests.test_every_binding_evidence_branch` |
| `SYN-EVIDENCE-M2-SCENARIO-024` | `CONNECTED_PREORDER_CALL` | `VERIFIED_PREORDER_EVIDENCE` | `false` | `CONNECTED_PREORDER_CALL` | `ACTIVE_CASE_CLASSIFICATION, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.EvidenceClassificationTests.test_every_binding_evidence_branch` |
| `SYN-EVIDENCE-M2-SCENARIO-025` | `INBOUND_ONLY_PREORDER_CONTACT` | `INBOUND_EVIDENCE_HUMAN_REVIEW` | `true` | `INBOUND_ONLY_PREORDER_CONTACT` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.EvidenceClassificationTests.test_every_binding_evidence_branch` |
| `SYN-EVIDENCE-M2-SCENARIO-026` | `OUTBOUND_ONLY_PREORDER_CONTACT` | `OUTBOUND_EVIDENCE_HUMAN_REVIEW` | `true` | `OUTBOUND_ONLY_PREORDER_CONTACT` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.EvidenceClassificationTests.test_every_binding_evidence_branch` |
| `SYN-EVIDENCE-M2-SCENARIO-027` | `MISSED_OR_UNANSWERED_INBOUND_CALL` | `INBOUND_EVIDENCE_HUMAN_REVIEW` | `true` | `MISSED_OR_UNANSWERED_INBOUND_CALL` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.EvidenceClassificationTests.test_every_binding_evidence_branch` |
| `SYN-EVIDENCE-M2-SCENARIO-028` | `POST_ORDER_CONTACT_ONLY` | `MANUAL_REVIEW_REQUIRED` | `true` | `POST_ORDER_CONTACT_ONLY` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.EvidenceClassificationTests.test_every_binding_evidence_branch` |
| `SYN-EVIDENCE-M2-SCENARIO-029` | `EVIDENCE_TIMING_UNCERTAIN` | `TIMING_UNCERTAIN_HUMAN_REVIEW` | `true` | `EVIDENCE_TIMING_UNCERTAIN` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.EvidenceClassificationTests.test_every_binding_evidence_branch` |
| `SYN-EVIDENCE-M2-SCENARIO-030` | `EVIDENCE_IDENTITY_UNPROVED` | `MANUAL_REVIEW_REQUIRED` | `true` | `EVIDENCE_IDENTITY_UNPROVED` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.EvidenceClassificationTests.test_every_binding_evidence_branch` |
| `SYN-EVIDENCE-M2-SCENARIO-031` | `NO_QUALIFYING_PREORDER_EVIDENCE` | `EVIDENCE_NEEDED` | `false` | `NO_QUALIFYING_PREORDER_EVIDENCE` | `ACTIVE_CASE_CLASSIFICATION, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.EvidenceClassificationTests.test_every_binding_evidence_branch` |
| `SYN-EVIDENCE-M2-SCENARIO-032` | `CANCELED_ORDER_ZERO_ACTIVE_VALUE` | `CANCELED_REPLACEMENT_WINDOW_ACTIVE` | `false` | `CANCELED_ORDER_ZERO_ACTIVE_VALUE` | `ACTIVE_CASE_CLASSIFICATION, NO_PERSISTENCE_MILESTONE_2, ZERO_ACTIVE_VALUE` | `tests.test_sales_credit_evaluator.CancellationAndReplacementTests.test_canceled_order_open_and_expired_windows_have_zero_active_value` |
| `SYN-EVIDENCE-M2-SCENARIO-033` | `REPLACEMENT_WINDOW_ACTIVE` | `CANCELED_REPLACEMENT_WINDOW_ACTIVE` | `false` | `REPLACEMENT_WINDOW_ACTIVE` | `ACTIVE_CASE_CLASSIFICATION, NO_PERSISTENCE_MILESTONE_2, ZERO_ACTIVE_VALUE` | `tests.test_sales_credit_evaluator.CancellationAndReplacementTests.test_canceled_order_open_and_expired_windows_have_zero_active_value` |
| `SYN-EVIDENCE-M2-SCENARIO-034` | `EXACT_ES_PRODUCT_CONTINUITY` | `POSSIBLE_REPLACEMENT_HUMAN_REVIEW` | `true` | `EXACT_ES_PRODUCT_CONTINUITY` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2, ZERO_ACTIVE_VALUE` | `tests.test_sales_credit_evaluator.CancellationAndReplacementTests.test_exact_es_mfg_one_among_many_nonexact_and_absent_branches` |
| `SYN-EVIDENCE-M2-SCENARIO-035` | `EXACT_MFG_OE_PRODUCT_CONTINUITY` | `POSSIBLE_REPLACEMENT_HUMAN_REVIEW` | `true` | `EXACT_MFG_OE_PRODUCT_CONTINUITY` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2, ZERO_ACTIVE_VALUE` | `tests.test_sales_credit_evaluator.CancellationAndReplacementTests.test_exact_es_mfg_one_among_many_nonexact_and_absent_branches` |
| `SYN-EVIDENCE-M2-SCENARIO-036` | `NONEXACT_PRODUCT_CONTINUITY_REQUIRES_REVIEW` | `POSSIBLE_REPLACEMENT_HUMAN_REVIEW` | `true` | `NONEXACT_PRODUCT_CONTINUITY_REQUIRES_REVIEW` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2, ZERO_ACTIVE_VALUE` | `tests.test_sales_credit_evaluator.CancellationAndReplacementTests.test_exact_es_mfg_one_among_many_nonexact_and_absent_branches` |
| `SYN-EVIDENCE-M2-SCENARIO-037` | `CUSTOMER_CONTINUITY_UNPROVED` | `POSSIBLE_REPLACEMENT_HUMAN_REVIEW` | `true` | `CUSTOMER_CONTINUITY_UNPROVED` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2, ZERO_ACTIVE_VALUE` | `tests.test_sales_credit_evaluator.CancellationAndReplacementTests.test_customer_absence_and_incomplete_lines_cannot_prove_replacement` |
| `SYN-EVIDENCE-M2-SCENARIO-038` | `CUSTOMER_CONTINUITY_MISMATCH` | `CANCELED_REPLACEMENT_WINDOW_ACTIVE` | `false` | `CUSTOMER_CONTINUITY_MISMATCH` | `ACTIVE_CASE_CLASSIFICATION, NO_PERSISTENCE_MILESTONE_2, ZERO_ACTIVE_VALUE` | `tests.test_sales_credit_evaluator.CancellationAndReplacementTests.test_customer_absence_and_incomplete_lines_cannot_prove_replacement` |
| `SYN-EVIDENCE-M2-SCENARIO-039` | `NO_PRODUCT_CONTINUITY` | `CANCELED_REPLACEMENT_WINDOW_ACTIVE` | `false` | `NO_PRODUCT_CONTINUITY` | `ACTIVE_CASE_CLASSIFICATION, NO_PERSISTENCE_MILESTONE_2, ZERO_ACTIVE_VALUE` | `tests.test_sales_credit_evaluator.CancellationAndReplacementTests.test_exact_es_mfg_one_among_many_nonexact_and_absent_branches` |
| `SYN-EVIDENCE-M2-SCENARIO-040` | `REPLACEMENT_WINDOW_EXPIRED` | `CANCELED_NO_REPLACEMENT` | `false` | `REPLACEMENT_WINDOW_EXPIRED` | `ACTIVE_CASE_CLASSIFICATION, NO_PERSISTENCE_MILESTONE_2, ZERO_ACTIVE_VALUE` | `tests.test_sales_credit_evaluator.CancellationAndReplacementTests.test_canceled_order_open_and_expired_windows_have_zero_active_value` |
| `SYN-EVIDENCE-M2-SCENARIO-041` | `PLACED_VALUE_PROVED` | `CREDIT_CONFIRMED_TARGET_REP` | `false` | `PLACED_VALUE_PROVED` | `ACTIVE_CASE_CLASSIFICATION, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_routine_changes_are_nonmaterial_but_current_value_never_substitutes` |
| `SYN-EVIDENCE-M2-SCENARIO-042` | `PLACED_VALUE_UNAVAILABLE` | `ORDER_CHANGED_HUMAN_REVIEW` | `true` | `PLACED_VALUE_UNAVAILABLE` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_routine_changes_are_nonmaterial_but_current_value_never_substitutes` |
| `SYN-EVIDENCE-M2-SCENARIO-043` | `MATERIAL_CHANGE_DETECTED` | `ORDER_CHANGED_HUMAN_REVIEW` | `true` | `MATERIAL_CHANGE_DETECTED` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_each_material_change_overrides_workflow_but_not_attribution` |
| `SYN-EVIDENCE-M2-SCENARIO-044` | `ROUTINE_LIFECYCLE_CHANGE_NONMATERIAL` | `CREDIT_CONFIRMED_TARGET_REP` | `false` | `ROUTINE_LIFECYCLE_CHANGE_NONMATERIAL` | `ACTIVE_CASE_CLASSIFICATION, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_routine_changes_are_nonmaterial_but_current_value_never_substitutes` |
| `SYN-EVIDENCE-M2-SCENARIO-045` | `AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW` | `MANUAL_REVIEW_REQUIRED` | `true` | `AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW` | `HUMAN_REVIEW_REQUIRED, NO_PERSISTENCE_MILESTONE_2` | `tests.test_sales_credit_evaluator.CancellationAndReplacementTests.test_forged_or_out_of_window_replacement_facts_fail_closed` |

## Closed branch inventories

| Scenario | Evidence | Material | Human outcome | Workflow | Test selectors |
|---|---|---|---|---|---|
| `SYN-EVIDENCE-M2-SCENARIO-023` | `VERIFIED_PREORDER_EVIDENCE` | `-` | `-` | `VERIFIED_PREORDER_EVIDENCE` | `tests.test_sales_credit_evaluator.EvidenceClassificationTests.test_every_binding_evidence_branch` |
| `SYN-EVIDENCE-M2-SCENARIO-025` | `INBOUND_EVIDENCE_HUMAN_REVIEW` | `-` | `-` | `INBOUND_EVIDENCE_HUMAN_REVIEW` | `tests.test_sales_credit_evaluator.EvidenceClassificationTests.test_every_binding_evidence_branch` |
| `SYN-EVIDENCE-M2-SCENARIO-026` | `OUTBOUND_EVIDENCE_HUMAN_REVIEW` | `-` | `-` | `OUTBOUND_EVIDENCE_HUMAN_REVIEW` | `tests.test_sales_credit_evaluator.EvidenceClassificationTests.test_every_binding_evidence_branch` |
| `SYN-EVIDENCE-M2-SCENARIO-028` | `POST_ORDER_CONTACT_ONLY` | `-` | `-` | `MANUAL_REVIEW_REQUIRED` | `tests.test_sales_credit_evaluator.EvidenceClassificationTests.test_every_binding_evidence_branch` |
| `SYN-EVIDENCE-M2-SCENARIO-029` | `TIMING_UNCERTAIN_HUMAN_REVIEW` | `-` | `-` | `TIMING_UNCERTAIN_HUMAN_REVIEW` | `tests.test_sales_credit_evaluator.EvidenceClassificationTests.test_every_binding_evidence_branch` |
| `SYN-EVIDENCE-M2-SCENARIO-030` | `UNKNOWN_OR_CONTRADICTORY` | `-` | `-` | `MANUAL_REVIEW_REQUIRED` | `tests.test_sales_credit_evaluator.EvidenceClassificationTests.test_every_binding_evidence_branch` |
| `SYN-EVIDENCE-M2-SCENARIO-046` | `-` | `PRODUCT_ADDITION` | `-` | `ORDER_CHANGED_HUMAN_REVIEW` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_each_material_change_overrides_workflow_but_not_attribution, tests.test_sales_credit_models.MaterialChangeTests.test_all_fourteen_kinds_have_exact_material_partition` |
| `SYN-EVIDENCE-M2-SCENARIO-047` | `-` | `PRODUCT_REMOVAL` | `-` | `ORDER_CHANGED_HUMAN_REVIEW` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_each_material_change_overrides_workflow_but_not_attribution, tests.test_sales_credit_models.MaterialChangeTests.test_all_fourteen_kinds_have_exact_material_partition` |
| `SYN-EVIDENCE-M2-SCENARIO-048` | `-` | `QUANTITY_CHANGE` | `-` | `ORDER_CHANGED_HUMAN_REVIEW` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_each_material_change_overrides_workflow_but_not_attribution, tests.test_sales_credit_models.MaterialChangeTests.test_all_fourteen_kinds_have_exact_material_partition` |
| `SYN-EVIDENCE-M2-SCENARIO-049` | `-` | `SUBSTITUTION` | `-` | `ORDER_CHANGED_HUMAN_REVIEW` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_each_material_change_overrides_workflow_but_not_attribution, tests.test_sales_credit_models.MaterialChangeTests.test_all_fourteen_kinds_have_exact_material_partition` |
| `SYN-EVIDENCE-M2-SCENARIO-050` | `-` | `PARTIAL_CANCELLATION` | `-` | `ORDER_CHANGED_HUMAN_REVIEW` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_each_material_change_overrides_workflow_but_not_attribution, tests.test_sales_credit_models.MaterialChangeTests.test_all_fourteen_kinds_have_exact_material_partition` |
| `SYN-EVIDENCE-M2-SCENARIO-051` | `-` | `SHIPPING_CHANGE` | `-` | `ORDER_CHANGED_HUMAN_REVIEW` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_each_material_change_overrides_workflow_but_not_attribution, tests.test_sales_credit_models.MaterialChangeTests.test_all_fourteen_kinds_have_exact_material_partition` |
| `SYN-EVIDENCE-M2-SCENARIO-052` | `-` | `DISCOUNT` | `-` | `ORDER_CHANGED_HUMAN_REVIEW` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_each_material_change_overrides_workflow_but_not_attribution, tests.test_sales_credit_models.MaterialChangeTests.test_all_fourteen_kinds_have_exact_material_partition` |
| `SYN-EVIDENCE-M2-SCENARIO-053` | `-` | `PRICE_ADJUSTMENT` | `-` | `ORDER_CHANGED_HUMAN_REVIEW` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_each_material_change_overrides_workflow_but_not_attribution, tests.test_sales_credit_models.MaterialChangeTests.test_all_fourteen_kinds_have_exact_material_partition` |
| `SYN-EVIDENCE-M2-SCENARIO-054` | `-` | `REFUND` | `-` | `ORDER_CHANGED_HUMAN_REVIEW` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_each_material_change_overrides_workflow_but_not_attribution, tests.test_sales_credit_models.MaterialChangeTests.test_all_fourteen_kinds_have_exact_material_partition` |
| `SYN-EVIDENCE-M2-SCENARIO-055` | `-` | `RETURN` | `-` | `ORDER_CHANGED_HUMAN_REVIEW` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_each_material_change_overrides_workflow_but_not_attribution, tests.test_sales_credit_models.MaterialChangeTests.test_all_fourteen_kinds_have_exact_material_partition` |
| `SYN-EVIDENCE-M2-SCENARIO-056` | `-` | `ROUTINE_WAREHOUSE` | `-` | `CREDIT_CONFIRMED_TARGET_REP` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_routine_changes_are_nonmaterial_but_current_value_never_substitutes, tests.test_sales_credit_models.MaterialChangeTests.test_all_fourteen_kinds_have_exact_material_partition` |
| `SYN-EVIDENCE-M2-SCENARIO-057` | `-` | `ROUTINE_INVENTORY` | `-` | `CREDIT_CONFIRMED_TARGET_REP` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_routine_changes_are_nonmaterial_but_current_value_never_substitutes, tests.test_sales_credit_models.MaterialChangeTests.test_all_fourteen_kinds_have_exact_material_partition` |
| `SYN-EVIDENCE-M2-SCENARIO-058` | `-` | `ROUTINE_TRACKING` | `-` | `CREDIT_CONFIRMED_TARGET_REP` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_routine_changes_are_nonmaterial_but_current_value_never_substitutes, tests.test_sales_credit_models.MaterialChangeTests.test_all_fourteen_kinds_have_exact_material_partition` |
| `SYN-EVIDENCE-M2-SCENARIO-059` | `-` | `ROUTINE_ADMINISTRATIVE` | `-` | `CREDIT_CONFIRMED_TARGET_REP` | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_routine_changes_are_nonmaterial_but_current_value_never_substitutes, tests.test_sales_credit_models.MaterialChangeTests.test_all_fourteen_kinds_have_exact_material_partition` |
| `SYN-EVIDENCE-M2-SCENARIO-060` | `-` | `-` | `APPROVED` | `CLOSED` | `tests.test_sales_credit_models.ManagerOutcomeTests.test_all_five_human_outcomes_have_separate_coherent_records` |
| `SYN-EVIDENCE-M2-SCENARIO-061` | `-` | `-` | `DENIED` | `CLOSED` | `tests.test_sales_credit_models.ManagerOutcomeTests.test_all_five_human_outcomes_have_separate_coherent_records` |
| `SYN-EVIDENCE-M2-SCENARIO-062` | `-` | `-` | `PARTIAL` | `CLOSED` | `tests.test_sales_credit_models.ManagerOutcomeTests.test_all_five_human_outcomes_have_separate_coherent_records` |
| `SYN-EVIDENCE-M2-SCENARIO-063` | `-` | `-` | `OTHER_REP` | `CLOSED` | `tests.test_sales_credit_models.ManagerOutcomeTests.test_all_five_human_outcomes_have_separate_coherent_records` |
| `SYN-EVIDENCE-M2-SCENARIO-064` | `-` | `-` | `NOT_PURSUED` | `CLOSED` | `tests.test_sales_credit_models.ManagerOutcomeTests.test_all_five_human_outcomes_have_separate_coherent_records` |
| `SYN-EVIDENCE-M2-SCENARIO-065` | `-` | `-` | `-` | `AWAITING_SOURCE_REVIEW` | `tests.test_sales_credit_accumulator.ReplayAndAtomicityTests.test_exact_replay_returns_the_original_logical_result_without_duplication` |
| `SYN-EVIDENCE-M2-SCENARIO-066` | `-` | `-` | `-` | `CLOSED` | `tests.test_sales_credit_accumulator.OutcomeClosureAndPurgeTests.test_manager_outcome_is_separate_replay_safe_and_blocks_later_mutation` |

## Workflow ownership

| Workflow | Owning synthetic scenario |
|---|---|
| `AWAITING_SOURCE_REVIEW` | `SYN-EVIDENCE-M2-SCENARIO-065` |
| `CHECKED_NO_ORDER_WINDOW_ACTIVE` | `SYN-EVIDENCE-M2-SCENARIO-003` |
| `REVIEW_WINDOW_CLOSED_NO_ORDER` | `SYN-EVIDENCE-M2-SCENARIO-004` |
| `CREDIT_CONFIRMED_TARGET_REP` | `SYN-EVIDENCE-M2-SCENARIO-017` |
| `EVIDENCE_NEEDED` | `SYN-EVIDENCE-M2-SCENARIO-019` |
| `VERIFIED_PREORDER_EVIDENCE` | `SYN-EVIDENCE-M2-SCENARIO-023` |
| `OUTBOUND_EVIDENCE_HUMAN_REVIEW` | `SYN-EVIDENCE-M2-SCENARIO-026` |
| `INBOUND_EVIDENCE_HUMAN_REVIEW` | `SYN-EVIDENCE-M2-SCENARIO-025` |
| `TIMING_UNCERTAIN_HUMAN_REVIEW` | `SYN-EVIDENCE-M2-SCENARIO-009` |
| `OTHER_REP_HUMAN_REVIEW` | `SYN-EVIDENCE-M2-SCENARIO-020` |
| `ORDER_CHANGED_HUMAN_REVIEW` | `SYN-EVIDENCE-M2-SCENARIO-013` |
| `CANCELED_REPLACEMENT_WINDOW_ACTIVE` | `SYN-EVIDENCE-M2-SCENARIO-007` |
| `POSSIBLE_REPLACEMENT_HUMAN_REVIEW` | `SYN-EVIDENCE-M2-SCENARIO-034` |
| `CANCELED_NO_REPLACEMENT` | `SYN-EVIDENCE-M2-SCENARIO-008` |
| `MANUAL_REVIEW_REQUIRED` | `SYN-EVIDENCE-M2-SCENARIO-001` |
| `CLOSED` | `SYN-EVIDENCE-M2-SCENARIO-060` |

## Acceptance coverage

| ID | Family | Requirement | Test selectors |
|---|---|---|---|
| `SCHEMA_FIELDS` | `SCHEMA_AND_NORMALIZATION` | Required, optional, and conditional fields. | `tests.test_sales_credit_models.ClosedModelShapeTests.test_required_constructor_fields_are_exact` |
| `SCHEMA_TIMESTAMPS` | `SCHEMA_AND_NORMALIZATION` | Timezone-aware timestamps and timestamp precision. | `tests.test_sales_credit_models.InteractionRecordTests.test_review_dates_are_exact_new_york_anchor_plus_fourteen` |
| `SCHEMA_MONEY` | `SCHEMA_AND_NORMALIZATION` | Exact nonnegative decimal money and integer quantity. | `tests.test_sales_credit_models.LineItemSnapshotTests.test_quantity_money_and_tuple_shapes_are_strict` |
| `SCHEMA_EMAIL` | `SCHEMA_AND_NORMALIZATION` | ASCII-four-trim and ASCII-lowercase email normalization. | `tests.test_sales_credit_discovery.ContactNormalizationTests.test_email_uses_ascii_four_trim_and_ascii_lowercase` |
| `SCHEMA_PHONE` | `SCHEMA_AND_NORMALIZATION` | Fictional phone normalization without guessed digits. | `tests.test_sales_credit_discovery.ContactNormalizationTests.test_phone_accepts_only_firewall_formats_and_never_guesses_area_code` |
| `SCHEMA_MALFORMED_PHONE` | `SCHEMA_AND_NORMALIZATION` | Malformed or non-fictional phones fail closed. | `tests.test_sales_credit_discovery.ContactNormalizationTests.test_malformed_or_nonfictional_phone_rejects_without_correction` |
| `WINDOW_INCLUSIVE` | `WINDOWS` | Interaction date plus fourteen full calendar days is inclusive. | `tests.test_sales_credit_windows.CalendarWindowTests.test_timezone_and_ordinary_inclusive_fourteen_day_window` |
| `WINDOW_DST` | `WINDOWS` | Spring and fall DST do not alter local-date windows. | `tests.test_sales_credit_windows.CalendarWindowTests.test_spring_and_fall_dst_do_not_change_calendar_day_count` |
| `WINDOW_TIMING` | `WINDOWS` | Same-day uncertain ordering never proves qualification. | `tests.test_sales_credit_windows.TimingClassificationTests.test_same_day_unreliable_never_proves_order_qualification` |
| `WINDOW_REPLACEMENT` | `WINDOWS` | Cancellation opens an independently extended replacement window. | `tests.test_sales_credit_windows.CalendarWindowTests.test_cancellation_has_its_own_window_that_may_extend_review` |
| `WINDOW_RECHECK` | `WINDOWS` | Automatic recheck is limited to once per New York local date. | `tests.test_sales_credit_windows.RecheckEligibilityTests.test_automatic_check_is_eligible_once_per_new_york_date` |
| `WINDOW_FORCE` | `WINDOWS` | Selected force recheck bypasses only the daily throttle and is audited. | `tests.test_sales_credit_windows.RecheckEligibilityTests.test_selected_force_bypasses_only_daily_throttle_and_is_audited` |
| `DISCOVERY_BOTH_IDS` | `DISCOVERY` | Every valid email and phone is searched. | `tests.test_sales_credit_discovery.DiscoveryCombinationTests.test_both_identifiers_are_mandatory_and_union_deduplicates_order_ids` |
| `DISCOVERY_COMPLETE` | `DISCOVERY` | Complete native result sets are combined without early exit. | `tests.test_sales_credit_discovery.DiscoveryCombinationTests.test_observed_candidates_survive_incomplete_enumeration_for_evaluation` |
| `DISCOVERY_DEDUPE` | `DISCOVERY` | Canonical Order Number deduplication is deterministic. | `tests.test_sales_credit_discovery.DiscoveryCombinationTests.test_result_order_does_not_change_deterministic_union` |
| `DISCOVERY_INCOMPLETE` | `DISCOVERY` | Incomplete enumeration cannot conclude no-order. | `tests.test_sales_credit_discovery.DiscoveryCombinationTests.test_missing_or_incomplete_identifier_can_never_conclude_no_order, tests.test_sales_credit_no_order_closure.PostEvaluationNoOrderReducerTests.test_incomplete_enumeration_applies_governed_manual_state` |
| `DISCOVERY_EMPTY` | `DISCOVERY` | Complete empty results distinguish active and closed windows. | `tests.test_sales_credit_accumulator.DiscoveryBatchAuthorityTests.test_state_is_the_only_supported_no_order_entrypoint, tests.test_sales_credit_discovery.DiscoveryCombinationTests.test_complete_empty_union_uses_exact_active_and_closed_states` |
| `RULE_REP` | `RULES` | Target, web, other, missing, and unrecognized rep branches. | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_every_exact_order_rep_branch_and_no_line_rep_substitution` |
| `RULE_EVIDENCE` | `RULES` | Every contact-evidence classification and timing branch. | `tests.test_sales_credit_evaluator.EvidenceClassificationTests.test_every_binding_evidence_branch` |
| `RULE_CANCELLATION` | `RULES` | Canceled orders and open or expired replacement windows. | `tests.test_sales_credit_evaluator.CancellationAndReplacementTests.test_canceled_order_open_and_expired_windows_have_zero_active_value` |
| `RULE_CONTINUITY` | `RULES` | Exact ES, exact MFG/OE, nonexact, and absent product continuity. | `tests.test_sales_credit_evaluator.CancellationAndReplacementTests.test_exact_es_mfg_one_among_many_nonexact_and_absent_branches` |
| `RULE_CUSTOMER` | `RULES` | Customer mismatch and unproved continuity fail closed. | `tests.test_sales_credit_evaluator.CancellationAndReplacementTests.test_customer_absence_and_incomplete_lines_cannot_prove_replacement` |
| `RULE_MATERIAL` | `RULES` | All material and routine lifecycle change kinds. | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_each_material_change_overrides_workflow_but_not_attribution, tests.test_sales_credit_evaluator.AttributionAndValueTests.test_routine_changes_are_nonmaterial_but_current_value_never_substitutes` |
| `RULE_VALUE` | `RULES` | Placed value is exact and current value is never substituted. | `tests.test_sales_credit_evaluator.AttributionAndValueTests.test_routine_changes_are_nonmaterial_but_current_value_never_substitutes` |
| `CASE_ATTACH` | `CASE_IDENTITY` | Multiple interactions attach to one logical order case. | `tests.test_sales_credit_accumulator.DiscoveryBatchAuthorityTests.test_complete_multi_candidate_discovery_is_atomic_and_has_no_early_exit, tests.test_sales_credit_accumulator.DiscoveryBatchAuthorityTests.test_mixed_positive_and_terminal_effects_commit_atomically, tests.test_sales_credit_accumulator.ReplayAndAtomicityTests.test_distinct_commands_union_facts_without_double_counting` |
| `CASE_REPLAY` | `CASE_IDENTITY` | Exact replay returns the original logical result. | `tests.test_sales_credit_accumulator.ReplayAndAtomicityTests.test_exact_replay_returns_the_original_logical_result_without_duplication` |
| `CASE_CONFLICT` | `CASE_IDENTITY` | Conflicting replay and digest collision fail safely. | `tests.test_sales_credit_accumulator.ReplayAndAtomicityTests.test_equal_digest_different_bytes_is_a_collision_not_replay, tests.test_sales_credit_accumulator.ReplayAndAtomicityTests.test_same_command_different_material_is_a_conflict` |
| `CASE_OUTCOME` | `CASE_IDENTITY` | Human outcome is separate and replay-safe. | `tests.test_sales_credit_accumulator.OutcomeClosureAndPurgeTests.test_manager_outcome_is_separate_replay_safe_and_blocks_later_mutation` |
| `RETENTION_MINIMIZE` | `RETENTION` | Closure atomically writes minimized governed metadata. | `tests.test_sales_credit_accumulator.OutcomeClosureAndPurgeTests.test_closure_is_atomic_minimization_and_exact_replay, tests.test_sales_credit_retention.ClosureProjectionTests.test_human_closure_preserves_only_minimized_governed_metadata` |
| `RETENTION_SYSTEM` | `RETENTION` | Terminal system closure fabricates no human outcome. | `tests.test_sales_credit_retention.ClosureProjectionTests.test_terminal_system_closure_requires_no_fabricated_human_outcome` |
| `RETENTION_BOUNDARY` | `RETENTION` | Purge begins at exactly ninety elapsed days. | `tests.test_sales_credit_retention.PurgeBoundaryTests.test_exact_elapsed_ninety_day_nanosecond_boundary` |
| `RETENTION_IDEMPOTENT` | `RETENTION` | Purge is idempotent and removes identity-bearing receipts. | `tests.test_sales_credit_accumulator.OutcomeClosureAndPurgeTests.test_purge_boundary_is_idempotent_and_deletes_identity_receipts` |
| `SAFETY_NO_UI` | `SAFETY` | No portal, write API, dashboard, or extension exists in Milestone 2. | `tests.test_milestone_boundary.MilestoneBoundaryTests.test_milestone_three_and_user_interface_modules_are_absent` |
| `SAFETY_NO_NETWORK` | `SAFETY` | Package code imports no network client. | `tests.test_milestone_boundary.MilestoneBoundaryTests.test_package_has_no_network_client_import` |
| `SAFETY_COUNTERS` | `SAFETY` | All nine safety counters remain zero. | `tests.test_foundation_audit.FoundationAuditTests.test_all_safety_counters_are_zero` |
| `SAFETY_PAYLOAD` | `SAFETY` | Malformed or private payloads fail closed without echo. | `tests.test_sales_credit_evaluator.ExplanationAndSafetyTests.test_wrong_shapes_and_private_payloads_reject_without_echo` |
| `METRICS_DEFINITIONS` | `METRICS` | Pure aggregate definitions, rates, latency, and agreement are exact. | `tests.test_sales_credit_metrics.AggregateMetricsTests.test_aggregate_definitions_median_nearest_rank_and_agreement_are_exact` |
| `METRICS_REPLAY` | `METRICS` | Exact duplicate observations are idempotent and conflicts fail. | `tests.test_sales_credit_metrics.AggregateMetricsTests.test_exact_duplicate_is_idempotent_and_conflicting_duplicate_fails` |
| `METRICS_PRIVACY` | `METRICS` | Aggregate output contains no identity or contact detail. | `tests.test_sales_credit_metrics.AggregateMetricsTests.test_input_shape_is_closed_and_output_contains_no_identity_or_contact_detail` |

## Safety counters

| Counter | Expected |
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
