from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError, replace

from synthetic_sales_assist.domain.identities import OrderId
from synthetic_sales_assist.domain.numeric import NonNegativeCount
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.sales_credit.metrics import (
    CaseMetricObservation,
    ExactRate,
    MetricsValidationError,
    SalesCreditMetrics,
    aggregate_metrics,
)
from synthetic_sales_assist.sales_credit.models import HumanOutcomeType, WorkflowState


def ts(value: str) -> CanonicalTimestamp:
    return CanonicalTimestamp(value)


def observation(
    suffix: str,
    *,
    workflow: WorkflowState,
    human_outcome: HumanOutcomeType | None,
    review_nanoseconds: int | None,
    latency_nanoseconds: int,
    failed_closed: bool = False,
) -> CaseMetricObservation:
    opened = ts("2026-08-01T00:00:00Z")
    reviewed = (
        None
        if review_nanoseconds is None
        else ts(f"2026-08-01T00:00:00.{review_nanoseconds:09d}Z")
    )
    return CaseMetricObservation(
        order_id=OrderId(f"SYN-ORDER-METRIC-{suffix}"),
        system_workflow=workflow,
        human_outcome=human_outcome,
        opened_at=opened,
        reviewed_at=reviewed,
        processing_latency_nanoseconds=NonNegativeCount(latency_nanoseconds),
        failed_closed=failed_closed,
    )


class ExactRateTests(unittest.TestCase):
    def test_zero_denominator_is_explicitly_undefined(self) -> None:
        rate = ExactRate(NonNegativeCount(0), NonNegativeCount(0))
        self.assertFalse(rate.is_defined)
        self.assertEqual(
            rate.to_dict(),
            {"defined": False, "denominator": 0, "numerator": 0},
        )

    def test_rate_rejects_nonpartition_and_wrong_types(self) -> None:
        with self.assertRaisesRegex(MetricsValidationError, "rate_partition"):
            ExactRate(NonNegativeCount(2), NonNegativeCount(1))
        with self.assertRaisesRegex(MetricsValidationError, "rate_numerator"):
            ExactRate(1, NonNegativeCount(1))  # type: ignore[arg-type]
        rate = ExactRate(NonNegativeCount(1), NonNegativeCount(2))
        with self.assertRaises(FrozenInstanceError):
            rate.numerator = NonNegativeCount(0)  # type: ignore[misc]


class ObservationTests(unittest.TestCase):
    def test_observation_is_redacted_immutable_and_strict(self) -> None:
        value = observation(
            "001",
            workflow=WorkflowState.MANUAL_REVIEW_REQUIRED,
            human_outcome=None,
            review_nanoseconds=None,
            latency_nanoseconds=10,
        )
        self.assertEqual(repr(value), "CaseMetricObservation(<redacted>)")
        self.assertNotIn(value.order_id.value, repr(value))
        with self.assertRaises(FrozenInstanceError):
            value.failed_closed = True  # type: ignore[misc]
        with self.assertRaisesRegex(MetricsValidationError, "metric_review_pair"):
            replace(value, human_outcome=HumanOutcomeType.APPROVED)
        with self.assertRaisesRegex(MetricsValidationError, "metric_failed_closed"):
            replace(value, failed_closed=1)  # type: ignore[arg-type]

    def test_review_timestamp_may_not_precede_opened_timestamp(self) -> None:
        with self.assertRaisesRegex(MetricsValidationError, "metric_review_time_order"):
            CaseMetricObservation(
                order_id=OrderId("SYN-ORDER-METRIC-EARLY"),
                system_workflow=WorkflowState.MANUAL_REVIEW_REQUIRED,
                human_outcome=HumanOutcomeType.DENIED,
                opened_at=ts("2026-08-02T00:00:00Z"),
                reviewed_at=ts("2026-08-01T23:59:59.999999999Z"),
                processing_latency_nanoseconds=NonNegativeCount(1),
                failed_closed=False,
            )


