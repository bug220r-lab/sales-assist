
> **Sanitized supporting reference.** This file is a mechanically sanitized derivative of
> source material supplied for the synthetic proof of concept. Historical status/freeze
> language is nonbinding. The curated files under `specs/` govern. No production-system
> access or real-data use is authorized by this reference.

# Synthetic Sales Assist — DOI Technical Specification v0.1.5 — Independent-Audit Remediation Candidate

Authority patch: v0.1.5.4 HumanFactUsageKind erratum candidate; independent audit required; not a freeze declaration.

**Candidate date:** 2026-08-09  
**Operational timezone:** `America/New_York`  
**Status:** remediation candidate; independent re-audit required; not frozen; offline specification work only; not production authorization  
**Rules namespace:** `synthetic.doi.rules.v0.1.5-remediation-candidate`

## 1. Authority and scope

This candidate incorporates the locked portions of **Synthetic Sales Assist — DOI Technical Specification v0.1 — Working Draft — 2026-08-08**, the 2026-08-09 formalization task, and the authoritative 2026-08-09 purge-finality and historical-reintegration amendment. The newest amendment controls wherever the authorities differ, particularly for the 90-day purge boundary, finalized aggregate history, post-purge recurrence, and mandatory use of all 213 historical records as scoped evidence.

The two historical spreadsheets and the five original corpus artifacts are evidence, not policy. A historical classification never becomes an oracle unless preserved source facts and this rules version independently reproduce it.

This package authorizes:

- deterministic offline rules-engine and storage implementation;
- synthetic tests, mandatory historical-assertion verification, and future replay only from independently complete whole-order captures;
- later adapter implementation only after separately authorized controlled reconnaissance.

It does **not** authorize live Synthetic Order Portal (OA) access, OA reconnaissance, production code, customer communication automation, or modification of any source workbook.

## 2. Permanent OA safety invariant

OA is permanently `READ_ONLY`.

Allowed operations are only:

`Observe → Search → Navigate → Extract → Validate → Calculate → Classify → Recommend → Report`.

The DOI system must never modify an order, line, product, quantity, shipment, fulfillment state, payment state, sales credit, Sales Rep, note, customer information, or any other OA state. It must never submit a mutating OA form or request, activate a business-action control, or provide a generic mutation, arbitrary-click, or write-capable helper.

All order splits, substitutions, DS separation, DEDUPE notes, rep changes, cancellations, releases, customer contacts, and other business actions occur manually outside Sales Assist by an authorized human. Sales Assist may later verify their effects through a separately authorized read-only recheck.

The current offline release has no OA/browser adapter or host permission. Its exact structural capability surface is the closed `DOI_OA_CAPABILITY_POLICY_v0.1.5.md`: empty browser/host/optional permissions, no content/background/external messaging, only fixture-local pure module capabilities, and a fail-closed source/dependency/manifest/registry/generated-output scan. The policy's complete permission and interaction-helper denylist, alias/wrapper/computed-name analysis, mutation canaries, network denial, page/fixture hash invariance, and empty mutation journal are release-blocking.

A future adapter requires a separate frozen reconnaissance-derived contract. Only that future contract can enumerate exact read-only host/navigation/extraction capabilities. Until then, any browser/host/network capability, unrecognized control/request method, `POST|PUT|PATCH|DELETE`, form/input action, state-changing GET, GraphQL write, arbitrary selector/click/type/submit helper, page-script execution, cookie/session/download/native/background capability, wrapper, or unresolved dynamic dispatch found in packaged source, a dependency, manifest, registry, module, helper, or generated output is RC-082 and fails the offline build before runtime. A deliberate local negative-harness request is not a packaged capability: `POST|PUT|PATCH|DELETE`, GraphQL mutation/write-RPC, generic action/click, background-poll, or unallowlisted side-effectful-read input offered to the user/API dispatcher is exclusively RC-083 and is rejected before dispatch with RC-082 absent and zero network/OA effect beyond the local blocked-probe observation.

## 3. Privacy and retention

### 3.1 Permitted active-case data

Only operational DOI facts may be retained:

- exact Order Number and case-local identifiers;
- source, batch, run, extraction, snapshot, and evaluation references;
- assigned/current rep classification or value needed for DOI ownership;
- line ES#, MFG#/OE, quantity, exact value, inventory, ETA, DS, cancellation, and continuity facts;
- DOI dispositions, flags, reasons, structured WWC/DEDUPE findings, and human verification records;
- exact potential/realized/reversed/net credit facts;
- timestamps, coarse DOI geography classification, and resulting-order links.

Never retain customer name, email, phone, VIN, full address, full OA note bodies, message bodies, credentials, cookies/session data, persistent customer hashes, OA HTML, DOM dumps, screenshots, page copies, or any equivalent reconstructable customer material. Geography is stored only as `DOMESTIC_STANDARD`, `DOMESTIC_SPECIAL_REVIEW`, `INTERNATIONAL`, or `UNKNOWN`.

Narrow non-sensitive raw strings may be retained only when needed to explain a failed normalization, for example an unrecognized availability phrase. Raw values must be field-scoped, length-bounded, and pass privacy lint.

### 3.2 Case retention

Detailed case information is retained until `purge_eligible_at`, exactly 90 `America/New_York` local calendar dates after the most recent verified terminal **transition**. Calculate it by converting the closure instant to local time, advancing the local date by 90 while preserving wall-clock time, resolving a nonexistent spring-forward target to the first valid instant after the gap and an ambiguous fall-back target to the later occurrence, then persisting the resulting UTC instant. An undefined `timestamp + 90 days` or fixed 2,160-hour shortcut is prohibited.

Hard terminal closures:

- `SHIPPED`;
- full `CANCELED`.

Reversible terminal closures:

- `REP_TRANSFERRED`;
- `DEDUPE_CONFIRMED`;
- explicit human `HUMAN_OUT_OF_SCOPE_CLOSED`.

`DOI_EXCLUDED` is a disposition, not by itself a retention terminal. In particular, `FULL_DS` and a system-observed payment-only exclusion do not start the purge clock unless a separately valid terminal closure occurs. Merely leaving an actionable queue never starts retention.

A source-grounded return of DOI eligibility may reopen a reversibly closed case only while its detailed identity still exists before purge. Reopening:

- reuses the same `DOIOrderCase`;
- creates no second episode or replacement case;
- appends a lifecycle event;
- cancels the pending purge deadline;
- never repeats previously recognized credit.

A later terminal transition starts a new 90-day deadline. Re-observing the same unchanged closed state does not reset the clock. Hard closures cannot reopen in DOI v0.1. While the detailed case exists, all same-case reopening, intervention correction, realized-value correction, reversal, partial reversal, system-over-human value authority, intervention supersession, and per-order duplicate-credit-prevention guarantees remain mandatory.

Purge is the irreversible case-finalization boundary. At the 90-day deadline, the case's then-current exact aggregate contribution is finalized into non-identifying aggregate KPI history and the entire per-order graph is atomically deleted. Deletion includes exact Order Number; case identity; snapshots and lines; evaluations; lifecycle history; opportunities; interventions and all action/value/reversal verification history; resulting-order identity/linkage; extraction/work-item records; case admission proofs/source bindings; and every case-owned source-batch reference. Attempt-owned staged/source-row records are never in this case graph and delete independently under TR-114. Case purge invokes TR-113: a batch remains only when another explicit retained reference exists, and otherwise the complete identifying batch/fingerprint graph is deleted. No batch/case/order/customer tombstone or persistent hash, de-identified per-order record, reconstructable archive, predecessor link, or identifying audit/log record survives.

Only non-identifying aggregate KPI history and separately governed, completely de-linked non-customer reusable product knowledge may survive. Aggregate KPI history contains no case, order, source-row, line, intervention, or resulting-order identifier and becomes final for the purged contribution. No later individual-order reversal, partial reversal, human-versus-system monetary correction, per-order reconciliation, or duplicate-credit correction can change that finalized history because the linking identity deliberately no longer exists. `SYSTEM_VERIFIED` evidence may supersede conflicting `HUMAN_VERIFIED` evidence only before purge.

If the same real-world Order Number later enters DOI after its prior detailed graph was purged, no retained identity exists to classify it as a recurrence. The normal `NONEXISTENT → ACTIVE` path creates a new `DOIOrderCase` with a new case ID. The system must not claim or infer a reopen, reconstruct prior identity, search for a tombstone/hash/archive, retain or create a predecessor link, or attempt cross-purge deduplication. Cross-purge duplicate-credit prevention and per-order historical reconciliation are explicitly not guaranteed. This intentional privacy limitation does not weaken any within-retention guarantee.

### 3.3 Product-knowledge retention

Verified, non-customer `DOIAlternateRelationship` knowledge is de-linked from cases and retained indefinitely, subject to `SUPERSEDED` or `INVALIDATED` lifecycle events. It may contain product identities and evidence provenance, never order/customer identity.

`DOIAlternateObservation` is volatile. Its nominal expiry uses the same exact 90-local-calendar-day algorithm from `observed_at`. Effective deletion is the earlier of that nominal expiry and the linked case's `purge_eligible_at`. A completely de-linked product-only observation follows only its nominal rolling deadline. A case-linked observation, context-link target, and their separate one-event volatile lifecycle wrappers delete atomically at that effective deadline; no direct record, wrapper, index, or deletion receipt survives. An immutable evaluation/opportunity may keep only its already accepted sealed observation ID/hash commitment inside the case graph until case purge; it cannot resolve/reconstruct the target or establish freshness. Storage retention does not imply freshness; an observation is current only when the live target is explicitly bound to the relevant immutable `DOIActionContext` created for the contemplated action.

