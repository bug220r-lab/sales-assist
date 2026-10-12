# ADR 0046: Single owner for two explicitly authorized pilots

Status: source implementation and synthetic verification only. Live execution is off.

## Context

One bounded credit-evidence read and one separately approved unsent draft need to
share the existing connection without competing with a cleanup credential owner.
The cleanup task was cancelled; its remaining manual work is not a prerequisite.
A fresh handoff and acquisition of its original lock are still required at action
time. A historical observation that a lock was free is not a reservation.

This source exception does not activate an installed app or change Sales Credit
business rules. Actual customer data, approval copy, credentials, and ledgers stay
outside this synthetic repository. The previously approved draft content does not
need another content approval. Token issuance requires its own explicit approval.

## Decision

Add a standalone default-off `sales_credit_evidence.coordinator` entry point. It
requires one credit email, explicit paths, an exact approved-bundle file hash, a
fresh ownership attestation, and a separate one-draft gate. It must acquire the
original cleanup lease first and the existing fixed-user `SessionLease` second,
then hold both until clients and the credential owner close. Every failure closes
constructed resources in reverse order. No background service or persistent launch
configuration is enabled.

Read-only inspection of the cancelled cleanup runner establishes its exact contract:
`helpscout_semantic_continuation_release/source/execute_release.py` uses the shared
`helpscout_one_outbound_candidate/operation-v1.lock`, a nonblocking `msvcrt` byte-zero
lock retained until release. The earlier cleanup runners use the same location and
mechanism. `cleanup_lock.py` validates the reviewed relative lock/connection pairing
under the explicit Documents root, opens only the existing lock, checks file/link
stability, and acquires/releases that same byte. It never creates, seeds, truncates,
deletes, polls, or restarts cleanup. Tests use dummy paths and injected operations;
the real shared lock is not probed during development.

`SessionSnapshotOwner` exposes a public immutable token/expiry snapshot, reads and
decrypts the approved cache once after both leases, and never instantiates the
legacy automatically renewing provider. It preserves authoritative expiry. A valid
cached token with more than 120 seconds remaining is reused. A near-expiry token is
blocked. Only an actually expired token, plus explicit issuance authorization,
permits one token POST. Reservation precedes that POST; errors never reopen it.
The response lifetime starts at the pre-request clock value and must still leave
the margin after receipt. No token is persisted, logged, passed on a command line,
or renewed after 401. Mutable plaintext buffers are cleared; immutable memory is
not claimed to be physically erased.

Run the credit reader first with at most 50 GETs and one attempt per request.
Preserve its real coverage result and `NOT_EVALUATED` credit classification. An
incomplete read blocks the draft sequence. A complete search with no exact credit
customer remains a valid scoped result; the independent draft recipient is checked
separately.

Draft preflight requires one exact existing customer with one matching email,
complete bounded traversal in the fixed mailbox, stable native metadata, and no
existing draft or conversation mentioning the approved order/subject. It considers
all retrieved threads, including those excluded from credit evidence. The sealed
proof binds the bundle and recipient, and expires 120 seconds after the first
observation. There is no claim of atomic duplicate absence: manual inbox changes
and unavailable records remain outside local process locks. Observed inconsistency
blocks execution; the coordinator never closes or changes unrelated conversations.

Official list documentation does not explicitly prove that `status=all` exposes
every historical draft-state conversation. The user authorized one new unsent
draft with scoped duplicate protection; global absence is not required or claimed.
Preflight reports only no match in the accessible mailbox snapshot. The durable
ledger separately prevents repeating this coordinator's own attempt, and all
returned drafts or matching-order conversations block creation. The native
conversation `threads` field counts published threads excluding notes; it cannot
prove total draft/thread completeness.

An approved bundle contains the full supplied row and genuine review evidence,
their existing canonical approval binding, source approval reference, exact body,
rendered-body hash, version, recipient, and subject. The file itself has an
out-of-band SHA256. Validation rejects missing review gates, changed copy, changed
rendering, and changed metadata. Packaging is not permission to invent review
facts. Normal service import/edit/approve commands establish a new row at explicitly
approved version 2. Existing records must match exactly and are never overwritten.

Use the existing durable `DraftTransferStore` and normal
`DraftTransferService.transfer(retry=False)` once. Its transaction records
`IN_FLIGHT` before network access. Known or uncertain prior final write states
cannot create a second draft; all other prior attempts also require a separate
workflow, unavailable in this coordinator. Unknown results never authorize retry.
The operation ID remains a local audit identifier, not remote idempotency.

`OneDraftClient` independently binds recipient, order, subject, rendered content,
and the verified existing customer ID. Both conversation and reply use that ID,
avoiding the email-based customer-creation behavior. Require fixed mailbox/user
verification, then permit one draft POST and a readback of only its returned ID.
At most three destination/readback GETs are allowed. Every request rechecks expiry;
401/403 stops the sequence without renewal. The payload cannot send, schedule, add
CC/BCC, mutate an order, or close another conversation. Readback verifies native
customer identity and existing draft/content checks before reporting success.

## Verification and limits

Use only injected cache, DPAPI, issuer, HTTP, and lease boundaries. Real local
temporary ledgers exercise the normal reservation and replay protections. Tests
cover default-off gates, acquisition/release ordering, one shared snapshot, actual
expiry versus near-expiry, failed/ambiguous coverage, stale or wrong proof, exact
copy binding, one POST, readback failure, and durable unknown outcomes. Safe output
contains operational counts/codes and an optional created conversation ID; no
content, customer email, secret, or private path is emitted.

Reuse the existing `launch.private_path()` policy for bundle inputs, bundle output,
and the durable ledger, including before authentication. Generic local-path checks
alone do not exclude synced roots, other repositories, or non-fixed disks. No
persistent launch configuration is needed to reuse that path policy.

Total configured reads are at most 50 credit GETs + 50 draft-preflight GETs + 3
destination/readback GETs. Token issuance and draft creation each have separate
one-attempt budgets. Socket timeouts do not establish a total wall-clock deadline.
Synthetic success is not live readiness or company policy. See the
[operator handoff](../single-owner-pilots.md) and existing
[evidence contract](../helpscout-credit-evidence.md).
