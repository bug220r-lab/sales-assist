
> **Sanitized supporting reference.** This file is a mechanically sanitized derivative of
> source material supplied for the synthetic proof of concept. Historical status/freeze
> language is nonbinding. The curated files under `specs/` govern. No production-system
> access or real-data use is authorized by this reference.

# DOI v0.1.5 Normative Opportunity Scope, KPI, and Idempotency Contract

Authority patch: v0.1.5.3 count/reference reconciliation only; opportunity, money, KPI, and retention semantics are unchanged; independent audit required; not a freeze declaration.

Status: Round-4 remediation-candidate governing module; independent re-audit required; not a freeze declaration  
Authority: 2026-08-09 independent-audit remediation, including exact RC-074/RC-075 ownership parity, plus Codex pre-implementation dry-run addendum  
Allocated additions: `RC-097` through `RC-104`; `TR-106` through `TR-112`  

This module reconciles three contract areas:

1. immutable `credit_scope`, `scenario_overlap_key`, and `scenario_option_id` for every `DOIOpportunity`;
2. realized monetary KPI persistence in daily `America/New_York` buckets with original-action attribution, deterministic upsert, and exactly-once purge finalization; and
3. canonical verification, resulting-order-link, and reversal evidence identities with fail-closed conflict behavior.

All requirements below are subordinate to the permanent Synthetic Order Portal boundary: DOI may observe, navigate, extract, validate, calculate, classify, recommend, and report through explicitly allowlisted read-only paths only. Nothing here authorizes an OA action, OA mutation, customer communication, background OA work, generic request/click helpers, or production OA access.

## 1. Canonical encoding shared by scopes, keys, and fingerprints

The following rules are normative wherever this module says `canonical`:

- Canonical serialization is RFC 8785 JSON Canonicalization Scheme encoded as UTF-8, domain-separated by an explicit version field.
- All object properties required by a fingerprint schema are present. A schema-defined inapplicable property is `null`; omission and `null` are not interchangeable.
- Enumerations use their registered uppercase ASCII spelling.
- Opaque identifiers use their exact immutable stored spelling. Row number or row position is never an identity input.
- An unordered set is converted to an array sorted by the bytewise lexicographic order of each member's own canonical UTF-8 serialization. Ordered business sequences retain their proved order.
- `CanonicalDecimal` is a plain base-10 string with no exponent, no leading `+`, no redundant leading zero, no trailing fractional zero, and no negative zero. Examples: `"0"`, `"2"`, `"2.5"`. Scope quantities MUST be greater than zero.
- Money uses the separately reconciled `{amount_decimal, currency_code, iso_4217_registry_version}` primitive. For arithmetic and bucket storage, `minor_units` is the exact arbitrary-precision integer coefficient derived without rounding from `amount_decimal` at the bound registry scale and is serialized as a base-10 integer string. Binary floating point and inferred FX are forbidden.
- A timestamp fingerprint input is the exact RFC 3339 instant normalized to UTC `Z`; a local calendar date is `YYYY-MM-DD`.
- A hash is lowercase hex `SHA-256(canonical_utf8_bytes)`.
- The retained evidence store MUST retain the canonical bytes, not merely their hash, until case purge. That byte comparison is mandatory for detecting a cryptographic hash collision.
- Every case/order/line/intervention/result-link-linked key, hash, canonical payload, and evidence record in this module is part of the per-order graph and MUST be deleted at case purge. No such fingerprint may become a tombstone or cross-purge lookup key.

## 2. Opportunity merchandise and credit scope

### 2.1 Closed types

```text
CreditScopeRole =
    MOVED_TO_RESULTING_ORDER
  | ORDERED_QUANTITY_SUBJECT_TO_REPLACEMENT
  | SAME_SKU_QUANTITY_SUBJECT_TO_RECHECK
  | PARTIAL_AVAILABLE_QUANTITY
  | DS_QUANTITY_SUBJECT_TO_SEPARATION_NON_CREDIT

ScenarioBasis =
    REALIZED_MERCHANDISE_CREDIT
  | NON_CREDIT_OPERATIONAL

PotentialSelectionState =
    SINGLETON_AUTOMATIC
  | EXPLICITLY_SELECTED
  | UNRESOLVED
```

`REALIZED_MERCHANDISE_CREDIT` applies only to opportunity types capable, under the existing intervention contract, of producing monetary credit: `FULFILLMENT_SPLIT`, `EXACT_MFG_ALTERNATE`, `MFG_CROSS_REFERENCE`, `MFG_SUPERSESSION`, and `FUNCTIONAL_ALTERNATE`. `NON_CREDIT_OPERATIONAL` applies to `DS_SEPARATION`, `EXACT_SKU_RECHECK`, and `PARTIAL_QUANTITY_REVIEW` in v0.1. The latter opportunities remain visible and scoped but never enter monetary potential or realized KPI calculations unless a future separately governed contract adds a credited intervention type.

### 2.2 `CreditScopeComponent`

Every component is immutable and contains exactly:

| Field | Type | Invariant |
|---|---|---|
| `line_snapshot_id` | `OpaqueId` | Exact line identity from the same immutable `DOIOrderSnapshot` referenced by the owning evaluation. |
| `quantity` | `CanonicalDecimal` | Exact positive quantity supported by that line snapshot and no greater than the applicable active quantity. |
| `scope_role` | `CreditScopeRole` | Must be legal for the owning opportunity type under section 2.4. |

`credit_scope` is a non-empty canonical ordered set of `CreditScopeComponent`. It is sorted by `(line_snapshot_id, scope_role, quantity)` using canonical byte order. Duplicate `(line_snapshot_id, scope_role)` entries are invalid; they are never silently summed. The owning evaluation's exact snapshot must contain every referenced line.

`credit_scope_hash` is:

```text
SHA-256(JCS({
  "scope_schema_version": "doi-credit-scope-v1",
  "components": credit_scope
}))
```

Unknown quantity, an absent immutable line identity, cross-snapshot line continuity marked `UNVERIFIED`, or a scope derived from row position cannot be repaired by guessing. If the exact required scope cannot be constructed, no `DOIOpportunity` is created for that candidate; the evaluation retains supported source findings, emits `OPPORTUNITY_SCOPE_UNPROVEN`, and contributes zero potential and realized money for that candidate.

### 2.3 Amended `DOIOpportunity` schema

Every immutable `DOIOpportunity` MUST contain:

| Field | Type | Invariant |
|---|---|---|
| `opportunity_schema_version` | `VersionId` | Literal `doi-opportunity-record/v1`. |
| `opportunity_id` | `OpaqueId` | Immutable and unique. |
| `evaluation_id` | `OpaqueId` | Exact immutable evaluation. |
| `case_id` | `OpaqueId` | Owning retained case. |
| `opportunity_type` | `OpportunityType` | Registered value. |
| `credit_scope` | non-empty ordered `CreditScopeComponent[]` | Exact immutable scope; never row-position-derived. |
| `credit_scope_hash` | `Sha256` | Must recompute exactly under section 2.2. |
| `scenario_basis` | `ScenarioBasis` | Derived solely from the opportunity type under section 2.1. |
| `scenario_overlap_key` | `Sha256` | Derived after all candidates for the evaluation are scoped under section 2.5. |
| `scenario_option_id` | `Sha256` | Distinguishes this exact option within its overlap group under section 2.6. |
| `alternate_relationship_id` | `OpaqueId?` | Required for alternate-based opportunities. |
| `alternate_relationship_revision_id` | `OpaqueId?` | Exact immutable relationship revision used; required with relationship ID. |
| `alternate_relationship_revision_content_hash` | `Sha256?` | Exact revision content hash; required with relationship ID. |
| `alternate_observation_id` | `OpaqueId?` | Present only when that exact observation was used. |
| `potential_value` | `EXACT Money` or `UNAVAILABLE` | Opportunity-level value only; never a realized value. |
| `customer_approval_required` | boolean | Existing action gate. |
| `human_compatibility_review_required` | boolean | Existing action gate. |
| `current_action_blockers` | registered-code set | Canonically ordered. |
| `created_at` | `Timestamp` | Assigned once after deterministic identity lookup; replay returns the original value. |
| `record_content_sha256` | `Sha256` | Exact full-record digest below. |

Unique constraints:

```text
UNIQUE(evaluation_id, scenario_option_id)
CHECK(credit_scope_hash = derive_credit_scope_hash(credit_scope))
CHECK(scenario_overlap_key = derive_overlap_key_for_candidate(evaluation_id, scenario_basis, credit_scope_hash))
```

`derive_overlap_key_for_candidate` operates only after every candidate for the evaluation has an exact scope. It builds the undirected overlap graph for candidates having the same `scenario_basis`, finds the one connected component containing the candidate identified by `credit_scope_hash` (or its byte-identical exact option preimage when two options intentionally share a scope), constructs that component's conservative maximum-quantity `group_credit_scope`, and returns the exact section 2.5 `scenario_overlap_key`. The sole hash input is the canonical `doi-scenario-overlap-v1` object containing `scenario_basis` plus `group_credit_scope`; evaluation ID, opportunity type, and individual scope hashes/preimages are deliberately excluded from the hash. Therefore two disconnected components in one evaluation+basis receive different keys, while every candidate in one transitive component receives the same key. A missing candidate, ambiguous duplicate preimage, incomplete graph, or component/key mismatch fails closed before opportunity persistence.

The lifecycle natural identity bytes are exactly RFC-8785/JCS `{opportunity_lifecycle_natural_schema_version:"doi-opportunity-lifecycle-natural/v1",evaluation_id,scenario_option_id}` and their digest is `SHA256(UTF8("doi-opportunity-lifecycle-natural/v1\n") || bytes)`. Resolve `UNIQUE(evaluation_id,scenario_option_id)` and byte-compare this identity before allocating `opportunity_id` or `created_at`. The full immutable opportunity object contains every schema field above except `record_content_sha256`, with nullable values explicit and all sets in their governing canonical order. `record_content_sha256 = SHA256(UTF8("doi-opportunity-record/v1\n") || UTF8(RFC8785(opportunity_without_record_content_sha256)))`. Exact identity/full bytes return the original record and creation instant; changed bytes under one identity fail closed and a proven digest collision uses RC-103.

The former `affected_line_snapshot_ids` field is derived as the unique set of `credit_scope[*].line_snapshot_id`; it is not an independent writable identity source. The former order-level exception for DS separation is removed: DS separation identifies the exact active DS line quantities in scope and remains non-credit.

### 2.4 Deterministic scope derivation by opportunity type

| Opportunity type | Exact scope rule | Role | Scenario basis |
|---|---|---|---|
| `FULFILLMENT_SPLIT` | Every exact active, non-DS, `IN_STOCK`/`FULL` line at its full snapshot-supported available quantity. This is the deterministic v0.1 split scope; no human proposal, later action, row position, or arbitrary subset changes it. Delayed lines not moved are not included. | `MOVED_TO_RESULTING_ORDER` | `REALIZED_MERCHANDISE_CREDIT` |
| `EXACT_MFG_ALTERNATE`, `MFG_CROSS_REFERENCE`, `MFG_SUPERSESSION`, `FUNCTIONAL_ALTERNATE` | The exact delayed ordered line quantity that the distinct candidate would replace. Candidate-product identity belongs in the option basis, not as a fabricated line component. | `ORDERED_QUANTITY_SUBJECT_TO_REPLACEMENT` | `REALIZED_MERCHANDISE_CREDIT` |
| `EXACT_SKU_RECHECK` | The exact ordered line quantity whose same-SKU availability/lead improvement is being rechecked. | `SAME_SKU_QUANTITY_SUBJECT_TO_RECHECK` | `NON_CREDIT_OPERATIONAL` |
| `PARTIAL_QUANTITY_REVIEW` | Only the explicitly supported available partial quantity; never the full ordered quantity. | `PARTIAL_AVAILABLE_QUANTITY` | `NON_CREDIT_OPERATIONAL` |
| `DS_SEPARATION` | Every exact active DS line quantity contemplated for separation. Non-DS lines are excluded. | `DS_QUANTITY_SUBJECT_TO_SEPARATION_NON_CREDIT` | `NON_CREDIT_OPERATIONAL` |