## 4. Time and identity foundations

- Operational timestamps are timezone-aware instants; UI display uses `America/New_York`.
- Money is the exact three-field object `{amount_decimal,currency_code,iso_4217_registry_version}`. The uppercase ISO-4217 code and canonical decimal scale must both resolve under that exact registry version. Implementations may persist the equivalent signed integer coefficient at the registry-defined scale, but binary floating point is forbidden. DOI v0.1.5 performs no currency conversion. Arithmetic requires identical currency code plus identical registry version/scale; other bindings remain separately segmented, and no mixed-currency or mixed-registry monetary headline is legal.
- Order Number validation/canonicalization is controlled by the exact versioned source or OA validator, never by a generic fuzzy normalizer. For `synthetic-doi-queue-v0.1`, a scalar digit text (including leading zeros) or provider-proved exact positive-integer lexeme is validated, then canonicalized to its decimal integer string with leading zeros removed; zero, sign, fraction, exponent, Boolean/date/error, and precision ambiguity fail the entire import. OA identity uses its separately versioned exact validator. No validator may fuzzy match or guess an Order Number.
- One retained exact Order Number maps to one `DOIOrderCase`.
- Case-local line identifiers never derive from customer data.
- WWC uses a versioned SyntheticCo business calendar: Monday–Friday excluding configured SyntheticCo-observed holidays. The exact calendar source remains a pre-production configuration dependency.

## 5. Manager-sheet source ingestion

### 5.1 Human-triggered selection

The manager maintains one persistent team Synthetic Queue Store with Monday, Wednesday, and Friday operational tabs. Sales Assist never polls or monitors it. Every `Run DOI Review` requires an explicit human confirmation of exactly one tab. The UI may suggest a likely tab but must not silently select it.

The versioned source schema must deterministically identify the Assigned Rep and Order Number columns. Header matching is exact according to that schema; fuzzy guessing is prohibited. Failure produces `SOURCE_SCHEMA_UNRECOGNIZED`, records only a minimal import attempt, and causes zero OA reads.

#### 5.1.1 Locked positional schema `synthetic-doi-queue-v0.1`

This schema is an explicit user-approved workbook-specific business contract. It records the approved structure; it does not convert the earlier blocked browser/export procedure into a certified reconnaissance pass.

The schema recognizes only:

- spreadsheet ID `SYNTHETIC-SOURCE-ID`;
- `DOI Monday`, sheet gid `0`;
- `DOI Wednesday`, sheet gid `1267803554`;
- `DOI Friday`, sheet gid `593832135`.

For the explicitly selected tab, the integrity anchors are exact: `A1` is blank, `B1` is blank, `E1` is `Rep`, `F1` is `# Of Orders`, and `G1` is `Completed`. Source records begin at row 2. Column A is Order Number and column B is Assigned Rep. Because A1 and B1 are intentionally blank, literal header-name recognition is not required for this schema and MUST NOT be invented. The positional exception applies only to this exact spreadsheet/schema version; no other workbook may use positional guessing.

On every populated A/B source record, column A accepts only a positive integer represented exactly as a scalar integer or outer-trimmed decimal-digit text. Zero, negative, fractional, exponent, comma-formatted, boolean, blank, lossy, or non-scalar values are invalid. Canonicalization is exact base-10 integer text with no sign and no leading zeroes. Column B must be scalar text. Personal scope is the exact locale-independent normalization `lower(trim(B)) == "TARGET_REP"`; no fuzzy, alias, initials, rep-code, or approximate match is legal. A scalar empty B is non-TARGET_REP; a non-scalar B is a schema/type failure.

Columns E:O are summary/reference areas outside the source-order row model. The importer determines the populated A/B source span from actual source records beginning at row 2 and MUST NOT use the Synthetic Queue Store filter-range endpoint as the source-span boundary.

Any workbook ID, selected-tab ID/title, anchor, column-type, populated-record A value/type, populated-record B type, or positional invariant failure produces `SOURCE_SCHEMA_UNRECOGNIZED` plus `SOURCE_IMPORT_ATTEMPT_FAILED`, terminalizes the current `DOISourceImportAttempt` with RC-002/090, creates no coherent source batch/work/case/evaluation, and causes zero OA reads. The run remains `IN_PROGRESS` only if an exact legal pre-OA next-ordinal retry is accepted; otherwise that final failed attempt drives `RUN_TERMINAL(FAILED)` with the same reasons. All populated A/B records are validated before personal-scope filtering, hashing, staging, or OA work. Duplicate valid TARGET_REP Order Numbers remain legal inputs to the deterministic duplicate/conflict rules; they are never assumed impossible.

### 5.2 Personal-scope filtering

The personal manager-sheet assignee is `TARGET_REP`, matched only by the exact locale-independent expression `lower(trim(B)) == "TARGET_REP"`. It is distinct from OA rep identifiers such as `target_rep` and `target_rep_web`, whose exact production mapping remains an adapter configuration dependency.

Rows for other reps may be read transiently only to filter and check integrity. Their names, raw assignees, unrelated Order Numbers, row contents, source locators, and metadata must not be persisted or opened in OA. The only survivors are allowlisted non-identifying aggregates plus the assignee-conflict fingerprint digest/cardinality derived solely from already-in-scope TARGET_REP Order Numbers; the canonical conflict set itself is transient.

Processing order is fixed:

1. validate the exact workbook/tab/anchor schema before any OA read;
2. validate every populated record's A value/type and B scalar type before any OA read;
3. transiently classify every valid record's assignee;
4. select only explicit TARGET_REP rows;
5. perform transient cross-assignee conflict detection;
6. normalize and fingerprint TARGET_REP rows only;
7. deduplicate/stage, then begin eligible OA reads.

Scalar blank/unrecognized assignee rows are never guessed, persist no row identity, and never cause OA reads. Any populated record with an invalid A value or non-scalar B fails the entire source import under `synthetic-doi-queue-v0.1`; it is not downgraded to a row-only rejection.

### 5.3 Duplicates and conflicts

Exact duplicate Order Numbers within one source version produce one staged order while preserving every applicable TARGET_REP source reference.

- under `synthetic-doi-queue-v0.1`, every duplicate TARGET_REP A/B row merges deterministically with `RC-006`; E:O is outside the row model even when its values differ;
- `SOURCE_ROW_CONFLICT`/`RC-007` is compatibility-reserved and unreachable for this mapping; a future mapping must separately version explicit conflict-capable row metadata before making it reachable;
- the same Order Number tagged TARGET_REP and a nonblank non-TARGET_REP scalar assignee in the same source version produces `SOURCE_ASSIGNEE_CONFLICT` and blocks OA access for that order; a blank scalar B is non-TARGET_REP but is not an assignee-conflict cause;
- no other-rep row detail is persisted as part of conflict evidence.

Other valid staged orders may continue.

### 5.4 Immutable source batches and runs

`DOISourceBatch` identity is the tuple:

`spreadsheet_id + explicitly_selected_tab_identity + schema_mapping_version + normalized_TARGET_REP_row_content_sha256 + assignee_conflict_fingerprint_sha256`.

The TARGET_REP-row hash input is RFC 8785 canonical UTF-8 JSON containing all normalized TARGET_REP row content in stable source-record order before deduplication, with only allowlisted fields. It includes duplicate/conflicting TARGET_REP rows. The assignee-conflict fingerprint is SHA-256 over the canonical sorted set of only those already-in-scope TARGET_REP Order Numbers that also occur in the same coherent source read with a normalized assignee other than TARGET_REP. It contains no other representative name, unrelated other-rep Order Number, other-rep row content, or customer/order metadata. Unrelated other-rep changes do not change the batch identity; creation or removal of a conflict involving a TARGET_REP Order Number does. A schema-mapping-version change always changes the identity. Only an identical full tuple may reuse the immutable batch.

Every intentional executable review creates a new immutable `DOIRun`, even when it reuses a batch. Each exact Order Number appears at most once in a run. Across runs it links to the same retained case.

The reusable batch contains only the identity-bound TARGET_REP-content hash (never TARGET_REP row content/source refs), TARGET_REP-derived counts, and the privacy-minimized conflict-fingerprint digest/cardinality. Per-read totals, out-of-scope counts, physical source-row locators, and other scan-specific diagnostics belong to the immutable `DOISourceImportAttempt`, not the reusable batch. Per-run staged records bind to the exact successful attempt so inserting unrelated other-rep rows cannot silently reuse stale source locators or eligibility. They remain attempt-owned operational detail and delete with that attempt; before case creation/source-present, only a closed case-owned `DOICaseSourceAdmissionProofV1` is copied, with no run/attempt/row/tab/actor identity or staged-record reference.

Every retained batch has explicit persisted `DOISourceBatchReference` owners under `source_retention_contract.md` section 2.4: retained run, coherent import attempt, staged source record, no-case rejected record, or case source binding. A reference deletes only with its owner. TR-113 locks and evaluates the exact retained reference set after due owner deletion. While any owner remains, the batch bytes are unchanged; after the final owner is released, the same transaction deletes the complete batch ID, identity bytes/hash, TARGET_REP hash, conflict fingerprint/cardinality, derived counts, and every batch-identifying event/cache/log/export. No hash/tombstone/lookup key survives; only the closed non-identifying import aggregate remains. Failure rolls back the whole owner/reference/batch/aggregate transaction.

