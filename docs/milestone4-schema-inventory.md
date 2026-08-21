# Milestone 4 SQLite schema inventory

Generated from a fresh database upgraded through every checked-in migration.
The exact `sqlite_schema` SQL below documents every table, index, trigger, view,
column constraint, and foreign-key declaration.

- Tables: 79
- Indexes: 20
- Triggers: 61
- Views: 0

## Tables

### `_schema_migrations`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `version` | `INTEGER` | 0 | - | 1 | 0 |
| `name` | `TEXT` | 1 | - | 0 | 0 |
| `sha256` | `TEXT` | 1 | - | 0 | 0 |
| `applied_at_utc` | `TEXT` | 1 | - | 0 | 0 |

```sql
CREATE TABLE _schema_migrations (
                version INTEGER PRIMARY KEY CHECK (version > 0),
                name TEXT NOT NULL UNIQUE,
                sha256 TEXT NOT NULL
                    CHECK (
                        length(sha256) = 64
                        AND sha256 NOT GLOB '*[^0-9a-f]*'
                    ),
                applied_at_utc TEXT NOT NULL
            )
```

### `application_metadata`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `singleton` | `INTEGER` | 0 | - | 1 | 0 |
| `application_id` | `TEXT` | 1 | - | 0 | 0 |
| `application_version` | `TEXT` | 1 | - | 0 | 0 |
| `database_format` | `TEXT` | 1 | - | 0 | 0 |
| `latest_schema_version` | `INTEGER` | 1 | - | 0 | 0 |

```sql
CREATE TABLE application_metadata (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    application_id TEXT NOT NULL COLLATE BINARY
        CHECK (application_id = 'synthetic-sales-assist'),
    application_version TEXT NOT NULL COLLATE BINARY,
    database_format TEXT NOT NULL COLLATE BINARY
        CHECK (database_format = 'synthetic-sales-assist-sqlite/v1'),
    latest_schema_version INTEGER NOT NULL CHECK (latest_schema_version >= 2)
) STRICT
```

### `backup_receipts`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `backup_id` | `TEXT` | 1 | - | 1 | 0 |
| `created_at` | `TEXT` | 1 | - | 0 | 0 |
| `completed_at` | `TEXT` | 0 | - | 0 | 0 |
| `schema_version` | `INTEGER` | 1 | - | 0 | 0 |
| `application_version` | `TEXT` | 1 | - | 0 | 0 |
| `source_sha256` | `TEXT` | 0 | - | 0 | 0 |
| `backup_sha256` | `TEXT` | 0 | - | 0 | 0 |
| `table_count` | `INTEGER` | 1 | - | 0 | 0 |
| `row_count` | `INTEGER` | 1 | - | 0 | 0 |
| `quick_check` | `TEXT` | 1 | - | 0 | 0 |
| `foreign_key_check` | `TEXT` | 1 | - | 0 | 0 |
| `status` | `TEXT` | 1 | - | 0 | 0 |
| `error_code` | `TEXT` | 0 | - | 0 | 0 |

```sql
CREATE TABLE backup_receipts (
    backup_id TEXT PRIMARY KEY COLLATE BINARY CHECK (length(backup_id) BETWEEN 1 AND 128),
    created_at TEXT NOT NULL COLLATE BINARY CHECK (created_at GLOB '*Z'),
    completed_at TEXT COLLATE BINARY CHECK (completed_at IS NULL OR completed_at GLOB '*Z'),
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    application_version TEXT NOT NULL COLLATE BINARY CHECK (length(application_version) BETWEEN 1 AND 64),
    source_sha256 TEXT COLLATE BINARY
        CHECK (source_sha256 IS NULL OR (length(source_sha256) = 64 AND source_sha256 NOT GLOB '*[^0-9a-f]*')),
    backup_sha256 TEXT COLLATE BINARY
        CHECK (backup_sha256 IS NULL OR (length(backup_sha256) = 64 AND backup_sha256 NOT GLOB '*[^0-9a-f]*')),
    table_count INTEGER NOT NULL CHECK (table_count >= 0),
    row_count INTEGER NOT NULL CHECK (row_count >= 0),
    quick_check TEXT NOT NULL COLLATE BINARY CHECK (quick_check IN ('ok', 'not_run', 'failed')),
    foreign_key_check TEXT NOT NULL COLLATE BINARY CHECK (foreign_key_check IN ('ok', 'not_run', 'failed')),
    status TEXT NOT NULL COLLATE BINARY CHECK (status IN ('STARTED', 'COMPLETED', 'FAILED')),
    error_code TEXT COLLATE BINARY
        CHECK (error_code IS NULL OR (length(error_code) BETWEEN 1 AND 96 AND error_code NOT GLOB '*[^A-Z0-9_-]*'))
) STRICT
```

### `doi_action_verification_events`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `event_id` | `TEXT` | 0 | - | 1 | 0 |
| `intervention_id` | `TEXT` | 1 | - | 0 | 0 |
| `occurrence_id` | `TEXT` | 1 | - | 0 | 0 |
| `record_domain` | `TEXT` | 1 | - | 0 | 0 |
| `record_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `record_payload` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `intervention_id` | `doi_interventions` | `intervention_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE doi_action_verification_events (
    event_id TEXT PRIMARY KEY,
    intervention_id TEXT NOT NULL REFERENCES doi_interventions(intervention_id) ON DELETE CASCADE,
    occurrence_id TEXT NOT NULL,
    record_domain TEXT NOT NULL,
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
    record_canonical_bytes BLOB NOT NULL CHECK (typeof(record_canonical_bytes) = 'blob'),
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob'),
    UNIQUE (intervention_id, occurrence_id)
)
```

### `doi_attempt_batch_references`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `attempt_id` | `TEXT` | 0 | - | 1 | 0 |
| `batch_id` | `TEXT` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `batch_id` | `doi_source_batches` | `batch_id` | `NO ACTION` | `NO ACTION` |
| `attempt_id` | `doi_source_import_attempts` | `attempt_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE doi_attempt_batch_references (
    attempt_id TEXT PRIMARY KEY REFERENCES doi_source_import_attempts(attempt_id) ON DELETE CASCADE,
    batch_id TEXT NOT NULL REFERENCES doi_source_batches(batch_id)
)
```

### `doi_case_artifacts`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `artifact_pk` | `INTEGER` | 0 | - | 1 | 0 |
| `case_id` | `TEXT` | 1 | - | 0 | 0 |
| `artifact_kind` | `TEXT` | 1 | - | 0 | 0 |
| `artifact_id` | `TEXT` | 1 | - | 0 | 0 |
| `record_domain` | `TEXT` | 1 | - | 0 | 0 |
| `record_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `record_payload` | `BLOB` | 1 | - | 0 | 0 |
| `created_at` | `TEXT` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `case_id` | `doi_cases` | `case_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_case_projections`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `case_id` | `TEXT` | 0 | - | 1 | 0 |
| `lifecycle_state` | `TEXT` | 1 | - | 0 | 0 |
| `current_snapshot_id` | `TEXT` | 0 | - | 0 | 0 |
| `current_evaluation_id` | `TEXT` | 0 | - | 0 | 0 |
| `terminal_closure_reason` | `TEXT` | 0 | - | 0 | 0 |
| `projection_version` | `INTEGER` | 1 | - | 0 | 0 |
| `head_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_payload` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `case_id` | `doi_cases` | `case_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_case_source_batch_references`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `case_id` | `TEXT` | 1 | - | 1 | 0 |
| `batch_id` | `TEXT` | 1 | - | 2 | 0 |
| `binding_artifact_pk` | `INTEGER` | 1 | - | 0 | 0 |
| `admission_artifact_pk` | `INTEGER` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `admission_artifact_pk` | `doi_case_artifacts` | `artifact_pk` | `NO ACTION` | `CASCADE` |
| `binding_artifact_pk` | `doi_case_artifacts` | `artifact_pk` | `NO ACTION` | `CASCADE` |
| `batch_id` | `doi_source_batches` | `batch_id` | `NO ACTION` | `NO ACTION` |
| `case_id` | `doi_cases` | `case_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE doi_case_source_batch_references (
    case_id TEXT NOT NULL REFERENCES doi_cases(case_id) ON DELETE CASCADE,
    batch_id TEXT NOT NULL REFERENCES doi_source_batches(batch_id),
    binding_artifact_pk INTEGER NOT NULL REFERENCES doi_case_artifacts(artifact_pk) ON DELETE CASCADE,
    admission_artifact_pk INTEGER NOT NULL REFERENCES doi_case_artifacts(artifact_pk) ON DELETE CASCADE,
    PRIMARY KEY (case_id, batch_id)
)
```

### `doi_cases`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `case_id` | `TEXT` | 0 | - | 1 | 0 |
| `order_id` | `TEXT` | 1 | - | 0 | 0 |
| `created_at` | `TEXT` | 1 | - | 0 | 0 |

```sql
CREATE TABLE doi_cases (
    case_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
)
```

### `doi_evaluation_reasons`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `evaluation_id` | `TEXT` | 1 | - | 1 | 0 |
| `reason_code` | `TEXT` | 1 | - | 2 | 0 |
| `owning_transition_id` | `TEXT` | 0 | - | 0 | 0 |
| `effective_overlay` | `INTEGER` | 1 | - | 0 | 0 |
| `ordinal` | `INTEGER` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `evaluation_id` | `doi_evaluations` | `evaluation_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE doi_evaluation_reasons (
    evaluation_id TEXT NOT NULL REFERENCES doi_evaluations(evaluation_id) ON DELETE CASCADE,
    reason_code TEXT NOT NULL,
    owning_transition_id TEXT,
    effective_overlay INTEGER NOT NULL CHECK (effective_overlay IN (0, 1)),
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    PRIMARY KEY (evaluation_id, reason_code),
    UNIQUE (evaluation_id, ordinal)
)
```

