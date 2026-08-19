
> **Sanitized supporting reference.** This file is a mechanically sanitized derivative of
> source material supplied for the synthetic proof of concept. Historical status/freeze
> language is nonbinding. The curated files under `specs/` govern. No production-system
> access or real-data use is authorized by this reference.

# DOI v0.1.5 Normative Source, Run, Currency, and Retention Contract

Status: remediation-candidate governing module; independent re-audit required. This module is incorporated into the v0.1.5 technical specification, machine contract, persistence model, transition matrix, acceptance matrix, synthetic requirements, and implementation handoff. It supersedes conflicting v0.1/v0.1.1 clauses. It does not authorize production implementation, live Synthetic Order Portal access, or any source-workbook change.

## 1. Permanent boundaries and locked source decision

Synthetic Order Portal (OA) remains permanently **100% READ-ONLY**. Source acquisition, validation, rejection, and run failure happen before any OA read. No clause below authorizes an OA write endpoint, generic request helper, arbitrary click/submit helper, mutation-capable control, background OA activity, credential capture, or live OA reconnaissance.

The only recognized manager-sheet mapping in DOI v0.1.5 is:

```yaml
schema_mapping_version: synthetic-doi-queue-v0.1
spreadsheet_id: SYNTHETIC-SOURCE-ID
tabs:
  MONDAY:    {title: "DOI Monday",    gid: "0"}
  WEDNESDAY: {title: "DOI Wednesday", gid: "1267803554"}
  FRIDAY:    {title: "DOI Friday",    gid: "593832135"}
schema_sentinels:
  A1: ""
  B1: ""
  E1: "Rep"
  F1: "# Of Orders"
  G1: "Completed"
record_columns:
  A: OrderNumber
  B: AssignedRep
first_record_row: 2
```

Normative source rules:

1. A human must explicitly confirm exactly one listed role/tab before the UI accepts a `Run DOI Review` invocation. A suggestion or disabled-control click is not an invocation and creates no run. Every accepted explicit invocation creates one `DOIRun` immediately.
2. The spreadsheet ID, confirmed role, exact title, exact `gid`, mapping version, and all five sentinel values must match the mapping above. No fuzzy header match, inferred layout, alternate tab, or general positional guess is legal.
3. Record rows are the rows `r >= 2` for which A or B is populated. The populated A/B span is derived from actual A/B records, not a Sheets filter range, named range, value in `F1`, or data in E:O. Blank A/B rows inside or after that span create no record.
4. Except for the three sentinel cells E1:G1, columns E:O are outside the source-row model. Their row values are not read into a DOI row, fingerprint, count, log, error, or decision.
5. A must normalize losslessly to a positive integer. A scalar text cell is outer-edge trimmed, must contain ASCII digits only, must contain at least one nonzero digit, and is canonicalized by removing leading zeros (`" 00123 " -> "123"`). A provider-typed numeric cell is accepted only when the connector exposes an exact decimal integer lexeme/proof without binary-float ambiguity; it canonicalizes to the same digit string. Fractions, exponent-only representations, booleans, dates, errors, zero, negatives, plus/minus signs, blanks on a populated A/B record, precision-ambiguous numbers, and fuzzy coercions violate the locked source-record invariant.
6. B must be scalar text. TARGET_REP selection is exactly locale-independent `lower(trim(B)) == "TARGET_REP"`. There are no aliases, substring matches, spell corrections, or OA-rep substitutions such as `target_rep` or `target_rep_web`. A scalar empty string is non-TARGET_REP and creates no persisted row identity; a non-scalar B value violates the locked source-record invariant.
7. Any workbook identity, selected-tab identity/title, sentinel, column-read, populated-record A normalization, or populated-record B type invariant failure emits `SOURCE_SCHEMA_UNRECOGNIZED` plus `SOURCE_IMPORT_ATTEMPT_FAILED`, terminalizes the current attempt as `SCHEMA_REJECTED`, creates no source batch/work/case/evaluation, and performs zero OA reads. The run terminalizes FAILED unless one exact legal pre-OA retry is later accepted. Validation of every populated A/B record completes before assignee filtering, hashing, staging, or any OA work; there is no row-level continuation for an invalid A or non-scalar B under `synthetic-doi-queue-v0.1`.
8. Under this A/B-only mapping, duplicate TARGET_REP rows for one canonical Order Number always merge for execution with `RC-006`; E:O is outside the row model and cannot create metadata conflict. `RC-007` remains compatibility-reserved for a future separately versioned schema with explicit row metadata. A valid Order Number appearing as TARGET_REP and also with a nonblank non-TARGET_REP scalar assignee emits `RC-008`, creates only the no-case rejection record, and blocks OA only for that Order Number; other coherent work may continue.
9. Other-assignee rows are transient. No other representative's name, Order Number, row content, source locator, customer/order metadata, or raw assignee value is persisted. Only privacy-safe aggregate counts and the conflict fingerprint defined below may remain.
10. Procedural browser reconnaissance of this manager sheet is `BLOCKED_BY_EXPLICIT_USER_DECISION` and is **not certified**. This fixed contract is authoritative; the remediation package must not claim browser-procedure certification.

## 2. Canonical source identity

All canonical JSON below is UTF-8 RFC 8785 JSON. All digests are lowercase SHA-256 hex. Every digest input uses the stated domain/version so a future normalization change requires a new version.

### 2.1 Normalized TARGET_REP row-content hash

After every populated record has passed the locked A/B value/type invariants, transiently scan valid record rows in ascending sheet-row order. For each row whose B value normalizes exactly to TARGET_REP, append one canonical item:

The following decimal value is a `NON_EXECUTABLE_SOURCE_NORMALIZATION_EXAMPLE` illustrating the manager-workbook Order Number canonicalizer. It is not a synthetic fixture, fixed vector, expected output, production lookup, or permitted input to any executable synthetic surface.

```json
{"assigned_rep":"TARGET_REP","order_number":"123456"}
```

If any populated record fails the locked rules, the TARGET_REP item set/hash is not established and no coherent batch is created. The raw invalid value and sheet-row locator do not persist. Duplicate valid TARGET_REP rows remain separate items before deduplication. Under `synthetic-doi-queue-v0.1`, no E:O value or other field is allowlisted.

```text
normalized_TARGET_REP_row_content_sha256 =
  SHA256(UTF8("doi-TARGET_REP-row-content/v1\n") || UTF8(RFC8785(TARGET_REP_items)))
```

### 2.2 Privacy-minimized assignee-conflict fingerprint

During the same coherent read, calculate transient sets:

```text
J = valid canonical Order Numbers on rows whose B normalizes to TARGET_REP
O = valid canonical Order Numbers on rows whose B is nonblank scalar text
    and does not normalize to TARGET_REP
C = bytewise-lexicographically sorted unique members of intersection(J, O)
```

Then calculate:

```text
assignee_conflict_fingerprint_sha256 =
  SHA256(UTF8("doi-TARGET_REP-assignee-conflict/v1\n") || UTF8(RFC8785(C)))
```

Only the digest and `|C|` may be stored in `DOISourceBatch`. `C` may exist transiently and in an attempt-local rejected record only for the already-in-scope TARGET_REP Order Number. No other-assignee name, raw assignee, source reference, unrelated Order Number, or row content may be persisted.

Consequences:

- changing an unrelated other-assignee row does not change either personal hash;
- adding or removing a non-TARGET_REP assignment for an existing TARGET_REP Order Number changes the conflict fingerprint and batch identity;
- changing a TARGET_REP row changes the TARGET_REP-content hash;
- changing `schema_mapping_version` changes the batch identity;
- the empty conflict set has a deterministic fingerprint;
- a conflicted TARGET_REP order emits `SOURCE_ASSIGNEE_CONFLICT` and receives zero OA reads.

### 2.3 `DOISourceBatch` identity and immutable schema

```json
{
  "source_batch_identity_version": "doi-source-batch/v0.1.3",
  "spreadsheet_id": "SYNTHETIC-SOURCE-ID",
  "selected_tab_identity": {
    "gid": "0",
    "role": "MONDAY",
    "title": "DOI Monday"
  },
  "schema_mapping_version": "synthetic-doi-queue-v0.1",
  "normalized_TARGET_REP_row_content_sha256": "<sha256>",
  "assignee_conflict_fingerprint_sha256": "<sha256>"
}
```

For Wednesday/Friday, substitute only the locked role/title/gid tuple. Define:

```text
source_batch_identity_sha256 = SHA256(UTF8(RFC8785(identity_material)))
```

`DOISourceBatch` is immutable and contains exactly:

- `source_batch_schema_version: "doi-source-batch/v1"`;
- `source_batch_id: OpaqueId`;
- `source_batch_identity_sha256: Sha256` with a unique constraint;
- every field in the identity material above;
- `status: READY`;
- `first_established_at: Timestamp`;
- `TARGET_REP_row_count: integer >= 0`;
- `valid_distinct_TARGET_REP_order_count: integer >= 0`;
- `compatible_duplicate_TARGET_REP_row_count: integer >= 0`;
- `TARGET_REP_conflict_order_count: integer >= 0`;
- `record_content_sha256: Sha256`.

The retained full-record object is exactly every field above except `record_content_sha256`, with the selected-tab identity retained as the exact nested object shown in the identity material and counts serialized as integers. Its digest is:

```text
record_content_sha256 = SHA256(
  UTF8("doi-source-batch/v1\n") ||
  UTF8(RFC8785(source_batch_without_record_content_sha256))
)
```

No extra field, omitted count, alternative tab alias, invocation field, or identity-only digest can satisfy the full-record binding. Lookup by `source_batch_identity_sha256` occurs before allocating `source_batch_id` or `first_established_at`; exact identity/full bytes return the original record and timestamp, while a changed full payload fails under the existing batch-integrity rule.

Invocation-specific actor/time, total rows, other-rep/out-of-scope counts, change-detection state, source references, rejected Order Numbers, and other mutable diagnostics do **not** belong to the immutable batch. They belong to `DOISourceImportAttempt`, `DOIRun`, ready staged records while retained, or attempt-local rejected records under the common run-terminal retention clock.

An identical identity may reuse the existing batch. Before reuse, compare the stored canonical identity material byte-for-byte. If the same digest resolves to different canonical material or incompatible batch payload, emit `SOURCE_BATCH_IDENTITY_INTEGRITY_CONFLICT`, terminalize the attempt as `BATCH_INTEGRITY_REJECTED`, create no replacement batch, and perform zero OA reads. The run fails unless one exact legal pre-OA retry follows. Silent overwrite or digest-only trust is forbidden.

### 2.4 Explicit source-batch owners and last-reference deletion

`DOISourceBatch` is not an indefinite archive. Its identity, TARGET_REP-row-content hash, conflict fingerprint, counts derived from the TARGET_REP Order Number set, and every batch-owned identifying field are sensitive retained detail. They exist only while at least one explicit retained owner needs the batch.

Use the closed owner enum:

```text
SourceBatchReferenceOwnerType =
  RUN
  | SOURCE_IMPORT_ATTEMPT
  | STAGED_SOURCE_RECORD
  | NO_CASE_REJECTED_RECORD
  | CASE_SOURCE_BINDING
```

Every active owner is represented by exactly one persisted row:

```yaml
source_batch_reference_id: OpaqueId
source_batch_reference_schema_version: doi-source-batch-reference/v1
source_batch_id: OpaqueId
reference_owner_type: SourceBatchReferenceOwnerType
reference_owner_id: OpaqueId
created_at: Timestamp
owner_revision_or_binding_sha256: Sha256 or null according to the closed table
content_sha256: Sha256
```

`source_batch_reference_id` is not caller-selected. It is exactly:

```text
SHA256(
  UTF8("doi-source-batch-reference-identity/v1\n") ||
  UTF8(RFC8785({
    "source_batch_reference_identity_schema_version":"doi-source-batch-reference-identity/v1",
    "source_batch_id":source_batch_id,
    "reference_owner_type":reference_owner_type,
    "reference_owner_id":reference_owner_id
  }))
)
```

The identity preimage bytes are retained while the reference exists and byte-compared before insert. A retry resolves the tuple/deterministic ID before allocating or recording `created_at`; it returns the original row and original timestamp when the complete semantic owner binding is unchanged.

Canonical reference content is the exact RFC-8785 object above except `content_sha256`, with an explicit null when the table permits no owner binding. The full digest is:

```text
content_sha256 = SHA256(
  UTF8("doi-source-batch-reference/v1\n") ||
  UTF8(RFC8785(reference_without_content_sha256))
)
```

Enforce `UNIQUE(source_batch_reference_id)` and `UNIQUE(source_batch_id,reference_owner_type,reference_owner_id)`, foreign-key ownership, stored identity/canonical-byte comparison, and exact source-batch existence. Same owner tuple and same bytes is idempotent; a changed owner binding under that tuple is RC-111; a proven digest collision is RC-103. A reference contains no raw cell, assignee, customer field, source locator, Order Number, or order-set hash of its own.