Every explicit human `Run DOI Review` invocation first creates one immutable `DOIRun` and source-import attempt ordinal 1. One or more sequential attempts may belong to the run: an opaque fresh attempt ID and next stable positive ordinal are legal only after a terminal non-success and while the run remains `IN_PROGRESS`; changed replay, an ordinal gap/concurrency, or a post-terminal attempt fails before append. A deliberate `ABORTED_PRE_OA` attempt uses `SOURCE_IMPORT_ABORTED`, an exact empty reason set, leaves the run in progress, and requires a later attempt to terminalize it. If schema recognition, source access, or coherent acquisition finally fails—including proven `SOURCE_CHANGED_DURING_IMPORT`—the final attempt and run terminate `FAILED` with RC-090 plus the exact source reason, no executable batch/work/case/evaluation, and zero OA reads. Lack of connector support for an optional defensive proof is capability metadata, never successful stability proof.

Run status is:

- `IN_PROGRESS`: TR-001 `RUN_INVOCATION_ACCEPTED` created a valid active `DOIRun`; `started_at` is present, `completed_at`, `run_purge_eligible_at`, and the initial `source_batch_id` are null, governed processing metadata may advance, and the run is not completed;
- `COMPLETED`: every eligible staged order completed;
- `COMPLETED_WITH_EXCEPTIONS`: source ingestion completed coherently and at least one individual order was blocked or exceptioned, including the edge case where every in-scope order was individually blocked and zero normal evaluations succeeded;
- `FAILED`: a run-level source/system condition prevented successful source execution, including unrecognized schema, proven source change, source inaccessible/unreadable, or another registered run-level fatal condition.

Only `COMPLETED`, `COMPLETED_WITH_EXCEPTIONS`, and `FAILED` are terminal. TR-002, TR-003, and TR-004 consume `IN_PROGRESS` and set the non-null terminal `completed_at` plus exact `run_purge_eligible_at=calendar90(completed_at)`; active runs have neither terminal value. No terminal status returns to `IN_PROGRESS`, and an unknown status or unlisted transition fails before persistence.

An individual order failure never discards other successful orders.

## 6. Extraction attempts, snapshots, and evaluations

### 6.1 Extraction attempt

Every attempted OA read creates minimal `DOIExtractionAttempt` metadata: attempt ID, retained run-work/case admission reference, trigger, timestamps, adapter/schema versions, outcome, reason codes, and whether any OA read began. It contains no staged-order/attempt-owned locator, HTML, screenshot, page copy, customer data, or partially extracted dynamic facts.

### 6.2 Successful whole-order snapshot

Every successful `Run DOI Review`, `Recheck Order`, or disappearance verification appends one immutable `DOIOrderSnapshot`. No prior snapshot is changed.

A snapshot exists only when all are true:

1. exact Order Number was deterministically confirmed;
2. the adapter's versioned complete-order contract proved the entire relevant line universe was captured;
3. every required order field was observed/readable;
4. every captured relevant line contains all required line fields, though a successfully observed value may normalize to `UNKNOWN`;
5. the extraction remained internally coherent for one point in time.

`UNKNOWN` means the source value was successfully observed but could not safely normalize. Missing, unreadable, inaccessible, or unobserved required data is extraction failure, not `UNKNOWN`.

The v0.1.5.3 field mapping is exact: unknown availability emits RC-016, unknown DS state emits RC-017, and unknown ETA emits RC-115. Independent UNKNOWN fields produce exact set union; no field reason may substitute for another. RC-115 blocks only ETA-dependent conclusions or ranking components. It does not guess or prove a date, lead time, availability, DS state, or terminal condition and does not permit stale ETA reuse.

An incomplete/failed extraction creates no snapshot and no evaluation. It appends only the extraction attempt and sets `RECHECK_REQUIRED`. A later snapshot never inherits dynamic facts from a prior snapshot.

Snapshots contain facts only. No disposition, opportunity, recommendation, reason code derived by policy, or calculated KPI belongs in a snapshot.

### 6.3 Line continuity

Cross-snapshot lineage requires a deterministic adapter-provided stable line identity or an exact versioned continuity proof. Row position alone is invalid. If continuity is ambiguous:

- retain current snapshot facts independently;
- emit `LINE_CONTINUITY_UNVERIFIED` in evaluation;
- block only calculations, intervention proof, reversals, or other conclusions that depend on lineage;
- preserve conclusions derivable solely from the current complete snapshot.

### 6.4 Immutable evaluation

Each successful snapshot receives an immutable `DOIEvaluation` linked to:

- snapshot ID and snapshot content hash;
- exact rules-engine version/hash;
- applicable alternate relationship revision and current observation IDs;
- applicable human-recorded contact/decision facts;
- versioned business-calendar reference when WWC timing is calculated.

Re-evaluating an old snapshot under a new rules version appends a new evaluation and never rewrites an old one. The current projection selects the newest accepted evaluation for the desired rules version; historical evaluations remain audit evidence until case purge.

## 7. Deterministic disposition algorithm

For a successful complete snapshot, compute facts and flags first, then one top-level disposition using this precedence:

1. `DOI_EXCLUDED` for a proven hard/reversible closure, `FULL_DS`, or sole payment out-of-scope condition;
2. `DOI_OPPORTUNITY` when any safe, specific opportunity exists, even if an unrelated line/handling/coordination flag requires review;
3. `DOI_MANUAL_REVIEW` when no safe opportunity exists and uncertainty or a required non-routine review prevents a safe monitor conclusion;
4. `DOI_MONITOR` for a valid active case with no current specific opportunity and no blocking review.

The algorithm never lets an unknown fact contaminate an independently supported conclusion. Conversely, `UNKNOWN` blocks universal/negative conclusions such as `FULL_DS`, all-in-stock, no solution, or DEDUPE eligibility when the unknown could change them.

Operational conditions such as `RECHECK_REQUIRED` can exist without a current evaluation and are not top-level DOI dispositions.

## 8. Line facts and value calculations

### 8.1 Availability

- `IN_STOCK`: OA explicitly establishes the captured line/quantity as in stock.
- `DELAYED`: OA explicitly establishes a recognized non-available state or future ETA under the versioned adapter map.
- `UNKNOWN`: a value was observed but could not be safely normalized or was coherently contradictory.

Order-level status, website/catalog stock, warehouse location, ETA alone, or `Warehouse Transfer` never proves line availability. Only explicit OA `IN_STOCK` facts count toward ready value.

### 8.2 Partial quantity

When `0 < available_quantity < active_ordered_quantity`, calculate exact `partial_available_value` if exact pricing permits and emit `PARTIAL_QTY_INTERVENTION_REVIEW`. Do not automatically recommend splitting the partial quantity. The line cannot contribute its full value to `available_to_ship_value`.

### 8.3 Values

Values are calculated only from exact source amounts or exact arithmetic inputs. Missing quantity/value inputs produce `null` plus a reason code, never an estimate.

- `full_order_value`: exact active order merchandise total when supported;
- `ds_value`: exact active DS line value;
- `non_ds_in_stock_value`: exact fully available active non-DS line value;
- `non_ds_delayed_value`: exact active delayed non-DS line value;
- `unknown_value`: exact active value whose availability is `UNKNOWN`;
- `partial_available_value`: exact value of explicitly available partial quantity;
- `available_to_ship_value`: sum of fully split-eligible active non-DS line values explicitly `IN_STOCK`;
- potential values: exact opportunity scenario values, never realized values;
- realized values: authoritative verified intervention values only.

Potential opportunities that address overlapping merchandise are tagged with the same scenario/scope key. A combined potential total is emitted only when all scopes are demonstrably disjoint or an explicit mutually exclusive scenario selection exists; otherwise the combined field is `null` with `POTENTIAL_OVERLAP_UNRESOLVED`. Opportunity-level values remain visible.

## 9. Drop ship, split, geography, and progress rules

### 9.1 DS

- one or more relevant active merchandise lines exist and every one is explicitly DS → `DOI_EXCLUDED` + `FULL_DS`;
- at least one DS and one active non-DS line → `DOI_OPPORTUNITY` + `DS_SEPARATION_REQUIRED`, then continue all non-DS analysis;
- mixed DS is never excluded solely because DS exists.

DS separation is human-performed. It never authorizes Sales Assist to alter OA.

### 9.2 Fulfillment split

At least one active non-DS `IN_STOCK` line plus at least one active non-DS `DELAYED` line in the same complete snapshot produces `FULFILLMENT_SPLIT_CANDIDATE`. There is no minimum dollar or delay-duration threshold.

Ranking is:

1. `available_to_ship_value` descending when known;
2. `full_order_value` descending when known;
3. supported ETA/delay impact;
4. order age/longest delay.

Unknown monetary values sort after known values at the affected rank; they never become zero.

For `DOMESTIC_STANDARD`, emit `HUMAN_DECISION_REQUIRED`; customer contact is not required by geography before a sensible manual split. For `DOMESTIC_SPECIAL_REVIEW`, emit `AK_HI_SHIPPING_REVIEW` and `HUMAN_DECISION_REQUIRED`; customer contact is case-by-case. For `INTERNATIONAL`, emit `INTERNATIONAL_ORDER_REVIEW`, `CUSTOMER_CONTACT_REQUIRED_BEFORE_SPLIT`, and `HUMAN_DECISION_REQUIRED`. With geography `UNKNOWN`, preserve an independently proven split opportunity but block geography-dependent action/contact handling and guess no geography-specific reason. Geography changes handling, not whether the opportunity is calculated.

