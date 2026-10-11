# Synthetic demo development and release

The optional [Campaign Replies companion](docs/campaign-replies.md) adds a dedicated
read-only review page for an independently running local dashboard. It is disabled by
default and isolated from the synthetic application services and database. Its bounded
user-requested presentation exception is recorded in [ADR 0033](docs/adr/0033-local-campaign-review-companion.md).

This repository is a synthetic-only local application. Milestone 7 adds a browser-based local
Control Center over the existing Shared Domain Engine, Sales Credit and DOI rule packs, schema-4
SQLite persistence, Milestone 5 portal/API, and Milestone 6 Chrome extension. Business rules remain
in the committed domain and application services. The Control Center is a local presentation and
closed-command boundary. M8 adds deterministic offline demo/source packaging and local
Windows launchers; it adds no production connector.

All listeners remain loopback-only. The owner-authorized
[CSV draft review and Help Scout draft transfer](docs/doi-draft-transfer.md) adds one
off-by-default server adapter, bounded in [ADR 0038](docs/adr/0038-approved-csv-draft-transfer.md).
Each external draft requires review and approval of its exact version. Customer sending is absent.
Private CSVs, databases, credentials and customer records stay outside this repository.
The original specification bundle remains unchanged; this authorized application extension does
not expand the core rules engine or Chrome extension's synthetic/localhost boundaries.
Tests use synthetic fixtures and mocked APIs. Do not restart an active review or change
credentials/grants without action-time approval.

## Requirements

- CPython 3.12.x for the Windows lifecycle launcher
- tzdata 2026.3 installed in that interpreter on Windows (time-zone data, Apache-2.0)
- Git
- Chrome 114 or newer for manual unpacked-extension acceptance
- no production credential, connector, or external data source

Runtime code uses the Python standard library plus Windows time-zone data. Dependencies are
never downloaded by the launcher. Optional development tools are declared in
`pyproject.toml`; verification runs offline. Run commands from the repository root and from a
complete verified checkout because migrations and the closed business registries are
repository-bound artifacts.

For direct Python commands from a checkout that has not been installed:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
```

## Windows lifecycle and Control Center

The launcher prefers a normal local, non-reparse CPython 3.12.x named `python.exe`. In the current
Codex workspace, the verified development fallback is explicit and process-scoped:

```powershell
# DEVELOPMENT / NONPORTABLE -- this workspace only
$env:SSA_PYTHON = `
  'C:\path\to\approved-development-runtime\python.exe'
.\scripts\start.ps1 -NoBrowser
.\scripts\status.ps1
Start-Process 'http://127.0.0.1:8765/overview'
.\scripts\stop.ps1
Remove-Item Env:SSA_PYTHON
```

Leave `SSA_PYTHON` unset when a normal PATH candidate is safe and usable. If PATH validation
fails, `SSA_PYTHON` must name the exact verified Codex runtime. Passing that runtime through
`-PythonPath` does not receive the development-only ancestor-reparse exception. The launcher
prints `DEVELOPMENT / NONPORTABLE` when it selects this fallback. This mechanism does not create
or claim a portable release.

The service origin is exactly `http://127.0.0.1:8765/`. `/` redirects to `/overview`. The stable
Control Center routes are documented in `docs/milestone7-architecture-and-routes.md`; the manager
sequence begins at `/system` and `/overview`. Queue and detail pages use current schema-4
projections, while audit/timeline pages retain immutable history. Restore and reset remain
separate strongly confirmed CLI workflows and are not Control Center actions.

## Unpacked localhost extension

Start the service, then load the repository-owned `chrome_extension` directory from
`chrome://extensions` using **Developer mode** and **Load unpacked**. The current extension
identity is:

```text
manifest_version = 3
version = 0.1.2
permissions = sidePanel
host_permissions = http://127.0.0.1/*, http://localhost/*
deterministic ZIP SHA-256 = 3c0d145c789fb990c9fe849f16a031f397285de020ec14b6bb97551ddf1aca55
```

The patch-version change adds only closed loopback deep links and a version-only, event-bound
last-seen handshake. It adds no Chrome permission, broader host access, polling, business rule,
source mutation, or external request. Package presence alone is not installation evidence; the
Control Center reports one of the five states documented in
`docs/milestone7-extension-status-semantics.md`.

After changing extension bytes, reload the unpacked extension and the portal tab. Check and export
the deterministic package outside the repository:

```powershell
& $env:SSA_PYTHON tools/package_milestone6_extension.py --check
& $env:SSA_PYTHON tools/package_milestone6_extension.py `
  --output-dir (Join-Path $env:LOCALAPPDATA 'SyntheticSalesAssist\exports')
