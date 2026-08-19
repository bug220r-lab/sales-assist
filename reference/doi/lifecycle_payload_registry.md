
> **Sanitized supporting reference.** This file is a mechanically sanitized derivative of
> source material supplied for the synthetic proof of concept. Historical status/freeze
> language is nonbinding. The curated files under `specs/` govern. No production-system
> access or real-data use is authorized by this reference.

# Synthetic Sales Assist DOI v0.1.5 — Lifecycle Event Payload Registry

Registry version: 0.1.5  
Lifecycle schema version: `doi-order-lifecycle-event/v2`  
Status: v0.1.5 Round-4 remediation-candidate governing registry; package-wide reconciliation and independent re-audit still required  
Scope: specification only; no live Synthetic Order Portal access, OA mutation, production implementation, workbook change, or historical-corpus mutation is authorized

## 1. Authority, scope, and closed-union rule

This artifact closes the serialization and replay contract for every case-linked lifecycle effect represented by the legal transition registry. It replaces every phrase equivalent to “event-specific allowlisted fields” for `DOIOrderLifecycleEvent`.

`DOIOrderLifecycleEvent` has two closed retention classes under the same v2 envelope. Every kind except `ALTERNATE_OBSERVATION_STORED` and `ACTION_CONTEXT_OBSERVATION_LINKED` belongs to the append-only `CASE_CORE` projection ledger and deletes only with the case. Those two volatile immutable-record wrappers belong to separate one-event `VOLATILE_ALTERNATE` streams owned by their exact target records; they never enter the core predecessor chain or change the case projection, and they delete atomically with their target at the target's earlier governed deadline. A typed fact stream remains the authority for contact, DEDUPE, attention, Action Context, product relationship, resulting-link, intervention-action, value, or reversal facts. When one of those accepted typed facts changes a retained case projection, the same ACID transaction appends a thin core `DOIOrderLifecycleEvent` variant that references the typed fact by exact schema, ID, and full-event hash; the lifecycle payload never copies the typed fact body. A wrapper and its authority either both commit or neither commits.

The following are deliberately not `DOIOrderLifecycleEvent` records:

- run and source-import events before a case exists;
- the run-local rejected/no-case record and its retention event;
- product-only relationship maintenance that has no retained case binding;
- exact-replay idempotent no-ops;
- deletion successes whose governing rule requires the identifying graph to be absent;
- a post-purge request for an identity that is no longer retained.

Those routes are nevertheless closed and reconciled to all 115 final transition rows in section 9. A deletion or post-purge rejection MUST NOT be converted into a surviving lifecycle receipt, hash, tombstone, or lookup key merely to make it look event-shaped.

For a selected `event_kind`, the named payload schema is exhaustive:

1. every key listed by that payload schema is present in canonical JSON;
2. every nullable key is serialized as explicit `null` when its selected row requires null;
3. every key not listed by that payload schema is absent and forbidden;
4. optional or extension keys do not exist;
5. unknown event kinds, payload types, schema versions, enum values, missing keys, extra keys, wrong null partitions, or hash aliases fail with `RC-113 LIFECYCLE_EVENT_SCHEMA_INVALID` before append;
6. stream identity/sequence/predecessor faults use `RC-111`; a proven same-digest/different-canonical-bytes condition additionally uses `RC-103`; an unlisted state edge uses `RC-081`.

## 2. Exact common envelope

Every persisted `DOIOrderLifecycleEvent` is exactly this object. The field names below are the canonical serialized names; legacy aliases such as `schema_version`, `event_type`, `payload_sha256`, or `event_envelope_sha256` are forbidden inside this record.

```text
DOIOrderLifecycleEventV2 {
  event_schema_version: "doi-order-lifecycle-event/v2",
  lifecycle_event_id: OpaqueId,
  case_id: OpaqueId,
  stream_id: Sha256,
  stream_sequence: integer >= 1,
  previous_event_id: OpaqueId | null,
  previous_event_content_sha256: Sha256 | null,
  event_kind: LifecycleEventKindV2,
  logical_occurrence_id: OpaqueId,
  event_natural_key_sha256: Sha256,
  occurred_at: Timestamp,
  recorded_at: Timestamp,
  actor_kind: SYSTEM | HUMAN,
  actor_id: OpaqueId | null,
  provenance: SYSTEM_VERIFIED | HUMAN_VERIFIED,
  prior_case_revision: integer >= 1 | null,
  result_case_revision: integer >= 1,
  prior_projection_hash: Sha256 | null,
  result_projection_hash: Sha256,
  source_bindings: canonical ordered nonempty set<LifecycleSourceBindingV1>,
  reason_codes: canonical ordered set<ReasonCodeId>,
  payload: LifecyclePayloadV2,
  payload_content_sha256: Sha256,
  content_sha256: Sha256
}
```

`lifecycle_event_id` is globally unique. `stream_id` is not caller-selected. For every `CASE_CORE` kind it is exactly:

```text
SHA256(UTF8(RFC8785({
  "event_stream_identity_version":"doi-event-stream-id-v1",
  "stream_namespace":"CASE_LIFECYCLE",
  "owner_identity":case_id
})))
```

For `ALTERNATE_OBSERVATION_STORED` or `ACTION_CONTEXT_OBSERVATION_LINKED`, `stream_id` is instead exactly:

```text
SHA256(UTF8(RFC8785({
  "event_stream_identity_version":"doi-event-stream-id-v1",
  "stream_namespace":"CASE_VOLATILE_ALTERNATE_LIFECYCLE",
  "owner_identity":{
    "case_id":case_id,
    "record_type":payload.record_type,
    "record_id":payload.record_id
  }
})))
```

Core sequence 1 is `CASE_CREATED`, has `prior_case_revision=null`, `prior_projection_hash=null`, and both predecessor fields null. It has `result_case_revision=1`. Every later core event has `result_case_revision=prior_case_revision+1`, `stream_sequence=result_case_revision`, names the exact prior core event ID/full-event hash, and has `prior_projection_hash` equal to that prior event's `result_projection_hash`. A case cannot have two accepted core events with one sequence or revision.

Each `VOLATILE_ALTERNATE` stream contains exactly one event at `stream_sequence=1`; both predecessor fields are null. At the atomic record/wrapper append boundary, `prior_case_revision=result_case_revision` equals the locked current core case revision and `prior_projection_hash=result_projection_hash` equals the locked current core projection hash. The wrapper changes no case/domain projection byte. A second event in that stream, a core predecessor reference, or a changed locked revision/hash is RC-111/113 and appends nothing. This separate-stream partition is derived solely from the two event-kind literals; no serialized extension flag exists.

Actor/provenance is an exact pair: `SYSTEM` requires `actor_id=null` and `SYSTEM_VERIFIED`; `HUMAN` requires a nonempty internal actor ID and `HUMAN_VERIFIED`. It never stores a customer identity. The selected payload fixes the pair exhaustively:

| Selected payload/event | Exact lifecycle actor/provenance derivation |
|---|---|
| `CASE_CREATED`; every `SourceHandlingPayloadV2`; `OPPORTUNITY_CREATED`; `ALTERNATE_OBSERVATION_STORED`; `ACTION_CONTEXT_OBSERVATION_LINKED`; `CASE_CLOSED_HARD`; `CASE_REOPENED`; every `PurgeDeadlinePayloadV2` | exactly `SYSTEM`, null actor ID, `SYSTEM_VERIFIED` |
| `CASE_CLOSED_REVERSIBLE/REP_TRANSFERRED` or `/DEDUPE_CONFIRMED` | exactly `SYSTEM`, null actor ID, `SYSTEM_VERIFIED`, equal to the accepted system proof |
| `CASE_CLOSED_REVERSIBLE/HUMAN_OUT_OF_SCOPE` | exactly `HUMAN`, the same nonempty internal actor ID, and `HUMAN_VERIFIED` as the bound accepted HumanFact |
| any `TypedEventReferencePayloadV2` | byte-equal to the referenced typed event actor pair |
| `ATTENTION_SET` or `ATTENTION_CLEARED` | byte-equal to the referenced accepted `DOIAttentionEventV2` actor pair; the separate cause/resolver groups do not replace it |

No other actor/provenance pair is legal. In particular, a system-derived immutable record cannot become HUMAN merely because a human initiated the read-only command that caused its observation.

`reason_codes` is a duplicate-free set serialized as an array in ascending Unicode code-point order of the exact registered `RC-NNN` strings. A copied typed-event/evaluation reason set must already use that same order and be byte-equal; an implementation never preserves caller insertion order. Duplicate, unknown, differently ordered, missing, or extra codes are RC-113 before hashing/append.

Envelope times are equally closed:

| Selected payload/event | Exact `occurred_at` |
|---|---|
| `CASE_CREATED` or `SOURCE_PRESENT` | the bound case-source admission proof's immutable `admitted_at` |
| `SOURCE_ABSENT` | the bound disappearance-verification attempt's terminal fact instant |
| `EXTRACTION_FAILED` | the bound extraction attempt's failure/terminal instant |
| `SNAPSHOT_ACCEPTED` | the bound complete snapshot's immutable capture instant |
| `EVALUATION_ACCEPTED` | the bound evaluation's `evaluated_at` |
| any typed-event wrapper or attention wrapper | byte-equal to the referenced typed event's `occurred_at` |
| `OPPORTUNITY_CREATED` | the immutable opportunity's creation instant |
| `ALTERNATE_OBSERVATION_STORED` | the observation's `observed_at` |
| `ACTION_CONTEXT_OBSERVATION_LINKED` | the link record's immutable creation/link instant |
| either case-closure kind | payload `verified_closure_at` |
| `CASE_REOPENED` | the bound reopen proof's governing accepted fact/evaluation occurrence instant |
| any purge-deadline event | the referenced closure/reopen lifecycle event's `occurred_at` |

`recorded_at` is assigned once by the persistence boundary after every target/stream/hash validation; it is not caller-selected and is never used as a source-fact substitute. A multi-event ACID bundle receives one `bundle_recorded_at` and every lifecycle event in that bundle serializes that identical instant. The natural-key locks are resolved before allocation. Exact replay or a concurrent duplicate returns the originally stored `lifecycle_event_id` and `recorded_at`; neither timestamp nor any prior byte is reallocated or changed.

### 2.1 Deterministic source/provenance binding

```text
LifecycleSourceBindingV1 {
  binding_role: LifecycleBindingRoleV1,
  entity_type: LifecycleBindingEntityTypeV1,
  entity_id: OpaqueId,
  entity_schema_version: VersionId,
  entity_content_sha256: Sha256
}
```

`LifecycleBindingRoleV1` is exactly:

```text
CASE_CREATION_SOURCE | SOURCE_BATCH | EXTRACTION_RESULT | SNAPSHOT_INPUT |
EVALUATION_INPUT | DOMAIN_EVENT | DOMAIN_RECORD | CLOSURE_PROOF |
REOPEN_PROOF | RETENTION_POLICY | RESOLUTION_SOURCE | CAUSE_EVENT |
KPI_EFFECT | MAPPING_REVISION
```

`LifecycleBindingEntityTypeV1` is exactly:

```text
CASE_SOURCE_ADMISSION_PROOF | SOURCE_BATCH | EXTRACTION_ATTEMPT | SNAPSHOT | EVALUATION |
OPPORTUNITY | ALTERNATE_RELATIONSHIP_REVISION | ALTERNATE_OBSERVATION |
ACTION_CONTEXT_EVENT | ACTION_CONTEXT_OBSERVATION_LINK | HUMAN_FACT_EVENT |
CONTACT_EVENT | DEDUPE_EVENT | ATTENTION_EVENT | WWC_EVENT |
INTERVENTION_ACTION_EVENT | INTERVENTION_VALUE_EVENT |
RESULT_LINK_SEARCH_EVENT | RESULT_LINK_EVENT | RESULT_LINK_MAPPING_REVISION |
ORDER_LIFECYCLE_EVENT | RETENTION_POLICY_RECORD | BUSINESS_CALENDAR_RECORD |
KPI_PROJECTION
```

Bindings are sorted by each complete member's RFC-8785 bytes and duplicate members are rejected. Every retained binding resolves to the same retained case or to explicitly de-linked product-only knowledge used by that case, and the stored schema/version and full-record digest match the immutable target bytes. A volatile wrapper is deleted in the same transaction as its target, so no retained missing-target exception exists. Raw OA pages, DOM, cookies, screenshots, exported files, free text, customer data, or a mutable projection pointer are not legal bindings.

#### 2.1.1 Closed source-binding constructor

`source_bindings` is generated only by this section. Every selected event produces exactly the members named below and zero others; an implementation may not infer, omit, duplicate, or add a binding. For each member, `entity_id` is the exact referenced immutable target ID, `entity_schema_version` is the literal below, and `entity_content_sha256` is the exact governing immutable digest named below. A full-event/full-record hash is used where the target defines one. Where a record deliberately defines a semantic immutable hash that excludes its generated ID, the binding's separate `entity_id` plus that digest is the complete identity-and-content binding; no implementation may substitute a different full/semantic digest. A missing target, ID/schema/hash mismatch, or different member count is RC-113; target and volatile wrapper share one deletion transaction, so replay never accepts a dangling binding.

| Binding entity type | Literal target schema | Exact `entity_content_sha256` source |
|---|---|---|
| `CASE_SOURCE_ADMISSION_PROOF` | `doi-case-source-admission-proof/v1` | `DOICaseSourceAdmissionProofV1.content_sha256` |
| `SOURCE_BATCH` | `doi-source-batch/v1` | `DOISourceBatch.record_content_sha256` |
| `EXTRACTION_ATTEMPT` | `doi-extraction-attempt/v1` | terminal `DOIExtractionAttempt.record_content_sha256` |
| `SNAPSHOT` | `doi-order-snapshot/v1` | `DOIOrderSnapshot.snapshot_content_sha256` |
| `EVALUATION` | `doi-evaluation-record/v1` | `DOIEvaluation.content_sha256` |
| `OPPORTUNITY` | `doi-opportunity-record/v1` | `DOIOpportunity.record_content_sha256` |
| `ALTERNATE_RELATIONSHIP_REVISION` | `doi-alternate-relationship-revision-event/v1` | revision envelope `content_sha256` |
| `ALTERNATE_OBSERVATION` | `doi-alternate-observation/v1` | `observation_content_sha256`; paired with `alternate_observation_id` |
| `ACTION_CONTEXT_EVENT` | `doi-action-context-event/v1` | event envelope `content_sha256` |
| `ACTION_CONTEXT_OBSERVATION_LINK` | `doi-action-context-observation-link/v1` | link `content_sha256` |
| `HUMAN_FACT_EVENT` | `doi-human-fact-event/v1` | event envelope `content_sha256` |
| `CONTACT_EVENT` | `doi-contact-state-event/v1` | event envelope `content_sha256` |
| `DEDUPE_EVENT` | `doi-dedupe-state-event/v1` | event envelope `content_sha256` |
| `ATTENTION_EVENT` | `doi-attention-event/v2` | event envelope `content_sha256` |
| `WWC_EVENT` | `doi-wwc-projection-event/v1` | event envelope `content_sha256` |
| `INTERVENTION_ACTION_EVENT` | `doi-intervention-action-event/v1` | event envelope `content_sha256` |
| `INTERVENTION_VALUE_EVENT` | `doi-intervention-value-event/v1` | event envelope `content_sha256` |
| `RESULT_LINK_SEARCH_EVENT` | `doi-result-link-search-event/v1` | event envelope `content_sha256` |
| `RESULT_LINK_EVENT` | `doi-result-link-exact-event/v1` | event envelope `content_sha256` |
| `RESULT_LINK_MAPPING_REVISION` | `doi-result-link-mapping-revision-event/v1` | revision envelope `content_sha256` |
| `ORDER_LIFECYCLE_EVENT` | `doi-order-lifecycle-event/v2` | lifecycle event `content_sha256` |
| `RETENTION_POLICY_RECORD` | `doi-retention-policy-binding/v1` | exact constructed policy digest below |
| `BUSINESS_CALENDAR_RECORD` | governing bound calendar version | exact bound `business_calendar_content_sha256` |
| `KPI_PROJECTION` | `doi-kpi-daily-v1` | retained contribution `authoritative_ledger_hash` |

The exact per-payload constructors are:

| Selected payload/event | Exact `source_bindings` members |
|---|---|
| `CASE_CREATED` | one `CASE_CREATION_SOURCE/CASE_SOURCE_ADMISSION_PROOF`, whose ID equals `logical_occurrence_id`; no standalone batch member |
| `SOURCE_PRESENT` | one `CASE_CREATION_SOURCE/CASE_SOURCE_ADMISSION_PROOF` whose ID equals `logical_occurrence_id`, plus one `SOURCE_BATCH/SOURCE_BATCH` whose ID equals non-null `payload.source_batch_id` |
| `SOURCE_ABSENT` | one `SOURCE_BATCH/SOURCE_BATCH` for non-null `payload.source_batch_id`, plus one `EXTRACTION_RESULT/EXTRACTION_ATTEMPT` whose ID equals `payload.disappearance_verification_attempt_id` |
| `EXTRACTION_FAILED` | one `EXTRACTION_RESULT/EXTRACTION_ATTEMPT` whose ID equals `payload.extraction_attempt_id`; add exactly one `SOURCE_BATCH/SOURCE_BATCH` iff `payload.source_batch_id` is non-null |
| `SNAPSHOT_ACCEPTED` | one `EXTRACTION_RESULT/EXTRACTION_ATTEMPT` for `payload.extraction_attempt_id`, one `SNAPSHOT_INPUT/SNAPSHOT` for `payload.snapshot_id`, and exactly one `SOURCE_BATCH/SOURCE_BATCH` iff `payload.source_batch_id` is non-null |
| `EVALUATION_ACCEPTED` | one `EXTRACTION_RESULT/EXTRACTION_ATTEMPT` for `payload.extraction_attempt_id`, one `SNAPSHOT_INPUT/SNAPSHOT` for `payload.snapshot_id`, one `EVALUATION_INPUT/EVALUATION` for `payload.evaluation_id`, and exactly one `SOURCE_BATCH/SOURCE_BATCH` iff `payload.source_batch_id` is non-null |
| `CASE_CLOSED_REVERSIBLE` or `CASE_CLOSED_HARD` | exactly one `CLOSURE_PROOF` member; payload `SNAPSHOT`, `DEDUPE_EVENT`, or `HUMAN_FACT_EVENT` maps to the identically named binding entity type and ID/hash |
| `CASE_REOPENED` | exactly four members: one `REOPEN_PROOF` for the payload's snapshot/evaluation/DEDUPE proof; one `CAUSE_EVENT/ORDER_LIFECYCLE_EVENT` for `prior_closure_retention_binding.prior_closure_event_id/content_sha256`; one `CLOSURE_PROOF` for the binding's exact prior closure source; and one `RETENTION_POLICY/RETENTION_POLICY_RECORD` constructed from the binding |
| `PURGE_SCHEDULED` or `PURGE_RESTARTED` | one `CAUSE_EVENT/ORDER_LIFECYCLE_EVENT` for `payload.source_event_id/content_sha256`, plus one `RETENTION_POLICY/RETENTION_POLICY_RECORD` constructed below |
| `PURGE_CANCELED` | exactly five members: one `CAUSE_EVENT/ORDER_LIFECYCLE_EVENT` for the byte-identical `source_event`/`cancellation_cause_event` reopen event; one `RESOLUTION_SOURCE` for the copied reopen proof; one `CAUSE_EVENT/ORDER_LIFECYCLE_EVENT` for the binding's prior closure event; one `CLOSURE_PROOF` for the binding's prior closure source; and one `RETENTION_POLICY/RETENTION_POLICY_RECORD` constructed from the binding |
| any `TypedEventReferencePayloadV2` kind | exactly one member from the typed-schema mapping below |
| any `ImmutableRecordReferencePayloadV2` kind | exactly one `DOMAIN_RECORD` member: `OPPORTUNITY`, `ALTERNATE_OBSERVATION`, or `ACTION_CONTEXT_OBSERVATION_LINK` according to `record_type` |
| `ATTENTION_SET` | one `DOMAIN_EVENT/ATTENTION_EVENT` for the accepted typed attention event plus one `CAUSE_EVENT` member from the attention-source mapping below |
| `ATTENTION_CLEARED` | one `DOMAIN_EVENT/ATTENTION_EVENT` for the accepted CLEAR, one `CAUSE_EVENT` member for the original cause, one `CAUSE_EVENT/ATTENTION_EVENT` for `clears_attention_event_id`, and one `RESOLUTION_SOURCE` member from the attention-source mapping below |

