"""Identity-free exact aggregate metrics for pure Sales Credit observations."""

from __future__ import annotations

from dataclasses import dataclass

from synthetic_sales_assist.domain.identities import OrderId
from synthetic_sales_assist.domain.numeric import NonNegativeCount
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.sales_credit.models import HumanOutcomeType, WorkflowState


_HUMAN_REVIEW_STATES = {
    WorkflowState.OUTBOUND_EVIDENCE_HUMAN_REVIEW,
    WorkflowState.INBOUND_EVIDENCE_HUMAN_REVIEW,
    WorkflowState.TIMING_UNCERTAIN_HUMAN_REVIEW,
    WorkflowState.OTHER_REP_HUMAN_REVIEW,
    WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
    WorkflowState.POSSIBLE_REPLACEMENT_HUMAN_REVIEW,
    WorkflowState.MANUAL_REVIEW_REQUIRED,
}
_AUTOMATIC_FAVORABLE_STATES = {
    WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
    WorkflowState.VERIFIED_PREORDER_EVIDENCE,
}
_COMPARABLE_OUTCOMES = {
    HumanOutcomeType.APPROVED,
    HumanOutcomeType.DENIED,
    HumanOutcomeType.OTHER_REP,
}


class MetricsValidationError(ValueError):
    """Reject invalid aggregate input without exposing a case identity."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Sales Credit metric input rejected: {code}")


@dataclass(frozen=True, slots=True)
class ExactRate:
    numerator: NonNegativeCount
    denominator: NonNegativeCount

    def __post_init__(self) -> None:
        if type(self.numerator) is not NonNegativeCount:
            raise MetricsValidationError("rate_numerator")
        if type(self.denominator) is not NonNegativeCount:
            raise MetricsValidationError("rate_denominator")
        if self.numerator.value > self.denominator.value:
            raise MetricsValidationError("rate_partition")

    @property
    def is_defined(self) -> bool:
        return self.denominator.value > 0

    def to_dict(self) -> dict[str, object]:
        return {
            "defined": self.is_defined,
            "denominator": self.denominator.value,
            "numerator": self.numerator.value,
        }


@dataclass(frozen=True, slots=True, repr=False, kw_only=True)
class CaseMetricObservation:
    order_id: OrderId
    system_workflow: WorkflowState
    human_outcome: HumanOutcomeType | None
    opened_at: CanonicalTimestamp
    reviewed_at: CanonicalTimestamp | None
    processing_latency_nanoseconds: NonNegativeCount
    failed_closed: bool

    def __post_init__(self) -> None:
        if type(self.order_id) is not OrderId:
            raise MetricsValidationError("metric_order_id")
        if type(self.system_workflow) is not WorkflowState:
            raise MetricsValidationError("metric_workflow")
        if self.human_outcome is not None and type(self.human_outcome) is not HumanOutcomeType:
            raise MetricsValidationError("metric_human_outcome")
        if type(self.opened_at) is not CanonicalTimestamp:
            raise MetricsValidationError("metric_opened_at")
        if self.reviewed_at is not None and type(self.reviewed_at) is not CanonicalTimestamp:
            raise MetricsValidationError("metric_reviewed_at")
        if type(self.processing_latency_nanoseconds) is not NonNegativeCount:
            raise MetricsValidationError("metric_latency")
        if type(self.failed_closed) is not bool:
            raise MetricsValidationError("metric_failed_closed")
        if (self.human_outcome is None) != (self.reviewed_at is None):
            raise MetricsValidationError("metric_review_pair")
        if self.reviewed_at is not None and _elapsed_ns(self.opened_at, self.reviewed_at) < 0:
            raise MetricsValidationError("metric_review_time_order")

    def __repr__(self) -> str:
        return "CaseMetricObservation(<redacted>)"


@dataclass(frozen=True, slots=True)
class SalesCreditMetrics:
    case_count: NonNegativeCount
    reviewed_case_count: NonNegativeCount
    median_time_to_review_nanoseconds: NonNegativeCount | None
    human_review_rate: ExactRate
    system_human_agreement_rate: ExactRate
    false_automatic_confirmation_count: NonNegativeCount
    median_processing_latency_nanoseconds: NonNegativeCount | None
    p95_processing_latency_nanoseconds: NonNegativeCount | None
    fail_closed_rate: ExactRate

    def __post_init__(self) -> None:
        for value, expected, code in (
            (self.case_count, NonNegativeCount, "metrics_case_count"),
            (self.reviewed_case_count, NonNegativeCount, "metrics_reviewed_count"),
            (self.human_review_rate, ExactRate, "metrics_human_rate"),
            (
                self.system_human_agreement_rate,
                ExactRate,
                "metrics_agreement_rate",
            ),
            (
                self.false_automatic_confirmation_count,
                NonNegativeCount,
                "metrics_false_automatic_count",
            ),
            (self.fail_closed_rate, ExactRate, "metrics_fail_closed_rate"),
        ):
            if type(value) is not expected:
                raise MetricsValidationError(code)
        for value, code in (
            (self.median_time_to_review_nanoseconds, "metrics_review_median"),
            (self.median_processing_latency_nanoseconds, "metrics_latency_median"),
            (self.p95_processing_latency_nanoseconds, "metrics_latency_p95"),
        ):
            if value is not None and type(value) is not NonNegativeCount:
                raise MetricsValidationError(code)
        case_count = self.case_count.value
        reviewed = self.reviewed_case_count.value
        if reviewed > case_count:
            raise MetricsValidationError("metrics_reviewed_partition")
        if self.human_review_rate.denominator.value != case_count:
            raise MetricsValidationError("metrics_human_denominator")
        if self.fail_closed_rate.denominator.value != case_count:
            raise MetricsValidationError("metrics_fail_closed_denominator")
        agreement_denominator = self.system_human_agreement_rate.denominator.value
        if agreement_denominator > reviewed:
            raise MetricsValidationError("metrics_agreement_denominator")
        if self.false_automatic_confirmation_count.value > agreement_denominator:
            raise MetricsValidationError("metrics_false_automatic_partition")
        if (self.median_time_to_review_nanoseconds is None) != (reviewed == 0):
            raise MetricsValidationError("metrics_review_median_partition")
        latency_values = (
            self.median_processing_latency_nanoseconds,
            self.p95_processing_latency_nanoseconds,
        )
        if any(value is None for value in latency_values) != (case_count == 0):
            raise MetricsValidationError("metrics_latency_partition")
        if (
            self.median_processing_latency_nanoseconds is not None
            and self.p95_processing_latency_nanoseconds is not None
            and self.p95_processing_latency_nanoseconds.value
            < self.median_processing_latency_nanoseconds.value
        ):
            raise MetricsValidationError("metrics_latency_order")

    def to_dict(self) -> dict[str, object]:
        return {
            "case_count": self.case_count.value,
            "fail_closed_rate": self.fail_closed_rate.to_dict(),
            "false_automatic_confirmation_count": (
                self.false_automatic_confirmation_count.value
            ),
            "human_review_rate": self.human_review_rate.to_dict(),
            "median_processing_latency_nanoseconds": (
                None
                if self.median_processing_latency_nanoseconds is None
                else self.median_processing_latency_nanoseconds.value
            ),
            "median_time_to_review_nanoseconds": (
                None
                if self.median_time_to_review_nanoseconds is None
                else self.median_time_to_review_nanoseconds.value
            ),
            "p95_processing_latency_nanoseconds": (
                None
                if self.p95_processing_latency_nanoseconds is None
                else self.p95_processing_latency_nanoseconds.value
            ),
            "reviewed_case_count": self.reviewed_case_count.value,
            "system_human_agreement_rate": self.system_human_agreement_rate.to_dict(),
        }


def _elapsed_ns(start: CanonicalTimestamp, end: CanonicalTimestamp) -> int:
    return (end.epoch_seconds - start.epoch_seconds) * 1_000_000_000 + (
        end.nanosecond - start.nanosecond
    )


def _median(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    length = len(ordered)
    midpoint = length // 2
    if length % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) // 2


def _nearest_rank_p95(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (95 * len(ordered) + 99) // 100
    return ordered[rank - 1]


def aggregate_metrics(
    observations: tuple[CaseMetricObservation, ...],
) -> SalesCreditMetrics:
    """Deduplicate exact observations and return only aggregate, identity-free facts."""

    if type(observations) is not tuple or any(
        type(item) is not CaseMetricObservation for item in observations
    ):
        raise MetricsValidationError("metric_observations")
    by_order: dict[str, CaseMetricObservation] = {}
    for observation in observations:
        existing = by_order.get(observation.order_id.value)
        if existing is not None and existing != observation:
            raise MetricsValidationError("metric_observation_conflict")
        by_order[observation.order_id.value] = observation
    unique = tuple(by_order[key] for key in sorted(by_order))
    review_durations = [
        _elapsed_ns(item.opened_at, item.reviewed_at)
        for item in unique
        if item.reviewed_at is not None
    ]
    latencies = [item.processing_latency_nanoseconds.value for item in unique]
    human_routed = sum(item.system_workflow in _HUMAN_REVIEW_STATES for item in unique)
    comparable = [item for item in unique if item.human_outcome in _COMPARABLE_OUTCOMES]
    agreement = 0
    false_automatic = 0
    for item in comparable:
        automatic = item.system_workflow in _AUTOMATIC_FAVORABLE_STATES
        human_approved = item.human_outcome is HumanOutcomeType.APPROVED
        agreement += automatic == human_approved
        false_automatic += automatic and item.human_outcome in {
            HumanOutcomeType.DENIED,
            HumanOutcomeType.OTHER_REP,
        }
    failed_closed = sum(item.failed_closed for item in unique)
    median_review = _median(review_durations)
    median_latency = _median(latencies)
    p95_latency = _nearest_rank_p95(latencies)
    return SalesCreditMetrics(
        case_count=NonNegativeCount(len(unique)),
        reviewed_case_count=NonNegativeCount(len(review_durations)),
        median_time_to_review_nanoseconds=(
            None if median_review is None else NonNegativeCount(median_review)
        ),
        human_review_rate=ExactRate(
            NonNegativeCount(human_routed),
            NonNegativeCount(len(unique)),
        ),
        system_human_agreement_rate=ExactRate(
            NonNegativeCount(agreement),
            NonNegativeCount(len(comparable)),
        ),
        false_automatic_confirmation_count=NonNegativeCount(false_automatic),
        median_processing_latency_nanoseconds=(
            None if median_latency is None else NonNegativeCount(median_latency)
        ),
        p95_processing_latency_nanoseconds=(
            None if p95_latency is None else NonNegativeCount(p95_latency)
        ),
        fail_closed_rate=ExactRate(
            NonNegativeCount(failed_closed),
            NonNegativeCount(len(unique)),
        ),
    )


__all__ = [
    "CaseMetricObservation",
    "ExactRate",
    "MetricsValidationError",
    "SalesCreditMetrics",
    "aggregate_metrics",
]
