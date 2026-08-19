
> **Sanitized supporting reference.** This file is a mechanically sanitized derivative of
> source material supplied for the synthetic proof of concept. Historical status/freeze
> language is nonbinding. The curated files under `specs/` govern. No production-system
> access or real-data use is authorized by this reference.

# DOI Synthetic Test Requirements v0.1.5

Authority patch: v0.1.5.4 HumanFactUsageKind erratum candidate; independent audit required; not a freeze declaration.

Status: v0.1.5 remediation-candidate release contract; independent re-audit required. These requirements define offline, release-blocking tests; they are not production code and do not authorize live Synthetic Order Portal access.

## 1. Authority, layers, and non-negotiable boundaries

The synthetic suite exists to test rule families that the preserved historical corpus cannot test safely or completely. It supplements history; it never changes historical facts or turns a historical assertion into an oracle. All 213 original historical cases remain mandatory assertion/supporting evidence: 0 executable, 59 human-review, and 154 supporting-only. Their executable denominator remains 0.

Every test record MUST declare exactly one layer:

- `SYNTHETIC_RELEASE_BLOCKING`: wholly fabricated, non-customer fixture data evaluated offline.
- `EXECUTABLE_HISTORICAL`: source facts independently satisfy the complete-whole-order snapshot contract and the expected result is derived from the governing specification.
- `HISTORICAL_ASSERTION_HUMAN_REVIEW`: a source assertion that requires human judgment and MUST NOT be used as a deterministic target.
- `SUPPORTING_ONLY_NOT_REPLAYABLE`: evidence useful for coverage or design but missing facts needed for an executable oracle.

Synthetic cases MUST use the reserved identity prefix `SYN-DOI-` for their harness identities. Under closed `doi-synthetic-identity-firewall/v1`, executable case, order, customer, and product harness identities MUST respectively match `^SYN-DOI-CASE-[A-Z0-9][A-Z0-9-]*$`, `^SYN-DOI-ORDER-[A-Z0-9][A-Z0-9-]*$`, `^SYN-DOI-CUSTOMER-[A-Z0-9][A-Z0-9-]*$`, and `^SYN-DOI-PRODUCT-[A-Z0-9][A-Z0-9-]*$`. A governed `OrderNumber` field remains a canonical positive-decimal string and therefore requires a closed one-to-one, nonserialized harness mapping to an exact allowlisted non-production sentinel; the only published fixed-vector exception in v0.1.5 is `SYN-DOI-ORDER-0001 -> "1"`. The harness scans mappings plus authored, normalized, canonical-vector, generated/built, source-map, and report surfaces before fixture execution or canonical hashing; it rejects generic `case-*`, unregistered/production-looking numeric orders, aliases/case variants, and exact controlled historical-identity matches without reporting the rejected value. It also rejects every conforming synthetic identity at every live-OA transport boundary. No synthetic fixture may contain or be derived from a real customer name, email, phone, VIN, address, Order Number, message body, credential, session datum, persistent customer hash, case identity, or product identity.

Permanent safety invariant: Synthetic Order Portal is read-only. A passing test run has `application_oa_mutation_attempt_count = 0`, `outbound_oa_mutation_request_count = 0`, and no state-changing browser action. A deliberate boundary-probe counter may be nonzero only inside the named negative tests; every probe must be rejected before outbound dispatch and is never application behavior. Tests MUST run with a fake/read-only OA adapter; this document grants no reconnaissance permission.

## 2. Test-harness contract

The harness MUST provide:

1. A deterministic clock and versioned business calendar.
2. A fake manager-sheet source capable of immutable before/after reads and deliberate mid-import changes.
3. A fake OA read adapter that can return complete, incomplete, unreadable, changing, or contradictory observations while recording every attempted method and interaction.
4. An append-only in-memory persistence adapter with uniqueness and immutability constraints enabled.
5. Explicit rules-engine and reason-code-registry versions on every evaluation.
6. Exact-money arithmetic in integer minor units; floating point is forbidden.
7. Event/audit capture sufficient to prove state transitions without retaining forbidden payloads.
8. A purge clock and storage inventory that can prove deletion and retained aggregate/product-knowledge exceptions.
9. A target-leakage guard that prevents historical classification/assertion fields from entering synthetic or historical expected-result calculation.
10. A historical assertion-manifest validator that proves exactly 213 deterministic-order entries, exact 0/59/154 layer reconciliation, immutable source hashes/bytes, valid source references, assertion scope, privacy compliance, and zero promotion into the executable denominator.

All tests below are release-blocking. A skipped, quarantined, flaky, or oracle-less synthetic test is a failed freeze gate.

## 3. Source ingestion requirements

