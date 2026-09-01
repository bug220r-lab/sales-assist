# Milestone 7 development

This repository is a synthetic-only local application. Milestone 7 adds a browser-based local
Control Center over the existing Shared Domain Engine, Sales Credit and DOI rule packs, schema-4
SQLite persistence, Milestone 5 portal/API, and Milestone 6 Chrome extension. Business rules remain
in the committed domain and application services. The Control Center is a local presentation and
closed-command boundary; it is not a production connector or a release package.

All listeners and runtime requests remain loopback-only. There is no production-system access,
external action, remote asset, remote analytics, automatic updater, or non-loopback bind.

## Requirements

- CPython 3.12.x for the Windows lifecycle launcher
- Git
- Chrome 114 or newer for manual unpacked-extension acceptance
- no production credential, connector, or external data source

Runtime code uses only the Python standard library. Optional development tools are declared in
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
  'C:\Users\jlewi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
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
version = 0.1.1
permissions = sidePanel
host_permissions = http://127.0.0.1/*, http://localhost/*
deterministic ZIP SHA-256 = 595044d03c0aa843f7e751167b27b8d16de4cb8cf8fbc7064409f30e88ba885c
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

The exported ZIP is a local development artifact for manual loading. It is not a portable release,
Chrome Web Store submission, installer, or Milestone 8 package.

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

Manual M7 acceptance is a later user-visible gate. The current implementation document must remain
`M7_MANUAL_ACCEPTANCE = PENDING` until the user completes it.

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

Milestone 8 release construction, installer/portable ZIP, store publication, release tag,
independent final audit, benchmark run, screenshot capture, and publication remain absent. The M7
machine-readable evidence endpoint and stable selectors are inputs for a future M8 task; they are
not an M8 implementation or acceptance verdict.
