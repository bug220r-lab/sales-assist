# Milestone 1 fixture-envelope hash preimages

This is the explicit known-answer table for every neutral Milestone 1 hash-bearing fixture
binding. Each preimage is exactly the ASCII domain, one `0A` byte, and the UTF-8 canonical JSON
shown below. There is no trailing line feed. The executable oracle is
`SharedRecordTests.test_every_envelope_has_a_pinned_hash_preimage_oracle`.

| Binding fixture | Domain | Expected SHA-256 |
|---|---|---|
| SourceRef | `shared-source-ref/v1` | `d2cdc91b11245c5d174e6ffb1d0e1a4dca0fcf2c7b482921ceec082a46cae581` |
| EvidenceRef | `shared-evidence-ref/v1` | `731db1044c2ef9c46451b118c7e9adcaf41e695eef3095f19dc40c46c7c1c97b` |
| ProcessingRunIdentity | `shared-processing-run-identity/v1` | `901d01972b3b537b46c1275c4f1eab822ff23e4bd07f54da6f65e257391a4c3b` |
| RequiredSection:ORDER_IDENTITY | `shared-required-section-proof/v1` | `6356dd0632a30c5d67f38a179b33e3f43d20ad2fc78dce6830bbbfc04fc9b20b` |
| RequiredSection:ORDER_FACTS | `shared-required-section-proof/v1` | `c796fbefad1298f0682b817200d899c41cb96a74423d02a56011993b3ebd2f5b` |
| RequiredSection:LINE_ITEMS | `shared-required-section-proof/v1` | `e3a131312b60c9f6449875bedd4f3422c2c452682f4e696b8dea68dad559099f` |
| RequiredSection:WWC_FINDING | `shared-required-section-proof/v1` | `ffc3a776d61fa6285a7b744e73d629500e5a8ef413ec3c6ced193ec3b72fbac9` |
| RequiredSection:DEDUPE_FINDING | `shared-required-section-proof/v1` | `b1eab1efd04245d36710f32be485705f7eefaa10e8e0e199585361038c893b59` |
| LineManifest | `shared-snapshot-line-manifest/v1` | `7b5e8d3729e55492807ec9f7f4b30bf88539d42a2f322a5ed83f13ca94e9e5d3` |
| WholeOrderCompletenessProof | `shared-snapshot-completeness-proof/v1` | `98a0057b5b5035328760d4ea9117ba81fa0a3ead5ba181d8523abc2b29c2d752` |
| SnapshotEnvelope | `shared-snapshot-envelope/v1` | `fe845e57d14230d33a14fe1b07e3ffeb8cf0c2ac18f18ca2b87ec2be07b62809` |
| EvaluationDimension:SUPPLIED_FACTS | `shared-evaluation-supplied-facts/v1` | `ba3f9349f67ae78d935f2b7d4c098b60597854a5e1c6d25a2842fc9c06e75285` |
| EvaluationDimension:RULES_EVALUATED | `shared-evaluation-rules-evaluated/v1` | `720beefe28586d4b33c302623687adc3a2d934f938844d067142fdf092f88d58` |
| EvaluationDimension:RULES_FIRED | `shared-evaluation-rules-fired/v1` | `5bfe30f3e569cd4b83715f9391e0791190bd7a73fcc9d18208b59bd6c3e6f936` |
| EvaluationDimension:RESULT | `shared-evaluation-result/v1` | `1cfd6ad7295ee202bad9557382769bbc622b7bb76d0beee5df3a71e18fe6b6d9` |
| EvaluationDimension:PERSISTENCE_EFFECTS | `shared-evaluation-persistence-effects/v1` | `21e7f150c8c06f266b319044b9bad54e1ca268ad28192e472d40a9969d27216e` |
| EvaluationEnvelope | `shared-evaluation-envelope/v1` | `b29920a75deea81054acc654d63d922418c675bde038de36364caf69b0229a23` |
| ImmutableEventEnvelope | `shared-immutable-event-envelope/v1` | `fa589e3a849cdc55b70f50205bdda6a8ad7be6860c9b618102d99c673896458d` |

