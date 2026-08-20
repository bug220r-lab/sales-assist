"""Pure synthetic contact normalization and complete multi-identifier discovery."""

from __future__ import annotations

import hmac
import re
import secrets
from dataclasses import dataclass, field, replace
from datetime import datetime, time, timedelta
from threading import RLock

from synthetic_sales_assist.domain.canonical import canonical_json_bytes
from synthetic_sales_assist.domain.identities import InteractionId, OrderId, RunId
from synthetic_sales_assist.domain.normalization import ascii_four_trim
from synthetic_sales_assist.domain.records import VersionBinding
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.domain.tokens import ImmutableStrEnum
from synthetic_sales_assist.sales_credit.models import (
    ClosedNoteCode,
    InteractionRecord,
    OrderSnapshot,
    SALES_CREDIT_RULE_PACK_VERSION,
    SalesCreditEvaluation,
    SalesCreditReason,
    SalesCreditValidation,
    SearchTriggerType,
    TimestampPrecision,
    WorkflowState,
)
from synthetic_sales_assist.sales_credit.windows import (
    BUSINESS_TIME_ZONE,
    CalendarWindow,
    OrderTiming,
    RecheckResult,
    WindowValidationError,
    business_local_date,
    classify_order_timing,
    decide_no_order_recheck,
)
from synthetic_sales_assist.safety.content import scan_payload
from synthetic_sales_assist.safety.identity import (
    IdentityFirewallError,
    assert_fictional_555_phone,
    assert_synthetic_email,
)


_ASCII_LOWER_TRANSLATION = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "abcdefghijklmnopqrstuvwxyz",
)
_CANONICAL_PHONE_PATTERN = re.compile(r"\A(?:[2-9][0-9]{2})?55501[0-9]{2}\Z", re.ASCII)


class DiscoveryValidationError(ValueError):
    """Reject invalid discovery material without retaining or echoing it."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Sales Credit discovery input rejected: {code}")


class SearchIdentifierKind(ImmutableStrEnum):
    EMAIL = "EMAIL"
    PHONE = "PHONE"


class SearchCompleteness(ImmutableStrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


class DiscoveryOutcome(ImmutableStrEnum):
    """Closed discovery result, including the two exact no-order workflow states."""

    CANDIDATES_FOUND = "CANDIDATES_FOUND"
    SEARCH_INCOMPLETE = "SEARCH_INCOMPLETE"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    CHECKED_NO_ORDER_WINDOW_ACTIVE = "CHECKED_NO_ORDER_WINDOW_ACTIVE"
    REVIEW_WINDOW_CLOSED_NO_ORDER = "REVIEW_WINDOW_CLOSED_NO_ORDER"


def normalize_synthetic_email(value: object) -> str:
    """ASCII-four trim and ASCII-lowercase one exact example.test mailbox."""

    if type(value) is not str:
        raise DiscoveryValidationError("email_type")
    candidate = ascii_four_trim(value)
    if not candidate.isascii():
        raise DiscoveryValidationError("email_grammar")
    canonical = candidate.translate(_ASCII_LOWER_TRANSLATION)
    invalid = False
    try:
        assert_synthetic_email(canonical)
    except IdentityFirewallError:
        invalid = True
    if invalid:
        raise DiscoveryValidationError("email_grammar") from None
    return canonical


def normalize_fictional_phone(value: object) -> str:
    """Normalize an allowlisted 555-01xx spelling without inventing missing digits."""

    if type(value) is not str:
        raise DiscoveryValidationError("phone_type")
    candidate = ascii_four_trim(value)
    invalid = False
    try:
        assert_fictional_555_phone(candidate)
    except IdentityFirewallError:
        invalid = True
    if invalid:
        raise DiscoveryValidationError("phone_grammar") from None
    digits = "".join(character for character in candidate if character.isdigit())
    if len(digits) == 11:
        if digits[0] != "1":
            raise DiscoveryValidationError("phone_country_code")
        digits = digits[1:]
    if len(digits) not in {7, 10}:
        raise DiscoveryValidationError("phone_length")
    return digits


@dataclass(frozen=True, slots=True, repr=False)
class SearchIdentifier:
    kind: SearchIdentifierKind
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.kind) is not SearchIdentifierKind:
            raise DiscoveryValidationError("identifier_kind_type")
        if type(self.value) is not str:
            raise DiscoveryValidationError("identifier_value_type")
        if self.kind is SearchIdentifierKind.EMAIL:
            if self.value != normalize_synthetic_email(self.value):
                raise DiscoveryValidationError("identifier_not_canonical")
        elif _CANONICAL_PHONE_PATTERN.fullmatch(self.value) is None:
            raise DiscoveryValidationError("identifier_not_canonical")

    def __repr__(self) -> str:
        return f"SearchIdentifier(kind={self.kind.value}, value=<redacted>)"


@dataclass(frozen=True, slots=True)
class DiscoveryPlan:
    """Every distinct valid identifier, deterministically ordered for mandatory search."""

    identifiers: tuple[SearchIdentifier, ...]

    def __post_init__(self) -> None:
        if type(self.identifiers) is not tuple or any(
            type(identifier) is not SearchIdentifier for identifier in self.identifiers
        ):
            raise DiscoveryValidationError("plan_identifiers_shape")
        expected = tuple(
            sorted(self.identifiers, key=lambda item: (item.kind.value, item.value))
        )
        if self.identifiers != expected or len(set(self.identifiers)) != len(self.identifiers):
            raise DiscoveryValidationError("plan_identifier_order_or_duplicate")

    @property
    def requires_manual_review(self) -> bool:
        return not self.identifiers


def _require_source_values(value: object, *, code: str) -> tuple[object, ...]:
    if type(value) is not tuple:
        raise DiscoveryValidationError(code)
    return value


def plan_discovery(
    *,
    email_values: tuple[object, ...] = (),
    phone_values: tuple[object, ...] = (),
) -> DiscoveryPlan:
    """Normalize every supplied contact and reject malformed material before rules."""

    emails = _require_source_values(email_values, code="email_values_shape")
    phones = _require_source_values(phone_values, code="phone_values_shape")
    identifiers: set[SearchIdentifier] = set()

    for source in emails:
        canonical = normalize_synthetic_email(source)
        identifiers.add(SearchIdentifier(SearchIdentifierKind.EMAIL, canonical))
    for source in phones:
        canonical = normalize_fictional_phone(source)
        identifiers.add(SearchIdentifier(SearchIdentifierKind.PHONE, canonical))

    ordered_identifiers = tuple(
        sorted(identifiers, key=lambda item: (item.kind.value, item.value))
    )
    return DiscoveryPlan(ordered_identifiers)


@dataclass(frozen=True, slots=True)
class IdentifierSearchResult:
    """One factual native search result; it never assigns a business conclusion."""

    identifier: SearchIdentifier
    completeness: SearchCompleteness
    order_ids: tuple[OrderId, ...]

    def __post_init__(self) -> None:
        if type(self.identifier) is not SearchIdentifier:
            raise DiscoveryValidationError("search_result_identifier_type")
        if type(self.completeness) is not SearchCompleteness:
            raise DiscoveryValidationError("search_result_completeness_type")
        if type(self.order_ids) is not tuple or any(
            type(order_id) is not OrderId for order_id in self.order_ids
        ):
            raise DiscoveryValidationError("search_result_order_ids_shape")
        values = tuple(order_id.value for order_id in self.order_ids)
        if len(values) != len(set(values)):
            raise DiscoveryValidationError("search_result_order_ids_duplicate")
        if values != tuple(sorted(values)):
            object.__setattr__(
                self,
                "order_ids",
                tuple(sorted(self.order_ids, key=lambda item: item.value)),
            )


NativeSearchResultSet = IdentifierSearchResult


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """Complete union/deduplication output with explicit no-order safety status."""

    outcome: DiscoveryOutcome
    order_ids: tuple[OrderId, ...]
    enumeration_complete: bool
    identifiers_required: int
    identifiers_attempted: int
    identifiers_completed: int
    reasons: tuple[SalesCreditReason, ...] = ()

    def __post_init__(self) -> None:
        if type(self.outcome) is not DiscoveryOutcome:
            raise DiscoveryValidationError("discovery_outcome_type")
        if type(self.order_ids) is not tuple or any(
            type(order_id) is not OrderId for order_id in self.order_ids
        ):
            raise DiscoveryValidationError("discovery_order_ids_shape")
        if tuple(sorted(self.order_ids, key=lambda item: item.value)) != self.order_ids:
            raise DiscoveryValidationError("discovery_order_ids_order")
        if len({order_id.value for order_id in self.order_ids}) != len(self.order_ids):
            raise DiscoveryValidationError("discovery_order_ids_duplicate")
        if type(self.enumeration_complete) is not bool:
            raise DiscoveryValidationError("enumeration_complete_type")
        if type(self.identifiers_required) is not int or self.identifiers_required < 0:
            raise DiscoveryValidationError("identifiers_required")
        if type(self.identifiers_attempted) is not int or not (
            0 <= self.identifiers_attempted <= self.identifiers_required
        ):
            raise DiscoveryValidationError("identifiers_attempted")
        if type(self.identifiers_completed) is not int or not (
            0 <= self.identifiers_completed <= self.identifiers_attempted
        ):
            raise DiscoveryValidationError("identifiers_completed")
        if type(self.reasons) is not tuple or any(
            type(reason) is not SalesCreditReason for reason in self.reasons
        ):
            raise DiscoveryValidationError("discovery_reasons")
        if self.reasons != tuple(sorted(set(self.reasons), key=lambda item: item.value)):
            raise DiscoveryValidationError("discovery_reasons")
        expected_complete = (
            self.identifiers_required > 0
            and self.identifiers_completed == self.identifiers_required
        )
        if self.enumeration_complete != expected_complete:
            raise DiscoveryValidationError("discovery_completeness_coherence")
        no_order_outcomes = {
            DiscoveryOutcome.CHECKED_NO_ORDER_WINDOW_ACTIVE,
            DiscoveryOutcome.REVIEW_WINDOW_CLOSED_NO_ORDER,
        }
        if self.outcome is DiscoveryOutcome.CANDIDATES_FOUND and not self.order_ids:
            raise DiscoveryValidationError("discovery_candidate_coherence")
        if self.outcome is not DiscoveryOutcome.CANDIDATES_FOUND and self.order_ids:
            raise DiscoveryValidationError("discovery_candidate_coherence")
        if self.outcome in no_order_outcomes and not self.enumeration_complete:
            raise DiscoveryValidationError("discovery_no_order_incomplete")
        if self.outcome is DiscoveryOutcome.SEARCH_INCOMPLETE and self.enumeration_complete:
            raise DiscoveryValidationError("discovery_incomplete_coherence")
        if self.outcome is DiscoveryOutcome.MANUAL_REVIEW_REQUIRED and (
            self.identifiers_required != 0 or self.enumeration_complete
        ):
            raise DiscoveryValidationError("discovery_manual_coherence")
        expected_reasons = {
            DiscoveryOutcome.CANDIDATES_FOUND: (),
            DiscoveryOutcome.SEARCH_INCOMPLETE: (
                SalesCreditReason.IDENTIFIER_SEARCH_INCOMPLETE,
            ),
            DiscoveryOutcome.MANUAL_REVIEW_REQUIRED: (
                SalesCreditReason.NO_USABLE_SEARCH_IDENTIFIER,
            ),
            DiscoveryOutcome.CHECKED_NO_ORDER_WINDOW_ACTIVE: (
                SalesCreditReason.NO_ORDER_WINDOW_ACTIVE,
            ),
            DiscoveryOutcome.REVIEW_WINDOW_CLOSED_NO_ORDER: (
                SalesCreditReason.NO_ORDER_WINDOW_CLOSED,
            ),
        }
        if self.reasons != expected_reasons[self.outcome]:
            raise DiscoveryValidationError("discovery_reason_coherence")


def combine_search_results(
    *,
    plan: DiscoveryPlan,
    results: tuple[IdentifierSearchResult, ...],
    review_window_closed: bool,
) -> DiscoveryResult:
    """Consume every planned result and forbid incomplete no-order conclusions."""

    if type(plan) is not DiscoveryPlan:
        raise DiscoveryValidationError("plan_type")
    if type(results) is not tuple or any(
        type(result) is not IdentifierSearchResult for result in results
    ):
        raise DiscoveryValidationError("results_shape")
    if type(review_window_closed) is not bool:
        raise DiscoveryValidationError("review_window_closed_type")
    if not plan.identifiers:
        if results:
            raise DiscoveryValidationError("results_without_identifiers")
        return DiscoveryResult(
            outcome=DiscoveryOutcome.MANUAL_REVIEW_REQUIRED,
            order_ids=(),
            enumeration_complete=False,
            identifiers_required=0,
            identifiers_attempted=0,
            identifiers_completed=0,
            reasons=(SalesCreditReason.NO_USABLE_SEARCH_IDENTIFIER,),
        )

    expected = set(plan.identifiers)
    result_by_identifier: dict[SearchIdentifier, IdentifierSearchResult] = {}
    for result in results:
        if result.identifier not in expected:
            raise DiscoveryValidationError("unexpected_search_result")
        if result.identifier in result_by_identifier:
            raise DiscoveryValidationError("duplicate_search_result")
        result_by_identifier[result.identifier] = result

    completed = sum(
        result.completeness is SearchCompleteness.COMPLETE
        for result in result_by_identifier.values()
    )
    enumeration_complete = completed == len(plan.identifiers)
    order_by_value: dict[str, OrderId] = {}
    for result in result_by_identifier.values():
        for order_id in result.order_ids:
            order_by_value.setdefault(order_id.value, order_id)
    order_ids = tuple(order_by_value[value] for value in sorted(order_by_value))

    if order_ids:
        outcome = DiscoveryOutcome.CANDIDATES_FOUND
        reasons: tuple[SalesCreditReason, ...] = ()
    elif not enumeration_complete:
        outcome = DiscoveryOutcome.SEARCH_INCOMPLETE
        reasons = (SalesCreditReason.IDENTIFIER_SEARCH_INCOMPLETE,)
    elif review_window_closed:
        outcome = DiscoveryOutcome.REVIEW_WINDOW_CLOSED_NO_ORDER
        reasons = (SalesCreditReason.NO_ORDER_WINDOW_CLOSED,)
    else:
        outcome = DiscoveryOutcome.CHECKED_NO_ORDER_WINDOW_ACTIVE
        reasons = (SalesCreditReason.NO_ORDER_WINDOW_ACTIVE,)
    return DiscoveryResult(
        outcome=outcome,
        order_ids=order_ids,
        enumeration_complete=enumeration_complete,
        identifiers_required=len(plan.identifiers),
        identifiers_attempted=len(result_by_identifier),
        identifiers_completed=completed,
        reasons=reasons,
    )


@dataclass(frozen=True, slots=True, repr=False, kw_only=True)
class OrderSearchRun:
    """One intentional, fully enumerated synthetic order-search invocation."""

    run_id: RunId
    trigger: SearchTriggerType
    interactions: tuple[InteractionRecord, ...] = field(repr=False)
    native_result_sets: tuple[IdentifierSearchResult, ...]
    adapter: VersionBinding
    started_at: CanonicalTimestamp
    completed_at: CanonicalTimestamp
    warnings: tuple[str, ...] = ()
    force_explanation: str | None = field(default=None, repr=False)
    schema_version: str = "sales-credit-order-search-run/v1"
    interaction_ids: tuple[InteractionId, ...] = field(init=False)
    attempted_identifiers: tuple[SearchIdentifier, ...] = field(
        init=False,
        repr=False,
    )
    recheck_results: tuple[RecheckResult, ...] = field(init=False)
    result: DiscoveryResult = field(init=False)

    ADAPTER_VERSION = "sales-credit-search-adapter/v1"

    def __post_init__(self) -> None:
        if type(self.run_id) is not RunId:
            raise DiscoveryValidationError("search_run_id")
        if type(self.trigger) is not SearchTriggerType:
            raise DiscoveryValidationError("search_run_trigger")
        if type(self.interactions) is not tuple or any(
            type(item) is not InteractionRecord for item in self.interactions
        ):
            raise DiscoveryValidationError("search_run_interactions")
        interaction_values = tuple(
            item.interaction_id.value for item in self.interactions
        )
        if (
            not interaction_values
            or interaction_values != tuple(sorted(interaction_values))
            or len(interaction_values) != len(set(interaction_values))
        ):
            raise DiscoveryValidationError("search_run_interactions")
        if any(not item.has_usable_identifier for item in self.interactions):
            raise DiscoveryValidationError("search_run_unusable_interaction")
        object.__setattr__(
            self,
            "interaction_ids",
            tuple(item.interaction_id for item in self.interactions),
        )
        plan = plan_discovery(
            email_values=tuple(
                item.email for item in self.interactions if item.email is not None
            ),
            phone_values=tuple(
                item.phone for item in self.interactions if item.phone is not None
            ),
        )
        object.__setattr__(self, "attempted_identifiers", plan.identifiers)
        if type(self.native_result_sets) is not tuple or any(
            type(item) is not IdentifierSearchResult for item in self.native_result_sets
        ):
            raise DiscoveryValidationError("search_run_results")
        result_identifiers = tuple(
            sorted(
                (item.identifier for item in self.native_result_sets),
                key=lambda item: (item.kind.value, item.value),
            )
        )
        if result_identifiers != plan.identifiers:
            raise DiscoveryValidationError("search_run_attempt_parity")
        if type(self.adapter) is not VersionBinding or (
            self.adapter.component != "sales_credit_search_adapter"
            or self.adapter.version != self.ADAPTER_VERSION
        ):
            raise DiscoveryValidationError("search_run_adapter")
        if type(self.started_at) is not CanonicalTimestamp:
            raise DiscoveryValidationError("search_run_started")
        if type(self.completed_at) is not CanonicalTimestamp:
            raise DiscoveryValidationError("search_run_completed")
        started = (self.started_at.epoch_seconds, self.started_at.nanosecond)
        completed = (self.completed_at.epoch_seconds, self.completed_at.nanosecond)
        if completed < started:
            raise DiscoveryValidationError("search_run_time_order")
        started_date = business_local_date(self.started_at)
        for interaction in self.interactions:
            interaction_date = business_local_date(interaction.effective_at)
            effective = (
                interaction.effective_at.epoch_seconds,
                interaction.effective_at.nanosecond,
            )
            if started_date < interaction_date or (
                started_date == interaction_date
                and (
                    not interaction.effective_precision.proves_same_day_ordering
                    or started <= effective
                )
            ):
                raise DiscoveryValidationError(
                    "search_run_not_after_interaction"
                )
        if type(self.warnings) is not tuple or any(
            type(item) is not str or re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", item) is None
            for item in self.warnings
        ):
            raise DiscoveryValidationError("search_run_warnings")
        if self.warnings != tuple(sorted(set(self.warnings))):
            raise DiscoveryValidationError("search_run_warnings")
        if self.trigger is SearchTriggerType.FORCE_RECHECK:
            if type(self.force_explanation) is not str or re.fullmatch(
                r"[A-Z][A-Z0-9_]{2,63}",
                self.force_explanation,
            ) is None:
                raise DiscoveryValidationError("search_run_force_explanation")
            if scan_payload({"force_explanation": self.force_explanation}):
                raise DiscoveryValidationError("search_run_force_explanation")
        elif self.force_explanation is not None:
                raise DiscoveryValidationError("search_run_force_explanation")
        if self.schema_version != "sales-credit-order-search-run/v1":
            raise DiscoveryValidationError("search_run_schema")
        recheck_results: tuple[RecheckResult, ...] = ()
        if self.trigger in {
            SearchTriggerType.AUTOMATIC_RECHECK,
            SearchTriggerType.FORCE_RECHECK,
        }:
            if any(
                interaction.workflow_state
                is not WorkflowState.CHECKED_NO_ORDER_WINDOW_ACTIVE
                or interaction.last_check_at is None
                or interaction.next_eligible_check_at is None
                for interaction in self.interactions
            ):
                raise DiscoveryValidationError("search_run_recheck_state")
            derived_results: list[RecheckResult] = []
            for interaction in self.interactions:
                last_check = interaction.last_check_at
                if last_check is not None and (
                    last_check.epoch_seconds,
                    last_check.nanosecond,
                ) > started:
                    raise DiscoveryValidationError("search_run_recheck_ineligible")
                try:
                    decision = decide_no_order_recheck(
                        trigger=self.trigger,
                        selected=self.trigger is SearchTriggerType.FORCE_RECHECK,
                        at=self.started_at,
                        window=CalendarWindow(
                            start=interaction.review_window_start,
                            end=interaction.review_window_end,
                        ),
                        last_automatic_check_date=(
                            business_local_date(last_check)
                            if last_check is not None
                            else None
                        ),
                        force_explanation=self.force_explanation,
                    )
                except WindowValidationError:
                    raise DiscoveryValidationError(
                        "search_run_recheck_ineligible"
                    ) from None
                derived_results.append(decision)
            recheck_results = tuple(derived_results)
            if any(
                not decision.allowed
                and started_date <= interaction.review_window_end
                for interaction, decision in zip(
                    self.interactions,
                    recheck_results,
                    strict=True,
                )
            ):
                raise DiscoveryValidationError("search_run_recheck_ineligible")
        object.__setattr__(self, "recheck_results", recheck_results)
        completed_date = business_local_date(self.completed_at)
        review_window_closed = all(
            completed_date > interaction.review_window_end
            for interaction in self.interactions
        )
        object.__setattr__(
            self,
            "result",
            combine_search_results(
                plan=plan,
                results=self.native_result_sets,
                review_window_closed=review_window_closed,
            ),
        )

    def __repr__(self) -> str:
        return "OrderSearchRun(<redacted>)"


class NoOrderLedgerError(RuntimeError):
    """Reject a no-order state command without retaining or echoing its material."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Sales Credit no-order state rejected: {code}")


