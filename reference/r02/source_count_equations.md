
> **Sanitized supporting reference.** This file is a mechanically sanitized derivative of
> source material supplied for the synthetic proof of concept. Historical status/freeze
> language is nonbinding. The curated files under `specs/` govern. No production-system
> access or real-data use is authorized by this reference.

# R02 Source, Attempt, and Run Count Equations

Status: modular R02 authority; closes `DOI-FWD-B015` and supplies the count semantics required by R02 event schemas and RunType machines. Every count has one equation and one persistence owner. No payload may use “all counts,” “available counts,” or an implementation-selected subtotal.

Every count is a `SafeJsonNonnegativeInteger` from 0 through 9,007,199,254,740,991 inclusive when serialized in canonical JSON. `source_import_attempt_count` for `RUN_DOI_REVIEW` is positive. An equation whose mathematical result exceeds the bound fails closed before event/batch append as an integrity/schema failure; it is never rounded, wrapped, emitted in exponent notation, or converted through binary floating point.

## 1. Prerequisite sets for one coherent manager read

These sets exist only after the exact manager DTO, every populated-row A/B invariant, the R01 OrderNumber dependency, and the R02 assignee classifier have all succeeded. If any row is malformed or the read is partial/systemically failed, none of these coherent sets is established.

For rows `r>=2` through finite last relevant row L:

```text
P(r)  := is_populated(A[r]) OR is_populated(B[r])
R     := { r | P(r) }
N(r)  := the R01-canonical OrderNumber for valid row r
Jrows := [ r in R, ascending r | B classification = IN_SCOPE_TARGET_REP ]
Orows := { r in R | B classification is OUT_OF_SCOPE_SCALAR
                    or PRIVACY_ERASED_OTHER_REP_INPUT }
NBrows:= { r in Orows | B classification = PRIVACY_ERASED_OTHER_REP_INPUT }
J     := { N(r) | r in Jrows }
O     := { N(r) | r in NBrows }
C     := bytewise-lexicographically sorted unique set J intersection O
nJ(o) := |{ r in Jrows | N(r)=o }|
```

`R` contains only schema-valid actual order rows. A literal B `TEXT("")` or TEXT made empty by the four allowed ASCII edge trim bytes is in Orows but not NBrows and therefore is out of scope but not a conflict cause. A physical blank B on an A-only row, a B-only row, a formula/merge/error/non-scalar, or an invalid A makes the entire import schema-rejected; it never enters R/Orows. Rows with both cells physical `BLANK` are not in R. Formatting-only rows and filter endpoints do not affect R or L.

Every set of OrderNumbers other than J and C is transient. O and unrelated non-TARGET_REP OrderNumbers/names/locators are erased before the persisted write set is built. Only the allowlisted count `|Orows|` and the digest/cardinality of C may persist.

## 2. Immutable DOISourceBatch counts

The owner of the following four values is one immutable `DOISourceBatch`. They are calculated from the coherent read used to create or validate that batch and are serialized as JSON integers in the full-record hash.

| Field | Exact equation | Scope and constraints |
|---|---|---|
| `TARGET_REP_row_count` | `\|Jrows\|` | Raw valid TARGET_REP row occurrences before deduplication; includes every occurrence of a conflicted TARGET_REP number. |
| `valid_distinct_TARGET_REP_order_count` | `\|J\|` | Unique R01-canonical TARGET_REP OrderNumbers, including conflicted numbers. This is the only persisted distinct-personal-order count. |
| `compatible_duplicate_TARGET_REP_row_count` | `sum(o in J, nJ(o)-1)` = `\|Jrows\|-\|J\|` | Number of excess compatible TARGET_REP row occurrences, not number of duplicate groups. Under manager v0.1 every same-number TARGET_REP duplicate is compatible, even if that number also has a cross-assignee conflict. |
| `TARGET_REP_conflict_order_count` | `\|C\|` | Unique TARGET_REP OrderNumbers with at least one nonblank non-TARGET_REP scalar row. It is not a row count. |

