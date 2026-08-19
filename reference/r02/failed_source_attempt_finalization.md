
> **Sanitized supporting reference.** This file is a mechanically sanitized derivative of
> source material supplied for the synthetic proof of concept. Historical status/freeze
> language is nonbinding. The curated files under `specs/` govern. No production-system
> access or real-data use is authorized by this reference.

# R02 Failed-Source-Attempt Explicit No-Retry Finalization Contract

Status: complete R02 v1.1 authoring; ready for independent audit; not frozen and not an integrated DOI specification.  
Package: `doi-authority-remediation-r02-ingestion-run/v1.1`  
Decision: `R02_FAILED_SOURCE_ATTEMPT_FINALIZATION = EXPLICIT_ACCEPTED_NO_RETRY_FINALIZATION`

## 1. Authority and behavioral boundary

The approved choice is incorporated exactly as the selected literal above. The rejected alternatives are immediate automatic failure, deterministic retry-window expiry, and any implicit or background finalization. The decision is not re-prompted.

After any qualifying `SOURCE_IMPORT_FAILED` terminal event commits, that attempt is final and immutable but its parent `RUN_DOI_REVIEW` remains `IN_PROGRESS` indefinitely. There is no timer, expiry, retry window, automatic transition, scheduler, background worker, or absence-of-retry test. The only two later accepted operations are:

1. a legal explicit next-ordinal source-import retry; or
2. the exact command `FINALIZE_FAILED_SOURCE_IMPORT_NO_RETRY`.

Both operations serialize under one run-scoped control lock. Lock/commit order is the sole winner authority. `accepted_action_at`, client clocks, UI order, worker order, and message arrival order never select a winner.

`ABORTED_PRE_OA` is retryable and never finalizable. A succeeded or nonterminal attempt is never finalizable.

## 2. Closed finalization command

The command schema/version and LF-terminated token domain are both:

```text
doi-finalize-failed-source-import-no-retry-command/v1\n
```

The exact command kind is:

```text
FINALIZE_FAILED_SOURCE_IMPORT_NO_RETRY
```

The complete command has exactly these 15 semantic members; every member is required and additional members are forbidden:

| Member | Exact rule |
|---|---|
| `finalization_command_schema_version` | literal `doi-finalize-failed-source-import-no-retry-command/v1` |
| `command_kind` | literal `FINALIZE_FAILED_SOURCE_IMPORT_NO_RETRY` |
| `run_id` | exact retained run ID |
| `run_type` | literal `RUN_DOI_REVIEW` |
| `expected_prior_run_status` | literal `IN_PROGRESS` |
| `latest_failed_source_import_attempt_id` | exact greatest retained failed attempt ID |
| `latest_failed_attempt_ordinal` | exact greatest ordinal; integer `>=1` |
| `latest_failed_attempt_outcome_class` | exactly one qualifying failed outcome |
| `latest_failed_attempt_terminal_event_id` | exact retained terminal event ID |
| `latest_failed_attempt_terminal_event_content_sha256` | exact retained lowercase SHA-256 |
| `explicit_user_acceptance` | literal `true` |
| `initiated_by_actor_id` | authorized internal non-customer `HUMAN` ID |
| `accepted_action_at` | canonical R01 `Timestamp`; provenance only |
| `user_action_evidence_schema_version` | literal `doi-user-accepted-run-action/v1` |
| `user_action_idempotency_key` | caller-generated non-customer opaque key |

The four qualifying outcome classes are `SCHEMA_REJECTED`, `SOURCE_CHANGED`, `INACCESSIBLE_OR_UNREADABLE`, and `BATCH_INTEGRITY_REJECTED`. `ABORTED_PRE_OA` and `SUCCEEDED` are forbidden. The five exact reason partitions, including the distinct `SOURCE_CHANGED` collision subbranch, are defined in the command schema and canonical vectors.

No command member may contain customer/order/workbook/source-cell/range/raw-token/OA content, a free-text reason, arbitrary metadata, a deadline, timer, timeout, expiry, or retention override.

## 3. Natural key, token, and known-answer test

The natural-key object is closed and contains exactly:

```json
{"finalization_command_key_schema_version":"doi-finalize-failed-source-import-no-retry-command-key/v1","user_action_idempotency_key":"<OpaqueId>"}
```

```text
finalization_command_key_sha256 = SHA256(
  UTF8("doi-finalize-failed-source-import-no-retry-command-key/v1\n") ||
  UTF8(RFC8785(complete_two_member_key_object))
)

finalization_command_token_sha256 = SHA256(
  UTF8("doi-finalize-failed-source-import-no-retry-command/v1\n") ||
  UTF8(RFC8785(complete_15_member_command))
)
```

Both domains end in exactly one LF byte. For raw key `SYN-R02-FINALIZE-CMD-0001`, the canonical key is 161 UTF-8 bytes and its final R02-only digest is:

