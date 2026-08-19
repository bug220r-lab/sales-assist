
> **Sanitized supporting reference.** This file is a mechanically sanitized derivative of
> source material supplied for the synthetic proof of concept. Historical status/freeze
> language is nonbinding. The curated files under `specs/` govern. No production-system
> access or real-data use is authorized by this reference.

# Synthetic Sales Assist DOI v0.1.5.3 — Reason-Code Registry

Registry version: 0.1.5.3  
Status: Unknown ETA normalization erratum candidate; independent re-audit required; not a freeze declaration  
Compatibility rule: codes are immutable within a registry version. Meanings may be changed only by publishing a new version.

## 1. Registry rules

Every persisted reason code MUST appear in this registry and every DOIEvaluation MUST identify this exact registry version. Codes are uppercase ASCII with underscores. Free-text substitutes, aliases, fuzzy matching, and silent fallback codes are forbidden.

Classification:

- OBSERVATION: source-grounded condition without an action claim.
- OPPORTUNITY: potentially useful action identified.
- HANDLING: affects how an opportunity may be handled.
- COORDINATION: affects who may act and when.
- BLOCK: prevents a specific conclusion, read, action, or calculation.
- CLOSURE: verified excluded/terminal disposition.
- AUDIT: provenance, lifecycle, or accounting event.
- SAFETY: permanent boundary enforcement.

Codes may coexist unless the machine contract defines mutual exclusion. A code never proves an intervention occurred unless it is an intervention verification code backed by the required entity.

## 2. Source ingestion

| ID | Code | Class | Owner | Deterministic trigger and effect |
|---|---|---|---|---|
| RC-001 | SOURCE_TAB_CONFIRMATION_REQUIRED | BLOCK | user action | Monday/Wednesday/Friday tab was not explicitly confirmed. Do not import or read OA. |
| RC-002 | SOURCE_SCHEMA_UNRECOGNIZED | BLOCK | DOISourceImportAttempt/DOIRun | Versioned mapping cannot deterministically identify Order Number or Assigned Rep. Fail the current source-import attempt with zero OA reads; the run fails only when no exact legal pre-OA retry is accepted. |
| RC-003 | SOURCE_ROW_INVALID_ORDER_NUMBER | BLOCK | compatibility-reserved | Reserved for a separately governed future schema that explicitly permits row-local invalidity; it is never emitted by `synthetic-doi-queue-v0.1`. In the locked schema, any populated-record A failure emits RC-002 + RC-090, fails run/import, creates no batch/work/case/evaluation, and performs zero OA reads. |
| RC-004 | SOURCE_ROW_UNRECOGNIZED_ASSIGNEE | BLOCK | DOISourceImportAttempt aggregate | Scalar assignee is blank/unrecognized under the exact normalizer. Do not guess; persist no row/order identity and do not read OA for it. |
| RC-005 | SOURCE_ROW_OUT_OF_SCOPE | OBSERVATION | DOISourceImportAttempt aggregate | Scalar assignee deterministically does not equal TARGET_REP. Count only; persist no row/order identity and do not read OA for it. |
| RC-006 | SOURCE_DUPLICATE_ROW_MERGED | AUDIT | DOIStagedOrder | Compatible TARGET_REP rows have the same exact Order Number. Merge to one staged order and preserve all TARGET_REP source refs. |
| RC-007 | SOURCE_ROW_CONFLICT | BLOCK | compatibility-reserved future DOIRejectedSourceRecord | Unreachable under `synthetic-doi-queue-v0.1` because A/B contains no conflict-capable metadata and E:O is outside the row model; duplicate TARGET_REP rows always merge with RC-006. A future mapping must version and govern explicit row metadata before RC-007 can become reachable. |
| RC-008 | SOURCE_ASSIGNEE_CONFLICT | BLOCK | DOIRejectedSourceRecord / source rejected outcome | Same valid Order Number is assigned to TARGET_REP and a nonblank non-TARGET_REP scalar assignee in the coherent import. TR-103 appends one run-local rejected record, no staged order/work/case, and zero OA reads for that number. |
| RC-009 | SOURCE_CHANGED_DURING_IMPORT | BLOCK | DOISourceImportAttempt/DOIRun | Defensive version/readback evidence proves the selected tab changed during import. Fail the current attempt; no executable batch/work proceeds from it. The run fails only when no exact legal pre-OA retry is accepted. |
| RC-010 | SOURCE_ABSENT_RECHECK_REQUIRED | BLOCK | DOIOrderCase | Previously active TARGET_REP case is absent from the new batch. Absence never closes; perform one read-only disappearance verification. |

## 3. Extraction, normalization, and continuity

