-- Milestone 4 durable Sales Credit graph and minimized retention survivors.
CREATE TABLE sc_cases (
    order_id TEXT PRIMARY KEY COLLATE BINARY CHECK (order_id GLOB 'SYN-ORDER-*'),
    projection_version INTEGER NOT NULL CHECK (projection_version >= 1),
    workflow_state TEXT NOT NULL COLLATE BINARY CHECK (length(workflow_state) BETWEEN 1 AND 64),
    attribution TEXT NOT NULL COLLATE BINARY CHECK (length(attribution) BETWEEN 1 AND 64),
    order_value_status TEXT NOT NULL COLLATE BINARY CHECK (length(order_value_status) BETWEEN 1 AND 64),
    placed_minor_units TEXT COLLATE BINARY
        CHECK (placed_minor_units IS NULL OR placed_minor_units GLOB '-[0-9]*' OR placed_minor_units GLOB '[0-9]*'),
    placed_currency TEXT COLLATE BINARY CHECK (placed_currency IS NULL OR length(placed_currency) = 3),
    placed_registry_version TEXT COLLATE BINARY,
    placed_scale INTEGER CHECK (placed_scale IS NULL OR placed_scale BETWEEN 0 AND 9),
    manager_occurrence_id TEXT COLLATE BINARY,
    replacement_parent_order_id TEXT COLLATE BINARY CHECK (replacement_parent_order_id IS NULL OR replacement_parent_order_id GLOB 'SYN-ORDER-*'),
    current_evaluation_id TEXT COLLATE BINARY,
    last_event_sequence INTEGER NOT NULL CHECK (last_event_sequence >= 1),
    last_event_id TEXT NOT NULL COLLATE BINARY,
    created_at TEXT NOT NULL COLLATE BINARY CHECK (created_at GLOB '*Z'),
    updated_at TEXT NOT NULL COLLATE BINARY CHECK (updated_at GLOB '*Z'),
    CHECK (
        (placed_minor_units IS NULL AND placed_currency IS NULL AND placed_registry_version IS NULL AND placed_scale IS NULL)
        OR
        (placed_minor_units IS NOT NULL AND placed_currency IS NOT NULL AND placed_registry_version IS NOT NULL AND placed_scale IS NOT NULL)
    )
) STRICT;

CREATE INDEX sc_cases_workflow_idx ON sc_cases(workflow_state, updated_at);

CREATE TABLE sc_case_events (
    event_id TEXT PRIMARY KEY COLLATE BINARY CHECK (event_id GLOB 'SYN-EVIDENCE-*'),
    order_id TEXT NOT NULL COLLATE BINARY CHECK (order_id GLOB 'SYN-ORDER-*'),
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    predecessor_event_id TEXT COLLATE BINARY REFERENCES sc_case_events(event_id),
    event_kind TEXT NOT NULL COLLATE BINARY
        CHECK (event_kind IN ('CASE_CREATED', 'FACTS_APPENDED', 'OUTCOME_RECORDED', 'CLOSED_MINIMIZED', 'REPLACEMENT_PARENT_DETACHED')),
    workflow_state TEXT NOT NULL COLLATE BINARY CHECK (length(workflow_state) BETWEEN 1 AND 64),
    attribution TEXT NOT NULL COLLATE BINARY CHECK (length(attribution) BETWEEN 1 AND 64),
    order_value_status TEXT NOT NULL COLLATE BINARY CHECK (length(order_value_status) BETWEEN 1 AND 64),
    manager_outcome TEXT COLLATE BINARY,
    current_evaluation_id TEXT COLLATE BINARY,
    replacement_parent_present INTEGER NOT NULL
        CHECK (replacement_parent_present IN (0, 1)),
    occurred_at TEXT NOT NULL COLLATE BINARY CHECK (occurred_at GLOB '*Z'),
    command_id TEXT NOT NULL COLLATE BINARY
        CHECK (
            length(command_id) BETWEEN 1 AND 128
            AND command_id GLOB 'SYN-EVIDENCE-M4-*'
        ),
    canonical_bytes BLOB NOT NULL CHECK (length(canonical_bytes) BETWEEN 2 AND 1048576),
    UNIQUE (order_id, sequence),
    CHECK ((sequence = 1 AND predecessor_event_id IS NULL) OR (sequence > 1 AND predecessor_event_id IS NOT NULL)),
    CHECK (event_kind != 'REPLACEMENT_PARENT_DETACHED' OR replacement_parent_present = 0)
) STRICT;

