
> **Sanitized supporting reference.** This file is a mechanically sanitized derivative of
> source material supplied for the synthetic proof of concept. Historical status/freeze
> language is nonbinding. The curated files under `specs/` govern. No production-system
> access or real-data use is authorized by this reference.

# Synthetic Sales Assist DOI v0.1.5 — Machine Contract

Authority patch: v0.1.5.4 HumanFactUsageKind erratum candidate; independent audit required; not a freeze declaration.

Status: independent-audit remediation candidate; independent re-audit required; offline specification work only  
Contract version: 0.1.5  
Rules authority: DOI Technical Specification v0.1.5 remediation candidate and its locked 2026-08-09 remediation decisions  
Operational timezone: America/New_York

## 1. Normative language and safety boundary

MUST, MUST NOT, SHOULD, and MAY are normative.

Synthetic Order Portal (OA) is permanently read-only. The future architectural operation classes are:

Observe → Search → Navigate → Extract → Validate → Calculate → Classify → Recommend → Report.

The v0.1.5 offline module contains no live OA/browser adapter, host permission, network path, session/cookie access, or navigation/extraction runtime. Its exact permitted fixture-local capabilities and complete prohibited manifest/helper surface are the closed `DOI_OA_CAPABILITY_POLICY_v0.1.5.md`. The source, dependency graph, manifest fragments/final manifest, registries, source maps, and built output MUST pass that policy's alias-aware static scan and mutation canaries before packaging. The DOI module MUST NOT expose or call an OA mutation endpoint, generic request helper, arbitrary selector/click/type/fill/keyboard/form helper, page-script execution, note writer, order editor, shipment editor, product editor, credit editor, rep editor, payment editor, customer editor, or any semantic wrapper/computed alias capable of changing OA state. A future OA read path exists only under a separately frozen contract; side-effect uncertainty fails before dispatch.

Every DOI user action defined in this contract changes only DOI-owned records. All order splits, substitutions, cancellations, releases, DEDUPE notes, rep changes, customer contacts, and other OA business actions are performed manually outside Sales Assist by an authorized human.

No unattended browsing, polling, scheduled OA check, periodic refresh, or silently selected manager-report tab is legal.

## 2. Shared representation

### 2.1 Primitive types

| Type | Exact representation and invariant |
|---|---|
| OpaqueId | Non-empty immutable identifier; unique within its entity type. The generation algorithm is implementation-local and MUST NOT encode customer data. |
| VersionId | Non-empty immutable string identifying an exact schema, extractor, calendar, or rules-engine version. |
| Timestamp | RFC 3339 instant. Display converts to America/New_York; storage MUST preserve the instant. |
| Date | ISO 8601 calendar date. |
| OrderNumber | Exact canonical order identifier accepted by the versioned source/OA validator. Trimming is allowed; fuzzy matching, approximate numeric coercion, and customer-derived identity are forbidden. |
| ESNumber | Canonical catalog product identifier. Equality uses exact canonical equality. |
| MFGNumber | Canonical manufacturer/OE identifier under a versioned normalization rule. |
| Quantity | Non-negative exact decimal or integer according to the source field contract; floating-point storage is forbidden. |
| Money | Object `{amount_decimal, currency_code, iso_4217_registry_version}`. `currency_code` is exactly three uppercase ASCII letters and a member of the bound versioned ISO-4217 registry. `amount_decimal` is a canonical exact base-10 string at the registry-defined scale, backed by arbitrary-precision integer-coefficient arithmetic; exponent notation, rounding, truncation, binary floating point, inferred FX, and cross-currency summing are forbidden. Source merchandise values MUST be non-negative; signed aggregate deltas MAY be negative only where explicitly allowed. |
| Sha256 | Lowercase 64-character SHA-256 hex digest. |
| SourceRef | Opaque, relocatable source locator containing source file ID, tab/document section, and row/range or provider locator. It MUST NOT contain customer data or OA page content. |

The exact OrderNumber syntax, source column names, OA selectors, and field locators are versioned extraction configuration, not business-rule guesses.

### 2.2 Observed normalized values

Every captured source field uses a tagged value:

- KNOWN: value is present and safely normalized.
- UNKNOWN: the source value was successfully observed but could not be safely normalized or classified.
- NOT_APPLICABLE: the field is not applicable to this entity.

UNKNOWN MUST include a registered normalization reason. It MAY include a narrowly scoped, non-sensitive raw hint when needed to explain normalization, such as an unrecognized availability phrase. Raw hints MUST be field-allowlisted, bounded, and MUST NOT contain names, email addresses, phone numbers, VINs, addresses, note bodies, HTML, DOM, screenshots, credentials, session data, or customer hashes.

Missing or unreadable required source data is not UNKNOWN. It is an extraction failure. Bare null is permitted only where a field below explicitly says nullable; it MUST NOT stand for UNKNOWN.

The v0.1.5.3 normalization map is closed and field-specific:

| Observed field normalized as UNKNOWN | Required exact reason |
|---|---|
| line availability | `RC-016 UNKNOWN_LINE_AVAILABILITY` |
| line DS state | `RC-017 UNKNOWN_LINE_DS_STATE` |
| line ETA | `RC-115 UNKNOWN_LINE_ETA_STATE` |

Independent UNKNOWN fields produce the exact set union of their registered field reasons. A code may not substitute across fields. RC-115 blocks only ETA-dependent conclusions or ranking components; it never proves or guesses availability, DS state, a date/lead time, or a terminal condition, and it never authorizes reuse of a stale ETA. Missing, unreadable, inaccessible, or unobserved required ETA data remains an extraction failure.

### 2.3 Calculated values

Calculated fields use:

- EXACT: deterministic value and calculation version are present.
- UNAVAILABLE: the required source facts are insufficient; value is null and a registered blocking reason is present.

UNAVAILABLE is never coerced to zero except for the explicit realized-credit KPI rule in section 12.

## 3. Closed enums

Unregistered enum values MUST fail validation.

### 3.1 Core workflow enums

- SourceTabRole = MONDAY | WEDNESDAY | FRIDAY
- SourceBatchStatus = READY
- StagedOrderStatus = READY
- RunType = RUN_DOI_REVIEW | RECHECK_ORDER | RECHECK_DEDUPE_ORDER
- RunStatus = IN_PROGRESS | COMPLETED | COMPLETED_WITH_EXCEPTIONS | FAILED
- RunWorkOrigin = MANAGER_TARGET_REP_ROW | SOURCE_ABSENCE_VERIFICATION | MANUAL_RECHECK | DEDUPE_RECHECK
- ExtractionStatus = SUCCEEDED | FAILED
- SourceSystem = MANAGER_DOI_SHEET | ORDER_ADMIN | synthetic_CATALOG | MANUFACTURER_SOURCE | HUMAN_ATTESTATION
- VerificationProvenance = SYSTEM_VERIFIED | HUMAN_VERIFIED

### 3.2 Case and evaluation enums

- CaseLifecycleState = ACTIVE | CLOSED_HARD | CLOSED_REVERSIBLE
- TerminalClosureReason = SHIPPED | CANCELED | REP_TRANSFERRED | DEDUPE_CONFIRMED | HUMAN_OUT_OF_SCOPE
- DOIState = DOI_MONITOR | DOI_OPPORTUNITY | DOI_MANUAL_REVIEW | DOI_EXCLUDED
- OrderState = ACTIVE | SHIPPED | CANCELED | UNKNOWN
- RepRelation = TARGET_REP_OWNED | OTHER_REP | UNKNOWN
- GeographyClass = DOMESTIC_STANDARD | DOMESTIC_SPECIAL_REVIEW | INTERNATIONAL | UNKNOWN
- PaymentCondition = NONE_OBSERVED | PRESENT | UNKNOWN
- LineActivity = ACTIVE | CANCELED | UNKNOWN
- DropShipState = DS | NON_DS | UNKNOWN
- LineAvailability = IN_STOCK | DELAYED | UNKNOWN
- QuantityAvailability = FULL | NONE | PARTIAL | UNKNOWN
- LineContinuityState = VERIFIED | UNVERIFIED
- ContinuityProofType = STABLE_SOURCE_LINE_ID | DETERMINISTIC_COMPOSITE | NONE
- SourcePresence = PRESENT | ABSENT
- FindingPresence = PRESENT | ABSENT | UNKNOWN

FULL_DS and PAYMENT_ISSUE_OUT_OF_SCOPE are DOI_EXCLUDED evaluation outcomes but are not, by themselves, verified terminal closures for retention. Leaving a queue or receiving DOI_EXCLUDED does not start the purge clock.

### 3.3 Opportunity and manual-work enums

- OpportunityType = FULFILLMENT_SPLIT | DS_SEPARATION | EXACT_SKU_RECHECK | EXACT_MFG_ALTERNATE | MFG_CROSS_REFERENCE | MFG_SUPERSESSION | FUNCTIONAL_ALTERNATE | PARTIAL_QUANTITY_REVIEW
- AlternateResearchState = NOT_RESEARCHED | RESEARCH_IN_PROGRESS | EXACT_SKU_RECHECK | EXACT_MFG_ALTERNATE_FOUND | MFG_CROSS_REFERENCE_FOUND | MFG_SUPERSESSION_FOUND | FUNCTIONAL_ALTERNATE_FOUND | NO_EXACT_MFG_ALTERNATE_FOUND | NO_VERIFIED_ALTERNATE_FOUND | MANUAL_IDENTIFICATION_REQUIRED | NO_VIABLE_ALTERNATE_HUMAN_CONFIRMED
- ContactState = NOT_CONTACTED | CONTACT_REQUIRED | CONTACT_ATTEMPTED | AWAITING_CUSTOMER | CUSTOMER_APPROVED | CUSTOMER_DECLINED | NO_RESPONSE
- ContactEventType = CONTACT_REQUIRED_DERIVED | CONTACT_ATTEMPT_RECORDED | AWAITING_CUSTOMER_RECORDED | CUSTOMER_APPROVAL_RECORDED | CUSTOMER_DECLINE_RECORDED | NO_RESPONSE_RECORDED
- WWCAuthorRelation = SELF | OTHER_REP | UNCERTAIN
- WWCTimingState = ACTIVE_PROTECTION | PROTECTION_EXPIRED | TIMING_UNCERTAIN | NOT_APPLICABLE
- WWCProjectionState = NOT_APPLICABLE | ACTIVE_SELF | ACTIVE_OTHER_REP | EXPIRED_OTHER_REP | AUTHOR_UNCERTAIN | TIMING_UNCERTAIN | AUTHOR_AND_TIMING_UNCERTAIN
- HumanFactResultCode = COMPATIBILITY_APPROVED | COMPATIBILITY_REJECTED | COMPATIBILITY_NEEDS_MORE_EVIDENCE | NO_VIABLE_ALTERNATE_CONFIRMED | NORMAL_PROGRESS_NO_ACTION_REQUIRED | COORDINATION_RESOLUTION_RECORDED | HUMAN_OUT_OF_SCOPE_CONFIRMED | DEDUPE_APPROVED | DEDUPE_REJECTED
- HumanFactUsageKind = COMPATIBILITY | RESEARCH_STATE | ORDER_PROGRESS | COORDINATION | OUT_OF_SCOPE | ACTION_READINESS
- ActionContextCompletionTrigger = INTERVENTION_ACTION_VERIFIED | HUMAN_COMPATIBILITY_DECISION | HUMAN_NO_VIABLE_ALTERNATE_CONFIRMATION | RESULTING_ORDER_LINK_RESOLVED
- DedupeState = NOT_CANDIDATE | CANDIDATE | HUMAN_APPROVED_AWAITING_OA_VERIFICATION | HUMAN_REJECTED | CONFIRMED
- AttentionCondition = RECHECK_REQUIRED | SOURCE_ABSENT_RECHECK_REQUIRED | INTERVENTION_VERIFICATION_REQUIRED | RESULTING_ORDER_LINK_REVIEW | HUMAN_COORDINATION_REVIEW_REQUIRED

Attention conditions form a set; they are not mutually exclusive and do not overwrite known opportunities.

### 3.4 Intervention and product-knowledge enums

- InterventionType = FULFILLMENT_SPLIT | PRODUCT_SUBSTITUTION | DS_SEPARATION
- InterventionStatus = VERIFIED | PARTIALLY_REVERSED | REVERSED
- ValueVerificationState = NOT_APPLICABLE | UNVERIFIED | VERIFIED
- ResultingOrderLinkState = AUTO_LINKED | HUMAN_CONFIRMED | AMBIGUOUS
- ResultingOrderLinkSearchState = NOT_FOUND | AMBIGUOUS
- AlternateRelationshipType = EXACT_MFG | MFG_CROSS_REFERENCE | MFG_SUPERSESSION | FUNCTIONAL
- AlternateRelationshipState = ACTIVE | SUPERSEDED | INVALIDATED
- AlternateAvailability = IN_STOCK | DELAYED | UNAVAILABLE | UNKNOWN

Verified fulfillment splits, product substitutions, and DS separations are interventions because each is an actual governed DOI order action. DS separation has `NOT_APPLICABLE` value verification and contributes zero credit. Customer contact, exact-SKU research/recheck, DEDUPE decisions, and no-viable-alternate decisions remain immutable coordination/research/manual-decision events rather than interventions.

### 3.5 Historical-evidence enums

- HistoricalLayer = EXECUTABLE_HISTORICAL | HISTORICAL_ASSERTION_HUMAN_REVIEW | SUPPORTING_ONLY_NOT_REPLAYABLE
- HistoricalAssertionCheckability = MACHINE_CHECKABLE | DOCUMENTATION_COVERAGE_ONLY

The original 213-case corpus has no `EXECUTABLE_HISTORICAL` members. These enum values also govern future independently complete historical corpora; they do not authorize promotion of the original records.

## 4. Source ingestion entities

### 4.1 DOISourceBatch

An immutable, privacy-minimized identity for one coherent validated manager-sheet state. Its complete governing schema and canonical hashing algorithms are in `source_retention_contract.md` sections 1–2 and are incorporated here.

Required fields are `source_batch_schema_version="doi-source-batch/v1"`, `source_batch_id`, `source_batch_identity_sha256`, `source_batch_identity_version`, exact `spreadsheet_id`, exact selected-tab role/title/gid, `schema_mapping_version`, `normalized_TARGET_REP_row_content_sha256`, `assignee_conflict_fingerprint_sha256`, `status=READY`, `first_established_at`, privacy-safe TARGET_REP-only aggregate counts, and `record_content_sha256`. The unique identity digest is SHA-256 over RFC 8785 canonical UTF-8 JSON containing exactly the spreadsheet ID, selected-tab identity, schema version, TARGET_REP-row-content hash, and assignee-conflict fingerprint. The distinct full-record digest and exact `doi-source-batch/v1\n` formula in `source_retention_contract.md` section 2.3 are incorporated; a lifecycle binding uses that full-record digest, never the identity digest alone.

The conflict fingerprint is the hash of the sorted unique valid Order Numbers observed both on exact-TARGET_REP rows and on nonblank non-TARGET_REP rows during the same coherent read. Only its digest and cardinality persist. Other-rep names, unrelated Order Numbers, row contents, source locators, and metadata never persist. Unrelated other-rep changes do not change identity; adding/removing a conflict for an already-in-scope TARGET_REP Order Number does. A same-digest/different-canonical-material condition fails before OA with `SOURCE_BATCH_IDENTITY_INTEGRITY_CONFLICT`.