All four are non-null integers `>=0`. Cross-field invariants:

```text
0 <= TARGET_REP_conflict_order_count <= valid_distinct_TARGET_REP_order_count <= TARGET_REP_row_count
compatible_duplicate_TARGET_REP_row_count = TARGET_REP_row_count - valid_distinct_TARGET_REP_order_count
```

The useful derived but non-persisted values are:

```text
compatible_duplicate_TARGET_REP_group_count = |{ o in J | nJ(o) >= 2 }|
staged_order_count                     = |J \ C|
rejected_source_record_count           = |C|
TARGET_REP_source_ref_count                  = |Jrows|
staged_TARGET_REP_source_ref_count           = sum(o in J\C, nJ(o))
rejected_TARGET_REP_source_ref_count         = sum(o in C, nJ(o))
```

`compatible_duplicate_TARGET_REP_group_count` is not interchangeable with `compatible_duplicate_TARGET_REP_row_count`: a duplicate triple is one group and two excess rows. Each TARGET_REP row yields one current-attempt R01 SourceRef. Batch records contain zero SourceRefs. TR-099 owns one staged row per member of `J\C`; TR-103 owns one rejected record per member of C. RC-006 is attached exactly when `nJ(o)>=2`; RC-008 is attached exactly when `o in C`. RC-007 remains unreachable.

Batch create/reuse transaction: recompute all four counts and both personal hashes from the current coherent read. Lookup the batch identity before allocating ID/time. Exact identity reuse is legal only when all immutable full-record bytes, including counts, are byte-equal. Changed counts under the same alleged identity use exact canonical reasons `[RC-090,RC-091]`, null failed-attempt fingerprint/batch/counts, rollback, and zero OA.

## 3. DOISourceImportAttempt scan counts

The owner is one `DOISourceImportAttempt` terminal projection and its exact terminal event payload. The exact member inventory is:

```text
total_record_rows_seen_count
TARGET_REP_rows_seen_count
out_of_scope_rows_seen_count
rejected_rows_seen_count
```

All four keys are mandatory in STARTED and every terminal payload. The null partition is closed:

| Attempt event/outcome | All four values |
|---|---|
| `SOURCE_IMPORT_STARTED` / `STARTED` | explicit `null` |
| `SOURCE_IMPORT_SUCCEEDED` / `SUCCEEDED` | non-null integer `>=0`, including exact zero |
| `SOURCE_IMPORT_FAILED` / any failed outcome | explicit `null` |
| `SOURCE_IMPORT_ABORTED` / `ABORTED_PRE_OA` | explicit `null` |

There are no partial counts. A failed read, schema failure after some rows, proven change, abort after a complete read, or batch integrity failure discards every candidate scan count and persists four nulls.

For `SUCCEEDED` only:

| Field | Exact equation |
|---|---|
| `total_record_rows_seen_count` | `\|R\|` |
| `TARGET_REP_rows_seen_count` | `\|Jrows\|` |
| `out_of_scope_rows_seen_count` | `\|Orows\|` |
| `rejected_rows_seen_count` | `\|{r in Jrows : N(r) in C}\|` = `sum(o in C,nJ(o))` |

Success invariants:

```text
total_record_rows_seen_count = TARGET_REP_rows_seen_count + out_of_scope_rows_seen_count
TARGET_REP_rows_seen_count = DOISourceBatch.TARGET_REP_row_count
rejected_rows_seen_count <= TARGET_REP_rows_seen_count
rejected_rows_seen_count = 0 iff no TARGET_REP row belongs to a conflict order
```

`rejected_rows_seen_count` counts rejected TARGET_REP row occurrences, not non-TARGET_REP counterpart rows and not rejection records. `TARGET_REP_conflict_order_count`/`rejected_source_record_count` count unique conflict OrderNumbers. The distinction is observable in duplicate-conflict fixtures and must not be collapsed.