For `SOURCE_PRESENT`, `work_origin` is exactly `MANAGER_TARGET_REP_ROW`; other origins use their accepted extraction/snapshot/evaluation event and never serialize a non-manager `SOURCE_PRESENT` variant. `SOURCE_ABSENT` always binds the coherent selected batch and the exact absence-verification attempt. Conditional batch membership elsewhere is determined solely by the explicit null/non-null `source_batch_id` partition, so two valid binding arrays cannot exist for one payload.

The source-batch value is derived from retained records, never read from a nonexistent convenience field. `DOIRunOrderWorkItem.source_batch_id` is the sole run-work-item batch binding: for `MANAGER_TARGET_REP_ROW` it equals the retained case-source admission proof's batch and the work item stores that proof ID, not a staged record/attempt/source-row locator; for `SOURCE_ABSENCE_VERIFICATION` it equals the coherent selected manager batch; and for a manual/re-evaluation origin it is explicit null unless that origin explicitly reuses the retained snapshot's producing work item. Its `origin`, `source_batch_id`, and nullable `case_source_admission_proof_id` are immutable and FK-guarded until the work graph is deleted. A retained work item MUST NOT contain `source_import_attempt_id`, staged-order ID, TARGET_REP SourceRef, spreadsheet/tab identity, or attempt actor/token/ordinal. Define `derived_source_batch_id(extraction_attempt)` as the exact `source_batch_id` on the attempt's retained `DOIRunOrderWorkItem`; define `derived_source_batch_id(snapshot)` as the value derived from its referenced extraction attempt; and define `derived_source_batch_id(evaluation)` as the value derived from its exact bound snapshot. Every retained FK in that chain must resolve and agree before event bytes are allocated. The lifecycle payload copies that derived value, including explicit null; a missing link, mutated binding, or disagreement is RC-113. For `SOURCE_ABSENT`, `disappearance_verification_attempt_id` resolves the exact retained `DOIExtractionAttempt`; its work item MUST have `origin=SOURCE_ABSENCE_VERIFICATION`, and `source_absence_run_id` MUST equal that work item's `run_id`. The same work item supplies the identical non-null `source_batch_id`. No caller-selected run alias is legal.

Typed-event reference mapping is exact:

| Typed schema | Binding role/type | Exact `domain_owner_type` | Exact owner-ID source in the referenced typed event |
|---|---|---|---|
| `doi-contact-state-event/v1` | `DOMAIN_EVENT/CONTACT_EVENT` | `CONTACT` | `action_context_id` |
| `doi-wwc-projection-event/v1` | `DOMAIN_EVENT/WWC_EVENT` | `WWC` | `case_id` |
| `doi-dedupe-state-event/v1` | `DOMAIN_EVENT/DEDUPE_EVENT` | `DEDUPE` | `case_id` |
| `doi-alternate-relationship-revision-event/v1` | `DOMAIN_EVENT/ALTERNATE_RELATIONSHIP_REVISION` | `RELATIONSHIP` | `alternate_relationship_id` |
| `doi-action-context-event/v1` | `DOMAIN_EVENT/ACTION_CONTEXT_EVENT` | `ACTION_CONTEXT` | `action_context_id` |
| `doi-human-fact-event/v1` | `DOMAIN_EVENT/HUMAN_FACT_EVENT` | `HUMAN_FACT` | `case_id` |
| `doi-intervention-action-event/v1` | `DOMAIN_EVENT/INTERVENTION_ACTION_EVENT` | `INTERVENTION_ACTION` | `intervention_id` |
| `doi-intervention-value-event/v1` | `DOMAIN_EVENT/INTERVENTION_VALUE_EVENT` | `INTERVENTION_VALUE` | `intervention_id` |
| `doi-result-link-search-event/v1` | `DOMAIN_EVENT/RESULT_LINK_SEARCH_EVENT` | `RESULT_LINK_SEARCH` | `resulting_order_link_search_id` |
| `doi-result-link-exact-event/v1` | `DOMAIN_EVENT/RESULT_LINK_EVENT` | `RESULT_LINK_EXACT` | `resulting_order_link_id` |
| `doi-result-link-mapping-revision-event/v1` | `MAPPING_REVISION/RESULT_LINK_MAPPING_REVISION` | `RESULT_LINK_MAPPING` | `resulting_order_link_id` |

The selected typed schema fixes all four columns as one closed row. `domain_owner_id` MUST equal the exact owner-ID field named in that row; no caller-selected owner, alternate subject alias, or cross-row owner type is legal. The source-binding member ID/hash and every wrapper identity/state field are validated against the same referenced typed event before append. Any row, owner, or binding mismatch is `RC-113` with zero lifecycle append.

Attention-source mapping is exact. `EXTRACTION_ATTEMPT`, `EVALUATION`, `WWC_PROJECTION_EVENT`, `RESULTING_ORDER_LINK_SEARCH_EVENT`, `RESULTING_ORDER_LINK_EXACT_EVENT`, `INTERVENTION_ACTION_EVENT`, and `HUMAN_FACT_EVENT` map respectively to `EXTRACTION_ATTEMPT`, `EVALUATION`, `WWC_EVENT`, `RESULT_LINK_SEARCH_EVENT`, `RESULT_LINK_EVENT`, `INTERVENTION_ACTION_EVENT`, and `HUMAN_FACT_EVENT` with the literal schemas above. The binding ID/hash equals the copied cause or resolution ID/hash; the source revision token is validated by the typed attention contract but is not a second binding field. `EXTRACTION_ATTEMPT` and `EVALUATION` are immutable non-stream records and therefore require a null revision token; every `*_EVENT` source requires its canonical decimal stream sequence. On CLEAR, the active SET member is always `CAUSE_EVENT/ATTENTION_EVENT` with ID `clears_attention_event_id` and the referenced SET's full digest.

For `CASE_REOPENED` and every purge-deadline wrapper, the retention-policy member is deterministic. For reopen and cancellation, the six policy values are copied from `prior_closure_retention_binding`; for assignment/restart they are the six top-level deadline fields. Map `prior_retention_policy_id`, `prior_retention_policy_version`, `prior_retention_timezone`, `prior_tzdb_version`, and `prior_local_calendar_rule_id` to the corresponding target fields below without renaming any serialized binding field. The member's `entity_id` is `doi-retention-calendar90-ny/v1@` followed by the exact selected tzdb version; its closed canonical target is `{"local_calendar_arithmetic_rule_identifier":"calendar90-america-new-york/v1","retention_policy_binding_schema_version":"doi-retention-policy-binding/v1","retention_policy_identifier":"DOI_CASE_GRAPH","retention_policy_version":"doi-retention-calendar90-ny/v1","timezone":"America/New_York","timezone_database_version":selected_timezone_database_version}` and its digest is `SHA256(UTF8("doi-retention-policy-binding/v1\n") || UTF8(RFC8785(target)))`. The member is therefore reproducible from the locked authoritative tuple and cannot point at a mutable policy alias.

### 2.2 Natural key, payload hash, and full-event hash

The event natural-key object is exactly:

```text
{
  "event_natural_key_schema_version":"doi-order-lifecycle-event-natural-key/v2",
  "case_id":case_id,
  "event_kind":event_kind,
  "logical_occurrence_id":logical_occurrence_id
}
```

```text
event_natural_key_sha256 = SHA256(
  UTF8("doi-order-lifecycle-event-natural-key/v2\n") ||
  UTF8(RFC8785(event_natural_key_object))
)

payload_content_sha256 = SHA256(
  UTF8("doi-order-lifecycle-payload/v2/" || event_kind || "\n") ||
  UTF8(RFC8785(payload))
)

content_sha256 = SHA256(
  UTF8("doi-order-lifecycle-event/v2\n") ||
  UTF8(RFC8785(event_without_content_sha256))
)
```

Enforce `UNIQUE(case_id,event_natural_key_sha256)` with retained natural-key canonical bytes, `UNIQUE(lifecycle_event_id)`, and `UNIQUE(stream_id,stream_sequence)`. Exact natural key plus byte-identical complete event is an idempotent reuse and appends nothing. The same natural key with different canonical semantic bytes is RC-113 unless a more specific typed-domain conflict applies; stale stream/predecessor/revision is RC-111; same digest with different canonical bytes is RC-103. Replays never allocate a new event ID or recorded time.

## 3. Exact case-projection hash contract

The lifecycle stream replays to one exact projection object:

```text
DOIOrderCaseProjectionV2 {
  case_projection_schema_version: "doi-order-case-projection/v2",
  case_id: OpaqueId,
  case_revision: integer >= 1,
  lifecycle_state: ACTIVE | CLOSED_REVERSIBLE | CLOSED_HARD,
  closure_kind: NONE | SHIPPED | CANCELED | REP_TRANSFERRED |
                DEDUPE_CONFIRMED | HUMAN_OUT_OF_SCOPE,
  closure_class: NONE | REVERSIBLE | HARD,
  verified_closure_at: Timestamp | null,
  retention_policy_identifier: "DOI_CASE_GRAPH" | null,
  retention_policy_version: "doi-retention-calendar90-ny/v1" | null,
  timezone: "America/New_York" | null,
  timezone_database_version: VersionId | null,
  local_calendar_arithmetic_rule_identifier:
      "calendar90-america-new-york/v1" | null,
  purge_eligible_at: Timestamp | null,
  current_snapshot_binding: ProjectionRecordBindingV1 | null,
  current_evaluation_binding: ProjectionRecordBindingV1 | null,
  domain_projection_bindings: canonical ordered set<DomainProjectionBindingV1>
}

ProjectionRecordBindingV1 {
  entity_id: OpaqueId,
  entity_schema_version: VersionId,
  entity_content_sha256: Sha256
}

DomainProjectionBindingV1 {
  projection_namespace: ATTENTION | CONTACT | DEDUPE | WWC | ACTION_CONTEXT |
                        OPPORTUNITY_INDEX | INTERVENTION | INTERVENTION_VALUE |
                        RESULT_LINK_SEARCH | RESULT_LINK_EXACT |
                        RESULT_LINK_MAPPING | KPI_RETAINED,
  projection_owner_id: OpaqueId,
  projection_revision: integer >= 1,
  projection_content_sha256: Sha256
}
```

The record and domain-binding objects are closed. Sets are sorted by complete-member RFC-8785 bytes; duplicates by `(projection_namespace,projection_owner_id)` are invalid. A domain binding is not an implementation-selected projection checksum: it is constructed only by the following exhaustive table.

| `projection_namespace` | Exact owner | Exact revision | Exact `projection_content_sha256` | Create/update/remove reducer |
|---|---|---|---|---|
| `ATTENTION` | `attention_cause_key_sha256` | accepted SET `DOIAttentionEventV2.stream_sequence` | accepted SET event envelope `content_sha256` | SET inserts this cause binding; CLEAR must match the active SET and removes exactly that binding. The CLEAR event remains in lifecycle history but is not an active-cause binding. |
| `CONTACT` | `DOIContactStateEvent.action_context_id` | referenced event `stream_sequence` | referenced event envelope `content_sha256` | Insert on first contact projection and replace only the same-owner binding on each later accepted contact event. |
| `DEDUPE` | `DOIDedupeStateEvent.case_id` | referenced event `stream_sequence` | referenced event envelope `content_sha256` | Insert/replace the sole case-owned DEDUPE binding. |
| `WWC` | `DOIWWCProjectionEvent.case_id` | referenced event `stream_sequence` | referenced event envelope `content_sha256` | Insert/replace the sole case-owned WWC binding; the evaluation ID unique rule remains authoritative. |
| `ACTION_CONTEXT` | `DOIActionContextEvent.action_context_id` | referenced event `stream_sequence` | referenced event envelope `content_sha256` | Insert on OPEN and replace only that context's binding on completion/abandonment/supersession. |
| `OPPORTUNITY_INDEX` | `DOIOpportunity.opportunity_id` | literal `1` | `DOIOpportunity.record_content_sha256` | Insert once for `OPPORTUNITY_CREATED`; exact replay changes nothing. It is never updated and deletes only with the case graph. |
| `INTERVENTION` | `DOIInterventionActionVerificationEvent.intervention_id` | referenced event `stream_sequence` | referenced event envelope `content_sha256` | Insert only on the first accepted action event. A later compatible proof may append a verification-evidence record only; it creates no second action event/lifecycle wrapper and leaves this binding byte-identical. |
| `INTERVENTION_VALUE` | `DOIInterventionValueEvent.intervention_id` | referenced event `stream_sequence` | referenced event envelope `content_sha256` | Insert/replace with the last accepted value/reversal/correction/void event after its deterministic reducer succeeds. |
| `RESULT_LINK_SEARCH` | non-null `DOIResultingOrderLinkEvent.resulting_order_link_search_id` | referenced event `stream_sequence` | referenced event envelope `content_sha256` | Insert/replace only the stable search owner; an exact-link event cannot update this namespace. |
| `RESULT_LINK_EXACT` | non-null `DOIResultingOrderLinkEvent.resulting_order_link_id` | referenced event `stream_sequence` | referenced event envelope `content_sha256` | Insert/replace only the stable exact-link owner; a search event cannot update this namespace. |
| `RESULT_LINK_MAPPING` | `DOIResultingOrderLinkRevision.resulting_order_link_id` | exact `revision_number=stream_sequence` | mapping-revision envelope `content_sha256` | Insert at verified revision 1 and replace on each accepted conflict/resolution revision. |
| `KPI_RETAINED` | `DOIRetainedKPIContribution.retained_kpi_contribution_id` | retained contribution `projection_revision` | retained contribution `authoritative_ledger_hash` | Insert/replace after an action/value/reversal wrapper carrying its exact TR-106..109 atomic effect. For TR-054..059, the one base exact-link wrapper whose `transition_ids` contains that owner row also applies the mandated current/zero split-credit recomputation; its mapping and attention companion wrappers never duplicate the KPI update. If the exact branch has no retained contribution, the binding is absent; case purge removes it with the row. |

`RELATIONSHIP` and `HUMAN_FACT` are deliberately not projection namespaces. A case-linked relationship or HumanFact core wrapper increments `case_revision` and preserves its exact immutable source binding but adds no domain binding; the next accepted evaluation binds any rules-relevant relationship revision or HumanFact in `current_evaluation_binding`. `ALTERNATE_OBSERVATION_STORED` and `ACTION_CONTEXT_OBSERVATION_LINKED` are instead the two one-event `VOLATILE_ALTERNATE` streams: they retain the exact record binding while the target exists, do not enter the core chain, and leave the locked case projection/revision/hash byte-identical. No namespace outside the twelve rows above is legal.

For `SNAPSHOT_ACCEPTED`, `current_snapshot_binding` becomes exactly `{snapshot_id,"doi-order-snapshot/v1",snapshot_content_sha256}` from the validated payload/binding. For `EVALUATION_ACCEPTED`, `current_snapshot_binding` must already equal the payload snapshot and `current_evaluation_binding` becomes exactly `{evaluation_id,"doi-evaluation-record/v1",evaluation_content_sha256}`. Other core event kinds leave those two record bindings byte-identical. Closure/reopen/deadline events modify only the exact lifecycle/closure/retention members specified by their payloads. Every `CASE_CORE` event increments `case_revision` once even when no domain binding changes. The two volatile wrappers increment no case revision and reproduce the locked current projection hash unchanged.

Before hashing, the reducer copies the prior projection, applies exactly the selected row(s) above plus the selected lifecycle payload's closed case fields, sorts the resulting domain set, and rejects any unexplained insertion, replacement, removal, revision jump, owner change, or digest mismatch with RC-113. A typed event can update at most its one event-backed namespace. An action/value/reversal wrapper with an exact TR-106..109 atomic effect may additionally update `KPI_RETAINED`; the base exact-link wrapper under TR-054..059 is the sole other allowed KPI updater and uses that owning row's mandated link recomputation. Mapping and attention companion wrappers leave the already-computed KPI binding byte-identical. Attention SET/CLEAR and immutable opportunity creation otherwise follow their dedicated rows. The projection digest is:

```text
result_projection_hash = SHA256(
  UTF8("doi-order-case-projection/v2\n") ||
  UTF8(RFC8785(result_projection_object))
)
```

When `lifecycle_state=ACTIVE`, every closure/retention member is exactly `NONE` or null. A closure has the exact non-`NONE` kind/class and all six closure/retention values non-null. Reopen clears every closure/retention member to `NONE`/null. Replaying accepted `CASE_CORE` events in `stream_sequence` order MUST reproduce every intermediate `result_projection_hash` and the final projection. Independently replaying either retained one-event volatile stream MUST reproduce its unchanged locked core projection hash. Wall-clock order is never the reducer order.

## 4. Closed payload schemas

Every payload listed below is a closed object. `transition_ids` and `atomic_effect_transition_ids` are duplicate-free arrays sorted by numeric transition order with `TR-045A` immediately after `TR-045`. They are derived only by the following constructor; they are not caller-selected authorization.

### 4.0 Exact transition-array constructor

Before any event bytes are allocated, the transition engine produces the exact `committed_transition_set` whose guards and effects all validate in the one ACID transaction under the state matrix. For each lifecycle event occurrence, `transition_ids` is exactly the sorted subset of that committed set whose section-9 route names that same occurrence with `L:`, `T+L:`, or `R+L:`. Conditional route text contributes an ID only when its stated condition is true and that event actually commits. If the same physical occurrence is named by more than one committed row, all and only those row IDs are included. Examples: the DEDUPE-note event in the closure bundle has `[TR-012,TR-063]`; its separate closure and deadline events each have `[TR-012]`; a mapping-revision-1 wrapper in system link creation has `[TR-054,TR-110]`; its base-link wrapper has `[TR-054]`. A conditional initial-link search-review CLEAR has `[TR-054,TR-093]` or `[TR-055,TR-093]`; an exact-link conflict-resolution CLEAR has `[TR-056,TR-093]` or `[TR-057,TR-093]`; an exact-link conflict SET has `[TR-058,TR-092]` or `[TR-059,TR-092]`; a search refinement CLEAR has `[TR-088,TR-093]`; and a search ambiguity SET has `[TR-089,TR-092]`. Parent and subordinate IDs are never silently dropped from a shared physical occurrence.

