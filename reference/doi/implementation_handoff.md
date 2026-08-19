
> **Sanitized supporting reference.** This file is a mechanically sanitized derivative of
> source material supplied for the synthetic proof of concept. Historical status/freeze
> language is nonbinding. The curated files under `specs/` govern. No production-system
> access or real-data use is authorized by this reference.

# DOI Implementation Handoff v0.1.5

Authority patch: v0.1.5.4 HumanFactUsageKind erratum candidate; independent audit required; not a freeze declaration. Repository checkpoint data is recorded only as supplied state in the separate v0.1.5.4 implementation-resume handoff; this Work task did not inspect or modify the repository.

Status: independent-audit remediation handoff; **independent re-audit is still required and this specification is not frozen**. No production code is included. This handoff does not authorize live OA reconnaissance or any modification of Synthetic Order Portal, the manager sheet, historical workbooks, or immutable source corpus. Drive writes are limited to delivery of this remediation artifact package.

## 1. Implementation objective

Build a deterministic, offline-testable DOI module whose operational reach is limited to:

`Observe -> Search -> Navigate -> Extract -> Validate -> Calculate -> Classify -> Recommend -> Report`

Synthetic Order Portal remains permanently read-only. DOI-local persistence is allowed only for the privacy-minimized entities and state described by this exact versioned remediation-candidate contract, pending independent freeze audit.

## 2. Inputs and authority order

Implement against the final package in this order of authority:

1. The locked `synthetic-doi-queue-v0.1` user decision and this v0.1.5 remediation decision set.
2. Technical specification, machine contract, and persistence model, including the incorporated governing modules `source_retention_contract.md`, `provenance_state_contract.md`, `opportunity_kpi_contract.md`, `DOI_LIFECYCLE_EVENT_PAYLOAD_REGISTRY_v0.1.5.md`, and `DOI_OA_CAPABILITY_POLICY_v0.1.5.md`.
3. Versioned reason registry, complete state-transition matrix, lifecycle-route registry, and transition traceability; all totals are derived from their final parsed ID sets.
4. Synthetic requirements and acceptance matrix, including every independently authored deterministic oracle in the final matching parsed ID sets; counts are not quotas.
5. The 213-entry historical assertion manifest as mandatory bounded release evidence, never as an implicit output oracle.
6. Original historical corpus as immutable source evidence and the final-label candidate as its unchanged lineage derivative.

If artifacts conflict, fail the build/gate and request specification reconciliation. Never choose a business rule in code.

## 3. Required component boundaries

Keep these interfaces narrow and independently testable:

- `ManagerSourceImporter`: exact locked workbook/tab/sentinel/positional contract, coherent A/B scan, exact TARGET_REP filtering, duplicate/conflict handling, dual personal hashes, mandatory import attempt, privacy-minimized immutable batch.
- `DOIRunCoordinator`: immediately records every accepted invocation/import attempt, distinguishes run-level failure from order exceptions, enforces one order per run, and manages source disappearance checks.
- `OAReadAdapter` (DEFERRED; not part of this offline release): a future fixed read-only interface may be implemented only after a separately frozen reconnaissance-derived adapter contract. Current work uses only the fictional/static fake adapter in release tests and contains no OA host, browser, credential, session, navigation, or network capability.
- `OrderExtractor`: complete-whole-order validation, normalized facts, minimal failed-attempt metadata, and deterministic line identity inputs.
- `SnapshotStore`: immutable normalized source snapshots and line snapshots; no classifications.
- `RulesEvaluator`: pure function of exact snapshot/rules/reason/calendar/revision/observation/human-fact bindings and hashes; emits immutable evaluations and scoped atomic outputs.
- `CaseLifecycle`: one persistent case per exact Order Number; legal transitions, reversible closure/reopen, purge-deadline management, and generated validation of the complete explicit `PriorClosureRetentionBindingV1` in both reopen and purge-cancellation payloads before append.
- `LifecycleEventSerializer`: generated closed `DOIOrderLifecycleEventV2` discriminator/validators, exact JCS domains, typed-event thin references, stream/projection replay, and RC-113/111/103/081 separation; no permissive unknown/additional-property path.
- `HumanFactStore` and `DedupeReducer`: constructible structured DEDUPE decision facts, deterministic review/fingerprint identity, exact fact-to-state-event ID/hash linkage, and atomic TR-061/TR-062.
- `AttentionReducerV2`: immutable cause-keyed SET/CLEAR history that preserves complete cause and independent resolution provenance and rebuilds the active set.
- `AlternateKnowledgeStore`: stable relationship identities plus immutable revisions, Action Context-scoped volatile observations, lifecycle/provenance, reuse, freshness, and deletion.
- `InterventionVerifier`: exact opportunity scope, logical/evidence keys and canonical bytes, action/value/reversal typed history, resulting-link natural/mapping identity, and fail-closed idempotency.
- `KPIAggregator`: arbitrary-precision arithmetic only within identical currency-and-ISO-registry-version/scale bindings, retained full-ledger contributions, daily New York leaf buckets, original-action attribution, deterministic upsert, and atomic finalization.
- `RetentionPurger`: independently testable deadline calculation, case purge, observation rolling purge, and allowed aggregate/product-knowledge survival.
- `PrivacyGuard`: allowlist/denylist enforcement at persistence, logging, tracing, error, cache, and export boundaries.
- `HistoricalEvidenceValidator`: offline-only one-to-one corpus/manifest accounting, immutable-hash and source-reference checks, assertion-scope/privacy/anti-leakage checks, layer/coverage reconciliation, and enforcement of an executable historical denominator of zero for the original baseline.

No component may reach around these interfaces to read stale facts, alter immutable records, or acquire a mutation-capable OA client.

## 4. Identity and idempotency checklist