## Exact preimages

The visible newline after each domain is the single required separator. Line wrapping by a
Markdown renderer is presentation only and is not part of the preimage.

### SourceRef

```text
shared-source-ref/v1
{"content":{"domain":"shared-source-content/v1","sha256":"a2c426d5213f89ed929eb6ca71f068d24a2dde500a750f97dc0f76cfc8e8550c"},"object_id":"SYN-ORDER-SHARED-0001","object_namespace":"SYNTHETIC_ORDER","schema":{"component":"source","version":"shared-source/v1"},"source_kind":"SYNTHETIC_ORDER_FIXTURE","source_ref_id":"SYN-EVIDENCE-SOURCE-0001"}
```

### EvidenceRef

```text
shared-evidence-ref/v1
{"content":{"domain":"shared-evidence-content/v1","sha256":"f708c4d5e66be20bf70664fc865ca1bdaf557603004833e982addc07ab9913c9"},"evidence_id":"SYN-EVIDENCE-ITEM-0001","schema":{"component":"evidence","version":"shared-evidence/v1"},"source":{"content":{"domain":"shared-source-content/v1","sha256":"a2c426d5213f89ed929eb6ca71f068d24a2dde500a750f97dc0f76cfc8e8550c"},"object_id":"SYN-ORDER-SHARED-0001","object_namespace":"SYNTHETIC_ORDER","schema":{"component":"source","version":"shared-source/v1"},"source_kind":"SYNTHETIC_ORDER_FIXTURE","source_ref_id":"SYN-EVIDENCE-SOURCE-0001"}}
```

### ProcessingRunIdentity

```text
shared-processing-run-identity/v1
{"request":{"domain":"shared-run-request/v1","sha256":"cb00aefa7c381980627226c8df34962d78ccb24eec980784337d11b3713f8706"},"run_id":"SYN-RUN-SHARED-0001","schema":{"component":"run","version":"shared-run/v1"}}
```

### RequiredSection:ORDER_IDENTITY

```text
shared-required-section-proof/v1
{"collapsed_regions_exhausted":true,"exhaustion_strategy":{"component":"section_exhaustion","version":"shared-section-exhaustion/v1"},"hidden_regions_exhausted":true,"observed_at":"2026-08-10T12:34:56.12Z","paginated_regions_exhausted":true,"readable":true,"schema":{"component":"required_section","version":"shared-required-section/v1"},"section":"ORDER_IDENTITY","source":{"domain":"shared-source-ref/v1","sha256":"d2cdc91b11245c5d174e6ffb1d0e1a4dca0fcf2c7b482921ceec082a46cae581"},"source_ref_id":"SYN-EVIDENCE-SOURCE-0001"}
```

### RequiredSection:ORDER_FACTS

```text
shared-required-section-proof/v1
{"collapsed_regions_exhausted":true,"exhaustion_strategy":{"component":"section_exhaustion","version":"shared-section-exhaustion/v1"},"hidden_regions_exhausted":true,"observed_at":"2026-08-10T12:34:56.12Z","paginated_regions_exhausted":true,"readable":true,"schema":{"component":"required_section","version":"shared-required-section/v1"},"section":"ORDER_FACTS","source":{"domain":"shared-source-ref/v1","sha256":"d2cdc91b11245c5d174e6ffb1d0e1a4dca0fcf2c7b482921ceec082a46cae581"},"source_ref_id":"SYN-EVIDENCE-SOURCE-0001"}
```

### RequiredSection:LINE_ITEMS

```text
shared-required-section-proof/v1
{"collapsed_regions_exhausted":true,"exhaustion_strategy":{"component":"section_exhaustion","version":"shared-section-exhaustion/v1"},"hidden_regions_exhausted":true,"observed_at":"2026-08-10T12:34:56.12Z","paginated_regions_exhausted":true,"readable":true,"schema":{"component":"required_section","version":"shared-required-section/v1"},"section":"LINE_ITEMS","source":{"domain":"shared-source-ref/v1","sha256":"d2cdc91b11245c5d174e6ffb1d0e1a4dca0fcf2c7b482921ceec082a46cae581"},"source_ref_id":"SYN-EVIDENCE-SOURCE-0001"}
```