`EVALUATION_ACCEPTED` has one additional closed rule because the top-level DOI reducer is a projection route: after applying the base constructor it MUST additionally contain exactly one committed result row from `TR-029..TR-039`, selected by the accepted evaluation output. It cannot contain two result rows or none. No other `P:` row enters `transition_ids`.

Only `TypedEventReferencePayloadV2` and `ImmutableRecordReferencePayloadV2` contain `atomic_effect_transition_ids`. For every immutable-record wrapper the value is exactly `[]`. For typed wrappers it is exactly:

| Typed lifecycle kind | Exact `atomic_effect_transition_ids` |
|---|---|
| `INTERVENTION_ACTION_SYSTEM_VERIFIED` or `INTERVENTION_ACTION_HUMAN_VERIFIED` | `[TR-106]` |
| `ORIGINAL_VALUE_VERIFIED` | `[TR-107]` |
| `ORIGINAL_VALUE_CORRECTED` | `[TR-108]` |
| `REVERSAL_VERIFIED`, `REVERSAL_CORRECTED`, or `REVERSAL_VOIDED` | `[TR-109]` |
| every other typed lifecycle kind | `[]` |

These four KPI rows are projection-only `P:` effects with no separate lifecycle wrapper. Mapping, attention, closure, context, opportunity, and other typed/record effects have their own lifecycle occurrences and therefore appear only through those occurrences' exact `transition_ids`, not again in `atomic_effect_transition_ids`. A missing, extra, duplicated, reordered, wrong-but-registered, or uncommitted transition ID in either array is RC-113 and appends nothing. `SYN-LIFE-PAYLOAD-004/005` MUST table-drive every legal constructor branch and mutate each array with a wrong registered ID, not only an unknown ID.

### 4.0.1 Exact multi-row bundle order

One ACID business transaction may commit lifecycle occurrences named by more than one transition row. Before sequence numbers, predecessors, recorded times, or hashes are allocated, construct one node per distinct lifecycle natural identity; references to the same physical occurrence from parent/subordinate rows collapse to that one node and contribute their IDs through section 4.0. Construct a dependency edge `A -> B` exactly when any of the following holds:

1. `A` and `B` are distinct nodes and `B.source_bindings` references either lifecycle occurrence `A` itself or the single external primary authority occurrence owned by `A` under the closed table below; no other record merely present in `A.source_bindings` qualifies, and a wrapper's binding to its own authority is validation evidence, never a lifecycle-node dependency or self-edge;
2. `B`'s closed guard or reducer consumes the case/domain projection produced by `A`;
3. the same section-9 row names `A` to the left of `B`;
4. the governing atomic-bundle clause explicitly requires `A` before `B` (fact before linked DEDUPE event/evaluation, link evidence before mapping, mapping before attention, closure/reopen before its deadline event).

The external primary-authority owner used by rule 1 is exact and unique within a bundle:

| Lifecycle node `A` | Sole external primary authority occurrence owned by `A` |
|---|---|
| any `TypedEventReferencePayloadV2` wrapper | its one referenced typed event |
| any `ImmutableRecordReferencePayloadV2` wrapper | its one referenced immutable record |
| `ATTENTION_SET` or `ATTENTION_CLEARED` | its accepted typed `DOIAttentionEventV2` |
| `SNAPSHOT_ACCEPTED` | its accepted immutable snapshot |
| `EVALUATION_ACCEPTED` | its accepted immutable evaluation |
| `SOURCE_ABSENT` or `EXTRACTION_FAILED` | its accepted immutable extraction attempt |
| every other lifecycle kind, including `CASE_CREATED`, `SOURCE_PRESENT`, closure, reopen, and purge-deadline kinds | none; its source bindings are proof/validation inputs, and ordering is determined only by rules 2–4 |

Every lifecycle node additionally owns its own lifecycle occurrence for a later `ORDER_LIFECYCLE_EVENT` binding. An external target has at most one primary-authority owner in the committed lifecycle bundle. Thus a closure that binds the same snapshot as `SNAPSHOT_ACCEPTED` depends on the snapshot wrapper, but it cannot create a reciprocal closure-to-snapshot edge merely because the closure also contains that proof binding. A duplicate owner, ambiguous owner, or edge derived from a non-primary proof binding is RC-113 and commits nothing.

When an accepted evaluation in the same transaction derives a closure or reopen, that evaluation is an explicit predecessor of the derived lifecycle event even when the event directly binds a snapshot or typed fact. Thus an evaluation-derived route is `SNAPSHOT_ACCEPTED -> EVALUATION_ACCEPTED -> CASE_CLOSED_* -> PURGE_SCHEDULED/RESTARTED`. A direct accepted proof route does not invent an evaluation: in particular TR-013 is `HUMAN_FACT_RECORDED -> CASE_CLOSED_REVERSIBLE(HUMAN_OUT_OF_SCOPE) -> PURGE_SCHEDULED`, and analogous direct source/typed proofs follow their section-9 route. Each TR-014 branch uses the exact proof map/order in section 4.7. No closure can sort before an evaluation that actually governs it.

Perform a stable topological sort. Among simultaneously ready nodes, select the node with the lowest owning transition ordinal (`TR-045A` immediately follows `TR-045`), then the lowest left-to-right route position within that row, then the UTF-8 lexical `event_kind`, then the UTF-8 lexical event-natural-key canonical bytes. This is the only legal tie-break. A cycle, missing dependency, or alternate ordering is RC-113 and commits nothing. After validation and locking, allocate one persistence `bundle_recorded_at` and serialize it identically on every lifecycle node. Assign consecutive sequence/result revisions, predecessors, and intermediate hashes only to the sorted `CASE_CORE` nodes. Each volatile observation/link wrapper is independently sequence 1 in its record-owned stream, has null predecessors, copies the one locked core revision/hash on both sides, and cannot affect the order or hashes of core nodes. Thus input collection, map order, thread scheduling, equivalent transaction-plan order, and per-node clock sampling cannot change canonical bytes.

Examples are normative: a structured HumanFact precedes any evaluation that binds it; an evaluation precedes its opportunity records and every closure/reopen actually derived from it; a direct HumanFact closure does not invent an evaluation; a DEDUPE decision fact precedes its linked DEDUPE event; link evidence precedes the mapping revision and the mapping precedes its attention SET/CLEAR; a resolving evaluation precedes the resulting WWC projection and that projection precedes its attention CLEAR; closure/reopen precedes schedule/cancel/restart. `SYN-LIFE-PAYLOAD-011` MUST submit every representative bundle, including evaluation-derived closure, direct HumanFact closure, and all three TR-014 proof branches, in multiple caller/permutation orders and reproduce the same event order and every intermediate hash.

### 4.1 Case creation

```text
CaseCreationPayloadV2 {
  payload_type: "CASE_CREATION",
  transition_ids: ["TR-007"],
  initial_lifecycle_state: "ACTIVE",
  retained_predecessor_case_id: null,
  post_purge_identity_lookup_performed: false
}
```

`logical_occurrence_id` is the exact retained `case_source_admission_proof_id`. `source_bindings` is exactly one `CASE_CREATION_SOURCE/CASE_SOURCE_ADMISSION_PROOF` binding. That case-owned closed proof binds the exact Order Number/TARGET_REP selection, batch, and `DOICaseSourceBinding` without any run ID, source-import-attempt ID/ordinal/token, source-row reference, spreadsheet/tab identity, attempt actor, or attempt timestamp. TR-007 constructs the proof from the locked staged source and batch/case authorities before allocating this lifecycle event; the staged record remains attempt-owned and is never a lifecycle target. `reason_codes` is exactly the empty ordered set. A later same real-world number after case purge uses a new proof/case and performs no predecessor lookup.

### 4.2 Source handling, snapshot, and evaluation append

```text
SourceHandlingPayloadV2 {
  payload_type: "SOURCE_HANDLING",
  transition_ids: canonical nonempty set<TransitionId>,
  source_operation: SOURCE_PRESENT | SOURCE_ABSENT | EXTRACTION_FAILED |
                    SNAPSHOT_ACCEPTED | EVALUATION_ACCEPTED,
  work_origin: MANAGER_TARGET_REP_ROW | SOURCE_ABSENCE_VERIFICATION |
               MANUAL_RECHECK | DEDUPE_RECHECK |
               STRUCTURED_FACT_REEVALUATION |
               PRODUCT_KNOWLEDGE_REEVALUATION |
               RULES_VERSION_REEVALUATION,
  source_batch_id: OpaqueId | null,
  extraction_attempt_id: OpaqueId | null,
  snapshot_id: OpaqueId | null,
  snapshot_content_sha256: Sha256 | null,
  evaluation_id: OpaqueId | null,
  evaluation_content_sha256: Sha256 | null,
  source_absence_run_id: OpaqueId | null,
  disappearance_verification_attempt_id: OpaqueId | null,
  prior_lifecycle_state: ACTIVE | CLOSED_REVERSIBLE | CLOSED_HARD,
  result_lifecycle_state: ACTIVE | CLOSED_REVERSIBLE | CLOSED_HARD
}
```

| `event_kind` | Required non-null fields | Fields exactly null | Guard and logical occurrence |
|---|---|---|---|
| `SOURCE_PRESENT` | `source_batch_id`; `work_origin=MANAGER_TARGET_REP_ROW` | extraction/snapshot/evaluation/absence fields | Retained case appears in exact coherent personal manager work; case-source admission-proof ID is the occurrence. Non-manager rechecks use their extraction/snapshot/evaluation variants, never `SOURCE_PRESENT`. |
| `SOURCE_ABSENT` | `source_absence_run_id`, `disappearance_verification_attempt_id`, `source_batch_id`; `work_origin=SOURCE_ABSENCE_VERIFICATION` | extraction/snapshot/evaluation | Case is active and absent from the selected coherent manager batch; verification-attempt ID is the occurrence. It never closes. |
| `EXTRACTION_FAILED` | `extraction_attempt_id`; source batch fixed by the record rule below | snapshot/evaluation and absence fields | Attempt is terminal failed/incomplete; extraction-attempt ID is the occurrence. No snapshot/evaluation binding is permitted. |
| `SNAPSHOT_ACCEPTED` | `extraction_attempt_id`, `snapshot_id`, `snapshot_content_sha256`; source batch fixed by the record rule below | evaluation and absence fields | Complete successful extraction; snapshot ID is the occurrence. |
| `EVALUATION_ACCEPTED` | `extraction_attempt_id`, snapshot pair, evaluation pair; source batch fixed by the record rule below | absence fields | Exact evaluation input/output/full hashes validate; evaluation ID is the occurrence. |

`source_operation` MUST equal the selected lifecycle `event_kind` byte-for-byte. The allowed origin and batch partition are exhaustive:

| `event_kind` | Allowed `work_origin` | Exact `source_batch_id` rule |
|---|---|---|
| `SOURCE_PRESENT` | `MANAGER_TARGET_REP_ROW` only | non-null and equal to the case-source admission proof's retained batch binding |
| `SOURCE_ABSENT` | `SOURCE_ABSENCE_VERIFICATION` only | non-null and equal to the coherent selected manager batch on the disappearance attempt's work item; `source_absence_run_id` equals that same work item's `run_id` |
| `EXTRACTION_FAILED` | `MANAGER_TARGET_REP_ROW`, `SOURCE_ABSENCE_VERIFICATION`, `MANUAL_RECHECK`, or `DEDUPE_RECHECK` | exactly `derived_source_batch_id(extraction_attempt)`, including explicit null; manager/source-absence origin requires non-null |
| `SNAPSHOT_ACCEPTED` | `MANAGER_TARGET_REP_ROW`, `SOURCE_ABSENCE_VERIFICATION`, `MANUAL_RECHECK`, or `DEDUPE_RECHECK` | exactly `derived_source_batch_id(snapshot)`, which must equal the value derived from the producing extraction attempt |
| `EVALUATION_ACCEPTED` | any of the seven closed `work_origin` values | exactly `derived_source_batch_id(evaluation)`, which must equal the value derived from the exact bound snapshot and its producing extraction attempt; structured-fact/product-knowledge/rules re-evaluation reuses that retained chain and cannot choose a new batch value |

Hash pairs are both non-null or both null. `prior_lifecycle_state=result_lifecycle_state` for these variants. `CLOSED_HARD` accepts none of them. `EVALUATION_ACCEPTED` binds the exact snapshot and evaluation; its `reason_codes` equals the referenced evaluation's ordered reason set byte-for-byte. `EXTRACTION_FAILED` has exactly RC-014 plus the proved subset of RC-011/012/013 and any owning attention code named by the atomic transition. Other source-handling wrappers use the exact reason set named by their transition row, otherwise empty. A disallowed event/origin pair, source-operation mismatch, or record-derived batch mismatch is RC-113 with zero append.

### 4.3 Thin typed-event reference

```text
TypedEventReferencePayloadV2 {
  payload_type: "TYPED_EVENT_REFERENCE",
  transition_ids: canonical nonempty set<TransitionId>,
  typed_event_id: OpaqueId,
  typed_event_schema_version: VersionId,
  typed_event_kind: closed type-specific event kind,
  typed_event_content_sha256: Sha256,
  domain_owner_type: ATTENTION | CONTACT | DEDUPE | WWC | RELATIONSHIP |
                     ACTION_CONTEXT | HUMAN_FACT | INTERVENTION_ACTION |
                     INTERVENTION_VALUE | RESULT_LINK_SEARCH |
                     RESULT_LINK_EXACT | RESULT_LINK_MAPPING,
  domain_owner_id: OpaqueId,
  prior_domain_state: closed domain state | NONEXISTENT | null,
  result_domain_state: closed domain state,
  atomic_effect_transition_ids: canonical set<TransitionId>
}
```

The lifecycle `event_kind` selects exactly one typed schema/kind row in section 5. `typed_event_kind` must equal that row's exact literal; the `DOMAIN_EVENT` or `MAPPING_REVISION` source binding must equal all four typed identity/version/hash values. The lifecycle actor, provenance, occurrence time, and reason set equal the typed event values byte-for-byte. `logical_occurrence_id=typed_event_id`. The selected schema also fixes `domain_owner_type` and `domain_owner_id` through section 2.1.1; the ID must equal the referenced typed event's registered stream owner/subject ID.

Prior/result states use only this exhaustive constructor:

| Typed schema | Exact wrapper prior/result source |
|---|---|
| `doi-contact-state-event/v1` | byte-equal `prior_contact_state` / `resulting_contact_state` |
| `doi-wwc-projection-event/v1` | byte-equal `prior_projection_state` / `resulting_projection_state` |
| `doi-dedupe-state-event/v1` | byte-equal `prior_dedupe_state` / `resulting_dedupe_state` |
| `doi-alternate-relationship-revision-event/v1` | `ALTERNATE_RELATIONSHIP_CREATED`: `NONEXISTENT -> ACTIVE`; `...REVISION_APPENDED`: `ACTIVE -> ACTIVE`; `...SUPERSEDED`: `ACTIVE -> SUPERSEDED`; `...INVALIDATED`: `ACTIVE -> INVALIDATED`; result MUST equal `relationship_state` and predecessor state/hash must prove the prior value |
| `doi-action-context-event/v1` | byte-equal `prior_state` / `resulting_state` |
| `doi-human-fact-event/v1` | `HUMAN_FACT_RECORDED`: `NONEXISTENT -> STORED`; `HUMAN_FACT_CORRECTED`: `STORED -> STORED`, with exact current predecessor fact |
| `doi-intervention-action-event/v1` | exactly `NONEXISTENT -> VERIFIED`; a later compatible corroborating proof is evidence-only and has no typed action/lifecycle event or state edge |
| `doi-intervention-value-event/v1` | exact authoritative value-state immediately before and after the accepted reducer: `UNVERIFIED`, `VERIFIED`, `PARTIALLY_REVERSED`, or `REVERSED`; the Money/predecessor ledger must reproduce both states |
| `doi-result-link-search-event/v1` | byte-equal non-null `prior_search_state` / `resulting_search_state`; link-state fields must be null |
| `doi-result-link-exact-event/v1` | byte-equal non-null `prior_link_state` / `resulting_link_state`; search-state fields must be null |
| `doi-result-link-mapping-revision-event/v1` | revision 1: `NONEXISTENT -> VERIFIED`; conflict revision: `VERIFIED -> CONFLICT_REVIEW`; resolution revision: `CONFLICT_REVIEW -> VERIFIED`; result MUST equal `mapping_state` and exact predecessor proves prior state |

No other state token, null, or independently selected legal edge is permitted. `prior_domain_state=null` is therefore never used by a typed wrapper in v0.1.5; `NONEXISTENT` is serialized only in the creation rows above. A typed event with explicit state fields must match them byte-for-byte; a derived row must reproduce from the exact current owner projection and predecessor event before append. `atomic_effect_transition_ids` lists only the exact subordinate effects fixed by the transition-array registry below and never creates an independent event for them.

### 4.4 Attention SET/CLEAR

```text
AttentionTransitionPayloadV2 {
  payload_type: "ATTENTION_TRANSITION",
  transition_ids: canonical nonempty set<TransitionId>,
  typed_attention_event_id: OpaqueId,
  typed_attention_event_schema_version: "doi-attention-event/v2",
  typed_attention_event_content_sha256: Sha256,
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
  resolution_reason_code: ReasonCodeId | null
}
```

Every field from `typed_attention_event_id` through `resolution_reason_code` is a byte-for-byte reference/copy of the accepted `DOIAttentionEventV2`; the lifecycle wrapper does not define or recompute a second attention semantic object. The lifecycle envelope `reason_codes` MUST also be byte-equal to the accepted typed attention event envelope's canonical ordered `reason_codes`, whose exact set is fixed by the owning transition row. A missing, extra, reordered, or different set is RC-113 with zero append. `logical_occurrence_id` is exactly `typed_attention_event_id` for SET and CLEAR; a caller-selected or resolver-derived occurrence ID is forbidden. The sole authoritative cause schema and domain are `doi-attention-cause-key/v2` and `doi-attention-cause-key/v2\n` from the integrated typed attention contract. The exact cause object contains `attention_cause_key_schema_version`, case, condition, and the four cause-provenance fields. No resolution field enters it.