| Owner type | Exact owner and binding | Creation | Release/deletion |
|---|---|---|---|
| `RUN` | retained `DOIRun`; binding is the accepted v2 `RUN_TERMINAL` full hash and contains no attempt ID/manifest | Atomically when a successful run terminalizes after TR-101/102 | With the complete run-identity graph when `run_purge_eligible_at` is due and the closed run last-reference predicate is true. |
| `SOURCE_IMPORT_ATTEMPT` | retained coherent successful `DOISourceImportAttempt`; binding is its exact terminal success-event full hash | Atomically with source-import success | With every successful-attempt projection/event/detail byte under TR-114, including this reference. Failed/aborted attempts own no batch reference but follow the same deadline and deletion graph. |
| `STAGED_SOURCE_RECORD` | retained READY `DOIStagedOrder`; binding is null because the exact owner foreign key and unique tuple are authoritative | Atomically with TR-099 staged creation | Staged detail is attempt-local and deletes under TR-114. Before any case lifecycle append, TR-007/TR-008 atomically creates the privacy-minimized `DOICaseSourceAdmissionProofV1` plus case batch/reference owner; lifecycle events bind that case-owned proof, never the staged record. |
| `NO_CASE_REJECTED_RECORD` | retained `DOIRejectedSourceRecord`; binding equals `rejection_natural_key_sha256` | Atomically with TR-103 when a safely established batch is non-null | With TR-105 in the exact no-case deletion transaction. |
| `CASE_SOURCE_BINDING` | retained `DOICaseSourceBinding`; binding equals its `content_sha256` | Atomically when a staged/current source result is attached to a retained case | With that case graph under TR-018/019. |

Every terminal attempt outcome and run detail is scheduled for deletion at the common `calendar90(run.completed_at)` boundary under sections 6 and 13. A failed or aborted attempt is never exempt merely because it produced no batch or case. Deleting an attempt owner does not delete a batch retained by a run, rejection, or case owner. Staged records and their TARGET_REP row references are attempt-owned and never transfer into a case graph. Before `CASE_CREATED` or `SOURCE_PRESENT`, the system creates a case-owned `DOICaseSourceAdmissionProofV1` that contains no run ID, attempt ID, attempt ordinal/token, source-row reference, spreadsheet/tab identity, actor, or timestamp from the attempt. Lifecycle replay therefore remains exact after TR-114 deletes the staged/attempt graph.

The case admission proof is closed:

```yaml
case_source_admission_proof_schema_version: doi-case-source-admission-proof/v1
case_source_admission_proof_id: OpaqueId
case_id: OpaqueId
order_number: OrderNumber
assigned_rep_normalized: TARGET_REP
source_batch_id: OpaqueId
case_source_binding_id: OpaqueId
admitted_at: Timestamp
content_sha256: Sha256
```

`case_source_admission_proof_id = SHA256(UTF8("doi-case-source-admission-proof-identity/v1\n") || UTF8(RFC8785({"case_source_admission_proof_identity_schema_version":"doi-case-source-admission-proof-identity/v1","case_id":case_id,"source_batch_id":source_batch_id})))`. `content_sha256` hashes the complete object except itself under `doi-case-source-admission-proof/v1\n`. Enforce unique ID and unique `(case_id,source_batch_id)`, resolve and byte-compare the retained batch and `DOICaseSourceBinding`, and compare the canonical Order Number/TARGET_REP selection transiently to the staged source before atomically creating the proof. Exact replay returns the same proof/time. A mismatch or missing authority fails before lifecycle append. The proof and case batch/reference owner delete only with the case graph; it cannot reconstruct an attempt or source row.

The explicit case owner is:

```yaml
case_source_binding_id: OpaqueId
case_source_binding_schema_version: doi-case-source-binding/v1
case_id: OpaqueId
source_batch_id: OpaqueId
first_bound_at: Timestamp
content_sha256: Sha256
```

Its canonical object is every field except `content_sha256`; its domain is `doi-case-source-binding/v1\n`. Enforce `UNIQUE(case_source_binding_id)` and `UNIQUE(case_id,source_batch_id)`. It contains no Order Number, row locator, assignee, customer field, or source content. Its reference and row delete atomically with the retained case graph.

`case_source_binding_id` is deterministically derived under `doi-case-source-binding-identity/v1\n` from the exact closed object `{case_source_binding_identity_schema_version:"doi-case-source-binding-identity/v1",case_id,source_batch_id}`. Resolve and byte-compare that tuple before assigning `first_bound_at`; exact replay returns the original row/time, while same digest/different identity bytes is RC-103.

Define the only legal last-reference predicate, evaluated after all owner deletions due in the same serializable transaction:

```text
source_batch_last_reference_predicate(batch_id) :=
  NOT EXISTS retained DOISourceBatchReference
  WHERE source_batch_id = batch_id
```

TR-113 owns last-reference release. The deleting transaction locks the affected batch and its reference set, deletes the due owner/reference rows, evaluates the predicate, and, when true, atomically:

1. deletes the entire `DOISourceBatch` row, including `source_batch_id`;
2. deletes the identity material, canonical bytes, identity digest, TARGET_REP-row hash, assignee-conflict fingerprint/cardinality, TARGET_REP-derived counts, and every batch-owned identifying field;
3. deletes every batch-owned cache, stream member, immutable event, log/error payload, or export that contains `source_batch_id`, either fingerprint, an Order Number set, or a reversible lookup key;
4. leaves no batch tombstone, deletion receipt, predecessor, content hash, conflict hash, order-set digest, or persistent batch lookup key; and
5. preserves only already-upserted `DOISourceImportAggregate` rows defined below.

The only surviving source-import aggregate is exactly `DOISourceImportAggregateV2`:

```yaml
aggregate_schema_version: doi-source-import-aggregate/v2
local_calendar_month: YYYY-MM  # run.completed_at in America/New_York
attempt_outcome_class: SUCCEEDED | SCHEMA_REJECTED | SOURCE_CHANGED | INACCESSIBLE_OR_UNREADABLE | BATCH_INTEGRITY_REJECTED | ABORTED_PRE_OA
attempt_count: integer >= 1
```

The unique row key is the exact three non-count members. One TR-114 transaction increments `attempt_count` by exactly one after locking that row. There is no aggregate ID, event stream, content hash, revision, drill-through, or contribution ledger. Every unlisted member is forbidden, including attempt/run/batch/reference/case/order ID, spreadsheet ID/name, tab role/title/gid, actor, schema mapping version, source-row reference, fingerprint/digest, reason code, duration, exact timestamp, free text, error text, and reversible lookup key. Thus even a failed attempt with no batch can leave only one non-identifying count.

An immutable run/import/rejection/case event containing `source_batch_id` is a child of its named owner graph; the corresponding active reference MUST exist while the event exists, and the event deletes with that graph. It does not create an undocumented independent lifetime. A surviving diagnostic or aggregate contains only the closed non-identifying fields above.

TR-114 is the sole owner of the per-attempt `attempt_count +1` aggregate delta. When TR-113 is invoked inside that transaction it validates and shares the locked aggregate write set; when invoked later by an independently due owner deletion, it validates/preserves the already committed aggregate and applies zero aggregate delta. If any owner deletion, applicable caller-owned aggregate upsert, predicate check, or batch cleanup fails, the complete owner/reference/batch transaction and any caller-owned aggregate delta roll back. Partial reference release, a missing owner with a surviving reference, a deleted batch with surviving references, a zero-reference identifying batch, and a second aggregate count for the same attempt are illegal. Exact replay after a committed deletion observes no retained identifier and writes no tombstone.

## 3. Source-import attempt and run contracts

### 3.1 `DOISourceImportAttempt`

Every accepted explicit `Run DOI Review` invocation creates one immutable run and its mandatory ordinal-1 privacy-minimized source-import attempt before acquisition begins. `DOISourceImportAttempt` is distinct from an OA `DOIExtractionAttempt`. A run may own one or more sequential source-import attempts. Ordinal `n+1` is legal only while the run is `IN_PROGRESS`, ordinal `n` is terminal and not `SUCCEEDED`, no OA read/work/case exists for that run, and an exact human-confirmed retry command is accepted. Parallel attempts, skipped/reused ordinals, retry after success/OA access/run terminal, and implicit retry are RC-081. A retry uses TR-098; no new transition is inferred.

Required terminal schema (STARTED/terminal history is represented by immutable events; the terminal projection is not an overwrite):

```yaml
source_import_attempt_id: OpaqueId
run_id: OpaqueId
attempt_ordinal: integer >= 1
attempt_command_token_sha256: Sha256  # attempt-owned idempotency token; deleted under TR-114
spreadsheet_id: string
selected_tab_role: MONDAY | WEDNESDAY | FRIDAY
selected_tab_gid: canonical decimal string
selected_tab_title: string
tab_confirmation_actor_id: non-customer internal actor ID
tab_confirmed_at: Timestamp
attempted_schema_mapping_version: VersionId
started_at: Timestamp
completed_at: Timestamp
outcome_class: SUCCEEDED | SCHEMA_REJECTED | SOURCE_CHANGED | INACCESSIBLE_OR_UNREADABLE | BATCH_INTEGRITY_REJECTED | ABORTED_PRE_OA
failure_reason_codes: registered exact set for the outcome; empty for SUCCEEDED and ABORTED_PRE_OA
total_record_rows_seen_count: nonnegative integer or null if unavailable
TARGET_REP_rows_seen_count: nonnegative integer or null if unavailable
out_of_scope_rows_seen_count: nonnegative integer or null if unavailable
rejected_rows_seen_count: nonnegative integer or null if unavailable
change_detection_state: UNCHANGED | CHANGED | NOT_TECHNICALLY_AVAILABLE | NOT_REACHED
coherent_source_fingerprint_sha256: Sha256 or null
bound_source_batch_id: OpaqueId or null
oa_read_count: 0
run_completed_at: Timestamp or null
retention_policy_version: doi-retention-calendar90-ny/v1
timezone_id: America/New_York
timezone_database_version: VersionId or null until run terminal
source_import_attempt_purge_eligible_at: Timestamp or null until run terminal
```

The outcome registry above is the entire v0.1.5 terminal-attempt union. `SCHEMA_REJECTED` binds RC-002+RC-090; `SOURCE_CHANGED` binds RC-009+RC-090; `INACCESSIBLE_OR_UNREADABLE` binds RC-089+RC-090; `BATCH_INTEGRITY_REJECTED` binds RC-091+RC-090. `ABORTED_PRE_OA` is an intermediate terminal-attempt outcome for a human-confirmed pre-OA abort and carries an empty reason set; it never permits work/OA access, masquerades as a source failure, or terminalizes the run. A later attempt must terminalize the run before any attempt deadline is assigned. Unknown outcome/version is RC-081 before persistence. `coherent_source_fingerprint_sha256` and `bound_source_batch_id` are non-null only on `SUCCEEDED`; both are null on every other outcome. A successful attempt owns one explicit `SOURCE_IMPORT_ATTEMPT` batch reference; all other outcomes own none.

`source_import_attempt_id` is opaque and is not derived from `run_id` or ordinal. Under a run lock, enforce `UNIQUE(run_id,attempt_ordinal)` and `UNIQUE(run_id,attempt_command_token_sha256)`. The attempt-owned command-token preimage/canonical bytes, ordinal index, and both unique indexes delete with the attempt. Exact token/same bytes resolves the retained attempt; same token/different bytes is RC-111; after deletion no deterministic attempt-ID derivation, token/hash/tombstone, or ordinal lookup survives. Every run terminal requires all associated attempts terminal; at most one attempt is `SUCCEEDED`, and if present it is the greatest ordinal.

The attempt schema must never contain customer PII, exact row contents, TARGET_REP or other-rep Order Numbers, other-rep identities, other-rep source locators, raw cells, full-sheet/range dumps, HTML/DOM/screenshots, credentials, cookies, or session data. Unexpected diagnostics containing such material fail privacy validation and are not written. All allowlisted operational identity and detail shown above still delete under TR-114; none may remain merely because it is privacy-minimized.

### 3.2 Failed source import

An accepted explicit invocation always leaves a retained `DOIRun` and at least one `DOISourceImportAttempt` until their exact retention boundary. The following map to closed unsuccessful attempt outcomes in v0.1.5:

- `SOURCE_SCHEMA_UNRECOGNIZED`;
- `SOURCE_CHANGED_DURING_IMPORT` when coherency evidence proves a change;
- `SOURCE_UNREADABLE_OR_INACCESSIBLE`;
- `SOURCE_BATCH_IDENTITY_INTEGRITY_CONFLICT`;

Each source failure has all of these effects:

1. `DOISourceImportAttempt.outcome_class` equals its exact section 3.1 class, with `SOURCE_IMPORT_ATTEMPT_FAILED` plus the exact specific reason;
2. the run remains `IN_PROGRESS` only long enough to accept one exact legal next-ordinal retry under section 3.1; otherwise it terminalizes `FAILED` through TR-004;
3. `DOIRun.source_batch_id = null`; the closed v0.1.5 schema/change/unreadable/integrity failure union creates or binds no executable batch;
4. zero executable work items and `oa_read_count = 0`;
5. no case, snapshot, evaluation, or OA extraction attempt;
6. privacy-minimized failure metadata only, all of which is nevertheless deleted under TR-114.

