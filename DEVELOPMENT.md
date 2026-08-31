# Milestone 6 development

This repository contains the synthetic-only safety foundation, immutable Shared Domain Engine,
Sales Credit rule pack, DOI rule pack, and local SQLite persistence and command-line interface.
Milestone 5 adds one standard-library HTTP service, closed local API, generic synthetic portal,
scenario library, and Windows lifecycle scripts. Milestone 6 adds one repository-owned Chrome
Manifest V3 extension with a read-only content extractor and local side panel. The listener and all
runtime requests remain loopback-only. There is no dashboard/control center, production connector,
scheduler, external action, internet client, remote asset, or external telemetry.

## Requirements

- Python 3.12 or newer for repository code; the Windows lifecycle launcher requires CPython 3.12.x
- Git
- Chrome 114 or newer for manual unpacked-extension acceptance
- no production connector, credential, or external data source

Runtime code uses only the Python standard library. Optional development tools are declared in
`pyproject.toml`; the release gates execute offline. Run commands from a complete verified source
checkout because migrations and the closed business registries are repository-bound artifacts.

Set the source path for a checkout that has not been installed:

```powershell
$env:PYTHONPATH = "src"
```

## Windows lifecycle launcher

The launcher prefers a normal local, non-reparse CPython 3.12.x named `python.exe`. On the current
Codex workspace, set this process-scoped fallback before using start, status, stop, or reset:

```powershell
# DEVELOPMENT / NONPORTABLE -- this workspace only
$localAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
$profileRoot = [IO.Directory]::GetParent($localAppData).Parent.FullName
$env:SSA_PYTHON = Join-Path $profileRoot `
  '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
.\scripts\start.ps1 -NoBrowser
.\scripts\status.ps1
.\scripts\stop.ps1
Remove-Item Env:SSA_PYTHON
```

Leave `SSA_PYTHON` unset when the normal PATH candidate is safe and usable. If PATH validation
fails, the fallback must name the exact verified Codex runtime through `SSA_PYTHON`; passing that
runtime through `-PythonPath` does not receive the development-only ancestor-reparse exception.
The launcher prints `DEVELOPMENT / NONPORTABLE` when it selects the fallback. This mechanism is
not a portable release and makes no such claim.

## Unpacked localhost extension

Start the accepted local service on its fixed development origin, then load the repository-owned
unpacked directory:

```powershell
.\scripts\start.ps1 -NoBrowser
Start-Process 'http://127.0.0.1:8765/scenarios'
```

In Chrome, open `chrome://extensions`, enable **Developer mode**, choose **Load unpacked**, and
select the repository's `chrome_extension` directory. Chrome must show extension version `0.1.0`,
only the `sidePanel` API permission, and only these host permissions:

```text
http://127.0.0.1/*
http://localhost/*
```

The static content script is narrower still: only `/orders/*` and `/interactions/*` on those two
hosts. Open a synthetic order detail page, choose **Synthetic Sales Assist Local Side Panel** in
Chrome's side-panel picker, and explicitly click Evaluate only after `SUPPORTED_READY`. Loading,
refreshing, or opening the panel never evaluates automatically. The extension uses no Chrome
storage and has no production, generic browser-automation, or external action capability.

After changing extension files, choose **Reload** on `chrome://extensions`, then reload the portal
tab to replace its static content script. Removal uses Chrome's ordinary **Remove** control and
does not alter the local SQLite database. Complete state, security, network, reload, and uninstall
steps are in `docs/milestone6-manual-acceptance.md`.

Validate the checked-in source inventory, then create a deterministic ZIP, checksum, and exact
file/hash inventory outside the repository:

```powershell
& $env:SSA_PYTHON tools/package_milestone6_extension.py --check
& $env:SSA_PYTHON tools/package_milestone6_extension.py `
  --output-dir (Join-Path $env:LOCALAPPDATA 'SyntheticSalesAssist\exports')
