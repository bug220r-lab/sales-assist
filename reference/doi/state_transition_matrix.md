
> **Sanitized supporting reference.** This file is a mechanically sanitized derivative of
> source material supplied for the synthetic proof of concept. Historical status/freeze
> language is nonbinding. The curated files under `specs/` govern. No production-system
> access or real-data use is authorized by this reference.

# Synthetic Sales Assist DOI v0.1.5 — State Transition Matrix

Authority patch: v0.1.5.4 HumanFactUsageKind erratum candidate; transition inventory remains 115; independent audit required; not a freeze declaration.

Matrix version: 0.1.5  
Status: independent-audit remediation candidate; independent re-audit required  
Default rule: every transition not explicitly listed below is illegal and MUST fail closed with STATE_TRANSITION_NOT_ALLOWED.

## 1. Transition semantics

Snapshots, line snapshots, evaluations, source batches, opportunities, alternate observations, and verification events are immutable. "Transition" for those entities means append a new immutable entity and update a current projection; it never means rewriting the prior record.

Case, intervention, relationship, link, contact, DEDUPE, attention, and WWC states are projections reduced from immutable events. Guards are mandatory. An invalid event is rejected and the last valid projection remains authoritative.

For every row, the exhaustive lifecycle/non-case/projection/deletion serialization route is the identically keyed row in `DOI_LIFECYCLE_EVENT_PAYLOAD_REGISTRY_v0.1.5.md` section 9. A case-linked typed fact and its thin `DOIOrderLifecycleEventV2` wrapper commit in the same transaction; projection-only subordinate effects are bound in the owning wrapper; deletion success is absence and creates no receipt. Unknown lifecycle kind/version/payload, missing/extra field, invalid null partition, or incorrect canonical hash is RC-113 with zero append. This companion route is part of this matrix and may not be replaced by implementation inference.

No transition in this matrix authorizes an OA write.

## 2. DOIRun execution

Accepted invocation, source-attempt, and terminal facts are immutable events; `IN_PROGRESS` and the terminal status are rebuildable projections. A mere suggestion or disabled-control click is not an accepted invocation.

| Transition | From | To | Required guard/evidence | Required effects |
|---|---|---|---|---|
| TR-001 | NONEXISTENT | IN_PROGRESS | Human accepted an explicit `Run DOI Review` with exactly one locked tab confirmed | Immediately persist one run invocation and start the first versioned source-import attempt at ordinal 1; later same-run attempts require the next stable ordinal and fresh ID while the run remains nonterminal; no OA read or background continuation |
| TR-002 | IN_PROGRESS | COMPLETED | Coherent batch bound; processing terminal; zero order exceptions/blocks | Persist exact counts; a coherent empty personal batch is legal |
| TR-003 | IN_PROGRESS | COMPLETED_WITH_EXCEPTIONS | Coherent batch bound; processing terminal; at least one order exception/block | Success count may be zero, including all-blocked/all-extraction-failed; preserve allowed per-order evidence; never classify this as FAILED |
| TR-004 | IN_PROGRESS | FAILED | Current source-import attempt has already terminalized with registered RC-002/009/089/091 plus RC-090 and no exact legal pre-OA retry is accepted | Terminalize the run with the final attempt's exact failure reasons; batch null; zero executable work/cases/evaluations/OA reads |

## 3. DOIExtractionAttempt

STARTED is transient; the terminal attempt is immutable.

| Transition | From | To | Required guard/evidence | Required effects |
|---|---|---|---|---|
| TR-005 | STARTED | SUCCEEDED | Exact identity observed; complete whole-order proof; every relevant line captured | Append exactly one new snapshot; snapshot_id required |
| TR-006 | STARTED | FAILED | Identity, completeness, or required source data cannot be proved/read | No snapshot/evaluation; retain minimal attempt metadata; set RECHECK_REQUIRED |

UNKNOWN is not an extraction terminal state. It is legal only for a successfully observed individual field inside a complete successful snapshot.

## 4. DOIOrderCase lifecycle

DELETED_AFTER_RETENTION is an operation result, not a persisted state. After deletion, no case/tombstone identifier survives.

| Transition | From | To | Required guard/evidence | Required effects |
|---|---|---|---|---|
| TR-007 | NONEXISTENT | ACTIVE | A valid exact TARGET_REP staged Order Number and safely bound batch are transiently proved; no retained case exists | Atomically create one case, case source binding/reference, and closed `DOICaseSourceAdmissionProofV1`; CASE_CREATED binds that case-owned proof/hash, never the staged/run/attempt/row/tab/actor graph. Current snapshot/evaluation remain null until first success. Post-purge same-number input uses this same path with no predecessor/reopen/historical lookup. |
| TR-008 | ACTIVE | ACTIVE | Successful later Run DOI Review/Recheck with safe current source admission and no terminal closure | Atomically create/reuse the case batch binding/admission proof, append SOURCE_PRESENT/snapshot/evaluation as applicable, and never retain the staged/run/attempt/row/tab/actor target or create a second case |
| TR-009 | ACTIVE | CLOSED_HARD | Complete snapshot verifies SHIPPED | Set SHIPPED/terminal instant; calculate exact `purge_eligible_at=calendar90(terminal_closed_at)` with policy/tzdb bindings |
| TR-010 | ACTIVE | CLOSED_HARD | Complete snapshot verifies full CANCELED | Set CANCELED/terminal instant; calculate exact `calendar90` purge eligibility |
| TR-011 | ACTIVE | CLOSED_REVERSIBLE | Complete snapshot verifies REP_TRANSFERRED | Set closure and exact `calendar90` purge eligibility |
| TR-012 | ACTIVE | CLOSED_REVERSIBLE | Read-only recheck verifies DEDUPE note | Set DEDUPE_CONFIRMED and exact `calendar90` purge eligibility |
| TR-013 | ACTIVE | CLOSED_REVERSIBLE | Explicit authorized human out-of-scope closure | Set HUMAN_OUT_OF_SCOPE and exact `calendar90` purge eligibility |
| TR-014 | CLOSED_REVERSIBLE | ACTIVE | Explicit recheck yields source-grounded DOI eligibility under the exact prior-closure proof map, and a required complete `PriorClosureRetentionBindingV1` is copied byte-for-byte from the locked pre-event closure event/projection. The referenced prior closure event and projection revision/hash must resolve; every tuple and closure source/evidence member must equal that authoritative state; its deadline must equal the active pre-event deadline. | Reuse the same case and preserve its identity. Proof wrappers precede the atomic `CASE_REOPENED` then `PURGE_CANCELED`; both carry the same explicit binding, and `canceled_purge_eligible_at` equals its `prior_purge_eligible_at`. Clear all resulting closure/deadline fields. Missing/hash-only/inferred or mismatched binding is RC-113 before append/persistence and leaves the prior projection/deadline byte-identical. |
| TR-015 | CLOSED_REVERSIBLE | CLOSED_REVERSIBLE | Explicit recheck confirms the same reversible closure and no eligibility | Append current snapshot/evaluation if extraction succeeded; do not restart deadline |
| TR-016 | CLOSED_REVERSIBLE | CLOSED_HARD | Recheck verifies SHIPPED | Append `CASE_CLOSED_HARD` then `PURGE_RESTARTED`; replace projection with SHIPPED and bind the new `calendar90` deadline/policy from this transition |
| TR-017 | CLOSED_REVERSIBLE | CLOSED_HARD | Recheck verifies full CANCELED | Append `CASE_CLOSED_HARD` then `PURGE_RESTARTED`; replace projection with CANCELED and bind the new `calendar90` deadline/policy from this transition |
| TR-018 | CLOSED_HARD | DELETED_AFTER_RETENTION | Current time >= exact `purge_eligible_at`; all ledger/bucket/hash guards pass | Execute TR-112 in the same ACID transaction, then delete every Section 15 graph edge; no per-case receipt/tombstone survives |
| TR-019 | CLOSED_REVERSIBLE | DELETED_AFTER_RETENTION | Current time >= exact `purge_eligible_at`; no accepted TR-014 binding canceled that exact deadline; case did not reopen; all TR-112 guards pass | Execute TR-112 and complete the same atomic graph deletion; mismatch rolls back finalization and deletion |