### RequiredSection:WWC_FINDING

```text
shared-required-section-proof/v1
{"collapsed_regions_exhausted":true,"exhaustion_strategy":{"component":"section_exhaustion","version":"shared-section-exhaustion/v1"},"hidden_regions_exhausted":true,"observed_at":"2026-08-10T12:34:56.12Z","paginated_regions_exhausted":true,"readable":true,"schema":{"component":"required_section","version":"shared-required-section/v1"},"section":"WWC_FINDING","source":{"domain":"shared-source-ref/v1","sha256":"d2cdc91b11245c5d174e6ffb1d0e1a4dca0fcf2c7b482921ceec082a46cae581"},"source_ref_id":"SYN-EVIDENCE-SOURCE-0001"}
```

### RequiredSection:DEDUPE_FINDING

```text
shared-required-section-proof/v1
{"collapsed_regions_exhausted":true,"exhaustion_strategy":{"component":"section_exhaustion","version":"shared-section-exhaustion/v1"},"hidden_regions_exhausted":true,"observed_at":"2026-08-10T12:34:56.12Z","paginated_regions_exhausted":true,"readable":true,"schema":{"component":"required_section","version":"shared-required-section/v1"},"section":"DEDUPE_FINDING","source":{"domain":"shared-source-ref/v1","sha256":"d2cdc91b11245c5d174e6ffb1d0e1a4dca0fcf2c7b482921ceec082a46cae581"},"source_ref_id":"SYN-EVIDENCE-SOURCE-0001"}
```

### LineManifest

```text
shared-snapshot-line-manifest/v1
{"entries":[{"content":{"domain":"shared-snapshot-line-content/v1","sha256":"905ad3b980ef8e8fe68a42963b7c5b8797b21ed01ce860c40059738de1193d65"},"line_id":"SYN-EVIDENCE-LINE-0001","ordinal":1,"source_ref_id":"SYN-EVIDENCE-SOURCE-0001"}],"schema_version":"shared-snapshot-line-manifest/v1"}
```

### WholeOrderCompletenessProof

