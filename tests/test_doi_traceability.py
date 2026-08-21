from __future__ import annotations

import json
import unittest
from collections.abc import Iterator
from pathlib import Path

from synthetic_sales_assist.doi.evaluator import (
    DOIEvaluationError,
    assert_reason_route_legal,
)
from synthetic_sales_assist.doi.lifecycle import (
    LifecycleConflictError,
    TransitionFixture,
    make_transition_command,
    reduce_transition,
)
from synthetic_sales_assist.doi.traceability import (
    ReasonOracleRow,
    reason_oracle_rows,
    traceability_test_selectors,
    transition_coverage_rows,
)
from synthetic_sales_assist.domain.registries import (
    EXPECTED_OWNERSHIP_COUNT,
    EXPECTED_REASON_COUNT,
    EXPECTED_TRANSITION_COUNT,
    load_doi_registries,
)


ROOT = Path(__file__).resolve().parents[1]


def _flatten(suite: unittest.TestSuite) -> Iterator[unittest.TestCase]:
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten(item)
        else:
            yield item


def collected_doi_test_ids() -> tuple[str, ...]:
    suite = unittest.defaultTestLoader.discover(
        str(ROOT / "tests"),
        pattern="test_doi_*.py",
        top_level_dir=str(ROOT),
    )
    return tuple(sorted(test.id() for test in _flatten(suite)))


def _row(reason_code: str) -> ReasonOracleRow:
    matches = [row for row in reason_oracle_rows() if row.reason.code == reason_code]
    if len(matches) != 1:
        raise AssertionError(reason_code)
    return matches[0]


class DOITraceabilityReconciliationTests(unittest.TestCase):
    def test_exact_reason_ownership_and_transition_counts_are_unchanged(self) -> None:
        rows = reason_oracle_rows()
        transitions = transition_coverage_rows()
        self.assertEqual(len(rows), EXPECTED_REASON_COUNT)
        self.assertEqual(len(rows), EXPECTED_OWNERSHIP_COUNT)
        self.assertEqual(len(transitions), EXPECTED_TRANSITION_COUNT)
        self.assertEqual(len({row.reason.code for row in rows}), len(rows))
        self.assertEqual(
            len({row.transition.transition_id for row in transitions}),
            len(transitions),
        )

    def test_approved_overlay_routes_are_exact(self) -> None:
        expected = {
            "RC-016": {"TR-027", "TR-028", "TR-033", "TR-034", "TR-035", "TR-037"},
            "RC-017": {"TR-027", "TR-028", "TR-033", "TR-034", "TR-035", "TR-037"},
            "RC-018": {"TR-027", "TR-028", "TR-033", "TR-034", "TR-035", "TR-037"},
            "RC-115": {"TR-027", "TR-028", "TR-033", "TR-034", "TR-035", "TR-037"},
            "RC-087": {"TR-033", "TR-034", "TR-035"},
        }
        for reason_code, transition_ids in expected.items():
            with self.subTest(reason=reason_code):
                self.assertEqual(
                    {
                        transition.transition_id
                        for transition in _row(reason_code).effective_transitions
                    },
                    transition_ids,
                )

    def test_all_field_specific_unknown_routes_are_exact(self) -> None:
        shared_positive_routes = {
            "TR-027",
            "TR-028",
            "TR-033",
            "TR-034",
            "TR-035",
            "TR-037",
        }
        expected = {
            "RC-018": shared_positive_routes,
            "RC-115": shared_positive_routes,
            "RC-116": shared_positive_routes,
            **{
                f"RC-{number:03d}": shared_positive_routes
                for number in range(117, 139)
            },
        }
        for reason_code, transition_ids in expected.items():
            with self.subTest(reason=reason_code):
                self.assertEqual(
                    {
                        transition.transition_id
                        for transition in _row(reason_code).effective_transitions
                    },
                    transition_ids,
                )

    def test_every_reason_has_zero_legal_route_leakage(self) -> None:
        registries = load_doi_registries()
        for row in reason_oracle_rows():
            legal = set(row.effective_transitions)
            illegal_routes = tuple(
                transition
                for transition in registries.transition_refs
                if transition not in legal
            )
            for illegal in illegal_routes:
                with self.subTest(
                    reason=row.reason.code,
                    transition=illegal.transition_id,
                ):
                    with self.assertRaises(DOIEvaluationError):
                        assert_reason_route_legal(
                            row.reason,
                            illegal,
                            registries=registries,
                        )
            representative = illegal_routes[0]
            with self.subTest(
                reason=row.reason.code,
                command_transition=representative.transition_id,
            ):
                with self.assertRaises(DOIEvaluationError):
                    assert_reason_route_legal(
                        row.reason,
                        representative,
                        registries=registries,
                    )
                fixture = TransitionFixture.legal(representative)
                with self.assertRaises(LifecycleConflictError):
                    make_transition_command(
                        transition=representative,
                        stream_id=fixture.command.stream_id,
                        occurrence_id=fixture.command.occurrence_id,
                        current_state=fixture.command.current_state,
                        expected_sequence=1,
                        expected_predecessor_sha256=None,
                        guard_proof=fixture.command.guard_proof,
                        reasons=(row.reason,),
                    )

    def test_supplied_planning_oracles_reconcile_to_real_behavior_selectors(self) -> None:
        document = json.loads(
            (ROOT / "specs" / "doi" / "reason_ownership.json").read_text(
                encoding="utf-8"
            )
        )
        supplied = document["rows"]
        actual = {row.reason.code: row.actual_test_selector for row in reason_oracle_rows()}
        self.assertEqual(len(supplied), EXPECTED_OWNERSHIP_COUNT)
        self.assertEqual(set(actual), {row["reason_code"] for row in supplied})
        self.assertTrue(
            all(row["owning_deterministic_oracles"] for row in supplied)
        )
        self.assertNotIn(
            "tests.test_doi_traceability.DOIReasonOwnershipOracleTests",
            "\n".join(actual.values()),
        )
        self.assertLessEqual(len(set(actual.values())), EXPECTED_OWNERSHIP_COUNT)

    def test_all_required_selectors_are_exactly_real_collected_tests(self) -> None:
        required = traceability_test_selectors()
        collected = collected_doi_test_ids()
        expected = len(
            {
                row.actual_test_selector for row in reason_oracle_rows()
            }
            | {
                selector
                for row in transition_coverage_rows()
                for selector in (row.legal_test_selector, row.invalid_test_selector)
            }
        )
        self.assertEqual(len(required), expected)
        self.assertEqual(len(required), len(set(required)))
        self.assertTrue(set(required).issubset(collected))
        for selector in required:
            with self.subTest(selector=selector):
                suite = unittest.defaultTestLoader.loadTestsFromName(selector)
                loaded_ids = tuple(test.id() for test in _flatten(suite))
                self.assertEqual(loaded_ids, (selector,))


if __name__ == "__main__":
    unittest.main()