### `doi_evaluations`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `evaluation_id` | `TEXT` | 0 | - | 1 | 0 |
| `case_id` | `TEXT` | 1 | - | 0 | 0 |
| `snapshot_id` | `TEXT` | 1 | - | 0 | 0 |
| `run_id` | `TEXT` | 1 | - | 0 | 0 |
| `order_id` | `TEXT` | 1 | - | 0 | 0 |
| `top_level_state` | `TEXT` | 1 | - | 0 | 0 |
| `transition_id` | `TEXT` | 1 | - | 0 | 0 |
| `input_domain` | `TEXT` | 1 | - | 0 | 0 |
| `input_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `input_canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `output_domain` | `TEXT` | 1 | - | 0 | 0 |
| `output_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `output_canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `record_artifact_pk` | `INTEGER` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `record_artifact_pk` | `doi_case_artifacts` | `artifact_pk` | `NO ACTION` | `CASCADE` |
| `run_id` | `doi_runs` | `run_id` | `NO ACTION` | `CASCADE` |
| `snapshot_id` | `doi_order_snapshots` | `snapshot_id` | `NO ACTION` | `CASCADE` |
| `case_id` | `doi_cases` | `case_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_extraction_attempts`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `attempt_id` | `TEXT` | 0 | - | 1 | 0 |
| `case_id` | `TEXT` | 1 | - | 0 | 0 |
| `run_id` | `TEXT` | 1 | - | 0 | 0 |
| `order_id` | `TEXT` | 1 | - | 0 | 0 |
| `status` | `TEXT` | 1 | - | 0 | 0 |
| `snapshot_id` | `TEXT` | 0 | - | 0 | 0 |
| `started_at` | `TEXT` | 1 | - | 0 | 0 |
| `completed_at` | `TEXT` | 1 | - | 0 | 0 |
| `record_artifact_pk` | `INTEGER` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `record_artifact_pk` | `doi_case_artifacts` | `artifact_pk` | `NO ACTION` | `CASCADE` |
| `run_id` | `doi_runs` | `run_id` | `NO ACTION` | `CASCADE` |
| `case_id` | `doi_cases` | `case_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_interventions`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `intervention_id` | `TEXT` | 0 | - | 1 | 0 |
| `case_id` | `TEXT` | 1 | - | 0 | 0 |
| `opportunity_id` | `TEXT` | 1 | - | 0 | 0 |
| `intervention_type` | `TEXT` | 1 | - | 0 | 0 |
| `status` | `TEXT` | 1 | - | 0 | 0 |
| `action_occurred_at` | `TEXT` | 0 | - | 0 | 0 |
| `projection_version` | `INTEGER` | 1 | - | 0 | 0 |
| `head_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_artifact_pk` | `INTEGER` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `record_artifact_pk` | `doi_case_artifacts` | `artifact_pk` | `NO ACTION` | `CASCADE` |
| `opportunity_id` | `doi_opportunities` | `opportunity_id` | `NO ACTION` | `CASCADE` |
| `case_id` | `doi_cases` | `case_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_kpi_contribution_events`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `intervention_id` | `TEXT` | 1 | - | 1 | 0 |
| `sequence_no` | `INTEGER` | 1 | - | 2 | 0 |
| `event_id` | `TEXT` | 1 | - | 0 | 0 |
| `predecessor_sha256` | `TEXT` | 0 | - | 0 | 0 |
| `record_domain` | `TEXT` | 1 | - | 0 | 0 |
| `record_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `record_payload` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `intervention_id` | `doi_interventions` | `intervention_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_kpi_daily_buckets`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `action_date` | `TEXT` | 1 | - | 1 | 0 |
| `intervention_type` | `TEXT` | 1 | - | 2 | 0 |
| `currency_code` | `TEXT` | 1 | - | 3 | 0 |
| `currency_registry_version` | `TEXT` | 1 | - | 4 | 0 |
| `currency_scale` | `INTEGER` | 1 | - | 5 | 0 |
| `amount_minor_units` | `INTEGER` | 1 | - | 0 | 0 |
| `intervention_count` | `INTEGER` | 1 | - | 0 | 0 |

```sql
CREATE TABLE doi_kpi_daily_buckets (
    action_date TEXT NOT NULL,
    intervention_type TEXT NOT NULL,
    currency_code TEXT NOT NULL,
    currency_registry_version TEXT NOT NULL,
    currency_scale INTEGER NOT NULL,
    amount_minor_units INTEGER NOT NULL,
    intervention_count INTEGER NOT NULL CHECK (intervention_count >= 0),
    PRIMARY KEY (action_date, intervention_type, currency_code, currency_registry_version, currency_scale)
)
```

### `doi_line_continuity_proof_references`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `line_snapshot_id` | `TEXT` | 0 | - | 1 | 0 |
| `proof_artifact_pk` | `INTEGER` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `proof_artifact_pk` | `doi_case_artifacts` | `artifact_pk` | `NO ACTION` | `CASCADE` |
| `line_snapshot_id` | `doi_line_snapshots` | `line_snapshot_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE doi_line_continuity_proof_references (
    line_snapshot_id TEXT PRIMARY KEY REFERENCES doi_line_snapshots(line_snapshot_id) ON DELETE CASCADE,
    proof_artifact_pk INTEGER NOT NULL REFERENCES doi_case_artifacts(artifact_pk) ON DELETE CASCADE
)
```

### `doi_line_snapshots`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `line_snapshot_id` | `TEXT` | 0 | - | 1 | 0 |
| `case_id` | `TEXT` | 1 | - | 0 | 0 |
| `snapshot_id` | `TEXT` | 1 | - | 0 | 0 |
| `line_ordinal` | `INTEGER` | 1 | - | 0 | 0 |
| `relevant_merchandise` | `INTEGER` | 1 | - | 0 | 0 |
| `continuity_state` | `TEXT` | 1 | - | 0 | 0 |
| `record_artifact_pk` | `INTEGER` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `record_artifact_pk` | `doi_case_artifacts` | `artifact_pk` | `NO ACTION` | `CASCADE` |
| `snapshot_id` | `doi_order_snapshots` | `snapshot_id` | `NO ACTION` | `CASCADE` |
| `case_id` | `doi_cases` | `case_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE doi_line_snapshots (
    line_snapshot_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES doi_cases(case_id) ON DELETE CASCADE,
    snapshot_id TEXT NOT NULL REFERENCES doi_order_snapshots(snapshot_id) ON DELETE CASCADE,
    line_ordinal INTEGER NOT NULL CHECK (line_ordinal > 0),
    relevant_merchandise INTEGER NOT NULL CHECK (relevant_merchandise IN (0, 1)),
    continuity_state TEXT NOT NULL,
    record_artifact_pk INTEGER NOT NULL UNIQUE REFERENCES doi_case_artifacts(artifact_pk) ON DELETE CASCADE,
    UNIQUE (snapshot_id, line_ordinal)
)
```

### `doi_opportunities`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `opportunity_id` | `TEXT` | 0 | - | 1 | 0 |
| `evaluation_id` | `TEXT` | 1 | - | 0 | 0 |
| `case_id` | `TEXT` | 1 | - | 0 | 0 |
| `opportunity_type` | `TEXT` | 1 | - | 0 | 0 |
| `potential_state` | `TEXT` | 1 | - | 0 | 0 |
| `amount_minor_units` | `INTEGER` | 0 | - | 0 | 0 |
| `currency_code` | `TEXT` | 0 | - | 0 | 0 |
| `currency_registry_version` | `TEXT` | 0 | - | 0 | 0 |
| `currency_scale` | `INTEGER` | 0 | - | 0 | 0 |
| `mutual_exclusion_group_id` | `TEXT` | 0 | - | 0 | 0 |
| `record_artifact_pk` | `INTEGER` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `record_artifact_pk` | `doi_case_artifacts` | `artifact_pk` | `NO ACTION` | `CASCADE` |
| `case_id` | `doi_cases` | `case_id` | `NO ACTION` | `CASCADE` |
| `evaluation_id` | `doi_evaluations` | `evaluation_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_opportunity_scope_components`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `opportunity_id` | `TEXT` | 1 | - | 1 | 0 |
| `line_snapshot_id` | `TEXT` | 1 | - | 2 | 0 |
| `role` | `TEXT` | 1 | - | 3 | 0 |
| `quantity_text` | `TEXT` | 1 | - | 0 | 0 |
| `ordinal` | `INTEGER` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `line_snapshot_id` | `doi_line_snapshots` | `line_snapshot_id` | `NO ACTION` | `RESTRICT` |
| `opportunity_id` | `doi_opportunities` | `opportunity_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE doi_opportunity_scope_components (
    opportunity_id TEXT NOT NULL REFERENCES doi_opportunities(opportunity_id) ON DELETE CASCADE,
    line_snapshot_id TEXT NOT NULL REFERENCES doi_line_snapshots(line_snapshot_id) ON DELETE RESTRICT,
    role TEXT NOT NULL,
    quantity_text TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    PRIMARY KEY (opportunity_id, line_snapshot_id, role),
    UNIQUE (opportunity_id, ordinal)
)
```

### `doi_order_snapshots`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `snapshot_id` | `TEXT` | 0 | - | 1 | 0 |
| `case_id` | `TEXT` | 1 | - | 0 | 0 |
| `run_id` | `TEXT` | 1 | - | 0 | 0 |
| `order_id` | `TEXT` | 1 | - | 0 | 0 |
| `source_observed_at` | `TEXT` | 1 | - | 0 | 0 |
| `completeness_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_artifact_pk` | `INTEGER` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `record_artifact_pk` | `doi_case_artifacts` | `artifact_pk` | `NO ACTION` | `CASCADE` |
| `run_id` | `doi_runs` | `run_id` | `NO ACTION` | `CASCADE` |
| `case_id` | `doi_cases` | `case_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE doi_order_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES doi_cases(case_id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES doi_runs(run_id) ON DELETE CASCADE,
    order_id TEXT NOT NULL,
    source_observed_at TEXT NOT NULL,
    completeness_sha256 TEXT NOT NULL CHECK (length(completeness_sha256) = 64),
    record_artifact_pk INTEGER NOT NULL UNIQUE REFERENCES doi_case_artifacts(artifact_pk) ON DELETE CASCADE
)
```

### `doi_owner_events`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `stream_family` | `TEXT` | 1 | - | 1 | 0 |
| `stream_id` | `TEXT` | 1 | - | 2 | 0 |
| `event_id` | `TEXT` | 1 | - | 0 | 0 |
| `sequence_no` | `INTEGER` | 1 | - | 3 | 0 |
| `transition_id` | `TEXT` | 0 | - | 0 | 0 |
| `projection_state` | `TEXT` | 1 | - | 0 | 0 |
| `predecessor_sha256` | `TEXT` | 0 | - | 0 | 0 |
| `occurred_at` | `TEXT` | 1 | - | 0 | 0 |
| `record_domain` | `TEXT` | 1 | - | 0 | 0 |
| `record_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `record_payload` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `stream_family` | `doi_owner_streams` | `stream_family` | `NO ACTION` | `CASCADE` |
| `stream_id` | `doi_owner_streams` | `stream_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_owner_stream_anchors`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `stream_family` | `TEXT` | 1 | - | 1 | 0 |
| `stream_id` | `TEXT` | 1 | - | 2 | 0 |
| `case_id` | `TEXT` | 0 | - | 0 | 0 |
| `run_id` | `TEXT` | 0 | - | 0 | 0 |
| `created_at` | `TEXT` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `run_id` | `doi_runs` | `run_id` | `NO ACTION` | `CASCADE` |
| `case_id` | `doi_cases` | `case_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE doi_owner_stream_anchors (
    stream_family TEXT NOT NULL,
    stream_id TEXT NOT NULL,
    case_id TEXT REFERENCES doi_cases(case_id) ON DELETE CASCADE,
    run_id TEXT REFERENCES doi_runs(run_id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (stream_family, stream_id)
)
```

### `doi_owner_streams`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `stream_id` | `TEXT` | 1 | - | 2 | 0 |
| `stream_family` | `TEXT` | 1 | - | 1 | 0 |
| `case_id` | `TEXT` | 0 | - | 0 | 0 |
| `run_id` | `TEXT` | 0 | - | 0 | 0 |
| `current_state` | `TEXT` | 1 | - | 0 | 0 |
| `sequence_no` | `INTEGER` | 1 | - | 0 | 0 |
| `head_sha256` | `TEXT` | 0 | - | 0 | 0 |
| `projection_payload` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `run_id` | `doi_runs` | `run_id` | `NO ACTION` | `CASCADE` |
| `case_id` | `doi_cases` | `case_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_product_observations`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `observation_id` | `TEXT` | 0 | - | 1 | 0 |
| `relationship_id` | `TEXT` | 0 | - | 0 | 0 |
| `case_id` | `TEXT` | 0 | - | 0 | 0 |
| `action_context_id` | `TEXT` | 1 | - | 0 | 0 |
| `observed_at` | `TEXT` | 1 | - | 0 | 0 |
| `record_domain` | `TEXT` | 1 | - | 0 | 0 |
| `record_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `record_payload` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `case_id` | `doi_cases` | `case_id` | `NO ACTION` | `CASCADE` |
| `relationship_id` | `doi_product_relationships` | `relationship_id` | `NO ACTION` | `NO ACTION` |

```sql
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
)
```

### `doi_product_relationship_revisions`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `relationship_id` | `TEXT` | 1 | - | 1 | 0 |
| `revision_no` | `INTEGER` | 1 | - | 2 | 0 |
| `revision_id` | `TEXT` | 1 | - | 0 | 0 |
| `predecessor_sha256` | `TEXT` | 0 | - | 0 | 0 |
| `record_domain` | `TEXT` | 1 | - | 0 | 0 |
| `record_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `record_payload` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `relationship_id` | `doi_product_relationships` | `relationship_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_product_relationships`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `relationship_id` | `TEXT` | 0 | - | 1 | 0 |
| `relationship_type` | `TEXT` | 1 | - | 0 | 0 |
| `ordered_sku` | `TEXT` | 1 | - | 0 | 0 |
| `candidate_sku` | `TEXT` | 1 | - | 0 | 0 |
| `current_revision` | `INTEGER` | 1 | - | 0 | 0 |
| `current_state` | `TEXT` | 1 | - | 0 | 0 |
| `head_sha256` | `TEXT` | 1 | - | 0 | 0 |

```sql
CREATE TABLE doi_product_relationships (
    relationship_id TEXT PRIMARY KEY,
    relationship_type TEXT NOT NULL,
    ordered_sku TEXT NOT NULL,
    candidate_sku TEXT NOT NULL,
    current_revision INTEGER NOT NULL CHECK (current_revision > 0),
    current_state TEXT NOT NULL,
    head_sha256 TEXT NOT NULL CHECK (length(head_sha256) = 64),
    UNIQUE (relationship_type, ordered_sku, candidate_sku)
)
```

