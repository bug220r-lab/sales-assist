# DOI intake: isolated companion and review handoff

Decision date: 2026-09-23. Status: proposed for pull-request review.
Base branch: `finish/synthetic-v0.1`.
Base commit: `dcf47074ce73b2886d8036423231e8612d2216b5`.
The Windows Preview 2 branch was inspected but is not the merge base.

## Decision and compatibility

Add the user's supplied DOI Intake v1 under `companions/doi_intake`, with an
explicit root launcher and review-only output validator. Preserve the original
script bytes and its tests; no existing application file is changed.

This introduces an optional Google-reading companion to a repository whose core
application is synthetic-only. Review that isolated profile explicitly before
merging. It does not alter protected `specs/`, `reference/`, checksummed bundle
files, synthetic identities, database schemas, Chrome permissions or runtime
networking. No dependency on this companion is added to the synthetic application.
No production read is performed as part of implementation or testing.

The repository launcher requires `--enable-google` for live commands and separate
read-only authorization. Credentials, history and generated records remain outside
the checkout. These are supported-entry-point controls, not a sandbox against
running arbitrary code or the original script directly.

The handoff returns only reviewed pending candidates plus separate held IDs.
It checks schema, scope, source freshness, uniqueness, source occurrences,
reconciliation, history, sorting, fingerprints and output-file consistency.
It never authorizes execution or inserts companion IDs into the synthetic database.
The four-hour capture-age default is a new integration guard, not an asserted DOI
business rule. Matching reads and checksums are not source-authenticity proof.

## Verification and remaining gates

Scoped local tests: 114 pass (76 preserved intake tests plus 38 integration tests).
Coverage includes module subprocess demo/verify, source/owner conflicts, stale
captures, duplicates and inconsistent bundles even after hashes are recomputed.
Only fictional fixtures and mocked Google responses are used.

The build container could not resolve github.com for a full Git clone. Repository
code was inspected through the authorized connector. Full-core local regression,
Windows execution, real OAuth and live workbook access were not exercised.
Do not report scoped tests as full application acceptance.

The added workflow runs the companion tests on Linux/Windows and separately runs
the existing core quality gate and test runner. Remote outcomes must be read from
GitHub, not inferred from local tests. Keep the pull request draft until the scope
review and required regression gates are resolved; do not weaken core safeguards
to force a pass.

No UI button, automatic read loop, Order Admin adapter, customer action, release or
installed-workstation update is included. Existing startup and backup behavior is
unchanged; app backups do not include the external companion data directory.

## Rollback

Revert only the added companion, launcher, documentation and workflow files.
Original application and database schemas are unchanged. A source revert must not
delete externally generated business records; retain them under company policy.