- `DOISourceBatch`: immutable identity from spreadsheet ID + exact tab role/title/gid + schema version + normalized TARGET_REP-row hash + privacy-minimized TARGET_REP-order assignee-conflict fingerprint. Unrelated other-rep rows do not affect identity; a conflict involving an in-scope TARGET_REP Order Number does.
- `DOIRun`/`DOISourceImportAttempt`: every accepted invocation creates one new run and attempt ordinal 1 before acquisition; one or more sequential same-run attempts use opaque fresh IDs, next ordinals, and attempt-owned command tokens while the run remains IN_PROGRESS. Run v2 retains only attempt count. Intermediate ABORTED_PRE_OA has empty reasons and requires a later terminalizing attempt; named failures have null executable batch, RC-090 plus exact reason, and zero OA reads.
- staged source order: unique by `(source_import_attempt_id,order_number)`; compatible duplicates within that exact attempt retain multiple source references, while a different legal attempt ordinal is separately owned and never collides on a run/order key.
- `DOIOrderCase`: one persistent identity per exact Order Number across runs and reopenings only while the detailed identity exists. After irreversible purge, a later matching Order Number follows ordinary new-case creation and has no predecessor link.
- `DOIOrderSnapshot`: new immutable identity for each successful complete extraction.
- `DOIEvaluation`: immutable complete binding manifest with exact snapshot/rules/reason/calendar/revision/observation/human-fact IDs and content hashes plus input/output/full-record digests; no substitution on mismatch.
- `DOIOpportunity`: exact nonempty quantity-bearing `credit_scope`, deterministic overlap key, and distinct scenario option ID; unproved scope creates no opportunity.
- `DOIIntervention`: one logical verified action effect keyed by case/type/stable proof-bound action occurrence ID, with action time/target/link/scope/quantity in closed material bytes plus one or more compatible proof records. Proof time is excluded from the natural key. For a credit-bearing intervention, null business action time is permitted only with RC-099 and no monetary row; non-credit `DS_SEPARATION` does not receive RC-099 merely because no monetary attribution instant is required. Contradictory material reuse fails closed.
- resulting-order link: unique retained `(parent case, relationship type, child Order Number)` identity plus separate immutable mapping revisions/fingerprints.
- alternate relationship: stable product-only identity plus immutable monotonically increasing revisions; evaluations bind exact revision/hash.
- alternate observation: immutable, binds exact relationship revision and Action Context when current for action; never overwritten to simulate freshness.
- Action Context: one immutable identity per human action-preparation attempt; later attempt gets a new ID and all case links delete at purge.
- DEDUPE review/decision: deterministic review ID from the case, exact candidate DEDUPE occurrence, and candidate evaluation ID/content hash before the candidate event is hashed; the candidate event embeds that derived review ID. Decision fingerprint and command token; exact HUMAN_FACT ID/hash FK from human DEDUPE events; one current decision chain with only the registered approval-to-rejection correction.
- attention: SET identity `(case,SET,cause_key)` and CLEAR identity `(case,CLEAR,active_set_event_id)` under the v2 cause/resolution partitions; exact replay no-op and conflicting resolver payload fail closed.
- reopen/cancellation: both events embed the same closed `PriorClosureRetentionBindingV1` copied byte-for-byte from the authoritative retained prior closure and locked pre-event projection. The binding includes closure event/kind/classification/verified instant, retention policy/version/timezone/tzdb/calendar rule, active deadline, prior projection revision/hash, and exact closure source/evidence identity. A projection hash alone is insufficient; any mismatch rejects both appends and preserves the prior state.
- executable synthetic fixtures: every case and every harness-level order, customer, and product identity must pass the reserved `SYN-DOI-` namespace validator before canonical serialization or fixture execution. Lifecycle V1/V2/V3 use exactly `SYN-DOI-CASE-0001`, `SYN-DOI-CASE-0002`, and `SYN-DOI-CASE-0003`. A production-shaped field with a stricter lexical type may use only an exact registered generated sentinel: V1 maps `SYN-DOI-ORDER-0001` to decimal `"1"`, after denyset proof, and arbitrary numeric identities remain forbidden. Documentation-only historical identifiers never enter executable bytes.
- KPI: one retained contribution per intervention and one non-identifying daily/currency/leaf bucket per exact key; retries are idempotent and no per-case marker survives purge.

Enforce uniqueness in persistence as well as application logic. Race tests must prove duplicate creation fails closed.

## 5. Source-import behavior