Attempt counts are current-read facts. Reusing an immutable batch does not reuse attempt counts. Unrelated non-TARGET_REP row additions can change `total_record_rows_seen_count` and `out_of_scope_rows_seen_count` while the privacy-relevant batch identity and batch counts remain byte-identical. A retry recomputes from its own read; no row count is summed across attempts.

## 4. Run and event counts

### 4.1 Source-import attempt count

The owner is the `DOIRun` projection and both run-event payload variants.

```text
source_import_attempt_count(run) =
  |{accepted SOURCE_IMPORT_STARTED streams owned by run}|
```

For `RUN_DOI_REVIEW`, invocation value is 1 and terminal value is the number of contiguous accepted ordinals `1..n`, with every attempt terminal at run terminal and at most the greatest ordinal successful. It is never a count of retries only and never a manifest of IDs. For `RECHECK_ORDER` and `RECHECK_DEDUPE_ORDER`, it is exactly 0 at invocation and terminal; those RunTypes create no manager batch or source-import attempt.

For every constructible later retry start, the attempt receipt/reservation/STARTED event and parent `DOIRunV3.source_import_attempt_count` reducer update commit or roll back in one transaction under the run lock. The new value is recomputed from committed accepted STARTED streams, not incremented from an untrusted cached scalar. Exact command/event replay returns the prior attempt and changes the parent count by zero; rollback exposes neither the new attempt nor a stale/incremented parent count.

### 4.2 Work and order-disposition universe

Let `W(run)` be the retained `DOIRunOrderWorkItem` rows owned by the run, unique by `(run_id,order_number)`. Let `Q(run)` be the distinct terminal order subjects:

```text
Q(run) = order subjects in W(run)
         union no-work TARGET_REP conflict subjects owned by the run's sole successful source attempt
```

The union is by exact R01 OrderNumber and counts each subject once. Recheck runs have exactly one work item/subject. A systemic run-level failure is not an order disposition and adds no subject beyond an already accepted work item.

For `RUN_DOI_REVIEW`, after the source-success transaction has atomically bound the parent batch, one separately atomic allocation boundary locks the run and every affected staged/rejection/case/order key, derives the complete `W(run)` set, inserts all of its unique work rows, and sets the active parent projection's `work_item_count = |W(run)|`. The scalar is always reduced from committed work rows. Exact allocation replay returns the same retained set and changes the count by zero; rollback exposes neither a partial set nor a changed count and performs zero OA reads. No extraction occurrence or OA dispatch is legal before this boundary commits. Recheck invocation already creates its sole work row and `work_item_count=1` atomically.

Every q in Q at terminal reduces to exactly one closed `RunOrderTerminalClass`:

```text
NORMAL_EVALUATION_SUCCEEDED
BLOCKED_PRE_OA
EXTRACTION_OR_EVALUATION_EXCEPTION
POST_SUCCESS_ORDER_EXCEPTION
```

- `NORMAL_EVALUATION_SUCCEEDED`: at least one run-owned normal evaluation was accepted for q and no order exception followed.
- `BLOCKED_PRE_OA`: q was individually forbidden/skipped before OA, including RC-008 no-work conflict or `execution_allowed=false`; no normal evaluation exists.
- `EXTRACTION_OR_EVALUATION_EXCEPTION`: execution was allowed but the order's extraction/evaluation chain terminalized without a normal evaluation.
- `POST_SUCCESS_ORDER_EXCEPTION`: a normal evaluation was accepted and the same order has an exception without a pre-OA block. This class has exactly two R02 triggers: (a) `RECHECK_DEDUPE_ORDER` completed the normal evaluation but found no independently verified note and therefore retained/SET attention with `[RC-015]`; or (b) a later order-local post-OA action/value/link transaction failed or collided while prior work remained committed. No other business result enters this class.

No class may be inferred from run status alone. A run-global authority/version failure after a valid recheck invocation but before extraction-occurrence reservation/read leaves its work item without an occurrence or order terminal class contribution; it is a systemic run failure, not a block/exception. The RunType state-machine artifact must serialize the exact terminal reason partition that establishes these classes.