For SET, the complete four-field cause group is non-null except `cause_source_entity_revision`, which is null exactly for non-stream `EXTRACTION_ATTEMPT` or `EVALUATION`; the four resolution fields, clear target, resolution time, and resolution reason are null. For CLEAR, the same complete cause group is copied byte-for-byte from the referenced active SET; `attention_cause_key_sha256` and `clears_attention_event_id` identify that SET; the complete independent resolution group and `resolution_occurred_at` are non-null, except its revision is null exactly for non-stream `EXTRACTION_ATTEMPT` or `EVALUATION`. The independent resolver may differ from the cause. `resolution_reason_code` follows the closed TR-093/TR-095 table and is null only for the exact no-dedicated-code branches. A CLEAR must match the exact active SET/cause key. Source bindings are exactly the typed v2 attention event, the original cause entity, the referenced SET on CLEAR, and the independent resolution entity on CLEAR.

### 4.5 Immutable record append/reference

```text
ImmutableRecordReferencePayloadV2 {
  payload_type: "IMMUTABLE_RECORD_REFERENCE",
  transition_ids: canonical nonempty set<TransitionId>,
  record_type: OPPORTUNITY | ALTERNATE_OBSERVATION |
               ACTION_CONTEXT_OBSERVATION_LINK,
  record_id: OpaqueId,
  record_schema_version: VersionId,
  record_content_sha256: Sha256,
  deterministic_identity_sha256: Sha256,
  prior_domain_state: NONEXISTENT,
  result_domain_state: STORED,
  atomic_effect_transition_ids: canonical set<TransitionId>
}
```

The `DOMAIN_RECORD` binding equals the record type/ID/version/governing immutable content hash. For opportunity, generic payload `record_schema_version` copies target `opportunity_schema_version="doi-opportunity-record/v1"` byte-for-byte, and `record_content_sha256=SHA256(UTF8("doi-opportunity-record/v1\n") || UTF8(RFC8785(opportunity_without_record_content_sha256)))`; the full object includes that target literal, generated opportunity ID, immutable creation time, and every governing opportunity field exactly once. Alternate observation uses its existing target literal `observation_schema_version="doi-alternate-observation/v1"` and `observation_content_sha256`. The Action-Context observation link uses its target `link_schema_version="doi-action-context-observation-link/v1"` and full `content_sha256`. The generic payload version field is always an alias of the selected target's exact schema field, never an additional record field.

`OPPORTUNITY_CREATED` is a `CASE_CORE` event and follows the core revision/projection reducer. `ALTERNATE_OBSERVATION_STORED` and `ACTION_CONTEXT_OBSERVATION_LINKED` are the exhaustive `VOLATILE_ALTERNATE` partition: each uses its target-owned stream ID formula, `stream_sequence=1`, null predecessors, and identical non-null prior/result core revision and projection hash from the locked case. They update no `DOIOrderCaseProjectionV2` field. Their record, wrapper, source binding, natural-key bytes, and indexes share one retention graph and delete atomically at the target's earlier governed deadline. Neither event can be referenced as a predecessor by a core event or another volatile event.

`deterministic_identity_sha256` and lifecycle envelope `logical_occurrence_id` MUST be byte-equal to the record's one deterministic pre-allocation identity fingerprint, never its generated ID. For opportunity both equal `SHA256(UTF8("doi-opportunity-lifecycle-natural/v1\n") || UTF8(RFC8785({"opportunity_lifecycle_natural_schema_version":"doi-opportunity-lifecycle-natural/v1","evaluation_id":evaluation_id,"scenario_option_id":scenario_option_id})))`. For alternate observation both equal `observation_content_sha256`. For the context link both equal `SHA256(UTF8("doi-action-context-observation-link-natural/v1\n") || UTF8(RFC8785({"action_context_observation_link_natural_schema_version":"doi-action-context-observation-link-natural/v1","action_context_id":action_context_id,"alternate_observation_id":alternate_observation_id,"relationship_revision_id":relationship_revision_id})))`. Exact identity plus exact bytes reuses the existing record and appends no second lifecycle event. A mismatch among the record-derived value, payload field, or envelope field is RC-113. Changed bytes under an existing identity fail under that record's specific conflict rule or RC-113; a proven digest collision uses RC-103. All three lifecycle wrappers carry the empty reason set; evaluation/domain reasons remain on their owning evaluation/typed event.

### 4.6 Closure

```text
CaseClosurePayloadV2 {
  payload_type: "CASE_CLOSURE",
  transition_ids: canonical nonempty set<TransitionId>,
  closure_kind: SHIPPED | CANCELED | REP_TRANSFERRED |
                DEDUPE_CONFIRMED | HUMAN_OUT_OF_SCOPE,
  closure_class: HARD | REVERSIBLE,
  prior_lifecycle_state: ACTIVE | CLOSED_REVERSIBLE,
  result_lifecycle_state: CLOSED_HARD | CLOSED_REVERSIBLE,
  verified_closure_at: Timestamp,
  retention_policy_identifier: "DOI_CASE_GRAPH",
  retention_policy_version: "doi-retention-calendar90-ny/v1",
  timezone: "America/New_York",
  timezone_database_version: VersionId,
  local_calendar_arithmetic_rule_identifier:
      "calendar90-america-new-york/v1",
  calculated_utc_purge_eligible_at: Timestamp,
  prior_purge_eligible_at: Timestamp | null,
  closure_source_entity_type: SNAPSHOT | DEDUPE_EVENT | HUMAN_FACT_EVENT,
  closure_source_entity_id: OpaqueId,
  closure_source_entity_content_sha256: Sha256
}
```

The closure event contains the verified closure instant and complete retention derivation even though a following deadline event repeats the resulting retention projection. This is deliberate hash-bound redundancy and the values must be byte-identical. `logical_occurrence_id` is exactly `closure_source_entity_id`; replay of the same accepted closure proof therefore resolves the same natural key and cannot allocate a second closure event.

Closure time and prior-state bytes are proof-derived, never caller-selected. For `SNAPSHOT`, `verified_closure_at` MUST equal the accepted current complete snapshot's immutable `captured_at`; for `DEDUPE_EVENT`, it MUST equal the accepted `DOIDedupeStateEvent.occurred_at`; for `HUMAN_FACT_EVENT`, it MUST equal the accepted `DOIHumanFactEvent.occurred_at`. The selected proof ID, schema version, full content hash, case ID, and closure discriminator MUST all agree. `prior_lifecycle_state`, `prior_purge_eligible_at`, and every preexisting closure/retention value consumed by the reducer MUST be byte-equal to the locked prior case projection named by the envelope. A changed timestamp, stale/non-current snapshot, mismatched proof, or caller-supplied prior value is RC-113 before deadline calculation or append.

| `event_kind` / closure | Guard and source | Required reason set | Prior deadline |
|---|---|---|---|
| `CASE_CLOSED_HARD` / `SHIPPED` | Complete snapshot; ACTIVE under TR-009 or reversible under TR-016 | `[RC-021]` | null from ACTIVE; non-null from reversible |
| `CASE_CLOSED_HARD` / `CANCELED` | Complete full-cancel snapshot; TR-010 or TR-017 | `[RC-022]` | null from ACTIVE; non-null from reversible |
| `CASE_CLOSED_REVERSIBLE` / `REP_TRANSFERRED` | Complete `SNAPSHOT` proving current rep outside workflow; TR-011. `closure_source_entity_type` is exactly `SNAPSHOT`. | `[RC-023]` | null |
| `CASE_CLOSED_REVERSIBLE` / `DEDUPE_CONFIRMED` | Exact accepted `OA_NOTE_SYSTEM_VERIFIED` event; `closure_source_entity_type` is exactly `DEDUPE_EVENT`; TR-012/063 | `[RC-024]` | null |
| `CASE_CLOSED_REVERSIBLE` / `HUMAN_OUT_OF_SCOPE` | Exact structured authorized human fact; `closure_source_entity_type` is exactly `HUMAN_FACT_EVENT`; TR-013 | `[RC-025]` | null |

Hard and reversible pairs are exhaustive. A hard closure cannot reopen. A repeated unchanged reversible closure uses source/evaluation events only and does not append another closure/deadline event.

### 4.7 Reopen and purge-deadline assignment/cancellation/restart

```text
PriorClosureRetentionBindingV1 {
  prior_closure_retention_binding_schema_version:
      "doi-prior-closure-retention-binding/v1",
  prior_closure_event_id: OpaqueId,
  prior_closure_event_content_sha256: Sha256,
  prior_closure_kind: SHIPPED | CANCELED | REP_TRANSFERRED |
                      DEDUPE_CONFIRMED | HUMAN_OUT_OF_SCOPE,
  prior_closure_classification: HARD | REVERSIBLE,
  prior_verified_closure_at: Timestamp,
  prior_retention_policy_id: "DOI_CASE_GRAPH",
  prior_retention_policy_version: "doi-retention-calendar90-ny/v1",
  prior_retention_timezone: "America/New_York",
  prior_tzdb_version: VersionId,
  prior_local_calendar_rule_id: "calendar90-america-new-york/v1",
  prior_purge_eligible_at: Timestamp,
  prior_closure_projection_revision: integer >= 1,
  prior_closure_projection_hash: Sha256,
  prior_closure_source_entity_type:
      SNAPSHOT | DEDUPE_EVENT | HUMAN_FACT_EVENT,
  prior_closure_source_entity_id: OpaqueId,
  prior_closure_source_entity_schema_version: VersionId,
  prior_closure_source_entity_content_sha256: Sha256
}

CaseReopenPayloadV2 {
  payload_type: "CASE_REOPEN",
  transition_ids: ["TR-014"],
  prior_closure_kind: REP_TRANSFERRED | DEDUPE_CONFIRMED | HUMAN_OUT_OF_SCOPE,
  prior_verified_closure_at: Timestamp,
  prior_purge_eligible_at: Timestamp,
  prior_closure_retention_binding: PriorClosureRetentionBindingV1,
  reopen_source_entity_type: SNAPSHOT | EVALUATION | DEDUPE_EVENT,
  reopen_source_entity_id: OpaqueId,
  reopen_source_entity_schema_version: VersionId,
  reopen_source_entity_content_sha256: Sha256,
  reopen_reason_code: "RC-078",
  reopen_at: Timestamp,
  result_lifecycle_state: "ACTIVE",
  result_closure_kind: "NONE",
  result_verified_closure_at: null,
  result_purge_eligible_at: null,
  purge_deadline_cancellation_effect: "CLEAR_ACTIVE_PURGE_DEADLINE",
  result_case_id: OpaqueId,
  same_case_identity_preserved: true,
  result_case_revision: integer >= 1,
  result_projection_hash: Sha256
}

PurgeDeadlinePayloadV2 {
  payload_type: "PURGE_DEADLINE",
  transition_ids: canonical nonempty set<TransitionId>,
  deadline_operation: ASSIGN | CANCEL | RESTART,
  closure_kind: SHIPPED | CANCELED | REP_TRANSFERRED |
                DEDUPE_CONFIRMED | HUMAN_OUT_OF_SCOPE | null,
  closure_class: HARD | REVERSIBLE | null,
  verified_closure_at: Timestamp | null,
  retention_policy_identifier: "DOI_CASE_GRAPH",
  retention_policy_version: "doi-retention-calendar90-ny/v1",
  timezone: "America/New_York",
  timezone_database_version: VersionId,
  local_calendar_arithmetic_rule_identifier:
      "calendar90-america-new-york/v1",
  calculated_utc_purge_eligible_at: Timestamp | null,
  prior_purge_eligible_at: Timestamp | null,
  source_event_id: OpaqueId,
  source_event_content_sha256: Sha256,
  prior_closure_retention_binding: PriorClosureRetentionBindingV1 | null,
  canceled_purge_eligible_at: Timestamp | null,
  cancellation_cause_event_id: OpaqueId | null,
  cancellation_cause_event_content_sha256: Sha256 | null,
  resolution_source_entity_type: SNAPSHOT | EVALUATION | DEDUPE_EVENT | null,
  resolution_source_entity_id: OpaqueId | null,
  resolution_source_entity_schema_version: VersionId | null,
  resolution_source_entity_content_sha256: Sha256 | null,
  result_purge_deadline_state: SCHEDULED | CANCELED,
  result_purge_eligible_at: Timestamp | null,
  result_case_id: OpaqueId,
  same_case_identity_preserved: true,
  result_case_revision: integer >= 1,
  result_projection_hash: Sha256
}
```

`PriorClosureRetentionBindingV1` is a closed, immutable value object, not an open map or a projection-hash alias. Every listed key is required and non-null; every unlisted key is absent and forbidden. Its canonical bytes are exactly `UTF8(RFC8785(complete_binding_object))`. Those exact nested bytes are covered by the selected lifecycle payload domain and therefore by `payload_content_sha256` and the full-event `content_sha256`; there is no second implementation-selected binding digest. Unknown binding versions, missing/extra keys, omitted null substitutes, noncanonical timestamps, uppercase/malformed hashes, or an enum outside this registry are RC-113 before append.

The kind/classification relation is closed: `SHIPPED` and `CANCELED` require `HARD`; `REP_TRANSFERRED`, `DEDUPE_CONFIRMED`, and `HUMAN_OUT_OF_SCOPE` require `REVERSIBLE`. The closure-source schema is likewise closed: `SNAPSHOT` requires `doi-order-snapshot/v1`, `DEDUPE_EVENT` requires `doi-dedupe-state-event/v1`, and `HUMAN_FACT_EVENT` requires `doi-human-fact-event/v1`. The source ID/hash MUST equal both the retained prior closure payload and its exact `CLOSURE_PROOF` source binding. All timestamps are timezone-aware canonical `Timestamp` values under section 2; the retention timezone is exactly `America/New_York`, and the policy, tzdb, and local-calendar values are the already-bound closed identifiers shown above.

Before either reopen event is allocated, lock the current case-core stream, its current projection, the referenced prior closure event, the closure event's proof target, and the retained policy record. Construct the authoritative binding from those records only. `prior_closure_event_id/content_sha256` MUST resolve to the last applicable retained `CASE_CLOSED_REVERSIBLE` event that has not been superseded by another closure/reopen; its kind, classification, verified instant, policy tuple, closure source, and active deadline MUST equal the locked closure-bearing state. `prior_closure_projection_revision/hash` are exactly the locked pre-reopen case revision and projection hash consumed by the `CASE_REOPENED` envelope, and `prior_purge_eligible_at` equals that projection's active deadline. Independently RFC-8785-serialize the authoritative object and require byte equality with `CaseReopenPayloadV2.prior_closure_retention_binding`. An implementation MUST NOT accept an omitted tuple, reconstruct fields from only a projection hash, or infer policy/source values from current configuration.

For `PURGE_CANCELED`, the complete nested binding is copied byte-for-byte from the just-accepted `CASE_REOPENED` payload in the same locked ACID bundle. Its `prior_closure_projection_revision/hash` therefore continue to identify the closure-bearing projection before reopen, not the immediately prior ACTIVE projection. The validator re-resolves the retained prior closure event/proof/policy and the referenced closure-bearing projection and repeats the complete byte comparison; it does not trust the nested copy merely because the reopen event hash resolves. Any missing target or any kind, classification, closure instant, policy ID/version, timezone, tzdb, calendar rule, deadline, projection revision/hash, closure-source identity/schema/hash, or canonical-byte mismatch is RC-113. The complete reopen/cancel bundle appends nothing, changes no projection/deadline, and leaves the prior closed projection byte-identical.

| `event_kind` | Exact partition and guard | Reason set | Logical occurrence |
|---|---|---|---|
| `CASE_REOPENED` | Every shown field is required. Only `result_verified_closure_at` and `result_purge_eligible_at` are null; all other fields are non-null. Binding classification is `REVERSIBLE`; its projection revision/hash equal envelope prior revision/hash. `prior_closure_kind`, `prior_verified_closure_at`, and `prior_purge_eligible_at` equal the nested binding. `reopen_at=occurred_at`; `reopen_reason_code` is the sole envelope reason. Result case ID equals envelope case ID, result revision/hash equal the envelope, and identity flag is true. Deadline/cancellation-source fields from `PurgeDeadlinePayloadV2` are absent and forbidden. | `[RC-078]` | exact reopen proof ID |
| `PURGE_SCHEDULED` | `ASSIGN`; closure/class/time/new deadline and result deadline non-null; prior deadline null; binding, canceled deadline, cancellation-cause group, and complete resolution-source group null; result deadline state `SCHEDULED` | `[RC-079]` | exact closure lifecycle-event ID |
| `PURGE_CANCELED` | `CANCEL`; closure/class/time/calculated new deadline null; binding, prior/canceled deadline, cancellation-cause group, and complete resolution-source group non-null; result deadline state `CANCELED`; result deadline null | `[RC-080]` | exact reopen lifecycle-event ID |
| `PURGE_RESTARTED` | `RESTART`; closure/class/time/calculated new, prior, and result deadlines non-null; binding, canceled deadline, cancellation-cause group, and resolution-source group null; result deadline state `SCHEDULED`; source is later hard-closure event | `[RC-079]` | exact later hard-closure lifecycle-event ID |

Every `PurgeDeadlinePayloadV2` key shown in the schema is required; the table fixes its only legal null partition and every unlisted key is absent/forbidden. `result_case_id`, `same_case_identity_preserved`, `result_case_revision`, and `result_projection_hash` are always non-null and equal the lifecycle envelope's case ID, literal `true`, result revision, and result hash. For `ASSIGN`/`RESTART`, `result_purge_eligible_at=calculated_utc_purge_eligible_at`. For `CANCEL`, `canceled_purge_eligible_at=prior_purge_eligible_at=prior_closure_retention_binding.prior_purge_eligible_at`, while `result_purge_eligible_at=null` proves the deadline is cleared.

The reopen proof type is exhaustive and is derived from the locked prior reversible closure:

| `prior_closure_kind` | Exact `reopen_source_entity_type` | Exact accepted proof and route guard |
|---|---|---|
| `REP_TRANSFERRED` | `SNAPSHOT` | the accepted current complete snapshot proves the order is again in TARGET_REP's governed scope; the same bundle's accepted evaluation proves DOI eligibility |
| `DEDUPE_CONFIRMED` | `DEDUPE_EVENT` | the accepted `DOIDedupeStateEvent/ELIGIBILITY_RETURNED`, whose exact evaluation binding proves current eligibility |
| `HUMAN_OUT_OF_SCOPE` | `EVALUATION` | the accepted new evaluation binds the current legal snapshot/human-fact set and proves DOI eligibility |

No cross-row proof type is legal. The duplicated prior kind/time/deadline fields MUST be byte-equal to the nested binding and locked prior case projection. The reopen proof ID/schema/full hash/case binding and `reopen_at`/lifecycle `occurred_at` MUST be byte-equal to the selected row's accepted source. `result_case_id` equals the same retained case ID; no new episode/case/predecessor identity is allocated. The bundle serializes any accepted source-fact wrapper first, then `EVALUATION_ACCEPTED`, then `DEDUPE_ELIGIBILITY_RETURNED` only for the DEDUPE branch, then `CASE_REOPENED`, then `PURGE_CANCELED`. This ordering makes every proof exist before the event that binds it and leaves no evaluator-selected ordering.