| Test ID | Requirement | Expected contract |
|---|---|---|
| `SYN-SRC-001` | Explicit invocation boundary | Suggestion creates no run/attempt/import/OA read. Accepted invocation immediately creates exactly one run and at least one versioned source-import attempt. The reduced `DOIRun` is exactly `status=IN_PROGRESS` with non-null `started_at` and null `completed_at`, `run_purge_eligible_at`, and initial `source_batch_id`; the invocation event omits completion time. A later same-run attempt uses the next stable positive ordinal and fresh ID; exact same invocation/ordinal bytes replay, while an ordinal gap, changed duplicate, or post-terminal attempt fails before append. |
| `SYN-SRC-002` | Locked schema success | Recognize only the fixed spreadsheet/tab role-title-gid tuples, A1/B1 blanks, E1:G1 sentinels, and A/B rows 2+; no guessed alternative. |
| `SYN-SRC-003` | Locked workbook/tab/anchor/record invariant failure | Any workbook, tab, sentinel, positional, populated-record A value/type, or populated-record B type failure terminalizes the current attempt `SCHEMA_REJECTED` with RC-002/090, null batch, and zero work/cases/evaluations/OA reads. Table-drive an accepted legal next-ordinal retry that leaves the run IN_PROGRESS and a no-retry branch where the final failed attempt drives run `FAILED`. |
| `SYN-SRC-004` | Exact TARGET_REP matching | Scalar-text B values enter TARGET_REP scope iff exact locale-independent `lower(trim(B)) == "TARGET_REP"`; this admits ` TARGET_REP ` and `TARGET_REP` and applies no other normalization. |
| `SYN-SRC-005` | No fuzzy assignee match | Typos, aliases, substrings, and OA rep values such as `target_rep`/`target_rep_web` are out of scope unless the exact manager value normalizes to `TARGET_REP`; zero OA reads result for those rows. |
| `SYN-SRC-006` | Invalid populated source record | A missing/invalid A or non-scalar B on any populated A/B record terminalizes the current attempt `SCHEMA_REJECTED` with RC-002/090 before assignee filtering/hashing; batch/work/case/evaluation are absent, no raw cell/locator persists, and OA reads are zero. Accepted legal retry leaves the run IN_PROGRESS for the next ordinal; without one, that final failed attempt terminalizes the run `FAILED`. |
| `SYN-SRC-007` | Other-rep minimization | Other-rep names/raw assignees/unrelated Order Numbers/rows/locators are absent from staged input, logs, errors, snapshots, and persisted source data. Only allowlisted non-identifying aggregates and the TARGET_REP-order conflict-fingerprint digest/cardinality may survive; unrelated other-rep changes affect neither personal hash. |
| `SYN-SRC-008` | Compatible duplicate rows | TR-099 atomically commits import success plus one READY staged order for two compatible TARGET_REP rows, preserves both deduplicated current-attempt refs, emits RC-006, and exposes no staged order before commit. |
| `SYN-SRC-009` | Out-of-model E:O difference on duplicate TARGET_REP rows | Duplicate TARGET_REP A/B rows share one canonical Order Number but deliberately differ in E:O. Because E:O is outside the source-order row model, TR-099 merges one READY staged order with both refs and RC-006; RC-007/rejected record are absent and execution is not blocked. |
| `SYN-SRC-010` | Assignee conflict identity | Adding/removing a non-TARGET_REP assignment for an existing TARGET_REP Order Number leaves TARGET_REP hash unchanged, changes conflict fingerprint/batch identity, emits RC-008, creates no staged order/work item, retains only the run-local rejection graph, and gives that order zero OA reads. |
| `SYN-SRC-011` | Privacy-relevant fingerprint | Unrelated non-TARGET_REP changes affect neither personal hash; a TARGET_REP-row change affects the TARGET_REP hash. |
| `SYN-SRC-012` | Source-batch reuse without stale staging | Identical privacy-relevant state/schema reuses the batch, but every accepted invocation creates a distinct run/attempt and new attempt-local staged records/source refs from that coherent scan; batch fields and stale locators are never reused. |
| `SYN-SRC-013` | Attempt-scoped order uniqueness | Compatible duplicates in one successful attempt produce one staged record and at most one extraction path per exact Order Number. The key is `(source_import_attempt_id,order_number)`; the same number in a distinct legal attempt ordinal is separately owned and never collides on a run/order key. |
| `SYN-SRC-014` | Cross-run retained identity | Before purge, reappearance of the same exact Order Number in later runs links to the same retained `DOIOrderCase`; no second case/episode is created. |
| `SYN-SRC-015` | Source changed during import | Proven change terminalizes the current attempt `SOURCE_CHANGED` with RC-009/090, no batch/work/case, and zero OA reads. Accepted legal retry leaves the run IN_PROGRESS for the next ordinal; without one, the final failed attempt terminalizes the run `FAILED`. |
| `SYN-SRC-016` | Individual extraction exception | One order extraction failure does not discard successful orders. The run is `COMPLETED_WITH_EXCEPTIONS`; the failed order gets minimal attempt metadata and `RECHECK_REQUIRED`. |
| `SYN-SRC-017` | Named source-attempt failures and final run branch | Table-drive unreadable, schema, proven change, and batch-integrity outcomes. Each terminalizes the current attempt with exact RC-089/002/009/091 plus RC-090, null batch, and zero work/cases/OA reads. Accepted legal retry leaves the run IN_PROGRESS; without one, the final failed attempt drives `RUN_TERMINAL(FAILED)` with the same reasons. |
| `SYN-SRC-018` | Source disappearance | Absence of an active TARGET_REP case from a new batch never closes it. It receives `SOURCE_ABSENT_RECHECK_REQUIRED` and exactly one read-only disappearance verification attempt. |
| `SYN-SRC-019` | Disappearance recheck complete | A complete recheck may establish `SHIPPED`, full `CANCELED`, `REP_TRANSFERRED`, `DEDUPE_CONFIRMED`, or active/TARGET_REP-owned. If still active/TARGET_REP-owned, the same case remains active and is reevaluated from the new complete snapshot. |
| `SYN-SRC-020` | Disappearance recheck incomplete | Incomplete verification creates no snapshot/evaluation and leaves the existing case at `RECHECK_REQUIRED`; source absence alone supplies no closure fact. |
| `SYN-BATCH-REF-001` | Explicit reference owners | One batch with run, coherent attempt, two staged, one rejection, and one case-binding owners has exactly six unique canonical `DOISourceBatchReference` rows with valid FKs/digests; duplicate creation is a no-op. |
| `SYN-BATCH-REF-002` | Nonfinal owner release | Releasing three owners while three remain deletes only due owner/reference graphs; predicate false and the batch bytes/fingerprints remain unchanged. |
| `SYN-BATCH-REF-003` | Exact last-reference release | Releasing the final owner makes TR-113 atomically delete the complete batch identity/fingerprints/identifying derivatives, with no tombstone or reversible hash. |
| `SYN-BATCH-REF-004` | Reused batch lifetimes | Two invocations create independent references; first graph deletion retains the batch and only the final owner across both invocations deletes it. Reuse extends no owner lifetime. |
| `SYN-BATCH-REF-005` | Atomic rollback | Failure at every release/aggregate/predicate/cleanup boundary rolls back all owner/reference/batch/aggregate effects and leaves no orphan or zero-reference batch. |
| `SYN-BATCH-REF-006` | No identifying survivor | After final release, no store/log/cache/export contains source-batch ID/hash, TARGET_REP/conflict fingerprint, order-set digest, predecessor, receipt, tombstone, or lookup key; replay creates nothing. |
| `SYN-BATCH-REF-007` | Safe aggregate survivor | Exactly one closed dimension-keyed import aggregate with expected counts survives and contains no batch/run/attempt/reference/case/order ID, hash, actor, or free text. |

## 4. Extraction, snapshot, evaluation, and line-continuity requirements

| Test ID | Requirement | Expected contract |
|---|---|---|
| `SYN-EXT-001` | Complete whole-order capture and hash determinism | Exact identity plus whole-order proof appends one normalized-source-facts-only snapshot. Table-driven canonical input order matches fixed `doi-line-item-snapshot/v1` and `doi-order-snapshot/v1` hash vectors; any missing/extra/omitted-null/wrong-domain/tampered line or snapshot member rejects the whole snapshot and appends no evaluation. |
| `SYN-EXT-002` | Missing exact identity | Missing or ambiguous order identity is extraction failure: no snapshot, no evaluation, minimal `DOIExtractionAttempt`, and `RECHECK_REQUIRED`. |
| `SYN-EXT-003` | Incomplete line capture | Missing proof of whole-order line completeness is extraction failure, not `UNKNOWN`; no snapshot or evaluation is created. |
| `SYN-EXT-004` | Unreadable required source | A required field/section that could not be observed is extraction failure, not `UNKNOWN`. Named selector `[ETA_MISSING_OR_UNREADABLE]` emits existing extraction-failure reasons, never RC-115, creates no snapshot/evaluation, and never substitutes a stale ETA. |
| `SYN-EXT-005` | Availability-specific UNKNOWN | A complete active one-line fixture has successfully observed but unnormalizable availability, known `NON_DS`, known ETA, quantity, and value, and no other opportunity. Emit exact `{RC-016}`, with RC-017/115 absent; preserve exact `full_order_value`; make availability-dependent outputs unavailable; route TR-037 to `DOI_MANUAL_REVIEW`. Missing/unreadable data is not this branch, and any raw hint is field-allowlisted, bounded, and non-sensitive. |
| `SYN-EXT-006` | Exactly two governed UNKNOWN selectors | `[ETA_UNKNOWN]`: a complete active `DOMESTIC_STANDARD` two-line fixture has known non-DS and availability/quantity/value facts, one `IN_STOCK/FULL` line, and one `DELAYED/NONE` line whose ETA is observed but unnormalizable. Emit exact `{RC-031,RC-052,RC-115}` with RC-016/017 absent; TR-034 preserves `DOI_OPPORTUNITY`, `FULFILLMENT_SPLIT_CANDIDATE`, and exact `available_to_ship_value`, while `supported_eta_delay_impact` alone is `UNAVAILABLE`; infer no date, lead time, state, stale ETA, or extraction failure. `[DS_UNKNOWN]`: a complete active one-line fixture has known ETA, `IN_STOCK/FULL` availability, quantity, and value, but observed unnormalizable DS. Emit exact `{RC-017}` with RC-016/115 absent; TR-037 yields `DOI_MANUAL_REVIEW`, preserves exact `full_order_value`, and blocks every DS-dependent classification/value; infer no extraction failure. Both selectors permit only bounded field-allowlisted non-sensitive raw hints. |
| `SYN-EXT-007` | No stale inheritance | A newer snapshot omitting/changing a dynamic OA fact never inherits the older value. It either records the current normalized fact/`UNKNOWN` or fails extraction if the source was not readable. |
| `SYN-EXT-008` | Successful recheck clear and immutable append | After failed/incomplete extraction sets cause-keyed RECHECK_REQUIRED, the first complete Recheck Order performs exact TR-024 present -> cleared, appends snapshot/evaluation, and preserves every other cause; a second success appends again without a spurious clear. Prior records are byte/field immutable. |
| `SYN-EXT-009` | Evaluation separation | Classifications, values, reason codes, flags, and recommendations appear only in `DOIEvaluation`, not in `DOIOrderSnapshot`. |
| `SYN-EXT-010` | Rules-version replay | Re-evaluating the same snapshot under a new rules version appends a new evaluation linked to the same snapshot; the old evaluation is unchanged. |
| `SYN-LINE-001` | Stable continuity despite row movement | Line continuity is established from deterministic source identity, not row position; reordered rows retain correct lineage. |
| `SYN-LINE-002` | Repeated product identity | Repeated identical product references are not treated as quantities, alternates, or continuity proof without the required deterministic line identity. |
| `SYN-LINE-003` | Ambiguous split/merge lineage | Ambiguous cross-snapshot mapping records `LINE_CONTINUITY_UNVERIFIED` and blocks intervention, reversal, and value conclusions that depend on lineage. Independent case-level conclusions may still proceed. |