### `doi_rejected_source_records`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `rejection_id` | `TEXT` | 0 | - | 1 | 0 |
| `attempt_id` | `TEXT` | 1 | - | 0 | 0 |
| `run_id` | `TEXT` | 1 | - | 0 | 0 |
| `batch_id` | `TEXT` | 0 | - | 0 | 0 |
| `order_id` | `TEXT` | 1 | - | 0 | 0 |
| `retention_state` | `TEXT` | 1 | - | 0 | 0 |
| `purge_eligible_at` | `TEXT` | 0 | - | 0 | 0 |
| `record_domain` | `TEXT` | 1 | - | 0 | 0 |
| `record_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `record_payload` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `batch_id` | `doi_source_batches` | `batch_id` | `NO ACTION` | `NO ACTION` |
| `run_id` | `doi_runs` | `run_id` | `NO ACTION` | `CASCADE` |
| `attempt_id` | `doi_source_import_attempts` | `attempt_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_resulting_order_link_revisions`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `link_id` | `TEXT` | 1 | - | 1 | 0 |
| `revision_no` | `INTEGER` | 1 | - | 2 | 0 |
| `revision_id` | `TEXT` | 1 | - | 0 | 0 |
| `predecessor_sha256` | `TEXT` | 0 | - | 0 | 0 |
| `record_domain` | `TEXT` | 1 | - | 0 | 0 |
| `record_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `record_payload` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `link_id` | `doi_resulting_order_links` | `link_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_resulting_order_links`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `link_id` | `TEXT` | 0 | - | 1 | 0 |
| `case_id` | `TEXT` | 1 | - | 0 | 0 |
| `intervention_id` | `TEXT` | 1 | - | 0 | 0 |
| `parent_order_id` | `TEXT` | 1 | - | 0 | 0 |
| `child_order_id` | `TEXT` | 1 | - | 0 | 0 |
| `state` | `TEXT` | 1 | - | 0 | 0 |
| `current_revision` | `INTEGER` | 1 | - | 0 | 0 |
| `head_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `projection_payload` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `intervention_id` | `doi_interventions` | `intervention_id` | `NO ACTION` | `CASCADE` |
| `case_id` | `doi_cases` | `case_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_resulting_order_mapping_components`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `link_id` | `TEXT` | 1 | - | 1 | 0 |
| `revision_no` | `INTEGER` | 1 | - | 2 | 0 |
| `parent_line_id` | `TEXT` | 1 | - | 3 | 0 |
| `child_line_id` | `TEXT` | 1 | - | 4 | 0 |
| `quantity_text` | `TEXT` | 1 | - | 0 | 0 |
| `ordinal` | `INTEGER` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `link_id` | `doi_resulting_order_link_revisions` | `link_id` | `NO ACTION` | `CASCADE` |
| `revision_no` | `doi_resulting_order_link_revisions` | `revision_no` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_resulting_order_search_events`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `search_id` | `TEXT` | 1 | - | 1 | 0 |
| `sequence_no` | `INTEGER` | 1 | - | 2 | 0 |
| `event_id` | `TEXT` | 1 | - | 0 | 0 |
| `predecessor_sha256` | `TEXT` | 0 | - | 0 | 0 |
| `record_domain` | `TEXT` | 1 | - | 0 | 0 |
| `record_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `record_payload` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `search_id` | `doi_resulting_order_searches` | `search_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_resulting_order_searches`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `search_id` | `TEXT` | 0 | - | 1 | 0 |
| `case_id` | `TEXT` | 1 | - | 0 | 0 |
| `parent_order_id` | `TEXT` | 1 | - | 0 | 0 |
| `intervention_type` | `TEXT` | 1 | - | 0 | 0 |
| `state` | `TEXT` | 1 | - | 0 | 0 |
| `revision` | `INTEGER` | 1 | - | 0 | 0 |
| `head_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `projection_payload` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `case_id` | `doi_cases` | `case_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE doi_resulting_order_searches (
    search_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES doi_cases(case_id) ON DELETE CASCADE,
    parent_order_id TEXT NOT NULL,
    intervention_type TEXT NOT NULL,
    state TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    head_sha256 TEXT NOT NULL CHECK (length(head_sha256) = 64),
    projection_payload BLOB NOT NULL CHECK (typeof(projection_payload) = 'blob')
)
```

### `doi_retained_kpi_contributions`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `intervention_id` | `TEXT` | 0 | - | 1 | 0 |
| `case_id` | `TEXT` | 1 | - | 0 | 0 |
| `intervention_type` | `TEXT` | 1 | - | 0 | 0 |
| `action_date` | `TEXT` | 1 | - | 0 | 0 |
| `amount_minor_units` | `INTEGER` | 1 | - | 0 | 0 |
| `currency_code` | `TEXT` | 1 | - | 0 | 0 |
| `currency_registry_version` | `TEXT` | 1 | - | 0 | 0 |
| `currency_scale` | `INTEGER` | 1 | - | 0 | 0 |
| `revision` | `INTEGER` | 1 | - | 0 | 0 |
| `head_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_payload` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `case_id` | `doi_cases` | `case_id` | `NO ACTION` | `CASCADE` |
| `intervention_id` | `doi_interventions` | `intervention_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_retention_deadlines`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `deadline_id` | `TEXT` | 0 | - | 1 | 0 |
| `case_id` | `TEXT` | 1 | - | 0 | 0 |
| `closure_event_id` | `TEXT` | 1 | - | 0 | 0 |
| `lifecycle_state` | `TEXT` | 1 | - | 0 | 0 |
| `closure_reason` | `TEXT` | 1 | - | 0 | 0 |
| `closed_at` | `TEXT` | 1 | - | 0 | 0 |
| `purge_eligible_at` | `TEXT` | 1 | - | 0 | 0 |
| `policy_version` | `TEXT` | 1 | - | 0 | 0 |
| `timezone_database_binding` | `TEXT` | 1 | - | 0 | 0 |
| `canceled_by_reopen_event_id` | `TEXT` | 0 | - | 0 | 0 |
| `record_payload` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `case_id` | `doi_cases` | `case_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_run_control_receipts`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `receipt_id` | `TEXT` | 0 | - | 1 | 0 |
| `run_id` | `TEXT` | 1 | - | 0 | 0 |
| `occurrence_key` | `TEXT` | 1 | - | 0 | 0 |
| `operation` | `TEXT` | 1 | - | 0 | 0 |
| `material_domain` | `TEXT` | 1 | - | 0 | 0 |
| `material_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `material_canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `result_payload` | `BLOB` | 1 | - | 0 | 0 |
| `committed_at` | `TEXT` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `run_id` | `doi_runs` | `run_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_run_events`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `run_id` | `TEXT` | 1 | - | 1 | 0 |
| `sequence_no` | `INTEGER` | 1 | - | 2 | 0 |
| `event_kind` | `TEXT` | 1 | - | 0 | 0 |
| `occurred_at` | `TEXT` | 1 | - | 0 | 0 |
| `predecessor_sha256` | `TEXT` | 0 | - | 0 | 0 |
| `record_domain` | `TEXT` | 1 | - | 0 | 0 |
| `record_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `record_payload` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `run_id` | `doi_runs` | `run_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_run_material_events`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `run_id` | `TEXT` | 1 | - | 1 | 0 |
| `material_version` | `INTEGER` | 1 | - | 2 | 0 |
| `cause_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_sha256` | `TEXT` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `run_id` | `doi_runs` | `run_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE doi_run_material_events (
    run_id TEXT NOT NULL REFERENCES doi_runs(run_id) ON DELETE CASCADE,
    material_version INTEGER NOT NULL CHECK (material_version > 0),
    cause_sha256 TEXT NOT NULL CHECK (length(cause_sha256) = 64),
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
    PRIMARY KEY (run_id, material_version),
    UNIQUE (run_id, cause_sha256)
)
```

### `doi_run_projections`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `run_id` | `TEXT` | 0 | - | 1 | 0 |
| `status` | `TEXT` | 1 | - | 0 | 0 |
| `projection_version` | `INTEGER` | 1 | - | 0 | 0 |
| `head_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `material_version` | `INTEGER` | 1 | - | 0 | 0 |
| `material_event_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `source_batch_id` | `TEXT` | 0 | - | 0 | 0 |
| `completed_at` | `TEXT` | 0 | - | 0 | 0 |
| `purge_eligible_at` | `TEXT` | 0 | - | 0 | 0 |
| `source_attempt_count` | `INTEGER` | 1 | - | 0 | 0 |
| `work_item_count` | `INTEGER` | 1 | - | 0 | 0 |
| `disposition_subject_count` | `INTEGER` | 1 | - | 0 | 0 |
| `successful_evaluation_count` | `INTEGER` | 1 | - | 0 | 0 |
| `order_exception_count` | `INTEGER` | 1 | - | 0 | 0 |
| `blocked_order_count` | `INTEGER` | 1 | - | 0 | 0 |
| `portal_read_count` | `INTEGER` | 1 | - | 0 | 0 |
| `record_domain` | `TEXT` | 1 | - | 0 | 0 |
| `record_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `record_payload` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `source_batch_id` | `doi_source_batches` | `batch_id` | `NO ACTION` | `NO ACTION` |
| `run_id` | `doi_runs` | `run_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_run_work_dispositions`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `work_item_id` | `TEXT` | 1 | - | 2 | 0 |
| `run_id` | `TEXT` | 1 | - | 1 | 0 |
| `disposition_kind` | `TEXT` | 1 | - | 0 | 0 |
| `occurred_at` | `TEXT` | 1 | - | 0 | 0 |
| `record_domain` | `TEXT` | 1 | - | 0 | 0 |
| `record_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `record_payload` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `run_id` | `doi_run_work_items` | `run_id` | `NO ACTION` | `CASCADE` |
| `work_item_id` | `doi_run_work_items` | `work_item_id` | `NO ACTION` | `CASCADE` |
| `run_id` | `doi_runs` | `run_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_run_work_items`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `work_item_id` | `TEXT` | 1 | - | 2 | 0 |
| `run_id` | `TEXT` | 1 | - | 1 | 0 |
| `order_id` | `TEXT` | 1 | - | 0 | 0 |
| `origin` | `TEXT` | 1 | - | 0 | 0 |
| `source_batch_id` | `TEXT` | 0 | - | 0 | 0 |
| `record_domain` | `TEXT` | 1 | - | 0 | 0 |
| `record_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `record_payload` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `source_batch_id` | `doi_source_batches` | `batch_id` | `NO ACTION` | `NO ACTION` |
| `run_id` | `doi_runs` | `run_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_runs`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `run_id` | `TEXT` | 0 | - | 1 | 0 |
| `invocation_id` | `TEXT` | 1 | - | 0 | 0 |
| `run_type` | `TEXT` | 1 | - | 0 | 0 |
| `recheck_order_id` | `TEXT` | 0 | - | 0 | 0 |
| `started_at` | `TEXT` | 1 | - | 0 | 0 |

```sql
CREATE TABLE doi_runs (
    run_id TEXT PRIMARY KEY,
    invocation_id TEXT NOT NULL UNIQUE,
    run_type TEXT NOT NULL CHECK (run_type IN ('RUN_DOI_REVIEW', 'RECHECK_ORDER', 'RECHECK_DEDUPE_ORDER')),
    recheck_order_id TEXT,
    started_at TEXT NOT NULL,
    CHECK ((run_type = 'RUN_DOI_REVIEW') = (recheck_order_id IS NULL))
)
```

### `doi_snapshot_completeness_proof_references`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `snapshot_id` | `TEXT` | 0 | - | 1 | 0 |
| `proof_artifact_pk` | `INTEGER` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `proof_artifact_pk` | `doi_case_artifacts` | `artifact_pk` | `NO ACTION` | `CASCADE` |
| `snapshot_id` | `doi_order_snapshots` | `snapshot_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE doi_snapshot_completeness_proof_references (
    snapshot_id TEXT PRIMARY KEY REFERENCES doi_order_snapshots(snapshot_id) ON DELETE CASCADE,
    proof_artifact_pk INTEGER NOT NULL REFERENCES doi_case_artifacts(artifact_pk) ON DELETE CASCADE
)
```

