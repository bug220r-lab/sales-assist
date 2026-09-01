from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from synthetic_sales_assist.application.control_center import ControlCenterApplication
from synthetic_sales_assist.application.control_center_actions import ControlCenterActionError
from synthetic_sales_assist.application.scenarios import ScenarioApplication


class Milestone7ActionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="synthetic-sales-assist-m7-actions-")
        self.addCleanup(temporary.cleanup)
        self.data_root = Path(temporary.name) / "owned-local-data"
        self.scenarios = ScenarioApplication.open(self.data_root)
        self.control_center = ControlCenterApplication(
            self.scenarios.database,
            scenario_application=self.scenarios,
        )

    def test_sales_credit_manager_outcome_success_replay_conflict_and_separation(
        self,
    ) -> None:
        order = self.scenarios.instantiate(
            "sales-credit-human-review",
            "m7-sc-outcome-instance",
        )
        evaluated = self.scenarios.evaluate(order.order_id, "m7-sc-evaluate")
        before = self.scenarios.get_order(order.order_id).latest_evaluation
        self.assertIsNotNone(before)
        with self.scenarios.database.read() as connection:
            before_attribution = connection.execute(
                "SELECT attribution FROM sc_cases WHERE order_id=?",
                (order.order_id,),
            ).fetchone()[0]
        values = {
            "actor_id": "SYN-REP-M7-MANAGER",
            "outcome": "APPROVED",
            "amount_minor_units": None,
            "currency_code": None,
            "request_key": "m7-sc-manager-outcome",
            "confirmed": True,
            "decided_at": "2026-09-01T12:00:00Z",
        }
        first = self.control_center.record_sales_credit_manager_outcome(
            order.order_id,
            **values,
        )
        replay = self.control_center.record_sales_credit_manager_outcome(
            order.order_id,
            **values,
        )
        self.assertEqual(first["status"], "RECORDED")
        self.assertEqual(replay["status"], "EXACT_REPLAY")
        self.assertEqual(first["command_id"], replay["command_id"])
        self.assertEqual(self.control_center.sales_credit_cases().total_count, 0)
        closed_detail = self.control_center.sales_credit_detail(order.order_id)
        self.assertEqual(closed_detail["summary"]["workflow_state"], "CLOSED")
        self.assertEqual(closed_detail["summary"]["manager_outcome"], "APPROVED")
        self.assertEqual(len(closed_detail["manager_outcomes"]), 1)
        with self.assertRaises(ControlCenterActionError) as conflict:
            self.control_center.record_sales_credit_manager_outcome(
                order.order_id,
                **{**values, "outcome": "DENIED"},
            )
        self.assertEqual(conflict.exception.category, "CONFLICT")
        after = self.scenarios.get_order(order.order_id).latest_evaluation
        self.assertEqual(before, after)
        with self.scenarios.database.read() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM sc_manager_outcomes WHERE order_id=?",
                    (order.order_id,),
                ).fetchone()[0],
                1,
            )
            event = connection.execute(
                "SELECT manager_outcome, attribution FROM sc_case_events "
                "WHERE order_id=? AND event_kind='OUTCOME_RECORDED'",
                (order.order_id,),
            ).fetchone()
        self.assertEqual(tuple(event), ("APPROVED", before_attribution))

    def test_partial_requires_exact_currency_money(self) -> None:
        order = self.scenarios.instantiate(
            "sales-credit-human-review",
            "m7-sc-partial-instance",
        )
        self.scenarios.evaluate(order.order_id, "m7-sc-partial-evaluate")
        base = {
            "actor_id": "SYN-REP-M7-MANAGER",
            "outcome": "PARTIAL",
            "request_key": "m7-sc-partial-outcome",
            "confirmed": True,
            "decided_at": "2026-09-01T12:00:01Z",
        }
        with self.assertRaises(ControlCenterActionError):
            self.control_center.record_sales_credit_manager_outcome(
                order.order_id,
                amount_minor_units=None,
                currency_code=None,
                **base,
            )
        result = self.control_center.record_sales_credit_manager_outcome(
            order.order_id,
            amount_minor_units=1250,
            currency_code="USD",
            **base,
        )
        self.assertEqual(result["status"], "RECORDED")
        outcome = self.control_center.sales_credit_detail(order.order_id)[
            "manager_outcomes"
        ][0]
        self.assertEqual(outcome["amount_minor_units"], 1250)
        self.assertEqual(outcome["currency_code"], "USD")
        self.assertEqual(outcome["currency_scale"], 2)
        self.assertIsNotNone(outcome["currency_registry_version"])

    def test_doi_overlap_selection_is_atomic_replayable_and_conflicting(self) -> None:
        order = self.scenarios.instantiate("doi-overlap", "m7-doi-overlap-instance")
        evaluated = self.scenarios.evaluate(order.order_id, "m7-doi-overlap-evaluate")
        self.assertIsNotNone(evaluated.case_id)
        self.assertIsNotNone(evaluated.evaluation_id)
        case_id = str(evaluated.case_id)
        detail = self.control_center.doi_detail(case_id)
        self.assertIsNone(detail["scenario_selection"])
        opportunities = detail["opportunities"]
        self.assertIsInstance(opportunities, list)
        option_ids = tuple(sorted(str(item["opportunity_id"]) for item in opportunities))
        selected = next(
            str(item["opportunity_id"])
            for item in opportunities
            if item["opportunity_type"] == "EXACT_SKU_RECHECK"
        )
        values = {
            "evaluation_id": str(evaluated.evaluation_id),
            "actor_id": "SYN-REP-M7-DOI-MANAGER",
            "selected_opportunity_id": selected,
            "option_opportunity_ids": option_ids,
            "request_key": "m7-doi-scenario-selection",
            "confirmed": True,
            "occurred_at": "2026-09-01T12:00:02Z",
        }
        first = self.control_center.record_doi_overlap_selection(case_id, **values)
        replay = self.control_center.record_doi_overlap_selection(case_id, **values)
        self.assertEqual(first["status"], "RECORDED")
        self.assertEqual(replay["status"], "EXACT_REPLAY")
        self.assertEqual(first["evaluation_id"], replay["evaluation_id"])
        selected_detail = self.control_center.doi_detail(case_id)
        current_options = tuple(
            sorted(
                str(item["opportunity_id"])
                for item in selected_detail["opportunities"]
            )
        )
        current_selected = next(
            str(item["opportunity_id"])
            for item in selected_detail["opportunities"]
            if item["opportunity_type"] == "EXACT_SKU_RECHECK"
        )
        self.assertEqual(
            selected_detail["scenario_selection"]["option_opportunity_ids"],
            list(current_options),
        )
        self.assertEqual(
            selected_detail["scenario_selection"]["selected_opportunity_id"],
            current_selected,
        )
        self.assertTrue(
            selected_detail["scenario_selection"]["selection_id"].startswith(
                "SYN-EVIDENCE-M7-DOI-SELECTION-"
            )
        )
        other = next(value for value in option_ids if value != selected)
        with self.assertRaises(ControlCenterActionError) as conflict:
            self.control_center.record_doi_overlap_selection(
                case_id,
                **{**values, "selected_opportunity_id": other},
            )
        self.assertEqual(conflict.exception.category, "CONFLICT")
        current = self.control_center.doi_detail(case_id)
        self.assertEqual(current["scenario_selection"], selected_detail["scenario_selection"])
        self.assertEqual(current["summary"]["scenario_selection_state"], "SELECTED")
        self.assertNotEqual(
            current["summary"]["current_evaluation_id"],
            evaluated.evaluation_id,
        )
        event_kinds = {item["event_kind"] for item in current["timeline"]}
        self.assertIn("ACTION_CONTEXT", event_kinds)
        self.assertIn("HUMAN_FACT", event_kinds)
        with self.scenarios.database.read() as connection:
            counts = tuple(
                connection.execute(statement, (case_id,)).fetchone()[0]
                for statement in (
                    "SELECT COUNT(*) FROM doi_evaluations WHERE case_id=?",
                    "SELECT COUNT(*) FROM doi_owner_events e JOIN doi_owner_streams s "
                    "ON s.stream_family=e.stream_family AND s.stream_id=e.stream_id "
                    "WHERE s.case_id=? AND e.stream_family='ACTION_CONTEXT'",
                    "SELECT COUNT(*) FROM doi_owner_events e JOIN doi_owner_streams s "
                    "ON s.stream_family=e.stream_family AND s.stream_id=e.stream_id "
                    "WHERE s.case_id=? AND e.stream_family='HUMAN_FACT'",
                )
            )
        self.assertEqual(counts, (2, 1, 1))

    def test_doi_overlap_selection_retains_its_action_source_across_restart(self) -> None:
        order = self.scenarios.instantiate(
            "doi-overlap",
            "m7-doi-overlap-restart-instance",
        )
        evaluated = self.scenarios.evaluate(
            order.order_id,
            "m7-doi-overlap-restart-evaluate",
        )
        self.assertIsNotNone(evaluated.case_id)
        self.assertIsNotNone(evaluated.evaluation_id)

        reopened = ScenarioApplication.open(self.data_root)
        control_center = ControlCenterApplication(
            reopened.database,
            scenario_application=reopened,
        )
        case_id = str(evaluated.case_id)
        detail = control_center.doi_detail(case_id)
        option_ids = tuple(
            sorted(str(item["opportunity_id"]) for item in detail["opportunities"])
        )
        selected = next(
            str(item["opportunity_id"])
            for item in detail["opportunities"]
            if item["opportunity_type"] == "EXACT_SKU_RECHECK"
        )
        result = control_center.record_doi_overlap_selection(
            case_id,
            evaluation_id=str(evaluated.evaluation_id),
            actor_id="SYN-REP-M7-DOI-MANAGER",
            selected_opportunity_id=selected,
            option_opportunity_ids=option_ids,
            request_key="m7-doi-scenario-selection-after-restart",
            confirmed=True,
            occurred_at="2026-09-01T12:00:03Z",
        )
        self.assertEqual(result["status"], "RECORDED")
        self.assertEqual(
            control_center.doi_detail(case_id)["summary"]["scenario_selection_state"],
            "SELECTED",
        )

    def test_backup_is_verified_privacy_safe_and_exact_replay(self) -> None:
        first = self.control_center.create_verified_backup(
            request_key="m7-verified-backup",
            confirmed=True,
        )
        replay = self.control_center.create_verified_backup(
            request_key="m7-verified-backup",
            confirmed=True,
        )
        self.assertEqual(first["status"], "RECORDED")
        self.assertEqual(replay["status"], "EXACT_REPLAY")
        self.assertEqual(first["backup_sha256"], replay["backup_sha256"])
        self.assertEqual(first["location_class"], "OWNED_LOCAL_BACKUP_DIRECTORY")
        self.assertNotIn(str(self.data_root), repr(first))
        with self.assertRaises(ControlCenterActionError):
            self.control_center.create_verified_backup(
                request_key="m7-unconfirmed-backup",
                confirmed=False,
            )


if __name__ == "__main__":
    unittest.main()
