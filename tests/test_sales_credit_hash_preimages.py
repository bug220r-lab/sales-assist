from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import dataclass
from pathlib import Path

from synthetic_sales_assist.sales_credit.accumulator import (
    InMemorySalesCreditState,
    SearchEvaluationBatch,
)
from synthetic_sales_assist.sales_credit.discovery import (
    SelectorOwnedCandidateEvaluation,
)
from synthetic_sales_assist.sales_credit.fixtures import (
    milestone2_case_mutation,
    milestone2_hash_fixtures,
)


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class Oracle:
    name: str
    domain: str
    digest: str
    canonical_json: str


ORACLES = (
    Oracle(
        "CaseMutation",
        "sales-credit-case-command/v1",
        "e582935828dec5c895b34491a0e7d9522b4da660971a31f13f7b2450b45d0162",
        (
            '{"active_note":null,"command_id":"SYN-EVIDENCE-M2-COMMAND-0001","discovery_'
            'run":{"adapter":{"component":"sales_credit_search_adapter","version":"sales-'
            'credit-search-adapter/v1"},"completed_at":"2026-08-21T16:30:00Z","force_expl'
            'anation":null,"interaction_ids":["SYN-INTERACTION-M2-KAT-0001"],"native_resu'
            'lt_sets":[{"completeness":"COMPLETE","identifier":{"kind":"EMAIL","value"'
            ':"m2-kat@example.test"},"order_ids":["SYN-ORDER-M2-KAT-0001"]}],"run_id":"'
            'SYN-RUN-M2-KAT-0001","schema_version":"sales-credit-order-search-run/v1","st'
            'arted_at":"2026-08-21T16:15:00Z","trigger":"NORMAL","warnings":[]},"evaluati'
            'on":{"attribution":{"classification":"TARGET_REP","raw_order_rep_present":true}'
            ',"evaluation_id":"SYN-EVALUATION-M2-KAT-0001","human_review_required":false,'
            '"order_id":"SYN-ORDER-M2-KAT-0001","persistence_effects":["ACTIVE_CASE_CLASS'
            'IFICATION","NO_PERSISTENCE_MILESTONE_2"],"reasons":["PLACED_VALUE_PROVED","T'
            'ARGET_REP"],"replacement":{"candidate_results":[],"customer_continuity":"UN'
            'KNOWN","enumeration_complete":false,"product_continuity":"UNKNOWN","search_r'
            'un_id":null,"status":"NOT_APPLICABLE"},"rule_pack_version":"synthetic-sale'
            's-credit-rules/v1","rules_evaluated":["AMBIGUITY_ROUTING","CANCELLATION","MA'
            'TERIAL_CHANGE","ORDER_REP_ATTRIBUTION","ORDER_WINDOW","PLACED_VALUE","REPLAC'
            'EMENT","SNAPSHOT_VALIDATION"],"rules_fired":["ORDER_REP_ATTRIBUTION","ORDER_'
            'WINDOW","PLACED_VALUE","SNAPSHOT_VALIDATION"],"schema_version":"synthetic-sa'
            'les-credit-domain/v1","snapshot_id":"SYN-SNAPSHOT-M2-KAT-0001","supplied_fac'
            'ts":["ORDER_IDENTITY","ORDER_LIFECYCLE","ORDER_REP","ORDER_TIMING","ORDER_VA'
            'LUE","SNAPSHOT"],"validations":["ORDER_ID_MATCHED","ORDER_TIMING_ACCEPTED","'
            'SNAPSHOT_ACCEPTED"],"value":{"active_value":{"amount":"123.45","currency_cod'
            'e":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/'
            'v1","currency_scale":2},"material_changes":[],"placed_value":{"amount":"123.'
            '45","currency_code":"USD","currency_registry_version":"synthetic-iso-style-c'
            'urrency-registry/v1","currency_scale":2},"status":"PLACED_VALUE_VERIFIED"},"'
            'workflow_state":"CREDIT_CONFIRMED_TARGET_REP"},"evidence":[],"interactions":'
            '[{"active_notes":null,"corrected_at":null,"corrected_precision":null,"email"'
            ':"m2-kat@example.test","interaction_id":"SYN-INTERACTION-M2-KAT-0001","last_'
            'check_at":null,"next_eligible_check_at":null,"part_request":null,"phone":nul'
            'l,"provenance":{"component":"sales_credit_interaction_source","version":"sal'
            'es-credit-interaction-source/v1"},"recorded_at":"2026-08-20T16:00:00Z","revi'
            'ew_window_end":"2026-09-03","review_window_start":"2026-08-20","schema_versi'
            'on":"synthetic-sales-credit-domain/v1","source_ref":"SYN-EVIDENCE-M2-INTERAC'
            'TION-SOURCE-0001","timestamp_precision":"EXACT","vin_like_reference":null,"w'
            'orkflow_state":"AWAITING_SOURCE_REVIEW"}],"occurred_at":"2026-08-21T17:00:00'
            'Z","order_id":"SYN-ORDER-M2-KAT-0001","replacement_candidates":[],"replaceme'
            'nt_run":null,"snapshots":[{"active_notes":null,"canceled_at":null,"captured_'
            'at":"2026-08-21T16:00:00Z","current'
            '_value":{"amount":"123.45","currency_code":"USD","currency_registry_version"'
            ':"synthetic-iso-style-currency-registry/v1","currency_scale":2},"customer_id'
            's":["SYN-CUSTOMER-M2-KAT-0001"],"extraction_status":"VALID","lifecycle_statu'
            's":"ACTIVE","lines":[{"canonical_es_number":"123","canonical_mfg_oe_number":'
            '"AB-001 / C","content":{"domain":"sales-credit-line-content/v1","sha256":"d6'
            '19d96b3217fd1ce7ab48e81572108aeb5b36d17a173ea90639bcb2ec4e53c5"},"descriptio'
            'n":null,"line_id":"SYN-EVIDENCE-M2-LINE-0001","line_value":{"amount":"25.00"'
            ',"currency_code":"USD","currency_registry_version":"synthetic-iso-style-curr'
            'ency-registry/v1","currency_scale":2},"observed_availability":null,"observed'
            '_eta":null,"quantity":"2","raw_es_number":"synthetic: ES#000123","raw_line_r'
            'ep":null,"raw_mfg_oe_number":"synthetic: ab-001 / c","sku_id":"SYN-SKU-M2-KA'
            'T-0001","warnings":[]}],"material_changes":[],"notes_scan_status":"COMPLETE"'
            ',"order_id":"SYN-ORDER-M2-KAT-0001","parser":{"component":"sales_credit_pars'
            'er","version":"sales-credit-parser/v1"},"placed_at":"2026-08-21T15:00:00Z","'
            'placed_at_precision":"EXACT","placed_value":{"amount":"123.45","currency_cod'
            'e":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/'
            'v1","currency_scale":2},"provenance":{"domain":"sales-credit-order-provenanc'
            'e/v1","sha256":"84d0fbe12d6ea55c0020f36367e22dd934b8137d926546c5bc2c02571380'
            'ca5d"},"raw_order_rep":"target_rep","raw_order_status":"active","schema_vers'
            'ion":"synthetic-sales-credit-domain/v1","snapshot_id":"SYN-SNAPSHOT-M2-KAT-0'
            '001","source_ref":"SYN-EVIDENCE-M2-ORDER-SOURCE-0001","warnings":[]}]}'
        ),
    ),
    Oracle(
        "ClosedAuditRecord",
        "sales-credit-closed-audit/v1",
        "866a63d7bd62e197cbbb975b4588a49442501004a8060004eeafcc49c27df595",
        (
            '{"approved_amount":{"amount":"123.45","currency_code":"USD","currency_regist'
            'ry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"'
            'attribution":"TARGET_REP","closed_at":"2026-08-22T16:00:00Z","concise_note":'
            '"HUMAN_OUTCOME_RECORDED","controlled_reason":"TARGET_REP","decision_actor":"'
            'SYN-REP-M2-MANAGER-0001","evidence_classifications":["VERIFIED_PREORDER_EVID'
            'ENCE"],"evidence_source_types":["SYNTHETIC_EMAIL"],"human_decided_at":"2026-'
            '08-22T15:55:00Z","human_outcome":"APPROVED","human_recorded_at":"2026-08-22T'
            '16:00:00Z","interaction_precisions":["EXACT"],"opened_at":"2026-08-20T16:00:'
            '00Z","order_id":"SYN-ORDER-M2-KAT-0001","order_value_status":"PLACED_VALUE_V'
            'ERIFIED","reasons":["TARGET_REP"],"retention_policy_version":"sales-credit-r'
            'etention-elapsed-90d/v1","rule_pack_version":"synthetic-sales-credit-rules/v'
            '1","schema_version":"synthetic-sales-credit-domain/v1","system_workflow_befo'
            're_close":"CREDIT_CONFIRMED_TARGET_REP"}'
        ),
    ),
    Oracle(
        "EvidenceIdentifierRef",
        "sales-credit-search-identifier-ref/v1",
        "0dfd4b0b870b3de1b6cc58b097ed4690de0c0ece1794ff9ea57bcfd00b332b4c",
        (
            '{"identifier_kind":"EMAIL","interaction_id":"SYN-INTERACTION-M2-KAT-0001"}'
        ),
    ),
    Oracle(
        "LineItemContent",
        "sales-credit-line-content/v1",
        "d619d96b3217fd1ce7ab48e81572108aeb5b36d17a173ea90639bcb2ec4e53c5",
        (
            '{"canonical_es_number":"123","canonical_mfg_oe_number":"AB-001 / C","descrip'
            'tion":null,"line_id":"SYN-EVIDENCE-M2-LINE-0001","line_value":{"amount":"25.'
            '00","currency_code":"USD","currency_registry_version":"synthetic-iso-style-c'
            'urrency-registry/v1","currency_scale":2},"observed_availability":null,"obser'
            'ved_eta":null,"quantity":"2","raw_es_number":"synthetic: ES#000123","raw_lin'
            'e_rep":null,"raw_mfg_oe_number":"synthetic: ab-001 / c","sku_id":"SYN-SKU-M2'
            '-KAT-0001","warnings":[]}'
        ),
    ),
    Oracle(
        "ManagerOutcome",
        "sales-credit-manager-outcome/v1",
        "b496954b4fa507ea7305c468f55b8dcb225a692d95c9e9b303f03fb1410363d9",
        (
            '{"active_note":null,"actor":"SYN-REP-M2-MANAGER-0001","approved_amount":{"am'
            'ount":"123.45","currency_code":"USD","currency_registry_version":"synthetic-'
            'iso-style-currency-registry/v1","currency_scale":2},"controlled_reason":"TAR'
            'GET_REP","decided_at":"2026-08-22T15:55:00Z","occurrence_id":"SYN-EVIDENCE-M'
            '2-MANAGER-0001","outcome":"APPROVED","recorded_at":"2026-08-22T16:00:00Z","s'
            'chema_version":"synthetic-sales-credit-domain/v1"}'
        ),
    ),
    Oracle(
        "NoOrderClosedAuditRecord",
        "sales-credit-no-order-closed-audit/v1",
        "76e433cc36bafc21b6c0128445afde4c8f41a17d53bcde3d1c853d2b6d0004a3",
        (
            '{"closed_at":"2026-08-17T16:00:00.000000001Z","concise_note":"REVIEW_WIN'
            'DOW_CLOSED_NO_ORDER","enumeration_complete":true,"identifiers_attempted"'
            ':2,"identifiers_completed":2,"identifiers_required":2,"interaction_count'
            '":2,"interaction_precisions":["EXACT","HISTORICAL_APPROXIMATION"],"lates'
            't_review_window_end":"2026-08-16","opened_at":"2026-08-01T14:00:00Z","re'
            'asons":["NO_ORDER_WINDOW_CLOSED"],"retention_policy_version":"sales-cred'
            'it-retention-elapsed-90d/v1","rule_pack_version":"synthetic-sales-credit'
            '-rules/v1","schema_version":"sales-credit-no-order-closed-audit/v1","sea'
            'rch_adapter_version":"sales-credit-search-adapter/v1","search_run_schema'
            '_version":"sales-credit-order-search-run/v1","search_trigger":"NORMAL","'
            'system_workflow_before_close":"REVIEW_WINDOW_CLOSED_NO_ORDER"}'
        ),
    ),
    Oracle(
        "OrderProvenance",
        "sales-credit-order-provenance/v1",
        "84d0fbe12d6ea55c0020f36367e22dd934b8137d926546c5bc2c02571380ca5d",
        (
            '{"captured_at":"2026-08-21T16:00:00Z","parser":{"component":"sales_credit_pa'
            'rser","version":"sales-credit-parser/v1"},"source_ref":"SYN-EVIDENCE-M2-ORDE'
            'R-SOURCE-0001"}'
        ),
    ),
    Oracle(
        "SalesCreditEvaluation",
        "sales-credit-evaluation/v1",
        "a60023ba5f0e6867f5d9876aaa8f5bc2b3f9be9cab41457f24343b4394dd1708",
        (
            '{"attribution":{"classification":"TARGET_REP","raw_order_rep_present":true},'
            '"evaluation_id":"SYN-EVALUATION-M2-KAT-0001","human_review_required":false,"'
            'order_id":"SYN-ORDER-M2-KAT-0001","persistence_effects":["ACTIVE_CASE_CLASSI'
            'FICATION","NO_PERSISTENCE_MILESTONE_2"],"reasons":["PLACED_VALUE_PROVED","TA'
            'RGET_REP"],"replacement":{"candidate_results":[],"customer_continuity":"UN'
            'KNOWN","enumeration_complete":false,"product_continuity":"UNKNOWN","search_r'
            'un_id":null,"status":"NOT_APPLICABLE"},"rule_pack_version":"synthetic-sales'
            '-credit-rules/v1","rules_evaluated":["AMBIGUITY_ROUTING","CANCELLATION","MAT'
            'ERIAL_CHANGE","ORDER_REP_ATTRIBUTION","ORDER_WINDOW","PLACED_VALUE","REPLACE'
            'MENT","SNAPSHOT_VALIDATION"],"rules_fired":["ORDER_REP_ATTRIBUTION","ORDER_W'
            'INDOW","PLACED_VALUE","SNAPSHOT_VALIDATION"],"schema_version":"synthetic-sal'
            'es-credit-domain/v1","snapshot_id":"SYN-SNAPSHOT-M2-KAT-0001","supplied_fact'
            's":["ORDER_IDENTITY","ORDER_LIFECYCLE","ORDER_REP","ORDER_TIMING","ORDER_VAL'
            'UE","SNAPSHOT"],"validations":["ORDER_ID_MATCHED","ORDER_TIMING_ACCEPTED","S'
            'NAPSHOT_ACCEPTED"],"value":{"active_value":{"amount":"123.45","currency_code'
            '":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v'
            '1","currency_scale":2},"material_changes":[],"placed_value":{"amount":"123.4'
            '5","currency_code":"USD","currency_registry_version":"synthetic-iso-style-cu'
            'rrency-registry/v1","currency_scale":2},"status":"PLACED_VALUE_VERIFIED"},"w'
            'orkflow_state":"CREDIT_CONFIRMED_TARGET_REP"}'
        ),
    ),
)