CREATE INDEX sc_case_events_order_idx ON sc_case_events(order_id, sequence);

CREATE TABLE sc_interactions (
    interaction_id TEXT PRIMARY KEY COLLATE BINARY CHECK (interaction_id GLOB 'SYN-INTERACTION-*'),
    source_ref_id TEXT NOT NULL COLLATE BINARY CHECK (source_ref_id GLOB 'SYN-EVIDENCE-*'),
    recorded_at TEXT NOT NULL COLLATE BINARY CHECK (recorded_at GLOB '*Z'),
    timestamp_precision TEXT NOT NULL COLLATE BINARY CHECK (length(timestamp_precision) BETWEEN 1 AND 64),
    workflow_state TEXT NOT NULL COLLATE BINARY CHECK (length(workflow_state) BETWEEN 1 AND 64),
    canonical_bytes BLOB NOT NULL CHECK (length(canonical_bytes) BETWEEN 2 AND 1048576)
) STRICT;

CREATE TABLE sc_search_runs (
    run_id TEXT PRIMARY KEY COLLATE BINARY CHECK (run_id GLOB 'SYN-RUN-*'),
    trigger_type TEXT NOT NULL COLLATE BINARY CHECK (length(trigger_type) BETWEEN 1 AND 64),
    started_at TEXT NOT NULL COLLATE BINARY CHECK (started_at GLOB '*Z'),
    completed_at TEXT NOT NULL COLLATE BINARY CHECK (completed_at GLOB '*Z'),
    adapter_version TEXT NOT NULL COLLATE BINARY CHECK (length(adapter_version) BETWEEN 1 AND 128),
    enumeration_complete INTEGER NOT NULL CHECK (enumeration_complete IN (0, 1)),
    terminal_outcome TEXT NOT NULL COLLATE BINARY CHECK (length(terminal_outcome) BETWEEN 1 AND 96),
    canonical_bytes BLOB NOT NULL CHECK (length(canonical_bytes) BETWEEN 2 AND 1048576)
) STRICT;

CREATE TABLE sc_search_identifiers (
    run_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_search_runs(run_id) ON DELETE CASCADE,
    interaction_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_interactions(interaction_id) ON DELETE CASCADE,
    identifier_kind TEXT NOT NULL COLLATE BINARY CHECK (identifier_kind IN ('EMAIL', 'PHONE')),
    normalized_value TEXT NOT NULL COLLATE BINARY CHECK (length(normalized_value) BETWEEN 3 AND 320),
    completeness TEXT NOT NULL COLLATE BINARY CHECK (length(completeness) BETWEEN 1 AND 32),
    PRIMARY KEY (run_id, interaction_id, identifier_kind)
) STRICT;

CREATE TABLE sc_search_result_orders (
    run_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_search_runs(run_id) ON DELETE CASCADE,
    interaction_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_interactions(interaction_id) ON DELETE CASCADE,
    identifier_kind TEXT NOT NULL COLLATE BINARY CHECK (identifier_kind IN ('EMAIL', 'PHONE')),
    order_id TEXT NOT NULL COLLATE BINARY CHECK (order_id GLOB 'SYN-ORDER-*'),
    PRIMARY KEY (run_id, interaction_id, identifier_kind, order_id),
    FOREIGN KEY (run_id, interaction_id, identifier_kind)
        REFERENCES sc_search_identifiers(run_id, interaction_id, identifier_kind)
        ON DELETE CASCADE
) STRICT;

CREATE TABLE sc_case_interactions (
    order_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_cases(order_id) ON DELETE CASCADE,
    interaction_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_interactions(interaction_id) ON DELETE RESTRICT,
    PRIMARY KEY (order_id, interaction_id)
) STRICT;

CREATE INDEX sc_case_interactions_interaction_idx ON sc_case_interactions(interaction_id);

CREATE TABLE sc_case_search_runs (
    order_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_cases(order_id) ON DELETE CASCADE,
    run_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_search_runs(run_id) ON DELETE RESTRICT,
    PRIMARY KEY (order_id, run_id)
) STRICT;

CREATE INDEX sc_case_search_runs_run_idx ON sc_case_search_runs(run_id);

