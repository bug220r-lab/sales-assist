# Milestone 3 development

This repository contains the synthetic-only foundation, immutable Shared Domain Engine, pure
Milestone 2 Sales Credit rule pack, and pure deterministic Milestone 3 DOI rule pack. Business
persistence, source connectors, a portal, an API, a dashboard, and a Chrome extension remain
absent. Milestone 4 has not begun.

## Requirements

- Python 3.12 or newer
- Git
- no network service, production connector, credential, or external data source

The executable foundation has no runtime package dependencies. Optional development tools are
declared in `pyproject.toml`; the commit gate itself runs on the Python standard library so it can
execute offline.

Through Milestone 3, execution is intentionally bound to a complete verified source checkout:
the foundation audit, migration framework, and closed DOI registries read immutable root-level
bundle files. Wheel and source-distribution deployment are not claimed by this local PoC milestone.

## Offline verification

From the complete verified repository root:

```text
python tools/quality_gate.py
python -m compileall -q src tests tools
python -m unittest discover -s tests -t . -p "test_doi_*.py"
python tools/run_tests.py
python tools/run_foundation_audit.py
```

The final command verifies the immutable supplied bundle, repository safety scans, identity
firewall, loopback policy, future Chrome permission policy, and zero safety counters. It performs
no network operation.

## Milestone boundary

Milestone 3 adds only immutable DOI records, deterministic source/extraction/evaluation rules,
registry-backed pure lifecycle reduction, process-local replay/concurrency coordination, pure
intervention/value/KPI histories, and synthetic executable scenarios. It adds no business SQLite
table, durable repository, source adapter, portal, API, browser artifact, scheduler, worker,
external request, customer communication, or business mutation.

The closed Milestone 3 surface includes:

- exact review/recheck run machines, source-import retries, explicit no-retry finalization, count
  conservation, and extraction-reservation versus RC-084 serialization;
- whole-order extraction with source-time coherence, complete manifests, stable/composite line
  continuity, and missing-versus-observed-UNKNOWN separation;
- the approved opportunity-preservation policy, including field-specific UNKNOWN containment,
  independently preserved opportunities, and TR-037 only when no safe conclusion survives;
- full DS, mixed DS, split, partial quantity, payment, progress, source-absence, geography, ETA,
  hard-closure, and reversible-closure decisions;
- exact SKU plus four distinct alternate-product relationship types, immutable product-only
  revision/observation evidence, and closed compatibility decisions;
- structured contact, all 64 legal WWC PRESENT partitions, DEDUPE candidate/decision/later-source
  verification, cause-keyed attention, and hash-bound human provenance;
- exact opportunity scope and value, hash-bound mutually exclusive scenario evidence, unresolved
  overlap without double counting, and explicit human scenario selection;
- verified intervention occurrence, exact result-link scope, append-only value corrections and
  reversals, exactly-once currency-segmented KPI contributions, and identity-free purge transfer;
- all 115 supplied transitions with one collected typed-owner legal test and one collected
  production invalid-from-state test, plus structural false-guard coverage, exact registered
  effects, replay/collision/predecessor checks, and first-event admission;
- all 138 supplied reasons and 138 ownership rows with the approved implementation-side overlay,
  independently collected owning-behavior selectors, and zero legal-route leakage; and
- deterministic generated scenario, reason, transition, and 94-domain hash-preimage artifacts with nine
  zero safety counters per scenario.

The central DOI hash-domain fixtures and exact preimages are published in
`docs/milestone3-hash-preimages.md`. Reason ownership, transition coverage, and scenario inventory
are published in the corresponding `docs/milestone3-*` generated artifacts; executable tests
reject any byte drift.

The supplied root `README.md` is part of the checksummed specification bundle and remains
byte-for-byte unchanged. Milestone-specific implementation and verification documentation lives
under `docs/` and in this development guide.

## Milestone 1 foundation

Milestone 1 adds only:

- typed synthetic identifiers and canonical timestamp, money, quantity, count, and ordinal
  values;
- deterministic canonical JSON and domain-separated SHA-256 bindings;
- source normalization and closed observation values;
- read-only reason, ownership, and transition registries;
- typed source/evidence references, neutral run/snapshot/evaluation/event envelopes, and an
  in-memory idempotency receipt store;
- a closed whole-order completeness proof value with exact order/source identity, five required
  sections, source-time coherence, exhaustion flags, count/manifest parity, version bindings, and
  minimized source-reference resolution;
- enumerable, role-separated evaluation explanation items for supplied facts, evaluated/fired
  rules, result, and persistence effects.

The public Milestone 1 ownership view intentionally excludes planning oracle IDs, statuses, and
selectors. Executable selector reconciliation remains binding for the later DOI behavior milestone.
The completeness and explanation records validate shared structure only; they do not extract a
source, execute a rule, emit a reason, apply a transition, or authorize business persistence.

The exact neutral-envelope fixture preimages and known-answer digests are published in
`docs/milestone1-hash-preimages.md` and pinned by executable tests.

The Milestone 0 safety, logging, audit, and migration controls remain active. Together the two
milestones supply:

- package and test structure;
- synthetic identity and prohibited-input controls;
- secret and repository scanners;
- loopback and Chrome permission policy validators;
- structured JSON logging primitives;
- a versioned SQLite migration framework.

Before Milestone 2, those foundations contain no workflow classification, reason emission,
transition execution, business-rule evaluation, business table, UI, browser extension, or portal
integration. Milestone 2 adds only the Sales Credit classifications and reason emissions described
above; DOI transitions and business behavior remain absent.
