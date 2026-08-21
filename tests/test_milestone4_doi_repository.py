from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from synthetic_sales_assist.doi.demo import DOI_DEMOS, execute_doi_demo
from synthetic_sales_assist.persistence.database import SQLiteDatabase
from synthetic_sales_assist.persistence.doi_repository import DOIRepository
from synthetic_sales_assist.persistence.doi_services import DOIPersistenceService


class Milestone4DOIRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "doi.sqlite3"
        self.database = SQLiteDatabase(self.path)
        verification = self.database.initialize()
        self.assertEqual(verification.schema_version, 4)
        self.service = DOIPersistenceService(self.database)

    def test_schema_covers_every_durable_logical_group(self) -> None:
        required = {
            "doi_source_batches",
            "doi_runs",
            "doi_run_events",
            "doi_source_import_attempts",
            "doi_staged_orders",
            "doi_rejected_source_records",
            "doi_cases",
            "doi_order_snapshots",
            "doi_line_snapshots",
            "doi_evaluations",
            "doi_evaluation_reasons",
            "doi_opportunities",
            "doi_opportunity_scope_components",
            "doi_product_relationship_revisions",
            "doi_product_observations",
            "doi_owner_streams",
            "doi_owner_events",
            "doi_interventions",
            "doi_action_verification_events",
            "doi_value_events",
            "doi_resulting_order_links",
            "doi_kpi_contribution_events",
            "doi_kpi_daily_buckets",
            "doi_retention_deadlines",
        }
        with self.database.read() as connection:
            actual = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_schema WHERE type='table' AND name LIKE 'doi_%'"
                )
            }
            version = connection.execute(
                "SELECT latest_schema_version FROM application_metadata WHERE singleton=1"
            ).fetchone()[0]
        self.assertEqual(version, 4)
        self.assertTrue(required.issubset(actual), sorted(required - actual))

    def test_every_demo_round_trips_as_valid_domain_types_after_reopen(self) -> None:
        executions = tuple(execute_doi_demo(row.alias) for row in DOI_DEMOS)
        for execution in executions:
            result = self.service.persist_demo(execution)
            self.assertFalse(result.replayed)

        reopened = DOIPersistenceService(SQLiteDatabase(self.path))
        for execution in executions:
            with self.subTest(alias=execution.definition.alias):
                retained = reopened.get_evaluation(
                    execution.evaluation.evaluation_id.value
                )
                self.assertEqual(retained, execution.evaluation)
                self.assertEqual(
                    retained.hash_binding(),
                    execution.evaluation.hash_binding(),
                )
                history = reopened.run_history(
                    execution.evaluation.run_id.to_json_value()
                )
                self.assertEqual(history, (execution.run_start.run_event,))
        self.assertTrue(reopened.verify_projections().ok)

    def test_reason_transition_ownership_and_scope_are_normalized_exactly(self) -> None:
        execution = execute_doi_demo("doi-overlap")
        self.service.persist_demo(execution)
        evaluation = execution.evaluation
        with self.database.read() as connection:
            reasons = tuple(
                tuple(row)
                for row in connection.execute(
                    "SELECT reason_code, owning_transition_id, effective_overlay "
                    "FROM doi_evaluation_reasons WHERE evaluation_id=? ORDER BY ordinal",
                    (evaluation.evaluation_id.value,),
                )
            )
            scopes = tuple(
                tuple(row)
                for row in connection.execute(
                    "SELECT opportunity_id, line_snapshot_id, role, quantity_text "
                    "FROM doi_opportunity_scope_components ORDER BY opportunity_id, ordinal"
                )
            )
        expected_reasons = tuple(
            (
                route.reason.code,
                None
                if route.owning_transition is None
                else route.owning_transition.transition_id,
                int(route.effective_overlay),
            )
            for route in evaluation.reason_routes
        )
        self.assertEqual(reasons, expected_reasons)
        expected_scopes = tuple(
            (
                opportunity.opportunity_id.value,
                component.line_snapshot_id.to_json_value(),
                component.role.value,
                component.quantity.to_json_value(),
            )
            for opportunity in evaluation.opportunities
            for component in opportunity.scope.components
        )
        self.assertEqual(scopes, expected_scopes)
        rc087 = next(row for row in reasons if row[0] == "RC-087")
        self.assertEqual(rc087, ("RC-087", "TR-034", 1))

    def test_immutable_records_reject_direct_sql_update(self) -> None:
        execution = execute_doi_demo("doi-fulfillment-split")
        self.service.persist_demo(execution)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "DOI_IMMUTABLE_RECORD"):
            with self.database.write() as connection:
                connection.execute(
                    "UPDATE doi_evaluations SET transition_id='TR-037' "
                    "WHERE evaluation_id=?",
                    (execution.evaluation.evaluation_id.value,),
                )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "DOI_IMMUTABLE_RECORD"):
            with self.database.write() as connection:
                connection.execute(
                    "UPDATE doi_case_artifacts SET created_at=created_at "
                    "WHERE artifact_kind='ORDER_SNAPSHOT'"
                )

    def test_projection_verifier_detects_drift_without_rebuilding(self) -> None:
        execution = execute_doi_demo("doi-fulfillment-split")
        self.service.persist_demo(execution)
        self.assertTrue(self.service.verify_projections().ok)
        with self.database.write() as connection:
            connection.execute(
                "UPDATE doi_case_projections SET head_sha256=?",
                ("0" * 64,),
            )
        report = self.service.verify_projections()
        self.assertFalse(report.ok)
        self.assertIn("DOI_CASE_PROJECTION_MISMATCH", report.errors)

    def test_repository_requires_an_explicit_transaction(self) -> None:
        connection = sqlite3.connect(self.path)
        self.addCleanup(connection.close)
        with self.assertRaisesRegex(RuntimeError, "DOI_ACTIVE_TRANSACTION_REQUIRED"):
            DOIRepository(connection)


if __name__ == "__main__":
    unittest.main()
