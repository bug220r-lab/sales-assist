
> **Sanitized supporting reference.** This file is a mechanically sanitized derivative of
> source material supplied for the synthetic proof of concept. Historical status/freeze
> language is nonbinding. The curated files under `specs/` govern. No production-system
> access or real-data use is authorized by this reference.

# R01 Whole-Order Completeness Contract

Status: normative modular R01 object; not integrated and not frozen. Proof schema `doi-whole-order-completeness-proof/r01-v1`; line manifest `doi-whole-order-line-manifest/r01-v1`.

The proof-type registry `doi-whole-order-proof-type-registry/r01-v1` has exactly `STATIC_FIXTURE_LINE_MANIFEST` and content SHA-256 `480b91d3a1205ecc0504158b10bc851348cd2c90732289bb21522d4a3635bcad`. Production OA proof types and line-category mappings remain Phase 2.

## Relevant-line universe

For the offline fixture only, the relevant universe is every entry in the complete declared inventory whose `line_role=RELEVANT_MERCHANDISE`, regardless of ACTIVE/CANCELED/UNKNOWN activity. `EXCLUDED_NON_MERCHANDISE` entries remain in the full source inventory but create no `DOILineItemSnapshot`. No production tax/shipping/fee/merchandise mapping is inferred.

Zero relevant lines are legal only when the complete source inventory proves zero relevant entries. It yields an empty line-snapshot manifest and never proves FULL_DS or another universal active-merchandise result.

## WholeOrderLineManifestV1

Exact members: `line_manifest_schema_version`, `fixture_id`, `fixture_content_sha256`, `source_revision_token`, `declared_total_line_count`, `observed_total_line_count`, `declared_relevant_line_count`, `observed_relevant_line_count`, `entries`, `line_manifest_content_sha256`.

Each entry is exactly `{fixture_line_id,line_role,line_result_schema_version,line_result_content_sha256}`. Entries include every relevant and excluded source line, sort by fixture line ID, and are duplicate-free. Domain: `doi-whole-order-line-manifest/r01-v1\n` over the complete object except its hash.

Every manifest member is required and non-null. Counts are nonnegative JSON integers; IDs/tokens satisfy the fake-adapter grammars; all hashes are 64 lowercase hex; entries is a required array that may be empty. Missing/extra/duplicate members or a count/key/hash contradiction reject.

## WholeOrderCompletenessProofV1

Exact members: `proof_schema_version`, `proof_id`, `proof_type_registry_version`, `proof_type_registry_content_sha256`, `proof_type`, `request_content_sha256`, `fixture_set_id`, `fixture_id`, `fixture_content_sha256`, `synthetic_order_identity`, `order_mapping_version`, `order_mapping_content_sha256`, `requested_order_number`, `observed_order_number`, `observed_identity_fact_content_sha256`, `source_revision_before`, `source_revision_after`, `extractor_version`, `extractor_content_sha256`, `source_ref_registry_version`, `source_ref_registry_content_sha256`, `required_section_result_hashes`, `line_manifest_schema_version`, `line_manifest_content_sha256`, `declared_relevant_line_count`, `captured_relevant_line_count`, `source_observed_at`, `proof_source_ref`, `proof_content_sha256`.

Required-section hashes are an exact five-member array in the adapter section order. `proof_source_ref` is `OfflineFakeOASourceRefV1` with `object_id = "SYN-DOI-PROOF-" + ASCII_UPPERCASE(proof_id)`, where `proof_id` is all 64 lowercase hexadecimal characters; `section=WHOLE_ORDER_PROOF`, its line key is null, and its content hash equals `proof_content_sha256`. No truncation, alias, alternate object ID, or second natural key is conforming. To avoid recursion, proof hashing substitutes this exact SourceRef with its content hash member set to 64 lowercase zeroes, then the stored reference receives the finished proof hash.

Proof ID is:

```text
SHA256(
  UTF8("doi-whole-order-completeness-proof-id/r01-v1\n") ||
  UTF8(RFC8785({
    fixture_id,
    fixture_content_sha256,
    requested_order_number,
    extractor_content_sha256,
    source_revision_before,
    line_manifest_content_sha256
  }))
)
```

`proof_content_sha256` uses domain `doi-whole-order-completeness-proof/r01-v1\n` over the complete proof except itself, with the zero-hash SourceRef substitution above. Exact replay returns the same proof; same proof ID with different canonical bytes is an integrity conflict.

Every proof member is required and non-null except the nested `proof_source_ref.line_key`, which is required as literal null. Counts are nonnegative JSON integers; requested/observed OrderNumber values are canonical strings; `source_observed_at` is `doi-timestamp/r01-v1`; hashes/proof ID are 64 lowercase hex; `required_section_result_hashes` is an exact five-hash array in `ORDER_IDENTITY, ORDER_FACTS, LINE_ITEMS, WWC_FINDING, DEDUPE_FINDING` order. Missing, extra, null-in-required, unknown-version or wrong-domain members reject.

## Completeness success/failure result

`WholeOrderCompletenessResultV1` version `doi-whole-order-completeness-result/r01-v1` has exactly `completeness_result_schema_version`, `result_kind`, `proof`, `failure`, `completeness_result_content_sha256`. `COMPLETE` requires a complete non-null proof and null failure; `INCOMPLETE` requires null proof and a non-null `WholeOrderCompletenessFailureV1`. Hash domain is `doi-whole-order-completeness-result/r01-v1\n` over the result without its hash.

