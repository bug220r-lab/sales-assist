
> **Sanitized supporting reference.** This file is a mechanically sanitized derivative of
> source material supplied for the synthetic proof of concept. Historical status/freeze
> language is nonbinding. The curated files under `specs/` govern. No production-system
> access or real-data use is authorized by this reference.

# DOI v0.1.5 Normative Provenance, State-History, and Transition Contract

Authority patch: v0.1.5.5 HumanFactBinding derived-hash correction layered on the unchanged v0.1.5.4 HumanFactUsageKind binding; independent audit required; not a freeze declaration.

Status: remediation-candidate governing module; independent re-audit required. This module is incorporated into the v0.1.5 technical specification, machine contract, persistence model, transition matrix, acceptance matrix, synthetic requirements, and implementation handoff. It does not declare the specification frozen and does not authorize production implementation or live Synthetic Order Portal access.

## 1. Permanent boundaries and record layers

Synthetic Order Portal (OA) remains permanently **100% read-only**. Every entity, event, projection, transition, and user action below is DOI-local. None authorizes an OA mutation, generic request helper, arbitrary click/submit helper, background OA activity, or a state-changing control activation. A read path whose side-effect safety is not proved fails before dispatch.

The persistence model MUST keep four layers distinct:

| Layer | Normative contents | Forbidden contents/effects |
|---|---|---|
| `SOURCE_FACT` | Immutable normalized observations actually read from an allowlisted source, including complete `DOIOrderSnapshot`, product-only relationship evidence, and `DOIAlternateObservation`. | Human claims, DOI classifications, recommendations, reasoned outputs, or lifecycle state. |
| `HUMAN_FACT` | Immutable structured authorized-human statements with explicit `HUMAN_VERIFIED` provenance, actor, time, scope, evidence fingerprint, and content hash. | Pretending a human statement was source-observed; free-text customer/message/note bodies; silent overwrite. |
| `EVALUATION_OUTPUT` | Immutable `DOIEvaluation`, `DOIOpportunity`, and `DOIWWCProjectionEvent` derived from exact bound source/human facts and exact rules. | Altering a source fact or human fact; treating an output as proof an action occurred. |
| `LIFECYCLE_EVENT` | Immutable retained case, attention, Action Context, contact, DEDUPE, relationship-revision, resulting-link, intervention-verification, value-correction, and reversal events; plus the separately governed transaction-local source-import-attempt retention event that is deleted with its graph. Current states are reductions of retained events. | Rewriting a prior fact/event; treating a projection cache as authority; retaining an attempt purge event/reason/hash as a tombstone; performing an OA action. |

No field may silently migrate between layers. A lifecycle event MAY reference a source fact, human fact, or evaluation output; it MUST NOT copy it into a differently labelled fact.

### 1.1 Canonical serialization and hashes

Every content hash and evidence fingerprint uses RFC 8785 JSON Canonicalization Scheme encoded as UTF-8, domain-separated by the explicit schema/version named for that identity. The following schema rules apply before RFC 8785 serialization:

1. lexicographically ordered object keys;
2. closed-enum strings exactly as registered;
3. RFC 3339 UTC instants with a `Z` suffix;
4. exact decimal strings or integer minor units, never binary floating point;
5. arrays sorted only when the schema defines them as sets; semantically ordered arrays retain their normative order;
6. no omitted-vs-null ambiguity: nullable fields are explicitly `null` and inapplicable tagged values are `NOT_APPLICABLE`;
7. SHA-256 returned as lowercase 64-character hexadecimal.

An immutable record's `content_sha256` follows its registered domain formula: SHA-256 over the literal UTF-8 domain prefix plus RFC-8785/JCS of every persisted immutable field except the digest field itself. Section 1.2 gives the event domains; record-specific sections give non-event domains. Generated IDs are included only in full-record hashes, never in narrower semantic fingerprints unless that fingerprint schema explicitly says otherwise. A digest collision evidenced by two different canonical payloads is a fatal integrity conflict; neither payload may overwrite the other or produce a credit-bearing result.

`HumanFactBindingHashV1` is the derived component digest `human_fact_binding_sha256 = SHA256(UTF8("doi-human-fact-binding/v1\n") || UTF8(RFC8785(HumanFactBinding)))`. Its schema/domain identifier is exactly `doi-human-fact-binding/v1`; the prefix includes the final LF byte; the result is lowercase 64-character hexadecimal. The closed eight-member `HumanFactBinding` object below does not serialize `human_fact_binding_sha256`: the digest is calculated outside the object, so there is no recursive self-hash, new nullable member, or persistence identity. The machine-readable authority is `DOI_HUMAN_FACT_BINDING_HASH_CONTRACT_v0.1.5.5.json`. Wrong/empty/version-mismatched/no-LF prefixes, non-JCS bytes, malformed or uppercase expected digest text, or a supplied expected digest that does not match the derived value fails closed before evaluation persistence with RC-106; an independently illegal binding remains RC-105 and cannot be legitimized by any digest.

### 1.2 Event-stream envelope

Every append-only event below except every `DOIOrderLifecycleEventV2` stream and the transaction-local `DOISourceImportAttemptRetentionEventV1` includes this exact envelope in addition to its type-specific fields. Both case lifecycle namespaces are governed exclusively by the closed order-lifecycle registry. The source-import retention event is governed exclusively by `source_retention_contract.md` section 13.4 and the lifecycle registry section 6.1; it uses its own event/stream ID formulas, exact non-case envelope names, payload/domain hashes, sequence-1 null partition, and is deleted before commit. Neither exception may serialize duplicate generic aliases.

```text
schema_version: VersionId
event_id: OpaqueId
stream_id: Sha256
stream_sequence: integer >= 1
previous_event_id: OpaqueId | null
previous_event_content_sha256: Sha256 | null
event_type: closed event enum
occurred_at: Timestamp
recorded_at: Timestamp
actor_kind: SYSTEM | HUMAN
actor_id: OpaqueId | null          # required for HUMAN; never customer identity
provenance: SYSTEM_VERIFIED | HUMAN_VERIFIED
reason_codes: ordered registered-code set
content_sha256: Sha256
```

Where a type-specific schema gives the event a domain name such as `contact_event_id` or `value_event_id`, that field is the domain alias of envelope `event_id`, not a second identifier.

`stream_id` is not caller-selected. It is exactly `SHA-256(JCS({"event_stream_identity_version":"doi-event-stream-id-v1","stream_namespace":N,"owner_identity":O}))`, where `N` and `O` are fixed by this closed table:

| `stream_namespace` | Exact `owner_identity` |
|---|---|
| `RUN` | `run_id` |
| `SOURCE_IMPORT_ATTEMPT` | `source_import_attempt_id` |
| `REJECTED_SOURCE_RETENTION` | `rejected_source_record_id` |
| `CASE_LIFECYCLE` | `case_id` |
| `ALTERNATE_RELATIONSHIP` | `alternate_relationship_id` |
| `ACTION_CONTEXT` | `action_context_id` |
| `HUMAN_FACT` | `case_id` |
| `CONTACT` | `action_context_id` |
| `DEDUPE` | `case_id` |
| `ATTENTION` | `case_id` |
| `WWC_PROJECTION` | `case_id` |
| `RESULT_LINK_SEARCH` | `resulting_order_link_search_id` |
| `RESULT_LINK_EXACT` | `resulting_order_link_id` |
| `RESULT_LINK_MAPPING` | `resulting_order_link_id` |
| `INTERVENTION_ACTION` | `intervention_id` |
| `INTERVENTION_VALUE` | `intervention_id` |

For a `DOIResultingOrderLinkEvent`, the sole non-null search/link ID selects `RESULT_LINK_SEARCH` or `RESULT_LINK_EXACT`; mapping revisions always use `RESULT_LINK_MAPPING`. The persistence boundary MUST enforce global `UNIQUE(event_id)`, `UNIQUE(stream_id, stream_sequence)`, and, within each stream, exact predecessor adjacency. `stream_sequence=1` requires both previous fields null. Sequence `n>1` requires `previous_event_id` and `previous_event_content_sha256` to equal the accepted sequence `n-1` event. A missing, caller-chosen, wrong-owner, wrong-namespace, stale, skipped, duplicated, or forked stream identity/sequence fails with `RC-111`; a proven same-digest/different-bytes condition additionally invokes `RC-103`. No projection changes on rejection.

Each non-source namespace has one literal envelope schema/domain pair:

| Namespace | Literal `schema_version` | Hash domain prefix |
|---|---|---|
| `CASE_LIFECYCLE` | `doi-order-lifecycle-event/v2` | `doi-order-lifecycle-event/v2\n` |
| `ALTERNATE_RELATIONSHIP` | `doi-alternate-relationship-revision-event/v1` | `doi-alternate-relationship-revision-event/v1\n` |
| `ACTION_CONTEXT` | `doi-action-context-event/v1` | `doi-action-context-event/v1\n` |
| `HUMAN_FACT` | `doi-human-fact-event/v1` | `doi-human-fact-event/v1\n` |
| `CONTACT` | `doi-contact-state-event/v1` | `doi-contact-state-event/v1\n` |
| `DEDUPE` | `doi-dedupe-state-event/v1` | `doi-dedupe-state-event/v1\n` |
| `ATTENTION` | `doi-attention-event/v2` | `doi-attention-event/v2\n` |
| `WWC_PROJECTION` | `doi-wwc-projection-event/v1` | `doi-wwc-projection-event/v1\n` |
| `RESULT_LINK_SEARCH` | `doi-result-link-search-event/v1` | `doi-result-link-search-event/v1\n` |
| `RESULT_LINK_EXACT` | `doi-result-link-exact-event/v1` | `doi-result-link-exact-event/v1\n` |
| `RESULT_LINK_MAPPING` | `doi-result-link-mapping-revision-event/v1` | `doi-result-link-mapping-revision-event/v1\n` |
| `INTERVENTION_ACTION` | `doi-intervention-action-event/v1` | `doi-intervention-action-event/v1\n` |
| `INTERVENTION_VALUE` | `doi-intervention-value-event/v1` | `doi-intervention-value-event/v1\n` |

For every row, `content_sha256 = SHA256(UTF8(domain_prefix) || UTF8(RFC8785(event_without_content_sha256)))`. A domain-specific ID/schema name is an in-memory/API alias of the common `event_id`/`schema_version` field and is serialized exactly once under the common field name. Wrong literal, domain prefix, duplicate alias field, or formula is RC-111; same digest with different canonical bytes additionally invokes RC-103.

`stream_sequence=1` requires both previous fields null. Every later append requires the exact current sequence, prior event ID, and prior event digest. A mismatch fails closed with no append and leaves the last valid projection authoritative. Events are reduced strictly by `stream_sequence`, not wall-clock order. `occurred_at` is the fact/action time; `recorded_at` is audit ingestion time.

## 2. Exact `DOIEvaluation` provenance

### 2.1 Binding objects

```text
SnapshotBinding {
  snapshot_id: OpaqueId,
  snapshot_content_sha256: Sha256
}

RulesBinding {
  rules_engine_version: VersionId,
  rules_bundle_content_sha256: Sha256,
  reason_registry_version: VersionId,
  reason_registry_content_sha256: Sha256,
  evaluation_schema_version: VersionId,  # literal doi-evaluation-record/v1
  normalization_contract_version: VersionId
}

BusinessCalendarBinding {
  business_calendar_version: VersionId,
  business_calendar_content_sha256: Sha256
}

RelationshipRevisionBinding {
  alternate_relationship_id: OpaqueId,
  relationship_revision_id: OpaqueId,
  revision_number: integer >= 1,
  revision_content_sha256: Sha256,
  applies_to_line_snapshot_ids: canonical ordered non-empty set<OpaqueId>,
  usage_kind: OPPORTUNITY_IDENTITY | COMPATIBILITY | VALUE_CONTEXT | RESEARCH_STATE
}

AlternateObservationBinding {
  alternate_observation_id: OpaqueId,
  observation_schema_version: VersionId,
  observation_content_sha256: Sha256,
  alternate_relationship_id: OpaqueId,
  relationship_revision_id: OpaqueId,
  relationship_revision_content_sha256: Sha256,
  action_context_id: OpaqueId,
  applies_to_line_snapshot_ids: canonical ordered non-empty set<OpaqueId>,
  usage_kind: AVAILABILITY | PRICE | ETA | ACTION_READINESS
}

HumanFactBinding {
  fact_kind: closed HumanFactKind,
  human_fact_event_id: OpaqueId,
  fact_schema_version: VersionId,
  fact_content_sha256: Sha256,
  provenance: HUMAN_VERIFIED,
  action_context_id: OpaqueId | null,
  applies_to_line_snapshot_ids: canonical ordered set<OpaqueId>,
  usage_kind: closed HumanFactUsageKind
}
```

`HumanFactUsageKind` is distinct from `HumanFactKind` and has this exact closed ordered domain:

```text
HumanFactUsageKind = COMPATIBILITY | RESEARCH_STATE | ORDER_PROGRESS |
                     COORDINATION | OUT_OF_SCOPE | ACTION_READINESS
```

The order above is the canonical enum-member order under registry `doi-human-fact-usage-kind/v1`; its canonical registry-object SHA-256 is `da0612598dcd2b8300d9459af29e192cbf0a3413802cf548fc618713d4721764`. Unknown members, aliases, case variants, free text, missing values, and extensions fail before evaluation persistence with RC-105. The exact registry object and applicability function remain published in `DOI_HUMAN_FACT_USAGE_KIND_REGISTRY_v0.1.5.4.json`; the unchanged field/member/applicability schema plus the external derived-hash reference are published in `DOI_HUMAN_FACT_EVALUATION_SCHEMAS_v0.1.5.5.json`.

The fact-kind/usage-kind relation is exactly: `COMPATIBILITY_REVIEW_RESULT -> {COMPATIBILITY, RESEARCH_STATE, ACTION_READINESS}`; `NO_VIABLE_ALTERNATE_CONFIRMED -> {RESEARCH_STATE}`; `NORMAL_PROGRESS_REVIEW_RESULT -> {ORDER_PROGRESS}`; `COORDINATION_RESOLUTION -> {COORDINATION}`; `HUMAN_OUT_OF_SCOPE_DECISION -> {OUT_OF_SCOPE}`; and both `DEDUPE_APPROVED` and `DEDUPE_REJECTED` have no legal `DOIEvaluation.human_fact_bindings` usage. DEDUPE facts remain valid immutable HUMAN_FACT events and participate only through the dedicated TR-061/TR-062 contract. No other pair is legal.

For authority revision 0.1.5.5, the exact business-rule binding remains: rules engine `synthetic.doi.rules/v0.1.5.4`; rules bundle SHA-256 `df48446467a81eec9970b22649bf5d86cb5dc09e0ecaad291839774523288ad0`; unchanged reason registry version `0.1.5.3`; unchanged reason registry SHA-256 `38eba58f78950c320b9b4e3ece167cc050cae6c11ee0978b98749f3247c2ec86`; evaluation schema `doi-evaluation-record/v1`; unchanged normalization contract `doi-normalization-contract/v0.1.5.3`; and HumanFact usage registry `doi-human-fact-usage-kind/v1` / `da0612598dcd2b8300d9459af29e192cbf0a3413802cf548fc618713d4721764`. The v0.1.5.5 change is solely the serialization/provenance hash contract, so it does not bump or alter the v0.1.5.4 business-rules bundle. `DOI_AUTHORITY_VERSION_MANIFEST_v0.1.5.5.json` binds both the unchanged rules bundle and the new hash-contract artifact. A stale rules binding, unknown/unavailable version, or mismatched digest is rejected before append; no substitute version is legal. Prior evaluations remain reproducible under their originally bound versions and hashes.

### 2.2 Immutable schema

```text
DOIEvaluation {
  evaluation_id: OpaqueId,
  evaluation_schema_version: VersionId,
  case_id: OpaqueId,
  evaluated_at: Timestamp,
  snapshot_binding: SnapshotBinding,
  rules_binding: RulesBinding,
  business_calendar_binding: BusinessCalendarBinding | null,
  relationship_revision_bindings: canonical ordered set<RelationshipRevisionBinding>,
  alternate_observation_bindings: canonical ordered set<AlternateObservationBinding>,
  human_fact_bindings: canonical ordered set<HumanFactBinding>,
  evaluation_input_manifest_sha256: Sha256,
  doi_state: DOIState,
  reason_codes: registered ordered set (empty only for a legal result whose transition explicitly requires no reason code, including initial DOI_MONITOR),
  opportunity_ids: canonical ordered set<OpaqueId>,
  handling_flags: registered ordered set,
  coordination_flags: registered ordered set,
  alternate_research_by_line: canonical map<line_snapshot_id, AlternateResearchState>,
  calculated_values: typed calculated-value object,
  recommendations: registered ordered set,
  evaluation_output_sha256: Sha256,
  content_sha256: Sha256
}
```

The three evaluation digests use these literal, closed objects and no extension fields:

```text
evaluation_input_manifest_object = {
  "input_manifest_schema_version":"doi-evaluation-input-manifest/v1",
  "case_id":case_id,
  "evaluated_at":evaluated_at,
  "snapshot_binding":snapshot_binding,
  "rules_binding":rules_binding,
  "business_calendar_binding":business_calendar_binding,
  "relationship_revision_bindings":relationship_revision_bindings,
  "alternate_observation_bindings":alternate_observation_bindings,
  "human_fact_bindings":human_fact_bindings
}

evaluation_output_object = {
  "output_schema_version":"doi-evaluation-output/v1",
  "doi_state":doi_state,
  "reason_codes":reason_codes,
  "opportunity_ids":opportunity_ids,
  "handling_flags":handling_flags,
  "coordination_flags":coordination_flags,
  "alternate_research_by_line":alternate_research_by_line,
  "calculated_values":calculated_values,
  "recommendations":recommendations
}
```