1. Require explicit confirmation of one of the three locked role/title/gid tuples in spreadsheet `SYNTHETIC-SOURCE-ID`.
2. Implement only `synthetic-doi-queue-v0.1`: A1/B1 blank, E1=`Rep`, F1=`# Of Orders`, G1=`Completed`, Order Number=A and Assigned Rep=B from row 2. Literal A/B headers are intentionally absent. No fuzzy or alternate positional guessing.
3. Derive the populated A/B span from actual records, not filter endpoint. E:O row data is outside the model.
4. Before assignee filtering or hashing, validate every populated A/B record: normalize A losslessly from digit text (leading zeros removed) or a provider-proved exact integer lexeme; fractions/exponents/signs/zero/negative/boolean/date/error/precision ambiguity are invariant failures. Require scalar B; include a valid record in personal scope only when locale-independent `lower(trim(B)) == "TARGET_REP"`; no aliases.
5. Immediately create the run and attempt ordinal 1. A legal retry after terminal non-success uses the next ordinal/fresh ID in the same IN_PROGRESS run; ordinal gaps, concurrency, changed replay, and post-terminal append fail. A deliberate pre-OA abort terminalizes only that attempt with empty reasons and requires a later attempt. A final workbook/tab/sentinel/positional/populated-record A-value or B-type/read/change/integrity failure emits RC-090 plus its exact specific code, terminalizes run/final attempt FAILED, creates no source batch/work/case/evaluation, and performs zero OA reads.
6. Compute exact TARGET_REP-row-content hash and conflict fingerprint. Never persist other-rep name/content/locator/unrelated Order Number. A conflict involving a TARGET_REP Order Number changes batch identity and blocks only that order.
7. Never downgrade an invalid populated-record A or non-scalar B to a row-only rejection. After whole-source validation succeeds, all duplicate TARGET_REP A/B rows for one canonical number merge with RC-006 even when E:O differs, because E:O is outside this mapping. RC-007 is compatibility-reserved/unreachable here. Only a valid same-number TARGET_REP plus nonblank non-TARGET_REP scalar assignee creates the RC-008 no-case rejection; blank scalar B does not.
8. Reuse an identical privacy-relevant batch but never reuse a completed run or attempt identity. Exact same attempt command/ordinal/bytes is idempotent; a new retry uses a fresh attempt identity. Scan-specific counts/locators stay off the immutable batch.
9. A coherent run with any order exception is `COMPLETED_WITH_EXCEPTIONS`, including all orders blocked or all permitted extractions failed with zero normal evaluations. `FAILED` is run-level source execution only.
10. Attempt-local no-case rejected identity uses exact v2 natural-key bytes over `(source_import_attempt_id,order_number)` and deletes at exact `calendar90(run.completed_at)`; batch reuse cannot extend or revive it, and a legal later ordinal is a distinct record.
11. Create one explicit `DOISourceBatchReference` for every retained successful run, coherent successful attempt, staged record, no-case record, and case source binding. Non-success attempts own no batch reference. For every failure including RC-091, store null coherent fingerprint/batch and no candidate digest/preimage/fingerprint/undocumented reference. Delete attempt/staged references under TR-114 and retain/delete the shared batch solely through TR-113's locked exact last-reference predicate.
12. Keep every staged record/source row attempt-owned. Before `CASE_CREATED`/`SOURCE_PRESENT`, atomically create/reuse `DOICaseSourceBinding`, its batch/reference owner, and closed `DOICaseSourceAdmissionProofV1`; lifecycle binds the admission proof, never staged/run/attempt/row/tab/actor detail. The proof contains only schema/ID, case ID, Order Number, TARGET_REP, batch/binding IDs, admitted time, and content hash and deletes only with the case. A retained work/extraction/snapshot/evaluation chain may keep governed run ID, source-batch ID, and case admission proof while its `RUN_WORK_GRAPH` reference remains, but must have zero source-import-attempt ID, staged-order ID, TARGET_REP SourceRef, ordinal/token, or attempt/source-row locator after TR-114.
13. At run terminal, assign every attempt and the run the same exact `calendar90(run.completed_at)` deadline. Implement `doi-run-identity-reference/v1`, TR-114, the transaction-local RC-114 retention event/fixed hashes, complete attempt/staged/rejection/log/cache/export/index deletion, aggregate + rollback + last-owner logic, and closed month/outcome/count `DOISourceImportAggregateV2`. Run all `SYN-IMPORT-RET-001..022` branches.
14. Treat source absence as `SOURCE_ABSENT_RECHECK_REQUIRED`, never closure; perform one read-only check against the existing case.

Persist only privacy-minimized TARGET_REP references/counts and the two allowed hashes. Ensure log/error paths do not preserve raw cells. The prior unauthorized temporary-export/browser procedure remains BLOCKED and is not a certified reconnaissance PASS; this fixed mapping is the explicit user business decision.

## 6. Extraction and evaluation behavior

The extractor has only two successful field outcomes: a normalized value or `UNKNOWN` for a value that was observed but could not safely normalize. Missing/unreadable required source material is an extraction failure. Under authority revision 0.1.5.3, UNKNOWN availability emits RC-016, UNKNOWN DS state emits RC-017, and UNKNOWN ETA emits RC-115. Independent unknown fields use exact set union; a reason cannot substitute across fields. RC-115 blocks only ETA-dependent conclusions/ranking and never guesses or reuses an ETA.

Success requires exact order identity and proof of all relevant lines. A failure creates no snapshot/evaluation and stores only minimal `DOIExtractionAttempt` metadata plus `RECHECK_REQUIRED`.

Never carry a dynamic fact forward from an older snapshot. Never use row position alone for line continuity. `LINE_CONTINUITY_UNVERIFIED` blocks only conclusions dependent on uncertain lineage; it need not contaminate independently safe case-level rules.

Keep snapshots facts-only. The evaluator receives a complete immutable binding manifest: snapshot ID/hash; exact rules/reason/calendar versions and hashes as applicable; exact relationship revisions/hashes; current Action-Context-bound observations/hashes; structured human facts/hashes; and evaluation time. It validates canonical input bytes and appends classifications, scoped opportunities, flags, calculations, reason codes, recommendations, and output/full-record hashes as a separate immutable record. Missing/wrong-scope/hash-mismatched input appends no evaluation and never substitutes a newer version.

## 7. Rule-engine implementation constraints

- Exact Order Number is the persistent case key.
- All relevant lines DS -> `DOI_EXCLUDED`.
- Mixed DS remains actionable and emits `DS_SEPARATION_REQUIRED`.
- Explicit non-DS in-stock plus delayed -> `FULFILLMENT_SPLIT_CANDIDATE` opportunity.
- Only explicit OA-normalized `IN_STOCK` eligible quantities/values contribute to available-to-ship value.
- Partial calculations use exact remaining/available quantity and integer minor units, remain in `partial_available_value`, and emit `PARTIAL_QTY_INTERVENTION_REVIEW`; they are not automatically treated as fully split-eligible ATS value. Missing inputs do not become estimates.
- Unknown facts are contained unless they block every safe conclusion.
- Payment, WWC, and DEDUPE findings remain separate from opportunities.
- Same ES# -> `EXACT_SKU_RECHECK`, never alternate.
- Alternate requires a verified different ES# and follows exact-MFG/OE -> explicit cross-reference/supersession -> functional hierarchy.
- Every substitution requires customer approval; functional candidates also require fresh compatibility review for each application/order.

Bind geography handling, payment-only handling, all-in-stock handling, WWC business-date boundaries, and event-scoped alternate-observation freshness to the explicit machine-contract clauses. These items are resolved by the governing draft plus newer decisions; tests must use those clauses and must not resurrect them as open policy.

## 8. Alternate knowledge implementation

Separate stable product-only relationship identity from immutable monotonically increasing relationship revisions and from timestamped volatile observations. Creation, product-fact change, supersession, and invalidation append revisions; no prior revision changes. Every evaluation binds the exact relationship/revision/content hash it used.

First complete exact-MFG/OE, explicit cross-reference, or explicit supersession proof creates exactly one ACTIVE relationship revision of the matching type; exact replay reuses it. When the fixture includes the required fresh current observation, surface exactly one customer-approval-required alternate opportunity. On a matching later order, reuse one exact relationship without a duplicate and surface exactly one opportunity; if the current observation is absent/stale, set exactly `RECHECK_REQUIRED_BEFORE_ACTION`. Prior functional knowledge instead surfaces exactly one `FUNCTIONAL_COMPATIBILITY_REVIEW_REQUIRED` state and never reuses compatibility approval for a new application.