`PURGE_CANCELED.source_event_id/content_sha256` and `cancellation_cause_event_id/content_sha256` are byte-identical aliases of the exact accepted `CASE_REOPENED` event; both are required so generic deadline replay and cancellation-cause validation are independently closed. The complete resolution-source group is copied from that reopen payload and resolves to the same retained source as the `RESOLUTION_SOURCE` binding. The top-level retention policy/timezone/tzdb/calendar/deadline values equal the nested prior binding. Its exact source-binding set additionally resolves the prior closure event, prior closure proof, and bound policy; a hash-only cause reference is insufficient. Any disagreement fails the entire bundle before either append. `PURGE_RESTARTED` recalculates from the new verified hard-closure instant and never from the earlier reversible deadline. All deadline timestamps are exact UTC outputs of the bound `America/New_York` local-calendar algorithm. Fixed elapsed hours are illegal.

### 4.8 Transient post-purge rejection (not a lifecycle event)

```text
DOITransientPostPurgeRejectionV1 {
  rejection_schema_version: "doi-transient-post-purge-rejection/v1",
  request_occurrence_id: OpaqueId,
  requested_subject_type: CASE | INTERVENTION | RESULT_LINK | ACTION_CONTEXT,
  requested_subject_id: OpaqueId,
  result_code: "CASE_IDENTITY_NOT_RETAINED",
  persisted: false,
  aggregate_mutated: false,
  identity_reconstruction_performed: false
}
```

This object exists only in request memory long enough to return the rejection. It has no hash, database row, event ID, source binding, log payload, metric label, receipt, or retry key and is erased after the response. It is therefore excluded from `LifecycleEventKindV2`.

## 5. Complete discriminated event-kind registry

The following 56 literals are the entire `LifecycleEventKindV2` union. Any other string is RC-113.

### 5.1 Case/source/retention and attention kinds

The source-binding column below is a human-readable summary only. Section 2.1.1 is the sole executable constructor and fixes every role, entity type, schema, target, conditional, and cardinality; any array that differs from it is RC-113.

| `event_kind` | Payload schema | Exact source-binding requirement | State guard / effect |
|---|---|---|---|
| `CASE_CREATED` | `CaseCreationPayloadV2` | exactly one `CASE_CREATION_SOURCE/CASE_SOURCE_ADMISSION_PROOF` binding; no attempt-owned staged target or second batch alias is serialized | NONEXISTENT to ACTIVE; sequence/revision 1 only |
| `SOURCE_PRESENT` | `SourceHandlingPayloadV2` | case-owned admission proof and batch when manager-origin | retained non-hard case; no closure change |
| `SOURCE_ABSENT` | `SourceHandlingPayloadV2` | coherent batch/run + absence verification attempt | ACTIVE only; no closure |
| `EXTRACTION_FAILED` | `SourceHandlingPayloadV2` | failed extraction attempt | retained non-hard case; no snapshot/evaluation |
| `SNAPSHOT_ACCEPTED` | `SourceHandlingPayloadV2` | extraction attempt + complete snapshot | retained non-hard case; update current snapshot |
| `EVALUATION_ACCEPTED` | `SourceHandlingPayloadV2` | snapshot + exact evaluation | retained non-hard case; update current evaluation/domain projections |
| `ATTENTION_SET` | `AttentionTransitionPayloadV2` | typed attention event + inline cause | add exactly one cause key |
| `ATTENTION_CLEARED` | `AttentionTransitionPayloadV2` | typed attention event + prior SET + independent resolver | remove exactly one active cause key |
| `CASE_CLOSED_REVERSIBLE` | `CaseClosurePayloadV2` | exact closure proof | ACTIVE to reversible |
| `CASE_CLOSED_HARD` | `CaseClosurePayloadV2` | complete snapshot proof | ACTIVE/reversible to hard |
| `CASE_REOPENED` | `CaseReopenPayloadV2` | reopen proof + explicit prior closure event/proof/policy and byte-equal full prior tuple | reversible to same-case ACTIVE; clear closure/deadline |
| `PURGE_SCHEDULED` | `PurgeDeadlinePayloadV2` | closure lifecycle event + retention policy | assign first deadline |
| `PURGE_CANCELED` | `PurgeDeadlinePayloadV2` | reopen cause + resolution proof + explicit prior closure event/proof/policy and byte-identical full prior tuple | cancel exact prior deadline before purge; same-case revision |
| `PURGE_RESTARTED` | `PurgeDeadlinePayloadV2` | later hard-closure lifecycle event + prior deadline | replace reversible deadline |

### 5.2 Typed-event-reference kinds

Every row uses `TypedEventReferencePayloadV2`; the event-kind literal fixes the exact typed schema and `typed_event_kind`. A typed event/body mismatch is RC-113. Reason codes, actor, provenance, occurred time, and type-specific null partitions are validated first against the named typed schema, then required to equal the wrapper. The last column describes other routes that must commit in the same transaction; it does not override section 4.0's narrower exact `atomic_effect_transition_ids` field.

| Lifecycle `event_kind` | Exact typed schema / typed kind | Exact prior to result guard | Required same-transaction routes |
|---|---|---|---|
| `CONTACT_REQUIRED_DERIVED` | `doi-contact-state-event/v1` / `CONTACT_REQUIRED_DERIVED` | NOT_CONTACTED to CONTACT_REQUIRED | none |
| `CONTACT_ATTEMPT_RECORDED` | `doi-contact-state-event/v1` / `CONTACT_ATTEMPT_RECORDED` | CONTACT_REQUIRED, NOT_CONTACTED, CONTACT_ATTEMPTED, AWAITING_CUSTOMER, CUSTOMER_DECLINED, or NO_RESPONSE to CONTACT_ATTEMPTED, exactly as TR-066/067/080 | none |
| `AWAITING_CUSTOMER_RECORDED` | `doi-contact-state-event/v1` / `AWAITING_CUSTOMER_RECORDED` | CONTACT_ATTEMPTED to AWAITING_CUSTOMER | none |
| `CUSTOMER_APPROVAL_RECORDED` | `doi-contact-state-event/v1` / `CUSTOMER_APPROVAL_RECORDED` | AWAITING_CUSTOMER or CONTACT_ATTEMPTED to CUSTOMER_APPROVED | none |
| `CUSTOMER_DECLINE_RECORDED` | `doi-contact-state-event/v1` / `CUSTOMER_DECLINE_RECORDED` | AWAITING_CUSTOMER, CONTACT_ATTEMPTED, or CUSTOMER_APPROVED to CUSTOMER_DECLINED | none |
| `NO_RESPONSE_RECORDED` | `doi-contact-state-event/v1` / `NO_RESPONSE_RECORDED` | AWAITING_CUSTOMER to NO_RESPONSE | none |
| `WWC_PROJECTION_APPENDED` | `doi-wwc-projection-event/v1` / `WWC_PROJECTION_APPENDED` | any/nonexistent to exact seven-state WWC partition | TR-094/095 only when applicable |
| `DEDUPE_CANDIDATE_DERIVED` | `doi-dedupe-state-event/v1` / `CANDIDATE_DERIVED` | NOT_CANDIDATE or HUMAN_REJECTED to CANDIDATE | none |
| `DEDUPE_CANDIDATE_WITHDRAWN` | `doi-dedupe-state-event/v1` / `CANDIDATE_WITHDRAWN` | candidate/approved/rejected to NOT_CANDIDATE | none |
| `DEDUPE_HUMAN_APPROVED` | `doi-dedupe-state-event/v1` / `HUMAN_APPROVED` | CANDIDATE to HUMAN_APPROVED_AWAITING_OA_VERIFICATION | same-transaction `HUMAN_FACT_RECORDED` |
| `DEDUPE_HUMAN_REJECTED` | `doi-dedupe-state-event/v1` / `HUMAN_REJECTED` | CANDIDATE or approved-awaiting to HUMAN_REJECTED | same-transaction `HUMAN_FACT_RECORDED` or legal corrected fact |
| `DEDUPE_OA_NOTE_SYSTEM_VERIFIED` | `doi-dedupe-state-event/v1` / `OA_NOTE_SYSTEM_VERIFIED` | approved-awaiting to CONFIRMED | TR-012 closure + schedule |
| `DEDUPE_ELIGIBILITY_RETURNED` | `doi-dedupe-state-event/v1` / `ELIGIBILITY_RETURNED` | CONFIRMED to NOT_CANDIDATE | TR-014 reopen + cancel |
| `ALTERNATE_RELATIONSHIP_CREATED` | `doi-alternate-relationship-revision-event/v1` / `ALTERNATE_RELATIONSHIP_CREATED` | NONEXISTENT to ACTIVE revision 1 | none |
| `ALTERNATE_RELATIONSHIP_REVISION_APPENDED` | `doi-alternate-relationship-revision-event/v1` / `ALTERNATE_RELATIONSHIP_REVISION_APPENDED` | ACTIVE n to ACTIVE n+1 | none |
| `ALTERNATE_RELATIONSHIP_SUPERSEDED` | `doi-alternate-relationship-revision-event/v1` / `ALTERNATE_RELATIONSHIP_SUPERSEDED` | ACTIVE n to SUPERSEDED n+1 | none |
| `ALTERNATE_RELATIONSHIP_INVALIDATED` | `doi-alternate-relationship-revision-event/v1` / `ALTERNATE_RELATIONSHIP_INVALIDATED` | ACTIVE n to INVALIDATED n+1 | none |
| `ACTION_CONTEXT_OPENED` | `doi-action-context-event/v1` / `ACTION_CONTEXT_OPENED` | NONEXISTENT to OPEN | none |
| `ACTION_CONTEXT_COMPLETED` | `doi-action-context-event/v1` / `ACTION_CONTEXT_COMPLETED` | OPEN to CLOSED_COMPLETED under one closed trigger pair | none |
| `ACTION_CONTEXT_ABANDONED` | `doi-action-context-event/v1` / `ACTION_CONTEXT_ABANDONED` | OPEN to CLOSED_ABANDONED | none |
| `ACTION_CONTEXT_SUPERSEDED` | `doi-action-context-event/v1` / `ACTION_CONTEXT_SUPERSEDED` | OPEN to CLOSED_SUPERSEDED | none |
| `HUMAN_FACT_RECORDED` | `doi-human-fact-event/v1` / `HUMAN_FACT_RECORDED` | no accepted occurrence to accepted immutable fact | TR-028 only when rules-relevant; TR-061/062 when DEDUPE fact |
| `HUMAN_FACT_CORRECTED` | `doi-human-fact-event/v1` / `HUMAN_FACT_CORRECTED` | current fact to predecessor-bound correction | TR-028 only when rules-relevant; corrected DEDUPE decision only if separately legal |
| `INTERVENTION_ACTION_SYSTEM_VERIFIED` | `doi-intervention-action-event/v1` / `INTERVENTION_ACTION_SYSTEM_VERIFIED` | NONEXISTENT to VERIFIED | TR-106 |
| `INTERVENTION_ACTION_HUMAN_VERIFIED` | `doi-intervention-action-event/v1` / `INTERVENTION_ACTION_HUMAN_VERIFIED` | NONEXISTENT to VERIFIED | TR-106 |
| `ORIGINAL_VALUE_VERIFIED` | `doi-intervention-value-event/v1` / `ORIGINAL_VALUE_VERIFIED` | UNVERIFIED to VERIFIED | TR-107 |
| `ORIGINAL_VALUE_CORRECTED` | `doi-intervention-value-event/v1` / `ORIGINAL_VALUE_CORRECTED` | legal verified/reversal state to recomputed state | TR-108 |
| `REVERSAL_VERIFIED` | `doi-intervention-value-event/v1` / `REVERSAL_VERIFIED` | legal verified/reversal state to VERIFIED/PARTIALLY_REVERSED/REVERSED | TR-109 |
| `REVERSAL_CORRECTED` | `doi-intervention-value-event/v1` / `REVERSAL_CORRECTED` | exact current reversal chain to recomputed state | TR-109 |
| `REVERSAL_VOIDED` | `doi-intervention-value-event/v1` / `REVERSAL_VOIDED` | exact current reversal chain to recomputed state | TR-109 |
| `RESULT_LINK_SEARCH_NOT_FOUND` | `doi-result-link-search-event/v1` / `SEARCH_NOT_FOUND` | NONEXISTENT/NOT_FOUND/AMBIGUOUS to NOT_FOUND | TR-093 only when clearing prior ambiguity |
| `RESULT_LINK_SEARCH_AMBIGUOUS` | `doi-result-link-search-event/v1` / `CANDIDATES_AMBIGUOUS` | NONEXISTENT/NOT_FOUND/AMBIGUOUS to AMBIGUOUS | TR-092 |
| `RESULT_LINK_SYSTEM_VERIFIED` | `doi-result-link-exact-event/v1` / `SYSTEM_LINK_VERIFIED` | NONEXISTENT/AMBIGUOUS/HUMAN_CONFIRMED to AUTO_LINKED | TR-110 exactly for TR-054 creation or TR-056 exact-link conflict resolution; TR-093 only when an active same-subject link/search review is cleared. TR-091 agreeing system corroboration from HUMAN_CONFIRMED has neither TR-110 nor TR-093. |
| `RESULT_LINK_HUMAN_VERIFIED` | `doi-result-link-exact-event/v1` / `HUMAN_LINK_VERIFIED` | NONEXISTENT/AMBIGUOUS to HUMAN_CONFIRMED | TR-110 exactly for TR-055 creation or TR-057 exact-link conflict resolution; TR-093 only when an active same-subject link/search review is cleared. |
| `RESULT_LINK_CORROBORATION_APPENDED` | `doi-result-link-exact-event/v1` / `CORROBORATING_EVIDENCE_APPENDED` | linked state to same state | none |
| `RESULT_LINK_EVIDENCE_CONFLICT` | `doi-result-link-exact-event/v1` / `EVIDENCE_CONFLICT` | AUTO_LINKED/HUMAN_CONFIRMED to AMBIGUOUS | TR-111 + TR-092 |
| `RESULT_LINK_MAPPING_VERIFIED` | `doi-result-link-mapping-revision-event/v1` / `RESULT_LINK_MAPPING_VERIFIED` | no revision to VERIFIED revision 1 | subordinate TR-110 only |
| `RESULT_LINK_MAPPING_CONFLICT_RECORDED` | `doi-result-link-mapping-revision-event/v1` / `RESULT_LINK_MAPPING_CONFLICT_RECORDED` | VERIFIED n to CONFLICT_REVIEW n+1 | subordinate TR-111 only |
| `RESULT_LINK_MAPPING_CONFLICT_RESOLVED` | `doi-result-link-mapping-revision-event/v1` / `RESULT_LINK_MAPPING_CONFLICT_RESOLVED` | CONFLICT_REVIEW n to VERIFIED n+1 | subordinate TR-110 only |

Product-only relationship typed events remain free of case/order/context reverse links. A lifecycle wrapper that references one is case-owned and deletes at case purge; it does not change the reusable product event bytes.

### 5.3 Immutable-record-reference kinds

| `event_kind` | Record | Required identity and guard | Replay result |
|---|---|---|---|
| `ALTERNATE_OBSERVATION_STORED` | `doi-alternate-observation/v1` | exact active relationship revision, observed time, retention/tzdb, source facts, case/context partitions; one target-owned volatile stream | While retained, return identical observation/wrapper; no second event/deadline extension. At effective expiry delete target and wrapper atomically. |
| `ACTION_CONTEXT_OBSERVATION_LINKED` | `doi-action-context-observation-link/v1` | exact OPEN same-case context, observation, relationship revision; one target-owned volatile stream | While retained, return identical link/wrapper; no second event. At the observation/link effective expiry delete target and wrapper atomically. |
| `OPPORTUNITY_CREATED` | governing immutable opportunity schema | exact evaluation, scope hash, overlap key, option ID, product/observation/gates | Reuse exact `(evaluation_id,scenario_option_id)`; conflicting bytes fail, and no `OPPORTUNITY_REUSED` event is appended. |

### 5.4 `LifecycleEventKindV2` inventory

The derived inventory is 56 unique literals: 14 case/source/attention/retention kinds, 39 typed-event-reference kinds, and 3 immutable-record-reference kinds. Counts are derived from the closed rows above, not a quota. Deletion operations, exact replay, projection-only subeffects, non-case events, and transient post-purge rejection are not silently added to the enum.

## 6. Closure, retention, deletion, and replay rules

1. `CASE_CLOSED_HARD` and `CASE_CLOSED_REVERSIBLE` bind the exact verified closure instant and source proof. The immediately following `PURGE_SCHEDULED`, or `PURGE_RESTARTED` for TR-016/TR-017, repeats the exact policy/timezone/tzdb/arithmetic/deadline values. Both events commit atomically with the closure projection.
2. `CASE_REOPENED` and `PURGE_CANCELED` commit atomically. Each carries a required byte-identical `PriorClosureRetentionBindingV1`; cancellation copies the exact nested bytes from reopen while both independently validate the retained closure event/proof/policy and closure-bearing projection. The reopen result projection has all closure and deadline fields cleared. Any binding mismatch appends neither event and preserves the prior closed projection; the canceled deadline is retained only inside the case graph and disappears if the case is later purged.
3. Re-observing the same reversible closure never emits a closure or deadline event and never extends retention.
4. TR-018/TR-019/TR-112 commit KPI finalization and delete the complete event stream, natural-key bytes, hashes, typed-event bindings, and case projection. Success is absence. No `CASE_PURGED` kind is legal.
5. TR-043 and TR-105 similarly use absence for the deleted identifying record; they do not leave an identifying lifecycle receipt.
6. A post-purge request uses the transient schema in section 4.8 and cannot resolve a lifecycle stream or create a durable event.
7. Replay validates each retained event's schema, natural key, payload hash, full hash, live source target/binding, stream predecessor, revision, and state guard before applying its reducer. Any failure leaves the last valid projection byte-identical.
8. Replaying accepted core events into an empty projection MUST reproduce the stored result projection hash at every sequence. Replaying the same complete core stream twice yields the same projection and creates no new bytes. Each retained volatile stream separately validates its one live target and reproduces the locked unchanged core projection hash.
9. Appending a later event never changes an earlier event's canonical bytes, recorded time, source bindings, hashes, or payload. Corrections and resolutions are new events with exact predecessors.
10. `ALTERNATE_OBSERVATION_STORED` and `ACTION_CONTEXT_OBSERVATION_LINKED` never survive their target. At `min(observation_purge_eligible_at, linked_case.purge_eligible_at when non-null)`, one transaction deletes the observation, its context link when present, both target-owned volatile lifecycle streams/wrappers, their source bindings/natural-key bytes/hashes/indexes, and every direct lookup/retry/log/export derivative. Success is absence of that target graph; no core lifecycle receipt or predecessor hash is created. An immutable evaluation/opportunity that validly consumed the observation before expiry retains its already embedded observation ID/content-hash binding only as a sealed historical case-graph commitment until case purge. That downstream commitment is not a target, index, freshness fact, or independent deletion receipt; it cannot resolve/reconstruct the expired observation or authorize action, and no new evaluation may bind it after expiry. Core replay continues through the retained evaluation's own full-record hash. Case purge deletes every such downstream ID/hash.

### 6.1 Separate non-case source-import-attempt retention lifecycle

