# Milestone 2 Sales Credit hash preimages

This is the explicit known-answer table for the frozen eight-domain inventory
returned by `milestone2_hash_fixtures()`. Each preimage is exactly the ASCII
domain, one `0A` byte, and the UTF-8 canonical JSON shown below. There is no
trailing line feed. The executable oracles are
`Milestone2HashPreimageTests.test_frozen_eight_domain_inventory_and_independent_sha256`
and `Milestone2HashPreimageTests.test_published_preimage_document_has_no_drift`.

| Binding fixture | Domain | Expected SHA-256 |
|---|---|---|
| CaseMutation | `sales-credit-case-command/v1` | `e582935828dec5c895b34491a0e7d9522b4da660971a31f13f7b2450b45d0162` |
| ClosedAuditRecord | `sales-credit-closed-audit/v1` | `866a63d7bd62e197cbbb975b4588a49442501004a8060004eeafcc49c27df595` |
| EvidenceIdentifierRef | `sales-credit-search-identifier-ref/v1` | `0dfd4b0b870b3de1b6cc58b097ed4690de0c0ece1794ff9ea57bcfd00b332b4c` |
| LineItemContent | `sales-credit-line-content/v1` | `d619d96b3217fd1ce7ab48e81572108aeb5b36d17a173ea90639bcb2ec4e53c5` |
| ManagerOutcome | `sales-credit-manager-outcome/v1` | `b496954b4fa507ea7305c468f55b8dcb225a692d95c9e9b303f03fb1410363d9` |
| NoOrderClosedAuditRecord | `sales-credit-no-order-closed-audit/v1` | `76e433cc36bafc21b6c0128445afde4c8f41a17d53bcde3d1c853d2b6d0004a3` |
| OrderProvenance | `sales-credit-order-provenance/v1` | `84d0fbe12d6ea55c0020f36367e22dd934b8137d926546c5bc2c02571380ca5d` |
| SalesCreditEvaluation | `sales-credit-evaluation/v1` | `a60023ba5f0e6867f5d9876aaa8f5bc2b3f9be9cab41457f24343b4394dd1708` |

## Exact preimages

The visible newline after each domain is the single required separator.
Every canonical JSON value occupies exactly one line.

### CaseMutation