Failure to rediscover an active relationship does not invalidate it. Only explicit product-only contradiction/supersession changes lifecycle. Contact/substitution requires a new `DOIActionContext` for the specific retained case/evaluation/opportunity and an observation explicitly linked to that OPEN context. Later attempts create new contexts; context creation performs no OA action.

Nominal observation deletion is exact `calendar90(observed_at)`, and a case-linked observation/link target plus its target-owned one-event volatile lifecycle wrapper delete atomically at the earlier nominal deadline or current linked-case purge. The core case ledger never references the volatile wrapper; no direct target/index/receipt remains. A preexisting evaluation/opportunity may retain only its sealed observation ID/hash commitment until case purge, unusable for lookup, reconstruction, or freshness. Relationship revisions survive indefinitely only when product-only from inception and fully de-linked from every order/case/customer/context/source-row/evaluation/intervention/result-order marker or reconstructable derivative.

## 9. Opportunity, intervention, evidence, and KPI implementation

Normal path:

`opportunity -> human acts manually in OA -> Recheck Order -> deterministic proof -> intervention`

Planning/recommending is not intervention. Unprovable change creates verification-required state only. Both SYSTEM_VERIFIED and HUMAN_VERIFIED action evidence are valid. The first complete structured human action proof creates one intervention and one HUMAN_VERIFIED event; exact replay reuses them with zero additional credit-bearing effect, and conflicting same-key payload fails closed. Action and value verification are independent.

TR-106 is exhaustive and order-independent. First derive the exact date/currency base set: exact-date valid or absent `{RC-063}`; exact-date invalid `{RC-063,RC-094}`; null-date valid or absent `{RC-063,RC-099}`; null-date invalid `{RC-063,RC-094,RC-099}`. Then union at most one rep-proof modifier. A split with exact accepted `AUTO_LINKED|HUMAN_CONFIRMED` child link adds RC-074 iff resulting-order-level TARGET_REP rep is missing/different/ambiguous; preserve the exact link. A substitution adds RC-075 iff replacement line-level TARGET_REP rep is missing/different/ambiguous; parent order-level rep never substitutes and the line binding remains unchanged. Verified applicable TARGET_REP rep adds neither. Exact-date/valid blocked sets are exactly `{RC-063,RC-074}` and `{RC-063,RC-075}`; each keeps one verified intervention `UNVERIFIED`, creates one count-1 zero-money row, and realizes zero. DS is `NOT_APPLICABLE`, all money/currency null, no row, and none of RC-063, RC-074, RC-075, or RC-099 merely for lacking a monetary date. Both rep modifiers, wrong type, or a contradictory branch is RC-081 before TR-106 with zero row/state append. Preserve the independently valid action when only invalid monetary material is rejected; never create a second intervention or fabricated link.

Generate and validate the unchanged closed `doi-reason-ownership/v1` matrix at authority revision 0.1.5.3 with reason registry 0.1.5.3. All 115 codes require at least one external rule/service owner and deterministic asserting oracle; every emitted/referenced code must exist; every registry entry must be owned/asserted; unknown code/version, stale binding, orphan, undefined reference, duplicate, or unversioned alias fails before persistence. Bind new evaluations to registry hash `38eba58f78950c320b9b4e3ece167cc050cae6c11ee0978b98749f3247c2ec86`, ownership hash `c2f0e0a365aed6c594d5f4f5ad19efdac4ee9a1488f525a63f898a26bb571a45`, rules engine `synthetic.doi.rules/v0.1.5.4`, rules-bundle hash `df48446467a81eec9970b22649bf5d86cb5dc09e0ecaad291839774523288ad0`, normalization contract `doi-normalization-contract/v0.1.5.3`, and HumanFact usage registry `doi-human-fact-usage-kind/v1` / `da0612598dcd2b8300d9459af29e192cbf0a3413802cf548fc618713d4721764`. Preserve that rules bundle byte-for-byte: v0.1.5.5 adds only the serialization/provenance contract `DOI_HUMAN_FACT_BINDING_HASH_CONTRACT_v0.1.5.5.json`. For each validated eight-member binding, derive `human_fact_binding_sha256 = SHA256(UTF8("doi-human-fact-binding/v1\n") || UTF8(RFC8785(binding)))` outside the binding object; never persist it as a ninth member or confuse it with fact/evaluation digests. Generate the exact six-member enum, unchanged applicability matrix, v0.1.5.5 schema slice, and fixed v0.1.5.5 evaluation vector. Run strengthened `SYN-EVAL-PROV-001/005` known-answer, negative-domain, canonicalization, mutation, legality, and idempotency selectors plus all previously required gates.

Keep OA safety ownership partitioned. RC-082 is the structural system/build-boundary result for a forbidden `click` helper or equivalent write-capable module/manifest capability and fails before runtime/package promotion (`SYN-OA-RO-003`, `SYN-OA-CAP-002`, `SYN-REASON-OWN-005`; `SYN-REASON-OWN-006` is its negative/non-applicable control). RC-083 is the runtime user/API dispatch-boundary result for each canonical unsafe predicate—deliberate `POST|PUT|PATCH|DELETE`, GraphQL mutation/write-RPC, generic mutation-capable action/click request, background-poll request, or unallowlisted side-effectful read—and fails before dispatch (`SYN-OA-RO-001/005`, `SYN-REASON-OWN-006..008`). Never substitute one for the other; every branch has zero OA mutation, DOI append, persistence, and dispatched network side effect beyond the local blocked-probe observation.

Every opportunity first derives a nonempty canonical exact line/quantity `credit_scope` from the immutable snapshot. Row position, unknown quantity, or unverified continuity cannot fabricate scope. Build overlap groups from actually shared scoped merchandise under one scenario basis; opportunity type is excluded from the overlap key when types compete for the same credit. Each option has a distinct deterministic ID. Same-order membership alone does not imply overlap; a multi-option group contributes at most one selected potential value.

Money rules:

- store exact `{amount_decimal,currency_code,iso_4217_registry_version}` Money and calculate with arbitrary-precision integer coefficients at the exact registry scale;
- validate ISO-4217; never infer USD, FX, base currency, or a mixed-currency scalar;
- estimated/unverified money contributes zero;
- human-verified money must be exact, never a range/estimate;
- later conflicting SYSTEM_VERIFIED value controls current KPI calculations while all evidence remains in audit history;
- support `VERIFIED`, `PARTIALLY_REVERSED`, `REVERSED`;
- preserve `original_realized_value`, `reversed_value`, `net_realized_value`;
- require `0 <= reversed_value <= original_realized_value` and `net = original - reversed`;
- persist only daily `America/New_York` currency/leaf-class KPI buckets; weekly/monthly/quarterly/yearly and ALL views are rollups;
- attribute realized credit only when exact business action time exists, to that action's local date; never substitute proof/review time. Later value/correction/reversal evidence updates that same original bucket, whose provenance dimension remains the first accepted action event despite compatible cross-provenance corroboration;
- keep retained contributions case-linked and rebuild them from the full accepted ledger. At purge, atomically transfer identical retained values to finalized fields and delete every case-linked identity/fingerprint;
- reopening does not duplicate old interventions or credit.

The supersession, reversal, reconciliation, and duplicate-credit guarantees above apply only while the detailed case exists. Purge finalizes its then-current exact aggregate contribution; later per-order evidence cannot recover the deleted scope or alter that aggregate.

Use canonical natural keys plus retained canonical payload bytes and SHA-256 for action/value/reversal/link evidence. Enforce the shared action/value occurrence registries before natural-key allocation: reuse across a different action type/value kind or with changed material is RC-102 and never a second effect. Exact replay is a no-op; same digest with different bytes is fatal. Resulting-order natural identity and canonical `moved_components[].quantity` mapping have separate fingerprints/revisions; all event/revision/logical-material/evidence aliases must resolve to byte-identical scope, candidate-set, and mapping hashes. Never infer action, approval, value, reversal, or resulting-order identity from historical labels or temporal/customer proximity.

## 10. Lifecycle and retention implementation

Generate the case lifecycle serializer/reducer from `DOI_LIFECYCLE_EVENT_PAYLOAD_REGISTRY_v0.1.5.md`. Validate the exact 56-kind union, eight persisted case payload schemas, common envelope, source bindings, event-natural/payload/projection/full hashes, and exact stream partition before append: 54 kinds use the core case chain; observation/link wrappers each use one separate target-owned sequence-1 stream with equal locked prior/result core revision/hash and no projection change. CASE_CREATED/SOURCE_PRESENT source bindings resolve only the closed case-owned `DOICaseSourceAdmissionProofV1`, never staged/run/attempt/row/tab/actor detail. Regenerated V1 authorities are case-source binding `e39a40adfeb2b606981364928e38bb867a20f6349e0b2a734e82d0c17bceb2f3`, proof ID/logical occurrence `e2aa8e7b7fe795821d230ede3d731c79f8670718e277d8d0812f1a83df97636e`, proof hash `2e9ac63cf8d5cda713e46351f4c8e8ce83429c2e39f35142113fd54da15f53b8`, natural `a8feba67a425e50f0a584a14336f4a3290a5f3de104cc0f86fb6ab2d34e3cb90`, and full event `0baab70132263d66f67582425bbf6d6c227ebb5c10317ea124babf5aee70c257`; use these exact literals in executable vectors. Generate `PriorClosureRetentionBindingV1` as a closed reusable type and make it required in `CaseReopenPayloadV2` and `PURGE_CANCELED`. Resolve the exact retained closure event and locked pre-event projection; byte-compare every binding field and require `canceled_purge_eligible_at == prior_purge_eligible_at`. Bind the reopen proof/reason/time, same case, prior deadline, resulting revision/projection, and cancellation effect under exact required/null/absent partitions. Missing, inferred, hash-only, stale, or different tuple bytes are RC-113 and roll back the full bundle with no revision allocation. A case-linked typed event, thin core wrapper, projection, and subordinate KPI/mapping effect are one transaction; an observation/link target and its volatile wrapper are one transaction and one retention graph. Replaying exact retained bytes returns the original event/timestamp; any unknown/extra/missing/null-partition/hash variant is RC-113 with no append. Run the published V1/V2 fixed vectors and all `SYN-LIFE-PAYLOAD-*` fixtures. Never invent an implementation payload or `CASE_PURGED` receipt.

Generate the separate non-case `DOISourceImportAttemptRetentionEventV1` and `SourceImportAttemptPurgePayloadV1` from source-retention section 13. They do not change the case-lifecycle kind/schema counts. Validate its owner-derived sequence-1 stream, exact RC-114, aggregate/run/batch branch partitions, and all required deletion booleans before any aggregate or graph mutation. The fixed vector must reproduce stream `b14b67e59e765b28d927b12a6d59b161944dd27c06dbe13ce3439000f3233513`, event ID `86b3208fb50e2352a65a49b4a74016d00956fd9109f72030071848cb500aac90`, payload hash `2ad1678cdad8d10be9b4bbb2b46d9b7158c7635638356982b8ce120d7f4c7e32`, and full event hash `738fa8d9ac327be19c099404891e9d18f47a224d8e26c1006e6faa544241c4fe`. Delete that event itself in the same TR-114 commit; no retention event or hash survives.

Before running any executable synthetic fixture or fixed vector, apply the closed synthetic identity firewall to every case/order/customer/product identity in source, generated fixture output, and built artifacts. Accept only exact registered `SYN-DOI-` harness identities, including lifecycle vector cases `SYN-DOI-CASE-0001`, `SYN-DOI-CASE-0002`, and `SYN-DOI-CASE-0003`; the sole V1 `OrderNumber` conversion is the registered `SYN-DOI-ORDER-0001 -> "1"` schema adapter after complete historical/source denyset validation. Reject `case-0001`, `case-0002`, generic `case-*`, arbitrary or production-looking numeric order identities, aliases/lowercase prefixes, and controlled historical canaries before serialization, reducer construction, adapter construction, or persistence. Run the regenerated `SYN-LIFE-PAYLOAD-002/003/004/005/010`, `SYN-OA-RO-009`, and `SYN-OA-RO-008` against authored and built outputs.

