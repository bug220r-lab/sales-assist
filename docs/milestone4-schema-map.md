# Milestone 4 logical schema map

```text
shared migration / safety / replay / telemetry / maintenance
             |                         |
     Sales Credit root          DOI run/case roots
       |            |          |                 |
 immutable facts  projection  immutable events  projections
       |            |          |                 |
 minimized audit / aggregate   KPI aggregate / graph purge
```

There is no Sales Credit-to-DOI foreign key and no external-system capability.

## Shared and system tables

- `_schema_migrations`
- `application_metadata`
- `backup_receipts`
- `durable_command_receipts`
- `durable_commands`
- `durable_receipt_owners`
- `processing_telemetry`
- `restore_receipts`
- `structured_domain_failures`
- `system_safety_counters`
- `telemetry_safety_counters`

## Sales Credit tables

- `sc_active_replacement_links`
- `sc_case_evaluations`
- `sc_case_events`
- `sc_case_evidence`
- `sc_case_interactions`
- `sc_case_search_runs`
- `sc_case_snapshots`
- `sc_cases`
- `sc_closed_audits`
- `sc_daily_aggregates`
- `sc_evaluation_reasons`
- `sc_evaluations`
- `sc_evidence_events`
- `sc_interactions`
- `sc_manager_outcomes`
- `sc_no_order_closed_audits`
- `sc_replacement_candidates`
- `sc_search_identifiers`
- `sc_search_result_orders`
- `sc_search_runs`
- `sc_snapshot_lines`
- `sc_snapshots`

## DOI tables

- `doi_action_verification_events`
- `doi_attempt_batch_references`
- `doi_case_artifacts`
- `doi_case_projections`
- `doi_case_source_batch_references`
- `doi_cases`
- `doi_evaluation_reasons`
- `doi_evaluations`
- `doi_extraction_attempts`
- `doi_interventions`
- `doi_kpi_contribution_events`
- `doi_kpi_daily_buckets`
- `doi_line_continuity_proof_references`
- `doi_line_snapshots`
- `doi_opportunities`
- `doi_opportunity_scope_components`
- `doi_order_snapshots`
- `doi_owner_events`
- `doi_owner_stream_anchors`
- `doi_owner_streams`
- `doi_product_observations`
- `doi_product_relationship_revisions`
- `doi_product_relationships`
- `doi_rejected_source_records`
- `doi_resulting_order_link_revisions`
- `doi_resulting_order_links`
- `doi_resulting_order_mapping_components`
- `doi_resulting_order_search_events`
- `doi_resulting_order_searches`
- `doi_retained_kpi_contributions`
- `doi_retention_deadlines`
- `doi_run_control_receipts`
- `doi_run_events`
- `doi_run_material_events`
- `doi_run_projections`
- `doi_run_work_dispositions`
- `doi_run_work_items`
- `doi_runs`
- `doi_snapshot_completeness_proof_references`
- `doi_source_batches`
- `doi_source_import_aggregates`
- `doi_source_import_attempt_events`
- `doi_source_import_attempts`
- `doi_staged_order_source_refs`
- `doi_staged_orders`
- `doi_value_events`