`ABORTED_PRE_OA` has the same zero-batch/work/case/evaluation/OA effects but is not mislabelled as a source failure. It leaves the run `IN_PROGRESS` and requires a later ordinal; it can never be the final attempt named by a run terminal. No governing document may say that a confirmed explicit invocation creates no run, may create a run, creates an executable batch on an unsuccessful attempt, or may open OA after one of these outcomes.

### 3.3 `DOIRun` schema, active state, and terminal outcome

For `RUN_DOI_REVIEW`, add/lock:

```yaml
run_id: OpaqueId
run_type: RUN_DOI_REVIEW
initiated_by_actor_id: non-customer internal actor ID
started_at: Timestamp
completed_at: Timestamp or null                    # null if and only if status=IN_PROGRESS
status: IN_PROGRESS | COMPLETED | COMPLETED_WITH_EXCEPTIONS | FAILED
source_import_attempt_count: integer >= 1 # no attempt ID or manifest may be retained here
source_batch_id: OpaqueId or null        # may be null while IN_PROGRESS; null on named failed imports
schema_mapping_version: VersionId
rules_engine_version: VersionId
extractor_version: VersionId
business_calendar_version: VersionId or null under existing WWC rule
work_item_count: integer >= 0
normal_evaluation_succeeded_count: integer >= 0
order_exception_count: integer >= 0
blocked_order_count: integer >= 0
oa_read_count: integer >= 0
reason_codes: registered set
run_purge_eligible_at: Timestamp or null            # null if and only if status=IN_PROGRESS; otherwise calendar90(completed_at)
```

`IN_PROGRESS` is the valid nonterminal projection created by TR-001 `RUN_INVOCATION_ACCEPTED`. Exactly while `status=IN_PROGRESS`, `started_at` is non-null, `completed_at` and `run_purge_eligible_at` are null, governed active-processing metadata—including a safely established `source_batch_id`—may advance, and the run must not be treated as completed. The invocation event omits a completion-time member; the reduced `DOIRun` projection materializes its required `completed_at` field as null. TR-002, TR-003, and TR-004 alone consume `IN_PROGRESS` into `COMPLETED`, `COMPLETED_WITH_EXCEPTIONS`, or `FAILED`; that terminal transaction sets non-null `completed_at` to the terminal completion instant and non-null `run_purge_eligible_at=calendar90(completed_at)`. No terminal status returns to `IN_PROGRESS`; an unknown status or unlisted edge fails before persistence.

Terminal classification is based on source/run execution, not on whether at least one normal evaluation succeeded:

- `FAILED` only when a registered run-level fatal gate prevents coherent source execution. Under v0.1.5 every such gate is pre-OA, so `oa_read_count = 0`.
- `COMPLETED_WITH_EXCEPTIONS` when a coherent validated source batch was created/reused and processing reached a terminal result, but one or more individual orders was blocked, skipped, extraction-failed, or otherwise exceptioned. This explicitly includes (a) every in-scope order blocked and zero normal evaluations, and (b) every permitted OA extraction attempt failing while the run-level source execution itself completes.
- `COMPLETED` only when coherent source processing terminates with `order_exception_count = 0` and `blocked_order_count = 0`. A coherent empty personal batch may be `COMPLETED` with all work/evaluation counts and OA reads equal to zero.

A bad order never converts a coherently executed run into `FAILED`. Every accepted invocation creates a new run and ordinal-1 source-import attempt even when it reuses an immutable batch. A legal pre-OA retry appends a later ordinal under that same run; all attempts are terminal before the run terminal event. On run terminal, `run_purge_eligible_at=calendar90(completed_at)` and is byte-equal to every associated attempt deadline.

### 3.4 Immutable run and source-import event schemas

`DOIRun` and `DOISourceImportAttempt` projections are reduced from two separate immutable streams. Every event uses RFC 8785 canonical UTF-8 JSON and lowercase SHA-256. Each event stores its exact schema version, event ID, owning stream ID, strictly increasing sequence, predecessor event ID/content digest (both null only for sequence 1), closed event type, occurred/recorded timestamps, actor kind/ID, registered reason-code set, exact type-specific payload, and content digest over the canonical event without that digest.

#### 3.4.1 `DOIRunEvent`

```yaml
run_event_id: OpaqueId  # domain alias of common envelope event_id
event_schema_version: doi-run-event/v2  # domain alias of schema_version
run_id: OpaqueId
stream_id: Sha256  # exact RUN identity derived from run_id under doi-event-stream-id-v1
stream_sequence: 1 | 2
previous_event_id: OpaqueId or null
previous_event_content_sha256: Sha256 or null
event_type: RUN_INVOCATION_ACCEPTED | RUN_TERMINAL
occurred_at: Timestamp
recorded_at: Timestamp
actor_kind: HUMAN | SYSTEM
actor_id: internal actor ID or null only for SYSTEM
provenance: HUMAN_VERIFIED | SYSTEM_VERIFIED
reason_codes: registered set
payload: type-specific object
content_sha256: Sha256
```

The names above are the common envelope fields; `run_event_id`/`event_schema_version` are domain aliases, not duplicate stored values. `RUN_INVOCATION_ACCEPTED` requires HUMAN/HUMAN_VERIFIED and its exact actor ID. `RUN_TERMINAL` requires SYSTEM/SYSTEM_VERIFIED. Any alias, actor, provenance, stream identity, or type mismatch is RC-111 and appends nothing.

`RUN_INVOCATION_ACCEPTED` is sequence 1 and its payload contains exactly: `run_type=RUN_DOI_REVIEW`, `initiated_by_actor_id`, `started_at`, `source_import_attempt_count=1`, attempted `schema_mapping_version`, `rules_engine_version`, `extractor_version`, nullable `business_calendar_version`, `resulting_status=IN_PROGRESS`, `source_batch_id=null`, `run_purge_eligible_at=null`, all work/evaluation/exception/block/OA-read counts zero, and an empty reason set. It contains no attempt ID, attempt token, ordinal list, or attempt-event hash.

`RUN_TERMINAL` is sequence 2 and its payload contains exactly: `prior_status=IN_PROGRESS`; `resulting_status=COMPLETED|COMPLETED_WITH_EXCEPTIONS|FAILED`; `completed_at`; integer `source_import_attempt_count>=1`; nullable `source_batch_id`; exact schema/rules/extractor/calendar versions; final work-item, normal-evaluation-success, order-exception, blocked-order, and OA-read counts; `retention_policy_version`, `timezone_id`, `timezone_database_version`, exact `run_purge_eligible_at=calendar90(completed_at)`; and the terminal registered reason set. It contains no attempt ID/manifest/ordinal/token. Its count must equal the number of terminal attempt projections at commit. `FAILED` requires the final unsuccessful source failure's RC-090 plus exact specific code; `ABORTED_PRE_OA` cannot be final. The two completed states require one final successful attempt/coherent bound batch and obey section 3.3 exactly.

#### 3.4.2 `DOISourceImportAttemptEvent`

```yaml
source_import_attempt_event_id: OpaqueId  # domain alias of common envelope event_id
event_schema_version: doi-source-import-attempt-event/v2  # alias of schema_version
source_import_attempt_id: OpaqueId
run_id: OpaqueId
attempt_ordinal: integer >= 1
attempt_command_token_sha256: Sha256
stream_id: Sha256  # exact SOURCE_IMPORT_ATTEMPT identity derived from source_import_attempt_id
stream_sequence: 1 | 2
previous_event_id: OpaqueId or null
previous_event_content_sha256: Sha256 or null
event_type: SOURCE_IMPORT_STARTED | SOURCE_IMPORT_SUCCEEDED | SOURCE_IMPORT_FAILED | SOURCE_IMPORT_ABORTED
occurred_at: Timestamp
recorded_at: Timestamp
actor_kind: SYSTEM
actor_id: null
provenance: SYSTEM_VERIFIED
reason_codes: registered set
payload: type-specific object
content_sha256: Sha256
```

The attempt event names are likewise common-envelope aliases, not parallel fields. All three attempt event types require SYSTEM/SYSTEM_VERIFIED. The human source confirmation remains an exact invocation-payload binding and is not relabelled as the attempt-event actor.

`SOURCE_IMPORT_STARTED` is sequence 1 and its payload contains exactly: `prior_status=NONEXISTENT`, `resulting_status=STARTED`, the envelope-equal `attempt_ordinal` and `attempt_command_token_sha256`, spreadsheet ID, selected tab role/title/gid, confirmation actor/time, attempted schema version, start time, null completion/outcome/fingerprint/batch/run-terminal/deadline, all available aggregate counts null or zero, `change_detection_state=NOT_REACHED`, and `oa_read_count=0`.

`SOURCE_IMPORT_SUCCEEDED` is sequence 2 and its payload contains exactly: `prior_status=STARTED`, `resulting_status=SUCCEEDED`, `outcome_class=SUCCEEDED`, completion time, the same exact ordinal/token/source/tab/schema binding, privacy-safe final aggregate counts, final change-detection state, required coherent-source fingerprint, required safely bound source-batch ID, empty failure reasons, null run-terminal/deadline until the run terminalizes, and `oa_read_count=0` through import completion.

`SOURCE_IMPORT_FAILED` is sequence 2 and its payload contains exactly: `prior_status=STARTED`, `resulting_status=FAILED`, one of the four failed `outcome_class` literals in section 3.1, completion time, the exact ordinal/token/source/tab/schema information known before failure, only privacy-safe aggregate counts available before failure, final change-detection state, `coherent_source_fingerprint_sha256=null`, null bound executable batch, RC-090 plus the class's exact source failure reason, null run-terminal/deadline until run terminal, and `oa_read_count=0`. `SOURCE_IMPORT_ABORTED` has the same exact field set and nulls but `resulting_status=ABORTED`, `outcome_class=ABORTED_PRE_OA`, `change_detection_state=NOT_REACHED|UNCHANGED` according to already completed reads, and an empty reason set; it is legal only before OA/work/case creation. Every terminal event receives exact `run_completed_at`, policy/tzdb tuple, and `source_import_attempt_purge_eligible_at` in its terminal projection when the v2 run-terminal transaction commits; immutable event bytes are not overwritten.

#### 3.4.3 Canonical domains, constraints, and atomicity

Run-event content uses domain `doi-run-event/v2\n`; source-import-attempt event content uses `doi-source-import-attempt-event/v2\n`. In each case, `content_sha256 = SHA256(UTF8(domain) || UTF8(RFC8785(event_without_content_sha256)))`.

- `UNIQUE(run_event_id)`, `UNIQUE(run.stream_id,stream_sequence)`, `UNIQUE(source_import_attempt_event_id)`, `UNIQUE(attempt.stream_id,stream_sequence)`, `UNIQUE(run_id,attempt_ordinal)`, and `UNIQUE(run_id,attempt_command_token_sha256)` are mandatory while their graph is retained. Stream IDs equal the common-envelope derivation from their owners. A run has one or more sequential attempts; every ID/token/ordinal index is attempt-owned and deletes under TR-114.
- The envelope `reason_codes` is authoritative and must equal any reason set repeated in the type payload byte-for-byte. Run/import starts and import success use the empty set; import failure and run `FAILED` use exactly RC-090 plus one specific registered source-failure code; a completed run uses exactly its terminal registered order/run codes. A mismatch rejects the append with RC-111 and changes no projection.
- Stream sequence 1 has null common-envelope predecessors; sequence 2 names the exact sequence-1 event ID/full-event digest. Each stream has exactly one start event and at most one terminal event. Exact same-ID/same-canonical-byte replay is a no-op; a stale sequence/predecessor, wrong stream derivation/provenance, second terminal, or same ID with different canonical bytes is rejected with RC-111 (and RC-103 only for a proven digest collision), leaving projections unchanged.
- Accepted invocation appends the run sequence-1 event and ordinal-1 attempt sequence-1 event in one transaction. A failed terminal attempt either receives an explicitly authorized next-ordinal TR-098 retry or terminalizes the run `FAILED`; an aborted terminal attempt leaves the run `IN_PROGRESS` and requires a later ordinal. Neither path retries implicitly. Source success appends `SOURCE_IMPORT_SUCCEEDED` before any eligible OA read and forbids another attempt. The run terminal event is appended only after all attempts are terminal and, in the completed states, run work finishes.
- Projection fields are recomputed only from these streams. No run/import status, count, reason, binding, or timestamp is overwritten in place as an authoritative fact.

## 4. Rejected/no-case source identity

Rejected input that creates no `DOIOrderCase` must not be stored as an indefinitely durable child of a reusable batch. Use an attempt-local `DOIRejectedSourceRecord` only when a privacy-minimized exact record is operationally necessary.

