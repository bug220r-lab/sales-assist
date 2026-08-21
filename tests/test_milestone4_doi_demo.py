from __future__ import annotations

import unittest

from synthetic_sales_assist.doi.demo import DOI_DEMOS, execute_doi_demo
from synthetic_sales_assist.doi.fixtures import scenario_catalog
from synthetic_sales_assist.doi.models import DOIState, ValueAvailabilityState
from synthetic_sales_assist.domain.registries import (
    EXPECTED_OWNERSHIP_COUNT,
    EXPECTED_REASON_COUNT,
    EXPECTED_TRANSITION_COUNT,
    load_doi_registries,
)


class Milestone4DOIDemoTests(unittest.TestCase):
    def test_required_aliases_are_exact_catalog_scenarios(self) -> None:
        catalog = {row.scenario_key: row for row in scenario_catalog()}
        self.assertEqual(
            tuple(row.alias for row in DOI_DEMOS),
            (
                "doi-fulfillment-split",
                "doi-full-ds",
                "doi-manual-review",
                "doi-overlap",
            ),
        )
        for definition in DOI_DEMOS:
            with self.subTest(alias=definition.alias):
                execution = execute_doi_demo(definition.alias)
                expected = catalog[definition.scenario_key]
                self.assertEqual(execution.scenario, expected)
                self.assertIs(execution.evaluation.state, expected.expected_top_level_state)
                self.assertEqual(
                    tuple(reason.code for reason in execution.evaluation.reasons.reasons),
                    tuple(reason.code for reason in expected.expected_reasons),
                )
                self.assertEqual(
                    execution.run_start.run.run_id,
                    execution.evaluation.run_id.value,
                )

    def test_overlay_results_remain_exact(self) -> None:
        manual = execute_doi_demo("doi-manual-review").evaluation
        self.assertIs(manual.state, DOIState.DOI_MANUAL_REVIEW)
        self.assertEqual(manual.transition.transition_id, "TR-037")
        self.assertEqual(
            tuple(reason.code for reason in manual.reasons.reasons),
            ("RC-016",),
        )

        overlap = execute_doi_demo("doi-overlap").evaluation
        self.assertIs(overlap.state, DOIState.DOI_OPPORTUNITY)
        self.assertEqual(overlap.transition.transition_id, "TR-034")
        self.assertEqual(len(overlap.opportunities), 2)
        self.assertIn("RC-087", {reason.code for reason in overlap.reasons.reasons})
        self.assertIs(
            overlap.aggregate_potential_state,
            ValueAvailabilityState.UNAVAILABLE,
        )
        self.assertIsNone(overlap.aggregate_potential)

    def test_registry_counts_are_unchanged(self) -> None:
        registries = load_doi_registries()
        self.assertEqual(registries.reason_count, EXPECTED_REASON_COUNT)
        self.assertEqual(registries.ownership_count, EXPECTED_OWNERSHIP_COUNT)
        self.assertEqual(registries.transition_count, EXPECTED_TRANSITION_COUNT)
        self.assertEqual((EXPECTED_REASON_COUNT, EXPECTED_OWNERSHIP_COUNT), (138, 138))
        self.assertEqual(EXPECTED_TRANSITION_COUNT, 115)

    def test_unknown_alias_is_closed(self) -> None:
        with self.assertRaises(KeyError):
            execute_doi_demo("doi-not-registered")


if __name__ == "__main__":
    unittest.main()