```text
shared-snapshot-completeness-proof/v1
{"change_detection_state":"UNCHANGED","coherence_state":"COHERENT","declared_relevant_line_count":1,"duplicate_rule":{"component":"duplicate_rule","version":"shared-duplicate-rule/v1"},"empty_universe_proved":false,"extractor":{"component":"extractor","version":"shared-extractor/v1"},"fixture":{"component":"fixture","version":"shared-fixture/v1"},"line_manifest":[{"content":{"domain":"shared-snapshot-line-content/v1","sha256":"905ad3b980ef8e8fe68a42963b7c5b8797b21ed01ce860c40059738de1193d65"},"line_id":"SYN-EVIDENCE-LINE-0001","ordinal":1,"source_ref_id":"SYN-EVIDENCE-SOURCE-0001"}],"line_manifest_binding":{"domain":"shared-snapshot-line-manifest/v1","sha256":"7b5e8d3729e55492807ec9f7f4b30bf88539d42a2f322a5ed83f13ca94e9e5d3"},"observed_order_id":"SYN-ORDER-SHARED-0001","observed_relevant_line_count":1,"order_source_observed_at":"2026-08-10T12:34:56.12Z","proof_source_observed_at":"2026-08-10T12:34:56.12Z","reordering_rule":{"component":"reordering_rule","version":"shared-reordering-rule/v1"},"requested_order_id":"SYN-ORDER-SHARED-0001","required_section_bindings":[{"domain":"shared-required-section-proof/v1","sha256":"6356dd0632a30c5d67f38a179b33e3f43d20ad2fc78dce6830bbbfc04fc9b20b"},{"domain":"shared-required-section-proof/v1","sha256":"c796fbefad1298f0682b817200d899c41cb96a74423d02a56011993b3ebd2f5b"},{"domain":"shared-required-section-proof/v1","sha256":"e3a131312b60c9f6449875bedd4f3422c2c452682f4e696b8dea68dad559099f"},{"domain":"shared-required-section-proof/v1","sha256":"ffc3a776d61fa6285a7b744e73d629500e5a8ef413ec3c6ced193ec3b72fbac9"},{"domain":"shared-required-section-proof/v1","sha256":"b1eab1efd04245d36710f32be485705f7eefaa10e8e0e199585361038c893b59"}],"required_sections":["ORDER_IDENTITY","ORDER_FACTS","LINE_ITEMS","WWC_FINDING","DEDUPE_FINDING"],"schema":{"component":"whole_order_completeness","version":"shared-whole-order-completeness/v1"},"section_proofs":[{"collapsed_regions_exhausted":true,"exhaustion_strategy":{"component":"section_exhaustion","version":"shared-section-exhaustion/v1"},"hidden_regions_exhausted":true,"observed_at":"2026-08-10T12:34:56.12Z","paginated_regions_exhausted":true,"readable":true,"schema":{"component":"required_section","version":"shared-required-section/v1"},"section":"ORDER_IDENTITY","source":{"domain":"shared-source-ref/v1","sha256":"d2cdc91b11245c5d174e6ffb1d0e1a4dca0fcf2c7b482921ceec082a46cae581"},"source_ref_id":"SYN-EVIDENCE-SOURCE-0001"},{"collapsed_regions_exhausted":true,"exhaustion_strategy":{"component":"section_exhaustion","version":"shared-section-exhaustion/v1"},"hidden_regions_exhausted":true,"observed_at":"2026-08-10T12:34:56.12Z","paginated_regions_exhausted":true,"readable":true,"schema":{"component":"required_section","version":"shared-required-section/v1"},"section":"ORDER_FACTS","source":{"domain":"shared-source-ref/v1","sha256":"d2cdc91b11245c5d174e6ffb1d0e1a4dca0fcf2c7b482921ceec082a46cae581"},"source_ref_id":"SYN-EVIDENCE-SOURCE-0001"},{"collapsed_regions_exhausted":true,"exhaustion_strategy":{"component":"section_exhaustion","version":"shared-section-exhaustion/v1"},"hidden_regions_exhausted":true,"observed_at":"2026-08-10T12:34:56.12Z","paginated_regions_exhausted":true,"readable":true,"schema":{"component":"required_section","version":"shared-required-section/v1"},"section":"LINE_ITEMS","source":{"domain":"shared-source-ref/v1","sha256":"d2cdc91b11245c5d174e6ffb1d0e1a4dca0fcf2c7b482921ceec082a46cae581"},"source_ref_id":"SYN-EVIDENCE-SOURCE-0001"},{"collapsed_regions_exhausted":true,"exhaustion_strategy":{"component":"section_exhaustion","version":"shared-section-exhaustion/v1"},"hidden_regions_exhausted":true,"observed_at":"2026-08-10T12:34:56.12Z","paginated_regions_exhausted":true,"readable":true,"schema":{"component":"required_section","version":"shared-required-section/v1"},"section":"WWC_FINDING","source":{"domain":"shared-source-ref/v1","sha256":"d2cdc91b11245c5d174e6ffb1d0e1a4dca0fcf2c7b482921ceec082a46cae581"},"source_ref_id":"SYN-EVIDENCE-SOURCE-0001"},{"collapsed_regions_exhausted":true,"exhaustion_strategy":{"component":"section_exhaustion","version":"shared-section-exhaustion/v1"},"hidden_regions_exhausted":true,"observed_at":"2026-08-10T12:34:56.12Z","paginated_regions_exhausted":true,"readable":true,"schema":{"component":"required_section","version":"shared-required-section/v1"},"section":"DEDUPE_FINDING","source":{"domain":"shared-source-ref/v1","sha256":"d2cdc91b11245c5d174e6ffb1d0e1a4dca0fcf2c7b482921ceec082a46cae581"},"source_ref_id":"SYN-EVIDENCE-SOURCE-0001"}],"source_refs":[{"content":{"domain":"shared-source-content/v1","sha256":"a2c426d5213f89ed929eb6ca71f068d24a2dde500a750f97dc0f76cfc8e8550c"},"object_id":"SYN-ORDER-SHARED-0001","object_namespace":"SYNTHETIC_ORDER","schema":{"component":"source","version":"shared-source/v1"},"source_kind":"SYNTHETIC_ORDER_FIXTURE","source_ref_id":"SYN-EVIDENCE-SOURCE-0001"}]}
```

