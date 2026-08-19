-- Milestone 0 neutral safety foundation.  No Sales Credit or DOI entity is stored.
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
);

INSERT INTO system_safety_counters (counter_name, counter_value)
VALUES
    ('PRODUCTION_SYSTEM_ACCESS_COUNT', 0),
    ('PRODUCTION_MUTATION_REQUEST_COUNT', 0),
    ('REAL_CUSTOMER_IDENTITY_COUNT', 0),
    ('NON_SYNTHETIC_FIXTURE_COUNT', 0),
    ('SECRET_MATERIAL_COUNT', 0),
    ('EXTERNAL_PRODUCTION_SYSTEM_ACCESS_COUNT', 0),
    ('EXTERNAL_MUTATION_REQUEST_COUNT', 0),
    ('NON_LOCALHOST_RUNTIME_REQUEST_COUNT', 0),
    ('REAL_CUSTOMER_DATA_COUNT', 0);