### 4.3 Terminal run equations

The owner is the terminal `DOIRun` projection and exact `RUN_TERMINAL` payload. Invocation payloads use the initial values specified below.

| Field | Exact terminal equation |
|---|---|
| `work_item_count` | `\|W(run)\|` |
| `normal_evaluation_succeeded_count` | number of q with class `NORMAL_EVALUATION_SUCCEEDED` or `POST_SUCCESS_ORDER_EXCEPTION` |
| `order_exception_count` | number of q with class `BLOCKED_PRE_OA`, `EXTRACTION_OR_EVALUATION_EXCEPTION`, or `POST_SUCCESS_ORDER_EXCEPTION` |
| `blocked_order_count` | number of q with class `BLOCKED_PRE_OA` |
| `oa_read_count` | number of allowlisted OA read request dispatches attributed to the run that crossed the local dispatch boundary; each dispatched retry counts, irrespective of response success; a request rejected before dispatch does not count |

The distinct-order equations mean a single order with multiple errors counts once in `order_exception_count`; a post-success exception contributes once to both success and exception counts. A no-work RC-008 subject increments both exception and blocked but not work or OA. A systemic run-level failure increments neither exception nor blocked.

Cross-field constraints:

```text
0 <= blocked_order_count <= order_exception_count <= |Q(run)|
0 <= normal_evaluation_succeeded_count <= work_item_count
oa_read_count >= 0
```

Initial `RUN_INVOCATION_ACCEPTED` values:

| RunType | source attempts | work items | normal success | exceptions | blocked | OA reads |
|---|---:|---:|---:|---:|---:|---:|
| `RUN_DOI_REVIEW` | 1 | 0 | 0 | 0 | 0 | 0 |
| `RECHECK_ORDER` | 0 | 1 | 0 | 0 | 0 | 0 |
| `RECHECK_DEDUPE_ORDER` | 0 | 1 | 0 | 0 | 0 | 0 |

For source-review `FAILED` before a coherent batch, all work/result/OA counters are zero. For a valid recheck whose later systemic authority/version gate fails before occurrence reservation/read, terminal counters are exactly `source_import_attempt_count=0`, `work_item_count=1`, and every other counter 0; the failure is run-level and owns zero extraction occurrences. A coherent empty review has one successful source attempt and every work/result/OA counter zero.

Status equations after a coherent executable source/recheck path:

```text
COMPLETED                 iff order_exception_count=0 and blocked_order_count=0
COMPLETED_WITH_EXCEPTIONS iff order_exception_count>0
FAILED                    iff the RunType's closed run-global fatal gate fires
```

`blocked_order_count>0` necessarily implies `order_exception_count>0`. Zero normal successes does not imply FAILED. Run counters are reduced from committed records/events and never summed from source-attempt row counts.

### 4.4 OA count transaction rule

The OA boundary is permanently read-only. Increment the run-attributed logical read counter exactly once in the same local audit transaction that records a permitted read dispatch crossing the local boundary. A pre-dispatch safety/schema/version rejection increments zero. Retries are distinct dispatches. The terminal reducer sums those immutable run-attributed increments; it never trusts a caller-supplied total. Every source-ingestion failure has zero. `outbound_oa_mutation_request_count` remains a separate invariant fixed at zero and is not a member of these run payloads.

## 5. Retained source-import aggregate count

The only post-purge aggregate is the baseline closed `DOISourceImportAggregateV2`. Its owner is the unique row keyed by `(aggregate_schema_version,local_calendar_month,attempt_outcome_class)`.

```text
attempt_count(key) = number of terminal source-import attempts with that exact key
                     whose TR-114 purge transaction committed
```

TR-114 increments exactly one row by exactly one per purged attempt. Replay after committed deletion increments zero because no retained attempt/tombstone identity exists. This aggregate does not sum row, TARGET_REP, rejection, work, batch, reason, duration, or OA counts and contains no extra count member.

## 6. Known-answer fixtures