### 4.1 Closed TR-014 prior-closure/retention binding

`PriorClosureRetentionBindingV1` is a closed, versioned, immutable value embedded explicitly and identically in both TR-014 lifecycle payloads. Its canonical member inventory is exactly: `prior_closure_retention_binding_schema_version`, `prior_closure_event_id`, `prior_closure_event_content_sha256`, `prior_closure_kind`, `prior_closure_classification`, `prior_verified_closure_at`, `prior_retention_policy_id`, `prior_retention_policy_version`, `prior_retention_timezone`, `prior_tzdb_version`, `prior_local_calendar_rule_id`, `prior_purge_eligible_at`, `prior_closure_projection_revision`, `prior_closure_projection_hash`, `prior_closure_source_entity_type`, `prior_closure_source_entity_id`, `prior_closure_source_entity_schema_version`, and `prior_closure_source_entity_content_sha256`. The schema version is exactly `doi-prior-closure-retention-binding/v1`; no additional or omitted member is legal.

The validator locks the pre-event stream/projection before constructing either event and independently proves all of the following before append:

1. `prior_closure_event_id` resolves to the retained authoritative prior closure event for the same case.
2. `prior_closure_projection_revision` and `prior_closure_projection_hash` resolve to the retained locked pre-event projection.
3. Every binding member, including the closure source/evidence identity and content hash, is byte-equal to the authoritative retained state after canonical timestamp serialization.
4. `prior_closure_classification` is the registered `REVERSIBLE` literal and `prior_closure_kind` is exactly one of `REP_TRANSFERRED`, `DEDUPE_CONFIRMED`, or `HUMAN_OUT_OF_SCOPE` under the existing proof map: REP_TRANSFERRED -> current complete SNAPSHOT; DEDUPE_CONFIRMED -> accepted DEDUPE `ELIGIBILITY_RETURNED` event bound to the accepted evaluation; HUMAN_OUT_OF_SCOPE -> accepted new EVALUATION bound to the current legal proof set.
5. `prior_retention_timezone` is exactly `America/New_York`; policy ID/version, tzdb version, and local-calendar rule are the closed values that governed the retained deadline.
6. `prior_purge_eligible_at` equals the active locked pre-event purge deadline and byte-equals `PURGE_CANCELED.canceled_purge_eligible_at`.
7. Both lifecycle payloads carry byte-identical canonical `PriorClosureRetentionBindingV1` bytes; the later event may not infer or reconstruct the tuple from a projection hash or from the earlier event alone.

Any missing reference, missing tuple, mismatch, unknown member/version, noncanonical timestamp, or hash-only inference attempt is rejected with RC-113 before either append. The proof wrappers, both lifecycle events, projection revision, closure/deadline clear, and any subordinate effect are one atomic transaction, so every failure preserves the complete prior closed state. Exact replay validates the binding again and reproduces the same event order, case revision, projection bytes, and hashes.

Lifecycle-registry V3 is a top-level canonical-serialization vector with explicitly opaque already-validated source/predecessor inputs; it cannot satisfy any TR-014 target-existence or authority guard. The valid/replay branches of `SYN-LIFE-PAYLOAD-004/010` independently construct the actual closed-schema closure event, proof, evaluation, policy, and reachable projection records, compute their real hashes, and derive the binding from those locked records. V3 placeholder digests may not be substituted into that branch.

Explicitly illegal:

- CLOSED_HARD → ACTIVE;
- ACTIVE → DELETED_AFTER_RETENTION;
- any retained state → a second DOIOrderCase for the same Order Number; after purge there is no retained state/identity, so a later input follows TR-007 as a new unlinked case;
- FULL_DS, PAYMENT_ISSUE_OUT_OF_SCOPE, or queue exit → a closure without a listed closure transition;
- extending purge merely by re-observing the same reversible closure.

## 5. Case attention conditions

Attention is a cause-keyed set under `doi-attention-event/v2` and `doi-attention-cause-key/v2`. SET stores a complete immutable cause group and an exactly null resolver group. CLEAR copies the cause/key from the exact active SET, names that SET, and stores a separate complete resolver group, time, and registered reason/null partition; resolver members never enter the cause key. Each row changes only its named cause.