## 5. Core DOI classification and calculation requirements

| Test ID | Requirement | Expected contract |
|---|---|---|
| `SYN-RULE-001` | Full DS | A complete synthetic snapshot with all relevant lines explicitly DS produces `DOI_EXCLUDED` with `FULL_DS`; available-to-ship value is zero. This is a synthetic oracle, not a historical frozen label. |
| `SYN-RULE-002` | Mixed DS | At least one DS line and at least one non-DS line remains actionable: `DOI_OPPORTUNITY` includes `DS_SEPARATION_REQUIRED`; it is never excluded merely because DS is present. |
| `SYN-RULE-003` | Fulfillment split | Explicit non-DS `IN_STOCK` plus explicit non-DS delayed content in the same complete snapshot produces `DOI_OPPORTUNITY` with `FULFILLMENT_SPLIT_CANDIDATE`. |
| `SYN-RULE-004` | Overlapping opportunities | A mixed-DS order that also meets the non-DS split rule emits both atomic opportunity outputs in one case/evaluation without duplicate case creation. |
| `SYN-RULE-005` | Explicit in-stock value only | Available-to-ship value includes only explicitly OA-normalized `IN_STOCK` line quantity/value. DS, delayed, payment state, unknown, and full-order total do not contribute. |
| `SYN-RULE-006` | Partial quantity arithmetic | For ordered quantity 5, explicitly available quantity 2, and exact unit value 10,000 minor units, `partial_available_value` is exactly 20,000 and `PARTIAL_QTY_INTERVENTION_REVIEW` is emitted. The line is not automatically placed in a split and contributes zero to the normal fully-split-eligible `available_to_ship_value`. |
| `SYN-RULE-007` | Partial quantity missing inputs | If ordered quantity, available quantity, or unit value needed by the calculation is missing/unreadable, the monetary output is unavailable/not replayable; no estimate or full-order-total substitution is allowed. |
| `SYN-RULE-008` | Initial monitor plus reviewed progress | Table-drive (a) a first complete active valid condition with no opportunity/blocking uncertainty, which directly takes TR-038 NONEXISTENT -> `DOI_MONITOR` with an accepted empty reason set, and (b) an all-in-stock case that first becomes `DOI_MANUAL_REVIEW` + `ORDER_PROGRESS_REVIEW` and then takes TR-039 to `DOI_MONITOR` + `NO_ACTION_REQUIRED` after exact human normal-progress review. Potential is zero. |
| `SYN-RULE-009` | Payment-only block | A complete order whose sole impediment is payment produces `DOI_EXCLUDED` with `PAYMENT_ISSUE_OUT_OF_SCOPE` and no product opportunity. |
| `SYN-RULE-010` | Payment plus product opportunity | A genuine product opportunity controls the top-level result; `PAYMENT_ISSUE_PRESENT_OUT_OF_SCOPE` is added and does not suppress the product opportunity. |
| `SYN-RULE-011` | Rep transfer | Verified current rep outside the personal workflow produces the reversible `REP_TRANSFERRED` terminal closure on the existing case; no new case or OA mutation occurs. |
| `SYN-RULE-012` | Cancellation distinction | Pending-cancel text is not full `CANCELED`. Only a verified full cancellation creates the hard terminal closure. |
| `SYN-RULE-013` | Partial line cancellation | A canceled line on an otherwise active order is excluded from current opportunity/value calculations, remains in older audit snapshots, and remaining active lines continue through evaluation. |
| `SYN-RULE-014` | Multi-SKU independent analysis | A complete order with multiple delayed non-DS ES# values receives an independent research state/opportunity set for every delayed line; one line's result does not overwrite another's. |

## 6. Geography requirements

Geography fixtures MUST contain only a normalized test classification, never a synthetic-looking full address that could normalize bad retention behavior.

| Test ID | Requirement | Expected contract |
|---|---|---|
| `SYN-GEO-001` | Complete split-eligible snapshot; contiguous United States | Retain only `DOMESTIC_STANDARD`; emit `DOI_OPPORTUNITY` + `FULFILLMENT_SPLIT_CANDIDATE` + `HUMAN_DECISION_REQUIRED`; emit no AK/HI, international, or geography-driven contact-required code. |
| `SYN-GEO-002` | Complete split-eligible snapshot; Alaska/Hawaii | Retain only `DOMESTIC_SPECIAL_REVIEW`; emit `DOI_OPPORTUNITY` + `FULFILLMENT_SPLIT_CANDIDATE` + `AK_HI_SHIPPING_REVIEW` + `HUMAN_DECISION_REQUIRED`; do not add `CUSTOMER_CONTACT_REQUIRED_BEFORE_SPLIT` solely from this class; retain no address component. |
| `SYN-GEO-003` | Complete split-eligible snapshot; international | Retain only `INTERNATIONAL`; emit `DOI_OPPORTUNITY` + `FULFILLMENT_SPLIT_CANDIDATE` + `INTERNATIONAL_ORDER_REVIEW` + `CUSTOMER_CONTACT_REQUIRED_BEFORE_SPLIT` + `HUMAN_DECISION_REQUIRED`; no address or email/domain proxy is permitted. |
| `SYN-GEO-004` | Complete split-eligible snapshot; geography observed but unclassifiable | Retain `UNKNOWN` plus the independently proven `DOI_OPPORTUNITY` and `FULFILLMENT_SPLIT_CANDIDATE`; block geography-dependent action readiness/contact handling and guess no geography-specific reason. |

These exact downstream outputs are bound to Machine Contract §5.7. The fixture supplies a complete split-eligible order so geography handling is tested without making geography itself create an opportunity.

## 7. WWC and business-day protection requirements

WWC is a structured finding separate from DOI opportunities and realized-credit calculations. The harness MUST inject the authoritative business calendar and protection anchor; wall-clock-day arithmetic is forbidden.

| Test ID | Requirement | Expected contract |
|---|---|---|
| `SYN-WWC-001` | Self finding | Source-grounded self evidence normalizes to the canonical SELF finding with provenance; it is not an opportunity by itself. |
| `SYN-WWC-002` | Other finding | Source-grounded other-rep evidence normalizes to OTHER without retaining the other rep's unrelated order/customer details. |
| `SYN-WWC-003` | Uncertain finding | Conflicting/insufficient evidence normalizes to UNCERTAIN and requires review; it is never guessed as SELF or OTHER. |
| `SYN-WWC-004` | Friday anchor | With no configured holiday, a Friday protection anchor counts Monday, Tuesday, and Wednesday as business days; the weekend contributes zero. |
| `SYN-WWC-005` | Configured holiday | A configured weekday holiday contributes zero and moves the third-business-day boundary by one business day. |
| `SYN-WWC-006` | Before eligibility date | Through the end of the third full SyntheticCo business date, protection remains active. |
| `SYN-WWC-007` | Eligibility boundary | Eligibility begins at `00:00:00` America/New_York on the next SyntheticCo business date after the three full business dates. |
| `SYN-WWC-008` | After boundary | Any later instant on the eligibility date remains outside protection unless a newer qualifying other-rep contact reset the window. |
| `SYN-WWC-009` | Timezone determinism | The same timestamps and calendar version yield the same result regardless of host timezone; the contract timezone is explicit. |

## 8. DEDUPE lifecycle requirements