Invocation actor/time, total/out-of-scope counts, physical row locators, rejected identities, and change-detection diagnostics do not belong to the reusable batch. They belong only to the mandatory import attempt/run or an allowlisted run-local rejected record under its own retention clock.

The batch is immutable while retained, not permanent. It MUST have at least one explicit `DOISourceBatchReference`. When the exact last-reference predicate becomes true, TR-113 deletes the complete batch identity/fingerprints and every batch-identifying derivative; no hash/tombstone survives.

### 4.1A DOISourceImportAttempt

Every accepted `Run DOI Review` creates attempt ordinal 1 before acquisition and may create one or more sequential attempts while its run remains `IN_PROGRESS`. Immutable events reduce each attempt independently to a projection containing: opaque nondeterministic `source_import_attempt_id`; `run_id`; stable positive `attempt_ordinal`; attempt-owned command token; exact spreadsheet and explicitly confirmed tab role/title/gid available before failure; attempted schema version; confirmation actor/time; start/completion instants; closed outcome `SUCCEEDED|SCHEMA_REJECTED|SOURCE_CHANGED|INACCESSIBLE_OR_UNREADABLE|BATCH_INTEGRITY_REJECTED|ABORTED_PRE_OA`; deterministic registered reason set; privacy-safe optional aggregate counts; change-detection state; coherent source fingerprint required only for `SUCCEEDED` and exactly null otherwise; optional safely bound batch ID only on success; `oa_read_count=0` through import completion; and nullable `source_import_attempt_purge_eligible_at`, assigned only when the associated run becomes terminal. Enforce `UNIQUE(run_id,attempt_ordinal)` plus attempt-owned command-token uniqueness and byte comparison. A legal retry uses the next ordinal and fresh ID only after a terminal non-success attempt and only while the run remains `IN_PROGRESS`; ordinal gaps, changed replay, concurrent ordinals, and post-run-terminal append fail before persistence. `ABORTED_PRE_OA` has event type `SOURCE_IMPORT_ABORTED`, an exact empty reason set, leaves the run `IN_PROGRESS`, and requires a later attempt to terminalize the run. Every registered failure outcome uses `SOURCE_IMPORT_FAILED` plus RC-090 and its exact specific source reason. RC-091 failure retains no candidate batch digest, identity preimage, TARGET_REP/conflict fingerprint, or undocumented batch reference.

The attempt never contains customer PII, raw cells, full-sheet/range dumps, exact unrelated other-rep identities or orders, row contents, HTML/DOM/screenshots, credentials, cookies, or session data. A final failed attempt persists `SOURCE_IMPORT_FAILED` plus its exact specific source reason. Unreadable, unrecognized-schema, proven changed-source, and batch-identity-integrity final outcomes leave the run `FAILED`, no executable batch/work/case/evaluation, and zero OA reads. Earlier non-success attempts remain governed by the same common run-terminal retention boundary and cannot survive it merely because a later attempt succeeded.

### 4.1B DOIRejectedSourceRecord

When operationally necessary, an allowlisted rejected TARGET_REP record that never creates a case is attempt-local, never a durable child of a reusable batch. It contains its own ID, run/import-attempt IDs, optional safely established batch ID, canonical nonempty rejection-kind/reason sets, exact valid TARGET_REP Order Number, TARGET_REP-only source references, and creation/run-terminal/retention fields. Its natural-key bytes are exactly JCS `{rejection_identity_schema_version:"doi-rejected-source-identity-v2",source_import_attempt_id,order_number}`. Enforce `UNIQUE(source_import_attempt_id,order_number)` plus unique natural-key digest with canonical-byte comparison; the retained `run_id` is only the validated parent FK and is not the uniqueness scope because a later legal ordinal is distinct. Exact replay reuses one record, conflicting completed payload is RC-111, and digest collision is RC-103. Under `synthetic-doi-queue-v0.1`, only the TARGET_REP plus nonblank non-TARGET_REP scalar assignee conflict/RC-008 is reachable; blank scalar B is not a conflict, and RC-007 row conflict is reserved for a future schema with explicit governed row metadata. Invalid A or non-scalar B fails before this entity/batch; invalid raw values and other-assignee details never persist.

At run terminal, schedule `purge_eligible_at = calendar90(run.completed_at)`. At that instant TR-105 deletes exact Order Number, source references, record ID, evidence fingerprint, every reconstructable join key, and its transaction-local RC-093 deletion event/stream in the same commit. No rejection aggregate, reason/schema/date dimension, receipt, code, hash, or tombstone survives; source import retains only the exact TR-114 `DOISourceImportAggregateV2` month/outcome/count row. Batch reuse never extends or revives this clock.

### 4.1C DOISourceBatchReference and DOICaseSourceBinding

The complete schemas, owner table, canonical domain/hash, unique/FK rules, retention behavior, last-reference predicate, closed non-identifying aggregate, and rollback semantics in `source_retention_contract.md` section 2.4 are incorporated here without relaxation.

Every retained batch has one reference per exact owner tuple. The closed owners are RUN, SOURCE_IMPORT_ATTEMPT, STAGED_SOURCE_RECORD, NO_CASE_REJECTED_RECORD, and CASE_SOURCE_BINDING. Each reference deletes atomically with its owner; an event containing batch identity is a child of that owner and cannot create an independent lifetime. A retained case binds a batch only through an explicit `DOICaseSourceBinding`, which deletes with case purge.

TR-113 locks the batch/reference set after all due owner releases. Any remaining reference retains the byte-identical batch. Zero remaining references atomically delete the batch ID, canonical identity bytes/hash, TARGET_REP hash, conflict fingerprint/cardinality, TARGET_REP-derived counts, and every identifying event/cache/log/export. Only `DOISourceImportAggregateV2` with exact schema `{aggregate_schema_version,local_calendar_month,attempt_outcome_class,attempt_count}` survives; it has no batch/run/attempt/reference/case/order ID, hash, reason, timestamp, or drill-through. Failure rolls the complete transaction back.

### 4.1D DOICaseSourceAdmissionProofV1

Before `CASE_CREATED` or `SOURCE_PRESENT`, TR-007/TR-008 atomically creates the case-owned source binding/reference and this closed proof:

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

`case_source_admission_proof_id = SHA256(UTF8("doi-case-source-admission-proof-identity/v1\n") || UTF8(RFC8785({"case_source_admission_proof_identity_schema_version":"doi-case-source-admission-proof-identity/v1","case_id":case_id,"source_batch_id":source_batch_id})))`. Hash the complete proof except `content_sha256` under `doi-case-source-admission-proof/v1\n`; enforce unique ID and `(case_id,source_batch_id)`. Resolve/byte-compare the retained batch and `DOICaseSourceBinding`, and transiently compare canonical Order Number/TARGET_REP selection to the staged source before the atomic proof append. Exact replay returns the same proof/time; mismatch or missing authority fails before lifecycle append. The proof contains no run ID, attempt ID/ordinal/token, source-row reference, spreadsheet/tab identity, actor, or attempt timestamp and therefore cannot reconstruct an attempt or row. It and its case batch/reference owner delete only with the case graph.

### 4.2 DOIStagedOrder

One privacy-minimized, deduplicated TARGET_REP order input in a READY source batch.

Required fields:

- staged_order_schema_version: literal `doi-staged-order/v1`.
- staged_order_id: OpaqueId.
- run_id: OpaqueId.
- source_import_attempt_id: OpaqueId.
- source_batch_id: OpaqueId.
- order_number: OrderNumber.
- assigned_rep_normalized: literal TARGET_REP.
- status: StagedOrderStatus.
- TARGET_REP_source_refs: non-empty ordered set of SourceRef.
- compatible_source_metadata: literal empty object for `synthetic-doi-queue-v0.1`; E:O is never read into the row model. A future schema requires a new mapping version before adding typed fields.
- reason_codes: registered reason-code set.
- created_at: Timestamp assigned once by the TR-099 persistence boundary.
- record_content_sha256: Sha256.

Unique key: `(source_import_attempt_id,order_number)`. The `source_import_attempt_id` must identify the exact successful attempt/ordinal owned by `run_id`, and its safely bound `source_batch_id` must equal the staged record's batch. A later legal attempt ordinal is a distinct ownership scope, so run/order uniqueness across retries is forbidden. `TARGET_REP_source_refs` and any physical locators are attempt-local observations; they are never fields of, or reused from, the immutable batch. Reusing a batch creates new attempt-local staged records/source refs from the current coherent scan and cannot reuse stale locators or eligibility. Staged storage is attempt-owned operational detail and is always deleted with its attempt at TR-114; case creation/source-present first copies only the closed case-owned `DOICaseSourceAdmissionProofV1`, never a run/attempt/row/tab/actor field or staged-record reference.

The full staged-order record is closed. `TARGET_REP_source_refs` and `reason_codes` are duplicate-free canonical sets sorted by complete-member RFC-8785 bytes and reason-code strings respectively. `record_content_sha256 = SHA256(UTF8("doi-staged-order/v1\n") || UTF8(RFC8785(staged_order_without_record_content_sha256)))`. Resolve `(source_import_attempt_id,order_number)` before allocating `staged_order_id` or `created_at`; exact replay returns the original complete record/timestamp, changed bytes reject with RC-111, and a proven digest collision adds RC-103. `created_at` is only the immutable staging instant and never enters a case lifecycle payload. `CASE_CREATED`/`SOURCE_PRESENT` instead bind the independently persisted case-owned admission proof and its `admitted_at`; import start, staged creation, or retry time cannot substitute.

TR-099 is the sole `DOIStagedOrder` append owner. In the same commit as source-import success, every duplicate valid TARGET_REP A/B row for one canonical number merges into one READY staged order, retains every deduplicated current-attempt TARGET_REP SourceRef, and carries RC-006; different E:O values are ignored and cannot cause RC-007. Simultaneous TARGET_REP plus nonblank non-TARGET_REP scalar assignment creates no staged order; a blank scalar B is not a conflict. TR-103 owns the sole natural-keyed rejection record with RC-008, zero work/case/OA reads, and the independent no-case retention clock. Thus no rejected/no-case Order Number or source ref can survive staged storage after TR-105 deletes its rejection graph.

Every populated A/B record is value/type validated before personal filtering or staging. A missing/invalid OrderNumber or non-scalar Assigned Rep makes the locked schema unrecognized, terminalizes the current import attempt with RC-002/090, creates no source batch or DOIStagedOrder, and performs zero OA reads. The run remains `IN_PROGRESS` only when an exact legal pre-OA next-ordinal retry is accepted; without one, that final failure terminalizes the run `FAILED`. It is never treated as a row-only rejection under `synthetic-doi-queue-v0.1`.

### 4.3 DOIRun

One accepted explicit user-triggered review. Creation is immediate at invocation; immutable start/terminal events reduce to the current run projection—`IN_PROGRESS` after accepted invocation and exactly one terminal status after a legal run-terminal event. Every `RUN_DOI_REVIEW` has one or more sequential `DOISourceImportAttempt` children as defined by `source_retention_contract.md` section 3; the run projection and event stream retain only their count, never an attempt ID/manifest.

Required fields:

- run_id: OpaqueId.
- run_type: RunType.
- initiated_by_actor_id: non-customer internal actor identifier.
- started_at: Timestamp.
- completed_at: Timestamp, nullable if and only if status = IN_PROGRESS.
- status: RunStatus.
- run_purge_eligible_at: Timestamp, nullable if and only if status = IN_PROGRESS; otherwise byte-equal to `calendar90(completed_at)` under `source_retention_contract.md` section 6.
- source_import_attempt_count: positive integer for `RUN_DOI_REVIEW`; exact count of accepted attempt ordinals and the only attempt summary retained by the run while it exists.
- source_batch_id: OpaqueId, nullable while IN_PROGRESS, for manual single-case rechecks, and for run-level source failures.
- rules_engine_version: VersionId.
- extractor_version: VersionId.
- schema_mapping_version: VersionId, nullable for manual rechecks.
- business_calendar_version: VersionId, nullable only if no WWC calculation occurred.
- work_item_count: integer >= 0.
- normal_evaluation_succeeded_count: integer >= 0.
- order_exception_count: integer >= 0.
- blocked_order_count: integer >= 0.
- oa_read_count: integer >= 0.
- reason_codes: registered reason-code set.

Run status:

- IN_PROGRESS: TR-001 `RUN_INVOCATION_ACCEPTED` created a valid active run. `started_at` is non-null; `completed_at`, `run_purge_eligible_at`, and the initial `source_batch_id` are null; governed active-processing metadata may advance; the run is not completed.
- COMPLETED: a coherent batch completed with zero order exceptions and zero blocked orders; a coherent empty TARGET_REP batch is legal.
- COMPLETED_WITH_EXCEPTIONS: coherent source execution completed with one or more individual order blocks/exceptions. This includes all orders blocked or all permitted extractions failed with zero normal evaluations.
- FAILED: only a registered run-level source/integrity condition prevented successful source execution. Named v0.1.5 failures are pre-OA, leave the mandatory run/import-attempt history, permit a null batch, create no executable work/case/evaluation, and require `oa_read_count=0`.

Only `COMPLETED`, `COMPLETED_WITH_EXCEPTIONS`, and `FAILED` are terminal. TR-002, TR-003, and TR-004 consume `IN_PROGRESS` and atomically set non-null `completed_at` plus the exact non-null run deadline; no terminal status returns to `IN_PROGRESS`. Unknown status values and unlisted edges fail before persistence under the closed-enum and transition rules.

Every accepted explicit review creates a distinct DOIRun and at least one source-import attempt even when it reuses the same DOISourceBatch. A legal pre-OA retry appends the next same-run attempt ordinal; it never creates a second run. A bad order never converts a coherent completed batch into `FAILED`. Within each retained source-import attempt, each exact OrderNumber appears at most once; the same number in a different legal attempt ordinal is separately owned and must not collide on a run/order key.

### 4.3A Immutable run/import/retention event machines

The exact field-level schemas and canonical domains in `source_retention_contract.md` sections 3.4 and 4 are incorporated as machine schemas. They are not optional audit prose.

`DOIRunEvent` uses the complete common envelope. `run_event_id` aliases `event_id`; v0.1.5 emits only `doi-run-event/v2`; `stream_id` is the exact hashed RUN identity derived from `run_id`; and `stream_sequence`/`previous_event_id`/`previous_event_content_sha256` are the sole ordering fields. `RUN_INVOCATION_ACCEPTED` requires HUMAN/HUMAN_VERIFIED; `RUN_TERMINAL` requires SYSTEM/SYSTEM_VERIFIED. Invocation payload binds actor/time, run/schema/rules/extractor/calendar versions, `IN_PROGRESS`, null batch, `source_import_attempt_count=1`, and zero work/result/OA counters. Terminal payload binds prior/result status, completion time, exact `source_import_attempt_count` but no attempt ID/manifest, nullable batch, exact versions, all final work/result/OA counts, and terminal reasons. The `FAILED` variant requires RC-090 plus one registered source failure, null executable batch/work/case/evaluation, and zero OA reads; an intermediate `ABORTED_PRE_OA` attempt cannot terminalize the run.