`evaluation_input_manifest_sha256 = SHA256(UTF8("doi-evaluation-input-manifest/v1\n") || UTF8(RFC8785(evaluation_input_manifest_object)))`. `evaluation_output_sha256 = SHA256(UTF8("doi-evaluation-output/v1\n") || UTF8(RFC8785(evaluation_output_object)))`. `evaluation_schema_version` is literal `doi-evaluation-record/v1`, and `content_sha256 = SHA256(UTF8("doi-evaluation-record/v1\n") || UTF8(RFC8785(evaluation_without_content_sha256)))`. The full-record object contains every stored `DOIEvaluation` field, including `evaluation_id` and the two narrower digests, exactly once; it excludes only `content_sha256`. The separately derived `human_fact_binding_sha256` is a component known-answer value over one complete validated binding. It neither replaces nor changes `fact_content_sha256`, `evaluation_input_manifest_sha256`, `evaluation_output_sha256`, or evaluation `content_sha256`.

All nullable members are serialized explicitly as `null`; in particular the calendar binding is `null` when forbidden. Binding sets are sorted by the ascending UTF-8 RFC-8785 byte sequence of each complete member after schema validation; ID sets and registered-code/flag/recommendation sets are sorted by UTF-8 code-point order with duplicates rejected; `alternate_research_by_line` is an object whose line-ID keys are lexicographically ordered by JCS; and typed `calculated_values` uses its closed schema with every nullable member explicit. For `human_fact_bindings`, the natural uniqueness key is exactly `(human_fact_event_id, usage_kind)`: one fact may appear in multiple distinct legal roles only through distinct legal keys and exact role-specific scope; a duplicate complete binding is rejected with RC-105, and the same key with changed bytes is rejected with RC-105 (or RC-106 when the resolved event/hash differs). Input enumeration, database row order, or map iteration order cannot alter any digest. Missing/extra keys, wrong literal/domain, duplicate set members, noncanonical timestamps/decimals, or digest mismatch rejects the evaluation with `RC-105` or `RC-106` as applicable and appends nothing.

### 2.3 Deterministic provenance rules

1. `snapshot_binding.snapshot_id` MUST resolve to the same `case_id`; its stored content digest MUST match.
2. The exact rules bundle and reason registry MUST be loadable and MUST match both version and digest. A matching version string with a different digest is not the requested rules.
3. `business_calendar_binding` is required whenever WWC timing was evaluated and forbidden when no calendar-derived field was used.
4. Every reusable product relationship used in research, classification, compatibility, or value context MUST appear once with the exact revision ID, revision number, and revision digest used. The revision MUST have been the accepted `ACTIVE` current revision at the evaluation's as-of instant. Later revision, supersession, or invalidation never changes the old evaluation.
5. Every alternate price, availability, ETA, or action-readiness fact used MUST bind the exact immutable observation version/digest and exact Action Context. An observation not explicitly linked to that Action Context cannot be used as current.
6. Every observation target resolves and byte-matches at evaluation append. After its mandatory earlier deletion, the immutable evaluation/opportunity may retain only the already accepted observation ID/hash as a sealed historical case-graph commitment. It is not resolvable evidence, cannot establish current freshness or enter a new evaluation/action, and deletes with case purge.
7. Every applicable structured human fact used by the rules MUST appear in `human_fact_bindings`. A bare manual-decision ID is insufficient. The binding MUST include exact schema version, digest, scope, provenance, and registered `usage_kind`.
8. Applicability is the closed deterministic `doi-human-fact-usage-kind/v1` function in the bound v0.1.5.4 rules bundle. It selects accepted facts for the exact case, snapshot line scope, opportunity/context scope, and `occurred_at <= evaluated_at`. A later corrected/superseding human fact requires a new evaluation; it never rewrites the old evaluation.
9. Any missing record, wrong case/scope, unregistered type or usage, illegal fact/usage pair, digest mismatch, unavailable rules, or incomplete binding causes no evaluation to be appended. Emit the exact blocking code below; do not substitute a newer fact/version.
10. Re-evaluation appends a new record even when outputs happen to be identical. Source facts, human facts, prior evaluations, and prior opportunities remain unchanged until case purge.

### 2.4 Closed HumanFact usage scope and failure routes

- `COMPATIBILITY` accepts only `COMPATIBILITY_REVIEW_RESULT`, a nonempty canonical line set belonging to the evaluation snapshot and exactly matching the fact scope, and the fact's exact `action_context_id` (which may be null when the fact was not recorded for a current attempt). It affects compatibility conclusions only.
- `RESEARCH_STATE` accepts only `COMPATIBILITY_REVIEW_RESULT` or `NO_VIABLE_ALTERNATE_CONFIRMED`, the fact's exact nonempty line scope, and the fact's exact context. It affects alternate-research state and its registered downstream consumers only; no-viable-alternate alone proves no DEDUPE, closure, intervention, or action.
- `ACTION_READINESS` accepts only `COMPATIBILITY_REVIEW_RESULT`, requires the exact non-null OPEN context stored by the fact, requires the fact's opportunity to resolve to the compatible same-context opportunity, and requires the exact nonempty fact/opportunity line scope. The existing approved/rejected/needs-more-evidence behavior is unchanged; the binding never proves an intervention.
- `ORDER_PROGRESS` accepts only `NORMAL_PROGRESS_REVIEW_RESULT`, the exact empty line set, and the exact context stored by the fact (null under the current fact contract unless another already-governing clause explicitly permits otherwise). It affects only the normal-progress/no-action route.
- `COORDINATION` accepts only `COORDINATION_RESOLUTION`, the exact empty line set, and the fact's exact context. The existing SELF/OTHER_REP non-null qualifying-contact and NOT_APPLICABLE null partition remains. It affects only WWC/coordination and proves no contact or action without a separate qualifying event.
- `OUT_OF_SCOPE` accepts only `HUMAN_OUT_OF_SCOPE_DECISION`, the exact empty line set, and exact null context under the closure contract. It affects only the human-out-of-scope disposition/closure and is not a generic ignore flag.

Every binding resolves the exact immutable event and byte-verifies its schema, full content hash, fact kind, HUMAN_VERIFIED provenance, context, line scope, case, opportunity when required, and occurrence time before append. Unknown/missing usage, illegal pairs, wrong/null scope, missing target, duplicate complete binding, or same natural key with changed binding bytes is RC-105; a resolved record/registry digest mismatch is RC-106; human-fact construction/correction provenance conflicts remain RC-112; stream predecessor faults remain RC-111; and a proven digest collision remains RC-103. No new reason code is introduced.

## 3. Reusable product relationship revision model

### 3.1 Stable relationship identity

```text
DOIAlternateRelationship {
  alternate_relationship_id: OpaqueId,
  relationship_schema_version: VersionId,
  relationship_identity_canonical_bytes: bytes,
  relationship_identity_sha256: Sha256,
  ordered_es_number: ESNumber,
  candidate_es_number: ESNumber,
  ordered_mfg_number: MFGNumber | null,
  candidate_mfg_number: MFGNumber | null,
  relationship_type: EXACT_MFG | MFG_CROSS_REFERENCE | MFG_SUPERSESSION | FUNCTIONAL,
  applicability_identity: canonical product-only structured object | null,
  created_at: Timestamp,
  current_relationship_revision_id: OpaqueId,
  current_revision_number: integer >= 1,
  current_state: ACTIVE | SUPERSEDED | INVALIDATED
}
```

The stored canonical identity bytes are RFC-8785/JCS over `{relationship_identity_schema_version:"doi-alternate-relationship-identity-v1",ordered_es_number,candidate_es_number,ordered_mfg_number,candidate_mfg_number,relationship_type,applicability_identity}` with explicit nulls; `relationship_identity_sha256=SHA256(identity_bytes)`. Enforce `UNIQUE(relationship_identity_sha256)` and byte-compare on lookup before allocating `alternate_relationship_id`. Exact identity bytes always resolve the same stable base ID and never create a second relationship. After that lookup, an exact replay of the current semantic revision payload reuses the current revision; a different valid semantic payload with the exact current predecessor invokes TR-083 and appends revision `n+1`. Same identity digest with different identity bytes is fatal RC-103. Ordered and candidate ES numbers MUST differ. `EXACT_MFG` requires both MFG values non-null and equal. `MFG_CROSS_REFERENCE` and `MFG_SUPERSESSION` require both non-null and different. `FUNCTIONAL` permits either both null or both non-null and different; one-null and equal-non-null forms are illegal. Every revision MUST repeat the base identity fields exactly; changing any identity field creates a different relationship, not a revision. The tuple MUST NOT contain an Order Number, case ID, line snapshot ID, Action Context ID, customer identity, source row, or a key derived from any of them. The mutable-looking `current_*` fields are a rebuildable projection cache only; the revision stream is authoritative.

### 3.2 Immutable revision

```text
DOIAlternateRelationshipRevision {
  <event-stream envelope; stream_namespace=ALTERNATE_RELATIONSHIP>,
  event_type: ALTERNATE_RELATIONSHIP_CREATED |
              ALTERNATE_RELATIONSHIP_REVISION_APPENDED |
              ALTERNATE_RELATIONSHIP_SUPERSEDED |
              ALTERNATE_RELATIONSHIP_INVALIDATED,
  relationship_revision_id: OpaqueId,
  relationship_revision_schema_version: VersionId,
  alternate_relationship_id: OpaqueId,
  revision_number: integer >= 1,
  relationship_type: AlternateRelationshipType,
  normalized_product_facts: {
    ordered_es_number: ESNumber,
    candidate_es_number: ESNumber,
    ordered_mfg_number: MFGNumber | null,
    candidate_mfg_number: MFGNumber | null,
    applicability_facts: canonical product-only structured object | null
  },
  provenance_type: SYSTEM_VERIFIED | HUMAN_VERIFIED,
  source_provenance: canonical ordered non-empty set<{
    source_system: synthetic_CATALOG | MANUFACTURER_SOURCE | HUMAN_ATTESTATION | ORDER_ADMIN,
    source_object_id: string | null,
    source_revision_id: string | null,
    source_ref: SourceRef,
    evidence_content_sha256: Sha256,
    observed_at: Timestamp
  }>,
  relationship_state: ACTIVE | SUPERSEDED | INVALIDATED,
  created_at: Timestamp,
  supersedes_relationship_revision_id: OpaqueId | null,
  successor_alternate_relationship_id: OpaqueId | null,
  successor_relationship_identity_sha256: Sha256 | null,
  invalidation_reason_code: registered reason code | null,
  revision_content_sha256: Sha256
}
```

`relationship_revision_id` is the alias of envelope `event_id`; `relationship_revision_schema_version` equals envelope `schema_version`; `created_at` equals envelope `recorded_at`; and envelope `content_sha256` hashes the complete persisted event. Revision 1 has `revision_number=1`, `stream_sequence=1`, null envelope predecessors, `supersedes_relationship_revision_id=null`, and `event_type=ALTERNATE_RELATIONSHIP_CREATED`. Revision `n>1` MUST have `revision_number=stream_sequence=current_revision_number+1`, MUST point through both predecessor mechanisms to the exact prior current revision/event and full-event digest, and MUST use the event type matching its resulting state/action. `SUPERSEDED` requires `ALTERNATE_RELATIONSHIP_SUPERSEDED` plus `successor_alternate_relationship_id`; `INVALIDATED` requires `ALTERNATE_RELATIONSHIP_INVALIDATED`, explicit contradictory product evidence, and its registered reason. Terminal states cannot return to `ACTIVE`; later verified knowledge creates a new stable relationship identity where required.

`revision_content_sha256` uses the following exact closed semantic object, with no extension keys:

```text
relationship_revision_semantic_object = {
  "revision_semantic_schema_version":"doi-alternate-relationship-revision-semantic/v1",
  "relationship_identity_sha256":relationship_identity_sha256,
  "event_type":event_type,
  "relationship_type":relationship_type,
  "normalized_product_facts":normalized_product_facts,
  "provenance_type":provenance_type,
  "source_provenance":source_provenance,
  "relationship_state":relationship_state,
  "successor_relationship_identity_sha256":successor_relationship_identity_sha256,
  "invalidation_reason_code":invalidation_reason_code
}
```

`successor_relationship_identity_sha256` is required exactly for `SUPERSEDED` and otherwise explicit `null`; `invalidation_reason_code` is required exactly for `INVALIDATED` and otherwise explicit `null`. `source_provenance` is a canonical ordered nonempty set sorted by each complete member's RFC-8785 bytes, with duplicates rejected; every nullable source object/revision field and `normalized_product_facts.applicability_facts` is serialized explicitly as `null`. `revision_content_sha256 = SHA256(UTF8("doi-alternate-relationship-revision-semantic/v1\n") || UTF8(RFC8785(relationship_revision_semantic_object)))`. Generated relationship/revision/event IDs, revision number, creation/occurrence/recording time, stream/predecessor fields, `supersedes_relationship_revision_id`, and both digest fields are excluded from this narrower semantic object; the common full-event hash binds all stored event fields. An exact replay of the current semantic bytes/hash is idempotent and returns the current revision without appending. Missing/extra members, wrong null form/set ordering/domain, or a different payload presented under the same revision identity/number fails closed.

`source_provenance` MUST already be product-only. A case-specific finding may be promoted into reusable knowledge only by writing a separate sanitized product-only evidence object; no reverse link to the originating case/order/context may enter the relationship or revision. Registered `ORDER_ADMIN` is legal here only when the evidence object itself is a non-order product object and the SourceRef is explicitly qualified `product_only=true`; an order-page/source-row locator is forbidden.

### 3.3 Observation amendment

`DOIAlternateObservation` MUST additionally contain:

```text
observation_schema_version: VersionId  # literal doi-alternate-observation/v1
relationship_revision_id: OpaqueId
relationship_revision_content_sha256: Sha256
observation_content_sha256: Sha256
action_context_id: OpaqueId | null
```

An observation used for current action readiness requires a non-null `action_context_id`, a relationship revision that is exact and active as of observation time, and an immutable context-observation link. Independent storage expiry follows the exact 90-local-calendar-day retention contract. Effective deletion for a case-linked observation/link target and its one-event target-owned volatile lifecycle wrapper is the earlier of that independent expiry and linked-case purge. The core case stream never references the wrapper; deletion leaves no direct target/index/receipt. A preexisting immutable evaluation/opportunity may retain only its sealed observation ID/hash commitment inside the case graph, so no expired fact can be reconstructed or satisfy freshness/action gates.

`observation_content_sha256 = SHA256(UTF8("doi-alternate-observation/v1\n") || UTF8(RFC8785(observation_without_alternate_observation_id_and_observation_content_sha256)))`. The closed object contains exactly: `observation_schema_version`, `alternate_relationship_id`, `relationship_revision_id`, `relationship_revision_content_sha256`, `observed_at`, `retention_policy_version`, `timezone_database_version`, `observation_purge_eligible_at`, `source_system`, `observed_price`, `observed_availability`, `observed_eta`, `observation_source_refs`, `action_context_id`, and `case_id`. Nullable values are explicit null; proof refs are a duplicate-free set sorted by complete-member JCS bytes. No extension field or alternate ordering/domain is legal.

## 4. Action Context

### 4.1 Immutable base and event stream

```text
ActionContextKind = SUBSTITUTION | CUSTOMER_CONTACT | FULFILLMENT_SPLIT_REVIEW |
                    DS_SEPARATION_REVIEW | RESULTING_ORDER_LINK_REVIEW |
                    INTERVENTION_VERIFICATION

ActionContextState = OPEN | CLOSED_COMPLETED | CLOSED_ABANDONED | CLOSED_SUPERSEDED

DOIActionContext {
  action_context_id: OpaqueId,
  action_context_schema_version: VersionId,  # literal doi-action-context/v1
  attempt_intent_id: OpaqueId,
  request_canonical_bytes: bytes,
  request_sha256: Sha256,
  case_id: OpaqueId,
  evaluation_id: OpaqueId,
  opportunity_id: OpaqueId,
  context_kind: ActionContextKind,
  created_at: Timestamp,
  created_by_actor_id: OpaqueId,
  initial_state: OPEN,
  context_content_sha256: Sha256
}

DOIActionContextEvent {
  <event-stream envelope>,
  event_type: ACTION_CONTEXT_OPENED | ACTION_CONTEXT_COMPLETED |
              ACTION_CONTEXT_ABANDONED | ACTION_CONTEXT_SUPERSEDED,
  action_context_id: OpaqueId,
  case_id: OpaqueId,
  prior_state: ActionContextState | NONEXISTENT,
  resulting_state: ActionContextState,
  close_reason: ACTION_VERIFIED | DECISION_RECORDED | REVIEW_FINISHED |
                HUMAN_ABANDONED | SUPERSEDED_BY_LATER_ATTEMPT | null,
  completion_trigger: INTERVENTION_ACTION_VERIFIED |
                      HUMAN_COMPATIBILITY_DECISION |
                      HUMAN_NO_VIABLE_ALTERNATE_CONFIRMATION |
                      RESULTING_ORDER_LINK_RESOLVED | null,
  source_entity_ids: canonical ordered set<OpaqueId>
}

DOIActionContextObservationLink {
  action_context_observation_link_id: OpaqueId,
  link_schema_version: VersionId,
  action_context_id: OpaqueId,
  alternate_observation_id: OpaqueId,
  relationship_revision_id: OpaqueId,
  linked_at: Timestamp,
  content_sha256: Sha256
}
```