| ID | Code | Class | Owner | Deterministic trigger and effect |
|---|---|---|---|---|
| RC-011 | EXTRACTION_REQUIRED_IDENTITY_MISSING | BLOCK | DOIExtractionAttempt | Exact requested Order Number cannot be proved on the read surface. Create no snapshot/evaluation. |
| RC-012 | EXTRACTION_WHOLE_ORDER_UNPROVEN | BLOCK | DOIExtractionAttempt | Proof that every relevant line was captured is absent or inconsistent. Create no snapshot/evaluation. |
| RC-013 | EXTRACTION_REQUIRED_DATA_UNREADABLE | BLOCK | DOIExtractionAttempt | Required source data is missing/unreadable rather than successfully observed. It is not UNKNOWN; create no snapshot/evaluation. |
| RC-014 | EXTRACTION_FAILED | BLOCK | DOIExtractionAttempt | Umbrella failure code paired with at least one specific extraction reason. Set RECHECK_REQUIRED. |
| RC-015 | RECHECK_REQUIRED | BLOCK | DOIOrderCase | A failed/incomplete extraction or unresolved verification requires a new explicit read-only recheck. |
| RC-016 | UNKNOWN_LINE_AVAILABILITY | OBSERVATION | DOIEvaluation line | Availability was successfully observed but cannot be safely normalized. Exclude the line from available-to-ship value and contain uncertainty. |
| RC-017 | UNKNOWN_LINE_DS_STATE | OBSERVATION | DOIEvaluation line | DS value was successfully observed but cannot be safely normalized. Do not infer DS/non-DS for that line. |
| RC-018 | LINE_CONTINUITY_UNVERIFIED | BLOCK | DOIEvaluation line | Cross-snapshot lineage is not deterministic. Row position is insufficient; block lineage-dependent conclusions. |

## 4. Evaluation, exclusion, and closure

| ID | Code | Class | Owner | Deterministic trigger and effect |
|---|---|---|---|---|
| RC-019 | FULL_DS | OBSERVATION | DOIEvaluation | At least one relevant active merchandise line exists and every such line is explicitly DS. DOI state is DOI_EXCLUDED; no purge begins solely from this evaluation. |
| RC-020 | MIXED_DS | OBSERVATION | DOIEvaluation | At least one active DS and one active non-DS line exist. Preserve non-DS analysis and emit DS_SEPARATION_REQUIRED. |
| RC-021 | SHIPPED | CLOSURE | DOIOrderCase | Complete OA snapshot verifies fully shipped. DOI_EXCLUDED; hard-close and schedule 90-day purge. |
| RC-022 | CANCELED | CLOSURE | DOIOrderCase | Complete OA snapshot verifies fully canceled. DOI_EXCLUDED; hard-close and schedule 90-day purge. |
| RC-023 | REP_TRANSFERRED | CLOSURE | DOIOrderCase | Complete OA snapshot verifies order assigned away from TARGET_REP. Reversible close and schedule purge. |
| RC-024 | DEDUPE_CONFIRMED | CLOSURE | DOIOrderCase | Read-only OA recheck verifies DEDUPE note. Reversible close and schedule purge. |
| RC-025 | HUMAN_OUT_OF_SCOPE_CLOSED | CLOSURE | DOIOrderCase | Authorized human explicitly closes as out of scope. Reversible close and schedule purge. |
| RC-026 | PAYMENT_ISSUE_OUT_OF_SCOPE | OBSERVATION | DOIEvaluation | Payment is the sole non-progression reason. DOI_EXCLUDED; no purge begins solely from this evaluation. |
| RC-027 | PAYMENT_ISSUE_PRESENT_OUT_OF_SCOPE | HANDLING | DOIEvaluation | Payment issue coexists with a product-side opportunity. Preserve the opportunity and surface payment before action. |
| RC-028 | ORDER_PROGRESS_REVIEW | HANDLING | DOIEvaluation | Active unshipped order has all relevant active non-DS lines explicitly IN_STOCK/FULL. DOI_MANUAL_REVIEW without a release recommendation. |
| RC-029 | NO_ACTION_REQUIRED | OBSERVATION | DOIEvaluation | Human review finds normal or out-of-scope progression with no current useful intervention. DOI_MONITOR. |

## 5. Opportunities and alternate research