class AggregateMetricsTests(unittest.TestCase):
    def test_empty_input_has_zero_counts_explicit_rates_and_no_invented_latency(self) -> None:
        result = aggregate_metrics(())
        self.assertEqual(result.case_count.value, 0)
        self.assertEqual(result.reviewed_case_count.value, 0)
        self.assertIsNone(result.median_time_to_review_nanoseconds)
        self.assertIsNone(result.median_processing_latency_nanoseconds)
        self.assertIsNone(result.p95_processing_latency_nanoseconds)
        for rate in (
            result.human_review_rate,
            result.system_human_agreement_rate,
            result.fail_closed_rate,
        ):
            self.assertEqual(rate.denominator.value, 0)
            self.assertFalse(rate.is_defined)

    def test_aggregate_definitions_median_nearest_rank_and_agreement_are_exact(self) -> None:
        observations = (
            observation(
                "001",
                workflow=WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
                human_outcome=HumanOutcomeType.APPROVED,
                review_nanoseconds=10,
                latency_nanoseconds=10,
            ),
            observation(
                "002",
                workflow=WorkflowState.VERIFIED_PREORDER_EVIDENCE,
                human_outcome=HumanOutcomeType.DENIED,
                review_nanoseconds=30,
                latency_nanoseconds=20,
            ),
            observation(
                "003",
                workflow=WorkflowState.OTHER_REP_HUMAN_REVIEW,
                human_outcome=HumanOutcomeType.OTHER_REP,
                review_nanoseconds=20,
                latency_nanoseconds=30,
            ),
            observation(
                "004",
                workflow=WorkflowState.MANUAL_REVIEW_REQUIRED,
                human_outcome=None,
                review_nanoseconds=None,
                latency_nanoseconds=100,
                failed_closed=True,
            ),
        )
        result = aggregate_metrics(observations)
        self.assertEqual(result.case_count.value, 4)
        self.assertEqual(result.reviewed_case_count.value, 3)
        self.assertEqual(
            result.median_time_to_review_nanoseconds.value,  # type: ignore[union-attr]
            20,
        )
        self.assertEqual(
            result.median_processing_latency_nanoseconds.value,  # type: ignore[union-attr]
            25,
        )
        self.assertEqual(
            result.p95_processing_latency_nanoseconds.value,  # type: ignore[union-attr]
            100,
        )
        self.assertEqual(
            result.human_review_rate.to_dict(),
            {"defined": True, "denominator": 4, "numerator": 2},
        )
        self.assertEqual(
            result.system_human_agreement_rate.to_dict(),
            {"defined": True, "denominator": 3, "numerator": 2},
        )
        self.assertEqual(result.false_automatic_confirmation_count.value, 1)
        self.assertEqual(
            result.fail_closed_rate.to_dict(),
            {"defined": True, "denominator": 4, "numerator": 1},
        )

    def test_exact_duplicate_is_idempotent_and_conflicting_duplicate_fails(self) -> None:
        value = observation(
            "001",
            workflow=WorkflowState.MANUAL_REVIEW_REQUIRED,
            human_outcome=None,
            review_nanoseconds=None,
            latency_nanoseconds=10,
        )
        self.assertEqual(aggregate_metrics((value, value)).case_count.value, 1)
        with self.assertRaisesRegex(MetricsValidationError, "metric_observation_conflict"):
            aggregate_metrics(
                (
                    value,
                    replace(value, processing_latency_nanoseconds=NonNegativeCount(11)),
                )
            )

    def test_noncomparable_human_outcomes_do_not_inflate_agreement_denominator(self) -> None:
        values = (
            observation(
                "001",
                workflow=WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
                human_outcome=HumanOutcomeType.PARTIAL,
                review_nanoseconds=1,
                latency_nanoseconds=1,
            ),
            observation(
                "002",
                workflow=WorkflowState.MANUAL_REVIEW_REQUIRED,
                human_outcome=HumanOutcomeType.NOT_PURSUED,
                review_nanoseconds=2,
                latency_nanoseconds=2,
            ),
        )
        result = aggregate_metrics(values)
        self.assertEqual(result.reviewed_case_count.value, 2)
        self.assertEqual(result.system_human_agreement_rate.denominator.value, 0)
        self.assertFalse(result.system_human_agreement_rate.is_defined)

    def test_input_shape_is_closed_and_output_contains_no_identity_or_contact_detail(self) -> None:
        value = observation(
            "PRIVATE-001",
            workflow=WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
            human_outcome=HumanOutcomeType.APPROVED,
            review_nanoseconds=5,
            latency_nanoseconds=7,
        )
        with self.assertRaisesRegex(MetricsValidationError, "metric_observations"):
            aggregate_metrics([value])  # type: ignore[arg-type]
        result = aggregate_metrics((value,))
        serialized = json.dumps(result.to_dict(), sort_keys=True)
        self.assertNotIn(value.order_id.value, serialized)
        self.assertNotIn("example.test", serialized)
        self.assertNotIn("555", serialized)
        self.assertNotIn("note", serialized.casefold())
        self.assertEqual(set(result.to_dict()), {
            "case_count",
            "fail_closed_rate",
            "false_automatic_confirmation_count",
            "human_review_rate",
            "median_processing_latency_nanoseconds",
            "median_time_to_review_nanoseconds",
            "p95_processing_latency_nanoseconds",
            "reviewed_case_count",
            "system_human_agreement_rate",
        })

    def test_aggregate_result_constructor_enforces_cross_field_invariants(self) -> None:
        valid = aggregate_metrics(())
        with self.assertRaises(MetricsValidationError):
            SalesCreditMetrics(
                case_count=NonNegativeCount(0),
                reviewed_case_count=NonNegativeCount(1),
                median_time_to_review_nanoseconds=NonNegativeCount(1),
                human_review_rate=valid.human_review_rate,
                system_human_agreement_rate=valid.system_human_agreement_rate,
                false_automatic_confirmation_count=NonNegativeCount(0),
                median_processing_latency_nanoseconds=None,
                p95_processing_latency_nanoseconds=None,
                fail_closed_rate=valid.fail_closed_rate,
            )

    def test_metric_result_is_immutable(self) -> None:
        result = aggregate_metrics(())
        with self.assertRaises(FrozenInstanceError):
            result.case_count = NonNegativeCount(1)  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