TR-114 uses one closed `DOISourceImportAttemptRetentionEventV1`. It is not a `DOIOrderLifecycleEventV2`, has no `case_id`/case revision/projection/source-binding array, and does not enter the 56-kind/eight-payload case registry. Its exact event schema is `doi-source-import-attempt-retention-event/v1`, its only event type is `SOURCE_IMPORT_ATTEMPT_PURGE_FINALIZED`, its owner-derived retention stream has sequence 1 and null predecessors, and its actor/provenance/reason tuple is exactly `SYSTEM/null/SYSTEM_VERIFIED/[RC-114]`.

Its payload schema is exactly `doi-source-import-attempt-purge-payload/v1` with the complete required/non-null member set in `source_retention_contract.md` section 13.4: transition/terminal-attempt/run-terminal authorities; closed attempt outcome; exact run-completion/policy/timezone/tzdb/calendar/deadline tuple; exact v2 aggregate month/outcome/count delta; closed batch-reference, run-last-reference, deletion-effect, result-state, no-tombstone booleans/enums. Every member is required and non-null. The only null event members are `actor_id`, `previous_event_id`, and `previous_event_content_sha256`; every unlisted key is absent and forbidden. `SUCCEEDED` alone selects `PRESENT/RELEASE`; every other outcome selects `ABSENT/NOT_APPLICABLE`. `RETAIN_RUN/RETAINED` and `DELETE_RUN/ABSENT` are the only result pairs.

Payload hash domain is `doi-source-import-attempt-purge-payload/v1\n`; event hash domain is `doi-source-import-attempt-retention-event/v1\n`. The exact stream/event ID constructors and complete canonical fixed vector are source-retention section 13.4-.5. The expected stream/event-ID/payload/full hashes are respectively `b14b67e59e765b28d927b12a6d59b161944dd27c06dbe13ce3439000f3233513`, `86b3208fb50e2352a65a49b4a74016d00956fd9109f72030071848cb500aac90`, `2ad1678cdad8d10be9b4bbb2b46d9b7158c7635638356982b8ce120d7f4c7e32`, and `738fa8d9ac327be19c099404891e9d18f47a224d8e26c1006e6faa544241c4fe`.

The event is constructed, canonicalized, hashed, and validated only inside the locked TR-114 transaction. That same transaction increments the exact non-identifying aggregate, deletes the complete attempt graph/edges/derivatives and any last-reference run graph, then deletes this event itself. It is never externally committed alone. Any injected failure rolls back the event, aggregate delta, deletion, and reference releases. A committed purge is represented by absence plus the non-identifying month/outcome/count aggregate only; no event ID/hash/reason/predecessor/tombstone survives.

The due guard uses the trusted transaction clock. Canonical `occurred_at` equals the stored exact purge-eligibility instant even if the worker runs late; `recorded_at` is the fixed fixture/transaction recording instant and is never caller-selected. Before the due guard no event bytes/hash exist. Unknown outcome/version, missing/extra/null-partition error, authority mismatch, or payload/full-hash mismatch rejects before aggregate upsert or deletion.

## 7. Fixed canonical vectors

### 7.1 Vector V1 — case creation

The exact canonical payload bytes are:

```json
{"initial_lifecycle_state":"ACTIVE","payload_type":"CASE_CREATION","post_purge_identity_lookup_performed":false,"retained_predecessor_case_id":null,"transition_ids":["TR-007"]}
```

Expected values:

| Value | Expected lowercase SHA-256 |
|---|---|
| CASE_LIFECYCLE stream ID for `SYN-DOI-CASE-0001` | `26c7b4a8d9d56577240a1c66160d0b921fc380fbe402d3e00ea3a34b8cd141f1` |
| payload hash | `c9213e527d8132e2c72cff86337e9692156dfb45c62886b4869265c25eebf2a8` |
| initial projection hash | `a739d6ce2fc0db47c6f232cfa29fa750a4f5ec95b6029b01991c92802d5b7e27` |
| event natural-key hash | `a8feba67a425e50f0a584a14336f4a3290a5f3de104cc0f86fb6ab2d34e3cb90` |
| case-source binding ID | `e39a40adfeb2b606981364928e38bb867a20f6349e0b2a734e82d0c17bceb2f3` |
| case-source admission-proof ID | `e2aa8e7b7fe795821d230ede3d731c79f8670718e277d8d0812f1a83df97636e` |
| case-source admission-proof hash | `2e9ac63cf8d5cda713e46351f4c8e8ce83429c2e39f35142113fd54da15f53b8` |
| full event hash | `0baab70132263d66f67582425bbf6d6c227ebb5c10317ea124babf5aee70c257` |

The exact initial projection canonical bytes are:

```json
{"case_id":"SYN-DOI-CASE-0001","case_projection_schema_version":"doi-order-case-projection/v2","case_revision":1,"closure_class":"NONE","closure_kind":"NONE","current_evaluation_binding":null,"current_snapshot_binding":null,"domain_projection_bindings":[],"lifecycle_state":"ACTIVE","local_calendar_arithmetic_rule_identifier":null,"purge_eligible_at":null,"retention_policy_identifier":null,"retention_policy_version":null,"timezone":null,"timezone_database_version":null,"verified_closure_at":null}
```

The exact natural-key canonical bytes are:

```json
{"case_id":"SYN-DOI-CASE-0001","event_kind":"CASE_CREATED","event_natural_key_schema_version":"doi-order-lifecycle-event-natural-key/v2","logical_occurrence_id":"e2aa8e7b7fe795821d230ede3d731c79f8670718e277d8d0812f1a83df97636e"}
```

The exact bound case-source admission-proof target canonical bytes, excluding only its `content_sha256`, are:

```json
{"admitted_at":"2026-08-09T14:00:00Z","assigned_rep_normalized":"TARGET_REP","case_id":"SYN-DOI-CASE-0001","case_source_admission_proof_id":"e2aa8e7b7fe795821d230ede3d731c79f8670718e277d8d0812f1a83df97636e","case_source_admission_proof_schema_version":"doi-case-source-admission-proof/v1","case_source_binding_id":"e39a40adfeb2b606981364928e38bb867a20f6349e0b2a734e82d0c17bceb2f3","order_number":"1","source_batch_id":"batch-fixture-001"}
```

The executable harness identity registry maps reserved synthetic identity `SYN-DOI-ORDER-0001` to schema-valid canonical positive-decimal `OrderNumber` sentinel `"1"` before this fixture is constructed. That mapping is harness metadata, never an admission-proof member, and its global firewall proves `"1"` matches no historical/source Order Number before execution. It is deliberately not a production-looking multi-digit identifier. The case-source binding ID is independently derived from the exact case/batch tuple under the source contract; the proof ID is independently derived from the same tuple under its distinct domain. Hashing the displayed proof bytes under `doi-case-source-admission-proof/v1\n` yields the published proof hash. The lifecycle fixture uses `lifecycle_event_id=life-0001`, `logical_occurrence_id=e2aa8e7b...97636e`, both instants `2026-08-09T14:00:00Z`, `SYSTEM/SYSTEM_VERIFIED`, empty reasons, null prior/predecessor values, result revision/sequence 1, and exactly one `CASE_CREATION_SOURCE/CASE_SOURCE_ADMISSION_PROOF` binding with that exact ID/schema/hash. No run/attempt/source-row identity appears in the retained target or lifecycle bytes.

The exact complete event canonical bytes, excluding only `content_sha256`, are:

```json
{"actor_id":null,"actor_kind":"SYSTEM","case_id":"SYN-DOI-CASE-0001","event_kind":"CASE_CREATED","event_natural_key_sha256":"a8feba67a425e50f0a584a14336f4a3290a5f3de104cc0f86fb6ab2d34e3cb90","event_schema_version":"doi-order-lifecycle-event/v2","lifecycle_event_id":"life-0001","logical_occurrence_id":"e2aa8e7b7fe795821d230ede3d731c79f8670718e277d8d0812f1a83df97636e","occurred_at":"2026-08-09T14:00:00Z","payload":{"initial_lifecycle_state":"ACTIVE","payload_type":"CASE_CREATION","post_purge_identity_lookup_performed":false,"retained_predecessor_case_id":null,"transition_ids":["TR-007"]},"payload_content_sha256":"c9213e527d8132e2c72cff86337e9692156dfb45c62886b4869265c25eebf2a8","previous_event_content_sha256":null,"previous_event_id":null,"prior_case_revision":null,"prior_projection_hash":null,"provenance":"SYSTEM_VERIFIED","reason_codes":[],"recorded_at":"2026-08-09T14:00:00Z","result_case_revision":1,"result_projection_hash":"a739d6ce2fc0db47c6f232cfa29fa750a4f5ec95b6029b01991c92802d5b7e27","source_bindings":[{"binding_role":"CASE_CREATION_SOURCE","entity_content_sha256":"2e9ac63cf8d5cda713e46351f4c8e8ce83429c2e39f35142113fd54da15f53b8","entity_id":"e2aa8e7b7fe795821d230ede3d731c79f8670718e277d8d0812f1a83df97636e","entity_schema_version":"doi-case-source-admission-proof/v1","entity_type":"CASE_SOURCE_ADMISSION_PROOF"}],"stream_id":"26c7b4a8d9d56577240a1c66160d0b921fc380fbe402d3e00ea3a34b8cd141f1","stream_sequence":1}
```

### 7.2 Vector V2 — hard closure across daylight-saving offset

Fixture closure is `2026-01-15T17:30:00Z` (12:30 America/New_York standard time). Exact 90-local-calendar-day preservation produces `2026-04-15T16:30:00Z` (12:30 daylight time), not a fixed 2160-hour result.

Expected values:

| Value | Expected lowercase SHA-256 |
|---|---|
| CASE_LIFECYCLE stream ID for `SYN-DOI-CASE-0002` | `7bca825060be4f0e80f71627168b8b68461703e1ae8fc97832f08268b43b024d` |
| `CASE_CLOSED_HARD` payload hash | `19ac1831b3a17883afd957810d725bd9a8c86a6ff7a6b42dc62e45adbc3e3dd4` |
| resulting closed projection hash | `d99c4ce97e398adb7521f580e00893110b69bc56daeb6a28ef58d3da14e95198` |
| event natural-key hash | `1ab0fb29b3d6f067aaa00a10b32844d73a224c371e6bff55297c9a5bc4a0568d` |
| full event hash | `1bf19ddbbd4b108617d52d349ceec5ba950947f5a587d7784b4082d88a0f4b36` |

The exact closure payload canonical bytes are:

```json
{"calculated_utc_purge_eligible_at":"2026-04-15T16:30:00Z","closure_class":"HARD","closure_kind":"SHIPPED","closure_source_entity_content_sha256":"2222222222222222222222222222222222222222222222222222222222222222","closure_source_entity_id":"snap-0002","closure_source_entity_type":"SNAPSHOT","local_calendar_arithmetic_rule_identifier":"calendar90-america-new-york/v1","payload_type":"CASE_CLOSURE","prior_lifecycle_state":"ACTIVE","prior_purge_eligible_at":null,"result_lifecycle_state":"CLOSED_HARD","retention_policy_identifier":"DOI_CASE_GRAPH","retention_policy_version":"doi-retention-calendar90-ny/v1","timezone":"America/New_York","timezone_database_version":"2026a","transition_ids":["TR-009"],"verified_closure_at":"2026-01-15T17:30:00Z"}
```

The exact resulting projection canonical bytes are:

```json
{"case_id":"SYN-DOI-CASE-0002","case_projection_schema_version":"doi-order-case-projection/v2","case_revision":7,"closure_class":"HARD","closure_kind":"SHIPPED","current_evaluation_binding":null,"current_snapshot_binding":{"entity_content_sha256":"2222222222222222222222222222222222222222222222222222222222222222","entity_id":"snap-0002","entity_schema_version":"doi-order-snapshot/v1"},"domain_projection_bindings":[],"lifecycle_state":"CLOSED_HARD","local_calendar_arithmetic_rule_identifier":"calendar90-america-new-york/v1","purge_eligible_at":"2026-04-15T16:30:00Z","retention_policy_identifier":"DOI_CASE_GRAPH","retention_policy_version":"doi-retention-calendar90-ny/v1","timezone":"America/New_York","timezone_database_version":"2026a","verified_closure_at":"2026-01-15T17:30:00Z"}
```

The exact complete event canonical bytes, excluding only `content_sha256`, are:

```json
{"actor_id":null,"actor_kind":"SYSTEM","case_id":"SYN-DOI-CASE-0002","event_kind":"CASE_CLOSED_HARD","event_natural_key_sha256":"1ab0fb29b3d6f067aaa00a10b32844d73a224c371e6bff55297c9a5bc4a0568d","event_schema_version":"doi-order-lifecycle-event/v2","lifecycle_event_id":"life-0007","logical_occurrence_id":"snap-0002","occurred_at":"2026-01-15T17:30:00Z","payload":{"calculated_utc_purge_eligible_at":"2026-04-15T16:30:00Z","closure_class":"HARD","closure_kind":"SHIPPED","closure_source_entity_content_sha256":"2222222222222222222222222222222222222222222222222222222222222222","closure_source_entity_id":"snap-0002","closure_source_entity_type":"SNAPSHOT","local_calendar_arithmetic_rule_identifier":"calendar90-america-new-york/v1","payload_type":"CASE_CLOSURE","prior_lifecycle_state":"ACTIVE","prior_purge_eligible_at":null,"result_lifecycle_state":"CLOSED_HARD","retention_policy_identifier":"DOI_CASE_GRAPH","retention_policy_version":"doi-retention-calendar90-ny/v1","timezone":"America/New_York","timezone_database_version":"2026a","transition_ids":["TR-009"],"verified_closure_at":"2026-01-15T17:30:00Z"},"payload_content_sha256":"19ac1831b3a17883afd957810d725bd9a8c86a6ff7a6b42dc62e45adbc3e3dd4","previous_event_content_sha256":"4444444444444444444444444444444444444444444444444444444444444444","previous_event_id":"life-0006","prior_case_revision":6,"prior_projection_hash":"3333333333333333333333333333333333333333333333333333333333333333","provenance":"SYSTEM_VERIFIED","reason_codes":["RC-021"],"recorded_at":"2026-01-15T17:31:00Z","result_case_revision":7,"result_projection_hash":"d99c4ce97e398adb7521f580e00893110b69bc56daeb6a28ef58d3da14e95198","source_bindings":[{"binding_role":"CLOSURE_PROOF","entity_content_sha256":"2222222222222222222222222222222222222222222222222222222222222222","entity_id":"snap-0002","entity_schema_version":"doi-order-snapshot/v1","entity_type":"SNAPSHOT"}],"stream_id":"7bca825060be4f0e80f71627168b8b68461703e1ae8fc97832f08268b43b024d","stream_sequence":7}
```

The fixture uses `case_id=SYN-DOI-CASE-0002`, `lifecycle_event_id=life-0007`, `logical_occurrence_id=snap-0002`, `SYSTEM/SYSTEM_VERIFIED`, occurred `2026-01-15T17:30:00Z`, recorded `2026-01-15T17:31:00Z`, sequence/result revision 7, prior revision 6, prior event `life-0006`, prior event digest 64 lowercase `4` characters, prior projection digest 64 lowercase `3` characters, exactly one `CLOSURE_PROOF/SNAPSHOT` binding for `snap-0002` with schema `doi-order-snapshot/v1` and digest 64 lowercase `2` characters, tzdb `2026a`, and reason set `[RC-021]`. V2 is an exact serialization/calendar/hash vector whose predecessor digests are opaque fixed inputs; `SYN-LIFE-PAYLOAD-010` separately proves the same closure through a fully reachable prior stream. Any field, null, domain, timestamp, set order, or alias change must change the appropriate digest and fail the vector.

### 7.3 Vector V3 — reopen/cancellation canonical serialization with opaque validated inputs

This paired top-level lifecycle vector fixes canonical `PriorClosureRetentionBindingV1`, payload, projection, source-binding, and full-envelope serialization for reopen and deadline cancellation. Like V2's opaque predecessor digests, it accepts the named prior closure/source/predecessor digests as fixed already-validated inputs; V3 does **not** claim to prove those target records are reachable or revalidate their governing non-lifecycle schemas. That independent reachability/authority proof belongs to `SYN-LIFE-PAYLOAD-010` below and deliberately computes its own real target hashes. V3's only case identity is reserved synthetic `SYN-DOI-CASE-0003`. The fixed closure-bearing pre-reopen projection canonical bytes are:

```json
{"case_id":"SYN-DOI-CASE-0003","case_projection_schema_version":"doi-order-case-projection/v2","case_revision":8,"closure_class":"REVERSIBLE","closure_kind":"HUMAN_OUT_OF_SCOPE","current_evaluation_binding":{"entity_content_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","entity_id":"eval-reopen-0003","entity_schema_version":"doi-evaluation-record/v1"},"current_snapshot_binding":{"entity_content_sha256":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd","entity_id":"snap-current-0003","entity_schema_version":"doi-order-snapshot/v1"},"domain_projection_bindings":[],"lifecycle_state":"CLOSED_REVERSIBLE","local_calendar_arithmetic_rule_identifier":"calendar90-america-new-york/v1","purge_eligible_at":"2026-05-16T14:00:00Z","retention_policy_identifier":"DOI_CASE_GRAPH","retention_policy_version":"doi-retention-calendar90-ny/v1","timezone":"America/New_York","timezone_database_version":"2026a","verified_closure_at":"2026-02-15T15:00:00Z"}
```

Its hash under `doi-order-case-projection/v2\n` is `a70aa963f903de71d7ab0fc1abf4f8bca8794828f4d18a832ab4c8586cf4d94f`. The exact binding bytes, copied unchanged into both events, are:

```json
{"prior_closure_classification":"REVERSIBLE","prior_closure_event_content_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","prior_closure_event_id":"life-close-0003","prior_closure_kind":"HUMAN_OUT_OF_SCOPE","prior_closure_projection_hash":"a70aa963f903de71d7ab0fc1abf4f8bca8794828f4d18a832ab4c8586cf4d94f","prior_closure_projection_revision":8,"prior_closure_retention_binding_schema_version":"doi-prior-closure-retention-binding/v1","prior_closure_source_entity_content_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","prior_closure_source_entity_id":"human-fact-close-0003","prior_closure_source_entity_schema_version":"doi-human-fact-event/v1","prior_closure_source_entity_type":"HUMAN_FACT_EVENT","prior_local_calendar_rule_id":"calendar90-america-new-york/v1","prior_purge_eligible_at":"2026-05-16T14:00:00Z","prior_retention_policy_id":"DOI_CASE_GRAPH","prior_retention_policy_version":"doi-retention-calendar90-ny/v1","prior_retention_timezone":"America/New_York","prior_tzdb_version":"2026a","prior_verified_closure_at":"2026-02-15T15:00:00Z"}
```

The 64-character `a`, `b`, `c`, `d`, and `e` values are opaque fixed serialization inputs, not claimed preimages and not values inferred from another hash. They are sufficient only for this top-level canonical-bytes/hash vector and MUST NOT be used by a test that asserts target existence. The retention-policy record itself is constructible and has hash `c60ef565b722289ae9bb7000123c02182a9ca76fef61c3334a3b08d600a7afd3`. The CASE_LIFECYCLE stream ID is `06d1179f1031e8b169e40dd09fd2696ab34baf858a8385091e62782575f13be5`.

