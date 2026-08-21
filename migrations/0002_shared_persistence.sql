-- Milestone 4 shared durable command, telemetry, and maintenance foundation.
CREATE TABLE application_metadata (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    application_id TEXT NOT NULL COLLATE BINARY
        CHECK (application_id = 'synthetic-sales-assist'),
    application_version TEXT NOT NULL COLLATE BINARY,
    database_format TEXT NOT NULL COLLATE BINARY
        CHECK (database_format = 'synthetic-sales-assist-sqlite/v1'),
    latest_schema_version INTEGER NOT NULL CHECK (latest_schema_version >= 2)
) STRICT;

INSERT INTO application_metadata (
    singleton,
    application_id,
    application_version,
    database_format,
    latest_schema_version
) VALUES (
    1,
    'synthetic-sales-assist',
    '0.1.0',
    'synthetic-sales-assist-sqlite/v1',
    2
);

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
) STRICT;

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
) STRICT;

CREATE TABLE durable_receipt_owners (
    command_id TEXT NOT NULL COLLATE BINARY
        REFERENCES durable_command_receipts(command_id) ON DELETE CASCADE,
    owner_domain TEXT NOT NULL COLLATE BINARY
        CHECK (owner_domain IN ('SALES_CREDIT', 'DOI', 'SYSTEM')),
    owner_id TEXT NOT NULL COLLATE BINARY
        CHECK (length(owner_id) BETWEEN 1 AND 128),
    PRIMARY KEY (command_id, owner_domain, owner_id)
) STRICT;

CREATE INDEX durable_receipt_owners_owner_idx
    ON durable_receipt_owners(owner_domain, owner_id);

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
) STRICT;

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
) STRICT;

CREATE INDEX processing_telemetry_rule_result_idx
    ON processing_telemetry(rule_pack, result_class, ended_at);

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
) STRICT;

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
) STRICT;

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
) STRICT;

CREATE TRIGGER durable_commands_immutable_update
BEFORE UPDATE ON durable_commands
BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_DURABLE_COMMAND');
END;

CREATE TRIGGER durable_command_receipts_immutable_update
BEFORE UPDATE ON durable_command_receipts
BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_DURABLE_COMMAND_RECEIPT');
END;

CREATE TRIGGER durable_receipt_owners_immutable_update
BEFORE UPDATE ON durable_receipt_owners
BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_DURABLE_RECEIPT_OWNER');
END;

CREATE TRIGGER structured_domain_failures_immutable_update
BEFORE UPDATE ON structured_domain_failures
BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_STRUCTURED_DOMAIN_FAILURE');
END;

CREATE TRIGGER processing_telemetry_immutable_update
BEFORE UPDATE ON processing_telemetry
BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_PROCESSING_TELEMETRY');
END;

CREATE TRIGGER telemetry_safety_counters_immutable_update
BEFORE UPDATE ON telemetry_safety_counters
BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_TELEMETRY_SAFETY_COUNTER');
END;

CREATE TRIGGER backup_receipts_immutable_completed_update
BEFORE UPDATE ON backup_receipts
WHEN OLD.status != 'STARTED' OR NEW.status NOT IN ('COMPLETED', 'FAILED')
BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_BACKUP_RECEIPT');
END;

CREATE TRIGGER restore_receipts_immutable_completed_update
BEFORE UPDATE ON restore_receipts
WHEN OLD.status != 'STARTED' OR NEW.status NOT IN ('COMPLETED', 'FAILED')
BEGIN
    SELECT RAISE(ABORT, 'IMMUTABLE_RESTORE_RECEIPT');
END;