An Action Context belongs to exactly one retained case and references the exact evaluation/opportunity for one human decision or action-preparation attempt. Context kind MUST be compatible with the opportunity. `attempt_intent_id` is a nonempty opaque idempotency token generated for one explicit begin-attempt command and is globally unique while retained. `request_canonical_bytes` is exact RFC-8785/JCS for `{action_context_request_schema_version:"doi-action-context-request/v1",attempt_intent_id,case_id,evaluation_id,opportunity_id,context_kind,created_by_actor_id}` and `request_sha256=SHA256(UTF8("doi-action-context-request/v1\n") || request_canonical_bytes)`. Enforce `UNIQUE(attempt_intent_id)` and byte-compare before allocating `action_context_id`: same token plus byte-identical request returns the existing context/event; same token with different request bytes rejects with `RC-110` and changes nothing; a genuinely later attempt requires a fresh token and creates a new `action_context_id`. It never rewrites or reopens the old context. Creating the later context MAY atomically append `CLOSED_SUPERSEDED` to the old open context. The old context base/events remain until case purge; its observation/link/volatile-wrapper target graph remains only until the earlier observation nominal expiry or case purge, after which only sealed evaluation/opportunity commitments remain.

`context_content_sha256 = SHA256(UTF8("doi-action-context/v1\n") || UTF8(RFC8785(context_without_context_content_sha256)))`; the closed full-base object contains every stored base field exactly once, including generated `action_context_id`, canonical request bytes/hash, `created_at`, and explicit initial state. `link_schema_version` is literal `doi-action-context-observation-link/v1` and link `content_sha256 = SHA256(UTF8("doi-action-context-observation-link/v1\n") || UTF8(RFC8785(link_without_content_sha256)))`, again over every stored link field including its ID/time. Resolve `UNIQUE(action_context_id,alternate_observation_id,relationship_revision_id)` before allocating the link ID/time: exact tuple replay returns the existing byte-identical link; conflicting bytes reject RC-110; a hash collision invokes RC-103. Missing/extra/null/domain/order/hash variance is invalid.

Only a successful explicit observation made after the context was created may be linked. A link requires matching case/opportunity product scope and exact relationship revision. A closed context accepts no new observation or human fact and cannot make an observation current. An Action Context never represents an autonomous OA action, never authorizes a mutation, and never changes OA.

Context compatibility is the following exhaustive table. Any pair or required gate not listed is `RC-110`; `EXACT_SKU_RECHECK` and `PARTIAL_QUANTITY_REVIEW` do not authorize an Action Context under v0.1.5.

| `ActionContextKind` | Legal exact opportunity/gate | Compatible eventual intervention |
|---|---|---|
| `SUBSTITUTION` | `EXACT_MFG_ALTERNATE`, `MFG_CROSS_REFERENCE`, `MFG_SUPERSESSION`, or `FUNCTIONAL_ALTERNATE`, with exact selected option/scope and required relationship revision | `PRODUCT_SUBSTITUTION` |
| `CUSTOMER_CONTACT` | `FULFILLMENT_SPLIT` or one of the four substitution opportunities, only when that exact opportunity/evaluation carries its registered customer-contact/customer-approval gate | `FULFILLMENT_SPLIT` or `PRODUCT_SUBSTITUTION` matching the opportunity |
| `FULFILLMENT_SPLIT_REVIEW` | `FULFILLMENT_SPLIT` with exact selected scope/option | `FULFILLMENT_SPLIT` |
| `DS_SEPARATION_REVIEW` | `DS_SEPARATION` with exact active DS scope | `DS_SEPARATION` |
| `RESULTING_ORDER_LINK_REVIEW` | `FULFILLMENT_SPLIT` with an exact cause-keyed resulting-link review/search requirement for that scope | `FULFILLMENT_SPLIT` |
| `INTERVENTION_VERIFICATION` | `FULFILLMENT_SPLIT`, `DS_SEPARATION`, or one of the four substitution opportunities, plus the exact expected intervention type derived by the rows above | the exact derived type only |

Context creation validates the opportunity ID, its evaluation/case, type, immutable scope/option/gates, and the table row in one transaction. A later gate change requires a new evaluation/opportunity/context; it never changes the old context.

The event and completion fields are a closed cross-field contract. `OPEN` uses `ACTION_CONTEXT_OPENED`, null `close_reason`, and null `completion_trigger`. `CLOSED_ABANDONED` uses `ACTION_CONTEXT_ABANDONED` + `HUMAN_ABANDONED` and no completion trigger. `CLOSED_SUPERSEDED` uses `ACTION_CONTEXT_SUPERSEDED` + `SUPERSEDED_BY_LATER_ATTEMPT` and no completion trigger. `CLOSED_COMPLETED` uses `ACTION_CONTEXT_COMPLETED` and exactly one of these pairs: `ACTION_VERIFIED` + `INTERVENTION_ACTION_VERIFIED`; `DECISION_RECORDED` + one of `HUMAN_COMPATIBILITY_DECISION` or `HUMAN_NO_VIABLE_ALTERNATE_CONFIRMATION`; or `REVIEW_FINISHED` + `RESULTING_ORDER_LINK_RESOLVED`. The sole source entity MUST be an accepted, same-case/same-context typed event of the required kind.

| Completion trigger | Allowed `ActionContextKind` | Required accepted source |
|---|---|---|
| `INTERVENTION_ACTION_VERIFIED` | `SUBSTITUTION`, `CUSTOMER_CONTACT`, `FULFILLMENT_SPLIT_REVIEW`, `DS_SEPARATION_REVIEW`, or `INTERVENTION_VERIFICATION` | Same-context `DOIInterventionActionVerificationEvent`; intervention type/opportunity/scope must match the context compatibility table |
| `HUMAN_COMPATIBILITY_DECISION` | `SUBSTITUTION` only | Same-context `DOIHumanFactEvent` with compatibility APPROVED or REJECTED (not NEEDS_MORE_EVIDENCE) |
| `HUMAN_NO_VIABLE_ALTERNATE_CONFIRMATION` | `SUBSTITUTION` only | Same-context line-scoped no-viable-alternate confirmation |
| `RESULTING_ORDER_LINK_RESOLVED` | `RESULTING_ORDER_LINK_REVIEW` only | Same-context exact `SYSTEM_LINK_VERIFIED` or `HUMAN_LINK_VERIFIED` resolution event |

Coordination resolution, normal-progress, out-of-scope, compatibility-needs-more-evidence, and context-null facts may be valid facts/evaluation inputs but never close an Action Context. No open-ended domain code, free text, or caller-supplied completion label is legal.

## 5. Typed append-only histories

### 5.1 Human facts, including constructible DEDUPE decisions

Contact, intervention verification, and value/reversal facts use their dedicated schemas below. A human DEDUPE decision is a `DOIHumanFactEvent` in the HUMAN_FACT layer and is atomically referenced by the dedicated `DOIDedupeStateEvent`; the two records are never aliases. The closed human-fact unions are:

```text
HumanFactKind = COMPATIBILITY_REVIEW_RESULT | NO_VIABLE_ALTERNATE_CONFIRMED |
                NORMAL_PROGRESS_REVIEW_RESULT | COORDINATION_RESOLUTION |
                HUMAN_OUT_OF_SCOPE_DECISION | DEDUPE_APPROVED |
                DEDUPE_REJECTED

HumanFactResultCode = COMPATIBILITY_APPROVED | COMPATIBILITY_REJECTED |
                      COMPATIBILITY_NEEDS_MORE_EVIDENCE |
                      NO_VIABLE_ALTERNATE_CONFIRMED |
                      NORMAL_PROGRESS_NO_ACTION_REQUIRED |
                      COORDINATION_RESOLUTION_RECORDED |
                      HUMAN_OUT_OF_SCOPE_CONFIRMED | DEDUPE_APPROVED |
                      DEDUPE_REJECTED

DOIHumanFactEvent {
  <event-stream envelope; provenance=HUMAN_VERIFIED>,
  event_type: HUMAN_FACT_RECORDED | HUMAN_FACT_CORRECTED,
  human_fact_event_id: OpaqueId,
  case_id: OpaqueId,
  action_context_id: OpaqueId | null,
  fact_kind: HumanFactKind,
  result_code: HumanFactResultCode,
  evaluation_id: OpaqueId | null,
  opportunity_id: OpaqueId | null,
  fact_occurrence_id: OpaqueId,
  line_snapshot_ids: canonical ordered set<OpaqueId>,
  structured_fact: CompatibilityFact | NoViableAlternateFact |
                   NormalProgressFact | CoordinationResolutionFact |
                   HumanOutOfScopeFact | DedupeDecisionFact,
  evidence_fingerprint: Sha256,
  supersedes_human_fact_event_id: OpaqueId | null
}

CompatibilityFact = {
  payload_type: "COMPATIBILITY_FACT",
  outcome: APPROVED | REJECTED | NEEDS_MORE_EVIDENCE
}
NoViableAlternateFact = {
  payload_type: "NO_VIABLE_ALTERNATE_FACT",
  confirmed: true
}
NormalProgressFact = {
  payload_type: "NORMAL_PROGRESS_FACT",
  outcome: NO_ACTION_REQUIRED
}
CoordinationResolutionFact = {
  payload_type: "COORDINATION_RESOLUTION_FACT",
  resolved_author_relation: SELF | OTHER_REP | NOT_APPLICABLE,
  qualifying_contact_at: Timestamp | null
}
HumanOutOfScopeFact = {
  payload_type: "HUMAN_OUT_OF_SCOPE_FACT",
  decision: OUT_OF_SCOPE
}
HumanVerificationReference = {
  reference_schema_version: "doi-dedupe-human-verification-ref/v1",
  reference_id: OpaqueId,
  reference_content_sha256: Sha256,
  authorized_actor_id: OpaqueId
}
DedupeDecisionFact = {
  payload_type: "DEDUPE_DECISION_FACT",
  dedupe_review_id: Sha256,
  candidate_dedupe_event_id: OpaqueId,
  candidate_dedupe_event_content_sha256: Sha256,
  candidate_dedupe_occurrence_id: OpaqueId,
  candidate_evaluation_id: OpaqueId,
  candidate_evaluation_content_sha256: Sha256,
  decision_kind: APPROVED | REJECTED,
  decided_at: Timestamp,
  human_verification_ref: HumanVerificationReference,
  decision_reason_code: RC-058 | null
}
```

The `fact_kind`/`result_code`/payload pairing is closed. `COMPATIBILITY_REVIEW_RESULT` uses the matching compatibility result and `CompatibilityFact`; `NO_VIABLE_ALTERNATE_CONFIRMED` uses its identically named result and `NoViableAlternateFact`; `NORMAL_PROGRESS_REVIEW_RESULT` uses `NORMAL_PROGRESS_NO_ACTION_REQUIRED` and `NormalProgressFact`; `COORDINATION_RESOLUTION` uses `COORDINATION_RESOLUTION_RECORDED` and `CoordinationResolutionFact`; `HUMAN_OUT_OF_SCOPE_DECISION` uses `HUMAN_OUT_OF_SCOPE_CONFIRMED` and `HumanOutOfScopeFact`; `DEDUPE_APPROVED` uses result `DEDUPE_APPROVED`, `DedupeDecisionFact`, and decision `APPROVED`; and `DEDUPE_REJECTED` uses result `DEDUPE_REJECTED`, `DedupeDecisionFact`, and decision `REJECTED`. Every cross-pair is `RC-112` and appends nothing. The two DEDUPE result values are domain result enums, not new `RC-*` reason codes.

Compatibility and no-alternate facts require nonempty exact `line_snapshot_ids`; normal-progress and out-of-scope facts require case/evaluation scope and no invented line scope; any fact used for action readiness requires the exact OPEN `action_context_id` and compatible `opportunity_id`. Coordination SELF/OTHER_REP requires non-null exact `qualifying_contact_at`; `NOT_APPLICABLE` requires it null and means no qualifying contact. No payload admits an extension field, free text, note body, customer data, or omitted-vs-null variant.

A DEDUPE decision requires `actor_kind=HUMAN`, non-null `actor_id`, and `provenance=HUMAN_VERIFIED`; `decided_at` equals envelope `occurred_at`. Its generic shell has `action_context_id=null`, `evaluation_id=candidate_evaluation_id`, `opportunity_id=null`, and an empty canonical `line_snapshot_ids` set. The immutable `human_verification_ref` actor equals envelope `actor_id`, and its ID/hash resolves to one privacy-minimized local authorization/structured-decision record. It cannot refer to an OA note, DEDUPE lifecycle event, free-text note, or customer record. `decision_reason_code=RC-058` is permitted only when the exact candidate evaluation contains RC-058; it records candidate context, not an inferred human rationale. Every candidate/review field must resolve and reproduce the Section 5.3 review identity.

For non-DEDUPE kinds, `HUMAN_FACT_RECORDED` requires a null supersedes ID and `HUMAN_FACT_CORRECTED` requires the exact current prior same-kind/same-scope event. A correction appends and never overwrites. For DEDUPE kinds, the only legal cross-kind correction is predecessor-bound `DEDUPE_APPROVED -> DEDUPE_REJECTED` under TR-062 while the exact review remains `HUMAN_APPROVED_AWAITING_OA_VERIFICATION` and before OA note verification. Every other same-review conflicting decision or correction is `RC-112` and appends nothing.

`fact_occurrence_id` is a nonempty human-command idempotency token. For every non-DEDUPE kind, its semantic object remains exactly `{human_fact_evidence_schema_version:"doi-human-fact-evidence/v1",case_id,action_context_id,fact_occurrence_id,event_type,fact_kind,result_code,evaluation_id,opportunity_id,line_snapshot_ids,structured_fact,supersedes_human_fact_event_id,actor_id,occurred_at,provenance:"HUMAN_VERIFIED"}` with explicit nulls and duplicate-free line IDs sorted by canonical UTF-8 order. `evidence_fingerprint=SHA256(UTF8("doi-human-fact-evidence/v1\n") || UTF8(RFC8785(object)))`.

For `DEDUPE_APPROVED|DEDUPE_REJECTED`, the semantic object is instead exactly:

```text
DedupeDecisionEvidenceObject = {
  dedupe_decision_evidence_schema_version: "doi-dedupe-human-decision-evidence/v1",
  case_id: OpaqueId,
  dedupe_review_id: Sha256,
  candidate_dedupe_event_id: OpaqueId,
  candidate_dedupe_event_content_sha256: Sha256,
  candidate_dedupe_occurrence_id: OpaqueId,
  candidate_evaluation_id: OpaqueId,
  candidate_evaluation_content_sha256: Sha256,
  decision_kind: APPROVED | REJECTED,
  decided_at: Timestamp,
  human_verification_ref: HumanVerificationReference,
  decision_reason_code: RC-058 | null,
  supersedes_human_fact_event_id: OpaqueId | null,
  actor_id: OpaqueId,
  provenance: "HUMAN_VERIFIED"
}
evidence_fingerprint = SHA256(
  UTF8("doi-dedupe-human-decision-evidence/v1\n") ||
  UTF8(RFC8785(DedupeDecisionEvidenceObject))
)
```

The DEDUPE semantic fingerprint deliberately excludes `fact_occurrence_id`, generated event/stream fields, `recorded_at`, and the full-event hash. The command-token guard and full event hash still bind those fields. This permits semantic idempotent reuse of a byte-identical decision/proof without making a transport retry wrapper part of the decision identity.

Known-answer approval vector:

```text
domain = "doi-dedupe-human-decision-evidence/v1\n"
canonical bytes = {"actor_id":"actor-fixture-TARGET_REP","candidate_dedupe_event_content_sha256":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd","candidate_dedupe_event_id":"dedupe-event-fixture-001","candidate_dedupe_occurrence_id":"dedupe-occurrence-fixture-001","candidate_evaluation_content_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","candidate_evaluation_id":"evaluation-fixture-001","case_id":"SYN-DOI-CASE-PROV-0001","decided_at":"2026-08-09T15:00:00Z","decision_kind":"APPROVED","decision_reason_code":"RC-058","dedupe_decision_evidence_schema_version":"doi-dedupe-human-decision-evidence/v1","dedupe_review_id":"c2a58efae01d42a336654ad134ff2b63199b916e6e2330f7b8b0efdc12c615e5","human_verification_ref":{"authorized_actor_id":"actor-fixture-TARGET_REP","reference_content_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","reference_id":"human-verification-fixture-001","reference_schema_version":"doi-dedupe-human-verification-ref/v1"},"provenance":"HUMAN_VERIFIED","supersedes_human_fact_event_id":null}
expected evidence_fingerprint = 4014615999a5f8c890cd1dd42b06d81e2e8be62c15bb030df20f103fab67bf06
```

Enforce `UNIQUE(case_id,fact_occurrence_id)`, retain canonical bytes, and compare before reuse. For non-DEDUPE facts, same token/same bytes is a no-op and same token/different bytes is RC-112. For DEDUPE facts, also enforce `UNIQUE(case_id,dedupe_review_id,evidence_fingerprint)` and one current decision chain per review: same decision fingerprint plus byte-identical semantic payload returns the existing fact; same token/different bytes, same review with changed same-kind semantic bytes, or same review with a conflicting decision outside the exact legal correction is RC-112. A proven digest collision also invokes RC-103. Generated event/stream/recorded-time/full-event-hash fields remain bound by the full event hash.

### 5.2 Contact history

```text
DOIContactStateEvent {
  <event-stream envelope>,
  event_type: CONTACT_REQUIRED_DERIVED | CONTACT_ATTEMPT_RECORDED |
              AWAITING_CUSTOMER_RECORDED | CUSTOMER_APPROVAL_RECORDED |
              CUSTOMER_DECLINE_RECORDED | NO_RESPONSE_RECORDED,
  contact_event_id: OpaqueId,
  case_id: OpaqueId,
  action_context_id: OpaqueId,
  opportunity_id: OpaqueId,
  contact_occurrence_id: OpaqueId,
  source_evaluation_id: OpaqueId | null,
  prior_contact_state: ContactState,
  resulting_contact_state: ContactState,
  contact_occurred_at: Timestamp | null,
  evidence_fingerprint: Sha256,
  structured_evidence_refs: canonical ordered set<SourceRef>
}
```