`DOISourceImportAttemptEvent` also uses the complete envelope. Its domain ID/schema names alias `event_id`/`schema_version`; `stream_id` is derived from `source_import_attempt_id` under SOURCE_IMPORT_ATTEMPT; and the closed STARTED, SUCCEEDED, FAILED, and ABORTED types require SYSTEM/SYSTEM_VERIFIED. Every payload binds `run_id`, `source_import_attempt_id`, stable `attempt_ordinal`, and attempt-owned command-token identity. Start binds the exact selected spreadsheet/tab/schema confirmation and `STARTED`. Success binds the same source identity, privacy-safe counts, change-detection state, required coherent fingerprint, safe batch ID, empty failure reasons, and zero OA reads through import. Failure binds only source identity known before failure, one exact closed failure outcome, privacy-safe counts, change state, null coherent fingerprint/batch, RC-090 plus one exact specific source reason, and zero OA reads; this includes RC-091 and cannot retain an unowned candidate digest. `SOURCE_IMPORT_ABORTED` binds `ABORTED_PRE_OA`, null fingerprint/batch, exact empty reason set, zero OA reads, and requires the parent run to remain `IN_PROGRESS` for a later ordinal. On run terminal, every attempt receives the same immutable `source_import_attempt_purge_eligible_at=calendar90(run.completed_at)`; a nonterminal run assigns none.

`DOIRejectedSourceRetentionEvent` uses the complete envelope: its domain ID/schema alias the common fields; `stream_id` is derived under REJECTED_SOURCE_RETENTION from the owning rejected-record ID; `stream_sequence=1` with null predecessors; type is `RETENTION_SCHEDULED`; actor/provenance are SYSTEM/SYSTEM_VERIFIED; and its closed payload binds the exact run-terminal event ID/hash, policy/tzdb versions, terminal anchor, and exact purge instant with RC-092. It is unique by event ID, `(stream_id,stream_sequence)`, and rejected-record ID, cannot reset/extend, and deletes atomically with the rejected identity. No deletion receipt survives.

Run/import stream sequence 1 has null predecessors; sequence 2 must name sequence 1 exactly. Every attempt stream has one start and one terminal; the run has one invocation and at most one terminal. Same-ID/same-byte replay is a no-op; wrong owner-derived stream ID/alias/provenance, stale sequence/predecessor, second terminal, or same ID/different canonical bytes is RC-111 (plus RC-103 only for a proven digest collision), with no projection change. Invocation appends the run start and attempt-ordinal-1 start atomically. An intermediate failure/abort terminalizes only its attempt; a legal retry appends a new attempt stream at the next ordinal. Final failed import appends attempt and run terminal events atomically before OA. Successful import terminalizes only its attempt before any eligible OA read; the completed run terminal event appends only after all completed-state run work finishes and binds the final work/result/OA counts. Projections are reducer outputs only and never authoritative in-place overwrites.

For run/import events, envelope `reason_codes` is authoritative and must byte-equal any repeated payload reason set: starts, import success, and intermediate abort are empty; import failure and run `FAILED` are exactly RC-090 plus one specific source failure; a completed run carries exactly its terminal registered order/run codes. An aborted attempt cannot create `RUN_TERMINAL`. Divergence is RC-111 and no append.

### 4.3B Source-import attempt retention event, run references, and aggregate

`source_retention_contract.md` section 13 is incorporated exactly. Every lawful graph retaining `run_id` owns one closed `doi-run-identity-reference/v1` row for owner type `SOURCE_IMPORT_ATTEMPT|STAGED_SOURCE_RECORD|NO_CASE_REJECTED_RECORD|RUN_WORK_GRAPH`; run v2 stores no attempt locator. `RUN_WORK_GRAPH` is legal only while a retained extraction/snapshot/evaluation resolves its exact run work item and follows that case/work deadline. A bare case admission proof/binding contains no run ID and owns no run reference. At or after the common deadline, TR-114 is the sole attempt-deletion owner.

`DOISourceImportAttemptRetentionEventV1` is a transaction-local non-case event, never a `DOIOrderLifecycleEventV2`. It uses schema `doi-source-import-attempt-retention-event/v1`, owner-derived stream sequence 1/null predecessors, SYSTEM/SYSTEM_VERIFIED, event type `SOURCE_IMPORT_ATTEMPT_PURGE_FINALIZED`, exact `[RC-114]`, and closed payload `doi-source-import-attempt-purge-payload/v1`. The payload contains exactly: schema/transition IDs; terminal attempt event ID/hash and outcome; run terminal event ID/hash/completion time; retention policy, literal New York timezone, tzdb and calendar-rule versions; exact attempt deadline; aggregate v2 month/outcome/count delta 1; successful-only batch-reference PRESENT/RELEASE or non-success ABSENT/NOT_APPLICABLE; run-reference RELEASE plus RETAIN_RUN/DELETE_RUN; six required deletion booleans true; tombstone false; result attempt ABSENT; and result run RETAINED/ABSENT. Missing/extra/null/wrong branch/hash rejects before aggregate/persistence/deletion.

Hash exact payload/event canonical bytes under `doi-source-import-attempt-purge-payload/v1\n` and `doi-source-import-attempt-retention-event/v1\n`. Fixed vector authorities are stream `b14b67e59e765b28d927b12a6d59b161944dd27c06dbe13ce3439000f3233513`, event ID `86b3208fb50e2352a65a49b4a74016d00956fd9109f72030071848cb500aac90`, payload `2ad1678cdad8d10be9b4bbb2b46d9b7158c7635638356982b8ce120d7f4c7e32`, and full event `738fa8d9ac327be19c099404891e9d18f47a224d8e26c1006e6faa544241c4fe`. The event exists only in the transaction write set and is deleted before commit, so RC-114 does not survive.

The only surviving source-import record is `DOISourceImportAggregateV2` with exactly `{aggregate_schema_version:"doi-source-import-aggregate/v2",local_calendar_month,attempt_outcome_class,attempt_count}`. The key is its first three members; TR-114 increments count by one. Aggregate ID/hash/revision, reason, duration, exact time, free text, source/run/attempt/batch/case/order identity, and drill-through are forbidden.

### 4.4 DOIRunOrderWorkItem

Required fields:

- run_work_item_id: OpaqueId.
- run_id: OpaqueId.
- order_number: OrderNumber.
- case_id: OpaqueId, nullable only for another explicitly registered non-case origin. The manager-v0.1 RC-008 assignee conflict creates no work item; its sole identity-bearing record is the retained rejection record. RC-007 is unreachable for this mapping.
- origin: RunWorkOrigin.
- case_source_admission_proof_id: OpaqueId, required for `MANAGER_TARGET_REP_ROW`; nullable only for separately governed absence/manual rechecks. No work item may retain `staged_order_id` or any attempt-owned locator.
- source_batch_id: OpaqueId, non-null for `MANAGER_TARGET_REP_ROW` and `SOURCE_ABSENCE_VERIFICATION`, otherwise explicit null unless an authorized re-evaluation reuses the retained snapshot's producing work item.
- execution_allowed: boolean.
- extraction_attempt_id: OpaqueId, nullable if execution_allowed is false.
- reason_codes: registered reason-code set.

The `DOIRunOrderWorkItem` key is the exact two-field tuple of `run_id` and `order_number`. This is a post-success work key, not a source-import-attempt, staged-record, or rejection identity: work starts only after the run's sole successful import attempt, after which no later source attempt is legal. For manager-origin work, `source_batch_id`, `order_number`, and case ID MUST byte-equal the closed case-source admission proof/binding created after transient staged validation; no staged-record FK survives. For source-absence verification, `source_batch_id` MUST equal the coherent selected manager batch. This field and `origin` are immutable from work-item creation through owner deletion; a database constraint forbids later rebinding. The admission proof/source batch is the retained derivation root used by lifecycle source-handling wrappers; extraction attempts, snapshots, and evaluations derive it through their exact retained work-item/attempt/snapshot chain rather than inventing duplicate fields. Every extraction attempt FK names exactly one retained work item, every snapshot FK names exactly one retained extraction attempt, and every evaluation input names exactly one retained snapshot; the complete chain must exist and agree until its case/source owner graph is deleted. After TR-114, a retained chain may contain governed run ID, source-batch ID, and admission-proof ID only; `source_import_attempt_id`, `staged_order_id`, TARGET_REP `SourceRef`, attempt ordinal/token, and every other attempt/source-row locator are forbidden throughout the chain. A READY staged order may transiently authorize atomic admission-proof/work creation but deletes under TR-114 and is never a retained work target. Under `synthetic-doi-queue-v0.1`, duplicate TARGET_REP rows always merge through RC-006 and cannot emit `SOURCE_ROW_CONFLICT`; RC-007 is compatibility-reserved for a future versioned metadata schema. `SOURCE_ASSIGNEE_CONFLICT`/RC-008 creates neither a staged order nor work item, increments run exception/block counts from the attempt-local rejection graph, and forces `COMPLETED_WITH_EXCEPTIONS` without OA.

## 5. Extraction, case, snapshot, and evaluation entities

### 5.1 DOIExtractionAttempt

Minimal metadata for one read-only attempt. It MUST NOT retain HTML, DOM, screenshots, page copies, full note bodies, credentials, session data, or customer data.

Required fields:

- extraction_attempt_schema_version: literal `doi-extraction-attempt/v1`.
- extraction_attempt_id: OpaqueId.
- run_work_item_id: OpaqueId.
- order_number: OrderNumber.
- source_system: ORDER_ADMIN.
- started_at: Timestamp.
- completed_at: Timestamp.
- status: ExtractionStatus.
- exact_identity_observed: boolean.
- whole_order_capture_proven: boolean.
- captured_relevant_line_count: integer >= 0, nullable on early failure.
- snapshot_id: OpaqueId, nullable.
- reason_codes: registered non-empty set on failure.
- record_content_sha256: Sha256, fixed only at terminalization.

Invariant:

- SUCCEEDED iff exact_identity_observed=true, whole_order_capture_proven=true, snapshot_id is non-null, and exactly one new snapshot was appended.
- FAILED iff snapshot_id is null. A failed attempt creates no snapshot and no evaluation and sets RECHECK_REQUIRED on the case/work item.

At terminalization the attempt becomes immutable. Its closed full-record object is every required field above except `record_content_sha256`; nullable values are explicit, and `reason_codes` is a duplicate-free ascending set. `record_content_sha256 = SHA256(UTF8("doi-extraction-attempt/v1\n") || UTF8(RFC8785(extraction_attempt_without_record_content_sha256)))`. Lifecycle source/absence/snapshot bindings use this digest and `completed_at` as the exact accepted terminal-fact instant. A retry resolves the retained attempt before any new timestamp or ID allocation; no terminal byte is rewritten.

### 5.2 DOIOrderCase

Mutable current projection backed by immutable lifecycle events.

Required fields:

- case_id: OpaqueId.
- order_number: OrderNumber.
- lifecycle_state: CaseLifecycleState.
- created_at: Timestamp.
- first_source_batch_id: OpaqueId, nullable for a manual-first case if that flow is later authorized.
- current_snapshot_id: OpaqueId, nullable only before the case's first successful complete extraction.
- current_evaluation_id: OpaqueId, nullable only when current_snapshot_id is null or the exact requested rules version is unavailable and evaluation therefore failed closed.
- current_attention_conditions: set of AttentionCondition.
- terminal_closure_reason: TerminalClosureReason, nullable unless closed.
- terminal_closed_at: Timestamp, nullable unless closed.
- purge_eligible_at: Timestamp, nullable unless closed; exact UTC output of the bound `calendar90` policy.
- lifecycle_version: monotonically increasing integer.

Unique key while retained: order_number. Create the case when a valid exact TARGET_REP staged order first enters the workflow, before its extraction attempt, so a first-attempt failure can carry `RECHECK_REQUIRED` without inventing a snapshot/evaluation. A reopened retained case reuses the same case_id and never creates a second episode/case. After purge, no unique-key record or historical lookup survives; a later same-number input creates a new unlinked case under the ordinary creation rule.

The current projection may change only by reducing immutable events. It contains no free-text notes or customer identity.

For the v2 core case lifecycle ledger, `lifecycle_version` is exactly the last accepted core `result_case_revision` and `stream_sequence`; it is never independently incremented. The two target-owned volatile observation/link wrapper streams do not change it. The complete rebuildable projection and its hash use `DOIOrderCaseProjectionV2` from `DOI_LIFECYCLE_EVENT_PAYLOAD_REGISTRY_v0.1.5.md` section 3.

### 5.3 DOIOrderLifecycleEvent

Immutable v2 lifecycle event under one of two closed retention classes. Core projection-ledger events remain append-only until case purge. `ALTERNATE_OBSERVATION_STORED` and `ACTION_CONTEXT_OBSERVATION_LINKED` are single-event target-owned volatile streams and delete atomically with their target at its earlier governed deadline; they never enter/change the core ledger. `DOI_LIFECYCLE_EVENT_PAYLOAD_REGISTRY_v0.1.5.md` is the sole authority for this entity. The former v1 `schema_version`/`event_type`/single-source/open-payload shape is deleted and MUST NOT be parsed as v2.

The exact serialized common envelope is `DOIOrderLifecycleEventV2` with literal `event_schema_version="doi-order-lifecycle-event/v2"` and fields: `lifecycle_event_id`, `case_id`, the event-kind-derived core or volatile `stream_id`, sequence, exact predecessor ID/hash, closed `event_kind`, `logical_occurrence_id`, event-natural-key hash, occurred/recorded instants, actor/provenance pair, prior/result case revisions, prior/result projection hashes, canonical nonempty exact source bindings, canonical registered reason set, one selected closed payload, canonical payload digest, and full `content_sha256`. No alias or extension field is serialized.

`LifecycleEventKindV2` has exactly the 56 literals in registry section 5. Each literal selects exactly one of eight persisted closed payload object types and its required/non-null/null/absent partition. Unknown kinds, versions, payload types, enum values, missing or extra keys, illegal nulls, actor/provenance mismatch, typed ID/schema/hash mismatch, wrong JCS/domain, or incorrect natural/payload/projection/full hash is `RC-113 LIFECYCLE_EVENT_SCHEMA_INVALID`; append and projection change are zero. Unlisted state edges remain RC-081, stream sequence/predecessor faults remain RC-111, and proven digest collisions additionally use RC-103.

Typed contact, DEDUPE, attention, Action Context, relationship, resulting-link, WWC, intervention-action, and value/reversal facts remain authoritative in their dedicated immutable streams. A case-linked accepted typed fact atomically appends only the thin lifecycle reference carrying its exact event ID/schema/full hash and before/after domain state; it never copies the typed fact body. Product-only relationship events without a case remain product-only. Run/import/no-case retention events remain non-case. TR-018/019/043/105/112/113 deletion success and transient post-purge rejection create no surviving identifying lifecycle receipt.

Attention lifecycle wrappers reference `DOIAttentionEventV2` with literal `doi-attention-event/v2`. Their cause and resolution fields equal that typed event byte-for-byte. The one authoritative cause schema/domain is `doi-attention-cause-key/v2` / `doi-attention-cause-key/v2\n`; no lifecycle-specific alternate formula is legal.

Core sequence 1 is `CASE_CREATED`, has null predecessors/prior revision/prior projection, and produces revision/sequence 1. Each later core append has `result_case_revision=prior_case_revision+1=stream_sequence`, names the exact prior core event/hash, and consumes that event's result projection hash. Each of the two volatile record-owned streams contains exactly one sequence-1 event with null predecessors and identical locked non-null prior/result core revision and projection hash; it changes no case byte and deletes with its target. Enforce `UNIQUE(lifecycle_event_id)`, `UNIQUE(stream_id,stream_sequence)`, and `UNIQUE(case_id,event_natural_key_sha256)` with retained canonical natural-key bytes. Exact replay returns the existing event without allocating ID/time/bytes. Replaying core events by sequence reproduces every intermediate `DOIOrderCaseProjectionV2` hash; independently replaying a retained volatile stream reproduces the unchanged locked hash.