```text
sales-credit-case-command/v1
{"active_note":null,"command_id":"SYN-EVIDENCE-M2-COMMAND-0001","discovery_run":{"adapter":{"component":"sales_credit_search_adapter","version":"sales-credit-search-adapter/v1"},"completed_at":"2026-08-21T16:30:00Z","force_explanation":null,"interaction_ids":["SYN-INTERACTION-M2-KAT-0001"],"native_result_sets":[{"completeness":"COMPLETE","identifier":{"kind":"EMAIL","value":"m2-kat@example.test"},"order_ids":["SYN-ORDER-M2-KAT-0001"]}],"run_id":"SYN-RUN-M2-KAT-0001","schema_version":"sales-credit-order-search-run/v1","started_at":"2026-08-21T16:15:00Z","trigger":"NORMAL","warnings":[]},"evaluation":{"attribution":{"classification":"TARGET_REP","raw_order_rep_present":true},"evaluation_id":"SYN-EVALUATION-M2-KAT-0001","human_review_required":false,"order_id":"SYN-ORDER-M2-KAT-0001","persistence_effects":["ACTIVE_CASE_CLASSIFICATION","NO_PERSISTENCE_MILESTONE_2"],"reasons":["PLACED_VALUE_PROVED","TARGET_REP"],"replacement":{"candidate_results":[],"customer_continuity":"UNKNOWN","enumeration_complete":false,"product_continuity":"UNKNOWN","search_run_id":null,"status":"NOT_APPLICABLE"},"rule_pack_version":"synthetic-sales-credit-rules/v1","rules_evaluated":["AMBIGUITY_ROUTING","CANCELLATION","MATERIAL_CHANGE","ORDER_REP_ATTRIBUTION","ORDER_WINDOW","PLACED_VALUE","REPLACEMENT","SNAPSHOT_VALIDATION"],"rules_fired":["ORDER_REP_ATTRIBUTION","ORDER_WINDOW","PLACED_VALUE","SNAPSHOT_VALIDATION"],"schema_version":"synthetic-sales-credit-domain/v1","snapshot_id":"SYN-SNAPSHOT-M2-KAT-0001","supplied_facts":["ORDER_IDENTITY","ORDER_LIFECYCLE","ORDER_REP","ORDER_TIMING","ORDER_VALUE","SNAPSHOT"],"validations":["ORDER_ID_MATCHED","ORDER_TIMING_ACCEPTED","SNAPSHOT_ACCEPTED"],"value":{"active_value":{"amount":"123.45","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"material_changes":[],"placed_value":{"amount":"123.45","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"status":"PLACED_VALUE_VERIFIED"},"workflow_state":"CREDIT_CONFIRMED_TARGET_REP"},"evidence":[],"interactions":[{"active_notes":null,"corrected_at":null,"corrected_precision":null,"email":"m2-kat@example.test","interaction_id":"SYN-INTERACTION-M2-KAT-0001","last_check_at":null,"next_eligible_check_at":null,"part_request":null,"phone":null,"provenance":{"component":"sales_credit_interaction_source","version":"sales-credit-interaction-source/v1"},"recorded_at":"2026-08-20T16:00:00Z","review_window_end":"2026-09-03","review_window_start":"2026-08-20","schema_version":"synthetic-sales-credit-domain/v1","source_ref":"SYN-EVIDENCE-M2-INTERACTION-SOURCE-0001","timestamp_precision":"EXACT","vin_like_reference":null,"workflow_state":"AWAITING_SOURCE_REVIEW"}],"occurred_at":"2026-08-21T17:00:00Z","order_id":"SYN-ORDER-M2-KAT-0001","replacement_candidates":[],"replacement_run":null,"snapshots":[{"active_notes":null,"canceled_at":null,"captured_at":"2026-08-21T16:00:00Z","current_value":{"amount":"123.45","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"customer_ids":["SYN-CUSTOMER-M2-KAT-0001"],"extraction_status":"VALID","lifecycle_status":"ACTIVE","lines":[{"canonical_es_number":"123","canonical_mfg_oe_number":"AB-001 / C","content":{"domain":"sales-credit-line-content/v1","sha256":"d619d96b3217fd1ce7ab48e81572108aeb5b36d17a173ea90639bcb2ec4e53c5"},"description":null,"line_id":"SYN-EVIDENCE-M2-LINE-0001","line_value":{"amount":"25.00","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"observed_availability":null,"observed_eta":null,"quantity":"2","raw_es_number":"synthetic: ES#000123","raw_line_rep":null,"raw_mfg_oe_number":"synthetic: ab-001 / c","sku_id":"SYN-SKU-M2-KAT-0001","warnings":[]}],"material_changes":[],"notes_scan_status":"COMPLETE","order_id":"SYN-ORDER-M2-KAT-0001","parser":{"component":"sales_credit_parser","version":"sales-credit-parser/v1"},"placed_at":"2026-08-21T15:00:00Z","placed_at_precision":"EXACT","placed_value":{"amount":"123.45","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"provenance":{"domain":"sales-credit-order-provenance/v1","sha256":"84d0fbe12d6ea55c0020f36367e22dd934b8137d926546c5bc2c02571380ca5d"},"raw_order_rep":"target_rep","raw_order_status":"active","schema_version":"synthetic-sales-credit-domain/v1","snapshot_id":"SYN-SNAPSHOT-M2-KAT-0001","source_ref":"SYN-EVIDENCE-M2-ORDER-SOURCE-0001","warnings":[]}]}
```

### ClosedAuditRecord

```text
sales-credit-closed-audit/v1
{"approved_amount":{"amount":"123.45","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"attribution":"TARGET_REP","closed_at":"2026-08-22T16:00:00Z","concise_note":"HUMAN_OUTCOME_RECORDED","controlled_reason":"TARGET_REP","decision_actor":"SYN-REP-M2-MANAGER-0001","evidence_classifications":["VERIFIED_PREORDER_EVIDENCE"],"evidence_source_types":["SYNTHETIC_EMAIL"],"human_decided_at":"2026-08-22T15:55:00Z","human_outcome":"APPROVED","human_recorded_at":"2026-08-22T16:00:00Z","interaction_precisions":["EXACT"],"opened_at":"2026-08-20T16:00:00Z","order_id":"SYN-ORDER-M2-KAT-0001","order_value_status":"PLACED_VALUE_VERIFIED","reasons":["TARGET_REP"],"retention_policy_version":"sales-credit-retention-elapsed-90d/v1","rule_pack_version":"synthetic-sales-credit-rules/v1","schema_version":"synthetic-sales-credit-domain/v1","system_workflow_before_close":"CREDIT_CONFIRMED_TARGET_REP"}
```

### EvidenceIdentifierRef