| ID | Code | Class | Owner | Deterministic trigger and effect |
|---|---|---|---|---|
| RC-030 | DS_SEPARATION_REQUIRED | OPPORTUNITY | DOIOpportunity | MIXED_DS is proved. Recommend human DS separation; never perform it. |
| RC-031 | FULFILLMENT_SPLIT_CANDIDATE | OPPORTUNITY | DOIOpportunity | At least one active non-DS IN_STOCK/FULL line and one active non-DS DELAYED line. No minimum value/duration. |
| RC-032 | PARTIAL_QTY_INTERVENTION_REVIEW | HANDLING | DOIEvaluation line | Exact 0 < available quantity < active quantity. Calculate partial value when possible; never auto-recommend partial split. |
| RC-033 | EXACT_SKU_RECHECK | OPPORTUNITY | DOIOpportunity | Same ordered ES has a plausible current availability/lead improvement. It is not an alternate; OA confirmation is required. |
| RC-034 | EXACT_MFG_ALTERNATE | OPPORTUNITY | DOIOpportunity | Different ES, identical canonical MFG/OE, better current availability/lead, and valid relationship evidence. Customer approval required. |
| RC-035 | MFG_CROSS_REFERENCE | OPPORTUNITY | DOIOpportunity | Different ES/MFG with explicit cross-reference evidence. Customer approval and any required compatibility review apply. |
| RC-036 | MFG_SUPERSESSION | OPPORTUNITY | DOIOpportunity | Different ES/MFG with explicit supersession evidence. Preserve provenance; customer approval and any required compatibility review apply. |
| RC-037 | FUNCTIONAL_ALTERNATE | OPPORTUNITY | DOIOpportunity | Different product may perform the function but is not exact/cross-reference/supersession. Fresh compatibility review and approval required. |
| RC-038 | NO_EXACT_MFG_ALTERNATE_FOUND | OBSERVATION | DOIEvaluation line | Completed research found no verified different-ES identical-MFG candidate. Does not prove no other alternate exists. |
| RC-039 | NO_VERIFIED_ALTERNATE_FOUND | OBSERVATION | DOIEvaluation line | Completed supported research found no verified safe alternate. Does not itself prove DEDUPE eligibility. |
| RC-040 | MANUAL_IDENTIFICATION_REQUIRED | BLOCK | DOIEvaluation line | Ordered product/application cannot be identified strongly enough. Human review required; DEDUPE blocked. |
| RC-041 | NO_VIABLE_ALTERNATE_HUMAN_CONFIRMED | OBSERVATION | DOIEvaluation line | Human completed review and explicitly confirmed no viable alternate. Does not itself close or write DEDUPE. |
| RC-042 | CUSTOMER_APPROVAL_REQUIRED | HANDLING | DOIOpportunity | Every substitution requires customer approval before manual OA execution. |
| RC-043 | HUMAN_COMPATIBILITY_REVIEW_REQUIRED | HANDLING | DOIOpportunity | Functional alternate, or non-deterministic cross-reference/supersession, requires human application/fitment review. |

## 6. Alternate knowledge lifecycle

| ID | Code | Class | Owner | Deterministic trigger and effect |
|---|---|---|---|---|
| RC-044 | ALTERNATE_OBSERVATION_REQUIRED | BLOCK | DOIOpportunity | A durable relationship exists but no new current-action observation exists. Research may surface; contact/substitution gate remains closed. |
| RC-045 | ALTERNATE_OBSERVATION_STALE | BLOCK | DOIAlternateObservation | Observation remains stored or was found in history but is not from the current explicit action context. Never treat as current. |
| RC-046 | ALTERNATE_RELATIONSHIP_SUPERSEDED | AUDIT | DOIAlternateRelationship | Explicit source-grounded evidence identifies a successor relationship. ACTIVE → SUPERSEDED. |
| RC-047 | ALTERNATE_RELATIONSHIP_INVALIDATED | AUDIT | DOIAlternateRelationship | Explicit contradictory evidence invalidates the relationship. ACTIVE → INVALIDATED. |
| RC-048 | FUNCTIONAL_ALTERNATE_REVALIDATION_REQUIRED | HANDLING | DOIOpportunity | Prior functional knowledge is reused for a new order/application. Re-review compatibility before action. |

## 7. Geography and human handling

| ID | Code | Class | Owner | Deterministic trigger and effect |
|---|---|---|---|---|
| RC-049 | AK_HI_SHIPPING_REVIEW | HANDLING | DOIEvaluation | Geography is Alaska/Hawaii class. Human review required before split; customer contact case-by-case. |
| RC-050 | INTERNATIONAL_ORDER_REVIEW | HANDLING | DOIEvaluation | Geography is outside the 50-state operational class, including territories, APO/FPO, and Washington D.C. Human review required. |
| RC-051 | CUSTOMER_CONTACT_REQUIRED_BEFORE_SPLIT | HANDLING | DOIOpportunity | International split handling requires customer contact before manual split. |
| RC-052 | HUMAN_DECISION_REQUIRED | HANDLING | DOIEvaluation/opportunity | Locked rule delegates commercial or non-routine choice to an authorized human; it is not proof of action. |