| Transition | From | To | Required guard/evidence | Required effects |
|---|---|---|---|---|
| TR-020 | exact cause absent | RECHECK_REQUIRED cause present | Failed/incomplete extraction event validates | SET complete extraction cause; resolver/clear fields null; no snapshot/evaluation |
| TR-021 | exact cause absent | SOURCE_ABSENT_RECHECK_REQUIRED cause present | Active case absent and exact absence event validates | SET complete absence cause; resolver/clear fields null; schedule one read-only disappearance verification |
| TR-022 | exact source-absence cause active | that cause cleared plus distinct RECHECK_REQUIRED cause present | Disappearance verification incomplete/failed | CLEAR references/copies old SET and binds the incomplete verification as resolver; distinct SET uses it as new cause; one atomic bundle, no closure |
| TR-023 | exact source-absence cause active | that cause cleared | Complete disappearance-verification evaluation succeeds | CLEAR references/copies active SET and binds exact accepted evaluation as resolver; append snapshot/evaluation/lifecycle result atomically |
| TR-024 | exact recheck cause active | that cause cleared | Later complete read-only extraction/evaluation succeeds | CLEAR references/copies active SET and independently binds exact accepted evaluation; append snapshot/evaluation atomically |
| TR-025 | exact cause absent | INTERVENTION_VERIFICATION_REQUIRED cause present | Exact accepted EVALUATION detects a changed condition but cannot prove an action | SET complete EVALUATION cause with null resolver partition; create no intervention/credit |
| TR-026 | exact intervention-verification cause active | that cause cleared | Action becomes SYSTEM_VERIFIED or HUMAN_VERIFIED | CLEAR references/copies active SET and binds exact action event as resolver; create/reuse intervention in same transaction |

Known opportunities MUST NOT be deleted merely because an unrelated attention condition is added.

## 6. Immutable evaluation append

| Transition | From | To | Required guard/evidence | Required effects |
|---|---|---|---|---|
| TR-027 | snapshot with no evaluation for requested complete input manifest | new DOIEvaluation | Exact snapshot hash; rules/reason/calendar versions+hashes as applicable; complete relationship-revision, Action-Context observation, and structured human-fact bindings whose fact/usage pairs and exact scopes validate under the bound `doi-human-fact-usage-kind/v1` registry | Verify canonical input/output hashes; append evaluation; never modify any source/human fact. Unknown/missing/illegal usage or scope is RC-105; resolved digest mismatch is RC-106. |
| TR-028 | snapshot with prior evaluation | additional DOIEvaluation | New exact rules bundle, snapshot, accepted relationship revision, current context observation, or current corrected structured human fact yields a complete registry-valid binding manifest | Preserve every prior fact/evaluation; append only. Bare manual ID, stale corrected fact for the new evaluation, illegal/duplicate usage binding, or missing/hash-mismatched binding appends nothing (RC-105/106). No transition ID or state edge changes. |

No evaluation may be appended for a failed/incomplete extraction attempt.

## 7. Top-level DOI state in a new evaluation

These rows describe the next immutable evaluation; any prior DOIState may precede them.

| Transition | From | To | Required guard/evidence | Required effects/precedence |
|---|---|---|---|---|
| TR-029 | ANY prior DOIState | DOI_EXCLUDED | Snapshot verifies SHIPPED or full CANCELED | Hard closure takes precedence |
| TR-030 | ANY prior DOIState | DOI_EXCLUDED | Snapshot verifies REP_TRANSFERRED or DEDUPE_CONFIRMED, or human closure event exists | Reversible closure |
| TR-031 | ANY prior DOIState | DOI_EXCLUDED | All relevant active merchandise is DS | Emit FULL_DS; do not start purge solely from it |
| TR-032 | ANY prior DOIState | DOI_EXCLUDED | Payment is sole blocker and no product opportunity exists | Emit PAYMENT_ISSUE_OUT_OF_SCOPE; no retention closure |
| TR-033 | ANY prior DOIState | DOI_OPPORTUNITY | Mixed DS is proved | Emit DS_SEPARATION_REQUIRED and continue non-DS analysis |
| TR-034 | ANY prior DOIState | DOI_OPPORTUNITY | Split base rule is proved, including when ETA alone is UNKNOWN but availability, DS state, quantities, and split basis remain independently complete | Emit FULFILLMENT_SPLIT_CANDIDATE. ETA UNKNOWN adds RC-115 and makes only ETA-dependent ranking unavailable; it never suppresses the independently proved split or guesses an ETA/date/lead time |
| TR-035 | ANY prior DOIState | DOI_OPPORTUNITY | At least one safely established alternate/exact-SKU opportunity exists | Preserve concurrent handling/coordination flags |
| TR-036 | ANY prior DOIState | DOI_MANUAL_REVIEW | All active non-DS lines explicitly IN_STOCK/FULL and order active/unshipped | Emit ORDER_PROGRESS_REVIEW; no release inference |
| TR-037 | ANY prior DOIState | DOI_MANUAL_REVIEW | Uncertainty prevents every safe order-level conclusion | Emit exact field blocker(s), including RC-016 for availability, RC-017 for DS state, or RC-115 for ETA; independent multiple unknowns use set union. Do not erase known line facts. RC-115 does not route here when TR-034 remains independently proved |
| TR-038 | ANY prior DOIState | DOI_MONITOR | Active valid DOI condition, no current opportunity, no blocking uncertainty | Monitor |
| TR-039 | DOI_MANUAL_REVIEW | DOI_MONITOR | Human review records normal/out-of-scope progression | Emit NO_ACTION_REQUIRED; no intervention/credit |

If a known safe opportunity exists and an unrelated line is UNKNOWN, TR-035 applies with the uncertainty code unless that uncertainty makes every order-level conclusion unsafe.

## 8. DOIAlternateRelationship lifecycle

| Transition | From | To | Required guard/evidence | Required effects |
|---|---|---|---|---|
| TR-040 | ACTIVE revision n | SUPERSEDED revision n+1 | Explicit product-only successor relationship; exact current predecessor/hash | Append terminal revision with successor ID and RC-046/RC-108; preserve every prior revision |
| TR-041 | ACTIVE revision n | INVALIDATED revision n+1 | Explicit contradictory product-only evidence; exact current predecessor/hash | Append terminal revision with RC-047/RC-108; non-rediscovery causes no transition |

SUPERSEDED and INVALIDATED are terminal. Failure to rediscover a relationship causes no transition. Reactivation requires a new verified relationship record; it never rewrites the old one.

## 9. DOIAlternateObservation retention