### SnapshotEnvelope

```text
shared-snapshot-envelope/v1
{"completeness_proof":{"domain":"shared-snapshot-completeness-proof/v1","sha256":"98a0057b5b5035328760d4ea9117ba81fa0a3ead5ba181d8523abc2b29c2d752"},"payload":{"domain":"shared-snapshot-payload/v1","sha256":"8c2f35a22b5d33cad6304ec92404bdd7638c369029981a47ddda025d3fa1460a"},"run_id":"SYN-RUN-SHARED-0001","schema":{"component":"snapshot","version":"shared-snapshot/v1"},"snapshot_id":"SYN-SNAPSHOT-SHARED-0001","source_refs":[{"content":{"domain":"shared-source-content/v1","sha256":"a2c426d5213f89ed929eb6ca71f068d24a2dde500a750f97dc0f76cfc8e8550c"},"object_id":"SYN-ORDER-SHARED-0001","object_namespace":"SYNTHETIC_ORDER","schema":{"component":"source","version":"shared-source/v1"},"source_kind":"SYNTHETIC_ORDER_FIXTURE","source_ref_id":"SYN-EVIDENCE-SOURCE-0001"}]}
```

### EvaluationDimension:SUPPLIED_FACTS

```text
shared-evaluation-supplied-facts/v1
{"explicitly_empty":false,"items":[{"content":{"domain":"shared-evaluation-supplied-fact-content/v1","sha256":"d11133ab77ccdca4d931ae23dc08618840229f70ad58188b2571fdc802cb3b11"},"item_id":"SYN-EVIDENCE-EVAL-FACT-0001","role":"SUPPLIED_FACTS","schema":{"component":"supplied_fact","version":"shared-evaluation-supplied-fact-item/v1"}}],"role":"SUPPLIED_FACTS","schema":{"component":"supplied_facts","version":"shared-evaluation-supplied-facts/v1"}}
```

### EvaluationDimension:RULES_EVALUATED

```text
shared-evaluation-rules-evaluated/v1
{"explicitly_empty":false,"items":[{"content":{"domain":"shared-evaluation-rule-evaluated-content/v1","sha256":"f9d713f8cb17afe801a443ffdb823b67e36933e60cd09ab2a132d6f08d5500a3"},"item_id":"SYN-EVIDENCE-EVAL-RULE-0001","role":"RULES_EVALUATED","schema":{"component":"rule_evaluated","version":"shared-evaluation-rule-evaluated-item/v1"}}],"role":"RULES_EVALUATED","schema":{"component":"rules_evaluated","version":"shared-evaluation-rules-evaluated/v1"}}
```

### EvaluationDimension:RULES_FIRED

```text
shared-evaluation-rules-fired/v1
{"explicitly_empty":true,"items":[],"role":"RULES_FIRED","schema":{"component":"rules_fired","version":"shared-evaluation-rules-fired/v1"}}
```

### EvaluationDimension:RESULT

```text
shared-evaluation-result/v1
{"explicitly_empty":false,"items":[{"content":{"domain":"shared-evaluation-result-content/v1","sha256":"af1c15ee0f717e6577416893d27f0cecf0e74dd8381dda8f89c0d0158be2cdd5"},"item_id":"SYN-EVIDENCE-EVAL-RESULT-0001","role":"RESULT","schema":{"component":"result_item","version":"shared-evaluation-result-item/v1"}}],"role":"RESULT","schema":{"component":"result","version":"shared-evaluation-result/v1"}}
```

