
> **Sanitized supporting reference.** This file is a mechanically sanitized derivative of
> source material supplied for the synthetic proof of concept. Historical status/freeze
> language is nonbinding. The curated files under `specs/` govern. No production-system
> access or real-data use is authorized by this reference.

# R02 RunType State Machines and One-Order Rule

Status: complete R02 v1.1 authoring; `DOI-FWD-B018` and `DOI-FWD-N002` are closed; ready for independent audit; not frozen or integrated.  
Run projection schema: `doi-run/v3`  
Run event schema dependency: `doi-run-event/v3`

## 1. Scope, common machine, and R01 dependencies

The frozen `RunType` domain remains exactly:

```text
RUN_DOI_REVIEW | RECHECK_ORDER | RECHECK_DEDUPE_ORDER
```

The common `RunStatus` remains exactly:

```text
IN_PROGRESS | COMPLETED | COMPLETED_WITH_EXCEPTIONS | FAILED
```

This document closes both recheck machines and every review path, including the approved explicit accepted no-retry finalization after a qualifying terminal failed source attempt. It does not force the manager-source invocation payload onto either recheck. It references, without redefining, R01 `Timestamp`, `OrderNumber`, business-calendar, fake-OA factual-boundary, and related content-hash authority. A final vector containing an unresolved R01 value remains `DEFERRED_TO_R01_R02_INTEGRATION`.

### 1.1 Approved failed-source finalization decision

```text
R02_FAILED_SOURCE_ATTEMPT_FINALIZATION = EXPLICIT_ACCEPTED_NO_RETRY_FINALIZATION
COMMAND_KIND = FINALIZE_FAILED_SOURCE_IMPORT_NO_RETRY
```

After any qualifying `SOURCE_IMPORT_FAILED` attempt commits independently, the parent remains `IN_PROGRESS` without timer, expiry, window, automatic transition or background action. A later explicit legal next-ordinal retry or the exact explicit finalization command may proceed. Both acquire the same run-scoped control lock covering status, greatest ordinal, retry reservation and finalization. Lock/commit order is the only winner authority; user/client timestamps, UI order and worker/message arrival order are ignored.

Retry-first commits the new ordinal receipt/reservation/start/count update and makes the stale finalizer reject `[RC-081]`, leaving the run `IN_PROGRESS`. Finalize-first atomically creates the finalization receipt, appends exactly one `RUN_TERMINAL`, reduces `IN_PROGRESS -> FAILED`, assigns trusted terminal time and calendar90 deadline, overlays all attempts, and makes a later retry reject `[RC-081]`. Exact replay lookup occurs before the terminal-state guard and returns the original winner. `ABORTED_PRE_OA` remains retryable and is never finalizable.

The rejected alternatives are immediate automatic failure, deterministic retry-window expiry and implicit/background finalization. No new RunStatus, transition ID, reason code or event type is introduced.

## 2. Closed common `DOIRunV3` projection

Every run projection contains exactly:

| Member | Type / rule |
|---|---|
| `business_calendar_version` | non-null `VersionId`; exact requested/final R01 binding required for every current RunType and its terminal retention deadline |
| `blocked_order_count` | integer `>=0`; R02 count-contract equation |
| `completed_at` | R01 `Timestamp` or null iff `IN_PROGRESS`; terminal value is transaction-assigned and `>= started_at` and every committed subordinate terminal timestamp reduced into the run terminal under the R01 ordering contract |
| `extractor_version` | non-null exact `VersionId` |
| `initiated_by_actor_id` | nonempty internal actor ID |
| `normal_evaluation_succeeded_count` | integer `>=0`; R02 count-contract equation |
| `oa_read_count` | integer `>=0`; R02 count-contract equation |
| `order_exception_count` | integer `>=0`; R02 count-contract equation |
| `reason_codes` | exact registered set under sections 5–7 |
| `rules_engine_version` | non-null exact `VersionId` |
| `run_context` | one closed subtype from section 3 |
| `run_id` | `OpaqueId` |
| `run_invocation_command_token_sha256` | exact retained command token |
| `run_invocation_key_sha256` | exact retained global invocation key |
| `run_purge_eligible_at` | R01 `Timestamp` or null iff `IN_PROGRESS`; terminal value is exact bound R01 `calendar90(completed_at)` |
| `run_schema_version` | literal `doi-run/v3` |
| `run_type` | exact discriminator matching `run_context` |
| `source_import_attempt_count` | section 4 exact integer |
| `started_at` | non-null R01 `Timestamp` assigned once after command lookup |
| `status` | common `RunStatus` |
| `work_item_count` | integer `>=0`; distinct retained run-work-item equation |