| Test ID | Requirement | Expected contract |
|---|---|---|
| `SYN-DED-001` | Complete no-solution candidate | One complete analysis with no unresolved/actionable DOI path produces `DEDUPE_CANDIDATE` plus `HUMAN_DECISION_REQUIRED`; replaying the same evaluation derives the same `doi-dedupe-occurrence-v1` identity and appends nothing; it is not a duplicate-order detector and creates no closure. |
| `SYN-DED-002` | Structured approval, human note, then read-only confirmation | Complete approval first atomically records one exact HumanFact plus linked DEDUPE event and stops at awaiting verification. The OA note itself creates no fact. Only a later read-only complete recheck that proves it creates reversible `DEDUPE_CONFIRMED`; OA writes remain zero. |
| `SYN-DED-003` | Recheck unresolved | An incomplete DEDUPE recheck leaves the case `RECHECK_REQUIRED`; it does not close or merge cases. |
| `SYN-DED-004` | Reopen after contradiction | Before purge, later source-grounded evidence that DOI eligibility returned reopens the same retained case, cancels the purge deadline, and preserves retained lifecycle history. |
| `SYN-DED-005` | DEDUPE gate isolation | Any split, DS separation, partial review, exact-SKU improvement, alternate/review, opportunity-concealing unknown, manual identification, active other-rep WWC, or other opportunity blocks `DEDUPE_CANDIDATE`; DEDUPE remains separate from opportunities. |

## 9. Alternate and reusable product-knowledge requirements

| Test ID | Requirement | Expected contract |
|---|---|---|
| `SYN-ALT-001` | Same ES# | Same ES# is the same catalog product and yields `EXACT_SKU_RECHECK`, never an alternate relationship. |
| `SYN-ALT-002` | Different ES# prerequisite | No alternate relationship is created without a verified different ES# candidate identity. |
| `SYN-ALT-003` | Exact MFG/OE | Fixture: One different-ES candidate with exact same MFG/OE, one fixed SYSTEM_VERIFIED source record, and one explicitly included fresh current observation bound to the case/evaluation/opportunity context. Exact oracle: CREATE exactly one ACTIVE `EXACT_MFG` relationship revision with the fixture's exact provenance and exactly one customer-approval-required alternate opportunity. Replay creates zero duplicate relationship/revision/opportunity rows. The fresh observation is included, so the expected result is not conditional. |
| `SYN-ALT-004` | Explicit MFG cross-reference | Fixture: One explicit source-grounded MFG cross-reference, fixed provenance, and one explicitly included fresh current observation. Exact oracle: CREATE exactly one ACTIVE `MFG_CROSS_REFERENCE` relationship revision bound to that exact provenance and exactly one customer-approval-required alternate opportunity. Replay creates no duplicate relationship/revision/opportunity; no hint-only branch exists in this fixture. |
| `SYN-ALT-005` | Explicit supersession | Fixture: One explicit source-grounded MFG supersession with privacy-minimized fitment/source provenance and one explicitly included fresh current observation. Exact oracle: CREATE exactly one ACTIVE `MFG_SUPERSESSION` relationship revision and exactly one customer-approval-required alternate opportunity. Retain only the fixture's privacy-minimized provenance, create no duplicate, and emit no functional-compatibility requirement because this fixture is not functional-alternate evidence. |
| `SYN-ALT-006` | Functional alternate | A different-ES# functional candidate always requires fresh application-specific compatibility review and customer approval before substitution. |
| `SYN-ALT-007` | Customer approval | Every substitution class requires customer approval; research or recommendation alone is not approval. |
| `SYN-ALT-008` | Relationship lifecycle | An ACTIVE relationship remains active when later search fails to rediscover it; only explicit contradictory/superseding evidence changes it to INVALIDATED/SUPERSEDED. |
| `SYN-ALT-009` | Durable reuse | Fixture: A matching future order reuses one existing ACTIVE exact relationship; its current observation is explicitly absent/stale. Exact oracle: REUSE the existing relationship and current revision, create zero duplicate relationships/revisions, and surface exactly one alternate opportunity in `RECHECK_REQUIRED_BEFORE_ACTION`. No substitution-ready/contact-ready state is emitted without a fresh observation. |
| `SYN-ALT-010` | Functional reuse limit | Fixture: A matching future order has one prior product-only functional candidate and no new application/order-specific compatibility approval. Exact oracle: REUSE the prior knowledge only as candidate evidence and surface exactly one `FUNCTIONAL_COMPATIBILITY_REVIEW_REQUIRED` opportunity/review state. Universal compatibility is not inferred and customer substitution remains blocked pending a new application/order-specific human review. |
| `SYN-ALT-011` | Fresh observation required and hash-bound | Contact/substitution requires an observation produced by the explicit current `Recheck Alternate`; its canonical object matches the fixed observation hash across input order and tamper rejects. Durable relationship alone is insufficient. |
| `SYN-ALT-012` | Stale stored observation | An older stored observation not bound to the current explicit recheck context is never current, even if it is less than 90 days old. Freshness is event-scoped, not inferred from an age threshold. |
| `SYN-ALT-013` | Observation purge | Nominal target deletion is exact `calendar90(observed_at)`; a linked-case purge deletes earlier. Target bytes/indexes/volatile wrappers are atomically absent; sealed downstream evaluation/opportunity observation commitments are non-resolvable/non-fresh until case purge; core replay remains exact. Only fully de-linked relationship revisions may survive. |
| `SYN-ALT-014` | Provenance | SYSTEM_VERIFIED and HUMAN_VERIFIED relationships are both representable and their audit provenance is immutable. |
| `SYN-ALT-015` | No verified alternate, including `[EXACT_MFG_SCOPE]` | A completed different-ES/identical-MFG scoped search with no candidate emits exact `{RC-038}` and RC-039 absent. A completed broader supported alternate search with none verified emits `{RC-039}`; RC-038 appears only if the exact-MFG subsearch was separately completed. Blank, failed, unversioned, or missing-candidate search emits neither and cannot prove a negative. |
| `SYN-ALT-016` | Manual identification | Unresolved product identity produces `MANUAL_IDENTIFICATION_REQUIRED`, requires human review, and blocks DEDUPE eligibility without fabricating an ES#/MFG relationship. |
| `SYN-ALT-017` | Mark No Viable Alternate | The explicit human action appends `NO_VIABLE_ALTERNATE_HUMAN_CONFIRMED` for the scoped order line, never writes OA, and does not invalidate durable product knowledge without contradictory evidence. |

Observation freshness is satisfied only by an explicit current recheck context. The 90-day storage limit is retention, not a freshness threshold.

## 10. Opportunity, intervention, value, and reversal requirements

