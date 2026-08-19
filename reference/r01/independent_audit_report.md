
> **Sanitized supporting reference.** This file is a mechanically sanitized derivative of
> source material supplied for the synthetic proof of concept. Historical status/freeze
> language is nonbinding. The curated files under `specs/` govern. No production-system
> access or real-data use is authorized by this reference.

# DOI R01 Fact Normalization & Registries Independent Audit

Audit date: 2026-08-11  
Target folder: `187MGD9M57F6yy5UMt5e8aECOJKVdt7v0`  
Target package: `doi-authority-remediation-r01-fact-normalization/v1.1`  
Audit posture: fresh, independent, adversarial, read-only  
Overall verdict: **FAIL**

## Executive conclusion

The R01 package is intact, private, checksum-correct, stable from audit start to finish, exactly bound to the v0.1.5.6 baseline, and correctly reconciled against its predecessor and the exact R02 v1 overlap evidence. All 247 published vector envelopes reproduce byte-for-byte and hash-for-hash. Whole-order proof, ISO-4217, business-calendar/tzdb, numeric count arithmetic, capability isolation, and overlap merge rules pass.

R01 is nevertheless not ready. Sixteen material authority/oracle defects remain. The mandatory blocker matrix regressed to three columns; fixture hashing has contradictory preimages; Timestamp and Quantity source admission are not fully closed; SourceRef privacy is not enforceable; one adapter-success branch has no legal downstream DEDUPE representation; OrderNumber omits source-preservation authority; UNKNOWN rows contain 204 dangling test references; finding identities/nested schemas/hash laws are incomplete; and required known-answer/mutation coverage is missing. Any material defect requires the prescribed FAIL verdict.

No input package was modified. No repository, authority cache, workbook, corpus, Synthetic Interaction Queue, Synthetic Email Source, migration, code, production order, or live Synthetic Order Portal was accessed or changed.

## Evidence and independent verification

| Evidence set | Raw result |
|---|---|
| R01 v1.1 | 31 files / 30 checksum-covered payloads; 30/30 checksum rows PASS |
| R01 `SHA256SUMS.txt` | `0567381c8ff02c6ed4f0055a5b985ae88321d6f252adf6c2ce5d66a2fe078cd9` |
| R01 authority manifest | `6f3dbe50e6a8793f75b799af5d102c57efc5c0547a9c87a6bb3a07d7eb9e6108` |
| v0.1.5.6 baseline | 47 total files / 46 manifested payloads; 46/46 PASS |
| Baseline `SHA256SUMS.txt` | `e20bbbcf1cbf6e6c3c13c3687dac6f55abcd9d739be8c194823fbaf485f3c444` |
| Baseline authority manifest | `f0430ef6fa2c72abc7989dc3cfe735e2314d42ab9b44fca9b83f093c14f441d5` |
| Original R01 predecessor | 29 files / 28 checksum-covered payloads; 28/28 PASS |
| Predecessor manifests | checksum `27536f0d635c5980383e00a78aedf8706b8bc3c5ea6f1260661147c73b3d56cd`; authority `95e911cddc50cfe240204b7079fcee8fd07d9f7c45c618d6e61a129e3ab684ff` |
| Exact R02 v1 evidence | 23 files / 22 checksum-covered payloads; 22/22 PASS |
| Forward-readiness audit | 15 files / 14 checksum-covered payloads; 14/14 PASS |

All 18 R01 baseline-entry hashes and all 18 delta hashes recompute. Direct predecessor comparison is exactly 18 changed, 11 unchanged, 2 new, and 0 removed. The package plus 31 files were private/unshared and owner-only at audit start and finish. Finish raw readback matched all 31 starting SHA-256 values and byte lengths.

## Section verdicts