No attempt ID/list/manifest, source row, customer data, free text, OA content, or command canonical bytes appears in the projection. Canonical command bytes live only in the retained command receipt. Status is reduced from exactly one v3 invocation event and at most one v3 terminal event. Subordinate records provide active work detail; the terminal event binds the exact final counts.

## 3. Closed run contexts

### 3.1 Manager review context

Schema `doi-run-doi-review-context/v1`, containing exactly:

| Member | Rule |
|---|---|
| `context_schema_version` | literal `doi-run-doi-review-context/v1` |
| `schema_mapping_version` | exact `synthetic-doi-queue-v0.1` |
| `selected_source` | exact closed `{gid,role,spreadsheet_id,title}` from invocation |
| `source_batch_id` | null on invocation and FAILED; non-null on completed states; may become non-null while active only after successful coherent import |

There is no single requested case/order or DEDUPE-review target in this context.

### 3.2 Recheck Order context

Schema `doi-recheck-order-context/v1`, containing exactly:

| Member | Rule |
|---|---|
| `case_id` | exact retained target |
| `context_schema_version` | literal `doi-recheck-order-context/v1` |
| `requested_case_lifecycle_state` | locked invocation value `ACTIVE \| CLOSED_REVERSIBLE` |
| `requested_case_projection_hash` | locked invocation hash |
| `requested_case_revision` | locked invocation revision `>=1` |
| `requested_order_number` | exact canonical R01 OrderNumber; byte-equal case/work item |
| `requested_order_number_contract_version` | exact R01 version |
| `schema_mapping_version` | explicit null |
| `selected_source` | explicit null |
| `source_batch_id` | explicit null |
| `target_attention_cause_key_sha256` | invocation value, null/non-null with SET event |
| `target_attention_set_event_id` | invocation value, null/non-null with cause key |

### 3.3 Recheck DEDUPE context

Schema `doi-recheck-dedupe-order-context/v1`, containing exactly:

| Member | Rule |
|---|---|
| `case_id` | exact retained target |
| `context_schema_version` | literal `doi-recheck-dedupe-order-context/v1` |
| `current_dedupe_state` | locked `HUMAN_APPROVED_AWAITING_OA_VERIFICATION \| CONFIRMED` |
| `dedupe_review_id` | exact retained review |
| `dedupe_state_event_content_sha256` | exact retained event hash |
| `dedupe_state_event_id` | exact retained event ID |
| `requested_case_lifecycle_state` | ACTIVE for awaiting; CLOSED_REVERSIBLE for confirmed |
| `requested_case_projection_hash` | exact locked hash |
| `requested_case_revision` | exact locked revision `>=1` |
| `requested_order_number` | exact canonical R01 OrderNumber |
| `requested_order_number_contract_version` | exact R01 version |
| `schema_mapping_version` | explicit null |
| `selected_source` | explicit null |
| `source_batch_id` | explicit null |

Every recheck context value and the manager-review `context_schema_version`, `schema_mapping_version`, and `selected_source` are immutable. The sole context reducer is the manager-review projection's `source_batch_id`: it changes once from null to the byte-equal successful attempt batch only in the source-success transaction defined below. The retained command and immutable invocation-event context remain unchanged with null `source_batch_id`; exact replay changes no projection byte. A later recheck target-state change is handled by the work transaction or a fresh invocation and never rewrites its retained command/context.

## 4. Cross-RunType invariants

| Invariant | `RUN_DOI_REVIEW` | `RECHECK_ORDER` | `RECHECK_DEDUPE_ORDER` |
|---|---:|---:|---:|
| explicit accepted user action | exact confirmed manager tab | exact retained case/order recheck | exact retained DEDUPE case/order/review recheck |
| manager source/tab | required | forbidden/null | forbidden/null |
| source batch | required for completed status; null initially/FAILED | always null | always null |
| `source_import_attempt_count` | number of accepted ordinals, `>=1` | exactly `0` | exactly `0` |
| source-import-attempt events | one start+terminal chain per accepted ordinal | none | none |
| valid invocation `work_item_count` | initially `0`; terminal count from successful import/reconciliation | exactly `1` from invocation onward | exactly `1` from invocation onward |
| requested case/order in run context | absent | required | required |
| case admission proof on work | manager work required; source-absence work null | null | null |
| work origin | `MANAGER_TARGET_REP_ROW \| SOURCE_ABSENCE_VERIFICATION` | `MANUAL_RECHECK` | `DEDUPE_RECHECK` |
| extraction occurrences | zero/one per distinct work item | zero or one; exactly one only if executable work reaches occurrence reservation before a run-global pre-read failure | zero or one; exactly one only if executable work reaches occurrence reservation before a run-global pre-read failure |
| implicit/background retry | forbidden | forbidden | forbidden |