def _expected_document() -> str:
    lines = [
        "# Milestone 2 Sales Credit hash preimages",
        "",
        "This is the explicit known-answer table for the frozen eight-domain inventory",
        "returned by `milestone2_hash_fixtures()`. Each preimage is exactly the ASCII",
        "domain, one `0A` byte, and the UTF-8 canonical JSON shown below. There is no",
        "trailing line feed. The executable oracles are",
        "`Milestone2HashPreimageTests.test_frozen_eight_domain_inventory_and_independent_sha256`",
        "and `Milestone2HashPreimageTests.test_published_preimage_document_has_no_drift`.",
        "",
        "| Binding fixture | Domain | Expected SHA-256 |",
        "|---|---|---|",
    ]
    lines.extend(
        f"| {oracle.name} | `{oracle.domain}` | `{oracle.digest}` |"
        for oracle in ORACLES
    )
    lines.extend(
        (
            "",
            "## Exact preimages",
            "",
            "The visible newline after each domain is the single required separator.",
            "Every canonical JSON value occupies exactly one line.",
        )
    )
    for oracle in ORACLES:
        lines.extend(
            (
                "",
                f"### {oracle.name}",
                "",
                "```text",
                oracle.domain,
                oracle.canonical_json,
                "```",
            )
        )
    return "\n".join(lines) + "\n"


