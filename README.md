
# Synthetic Sales Assist Specification Bundle v1.0.1

This folder is a curated, synthetic-only specification package for a fresh Codex
implementation of the Sales Credit and DOI rule packs.

## What this bundle contains

- binding project, safety, data, rule, lifecycle, retention, and telemetry specifications;
- a 138-row DOI reason registry;
- a 138-row reason-ownership registry;
- a 115-row transition registry;
- Sales Credit workflow states and deterministic rules;
- approved product decisions;
- mandatory implementation findings from the prior independent audits;
- sanitized, source-derived reference documents for detailed traceability.

## What this bundle does not contain

- source code or prior Git history;
- customer or employee records;
- real orders or products;
- historical corpora;
- screenshots or HTML captured from a real system;
- production URLs, selectors, credentials, cookies, tokens, or sessions;
- permission to access a production system.

## How to use it

1. Create a new empty folder for the new Codex project.
2. Copy the contents of this bundle into that folder.
3. Open the folder in a brand-new Codex chat.
4. Paste the synthetic rewrite launch prompt.
5. Tell Codex to read `AGENTS.md` and `specs/SPEC_INDEX.md`.
6. Begin with Milestone 0 only.
7. Keep `reference/` read-only and treat it as supporting context, not code.

## Authority rule

The curated files under `specs/` govern. The sanitized documents under `reference/`
preserve detail but may contain historical candidate/freeze language or superseded
engineering assumptions. They cannot override the authority order in `SPEC_INDEX.md`.

## Limitation

This package proves technical feasibility against synthetic data. It does not establish
validation or readiness for any real organization, customer workflow, or production system.


## v1.0.1 correction

This version supersedes the initial bundle before any repository initialization.

It reconciles:

- explicit no-retry finalization versus absence-of-retry wording;
- RC-084 transition ownership and TR-004 legality;
- stale sanitized-reference hashes in `specs/SOURCE_PROVENANCE.json`.

Binding counts remain 138 reasons, 138 ownership records, and 115 transitions.