Implement attention only as `doi-attention-event/v2` plus `doi-attention-cause-key/v2`. SET stores complete cause and null resolution. CLEAR names the exact active SET, copies its cause/key, and binds a separate complete resolver/time/reason; resolver fields never enter the cause key. Implement the exact TR-093 and TR-095 branch tables. Implement DEDUPE decisions only through the two closed HumanFact pairs and the two-stream atomic algorithms; an OA note can never synthesize a human decision.

Hard terminal closures: `SHIPPED`, full `CANCELED`.

Reversible terminal closures: `REP_TRANSFERRED`, `DEDUPE_CONFIRMED`, explicit human out-of-scope closure.

Queue exit is not closure. A verified terminal transition schedules `purge_eligible_at=calendar90(terminal_closed_at)`: convert to `America/New_York`, advance exactly 90 local dates preserving wall time, resolve a spring gap to the first valid instant after the gap and a fall overlap to the later occurrence, then persist UTC plus policy/timezone-database versions. Fixed 2,160-hour arithmetic is forbidden. Reopening cancels that deadline on the same case; a later verified closure calculates a new one.

Source-import-attempt retention uses the same calendar algorithm but always anchors to the associated terminal run: `source_import_attempt_purge_eligible_at = run_purge_eligible_at = calendar90(run.completed_at)`. A nonterminal run assigns neither deadline. All attempts of one terminal run—including successful, failed, and an earlier intermediate abort—receive the byte-identical deadline. Implement one `doi-run-identity-reference/v1` row per lawful run-ID owner; run v2 stores only attempt count. TR-114 locks the complete graph, upserts exactly one non-identifying month/outcome/count aggregate delta, constructs/hashes the transaction-local RC-114 event, deletes the complete attempt/staged/due-rejection/source/artifact/index/reverse-lookup graph and due batch edges, releases the attempt run reference, conditionally deletes the due run graph at final reference, deletes the event itself, and commits. A non-due owner retains the run without an attempt locator. Every injected failure restores the aggregate/event/graph/reference/batch/run state byte-for-byte; committed replay finds absence and does nothing.

Purge is the irreversible case-finalization boundary. In one ACID transaction, verify and transfer each retained contribution from retained to finalized fields in its original daily/currency bucket without changing totals; then delete the complete case graph. This includes exact Order Number, case source admission proofs/bindings and work links, snapshots/lines/evaluations and hashes, opportunities/scopes, Action Contexts and linked observations, all typed histories/human facts, interventions and canonical evidence bytes/keys/fingerprints, resulting child Order Number/link mappings, logs/caches/exports, and every reconstructable join. Attempt-owned staged/source-row detail is never part of this case graph and deletes under TR-114. Delete the case's source-batch references and invoke TR-113 in that transaction; a source-batch event deletes with its explicit owner graph. Retain no tombstone, finalization marker, persistent case/order/customer/source-batch hash, predecessor, or per-case archive. Retain only non-identifying daily/import aggregates and separately governed fully de-linked product-only relationship revisions.

After purge:

- same-case reopen, per-case correction/reversal/reconciliation, and cross-purge duplicate-credit guarantees intentionally end;
- a later input with the same real-world Order Number follows `NONEXISTENT → ACTIVE`, creates a new `DOIOrderCase` and new `case_id`, and creates no predecessor/reopen link;
- the system does not search for or reconstruct a tombstone, hash, archive, or prior identity and makes no cross-purge deduplication claim;
- a late reversal or system-over-human correction cannot resolve a retained case/intervention, is rejected with `CASE_IDENTITY_NOT_RETAINED`, appends no per-case event, changes no finalized aggregate, and leaves no order-specific rejection record.

Within retention, all prior same-case, correction, reversal, evidence-supersession, and duplicate-credit guarantees remain mandatory. Reopening before purge cancels the old deadline; the next verified terminal closure calculates a new exact calendar deadline. A linked observation uses the earlier of its nominal `calendar90(observed_at)` deadline and current case purge.

The purge implementation must inventory every primary, index, cache, search document, log correlation, export, backup policy, and analytics join key. A logical row delete that leaves reconstructable identity elsewhere fails acceptance.

## 11. Privacy engineering checklist

Allowed active-case operational data is limited to the governing allowlist. Explicitly deny at every boundary:

- customer name, email, phone, VIN, full address;
- full OA note bodies;
- persistent customer hashes;
- full OA HTML, DOM dumps, screenshots, page copies;
- credentials and session data.

Retain only the necessary geography classification. Narrow structured non-sensitive raw values may explain normalization, but must not carry surrounding page text.

Use structured logging with a field allowlist, not after-the-fact redaction alone. Test logs, errors, traces, caches, dead-letter paths, and exported fixtures with `SYN-PRV-*` canaries.

## 12. Permanent OA read-only architecture

The v0.1.5 offline core exposes no OA integration, live browser, host/network permission, cookie/session access, background/content script, native messaging, download/export path, or input/mutation helper. Implement `DOI_OA_CAPABILITY_POLICY_v0.1.5.md` exactly:

1. Normalize and inspect source, dependency graph/lock, manifest fragments, final manifest, module registries, source maps, and built output.
2. Require the exact empty browser/host/optional/content/background/external-messaging permission projection and the closed fixture-only module capability set.
3. Reject every named interaction/input helper plus aliases, wrappers, computed/bracket access, reflection, registry dispatch, callbacks, minified output, and unresolved dynamic capability names.
4. Run mutation canaries with network denied; require exact page/fixture hash invariance and an empty mutation-event journal.
5. Preserve separate zero counters for application-originated OA attempts and outbound OA mutation/read requests; named probes are rejected before dispatch.
6. Block artifact promotion on any finding. A future exact read-only OA adapter requires a separate frozen reconnaissance-derived contract and cannot be introduced here.

Manual workflow actions write only DOI-local records. The human performs any real OA action outside Sales Assist; subsequent read-only recheck verifies what happened.

## 13. Recommended implementation sequence and gates