class SearchRunAuthorityError(RuntimeError):
    """Reject a conflicting or invalid process-local search-run claim."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Sales Credit search-run authority rejected: {code}")


class SearchRunPartitionKind(ImmutableStrEnum):
    POSITIVE_CASE_ACTIVE = "POSITIVE_CASE_ACTIVE"
    NO_ORDER_ACTIVE = "NO_ORDER_ACTIVE"
    NO_ORDER_MINIMIZED = "NO_ORDER_MINIMIZED"


class CandidateInteractionDisposition(ImmutableStrEnum):
    """Selector-owned candidate conclusion for one native interaction owner."""

    QUALIFYING = "QUALIFYING"
    DETERMINISTICALLY_NONQUALIFYING = "DETERMINISTICALLY_NONQUALIFYING"
    PRESERVED_UNCERTAIN = "PRESERVED_UNCERTAIN"


class InteractionSearchDisposition(ImmutableStrEnum):
    """Governed per-interaction effect of one evaluated search invocation."""

    POSITIVE_CANDIDATE = "POSITIVE_CANDIDATE"
    NO_ORDER_WINDOW_ACTIVE = "NO_ORDER_WINDOW_ACTIVE"
    NO_ORDER_WINDOW_CLOSED = "NO_ORDER_WINDOW_CLOSED"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


def _interaction_token_value(value: InteractionRecord) -> dict[str, object]:
    return {
        "active_notes": value.active_notes,
        "corrected_at": None if value.corrected_at is None else value.corrected_at.value,
        "corrected_precision": (
            None if value.corrected_precision is None else value.corrected_precision.value
        ),
        "email": value.email,
        "interaction_id": value.interaction_id.value,
        "last_check_at": None if value.last_check_at is None else value.last_check_at.value,
        "next_eligible_check_at": (
            None
            if value.next_eligible_check_at is None
            else value.next_eligible_check_at.value
        ),
        "part_request": value.part_request,
        "phone": value.phone,
        "provenance": value.provenance.to_dict(),
        "recorded_at": value.recorded_at.value,
        "review_window_end": value.review_window_end.isoformat(),
        "review_window_start": value.review_window_start.isoformat(),
        "schema_version": value.schema_version,
        "source_ref": value.source_ref.value,
        "timestamp_precision": value.timestamp_precision.value,
        "vin_like_reference": value.vin_like_reference,
        "workflow_state": value.workflow_state.value,
    }


def _identifier_token_value(value: SearchIdentifier) -> dict[str, str]:
    return {"kind": value.kind.value, "value": value.value}


def _native_result_token_value(value: IdentifierSearchResult) -> dict[str, object]:
    return {
        "completeness": value.completeness.value,
        "identifier": _identifier_token_value(value.identifier),
        "order_ids": [order_id.value for order_id in value.order_ids],
    }


def _recheck_token_value(value: RecheckResult) -> dict[str, object]:
    return {
        "allowed": value.allowed,
        "audit_required": value.audit_required,
        "business_date": value.business_date.isoformat(),
        "bypassed_daily_throttle": value.bypassed_daily_throttle,
        "decision": value.decision.value,
        "explanation_code": value.explanation_code,
        "reason": None if value.reason is None else value.reason.value,
    }


def _discovery_result_token_value(value: DiscoveryResult) -> dict[str, object]:
    return {
        "enumeration_complete": value.enumeration_complete,
        "identifiers_attempted": value.identifiers_attempted,
        "identifiers_completed": value.identifiers_completed,
        "identifiers_required": value.identifiers_required,
        "order_ids": [order_id.value for order_id in value.order_ids],
        "outcome": value.outcome.value,
        "reasons": [reason.value for reason in value.reasons],
    }


def _order_search_run_token(run: OrderSearchRun) -> bytes:
    value: dict[str, object] = {
        "adapter": run.adapter.to_dict(),
        "attempted_identifiers": [
            _identifier_token_value(identifier)
            for identifier in run.attempted_identifiers
        ],
        "completed_at": run.completed_at.value,
        "force_explanation": run.force_explanation,
        "interaction_ids": [item.value for item in run.interaction_ids],
        "interactions": [
            _interaction_token_value(interaction)
            for interaction in run.interactions
        ],
        "native_result_sets": [
            _native_result_token_value(result) for result in run.native_result_sets
        ],
        "recheck_results": [
            _recheck_token_value(result) for result in run.recheck_results
        ],
        "result": _discovery_result_token_value(run.result),
        "run_id": run.run_id.value,
        "schema_version": run.schema_version,
        "started_at": run.started_at.value,
        "trigger": run.trigger.value,
        "warnings": list(run.warnings),
    }
    return canonical_json_bytes(value, expected_members=set(value))


def _hash_binding_token(value: object) -> dict[str, str] | None:
    if value is None:
        return None
    return {"domain": value.domain, "sha256": value.sha256}


def _line_snapshot_token(value: object) -> dict[str, object]:
    return {
        "canonical_es_number": value.canonical_es_number,
        "canonical_mfg_oe_number": value.canonical_mfg_oe_number,
        "content": _hash_binding_token(value.content),
        "description": value.description,
        "line_id": value.line_id.value,
        "line_value": value.line_value.to_json_value(),
        "observed_availability": value.observed_availability,
        "observed_eta": None if value.observed_eta is None else value.observed_eta.value,
        "quantity": value.quantity.to_json_value(),
        "raw_es_number": value.raw_es_number,
        "raw_line_rep": value.raw_line_rep,
        "raw_mfg_oe_number": value.raw_mfg_oe_number,
        "sku_id": value.sku_id.value,
        "warnings": list(value.warnings),
    }


def _order_snapshot_token(value: OrderSnapshot) -> dict[str, object]:
    return {
        "active_notes": value.active_notes,
        "canceled_at": None if value.canceled_at is None else value.canceled_at.value,
        "captured_at": value.captured_at.value,
        "current_value": (
            None if value.current_value is None else value.current_value.to_json_value()
        ),
        "customer_ids": [item.value for item in value.customer_ids],
        "extraction_status": value.extraction_status.value,
        "lifecycle_status": value.lifecycle_status.value,
        "lines": [_line_snapshot_token(item) for item in value.lines],
        "material_changes": [
            {
                "affects_commercial_value": item.affects_commercial_value,
                "change_id": item.change_id.value,
                "kind": item.kind.value,
            }
            for item in value.material_changes
        ],
        "notes_scan_status": value.notes_scan_status.value,
        "order_id": None if value.order_id is None else value.order_id.value,
        "parser": value.parser.to_dict(),
        "placed_at": None if value.placed_at is None else value.placed_at.value,
        "placed_at_precision": (
            None if value.placed_at_precision is None else value.placed_at_precision.value
        ),
        "placed_value": (
            None if value.placed_value is None else value.placed_value.to_json_value()
        ),
        "provenance": _hash_binding_token(value.provenance),
        "raw_order_rep": value.raw_order_rep,
        "raw_order_status": value.raw_order_status,
        "schema_version": value.schema_version,
        "snapshot_id": value.snapshot_id.value,
        "source_ref": None if value.source_ref is None else value.source_ref.value,
        "warnings": list(value.warnings),
    }


def _post_evaluation_command_bytes(
    *,
    run: OrderSearchRun,
    candidate_evaluations: tuple[SelectorOwnedCandidateEvaluation, ...],
) -> bytes:
    document = {
        "candidate_evaluations": [
            {
                "evaluation": item.evaluation.to_dict(),
                "evaluated_at": item.evaluated_at.value,
                "interaction_id": item.interaction_id.value,
                "snapshot": _order_snapshot_token(item.snapshot),
            }
            for item in candidate_evaluations
        ],
        "run": _order_search_run_token(run).decode("utf-8"),
    }
    return canonical_json_bytes(document, expected_members=set(document))


@dataclass(frozen=True, slots=True, repr=False)
class SearchRunAuthorityClaim:
    """Opaque rollback handle for one exact canonical run claim."""

    run_id: RunId
    newly_acquired: bool
    _authority: object = field(repr=False, compare=False)
    _owner: object = field(repr=False, compare=False)
    _canonical_bytes: bytes = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.run_id) is not RunId:
            raise SearchRunAuthorityError("search_run_claim_id")
        if type(self.newly_acquired) is not bool:
            raise SearchRunAuthorityError("search_run_claim_state")
        if type(self._canonical_bytes) is not bytes:
            raise SearchRunAuthorityError("search_run_claim_material")

    def __repr__(self) -> str:
        return "SearchRunAuthorityClaim(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class SearchRunOwnerPartition:
    """Identity-free owner disposition retained after full-run canonical sealing."""

    partition_id: str
    kind: SearchRunPartitionKind
    _owner: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            type(self.partition_id) is not str
            or not self.partition_id.startswith("SYN-SEARCH-RUN-PARTITION-")
            or not self.partition_id.removeprefix(
                "SYN-SEARCH-RUN-PARTITION-"
            ).isdigit()
        ):
            raise SearchRunAuthorityError("search_run_partition_id")
        if type(self.kind) is not SearchRunPartitionKind:
            raise SearchRunAuthorityError("search_run_partition_kind")

    def __repr__(self) -> str:
        return "SearchRunOwnerPartition(<minimized>)"


@dataclass(frozen=True, slots=True, repr=False)
class SearchRunSeal:
    """Opaque handle for finalizing or rolling back one atomic canonical seal."""

    run_id: RunId
    _authority: object = field(repr=False, compare=False)
    _token: object = field(repr=False, compare=False)

    def __repr__(self) -> str:
        return "SearchRunSeal(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class SearchRunPartitionTransfer:
    """Opaque rollback handle for one atomic sealed-run partition split."""

    run_id: RunId
    outgoing_partition: SearchRunOwnerPartition
    incoming_partitions: tuple[SearchRunOwnerPartition, ...]
    retain_outgoing: bool
    _authority: object = field(repr=False, compare=False)
    _handle: object = field(repr=False, compare=False)

    def __repr__(self) -> str:
        return "SearchRunPartitionTransfer(<minimized>)"


@dataclass(frozen=True, slots=True, repr=False)
class _SearchRunAuthorityEntry:
    canonical_bytes: bytes = field(repr=False)
    owners: tuple[object, ...] = field(repr=False)


@dataclass(frozen=True, slots=True, repr=False)
class _SealedSearchRunEntry:
    canonical_authenticator: bytes = field(repr=False)
    partitions: tuple[SearchRunOwnerPartition, ...]


@dataclass(frozen=True, slots=True, repr=False)
class _PendingSearchRunSeal:
    prior: _SearchRunAuthorityEntry = field(repr=False)
    sealed: _SealedSearchRunEntry


@dataclass(frozen=True, slots=True, repr=False)
class _PendingSearchRunPartitionTransfer:
    prior: _SealedSearchRunEntry
    transferred: _SealedSearchRunEntry
    newly_added_partitions: tuple[SearchRunOwnerPartition, ...]
    outgoing_removed: bool


@dataclass(frozen=True, slots=True, repr=False)
class _RetiredSearchRunEntry:
    receipt_id: str
    canonical_authenticator: bytes = field(repr=False)
    terminal_replay: bool
    owner: object = field(repr=False, compare=False)


class InMemorySearchRunAuthority:
    """One-lock exact RunId/material authority shared by process-local ledgers."""

    _RECEIPT_PREFIX = "SYN-NO-ORDER-CLOSURE-"

    def __init__(self) -> None:
        self._lock = RLock()
        self._owners: set[object] = set()
        self._active: dict[str, _SearchRunAuthorityEntry] = {}
        self._sealed: dict[str, _SealedSearchRunEntry] = {}
        self._pending_seals: dict[object, _PendingSearchRunSeal] = {}
        self._pending_seal_by_run: dict[str, object] = {}
        self._pending_partition_transfers: dict[
            object, _PendingSearchRunPartitionTransfer
        ] = {}
        self._pending_partition_transfer_by_run: dict[str, object] = {}
        self._issued_partitions: dict[str, SearchRunOwnerPartition] = {}
        self._retired: dict[str, _RetiredSearchRunEntry] = {}
        self._seal_key = secrets.token_bytes(32)
        self._next_partition_ordinal = 1
        self._next_receipt_ordinal = 1

    def new_owner(self) -> object:
        """Issue an opaque owner handle scoped to this authority instance."""

        owner = object()
        with self._lock:
            self._owners.add(owner)
        return owner

    def _require_owner(self, owner: object) -> None:
        if owner not in self._owners:
            raise SearchRunAuthorityError("search_run_owner")

    def _seal_authenticator(self, canonical_bytes: bytes) -> bytes:
        return hmac.digest(self._seal_key, canonical_bytes, "sha256")

    def new_partition(
        self,
        *,
        owner: object,
        kind: SearchRunPartitionKind,
    ) -> SearchRunOwnerPartition:
        """Issue one opaque identity-free owner disposition for an atomic seal."""

        if type(kind) is not SearchRunPartitionKind:
            raise SearchRunAuthorityError("search_run_partition_kind")
        with self._lock:
            self._require_owner(owner)
            partition = SearchRunOwnerPartition(
                partition_id=(
                    "SYN-SEARCH-RUN-PARTITION-"
                    f"{self._next_partition_ordinal:012d}"
                ),
                kind=kind,
                _owner=owner,
            )
            self._next_partition_ordinal += 1
            self._issued_partitions[partition.partition_id] = partition
            return partition

    def discard_partition(
        self,
        partition: SearchRunOwnerPartition,
        *,
        owner: object,
    ) -> None:
        """Discard an issued partition that was never committed into a seal."""

        if type(partition) is not SearchRunOwnerPartition:
            raise SearchRunAuthorityError("search_run_partition")
        with self._lock:
            self._require_owner(owner)
            issued = self._issued_partitions.get(partition.partition_id)
            if issued is not partition or partition._owner is not owner:
                raise SearchRunAuthorityError("search_run_partition")
            if any(
                any(retained is partition for retained in entry.partitions)
                for entry in self._sealed.values()
            ):
                raise SearchRunAuthorityError("search_run_partition_active")
            if any(
                any(
                    retained is partition
                    for retained in (
                        *pending_transfer.prior.partitions,
                        *pending_transfer.transferred.partitions,
                    )
                )
                for pending_transfer in self._pending_partition_transfers.values()
            ):
                raise SearchRunAuthorityError("search_run_partition_active")
            self._issued_partitions.pop(partition.partition_id)

    def claim(
        self,
        run: OrderSearchRun,
        *,
        owner: object,
    ) -> SearchRunAuthorityClaim:
        """Claim exact canonical material or reject RunId reuse with changed bytes."""

        if type(run) is not OrderSearchRun:
            raise SearchRunAuthorityError("search_run_type")
        try:
            validated_run = replace(run)
        except (TypeError, ValueError):
            raise SearchRunAuthorityError("search_run_invalid") from None
        if validated_run != run:
            raise SearchRunAuthorityError("search_run_derived_material")
        canonical_bytes = _order_search_run_token(validated_run)
        run_key = validated_run.run_id.value
        with self._lock:
            self._require_owner(owner)
            if run_key in self._retired:
                raise SearchRunAuthorityError("search_run_retired")
            if run_key in self._pending_seal_by_run:
                raise SearchRunAuthorityError("search_run_seal_pending")
            if run_key in self._pending_partition_transfer_by_run:
                raise SearchRunAuthorityError("search_run_partition_transfer_pending")
            sealed = self._sealed.get(run_key)
            if sealed is not None:
                if not hmac.compare_digest(
                    sealed.canonical_authenticator,
                    self._seal_authenticator(canonical_bytes),
                ):
                    raise SearchRunAuthorityError("search_run_material_conflict")
                if not any(
                    partition._owner is owner
                    for partition in sealed.partitions
                ):
                    raise SearchRunAuthorityError("search_run_sealed_owner")
                return SearchRunAuthorityClaim(
                    run_id=validated_run.run_id,
                    newly_acquired=False,
                    _authority=self,
                    _owner=owner,
                    _canonical_bytes=canonical_bytes,
                )
            prior = self._active.get(run_key)
            if prior is not None:
                if prior.canonical_bytes != canonical_bytes:
                    raise SearchRunAuthorityError("search_run_material_conflict")
                newly_acquired = not any(
                    retained_owner is owner for retained_owner in prior.owners
                )
                if newly_acquired:
                    self._active[run_key] = _SearchRunAuthorityEntry(
                        canonical_bytes=prior.canonical_bytes,
                        owners=(*prior.owners, owner),
                    )
            else:
                newly_acquired = True
                self._active[run_key] = _SearchRunAuthorityEntry(
                    canonical_bytes=canonical_bytes,
                    owners=(owner,),
                )
            return SearchRunAuthorityClaim(
                run_id=validated_run.run_id,
                newly_acquired=newly_acquired,
                _authority=self,
                _owner=owner,
                _canonical_bytes=canonical_bytes,
            )

    def seal_run(
        self,
        claims: tuple[SearchRunAuthorityClaim, ...],
        *,
        partitions: tuple[SearchRunOwnerPartition, ...],
    ) -> SearchRunSeal:
        """Atomically replace one full run with an HMAC and owner dispositions.

        The returned handle must be committed after every consuming ledger commits, or
        rolled back together with those ledgers.  Raw bytes remain rollback material
        only until ``commit_seal``.
        """

        if type(claims) is not tuple or not claims or any(
            type(claim) is not SearchRunAuthorityClaim
            or claim._authority is not self
            for claim in claims
        ):
            raise SearchRunAuthorityError("search_run_seal_claims")
        if type(partitions) is not tuple or not partitions or any(
            type(partition) is not SearchRunOwnerPartition
            for partition in partitions
        ):
            raise SearchRunAuthorityError("search_run_seal_partitions")
        run_id = claims[0].run_id
        canonical_bytes = claims[0]._canonical_bytes
        if any(
            claim.run_id != run_id
            or claim._canonical_bytes != canonical_bytes
            for claim in claims
        ):
            raise SearchRunAuthorityError("search_run_seal_claims")
        claim_owners = tuple(claim._owner for claim in claims)
        if len({id(owner) for owner in claim_owners}) != len(claim_owners):
            raise SearchRunAuthorityError("search_run_seal_claims")
        partition_ids = tuple(partition.partition_id for partition in partitions)
        if len(set(partition_ids)) != len(partition_ids):
            raise SearchRunAuthorityError("search_run_seal_partitions")

        run_key = run_id.value
        with self._lock:
            if run_key in self._pending_seal_by_run:
                raise SearchRunAuthorityError("search_run_seal_pending")
            if run_key in self._sealed:
                raise SearchRunAuthorityError("search_run_already_sealed")
            prior = self._active.get(run_key)
            if prior is None or prior.canonical_bytes != canonical_bytes:
                raise SearchRunAuthorityError("search_run_seal_missing")
            if len(prior.owners) != len(claim_owners) or any(
                not any(owner is claimed for claimed in claim_owners)
                for owner in prior.owners
            ):
                raise SearchRunAuthorityError("search_run_seal_claims")
            for partition in partitions:
                self._require_owner(partition._owner)
                if self._issued_partitions.get(partition.partition_id) is not partition:
                    raise SearchRunAuthorityError("search_run_partition")
            seal_handle = object()
            sealed = _SealedSearchRunEntry(
                canonical_authenticator=self._seal_authenticator(canonical_bytes),
                partitions=partitions,
            )
            self._active.pop(run_key)
            self._sealed[run_key] = sealed
            self._pending_seals[seal_handle] = _PendingSearchRunSeal(
                prior=prior,
                sealed=sealed,
            )
            self._pending_seal_by_run[run_key] = seal_handle
            return SearchRunSeal(
                run_id=run_id,
                _authority=self,
                _token=seal_handle,
            )

    def seal_contains(
        self,
        seal: SearchRunSeal,
        *,
        partition: SearchRunOwnerPartition,
    ) -> bool:
        """Return whether a pending seal contains the exact issued partition."""

        if (
            type(seal) is not SearchRunSeal
            or seal._authority is not self
            or type(partition) is not SearchRunOwnerPartition
        ):
            raise SearchRunAuthorityError("search_run_seal")
        with self._lock:
            pending = self._pending_seals.get(seal._token)
            if pending is None:
                raise SearchRunAuthorityError("search_run_seal")
            return any(
                retained is partition for retained in pending.sealed.partitions
            )

    def commit_seal(self, seal: SearchRunSeal) -> None:
        """Erase rollback bytes and make the HMAC-only partition durable."""

        if type(seal) is not SearchRunSeal or seal._authority is not self:
            raise SearchRunAuthorityError("search_run_seal")
        with self._lock:
            pending = self._pending_seals.pop(seal._token, None)
            if pending is None:
                raise SearchRunAuthorityError("search_run_seal")
            seal_handle = self._pending_seal_by_run.get(seal.run_id.value)
            if seal_handle is not seal._token:
                self._pending_seals[seal._token] = pending
                raise SearchRunAuthorityError("search_run_seal")
            self._pending_seal_by_run.pop(seal.run_id.value)

    def rollback_seal(self, seal: SearchRunSeal) -> None:
        """Restore exact pre-seal authority state after a composed rollback."""

        if type(seal) is not SearchRunSeal or seal._authority is not self:
            raise SearchRunAuthorityError("search_run_seal")
        with self._lock:
            pending = self._pending_seals.pop(seal._token, None)
            if pending is None:
                raise SearchRunAuthorityError("search_run_seal")
            seal_handle = self._pending_seal_by_run.get(seal.run_id.value)
            if seal_handle is not seal._token:
                self._pending_seals[seal._token] = pending
                raise SearchRunAuthorityError("search_run_seal")
            retained = self._sealed.get(seal.run_id.value)
            if retained is not pending.sealed:
                self._pending_seals[seal._token] = pending
                raise SearchRunAuthorityError("search_run_seal_conflict")
            self._sealed.pop(seal.run_id.value)
            self._active[seal.run_id.value] = pending.prior
            self._pending_seal_by_run.pop(seal.run_id.value)

    def stage_partition_transfer(
        self,
        run_id: RunId,
        *,
        outgoing_partition: SearchRunOwnerPartition,
        incoming_partitions: tuple[SearchRunOwnerPartition, ...],
        retain_outgoing: bool,
    ) -> SearchRunPartitionTransfer:
        """Stage an atomic HMAC-only per-root partition split for a sealed run."""

        if (
            type(run_id) is not RunId
            or type(outgoing_partition) is not SearchRunOwnerPartition
            or type(incoming_partitions) is not tuple
            or not incoming_partitions
            or any(
                type(partition) is not SearchRunOwnerPartition
                for partition in incoming_partitions
            )
            or type(retain_outgoing) is not bool
        ):
            raise SearchRunAuthorityError("search_run_partition_transfer")
        if any(
            outgoing_partition is incoming_partition
            for incoming_partition in incoming_partitions
        ) or len(
            {partition.partition_id for partition in incoming_partitions}
        ) != len(incoming_partitions):
            raise SearchRunAuthorityError("search_run_partition_transfer")
        with self._lock:
            run_key = run_id.value
            if (
                run_key in self._pending_seal_by_run
                or run_key in self._pending_partition_transfer_by_run
            ):
                raise SearchRunAuthorityError(
                    "search_run_partition_transfer_pending"
                )
            if (
                self._issued_partitions.get(outgoing_partition.partition_id)
                is not outgoing_partition
                or any(
                    self._issued_partitions.get(partition.partition_id)
                    is not partition
                    for partition in incoming_partitions
                )
            ):
                raise SearchRunAuthorityError("search_run_partition")
            if any(
                partition.kind
                is not SearchRunPartitionKind.POSITIVE_CASE_ACTIVE
                for partition in incoming_partitions
            ):
                raise SearchRunAuthorityError("search_run_partition_transfer_kind")
            sealed = self._sealed.get(run_key)
            if sealed is None or not any(
                partition is outgoing_partition
                for partition in sealed.partitions
            ):
                raise SearchRunAuthorityError(
                    "search_run_partition_transfer_missing"
                )
            if any(
                any(
                    retained is incoming
                    for retained in entry.partitions
                )
                for entry in self._sealed.values()
                for incoming in incoming_partitions
            ):
                raise SearchRunAuthorityError("search_run_partition_transfer_active")
            retained_partitions = (
                sealed.partitions
                if retain_outgoing
                else tuple(
                    partition
                    for partition in sealed.partitions
                    if partition is not outgoing_partition
                )
            )
            transferred = _SealedSearchRunEntry(
                canonical_authenticator=sealed.canonical_authenticator,
                partitions=(*retained_partitions, *incoming_partitions),
            )
            transfer_handle = object()
            self._sealed[run_key] = transferred
            self._pending_partition_transfers[transfer_handle] = (
                _PendingSearchRunPartitionTransfer(
                    prior=sealed,
                    transferred=transferred,
                    newly_added_partitions=incoming_partitions,
                    outgoing_removed=not retain_outgoing,
                )
            )
            self._pending_partition_transfer_by_run[run_key] = transfer_handle
            return SearchRunPartitionTransfer(
                run_id=run_id,
                outgoing_partition=outgoing_partition,
                incoming_partitions=incoming_partitions,
                retain_outgoing=retain_outgoing,
                _authority=self,
                _handle=transfer_handle,
            )

    def partition_transfer_matches(
        self,
        transfer: SearchRunPartitionTransfer,
        *,
        run_id: RunId,
        outgoing_partition: SearchRunOwnerPartition,
        incoming_count: int,
        retain_outgoing: bool,
    ) -> bool:
        if (
            type(transfer) is not SearchRunPartitionTransfer
            or transfer._authority is not self
            or type(run_id) is not RunId
            or type(outgoing_partition) is not SearchRunOwnerPartition
            or type(incoming_count) is not int
            or incoming_count <= 0
            or type(retain_outgoing) is not bool
        ):
            raise SearchRunAuthorityError("search_run_partition_transfer")
        with self._lock:
            pending = self._pending_partition_transfers.get(transfer._handle)
            return (
                pending is not None
                and transfer.run_id == run_id
                and transfer.outgoing_partition is outgoing_partition
                and len(transfer.incoming_partitions) == incoming_count
                and transfer.retain_outgoing is retain_outgoing
            )

    def commit_partition_transfer(
        self,
        transfer: SearchRunPartitionTransfer,
    ) -> None:
        if (
            type(transfer) is not SearchRunPartitionTransfer
            or transfer._authority is not self
        ):
            raise SearchRunAuthorityError("search_run_partition_transfer")
        with self._lock:
            pending = self._pending_partition_transfers.pop(
                transfer._handle,
                None,
            )
            if pending is None:
                raise SearchRunAuthorityError("search_run_partition_transfer")
            retained_handle = self._pending_partition_transfer_by_run.get(
                transfer.run_id.value
            )
            if retained_handle is not transfer._handle:
                self._pending_partition_transfers[transfer._handle] = pending
                raise SearchRunAuthorityError("search_run_partition_transfer")
            self._pending_partition_transfer_by_run.pop(transfer.run_id.value)
            if pending.outgoing_removed:
                self._issued_partitions.pop(
                    transfer.outgoing_partition.partition_id,
                    None,
                )

    def rollback_partition_transfer(
        self,
        transfer: SearchRunPartitionTransfer,
    ) -> None:
        if (
            type(transfer) is not SearchRunPartitionTransfer
            or transfer._authority is not self
        ):
            raise SearchRunAuthorityError("search_run_partition_transfer")
        with self._lock:
            pending = self._pending_partition_transfers.pop(
                transfer._handle,
                None,
            )
            if pending is None:
                raise SearchRunAuthorityError("search_run_partition_transfer")
            retained_handle = self._pending_partition_transfer_by_run.get(
                transfer.run_id.value
            )
            current = self._sealed.get(transfer.run_id.value)
            if (
                retained_handle is not transfer._handle
                or current is not pending.transferred
            ):
                self._pending_partition_transfers[transfer._handle] = pending
                raise SearchRunAuthorityError(
                    "search_run_partition_transfer_conflict"
                )
            self._sealed[transfer.run_id.value] = pending.prior
            self._pending_partition_transfer_by_run.pop(transfer.run_id.value)
            for incoming_partition in pending.newly_added_partitions:
                self._issued_partitions.pop(
                    incoming_partition.partition_id,
                    None,
                )

    def is_sealed_run(self, run_id: RunId) -> bool:
        """Return whether any minimized owner partition still binds this RunId."""

        if type(run_id) is not RunId:
            raise SearchRunAuthorityError("search_run_id")
        with self._lock:
            return run_id.value in self._sealed

    def verify_sealed(self, run: OrderSearchRun) -> None:
        """Verify exact sealed run material without acquiring an owner partition."""

        if type(run) is not OrderSearchRun:
            raise SearchRunAuthorityError("search_run_type")
        try:
            validated_run = replace(run)
        except (TypeError, ValueError):
            raise SearchRunAuthorityError("search_run_invalid") from None
        if validated_run != run:
            raise SearchRunAuthorityError("search_run_derived_material")
        canonical_bytes = _order_search_run_token(validated_run)
        with self._lock:
            sealed = self._sealed.get(validated_run.run_id.value)
            if sealed is None:
                raise SearchRunAuthorityError("search_run_sealed_missing")
            if not hmac.compare_digest(
                sealed.canonical_authenticator,
                self._seal_authenticator(canonical_bytes),
            ):
                raise SearchRunAuthorityError("search_run_material_conflict")

    def release_partition(
        self,
        run_id: RunId,
        partition: SearchRunOwnerPartition,
        *,
        owner: object,
    ) -> None:
        """Release one sealed owner disposition without exposing canonical bytes."""

        if type(run_id) is not RunId or type(partition) is not SearchRunOwnerPartition:
            raise SearchRunAuthorityError("search_run_partition")
        with self._lock:
            self._require_owner(owner)
            if run_id.value in self._pending_seal_by_run:
                raise SearchRunAuthorityError("search_run_seal_pending")
            if run_id.value in self._pending_partition_transfer_by_run:
                raise SearchRunAuthorityError(
                    "search_run_partition_transfer_pending"
                )
            issued = self._issued_partitions.get(partition.partition_id)
            if issued is not partition or partition._owner is not owner:
                raise SearchRunAuthorityError("search_run_partition")
            sealed = self._sealed.get(run_id.value)
            if sealed is None or not any(
                retained is partition for retained in sealed.partitions
            ):
                raise SearchRunAuthorityError("search_run_partition_missing")
            remaining = tuple(
                retained
                for retained in sealed.partitions
                if retained is not partition
            )
            self._issued_partitions.pop(partition.partition_id)
            if remaining:
                self._sealed[run_id.value] = _SealedSearchRunEntry(
                    canonical_authenticator=sealed.canonical_authenticator,
                    partitions=remaining,
                )
            else:
                self._sealed.pop(run_id.value)

    def resolve_retired(
        self,
        run_id: RunId,
        *,
        owner: object,
        canonical_authenticator: bytes,
    ) -> tuple[str, bool] | None:
        """Resolve exact retired material without retaining its canonical bytes."""

        if type(run_id) is not RunId:
            raise SearchRunAuthorityError("search_run_id")
        if (
            type(canonical_authenticator) is not bytes
            or len(canonical_authenticator) != 32
        ):
            raise SearchRunAuthorityError("search_run_authenticator")
        with self._lock:
            self._require_owner(owner)
            entry = self._retired.get(run_id.value)
            if entry is None:
                return None
            if entry.owner is not owner:
                raise SearchRunAuthorityError("search_run_retired")
            if not hmac.compare_digest(
                entry.canonical_authenticator,
                canonical_authenticator,
            ):
                raise SearchRunAuthorityError("search_run_material_conflict")
            return entry.receipt_id, entry.terminal_replay

    def rollback(self, claim: SearchRunAuthorityClaim) -> None:
        """Undo only the owner addition performed by this uncommitted claim."""

        if type(claim) is not SearchRunAuthorityClaim or claim._authority is not self:
            raise SearchRunAuthorityError("search_run_claim")
        if not claim.newly_acquired:
            return
        with self._lock:
            self._require_owner(claim._owner)
            prior = self._active.get(claim.run_id.value)
            if prior is None:
                return
            if prior.canonical_bytes != claim._canonical_bytes:
                raise SearchRunAuthorityError("search_run_claim_conflict")
            remaining = tuple(
                owner for owner in prior.owners if owner is not claim._owner
            )
            if remaining:
                self._active[claim.run_id.value] = _SearchRunAuthorityEntry(
                    canonical_bytes=prior.canonical_bytes,
                    owners=remaining,
                )
            else:
                self._active.pop(claim.run_id.value)

    def release_run(self, run_id: RunId, *, owner: object) -> None:
        """Release one committed owner's active claim without retiring the RunId."""

        if type(run_id) is not RunId:
            raise SearchRunAuthorityError("search_run_release_id")
        with self._lock:
            self._require_owner(owner)
            if run_id.value in self._pending_seal_by_run:
                raise SearchRunAuthorityError("search_run_seal_pending")
            if run_id.value in self._pending_partition_transfer_by_run:
                raise SearchRunAuthorityError(
                    "search_run_partition_transfer_pending"
                )
            sealed = self._sealed.get(run_id.value)
            if sealed is not None:
                owned = tuple(
                    partition
                    for partition in sealed.partitions
                    if partition._owner is owner
                )
                if not owned:
                    raise SearchRunAuthorityError("search_run_release_missing")
                remaining = tuple(
                    partition
                    for partition in sealed.partitions
                    if partition._owner is not owner
                )
                for partition in owned:
                    self._issued_partitions.pop(partition.partition_id, None)
                if remaining:
                    self._sealed[run_id.value] = _SealedSearchRunEntry(
                        canonical_authenticator=sealed.canonical_authenticator,
                        partitions=remaining,
                    )
                else:
                    self._sealed.pop(run_id.value)
                return
            prior = self._active.get(run_id.value)
            if prior is None or not any(
                retained_owner is owner for retained_owner in prior.owners
            ):
                raise SearchRunAuthorityError("search_run_release_missing")
            remaining = tuple(
                retained_owner
                for retained_owner in prior.owners
                if retained_owner is not owner
            )
            if remaining:
                self._active[run_id.value] = _SearchRunAuthorityEntry(
                    canonical_bytes=prior.canonical_bytes,
                    owners=remaining,
                )
            else:
                self._active.pop(run_id.value)

    def allocate_closure_receipt_id(self, *, owner: object) -> str:
        """Allocate a non-linkable process-local closure replay handle."""

        with self._lock:
            self._require_owner(owner)
            receipt_id = (
                f"{self._RECEIPT_PREFIX}{self._next_receipt_ordinal:012d}"
            )
            self._next_receipt_ordinal += 1
            return receipt_id

    def retire_runs(
        self,
        run_bindings: (
            tuple[RunId, ...] | tuple[tuple[RunId, bytes, bool], ...]
        ),
        *,
        owner: object,
        receipt_id: str,
    ) -> None:
        """Atomically erase exact bytes and reserve opaque RunIds until receipt purge."""

        if type(run_bindings) is not tuple or not run_bindings:
            raise SearchRunAuthorityError("search_run_retire_ids")
        if all(type(binding) is RunId for binding in run_bindings):
            normalized_bindings = tuple(
                (binding, b"", False) for binding in run_bindings
            )
        elif all(
            type(binding) is tuple
            and len(binding) == 3
            and type(binding[0]) is RunId
            and type(binding[1]) is bytes
            and len(binding[1]) == 32
            and type(binding[2]) is bool
            for binding in run_bindings
        ):
            normalized_bindings = run_bindings
        else:
            raise SearchRunAuthorityError("search_run_retire_ids")
        run_keys = tuple(binding[0].value for binding in normalized_bindings)
        if run_keys != tuple(sorted(set(run_keys))):
            raise SearchRunAuthorityError("search_run_retire_ids")
        if (
            type(receipt_id) is not str
            or not receipt_id.startswith(self._RECEIPT_PREFIX)
            or not receipt_id[len(self._RECEIPT_PREFIX) :].isdigit()
        ):
            raise SearchRunAuthorityError("search_run_retire_receipt")
        with self._lock:
            self._require_owner(owner)
            for run_key in run_keys:
                prior = self._active.get(run_key)
                if prior is None or not any(
                    retained_owner is owner for retained_owner in prior.owners
                ):
                    raise SearchRunAuthorityError("search_run_retire_missing")
                if len(prior.owners) != 1:
                    raise SearchRunAuthorityError("search_run_retire_shared")
            staged_active = dict(self._active)
            staged_retired = dict(self._retired)
            for run_key, (_, authenticator, terminal_replay) in zip(
                run_keys,
                normalized_bindings,
                strict=True,
            ):
                staged_active.pop(run_key)
                staged_retired[run_key] = _RetiredSearchRunEntry(
                    receipt_id=receipt_id,
                    canonical_authenticator=authenticator,
                    terminal_replay=terminal_replay,
                    owner=owner,
                )
            self._active = staged_active
            self._retired = staged_retired

    def purge_retired(self, *, receipt_id: str, owner: object) -> int:
        """Forget opaque RunId reservations with their minimized closure receipt."""

        with self._lock:
            self._require_owner(owner)
            purge_keys = tuple(
                run_key
                for run_key, entry in self._retired.items()
                if entry.receipt_id == receipt_id and entry.owner is owner
            )
            for run_key in purge_keys:
                self._retired.pop(run_key)
            return len(purge_keys)

    @property
    def retained_canonical_material(self) -> tuple[bytes, ...]:
        with self._lock:
            retained = [
                self._active[key].canonical_bytes for key in sorted(self._active)
            ]
            retained.extend(
                self._pending_seals[seal_handle].prior.canonical_bytes
                for seal_handle in self._pending_seals
            )
            return tuple(retained)

    @property
    def sealed_run_ids(self) -> tuple[RunId, ...]:
        with self._lock:
            return tuple(RunId(key) for key in sorted(self._sealed))

    @property
    def retired_run_ids(self) -> tuple[RunId, ...]:
        with self._lock:
            return tuple(RunId(key) for key in sorted(self._retired))