The exact stream, natural-key, payload, projection, full-event, immutable opportunity-record, opportunity-lifecycle-natural, and Action-Context-observation-link-natural JCS objects/domains are incorporated from registry sections 2–4 without variation. `DOIOpportunity` therefore additionally stores literal target field `opportunity_schema_version="doi-opportunity-record/v1"`, immutable `created_at`, and its exact full-record `record_content_sha256`; the generic lifecycle payload field `record_schema_version` copies `opportunity_schema_version` byte-for-byte. Exact `(evaluation_id,scenario_option_id)` content reuses the record, creation time, and lifecycle event.

#### 5.3.1 Explicit prior closure and retention binding

`PriorClosureRetentionBindingV1` is the closed nested lifecycle value with literal version `doi-prior-closure-retention-binding/v1` and exactly these required non-null fields: `prior_closure_event_id`, `prior_closure_event_content_sha256`, `prior_closure_kind`, `prior_closure_classification`, `prior_verified_closure_at`, `prior_retention_policy_id`, `prior_retention_policy_version`, `prior_retention_timezone`, `prior_tzdb_version`, `prior_local_calendar_rule_id`, `prior_purge_eligible_at`, `prior_closure_projection_revision`, `prior_closure_projection_hash`, `prior_closure_source_entity_type`, `prior_closure_source_entity_id`, `prior_closure_source_entity_schema_version`, and `prior_closure_source_entity_content_sha256`. No optional/extension field exists. Kind uses the closed closure-kind registry; classification is exactly `HARD|REVERSIBLE` with hard limited to `SHIPPED|CANCELED` and reversible limited to `REP_TRANSFERRED|DEDUPE_CONFIRMED|HUMAN_OUT_OF_SCOPE`. Timezone is exactly `America/New_York`; policy ID/version and local-calendar rule are exactly `DOI_CASE_GRAPH`, `doi-retention-calendar90-ny/v1`, and `calendar90-america-new-york/v1`; tzdb is the retained closure's exact bound version. Timestamps and hashes use the existing canonical `Timestamp`/lowercase-SHA-256 representations.

`CaseReopenPayloadV2.prior_closure_retention_binding` is required and non-null. The rest of its closed required schema is: duplicated prior closure kind/time/deadline; exact reopen source type/ID/schema/full hash; `reopen_reason_code="RC-078"`; proof-derived `reopen_at`; ACTIVE/NONE/null result closure fields; literal `purge_deadline_cancellation_effect="CLEAR_ACTIVE_PURGE_DEADLINE"`; same `result_case_id`; literal `same_case_identity_preserved=true`; and exact result revision/projection hash. The only nulls are resulting verified-closure time and purge deadline. The binding's projection revision/hash equal the locked pre-reopen envelope prior revision/hash, and its deadline equals the active pre-event deadline. The payload proves the exact prior closure event and closure proof; a projection hash without the explicit tuple is invalid.

`PurgeDeadlinePayloadV2` carries the complete required conditional fields in lifecycle registry section 4.7. For `PURGE_CANCELED`, its nested binding, canceled deadline, cancellation-cause event ID/hash, complete reopen-resolution source type/ID/schema/hash, result deadline state, same-case ID flag, and result revision/hash are non-null as specified; closure kind/class/verified time/new deadline and result deadline are explicit null. The canceled deadline equals the nested prior deadline. The source/cancellation event aliases both name and hash the exact `CASE_REOPENED` event; the resolution group equals that event's reopen proof; the complete nested binding is byte-for-byte identical to the reopen event's nested binding. `PURGE_SCHEDULED` and `PURGE_RESTARTED` require that binding/cancellation/resolution group null and follow their closed scheduled-deadline partitions.

Validation locks and independently resolves the last applicable prior closure event, its exact source proof, the authoritative closure-bearing projection revision/hash, active deadline, and constructed retention-policy record. It constructs and RFC-8785-serializes the authoritative binding, then requires byte equality with the proposed nested object before event IDs, times, or rows are allocated. Cancellation repeats this validation against both the retained authorities and the exact accepted reopen payload; it never infers a field from only a digest. Any missing target, unknown version, missing/extra/null field, kind/classification/instant/policy/timezone/tzdb/calendar/deadline/projection/source mismatch, or reopen-to-cancel byte difference is RC-113. The atomic reopen/cancel bundle appends nothing and preserves the prior closed projection byte-identically. Exact replay validates the same authorities and reproduces the exact event/projection bytes without allocating anything.

Lifecycle fixed vectors are also closed by executable identity. V1 uses exact case `SYN-DOI-CASE-0001`; V2 uses exact case `SYN-DOI-CASE-0002`; the V3 top-level serialization fixture uses `SYN-DOI-CASE-0003`. V3 deliberately treats its repeated-hex predecessor/source digests as opaque already-validated inputs and is not the target-reachability proof; `SYN-LIFE-PAYLOAD-010` separately constructs actual closed-schema targets/a reachable stream and computes its own hashes. The V1 harness identity `SYN-DOI-ORDER-0001` maps outside serialized admission-proof bytes to schema-valid, historical-denyset-checked sentinel OrderNumber `"1"`. The obsolete executable inputs `case-0001`, `case-0002`, production-looking `10000001`, or any unregistered non-`SYN-DOI-` case identity are rejected before execution. V1 now binds `CASE_SOURCE_ADMISSION_PROOF`/`doi-case-source-admission-proof/v1`: case-source binding `e39a40adfeb2b606981364928e38bb867a20f6349e0b2a734e82d0c17bceb2f3`, admission-proof ID/logical occurrence `e2aa8e7b7fe795821d230ede3d731c79f8670718e277d8d0812f1a83df97636e`, proof hash `2e9ac63cf8d5cda713e46351f4c8e8ce83429c2e39f35142113fd54da15f53b8`, natural hash `a8feba67a425e50f0a584a14336f4a3290a5f3de104cc0f86fb6ab2d34e3cb90`, and full event `0baab70132263d66f67582425bbf6d6c227ebb5c10317ea124babf5aee70c257`. V2 projection/full hashes remain `d99c4ce97e398adb7521f580e00893110b69bc56daeb6a28ef58d3da14e95198` / `1bf19ddbbd4b108617d52d349ceec5ba950947f5a587d7784b4082d88a0f4b36`; V3 reopen/cancel serialization-only full hashes are `94e4bd6ed31f4cadc6e24c27fe22c01d1bcadaafbf72652b475b5e70d473dff0` / `f434eba59677521936b21f3f45a8f9ceff3e3a195e001c2eb0944fb6229976e3`. The complete bytes and all intermediate values are registry sections 7 and 10.

### 5.4 DOIOrderSnapshot

An immutable complete whole-order fact record. It contains normalized source facts only—never classification, reason codes, opportunity flags, recommendations, or calculated DOI values.

Required fields:

- snapshot_id: OpaqueId.
- case_id: OpaqueId.
- extraction_attempt_id: OpaqueId.
- captured_at: Timestamp.
- source_system: ORDER_ADMIN.
- extractor_version: VersionId.
- order_number: OrderNumber.
- order_state: observed normalized OrderState.
- current_rep_value: observed normalized non-customer rep string.
- current_rep_relation: observed normalized RepRelation.
- geography_class: observed normalized GeographyClass; no address components may be retained.
- payment_condition: observed normalized PaymentCondition.
- order_total: observed normalized Money.
- declared_relevant_line_count: integer >= 0.
- captured_relevant_line_count: integer >= 0.
- whole_order_proof_type: versioned extractor enum.
- whole_order_proof_ref: privacy-safe SourceRef.
- line_snapshot_ids: ordered non-empty set, except a proven zero-relevant-line order.
- wwc_finding: object `{presence: FindingPresence, author_relation: observed WWCAuthorRelation, contact_at: observed Timestamp, source_ref: SourceRef|null}`. When absent, author/time are NOT_APPLICABLE and source_ref may be null. UNKNOWN author/time means observed-but-unnormalizable; no note body is retained.
- dedupe_finding: object `{presence: FindingPresence, observed_at: Timestamp, source_ref: SourceRef|null}`. PRESENT means the configured DEDUPE marker was observed; it never stores surrounding note text.
- source_observed_at: Timestamp.
- snapshot_schema_version: literal `doi-order-snapshot/v1`.
- snapshot_content_sha256: Sha256 under the exact formula below.

The hash input is the closed object containing exactly every required snapshot field listed above except `snapshot_content_sha256`, with `line_snapshot_ids` replaced by `line_manifest`, a canonical ordered array of exact `{line_snapshot_id,line_snapshot_content_sha256}` objects sorted by `line_snapshot_id`. Nullable values in WWC/DEDUPE findings are explicit `null`; the zero-line case has an empty manifest. No other alias or extension key is admitted. The formula is `snapshot_content_sha256 = SHA256(UTF8("doi-order-snapshot/v1\n") || UTF8(RFC8785(snapshot_hash_input)))`. The stored `line_snapshot_ids` must be byte-for-byte the ID projection of `line_manifest`; duplicate line IDs are invalid.

Invariant: declared_relevant_line_count = captured_relevant_line_count. If equality or completeness proof cannot be established, no snapshot exists.

A new snapshot never inherits dynamic values from an older snapshot. Every dynamic field is newly observed or explicitly UNKNOWN from the current successful read.

### 5.5 DOILineItemSnapshot

Required fields:

- line_snapshot_id: OpaqueId.
- snapshot_id: OpaqueId.
- within_snapshot_line_key: non-empty deterministic key unique within the snapshot.
- stable_source_line_id: observed normalized string; UNKNOWN is allowed.
- prior_line_snapshot_id: OpaqueId, nullable.
- continuity_state: LineContinuityState.
- continuity_proof_type: ContinuityProofType.
- activity: observed normalized LineActivity.
- es_number: observed normalized ESNumber.
- mfg_number: observed normalized MFGNumber.
- ordered_quantity: observed normalized Quantity.
- active_quantity: observed normalized Quantity.
- canceled_quantity: observed normalized Quantity.
- explicitly_available_quantity: observed normalized Quantity.
- quantity_availability: observed normalized QuantityAvailability.
- unit_value: observed normalized Money.
- active_line_value: observed normalized Money.
- drop_ship_state: observed normalized DropShipState.
- availability: observed normalized LineAvailability.
- eta: observed normalized Timestamp or Date.
- line_sales_rep: observed normalized non-customer rep string.
- privacy_safe_raw_hints: field-keyed bounded map, optional.
- line_snapshot_schema_version: literal `doi-line-item-snapshot/v1`.
- line_snapshot_content_sha256: Sha256 under the exact formula below.

The line hash input is the closed object containing exactly every required line field listed above except `line_snapshot_content_sha256`, including `line_snapshot_id`, `snapshot_id`, and explicit-null `prior_line_snapshot_id`; optional `privacy_safe_raw_hints` is serialized as an explicitly empty canonical map when no hints exist. Its formula is `line_snapshot_content_sha256 = SHA256(UTF8("doi-line-item-snapshot/v1\n") || UTF8(RFC8785(line_hash_input)))`. Missing/extra keys, an omitted nullable field, wrong literal/domain, noncanonical money/timestamp/map, or digest mismatch rejects the entire snapshot; no evaluation is appended.

Row position alone MUST NOT establish continuity. If continuity is ambiguous, continuity_state=UNVERIFIED, prior_line_snapshot_id=null, LINE_CONTINUITY_UNVERIFIED is emitted by the evaluation, and all conclusions dependent on cross-snapshot lineage are blocked.

Quantity rules:

- QuantityAvailability FULL requires explicitly_available_quantity = active_quantity.
- PARTIAL requires 0 < explicitly_available_quantity < active_quantity and exact known quantities.
- NONE requires explicitly_available_quantity = 0 when quantities are known.
- PARTIAL never qualifies that line as a deterministic split line; it produces PARTIAL_QTY_INTERVENTION_REVIEW.

### 5.6 DOIEvaluation

An immutable rules result with the complete field-level provenance contract in `provenance_state_contract.md` section 2, incorporated here. Its schema contains: `evaluation_id`, schema version, `case_id`, `evaluated_at`; exact snapshot ID/content hash; exact rules-engine version/bundle hash, reason-registry version/hash, evaluation-schema version, and normalization-contract version; an exact business-calendar version/hash when calendar facts were used; canonical ordered exact relationship-revision, current Action-Context-bound observation, and structured human-fact bindings; canonical input-manifest hash; every output field; output hash; and whole-record content hash.

For this erratum authority, new evaluations bind `rules_engine_version=synthetic.doi.rules/v0.1.5.4`, `rules_bundle_content_sha256=df48446467a81eec9970b22649bf5d86cb5dc09e0ecaad291839774523288ad0`, unchanged `reason_registry_version=0.1.5.3`, unchanged `reason_registry_content_sha256=38eba58f78950c320b9b4e3ece167cc050cae6c11ee0978b98749f3247c2ec86`, unchanged `normalization_contract_version=doi-normalization-contract/v0.1.5.3`, and HumanFact usage registry `doi-human-fact-usage-kind/v1` / `da0612598dcd2b8300d9459af29e192cbf0a3413802cf548fc618713d4721764`. The rules-bundle digest is the SHA-256 of the RFC 8785/JCS object published in `DOI_RULES_BUNDLE_v0.1.5.4.json` and bound by `DOI_AUTHORITY_VERSION_MANIFEST_v0.1.5.4.json`. A stale v0.1.5.3 rules binding, unavailable version, unknown registry version, or digest mismatch is rejected before evaluation append; no substitute is loaded. Prior evaluations retain their original version/hash bindings.

Each relationship binding contains stable relationship ID, exact revision ID/number/content hash, line scope, and usage kind. Each observation binding contains observation ID/schema/content hash, exact relationship revision/hash, exact Action Context, line scope, and usage kind. Each human-fact binding contains closed fact kind, exact event ID/schema/content hash, `HUMAN_VERIFIED` provenance, applicable Action Context/line scope, and one exact closed `HumanFactUsageKind`. A bare manual-decision ID is insufficient.

The exact fact/usage pairs are: compatibility fact to COMPATIBILITY, RESEARCH_STATE, or ACTION_READINESS; no-viable-alternate fact to RESEARCH_STATE; normal-progress fact to ORDER_PROGRESS; coordination fact to COORDINATION; out-of-scope fact to OUT_OF_SCOPE; and no evaluation-binding usage for either DEDUPE fact. Scope and nullability are the closed rules in `provenance_state_contract.md` section 2.4. Complete human-fact bindings sort by ascending UTF-8 RFC-8785 bytes, use natural key `(human_fact_event_id,usage_kind)`, and reject exact duplicates. One fact may appear in multiple distinct legal roles only through distinct keys and exact role-specific scope. Unknown/missing usage, aliases/case variants, illegal pairs, wrong scopes or targets, duplicate bindings, and same-key changed bytes fail before persistence with RC-105; resolved digest mismatch is RC-106. Existing RC-112/111/103 routes for fact provenance, stream conflict, and collision are unchanged.

At evaluation append, all bound IDs must resolve to the exact case/scope/as-of time and their canonical bytes must match the bound digests. Missing, wrong-scope, unavailable, expired, or hash-mismatched input appends no evaluation and never substitutes a newer version. Re-evaluation always appends a new record; later fact, observation, or relationship revision never rewrites an earlier evaluation. After a bound volatile observation reaches its mandated deletion deadline, the immutable evaluation and any immutable opportunity may retain that exact observation ID/hash only as a sealed historical commitment inside the retained case graph. It cannot resolve/reconstruct the deleted target, prove current freshness, or be bound by a new evaluation/action; all such downstream commitments delete with case purge.