The numeric-looking values below are reserved synthetic integration input labels, not R02-authored OrderNumbers. Their R01 acceptance and canonical values are `DEFERRED_TO_R01_R02_INTEGRATION`; R02 does not define their normalization.

The machine-readable selector `.source_count_row_notation` in `R02_MANAGER_SOURCE_FIXTURES.json` is the closed legend for every string in `.source_count_vectors[].rows` and `.source_count_vectors[].attempts[].current_read_rows`. Success tokens match exact ASCII `^(J|O|E):(1|2|3)$`: `J` means an in-scope TARGET_REP actual-order row, `O` means a nonempty privacy-erased other-rep actual-order row, and `E` means an empty-TEXT out-of-scope actual-order row. The suffix is a fixture-only synthetic source-input label, not an R02 definition of `OrderNumber`; its R01 acceptance and canonical value are `DEFERRED_TO_R01_R02_INTEGRATION`, and integration must establish that equal labels bind equal canonical OrderNumbers and distinct used labels remain pairwise distinct. Array order is ascending synthetic source-row order and repeated tokens are distinct rows. The exact token `MALFORMED_AFTER_PARTIAL_READ` is legal only as the sole element of the systemic-negative vector: the provider read/closed DTO is technically complete and stable-token `UNCHANGED`, earlier rows were processed transiently, then a later constructible row failed the A/B semantic gate. Its exact outcome is `SCHEMA_REJECTED` `[RC-002,RC-090]`, no coherent row set, four null attempt counts, null fingerprint/batch, no derived counts, and zero OA. It cannot mix with success tokens. Every unknown or malformed token makes the fixture itself invalid and is never coerced, skipped, counted, or executed as a source outcome.

| Fixture | Rows after schema/R01 validation | Attempt counts `(total,J,out,rejected)` | Batch counts `(J rows,distinct J,duplicate excess,conflict orders)` | Derived `(dup groups,staged,rejected records,staged refs,rejected refs)` |
|---|---|---|---|---|
| one TARGET_REP row | `J(1)` | `(1,1,0,0)` | `(1,1,0,0)` | `(0,1,0,1,0)` |
| duplicate pair | `J(1),J(1)` | `(2,2,0,0)` | `(2,1,1,0)` | `(1,1,0,2,0)` |
| duplicate triple | `J(1),J(1),J(1)` | `(3,3,0,0)` | `(3,1,2,0)` | `(1,1,0,3,0)` |
| mixed distinct reps | `J(1),Other(2)` | `(2,1,1,0)` | `(1,1,0,0)` | `(0,1,0,1,0)` |
| one assignment conflict | `J(1),Other(1)` | `(2,1,1,1)` | `(1,1,0,1)` | `(0,0,1,0,1)` |
| duplicate conflict plus valid order | `J(1),J(1),Other(1),J(2),Other(3)` | `(5,3,2,2)` | `(3,2,1,1)` | `(1,1,1,1,2)` |
| scalar-empty assignee | `J(1),EmptyScalar(2)` | `(2,1,1,0)` | `(1,1,0,0)` | `(0,1,0,1,0)` |
| coherent no rows | none | `(0,0,0,0)` | `(0,0,0,0)` | `(0,0,0,0,0)` |
| coherent empty personal batch | `Other(2),EmptyScalar(3)` | `(2,0,2,0)` | `(0,0,0,0)` | `(0,0,0,0,0)` |
| sparse blanks | `J(1), blank, formatted-blank, J(2)` | `(2,2,0,0)` | `(2,2,0,0)` | `(0,2,0,2,0)` |
| malformed/partial/systemic failure | no coherent set | `(null,null,null,null)` | no batch | no staged/rejected/ref effects |

For `duplicate conflict plus valid order`, the normalized TARGET_REP-item array is exactly:

```json
[{"assigned_rep":"TARGET_REP","order_number":"1"},{"assigned_rep":"TARGET_REP","order_number":"1"},{"assigned_rep":"TARGET_REP","order_number":"2"}]
```