| Test ID | Requirement | Expected contract |
|---|---|---|
| `SYN-INT-001` | Opportunity only | Identification or recommendation creates `DOIOpportunity` only; no `DOIIntervention` and no realized credit exist. |
| `SYN-INT-002` | Planned action | A human decision or plan to act creates no intervention. |
| `SYN-INT-003` | System action proof | A recheck that deterministically proves the action creates one SYSTEM_VERIFIED intervention. |
| `SYN-INT-004` | Change without proof | A recheck that detects change but cannot prove causation/action creates verification-required state only; no intervention or realized credit. |
| `SYN-INT-005` | Structured human action proof and replay | Fixture: Submit one complete structured human action proof, replay its byte-identical natural key/evidence fingerprint/payload, then submit a conflicting payload under the same occurrence/natural key. Exact oracle: First submission CREATEs exactly one `DOIIntervention` and one `HUMAN_VERIFIED` action-verification event bound to the exact evidence fingerprint. Exact replay REUSEs that intervention/result and creates zero additional intervention, verification, credit-bearing, or KPI effects. The conflicting payload fails closed under the governed integrity route and leaves all prior bytes/counts unchanged. |
| `SYN-INT-006` | Action/value independence | Verified action with unverified value remains a completed intervention; current realized monetary contribution is zero. |
| `SYN-INT-007` | Exact human value | Human-verified realized value accepts only an exact known integer-minor-unit amount; estimates/ranges are rejected as verified values. |
| `SYN-INT-008` | Estimated value | Estimated or unverified money contributes zero to Net Realized DOI Credit and Gross Verified Credit. |
| `SYN-INT-009` | System value override | Later conflicting SYSTEM_VERIFIED money becomes authoritative for current KPIs while both system and earlier human evidence remain in immutable history. |
| `SYN-INT-010` | Non-conflicting evidence | Consistent human and system evidence does not create a second intervention or double-count value. |
| `SYN-INT-011` | Partial reversal | Credited merchandise partially removed/canceled changes status to `PARTIALLY_REVERSED`; `net_realized_value = original_realized_value - reversed_value`, with all amounts exact and nonnegative. |
| `SYN-INT-012` | Full reversal | Reversal equal to original changes status to `REVERSED` and net value to zero. Reversal above original fails closed. |
| `SYN-INT-013` | Zero active reversal after correction/void | Original 100,000, accepted reversal 30,000, then exact predecessor-bound void (and separately a correction yielding zero active sum) directly takes TR-049 to `VERIFIED`, reversed 0, net 100,000; TR-052 invokes TR-109 in the original action-day bucket and old events remain. A zero-valued new `REVERSAL_VERIFIED` is rejected. |
| `SYN-INT-014` | Headline/supporting KPIs | Net Realized DOI Credit is headline; Gross Verified Credit and Reversed Credit are separately retained aggregate analytics. |
| `SYN-INT-015` | Case reopen | Before purge, reopening the same retained case never recreates or recounts prior intervention value. New credit requires a distinct newly verified intervention identity. |
| `SYN-INT-016` | Resulting-order identity | A permitted resulting-order link is explicit, provenance-bearing, and idempotent; it never implies customer approval or value verification by itself. |
| `SYN-INT-017` | Split credit proof | Table-drive verified exact resulting-order link plus resulting order-level Sales Rep proof. Missing/different/ambiguous rep proof preserves the one intervention and exact link, leaves value `UNVERIFIED`, produces zero realized split credit and one count-1 zero-money row for exact-date/valid-currency input, and emits exactly `{RC-063,RC-074}` with RC-075 absent. Exact verified TARGET_REP rep makes both RC-074 and RC-075 absent and permits the separately verified exact split-value path. |
| `SYN-INT-018` | Swap credit proof | Table-drive exact replacement-line identity/value plus replacement line-level Sales Rep proof. Missing/different/ambiguous line proof—including verified parent-order rep alone—preserves the one intervention/binding, leaves value `UNVERIFIED`, produces zero realized swap credit and one count-1 zero-money row for exact-date/valid-currency input, and emits exactly `{RC-063,RC-075}` with RC-074 absent. Exact verified TARGET_REP line proof makes both codes absent and permits the separately verified exact swap-value path. |
| `SYN-INT-019` | Search/exact-link resolution separation | Table-drive (a) search NOT_FOUND/AMBIGUOUS followed by exact human proof, where search history remains and TR-055 creates one HUMAN_CONFIRMED exact link/revision 1, and (b) an existing exact link AMBIGUOUS followed by TR-057/TR-110 verified revision n+1. Only the exact review cause clears; neither branch implies customer approval or value. |
| `SYN-INT-020` | Complete contact transition/idempotency table | Table-drive every legal edge TR-065–073, TR-080, and TR-081 with exact states/type/provenance/context/occurrence ID. TR-065 is derived SYSTEM with null contact time/exact evaluation; actual contact is HUMAN with exact time. Same occurrence/bytes replays, mutation rejects, and fresh IDs append all TR-080 re-contact edges. No edge creates an intervention, sends communication, or writes OA. |
| `SYN-INT-021` | Verified DS separation | Deterministic or exact human proof creates one verified `DS_SEPARATION` intervention with value `NOT_APPLICABLE`, all money/currency fields null, zero retained/realized KPI contribution, and no RC-063. |

## 11. Closure, reopening, retention, and privacy requirements

| Test ID | Requirement | Expected contract |
|---|---|---|
| `SYN-RET-001` | Queue exit is not retention anchor | Leaving an actionable queue without terminal closure creates no purge deadline. |
| `SYN-RET-002` | Hard closure deadline | Verified `SHIPPED` or full `CANCELED` schedules detailed case purge at exact `calendar90(most_recent_verified_terminal_transition)` under the bound New York policy/tzdb versions. |
| `SYN-RET-003` | Reversible closure deadline | `REP_TRANSFERRED`, `DEDUPE_CONFIRMED`, or explicit human out-of-scope closure schedules exact `calendar90(most_recent_verified_terminal_transition)` under the same bound policy/tzdb and remains reopenable only while its detailed identity exists before purge. |
| `SYN-RET-004` | Reopen cancellation | Before purge, `CASE_REOPENED` and atomic `PURGE_CANCELED` each carry the complete explicit `PriorClosureRetentionBindingV1` copied byte-for-byte from the locked authoritative prior closure event/projection, including the governing source/evidence identity. The canceled deadline equals the binding's active prior deadline; the same case becomes ACTIVE with null closure/deadline. Missing, hash-only/inferred, or byte-different binding rejects before append and leaves the prior state unchanged. |
| `SYN-RET-005` | Reversible-to-hard branches | Table-drive a retained CLOSED_REVERSIBLE case later proved (a) SHIPPED and (b) fully CANCELED. Direct TR-016 and TR-017 each append CLOSED_HARD with the exact reason/event and start a new `calendar90` countdown from that later transition. |
| `SYN-RET-006` | Purge boundary owners | Table-drive CLOSED_HARD and not-reopened CLOSED_REVERSIBLE immediately before/at the deadline. Details remain before; at the deadline direct TR-018/TR-019 respectively invoke mandatory TR-112 and delete exactly once. |
| `SYN-RET-007` | Post-purge deletion | No per-order archive, reconstructable order/customer identity, snapshots, evaluations, lifecycle details, or source references survive purge. |
| `SYN-RET-008` | Aggregate exception | Non-identifying aggregate KPI history survives indefinitely and cannot be joined back to an order/customer. |
| `SYN-RET-009` | Product-knowledge exception | Verified reusable product relationships survive only as completely de-linked product knowledge; case/order links do not. |
| `SYN-RET-010` | Alternate rolling retention | Nominal target deletion is exact `calendar90(observed_at)`; effective linked deletion is the earlier current case purge. A canceled case deadline after reopen does not delete. Target and volatile wrapper streams delete together; sealed downstream commitments remain unusable until case purge, while core replay remains identical. Durable relationship survival requires complete de-linking. |
| `SYN-RET-011` | Same Order Number returns after purge | After the original case is purged, a later fictional input bearing the same Order Number finds no retained case identity and follows the ordinary `NONEXISTENT → ACTIVE` path: create a new `DOIOrderCase` with a new case ID; create no predecessor/reopen link; perform no tombstone/hash/archive lookup; make no cross-purge deduplication claim. The deleted graph remains absent. |
| `SYN-RET-012` | Credit correction after purge | At purge, the case's then-current exact gross/reversed/net contribution is atomically finalized into non-identifying aggregate history before the entire per-order graph is deleted. A later reversal or system-over-human correction cannot resolve a retained case/intervention, is rejected with `CASE_IDENTITY_NOT_RETAINED`, appends no per-case event, changes no finalized aggregate, and leaves no order-specific rejection record. |
| `SYN-PRV-001` | Active-case allowlist | Persisted case detail is limited to the governing operational allowlist: exact Order Number; source/run refs; assigned/current rep; line ES#/MFG#/qty/value; inventory/ETA/DS facts; DOI states/flags; structured WWC/DEDUPE; intervention/credit values; timestamps; geography class; resulting-order links. |
| `SYN-PRV-002` | Permanent denylist | Customer name/email/phone/VIN/full address/full note bodies/persistent customer hashes/full HTML/DOM dumps/screenshots/page copies never appear in persistence, logs, traces, errors, caches, fixtures, or audit exports. |
| `SYN-PRV-003` | Narrow raw values | Only structured non-sensitive raw values necessary to explain normalization may be retained; surrounding page/text context is discarded. |
| `SYN-PRV-004` | Other-rep erasure | Transient other-rep names/raw assignees/unrelated Order Numbers/rows/locators are absent after filtering; only allowlisted non-identifying aggregates plus the TARGET_REP-order conflict-fingerprint digest/cardinality survive. |

## 12. Permanent OA read-only negative requirements