`CONTACT_REQUIRED_DERIVED` is the sole system-derived contact event: it requires `actor_kind=SYSTEM`, `provenance=SYSTEM_VERIFIED`, null `contact_occurred_at`, a non-null exact `source_evaluation_id`/opportunity binding, and only `NOT_CONTACTED -> CONTACT_REQUIRED`. It records a locked DOI readiness gate, not proof that contact occurred. Every other contact event requires `actor_kind=HUMAN`, `provenance=HUMAN_VERIFIED`, null `source_evaluation_id`, a non-null exact human-recorded occurrence instant, and the matching legal transition. Contact projection is per Action Context, never a case-global approval. `CUSTOMER_APPROVED` opens only the manual readiness gate for the exact context/opportunity and never performs a substitution, sends a message, reads Synthetic Message Source, or creates an intervention. A later action attempt starts a new context at `NOT_CONTACTED`.

`contact_occurrence_id` is deterministic `SHA256(JCS({contact_occurrence_schema_version:"doi-contact-derived-occurrence/v1",action_context_id,event_type,source_evaluation_id}))` for the system-derived kind, and a fresh nonempty human-command idempotency token for every actual human contact fact. The evidence object is exactly `{contact_evidence_schema_version:"doi-contact-evidence/v1",case_id,action_context_id,opportunity_id,contact_occurrence_id,source_evaluation_id,event_type,prior_contact_state,resulting_contact_state,contact_occurred_at,structured_evidence_refs,actor_kind,actor_id,provenance,occurred_at}`; nullable values are explicit, refs are sorted by complete-member JCS bytes, and duplicates are rejected. `evidence_fingerprint=SHA256(UTF8("doi-contact-evidence/v1\n") || UTF8(RFC8785(object)))`. Enforce `UNIQUE(action_context_id,contact_occurrence_id)` plus canonical-byte comparison. Same occurrence/same bytes is a no-op; same occurrence/different bytes is RC-110; hash collision adds RC-103. A distinct later attempt under TR-080 MUST use a fresh occurrence ID and append; it cannot be mistaken for replay.

### 5.3 DEDUPE history

```text
DedupeReviewIdentityObject = {
  dedupe_review_identity_schema_version: "doi-dedupe-review-identity/v1",
  case_id: OpaqueId,
  candidate_dedupe_occurrence_id: OpaqueId,
  candidate_evaluation_id: OpaqueId,
  candidate_evaluation_content_sha256: Sha256
}

DOIDedupeStateEvent {
  <event-stream envelope>,
  dedupe_event_id: OpaqueId,
  case_id: OpaqueId,
  dedupe_review_id: Sha256,
  dedupe_occurrence_id: OpaqueId,
  prior_dedupe_state: DedupeState,
  resulting_dedupe_state: DedupeState,
  event_kind: CANDIDATE_DERIVED | CANDIDATE_WITHDRAWN | HUMAN_APPROVED |
              HUMAN_REJECTED | OA_NOTE_SYSTEM_VERIFIED | ELIGIBILITY_RETURNED,
  evaluation_id: OpaqueId | null,
  snapshot_id: OpaqueId | null,
  human_fact_event_id: OpaqueId | null,
  human_fact_event_content_sha256: Sha256 | null,
  evidence_fingerprint: Sha256
}
```

`TR-060 CANDIDATE_DERIVED` establishes the review identity before the candidate event is hashed:

```text
dedupe_review_id = SHA256(
  UTF8("doi-dedupe-review-identity/v1\n") ||
  UTF8(RFC8785(DedupeReviewIdentityObject))
)
```

`candidate_dedupe_occurrence_id` is the already-defined deterministic system occurrence for the accepted evaluation and `CANDIDATE_DERIVED` kind. The candidate event uses that occurrence and derived review ID; its evaluation ID/digest must equal the review object. Because the event hash is not an input to the review ID, no event-hash/review-ID cycle exists. A later new candidate episode uses a new accepted evaluation/occurrence and derives a new review ID. A caller-supplied or non-reproducing ID is invalid.

Known-answer review vector:

```text
domain = "doi-dedupe-review-identity/v1\n"
canonical bytes = {"candidate_dedupe_occurrence_id":"dedupe-occurrence-fixture-001","candidate_evaluation_content_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","candidate_evaluation_id":"evaluation-fixture-001","case_id":"SYN-DOI-CASE-PROV-0001","dedupe_review_identity_schema_version":"doi-dedupe-review-identity/v1"}
expected dedupe_review_id = c2a58efae01d42a336654ad134ff2b63199b916e6e2330f7b8b0efdc12c615e5
```

Every DEDUPE event requires the exact review ID for the candidate episode it advances, withdraws, confirms, or reopens. `CANDIDATE_DERIVED`, `CANDIDATE_WITHDRAWN`, and `ELIGIBILITY_RETURNED` are evaluation results and require exactly `evaluation_id` non-null with `snapshot_id`, `human_fact_event_id`, and `human_fact_event_content_sha256` null. `OA_NOTE_SYSTEM_VERIFIED` requires exactly `snapshot_id` non-null with both evaluation and human-fact fields null; that snapshot is a successful complete read-only OA snapshot and never an OA write. `HUMAN_APPROVED` and `HUMAN_REJECTED` require exactly `human_fact_event_id` plus `human_fact_event_content_sha256` non-null with `evaluation_id` and `snapshot_id` null. No other source-ID/null partition is valid. A later qualifying opportunity/blocker withdraws a stale candidate or unverified approval. `CONFIRMED` reopens only through source-grounded eligibility under the existing case-reopen transition.

`DOIDedupeStateEvent.event_kind` is the domain alias of envelope `event_type` and MUST equal it exactly. `HUMAN_APPROVED|HUMAN_REJECTED` require HUMAN/HUMAN_VERIFIED; every other listed kind requires SYSTEM/SYSTEM_VERIFIED. A mismatch is schema-invalid and appends nothing.

System occurrence identity is exact and closed. For `CANDIDATE_DERIVED|CANDIDATE_WITHDRAWN|ELIGIBILITY_RETURNED`, `source_entity_type` is literal `EVALUATION` and `source_entity_id=evaluation_id`; for `OA_NOTE_SYSTEM_VERIFIED`, it is literal `SNAPSHOT` and `source_entity_id=snapshot_id`. The occurrence object is exactly `{dedupe_occurrence_schema_version:"doi-dedupe-occurrence-v1",case_id,event_kind,source_entity_type,source_entity_id}` and `dedupe_occurrence_id=SHA256(UTF8("doi-dedupe-occurrence-v1\n") || UTF8(RFC8785(object)))`. Human `HUMAN_APPROVED|HUMAN_REJECTED` events require a fresh nonempty command idempotency token as `dedupe_occurrence_id`, and it must equal the exact referenced human fact's `fact_occurrence_id`. An unlisted kind/source pair, missing/extra source ID, arbitrary system token, or reused human token with another fact is invalid.

The DEDUPE evidence object is exactly `{dedupe_evidence_schema_version:"doi-dedupe-evidence/v1",case_id,dedupe_review_id,dedupe_occurrence_id,event_kind,prior_dedupe_state,resulting_dedupe_state,evaluation_id,snapshot_id,human_fact_event_id,human_fact_event_content_sha256,actor_kind,actor_id,provenance,occurred_at}` with explicit nulls. `evidence_fingerprint=SHA256(UTF8("doi-dedupe-evidence/v1\n") || UTF8(RFC8785(object)))`.

For human kinds, the referenced record must be an accepted HUMAN_FACT stream event for the same case/review: `HUMAN_APPROVED` requires exact `DEDUPE_APPROVED`/`APPROVED`; `HUMAN_REJECTED` requires exact `DEDUPE_REJECTED`/`REJECTED`. No lifecycle event, OA note, evaluation inference, or unrelated human fact can satisfy the ID/hash FK. OA note observation remains the separate later read-only `OA_NOTE_SYSTEM_VERIFIED` source fact.

Enforce `UNIQUE(case_id,dedupe_occurrence_id)`, canonical-byte comparison, an exact deferred human-fact ID+hash FK, and one current decision chain per `(case_id,dedupe_review_id)`. The same system source/kind deterministically returns the same occurrence. The same human decision fingerprint plus byte-identical semantic payload returns the existing human fact and corresponding DEDUPE result. Changed bytes under one system occurrence reject RC-111; same human token with changed bytes or same review with a conflicting/illegally corrected decision rejects RC-112; a proven digest collision also invokes RC-103.

TR-061 and TR-062 lock and validate both HUMAN_FACT and DEDUPE stream heads, then commit both exact events and the projection in one ACID transaction. TR-061 accepts only `CANDIDATE` plus a first `DEDUPE_APPROVED`/`HUMAN_FACT_RECORDED` fact with null supersedes and projects `HUMAN_APPROVED_AWAITING_OA_VERIFICATION`. TR-062 from `CANDIDATE` accepts a first `DEDUPE_REJECTED`/`HUMAN_FACT_RECORDED` fact with null supersedes. TR-062 from `HUMAN_APPROVED_AWAITING_OA_VERIFICATION` accepts only `DEDUPE_REJECTED`/`HUMAN_FACT_CORRECTED` whose `supersedes_human_fact_event_id` is the exact current approval fact, and only before OA note verification. The approval remains immutable. Rejected-to-approved under the same review is illegal; a later accepted evaluation must derive a new candidate episode/review before a new first decision. Any append, FK, unique, hash, stream, or projection failure rolls back both streams and the projection. Neither transition reads or writes OA.

### 5.4 Attention/manual-review history

```text
AttentionSourceEntityType = EXTRACTION_ATTEMPT | EVALUATION |
                            WWC_PROJECTION_EVENT |
                            RESULTING_ORDER_LINK_SEARCH_EVENT |
                            RESULTING_ORDER_LINK_EXACT_EVENT |
                            INTERVENTION_ACTION_EVENT | HUMAN_FACT_EVENT

DOIAttentionEventV2 {
  <ATTENTION event-stream envelope; schema_version="doi-attention-event/v2">,
  event_type: ATTENTION_SET | ATTENTION_CLEARED,
  attention_event_id: OpaqueId,
  case_id: OpaqueId,
  operation: SET | CLEAR,
  attention_condition: AttentionCondition,
  attention_cause_key_sha256: Sha256,

  cause_source_entity_type: AttentionSourceEntityType,
  cause_source_entity_id: OpaqueId,
  cause_source_entity_revision: CanonicalRevisionToken | null,
  cause_source_content_hash: Sha256,

  resolution_source_entity_type: AttentionSourceEntityType | null,
  resolution_source_entity_id: OpaqueId | null,
  resolution_source_entity_revision: CanonicalRevisionToken | null,
  resolution_source_content_hash: Sha256 | null,

  clears_attention_event_id: OpaqueId | null,
  resolution_occurred_at: Timestamp | null,
  resolution_reason_code: RegisteredReasonCode | null
}
```

`CanonicalRevisionToken` is the canonical decimal `stream_sequence` string for every `*_EVENT` source type. It is null exactly for the two immutable non-stream record types `EXTRACTION_ATTEMPT` and `EVALUATION`. An extraction-attempt source binds the exact terminal `DOIExtractionAttempt.extraction_attempt_id` and `record_content_sha256`; an evaluation source binds its exact ID and full-record content hash. Every non-null provenance group requires an exact accepted entity/event ID, applicable revision-or-required-null, and content hash. A group is all-or-nothing. No v1 single `source_entity_*` tuple, v1/v2 field mixture, partial group, extension field, or omitted-vs-null variant validates as v2.

The cause-key object and formula are exactly:

```text
AttentionCauseKeyObject = {
  attention_cause_key_schema_version: "doi-attention-cause-key/v2",
  case_id: OpaqueId,
  attention_condition: AttentionCondition,
  cause_source_entity_type: AttentionSourceEntityType,
  cause_source_entity_id: OpaqueId,
  cause_source_entity_revision: CanonicalRevisionToken | null,
  cause_source_content_hash: Sha256
}

attention_cause_key_sha256 = SHA256(
  UTF8("doi-attention-cause-key/v2\n") ||
  UTF8(RFC8785(AttentionCauseKeyObject))
)
```

The case, attention type, exact cause type/identity, applicable revision, and cause content hash are bound. No resolver field, resolution timestamp/reason, or CLEAR event ID enters this object. A resolver different from the original cause therefore cannot change the cause key.

Known-answer cause-key vector:

```text
domain = "doi-attention-cause-key/v2\n"
canonical bytes = {"attention_cause_key_schema_version":"doi-attention-cause-key/v2","attention_condition":"RESULTING_ORDER_LINK_REVIEW","case_id":"SYN-DOI-CASE-PROV-0001","cause_source_content_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","cause_source_entity_id":"link-event-fixture-017","cause_source_entity_revision":"7","cause_source_entity_type":"RESULTING_ORDER_LINK_EXACT_EVENT"}
expected attention_cause_key_sha256 = b9aa571b62e7fbc8b03bc83bd95914ec97a517ff50cd71cc71985362ef816262
```

For `SET`, the complete cause group is required and reproduces the submitted key. All four resolution provenance fields, `clears_attention_event_id`, `resolution_occurred_at`, and `resolution_reason_code` are present and null. The key must not already be active. SET adds only that key. Its natural identity is `(case_id,operation=SET,attention_cause_key_sha256)`; exact bytes are idempotent, while changed SET bytes under one identity are RC-081 unless a proven collision adds RC-103.

For `CLEAR`, the complete original cause group is required and byte-for-byte equals the cause group on `clears_attention_event_id`, which must reference the exact active SET for the same case, condition, and cause key. The submitted key must both equal the SET key and reproduce from the copied cause group. The complete independent resolution group and `resolution_occurred_at` are required; the timestamp equals the accepted resolver fact/event occurrence time, never record ingestion time. `resolution_reason_code` follows the closed transition table below and is null only where that table says null. CLEAR removes exactly that active key. Its natural identity is `(case_id,operation=CLEAR,clears_attention_event_id)`; exact replay is a no-op, while another cause, resolver, timestamp, reason, or payload under that identity is RC-081. A proven digest collision additionally invokes RC-103 and a stale/forked stream envelope uses RC-111.

Persist immutable events plus only this rebuildable active projection:

```text
active_attention[(case_id, attention_condition, attention_cause_key_sha256)]
  -> set_attention_event_id

UNIQUE(case_id, operation, attention_cause_key_sha256) WHERE operation=SET
UNIQUE(case_id, clears_attention_event_id) WHERE operation=CLEAR
FK CLEAR.clears_attention_event_id -> SET.attention_event_id
CHECK CLEAR cause tuple/key == referenced SET cause tuple/key
CHECK referenced SET is active at the accepted ATTENTION stream position
```

Replay reduces by ATTENTION stream sequence and validates every key, group, partition, FK, and resolver hash before changing the in-memory set. It reproduces the same current projection while preserving both the original cause and later independent resolver. A displayed condition exists iff its active-cause set is nonempty. Clearing one cause never clears another cause, condition, opportunity, or immutable evaluation history. Top-level `DOI_MANUAL_REVIEW` history remains in immutable evaluations; typed attention events hold operational/manual-review conditions that can exist without an evaluation.

The provenance/null ownership for every existing attention transition is closed:

| Transition | Operation and cause | Exact cause source | Exact resolver source/effect |
|---|---|---|---|
| TR-020 | SET `RECHECK_REQUIRED` | failed/incomplete immutable `EXTRACTION_ATTEMPT` record | resolution group null |
| TR-021 | SET `SOURCE_ABSENT_RECHECK_REQUIRED` | accepted absence-verification immutable `EXTRACTION_ATTEMPT` record | resolution group null |
| TR-022 | CLEAR exact source-absence cause + SET new recheck cause | CLEAR copies old SET; new SET uses the incomplete-verification `EXTRACTION_ATTEMPT` record | CLEAR resolver is that incomplete-verification record; both attention effects commit atomically |
| TR-023 | CLEAR exact source-absence cause | copied from active SET | accepted complete disappearance-verification `EVALUATION`; registered evaluation/clear bundle is atomic |
| TR-024 | CLEAR exact recheck cause | copied from active SET | later complete recheck `EVALUATION`; snapshot/evaluation/clear bundle is atomic |
| TR-025 | SET `INTERVENTION_VERIFICATION_REQUIRED` | accepted `EVALUATION` that detected the unproved change | resolution group null |
| TR-026 | CLEAR exact intervention-verification cause | copied from active SET | accepted `INTERVENTION_ACTION_EVENT`; proof/intervention/clear bundle is atomic |
| TR-092 | SET `RESULTING_ORDER_LINK_REVIEW` | exact ambiguous search event or exact-link conflict event, using its distinct source type | resolution group null; link-conflict bundle remains atomic |
| TR-093 | CLEAR exact link/search-review cause | copied from active SET | exact link-resolution or exact negative-search event under the mapping below; owning bundle is atomic |
| TR-094 | SET `HUMAN_COORDINATION_REVIEW_REQUIRED` | exact uncertain `WWC_PROJECTION_EVENT` | resolution group null |
| TR-095 | CLEAR exact coordination-review cause | copied from active SET | exact resolving `EVALUATION` for source/calendar proof or exact resolving `HUMAN_FACT_EVENT` for structured human proof; new evaluation/WWC projection/clear bundle is atomic |

TR-022's resolver is also the source of a new, different recheck cause, but that new SET derives its own cause key and never rewrites the source-absence key. No transition may substitute the resolver entity for the original cause.

Lifecycle serialization order follows the dedicated registry: TR-022 appends the extraction-failure wrapper before CLEAR and the replacement SET; TR-023/TR-024 append snapshot then evaluation before CLEAR. The resolver must exist and hash-validate before the CLEAR wrapper, so the reverse order is illegal even though the complete business transaction is atomic.