### `doi_source_batches`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `batch_id` | `TEXT` | 0 | - | 1 | 0 |
| `source_identity_id` | `TEXT` | 1 | - | 0 | 0 |
| `identity_domain` | `TEXT` | 1 | - | 0 | 0 |
| `identity_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `identity_canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `record_domain` | `TEXT` | 1 | - | 0 | 0 |
| `record_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `record_payload` | `BLOB` | 1 | - | 0 | 0 |
| `mapping_version` | `TEXT` | 1 | - | 0 | 0 |
| `finite_extent` | `INTEGER` | 1 | - | 0 | 0 |
| `status` | `TEXT` | 1 | - | 0 | 0 |

```sql
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
)
```

### `doi_source_import_aggregates`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `month_key` | `TEXT` | 1 | - | 1 | 0 |
| `outcome_class` | `TEXT` | 1 | - | 2 | 0 |
| `attempt_count` | `INTEGER` | 1 | - | 0 | 0 |

```sql
CREATE TABLE doi_source_import_aggregates (
    month_key TEXT NOT NULL CHECK (month_key GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'),
    outcome_class TEXT NOT NULL CHECK (outcome_class IN ('SUCCEEDED', 'FAILED', 'ABORTED')),
    attempt_count INTEGER NOT NULL CHECK (attempt_count >= 0),
    PRIMARY KEY (month_key, outcome_class)
)
```

### `doi_source_import_attempt_events`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `attempt_id` | `TEXT` | 1 | - | 1 | 0 |
| `sequence_no` | `INTEGER` | 1 | - | 2 | 0 |
| `event_kind` | `TEXT` | 1 | - | 0 | 0 |
| `occurred_at` | `TEXT` | 1 | - | 0 | 0 |
| `predecessor_sha256` | `TEXT` | 0 | - | 0 | 0 |
| `record_domain` | `TEXT` | 1 | - | 0 | 0 |
| `record_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `record_payload` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `attempt_id` | `doi_source_import_attempts` | `attempt_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_source_import_attempts`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `attempt_id` | `TEXT` | 0 | - | 1 | 0 |
| `run_id` | `TEXT` | 1 | - | 0 | 0 |
| `ordinal` | `INTEGER` | 1 | - | 0 | 0 |
| `source_identity_id` | `TEXT` | 1 | - | 0 | 0 |
| `state` | `TEXT` | 1 | - | 0 | 0 |
| `started_at` | `TEXT` | 1 | - | 0 | 0 |
| `completed_at` | `TEXT` | 0 | - | 0 | 0 |
| `source_batch_id` | `TEXT` | 0 | - | 0 | 0 |
| `portal_read_count` | `INTEGER` | 1 | - | 0 | 0 |
| `projection_version` | `INTEGER` | 1 | - | 0 | 0 |
| `head_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_domain` | `TEXT` | 1 | - | 0 | 0 |
| `record_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `record_payload` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `source_batch_id` | `doi_source_batches` | `batch_id` | `NO ACTION` | `NO ACTION` |
| `run_id` | `doi_runs` | `run_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `doi_staged_order_source_refs`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `attempt_id` | `TEXT` | 1 | - | 1 | 0 |
| `order_id` | `TEXT` | 1 | - | 2 | 0 |
| `source_ref_id` | `TEXT` | 1 | - | 3 | 0 |
| `ordinal` | `INTEGER` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `attempt_id` | `doi_staged_orders` | `attempt_id` | `NO ACTION` | `CASCADE` |
| `order_id` | `doi_staged_orders` | `order_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE doi_staged_order_source_refs (
    attempt_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    source_ref_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    PRIMARY KEY (attempt_id, order_id, source_ref_id),
    UNIQUE (attempt_id, order_id, ordinal),
    FOREIGN KEY (attempt_id, order_id) REFERENCES doi_staged_orders(attempt_id, order_id) ON DELETE CASCADE
)
```

### `doi_staged_orders`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `attempt_id` | `TEXT` | 1 | - | 1 | 0 |
| `order_id` | `TEXT` | 1 | - | 2 | 0 |
| `batch_id` | `TEXT` | 1 | - | 0 | 0 |
| `record_domain` | `TEXT` | 1 | - | 0 | 0 |
| `record_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `record_payload` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `batch_id` | `doi_source_batches` | `batch_id` | `NO ACTION` | `NO ACTION` |
| `attempt_id` | `doi_source_import_attempts` | `attempt_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE doi_staged_orders (
    attempt_id TEXT NOT NULL REFERENCES doi_source_import_attempts(attempt_id) ON DELETE CASCADE,
    order_id TEXT NOT NULL,
    batch_id TEXT NOT NULL REFERENCES doi_source_batches(batch_id),
    record_domain TEXT NOT NULL,
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
    record_canonical_bytes BLOB NOT NULL CHECK (typeof(record_canonical_bytes) = 'blob'),
    record_payload BLOB NOT NULL CHECK (typeof(record_payload) = 'blob'),
    PRIMARY KEY (attempt_id, order_id)
)
```

### `doi_value_events`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `intervention_id` | `TEXT` | 1 | - | 1 | 0 |
| `event_id` | `TEXT` | 1 | - | 0 | 0 |
| `sequence_no` | `INTEGER` | 1 | - | 2 | 0 |
| `occurrence_id` | `TEXT` | 1 | - | 0 | 0 |
| `event_type` | `TEXT` | 1 | - | 0 | 0 |
| `predecessor_sha256` | `TEXT` | 0 | - | 0 | 0 |
| `amount_minor_units` | `INTEGER` | 1 | - | 0 | 0 |
| `currency_code` | `TEXT` | 1 | - | 0 | 0 |
| `currency_registry_version` | `TEXT` | 1 | - | 0 | 0 |
| `currency_scale` | `INTEGER` | 1 | - | 0 | 0 |
| `record_domain` | `TEXT` | 1 | - | 0 | 0 |
| `record_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `record_canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `record_payload` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `intervention_id` | `doi_interventions` | `intervention_id` | `NO ACTION` | `CASCADE` |

```sql
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
)
```

### `durable_command_receipts`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `command_id` | `TEXT` | 1 | - | 1 | 0 |
| `result_domain` | `TEXT` | 1 | - | 0 | 0 |
| `result_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `result_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `recorded_at` | `TEXT` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `command_id` | `durable_commands` | `command_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE durable_command_receipts (
    command_id TEXT PRIMARY KEY COLLATE BINARY
        REFERENCES durable_commands(command_id) ON DELETE CASCADE,
    result_domain TEXT NOT NULL COLLATE BINARY
        CHECK (length(result_domain) BETWEEN 3 AND 128),
    result_sha256 TEXT NOT NULL COLLATE BINARY
        CHECK (
            length(result_sha256) = 64
            AND result_sha256 NOT GLOB '*[^0-9a-f]*'
        ),
    result_bytes BLOB NOT NULL CHECK (length(result_bytes) BETWEEN 2 AND 1048576),
    recorded_at TEXT NOT NULL COLLATE BINARY
        CHECK (recorded_at GLOB '*Z')
) STRICT
```

### `durable_commands`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `command_id` | `TEXT` | 1 | - | 1 | 0 |
| `natural_namespace` | `TEXT` | 1 | - | 0 | 0 |
| `natural_key` | `TEXT` | 1 | - | 0 | 0 |
| `command_domain` | `TEXT` | 1 | - | 0 | 0 |
| `command_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `command_bytes` | `BLOB` | 1 | - | 0 | 0 |
| `accepted_at` | `TEXT` | 1 | - | 0 | 0 |

```sql
CREATE TABLE durable_commands (
    command_id TEXT PRIMARY KEY COLLATE BINARY
        CHECK (length(command_id) BETWEEN 1 AND 128),
    natural_namespace TEXT NOT NULL COLLATE BINARY
        CHECK (
            length(natural_namespace) BETWEEN 1 AND 64
            AND natural_namespace NOT GLOB '*[^a-z0-9_.-]*'
        ),
    natural_key TEXT NOT NULL COLLATE BINARY
        CHECK (length(natural_key) BETWEEN 1 AND 512),
    command_domain TEXT NOT NULL COLLATE BINARY
        CHECK (length(command_domain) BETWEEN 3 AND 128),
    command_sha256 TEXT NOT NULL COLLATE BINARY
        CHECK (
            length(command_sha256) = 64
            AND command_sha256 NOT GLOB '*[^0-9a-f]*'
        ),
    command_bytes BLOB NOT NULL CHECK (length(command_bytes) BETWEEN 2 AND 1048576),
    accepted_at TEXT NOT NULL COLLATE BINARY
        CHECK (accepted_at GLOB '*Z'),
    UNIQUE (natural_namespace, natural_key)
) STRICT
```

### `durable_receipt_owners`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `command_id` | `TEXT` | 1 | - | 1 | 0 |
| `owner_domain` | `TEXT` | 1 | - | 2 | 0 |
| `owner_id` | `TEXT` | 1 | - | 3 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `command_id` | `durable_command_receipts` | `command_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE durable_receipt_owners (
    command_id TEXT NOT NULL COLLATE BINARY
        REFERENCES durable_command_receipts(command_id) ON DELETE CASCADE,
    owner_domain TEXT NOT NULL COLLATE BINARY
        CHECK (owner_domain IN ('SALES_CREDIT', 'DOI', 'SYSTEM')),
    owner_id TEXT NOT NULL COLLATE BINARY
        CHECK (length(owner_id) BETWEEN 1 AND 128),
    PRIMARY KEY (command_id, owner_domain, owner_id)
) STRICT
```

### `processing_telemetry`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `operation_id` | `TEXT` | 1 | - | 1 | 0 |
| `rule_pack` | `TEXT` | 1 | - | 0 | 0 |
| `demo_alias` | `TEXT` | 0 | - | 0 | 0 |
| `started_at` | `TEXT` | 1 | - | 0 | 0 |
| `ended_at` | `TEXT` | 1 | - | 0 | 0 |
| `extraction_ns` | `INTEGER` | 1 | - | 0 | 0 |
| `validation_ns` | `INTEGER` | 1 | - | 0 | 0 |
| `normalization_ns` | `INTEGER` | 1 | - | 0 | 0 |
| `rule_ns` | `INTEGER` | 1 | - | 0 | 0 |
| `database_ns` | `INTEGER` | 1 | - | 0 | 0 |
| `total_ns` | `INTEGER` | 1 | - | 0 | 0 |
| `result_class` | `TEXT` | 1 | - | 0 | 0 |
| `human_review` | `INTEGER` | 1 | - | 0 | 0 |
| `fail_closed` | `INTEGER` | 1 | - | 0 | 0 |
| `replay` | `INTEGER` | 1 | - | 0 | 0 |
| `conflict` | `INTEGER` | 1 | - | 0 | 0 |
| `database_error` | `INTEGER` | 1 | - | 0 | 0 |
| `rule_version` | `TEXT` | 1 | - | 0 | 0 |
| `schema_version` | `TEXT` | 1 | - | 0 | 0 |
| `catalog_version` | `TEXT` | 0 | - | 0 | 0 |
| `error_code` | `TEXT` | 0 | - | 0 | 0 |

```sql
CREATE TABLE processing_telemetry (
    operation_id TEXT PRIMARY KEY COLLATE BINARY
        CHECK (length(operation_id) BETWEEN 1 AND 128),
    rule_pack TEXT NOT NULL COLLATE BINARY
        CHECK (rule_pack IN ('SHARED', 'SALES_CREDIT', 'DOI')),
    demo_alias TEXT COLLATE BINARY CHECK (demo_alias IS NULL OR length(demo_alias) BETWEEN 1 AND 96),
    started_at TEXT NOT NULL COLLATE BINARY CHECK (started_at GLOB '*Z'),
    ended_at TEXT NOT NULL COLLATE BINARY CHECK (ended_at GLOB '*Z'),
    extraction_ns INTEGER NOT NULL CHECK (extraction_ns >= 0),
    validation_ns INTEGER NOT NULL CHECK (validation_ns >= 0),
    normalization_ns INTEGER NOT NULL CHECK (normalization_ns >= 0),
    rule_ns INTEGER NOT NULL CHECK (rule_ns >= 0),
    database_ns INTEGER NOT NULL CHECK (database_ns >= 0),
    total_ns INTEGER NOT NULL CHECK (total_ns >= 0),
    result_class TEXT NOT NULL COLLATE BINARY CHECK (length(result_class) BETWEEN 1 AND 96),
    human_review INTEGER NOT NULL CHECK (human_review IN (0, 1)),
    fail_closed INTEGER NOT NULL CHECK (fail_closed IN (0, 1)),
    replay INTEGER NOT NULL CHECK (replay IN (0, 1)),
    conflict INTEGER NOT NULL CHECK (conflict IN (0, 1)),
    database_error INTEGER NOT NULL CHECK (database_error IN (0, 1)),
    rule_version TEXT NOT NULL COLLATE BINARY CHECK (length(rule_version) BETWEEN 1 AND 128),
    schema_version TEXT NOT NULL COLLATE BINARY CHECK (length(schema_version) BETWEEN 1 AND 128),
    catalog_version TEXT COLLATE BINARY CHECK (catalog_version IS NULL OR length(catalog_version) BETWEEN 1 AND 128),
    error_code TEXT COLLATE BINARY
        CHECK (
            error_code IS NULL
            OR (
                length(error_code) BETWEEN 1 AND 96
                AND error_code NOT GLOB '*[^A-Z0-9_-]*'
            )
        ),
    CHECK (total_ns >= extraction_ns),
    CHECK (total_ns >= validation_ns),
    CHECK (total_ns >= normalization_ns),
    CHECK (total_ns >= rule_ns),
    CHECK (total_ns >= database_ns)
) STRICT
```

