# ADR 0011: Sales Credit replay, closure, retention, and metrics

- Status: accepted for Milestone 2
- Scope: process-local case accumulation and pure audit/metric projections

## Decision

`InMemorySalesCreditState` is the sole supported process-local coordinator for discovery-backed
case and no-order work. It shares one natural-key search-run authority and acquires the case and
no-order locks as one composition boundary. Selector-owned candidate evaluations are reduced before
case mutation: each native interaction owner receives an independent factual evaluation, the
coordinator attaches only that order's exact qualifying interaction scope (or, when no qualifying
owner exists, its exact preserved-uncertain scope), and deterministic nonmatches remain no-order
effects. A batch must contain exactly the orders that require a positive or governed-preserved case;
raw candidate enumeration alone does not authorize a favorable case. Direct discovery mutation,
case-only discovery batches, and direct no-order application are rejected in coordinated mode.
The standalone no-order ledger retains its isolated aggregate `apply_run` compatibility/KAT
surface, but that mode rejects post-evaluation staging; coordinated and legacy receipt families
cannot coexist in one ledger instance.

The natural case key is the canonical synthetic Order ID. Active command equality is represented
from initial acceptance by a keyed HMAC over the complete canonical command, never by retained raw
canonical bytes or an unkeyed public digest. Exact replay returns the prior immutable logical result;
same-key different material fails closed even when a caller-supplied test digest collides. Public
accepted mutation and manager-outcome results contain only closed workflow/classification enums and
the replay flag: no synthetic identity, timestamp, note, contact, snapshot, evidence, amount, or
command digest. Candidate state, minimized receipts, selector effects, and search authority are
staged and swapped together, so a failure on either side restores the prior state.

The mutation command carries factual interactions, snapshots, evidence, and governed replacement
inputs. Under the same lock, the accumulator recomputes the claimed evaluation with the fixed rule
pack and requires exact canonical-byte equality before accepting it. A discovery mutation's attached
snapshot and evaluation SnapshotId must exactly equal the selector-owned snapshot material validated
by the no-order reducer. Snapshot, interaction, evidence, and evaluation identities are globally
checked across active cases; an InteractionId may be shared only with exact material equality.
Appending any new classification-capable fact after an evaluation requires a cumulative replacement
evaluation in the same atomic command. The latest accepted evaluation is the sole classification
authority for manager outcomes and closure. Terminal no-order and no-replacement states cannot be
reopened.

Interactions, snapshots, evidence, and evaluations attach as deterministic set unions without
overwriting prior distinct facts. Placed value and manager outcomes are never counted twice. A
manager outcome is a separate explicit command and is accepted only from a workflow whose governed
exit permits a human decision or resolution. It can close a case but cannot mutate its system
classification. `PARTIAL` requires an exact approved amount, and `APPROVED` may carry the exact
amount when applicable; all five closed outcomes remain distinct.

Closure is a pure atomic projection in Milestone 2: build and verify the minimized
`ClosedAuditRecord`, then replace active detail in the in-memory accumulator. That sole order-case
survivor excludes contacts, active/raw notes, excerpts, full snapshots, line items, raw messages,
and customer-derived hashes. It retains only a closed concise-note code derived from the human or
terminal-system closure path. Active-detail objects are removed in the same closure swap. Keyed,
identity-indexed authenticators may survive only through the closed record's exact 90-day retention
window, and they preserve the same privacy-safe mutation or outcome result type for exact replay;
they are not public hashes and are deleted with the projection. No business persistence is created.
Closure reasons and the pre-close workflow are derived from the latest accepted evaluation; caller
input is only an expected-equality assertion. Automatic target-rep, verified-evidence, and
canceled-no-replacement order cases may close without fabricated manager authority.

A fully enumerated terminal `OrderSearchRun` whose derived outcome is
`REVIEW_WINDOW_CLOSED_NO_ORDER` is a separate retention root; it is never represented by inventing
an Order ID or `SalesCreditCase`. Its pure minimized `NoOrderClosedAuditRecord` derives the opening
instant and precision set from the exact included interactions, and derives closure time, latest
review-window end, trigger, enumeration counts, workflow, reason, adapter/schema versions, and
`REVIEW_WINDOW_CLOSED_NO_ORDER` concise-note code from the exact run. The survivor contains no run,
interaction, order, source, or contact identifier and no contact value, active note, warning, force
explanation, or reversible identity hash. Canonical bytes are verified under the dedicated
`sales-credit-no-order-closed-audit/v1` domain. `closed_at` is the terminal run completion instant,
so this root uses the same exact elapsed 90-day purge predicate without a fabricated later clock.
The no-order ledger deletes the terminal command's raw canonical bytes and contact-bearing active
receipts atomically with closure. To preserve same-command replay through that minimized boundary,
it retains only the opaque RunId-to-closure-receipt association and HMAC-SHA256 of the full canonical
command under a random process-local per-ledger secret. Exact `apply_run` material returns the prior
minimized result; changed material under the same RunId conflicts using constant-time authenticator
comparison. The authenticator is not a public hash domain, is not reversible without the secret,
and is purged with the closure receipt at the exact 90-day boundary. Distinct roots may have
identical identity-free projections because occurrence identity comes from their opaque closure
receipt IDs rather than aggregate projection equality.

The shared run authority retains full `OrderSearchRun` bytes only while the composed command can
still roll back. Successful commit replaces them with a keyed canonical authenticator and opaque
owner partitions. An all-positive run has a case partition, an all-negative run has only its
no-order partition, and a mixed run has both; no unused coordinator partition may survive. Exact
replay verifies the sealed run authenticator without acquiring a new raw owner, then requires exact
case-command and no-order component receipts. An identity-free empty no-order component remains
replayable while its positive case partition remains retained.

No-order state is partitioned by interaction root rather than by a whole combined result. When a
later governed search makes a previously negative root positive, the authority atomically splits
that root into an opaque case-owned partition. Each transferred root names only its target case
orders during active retention; an outgoing no-order partition remains while any negative or closed
no-order root still depends on it. The case side carries transferred partitions through active case
replay, closure, and the closed record's 90-day retention. A partition shared by several candidate
orders is released only after the last related projection is purged. At purge, all run/partition
links and any now-unneeded active selector snapshot bindings are deleted. A terminal no-order root
deletes its full selector snapshot and lines immediately; its keyed command authenticator alone
binds replay through D+90. No RunId, OrderId, interaction identity, or tombstone survives purge.

Sales Credit purge eligibility uses exact elapsed time: `now >= closed_at + 90 * 24 hours`.
The predicate and in-memory purge are idempotent. No case/order tombstone or reversible identity
hash survives a purge, including identity-bearing replay receipts.

Metrics consume immutable case/evaluation/outcome facts and emit aggregates only. Rates carry
explicit numerator and denominator values; an empty denominator is represented explicitly rather
than guessed. System results and human outcomes remain separate, and no metric contains contact,
order, interaction, evidence, note, or excerpt identity.

## Consequences

The M2 implementation proves replay and minimization behavior without pre-empting Milestone 4
database transaction design. A future persistent accumulator must preserve these byte comparison,
atomicity, deletion, and aggregate-only survivor rules under a new persistence ADR.
