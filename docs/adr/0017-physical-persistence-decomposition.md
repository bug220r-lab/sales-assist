# ADR 0017: Physical persistence decomposition

- Status: accepted for Milestone 4
- Scope: physical SQLite ownership for existing shared, Sales Credit, and DOI models

## Decision

Retain `0001_foundation.sql` unchanged and add one migration each for shared persistence, Sales
Credit persistence, and DOI persistence. The domains have separate case, run, event, projection,
and retention roots and no cross-domain foreign key. Shared command, receipt, telemetry, migration,
backup, and restore infrastructure remains neutral.

Immutable domain material is stored with its owner rather than globally deduplicated. Hash-bearing
rows retain the exact versioned domain, lowercase SHA-256 digest, and complete canonical bytes
needed for collision comparison. IDs and enums use binary-collated text; timestamps use canonical
UTC text; exact money and quantity representations never use SQLite `REAL`.

Sales Credit persists interactions, complete search provenance, immutable snapshots and evidence,
case associations, evaluation history, manager outcomes, and minimized closure records. DOI
persists the complete source/run, extraction, evaluation/opportunity, product, coordination,
intervention/value, KPI, and retention histories. Join rows make graph ownership explicit and
permit cascade deletion only from a governed root.

## Consequences

Physical tables do not redefine logical business entities or results. Owner-local material avoids
orphaned identity-bearing hashes after purge. Product-only DOI knowledge remains separate from
case and order ownership. Schema inventory and migration checksums are generated from the actual
database and migration bytes rather than maintained as an independent assertion.
