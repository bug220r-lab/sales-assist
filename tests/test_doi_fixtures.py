from __future__ import annotations

import dataclasses
import importlib
import unittest

from synthetic_sales_assist.doi.fixtures import (
    DOI_SCENARIO_CATALOG_VERSION,
    DOIFixtureError,
    SAFETY_COUNTER_NAMES,
    ScenarioEffect,
    ScenarioExecutionKind,
    ScenarioFamily,
    ZERO_SAFETY_COUNTERS,
    named_scenarios,
    scenario_catalog,
    transition_scenarios,
)
from synthetic_sales_assist.domain.identities import EvidenceId
from synthetic_sales_assist.domain.registries import load_doi_registries
from tests.doi_scenario_oracles import (
    SUPPORTED_EVALUATION_SCENARIOS,
    execute_evaluation_scenario,
    observe_evaluation,
)


REQUIRED_NAMED_SCENARIOS = frozenset(
    {
        "VALID_REVIEW_RUN",
        "DUPLICATE_ROWS_MERGED",
        "INVALID_ORDER_NUMBER",
        "OUT_OF_SCOPE_ASSIGNEE",
        "ASSIGNEE_CONFLICT",
        "SOURCE_CHANGED",
        "SOURCE_INACCESSIBLE",
        "FAILED_ATTEMPT_WAIT_AND_EXACT_RETRY",
        "RETRY_CONFLICT",
        "EXPLICIT_NO_RETRY_FINALIZATION",
        "RETRY_WINS_RACE",
        "FINALIZATION_WINS_RACE",
        "RECHECK_RUN_TYPES",
        "RC084_PRE_EXTRACTION_FAILURE",
        "SYSTEMIC_ONE_WORK_ZERO_DISPOSITIONS",
        "NORMAL_COMPLETION_COUNTS",
        "ALL_BLOCKED_COMPLETION_WITH_EXCEPTIONS",
        "EMPTY_COHERENT_BATCH_COMPLETION",
        "SOURCE_CELL_PRIVACY_FIREWALL",
        "COMPLETE_ORDINARY_ORDER",
        "LARGE_AND_ZERO_RELEVANT_ORDERS",
        "WRONG_ORDER_IDENTITY",
        "MISSING_REQUIRED_SECTION",
        "WHOLE_ORDER_COUNT_DUPLICATE_CHANGE_OR_TIME_FAILURE",
        "UNNORMALIZABLE_REQUIRED_TIMESTAMP",
        "UNKNOWN_FIELD_VERSUS_MISSING_FIELD",
        "STABLE_AND_COMPOSITE_CONTINUITY",
        "FULL_DIRECT_SHIP",
        "MIXED_DIRECT_SHIP",
        "ORDINARY_FULFILLMENT_SPLIT",
        "FULFILLMENT_SPLIT_WITH_UNRELATED_UNKNOWN",
        "FULFILLMENT_SPLIT_WITH_UNRELATED_UNKNOWN_DS",
        "ONLY_CANDIDATE_BLOCKED_BY_UNKNOWN",
        "UNKNOWN_CONTINUITY_PRESERVES_INDEPENDENT_SPLIT",
        "MULTI_UNKNOWN_EXACT_SET_UNION",
        "PARTIAL_QUANTITY_REVIEW",
        "PAYMENT_ONLY_EXCLUSION",
        "PAYMENT_WITH_SPLIT_OPPORTUNITY",
        "ALL_IN_STOCK_PROGRESS_REVIEW",
        "HUMAN_NO_ACTION_MONITOR",
        "SHIPPED_HARD_CLOSURE",
        "CANCELED_HARD_CLOSURE",
        "REP_TRANSFER_REVERSIBLE_CLOSURE",
        "HUMAN_OUT_OF_SCOPE_REVERSIBLE_CLOSURE",
        "SOURCE_ABSENCE_RECHECK",
        "DOMESTIC_SPECIAL_REVIEW_SPLIT",
        "INTERNATIONAL_SPLIT",
        "UNKNOWN_GEOGRAPHY_SPLIT",
        "INTERNATIONAL_SPLIT_WITH_UNKNOWN_ETA",
        "OVERLAP_UNAVAILABLE_THEN_HUMAN_SELECTED",
        "HUMAN_SCENARIO_SELECTION_RESOLVES_AGGREGATE",
        "DISJOINT_MUTUALLY_EXCLUSIVE_OPTIONS",
        "ALTERNATE_HIERARCHY_AND_COMPATIBILITY",
        "EXACT_SKU_RECHECK",
        "EXACT_MFG_ALTERNATE",
        "MFG_CROSS_REFERENCE",
        "MFG_SUPERSESSION",
        "FUNCTIONAL_ALTERNATE",
        "NO_EXACT_MFG_OR_VERIFIED_ALTERNATE",
        "MANUAL_ALTERNATE_IDENTIFICATION",
        "ALTERNATE_REVISION_SUPERSEDED_INVALIDATED",
        "STALE_ALTERNATE_OBSERVATION",
        "WWC_ALL_PRESENT_PARTITIONS",
        "WWC_MALFORMED_NESTED_FINDING",
        "CONTACT_ALL_GOVERNED_STATES",
        "DEDUPE_CANDIDATE_INCOMPLETE_AND_REJECTED",
        "DEDUPE_APPROVAL_AWAITING_AND_LATER_CONFIRMATION",
        "ATTENTION_COEXISTENCE_AND_EXACT_CLEAR",
        "UNVERIFIED_SYSTEM_AND_HUMAN_ACTION",
        "ACTION_REPLAY_AND_OCCURRENCE_CONFLICT",
        "VALUE_CORRECTION_PARTIAL_AND_FULL_REVERSAL",
        "HUMAN_VALUE_ESTIMATE_REJECTED",
        "RESULT_LINK_AUTO_HUMAN_AMBIGUOUS_NOT_FOUND",
        "RESULT_LINK_SEARCH_NOT_FOUND_AND_AMBIGUOUS",
        "KPI_EXACT_ONCE_AND_SCOPED_REP",
        "KPI_MIXED_CURRENCY_SEGMENTATION",
        "PURGE_FINALIZATION_AND_ROLLBACK",
    }
)


