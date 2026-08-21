# Milestone 5 development

This repository contains the synthetic-only safety foundation, immutable Shared Domain Engine,
Sales Credit rule pack, DOI rule pack, and local SQLite persistence and command-line interface.
Milestone 5 adds one standard-library HTTP service, closed local API, generic synthetic portal,
scenario library, and Windows lifecycle scripts. The listener and runtime requests are
loopback-only. There is no dashboard/control center, browser extension or manifest, production
connector, scheduler, external network client, remote asset, or external telemetry.

## Requirements

- Python 3.12 or newer
- Git
- no production connector, credential, or external data source

Runtime code uses only the Python standard library. Optional development tools are declared in
`pyproject.toml`; the release gates execute offline. Run commands from a complete verified source
checkout because migrations and the closed business registries are repository-bound artifacts.

Set the source path for a checkout that has not been installed:

```powershell
$env:PYTHONPATH = "src"
```

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
python tools/run_tests.py
python tools/run_foundation_audit.py
```

Generate the deterministic schema inventory and migration verification documents after any
migration change:

```powershell
python tools/generate_milestone4_artifacts.py
```

The final audit verifies the supplied bundle, protected bytes, repository safety scans, synthetic
identity firewall, loopback-only policy, zero Chrome manifests, zero external/non-loopback runtime
network operations, and all nine zero safety counters.

## Milestone boundary

Milestone 5 adds only the socket-neutral application boundary, loopback service/API, generic
synthetic portal and static assets, scenario selection/evaluation, Windows lifecycle scripts, and
their tests/docs. The pure Milestone 1-3 engines remain authoritative for business behavior; the
portal does not create a new reason, ownership row, transition, or rule outcome. Schema remains
version 4 with exactly the four Milestone 4 migrations.

The four migrations are applied transactionally and checksum-bound. WAL mode, `FULL` synchronous
writes, foreign keys on every connection, bounded busy handling, connection-per-operation units of
work, append-only triggers, compare-and-swap projections, canonical replay material, and exclusive
maintenance coordination are binding implementation choices documented in ADRs 0016-0020.

The supplied `specs/`, `reference/`, `BUNDLE_MANIFEST.json`, `SHA256SUMS.txt`, and checksummed
root `README.md` remain byte-for-byte unchanged. Milestone-specific implementation and
verification material lives under `docs/`, `scripts/`, `src/`, `tests/`, and `tools/`.