| Audit section | Verdict | Independent result |
|---|---|---|
| 1. Package integrity and baseline binding | PASS | Exact inventory, paths, bytes, checksums, privacy, stability, baseline and predecessor binding; no prohibited material |
| 2. Modular-scope discipline | FAIL | Correct blocker ownership, but every ten-row closure record lacks mandatory evidence columns (`R01-D001`) |
| 3. Offline fake-OA adapter | FAIL | Capability boundary passes; hash law, source-time coherence, and downstream constructability fail (`D002`, `D003`, `D009`) |
| 4. Timestamp and Quantity | FAIL | Canonical Quantity passes; Timestamp authority and adapter Quantity source grammar are incomplete; one Timestamp digest is missing (`D004`, `D005`, `D011`) |
| 5. SourceRef/privacy | FAIL | Four variants and fingerprints reproduce; open attempt ID, unenforceable product locator privacy, and inadequate privacy negatives remain (`D006`–`D008`) |
| 6. Observed tagged values | FAIL | Core three-tag wire union/hash passes; adapter-to-DEDUPE specialization is unconstructable and specialization vectors are incomplete (`D009`, `D012`) |
| 7. UNKNOWN reasons | FAIL | 28 field mappings, 138 reasons/owners, and 115 transitions are semantically correct; 204 oracle references are undefined (`D013`) |
| 8. Whole-order proof | PASS | Closed proof authority; proof and failure-route hashes/vectors recompute; B010 remains R07-owned |
| 9. ISO-4217 | PASS | XML-derived 178-code registry, 13 no-minor-unit and 165 Money-eligible codes, hash, and vectors reproduce |
| 10. WWC/DEDUPE findings | FAIL | Presence partitions exist, but identity/nested schemas, registry hash laws, and legal PRESENT subpartition vectors are incomplete (`D014`–`D016`) |
| 11. Business calendar | PASS | Calendar/TZIF/zone-rule hashes, 2026 DST transitions, algorithms, accepted/negative vectors, and offline behavior reproduce |
| 12. Normalization | FAIL | Core normalization and R02 OrderNumber dependency hashes reproduce; OrderNumber source-preservation rule is absent (`D010`) |
| 13. Canonical/negative vectors | FAIL | 247/247 envelope byte/hash recomputations pass; required expected digest and per-domain mutation/partition coverage do not (`D008`, `D011`, `D012`, `D013`, `D016`) |
| 14. R01/R02 overlap | PASS | 12 common-artifact counterpart hashes/ownership arrays and all delta hashes match exact R02 v1; fail-closed three-way merge law is explicit |
| 15. Counts/versions/preservation | FAIL | Numeric arithmetic and unchanged payloads pass, but governing selector/reference parity fails through `D013` |
| 16. Audit-output package | PASS at delivery | Eleven required files, private folder, checksum manifest, and final raw upload readback |
| 17. Required verdict | FAIL | One or more material blockers exist; 16 are recorded |

## Positive recomputation results

- Vectors: 91 canonical + 156 negative = 247 effective cases; 247 unique effective IDs; 113 unique base IDs; 145 selector-bearing cases; zero canonical-byte or vector-hash mismatches. UTF-8 byte-length ranges are 155–255,462 and 227–33,642.
- Counts: 115 baseline reasons + 23 contiguous new reasons = 138; 138 owner rows; 115 transitions; 312 baseline + 113 R01 synthetic IDs = 425; 29 + one governed `SYN-R01` family = 30; lifecycle remains 56 kinds and 8 payload schemas.
- Whole-order proof: proof-type hash `480b91d3a1205ecc0504158b10bc851348cd2c90732289bb21522d4a3635bcad`; every tested nested fixture/result/manifest/proof hash matched.
- ISO: source XML SHA-256 `838dfb991648cf36df939edd5fe3811737962b75a32252847d239cedd1e291c9`; registry hash `4e95f5dc30767c4e1fc2d0d4f7af603621a94d3ab3f941656387326f4af302d2`; 280 rows, 277 coded, 3 uncoded, 178 unique codes, zero conflicts.
- Calendar: registry `844d225814f487716d5ae79257da3234dbd8c41f32651b5d6f1e2c5908ce4185`; TZIF `e9ed07d7bee0c76a9d442d091ef1f01668fee7c4f26014c0a868b19fe6c18a95`; zone rules `a4cd7bd7094f8ef7370522456200aeabd59f002883963086fbd2a5b0a97c457e`; both 2026 New York transitions verified.
- Registries: SourceRef `a2064de3bdc58890a5467d5451c3e709f30208333cecfa9a1e32c620fb594d02`; Observed `c45c18b5ccbf6406c99f8adbbb6dcfcb94b18f03087c9333fef1d28bb10ee59e`; Normalization `d6db114b3fcfb326509609f2d2d570935765a9adb7d279248bc35ae6a61ae7d1`; Quantity `8d021f3460545fae638ce6df4b6cfcac46f693e7c5ad7a4cfd82f252fce4a5ca`.