A new recheck command is validated under its retained-case lock before receipt/run/time/event/work allocation. Absent purged case `RC-086`, target/state/revision/proof mismatch `RC-081`, unavailable required rules version `RC-084`, or unsafe/unallowlisted read boundary `RC-083` yields a transient rejection, zero run/work/read, and no persistent order-specific record. An exact replay of a retained command returns the existing run before current-target revalidation.

## 5. `RUN_DOI_REVIEW` machine

### 5.1 Invocation and active state

Required user action: explicitly accept `Run DOI Review` with exactly one locked tab tuple. An unconfirmed suggestion is RC-001 and creates nothing.

One atomic valid invocation transaction creates:

- one command receipt and `DOIRunV3`/`RUN_INVOCATION_ACCEPTED` in `IN_PROGRESS`;
- `source_import_attempt_count=1`;
- ordinal-1 source-attempt command receipt and `SOURCE_IMPORT_STARTED`;
- `work_item_count=normal_evaluation_succeeded_count=order_exception_count=blocked_order_count=oa_read_count=0`;
- null `source_batch_id`, `completed_at`, and `run_purge_eligible_at`; and
- empty run reason set.

Later source attempts use only the exact next-ordinal command machine. After `ABORTED_PRE_OA` or any qualifying `SOURCE_IMPORT_FAILED`, a legal explicitly accepted next-ordinal retry is constructible while the parent remains `IN_PROGRESS`; it must win the common run-control lock before finalization. Each accepted retry increments the run attempt count exactly once. All accepted attempts must be terminal before finalization; none may have succeeded. If one attempt succeeds it is greatest/last and every later retry or failed-source finalizer is illegal.

### 5.2 Source failure/abort branches

| Attempt outcome | Parent effect after attempt commit | Later legal operations / reasons |
|---|---|---|
| `ABORTED_PRE_OA` | remains `IN_PROGRESS`; no deadline | explicit next ordinal required; abort cannot finalize; `[]` |
| `SCHEMA_REJECTED` | remains `IN_PROGRESS`; null batch/zero downstream/OA | retry or explicit finalization may win lock; `[RC-002,RC-090]` |
| ordinary `SOURCE_CHANGED` | same | retry or explicit finalization; `[RC-009,RC-090]` |
| `SOURCE_CHANGED` with proved technical-digest collision | same | retry or explicit finalization; `[RC-009,RC-090,RC-103]` |
| `INACCESSIBLE_OR_UNREADABLE` | same | retry or explicit finalization; `[RC-089,RC-090]` |
| `BATCH_INTEGRITY_REJECTED` | same | retry or explicit finalization; `[RC-090,RC-091]` |

Every failed-attempt terminal event commits independently and remains byte/hash immutable. It creates no parent terminal event, receipt, completion time or deadline. The later finalizer must bind the locked greatest terminal failure by exact attempt ID, ordinal, outcome, terminal event ID and terminal event hash, copy its exact reason set, and prove all attempts terminal/none successful/null batch/zero work-case-snapshot-evaluation-intervention-OA. A stale or later-retry binding rejects `[RC-081]` with no effects.

### 5.3 Successful source and work allocation

The successful source-import transaction binds one coherent batch, finalizes all source counts, creates attempt-local staged/rejected state, and atomically changes the prior-null `DOIRunV3.run_context.source_batch_id` to the same opaque ID as the successful attempt's `bound_source_batch_id`. No top-level `source_batch_id` member exists in `DOIRunV3`; the later `RUN_TERMINAL` payload carries a byte-equal event alias derived from the nested context, while the immutable invocation-event alias remains null. Exact source-success replay changes no parent byte; failure at any component rolls back the attempt terminal, batch/reference/staged/rejected records, and parent binding together, leaving the prior STARTED attempt and null parent binding intact.

Only after that sole successful transaction may run work be allocated. Under the parent-run lock plus all affected staged/rejection/case/order locks, the allocator derives the complete work set exactly once from the committed batch and current qualifying retained cases:

- one `MANAGER_TARGET_REP_ROW` work item for each unconflicted distinct staged TARGET_REP Order Number; and
- one `SOURCE_ABSENCE_VERIFICATION` work item for each qualifying retained active TARGET_REP case absent from the coherent batch.

The allocation transaction inserts the entire missing set of unique `(run_id,order_number)` work rows and atomically sets active `DOIRunV3.work_item_count = |W(run)|`, reduced from the committed work rows rather than a caller subtotal. It commits the complete set/count or neither; a failure leaves the already committed source success and parent batch binding intact but exposes no partial work subset or count and performs zero OA reads. Exact allocation replay re-locks/reduces the same set, returns the retained work rows, and changes the parent count by zero. Extraction-occurrence reservation and every OA dispatch are forbidden until this allocation boundary commits.

