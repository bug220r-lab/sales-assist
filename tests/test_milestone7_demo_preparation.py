from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import cast

from synthetic_sales_assist.application import ScenarioApplication
from synthetic_sales_assist.application.control_center import ControlCenterApplication
from synthetic_sales_assist.domain.canonical import canonical_json_bytes
from synthetic_sales_assist.persistence.telemetry import SAFETY_COUNTER_NAMES
from tools.prepare_milestone7_demo import (
    DEMO_PREPARATION_SCHEMA_VERSION,
    prepare_demo,
)


EXPECTED_IDENTITIES = {
    "doi-fulfillment-split": {
        "case_id": "SYN-EVIDENCE-M4-DOI-CASE-CDBA2B0FD86833CD6C96515A",
        "evaluation_id": (
            "SYN-EVALUATION-DOI-DEMO-B3A345A9AAB76E0E-FULFILLMENT-SPLIT"
        ),
        "order_id": "SYN-ORDER-DOI-DEMO-B3A345A9AAB76E0E",
        "run_id": "SYN-RUN-DOI-DEMO-B3A345A9AAB76E0E-FULFILLMENT-SPLIT",
    },
    "doi-overlap": {
        "case_id": "SYN-EVIDENCE-M4-DOI-CASE-A153ABFE7BF6A864850763EF",
        "evaluation_id": "SYN-EVALUATION-DOI-DEMO-5B5294694586A283-OVERLAP",
        "order_id": "SYN-ORDER-DOI-DEMO-5B5294694586A283",
        "run_id": "SYN-RUN-DOI-DEMO-5B5294694586A283-OVERLAP",
    },
    "malformed-input": {
        "order_id": "SYN-ORDER-M5-MALFORMED-8499F4AC6427E3EF2B2EBA39",
    },
    "sales-credit-human-review": {
        "case_id": "SYN-ORDER-M5-SC-86229FF7F2E2100A",
        "evaluation_id": "SYN-EVALUATION-M5-SC-86229FF7F2E2100A",
        "order_id": "SYN-ORDER-M5-SC-86229FF7F2E2100A",
        "run_id": "SYN-RUN-M5-SC-86229FF7F2E2100A",
    },
    "sales-credit-target-rep": {
        "case_id": "SYN-ORDER-M5-SC-018FB80ED91C1EBD",
        "evaluation_id": "SYN-EVALUATION-M5-SC-018FB80ED91C1EBD",
        "order_id": "SYN-ORDER-M5-SC-018FB80ED91C1EBD",
        "run_id": "SYN-RUN-M5-SC-018FB80ED91C1EBD",
    },
}


class Milestone7DemoPreparationTests(unittest.TestCase):
    def test_exact_dataset_routes_pending_actions_and_idempotent_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            first = prepare_demo(data_dir)
            second = prepare_demo(data_dir)

            self.assertEqual(
                first["schema_version"],
                DEMO_PREPARATION_SCHEMA_VERSION,
            )
            self.assertEqual(first["database_schema_version"], 4)
            counters = cast(dict[str, int], first["safety_counters"])
            self.assertEqual(tuple(counters), SAFETY_COUNTER_NAMES)
            self.assertEqual(set(counters.values()), {0})
            self.assertEqual(first["evaluation_replay_count"], 0)
            self.assertFalse(first["all_evaluations_replayed"])
            self.assertEqual(second["evaluation_replay_count"], 4)
            self.assertTrue(second["all_evaluations_replayed"])
            rendered = canonical_json_bytes(first).decode("utf-8")
            self.assertNotIn(str(data_dir), rendered)
            self.assertNotIn("\\Users\\", rendered)

            first_scenarios = {
                item["alias"]: item
                for item in cast(list[dict[str, object]], first["scenarios"])
            }
            second_scenarios = {
                item["alias"]: item
                for item in cast(list[dict[str, object]], second["scenarios"])
            }
            self.assertEqual(set(first_scenarios), set(EXPECTED_IDENTITIES))
            for alias, expected in EXPECTED_IDENTITIES.items():
                with self.subTest(alias=alias):
                    self.assertEqual(
                        {key: first_scenarios[alias][key] for key in expected},
                        expected,
                    )
                    self.assertEqual(
                        {key: second_scenarios[alias][key] for key in expected},
                        expected,
                    )
                    self.assertFalse(first_scenarios[alias]["instance_preexisting"])
                    self.assertTrue(second_scenarios[alias]["instance_preexisting"])

            malformed = first_scenarios["malformed-input"]
            self.assertFalse(malformed["evaluated"])
            self.assertEqual(malformed["source_status"], "INCOMPLETE")
            self.assertNotIn("evaluation_id", malformed)
            for alias in set(EXPECTED_IDENTITIES) - {"malformed-input"}:
                self.assertFalse(first_scenarios[alias]["evaluation_replayed"])
                self.assertTrue(second_scenarios[alias]["evaluation_replayed"])

            expected_routes = [
                "/system",
                "/overview",
                "/sales-credit/SYN-ORDER-M5-SC-018FB80ED91C1EBD",
                "/sales-credit/SYN-ORDER-M5-SC-86229FF7F2E2100A",
                "/doi/SYN-EVIDENCE-M4-DOI-CASE-CDBA2B0FD86833CD6C96515A",
                "/doi/SYN-EVIDENCE-M4-DOI-CASE-A153ABFE7BF6A864850763EF",
                "/review",
                "/audit/evaluation/"
                "SYN-EVALUATION-DOI-DEMO-5B5294694586A283-OVERLAP",
                "/orders/SYN-ORDER-M5-SC-018FB80ED91C1EBD",
                "/orders/SYN-ORDER-M5-MALFORMED-8499F4AC6427E3EF2B2EBA39",
                "/system/telemetry",
                "/system/backups",
            ]
            self.assertEqual(
                [
                    item["route"]
                    for item in cast(list[dict[str, object]], first["route_sequence"])
                ],
                expected_routes,
            )
            self.assertEqual(
                [
                    item["step"]
                    for item in cast(list[dict[str, object]], first["route_sequence"])
                ],
                list(range(1, 13)),
            )
            self.assertEqual(first["route_sequence"], second["route_sequence"])
            self.assertEqual(
                first["human_actions"],
                {
                    "doi_overlap_selection": "PENDING_MANUAL_CONFIRMATION",
                    "sales_credit_manager_outcome": "PENDING_MANUAL_CONFIRMATION",
                },
            )

            application = ScenarioApplication.open(data_dir)
            control_center = ControlCenterApplication(
                application.database,
                scenario_application=application,
            )
            sales_credit = control_center.sales_credit_detail(
                EXPECTED_IDENTITIES["sales-credit-human-review"]["order_id"]
            )
            doi = control_center.doi_detail(
                EXPECTED_IDENTITIES["doi-overlap"]["case_id"]
            )
            self.assertIsNone(sales_credit["summary"]["manager_outcome"])
            self.assertEqual(sales_credit["manager_outcomes"], [])
            self.assertEqual(doi["summary"]["scenario_selection_state"], "REQUIRED")
            self.assertEqual(doi["human_fact_events"], [])
            self.assertEqual(doi["interventions"], [])
            self.assertEqual(doi["resulting_order_links"], [])


if __name__ == "__main__":
    unittest.main()