`resolution_reason_code` is exact for every CLEAR: TR-022 uses `RC-014`; TR-023 and TR-024 use null because an accepted complete evaluation is the proof and no dedicated attention-resolution reason exists; TR-026 uses `RC-061` or `RC-062` according to the accepted action-verification provenance; TR-093 and TR-095 use the closed mappings below. Every SET has this field null. The full event-envelope `reason_codes` may retain the larger transition-specific registered set; it cannot contradict the singular resolution reason.

TR-093 uses exactly:

| Resolution branch | Active cause source | Resolver source | Resolution reason |
|---|---|---|---|
| exact system link resolution | `RESULTING_ORDER_LINK_EXACT_EVENT` | accepted system-proved `RESULTING_ORDER_LINK_EXACT_EVENT` with exact successor mapping | `RC-070` |
| exact human link resolution | `RESULTING_ORDER_LINK_EXACT_EVENT` | accepted structured-human-proved `RESULTING_ORDER_LINK_EXACT_EVENT` with exact successor mapping | `RC-071` |
| ambiguous search resolved by exact system link | `RESULTING_ORDER_LINK_SEARCH_EVENT` | accepted system-proved `RESULTING_ORDER_LINK_EXACT_EVENT` for the same parent case, source opportunity, Action Context/scope, and resolved child/mapping subject | `RC-070` |
| ambiguous search resolved by exact human link | `RESULTING_ORDER_LINK_SEARCH_EVENT` | accepted structured-human-proved `RESULTING_ORDER_LINK_EXACT_EVENT` for the same parent case, source opportunity, Action Context/scope, and resolved child/mapping subject | `RC-071` |
| complete negative search displaces candidate ambiguity | `RESULTING_ORDER_LINK_SEARCH_EVENT` | accepted `RESULTING_ORDER_LINK_SEARCH_EVENT(SEARCH_NOT_FOUND)` | `RC-073` |

The source/resolver identities must match the exact stream/natural subject owning the cause. A negative-search resolution never creates or changes an exact link. An accepted exact-link resolver may clear a search-ambiguity cause only through the two same-subject rows above; it preserves the immutable search history and does not rewrite its prior search event. Wrong stream, type, subject, SET, or key is RC-081 and rolls back the owning bundle.

TR-095 uses exactly:

| Resulting WWC partition | Resolver provenance | Resolution reason |
|---|---|---|
| `ACTIVE_SELF` | accepted `EVALUATION` for source proof, or exact structured coordination `HUMAN_FACT_EVENT`, bound into the resulting WWC projection | `RC-053` |
| `ACTIVE_OTHER_REP` | accepted `EVALUATION` for source proof, or exact structured coordination `HUMAN_FACT_EVENT`, bound into the resulting WWC projection | `RC-054` |
| `NOT_APPLICABLE` | accepted `EVALUATION` or exact structured coordination `HUMAN_FACT_EVENT` proving no qualifying contact, bound into the resulting WWC projection | null |
| `EXPIRED_OTHER_REP` | accepted source/calendar-bound `EVALUATION` proving the exact boundary and bound into the resulting WWC projection | null |

An uncertain result never clears a cause. A human resolution group points to the exact human fact; a source/calendar resolution points to the exact evaluation. Both paths append a new evaluation/WWC projection and preserve the old uncertain cause event.

Envelope `event_type` is `ATTENTION_SET` iff `operation=SET` and `ATTENTION_CLEARED` iff `operation=CLEAR`; no other pairing validates.

### 5.5 WWC projection/history

```text
WWCProjectionState = NOT_APPLICABLE | ACTIVE_SELF | ACTIVE_OTHER_REP |
                     EXPIRED_OTHER_REP | AUTHOR_UNCERTAIN |
                     TIMING_UNCERTAIN | AUTHOR_AND_TIMING_UNCERTAIN

DOIWWCProjectionEvent {
  <event-stream envelope; layer=EVALUATION_OUTPUT>,
  event_type: WWC_PROJECTION_APPENDED,
  wwc_projection_event_id: OpaqueId,
  case_id: OpaqueId,
  evaluation_id: OpaqueId,
  snapshot_id: OpaqueId,
  snapshot_content_sha256: Sha256,
  human_coordination_fact_id: OpaqueId | null,
  human_coordination_fact_content_sha256: Sha256 | null,
  business_calendar_version: VersionId,
  business_calendar_content_sha256: Sha256,
  prior_projection_state: WWCProjectionState | NONEXISTENT,
  resulting_projection_state: WWCProjectionState,
  qualifying_contact_at: Timestamp | null,
  protection_eligible_at: Timestamp | null,
  outreach_suppressed: boolean,
  TARGET_REP_work_blocked: boolean,
  dedupe_blocked: boolean
}
```

Each complete evaluation that evaluates WWC appends a projection event, even when the resulting state is unchanged, because the snapshot/calendar binding may differ. `ABSENT` yields `NOT_APPLICABLE`; deterministic SELF yields `ACTIVE_SELF`; deterministic OTHER_REP yields `ACTIVE_OTHER_REP` before the exact eligibility boundary and `EXPIRED_OTHER_REP` at/after it; unresolved author/time yields the exact uncertainty state and sets `HUMAN_COORDINATION_REVIEW_REQUIRED`. A new snapshot or exact human coordination fact may move any prior state to any deterministically supported next state. `REP_TRANSFERRED` case closure supersedes WWC handling without deleting its history before purge.

Enforce `UNIQUE(evaluation_id)` for `DOIWWCProjectionEvent`. Exact replay of the same evaluation plus byte-identical event returns the existing event; the same evaluation with different semantic/full-event bytes rejects with RC-106/RC-111 and changes no projection. A new evaluation ID is required for every later projection append, including a same-state projection.

### 5.6 Resulting-order link and history

```text
DOIResultingOrderLinkSearch {
  resulting_order_link_search_id: OpaqueId,
  search_schema_version: VersionId,
  parent_case_id: OpaqueId,
  source_opportunity_id: OpaqueId,
  action_context_id: OpaqueId | null,
  credit_scope_sha256: Sha256,
  search_natural_key_canonical_bytes: bytes,
  search_natural_key_sha256: Sha256,
  created_at: Timestamp,
  current_search_state: NOT_FOUND | AMBIGUOUS,
  current_event_id: OpaqueId
}

ResultLinkSearchCandidateIdentity {
  child_order_number: OrderNumber,
  candidate_evidence_fingerprint: Sha256
}

DOIResultingOrderLink {
  resulting_order_link_id: OpaqueId,
  link_schema_version: VersionId,
  parent_case_id: OpaqueId,
  relationship_type: FULFILLMENT_SPLIT_CHILD,
  child_order_number: OrderNumber,
  natural_key_canonical_bytes: bytes,
  natural_key_sha256: Sha256,
  source_opportunity_id: OpaqueId,
  action_context_id: OpaqueId | null,
  credit_scope_sha256: Sha256,
  created_at: Timestamp,
  current_state: AUTO_LINKED | HUMAN_CONFIRMED | AMBIGUOUS,
  current_mapping_revision_id: OpaqueId | null,
  current_event_id: OpaqueId
}

MovedLineMappingComponent {
  parent_line_snapshot_id: OpaqueId,
  child_line_snapshot_id: OpaqueId | null,
  quantity: Quantity
}

DOIResultingOrderLinkEvent {
  <event-stream envelope>,
  resulting_order_link_event_id: OpaqueId,
  resulting_order_link_search_id: OpaqueId | null,
  resulting_order_link_id: OpaqueId | null,
  search_occurrence_id: OpaqueId | null,
  parent_case_id: OpaqueId,
  prior_search_state: NOT_FOUND | AMBIGUOUS | NONEXISTENT | null,
  resulting_search_state: NOT_FOUND | AMBIGUOUS | null,
  prior_link_state: AUTO_LINKED | HUMAN_CONFIRMED | AMBIGUOUS |
                    NONEXISTENT | null,
  resulting_link_state: AUTO_LINKED | HUMAN_CONFIRMED | AMBIGUOUS | null,
  event_kind: SEARCH_NOT_FOUND | CANDIDATES_AMBIGUOUS | SYSTEM_LINK_VERIFIED |
              HUMAN_LINK_VERIFIED | CORROBORATING_EVIDENCE_APPENDED |
              EVIDENCE_CONFLICT,
  child_order_number: OrderNumber | null,
  search_candidate_identities: canonical ordered set<ResultLinkSearchCandidateIdentity>,
  search_candidate_set_canonical_bytes: bytes | null,
  search_candidate_set_sha256: Sha256 | null,
  moved_components: canonical ordered set<MovedLineMappingComponent>,
  verification_provenance: SYSTEM_VERIFIED | HUMAN_VERIFIED | null,
  logical_evidence_key_id: OpaqueId,
  verification_evidence_id: OpaqueId,
  verification_evidence_fingerprint: Sha256,
  natural_link_key_sha256: Sha256 | null,
  mapping_content_sha256: Sha256 | null,
  source_snapshot_ids: canonical ordered set<OpaqueId>,
  evidence_refs: canonical ordered nonempty set<CanonicalProofReference>
}
```

The search natural-key bytes are exactly JCS `{"search_natural_key_schema_version":"doi-result-link-search-natural/v1","parent_case_id":parent_case_id,"source_opportunity_id":source_opportunity_id,"action_context_id":action_context_id,"credit_scope_sha256":credit_scope_sha256}` and `search_natural_key_sha256=SHA256(UTF8("doi-result-link-search-natural/v1\n") || canonical_bytes)`; bytes are stored and byte-compared. `credit_scope_sha256` is the exact field-name alias of the source opportunity's `credit_scope_hash`; the values and canonical scope preimages MUST be byte-identical. Enforce both `UNIQUE(parent_case_id,source_opportunity_id,action_context_id,credit_scope_sha256)` with null-safe equality and `UNIQUE(search_natural_key_sha256)`. A later Action Context is intentionally a distinct search identity. The implementation resolves or creates the stable `resulting_order_link_search_id` from this key before any event append. Same digest/different bytes is RC-103 and appends nothing.

Exactly one of `resulting_order_link_search_id` and `resulting_order_link_id` is non-null on an event. Search events require a non-null stable proof-bound `search_occurrence_id`; exact-link events require it null. For search events, logical `search_kind` is the in-memory alias of `event_kind` and equals it exactly; it is serialized only in the logical material object. Search candidate bytes are exactly JCS `{candidate_set_schema_version:"doi-result-link-search-candidates-v1",candidates:[...]}` over the canonical ordered candidate identities, and `search_candidate_set_sha256=SHA256(UTF8("doi-result-link-search-candidates-v1\n") || candidate_bytes)` is stored/byte-compared. A `SEARCH_NOT_FOUND` event has search states only, `resulting_search_state=NOT_FOUND`, an exactly empty candidate set and its exact empty-set bytes/hash, and null child/natural-link/mapping fields. `CANDIDATES_AMBIGUOUS` has search states only, `resulting_search_state=AMBIGUOUS`, a nonempty canonical candidate set/bytes/hash, and the same null exact-link fields. Each candidate contains only exact child Order Number plus proof fingerprint; the canonical candidate bytes, fingerprints, referenced proof records, and source evidence are case-linked, privacy-allowlisted, and deleted at case purge. An exact-link event has only the link-state fields non-null, an empty in-memory candidate set, null candidate bytes/hash, and requires the exact non-null child and natural-link identity. Thus search `NOT_FOUND` and search `AMBIGUOUS` are never exact-link states. A later complete negative search may project AMBIGUOUS -> NOT_FOUND by appending the exact empty-candidate event and clearing that cause while preserving the old immutable candidate event. Exact event/candidate-set replay is idempotent; a different candidate set has a different material/evidence fingerprint. Exact system/human proof creates/reuses the exact link under the unique tuple `(parent_case_id,relationship_type,child_order_number)`; TR-054/055 own link creation, while TR-056/057 own resolution of an already-existing exact link in `AMBIGUOUS`.

Logical-material `candidate_set_sha256` is the exact field-name alias of event/evidence `search_candidate_set_sha256`; both names denote the same canonical candidate bytes/hash and may not be independently serialized. Event/revision/logical-material/evidence `moved_components` use the one closed `MovedLineMappingComponent` schema and identical canonical ordering; any legacy input label `moved_line_mappings` or member label `moved_quantity` MUST be normalized once to `moved_components[].quantity` before validation and is never persisted. Their `mapping_content_sha256` (also called `mapping_content_fingerprint` only at an external API boundary) is exact equality over those one canonical mapping bytes. An alias, member, order, or hash mismatch rejects the entire link transaction.

`DOIResultingOrderLinkEvent.event_kind` is the domain alias of envelope `event_type` and MUST equal it exactly. `HUMAN_LINK_VERIFIED` requires HUMAN/HUMAN_VERIFIED; `SYSTEM_LINK_VERIFIED` requires SYSTEM/SYSTEM_VERIFIED; search/conflict/corroboration provenance follows its exact evidence record and may not contradict the envelope.

Every stored link/search event references exactly one `DOILogicalEvidenceKey` and `DOIVerificationEvidenceRecord`. The link/search typed kind plus provenance MUST map to the evidence kind through the exhaustive table in `opportunity_kpi_contract.md` section 4.1; event ID/full-event hash, case, exact-link or search subject ID, natural/material fingerprints, evidence fingerprint, actor/provenance, mapping/candidate-set hash or search-state/null partition MUST otherwise equal the referenced evidence record and tagged payload. Search events bind logical kind `RESULTING_ORDER_LINK_SEARCH`; exact-link events bind `RESULTING_ORDER_LINK`.

For an exact-link event, `natural_link_key_sha256` MUST equal the base `DOIResultingOrderLink.natural_key_fingerprint` computed under `doi-result-link-natural-v1\n`; for a mapping assertion, `mapping_content_sha256` MUST equal the mapping revision/logical-material/evidence-payload alias computed under `doi-result-link-mapping-v1\n`. Search events require both fields null and instead bind the exact stable `search_natural_key_sha256` plus candidate-set hash through their logical key/material. For every search event, logical-material `search_evidence_at`, evidence-payload `evidence_occurred_at`, and envelope `occurred_at` MUST be exactly equal. Any time/hash alias mismatch is schema-invalid and appends nothing.

TR-110 appends mapping revision 1 for exact-link creation and mapping revision `n+1` for accepted conflict resolution under the exact `DOIResultingOrderLinkRevision` schema in `opportunity_kpi_contract.md` section 4.3. TR-111 appends the intervening `CONFLICT_REVIEW` revision. Row position, same-customer identity, and temporal proximity are never proof. Identical natural key + identical mapping/evidence is idempotent. Same exact natural key + contradictory mapping bytes appends `EVIDENCE_CONFLICT`, projects the exact link to `AMBIGUOUS`, sets cause-keyed `RESULTING_ORDER_LINK_REVIEW`, and makes disputed split credit zero. Multiple candidate children without one exact natural key remain solely in the search stream and use RC-072 only. A later exact system proof may supersede a consistent human confirmation in projection; both events remain.

### 5.7 Intervention action verification

Replace the conflated verification record with:

```text
DOIInterventionActionVerificationEvent {
  <event-stream envelope>,
  event_type: INTERVENTION_ACTION_SYSTEM_VERIFIED |
              INTERVENTION_ACTION_HUMAN_VERIFIED,
  action_verification_event_id: OpaqueId,
  case_id: OpaqueId,
  intervention_id: OpaqueId,
  intervention_type: InterventionType,
  action_context_id: OpaqueId | null,
  source_opportunity_ids: canonical ordered non-empty set<OpaqueId>,
  action_occurrence_id: OpaqueId,
  action_occurred_at: Timestamp | null,
  logical_evidence_key_id: OpaqueId,
  verification_evidence_id: OpaqueId,
  evidence_natural_key_sha256: Sha256,
  verification_evidence_fingerprint: Sha256,
  normalized_evidence_payload_sha256: Sha256,
  source_snapshot_ids: canonical ordered set<OpaqueId>,
  resulting_order_link_id: OpaqueId | null,
  replacement_line_snapshot_id: OpaqueId | null,
  evidence_refs: canonical ordered nonempty set<CanonicalProofReference>
}
```

The first accepted event creates exactly one intervention projection and owns the sole `NONEXISTENT -> VERIFIED` action-state edge. Exact fingerprint and identical canonical payload is idempotent and returns the original event/intervention. A later distinct compatible system/human proof for the same natural/material action may append only its immutable `DOIVerificationEvidenceRecord`; it creates no second action event, lifecycle wrapper, intervention, KPI effect, or `VERIFIED -> VERIFIED` transition. Same natural evidence key with conflicting payload fails closed and creates no second intervention/credit. `PRODUCT_SUBSTITUTION` requires an Action Context whenever current observation/contact/compatibility facts are relied upon; post-hoc system discovery may omit it but may not claim those readiness facts.

`INTERVENTION_ACTION_SYSTEM_VERIFIED` requires SYSTEM/SYSTEM_VERIFIED; `INTERVENTION_ACTION_HUMAN_VERIFIED` requires HUMAN/HUMAN_VERIFIED. `action_occurrence_id` is the stable proof/attestation occurrence identity from the ACTION natural-key registry; it is required even when exact business `action_occurred_at` is null. Envelope `occurred_at` is the required proof/attestation fact time and MUST equal evidence-payload `evidence_occurred_at`; it MUST NOT be substituted into `action_occurred_at`. For a credit-bearing intervention, null business time is legal only with otherwise complete action proof, emits RC-099, and creates no retained monetary row. Non-credit `DS_SEPARATION` does not receive RC-099 merely because no monetary attribution instant is required. `evidence_natural_key_sha256` is an exact alias of the referenced `DOILogicalEvidenceKey.natural_key_fingerprint` and the intervention projection's `action_natural_key_sha256`. Typed-event `evidence_refs` is the byte-for-byte canonical-set alias of evidence-payload `proof_refs`. `normalized_evidence_payload_sha256` is not a second digest: it MUST equal `verification_evidence_fingerprint`, namely `SHA256(UTF8("doi-verification-evidence/v1\n") || canonical_evidence_payload_bytes)`. The event's logical key ID, verification-evidence ID/fingerprint, kind, event ID/full-event hash, natural/material binding, actor/provenance, and canonical payload MUST equal the referenced `DOIVerificationEvidenceRecord`. Any mismatch is schema-invalid and appends nothing.