| Test ID | Requirement | Expected contract |
|---|---|---|
| `SYN-OA-RO-001` | Network methods and unsafe runtime requests | Table-drive runtime user/API `POST|PUT|PATCH|DELETE`, GraphQL mutation/write RPC, generic mutation-capable action/click request, background poll, and unallowlisted side-effectful read. Every branch rejects before dispatch with exact `{RC-083}` and no RC-082; OA mutation, DOI append/persistence, and dispatched network effects remain zero beyond the local blocked-probe observation. |
| `SYN-OA-RO-002` | UI mutation controls | Submit/save/cancel/refund/transfer/edit/note/customer/shipment/payment mutation controls are never clicked or invoked. |
| `SYN-OA-RO-003` | Closed structural capability surface | Alias-aware inspection of source/dependencies, manifest fragments/final manifest, host/optional permissions, background/service worker, content scripts, registries, wrappers/computed access, source maps, and built output matches `doi-oa-capability-policy/v1` with zero findings. A forbidden `click` helper or equivalent write-capable module/manifest capability fails packaging before runtime with exact RC-082 and no RC-083, with zero OA/state/persistence/browser/network effect. |
| `SYN-OA-RO-004` | User actions stay read-only | Run Review, Recheck Order, Recheck Alternate, human action/value verification, Mark No Viable Alternate, and Recheck DEDUPE mutate DOI-local state only and emit zero OA writes. |
| `SYN-OA-RO-005` | Fail closed on read-only breach | Fault-inject each RC-083 canonical runtime branch: mutation request, generic action/click request, background poll, and unallowlisted side-effectful read. Each aborts before dispatch with exact `{RC-083}` and no RC-082, emits only a sanitized local failure, and commits no DOI state/persistence/result or OA/network side effect beyond the blocked probe. |
| `SYN-OA-RO-006` | Host allowlist and redirects | Read adapter rejects a redirect or request to an unapproved write-capable/non-OA host; credentials/session data never enter logs. |
| `SYN-OA-RO-007` | Adversarial source text | Sheet cells, OA text, and alternate-research text that look like instructions cannot trigger navigation or mutation outside the fixed read-only extraction plan. |
| `SYN-OA-RO-008` | Synthetic/live separation and complete positive identity scan | Scan every authored/normalized/canonical/generated/built executable synthetic case/order/customer/product identity, including both lifecycle vectors, under `doi-synthetic-identity-firewall/v1`; require zero namespace and historical-identity findings. Then offer one conforming `SYN-DOI-*` identity to the OA boundary and reject it before network/navigation dispatch, proving synthetic tests cannot become OA reconnaissance. |
| `SYN-OA-RO-009` | Non-prefixed/historical synthetic identity rejection | Inject `case-0001` into executable `case_id`, then table-drive an unregistered production-looking numeric Order Number, missing/non-bijective order mapping, unprefixed customer/product identity, lowercase/alias prefix, and one exact controlled historical-identity canary. Each failure occurs before fixture execution, canonical serialization/hash, reducer/adapter construction, dispatch, or promotion; the positive mapping `SYN-DOI-ORDER-0001 -> "1"` validates. Failure output contains only `SYNTHETIC_IDENTITY_NAMESPACE_VIOLATION` plus identity class, with zero append/projection/OA activity and no persisted rejected value. |
| `SYN-OA-CAP-001` | Manifest capability denylist | Every prohibited permission/member, wildcard/broad/OA host, optional permission, external messaging, background/service-worker, and content-script form fails; the one exact empty closed projection passes. No OA/network/browser activity occurs. |
| `SYN-OA-CAP-002` | Helper alias/wrapper denylist | Every forbidden `click`/input/mutation helper is detected through direct, renamed, re-exported, computed, wrapped, registry, callback, reflected, and minified forms; unresolved dynamic dispatch also fails with exact RC-082 and no RC-083 before invocation/package promotion and with zero state/network effect. |
| `SYN-OA-CAP-003` | Built-output mutation canaries | Canary insertion into dependency, source, generated bundle, and source map is detected on its exact surface; promotion fails, network remains denied, and all OA counters are zero. |
| `SYN-OA-CAP-004` | Closed fixture-only positive surface | Exact pure fixture parsing/normalization/rule evaluation produces one PASS scan with unchanged input hash and empty mutation journal; any extra capability deterministically produces FAIL. |

## 13. Release gate and evidence

A release candidate passes this suite only when:

- all 312 listed synthetic tests across 29 ID families have deterministic executable offline oracles and pass; skipped, quarantined, flaky, or oracle-less rows fail release;
- the expected result is traceable to the exact versioned remediation-candidate machine-contract clause and reason-code-registry version;
- no test relies on a historical classification/assertion as target truth;
- all immutable, uniqueness, provenance, money, privacy, retention, and zero-OA-mutation assertions pass;
- WWC date boundaries, event-scoped alternate freshness, geography handling, all-in-stock review, payment precedence, partial-quantity containment, and canonical reason/state names agree with the governing artifacts;
- `SYN-RET-011` proves post-purge new-case/no-link behavior and the explicit absence of cross-purge duplicate-credit guarantees;
- `SYN-RET-012` proves aggregate finality and rejection of unjoinable late correction without reconstructable retained identity;
- all 213 historical records appear exactly once in `HISTORICAL_DOI_ASSERTION_MANIFEST_v0.1.jsonl`, immutable corpus bytes/hashes remain unchanged, all source references validate, and privacy lint passes;
- historical counts reconcile exactly to 0 executable, 59 human-review, and 154 supporting-only, with all 213 marked against complete-whole-order-oracle use;
- no unsupported source fact or incomplete-data negative is promoted; no historical target leaks into an executable fixture or expected result; and no non-replayable case enters the executable denominator;
- every synthetic rule family records whether related real-world evidence exists, supporting historical case/source references, assertion/supporting layer, and structural-inspiration status, plus an attestation that no real order/customer identity or historical expected target was copied.

The historical assertion checks above are additional release gates, not additional `SYN-*` IDs, and therefore do not change the **312-test** synthetic total. A historical execution denominator of 0 is not itself a failure. Historical coverage cannot waive a failed or missing synthetic release-blocking test.

## 14. v0.1.5 remediation oracle incorporation

The exact fixture/action/oracle rows in `source_retention_contract.md` section 10, `provenance_state_contract.md` section 10, `opportunity_kpi_contract.md` section 7, and `DOI_LIFECYCLE_EVENT_PAYLOAD_REGISTRY_v0.1.5.md` section 8 are incorporated verbatim into this requirements artifact. Each ID below is one separate required deterministic test; its module row is the exact oracle, not optional commentary. The direct `SYN-BATCH-REF-*` and `SYN-OA-CAP-*` rows above are equally authoritative.

