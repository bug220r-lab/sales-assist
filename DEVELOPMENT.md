# Milestone 1 development

This repository contains the synthetic-only foundation plus an immutable Shared Domain Engine.
Sales Credit and DOI rule engines, business persistence, a portal, a dashboard, and a Chrome
extension remain deliberately absent until a later milestone is explicitly authorized.

## Requirements

- Python 3.12 or newer
- Git
- no network service, production connector, credential, or external data source

The executable foundation has no runtime package dependencies. Optional development tools are
declared in `pyproject.toml`; the commit gate itself runs on the Python standard library so it can
execute offline.

Through Milestone 1, execution is intentionally bound to a complete verified source checkout:
the foundation audit, migration framework, and closed DOI registries read immutable root-level
bundle files. Wheel and source-distribution deployment are not claimed by this local PoC milestone.

## Offline verification

From the complete verified repository root:

```text
python tools/quality_gate.py
python tools/run_tests.py
python tools/run_foundation_audit.py
```

The final command verifies the immutable supplied bundle, repository safety scans, identity
firewall, loopback policy, future Chrome permission policy, and zero safety counters. It performs
no network operation.

## Milestone boundary

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

They contain no workflow classification, reason emission, transition execution, business-rule
evaluation, business table, UI, browser extension, or portal integration.