### `restore_receipts`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `restore_id` | `TEXT` | 1 | - | 1 | 0 |
| `started_at` | `TEXT` | 1 | - | 0 | 0 |
| `completed_at` | `TEXT` | 0 | - | 0 | 0 |
| `backup_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `pre_restore_backup_id` | `TEXT` | 0 | - | 0 | 0 |
| `schema_version` | `INTEGER` | 0 | - | 0 | 0 |
| `status` | `TEXT` | 1 | - | 0 | 0 |
| `error_code` | `TEXT` | 0 | - | 0 | 0 |

```sql
CREATE TABLE restore_receipts (
    restore_id TEXT PRIMARY KEY COLLATE BINARY CHECK (length(restore_id) BETWEEN 1 AND 128),
    started_at TEXT NOT NULL COLLATE BINARY CHECK (started_at GLOB '*Z'),
    completed_at TEXT COLLATE BINARY CHECK (completed_at IS NULL OR completed_at GLOB '*Z'),
    backup_sha256 TEXT NOT NULL COLLATE BINARY
        CHECK (length(backup_sha256) = 64 AND backup_sha256 NOT GLOB '*[^0-9a-f]*'),
    pre_restore_backup_id TEXT COLLATE BINARY,
    schema_version INTEGER CHECK (schema_version IS NULL OR schema_version > 0),
    status TEXT NOT NULL COLLATE BINARY CHECK (status IN ('STARTED', 'COMPLETED', 'FAILED')),
    error_code TEXT COLLATE BINARY
        CHECK (error_code IS NULL OR (length(error_code) BETWEEN 1 AND 96 AND error_code NOT GLOB '*[^A-Z0-9_-]*'))
) STRICT
```

### `sc_active_replacement_links`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `candidate_order_id` | `TEXT` | 1 | - | 1 | 0 |
| `parent_order_id` | `TEXT` | 1 | - | 0 | 0 |
| `replacement_run_id` | `TEXT` | 1 | - | 0 | 0 |
| `linked_at` | `TEXT` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `replacement_run_id` | `sc_search_runs` | `run_id` | `NO ACTION` | `RESTRICT` |
| `parent_order_id` | `sc_cases` | `order_id` | `NO ACTION` | `RESTRICT` |
| `candidate_order_id` | `sc_cases` | `order_id` | `NO ACTION` | `RESTRICT` |

```sql
CREATE TABLE sc_active_replacement_links (
    candidate_order_id TEXT PRIMARY KEY COLLATE BINARY
        REFERENCES sc_cases(order_id) ON DELETE RESTRICT,
    parent_order_id TEXT NOT NULL COLLATE BINARY
        REFERENCES sc_cases(order_id) ON DELETE RESTRICT,
    replacement_run_id TEXT NOT NULL COLLATE BINARY
        REFERENCES sc_search_runs(run_id) ON DELETE RESTRICT,
    linked_at TEXT NOT NULL COLLATE BINARY CHECK (linked_at GLOB '*Z'),
    CHECK (parent_order_id != candidate_order_id)
) STRICT
```

### `sc_case_evaluations`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `order_id` | `TEXT` | 1 | - | 1 | 0 |
| `evaluation_id` | `TEXT` | 1 | - | 2 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `evaluation_id` | `sc_evaluations` | `evaluation_id` | `NO ACTION` | `RESTRICT` |
| `order_id` | `sc_cases` | `order_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE sc_case_evaluations (
    order_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_cases(order_id) ON DELETE CASCADE,
    evaluation_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_evaluations(evaluation_id) ON DELETE RESTRICT,
    PRIMARY KEY (order_id, evaluation_id)
) STRICT
```

### `sc_case_events`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `event_id` | `TEXT` | 1 | - | 1 | 0 |
| `order_id` | `TEXT` | 1 | - | 0 | 0 |
| `sequence` | `INTEGER` | 1 | - | 0 | 0 |
| `predecessor_event_id` | `TEXT` | 0 | - | 0 | 0 |
| `event_kind` | `TEXT` | 1 | - | 0 | 0 |
| `workflow_state` | `TEXT` | 1 | - | 0 | 0 |
| `attribution` | `TEXT` | 1 | - | 0 | 0 |
| `order_value_status` | `TEXT` | 1 | - | 0 | 0 |
| `manager_outcome` | `TEXT` | 0 | - | 0 | 0 |
| `current_evaluation_id` | `TEXT` | 0 | - | 0 | 0 |
| `replacement_parent_present` | `INTEGER` | 1 | - | 0 | 0 |
| `occurred_at` | `TEXT` | 1 | - | 0 | 0 |
| `command_id` | `TEXT` | 1 | - | 0 | 0 |
| `canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `predecessor_event_id` | `sc_case_events` | `event_id` | `NO ACTION` | `NO ACTION` |

```sql
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
) STRICT
```

### `sc_case_evidence`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `order_id` | `TEXT` | 1 | - | 1 | 0 |
| `evidence_id` | `TEXT` | 1 | - | 2 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `evidence_id` | `sc_evidence_events` | `evidence_id` | `NO ACTION` | `RESTRICT` |
| `order_id` | `sc_cases` | `order_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE sc_case_evidence (
    order_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_cases(order_id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_evidence_events(evidence_id) ON DELETE RESTRICT,
    PRIMARY KEY (order_id, evidence_id)
) STRICT
```

### `sc_case_interactions`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `order_id` | `TEXT` | 1 | - | 1 | 0 |
| `interaction_id` | `TEXT` | 1 | - | 2 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `interaction_id` | `sc_interactions` | `interaction_id` | `NO ACTION` | `RESTRICT` |
| `order_id` | `sc_cases` | `order_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE sc_case_interactions (
    order_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_cases(order_id) ON DELETE CASCADE,
    interaction_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_interactions(interaction_id) ON DELETE RESTRICT,
    PRIMARY KEY (order_id, interaction_id)
) STRICT
```

### `sc_case_search_runs`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `order_id` | `TEXT` | 1 | - | 1 | 0 |
| `run_id` | `TEXT` | 1 | - | 2 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `run_id` | `sc_search_runs` | `run_id` | `NO ACTION` | `RESTRICT` |
| `order_id` | `sc_cases` | `order_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE sc_case_search_runs (
    order_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_cases(order_id) ON DELETE CASCADE,
    run_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_search_runs(run_id) ON DELETE RESTRICT,
    PRIMARY KEY (order_id, run_id)
) STRICT
```

### `sc_case_snapshots`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `order_id` | `TEXT` | 1 | - | 1 | 0 |
| `snapshot_id` | `TEXT` | 1 | - | 2 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `snapshot_id` | `sc_snapshots` | `snapshot_id` | `NO ACTION` | `RESTRICT` |
| `order_id` | `sc_cases` | `order_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE sc_case_snapshots (
    order_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_cases(order_id) ON DELETE CASCADE,
    snapshot_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_snapshots(snapshot_id) ON DELETE RESTRICT,
    PRIMARY KEY (order_id, snapshot_id)
) STRICT
```

### `sc_cases`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `order_id` | `TEXT` | 1 | - | 1 | 0 |
| `projection_version` | `INTEGER` | 1 | - | 0 | 0 |
| `workflow_state` | `TEXT` | 1 | - | 0 | 0 |
| `attribution` | `TEXT` | 1 | - | 0 | 0 |
| `order_value_status` | `TEXT` | 1 | - | 0 | 0 |
| `placed_minor_units` | `TEXT` | 0 | - | 0 | 0 |
| `placed_currency` | `TEXT` | 0 | - | 0 | 0 |
| `placed_registry_version` | `TEXT` | 0 | - | 0 | 0 |
| `placed_scale` | `INTEGER` | 0 | - | 0 | 0 |
| `manager_occurrence_id` | `TEXT` | 0 | - | 0 | 0 |
| `replacement_parent_order_id` | `TEXT` | 0 | - | 0 | 0 |
| `current_evaluation_id` | `TEXT` | 0 | - | 0 | 0 |
| `last_event_sequence` | `INTEGER` | 1 | - | 0 | 0 |
| `last_event_id` | `TEXT` | 1 | - | 0 | 0 |
| `created_at` | `TEXT` | 1 | - | 0 | 0 |
| `updated_at` | `TEXT` | 1 | - | 0 | 0 |

```sql
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
) STRICT
```

### `sc_closed_audits`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `audit_id` | `TEXT` | 1 | - | 1 | 0 |
| `order_id` | `TEXT` | 1 | - | 0 | 0 |
| `closed_at` | `TEXT` | 1 | - | 0 | 0 |
| `purge_eligible_at` | `TEXT` | 1 | - | 0 | 0 |
| `workflow_before_close` | `TEXT` | 1 | - | 0 | 0 |
| `human_outcome` | `TEXT` | 0 | - | 0 | 0 |
| `material_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `order_id` | `sc_cases` | `order_id` | `NO ACTION` | `CASCADE` |

```sql
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
) STRICT
```

### `sc_daily_aggregates`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `business_date` | `TEXT` | 1 | - | 1 | 0 |
| `result_class` | `TEXT` | 1 | - | 2 | 0 |
| `occurrence_count` | `INTEGER` | 1 | - | 0 | 0 |

```sql
CREATE TABLE sc_daily_aggregates (
    business_date TEXT NOT NULL COLLATE BINARY CHECK (business_date GLOB '????-??-??'),
    result_class TEXT NOT NULL COLLATE BINARY CHECK (length(result_class) BETWEEN 1 AND 96),
    occurrence_count INTEGER NOT NULL CHECK (occurrence_count >= 0),
    PRIMARY KEY (business_date, result_class)
) STRICT
```

### `sc_evaluation_reasons`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `evaluation_id` | `TEXT` | 1 | - | 1 | 0 |
| `ordinal` | `INTEGER` | 1 | - | 2 | 0 |
| `reason_code` | `TEXT` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `evaluation_id` | `sc_evaluations` | `evaluation_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE sc_evaluation_reasons (
    evaluation_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_evaluations(evaluation_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 1),
    reason_code TEXT NOT NULL COLLATE BINARY CHECK (length(reason_code) BETWEEN 1 AND 96),
    PRIMARY KEY (evaluation_id, ordinal),
    UNIQUE (evaluation_id, reason_code)
) STRICT
```

### `sc_evaluations`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `evaluation_id` | `TEXT` | 1 | - | 1 | 0 |
| `order_id` | `TEXT` | 1 | - | 0 | 0 |
| `snapshot_id` | `TEXT` | 1 | - | 0 | 0 |
| `workflow_state` | `TEXT` | 1 | - | 0 | 0 |
| `attribution` | `TEXT` | 1 | - | 0 | 0 |
| `order_value_status` | `TEXT` | 1 | - | 0 | 0 |
| `human_review_required` | `INTEGER` | 1 | - | 0 | 0 |
| `rule_pack_version` | `TEXT` | 1 | - | 0 | 0 |
| `material_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `snapshot_id` | `sc_snapshots` | `snapshot_id` | `NO ACTION` | `RESTRICT` |

```sql
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
) STRICT
```

