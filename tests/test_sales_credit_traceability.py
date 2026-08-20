from __future__ import annotations

import hashlib
import importlib
import inspect
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

from synthetic_sales_assist.sales_credit.models import (
    EvidenceClassification,
    HumanOutcomeType,
    MaterialChangeKind,
    SalesCreditEffect,
    SalesCreditReason,
    WorkflowState,
)
from synthetic_sales_assist.sales_credit.traceability import (
    ACCEPTANCE_COVERAGE,
    REASON_SCENARIOS,
    SAFETY_COUNTER_NAMES,
    SCENARIO_CATALOG,
    TRACEABILITY_VERSION,
    ZERO_SAFETY_COUNTERS,
    AcceptanceFamily,
    ScenarioCatalogRow,
    TraceabilityValidationError,
    collected_test_selectors,
    reason_owner,
    render_traceability_markdown,
)


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "milestone2-traceability.md"
EXPECTED_DOC_SHA256 = "166ff0a6edb75c0a2c0140bcfa5e7b59b0369fa6be3a60382a80bb22ed8f67e1"


def collected_cases(suite: unittest.TestSuite) -> tuple[unittest.TestCase, ...]:
    cases: list[unittest.TestCase] = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            cases.extend(collected_cases(item))
        else:
            cases.append(item)
    return tuple(cases)


def selector_source(selector: str) -> str:
    module_name, owner_name, method_name = selector.rsplit(".", 2)
    module = importlib.import_module(module_name)
    owner = getattr(module, owner_name)
    return inspect.getsource(getattr(owner, method_name))


class CatalogInventoryTests(unittest.TestCase):
    def test_all_45_reasons_have_one_ordered_executable_owner(self) -> None:
        self.assertEqual(TRACEABILITY_VERSION, "synthetic-sales-credit-traceability/v1")
        self.assertEqual(len(REASON_SCENARIOS), 45)
        self.assertEqual(
            tuple(row.expected_reasons[0] for row in REASON_SCENARIOS),
            tuple(SalesCreditReason),
        )
        for reason in SalesCreditReason:
            with self.subTest(reason=reason.value):
                row = reason_owner(reason)
                self.assertEqual(row.expected_reasons, (reason,))
                self.assertTrue(row.test_selectors)

    def test_exact_workflow_evidence_material_and_human_inventories_are_covered(self) -> None:
        self.assertEqual(
            {row.expected_workflow for row in SCENARIO_CATALOG},
            set(WorkflowState),
        )
        self.assertEqual(
            {
                row.evidence_branch
                for row in SCENARIO_CATALOG
                if row.evidence_branch is not None
            },
            set(EvidenceClassification),
        )
        self.assertEqual(
            {
                row.material_branch
                for row in SCENARIO_CATALOG
                if row.material_branch is not None
            },
            set(MaterialChangeKind),
        )
        self.assertEqual(
            {
                row.human_outcome
                for row in SCENARIO_CATALOG
                if row.human_outcome is not None
            },
            set(HumanOutcomeType),
        )

    def test_every_row_has_unique_synthetic_id_version_effects_and_nine_zeroes(self) -> None:
        scenario_ids = tuple(row.scenario_id.value for row in SCENARIO_CATALOG)
        self.assertEqual(len(SCENARIO_CATALOG), 66)
        self.assertEqual(len(scenario_ids), len(set(scenario_ids)))
        self.assertEqual(len(SAFETY_COUNTER_NAMES), 9)
        for row in SCENARIO_CATALOG:
            with self.subTest(scenario=row.scenario_id.value):
                self.assertTrue(row.scenario_id.value.startswith("SYN-EVIDENCE-M2-SCENARIO-"))
                self.assertEqual(row.version, TRACEABILITY_VERSION)
                self.assertEqual(row.safety_counters, ZERO_SAFETY_COUNTERS)
                self.assertEqual(dict(row.safety_counters), dict.fromkeys(SAFETY_COUNTER_NAMES, 0))
                self.assertIn(
                    SalesCreditEffect.NO_PERSISTENCE_MILESTONE_2,
                    row.persistence_effects,
                )
                self.assertEqual(
                    row.persistence_effects,
                    tuple(sorted(set(row.persistence_effects), key=lambda item: item.value)),
                )

    def test_catalog_rows_are_frozen_slotted_and_fail_closed(self) -> None:
        row = SCENARIO_CATALOG[0]
        self.assertFalse(hasattr(row, "__dict__"))
        with self.assertRaises(FrozenInstanceError):
            row.version = "changed"  # type: ignore[misc]
        invalid = (
            {"version": "synthetic-sales-credit-traceability/v2"},
            {"expected_branch": "open branch"},
            {"expected_reasons": [row.expected_reasons[0]]},
            {"human_review_required": not row.human_review_required},
            {"persistence_effects": ()},
            {"safety_counters": row.safety_counters[:-1]},
            {"test_selectors": ("not-a-selector",)},
        )
        for overrides in invalid:
            with self.subTest(fields=tuple(overrides)):
                with self.assertRaises(TraceabilityValidationError):
                    replace(row, **overrides)
        with self.assertRaisesRegex(TraceabilityValidationError, "reason_owner_type"):
            reason_owner("TARGET_REP")  # type: ignore[arg-type]

    def test_acceptance_families_are_closed_and_each_row_has_real_ownership(self) -> None:
        self.assertEqual({row.family for row in ACCEPTANCE_COVERAGE}, set(AcceptanceFamily))
        acceptance_ids = tuple(row.acceptance_id for row in ACCEPTANCE_COVERAGE)
        self.assertEqual(len(acceptance_ids), len(set(acceptance_ids)))
        for row in ACCEPTANCE_COVERAGE:
            with self.subTest(acceptance=row.acceptance_id):
                self.assertTrue(row.requirement)
                self.assertTrue(row.test_selectors)