```text
493d55b5a3e6ebc3270f5e4d143cf81a6fe2b4ec5c87903d4f4f7fa510623c46
```

The complete token is `DEFERRED_TO_R01_R02_INTEGRATION` because the command contains the R01 `accepted_action_at` Timestamp. Hashing a placeholder is forbidden.

The raw accepted-action idempotency-key value is globally resolvable and unique across every retained run-control command receipt family: run invocation (`user_action_idempotency_key`), every source-attempt command ordinal including initial and retry (`attempt_command_idempotency_key`), and failed-source finalization (`user_action_idempotency_key`). Domain-specific key objects and digests remain distinct, but digest-only or family-only lookup cannot evade the global raw-value check. Concurrent creators use one shared cross-family lock namespace keyed by raw value and hold that value's lock through transactional reservation before any family-specific allocation; equal values serialize globally while distinct values may proceed to their owner locks.

## 4. Closed retained receipt

The logical receipt version is `doi-finalize-failed-source-import-no-retry-command-receipt/v1`. It retains exactly the closed members in `R02_FAILED_SOURCE_ATTEMPT_FINALIZATION_COMMAND_SCHEMA.json`: allocated receipt ID; exact raw key; canonical key bytes; canonical complete command bytes; key/token digests; run ID; all five greatest-failed-attempt binding fields; and the resulting `RUN_TERMINAL` event ID/hash.

The receipt ID is allocated only after replay lookups and locked guards succeed. To avoid a hash cycle, allocate the receipt ID, construct/hash the terminal event containing receipt ID/key/token, then persist the receipt with the resulting event ID/hash in the same atomic transaction. The receipt has no independent content hash.

## 5. Mandatory lookup and guard order

The order is normative:

1. validate only the closed command shape, literals, primitive types, canonical R01 Timestamp syntax/bytes and required evidence-field presence; current actor authorization is deliberately not resolved before identity replay;
2. canonicalize the exact key and command and compute both digests;
3. acquire and hold the candidate raw value's lock in the shared cross-family accepted-action-key lock namespace; look up that raw value across retained invocation, all-ordinal source-attempt command and finalization receipts, then look up the family-specific key and token digests;
4. byte-compare raw and canonical preimages, recompute digests, and return an exact retained replay unconditionally from retained command/evidence/result bytes before mutable authorization or run-state guards; otherwise resolve conflict/collision;
5. for a fresh command only, transactionally reserve the global raw value and family key/token identities while holding that raw-value lock, then acquire the common run-control lock; every later guard failure rolls the reservations back;
6. resolve current authorized-internal-HUMAN authority, then re-resolve the run, status, greatest accepted ordinal, terminal attempt/event bytes, retry reservation, prior receipt, batch and all downstream/OA guards;
7. validate the exact five-field binding and one permitted reason partition; and
8. only then allocate receipt/event IDs, trusted transaction time, timezone/tzdb and deadline and perform the atomic commit.

Exact replay lookup precedes the terminal-state guard. A byte-identical winning command replay after terminalization returns the original receipt, terminal event and run, and allocates nothing. Same raw key with changed valid command bytes is `[RC-111]`. Equal digest text with unequal corresponding bytes, or index disagreement proving that condition, is `[RC-103,RC-111]`. A fresh key against terminal, stale, later-retry, wrong-run, unsafe, or otherwise ineligible state is `[RC-081]`. `RC-103` never means merely different content. No new reason code is introduced.

## 6. Locked positive guards

A fresh finalization is legal only when all are true under the lock:

- the retained object is an existing `RUN_DOI_REVIEW` in `IN_PROGRESS` with no terminal event;
- all accepted source-attempt streams are terminal and none succeeded;
- the referenced attempt is the greatest accepted ordinal and has one of the four qualifying failure outcomes;
- attempt ID, ordinal, outcome, terminal event ID and terminal event hash are exact;
- the attempt reason set is exactly one permitted partition;
- no later retry/reservation and no non-replay finalization receipt exists;
- the run has null source batch and zero work, case, snapshot, evaluation, intervention and OA state; and
- explicit acceptance is true and the actor is an authorized internal human.

Any guard failure produces zero receipt/event/time/deadline effects and uses `[RC-081]` unless the earlier identity-collision matrix supersedes it.

## 7. Retry/finalization race

Retry-first: a legal retry for ordinal `n+1` commits its receipt/reservation/start/count update while holding the common lock. The finalizer re-resolves greatest ordinal `n+1`, rejects `[RC-081]`, creates no receipt or terminal event, and leaves the run `IN_PROGRESS`.

Finalize-first: the finalizer atomically commits the receipt, one terminal event, projection and retention effects. The run becomes `FAILED`. A later retry re-resolves terminal status, rejects `[RC-081]`, and creates no ordinal `n+1` attempt.