CREATE TABLE sc_snapshots (
    snapshot_id TEXT PRIMARY KEY COLLATE BINARY CHECK (snapshot_id GLOB 'SYN-SNAPSHOT-*'),
    order_id TEXT NOT NULL COLLATE BINARY CHECK (order_id GLOB 'SYN-ORDER-*'),
    captured_at TEXT NOT NULL COLLATE BINARY CHECK (captured_at GLOB '*Z'),
    extraction_status TEXT NOT NULL COLLATE BINARY CHECK (length(extraction_status) BETWEEN 1 AND 32),
    lifecycle_status TEXT NOT NULL COLLATE BINARY CHECK (length(lifecycle_status) BETWEEN 1 AND 32),
    parser_version TEXT NOT NULL COLLATE BINARY CHECK (length(parser_version) BETWEEN 1 AND 128),
    canonical_bytes BLOB NOT NULL CHECK (length(canonical_bytes) BETWEEN 2 AND 1048576)
) STRICT;

CREATE INDEX sc_snapshots_order_idx ON sc_snapshots(order_id, captured_at);

CREATE TABLE sc_snapshot_lines (
    snapshot_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_snapshots(snapshot_id) ON DELETE CASCADE,
    line_id TEXT NOT NULL COLLATE BINARY CHECK (line_id GLOB 'SYN-EVIDENCE-*'),
    sku_id TEXT NOT NULL COLLATE BINARY CHECK (sku_id GLOB 'SYN-SKU-*'),
    quantity TEXT NOT NULL COLLATE BINARY
        CHECK (quantity = '0' OR (quantity NOT GLOB '*[^0-9]*' AND quantity NOT GLOB '0*' AND length(quantity) <= 9)),
    line_minor_units TEXT COLLATE BINARY,
    currency TEXT COLLATE BINARY CHECK (currency IS NULL OR length(currency) = 3),
    currency_registry_version TEXT COLLATE BINARY,
    currency_scale INTEGER CHECK (currency_scale IS NULL OR currency_scale BETWEEN 0 AND 9),
    canonical_bytes BLOB NOT NULL CHECK (length(canonical_bytes) BETWEEN 2 AND 1048576),
    PRIMARY KEY (snapshot_id, line_id),
    CHECK (
        (line_minor_units IS NULL AND currency IS NULL AND currency_registry_version IS NULL AND currency_scale IS NULL)
        OR
        (line_minor_units IS NOT NULL AND currency IS NOT NULL AND currency_registry_version IS NOT NULL AND currency_scale IS NOT NULL)
    )
) STRICT;

CREATE TABLE sc_case_snapshots (
    order_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_cases(order_id) ON DELETE CASCADE,
    snapshot_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_snapshots(snapshot_id) ON DELETE RESTRICT,
    PRIMARY KEY (order_id, snapshot_id)
) STRICT;

CREATE TABLE sc_evidence_events (
    evidence_id TEXT PRIMARY KEY COLLATE BINARY CHECK (evidence_id GLOB 'SYN-EVIDENCE-*'),
    order_id TEXT NOT NULL COLLATE BINARY CHECK (order_id GLOB 'SYN-ORDER-*'),
    interaction_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_interactions(interaction_id) ON DELETE RESTRICT,
    source_type TEXT NOT NULL COLLATE BINARY CHECK (length(source_type) BETWEEN 1 AND 64),
    classification TEXT NOT NULL COLLATE BINARY CHECK (length(classification) BETWEEN 1 AND 64),
    occurred_at TEXT NOT NULL COLLATE BINARY CHECK (occurred_at GLOB '*Z'),
    canonical_bytes BLOB NOT NULL CHECK (length(canonical_bytes) BETWEEN 2 AND 1048576)
) STRICT;

