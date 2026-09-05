"""Focused M7 tests for projection, denominator, and truthful-status queries."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from synthetic_sales_assist.application.control_center import (
    CONTROL_CENTER_SCHEMA_VERSION,
    DENOMINATOR_REGISTRY_VERSION,
    ControlCenterApplication,
    ControlCenterError,
    ExtensionObservation,
    ExtensionStatusState,
    M4_BENCHMARK_REFERENCE,
    MetricWindow,
    PageRequest,
    classify_extension_status,
    denominator_registry,
)
from synthetic_sales_assist.domain.canonical import canonical_json_bytes, domain_hash
from synthetic_sales_assist.doi.lifecycle import AttentionEvent
from synthetic_sales_assist.doi.models import AttentionCondition
from synthetic_sales_assist.domain.identities import EvidenceId
from synthetic_sales_assist.domain.numeric import CURRENCY_REGISTRY_VERSION
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.persistence.database import SQLiteDatabase
from synthetic_sales_assist.persistence.doi_repository import DOIRepository
from synthetic_sales_assist.persistence.telemetry import SAFETY_COUNTER_NAMES


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
NOW = datetime(2026, 8, 31, 18, 0, tzinfo=timezone.utc)


def _doi_output(
    *,
    state: str,
    aggregate_state: str,
    selection_state: str,
    amount: str | None,
    currency: str = "USD",
    reviews: tuple[str, ...] = (),
    handling_flags: tuple[str, ...] = (),
) -> bytes:
    scale = 2
    money = None
    if amount is not None:
        money = {
            "amount": amount,
            "currency_code": currency,
            "currency_registry_version": CURRENCY_REGISTRY_VERSION,
            "currency_scale": scale,
        }
    payload = {
        "aggregate_potential": money,
        "aggregate_potential_state": aggregate_state,
        "append_transitions": ["TR-027"],
        "closure_proposal": None,
        "explanation": {"domain": "doi-explanation/v1", "sha256": SHA_A},
        "handling_flags": list(handling_flags),
        "human_review_requirements": list(reviews),
        "opportunities": [],
        "reason_routes": [],
        "reasons": [],
        "scenario_selection_state": selection_state,
        "state": state,
        "transition": "TR-001",
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _doi_input(*, evaluation_id: str, snapshot_id: str) -> bytes:
    payload = {
        "alternate_candidates": [],
        "alternate_research_state": "NOT_STARTED",
        "available_rule_pack_binding": {
            "domain": "doi-rule-pack/v1",
            "sha256": SHA_A,
        },
        "dedupe_history_projection": None,
        "dedupe_verification": None,
        "evaluated_at": "2026-08-31T17:04:00Z",
        "evaluation_id": evaluation_id,
        "human_facts": [],
        "required_rule_pack": {
            "component": "rule_pack",
            "version": "synthetic-doi-rules/v1",
        },
        "scenario_selection": None,
        "schema_version": "synthetic-doi-models/v1",
        "snapshot": {
            "domain": "doi-order-snapshot/v1",
            "sha256": domain_hash(
                "doi-test-snapshot/v1",
                canonical_json_bytes(
                    {"snapshot_id": snapshot_id},
                    expected_members={"snapshot_id"},
                ),
            ).sha256,
        },
    }
    return canonical_json_bytes(payload, expected_members=set(payload))


class ControlCenterCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = SQLiteDatabase(Path(self.temporary.name) / "control-center.sqlite3")
        self.database.initialize()
        self.application = ControlCenterApplication(self.database)

    def test_search_bound_accepts_96_and_rejects_97_ascii_characters(self) -> None:
        self.assertEqual(PageRequest(search="S" * 96).search, "S" * 96)
        with self.assertRaisesRegex(ControlCenterError, "SEARCH_INVALID"):
            PageRequest(search="S" * 97)

    def test_missing_audit_subjects_fail_closed_for_every_subject_kind(self) -> None:
        missing = {
            "SALES_CREDIT_CASE": "SYN-ORDER-M7-MISSING",
            "DOI_CASE": "SYN-EVIDENCE-M7-DOI-CASE-MISSING",
            "DOI_RUN": "SYN-RUN-M7-MISSING",
            "EVALUATION": "SYN-EVALUATION-M7-MISSING",
        }
        for subject_kind, subject_id in missing.items():
            with self.subTest(subject_kind=subject_kind):
                with self.assertRaisesRegex(
                    ControlCenterError,
                    "AUDIT_SUBJECT_NOT_FOUND",
                ):
                    self.application.audit_timeline(subject_kind, subject_id)

    def _insert_telemetry(
        self,
        operation: str,
        *,
        rule_pack: str,
        result: str,
        total_ns: int,
        replay: int = 0,
        conflict: int = 0,
        database_error: int = 0,
        fail_closed: int = 0,
        human_review: int = 0,
    ) -> None:
        suffix = int(operation.rsplit("-", 1)[-1])
        started = f"2026-08-31T17:00:0{suffix}Z"
        ended = f"2026-08-31T17:00:1{suffix}Z"
        with self.database.write() as connection:
            connection.execute(
                "INSERT INTO processing_telemetry ("
                "operation_id, rule_pack, demo_alias, started_at, ended_at, "
                "extraction_ns, validation_ns, normalization_ns, rule_ns, database_ns, "
                "total_ns, result_class, human_review, fail_closed, replay, conflict, "
                "database_error, rule_version, schema_version, catalog_version, error_code"
                ") VALUES (?, ?, NULL, ?, ?, 0, 0, 0, 0, 0, ?, ?, ?, ?, ?, ?, ?, "
                "'rules/v1', 'schema/v1', NULL, ?)",
                (
                    operation,
                    rule_pack,
                    started,
                    ended,
                    total_ns,
                    result,
                    human_review,
                    fail_closed,
                    replay,
                    conflict,
                    database_error,
                    None if result in {"SUCCESS", "HUMAN_REVIEW"} else f"{result}_TEST",
                ),
            )
            connection.executemany(
                "INSERT INTO telemetry_safety_counters "
                "(operation_id, counter_name, counter_value) VALUES (?, ?, 0)",
                ((operation, name) for name in SAFETY_COUNTER_NAMES),
            )

    def _insert_sales_credit(self, *, closed: bool = False) -> None:
        suffix = "CLOSED" if closed else "ACTIVE"
        order_id = f"SYN-ORDER-M7-SC-{suffix}"
        evaluation_id = None if closed else "SYN-EVALUATION-M7-SC-ACTIVE"
        snapshot_id = f"SYN-SNAPSHOT-M7-SC-{suffix}"
        workflow = "CLOSED" if closed else "MANUAL_REVIEW_REQUIRED"
        with self.database.write() as connection:
            connection.execute(
                "INSERT INTO sc_snapshots (snapshot_id, order_id, captured_at, "
                "extraction_status, lifecycle_status, parser_version, canonical_bytes) "
                "VALUES (?, ?, '2026-08-31T17:01:00Z', 'VALID', 'ACTIVE', 'parser/v1', ?)",
                (snapshot_id, order_id, b"{}"),
            )
            connection.execute(
                "INSERT INTO sc_cases (order_id, projection_version, workflow_state, "
                "attribution, order_value_status, current_evaluation_id, "
                "last_event_sequence, last_event_id, created_at, updated_at) "
                "VALUES (?, 1, ?, 'UNKNOWN', 'UNKNOWN', ?, 1, ?, "
                "'2026-08-31T17:01:00Z', '2026-08-31T17:01:00Z')",
                (
                    order_id,
                    workflow,
                    evaluation_id,
                    f"SYN-EVIDENCE-M7-SC-EVENT-{suffix}",
                ),
            )
            connection.execute(
                "INSERT INTO sc_case_events (event_id, order_id, sequence, "
                "predecessor_event_id, event_kind, workflow_state, attribution, "
                "order_value_status, manager_outcome, current_evaluation_id, "
                "replacement_parent_present, occurred_at, command_id, canonical_bytes) "
                "VALUES (?, ?, 1, NULL, 'CASE_CREATED', ?, 'UNKNOWN', 'UNKNOWN', "
                "NULL, ?, 0, '2026-08-31T17:01:00Z', ?, ?)",
                (
                    f"SYN-EVIDENCE-M7-SC-EVENT-{suffix}",
                    order_id,
                    workflow,
                    evaluation_id,
                    f"SYN-EVIDENCE-M4-M7-SC-{suffix}",
                    b"{}",
                ),
            )
            if closed:
                connection.execute(
                    "INSERT INTO sc_closed_audits (audit_id, order_id, closed_at, "
                    "purge_eligible_at, workflow_before_close, human_outcome, "
                    "material_sha256, canonical_bytes) VALUES (?, ?, "
                    "'2026-08-31T17:02:00Z', '2026-09-30T17:02:00Z', "
                    "'MANUAL_REVIEW_REQUIRED', NULL, ?, ?)",
                    ("SYN-EVIDENCE-M7-SC-CLOSED-AUDIT", order_id, SHA_A, b"{}"),
                )
                return
            connection.execute(
                "INSERT INTO sc_case_snapshots (order_id, snapshot_id) VALUES (?, ?)",
                (order_id, snapshot_id),
            )
            connection.execute(
                "INSERT INTO sc_evaluations (evaluation_id, order_id, snapshot_id, "
                "workflow_state, attribution, order_value_status, human_review_required, "
                "rule_pack_version, material_sha256, canonical_bytes) VALUES (?, ?, ?, "
                "'MANUAL_REVIEW_REQUIRED', 'UNKNOWN', 'UNKNOWN', 1, 'sc-rules/v1', ?, ?)",
                (evaluation_id, order_id, snapshot_id, SHA_A, b"{}"),
            )
            connection.execute(
                "INSERT INTO sc_case_evaluations (order_id, evaluation_id) VALUES (?, ?)",
                (order_id, evaluation_id),
            )
            connection.execute(
                "INSERT INTO sc_evaluation_reasons (evaluation_id, ordinal, reason_code) "
                "VALUES (?, 1, 'SC-MANUAL-REVIEW')",
                (evaluation_id,),
            )

    def _insert_doi_case(
        self,
        number: int,
        *,
        currency: str,
        amount: str | None,
        aggregate_state: str,
        selection_state: str,
        reviews: tuple[str, ...] = (),
        handling_flags: tuple[str, ...] = (),
        opportunity_count: int = 1,
        closed: bool = False,
    ) -> None:
        case_id = f"SYN-EVIDENCE-M7-DOI-CASE-{number}"
        order_id = f"SYN-ORDER-M7-DOI-{number}"
        run_id = f"SYN-RUN-M7-DOI-{number}"
        snapshot_id = f"SYN-SNAPSHOT-M7-DOI-{number}"
        evaluation_id = f"SYN-EVALUATION-M7-DOI-{number}"
        base_pk = number * 100
        state = "DOI_MANUAL_REVIEW" if reviews else "DOI_OPPORTUNITY"
        output = _doi_output(
            state=state,
            aggregate_state=aggregate_state,
            selection_state=selection_state,
            amount=amount,
            currency=currency,
            reviews=reviews,
            handling_flags=handling_flags,
        )
        evaluation_input = _doi_input(
            evaluation_id=evaluation_id,
            snapshot_id=snapshot_id,
        )
        input_domain = "doi-evaluation-input/v1"
        output_domain = "doi-evaluation-output/v1"
        input_sha256 = domain_hash(input_domain, evaluation_input).sha256
        output_sha256 = domain_hash(output_domain, output).sha256
        with self.database.write() as connection:
            connection.execute(
                "INSERT INTO doi_runs (run_id, invocation_id, run_type, recheck_order_id, "
                "started_at) VALUES (?, ?, 'RECHECK_ORDER', ?, '2026-08-31T17:03:00Z')",
                (run_id, f"SYN-EVIDENCE-M7-INVOKE-{number}", order_id),
            )
            connection.execute(
                "INSERT INTO doi_cases (case_id, order_id, created_at) "
                "VALUES (?, ?, '2026-08-31T17:03:00Z')",
                (case_id, order_id),
            )
            connection.execute(
                "INSERT INTO doi_case_artifacts (artifact_pk, case_id, artifact_kind, "
                "artifact_id, record_domain, record_sha256, record_canonical_bytes, "
                "record_payload, created_at) VALUES (?, ?, 'ORDER_SNAPSHOT', ?, ?, ?, ?, ?, "
                "'2026-08-31T17:03:00Z')",
                (
                    base_pk + 1,
                    case_id,
                    snapshot_id,
                    f"doi-snapshot-{number}/v1",
                    f"{number + 1:064x}",
                    b"{}",
                    b"{}",
                ),
            )
            connection.execute(
                "INSERT INTO doi_order_snapshots (snapshot_id, case_id, run_id, order_id, "
                "source_observed_at, completeness_sha256, record_artifact_pk) "
                "VALUES (?, ?, ?, ?, '2026-08-31T17:03:00Z', ?, ?)",
                (snapshot_id, case_id, run_id, order_id, SHA_A, base_pk + 1),
            )
            connection.execute(
                "INSERT INTO doi_case_artifacts (artifact_pk, case_id, artifact_kind, "
                "artifact_id, record_domain, record_sha256, record_canonical_bytes, "
                "record_payload, created_at) VALUES (?, ?, 'EVALUATION', ?, ?, ?, ?, ?, "
                "'2026-08-31T17:04:00Z')",
                (
                    base_pk + 2,
                    case_id,
                    evaluation_id,
                    f"doi-evaluation-{number}/v1",
                    f"{number + 10:064x}",
                    b"{}",
                    b"{}",
                ),
            )
            connection.execute(
                "INSERT INTO doi_evaluations (evaluation_id, case_id, snapshot_id, run_id, "
                "order_id, top_level_state, transition_id, input_domain, input_sha256, "
                "input_canonical_bytes, output_domain, output_sha256, output_canonical_bytes, "
                "record_artifact_pk) VALUES (?, ?, ?, ?, ?, ?, 'TR-001', "
                "?, ?, ?, ?, ?, ?, ?)",
                (
                    evaluation_id,
                    case_id,
                    snapshot_id,
                    run_id,
                    order_id,
                    state,
                    input_domain,
                    input_sha256,
                    evaluation_input,
                    output_domain,
                    output_sha256,
                    output,
                    base_pk + 2,
                ),
            )
            connection.execute(
                "INSERT INTO doi_evaluation_reasons (evaluation_id, reason_code, "
                "owning_transition_id, effective_overlay, ordinal) "
                "VALUES (?, ?, 'TR-001', 0, 1)",
                (evaluation_id, f"RC-{number:03d}"),
            )
            lifecycle = "CLOSED_HARD" if closed else "ACTIVE"
            closure = "SHIPPED" if closed else None
            connection.execute(
                "INSERT INTO doi_case_projections (case_id, lifecycle_state, "
                "current_snapshot_id, current_evaluation_id, terminal_closure_reason, "
                "projection_version, head_sha256, record_payload) "
                "VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
                (case_id, lifecycle, snapshot_id, evaluation_id, closure, SHA_D, b"{}"),
            )
            for ordinal in range(1, opportunity_count + 1):
                opportunity_id = f"SYN-EVIDENCE-M7-DOI-OPP-{number}-{ordinal}"
                connection.execute(
                    "INSERT INTO doi_case_artifacts (artifact_pk, case_id, artifact_kind, "
                    "artifact_id, record_domain, record_sha256, record_canonical_bytes, "
                    "record_payload, created_at) VALUES (?, ?, 'OPPORTUNITY', ?, ?, ?, ?, ?, "
                    "'2026-08-31T17:04:00Z')",
                    (
                        base_pk + 2 + ordinal,
                        case_id,
                        opportunity_id,
                        f"doi-opportunity-{number}-{ordinal}/v1",
                        f"{number * 10 + ordinal + 20:064x}",
                        b"{}",
                        b"{}",
                    ),
                )
                available = aggregate_state == "AVAILABLE"
                connection.execute(
                    "INSERT INTO doi_opportunities (opportunity_id, evaluation_id, case_id, "
                    "opportunity_type, potential_state, amount_minor_units, currency_code, "
                    "currency_registry_version, currency_scale, mutual_exclusion_group_id, "
                    "record_artifact_pk) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        opportunity_id,
                        evaluation_id,
                        case_id,
                        "FULFILLMENT_SPLIT" if ordinal == 1 else "DS_SEPARATION",
                        "AVAILABLE" if available else "UNAVAILABLE",
                        1000 if available else None,
                        currency if available else None,
                        CURRENCY_REGISTRY_VERSION if available else None,
                        2 if available else None,
                        (
                            f"SYN-EVIDENCE-M7-DOI-GROUP-{number}"
                            if selection_state == "REQUIRED"
                            else None
                        ),
                        base_pk + 2 + ordinal,
                    ),
                )

    def _insert_sales_credit_detail_history(self) -> None:
        order_id = "SYN-ORDER-M7-SC-ACTIVE"
        current_snapshot_id = "SYN-SNAPSHOT-M7-SC-ACTIVE"
        older_snapshot_id = "SYN-SNAPSHOT-M7-SC-HISTORY"
        unowned_snapshot_id = "SYN-SNAPSHOT-M7-SC-UNOWNED"
        private_blob = b"PRIVATE-M7-SC-CANONICAL-SENTINEL"
        interaction_a = "SYN-INTERACTION-M7-SC-A"
        interaction_b = "SYN-INTERACTION-M7-SC-B"
        run_a = "SYN-RUN-M7-SC-A"
        run_b = "SYN-RUN-M7-SC-B"
        normalized_contact = "fictional.manager@example.test"
        with self.database.write() as connection:
            connection.executemany(
                "INSERT INTO sc_snapshots (snapshot_id, order_id, captured_at, "
                "extraction_status, lifecycle_status, parser_version, canonical_bytes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    (
                        unowned_snapshot_id,
                        order_id,
                        "2026-08-31T16:58:00Z",
                        "VALID",
                        "ACTIVE",
                        "sales-credit-parser/unowned",
                        private_blob,
                    ),
                    (
                        older_snapshot_id,
                        order_id,
                        "2026-08-31T16:59:00Z",
                        "VALID",
                        "ACTIVE",
                        "sales-credit-parser/v0",
                        private_blob,
                    ),
                ),
            )
            connection.execute(
                "INSERT INTO sc_case_snapshots (order_id, snapshot_id) VALUES (?, ?)",
                (order_id, older_snapshot_id),
            )
            connection.executemany(
                "INSERT INTO sc_snapshot_lines (snapshot_id, line_id, sku_id, quantity, "
                "line_minor_units, currency, currency_registry_version, currency_scale, "
                "canonical_bytes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    (
                        current_snapshot_id,
                        "SYN-EVIDENCE-M7-SC-LINE-CURRENT-2",
                        "SYN-SKU-M7-SC-CURRENT-2",
                        "1",
                        None,
                        None,
                        None,
                        None,
                        private_blob,
                    ),
                    (
                        current_snapshot_id,
                        "SYN-EVIDENCE-M7-SC-LINE-CURRENT-1",
                        "SYN-SKU-M7-SC-CURRENT-1",
                        "2",
                        "1250",
                        "USD",
                        CURRENCY_REGISTRY_VERSION,
                        2,
                        private_blob,
                    ),
                    (
                        older_snapshot_id,
                        "SYN-EVIDENCE-M7-SC-LINE-HISTORY-1",
                        "SYN-SKU-M7-SC-HISTORY-1",
                        "1",
                        "900",
                        "USD",
                        CURRENCY_REGISTRY_VERSION,
                        2,
                        private_blob,
                    ),
                ),
            )
            connection.executemany(
                "INSERT INTO sc_interactions (interaction_id, source_ref_id, recorded_at, "
                "timestamp_precision, workflow_state, canonical_bytes) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    (
                        interaction_b,
                        "SYN-EVIDENCE-M7-SC-SOURCE-B",
                        "2026-08-31T17:01:40Z",
                        "CORRECTED",
                        "INBOUND_EVIDENCE_HUMAN_REVIEW",
                        private_blob,
                    ),
                    (
                        interaction_a,
                        "SYN-EVIDENCE-M7-SC-SOURCE-A",
                        "2026-08-31T17:01:30Z",
                        "EXACT",
                        "VERIFIED_PREORDER_EVIDENCE",
                        private_blob,
                    ),
                ),
            )
            connection.executemany(
                "INSERT INTO sc_case_interactions (order_id, interaction_id) VALUES (?, ?)",
                ((order_id, interaction_b), (order_id, interaction_a)),
            )
            connection.executemany(
                "INSERT INTO sc_search_runs (run_id, trigger_type, started_at, completed_at, "
                "adapter_version, enumeration_complete, terminal_outcome, canonical_bytes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    (
                        run_b,
                        "FORCE_RECHECK",
                        "2026-08-31T17:01:20Z",
                        "2026-08-31T17:01:22Z",
                        "synthetic-search-adapter/v2",
                        0,
                        "SEARCH_INCOMPLETE",
                        private_blob,
                    ),
                    (
                        run_a,
                        "NORMAL",
                        "2026-08-31T17:01:10Z",
                        "2026-08-31T17:01:12Z",
                        "synthetic-search-adapter/v1",
                        1,
                        "CANDIDATES_FOUND",
                        private_blob,
                    ),
                    (
                        "SYN-RUN-M7-SC-UNOWNED",
                        "NORMAL",
                        "2026-08-31T17:01:00Z",
                        "2026-08-31T17:01:01Z",
                        "synthetic-search-adapter/unowned",
                        0,
                        "MANUAL_REVIEW_REQUIRED",
                        private_blob,
                    ),
                ),
            )
            connection.executemany(
                "INSERT INTO sc_case_search_runs (order_id, run_id) VALUES (?, ?)",
                ((order_id, run_b), (order_id, run_a)),
            )
            connection.executemany(
                "INSERT INTO sc_search_identifiers (run_id, interaction_id, "
                "identifier_kind, normalized_value, completeness) VALUES (?, ?, ?, ?, ?)",
                (
                    (run_a, interaction_a, "EMAIL", normalized_contact, "COMPLETE"),
                    (run_a, interaction_b, "PHONE", "2125550101", "COMPLETE"),
                    (run_b, interaction_b, "PHONE", "2125550101", "INCOMPLETE"),
                ),
            )
            evidence_a = "SYN-EVIDENCE-M7-SC-EVIDENCE-A"
            evidence_b = "SYN-EVIDENCE-M7-SC-EVIDENCE-B"
            connection.executemany(
                "INSERT INTO sc_evidence_events (evidence_id, order_id, interaction_id, "
                "source_type, classification, occurred_at, canonical_bytes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    (
                        evidence_b,
                        order_id,
                        interaction_b,
                        "SYNTHETIC_PHONE_CALL",
                        "INBOUND_EVIDENCE_HUMAN_REVIEW",
                        "2026-08-31T17:01:55Z",
                        private_blob,
                    ),
                    (
                        evidence_a,
                        order_id,
                        interaction_a,
                        "SYNTHETIC_EMAIL",
                        "VERIFIED_PREORDER_EVIDENCE",
                        "2026-08-31T17:01:50Z",
                        private_blob,
                    ),
                    (
                        "SYN-EVIDENCE-M7-SC-EVIDENCE-UNOWNED",
                        order_id,
                        interaction_a,
                        "SYNTHETIC_INTERACTION",
                        "UNKNOWN_OR_CONTRADICTORY",
                        "2026-08-31T17:01:45Z",
                        private_blob,
                    ),
                ),
            )
            connection.executemany(
                "INSERT INTO sc_case_evidence (order_id, evidence_id) VALUES (?, ?)",
                ((order_id, evidence_b), (order_id, evidence_a)),
            )

    def _insert_realized_value(
        self,
        *,
        case_number: int,
        currency: str,
        amount_minor_units: int,
    ) -> None:
        case_id = f"SYN-EVIDENCE-M7-DOI-CASE-{case_number}"
        opportunity_id = f"SYN-EVIDENCE-M7-DOI-OPP-{case_number}-1"
        intervention_id = f"SYN-EVIDENCE-M7-DOI-INTERVENTION-{case_number}"
        artifact_pk = case_number * 100 + 50
        with self.database.write() as connection:
            connection.execute(
                "INSERT INTO doi_case_artifacts (artifact_pk, case_id, artifact_kind, "
                "artifact_id, record_domain, record_sha256, record_canonical_bytes, "
                "record_payload, created_at) VALUES (?, ?, 'INTERVENTION', ?, ?, ?, ?, ?, "
                "'2026-08-31T17:05:00Z')",
                (
                    artifact_pk,
                    case_id,
                    intervention_id,
                    f"doi-intervention-{case_number}/v1",
                    f"{case_number + 50:064x}",
                    b"{}",
                    b"{}",
                ),
            )
            connection.execute(
                "INSERT INTO doi_interventions (intervention_id, case_id, opportunity_id, "
                "intervention_type, status, action_occurred_at, projection_version, "
                "head_sha256, record_artifact_pk) VALUES (?, ?, ?, 'FULFILLMENT_SPLIT', "
                "'VERIFIED_ACTIVE', '2026-08-31T17:05:00Z', 1, ?, ?)",
                (intervention_id, case_id, opportunity_id, SHA_A, artifact_pk),
            )
            connection.execute(
                "INSERT INTO doi_retained_kpi_contributions (intervention_id, case_id, "
                "intervention_type, action_date, amount_minor_units, currency_code, "
                "currency_registry_version, currency_scale, revision, head_sha256, "
                "record_payload) VALUES (?, ?, 'FULFILLMENT_SPLIT', '2026-08-31', ?, ?, "
                "?, 2, 1, ?, ?)",
                (
                    intervention_id,
                    case_id,
                    amount_minor_units,
                    currency,
                    CURRENCY_REGISTRY_VERSION,
                    SHA_B,
                    b"{}",
                ),
            )

    def _insert_doi_detail_history(self, case_number: int = 1) -> None:
        """Add normalized schema-4 history whose private blobs must not escape."""

        case_id = f"SYN-EVIDENCE-M7-DOI-CASE-{case_number}"
        order_id = f"SYN-ORDER-M7-DOI-{case_number}"
        snapshot_id = f"SYN-SNAPSHOT-M7-DOI-{case_number}"
        intervention_id = f"SYN-EVIDENCE-M7-DOI-INTERVENTION-{case_number}"
        base_pk = case_number * 100
        private_blob = b"PRIVATE-M7-DOI-PAYLOAD-SENTINEL"
        artifact_rows = (
            (
                base_pk + 70,
                "COMPLETENESS_PROOF",
                f"SYN-EVIDENCE-M7-DOI-COMPLETENESS-{case_number}",
                "doi-completeness-proof/v1",
                "1" * 64,
            ),
            (
                base_pk + 71,
                "LINE_SNAPSHOT",
                f"SYN-EVIDENCE-M7-DOI-LINE-{case_number}-1",
                "doi-line-snapshot/v1",
                "2" * 64,
            ),
            (
                base_pk + 72,
                "LINE_SNAPSHOT",
                f"SYN-EVIDENCE-M7-DOI-LINE-{case_number}-2",
                "doi-line-snapshot/v1",
                "3" * 64,
            ),
        )
        with self.database.write() as connection:
            connection.executemany(
                "INSERT INTO doi_case_artifacts (artifact_pk, case_id, artifact_kind, "
                "artifact_id, record_domain, record_sha256, record_canonical_bytes, "
                "record_payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, "
                "'2026-08-31T17:05:30Z')",
                (
                    (
                        artifact_pk,
                        case_id,
                        artifact_kind,
                        artifact_id,
                        record_domain,
                        record_sha256,
                        private_blob,
                        private_blob,
                    )
                    for (
                        artifact_pk,
                        artifact_kind,
                        artifact_id,
                        record_domain,
                        record_sha256,
                    ) in artifact_rows
                ),
            )
            connection.execute(
                "INSERT INTO doi_snapshot_completeness_proof_references "
                "(snapshot_id, proof_artifact_pk) VALUES (?, ?)",
                (snapshot_id, base_pk + 70),
            )
            connection.executemany(
                "INSERT INTO doi_line_snapshots (line_snapshot_id, case_id, snapshot_id, "
                "line_ordinal, relevant_merchandise, continuity_state, record_artifact_pk) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    (
                        f"SYN-EVIDENCE-M7-DOI-LINE-{case_number}-2",
                        case_id,
                        snapshot_id,
                        2,
                        0,
                        "NOT_APPLICABLE",
                        base_pk + 72,
                    ),
                    (
                        f"SYN-EVIDENCE-M7-DOI-LINE-{case_number}-1",
                        case_id,
                        snapshot_id,
                        1,
                        1,
                        "COMPLETE",
                        base_pk + 71,
                    ),
                ),
            )
            connection.executemany(
                "INSERT INTO doi_opportunity_scope_components (opportunity_id, "
                "line_snapshot_id, role, quantity_text, ordinal) VALUES (?, ?, ?, ?, ?)",
                (
                    (
                        f"SYN-EVIDENCE-M7-DOI-OPP-{case_number}-1",
                        f"SYN-EVIDENCE-M7-DOI-LINE-{case_number}-2",
                        "DELAYED",
                        "1",
                        2,
                    ),
                    (
                        f"SYN-EVIDENCE-M7-DOI-OPP-{case_number}-1",
                        f"SYN-EVIDENCE-M7-DOI-LINE-{case_number}-1",
                        "AVAILABLE",
                        "2",
                        1,
                    ),
                ),
            )

            active_attention_stream = (
                f"SYN-EVIDENCE-M7-DOI-ATTENTION-ACTIVE-{case_number}"
            )
            coordination_attention_stream = (
                f"SYN-EVIDENCE-M7-DOI-ATTENTION-COORDINATION-{case_number}"
            )
            cleared_attention_stream = (
                f"SYN-EVIDENCE-M7-DOI-ATTENTION-CLEARED-{case_number}"
            )
            human_stream = f"SYN-EVIDENCE-M7-DOI-HUMAN-FACT-{case_number}"
            connection.execute(
                "INSERT INTO doi_owner_stream_anchors (stream_family, stream_id, case_id, "
                "run_id, created_at) VALUES (?, ?, ?, NULL, ?)",
                (
                    "HUMAN_FACT",
                    human_stream,
                    case_id,
                    "2026-08-31T17:06:02Z",
                ),
            )
            connection.execute(
                "INSERT INTO doi_owner_streams (stream_id, stream_family, case_id, run_id, "
                "current_state, sequence_no, head_sha256, projection_payload) "
                "VALUES (?, ?, ?, NULL, ?, ?, ?, ?)",
                (
                    human_stream,
                    "HUMAN_FACT",
                    case_id,
                    "SCENARIO_SELECTED",
                    2,
                    SHA_C,
                    private_blob,
                ),
            )
            owner_events = (
                (
                    "HUMAN_FACT",
                    human_stream,
                    f"SYN-EVIDENCE-M7-DOI-HUMAN-FACT-EVENT-{case_number}-1",
                    1,
                    None,
                    "RECORDED",
                    None,
                    "2026-08-31T17:06:02Z",
                    SHA_B,
                ),
                (
                    "HUMAN_FACT",
                    human_stream,
                    f"SYN-EVIDENCE-M7-DOI-HUMAN-FACT-EVENT-{case_number}-2",
                    2,
                    "TR-087",
                    "SCENARIO_SELECTED",
                    SHA_B,
                    "2026-08-31T17:06:04Z",
                    SHA_C,
                ),
            )
            connection.executemany(
                "INSERT INTO doi_owner_events (stream_family, stream_id, event_id, "
                "sequence_no, transition_id, projection_state, predecessor_sha256, "
                "occurred_at, record_domain, record_sha256, record_canonical_bytes, "
                "record_payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, "
                "'doi-owner-event-envelope/v1', ?, ?, ?)",
                (
                    (*event, private_blob, private_blob) for event in owner_events
                ),
            )

            repository = DOIRepository(connection)
            active_attention = AttentionEvent.set(
                event_id=EvidenceId(
                    f"SYN-EVIDENCE-M7-DOI-ATTENTION-ACTIVE-EVENT-{case_number}"
                ),
                case_id=EvidenceId(case_id),
                condition=AttentionCondition.RECHECK_REQUIRED,
                cause_key=EvidenceId(
                    f"SYN-EVIDENCE-M7-DOI-ATTENTION-ACTIVE-CAUSE-{case_number}"
                ),
                occurred_at=CanonicalTimestamp("2026-08-31T17:06:00Z"),
            )
            coordination_attention = AttentionEvent.set(
                event_id=EvidenceId(
                    f"SYN-EVIDENCE-M7-DOI-ATTENTION-COORDINATION-EVENT-{case_number}"
                ),
                case_id=EvidenceId(case_id),
                condition=AttentionCondition.HUMAN_COORDINATION_REVIEW_REQUIRED,
                cause_key=EvidenceId(
                    f"SYN-EVIDENCE-M7-DOI-ATTENTION-COORDINATION-CAUSE-{case_number}"
                ),
                occurred_at=CanonicalTimestamp("2026-08-31T17:06:01Z"),
            )
            cleared_set = AttentionEvent.set(
                event_id=EvidenceId(
                    f"SYN-EVIDENCE-M7-DOI-ATTENTION-CLEARED-SET-{case_number}"
                ),
                case_id=EvidenceId(case_id),
                condition=AttentionCondition.SOURCE_ABSENCE_RECHECK_REQUIRED,
                cause_key=EvidenceId(
                    f"SYN-EVIDENCE-M7-DOI-ATTENTION-CLEARED-CAUSE-{case_number}"
                ),
                occurred_at=CanonicalTimestamp("2026-08-31T17:06:02Z"),
            )
            cleared_event = AttentionEvent.clear(
                event_id=EvidenceId(
                    f"SYN-EVIDENCE-M7-DOI-ATTENTION-CLEARED-EVENT-{case_number}"
                ),
                active_set=cleared_set,
                resolver_id=EvidenceId(
                    f"SYN-EVIDENCE-M7-DOI-ATTENTION-CLEARED-RESOLVER-{case_number}"
                ),
                occurred_at=CanonicalTimestamp("2026-08-31T17:06:03Z"),
            )
            for stream_id, event in (
                (active_attention_stream, active_attention),
                (coordination_attention_stream, coordination_attention),
                (cleared_attention_stream, cleared_set),
            ):
                repository.append_owner_event(
                    stream_family="ATTENTION",
                    stream_id=stream_id,
                    current_state="SET",
                    event_id=event.event_id.value,
                    event=event,
                    occurred_at=event.occurred_at,
                    transition_id=event.transition.transition_id,
                    case_id=case_id,
                )
            repository.append_owner_event(
                stream_family="ATTENTION",
                stream_id=cleared_attention_stream,
                current_state="CLEAR",
                event_id=cleared_event.event_id.value,
                event=cleared_event,
                occurred_at=cleared_event.occurred_at,
                transition_id=cleared_event.transition.transition_id,
                case_id=case_id,
            )

            connection.execute(
                "INSERT INTO doi_action_verification_events (event_id, intervention_id, "
                "occurrence_id, record_domain, record_sha256, record_canonical_bytes, "
                "record_payload) VALUES (?, ?, ?, 'doi-action-verification/v1', ?, ?, ?)",
                (
                    f"SYN-EVIDENCE-M7-DOI-VERIFICATION-{case_number}",
                    intervention_id,
                    f"SYN-INTERACTION-M7-DOI-VERIFICATION-{case_number}",
                    SHA_D,
                    private_blob,
                    private_blob,
                ),
            )
            connection.executemany(
                "INSERT INTO doi_value_events (intervention_id, event_id, sequence_no, "
                "occurrence_id, event_type, predecessor_sha256, amount_minor_units, "
                "currency_code, currency_registry_version, currency_scale, record_domain, "
                "record_sha256, record_canonical_bytes, record_payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'USD', ?, 2, 'doi-value-event/v1', ?, ?, ?)",
                (
                    (
                        intervention_id,
                        f"SYN-EVIDENCE-M7-DOI-VALUE-{case_number}-1",
                        1,
                        f"SYN-INTERACTION-M7-DOI-VALUE-{case_number}-1",
                        "INITIAL_VERIFIED_VALUE",
                        None,
                        600,
                        CURRENCY_REGISTRY_VERSION,
                        SHA_A,
                        private_blob,
                        private_blob,
                    ),
                    (
                        intervention_id,
                        f"SYN-EVIDENCE-M7-DOI-VALUE-{case_number}-2",
                        2,
                        f"SYN-INTERACTION-M7-DOI-VALUE-{case_number}-2",
                        "PARTIAL_REVERSAL",
                        SHA_A,
                        -100,
                        CURRENCY_REGISTRY_VERSION,
                        SHA_B,
                        private_blob,
                        private_blob,
                    ),
                ),
            )

            link_id = f"SYN-EVIDENCE-M7-DOI-LINK-{case_number}"
            connection.execute(
                "INSERT INTO doi_resulting_order_links (link_id, case_id, intervention_id, "
                "parent_order_id, child_order_id, state, current_revision, head_sha256, "
                "projection_payload) VALUES (?, ?, ?, ?, ?, 'AUTO_LINKED', 2, ?, ?)",
                (
                    link_id,
                    case_id,
                    intervention_id,
                    order_id,
                    f"SYN-ORDER-M7-DOI-RESULT-{case_number}",
                    SHA_C,
                    private_blob,
                ),
            )
            connection.executemany(
                "INSERT INTO doi_resulting_order_link_revisions (link_id, revision_no, "
                "revision_id, predecessor_sha256, record_domain, record_sha256, "
                "record_canonical_bytes, record_payload) VALUES (?, ?, ?, ?, "
                "'doi-resulting-order-link/v1', ?, ?, ?)",
                (
                    (
                        link_id,
                        2,
                        f"SYN-EVIDENCE-M7-DOI-LINK-REVISION-{case_number}-2",
                        SHA_A,
                        SHA_C,
                        private_blob,
                        private_blob,
                    ),
                    (
                        link_id,
                        1,
                        f"SYN-EVIDENCE-M7-DOI-LINK-REVISION-{case_number}-1",
                        None,
                        SHA_A,
                        private_blob,
                        private_blob,
                    ),
                ),
            )
            connection.executemany(
                "INSERT INTO doi_resulting_order_mapping_components (link_id, revision_no, "
                "parent_line_id, child_line_id, quantity_text, ordinal) "
                "VALUES (?, 2, ?, ?, ?, ?)",
                (
                    (
                        link_id,
                        f"SYN-EVIDENCE-M7-DOI-PARENT-LINE-{case_number}-2",
                        f"SYN-EVIDENCE-M7-DOI-CHILD-LINE-{case_number}-2",
                        "1.000",
                        2,
                    ),
                    (
                        link_id,
                        f"SYN-EVIDENCE-M7-DOI-PARENT-LINE-{case_number}-1",
                        f"SYN-EVIDENCE-M7-DOI-CHILD-LINE-{case_number}-1",
                        "2.000",
                        1,
                    ),
                ),
            )
            connection.execute(
                "INSERT INTO doi_kpi_contribution_events (intervention_id, sequence_no, "
                "event_id, predecessor_sha256, record_domain, record_sha256, "
                "record_canonical_bytes, record_payload) VALUES (?, 1, ?, NULL, "
                "'doi-kpi-contribution-event/v1', ?, ?, ?)",
                (
                    intervention_id,
                    f"SYN-EVIDENCE-M7-DOI-KPI-EVENT-{case_number}",
                    SHA_B,
                    private_blob,
                    private_blob,
                ),
            )

    def _populate(self) -> None:
        self._insert_sales_credit()
        self._insert_sales_credit(closed=True)
        self._insert_doi_case(
            1,
            currency="USD",
            amount="10.00",
            aggregate_state="AVAILABLE",
            selection_state="NOT_REQUIRED",
            handling_flags=("COORDINATION_REQUIRED", "MANUAL_HANDLING"),
            opportunity_count=2,
        )
        self._insert_doi_case(
            2,
            currency="EUR",
            amount="20.00",
            aggregate_state="AVAILABLE",
            selection_state="SELECTED",
        )
        self._insert_doi_case(
            3,
            currency="USD",
            amount=None,
            aggregate_state="UNAVAILABLE",
            selection_state="REQUIRED",
            reviews=("SCENARIO_SELECTION",),
            opportunity_count=2,
        )
        self._insert_doi_case(
            4,
            currency="USD",
            amount="99.00",
            aggregate_state="AVAILABLE",
            selection_state="NOT_REQUIRED",
            closed=True,
        )
        self._insert_realized_value(case_number=1, currency="USD", amount_minor_units=500)
        self._insert_realized_value(case_number=2, currency="EUR", amount_minor_units=700)
        self._insert_telemetry(
            "SYN-EVIDENCE-M7-TELEMETRY-1",
            rule_pack="SALES_CREDIT",
            result="HUMAN_REVIEW",
            total_ns=100,
            human_review=1,
        )
        self._insert_telemetry(
            "SYN-EVIDENCE-M7-TELEMETRY-2",
            rule_pack="DOI",
            result="SUCCESS",
            total_ns=200,
            replay=1,
        )
        self._insert_telemetry(
            "SYN-EVIDENCE-M7-TELEMETRY-3",
            rule_pack="DOI",
            result="CONFLICT",
            total_ns=300,
            conflict=1,
        )
        self._insert_telemetry(
            "SYN-EVIDENCE-M7-TELEMETRY-4",
            rule_pack="DOI",
            result="ERROR",
            total_ns=400,
            database_error=1,
        )
        self._insert_telemetry(
            "SYN-EVIDENCE-M7-TELEMETRY-5",
            rule_pack="SHARED",
            result="SUCCESS",
            total_ns=999,
        )

    def _insert_operational_receipts_and_error(self) -> None:
        with self.database.write() as connection:
            connection.executemany(
                "INSERT INTO backup_receipts (backup_id, created_at, completed_at, "
                "schema_version, application_version, source_sha256, backup_sha256, "
                "table_count, row_count, quick_check, foreign_key_check, status, "
                "error_code) VALUES (?, ?, ?, 4, '0.1.0', ?, ?, 42, 100, ?, ?, ?, ?)",
                (
                    (
                        "SYN-EVIDENCE-M7-BACKUP-VERIFIED",
                        "2026-08-31T17:10:00Z",
                        "2026-08-31T17:11:00Z",
                        SHA_A,
                        SHA_B,
                        "ok",
                        "ok",
                        "COMPLETED",
                        None,
                    ),
                    (
                        "SYN-EVIDENCE-M7-BACKUP-FAILED",
                        "2026-08-31T17:20:00Z",
                        "2026-08-31T17:21:00Z",
                        SHA_A,
                        SHA_C,
                        "failed",
                        "not_run",
                        "FAILED",
                        "BACKUP_VERIFY_FAILED",
                    ),
                    (
                        "SYN-EVIDENCE-M7-BACKUP-STARTED",
                        "2026-08-31T17:30:00Z",
                        None,
                        None,
                        None,
                        "not_run",
                        "not_run",
                        "STARTED",
                        None,
                    ),
                ),
            )
            connection.execute(
                "INSERT INTO restore_receipts (restore_id, started_at, completed_at, "
                "backup_sha256, pre_restore_backup_id, schema_version, status, "
                "error_code) VALUES (?, ?, ?, ?, ?, 4, 'COMPLETED', NULL)",
                (
                    "SYN-EVIDENCE-M7-RESTORE-0001",
                    "2026-08-31T17:40:00Z",
                    "2026-08-31T17:41:00Z",
                    SHA_B,
                    "SYN-EVIDENCE-M7-BACKUP-PRE-RESTORE",
                ),
            )
            connection.execute(
                "INSERT INTO structured_domain_failures (failure_id, command_id, "
                "error_code, error_category, retryable, occurred_at) "
                "VALUES (?, NULL, 'SAFE_VALIDATION_FAILURE', 'VALIDATION', 0, ?)",
                (
                    "SYN-EVIDENCE-M7-FAILURE-0001",
                    "2026-08-31T17:42:00Z",
                ),
            )

    def test_registry_is_versioned_and_exhaustive(self) -> None:
        registry = denominator_registry()
        self.assertEqual(registry["schema_version"], DENOMINATOR_REGISTRY_VERSION)
        ids = {item["metric_id"] for item in registry["metrics"]}  # type: ignore[index]
        self.assertEqual(
            ids,
            {
                "requests_received",
                "unique_evaluations",
                "successful_request_rate",
                "fail_closed_rate",
                "human_review_rate",
                "active_sales_credit_cases",
                "manager_outcome_rate",
                "active_doi_opportunities",
                "doi_state_distribution",
                "opportunity_type_count",
                "latency",
                "throughput",
                "potential_value",
                "realized_value",
                "backup_database_safety_status",
            },
        )

    def test_empty_denominators_are_na_not_zero_percent(self) -> None:
        metrics = self.application.metrics()
        self.assertEqual(metrics.requests_received, 0)
        self.assertEqual(metrics.successful_request_rate.to_dict()["display"], "N/A")
        self.assertEqual(metrics.human_review_rate.to_dict()["display"], "N/A")
        self.assertEqual(metrics.manager_outcome_rate.to_dict()["display"], "N/A")
        self.assertEqual(metrics.safety_counters, tuple((name, 0) for name in SAFETY_COUNTER_NAMES))

    def test_metrics_separate_replay_conflict_and_current_projection_counts(self) -> None:
        self._populate()
        metrics = self.application.metrics()
        self.assertEqual(metrics.requests_received, 4)
        self.assertEqual(metrics.successful_requests, 2)
        self.assertEqual(metrics.exact_replays, 1)
        self.assertEqual(metrics.material_conflicts, 1)
        self.assertEqual(metrics.failed_closed_requests, 0)
        self.assertEqual(metrics.database_error_count, 1)
        self.assertEqual(
            dict(metrics.request_result_distribution),
            {
                "CONFLICT": 1,
                "ERROR": 1,
                "HUMAN_REVIEW": 1,
                "SUCCESS": 1,
            },
        )
        self.assertEqual(metrics.unique_evaluations, 5)
        self.assertEqual(metrics.active_sales_credit_cases, 1)
        self.assertEqual(metrics.active_doi_cases, 3)
        self.assertEqual(metrics.active_doi_opportunities, 5)
        self.assertEqual(metrics.median_latency_ns, 250)
        self.assertEqual(metrics.p95_latency_ns, 400)
        self.assertEqual(metrics.successful_request_rate.to_dict()["display"], "50.0%")
        reconciliation = self.application.reconciliation()
        self.assertGreater(
            reconciliation.sales_credit_history_events,
            metrics.active_sales_credit_cases,
        )
        self.assertGreater(reconciliation.doi_history_events, metrics.active_doi_cases)

    def test_system_and_telemetry_operational_metadata_is_closed_and_truthful(self) -> None:
        self._populate()
        self._insert_operational_receipts_and_error()
        self.database.clock = lambda: NOW
        system = self.application.system_view(
            expected_extension_version="0.1.2",
            expected_extension_package_sha256=SHA_A,
            extension_package_available=True,
            observed_extension_version=None,
            extension_observed_at=None,
            now=NOW,
        )
        telemetry = self.application.telemetry_view()
        database = system["database"]
        self.assertIsInstance(database, dict)
        assert isinstance(database, dict)
        self.assertEqual(database["schema_version"], 4)
        self.assertEqual(self.application.backup_receipts()[0].status, "STARTED")
        self.assertEqual(
            database["latest_backup"]["backup_id"],  # type: ignore[index]
            "SYN-EVIDENCE-M7-BACKUP-VERIFIED",
        )
        self.assertEqual(
            database["latest_restore"]["restore_id"],  # type: ignore[index]
            "SYN-EVIDENCE-M7-RESTORE-0001",
        )
        self.assertEqual(database["verification_observed_at"], "2026-08-31T18:00:00Z")
        self.assertEqual(database["safety_observed_at"], "2026-08-31T18:00:00Z")
        self.assertEqual(system["benchmark_reference"], M4_BENCHMARK_REFERENCE.to_dict())
        self.assertEqual(
            system["recent_safe_errors"],
            [
                {
                    "category": "VALIDATION",
                    "code": "SAFE_VALIDATION_FAILURE",
                    "occurred_at": "2026-08-31T17:42:00Z",
                    "retryable": False,
                }
            ],
        )
        self.assertEqual(
            telemetry["benchmark_reference"],
            M4_BENCHMARK_REFERENCE.to_dict(),
        )
        operational = telemetry["operational_status"]
        self.assertEqual(
            operational["latest_backup"]["backup_id"],  # type: ignore[index]
            "SYN-EVIDENCE-M7-BACKUP-VERIFIED",
        )
        self.assertEqual(telemetry["metrics"]["database_error_count"], 1)  # type: ignore[index]
        serialized = json.dumps({"system": system, "telemetry": telemetry})
        self.assertNotIn(self.temporary.name, serialized)
        self.assertNotIn("canonical_bytes", serialized)

    def test_currency_totals_are_segmented_and_overlap_remains_unavailable(self) -> None:
        self._populate()
        metrics = self.application.metrics()
        potential = {item.currency_code: item for item in metrics.potential_by_currency}
        self.assertEqual(potential["USD"].amount_minor_units, 1000)
        self.assertEqual(potential["EUR"].amount_minor_units, 2000)
        self.assertEqual(metrics.potential_unavailable_count, 1)
        self.assertEqual(metrics.unresolved_overlap_count, 1)
        realized = {item.currency_code: item for item in metrics.realized_by_currency}
        self.assertEqual(realized["USD"].amount_minor_units, 500)
        self.assertEqual(realized["EUR"].amount_minor_units, 700)

    def test_queues_are_current_bounded_and_domain_aware(self) -> None:
        self._populate()
        sc = self.application.sales_credit_queue_view(
            PageRequest(sort_by="order_id", descending=False, limit=1)
        )
        self.assertEqual(sc["total_count"], 1)
        self.assertEqual(len(sc["items"]), 1)  # type: ignore[arg-type]
        doi = self.application.doi_queue_view(
            PageRequest(state="DOI_MANUAL_REVIEW", sort_by="order_id", descending=False)
        )
        self.assertEqual(doi["total_count"], 1)
        review = self.application.review_queue_view()
        self.assertEqual(review["total_count"], 2)
        domains = {item["domain"] for item in review["items"]}  # type: ignore[index]
        self.assertEqual(domains, {"SALES_CREDIT", "DOI"})

    def test_queue_views_echo_closed_validated_query_without_changing_page(self) -> None:
        self._populate()
        sales_request = PageRequest(
            search="SC-ACTIVE",
            state="MANUAL_REVIEW_REQUIRED",
            sort_by="workflow_state",
            descending=False,
            offset=0,
            limit=1,
        )
        sales_page = self.application.sales_credit_cases(sales_request)
        sales_view = self.application.sales_credit_queue_view(sales_request)
        self.assertEqual(
            sales_view["query"],
            {
                "descending": False,
                "search": "SC-ACTIVE",
                "sort_by": "workflow_state",
                "state": "MANUAL_REVIEW_REQUIRED",
            },
        )
        self.assertEqual(sales_view["total_count"], sales_page.total_count)
        self.assertEqual(len(sales_view["items"]), len(sales_page.items))
        self.assertEqual(sales_view["offset"], sales_page.offset)
        self.assertEqual(sales_view["limit"], sales_page.limit)

        doi_request = PageRequest(
            search="M7-DOI",
            state="DOI_OPPORTUNITY",
            sort_by="case_id",
            descending=True,
            offset=1,
            limit=2,
        )
        doi_page = self.application.doi_cases(doi_request)
        doi_view = self.application.doi_queue_view(doi_request)
        self.assertEqual(
            doi_view["query"],
            {
                "descending": True,
                "search": "M7-DOI",
                "sort_by": "case_id",
                "state": "DOI_OPPORTUNITY",
            },
        )
        self.assertEqual(doi_view["total_count"], doi_page.total_count)
        self.assertEqual(len(doi_view["items"]), len(doi_page.items))
        self.assertEqual(doi_view["offset"], doi_page.offset)
        self.assertEqual(doi_view["limit"], doi_page.limit)

    def test_sales_credit_detail_empty_retained_graph_is_closed_and_versioned(self) -> None:
        self._insert_sales_credit(closed=True)
        detail = self.application.sales_credit_detail("SYN-ORDER-M7-SC-CLOSED")
        self.assertEqual(
            set(detail),
            {
                "current_evaluation",
                "evidence",
                "interactions",
                "manager_outcomes",
                "reason_codes",
                "schema_version",
                "search_runs",
                "snapshots",
                "summary",
                "timeline",
            },
        )
        self.assertEqual(detail["schema_version"], CONTROL_CENTER_SCHEMA_VERSION)
        self.assertIsNone(detail["current_evaluation"])
        for name in (
            "evidence",
            "interactions",
            "manager_outcomes",
            "reason_codes",
            "search_runs",
            "snapshots",
        ):
            self.assertEqual(detail[name], [], name)
        self.assertEqual(detail["summary"]["interaction_count"], 0)
        self.assertEqual(detail["summary"]["workflow_state"], "CLOSED")

    def test_sales_credit_detail_exposes_only_owned_normalized_metadata_read_only(self) -> None:
        self._insert_sales_credit()
        self._insert_sales_credit_detail_history()
        tables = (
            "sc_snapshots",
            "sc_snapshot_lines",
            "sc_case_snapshots",
            "sc_interactions",
            "sc_case_interactions",
            "sc_search_runs",
            "sc_search_identifiers",
            "sc_case_search_runs",
            "sc_evidence_events",
            "sc_case_evidence",
            "sc_evaluations",
            "sc_case_evaluations",
        )

        def counts() -> tuple[int, ...]:
            with self.database.read() as connection:
                return tuple(
                    int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                    for table in tables
                )

        before = counts()
        order_id = "SYN-ORDER-M7-SC-ACTIVE"
        detail = self.application.sales_credit_detail(order_id)
        self.assertEqual(detail, self.application.sales_credit_detail(order_id))
        self.assertEqual(counts(), before)
        self.assertEqual(detail["schema_version"], CONTROL_CENTER_SCHEMA_VERSION)

        current = detail["current_evaluation"]
        self.assertEqual(
            set(current),
            {
                "evaluation_id",
                "human_review_required",
                "material_sha256",
                "rule_pack_version",
                "snapshot_id",
            },
        )
        self.assertEqual(current["evaluation_id"], "SYN-EVALUATION-M7-SC-ACTIVE")
        self.assertEqual(current["snapshot_id"], "SYN-SNAPSHOT-M7-SC-ACTIVE")
        self.assertEqual(current["rule_pack_version"], "sc-rules/v1")
        self.assertEqual(current["material_sha256"], SHA_A)
        self.assertTrue(current["human_review_required"])
        self.assertEqual(detail["reason_codes"], ["SC-MANUAL-REVIEW"])

        snapshots = detail["snapshots"]
        self.assertEqual(
            [snapshot["snapshot_id"] for snapshot in snapshots],
            ["SYN-SNAPSHOT-M7-SC-HISTORY", "SYN-SNAPSHOT-M7-SC-ACTIVE"],
        )
        self.assertEqual(
            set(snapshots[0]),
            {
                "captured_at",
                "extraction_status",
                "is_current",
                "lifecycle_status",
                "line_count",
                "parser_version",
                "snapshot_id",
            },
        )
        self.assertEqual([snapshot["line_count"] for snapshot in snapshots], [1, 2])
        self.assertEqual([snapshot["is_current"] for snapshot in snapshots], [False, True])
        self.assertEqual(
            [snapshot["extraction_status"] for snapshot in snapshots],
            ["VALID", "VALID"],
        )

        interactions = detail["interactions"]
        self.assertEqual(
            [interaction["interaction_id"] for interaction in interactions],
            ["SYN-INTERACTION-M7-SC-A", "SYN-INTERACTION-M7-SC-B"],
        )
        self.assertEqual(
            set(interactions[0]),
            {
                "interaction_id",
                "recorded_at",
                "source_ref_id",
                "timestamp_precision",
                "workflow_state",
            },
        )
        self.assertEqual(detail["summary"]["interaction_count"], 2)

        evidence = detail["evidence"]
        self.assertEqual(
            [item["evidence_id"] for item in evidence],
            ["SYN-EVIDENCE-M7-SC-EVIDENCE-A", "SYN-EVIDENCE-M7-SC-EVIDENCE-B"],
        )
        self.assertEqual(
            set(evidence[0]),
            {
                "classification",
                "evidence_id",
                "interaction_id",
                "occurred_at",
                "source_type",
            },
        )
        self.assertEqual(evidence[0]["source_type"], "SYNTHETIC_EMAIL")
        self.assertEqual(evidence[0]["classification"], "VERIFIED_PREORDER_EVIDENCE")

        runs = detail["search_runs"]
        self.assertEqual(
            [run["run_id"] for run in runs],
            ["SYN-RUN-M7-SC-A", "SYN-RUN-M7-SC-B"],
        )
        self.assertEqual(
            set(runs[0]),
            {
                "adapter_version",
                "completed_at",
                "enumeration_complete",
                "identifier_count",
                "run_id",
                "started_at",
                "terminal_outcome",
                "trigger_type",
            },
        )
        self.assertEqual([run["identifier_count"] for run in runs], [2, 1])
        self.assertEqual([run["enumeration_complete"] for run in runs], [True, False])
        self.assertEqual(
            [run["terminal_outcome"] for run in runs],
            ["CANDIDATES_FOUND", "SEARCH_INCOMPLETE"],
        )

        serialized = json.dumps(detail, sort_keys=True)
        for prohibited in (
            "fictional.manager@example.test",
            "2125550101",
            "PRIVATE-M7-SC-CANONICAL-SENTINEL",
            "canonical_bytes",
            "normalized_value",
            "SYN-SNAPSHOT-M7-SC-UNOWNED",
            "SYN-RUN-M7-SC-UNOWNED",
            "SYN-EVIDENCE-M7-SC-EVIDENCE-UNOWNED",
            self.temporary.name,
        ):
            self.assertNotIn(prohibited, serialized)

    def test_closed_doi_case_is_history_visible_but_not_in_current_queue(self) -> None:
        self._populate()
        self.assertEqual(self.application.doi_cases().total_count, 3)
        detail = self.application.doi_detail("SYN-EVIDENCE-M7-DOI-CASE-4")
        self.assertEqual(detail["summary"]["lifecycle_state"], "CLOSED_HARD")
        self.assertEqual(detail["summary"]["doi_state"], "DOI_OPPORTUNITY")

    def test_doi_detail_empty_histories_use_closed_versioned_lists(self) -> None:
        self._insert_doi_case(
            9,
            currency="USD",
            amount=None,
            aggregate_state="UNAVAILABLE",
            selection_state="NOT_REQUIRED",
            opportunity_count=0,
        )
        detail = self.application.doi_detail("SYN-EVIDENCE-M7-DOI-CASE-9")
        self.assertEqual(
            set(detail),
            {
                "current_attention_causes",
                "current_evaluation",
                "handling_flags",
                "human_fact_events",
                "interventions",
                "opportunities",
                "reason_explanations",
                "resulting_order_links",
                "retained_kpi_contributions",
                "schema_version",
                "scenario_selection",
                "source_completeness",
                "summary",
                "timeline",
                "value_events",
            },
        )
        self.assertEqual(detail["schema_version"], CONTROL_CENTER_SCHEMA_VERSION)
        self.assertIsNone(detail["scenario_selection"])
        self.assertEqual(detail["summary"]["attention_causes"], [])
        self.assertEqual(
            set(detail["current_evaluation"]),
            {
                "evaluation_id",
                "input_domain",
                "input_sha256",
                "output_domain",
                "output_sha256",
                "run_id",
                "snapshot_id",
                "top_level_state",
                "transition_id",
            },
        )
        self.assertEqual(
            detail["current_evaluation"]["input_domain"],
            "doi-evaluation-input/v1",
        )
        self.assertEqual(
            detail["current_evaluation"]["output_domain"],
            "doi-evaluation-output/v1",
        )
        self.assertEqual(detail["reason_explanations"][0]["code"], "RC-009")
        for name in (
            "current_attention_causes",
            "handling_flags",
            "human_fact_events",
            "interventions",
            "opportunities",
            "resulting_order_links",
            "retained_kpi_contributions",
            "value_events",
        ):
            self.assertEqual(detail[name], [], name)
        self.assertEqual(len(detail["source_completeness"]), 1)
        source = detail["source_completeness"][0]
        self.assertEqual(
            set(source),
            {
                "completeness_proof_present",
                "completeness_sha256",
                "is_current",
                "line_count",
                "order_id",
                "record_domain",
                "record_sha256",
                "relevant_line_count",
                "run_id",
                "snapshot_id",
                "source_observed_at",
            },
        )
        self.assertTrue(source["is_current"])
        self.assertFalse(source["completeness_proof_present"])
        self.assertEqual(source["line_count"], 0)
        self.assertEqual(source["relevant_line_count"], 0)

    def test_doi_detail_exposes_governed_history_without_mutating_or_leaking(self) -> None:
        self._populate()
        self._insert_doi_detail_history()
        tables = (
            "doi_owner_events",
            "doi_interventions",
            "doi_action_verification_events",
            "doi_opportunity_scope_components",
            "doi_value_events",
            "doi_resulting_order_links",
            "doi_resulting_order_link_revisions",
            "doi_resulting_order_mapping_components",
            "doi_kpi_contribution_events",
            "doi_retained_kpi_contributions",
        )

        def counts() -> tuple[int, ...]:
            with self.database.read() as connection:
                return tuple(
                    int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                    for table in tables
                )

        before = counts()
        detail = self.application.doi_detail("SYN-EVIDENCE-M7-DOI-CASE-1")
        self.assertEqual(detail, self.application.doi_detail("SYN-EVIDENCE-M7-DOI-CASE-1"))
        self.assertEqual(counts(), before)
        self.assertEqual(
            detail["handling_flags"],
            ["COORDINATION_REQUIRED", "MANUAL_HANDLING"],
        )
        self.assertEqual(
            detail["reason_explanations"],
            [
                {
                    "class": "BLOCK",
                    "code": "RC-001",
                    "description": (
                        "Monday/Wednesday/Friday tab was not explicitly confirmed. "
                        "Do not import or read OA."
                    ),
                    "label": "SOURCE_TAB_CONFIRMATION_REQUIRED",
                    "registry_version": "synthetic-doi-reason-registry/v1.0.1",
                }
            ],
        )

        opportunities = {
            item["opportunity_id"]: item for item in detail["opportunities"]
        }
        scoped = opportunities["SYN-EVIDENCE-M7-DOI-OPP-1-1"]
        self.assertEqual(
            set(scoped),
            {
                "amount_minor_units",
                "currency_code",
                "currency_registry_version",
                "currency_scale",
                "mutual_exclusion_group_id",
                "opportunity_id",
                "opportunity_type",
                "potential_state",
                "scope_components",
            },
        )
        self.assertEqual(
            scoped["scope_components"],
            [
                {
                    "line_snapshot_id": "SYN-EVIDENCE-M7-DOI-LINE-1-1",
                    "ordinal": 1,
                    "quantity_text": "2",
                    "role": "AVAILABLE",
                },
                {
                    "line_snapshot_id": "SYN-EVIDENCE-M7-DOI-LINE-1-2",
                    "ordinal": 2,
                    "quantity_text": "1",
                    "role": "DELAYED",
                },
            ],
        )
        self.assertEqual(
            opportunities["SYN-EVIDENCE-M7-DOI-OPP-1-2"]["scope_components"],
            [],
        )

        source = detail["source_completeness"][0]
        self.assertEqual(source["line_count"], 2)
        self.assertEqual(source["relevant_line_count"], 1)
        self.assertTrue(source["completeness_proof_present"])
        self.assertEqual(source["record_domain"], "doi-snapshot-1/v1")

        attention = detail["current_attention_causes"]
        self.assertEqual(len(attention), 2)
        for cause in attention:
            self.assertEqual(
                set(cause),
                {
                    "cause_key",
                    "condition",
                    "current_event_id",
                    "current_event_occurred_at",
                    "head_sha256",
                    "projection_state",
                    "record_domain",
                    "record_sha256",
                    "sequence",
                    "stream_id",
                },
            )
            self.assertEqual(cause["projection_state"], "SET")
            self.assertNotIn("CLEARED", cause["stream_id"])
        self.assertEqual(
            [cause["condition"] for cause in attention],
            ["HUMAN_COORDINATION_REVIEW_REQUIRED", "RECHECK_REQUIRED"],
        )
        self.assertEqual(
            detail["summary"]["attention_causes"],
            ["HUMAN_COORDINATION_REVIEW_REQUIRED", "RECHECK_REQUIRED"],
        )
        queue_case = next(
            item
            for item in self.application.doi_cases().items
            if item.case_id == "SYN-EVIDENCE-M7-DOI-CASE-1"
        )
        self.assertEqual(
            queue_case.to_dict()["attention_causes"],
            ["HUMAN_COORDINATION_REVIEW_REQUIRED", "RECHECK_REQUIRED"],
        )

        human_events = detail["human_fact_events"]
        self.assertEqual([event["sequence"] for event in human_events], [1, 2])
        self.assertEqual(
            set(human_events[0]),
            {
                "event_id",
                "occurred_at",
                "projection_state",
                "record_domain",
                "record_sha256",
                "sequence",
                "stream_id",
                "transition_id",
            },
        )
        self.assertIsNone(human_events[0]["transition_id"])
        self.assertEqual(human_events[1]["transition_id"], "TR-087")

        intervention = detail["interventions"][0]
        self.assertEqual(
            set(intervention),
            {
                "action_occurred_at",
                "created_at",
                "head_sha256",
                "intervention_id",
                "intervention_type",
                "opportunity_id",
                "projection_version",
                "record_domain",
                "record_sha256",
                "status",
                "verification_events",
            },
        )
        self.assertEqual(intervention["intervention_type"], "FULFILLMENT_SPLIT")
        self.assertEqual(intervention["status"], "VERIFIED_ACTIVE")
        self.assertEqual(
            set(intervention["verification_events"][0]),
            {"event_id", "occurrence_id", "record_domain", "record_sha256"},
        )

        link = detail["resulting_order_links"][0]
        self.assertEqual(
            set(link),
            {
                "child_order_id",
                "current_revision",
                "head_sha256",
                "intervention_id",
                "link_id",
                "parent_order_id",
                "revisions",
                "state",
            },
        )
        self.assertEqual(link["state"], "AUTO_LINKED")
        self.assertEqual([item["revision"] for item in link["revisions"]], [1, 2])
        self.assertEqual(link["revisions"][0]["mapping_components"], [])
        mappings = link["revisions"][1]["mapping_components"]
        self.assertEqual([item["ordinal"] for item in mappings], [1, 2])
        self.assertEqual(
            set(mappings[0]),
            {"child_line_id", "ordinal", "parent_line_id", "quantity_text"},
        )

        values = detail["value_events"]
        self.assertEqual([item["sequence"] for item in values], [1, 2])
        self.assertEqual([item["amount_minor_units"] for item in values], [600, -100])
        self.assertEqual(
            set(values[0]),
            {
                "amount_minor_units",
                "currency_code",
                "currency_registry_version",
                "currency_scale",
                "event_id",
                "event_type",
                "intervention_id",
                "occurrence_id",
                "predecessor_sha256",
                "record_domain",
                "record_sha256",
                "sequence",
            },
        )
        self.assertEqual(values[0]["currency_code"], "USD")
        self.assertEqual(values[0]["currency_registry_version"], CURRENCY_REGISTRY_VERSION)
        self.assertEqual(values[0]["currency_scale"], 2)

        contribution = detail["retained_kpi_contributions"][0]
        self.assertEqual(
            set(contribution),
            {
                "action_date",
                "amount_minor_units",
                "currency_code",
                "currency_registry_version",
                "currency_scale",
                "head_sha256",
                "intervention_id",
                "intervention_type",
                "revision",
            },
        )
        self.assertEqual(contribution["amount_minor_units"], 500)
        self.assertEqual(contribution["currency_code"], "USD")

        serialized = json.dumps(detail, sort_keys=True)
        for prohibited in (
            "PRIVATE-M7-DOI-PAYLOAD-SENTINEL",
            "record_payload",
            "record_canonical_bytes",
            "projection_payload",
            self.temporary.name,
        ):
            self.assertNotIn(prohibited, serialized)

    def test_doi_detail_unknown_retained_reason_fails_closed(self) -> None:
        self._insert_doi_case(
            8,
            currency="USD",
            amount="8.00",
            aggregate_state="AVAILABLE",
            selection_state="NOT_REQUIRED",
        )
        with self.database.write() as connection:
            connection.execute(
                "INSERT INTO doi_evaluation_reasons (evaluation_id, reason_code, "
                "owning_transition_id, effective_overlay, ordinal) "
                "VALUES ('SYN-EVALUATION-M7-DOI-8', 'RC-999', 'TR-001', 0, 2)"
            )
        with self.assertRaisesRegex(
            ControlCenterError,
            "DOI_REASON_REGISTRY_MISMATCH",
        ):
            self.application.doi_detail("SYN-EVIDENCE-M7-DOI-CASE-8")

    def test_current_attention_owner_envelope_mismatch_fails_closed(self) -> None:
        self._populate()
        self._insert_doi_detail_history()
        with self.database.write() as connection:
            stream_id = "SYN-EVIDENCE-M7-DOI-ATTENTION-TAMPERED-1"
            connection.execute(
                "INSERT INTO doi_owner_stream_anchors (stream_family, stream_id, case_id, "
                "run_id, created_at) VALUES ('ATTENTION', ?, ?, NULL, ?)",
                (
                    stream_id,
                    "SYN-EVIDENCE-M7-DOI-CASE-1",
                    "2026-08-31T17:06:05Z",
                ),
            )
            connection.execute(
                "INSERT INTO doi_owner_streams (stream_id, stream_family, case_id, run_id, "
                "current_state, sequence_no, head_sha256, projection_payload) "
                "VALUES (?, 'ATTENTION', ?, NULL, 'SET', 1, ?, ?)",
                (stream_id, "SYN-EVIDENCE-M7-DOI-CASE-1", SHA_A, b"{}"),
            )
            connection.execute(
                "INSERT INTO doi_owner_events (stream_family, stream_id, event_id, "
                "sequence_no, transition_id, projection_state, predecessor_sha256, "
                "occurred_at, record_domain, record_sha256, record_canonical_bytes, "
                "record_payload) VALUES ('ATTENTION', ?, ?, 1, 'TR-020', 'SET', NULL, ?, "
                "'doi-owner-event-envelope/v1', ?, ?, ?)",
                (
                    stream_id,
                    "SYN-EVIDENCE-M7-DOI-ATTENTION-TAMPERED-EVENT-1",
                    "2026-08-31T17:06:05Z",
                    SHA_A,
                    b"{}",
                    b"[]",
                ),
            )
        with self.assertRaisesRegex(
            ControlCenterError,
            "DOI_ATTENTION_BINDING_INVALID",
        ):
            self.application.doi_detail("SYN-EVIDENCE-M7-DOI-CASE-1")

    def test_metric_window_is_half_open(self) -> None:
        self._populate()
        metrics = self.application.metrics(
            MetricWindow("2026-08-31T17:00:12Z", "2026-08-31T17:00:14Z")
        )
        self.assertEqual(metrics.requests_received, 2)
        self.assertEqual(metrics.exact_replays, 1)
        self.assertEqual(metrics.material_conflicts, 1)

    def test_all_five_extension_states(self) -> None:
        expected = "0.1.2"
        states = {
            classify_extension_status(
                expected_version=expected,
                expected_package_sha256=SHA_A,
                package_available=True,
                observation=None,
                now=NOW,
            ).state,
            classify_extension_status(
                expected_version=expected,
                expected_package_sha256=SHA_A,
                package_available=False,
                observation=None,
                now=NOW,
            ).state,
            classify_extension_status(
                expected_version=expected,
                expected_package_sha256=SHA_A,
                package_available=True,
                observation=ExtensionObservation(expected, NOW - timedelta(minutes=1)),
                now=NOW,
            ).state,
            classify_extension_status(
                expected_version=expected,
                expected_package_sha256=SHA_A,
                package_available=True,
                observation=ExtensionObservation(expected, NOW - timedelta(minutes=6)),
                now=NOW,
            ).state,
            classify_extension_status(
                expected_version=expected,
                expected_package_sha256=SHA_A,
                package_available=True,
                observation=ExtensionObservation("0.1.0", NOW),
                now=NOW,
            ).state,
        }
        self.assertEqual(states, ExtensionStatusState.ALL)

    def test_database_view_hides_absolute_path_and_keeps_schema_four(self) -> None:
        view = self.application.database_view(deep=True)
        database = view["database"]
        self.assertIsInstance(database, dict)
        assert isinstance(database, dict)
        self.assertEqual(database["schema_version"], 4)
        self.assertIn(
            database["database_location_class"],
            {"LOCAL_APPLICATION_DATA", "LOCAL_TEMPORARY", "LOCAL_FILESYSTEM"},
        )
        self.assertNotIn(self.temporary.name, json.dumps(view))


if __name__ == "__main__":
    unittest.main()