```yaml
rejected_source_record_id: OpaqueId
run_id: OpaqueId
source_import_attempt_id: OpaqueId
source_batch_id: OpaqueId or null
rejection_kinds: canonical ordered nonempty set<TARGET_REP_ROW_CONFLICT | TARGET_REP_ASSIGNEE_CONFLICT>
order_number: OrderNumber
TARGET_REP_source_refs: ordered set of SourceRef
rejection_natural_key_canonical_bytes: bytes
rejection_natural_key_sha256: Sha256
case_id: null
reason_codes: registered nonempty set
created_at: Timestamp
run_terminal_at: Timestamp or null until run terminalizes
retention_policy_version: doi-retention-calendar90-ny/v1
purge_eligible_at: Timestamp or null until run terminalizes
```

Field rules:

- `order_number` is required and already canonical for the closed conflict kinds. Under `synthetic-doi-queue-v0.1`, only `TARGET_REP_ASSIGNEE_CONFLICT`/RC-008 is reachable; duplicate TARGET_REP A/B rows merge, and RC-007/`TARGET_REP_ROW_CONFLICT` is compatibility-reserved for a separately governed future mapping. Invalid A or non-scalar B input cannot reach this entity; it fails the import before a coherent batch or rejected record exists, and the raw invalid value never persists.
- The no-case natural key bytes are exactly JCS `{rejection_identity_schema_version:"doi-rejected-source-identity-v2",source_import_attempt_id,order_number}` and its stored SHA-256. Enforce `UNIQUE(source_import_attempt_id,order_number)` and `UNIQUE(rejection_natural_key_sha256)` with byte comparison. The retained record still carries its validated `run_id` FK, but run identity is not the rejection uniqueness scope because a legal later ordinal is distinct. TR-103 appends exactly one complete record whose nonempty rejection-kind/reason sets contain every simultaneously proved allowlisted cause. Exact replay returns it; same digest/different bytes is RC-103; a same natural key with different completed cause/ref payload is RC-111 and never overwrites.
- `TARGET_REP_source_refs` contains TARGET_REP-row references only. No other-assignee row locator or content persists.
- Out-of-scope and scalar-unrecognized-assignee rows do not create an identity-bearing rejected record. Only allowlisted non-identifying aggregates plus the TARGET_REP-order conflict-fingerprint digest/cardinality may survive their transient scan; no raw row/name/unrelated Order Number/locator survives.
- No rejected record can create a case, run work item capable of OA execution, extraction attempt, snapshot, or evaluation. OA reads for it are zero.
- When its associated run terminalizes, calculate `purge_eligible_at = calendar90(run.completed_at)` under section 6. Delete the exact Order Number, source refs, record ID, any rejection evidence fingerprint, and all reconstructable identity at that instant.
- After deletion, only the section-13 exact attempt aggregate month/outcome/count may survive. No rejection count/reason/schema dimension, order-specific audit event, tombstone, hash, predecessor, or join key survives. `SOURCE_REJECTED_IDENTITY_PURGED` may be asserted transaction-locally by TR-105 but is not a surviving aggregate member.
- Reusing `DOISourceBatch` never changes an existing rejected record's `run_terminal_at` or `purge_eligible_at` and never revives a deleted record. A later genuine attempt/run may create a new attempt-local rejection record with its own natural identity; all attempts under one run nevertheless receive the common run-terminal clock and none extends or overwrites an older record.
- A safely established non-null batch creates one `NO_CASE_REJECTED_RECORD` source-batch reference atomically with the rejected record. TR-105 deletes that reference with the rejection graph and then invokes TR-113 in the same transaction. Batch hashes/counts remain only while another explicit section 2.4 owner survives; they are not durable anonymized history.

The pending-to-scheduled change is itself one immutable `DOIRejectedSourceRetentionEvent` using the full common envelope. `rejected_source_retention_event_id` aliases `event_id`; `event_schema_version=doi-rejected-source-retention-event/v1` aliases `schema_version`; `stream_id` is the exact `REJECTED_SOURCE_RETENTION` identity derived from `rejected_source_record_id`; `stream_sequence=1`; both common predecessor fields are null; `event_type=RETENTION_SCHEDULED`; actor/provenance are SYSTEM/SYSTEM_VERIFIED; reason set is exactly RC-092; and full-event `content_sha256=SHA256(UTF8("doi-rejected-source-retention-event/v1\n") || UTF8(RFC8785(event_without_content_sha256)))`. Its closed payload contains only the owning rejected-record ID, associated run ID, exact `RUN_TERMINAL` event ID/content hash, policy/tzdb versions, `run_terminal_at`, and calculated `purge_eligible_at`.

`UNIQUE(rejected_source_retention_event_id)`, `UNIQUE(stream_id,stream_sequence)`, and `UNIQUE(rejected_source_record_id)` make scheduling append-only and at most once; a wrong owner-derived stream ID/envelope alias is RC-111 and it cannot be reset or extended by batch reuse. Calculation failure appends no approximate schedule and emits RC-096 while the record remains pending. At actual deletion, the scheduling event is deleted in the same transaction as the rejected record. No per-record deletion event, receipt, tombstone, hash, predecessor, join key, or RC-093 dimension survives; RC-093 is transaction-local and the sole durable aggregate is the section-13 v2 month/outcome/count row.

## 5. Exact ISO-4217 monetary contract

The USD-only machine type and every `currency: USD` restriction are deleted.

```yaml
ISO4217CurrencyCode:
  representation: exactly three uppercase ASCII letters
  validity: member of the frozen ISO-4217 registry version bound to the containing snapshot/evaluation/event/KPI schema

Money:
  amount_decimal: canonical exact base-10 string
  currency_code: ISO4217CurrencyCode
  iso_4217_registry_version: nonempty VersionId
```

`amount_decimal` is represented and calculated as an integer coefficient plus the ISO registry's minor-unit exponent, rendered without exponent notation, commas, whitespace, a plus sign, leading integer zeros, or negative zero. It has exactly the registry-defined fractional scale (`USD 10.00`, `JPY 10`, `KWD 10.000`). An input with excess precision is rejected; it is never rounded or truncated. Source merchandise facts are nonnegative. A governed aggregate correction/reversal may be signed only where its field contract explicitly permits it. Binary floating-point arithmetic and serialization are forbidden.

All intervention values, resulting-order values, alternate values, opportunity values, and KPI money use the same type and bind an ISO-registry version. `CURRENCY_CODE_INVALID` makes the monetary fact invalid and every dependent calculation `UNAVAILABLE`; USD is never inferred.

Arithmetic invariants:

1. Money may be added, subtracted, compared, or netted only when both currency codes and `iso_4217_registry_version` are identical and the bound registry gives the same exact scale. A different registry binding remains a separate segment or fails the governed bucket operation; it is never silently rescaled.
2. Different currencies are never silently summed. Emit `MIXED_CURRENCY_AGGREGATION_PROHIBITED` for a requested cross-currency scalar and return `UNAVAILABLE` for that scalar.
3. KPI output is deterministically segmented by both currency and `iso_4217_registry_version`/scale. A single combined monetary headline is legal only when every contributing verified value has the same currency and the same registry version/scale.
4. DOI v0.1.5 has no FX table, inferred rate, currency conversion, base currency, or converted headline. Any future conversion requires a separately governed versioned feature.

## 6. Exact 90-local-calendar-day algorithm

The canonical machine field is `purge_eligible_at`; the ambiguous alias `purge_due_at` and all bare `timestamp + 90 days` language are removed.

Define `calendar90(anchor_instant)` with:

```yaml
retention_policy_version: doi-retention-calendar90-ny/v1
timezone_id: America/New_York
timezone_database_version: required versioned runtime value
```

Algorithm:

1. Convert the RFC 3339 `anchor_instant` to `America/New_York` using the bound timezone-database version.
2. Let `target_date = local_date + 90` calendar dates and let `target_wall_time` equal the original local hour, minute, second, and fractional second.
3. Form `target_local = target_date + target_wall_time`.
4. If the zone has one valid offset for `target_local`, use it.
5. If it has no valid offset because of a spring-forward gap, resolve to the transition's `dateTimeAfter`, the first valid local instant after the gap. Do not preserve minutes by shifting an additional gap duration.
6. If it has two valid offsets because of a fall-back overlap, calculate both instants and choose the later instant.
7. Convert the resolved instant to UTC, persist it as `purge_eligible_at`, and bind the retention-policy and timezone-database versions in the scheduling event.

If this calculation cannot be completed deterministically, emit `RETENTION_CLOCK_CALCULATION_FAILED`, schedule no earlier fallback, and block purge pending fail-closed repair.

Case rules:

- anchor on the exact most recent verified terminal transition, not queue exit, `FULL_DS`, payment-only exclusion, or re-observation of the unchanged closure;
- reopening a reversible case before purge clears the current `purge_eligible_at` only through the lifecycle registry's closed `CaseReopenPayloadV2` and `PURGE_CANCELED` schemas. Each must carry an explicit byte-equal `PriorClosureRetentionBindingV1` copied from the locked pre-event projection/event, including closure event/kind/classification/verified instant, retention policy/version/timezone/tzdb/calendar rule, active deadline, and prior projection revision/hash. The canceled deadline must equal the binding's `prior_purge_eligible_at`; an omitted, inferred, hash-only, or mismatched tuple fails before append and leaves the old deadline/state unchanged. The accepted old scheduling/cancellation events remain immutable while the case is retained;
- a later verified terminal closure calculates a new clock from that new instant;
- hard closure remains non-reopenable under the existing contract;
- details exist immediately before the instant and purge becomes eligible exactly at it.

The same `calendar90` function applies to no-case rejection retention (anchor: associated run terminal instant), nominal alternate-observation retention (anchor: `observed_at`), and **every** source-import attempt outcome (anchor: associated `DOIRun.completed_at`). When the run is nonterminal, `run_completed_at`, timezone-database version, and `source_import_attempt_purge_eligible_at` are all null and no purge may run. In the run-terminal transaction, calculate one exact deadline from the run completion instant and copy it byte-identically into every terminal associated attempt projection, regardless of outcome or attempt completion time. Fixed 2,160-hour arithmetic, host timezone/default tzdb, attempt-start/completion anchoring, success-only scheduling, and deadline extension by retry/batch reuse are forbidden.

## 7. Alternate-observation deletion

Every immutable `DOIAlternateObservation` stores:

```yaml
observed_at: Timestamp
retention_policy_version: doi-retention-calendar90-ny/v1
timezone_database_version: VersionId
observation_purge_eligible_at: Timestamp  # calendar90(observed_at)
action_context_id: OpaqueId or null
case_id: OpaqueId or null                 # derived/validated through Action Context
```

A case-linked observation belongs to exactly one retained Action Context/case; it is not shared across cases. Its effective deletion projection is:

```text
effective_observation_deletion_at =
  min(observation_purge_eligible_at,
      linked_case.purge_eligible_at when non-null)
```

At actual linked-case purge, the observation and all Action Context links are deleted atomically even if the nominal observation deadline is later. If a reversible case reopens before purge, its current case deadline becomes null and the observation again uses its own nominal deadline; no deletion occurs at the canceled case deadline. A later case closure recomputes the minimum. Storage until a deadline never makes an observation fresh; current action use still requires the exact current Action Context link.

Only completely de-linked reusable product **relationship revisions** may survive indefinitely. They must contain no Order Number, case/action-context/customer identity, source-row linkage, originating-order provenance, or reconstructable hash. Observation retention never extends relationship retention, and relationship retention never extends an observation.

## 8. Reason-code registry delta

The v0.1.5 candidate carries forward these existing codes without changing their IDs or meanings:

| ID | Code | Class | Owner | Deterministic trigger/effect |
|---|---|---|---|---|
| RC-089 | `SOURCE_UNREADABLE_OR_INACCESSIBLE` | BLOCK | `DOISourceImportAttempt`/`DOIRun` | Confirmed selected source or required sentinel/A:B read cannot be accessed or read. Attempt becomes `INACCESSIBLE_OR_UNREADABLE`; absent a legal retry the run fails. No batch/work/case; zero OA reads. |
| RC-090 | `SOURCE_IMPORT_ATTEMPT_FAILED` | BLOCK | `DOISourceImportAttempt` | Umbrella code required on every failed import and paired with at least one specific registered source-failure code. Never substitutes for the specific code. |
| RC-091 | `SOURCE_BATCH_IDENTITY_INTEGRITY_CONFLICT` | SAFETY | batch binding | Same digest maps to different canonical identity material or incompatible payload. Fail closed before OA; do not overwrite/reuse/create a conflicting batch. |
| RC-092 | `SOURCE_REJECTED_IDENTITY_RETENTION_SCHEDULED` | AUDIT | `DOIRejectedSourceRecord` | Associated run terminalized; exact no-case identity is scheduled with `calendar90(run.completed_at)` without extending any older record. |
| RC-093 | `SOURCE_REJECTED_IDENTITY_PURGED` | AUDIT | TR-105 transaction-local deletion assertion | At eligibility, exact rejected identity and all joinable detail are deleted. When attempt-owned this is a TR-114 subeffect; the code/event does not survive and the v2 aggregate retains no rejection reason/count dimension. |
| RC-094 | `CURRENCY_CODE_INVALID` | BLOCK | monetary fact/calculation | Code is not valid in the bound ISO-4217 registry or representation is invalid. Create no Money value; dependent scalar is `UNAVAILABLE`; infer no USD. |
| RC-095 | `MIXED_CURRENCY_AGGREGATION_PROHIBITED` | BLOCK | calculation/KPI projection | A scalar would combine different currencies. Return segmented currency results and no combined money/FX inference. |
| RC-096 | `RETENTION_CLOCK_CALCULATION_FAILED` | BLOCK | retention scheduler | Timezone/rule binding or DST resolution cannot produce the exact UTC instant. Never purge on an approximate/earlier fallback. |
| RC-114 | `SOURCE_IMPORT_ATTEMPT_PURGED` | AUDIT | TR-114 transaction-local `DOISourceImportAttemptRetentionEventV1` | At exact eligibility the complete attempt/edge/artifact graph is deleted atomically after the closed aggregate increment; this event/reason is deleted in the same commit and no identifying receipt/hash/lookup survives. |

