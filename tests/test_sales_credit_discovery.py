from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from synthetic_sales_assist.domain.identities import OrderId
from synthetic_sales_assist.sales_credit.models import SalesCreditReason
from synthetic_sales_assist.sales_credit.discovery import (
    DiscoveryOutcome,
    DiscoveryValidationError,
    IdentifierSearchResult,
    SearchCompleteness,
    SearchIdentifier,
    SearchIdentifierKind,
    combine_search_results,
    normalize_fictional_phone,
    normalize_synthetic_email,
    plan_discovery,
)


class ContactNormalizationTests(unittest.TestCase):
    def test_email_uses_ascii_four_trim_and_ascii_lowercase(self) -> None:
        vectors = {
            "\t Synthetic.User@EXAMPLE.TEST\r\n": "synthetic.user@example.test",
            "a+b@example.test": "a+b@example.test",
            "CASE@example.test": "case@example.test",
        }
        for source, expected in vectors.items():
            with self.subTest(expected=expected):
                self.assertEqual(normalize_synthetic_email(source), expected)

    def test_email_does_not_guess_or_apply_unicode_normalization(self) -> None:
        external = "person@" + "outside.invalid"
        subdomain = "person@" + "sub" + "." + "example.test"
        invalid: tuple[object, ...] = (
            external,
            subdomain,
            "two..dots@example.test",
            "user name@example.test",
            "person\N{NO-BREAK SPACE}@example.test",
            "",
            None,
            True,
        )
        for value in invalid:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(DiscoveryValidationError) as raised:
                    normalize_synthetic_email(value)
                if str(value):
                    self.assertNotIn(str(value), str(raised.exception))

    def test_phone_accepts_only_firewall_formats_and_never_guesses_area_code(self) -> None:
        vectors = {
            "555-0100": "5550100",
            "212-555-0101": "2125550101",
            "(212) 555-0199": "2125550199",
            "+1 212 555 0150": "2125550150",
            "\t212-555-0107\r\n": "2125550107",
        }
        for source, expected in vectors.items():
            with self.subTest(expected=expected):
                self.assertEqual(normalize_fictional_phone(source), expected)

    def test_malformed_or_nonfictional_phone_rejects_without_correction(self) -> None:
        invalid: tuple[object, ...] = (
            "555-0099",
            "555-0200",
            "112-555-0100",
            "2125550100",
            "+1-212-555-0100",
            "212-555-0100 ext 1",
            2125550100,
            None,
            True,
        )
        for value in invalid:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(DiscoveryValidationError) as raised:
                    normalize_fictional_phone(value)
                self.assertNotIn(str(value), str(raised.exception))


class DiscoveryPlanningTests(unittest.TestCase):
    def test_every_distinct_valid_email_and_phone_is_planned_deterministically(self) -> None:
        plan = plan_discovery(
            email_values=(
                "B@example.test",
                " a@example.test ",
                "b@EXAMPLE.TEST",
            ),
            phone_values=(
                "212-555-0102",
                "+1 212 555 0101",
                "(212) 555-0102",
            ),
        )
        self.assertEqual(
            tuple((item.kind.value, item.value) for item in plan.identifiers),
            (
                ("EMAIL", "a@example.test"),
                ("EMAIL", "b@example.test"),
                ("PHONE", "2125550101"),
                ("PHONE", "2125550102"),
            ),
        )
        self.assertFalse(plan.requires_manual_review)

    def test_invalid_values_reject_before_any_search_plan_is_created(self) -> None:
        private_marker = "private" + "-invalid@example.test " + "suffix"
        with self.assertRaises(DiscoveryValidationError) as raised:
            plan_discovery(
                email_values=(private_marker,),
                phone_values=("212-555-0100",),
            )
        self.assertNotIn(private_marker, repr(raised.exception))

    def test_no_valid_identifier_requires_manual_review(self) -> None:
        plan = plan_discovery(
            email_values=(),
            phone_values=(),
        )
        self.assertTrue(plan.requires_manual_review)
        result = combine_search_results(
            plan=plan,
            results=(),
            review_window_closed=False,
        )
        self.assertIs(result.outcome, DiscoveryOutcome.MANUAL_REVIEW_REQUIRED)
        self.assertFalse(result.enumeration_complete)
        self.assertEqual(
            result.reasons,
            (SalesCreditReason.NO_USABLE_SEARCH_IDENTIFIER,),
        )

    def test_canonical_identifier_rejects_unnormalized_direct_construction(self) -> None:
        with self.assertRaisesRegex(DiscoveryValidationError, "not_canonical"):
            SearchIdentifier(SearchIdentifierKind.EMAIL, "A@example.test")

    def test_plan_and_identifiers_are_immutable(self) -> None:
        plan = plan_discovery(email_values=("a@example.test",))
        with self.assertRaises(FrozenInstanceError):
            plan.identifiers = ()  # type: ignore[misc]


class DiscoveryCombinationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = plan_discovery(
            email_values=("synthetic.user@example.test",),
            phone_values=("212-555-0100",),
        )
        self.email = self.plan.identifiers[0]
        self.phone = self.plan.identifiers[1]

    def result(
        self,
        identifier: SearchIdentifier,
        *order_values: str,
        completeness: SearchCompleteness = SearchCompleteness.COMPLETE,
    ) -> IdentifierSearchResult:
        return IdentifierSearchResult(
            identifier=identifier,
            completeness=completeness,
            order_ids=tuple(OrderId(value) for value in order_values),
        )

    def test_both_identifiers_are_mandatory_and_union_deduplicates_order_ids(self) -> None:
        combined = combine_search_results(
            plan=self.plan,
            results=(
                self.result(self.phone, "SYN-ORDER-000003", "SYN-ORDER-000001"),
                self.result(self.email, "SYN-ORDER-000002", "SYN-ORDER-000001"),
            ),
            review_window_closed=False,
        )
        self.assertIs(combined.outcome, DiscoveryOutcome.CANDIDATES_FOUND)
        self.assertTrue(combined.enumeration_complete)
        self.assertEqual(combined.identifiers_required, 2)
        self.assertEqual(combined.identifiers_completed, 2)
        self.assertEqual(
            tuple(order.value for order in combined.order_ids),
            (
                "SYN-ORDER-000001",
                "SYN-ORDER-000002",
                "SYN-ORDER-000003",
            ),
        )

    def test_missing_or_incomplete_identifier_can_never_conclude_no_order(self) -> None:
        missing = combine_search_results(
            plan=self.plan,
            results=(self.result(self.email),),
            review_window_closed=True,
        )
        incomplete = combine_search_results(
            plan=self.plan,
            results=(
                self.result(self.email),
                self.result(
                    self.phone,
                    completeness=SearchCompleteness.INCOMPLETE,
                ),
            ),
            review_window_closed=True,
        )
        for result in (missing, incomplete):
            with self.subTest(completed=result.identifiers_completed):
                self.assertIs(result.outcome, DiscoveryOutcome.SEARCH_INCOMPLETE)
                self.assertFalse(result.enumeration_complete)
                self.assertEqual(
                    result.reasons,
                    (SalesCreditReason.IDENTIFIER_SEARCH_INCOMPLETE,),
                )

    def test_observed_candidates_survive_incomplete_enumeration_for_evaluation(self) -> None:
        combined = combine_search_results(
            plan=self.plan,
            results=(
                self.result(
                    self.email,
                    "SYN-ORDER-000009",
                    completeness=SearchCompleteness.INCOMPLETE,
                ),
                self.result(self.phone),
            ),
            review_window_closed=False,
        )
        self.assertIs(combined.outcome, DiscoveryOutcome.CANDIDATES_FOUND)
        self.assertFalse(combined.enumeration_complete)
        self.assertEqual(
            tuple(order.value for order in combined.order_ids),
            ("SYN-ORDER-000009",),
        )

    def test_complete_empty_union_uses_exact_active_and_closed_states(self) -> None:
        results = (self.result(self.email), self.result(self.phone))
        active = combine_search_results(
            plan=self.plan,
            results=results,
            review_window_closed=False,
        )
        closed = combine_search_results(
            plan=self.plan,
            results=results,
            review_window_closed=True,
        )
        self.assertIs(
            active.outcome,
            DiscoveryOutcome.CHECKED_NO_ORDER_WINDOW_ACTIVE,
        )
        self.assertIs(
            closed.outcome,
            DiscoveryOutcome.REVIEW_WINDOW_CLOSED_NO_ORDER,
        )
        self.assertTrue(active.enumeration_complete)
        self.assertTrue(closed.enumeration_complete)
        self.assertEqual(active.reasons, (SalesCreditReason.NO_ORDER_WINDOW_ACTIVE,))
        self.assertEqual(closed.reasons, (SalesCreditReason.NO_ORDER_WINDOW_CLOSED,))

    def test_result_order_does_not_change_deterministic_union(self) -> None:
        email = self.result(self.email, "SYN-ORDER-000002")
        phone = self.result(self.phone, "SYN-ORDER-000001")
        first = combine_search_results(
            plan=self.plan,
            results=(email, phone),
            review_window_closed=False,
        )
        second = combine_search_results(
            plan=self.plan,
            results=(phone, email),
            review_window_closed=False,
        )
        self.assertEqual(first, second)

    def test_duplicate_and_unplanned_results_fail_closed(self) -> None:
        duplicate = self.result(self.email)
        with self.assertRaisesRegex(DiscoveryValidationError, "duplicate"):
            combine_search_results(
                plan=self.plan,
                results=(duplicate, duplicate),
                review_window_closed=False,
            )
        other = SearchIdentifier(SearchIdentifierKind.EMAIL, "other@example.test")
        with self.assertRaisesRegex(DiscoveryValidationError, "unexpected"):
            combine_search_results(
                plan=self.plan,
                results=(self.result(other),),
                review_window_closed=False,
            )

    def test_closed_shapes_reject_aliases(self) -> None:
        with self.assertRaisesRegex(DiscoveryValidationError, "results_shape"):
            combine_search_results(
                plan=self.plan,
                results=[],  # type: ignore[arg-type]
                review_window_closed=False,
            )
        with self.assertRaisesRegex(DiscoveryValidationError, "closed_type"):
            combine_search_results(
                plan=self.plan,
                results=(),
                review_window_closed=0,  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