The failure has exactly `failure_schema_version`, `failure_code`, `cause_error_code`, `fixture_id`, `line_manifest_content_sha256`, `failure_content_sha256`. Its version is `doi-whole-order-completeness-failure/r01-v1`; domain is that literal plus `\n`. Closed codes are `ADAPTER_READ_FAILED`, `SECTION_INCOMPLETE`, `LINE_UNIVERSE_INCOMPLETE`, `BINDING_MISMATCH`, `SOURCE_CHANGED`, `MANIFEST_HASH_MISMATCH`, `PROOF_SOURCE_REF_UNRESOLVED`, and `SNAPSHOT_GATE_MISMATCH`. `cause_error_code` is null only when no adapter error exists; fixture/manifest locators are null only before they can be resolved. No failure appends a proof, snapshot or evaluation. Canonical and negative vectors publish literal result objects for both branches.

Failure routing is ordered and first-match-only. An adapter ERROR is always routed first by the exhaustive map below and stops further proof/gate processing. After adapter success, precedence is: manifest canonical/hash mismatch; proof/binding mismatch; two-read source change; proof SourceRef resolution; required-section completeness; line-universe coherence; snapshot gate. Unknown codes or no matching authorized failure reject rather than inventing an INCOMPLETE result. The identical machine-readable table is in `R01_NEGATIVE_VECTORS.json#/whole_order_completeness_failure_routing`.

| Adapter error code | Completeness failure code |
|---|---|
| `FIXTURE_NOT_FOUND` | `ADAPTER_READ_FAILED` |
| `REQUESTED_ORDER_IDENTITY_MISMATCH` | `BINDING_MISMATCH` |
| `MISSING_ORDER_IDENTITY` | `BINDING_MISMATCH` |
| `UNREADABLE_REQUIRED_SECTION` | `SECTION_INCOMPLETE` |
| `MALFORMED_FIXTURE` | `ADAPTER_READ_FAILED` |
| `DUPLICATE_LINE_IDENTITY` | `LINE_UNIVERSE_INCOMPLETE` |
| `INCONSISTENT_DECLARED_LINE_COUNT` | `LINE_UNIVERSE_INCOMPLETE` |
| `INCOMPLETE_LINE_UNIVERSE` | `LINE_UNIVERSE_INCOMPLETE` |
| `UNSUPPORTED_SCHEMA_VERSION` | `ADAPTER_READ_FAILED` |
| `PROHIBITED_CAPABILITY_INJECTED` | `ADAPTER_READ_FAILED` |
| `FIXTURE_CONTENT_HASH_MISMATCH` | `BINDING_MISMATCH` |
| `SOURCE_CHANGED_DURING_EXTRACTION` | `SOURCE_CHANGED` |
| `LINE_MANIFEST_HASH_MISMATCH` | `MANIFEST_HASH_MISMATCH` |

After adapter success, manifest mismatches route to `MANIFEST_HASH_MISMATCH`; fixture/order/request/extractor/mapping/registry/version/hash binding mismatches route to `BINDING_MISMATCH`; source revision/hash changes route to `SOURCE_CHANGED`; a missing, natural-key-mismatched, byte-mismatched, or content-hash-mismatched proof SourceRef target routes to `PROOF_SOURCE_REF_UNRESOLVED`; a non-COMPLETE required section routes to `SECTION_INCOMPLETE`; line count/key/relevant-projection mismatches route to `LINE_UNIVERSE_INCOMPLETE`; and missing/extra relevant snapshots or any excluded-line snapshot routes to `SNAPSHOT_GATE_MISMATCH`. Proof-stage failures have `cause_error_code=null`; adapter-routed failures preserve the exact adapter code. Literal vectors cover every failure code, including unreadable/hidden, identity/stale/source-change, missing/tampered proof reference, and missing/extra/excluded snapshot gates.

## Coherence predicate

A proof exists iff all clauses are true:

```text
recognized exact request/fixture/extractor/mapping/proof/source-ref versions and hashes
AND request expected fixture hash = admitted fixture hash
AND requested mapping resolves one exact OrderNumber
AND observed identity fact = requested OrderNumber
AND all five required sections are COMPLETE
AND source revision before = after = every section and line revision
AND fixture hash before = after = admitted final fixture hash
AND line IDs are unique
AND declared total = inventory cardinality = observed line-result cardinality
AND inventory key set = line-result key set
AND declared relevant = relevant inventory projection cardinality
AND observed relevant = relevant line-result projection cardinality
AND declared relevant = observed relevant
AND every required order/relevant-line fact satisfies its observation partition
AND section, line-result and line-manifest hashes resolve byte-exactly
```

Hidden, unreadable, filtered or pagination-incomplete input cannot produce a proof. Reordering source line input leaves sorted manifest/proof bytes unchanged. A supplied manifest hash mismatch is `LINE_MANIFEST_HASH_MISMATCH`; it is not caused by harmless reordering.

## Snapshot gate

A successful `DOIOrderSnapshot` is constructible only when the exact proof and proof SourceRef resolve, and:

```text
set(proof relevant fixture_line_id)
  = set(created line snapshot within_snapshot_line_key)
declared_relevant_line_count
  = captured_relevant_line_count
  = relevant manifest cardinality
created snapshots for EXCLUDED_NON_MERCHANDISE = 0
```

Every created line snapshot binds the exact source line-result hash. A mismatch, missing proof target, extra/missing line snapshot, or excluded-line snapshot rejects the entire snapshot/evaluation append. R07 still owns final independent snapshot/line known-answer hashes; R01 owns and publishes the intermediate fixture/result/manifest/proof hashes.

Canonical vectors cover multi-line, zero relevant, reordered-equivalent, repeated product identity, ambiguous split/merge continuity, UNKNOWN availability/DS/ETA, and failed-then-complete recheck. Negatives cover all adapter/proof errors, missing/duplicate lines, tampered manifest hash, stale fixture, source change, unreadable/hidden/filtered/paginated sections, and identity mismatch.