Amend existing codes without renumbering:

- RC-002 `SOURCE_SCHEMA_UNRECOGNIZED`: owner is source import attempt/run; current attempt becomes `SCHEMA_REJECTED`, with no batch and zero OA reads; absent a legal retry the run becomes `FAILED`.
- RC-003 `SOURCE_ROW_INVALID_ORDER_NUMBER` is retained only as a compatibility-reserved registry entry and is not emitted by `synthetic-doi-queue-v0.1`; invalid A routes to RC-002 + RC-090 and a failed run/import attempt. RC-004/005 scalar-assignee/out-of-scope diagnostics are import-attempt aggregates only and never durable other-rep detail.
- RC-008 `SOURCE_ASSIGNEE_CONFLICT`: order-local block, zero OA reads for that order; it does not make a coherent batch/run `FAILED`.
- RC-009 `SOURCE_CHANGED_DURING_IMPORT`: attempt becomes `SOURCE_CHANGED`; absent a legal retry the run becomes `FAILED`; no coherent batch and zero OA reads.
- RC-079 `PURGE_SCHEDULED`: replace “closure +90 days” with `calendar90(verified terminal transition)` and persist exact UTC instant plus policy/tzdb versions.

## 9. State-transition matrix delta

Replace run transitions TR-001..TR-004 with:

| ID | From | To | Guard | Required effects |
|---|---|---|---|---|
| TR-001 | `NONEXISTENT` | `IN_PROGRESS` | Human accepted an explicit `Run DOI Review` with one locked tab confirmed | Immediately persist one run invocation and start exactly one ordinal-1 source-import attempt; no OA read. |
| TR-002 | `IN_PROGRESS` | `COMPLETED` | Coherent batch bound; processing terminal; zero order exceptions/blocks | Persist exact counts. Zero-work coherent batch is legal. |
| TR-003 | `IN_PROGRESS` | `COMPLETED_WITH_EXCEPTIONS` | Coherent batch bound; processing terminal; at least one order exception/block | Success count may be zero, including all-blocked/all-extraction-failed; preserve per-order allowed evidence; do not call run `FAILED`. |
| TR-004 | `IN_PROGRESS` | `FAILED` | Registered pre-OA run-level fatal source/integrity condition | Terminalize run/attempt; nullable batch; zero executable work, cases, evaluations, and OA reads. |

Add:

| ID | Entity/from | To/action | Guard | Required effects |
|---|---|---|---|---|
| TR-098 | source import `NONEXISTENT` | `STARTED` | TR-001 accepted invocation for ordinal 1, or exact human-confirmed retry while run is IN_PROGRESS, prior greatest ordinal is terminal non-success, and run has zero OA/work/case | Under the run lock allocate the next contiguous ordinal, opaque attempt ID, and attempt-owned command token; append immutable v2 attempt-start event with exact selected source/schema identities; zero OA reads. Replay of the same token/bytes is a no-op. |
| TR-099 | source import `STARTED` | `SUCCEEDED` plus immutable READY staged set | Structural validation, coherent read, identity calculation, safe batch binding, and complete compatible-TARGET_REP consolidation all succeed | In one commit, append the terminal import event and exactly one current-attempt READY `DOIStagedOrder` per non-conflicted unique TARGET_REP Order Number; bind deduplicated current-attempt TARGET_REP SourceRefs and attach `RC-006` exactly when compatible duplicates merged. No staged order may precede this commit. Conflicted numbers are excluded and owned only by TR-103. |
| TR-100 | source import `STARTED` | terminal non-success | Specific registered unreadable/schema/change/integrity failure, or exact human-confirmed pre-OA abort | Append the exact v2 failed event with RC-090+specific code or the separate aborted event with empty reasons; no partial content and zero OA reads. A source failure either accepts one legal next-ordinal TR-098 retry or drives TR-004. An abort leaves the run IN_PROGRESS and requires a later TR-098; it cannot drive an empty-reason run terminal. No implicit retry. |
| TR-101 | coherent identity, no matching batch | append new `READY` batch | Unique digest and canonical material verified | Append immutable batch using section 2.3 only; bind run/attempt. |
| TR-102 | coherent identity, matching batch | bind existing `READY` batch | Digest and canonical identity material/payload are byte-identical | Reuse batch without changing its fields; invocation still has a new run/attempt. Mismatch drives TR-100/RC-091. |
| TR-103 | no rejected record and no staged order for the conflicted number | `RETAINED_PENDING_RUN_TERMINAL` | Coherent import proves a valid-Order-Number TARGET_REP/non-TARGET_REP assignee conflict; a future schema may additionally prove its explicitly governed row-conflict cause | Append/reuse exactly one natural-keyed run-local `DOIRejectedSourceRecord` with complete cause/reason sets and current-attempt TARGET_REP refs; under manager v0.1 this is RC-008 only. Append no staged order/case/work and perform zero OA reads. |
| TR-104 | `RETAINED_PENDING_RUN_TERMINAL` | `RETAINED_UNTIL` | Associated run reaches any terminal status | Set immutable scheduling event to `calendar90(run.completed_at)`; emit RC-092; batch reuse cannot change it. |
| TR-105 | `RETAINED_UNTIL` | `DELETED_AFTER_RETENTION` | Current instant >= exact `purge_eligible_at` | Delete record/order/source refs/fingerprint/join keys atomically; RC-093 is transaction-local. When attempt-owned, this is a TR-114 subeffect; no separate rejection aggregate or reason dimension survives. |
| TR-113 | one or more retained source-batch references | release due owner references; retain or delete batch | Every due owner deletion/de-link is validated and locked; the already-committed aggregate is validated/preserved, or the caller TR-114's one aggregate delta is in the same locked transaction; evaluate the exact section 2.4 predicate after all due releases | Delete each due reference with its owner. If any reference remains, retain the byte-identical batch. If none remains, atomically delete the complete batch identity/fingerprints/hashes and every batch-identifying event/cache/log/export; retain only the closed non-identifying import aggregate. Independently invoked TR-113 applies zero aggregate delta. Any failure rolls back all owner/reference/batch effects and any caller-owned TR-114 delta. |
| TR-114 | terminal source-import-attempt graph retained | identifying graph absent; aggregate count incremented | Run is terminal; attempt outcome is one closed section 3.1 literal; stored deadline byte-equals `calendar90(run.completed_at)` under the bound policy/tzdb; `now >= source_import_attempt_purge_eligible_at`; attempt/run/batch/reference/aggregate rows and all dependent stores are locked; closed graph inventory and aggregate input validate | In one serializable transaction upsert exactly one v2 non-identifying aggregate count; construct and hash the exact transaction-local `DOISourceImportAttemptRetentionEventV1` with RC-114; delete projection, start/terminal/retention event graphs, attempt identity and its run/source links, token/ordinal/indexes, staged and due rejection/source-row details, failure detail, fingerprints/digests, caches/logs/temp exports/files/exceptions/backups, and every reverse lookup; release every attempt/staged/rejection-owned batch edge and invoke TR-113; release the attempt's run-identity reference; delete the run identity graph only when its own deadline is due and no closed run-identity reference remains; delete the retention event itself. Leave no tombstone/hash/receipt. Any failure rolls back the complete aggregate/event/deletion/reference transaction. |

Amend existing transitions:

- TR-009..TR-019: replace every `+90 days`/`purge_due_at` with section 6 `purge_eligible_at`; re-observation does not reset; reopen clears current deadline; reclosure calculates anew.
- TR-042: store `observation_purge_eligible_at = calendar90(observed_at)`, never elapsed-hour arithmetic.
- TR-043: when nominal observation expiry is the earliest live deadline, atomically delete a de-linked observation or the complete case-linked observation/link/volatile-wrapper target graph. When current case purge is earlier, TR-018/019 deletes that target graph inside case purge. A canceled case deadline after reopen cannot delete it. Preexisting sealed evaluation/opportunity commitments are non-resolvable/non-fresh until case purge.

Every unlisted source-import, run, source-batch-reference, rejection-retention, currency, or purge transition remains illegal and emits `STATE_TRANSITION_NOT_ALLOWED`. None authorizes OA mutation.

## 10. Deterministic synthetic-oracle delta

Existing IDs listed as “amend” remain one test each; IDs listed as “add” increase the derived synthetic count. Do not delete another test to preserve 127.

### 10.1 Amend existing source tests

| Test | Exact oracle |
|---|---|
| `SYN-SRC-001` | A suggestion/no confirmed accepted invocation creates no run/attempt/import/OA read. Every accepted explicit invocation immediately creates one run projected exactly as `status=IN_PROGRESS` with non-null `started_at`, null `completed_at`, null `run_purge_eligible_at`, null `source_batch_id`, and one attempt. The `RUN_INVOCATION_ACCEPTED` event omits completion time; the reduced projection materializes its required `completed_at` field as null. |
| `SYN-SRC-002` | `synthetic-doi-queue-v0.1` recognizes only the exact spreadsheet, role/title/gid map, A1/B1 blanks, E1/F1/G1 literals, A/B rows 2+, and no guessed alternative. |
| `SYN-SRC-003` | Any structural invariant failure terminalizes the current attempt with exact RC-002/RC-090, null batch, and zero work/cases/OA reads. Table-drive the explicit pre-OA decision: an accepted legal retry leaves the run `IN_PROGRESS` and starts only the next contiguous ordinal; when no legal retry is accepted, the run terminalizes `FAILED` with the same zero-work/zero-OA invariants. |
| `SYN-SRC-008` | TR-099 atomically appends one `READY` current-run staged outcome for two compatible TARGET_REP rows, retains the two deduplicated current-attempt refs, emits `RC-006`, and exposes no staged row before terminal success. |
| `SYN-SRC-009` | Two duplicate TARGET_REP A/B rows have the same canonical Order Number but deliberately different E:O values. TR-099 ignores E:O, merges them into one READY staged order with both TARGET_REP refs and RC-006, and emits no RC-007/rejected record/OA block. |
| `SYN-SRC-010` | Adding a non-TARGET_REP row for an existing TARGET_REP Order Number leaves the TARGET_REP-content hash unchanged, changes the conflict fingerprint and batch identity, and makes TR-103 append one rejected record with RC-008/current-attempt TARGET_REP refs; no staged order exists and OA reads are zero for that number. Removing the conflict changes identity and a later invocation independently stages READY through TR-099; no stale ref is reused. |
| `SYN-SRC-011` | Adding/changing/removing only unrelated non-TARGET_REP orders leaves both personal hashes and batch identity unchanged. Changing a TARGET_REP row changes the TARGET_REP hash. |
| `SYN-SRC-012` | Exact identical privacy-relevant state/schema reuses one batch but creates two runs and two source attempts; immutable batch fields do not change. |
| `SYN-SRC-015` | Proven source change terminalizes the current import attempt with RC-009/RC-090, no batch/work/case, and zero OA reads. An accepted legal pre-OA retry leaves the run `IN_PROGRESS` and allocates the next ordinal; absent that accepted retry, the run terminalizes `FAILED`. Replace all “no run” wording. |
| `SYN-SRC-016` | Mixed successful and order-exceptioned work is `COMPLETED_WITH_EXCEPTIONS`; successful snapshots/evaluations remain. |
| `SYN-SRC-017` | Unreadable/inaccessible, schema failure, and proven source change are table-driven: the current attempt terminalizes with the exact specific reason plus RC-090, null batch, and zero OA. For each class, an accepted legal retry preserves run `IN_PROGRESS` and starts only the next ordinal; absent that accepted retry, the run terminalizes `FAILED`. |

### 10.2 Add source/run tests

