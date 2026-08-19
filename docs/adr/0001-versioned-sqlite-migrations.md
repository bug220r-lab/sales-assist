# ADR 0001: Versioned SQLite migration foundation

- Status: accepted for Milestone 0
- Scope: internal persistence and migration mechanics only

## Decision

Use ordered, immutable SQL files with four-digit numeric prefixes. The migration runner enables
SQLite foreign-key enforcement, applies pending files transactionally, and records each filename
and SHA-256 digest in a migration ledger. A previously applied filename with different bytes is a
hard failure. Reapplying an unchanged migration set is a no-op.

The initial migration contains neutral foundation metadata and the binding safety-counter names;
it contains no Sales Credit or DOI workflow tables.

## Consequences

Migration order and drift are deterministic and testable without a network service or third-party
package. SQL transaction-control statements are owned by the runner and are therefore forbidden
inside migration files. Physical business persistence, concurrency, replay, retention, and purge
designs remain deferred to their authorized milestones and will require their own ADRs.