The v0.1 split rule emits one scope containing the complete deterministic eligible moved set. It does not enumerate arbitrary power-set combinations or accept a human-selected quantity merely to inflate or reshape potential value. A future partial-split scenario requires a separately versioned rule and immutable quantity-allocation identity.

### 2.5 Overlap-group algorithm and `scenario_overlap_key`

The overlap key represents a mutually exclusive scenario group, not order membership.

For one evaluation:

1. Construct every candidate's exact `credit_scope` and `scenario_basis`.
2. For overlap comparison, project each component to `(line_snapshot_id, quantity)` and discard action-specific `scope_role`. Opportunity type, candidate product, relationship ID, observation ID, price, and potential value are also excluded.
3. Two candidates are overlap-adjacent only when they have the same `scenario_basis` and share a `line_snapshot_id` with positive quantity. Because units within one line quantity have no immutable serial identity, scopes on the same line are conservatively overlapping unless immutable snapshot facts explicitly partition them; v0.1 defines no such partition identity.
4. Build connected components of that adjacency graph. Same-order candidates with no shared scoped line are not connected merely because their case/order is the same.
5. For each connected component, construct `group_credit_scope` by sorting unique line IDs and assigning each line the maximum exact quantity claimed by any member. The maximum is a union bound, not a sum.
6. Assign every member of that component the same key:

```text
scenario_overlap_key = SHA-256(JCS({
  "scenario_key_schema_version": "doi-scenario-overlap-v1",
  "scenario_basis": scenario_basis,
  "group_credit_scope": [
    {"line_snapshot_id": exact_id, "quantity": canonical_union_quantity}, ...
  ]
}))
```

The key deliberately excludes `opportunity_type`. Therefore two different opportunity types capable of claiming the same merchandise credit share one overlap key. Connected-component grouping is intentionally conservative: it may decline to sum a combination that has not been proven disjoint, but it cannot double count a shared line.

### 2.6 `scenario_option_id`

For each opportunity:

```text
scenario_option_id = SHA-256(JCS({
  "scenario_option_schema_version": "doi-scenario-option-v1",
  "scenario_overlap_key": scenario_overlap_key,
  "opportunity_type": opportunity_type,
  "credit_scope_hash": credit_scope_hash,
  "alternate_relationship_id": alternate_relationship_id_or_null,
  "alternate_relationship_revision_id": alternate_relationship_revision_id_or_null,
  "alternate_relationship_revision_content_hash": revision_hash_or_null,
  "alternate_observation_id": alternate_observation_id_or_null,
  "potential_value": canonical_exact_or_unavailable_wrapper,
  "customer_approval_required": boolean,
  "human_compatibility_review_required": boolean
}))
```

Identical candidate content within one evaluation reuses one option; it does not create a duplicate opportunity. Different candidate relationships or different exact scopes produce different option IDs even when they share the same overlap key.

### 2.7 Potential-value selection and aggregation

Potential selection is a calculation input, not proof of a human action and not a `DOIIntervention`. The calculation accepts at most one `scenario_option_id` for each `scenario_overlap_key`.

- A one-member credit-bearing group is `SINGLETON_AUTOMATIC`.
- A multi-member credit-bearing group with exactly one valid explicit selection is `EXPLICITLY_SELECTED`.
- A multi-member group with no selection is `UNRESOLVED`: all opportunity values remain visible, but group and combined potential are `UNAVAILABLE` with existing `POTENTIAL_OVERLAP_UNRESOLVED` (`RC-087`).
- More than one selection, or a selected option not belonging to that group/evaluation, is rejected with `SCENARIO_OPTION_SELECTION_CONFLICT` (`RC-098`); no selected total is emitted.
- Disjoint resolved groups may be summed only when both ISO-4217 currency code and bound registry version/scale are identical. Results are returned as separate currency-and-registry segments. Mixed currencies or registry bindings are never summed, converted, rescaled, or used for one combined monetary headline; use the currency rules allocated by the source/retention reconciliation (`RC-094` and `RC-095`).
- `NON_CREDIT_OPERATIONAL` groups never contribute monetary potential.

## 3. Daily realized-KPI persistence contract

### 3.1 Closed constants and contribution class

```text
KPI_SCHEMA_VERSION = "doi-kpi-daily-v1"
KPIBucketGrain = LOCAL_CALENDAR_DAY
KPI_TIMEZONE = "America/New_York"
KPIContributionInterventionType = FULFILLMENT_SPLIT | PRODUCT_SUBSTITUTION
KPIActionProvenance = SYSTEM_VERIFIED | HUMAN_VERIFIED
```

`DS_SEPARATION` remains a verified operational intervention with `NOT_APPLICABLE` money and contributes no monetary KPI row. `ALL`, weekly, monthly, quarterly, and yearly rows are query rollups and MUST NOT be persisted as competing source-of-truth buckets.

### 3.2 Action attribution

A credit-bearing intervention has a nullable immutable business `action_occurred_at`, separate from the required evidence fact time. Only a non-null exact action instant may create a retained monetary row. Its attribution fields, when present, are:

```text
action_attribution_timezone = "America/New_York"
action_attribution_local_date = local_date(action_occurred_at, America/New_York)
```

The attribution date is the local date on which the verified human action occurred, not the date on which a later recheck, value verification, correction, reversal, or purge ran. Every later accepted value/reversal event updates the contribution in that original action-attribution bucket. `action_verification_provenance` is equally immutable: it is the provenance of the first accepted action-verification event that creates the logical intervention. A later byte-compatible SYSTEM or HUMAN proof is corroboration only, regardless of direction; it may append distinct evidence but never changes the intervention's first-event provenance, contribution identity, bucket dimension, count, or money.

If a credit-bearing action is otherwise verified but no exact action instant can establish one local date, the intervention remains in operational history with value status `UNVERIFIED`, `INTERVENTION_VALUE_UNVERIFIED` (`RC-063`), and `KPI_ACTION_DATE_UNVERIFIED` (`RC-099`). Its monetary KPI contribution is zero and no retained monetary contribution row is created. A proof, review, ingestion, or record timestamp MUST NOT be substituted. `DS_SEPARATION` is non-credit, uses `NOT_APPLICABLE`, and receives neither RC-063 nor RC-099 merely because no monetary attribution instant is needed.

### 3.3 `DOIRetainedKPIContribution`

This is a mutable projection rebuilt from immutable retained evidence. It is case-linked and deleted at purge.

| Field | Type | Invariant |
|---|---|---|
| `retained_kpi_contribution_id` | `Sha256` | Deterministic identity hash below; deleted at purge. |
| `retained_kpi_contribution_id_canonical_bytes` | `bytes` | Exact retained identity preimage below; deleted at purge. |
| `kpi_schema_version` | `VersionId` | Literal `doi-kpi-daily-v1`. |
| `case_id` | `OpaqueId` | Retained owning case. |
| `intervention_id` | `OpaqueId` | One credit-bearing verified intervention. |
| `action_occurred_at` | `Timestamp` | Exact immutable action instant. |
| `action_attribution_local_date` | `Date` | Derived under section 3.2 and immutable. |
| `currency_code` | ISO-4217 code | Exact credit currency; never inferred or converted. |
| `iso_4217_registry_version` | `VersionId` | Exact registry/scale binding used to derive integer coefficients; immutable. |
| `intervention_type` | `KPIContributionInterventionType` | Immutable contribution class. |
| `action_verification_provenance` | `KPIActionProvenance` | Immutable action provenance dimension. |
| `verified_intervention_count` | integer | Exactly `1`. |
| `gross_minor_units` | integer | Current authoritative original realized value, or `0` while exact value is unverified. |
| `reversed_minor_units` | integer | Sum of distinct current authoritative reversal effects, or `0` while value is unverified. |
| `net_minor_units` | integer | `gross_minor_units - reversed_minor_units`. |
| `authoritative_ledger_hash` | `Sha256` | Hash of the exact retained accepted event projection; retry/idempotency input, deleted at purge. |
| `projection_revision` | positive integer | Increments only when the authoritative projection changes. |
| `updated_at` | `Timestamp` | Audit time; never attribution time. |

Unique key: `UNIQUE(kpi_schema_version, intervention_id)`.

The identity bytes are exactly UTF-8 RFC-8785/JCS of `{retained_kpi_contribution_id_schema_version:"doi-retained-kpi-contribution-id/v1",kpi_schema_version,intervention_id}`. `retained_kpi_contribution_id = SHA256(UTF8("doi-retained-kpi-contribution-id/v1\n") || retained_kpi_contribution_id_canonical_bytes)`. Enforce both `UNIQUE(kpi_schema_version,intervention_id)` and `UNIQUE(retained_kpi_contribution_id)`. Lookup by the tuple occurs before insert; exact bytes/hash reuse the row, same digest with different bytes is RC-103, and any tuple/digest/preimage disagreement appends no projection or bucket delta.

Invariants:

```text
0 <= reversed_minor_units <= gross_minor_units
net_minor_units = gross_minor_units - reversed_minor_units
```

TR-106 reduces value state independently from KPI-row eligibility and rep-proof eligibility:

1. **Value-state reducer**
   - A verified `FULFILLMENT_SPLIT` or `PRODUCT_SUBSTITUTION` without an exact accepted value is `UNVERIFIED`, always carries `RC-063`, and has zero realized monetary contribution.
   - For a `FULFILLMENT_SPLIT` that already has one exact `AUTO_LINKED` or `HUMAN_CONFIRMED` child link, missing/different/ambiguous resulting **order-level** TARGET_REP-rep proof adds `RC-074`. The exact link and mapping remain unchanged; the code blocks value only and creates no link.
   - For a `PRODUCT_SUBSTITUTION`, missing/different/ambiguous replacement **line-level** TARGET_REP-rep proof adds `RC-075`. A parent order-level rep never substitutes. The replacement-line binding remains unchanged; the code blocks value only and creates no link.
   - A verified `DS_SEPARATION` is `NOT_APPLICABLE`, has every monetary/currency field null, creates no monetary contribution row, and never carries `RC-063`.
2. **KPI eligibility for credit-bearing interventions only**
   - Null/missing exact `action_occurred_at` adds `RC-099`, creates no row/date bucket, and never substitutes proof/review/record time.
   - A supplied invalid currency code, scale, representation, or registry binding adds `RC-094`; no `Money`, contribution, bucket, aggregate, USD fallback, FX, conversion, or rescale is persisted.
   - Exact date with absent/not-yet-known currency creates no row and no RC-094. Later TR-107 may create the first row only from exact accepted Money with a valid immutable currency/registry binding.
   - Exact date with valid currency/registry creates exactly one retained contribution immediately with count 1 and gross/reversed/net all exact zero until value verification.

These reducers are orthogonal. The exhaustive accepted mapping is:

| Intervention branch | Action date | Currency/registry input | Value status | Retained monetary row | Exact TR-106-owned reason set |
|---|---|---|---|---|---|
| credit-bearing | exact | valid | `UNVERIFIED` | exactly one count-1, zero-money row | `{RC-063}` |
| credit-bearing | exact | absent/not-yet-known | `UNVERIFIED` | none | `{RC-063}` |
| credit-bearing | exact | invalid | `UNVERIFIED` | none; invalid Money not persisted | `{RC-063, RC-094}` |
| credit-bearing | null | valid or absent | `UNVERIFIED` | none | `{RC-063, RC-099}` |
| credit-bearing | null | invalid | `UNVERIFIED` | none; invalid Money not persisted | `{RC-063, RC-094, RC-099}` |
| `DS_SEPARATION` | exact or null | every monetary/currency field null | `NOT_APPLICABLE` | none | `{}` |

For each credit-bearing row above, let its displayed set be `B`. Apply exactly one intervention-type/rep-proof modifier:

| Exact intervention/rep branch | Required precondition | Exact additive modifier | Exact effect |
|---|---|---|---|
| `FULFILLMENT_SPLIT`, rep verified | One already-exact child link is `AUTO_LINKED` or `HUMAN_CONFIRMED`; resulting order-level rep is exactly verified TARGET_REP | `{}` | Use `B`; RC-074 and RC-075 are absent. An exact accepted value proceeds only through its ordinary value owner. |
| `FULFILLMENT_SPLIT`, rep unverified | Same exact child-link precondition; resulting order-level TARGET_REP rep is missing, different, or ambiguous | `{RC-074}` | Exact TR-106 set is `B ∪ {RC-074}`; intervention remains `UNVERIFIED`; realized credit is zero; link/mapping state is unchanged; RC-075 is absent. With exact date and valid currency, the retained row is one count-1 zero-money row and the exact set is `{RC-063, RC-074}`. |
| `PRODUCT_SUBSTITUTION`, rep verified | Exact replacement-line binding; replacement line-level rep is exactly verified TARGET_REP | `{}` | Use `B`; RC-074 and RC-075 are absent. An exact accepted value proceeds only through its ordinary value owner. |
| `PRODUCT_SUBSTITUTION`, rep unverified | Exact replacement-line binding; replacement line-level TARGET_REP rep is missing, different, or ambiguous; parent order-level rep is ignored | `{RC-075}` | Exact TR-106 set is `B ∪ {RC-075}`; intervention remains `UNVERIFIED`; realized credit is zero; replacement-line binding is unchanged; RC-074 is absent. With exact date and valid currency, the retained row is one count-1 zero-money row and the exact set is `{RC-063, RC-075}`. |
| `DS_SEPARATION` | Closed null monetary payload | `{}` | Exact reason set remains `{}`; no RC-063/074/075/099 and no monetary row. |

`B ∪ modifier` is ordinary set union, so the rep code combines with RC-094 and/or RC-099 exactly when those independent predicates are true. RC-074 and RC-075 are mutually exclusive. A fixture that supplies both, uses a rep code for the wrong intervention type, lacks the required exact link/replacement-line binding, or otherwise contradicts its branch fails the action/TR-106 bundle with RC-081 before append; it creates no row and changes no link, intervention, value, or KPI state.

The reason sets exclude the already accepted parent action-proof code RC-061 or RC-062. A non-null DS monetary/currency field violates the closed DS payload and rejects the action/TR-106 bundle with RC-081; RC-094 additionally applies only when the input purports to construct invalid Money. DS never becomes `UNVERIFIED` and never receives RC-063, RC-074, or RC-075.

Invalid monetary material does not invalidate independent proof that the human action occurred. The DOI-local intervention remains one operational verified action with `UNVERIFIED` value, while the invalid monetary object is rejected before Money/contribution/bucket persistence or aggregation. This is the sole v0.1.5 policy; no retry creates a second intervention.

Once a retained row exists, a different currency or registry version is an integrity conflict, not an FX conversion, rescaling, or bucket move.

`authoritative_ledger_hash` is exact, not an implementation-selected reducer checksum. Its closed input object is `{ledger_schema_version:"doi-retained-kpi-ledger/v1",intervention_id,action_occurrence_id,action_occurred_at,action_attribution_local_date,currency_code,iso_4217_registry_version,intervention_type,action_verification_provenance,accepted_action_event_manifest,accepted_value_event_manifest,verified_intervention_count,gross_minor_units,reversed_minor_units,net_minor_units}`. Each manifest is an array of exact `{event_id,event_type,stream_sequence,content_sha256,logical_evidence_key_id,material_effect_fingerprint}` members sorted strictly by `stream_sequence`; duplicate/skipped sequence is invalid. Null action time cannot reach this object because it creates no row. `authoritative_ledger_hash = SHA256(UTF8("doi-retained-kpi-ledger/v1\n") || UTF8(RFC8785(object)))`. `projection_revision` and `updated_at` are excluded from this semantic reducer hash and remain ordinary projection audit fields. Missing/extra member, wrong order/domain, stale event hash, or projection-value mismatch is RC-101 (and RC-100 for bucket identity mismatch) with no delta/finalization.

### 3.4 `DOIAggregateKPIDailyBucket`

This is a non-identifying persisted leaf bucket. It contains no case/order/line/intervention/result-link/source reference, evidence fingerprint, canonical evidence bytes, or drill-through key.

| Field | Type | Invariant |
|---|---|---|
| `daily_bucket_id` | `Sha256` | Deterministic key hash below. |
| `kpi_schema_version` | `VersionId` | Literal `doi-kpi-daily-v1`. |
| `bucket_grain` | enum | Literal `LOCAL_CALENDAR_DAY`. |
| `timezone` | string | Literal `America/New_York`. |
| `local_calendar_date` | `Date` | Attribution date. |
| `period_start` | `Timestamp` | Inclusive UTC instant of local midnight starting the date. |
| `period_end` | `Timestamp` | Exclusive UTC instant of local midnight starting the next date. |
| `currency_code` | ISO-4217 code | One exact currency segment. |
| `iso_4217_registry_version` | `VersionId` | Exact registry/scale segment; never inferred or rewritten. |
| `intervention_type` | `KPIContributionInterventionType` | Leaf type only; no stored `ALL`. |
| `action_verification_provenance` | `KPIActionProvenance` | Leaf provenance only; no stored `ALL`. |
| `retained_verified_intervention_count` | non-negative integer | Sum of current retained projections assigned to this key. |
| `retained_gross_minor_units` | non-negative integer | Current retained gross. |
| `retained_reversed_minor_units` | non-negative integer | Current retained reversed. |
| `retained_net_minor_units` | non-negative integer | Current retained net. |
| `finalized_verified_intervention_count` | non-negative integer | Irreversibly finalized purged contribution count. |
| `finalized_gross_minor_units` | non-negative integer | Irreversibly finalized purged gross. |
| `finalized_reversed_minor_units` | non-negative integer | Irreversibly finalized purged reversed. |
| `finalized_net_minor_units` | non-negative integer | Irreversibly finalized purged net. |
| `bucket_revision` | non-negative integer | Increments on a committed retained upsert or finalization. |
| `computed_at` | `Timestamp` | Last committed computation time. |

Persisted unique identity:

```text
UNIQUE(
  kpi_schema_version,
  bucket_grain,
  timezone,
  local_calendar_date,
  currency_code,
  iso_4217_registry_version,
  intervention_type,
  action_verification_provenance
)

daily_bucket_id = SHA-256(JCS({
  "kpi_schema_version": "doi-kpi-daily-v1",
  "bucket_grain": "LOCAL_CALENDAR_DAY",
  "timezone": "America/New_York",
  "local_calendar_date": local_calendar_date,
  "currency_code": currency_code,
  "iso_4217_registry_version": iso_4217_registry_version,
  "intervention_type": intervention_type,
  "action_verification_provenance": action_verification_provenance
}))
```

`period_start` and `period_end` are derived checks, not independent identity inputs. A stored row whose derived key, date, boundaries, currency, registry version/scale, or class disagree fails closed with `KPI_BUCKET_IDENTITY_CONFLICT` (`RC-100`).

Bucket totals are always:

```text
total_count    = retained_count    + finalized_count
total_gross   = retained_gross    + finalized_gross
total_reversed= retained_reversed + finalized_reversed
total_net     = retained_net      + finalized_net
total_net     = total_gross - total_reversed
```

### 3.5 Local-day boundaries and rollups

For local date `D`:

```text
period_start = instant(D 00:00:00, America/New_York)
period_end   = instant((D + 1 local calendar date) 00:00:00, America/New_York)
```

The interval is `[period_start, period_end)`. It may be 23, 24, or 25 elapsed hours; fixed 24-hour arithmetic is forbidden.

Weekly, monthly, quarterly, and yearly views group these daily leaf rows by local calendar dates, exact currency, exact registry version, and requested contribution dimensions. They are recomputed rollups and are not persisted source-of-truth records. A monetary response across multiple currencies or registry/scale bindings is a segmented map/table; no cross-version rescaling, FX rate, or cross-currency total is inferred.

### 3.6 Deterministic retained upsert

On each accepted action/value/correction/reversal evidence event while the case is retained:

1. Reduce the full accepted immutable event ledger for the target intervention; never apply an unverified event delta directly to a bucket.
2. Derive the immutable action date, currency, ISO-registry version/scale, contribution class, amounts, and `authoritative_ledger_hash`.
3. In one ACID transaction, lock the existing `DOIRetainedKPIContribution` row (if any) and its target daily bucket.
4. If the stored ledger hash equals the newly derived hash and the canonical projection bytes match, return an idempotent no-op.
5. If the immutable bucket identity fields would change, fail with `KPI_BUCKET_IDENTITY_CONFLICT`; do not subtract from one bucket and silently move to another.
6. Compute `delta = new_projection - old_projection` for count/gross/reversed/net. Upsert the daily bucket by its unique key and add that delta only to the four retained fields.
7. Store the new retained projection and increment both revisions. Commit together.

Database retry after a committed transaction is a no-op because the ledger hash and projection bytes match. A crash/rollback before commit changes neither row. Concurrent writers serialize on the deterministic contribution and bucket keys. No update path uses binary floating point.

### 3.7 Exactly-once purge finalization

Case purge and KPI finalization are one indivisible ACID transaction:

1. Lock the retained case, all its retained KPI contributions, and every affected daily bucket.
2. Re-reduce accepted evidence and verify every stored `authoritative_ledger_hash`, bucket key, and amount. Any mismatch emits `KPI_FINALIZATION_CONFLICT` (`RC-101`), rolls back the complete transaction, and leaves both case and buckets unchanged.
3. For each contribution, subtract its current count/gross/reversed/net from the bucket's retained fields and add exactly the same values to the bucket's finalized fields.
4. Verify each bucket's total fields are unchanged by the transfer and all amount invariants hold.
5. Delete every retained contribution and the entire per-order graph, including all fingerprints and canonical evidence payloads, in the same commit.

No per-case finalization marker, delta, fingerprint, or join key survives. Exactly-once behavior comes from the atomic boundary: failure before commit rolls back both transfer and deletion; after commit the case/contribution identity no longer exists and a retry changes no bucket. Existing `AGGREGATE_KPI_FINALIZED` (`RC-088`) records only the non-identifying aggregate audit condition permitted by the governing purge contract.

After purge, the daily finalized component is final. A late correction/reversal is rejected transiently with existing `CASE_IDENTITY_NOT_RETAINED` (`RC-086`), changes no bucket, and leaves no order-specific rejection record. A later new case for the same real-world Order Number has no historical link and follows its own new action dates and contributions; cross-purge deduplication is neither attempted nor guaranteed.

## 4. Canonical verification and idempotency model

### 4.1 Two-level retained evidence identity

The persistence model MUST distinguish a logical business event from the exact proof record used to verify it.

#### `DOILogicalEvidenceKey`

| Field | Type | Invariant |
|---|---|---|
| `logical_evidence_key_id` | `OpaqueId` | Case-linked retained identity. |
| `case_id` | `OpaqueId` | Exact retained case. |
| `logical_event_kind` | closed enum | `ACTION`, `ORIGINAL_VALUE_VERIFIED`, `ORIGINAL_VALUE_CORRECTED`, `REVERSAL_VERIFIED`, `REVERSAL_CORRECTED`, `REVERSAL_VOIDED`, `RESULTING_ORDER_LINK`, or `RESULTING_ORDER_LINK_SEARCH`. These names exactly match the governed logical effect families. |
| `natural_key_schema_version` | `VersionId` | Domain-specific version below. |
| `natural_key_canonical_bytes` | bytes | Exact canonical natural-key payload. |
| `natural_key_fingerprint` | `Sha256` | Domain-separated hash of those bytes under the selected row below. |
| `material_effect_schema_version` | `VersionId` | Domain-specific version below. |
| `material_effect_canonical_bytes` | bytes | Canonical quantities/values/link effect, excluding audit-only proof source and provenance. |
| `material_effect_fingerprint` | `Sha256` | Domain-separated hash of material-effect bytes under the selected row below. |
| `created_at` | `Timestamp` | DOI record time. |

Unique key: `UNIQUE(case_id, logical_event_kind, natural_key_fingerprint)`.

#### `DOIVerificationEvidenceRecord`

