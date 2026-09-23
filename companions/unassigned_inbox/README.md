# Unassigned inbox companion

This optional Windows companion reads active, unassigned Help Scout conversations in one explicitly selected mailbox. It saves the listed work set and complete message histories to a private local runtime directory. It does not generate replies or offer any conversation mutation command.

The sales-assist core remains a synthetic training application. This companion is a separate, manually invoked integration proposed for review. Installing or opening sales-assist must not start it. No customer data, connection material, runtime reports, or generated work sets belong in GitHub.

## Private setup

Use an existing encrypted Help Scout connection owned by the Windows account running the companion. Copy `config.example.json` to a **location outside this checkout**, replace every example identity and mailbox value with values independently verified for the intended account, and set absolute paths for both `auth_path` and `runtime_dir`. Do not copy the live config or encrypted connection into this repository. Token renewal stays in memory.

The sample values are synthetic placeholders. A successful run requires a matching signed-in user, mailbox ID, name, and email. The `ecs` selector is only a local alias; it does not select a mailbox unless the configured identity checks pass.

From the repository root in PowerShell, invoke the reader explicitly:

```powershell
$configPath = Join-Path $env:LOCALAPPDATA 'sales-assist-private\unassigned\config.json'
python -m companions.unassigned_inbox --config $configPath --mailbox ecs --max-contexts 30
```

`--max-contexts` limits the number of full histories read in that call, after the complete listing is saved. Use `--all` to read every listed conversation, or continue only the unread IDs from a saved work set:

```powershell
python -m companions.unassigned_inbox --config $configPath --mailbox ecs --all
python -m companions.unassigned_inbox --config $configPath --mailbox ecs --resume 'unassigned-PASTE_ACTUAL_RUN_ID' --all
```

The reader first verifies the signed-in user and selected mailbox, then lists every page of active Unassigned conversations in that mailbox. It saves unique conversation IDs before reading histories. Each record is checked for current mailbox, active status, and absence of user or team assignment, and its full thread pagination must complete. Customer messages, staff replies, internal notes, events, and any existing drafts remain source records with their original type and state. Attachment names may be shown; attachment content is not downloaded.

Under the configured private `runtime_dir`, a run saves:

```text
unassigned/runs/RUN_ID/
  work-set.json       Listing, identifiers, scope, and page coverage
  records/ID.json     Individual read outcome and source history
  report.json         Counts and exceptions
  report.html         Local readable report
```

The report distinguishes fully read, unread, moved out of scope, and failed records. A bounded run may leave unread IDs by choice. Failed or moved records remain exceptions; `--resume` keeps the original work set and does not silently relist them. A new run obtains a new listing. The inbox can change during acquisition, so a completed report describes observed reads rather than a frozen server snapshot.

The local report contains private customer text. Keep its runtime directory private and outside the checkout. The HTML report escapes message text and does not load external images, scripts, or attachment contents. Do not attach reports or source records to issues or pull requests.

## Verification and limits

Run the companion's synthetic tests from the repository root:

```powershell
python -m unittest discover -s tests -p 'test_unassigned*.py' -q
```

These tests exercise pagination, scope checks, bounded resume, failures, and local report handling without a live Help Scout connection. This repository companion has no claim of live validation merely because a separate local reader was previously exercised. A reviewer should check the exact packaged code and private setup before any manual live invocation.

The companion does not include draft, send, assignment, status, note, tag, delete, or customer/order actions. It has no startup hook, UI button, schedule, or background worker. It does not use sales-assist's synthetic customer data as live input.
