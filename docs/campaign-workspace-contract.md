# Synthetic Campaigns and Replies workspace contract

This feature extends the existing loopback Control Center. It uses the standard-library
Python server and an independent `data/campaign_replies.sqlite3` database under the
explicit application data root. Existing Sales Credit, DOI, shared order, and worker
stores are not migrated. The source checkout remains unsuitable for runtime storage:
the existing absolute-local-path, no-reparse-point, outside-repository policy applies.

The new services are in `src/synthetic_sales_assist/campaign_replies/`.
`WorkspaceApplication` composes `CampaignService`, `RepliesService`, and `HistoryService`
over `Store`. The store uses connection-scoped transactions, `BEGIN IMMEDIATE`, WAL,
foreign keys, a bounded busy timeout, and `synchronous=FULL`.

This is the source integration. The previously extracted 0.1.4 release is immutable
and does not gain these pages when source changes are committed. Use the source demo
command below; a new release package is a separate step.

Required template wording ships as `campaign_replies/data/saved_reply_references.json`.
Its exact source hash is recorded beside it. Tests carry only the two pure companion
JS contracts and synthetic scenario inventory under `tests/fixtures/campaign_replies`.
The source and regression suite do not require the original local handoff folder.

## Prepare and launch the generated demo

From the repository root in PowerShell, use an explicit new synthetic data directory.
This example uses an explicitly selected local data directory. Keep the same
`$campaignData` value to recover previously saved drafts on the next launch.

```powershell
$campaignPython = 'C:\path\to\approved-development-runtime\python.exe'
$campaignData = 'C:\path\to\synthetic-campaign-demo-data'
& $campaignPython tools/campaign_demo.py --data-dir $campaignData --prepare-only
& $campaignPython tools/campaign_demo.py --data-dir $campaignData --port 8876
```

Preparation is idempotent. It creates five campaign recipients, eight reply examples,
and ten unique writing-history examples, with a deliberate repeated history record.
Launch prints the verified local origin and `/campaigns` URL. The feature pages are
`/campaigns`, `/replies`, and `/writing-history`; the existing portal navigation remains
available. Ctrl+C stops this foreground demo process through its normal cleanup path.
This command does not launch any PowerShell companion, poller, exporter, or sender.

The campaign demo ID is `SYN-RUN-CAMPAIGN-DEMO`. Its queue keys begin with
`SYN-EVIDENCE-QUEUE-00001`. The independent preloaded reply examples use
`SYN-RUN-REPLIES-DEMO`, so generated campaign replies cannot replace their identities.

To materialize inspectable generated audience and history JSON files after preparation:

```powershell
$env:PYTHONPATH = 'src'
$env:SSA_CAMPAIGN_DATA = $campaignData
@'
import json
import os
from pathlib import Path
from synthetic_sales_assist.campaign_replies.campaign_fixtures import demo_manifest
from synthetic_sales_assist.campaign_replies.history_fixtures import demo_history_export

output = Path(os.environ['SSA_CAMPAIGN_DATA']) / 'exports'
output.mkdir(exist_ok=True)
(output / 'synthetic-audience.json').write_text(
    json.dumps(demo_manifest(), indent=2), encoding='utf-8')
history = demo_history_export()
(output / 'synthetic-history-report.json').write_text(
    json.dumps(history['report'], indent=2), encoding='utf-8')
for name, document in history['files'].items():
    (output / name).write_text(json.dumps(document, indent=2), encoding='utf-8')
'@ | & $campaignPython -
```

## HTTP and service interfaces

All feature JSON reads use `GET /api/v1/campaign-workspace`. All actions use
`POST /api/v1/campaign-workspace/actions`, with the existing portal's same-origin,
CSRF, authorization, request-shape, and body-size protections. The feature body limit
is 8 MiB. Use the UI for authenticated actions; the service examples below are local
Python calls and do not bypass these HTTP protections. Unknown members are rejected.

| GET query | Result |
|---|---|
| `view=campaigns` | Campaign summaries and separate accepted, unverified/review, unknown, held, and untouched counts |
| `view=campaign&id=<campaign_id>` | Immutable queue records, intent/receipt/hold evidence, status, and accepted IDs |
| `view=preview&campaign_id=<campaign_id>&id=<queue_key>` | Exact synthetic payload, payload hash, and text/HTML source |
| `view=queue` | Reply queue; optional `campaign_id`, `needs_reply=true/false`, `category`, `owner`, `sort`, and `offset` |
| `view=conversation&id=<conversation_id>` | Conversation evidence, classification, starter wording, local draft, style version, and blockers |
| `view=history` | History summary, first candidate page, and current style profile |