```text
EvidenceEventKind = ACTION_SYSTEM_VERIFIED | ACTION_HUMAN_VERIFIED |
  ORIGINAL_VALUE_SYSTEM_VERIFIED | ORIGINAL_VALUE_HUMAN_VERIFIED |
  ORIGINAL_VALUE_CORRECTED_SYSTEM | ORIGINAL_VALUE_CORRECTED_HUMAN |
  REVERSAL_SYSTEM_VERIFIED | REVERSAL_HUMAN_VERIFIED |
  REVERSAL_CORRECTED_SYSTEM | REVERSAL_CORRECTED_HUMAN |
  REVERSAL_VOIDED_SYSTEM | REVERSAL_VOIDED_HUMAN |
  RESULT_LINK_SYSTEM_VERIFIED | RESULT_LINK_HUMAN_VERIFIED |
  RESULT_LINK_CORROBORATION_SYSTEM | RESULT_LINK_CORROBORATION_HUMAN |
  RESULT_LINK_CONFLICT_SYSTEM | RESULT_LINK_CONFLICT_HUMAN |
  RESULT_LINK_SEARCH_NOT_FOUND_SYSTEM | RESULT_LINK_SEARCH_AMBIGUOUS_SYSTEM

CanonicalProofReference {
  source_system: ORDER_ADMIN | synthetic_CATALOG | MANUFACTURER_SOURCE |
                 HUMAN_ATTESTATION,
  object_type: ORDER_SNAPSHOT | INTERVENTION_ACTION_PROOF | VALUE_PROOF |
               REVERSAL_PROOF | RESULTING_ORDER_REFERENCE |
               LINE_QUANTITY_CONTINUITY | RESULTING_ORDER_SEARCH_PROOF |
               HUMAN_ATTESTATION,
  immutable_object_id: string,
  revision_id: string,
  content_sha256: Sha256
}
```

| Field | Type | Invariant |
|---|---|---|
| `verification_evidence_id` | `OpaqueId` | Immutable evidence record. |
| `evidence_record_schema_version` | `VersionId` | Literal `doi-verification-evidence-record/v1`. |
| `logical_evidence_key_id` | `OpaqueId` | One logical business event. |
| `case_id` | `OpaqueId` | Must match logical key. |
| `event_kind` | `EvidenceEventKind` | Exact tagged proof kind. |
| `subject_type` | `INTERVENTION`, `RESULT_LINK`, or `RESULT_LINK_SEARCH` | Closed domain subject class. |
| `subject_id` | `OpaqueId` | Exact retained subject; linkage only, excluded from semantic fingerprint. |
| `typed_event_id` | `OpaqueId` | Exact typed event linked after semantic fingerprint calculation. |
| `typed_event_content_sha256` | `Sha256` | Full typed-event hash; not part of the semantic evidence fingerprint. |
| `fingerprint_schema_version` | `VersionId` | Domain-separated version. |
| `canonical_evidence_payload_bytes` | bytes | Exact canonical payload under sections 4.2–4.3. |
| `evidence_fingerprint` | `Sha256` | Hash of those bytes. |
| `provenance` | `SYSTEM_VERIFIED` or `HUMAN_VERIFIED` | Exact proof provenance. |
| `actor_kind` | `SYSTEM` or `HUMAN` | Must match the event-kind suffix/provenance. |
| `actor_id` | `OpaqueId?` | Required exactly for HUMAN; null exactly for SYSTEM. |
| `evidence_occurred_at` | `Timestamp` | Required proof/attestation fact time; never substitutes for nullable business action time. |
| `recorded_at` | `Timestamp` | DOI record time, not action attribution. |
| `verification_evidence_content_sha256` | `Sha256` | Full evidence-record hash, computed after the typed-event hash and excluded from the typed event. |

Unique key: `UNIQUE(case_id, event_kind, evidence_fingerprint)`.

`canonical_evidence_payload_bytes` is exactly UTF-8 RFC-8785/JCS for this closed semantic object, with no extension keys: `{evidence_payload_schema_version:"doi-verification-evidence-payload-v1",event_kind,case_id,natural_key_fingerprint,material_effect_fingerprint,subject_type,evidence_occurred_at,proof_refs,exact_value,supersedes_value_event_id,corrects_reversal_event_id,natural_link_key_sha256,mapping_content_sha256,search_state,search_candidate_set_sha256}`. `evidence_occurred_at` is the required timestamp at which the proof/attestation fact occurred; it is not a substitute for nullable business `action_occurred_at`. `proof_refs` is a canonical ordered nonempty set of the exact `CanonicalProofReference` object; every field is required/nonempty, no extension key is legal, and nullable fields elsewhere are explicit nulls. Each typed event's field named `evidence_refs` is a schema alias/input for this exact `proof_refs` value: after validation and canonical set ordering the two are byte-identical, and only `proof_refs` is serialized in the semantic evidence object. A mismatch rejects both records atomically. Storage-generated logical/evidence/typed-event/subject IDs and every record/event content hash are deliberately excluded; the natural-key fingerprint supplies the deterministic pre-creation action/search/link identity. `evidence_fingerprint = SHA256(UTF8("doi-verification-evidence/v1\n") || canonical_evidence_payload_bytes)`; `fingerprint_schema_version` is literal `doi-verification-evidence/v1`.

The acyclic commit order is normative: allocate record IDs and validate the logical key; compute semantic evidence bytes/fingerprint; compute the typed-event full hash using the evidence-record ID/fingerprint but not evidence-record full hash; then compute `verification_evidence_content_sha256 = SHA256(UTF8("doi-verification-evidence-record/v1\n") || UTF8(RFC8785(evidence_record_without_verification_evidence_content_sha256)))`, including the typed-event ID/hash. Commit the typed event, evidence record, and bidirectional deferred foreign keys atomically. The typed event MUST NOT contain `verification_evidence_content_sha256`; the semantic fingerprint MUST NOT contain either record's generated ID or content hash.

The tagged-field matrix is exhaustive:

| Evidence kinds | Logical kind / subject | Required non-null tagged fields | Fields that MUST be null |
|---|---|---|---|
| `ACTION_*` | `ACTION` / `INTERVENTION` | intervention subject ID, typed action-event ID/hash, stable action occurrence ID, required evidence occurrence time, nonempty exact proof refs; business action time is exact Timestamp or explicit null | value/predecessor, natural-link/mapping, search state |
| `ORIGINAL_VALUE_*_VERIFIED` | `ORIGINAL_VALUE_VERIFIED` / `INTERVENTION` | intervention ID, typed value-event ID/hash, exact Money, occurrence | both predecessor fields, natural-link/mapping, search state |
| `ORIGINAL_VALUE_CORRECTED_*` | `ORIGINAL_VALUE_CORRECTED` / `INTERVENTION` | intervention ID, typed event ID/hash, exact Money, exact superseded value-event ID, occurrence | reversal predecessor, natural-link/mapping, search state |
| `REVERSAL_*_VERIFIED` | `REVERSAL_VERIFIED` / `INTERVENTION` | intervention ID, typed event ID/hash, exact positive Money, occurrence | both predecessor fields, natural-link/mapping, search state |
| `REVERSAL_CORRECTED_*` | `REVERSAL_CORRECTED` / `INTERVENTION` | intervention ID, typed event ID/hash, exact positive Money, exact reversal predecessor, occurrence | original predecessor, natural-link/mapping, search state |
| `REVERSAL_VOIDED_*` | `REVERSAL_VOIDED` / `INTERVENTION` | intervention ID, typed event ID/hash, exact reversal predecessor, occurrence | exact value, original predecessor, natural-link/mapping, search state |
| `RESULT_LINK_SYSTEM_VERIFIED`, `RESULT_LINK_HUMAN_VERIFIED`, `RESULT_LINK_CORROBORATION_*`, `RESULT_LINK_CONFLICT_*` | `RESULTING_ORDER_LINK` / `RESULT_LINK` | exact link ID, typed link-event ID/hash, natural-link key, mapping hash, occurrence | value/predecessors, search state/candidate-set hash |
| `RESULT_LINK_SEARCH_*` | `RESULTING_ORDER_LINK_SEARCH` / `RESULT_LINK_SEARCH` | exact search ID, typed search-event ID/hash, exact `NOT_FOUND` or `AMBIGUOUS`, exact candidate-set hash, occurrence | value/predecessors, natural-link key, mapping hash |

System-suffixed kinds require SYSTEM/SYSTEM_VERIFIED/null actor ID; human-suffixed kinds require HUMAN/HUMAN_VERIFIED/non-null actor ID. The record's logical key ID, case, natural/material fingerprints, typed event ID/kind/content hash, evidence fingerprint, actor/provenance, and typed event's corresponding fields MUST all match exactly. Any unregistered kind, wrong logical-kind mapping, missing/extra/non-null-forbidden field, mismatched typed record, or bad JCS domain is schema rejection with no accepted evidence/business effect; stream mismatch uses RC-111 and a proven digest collision uses RC-103.

Proof-reference source/object pairs are an exhaustive tagged union:

| Evidence kinds | Every allowed `(source_system, object_type)` pair |
|---|---|
| `ACTION_SYSTEM_VERIFIED` | `(ORDER_ADMIN, ORDER_SNAPSHOT)`, `(ORDER_ADMIN, INTERVENTION_ACTION_PROOF)` |
| `ORIGINAL_VALUE_SYSTEM_VERIFIED`, `ORIGINAL_VALUE_CORRECTED_SYSTEM` | `(ORDER_ADMIN, VALUE_PROOF)` |
| `REVERSAL_SYSTEM_VERIFIED`, `REVERSAL_CORRECTED_SYSTEM`, `REVERSAL_VOIDED_SYSTEM` | `(ORDER_ADMIN, REVERSAL_PROOF)` |
| `RESULT_LINK_SYSTEM_VERIFIED`, `RESULT_LINK_CORROBORATION_SYSTEM`, `RESULT_LINK_CONFLICT_SYSTEM` | `(ORDER_ADMIN, RESULTING_ORDER_REFERENCE)`, `(ORDER_ADMIN, LINE_QUANTITY_CONTINUITY)` |
| `RESULT_LINK_SEARCH_NOT_FOUND_SYSTEM`, `RESULT_LINK_SEARCH_AMBIGUOUS_SYSTEM` | `(ORDER_ADMIN, RESULTING_ORDER_SEARCH_PROOF)` |
| every human-suffixed kind | `(HUMAN_ATTESTATION, HUMAN_ATTESTATION)` only |

Every proof set is nonempty and every member must use one pair in its selected row. A human attestation immutable object/revision MUST bind the same authorized actor, stable occurrence ID, and evidence occurrence time; actor-only evidence is invalid. All system proof refs must be immutable source facts appropriate to the event and content-hash verified. `synthetic_CATALOG` and `MANUFACTURER_SOURCE` are registered source-system values for other product-knowledge schemas but have no allowed pair in this verification-evidence union. Every unlisted cross-product—including ORDER_ADMIN with HUMAN_ATTESTATION, SyntheticCo/manufacturer with VALUE/REVERSAL/link/search objects, or a human suffix with a system object—plus missing revision/hash, empty proof set, arbitrary SourceRef, or extra proof field is schema rejection.

“Match” uses this exhaustive mapping; the two kind strings are not required to be identical:

| Typed event kind | Required provenance | `EvidenceEventKind` |
|---|---|---|
| `INTERVENTION_ACTION_SYSTEM_VERIFIED` | SYSTEM_VERIFIED | `ACTION_SYSTEM_VERIFIED` |
| `INTERVENTION_ACTION_HUMAN_VERIFIED` | HUMAN_VERIFIED | `ACTION_HUMAN_VERIFIED` |
| `ORIGINAL_VALUE_VERIFIED` | SYSTEM_VERIFIED / HUMAN_VERIFIED | `ORIGINAL_VALUE_SYSTEM_VERIFIED` / `ORIGINAL_VALUE_HUMAN_VERIFIED` |
| `ORIGINAL_VALUE_CORRECTED` | SYSTEM_VERIFIED / HUMAN_VERIFIED | `ORIGINAL_VALUE_CORRECTED_SYSTEM` / `ORIGINAL_VALUE_CORRECTED_HUMAN` |
| `REVERSAL_VERIFIED` | SYSTEM_VERIFIED / HUMAN_VERIFIED | `REVERSAL_SYSTEM_VERIFIED` / `REVERSAL_HUMAN_VERIFIED` |
| `REVERSAL_CORRECTED` | SYSTEM_VERIFIED / HUMAN_VERIFIED | `REVERSAL_CORRECTED_SYSTEM` / `REVERSAL_CORRECTED_HUMAN` |
| `REVERSAL_VOIDED` | SYSTEM_VERIFIED / HUMAN_VERIFIED | `REVERSAL_VOIDED_SYSTEM` / `REVERSAL_VOIDED_HUMAN` |
| `SYSTEM_LINK_VERIFIED` | SYSTEM_VERIFIED | `RESULT_LINK_SYSTEM_VERIFIED` |
| `HUMAN_LINK_VERIFIED` | HUMAN_VERIFIED | `RESULT_LINK_HUMAN_VERIFIED` |
| `CORROBORATING_EVIDENCE_APPENDED` | SYSTEM_VERIFIED / HUMAN_VERIFIED | `RESULT_LINK_CORROBORATION_SYSTEM` / `RESULT_LINK_CORROBORATION_HUMAN` |
| `EVIDENCE_CONFLICT` | SYSTEM_VERIFIED / HUMAN_VERIFIED | `RESULT_LINK_CONFLICT_SYSTEM` / `RESULT_LINK_CONFLICT_HUMAN` |
| `SEARCH_NOT_FOUND` | SYSTEM_VERIFIED only | `RESULT_LINK_SEARCH_NOT_FOUND_SYSTEM` |
| `CANDIDATES_AMBIGUOUS` | SYSTEM_VERIFIED only | `RESULT_LINK_SEARCH_AMBIGUOUS_SYSTEM` |