### 9.3 Progress and payment

An active unshipped order whose complete relevant active non-DS line universe is explicitly all in stock produces `ORDER_PROGRESS_REVIEW` and normally `DOI_MANUAL_REVIEW` unless a separately proven opportunity controls the top-level disposition. The system never infers that an order is stuck or should be released.

Billing, Purchasing, and Distribution Center problem resolution are outside DOI. A payment issue proven to be the sole blocker yields `DOI_EXCLUDED` + `PAYMENT_ISSUE_OUT_OF_SCOPE`. If it coexists with a product-side opportunity, retain the opportunity and add `PAYMENT_ISSUE_PRESENT_OUT_OF_SCOPE`.

## 10. Shipping, cancellation, and source disappearance

- overall status `SHIPPED` → hard close `SHIPPED`;
- overall status full `CANCELED` → hard close `CANCELED`;
- a canceled line on an otherwise active order is excluded from current values/opportunities but retained in prior snapshot history;
- normal partial shipment is not a DOI state; a human split creates a separate resulting order.

Absence from a later manager batch never closes a case. For each previously active TARGET_REP case absent from the selected batch, emit `SOURCE_ABSENT_RECHECK_REQUIRED` and perform one read-only disappearance verification:

- complete proof of shipped/canceled/rep transferred/DEDUPE confirmed → corresponding disposition/closure;
- still active and OA-owned by the configured TARGET_REP/TARGET_REP mapping → keep the same case, retain the absence flag, and evaluate the new complete snapshot;
- incomplete verification → no snapshot/evaluation and `RECHECK_REQUIRED`.

## 11. Alternate-product knowledge and order application

### 11.1 Identity rule and hierarchy

An alternate always has a different ES# from the ordered product. Same ES# is the same catalog product and belongs only to `EXACT_SKU_RECHECK`.

Priority is:

1. same ordered ES# current improvement/recheck;
2. different ES# with exact same MFG#/OE;
3. different ES# with explicit manufacturer cross-reference;
4. different ES# with explicit manufacturer supersession;
5. different ES# functional alternate.

Within a relationship class, current in-stock availability ranks before shorter lead time. Price delta is information, not an eligibility gate.

Every substitution requires human-recorded `CUSTOMER_APPROVED` before manual execution. Functional alternates require a new order/application-specific human compatibility review every time. Cross-reference/supersession candidates require compatibility review unless their durable relationship evidence explicitly proves deterministic applicability.

### 11.2 Durable relationship vs volatile observation

`DOIAlternateRelationship` stores stable product identities, relationship class, evidence/provenance, lifecycle, and revisions. Its lifecycle projection is `ACTIVE`, `SUPERSEDED`, or `INVALIDATED`. Failure to rediscover a relationship does not invalidate it; only explicit contradictory or superseding source evidence creates the corresponding event. Verification provenance is `SYSTEM_VERIFIED` or `HUMAN_VERIFIED`.

Exact-MFG, explicit cross-reference, and explicit supersession relationships may be reused for future matching products. Functional prior knowledge may only be surfaced as a candidate and must be reviewed again for each application.

The Round-2 creation fixtures are exact. `SYN-ALT-003` includes one complete exact-MFG proof plus one fresh current observation and creates exactly one ACTIVE `EXACT_MFG` revision with the fixture provenance and exactly one customer-approval-required alternate opportunity; replay creates no duplicate. `SYN-ALT-004` includes one complete explicit manufacturer cross-reference plus one fresh current observation and creates exactly one ACTIVE `MFG_CROSS_REFERENCE` revision with exact source provenance and exactly one customer-approval-required alternate opportunity; replay creates no duplicate. `SYN-ALT-005` includes one complete explicit manufacturer supersession proof, privacy-minimized fitment/source provenance, and one fresh current observation and creates exactly one ACTIVE `MFG_SUPERSESSION` revision plus exactly one customer-approval-required alternate opportunity; replay creates no duplicate, and this non-functional fixture emits no functional-compatibility-review requirement.

`DOIAlternateObservation` stores a timestamped price/availability/ETA observation and its source/provenance. For a matching future order, one applicable active exact relationship is reused without a duplicate and surfaces exactly one alternate opportunity. With no fresh current observation, that opportunity is exactly `RECHECK_REQUIRED_BEFORE_ACTION`; customer contact and substitution remain blocked. A fresh observation obtained by the explicit current `Recheck Alternate` action for the contemplated contact/substitution advances only that exact opportunity through its governed gates. Freshness is event/context-scoped, not an age-based TTL; an older stored observation never becomes current merely because it is less than 90 days old. Prior functional knowledge instead surfaces exactly one `FUNCTIONAL_COMPATIBILITY_REVIEW_REQUIRED` opportunity and never establishes universal compatibility.

Each delayed active non-DS line has a research state from the machine contract. A failed search is not proof of no alternate. `MANUAL_IDENTIFICATION_REQUIRED` and opportunity-concealing unknowns block `DEDUPE_CANDIDATE`. `Mark No Viable Alternate` is an append-only human decision in Sales Assist only; it never writes an OA note.

## 12. Contact, WWC, and DEDUPE

### 12.1 Contact

DOI v0.1 contact state is human-recorded. It does not send or read Synthetic Message Source messages. Only `CUSTOMER_APPROVED` permits a human to proceed with a substitution; Sales Assist still performs no OA action.

### 12.2 WWC

WWC is a structured, privacy-minimized finding derived from OA notes without retaining note bodies.

- latest qualifying other-rep contact → `WWC_ACTIVE_OTHER_REP`; analysis and values continue, customer work is blocked, and DEDUPE is blocked;
- TARGET_REP contact → `WWC_ACTIVE_SELF`; continuing work is allowed, but suppress new-outreach prompting;
- uncertain author or time → `WWC_AUTHOR_UNCERTAIN` and/or `TIMING_UNCERTAIN` plus human coordination review; never assume expiration.

Contact date is Day 0. Count three full SyntheticCo business dates after it; eligibility begins at `00:00:00` America/New_York on the next SyntheticCo business date. The latest qualifying other-rep contact resets the calculation. `REP_TRANSFERRED` supersedes WWC.

### 12.3 DEDUPE

A complete one-pass analysis with no unresolved/actionable condition may emit `DEDUPE_CANDIDATE` plus `HUMAN_DECISION_REQUIRED`. It is blocked by any DS separation, split, partial quantity review, exact-SKU improvement, alternate candidate/review, unknown that could conceal opportunity, manual identification, active other-rep WWC, or other identified opportunity.

TARGET_REP alone decides whether to add DEDUPE manually in OA. Sales Assist never writes the note. The DOI-local decision is recorded only as a closed `DOIHumanFactEvent`: `DEDUPE_APPROVED` or `DEDUPE_REJECTED`. The deterministic `dedupe_review_id` is derived from case ID, candidate DEDUPE occurrence ID, and candidate evaluation ID/content hash before the candidate event is hashed; that event then embeds the review ID, so its own ID/hash is never a cyclic review-ID input. The fact also binds the accepted candidate event/evaluation, structured human-verification reference, actor, decision instant, and evidence fingerprint defined by `provenance_state_contract.md`. TR-061/TR-062 atomically append or reuse that exact human fact and a `DOIDedupeStateEvent` that references the fact ID and full-event hash; a failure rolls back both. The only same-review correction is an exact predecessor-bound `DEDUPE_APPROVED -> DEDUPE_REJECTED` correction before OA verification. Every other conflicting same-review decision fails with RC-112. An OA note, note observation, lifecycle event, evaluation inference, or free text can never construct or imply the human decision.

Only a later complete read-only OA recheck that independently verifies the note may append `OA_NOTE_SYSTEM_VERIFIED`, yield `DEDUPE_CONFIRMED`, and close reversibly. Approval alone remains `HUMAN_APPROVED_AWAITING_OA_VERIFICATION`; rejection keeps the case active. An all-in-stock order merely progressing normally is `DOI_MONITOR` + `NO_ACTION_REQUIRED`, not DEDUPE.

`Recheck DEDUPE Order` is explicit and user-triggered. New source-grounded eligibility reopens the same retained case.

## 13. Opportunity and intervention separation

`DOIOpportunity` means a specific potentially useful action is identified. It is not evidence that anyone acted.

`DOIIntervention` exists only after actual action is verified. Planning, deciding, customer approval, clicking a UI intention control, detecting an unexplained change, or recording an estimate creates no intervention.

Normal flow:

`opportunity → human acts manually in OA → Recheck Order → deterministic proof → intervention`.

If a change is observed but action/lineage/resulting-order proof is insufficient, emit `INTERVENTION_VERIFICATION_REQUIRED`; create no intervention and count zero realized credit. The first complete structured human proof that exactly attests the action creates exactly one intervention plus one `HUMAN_VERIFIED` action-verification event bound to its evidence fingerprint. Byte-identical replay reuses that result with zero new credit-bearing effect; conflicting same-key material fails closed. Accepted provenance is `SYSTEM_VERIFIED` or `HUMAN_VERIFIED`.

V0.1 intervention kinds are limited to actions already defined by this specification:

- `FULFILLMENT_SPLIT`;
- `PRODUCT_SUBSTITUTION`;
- `DS_SEPARATION`.

Other findings may resolve, be dismissed, or remain monitor/review states without inventing an intervention kind. Split/substitution carry credit rules; DS separation has no realized-credit value unless a later independently defined credited intervention occurs.

## 14. Verification, resulting orders, reversal, and KPI

### 14.1 Independent verification dimensions