def _next_eligible_check(
    *,
    run: OrderSearchRun,
    interaction: InteractionRecord,
    target_state: WorkflowState,
) -> CanonicalTimestamp | None:
    if target_state is WorkflowState.REVIEW_WINDOW_CLOSED_NO_ORDER:
        return None
    next_date = business_local_date(run.started_at) + timedelta(days=1)
    next_midnight = datetime.combine(
        next_date,
        time.min,
        tzinfo=BUSINESS_TIME_ZONE,
    )
    return CanonicalTimestamp(next_midnight.isoformat(timespec="seconds"))


def _no_order_target(
    run: OrderSearchRun,
) -> tuple[WorkflowState, tuple[SalesCreditReason, ...]]:
    if run.trigger is SearchTriggerType.REPLACEMENT_CHECK:
        raise NoOrderLedgerError("replacement_check_not_no_order_root")
    result = run.result
    if (
        result.order_ids
        or not result.enumeration_complete
        or result.identifiers_required <= 0
        or result.identifiers_attempted != result.identifiers_required
        or result.identifiers_completed != result.identifiers_required
    ):
        raise NoOrderLedgerError("no_order_result_not_complete_empty")
    if result.outcome is DiscoveryOutcome.CHECKED_NO_ORDER_WINDOW_ACTIVE:
        return (
            WorkflowState.CHECKED_NO_ORDER_WINDOW_ACTIVE,
            (SalesCreditReason.NO_ORDER_WINDOW_ACTIVE,),
        )
    if result.outcome is DiscoveryOutcome.REVIEW_WINDOW_CLOSED_NO_ORDER:
        return (
            WorkflowState.REVIEW_WINDOW_CLOSED_NO_ORDER,
            (SalesCreditReason.NO_ORDER_WINDOW_CLOSED,),
        )
    raise NoOrderLedgerError("no_order_result_not_applicable")