### `sc_evidence_events`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `evidence_id` | `TEXT` | 1 | - | 1 | 0 |
| `order_id` | `TEXT` | 1 | - | 0 | 0 |
| `interaction_id` | `TEXT` | 1 | - | 0 | 0 |
| `source_type` | `TEXT` | 1 | - | 0 | 0 |
| `classification` | `TEXT` | 1 | - | 0 | 0 |
| `occurred_at` | `TEXT` | 1 | - | 0 | 0 |
| `canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `interaction_id` | `sc_interactions` | `interaction_id` | `NO ACTION` | `RESTRICT` |

```sql
CREATE TABLE sc_evidence_events (
    evidence_id TEXT PRIMARY KEY COLLATE BINARY CHECK (evidence_id GLOB 'SYN-EVIDENCE-*'),
    order_id TEXT NOT NULL COLLATE BINARY CHECK (order_id GLOB 'SYN-ORDER-*'),
    interaction_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_interactions(interaction_id) ON DELETE RESTRICT,
    source_type TEXT NOT NULL COLLATE BINARY CHECK (length(source_type) BETWEEN 1 AND 64),
    classification TEXT NOT NULL COLLATE BINARY CHECK (length(classification) BETWEEN 1 AND 64),
    occurred_at TEXT NOT NULL COLLATE BINARY CHECK (occurred_at GLOB '*Z'),
    canonical_bytes BLOB NOT NULL CHECK (length(canonical_bytes) BETWEEN 2 AND 1048576)
) STRICT
```

### `sc_interactions`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `interaction_id` | `TEXT` | 1 | - | 1 | 0 |
| `source_ref_id` | `TEXT` | 1 | - | 0 | 0 |
| `recorded_at` | `TEXT` | 1 | - | 0 | 0 |
| `timestamp_precision` | `TEXT` | 1 | - | 0 | 0 |
| `workflow_state` | `TEXT` | 1 | - | 0 | 0 |
| `canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |

```sql
CREATE TABLE sc_interactions (
    interaction_id TEXT PRIMARY KEY COLLATE BINARY CHECK (interaction_id GLOB 'SYN-INTERACTION-*'),
    source_ref_id TEXT NOT NULL COLLATE BINARY CHECK (source_ref_id GLOB 'SYN-EVIDENCE-*'),
    recorded_at TEXT NOT NULL COLLATE BINARY CHECK (recorded_at GLOB '*Z'),
    timestamp_precision TEXT NOT NULL COLLATE BINARY CHECK (length(timestamp_precision) BETWEEN 1 AND 64),
    workflow_state TEXT NOT NULL COLLATE BINARY CHECK (length(workflow_state) BETWEEN 1 AND 64),
    canonical_bytes BLOB NOT NULL CHECK (length(canonical_bytes) BETWEEN 2 AND 1048576)
) STRICT
```

### `sc_manager_outcomes`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `occurrence_id` | `TEXT` | 1 | - | 1 | 0 |
| `order_id` | `TEXT` | 1 | - | 0 | 0 |
| `outcome` | `TEXT` | 1 | - | 0 | 0 |
| `decided_at` | `TEXT` | 1 | - | 0 | 0 |
| `recorded_at` | `TEXT` | 1 | - | 0 | 0 |
| `actor_id` | `TEXT` | 1 | - | 0 | 0 |
| `approved_minor_units` | `TEXT` | 0 | - | 0 | 0 |
| `approved_currency` | `TEXT` | 0 | - | 0 | 0 |
| `approved_registry_version` | `TEXT` | 0 | - | 0 | 0 |
| `approved_scale` | `INTEGER` | 0 | - | 0 | 0 |
| `material_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `order_id` | `sc_cases` | `order_id` | `NO ACTION` | `CASCADE` |

```sql
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
) STRICT
```

### `sc_no_order_closed_audits`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `audit_id` | `TEXT` | 1 | - | 1 | 0 |
| `command_id` | `TEXT` | 1 | - | 0 | 0 |
| `closed_at` | `TEXT` | 1 | - | 0 | 0 |
| `purge_eligible_at` | `TEXT` | 1 | - | 0 | 0 |
| `material_sha256` | `TEXT` | 1 | - | 0 | 0 |
| `canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `command_id` | `durable_commands` | `command_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE sc_no_order_closed_audits (
    audit_id TEXT PRIMARY KEY COLLATE BINARY CHECK (audit_id GLOB 'SYN-EVIDENCE-*'),
    command_id TEXT NOT NULL UNIQUE COLLATE BINARY
        REFERENCES durable_commands(command_id) ON DELETE CASCADE,
    closed_at TEXT NOT NULL COLLATE BINARY CHECK (closed_at GLOB '*Z'),
    purge_eligible_at TEXT NOT NULL COLLATE BINARY CHECK (purge_eligible_at GLOB '*Z'),
    material_sha256 TEXT NOT NULL COLLATE BINARY
        CHECK (length(material_sha256) = 64 AND material_sha256 NOT GLOB '*[^0-9a-f]*'),
    canonical_bytes BLOB NOT NULL CHECK (length(canonical_bytes) BETWEEN 2 AND 1048576)
) STRICT
```

### `sc_replacement_candidates`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `parent_order_id` | `TEXT` | 1 | - | 0 | 0 |
| `evaluation_id` | `TEXT` | 1 | - | 1 | 0 |
| `replacement_run_id` | `TEXT` | 1 | - | 0 | 0 |
| `candidate_order_id` | `TEXT` | 1 | - | 2 | 0 |
| `snapshot_id` | `TEXT` | 1 | - | 0 | 0 |
| `candidate_status` | `TEXT` | 1 | - | 0 | 0 |
| `customer_continuity` | `TEXT` | 1 | - | 0 | 0 |
| `product_continuity` | `TEXT` | 1 | - | 0 | 0 |
| `line_universe_complete` | `INTEGER` | 1 | - | 0 | 0 |
| `possible_nonexact_continuity` | `INTEGER` | 1 | - | 0 | 0 |
| `canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `snapshot_id` | `sc_snapshots` | `snapshot_id` | `NO ACTION` | `RESTRICT` |
| `replacement_run_id` | `sc_search_runs` | `run_id` | `NO ACTION` | `RESTRICT` |
| `evaluation_id` | `sc_evaluations` | `evaluation_id` | `NO ACTION` | `CASCADE` |
| `parent_order_id` | `sc_cases` | `order_id` | `NO ACTION` | `CASCADE` |

```sql
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
) STRICT
```

### `sc_search_identifiers`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `run_id` | `TEXT` | 1 | - | 1 | 0 |
| `interaction_id` | `TEXT` | 1 | - | 2 | 0 |
| `identifier_kind` | `TEXT` | 1 | - | 3 | 0 |
| `normalized_value` | `TEXT` | 1 | - | 0 | 0 |
| `completeness` | `TEXT` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `interaction_id` | `sc_interactions` | `interaction_id` | `NO ACTION` | `CASCADE` |
| `run_id` | `sc_search_runs` | `run_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE sc_search_identifiers (
    run_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_search_runs(run_id) ON DELETE CASCADE,
    interaction_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_interactions(interaction_id) ON DELETE CASCADE,
    identifier_kind TEXT NOT NULL COLLATE BINARY CHECK (identifier_kind IN ('EMAIL', 'PHONE')),
    normalized_value TEXT NOT NULL COLLATE BINARY CHECK (length(normalized_value) BETWEEN 3 AND 320),
    completeness TEXT NOT NULL COLLATE BINARY CHECK (length(completeness) BETWEEN 1 AND 32),
    PRIMARY KEY (run_id, interaction_id, identifier_kind)
) STRICT
```

### `sc_search_result_orders`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `run_id` | `TEXT` | 1 | - | 1 | 0 |
| `interaction_id` | `TEXT` | 1 | - | 2 | 0 |
| `identifier_kind` | `TEXT` | 1 | - | 3 | 0 |
| `order_id` | `TEXT` | 1 | - | 4 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `run_id` | `sc_search_identifiers` | `run_id` | `NO ACTION` | `CASCADE` |
| `interaction_id` | `sc_search_identifiers` | `interaction_id` | `NO ACTION` | `CASCADE` |
| `identifier_kind` | `sc_search_identifiers` | `identifier_kind` | `NO ACTION` | `CASCADE` |
| `interaction_id` | `sc_interactions` | `interaction_id` | `NO ACTION` | `CASCADE` |
| `run_id` | `sc_search_runs` | `run_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE sc_search_result_orders (
    run_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_search_runs(run_id) ON DELETE CASCADE,
    interaction_id TEXT NOT NULL COLLATE BINARY REFERENCES sc_interactions(interaction_id) ON DELETE CASCADE,
    identifier_kind TEXT NOT NULL COLLATE BINARY CHECK (identifier_kind IN ('EMAIL', 'PHONE')),
    order_id TEXT NOT NULL COLLATE BINARY CHECK (order_id GLOB 'SYN-ORDER-*'),
    PRIMARY KEY (run_id, interaction_id, identifier_kind, order_id),
    FOREIGN KEY (run_id, interaction_id, identifier_kind)
        REFERENCES sc_search_identifiers(run_id, interaction_id, identifier_kind)
        ON DELETE CASCADE
) STRICT
```

### `sc_search_runs`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `run_id` | `TEXT` | 1 | - | 1 | 0 |
| `trigger_type` | `TEXT` | 1 | - | 0 | 0 |
| `started_at` | `TEXT` | 1 | - | 0 | 0 |
| `completed_at` | `TEXT` | 1 | - | 0 | 0 |
| `adapter_version` | `TEXT` | 1 | - | 0 | 0 |
| `enumeration_complete` | `INTEGER` | 1 | - | 0 | 0 |
| `terminal_outcome` | `TEXT` | 1 | - | 0 | 0 |
| `canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |

```sql
CREATE TABLE sc_search_runs (
    run_id TEXT PRIMARY KEY COLLATE BINARY CHECK (run_id GLOB 'SYN-RUN-*'),
    trigger_type TEXT NOT NULL COLLATE BINARY CHECK (length(trigger_type) BETWEEN 1 AND 64),
    started_at TEXT NOT NULL COLLATE BINARY CHECK (started_at GLOB '*Z'),
    completed_at TEXT NOT NULL COLLATE BINARY CHECK (completed_at GLOB '*Z'),
    adapter_version TEXT NOT NULL COLLATE BINARY CHECK (length(adapter_version) BETWEEN 1 AND 128),
    enumeration_complete INTEGER NOT NULL CHECK (enumeration_complete IN (0, 1)),
    terminal_outcome TEXT NOT NULL COLLATE BINARY CHECK (length(terminal_outcome) BETWEEN 1 AND 96),
    canonical_bytes BLOB NOT NULL CHECK (length(canonical_bytes) BETWEEN 2 AND 1048576)
) STRICT
```