`SYN-SRC-021` `SYN-SRC-022` `SYN-SRC-023` `SYN-SRC-024` `SYN-SRC-025` `SYN-SRC-026` `SYN-SRC-027` `SYN-SRC-028` `SYN-SRC-029` `SYN-SRC-030` `SYN-SRC-031`  
`SYN-CUR-001` `SYN-CUR-002` `SYN-CUR-003` `SYN-CUR-004` `SYN-CUR-005` `SYN-CUR-006`  
`SYN-RET-013` `SYN-RET-014` `SYN-RET-015` `SYN-RET-016` `SYN-RET-017` `SYN-RET-018` `SYN-RET-019` `SYN-RET-020`  
`SYN-EVAL-PROV-001` `SYN-EVAL-PROV-002` `SYN-EVAL-PROV-003` `SYN-EVAL-PROV-004` `SYN-EVAL-PROV-005` `SYN-EVAL-PROV-006` `SYN-EVAL-PROV-007` `SYN-EVAL-PROV-008`  
`SYN-ALT-REV-001` `SYN-ALT-REV-002` `SYN-ALT-REV-003` `SYN-ALT-REV-004` `SYN-ALT-REV-005` `SYN-ALT-REV-006` `SYN-ALT-REV-007` `SYN-ALT-REV-008`  
`SYN-ACTX-001` `SYN-ACTX-002` `SYN-ACTX-003` `SYN-ACTX-004` `SYN-ACTX-005` `SYN-ACTX-006` `SYN-ACTX-007` `SYN-ACTX-008`  
`SYN-STATE-001` `SYN-STATE-002` `SYN-STATE-003` `SYN-STATE-004` `SYN-STATE-005` `SYN-STATE-006` `SYN-STATE-007` `SYN-STATE-008` `SYN-STATE-009` `SYN-STATE-010` `SYN-STATE-011` `SYN-STATE-012` `SYN-STATE-013` `SYN-STATE-014` `SYN-STATE-015` `SYN-STATE-016` `SYN-STATE-017`  
`SYN-DED-006` `SYN-DED-007` `SYN-DED-008`  
`SYN-LINK-HIST-001` `SYN-LINK-HIST-002` `SYN-LINK-HIST-003` `SYN-LINK-HIST-004` `SYN-LINK-HIST-005` `SYN-LINK-HIST-006` `SYN-LINK-HIST-007` `SYN-LINK-HIST-008`  
`SYN-INT-HIST-001` `SYN-INT-HIST-002` `SYN-INT-HIST-003` `SYN-INT-HIST-004` `SYN-INT-HIST-005`  
`SYN-PURGE-EDGE-001` `SYN-PURGE-EDGE-002` `SYN-PURGE-EDGE-003` `SYN-PURGE-EDGE-004`  
`SYN-OA-RO-PROV-001` `SYN-OA-RO-PROV-002`  
`SYN-SCOPE-001` `SYN-SCOPE-002` `SYN-SCOPE-003` `SYN-SCOPE-004` `SYN-SCOPE-005` `SYN-SCOPE-006` `SYN-SCOPE-007` `SYN-SCOPE-008` `SYN-SCOPE-009` `SYN-SCOPE-010`  
`SYN-KPI-001` `SYN-KPI-002` `SYN-KPI-003` `SYN-KPI-004` `SYN-KPI-005` `SYN-KPI-006` `SYN-KPI-007` `SYN-KPI-008` `SYN-KPI-009` `SYN-KPI-010` `SYN-KPI-011` `SYN-KPI-012` `SYN-KPI-013` `SYN-KPI-014` `SYN-KPI-015` `SYN-KPI-016` `SYN-KPI-017` `SYN-KPI-018` `SYN-KPI-019`  
`SYN-IDEM-001` `SYN-IDEM-002` `SYN-IDEM-003` `SYN-IDEM-004` `SYN-IDEM-005` `SYN-IDEM-006` `SYN-IDEM-007` `SYN-IDEM-008` `SYN-IDEM-009` `SYN-IDEM-010` `SYN-IDEM-011` `SYN-IDEM-012`

`SYN-LIFE-PAYLOAD-001` `SYN-LIFE-PAYLOAD-002` `SYN-LIFE-PAYLOAD-003` `SYN-LIFE-PAYLOAD-004` `SYN-LIFE-PAYLOAD-005` `SYN-LIFE-PAYLOAD-006` `SYN-LIFE-PAYLOAD-007` `SYN-LIFE-PAYLOAD-008` `SYN-LIFE-PAYLOAD-009` `SYN-LIFE-PAYLOAD-010` `SYN-LIFE-PAYLOAD-011` `SYN-LIFE-PAYLOAD-012`

The Round-3 parameter inventory below is mandatory within those existing lifecycle IDs and does not add IDs:

| Required branch | Owning test | Deterministic fixture and expected result |
|---|---|---|
| V1 identity regeneration | `SYN-LIFE-PAYLOAD-002` | Use actual canonical `case_id=SYN-DOI-CASE-0001` and harness mapping `SYN-DOI-ORDER-0001 -> order_number "1"`; CASE_CREATED binds `CASE_SOURCE_ADMISSION_PROOF`/`doi-case-source-admission-proof/v1`, never staged detail. Reproduce stream `26c7b4a8d9d56577240a1c66160d0b921fc380fbe402d3e00ea3a34b8cd141f1`, payload `c9213e527d8132e2c72cff86337e9692156dfb45c62886b4869265c25eebf2a8`, projection `a739d6ce2fc0db47c6f232cfa29fa750a4f5ec95b6029b01991c92802d5b7e27`, case-source binding `e39a40adfeb2b606981364928e38bb867a20f6349e0b2a734e82d0c17bceb2f3`, admission-proof ID/logical occurrence `e2aa8e7b7fe795821d230ede3d731c79f8670718e277d8d0812f1a83df97636e`, proof hash `2e9ac63cf8d5cda713e46351f4c8e8ce83429c2e39f35142113fd54da15f53b8`, natural `a8feba67a425e50f0a584a14336f4a3290a5f3de104cc0f86fb6ab2d34e3cb90`, and envelope `0baab70132263d66f67582425bbf6d6c227ebb5c10317ea124babf5aee70c257`. Former staged-record binding or a stale dependent hash fails. |
| V2 identity regeneration | `SYN-LIFE-PAYLOAD-003` | Use actual canonical `case_id=SYN-DOI-CASE-0002`; reproduce stream `7bca825060be4f0e80f71627168b8b68461703e1ae8fc97832f08268b43b024d`, payload `19ac1831b3a17883afd957810d725bd9a8c86a6ff7a6b42dc62e45adbc3e3dd4`, projection `d99c4ce97e398adb7521f580e00893110b69bc56daeb6a28ef58d3da14e95198`, natural `1ab0fb29b3d6f067aaa00a10b32844d73a224c371e6bff55297c9a5bc4a0568d`, and envelope `1bf19ddbbd4b108617d52d349ceec5ba950947f5a587d7784b4082d88a0f4b36` from the published deadline/bytes. Former identity, stale hash, or fixed-elapsed calendar arithmetic fails. |
| 1. Valid reopen | `SYN-LIFE-PAYLOAD-004` | For each legal reversible closure branch, lock the authoritative pre-event state, copy its complete `PriorClosureRetentionBindingV1` including source/evidence identity into `CASE_REOPENED`, and obtain the exact registered ACTIVE projection. |
| 2. Valid purge cancellation | `SYN-LIFE-PAYLOAD-004` | In the same atomic bundle, copy the identical complete binding into `PURGE_CANCELED`; require `canceled_purge_eligible_at == prior_closure_retention_binding.prior_purge_eligible_at == locked_active_deadline` and a null resulting deadline. |
| 3. Prior closure kind mismatch | `SYN-LIFE-PAYLOAD-005` | Mutate only `prior_closure_kind`; RC-113 before append, no event, byte-identical prior state. |
| 4. Classification mismatch | `SYN-LIFE-PAYLOAD-005` | Mutate only `prior_closure_classification`; same fail-closed result. |
| 5. Verified instant mismatch | `SYN-LIFE-PAYLOAD-005` | Mutate only `prior_verified_closure_at`; same fail-closed result. |
| 6. Policy ID/version mismatch | `SYN-LIFE-PAYLOAD-005` | Independently mutate `prior_retention_policy_id` and `prior_retention_policy_version`; each has the same fail-closed result. |
| 7. Timezone mismatch | `SYN-LIFE-PAYLOAD-005` | Replace exact `America/New_York`; same fail-closed result. |
| 8. tzdb mismatch | `SYN-LIFE-PAYLOAD-005` | Mutate only `prior_tzdb_version`; same fail-closed result. |
| 9. Local-calendar-rule mismatch | `SYN-LIFE-PAYLOAD-005` | Mutate only `prior_local_calendar_rule_id`; same fail-closed result. |
| 10. Purge-deadline mismatch | `SYN-LIFE-PAYLOAD-005` | Independently mutate binding deadline and cancellation deadline; any disagreement with each other or locked active deadline has the same fail-closed result. |
| 11. Projection revision/hash mismatch | `SYN-LIFE-PAYLOAD-005` | Independently mutate `prior_closure_projection_revision` and `prior_closure_projection_hash`, then point to a nonexistent revision/hash; each has the same fail-closed result. |
| 12. Hash-only inference attempt | `SYN-LIFE-PAYLOAD-005` | Omit the explicit binding but retain the prior projection hash, then attempt reconstruction from that hash; both reject before persistence. |
| 13. Universal rollback | `SYN-LIFE-PAYLOAD-005` | Delete every required key, null every required-non-null key, populate forbidden/null partitions, add unknown keys, and independently mutate closure source/evidence, reopen proof, cancellation cause ID/hash, resolution source type/ID/schema/hash, same-case/result identity/revision/hash, and reopen-to-cancel nested bytes; every row yields zero append and a byte-identical prior projection/deadline. |
| 14. Exact replay | `SYN-LIFE-PAYLOAD-010` | Replay the accepted close/reopen/cancel stream twice; reproduce identical order, bytes, hashes, resulting revision, ACTIVE projection, and null closure/deadline without inference. |
| 15. Fixed bytes/hashes | `SYN-LIFE-PAYLOAD-010` | With exact V3 `case_id=SYN-DOI-CASE-0003`, independently reproduce the separate top-level serialization bytes and reopen/cancel payload hashes `6550aa6c...dda4ce` / `a0513a13...5fede5` plus full hashes `94e4bd6e...73dff0` / `f434eba5...9976e3`, treating V3's repeated-hex source/predecessor values only as opaque validated serialization inputs. Separately construct actual closed-schema targets/reachable stream, compute their real hashes, and publish/compare that fixture's own expected binding/payload/envelope/projection bytes and hashes; never use V3 as authority-existence proof. |