def _updated_no_order_interactions(
    *,
    run: OrderSearchRun,
    target_state: WorkflowState,
) -> tuple[InteractionRecord, ...]:
    return tuple(
        replace(
            interaction,
            workflow_state=target_state,
            last_check_at=run.started_at,
            next_eligible_check_at=_next_eligible_check(
                run=run,
                interaction=interaction,
                target_state=target_state,
            ),
        )
        for interaction in run.interactions
    )


def _no_order_transition_allowed(
    *,
    prior_states: tuple[WorkflowState, ...],
    target_state: WorkflowState,
    trigger: SearchTriggerType,
) -> bool:
    if not prior_states or len(set(prior_states)) != 1:
        return False
    prior_state = prior_states[0]
    if target_state is WorkflowState.CHECKED_NO_ORDER_WINDOW_ACTIVE:
        if prior_state is WorkflowState.AWAITING_SOURCE_REVIEW:
            return trigger is SearchTriggerType.NORMAL
        if prior_state is WorkflowState.CHECKED_NO_ORDER_WINDOW_ACTIVE:
            return trigger in {
                SearchTriggerType.AUTOMATIC_RECHECK,
                SearchTriggerType.FORCE_RECHECK,
            }
        return False
    return (
        target_state is WorkflowState.REVIEW_WINDOW_CLOSED_NO_ORDER
        and (
            (
                prior_state is WorkflowState.AWAITING_SOURCE_REVIEW
                and trigger is SearchTriggerType.NORMAL
            )
            or (
                prior_state is WorkflowState.CHECKED_NO_ORDER_WINDOW_ACTIVE
                and trigger
                in {
                    SearchTriggerType.AUTOMATIC_RECHECK,
                    SearchTriggerType.FORCE_RECHECK,
                }
            )
        )
    )


class NoOrderStateResult:
    """Marker for the active-transition or minimized-terminal ledger result."""

    __slots__ = ()


def _no_order_transition_authority_bytes(
    *,
    run: OrderSearchRun,
    prior_workflow_states: tuple[WorkflowState, ...],
    interactions: tuple[InteractionRecord, ...],
    workflow_state: WorkflowState,
    reasons: tuple[SalesCreditReason, ...],
    transitioned_at: CanonicalTimestamp,
    schema_version: str,
) -> bytes:
    value: dict[str, object] = {
        "interactions": [
            _interaction_token_value(interaction) for interaction in interactions
        ],
        "prior_workflow_states": [
            state.value for state in prior_workflow_states
        ],
        "reasons": [reason.value for reason in reasons],
        "run": _order_search_run_token(run).decode("utf-8"),
        "schema_version": schema_version,
        "transitioned_at": transitioned_at.value,
        "workflow_state": workflow_state.value,
    }
    return canonical_json_bytes(value, expected_members=set(value))


@dataclass(frozen=True, slots=True, repr=False, kw_only=True)
class _NoOrderTransitionAuthority:
    """Contact-bearing authority used only inside one ledger commit."""

    run: OrderSearchRun = field(repr=False)
    prior_workflow_states: tuple[WorkflowState, ...]
    interactions: tuple[InteractionRecord, ...] = field(repr=False)
    workflow_state: WorkflowState
    reasons: tuple[SalesCreditReason, ...]
    transitioned_at: CanonicalTimestamp
    _committing_ledger: object = field(repr=False, compare=False)
    _commit_capability: object = field(repr=False, compare=False)
    replayed: bool = False
    schema_version: str = "sales-credit-no-order-transition/v1"

    def __post_init__(self) -> None:
        if type(self._committing_ledger) is not InMemoryNoOrderStateLedger:
            raise NoOrderLedgerError("transition_not_ledger_authorized")
        self._committing_ledger._validate_transition_capability(self)
        if type(self.run) is not OrderSearchRun:
            raise NoOrderLedgerError("transition_run_type")
        if type(self.prior_workflow_states) is not tuple or any(
            type(state) is not WorkflowState for state in self.prior_workflow_states
        ):
            raise NoOrderLedgerError("transition_prior_states")
        if self.prior_workflow_states != tuple(
            interaction.workflow_state for interaction in self.run.interactions
        ):
            raise NoOrderLedgerError("transition_prior_states")
        target_state, reasons = _no_order_target(self.run)
        if not _no_order_transition_allowed(
            prior_states=self.prior_workflow_states,
            target_state=target_state,
            trigger=self.run.trigger,
        ):
            raise NoOrderLedgerError("transition_not_allowed")
        if self.workflow_state is not target_state or self.reasons != reasons:
            raise NoOrderLedgerError("transition_result_parity")
        if type(self.interactions) is not tuple or any(
            type(interaction) is not InteractionRecord
            for interaction in self.interactions
        ):
            raise NoOrderLedgerError("transition_interactions")
        if self.interactions != _updated_no_order_interactions(
            run=self.run,
            target_state=target_state,
        ):
            raise NoOrderLedgerError("transition_interactions")
        if self.transitioned_at != self.run.completed_at:
            raise NoOrderLedgerError("transition_timestamp")
        if type(self.replayed) is not bool:
            raise NoOrderLedgerError("transition_replayed")
        if self.schema_version != "sales-credit-no-order-transition/v1":
            raise NoOrderLedgerError("transition_schema")

    def __repr__(self) -> str:
        return "_NoOrderTransitionAuthority(<redacted>)"

    def _consume_terminal_projection_authority(self) -> None:
        if type(self._committing_ledger) is not InMemoryNoOrderStateLedger:
            raise NoOrderLedgerError("transition_not_ledger_authorized")
        self._committing_ledger._consume_terminal_transition_capability(self)


@dataclass(frozen=True, slots=True, repr=False, kw_only=True)
class NoOrderTransitionResult(NoOrderStateResult):
    """Identity-free logical result for one accepted active no-order command."""

    workflow_state: WorkflowState
    reasons: tuple[SalesCreditReason, ...]
    transitioned_at: CanonicalTimestamp
    search_trigger: SearchTriggerType
    interaction_count: int
    identifiers_required: int
    identifiers_attempted: int
    identifiers_completed: int
    enumeration_complete: bool
    replayed: bool = False
    schema_version: str = "sales-credit-no-order-transition-result/v1"

    def __post_init__(self) -> None:
        if self.workflow_state is not WorkflowState.CHECKED_NO_ORDER_WINDOW_ACTIVE:
            raise NoOrderLedgerError("transition_result_workflow")
        if self.reasons != (SalesCreditReason.NO_ORDER_WINDOW_ACTIVE,):
            raise NoOrderLedgerError("transition_result_reasons")
        if type(self.transitioned_at) is not CanonicalTimestamp:
            raise NoOrderLedgerError("transition_result_timestamp")
        if type(self.search_trigger) is not SearchTriggerType:
            raise NoOrderLedgerError("transition_result_trigger")
        for value in (
            self.interaction_count,
            self.identifiers_required,
            self.identifiers_attempted,
            self.identifiers_completed,
        ):
            if type(value) is not int or value <= 0:
                raise NoOrderLedgerError("transition_result_counts")
        if not (
            self.identifiers_required
            == self.identifiers_attempted
            == self.identifiers_completed
        ):
            raise NoOrderLedgerError("transition_result_counts")
        if type(self.enumeration_complete) is not bool or not self.enumeration_complete:
            raise NoOrderLedgerError("transition_result_enumeration")
        if type(self.replayed) is not bool:
            raise NoOrderLedgerError("transition_result_replayed")
        if self.schema_version != "sales-credit-no-order-transition-result/v1":
            raise NoOrderLedgerError("transition_result_schema")

    def __repr__(self) -> str:
        return "NoOrderTransitionResult(<minimized>)"


@dataclass(frozen=True, slots=True, repr=False, kw_only=True)
class ManualDiscoveryTransitionResult(NoOrderStateResult):
    """Identity-free result for an incomplete, uncertain, or identifierless root."""

    reasons: tuple[SalesCreditReason, ...]
    transitioned_at: CanonicalTimestamp
    interaction_count: int
    identifiers_required: int
    identifiers_attempted: int
    identifiers_completed: int
    replayed: bool = False
    schema_version: str = "sales-credit-manual-discovery-transition-result/v1"
    workflow_state: WorkflowState = field(
        default=WorkflowState.MANUAL_REVIEW_REQUIRED,
        init=False,
    )

    def __post_init__(self) -> None:
        permitted = {
            (SalesCreditReason.NO_USABLE_SEARCH_IDENTIFIER,),
            (SalesCreditReason.IDENTIFIER_SEARCH_INCOMPLETE,),
            (
                SalesCreditReason.AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW,
                SalesCreditReason.ORDER_TIMING_UNCERTAIN,
            ),
            (SalesCreditReason.AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW,),
        }
        if self.reasons not in permitted:
            raise NoOrderLedgerError("manual_transition_result_reasons")
        if type(self.transitioned_at) is not CanonicalTimestamp:
            raise NoOrderLedgerError("manual_transition_result_timestamp")
        if type(self.interaction_count) is not int or self.interaction_count <= 0:
            raise NoOrderLedgerError("manual_transition_result_counts")
        counts = (
            self.identifiers_required,
            self.identifiers_attempted,
            self.identifiers_completed,
        )
        if any(type(value) is not int or value < 0 for value in counts):
            raise NoOrderLedgerError("manual_transition_result_counts")
        if not (
            self.identifiers_completed
            <= self.identifiers_attempted
            <= self.identifiers_required
        ):
            raise NoOrderLedgerError("manual_transition_result_counts")
        identifierless = self.reasons == (
            SalesCreditReason.NO_USABLE_SEARCH_IDENTIFIER,
        )
        incomplete = self.reasons == (
            SalesCreditReason.IDENTIFIER_SEARCH_INCOMPLETE,
        )
        if identifierless != (counts == (0, 0, 0)):
            raise NoOrderLedgerError("manual_transition_result_counts")
        if incomplete and not (
            self.identifiers_required > 0
            and self.identifiers_completed < self.identifiers_required
        ):
            raise NoOrderLedgerError("manual_transition_result_counts")
        if type(self.replayed) is not bool:
            raise NoOrderLedgerError("manual_transition_result_replayed")
        if self.schema_version != "sales-credit-manual-discovery-transition-result/v1":
            raise NoOrderLedgerError("manual_transition_result_schema")

    def __repr__(self) -> str:
        return "ManualDiscoveryTransitionResult(<minimized>)"


@dataclass(frozen=True, slots=True, repr=False, kw_only=True)
class SelectorOwnedCandidateEvaluation:
    """One evaluator output produced for exactly one native interaction owner."""

    interaction_id: InteractionId
    snapshot: OrderSnapshot = field(repr=False)
    evaluation: SalesCreditEvaluation = field(repr=False)
    evaluated_at: CanonicalTimestamp

    def __post_init__(self) -> None:
        if type(self.interaction_id) is not InteractionId:
            raise NoOrderLedgerError("candidate_evaluation_interaction")
        if type(self.snapshot) is not OrderSnapshot:
            raise NoOrderLedgerError("candidate_evaluation_snapshot")
        if type(self.evaluation) is not SalesCreditEvaluation:
            raise NoOrderLedgerError("candidate_evaluation_result")
        if type(self.evaluated_at) is not CanonicalTimestamp:
            raise NoOrderLedgerError("candidate_evaluation_timestamp")
        if (
            self.snapshot.order_id is None
            or self.evaluation.order_id != self.snapshot.order_id
            or self.evaluation.snapshot_id != self.snapshot.snapshot_id
        ):
            raise NoOrderLedgerError("candidate_evaluation_identity")

    def __repr__(self) -> str:
        return "SelectorOwnedCandidateEvaluation(<redacted>)"