## 8. WWC coordination

| ID | Code | Class | Owner | Deterministic trigger and effect |
|---|---|---|---|---|
| RC-053 | WWC_ACTIVE_SELF | COORDINATION | DOIEvaluation | Latest qualifying WWC is by TARGET_REP. Ongoing work may continue; suppress new outreach only. |
| RC-054 | WWC_ACTIVE_OTHER_REP | COORDINATION | DOIEvaluation | Latest qualifying WWC is another rep and the next-business-date eligibility boundary has not arrived. Analysis continues; TARGET_REP contact/work and DEDUPE are blocked. |
| RC-055 | WWC_AUTHOR_UNCERTAIN | BLOCK | DOIEvaluation | WWC author cannot be safely classified. Never guess; require coordination review. |
| RC-056 | TIMING_UNCERTAIN | BLOCK | DOIEvaluation | WWC timestamp/calendar result cannot be safely established. Never assume protection expired. |
| RC-057 | HUMAN_COORDINATION_REVIEW_REQUIRED | COORDINATION | DOIEvaluation | WWC author/timing ambiguity needs human resolution. Preserve known opportunities. |

## 9. DEDUPE

| ID | Code | Class | Owner | Deterministic trigger and effect |
|---|---|---|---|---|
| RC-058 | DEDUPE_CANDIDATE | HANDLING | DOIEvaluation | Complete one-pass analysis finds no unresolved/actionable DOI solution. Human decision required; system never writes OA note. |
| RC-059 | DEDUPE_BLOCKED_INCOMPLETE_ANALYSIS | BLOCK | DOIEvaluation | Any opportunity, partial quantity, unknown-concealed opportunity, manual identification, active other-rep WWC, or incomplete research remains. |

## 10. Intervention, credit, and resulting-order verification

| ID | Code | Class | Owner | Deterministic trigger and effect |
|---|---|---|---|---|
| RC-060 | INTERVENTION_VERIFICATION_REQUIRED | BLOCK | DOIOrderCase | A change is detected but action identity/causation is not proved. Create no intervention or realized credit. |
| RC-061 | INTERVENTION_ACTION_SYSTEM_VERIFIED | AUDIT | DOIIntervention | Deterministic source evidence proves actual human action. Create/reuse intervention with SYSTEM_VERIFIED provenance. |
| RC-062 | INTERVENTION_ACTION_HUMAN_VERIFIED | AUDIT | DOIIntervention | Authorized human exactly attests actual completed action with structured evidence. Create/reuse intervention with HUMAN_VERIFIED provenance. |
| RC-063 | INTERVENTION_VALUE_UNVERIFIED | BLOCK | DOIIntervention | A verified credit-bearing split/substitution action has no exact accepted realized value, so value is UNVERIFIED and realized money is zero. It is mandatory even when an independent date/currency gate also fails, and forbidden for DS_SEPARATION/NOT_APPLICABLE. |
| RC-064 | INTERVENTION_VALUE_SYSTEM_VERIFIED | AUDIT | verification event | System-grounded evidence proves exact realized value. Use for current KPI. |
| RC-065 | INTERVENTION_VALUE_HUMAN_VERIFIED | AUDIT | verification event | Human provides exact known realized value. Count unless later authoritative system evidence conflicts. |
| RC-066 | INTERVENTION_VALUE_CONFLICT_SYSTEM_AUTHORITATIVE | AUDIT | verification event | While the detailed case remains retained, later system value conflicts with human value. Preserve both; system value controls current KPI. |
| RC-067 | HUMAN_VALUE_NOT_EXACT | BLOCK | user action | Human-provided amount is estimated, rounded, ranged, or otherwise not exact. Reject verification; KPI remains zero. |
| RC-068 | INTERVENTION_PARTIALLY_REVERSED | AUDIT | DOIIntervention | Verified reversal is greater than zero and less than original realized value. |
| RC-069 | INTERVENTION_REVERSED | AUDIT | DOIIntervention | Verified reversal equals original realized value; net is zero. |
| RC-070 | RESULTING_ORDER_AUTO_LINKED | AUDIT | DOIResultingOrderLink | Deterministic allowed evidence proves child order relationship. |
| RC-071 | RESULTING_ORDER_HUMAN_CONFIRMED | AUDIT | DOIResultingOrderLink | Authorized human verifies child relationship with structured evidence. |
| RC-072 | RESULTING_ORDER_LINK_REVIEW | BLOCK | DOIResultingOrderLinkSearch or exact DOIResultingOrderLink | A candidate search is ambiguous, or an existing exact link has unresolved mapping conflict. Keep search and exact-link streams distinct; human/exact resolution is required and disputed split credit is unverified. |
| RC-073 | RESULTING_ORDER_NOT_FOUND | BLOCK | DOIResultingOrderLinkSearch | A complete search finds no exact resulting order. Append only search-state NOT_FOUND; do not create an exact link, child identity, mapping, or realized split credit. |
| RC-074 | SPLIT_CREDIT_REP_UNVERIFIED | BLOCK | DOIIntervention | Resulting order-level TARGET_REP rep is missing/different/ambiguous. Realized split credit is zero until resolved. |
| RC-075 | SWAP_CREDIT_REP_UNVERIFIED | BLOCK | DOIIntervention | Replacement line-level TARGET_REP rep is missing/different/ambiguous. Order-level rep cannot substitute; realized swap credit is zero. |
| RC-076 | CREDIT_DUPLICATE_SUPPRESSED | AUDIT | aggregate calculation | Same verified action-evidence fingerprint or credit unit was encountered again. Reuse original intervention; add no credit. |
| RC-077 | REVERSAL_VERIFICATION_REQUIRED | BLOCK | DOIIntervention | Potential removal/cancellation of credited merchandise is detected but exact reversal is not proved. Preserve prior verified totals pending verification. |