Queue HTTP responses contain at most 50 records. Default priority keeps opt-outs and
complaints prominent; `sort=cart` deliberately selects descending recorded cart value.
The direct service offers `list_queue(..., limit=50)` with a maximum limit of 100.
Recorded cart value and reported purchases are not recovered-revenue measurements.

| POST `action` | Required additional members |
|---|---|
| `demo` | None; idempotently seed generated fixtures |
| `prepare` | `document`: new synthetic manifest |
| `send-state` | `document`: complete synthetic byte-hashed transfer envelope |
| `launch`, `pause`, `resume`, `step`, `reconcile`, `demo-reply` | `campaign_id` |
| `snapshot` | `snapshot`: complete validated schema-2 synthetic reply snapshot |
| `history` | `report`, `files`: extracted exporter-shaped history documents |
| `profile` | `profile`: next versioned style configuration |
| `save-draft` | `conversation_id`, `text`, `expected_revision`, `source_fingerprint`, `style_version`, `reviewed` |
| `synthetic-job` | `conversation_id`: reviewed synthetic serialization exercise only |

`launch` claims the local simulated writer; it does not create a background loop.
Each `step` admits at most one simulated creation. `pause` immediately prevents new
admission; an already admitted request may save its outcome, then becomes `PAUSED`.
A receiptless unexplained intent blocks further sending throughout the same feature
store. Resume never clears attempts, receipts, or holds. An idle local worker may be
paused and reclaimed; an in-flight worker cannot be replaced through launch/resume.
This is local-store coordination, not distributed locking or ownership on another PC.

`demo-reply` constructs a complete generated snapshot from the campaign's accepted
conversation and anchor IDs through `snapshot_from_campaign_records`. It does not
discover membership by subject. `reconcile` reads saved IDs and performs local fake
observation checks; it cannot resend. Neither operation contacts Help Scout.

The direct reply APIs are `import_snapshot`, `list_queue`, `detail`, `save_draft`,
`style_profile`, `set_style_profile`, `synthetic_job`, and `suppression_candidates`.
Snapshot facts and editable draft records are separate. Older, partial, identity-changing,
or malformed snapshots do not replace the prior complete snapshot. Draft revisions,
source fingerprints, and style versions are checked together. Source/style changes
invalidate review while retaining accepted local text and superseded versions.
Attachment-only follow-ups, staff drafts, unresolved merges, and uncertain writer
outcomes are represented explicitly.

`synthetic_job` is a serialization fixture with literal `draft: true`, a synthetic
profile, and reserved IDs. It is deliberately incompatible with the production writer.
Campaign outreach uses `draft: false`; there is no published customer-reply action.
`suppression_candidates()` returns a versioned opt-out/bounce interface with
`enforced_by_running_sender: false`. The existing sender does not read this new store.

## New audience and immutable synthetic transfer

`CampaignService.prepare_audience(manifest)` accepts the generated v1 manifest shape.
It requires explicit synthetic profile/fixture markers, reserved campaign, queue,
customer, sender and inbox identities, `example.test` addresses, an exact template
containing one `{cart_url}`, and explicit eligibility/exclusion/address-review flags.
Recipient matching trims and lowercases email; it never corrects spelling. Duplicate
keys, recipients, or original ranks are rejected atomically. Positive-value eligible
rows are ordered by descending recorded cart cents and then original rank. Unknown
eligibility, address review, exclusions, and zero-value carts remain held.

Tagged cart URLs must be loopback HTTP URLs; product, quantity, configuration, and
sender query parameters are preserved. The source manifest, recipient/content binding,
original ranks, and independently hashed pilot manifest become immutable. A new
manifest cannot revise an existing campaign under the same ID.

The original `jlewis` tagged links are retained unchanged in the handoff reference files.
The executable adapter deliberately uses reserved `SYN-REP-*` tracking identities;
`salesrep=jlewis` is rejected in this synthetic store. This is a synthetic fixture adaptation,
not evidence of production-link import. The separately authorized production adapter must
retain original tagged URLs exactly, including the original sender tracking value.