### `sc_snapshot_lines`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `snapshot_id` | `TEXT` | 1 | - | 1 | 0 |
| `line_id` | `TEXT` | 1 | - | 2 | 0 |
| `sku_id` | `TEXT` | 1 | - | 0 | 0 |
| `quantity` | `TEXT` | 1 | - | 0 | 0 |
| `line_minor_units` | `TEXT` | 0 | - | 0 | 0 |
| `currency` | `TEXT` | 0 | - | 0 | 0 |
| `currency_registry_version` | `TEXT` | 0 | - | 0 | 0 |
| `currency_scale` | `INTEGER` | 0 | - | 0 | 0 |
| `canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `snapshot_id` | `sc_snapshots` | `snapshot_id` | `NO ACTION` | `CASCADE` |

```sql
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
) STRICT
```

### `sc_snapshots`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `snapshot_id` | `TEXT` | 1 | - | 1 | 0 |
| `order_id` | `TEXT` | 1 | - | 0 | 0 |
| `captured_at` | `TEXT` | 1 | - | 0 | 0 |
| `extraction_status` | `TEXT` | 1 | - | 0 | 0 |
| `lifecycle_status` | `TEXT` | 1 | - | 0 | 0 |
| `parser_version` | `TEXT` | 1 | - | 0 | 0 |
| `canonical_bytes` | `BLOB` | 1 | - | 0 | 0 |

```sql
CREATE TABLE sc_snapshots (
    snapshot_id TEXT PRIMARY KEY COLLATE BINARY CHECK (snapshot_id GLOB 'SYN-SNAPSHOT-*'),
    order_id TEXT NOT NULL COLLATE BINARY CHECK (order_id GLOB 'SYN-ORDER-*'),
    captured_at TEXT NOT NULL COLLATE BINARY CHECK (captured_at GLOB '*Z'),
    extraction_status TEXT NOT NULL COLLATE BINARY CHECK (length(extraction_status) BETWEEN 1 AND 32),
    lifecycle_status TEXT NOT NULL COLLATE BINARY CHECK (length(lifecycle_status) BETWEEN 1 AND 32),
    parser_version TEXT NOT NULL COLLATE BINARY CHECK (length(parser_version) BETWEEN 1 AND 128),
    canonical_bytes BLOB NOT NULL CHECK (length(canonical_bytes) BETWEEN 2 AND 1048576)
) STRICT
```

### `structured_domain_failures`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `failure_id` | `TEXT` | 1 | - | 1 | 0 |
| `command_id` | `TEXT` | 0 | - | 0 | 0 |
| `error_code` | `TEXT` | 1 | - | 0 | 0 |
| `error_category` | `TEXT` | 1 | - | 0 | 0 |
| `retryable` | `INTEGER` | 1 | - | 0 | 0 |
| `occurred_at` | `TEXT` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `command_id` | `durable_commands` | `command_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE structured_domain_failures (
    failure_id TEXT PRIMARY KEY COLLATE BINARY
        CHECK (length(failure_id) BETWEEN 1 AND 128),
    command_id TEXT COLLATE BINARY
        REFERENCES durable_commands(command_id) ON DELETE CASCADE,
    error_code TEXT NOT NULL COLLATE BINARY
        CHECK (
            length(error_code) BETWEEN 1 AND 96
            AND error_code NOT GLOB '*[^A-Z0-9_-]*'
        ),
    error_category TEXT NOT NULL COLLATE BINARY
        CHECK (error_category IN ('VALIDATION', 'VERSION', 'PRIVACY', 'CONFLICT', 'COLLISION', 'DATABASE')),
    retryable INTEGER NOT NULL CHECK (retryable IN (0, 1)),
    occurred_at TEXT NOT NULL COLLATE BINARY CHECK (occurred_at GLOB '*Z')
) STRICT
```

### `system_safety_counters`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `counter_name` | `TEXT` | 0 | - | 1 | 0 |
| `counter_value` | `INTEGER` | 1 | `0` | 0 | 0 |

```sql
CREATE TABLE system_safety_counters (
    counter_name TEXT PRIMARY KEY
        CHECK (
            counter_name IN (
                'PRODUCTION_SYSTEM_ACCESS_COUNT',
                'PRODUCTION_MUTATION_REQUEST_COUNT',
                'REAL_CUSTOMER_IDENTITY_COUNT',
                'NON_SYNTHETIC_FIXTURE_COUNT',
                'SECRET_MATERIAL_COUNT',
                'EXTERNAL_PRODUCTION_SYSTEM_ACCESS_COUNT',
                'EXTERNAL_MUTATION_REQUEST_COUNT',
                'NON_LOCALHOST_RUNTIME_REQUEST_COUNT',
                'REAL_CUSTOMER_DATA_COUNT'
            )
        ),
    counter_value INTEGER NOT NULL DEFAULT 0
        CHECK (
            typeof(counter_value) = 'integer'
            AND counter_value >= 0
        )
)
```

### `telemetry_safety_counters`

| Column | Declared type | Not null | Default | PK order | Hidden |
|---|---|---:|---|---:|---:|
| `operation_id` | `TEXT` | 1 | - | 1 | 0 |
| `counter_name` | `TEXT` | 1 | - | 2 | 0 |
| `counter_value` | `INTEGER` | 1 | - | 0 | 0 |

Foreign keys:

| From | Target | To | On update | On delete |
|---|---|---|---|---|
| `operation_id` | `processing_telemetry` | `operation_id` | `NO ACTION` | `CASCADE` |

```sql
CREATE TABLE telemetry_safety_counters (
    operation_id TEXT NOT NULL COLLATE BINARY
        REFERENCES processing_telemetry(operation_id) ON DELETE CASCADE,
    counter_name TEXT NOT NULL COLLATE BINARY
        CHECK (
            counter_name IN (
                'PRODUCTION_SYSTEM_ACCESS_COUNT',
                'PRODUCTION_MUTATION_REQUEST_COUNT',
                'REAL_CUSTOMER_IDENTITY_COUNT',
                'NON_SYNTHETIC_FIXTURE_COUNT',
                'SECRET_MATERIAL_COUNT',
                'EXTERNAL_PRODUCTION_SYSTEM_ACCESS_COUNT',
                'EXTERNAL_MUTATION_REQUEST_COUNT',
                'NON_LOCALHOST_RUNTIME_REQUEST_COUNT',
                'REAL_CUSTOMER_DATA_COUNT'
            )
        ),
    counter_value INTEGER NOT NULL CHECK (counter_value >= 0),
    PRIMARY KEY (operation_id, counter_name)
) STRICT
```

## Indexes

### `doi_attempt_run_index` on `doi_source_import_attempts`

```sql
CREATE INDEX doi_attempt_run_index ON doi_source_import_attempts(run_id, ordinal)
```

### `doi_case_order_index` on `doi_cases`

```sql
CREATE INDEX doi_case_order_index ON doi_cases(order_id)
```

### `doi_evaluation_case_index` on `doi_evaluations`

```sql
CREATE INDEX doi_evaluation_case_index ON doi_evaluations(case_id, evaluation_id)
```

### `doi_one_active_retention_deadline` on `doi_retention_deadlines`

```sql
CREATE UNIQUE INDEX doi_one_active_retention_deadline
    ON doi_retention_deadlines(case_id)
    WHERE canceled_by_reopen_event_id IS NULL
```

### `doi_owner_event_head_index` on `doi_owner_events`

```sql
CREATE INDEX doi_owner_event_head_index ON doi_owner_events(stream_family, stream_id, sequence_no)
```

### `doi_retention_due_index` on `doi_retention_deadlines`

```sql
CREATE INDEX doi_retention_due_index ON doi_retention_deadlines(purge_eligible_at) WHERE canceled_by_reopen_event_id IS NULL
```

### `doi_run_status_index` on `doi_run_projections`

```sql
CREATE INDEX doi_run_status_index ON doi_run_projections(status, completed_at)
```

### `doi_snapshot_case_index` on `doi_order_snapshots`

```sql
CREATE INDEX doi_snapshot_case_index ON doi_order_snapshots(case_id, source_observed_at)
```

### `durable_receipt_owners_owner_idx` on `durable_receipt_owners`

```sql
CREATE INDEX durable_receipt_owners_owner_idx
    ON durable_receipt_owners(owner_domain, owner_id)
```

### `processing_telemetry_rule_result_idx` on `processing_telemetry`

```sql
CREATE INDEX processing_telemetry_rule_result_idx
    ON processing_telemetry(rule_pack, result_class, ended_at)
```

### `sc_active_replacement_links_parent_idx` on `sc_active_replacement_links`

```sql
CREATE INDEX sc_active_replacement_links_parent_idx
    ON sc_active_replacement_links(parent_order_id, candidate_order_id)
```

### `sc_case_events_order_idx` on `sc_case_events`

```sql
CREATE INDEX sc_case_events_order_idx ON sc_case_events(order_id, sequence)
```

### `sc_case_interactions_interaction_idx` on `sc_case_interactions`

```sql
CREATE INDEX sc_case_interactions_interaction_idx ON sc_case_interactions(interaction_id)
```

### `sc_case_search_runs_run_idx` on `sc_case_search_runs`

```sql
CREATE INDEX sc_case_search_runs_run_idx ON sc_case_search_runs(run_id)
```

### `sc_cases_workflow_idx` on `sc_cases`

```sql
CREATE INDEX sc_cases_workflow_idx ON sc_cases(workflow_state, updated_at)
```

### `sc_closed_audits_purge_idx` on `sc_closed_audits`

```sql
CREATE INDEX sc_closed_audits_purge_idx ON sc_closed_audits(purge_eligible_at)
```

### `sc_evaluations_order_idx` on `sc_evaluations`

```sql
CREATE INDEX sc_evaluations_order_idx ON sc_evaluations(order_id, evaluation_id)
```

### `sc_no_order_audits_purge_idx` on `sc_no_order_closed_audits`

```sql
CREATE INDEX sc_no_order_audits_purge_idx ON sc_no_order_closed_audits(purge_eligible_at)
```

### `sc_replacement_candidates_parent_idx` on `sc_replacement_candidates`

```sql
CREATE INDEX sc_replacement_candidates_parent_idx
    ON sc_replacement_candidates(parent_order_id, candidate_order_id)
```

### `sc_snapshots_order_idx` on `sc_snapshots`

```sql
CREATE INDEX sc_snapshots_order_idx ON sc_snapshots(order_id, captured_at)
```

## Triggers

### `backup_receipts_immutable_completed_update` on `backup_receipts`

```sql
CREATE TRIGGER backup_receipts_immutable_completed_update
BEFORE UPDATE ON backup_receipts
WHEN OLD.status != 'STARTED' OR NEW.status NOT IN ('COMPLETED', 'FAILED')
BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_BACKUP_RECEIPT');
END
```

### `doi_attempt_event_sequence_guard` on `doi_source_import_attempt_events`

```sql
CREATE TRIGGER doi_attempt_event_sequence_guard
BEFORE INSERT ON doi_source_import_attempt_events
BEGIN
    SELECT CASE WHEN NEW.sequence_no != COALESCE((SELECT MAX(sequence_no) + 1 FROM doi_source_import_attempt_events WHERE attempt_id = NEW.attempt_id), 1)
        THEN RAISE(ABORT, 'DOI_ATTEMPT_EVENT_SEQUENCE_CONFLICT') END;
    SELECT CASE WHEN NEW.sequence_no = 1 AND NEW.predecessor_sha256 IS NOT NULL
        THEN RAISE(ABORT, 'DOI_ATTEMPT_EVENT_PREDECESSOR_CONFLICT') END;
    SELECT CASE WHEN NEW.sequence_no > 1 AND NEW.predecessor_sha256 IS NOT (SELECT record_sha256 FROM doi_source_import_attempt_events WHERE attempt_id = NEW.attempt_id AND sequence_no = NEW.sequence_no - 1)
        THEN RAISE(ABORT, 'DOI_ATTEMPT_EVENT_PREDECESSOR_CONFLICT') END;