def _require_sorted_interaction_ids(
    values: tuple[InteractionId, ...],
    *,
    code: str,
) -> None:
    if type(values) is not tuple or any(type(value) is not InteractionId for value in values):
        raise NoOrderLedgerError(code)
    identities = tuple(value.value for value in values)
    if identities != tuple(sorted(set(identities))):
        raise NoOrderLedgerError(code)


@dataclass(frozen=True, slots=True, repr=False, kw_only=True)
class CandidateInteractionScope:
    """Exact selector-owned per-order scope exposed to the batch coordinator."""

    order_id: OrderId
    positive_interaction_ids: tuple[InteractionId, ...]
    preserved_interaction_ids: tuple[InteractionId, ...]
    nonqualifying_interaction_ids: tuple[InteractionId, ...]

    def __post_init__(self) -> None:
        if type(self.order_id) is not OrderId:
            raise NoOrderLedgerError("candidate_scope_order")
        for values in (
            self.positive_interaction_ids,
            self.preserved_interaction_ids,
            self.nonqualifying_interaction_ids,
        ):
            _require_sorted_interaction_ids(values, code="candidate_scope_interactions")
        combined = (
            *self.positive_interaction_ids,
            *self.preserved_interaction_ids,
            *self.nonqualifying_interaction_ids,
        )
        if not combined or len({value.value for value in combined}) != len(combined):
            raise NoOrderLedgerError("candidate_scope_partition")

    def __repr__(self) -> str:
        return "CandidateInteractionScope(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False, kw_only=True)
class PostEvaluationInteractionResult:
    """Per-interaction derived disposition available only during orchestration."""

    interaction_id: InteractionId
    disposition: InteractionSearchDisposition
    workflow_state: WorkflowState | None
    reasons: tuple[SalesCreditReason, ...]
    identifiers_required: int
    identifiers_completed: int
    candidates_owned: int

    def __post_init__(self) -> None:
        if type(self.interaction_id) is not InteractionId:
            raise NoOrderLedgerError("post_evaluation_interaction")
        if type(self.disposition) is not InteractionSearchDisposition:
            raise NoOrderLedgerError("post_evaluation_disposition")
        if self.workflow_state is not None and type(self.workflow_state) is not WorkflowState:
            raise NoOrderLedgerError("post_evaluation_workflow")
        if type(self.reasons) is not tuple or any(
            type(reason) is not SalesCreditReason for reason in self.reasons
        ):
            raise NoOrderLedgerError("post_evaluation_reasons")
        if self.reasons != tuple(sorted(set(self.reasons), key=lambda item: item.value)):
            raise NoOrderLedgerError("post_evaluation_reasons")
        for value in (
            self.identifiers_required,
            self.identifiers_completed,
            self.candidates_owned,
        ):
            if type(value) is not int or value < 0:
                raise NoOrderLedgerError("post_evaluation_counts")
        if self.identifiers_completed > self.identifiers_required:
            raise NoOrderLedgerError("post_evaluation_counts")

    def __repr__(self) -> str:
        return "PostEvaluationInteractionResult(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False, kw_only=True)
class PositiveNoOrderRootBinding:
    """Transient interaction-to-order ownership for one positive transfer root."""

    interaction_id: InteractionId
    target_order_ids: tuple[OrderId, ...]

    def __post_init__(self) -> None:
        if type(self.interaction_id) is not InteractionId:
            raise NoOrderLedgerError("positive_transfer_interaction")
        if type(self.target_order_ids) is not tuple or not self.target_order_ids or any(
            type(order_id) is not OrderId for order_id in self.target_order_ids
        ):
            raise NoOrderLedgerError("positive_transfer_orders")
        order_values = tuple(order_id.value for order_id in self.target_order_ids)
        if order_values != tuple(sorted(set(order_values))):
            raise NoOrderLedgerError("positive_transfer_orders")

    def __repr__(self) -> str:
        return "PositiveNoOrderRootBinding(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False, kw_only=True)
class PositiveNoOrderTransfer:
    """Transient split of negative roots into distinct case-owned partitions."""

    source_run_id: RunId
    outgoing_partition: SearchRunOwnerPartition
    roots: tuple[PositiveNoOrderRootBinding, ...]
    retain_outgoing: bool
    transitioned_at: CanonicalTimestamp

    def __post_init__(self) -> None:
        if type(self.source_run_id) is not RunId:
            raise NoOrderLedgerError("positive_transfer_run")
        if type(self.outgoing_partition) is not SearchRunOwnerPartition:
            raise NoOrderLedgerError("positive_transfer_partition")
        if type(self.roots) is not tuple or not self.roots or any(
            type(root) is not PositiveNoOrderRootBinding for root in self.roots
        ):
            raise NoOrderLedgerError("positive_transfer_roots")
        root_values = tuple(root.interaction_id.value for root in self.roots)
        if root_values != tuple(sorted(set(root_values))):
            raise NoOrderLedgerError("positive_transfer_roots")
        if type(self.retain_outgoing) is not bool:
            raise NoOrderLedgerError("positive_transfer_retain")
        if type(self.transitioned_at) is not CanonicalTimestamp:
            raise NoOrderLedgerError("positive_transfer_timestamp")

    def __repr__(self) -> str:
        return "PositiveNoOrderTransfer(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False, kw_only=True)
class PostEvaluationNoOrderStage:
    """Opaque rollback handle plus transient selector scopes for one exact run."""

    run_id: RunId
    candidate_scopes: tuple[CandidateInteractionScope, ...]
    interaction_results: tuple[PostEvaluationInteractionResult, ...]
    required_partition: SearchRunOwnerPartition | None
    positive_transfers: tuple[PositiveNoOrderTransfer, ...]
    _ledger: object = field(repr=False, compare=False)
    _token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.run_id) is not RunId:
            raise NoOrderLedgerError("post_evaluation_stage_run")
        if type(self.candidate_scopes) is not tuple or any(
            type(scope) is not CandidateInteractionScope
            for scope in self.candidate_scopes
        ):
            raise NoOrderLedgerError("post_evaluation_stage_scopes")
        order_values = tuple(scope.order_id.value for scope in self.candidate_scopes)
        if order_values != tuple(sorted(set(order_values))):
            raise NoOrderLedgerError("post_evaluation_stage_scopes")
        if type(self.interaction_results) is not tuple or any(
            type(result) is not PostEvaluationInteractionResult
            for result in self.interaction_results
        ):
            raise NoOrderLedgerError("post_evaluation_stage_interactions")
        interaction_values = tuple(
            result.interaction_id.value for result in self.interaction_results
        )
        if interaction_values != tuple(sorted(set(interaction_values))):
            raise NoOrderLedgerError("post_evaluation_stage_interactions")
        if self.required_partition is not None and type(
            self.required_partition
        ) is not SearchRunOwnerPartition:
            raise NoOrderLedgerError("post_evaluation_stage_partition")
        if type(self.positive_transfers) is not tuple or any(
            type(transfer) is not PositiveNoOrderTransfer
            for transfer in self.positive_transfers
        ):
            raise NoOrderLedgerError("post_evaluation_stage_transfers")
        transfer_runs = tuple(
            transfer.source_run_id.value for transfer in self.positive_transfers
        )
        if transfer_runs != tuple(sorted(set(transfer_runs))):
            raise NoOrderLedgerError("post_evaluation_stage_transfers")

    def __repr__(self) -> str:
        return "PostEvaluationNoOrderStage(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False, kw_only=True)
class PostEvaluationCommitResult(NoOrderStateResult):
    """Identity-free logical result of one committed post-evaluation reduction."""

    active_no_order: tuple[NoOrderTransitionResult, ...]
    manual_review: tuple[ManualDiscoveryTransitionResult, ...]
    terminal_no_order: tuple[NoOrderStateResult, ...]
    replayed: bool = False
    schema_version: str = "sales-credit-post-evaluation-result/v1"

    def __post_init__(self) -> None:
        if type(self.active_no_order) is not tuple or any(
            type(value) is not NoOrderTransitionResult
            for value in self.active_no_order
        ):
            raise NoOrderLedgerError("post_evaluation_result_active")
        if type(self.manual_review) is not tuple or any(
            type(value) is not ManualDiscoveryTransitionResult
            for value in self.manual_review
        ):
            raise NoOrderLedgerError("post_evaluation_result_manual")
        from synthetic_sales_assist.sales_credit.retention import NoOrderClosureResult

        if type(self.terminal_no_order) is not tuple or any(
            type(value) is not NoOrderClosureResult
            for value in self.terminal_no_order
        ):
            raise NoOrderLedgerError("post_evaluation_result_terminal")
        if type(self.replayed) is not bool:
            raise NoOrderLedgerError("post_evaluation_result_replayed")
        if self.schema_version != "sales-credit-post-evaluation-result/v1":
            raise NoOrderLedgerError("post_evaluation_result_schema")

    def __repr__(self) -> str:
        return "PostEvaluationCommitResult(<minimized>)"


@dataclass(frozen=True, slots=True, repr=False)
class _NoOrderReceipt:
    canonical_bytes: bytes = field(repr=False)
    interaction_ids: tuple[str, ...] = field(repr=False)
    result: NoOrderTransitionResult = field(repr=False)
    transition_capability: object = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True, repr=False)
class _RetiredNoOrderCommandReceipt:
    closure_receipt_id: str
    result: NoOrderStateResult = field(repr=False)


@dataclass(frozen=True, slots=True, repr=False)
class _ManualDiscoveryReceipt:
    canonical_bytes: bytes = field(repr=False)
    result: ManualDiscoveryTransitionResult = field(repr=False)


@dataclass(frozen=True, slots=True, repr=False)
class _PostEvaluationReceipt:
    command_authenticator: bytes = field(repr=False)
    result: PostEvaluationCommitResult = field(repr=False)
    partition: SearchRunOwnerPartition | None = field(repr=False)
    active_interaction_ids: tuple[str, ...] = field(repr=False)
    retention_receipt_ids: tuple[str, ...] = field(repr=False)


@dataclass(frozen=True, slots=True, repr=False)
class _RetainedSnapshotMaterial:
    snapshot: OrderSnapshot = field(repr=False)
    active_interaction_ids: tuple[str, ...] = field(repr=False)
    retention_receipt_ids: tuple[str, ...] = field(repr=False)


@dataclass(frozen=True, slots=True, repr=False)
class _PendingPostEvaluationStage:
    run: OrderSearchRun = field(repr=False)
    authority_claim: SearchRunAuthorityClaim | None = field(repr=False)
    command_authenticator: bytes = field(repr=False)
    candidate_scopes: tuple[CandidateInteractionScope, ...] = field(repr=False)
    interaction_results: tuple[PostEvaluationInteractionResult, ...] = field(
        repr=False
    )
    updated_interactions: tuple[InteractionRecord, ...] = field(repr=False)
    terminal_roots: tuple[tuple[InteractionRecord, int], ...] = field(repr=False)
    expected_retained: tuple[
        tuple[str, InteractionRecord | None], ...
    ] = field(repr=False)
    partition: SearchRunOwnerPartition | None = field(repr=False)
    positive_transfers: tuple[PositiveNoOrderTransfer, ...] = field(repr=False)
    retained_snapshot_pairs: tuple[tuple[str, OrderSnapshot], ...] = field(
        repr=False
    )
    expected_snapshot_material: tuple[
        tuple[str, _RetainedSnapshotMaterial | None], ...
    ] = field(repr=False)
    replay_result: PostEvaluationCommitResult | None = field(
        default=None,
        repr=False,
    )


@dataclass(frozen=True, slots=True, repr=False)
class _CommittedPostEvaluationRollback:
    prior_interactions: dict[str, InteractionRecord] = field(repr=False)
    prior_closed_receipts: dict[str, NoOrderStateResult] = field(repr=False)
    prior_post_evaluation_receipts: dict[str, _PostEvaluationReceipt] = field(
        repr=False
    )
    prior_manual_provenance: dict[str, SalesCreditReason] = field(repr=False)
    prior_snapshot_material: dict[str, _RetainedSnapshotMaterial] = field(
        repr=False
    )


def _public_no_order_transition(
    authority: _NoOrderTransitionAuthority,
) -> NoOrderTransitionResult:
    run = authority.run
    return NoOrderTransitionResult(
        workflow_state=authority.workflow_state,
        reasons=authority.reasons,
        transitioned_at=authority.transitioned_at,
        search_trigger=run.trigger,
        interaction_count=len(authority.interactions),
        identifiers_required=run.result.identifiers_required,
        identifiers_attempted=run.result.identifiers_attempted,
        identifiers_completed=run.result.identifiers_completed,
        enumeration_complete=run.result.enumeration_complete,
    )


def _owned_identifiers(
    interaction: InteractionRecord,
) -> tuple[SearchIdentifier, ...]:
    return plan_discovery(
        email_values=(() if interaction.email is None else (interaction.email,)),
        phone_values=(() if interaction.phone is None else (interaction.phone,)),
    ).identifiers


def _candidate_interaction_disposition(
    *,
    interaction: InteractionRecord,
    candidate: SelectorOwnedCandidateEvaluation,
) -> tuple[CandidateInteractionDisposition, OrderTiming | None]:
    snapshot = candidate.snapshot
    evaluation = candidate.evaluation
    if snapshot.placed_at is None or snapshot.placed_at_precision is None:
        return CandidateInteractionDisposition.PRESERVED_UNCERTAIN, None
    try:
        timing = classify_order_timing(
            interaction_at=interaction.effective_at,
            order_at=snapshot.placed_at,
            interaction_precision=interaction.effective_precision,
            order_precision=snapshot.placed_at_precision,
        )
    except WindowValidationError:
        return CandidateInteractionDisposition.PRESERVED_UNCERTAIN, None
    validations = set(evaluation.validations)
    reasons = set(evaluation.reasons)
    if timing is OrderTiming.QUALIFYING_ON_OR_AFTER_INTERACTION:
        accepted = {
            SalesCreditValidation.ORDER_ID_MATCHED,
            SalesCreditValidation.ORDER_TIMING_ACCEPTED,
            SalesCreditValidation.SNAPSHOT_ACCEPTED,
        }
        if accepted.issubset(validations) and not reasons.intersection(
            {
                SalesCreditReason.ORDER_BEFORE_INTERACTION,
                SalesCreditReason.ORDER_AFTER_REVIEW_WINDOW,
                SalesCreditReason.ORDER_TIMING_UNCERTAIN,
            }
        ):
            return CandidateInteractionDisposition.QUALIFYING, timing
        if reasons.intersection(
            {
                SalesCreditReason.ORDER_BEFORE_INTERACTION,
                SalesCreditReason.ORDER_AFTER_REVIEW_WINDOW,
                SalesCreditReason.ORDER_TIMING_UNCERTAIN,
            }
        ):
            raise NoOrderLedgerError("candidate_evaluation_timing_parity")
        return CandidateInteractionDisposition.PRESERVED_UNCERTAIN, timing
    if timing in {
        OrderTiming.BEFORE_INTERACTION,
        OrderTiming.AFTER_REVIEW_WINDOW,
    }:
        expected_reason = timing.reason
        if SalesCreditValidation.ORDER_TIMING_ACCEPTED in validations:
            raise NoOrderLedgerError("candidate_evaluation_timing_parity")
        if (
            SalesCreditValidation.SNAPSHOT_REJECTED not in validations
            and expected_reason not in reasons
        ):
            raise NoOrderLedgerError("candidate_evaluation_timing_parity")
        expected_reasons = {
            expected_reason,
            SalesCreditReason.AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW,
        }
        if (
            expected_reason is not None
            and reasons == expected_reasons
            and validations == {SalesCreditValidation.SNAPSHOT_ACCEPTED}
            and evaluation.workflow_state is WorkflowState.MANUAL_REVIEW_REQUIRED
            and evaluation.human_review_required
        ):
            return (
                CandidateInteractionDisposition.DETERMINISTICALLY_NONQUALIFYING,
                timing,
            )
    if (
        timing is OrderTiming.SAME_DAY_UNCERTAIN
        and SalesCreditValidation.ORDER_TIMING_ACCEPTED in validations
    ):
        raise NoOrderLedgerError("candidate_evaluation_timing_parity")
    return CandidateInteractionDisposition.PRESERVED_UNCERTAIN, timing


def _post_evaluation_manual_reasons(
    timings: tuple[OrderTiming | None, ...],
) -> tuple[SalesCreditReason, ...]:
    if OrderTiming.SAME_DAY_UNCERTAIN in timings:
        return (
            SalesCreditReason.AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW,
            SalesCreditReason.ORDER_TIMING_UNCERTAIN,
        )
    return (SalesCreditReason.AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW,)


def _build_interaction_closure_projection(
    *,
    run: OrderSearchRun,
    interaction: InteractionRecord,
    identifier_count: int,
) -> object:
    from synthetic_sales_assist.sales_credit.retention import (
        NoOrderClosedAuditRecord,
        NoOrderClosureProjection,
    )

    record = NoOrderClosedAuditRecord(
        opened_at=interaction.effective_at,
        closed_at=run.completed_at,
        latest_review_window_end=interaction.review_window_end,
        interaction_count=1,
        interaction_precisions=(interaction.effective_precision,),
        search_trigger=run.trigger,
        identifiers_required=identifier_count,
        identifiers_attempted=identifier_count,
        identifiers_completed=identifier_count,
        enumeration_complete=True,
        system_workflow_before_close=WorkflowState.REVIEW_WINDOW_CLOSED_NO_ORDER,
        reasons=(SalesCreditReason.NO_ORDER_WINDOW_CLOSED,),
        concise_note=ClosedNoteCode.REVIEW_WINDOW_CLOSED_NO_ORDER,
        search_adapter_version=run.adapter.version,
        search_run_schema_version=run.schema_version,
        rule_pack_version=SALES_CREDIT_RULE_PACK_VERSION,
    )
    try:
        binding = record.hash_binding()
        canonical_bytes = record.canonical_bytes()
    except (TypeError, ValueError):
        raise NoOrderLedgerError("no_order_projection_hash_binding") from None
    if binding.canonical_bytes != canonical_bytes:
        raise NoOrderLedgerError("no_order_projection_hash_binding")
    return NoOrderClosureProjection(
        record=record,
        interactions_removed=1,
        identifiers_removed=identifier_count,
        native_result_sets_removed=identifier_count,
    )