## 11. Lifecycle, retention, rules, and safety

| ID | Code | Class | Owner | Deterministic trigger and effect |
|---|---|---|---|---|
| RC-078 | CASE_REOPENED | AUDIT | DOIOrderCase | Before purge, explicit recheck provides source-grounded eligibility after reversible closure. Reuse the retained case and cancel purge. |
| RC-079 | PURGE_SCHEDULED | AUDIT | DOIOrderCase | Verified terminal transition schedules detailed-data purge at exact `calendar90(terminal_closed_at)`; persist UTC plus retention-policy/timezone-database versions. |
| RC-080 | PURGE_CANCELED_ON_REOPEN | AUDIT | DOIOrderCase | A reversible closure reopens before purge only after `CaseReopenPayloadV2` and `PURGE_CANCELED` each carry the complete explicit `PriorClosureRetentionBindingV1` copied byte-for-byte from the locked pre-event closure/retention projection. The canceled deadline must equal that binding's `prior_purge_eligible_at`; then clear the deadline on the same retained case. |
| RC-081 | STATE_TRANSITION_NOT_ALLOWED | BLOCK | any projection | Requested/derived transition is unlisted or violates its guard. Attention examples include wrong/inactive cause key, wrong SET reference, incomplete resolver group, illegal reason/null partition, or conflicting CLEAR identity. Reject and preserve last valid projection. |
| RC-082 | OA_WRITE_PROHIBITED | SAFETY | system boundary | Requested capability or operation could mutate OA. It must not exist or execute. |
| RC-083 | UNSAFE_ACTION_REJECTED | SAFETY | user/API action | A DOI request attempts an OA mutation, generic click/request, background poll, or unallowlisted side-effectful read path. Reject with no OA request. |
| RC-084 | RULE_VERSION_UNAVAILABLE | BLOCK | DOIEvaluation | Exact requested historical/current rules version cannot be loaded. Create no evaluation under a substitute version. |
| RC-085 | VALUE_CALCULATION_UNAVAILABLE | BLOCK | DOIEvaluation | Required exact quantity/value/classification inputs are unavailable. Return UNAVAILABLE, never an inferred or silently zero value. |
| RC-086 | CASE_IDENTITY_NOT_RETAINED | BLOCK | user/API action | A requested case-linked correction, reversal, or reconciliation targets no retained case/intervention identity, including after purge. Reject without reconstruction, tombstone/hash lookup, aggregate change, or a persistent order-specific rejection record. |
| RC-087 | POTENTIAL_OVERLAP_UNRESOLVED | BLOCK | DOIEvaluation/aggregate | Potential opportunities address overlapping/mutually exclusive merchandise scopes and no explicit scenario selection exists. Keep opportunity values separate and overall potential UNAVAILABLE. |
| RC-088 | AGGREGATE_KPI_FINALIZED | AUDIT | aggregate calculation | At purge, atomically transfer the case's then-current exact contribution into non-identifying finalized aggregate history before deleting its entire per-order graph. Retain no per-case delta or linkage. |

## 12. Carried-forward source, retention, currency, KPI, provenance, and history additions