```

The package is a development distribution artifact for local manual loading, not a portable
release and not a store submission. The tool stages and verifies the ZIP, checksum, and inventory
together, then atomically publishes their digest-named generation directory. A failed generation
does not replace a prior complete generation. Do not write package output into the repository.

## Local data

By default the CLI uses `%LOCALAPPDATA%\SyntheticSalesAssist\`, outside both this repository and
OneDrive. Tests and manual acceptance should pass an absolute, local, isolated directory:

```powershell
$dataRoot = Join-Path $env:LOCALAPPDATA "SyntheticSalesAssist-acceptance"
python -m synthetic_sales_assist.cli --data-dir $dataRoot db init
```

The path guard rejects relative paths, traversal, URLs, UNC/network shares, Windows device paths,
symlinked ancestors, and every path inside the repository. Runtime databases, WAL/journal files,
logs, exports, and backups are ignored by Git and must never be committed.

## CLI smoke test

The CLI performs no networking. Every demonstration uses a collected, reserved synthetic
scenario and persists through the same repositories used by application services.

```powershell
python -m synthetic_sales_assist.cli --data-dir $dataRoot doctor
python -m synthetic_sales_assist.cli --data-dir $dataRoot db verify --deep
python -m synthetic_sales_assist.cli --data-dir $dataRoot demo list
python -m synthetic_sales_assist.cli --data-dir $dataRoot demo run sales-credit-target-rep
python -m synthetic_sales_assist.cli --data-dir $dataRoot demo run doi-fulfillment-split
python -m synthetic_sales_assist.cli --data-dir $dataRoot metrics summary
```

Add `--json` anywhere in a command for the stable machine-readable envelope. The complete command
contract, all seven required aliases, inspection commands, exit codes, and backup/restore examples
are in `docs/milestone4-cli-reference.md` and `docs/milestone4-manual-acceptance.md`.

## Database maintenance

Initialize and verify before use. `db backup` uses SQLite's online backup API and writes a verified
sidecar receipt. Restore verifies the source, creates a pre-restore backup, stages and verifies the
replacement and rollback images, atomically replaces the still-present active path once, and
atomically installs the verified rollback image if post-replacement verification fails.
Backup overwrite likewise keeps the prior identity database at its canonical pathname until one
atomic replacement; managed backup-directory cleanup removes strictly named crash temporaries.

```powershell
python -m synthetic_sales_assist.cli --data-dir $dataRoot db status
python -m synthetic_sales_assist.cli --data-dir $dataRoot db backup `
  (Join-Path $dataRoot "backups\manual.sqlite3") --create-parent
python -m synthetic_sales_assist.cli --data-dir $dataRoot db restore `
  (Join-Path $dataRoot "backups\manual.sqlite3") --confirm
python -m synthetic_sales_assist.cli --data-dir $dataRoot db purge-expired-backups
```

Do not copy an open SQLite file as a backup. See `docs/milestone4-backup-restore-guide.md` for the
recovery, overwrite, cross-process exclusion, and exact-expiry cleanup rules and
`docs/milestone4-data-location-guide.md` for directory policy.

## Offline verification

Run the release gates from the repository root:

```powershell
python tools/quality_gate.py
python -m compileall -q src tests tools
python -m unittest tests.test_migrations
python -m unittest discover -s tests -t . -p "test_*persistence*.py"
python -m unittest discover -s tests -t . -p "test_*cli*.py"
python -m unittest discover -s tests -t . -p "test_sales_credit_*.py"
python -m unittest discover -s tests -t . -p "test_doi_*.py"
python -m unittest tests.test_milestone5_application
python -m unittest tests.test_milestone5_portal tests.test_milestone5_security
python -m unittest tests.test_milestone5_lifecycle tests.test_milestone5_boundary
python -m unittest tests.test_chrome_permissions
python -m unittest tests.test_milestone6_extension tests.test_milestone6_security tests.test_milestone6_boundary
python tools/package_milestone6_extension.py --check
python tools/run_tests.py
python tools/run_foundation_audit.py
```

Generate the deterministic schema inventory and migration verification documents after any
migration change:

```powershell
python tools/generate_milestone4_artifacts.py
```

The final audit verifies the supplied bundle, protected bytes, repository safety scans, synthetic
identity firewall, loopback-only policy, exactly one closed Milestone 6 Chrome manifest, zero
external/non-loopback runtime network operations, and all nine zero safety counters.

## Milestone boundary

Milestone 6 adds only the closed Chrome MV3 manifest, static read-only content extraction, closed
message relay, local side-panel display, deterministic packaging, and renderer-only DOM
compatibility needed to compare existing fictional facts. Order detail now labels its existing
summary, completeness, and line-universe sections; interaction detail publishes its existing
closed canonical interaction view and order binding. These are additive markers under the
unchanged `synthetic-sales-assist-dom/v1` contract, not new source facts or behavior. The existing
M5 API routes and same-origin/CSRF action boundary remain unchanged. The pure Milestone 1-3 engines
remain authoritative for business behavior; neither portal nor extension creates a reason,
ownership row, transition, or rule outcome. Schema remains version 4 with exactly the four
Milestone 4 migrations.

The four migrations are applied transactionally and checksum-bound. WAL mode, `FULL` synchronous
writes, foreign keys on every connection, bounded busy handling, connection-per-operation units of
work, append-only triggers, compare-and-swap projections, canonical replay material, and exclusive
maintenance coordination are binding implementation choices documented in ADRs 0016-0020.

The supplied `specs/`, `reference/`, `BUNDLE_MANIFEST.json`, `SHA256SUMS.txt`, and checksummed
root `README.md` remain byte-for-byte unchanged. Milestone-specific implementation and
verification material lives under `chrome_extension/`, `docs/`, `scripts/`, `src/`, `tests/`, and
`tools/`. Dashboard/control-center pages, non-loopback capability, store publication, production
connectors, and all Milestone 7 work remain absent.