| Transition | From | To | Required guard/evidence | Required effects |
|---|---|---|---|---|
| TR-042 | NONEXISTENT | STORED | Successful explicit alternate observation binds exact active relationship revision; current-for-action use also has OPEN Action Context | Append immutable observation/hash and atomic context link where used; nominal deadline=`calendar90(observed_at)` |
| TR-043 | STORED | DELETED | Completely de-linked observation reaches nominal deadline, or linked observation/link graph reaches the earlier nominal/current-case deadline | Atomically delete observation/context-link targets, target-owned volatile lifecycle wrappers/streams, direct indexes, and receipts; leave sealed preexisting evaluation/opportunity commitments non-resolvable/non-fresh only until case purge; never alter durable relationship. Reopen-canceled case deadline cannot delete it |

A Recheck Alternate always creates a new observation; it never extends or rewrites an older observation.

## 10. DOIIntervention and value projection

No intervention exists before action verification.

| Transition | From | To | Required guard/evidence | Required effects |
|---|---|---|---|---|
| TR-044 | NONEXISTENT | VERIFIED | Deterministic system proof of completed human action; exact scope/time/natural key/fingerprint validates | Append typed action-verification event, invoke TR-106, and project one SYSTEM_VERIFIED intervention; identical evidence no-op |
| TR-045 | NONEXISTENT | VERIFIED | Complete structured human proof of completed action; exact scope/time/natural key/fingerprint validates | Append typed HUMAN_VERIFIED event, invoke TR-106; plan/intention rejected |
| TR-045A | NONEXISTENT | VERIFIED | System/human verification proves completed DS separation with exact non-credit scope | Append/reuse DS_SEPARATION intervention; value NOT_APPLICABLE, monetary fields null, KPI zero |
| TR-046 | Value UNVERIFIED | Value VERIFIED | Exact SYSTEM_VERIFIED original Money event with valid identical currency and ISO-registry-version/scale binding | Append typed value event; recompute ledger; invoke TR-107 |
| TR-047 | Value UNVERIFIED | Value VERIFIED | Exact HUMAN_VERIFIED original Money event | Append event; estimates rejected; recompute ledger; invoke TR-107 |
| TR-048 | any value-verified state | recomputed VERIFIED/PARTIALLY_REVERSED/REVERSED | Legal exact correction or system-over-human authority event references predecessor | Preserve history; recompute authoritative original/reversals/net; invoke TR-108 where correction |
| TR-049 | any value-verified state | VERIFIED | Accepted reversal/correction reducer yields active reversal sum zero | Preserve events; exact same-currency-and-registry-binding ledger recompute |
| TR-050 | any value-verified state | PARTIALLY_REVERSED | Reducer yields reversal sum strictly between zero and authoritative original | Preserve events; duplicate logical reversal suppressed; invoke TR-109 for new reversal |
| TR-051 | any value-verified state | REVERSED | Reducer yields reversal sum equal to authoritative original | Net zero; preserve events; invoke TR-109 for new reversal |
| TR-052 | any value-verified state | recomputed VERIFIED/PARTIALLY_REVERSED/REVERSED | Valid `REVERSAL_CORRECTED` or `REVERSAL_VOIDED` references the exact current accepted predecessor under its closed natural-key/fingerprint contract | Append correction/void; never delete old reversal; recompute full ledger and atomically invoke TR-109, including zero-reversal VERIFIED |
| TR-053 | any value-verified state | recomputed VERIFIED/PARTIALLY_REVERSED/REVERSED | Accepted authoritative `ORIGINAL_VALUE_CORRECTED` after reversals references the exact current authoritative predecessor | Append correction; recompute full ledger and atomically invoke TR-108. Invalid amount/currency/evidence retains last valid projection |

Illegal:

- plan/opportunity → intervention without action verification;
- estimated human value → VERIFIED;
- reversal > authoritative original;
- deleting/recreating an intervention on case reopen;
- generating a second intervention from the same action evidence.

All intervention correction, system-over-human authority, reversal, and duplicate-evidence suppression transitions require the retained intervention/case graph. They do not cross the purge boundary.

## 11. DOIResultingOrderLink

| Transition | From | To | Required guard/evidence | Required effects |
|---|---|---|---|---|
| TR-054 | exact link NONEXISTENT; separate search absent/NOT_FOUND/AMBIGUOUS | AUTO_LINKED | Exact parent/type/child natural key and deterministic system proof/mapping | Create/reuse one exact link and invoke TR-110 for mapping revision 1; preserve any search history; if resolving its ambiguity invoke TR-093 for that cause |
| TR-055 | exact link NONEXISTENT; separate search absent/NOT_FOUND/AMBIGUOUS | HUMAN_CONFIRMED | Human verifies exact child and mapping with complete structured evidence | Create/reuse one exact link and invoke TR-110 for revision 1; preserve search history; clear only its resolved cause through TR-093 |
| TR-056 | existing exact link AMBIGUOUS | AUTO_LINKED | Later deterministic evidence resolves the exact link's current conflict revision to one mapping | Append exact-link resolution, invoke TR-110 for verified revision `n+1`, and invoke TR-093; no search state changes |
| TR-057 | existing exact link AMBIGUOUS | HUMAN_CONFIRMED | Human verifies one exact mapping against the current exact-link conflict revision | Append exact-link resolution, invoke TR-110 for verified revision `n+1`, and invoke TR-093; no search state changes |
| TR-058 | AUTO_LINKED | AMBIGUOUS | Same exact parent/type/child natural link receives contradictory canonical moved-line/quantity mapping evidence | Preserve history; invoke TR-111 and TR-092; disputed split value zero. A different child is a different natural key/search question, not RC-104. |
| TR-059 | HUMAN_CONFIRMED | AMBIGUOUS | Later system evidence conflicts and no authority rule resolves it | Preserve both; invoke TR-111/TR-092; zero disputed credit |

Same-customer identity or timing alone is never a legal guard.

Each accepted row is one ACID business transaction. TR-054/055 atomically commit the base link, logical mapping-assertion key, verification evidence record, exact-link typed event, TR-110 verified mapping revision 1, exact-link projection, any cause-keyed TR-093 clear, and the resulting zero/current KPI recomputation. TR-056/057 atomically commit their evidence/logical key, exact-link resolution event, TR-110 verified successor revision, projection, TR-093 clear, and KPI recomputation. TR-058/059 atomically commit the contradictory mapping logical key/evidence, exact-link conflict event, TR-111 conflict revision, AMBIGUOUS projection, TR-092 cause SET, and zero disputed KPI recomputation. Any component/constraint failure rolls back the entire bundle; no orphan base, event, revision, evidence, attention cause, or KPI delta survives.