### 14.1 Round-4 reason ownership and parity family

| Test ID | Deterministic fixture | Exact oracle |
|---|---|---|
| `SYN-REASON-OWN-001` | Split, exact accepted child link, missing/different/ambiguous resulting-order-level TARGET_REP rep, crossed with every accepted date/currency base branch | Exact unions: `{RC-063,RC-074}`, `{RC-063,RC-074,RC-094}`, `{RC-063,RC-074,RC-099}`, `{RC-063,RC-074,RC-094,RC-099}` as applicable; no RC-075. Intervention `UNVERIFIED`, link unchanged, realized split zero; row/no-row and invalid-Money behavior follow the base table. |
| `SYN-REASON-OWN-002` | Split verified-TARGET_REP-rep control, RC-075 swap cross-condition, and unrelated branch across every accepted date/currency base; separate contradictory both-code/wrong-type/schema branch | Control/unrelated retain each exact applicable base with neither modifier. Swap unions RC-075 with every base and keeps RC-063 mandatory: `{RC-063,RC-075}`, `{RC-063,RC-075,RC-094}`, `{RC-063,RC-075,RC-099}`, or `{RC-063,RC-075,RC-094,RC-099}`; no RC-074. Contradiction is RC-081 before TR-106/no append, distinct from accepted invalid-currency RC-094 branch. |
| `SYN-REASON-OWN-003` | Substitution with missing/different/ambiguous replacement line-level TARGET_REP rep (including parent-only proof), crossed with every accepted date/currency base branch | Exact unions: `{RC-063,RC-075}`, `{RC-063,RC-075,RC-094}`, `{RC-063,RC-075,RC-099}`, `{RC-063,RC-075,RC-094,RC-099}` as applicable; no RC-074. Intervention `UNVERIFIED`, binding unchanged, realized swap zero; row/no-row follows base table. |
| `SYN-REASON-OWN-004` | Swap verified-TARGET_REP-line control, RC-074 split cross-condition, and unrelated branch across every accepted date/currency base; separate contradictory both-code/wrong-type/schema branch | Control/unrelated retain each exact applicable base with neither modifier. Split unions RC-074 with every base and keeps RC-063 mandatory: `{RC-063,RC-074}`, `{RC-063,RC-074,RC-094}`, `{RC-063,RC-074,RC-099}`, or `{RC-063,RC-074,RC-094,RC-099}`; no RC-075. Contradiction is RC-081 before TR-106/no append; accepted invalid currency remains RC-094 base. |
| `SYN-REASON-OWN-005` | Forbidden `click`/equivalent write-capable build capability | Exact `{RC-082}`, no RC-083; reject before runtime/package promotion; zero OA/state/persistence/network effect. |
| `SYN-REASON-OWN-006` | Clean closed capability registry and allowlisted static-fixture action plus every canonical runtime user/API negative control | Clean/allowed rows emit neither. Each mutation/POST-write-RPC, generic action/click, background-poll, and unallowlisted side-effectful-read request emits exact `{RC-083}` only and no RC-082; every negative row fails before dispatch with zero DOI append/persistence, OA mutation, or network side effect beyond the local blocked-probe observation. |
| `SYN-REASON-OWN-007` | Table-drive runtime mutation, generic action/click, background-poll, and unallowlisted side-effectful-read requests | Each exact `{RC-083}`, no RC-082; reject before dispatch; zero OA/state/persistence/network effect beyond local blocked-probe observation. |
| `SYN-REASON-OWN-008` | Allowlisted DOI-local/read-only request plus separate forbidden static capability and every RC-083 runtime branch | Clean emits neither; static forbidden capability exact `{RC-082}` only; each runtime unsafe branch exact `{RC-083}` only; no cross-emission/side effect. |
| `SYN-REASON-OWN-009` | Parse reason registry, `doi-reason-ownership/v1`, transitions, and all oracle references; table-drive known fields plus availability, DS, ETA, availability+ETA, DS+ETA, and all-three UNKNOWN field combinations, including `[ETA_BLOCKS_ALL]` where ETA uncertainty blocks every safe order-level conclusion; inject unknown code/version and stale 0.1.5.2 binding | 115/115 external ownership; no undefined, orphan, duplicate, or implicit alias; every referenced/emitted code exists and every code has an asserting oracle. A known ETA emits no RC-115. Exact field mapping is availability `{RC-016}`, DS `{RC-017}`, ETA `{RC-115}`, with set union only for independent multiple unknowns. `[ETA_BLOCKS_ALL]` emits RC-115 and routes TR-037; TR-034 is forbidden without an independently proved split. Cross-field substitution, missing/extra reasons, unknown code/version, or stale binding fails before persistence. |
| `SYN-REASON-OWN-010` | Normalize/compare exhaustive reason sets across all governing artifacts, explicitly including the provenance/state contract and persistence model | Exact parity for TR-106 base unions/modifiers and OA partitions across the technical, machine, provenance, persistence, opportunity/KPI, OA, transition, traceability, acceptance/synthetic, handoff, registry, and ownership artifacts. Any extra/missing/swapped code, unversioned alias, or stale pre-Round-4 ownership/count claim fails release. |

### 14.2 Round-4 source-import-attempt retention family

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

The complete merged unique inventory is exactly 312 IDs across 29 families. Every row runs on fictional offline fixtures, verifies its registered codes/transitions/persistence effects, and asserts `outbound_oa_mutation_request_count=0`; failed source-import rows additionally assert `oa_read_count=0`.

### 14.3 HumanFactBinding hash erratum selectors (existing IDs only)

- `SYN-EVAL-PROV-001`: consume the fixed v0.1.5.5 vector while preserving the accepted v0.1.5.4 compatibility event/binding, usage registry, and rules binding. Reproduce the exact 425-byte binding JCS and `human_fact_binding_sha256=07dc93c4fabdad118c2c16d79375ff314b3ee3e1bb5da242e4670dafe96adaa8` using only `UTF8("doi-human-fact-binding/v1\n") || binding_bytes`. Reordered set inputs reproduce both; any material member change changes both. Empty/wrong/missing-LF prefix, non-JCS bytes, uppercase/malformed expected digest, and mismatch fail closed. The narrow binding digest never replaces the human-fact content, evaluation-input, output, or full-record digest. Existing stale/unavailable/unknown/tampered branches use RC-084/105/106 and never substitute a version.
- `SYN-EVAL-PROV-005`: retain all v0.1.5.4 HumanFact kind/result/payload/idempotency/correction and legal/illegal usage rows. Add bracketed rows proving same binding/equivalent set order yields the same digest; changed usage, context, line scope, fact event ID, or fact content hash yields a different digest; an illegal binding fails RC-105 before any digest can legitimize it; and a mismatched expected digest fails RC-106. Existing fact construction/correction, stream, and collision routes remain RC-112/111/103. No new test ID or family.

No selector adds an ID, family, reason, transition, lifecycle kind, or historical gate. The package must still mechanically derive 312 unique IDs across 29 families.

Future supervised shadow-mode captures may enter a separate executable historical layer only after independent proof of complete relevant line capture, all required order/line facts, exact source/extractor/schema/rules versions, immutable fact binding, privacy minimization, and expected-result leakage controls. Future captures never mutate or retroactively promote the original 213 cases.
