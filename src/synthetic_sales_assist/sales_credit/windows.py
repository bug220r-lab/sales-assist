"""Pure New York calendar windows and Sales Credit timing decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo

from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.domain.tokens import ImmutableStrEnum
from synthetic_sales_assist.sales_credit.models import (
    SalesCreditReason,
    SearchTriggerType,
    TimestampPrecision,
)
from synthetic_sales_assist.safety.content import scan_payload


BUSINESS_TIME_ZONE_NAME = "America/New_York"
BUSINESS_TIME_ZONE = ZoneInfo(BUSINESS_TIME_ZONE_NAME)
WINDOW_DAYS_AFTER_ANCHOR = 14
_UTC_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class WindowValidationError(ValueError):
    """Reject invalid timing material without echoing the supplied value."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Sales Credit window input rejected: {code}")


class WindowPosition(ImmutableStrEnum):
    """Position of a New York business date relative to a closed calendar window."""

    BEFORE = "BEFORE"
    ACTIVE = "ACTIVE"
    AFTER = "AFTER"


class OrderTiming(ImmutableStrEnum):
    """Closed qualification timing for one candidate order."""

    BEFORE_INTERACTION = "BEFORE_INTERACTION"
    QUALIFYING_ON_OR_AFTER_INTERACTION = "QUALIFYING_ON_OR_AFTER_INTERACTION"
    SAME_DAY_UNCERTAIN = "SAME_DAY_UNCERTAIN"
    AFTER_REVIEW_WINDOW = "AFTER_REVIEW_WINDOW"

    @property
    def reason(self) -> SalesCreditReason | None:
        if self is OrderTiming.BEFORE_INTERACTION:
            return SalesCreditReason.ORDER_BEFORE_INTERACTION
        if self is OrderTiming.AFTER_REVIEW_WINDOW:
            return SalesCreditReason.ORDER_AFTER_REVIEW_WINDOW
        if self is OrderTiming.SAME_DAY_UNCERTAIN:
            return SalesCreditReason.ORDER_TIMING_UNCERTAIN
        return None


class EvidenceTiming(ImmutableStrEnum):
    """Closed evidence-to-order timing relationship."""

    PRE_ORDER = "PRE_ORDER"
    POST_ORDER = "POST_ORDER"
    TIMING_UNCERTAIN = "TIMING_UNCERTAIN"


class RecheckDecision(ImmutableStrEnum):
    """Closed recheck decision returned without performing work."""

    ELIGIBLE = "ELIGIBLE"
    THROTTLED_ALREADY_CHECKED_LOCAL_DAY = "THROTTLED_ALREADY_CHECKED_LOCAL_DAY"
    WINDOW_NOT_ACTIVE = "WINDOW_NOT_ACTIVE"
    FORCE_RECHECK_SELECTED = "FORCE_RECHECK_SELECTED"
    FORCE_RECHECK_NOT_SELECTED = "FORCE_RECHECK_NOT_SELECTED"


type Instant = CanonicalTimestamp | datetime
RecheckTrigger = SearchTriggerType
_EXPLANATION = re.compile(r"\A[A-Z][A-Z0-9_]{2,63}\Z", re.ASCII)


def _require_date(value: object, *, code: str) -> date:
    if type(value) is not date:
        raise WindowValidationError(code)
    return value


def _instant_parts(value: object) -> tuple[int, int]:
    if type(value) is CanonicalTimestamp:
        return value.epoch_seconds, value.nanosecond
    if type(value) is not datetime:
        raise WindowValidationError("timestamp_type")
    offset = value.utcoffset()
    if offset is None:
        raise WindowValidationError("timestamp_naive")
    utc = value.astimezone(timezone.utc)
    delta = utc - _UTC_EPOCH
    return delta.days * 86_400 + delta.seconds, utc.microsecond * 1_000


def business_local_date(value: Instant) -> date:
    """Return the America/New_York calendar date of one aware instant."""

    epoch_seconds, _ = _instant_parts(value)
    utc = _UTC_EPOCH + timedelta(seconds=epoch_seconds)
    return utc.astimezone(BUSINESS_TIME_ZONE).date()


@dataclass(frozen=True, slots=True)
class CalendarWindow:
    """An inclusive anchor date through fourteen full calendar days after it."""

    start: date
    end: date

    def __post_init__(self) -> None:
        start = _require_date(self.start, code="window_start_type")
        end = _require_date(self.end, code="window_end_type")
        if end != start + timedelta(days=WINDOW_DAYS_AFTER_ANCHOR):
            raise WindowValidationError("window_span")

    @classmethod
    def from_anchor_date(cls, anchor: date) -> CalendarWindow:
        start = _require_date(anchor, code="anchor_date_type")
        return cls(start=start, end=start + timedelta(days=WINDOW_DAYS_AFTER_ANCHOR))

    def position_of_date(self, candidate: date) -> WindowPosition:
        observed = _require_date(candidate, code="candidate_date_type")
        if observed < self.start:
            return WindowPosition.BEFORE
        if observed > self.end:
            return WindowPosition.AFTER
        return WindowPosition.ACTIVE

    def contains_date(self, candidate: date) -> bool:
        return self.position_of_date(candidate) is WindowPosition.ACTIVE