A conflicted TARGET_REP Order Number creates one RC-008 no-case rejection record and no work item/OA read. Compatible duplicate TARGET_REP rows merge into the same manager work key. The complete one-order rule is section 8.

Each executable work item reserves at most one extraction occurrence. Manager work proves/creates or reuses the retained case/admission proof before extraction. Source absence by itself never closes a case; its exact verification produces a complete snapshot/evaluation/closure outcome or an extraction failure/recheck attention.

### 5.4 Terminal classification

| Status | Exact guards | Exact run reason set |
|---|---|---|
| `COMPLETED` | coherent batch non-null; all work terminal; exception/block counts 0 | `[]` |
| `COMPLETED_WITH_EXCEPTIONS` | coherent batch non-null; all work terminal; at least one unique exception/block | section 9 union |
| `FAILED` | only exact accepted `FINALIZE_FAILED_SOURCE_IMPORT_NO_RETRY` against the locked greatest qualifying failed attempt, or the separately closed recheck systemic branch | review: exact bound failed-attempt partition; recheck: `[RC-084]` |

Review FAILED has null batch, source-attempt count equal to accepted STARTED streams, all attempts terminal, none succeeded, and all work/evaluation/exception/block/OA counts zero. Its `doi-run-terminal-payload/v3` carries a non-null exact finalization binding; every other terminal branch carries null. No individual bad order, assignee conflict, extraction/evaluation failure after work, event collision after read, or zero normal evaluations converts a coherent run to FAILED. All-blocked and all-extraction-failed coherent runs are `COMPLETED_WITH_EXCEPTIONS`.

## 6. `RECHECK_ORDER` machine

### 6.1 Invocation/guards

Required user action: explicitly accept `Recheck Order` for one exact retained case/order. There is no throttle and no manager source. The invocation command, requested version/read-boundary, exact case/order, lifecycle state, revision/hash, and optional active attention cause are all validated before allocation.

One valid atomic invocation creates one IN_PROGRESS run and exactly one work item with:

```text
origin = MANUAL_RECHECK
case_id = requested case
order_number = requested canonical OrderNumber
case_source_admission_proof_id = null
source_batch_id = null
execution_allowed = true
source_import_attempt_count = 0
work_item_count = 1
normal_evaluation_succeeded_count = 0
order_exception_count = 0
blocked_order_count = 0
oa_read_count = 0
reason_codes = []
```

No source-attempt event, manager range, batch reference, staged order, or rejected source record is legal.

### 6.2 Read/work branches

If the exact pre-read authority/version guard remains available and work reaches reservation, the sole work item creates exactly one extraction occurrence. If the later run-global pre-read guard fails first, the work item has zero occurrences. Only the exact R01 fake fixture or separately frozen read-only OA adapter may supply facts. No task in this R02 package executes a live read.

| Branch | Atomic effects | Terminal status/counts | Run reasons |
|---|---|---|---|
| complete extraction + accepted evaluation, no order exception | one new snapshot/evaluation; apply legal case transitions; clear the exact targeted active RECHECK_REQUIRED cause only when its resolver is this evaluation; preserve other causes | `COMPLETED`; work 1, evaluation-success 1, exception 0, blocked 0; actual allowed read count | `[]` |
| complete extraction + accepted evaluation when no target cause was supplied/already resolved | append facts/evaluation; no spurious CLEAR | `COMPLETED`; 1/1/0/0 | `[]` |
| extraction FAILED | no snapshot/evaluation; SET/retain cause-keyed RECHECK_REQUIRED | `COMPLETED_WITH_EXCEPTIONS`; work 1, evaluation-success 0, exception 1, blocked 0 | exact extraction work set in section 9 |
| snapshot succeeds but exact evaluation version/binding fails | preserve accepted snapshot; no substitute evaluation | `COMPLETED_WITH_EXCEPTIONS`; work 1, evaluation-success 0, exception 1, blocked 0 | one exact singleton `[RC-084]`, `[RC-105]`, or `[RC-106]` |
| post-read work/lifecycle transaction rejects | roll back that affected transaction; preserve earlier accepted bytes | `COMPLETED_WITH_EXCEPTIONS`; work 1, exception 1, blocked 0; evaluation-success 0 unless an evaluation already committed, in which case 1 | exact section 9 integrity partition |
| after valid invocation but before extraction-occurrence reservation or any read, the exact rules/authority version that resolved during invocation becomes systemically unavailable | no occurrence/read/snapshot/evaluation | `FAILED`; work 1, evaluation 0, exception 0, blocked 0, OA 0 | exactly `[RC-084]` |