| Test | Exact oracle |
|---|---|
| `SYN-SRC-021` | A1/B1/E1/F1/G1 exact values and all three locked title/gid/role tuples pass. Changing any one fails RC-002/RC-090 with zero OA. |
| `SYN-SRC-022` | A/B rows beyond a stale Sheets filter range are included; E2:O values and a wider filter range are ignored. The same A/B records yield the same personal hashes. |
| `SYN-SRC-023` | With identical spreadsheet/tab/rows/conflicts, changing `schema_mapping_version` changes `source_batch_identity_sha256`; old batch is not reused. |
| `SYN-SRC-024` | All N TARGET_REP orders are individually blocked (including assignee conflicts), coherent batch exists, OA reads are zero, succeeded count is zero, and run is `COMPLETED_WITH_EXCEPTIONS`, never `FAILED`. |
| `SYN-SRC-025` | Table-drive a coherent READY batch where (a) all N permitted OA extraction attempts fail independently and (b) prior order work succeeds, then a post-OA action/value/link evidence collision rolls back only the affected transaction. Both runs are `COMPLETED_WITH_EXCEPTIONS`, not `FAILED`; (a) has no snapshots/evaluations and retains minimal attempts, while (b) preserves prior committed work and records the affected order exception. |
| `SYN-SRC-026` | Coherent source with no TARGET_REP rows and no row exceptions creates/reuses a valid empty personal batch and terminalizes `COMPLETED` with zero work/evaluations/OA reads. |
| `SYN-SRC-027` | Same candidate batch identity digest paired with contradictory canonical material/payload triggers RC-091 + RC-090 and terminalizes the current attempt as `FAILED`, with no overwrite/reuse/OA read. In the explicit no-accepted-retry fixture the run also terminalizes `FAILED`; a separately accepted legal pre-OA retry would instead keep the run `IN_PROGRESS` and allocate the next ordinal. The failed `DOISourceImportAttempt` projection and `SOURCE_IMPORT_FAILED` event carry `coherent_source_fingerprint_sha256=null` and null bound batch; `RUN_TERMINAL(FAILED)` in the final fixture carries `source_batch_id=null` and, by its closed schema, has no fingerprint member. None retains a candidate batch digest/preimage/fingerprint or undocumented `DOISourceBatchReference`; after existing owners release, TR-113 leaves no identifying batch lookup. |
| `SYN-SRC-028` | Two accepted invocations over an identical batch yield one batch, two distinct runs/attempts, and four independent canonical two-event chains (start plus exact predecessor-bound terminal). A stale/second terminal or envelope/payload reason mismatch is rejected with RC-111 and leaves every projection byte-identical. |
| `SYN-SRC-029` | A populated record with invalid A or non-scalar B fails the import with RC-002/090 and stores no raw cell/locator; valid non-TARGET_REP rows store no exact Order Number/name/locator; only privacy-safe attempt aggregates and allowlisted valid TARGET_REP conflict records can exist. |
| `SYN-SRC-030` | Static/contract inspection finds no claim of procedural browser reconnaissance certification and no fallback positional/header guessing beyond the locked mapping. |
| `SYN-SRC-031` | In separate coherent fixtures, table-drive A as exact numeric integer `123`, text `" 00123 "`, zero, negative, fraction, exponent-only, boolean, date/error, and precision-ambiguous numeric. The first two canonicalize identically to Order Number `"123"`; every invalid/ambiguous populated record fails the run/import with RC-002/090, creates no batch/work/case/evaluation, persists no raw value, and performs zero OA reads. |

### 10.3 Add currency tests

| Test | Exact oracle |
|---|---|
| `SYN-CUR-001` | Valid `USD 0.10 + USD 0.20` equals canonical `USD 0.30` using exact decimal/integer-coefficient arithmetic; binary floating point is absent. |
| `SYN-CUR-002` | Valid non-USD examples (`EUR 12.34`, `JPY 12`, `KWD 12.345`) pass under the bound registry and remain in their own currencies. |
| `SYN-CUR-003` | Lowercase/unknown code, wrong scale, exponent notation, NaN/infinity, negative zero, or excess precision creates no Money; RC-094; dependent value `UNAVAILABLE`; no USD fallback. |
| `SYN-CUR-004` | Same-currency intervention/resulting-order/alternate values aggregate only when both currency code and ISO-registry version/scale match exactly. A differing registry binding remains a separate segment or fails an attempted bucket move with RC-100; no silent rescale occurs. |
| `SYN-CUR-005` | USD and EUR verified contributions return separate currency projections; requested scalar total is `UNAVAILABLE` with RC-095; neither amount changes. |
| `SYN-CUR-006` | No FX/configured base-currency path exists; a supplied or inferred exchange rate is rejected as unauthorized input and cannot affect any stored amount/headline. |

### 10.4 Amend/add retention tests

| Test | Exact oracle |
|---|---|
| amend `SYN-ALT-013` and `SYN-RET-010` | Observation/link target nominal expiry uses `calendar90(observed_at)`; case-linked effective deletion is the minimum with current case purge. Target bytes/indexes and their separate target-owned volatile lifecycle wrappers delete atomically; no direct receipt survives. Preexisting evaluation/opportunity observation ID/hash commitments remain sealed/non-resolvable only until case purge and cannot satisfy freshness. Relationship revision survives only fully de-linked. |
| `SYN-RET-013` | Ordinary anchor `2026-01-15T10:30:00-05:00` yields local `2026-04-15T10:30:00-04:00` and stored UTC `2026-04-15T14:30:00Z`. Details exist immediately before and purge is eligible exactly then. |
| `SYN-RET-014` | Spring-gap anchor `2025-12-08T02:30:00-05:00` targets nonexistent `2026-03-08 02:30`; resolve to first valid `2026-03-08T03:00:00-04:00` = `2026-03-08T07:00:00Z`. Do not resolve to 03:30. |
| `SYN-RET-015` | Fall-overlap anchor `2026-08-03T01:30:00-04:00` targets ambiguous `2026-11-01 01:30`; choose later `-05:00` occurrence = `2026-11-01T06:30:00Z`. |
| `SYN-RET-016` | Reversible closure schedules exact calendar90. Reopen one instant before the deadline is accepted only when `CaseReopenPayloadV2` and `PURGE_CANCELED` each copy the complete locked `PriorClosureRetentionBindingV1` byte-for-byte and `canceled_purge_eligible_at` equals its active prior deadline; the accepted reopen preserves the same case identity, clears that deadline, and nothing deletes at the canceled instant. Omit or mutate any tuple member or supply only the prior projection hash and both appends roll back with the prior closure/deadline unchanged. A later verified closure creates a new independently calculated deadline; re-observing unchanged closure does not. |
| `SYN-RET-017` | Retention calculation without the bound timezone/rule version emits RC-096 and performs no approximate/early purge. |
| `SYN-RET-018` | A no-case TARGET_REP conflict creates no staged order/work item and one rejection graph. At run terminal, TR-104 appends exactly one retention-scheduling event with exact `{RC-092}` and `purge_eligible_at = calendar90(run.completed_at)`; RC-093 is absent before eligibility. At that instant TR-105 asserts exact transaction-local `{RC-093}` while deleting the record; RC-092 is not re-emitted and no other purge reason is present. On commit its Order Number, TARGET_REP refs, ID, scheduling event, fingerprint, join keys, RC-092/093 event/receipt/hash, and every reason dimension are absent from every store. Only the closed `DOISourceImportAggregateV2` month, attempt outcome class, and count may remain. |
| `SYN-RET-019` | Reusing the same batch before/after the record clock does not change the old rejection deadline and cannot revive the deleted record. A genuinely later attempt-local rejection has a distinct `(source_import_attempt_id,order_number)` record; attempts in one run share the common run-terminal clock, while a later run has its own clock. |
| `SYN-RET-020` | Case terminal `2026-01-01T12:00:00-05:00` gives case purge `2026-04-01T12:00:00-04:00`; a linked observation at `2026-03-01T12:00:00-05:00` has later nominal expiry. It is deleted with the case on April 1. If the case legally reopens before April 1, that deadline is canceled and the observation remains only until its nominal deadline or a new earlier case purge. |

### 10.5 Add source-batch-reference tests

| Test | Exact oracle |
|---|---|
| `SYN-BATCH-REF-001` | One coherent batch is simultaneously owned by one run, one successful import attempt, two staged records, one no-case rejection, and one case binding. Exactly six unique section 2.4 reference rows exist with byte-valid canonical objects/digests and exact owner foreign keys; duplicate creation is an idempotent no-op. |
| `SYN-BATCH-REF-002` | Release the run, attempt, and one staged owner while another staged owner, rejection, and case binding remain. TR-113 deletes exactly the three due owner/reference graphs, the last-reference predicate is false, and the original batch bytes/fingerprints remain unchanged. |
| `SYN-BATCH-REF-003` | Release the final retained case/source owner after every other owner is already gone. In the same TR-113 transaction the predicate becomes true and the batch ID, identity bytes/hash, TARGET_REP hash, conflict fingerprint/cardinality, counts, events/caches/logs/exports, and reference rows are all absent; no tombstone or reversible digest survives. |
| `SYN-BATCH-REF-004` | Reuse one byte-identical batch from two runs whose attempt, staged, rejection, and case owners have different retention lifetimes. Each owner has its own reference. Deleting the first run graph retains the batch; only deletion of the last owner across both invocations deletes it. No lifetime is extended by reuse. |
| `SYN-BATCH-REF-005` | In a TR-114-bundled fixture, inject failure after due-owner deletion, the sole caller-owned aggregate upsert, predicate evaluation, and each batch-cleanup step; every branch rolls back owner/reference/batch plus that aggregate delta. In a later independent-owner TR-113 fixture, assert zero aggregate delta and inject the same predicate/cleanup failures; owner/reference/batch rolls back while the already-committed aggregate remains byte-identical. Neither branch permits an orphan reference, zero-reference batch, partial fingerprint, or duplicate aggregate count. |
| `SYN-BATCH-REF-006` | Inspect all persistence, event, cache, log, error, export, backup, and lookup surfaces after final reference release, including a prior RC-091 failed import. No source-batch ID/hash, coherent-source fingerprint on the failed attempt/event, TARGET_REP/conflict fingerprint, Order Number set, predecessor, deletion receipt, tombstone, or reconstructable lookup key exists. The failed attempt/event has null fingerprint and null batch; exact replay creates nothing. |
| `SYN-BATCH-REF-007` | Before deleting the last reference, run TR-114 for a fixture with known local month/outcome; then delete all identifying owners. Exactly one closed v2 aggregate row `{version,local_calendar_month,attempt_outcome_class,attempt_count}` survives with count one, and it contains none of the forbidden identity/hash/reason/source/schema/tab/actor/free-text/drill-through fields. |

Every test asserts `outbound_oa_mutation_request_count = 0`; every named failed source-import test also asserts `oa_read_count = 0`.

## 11. Implementation-handoff checklist

The handoff must state all of the following as release-blocking:

1. Implement only the exact fixed `synthetic-doi-queue-v0.1` mapping above; procedural browser reconnaissance remains blocked/not certified.
2. Persist a run at accepted invocation and mandatory distinct ordinal-1 source-import attempt; permit only the exact sequential pre-OA retry rule, and do not conflate source attempts with OA extraction.
3. Do not permit OA reads until source attempt success and safe batch binding.
4. Use both TARGET_REP-row hash and conflict fingerprint plus schema version in batch identity; move invocation/other-rep counts out of the immutable batch.
5. Keep conflict/no-case exact identities run-local, purge them at `calendar90(run terminal)`, and never extend them by batch reuse.
6. Persist one explicit `DOISourceBatchReference` for every retained run, coherent attempt, staged/no-case record, and case binding; release it only with its owner. TR-113 must atomically delete the complete identifying batch when the exact last-reference predicate becomes true, leaving no batch hash/tombstone and only the closed v2 month/outcome/count aggregate.
7. Classify all-blocked/all-order-failed coherent execution as `COMPLETED_WITH_EXCEPTIONS`; reserve `FAILED` for registered pre-OA run-level fatal source execution.
8. Use exact ISO-4217 Money everywhere, segment mixed currencies, and provide no FX conversion.
9. Use the versioned America/New_York local-calendar algorithm and exact DST rules for every 90-day clock; use `purge_eligible_at` consistently.
10. Assign every terminal attempt, successful or not, the exact common `calendar90(run.completed_at)` deadline; implement TR-114's complete graph/event/reference deletion, rollback, idempotency, and no-tombstone rules.
11. Keep staged records/source-row refs attempt-owned. Before lifecycle append, create the privacy-minimized case admission proof; never bind a staged attempt record from a retained case event.
12. Persist closed run-identity references only for attempts, staged/rejection owners, and run-work graphs; never for a bare case-source binding. Retain/delete the run strictly by its due last-reference predicate.
13. Delete a case-linked alternate observation at the earlier current case purge or nominal observation expiry; never treat retention as freshness. Preserve permanent OA 100% read-only controls and tests.

## 12. Mandatory cross-document replacements