Action verification and value verification are independent. An intervention is created only when action verification is `VERIFIED`, with provenance `SYSTEM_VERIFIED` or `HUMAN_VERIFIED`. A stable proof-bound action occurrence ID identifies the logical action independently of proof time; scope/time/target/link/quantity are immutable material and conflicting reuse fails closed. Exact business `action_occurred_at` may be null when the action is otherwise proved; the proof/attestation occurrence time remains required but may not substitute. On a credit-bearing intervention, null action time emits RC-099 and creates no retained monetary row. Non-credit `DS_SEPARATION` does not receive RC-099 merely because no monetary attribution instant is required. Monetary status may independently remain `UNVERIFIED`; with exact action date/currency/registry it contributes count one and zero money until value proof.

Human value verification requires an exact known amount and currency; estimates are rejected. While the detailed case remains retained, if later deterministic system evidence conflicts with a human value, the system value becomes authoritative for the current projection while both immutable evidence events remain in audit history.

### 14.2 Credit scopes

- split: realized value is the exact linked resulting-order value, and resulting order-level Sales Rep is authoritative. With an exact accepted `AUTO_LINKED|HUMAN_CONFIRMED` child link, missing/different/ambiguous resulting-order-level TARGET_REP rep adds `RC-074 SPLIT_CREDIT_REP_UNVERIFIED`; the exact link remains unchanged, value stays `UNVERIFIED`, and realized split credit is zero;
- substitution: realized value is the exact final replacement-line value, and line-level Sales Rep is authoritative. Missing/different/ambiguous replacement line-level TARGET_REP rep adds `RC-075 SWAP_CREDIT_REP_UNVERIFIED`; parent order-level rep never substitutes, the replacement-line binding remains unchanged, value stays `UNVERIFIED`, and realized swap credit is zero;
- RC-074 and RC-075 are mutually exclusive TR-106 modifiers. Each unions with the independently derived date/currency base set. Both at once, a code on the wrong intervention type, or a contradictory branch is RC-081 before TR-106 and creates no row or state append.

Resulting-order linkage hierarchy is:

1. explicit OA relationship;
2. exact moved-line/quantity continuity plus transient same-customer/timing validation, retaining only the proof classification and no customer identity/hash;
3. exact human confirmation.

Exact-link states are `AUTO_LINKED`, `HUMAN_CONFIRMED`, or `AMBIGUOUS`; an exact link always has a non-null child Order Number and natural key. `NOT_FOUND` and candidate `AMBIGUOUS` are separate `DOIResultingOrderLinkSearch` states and cannot invent a child/link/mapping. Search ambiguity or exact-link conflict emits `RESULTING_ORDER_LINK_REVIEW` for its own cause and blocks split value verification.

### 14.3 Reversals

Before purge, verified cancellation/removal of previously credited merchandise appends reversal evidence. Reduce accepted events strictly by stream sequence. The authoritative original-value chain prefers accepted SYSTEM_VERIFIED over HUMAN_VERIFIED; within one provenance only a valid explicit correction of the current authoritative event replaces it. Apply each reversal correction/void chain to its exact predecessor so corrected/voided predecessors remain history but do not contribute twice.

`reversed_value` is the exact sum of active reversals sharing the authoritative original's identical currency-and-ISO-registry-version/scale binding, and `net_realized_value = authoritative_original_realized_value - reversed_value`. Missing original, currency or registry/scale mismatch, negative/above-original reversal, broken predecessor, or conflicting natural evidence fails closed, preserves the last valid projection, and applies zero disputed delta. Credit status is:

- `VERIFIED`: reversed value = 0;
- `PARTIALLY_REVERSED`: 0 < reversed value < original;
- `REVERSED`: reversed value = original.

The projection preserves `original_realized_value`, `reversed_value`, and `net_realized_value`. Valid corrections/voids may move among all three states; reversal state is not monotonic. Reopening never creates a second credit event for merchandise already represented by a retained credit-scope key.

### 14.4 Aggregates

Headline: `Net Realized DOI Credit = finalized non-identifying net credit from purged cases + Σ current net_realized_value across retained unique, verified credit scopes`.

Supporting analytics:

- `Gross Verified Credit = finalized non-identifying gross credit from purged cases + Σ authoritative original_realized_value for retained cases`;
- `Reversed Credit = finalized non-identifying reversed credit from purged cases + Σ authoritative reversed_value for retained cases`.

Unverified, ambiguous, estimated, mixed-currency, or duplicate-scope money contributes zero. Before purge, aggregates are recomputed from the retained authoritative append-only ledger rather than incremented from case reopening. Persisted source-of-truth buckets are daily `America/New_York` leaves keyed by schema, local date, ISO currency/registry, intervention type, and the provenance of the first accepted action event; later compatible cross-provenance corroboration never moves the bucket. A verified action with null exact business action time creates no retained monetary row. Otherwise credit is attributed to the exact verified action's local date; 23/24/25-hour UTC spans are legal, longer-period/ALL views are rollups only, and later value/correction/reversal evidence updates that same bucket. At purge, the exact contribution moves retained→finalized atomically before the ledger is deleted; totals do not change, no per-case join survives, and later per-order correction cannot alter it.

## 15. Lifecycle and user actions

Legal transitions and exact preconditions are in `DOI_STATE_TRANSITION_MATRIX_v0.1.5.md`. Impossible transitions against a retained graph fail closed and append a structured rejection reason. A request targeting an identity absent after purge is rejected transiently with `CASE_IDENTITY_NOT_RETAINED` and leaves no order-specific rejection record.

Required user actions are:

- `Run DOI Review`: confirm tab, import/read/evaluate; never mutate OA;
- `Recheck Order`: read one exact order, append attempt and on success snapshot/evaluation;
- `Recheck Alternate`: read current alternate facts and append an observation;
- `Verify Action`: exact human fallback attestation of an action that occurred;
- `Verify Value`: exact human fallback monetary attestation; estimates prohibited;
- `Mark No Viable Alternate`: append a human line-level research decision;
- `Recheck DEDUPE Order`: read/re-evaluate an intentionally selected DEDUPE case;
- `Record Contact State`: append a structured human contact/approval state;
- `Confirm Resulting Order Link`: append an exact human link confirmation;
- `Mark Human Out of Scope`: append a reversible terminal event with `HUMAN_OUT_OF_SCOPE_CLOSED`;
- `Recheck Source-Absent Case`: the one read-only disappearance verification initiated by a run.

No action above performs customer communication or OA mutation.

## 16. Historical and synthetic acceptance policy

### 16.1 Immutable 213-case evidence baseline

The original corpus remains an immutable, privacy-minimized evidence baseline with this exact accounting:

- 213 unique exact-order cases;
- 0 duplicate Order Numbers;
- 0 `EXECUTABLE_HISTORICAL` cases;
- 59 `HISTORICAL_ASSERTION_HUMAN_REVIEW` cases;
- 154 `SUPPORTING_ONLY_NOT_REPLAYABLE` cases;
- 0 frozen end-to-end deterministic historical expected-result oracles.

The historical execution denominator is therefore 0. The complete-whole-order requirement must not be weakened to promote any of the 213 records. A zero historical execution denominator is not itself a release failure while the complete versioned remediation-candidate contract is covered by deterministic release-blocking synthetic fixtures.

All 213 cases are nevertheless mandatory release evidence. `HISTORICAL_DOI_ASSERTION_MANIFEST_v0.1.jsonl` must contain exactly one entry per case in deterministic corpus order. Each entry must preserve a case identifier, historical layer, immutable source references, independently supported positive source facts/assertions, independently supported historical research findings, supported human-review requirements, unsupported/missing facts, replayability blockers, represented rule-family/category annotations, assertion checkability, and an explicit prohibition against treating the record as a complete whole-order oracle.

Assertions may derive only from independently supported source facts or research results. A historical label or final classification may not become an input, hidden target, or substitute for missing engine facts. Incomplete data must not yield negative whole-order assertions such as no split, no alternate, full DS, all in stock, no unknown line, DEDUPE eligibility, or no other opportunity. A source-supported negative research finding such as `NO_VERIFIED_ALTERNATE_FOUND` remains limited to the exact researched scope and never proves a whole-order no-opportunity result.

### 16.2 Permitted historical validation and release gates

At its supported scope, historical evidence may validate ingestion parsing, provenance, exact-order deduplication, privacy minimization, multi-SKU occurrence, recorded DS patterns, split/progress-review patterns, exact-SKU findings, different-ES exact-MFG findings, functional-alternate research, manual identification, scoped no-verified-alternate research, pending-cancellation observations, overlap patterns, human-review preservation, and real-world rule-family coverage. It validates only the preserved assertion, never a complete `DOIEvaluation` unless the complete snapshot and independently derived expected result are present.

An offline release must fail unless:

1. all 213 records are accounted for exactly once and immutable source bytes/hashes are unchanged;
2. the layer counts reconcile to 0 executable, 59 human-review, and 154 supporting-only records;
3. the assertion manifest contains exactly 213 valid source-linked entries;
4. every source reference validates and privacy lint passes;
5. no unsupported fact or incomplete-source negative is promoted to an assertion;
6. no historical classification/expected output leaks into executable inputs or synthetic targets;
7. no non-replayable record enters the executable denominator;
8. every one of the 59 human-review and 154 supporting-only records remains represented;
9. historical coverage totals reconcile across the manifest and coverage artifacts; and
10. deterministic synthetic coverage remains release-blocking wherever executable history is absent.