A complete recheck may leave ACTIVE, close hard/reversibly under existing proof rules, leave the same reversible closure without resetting its deadline, or reopen the same retained reversible case with the complete required prior-closure binding. It never creates a second case. `CLOSED_HARD` is not a legal invocation target for this RunType.

### 6.3 Retry/idempotency

An exact invocation/occurrence replay returns the retained run/attempt/snapshot outcome. A failed or successful extraction never gets a second attempt within this run. A new business recheck requires a new explicit user action/key, a new run, one new work item, and one new occurrence; all prior bytes remain immutable.

## 7. `RECHECK_DEDUPE_ORDER` machine

### 7.1 Invocation/guards

Required user action: explicitly accept `Recheck DEDUPE Order` for one retained case/order and exact retained DEDUPE review/current-state event.

Before any allocation, one lock proves either:

1. `HUMAN_APPROVED_AWAITING_OA_VERIFICATION`, ACTIVE case, and exact approval review/event; or
2. `CONFIRMED`, CLOSED_REVERSIBLE case whose closure is `DEDUPE_CONFIRMED`, and exact current review/event.

Human approval alone never proves the OA note. A note observation never constructs approval. A purged case is transient RC-086; every other binding/state mismatch is transient RC-081. Both create no run/receipt/work/read.

One valid invocation creates one IN_PROGRESS run and one work item with `origin=DEDUPE_RECHECK`, exact case/order, null admission proof/batch, `source_import_attempt_count=0`, `work_item_count=1`, `normal_evaluation_succeeded_count=0`, `order_exception_count=0`, `blocked_order_count=0`, `oa_read_count=0`, and empty reasons.

### 7.2 Complete/failure branches

| Starting proof | Complete read result | Required case/DEDUPE effect | Terminal run |
|---|---|---|---|
| awaiting OA verification | independently verified DEDUPE note | append system verification only; transition to CONFIRMED; reversible `DEDUPE_CONFIRMED` closure and deadline | `COMPLETED`, counts 1/1/0/0, reasons `[]` |
| awaiting OA verification | no independently verified note | remain ACTIVE/awaiting; set/retain RECHECK_REQUIRED; no close/merge | `COMPLETED_WITH_EXCEPTIONS`, work 1/evaluation-success 1/exception 1/blocked 0, reasons `[RC-015]` |
| CONFIRMED reversible closure | source-grounded DOI eligibility returned | append complete snapshot/evaluation; transition DEDUPE to NOT_CANDIDATE; reopen same case and cancel exact deadline through required prior binding | `COMPLETED`, 1/1/0/0, reasons `[]` |
| CONFIRMED reversible closure | same closure still proved | append current complete facts as governed; do not reset/extend deadline | `COMPLETED`, 1/1/0/0, reasons `[]` |
| CONFIRMED reversible closure | SHIPPED or full CANCELED proved | transition same case to hard closure; restart exact deadline under existing authority | `COMPLETED`, 1/1/0/0, reasons `[]` |
| either | extraction FAILED | no snapshot/evaluation/closure; SET/retain RECHECK_REQUIRED | `COMPLETED_WITH_EXCEPTIONS`, work 1/evaluation-success 0/exception 1/blocked 0, extraction set from section 9 |
| either | snapshot accepted but evaluation unavailable/incomplete/hash-mismatched | no substitute evaluation/closure | `COMPLETED_WITH_EXCEPTIONS`, work 1/evaluation-success 0/exception 1/blocked 0, singleton `[RC-084]`/`[RC-105]`/`[RC-106]` |
| either | post-read work/lifecycle transaction rejects | roll back that affected transaction; preserve earlier accepted bytes | `COMPLETED_WITH_EXCEPTIONS`, work 1/exception 1/blocked 0; evaluation-success 0 unless a normal evaluation already committed, then 1; exact section 9 integrity set |
| either | later systemic loss of the exact rules/authority version after valid invocation but before extraction-occurrence reservation or any read | no occurrence/read/snapshot/evaluation | `FAILED`, work 1/eval 0/exception 0/blocked 0/OA 0, exactly `[RC-084]` |

Actual allowed read count is the exact count-contract result. DEDUPE recheck writes nothing to OA, never merges cases, and never persists note text. Exact replay returns the same run/outcome; another recheck needs a fresh accepted run/work/occurrence.

## 8. N002 exact one-order/run-key correction

The normative rule is:

> Within one retained run, one exact canonical Order Number owns at most one `DOIRunOrderWorkItem`. The immutable natural key is exactly `(run_id,order_number)`.

The complete reconciliation is:

1. Source-row duplicates are not work items. Within a successful import attempt, compatible TARGET_REP rows first merge to one `DOIStagedOrder` under `(source_import_attempt_id,order_number)` and RC-006.
2. Source-import attempts remain independently owned. A later legal ordinal can observe the same source number, but only the run's sole successful greatest ordinal may create a batch/staged set/work. Every earlier legal attempt is failed/aborted and creates no staged order or work. Thus cross-attempt observations never require or permit two run work items.
3. When successful staging becomes work, all duplicate refs disappear behind one `(run_id,order_number)` work item. The work item never retains an attempt/staged-row locator.
4. A same-number TARGET_REP/non-TARGET_REP assignment conflict creates no staged order/work item. It owns one attempt-local RC-008 rejection record and contributes one unique order exception/block.
5. Source-absence work and manager-present work are mutually exclusive for the same canonical number in the same coherent run. The presence reconciliation is locked before work insertion; the run/order unique key is the final guard.
6. Each valid recheck run has exactly one work item for its requested number; a different explicit recheck is a different run and therefore a different work key.
7. Across runs, the same canonical number may own one work item in each run while resolving to the same retained `DOIOrderCase`. No work or source locator is reused.
8. After case purge, a manager review may create a new unlinked case under ordinary admission. A case-targeted recheck is rejected RC-086 and cannot reconstruct it.
9. Reusing a `DOISourceBatch` never reuses a run, attempt, staged record, SourceRef, work item, extraction attempt, or snapshot. It only reuses the immutable byte-identical batch.

The contradictory sentence in baseline `SYN-SRC-013` is replaced by:

> Three compatible duplicate TARGET_REP rows in the sole successful source-import attempt create one attempt-scoped staged record and one run-scoped work/extraction path. A prior non-success attempt may have observed the same number but created no staged/work row. Staged uniqueness is `(source_import_attempt_id,order_number)`; work uniqueness is `(run_id,order_number)`. A distinct run may create its own work item and reuse the same retained case; source-batch reuse never reuses work.

No broader case, staging, or retention rule changes.

## 9. Exact R02 order-exception reason partitions

For `COMPLETED_WITH_EXCEPTIONS`, the run reason set is the ascending set union of the exact per-order sets below, once per unique exceptioned Order Number; it is not a count and never duplicates a code:

| R02 order disposition | Exact per-order reason set |
|---|---|
| manager assignee conflict/no work | `[RC-008]` |
| ordinary extraction failure | `{RC-014,RC-015}` plus a nonempty subset of `{RC-011,RC-012,RC-013}` |
| source-absence extraction failure | ordinary extraction set plus `RC-010` |
| complete DEDUPE recheck with no verified note | `[RC-015]` |
| evaluation version unavailable | `[RC-084]` |
| evaluation provenance incomplete | `[RC-105]` |
| evaluation bound hash mismatch | `[RC-106]` |
| illegal subordinate state edge | `[RC-081]` |
| proven non-stream content/key digest collision | `[RC-103]` |
| immutable stream/key conflict without proven collision | `[RC-111]` |
| immutable stream/key conflict with proven collision | `[RC-103,RC-111]` |
| lifecycle schema/serialization rejection | `[RC-113]` |

RC-006 is staged-record audit provenance and is not a run exception. Evaluation business results such as monitor/opportunity/manual-review/closure codes remain in their owning evaluation/lifecycle records and are not run exceptions merely because the business result is not an opportunity. RC-090 is exclusive to source-import failure and never appears on a coherent completed run.

## 10. Events, projection reduction, and transaction boundaries

`doi-run-event/v3` retains exactly two event types: `RUN_INVOCATION_ACCEPTED` at sequence 1 and optional `RUN_TERMINAL` at sequence 2. Both carry the exact command identities; payloads are closed per RunType. Same event identity/bytes replay is a no-op; changed identity/sequence/predecessor is RC-111, with RC-103 added only for proven digest collision.

Required transaction boundaries are:

1. Review invocation: run receipt/start plus ordinal-1 attempt receipt/start, atomic.
2. Valid recheck invocation: run receipt/start plus sole work item, atomic.
3. Source-attempt retry start: after `ABORTED_PRE_OA` or qualifying `SOURCE_IMPORT_FAILED`, lock/re-resolve parent IN_PROGRESS and exact greatest terminal binding; atomically commit next-ordinal reservation/receipt/start plus `source_import_attempt_count := count(accepted SOURCE_IMPORT_STARTED streams)`. Exact replay has zero delta. The same lock serializes finalization; winner is commit order only.
4. Review source/work uses two ordered atomic boundaries. **4a source success/batch binding:** terminal attempt event/projection, coherent batch/reference, exact source counts, staged/rejected records, and the parent `run_context.source_batch_id := bound_source_batch_id` reducer commit or roll back together; exact replay has parent-binding delta zero. **4b work allocation:** after 4a, lock the run and all affected staged/rejection/case/order keys, derive the complete exact `W(run)` set, insert its unique work rows, and set `DOIRunV3.work_item_count := |W(run)|` in one transaction; exact replay delta is zero, rollback exposes neither a partial work set nor a changed count, and no extraction reservation/OA dispatch may precede its commit.
5. Extraction reservation: one occurrence/attempt reservation per work, atomic and before dispatch.
6. Extraction failure: terminal FAILED attempt plus attention SET, atomic; no snapshot/evaluation.
7. Extraction success: one transaction performs exactly five R02-owned effects/guards: (a) revalidate exact identity and whole-order proof on the retained STARTED occurrence/attempt/work tuple; (b) construct the one complete R01-governed snapshot and hashes and allocate its `snapshot_id` only after re-proving no snapshot exists; (c) insert that snapshot with the required unique `extraction_attempt_id`; (d) terminalize the same attempt `SUCCEEDED` with exact proof booleans, non-null line count/snapshot ID, empty reasons and terminal hash; and (e) revalidate and preserve, without rewriting, the work item's already-committed pointer to that same attempt. No evaluation, lifecycle, closure or other undefined downstream effect is a member or precondition of this R02 transaction.
8. Run terminal: for completed review runs and both rechecks, retain the existing atomic terminal reducer. For explicit failed-source finalization, after global replay and locked guards allocate receipt/event/time only then atomically persist receipt, append one sequence-2 terminal, reduce IN_PROGRESS to FAILED, assign trusted completed/occurred/recorded time, compute exact R01 calendar90, overlay all attempts byte-equally, preserve failed-attempt event bytes/null batch/zero downstream, and prevent a second terminal. Failure at each of 13 named effects restores prior bytes.
9. Any failed component rolls its entire boundary back; it cannot expose a new partial event/count/snapshot/status/deadline. A failed extraction-success terminal transaction leaves the previously committed STARTED reservation and work-item-to-attempt pointer intact for exact resume; that earlier pointer is not part of the failed terminal boundary and cannot be erased by its rollback.

The recheck run-global `[RC-084]` gate is re-evaluated immediately before boundary 5 and may terminalize the run only while no occurrence exists. Once boundary 5 commits, that run-global branch is no longer legal: the retained STARTED occurrence must resume or terminalize under the extraction/evaluation branches, so no orphan STARTED attempt can coexist with a terminal run.

`completed_at` is transaction-assigned, not caller-selected. `run_purge_eligible_at` is never calculated with elapsed hours or host defaults; it references the frozen R01 calendar policy/version. Recheck runs own no source-import aggregate because they own zero source attempts.

## 11. Retention

- Run receipt/event/projection identity and every run command key/preimage delete only when the exact last run-identity reference permits deletion at/after the run deadline.
- Review source attempts/staged/rejections/source references follow TR-114/TR-105; batch references follow TR-113. All attempt graphs remain independently retained until their governed common deadline/TR-114; a later success does not early-delete an earlier failed/aborted attempt. Earlier non-success attempts create no staged/work rows.
- A retained work/extraction/snapshot/evaluation chain may retain its governed run reference until the case/work graph deadline; it retains no source-import attempt/staged locator.
- Recheck work/extraction/snapshot/evaluation is case-owned and deletes with the case graph; its run identity follows the same explicit run-reference predicate.
- No command token, key, case/order identity, event, receipt, digest, or tombstone survives its owner deletion. Only already-authorized non-identifying aggregates survive; recheck runs create no source-import attempt aggregate.

## 12. End-to-end vectors

