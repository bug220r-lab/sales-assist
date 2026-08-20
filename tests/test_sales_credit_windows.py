from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime

from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.sales_credit.models import (
    SalesCreditReason,
    TimestampPrecision,
)
from synthetic_sales_assist.sales_credit.windows import (
    BUSINESS_TIME_ZONE_NAME,
    CalendarWindow,
    EvidenceTiming,
    OrderTiming,
    RecheckDecision,
    RecheckTrigger,
    WindowPosition,
    WindowValidationError,
    business_local_date,
    cancellation_replacement_window,
    classify_evidence_timing,
    classify_order_timing,
    decide_no_order_recheck,
    review_window,
    window_position,
)


def ts(value: str) -> CanonicalTimestamp:
    return CanonicalTimestamp(value)


class CalendarWindowTests(unittest.TestCase):
    def test_timezone_and_ordinary_inclusive_fourteen_day_window(self) -> None:
        interaction = ts("2026-08-20T04:30:00Z")
        window = review_window(interaction)

        self.assertEqual(BUSINESS_TIME_ZONE_NAME, "America/New_York")
        self.assertEqual(business_local_date(interaction), date(2026, 8, 20))
        self.assertEqual(window.start, date(2026, 8, 20))
        self.assertEqual(window.end, date(2026, 9, 3))
        self.assertTrue(window.contains_date(window.start))
        self.assertTrue(window.contains_date(window.end))
        self.assertFalse(window.contains_date(date(2026, 9, 4)))

    def test_month_year_and_leap_boundaries_are_calendar_arithmetic(self) -> None:
        vectors = (
            ("2026-08-25T12:00:00-04:00", date(2026, 8, 25), date(2026, 9, 8)),
            ("2026-12-25T12:00:00-05:00", date(2026, 12, 25), date(2027, 1, 8)),
            ("2028-02-20T12:00:00-05:00", date(2028, 2, 20), date(2028, 3, 5)),
        )
        for source, start, end in vectors:
            with self.subTest(start=start):
                window = review_window(ts(source))
                self.assertEqual((window.start, window.end), (start, end))

    def test_spring_and_fall_dst_do_not_change_calendar_day_count(self) -> None:
        spring = review_window(ts("2026-03-07T23:30:00-05:00"))
        fall = review_window(ts("2026-10-31T23:30:00-04:00"))
        self.assertEqual(spring, CalendarWindow(date(2026, 3, 7), date(2026, 3, 21)))
        self.assertEqual(fall, CalendarWindow(date(2026, 10, 31), date(2026, 11, 14)))

    def test_cancellation_has_its_own_window_that_may_extend_review(self) -> None:
        review = review_window(ts("2026-06-01T12:00:00-04:00"))
        replacement = cancellation_replacement_window(
            ts("2026-06-14T23:45:00-04:00")
        )
        self.assertEqual(review.end, date(2026, 6, 15))
        self.assertEqual(replacement.start, date(2026, 6, 14))
        self.assertEqual(replacement.end, date(2026, 6, 28))

    def test_window_positions_include_both_exact_boundaries(self) -> None:
        window = CalendarWindow.from_anchor_date(date(2026, 1, 10))
        self.assertIs(window.position_of_date(date(2026, 1, 9)), WindowPosition.BEFORE)
        self.assertIs(window.position_of_date(date(2026, 1, 10)), WindowPosition.ACTIVE)
        self.assertIs(window.position_of_date(date(2026, 1, 24)), WindowPosition.ACTIVE)
        self.assertIs(window.position_of_date(date(2026, 1, 25)), WindowPosition.AFTER)
        self.assertIs(
            window_position(window, ts("2026-01-25T04:59:59Z")),
            WindowPosition.ACTIVE,
        )
        self.assertIs(
            window_position(window, ts("2026-01-25T05:00:00Z")),
            WindowPosition.AFTER,
        )

    def test_invalid_window_shape_and_naive_timestamp_fail_closed(self) -> None:
        with self.assertRaisesRegex(WindowValidationError, "window_span"):
            CalendarWindow(date(2026, 1, 1), date(2026, 1, 14))
        with self.assertRaisesRegex(WindowValidationError, "timestamp_naive"):
            review_window(datetime(2026, 1, 1, 12, 0))

    def test_window_is_immutable(self) -> None:
        window = CalendarWindow.from_anchor_date(date(2026, 1, 1))
        with self.assertRaises(FrozenInstanceError):
            window.end = date(2026, 2, 1)  # type: ignore[misc]


class TimingClassificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.interaction = ts("2026-03-01T12:00:00-05:00")

    def test_exact_same_day_before_equal_and_after(self) -> None:
        before = ts("2026-03-01T11:59:59.999999999-05:00")
        equal = ts("2026-03-01T12:00:00-05:00")
        after = ts("2026-03-01T12:00:00.000000001-05:00")

        before_result = classify_order_timing(
                interaction_at=self.interaction,
                order_at=before,
                interaction_precision=TimestampPrecision.EXACT,
                order_precision=TimestampPrecision.EXACT,
        )
        self.assertIs(before_result, OrderTiming.BEFORE_INTERACTION)
        self.assertIs(before_result.reason, SalesCreditReason.ORDER_BEFORE_INTERACTION)
        for order in (equal, after):
            with self.subTest(order=str(order)):
                self.assertIs(
                    classify_order_timing(
                        interaction_at=self.interaction,
                        order_at=order,
                        interaction_precision=TimestampPrecision.EXACT,
                        order_precision=TimestampPrecision.EXACT,
                    ),
                    OrderTiming.QUALIFYING_ON_OR_AFTER_INTERACTION,
                )

    def test_same_day_unreliable_never_proves_order_qualification(self) -> None:
        result = classify_order_timing(
            interaction_at=self.interaction,
            order_at=ts("2026-03-01T23:00:00-05:00"),
            interaction_precision=TimestampPrecision.HISTORICAL_APPROXIMATION,
            order_precision=TimestampPrecision.EXACT,
        )
        self.assertIs(result, OrderTiming.SAME_DAY_UNCERTAIN)
        self.assertIs(result.reason, SalesCreditReason.ORDER_TIMING_UNCERTAIN)

    def test_later_date_does_not_require_same_day_precision(self) -> None:
        result = classify_order_timing(
            interaction_at=self.interaction,
            order_at=ts("2026-03-02T00:00:00-05:00"),
            interaction_precision=TimestampPrecision.HISTORICAL_APPROXIMATION,
            order_precision=TimestampPrecision.EXACT,
        )
        self.assertIs(result, OrderTiming.QUALIFYING_ON_OR_AFTER_INTERACTION)

    def test_exact_review_end_and_first_outside_instant(self) -> None:
        at_end = classify_order_timing(
            interaction_at=self.interaction,
            order_at=ts("2026-03-15T23:59:59.999999999-04:00"),
            interaction_precision=TimestampPrecision.EXACT,
            order_precision=TimestampPrecision.EXACT,
        )
        outside = classify_order_timing(
            interaction_at=self.interaction,
            order_at=ts("2026-03-16T00:00:00-04:00"),
            interaction_precision=TimestampPrecision.EXACT,
            order_precision=TimestampPrecision.EXACT,
        )
        self.assertIs(at_end, OrderTiming.QUALIFYING_ON_OR_AFTER_INTERACTION)
        self.assertIs(outside, OrderTiming.AFTER_REVIEW_WINDOW)

    def test_evidence_requires_strictly_pre_order_timing(self) -> None:
        order = ts("2026-04-10T15:00:00-04:00")
        self.assertIs(
            classify_evidence_timing(
                evidence_at=ts("2026-04-10T14:59:59.999999999-04:00"),
                order_at=order,
                evidence_precision=TimestampPrecision.EXACT,
                order_precision=TimestampPrecision.EXACT,
            ),
            EvidenceTiming.PRE_ORDER,
        )
        self.assertIs(
            classify_evidence_timing(
                evidence_at=order,
                order_at=order,
                evidence_precision=TimestampPrecision.EXACT,
                order_precision=TimestampPrecision.EXACT,
            ),
            EvidenceTiming.POST_ORDER,
        )
        self.assertIs(
            classify_evidence_timing(
                evidence_at=ts("2026-04-10T14:00:00-04:00"),
                order_at=order,
                evidence_precision=TimestampPrecision.HISTORICAL_APPROXIMATION,
                order_precision=TimestampPrecision.EXACT,
            ),
            EvidenceTiming.TIMING_UNCERTAIN,
        )
        self.assertIs(
            classify_evidence_timing(
                evidence_at=ts("2026-04-09T23:00:00-04:00"),
                order_at=order,
                evidence_precision=TimestampPrecision.HISTORICAL_APPROXIMATION,
                order_precision=TimestampPrecision.EXACT,
            ),
            EvidenceTiming.PRE_ORDER,
        )


class RecheckEligibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.window = CalendarWindow.from_anchor_date(date(2026, 8, 1))
        self.at = ts("2026-08-10T15:00:00-04:00")

    def test_automatic_check_is_eligible_once_per_new_york_date(self) -> None:
        eligible = decide_no_order_recheck(
            trigger=RecheckTrigger.AUTOMATIC_RECHECK,
            selected=False,
            at=self.at,
            window=self.window,
            last_automatic_check_date=date(2026, 8, 9),
        )
        throttled = decide_no_order_recheck(
            trigger=RecheckTrigger.AUTOMATIC_RECHECK,
            selected=False,
            at=self.at,
            window=self.window,
            last_automatic_check_date=date(2026, 8, 10),
        )
        self.assertTrue(eligible.allowed)
        self.assertIs(eligible.decision, RecheckDecision.ELIGIBLE)
        self.assertFalse(throttled.allowed)
        self.assertIs(
            throttled.decision,
            RecheckDecision.THROTTLED_ALREADY_CHECKED_LOCAL_DAY,
        )
        self.assertIs(
            throttled.reason,
            SalesCreditReason.AUTOMATIC_RECHECK_THROTTLED_LOCAL_DAY,
        )

    def test_local_day_not_utc_day_controls_throttle(self) -> None:
        result = decide_no_order_recheck(
            trigger=RecheckTrigger.AUTOMATIC_RECHECK,
            selected=False,
            at=ts("2026-08-11T03:30:00Z"),
            window=self.window,
            last_automatic_check_date=date(2026, 8, 10),
        )
        self.assertEqual(result.business_date, date(2026, 8, 10))
        self.assertFalse(result.allowed)

    def test_selected_force_bypasses_only_daily_throttle_and_is_audited(self) -> None:
        forced = decide_no_order_recheck(
            trigger=RecheckTrigger.FORCE_RECHECK,
            selected=True,
            at=self.at,
            window=self.window,
            last_automatic_check_date=date(2026, 8, 10),
            force_explanation="SELECTED_CASE_REVIEW",
        )
        self.assertTrue(forced.allowed)
        self.assertIs(forced.decision, RecheckDecision.FORCE_RECHECK_SELECTED)
        self.assertTrue(forced.audit_required)
        self.assertTrue(forced.bypassed_daily_throttle)
        self.assertIs(forced.reason, SalesCreditReason.FORCE_RECHECK_ACCEPTED)
        self.assertEqual(forced.explanation_code, "SELECTED_CASE_REVIEW")

    def test_force_requires_selection_and_does_not_bypass_window(self) -> None:
        not_selected = decide_no_order_recheck(
            trigger=RecheckTrigger.FORCE_RECHECK,
            selected=False,
            at=self.at,
            window=self.window,
            last_automatic_check_date=None,
        )
        outside = decide_no_order_recheck(
            trigger=RecheckTrigger.FORCE_RECHECK,
            selected=True,
            at=ts("2026-08-16T00:00:00-04:00"),
            window=self.window,
            last_automatic_check_date=None,
            force_explanation="SELECTED_CASE_REVIEW",
        )
        self.assertIs(
            not_selected.decision,
            RecheckDecision.FORCE_RECHECK_NOT_SELECTED,
        )
        self.assertFalse(not_selected.audit_required)
        self.assertIs(outside.decision, RecheckDecision.WINDOW_NOT_ACTIVE)
        self.assertTrue(outside.audit_required)

    def test_future_throttle_state_and_wrong_shapes_fail_closed(self) -> None:
        with self.assertRaisesRegex(WindowValidationError, "future"):
            decide_no_order_recheck(
                trigger=RecheckTrigger.AUTOMATIC_RECHECK,
                selected=False,
                at=self.at,
                window=self.window,
                last_automatic_check_date=date(2026, 8, 11),
            )
        with self.assertRaisesRegex(WindowValidationError, "precision"):
            classify_order_timing(
                interaction_at=self.at,
                order_at=self.at,
                interaction_precision=1,  # type: ignore[arg-type]
                order_precision=TimestampPrecision.EXACT,
            )

    def test_recheck_result_cannot_forge_an_unaudited_force_decision(self) -> None:
        forced = decide_no_order_recheck(
            trigger=RecheckTrigger.FORCE_RECHECK,
            selected=True,
            at=self.at,
            window=self.window,
            last_automatic_check_date=date(2026, 8, 10),
            force_explanation="SELECTED_CASE_REVIEW",
        )
        for changes in (
            {"audit_required": False},
            {"reason": None},
            {"explanation_code": None},
            {"allowed": False},
            {
                "decision": RecheckDecision.ELIGIBLE,
                "audit_required": False,
                "reason": None,
                "explanation_code": None,
            },
        ):
            with self.subTest(changes=tuple(changes)):
                with self.assertRaisesRegex(WindowValidationError, "coherence"):
                    replace(forced, **changes)


if __name__ == "__main__":
    unittest.main()
