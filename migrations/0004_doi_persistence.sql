-- Milestone 4 durable DOI persistence.  All payloads are closed, synthetic domain records.

CREATE TABLE doi_source_batches (
    batch_id TEXT PRIMARY KEY,
    source_identity_id TEXT NOT NULL,
    identity_domain TEXT NOT NULL,
    identity_sha256 TEXT NOT NULL CHECK (length(identity_sha256) = 64),
    identity_canonical_bytes BLOB NOT NULL CHECK (typeof(identity_canonical_bytes) = 'blob'),
    record_domain TEXT NOT NULL,
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
    record_canonical_bytes BLOB NOT NULL CHECK (typeof(record_canonical_bytes) = 'blob'),
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob'),
    mapping_version TEXT NOT NULL,
    finite_extent INTEGER NOT NULL CHECK (finite_extent >= 0),
    status TEXT NOT NULL CHECK (status = 'READY'),
    UNIQUE (identity_domain, identity_sha256)
);

CREATE TABLE doi_runs (
    run_id TEXT PRIMARY KEY,
    invocation_id TEXT NOT NULL UNIQUE,
    run_type TEXT NOT NULL CHECK (run_type IN ('RUN_DOI_REVIEW', 'RECHECK_ORDER', 'RECHECK_DEDUPE_ORDER')),
    recheck_order_id TEXT,
    started_at TEXT NOT NULL,
    CHECK ((run_type = 'RUN_DOI_REVIEW') = (recheck_order_id IS NULL))
);

CREATE TABLE doi_run_projections (
    run_id TEXT PRIMARY KEY REFERENCES doi_runs(run_id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('IN_PROGRESS', 'COMPLETED', 'COMPLETED_WITH_EXCEPTIONS', 'FAILED')),
    projection_version INTEGER NOT NULL CHECK (projection_version > 0),
    head_sha256 TEXT NOT NULL CHECK (length(head_sha256) = 64),
    material_version INTEGER NOT NULL CHECK (material_version > 0),
    material_event_sha256 TEXT NOT NULL CHECK (length(material_event_sha256) = 64),
    source_batch_id TEXT REFERENCES doi_source_batches(batch_id),
    completed_at TEXT,
    purge_eligible_at TEXT,
    source_attempt_count INTEGER NOT NULL CHECK (source_attempt_count >= 0),
    work_item_count INTEGER NOT NULL CHECK (work_item_count >= 0),
    disposition_subject_count INTEGER NOT NULL CHECK (disposition_subject_count >= 0),
    successful_evaluation_count INTEGER NOT NULL CHECK (successful_evaluation_count >= 0),
    order_exception_count INTEGER NOT NULL CHECK (order_exception_count >= 0),
    blocked_order_count INTEGER NOT NULL CHECK (blocked_order_count >= 0),
    portal_read_count INTEGER NOT NULL CHECK (portal_read_count >= 0),
    record_domain TEXT NOT NULL,
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
    record_canonical_bytes BLOB NOT NULL CHECK (typeof(record_canonical_bytes) = 'blob'),
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob'),
    CHECK ((status = 'IN_PROGRESS') = (completed_at IS NULL AND purge_eligible_at IS NULL)),
    CHECK (disposition_subject_count = successful_evaluation_count + order_exception_count + blocked_order_count),
    CHECK (disposition_subject_count <= work_item_count),
    CHECK (portal_read_count <= work_item_count)
);