### EvaluationDimension:PERSISTENCE_EFFECTS

```text
shared-evaluation-persistence-effects/v1
{"explicitly_empty":true,"items":[],"role":"PERSISTENCE_EFFECTS","schema":{"component":"persistence_effects","version":"shared-evaluation-persistence-effects/v1"}}
```

### EvaluationEnvelope

```text
shared-evaluation-envelope/v1
{"evaluation_id":"SYN-EVALUATION-SHARED-0001","human_review":{"reasons":[{"code":"RC-001","label":"SOURCE_TAB_CONFIRMATION_REQUIRED","registry_version":"synthetic-doi-reason-registry/v1.0.1"}],"required":true},"persistence_effects":{"explicitly_empty":true,"items":[],"role":"PERSISTENCE_EFFECTS","schema":{"component":"persistence_effects","version":"shared-evaluation-persistence-effects/v1"}},"reasons":[{"code":"RC-001","label":"SOURCE_TAB_CONFIRMATION_REQUIRED","registry_version":"synthetic-doi-reason-registry/v1.0.1"}],"result":{"explicitly_empty":false,"items":[{"content":{"domain":"shared-evaluation-result-content/v1","sha256":"af1c15ee0f717e6577416893d27f0cecf0e74dd8381dda8f89c0d0158be2cdd5"},"item_id":"SYN-EVIDENCE-EVAL-RESULT-0001","role":"RESULT","schema":{"component":"result_item","version":"shared-evaluation-result-item/v1"}}],"role":"RESULT","schema":{"component":"result","version":"shared-evaluation-result/v1"}},"rule_pack":{"component":"rule_pack","version":"shared-rule-pack/v1"},"rules_evaluated":{"explicitly_empty":false,"items":[{"content":{"domain":"shared-evaluation-rule-evaluated-content/v1","sha256":"f9d713f8cb17afe801a443ffdb823b67e36933e60cd09ab2a132d6f08d5500a3"},"item_id":"SYN-EVIDENCE-EVAL-RULE-0001","role":"RULES_EVALUATED","schema":{"component":"rule_evaluated","version":"shared-evaluation-rule-evaluated-item/v1"}}],"role":"RULES_EVALUATED","schema":{"component":"rules_evaluated","version":"shared-evaluation-rules-evaluated/v1"}},"rules_fired":{"explicitly_empty":true,"items":[],"role":"RULES_FIRED","schema":{"component":"rules_fired","version":"shared-evaluation-rules-fired/v1"}},"run_id":"SYN-RUN-SHARED-0001","schema":{"component":"evaluation","version":"shared-evaluation/v1"},"snapshot_id":"SYN-SNAPSHOT-SHARED-0001","supplied_facts":{"explicitly_empty":false,"items":[{"content":{"domain":"shared-evaluation-supplied-fact-content/v1","sha256":"d11133ab77ccdca4d931ae23dc08618840229f70ad58188b2571fdc802cb3b11"},"item_id":"SYN-EVIDENCE-EVAL-FACT-0001","role":"SUPPLIED_FACTS","schema":{"component":"supplied_fact","version":"shared-evaluation-supplied-fact-item/v1"}}],"role":"SUPPLIED_FACTS","schema":{"component":"supplied_facts","version":"shared-evaluation-supplied-facts/v1"}}}
```

### ImmutableEventEnvelope

```text
shared-immutable-event-envelope/v1
{"event_id":"SYN-INTERACTION-EVENT-0001","event_kind":"SHARED_RECORD_ACCEPTED","occurred_at":"2026-08-10T12:34:56.12Z","payload":{"domain":"shared-event-payload/v1","sha256":"7181294b7ced82a17e3f8650f29474b32185a3e9dda5faf97691ab5cc77ff6b2"},"run_id":"SYN-RUN-SHARED-0001","schema":{"component":"event","version":"shared-event/v1"},"versions":[{"component":"snapshot","version":"shared-snapshot/v1"}]}
```