### 5.8 Value verification, correction, and reversal

```text
InterventionValueEventKind = ORIGINAL_VALUE_VERIFIED | ORIGINAL_VALUE_CORRECTED |
                             REVERSAL_VERIFIED | REVERSAL_CORRECTED |
                             REVERSAL_VOIDED

DOIInterventionValueEvent {
  <event-stream envelope>,
  value_event_id: OpaqueId,
  case_id: OpaqueId,
  intervention_id: OpaqueId,
  event_kind: InterventionValueEventKind,
  logical_occurrence_id: OpaqueId,
  exact_value: Money | null,
  provenance: SYSTEM_VERIFIED | HUMAN_VERIFIED,
  logical_evidence_key_id: OpaqueId,
  verification_evidence_id: OpaqueId,
  evidence_natural_key_sha256: Sha256,
  verification_evidence_fingerprint: Sha256,
  normalized_evidence_payload_sha256: Sha256,
  supersedes_value_event_id: OpaqueId | null,
  corrects_reversal_event_id: OpaqueId | null,
  evidence_refs: canonical ordered nonempty set<CanonicalProofReference>
}
```

`event_kind` is the domain alias of envelope `event_type` and MUST equal it exactly; the type-specific `provenance` MUST equal envelope `provenance`, with matching actor kind. `logical_occurrence_id` is the stable natural-key occurrence identity. Envelope `occurred_at` is the exact effective instant stored in the selected logical material object, never the natural key; it also equals evidence `evidence_occurred_at` only when that proof fact and effective fact are the same event instant. The per-kind field table is exhaustive:

| `event_kind` | `exact_value` | `supersedes_value_event_id` | `corrects_reversal_event_id` |
|---|---|---|---|
| `ORIGINAL_VALUE_VERIFIED` | exact nonnegative Money | null | null |
| `ORIGINAL_VALUE_CORRECTED` | exact nonnegative Money | required exact current authoritative original-value event | null |
| `REVERSAL_VERIFIED` | exact positive Money | null | null |
| `REVERSAL_CORRECTED` | exact positive Money | null | required exact current event in one active reversal chain |
| `REVERSAL_VOIDED` | null | null | required exact current event in one active reversal chain |

All fields not permitted by the selected row MUST be explicitly null, and no extension field is accepted. A predecessor must belong to the same retained case/intervention and identical currency-plus-ISO-registry-version/scale binding and be the exact current chain event; correction/void never deletes it. Values are exact ISO-4217 money and never cross currency or registry/scale bindings. A human value must be exact. Exact duplicate fingerprints and bytes are idempotent. Conflicting payload under one natural evidence key fails with RC-102, stale/foreign predecessor or envelope mismatch fails with RC-111, and a proven digest collision fails with RC-103; none appends an accepted value event or KPI delta.

For every value event, `evidence_natural_key_sha256` exactly equals the referenced `DOILogicalEvidenceKey.natural_key_fingerprint`; typed-event `evidence_refs` is byte-for-byte evidence-payload `proof_refs`; and `normalized_evidence_payload_sha256` exactly equals the referenced `verification_evidence_fingerprint` under the `doi-verification-evidence/v1\n` domain. The event's logical key ID, verification-evidence ID/fingerprint, event kind plus provenance-derived `EvidenceEventKind`, event ID/full-event hash, exact Money/predecessor/null partition, actor/provenance, and natural/material fingerprints MUST equal its `DOIVerificationEvidenceRecord` tagged payload. Multiple compatible evidence records may corroborate one logical key; they do not create a second value/reversal effect.

Current projection is deterministic:

1. For original value, an accepted `SYSTEM_VERIFIED` chain is authoritative over any human chain. Within the same provenance, only a later valid explicit correction of the current authoritative event replaces it.
2. Active reversals are distinct accepted `REVERSAL_VERIFIED` events after applying valid correction/void chains. Duplicate evidence contributes once.
3. `reversed_value` is the exact sum of active reversals sharing the authoritative original's identical currency code and ISO-registry-version/scale binding; `net_realized_value = authoritative_original - reversed_value`.
4. If no authoritative exact original exists, monetary contribution is zero. If currency or registry/scale bindings differ, or `reversed_value < 0` or exceeds original, retain the last valid projection and fail closed on the disputed event.
5. State is `VERIFIED` at zero reversed value, `PARTIALLY_REVERSED` when strictly between zero and original, and `REVERSED` when equal. Every correction may move among all three states; no row may assume monotonic reversal state.

### 5.9 Case lifecycle event narrowing

`DOIOrderLifecycleEventV2` is governed exclusively by `DOI_LIFECYCLE_EVENT_PAYLOAD_REGISTRY_v0.1.5.md`. Its exact 56-kind discriminated union, eight persisted case payload schemas, common envelope, two closed stream/retention classes (54 core kinds plus two target-owned one-event volatile record kinds), actor/time/reason rules, source-binding constructor, natural/payload/projection/full hash formulas, null/absent partitions, fixed vectors, replay/idempotency rules, and complete 115-transition route table are incorporated without variation. No competing case-lifecycle-kind enum exists in this module. The one `DOISourceImportAttemptRetentionEventV1/SOURCE_IMPORT_ATTEMPT_PURGE_FINALIZED` kind and its one purge payload schema are separately non-case and transaction-local; they do not change 56/eight.

`CASE_CREATED` and manager-origin `SOURCE_PRESENT` bind only a retained case-owned `DOICaseSourceAdmissionProofV1`, never an attempt-owned staged record. The proof's exact case/order/TARGET_REP/batch/case-binding/time/hash bytes contain no run ID, source-import-attempt ID/ordinal/token, source-row reference, spreadsheet/tab identity, or attempt actor. Its V1 fixed-vector proof ID/hash, event natural key, and full lifecycle hash are `e2aa8e7b7fe795821d230ede3d731c79f8670718e277d8d0812f1a83df97636e`, `2e9ac63cf8d5cda713e46351f4c8e8ce83429c2e39f35142113fd54da15f53b8`, `a8feba67a425e50f0a584a14336f4a3290a5f3de104cc0f86fb6ab2d34e3cb90`, and `0baab70132263d66f67582425bbf6d6c227ebb5c10317ea124babf5aee70c257`. Attempt/staged/source-row deletion therefore cannot break case replay.

A case-linked typed contact, DEDUPE, attention, Action Context, link, relationship, intervention, or value fact commits with a thin core lifecycle reference that stores the accepted typed event's exact ID/schema/kind/full hash, owner, actual prior/result state, and subordinate transition IDs—never its typed body. Immutable opportunity uses the core record-reference wrapper. Observation/context-link records use their target-owned volatile record-reference streams, change no core projection, and delete atomically with their targets. Arbitrary free text and implementation-selected extension fields remain forbidden.

The lifecycle registry's closed `PriorClosureRetentionBindingV1` is incorporated here as provenance-bearing state, not an optional audit annotation. `CaseReopenPayloadV2` and `PURGE_CANCELED` each require its complete explicit nested bytes. Those bytes bind the exact retained prior closure event ID/full hash, closed kind and hard/reversible classification, verified closure instant, policy ID/version, exact `America/New_York` timezone, tzdb version, local-calendar rule, active deadline, closure-bearing projection revision/hash, and prior closure source type/ID/schema/full hash. Reopen additionally binds its independent accepted proof; cancellation binds the exact reopen event as cause and the same proof as resolution source. The lifecycle source-binding arrays resolve all of those targets under the exact roles and cardinalities in registry section 2.1.1.

Under TR-014, the reducer locks the reversible closure-bearing projection and referenced retained sources, constructs and RFC-8785-serializes the authoritative binding, and requires byte equality before appending either lifecycle event. `prior_closure_projection_revision/hash` equal the pre-reopen envelope prior revision/hash; `prior_purge_eligible_at` equals its active deadline. The cancellation event copies the nested reopen bytes unchanged while independently resolving the same closure/proof/policy/projection authorities. No field may be recovered by inference from only a projection/event hash. Any missing target, unknown binding version, or field/canonical-byte mismatch rejects the complete typed/evaluation/reopen/cancel bundle with RC-113 and preserves every stream head and projection byte. Replay repeats the same validation and deterministically reproduces the exact same-case ACTIVE/null-deadline projection.

All executable known-answer case identities in this module use the reserved synthetic namespace. The DEDUPE review, DEDUPE decision, and attention-cause vectors use exact `SYN-DOI-CASE-PROV-0001`; their regenerated hashes are respectively `c2a58efae01d42a336654ad134ff2b63199b916e6e2330f7b8b0efdc12c615e5`, `4014615999a5f8c890cd1dd42b06d81e2e8be62c15bb030df20f103fab67bf06`, and `b9aa571b62e7fbc8b03bc83bd95914ec97a517ff50cd71cc71985362ef816262`. `case-fixture-001` and any other non-`SYN-DOI-` executable case identity are rejected by `SYN-OA-RO-009` before fixture execution.

## 6. Reason-code additions

Add exactly these versioned codes after the currently assigned registry range. Codes are immutable after publication.

| ID | Code | Class | Owner | Deterministic trigger/effect |
|---|---|---|---|---|
| RC-105 | EVALUATION_PROVENANCE_INCOMPLETE | BLOCK | DOIEvaluation | A required snapshot/rules/calendar/relationship-revision/observation/human-fact binding is absent, out of scope, or cannot resolve. Append no evaluation. |
| RC-106 | EVALUATION_PROVENANCE_HASH_MISMATCH | BLOCK | DOIEvaluation | A bound version/ID resolves but its canonical content digest differs. Append no evaluation; never substitute another version. |
| RC-107 | ALTERNATE_RELATIONSHIP_CREATED | AUDIT | DOIAlternateRelationshipRevision | Valid product-only evidence creates one stable relationship plus immutable revision 1. |
| RC-108 | ALTERNATE_RELATIONSHIP_REVISION_APPENDED | AUDIT | DOIAlternateRelationshipRevision | Accepted explicit product-only change appends exactly revision `n+1`; prior revisions remain unchanged. |
| RC-109 | ALTERNATE_RELATIONSHIP_REVISION_CONFLICT | BLOCK | DOIAlternateRelationshipRevision | With a valid current envelope, identity-field mutation, event-type/state mismatch, unsupported semantic product content, or illegal terminal reactivation is attempted. Reject and retain projection. Stream/revision-number/predecessor/full-event conflicts use RC-111 exclusively. |
| RC-110 | ACTION_CONTEXT_BINDING_INVALID | BLOCK | DOIActionContext | Context is absent, closed, wrong case/evaluation/opportunity/kind, or an observation/fact is not explicitly linked to it. It cannot satisfy action readiness. |
| RC-111 | EVENT_STREAM_SEQUENCE_CONFLICT | SAFETY | any typed immutable history | Proposed append has a non-current sequence/predecessor/digest, or reuses an event identity with different canonical bytes. Reject the append and retain the last valid projection; apparent content-hash collisions also invoke RC-103. |
| RC-112 | HUMAN_FACT_PROVENANCE_INCOMPLETE | BLOCK | DOIHumanFactEvent | Actor, exact structured scope, evidence fingerprint, provenance, DEDUPE review/verification binding, or legal correction predecessor is absent/conflicting. Reject the fact; do not evaluate from it. |

`RC-084 RULE_VERSION_UNAVAILABLE` remains correct when the requested rules bundle cannot load. `RC-105` covers an incomplete binding manifest; `RC-106` covers a resolved-but-mismatched digest. Existing observation, WWC, DEDUPE, intervention, value, reversal, retention, and OA safety codes remain authoritative.

## 7. Transition-matrix additions (TR-082 through TR-097)

Every row appends the typed event named above and updates only a rebuildable projection. An unlisted or unsupported transition fails with `STATE_TRANSITION_NOT_ALLOWED`; a digest/stream conflict uses its more specific code.

| ID | Stream | From | Deterministic action/guard | To / required effects | Allowed codes |
|---|---|---|---|---|---|
| TR-082 | relationship | NONEXISTENT | Explicit verified, canonical, product-only evidence passes identity/type/privacy invariants | ACTIVE revision 1; create stable ID and append revision; no case reverse-link | RC-107 |
| TR-083 | relationship | ACTIVE revision `n` | Explicit verified product-only fact change; exact current predecessor; change neither supersedes nor invalidates relationship | ACTIVE revision `n+1`; append only; exact semantic replay is idempotent no-op | RC-108; conflict RC-109 |
| TR-084 | Action Context | NONEXISTENT | Authorized human begins one attempt; exact retained case/evaluation and compatible opportunity/kind | OPEN; append immutable base + creation event; zero OA action/write | no additional reason required |
| TR-085 | Action Context | OPEN | Successful explicit current observation after context creation; exact case/opportunity/product/revision match | OPEN; append observation and immutable context link in one transaction | RC-044/045 as applicable; invalid RC-110 |
| TR-086 | Action Context | OPEN | One accepted same-context trigger from the closed Section 4 completion table explicitly ends this attempt | CLOSED_COMPLETED; append `ACTION_CONTEXT_COMPLETED` with the exact allowed close-reason/trigger pair; context base/events remain to case purge, while observation/link/volatile-wrapper targets obey the earlier nominal/case deadline and leave only sealed downstream commitments | only the closed completion event/trigger pair; action source reason is `RC-061` or `RC-062` where applicable |
| TR-087 | Action Context | OPEN | Explicit human abandonment, or a later same-scope attempt is created and supersession is recorded | CLOSED_ABANDONED or CLOSED_SUPERSEDED according to exact event; later attempt uses TR-084/new ID | invalid RC-110 |
| TR-088 | resulting-link search | NONEXISTENT, NOT_FOUND, or AMBIGUOUS | Complete explicit search finds no exact child; from AMBIGUOUS it explicitly disproves every prior candidate | NOT_FOUND; append distinct empty-candidate evidence; exact replay no-op; split realized value remains zero; from AMBIGUOUS invoke cause-keyed TR-093 | RC-073 |
| TR-089 | resulting link | NONEXISTENT, NOT_FOUND, or AMBIGUOUS | New accepted evidence yields multiple candidates or unresolved child/mapping | AMBIGUOUS; append distinct evidence and invoke TR-092; exact replay no-op | RC-072 |
| TR-090 | resulting link | AUTO_LINKED or HUMAN_CONFIRMED | New distinct corroborating evidence agrees on exact child and mapping | Same state; append corroboration. Exact duplicate fingerprint is idempotent and appends nothing | RC-070 or RC-071; no duplicate reason required |
| TR-091 | resulting link | HUMAN_CONFIRMED | Later exact deterministic system evidence agrees with child and mapping | AUTO_LINKED; append system event; preserve human event | RC-070 |
| TR-092 | attention | named cause absent or other causes already present | One distinct exact-link conflict or ambiguous search event becomes the complete v2 cause; resolution group is null | SET only that cause-keyed `RESULTING_ORDER_LINK_REVIEW`; disputed scope zero | RC-072 or RC-104 |
| TR-093 | attention | exact active link/search-review SET present | CLEAR copies the SET cause/key and binds an independent exact accepted-link resolver or `SEARCH_NOT_FOUND` resolver | Remove only that active cause; exact-link system/human resolution uses RC-070/071; negative search uses RC-073 and never changes an exact link | RC-070, RC-071, or RC-073 exactly by Section 5.4 branch; invalid provenance/key RC-081 |
| TR-094 | attention | named cause absent or other causes already present | One uncertain WWC projection event is the complete v2 cause; resolution group is null | SET only that cause-keyed `HUMAN_COORDINATION_REVIEW_REQUIRED`; preserve opportunities; block affected action/DEDUPE only | RC-055/056 plus RC-057 |
| TR-095 | attention | exact active coordination-review SET present | CLEAR copies the SET cause/key and independently binds the exact resolving evaluation or structured human fact | Remove only that active cause; append evaluation/WWC event atomically; resulting ACTIVE_SELF/OTHER uses RC-053/054, NOT_APPLICABLE/EXPIRED uses null | RC-053, RC-054, or null exactly by Section 5.4 branch; invalid provenance/key RC-081 |
| TR-096 | DEDUPE | CANDIDATE, HUMAN_APPROVED_AWAITING_OA_VERIFICATION, or HUMAN_REJECTED | New accepted evaluation proves any DEDUPE blocker/opportunity | NOT_CANDIDATE; append withdrawal; stale human approval never writes OA or closes case | RC-059 plus exact blocker |
| TR-097 | human fact | no accepted event for this exact evidence fingerprint | Authorized human submits one complete Section 5.1 `fact_kind`/`result_code` pair with exact scope/provenance, including constructible DEDUPE pairs | append immutable HUMAN_VERIFIED fact; DEDUPE pairs commit only inside atomic TR-061/TR-062 and are linked by exact event ID/hash; other rules-relevant facts may invoke TR-028 | closed `HumanFactResultCode`; invalid `RC-112`; stream `RC-111`; collision `RC-103` |

## 8. Required amendments to existing transitions

The following are corrections to existing IDs, not additional transitions.

### 8.1 Evaluation append

- `TR-027` and `TR-028` require the complete Section 2 binding manifest. A missing/hash-mismatched binding appends no evaluation. `TR-028` includes a new accepted relationship revision, current observation, or structured human fact—not a bare manual ID—as a legal re-evaluation cause.

### 8.2 Relationship state