def _selector_is_collected(selector: str) -> bool:
    module_name, class_name, method_name = selector.rsplit(".", 2)
    module = importlib.import_module(module_name)
    case_type = getattr(module, class_name)
    return method_name in unittest.defaultTestLoader.getTestCaseNames(case_type)


def _execute_selector(selector: str) -> unittest.TestResult:
    module_name, class_name, method_name = selector.rsplit(".", 2)
    module = importlib.import_module(module_name)
    case_type = getattr(module, class_name)
    result = unittest.TestResult()
    unittest.TestSuite((case_type(method_name),)).run(result)
    return result


class DOISyntheticFixtureCatalogTests(unittest.TestCase):
    def test_named_catalog_covers_every_required_business_scenario_family(self) -> None:
        rows = named_scenarios()
        keys = {row.scenario_key for row in rows}
        self.assertTrue(REQUIRED_NAMED_SCENARIOS <= keys)
        self.assertEqual(
            {row.family for row in rows},
            set(ScenarioFamily) - {ScenarioFamily.LIFECYCLE_TRANSITION},
        )
        self.assertGreaterEqual(len(rows), len(REQUIRED_NAMED_SCENARIOS))

    def test_every_registered_transition_has_collected_legal_and_invalid_scenarios(self) -> None:
        registry = load_doi_registries()
        rows = transition_scenarios()
        self.assertEqual(len(rows), len(registry.transition_refs) * 2)
        by_transition: dict[str, set[str]] = {}
        for row in rows:
            self.assertEqual(row.family, ScenarioFamily.LIFECYCLE_TRANSITION)
            self.assertEqual(len(row.transitions), 1)
            transition_id = row.transitions[0].transition_id
            branch = row.scenario_key.removeprefix(
                transition_id.replace("-", "_") + "_"
            )
            by_transition.setdefault(transition_id, set()).add(branch)
        self.assertEqual(
            set(by_transition),
            {item.transition_id for item in registry.transition_refs},
        )
        self.assertTrue(
            all(branches == {"LEGAL", "INVALID_GUARD"} for branches in by_transition.values())
        )

    def test_catalog_is_closed_deterministic_and_all_selectors_are_collected(self) -> None:
        first = scenario_catalog()
        second = scenario_catalog()
        self.assertEqual(first, second)
        self.assertEqual(len({row.scenario_id for row in first}), len(first))
        self.assertEqual(len({row.scenario_key for row in first}), len(first))
        selectors = {selector for row in first for selector in row.test_selectors}
        missing = sorted(selector for selector in selectors if not _selector_is_collected(selector))
        self.assertEqual(missing, [])

    def test_every_catalog_selector_executes_its_real_owner_oracle(self) -> None:
        selectors = sorted(
            {selector for row in scenario_catalog() for selector in row.test_selectors}
        )
        for selector in selectors:
            with self.subTest(selector=selector):
                result = _execute_selector(selector)
                details = tuple(
                    traceback.splitlines()[-1]
                    for _, traceback in (*result.failures, *result.errors)
                )
                self.assertTrue(
                    result.wasSuccessful(),
                    f"owner oracle failed: {selector}: {details}",
                )

    def test_every_evaluation_catalog_row_matches_real_normalized_output(self) -> None:
        rows = {
            row.scenario_key: row
            for row in named_scenarios()
            if row.execution_kind is ScenarioExecutionKind.EVALUATION_RESULT
        }
        self.assertEqual(set(rows), set(SUPPORTED_EVALUATION_SCENARIOS))
        for scenario_key, row in rows.items():
            with self.subTest(scenario=scenario_key):
                first = execute_evaluation_scenario(scenario_key)
                second = execute_evaluation_scenario(scenario_key)
                self.assertEqual(first.input_binding, second.input_binding)
                self.assertEqual(first.output_binding, second.output_binding)
                actual = observe_evaluation(first)
                self.assertEqual(actual.state, row.expected_top_level_state)
                self.assertEqual(
                    actual.reasons,
                    tuple(item.code for item in row.expected_reasons),
                )
                self.assertEqual(actual.opportunities, row.expected_opportunities)
                self.assertEqual(actual.scope, row.scope_expectation)
                self.assertEqual(actual.reviews, row.human_review)
                self.assertEqual(actual.attention, row.attention)
                self.assertEqual(actual.closure, row.closure)
                self.assertEqual(
                    actual.transitions,
                    tuple(item.transition_id for item in row.transitions),
                )
                self.assertEqual(actual.effects, row.event_effects)
                self.assertEqual(actual.value, row.expected_value_state)
                self.assertEqual(
                    row.synthetic_inputs,
                    (
                        EvidenceId(
                            "SYN-EVIDENCE-DOI-INPUT-"
                            + scenario_key.replace("_", "-")
                        ),
                    ),
                )

    def test_every_catalog_row_has_a_closed_executable_proof_partition(self) -> None:
        for row in scenario_catalog():
            with self.subTest(scenario=row.scenario_key):
                if row.family is ScenarioFamily.LIFECYCLE_TRANSITION:
                    expected = (
                        ScenarioExecutionKind.TRANSITION_LEGAL
                        if row.scenario_key.endswith("_LEGAL")
                        else ScenarioExecutionKind.TRANSITION_INVALID_GUARD
                    )
                elif row.expected_top_level_state is not None:
                    expected = ScenarioExecutionKind.EVALUATION_RESULT
                else:
                    expected = ScenarioExecutionKind.OWNER_BOUNDARY_ORACLE
                self.assertIs(row.execution_kind, expected)
                self.assertEqual(
                    row.scenario_id,
                    EvidenceId(
                        "SYN-EVIDENCE-DOI-SCENARIO-"
                        + row.scenario_key.replace("_", "-")
                    ),
                )
                self.assertEqual(
                    row.synthetic_inputs,
                    (
                        EvidenceId(
                            "SYN-EVIDENCE-DOI-INPUT-"
                            + row.scenario_key.replace("_", "-")
                        ),
                    ),
                )

    def test_every_scenario_declares_zero_safety_and_milestone3_effect_boundaries(self) -> None:
        self.assertEqual(len(SAFETY_COUNTER_NAMES), 9)
        self.assertEqual(len(ZERO_SAFETY_COUNTERS), 9)
        for row in scenario_catalog():
            with self.subTest(scenario=row.scenario_key):
                self.assertEqual(row.version, DOI_SCENARIO_CATALOG_VERSION)
                self.assertEqual(row.safety_counters, ZERO_SAFETY_COUNTERS)
                self.assertIn(ScenarioEffect.NO_EXTERNAL_MUTATION, row.event_effects)
                self.assertIn(
                    ScenarioEffect.NO_DURABLE_BUSINESS_PERSISTENCE,
                    row.event_effects,
                )
                self.assertTrue(row.synthetic_inputs)
                self.assertTrue(row.test_selectors)

    def test_malformed_or_nonzero_safety_fixture_is_rejected(self) -> None:
        row = named_scenarios()[0]
        bad_counters = tuple(
            (name, 1 if index == 0 else 0)
            for index, name in enumerate(SAFETY_COUNTER_NAMES)
        )
        with self.assertRaises(DOIFixtureError) as caught:
            dataclasses.replace(row, safety_counters=bad_counters)
        self.assertEqual(caught.exception.code, "SCENARIO_SAFETY_COUNTERS_INVALID")


if __name__ == "__main__":
    unittest.main()