```

The exported ZIP is a local development artifact for loading in a dedicated Chrome profile.
M8 also includes those exact extension bytes in its release. No Chrome Web Store submission,
portable interpreter, or machine installer is provided.

## Local data and database maintenance

By default, owned data is under `%LOCALAPPDATA%\SyntheticSalesAssist\`, outside this repository
and OneDrive. Tests and manual acceptance should use an absolute, local, isolated directory:

```powershell
$dataRoot = Join-Path $env:LOCALAPPDATA 'SyntheticSalesAssist-acceptance'
& $env:SSA_PYTHON -m synthetic_sales_assist.cli --data-dir $dataRoot db init
& $env:SSA_PYTHON -m synthetic_sales_assist.cli --data-dir $dataRoot db verify --deep
```

The database schema remains version `4`; Milestone 7 adds no migration. The path guard rejects
relative paths, traversal, URLs, UNC/network shares, Windows device paths, reparse ancestors, and
paths inside the repository. Ordinary Control Center pages return privacy-safe location classes,
not absolute username-bearing paths.

Backup creation in the Control Center derives a managed local destination server-side and verifies
the receipt. Restore remains a separate CLI operation:

```powershell
& $env:SSA_PYTHON -m synthetic_sales_assist.cli --data-dir $dataRoot db status
& $env:SSA_PYTHON -m synthetic_sales_assist.cli --data-dir $dataRoot db backup `
  (Join-Path $dataRoot 'backups\manual.sqlite3') --create-parent
& $env:SSA_PYTHON -m synthetic_sales_assist.cli --data-dir $dataRoot db restore `
  (Join-Path $dataRoot 'backups\manual.sqlite3') --confirm
```

Do not copy an open SQLite file as a backup. See `docs/milestone4-backup-restore-guide.md` and
`docs/milestone4-data-location-guide.md` for the binding maintenance and path policies.

## Offline verification

Run focused M7 gates before the complete repository suite:

```powershell
& $env:SSA_PYTHON tools/quality_gate.py
& $env:SSA_PYTHON -m compileall -q src tests tools
& $env:SSA_PYTHON tools/run_tests.py `
  tests.test_milestone7_control_center_core `
  tests.test_milestone7_actions `
  tests.test_milestone7_extension `
  tests.test_milestone7_dashboard_rendering `
  tests.test_milestone7_server `
  tests.test_milestone7_documentation
& $env:SSA_PYTHON tools/package_milestone6_extension.py --check
& $env:SSA_PYTHON tools/run_tests.py
& $env:SSA_PYTHON tools/run_foundation_audit.py
```

The final candidate gate must also run the M6 lifecycle/current-byte/package tests, M5 portal/API
tests, M4 persistence/CLI/backup/restore tests, M3 DOI tests, M2 Sales Credit tests, M1 shared-domain
tests, protected-file verification, synthetic-identity/prohibited-input/secret scans,
localhost/no-network checks, Chrome permission audit, and milestone-boundary tests. Use actual
collected counts from that run; do not carry a historical total forward.

Historical manual acceptance remains pending until actually performed by the user. Current
`M7_MANUAL_ACCEPTANCE = PENDING` is preserved as a historical manual gate.
release evidence separately records `AGENT_EXECUTED_ACCEPTANCE`, `HUMAN_MANUAL_ACCEPTANCE`, and
`CLEAN_MACHINE_VALIDATION`; a browser capability gap is never converted into a manual PASS.

## Milestone boundary

Milestone 7 permits the local Control Center, privacy-safe current projection queries, immutable
timeline views, exact metric denominator registry, closed human-action adapters, local database
verify/backup operations, and minimal no-new-permission extension deep links/last-seen semantics.
The pure domain engines remain authoritative. HTTP handlers and rendering do not create a reason,
ownership row, transition, classification, intervention, resulting-order link, or value rule.

Schema remains version 4 with exactly `migrations/0001_foundation.sql` through
`migrations/0004_doi_persistence.sql`. The supplied `specs/`, `reference/`,
`BUNDLE_MANIFEST.json`, `SHA256SUMS.txt`, and checksummed root `README.md` remain byte-for-byte
unchanged.

M8 packaging is implemented by `tools/build_demo_release.py --commit <full-commit-id>
--output-dir <new-external-directory>`. Freeze and fully test a candidate before committing,
then build twice from that immutable commit and test the exact extracted archives. Reports,
hashes, measurements, and reviewer attestations belong outside the source commit. See
`docs/adr/0028-deterministic-demo-release-and-local-ownership.md` and `docs/m8/START_HERE.txt`.
The launchers START/STOP/STATUS/BACKUP/RESET/REMOVE/UPGRADE.cmd need no Python command entry.
Their default demo data is release-specific local application data; original data is untouched.
Release construction does not itself establish acceptance, clean-machine portability, or review.

`tools/measure_demo_release.py` measures exactly 1,000 or 10,000 mixed persistence-service
calls in a fresh isolated data root. Every ten calls comprise six new evaluations, two
replays, one changed-material conflict, and one history query. It retains the 256-order
portal limit and reports actual Windows working set, CPU, growth, verified backup, and
per-operation latency. UI and idle-service measurements are separate external evidence.