- `TR-040 ACTIVE -> SUPERSEDED` appends revision `n+1` with state `SUPERSEDED`, exact predecessor, successor relationship ID, RC-046, and RC-108. It never mutates revision `n`.
- `TR-041 ACTIVE -> INVALIDATED` appends revision `n+1` with state `INVALIDATED`, explicit contradictory product evidence, RC-047, and RC-108. Non-rediscovery remains no transition.

### 8.3 Observation state

- `TR-042` requires an exact relationship revision and, when used as current for action, an OPEN Action Context plus the atomic TR-085 link.
- `TR-043` deletes either a de-linked observation at its exact nominal expiry or a case-linked observation/link/volatile-wrapper target graph when that same nominal expiry is earlier than case purge. TR-018/019 deletes the linked target graph when case purge is earlier. Deletion never changes the durable relationship; sealed preexisting evaluation/opportunity commitments remain non-resolvable/non-fresh only until case purge.

### 8.4 Intervention/value reducer

- `TR-044`, `TR-045`, and `TR-045A` append an exact `DOIInterventionActionVerificationEvent`. Identical fingerprint/payload returns the original intervention; conflicting same-natural-key payload fails closed.
- Each accepted TR-044/045/045A bundle invokes TR-106 using the exact exhaustive table in `opportunity_kpi_contract.md` section 3.3. Let `B` be the credit-bearing date/currency base reason set: exact date with valid or absent currency yields `{RC-063}`; exact date with invalid supplied currency/registry yields `{RC-063,RC-094}`; null exact business action date with valid or absent currency yields `{RC-063,RC-099}`; and null date with invalid supplied currency/registry yields `{RC-063,RC-094,RC-099}`. TR-106 then unions at most one exact rep-proof modifier: verified split with an exact child link and missing/different/ambiguous resulting-order-level TARGET_REP rep adds only RC-074; substitution with an exact replacement-line binding and missing/different/ambiguous line-level TARGET_REP rep adds only RC-075; verified rep adds neither. RC-074 never depends on replacement-line rep, RC-075 never depends on parent/resulting-order rep, and wrong-type, contradictory, or both-code input rejects with RC-081 before append. The applicable state/value/link result remains the section-3.3 result: the valid intervention is preserved; the retained row is created only when the base permits it; rep failure never changes the verified link/binding and keeps value `UNVERIFIED` with zero money. `DS_SEPARATION` is `NOT_APPLICABLE`, all Money/currency fields null, no row, and neither RC-063, RC-074, RC-075, nor RC-099 merely because no monetary date or rep proof is needed. Pre-Money validation failure rejects only the invalid monetary material while preserving the independently valid single action, and never allocates a second intervention.
- `TR-046` and `TR-047` append exact system/human original-value events from UNVERIFIED and atomically invoke KPI subtransition `TR-107`.
- `TR-048` accepts a valid exact correction or system-over-human authority event and recomputes original/reversed/net from all accepted events; it may result in VERIFIED, PARTIALLY_REVERSED, or REVERSED.
- `TR-049`, `TR-050`, and `TR-051` cover a recomputed active reversal sum of respectively zero, strictly between zero and original, or equal to original, from **any** previously value-verified status.
- `TR-052` covers a valid reversal correction/void, recomputes through the same reducer, and atomically invokes KPI subtransition `TR-109`; old reversal events remain.
- `TR-053` covers an accepted authoritative original-value correction after reversals, recomputes through the same reducer, and atomically invokes KPI subtransition `TR-108`. Any invalid amount/currency/evidence retains the prior projection and is not an accepted transition.

This replaces the incomplete assumption that reversal state can only increase monotonically.

### 8.5 Resulting-order link

- `TR-054` and `TR-055` create an exact link only from exact-link `NONEXISTENT`; any prior search stream may independently be absent, `NOT_FOUND`, or `AMBIGUOUS`. Both append the typed exact-link event and invoke TR-110 for verified mapping revision 1. If a prior search ambiguity owns a review cause, they also invoke TR-093 for that exact cause.
- `TR-056` and `TR-057` resolve an already-existing exact link from exact-link `AMBIGUOUS`, MUST invoke TR-110 for verified mapping revision `n+1`, and MUST invoke TR-093. They never reinterpret or overwrite a search-state event.
- `TR-058` and `TR-059` append evidence conflict, project AMBIGUOUS, invoke TR-092, and set disputed credit to zero. Contradictory canonical payload never overwrites the existing link event.

The full bundle for each row is atomic. TR-054/055 include logical key + evidence + exact-link typed event + base link + TR-110 revision 1 + projection + any cause-keyed TR-093 clear + KPI recomputation. TR-056/057 include logical key/evidence + resolution event + TR-110 successor revision + projection + TR-093 clear + KPI recomputation. TR-058/059 include the M2 logical key/evidence + conflict event + TR-111 revision + AMBIGUOUS projection + TR-092 cause + zero disputed KPI recomputation. Any failed append, unique/FK/hash/stream check, or projection update rolls back every component.

### 8.6 DEDUPE

- `TR-060` also permits `HUMAN_REJECTED -> CANDIDATE` when a later complete evaluation newly satisfies every candidate guard. The prior rejection remains history and no approval is inferred.
- `TR-061` from `CANDIDATE` accepts only a first constructible `DEDUPE_APPROVED`/`APPROVED` HUMAN_FACT with null supersedes for the exact active review. It atomically appends/reuses that fact, appends/reuses `DOIDedupeStateEvent(HUMAN_APPROVED)` with the exact fact ID/hash, and projects `HUMAN_APPROVED_AWAITING_OA_VERIFICATION`. No component commits alone.
- `TR-062` from `CANDIDATE` accepts only a first constructible `DEDUPE_REJECTED`/`REJECTED` HUMAN_FACT with null supersedes. From `HUMAN_APPROVED_AWAITING_OA_VERIFICATION`, it accepts only the exact predecessor-bound `HUMAN_FACT_CORRECTED` rejection before OA note verification. It atomically appends/reuses the fact, exact linked `HUMAN_REJECTED` event, and projection; prior approval bytes remain. Same-review conflict without this legal predecessor is RC-112. Rejected-to-approved requires a later TR-060 evaluation and a newly derived review identity.
- `TR-063` requires a new complete read-only snapshot that verifies the OA note. Human approval alone never confirms or closes.
- `TR-064` retains the exact source-grounded reopen semantics. TR-096 handles non-confirmed candidate withdrawal.
- OA notes, OA note findings, and unrelated lifecycle events never construct or infer `DEDUPE_APPROVED`/`DEDUPE_REJECTED`; note verification remains a separate later read-only source fact. Every DEDUPE decision transaction has OA read/write count zero.

### 8.7 Contact

All `TR-065` through `TR-073`, `TR-080`, and `TR-081` are per-Action-Context transitions and append `DOIContactStateEvent`.

- `TR-065` alone appends `CONTACT_REQUIRED_DERIVED` with `SYSTEM_VERIFIED` provenance from an exact accepted evaluation/opportunity. It records no contact occurrence.
- `TR-066`–`TR-073`, `TR-080`, and `TR-081` append only the matching human-recorded event kind with `HUMAN_VERIFIED` provenance and an exact occurrence instant.
- `TR-080` permits a new distinct actual attempt from `CONTACT_ATTEMPTED|AWAITING_CUSTOMER|CUSTOMER_DECLINED|NO_RESPONSE -> CONTACT_ATTEMPTED`.
- `TR-081` permits `CUSTOMER_APPROVED -> CUSTOMER_DECLINED` only on explicit human-recorded withdrawal/decline before action; it closes readiness and never reverses an already verified intervention.
- Exact evidence replay is idempotent. No state sends or reads a message, creates an intervention, or changes OA.

### 8.8 WWC

Revise `TR-074` through `TR-079` into a complete deterministic result partition for every accepted new evaluation:

| Existing ID | From | Result |
|---|---|---|
| TR-074 | ANY prior/nonexistent | NOT_APPLICABLE when no qualifying contact is present |
| TR-075 | ANY prior/nonexistent | ACTIVE_SELF on deterministic latest self evidence |
| TR-076 | ANY prior/nonexistent | ACTIVE_OTHER_REP before the exact protected-until boundary |
| TR-077 | ANY prior/nonexistent | EXPIRED_OTHER_REP at/after the exact eligibility boundary |
| TR-078 | ANY prior/nonexistent | AUTHOR_UNCERTAIN, TIMING_UNCERTAIN, or both when exact input is unresolved; invoke TR-094 |
| TR-079 | any state | same state on a newer accepted snapshot/calendar/human-fact binding; append a new projection event rather than rewriting prior history |

This covers SELF to OTHER, OTHER to SELF, expired to newly active, resolved to uncertain, and every other source-grounded change. No prior evaluation/projection is edited.

### 8.9 Purge transitions

`TR-018` and `TR-019` include every Section 9 edge and complete atomically with KPI finalization. There is no persisted `CASE_PURGED` event, transaction log entry, receipt, or tombstone; success is represented only by absence of the case graph plus the non-identifying bucket totals.

## 9. Purge graph and retention edges

At exact case purge, the transaction MUST finalize the current deduplicated non-identifying KPI contribution and delete all of the following before commit:

1. case/order identity, lifecycle events/projection, case-source admission proof/binding, snapshots/lines, extraction attempts, evaluations and their input/output hashes/bindings, opportunities, and case-owned work references; attempt-owned staged/source-row references are governed only by earlier/equal TR-114 and are never lifecycle targets;
2. every `DOIActionContext`, context event, context-observation link, and any case/action link to a product relationship;
3. every contact, DEDUPE, attention, WWC projection, miscellaneous human-fact, and manual-review event/fingerprint;
4. every intervention projection, action-verification event, value/correction/reversal event, natural evidence key, evidence fingerprint, and source evidence reference;
5. every resulting-order link/event, child Order Number, moved-line mapping, natural key, content/evidence fingerprint, and review condition;
6. every alternate observation still linked to any deleted context/case, even if its independent expiry is later;
7. any case-specific research/evidence object not independently sanitized into product-only reusable knowledge;
8. all logs, caches, queues, errors, and exports capable of reconstructing any deleted identity.

A stable `DOIAlternateRelationship` and its revision history may survive only because they contain product-only identities/provenance from inception. They MUST contain no originating Order Number, case, line snapshot, context, customer, source row, evaluation, opportunity, intervention, resulting order, or reconstructable derivative. Removing a reverse link at purge is insufficient if the relationship payload itself encoded case identity.

An observation's effective deletion is `min(independent_observation_expiry, linked_case_purge_eligible_at)`. A fully de-linked product-only observation may use its independent deadline. Content/evidence hashes that fingerprint a case are case detail, not anonymized aggregate data, and MUST delete at case purge. The only pre-purge residual permitted after earlier observation-target expiry is the already embedded sealed observation ID/hash inside an immutable retained evaluation/opportunity; it cannot resolve/reconstruct the target or satisfy freshness and is not independently retained after its case.

No later correction/reversal/link/Action Context request can resolve a purged target. It is rejected transiently with `CASE_IDENTITY_NOT_RETAINED`, changes no finalized aggregate, appends no persistent order-specific record, and performs no identity reconstruction.

### 9.1 Source-import-attempt and run deletion provenance

Every terminal source-import outcome—`SUCCEEDED`, `SCHEMA_REJECTED`, `SOURCE_CHANGED`, `INACCESSIBLE_OR_UNREADABLE`, `BATCH_INTEGRITY_REJECTED`, or intermediate `ABORTED_PRE_OA` followed by a later terminal attempt/run—receives the same exact `source_import_attempt_purge_eligible_at=calendar90(DOIRun.completed_at)`. While the run is nonterminal, every attempt deadline is null. Run event v2 stores attempt count only and no attempt ID/manifest. Sequential attempt IDs/tokens/ordinals and their indexes are attempt-owned.

At TR-114, one locked transaction constructs the exact sequence-1 `DOISourceImportAttemptRetentionEventV1` and `SourceImportAttemptPurgePayloadV1`, validates its terminal-attempt/run/policy/tzdb/deadline/aggregate/reference/result authorities and canonical hashes, then deletes the entire attempt projection/event/identity/source/artifact graph and the retention event itself. The reason set is exactly `[RC-114]` inside that event and survives nowhere. All payload members are required/non-null; only actor and predecessor envelope fields are null; extra fields are forbidden. The source-retention fixed vector's stream/event-ID/payload/full hashes are `b14b67e59e765b28d927b12a6d59b161944dd27c06dbe13ce3439000f3233513`, `86b3208fb50e2352a65a49b4a74016d00956fd9109f72030071848cb500aac90`, `2ad1678cdad8d10be9b4bbb2b46d9b7158c7635638356982b8ce120d7f4c7e32`, and `738fa8d9ac327be19c099404891e9d18f47a224d8e26c1006e6faa544241c4fe`.

Only `DOISourceImportAggregateV2 {aggregate_schema_version,local_calendar_month,attempt_outcome_class,attempt_count}` may survive. It contains no ID, reason, hash, exact instant, source/schema/tab/actor dimension, event/revision, or drill-through. A successful attempt releases its exact batch reference; other outcomes prove absence. TR-113 then applies independently. `DOIRunIdentityReferenceV1` owners are closed to attempt, staged, rejection, and `RUN_WORK_GRAPH`. The work owner is lawful only while a retained extraction/snapshot/evaluation chain resolves its exact run work item; a case-source admission proof/binding has no run ID and owns no run reference. A remaining non-due owner retains the byte-identical run; final-owner deletion removes every run identity/event/index/artifact atomically. Failure at aggregate, graph, edge, run, or transient-event deletion restores the complete pre-transaction state; repeat after absence is a no-op without tombstone.

## 10. Deterministic synthetic oracles to add

These tests are additive. Counts are derived after the complete remediation merge; none may be deleted merely to preserve 127.

The exact 22-test `SYN-IMPORT-RET-001..022` family in `source_retention_contract.md` section 13.6 is incorporated here without creating aliases. It exhaustively covers success/failure/abort-before-later-run deadlines, exact-boundary deletion, every closed outcome, no-batch and batch-release branches, multiple attempts/run last references, the four failure-injection/rollback positions, aggregate schema, artifact scans, idempotency/no tombstone, host-timezone independence, DST, and unknown/null/extra/hash rejection. Those tests are the deterministic provenance proof for section 9.1.

### 10.1 Evaluation provenance

| Test ID | Fixture/action | Exact oracle |
|---|---|---|
| SYN-EVAL-PROV-001 | Use `DOI_EVALUATION_PROVENANCE_VECTOR_v0.1.5.5.json`: the unchanged exact v0.1.5.4 compatibility fixture and rules/usage binding plus the v0.1.5.5 `doi-human-fact-binding/v1` known-answer contract. Enumerate every schema-defined set/map in multiple input orders and execute the published empty-prefix, wrong-version-prefix, missing-LF, pretty/non-JCS, one-member-mutation, uppercase-expected-digest, malformed-expected-digest, stale-rules, unavailable-rules, unknown-registry, and tampered-hash selectors. | The validated binding's JCS bytes equal the fixed 425-byte vector and `SHA256(UTF8("doi-human-fact-binding/v1\n") || binding_bytes)` equals `07dc93c4fabdad118c2c16d79375ff314b3ee3e1bb5da242e4670dafe96adaa8`. Reordered equivalent set inputs reproduce identical binding bytes/digest; every material member mutation changes both. Wrong domain/non-JCS/uppercase/malformed/mismatched expected values fail the known-answer check. The binding digest remains distinct from the fact-content, evaluation-input, output, and full-record digests. Illegal binding bytes fail RC-105 before a digest can legitimize them; resolved digest mismatch is RC-106; unavailable rules is exactly RC-084. No branch appends a substitute or alters RC-115. |
| SYN-EVAL-PROV-002 | Correct snapshot ID, wrong snapshot digest | No evaluation; RC-106; facts unchanged. |
| SYN-EVAL-PROV-003 | Relationship used but revision binding absent | No evaluation; RC-105; no substitute current revision. |
| SYN-EVAL-PROV-004 | Evaluation uses revision 1; relationship later appends revision 2 | Old evaluation still resolves revision 1/hash and reproduces; new evaluation may bind revision 2. |
| SYN-EVAL-PROV-005 | Retain every prior HumanFactKind/result/payload/idempotency/correction and v0.1.5.4 legal/illegal usage selector, then also table-drive same binding, equivalent set ordering, and changes to usage, Action Context, line scope, fact event ID, or fact content hash with their derived binding digests. Include illegal pair plus correct digest and legal binding plus mismatched expected digest. | Same canonical binding and equivalent set order produce the same digest; each material change produces different bytes/digest. Illegal bindings fail RC-105 before hashing can confer validity, including an otherwise correctly computed digest; a mismatched expected digest fails RC-106. Valid fact construction remains TR-097, DEDUPE remains TR-061/062, prior evaluation bytes remain reproducible, and existing RC-112/111/103 routes remain unchanged. No new test ID, family, reason code, transition, or stored binding member. |
| SYN-EVAL-PROV-006 | Observation used for readiness but linked to another/closed context | No readiness/evaluation result dependent on it; RC-110 and RC-044/045 as applicable. |
| SYN-EVAL-PROV-007 | WWC evaluated with missing/mismatched calendar hash | No evaluation; RC-105/106; never infer expiry. |
| SYN-EVAL-PROV-008 | Inspect records by layer | Snapshots contain only source facts; human facts preserve provenance; evaluations contain outputs; lifecycle histories contain events only. |

### 10.2 Relationship revisions