The original production eligibility/exclusion spreadsheets and current campaign
configuration are absent. This implementation therefore consumes explicit generated
eligibility decisions; it cannot recreate those missing decisions or relabel historically
skipped purchase/opt-out/support checks as passed.

For a byte-preserving synthetic transfer preview, pause the local simulated campaign
and wait until its UI status is `PAUSED`. With the PowerShell variables above still set:

```powershell
@'
import json
import os
from pathlib import Path
from synthetic_sales_assist.campaign_replies.campaigns import CampaignService
from synthetic_sales_assist.campaign_replies.store import Store

root = Path(os.environ['SSA_CAMPAIGN_DATA'])
source = CampaignService(Store(root / 'data' / 'campaign_replies.sqlite3'))
campaign_id = 'SYN-RUN-CAMPAIGN-DEMO'
bundle = source.export_send_state(campaign_id)
path = root / 'exports' / 'synthetic-send-state.json'
path.write_text(json.dumps(bundle, indent=2), encoding='utf-8')
preview = CampaignService(Store(root / 'synthetic-transfer-preview.sqlite3'))
result = preview.import_send_state(json.loads(path.read_text(encoding='utf-8')))
print(result['counts'])
assert preview.transport.posts == []
'@ | & $campaignPython -
```

The envelope requires `schema_version: 1`, `profile: synthetic`, `synthetic_fixture:
true`, `complete: true`, and matching `files`/`hashes` inventories. `files` contains
UTF-8 text bytes represented as JSON strings for `campaign.json`, `pilot.json`,
`recovery.json`, `audit.json`, and each existing `records/<queue_key>/` intent,
receipt, hold, post-error, and observation. SHA-256 is computed over each exact UTF-8
string; changing whitespace in a reviewed intent invalidates its byte hash.
The envelope is a transport for this new synthetic schema, not the original sender's
filesystem layout or an import authorization for customer data.

Import validates inventory, size, filenames, source hashes, per-record campaign/pilot
bindings, payload/recipient bindings, all saved protections, and complete observations
before committing. Original envelopes and append-only event evidence remain stored.
An older copy cannot remove or alter saved intents, receipts, holds, or audit history.
A receipt without intent, report-only acceptance, altered source binding, incorrect
pilot binding, or changed review-evidence hash is rejected. A valid receipt without
verification remains accepted-but-unverified. An unexplained intent remains unknown
and prevents creation. The exact historical-unknown hold requires a matching recovery
entry, queue key, run ID, and intent byte hash; it is not a general retry exemption.

## Writing history preparation

`HistoryService.import_export(report, files)` accepts extracted
`sent-emails-00001.json`-style chunks as parsed documents or their original JSON text.
Exporter 2.1.0 schema validation runs independently of the synthetic identity gate.
ZIP extraction is intentionally unsupported. The direct importer bounds total input
to 32 MiB and 50,000 records; HTTP imports additionally obey the 8 MiB request limit.
`summary()` gives included/held/excluded counts and reasons;
`candidates(offset=0, limit=50)` exposes prepared text, raw variants, and provenance.

Thread identity deduplicates exact copies. Conflicting copies remain quarantined,
and every record's author is compared with the report author. Source metadata,
saved-reply IDs, text/HTML, timestamps, published/bounced state, attachments, and raw
chunk provenance remain available. Interrupted/partial coverage and older imports
are reported. `replyUserIds` is a filtered conversation index, so initial outbound-only
coverage remains unverified and successful import never means exhaustive all-sent history.

Reference wording from `Jude-Saved-Reply-References.json` informs the deterministic
template detector. Exact/normalized repeated substantive passages and variable links
are separated from candidate prose; custom additions survive. Near matches are held
for review. Greeting/closing-only matches are insufficient. An unverified saved-reply ID
alone does not identify a signature or exclude a message. HTML cleaning, quote removal,
and near-match detection remain inspectable heuristics. Candidate attribution is not
proof of personally typed text. This is neither model training nor completed large-corpus
style analysis; the versioned style slot begins with an explicitly provisional profile.

## Reference mapping and deferred production work

Original files under `SalesAssist_Handoff/` remain references and are not loaded as
executable customer fixtures. Generated fixtures replace their legacy IDs explicitly.