CREATE TABLE sc_case_evidence (
    order_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_cases(order_id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_evidence_events(evidence_id) ON DELETE RESTRICT,
    PRIMARY KEY (order_id, evidence_id)
) STRICT;

CREATE TABLE sc_evaluations (
    evaluation_id TEXT PRIMARY KEY COLLATE BINARY CHECK (evaluation_id GLOB 'SYN-EVALUATION-*'),
    order_id TEXT NOT NULL COLLATE BINARY CHECK (order_id GLOB 'SYN-ORDER-*'),
    snapshot_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_snapshots(snapshot_id) ON DELETE RESTRICT,
    workflow_state TEXT NOT NULL COLLATE BINARY CHECK (length(workflow_state) BETWEEN 1 AND 64),
    attribution TEXT NOT NULL COLLATE BINARY CHECK (length(attribution) BETWEEN 1 AND 64),
    order_value_status TEXT NOT NULL COLLATE BINARY CHECK (length(order_value_status) BETWEEN 1 AND 64),
    human_review_required INTEGER NOT NULL CHECK (human_review_required IN (0, 1)),
    rule_pack_version TEXT NOT NULL COLLATE BINARY CHECK (length(rule_pack_version) BETWEEN 1 AND 128),
    material_sha256 TEXT NOT NULL COLLATE BINARY
        CHECK (length(material_sha256) = 64 AND material_sha256 NOT GLOB '*[^0-9a-f]*'),
    canonical_bytes BLOB NOT NULL CHECK (length(canonical_bytes) BETWEEN 2 AND 1048576)
) STRICT;

CREATE INDEX sc_evaluations_order_idx ON sc_evaluations(order_id, evaluation_id);

CREATE TABLE sc_evaluation_reasons (
    evaluation_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_evaluations(evaluation_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 1),
    reason_code TEXT NOT NULL COLLATE BINARY CHECK (length(reason_code) BETWEEN 1 AND 96),
    PRIMARY KEY (evaluation_id, ordinal),
    UNIQUE (evaluation_id, reason_code)
) STRICT;

CREATE TABLE sc_case_evaluations (
    order_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_cases(order_id) ON DELETE CASCADE,
    evaluation_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_evaluations(evaluation_id) ON DELETE RESTRICT,
    PRIMARY KEY (order_id, evaluation_id)
) STRICT;

CREATE TABLE sc_replacement_candidates (
    parent_order_id TEXT NOT NULL COLLATE BINARY
        REFERENCES sc_cases(order_id) ON DELETE CASCADE,
    evaluation_id TEXT NOT NULL COLLATE BINARY
        REFERENCES sc_evaluations(evaluation_id) ON DELETE CASCADE,
    replacement_run_id TEXT NOT NULL COLLATE BINARY
        REFERENCES sc_search_runs(run_id) ON DELETE RESTRICT,
    candidate_order_id TEXT NOT NULL COLLATE BINARY
        CHECK (candidate_order_id GLOB 'SYN-ORDER-*'),
    snapshot_id TEXT NOT NULL COLLATE BINARY
        REFERENCES sc_snapshots(snapshot_id) ON DELETE RESTRICT,
    candidate_status TEXT NOT NULL COLLATE BINARY
        CHECK (candidate_status IN ('EXACT_RELEVANT', 'POSSIBLE_REVIEW', 'NOT_CONTINUATION', 'BLOCKED')),
    customer_continuity TEXT NOT NULL COLLATE BINARY
        CHECK (length(customer_continuity) BETWEEN 1 AND 32),
    product_continuity TEXT NOT NULL COLLATE BINARY
        CHECK (length(product_continuity) BETWEEN 1 AND 32),
    line_universe_complete INTEGER NOT NULL CHECK (line_universe_complete IN (0, 1)),
    possible_nonexact_continuity INTEGER NOT NULL
        CHECK (possible_nonexact_continuity IN (0, 1)),
    canonical_bytes BLOB NOT NULL CHECK (length(canonical_bytes) BETWEEN 2 AND 1048576),
    PRIMARY KEY (evaluation_id, candidate_order_id),
    UNIQUE (evaluation_id, snapshot_id),
    CHECK (parent_order_id != candidate_order_id)
) STRICT;

CREATE INDEX sc_replacement_candidates_parent_idx
    ON sc_replacement_candidates(parent_order_id, candidate_order_id);

CREATE TABLE sc_active_replacement_links (
    candidate_order_id TEXT PRIMARY KEY COLLATE BINARY
        REFERENCES sc_cases(order_id) ON DELETE RESTRICT,
    parent_order_id TEXT NOT NULL COLLATE BINARY
        REFERENCES sc_cases(order_id) ON DELETE RESTRICT,
    replacement_run_id TEXT NOT NULL COLLATE BINARY
        REFERENCES sc_search_runs(run_id) ON DELETE RESTRICT,
    linked_at TEXT NOT NULL COLLATE BINARY CHECK (linked_at GLOB '*Z'),
    CHECK (parent_order_id != candidate_order_id)
) STRICT;

CREATE INDEX sc_active_replacement_links_parent_idx
    ON sc_active_replacement_links(parent_order_id, candidate_order_id);

CREATE TABLE sc_manager_outcomes (
    occurrence_id TEXT PRIMARY KEY COLLATE BINARY CHECK (occurrence_id GLOB 'SYN-EVIDENCE-*'),
    order_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_cases(order_id) ON DELETE CASCADE,
    outcome TEXT NOT NULL COLLATE BINARY CHECK (outcome IN ('APPROVED', 'DENIED', 'PARTIAL', 'OTHER_REP', 'NOT_PURSUED')),
    decided_at TEXT NOT NULL COLLATE BINARY CHECK (decided_at GLOB '*Z'),
    recorded_at TEXT NOT NULL COLLATE BINARY CHECK (recorded_at GLOB '*Z'),
    actor_id TEXT NOT NULL COLLATE BINARY CHECK (actor_id GLOB 'SYN-REP-*'),
    approved_minor_units TEXT COLLATE BINARY,
    approved_currency TEXT COLLATE BINARY CHECK (approved_currency IS NULL OR length(approved_currency) = 3),
    approved_registry_version TEXT COLLATE BINARY,
    approved_scale INTEGER CHECK (approved_scale IS NULL OR approved_scale BETWEEN 0 AND 9),
    material_sha256 TEXT NOT NULL COLLATE BINARY
        CHECK (length(material_sha256) = 64 AND material_sha256 NOT GLOB '*[^0-9a-f]*'),
    canonical_bytes BLOB NOT NULL CHECK (length(canonical_bytes) BETWEEN 2 AND 1048576),
    CHECK (
        (approved_minor_units IS NULL AND approved_currency IS NULL AND approved_registry_version IS NULL AND approved_scale IS NULL)
        OR
        (approved_minor_units IS NOT NULL AND approved_currency IS NOT NULL AND approved_registry_version IS NOT NULL AND approved_scale IS NOT NULL)
    )
) STRICT;

CREATE TABLE sc_closed_audits (
    audit_id TEXT PRIMARY KEY COLLATE BINARY CHECK (audit_id GLOB 'SYN-EVIDENCE-*'),
    order_id TEXT NOT NULL UNIQUE COLLATE BINARY REFERENCES sc_cases(order_id) ON DELETE CASCADE,
    closed_at TEXT NOT NULL COLLATE BINARY CHECK (closed_at GLOB '*Z'),
    purge_eligible_at TEXT NOT NULL COLLATE BINARY CHECK (purge_eligible_at GLOB '*Z'),
    workflow_before_close TEXT NOT NULL COLLATE BINARY CHECK (length(workflow_before_close) BETWEEN 1 AND 64),
    human_outcome TEXT COLLATE BINARY,
    material_sha256 TEXT NOT NULL COLLATE BINARY
        CHECK (length(material_sha256) = 64 AND material_sha256 NOT GLOB '*[^0-9a-f]*'),
    canonical_bytes BLOB NOT NULL CHECK (length(canonical_bytes) BETWEEN 2 AND 1048576)
) STRICT;

CREATE INDEX sc_closed_audits_purge_idx ON sc_closed_audits(purge_eligible_at);

CREATE TABLE sc_no_order_closed_audits (
    audit_id TEXT PRIMARY KEY COLLATE BINARY CHECK (audit_id GLOB 'SYN-EVIDENCE-*'),
    command_id TEXT NOT NULL UNIQUE COLLATE BINARY
        REFERENCES durable_commands(command_id) ON DELETE CASCADE,
    closed_at TEXT NOT NULL COLLATE BINARY CHECK (closed_at GLOB '*Z'),
    purge_eligible_at TEXT NOT NULL COLLATE BINARY CHECK (purge_eligible_at GLOB '*Z'),
    material_sha256 TEXT NOT NULL COLLATE BINARY
        CHECK (length(material_sha256) = 64 AND material_sha256 NOT GLOB '*[^0-9a-f]*'),
    canonical_bytes BLOB NOT NULL CHECK (length(canonical_bytes) BETWEEN 2 AND 1048576)
) STRICT;

CREATE INDEX sc_no_order_audits_purge_idx ON sc_no_order_closed_audits(purge_eligible_at);

CREATE TABLE sc_daily_aggregates (
    business_date TEXT NOT NULL COLLATE BINARY CHECK (business_date GLOB '????-??-??'),
    result_class TEXT NOT NULL COLLATE BINARY CHECK (length(result_class) BETWEEN 1 AND 96),
    occurrence_count INTEGER NOT NULL CHECK (occurrence_count >= 0),
    PRIMARY KEY (business_date, result_class)
) STRICT;

CREATE TRIGGER sc_cases_version_guard
BEFORE UPDATE ON sc_cases
WHEN NOT (
    NEW.projection_version = OLD.projection_version + 1
    AND NEW.last_event_id != OLD.last_event_id
    AND (
        NEW.last_event_sequence = OLD.last_event_sequence + 1
        OR (
            NEW.workflow_state = 'CLOSED'
            AND NEW.last_event_sequence = 1
        )
    )
    AND EXISTS (
        SELECT 1 FROM sc_case_events AS event
        WHERE event.event_id = NEW.last_event_id
          AND event.order_id = NEW.order_id
          AND event.sequence = NEW.last_event_sequence
          AND event.predecessor_event_id IS
              CASE
                  WHEN NEW.last_event_sequence = 1 THEN NULL
                  ELSE OLD.last_event_id
              END
          AND event.workflow_state = NEW.workflow_state
          AND event.attribution = NEW.attribution
          AND event.order_value_status = NEW.order_value_status
          AND event.current_evaluation_id IS NEW.current_evaluation_id
          AND event.replacement_parent_present =
              CASE WHEN NEW.replacement_parent_order_id IS NULL THEN 0 ELSE 1 END
          AND (
              OLD.replacement_parent_order_id IS NULL
              OR NEW.replacement_parent_order_id IS NOT NULL
              OR event.event_kind = 'REPLACEMENT_PARENT_DETACHED'
          )
    )
)
BEGIN
    SELECT RAISE(ABORT, 'SALES_CREDIT_PROJECTION_CONFLICT');
END;

CREATE TRIGGER sc_case_events_immutable_update BEFORE UPDATE ON sc_case_events BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_CASE_EVENT'); END;
CREATE TRIGGER sc_interactions_immutable_update BEFORE UPDATE ON sc_interactions BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_INTERACTION'); END;
CREATE TRIGGER sc_search_runs_immutable_update BEFORE UPDATE ON sc_search_runs BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_SEARCH_RUN'); END;
CREATE TRIGGER sc_search_identifiers_immutable_update BEFORE UPDATE ON sc_search_identifiers BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_SEARCH_IDENTIFIER'); END;
CREATE TRIGGER sc_search_result_orders_immutable_update BEFORE UPDATE ON sc_search_result_orders BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_SEARCH_RESULT'); END;
CREATE TRIGGER sc_snapshots_immutable_update BEFORE UPDATE ON sc_snapshots BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_SNAPSHOT'); END;
CREATE TRIGGER sc_snapshot_lines_immutable_update BEFORE UPDATE ON sc_snapshot_lines BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_LINE'); END;
CREATE TRIGGER sc_evidence_events_immutable_update BEFORE UPDATE ON sc_evidence_events BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_EVIDENCE'); END;
CREATE TRIGGER sc_evaluations_immutable_update BEFORE UPDATE ON sc_evaluations BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_EVALUATION'); END;
CREATE TRIGGER sc_evaluation_reasons_immutable_update BEFORE UPDATE ON sc_evaluation_reasons BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_EVALUATION_REASON'); END;
CREATE TRIGGER sc_replacement_candidates_immutable_update BEFORE UPDATE ON sc_replacement_candidates BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_REPLACEMENT_CANDIDATE'); END;
CREATE TRIGGER sc_manager_outcomes_immutable_update BEFORE UPDATE ON sc_manager_outcomes BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_MANAGER_OUTCOME'); END;
CREATE TRIGGER sc_closed_audits_immutable_update BEFORE UPDATE ON sc_closed_audits BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_CLOSED_AUDIT'); END;
CREATE TRIGGER sc_no_order_closed_audits_immutable_update BEFORE UPDATE ON sc_no_order_closed_audits BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_NO_ORDER_AUDIT'); END;

UPDATE application_metadata SET latest_schema_version = 3 WHERE singleton = 1;