## 12. DEDUPE state

| Transition | From | To | Required guard/evidence | Required effects |
|---|---|---|---|---|
| TR-060 | NOT_CANDIDATE or HUMAN_REJECTED | CANDIDATE | New complete evaluation proves one no-solution analysis and every DEDUPE blocker absent | Append typed DEDUPE event; prior rejection remains; no approval inferred |
| TR-061 | CANDIDATE for exact active `dedupe_review_id` | HUMAN_APPROVED_AWAITING_OA_VERIFICATION | Complete `DEDUPE_APPROVED`/`APPROVED` HumanFact binds candidate/evaluation/review/proof/fingerprint; no prior decision | Atomically append/reuse one HUMAN_FACT and one linked `HUMAN_APPROVED` DEDUPE event carrying the exact fact ID/hash, then project awaiting verification; any failure rolls back both; no OA write |
| TR-062 | CANDIDATE or HUMAN_APPROVED_AWAITING_OA_VERIFICATION for exact review | HUMAN_REJECTED | Initial complete `DEDUPE_REJECTED` fact, or before OA verification an exact `HUMAN_FACT_CORRECTED` rejection naming the current approval fact | Atomically append/reuse exact rejection fact and linked DEDUPE event; preserve approval history. Wrong/missing predecessor, same-review conflict, rejected-to-approved change, or changed same-kind bytes is RC-112 with zero append |
| TR-063 | HUMAN_APPROVED_AWAITING_OA_VERIFICATION | CONFIRMED | Separate later complete read-only OA snapshot proves DEDUPE note | Append only `OA_NOTE_SYSTEM_VERIFIED`; note cannot create/infer approval. Reversibly close and schedule purge; retain no note body |
| TR-064 | CONFIRMED | NOT_CANDIDATE | Explicit DEDUPE recheck proves DOI eligibility returned | Reopen same case; cancel purge; reevaluate |

DEDUPE cannot become CONFIRMED from the human approval event alone.

## 13. Human-recorded contact state

Contact records are DOI-owned, scoped to exactly one Action Context, append typed events, and never send a message.

| Transition | From | To | Required guard/evidence | Required effects |
|---|---|---|---|---|
| TR-065 | NOT_CONTACTED | CONTACT_REQUIRED | Exact accepted evaluation/opportunity deterministically requires contact | Append `CONTACT_REQUIRED_DERIVED` with SYSTEM_VERIFIED provenance and null contact occurrence; display requirement only |
| TR-066 | CONTACT_REQUIRED | CONTACT_ATTEMPTED | Human records an actual attempt | Append human event |
| TR-067 | NOT_CONTACTED | CONTACT_ATTEMPTED | Human records an attempt that occurred before state entry | Append human event; no messaging |
| TR-068 | CONTACT_ATTEMPTED | AWAITING_CUSTOMER | Human records awaiting response | Append human event |
| TR-069 | AWAITING_CUSTOMER | CUSTOMER_APPROVED | Human records explicit approval | Manual substitution gate may open if all other guards pass |
| TR-070 | AWAITING_CUSTOMER | CUSTOMER_DECLINED | Human records decline | Substitution gate closed |
| TR-071 | AWAITING_CUSTOMER | NO_RESPONSE | Human records no response | Substitution gate closed |
| TR-072 | CONTACT_ATTEMPTED | CUSTOMER_APPROVED | Human records immediate explicit approval | Manual substitution gate may open if all other guards pass |
| TR-073 | CONTACT_ATTEMPTED | CUSTOMER_DECLINED | Human records immediate decline | Substitution gate closed |
| TR-080 | CONTACT_ATTEMPTED, AWAITING_CUSTOMER, CUSTOMER_DECLINED, or NO_RESPONSE | CONTACT_ATTEMPTED | Human records a distinct later actual attempt in the same OPEN context | Append typed event; exact replay no-op; no messaging |
| TR-081 | CUSTOMER_APPROVED | CUSTOMER_DECLINED | Explicit human-recorded withdrawal/decline before action | Close readiness for that context; never reverse an already verified intervention |

No automatic transition to CUSTOMER_APPROVED exists. Re-contact transitions are factual human records only and never send a message.

## 14. WWC coordination projection

WWC state is recalculated from each complete snapshot and the versioned SyntheticCo calendar; old snapshots are unchanged.

| Transition | From | To | Required guard/evidence | Required effects |
|---|---|---|---|---|
| TR-074 | ANY prior/nonexistent | NOT_APPLICABLE | Accepted evaluation has no qualifying contact | Append typed WWC projection event with exact bindings |
| TR-075 | ANY prior/nonexistent | ACTIVE_SELF | Deterministic latest qualifying self evidence | Suppress new outreach; ongoing work allowed; append history |
| TR-076 | ANY prior/nonexistent | ACTIVE_OTHER_REP | Deterministic latest other-rep evidence before exact protected-until boundary | Block affected action/DEDUPE; preserve analysis; append history |
| TR-077 | ANY prior/nonexistent | EXPIRED_OTHER_REP | Deterministic as-of instant is at/after exact eligibility boundary | Remove only other-rep block; append history |
| TR-078 | ANY prior/nonexistent | AUTHOR_UNCERTAIN, TIMING_UNCERTAIN, or AUTHOR_AND_TIMING_UNCERTAIN | Accepted evaluation cannot establish author/time/calendar exactly | Never infer expiry; append history and invoke TR-094 |
| TR-079 | any state | same or different deterministic partition state | New accepted snapshot/calendar/structured human-fact binding | Append a new WWC event/evaluation even if state is unchanged; invoke TR-095 when uncertainty resolves; never rewrite history |

REP_TRANSFERRED is not a WWC transition. It supersedes WWC handling through the reversible case-closure transition.

## 15. Purge operation

Purge is legal only through TR-018 or TR-019 and is the irreversible case-finalization boundary. It atomically finalizes the case's then-current exact gross/reversed/net contribution into non-identifying aggregate KPI history and removes the complete per-order graph. A partial purge that leaves an Order Number, case ID, source-row link, snapshot/evaluation/lifecycle detail, opportunity, intervention or verification ID, resulting-order link, customer/order-derived hash, predecessor link, order-specific audit record, or reconstructable identity is illegal. The finalized aggregate contains no per-case delta or join key.

