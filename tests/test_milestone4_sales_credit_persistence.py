from __future__ import annotations

import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from synthetic_sales_assist.domain.idempotency import IdempotencyConflictError
from synthetic_sales_assist.domain.identities import EvaluationId, EvidenceId, InteractionId
from synthetic_sales_assist.domain.records import VersionBinding
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.persistence.database import SQLiteDatabase
from synthetic_sales_assist.persistence.records import (
    PersistenceRecordError,
    StoredSalesCreditCase,
)
from synthetic_sales_assist.persistence.sales_credit_repository import (
    SalesCreditPersistenceConflict,
)
from synthetic_sales_assist.persistence.sales_credit_services import (
    SalesCreditPersistenceService,
)
from synthetic_sales_assist.sales_credit.accumulator import CaseMutation
from synthetic_sales_assist.sales_credit.discovery import (
    NativeSearchResultSet,
    SearchCompleteness,
    SearchIdentifier,
    SearchIdentifierKind,
)
from synthetic_sales_assist.sales_credit.evaluator import (
    KNOWN_OTHER_REP_CATALOG,
    evaluate_sales_credit,
)
from synthetic_sales_assist.sales_credit.fixtures import (
    _manager_outcome,
    milestone2_case_mutation,
)
from synthetic_sales_assist.sales_credit.models import (
    HumanOutcomeType,
    WorkflowState,
    order_provenance_binding,
)


FIXED_TIME = datetime(2026, 8, 21, 18, 0, tzinfo=timezone.utc)


def _multi_fact_mutation() -> CaseMutation:
    base = milestone2_case_mutation()
    original = base.interactions[0]
    second = replace(
        original,
        interaction_id=InteractionId("SYN-INTERACTION-M4-PERSIST-0002"),
        source_ref=EvidenceId("SYN-EVIDENCE-M4-INTERACTION-SOURCE-0002"),
        email="m4-second@example.test",
    )
    assert base.discovery_run is not None
    second_results = NativeSearchResultSet(
        identifier=SearchIdentifier(
            SearchIdentifierKind.EMAIL,
            "m4-second@example.test",
        ),
        completeness=SearchCompleteness.COMPLETE,
        order_ids=(base.order_id,),
    )
    result_sets = tuple(
        sorted(
            (*base.discovery_run.native_result_sets, second_results),
            key=lambda item: (item.identifier.kind.value, item.identifier.value),
        )
    )
    search_run = replace(
        base.discovery_run,
        interactions=(original, second),
        native_result_sets=result_sets,
    )

    first_snapshot = base.snapshots[0]
    second_captured_at = CanonicalTimestamp("2026-08-21T16:30:00Z")
    second_source = EvidenceId("SYN-EVIDENCE-M4-ORDER-SOURCE-0002")
    second_snapshot = replace(
        first_snapshot,
        snapshot_id=type(first_snapshot.snapshot_id)("SYN-SNAPSHOT-M4-PERSIST-0002"),
        source_ref=second_source,
        captured_at=second_captured_at,
        parser=VersionBinding("sales_credit_parser", "sales-credit-parser/v1"),
        provenance=order_provenance_binding(
            source_ref=second_source,
            captured_at=second_captured_at,
            parser=VersionBinding("sales_credit_parser", "sales-credit-parser/v1"),
        ),
    )
    evaluation = evaluate_sales_credit(
        evaluation_id=EvaluationId("SYN-EVALUATION-M4-PERSIST-0002"),
        expected_order_id=base.order_id,
        snapshot=second_snapshot,
        evaluated_at=base.occurred_at,
        known_other_reps=KNOWN_OTHER_REP_CATALOG,
        interactions=(original, second),
        prior_snapshots=(first_snapshot,),
    )
    return replace(
        base,
        command_id=EvidenceId("SYN-EVIDENCE-M4-PERSIST-COMMAND-0001"),
        interactions=(original, second),
        snapshots=(first_snapshot, second_snapshot),
        evaluation=evaluation,
        discovery_run=search_run,
    )


