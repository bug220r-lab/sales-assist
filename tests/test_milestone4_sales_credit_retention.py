from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from synthetic_sales_assist.domain.identities import EvidenceId
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.persistence.database import SQLiteDatabase
from synthetic_sales_assist.persistence.faults import (
    FaultInjector,
    FaultPoint,
    InjectedPersistenceFault,
)
from synthetic_sales_assist.persistence.projections import ProjectionVerifier
from synthetic_sales_assist.persistence.retention import SalesCreditRetentionService
from synthetic_sales_assist.persistence.sales_credit_repository import (
    SalesCreditPersistenceConflict,
)
from synthetic_sales_assist.persistence.sales_credit_services import (
    SalesCreditPersistenceService,
)
from synthetic_sales_assist.sales_credit.fixtures import milestone2_case_mutation
from synthetic_sales_assist.sales_credit.models import SalesCreditCase, WorkflowState
from synthetic_sales_assist.sales_credit.retention import build_closure_projection


FIXED_TIME = datetime(2026, 8, 22, 16, 0, tzinfo=timezone.utc)
CLOSED_AT = CanonicalTimestamp("2026-08-22T16:00:00Z")


def _closure_projection():
    mutation = milestone2_case_mutation()
    assert mutation.evaluation is not None
    case = SalesCreditCase(
        order_id=mutation.order_id,
        interaction_ids=tuple(item.interaction_id for item in mutation.interactions),
        snapshot_ids=tuple(item.snapshot_id for item in mutation.snapshots),
        evidence_ids=tuple(item.evidence_id for item in mutation.evidence),
        evaluation_ids=(mutation.evaluation.evaluation_id,),
        attribution=mutation.evaluation.attribution.classification,
        order_value_status=mutation.evaluation.value.status,
        placed_value=mutation.evaluation.value.placed_value,
        workflow_state=mutation.evaluation.workflow_state,
        replacement_parent=None,
        manager_outcome=None,
        created_at=mutation.occurred_at,
        updated_at=mutation.occurred_at,
    )
    projection = build_closure_projection(
        case=case,
        interactions=mutation.interactions,
        evidence=mutation.evidence,
        evaluation=mutation.evaluation,
        closed_at=CLOSED_AT,
    )
    return mutation, projection


def _plus_days(value: CanonicalTimestamp, days: int) -> CanonicalTimestamp:
    instant = datetime.fromtimestamp(value.epoch_seconds, tz=timezone.utc) + timedelta(
        days=days
    )
    return CanonicalTimestamp(instant.isoformat(timespec="seconds").replace("+00:00", "Z"))