END
```

### `doi_immutable_action_event` on `doi_action_verification_events`

```sql
CREATE TRIGGER doi_immutable_action_event BEFORE UPDATE ON doi_action_verification_events BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_attempt_batch_reference` on `doi_attempt_batch_references`

```sql
CREATE TRIGGER doi_immutable_attempt_batch_reference BEFORE UPDATE ON doi_attempt_batch_references BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_attempt_event` on `doi_source_import_attempt_events`

```sql
CREATE TRIGGER doi_immutable_attempt_event BEFORE UPDATE ON doi_source_import_attempt_events BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_case` on `doi_cases`

```sql
CREATE TRIGGER doi_immutable_case BEFORE UPDATE ON doi_cases BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_case_artifact` on `doi_case_artifacts`

```sql
CREATE TRIGGER doi_immutable_case_artifact BEFORE UPDATE ON doi_case_artifacts BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_case_source_reference` on `doi_case_source_batch_references`

```sql
CREATE TRIGGER doi_immutable_case_source_reference BEFORE UPDATE ON doi_case_source_batch_references BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_disposition` on `doi_run_work_dispositions`

```sql
CREATE TRIGGER doi_immutable_disposition BEFORE UPDATE ON doi_run_work_dispositions BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_evaluation` on `doi_evaluations`

```sql
CREATE TRIGGER doi_immutable_evaluation BEFORE UPDATE ON doi_evaluations BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_evaluation_reason` on `doi_evaluation_reasons`

```sql
CREATE TRIGGER doi_immutable_evaluation_reason BEFORE UPDATE ON doi_evaluation_reasons BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_extraction_attempt` on `doi_extraction_attempts`

```sql
CREATE TRIGGER doi_immutable_extraction_attempt BEFORE UPDATE ON doi_extraction_attempts BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_kpi_event` on `doi_kpi_contribution_events`

```sql
CREATE TRIGGER doi_immutable_kpi_event BEFORE UPDATE ON doi_kpi_contribution_events BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_line_proof_reference` on `doi_line_continuity_proof_references`

```sql
CREATE TRIGGER doi_immutable_line_proof_reference BEFORE UPDATE ON doi_line_continuity_proof_references BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_line_snapshot` on `doi_line_snapshots`

```sql
CREATE TRIGGER doi_immutable_line_snapshot BEFORE UPDATE ON doi_line_snapshots BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_link_mapping` on `doi_resulting_order_mapping_components`

```sql
CREATE TRIGGER doi_immutable_link_mapping BEFORE UPDATE ON doi_resulting_order_mapping_components BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_link_revision` on `doi_resulting_order_link_revisions`

```sql
CREATE TRIGGER doi_immutable_link_revision BEFORE UPDATE ON doi_resulting_order_link_revisions BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_opportunity` on `doi_opportunities`

```sql
CREATE TRIGGER doi_immutable_opportunity BEFORE UPDATE ON doi_opportunities BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_opportunity_scope` on `doi_opportunity_scope_components`

```sql
CREATE TRIGGER doi_immutable_opportunity_scope BEFORE UPDATE ON doi_opportunity_scope_components BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_owner_event` on `doi_owner_events`

```sql
CREATE TRIGGER doi_immutable_owner_event BEFORE UPDATE ON doi_owner_events BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_owner_stream_anchor` on `doi_owner_stream_anchors`

```sql
CREATE TRIGGER doi_immutable_owner_stream_anchor BEFORE UPDATE ON doi_owner_stream_anchors BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_product_observation` on `doi_product_observations`

```sql
CREATE TRIGGER doi_immutable_product_observation BEFORE UPDATE ON doi_product_observations BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_rejected_source_material` on `doi_rejected_source_records`

```sql
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
END
```

### `doi_immutable_relationship_revision` on `doi_product_relationship_revisions`

```sql
CREATE TRIGGER doi_immutable_relationship_revision BEFORE UPDATE ON doi_product_relationship_revisions BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_run` on `doi_runs`

```sql
CREATE TRIGGER doi_immutable_run BEFORE UPDATE ON doi_runs BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_run_control_receipt` on `doi_run_control_receipts`

```sql
CREATE TRIGGER doi_immutable_run_control_receipt BEFORE UPDATE ON doi_run_control_receipts BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_run_event` on `doi_run_events`

```sql
CREATE TRIGGER doi_immutable_run_event BEFORE UPDATE ON doi_run_events BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_run_material_event` on `doi_run_material_events`

```sql
CREATE TRIGGER doi_immutable_run_material_event BEFORE UPDATE ON doi_run_material_events BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_search_event` on `doi_resulting_order_search_events`

```sql
CREATE TRIGGER doi_immutable_search_event BEFORE UPDATE ON doi_resulting_order_search_events BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_snapshot` on `doi_order_snapshots`

```sql
CREATE TRIGGER doi_immutable_snapshot BEFORE UPDATE ON doi_order_snapshots BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_snapshot_proof_reference` on `doi_snapshot_completeness_proof_references`

```sql
CREATE TRIGGER doi_immutable_snapshot_proof_reference BEFORE UPDATE ON doi_snapshot_completeness_proof_references BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_source_batch` on `doi_source_batches`

```sql
CREATE TRIGGER doi_immutable_source_batch BEFORE UPDATE ON doi_source_batches BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_staged_order` on `doi_staged_orders`

```sql
CREATE TRIGGER doi_immutable_staged_order BEFORE UPDATE ON doi_staged_orders BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_staged_order_source_ref` on `doi_staged_order_source_refs`

```sql
CREATE TRIGGER doi_immutable_staged_order_source_ref BEFORE UPDATE ON doi_staged_order_source_refs BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_value_event` on `doi_value_events`

```sql
CREATE TRIGGER doi_immutable_value_event BEFORE UPDATE ON doi_value_events BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_immutable_work_item` on `doi_run_work_items`

```sql
CREATE TRIGGER doi_immutable_work_item BEFORE UPDATE ON doi_run_work_items BEGIN SELECT RAISE(ABORT, 'DOI_IMMUTABLE_RECORD'); END
```

### `doi_owner_event_sequence_guard` on `doi_owner_events`

```sql
CREATE TRIGGER doi_owner_event_sequence_guard
BEFORE INSERT ON doi_owner_events
BEGIN
    SELECT CASE WHEN NEW.sequence_no != COALESCE((SELECT MAX(sequence_no) + 1 FROM doi_owner_events WHERE stream_family = NEW.stream_family AND stream_id = NEW.stream_id), 1)
        THEN RAISE(ABORT, 'DOI_OWNER_EVENT_SEQUENCE_CONFLICT') END;
    SELECT CASE WHEN NEW.sequence_no = 1 AND NEW.predecessor_sha256 IS NOT NULL
        THEN RAISE(ABORT, 'DOI_OWNER_EVENT_PREDECESSOR_CONFLICT') END;
    SELECT CASE WHEN NEW.sequence_no > 1 AND NEW.predecessor_sha256 IS NOT (SELECT record_sha256 FROM doi_owner_events WHERE stream_family = NEW.stream_family AND stream_id = NEW.stream_id AND sequence_no = NEW.sequence_no - 1)
        THEN RAISE(ABORT, 'DOI_OWNER_EVENT_PREDECESSOR_CONFLICT') END;
END
```

### `doi_run_event_sequence_guard` on `doi_run_events`

```sql
CREATE TRIGGER doi_run_event_sequence_guard
BEFORE INSERT ON doi_run_events
BEGIN
    SELECT CASE WHEN NEW.sequence_no != COALESCE((SELECT MAX(sequence_no) + 1 FROM doi_run_events WHERE run_id = NEW.run_id), 1)
        THEN RAISE(ABORT, 'DOI_RUN_EVENT_SEQUENCE_CONFLICT') END;
    SELECT CASE WHEN NEW.sequence_no = 1 AND NEW.predecessor_sha256 IS NOT NULL
        THEN RAISE(ABORT, 'DOI_RUN_EVENT_PREDECESSOR_CONFLICT') END;
    SELECT CASE WHEN NEW.sequence_no > 1 AND NEW.predecessor_sha256 IS NOT (SELECT record_sha256 FROM doi_run_events WHERE run_id = NEW.run_id AND sequence_no = NEW.sequence_no - 1)
        THEN RAISE(ABORT, 'DOI_RUN_EVENT_PREDECESSOR_CONFLICT') END;
END
```

### `doi_value_event_sequence_guard` on `doi_value_events`

```sql
CREATE TRIGGER doi_value_event_sequence_guard
BEFORE INSERT ON doi_value_events
BEGIN
    SELECT CASE WHEN NEW.sequence_no != COALESCE((SELECT MAX(sequence_no) + 1 FROM doi_value_events WHERE intervention_id = NEW.intervention_id), 1)
        THEN RAISE(ABORT, 'DOI_VALUE_EVENT_SEQUENCE_CONFLICT') END;
    SELECT CASE WHEN NEW.sequence_no = 1 AND NEW.predecessor_sha256 IS NOT NULL
        THEN RAISE(ABORT, 'DOI_VALUE_EVENT_PREDECESSOR_CONFLICT') END;
    SELECT CASE WHEN NEW.sequence_no > 1 AND NEW.predecessor_sha256 IS NOT (SELECT record_sha256 FROM doi_value_events WHERE intervention_id = NEW.intervention_id AND sequence_no = NEW.sequence_no - 1)
        THEN RAISE(ABORT, 'DOI_VALUE_EVENT_PREDECESSOR_CONFLICT') END;
END
```

### `durable_command_receipts_immutable_update` on `durable_command_receipts`

```sql
CREATE TRIGGER durable_command_receipts_immutable_update
BEFORE UPDATE ON durable_command_receipts
BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_DURABLE_COMMAND_RECEIPT');
END
```

### `durable_commands_immutable_update` on `durable_commands`

```sql
CREATE TRIGGER durable_commands_immutable_update
BEFORE UPDATE ON durable_commands
BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_DURABLE_COMMAND');
END
```

### `durable_receipt_owners_immutable_update` on `durable_receipt_owners`

```sql
CREATE TRIGGER durable_receipt_owners_immutable_update
BEFORE UPDATE ON durable_receipt_owners
BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_DURABLE_RECEIPT_OWNER');
END
```

### `processing_telemetry_immutable_update` on `processing_telemetry`

```sql
CREATE TRIGGER processing_telemetry_immutable_update
BEFORE UPDATE ON processing_telemetry
BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_PROCESSING_TELEMETRY');
END
```

### `restore_receipts_immutable_completed_update` on `restore_receipts`

```sql
CREATE TRIGGER restore_receipts_immutable_completed_update
BEFORE UPDATE ON restore_receipts
WHEN OLD.status != 'STARTED' OR NEW.status NOT IN ('COMPLETED', 'FAILED')
BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_RESTORE_RECEIPT');
END
```

### `sc_case_events_immutable_update` on `sc_case_events`

```sql
CREATE TRIGGER sc_case_events_immutable_update BEFORE UPDATE ON sc_case_events BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_CASE_EVENT'); END
```

### `sc_cases_version_guard` on `sc_cases`

```sql
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
END
```

### `sc_closed_audits_immutable_update` on `sc_closed_audits`

```sql
CREATE TRIGGER sc_closed_audits_immutable_update BEFORE UPDATE ON sc_closed_audits BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_CLOSED_AUDIT'); END
```

### `sc_evaluation_reasons_immutable_update` on `sc_evaluation_reasons`

```sql
CREATE TRIGGER sc_evaluation_reasons_immutable_update BEFORE UPDATE ON sc_evaluation_reasons BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_EVALUATION_REASON'); END
```

### `sc_evaluations_immutable_update` on `sc_evaluations`

```sql
CREATE TRIGGER sc_evaluations_immutable_update BEFORE UPDATE ON sc_evaluations BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_EVALUATION'); END
```

### `sc_evidence_events_immutable_update` on `sc_evidence_events`

```sql
CREATE TRIGGER sc_evidence_events_immutable_update BEFORE UPDATE ON sc_evidence_events BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_EVIDENCE'); END
```

### `sc_interactions_immutable_update` on `sc_interactions`

```sql
CREATE TRIGGER sc_interactions_immutable_update BEFORE UPDATE ON sc_interactions BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_INTERACTION'); END
```

### `sc_manager_outcomes_immutable_update` on `sc_manager_outcomes`

```sql
CREATE TRIGGER sc_manager_outcomes_immutable_update BEFORE UPDATE ON sc_manager_outcomes BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_MANAGER_OUTCOME'); END
```

### `sc_no_order_closed_audits_immutable_update` on `sc_no_order_closed_audits`

```sql
CREATE TRIGGER sc_no_order_closed_audits_immutable_update BEFORE UPDATE ON sc_no_order_closed_audits BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_NO_ORDER_AUDIT'); END
```

### `sc_replacement_candidates_immutable_update` on `sc_replacement_candidates`

```sql
CREATE TRIGGER sc_replacement_candidates_immutable_update BEFORE UPDATE ON sc_replacement_candidates BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_REPLACEMENT_CANDIDATE'); END
```

### `sc_search_identifiers_immutable_update` on `sc_search_identifiers`

```sql
CREATE TRIGGER sc_search_identifiers_immutable_update BEFORE UPDATE ON sc_search_identifiers BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_SEARCH_IDENTIFIER'); END
```

### `sc_search_result_orders_immutable_update` on `sc_search_result_orders`

```sql
CREATE TRIGGER sc_search_result_orders_immutable_update BEFORE UPDATE ON sc_search_result_orders BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_SEARCH_RESULT'); END
```

### `sc_search_runs_immutable_update` on `sc_search_runs`

```sql
CREATE TRIGGER sc_search_runs_immutable_update BEFORE UPDATE ON sc_search_runs BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_SEARCH_RUN'); END
```

### `sc_snapshot_lines_immutable_update` on `sc_snapshot_lines`

```sql
CREATE TRIGGER sc_snapshot_lines_immutable_update BEFORE UPDATE ON sc_snapshot_lines BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_LINE'); END
```

### `sc_snapshots_immutable_update` on `sc_snapshots`

```sql
CREATE TRIGGER sc_snapshots_immutable_update BEFORE UPDATE ON sc_snapshots BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_SC_SNAPSHOT'); END
```

### `structured_domain_failures_immutable_update` on `structured_domain_failures`

```sql
CREATE TRIGGER structured_domain_failures_immutable_update
BEFORE UPDATE ON structured_domain_failures
BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_STRUCTURED_DOMAIN_FAILURE');
END
```

### `telemetry_safety_counters_immutable_update` on `telemetry_safety_counters`

```sql
CREATE TRIGGER telemetry_safety_counters_immutable_update
BEFORE UPDATE ON telemetry_safety_counters
BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_TELEMETRY_SAFETY_COUNTER');
END
```

## Views

None.