def review_window(interaction_at: Instant) -> CalendarWindow:
    """Build the inclusive review window from the interaction's New York date."""

    return CalendarWindow.from_anchor_date(business_local_date(interaction_at))


def cancellation_replacement_window(canceled_at: Instant) -> CalendarWindow:
    """Build the independent inclusive replacement window from cancellation date."""

    return CalendarWindow.from_anchor_date(business_local_date(canceled_at))


def window_position(window: CalendarWindow, at: Instant) -> WindowPosition:
    if type(window) is not CalendarWindow:
        raise WindowValidationError("window_type")
    return window.position_of_date(business_local_date(at))


def classify_order_timing(
    *,
    interaction_at: Instant,
    order_at: Instant,
    interaction_precision: TimestampPrecision,
    order_precision: TimestampPrecision,
) -> OrderTiming:
    """Classify one order without treating date-only same-day facts as proof."""

    if type(interaction_precision) is not TimestampPrecision:
        raise WindowValidationError("interaction_precision_type")
    if type(order_precision) is not TimestampPrecision:
        raise WindowValidationError("order_precision_type")
    same_day_ordering_reliable = (
        interaction_precision.proves_same_day_ordering
        and order_precision.proves_same_day_ordering
    )
    interaction_parts = _instant_parts(interaction_at)
    order_parts = _instant_parts(order_at)
    window = review_window(interaction_at)
    order_date = business_local_date(order_at)

    if order_date < window.start:
        return OrderTiming.BEFORE_INTERACTION
    if order_date > window.end:
        return OrderTiming.AFTER_REVIEW_WINDOW
    if order_date == window.start:
        if not same_day_ordering_reliable:
            return OrderTiming.SAME_DAY_UNCERTAIN
        if order_parts < interaction_parts:
            return OrderTiming.BEFORE_INTERACTION
    return OrderTiming.QUALIFYING_ON_OR_AFTER_INTERACTION


def classify_evidence_timing(
    *,
    evidence_at: Instant,
    order_at: Instant,
    evidence_precision: TimestampPrecision,
    order_precision: TimestampPrecision,
) -> EvidenceTiming:
    """Classify evidence as pre-order only when its ordering is actually proved."""

    if type(evidence_precision) is not TimestampPrecision:
        raise WindowValidationError("evidence_precision_type")
    if type(order_precision) is not TimestampPrecision:
        raise WindowValidationError("order_precision_type")
    same_day_ordering_reliable = (
        evidence_precision.proves_same_day_ordering
        and order_precision.proves_same_day_ordering
    )
    evidence_date = business_local_date(evidence_at)
    order_date = business_local_date(order_at)
    if evidence_date == order_date and not same_day_ordering_reliable:
        return EvidenceTiming.TIMING_UNCERTAIN
    if _instant_parts(evidence_at) < _instant_parts(order_at):
        return EvidenceTiming.PRE_ORDER
    return EvidenceTiming.POST_ORDER


@dataclass(frozen=True, slots=True)
class RecheckResult:
    """An auditable pure eligibility result; it never starts a search."""

    allowed: bool
    decision: RecheckDecision
    business_date: date
    audit_required: bool
    bypassed_daily_throttle: bool
    reason: SalesCreditReason | None
    explanation_code: str | None

    def __post_init__(self) -> None:
        if type(self.allowed) is not bool:
            raise WindowValidationError("recheck_allowed_type")
        if type(self.decision) is not RecheckDecision:
            raise WindowValidationError("recheck_decision_type")
        _require_date(self.business_date, code="recheck_business_date_type")
        if type(self.audit_required) is not bool:
            raise WindowValidationError("recheck_audit_type")
        if type(self.bypassed_daily_throttle) is not bool:
            raise WindowValidationError("recheck_bypass_type")
        if self.reason is not None and type(self.reason) is not SalesCreditReason:
            raise WindowValidationError("recheck_reason_type")
        if self.explanation_code is not None and (
            type(self.explanation_code) is not str
            or _EXPLANATION.fullmatch(self.explanation_code) is None
            or scan_payload({"explanation": self.explanation_code})
        ):
            raise WindowValidationError("recheck_explanation")
        automatic_window_closed = (
            False,
            RecheckDecision.WINDOW_NOT_ACTIVE,
            False,
            False,
            None,
            None,
        )
        forced_window_closed = (
            False,
            RecheckDecision.WINDOW_NOT_ACTIVE,
            True,
            False,
            SalesCreditReason.FORCE_RECHECK_ACCEPTED,
            self.explanation_code,
        )
        legal = {
            automatic_window_closed,
            (
                True,
                RecheckDecision.ELIGIBLE,
                False,
                False,
                None,
                None,
            ),
            (
                False,
                RecheckDecision.THROTTLED_ALREADY_CHECKED_LOCAL_DAY,
                False,
                False,
                SalesCreditReason.AUTOMATIC_RECHECK_THROTTLED_LOCAL_DAY,
                None,
            ),
            (
                False,
                RecheckDecision.FORCE_RECHECK_NOT_SELECTED,
                False,
                False,
                None,
                None,
            ),
        }
        if self.explanation_code is not None:
            legal.add(forced_window_closed)
            legal.add(
                (
                    True,
                    RecheckDecision.FORCE_RECHECK_SELECTED,
                    True,
                    False,
                    SalesCreditReason.FORCE_RECHECK_ACCEPTED,
                    self.explanation_code,
                )
            )
            legal.add(
                (
                    True,
                    RecheckDecision.FORCE_RECHECK_SELECTED,
                    True,
                    True,
                    SalesCreditReason.FORCE_RECHECK_ACCEPTED,
                    self.explanation_code,
                )
            )
        actual = (
            self.allowed,
            self.decision,
            self.audit_required,
            self.bypassed_daily_throttle,
            self.reason,
            self.explanation_code,
        )
        if actual not in legal:
            raise WindowValidationError("recheck_result_coherence")