Any other typed-kind/provenance/evidence-kind triple is schema-invalid and appends neither record. Search evidence is SYSTEM-only in v0.1.5; human exact resolution uses `HUMAN_LINK_VERIFIED` on the exact-link stream, never a human search event.

Insert rules:

1. Same evidence fingerprint plus byte-identical payload is idempotent: return the existing record and apply no business/KPI effect.
2. Same evidence fingerprint with different canonical bytes is a detected cryptographic collision and causes `EVIDENCE_FINGERPRINT_INTEGRITY_FAILURE` (`RC-103`). Roll back the affected transaction; no prior valid projection changes. A registered pre-OA source/integrity gate may fail the run with RC-090, but a post-OA order collision marks that order exception and the otherwise coherent run completes `COMPLETED_WITH_EXCEPTIONS`; it never retroactively becomes `FAILED`.
3. Same natural-key fingerprint with different natural-key bytes is also `RC-103`.
4. Same logical natural key and byte-identical material effect, but different compatible proof/provenance, may append corroborating evidence; it applies the business effect exactly once through the one logical key.
5. For ACTION/original-value/reversal logical kinds, the same stable occurrence natural key with a different material effect is `EVIDENCE_NATURAL_KEY_CONFLICT` (`RC-102`). Fail closed, retain the last valid projection, create no duplicate intervention/value/reversal, and contribute zero from the disputed delta. Each exact-link mapping assertion instead has its own logical key containing the base natural-link hash plus mapping-content hash. A contradictory M2 therefore appends under a distinct valid logical key; the base-link reducer compares M2 against current M1 and routes solely RC-104 + RC-072 through TR-111 without mutating M1 (plus RC-103 only for collision and RC-111 only for stream-envelope conflict). Legal search events use the stable search identity plus `search_occurrence_id` as natural key; evidence time, kind, state, and candidates are material and may change the stable search projection only through a new occurrence.
6. A legitimate later correction/void is not disguised as a conflicting rewrite. It uses `ORIGINAL_VALUE_CORRECTED`, `REVERSAL_CORRECTED`, or `REVERSAL_VOIDED`, has its own natural event identity, and explicitly references the exact accepted predecessor required below.

### 4.2 Action/value/reversal canonical payloads

Every verification evidence fingerprint binds, where applicable:

- exact `case_id`;
- exact event/action type;
- target `intervention_id` or deterministic pre-creation intervention key;
- `intervention_type`;
- exact `credit_scope_hash` and scoped line/quantity components;
- exact action/value/reversal occurrence instant;
- exact immutable `snapshot_id` and snapshot content hash;
- the closed nonempty `CanonicalProofReference` set, including exact source system, object type, immutable object ID, revision ID, and content SHA-256 as required by the selected evidence kind;
- normalized resulting-order natural key and mapping content fingerprint when applicable;
- replacement-line continuity identity when applicable;
- exact Money when applicable;
- `supersedes_event_id` when applicable; and
- exact verification provenance.

Source identity for human evidence is the immutable DOI human-attestation record ID and revision; free text is never an identity. Missing schema-defined fields are `null`, not omitted.

Natural keys and material effects use this closed registry. In every row the bytes are UTF-8 RFC-8785/JCS of the exact shown object, including its literal `*_schema_version` member and every explicit null. The fingerprint formula is `SHA256(UTF8(schema_version || "\n") || canonical_bytes)`. No extra/omitted field or alternate domain is accepted.

| Logical kind | Natural schema and exact object | Material schema and exact object |
|---|---|---|
| `ACTION` | `doi-action-natural/v1`: `{natural_key_schema_version,case_id,logical_kind:"ACTION",intervention_type,action_occurrence_id}` | `doi-action-material/v1`: `{material_effect_schema_version,credit_scope_hash,credit_scope_components,action_occurred_at,resulting_order_natural_key_or_null,replacement_target_or_null,normalized_action_relationship}`; `action_occurred_at` is exact Timestamp or explicit null. |
| `ORIGINAL_VALUE_VERIFIED` | `doi-original-value-natural/v1`: `{natural_key_schema_version,case_id,intervention_id,logical_kind:"ORIGINAL_VALUE_VERIFIED",logical_occurrence_id}` | `doi-original-value-material/v1`: `{material_effect_schema_version,value_effective_at,exact_money,credited_scope_hash}`. |
| `ORIGINAL_VALUE_CORRECTED` | `doi-original-value-correction-natural/v1`: `{natural_key_schema_version,case_id,intervention_id,logical_kind:"ORIGINAL_VALUE_CORRECTED",logical_occurrence_id}` | `doi-original-value-correction-material/v1`: `{material_effect_schema_version,correction_effective_at,supersedes_value_event_id,replacement_exact_money,credited_scope_hash}`. |
| `REVERSAL_VERIFIED` | `doi-reversal-natural/v1`: `{natural_key_schema_version,case_id,intervention_id,logical_kind:"REVERSAL_VERIFIED",logical_occurrence_id}` | `doi-reversal-material/v1`: `{material_effect_schema_version,reversal_occurred_at,reversed_scope_components,mapping_content_sha256,exact_money}`. |
| `REVERSAL_CORRECTED` | `doi-reversal-correction-natural/v1`: `{natural_key_schema_version,case_id,intervention_id,logical_kind:"REVERSAL_CORRECTED",logical_occurrence_id}` | `doi-reversal-correction-material/v1`: `{material_effect_schema_version,correction_effective_at,corrects_reversal_event_id,replacement_reversed_scope_components,mapping_content_sha256,replacement_exact_money}`. |
| `REVERSAL_VOIDED` | `doi-reversal-void-natural/v1`: `{natural_key_schema_version,case_id,intervention_id,logical_kind:"REVERSAL_VOIDED",logical_occurrence_id}` | `doi-reversal-void-material/v1`: `{material_effect_schema_version,void_effective_at,corrects_reversal_event_id}`. |
| `RESULTING_ORDER_LINK` | `doi-result-link-mapping-assertion-v1`: `{natural_key_schema_version,base_natural_link_sha256,mapping_content_sha256}`; the base link remains uniquely identified by its separate parent/type/child bytes/hash | `doi-result-link-mapping-v1`: the exact closed stored `{mapping_schema_version,moved_components}` mapping object. Every compatible M1 proof reuses M1; contradictory M2 gets a distinct key and RC-104 + RC-072/TR-111; later exact M2 resolution may reuse M2. |
| `RESULTING_ORDER_LINK_SEARCH` | `doi-result-link-search-event-natural/v1`: `{natural_key_schema_version,case_id,logical_kind:"RESULTING_ORDER_LINK_SEARCH",search_natural_key_sha256,search_occurrence_id}` | `doi-result-link-search-event-material/v1`: `{material_effect_schema_version,search_evidence_at,search_kind,search_state,candidate_set_sha256,candidate_set}`; NOT_FOUND requires the exact empty set, AMBIGUOUS a nonempty canonical set. |

`action_occurrence_id`, `logical_occurrence_id`, and `search_occurrence_id` are nonempty stable proof/attestation occurrence identities, not generated DOI storage IDs. The selected `CanonicalProofReference` set MUST bind the same occurrence identity; each proof's independently required `evidence_occurred_at` belongs only in that proof's evidence fingerprint, never in the logical natural key. `action_occurrence_id` identifies the one claimed OA action independently of disputed time/target/link/scope/quantity; all compatible proofs of that action reuse it. `logical_occurrence_id` is unique to the original-value/reversal/correction/void fact occurrence. Search occurrence identity is unique within its stable search. Reusing one occurrence identity with any changed material member invokes RC-102 for action/value/reversal or the governed search conflict/reducer path; allocating a second business effect is forbidden. A predecessor that is stale, foreign, or not the current legal chain target is rejected first with RC-111 and never reaches material-conflict handling.

Occurrence allocation is globally guarded before natural-key allocation. The ACTION occurrence registry enforces `UNIQUE(case_id,action_occurrence_id)` and stores the exact ACTION natural-key bytes/hash; reuse with a different intervention type or any different natural bytes is RC-102 and cannot allocate a second intervention. A shared value/reversal occurrence registry enforces `UNIQUE(case_id,intervention_id,logical_occurrence_id)` across all five kinds `ORIGINAL_VALUE_VERIFIED|ORIGINAL_VALUE_CORRECTED|REVERSAL_VERIFIED|REVERSAL_CORRECTED|REVERSAL_VOIDED`; cross-kind reuse or changed natural bytes is RC-102 and appends no value/reversal event. Exact same natural and material bytes are replay; same occurrence with changed material bytes is RC-102. Stream sequence/predecessor validation runs first and exclusively routes RC-111 when it fails. Search occurrences analogously enforce `UNIQUE(resulting_order_link_search_id,search_occurrence_id)` and then apply the governed search reducer/material-conflict rules.

The full evidence payload additionally includes immutable snapshot/source/revision identities and provenance, so human and system proofs of the same material action may have different evidence fingerprints but one logical business effect. If their material quantities/value disagree, the natural-key conflict rule applies unless the later record is a separately legal explicit correction/supersession event.

`ORIGINAL_VALUE_CORRECTED` must reference the exact current authoritative original-value event. `REVERSAL_CORRECTED` and `REVERSAL_VOIDED` must reference the exact current event in one accepted reversal chain; a target already superseded/voided, a cross-intervention target, or a stale stream predecessor fails with `RC-111` and applies no KPI delta. Exact fingerprint plus byte-identical canonical payload is idempotent. Same logical correction/void natural key with different material bytes is `RC-102`; a proven same-digest/different-bytes condition is `RC-103`.

The authoritative reversal projection sums one current material effect per distinct logical `REVERSAL_VERIFIED` chain after applying its accepted correction/void events, not one amount per evidence fingerprint. Consequently duplicate evidence, including compatible system and human corroboration, cannot create a second reversal. Existing `CREDIT_DUPLICATE_SUPPRESSED` (`RC-076`) records the no-op where an audit code is required; unresolved reversal conflicts also retain existing `REVERSAL_VERIFICATION_REQUIRED` (`RC-077`).

### 4.3 Resulting-order natural identity and mapping fingerprint

Add closed type:

```text
ResultingOrderRelationshipType = FULFILLMENT_SPLIT_CHILD
ResultingOrderMappingState = UNVERIFIED | VERIFIED | CONFLICT_REVIEW
```

An exact `DOIResultingOrderLink` has:

| Field | Type | Invariant |
|---|---|---|
| `resulting_order_link_id` | `OpaqueId` | Stable while case retained. |
| `parent_case_id` | `OpaqueId` | Exact retained parent case. |
| `relationship_type` | `ResultingOrderRelationshipType` | Registered value. |
| `child_order_number` | `OrderNumber` | Exact child Order Number; required for an exact link. |
| `natural_key_canonical_bytes` | bytes | JCS payload below. |
| `natural_key_fingerprint` | `Sha256` | Exact domain-separated hash below; every `natural_link_key_sha256`/`base_natural_link_sha256` field is an alias of this value. |
| `mapping_state` | `ResultingOrderMappingState` | Current projection from immutable revisions. |
| `current_link_revision_id` | `OpaqueId?` | Latest accepted exact mapping revision. |
| `state` | existing link state | `AUTO_LINKED`, `HUMAN_CONFIRMED`, or `AMBIGUOUS`; `NOT_FOUND` is an attempt outcome, not an exact-link identity. |