| Vector | Fixture/action | Exact oracle |
|---|---|---|
| `R02-RUN-MCH-001` | review invocation, one successful attempt, empty TARGET_REP/absence set | source-success transaction binds parent context batch byte-equal to attempt batch; following atomic work allocation commits empty `W(run)` and active work count 0; COMPLETED; attempts 1; work/eval/exception/block/OA 0; reasons [] |
| `R02-RUN-MCH-002` | review schema failure, explicit accepted no-retry finalization wins | failed attempt commits first; retained finalization receipt + one terminal atomically produce FAILED; null batch; all work/read 0; exact `[RC-002,RC-090]` |
| `R02-RUN-MCH-003` | abort ordinal 1, retry ordinal 2 succeeds | attempts 2; first aborted; second success; parent batch becomes byte-equal to ordinal-2 bound batch only in its success transaction; complete work/count boundary follows; terminal completed class from work; no ordinal gap |
| `R02-RUN-MCH-004` | duplicate triple in successful attempt | one staged/work/extraction path; amended SYN-SRC-013 rule |
| `R02-RUN-MCH-005` | two compatible orders, one extraction failure | CWE; work 2; evaluation-success 1; exception 1; blocked 0; exact extraction reason set |
| `R02-RUN-MCH-006` | one coherent source with exactly one TARGET_REP/non-TARGET_REP assignment-conflict subject and no executable order | CWE; batch non-null; work 0; evaluation-success 0; exception 1; blocked 1; OA 0; reasons `[RC-008]`; never FAILED |
| `R02-RUN-MCH-007` | source-absence verification complete | same case receives exact complete outcome; no closure from absence alone |
| `R02-RUN-MCH-008` | source-absence verification incomplete | CWE; no snapshot/eval; RC-010 plus extraction set |
| `R02-RUN-MCH-009` | valid Recheck Order succeeds twice via two accepted commands | two runs/work/attempt/snapshots; same retained case; no duplicate in either run |
| `R02-RUN-MCH-010` | exact Recheck Order command replay | original run/work/outcome returned; zero new read/append |
| `R02-RUN-MCH-011` | new Recheck Order targets purged case | transient RC-086; no receipt/run/work/read/rejection record |
| `R02-RUN-MCH-012` | Recheck Order extraction failure | CWE; work 1/evaluation-success 0/exception 1/blocked 0; no snapshot/evaluation; extraction+attention reasons |
| `R02-RUN-MCH-013` | DEDUPE awaiting + verified note | COMPLETED; reversible closure; no OA write/note text |
| `R02-RUN-MCH-014` | DEDUPE awaiting + no verified note | CWE; remains active/awaiting; RC-015; no merge |
| `R02-RUN-MCH-015` | confirmed DEDUPE + eligibility returned | COMPLETED; same case reopened; exact deadline canceled; DEDUPE NOT_CANDIDATE |
| `R02-RUN-MCH-016` | confirmed DEDUPE + incomplete extraction | CWE; closure/deadline unchanged; RECHECK_REQUIRED |
| `R02-RUN-MCH-017` | any recheck attempts source import/batch/tab | RC-081 before creation; zero run/read |
| `R02-RUN-MCH-018` | valid recheck then exact-version loss before occurrence reservation/read | FAILED; work1/occurrence0/eval0/exception0/block0/OA0; exactly `[RC-084]` |
| `R02-RUN-MCH-019` | source batch reused across two review runs for one still-retained exact case/order | distinct run/attempt/staged/work; byte-identical batch; same retained case |
| `R02-RUN-MCH-020` | same run/order insertion races | one work item; exact replay returns it; conflicting bytes reject; no second extraction |
| `R02-RUN-MCH-021` | two executable orders; each performs exactly one allowed fact-read dispatch and terminalizes ordinary extraction failure with the same minimal specific set | CWE; work 2; evaluation-success 0; exception 2; blocked 0; OA 2; reasons `[RC-011,RC-014,RC-015]`; never FAILED |

| `R02-RUN-MCH-022` | failed ordinal n; retry n+1 commits before finalizer | retry wins common lock; finalizer RC-081; run IN_PROGRESS; no finalization receipt/event |
| `R02-RUN-MCH-023` | failed ordinal n; finalizer commits before retry | run FAILED; retry RC-081; no n+1 attempt; exact finalizer replay returns winner |
| `R02-RUN-MCH-024` | inject failure after each of 13 finalization effects | prior state byte-identical for every selector; no residue |
| `R02-RUN-MCH-025` | multiple terminal failed attempts, finalization succeeds | every attempt projection gets byte-equal run completion/tzdb/deadline; attempt events unchanged |

Negative selectors additionally cover every unknown RunType/RunStatus, wrong context discriminator, missing/extra/null field, illegal source/recheck field cross-product, wrong predecessor, second terminal, post-terminal retry, noncanonical reason ordering, count/status contradiction, hash mutation, and projection rebuild mismatch. Each rejects before the affected transaction commits and preserves prior bytes.

## 13. Directly dependent artifacts/tests

This contract replaces the RUN_DOI_REVIEW-only v2 run payload assumption and directly updates the source-retention, machine, provenance/state, state-transition, transition-traceability, lifecycle route, acceptance, synthetic, persistence-intent, and implementation-handoff sections that serialize or reduce runs/work. It amends `SYN-SRC-001/003/012/013/015..020/024..028`, `SYN-EXT-001..004/008`, `SYN-DED-002/003/004`, `SYN-STATE-009`, and every direct run-event payload selector. R06 must implement the logical unique/FK/transaction constraints; later R03/R04 authority may supply downstream evaluation/lifecycle reason partitions but cannot change R02 source/run/extraction identities or the one-order rule.