Non-identifying aggregate KPI records and fully de-linked product relationships are outside the deleted graph. A completely de-linked product-only DOIAlternateObservation follows TR-043 independently; a case-linked observation/action context is part of the graph removed by TR-018/TR-019 and may not survive merely because its standalone expiry is later.

Same-case reopening, reversal, partial reversal, system-over-human correction, intervention supersession, and per-order duplicate-credit prevention remain mandatory before purge and end at purge. A later case-linked correction request cannot resolve a retained target; reject it with `CASE_IDENTITY_NOT_RETAINED`, append no per-case event, and make no aggregate adjustment. Do not reconstruct identity or retain an order-specific rejection record.

If the same real-world Order Number later enters the workflow, the system has no retained fact that it was previously present. TR-007 creates a new case with a new case ID and no predecessor/reopen link. No tombstone/hash/archive lookup or cross-purge deduplication is legal, and cross-purge duplicate-credit prevention is not guaranteed. `SYN-RET-011/012` deterministically verify these two outcomes.

## 16. Fail-closed matrix checks

An implementation MUST reject:

1. a transition ID not in this matrix;
2. a transition whose guard is UNKNOWN or unsupported;
3. a transition that mutates an immutable entity;
4. a closure inferred only from source absence;
5. a purge inferred from queue exit, FULL_DS, or payment-only exclusion;
6. a relationship invalidation inferred from non-rediscovery;
7. an intervention inferred from an opportunity or plan;
8. a value verification using an estimate;
9. a contact approval inferred by the system;
10. any transition implemented by changing OA.

## 17. Provenance, relationship, Action Context, and typed-history additions

Every row appends the typed immutable event named by the governing provenance module and updates only a rebuildable projection. Stale stream sequence/predecessor/hash fails with RC-111; different canonical bytes under one digest also invokes RC-103.

| Transition | Entity/from | To/action | Deterministic guard/evidence | Required effects | Allowed codes |
|---|---|---|---|---|---|
| TR-082 | relationship NONEXISTENT | ACTIVE revision 1 | Explicit verified canonical product-only evidence passes identity/type/privacy invariants | Create stable identity and append revision; no case reverse-link | RC-107 |
| TR-083 | relationship ACTIVE revision n | ACTIVE revision n+1 | Explicit product-only fact change with exact current predecessor; not terminal | Append only; exact semantic replay no-op | RC-108; semantic invalidity RC-109; stream/revision/predecessor conflict RC-111 |
| TR-084 | Action Context NONEXISTENT | OPEN | Authorized human begins one attempt with exact retained case/evaluation/opportunity/kind | Append immutable base/creation event; zero OA action/write | RC-110 on invalid binding |
| TR-085 | Action Context OPEN | OPEN plus observation link | Successful explicit current alternate observation after context creation; exact case/opportunity/product/revision match | Append the accepted case-linked observation and immutable context-observation link atomically. Structured HumanFacts bind the context directly in their own typed event and do not use this transition. | RC-044/045; invalid RC-110 |
| TR-086 | Action Context OPEN | CLOSED_COMPLETED | One accepted same-context source matches an exact closed completion trigger in `provenance_state_contract.md` section 4; normal-progress, out-of-scope, and context-null coordination facts are not completion triggers | Append `ACTION_CONTEXT_COMPLETED` with its one legal close-reason/trigger pair; old links audit-only until purge | closed completion event/trigger only; action source may carry RC-061 or RC-062 |
| TR-087 | Action Context OPEN | CLOSED_ABANDONED or CLOSED_SUPERSEDED | Explicit abandonment or recorded superseding later attempt | Append exact close event; later attempt uses TR-084/new ID | RC-110 on invalid binding |
| TR-088 | resulting-link search NONEXISTENT, NOT_FOUND, or AMBIGUOUS | NOT_FOUND | Complete search finds no exact child; from AMBIGUOUS it disproves every prior candidate | Append distinct search evidence; exact replay no-op; split value zero; when resolving AMBIGUOUS invoke TR-093 for only that search-review cause | RC-073 |
| TR-089 | resulting-link attempt NONEXISTENT, NOT_FOUND, or AMBIGUOUS | AMBIGUOUS | New accepted unresolved candidate set/mapping | Append distinct evidence and invoke TR-092; exact replay no-op | RC-072 |
| TR-090 | link AUTO_LINKED or HUMAN_CONFIRMED | same state | New distinct corroborating evidence agrees exactly | Append corroboration; identical fingerprint no-op | RC-070/071; no duplicate code required |
| TR-091 | link HUMAN_CONFIRMED | AUTO_LINKED | Later exact deterministic system evidence agrees | Append system event; preserve human event | RC-070 |
| TR-092 | exact cause absent or other causes present | add cause-keyed RESULTING_ORDER_LINK_REVIEW | Exact ambiguous search or exact-link mapping-conflict event validates | SET complete cause and null resolver group; add only that key; disputed scope zero; condition remains until active set empty | ordinary search RC-072; exact mapping conflict RC-104 + RC-072 |
| TR-093 | exact link/search review SET active | clear that exact cause | Resolver is exact system link, human link, or complete SEARCH_NOT_FOUND event for same subject | CLEAR copies active SET cause/key, names that SET, and independently binds resolver/time; preserve every other cause/history | RC-070 system link; RC-071 human link; RC-073 negative search |
| TR-094 | exact cause absent or other causes present | add cause-keyed HUMAN_COORDINATION_REVIEW_REQUIRED | Exact uncertain WWC event validates | SET complete WWC cause and null resolver group; preserve opportunities and block only affected action/DEDUPE | RC-055 and/or RC-056 plus RC-057 |
| TR-095 | exact coordination SET active | clear that exact cause | Exact resolving `EVALUATION` or structured `HUMAN_FACT_EVENT` establishes the registered partition; the resulting WWC projection is an atomic output/binding, not the resolver | CLEAR copies active SET cause/key and independently binds resolver/time; preserve other causes; append evaluation/WWC event atomically | RC-053 ACTIVE_SELF; RC-054 ACTIVE_OTHER_REP; null only NOT_APPLICABLE or EXPIRED_OTHER_REP |
| TR-096 | DEDUPE candidate/approved/rejected | NOT_CANDIDATE | New accepted evaluation proves any blocker/opportunity | Append withdrawal; stale approval never writes OA/closes | RC-059 plus exact blocker |
| TR-097 | no accepted exact human-fact fingerprint | append HUMAN_VERIFIED fact | Complete authorized fact uses one registered closed kind/result/payload pair, including exact DEDUPE_APPROVED or DEDUPE_REJECTED | Append immutable `HUMAN_FACT_RECORDED` or exact predecessor-bound `HUMAN_FACT_CORRECTED`; DEDUPE facts participate atomically in TR-061/062; if otherwise rules-relevant invoke TR-028 | closed result code; invalid/conflicting RC-112; stream RC-111; collision RC-103 |