Natural key:

```text
natural_key_canonical_bytes = UTF8(RFC8785({
  "natural_key_schema_version": "doi-result-link-natural-v1",
  "parent_case_id": parent_case_id,
  "relationship_type": relationship_type,
  "child_order_number": child_order_number
}))
natural_key_fingerprint = SHA256(
  UTF8("doi-result-link-natural-v1\n") || natural_key_canonical_bytes
)
```

Unique key: `UNIQUE(parent_case_id, relationship_type, child_order_number)`.

An immutable `DOIResultingOrderLinkRevision` contains:

- the complete common immutable event envelope from `provenance_state_contract.md` section 1.2 with `stream_namespace=RESULT_LINK_MAPPING`;
- `event_type = RESULT_LINK_MAPPING_VERIFIED | RESULT_LINK_MAPPING_CONFLICT_RECORDED | RESULT_LINK_MAPPING_CONFLICT_RESOLVED`;
- `resulting_order_link_revision_id`, the exact alias of envelope `event_id`;
- `link_revision_schema_version`, equal to envelope `schema_version`;
- `resulting_order_link_id`;
- `stream_id` derived from `resulting_order_link_id` under `doi-event-stream-id-v1`;
- monotonically increasing `revision_number`, exactly equal to `stream_sequence`;
- exact `previous_event_id` and `previous_event_content_sha256`, matching the prior accepted mapping revision/full-event hash except at revision 1;
- `mapping_state`;
- canonical ordered `moved_components`, each an exact `MovedLineMappingComponent {parent_line_snapshot_id,child_line_snapshot_id,quantity}` with exact parent line, exact child line when proved, and exact positive quantity;
- stored canonical `mapping_content_bytes = UTF8(RFC8785({"mapping_schema_version":"doi-result-link-mapping-v1","moved_components":...}))` and `mapping_content_sha256 = SHA256(UTF8("doi-result-link-mapping-v1\n") || mapping_content_bytes)`; every field elsewhere named mapping content hash/fingerprint is an exact alias of this one value;
- exact verification evidence record ID/fingerprint and provenance;
- `created_at`, exactly equal to envelope `recorded_at`;
- full-event `content_sha256`, distinct from the semantic mapping-content fingerprint; and
- optional `supersedes_link_revision_id` for an explicitly authorized resolution.

`RESULT_LINK_MAPPING_VERIFIED` is legal only for revision 1. `RESULT_LINK_MAPPING_CONFLICT_RECORDED` is legal only for TR-111 and `mapping_state=CONFLICT_REVIEW`. `RESULT_LINK_MAPPING_CONFLICT_RESOLVED` is legal only for TR-110 after TR-056/057, `mapping_state=VERIFIED`, and a non-null `supersedes_link_revision_id` equal to the exact current conflict revision. Event type, mapping state, transition owner, actor/provenance, revision/sequence, and predecessor fields are one closed cross-field contract. The store enforces `UNIQUE(resulting_order_link_revision_id)` and `UNIQUE(stream_id,stream_sequence)`; mismatch rejects with RC-111 and no projection/KPI change.

Rediscovery of the same natural link with an identical mapping fingerprint and identical mapping bytes is idempotent. Exact-link creation appends verified revision 1 through TR-110. Once an exact mapping exists, contradictory moved-line or quantity evidence for the same natural link appends revision `n+1` with `mapping_state=CONFLICT_REVIEW`, exact current predecessor, and the contradictory canonical mapping/evidence through TR-111; it emits `RESULTING_ORDER_LINK_EVIDENCE_CONFLICT` (`RC-104`), projects the exact link to `AMBIGUOUS`, adds existing `RESULTING_ORDER_LINK_REVIEW` (`RC-072`), preserves immutable history, and contributes zero disputed split credit. It MUST NOT silently overwrite, merge, or create a second link.

Later exact conflict resolution appends verified revision `n+1` through TR-110. It requires an already-existing exact link in `AMBIGUOUS`, the exact current `CONFLICT_REVIEW` predecessor revision/hash, an exact authorized system/human resolution event, and `supersedes_link_revision_id` equal to that predecessor. The base-link resolution owner is TR-056 or TR-057; TR-110 owns only the subordinate mapping append. Search-state `AMBIGUOUS`/`NOT_FOUND` never enters this revision stream. A stale predecessor/sequence fails with `RC-111`; an injected mapping-hash collision with different bytes is fatal `RC-103`.

`AMBIGUOUS` and `NOT_FOUND` attempt evidence may be retained as case-linked immutable events but cannot invent a child Order Number or exact natural link. Exact human confirmation creates/reuses the natural link only when the exact child Order Number is supplied.

### 4.4 Purge and privacy edges

At case purge delete:

- `DOILogicalEvidenceKey` rows and both canonical payloads/hashes;
- `DOIVerificationEvidenceRecord` rows and evidence fingerprints;
- result-link natural keys, revisions, mapping fingerprints, exact child Order Number, and moved-line mappings;
- opportunity scope hashes, overlap keys, and option IDs;
- retained KPI contribution identities and ledger hashes.

Only the non-identifying daily aggregate bucket survives. It contains no per-case fingerprint or contribution marker. Reusable product relationship knowledge may survive only under its separate complete de-linking contract; an opportunity or evidence fingerprint must never be copied into that durable product record.

## 5. Added reason codes

These eight IDs are allocated to this reconciliation. Existing `RC-076`, `RC-077`, `RC-086`, `RC-087`, and `RC-088`, plus cross-slice `RC-094`/`RC-095`, remain in force.

| ID | Code | Class | Owner | Deterministic trigger and effect |
|---|---|---|---|---|
| `RC-097` | `OPPORTUNITY_SCOPE_UNPROVEN` | BLOCK | `DOIEvaluation` candidate | Required immutable line identity/quantity or continuity is not proved. Create no `DOIOpportunity` for that candidate; emit no candidate potential/credit. |
| `RC-098` | `SCENARIO_OPTION_SELECTION_CONFLICT` | BLOCK | potential calculation | More than one option is selected for one overlap key, or a selection does not belong to that evaluation/group. Reject selection and emit no group/combined total. |
| `RC-099` | `KPI_ACTION_DATE_UNVERIFIED` | BLOCK | `DOIIntervention` | Credit-bearing verified action lacks an exact occurrence instant/local attribution date. Retain operational intervention evidence but create no monetary KPI contribution. `DS_SEPARATION`/`NOT_APPLICABLE` is excluded. |
| `RC-100` | `KPI_BUCKET_IDENTITY_CONFLICT` | BLOCK | KPI persistence | Derived immutable daily-bucket date/bounds/currency/class disagrees with a stored contribution or bucket. Roll back; do not move or duplicate money. |
| `RC-101` | `KPI_FINALIZATION_CONFLICT` | BLOCK | purge transaction | Pre-finalization ledger/bucket projection does not reconcile. Roll back both KPI transfer and case deletion; finalization is not partial. |
| `RC-102` | `EVIDENCE_NATURAL_KEY_CONFLICT` | BLOCK | action/value/reversal verification ledger | Same canonical ACTION/original-value/reversal key carries a different material effect without a legal explicit correction event. Preserve the last valid projection; apply no disputed effect. Exact resulting-link mapping conflicts are excluded and use RC-104 + RC-072. |
| `RC-103` | `EVIDENCE_FINGERPRINT_INTEGRITY_FAILURE` | SAFETY | persistence boundary | Same SHA-256 value maps to different canonical bytes for any natural key/evidence/mapping payload. Roll back the affected transaction and change no projection. Pre-OA registered source/integrity gate may fail the run; post-OA collision is an order exception and coherent run completes with exceptions. |
| `RC-104` | `RESULTING_ORDER_LINK_EVIDENCE_CONFLICT` | BLOCK | `DOIResultingOrderLink` | Same parent/type/child natural link has contradictory exact moved-line/quantity mapping. Set conflict review, add `RC-072`, and count zero disputed split credit. |

TR-106 uses five existing/cross-slice reasons under exact closed predicates. `RC-063` means a verified **credit-bearing** action lacks an exact verified value and is forbidden for `DS_SEPARATION`/`NOT_APPLICABLE`. `RC-074` applies only to a split with an already-exact child link whose resulting order-level TARGET_REP-rep proof is missing/different/ambiguous. `RC-075` applies only to a substitution whose replacement line-level TARGET_REP-rep proof is missing/different/ambiguous; parent order rep is never sufficient. `RC-094` means a supplied ISO code, scale, representation, or bound registry fails validation; absent pre-value currency is not invalid. `RC-099` means a **credit-bearing** action's exact business instant is null/missing; no proof, review, ingestion, or record time can substitute and no date bucket is created. The five predicates combine only as Section 3.3 specifies; RC-074 and RC-075 never coexist.

## 6. Required transition additions

Exact-repeat idempotent no-ops are not state transitions. All rows append immutable evidence and reduce projections; none mutates prior events or OA.

| Transition | From | To | Required guard/evidence | Required effects |
|---|---|---|---|---|
| `TR-106` | accepted retained intervention with no KPI-contribution projection | exact Section 3.3 value/rep state plus retained row/no-row result | `TR-044/045/045A` accepted exactly one intervention; natural/evidence keys validate; value is not yet exactly verified; a split rep branch has one already-exact child link and a substitution rep branch has one exact replacement-line binding | Credit-bearing is `UNVERIFIED` + RC-063. Date/currency produces exact base set `B`; split missing/different/ambiguous resulting order-level TARGET_REP rep adds only RC-074, while substitution missing/different/ambiguous replacement line-level TARGET_REP rep adds only RC-075. Exact date/valid binding creates one count-1 zero-money row even when rep-blocked; absent/invalid/null branches retain the Section 3.3 no-row effects. Link/replacement binding never changes. DS is `NOT_APPLICABLE`, null money, no row, and no RC-063/074/075. Contradictory/wrong-type branches are RC-081 before append. Never create/recreate intervention. |
| `TR-107` | contribution absent only because currency/registry was unknown, or existing value unverified/zero | current verified value | Accepted exact original `VALUE` event has valid currency/registry, fingerprint checks pass, and exact business action date exists | If absent, create the first count-1 retained row/bucket and immutably bind currency/registry; otherwise recompute the full ledger. Always use the original action-day bucket. Null action date remains no-row. |
| `TR-108` | current verified value | corrected current verified value | Legal explicit `VALUE_CORRECTION` references the superseded event; exact system-authoritative or otherwise governed evidence; no collision | Preserve both events; recompute full ledger and same original action bucket; never attribute to correction date. |
| `TR-109` | any legal value/reversal contribution state | recomputed `VERIFIED`, `PARTIALLY_REVERSED`, or `REVERSED` contribution | Parent TR-050/051 accepts a new distinct reversal, or TR-052 accepts an exact predecessor-bound `REVERSAL_CORRECTED`/`REVERSAL_VOIDED`; exact Money/scope and cumulative reversal validate | Recompute once and update the same original action bucket, including a zero-reversal return to VERIFIED. Exact replay applies no second delta; natural-key conflict uses `RC-102`; stale predecessor uses `RC-111`; collision uses `RC-103`. |
| `TR-110` | (a) exact link newly accepted by `TR-054/055` with no mapping revision, or (b) existing exact link `AMBIGUOUS` with current `CONFLICT_REVIEW` revision and accepted `TR-056/057` resolution | append verified mapping revision 1 or exact successor revision `n+1` | Exact parent/type/child natural link, permitted proof, canonical mapping bytes, current predecessor/hash, and resolution supersession validate | Do not create a second link. Append/reuse revision 1 or append one verified resolution revision; link alone proves no action, approval, rep, or value. |
| `TR-111` | exact link with verified mapping revision `n` | append `CONFLICT_REVIEW` revision `n+1`; exact-link projection becomes `AMBIGUOUS` | Same natural link is rediscovered with contradictory exact mapping bytes and exact current predecessor | Preserve every revision; emit `RC-104` + `RC-072`; block disputed split value; no second link or silent overwrite. |
| `TR-112` | purge-eligible case, with zero or one retained KPI contribution | atomically finalized optional contribution plus deleted per-order graph | Existing legal case purge (`TR-018`/`TR-019`), exact optional-contribution lookup, full ledger reconciliation, and one ACID transaction | If a contribution exists, move identical amounts retained → finalized in original daily buckets and prove total unchanged. If none exists, assert no contribution/key/bucket delta and finalize zero. In both branches delete the complete graph; any mismatch rolls back with `RC-101`. |