Every synthetic rule family must identify related real-history evidence, cited case/source references, the history's executable/assertion/supporting layer, and whether the fictional fixture was structurally inspired by that evidence. Synthetic fixtures remain fictional and privacy-safe; they must copy neither customer/order identity nor a historical expected target. Their expected results are independently authored from this remediation-candidate contract.

### 16.3 Future executable historical layer

During separately authorized supervised shadow mode, new privacy-minimized complete whole-order captures may become candidates for an executable historical regression layer. Each candidate must independently preserve proof of the complete relevant line set, required order- and line-level facts, exact source/extractor/schema versions, privacy minimization, immutable source-fact binding, and target-leakage controls. Its expected result must be derived independently under an exact frozen rules version.

Future evidence must not mutate, merge with, or retroactively upgrade the original 213 cases. The original corpus remains a separate immutable assertion/supporting baseline even after a future executable corpus exists.

## 17. Deferred pre-production dependencies, not business-rule blockers

The following remain intentionally deferred to separately authorized controlled reconnaissance or configuration:

1. exact OA read-only selectors/page contracts and safe navigation allowlist;
2. deterministic whole-order completeness proof exposed by OA;
3. exact OA availability/status strings mapped to `IN_STOCK`, `DELAYED`, or observed `UNKNOWN`;
4. stable OA order/line identities and exact line-continuity evidence;
5. exact OA rep fields/values for current ownership and split/swap credit proof;
6. privacy-safe WWC author/time and DEDUPE-note extraction without note-body retention;
7. exact payment-only, cancellation, shipment, DS, quantity, price, ETA, and geography source fields;
8. explicit split/resulting-order relationship evidence and transient linkage checks;
9. alternate ES#/MFG#/OE, availability, price, ETA, cross-reference, and supersession evidence fields;
10. connector support for source revision/change-during-import proof;
11. authoritative synthetic business holiday-calendar source and maintenance process;
12. exact ETA-improvement presentation and GUI layout.

Each unknown is an adapter/configuration detail with a defined fail-closed contract. None authorizes guessing, stale inheritance, or live access in this task.

## 18. Freeze-candidate determination

The authoritative purge-finality amendment resolves the prior material policy contradiction by making purge the explicit end of all case-linked guarantees. Within-window reopening, correction, reversal, supersession, and duplicate-credit prevention remain mandatory; after purge, aggregate history is final and a later same-number input creates an unlinked new case. No tombstone, hash, or reconstructable identity is retained.

The 213-case corpus is now mandatory first-class release evidence without falsely promoting any record into complete executable history. Functional fitment remains safely routed to mandatory human review; additional intervention/KPI types are excluded rather than invented. The OA and calendar items above are extraction/configuration dependencies and do not independently block offline implementation against fixtures. This contract authorizes no live OA reconnaissance or production implementation.

The later independent audits superseded that earlier self-assessment. Section 19 carries forward all validated earlier remediation and adds the two narrow Round-4 corrections required after the v0.1.4 independent freeze audit failed: complete reason ownership/oracle parity and exact deletion for every source-import attempt outcome.

DOI_V0.1_FREEZE_CANDIDATE = SUPERSEDED_BY_INDEPENDENT_AUDIT_FAIL

## 19. Independent-audit remediation contract v0.1.5

This section carries forward every validated Round-1 through Round-3 remediation, including explicit prior-closure binding and the synthetic-identity firewall, then resolves the two Round-4 blockers: complete reason-code external ownership/oracle parity and exact every-outcome source-import-attempt retention/deletion. The v0.1.5.3 erratum adds only the closed ETA normalization reason and directly dependent bindings/oracles. The v0.1.5.4 erratum adds only the missing closed HumanFact usage-role domain, fact/usage applicability, role scope/nullability, canonical binding rules, and directly dependent rules/vector/schema/test bindings. It does not reopen the validated historical corpus, synthetic/historical separation, complete-whole-order gate, privacy denylist, purge-finality business decision, or permanent OA read-only invariant. The governing modules `source_retention_contract.md`, `provenance_state_contract.md`, `opportunity_kpi_contract.md`, `DOI_LIFECYCLE_EVENT_PAYLOAD_REGISTRY_v0.1.5.md`, `DOI_OA_CAPABILITY_POLICY_v0.1.5.md`, `DOI_REASON_OWNERSHIP_MATRIX_v0.1.5.3.md`, and the v0.1.5.4 HumanFact usage registry/schema artifacts are incorporated into this specification, machine contract, persistence model, transitions, tests, and handoff. Their exact schemas/algorithms replace any looser earlier clause.

### 19.1 Source import, reusable batch identity, and run outcome

Every explicit `Run DOI Review` creates exactly one immutable `DOIRun` and source-import attempt ordinal 1 before acquisition. It may append one or more sequential attempts while the run remains `IN_PROGRESS`; each uses an opaque nonderived ID, the next stable positive ordinal, and attempt-owned command token. Exact same ordinal/token/bytes replays; gaps, concurrency, changed duplicates, or post-run-terminal append fail before persistence. The run v2 event/projection retains only `source_import_attempt_count`, never an attempt ID or manifest. Attempts are distinct from `DOIExtractionAttempt` and use the closed outcomes `SUCCEEDED|SCHEMA_REJECTED|SOURCE_CHANGED|INACCESSIBLE_OR_UNREADABLE|BATCH_INTEGRITY_REJECTED|ABORTED_PRE_OA`. Abort is intermediate only, uses `SOURCE_IMPORT_ABORTED` with empty reasons, leaves the run in progress, and requires a later terminalizing attempt. Every failed outcome including RC-091 stores null coherent fingerprint/batch, emits RC-090 plus its exact specific reason, and retains no candidate batch digest/preimage/fingerprint/undocumented reference.

A reusable `DOISourceBatch` is created only from one coherent validated read. Its identity binds spreadsheet ID, exact selected tab identity, schema-mapping version, normalized TARGET_REP-only row-content hash, and privacy-minimized assignee-conflict fingerprint. The conflict fingerprint contains only the sorted intersection between valid TARGET_REP Order Numbers and valid Order Numbers simultaneously observed with a normalized assignee other than TARGET_REP. Other-rep names, unrelated numbers, rows, and metadata are excluded. Scan-specific totals and physical row locators live on the import attempt/run records, not the reusable batch.

Per-run staged records bind to the exact successful attempt and are part of its operational graph. Before `CASE_CREATED` or `SOURCE_PRESENT`, persist only the closed case-owned `DOICaseSourceAdmissionProofV1` and bind lifecycle through that proof; it contains no run/attempt/row/tab/actor identity or staged-record pointer. A final failure from the closed v0.1.5 acquisition/schema/change/integrity union is `FAILED`, creates no executable batch, and causes zero OA reads. A coherent run with any individual blocked/exceptioned order is `COMPLETED_WITH_EXCEPTIONS`, even when every in-scope order is individually blocked and zero evaluations succeed. `COMPLETED` permits no exception.

### 19.2 Evaluation provenance and immutable state histories

Every evaluation binds exact snapshot ID/content hash, rules version/content hash, reason-registry version/content hash, applicable calendar version/content hash, exact relationship revision IDs/content hashes, current Action-Context-bound observation IDs/content hashes, human-fact event IDs/content hashes, evaluation time, canonical input hash, and canonical output hash. An unavailable referenced revision or hash fails closed; no substitute evaluation is legal.

New evaluations under this erratum bind `synthetic.doi.rules/v0.1.5.4` / `df48446467a81eec9970b22649bf5d86cb5dc09e0ecaad291839774523288ad0`, unchanged reason registry `0.1.5.3` / `38eba58f78950c320b9b4e3ece167cc050cae6c11ee0978b98749f3247c2ec86`, unchanged normalization contract `doi-normalization-contract/v0.1.5.3`, and HumanFact usage registry `doi-human-fact-usage-kind/v1` / `da0612598dcd2b8300d9459af29e192cbf0a3413802cf548fc618713d4721764`. The exact canonical rules material is published in `DOI_RULES_BUNDLE_v0.1.5.4.json` and bound by `DOI_AUTHORITY_VERSION_MANIFEST_v0.1.5.4.json`. A stale v0.1.5.3 rules binding, unavailable or unknown version, or mismatched digest fails before append with no substitute; prior evaluations remain reproducible under their old bindings.

Reusable relationship knowledge uses stable `DOIAlternateRelationship` identity plus immutable monotonically numbered `DOIAlternateRelationshipRevision` records. Creation, evidence change, supersession, and invalidation append revisions/events; no revision is overwritten. Evaluations remain reproducible after later relationship change.

Append-only typed histories govern resulting-order links, contact state, DEDUPE state, attention/manual-review conditions, WWC projection, Action Context, intervention action/value/correction/reversal, and relationship state. Source facts, human facts, evaluation outputs, and lifecycle events remain separate entity classes and cannot overwrite one another.

`DOIOrderLifecycleEvent` uses only the closed `doi-order-lifecycle-event/v2` envelope, 56-kind discriminated union, exact payload/null/absent partitions, source bindings, projection hashes, canonical domains, and replay reducers in `DOI_LIFECYCLE_EVENT_PAYLOAD_REGISTRY_v0.1.5.md`. Fifty-four kinds use the append-only core case stream; the observation/link record kinds each use a separate target-owned one-event volatile stream, copy the locked core revision/hash without changing it, and delete with the target. A case-linked accepted typed fact is referenced by exact ID, schema, and full-event hash; its body is never copied into the lifecycle wrapper. The typed event, thin wrapper, projection, and registered subordinate KPI/mapping effect commit atomically or not at all. Unknown kinds/versions, missing or extra fields, wrong null partitions, illegal aliases, or incorrect payload/natural/projection/full hashes fail before append with RC-113; stream faults remain RC-111, collisions RC-103, and unlisted state edges RC-081. Core replay is by sequence and reproduces every stored intermediate projection hash; each live volatile stream independently reproduces the unchanged locked core hash. Purge/deletion success is absence: no `CASE_PURGED`, lifecycle receipt, hash, or tombstone survives.

