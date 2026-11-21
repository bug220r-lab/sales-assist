# Sales Assist DOI Intake — repository integration

A separate, opt-in companion process. This adds a repository entry point and a
validated review handoff; it is not a native dashboard button or Order Admin
adapter. Existing `START.cmd`, application behavior and databases are unchanged.
The manager sheet is never sorted or written back.

## Run the offline example

From the repository root, with Python 3.10 or newer installed:

```powershell
.\DOI_INTAKE.cmd
.\DOI_INTAKE.cmd demo
```

The first command displays help without starting a task. Cross-platform commands:

```text
python -m companions.doi_intake demo
python -m unittest discover -s companions/doi_intake/tests -v
```

The Windows launcher uses `py -3`, or the executable named by `SSA_DOI_PYTHON`.
It does not install packages or trigger OAuth on startup. Demo and tests need only
the standard library. The demo contains fictional numbers: 8 Jude occurrences,
7 unique orders, 6 lookup candidates and 1 held assignment conflict.

Data defaults to `%LOCALAPPDATA%\SalesAssistDOIIntake` on Windows and
`~/.local/share/SalesAssistDOIIntake` elsewhere. The supported entry point rejects
output, credential, history and review paths inside this checkout. Use local,
access-controlled storage outside Git and synced/shared working folders.

## Optional live Google reads

The Google account needs existing permission to read the manager workbook and an
organization-approved Desktop OAuth client. This code does not grant permission,
change sharing, or reuse ChatGPT's connected account. Install the optional
requirements into an environment outside the checkout:

```powershell
py -3 -m venv "$env:LOCALAPPDATA\SalesAssistDOIIntake\venv"
$env:SSA_DOI_PYTHON = "$env:LOCALAPPDATA\SalesAssistDOIIntake\venv\Scripts\python.exe"
& $env:SSA_DOI_PYTHON -m pip install -r .\companions\doi_intake\requirements-google.txt
.\DOI_INTAKE.cmd --enable-google auth --client-secret "C:\approved-location\desktop-client.json"
.\DOI_INTAKE.cmd --enable-google sheets --day wednesday --source-date 2026-09-23 --run-id 2026-09-23-wednesday
```

The client path is a placeholder. Supply the actual batch date; a tab name or
capture timestamp does not establish which business batch it contains. Date and
weekday must agree. `--enable-google` must precede `auth` or `sheets`.

Use this wrapper rather than invoking the vendored script directly: its extra
opt-in/path checks are entry-point controls, not a sandbox against arbitrary Python
execution. Dependency ranges are not a reproducible lockfile. The separate OAuth
token is sensitive plaintext protected by local file permissions, not encrypted
by the companion. Never commit or share it.

Source acquisition retains the v1 fixed workbook/tab/layout contract and exact
Jude normalization. Only bounded metadata and A1:B1, E1:G1 and A2:B data are read;
E2:O is not ingested. Two matching reads are not a revision lock. Authentication
uses Google OAuth endpoints; data requests are GET-only to the fixed Sheets host.
There is no Order Admin request, source mutation, order change or email action.

## Verify and review the output

Each run produces `intake.json`, `lookup_queue.csv`, `held_orders.csv`,
`source_occurrences.csv`, `report.json` and `manifest.json`.

```powershell
.\DOI_INTAKE.cmd verify "$env:LOCALAPPDATA\SalesAssistDOIIntake\runs\2026-09-23-wednesday"
.\DOI_INTAKE.cmd review "$env:LOCALAPPDATA\SalesAssistDOIIntake\runs\2026-09-23-wednesday" --run-id 2026-09-23-wednesday --source-date 2026-09-23
```

`verify` checks completion-file hashes. `review` additionally checks source/run
identity, version, capture freshness, ownership, states, unique orders and source
rows, historical context, priorities, count equations, fingerprints and agreement
between JSON, reports and CSVs. A held order remains outside the lookup queue.
The returned `sales-assist-doi-review-queue/v1` contract always carries
`execution_authorized: false`: this is a review result, not a reader command.

The default capture-age limit is **4 hours**, configurable with
`--max-age-hours` from 1 through 24. This is a new integration guard, not an
existing DOI business rule. Future-dated captures are rejected. Old source dates
stay visible even after a recent capture. Checksums detect corruption; they do not
prove source authenticity against wholesale replacement of an unsigned bundle.

Synthetic examples require `--allow-synthetic` for review and still obey the age
limit. The preserved demo clock is fixed at September 23, 2026; it is not refreshed
to look current. Use `demo` followed by `verify` for a timeless smoke test. Tests
inject a deterministic clock to exercise review validation.

Default sorting preserves source order after filtering/deduplication. Optional
`--sort followups --history <external-file>` prioritizes historical unfinished
checks, then due follow-ups, new orders and other rechecks. The history envelope is
`{"schema_version":"sales-assist-doi-intake-history/v1","records":[]}`. Each record
has `order_number`, `observed_at`, `lookup_state`, `followup_at`,
`last_known_status` and `evidence_ref`. Timestamps include offsets; lookup states
are unfinished, failed, completed or unknown. History is explicitly historical:
shipped/canceled/excluded labels never remove a current source candidate.

Malformed populated rows block the whole import. Duplicate Jude rows preserve all
source references. Cross-assignment orders are held. Identical reruns reuse their
original output and capture time; changed material under the same run ID is
blocked instead of overwritten. After a failed invocation, do not treat an older
successful folder as its result. No live totals, stock or split eligibility are
inferred from the manager sheet.

Exit codes: 0 means the command completed, not permission to execute; 2 means
blocked/invalid input; 4 means a run-content conflict.

## Provenance and limits

`doi_intake.py` is the supplied v1.0.0 script, byte-for-byte. SHA-256:
`e0172417ae2820414eb8bdb01f27416f1a8edb6e9255a6dbaad965a194892f2b`.
Its 76 tests are preserved with only the import changed for the repository package.
There are 38 additional entry-point/handoff tests, all using fictional records.
Actual local results and unexecuted gates are recorded in `verification.json`.

See [the design decision](../../docs/integrations/doi-intake.md). This source
integration does not update an installed Windows app, publish a release, connect
an Order Admin reader, or prove live production readiness. Existing app backup
commands do not back up the external companion data directory.