| Test ID | Fixture/action | Exact oracle |
|---|---|---|
| SYN-ALT-REV-001 | Submit one valid product-only relationship identity/revision payload in multiple source-provenance input orders against fixed identity, semantic-revision, and full-event hash vectors; then concurrently submit the same canonical bytes | Every canonical order matches the known-answer vectors. One stable ID plus one revision 1 ACTIVE; RC-107 occurs once; every submitter resolves the same identity/current revision; no case/order/context reverse-link. |
| SYN-ALT-REV-002 | Explicit compatible product fact change | Revision 2 ACTIVE points to revision 1; revision 1 bytes unchanged; RC-108. |
| SYN-ALT-REV-003 | Exact base-identity/current-revision semantic replay, then table-drive semantic field/null/set/domain/full-event tamper and an injected same identity digest with different bytes | Exact bytes return the stable relationship/current revision with append counts unchanged. Any semantic/full-event tamper or noncanonical/missing/extra member is rejected with RC-109 or RC-111 according to semantic vs envelope ownership; different identity bytes under one digest fail RC-103. No branch creates a base/revision/projection. |
| SYN-ALT-REV-004 | Table-drive (a) valid-envelope revision that mutates a base identity field, mismatches event type/state, or carries unsupported product content and (b) stale revision number/predecessor/full-event hash | (a) rejects with RC-109; (b) rejects exclusively with RC-111. Current relationship/revision projection remains byte-identical in every branch. |
| SYN-ALT-REV-005 | Explicit successor evidence | Append terminal SUPERSEDED revision with successor relationship; prior revisions unchanged. |
| SYN-ALT-REV-006 | Explicit contradictory evidence | Append terminal INVALIDATED revision; non-rediscovery alone appends nothing. |
| SYN-ALT-REV-007 | Attempt terminal relationship reactivation | Reject RC-109; new verified knowledge requires a valid new identity. |
| SYN-ALT-REV-008 | Inject originating order/case/source-row marker into revision/provenance | Persistence rejects it; marker absent from durable product store. |

### 10.3 Action Context/contact

| Test ID | Fixture/action | Exact oracle |
|---|---|---|
| SYN-ACTX-001 | Table-drive every valid context-kind/opportunity/gate pair in the Section 4 table, with an explicit fresh `attempt_intent_id`; replay each token with identical and then different request bytes | Each fresh token creates one OPEN context bound to the exact case/evaluation/opportunity/scope/option/gates and derived intervention type; same token/same bytes reuses it; same token/different bytes rejects RC-110 with no append; zero OA action/write. |
| SYN-ACTX-002 | Table-drive (a) explicit human abandonment and (b) creation of a later same-scope attempt with a fresh `attempt_intent_id` | (a) TR-087 appends `ACTION_CONTEXT_ABANDONED`, `OPEN -> CLOSED_ABANDONED`, with `HUMAN_ABANDONED`; (b) the fresh token creates a new context ID and the old OPEN context appends `ACTION_CONTEXT_SUPERSEDED`, `OPEN -> CLOSED_SUPERSEDED`, with `SUPERSEDED_BY_LATER_ATTEMPT`. Reusing the prior token cannot create a later attempt. Old base/events remain unchanged. |
| SYN-ACTX-003 | Context A observation offered to context B | RC-110; observation is not current for B. |
| SYN-ACTX-004 | Recheck Alternate in open context against fixed observation/link hash vectors; replay identical context/observation/revision tuple, then mutate bytes | New immutable observation plus one exact context link; exact tuple replay reuses the link; changed bytes reject RC-110; all known-answer hashes match and old observations remain unchanged. |
| SYN-ACTX-005 | Table-drive every unlisted context-kind/opportunity pair, missing/wrong gate/scope/option/intervention type, an observation-link attempt after context closed, and a structured HumanFact whose direct `action_context_id` names a closed/wrong-scope context | Reject RC-110 with no context/link/fact append and no readiness; prior projections unchanged. HumanFacts never alias the observation-link schema. |
| SYN-ACTX-006 | Table-drive every completion-trigger/context-kind/source row above and every cross-product invalid pairing; separately submit coordination, normal-progress, out-of-scope, and compatibility-needs-more-evidence facts | Each allowed row performs exactly `OPEN -> CLOSED_COMPLETED` with one matching close reason/trigger/source. Every unlisted kind, mismatched intervention/opportunity/scope, or wrong source is RC-110 with no close. The separately valid non-completion facts append under their own rules but never invoke TR-086. No case-global approval, message, autonomous intervention, or OA write occurs. |
| SYN-ACTX-007 | Human withdraws approval before action | Append CUSTOMER_DECLINED; readiness closes; approval event remains. |
| SYN-ACTX-008 | New context after prior approval | Begins at NOT_CONTACTED; prior approval is not reused. |

### 10.4 DEDUPE, attention, and WWC

| Test ID | Fixture/action | Exact oracle |
|---|---|---|
| SYN-DED-006 | With exact reserved case `SYN-DOI-CASE-PROV-0001`, derive fixed review ID `c2a58efa...c615e5`; submit one valid `DEDUPE_APPROVED` fact with decision fingerprint `40146159...7bf06` and inject failure after each human-fact/DEDUPE/projection write; then replay byte-identical decision evidence | Both regenerated known-answer hashes match. One ACID transaction appends exactly one HUMAN_FACT plus one TR-061 DEDUPE event with exact fact ID/hash and projects `HUMAN_APPROVED_AWAITING_OA_VERIFICATION`. Every injected failure leaves both streams/projection unchanged; exact replay creates zero events; a non-`SYN-DOI-` executable case identity rejects before execution; OA read/write count zero. |
| SYN-DED-007 | Table-drive initial rejection, approval followed by predecessor-bound rejection/retraction before OA verification, every illegal same-review conflict/correction, and a new candidate evaluation after rejection | Initial rejection appends one fact + TR-062. Legal retraction preserves approval and appends one corrected rejection + TR-062 atomically. Missing/wrong predecessor, rejected-to-approved same-review change, or changed same-kind semantic payload is RC-112 with no append. A later candidate derives a different review ID and may receive its own first decision. |
| SYN-DED-008 | Table-drive OA DEDUPE note PRESENT with no human decision, human approval with no OA recheck, then a later complete read-only snapshot proving the note | OA note alone creates no human fact, approval, or closure. Human approval alone stops at awaiting verification. Only separate `OA_NOTE_SYSTEM_VERIFIED` may invoke TR-063/closure. No note text is retained; OA write/mutation count zero. |
| SYN-STATE-001 | DEDUPE candidate then new split opportunity | TR-096 -> NOT_CANDIDATE; prior candidate/human decision retained; no OA note write. |
| SYN-STATE-002 | HUMAN_REJECTED then later complete no-solution evaluation | Revised TR-060 -> CANDIDATE; rejection remains history; no approval inferred. |
| SYN-STATE-003 | Result link becomes ambiguous | TR-092 sets only RESULTING_ORDER_LINK_REVIEW; other attention/opportunities remain. |
| SYN-STATE-004 | Table-drive system and human resolution of an already-existing exact link in `AMBIGUOUS` after conflict revision `n` | TR-056/057 appends exact-link resolution, TR-110 appends verified mapping revision `n+1`, and TR-093 CLEAR copies the exact active v2 cause while independently binding the system/human resolver with RC-070/071. No search event is rewritten; other causes remain; disputed value may be reevaluated. |
| SYN-STATE-005 | WWC author/time uncertain | TR-094 sets HUMAN_COORDINATION_REVIEW_REQUIRED; DEDUPE/action blocked; opportunity analysis preserved. |
| SYN-STATE-006 | Later exact source/calendar or structured-human coordination resolution | TR-095 CLEAR copies the exact active uncertain-WWC cause, binds the independent evaluation or HUMAN_FACT resolver, uses RC-053/054/null exactly by resulting partition, and atomically appends the new evaluation/WWC event. Old uncertainty provenance remains; other causes do not change. |
| SYN-STATE-007 | Table-drive SELF->OTHER, OTHER->SELF, EXPIRED->ACTIVE, resolved->uncertain, uncertain->resolved | Every change is legal only with exact new snapshot/calendar/human binding and appends history; no state overwrite. |
| SYN-STATE-008 | Table-drive (a) first accepted evaluation with no qualifying contact and (b) a newer accepted snapshot that again has no qualifying contact | (a) TR-074 appends `NONEXISTENT -> NOT_APPLICABLE`; (b) TR-079 appends `NOT_APPLICABLE -> NOT_APPLICABLE` with new bindings. Both use the canonical `WWCProjectionState`; prior events remain unchanged. |
| SYN-STATE-009 | Table-drive every typed immutable stream and registered semantic/base hash, including DEDUPE review/decision vectors and ATTENTION v2 cause/resolver vectors; then submit stale sequence/predecessor, wrong owner-derived stream ID, wrong schema/domain prefix, duplicated alias/extra field, null/order/payload tamper, and reused identity with different bytes. Also table-drive the closed `DOIRun` projection: `IN_PROGRESS` requires non-null `started_at`, null `completed_at`, and null `run_purge_eligible_at`; the TR-001 invocation branch additionally requires initial null `source_batch_id`, while later governed active processing may bind it. Each of `COMPLETED`, `COMPLETED_WITH_EXCEPTIONS`, and `FAILED` requires non-null `completed_at` and exact `calendar90(completed_at)` run deadline; unknown status, terminal-to-`IN_PROGRESS`, or either nullability mismatch rejects before persistence. | Every valid vector matches its exact formula. Every illegal append is rejected by its semantic code or RC-111 for stream identity, prior bytes/projection stay identical, and a proven collision adds RC-103. v1/v2 attention mixtures and DEDUPE event aliases are rejected. The `RUN_INVOCATION_ACCEPTED` event omits completion time while the reduced active projection materializes its required `completed_at` member as null. |
| SYN-STATE-010 | Two different links independently SET `RESULTING_ORDER_LINK_REVIEW`; resolve only one | Both v2 SET events have distinct cause keys. One exact CLEAR references and removes only its SET while preserving independent resolver provenance; the other remains and displayed condition stays present. Resolving the second clears it; unrelated attention/opportunities never change. |
| SYN-STATE-011 | Table-drive DEDUPE occurrence/review identity: derive a system candidate twice, submit constructible approval, exact replay, legal predecessor-bound retraction, and every illegal kind/source/fact partition or arbitrary system token | Same evaluation derives one occurrence/review ID and exact replay appends nothing; changed system bytes reject RC-111. Approval atomically appends one exact human fact + DEDUPE event; legal retraction appends one corrected fact + event and preserves approval. Reused token/different fact or illegal same-review decision is RC-112. OA mutation/write count zero. |
| SYN-STATE-012 | Build the Section 5.4 known-answer cause key with exact reserved case `SYN-DOI-CASE-PROV-0001` and valid SET; mutate every cause member and SET null-partition field | Canonical bytes yield `b9aa571b62e7fbc8b03bc83bd95914ec97a517ff50cd71cc71985362ef816262`; SET stores that cause/key with null resolver/clear fields. Cause mutation changes the derived key or rejects the partition; resolver data never enters the key. A non-`SYN-DOI-` executable case identity is rejected before vector execution. |
| SYN-STATE-013 | Active link-review SET has cause A; CLEAR it with distinct valid resolver B under TR-093 | CLEAR matches A's exact key/SET, preserves A cause and B resolution provenance, and removes only that cause. Replay rebuilds the identical result; B does not change the cause key. |
| SYN-STATE-014 | Replay the exact same valid CLEAR bytes/natural identity | Existing CLEAR is returned; event count, active set, stream projection, and prior bytes remain unchanged. |
| SYN-STATE-015 | Submit CLEAR with wrong cause key, SET ID, condition/case, or resolver-derived key | RC-081; append count zero; active and unrelated causes remain. |
| SYN-STATE-016 | Table-drive each missing/null resolver member, unresolved hash/revision, null resolution timestamp, and illegal reason/null pairing; explicitly require null revision for immutable `EXTRACTION_ATTEMPT`/`EVALUATION` and canonical decimal stream sequence for every `*_EVENT` source | The exact non-stream/event revision partitions validate only on their named rows. Every wrong-null/non-null revision or other closed-schema mismatch is RC-081; append/projection counts remain unchanged. |
| SYN-STATE-017 | Reuse an accepted CLEAR natural identity with different resolver ID/hash/revision/timestamp/reason; separately inject a proven digest collision | Ordinary conflict is RC-081; proven same-digest/different-bytes additionally invokes RC-103. Accepted event/projection remain; replay preserves original cause and accepted resolver. |

### 10.5 Resulting links and intervention histories

| Test ID | Fixture/action | Exact oracle |
|---|---|---|
| SYN-LINK-HIST-001 | Table-drive system/human exact-link creation while the separate search stream is absent, NOT_FOUND, or AMBIGUOUS; inject failure at each bundle write | TR-054/055 atomically creates one exact link from exact-link NONEXISTENT plus logical key/evidence/event, TR-110 revision 1, projection, cause clear, and KPI recomputation. A prior search record remains immutable. Every injected failure leaves all bundle counts/projections unchanged; search and exact-link states never share fields or stream IDs. |
| SYN-LINK-HIST-002 | Initial complete search finds none | TR-088 creates NOT_FOUND; no child inference/value. |
| SYN-LINK-HIST-003 | Initial evidence has multiple children | TR-089 creates AMBIGUOUS and TR-092 review; disputed value zero. |
| SYN-LINK-HIST-004 | Replay identical link evidence | Existing event/link returned; append and credit counts unchanged. |
| SYN-LINK-HIST-005 | Distinct corroborating evidence agrees | TR-090 appends evidence; link identity/state and credit scope remain one. |
| SYN-LINK-HIST-006 | System proof later agrees with human link | TR-091 projects AUTO_LINKED; both events retained. |
| SYN-LINK-HIST-007 | Table-drive the same base parent/type/child link with accepted M1 then contradictory M2 from AUTO_LINKED/HUMAN_CONFIRMED; inject failure at each conflict-bundle write | M1/M2 have distinct mapping-assertion keys. TR-058/059 atomically commits M2 key/evidence/event, TR-111 revision, AMBIGUOUS projection, TR-092 cause, and zero disputed KPI with RC-104 + RC-072 and no RC-102. Every injected failure rolls the whole bundle back; on success both keys survive, M1 is unchanged, and no second base link exists. |
| SYN-LINK-HIST-008 | Initial NOT_FOUND, later AMBIGUOUS candidates that set one cause-keyed review, then complete search disproves all; separately replay identical evidence | Legal history projects NOT_FOUND -> AMBIGUOUS -> NOT_FOUND without child/value inference; the final TR-088 invokes TR-093 with SEARCH_NOT_FOUND/RC-073 and clears only that search ambiguity cause. Identical replay appends nothing; an exact verified link and unrelated causes are unchanged by mere non-rediscovery. |
| SYN-INT-HIST-001 | Same action proven twice with identical payload | One action event/intervention; no duplicate credit. |
| SYN-INT-HIST-002 | Same natural evidence key with conflicting action payload | Fail closed; no second intervention/credit; prior projection retained. |
| SYN-INT-HIST-003 | Human exact value then system exact correction | Both events retained; system chain controls current original value. |
| SYN-INT-HIST-004 | Verified reversal, exact reversal correction, then exact reversal void; replay each correction/void | `REVERSAL_VERIFIED`, `REVERSAL_CORRECTED`, and `REVERSAL_VOIDED` use distinct closed logical kinds and predecessor-bound natural keys. TR-052 invokes TR-109 after correction/void; every event remains, active reversal/status/net and the original action-day KPI recompute exactly, including direct transition to VERIFIED at zero. Exact replay changes no event, contribution, or bucket. |
| SYN-INT-HIST-005 | With active reversals, table-drive (a) a valid authoritative original-value correction whose new original remains >= active reversal sum and (b) a correction below that sum | (a) TR-053 succeeds, invokes TR-108, and recomputes the projection/KPI in the original action-day bucket; (b) rejects the disputed correction and retains the last valid projection/KPI. No correction-date bucket is created. |

### 10.6 Purge and OA safety

| Test ID | Fixture/action | Exact oracle |
|---|---|---|
| SYN-PURGE-EDGE-001 | Table-drive a purge-eligible `CLOSED_HARD` case and a not-reopened purge-eligible `CLOSED_REVERSIBLE` case, each populated with every new entity/event/hash | TR-018 and TR-019 each invoke TR-112 and commit their exact from/to edge once; all Section 9 case graph rows, fingerprints, links, caches, and log/export traces are absent. Any injected finalization/deletion failure rolls the matching edge back completely. |
| SYN-PURGE-EDGE-002 | Case-linked observation expiry later than case purge | Observation and context link delete at case purge. |
| SYN-PURGE-EDGE-003 | Fully de-linked product relationship/revisions | Product-only records survive; scan proves no case/order/context/source-row/reconstructable marker. |
| SYN-PURGE-EDGE-004 | Request correction/link/context after purge | Transient CASE_IDENTITY_NOT_RETAINED; no durable rejection, identity lookup, or aggregate change. |
| SYN-OA-RO-PROV-001 | Exercise every new context/fact/link/revision/verification transition | OA mutation attempts and outbound writes are exactly zero; only DOI-local event appends occur. |
| SYN-OA-RO-PROV-002 | Inject an event payload that looks like an OA command | It remains inert data or is schema-rejected; no navigation/mutation plan changes. |

## 11. Cross-document integration requirements

The technical specification MUST carry Sections 1–5 and 9 as governing prose. The machine contract MUST carry every exact schema, hash rule, projection rule, and uniqueness constraint. The reason registry carries RC-105–RC-112 plus transaction-local RC-114 under its later source-retention owner; the transition matrix carries TR-082–TR-097 plus TR-114 and applies every amendment in Section 8. The acceptance matrix and synthetic requirements MUST add every Section 10 oracle and the exact 22-test source-import-retention family. The implementation handoff MUST require typed event stores, deterministic reducers, binding validation before evaluation commit, full purge-edge tests, and a build/static proof that the new flows expose no OA write capability.

The final traceability/delta report MUST map independent-audit Blockers 2 and 3 and dry-run Sections C, D, and F to these exact schemas/transitions/tests. Final reason, transition, and synthetic counts are derived only after merging all remediation drafts and validating uniqueness; the former counts 88, 82, and 127 are not targets.