Before resuming Checkpoint 04—and only after an independent audit freezes v0.1.5.5—verify the exact stopped repository state in `DOI_IMPLEMENTATION_RESUME_HANDOFF_v0.1.5.5.md`, refresh the authority cache, and deterministically regenerate only the Checkpoint 03 outputs directly dependent on v0.1.5.4/v0.1.5.5: the primitive/enum catalog, `HumanFactBinding` schema, external binding-hash validator, `DOIEvaluation` provenance schema, fixed `SYN-EVAL-PROV-001` fixture/vector, authority manifest, and generated test/traceability views. Source authorities are `DOI_HUMAN_FACT_USAGE_KIND_REGISTRY_v0.1.5.4.json`, unchanged `DOI_RULES_BUNDLE_v0.1.5.4.json`, `DOI_HUMAN_FACT_BINDING_HASH_CONTRACT_v0.1.5.5.json`, `DOI_HUMAN_FACT_EVALUATION_SCHEMAS_v0.1.5.5.json`, `DOI_EVALUATION_PROVENANCE_VECTOR_v0.1.5.5.json`, and `DOI_AUTHORITY_VERSION_MANIFEST_v0.1.5.5.json`. Commit the scoped regenerated delta only after its tests pass, before Checkpoint 04 starts. Stop if repository state differs. Do not regenerate unrelated outputs, add a reason/transition/test ID, or change prior checkpoint history.

1. Implement canonical JCS/SHA-256 encoders, exact decimal/ISO registry types, the closed case lifecycle and non-case retention/typed-event envelopes, generated discriminators, `DOICaseSourceAdmissionProofV1`, `PriorClosureRetentionBindingV1`, `SourceImportAttemptPurgePayloadV1`, and known-answer/collision tests including every regenerated `SYN-LIFE-PAYLOAD-*` and fixed TR-114 vector plus the reserved synthetic-identity negative case.
2. Implement privacy-safe entity persistence and immutable/idempotent constraints.
3. Implement sequential source-import attempts and fake sheet adapter; pass all `SYN-SRC-*` tests, including ordinal/token/abort/retry branches.
4. Implement fake OA read adapter, extractor, snapshot/evaluation separation, and continuity; pass `SYN-EXT-*`/`SYN-LINE-*`.
5. Implement pure deterministic rules plus the constructible DEDUPE HumanFact/state atomic flow; pass `SYN-RULE-*`, `SYN-GEO-*`, `SYN-WWC-*`, and every `SYN-DED-*` including failure injection and OA-note isolation.
6. Implement relationship revisions, Action Context, provenance bindings, typed state histories, and attention v2; pass `SYN-ALT-REV-*`, `SYN-ACTX-*`, `SYN-EVAL-PROV-*`, every `SYN-STATE-*`, and history tests.
7. Implement exact opportunity scope/overlap/selection; pass `SYN-SCOPE-*`.
8. Implement logical/evidence keys, result-link revisions, intervention/value/reversal reducers; pass `SYN-INT-*`, `SYN-IDEM-*`, and history tests.
9. Implement exhaustive TR-106 including mutually exclusive RC-074 and RC-075 modifiers, retained KPI contributions, New York daily buckets, full-ledger upsert, and atomic fault-injected finalization; generate/validate 115/115 reason ownership and pass every `SYN-KPI-*`, `SYN-CUR-*`, and `SYN-REASON-OWN-*` parity test.
10. Implement exact `calendar90`, case-owned source admission proofs, no-case retention, explicit source-batch/run references, TR-113/TR-114, complete every-outcome attempt deletion, full purge graphs, and privacy deletion; pass `SYN-RET-*`, `SYN-IMPORT-RET-*`, `SYN-BATCH-REF-*`, `SYN-PURGE-EDGE-*`, and `SYN-PRV-*`.
11. Enforce permanent read-only architecture, exact RC-082 structural/RC-083 runtime ownership partition, and the source/generated/built synthetic identity firewall; pass every `SYN-OA-RO-*`, `SYN-OA-RO-PROV-*`, `SYN-OA-CAP-*`, and applicable `SYN-REASON-OWN-*` static/runtime negative test.
12. Validate the 213-entry assertion manifest against the immutable corpus; pass all 16 `HIST-CORPUS-*` gates. Historical assertion/supporting cases remain non-oracles but mandatory release evidence.

No later stage can waive an earlier failed gate.

## 14. Minimal user-action contracts

Each action requires authenticated local authorization, explicit target, idempotency protection, audit provenance, and an OA-write count of zero.

- Run DOI Review: confirm one exact locked tab -> create one run + attempt ordinal 1 -> validate/coherently read A/B -> on a legal pre-OA non-success optionally append next same-run ordinal/fresh ID -> calculate hashes -> create/reuse safe batch -> create case-owned admission proof, never retain staged target -> read only eligible orders -> append complete snapshots/evaluations or final failed attempt/run. Abort stays intermediate; any final import failure stops before OA.
- Recheck Order: read one existing case's order -> append complete snapshot/evaluation or attempt; may verify an intervention/closure but never performs it in OA.
- Recheck Alternate: refresh a volatile observation through permitted read/search sources; never treats durable relationship as fresh availability.
- Human action verification: records exact human assertion/provenance locally; does not perform action in OA.
- Human value verification: accepts exact Money with valid ISO code only; estimate remains unverified/zero KPI and never supplies an FX/base currency.
- Approve DEDUPE: accepts one exact active review, `DEDUPE_APPROVED` structured fact, human-verification reference, decision time, actor, and idempotency token; atomically creates the HumanFact and linked awaiting-verification DEDUPE event; never writes OA.
- Reject DEDUPE: accepts an initial exact `DEDUPE_REJECTED` fact or the sole legal predecessor-bound approval-to-rejection correction before OA verification; every other same-review conflict is RC-112 and appends nothing.
- Mark No Viable Alternate: records a scoped human conclusion locally; does not invalidate durable product knowledge without explicit contradictory evidence.
- Recheck DEDUPE Order: separately reads and appends system evidence; only proven note confirmation after structured approval closes reversibly, and the OA note never constructs the human fact.

Impossible transitions and invalid/null-ambiguous inputs fail closed through the canonical transition matrix.

## 15. Historical versus synthetic execution

Preserve the five original corpus artifacts byte-for-byte. The final-label candidate remains a separate unchanged derivative with explicit lineage. `HISTORICAL_DOI_ASSERTION_MANIFEST_v0.1.jsonl` is a second derived artifact: exactly 213 entries in deterministic corpus order, one per original case, and never an expected-output file.