## Material discrepancy index

| ID | Exact primary reference | Smallest remediation |
|---|---|---|
| R01-D001 | `R01_BLOCKER_CLOSURE_MATRIX.md:5-16` | Restore/populate the complete predecessor matrix schema; regenerate and re-audit |
| R01-D002 | `R01_OFFLINE_FAKE_OA_ADAPTER_CONTRACT.md:58-77` | Publish one explicit per-object preimage law |
| R01-D003 | Adapter lines 32/47; field registry `ORDER_FACTS.source_observed_at` | Require canonical equality of both timestamp loci and add negatives |
| R01-D004 | `R01_TIMESTAMP_QUANTITY_CONTRACT.md:7-9`; extractor/manifest/overlap bindings | Publish exact hash-bound Timestamp schema and boundary vectors |
| R01-D005 | Timestamp/Quantity line 17; `DECIMAL_LEXEME` | Publish bounded source-lexeme grammar and edges |
| R01-D006 | SourceRef `#/variants/0/rules/source_import_attempt_id` | Bounded generated-ID grammar plus owner resolution |
| R01-D007 | SourceRef `#/variants/2|3/rules/source_object_id` | Bind product-only evidence schema/resolution or governed namespace |
| R01-D008 | Negative vectors `/9`, `/10`, `/65` | Grammar-valid literal canaries plus precedence |
| R01-D009 | Field registry `DEDUPE_FINDING.observed_at`; Observed `/specializations/21`; DEDUPE PRESENT | Reject unnormalizable success; add focused negative |
| R01-D010 | Normalization `#/OrderNumber` | Add/version source-preservation rule and regenerate hashes |
| R01-D011 | Canonical vectors `/2` | Add expected primitive digest and regenerate vector hash |
| R01-D012 | Both vector artifacts; Observed `#/specializations` | Complete per-domain positive/mutation suite and reconcile counts |
| R01-D013 | UNKNOWN rows/tests and ownership/oracle selectors | Resolve bare versus selector IDs; regenerate overlays/counts/hashes |
| R01-D014 | Finding schemas PRESENT descriptors/examples | Publish identity and exact nested schemas/laws; regenerate |
| R01-D015 | Finding registry/presence/descriptor digest keys | Publish normative hash domains/preimages/separators |
| R01-D016 | WWC PRESENT truth table and vector corpora | Add three legal subpartitions and focused nested negatives |

`R01_DISCREPANCIES.jsonl` contains full evidence, impact, exact references, remediation, and re-audit scope for every row.

## R01/R02 safety and dependency caveat

All 12 R01-confirmed common artifacts match exact R02 v1 baseline hashes, ownership arrays, counterpart delta hashes, and independently recomputed R02 deltas. The 13th R02 record is correctly marked R02-only. No latest-whole-file integration is permitted.

This overlap PASS is evidence-specific, not readiness. The bound R02 v1 package has `package_status = BLOCKED_PENDING_PRODUCT_DECISION_NOT_FROZEN`; any R02 successor requires refreshed overlap evidence. The R01 successor must first close all 16 discrepancies and pass independent re-audit.

## Final decision

Do not integrate, freeze, implement, or resume from the present R01 package. Create a private successor, make only the smallest authority corrections listed above, regenerate every affected byte/hash/vector/manifest/checksum, reconcile it with the then-current R02 package, and conduct a fresh independent audit.

INDEPENDENT_DOI_R01_FACT_NORMALIZATION_AUDIT = FAIL
DOI_R01_FACT_NORMALIZATION_MODULE = NOT_READY