`HumanFactKind` includes the constructible closed pairs `DEDUPE_APPROVED/DEDUPE_APPROVED/DEDUPE_DECISION_FACT(APPROVED)` and `DEDUPE_REJECTED/DEDUPE_REJECTED/DEDUPE_DECISION_FACT(REJECTED)`. Distinct `HumanFactUsageKind` is exactly `COMPATIBILITY | RESEARCH_STATE | ORDER_PROGRESS | COORDINATION | OUT_OF_SCOPE | ACTION_READINESS` in that canonical member order under `doi-human-fact-usage-kind/v1`. The legal fact/usage relation is: compatibility to COMPATIBILITY/RESEARCH_STATE/ACTION_READINESS; no-viable-alternate to RESEARCH_STATE; normal-progress to ORDER_PROGRESS; coordination to COORDINATION; out-of-scope to OUT_OF_SCOPE; DEDUPE approved/rejected to no evaluation-binding role. Exact role scopes/nullability, natural key `(human_fact_event_id,usage_kind)`, complete-binding JCS-byte order, duplicate rejection, correction behavior, and RC-105/106/112/111/103 routes are incorporated from `provenance_state_contract.md` sections 2.1–2.4. Attention uses only `doi-attention-event/v2` and `doi-attention-cause-key/v2`: SET binds one complete immutable cause group and null resolver group; CLEAR copies the exact active SET cause/key, names that SET, and binds a separate complete resolution group and resolution time/reason. Resolver fields never enter or change the cause key. TR-093 accepts exactly system-link RC-070, human-link RC-071, or complete negative-search RC-073 resolution; TR-095 accepts RC-053/RC-054 for the corresponding active partitions and null only for the registered NOT_APPLICABLE/EXPIRED branches.

### 19.3 Action Context

`DOIActionContext` binds one explicit human decision/action-preparation attempt to exactly one retained case, evaluation, opportunity, closed context kind, and creation time. Fresh alternate observations are current for action only through an explicit immutable context-observation link. A later attempt creates a new context. Context creation performs no OA action and grants no mutation authority. Observation/link targets and their volatile lifecycle wrappers delete at their earlier observation/case deadline; contexts and all remaining case detail delete with case purge. Reusable relationships may survive only after complete de-linking.

### 19.4 Opportunity credit scope and scenario overlap

Every opportunity contains immutable `credit_scope`: a canonical ordered set of exact snapshot-line components with exact applicable quantity and registered scope role. Scope derives only from the immutable snapshot. Row position and unverified continuity are illegal scope inputs. If exact scope cannot be established, credit-bearing potential is unavailable.

`scenario_overlap_key` is derived candidate-by-candidate only after building the complete overlap graph for one evaluation+basis and finding the connected component containing that candidate's exact scope. The sole hash input is the canonical `doi-scenario-overlap-v1` object containing the component's `scenario_basis` and conservative maximum-quantity `group_credit_scope`; evaluation ID, opportunity type, and individual candidate scope hashes/preimages are excluded. Disconnected components in one evaluation+basis receive different keys, while transitive overlap receives one key. Each distinct option has `scenario_option_id`. Same-order opportunities are not presumed overlapping, but at most one option from an actual overlap component may contribute to a selected potential scenario. Missing/ambiguous/partial graph input fails closed and unresolved overlap keeps the options visible with combined potential unavailable.

### 19.5 Evidence identity and idempotency

System-verifiable actions, values, reversals, corrections, and link evidence use RFC 8785 canonical payloads and SHA-256 fingerprints binding retained case, event type, immutable evidence/snapshot/source revision, exact relationship/link, quantities/values, currency, and provenance as applicable. Exact fingerprint plus identical payload is idempotent. The same natural evidence key with contradictory content fails closed; an apparent fingerprint collision with different canonical bytes is a fatal integrity failure. Resulting-order links additionally use the retained natural key `(parent_case_id, relationship_type, exact_child_order_number)` and a separate moved-line/quantity content fingerprint. Duplicate reversal evidence never creates a second reversal. All case-derived evidence fingerprints are deleted at case purge.

### 19.6 Daily multicurrency KPI contract

The source-of-truth monetary grain is `LOCAL_CALENDAR_DAY` in `America/New_York`. A durable non-identifying daily bucket key binds KPI schema version, local date, ISO-4217 currency, and metric/contribution class. Its `[period_start, period_end)` UTC bounds are the exact local-midnight bounds and may span 23, 24, or 25 hours. Weekly, monthly, quarterly, and yearly views are rollups only.

A verified credit-bearing intervention with an exact business action instant is attributed to that action's local date; proof time cannot substitute. TR-106 first derives an exact date/currency base set: exact-date valid or absent currency `{RC-063}`; exact-date invalid currency `{RC-063,RC-094}`; null-date valid or absent `{RC-063,RC-099}`; null-date invalid `{RC-063,RC-094,RC-099}`. It then unions at most one rep-proof modifier: RC-074 for a split with exact accepted child link and missing/different/ambiguous resulting-order-level TARGET_REP rep, or RC-075 for a substitution with missing/different/ambiguous replacement line-level TARGET_REP rep. Verified applicable TARGET_REP rep adds neither. Thus exact-date/valid blocked split and swap are exactly `{RC-063,RC-074}` and `{RC-063,RC-075}`; each preserves one verified intervention and its exact link/line binding, leaves value `UNVERIFIED`, creates one count-1 zero-money row, and realizes zero. `DS_SEPARATION` is `NOT_APPLICABLE`, requires null monetary/currency fields, creates no retained row, and emits none of RC-063, RC-074, RC-075, or RC-099 merely because it needs no monetary attribution instant. Both rep modifiers, wrong intervention type, or a contradictory branch is RC-081 before TR-106. A merely absent pre-value currency is not RC-094; a later exact TR-107 value may create the first row only with a valid immutable binding.

Later exact value verification, correction, and reversal update the retained case-linked contribution for that original attribution bucket. Like currency-and-registry bindings aggregate; mixed bindings remain segmented, no FX/rescale is inferred, and a combined headline is unavailable unless every contribution shares both. At purge the case's final deduplicated contribution is atomically finalized into the corresponding non-identifying daily/currency buckets while every case-linked contribution and join key is deleted. Retrying after successful purge finds no retained case and cannot change the aggregate.

### 19.7 Retention for observations, failed imports, and no-case rejections

All 90-day rules use the exact local-calendar algorithm in section 3.2, including spring-gap and fall-overlap resolution. Case-linked observation/context-link targets and their target-owned volatile lifecycle wrappers delete atomically at `min(observation_nominal_expiry, linked_case.purge_eligible_at)`; the core case stream never referenced them, and no direct target/index/receipt survives. Only a preexisting sealed observation ID/hash embedded in an immutable evaluation/opportunity may remain inside that retained case graph, unusable for reconstruction/freshness and deleted at case purge. Every source-import attempt outcome—success, each registered failure, and intermediate abort—receives the same immutable `source_import_attempt_purge_eligible_at=calendar90(run.completed_at)` only after its associated run becomes terminal; a nonterminal run assigns no deadline. TR-114 atomically removes each due attempt projection/event graph, attempt/run/source/tab/actor/time/failure/fingerprint/revision/row identity, all attempt-owned staged/rejected detail, logs/caches/temp exports/files/exceptions/indexes, batch/reference edges, and the transient purge event itself. A staged record is never case-retained: `CASE_CREATED`/`SOURCE_PRESENT` bind only `DOICaseSourceAdmissionProofV1`, with no run/attempt/row/tab/actor identity. Run identity deletes when its deadline is due and no explicit non-due retained owner remains; an owner prevents premature deletion and final-owner deletion removes every reverse lookup atomically. Reusing a batch never extends any deadline. Only closed `DOISourceImportAggregateV2` monthly outcome counts survive; exact/reconstructable identities and drill-through keys do not.

### 19.8 Complete legal-transition requirement

Every mutable projection and every immutable creation/appending action named by this specification must have a registered legal transition with deterministic from-state, guard/event, resulting projection, reason/event codes, illegal behavior, lifecycle serialization route, and synthetic oracle. This includes initial relationship and resulting-link creation; result-link-review and human-coordination attention add/clear; relationship revision; contact and DEDUPE initialization; Action Context; source-import attempt; no-case rejection retention; source-batch final-reference release; KPI contribution/finalization; and all existing case/intervention/WWC paths. Malformed lifecycle serialization is a rejected attempt under RC-113 and therefore does not create an extra transition. Counts are derived from the complete registries and are not quotas.

### 19.9 Round-3 prior-closure binding and synthetic identity firewall

`PriorClosureRetentionBindingV1` is a closed, versioned, immutable value embedded in both `CaseReopenPayloadV2` and `PURGE_CANCELED`. It contains the exact prior closure event ID, closed closure kind, hard/reversible classification, verified closure instant, retention-policy ID/version, literal `America/New_York` timezone, tzdb version, local-calendar rule ID, active purge deadline, prior closure projection revision/hash, and the registry-required immutable closure source/evidence binding. All timestamps and hashes use the existing canonical timestamp/JCS/SHA-256 contract; no extra or inferred field is legal.