```text
sales-credit-search-identifier-ref/v1
{"identifier_kind":"EMAIL","interaction_id":"SYN-INTERACTION-M2-KAT-0001"}
```

### LineItemContent

```text
sales-credit-line-content/v1
{"canonical_es_number":"123","canonical_mfg_oe_number":"AB-001 / C","description":null,"line_id":"SYN-EVIDENCE-M2-LINE-0001","line_value":{"amount":"25.00","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"observed_availability":null,"observed_eta":null,"quantity":"2","raw_es_number":"synthetic: ES#000123","raw_line_rep":null,"raw_mfg_oe_number":"synthetic: ab-001 / c","sku_id":"SYN-SKU-M2-KAT-0001","warnings":[]}
```

### ManagerOutcome

```text
sales-credit-manager-outcome/v1
{"active_note":null,"actor":"SYN-REP-M2-MANAGER-0001","approved_amount":{"amount":"123.45","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"controlled_reason":"TARGET_REP","decided_at":"2026-08-22T15:55:00Z","occurrence_id":"SYN-EVIDENCE-M2-MANAGER-0001","outcome":"APPROVED","recorded_at":"2026-08-22T16:00:00Z","schema_version":"synthetic-sales-credit-domain/v1"}
```

### NoOrderClosedAuditRecord

```text
sales-credit-no-order-closed-audit/v1
{"closed_at":"2026-08-17T16:00:00.000000001Z","concise_note":"REVIEW_WINDOW_CLOSED_NO_ORDER","enumeration_complete":true,"identifiers_attempted":2,"identifiers_completed":2,"identifiers_required":2,"interaction_count":2,"interaction_precisions":["EXACT","HISTORICAL_APPROXIMATION"],"latest_review_window_end":"2026-08-16","opened_at":"2026-08-01T14:00:00Z","reasons":["NO_ORDER_WINDOW_CLOSED"],"retention_policy_version":"sales-credit-retention-elapsed-90d/v1","rule_pack_version":"synthetic-sales-credit-rules/v1","schema_version":"sales-credit-no-order-closed-audit/v1","search_adapter_version":"sales-credit-search-adapter/v1","search_run_schema_version":"sales-credit-order-search-run/v1","search_trigger":"NORMAL","system_workflow_before_close":"REVIEW_WINDOW_CLOSED_NO_ORDER"}
```

### OrderProvenance

```text
sales-credit-order-provenance/v1
{"captured_at":"2026-08-21T16:00:00Z","parser":{"component":"sales_credit_parser","version":"sales-credit-parser/v1"},"source_ref":"SYN-EVIDENCE-M2-ORDER-SOURCE-0001"}
```

### SalesCreditEvaluation

```text
sales-credit-evaluation/v1
{"attribution":{"classification":"TARGET_REP","raw_order_rep_present":true},"evaluation_id":"SYN-EVALUATION-M2-KAT-0001","human_review_required":false,"order_id":"SYN-ORDER-M2-KAT-0001","persistence_effects":["ACTIVE_CASE_CLASSIFICATION","NO_PERSISTENCE_MILESTONE_2"],"reasons":["PLACED_VALUE_PROVED","TARGET_REP"],"replacement":{"candidate_results":[],"customer_continuity":"UNKNOWN","enumeration_complete":false,"product_continuity":"UNKNOWN","search_run_id":null,"status":"NOT_APPLICABLE"},"rule_pack_version":"synthetic-sales-credit-rules/v1","rules_evaluated":["AMBIGUITY_ROUTING","CANCELLATION","MATERIAL_CHANGE","ORDER_REP_ATTRIBUTION","ORDER_WINDOW","PLACED_VALUE","REPLACEMENT","SNAPSHOT_VALIDATION"],"rules_fired":["ORDER_REP_ATTRIBUTION","ORDER_WINDOW","PLACED_VALUE","SNAPSHOT_VALIDATION"],"schema_version":"synthetic-sales-credit-domain/v1","snapshot_id":"SYN-SNAPSHOT-M2-KAT-0001","supplied_facts":["ORDER_IDENTITY","ORDER_LIFECYCLE","ORDER_REP","ORDER_TIMING","ORDER_VALUE","SNAPSHOT"],"validations":["ORDER_ID_MATCHED","ORDER_TIMING_ACCEPTED","SNAPSHOT_ACCEPTED"],"value":{"active_value":{"amount":"123.45","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"material_changes":[],"placed_value":{"amount":"123.45","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"status":"PLACED_VALUE_VERIFIED"},"workflow_state":"CREDIT_CONFIRMED_TARGET_REP"}
```