| ID | Code | Class | Owner | Deterministic trigger and effect |
|---|---|---|---|---|
| RC-089 | SOURCE_UNREADABLE_OR_INACCESSIBLE | BLOCK | DOISourceImportAttempt/DOIRun | Confirmed selected source or required sentinel/A:B read cannot be accessed. The current attempt fails with no batch/work/case and zero OA reads; the run fails only when no exact legal pre-OA retry is accepted. |
| RC-090 | SOURCE_IMPORT_ATTEMPT_FAILED | BLOCK | DOISourceImportAttempt | Umbrella required on each failed import with at least one exact specific source reason; never replaces the specific code. |
| RC-091 | SOURCE_BATCH_IDENTITY_INTEGRITY_CONFLICT | SAFETY | source-batch binding | Same digest maps to different canonical identity material or incompatible payload. Fail the current attempt before OA; do not overwrite/reuse/create a conflicting batch. The run fails only when no exact legal pre-OA retry is accepted. |
| RC-092 | SOURCE_REJECTED_IDENTITY_RETENTION_SCHEDULED | AUDIT | DOIRejectedSourceRecord | Run terminalized; schedule exact no-case identity deletion at `calendar90(run.completed_at)` without extension by batch reuse. |
| RC-093 | SOURCE_REJECTED_IDENTITY_PURGED | AUDIT | TR-105 transaction-local deletion assertion | At eligibility the exact rejected identity and joinable detail are deleted atomically. RC-093 exists only inside the deleting transaction and no rejection reason, dimension, event, receipt, hash, record/order/source reference, or separate rejection aggregate survives commit. |
| RC-094 | CURRENCY_CODE_INVALID | BLOCK | monetary fact/calculation | A supplied code/scale/representation/registry binding is invalid. Create no Money/row/bucket; infer no USD/FX. A merely absent pre-value currency is not RC-094. |
| RC-095 | MIXED_CURRENCY_AGGREGATION_PROHIBITED | BLOCK | calculation/KPI | A scalar would combine currencies. Return segmented results and no combined value or FX inference. |
| RC-096 | RETENTION_CLOCK_CALCULATION_FAILED | BLOCK | retention scheduler | Policy/timezone binding or DST resolution cannot produce exact UTC. Schedule no approximate/earlier purge. |
| RC-097 | OPPORTUNITY_SCOPE_UNPROVEN | BLOCK | DOIEvaluation candidate | Required immutable line identity/quantity/continuity is unproved. Create no candidate opportunity or potential/credit. |
| RC-098 | SCENARIO_OPTION_SELECTION_CONFLICT | BLOCK | potential calculation | Multiple options selected for one overlap key or option is outside the group/evaluation. Reject selection; emit no group/combined total. |
| RC-099 | KPI_ACTION_DATE_UNVERIFIED | BLOCK | DOIIntervention | Credit-bearing verified action lacks exact business occurrence instant/local attribution date. Evidence/review/ingestion/record time cannot substitute; retain operational evidence but create no contribution/date bucket. |
| RC-100 | KPI_BUCKET_IDENTITY_CONFLICT | BLOCK | KPI persistence | Derived daily date/bounds/currency/class conflicts with stored identity. Roll back; do not move or duplicate money. |
| RC-101 | KPI_FINALIZATION_CONFLICT | BLOCK | purge transaction | Ledger/bucket projection fails pre-finalization reconciliation. Roll back both KPI transfer and case deletion. |
| RC-102 | EVIDENCE_NATURAL_KEY_CONFLICT | BLOCK | action/value/reversal verification ledger | Same ACTION/original-value/reversal logical key has a different material effect without legal correction. Preserve last valid projection; apply no disputed effect. Exact parent/type/child mapping conflict is excluded and uses RC-104 + RC-072. |
| RC-103 | EVIDENCE_FINGERPRINT_INTEGRITY_FAILURE | SAFETY | persistence boundary | One SHA-256 value maps to different canonical bytes for a key/evidence/mapping payload. Roll back the affected transaction. At a registered pre-OA source/integrity gate this may terminalize the run FAILED with RC-090; after any OA work began it is an order exception and a coherent run terminalizes COMPLETED_WITH_EXCEPTIONS, never FAILED solely for this post-OA collision. |
| RC-104 | RESULTING_ORDER_LINK_EVIDENCE_CONFLICT | BLOCK | DOIResultingOrderLink | Same parent/type/child natural link has contradictory moved-line/quantity mapping. Set review/ambiguous; add RC-072; disputed split credit zero. |
| RC-105 | EVALUATION_PROVENANCE_INCOMPLETE | BLOCK | DOIEvaluation | Required snapshot/rules/calendar/relationship-revision/observation/human-fact binding absent, wrong-scope, or unresolved. Append no evaluation. |
| RC-106 | EVALUATION_PROVENANCE_HASH_MISMATCH | BLOCK | DOIEvaluation | Bound version/ID resolves but canonical digest differs. Append no evaluation; never substitute another version. |
| RC-107 | ALTERNATE_RELATIONSHIP_CREATED | AUDIT | DOIAlternateRelationshipRevision | Valid product-only evidence creates one stable relationship and immutable revision 1. |
| RC-108 | ALTERNATE_RELATIONSHIP_REVISION_APPENDED | AUDIT | DOIAlternateRelationshipRevision | Accepted explicit product-only change appends exactly revision n+1; prior revisions unchanged. |
| RC-109 | ALTERNATE_RELATIONSHIP_REVISION_CONFLICT | BLOCK | DOIAlternateRelationshipRevision | With an otherwise valid current envelope, semantic content is illegal: identity-field mutation inside a revision, event-type/state mismatch, unsupported product content, or terminal relationship reactivation. Reject append and retain projection. Sequence, revision-number, predecessor, full-event-hash, stream-ID, and event-identity conflicts use RC-111 exclusively. |
| RC-110 | ACTION_CONTEXT_BINDING_INVALID | BLOCK | DOIActionContext | Context absent/closed/wrong case-evaluation-opportunity-kind, or fact is not explicitly linked. It cannot satisfy readiness. |
| RC-111 | EVENT_STREAM_SEQUENCE_CONFLICT | SAFETY | any typed immutable history | Proposed append has stale sequence/predecessor/digest or reuses event identity with different canonical bytes. Reject; retain projection; RC-103 also applies to a detected digest collision. |
| RC-112 | HUMAN_FACT_PROVENANCE_INCOMPLETE | BLOCK | DOIHumanFactEvent | Actor/scope/fingerprint/provenance is incomplete, or a DEDUPE review/verification binding, fact-to-state-event mapping, current-decision guard, or legal correction predecessor is missing/conflicting. Reject fact/atomic DEDUPE bundle; do not evaluate from it. |
| RC-113 | LIFECYCLE_EVENT_SCHEMA_INVALID | SAFETY | lifecycle serialization boundary | Unknown lifecycle kind/version/payload type; missing/extra field; wrong required/null/absent partition; illegal enum/alias/domain; actor/provenance or typed-event binding mismatch; incorrect natural-key, payload, projection, or full-event hash. For reopen/purge cancellation this includes an omitted, hash-only, inferred, or non-byte-equal `PriorClosureRetentionBindingV1`, any mismatched binding member, and any canceled deadline different from the locked prior deadline. Block and reject before append; preserve the prior closure, deadline, and projection. Stream predecessor/revision faults remain RC-111; proven digest collisions remain RC-103; unlisted state edges remain RC-081. |
| RC-114 | SOURCE_IMPORT_ATTEMPT_PURGED | AUDIT | TR-114 transaction-local DOISourceImportAttemptRetentionEventV1 | At TR-114 eligibility, emit/assert RC-114 only inside the deletion transaction, then atomically delete one terminal source-import-attempt graph, its attempt-owned run/source links, attempt-owned batch/reference edges, indexes/caches/logs/temp artifacts, and the transient purge event/reason itself. Delete the run identity graph only when its own deadline is due and the closed last-reference predicate is true. Only `DOISourceImportAggregateV2` month, outcome class, and count may survive; it retains no reason code, tombstone, hash, or reversible lookup. |
| RC-115 | UNKNOWN_LINE_ETA_STATE | OBSERVATION | DOIEvaluation line | The ETA field was successfully observed, but its raw value could not be safely normalized into the closed ETA tagged-value model. Preserve the line's other independently known source facts and block only conclusions whose complete basis depends on ETA. Do not infer a date, lead time, terminal state, availability state, or DS state, and never reuse a stale ETA. A narrowly bounded, field-allowlisted, non-sensitive raw ETA hint may be retained only under the existing UNKNOWN/raw-hint privacy contract. Missing, unreadable, inaccessible, or unobserved required ETA data is extraction failure. RC-115 does not substitute for RC-016, RC-017, or RC-085 and authorizes no OA action or write. |