class ExecutableOwnershipTests(unittest.TestCase):
    def test_every_collected_selector_resolves_to_exactly_one_real_test(self) -> None:
        selectors = collected_test_selectors()
        self.assertEqual(selectors, tuple(sorted(set(selectors))))
        self.assertEqual(len(selectors), 55)
        for selector in selectors:
            with self.subTest(selector=selector):
                suite = unittest.defaultTestLoader.loadTestsFromName(selector)
                cases = collected_cases(suite)
                self.assertEqual(len(cases), 1)
                self.assertEqual(cases[0].id(), selector)
                self.assertNotEqual(type(cases[0]).__name__, "_FailedTest")

    def test_reason_owner_source_contains_the_named_reason_and_an_assertion(self) -> None:
        for row in REASON_SCENARIOS:
            reason = row.expected_reasons[0]
            token = f"SalesCreditReason.{reason.value}"
            sources = tuple(selector_source(selector) for selector in row.test_selectors)
            with self.subTest(reason=reason.value):
                self.assertTrue(any(token in source for source in sources))
                self.assertTrue(
                    any(token in source and "self.assert" in source for source in sources)
                )


class DeterministicDocumentTests(unittest.TestCase):
    def test_checked_in_document_is_the_exact_generated_utf8_bytes(self) -> None:
        generated = render_traceability_markdown().encode("utf-8")
        self.assertEqual(DOC.read_bytes(), generated)
        self.assertEqual(hashlib.sha256(generated).hexdigest(), EXPECTED_DOC_SHA256)

    def test_render_is_stable_complete_and_contains_no_contact_material(self) -> None:
        first = render_traceability_markdown()
        second = render_traceability_markdown()
        self.assertEqual(first, second)
        self.assertTrue(first.endswith("\n"))
        for row in SCENARIO_CATALOG:
            self.assertIn(row.scenario_id.value, first)
        for reason in SalesCreditReason:
            self.assertIn(reason.value, first)
        for workflow in WorkflowState:
            self.assertIn(workflow.value, first)
        self.assertNotIn("@example.test", first)
        self.assertNotIn("555-01", first)


if __name__ == "__main__":
    unittest.main()