The opportunity-scope and potential-selection rules are immutable evaluation/calculation rules rather than lifecycle transitions. Matrix sections for evaluation output MUST nevertheless add the guards: an opportunity append is legal only with a valid `credit_scope_hash`, overlap key, and option ID; an invalid/multiple scenario selection produces no projection change. `TR-106` is an atomic KPI-projection subtransition of `TR-044/045/045A`; `TR-110` is a mapping-revision subtransition of `TR-054/055/056/057`; neither duplicates its owning lifecycle effect.

## 7. Deterministic synthetic oracle additions

These tests are additions, not replacements. Old counts are not quotas. The final package must derive and report the new total after all agent drafts are merged. Fixtures are fictional, offline, and contain no copied customer/order identity.

### 7.1 Scope and overlap (`SYN-SCOPE-*`)

| ID | Fixture/action | Exact oracle |
|---|---|---|
| `SYN-SCOPE-001` | Split candidate moves line `L2` qty `1` and line `L1` qty `2`; input enumeration is reversed twice | Both runs persist scope ordered `L1/2`, `L2/1`, the same `credit_scope_hash`, the same overlap key, and the same option ID. Row order changes nothing. |
| `SYN-SCOPE-002` | `EXACT_MFG_ALTERNATE` and `FUNCTIONAL_ALTERNATE` target the same delayed `L1` qty `2` through different relationship revisions | Both have `ORDERED_QUANTITY_SUBJECT_TO_REPLACEMENT`, one shared `scenario_overlap_key`, and two different `scenario_option_id` values; opportunity type is absent from the overlap-key payload. |
| `SYN-SCOPE-003` | Ordered qty `5`, explicitly available partial qty `2` | `PARTIAL_QUANTITY_REVIEW.credit_scope` contains exactly `L1` qty `2`, never qty `5`; basis is `NON_CREDIT_OPERATIONAL` and monetary potential is excluded. |
| `SYN-SCOPE-004` | In one evaluation and one basis, create candidates over `L1`, `L1+L2`, `L2`, and a disconnected `L9`; table-drive candidate input order and derive each key with its exact scope hash/preimage | `L1/L1+L2/L2` receive one identical transitive-component key; `L9` receives a different key. Evaluation ID/type are absent from component bytes. A global one-key-for-basis result, wrong-component candidate, ambiguous duplicate preimage, or partial graph fails closed. Only resolved, non-overlapping, same-currency+registry components may sum. |
| `SYN-SCOPE-005` | Options scope `L1` qty `2`, `L1` qty `5`, and `L2` qty `1` under one basis | The first two share one group/key whose union quantity for `L1` is `5`; the `L2` option has a different key. Quantities `2+5` are never summed as a union. |
| `SYN-SCOPE-006` | Alternate candidate has no exact line identity, or cross-snapshot continuity is `UNVERIFIED` | No `DOIOpportunity` is created for that candidate; emit `RC-097`; potential and realized contribution are zero. |
| `SYN-SCOPE-007` | Two alternate options in one overlap group; no explicit selection | Both remain visible; group and combined potential are `UNAVAILABLE` with `RC-087`; no guessed maximum/sum is emitted. |
| `SYN-SCOPE-008` | Two options are submitted as selected for one overlap key | Reject calculation with `RC-098`; emit no selected group total and change no opportunity/intervention state. |
| `SYN-SCOPE-009` | Select exactly one of two overlapping USD options and include one resolved disjoint USD group | Potential equals selected option plus disjoint group exactly once. The unselected option remains visible and contributes zero to combined potential. |
| `SYN-SCOPE-010` | Resolved opportunities are EUR 10,000 minor units and USD 12,000 minor units | Return two currency segments; no combined number and no FX. Emit/apply `RC-095` if a caller requests one mixed-currency total. |

### 7.2 Daily KPI/upsert/finalization (`SYN-KPI-*`)

| ID | Fixture/action | Exact oracle |
|---|---|---|
| `SYN-KPI-001` | Table-drive SYSTEM_VERIFIED action at `2026-01-31T23:30:00-05:00` with (a) known currency/registry zero row and (b) no row because currency/registry is initially unknown; accept exact SYSTEM original Money on `2026-02-03` | TR-046 appends `ORIGINAL_VALUE_VERIFIED`/RC-064 and invokes TR-107. It updates (a) or creates (b) once with immutable currency/registry. Both belong to local date `2026-01-31`; no February contribution exists. |
| `SYN-KPI-002` | Human value USD 50,000 minor units; later legal system correction USD 40,000 | Same original action bucket changes retained gross/net from 50,000 to 40,000; count remains 1; no correction-date bucket is created. |
| `SYN-KPI-003` | Original USD 40,000 then distinct reversal USD 10,000 reviewed on a later date | Same original action bucket is gross 40,000, reversed 10,000, net 30,000, count 1. |
| `SYN-KPI-004` | Build the accepted action/value ledger in alternate input enumeration orders against fixed `doi-retained-kpi-contribution-id/v1` and `doi-retained-kpi-ledger/v1` vectors, then replay the identical accepted ledger/upsert ten times; separately force tuple/digest/preimage disagreement | Canonical identity bytes produce the exact contribution ID and canonical manifests produce the exact ledger hash. One retained contribution row, one daily bucket key, count 1, unchanged amounts, unchanged projection after the first commit. Any identity/manifest order/member/domain/tamper mismatch rejects without a delta; digest collision routes RC-103. |
| `SYN-KPI-005` | Bucket local date `2026-03-08` (spring DST) | `period_start=2026-03-08T05:00:00Z`, `period_end=2026-03-09T04:00:00Z`; elapsed duration 23 hours. |
| `SYN-KPI-006` | Bucket local date `2026-11-01` (fall DST) | `period_start=2026-11-01T04:00:00Z`, `period_end=2026-11-02T05:00:00Z`; elapsed duration 25 hours. |
| `SYN-KPI-007` | Persist seven daily rows then request weekly/monthly views | Views equal grouping of daily rows; persistence contains no weekly/monthly/quarterly/yearly source row and no stored `ALL` contribution row. |
| `SYN-KPI-008` | Same date/type has USD and EUR under registry v2026 plus a separately bound USD under registry v2027 | Three unique registry/currency leaf buckets; no key collision or silent rescaling; all segmented totals are exact; cross-currency/cross-version scalar total is absent and no FX call/rate exists. |
| `SYN-KPI-009` | Credit-bearing action has exact applicable TARGET_REP-rep proof, a stable occurrence ID, and required proof evidence time but nullable business `action_occurred_at` is null | Keep one operational intervention with value `UNVERIFIED`; exact TR-106 reason set is `{RC-063,RC-099}`; create no retained monetary KPI contribution and add zero money. Proof/review/record timestamp is not substituted; RC-074/075 are absent because the applicable rep proof is exact. |
| `SYN-KPI-010` | Case legally reopens before purge using byte-equal `PriorClosureRetentionBindingV1` in both the reopen and purge-cancellation lifecycle payloads, then the unchanged intervention is reevaluated | Same retained contribution/bucket remains count 1 with unchanged money; no second credit. A missing/mismatched prior-closure binding rejects the lifecycle bundle before append and cannot alter the contribution. |
| `SYN-KPI-011` | Table-drive purge of (a) a valued retained row count 1/gross 40,000/reversed 10,000/net 30,000, (b) an unverified-value retained row with exact applicable TARGET_REP-rep proof, exact action date/currency/registry and count 1/money zero/RC-063, and (c) no retained row for DS or missing date/currency | (a) moves identical count/money retained to finalized; (b) moves count 1 and zero money identically and has neither RC-074 nor RC-075; (c) proves the optional row absent and changes no bucket. DS is NOT_APPLICABLE with no RC-063; missing-date credit is UNVERIFIED with RC-063+099. All branches complete TR-112 and graph deletion atomically with no case/fingerprint/zero marker. |
| `SYN-KPI-012` | Inject failure after retained subtraction but before finalized addition/deletion | Entire transaction rolls back: case and contribution remain; both bucket components equal pre-attempt values. Retry without injection produces exactly `SYN-KPI-011` once. |
| `SYN-KPI-013` | Tamper stored contribution ledger hash or bucket identity immediately before purge | Emit `RC-101` (and `RC-100` for identity mismatch), delete nothing, finalize nothing, and leave all pre-attempt amounts unchanged. |
| `SYN-KPI-014` | Retry purge after the successful atomic commit | No retained case/contribution resolves; finalized values remain unchanged and no marker/tombstone is created. |
| `SYN-KPI-015` | Credit-bearing verified action, exact applicable TARGET_REP-rep proof, exact action date, valid currency/registry, no verified value | Value `UNVERIFIED`; exact reason set `{RC-063}`; one retained count-1 row with all money zero; realized contribution zero; RC-074/075 are absent. |
| `SYN-KPI-016` | Verified `DS_SEPARATION` with closed null monetary payload | Value `NOT_APPLICABLE`; all money/currency fields null; zero retained monetary rows; exact TR-106 reason set `{}` and specifically no RC-063. |
| `SYN-KPI-017` | Credit-bearing verified action with exact applicable TARGET_REP-rep proof and exact date but invalid code, scale, representation, or bound registry | Value remains `UNVERIFIED`; exact reason set `{RC-063,RC-094}`; invalid Money and every contribution/bucket/aggregate write are absent; exactly one independently valid action/intervention remains; no USD/FX inference and no RC-074/075. |
| `SYN-KPI-018` | Credit-bearing verified action with exact applicable TARGET_REP-rep proof, null business action instant, and otherwise valid currency | Value `UNVERIFIED`; exact reason set `{RC-063,RC-099}`; no contribution/date bucket; proof, review, and recorded timestamps are not substituted; RC-074/075 are absent. |
| `SYN-KPI-019` | Static cross-document parity plus executable cross-product for split/substitution/DS × exact/null date × valid/absent/invalid currency × verified/missing/different/ambiguous applicable rep proof | Every governing artifact/oracle yields exactly Section 3.3: combined invalid+null base `{RC-063,RC-094,RC-099}`; split rep failure adds only RC-074; substitution line-rep failure adds only RC-075; absent currency adds no RC-094; verified rep adds neither rep code; DS adds none of RC-063/074/075/099. Any extra/missing code, state, row/link effect, or stale label fails release. |

### 7.3 Evidence/link/reversal idempotency (`SYN-IDEM-*`)