| Reference functions | Current service equivalent / status |
|---|---|
| Sender `Email` | `_manifest`: trim/lowercase matching plus existing synthetic email firewall |
| Sender `Hash`, `Write-NewJson`, `Write-AtomicJson` | `sha`, immutable ledger fields, `Store.transaction`; original byte strings retained on transfer |
| Sender `Has-History` | `SimulationTransport.history` and `CampaignService.step`: fresh complete all-status evidence or hold/failure |
| Sender `Send-Once` | `CampaignService.step`: committed immutable intent, one simulated creation, immediate receipt save, no uncertain retry |
| Sender `Assert-Published`, `Verify-Published`, `Assert-EmptyRecipientArray` | `_verify` / `reconcile`: exact identity, author, inbox, body, scheduling and recipient checks; explicit empty To has distinct evidence |
| Sender `Hrefs`, `Semantic-Body`, `Body-Layout`, `Assert-Body` | Generated tagged-link preservation and stricter exact synthetic HTML comparison; legacy HTML-equivalence implementation remains reference-only |
| Sender `Is-EmailErrorField`, `Save-Post400`, `Apply-ReviewHold`, `Create-ReviewHold` | `_email_error`, durable error/hold bindings, and `import_send_state` byte-hash validation |
| Sender `Install-ReviewedCheckpoint` | Exact synthetic recovery binding supported; original 115-receipt and 58-hold production anchors await actual source files |
| Sender `Read-Api`, `Require-TokenBudget`, `Pace`, `Admit-Request`, `Update-RateBudget`, `Pause-Requests` | No live implementation; simulation exposes explicit authorization/ownership/rate-budget preconditions only |
| `ReplySync.psm1` `New-ApiSession`, `Connect-HelpScout` | Authentication remains reference-only and unconnected |
| `replies-core.js` lifecycle/category/queue behavior | Server-side `replies.py` classification, `derive`, and cached paginated `RepliesService.list_queue`; generated parity checks exercise the companion |
| `drafts-core.js` `prepareEvidence`, `eligible`, `proposal`, `job` | `prepare_evidence`, `eligible`, `proposal`, `save_draft`, and `synthetic_job` |
| `ReplySync.psm1` `Import-Campaign`, `Get-Pages`, `Get-Conversation`, `Get-ListedAnchor`, `Sync-Campaign` | Schema-2 snapshot validation/import and generated anchor bridge; network sync and merge retrieval are deferred |
| `DraftWriter.psm1` `Thread-Evidence`, `Assert-Evidence`, `Assert-DraftTarget`, `Submit-Draft`, `Invoke-DraftJob` | Local evidence/review and synthetic job serialization implemented; remote draft execution remains unconnected |

No authentication, live request pacing, account-wide rate sharing, live history lookup,
production send, remote draft, worker control, ownership cutover, or cross-PC lock was
performed. The three separate PowerShell workers and their data are outside this
development feature's control.

Later production integration requires the full immutable campaign/pilot/recovery
sources, current record directories and observation history, complete current ledger,
monitor snapshot, draft ledger if present, and the exporter run/checkpoint bundle where
continuation is required. Follow `SalesAssist_Handoff/PRODUCTION_STATE_HANDOFF.md`:
first establish a deliberate single-writer cutover and stable source copies, preserve
original bytes, then validate a separately designed production-profile adapter/store.
Do not copy a lock filename as ownership proof, restart a sender to test this UI, or
infer current progress from the historical checkpoint counts.

## Executable verification

The campaign suite is standard-library unittest and is included by the normal
`tools/run_tests.py` discovery. Its concrete cases cover the supplied scenario inventory,
strict HTTP400 holds, unknown outcomes, receipt-save failure, in-flight pause, reentrant
admission, ownership, stale/altered transfer data, bad To evidence, and campaign-to-reply
review persistence. Run it with:

```powershell
& $campaignPython tools/run_tests.py tests.test_campaign_sending
& $campaignPython tools/quality_gate.py
& $campaignPython tools/run_tests.py
```

`MORNING_HANDOFF.md` records the actual final suite/browser/scale results for this
checkout. This contract describes behavior; it does not promote an offline simulation
to Help Scout acceptance, delivery, manual business acceptance, or production readiness.
