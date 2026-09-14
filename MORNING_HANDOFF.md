# Morning handoff: synthetic Campaigns and Replies

Working tree: `C:\Users\jlewi\OneDrive\Documents\Synthetic_Sales_Assist_Specification_Bundle_v1.0.1`

Branch: `codex/campaigns-replies-offline`.
Starting branch: `finish/synthetic-v0.1`.
Integration base HEAD: `dcf47074ce73b2886d8036423231e8612d2216b5`.
This is a local source integration on the isolated branch. No merge, PR, push,
deployment, production sync or background monitor is part of this handoff.
The separately validated 0.1.4 extracted release remains at `d667eb38`; its existing
`START.cmd` does not include this integration. Use the source launch command below.

## Delivered behavior

- The existing Control Center now links to `/campaigns`, `/replies`, and `/writing-history`.
  The existing loopback server, Host/Origin/CSRF guards and restrictive CSP serve these pages.
- Campaigns support explicit synthetic audience preparation, exclusions and holds,
  immutable exact payload previews, local simulated launch/pause/resume/step, receipt
  reconciliation and byte-hashed send-state import. Intents precede simulated creation;
  accepted or uncertain attempts cannot be resent. Pilot and campaign bindings stay separate.
- Replies have a paged/filterable queue, attention priority with deliberate cart sorting,
  thread evidence, classification explanation, attachment metadata, next action, reusable
  starter wording and durable local edits. Review binds revision, source fingerprint and
  style version. Concurrent/stale edits conflict; changed evidence or style invalidates review
  while preserving prior text. Customer requests remain separate from workflow status.
- History accepts extracted exporter 2.1.0 JSON, checks each record's author, preserves
  source/provenance, deduplicates exact IDs, quarantines conflicting copies, and provides
  included/held/excluded preparation with reasons. Quotes, signatures, templates, forwards
  and bounces are separated heuristically. Original wording remains available for review.
- The style slot is versioned. The supplied 13-message profile remains provisional. There
  is no large-corpus analysis, model training or AI API connection. Factual claims do not
  come from style rules. Synthetic reviewed jobs retain literal `draft: true` and are explicitly
  incompatible with the production writer; the UI performs no remote draft creation.

The new services live in `src/synthetic_sales_assist/campaign_replies/`. The UI assets are
`src/synthetic_sales_assist/portal/campaign_workspace.js` and `.css`. The launcher is
`tools/campaign_demo.py`. ADR 0031 explains persistence, concurrency, privacy and cutover.
The detailed contract is `docs/campaign-workspace-contract.md`.

Sales Credit, DOI, the shared order adapter, the four existing migrations, extension
permissions and protected specifications remain unchanged. A separate sibling
`data/campaign_replies.sqlite3` stores this feature using the existing local-path policy,
SQLite WAL/FULL and atomic transactions. It rejects unrelated existing databases before
writing. Core schema-4 backup/restore does not include this feature store; use SQLite's
backup API separately, never copy an open SQLite file.

One narrow scanner correction recognizes a PowerShell secure-string conversion from a
variable as code rather than a literal credential. Tests retain rejection of quoted values
and literal operands. The supplied exporter source remains byte-identical.
The two vendored JS test references are accepted only at their exact paths and reviewed
SHA-256 hashes. Altered or relocated copies retain normal rejection, and credential
scanning still applies. They are not app-served assets or a live transport.

## Launch

From this working tree, run in PowerShell:

```powershell
$python = 'C:\Users\jlewi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$campaignData = Join-Path $env:LOCALAPPDATA 'SyntheticSalesAssist-Campaigns-Demo-20260911'
& $python .\tools\campaign_demo.py --data-dir $campaignData --port 8876
```

This explicit runtime is available on this PC and is development-only/nonportable.
An installed compatible Python with the repository's existing dependencies may be used
instead. The launcher does not install or download anything. The explicit data root avoids
the delivered launcher's selected-data-root pointer and all existing worker data.