class InMemoryNoOrderStateLedger:
    """One-lock interaction-state and exact-replay authority for no-order roots."""

    def __init__(
        self,
        *,
        search_run_authority: InMemorySearchRunAuthority,
        coordinator_required: bool = False,
    ) -> None:
        if type(search_run_authority) is not InMemorySearchRunAuthority:
            raise NoOrderLedgerError("no_order_search_run_authority")
        if type(coordinator_required) is not bool:
            raise NoOrderLedgerError("no_order_coordinator_mode")
        self._lock = RLock()
        self._search_run_authority = search_run_authority
        self._search_run_owner = search_run_authority.new_owner()
        self._coordinator_required = coordinator_required
        self._closure_replay_key = secrets.token_bytes(32)
        self._post_evaluation_replay_key = secrets.token_bytes(32)
        self._interactions: dict[str, InteractionRecord] = {}
        self._receipts: dict[str, _NoOrderReceipt] = {}
        self._closed_receipts: dict[str, NoOrderStateResult] = {}
        self._retired_command_receipts: dict[
            str, _RetiredNoOrderCommandReceipt
        ] = {}
        self._manual_receipts: dict[str, _ManualDiscoveryReceipt] = {}
        self._manual_provenance: dict[str, SalesCreditReason] = {}
        self._snapshot_material: dict[str, _RetainedSnapshotMaterial] = {}
        self._post_evaluation_receipts: dict[str, _PostEvaluationReceipt] = {}
        self._pending_post_evaluation: dict[
            object, _PendingPostEvaluationStage
        ] = {}
        self._committed_post_evaluation: dict[
            object, _CommittedPostEvaluationRollback
        ] = {}
        self._transition_capabilities: dict[object, bytes] = {}
        self._pending_terminal_capability: object | None = None

    @property
    def search_run_authority(self) -> InMemorySearchRunAuthority:
        return self._search_run_authority

    def _closure_authenticator(self, canonical_bytes: bytes) -> bytes:
        return hmac.digest(
            self._closure_replay_key,
            canonical_bytes,
            "sha256",
        )

    def _post_evaluation_authenticator(self, canonical_bytes: bytes) -> bytes:
        return hmac.digest(
            self._post_evaluation_replay_key,
            canonical_bytes,
            "sha256",
        )

    @property
    def retained_snapshot_count(self) -> int:
        """Return the number of exact SnapshotId/material parity bindings retained."""

        with self._lock:
            return len(self._snapshot_material)

    @staticmethod
    def _transition_authority_bytes(
        transition: _NoOrderTransitionAuthority,
    ) -> bytes:
        return _no_order_transition_authority_bytes(
            run=transition.run,
            prior_workflow_states=transition.prior_workflow_states,
            interactions=transition.interactions,
            workflow_state=transition.workflow_state,
            reasons=transition.reasons,
            transitioned_at=transition.transitioned_at,
            schema_version=transition.schema_version,
        )

    def _validate_transition_capability(
        self,
        transition: _NoOrderTransitionAuthority,
    ) -> None:
        expected = self._transition_capabilities.get(
            transition._commit_capability
        )
        if (
            expected is None
            or expected != self._transition_authority_bytes(transition)
        ):
            raise NoOrderLedgerError("transition_not_ledger_authorized")

    def _consume_terminal_transition_capability(
        self,
        transition: _NoOrderTransitionAuthority,
    ) -> None:
        with self._lock:
            self._validate_transition_capability(transition)
            if (
                transition.workflow_state
                is not WorkflowState.REVIEW_WINDOW_CLOSED_NO_ORDER
                or self._pending_terminal_capability
                is not transition._commit_capability
            ):
                raise NoOrderLedgerError("transition_not_ledger_authorized")
            self._transition_capabilities.pop(transition._commit_capability)
            self._pending_terminal_capability = None

    def _issue_transition(
        self,
        *,
        run: OrderSearchRun,
        prior_workflow_states: tuple[WorkflowState, ...],
        interactions: tuple[InteractionRecord, ...],
        workflow_state: WorkflowState,
        reasons: tuple[SalesCreditReason, ...],
        transitioned_at: CanonicalTimestamp,
    ) -> _NoOrderTransitionAuthority:
        capability = object()
        authority_bytes = _no_order_transition_authority_bytes(
            run=run,
            prior_workflow_states=prior_workflow_states,
            interactions=interactions,
            workflow_state=workflow_state,
            reasons=reasons,
            transitioned_at=transitioned_at,
            schema_version="sales-credit-no-order-transition/v1",
        )
        self._transition_capabilities[capability] = authority_bytes
        try:
            return _NoOrderTransitionAuthority(
                run=run,
                prior_workflow_states=prior_workflow_states,
                interactions=interactions,
                workflow_state=workflow_state,
                reasons=reasons,
                transitioned_at=transitioned_at,
                _committing_ledger=self,
                _commit_capability=capability,
            )
        except (NoOrderLedgerError, TypeError, ValueError):
            self._transition_capabilities.pop(capability, None)
            raise

    @property
    def retained_interactions(self) -> tuple[InteractionRecord, ...]:
        with self._lock:
            return tuple(
                self._interactions[key] for key in sorted(self._interactions)
            )

    @property
    def receipt_count(self) -> int:
        with self._lock:
            return len(self._receipts) + len(self._closed_receipts)

    @property
    def active_receipt_count(self) -> int:
        with self._lock:
            return len(self._receipts)

    @property
    def closure_receipt_count(self) -> int:
        with self._lock:
            return len(self._closed_receipts)

    @property
    def retained_active_replay_material(self) -> tuple[bytes, ...]:
        with self._lock:
            return tuple(
                self._receipts[key].canonical_bytes
                for key in sorted(self._receipts)
            )

    def apply_manual_interaction(
        self,
        interaction: InteractionRecord,
        *,
        decided_at: CanonicalTimestamp,
    ) -> ManualDiscoveryTransitionResult:
        """Govern an identifierless root without fabricating an OrderSearchRun."""

        if type(interaction) is not InteractionRecord:
            raise NoOrderLedgerError("manual_interaction_type")
        if type(decided_at) is not CanonicalTimestamp:
            raise NoOrderLedgerError("manual_interaction_timestamp")
        if interaction.has_usable_identifier:
            raise NoOrderLedgerError("manual_interaction_has_identifier")
        if (
            decided_at.epoch_seconds,
            decided_at.nanosecond,
        ) < (
            interaction.effective_at.epoch_seconds,
            interaction.effective_at.nanosecond,
        ):
            raise NoOrderLedgerError("manual_interaction_time_order")
        document = {
            "decided_at": decided_at.value,
            "interaction": _interaction_token_value(interaction),
            "reason": SalesCreditReason.NO_USABLE_SEARCH_IDENTIFIER.value,
        }
        canonical_bytes = canonical_json_bytes(
            document,
            expected_members=set(document),
        )
        interaction_key = interaction.interaction_id.value
        with self._lock:
            receipt = self._manual_receipts.get(interaction_key)
            if receipt is not None:
                if receipt.canonical_bytes != canonical_bytes:
                    raise NoOrderLedgerError("manual_interaction_replay_conflict")
                return replace(receipt.result, replayed=True)
            retained = self._interactions.get(interaction_key)
            if retained is not None and retained != interaction:
                raise NoOrderLedgerError("manual_interaction_stale")
            if retained is None and (
                interaction.workflow_state is not WorkflowState.AWAITING_SOURCE_REVIEW
                or interaction.last_check_at is not None
                or interaction.next_eligible_check_at is not None
            ):
                raise NoOrderLedgerError("manual_interaction_initial_state")
            result = ManualDiscoveryTransitionResult(
                reasons=(SalesCreditReason.NO_USABLE_SEARCH_IDENTIFIER,),
                transitioned_at=decided_at,
                interaction_count=1,
                identifiers_required=0,
                identifiers_attempted=0,
                identifiers_completed=0,
            )
            self._interactions[interaction_key] = replace(
                interaction,
                workflow_state=WorkflowState.MANUAL_REVIEW_REQUIRED,
                next_eligible_check_at=None,
            )
            self._manual_receipts[interaction_key] = _ManualDiscoveryReceipt(
                canonical_bytes=canonical_bytes,
                result=result,
            )
            return result

    def stage_post_evaluation_run(
        self,
        run: OrderSearchRun,
        candidate_evaluations: tuple[SelectorOwnedCandidateEvaluation, ...],
        *,
        authority_claim: SearchRunAuthorityClaim | None = None,
    ) -> PostEvaluationNoOrderStage:
        """Stage independent selector-owned outcomes without mutating retained state."""

        if not self._coordinator_required:
            raise NoOrderLedgerError("no_order_coordinator_required")
        if type(run) is not OrderSearchRun:
            raise NoOrderLedgerError("post_evaluation_run_type")
        if run.trigger is SearchTriggerType.REPLACEMENT_CHECK:
            raise NoOrderLedgerError("replacement_check_not_no_order_root")
        if type(candidate_evaluations) is not tuple or any(
            type(item) is not SelectorOwnedCandidateEvaluation
            for item in candidate_evaluations
        ):
            raise NoOrderLedgerError("candidate_evaluations_shape")
        if authority_claim is None:
            try:
                self._search_run_authority.verify_sealed(run)
            except SearchRunAuthorityError as error:
                if error.code == "search_run_material_conflict":
                    raise NoOrderLedgerError(
                        "post_evaluation_replay_conflict"
                    ) from None
                raise NoOrderLedgerError(
                    "post_evaluation_authority_claim"
                ) from None
        elif (
            type(authority_claim) is not SearchRunAuthorityClaim
            or authority_claim._authority is not self._search_run_authority
            or authority_claim.run_id != run.run_id
            or authority_claim._canonical_bytes != _order_search_run_token(run)
        ):
            raise NoOrderLedgerError("post_evaluation_authority_claim")
        pair_keys = tuple(
            (item.evaluation.order_id.value, item.interaction_id.value)
            for item in candidate_evaluations
        )
        if pair_keys != tuple(sorted(set(pair_keys))):
            raise NoOrderLedgerError("candidate_evaluations_order_or_duplicate")
        evaluation_ids = tuple(
            item.evaluation.evaluation_id.value for item in candidate_evaluations
        )
        if len(set(evaluation_ids)) != len(evaluation_ids):
            raise NoOrderLedgerError("candidate_evaluations_duplicate")

        interactions = {
            interaction.interaction_id: interaction
            for interaction in run.interactions
        }
        result_by_identifier = {
            result.identifier: result for result in run.native_result_sets
        }
        candidate_orders_by_interaction: dict[InteractionId, tuple[OrderId, ...]] = {}
        identifier_counts: dict[InteractionId, tuple[int, int]] = {}
        expected_pairs: set[tuple[str, str]] = set()
        for interaction in run.interactions:
            owned = _owned_identifiers(interaction)
            owned_results = tuple(result_by_identifier[item] for item in owned)
            orders = tuple(
                OrderId(value)
                for value in sorted(
                    {
                        order_id.value
                        for result in owned_results
                        for order_id in result.order_ids
                    }
                )
            )
            candidate_orders_by_interaction[interaction.interaction_id] = orders
            completed = sum(
                result.completeness is SearchCompleteness.COMPLETE
                for result in owned_results
            )
            identifier_counts[interaction.interaction_id] = (
                len(owned),
                completed,
            )
            expected_pairs.update(
                (order_id.value, interaction.interaction_id.value)
                for order_id in orders
            )
        if set(pair_keys) != expected_pairs:
            raise NoOrderLedgerError("candidate_evaluations_owner_parity")

        pair_dispositions: dict[
            tuple[str, str],
            tuple[CandidateInteractionDisposition, OrderTiming | None],
        ] = {}
        snapshots_by_order: dict[str, OrderSnapshot] = {}
        snapshots_by_id: dict[str, OrderSnapshot] = {}
        snapshot_orders: dict[str, str] = {}
        from synthetic_sales_assist.sales_credit.evaluator import (
            KNOWN_OTHER_REP_CATALOG,
            SalesCreditEvaluationError,
            evaluate_sales_credit,
        )

        for item in candidate_evaluations:
            interaction = interactions.get(item.interaction_id)
            if interaction is None:
                raise NoOrderLedgerError("candidate_evaluation_interaction")
            if item.snapshot.placed_at is not None and (
                item.snapshot.placed_at.epoch_seconds,
                item.snapshot.placed_at.nanosecond,
            ) > (
                run.completed_at.epoch_seconds,
                run.completed_at.nanosecond,
            ):
                raise NoOrderLedgerError("candidate_order_after_search")
            try:
                expected_evaluation = evaluate_sales_credit(
                    evaluation_id=item.evaluation.evaluation_id,
                    expected_order_id=item.evaluation.order_id,
                    snapshot=item.snapshot,
                    evaluated_at=item.evaluated_at,
                    known_other_reps=KNOWN_OTHER_REP_CATALOG,
                    interactions=(interaction,),
                )
            except SalesCreditEvaluationError:
                raise NoOrderLedgerError(
                    "candidate_evaluation_recompute"
                ) from None
            if item.evaluation != expected_evaluation:
                raise NoOrderLedgerError("candidate_evaluation_recompute")
            order_key = item.evaluation.order_id.value
            snapshot_key = item.snapshot.snapshot_id.value
            prior_order = snapshot_orders.setdefault(snapshot_key, order_key)
            if prior_order != order_key:
                raise NoOrderLedgerError("candidate_snapshot_owner_conflict")
            prior_snapshot = snapshots_by_order.setdefault(order_key, item.snapshot)
            if prior_snapshot != item.snapshot:
                raise NoOrderLedgerError("candidate_evaluation_snapshot_conflict")
            prior_material = snapshots_by_id.setdefault(snapshot_key, item.snapshot)
            if prior_material != item.snapshot:
                raise NoOrderLedgerError("candidate_snapshot_material_conflict")
            pair_dispositions[(order_key, item.interaction_id.value)] = (
                _candidate_interaction_disposition(
                    interaction=interaction,
                    candidate=item,
                )
            )

        scopes: list[CandidateInteractionScope] = []
        for order_id in run.result.order_ids:
            owned_ids = tuple(
                interaction.interaction_id
                for interaction in run.interactions
                if (order_id.value, interaction.interaction_id.value)
                in pair_dispositions
            )
            positive = tuple(
                interaction_id
                for interaction_id in owned_ids
                if pair_dispositions[(order_id.value, interaction_id.value)][0]
                is CandidateInteractionDisposition.QUALIFYING
            )
            preserved = tuple(
                interaction_id
                for interaction_id in owned_ids
                if pair_dispositions[(order_id.value, interaction_id.value)][0]
                is CandidateInteractionDisposition.PRESERVED_UNCERTAIN
            )
            nonqualifying = tuple(
                interaction_id
                for interaction_id in owned_ids
                if pair_dispositions[(order_id.value, interaction_id.value)][0]
                is CandidateInteractionDisposition.DETERMINISTICALLY_NONQUALIFYING
            )
            scopes.append(
                CandidateInteractionScope(
                    order_id=order_id,
                    positive_interaction_ids=positive,
                    preserved_interaction_ids=preserved,
                    nonqualifying_interaction_ids=nonqualifying,
                )
            )

        command_bytes = _post_evaluation_command_bytes(
            run=run,
            candidate_evaluations=candidate_evaluations,
        )
        command_authenticator = self._post_evaluation_authenticator(command_bytes)
        run_key = run.run_id.value
        with self._lock:
            replay_receipt = self._post_evaluation_receipts.get(run_key)
            observed_interactions = dict(self._interactions)
            observed_manual_provenance = dict(self._manual_provenance)
            expected_snapshot_material = tuple(
                (snapshot_id, self._snapshot_material.get(snapshot_id))
                for snapshot_id in sorted(snapshots_by_id)
            )
            for snapshot_id, prior_material in expected_snapshot_material:
                if (
                    prior_material is not None
                    and prior_material.snapshot != snapshots_by_id[snapshot_id]
                ):
                    raise NoOrderLedgerError(
                        "candidate_snapshot_material_conflict"
                    )
            if replay_receipt is not None and not hmac.compare_digest(
                replay_receipt.command_authenticator,
                command_authenticator,
            ):
                raise NoOrderLedgerError("post_evaluation_replay_conflict")

        interaction_results: list[PostEvaluationInteractionResult] = []
        updated_interactions: list[InteractionRecord] = []
        terminal_roots: list[tuple[InteractionRecord, int]] = []
        expected_retained: list[tuple[str, InteractionRecord | None]] = []
        run_date = business_local_date(run.started_at)
        for interaction in run.interactions:
            required, completed = identifier_counts[interaction.interaction_id]
            owned_orders = candidate_orders_by_interaction[interaction.interaction_id]
            owned_pair_results = tuple(
                pair_dispositions[(order_id.value, interaction.interaction_id.value)]
                for order_id in owned_orders
            )
            pair_kinds = tuple(item[0] for item in owned_pair_results)
            pair_timings = tuple(item[1] for item in owned_pair_results)
            if completed < required:
                disposition = InteractionSearchDisposition.MANUAL_REVIEW_REQUIRED
                target_state: WorkflowState | None = WorkflowState.MANUAL_REVIEW_REQUIRED
                reasons = (SalesCreditReason.IDENTIFIER_SEARCH_INCOMPLETE,)
            elif CandidateInteractionDisposition.PRESERVED_UNCERTAIN in pair_kinds:
                disposition = InteractionSearchDisposition.MANUAL_REVIEW_REQUIRED
                target_state = WorkflowState.MANUAL_REVIEW_REQUIRED
                reasons = _post_evaluation_manual_reasons(pair_timings)
            elif CandidateInteractionDisposition.QUALIFYING in pair_kinds:
                disposition = InteractionSearchDisposition.POSITIVE_CANDIDATE
                target_state = None
                reasons = ()
            elif run_date > interaction.review_window_end:
                disposition = InteractionSearchDisposition.NO_ORDER_WINDOW_CLOSED
                target_state = WorkflowState.REVIEW_WINDOW_CLOSED_NO_ORDER
                reasons = (SalesCreditReason.NO_ORDER_WINDOW_CLOSED,)
            else:
                disposition = InteractionSearchDisposition.NO_ORDER_WINDOW_ACTIVE
                target_state = WorkflowState.CHECKED_NO_ORDER_WINDOW_ACTIVE
                reasons = (SalesCreditReason.NO_ORDER_WINDOW_ACTIVE,)

            retained = interaction
            if replay_receipt is None:
                observed_retained = observed_interactions.get(
                    interaction.interaction_id.value
                )
                expected_retained.append(
                    (interaction.interaction_id.value, observed_retained)
                )
                if observed_retained is None:
                    if (
                        interaction.workflow_state
                        is not WorkflowState.AWAITING_SOURCE_REVIEW
                        or interaction.last_check_at is not None
                        or interaction.next_eligible_check_at is not None
                    ):
                        raise NoOrderLedgerError("post_evaluation_initial_state")
                else:
                    if observed_retained != interaction:
                        raise NoOrderLedgerError(
                            "post_evaluation_stale_interaction"
                        )
                    retained = observed_retained
                prior_state = retained.workflow_state
                trigger_allowed = (
                    prior_state is WorkflowState.AWAITING_SOURCE_REVIEW
                    and run.trigger is SearchTriggerType.NORMAL
                ) or (
                    prior_state is WorkflowState.CHECKED_NO_ORDER_WINDOW_ACTIVE
                    and run.trigger
                    in {
                        SearchTriggerType.AUTOMATIC_RECHECK,
                        SearchTriggerType.FORCE_RECHECK,
                    }
                ) or (
                    prior_state is WorkflowState.MANUAL_REVIEW_REQUIRED
                    and observed_manual_provenance.get(
                        interaction.interaction_id.value
                    )
                    is SalesCreditReason.IDENTIFIER_SEARCH_INCOMPLETE
                    and run.trigger is SearchTriggerType.NORMAL
                )
                if not trigger_allowed:
                    raise NoOrderLedgerError(
                        "post_evaluation_trigger_not_allowed"
                    )
                if target_state in {
                    WorkflowState.CHECKED_NO_ORDER_WINDOW_ACTIVE,
                    WorkflowState.REVIEW_WINDOW_CLOSED_NO_ORDER,
                }:
                    transition_allowed = _no_order_transition_allowed(
                        prior_states=(retained.workflow_state,),
                        target_state=target_state,
                        trigger=run.trigger,
                    ) or (
                        retained.workflow_state
                        is WorkflowState.MANUAL_REVIEW_REQUIRED
                        and observed_manual_provenance.get(
                            interaction.interaction_id.value
                        )
                        is SalesCreditReason.IDENTIFIER_SEARCH_INCOMPLETE
                        and run.trigger is SearchTriggerType.NORMAL
                    )
                    if not transition_allowed:
                        raise NoOrderLedgerError(
                            "post_evaluation_transition_not_allowed"
                        )
            if (
                target_state is WorkflowState.REVIEW_WINDOW_CLOSED_NO_ORDER
                and run_date <= interaction.review_window_end
            ):
                raise NoOrderLedgerError("no_order_terminal_started_before_close")
            if (
                replay_receipt is None
                and target_state is WorkflowState.MANUAL_REVIEW_REQUIRED
            ):
                updated_interactions.append(
                    replace(
                        retained,
                        workflow_state=target_state,
                        last_check_at=run.started_at,
                        next_eligible_check_at=None,
                    )
                )
            elif (
                replay_receipt is None
                and target_state is WorkflowState.CHECKED_NO_ORDER_WINDOW_ACTIVE
            ):
                updated_interactions.append(
                    replace(
                        retained,
                        workflow_state=target_state,
                        last_check_at=run.started_at,
                        next_eligible_check_at=_next_eligible_check(
                            run=run,
                            interaction=retained,
                            target_state=target_state,
                        ),
                    )
                )
            elif (
                replay_receipt is None
                and target_state is WorkflowState.REVIEW_WINDOW_CLOSED_NO_ORDER
            ):
                terminal_roots.append((retained, required))
            interaction_results.append(
                PostEvaluationInteractionResult(
                    interaction_id=interaction.interaction_id,
                    disposition=disposition,
                    workflow_state=target_state,
                    reasons=reasons,
                    identifiers_required=required,
                    identifiers_completed=completed,
                    candidates_owned=len(owned_orders),
                )
            )

        disposition_by_id = {
            result.interaction_id.value: result.disposition
            for result in interaction_results
        }
        retained_snapshot_pairs = tuple(
            sorted(
                (
                    (
                        item.interaction_id.value,
                        item.snapshot,
                    )
                    for item in candidate_evaluations
                    if disposition_by_id[item.interaction_id.value]
                    in {
                        InteractionSearchDisposition.MANUAL_REVIEW_REQUIRED,
                        InteractionSearchDisposition.NO_ORDER_WINDOW_ACTIVE,
                    }
                ),
                key=lambda pair: (pair[0], pair[1].snapshot_id.value),
            )
        )

        with self._lock:
            if any(
                pending.run.run_id == run.run_id
                for pending in self._pending_post_evaluation.values()
            ):
                raise NoOrderLedgerError("post_evaluation_stage_pending")
            receipt = self._post_evaluation_receipts.get(run_key)
            if receipt is not None:
                if not hmac.compare_digest(
                    receipt.command_authenticator,
                    command_authenticator,
                ):
                    raise NoOrderLedgerError("post_evaluation_replay_conflict")
                stage_handle = object()
                pending = _PendingPostEvaluationStage(
                    run=run,
                    authority_claim=authority_claim,
                    command_authenticator=command_authenticator,
                    candidate_scopes=tuple(scopes),
                    interaction_results=tuple(interaction_results),
                    updated_interactions=(),
                    terminal_roots=(),
                    expected_retained=(),
                    partition=None,
                    positive_transfers=(),
                    retained_snapshot_pairs=(),
                    expected_snapshot_material=(),
                    replay_result=receipt.result,
                )
                self._pending_post_evaluation[stage_handle] = pending
                return PostEvaluationNoOrderStage(
                    run_id=run.run_id,
                    candidate_scopes=pending.candidate_scopes,
                    interaction_results=pending.interaction_results,
                    required_partition=None,
                    positive_transfers=(),
                    _ledger=self,
                    _token=stage_handle,
                )
            if authority_claim is None:
                raise NoOrderLedgerError("post_evaluation_authority_claim")
            if any(
                self._interactions.get(key) != expected
                for key, expected in expected_retained
            ):
                raise NoOrderLedgerError("post_evaluation_state_changed")
            if any(
                self._snapshot_material.get(snapshot_id) != expected
                for snapshot_id, expected in expected_snapshot_material
            ):
                raise NoOrderLedgerError("post_evaluation_state_changed")
            negative_results = tuple(
                result
                for result in interaction_results
                if result.disposition
                is not InteractionSearchDisposition.POSITIVE_CANDIDATE
            )
            positive_ids = {
                result.interaction_id.value
                for result in interaction_results
                if result.disposition
                is InteractionSearchDisposition.POSITIVE_CANDIDATE
            }
            positive_orders_by_interaction: dict[str, tuple[OrderId, ...]] = {
                interaction_id: tuple(
                    scope.order_id
                    for scope in scopes
                    if any(
                        retained.value == interaction_id
                        for retained in scope.positive_interaction_ids
                    )
                )
                for interaction_id in sorted(positive_ids)
            }
            positive_transfers: list[PositiveNoOrderTransfer] = []
            for prior_run_key, prior_receipt in sorted(
                self._post_evaluation_receipts.items()
            ):
                transferred_ids = positive_ids.intersection(
                    prior_receipt.active_interaction_ids
                )
                remaining_ids = set(
                    prior_receipt.active_interaction_ids
                ).difference(transferred_ids)
                if transferred_ids:
                    if prior_receipt.partition is None:
                        raise NoOrderLedgerError(
                            "post_evaluation_partition_missing"
                        )
                    positive_transfers.append(
                        PositiveNoOrderTransfer(
                            source_run_id=RunId(prior_run_key),
                            outgoing_partition=prior_receipt.partition,
                            roots=tuple(
                                PositiveNoOrderRootBinding(
                                    interaction_id=InteractionId(interaction_id),
                                    target_order_ids=(
                                        positive_orders_by_interaction[
                                            interaction_id
                                        ]
                                    ),
                                )
                                for interaction_id in sorted(transferred_ids)
                            ),
                            retain_outgoing=bool(
                                remaining_ids
                                or prior_receipt.retention_receipt_ids
                            ),
                            transitioned_at=run.completed_at,
                        )
                    )
            partition = None
            if negative_results:
                has_active = any(
                    result.disposition
                    in {
                        InteractionSearchDisposition.MANUAL_REVIEW_REQUIRED,
                        InteractionSearchDisposition.NO_ORDER_WINDOW_ACTIVE,
                    }
                    for result in negative_results
                )
                partition = self._search_run_authority.new_partition(
                    owner=self._search_run_owner,
                    kind=(
                        SearchRunPartitionKind.NO_ORDER_ACTIVE
                        if has_active
                        else SearchRunPartitionKind.NO_ORDER_MINIMIZED
                    ),
                )
            stage_handle = object()
            pending = _PendingPostEvaluationStage(
                run=run,
                authority_claim=authority_claim,
                command_authenticator=command_authenticator,
                candidate_scopes=tuple(scopes),
                interaction_results=tuple(interaction_results),
                updated_interactions=tuple(updated_interactions),
                terminal_roots=tuple(terminal_roots),
                expected_retained=tuple(expected_retained),
                partition=partition,
                positive_transfers=tuple(positive_transfers),
                retained_snapshot_pairs=retained_snapshot_pairs,
                expected_snapshot_material=expected_snapshot_material,
            )
            self._pending_post_evaluation[stage_handle] = pending
            return PostEvaluationNoOrderStage(
                run_id=run.run_id,
                candidate_scopes=pending.candidate_scopes,
                interaction_results=pending.interaction_results,
                required_partition=partition,
                positive_transfers=pending.positive_transfers,
                _ledger=self,
                _token=stage_handle,
            )

    def commit_post_evaluation_stage(
        self,
        stage: PostEvaluationNoOrderStage,
        *,
        seal: SearchRunSeal | None,
        partition_transfers: tuple[SearchRunPartitionTransfer, ...] = (),
    ) -> PostEvaluationCommitResult:
        """Commit a staged reducer only while its shared authority seal is pending."""

        if type(stage) is not PostEvaluationNoOrderStage or stage._ledger is not self:
            raise NoOrderLedgerError("post_evaluation_stage")
        with self._lock:
            pending = self._pending_post_evaluation.get(stage._token)
            if pending is None:
                raise NoOrderLedgerError("post_evaluation_stage")
            if pending.replay_result is not None:
                if seal is not None or partition_transfers:
                    raise NoOrderLedgerError("post_evaluation_replay_seal")
                self._pending_post_evaluation.pop(stage._token)
                return replace(pending.replay_result, replayed=True)
            if pending.partition is not None:
                if seal is None or not self._search_run_authority.seal_contains(
                    seal,
                    partition=pending.partition,
                ):
                    raise NoOrderLedgerError("post_evaluation_partition_not_sealed")
            elif seal is not None and seal.run_id != pending.run.run_id:
                raise NoOrderLedgerError("post_evaluation_seal_run")
            if type(partition_transfers) is not tuple or any(
                type(transfer) is not SearchRunPartitionTransfer
                for transfer in partition_transfers
            ):
                raise NoOrderLedgerError("post_evaluation_partition_transfers")
            transfer_by_run = {
                transfer.run_id.value: transfer
                for transfer in partition_transfers
            }
            if len(transfer_by_run) != len(partition_transfers) or set(
                transfer_by_run
            ) != {
                transfer.source_run_id.value
                for transfer in pending.positive_transfers
            }:
                raise NoOrderLedgerError("post_evaluation_partition_transfers")
            for expected_transfer in pending.positive_transfers:
                actual_transfer = transfer_by_run[
                    expected_transfer.source_run_id.value
                ]
                if not self._search_run_authority.partition_transfer_matches(
                    actual_transfer,
                    run_id=expected_transfer.source_run_id,
                    outgoing_partition=expected_transfer.outgoing_partition,
                    incoming_count=len(expected_transfer.roots),
                    retain_outgoing=expected_transfer.retain_outgoing,
                ):
                    raise NoOrderLedgerError(
                        "post_evaluation_partition_transfers"
                    )
            if any(
                self._interactions.get(key) != expected
                for key, expected in pending.expected_retained
            ):
                raise NoOrderLedgerError("post_evaluation_state_changed")
            if any(
                self._snapshot_material.get(snapshot_id) != expected
                for snapshot_id, expected in pending.expected_snapshot_material
            ):
                raise NoOrderLedgerError("post_evaluation_state_changed")

            active_results: list[NoOrderTransitionResult] = []
            manual_results: list[ManualDiscoveryTransitionResult] = []
            terminal_results: list[NoOrderStateResult] = []
            terminal_receipts_by_interaction: dict[str, str] = {}
            from synthetic_sales_assist.sales_credit.retention import (
                NoOrderClosureResult,
                RetentionDecisionError,
            )

            try:
                for result in pending.interaction_results:
                    if (
                        result.disposition
                        is InteractionSearchDisposition.NO_ORDER_WINDOW_ACTIVE
                    ):
                        active_results.append(
                            NoOrderTransitionResult(
                                workflow_state=(
                                    WorkflowState.CHECKED_NO_ORDER_WINDOW_ACTIVE
                                ),
                                reasons=(SalesCreditReason.NO_ORDER_WINDOW_ACTIVE,),
                                transitioned_at=pending.run.completed_at,
                                search_trigger=pending.run.trigger,
                                interaction_count=1,
                                identifiers_required=result.identifiers_required,
                                identifiers_attempted=result.identifiers_required,
                                identifiers_completed=result.identifiers_completed,
                                enumeration_complete=True,
                            )
                        )
                    elif (
                        result.disposition
                        is InteractionSearchDisposition.MANUAL_REVIEW_REQUIRED
                    ):
                        manual_results.append(
                            ManualDiscoveryTransitionResult(
                                reasons=result.reasons,
                                transitioned_at=pending.run.completed_at,
                                interaction_count=1,
                                identifiers_required=result.identifiers_required,
                                identifiers_attempted=result.identifiers_required,
                                identifiers_completed=result.identifiers_completed,
                            )
                        )
                for interaction, identifier_count in pending.terminal_roots:
                    projection = _build_interaction_closure_projection(
                        run=pending.run,
                        interaction=interaction,
                        identifier_count=identifier_count,
                    )
                    receipt_id = (
                        self._search_run_authority.allocate_closure_receipt_id(
                            owner=self._search_run_owner
                        )
                    )
                    terminal_results.append(
                        NoOrderClosureResult(
                            receipt_id=receipt_id,
                            projection=projection,
                        )
                    )
                    terminal_receipts_by_interaction[
                        interaction.interaction_id.value
                    ] = receipt_id
                committed_result = PostEvaluationCommitResult(
                    active_no_order=tuple(active_results),
                    manual_review=tuple(manual_results),
                    terminal_no_order=tuple(terminal_results),
                )
            except (NoOrderLedgerError, RetentionDecisionError):
                raise NoOrderLedgerError("post_evaluation_result_failed") from None

            staged_interactions = dict(self._interactions)
            processed_ids = {
                result.interaction_id.value
                for result in pending.interaction_results
            }
            for interaction_id in processed_ids:
                staged_interactions.pop(interaction_id, None)
            for interaction in pending.updated_interactions:
                staged_interactions[interaction.interaction_id.value] = interaction
            staged_closed = dict(self._closed_receipts)
            for terminal_result in terminal_results:
                staged_closed[terminal_result.receipt_id] = terminal_result
            staged_manual_provenance = dict(self._manual_provenance)
            disposition_result_by_interaction = {
                result.interaction_id.value: result
                for result in pending.interaction_results
            }
            for interaction_id, interaction_result in (
                disposition_result_by_interaction.items()
            ):
                if (
                    interaction_result.disposition
                    is InteractionSearchDisposition.MANUAL_REVIEW_REQUIRED
                ):
                    staged_manual_provenance[interaction_id] = (
                        SalesCreditReason.IDENTIFIER_SEARCH_INCOMPLETE
                        if SalesCreditReason.IDENTIFIER_SEARCH_INCOMPLETE
                        in interaction_result.reasons
                        else interaction_result.reasons[0]
                    )
                else:
                    staged_manual_provenance.pop(interaction_id, None)

            staged_snapshot_material = dict(self._snapshot_material)
            for snapshot_id, snapshot_entry in tuple(
                staged_snapshot_material.items()
            ):
                remaining_active = set(snapshot_entry.active_interaction_ids)
                remaining_active.difference_update(processed_ids)
                if remaining_active or snapshot_entry.retention_receipt_ids:
                    staged_snapshot_material[snapshot_id] = replace(
                        snapshot_entry,
                        active_interaction_ids=tuple(sorted(remaining_active)),
                    )
                else:
                    staged_snapshot_material.pop(snapshot_id)
            for interaction_id, snapshot in pending.retained_snapshot_pairs:
                snapshot_id = snapshot.snapshot_id.value
                snapshot_entry = staged_snapshot_material.get(snapshot_id)
                if snapshot_entry is None:
                    snapshot_entry = _RetainedSnapshotMaterial(
                        snapshot=snapshot,
                        active_interaction_ids=(),
                        retention_receipt_ids=(),
                    )
                elif snapshot_entry.snapshot != snapshot:
                    raise NoOrderLedgerError(
                        "candidate_snapshot_material_conflict"
                    )
                active_snapshot_roots = set(
                    snapshot_entry.active_interaction_ids
                )
                terminal_snapshot_roots = set(
                    snapshot_entry.retention_receipt_ids
                )
                terminal_receipt_id = terminal_receipts_by_interaction.get(
                    interaction_id
                )
                if terminal_receipt_id is None:
                    active_snapshot_roots.add(interaction_id)
                else:
                    terminal_snapshot_roots.add(terminal_receipt_id)
                staged_snapshot_material[snapshot_id] = replace(
                    snapshot_entry,
                    active_interaction_ids=tuple(sorted(active_snapshot_roots)),
                    retention_receipt_ids=tuple(
                        sorted(terminal_snapshot_roots)
                    ),
                )
            staged_post_receipts = dict(self._post_evaluation_receipts)
            disposition_by_interaction = {
                result.interaction_id.value: result.disposition
                for result in pending.interaction_results
            }
            transfers_by_run = {
                transfer.source_run_id.value: transfer
                for transfer in pending.positive_transfers
            }
            for prior_run_key, prior_receipt in tuple(
                staged_post_receipts.items()
            ):
                remaining_active = set(prior_receipt.active_interaction_ids)
                retention_receipts = set(prior_receipt.retention_receipt_ids)
                for interaction_id in processed_ids.intersection(remaining_active):
                    terminal_receipt_id = terminal_receipts_by_interaction.get(
                        interaction_id
                    )
                    if terminal_receipt_id is not None:
                        remaining_active.remove(interaction_id)
                        retention_receipts.add(terminal_receipt_id)
                    elif (
                        disposition_by_interaction[interaction_id]
                        is InteractionSearchDisposition.POSITIVE_CANDIDATE
                    ):
                        remaining_active.remove(interaction_id)
                transfer = transfers_by_run.get(prior_run_key)
                staged_post_receipts[prior_run_key] = replace(
                    prior_receipt,
                    partition=(
                        None
                        if transfer is not None and not transfer.retain_outgoing
                        else prior_receipt.partition
                    ),
                    active_interaction_ids=tuple(sorted(remaining_active)),
                    retention_receipt_ids=tuple(sorted(retention_receipts)),
                )
            active_members = tuple(
                sorted(
                    result.interaction_id.value
                    for result in pending.interaction_results
                    if result.disposition
                    in {
                        InteractionSearchDisposition.MANUAL_REVIEW_REQUIRED,
                        InteractionSearchDisposition.NO_ORDER_WINDOW_ACTIVE,
                    }
                )
            )
            staged_post_receipts[pending.run.run_id.value] = _PostEvaluationReceipt(
                command_authenticator=pending.command_authenticator,
                result=committed_result,
                partition=pending.partition,
                active_interaction_ids=active_members,
                retention_receipt_ids=tuple(
                    sorted(terminal_receipts_by_interaction.values())
                ),
            )
            self._committed_post_evaluation[stage._token] = (
                _CommittedPostEvaluationRollback(
                    prior_interactions=self._interactions,
                    prior_closed_receipts=self._closed_receipts,
                    prior_post_evaluation_receipts=self._post_evaluation_receipts,
                    prior_manual_provenance=self._manual_provenance,
                    prior_snapshot_material=self._snapshot_material,
                )
            )
            self._interactions = staged_interactions
            self._closed_receipts = staged_closed
            self._post_evaluation_receipts = staged_post_receipts
            self._manual_provenance = staged_manual_provenance
            self._snapshot_material = staged_snapshot_material
            self._pending_post_evaluation.pop(stage._token)
            return committed_result

    def finalize_post_evaluation_stage(
        self,
        stage: PostEvaluationNoOrderStage,
    ) -> None:
        """Discard ledger rollback material after the authority seal is committed."""

        if type(stage) is not PostEvaluationNoOrderStage or stage._ledger is not self:
            raise NoOrderLedgerError("post_evaluation_stage")
        with self._lock:
            if self._committed_post_evaluation.pop(stage._token, None) is None:
                raise NoOrderLedgerError("post_evaluation_stage")

    def rollback_post_evaluation_stage(
        self,
        stage: PostEvaluationNoOrderStage,
    ) -> None:
        """Undo a pending or committed reducer stage after authority rollback."""

        if type(stage) is not PostEvaluationNoOrderStage or stage._ledger is not self:
            raise NoOrderLedgerError("post_evaluation_stage")
        with self._lock:
            pending = self._pending_post_evaluation.pop(stage._token, None)
            committed = self._committed_post_evaluation.pop(stage._token, None)
            if pending is None and committed is None:
                raise NoOrderLedgerError("post_evaluation_stage")
            if committed is not None:
                self._interactions = committed.prior_interactions
                self._closed_receipts = committed.prior_closed_receipts
                self._post_evaluation_receipts = (
                    committed.prior_post_evaluation_receipts
                )
                self._manual_provenance = committed.prior_manual_provenance
                self._snapshot_material = committed.prior_snapshot_material
            partition = (
                pending.partition if pending is not None else stage.required_partition
            )
            if partition is not None:
                try:
                    self._search_run_authority.discard_partition(
                        partition,
                        owner=self._search_run_owner,
                    )
                except SearchRunAuthorityError as error:
                    raise NoOrderLedgerError(
                        "post_evaluation_authority_rollback"
                    ) from error

    def replay_closure(self, result: NoOrderStateResult) -> NoOrderStateResult:
        """Replay only exact identity-free closure material after active deletion."""

        from synthetic_sales_assist.sales_credit.retention import NoOrderClosureResult

        if type(result) is not NoOrderClosureResult:
            raise NoOrderLedgerError("no_order_closure_replay_type")
        key = result.receipt_id
        with self._lock:
            retained = self._closed_receipts.get(key)
            if type(retained) is not NoOrderClosureResult:
                raise NoOrderLedgerError("no_order_closure_replay_missing")
            if retained.projection != result.projection:
                raise NoOrderLedgerError("no_order_closure_replay_conflict")
            return replace(retained, replayed=True)

    def purge_closed(self, *, now: CanonicalTimestamp) -> int:
        """Delete minimized closure receipts at the exact elapsed 90-day boundary."""

        from synthetic_sales_assist.sales_credit.retention import (
            NoOrderClosureResult,
            purge_eligible,
        )

        if type(now) is not CanonicalTimestamp:
            raise NoOrderLedgerError("no_order_purge_timestamp")
        with self._lock:
            purge_keys: list[str] = []
            for key, result in self._closed_receipts.items():
                if type(result) is not NoOrderClosureResult:
                    raise NoOrderLedgerError("no_order_closed_receipt_invalid")
                if purge_eligible(
                    closed_at=result.projection.record.closed_at,
                    now=now,
                ):
                    purge_keys.append(key)
            staged = dict(self._closed_receipts)
            staged_retired_commands = dict(
                self._retired_command_receipts
            )
            staged_post_evaluation = dict(self._post_evaluation_receipts)
            staged_snapshot_material = dict(self._snapshot_material)
            for key in purge_keys:
                staged.pop(key)
                staged_retired_commands = {
                    run_key: receipt
                    for run_key, receipt in staged_retired_commands.items()
                    if receipt.closure_receipt_id != key
                }
                self._search_run_authority.purge_retired(
                    receipt_id=key,
                    owner=self._search_run_owner,
                )
            purge_key_set = set(purge_keys)
            for snapshot_id, snapshot_entry in tuple(
                staged_snapshot_material.items()
            ):
                retained_snapshot_bindings = tuple(
                    receipt_id
                    for receipt_id in snapshot_entry.retention_receipt_ids
                    if receipt_id not in purge_key_set
                )
                if (
                    snapshot_entry.active_interaction_ids
                    or retained_snapshot_bindings
                ):
                    staged_snapshot_material[snapshot_id] = replace(
                        snapshot_entry,
                        retention_receipt_ids=retained_snapshot_bindings,
                    )
                else:
                    staged_snapshot_material.pop(snapshot_id)
            release_partitions: list[
                tuple[RunId, SearchRunOwnerPartition]
            ] = []
            for run_key, receipt in tuple(staged_post_evaluation.items()):
                retained_terminal = tuple(
                    result
                    for result in receipt.result.terminal_no_order
                    if result.receipt_id not in purge_key_set
                )
                retained_bindings = tuple(
                    receipt_id
                    for receipt_id in receipt.retention_receipt_ids
                    if receipt_id not in purge_key_set
                )
                retained_result = replace(
                    receipt.result,
                    terminal_no_order=retained_terminal,
                )
                roots_exhausted = (
                    not receipt.active_interaction_ids
                    and not retained_bindings
                    and not retained_terminal
                )
                if roots_exhausted and receipt.partition is not None:
                    release_partitions.append(
                        (RunId(run_key), receipt.partition)
                    )
                staged_post_evaluation[run_key] = replace(
                    receipt,
                    result=retained_result,
                    partition=(None if roots_exhausted else receipt.partition),
                    retention_receipt_ids=retained_bindings,
                )
            for run_id, partition in release_partitions:
                try:
                    self._search_run_authority.release_partition(
                        run_id,
                        partition,
                        owner=self._search_run_owner,
                    )
                except SearchRunAuthorityError as error:
                    raise NoOrderLedgerError(
                        "post_evaluation_partition_release"
                    ) from error
            for run_key, receipt in tuple(staged_post_evaluation.items()):
                if (
                    not receipt.active_interaction_ids
                    and not receipt.retention_receipt_ids
                    and not receipt.result.terminal_no_order
                    and not self._search_run_authority.is_sealed_run(
                        RunId(run_key)
                    )
                ):
                    staged_post_evaluation.pop(run_key)
            self._closed_receipts = staged
            self._retired_command_receipts = staged_retired_commands
            self._post_evaluation_receipts = staged_post_evaluation
            self._snapshot_material = staged_snapshot_material
            return len(purge_keys)

    def apply_run(self, run: OrderSearchRun) -> NoOrderStateResult:
        if self._coordinator_required:
            raise NoOrderLedgerError("no_order_coordinator_required")
        if type(run) is not OrderSearchRun:
            raise NoOrderLedgerError("no_order_run_type")
        try:
            validated_run = replace(run)
        except (TypeError, ValueError):
            raise NoOrderLedgerError("no_order_run_invalid") from None
        if validated_run != run:
            raise NoOrderLedgerError("no_order_run_derived_material")
        canonical_bytes = _order_search_run_token(validated_run)
        run_key = validated_run.run_id.value

        with self._lock:
            try:
                retired = self._search_run_authority.resolve_retired(
                    validated_run.run_id,
                    owner=self._search_run_owner,
                    canonical_authenticator=self._closure_authenticator(
                        canonical_bytes
                    ),
                )
            except SearchRunAuthorityError as error:
                if error.code == "search_run_material_conflict":
                    raise NoOrderLedgerError(
                        "no_order_run_replay_conflict"
                    ) from None
                raise NoOrderLedgerError("no_order_run_retired") from None
            if retired is not None:
                receipt_id, terminal_replay = retired
                if not terminal_replay:
                    retired_command = self._retired_command_receipts.get(
                        run_key
                    )
                    if (
                        retired_command is None
                        or retired_command.closure_receipt_id != receipt_id
                        or type(retired_command.result)
                        is not NoOrderTransitionResult
                    ):
                        raise NoOrderLedgerError(
                            "no_order_retired_receipt_invalid"
                        )
                    return replace(retired_command.result, replayed=True)
                from synthetic_sales_assist.sales_credit.retention import (
                    NoOrderClosureResult,
                )

                retained = self._closed_receipts.get(receipt_id)
                if type(retained) is not NoOrderClosureResult:
                    raise NoOrderLedgerError(
                        "no_order_closed_receipt_invalid"
                    )
                return replace(retained, replayed=True)
            prior_receipt = self._receipts.get(run_key)
            if prior_receipt is not None:
                if prior_receipt.canonical_bytes != canonical_bytes:
                    raise NoOrderLedgerError("no_order_run_replay_conflict")
                return replace(prior_receipt.result, replayed=True)

            target_state, reasons = _no_order_target(validated_run)
            terminal_projection = None
            terminal_result = None
            terminal_key: str | None = None
            run_date = business_local_date(validated_run.started_at)
            if any(
                run_date < interaction.review_window_start
                for interaction in validated_run.interactions
            ):
                raise NoOrderLedgerError("no_order_run_before_review_window")
            if (
                target_state is WorkflowState.REVIEW_WINDOW_CLOSED_NO_ORDER
                and any(
                    run_date <= interaction.review_window_end
                    for interaction in validated_run.interactions
                )
            ):
                raise NoOrderLedgerError("no_order_terminal_started_before_close")
            prior_states: list[WorkflowState] = []
            for incoming in validated_run.interactions:
                retained = self._interactions.get(incoming.interaction_id.value)
                if retained is None:
                    if (
                        incoming.workflow_state is not WorkflowState.AWAITING_SOURCE_REVIEW
                        or incoming.last_check_at is not None
                        or incoming.next_eligible_check_at is not None
                    ):
                        raise NoOrderLedgerError("no_order_initial_state")
                    retained = incoming
                elif retained != incoming:
                    raise NoOrderLedgerError("no_order_stale_interaction")
                if retained.last_check_at is not None and (
                    retained.last_check_at.epoch_seconds,
                    retained.last_check_at.nanosecond,
                ) > (
                    validated_run.started_at.epoch_seconds,
                    validated_run.started_at.nanosecond,
                ):
                    raise NoOrderLedgerError("no_order_time_regression")
                prior_states.append(retained.workflow_state)

            if not _no_order_transition_allowed(
                prior_states=tuple(prior_states),
                target_state=target_state,
                trigger=validated_run.trigger,
            ):
                raise NoOrderLedgerError("no_order_transition_not_allowed")

            updated_interactions = _updated_no_order_interactions(
                run=validated_run,
                target_state=target_state,
            )
            result = self._issue_transition(
                run=validated_run,
                prior_workflow_states=tuple(prior_states),
                interactions=updated_interactions,
                workflow_state=target_state,
                reasons=reasons,
                transitioned_at=validated_run.completed_at,
            )
            if target_state is WorkflowState.REVIEW_WINDOW_CLOSED_NO_ORDER:
                from synthetic_sales_assist.sales_credit.retention import (
                    NoOrderClosureResult,
                    RetentionDecisionError,
                    build_no_order_closure_projection,
                )

                self._pending_terminal_capability = result._commit_capability
                try:
                    terminal_projection = build_no_order_closure_projection(
                        transition=result
                    )
                except RetentionDecisionError:
                    self._transition_capabilities.pop(
                        result._commit_capability,
                        None,
                    )
                    self._pending_terminal_capability = None
                    raise NoOrderLedgerError(
                        "no_order_closure_projection_failed"
                    ) from None
            staged_interactions = dict(self._interactions)
            staged_receipts = dict(self._receipts)
            staged_closed_receipts = dict(self._closed_receipts)
            staged_retired_command_receipts = dict(
                self._retired_command_receipts
            )
            try:
                authority_claim = self._search_run_authority.claim(
                    validated_run,
                    owner=self._search_run_owner,
                )
            except SearchRunAuthorityError as error:
                self._transition_capabilities.pop(
                    result._commit_capability,
                    None,
                )
                self._pending_terminal_capability = None
                if error.code == "search_run_material_conflict":
                    raise NoOrderLedgerError(
                        "no_order_run_replay_conflict"
                    ) from None
                if error.code == "search_run_retired":
                    raise NoOrderLedgerError("no_order_run_retired") from None
                raise NoOrderLedgerError(
                    "no_order_search_run_authority"
                ) from None
            if target_state is WorkflowState.REVIEW_WINDOW_CLOSED_NO_ORDER:
                if terminal_projection is None:
                    self._search_run_authority.rollback(authority_claim)
                    raise NoOrderLedgerError("no_order_terminal_projection_missing")
                terminal_key = (
                    self._search_run_authority.allocate_closure_receipt_id(
                        owner=self._search_run_owner
                    )
                )
                terminal_result = NoOrderClosureResult(
                    receipt_id=terminal_key,
                    projection=terminal_projection,
                )
                terminal_ids = {
                    interaction.interaction_id.value
                    for interaction in validated_run.interactions
                }
                retired_run_bindings = [
                    (
                        validated_run.run_id,
                        self._closure_authenticator(canonical_bytes),
                        True,
                    )
                ]
                retired_run_bindings.extend(
                    (
                        RunId(key),
                        self._closure_authenticator(receipt.canonical_bytes),
                        False,
                    )
                    for key, receipt in staged_receipts.items()
                    if not terminal_ids.isdisjoint(receipt.interaction_ids)
                )
                retired_run_bindings.sort(key=lambda binding: binding[0].value)
                try:
                    self._search_run_authority.retire_runs(
                        tuple(retired_run_bindings),
                        owner=self._search_run_owner,
                        receipt_id=terminal_key,
                    )
                except SearchRunAuthorityError:
                    self._search_run_authority.rollback(authority_claim)
                    raise NoOrderLedgerError(
                        "no_order_search_run_retirement"
                    ) from None
                for interaction_id in terminal_ids:
                    staged_interactions.pop(interaction_id, None)
                for key, receipt in tuple(staged_receipts.items()):
                    if not terminal_ids.isdisjoint(receipt.interaction_ids):
                        staged_retired_command_receipts[key] = (
                            _RetiredNoOrderCommandReceipt(
                                closure_receipt_id=terminal_key,
                                result=receipt.result,
                            )
                        )
                        self._transition_capabilities.pop(
                            receipt.transition_capability,
                            None,
                        )
                staged_receipts = {
                    key: receipt
                    for key, receipt in staged_receipts.items()
                    if terminal_ids.isdisjoint(receipt.interaction_ids)
                }
                staged_closed_receipts[terminal_key] = terminal_result
                committed_result: NoOrderStateResult = terminal_result
            else:
                public_result = _public_no_order_transition(result)
                for interaction in updated_interactions:
                    staged_interactions[interaction.interaction_id.value] = interaction
                staged_receipts[run_key] = _NoOrderReceipt(
                    canonical_bytes=canonical_bytes,
                    interaction_ids=tuple(
                        interaction.interaction_id.value
                        for interaction in validated_run.interactions
                    ),
                    result=public_result,
                    transition_capability=result._commit_capability,
                )
                committed_result = public_result
            self._interactions = staged_interactions
            self._receipts = staged_receipts
            self._closed_receipts = staged_closed_receipts
            self._retired_command_receipts = (
                staged_retired_command_receipts
            )
            return committed_result