## 13. Registry invariants

1. SOURCE_SCHEMA_UNRECOGNIZED and SOURCE_CHANGED_DURING_IMPORT require the current attempt to fail with `oa_read_count=0`; absent an exact legal pre-OA retry, the run terminalizes FAILED with zero OA reads.
2. SOURCE_ROW_CONFLICT and SOURCE_ASSIGNEE_CONFLICT forbid an OA read for that order.
3. EXTRACTION failure codes cannot coexist with a new snapshot_id.
4. The field-specific UNKNOWN mapping is closed: observed-but-unnormalizable availability emits RC-016, DS state emits RC-017, and ETA emits RC-115. Independently UNKNOWN fields produce exact set union. A reason may not substitute for another field; missing/unreadable/unobserved required data uses extraction failure.
5. SHIPPED and CANCELED are the only hard-closure reason codes.
6. REP_TRANSFERRED, DEDUPE_CONFIRMED, and HUMAN_OUT_OF_SCOPE_CLOSED are reversible closures.
7. FULL_DS and PAYMENT_ISSUE_OUT_OF_SCOPE do not schedule purge without a separate verified terminal closure.
8. Opportunity codes never imply an intervention.
9. Intervention verification codes require immutable verification evidence.
10. Unverified or non-exact value always contributes zero.
11. Product relationship non-rediscovery emits no invalidation code.
12. OA_WRITE_PROHIBITED is release-blocking and cannot be waived by a user action.
13. CASE_IDENTITY_NOT_RETAINED never authorizes identity reconstruction or a persistent rejection record; AGGREGATE_KPI_FINALIZED never carries a case/order/intervention link.
14. CASE_REOPENED and system-over-human correction apply only while detailed case identity remains retained; after purge, the ordinary no-retained-case creation path may create a new unlinked case.
15. A coherent run with any order exception is COMPLETED_WITH_EXCEPTIONS even when zero normal evaluations succeed; FAILED is reserved for a registered source-execution failure after the exact pre-OA retry decision has closed without a successful retry.
16. Every accepted `RUN_DOI_REVIEW` has one or more sequential `DOISourceImportAttempt` ordinals. Each named failed attempt has a null executable batch and zero OA reads; a legal retry uses the next ordinal while the run remains IN_PROGRESS.
17. Money always binds a valid ISO-4217 code/registry; mixed currencies never share a scalar or FX conversion.
18. RC-104 is the sole resulting-link mapping-conflict code; RC-111 governs immutable stream sequencing and predecessor integrity.
19. Registry cardinality is exactly 115 unique IDs, `RC-001` through `RC-115`; codes are unique and no ID is skipped.
20. RC-113 is lifecycle schema/serialization rejection only. It never substitutes for RC-081 state illegality, RC-111 stream predecessor/revision conflict, or RC-103 a proven same-digest/different-canonical-bytes collision.
21. TR-106 reason parity is exact: credit-bearing UNVERIFIED always includes RC-063; invalid supplied currency adds RC-094; null business action date adds RC-099; a FULFILLMENT_SPLIT whose already-exact child link has missing/different/ambiguous resulting order-level TARGET_REP-rep proof adds RC-074; a PRODUCT_SUBSTITUTION whose replacement line has missing/different/ambiguous line-level TARGET_REP-rep proof adds RC-075. Combined predicates are set union. RC-074 and RC-075 are mutually exclusive because one accepted intervention has one exact registered type; DS_SEPARATION/NOT_APPLICABLE includes none of RC-063/074/075/099 and persists no Money row. Absent pre-value currency is not RC-094. A both-code, wrong-type, or contradictory rep branch is RC-081 before TR-106 and changes no state.
22. An OA note, note observation, lifecycle event, or evaluation inference never creates DEDUPE_APPROVED/REJECTED. Same-review conflicts outside the one predecessor-bound approval-to-rejection correction are RC-112 with zero append.
23. Reopen and purge-cancellation serialization require the complete explicit `PriorClosureRetentionBindingV1`; a projection hash alone never substitutes for the tuple. Every member and the active pre-event deadline must be byte-equal to authoritative retained state before RC-078/080 can commit.
24. RC-082 is the exact system/build-boundary rejection for a forbidden write-capable capability or helper such as `click`; it fails before runtime/package promotion and does not coexist with RC-083. RC-083 is the exact user/API-runtime rejection for a deliberate blocked POST/write-RPC, generic action, poll, or unallowlisted side-effectful read request; it fails before dispatch and does not coexist with RC-082. Clean/allowed DOI-local branches emit neither. Unknown safety code or registry version fails before persistence.
25. RC-114 is permitted only inside the TR-114 transaction-local `DOISourceImportAttemptRetentionEventV1`; the same transaction deletes that event/reason with the due attempt graph, its attempt-owned run/source links, attempt-owned batch/reference edges, and all attempt-identifying derivatives. The run identity graph deletes only when its own deadline is due and no closed run-identity reference remains. `DOISourceImportAggregateV2` may retain only month, outcome class, and count; it retains no reason code, attempt/run/spreadsheet/tab/actor identity, source fingerprint, tombstone, hash, or reversible key.
26. `DOI_REASON_OWNERSHIP_MATRIX_v0.1.5.3.md` is the closed external-ownership authority. Release requires all 115 registry rows to have a non-registry rule/service owner and at least one deterministic oracle; every emitted/referenced code must exist here; no orphan, alias, undefined reference, or unknown version may reach persistence.