CREATE TABLE doi_run_events (
    run_id TEXT NOT NULL REFERENCES doi_runs(run_id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL CHECK (sequence_no > 0),
    event_kind TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    predecessor_sha256 TEXT,
    record_domain TEXT NOT NULL,
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
    record_canonical_bytes BLOB NOT NULL CHECK (typeof(record_canonical_bytes) = 'blob'),
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob'),
    PRIMARY KEY (run_id, sequence_no),
    UNIQUE (run_id, record_sha256)
);

CREATE TABLE doi_run_material_events (
    run_id TEXT NOT NULL REFERENCES doi_runs(run_id) ON DELETE CASCADE,
    material_version INTEGER NOT NULL CHECK (material_version > 0),
    cause_sha256 TEXT NOT NULL CHECK (length(cause_sha256) = 64),
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
    PRIMARY KEY (run_id, material_version),
    UNIQUE (run_id, cause_sha256)
);

CREATE TABLE doi_source_import_attempts (
    attempt_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES doi_runs(run_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    source_identity_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('STARTED', 'SUCCEEDED', 'FAILED', 'ABORTED')),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    source_batch_id TEXT REFERENCES doi_source_batches(batch_id),
    portal_read_count INTEGER NOT NULL CHECK (portal_read_count = 0),
    projection_version INTEGER NOT NULL CHECK (projection_version > 0),
    head_sha256 TEXT NOT NULL CHECK (length(head_sha256) = 64),
    record_domain TEXT NOT NULL,
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
    record_canonical_bytes BLOB NOT NULL CHECK (typeof(record_canonical_bytes) = 'blob'),
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob'),
    UNIQUE (run_id, ordinal),
    CHECK ((state = 'STARTED') = (completed_at IS NULL)),
    CHECK ((state = 'SUCCEEDED') = (source_batch_id IS NOT NULL))
);

CREATE TABLE doi_source_import_attempt_events (
    attempt_id TEXT NOT NULL REFERENCES doi_source_import_attempts(attempt_id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL CHECK (sequence_no > 0),
    event_kind TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    predecessor_sha256 TEXT,
    record_domain TEXT NOT NULL,
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
    record_canonical_bytes BLOB NOT NULL CHECK (typeof(record_canonical_bytes) = 'blob'),
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob'),
    PRIMARY KEY (attempt_id, sequence_no),
    UNIQUE (attempt_id, record_sha256)
);

CREATE TABLE doi_attempt_batch_references (
    attempt_id TEXT PRIMARY KEY REFERENCES doi_source_import_attempts(attempt_id) ON DELETE CASCADE,
    batch_id TEXT NOT NULL REFERENCES doi_source_batches(batch_id)
);

CREATE TABLE doi_staged_orders (
    attempt_id TEXT NOT NULL REFERENCES doi_source_import_attempts(attempt_id) ON DELETE CASCADE,
    order_id TEXT NOT NULL,
    batch_id TEXT NOT NULL REFERENCES doi_source_batches(batch_id),
    record_domain TEXT NOT NULL,
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
    record_canonical_bytes BLOB NOT NULL CHECK (typeof(record_canonical_bytes) = 'blob'),
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob'),
    PRIMARY KEY (attempt_id, order_id)
);

CREATE TABLE doi_staged_order_source_refs (
    attempt_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    source_ref_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    PRIMARY KEY (attempt_id, order_id, source_ref_id),
    UNIQUE (attempt_id, order_id, ordinal),
    FOREIGN KEY (attempt_id, order_id) REFERENCES doi_staged_orders(attempt_id, order_id) ON DELETE CASCADE
);

CREATE TABLE doi_rejected_source_records (
    rejection_id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES doi_source_import_attempts(attempt_id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES doi_runs(run_id) ON DELETE CASCADE,
    batch_id TEXT REFERENCES doi_source_batches(batch_id),
    order_id TEXT NOT NULL,
    retention_state TEXT NOT NULL CHECK (retention_state IN ('PENDING_RUN_TERMINAL', 'RETAINED_UNTIL')),
    purge_eligible_at TEXT,
    record_domain TEXT NOT NULL,
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
    record_canonical_bytes BLOB NOT NULL CHECK (typeof(record_canonical_bytes) = 'blob'),
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob'),
    UNIQUE (run_id, order_id),
    CHECK ((retention_state = 'RETAINED_UNTIL') = (purge_eligible_at IS NOT NULL))
);

CREATE TABLE doi_run_work_items (
    work_item_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES doi_runs(run_id) ON DELETE CASCADE,
    order_id TEXT NOT NULL,
    origin TEXT NOT NULL,
    source_batch_id TEXT REFERENCES doi_source_batches(batch_id),
    record_domain TEXT NOT NULL,
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
    record_canonical_bytes BLOB NOT NULL CHECK (typeof(record_canonical_bytes) = 'blob'),
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob'),
    PRIMARY KEY (run_id, work_item_id),
    UNIQUE (run_id, order_id)
);

CREATE TABLE doi_run_work_dispositions (
    work_item_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES doi_runs(run_id) ON DELETE CASCADE,
    disposition_kind TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    record_domain TEXT NOT NULL,
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
    record_canonical_bytes BLOB NOT NULL CHECK (typeof(record_canonical_bytes) = 'blob'),
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob'),
    PRIMARY KEY (run_id, work_item_id),
    FOREIGN KEY (run_id, work_item_id)
        REFERENCES doi_run_work_items(run_id, work_item_id) ON DELETE CASCADE
);

CREATE TABLE doi_run_control_receipts (
    receipt_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES doi_runs(run_id) ON DELETE CASCADE,
    occurrence_key TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('RETRY', 'NO_RETRY_FINALIZATION', 'EXTRACTION_RESERVED', 'PRE_EXTRACTION_RULES_UNAVAILABLE')),
    material_domain TEXT NOT NULL,
    material_sha256 TEXT NOT NULL CHECK (length(material_sha256) = 64),
    material_canonical_bytes BLOB NOT NULL CHECK (typeof(material_canonical_bytes) = 'blob'),
    result_payload BLOB NOT NULL CHECK (typeof(result_payload) = 'blob'),
    committed_at TEXT NOT NULL,
    UNIQUE (run_id, occurrence_key)
);

CREATE TABLE doi_source_import_aggregates (
    month_key TEXT NOT NULL CHECK (month_key GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'),
    outcome_class TEXT NOT NULL CHECK (outcome_class IN ('SUCCEEDED', 'FAILED', 'ABORTED')),
    attempt_count INTEGER NOT NULL CHECK (attempt_count >= 0),
    PRIMARY KEY (month_key, outcome_class)
);

CREATE TABLE doi_cases (
    case_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE doi_case_projections (
    case_id TEXT PRIMARY KEY REFERENCES doi_cases(case_id) ON DELETE CASCADE,
    lifecycle_state TEXT NOT NULL CHECK (lifecycle_state IN ('ACTIVE', 'CLOSED_HARD', 'CLOSED_REVERSIBLE')),
    current_snapshot_id TEXT,
    current_evaluation_id TEXT,
    terminal_closure_reason TEXT,
    projection_version INTEGER NOT NULL CHECK (projection_version > 0),
    head_sha256 TEXT NOT NULL CHECK (length(head_sha256) = 64),
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob'),
    CHECK ((lifecycle_state = 'ACTIVE') = (terminal_closure_reason IS NULL))
);

CREATE TABLE doi_case_artifacts (
    artifact_pk INTEGER PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES doi_cases(case_id) ON DELETE CASCADE,
    artifact_kind TEXT NOT NULL CHECK (artifact_kind IN (
        'CASE_ADMISSION_PROOF', 'CASE_SOURCE_BINDING', 'EXTRACTION_ATTEMPT',
        'COMPLETENESS_PROOF', 'LINE_CONTINUITY_PROOF', 'ORDER_SNAPSHOT',
        'LINE_SNAPSHOT', 'EVALUATION',
        'OPPORTUNITY', 'MUTUAL_EXCLUSION', 'SCENARIO_SELECTION', 'ACTION_CONTEXT',
        'HUMAN_FACT', 'CONTACT', 'CONTACT_WORKFLOW', 'WWC', 'DEDUPE', 'ATTENTION',
        'INTERVENTION', 'RESULTING_SEARCH', 'RESULTING_LINK', 'KPI_CONTRIBUTION',
        'RETENTION_BINDING', 'LIFECYCLE_EVENT', 'COMMAND_RECEIPT'
    )),
    artifact_id TEXT NOT NULL,
    record_domain TEXT NOT NULL,
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
    record_canonical_bytes BLOB NOT NULL CHECK (typeof(record_canonical_bytes) = 'blob'),
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob'),
    created_at TEXT NOT NULL,
    UNIQUE (artifact_kind, artifact_id),
    UNIQUE (case_id, record_domain, record_sha256)
);

CREATE TABLE doi_case_source_batch_references (
    case_id TEXT NOT NULL REFERENCES doi_cases(case_id) ON DELETE CASCADE,
    batch_id TEXT NOT NULL REFERENCES doi_source_batches(batch_id),
    binding_artifact_pk INTEGER NOT NULL REFERENCES doi_case_artifacts(artifact_pk) ON DELETE CASCADE,
    admission_artifact_pk INTEGER NOT NULL REFERENCES doi_case_artifacts(artifact_pk) ON DELETE CASCADE,
    PRIMARY KEY (case_id, batch_id)
);

CREATE TABLE doi_extraction_attempts (
    attempt_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES doi_cases(case_id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES doi_runs(run_id) ON DELETE CASCADE,
    order_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('SUCCEEDED', 'FAILED')),
    snapshot_id TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    record_artifact_pk INTEGER NOT NULL REFERENCES doi_case_artifacts(artifact_pk) ON DELETE CASCADE,
    UNIQUE (run_id, order_id),
    CHECK ((status = 'SUCCEEDED') = (snapshot_id IS NOT NULL))
);

CREATE TABLE doi_order_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES doi_cases(case_id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES doi_runs(run_id) ON DELETE CASCADE,
    order_id TEXT NOT NULL,
    source_observed_at TEXT NOT NULL,
    completeness_sha256 TEXT NOT NULL CHECK (length(completeness_sha256) = 64),
    record_artifact_pk INTEGER NOT NULL UNIQUE REFERENCES doi_case_artifacts(artifact_pk) ON DELETE CASCADE
);

CREATE TABLE doi_line_snapshots (
    line_snapshot_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES doi_cases(case_id) ON DELETE CASCADE,
    snapshot_id TEXT NOT NULL REFERENCES doi_order_snapshots(snapshot_id) ON DELETE CASCADE,
    line_ordinal INTEGER NOT NULL CHECK (line_ordinal > 0),
    relevant_merchandise INTEGER NOT NULL CHECK (relevant_merchandise IN (0, 1)),
    continuity_state TEXT NOT NULL,
    record_artifact_pk INTEGER NOT NULL UNIQUE REFERENCES doi_case_artifacts(artifact_pk) ON DELETE CASCADE,
    UNIQUE (snapshot_id, line_ordinal)
);

CREATE TABLE doi_snapshot_completeness_proof_references (
    snapshot_id TEXT PRIMARY KEY REFERENCES doi_order_snapshots(snapshot_id) ON DELETE CASCADE,
    proof_artifact_pk INTEGER NOT NULL REFERENCES doi_case_artifacts(artifact_pk) ON DELETE CASCADE
);

CREATE TABLE doi_line_continuity_proof_references (
    line_snapshot_id TEXT PRIMARY KEY REFERENCES doi_line_snapshots(line_snapshot_id) ON DELETE CASCADE,
    proof_artifact_pk INTEGER NOT NULL REFERENCES doi_case_artifacts(artifact_pk) ON DELETE CASCADE
);

CREATE TABLE doi_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES doi_cases(case_id) ON DELETE CASCADE,
    snapshot_id TEXT NOT NULL REFERENCES doi_order_snapshots(snapshot_id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES doi_runs(run_id) ON DELETE CASCADE,
    order_id TEXT NOT NULL,
    top_level_state TEXT NOT NULL CHECK (top_level_state IN ('DOI_EXCLUDED', 'DOI_OPPORTUNITY', 'DOI_MANUAL_REVIEW', 'DOI_MONITOR')),
    transition_id TEXT NOT NULL,
    input_domain TEXT NOT NULL,
    input_sha256 TEXT NOT NULL CHECK (length(input_sha256) = 64),
    input_canonical_bytes BLOB NOT NULL CHECK (typeof(input_canonical_bytes) = 'blob'),
    output_domain TEXT NOT NULL,
    output_sha256 TEXT NOT NULL CHECK (length(output_sha256) = 64),
    output_canonical_bytes BLOB NOT NULL CHECK (typeof(output_canonical_bytes) = 'blob'),
    record_artifact_pk INTEGER NOT NULL UNIQUE REFERENCES doi_case_artifacts(artifact_pk) ON DELETE CASCADE,
    UNIQUE (snapshot_id, input_domain, input_sha256)
);

CREATE TABLE doi_evaluation_reasons (
    evaluation_id TEXT NOT NULL REFERENCES doi_evaluations(evaluation_id) ON DELETE CASCADE,
    reason_code TEXT NOT NULL,
    owning_transition_id TEXT,
    effective_overlay INTEGER NOT NULL CHECK (effective_overlay IN (0, 1)),
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    PRIMARY KEY (evaluation_id, reason_code),
    UNIQUE (evaluation_id, ordinal)
);

CREATE TABLE doi_opportunities (
    opportunity_id TEXT PRIMARY KEY,
    evaluation_id TEXT NOT NULL REFERENCES doi_evaluations(evaluation_id) ON DELETE CASCADE,
    case_id TEXT NOT NULL REFERENCES doi_cases(case_id) ON DELETE CASCADE,
    opportunity_type TEXT NOT NULL,
    potential_state TEXT NOT NULL CHECK (potential_state IN ('AVAILABLE', 'UNAVAILABLE', 'NOT_APPLICABLE')),
    amount_minor_units INTEGER,
    currency_code TEXT,
    currency_registry_version TEXT,
    currency_scale INTEGER,
    mutual_exclusion_group_id TEXT,
    record_artifact_pk INTEGER NOT NULL UNIQUE REFERENCES doi_case_artifacts(artifact_pk) ON DELETE CASCADE,
    CHECK ((potential_state = 'AVAILABLE') = (amount_minor_units IS NOT NULL AND currency_code IS NOT NULL AND currency_registry_version IS NOT NULL AND currency_scale IS NOT NULL))
);

CREATE TABLE doi_opportunity_scope_components (
    opportunity_id TEXT NOT NULL REFERENCES doi_opportunities(opportunity_id) ON DELETE CASCADE,
    line_snapshot_id TEXT NOT NULL REFERENCES doi_line_snapshots(line_snapshot_id) ON DELETE RESTRICT,
    role TEXT NOT NULL,
    quantity_text TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    PRIMARY KEY (opportunity_id, line_snapshot_id, role),
    UNIQUE (opportunity_id, ordinal)
);

CREATE TABLE doi_product_relationships (
    relationship_id TEXT PRIMARY KEY,
    relationship_type TEXT NOT NULL,
    ordered_sku TEXT NOT NULL,
    candidate_sku TEXT NOT NULL,
    current_revision INTEGER NOT NULL CHECK (current_revision > 0),
    current_state TEXT NOT NULL,
    head_sha256 TEXT NOT NULL CHECK (length(head_sha256) = 64),
    UNIQUE (relationship_type, ordered_sku, candidate_sku)
);

CREATE TABLE doi_product_relationship_revisions (
    relationship_id TEXT NOT NULL REFERENCES doi_product_relationships(relationship_id) ON DELETE CASCADE,
    revision_no INTEGER NOT NULL CHECK (revision_no > 0),
    revision_id TEXT NOT NULL UNIQUE,
    predecessor_sha256 TEXT,
    record_domain TEXT NOT NULL,
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
    record_canonical_bytes BLOB NOT NULL CHECK (typeof(record_canonical_bytes) = 'blob'),
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob'),
    PRIMARY KEY (relationship_id, revision_no)
);

CREATE TABLE doi_product_observations (
    observation_id TEXT PRIMARY KEY,
    relationship_id TEXT REFERENCES doi_product_relationships(relationship_id),
    case_id TEXT REFERENCES doi_cases(case_id) ON DELETE CASCADE,
    action_context_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    record_domain TEXT NOT NULL,
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
    record_canonical_bytes BLOB NOT NULL CHECK (typeof(record_canonical_bytes) = 'blob'),
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob')
);

CREATE TABLE doi_owner_streams (
    stream_id TEXT NOT NULL,
    stream_family TEXT NOT NULL CHECK (stream_family IN ('CASE', 'LIFECYCLE', 'ACTION_CONTEXT', 'CONTACT', 'CONTACT_WORKFLOW', 'WWC', 'DEDUPE', 'ATTENTION', 'HUMAN_FACT', 'RESULTING_SEARCH', 'RESULTING_LINK', 'INTERVENTION_VALUE', 'KPI')),
    case_id TEXT REFERENCES doi_cases(case_id) ON DELETE CASCADE,
    run_id TEXT REFERENCES doi_runs(run_id) ON DELETE CASCADE,
    current_state TEXT NOT NULL,
    sequence_no INTEGER NOT NULL CHECK (sequence_no >= 0),
    head_sha256 TEXT,
    projection_payload BLOB NOT NULL CHECK (typeof(projection_payload) = 'blob'),
    PRIMARY KEY (stream_family, stream_id),
    CHECK ((case_id IS NOT NULL) + (run_id IS NOT NULL) <= 1),
    CHECK ((sequence_no = 0) = (head_sha256 IS NULL))
);

CREATE TABLE doi_owner_stream_anchors (
    stream_family TEXT NOT NULL,
    stream_id TEXT NOT NULL,
    case_id TEXT REFERENCES doi_cases(case_id) ON DELETE CASCADE,
    run_id TEXT REFERENCES doi_runs(run_id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (stream_family, stream_id)
);

CREATE TABLE doi_owner_events (
    stream_family TEXT NOT NULL,
    stream_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    sequence_no INTEGER NOT NULL CHECK (sequence_no > 0),
    transition_id TEXT,
    projection_state TEXT NOT NULL,
    predecessor_sha256 TEXT,
    occurred_at TEXT NOT NULL,
    record_domain TEXT NOT NULL,
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
    record_canonical_bytes BLOB NOT NULL CHECK (typeof(record_canonical_bytes) = 'blob'),
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob'),
    PRIMARY KEY (stream_family, stream_id, sequence_no),
    UNIQUE (stream_family, event_id),
    FOREIGN KEY (stream_family, stream_id) REFERENCES doi_owner_streams(stream_family, stream_id) ON DELETE CASCADE
);

CREATE TABLE doi_interventions (
    intervention_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES doi_cases(case_id) ON DELETE CASCADE,
    opportunity_id TEXT NOT NULL REFERENCES doi_opportunities(opportunity_id) ON DELETE CASCADE,
    intervention_type TEXT NOT NULL,
    status TEXT NOT NULL,
    action_occurred_at TEXT,
    projection_version INTEGER NOT NULL CHECK (projection_version > 0),
    head_sha256 TEXT NOT NULL CHECK (length(head_sha256) = 64),
    record_artifact_pk INTEGER NOT NULL UNIQUE REFERENCES doi_case_artifacts(artifact_pk) ON DELETE CASCADE,
    UNIQUE (opportunity_id, intervention_type)
);

CREATE TABLE doi_action_verification_events (
    event_id TEXT PRIMARY KEY,
    intervention_id TEXT NOT NULL REFERENCES doi_interventions(intervention_id) ON DELETE CASCADE,
    occurrence_id TEXT NOT NULL,
    record_domain TEXT NOT NULL,
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
    record_canonical_bytes BLOB NOT NULL CHECK (typeof(record_canonical_bytes) = 'blob'),
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob'),
    UNIQUE (intervention_id, occurrence_id)
);

CREATE TABLE doi_value_events (
    intervention_id TEXT NOT NULL REFERENCES doi_interventions(intervention_id) ON DELETE CASCADE,
    event_id TEXT NOT NULL UNIQUE,
    sequence_no INTEGER NOT NULL CHECK (sequence_no > 0),
    occurrence_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    predecessor_sha256 TEXT,
    amount_minor_units INTEGER NOT NULL,
    currency_code TEXT NOT NULL,
    currency_registry_version TEXT NOT NULL,
    currency_scale INTEGER NOT NULL,
    record_domain TEXT NOT NULL,
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
    record_canonical_bytes BLOB NOT NULL CHECK (typeof(record_canonical_bytes) = 'blob'),
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob'),
    PRIMARY KEY (intervention_id, sequence_no),
    UNIQUE (intervention_id, occurrence_id)
);

CREATE TABLE doi_resulting_order_searches (
    search_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES doi_cases(case_id) ON DELETE CASCADE,
    parent_order_id TEXT NOT NULL,
    intervention_type TEXT NOT NULL,
    state TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    head_sha256 TEXT NOT NULL CHECK (length(head_sha256) = 64),
    projection_payload BLOB NOT NULL CHECK (typeof(projection_payload) = 'blob')
);

CREATE TABLE doi_resulting_order_search_events (
    search_id TEXT NOT NULL REFERENCES doi_resulting_order_searches(search_id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL CHECK (sequence_no > 0),
    event_id TEXT NOT NULL UNIQUE,
    predecessor_sha256 TEXT,
    record_domain TEXT NOT NULL,
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
    record_canonical_bytes BLOB NOT NULL CHECK (typeof(record_canonical_bytes) = 'blob'),
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob'),
    PRIMARY KEY (search_id, sequence_no)
);

CREATE TABLE doi_resulting_order_links (
    link_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES doi_cases(case_id) ON DELETE CASCADE,
    intervention_id TEXT NOT NULL REFERENCES doi_interventions(intervention_id) ON DELETE CASCADE,
    parent_order_id TEXT NOT NULL,
    child_order_id TEXT NOT NULL,
    state TEXT NOT NULL,
    current_revision INTEGER NOT NULL CHECK (current_revision > 0),
    head_sha256 TEXT NOT NULL CHECK (length(head_sha256) = 64),
    projection_payload BLOB NOT NULL CHECK (typeof(projection_payload) = 'blob'),
    UNIQUE (intervention_id, parent_order_id, child_order_id)
);

CREATE TABLE doi_resulting_order_link_revisions (
    link_id TEXT NOT NULL REFERENCES doi_resulting_order_links(link_id) ON DELETE CASCADE,
    revision_no INTEGER NOT NULL CHECK (revision_no > 0),
    revision_id TEXT NOT NULL UNIQUE,
    predecessor_sha256 TEXT,
    record_domain TEXT NOT NULL,
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
    record_canonical_bytes BLOB NOT NULL CHECK (typeof(record_canonical_bytes) = 'blob'),
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob'),
    PRIMARY KEY (link_id, revision_no)
);

CREATE TABLE doi_resulting_order_mapping_components (
    link_id TEXT NOT NULL,
    revision_no INTEGER NOT NULL,
    parent_line_id TEXT NOT NULL,
    child_line_id TEXT NOT NULL,
    quantity_text TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    PRIMARY KEY (link_id, revision_no, parent_line_id, child_line_id),
    UNIQUE (link_id, revision_no, ordinal),
    FOREIGN KEY (link_id, revision_no) REFERENCES doi_resulting_order_link_revisions(link_id, revision_no) ON DELETE CASCADE
);

CREATE TABLE doi_kpi_contribution_events (
    intervention_id TEXT NOT NULL REFERENCES doi_interventions(intervention_id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL CHECK (sequence_no > 0),
    event_id TEXT NOT NULL UNIQUE,
    predecessor_sha256 TEXT,
    record_domain TEXT NOT NULL,
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
    record_canonical_bytes BLOB NOT NULL CHECK (typeof(record_canonical_bytes) = 'blob'),
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob'),
    PRIMARY KEY (intervention_id, sequence_no)
);

CREATE TABLE doi_retained_kpi_contributions (
    intervention_id TEXT PRIMARY KEY REFERENCES doi_interventions(intervention_id) ON DELETE CASCADE,
    case_id TEXT NOT NULL REFERENCES doi_cases(case_id) ON DELETE CASCADE,
    intervention_type TEXT NOT NULL,
    action_date TEXT NOT NULL,
    amount_minor_units INTEGER NOT NULL,
    currency_code TEXT NOT NULL,
    currency_registry_version TEXT NOT NULL,
    currency_scale INTEGER NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    head_sha256 TEXT NOT NULL CHECK (length(head_sha256) = 64),
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob')
);

CREATE TABLE doi_kpi_daily_buckets (
    action_date TEXT NOT NULL,
    intervention_type TEXT NOT NULL,
    currency_code TEXT NOT NULL,
    currency_registry_version TEXT NOT NULL,
    currency_scale INTEGER NOT NULL,
    amount_minor_units INTEGER NOT NULL,
    intervention_count INTEGER NOT NULL CHECK (intervention_count >= 0),
    PRIMARY KEY (action_date, intervention_type, currency_code, currency_registry_version, currency_scale)
);

CREATE TABLE doi_retention_deadlines (
    deadline_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES doi_cases(case_id) ON DELETE CASCADE,
    closure_event_id TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL,
    closure_reason TEXT NOT NULL,
    closed_at TEXT NOT NULL,
    purge_eligible_at TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    timezone_database_binding TEXT NOT NULL,
    canceled_by_reopen_event_id TEXT,
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob')
);

CREATE UNIQUE INDEX doi_one_active_retention_deadline
    ON doi_retention_deadlines(case_id)
    WHERE canceled_by_reopen_event_id IS NULL;

CREATE INDEX doi_run_status_index ON doi_run_projections(status, completed_at);
CREATE INDEX doi_attempt_run_index ON doi_source_import_attempts(run_id, ordinal);
CREATE INDEX doi_case_order_index ON doi_cases(order_id);
CREATE INDEX doi_snapshot_case_index ON doi_order_snapshots(case_id, source_observed_at);
CREATE INDEX doi_evaluation_case_index ON doi_evaluations(case_id, evaluation_id);
CREATE INDEX doi_owner_event_head_index ON doi_owner_events(stream_family, stream_id, sequence_no);
CREATE INDEX doi_retention_due_index ON doi_retention_deadlines(purge_eligible_at) WHERE canceled_by_reopen_event_id IS NULL;

CREATE TRIGGER doi_run_event_sequence_guard
BEFORE INSERT ON doi_run_events
BEGIN
    SELECT CASE WHEN NEW.sequence_no != COALESCE((SELECT MAX(sequence_no) + 1 FROM doi_run_events WHERE run_id = NEW.run_id), 1)
        THEN RAISE(ABORT, 'DOI_RUN_EVENT_SEQUENCE_CONFLICT') END;
    SELECT CASE WHEN NEW.sequence_no = 1 AND NEW.predecessor_sha256 IS NOT NULL
        THEN RAISE(ABORT, 'DOI_RUN_EVENT_PREDECESSOR_CONFLICT') END;
    SELECT CASE WHEN NEW.sequence_no > 1 AND NEW.predecessor_sha256 IS NOT (SELECT record_sha256 FROM doi_run_events WHERE run_id = NEW.run_id AND sequence_no = NEW.sequence_no - 1)
        THEN RAISE(ABORT, 'DOI_RUN_EVENT_PREDECESSOR_CONFLICT') END;
END;

CREATE TRIGGER doi_attempt_event_sequence_guard
BEFORE INSERT ON doi_source_import_attempt_events
BEGIN
    SELECT CASE WHEN NEW.sequence_no != COALESCE((SELECT MAX(sequence_no) + 1 FROM doi_source_import_attempt_events WHERE attempt_id = NEW.attempt_id), 1)
        THEN RAISE(ABORT, 'DOI_ATTEMPT_EVENT_SEQUENCE_CONFLICT') END;
    SELECT CASE WHEN NEW.sequence_no = 1 AND NEW.predecessor_sha256 IS NOT NULL
        THEN RAISE(ABORT, 'DOI_ATTEMPT_EVENT_PREDECESSOR_CONFLICT') END;
    SELECT CASE WHEN NEW.sequence_no > 1 AND NEW.predecessor_sha256 IS NOT (SELECT record_sha256 FROM doi_source_import_attempt_events WHERE attempt_id = NEW.attempt_id AND sequence_no = NEW.sequence_no - 1)
        THEN RAISE(ABORT, 'DOI_ATTEMPT_EVENT_PREDECESSOR_CONFLICT') END;
END;

CREATE TRIGGER doi_owner_event_sequence_guard
BEFORE INSERT ON doi_owner_events
BEGIN
    SELECT CASE WHEN NEW.sequence_no != COALESCE((SELECT MAX(sequence_no) + 1 FROM doi_owner_events WHERE stream_family = NEW.stream_family AND stream_id = NEW.stream_id), 1)
        THEN RAISE(ABORT, 'DOI_OWNER_EVENT_SEQUENCE_CONFLICT') END;
    SELECT CASE WHEN NEW.sequence_no = 1 AND NEW.predecessor_sha256 IS NOT NULL
        THEN RAISE(ABORT, 'DOI_OWNER_EVENT_PREDECESSOR_CONFLICT') END;
    SELECT CASE WHEN NEW.sequence_no > 1 AND NEW.predecessor_sha256 IS NOT (SELECT record_sha256 FROM doi_owner_events WHERE stream_family = NEW.stream_family AND stream_id = NEW.stream_id AND sequence_no = NEW.sequence_no - 1)
        THEN RAISE(ABORT, 'DOI_OWNER_EVENT_PREDECESSOR_CONFLICT') END;
END;

CREATE TRIGGER doi_value_event_sequence_guard
BEFORE INSERT ON doi_value_events
BEGIN
    SELECT CASE WHEN NEW.sequence_no != COALESCE((SELECT MAX(sequence_no) + 1 FROM doi_value_events WHERE intervention_id = NEW.intervention_id), 1)
        THEN RAISE(ABORT, 'DOI_VALUE_EVENT_SEQUENCE_CONFLICT') END;
    SELECT CASE WHEN NEW.sequence_no = 1 AND NEW.predecessor_sha256 IS NOT NULL
        THEN RAISE(ABORT, 'DOI_VALUE_EVENT_PREDECESSOR_CONFLICT') END;
    SELECT CASE WHEN NEW.sequence_no > 1 AND NEW.predecessor_sha256 IS NOT (SELECT record_sha256 FROM doi_value_events WHERE intervention_id = NEW.intervention_id AND sequence_no = NEW.sequence_no - 1)
        THEN RAISE(ABORT, 'DOI_VALUE_EVENT_PREDECESSOR_CONFLICT') END;
END;

CREATE TRIGGER doi_immutable_source_batch BEFORE UPDATE ON doi_source_batches BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_run BEFORE UPDATE ON doi_runs BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_run_event BEFORE UPDATE ON doi_run_events BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_run_material_event BEFORE UPDATE ON doi_run_material_events BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_attempt_event BEFORE UPDATE ON doi_source_import_attempt_events BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_attempt_batch_reference BEFORE UPDATE ON doi_attempt_batch_references BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_staged_order BEFORE UPDATE ON doi_staged_orders BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_staged_order_source_ref BEFORE UPDATE ON doi_staged_order_source_refs BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_rejected_source_material
BEFORE UPDATE OF
    rejection_id,
    attempt_id,
    run_id,
    batch_id,
    order_id,
    record_domain,
    record_sha256,
    record_canonical_bytes,
    record_payload
ON doi_rejected_source_records
BEGIN
    SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD');
END;
CREATE TRIGGER doi_immutable_work_item BEFORE UPDATE ON doi_run_work_items BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_disposition BEFORE UPDATE ON doi_run_work_dispositions BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_run_control_receipt BEFORE UPDATE ON doi_run_control_receipts BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_case BEFORE UPDATE ON doi_cases BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_case_artifact BEFORE UPDATE ON doi_case_artifacts BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_case_source_reference BEFORE UPDATE ON doi_case_source_batch_references BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_extraction_attempt BEFORE UPDATE ON doi_extraction_attempts BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_snapshot BEFORE UPDATE ON doi_order_snapshots BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_line_snapshot BEFORE UPDATE ON doi_line_snapshots BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_snapshot_proof_reference BEFORE UPDATE ON doi_snapshot_completeness_proof_references BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_line_proof_reference BEFORE UPDATE ON doi_line_continuity_proof_references BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_evaluation BEFORE UPDATE ON doi_evaluations BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_evaluation_reason BEFORE UPDATE ON doi_evaluation_reasons BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_opportunity BEFORE UPDATE ON doi_opportunities BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_opportunity_scope BEFORE UPDATE ON doi_opportunity_scope_components BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_relationship_revision BEFORE UPDATE ON doi_product_relationship_revisions BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_product_observation BEFORE UPDATE ON doi_product_observations BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_owner_event BEFORE UPDATE ON doi_owner_events BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_owner_stream_anchor BEFORE UPDATE ON doi_owner_stream_anchors BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_action_event BEFORE UPDATE ON doi_action_verification_events BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_value_event BEFORE UPDATE ON doi_value_events BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_search_event BEFORE UPDATE ON doi_resulting_order_search_events BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_link_revision BEFORE UPDATE ON doi_resulting_order_link_revisions BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_link_mapping BEFORE UPDATE ON doi_resulting_order_mapping_components BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;
CREATE TRIGGER doi_immutable_kpi_event BEFORE UPDATE ON doi_kpi_contribution_events BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END;

UPDATE application_metadata
SET latest_schema_version = 4
WHERE singleton = 1;