__all__ = [
    "CandidateInteractionDisposition",
    "CandidateInteractionScope",
    "DiscoveryOutcome",
    "DiscoveryPlan",
    "DiscoveryResult",
    "DiscoveryValidationError",
    "IdentifierSearchResult",
    "InMemoryNoOrderStateLedger",
    "InMemorySearchRunAuthority",
    "InteractionSearchDisposition",
    "ManualDiscoveryTransitionResult",
    "NativeSearchResultSet",
    "NoOrderLedgerError",
    "NoOrderStateResult",
    "NoOrderTransitionResult",
    "OrderSearchRun",
    "PostEvaluationCommitResult",
    "PostEvaluationInteractionResult",
    "PostEvaluationNoOrderStage",
    "PositiveNoOrderRootBinding",
    "PositiveNoOrderTransfer",
    "SearchCompleteness",
    "SearchIdentifier",
    "SearchIdentifierKind",
    "SearchRunAuthorityClaim",
    "SearchRunAuthorityError",
    "SearchRunOwnerPartition",
    "SearchRunPartitionKind",
    "SearchRunPartitionTransfer",
    "SearchRunSeal",
    "SelectorOwnedCandidateEvaluation",
    "combine_search_results",
    "normalize_fictional_phone",
    "normalize_synthetic_email",
    "plan_discovery",
]