The integrator must search every package artifact and remove or replace all surviving variants of these old statements:

- batch identity that omits `schema_mapping_version` or `assignee_conflict_fingerprint_sha256`;
- any claim that batch identity/fingerprints may survive after the final explicit retained `DOISourceBatchReference` owner is deleted, or any indirect/undocumented reference owner;
- invocation-specific actor/time, total/out-of-scope counts, rejected identities, or change-detection fields modeled as immutable batch identity/payload;
- “other-rep rows never affect batch identity” without the conflict-relevant TARGET_REP-order exception;
- any assignee conflict making the whole coherent batch/run `FAILED` rather than blocking only that order;
- source schema/change/unreadable failure creating no run, optionally creating a run, creating an executable batch, or permitting an OA read;
- `COMPLETED_WITH_EXCEPTIONS` requiring at least one successful evaluation;
- `FAILED` defined merely as zero successful items after coherent execution;
- `Money {currency: "USD", minor_units: ...}`, `currency: USD`, a USD-only KPI, implicit base currency, mixed-currency sum, or inferred FX;
- `purge_due_at`, `terminal_closed_at + 90 days`, `observed_at + 90 days`, elapsed 2,160-hour arithmetic, or any unversioned timezone calculation;
- independent alternate-observation expiry that can outlive an earlier linked-case purge;
- rejected/no-case exact source identity stored indefinitely under a reusable source batch;
- any success-only attempt retention, failed/aborted attempt without the common run-terminal clock, or elapsed-hours/attempt-completion anchor;
- a v1 source-import aggregate containing run count, ready/rejected/duplicate counts, tab role, schema version, reason, identifier, hash, or drill-through rather than the exact v2 month/outcome/count schema;
- a run event/projection containing one attempt ID/manifest, `UNIQUE(run_id)` attempt cardinality, or a deterministic post-purge attempt lookup;
- a staged record/source-row reference transferred into a case lifecycle graph rather than the privacy-minimized case admission proof;
- `DOICaseSourceBinding` as a run-identity reference owner; only a retained `RUN_WORK_GRAPH` may carry the case-lifetime run need;
- any failed-attempt projection/event, spreadsheet/tab/schema/operator/timestamp/log/cache/export/index/reverse lookup, or transaction-local purge event/hash surviving TR-114;
- the old 127-test, 88-reason, or 82-transition count presented as a target after registry expansion;
- any statement that browser reconnaissance of the fixed manager sheet was performed or certified.

The technical specification, machine contract, reason registry, transition matrix, acceptance matrix, synthetic requirements, implementation handoff, historical reports/coverage metadata, traceability, and final SHA-256 inventory must all report the final derived counts and identical semantics.

## 13. Round-4 closed source-import-attempt retention and deletion contract

This section is the governing v0.1.5 replacement for any earlier success-only, optional, indefinite, or attempt-completion-anchored source-import retention wording.

### 13.1 Exact attempt and run deadlines

For every terminal attempt in the closed section 3.1 outcome registry:

```text
source_import_attempt_purge_eligible_at = calendar90(associated_DOIRun.completed_at)
run_purge_eligible_at                   = calendar90(associated_DOIRun.completed_at)
```

Both values use the one exact section 6 `America/New_York` wall-time/DST/tzdb algorithm and are byte-identical across all attempts of one run. Before `DOIRun` terminalizes, its completion time and every attempt/run purge deadline are null. A terminal attempt may therefore wait without a deadline while its run is still `IN_PROGRESS`, including an `ABORTED_PRE_OA` attempt awaiting a later ordinal. The terminal-run transaction requires all attempts terminal, calculates the deadline once, validates it independently for each attempt, and materializes the joined attempt/run projections atomically. No attempt outcome is exempt.

### 13.2 Closed run-identity ownership and last reference

`DOIRunEventV2` and `DOIRun` retain `source_import_attempt_count` only; they never contain an attempt ID, list/manifest, ordinal, token, or attempt-event hash. Every lawful retained graph that still needs `run_id` owns one exact row:

```yaml
run_identity_reference_schema_version: doi-run-identity-reference/v1
run_identity_reference_id: Sha256
run_id: OpaqueId
reference_owner_type: SOURCE_IMPORT_ATTEMPT | STAGED_SOURCE_RECORD | NO_CASE_REJECTED_RECORD | RUN_WORK_GRAPH
reference_owner_id: OpaqueId
created_at: Timestamp
content_sha256: Sha256
```

The identity is `SHA256(UTF8("doi-run-identity-reference-id/v1\n") || UTF8(RFC8785({"run_identity_reference_identity_schema_version":"doi-run-identity-reference-identity/v1","run_id":run_id,"reference_owner_type":reference_owner_type,"reference_owner_id":reference_owner_id})))`. Full content is every shown field except `content_sha256`, hashed under `doi-run-identity-reference/v1\n`. Enforce unique ID, unique `(run_id,reference_owner_type,reference_owner_id)`, exact owner FK, canonical-byte comparison, and owner-cascade deletion. The immutable reference carries no duplicated deadline; due/non-due state is resolved from its locked owner authority. Attempt/staged/rejection owner IDs disappear with their graphs. `RUN_WORK_GRAPH` is the only case-lifetime owner: it is required while a retained extraction/snapshot/evaluation chain resolves its exact `DOIRunOrderWorkItem.run_id`, contains no attempt ID, and takes the governing case/work purge deadline. `DOICaseSourceBinding` and `DOICaseSourceAdmissionProofV1` contain no run ID and therefore MUST NOT own or extend a run-identity reference; their separate source-batch ownership is unchanged. A non-due retained owner prevents run deletion; it never authorizes indefinite retention after that owner reaches its governed deletion boundary.

Create a `SOURCE_IMPORT_ATTEMPT` run reference atomically with each TR-098 attempt start; a `STAGED_SOURCE_RECORD` reference with each TR-099 staged record; a `NO_CASE_REJECTED_RECORD` reference with each TR-103 rejection; and one `RUN_WORK_GRAPH` reference when the retained work item/chain is created. Delete each only with its exact owner. Same owner tuple/bytes is idempotent; a changed binding is RC-111 and a proven digest collision RC-103. No implicit event/log or source-batch reference counts as a run-identity owner.

After all owner releases selected in the locked transaction:

```text
run_last_reference_predicate(target_run_id) :=
  NOT EXISTS retained DOIRunIdentityReference AS r
  WHERE r.run_id = target_run_id
```

Delete the complete run-identity graph only when `now >= run_purge_eligible_at` and that predicate is true. If any reference remains—including a later-due case/work owner or another attempt not yet processed—the run projection/events/indexes remain byte-identical, but because v2 stores no attempt locator they cannot reconstruct a deleted attempt. When the final owner later deletes, its transaction re-evaluates the predicate and atomically deletes `run_id`, v2 run events/projection, actor/operator, source connector/tab/schema fields, timestamps, counts/detail, run-owned batch reference, indexes/caches/logs/exports/exceptions, and every reverse lookup, then invokes TR-113. No run tombstone/hash/receipt survives.

### 13.3 Closed attempt-deletion graph

At TR-114 eligibility the complete deletion set is closed and includes:

1. `DOISourceImportAttempt` projection and the complete v2 start/terminal event stream;
2. `source_import_attempt_id`, retained `run_id` link, attempt ordinal, command-token preimage/hash, unique/index rows, and owner-derived stream identities;
3. spreadsheet ID/name or connector identity; selected tab role/title/gid; attempted schema mapping version; confirmation/operator identity; confirmation/start/completion/run-completion timestamps;
4. outcome, failure reason/detail payload, all attempt reason/event history, coherent-source fingerprint, source revision/range digest, and every partial/candidate digest if present in an invalid legacy row;
5. attempt-owned staged records, TARGET_REP source-row references, source locators, attempt-specific rejected/no-case graphs due at the common boundary, and their scheduling events;
6. the successful attempt's `SOURCE_IMPORT_ATTEMPT`, staged, and due rejection `DOISourceBatchReference` rows, or no batch edge for all non-success outcomes;
7. every cache, materialized view, search/index entry, retry/idempotency key, temporary export/file, backup, log, trace, metric exemplar, exception/crash artifact, dead-letter item, and diagnostic containing attempt/run/source identity; and
8. every reverse lookup or drill-through from an aggregate, batch, run, event, index, or log to the attempt.

An implementation may add no identifying child outside this list. A discovery scan that finds an unclassified child fails closed before aggregate mutation or deletion. TR-114 releases rather than deletes a shared source batch when another explicit batch owner remains; TR-113 deletes the batch only at its own exact last reference. A case lifecycle target cannot dangle because it binds `DOICaseSourceAdmissionProofV1`, never an attempt-owned staged record.

### 13.4 Exact transaction-local retention event

The purge event is a separate non-case lifecycle event. It is **not** a `DOIOrderLifecycleEventV2`, does not change the 56-kind case-lifecycle union, and does not add a case payload schema. It exists only in the TR-114 transaction write set and is deleted with the attempt graph before commit.

```yaml
source_import_attempt_retention_event_id: Sha256
event_schema_version: doi-source-import-attempt-retention-event/v1
source_import_attempt_id: OpaqueId
run_id: OpaqueId
attempt_ordinal: integer >= 1
stream_id: Sha256
stream_sequence: 1
previous_event_id: null
previous_event_content_sha256: null
event_type: SOURCE_IMPORT_ATTEMPT_PURGE_FINALIZED
occurred_at: Timestamp
recorded_at: Timestamp
actor_kind: SYSTEM
actor_id: null
provenance: SYSTEM_VERIFIED
reason_codes: [RC-114]
payload: SourceImportAttemptPurgePayloadV1
payload_content_sha256: Sha256
content_sha256: Sha256
```

The stream identity is `SHA256(UTF8("doi-source-import-attempt-retention-stream-id/v1\n") || UTF8(RFC8785({"source_import_attempt_id":source_import_attempt_id,"source_import_attempt_retention_stream_identity_schema_version":"doi-source-import-attempt-retention-stream-identity/v1"})))`. The event ID is `SHA256(UTF8("doi-source-import-attempt-retention-event-id/v1\n") || UTF8(RFC8785({"source_import_attempt_id":source_import_attempt_id,"source_import_attempt_purge_eligible_at":source_import_attempt_purge_eligible_at,"source_import_attempt_retention_event_identity_schema_version":"doi-source-import-attempt-retention-event-identity/v1","terminal_attempt_event_id":terminal_attempt_event_id})))`. Resolve and byte-compare both before allocation.

`SourceImportAttemptPurgePayloadV1` has exactly these required, non-null members and no others:

```yaml
payload_schema_version: doi-source-import-attempt-purge-payload/v1
transition_id: TR-114
terminal_attempt_event_id: OpaqueId
terminal_attempt_event_content_sha256: Sha256
attempt_outcome_class: closed section 3.1 literal
run_terminal_event_id: OpaqueId
run_terminal_event_content_sha256: Sha256
run_completed_at: Timestamp
retention_policy_version: doi-retention-calendar90-ny/v1
timezone_id: America/New_York
timezone_database_version: VersionId
local_calendar_rule_identifier: calendar90-america-new-york/v1
source_import_attempt_purge_eligible_at: Timestamp
aggregate_schema_version: doi-source-import-aggregate/v2
aggregate_local_calendar_month: YYYY-MM
aggregate_attempt_outcome_class: closed section 3.1 literal
aggregate_count_delta: 1
attempt_owned_batch_reference_state: PRESENT | ABSENT
attempt_owned_batch_reference_effect: RELEASE | NOT_APPLICABLE
run_identity_reference_effect: RELEASE
run_identity_last_reference_result: RETAIN_RUN | DELETE_RUN
delete_attempt_projection: true
delete_attempt_event_graph: true
delete_attempt_owned_staged_and_rejected_detail: true
delete_attempt_source_identity_and_artifacts: true
delete_attempt_indexes_and_reverse_lookups: true
delete_transient_retention_event: true
leave_identifying_tombstone: false
result_attempt_state: ABSENT
result_run_state: RETAINED | ABSENT
```

`SUCCEEDED` requires `PRESENT/RELEASE`; every other outcome requires `ABSENT/NOT_APPLICABLE`. The aggregate outcome equals the attempt outcome and its month is derived from `run_completed_at` in the bound timezone. `RETAIN_RUN` pairs only with `result_run_state=RETAINED` and a false last-reference predicate; `DELETE_RUN` pairs only with `result_run_state=ABSENT`, a due run, and a true predicate. Every boolean/literal is fixed as shown. The only null envelope members are actor and the two sequence-1 predecessor fields; omission is not a null substitute, and every extension member is forbidden.