Before either event appends, the validator resolves the named retained closure event and locked pre-event projection, copies the complete tuple byte-for-byte, verifies every member independently, and requires the active prior deadline and `canceled_purge_eligible_at` to equal `prior_purge_eligible_at`. `CaseReopenPayloadV2` additionally binds the exact reopen proof/source, reason and instant, prior deadline, same retained case identity, next case revision/projection, and mandatory purge-cancellation effect under its closed required/null/absent partition. `PURGE_CANCELED` binds the exact cancellation cause/reopen event, resolution source, resulting cleared deadline state, and resulting case revision/projection. A projection hash alone is never a substitute for the explicit tuple. Missing, extra, hash-only, inferred, stale, or non-byte-equal input is RC-113, appends neither event, allocates no revision, and leaves the prior closure/deadline/projection byte-identical. Exact replay reproduces the original event and projection bytes.

The lifecycle registry is the canonical byte authority for these schemas, content domains, event-envelope hashes, fixed vectors, rollback and replay tests. `SYN-LIFE-PAYLOAD-004/005/010` table-drive the valid reopen/cancellation path plus closure-kind, classification, verified-instant, policy ID/version, timezone, tzdb, calendar-rule, deadline, projection revision/hash, missing-explicit-tuple, and rollback/replay variants.

Every executable synthetic case identity and every harness-level synthetic order/customer/product identity belongs to the reserved `SYN-DOI-` namespace before fixture execution or canonical serialization. The lifecycle V1/V2 case identities are exactly `SYN-DOI-CASE-0001` and `SYN-DOI-CASE-0002`; the new V3 reopen/cancellation serialization vector uses exactly `SYN-DOI-CASE-0003`. All dependent canonical bytes, stream/natural/payload/projection/full-event hashes, replay outputs, and expected values are regenerated from those literals. When a governed production-shaped field has a stricter lexical type, the harness may use only an exact registered one-way fixture mapping: V1 maps `SYN-DOI-ORDER-0001` to the schema-valid non-production-looking decimal sentinel `"1"`, proves that sentinel absent from the complete historical/source denyset, and serializes only the generated field value. Arbitrary/unregistered numeric values remain forbidden. A generic `case-*`, production-looking numeric ID, historical identifier, lowercase/alias prefix, or unprefixed harness semantic identity fails the package-wide synthetic identity firewall before execution, reducer/adapter creation, network/navigation, or persistence. Documentation-only historical evidence remains isolated and never enters executable fixture bytes. `SYN-LIFE-PAYLOAD-002/003/004/005/010`, `SYN-OA-RO-009`, and `SYN-OA-RO-008` enforce this boundary over source, dependency, generated, and built artifacts.

### 19.10 Complete reason ownership and oracle parity

`DOI_REASON_OWNERSHIP_MATRIX_v0.1.5.3.md` is the machine-checkable external-ownership authority. Each of the 115 registered reasons records its exact canonical label/version, transition owners where applicable, deterministic asserting oracle, rule/service owner, emitted/asserted mode, and governing artifact references. A registry definition alone is not ownership. Release requires 115/115 external ownership, every emitted/referenced code present in `DOI_REASON_CODE_REGISTRY_v0.1.5.3.md`, every registry code asserted by at least one deterministic oracle, no orphan/undefined code, no unversioned alias, and unknown code/version rejection before persistence.

TR-106's exact exhaustive date/currency base sets and mutually exclusive RC-074 and RC-075 modifiers are identical across the opportunity/KPI contract, technical and machine contracts, provenance/state contract, persistence model, transition matrix/traceability, tests, handoff, registry, and ownership matrix. `SYN-INT-017/018` and `SYN-REASON-OWN-001..004/010` prove both positive rep-proof failures, exact state/value/link results, cross-negatives, unrelated branches, contradictory fail-closed behavior, and byte-normalized cross-document parity. The structural OA build boundary owns RC-082 through `SYN-OA-RO-003`, `SYN-OA-CAP-002`, and the positive `SYN-REASON-OWN-005` branch; `SYN-REASON-OWN-006` is its negative/non-applicable control. Forbidden `click`/equivalent write capability fails before runtime/package promotion. The runtime user/API dispatch boundary owns RC-083 through `SYN-OA-RO-001/005` and `SYN-REASON-OWN-006..008`: deliberate `POST|PUT|PATCH|DELETE`, GraphQL mutation/write-RPC, generic mutation-capable action/click request, background-poll request, and unallowlisted side-effectful read each fail before dispatch. The two codes are mutually non-substitutable and all safety rejections have zero OA mutation, DOI append, persistence, and dispatched network effect beyond the local blocked-probe observation.

### 19.11 Exact retention and deletion for every source-import attempt

Every run has one or more sequential source-import attempts with opaque nonderived IDs, unique `(run_id,attempt_ordinal)` and attempt-owned command tokens. `DOIRunEventV2`/run projection retain only `source_import_attempt_count`, never an attempt ID/list/token/hash. The closed outcomes are `SUCCEEDED|SCHEMA_REJECTED|SOURCE_CHANGED|INACCESSIBLE_OR_UNREADABLE|BATCH_INTEGRITY_REJECTED|ABORTED_PRE_OA`; abort is an intermediate empty-reason `SOURCE_IMPORT_ABORTED` while the run stays `IN_PROGRESS`, and a later attempt must terminalize the run. When the run terminalizes, all attempts atomically receive the byte-identical `source_import_attempt_purge_eligible_at=calendar90(run.completed_at)` under the existing New York wall-time/DST/tzdb policy; before run terminal, every attempt/run deadline is null.

Staged records and source-row locators remain attempt-owned and always delete under TR-114. Before `CASE_CREATED`/`SOURCE_PRESENT`, TR-007/TR-008 create the closed `DOICaseSourceAdmissionProofV1` plus case source binding/reference. The proof contains only schema/ID, case ID, canonical Order Number, TARGET_REP selection, batch ID, case-source-binding ID, admission time, and content hash. It contains no run/attempt/ordinal/token/row/tab/spreadsheet/actor identity and cannot reconstruct the attempt; lifecycle replay remains exact after attempt deletion. A retained `DOIRunOrderWorkItem`/extraction/snapshot/evaluation chain may keep its governed run ID, source-batch ID, and case admission proof while its `RUN_WORK_GRAPH` owner remains, but must contain zero source-import-attempt ID, staged-order ID, TARGET_REP SourceRef, attempt ordinal/token, or other attempt/source-row locator.

Every lawful graph retaining run identity owns one `doi-run-identity-reference/v1` row. TR-114 locks all attempt/run/batch/reference/aggregate/child stores, validates the due guard, constructs the exact transaction-local non-case `DOISourceImportAttemptRetentionEventV1` (`SOURCE_IMPORT_ATTEMPT_PURGE_FINALIZED`, RC-114, payload `doi-source-import-attempt-purge-payload/v1`), increments one closed v2 aggregate count, deletes the complete attempt projection/start/terminal/retention graph, IDs, run/source/tab/schema/actor/time/failure/fingerprint/revision/row detail, attempt-owned staged/rejected graphs, indexes/caches/logs/traces/temp exports/files/backups/exceptions/dead letters, every reverse lookup, and all due batch/run edges, invokes TR-105/113 as applicable, conditionally deletes run identity at its due final reference, and deletes the RC-114 event itself before commit. A retained non-due owner prevents premature run deletion but cannot reconstruct a deleted attempt; final-owner deletion removes the complete run graph. Any failure at aggregate, graph, reference, batch, run, or transient-event deletion restores every pretransaction byte. Committed repeat is an absence no-op with no tombstone/count/event/hash.

Only `DOISourceImportAggregateV2` survives, with exact fields `{aggregate_schema_version="doi-source-import-aggregate/v2",local_calendar_month,attempt_outcome_class,attempt_count}`. No aggregate ID/hash/revision, reason, duration/exact time, source/run/attempt/batch/case/order identity, error text, or drill-through key is legal. The fixed retention vector reproduces stream `b14b67e59e765b28d927b12a6d59b161944dd27c06dbe13ce3439000f3233513`, event ID `86b3208fb50e2352a65a49b4a74016d00956fd9109f72030071848cb500aac90`, payload hash `2ad1678cdad8d10be9b4bbb2b46d9b7158c7635638356982b8ce120d7f4c7e32`, and full event hash `738fa8d9ac327be19c099404891e9d18f47a224d8e26c1006e6faa544241c4fe`. `SYN-IMPORT-RET-001..022` are the release-blocking success/failure/boundary/multi-owner/aggregate/artifact/rollback/idempotency/host-timezone/DST/outcome-parity oracles.

### 19.12 Remediation status and safety

No clause here authorizes live OA access, production implementation, source-workbook modification, or any OA write primitive. The exact workbook schema in section 5.1.1 is an explicit user decision based on observed structure; the earlier unauthorized temporary-export procedure remains blocked and is not relabeled as a certified reconnaissance pass.

This remediation package must return to the independent auditor. It does not declare the specification frozen.

Derived registry totals are **115** unique reason codes with **115/115 external ownership**, **115** legal transition rows, and **312** deterministic synthetic oracles across **29** ID families, plus the unchanged 16 historical gates and 213/213 historical accounting.

DOI_FREEZE_REMEDIATION_CANDIDATE = READY_FOR_INDEPENDENT_AUDIT
