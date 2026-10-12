# Single-owner pilot handoff

Source-only build. No credentials, ownership locks, live API, installed app, or
historical ledger have been used to verify this change. Automated cleanup has been
cancelled and must not be restarted by this workflow. Manual inbox work can continue.

The coordinator requires the cleanup owner's original `operation-v1.lock` and its
nonblocking byte-zero Windows lock, followed by the existing `SessionLease`.
The reviewed lock is under the explicitly supplied connection's same Documents
root at `Codex/2026-10-10/task-3/helpscout_one_outbound_candidate/operation-v1.lock`.
It is opened as an existing file and never created, truncated, or deleted. A fresh
stopped-owner confirmation and successful action-time acquisition are required;
do not wait for manual inbox closures to finish.

Duplicate protection combines the durable local ledger with complete supported
scoped API checks. Official conversation listing documents all statuses, without
an explicit promise of visibility of every historical draft-state conversation.
Preflight therefore reports only `NO_MATCH_IN_ACCESSIBLE_MAILBOX_SNAPSHOT`, not
global absence. It blocks on any returned draft, approved-order conversation,
ambiguous customer, incomplete page, or observed inconsistency. The conversation
`threads` metadata counts published threads excluding notes; every returned draft
and note is still inspected. See the endpoint references in the evidence contract.

## Private preparation

Keep all real inputs outside Git. Preserve the existing draft ledger. Supply the
actual approved draft row and its complete genuine review evidence; never turn
unknown factual, recipient, duplicate, or cart checks into invented confirmations.
Use the existing approval reference and exact already-approved copy, preserving
its link/rendering semantics. There is no need to reapprove unchanged copy.

The approved-bundle helper packages these supplied inputs, validates all review
holds, computes the canonical approval/body/rendering hashes, and reports the
SHA256 of the resulting file. A new ledger row uses version 2 because normal import
creates version 1 and recording the review through normal edit creates version 2.
An existing row requires its actual matching version and binding. No version is
silently upgraded.

```powershell
python -m sales_credit_evidence.approved_draft --help
python -m sales_credit_evidence.coordinator --help
python -m sales_credit_evidence.coordinator
```

The last command is deliberately `DISABLED` and performs no I/O. Preparation and
live flag names are documented by each command's help. Secrets are never command
arguments. The coordinator receives the bundle path and independently retained
SHA256; it does not discover a cache, choose a ledger, or infer an approval.

## Action-time gates, after source integration

1. Confirm the cancelled cleanup owner is stopped and no other credential consumer
   owns the connection. Do not run cleanup to obtain that confirmation.
2. Supply the original shared lock path paired with the explicit connection path.
   No substitute lock, injected no-op, or fake transport may be used for live execution.
3. Retain the existing content approval and verified full row/review evidence.
   Confirm the selected existing ledger, private bundle, file hash, and single
   credit contact. Historical sheet entry timestamps do not prove interaction time.
4. Ask for the one issuance authorization only at activation, if an expired cached
   token may need it. Suggested wording: “May this one Sales Assist session issue
   one token only if the cached token is expired, then read the selected contact
   and create the already-approved unsent draft?” No sending is authorized.
5. Invoke the coordinator once with `--live`, `--allow-one-draft`, all explicit
   scope/path/hash options, `--ownership controlled-handoff-complete`, and
   `--confirm-sole-owner`. Add `--allow-one-issuance` only for that separate grant.
   Both leases are acquired before cache access and held across both pilots.

After supplying these private variables, the complete cached-token invocation is:

```powershell
python -m sales_credit_evidence.coordinator `
  --live --allow-one-draft --confirm-sole-owner `
  --ownership controlled-handoff-complete `
  --credit-email $creditEmail --connection-path $connectionPath `
  --cleanup-lock-path $sharedLockPath `
  --approval-bundle-path $approvedBundlePath `
  --approval-bundle-sha256 $approvedBundleSha256 --ledger-path $ledgerPath
```

The extra `--allow-one-issuance` flag is omitted deliberately; append it only after
the separate one-issuance approval. A cached token that is expired without this
grant, or valid but within 120 seconds of expiry even with the grant, blocks.

The credit reader runs first. Missing/partial/ambiguous coverage stays explicit;
only a complete read permits draft preflight. The draft recipient must separately
resolve to one existing customer, with complete current duplicate checks. An
existing draft or matching-order conversation blocks creation. Manual user edits
may still race a read; these are bounded non-atomic observations, not a guarantee
that the inbox cannot change.

The normal durable transfer service reserves before the one POST. Success requires
verified readback of the unsent draft. `UNKNOWN`, `IN_FLIGHT`, or
`CREATED_UNVERIFIED` is a hold, never permission to retry. Preserve the ledger and
known conversation ID for a separately authorized read-only reconciliation. No
automatic retry, renewal, bulk transfer, customer creation, sending, or order
mutation is available.

Safe output retains the credit coverage summary if the later draft step fails.
`COMPLETE` requires both a complete credit read and verified draft result; it does
not assign credit. No persistent launch JSON, app startup setting, or cache is
written by the coordinator.

## Source verification

The final focused batch passed 962 tests: all evidence/coordinator components,
foundation safety checks, adjacent session/draft authentication and durable transfer
regressions, and Sales Credit evaluator/window tests. Ruff and strict typing checks
cover the six new source modules. Independent review found no blocking code issue.
Native lock compatibility was exercised only on a temporary dummy file, in both
directions against the original byte-lock mechanism.

The full repository suite is not certified: its sandbox run failed while collecting
unrelated DOI registries; an elevated run progressed to 14% and then stalled and
was stopped. These results do not establish a live API or credit-rule outcome.