def decide_no_order_recheck(
    *,
    trigger: SearchTriggerType,
    selected: bool,
    at: Instant,
    window: CalendarWindow,
    last_automatic_check_date: date | None,
    force_explanation: str | None = None,
) -> RecheckResult:
    """Apply the local-day throttle; selected force bypasses only that throttle."""

    if type(trigger) is not SearchTriggerType:
        raise WindowValidationError("recheck_trigger_type")
    if type(selected) is not bool:
        raise WindowValidationError("recheck_selected_type")
    if type(window) is not CalendarWindow:
        raise WindowValidationError("window_type")
    if last_automatic_check_date is not None:
        _require_date(last_automatic_check_date, code="last_automatic_check_date_type")

    business_date = business_local_date(at)
    if last_automatic_check_date is not None and last_automatic_check_date > business_date:
        raise WindowValidationError("last_automatic_check_in_future")
    position = window.position_of_date(business_date)
    if trigger is SearchTriggerType.AUTOMATIC_RECHECK:
        if force_explanation is not None:
            raise WindowValidationError("automatic_recheck_force_explanation")
        if selected:
            raise WindowValidationError("automatic_recheck_cannot_be_selected_force")
        if position is not WindowPosition.ACTIVE:
            return RecheckResult(
                allowed=False,
                decision=RecheckDecision.WINDOW_NOT_ACTIVE,
                business_date=business_date,
                audit_required=False,
                bypassed_daily_throttle=False,
                reason=None,
                explanation_code=None,
            )
        if last_automatic_check_date == business_date:
            return RecheckResult(
                allowed=False,
                decision=RecheckDecision.THROTTLED_ALREADY_CHECKED_LOCAL_DAY,
                business_date=business_date,
                audit_required=False,
                bypassed_daily_throttle=False,
                reason=SalesCreditReason.AUTOMATIC_RECHECK_THROTTLED_LOCAL_DAY,
                explanation_code=None,
            )
        return RecheckResult(
            allowed=True,
            decision=RecheckDecision.ELIGIBLE,
            business_date=business_date,
            audit_required=False,
            bypassed_daily_throttle=False,
            reason=None,
            explanation_code=None,
        )

    if trigger is not SearchTriggerType.FORCE_RECHECK:
        raise WindowValidationError("recheck_trigger_not_eligible")

    if not selected:
        if force_explanation is not None:
            raise WindowValidationError("unselected_force_explanation")
        return RecheckResult(
            allowed=False,
            decision=RecheckDecision.FORCE_RECHECK_NOT_SELECTED,
            business_date=business_date,
            audit_required=False,
            bypassed_daily_throttle=False,
            reason=None,
            explanation_code=None,
        )
    if (
        type(force_explanation) is not str
        or _EXPLANATION.fullmatch(force_explanation) is None
        or scan_payload({"explanation": force_explanation})
    ):
        raise WindowValidationError("force_explanation_required")
    if position is not WindowPosition.ACTIVE:
        return RecheckResult(
            allowed=False,
            decision=RecheckDecision.WINDOW_NOT_ACTIVE,
            business_date=business_date,
            audit_required=True,
            bypassed_daily_throttle=False,
            reason=SalesCreditReason.FORCE_RECHECK_ACCEPTED,
            explanation_code=force_explanation,
        )
    return RecheckResult(
        allowed=True,
        decision=RecheckDecision.FORCE_RECHECK_SELECTED,
        business_date=business_date,
        audit_required=True,
        bypassed_daily_throttle=last_automatic_check_date == business_date,
        reason=SalesCreditReason.FORCE_RECHECK_ACCEPTED,
        explanation_code=force_explanation,
    )


__all__ = [
    "BUSINESS_TIME_ZONE",
    "BUSINESS_TIME_ZONE_NAME",
    "CalendarWindow",
    "EvidenceTiming",
    "Instant",
    "OrderTiming",
    "RecheckDecision",
    "RecheckResult",
    "RecheckTrigger",
    "WINDOW_DAYS_AFTER_ANCHOR",
    "WindowPosition",
    "WindowValidationError",
    "business_local_date",
    "cancellation_replacement_window",
    "classify_evidence_timing",
    "classify_order_timing",
    "decide_no_order_recheck",
    "review_window",
    "window_position",
]
