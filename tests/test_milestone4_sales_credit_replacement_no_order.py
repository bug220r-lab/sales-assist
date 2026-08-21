from __future__ import annotations

import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from synthetic_sales_assist.domain.identities import EvidenceId
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.persistence.database import SQLiteDatabase
from synthetic_sales_assist.persistence.faults import (
    FaultInjector,
    FaultPoint,
    InjectedPersistenceFault,
)
from synthetic_sales_assist.persistence.sales_credit_services import (
    SalesCreditPersistenceService,
)
from synthetic_sales_assist.persistence.records import PersistenceRecordError
from synthetic_sales_assist.sales_credit.models import SalesCreditCase, WorkflowState
from synthetic_sales_assist.sales_credit.retention import build_closure_projection
from tests.test_sales_credit_accumulator import (
    manager_outcome,
    replacement_evaluated_mutations,
)
from tests.test_sales_credit_no_order_closure import terminal_closure, terminal_run


FIXED_TIME = datetime(2026, 8, 22, 20, 0, tzinfo=timezone.utc)


class Milestone4SalesCreditReplacementNoOrderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ssa-m4-sc-relationships-")
        self.addCleanup(self.temporary.cleanup)
        self.database = SQLiteDatabase(
            Path(self.temporary.name) / "sales-credit-relationships.sqlite3",
            clock=lambda: FIXED_TIME,
        )
        self.database.initialize()
        self.service = SalesCreditPersistenceService(self.database)

    def test_relevant_replacement_candidate_gets_one_normalized_child_projection(self) -> None:
        parent, replacement = replacement_evaluated_mutations(
            "M4-REPLACEMENT-COMMAND-0001"
        )
        self.service.persist_case_mutation(parent, request_key="replacement-parent")
        first = self.service.persist_case_mutation(
            replacement,
            request_key="replacement-evaluation",
        )
        replay = self.service.persist_case_mutation(
            replacement,
            request_key="replacement-evaluation",
        )
        candidate = replacement.replacement_candidates[0].snapshot
        assert candidate.order_id is not None
        child = self.service.get_case(candidate.order_id)

        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        self.assertIsNotNone(child)
        assert child is not None
        self.assertEqual(child.replacement_parent, parent.order_id)
        self.assertIs(child.workflow_state, WorkflowState.AWAITING_SOURCE_REVIEW)
        self.assertEqual(len(self.service.case_history(candidate.order_id)), 1)
        verification = self.service.verify_projections()
        self.assertTrue(verification.valid, verification.mismatches)
        with self.database.read() as connection:
            counts = tuple(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "sc_replacement_candidates",
                    "sc_active_replacement_links",
                )
            )
            snapshot_owners = tuple(
                row[0]
                for row in connection.execute(
                    """
                    SELECT order_id FROM sc_case_snapshots
                    WHERE snapshot_id = ? ORDER BY order_id
                    """,
                    (candidate.snapshot_id.value,),
                ).fetchall()
            )
        self.assertEqual(counts, (1, 1))
        self.assertEqual(snapshot_owners, (candidate.order_id.value,))

    def test_parent_purge_detaches_surviving_replacement_child_and_run(self) -> None:
        parent, replacement = replacement_evaluated_mutations(
            "M4-REPLACEMENT-PURGE-0001"
        )
        self.service.persist_case_mutation(parent)
        self.service.persist_case_mutation(replacement)
        candidate_order = replacement.replacement_candidates[0].snapshot.order_id
        assert candidate_order is not None
        child_history_before_closure = self.service.case_history(candidate_order)
        self.assertEqual(len(child_history_before_closure), 1)
        self.assertIsNotNone(child_history_before_closure[0].command_id)
        with self.database.read() as connection:
            event_row_before = tuple(
                connection.execute(
                    "SELECT * FROM sc_case_events WHERE order_id = ?",
                    (candidate_order.value,),
                ).fetchone()
            )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "IMMUTABLE_SC_CASE_EVENT"):
            with self.database.write() as connection:
                connection.execute(
                    "UPDATE sc_case_events SET command_id = NULL WHERE order_id = ?",
                    (candidate_order.value,),
                )
        linked_child = self.service.get_case(candidate_order)
        linked_parent = self.service.get_case(parent.order_id)
        assert linked_child is not None
        assert linked_parent is not None
        with self.assertRaisesRegex(
            sqlite3.IntegrityError,
            "SALES_CREDIT_PROJECTION_CONFLICT",
        ):
            with self.database.write() as connection:
                connection.execute(
                    """
                    UPDATE sc_cases SET replacement_parent_order_id = NULL
                    WHERE order_id = ?
                    """,
                    (candidate_order.value,),
                )
        forked_event_id = "SYN-EVIDENCE-M4-SC-FORKED-DETACH-0001"
        self.assertNotEqual(linked_parent.last_event_id, linked_child.last_event_id)
        with self.assertRaisesRegex(
            sqlite3.IntegrityError,
            "SALES_CREDIT_PROJECTION_CONFLICT",
        ):
            with self.database.write() as connection:
                connection.execute(
                    """
                    INSERT INTO sc_case_events (
                        event_id, order_id, sequence, predecessor_event_id,
                        event_kind, workflow_state, attribution,
                        order_value_status, manager_outcome,
                        current_evaluation_id, replacement_parent_present,
                        occurred_at, command_id, canonical_bytes
                    ) VALUES (?, ?, ?, ?, 'REPLACEMENT_PARENT_DETACHED',
                              ?, ?, ?, NULL, ?, 0, ?, ?, ?)
                    """,
                    (
                        forked_event_id,
                        candidate_order.value,
                        linked_child.last_event_sequence + 1,
                        linked_parent.last_event_id.value,
                        linked_child.workflow_state.value,
                        linked_child.attribution.value,
                        linked_child.order_value_status.value,
                        None
                        if linked_child.current_evaluation_id is None
                        else linked_child.current_evaluation_id.value,
                        "2026-08-02T16:59:00Z",
                        "SYN-EVIDENCE-M4-SC-FORKED-DETACH-COMMAND-0001",
                        b"{}",
                    ),
                )
                connection.execute(
                    """
                    UPDATE sc_cases
                    SET projection_version = projection_version + 1,
                        replacement_parent_order_id = NULL,
                        last_event_sequence = ?, last_event_id = ?,
                        updated_at = ?
                    WHERE order_id = ? AND projection_version = ?
                      AND last_event_id = ?
                    """,
                    (
                        linked_child.last_event_sequence + 1,
                        forked_event_id,
                        "2026-08-02T16:59:00Z",
                        candidate_order.value,
                        linked_child.projection_version,
                        linked_child.last_event_id.value,
                    ),
                )
        self.assertEqual(self.service.get_case(candidate_order), linked_child)
        with self.database.read() as connection:
            self.assertIsNone(
                connection.execute(
                    "SELECT 1 FROM sc_case_events WHERE event_id = ?",
                    (forked_event_id,),
                ).fetchone()
            )
        outcome = manager_outcome(
            "M4-REPLACEMENT-OUTCOME-0001",
            decided_at="2026-08-02T17:00:00Z",
            recorded_at="2026-08-02T17:01:00Z",
        )
        self.service.record_manager_outcome(
            order_id=parent.order_id,
            outcome=outcome,
        )
        assert parent.evaluation is not None
        assert replacement.evaluation is not None
        case = SalesCreditCase(
            order_id=parent.order_id,
            interaction_ids=tuple(item.interaction_id for item in parent.interactions),
            snapshot_ids=tuple(item.snapshot_id for item in parent.snapshots),
            evidence_ids=(),
            evaluation_ids=tuple(
                sorted(
                    (
                        parent.evaluation.evaluation_id,
                        replacement.evaluation.evaluation_id,
                    ),
                    key=lambda item: item.value,
                )
            ),
            attribution=replacement.evaluation.attribution.classification,
            order_value_status=replacement.evaluation.value.status,
            placed_value=replacement.evaluation.value.placed_value,
            workflow_state=WorkflowState.CLOSED,
            replacement_parent=None,
            manager_outcome=outcome,
            created_at=parent.occurred_at,
            updated_at=outcome.recorded_at,
        )
        closed_at = CanonicalTimestamp("2026-08-02T18:00:00Z")
        projection = build_closure_projection(
            case=case,
            interactions=parent.interactions,
            evidence=(),
            evaluation=replacement.evaluation,
            closed_at=closed_at,
        )
        self.service.close_and_minimize_case(
            projection=projection,
            audit_id=EvidenceId("SYN-EVIDENCE-M4-REPLACEMENT-AUDIT-0001"),
        )
        child_before = self.service.get_case(candidate_order)
        assert child_before is not None
        self.assertEqual(child_before.replacement_parent, parent.order_id)
        child_history_before = self.service.case_history(candidate_order)
        self.assertEqual(len(child_history_before), 1)
        self.assertEqual(
            child_history_before[0].command_id,
            child_history_before_closure[0].command_id,
        )
        with self.database.read() as connection:
            event_rows_before_purge = tuple(
                tuple(row)
                for row in connection.execute(
                    """
                    SELECT * FROM sc_case_events
                    WHERE order_id = ? ORDER BY sequence
                    """,
                    (candidate_order.value,),
                ).fetchall()
            )
            parent_event_rows_before_purge = tuple(
                tuple(row)
                for row in connection.execute(
                    """
                    SELECT * FROM sc_case_events
                    WHERE order_id = ? ORDER BY sequence
                    """,
                    (parent.order_id.value,),
                ).fetchall()
            )
            case_rows_before_purge = tuple(
                tuple(row)
                for row in connection.execute(
                    """
                    SELECT * FROM sc_cases
                    WHERE order_id IN (?, ?) ORDER BY order_id
                    """,
                    (parent.order_id.value, candidate_order.value),
                ).fetchall()
            )
            link_rows_before_purge = tuple(
                tuple(row)
                for row in connection.execute(
                    "SELECT * FROM sc_active_replacement_links"
                ).fetchall()
            )
            audit_rows_before_purge = tuple(
                tuple(row)
                for row in connection.execute(
                    "SELECT * FROM sc_closed_audits WHERE order_id = ?",
                    (parent.order_id.value,),
                ).fetchall()
            )
        self.assertEqual(event_rows_before_purge, (event_row_before,))

        for fault_point in (
            FaultPoint.BEFORE_EVENT_APPEND,
            FaultPoint.AFTER_EVENT_BEFORE_PROJECTION,
            FaultPoint.AFTER_PROJECTION_BEFORE_RECEIPT,
            FaultPoint.BEFORE_COMMIT,
        ):
            with self.subTest(fault_point=fault_point.value):
                with self.assertRaises(InjectedPersistenceFault):
                    self.service.purge_closed_case(
                        order_id=parent.order_id,
                        now=CanonicalTimestamp("2026-10-31T18:00:00Z"),
                        fault_injector=FaultInjector(frozenset({fault_point})),
                    )
                self.assertEqual(self.service.get_case(candidate_order), child_before)
                with self.database.read() as connection:
                    retained_rows = tuple(
                        tuple(row)
                        for row in connection.execute(
                            """
                            SELECT * FROM sc_case_events
                            WHERE order_id = ? ORDER BY sequence
                            """,
                            (candidate_order.value,),
                        ).fetchall()
                    )
                    retained_parent_rows = tuple(
                        tuple(row)
                        for row in connection.execute(
                            """
                            SELECT * FROM sc_case_events
                            WHERE order_id = ? ORDER BY sequence
                            """,
                            (parent.order_id.value,),
                        ).fetchall()
                    )
                    retained_case_rows = tuple(
                        tuple(row)
                        for row in connection.execute(
                            """
                            SELECT * FROM sc_cases
                            WHERE order_id IN (?, ?) ORDER BY order_id
                            """,
                            (parent.order_id.value, candidate_order.value),
                        ).fetchall()
                    )
                    retained_link_rows = tuple(
                        tuple(row)
                        for row in connection.execute(
                            "SELECT * FROM sc_active_replacement_links"
                        ).fetchall()
                    )
                    retained_audit_rows = tuple(
                        tuple(row)
                        for row in connection.execute(
                            "SELECT * FROM sc_closed_audits WHERE order_id = ?",
                            (parent.order_id.value,),
                        ).fetchall()
                    )
                self.assertEqual(retained_rows, event_rows_before_purge)
                self.assertEqual(
                    retained_parent_rows,
                    parent_event_rows_before_purge,
                )
                self.assertEqual(retained_case_rows, case_rows_before_purge)
                self.assertEqual(retained_link_rows, link_rows_before_purge)
                self.assertEqual(retained_audit_rows, audit_rows_before_purge)
                verification_after_fault = self.service.verify_projections()
                self.assertTrue(
                    verification_after_fault.valid,
                    verification_after_fault.mismatches,
                )

        result = self.service.purge_closed_case(
            order_id=parent.order_id,
            now=CanonicalTimestamp("2026-10-31T18:00:00Z"),
        )

        self.assertEqual(result.cases_deleted, 1)
        child_after = self.service.get_case(candidate_order)
        assert child_after is not None
        self.assertIsNone(child_after.replacement_parent)
        child_history_after = self.service.case_history(candidate_order)
        self.assertEqual(len(child_history_after), 2)
        self.assertEqual(child_history_after[0], child_history_before[0])
        detach_event = child_history_after[1]
        self.assertEqual(detach_event.event_kind, "REPLACEMENT_PARENT_DETACHED")
        self.assertEqual(detach_event.sequence, child_before.last_event_sequence + 1)
        self.assertEqual(detach_event.predecessor_event_id, child_before.last_event_id)
        self.assertFalse(detach_event.replacement_parent_present)
        for invalid_presence in (1, True):
            with self.subTest(invalid_presence=invalid_presence):
                with self.assertRaisesRegex(
                    PersistenceRecordError,
                    "STORED_SALES_CREDIT_EVENT_INVALID",
                ):
                    replace(
                        detach_event,
                        replacement_parent_present=invalid_presence,
                    )
        self.assertEqual(child_after.last_event_id, detach_event.event_id)
        self.assertEqual(child_after.last_event_sequence, detach_event.sequence)
        self.assertEqual(
            child_after.projection_version,
            child_before.projection_version + 1,
        )
        verification = self.service.verify_projections()
        self.assertTrue(verification.valid, verification.mismatches)
        with self.database.read() as connection:
            event_rows_after = tuple(
                tuple(row)
                for row in connection.execute(
                    """
                    SELECT * FROM sc_case_events
                    WHERE order_id = ? ORDER BY sequence
                    """,
                    (candidate_order.value,),
                ).fetchall()
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM sc_active_replacement_links"
                ).fetchone()[0],
                0,
            )
            self.assertIsNone(
                connection.execute(
                    "SELECT 1 FROM sc_search_runs WHERE run_id = ?",
                    (replacement.replacement_run.run_id.value,),  # type: ignore[union-attr]
                ).fetchone()
            )
        self.assertEqual(event_rows_after[:-1], event_rows_before_purge)

    def test_no_order_closure_removes_active_identity_and_replays_durably(self) -> None:
        run = terminal_run()
        projection = terminal_closure().projection
        audit_id = EvidenceId("SYN-EVIDENCE-M4-NO-ORDER-AUDIT-0001")
        self.service.persist_interaction_search_result(run)
        first = self.service.close_and_minimize_no_order_run(
            run=run,
            projection=projection,
            audit_id=audit_id,
            request_key="no-order-close",
        )
        replay = self.service.close_and_minimize_no_order_run(
            run=run,
            projection=projection,
            audit_id=audit_id,
            request_key="no-order-close",
        )

        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        with self.database.read() as connection:
            retained = connection.execute(
                """
                SELECT canonical_bytes FROM sc_no_order_closed_audits
                WHERE audit_id = ?
                """,
                (audit_id.value,),
            ).fetchone()
            active_counts = (
                connection.execute("SELECT COUNT(*) FROM sc_search_runs").fetchone()[0],
                connection.execute("SELECT COUNT(*) FROM sc_interactions").fetchone()[0],
                connection.execute(
                    "SELECT COUNT(*) FROM sc_search_identifiers"
                ).fetchone()[0],
            )
        self.assertEqual(bytes(retained[0]), projection.record.canonical_bytes())
        self.assertEqual(active_counts, (0, 0, 0))
        serialized = bytes(retained[0])
        self.assertNotIn(run.run_id.value.encode("ascii"), serialized)
        for interaction in run.interactions:
            self.assertNotIn(interaction.interaction_id.value.encode("ascii"), serialized)

    def test_no_order_closure_fault_restores_active_run_and_purge_is_exact(self) -> None:
        run = terminal_run()
        projection = terminal_closure().projection
        audit_id = EvidenceId("SYN-EVIDENCE-M4-NO-ORDER-AUDIT-FAULT-0001")
        self.service.persist_interaction_search_result(run)
        with self.assertRaises(InjectedPersistenceFault):
            self.service.close_and_minimize_no_order_run(
                run=run,
                projection=projection,
                audit_id=audit_id,
                fault_injector=FaultInjector(
                    frozenset({FaultPoint.AFTER_PROJECTION_BEFORE_RECEIPT})
                ),
            )
        with self.database.read() as connection:
            self.assertIsNotNone(
                connection.execute(
                    "SELECT 1 FROM sc_search_runs WHERE run_id = ?",
                    (run.run_id.value,),
                ).fetchone()
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM sc_no_order_closed_audits"
                ).fetchone()[0],
                0,
            )

        self.service.close_and_minimize_no_order_run(
            run=run,
            projection=projection,
            audit_id=audit_id,
        )
        before = self.service.purge_no_order_audit(
            audit_id=audit_id,
            now=CanonicalTimestamp("2026-11-15T16:00:00Z"),
        )
        exact = self.service.purge_no_order_audit(
            audit_id=audit_id,
            now=CanonicalTimestamp("2026-11-15T16:00:00.000000001Z"),
        )
        replay = self.service.purge_no_order_audit(
            audit_id=audit_id,
            now=CanonicalTimestamp("2026-11-15T16:00:00.000000001Z"),
        )
        self.assertEqual((before, exact, replay), (0, 1, 0))
        with self.database.read() as connection:
            aggregate = connection.execute(
                """
                SELECT business_date, result_class, occurrence_count
                FROM sc_daily_aggregates
                WHERE result_class = 'PURGED_NO_ORDER_AUDIT'
                """
            ).fetchone()
        self.assertEqual(tuple(aggregate), ("2026-08-17", "PURGED_NO_ORDER_AUDIT", 1))


if __name__ == "__main__":
    unittest.main()