The trusted transaction clock separately MUST satisfy `current_instant >= source_import_attempt_purge_eligible_at`. The canonical event's `occurred_at` is exactly the stored `source_import_attempt_purge_eligible_at` (the governed eligibility fact), while `recorded_at` is assigned once from that transaction's trusted persistence clock after all pre-delete validations and MUST be `>= current_instant`. Neither is caller-selected. The stream ID, event ID, and payload bytes/hash are deterministic even when a worker runs late; the complete event bytes/hash are deterministic for the assigned `recorded_at`. If a transaction rolls back, no event bytes or identity survive, and a later retry may lawfully receive a later `recorded_at` and corresponding full-event hash while preserving the same stream ID, event ID, payload, and deletion result. A host clock/default timezone cannot alter the stored deadline. Before the boundary no event ID/stream/payload/hash or aggregate delta is constructed. At or after it, a retry while the graph is locked reconstructs the same canonical eligibility identity and payload; after a committed absence it constructs nothing.

```text
payload_content_sha256 = SHA256(
  UTF8("doi-source-import-attempt-purge-payload/v1\n") ||
  UTF8(RFC8785(complete_payload)))

content_sha256 = SHA256(
  UTF8("doi-source-import-attempt-retention-event/v1\n") ||
  UTF8(RFC8785(complete_event_without_content_sha256)))
```

TR-114 locks the attempt projection/terminal event, run projection/terminal event, all attempt/run identity references, affected batch/reference sets, aggregate row, and every closed child store. It validates the graph and due guard; constructs/hashes the event; upserts aggregate count `+1`; deletes all attempt children and batch edges; invokes TR-105/113 as applicable; releases the attempt run-identity reference; conditionally deletes the run graph; deletes this retention event itself; and commits. Failure before aggregate finalization, after its in-transaction upsert, during any graph deletion/reference release, or while deleting the transient event rolls back the entire pre-transaction state byte-for-byte. The aggregate update is never externally visible before commit.

Concurrent/repeated purge is idempotent without a tombstone: one transaction locks and deletes the retained graph; a waiter that subsequently finds no attempt performs no aggregate increment, event construction, lookup persistence, or error receipt. A transaction may not use an aggregate count/hash to infer that a particular attempt once existed.

### 13.5 Fixed deletion-event vector

This serialization-only vector uses reserved synthetic identities and an inaccessible/unreadable failed attempt with no batch edge. `run_completed_at=2026-01-15T15:30:00Z` is local 10:30 EST; exact `calendar90` is `2026-04-15T14:30:00Z` (local 10:30 EDT). The vector fixes:

| Value | Expected lowercase SHA-256 |
|---|---|
| retention stream ID | `b14b67e59e765b28d927b12a6d59b161944dd27c06dbe13ce3439000f3233513` |
| retention event ID | `86b3208fb50e2352a65a49b4a74016d00956fd9109f72030071848cb500aac90` |
| purge payload hash | `2ad1678cdad8d10be9b4bbb2b46d9b7158c7635638356982b8ce120d7f4c7e32` |
| full retention event hash | `738fa8d9ac327be19c099404891e9d18f47a224d8e26c1006e6faa544241c4fe` |

Exact canonical payload bytes:

```json
{"aggregate_attempt_outcome_class":"INACCESSIBLE_OR_UNREADABLE","aggregate_count_delta":1,"aggregate_local_calendar_month":"2026-01","aggregate_schema_version":"doi-source-import-aggregate/v2","attempt_outcome_class":"INACCESSIBLE_OR_UNREADABLE","attempt_owned_batch_reference_effect":"NOT_APPLICABLE","attempt_owned_batch_reference_state":"ABSENT","delete_attempt_event_graph":true,"delete_attempt_indexes_and_reverse_lookups":true,"delete_attempt_owned_staged_and_rejected_detail":true,"delete_attempt_projection":true,"delete_attempt_source_identity_and_artifacts":true,"delete_transient_retention_event":true,"leave_identifying_tombstone":false,"local_calendar_rule_identifier":"calendar90-america-new-york/v1","payload_schema_version":"doi-source-import-attempt-purge-payload/v1","result_attempt_state":"ABSENT","result_run_state":"ABSENT","retention_policy_version":"doi-retention-calendar90-ny/v1","run_completed_at":"2026-01-15T15:30:00Z","run_identity_last_reference_result":"DELETE_RUN","run_identity_reference_effect":"RELEASE","run_terminal_event_content_sha256":"2222222222222222222222222222222222222222222222222222222222222222","run_terminal_event_id":"run-terminal-syn-0001","source_import_attempt_purge_eligible_at":"2026-04-15T14:30:00Z","terminal_attempt_event_content_sha256":"1111111111111111111111111111111111111111111111111111111111111111","terminal_attempt_event_id":"source-import-terminal-syn-0001","timezone_database_version":"2026a","timezone_id":"America/New_York","transition_id":"TR-114"}
```

Exact canonical event bytes excluding only `content_sha256`:

```json
{"actor_id":null,"actor_kind":"SYSTEM","attempt_ordinal":1,"event_schema_version":"doi-source-import-attempt-retention-event/v1","event_type":"SOURCE_IMPORT_ATTEMPT_PURGE_FINALIZED","occurred_at":"2026-04-15T14:30:00Z","payload":{"aggregate_attempt_outcome_class":"INACCESSIBLE_OR_UNREADABLE","aggregate_count_delta":1,"aggregate_local_calendar_month":"2026-01","aggregate_schema_version":"doi-source-import-aggregate/v2","attempt_outcome_class":"INACCESSIBLE_OR_UNREADABLE","attempt_owned_batch_reference_effect":"NOT_APPLICABLE","attempt_owned_batch_reference_state":"ABSENT","delete_attempt_event_graph":true,"delete_attempt_indexes_and_reverse_lookups":true,"delete_attempt_owned_staged_and_rejected_detail":true,"delete_attempt_projection":true,"delete_attempt_source_identity_and_artifacts":true,"delete_transient_retention_event":true,"leave_identifying_tombstone":false,"local_calendar_rule_identifier":"calendar90-america-new-york/v1","payload_schema_version":"doi-source-import-attempt-purge-payload/v1","result_attempt_state":"ABSENT","result_run_state":"ABSENT","retention_policy_version":"doi-retention-calendar90-ny/v1","run_completed_at":"2026-01-15T15:30:00Z","run_identity_last_reference_result":"DELETE_RUN","run_identity_reference_effect":"RELEASE","run_terminal_event_content_sha256":"2222222222222222222222222222222222222222222222222222222222222222","run_terminal_event_id":"run-terminal-syn-0001","source_import_attempt_purge_eligible_at":"2026-04-15T14:30:00Z","terminal_attempt_event_content_sha256":"1111111111111111111111111111111111111111111111111111111111111111","terminal_attempt_event_id":"source-import-terminal-syn-0001","timezone_database_version":"2026a","timezone_id":"America/New_York","transition_id":"TR-114"},"payload_content_sha256":"2ad1678cdad8d10be9b4bbb2b46d9b7158c7635638356982b8ce120d7f4c7e32","previous_event_content_sha256":null,"previous_event_id":null,"provenance":"SYSTEM_VERIFIED","reason_codes":["RC-114"],"recorded_at":"2026-04-15T14:30:01Z","run_id":"SYN-DOI-RUN-0001","source_import_attempt_id":"SYN-DOI-SOURCE-IMPORT-ATTEMPT-0001","source_import_attempt_retention_event_id":"86b3208fb50e2352a65a49b4a74016d00956fd9109f72030071848cb500aac90","stream_id":"b14b67e59e765b28d927b12a6d59b161944dd27c06dbe13ce3439000f3233513","stream_sequence":1}
```

The all-`1`/all-`2` predecessor target hashes are opaque already-validated synthetic inputs for serialization only. `SYN-IMPORT-RET-004` and `-007` separately construct real terminal attempt/run authorities. No vector byte survives a committed purge.

### 13.6 Deterministic Round-4 oracle family

The following 22 tests form the new collision-free `SYN-IMPORT-RET` family and are release-blocking:

| Test | Exact oracle |
|---|---|
| `SYN-IMPORT-RET-001` | A successful attempt one instant before its exact deadline retains its complete graph; TR-114 emits nothing and aggregate count is unchanged. |
| `SYN-IMPORT-RET-002` | The same successful graph exactly at the deadline deletes atomically, releases its batch edge, emits/asserts RC-114 only inside the deleted retention event, and increments exactly one aggregate count. |
| `SYN-IMPORT-RET-003` | A failed attempt one instant before its exact deadline retains its complete privacy-minimized graph with no early aggregate/event/deletion. |
| `SYN-IMPORT-RET-004` | A constructed failed terminal attempt/run exactly at deadline regenerates the closed payload/event hashes, deletes every listed byte, and leaves only the exact v2 aggregate. |
| `SYN-IMPORT-RET-005` | `SCHEMA_REJECTED` with RC-002/090, no batch, and zero OA is deleted exactly at the common deadline, including spreadsheet/tab/schema/operator/event detail. |
| `SYN-IMPORT-RET-006` | `SOURCE_CHANGED` with RC-009/090 deletes its revision/range/change evidence, event history, logs, and reverse lookups at the common deadline. |
| `SYN-IMPORT-RET-007` | `INACCESSIBLE_OR_UNREADABLE` with RC-089/090 constructs the fixed vector authorities and deletes all failure detail with no batch edge. |
| `SYN-IMPORT-RET-008` | Table-drive every non-success outcome with null batch/fingerprint and prove TR-114 does not require or invent a batch reference. An intermediate `ABORTED_PRE_OA` fixture has a later terminal ordinal/run before receiving the same common deadline. |
| `SYN-IMPORT-RET-009` | `SUCCEEDED` requires exactly one attempt-owned batch reference; TR-114 releases it and TR-113 retains or deletes the batch solely from remaining explicit owners. |
| `SYN-IMPORT-RET-010` | A run with ordinals 1 failed and 2 succeeded has equal deadlines. Purging ordinal 1 while ordinal 2 remains retains the run; a parallel fixture with all attempts gone but a later-due `RUN_WORK_GRAPH` reference needed by a retained extraction/snapshot/evaluation chain also retains the run without any deleted-attempt locator. A bare case-source binding creates no run reference. |
| `SYN-IMPORT-RET-011` | In a no-other-owner fixture, purging the final attempt/reference after the run deadline makes the last-reference predicate true and atomically deletes the complete run identity/event/reference graph. In the later-due-owner fixture, deleting that final owner later does the same. |
| `SYN-IMPORT-RET-012` | After purge exactly one `{v2,local month,outcome,count}` aggregate row survives; closed-schema inspection rejects every identifying/hash/drill-through/extra field. |
| `SYN-IMPORT-RET-013` | Seed cache, index, log, trace, temp export/file, backup, exception/dead-letter, staged row/ref, and reverse-lookup variants; all are absent after one commit. |
| `SYN-IMPORT-RET-014` | Inject failure before aggregate upsert/finalization; attempt/run/batch/reference/aggregate/event state remains byte-identical. |
| `SYN-IMPORT-RET-015` | Inject failure after the in-transaction aggregate upsert but before graph deletion; rollback removes the delta/event and restores the complete graph. |
| `SYN-IMPORT-RET-016` | Inject failure during each attempt/staged/rejection batch-reference release and TR-113 branch; rollback restores every owner/reference/batch/aggregate byte. |
| `SYN-IMPORT-RET-017` | Inject failure at every ordered deletion step, including transient-event deletion; each restores the complete pre-transaction projection/events/indexes/artifacts/edges and no aggregate delta is visible. |
| `SYN-IMPORT-RET-018` | Replay/concurrent purge after committed absence is a no-op: no duplicate count, event, tombstone, clock, ID, hash, or lookup appears. |
| `SYN-IMPORT-RET-019` | Exhaustive post-purge scan proves no deleted attempt/source identifier, event/hash/predecessor, token/ordinal index, source-row reference, attempt-owned batch edge, or reversible lookup/tombstone survives. In a parallel retained `RUN_WORK_GRAPH` fixture, work/extraction/snapshot/evaluation may retain only their governed `run_id`, `source_batch_id`, and case admission-proof binding; they contain zero `source_import_attempt_id`, staged-order ID, TARGET_REP SourceRef, spreadsheet/tab identity, or other attempt/source-row locator. Final work-owner deletion removes the remaining run identity. |
| `SYN-IMPORT-RET-020` | Run the same fixtures under UTC, Los Angeles, and Tokyo host defaults; stored deadline, vector bytes/hashes, and deletion instant remain identical to the bound New York/tzdb result. |
| `SYN-IMPORT-RET-021` | Table-drive the existing ordinary, spring-gap, and fall-overlap calendar vectors for successful and failed attempts; gap resolves first valid local instant and overlap chooses the later instant, never elapsed hours. |
| `SYN-IMPORT-RET-022` | Table-drive all six outcome literals over identical terminal-run anchors; every attempt receives the byte-identical policy/tzdb/deadline and TR-114 graph. Unknown outcome/version, missing/extra payload member, wrong null, contradictory batch/run-result branch, or bad hash fails before aggregate/persistence/deletion. |

All 22 tests assert `outbound_oa_mutation_request_count=0`; source-failure/abort fixtures also assert `oa_read_count=0`. They do not access a source workbook, production order, or live OA.