class Milestone4SalesCreditPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ssa-m4-sc-")
        self.addCleanup(self.temporary.cleanup)
        self.database = SQLiteDatabase(
            Path(self.temporary.name) / "sales-credit.sqlite3",
            clock=lambda: FIXED_TIME,
        )
        self.database.initialize()
        self.service = SalesCreditPersistenceService(self.database)

    def test_typed_case_persists_multiple_interactions_snapshots_and_exact_money(self) -> None:
        mutation = _multi_fact_mutation()
        first = self.service.persist_case_mutation(mutation, request_key="multi-fact")
        replay = self.service.persist_case_mutation(mutation, request_key="multi-fact")
        case = self.service.get_case(mutation.order_id)

        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        self.assertIsInstance(case, StoredSalesCreditCase)
        assert case is not None
        assert mutation.evaluation is not None
        self.assertEqual(case.placed_value, mutation.evaluation.value.placed_value)
        self.assertIs(case.workflow_state, WorkflowState.CREDIT_CONFIRMED_TARGET_REP)
        self.assertTrue(self.service.verify_projections().valid)
        with self.database.read() as connection:
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "sc_interactions",
                    "sc_snapshots",
                    "sc_case_interactions",
                    "sc_case_snapshots",
                    "sc_evaluations",
                    "sc_case_events",
                )
            }
        self.assertEqual(counts["sc_interactions"], 2)
        self.assertEqual(counts["sc_snapshots"], 2)
        self.assertEqual(counts["sc_case_interactions"], 2)
        self.assertEqual(counts["sc_case_snapshots"], 2)
        self.assertEqual(counts["sc_evaluations"], 1)
        self.assertEqual(counts["sc_case_events"], 1)

    def test_immutable_roots_and_events_reject_direct_sql_update(self) -> None:
        mutation = milestone2_case_mutation()
        self.service.persist_case_mutation(mutation)
        attempts = (
            ("sc_interactions", "workflow_state = workflow_state"),
            ("sc_snapshots", "parser_version = parser_version"),
            ("sc_evaluations", "workflow_state = workflow_state"),
            ("sc_case_events", "event_kind = event_kind"),
        )
        for table, assignment in attempts:
            with self.subTest(table=table):
                with self.assertRaisesRegex(sqlite3.IntegrityError, "IMMUTABLE"):
                    with self.database.write() as connection:
                        connection.execute(f"UPDATE {table} SET {assignment}")

    def test_manager_outcome_replay_conflict_and_authority_are_enforced(self) -> None:
        mutation = milestone2_case_mutation()
        self.service.persist_case_mutation(mutation)
        outcome = _manager_outcome()
        first = self.service.record_manager_outcome(
            order_id=mutation.order_id,
            outcome=outcome,
            request_key="manager-outcome",
        )
        replay = self.service.record_manager_outcome(
            order_id=mutation.order_id,
            outcome=outcome,
            request_key="manager-outcome",
        )
        case = self.service.get_case(mutation.order_id)
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        assert case is not None
        self.assertIs(case.workflow_state, WorkflowState.CLOSED)
        self.assertEqual(case.manager_occurrence_id, outcome.occurrence_id)
        changed = replace(
            outcome,
            recorded_at=CanonicalTimestamp("2026-08-22T16:01:00Z"),
        )
        with self.assertRaises(IdempotencyConflictError):
            self.service.record_manager_outcome(
                order_id=mutation.order_id,
                outcome=changed,
                request_key="manager-outcome",
            )

        awaiting = replace(
            mutation,
            command_id=EvidenceId("SYN-EVIDENCE-M4-AWAITING-COMMAND-0001"),
            order_id=type(mutation.order_id)("SYN-ORDER-M4-AWAITING-0001"),
            snapshots=(),
            evaluation=None,
            discovery_run=None,
        )
        awaiting = replace(
            awaiting,
            interactions=tuple(
                replace(
                    item,
                    interaction_id=InteractionId("SYN-INTERACTION-M4-AWAITING-0001"),
                    source_ref=EvidenceId("SYN-EVIDENCE-M4-AWAITING-SOURCE-0001"),
                )
                for item in awaiting.interactions
            ),
        )
        self.service.persist_case_mutation(awaiting)
        with self.assertRaisesRegex(
            SalesCreditPersistenceConflict,
            "WORKFLOW_NOT_AUTHORIZED",
        ):
            self.service.record_manager_outcome(
                order_id=awaiting.order_id,
                outcome=replace(
                    outcome,
                    occurrence_id=EvidenceId("SYN-EVIDENCE-M4-AWAITING-OUTCOME-0001"),
                    outcome=HumanOutcomeType.DENIED,
                    approved_amount=None,
                ),
            )

    def test_stored_event_constructor_rejects_unvalidated_sequence(self) -> None:
        mutation = milestone2_case_mutation()
        self.service.persist_case_mutation(mutation)
        event = self.service.case_history(mutation.order_id)[0]
        with self.assertRaisesRegex(
            PersistenceRecordError,
            "STORED_SALES_CREDIT_EVENT_INVALID",
        ):
            replace(event, sequence=0)


if __name__ == "__main__":
    unittest.main()