The exact `CASE_REOPENED` payload bytes are:

```json
{"payload_type":"CASE_REOPEN","prior_closure_kind":"HUMAN_OUT_OF_SCOPE","prior_closure_retention_binding":{"prior_closure_classification":"REVERSIBLE","prior_closure_event_content_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","prior_closure_event_id":"life-close-0003","prior_closure_kind":"HUMAN_OUT_OF_SCOPE","prior_closure_projection_hash":"a70aa963f903de71d7ab0fc1abf4f8bca8794828f4d18a832ab4c8586cf4d94f","prior_closure_projection_revision":8,"prior_closure_retention_binding_schema_version":"doi-prior-closure-retention-binding/v1","prior_closure_source_entity_content_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","prior_closure_source_entity_id":"human-fact-close-0003","prior_closure_source_entity_schema_version":"doi-human-fact-event/v1","prior_closure_source_entity_type":"HUMAN_FACT_EVENT","prior_local_calendar_rule_id":"calendar90-america-new-york/v1","prior_purge_eligible_at":"2026-05-16T14:00:00Z","prior_retention_policy_id":"DOI_CASE_GRAPH","prior_retention_policy_version":"doi-retention-calendar90-ny/v1","prior_retention_timezone":"America/New_York","prior_tzdb_version":"2026a","prior_verified_closure_at":"2026-02-15T15:00:00Z"},"prior_purge_eligible_at":"2026-05-16T14:00:00Z","prior_verified_closure_at":"2026-02-15T15:00:00Z","purge_deadline_cancellation_effect":"CLEAR_ACTIVE_PURGE_DEADLINE","reopen_at":"2026-03-01T15:00:00Z","reopen_reason_code":"RC-078","reopen_source_entity_content_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","reopen_source_entity_id":"eval-reopen-0003","reopen_source_entity_schema_version":"doi-evaluation-record/v1","reopen_source_entity_type":"EVALUATION","result_case_id":"SYN-DOI-CASE-0003","result_case_revision":9,"result_closure_kind":"NONE","result_lifecycle_state":"ACTIVE","result_projection_hash":"8ee6d55e81a1f2a212f0e277089a0acc0561e4468d35e2ec6cf9aee87cd98914","result_purge_eligible_at":null,"result_verified_closure_at":null,"same_case_identity_preserved":true,"transition_ids":["TR-014"]}
```

The exact `PURGE_CANCELED` payload bytes are:

```json
{"calculated_utc_purge_eligible_at":null,"canceled_purge_eligible_at":"2026-05-16T14:00:00Z","cancellation_cause_event_content_sha256":"94e4bd6ed31f4cadc6e24c27fe22c01d1bcadaafbf72652b475b5e70d473dff0","cancellation_cause_event_id":"life-reopen-0003","closure_class":null,"closure_kind":null,"deadline_operation":"CANCEL","local_calendar_arithmetic_rule_identifier":"calendar90-america-new-york/v1","payload_type":"PURGE_DEADLINE","prior_closure_retention_binding":{"prior_closure_classification":"REVERSIBLE","prior_closure_event_content_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","prior_closure_event_id":"life-close-0003","prior_closure_kind":"HUMAN_OUT_OF_SCOPE","prior_closure_projection_hash":"a70aa963f903de71d7ab0fc1abf4f8bca8794828f4d18a832ab4c8586cf4d94f","prior_closure_projection_revision":8,"prior_closure_retention_binding_schema_version":"doi-prior-closure-retention-binding/v1","prior_closure_source_entity_content_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","prior_closure_source_entity_id":"human-fact-close-0003","prior_closure_source_entity_schema_version":"doi-human-fact-event/v1","prior_closure_source_entity_type":"HUMAN_FACT_EVENT","prior_local_calendar_rule_id":"calendar90-america-new-york/v1","prior_purge_eligible_at":"2026-05-16T14:00:00Z","prior_retention_policy_id":"DOI_CASE_GRAPH","prior_retention_policy_version":"doi-retention-calendar90-ny/v1","prior_retention_timezone":"America/New_York","prior_tzdb_version":"2026a","prior_verified_closure_at":"2026-02-15T15:00:00Z"},"prior_purge_eligible_at":"2026-05-16T14:00:00Z","resolution_source_entity_content_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","resolution_source_entity_id":"eval-reopen-0003","resolution_source_entity_schema_version":"doi-evaluation-record/v1","resolution_source_entity_type":"EVALUATION","result_case_id":"SYN-DOI-CASE-0003","result_case_revision":10,"result_projection_hash":"5440d425dc55c463c67d7ca6141082049b9dfc0ba2ec7a2ddcf8c209f6f73b50","result_purge_deadline_state":"CANCELED","result_purge_eligible_at":null,"retention_policy_identifier":"DOI_CASE_GRAPH","retention_policy_version":"doi-retention-calendar90-ny/v1","same_case_identity_preserved":true,"source_event_content_sha256":"94e4bd6ed31f4cadc6e24c27fe22c01d1bcadaafbf72652b475b5e70d473dff0","source_event_id":"life-reopen-0003","timezone":"America/New_York","timezone_database_version":"2026a","transition_ids":["TR-014"],"verified_closure_at":null}
```

Expected hashes are:

| Value | Expected lowercase SHA-256 |
|---|---|
| reopen result projection, revision 9 | `8ee6d55e81a1f2a212f0e277089a0acc0561e4468d35e2ec6cf9aee87cd98914` |
| `CASE_REOPENED` payload | `6550aa6c8a82ecea90f4ffb7a185c6f96c8a6ed57193fbfbc7c6004cafdda4ce` |
| `CASE_REOPENED` natural key | `72078bfb14f4360fed638ddb88a598949f57c8dd9baf9ee15862983e432ccc07` |
| `CASE_REOPENED` full event | `94e4bd6ed31f4cadc6e24c27fe22c01d1bcadaafbf72652b475b5e70d473dff0` |
| cancel result projection, revision 10 | `5440d425dc55c463c67d7ca6141082049b9dfc0ba2ec7a2ddcf8c209f6f73b50` |
| `PURGE_CANCELED` payload | `a0513a1305231296eec1b2a1e8b632545294c88ad0872266c3c6776a3f5fede5` |
| `PURGE_CANCELED` natural key | `292150b5da914ac2ecd6e22871bdcfa9e63d4deb5fadc60ba7cd6c38ebe331a6` |
| `PURGE_CANCELED` full event | `f434eba59677521936b21f3f45a8f9ceff3e3a195e001c2eb0944fb6229976e3` |

The exact canonical source-binding arrays, already in complete-member RFC-8785 sort order, are:

```json
[{"binding_role":"CAUSE_EVENT","entity_content_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","entity_id":"life-close-0003","entity_schema_version":"doi-order-lifecycle-event/v2","entity_type":"ORDER_LIFECYCLE_EVENT"},{"binding_role":"CLOSURE_PROOF","entity_content_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","entity_id":"human-fact-close-0003","entity_schema_version":"doi-human-fact-event/v1","entity_type":"HUMAN_FACT_EVENT"},{"binding_role":"REOPEN_PROOF","entity_content_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","entity_id":"eval-reopen-0003","entity_schema_version":"doi-evaluation-record/v1","entity_type":"EVALUATION"},{"binding_role":"RETENTION_POLICY","entity_content_sha256":"c60ef565b722289ae9bb7000123c02182a9ca76fef61c3334a3b08d600a7afd3","entity_id":"doi-retention-calendar90-ny/v1@2026a","entity_schema_version":"doi-retention-policy-binding/v1","entity_type":"RETENTION_POLICY_RECORD"}]
```

```json
[{"binding_role":"CAUSE_EVENT","entity_content_sha256":"94e4bd6ed31f4cadc6e24c27fe22c01d1bcadaafbf72652b475b5e70d473dff0","entity_id":"life-reopen-0003","entity_schema_version":"doi-order-lifecycle-event/v2","entity_type":"ORDER_LIFECYCLE_EVENT"},{"binding_role":"CAUSE_EVENT","entity_content_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","entity_id":"life-close-0003","entity_schema_version":"doi-order-lifecycle-event/v2","entity_type":"ORDER_LIFECYCLE_EVENT"},{"binding_role":"CLOSURE_PROOF","entity_content_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","entity_id":"human-fact-close-0003","entity_schema_version":"doi-human-fact-event/v1","entity_type":"HUMAN_FACT_EVENT"},{"binding_role":"RESOLUTION_SOURCE","entity_content_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","entity_id":"eval-reopen-0003","entity_schema_version":"doi-evaluation-record/v1","entity_type":"EVALUATION"},{"binding_role":"RETENTION_POLICY","entity_content_sha256":"c60ef565b722289ae9bb7000123c02182a9ca76fef61c3334a3b08d600a7afd3","entity_id":"doi-retention-calendar90-ny/v1@2026a","entity_schema_version":"doi-retention-policy-binding/v1","entity_type":"RETENTION_POLICY_RECORD"}]
```

To remove every remaining reconstruction choice, the complete non-payload envelope members are fixed as follows. The `payload` member is exactly the corresponding canonical object printed above, not a hash alias.

| Envelope member | `CASE_REOPENED` exact value | `PURGE_CANCELED` exact value |
|---|---|---|
| `event_schema_version` | `doi-order-lifecycle-event/v2` | `doi-order-lifecycle-event/v2` |
| `lifecycle_event_id` | `life-reopen-0003` | `life-cancel-0003` |
| `case_id` | `SYN-DOI-CASE-0003` | `SYN-DOI-CASE-0003` |
| `stream_id` | `06d1179f1031e8b169e40dd09fd2696ab34baf858a8385091e62782575f13be5` | same exact value |
| `stream_sequence` | `9` | `10` |
| `previous_event_id` | `life-before-reopen-0003` | `life-reopen-0003` |
| `previous_event_content_sha256` | 64 lowercase `e` characters | `94e4bd6ed31f4cadc6e24c27fe22c01d1bcadaafbf72652b475b5e70d473dff0` |
| `event_kind` | `CASE_REOPENED` | `PURGE_CANCELED` |
| `logical_occurrence_id` | `eval-reopen-0003` | `life-reopen-0003` |
| `event_natural_key_sha256` | `72078bfb14f4360fed638ddb88a598949f57c8dd9baf9ee15862983e432ccc07` | `292150b5da914ac2ecd6e22871bdcfa9e63d4deb5fadc60ba7cd6c38ebe331a6` |
| `occurred_at` | `2026-03-01T15:00:00Z` | `2026-03-01T15:00:00Z` |
| `recorded_at` | `2026-03-01T15:00:30Z` | `2026-03-01T15:00:30Z` |
| `actor_kind` / `actor_id` / `provenance` | `SYSTEM` / null / `SYSTEM_VERIFIED` | same exact values |
| `prior_case_revision` / `result_case_revision` | `8` / `9` | `9` / `10` |
| `prior_projection_hash` | `a70aa963f903de71d7ab0fc1abf4f8bca8794828f4d18a832ab4c8586cf4d94f` | `8ee6d55e81a1f2a212f0e277089a0acc0561e4468d35e2ec6cf9aee87cd98914` |
| `result_projection_hash` | `8ee6d55e81a1f2a212f0e277089a0acc0561e4468d35e2ec6cf9aee87cd98914` | `5440d425dc55c463c67d7ca6141082049b9dfc0ba2ec7a2ddcf8c209f6f73b50` |
| `source_bindings` | first exact array above | second exact array above |
| `reason_codes` | `["RC-078"]` | `["RC-080"]` |
| `payload_content_sha256` | `6550aa6c8a82ecea90f4ffb7a185c6f96c8a6ed57193fbfbc7c6004cafdda4ce` | `a0513a1305231296eec1b2a1e8b632545294c88ad0872266c3c6776a3f5fede5` |

RFC-8785 serialization of the exact closed envelope object containing those members and the printed payload, followed by the section-2 `doi-order-lifecycle-event/v2\n` domain, independently reproduces the two published full hashes. `content_sha256` is excluded from that input and then stores the matching result. V3 is not the authority-existence oracle. `SYN-LIFE-PAYLOAD-010` separately constructs actual closed-schema target records and a reachable prior stream, computes their real hashes, constructs its authoritative binding from those records, copies those real binding bytes unchanged into its cancellation, and publishes/compares that fixture's generated expected bytes/hashes without substituting V3's opaque inputs.

## 8. New deterministic release-blocking oracles

These 12 new IDs are required; they are derived coverage, not a quota.

| ID | Exact deterministic oracle |
|---|---|
| `SYN-LIFE-PAYLOAD-001` | Enumerate `LifecycleEventKindV2`; prove exactly one payload schema/typed-schema row per kind, no duplicates, and section 9 covers all 115 final transitions exactly once as owner, subordinate, non-case, or deletion/no-event. Separately validate the one transaction-local non-case retention kind/payload without adding it to the case union. |
| `SYN-LIFE-PAYLOAD-002` | Reproduce V1 using exact `case_id=SYN-DOI-CASE-0001` and harness identity `SYN-DOI-ORDER-0001`, deterministically mapped to schema-valid nonhistorical sentinel `order_number="1"`; construct the case binding and privacy-minimized admission proof, then verify canonical payload/projection/natural/full bytes and regenerated stream `26c7b4a8...141f1`, proof ID `e2aa8e7b...97636e`, proof hash `2e9ac63c...5f53b8`, projection `a739d6ce...b7e27`, natural `a8feba67...e3cb90`, and full-event `0baab701...70c257` exactly. Assert no run/attempt/source-row identity exists in the lifecycle target. The old staged-target vector and every old dependent hash fail before execution. |
| `SYN-LIFE-PAYLOAD-003` | Reproduce V2 using exact `case_id=SYN-DOI-CASE-0002`; verify the local-calendar deadline and regenerated stream `7bca8250...b024d`, projection `d99c4ce9...e95198`, natural `1ab0fb29...0568d`, and full-event `1bf19ddb...f4b36` hashes exactly; fixed-elapsed arithmetic or the old `case-0002` input produces a failing non-oracle. |
| `SYN-LIFE-PAYLOAD-004` | Table-drive one valid canonical fixture for every one of the 56 event kinds. For `CASE_REOPENED` and `PURGE_CANCELED`, construct actual closed-schema closure/projection/proof/policy records, compute their real hashes, include their byte-equal `PriorClosureRetentionBindingV1`, require canceled-deadline equality and complete source-binding sets, and verify payload/full bytes and hashes, state guard, result revision/projection, same-case identity, and exact replay. Do not use V3's opaque serialization inputs for this validity branch. |
| `SYN-LIFE-PAYLOAD-005` | For every kind, delete each required key, null each required-non-null key, populate each required-null key, and add one unknown key. For reopen/cancel specifically table-drive: kind mismatch; classification mismatch; verified-instant mismatch; policy-ID mismatch; policy-version mismatch; timezone mismatch; tzdb mismatch; local-calendar-rule mismatch; purge-deadline mismatch; prior projection-revision mismatch; prior projection-hash mismatch; omitted explicit tuple/hash-only inference; closure-event/proof identity/schema/hash mismatch; unknown binding version; and any reopen-to-cancel byte difference. Every mutation yields RC-113 before append, rolls the complete bundle back, and leaves the prior projection/deadline byte-identical. |
| `SYN-LIFE-PAYLOAD-006` | Unknown event kind, payload type, lifecycle schema version, typed schema version, enum, domain prefix, or duplicate alias yields RC-113; no permissive fallback exists. |
| `SYN-LIFE-PAYLOAD-007` | Exact natural/full-byte replay returns the original event; same natural key with changed bytes fails; stale/forked sequence/revision/predecessor uses RC-111; collision canary adds RC-103. |
| `SYN-LIFE-PAYLOAD-008` | Actor/provenance or source-binding ID/schema/hash mismatch fails; typed fact and wrapper commit atomically; no copied typed payload appears in lifecycle bytes. |
| `SYN-LIFE-PAYLOAD-009` | SET derives its cause key only from cause provenance; CLEAR by a different resolver references the active SET/key and preserves both provenance groups; wrong/missing/conflicting resolver fails. |
| `SYN-LIFE-PAYLOAD-010` | From fully reachable hard/reversible closure streams and actual closed-schema source/evaluation/typed target records, compute every target/event/projection hash; prove unchanged reversible re-observation, a valid same-case reopen plus cancel with byte-equal explicit prior tuple, and reversible-to-hard restart. This reachable fixture has its own generated expected binding/payload/full-event bytes and hashes and MUST NOT substitute V3's opaque inputs. Replay reproduces its exact final ACTIVE/null-deadline state. Together with the separate V3 fixed-serialization branch, the 15 valid/mismatch/hash-only/rollback/replay/fixed-byte branches required by Round 3 are deterministic; any mismatch appends neither event and preserves the locked prior state. |
| `SYN-LIFE-PAYLOAD-011` | Table-drive representative multi-row atomic bundles in every caller/map/thread permutation, apply the exact dependency/topological tie-break, and replay the resulting mixed typed/case stream twice; event order and each intermediate/final projection hash are identical and every pre-existing event byte/hash remains unchanged. |
| `SYN-LIFE-PAYLOAD-012` | Case/rejected-record purge leaves no event/receipt/hash/tombstone. Observation expiry deletes the target/link/volatile-wrapper graph and direct indexes/receipts; only a preexisting sealed evaluation/opportunity observation commitment remains non-resolvable/non-fresh until case purge, then is absent. Post-case-purge request returns only the transient schema, creates no durable bytes, performs no identity reconstruction, and changes no aggregate. |

Each oracle also asserts zero OA writes, no write-capable OA capability, no source-workbook mutation, and no historical target usage.

The package-wide identity-firewall oracle `SYN-OA-RO-009` is incorporated here without creating a second lifecycle test ID: it injects `case-0001` and equivalent non-prefixed executable identities and requires rejection before fixture execution, event allocation, or OA access. It scans registry source, generated fixtures, and built outputs and permits lifecycle executable case identities only when they begin with exact `SYN-DOI-`.

## 9. Mechanical reconciliation to all 115 final transition rows

Legend: `L:` lifecycle kind in this registry; `T:` existing non-case or typed immutable event; `R:` immutable record append with lifecycle reference where case-linked; `P:` projection/subordinate effect represented in its owning lifecycle event and result-projection hash, with no independent lifecycle event; `D:` atomic deletion represented by absence, with no surviving identifying event. Multiple entries in one cell are an atomic ordered bundle. Exact replay is always a no-op and is not another transition.