Output fields are `doi_state`, registered ordered reasons, canonical opportunity IDs, handling and coordination flags, per-line research state, typed calculated values, and registered recommendations. The exact closed input-manifest, output, and full-record objects, null/set/map ordering rules, literal schemas, and SHA-256 domain formulas in `provenance_state_contract.md` section 2.2 are incorporated without variation; `evaluation_schema_version` is literal `doi-evaluation-record/v1`.

Calculated-value object:

- full_order_value.
- ds_value.
- non_ds_in_stock_value.
- non_ds_delayed_value.
- unknown_value.
- partial_available_value.
- available_to_ship_value.
- potential_split_credit_value.
- potential_swap_credit_value.

Each uses EXACT or UNAVAILABLE. available_to_ship_value includes only active, non-DS lines explicitly IN_STOCK with FULL quantity availability and known value. Website/catalog availability never contributes.

### 5.7 Deterministic classification invariants

1. One or more relevant active lines exist and all are DS → DOI_EXCLUDED + FULL_DS. This evaluation does not itself close the case; an empty line universe is never FULL_DS.
2. At least one active DS line and one active non-DS line → DS_SEPARATION_REQUIRED; non-DS analysis continues.
3. At least one active non-DS IN_STOCK/FULL line and one active non-DS DELAYED line → FULFILLMENT_SPLIT_CANDIDATE. No value or duration threshold applies.
4. One or more relevant active non-DS lines exist and all are explicitly IN_STOCK/FULL on an active unshipped order → ORDER_PROGRESS_REVIEW + DOI_MANUAL_REVIEW.
5. SHIPPED or full CANCELED → DOI_EXCLUDED and verified hard closure.
6. Verified OTHER_REP ownership → DOI_EXCLUDED + REP_TRANSFERRED and reversible closure.
7. Verified DEDUPE note → DOI_EXCLUDED + DEDUPE_CONFIRMED and reversible closure.
8. Payment as sole blocker → DOI_EXCLUDED + PAYMENT_ISSUE_OUT_OF_SCOPE, but does not itself start retention.
9. Payment plus a product opportunity preserves DOI_OPPORTUNITY and adds PAYMENT_ISSUE_PRESENT_OUT_OF_SCOPE.
10. Geography changes handling only; it neither creates nor suppresses an independently proven opportunity.
11. A complete split-eligible `DOMESTIC_STANDARD` snapshot produces `DOI_OPPORTUNITY` + `FULFILLMENT_SPLIT_CANDIDATE` + `HUMAN_DECISION_REQUIRED`; it adds none of `AK_HI_SHIPPING_REVIEW`, `INTERNATIONAL_ORDER_REVIEW`, or `CUSTOMER_CONTACT_REQUIRED_BEFORE_SPLIT`, and geography alone does not require customer contact.
12. A complete split-eligible `DOMESTIC_SPECIAL_REVIEW` snapshot produces `DOI_OPPORTUNITY` + `FULFILLMENT_SPLIT_CANDIDATE` + `AK_HI_SHIPPING_REVIEW` + `HUMAN_DECISION_REQUIRED`; contact remains a case-by-case human decision and `CUSTOMER_CONTACT_REQUIRED_BEFORE_SPLIT` is not added solely from this class.
13. A complete split-eligible `INTERNATIONAL` snapshot produces `DOI_OPPORTUNITY` + `FULFILLMENT_SPLIT_CANDIDATE` + `INTERNATIONAL_ORDER_REVIEW` + `CUSTOMER_CONTACT_REQUIRED_BEFORE_SPLIT` + `HUMAN_DECISION_REQUIRED`.
14. A complete split-eligible snapshot with geography `UNKNOWN` retains `DOI_OPPORTUNITY` + `FULFILLMENT_SPLIT_CANDIDATE`, but geography-dependent action readiness/contact handling remains blocked; no geography-specific handling code is guessed.
15. Known safe opportunities survive unrelated unknown lines or handling/coordination flags. DOI_MANUAL_REVIEW replaces DOI_OPPORTUNITY only when uncertainty prevents every safe overall conclusion.
16. Canceled lines remain in the immutable snapshot but do not contribute to current opportunity/value calculations.
17. Multiple opportunity flags may coexist; queues are overlapping views, not new cases.

## 6. Opportunity entity

### 6.1 DOIOpportunity

Immutable finding from one evaluation under the exact schema/derivation algorithms in `opportunity_kpi_contract.md` section 2, incorporated here. It also stores literal `opportunity_schema_version="doi-opportunity-record/v1"`, immutable `created_at`, and `record_content_sha256=SHA256(UTF8("doi-opportunity-record/v1\n") || UTF8(RFC8785(opportunity_without_record_content_sha256)))` as required by the lifecycle registry; the full object includes the schema literal, generated opportunity ID, creation time, and every governing opportunity field exactly once. The lifecycle wrapper's generic `record_schema_version` is an exact alias of this target field, not another stored opportunity key.

Required fields are: `opportunity_schema_version`, `opportunity_id`, exact `evaluation_id` and `case_id`, registered `opportunity_type`; nonempty canonical ordered `credit_scope` components containing exact same-snapshot `line_snapshot_id`, exact positive applicable quantity, and legal scope role; `credit_scope_hash`; `REALIZED_MERCHANDISE_CREDIT|NON_CREDIT_OPERATIONAL` scenario basis; deterministic `scenario_overlap_key` and `scenario_option_id`; exact alternate relationship/revision/hash and observation where applicable; typed exact-or-unavailable potential value; approval/compatibility gates; canonical blockers; immutable `created_at`; and `record_content_sha256`.

`affected_line_snapshot_ids` is a derived view from `credit_scope`, never writable identity. Row position, absent line identity, unknown quantity, or unverified continuity cannot enter scope. An unproved required scope creates no candidate opportunity and emits `OPPORTUNITY_SCOPE_UNPROVEN`. DS separation now scopes the exact active DS line quantities and remains non-credit.

For each evaluation, overlap groups are connected components of opportunities under the same scenario basis that share a positive scoped line quantity. Their key hashes the canonical group union scope plus basis and deliberately excludes opportunity type/candidate/value. Same order alone never proves overlap. Every distinct option hashes the overlap key plus its exact type/scope/relationship/observation/value/gates. A credit-bearing multi-option group contributes potential from at most one exact selected option; unresolved or conflicting selection emits no group total. Disjoint groups may sum only within an identical currency-and-ISO-registry-version/scale binding; other bindings remain separate.

An opportunity proves only that something potentially useful was identified. It MUST NOT create a DOIIntervention, realized credit, or claim that a human acted.

Alternate invariants:

- candidate ES = ordered ES → never an alternate; only EXACT_SKU_RECHECK.
- EXACT_MFG requires different ES and equal canonical MFG/OE.
- MFG_CROSS_REFERENCE and MFG_SUPERSESSION require different ES and different MFG plus explicit evidence.
- FUNCTIONAL_ALTERNATE requires different ES and fresh per-order human compatibility review before action.
- Every substitution requires CUSTOMER_APPROVED before the human may manually swap in OA.

## 7. Alternate/product-knowledge entities

### 7.1 DOIAlternateRelationship

Durable, non-customer product identity plus a rebuildable current-revision projection. The complete revision schema and canonical identity/hash rules in `provenance_state_contract.md` section 3 are incorporated here.

Required fields:

- alternate_relationship_id: OpaqueId.
- relationship_schema_version: VersionId.
- relationship_identity_canonical_bytes: exact RFC-8785/JCS bytes under `doi-alternate-relationship-identity-v1`.
- relationship_identity_sha256: Sha256 over the canonical product-only identity tuple.
- ordered_es_number: ESNumber.
- candidate_es_number: ESNumber.
- ordered_mfg_number: MFGNumber, nullable only under the FUNCTIONAL rule below.
- candidate_mfg_number: MFGNumber, nullable only under the FUNCTIONAL rule below.
- relationship_type: AlternateRelationshipType.
- applicability_identity: canonical product-only structured object or null.
- created_at: Timestamp.
- current_relationship_revision_id: OpaqueId.
- current_revision_number: integer >= 1.
- current_state: AlternateRelationshipState.

Enforce `UNIQUE(relationship_identity_sha256)` and byte-compare stored canonical identity bytes before allocating/reusing the stable relationship ID. Exact identity bytes always reuse the same base ID. After that lookup, exact replay of the current semantic revision payload reuses the current revision; a different valid semantic payload with the exact current predecessor invokes TR-083 and appends revision `n+1`. Same identity digest with different bytes is RC-103 and creates nothing. The relationship and its identity MUST contain no case ID, Order Number, line snapshot, Action Context, customer data, source-batch row reference, originating-order provenance, reconstructable hash, or customer-derived key. Current fields are projection caches only; immutable revisions are authoritative.

### 7.1A DOIAlternateRelationshipRevision

Each change appends an immutable revision containing the complete `ALTERNATE_RELATIONSHIP` event envelope from `provenance_state_contract.md` section 1.2 plus: revision ID/schema aliases; stable relationship ID; monotonically increasing revision number equal to stream sequence; exact closed relationship event type; relationship type; normalized ordered/candidate ES and conditionally required MFG/product-only applicability facts; `SYSTEM_VERIFIED|HUMAN_VERIFIED` provenance; canonical nonempty product-only source-provenance records; `ACTIVE|SUPERSEDED|INVALIDATED`; creation time; exact predecessor revision/event/full-event hash; optional successor relationship for supersession; required invalidation reason where invalidated; semantic revision-content hash; and full-event content hash.

Revision 1 has no predecessor. Revision `n+1` must point to the exact current revision. Exact semantic replay is idempotent. Same revision identity/number with different canonical content fails closed. Supersession and invalidation append terminal revisions; no terminal revision returns to active. An evaluation always binds the exact revision ID/number/hash it used.

Relationship invariants:

- ordered_es_number != candidate_es_number for every relationship.
- EXACT_MFG requires both MFG values non-null and equal.
- MFG_CROSS_REFERENCE and MFG_SUPERSESSION require both MFG values non-null and different.
- FUNCTIONAL permits either both MFG values null or both non-null and different; one-null and equal-non-null forms are illegal.
- The base identity hash includes both explicit MFG values/nulls, relationship type, ES pair, and applicability identity. Every revision repeats those identity fields exactly; an identity-field change creates a new relationship rather than a revision.
- Non-rediscovery causes no lifecycle change.
- ACTIVE changes only on explicit source-grounded contradictory or superseding evidence.
- FUNCTIONAL may be surfaced as prior knowledge but must be re-reviewed for each application/order.
- Relationship retention is indefinite after complete de-linking from customer/order context.

Deterministic creation/application rules:

- first complete exact-MFG proof creates exactly one ACTIVE `EXACT_MFG` revision; first complete explicit cross-reference proof creates exactly one ACTIVE `MFG_CROSS_REFERENCE` revision; first complete explicit supersession proof creates exactly one ACTIVE `MFG_SUPERSESSION` revision;
- exact identity/revision replay reuses the one relationship/revision and creates no duplicate;
- when the creation fixture includes the required fresh current observation, it creates exactly one customer-approval-required alternate opportunity;
- a matching future order reusing an ACTIVE exact relationship creates exactly one alternate opportunity; when its current observation is absent/stale, that opportunity is exactly `RECHECK_REQUIRED_BEFORE_ACTION` and cannot be substitution-ready;
- prior FUNCTIONAL knowledge creates exactly one `FUNCTIONAL_COMPATIBILITY_REVIEW_REQUIRED` opportunity/review state for the new application/order and never reuses compatibility approval.

### 7.2 DOIAlternateObservation

One immutable timestamped volatile observation.

Required fields:

- alternate_observation_id: OpaqueId.
- observation_schema_version: VersionId.
- alternate_relationship_id: OpaqueId.
- relationship_revision_id: OpaqueId.
- relationship_revision_content_sha256: Sha256.
- observed_at: Timestamp.
- observation_content_sha256: Sha256.
- retention_policy_version: literal `doi-retention-calendar90-ny/v1`.
- timezone_database_version: VersionId.
- observation_purge_eligible_at: Timestamp equal to the exact `calendar90(observed_at)` result.
- source_system: synthetic_CATALOG | MANUFACTURER_SOURCE | ORDER_ADMIN.
- observed_price: observed normalized Money.
- observed_availability: observed normalized AlternateAvailability.
- observed_eta: observed normalized Timestamp or Date.
- observation_source_refs: non-customer product SourceRef set.
- action_context_id: OpaqueId, nullable.
- case_id: OpaqueId, nullable and derivable only through the Action Context.

Stored age alone never makes an observation current. Customer contact or substitution requires a newly successful explicit Recheck Alternate (or targeted alternate refresh within Recheck Order) whose observation is linked to that action_context_id. An older stored observation may inform research but cannot satisfy the action gate.

Effective deletion is the earlier of nominal `observation_purge_eligible_at` and the current linked-case `purge_eligible_at`. At actual case purge the observation and every context link delete atomically even if nominal expiry is later. Reopening before purge cancels that case deadline; the nominal observation clock remains. Expiry or early case purge does not invalidate or supersede the durable relationship.

### 7.3 DOIActionContext and context links

The exact entity/event schema in `provenance_state_contract.md` section 4 is incorporated here. Each immutable base belongs to one retained case and binds exact evaluation, opportunity, closed context kind, creator, creation time, and a globally unique retained `attempt_intent_id` plus canonical request bytes/hash. The store resolves the token before allocating an ID: same token/same bytes reuses the context/event, same token/different bytes rejects RC-110, and a fresh token is mandatory for a later attempt and creates a new context. Append-only context events project `OPEN|CLOSED_COMPLETED|CLOSED_ABANDONED|CLOSED_SUPERSEDED`.

An alternate observation is current for action only through the immutable `DOIActionContextObservationLink` to the exact OPEN context and compatible case/evaluation/opportunity/relationship revision/line scope; TR-085 appends the accepted case-linked observation and link atomically. A structured HumanFact instead carries the exact `action_context_id` and compatible scope directly in its own typed immutable event; it never creates or aliases an observation-link record. A closed/wrong-scope context cannot satisfy action readiness. Context creation never represents or authorizes an OA action or mutation. Observation/link targets and their separate one-event volatile lifecycle streams/wrappers delete atomically at the earlier governed deadline, leaving no direct target/index/receipt. The core case ledger remains replayable through its retained evaluation record; that evaluation/opportunity may retain only a sealed observation ID/hash commitment that cannot reconstruct the target or satisfy freshness. Contexts and every remaining case-owned detail/commitment delete with case purge.

## 8. Intervention, verification, reversal, and resulting-order entities

All records in this section use the common immutable event envelope, canonical content hashes, exact predecessor/sequence guards, and deterministic reducers defined in `provenance_state_contract.md` sections 1 and 5. Typed streams exist separately for human facts, contact, DEDUPE, attention/manual review, WWC, resulting-order links, intervention action verification, and value/correction/reversal. Source facts, human facts, evaluation outputs, and lifecycle events never overwrite or masquerade as one another.

### 8.1 DOIIntervention

A current projection derived from immutable verification history. It is created only after an actual human OA action is verified.

Required fields:

- intervention_id: OpaqueId.
- case_id: OpaqueId.
- intervention_type: InterventionType.
- source_opportunity_ids: non-empty set.
- action_occurrence_id: nonempty stable proof/attestation occurrence identity; part of the ACTION natural key and not a generated intervention ID.
- action_natural_key_sha256: Sha256 over the canonical logical ACTION natural key in `opportunity_kpi_contract.md` section 4.2.
- verification_evidence_fingerprints: canonical ordered non-empty set<Sha256>, a rebuildable corroboration projection rather than intervention identity.
- action_evidence_occurred_at: Timestamp of the first accepted proof/attestation fact.
- action_occurred_at: Timestamp, nullable only when otherwise complete action proof cannot establish the exact business action instant; proof time may not substitute.
- action_verification_provenance: VerificationProvenance.
- status: InterventionStatus.
- original_realized_value: Money, nullable while value is UNVERIFIED and always null when NOT_APPLICABLE.
- reversed_value: Money, zero while a credit-bearing intervention has no verified reversal; null when NOT_APPLICABLE.
- net_realized_value: Money, nullable while value is UNVERIFIED and always null when NOT_APPLICABLE.
- value_verification_state: ValueVerificationState.
- current_value_provenance: VerificationProvenance, nullable while unverified.
- resulting_order_link_id: OpaqueId, nullable unless split.
- replacement_line_snapshot_id: OpaqueId, nullable unless substitution.

Unique keys: `action_natural_key_sha256` and the pre-allocation occurrence guard `UNIQUE(case_id,action_occurrence_id)`. The natural key is case + ACTION kind + intervention type + stable `action_occurrence_id`; proof time is excluded, while business action time, target/link/replacement, exact scope, and quantities are material. One exact evidence fingerprint plus identical bytes is idempotent; a distinct compatible system/human fingerprint for the same natural key/material effect may append a corroborating `DOIVerificationEvidenceRecord` only, but creates no second action-verification event or lifecycle wrapper and reuses the same intervention and KPI effect. Reusing the occurrence ID with a different intervention type/natural bytes or changed material fails with RC-102 before any second intervention/effect allocation. `action_verification_provenance` is fixed by the first accepted action event; later compatible proof in either SYSTEM-to-HUMAN or HUMAN-to-SYSTEM order never rewrites it, the lifecycle projection binding, or the retained contribution/bucket. A proven digest collision fails with RC-103. For a credit-bearing intervention, null `action_occurred_at` emits RC-099 and creates no retained monetary row; evidence/record time is never substituted. Non-credit `DS_SEPARATION` does not receive RC-099 merely because no monetary attribution instant is required. Re-observing the same verified action, including after case reopen, MUST NOT create credit again.

If a recheck detects a change but cannot prove the action, it creates INTERVENTION_VERIFICATION_REQUIRED only. No intervention or realized value exists.

`DS_SEPARATION` requires `value_verification_state=NOT_APPLICABLE`, null monetary fields, and no resulting-order/replacement-line link. It is a verified intervention for operational history but never enters monetary KPI calculations.

### 8.2 DOIInterventionVerificationEvent

This former umbrella record is replaced by the typed append-only `DOIInterventionActionVerificationEvent` and `DOIInterventionValueEvent` streams in `provenance_state_contract.md` sections 5.7–5.8. Action events bind exact case/opportunity/action type, immutable evidence identities, normalized action payload, provenance, natural evidence key, evidence fingerprint, canonical payload bytes/hash, and stream predecessor. Value events use exactly `ORIGINAL_VALUE_VERIFIED|ORIGINAL_VALUE_CORRECTED|REVERSAL_VERIFIED|REVERSAL_CORRECTED|REVERSAL_VOIDED` and bind the exact intervention, per-kind Money/null fields, exact target/predecessor where required, provenance, evidence identities/fingerprint, canonical payload/hash, and stream predecessor. Their `event_kind` equals envelope `event_type`; the per-kind required/null table in the provenance module is authoritative.

Exact fingerprint plus identical canonical payload is idempotent and appends nothing. Same natural evidence key or apparent digest with contradictory canonical payload fails closed and leaves the prior projection. A shared `UNIQUE(case_id,intervention_id,logical_occurrence_id)` guard spans every original-value/correction/reversal/correction/void kind; cross-kind reuse or any changed natural/material bytes is RC-102 and cannot create a second reducer effect. Stream predecessor failure routes RC-111 first. All case-derived keys/fingerprints delete with purge.

Human `ORIGINAL_VALUE_VERIFIED` and `REVERSAL_VERIFIED` events require an exact known amount. Estimated, rounded, ranged, or "about" values are rejected and contribute zero.

Action and value verification are independent. A verified intervention with unverified value contributes zero to realized-credit KPIs.

While the detailed case remains retained, when later SYSTEM_VERIFIED evidence conflicts with HUMAN_VERIFIED value, append both the system event and conflict reason. The system value becomes the current authoritative original_realized_value; retained history is preserved until purge.

### 8.3 Value/correction/reversal reduction

For a value-verified intervention, reduce accepted events strictly by stream sequence. Select the authoritative original-value chain: an accepted SYSTEM_VERIFIED chain controls over a HUMAN_VERIFIED chain; within one provenance, only a valid explicit correction of the current authoritative event replaces it. Determine active reversals by applying every accepted REVERSAL_CORRECTED or REVERSAL_VOIDED chain to its exact predecessor; corrected/voided predecessors remain immutable history but do not also contribute.

`reversed_value` is the exact sum of active reversals sharing the authoritative original's identical currency-and-ISO-registry-version/scale binding, and `net_realized_value = authoritative_original_realized_value - reversed_value`. If no exact authoritative original exists, monetary contribution is zero. Currency or registry/scale mismatch, negative reversal, reversal above original, broken predecessor, or conflicting natural evidence fails closed: reject the disputed event, preserve the last valid projection, and apply zero disputed delta.

The projection is VERIFIED when reversed value is zero, PARTIALLY_REVERSED when strictly between zero and original, and REVERSED when equal. A valid correction/void may move among all three states; reversal state is not monotonic.

### 8.4 Resulting-order search, exact link, and mapping revision

`DOIResultingOrderLinkSearch` is a case-linked search projection with required `resulting_order_link_search_id`, schema version, exact parent case/opportunity/optional Action Context, exact credit-scope hash, creation time, `current_search_state: ResultingOrderLinkSearchState`, and current search-event ID. Its immutable events use the `RESULT_LINK_SEARCH` stream and enforce `UNIQUE(resulting_order_link_search_id,search_occurrence_id)`. `credit_scope_sha256==credit_scope_hash` and logical `candidate_set_sha256==search_candidate_set_sha256` are exact canonical-byte/hash aliases. Search events have null child Order Number, natural-link key, exact-link ID, and mapping identity. `NOT_FOUND` and candidate `AMBIGUOUS` exist only here.

An exact `DOIResultingOrderLink` has required:

- resulting_order_link_id: OpaqueId.
- link_schema_version: VersionId.
- parent_case_id: OpaqueId.
- relationship_type: literal FULFILLMENT_SPLIT_CHILD.
- child_order_number: non-null exact OrderNumber.
- natural_key_canonical_bytes and natural_link_key_sha256 over exact `(parent_case_id, relationship_type, child_order_number)`.
- source_opportunity_id, optional exact Action Context, and exact credit-scope hash.
- created_at: Timestamp.
- current_state: ResultingOrderLinkState.
- current_mapping_revision_id and current event ID.

Its immutable evidence events use the `RESULT_LINK_EXACT` stream and the split state fields in `provenance_state_contract.md` section 5.6; search-state fields are null. Creation and every evidence change append that typed event. Exact rediscovery is idempotent; distinct agreeing evidence may append corroboration; contradictory exact mapping evidence projects this existing exact link to `AMBIGUOUS`, adds `RESULTING_ORDER_LINK_REVIEW`, counts disputed split credit as zero, and never overwrites prior evidence or changes a search projection.

Every `DOIResultingOrderLinkRevision` uses the full `RESULT_LINK_MAPPING` event envelope and closed revision schema in `opportunity_kpi_contract.md` section 4.3: revision number equals stream sequence; predecessor ID/full-event hash is exact; event type is initial verified, conflict recorded, or conflict resolved; semantic mapping hash and full-event hash are distinct. Event, revision, logical material, and evidence use the byte-identical canonical `moved_components[].{parent_line_snapshot_id,child_line_snapshot_id,quantity}` schema and one `mapping_content_sha256`; legacy label aliases are normalized once and never persisted. TR-110 owns initial revision 1 and verified resolution revision `n+1`; TR-111 owns conflict revision `n+1`. A search record never creates a mapping revision. Same-customer identity or temporal proximity alone is never sufficient. Customer comparison may occur transiently during extraction but no customer identity, hash, or raw evidence may be persisted.

Split realized credit requires a verified child link and verified child order-level TARGET_REP sales rep. Substitution realized credit requires deterministic replacement-line continuity and verified replacement line-level TARGET_REP sales rep. Missing/different/ambiguous rep means unverified value and zero KPI credit.

## 9. Manual user-action contract

All actions require authenticated human intent, append DOI-owned audit records, and MUST NOT mutate OA.

### 9.1 Run DOI Review

Inputs:

- exact locked spreadsheet ID.
- one explicit confirmed SourceTabRole with exact visible title and gid.
- literal schema mapping version `synthetic-doi-queue-v0.1`.

Preconditions:

- the fixed source contract in `source_retention_contract.md` section 1 recognizes the exact workbook/tab/sentinels and positional A/B record model. A1 and B1 are intentionally blank and do not require literal headers.
- every populated A/B record has Order Number in column A row 2+, a positive integer canonicalized to a decimal integer string, and scalar-text Assigned Rep in column B; TARGET_REP scope is exact locale-independent `lower(trim(B)) == "TARGET_REP"`; no fuzzy matching.

Effects:

1. immediately create one distinct DOIRun and source-import attempt ordinal 1; after a terminal non-success, a deliberate retry while the run remains IN_PROGRESS appends only the next ordinal/fresh attempt ID, never a second run;
2. validate the exact locked schema plus every populated record's A normalization and B scalar type, then coherently scan actual A/B source records, ignoring the filter-range endpoint and E:O row data; any record invariant failure stops the whole import before hashing/staging/OA;
3. calculate both personal source hashes and persist only allowlisted TARGET_REP records/aggregates; never persist unrelated other-rep detail;
4. create/reuse a safe immutable DOISourceBatch only after coherent validation;
5. perform read-only OA extraction only after import success, safe batch binding, and per-order execution approval;
6. append snapshots/evaluations for successful complete extracts;
7. record only extraction metadata and RECHECK_REQUIRED for order failures. A final schema/acquisition/change/integrity failure terminalizes the attempt/run as FAILED with RC-090 plus its exact source reason and zero OA reads. A deliberate pre-OA abort terminalizes only that attempt as ABORTED_PRE_OA with empty reasons, leaves the run IN_PROGRESS, and requires a later attempt to terminalize it.

### 9.2 Recheck Order

Input: existing case_id. No throttle.

Effect: one read-only whole-order extraction attempt. Success appends a new snapshot and evaluation. Failure appends no snapshot/evaluation and sets RECHECK_REQUIRED. It may include targeted alternate refresh if explicitly requested.

### 9.3 Recheck Alternate

Inputs: alternate_relationship_id and explicit action_context_id.

Effect: read-only product-source research and one new DOIAlternateObservation. It never changes OA or the durable relationship solely because a result was not rediscovered.

### 9.4 Human action verification

Inputs: case_id, InterventionType, exact occurrence timestamp, structured evidence reference, and attestation that the action actually occurred.

Effect: the first valid complete proof atomically creates exactly one `DOIIntervention` and one `HUMAN_VERIFIED` action-verification event bound to its exact evidence fingerprint. Byte-identical replay returns the existing intervention/event and creates zero additional intervention, verification, credit-bearing, or KPI effects. Conflicting material under the same occurrence/natural key fails closed and preserves the prior projection. A plan, intention, or recommendation is rejected.

### 9.5 Human value verification

Inputs: existing intervention_id, exact Money, evidence reference, and attestation that the value is known rather than estimated.

Effect: append HUMAN_VERIFIED value event and recalculate the intervention projection. Estimates are rejected and KPI contribution remains zero.

### 9.6 Mark No Viable Alternate

Inputs: case_id, exact line identity, actor, timestamp.

Preconditions: the line has been human reviewed.

Effect: append a manual-decision event and a new evaluation of the existing snapshot with NO_VIABLE_ALTERNATE_HUMAN_CONFIRMED. It does not create an intervention, DEDUPE closure, or OA note.

### 9.7 DEDUPE decision and Recheck DEDUPE Order

Approve DEDUPE records HUMAN_APPROVED_AWAITING_OA_VERIFICATION only. The human separately writes the OA note. Recheck DEDUPE Order performs a read-only complete recheck.

- verified DEDUPE note → reversible DEDUPE_CONFIRMED closure;
- no verified note → remain active/recheck-required;
- new source-grounded DOI eligibility during an explicit DEDUPE recheck before purge → reopen the same retained case and cancel the purge deadline.

### 9.8 Record contact state

Human records ContactState only. Sales Assist sends no email/message and performs no Synthetic Message Source write. CUSTOMER_APPROVED is required before a human substitution; standard domestic split contact is not mandatory by default.

### 9.9 Confirm resulting-order link

Human may confirm an ambiguous/not-found child relationship with structured evidence. This appends HUMAN_VERIFIED link history; it does not open or edit either order except through separately authorized read-only extraction.

### 9.10 Record human out-of-scope closure

An explicit human action may create reversible HUMAN_OUT_OF_SCOPE closure. Merely leaving a queue, FULL_DS, or payment-only evaluation is not this action.

## 10. Source absence

For each previously ACTIVE TARGET_REP case absent from a newly confirmed batch:

1. set SOURCE_ABSENT_RECHECK_REQUIRED;
2. perform exactly one read-only disappearance verification in that run;
3. on complete extraction, append snapshot/evaluation;
4. SHIPPED/CANCELED closes hard; REP_TRANSFERRED/DEDUPE_CONFIRMED closes reversibly;
5. if still active and TARGET_REP-owned, remain ACTIVE, retain the source-absence event, and evaluate current facts;
6. incomplete verification sets RECHECK_REQUIRED and creates no snapshot/evaluation.

Source absence alone never closes a case.

## 11. Lifecycle and retention

Hard closures: SHIPPED, CANCELED. They do not reopen under v0.1.

Reversible closures: REP_TRANSFERRED, DEDUPE_CONFIRMED, HUMAN_OUT_OF_SCOPE. Source-grounded evidence obtained by an authorized explicit recheck may reopen the same case only while that detailed case identity still exists before purge.

On verified terminal closure:

- terminal_closed_at is set;
- `purge_eligible_at = calendar90(terminal_closed_at)` under `doi-retention-calendar90-ny/v1` and the persisted timezone-database version;
- `calendar90` converts the anchor to `America/New_York`, advances exactly 90 local dates preserving wall time, resolves a nonexistent spring-forward target to the first valid instant after the gap and an ambiguous fall-back target to the later occurrence, and persists the resulting UTC instant;
- detailed case retention continues until `purge_eligible_at`; fixed 2,160-hour arithmetic and an undefined timestamp addition are forbidden.

Reopening:

- the accepted `CASE_REOPENED` and following `PURGE_CANCELED` each serialize the complete required `PriorClosureRetentionBindingV1`; the nested bytes identify the retained prior closure event, kind/classification/verified instant, source proof, policy/version/timezone/tzdb/calendar rule, active deadline, and closure-bearing projection revision/hash;
- the reopen binding is byte-equal to the independently constructed locked authoritative state, and cancellation copies those exact nested bytes while independently revalidating them; hash-only inference, omission, reconstruction from current configuration, or any mismatch fails before append and leaves the prior closed state unchanged;
- lifecycle_state becomes ACTIVE;
- terminal closure fields become null in the current projection;
- purge_eligible_at becomes null;
- PURGE_CANCELED_ON_REOPEN is recorded;
- the cancellation payload explicitly binds the canceled deadline, exact reopen cause event, exact reopen resolution source, resulting `CANCELED` deadline state/null deadline, same case identity, and resulting revision/projection hash;
- prior snapshots, evaluations, intervention history, and credit remain until a later purge;
- existing intervention fingerprints prevent double counting.

A later verified terminal closure after reopen calculates a new `calendar90` deadline from that new instant. Re-observing the same closure without a reopen does not extend the deadline. If the timezone/policy binding cannot resolve deterministically, no approximate or earlier purge is scheduled.

While the case exists, all same-case reopening, intervention/value correction, reversal, partial reversal, system-over-human authority, intervention supersession, and per-order duplicate-credit-prevention guarantees are mandatory. `SYSTEM_VERIFIED` evidence may supersede conflicting `HUMAN_VERIFIED` evidence only during this retained-detail window.

At purge:

- atomically finalize the case's then-current exact gross/reversed/net aggregate contribution into non-identifying aggregate KPI history before deleting the detail that supports it;
- delete DOIOrderCase and all case-owned children: exact Order Number, case source admission proofs/bindings, lifecycle events, snapshots, lines, evaluations, opportunities, interventions, action/value/reversal verification events, resulting-order identity/links, case-linked alternate observations/action contexts, work items, extraction attempts, and reconstructable order/customer identity. Attempt-owned staged records, source-row references, and their locators are never case children and delete independently under TR-114;
- delete or de-link source-batch fingerprints/references when no retained case requires them;
- retain no de-identified per-order archive, tombstone, persistent order/customer hash, case identifier, predecessor link, or order-specific audit/log record;
- retain only finalized non-identifying aggregate KPI history;
- retain verified product relationships only after complete removal of all order/case links.

Purge is the irreversible case-finalization boundary. After it, the system no longer guarantees same-case reopening, late reversal or partial reversal, late human-versus-system correction, cross-purge duplicate-credit detection, or per-order historical reconciliation. A reversal/correction request whose target identity is no longer retained is rejected with `CASE_IDENTITY_NOT_RETAINED`; it appends no case/intervention event, changes no finalized aggregate, and retains no order-specific rejection record.

If the same real-world Order Number later enters the workflow, no retained identity exists by which to recognize it as historical. It follows the ordinary `NONEXISTENT → ACTIVE` case-creation path, receives a new case_id, and has no predecessor/reopen link. The implementation MUST NOT reconstruct prior identity, query or create a tombstone/hash/archive, infer that the new case is a reopen, or attempt cross-purge deduplication. Cross-purge duplicate-credit prevention is explicitly not guaranteed. These post-purge limits do not weaken any guarantee before purge.

A completely de-linked product-only DOIAlternateObservation is deleted at `calendar90(observed_at)`. A case-linked observation is deleted at the earlier of its nominal deadline and the current linked-case purge, so no Action Context or case linkage survives. Durable product-only relationship revisions are the only alternate knowledge eligible for indefinite de-linked retention.

## 12. Aggregate KPI contract

### 12.1 Daily KPI source-of-truth model

The exact schemas, key derivations, reducers, and transaction rules in `opportunity_kpi_contract.md` section 3 are incorporated here. The only persisted monetary source-of-truth grain is `LOCAL_CALENDAR_DAY` in `America/New_York`; weekly, monthly, quarterly, yearly, and `ALL` views are computed rollups, never competing stored buckets.

`DOIRetainedKPIContribution` is a case-linked rebuildable projection unique on `(kpi_schema_version, intervention_id)` and on its deterministic ID. Its exact ID bytes/hash use `doi-retained-kpi-contribution-id/v1` over `{kpi_schema_version,intervention_id}` as specified in the KPI module; tuple lookup precedes insert and digest/preimage conflict is RC-103. It binds exact verified action instant and immutable New York local attribution date, exact ISO currency and `iso_4217_registry_version`, leaf intervention/provenance classes, current count/gross/reversed/net integer coefficients, full authoritative retained-ledger hash, projection revision, and audit update time. An action with no exact occurrence instant creates no monetary contribution. Later value verification, correction, or reversal always recomputes the full retained ledger and updates the original verified-action date; evidence-review time never becomes attribution time. Currency or registry-version change is an integrity conflict, never a bucket move/rescale.

`DOIAggregateKPIDailyBucket` is a non-identifying leaf bucket uniquely keyed by `(kpi_schema_version, LOCAL_CALENDAR_DAY, America/New_York, local_calendar_date, currency_code, iso_4217_registry_version, intervention_type, action_verification_provenance)`. Its deterministic ID hashes that tuple. It stores exact inclusive local-midnight `period_start` and exclusive next-local-midnight `period_end` UTC instants (therefore 23/24/25-hour days are legal), retained and finalized count/gross/reversed/net integer coefficients, revision, and computed time. It stores no case/order/line/intervention/result-link/source reference, evidence hash, canonical payload, or drill-through key. Different currency-registry bindings remain separate leaf buckets and rollups.

Every accepted ledger change runs one ACID full-projection upsert: exact same ledger hash and canonical bytes is a no-op; otherwise lock the contribution and bucket, verify immutable identity, apply `new_projection-old_projection` only to retained fields, and commit both together. Currency or bucket identity cannot move silently. Money aggregates only when both currency code and ISO-4217 registry version/scale are identical; other bindings remain separate and no FX/base-currency/combined scalar exists.

Case purge and finalization are one ACID transaction: re-reduce and verify every contribution, subtract the exact current values from retained fields, add the same values to finalized fields, prove totals unchanged, then delete contributions and the complete per-order graph. Any mismatch rolls back transfer and deletion. Before-commit failure changes nothing; after commit no case/contribution identity remains for a retry, so exactly-once is achieved without a surviving per-case marker. Late per-order evidence after purge changes no aggregate.

Potential DOI Impact uses the exact opportunity overlap/option-selection contract in section 6.1. At most one option from a real overlap group contributes; disjoint resolved groups may sum only within an identical currency-and-ISO-registry-version/scale binding. Unresolved overlap or mixed currency/registry bindings never produce a guessed combined number.

## 13. Privacy allowlist and denylist

Allowed only when operationally required:

- exact Order Number;
- source/run references;
- assigned/current rep;
- line ES#/MFG#/quantity/value;
- inventory/ETA/DS facts;
- DOI states/flags/reason codes;
- structured WWC/DEDUPE findings;
- intervention/credit values and verification history;
- timestamps;
- geography classification;
- resulting-order links.

Forbidden:

- customer name, email, phone, VIN;
- address components or full address;
- full OA note bodies;
- persistent customer hashes;
- OA HTML, DOM dumps, screenshots, page copies;
- credentials, tokens, cookies, session data;
- message bodies;
- arbitrary free-text notes;
- other-rep row/order details from the manager sheet.

## 14. Historical evidence contract

### 14.1 DOIHistoricalAssertionManifestEntry

`HISTORICAL_DOI_ASSERTION_MANIFEST_v0.1.jsonl` is an immutable derived assertion index over the byte-preserved 213-case source corpus. It MUST contain exactly one entry per source case in deterministic corpus order.

Each entry MUST contain these exact top-level fields:

- manifest_version: VersionId;
- corpus_sequence: integer from 1 through 213, unique and contiguous;
- case_identifier: object `{case_id, kind}` preserving the existing privacy-minimized corpus identifier and its declared kind;
- historical_layer: HistoricalLayer;
- immutable_source_refs: object containing the immutable source artifact name/hash/line and relocatable workbook row references;
- source_observations: ordered privacy-minimized source-observation metadata copied from the immutable case record;
- positive_assertions: ordered independently source-supported positive assertions;
- historical_recorded_assertions: ordered source-preserved historical statements, kept explicitly separate from expected results;
- historical_research_findings: ordered independently source-supported research findings;
- human_review_requirements: ordered source-supported requirements, possibly empty;
- unsupported_or_missing_facts: ordered explicit limitations;
- replayability_blockers: non-empty ordered blockers for every original-corpus entry;
- represented_rule_families: unique ordered rule-family strings;
- represented_categories: scoped annotation objects;
- release_gate_accounting: per-entry accounting fields used to reconcile the manifest without changing the historical layer;
- complete_whole_order_oracle: literal false for every original-corpus entry;
- expected_result_input_prohibited: literal true;
- negative_whole_order_inference_prohibited: literal true;
- privacy_projection: structured privacy-minimization result.

Every positive assertion, recorded assertion, and research finding MUST carry `assertion_id` or `finding_id`, `kind`, `source_record_id`, exact `scope`, `source_ref_ids`, `checkability` (`MACHINE_CHECKABLE` or `DOCUMENTATION_COVERAGE_ONLY`), and an explicit indication that it does not establish complete-order eligibility.

Historical classification/final-label fields MUST NOT enter an assertion's value, an executable fixture input, or an expected-result calculation. Positive assertions derive only from independently supported facts/findings. Negative research findings remain limited to their explicit researched scope. Incomplete source data MUST NOT be converted into a negative or universal whole-order assertion.

### 14.2 Authoritative accounting and release reconciliation

The original corpus accounting is fixed at:

- source cases: 213 unique exact Order Numbers;
- exact Order Number duplicates: 0;
- EXECUTABLE_HISTORICAL: 0;
- HISTORICAL_ASSERTION_HUMAN_REVIEW: 59;
- SUPPORTING_ONLY_NOT_REPLAYABLE: 154;
- frozen complete end-to-end historical expected results: 0.

Every offline release MUST verify that all 213 entries are present exactly once; immutable corpus bytes/hashes are unchanged; all SourceRefs resolve; privacy lint passes; layer/coverage counts reconcile; all 59 human-review cases and 154 supporting-only cases remain represented; no unsupported assertion or target leakage exists; and no non-replayable case enters the executable denominator. The historical execution denominator remains 0 until independently source-sufficient complete whole-order evidence is added as a separate corpus. Zero is not a release failure when deterministic synthetic coverage remains release-blocking for every required versioned rule family.

Historical-to-synthetic mapping MUST cite related case/source evidence, identify its layer and assertion scope, and state whether a fictional fixture was structurally inspired by it. It MUST also attest that no real customer/order identity or historical expected target was copied. Historical labels never become hidden fixture inputs.

### 14.3 Future executable history

Separately authorized supervised shadow mode may produce new executable-history candidates only when each capture independently proves complete relevant line-set capture; contains all required order- and line-level facts; binds exact source, extractor, schema, and rules versions; satisfies privacy minimization; preserves immutable source-fact binding; and prevents expected-result leakage. New evidence MUST remain separate from, and MUST NOT mutate or retroactively upgrade, the original 213-case baseline.

## 15. Fail-closed invariants

1. No exact, valid TARGET_REP OrderNumber → no OA read.
2. Unrecognized source schema → current attempt `SCHEMA_REJECTED` with RC-002/090 and zero OA reads; the run remains `IN_PROGRESS` only for an accepted legal next-ordinal retry, otherwise the final failure terminalizes it `FAILED`.
3. Assignee conflict → conflicted order receives zero OA reads.
4. Source changed during import when proven → no executable batch/work proceeds.
5. Incomplete whole-order proof → no snapshot or evaluation.
6. Required source unreadable → extraction failure, not UNKNOWN.
7. Unknown normalized field → contain uncertainty; do not infer.
8. Ambiguous line continuity → block lineage-dependent conclusions.
9. Same ES candidate → reject as alternate.
10. No current alternate observation → no customer-contact/substitution action gate.
11. Unverified action → no intervention.
12. Unverified/estimated value → zero realized KPI.
13. Impossible lifecycle/value transition → reject, preserve last valid projection, emit STATE_TRANSITION_NOT_ALLOWED.
14. Any possible OA mutation capability → build/release failure.
15. Missing or malformed historical assertion entry, count/hash/layer mismatch, unsupported assertion promotion, or target leakage → release failure.
16. Post-purge request for a deleted case/intervention identity → reject with CASE_IDENTITY_NOT_RETAINED, no aggregate change, and no reconstructable rejection record.

## 16. Freeze determination and deferred extraction details

### 16.1 Freeze determination

The authoritative purge-finality amendment makes purge the explicit end of all case-linked guarantees. Within-window protections remain mandatory; after purge, aggregate history is final and later same-number input creates an unlinked new case. `SYN-RET-011/012` are deterministic release-blocking oracles. Potential overlap is fail-closed as UNAVAILABLE, DS separation is a non-credit intervention, and alternate freshness is explicitly tied to the current recheck context. This remediation-candidate contract still requires independent re-audit before any formal freeze declaration.

### 16.2 Deferred OA/source reconnaissance details

- exact OA selectors, routes, page contracts, and read-only capability allowlist;
- OA-only field mappings and validators. The manager workbook source contract is no longer deferred: `synthetic-doi-queue-v0.1` is locked, including blank A/B headers and positive-integer Order Number normalization;
- exact OA status/phrase mapping to ACTIVE, DELAYED, IN_STOCK, CANCELED, SHIPPED, and UNKNOWN;
- whole-order completeness proof mechanism;
- stable OA line identifier and deterministic composite-lineage inputs;
- exact current-rep values that map to TARGET_REP ownership;
- privacy-safe WWC/DEDUPE extraction rules and source locators;
- exact geography source fields and transient classification procedure;
- payment-condition source fields;
- explicit split/resulting-order relationship evidence available in OA;
- synthetic business holiday-calendar source and maintenance mechanism;
- ETA normalization and improvement display;
- functional-alternate fitment fields.

These are intentionally deferred extraction/configuration details. They MUST be filled by controlled read-only reconnaissance and versioned mappings, never by fuzzy guessing.


## 17. Authoritative v0.1.5 remediation extensions

The following requirements extend and, where necessary, replace incomplete v0.1.1 entity definitions. The following package modules/registries are incorporated into this machine contract and persistence model: `source_retention_contract.md`, `provenance_state_contract.md`, `opportunity_kpi_contract.md`, `DOI_LIFECYCLE_EVENT_PAYLOAD_REGISTRY_v0.1.5.md`, and `DOI_OA_CAPABILITY_POLICY_v0.1.5.md`. Their field-level schemas, canonical algorithms, transition amendments, purge edges, and deterministic oracles are normative. For `DOIOrderLifecycleEvent`, the dedicated lifecycle registry has exact-schema precedence over any older generic-envelope prose. Earlier fields remain required only where they do not conflict with an explicit replacement in those modules.


This section is the authoritative narrow remediation of the independent freeze audit and the Codex offline implementation dry run. It does not reopen the validated historical corpus, synthetic/historical separation, complete-whole-order gate, privacy denylist, purge-finality business decision, or permanent OA read-only invariant. Where an earlier clause conflicts with this section, this section replaces that clause. The complete machine and persistence schemas are normative companion artifacts.

### 17.1 Source import, reusable batch identity, and run outcome