| ID | Fixture/action | Exact oracle |
|---|---|---|
| `SYN-IDEM-001` | Table-drive every logical-kind natural/material registry row and typed-event-kind/provenance/EvidenceEventKind row against fixed known-answer bytes/digests, reverse canonical proof/set input order, then mutate each natural/material member and submit invalid cross-pairs, empty proof sets, human actor-only proof, wrong source/object type, missing revision/hash, and extra fields | Every valid row matches its literal domain vector and produces identical canonical bytes/fingerprint regardless of set order, one matching typed event/evidence record, and one logical effect. Same occurrence ID with any changed material member fails under its exact conflict route and creates no second effect. Every invalid schema branch, including human search evidence, appends nothing. |
| `SYN-IDEM-002` | Submit the exact same action evidence fingerprint and payload twice | Return the original evidence/intervention; action effect and KPI count remain 1; second submission is an idempotent no-op. |
| `SYN-IDEM-003` | Table-drive (a) HUMAN action proof then compatible SYSTEM corroboration and (b) SYSTEM action proof then compatible HUMAN corroboration with different proof evidence times but the same action occurrence ID and byte-identical material scope/effect; then reuse that `(case_id,action_occurrence_id)` with a different intervention type/natural bytes | Compatible proofs may yield two evidence records/fingerprints but exactly one logical action/intervention/KPI effect. Proof time is absent from the natural key, and first accepted provenance/bucket never moves. The cross-type occurrence reuse emits RC-102 before natural-key allocation, creates no second intervention, and applies zero delta. |
| `SYN-IDEM-004` | Under one ACTION occurrence ID/natural identity, table-drive mutations of action time (including null/non-null), target/link/replacement, normalized relationship, credit-scope member, and scoped quantity without a legal correction event | Every changed material member emits `RC-102`; the prior intervention/contribution remains, no second effect is allocated, and disputed delta is zero. Exact same bytes replay. |
| `SYN-IDEM-005` | Table-drive every logical evidence kind, including `REVERSAL_CORRECTED` and `REVERSAL_VOIDED`, while the test hasher returns one digest for two different canonical payloads; run once at a registered pre-OA gate and once after another order has begun permitted OA work | Byte comparison detects RC-103; no new evidence, projection, KPI update, or partial transaction effect commits. Pre-OA gate uses RC-090/FAILED. Post-OA collision marks only that order exception; successful prior work remains and coherent run is COMPLETED_WITH_EXCEPTIONS, never FAILED. |
| `SYN-IDEM-006` | Rediscover same parent/type/exact child link with identical moved-line mapping | One natural link and one mapping revision/effect; repeated discovery is a no-op and proves neither intervention nor value by itself. |
| `SYN-IDEM-007` | Exact base link has accepted mapping M1; submit compatible M1 corroboration, then contradictory M2, then exact M2 resolution proof | M1 corroboration reuses one M1 logical key/effect. M2 creates a distinct mapping-assertion logical key and TR-111 conflict revision with RC-104 + RC-072 and no RC-102, without mutating M1 or creating a second base link; both M1 and M2 logical-key rows/bytes survive. Disputed credit is zero. Exact M2 resolution reuses M2 key and appends the governed resolution revision once. |
| `SYN-IDEM-008` | Same child Order Number appears under two different retained parent cases | Natural keys differ because `parent_case_id` differs; each case may have one independent link. |
| `SYN-IDEM-009` | Submit identical reversal evidence twice, then compatible human/system corroboration of the same material reversal | One logical reversal amount is counted; gross unchanged; reversed/net change once; optional duplicate audit uses `RC-076`. |
| `SYN-IDEM-010` | Table-drive every original-value/reversal/correction/void kind: reuse one `(case_id,intervention_id,logical_occurrence_id)` with changed material, reuse it across a different logical kind, and submit a correction/void with a stale or cross-intervention predecessor | Same-occurrence changed material or cross-kind reuse emits `RC-102` (plus `RC-077` where reversal review applies); stale/cross-target is rejected first with `RC-111`. Every branch retains the prior reducer/KPI, appends nothing, and applies zero disputed delta. Exact same-kind/same-natural/same-material replay is a no-op. |
| `SYN-IDEM-011` | Test hasher collides two different result-link mapping payloads | Emit fatal `RC-103`, not an ordinary mapping conflict; no revision/projection/KPI change commits. |
| `SYN-IDEM-012` | Purge a case with action/value/reversal/link fingerprints | After atomic finalization, no natural key, canonical payload, fingerprint, link mapping, contribution hash, or reconstructable per-case identifier is present; only non-identifying daily totals remain. |

### 7.4 Round-4 rep-reason ownership (`SYN-INT-*`, `SYN-REASON-OWN-*`)

| ID | Fixture/action | Exact oracle |
|---|---|---|
| `SYN-INT-017` | Table-drive a verified `FULFILLMENT_SPLIT` with one exact child link and exact-date/valid-currency inputs: resulting order-level rep exactly TARGET_REP versus missing, different, and ambiguous | Exact TARGET_REP-rep proof permits the ordinary exact-value owner and emits neither RC-074 nor RC-075. Each unverified-rep row keeps the exact link/mapping unchanged, leaves value `UNVERIFIED`, emits exact TR-106 set `{RC-063, RC-074}`, explicitly omits RC-075, retains one count-1 zero-money row, and contributes zero realized credit. |
| `SYN-INT-018` | Table-drive a verified `PRODUCT_SUBSTITUTION` with one exact replacement-line binding and exact-date/valid-currency inputs: replacement line-level rep exactly TARGET_REP versus missing, different, and ambiguous; also set parent order rep to TARGET_REP in a blocked row | Exact line-level TARGET_REP-rep proof permits the ordinary exact-value owner and emits neither RC-074 nor RC-075. Each unverified line-rep row leaves the replacement binding unchanged, leaves value `UNVERIFIED`, emits exact TR-106 set `{RC-063, RC-075}`, explicitly omits RC-074, retains one count-1 zero-money row, and contributes zero realized credit. Parent order rep never substitutes. |
| `SYN-REASON-OWN-001` | RC-074 positive table: split exact link with missing/different/ambiguous resulting order-level TARGET_REP rep across every Section 3.3 date/currency base set | Each result equals exact `B ∪ {RC-074}` with RC-075 absent; row/no-row, value, link, and zero-credit effects exactly match Section 3.3. |
| `SYN-REASON-OWN-002` | RC-074 negative/cross branch: split with verified resulting order-level TARGET_REP rep, a swap rep failure across every Section 3.3 date/currency base set, DS, unrelated TR-106 branch, then a contradictory both-code/wrong-type payload | RC-074 is absent from every non-applicable branch; every swap row derives its exact base set `B` and yields `B ∪ {RC-075}` with RC-074 absent; DS/unrelated branches use their own exact sets; contradiction fails with RC-081 before append and leaves all state unchanged. |
| `SYN-REASON-OWN-003` | RC-075 positive table: substitution with missing/different/ambiguous replacement line-level TARGET_REP rep across every Section 3.3 date/currency base set, including parent order rep TARGET_REP | Each result equals exact `B ∪ {RC-075}` with RC-074 absent; row/no-row, value, replacement binding, and zero-credit effects exactly match Section 3.3; parent order rep is ignored. |
| `SYN-REASON-OWN-004` | RC-075 negative/cross branch: substitution with verified line-level TARGET_REP rep, a split rep failure across every Section 3.3 date/currency base set, DS, unrelated TR-106 branch, then a contradictory both-code/wrong-type payload | RC-075 is absent from every non-applicable branch; every split row derives its exact base set `B` and yields `B ∪ {RC-074}` with RC-075 absent; DS/unrelated branches use their own exact sets; contradiction fails with RC-081 before append and leaves all state unchanged. |

The package-level `SYN-REASON-OWN-009` and `SYN-REASON-OWN-010` additionally require 115/115 external ownership and exact parity of this branch model with the machine contract, technical specification, provenance/state contract, persistence model, transition matrix/traceability, acceptance matrix, synthetic requirements, implementation handoff, OA policy, v0.1.5.3 reason registry, and reason ownership matrix. RC-115 changes no money, KPI, scope, overlap, selection, or TR-106 semantics. An undefined code, alias, unknown reason-registry version, orphan registry row, missing oracle, or set mismatch fails before persistence.

## 8. Required cross-artifact merge points

The final remediation package MUST copy the same normative answer into every governed artifact rather than summarize it differently:

- **Technical specification:** replace the one-paragraph overlap rule with sections 2.2–2.7; replace generic aggregate language with sections 3.2, 3.5–3.7; add evidence/link idempotency and purge deletion rules.
- **Machine contract:** add the closed enums and exact entity schemas in sections 2–4; replace USD-only KPI fields with valid ISO currency; keep money segmented and no-FX; add database keys/checks.
- **Persistence model:** include both retained case-linked contribution rows and non-identifying daily buckets; include canonical bytes required for collision detection; encode one ACID upsert/finalization boundary.
- **Reason registry and ownership matrix:** retain `RC-097`–`RC-104`, preserve the canonical RC-074/RC-075 definitions, add the exact TR-106 external owners/oracles in Section 7.4, and require the package-wide 115/115 closed ownership gate. RC-115 is outside KPI calculation and contributes no value by itself.
- **State-transition matrix:** add `TR-106`–`TR-112`, reference `TR-112` from legal case purge transitions, and add immutable opportunity guards.
- **Acceptance matrix and synthetic requirements:** add all `SYN-SCOPE-*`, `SYN-KPI-*`, and `SYN-IDEM-*` rows with identical oracles; update the derived synthetic-family and test totals.
- **Implementation handoff:** require JCS/SHA-256 known-answer tests, canonical-byte retention until purge, unique constraints, transaction fault injection, timezone DST vectors, collision injection, and no persisted non-daily/ALL bucket rows.
- **Historical/final-label artifacts:** update only version/count/traceability metadata where necessary. Preserve 213/213 accounting, 0 executable history, 59 human-review, 154 supporting-only, zero historical oracle denominator, and no target leakage. Historical labels or provisional results MUST NOT populate scope, option, fingerprint, intervention, or KPI expected results.
- **SHA-256 manifest:** regenerate after all reconciled artifacts are final; do not alter the immutable source corpus.

### 8.1 Conflicting baseline text that must not survive the merge

The following older formulations are directly incompatible with this module and must be replaced, not left as alternate guidance:

- Machine Contract `Money = {currency:"USD", ...}` and `DOIAggregateKPIRecord.currency = USD`: replace with exact ISO-4217 currency and the sibling reconciliation's no-FX rules.
- The old `DOIOpportunity.affected_line_snapshot_ids` schema, including its empty/order-level DS exception: replace with the non-empty component/quantity scope in section 2; keep affected-line IDs only as a derived view.
- Generic `merchandise/credit-scope key` prose without component quantities, overlap-group derivation, or option identity: replace with `credit_scope`, `scenario_overlap_key`, and `scenario_option_id` algorithms above.
- Generic `period_start`/`period_end` aggregate records with no grain/timezone/date identity: replace with daily `America/New_York` leaf buckets and exact DST-aware boundaries.
- Any rule that attributes value to evidence-review, correction, reversal, computation, or purge time: replace with immutable verified-action attribution.
- Increment-only aggregate logic or a finalization marker keyed by case/intervention/fingerprint: replace with retained full-ledger recomputation and the atomic retained-to-finalized transfer that deletes its join keys.
- `action_evidence_fingerprint` as the sole intervention unique key without canonical payload bytes, a separate logical natural key, and conflict behavior: replace with section 4's two-level evidence identity.
- Resulting-order links lacking `relationship_type`, the parent/type/child natural uniqueness tuple, or a separate moved-line/quantity mapping fingerprint: replace with section 4.3.
- Reversal summation by evidence-record count or raw fingerprint count: replace with one authoritative material effect per distinct logical reversal key.
- Any fingerprint, scope key, option ID, result-link key, or contribution hash surviving case purge: remove it; only non-identifying daily totals may survive.

## 9. Handoff implementation order and release invariants

Recommended offline order for this slice:

1. implement canonical primitive encoders plus known-answer hash tests;
2. implement exact scope derivation, overlap connected components, option IDs, and potential selection;
3. implement logical/evidence key stores and idempotent insert/collision behavior;
4. implement resulting-order natural links and mapping revisions;
5. implement retained KPI contribution reducer and daily bucket upsert;
6. implement atomic purge finalization with transaction-failure injection;
7. run all old and new synthetic/historical gates entirely against fictional fixtures and fake read-only OA transport.

Release-blocking invariants:

1. No opportunity without an exact non-empty immutable scope.
2. Shared merchandise credit cannot be counted from more than one scenario option in an overlap group.
3. Same-order membership alone never fabricates overlap.
4. Realized credit is attributed only to the verified action's New York local date.
5. Later value/correction/reversal evidence updates that original daily bucket.
6. Daily/currency/leaf-class rows are the only persisted KPI source of truth.
7. Mixed currencies are segmented; no FX and no cross-currency total.
8. Exact replay is a no-op; same natural key with conflicting material payload fails closed.
9. Different canonical bytes with one hash are a fatal integrity failure.
10. Result-link identity and moved-line mapping are separately canonical and idempotent.
11. Duplicate reversal evidence changes reversal/KPI totals once.
12. Purge atomically transfers retained to finalized amounts and deletes every case-linked identity/fingerprint.
13. After purge, finalized aggregates are immutable to per-order evidence; no tombstone or cross-purge lookup exists.
14. OA is permanently 100% read-only; all DOI user actions change DOI-owned records only and require explicit human intent.
15. TR-106 rep parity is closed: split rep failure emits RC-074 and never RC-075; substitution line-rep failure emits RC-075 and never RC-074; unrelated/DS branches emit neither; contradictory branches fail before persistence.

This module does not declare `DOI_V0.1_SPEC = FROZEN`. The complete reconciled package must be independently re-audited.