| Transition | Closed serialization route |
|---|---|
| TR-001 | T:`RUN_INVOCATION_ACCEPTED`; T:`SOURCE_IMPORT_STARTED` atomically |
| TR-002 | T:`RUN_TERMINAL/COMPLETED` |
| TR-003 | T:`RUN_TERMINAL/COMPLETED_WITH_EXCEPTIONS` |
| TR-004 | T:`SOURCE_IMPORT_FAILED`; T:`RUN_TERMINAL/FAILED` atomically |
| TR-005 | R:`DOIExtractionAttempt/SUCCEEDED`; L:`SNAPSHOT_ACCEPTED` |
| TR-006 | R:`DOIExtractionAttempt/FAILED`; L:`EXTRACTION_FAILED`; L:`ATTENTION_SET` |
| TR-007 | R:`DOICaseSourceAdmissionProofV1`; L:`CASE_CREATED` binding that proof, never the staged attempt record |
| TR-008 | R/reuse:`DOICaseSourceAdmissionProofV1`; L:`SOURCE_PRESENT`; L:`SNAPSHOT_ACCEPTED`; L:`EVALUATION_ACCEPTED` |
| TR-009 | L:`CASE_CLOSED_HARD(SHIPPED)`; L:`PURGE_SCHEDULED` |
| TR-010 | L:`CASE_CLOSED_HARD(CANCELED)`; L:`PURGE_SCHEDULED` |
| TR-011 | L:`CASE_CLOSED_REVERSIBLE(REP_TRANSFERRED)`; L:`PURGE_SCHEDULED` |
| TR-012 | L:`DEDUPE_OA_NOTE_SYSTEM_VERIFIED`; L:`CASE_CLOSED_REVERSIBLE(DEDUPE_CONFIRMED)`; L:`PURGE_SCHEDULED` |
| TR-013 | L:`HUMAN_FACT_RECORDED`; L:`CASE_CLOSED_REVERSIBLE(HUMAN_OUT_OF_SCOPE)`; L:`PURGE_SCHEDULED` |
| TR-014 | Three closed branches: REP_TRANSFERRED = L:`SNAPSHOT_ACCEPTED`; L:`EVALUATION_ACCEPTED`; L:`CASE_REOPENED`; L:`PURGE_CANCELED`. DEDUPE_CONFIRMED = L:`EVALUATION_ACCEPTED`; L:`DEDUPE_ELIGIBILITY_RETURNED`; L:`CASE_REOPENED`; L:`PURGE_CANCELED`. HUMAN_OUT_OF_SCOPE = L:`HUMAN_FACT_RECORDED` for a first accepted fact or L:`HUMAN_FACT_CORRECTED` for the one legal predecessor-bound correction; then L:`EVALUATION_ACCEPTED`; L:`CASE_REOPENED`; L:`PURGE_CANCELED`. Existing already-accepted proof wrappers are not duplicated. |
| TR-015 | L:`SNAPSHOT_ACCEPTED`; L:`EVALUATION_ACCEPTED`; no closure/deadline event |
| TR-016 | L:`CASE_CLOSED_HARD(SHIPPED)`; L:`PURGE_RESTARTED` |
| TR-017 | L:`CASE_CLOSED_HARD(CANCELED)`; L:`PURGE_RESTARTED` |
| TR-018 | P:TR-112; D:case graph and lifecycle stream atomically |
| TR-019 | P:TR-112; D:case graph and lifecycle stream atomically |
| TR-020 | L:`ATTENTION_SET(RECHECK_REQUIRED)` |
| TR-021 | L:`SOURCE_ABSENT`; L:`ATTENTION_SET(SOURCE_ABSENT_RECHECK_REQUIRED)` |
| TR-022 | L:`EXTRACTION_FAILED`; L:`ATTENTION_CLEARED(SOURCE_ABSENT_RECHECK_REQUIRED)`; L:`ATTENTION_SET(RECHECK_REQUIRED)` |
| TR-023 | L:`SNAPSHOT_ACCEPTED`; L:`EVALUATION_ACCEPTED`; L:`ATTENTION_CLEARED`. Any additional proved effect is serialized only by its separately named committed transition row. |
| TR-024 | L:`SNAPSHOT_ACCEPTED`; L:`EVALUATION_ACCEPTED`; L:`ATTENTION_CLEARED` |
| TR-025 | L:`ATTENTION_SET(INTERVENTION_VERIFICATION_REQUIRED)` |
| TR-026 | L:`INTERVENTION_ACTION_SYSTEM_VERIFIED` for the system-proof branch or L:`INTERVENTION_ACTION_HUMAN_VERIFIED` for the structured-human-proof branch; then L:`ATTENTION_CLEARED`; P:TR-106 |
| TR-027 | L:`EVALUATION_ACCEPTED`; zero or more L:`OPPORTUNITY_CREATED` in canonical option order |
| TR-028 | L:`EVALUATION_ACCEPTED`; zero or more L:`OPPORTUNITY_CREATED` in canonical option order |
| TR-029 | P:top-level DOI projection inside owning `EVALUATION_ACCEPTED`; closure kinds through TR-009/010 |
| TR-030 | P:top-level DOI projection inside owning `EVALUATION_ACCEPTED`; closure through TR-011/012/013 |
| TR-031 | P:top-level DOI projection inside owning `EVALUATION_ACCEPTED` |
| TR-032 | P:top-level DOI projection inside owning `EVALUATION_ACCEPTED` |
| TR-033 | P:DOI projection; L:`OPPORTUNITY_CREATED` for each valid candidate |
| TR-034 | P:DOI projection; L:`OPPORTUNITY_CREATED` |
| TR-035 | P:DOI projection; L:`OPPORTUNITY_CREATED` for each valid candidate |
| TR-036 | P:top-level DOI projection inside owning `EVALUATION_ACCEPTED` |
| TR-037 | P:top-level DOI projection inside owning `EVALUATION_ACCEPTED` |
| TR-038 | P:top-level DOI projection inside owning `EVALUATION_ACCEPTED` |
| TR-039 | L:`HUMAN_FACT_RECORDED`; L:`EVALUATION_ACCEPTED` |
| TR-040 | T+L:`ALTERNATE_RELATIONSHIP_SUPERSEDED` when case-bound; product-only T otherwise |
| TR-041 | T+L:`ALTERNATE_RELATIONSHIP_INVALIDATED` when case-bound; product-only T otherwise |
| TR-042 | Product-only/de-linked branch (`case_id=null`, `action_context_id=null`): R:`ALTERNATE_OBSERVATION_STORED` only, with no case lifecycle stream. Case-linked branch: R+L:`ALTERNATE_OBSERVATION_STORED`. Current-for-action branch additionally commits TR-085 and R+L:`ACTION_CONTEXT_OBSERVATION_LINKED`. |
| TR-043 | D:observation/context link; no surviving identifying lifecycle receipt |
| TR-044 | T+L:`INTERVENTION_ACTION_SYSTEM_VERIFIED`; P:TR-106 |
| TR-045 | T+L:`INTERVENTION_ACTION_HUMAN_VERIFIED`; P:TR-106 |
| TR-045A | T+L:`INTERVENTION_ACTION_SYSTEM_VERIFIED` for the deterministic-system branch or T+L:`INTERVENTION_ACTION_HUMAN_VERIFIED` for the structured-human branch; P:TR-106 NOT_APPLICABLE branch |
| TR-046 | T+L:`ORIGINAL_VALUE_VERIFIED` SYSTEM; P:TR-107 |
| TR-047 | T+L:`ORIGINAL_VALUE_VERIFIED` HUMAN; P:TR-107 |
| TR-048 | T+L:`ORIGINAL_VALUE_CORRECTED`; P:TR-108 |
| TR-049 | P:value/KPI reducer result inside the accepted correction/reversal event |
| TR-050 | T+L:`REVERSAL_VERIFIED`; P:TR-109 partial result |
| TR-051 | T+L:`REVERSAL_VERIFIED`; P:TR-109 full result |
| TR-052 | T+L:`REVERSAL_CORRECTED` or `REVERSAL_VOIDED`; P:TR-109 |
| TR-053 | T+L:`ORIGINAL_VALUE_CORRECTED`; P:TR-108 |
| TR-054 | T+L:`RESULT_LINK_SYSTEM_VERIFIED`; T+L:`RESULT_LINK_MAPPING_VERIFIED`; L:`ATTENTION_CLEARED` only when this initial exact link resolves an active same-subject search-ambiguity cause; P:TR-110 |
| TR-055 | T+L:`RESULT_LINK_HUMAN_VERIFIED`; T+L:`RESULT_LINK_MAPPING_VERIFIED`; L:`ATTENTION_CLEARED` only when this initial exact link resolves an active same-subject search-ambiguity cause; P:TR-110 |
| TR-056 | T+L:`RESULT_LINK_SYSTEM_VERIFIED`; T+L:`RESULT_LINK_MAPPING_CONFLICT_RESOLVED`; L:`ATTENTION_CLEARED`; P:TR-110 |
| TR-057 | T+L:`RESULT_LINK_HUMAN_VERIFIED`; T+L:`RESULT_LINK_MAPPING_CONFLICT_RESOLVED`; L:`ATTENTION_CLEARED`; P:TR-110 |
| TR-058 | T+L:`RESULT_LINK_EVIDENCE_CONFLICT`; T+L:`RESULT_LINK_MAPPING_CONFLICT_RECORDED`; L:`ATTENTION_SET`; P:TR-111 |
| TR-059 | T+L:`RESULT_LINK_EVIDENCE_CONFLICT`; T+L:`RESULT_LINK_MAPPING_CONFLICT_RECORDED`; L:`ATTENTION_SET`; P:TR-111 |
| TR-060 | T+L:`DEDUPE_CANDIDATE_DERIVED` |
| TR-061 | T+L:`HUMAN_FACT_RECORDED(DEDUPE_APPROVED)`; T+L:`DEDUPE_HUMAN_APPROVED`, same transaction |
| TR-062 | T+L:`HUMAN_FACT_RECORDED` for a first `DEDUPE_REJECTED` decision or T+L:`HUMAN_FACT_CORRECTED` for the sole legal predecessor-bound approval-to-rejection correction; T+L:`DEDUPE_HUMAN_REJECTED`, same transaction |
| TR-063 | T+L:`DEDUPE_OA_NOTE_SYSTEM_VERIFIED`; closure/schedule bundle of TR-012 |
| TR-064 | T+L:`DEDUPE_ELIGIBILITY_RETURNED`; reopen/cancel bundle of TR-014 |
| TR-065 | T+L:`CONTACT_REQUIRED_DERIVED` |
| TR-066 | T+L:`CONTACT_ATTEMPT_RECORDED` |
| TR-067 | T+L:`CONTACT_ATTEMPT_RECORDED` |
| TR-068 | T+L:`AWAITING_CUSTOMER_RECORDED` |
| TR-069 | T+L:`CUSTOMER_APPROVAL_RECORDED` |
| TR-070 | T+L:`CUSTOMER_DECLINE_RECORDED` |
| TR-071 | T+L:`NO_RESPONSE_RECORDED` |
| TR-072 | T+L:`CUSTOMER_APPROVAL_RECORDED` |
| TR-073 | T+L:`CUSTOMER_DECLINE_RECORDED` |
| TR-074 | T+L:`WWC_PROJECTION_APPENDED(NOT_APPLICABLE)` |
| TR-075 | T+L:`WWC_PROJECTION_APPENDED(ACTIVE_SELF)` |
| TR-076 | T+L:`WWC_PROJECTION_APPENDED(ACTIVE_OTHER_REP)` |
| TR-077 | T+L:`WWC_PROJECTION_APPENDED(EXPIRED_OTHER_REP)` |
| TR-078 | T+L:`WWC_PROJECTION_APPENDED(uncertainty)`; L:`ATTENTION_SET` |
| TR-079 | T+L:`WWC_PROJECTION_APPENDED`; L:`ATTENTION_CLEARED` when resolved |
| TR-080 | T+L:`CONTACT_ATTEMPT_RECORDED` |
| TR-081 | T+L:`CUSTOMER_DECLINE_RECORDED` |
| TR-082 | T+L:`ALTERNATE_RELATIONSHIP_CREATED` when case-bound; product-only T otherwise |
| TR-083 | T+L:`ALTERNATE_RELATIONSHIP_REVISION_APPENDED` when case-bound; product-only T otherwise |
| TR-084 | T+L:`ACTION_CONTEXT_OPENED` |
| TR-085 | R+L:`ACTION_CONTEXT_OBSERVATION_LINKED` for one accepted case-linked alternate observation and one exact OPEN same-scope Action Context. Structured HumanFacts bind `action_context_id` directly in their own typed event and do not use TR-085 or this link record. |
| TR-086 | T+L:`ACTION_CONTEXT_COMPLETED` |
| TR-087 | T+L:`ACTION_CONTEXT_ABANDONED` or `ACTION_CONTEXT_SUPERSEDED` |
| TR-088 | T+L:`RESULT_LINK_SEARCH_NOT_FOUND`; L:`ATTENTION_CLEARED` when resolving prior ambiguity |
| TR-089 | T+L:`RESULT_LINK_SEARCH_AMBIGUOUS`; L:`ATTENTION_SET` |
| TR-090 | T+L:`RESULT_LINK_CORROBORATION_APPENDED` |
| TR-091 | T+L:`RESULT_LINK_SYSTEM_VERIFIED` |
| TR-092 | L:`ATTENTION_SET(RESULTING_ORDER_LINK_REVIEW)` |
| TR-093 | L:`ATTENTION_CLEARED(RESULTING_ORDER_LINK_REVIEW)` |
| TR-094 | L:`ATTENTION_SET(HUMAN_COORDINATION_REVIEW_REQUIRED)` |
| TR-095 | L:`WWC_PROJECTION_APPENDED`; L:`ATTENTION_CLEARED(HUMAN_COORDINATION_REVIEW_REQUIRED)` |
| TR-096 | T+L:`DEDUPE_CANDIDATE_WITHDRAWN` |
| TR-097 | T+L:`HUMAN_FACT_RECORDED` or `HUMAN_FACT_CORRECTED`; L:`EVALUATION_ACCEPTED` only when rules-relevant |
| TR-098 | T:`SOURCE_IMPORT_STARTED` (non-case initial or legal next-ordinal retry) |
| TR-099 | T:`SOURCE_IMPORT_SUCCEEDED`; R:READY staged set. No case lifecycle event; later case work independently owns `SOURCE_PRESENT` under TR-008. |
| TR-100 | T:`SOURCE_IMPORT_FAILED` then legal retry or `RUN_TERMINAL/FAILED`; alternatively T:`SOURCE_IMPORT_ABORTED` with empty reasons and later retry; no case event |
| TR-101 | R:`DOISourceBatch/READY`; binding is represented in source-import success |
| TR-102 | R:reuse existing exact batch; exact replay/binding, no new batch event |
| TR-103 | R:`DOIRejectedSourceRecord`; no case/lifecycle event |
| TR-104 | T:`DOIRejectedSourceRetentionEvent/RETENTION_SCHEDULED`; no case event |
| TR-105 | D:rejected identity/retention stream; no receipt |
| TR-106 | P:atomic result-projection effect inside accepted TR-044/045/045A lifecycle wrapper |
| TR-107 | P:atomic KPI effect inside accepted `ORIGINAL_VALUE_VERIFIED` wrapper |
| TR-108 | P:atomic KPI effect inside accepted `ORIGINAL_VALUE_CORRECTED` wrapper |
| TR-109 | P:atomic KPI effect inside accepted reversal/correction/void wrapper |
| TR-110 | T+L:`RESULT_LINK_MAPPING_VERIFIED` subordinate to TR-054/TR-055 initial exact-link creation, or T+L:`RESULT_LINK_MAPPING_CONFLICT_RESOLVED` subordinate to TR-056/TR-057 conflict resolution |
| TR-111 | T+L:`RESULT_LINK_MAPPING_CONFLICT_RECORDED`, subordinate to TR-058/059 |
| TR-112 | P:optional finalization inside TR-018/019; D:contribution/case graph and lifecycle stream |
| TR-113 | D:release all due `DOISourceBatchReference` rows with their closed non-case owners; if the exact post-release `NOT EXISTS` predicate is true, delete the complete identifying source-batch identity/fingerprints/derivatives in the same transaction; if false retain the byte-identical batch. No case-lifecycle event, batch tombstone, hash, or deletion receipt survives. A case-purge caller deletes its case lifecycle stream independently in the same owning transaction. |
| TR-114 | T+D:construct/hash one separate non-case `DOISourceImportAttemptRetentionEventV1/SOURCE_IMPORT_ATTEMPT_PURGE_FINALIZED` with RC-114 inside the locked transaction, upsert the closed aggregate, delete the complete attempt/staged/due-rejection/reference/artifact graph, conditionally delete the last-reference run graph, then delete the retention event itself. No case-lifecycle kind or identifying receipt survives. |

All 115 final row identities are present exactly once in the left column: TR-001 through TR-114 plus TR-045A. The case-lifecycle inventory remains 56 kinds/eight case payload schemas. The separately governed transaction-local retention lifecycle adds one non-case kind and one non-case purge payload schema, both deleted in their own commit; it is never counted inside `LifecycleEventKindV2`.

## 10. Reason-code addition

The registry carries the case-lifecycle schema code and the separate source-import retention audit code at their allocated identifiers:

| ID | Code | Class | Owner | Exact trigger/effect |
|---|---|---|---|---|
| `RC-113` | `LIFECYCLE_EVENT_SCHEMA_INVALID` | SAFETY | lifecycle serialization boundary | Unknown lifecycle kind/version/payload type; missing/extra field; wrong required/null/absent partition; illegal enum/alias/domain; actor/provenance or typed-event binding mismatch; incorrect natural-key, payload, projection, or full-event hash. Block and reject before append; preserve the prior projection. Stream predecessor/revision faults remain RC-111; proven digest collisions remain RC-103; unlisted state edges remain RC-081. |
| `RC-114` | `SOURCE_IMPORT_ATTEMPT_PURGED` | AUDIT | TR-114 transaction-local `DOISourceImportAttemptRetentionEventV1` | Exact due attempt graph and all identifying derivatives/edges are deleted atomically after the closed aggregate increment; the event/reason itself is deleted before commit and no tombstone/hash/lookup survives. |

RC-113 remains the case-lifecycle schema guard. RC-114 and TR-114 belong only to the separate non-case retention graph and do not extend `LifecycleEventKindV2`.

## 11. Privacy, retention, and Synthetic Order Portal safety

- Lifecycle payloads contain identifiers and hashes only for the retained case graph or an exact de-linked product record used by it. They contain no customer name, email, phone, address, VIN, note body, raw HTML/DOM, screenshot, cookie, credential, session value, arbitrary free text, or non-TARGET_REP source row.
- Every case-local lifecycle byte, key, binding, and projection hash deletes with the case. It cannot survive as a log field, analytics dimension, dead-letter payload, retry key, export, or tombstone.
- A reusable relationship/revision survives only in its product-only typed stream; the case lifecycle wrapper that referenced it does not survive case purge.
- The event registry describes DOI-local serialization only. It contains no OA request, selector, navigation, click, submit, input, script, mutation, or credential capability. OA remains permanently 100% read-only.

## 12. Required incorporation boundary

This registry becomes authoritative only when the v0.1.5 technical specification, machine contract, provenance/state contract, persistence model, state-transition matrix, transition traceability, reason registry, acceptance matrix, synthetic requirements, implementation handoff, historical finalization/coverage reports, and remediation delta all incorporate it without a looser duplicate schema. The integration map beside this draft gives exact replacements.

This artifact does not declare the specification frozen.