Every explicit `Run DOI Review` creates one immutable `DOIRun` plus attempt ordinal 1 before acquisition and may append sequential attempts while that run remains `IN_PROGRESS`. Attempt IDs are opaque and nonderived; `(run_id,attempt_ordinal)` and the attempt-owned command token are independently unique/idempotent. A retry is legal only after a terminal non-success attempt, uses the next ordinal/fresh ID, and cannot follow run terminal. The run v2 projection/events retain only `source_import_attempt_count`, never an attempt ID or manifest. Attempts are distinct from `DOIExtractionAttempt` and record only the selected spreadsheet/tab identity available before failure, attempted schema version, timestamps, closed outcome, registered reason set, privacy-safe counts, and—only on success—the coherent-source fingerprint protected by that attempt owner's explicit batch reference. `ABORTED_PRE_OA` is intermediate only, uses `SOURCE_IMPORT_ABORTED` and an empty reason set, leaves the run `IN_PROGRESS`, and requires a later attempt. Every failure including RC-091 uses `SOURCE_IMPORT_FAILED`, null coherent fingerprint/batch, RC-090 plus the exact source reason, and no candidate batch digest/preimage. A terminal run assigns every one of its attempts the same exact `calendar90(run.completed_at)` deadline; a nonterminal run assigns none.

A reusable `DOISourceBatch` is created only from one coherent validated read. Its identity binds spreadsheet ID, exact selected tab identity, schema-mapping version, normalized TARGET_REP-only row-content hash, and privacy-minimized assignee-conflict fingerprint. The conflict fingerprint contains only the sorted intersection between valid TARGET_REP Order Numbers and valid Order Numbers simultaneously observed with a normalized assignee other than TARGET_REP. Other-rep names, unrelated numbers, rows, and metadata are excluded. Scan-specific totals and physical row locators live on the import attempt/run records, not the reusable batch.

Per-run staged records bind to the exact successful import attempt and are attempt-owned operational detail. Before creating/updating a case, copy only the closed case-owned `DOICaseSourceAdmissionProofV1`; no staged/run/attempt/row/tab/actor identity may enter the retained case graph. A final failure from the closed v0.1.5 acquisition/schema/change/integrity union is `FAILED`, creates no executable batch, and causes zero OA reads. A coherent run with any individual blocked/exceptioned order is `COMPLETED_WITH_EXCEPTIONS`, even when every in-scope order is individually blocked and zero evaluations succeed. `COMPLETED` permits no exception.

### 17.2 Evaluation provenance and immutable state histories

Every evaluation binds exact snapshot ID/content hash, rules version/content hash, reason-registry version/content hash, applicable calendar version/content hash, exact relationship revision IDs/content hashes, current Action-Context-bound observation IDs/content hashes, human-fact event IDs/content hashes, evaluation time, canonical input hash, and canonical output hash. At append or new-evaluation validation time, an unavailable referenced revision or hash fails closed and no substitute evaluation is legal. After a governed earlier observation-target deletion, replay of an already accepted evaluation validates the retained evaluation's own full-record hash and its sealed, non-resolvable observation ID/hash commitment without dereferencing the expired target; that commitment cannot prove current freshness, reconstruct the target, or enter any new evaluation or action and deletes with the case graph.

Reusable relationship knowledge uses stable `DOIAlternateRelationship` identity plus immutable monotonically numbered `DOIAlternateRelationshipRevision` records. Creation, evidence change, supersession, and invalidation append revisions/events; no revision is overwritten. Evaluations remain reproducible after later relationship change.

Append-only typed histories govern resulting-order links, contact state, DEDUPE state, attention/manual-review conditions, WWC projection, Action Context, intervention action/value/correction/reversal, and relationship state. Source facts, human facts, evaluation outputs, and lifecycle events remain separate entity classes and cannot overwrite one another.

The exact DEDUPE and attention machine schemas are incorporated from `provenance_state_contract.md` sections 5.1, 5.3, and 5.4. `HumanFactKind` and `HumanFactResultCode` include the two and only two DEDUPE decision pairs: `DEDUPE_APPROVED`/`DEDUPE_APPROVED`/`DEDUPE_DECISION_FACT(APPROVED)` and `DEDUPE_REJECTED`/`DEDUPE_REJECTED`/`DEDUPE_DECISION_FACT(REJECTED)`. `dedupe_review_id` is derived before the candidate event is hashed from the exact case ID, deterministic candidate DEDUPE occurrence ID, and candidate evaluation ID/content hash; the derived review ID is then embedded in the candidate event. The candidate event ID/hash is deliberately not an input to the review ID. The decision evidence fingerprint binds that review, decision, instant, authorized immutable human-verification reference, actor/provenance, and correction predecessor under the literal domains in the provenance contract. Human DEDUPE state events require the exact accepted HumanFact ID and full-event hash. TR-061/TR-062 append the fact, linked DEDUPE event, lifecycle wrappers, and projection in one ACID transaction. Only the exact predecessor-bound approval-to-rejection correction before OA-note verification is legal; every other same-review conflict is RC-112. `OA_NOTE_SYSTEM_VERIFIED` is a separate later read-only source fact and cannot construct a human decision.

`DOIAttentionEventV2` uses literal `doi-attention-event/v2` and the closed cause/resolution fields in the provenance contract. Its sole cause key is `SHA256(UTF8("doi-attention-cause-key/v2\n") || UTF8(RFC8785(exact_cause_object)))`. SET requires the complete cause group and exactly null resolution/clear/time/reason fields. CLEAR requires the copied cause/key of the exact active SET, that SET event ID, and a complete independent resolver/time/reason group; resolver fields are excluded from the cause key. Enforce the SET and CLEAR natural identities, unique constraints, active-SET FK, byte-equal cause check, resolver hash/revision checks, and replay reducer. TR-093 permits exactly RC-070 system-link, RC-071 human-link, or RC-073 negative-search resolution. TR-095 permits RC-053/054 for the corresponding active partition and null only for registered NOT_APPLICABLE/EXPIRED branches.

### 17.3 Action Context

`DOIActionContext` binds one explicit human decision/action-preparation attempt to exactly one retained case, evaluation, opportunity, closed context kind, and creation time. Fresh alternate observations are current for action only through an explicit immutable context-observation link. A later attempt creates a new context. Context creation performs no OA action and grants no mutation authority. Observation/link targets and their volatile wrappers delete at the earlier observation/case deadline; contexts and sealed historical evaluation/opportunity commitments delete with case purge. Reusable relationships may survive only after complete de-linking.

### 17.4 Opportunity credit scope and scenario overlap

Every opportunity contains immutable `credit_scope`: a canonical ordered set of exact snapshot-line components with exact applicable quantity and registered scope role. Scope derives only from the immutable snapshot. Row position and unverified continuity are illegal scope inputs. If exact scope cannot be established, credit-bearing potential is unavailable.

`scenario_overlap_key` is derived candidate-by-candidate only after building the complete overlap graph for one evaluation+basis and finding the connected component containing that candidate's exact scope. The sole hash input is the canonical `doi-scenario-overlap-v1` object containing the component's `scenario_basis` and conservative maximum-quantity `group_credit_scope`; evaluation ID, opportunity type, and individual candidate scope hashes/preimages are excluded. Disconnected components in one evaluation+basis receive different keys, while transitive overlap receives one key. Each distinct option has `scenario_option_id`. Same-order opportunities are not presumed overlapping, but at most one option from an actual overlap component may contribute to a selected potential scenario. Missing/ambiguous/partial graph input fails closed and unresolved overlap keeps the options visible with combined potential unavailable.

### 17.5 Evidence identity and idempotency

System-verifiable actions, values, reversals, corrections, and link evidence use RFC 8785 canonical payloads and SHA-256 fingerprints binding retained case, event type, immutable evidence/snapshot/source revision, exact relationship/link, quantities/values, currency, and provenance as applicable. Exact fingerprint plus identical payload is idempotent. The same natural evidence key with contradictory content fails closed; an apparent fingerprint collision with different canonical bytes is a fatal integrity failure. Resulting-order links additionally use the retained natural key `(parent_case_id, relationship_type, exact_child_order_number)` and a separate moved-line/quantity content fingerprint. Duplicate reversal evidence never creates a second reversal. All case-derived evidence fingerprints are deleted at case purge.

### 17.6 Daily multicurrency KPI contract

The source-of-truth monetary grain is `LOCAL_CALENDAR_DAY` in `America/New_York`. A durable non-identifying daily bucket key binds KPI schema version, local date, ISO-4217 currency, and metric/contribution class. Its `[period_start, period_end)` UTC bounds are the exact local-midnight bounds and may span 23, 24, or 25 hours. Weekly, monthly, quarterly, and yearly views are rollups only.

TR-106 applies the exact exhaustive table in `opportunity_kpi_contract.md` section 3.3. It first derives the date/currency base set: exact-date valid or absent currency `{RC-063}`; exact-date invalid `{RC-063,RC-094}`; null-date valid or absent `{RC-063,RC-099}`; null-date invalid `{RC-063,RC-094,RC-099}`. It then unions at most one rep-proof modifier. For `FULFILLMENT_SPLIT` with an exact accepted `AUTO_LINKED|HUMAN_CONFIRMED` child link, missing/different/ambiguous resulting-order-level TARGET_REP rep adds RC-074; the exact link remains unchanged. For `PRODUCT_SUBSTITUTION`, missing/different/ambiguous replacement line-level TARGET_REP rep adds RC-075; parent order-level rep is insufficient and the replacement-line binding remains unchanged. Verified applicable TARGET_REP rep adds neither. Exact-date/valid blocked branches are therefore exactly `{RC-063,RC-074}` and `{RC-063,RC-075}`; each preserves one verified intervention, leaves value `UNVERIFIED`, creates one count-1 zero-money row, and realizes zero. `DS_SEPARATION` is `NOT_APPLICABLE`, all money/currency null, no row, and none of RC-063, RC-074, RC-075, or RC-099 merely for lacking a monetary date. Both rep modifiers, wrong intervention type, or contradictory branch is RC-081 before TR-106 with no row/state append. Reject invalid monetary material while preserving the independently valid single action/intervention.

A verified intervention with exact business action time is attributed to that action's local date; proof time cannot substitute. Later exact value verification, correction, and reversal update the retained case-linked contribution for that original attribution bucket. Only identical currency plus identical ISO-registry version/scale aggregate; other bindings remain segmented, no FX/rescale is inferred, and a combined headline is unavailable unless all contributions share both. At purge the case's final deduplicated contribution is atomically finalized into the corresponding non-identifying daily/currency/registry buckets while every case-linked contribution and join key is deleted. Retrying after successful purge finds no retained case and cannot change the aggregate.

### 17.7 Retention for observations, failed imports, and no-case rejections

All 90-day rules use the exact local-calendar algorithm in section 3.2, including spring-gap and fall-overlap resolution. Case-linked observation/link targets and their target-owned volatile lifecycle wrappers delete atomically at `min(observation_nominal_expiry, linked_case.purge_eligible_at)`; no direct target/index/receipt survives. A preexisting immutable evaluation/opportunity may retain only its sealed observation ID/hash commitment until case purge, unusable for lookup/reconstruction/freshness. Every source-import attempt outcome—including success, all registered failures, and intermediate abort—receives the same immutable `source_import_attempt_purge_eligible_at=calendar90(run.completed_at)` only when its associated run becomes terminal; no nonterminal run assigns a deadline. TR-114 atomically removes each due attempt projection/event graph, attempt/run/source/tab/actor/time/failure/fingerprint/revision/row identity, attempt-owned staged/rejected data, logs/caches/temp exports/files/exceptions/indexes, batch/reference edges, and the transient purge event itself. A staged record never becomes case-retained: case lifecycle binds only `DOICaseSourceAdmissionProofV1`, which carries no run/attempt/row/tab/actor identity. Run identity deletes when its deadline is due and no explicit non-due owner remains; a retained owner prevents premature deletion, and final-owner deletion removes every reverse lookup atomically. Reusing a batch never extends a deadline. Only closed `DOISourceImportAggregateV2` monthly outcome counts survive; exact/reconstructable identities and drill-through keys may not.

### 17.8 Complete legal-transition requirement

Every mutable projection and every immutable creation/appending action named by this specification must have a registered legal transition with deterministic from-state, guard/event, resulting projection, reason/event codes, illegal behavior, and synthetic oracle. This includes initial relationship and resulting-link creation; result-link-review and human-coordination attention add/clear; relationship revision; contact and DEDUPE initialization; Action Context; source-import attempt; no-case rejection retention; KPI contribution/finalization; and all existing case/intervention/WWC paths. Counts are derived from the complete registries and are not quotas.

### 17.9 Complete reason ownership and oracle parity

`DOI_REASON_OWNERSHIP_MATRIX_v0.1.5.3.md` under literal `doi-reason-ownership/v1`, authority revision `0.1.5.3`, remains machine-authoritative beside `DOI_REASON_CODE_REGISTRY_v0.1.5.3.md`. Exactly 115/115 codes have at least one external rule/service owner and deterministic asserting oracle. Every emitted/referenced code exists, every registry code is asserted, and no orphan, undefined code, duplicate, or unversioned alias exists. Unknown code/version fails before append/persistence. RC-016, RC-017, and RC-115 follow the unchanged closed field-specific UNKNOWN mapping in Section 2.2; multiple independent UNKNOWN fields produce exact set union. TR-106's base sets plus mutually exclusive RC-074 and RC-075 modifiers remain byte-normalized across all governing artifacts and generated from one closed table. The v0.1.5.4 rules bundle changes only to bind the new HumanFact usage registry/applicability function; it adds no reason or transition.

OA safety codes are partitioned. `RC-082 OA_WRITE_PROHIBITED` is emitted only by the system/build boundary when a forbidden `click` helper or equivalent write-capable module/manifest capability is found; fail before runtime/package promotion and never emit RC-083 (`SYN-OA-RO-003`, `SYN-OA-CAP-002`, `SYN-REASON-OWN-005`, with `SYN-REASON-OWN-006` as the negative/non-applicable control). `RC-083 UNSAFE_ACTION_REJECTED` is emitted only by the runtime user/API dispatch boundary for each canonical unsafe predicate: deliberate `POST|PUT|PATCH|DELETE`, GraphQL mutation/write-RPC, generic mutation-capable action/click request, background-poll request, or unallowlisted side-effectful read. Each fails before dispatch and never emits RC-082 (`SYN-OA-RO-001/005`, `SYN-REASON-OWN-006..008`). Both branches have zero OA mutation, DOI append, persistence, and dispatched network side effect beyond the local blocked-probe observation.

### 17.10 Every-outcome source-import-attempt deletion

The closed schemas/algorithms and exact TR-114 transaction in machine section 4.3B and `source_retention_contract.md` section 13 govern. Every success/failure/abort attempt receives the same exact run-terminal calendar90 deadline; no nonterminal run assigns one. TR-114 deletes the complete due attempt operational graph, attempt-owned staged/rejected/reference graph, and transaction-local RC-114 event in one serializable transaction, preserves a run only while an explicit non-due owner remains, and deletes the due run at final reference. Only closed month/outcome/count `DOISourceImportAggregateV2` survives. `SYN-IMPORT-RET-001..022` must all pass, including published fixed hashes, injected rollback, last-reference, host-timezone, DST, and all-outcome parity branches.

### 17.11 Remediation status and safety

No clause here authorizes live OA access, production implementation, source-workbook modification, or any OA write primitive. The exact workbook schema in section 5.1.1 is an explicit user decision based on observed structure; the earlier unauthorized temporary-export procedure remains blocked and is not relabeled as a certified reconnaissance pass.

This remediation package must return to the independent auditor. It does not declare the specification frozen.

DOI_FREEZE_REMEDIATION_CANDIDATE = READY_FOR_INDEPENDENT_AUDIT