Unique constraints and the common lock make both winners impossible. Replaying the exact winning command returns its retained winner. After a later retry itself fails, a new intentional finalization MUST use a fresh caller key and bind that new greatest failure. `[RC-111]` applies only when the submitted raw key resolves to an actually retained invocation, source-attempt, or finalization receipt with different command bytes—for example, reuse of the committed retry key across families. A losing finalizer that rolled back with `[RC-081]` leaves no receipt, key/token reservation or tombstone, so the service does not claim retained-key conflict authority for that uncommitted submission; current locked state/binding guards govern it.

## 8. RUN_TERMINAL payload and atomic transaction

No event enum changes. `RunEventType` remains exactly `RUN_INVOCATION_ACCEPTED | RUN_TERMINAL`; `SourceImportAttemptEventType` remains exactly the four existing literals. Finalization adds no source-attempt event and no third run event.

The run event remains `doi-run-event/v3`; only its terminal payload shape is versioned to `doi-run-terminal-payload/v3`. Its required nullable `failed_source_import_finalization_binding` is non-null only for this branch. That closed 10-member object binds the exact trigger `EXPLICIT_FAILED_SOURCE_IMPORT_NO_RETRY`, receipt ID/key/token, and five greatest-failed-attempt fields. Every other terminal branch carries null.

The terminal event is sequence 2, predecessor-bound to sequence 1, exactly once, with `SYSTEM`, `SYSTEM_VERIFIED`, and null `actor_id`. Human evidence stays in the receipt. Its payload has prior `IN_PROGRESS`, result `FAILED`, exact copied attempt reasons, null batch, zero work/evaluation/exception/block/OA counts, accepted-attempt count equal to the number of contiguous STARTED streams, and trusted terminal/deadline values.

The locked transaction performs these exact 13 directive effects atomically:

1. persist the finalization command receipt;
2. append exactly one sequence-2 `RUN_TERMINAL`;
3. reduce the run projection `IN_PROGRESS -> FAILED`;
4. set one trusted transaction-clock `completed_at`;
5. set terminal occurrence/recording semantics consistently with existing event authority;
6. compute `run_purge_eligible_at=calendar90(completed_at)` from the exact retained R01 calendar/retention binding;
7. set every associated attempt's required parent-terminal retention tuple, including purge eligibility byte-equal to the run deadline;
8. preserve every failed attempt's committed immutable terminal event bytes and hash;
9. copy the greatest failed attempt's exact permitted reason-code set;
10. preserve `source_batch_id=null`;
11. preserve zero OA reads and zero downstream work;
12. prevent a second terminal event; and
13. bind receipt, run event, projection and retention effects in one rollback-safe transaction.

Failure injected after any named effect restores the complete prior state byte-for-byte and exposes no receipt, event, projection, time, tzdb or deadline residue. A generic storage failure invents no DOI reason.

## 9. Clock, retention, deletion and privacy

`accepted_action_at` is canonical R01 provenance only. The trusted locked transaction assigns terminal time consistently with run-event authority; accepted-action time never supplies `completed_at`, `occurred_at`, `recorded_at`, winner ordering, or the retention anchor. `calendar90` derives only from trusted `completed_at`.

The receipt is identifying run-control detail owned one-to-one by `run_id`. It participates in replay from commit until governed run-detail deletion and cannot outlive the run. It creates no independent retention reference and cannot move or extend the common deadline. Receipt, raw/canonical preimages, key/token indexes, failed-attempt binding and reverse event lookup delete atomically with the run-detail graph. No tombstone, nonidentifying aggregate, log, cache, dead letter, export or backup copy survives. After deletion, the missing-run guard prevents recreation; no tombstone is consulted.

Every associated attempt projection receives the common terminal tuple while all attempt event bytes and hashes remain unchanged. The command, receipt, terminal binding and projection contain no customer identity, OrderNumber, workbook row, raw source/cell/range/token, free text, OA fact, timeout, timer, expiry or arbitrary metadata. `source_batch_id` remains null and all downstream/OA counts remain zero.

## 10. Deferral, downstream and audit boundary

The two-member key KAT is final. The complete command token, R01-bearing failed-attempt hashes, resulting terminal hashes, trusted time/deadline and overlay-equality KATs remain exactly `DEFERRED_TO_R01_R02_INTEGRATION`. R02 does not redefine Timestamp, business calendar, timezone or retention authority.

R06 later owns physical schema/index/transaction/deletion design. This contract authorizes no DDL, migration, implementation, repository change, cache refresh, manager-workbook access, corpus change, or live Synthetic Order Portal access. Independent R02 audit remains required; the package is not frozen and does not make Checkpoints 04–11 implementation-ready.