class Milestone4SalesCreditRetentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ssa-m4-sc-retention-")
        self.addCleanup(self.temporary.cleanup)
        self.database = SQLiteDatabase(
            Path(self.temporary.name) / "sales-credit-retention.sqlite3",
            clock=lambda: FIXED_TIME,
        )
        self.database.initialize()
        self.service = SalesCreditPersistenceService(self.database)
        self.retention = SalesCreditRetentionService(self.database)

    def close_case(self):
        mutation, projection = _closure_projection()
        self.service.persist_case_mutation(mutation, request_key="retention-mutation")
        result = self.service.close_and_minimize_case(
            projection=projection,
            audit_id=EvidenceId("SYN-EVIDENCE-M4-CLOSED-AUDIT-0001"),
            request_key="retention-close",
        )
        return mutation, projection, result

    def test_closure_atomically_minimizes_active_detail_and_exactly_replays(self) -> None:
        mutation, projection, first = self.close_case()
        replay = self.service.close_and_minimize_case(
            projection=projection,
            audit_id=EvidenceId("SYN-EVIDENCE-M4-CLOSED-AUDIT-0001"),
            request_key="retention-close",
        )
        case = self.service.get_case(mutation.order_id)
        history = self.service.case_history(mutation.order_id)

        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        assert case is not None
        self.assertIs(case.workflow_state, WorkflowState.CLOSED)
        self.assertIsNone(case.placed_value)
        self.assertIsNone(case.current_evaluation_id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].event_kind, "CLOSED_MINIMIZED")
        self.assertTrue(ProjectionVerifier(self.database).verify_sales_credit().valid)
        with self.database.read() as connection:
            active_counts = tuple(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "sc_case_interactions",
                    "sc_case_search_runs",
                    "sc_case_snapshots",
                    "sc_case_evidence",
                    "sc_case_evaluations",
                    "sc_manager_outcomes",
                )
            )
            audit = connection.execute(
                """
                SELECT canonical_bytes, purge_eligible_at
                FROM sc_closed_audits WHERE order_id = ?
                """,
                (mutation.order_id.value,),
            ).fetchone()
        self.assertEqual(active_counts, (0, 0, 0, 0, 0, 0))
        self.assertEqual(bytes(audit[0]), projection.record.canonical_bytes())
        self.assertEqual(audit[1], _plus_days(CLOSED_AT, 90).value)
        self.assertNotIn(b"@example.test", bytes(audit[0]))

    def test_fault_during_closure_rolls_back_to_complete_active_case(self) -> None:
        mutation, projection = _closure_projection()
        self.service.persist_case_mutation(mutation)
        with self.assertRaises(InjectedPersistenceFault):
            self.service.close_and_minimize_case(
                projection=projection,
                audit_id=EvidenceId("SYN-EVIDENCE-M4-CLOSED-AUDIT-FAULT-0001"),
                fault_injector=FaultInjector(
                    frozenset({FaultPoint.AFTER_EVENT_BEFORE_PROJECTION})
                ),
            )
        case = self.service.get_case(mutation.order_id)
        assert case is not None
        self.assertIsNot(case.workflow_state, WorkflowState.CLOSED)
        self.assertEqual(len(self.service.case_history(mutation.order_id)), 1)
        with self.database.read() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM sc_closed_audits").fetchone()[0],
                0,
            )
            self.assertGreater(
                connection.execute("SELECT COUNT(*) FROM sc_snapshots").fetchone()[0],
                0,
            )

    def test_closure_rejects_claimed_removal_counts_that_do_not_match_storage(self) -> None:
        mutation, projection = _closure_projection()
        self.service.persist_case_mutation(mutation)
        with self.assertRaisesRegex(
            SalesCreditPersistenceConflict,
            "CLOSURE_REMOVAL_COUNT_MISMATCH",
        ):
            self.service.close_and_minimize_case(
                projection=replace(
                    projection,
                    interactions_removed=projection.interactions_removed + 1,
                ),
                audit_id=EvidenceId("SYN-EVIDENCE-M4-CLOSED-AUDIT-MISMATCH-0001"),
            )
        self.assertIsNotNone(self.service.get_case(mutation.order_id))

    def test_exact_ninety_day_purge_is_idempotent_and_identity_free(self) -> None:
        mutation, _projection, _first = self.close_case()
        before = self.retention.purge_eligible_case(
            order_id=mutation.order_id,
            now=CanonicalTimestamp("2026-11-20T15:59:59.999999999Z"),
        )
        self.assertEqual(before.cases_deleted, 0)

        eligible = _plus_days(CLOSED_AT, 90)
        purged = self.retention.purge_eligible_case(
            order_id=mutation.order_id,
            now=eligible,
        )
        replay = self.retention.purge_eligible_case(
            order_id=mutation.order_id,
            now=eligible,
        )
        self.assertEqual(purged.cases_deleted, 1)
        self.assertEqual(purged.closed_audits_deleted, 1)
        self.assertEqual(replay.cases_deleted, 0)
        self.assertIsNone(self.service.get_case(mutation.order_id))
        with self.database.read() as connection:
            identity_hits = 0
            for table, column in (
                ("sc_cases", "order_id"),
                ("sc_case_events", "order_id"),
                ("sc_closed_audits", "order_id"),
                ("durable_receipt_owners", "owner_id"),
            ):
                identity_hits += connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {column} = ?",
                    (mutation.order_id.value,),
                ).fetchone()[0]
            aggregate = tuple(
                tuple(row)
                for row in connection.execute(
                    """
                    SELECT business_date, result_class, occurrence_count
                    FROM sc_daily_aggregates
                    """
                ).fetchall()
            )
        self.assertEqual(identity_hits, 0)
        self.assertEqual(aggregate, (("2026-08-22", "PURGED_CLOSED_CASE", 1),))

    def test_purge_fault_rolls_back_and_retry_completes_once(self) -> None:
        mutation, _projection, _first = self.close_case()
        eligible = _plus_days(CLOSED_AT, 90)
        with self.assertRaises(InjectedPersistenceFault):
            self.retention.purge_eligible_case(
                order_id=mutation.order_id,
                now=eligible,
                fault_injector=FaultInjector(
                    frozenset({FaultPoint.DURING_CASE_PURGE})
                ),
            )
        self.assertIsNotNone(self.service.get_case(mutation.order_id))
        with self.database.read() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM sc_daily_aggregates").fetchone()[0],
                0,
            )
        retry = self.retention.purge_eligible_case(
            order_id=mutation.order_id,
            now=eligible,
        )
        self.assertEqual(retry.cases_deleted, 1)

    def test_projection_verifier_reports_a_guarded_projection_drift(self) -> None:
        mutation = milestone2_case_mutation()
        self.service.persist_case_mutation(mutation)
        with self.database.write() as connection:
            connection.execute("DROP TRIGGER sc_cases_version_guard")
            connection.execute(
                """
                UPDATE sc_cases
                SET projection_version = projection_version + 1,
                    last_event_sequence = last_event_sequence + 1,
                    last_event_id = 'SYN-EVIDENCE-M4-DRIFT-0001'
                WHERE order_id = ?
                """,
                (mutation.order_id.value,),
            )
        result = ProjectionVerifier(self.database).verify_sales_credit()
        self.assertFalse(result.valid)
        self.assertIn(
            f"{mutation.order_id.value}:PROJECTION_DRIFT",
            result.mismatches,
        )


if __name__ == "__main__":
    unittest.main()
