# Milestone 0 development

This repository currently contains only the synthetic-only safety and repository foundation.
Sales Credit and DOI rule engines, a portal, a dashboard, and a Chrome extension are deliberately
absent until a later milestone is explicitly authorized.

## Requirements

- Python 3.12 or newer
- Git
- no network service, production connector, credential, or external data source

The executable foundation has no runtime package dependencies. Optional development tools are
declared in `pyproject.toml`; the commit gate itself runs on the Python standard library so it can
execute offline.

## Offline verification

From the repository root:

```text
python tools/quality_gate.py
python tools/run_tests.py
python tools/run_foundation_audit.py
```

The final command verifies the immutable supplied bundle, repository safety scans, identity
firewall, loopback policy, future Chrome permission policy, and zero safety counters. It performs
no network operation.

## Milestone boundary

Milestone 0 supplies only:

- package and test structure;
- synthetic identity and prohibited-input controls;
- secret and repository scanners;
- loopback and Chrome permission policy validators;
- structured JSON logging primitives;
- a versioned SQLite migration framework.

It contains no workflow classification, reason emission, transition execution, business-rule
evaluation, UI, browser extension, or portal integration.