Open [Campaigns](http://127.0.0.1:8876/campaigns),
[Replies](http://127.0.0.1:8876/replies), or
[Writing history](http://127.0.0.1:8876/writing-history).
Press Ctrl+C in the demo terminal to stop that process; rerun the same command to restore
saved edits. If the port is already owned, choose another explicit unused port; do not kill
an unrelated listener. `--prepare-only` creates the generated demo without a listener.

For the complete round trip:

1. Open the prepared `SYN-RUN-CAMPAIGN-DEMO` campaign and inspect Preview.
2. Select Launch, then Simulate next outreach. Counts show local simulated acceptance.
3. Select Simulate customer replies, then open Replies.
4. Open `synthetic-customer-1@example.test`, inspect evidence, edit the draft and save.
5. Reload, or restart the app with the same data directory, and reopen the conversation.
6. Inspect Writing history's candidate reasons and versioned provisional style configuration.

Load synthetic demo is idempotent for unchanged fixtures and preserves edits/protections.
All import controls accept generated synthetic inputs only. The handoff's legacy IDs are
not relaxed into the application validator. The three independent Help Scout scripts were
not inspected, controlled, restarted or otherwise modified; their data was not accessed.
Their current status cannot be established from this development package.

## Earlier implementation validation

The following results belong to the earlier implementation and completion audit.
The later source-commit validation is recorded in "Source commit preparation" below.
One Windows directory-symlink check was unavailable, as detailed below.

| Check | Actual result |
|---|---|
| Complete repository regression | PASS: 1,721 tests in 845.394 s, with 1 unavailable symlink check skipped |
| Feature suite before completion audit | PASS: 102 unittest methods, 35.703 s, plus parameterized boundary cases |
| Final completion-audit feature checks | PASS: all 103 methods in scoped runs: 33 campaign tests / 14.725 s and 70 reply/history/workspace tests / 21.043 s |
| Companion regression | PASS: all 91 original mocked checks |
| Quality gate | PASS: 204 Python files, zero findings |
| Compilation | PASS: `compileall` over src/tests/tools |
| Foundation audit | PASS: protected bundle, schema-4 migrations, identity/content/secrets, loopback and all-zero safety counters |
| Existing extension package | PASS: unchanged bytes/permissions |
| Original handoff file hashes | PASS: all 40 manifest entries unchanged |
| In-app browser | PASS: campaign send simulation, reply, edit/save/review, reload and full process restart recovery; deliberate cart sort |
| 10,000-conversation latest measurement | Import 11.348 s; 50-row queue 0.368 s during the completion-audit scoped run |

Raw logs: `.runtime/campaign-full-suite.txt` and `.runtime/campaign-final-focused.txt`.
The full suite ran during feature review; the separate 102-test run checked the initial
delivery. The completion audit below added one UI regression and reran all 103 feature
methods in scoped runs after reviewing their current source. The skipped full-suite check was
`tests.test_milestone6_boundary.Milestone6BoundaryTests.test_packager_rejects_symlinked_extension_root_when_supported`
(`directory symlink unavailable: OSError`). That platform-dependent case is **NOT_PERFORMED**;
all other discovered full-suite cases passed.
Screenshot: `.runtime/campaign-replies-browser.png` (generated synthetic records only).
The earlier `.runtime/campaign-replies-browser-initial.png` preserves evidence of the
table-width issue before its correction; use the final screenshot for review.

The original browser acceptance used this task-owned data root:
`C:\Users\jlewi\.codex\visualizations\2026\09\11\01a08ec8-0d3a-7c81-8397-0b975858844a\campaign-demo-data`.
It held the browser-saved reviewed draft for `synthetic-customer-1@example.test`.
Use that exact data root to continue the previously populated demo; this document
does not assert that a service is currently running. The launch example
above uses a different, fresh local-app-data root. Pause then Resume safely reacquires
an idle simulated campaign after a process restart; uncertain in-flight state stays blocked.

```powershell
& $python tools/run_tests.py
& $python tools/run_tests.py tests.test_campaign_sending tests.test_campaign_replies `
  tests.test_campaign_history tests.test_campaign_workspace tests.test_campaign_workspace_review
& $python tools/quality_gate.py
& $python -m compileall -q src tests tools
& $python tools/run_foundation_audit.py
& $python tools/package_milestone6_extension.py --check
```

The companion results are mocked, offline contract checks: 26 lifecycle +17 draft
preparation +27 sync +21 writer = **91 PASS**. They are not evidence of live operations.
The four reference test files and all other package-manifest entries remain byte-identical
(40 hash checks). Generated application fixtures use reserved SYN identities and example.test.
These 91 checks are retained historical validation of the optional original handoff;
they are not dependencies of the committed regression suite. If repeated later, run
the original companion tests only in an isolated temporary copy with their mocks:
the draft test writes its own sibling fixture. Do not run it against the preserved original.

The new suite covers partial/older/repeated snapshots; draft persistence, competing edits,
review invalidation; customer followups, staff answers, notes, drafts, bounces, scheduling,
attachments, owner/recipient changes, missing anchors and merges; strict synthetic isolation;
history author/template/conflict/rollback boundaries; intent/receipt uncertainty, pause,
ownership, transfer hashes and reconciliation. Node parity tests compare the Python port
against the original lifecycle/evidence implementation using shared generated fixtures.

The 10,000-conversation fixture measures one import and a 50-row queue page using
`perf_counter`, without a stress loop. Queue rendering is capped at 50 rows. Read views use
stored derivations and a small sync projection; they do not regenerate every draft proposal.
A versioned one-time projection repair upgrades earlier cached summaries without changing
source snapshots, draft text, revisions or reviewed state; restart regression covers it.

Browser acceptance uses the Codex in-app browser on loopback with generated records:
campaign → simulated send → incoming reply → edit → save/review → reload → recover.
This is agent-executed synthetic evidence, not human acceptance, extension acceptance,
clean-machine validation, delivery or production readiness.

## Completion audit

The continuation audit re-read the three handoff instructions, inspected the current
branch/code/tests, and independently reviewed the campaign and reply/history services.
It found and fixed one interface defect: attachment metadata and proposal review notes
were stored correctly but not displayed beside the conversation. The conversation now
shows embedded attachment metadata, the unseen-content warning and starter review notes
as inert text. A rendering regression using the real API response and UI script failed
before the fix and passed afterward. Browser verification of the attachment-only follow-up
is captured in `.runtime/campaign-attachments-browser.png`.
The final affected suites were run with:

```powershell
& $python tools/run_tests.py tests.test_campaign_sending
& $python tools/run_tests.py tests.test_campaign_replies tests.test_campaign_history `
  tests.test_campaign_workspace tests.test_campaign_workspace_review
```

All 103 methods passed. The final quality gate checked 204 Python files with zero findings,
and `git diff --check` passed. The complete repository run above preceded this small
display correction; the affected feature suites and browser were rerun afterward.

| Required workflow | Completion evidence |
|---|---|
| Campaign import, exclusions, sorting and preview | `CampaignService.prepare_audience` / `preview`; campaign tests verify immutable payloads, exact synthetic tagged URLs, stable cart ordering and holds |
| Simulated execution, pause/resume and reconciliation | `CampaignService.step` / `reconcile`; tests cover one creation, durable intent/receipt, lost outcomes, ownership, interrupted admission, immutable transfer and no retry |
| Prioritized customer work | Cached reply queue and browser: opt-out remains above the larger cart; accepted identities connect campaign records to reply anchors |
| Editable persistent review | Source/revision/style conflict tests plus the browser-saved reviewed draft restored after process restart; attachment metadata and review notes now visibly verified |
| History and style preparation | History tests cover wrong authors, duplicate/conflicting records, partial coverage, malformed imports, templates/signatures/custom writing; provisional profile and reasons are inspectable |
| Preservation and isolation | All 40 handoff hashes rechecked unchanged; protected business modules/specifications have no diff; only generated local demo records used |
| Runnable result and future integration | The explicit demo command above and the separately scoped production transfer steps below |

## Source commit preparation

The integration includes its required runtime template resource and minimal test references.
History reads `src/synthetic_sales_assist/campaign_replies/data/saved_reply_references.json`
as a packaged resource. Its six supplied template transcriptions are unchanged; provenance
and SHA-256 are beside it. Two pure companion JS contracts and the synthetic scenario
inventory are tracked in `tests/fixtures/campaign_replies` with their source hashes.
The regression suite therefore runs without the original local handoff folder or ZIP.
Package-data declarations include the template JSON and workspace JS/CSS assets.
No worker modules, customer history, credentials, production ledgers, databases or
screenshots/logs are included in the integration commit.

Scoped commit validation ran from an isolated export of the staged source,
without the untracked original handoff. The complete repository regression was also
rerun on the final source before commit. Results are recorded here before the local commit.

- Complete final repository regression: **PASS**, 1,752 discovered tests in 766.287
  seconds: **1,751 passed, zero failed, one skipped**. The skipped case was
  `tests.test_milestone6_boundary.Milestone6BoundaryTests.test_packager_rejects_symlinked_extension_root_when_supported`
  (`directory symlink unavailable: OSError`). That platform-dependent check remains
  **NOT_PERFORMED**. Both corrected artifact-inventory selectors passed in this run.
- Final staged feature suite: **PASS**, 105 tests in 36.306 seconds. The added checks
  cover packaged template/UI resources without the handoff and the exact-reference
  scanner boundary, including credential detection at an approved fixture path.
- Staged foundation audit: **PASS**, no prohibited/secret findings and all safety
  counters zero. Quality: **PASS**, 204 Python files. Compilation and unchanged
  extension package check: **PASS**.
- Latest scale observation: 10,000 conversations imported in 10.424 seconds;
  the 50-row queue returned in 0.336 seconds during the final complete regression.
- Separate staged-source review: approved all 32 changed files, the exact-reference
  scanner allowance and the matching milestone inventory check. This is source review,
  not a new package attestation.
- Original handoff: all 40 manifest entries rechecked unchanged. Its ZIP/folder,
  databases, runtime evidence and previous release packages are excluded from the commit.

Final complete log: `.runtime/campaign-commit-full-suite-verified.txt`.
Final scoped log: `.runtime/campaign-commit-staged-feature-final.txt`.
Final foundation evidence: `.runtime/campaign-commit-staged-foundation-final.json`.
The initial staged audit rejected unregistered JS reference assets; its failed report
and the interrupted initial full-run log are preserved. The hash-bound exception and
negative tests closed that issue. The first completed commit regression ran 1,752 tests
in 776.022 seconds: 1,749 passed, two failed and one was skipped. Both failures were
the older milestone artifact inventory rejecting those same pinned test references.
Its exact-path/hash/size allowance now agrees with the scanner, without changing the
migration, portal or network restrictions. The 42 affected boundary/scanner/workspace
checks passed in 6.091 seconds. The failed full-run log remains unchanged at
`.runtime/campaign-commit-full-suite-final.txt`; only the complete corrected rerun is
used for commit acceptance.

## Reused references and later integration

`replies-core.js` lifecycle/category/queue behavior is ported to `replies.py` with parity
checks. `drafts-core.js` provides starter wording, evidence shape and reviewed-job boundaries.
`ReplySync.psm1` is a read-only sync contract reference; no PowerShell is executed by a web
request. `DraftWriter.psm1` supplies the future draft-only intent/receipt/no-retry contract.
The sender's conservative creation protocol is ported to `campaigns.py` with a closed
simulation transport. Its exact production authentication/pacing/source fixtures remain
reference-only. `Export-AllSentEmails.ps1` defines the imported report/chunk structure.
`Jude-Saved-Reply-References.json` supplies reference template wording kept separately from
the generated candidate corpus.

Before any production connection, a separately authorized production profile/store and
adapter are required. No actual recipient ledger is present here. The sending PC must supply:

- Exact campaign/pilot fixtures, recovery source and source/exclusion/template audits.
- Complete current sender state, every recipient record, intents, receipts, holds,
  review-holds, errors, observations and run reports, including all later attempts.
- Stable monitor snapshot/state with accepted conversation and anchor identities.
- Complete draft intent/receipt/reconciliation ledger if one exists.
- The exporter report and all extracted sent-email chunks for style preparation; exporter
  checkpoints/latest-run pointer if export itself will continue elsewhere.

Follow `SalesAssist_Handoff/PRODUCTION_STATE_HANDOFF.md`: independently verify writer
ownership and deliberately stop/cut over only when later authorized; preserve in-flight
unknowns; take byte-preserving staged copies with hashes; validate pilot and campaign
bindings and every protection; preview with zero creation requests. A copied lock does
not coordinate two PCs. Do not resolve uncertainty by resending or deleting history.

The versioned suppression-candidate view exposes opt-outs/bounces for future integration.
The existing PowerShell sender does not consume it; enforcement there is not claimed.
Eligibility/exclusion flags in new synthetic manifests are explicit inputs, because the
actual source/exclusion sheets are absent. Existing campaign continuation imports immutable
queues rather than regenerating them from a newer sheet.

Original `jlewis` cart links remain byte-preserved in the handoff references. The executable
adapter uses localhost cart URLs and reserved `SYN-REP-*` tracking values, as required by
the repository's synthetic identity policy. Accepted synthetic query strings are preserved
exactly, including product, quantity, configuration and tracking parameters. Literal
`salesrep=jlewis` is not an accepted runtime identity in this development store. The later
production adapter must preserve the original tagged URLs without substituting demo values.

Known limits: extracted JSON only (no ZIP); UI imports bounded to 8 MiB, offline history
service to 32 MiB/50,000 records; no remote polling, sends, drafts, credentials, attachment
downloads, production export or external links. Published acceptance is not delivery, and
recorded cart values or reported purchases are not recovered revenue. Future integration
must preserve these distinctions and the original three-worker handoff boundary.