class Milestone2HashPreimageTests(unittest.TestCase):
    def test_case_mutation_oracle_is_an_accepted_replayable_command(self) -> None:
        state = InMemorySalesCreditState()
        command = milestone2_case_mutation()
        if command.discovery_run is None or command.evaluation is None:
            self.fail("accepted fixture lacks discovery or evaluation authority")
        batch = SearchEvaluationBatch(command.discovery_run, (command,))
        candidate_evaluations = (
            SelectorOwnedCandidateEvaluation(
                interaction_id=command.interactions[0].interaction_id,
                snapshot=command.snapshots[0],
                evaluated_at=command.occurred_at,
                evaluation=command.evaluation,
            ),
        )
        accepted = state.apply_discovery_batch(
            batch,
            candidate_evaluations=candidate_evaluations,
        )
        replay = state.apply_discovery_batch(
            batch,
            candidate_evaluations=candidate_evaluations,
        )
        self.assertEqual(len(accepted.case_results), 1)
        self.assertFalse(accepted.case_results[0].replayed)
        self.assertTrue(replay.case_results[0].replayed)
        self.assertEqual(
            accepted.case_results[0].state,
            replay.case_results[0].state,
        )
        self.assertFalse(accepted.no_order_result.replayed)
        self.assertTrue(replay.no_order_result.replayed)
        self.assertEqual(state.case_accumulator.active_case_count, 1)

    def test_frozen_eight_domain_inventory_and_independent_sha256(self) -> None:
        fixtures = milestone2_hash_fixtures()
        self.assertEqual(len(fixtures), 8)
        self.assertEqual(
            tuple((fixture.name, fixture.binding.domain) for fixture in fixtures),
            tuple((oracle.name, oracle.domain) for oracle in ORACLES),
        )
        self.assertEqual(len({oracle.name for oracle in ORACLES}), 8)
        self.assertEqual(len({oracle.domain for oracle in ORACLES}), 8)

        for fixture, oracle in zip(fixtures, ORACLES, strict=True):
            with self.subTest(name=oracle.name):
                canonical = oracle.canonical_json.encode("utf-8")
                independently_encoded = json.dumps(
                    json.loads(oracle.canonical_json),
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                self.assertEqual(independently_encoded, canonical)
                self.assertNotIn(b"\n", canonical)

                domain = oracle.domain.encode("ascii")
                preimage = domain + b"\n" + canonical
                self.assertEqual(preimage.count(b"\n"), 1)
                self.assertEqual(hashlib.sha256(preimage).hexdigest(), oracle.digest)
                self.assertEqual(fixture.binding.domain, oracle.domain)
                self.assertEqual(fixture.binding.canonical_bytes, canonical)
                self.assertEqual(fixture.binding.preimage, preimage)
                self.assertEqual(fixture.binding.sha256, oracle.digest)

                wrong_separators = (
                    domain + canonical,
                    domain + b"\r\n" + canonical,
                    domain + b"\n\n" + canonical,
                    preimage + b"\n",
                )
                for wrong_preimage in wrong_separators:
                    self.assertNotEqual(
                        hashlib.sha256(wrong_preimage).hexdigest(),
                        oracle.digest,
                    )

    def test_published_preimage_document_has_no_drift(self) -> None:
        published = (ROOT / "docs" / "milestone2-hash-preimages.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(published, _expected_document())


if __name__ == "__main__":
    unittest.main()