## 18. Source import and no-case rejection additions

| Transition | Entity/from | To/action | Deterministic guard/evidence | Required effects | Allowed codes |
|---|---|---|---|---|---|
| TR-098 | source import NONEXISTENT, or prior same-run attempt terminal non-success while run IN_PROGRESS | STARTED at next stable ordinal | TR-001 accepted invocation for ordinal 1, or explicit legal retry uses fresh opaque attempt ID, next positive ordinal, and exact attempt-owned command token | Append attempt-start with exact selected source/schema identity; run v2 stores count only, no attempt ID/manifest; exact ordinal/token/bytes replay; gap/concurrency/changed replay/post-terminal rejects before append; zero OA reads | none; stream conflict RC-111; collision RC-103 |
| TR-099 | source import STARTED | SUCCEEDED plus READY staged set | Structural validation, coherent read, identity calculation, safe batch binding, and complete compatible-TARGET_REP consolidation all succeed | In one commit append the terminal import event and one READY `DOIStagedOrder` per non-conflicted unique TARGET_REP Order Number with current-attempt refs; compatible duplicates merge with RC-006; conflicts are excluded and separately owned by TR-103; permit work only after commit | RC-006 where merged; stream RC-111 |
| TR-100 | source import STARTED | registered terminal non-success | Specific registered unreadable/schema/change/integrity failure, or deliberate pre-OA abort | Failure appends `SOURCE_IMPORT_FAILED` with RC-090 plus the exact specific code, no partial content, and zero OA; it terminalizes only the current attempt, after which an accepted exact legal pre-OA retry keeps the run IN_PROGRESS and appends the next ordinal, while absence of such a retry makes this the final failure and drives TR-004. Abort appends `SOURCE_IMPORT_ABORTED`, exact empty reasons, leaves run IN_PROGRESS, and requires a later attempt; it never creates a deadline before run terminal. | failure RC-002/009/089/091 plus RC-090; abort exact `{}`; stream conflict RC-111; collision RC-103 |
| TR-101 | coherent identity; no matching batch | append READY batch | Unique digest and canonical material verified | Append immutable batch; bind run/attempt | RC-091 on conflict |
| TR-102 | coherent identity; matching batch | bind existing READY batch | Canonical identity material/payload byte-identical | Reuse without changing batch; invocation still new run/attempt | RC-091/090 on mismatch |
| TR-103 | no rejected record and no staged order for the conflicted number | RETAINED_PENDING_RUN_TERMINAL | Under manager v0.1, coherent import proves the valid Order Number occurs on TARGET_REP and nonblank non-TARGET_REP rows | Append/reuse one natural-keyed run-local `DOIRejectedSourceRecord` with current-attempt TARGET_REP refs and RC-008; append no staged order/case/work and perform zero OA reads. RC-007 is unreachable/reserved until a future schema versions conflict-capable metadata. | RC-008; stream RC-111; collision RC-103 |
| TR-104 | rejection pending run terminal | RETAINED_UNTIL | Associated run reaches terminal status | Schedule immutable `calendar90(run.completed_at)`; batch reuse cannot extend | RC-092/096 |
| TR-105 | rejection RETAINED_UNTIL | complete absence | current instant >= exact purge eligibility; record/refs/stream locks validate | Atomically delete identity, refs, fingerprint, join keys, and the transaction-local rejection-deletion event/stream itself. RC-093 exists only inside that transaction; no rejection aggregate/reason dimension, receipt, code, hash, or tombstone survives. | transaction-local RC-093; stale/stream conflict RC-111; collision RC-103 |
| TR-113 | source batch has one or more retained explicit owner references | release all due owner references; retain unchanged batch or delete complete batch identity | Owner deletion/de-link, owner/reference foreign keys, the already-committed aggregate or caller TR-114 aggregate write set, and batch/reference locks all validate; evaluate exact `NOT EXISTS` predicate only after every due release in the same transaction | Delete due references with owners. If any reference remains, retain byte-identical batch. If none remains, delete batch ID/identity bytes/hash, TARGET_REP hash, conflict fingerprint/cardinality, counts, and every identifying event/cache/log/export; leave no tombstone and only the closed non-identifying aggregate. TR-114 exclusively owns `attempt_count +1`; an independently invoked TR-113 applies zero aggregate delta. Any failure rolls back the complete owner/reference/batch transaction and any caller-owned TR-114 delta. | success none; stale owner/reference/predicate conflict RC-111; proven collision RC-103 |
| TR-114 | terminal source-import attempt operational graph retained | complete absence after attempt retention | Associated run is terminal; attempt outcome is any closed success/failure/abort outcome; `current_instant >= source_import_attempt_purge_eligible_at = calendar90(run.completed_at)` under the bound New York policy/tzdb; exact aggregate-finalization input, attempt/batch/run owner locks, and retained-owner/last-reference predicates validate | One ACID transaction upserts only closed `DOISourceImportAggregateV2` monthly outcome count, constructs canonical transient `SOURCE_IMPORT_ATTEMPT_PURGE_FINALIZED`, deletes the attempt projection and complete attempt lifecycle/retention graph, IDs, run/source/tab/schema/actor/time/failure/fingerprint/revision/row detail, attempt-owned staged/rejected records and source refs, indexes, caches, logs, traces, temporary exports/files, backups, exceptions, dead letters, and every reverse lookup; invokes TR-105 for due rejected detail and TR-113 for due source-batch edges; separately releases the attempt's run-identity reference; deletes run identity only when its own deadline is due and no explicit non-due owner remains; and finally deletes the purge event/stream itself. Any failure rolls back the byte-complete pretransaction graph and aggregate; repeat after success is an absence no-op with no event, count, hash, lookup, or tombstone. | transaction-local success RC-114; stale owner/reference/sequence RC-111; collision RC-103; no surviving reason/event/tombstone |