For each of 213 historical cases, assign exactly one layer:

- `EXECUTABLE_HISTORICAL` only when preserved facts prove complete whole-order capture and the frozen rule supplies an oracle;
- `HISTORICAL_ASSERTION_HUMAN_REVIEW` where judgment remains mandatory;
- `SUPPORTING_ONLY_NOT_REPLAYABLE` where facts are missing.

Authoritative original-baseline counts are exactly 0 `EXECUTABLE_HISTORICAL`, 59 `HISTORICAL_ASSERTION_HUMAN_REVIEW`, and 154 `SUPPORTING_ONLY_NOT_REPLAYABLE`. Frozen historical end-to-end oracle count and executable denominator are both zero.

All 213 are nevertheless mandatory release evidence. The historical validator must prove exact count/order/uniqueness, immutable bytes/hash, source-reference resolution, privacy, supported assertion scope, negative-assertion containment, no target leakage, no non-replayable denominator leakage, 59/154 reconciliation, category/coverage reconciliation, and one-to-one manifest accounting. No case may silently disappear because it is non-replayable.

Synthetic tests remain release-blocking for every family, including source identity/import failure, sequential attempts, exact every-outcome attempt deletion, source admission proofs/references, complete reason ownership, ISO currency, lifecycle payload/replay, provenance, relationship revisions, Action Context, typed histories, exact scope/overlap, evidence/link/reversal idempotency, daily KPI upsert/finalization, exact DST retention, privacy, and OA structural safety. The suite contains **312/312 deterministic synthetic oracles across 29 ID families**. Historical classifications or provisional expected results never become synthetic inputs or targets; fixtures remain fictional and contain no copied customer, order, case, or product identity.

## 16. Resolved purge-finality decision

The former post-purge identity-policy issue is resolved. Purge is intentionally the irreversible case-finalization boundary.

The controlling horizon is explicit:

1. Before purge, same-case reopening, old-deadline cancellation, later reclosure, intervention/value correction, reversal/partial reversal, and per-order duplicate-credit protection remain mandatory.
2. At purge, finalized aggregate contribution is folded into non-identifying history and the complete per-order graph is irreversibly deleted.
3. After purge, no same-case, correction, reconciliation, or cross-purge duplicate-credit guarantee survives because the identity needed to provide it deliberately does not survive.
4. A later matching Order Number starts an unrelated new case; a late correction is rejected without a per-order record or aggregate change.

`SYN-RET-011` deterministically proves new-case semantics and the absence of predecessor/tombstone/hash/archive lookup. `SYN-RET-012` deterministically proves aggregate finalization plus `CASE_IDENTITY_NOT_RETAINED` handling for late correction evidence. Neither test remains policy-undecided.

No tombstone/hash/reconstructable identity may be added to recover the intentionally discontinued guarantee. Completely de-linked reusable product knowledge remains governed separately and cannot join back to a case, order, customer, intervention, or aggregate contribution.

All other previously open policy areas remain resolved for v0.1: WWC counts three full versioned SyntheticCo business dates and eligibility starts on the next business date; alternate freshness is an explicit current-recheck context rather than an age threshold; geography changes handling as specified; all-in-stock routes to progress review then monitor on normal progression; payment-only excludes while payment+product preserves opportunity; partial quantity remains a separately calculated human-review value.

OA-only extraction selectors/field locations and the synthetic business holiday-calendar source may remain deferred to separately authorized reconnaissance/configuration, but that deferral cannot weaken complete-snapshot, privacy, or read-only contracts. The manager workbook schema is not deferred: `synthetic-doi-queue-v0.1` is locked. The earlier browser/export procedure remains blocked and uncertified.

## 17. Future executable historical path

During supervised shadow mode, privacy-minimized complete whole-order captures may be added to a new executable historical regression layer. Every candidate must independently preserve:

- proof of the complete relevant line-set capture;
- every required order-level and line-level fact;
- source, extractor, and schema versions;
- immutable source-fact binding;
- privacy minimization and forbidden-data linting; and
- independent labeling with no historical or engine-output target leakage.

This path is additive. New evidence must not mutate, relabel, merge with, backfill completeness into, or retroactively upgrade any of the original 213 source cases.

## 18. Definition of handoff-ready

The erratum authority contains **312 synthetic release-blocking IDs across 29 ID families**, all **312 with deterministic fixture oracles**, **115 unique reason codes with 115/115 external ownership**, **115 legal transition rows**, plus **16 mandatory historical integrity/assertion/coverage gates** covering all **213** source cases. Bracketed selectors are closed rows within existing test IDs and do not change the 312-ID count.

The remediation package is handoff-ready for independent audit only when:

- all freeze dependencies above are resolved;
- every `SYN-*` row has an executable deterministic oracle, including `SYN-RET-011/012`, `SYN-REASON-OWN-001..010`, and `SYN-IMPORT-RET-001..022`;
- entity schema, null rules, reason registry, and transition matrix agree;
- assertion-manifest count/order/bijection is 213/213 and source bytes/hashes remain unchanged;
- historical layers reconcile to 0/59/154, with executable denominator and frozen historical end-to-end oracle count both zero;
- all historical cases remain release evidence and show no unsupported promotion, negative broadening, privacy breach, target leakage, identity copying, or non-replayable denominator leakage;
- coverage artifacts reconcile and the synthetic suite remains the deterministic fallback for every absent executable-history family;
- retention deletion is demonstrably comprehensive;
- aggregate finalization and post-purge new-case/late-correction behavior match the deterministic boundary tests;
- OA integration has no possible write capability by construction and negative test;
- exact artifact hashes identify the reviewed specification package.

The package-builder's final validation may set `DOI_FREEZE_REMEDIATION_ROUND_4 = PASS` only when both Round-4 blocker families, package hashes, Drive raw read-back, and every-prior-package preservation checks pass. Until then the delta report remains PENDING and carries no terminal PASS line. This is neither a freeze declaration nor production authorization; only a fresh independent auditor may determine whether `DOI_V0.1_SPEC` can become FROZEN.

DOI_FREEZE_REMEDIATION_CANDIDATE = READY_FOR_INDEPENDENT_AUDIT
