
# Project Instructions

Read `specs/SPEC_INDEX.md` before making any repository change.

## Scope

This repository is a synthetic-only implementation of the supplied Sales Credit and DOI
business specifications.

## Mandatory constraints

- Use only reserved synthetic identities.
- Do not access, reference, or connect to any production or company system.
- Runtime networking is localhost-only.
- Chrome host permissions are limited to `http://127.0.0.1/*` and `http://localhost/*`.
- Do not inspect files outside this repository.
- Do not copy a prior implementation repository or Git history.
- Binding business behavior comes from `specs/`.
- `reference/` contains sanitized source-derived supporting material; it is nonbinding
  unless `specs/SPEC_INDEX.md` explicitly names a file as a conflict-resolution source.
- Internal implementation choices belong to Codex.
- Create ADRs for consequential persistence, concurrency, replay, privacy, migration,
  canonical-hash, and extension-security decisions.
- Every reason/oracle reference must resolve to a real executable test.
- Run scoped and complete available regression tests before milestone commits.
- Stop only for a genuine contradiction that changes a business outcome or protected invariant.

## First execution boundary

Implement Milestone 0 only on the initial run. Do not implement business rules until the
specification inventory, safety controls, synthetic identity firewall, and localhost-only
tests pass.