## 19. Evidence, KPI, and finalization additions

| Transition | Entity/from | To/action | Deterministic guard/evidence | Required effects | Allowed codes |
|---|---|---|---|---|---|
| TR-106 | accepted retained intervention with no KPI-contribution projection | initialize exact value state plus retained row/no-row gate | TR-044/045/045A accepted exactly one intervention and keys validate; split has exact accepted child link; swap has exact replacement-line binding | Base credit set is exact-date/valid or absent `{RC-063}`, exact-date/invalid-currency `{RC-063,RC-094}`, null-date valid/absent `{RC-063,RC-099}`, and null-date/invalid-currency `{RC-063,RC-094,RC-099}`. Split with child-link state `AUTO_LINKED|HUMAN_CONFIRMED` adds RC-074 iff resulting-order-level TARGET_REP rep is missing/different/ambiguous. Substitution adds RC-075 iff replacement line-level TARGET_REP rep is missing/different/ambiguous; parent-order rep cannot substitute. Each modifier unions with every base branch. Blocked exact-date/valid branches remain one `UNVERIFIED` intervention, preserve link/line binding, create one count-1 zero-money row, and realize zero credit; other row/no-row effects follow the base table. Verified applicable rep adds neither modifier. DS is `NOT_APPLICABLE`, null money/currency, no row, and adds neither. Both modifiers, wrong intervention type, or schema-contradictory branch is RC-081 before TR-106 with no row/state append; this is distinct from accepted invalid-currency branches carrying RC-094. Never fabricate/recreate intervention or link. | Exact base-set union plus at most applicable RC-074 or RC-075; never both. DS `{}`; schema contradiction RC-081; identity/material conflict RC-102; collision RC-103 |
| TR-107 | retained contribution absent only because currency/registry was unknown, or existing value unverified/zero | current verified value | Accepted exact original VALUE has valid currency/registry and exact business action date | Atomically create first count-1 row/bucket and bind currency/registry when absent, or recompute existing row; always original action day. Null action date remains no-row. | RC-094/100/102/103 |
| TR-108 | current verified value | corrected current verified value | Legal VALUE_CORRECTION references predecessor; exact authoritative evidence | Preserve events; full-ledger recompute in original action bucket | RC-100/102/103 |
| TR-109 | any legal value/reversal contribution state | recomputed VERIFIED/PARTIALLY_REVERSED/REVERSED | TR-050/051 accepts a distinct reversal or TR-052 accepts an exact predecessor-bound correction/void; scope/value share the original's identical currency and ISO-registry-version/scale binding | Recompute once in original action bucket, including return to VERIFIED at zero; replay no-op; no second reversal/delta | RC-076/077/102/103; stale predecessor RC-111 |
| TR-110 | exact link newly accepted by TR-054/055 with no revision, or existing exact link AMBIGUOUS with current conflict revision and accepted TR-056/057 resolution | append verified mapping revision 1 or successor `n+1` | Exact natural link, proof, canonical mapping bytes, current predecessor/hash, and resolution supersession validate | Do not create a second link. Append/reuse revision 1 or one verified resolution revision; proves no action/approval/rep/value | RC-070/071; stream RC-111; collision RC-103 |
| TR-111 | exact link with verified mapping revision `n` | append CONFLICT_REVIEW revision `n+1`; project exact link AMBIGUOUS | Same natural link has contradictory exact mapping bytes and exact current predecessor | Preserve revisions; set review; zero disputed split value; no second link/overwrite | RC-104/072; stream RC-111; collision RC-103 |
| TR-112 | purge-eligible case with zero or one retained contribution | optional finalized bucket effect plus deleted graph | TR-018/019, exact optional-contribution lookup, complete reconciliation, one ACID transaction | Contribution present: move identical retained→finalized and prove total unchanged. Contribution absent: prove zero delta/no contribution. Both delete graph; mismatch rolls back | RC-088; conflict RC-101/100 |

Opportunity append under TR-027/028 is legal only when exact nonempty scope/hash, overlap key, and option ID validate. Invalid scope emits RC-097 with no opportunity. A multiple/out-of-group scenario selection emits RC-098 with no projection change. These are immutable evaluation/calculation guards, not separate mutable-state transitions.

TR-106 is an atomic KPI-projection subtransition of accepted TR-044/045/045A and never creates an intervention. TR-107–109 are KPI effects of accepted value/correction/reversal lifecycle transitions, including correction/void. TR-110 is a mapping-revision subtransition of TR-054/055/056/057 and never creates a second link; TR-111 owns the conflict revision inside the same TR-058/059 + cause-keyed TR-092 transaction. TR-112 is indivisible from TR-018/019 and has a mandatory zero-contribution branch. Therefore each business lifecycle effect has one owning transition and no subordinate effect commits independently.

The complete registry contains exactly **115** legal transition rows: TR-001 through TR-114 plus TR-045A. Every row has deterministic synthetic coverage in the acceptance and synthetic matrices; the transition traceability table maps all 115 rows to codes and oracles.

## 20. Remediation status and deferred items

The authoritative purge-finality amendment remains in force: retained-case guarantees end at irreversible purge; post-purge same-number input creates a new unlinked case; finalized aggregates do not accept later per-order correction. This remediation candidate adds complete source, provenance, relationship, Action Context, review add/clear, typed-history, idempotency, KPI, and finalization coverage. It requires independent re-audit and does not declare the specification frozen.

Potential overlap fails closed to an unavailable overall total, DS separation is a verified non-credit intervention, re-contact is human-recorded, and alternate freshness is bound to the current explicit recheck context; none is a blocker.

Deferred read-only reconnaissance/configuration details:

- OA status mappings;
- whole-order completeness proof;
- line continuity inputs;
- WWC/DEDUPE parsing and calendar source;
- current-rep mapping;
- parent/child evidence fields;
- geography/payment extraction;
- OA-only extraction selectors/field mappings. The manager workbook mapping is no longer deferred: `synthetic-doi-queue-v0.1` is locked by explicit user decision.

Deferred extraction details MUST NOT weaken guards or create implicit transitions.