The ordered TARGET_REP preimage above and conflict preimage `C=["1"]` are closed R02 integration inputs, but both depend on R01 accepting and canonicalizing the synthetic source values to those exact OrderNumbers. Therefore their authoritative expected digests are each exactly `DEFERRED_TO_R01_R02_INTEGRATION`. The integration step must validate the frozen R01 outputs, then recompute the baseline-domain TARGET_REP-row and conflict hashes; no provisional digest may be promoted as authority.

Legal retry/reuse vector: attempt ordinal 1 fails unreadable with four null counts/no batch and leaves the parent `IN_PROGRESS`. If an explicitly accepted ordinal 2 retry wins the common run-control lock before finalization, it performs a complete independent read equal to a batch retained by another run. It has its own non-null current-read counts, reuses the byte-identical batch/count record, and yields `source_import_attempt_count=2`; no row count is summed across ordinals and the batch timestamp/counts do not change. If finalization wins first, ordinal 2 is not created and rejects `[RC-081]`.

## 7. Negative vectors

Required negatives reject: duplicate group count substituted for duplicate excess; conflict rows substituted for conflict OrderNumbers; non-TARGET_REP counterpart rows added to rejected count; physical blank B counted out-of-scope; formatted/filter rows counted; malformed/partial counts persisted as zero or partial instead of null; successful zero count represented null; unrelated non-TARGET_REP distinct OrderNumber persisted; attempt counts copied from a reused batch; cross-attempt row summing; rejected record counted as work item; an order counted twice for multiple exceptions; block omitted from exception; systemic run failure counted as order block; recheck source-attempt count 1; source-review invocation attempt count 0; OA rejection-before-dispatch counted; and an extra/omitted/null/wrong-type event count.

Every invalid count causes the owning event/projection/batch transaction to append nothing or roll back under its exact integrity reason. No invalid count can enable OA. Hash mutation tests must prove any changed batch/fingerprint/event count changes its owning canonical digest.

The reason ownership partition is exact:

| Count-affecting condition | Exact reason effect |
|---|---|
| compatible same-number TARGET_REP rows | `RC-006` on the one staged order; not a failed attempt |
| TARGET_REP/nonblank-non-TARGET_REP conflict | `RC-008` on the one no-case rejection; contributes to rejected/blocked/exception equations |
| malformed row/cell or count construction blocked by schema | failed attempt `[RC-002,RC-090]` and four null counts |
| proven source change | failed attempt `[RC-009,RC-090]` and four null counts |
| unreadable/partial source | failed attempt `[RC-089,RC-090]` and four null counts |
| incompatible same batch identity/full count bytes | failed attempt `[RC-090,RC-091]` and four null counts |
| event count missing/extra/null in wrong branch or inconsistent with immutable owners | `RC-111`, zero append/projection change |
| equal transient technical digest with unequal complete canonical source snapshots | exact failed attempt `SOURCE_CHANGED` with `[RC-009,RC-090,RC-103]`, four null counts, null fingerprint/batch, zero OA, and no retained transient evidence |

No count equation invents a new reason code. `ABORTED_PRE_OA` carries the empty reason set and four null counts.

## 8. Dependent artifacts and tests

- Replace all open count prose in the source-retention contract, machine/technical/persistence contracts, run and attempt event registries, terminal reducers, and fake-manager adapter.
- Amend `SYN-SRC-008..013`, `024`, `026`, `027`, and `SYN-SRC-028`; add direct duplicate-triple, duplicate-conflict-row, scalar-empty, sparse-blank, partial/null, retry/reuse, recheck-systemic-failure, and OA-dispatch-count cases.
- The event schema artifacts must enumerate all four attempt count members individually and every six run count members individually; no shorthand is legal.
- Projection readback tests must recompute each count from immutable owners and compare byte-for-byte with the terminal payload/projection.

Closure decision: `DOI-FWD-B015 = CLOSED_BY_R02` subject to independent R02 audit and R01 integration for OrderNumber/SourceRef inputs.
