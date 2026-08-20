"""Closed immutable values for the pure synthetic Sales Credit rule pack."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import ClassVar
from zoneinfo import ZoneInfo

from synthetic_sales_assist.domain.canonical import (
    HashBinding,
    canonical_json_bytes,
    domain_hash,
)
from synthetic_sales_assist.domain.identities import (
    CustomerId,
    EvaluationId,
    EvidenceId,
    InteractionId,
    OrderId,
    RepId,
    RunId,
    SkuId,
    SnapshotId,
)
from synthetic_sales_assist.domain.normalization import (
    ascii_four_trim,
    normalize_es_number,
    normalize_mfg_oe_number,
)
from synthetic_sales_assist.domain.numeric import Money, Quantity
from synthetic_sales_assist.domain.records import VersionBinding
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.domain.tokens import ImmutableStrEnum
from synthetic_sales_assist.safety.identity import (
    IdentityFirewallError,
    assert_fictional_555_phone,
    assert_synthetic_email,
)
from synthetic_sales_assist.safety.content import scan_payload


SALES_CREDIT_RULE_PACK_VERSION = "synthetic-sales-credit-rules/v1"
SALES_CREDIT_SCHEMA_VERSION = "synthetic-sales-credit-domain/v1"
SALES_CREDIT_PARSER_VERSION = "sales-credit-parser/v1"
NEW_YORK = ZoneInfo("America/New_York")
_TOKEN = re.compile(r"\A[A-Z][A-Z0-9_]{0,63}\Z", re.ASCII)
_RAW_REP = re.compile(r"\A[a-z][a-z0-9_]{0,63}\Z", re.ASCII)
_SYNTHETIC_REP = re.compile(r"\Asynthetic_[a-z0-9]+(?:_[a-z0-9]+)*\Z", re.ASCII)
_BINDING_REP_LITERALS = frozenset(
    {"target_rep", "target_rep_web", "unassigned_web"}
)
_SYNTHETIC_SOURCE_PREFIX = "synthetic:"
_ACTIVE_TEXT_MAX = 256
_DEPENDENCY_INCOMPLETE_WARNINGS = frozenset(
    {"CUSTOMERS_INCOMPLETE", "LINES_INCOMPLETE"}
)


class SalesCreditValidationError(ValueError):
    """Reject Sales Credit material without retaining or echoing it."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Sales Credit value rejected: {code}")


class TimestampPrecision(ImmutableStrEnum):
    EXACT = "EXACT"
    CORRECTED = "CORRECTED"
    REVISION_DERIVED = "REVISION_DERIVED"
    HISTORICAL_APPROXIMATION = "HISTORICAL_APPROXIMATION"

    @property
    def proves_same_day_ordering(self) -> bool:
        return self in {TimestampPrecision.EXACT, TimestampPrecision.CORRECTED}


class WorkflowState(ImmutableStrEnum):
    AWAITING_SOURCE_REVIEW = "AWAITING_SOURCE_REVIEW"
    CHECKED_NO_ORDER_WINDOW_ACTIVE = "CHECKED_NO_ORDER_WINDOW_ACTIVE"
    REVIEW_WINDOW_CLOSED_NO_ORDER = "REVIEW_WINDOW_CLOSED_NO_ORDER"
    CREDIT_CONFIRMED_TARGET_REP = "CREDIT_CONFIRMED_TARGET_REP"
    EVIDENCE_NEEDED = "EVIDENCE_NEEDED"
    VERIFIED_PREORDER_EVIDENCE = "VERIFIED_PREORDER_EVIDENCE"
    OUTBOUND_EVIDENCE_HUMAN_REVIEW = "OUTBOUND_EVIDENCE_HUMAN_REVIEW"
    INBOUND_EVIDENCE_HUMAN_REVIEW = "INBOUND_EVIDENCE_HUMAN_REVIEW"
    TIMING_UNCERTAIN_HUMAN_REVIEW = "TIMING_UNCERTAIN_HUMAN_REVIEW"
    OTHER_REP_HUMAN_REVIEW = "OTHER_REP_HUMAN_REVIEW"
    ORDER_CHANGED_HUMAN_REVIEW = "ORDER_CHANGED_HUMAN_REVIEW"
    CANCELED_REPLACEMENT_WINDOW_ACTIVE = "CANCELED_REPLACEMENT_WINDOW_ACTIVE"
    POSSIBLE_REPLACEMENT_HUMAN_REVIEW = "POSSIBLE_REPLACEMENT_HUMAN_REVIEW"
    CANCELED_NO_REPLACEMENT = "CANCELED_NO_REPLACEMENT"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    CLOSED = "CLOSED"


class SearchTriggerType(ImmutableStrEnum):
    NORMAL = "NORMAL"
    AUTOMATIC_RECHECK = "AUTOMATIC_RECHECK"
    FORCE_RECHECK = "FORCE_RECHECK"
    REPLACEMENT_CHECK = "REPLACEMENT_CHECK"


class SnapshotStatus(ImmutableStrEnum):
    VALID = "VALID"
    PARTIAL = "PARTIAL"
    INVALID = "INVALID"


class NotesScanStatus(ImmutableStrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    UNAVAILABLE = "UNAVAILABLE"


class OrderLifecycleStatus(ImmutableStrEnum):
    ACTIVE = "ACTIVE"
    CANCELED = "CANCELED"
    UNKNOWN = "UNKNOWN"


class MaterialChangeKind(ImmutableStrEnum):
    PRODUCT_ADDITION = "PRODUCT_ADDITION"
    PRODUCT_REMOVAL = "PRODUCT_REMOVAL"
    QUANTITY_CHANGE = "QUANTITY_CHANGE"
    SUBSTITUTION = "SUBSTITUTION"
    PARTIAL_CANCELLATION = "PARTIAL_CANCELLATION"
    SHIPPING_CHANGE = "SHIPPING_CHANGE"
    DISCOUNT = "DISCOUNT"
    PRICE_ADJUSTMENT = "PRICE_ADJUSTMENT"
    REFUND = "REFUND"
    RETURN = "RETURN"
    ROUTINE_WAREHOUSE = "ROUTINE_WAREHOUSE"
    ROUTINE_INVENTORY = "ROUTINE_INVENTORY"
    ROUTINE_TRACKING = "ROUTINE_TRACKING"
    ROUTINE_ADMINISTRATIVE = "ROUTINE_ADMINISTRATIVE"

    @property
    def is_material(self) -> bool:
        return not self.value.startswith("ROUTINE_")


class EvidenceSourceType(ImmutableStrEnum):
    SYNTHETIC_EMAIL = "SYNTHETIC_EMAIL"
    SYNTHETIC_PHONE_CALL = "SYNTHETIC_PHONE_CALL"
    SYNTHETIC_CONVERSATION = "SYNTHETIC_CONVERSATION"
    SYNTHETIC_INTERACTION = "SYNTHETIC_INTERACTION"


class EvidenceDirection(ImmutableStrEnum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"
    TWO_WAY = "TWO_WAY"
    UNKNOWN = "UNKNOWN"


class EvidenceIdentifierKind(ImmutableStrEnum):
    EMAIL = "EMAIL"
    PHONE = "PHONE"


class EvidenceTimingRelation(ImmutableStrEnum):
    PRE_ORDER = "PRE_ORDER"
    POST_ORDER = "POST_ORDER"
    SAME_DAY_UNCERTAIN = "SAME_DAY_UNCERTAIN"
    UNKNOWN = "UNKNOWN"


class EvidenceClassification(ImmutableStrEnum):
    VERIFIED_PREORDER_EVIDENCE = "VERIFIED_PREORDER_EVIDENCE"
    INBOUND_EVIDENCE_HUMAN_REVIEW = "INBOUND_EVIDENCE_HUMAN_REVIEW"
    OUTBOUND_EVIDENCE_HUMAN_REVIEW = "OUTBOUND_EVIDENCE_HUMAN_REVIEW"
    TIMING_UNCERTAIN_HUMAN_REVIEW = "TIMING_UNCERTAIN_HUMAN_REVIEW"
    POST_ORDER_CONTACT_ONLY = "POST_ORDER_CONTACT_ONLY"
    UNKNOWN_OR_CONTRADICTORY = "UNKNOWN_OR_CONTRADICTORY"


class AttributionClassification(ImmutableStrEnum):
    TARGET_REP = "TARGET_REP"
    UNASSIGNED_WEB = "UNASSIGNED_WEB"
    OTHER_REP = "OTHER_REP"
    UNKNOWN = "UNKNOWN"


class OrderValueStatus(ImmutableStrEnum):
    PLACED_VALUE_VERIFIED = "PLACED_VALUE_VERIFIED"
    CURRENT_ONLY = "CURRENT_ONLY"
    CHANGED_REVIEW = "CHANGED_REVIEW"
    UNKNOWN = "UNKNOWN"


class CustomerContinuityStatus(ImmutableStrEnum):
    PROVED = "PROVED"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"


class ProductContinuityStatus(ImmutableStrEnum):
    EXACT_ES = "EXACT_ES"
    EXACT_MFG_OE = "EXACT_MFG_OE"
    NONEXACT = "NONEXACT"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"


class ReplacementStatus(ImmutableStrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    WINDOW_ACTIVE = "WINDOW_ACTIVE"
    WINDOW_EXPIRED = "WINDOW_EXPIRED"
    EXACT_RELEVANT = "EXACT_RELEVANT"
    POSSIBLE_REVIEW = "POSSIBLE_REVIEW"
    NOT_CONTINUATION = "NOT_CONTINUATION"
    BLOCKED = "BLOCKED"


class HumanOutcomeType(ImmutableStrEnum):
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    PARTIAL = "PARTIAL"
    OTHER_REP = "OTHER_REP"
    NOT_PURSUED = "NOT_PURSUED"


class ClosedNoteCode(ImmutableStrEnum):
    AUTOMATIC_CLASSIFICATION_CLOSED = "AUTOMATIC_CLASSIFICATION_CLOSED"
    HUMAN_OUTCOME_RECORDED = "HUMAN_OUTCOME_RECORDED"
    REVIEW_WINDOW_CLOSED_NO_ORDER = "REVIEW_WINDOW_CLOSED_NO_ORDER"
    CANCELED_NO_REPLACEMENT = "CANCELED_NO_REPLACEMENT"


class SalesCreditReason(ImmutableStrEnum):
    NO_USABLE_SEARCH_IDENTIFIER = "NO_USABLE_SEARCH_IDENTIFIER"
    IDENTIFIER_SEARCH_INCOMPLETE = "IDENTIFIER_SEARCH_INCOMPLETE"
    NO_ORDER_WINDOW_ACTIVE = "NO_ORDER_WINDOW_ACTIVE"
    NO_ORDER_WINDOW_CLOSED = "NO_ORDER_WINDOW_CLOSED"
    ORDER_BEFORE_INTERACTION = "ORDER_BEFORE_INTERACTION"
    ORDER_AFTER_REVIEW_WINDOW = "ORDER_AFTER_REVIEW_WINDOW"
    ORDER_BEFORE_CANCELLATION = "ORDER_BEFORE_CANCELLATION"
    ORDER_AFTER_REPLACEMENT_WINDOW = "ORDER_AFTER_REPLACEMENT_WINDOW"
    ORDER_TIMING_UNCERTAIN = "ORDER_TIMING_UNCERTAIN"
    AUTOMATIC_RECHECK_THROTTLED_LOCAL_DAY = (
        "AUTOMATIC_RECHECK_THROTTLED_LOCAL_DAY"
    )
    FORCE_RECHECK_ACCEPTED = "FORCE_RECHECK_ACCEPTED"
    SNAPSHOT_INVALID = "SNAPSHOT_INVALID"
    SNAPSHOT_PARTIAL_DEPENDENCY_BLOCKED = "SNAPSHOT_PARTIAL_DEPENDENCY_BLOCKED"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    UNSUPPORTED_SCHEMA_OR_SNAPSHOT = "UNSUPPORTED_SCHEMA_OR_SNAPSHOT"
    CONTRADICTORY_FACTS = "CONTRADICTORY_FACTS"
    TARGET_REP = "TARGET_REP"
    TARGET_REP_WEB = "TARGET_REP_WEB"
    UNASSIGNED_WEB = "UNASSIGNED_WEB"
    OTHER_KNOWN_REP = "OTHER_KNOWN_REP"
    REP_MISSING = "REP_MISSING"
    REP_UNRECOGNIZED = "REP_UNRECOGNIZED"
    TWO_WAY_PREORDER_INTERACTION = "TWO_WAY_PREORDER_INTERACTION"
    CONNECTED_PREORDER_CALL = "CONNECTED_PREORDER_CALL"
    INBOUND_ONLY_PREORDER_CONTACT = "INBOUND_ONLY_PREORDER_CONTACT"
    OUTBOUND_ONLY_PREORDER_CONTACT = "OUTBOUND_ONLY_PREORDER_CONTACT"
    MISSED_OR_UNANSWERED_INBOUND_CALL = "MISSED_OR_UNANSWERED_INBOUND_CALL"
    POST_ORDER_CONTACT_ONLY = "POST_ORDER_CONTACT_ONLY"
    EVIDENCE_TIMING_UNCERTAIN = "EVIDENCE_TIMING_UNCERTAIN"
    EVIDENCE_IDENTITY_UNPROVED = "EVIDENCE_IDENTITY_UNPROVED"
    NO_QUALIFYING_PREORDER_EVIDENCE = "NO_QUALIFYING_PREORDER_EVIDENCE"
    CANCELED_ORDER_ZERO_ACTIVE_VALUE = "CANCELED_ORDER_ZERO_ACTIVE_VALUE"
    REPLACEMENT_WINDOW_ACTIVE = "REPLACEMENT_WINDOW_ACTIVE"
    EXACT_ES_PRODUCT_CONTINUITY = "EXACT_ES_PRODUCT_CONTINUITY"
    EXACT_MFG_OE_PRODUCT_CONTINUITY = "EXACT_MFG_OE_PRODUCT_CONTINUITY"
    NONEXACT_PRODUCT_CONTINUITY_REQUIRES_REVIEW = (
        "NONEXACT_PRODUCT_CONTINUITY_REQUIRES_REVIEW"
    )
    CUSTOMER_CONTINUITY_UNPROVED = "CUSTOMER_CONTINUITY_UNPROVED"
    CUSTOMER_CONTINUITY_MISMATCH = "CUSTOMER_CONTINUITY_MISMATCH"
    NO_PRODUCT_CONTINUITY = "NO_PRODUCT_CONTINUITY"
    REPLACEMENT_WINDOW_EXPIRED = "REPLACEMENT_WINDOW_EXPIRED"
    PLACED_VALUE_PROVED = "PLACED_VALUE_PROVED"
    PLACED_VALUE_UNAVAILABLE = "PLACED_VALUE_UNAVAILABLE"
    MATERIAL_CHANGE_DETECTED = "MATERIAL_CHANGE_DETECTED"
    ROUTINE_LIFECYCLE_CHANGE_NONMATERIAL = "ROUTINE_LIFECYCLE_CHANGE_NONMATERIAL"
    AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW = "AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW"


class SalesCreditFact(ImmutableStrEnum):
    SNAPSHOT = "SNAPSHOT"
    ORDER_IDENTITY = "ORDER_IDENTITY"
    ORDER_TIMING = "ORDER_TIMING"
    ORDER_LIFECYCLE = "ORDER_LIFECYCLE"
    ORDER_REP = "ORDER_REP"
    ORDER_VALUE = "ORDER_VALUE"
    MATERIAL_CHANGES = "MATERIAL_CHANGES"
    REPLACEMENT_CONTINUITY = "REPLACEMENT_CONTINUITY"
    CONTACT_EVIDENCE = "CONTACT_EVIDENCE"


class SalesCreditRule(ImmutableStrEnum):
    SNAPSHOT_VALIDATION = "SNAPSHOT_VALIDATION"
    ORDER_WINDOW = "ORDER_WINDOW"
    CANCELLATION = "CANCELLATION"
    REPLACEMENT = "REPLACEMENT"
    PLACED_VALUE = "PLACED_VALUE"
    MATERIAL_CHANGE = "MATERIAL_CHANGE"
    ORDER_REP_ATTRIBUTION = "ORDER_REP_ATTRIBUTION"
    CONTACT_EVIDENCE = "CONTACT_EVIDENCE"
    AMBIGUITY_ROUTING = "AMBIGUITY_ROUTING"


class SalesCreditValidation(ImmutableStrEnum):
    SNAPSHOT_ACCEPTED = "SNAPSHOT_ACCEPTED"
    SNAPSHOT_PARTIAL = "SNAPSHOT_PARTIAL"
    SNAPSHOT_REJECTED = "SNAPSHOT_REJECTED"
    ORDER_ID_MATCHED = "ORDER_ID_MATCHED"
    ORDER_TIMING_ACCEPTED = "ORDER_TIMING_ACCEPTED"
    DEPENDENCY_BLOCKED = "DEPENDENCY_BLOCKED"


class SalesCreditEffect(ImmutableStrEnum):
    NO_PERSISTENCE_MILESTONE_2 = "NO_PERSISTENCE_MILESTONE_2"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    ZERO_ACTIVE_VALUE = "ZERO_ACTIVE_VALUE"
    ACTIVE_CASE_CLASSIFICATION = "ACTIVE_CASE_CLASSIFICATION"


def derive_evidence_classification(
    *,
    source_type: EvidenceSourceType,
    direction: EvidenceDirection,
    target_rep_participated: bool | None,
    connected: bool | None,
    two_way: bool | None,
    timing: EvidenceTimingRelation,
) -> EvidenceClassification:
    """Derive one evidence result from factual fields; callers cannot select it."""

    if type(source_type) is not EvidenceSourceType:
        raise SalesCreditValidationError("evidence_source_type")
    if type(direction) is not EvidenceDirection:
        raise SalesCreditValidationError("evidence_direction")
    if type(timing) is not EvidenceTimingRelation:
        raise SalesCreditValidationError("evidence_timing")
    for value in (target_rep_participated, connected, two_way):
        if value is not None and type(value) is not bool:
            raise SalesCreditValidationError("evidence_boolean")
    if timing is EvidenceTimingRelation.SAME_DAY_UNCERTAIN:
        return EvidenceClassification.TIMING_UNCERTAIN_HUMAN_REVIEW
    if timing is EvidenceTimingRelation.POST_ORDER:
        return EvidenceClassification.POST_ORDER_CONTACT_ONLY
    if timing is not EvidenceTimingRelation.PRE_ORDER:
        return EvidenceClassification.UNKNOWN_OR_CONTRADICTORY
    verified_two_way = direction is EvidenceDirection.TWO_WAY and two_way is True
    connected_call = (
        source_type is EvidenceSourceType.SYNTHETIC_PHONE_CALL
        and connected is True
    )
    if target_rep_participated is True and (verified_two_way or connected_call):
        return EvidenceClassification.VERIFIED_PREORDER_EVIDENCE
    if (
        direction is EvidenceDirection.INBOUND
        and target_rep_participated is False
        and connected is False
        and two_way is False
    ):
        return EvidenceClassification.INBOUND_EVIDENCE_HUMAN_REVIEW
    if (
        direction is EvidenceDirection.OUTBOUND
        and target_rep_participated is True
        and connected is False
        and two_way is False
    ):
        return EvidenceClassification.OUTBOUND_EVIDENCE_HUMAN_REVIEW
    return EvidenceClassification.UNKNOWN_OR_CONTRADICTORY


def _require_type(value: object, expected: type[object], code: str) -> None:
    if type(value) is not expected:
        raise SalesCreditValidationError(code)


def _require_optional_type(value: object, expected: type[object], code: str) -> None:
    if value is not None and type(value) is not expected:
        raise SalesCreditValidationError(code)


def _require_sorted_unique(
    values: object,
    *,
    item_type: type[object],
    key: object,
    code: str,
) -> None:
    if type(values) is not tuple or any(type(item) is not item_type for item in values):
        raise SalesCreditValidationError(code)
    key_function = key
    observed = tuple(key_function(item) for item in values)  # type: ignore[operator]
    if observed != tuple(sorted(observed)) or len(observed) != len(set(observed)):
        raise SalesCreditValidationError(code)


def _require_nonnegative_money(value: Money | None, code: str) -> None:
    if value is not None and (type(value) is not Money or value.minor_units < 0):
        raise SalesCreditValidationError(code)


def _require_active_text(value: str | None, code: str) -> None:
    if value is None:
        return
    if (
        type(value) is not str
        or not value.startswith("synthetic:")
        or not value.isascii()
        or not 10 <= len(value) <= _ACTIVE_TEXT_MAX
        or "\n" in value
        or "\r" in value
    ):
        raise SalesCreditValidationError(code)
    _require_payload_safe({"note": value}, code)


def _require_payload_safe(value: object, code: str) -> None:
    failed = bool(scan_payload(value))
    if failed:
        raise SalesCreditValidationError(code)


def _synthetic_product_payload(raw: object, *, field: str, code: str) -> str:
    if type(raw) is not str or not raw.startswith(_SYNTHETIC_SOURCE_PREFIX):
        raise SalesCreditValidationError(code)
    _require_payload_safe({field: raw}, code)
    payload = ascii_four_trim(raw[len(_SYNTHETIC_SOURCE_PREFIX) :])
    if not payload:
        raise SalesCreditValidationError(code)
    return payload


def _require_synthetic_raw_rep(value: str, code: str) -> None:
    if value in _BINDING_REP_LITERALS or _SYNTHETIC_REP.fullmatch(value) is not None:
        _require_payload_safe({"raw_rep": value}, code)
        return
    raise SalesCreditValidationError(code)


def _require_token_tuple(values: object, code: str) -> None:
    if type(values) is not tuple or any(
        type(value) is not str or _TOKEN.fullmatch(value) is None for value in values
    ):
        raise SalesCreditValidationError(code)
    if values != tuple(sorted(values)) or len(values) != len(set(values)):
        raise SalesCreditValidationError(code)


def _binding_dict(value: HashBinding) -> dict[str, str]:
    return {"domain": value.domain, "sha256": value.sha256}


def _money_dict(value: Money | None) -> dict[str, object] | None:
    return None if value is None else value.to_json_value()


def _new_york_date(value: CanonicalTimestamp) -> date:
    instant = datetime.fromtimestamp(value.epoch_seconds, tz=timezone.utc)
    return instant.astimezone(NEW_YORK).date()


@dataclass(frozen=True, slots=True, repr=False, kw_only=True)
class InteractionRecord:
    interaction_id: InteractionId
    source_ref: EvidenceId
    recorded_at: CanonicalTimestamp
    timestamp_precision: TimestampPrecision
    review_window_start: date
    review_window_end: date
    workflow_state: WorkflowState
    provenance: VersionBinding
    email: str | None = field(default=None, repr=False)
    phone: str | None = field(default=None, repr=False)
    corrected_at: CanonicalTimestamp | None = None
    corrected_precision: TimestampPrecision | None = None
    vin_like_reference: str | None = field(default=None, repr=False)
    part_request: str | None = field(default=None, repr=False)
    active_notes: str | None = field(default=None, repr=False)
    last_check_at: CanonicalTimestamp | None = None
    next_eligible_check_at: CanonicalTimestamp | None = None
    schema_version: str = SALES_CREDIT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_type(self.interaction_id, InteractionId, "interaction_id")
        _require_type(self.source_ref, EvidenceId, "interaction_source_ref")
        _require_type(self.recorded_at, CanonicalTimestamp, "interaction_recorded_at")
        _require_type(self.timestamp_precision, TimestampPrecision, "interaction_precision")
        _require_type(self.workflow_state, WorkflowState, "interaction_workflow")
        _require_type(self.provenance, VersionBinding, "interaction_provenance")
        if (
            self.provenance.component != "sales_credit_interaction_source"
            or self.provenance.version != "sales-credit-interaction-source/v1"
        ):
            raise SalesCreditValidationError("interaction_provenance")
        if self.schema_version != SALES_CREDIT_SCHEMA_VERSION:
            raise SalesCreditValidationError("interaction_schema")
        if type(self.review_window_start) is not date or type(self.review_window_end) is not date:
            raise SalesCreditValidationError("interaction_review_dates")
        basis = self.corrected_at or self.recorded_at
        if self.review_window_start != _new_york_date(basis):
            raise SalesCreditValidationError("interaction_review_start")
        if self.review_window_end != self.review_window_start + timedelta(days=14):
            raise SalesCreditValidationError("interaction_review_end")
        if (self.corrected_at is None) != (self.corrected_precision is None):
            raise SalesCreditValidationError("interaction_correction_pair")
        _require_optional_type(
            self.corrected_at,
            CanonicalTimestamp,
            "interaction_corrected_at",
        )
        _require_optional_type(
            self.corrected_precision,
            TimestampPrecision,
            "interaction_corrected_precision",
        )
        _require_optional_type(self.last_check_at, CanonicalTimestamp, "interaction_last_check")
        _require_optional_type(
            self.next_eligible_check_at,
            CanonicalTimestamp,
            "interaction_next_check",
        )
        if self.email is not None:
            email_invalid = False
            try:
                accepted_email = assert_synthetic_email(self.email)
            except IdentityFirewallError:
                email_invalid = True
                accepted_email = None
            if email_invalid:
                raise SalesCreditValidationError("interaction_email") from None
            if accepted_email != self.email.lower():
                raise SalesCreditValidationError("interaction_email")
        if self.phone is not None:
            phone_invalid = False
            try:
                assert_fictional_555_phone(self.phone)
            except IdentityFirewallError:
                phone_invalid = True
            if phone_invalid:
                raise SalesCreditValidationError("interaction_phone") from None
        for value, code in (
            (self.vin_like_reference, "interaction_vin_reference"),
            (self.part_request, "interaction_part_request"),
            (self.active_notes, "interaction_notes"),
        ):
            _require_active_text(value, code)

    @property
    def has_usable_identifier(self) -> bool:
        return self.email is not None or self.phone is not None

    @property
    def effective_at(self) -> CanonicalTimestamp:
        return self.corrected_at or self.recorded_at

    @property
    def effective_precision(self) -> TimestampPrecision:
        return self.corrected_precision or self.timestamp_precision

    def __repr__(self) -> str:
        return "InteractionRecord(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False, kw_only=True)
class LineItemSnapshot:
    line_id: EvidenceId
    sku_id: SkuId
    quantity: Quantity
    line_value: Money
    content: HashBinding
    raw_es_number: str | None = field(default=None, repr=False)
    canonical_es_number: str | None = field(default=None, repr=False)
    raw_mfg_oe_number: str | None = field(default=None, repr=False)
    canonical_mfg_oe_number: str | None = field(default=None, repr=False)
    description: str | None = field(default=None, repr=False)
    raw_line_rep: str | None = field(default=None, repr=False)
    observed_availability: str | None = None
    observed_eta: CanonicalTimestamp | None = None
    warnings: tuple[str, ...] = ()

    CONTENT_DOMAIN: ClassVar[str] = "sales-credit-line-content/v1"

    @classmethod
    def create(
        cls,
        *,
        line_id: EvidenceId,
        sku_id: SkuId,
        quantity: Quantity,
        line_value: Money,
        raw_es_number: str | None = None,
        canonical_es_number: str | None = None,
        raw_mfg_oe_number: str | None = None,
        canonical_mfg_oe_number: str | None = None,
        description: str | None = None,
        raw_line_rep: str | None = None,
        observed_availability: str | None = None,
        observed_eta: CanonicalTimestamp | None = None,
        warnings: tuple[str, ...] = (),
    ) -> LineItemSnapshot:
        document = _line_content_document(
            line_id=line_id,
            sku_id=sku_id,
            quantity=quantity,
            line_value=line_value,
            raw_es_number=raw_es_number,
            canonical_es_number=canonical_es_number,
            raw_mfg_oe_number=raw_mfg_oe_number,
            canonical_mfg_oe_number=canonical_mfg_oe_number,
            description=description,
            raw_line_rep=raw_line_rep,
            observed_availability=observed_availability,
            observed_eta=observed_eta,
            warnings=warnings,
        )
        content = domain_hash(
            cls.CONTENT_DOMAIN,
            canonical_json_bytes(document, expected_members=set(document)),
        )
        return cls(
            line_id=line_id,
            sku_id=sku_id,
            quantity=quantity,
            line_value=line_value,
            content=content,
            raw_es_number=raw_es_number,
            canonical_es_number=canonical_es_number,
            raw_mfg_oe_number=raw_mfg_oe_number,
            canonical_mfg_oe_number=canonical_mfg_oe_number,
            description=description,
            raw_line_rep=raw_line_rep,
            observed_availability=observed_availability,
            observed_eta=observed_eta,
            warnings=warnings,
        )

    def __post_init__(self) -> None:
        _require_type(self.line_id, EvidenceId, "line_id")
        _require_type(self.sku_id, SkuId, "line_sku")
        _require_type(self.quantity, Quantity, "line_quantity")
        _require_nonnegative_money(self.line_value, "line_value")
        _require_type(self.content, HashBinding, "line_content")
        if self.content.domain != self.CONTENT_DOMAIN:
            raise SalesCreditValidationError("line_content")
        for raw, canonical, normalizer, field, code in (
            (
                self.raw_es_number,
                self.canonical_es_number,
                normalize_es_number,
                "oe_number",
                "line_es_number",
            ),
            (
                self.raw_mfg_oe_number,
                self.canonical_mfg_oe_number,
                normalize_mfg_oe_number,
                "manufacturer_part_number",
                "line_mfg_oe_number",
            ),
        ):
            if (raw is None) != (canonical is None):
                raise SalesCreditValidationError(code)
            if raw is not None:
                payload = _synthetic_product_payload(raw, field=field, code=code)
                invalid = False
                try:
                    expected = normalizer(payload)
                except ValueError:
                    invalid = True
                    expected = None
                if invalid or expected != canonical:
                    raise SalesCreditValidationError(code)
        _require_active_text(self.description, "line_description")
        if self.raw_line_rep is not None and type(self.raw_line_rep) is not str:
            raise SalesCreditValidationError("line_rep")
        if self.raw_line_rep is not None:
            _require_synthetic_raw_rep(self.raw_line_rep, "line_rep")
        if self.observed_availability is not None and (
            type(self.observed_availability) is not str
            or _TOKEN.fullmatch(self.observed_availability) is None
        ):
            raise SalesCreditValidationError("line_availability")
        _require_optional_type(self.observed_eta, CanonicalTimestamp, "line_eta")
        _require_token_tuple(self.warnings, "line_warnings")
        expected_document = _line_content_document(
            line_id=self.line_id,
            sku_id=self.sku_id,
            quantity=self.quantity,
            line_value=self.line_value,
            raw_es_number=self.raw_es_number,
            canonical_es_number=self.canonical_es_number,
            raw_mfg_oe_number=self.raw_mfg_oe_number,
            canonical_mfg_oe_number=self.canonical_mfg_oe_number,
            description=self.description,
            raw_line_rep=self.raw_line_rep,
            observed_availability=self.observed_availability,
            observed_eta=self.observed_eta,
            warnings=self.warnings,
        )
        expected = domain_hash(
            self.CONTENT_DOMAIN,
            canonical_json_bytes(
                expected_document,
                expected_members=set(expected_document),
            ),
        )
        if self.content != expected:
            raise SalesCreditValidationError("line_content_mismatch")

    def __repr__(self) -> str:
        return "LineItemSnapshot(<redacted>)"


def _line_content_document(
    *,
    line_id: EvidenceId,
    sku_id: SkuId,
    quantity: Quantity,
    line_value: Money,
    raw_es_number: str | None,
    canonical_es_number: str | None,
    raw_mfg_oe_number: str | None,
    canonical_mfg_oe_number: str | None,
    description: str | None,
    raw_line_rep: str | None,
    observed_availability: str | None,
    observed_eta: CanonicalTimestamp | None,
    warnings: tuple[str, ...],
) -> dict[str, object]:
    return {
        "canonical_es_number": canonical_es_number,
        "canonical_mfg_oe_number": canonical_mfg_oe_number,
        "description": description,
        "line_id": line_id.value,
        "line_value": line_value.to_json_value(),
        "observed_availability": observed_availability,
        "observed_eta": None if observed_eta is None else observed_eta.value,
        "quantity": quantity.to_json_value(),
        "raw_es_number": raw_es_number,
        "raw_line_rep": raw_line_rep,
        "raw_mfg_oe_number": raw_mfg_oe_number,
        "sku_id": sku_id.value,
        "warnings": list(warnings),
    }


@dataclass(frozen=True, slots=True)
class MaterialChange:
    change_id: EvidenceId
    kind: MaterialChangeKind
    affects_commercial_value: bool

    def __post_init__(self) -> None:
        _require_type(self.change_id, EvidenceId, "material_change_id")
        _require_type(self.kind, MaterialChangeKind, "material_change_kind")
        if type(self.affects_commercial_value) is not bool:
            raise SalesCreditValidationError("material_change_effect")
        if self.kind.is_material != self.affects_commercial_value:
            raise SalesCreditValidationError("material_change_coherence")


@dataclass(frozen=True, slots=True, repr=False, kw_only=True)
class OrderSnapshot:
    snapshot_id: SnapshotId
    order_id: OrderId | None
    source_ref: EvidenceId | None
    captured_at: CanonicalTimestamp
    parser: VersionBinding
    extraction_status: SnapshotStatus
    lifecycle_status: OrderLifecycleStatus
    notes_scan_status: NotesScanStatus
    placed_at: CanonicalTimestamp | None
    placed_at_precision: TimestampPrecision | None
    raw_order_status: str | None
    raw_order_rep: str | None
    current_value: Money | None
    placed_value: Money | None
    customer_ids: tuple[CustomerId, ...]
    lines: tuple[LineItemSnapshot, ...]
    material_changes: tuple[MaterialChange, ...]
    provenance: HashBinding | None
    canceled_at: CanonicalTimestamp | None = None
    warnings: tuple[str, ...] = ()
    active_notes: str | None = field(default=None, repr=False)
    schema_version: str = SALES_CREDIT_SCHEMA_VERSION

    PROVENANCE_DOMAIN: ClassVar[str] = "sales-credit-order-provenance/v1"

    def __post_init__(self) -> None:
        _require_type(self.snapshot_id, SnapshotId, "snapshot_id")
        _require_optional_type(self.order_id, OrderId, "snapshot_order_id")
        _require_optional_type(self.source_ref, EvidenceId, "snapshot_source_ref")
        _require_type(self.captured_at, CanonicalTimestamp, "snapshot_captured_at")
        _require_type(self.parser, VersionBinding, "snapshot_parser")
        if (
            self.parser.component != "sales_credit_parser"
            or self.parser.version != SALES_CREDIT_PARSER_VERSION
        ):
            raise SalesCreditValidationError("snapshot_parser")
        _require_type(self.extraction_status, SnapshotStatus, "snapshot_status")
        _require_type(self.lifecycle_status, OrderLifecycleStatus, "snapshot_lifecycle")
        _require_type(self.notes_scan_status, NotesScanStatus, "snapshot_notes_scan")
        _require_optional_type(self.placed_at, CanonicalTimestamp, "snapshot_placed_at")
        _require_optional_type(
            self.placed_at_precision,
            TimestampPrecision,
            "snapshot_placed_at_precision",
        )
        if (self.placed_at is None) != (self.placed_at_precision is None):
            raise SalesCreditValidationError("snapshot_placed_time_pair")
        _require_optional_type(self.canceled_at, CanonicalTimestamp, "snapshot_canceled_at")
        if self.raw_order_status is not None and (
            type(self.raw_order_status) is not str
            or _RAW_REP.fullmatch(self.raw_order_status) is None
        ):
            raise SalesCreditValidationError("snapshot_raw_status")
        if self.raw_order_status is not None:
            _require_payload_safe(
                {"raw_order_status": self.raw_order_status},
                "snapshot_raw_status",
            )
        if self.raw_order_rep is not None and type(self.raw_order_rep) is not str:
            raise SalesCreditValidationError("snapshot_raw_rep")
        if self.raw_order_rep:
            _require_synthetic_raw_rep(self.raw_order_rep, "snapshot_raw_rep")
        _require_nonnegative_money(self.current_value, "snapshot_current_value")
        _require_nonnegative_money(self.placed_value, "snapshot_placed_value")
        _require_sorted_unique(
            self.customer_ids,
            item_type=CustomerId,
            key=lambda item: item.value,
            code="snapshot_customer_ids",
        )
        _require_sorted_unique(
            self.lines,
            item_type=LineItemSnapshot,
            key=lambda item: item.line_id.value,
            code="snapshot_lines",
        )
        _require_sorted_unique(
            self.material_changes,
            item_type=MaterialChange,
            key=lambda item: item.change_id.value,
            code="snapshot_material_changes",
        )
        if self.provenance is not None and (
            type(self.provenance) is not HashBinding
            or self.provenance.domain != self.PROVENANCE_DOMAIN
        ):
            raise SalesCreditValidationError("snapshot_provenance")
        if (self.source_ref is None) != (self.provenance is None):
            raise SalesCreditValidationError("snapshot_provenance_pair")
        if self.provenance is not None and self.source_ref is not None:
            expected = order_provenance_binding(
                source_ref=self.source_ref,
                captured_at=self.captured_at,
                parser=self.parser,
            )
            if self.provenance != expected:
                raise SalesCreditValidationError("snapshot_provenance_mismatch")
        if self.lifecycle_status is OrderLifecycleStatus.CANCELED:
            if self.canceled_at is None:
                raise SalesCreditValidationError("snapshot_cancellation_time")
        elif self.canceled_at is not None:
            raise SalesCreditValidationError("snapshot_cancellation_state")
        _require_token_tuple(self.warnings, "snapshot_warnings")
        if (
            _DEPENDENCY_INCOMPLETE_WARNINGS.intersection(self.warnings)
            and self.extraction_status is not SnapshotStatus.PARTIAL
        ):
            raise SalesCreditValidationError("snapshot_dependency_incomplete_status")
        _require_active_text(self.active_notes, "snapshot_notes")
        if self.schema_version != SALES_CREDIT_SCHEMA_VERSION:
            raise SalesCreditValidationError("snapshot_schema")
        if self.extraction_status is SnapshotStatus.VALID:
            required = (
                self.order_id,
                self.placed_at,
                self.raw_order_status,
                self.current_value,
                self.source_ref,
                self.provenance,
            )
            if any(value is None or value == "" for value in required):
                raise SalesCreditValidationError("valid_snapshot_required_field")
            if self.notes_scan_status is not NotesScanStatus.COMPLETE:
                raise SalesCreditValidationError("valid_snapshot_notes")
        if self.extraction_status is SnapshotStatus.PARTIAL:
            has_declared_dependency_gap = (
                self.notes_scan_status is not NotesScanStatus.COMPLETE
                or bool(_DEPENDENCY_INCOMPLETE_WARNINGS.intersection(self.warnings))
            )
            if not has_declared_dependency_gap:
                raise SalesCreditValidationError("partial_snapshot_dependency_gap")
            partial_core = (
                self.order_id,
                self.placed_at,
                self.placed_at_precision,
                self.raw_order_status,
                self.current_value,
                self.source_ref,
                self.provenance,
            )
            if any(value is None or value == "" for value in partial_core):
                raise SalesCreditValidationError("partial_snapshot_required_field")

    @property
    def has_material_change(self) -> bool:
        return any(change.kind.is_material for change in self.material_changes)

    def __repr__(self) -> str:
        return "OrderSnapshot(<redacted>)"


def order_provenance_binding(
    *,
    source_ref: EvidenceId,
    captured_at: CanonicalTimestamp,
    parser: VersionBinding,
) -> HashBinding:
    if type(source_ref) is not EvidenceId:
        raise SalesCreditValidationError("snapshot_source_ref")
    if type(captured_at) is not CanonicalTimestamp:
        raise SalesCreditValidationError("snapshot_captured_at")
    if type(parser) is not VersionBinding or (
        parser.component != "sales_credit_parser"
        or parser.version != SALES_CREDIT_PARSER_VERSION
    ):
        raise SalesCreditValidationError("snapshot_parser")
    document = {
        "captured_at": captured_at.value,
        "parser": parser.to_dict(),
        "source_ref": source_ref.value,
    }
    return domain_hash(
        OrderSnapshot.PROVENANCE_DOMAIN,
        canonical_json_bytes(document, expected_members=set(document)),
    )


@dataclass(frozen=True, slots=True, repr=False, kw_only=True)
class EvidenceEvent:
    evidence_id: EvidenceId
    order_id: OrderId
    interaction_id: InteractionId
    source_type: EvidenceSourceType
    source_ref: EvidenceId
    occurred_at: CanonicalTimestamp
    timestamp_precision: TimestampPrecision
    direction: EvidenceDirection
    target_rep_participated: bool | None
    connected: bool | None
    two_way: bool | None
    identifier_kind: EvidenceIdentifierKind
    matched_identifier_ref: HashBinding
    timing: EvidenceTimingRelation
    active_excerpt: str | None = field(default=None, repr=False)
    schema_version: str = SALES_CREDIT_SCHEMA_VERSION
    classification: EvidenceClassification = field(init=False)

    IDENTIFIER_REF_DOMAIN: ClassVar[str] = "sales-credit-search-identifier-ref/v1"

    def __post_init__(self) -> None:
        _require_type(self.evidence_id, EvidenceId, "evidence_id")
        _require_type(self.order_id, OrderId, "evidence_order_id")
        _require_type(self.interaction_id, InteractionId, "evidence_interaction_id")
        _require_type(self.source_type, EvidenceSourceType, "evidence_source_type")
        _require_type(self.source_ref, EvidenceId, "evidence_source_ref")
        _require_type(self.occurred_at, CanonicalTimestamp, "evidence_occurred_at")
        _require_type(self.timestamp_precision, TimestampPrecision, "evidence_precision")
        _require_type(self.direction, EvidenceDirection, "evidence_direction")
        for value, code in (
            (self.target_rep_participated, "evidence_target_rep"),
            (self.connected, "evidence_connected"),
            (self.two_way, "evidence_two_way"),
        ):
            if value is not None and type(value) is not bool:
                raise SalesCreditValidationError(code)
        _require_type(self.identifier_kind, EvidenceIdentifierKind, "evidence_identifier")
        if (
            type(self.matched_identifier_ref) is not HashBinding
            or self.matched_identifier_ref.domain != self.IDENTIFIER_REF_DOMAIN
        ):
            raise SalesCreditValidationError("evidence_identifier_ref")
        _require_type(self.timing, EvidenceTimingRelation, "evidence_timing")
        classification = derive_evidence_classification(
            source_type=self.source_type,
            direction=self.direction,
            target_rep_participated=self.target_rep_participated,
            connected=self.connected,
            two_way=self.two_way,
            timing=self.timing,
        )
        object.__setattr__(self, "classification", classification)
        _require_active_text(self.active_excerpt, "evidence_excerpt")
        if self.schema_version != SALES_CREDIT_SCHEMA_VERSION:
            raise SalesCreditValidationError("evidence_schema")

    def __repr__(self) -> str:
        return "EvidenceEvent(<redacted>)"


@dataclass(frozen=True, slots=True)
class ReplacementFacts:
    customer_continuity: CustomerContinuityStatus
    product_continuity: ProductContinuityStatus
    parent_order_id: OrderId | None
    replacement_order_id: OrderId | None
    line_universe_complete: bool

    def __post_init__(self) -> None:
        _require_type(self.customer_continuity, CustomerContinuityStatus, "customer_continuity")
        _require_type(self.product_continuity, ProductContinuityStatus, "product_continuity")
        _require_optional_type(self.parent_order_id, OrderId, "replacement_parent")
        _require_optional_type(self.replacement_order_id, OrderId, "replacement_order")
        if type(self.line_universe_complete) is not bool:
            raise SalesCreditValidationError("replacement_line_completeness")
        ids_present = self.parent_order_id is not None and self.replacement_order_id is not None
        if self.customer_continuity is CustomerContinuityStatus.PROVED and not ids_present:
            raise SalesCreditValidationError("replacement_customer_proof")
        if self.parent_order_id == self.replacement_order_id and ids_present:
            raise SalesCreditValidationError("replacement_distinct_orders")
        exact_product = self.product_continuity in {
            ProductContinuityStatus.EXACT_ES,
            ProductContinuityStatus.EXACT_MFG_OE,
        }
        if exact_product and (not ids_present or not self.line_universe_complete):
            raise SalesCreditValidationError("replacement_product_proof")


@dataclass(frozen=True, slots=True, repr=False)
class ReplacementCandidateInput:
    """One candidate snapshot plus the two factual continuity observations."""

    snapshot: OrderSnapshot
    line_universe_complete: bool
    possible_nonexact_continuity: bool = False

    def __post_init__(self) -> None:
        _require_type(self.snapshot, OrderSnapshot, "replacement_candidate_snapshot")
        if self.snapshot.order_id is None:
            raise SalesCreditValidationError("replacement_candidate_order_identity")
        if type(self.line_universe_complete) is not bool:
            raise SalesCreditValidationError("replacement_candidate_line_completeness")
        if type(self.possible_nonexact_continuity) is not bool:
            raise SalesCreditValidationError("replacement_candidate_nonexact")
        if self.line_universe_complete and (
            self.snapshot.extraction_status is SnapshotStatus.INVALID
            or "LINES_INCOMPLETE" in self.snapshot.warnings
        ):
            raise SalesCreditValidationError("replacement_candidate_line_completeness")

    def __repr__(self) -> str:
        return "ReplacementCandidateInput(<redacted>)"


_CANDIDATE_REPLACEMENT_STATUSES = frozenset(
    {
        ReplacementStatus.EXACT_RELEVANT,
        ReplacementStatus.POSSIBLE_REVIEW,
        ReplacementStatus.NOT_CONTINUATION,
        ReplacementStatus.BLOCKED,
    }
)
_REPLACEMENT_STATUS_PRIORITY = {
    ReplacementStatus.NOT_CONTINUATION: 0,
    ReplacementStatus.BLOCKED: 1,
    ReplacementStatus.POSSIBLE_REVIEW: 2,
    ReplacementStatus.EXACT_RELEVANT: 3,
}


def _require_replacement_continuity_partition(
    *,
    status: ReplacementStatus,
    customer: CustomerContinuityStatus,
    product: ProductContinuityStatus,
    code: str,
    reasons: frozenset[SalesCreditReason] = frozenset(),
) -> None:
    if status is ReplacementStatus.EXACT_RELEVANT and not (
        customer is CustomerContinuityStatus.PROVED
        and product
        in {ProductContinuityStatus.EXACT_ES, ProductContinuityStatus.EXACT_MFG_OE}
    ):
        raise SalesCreditValidationError(code)
    if status is ReplacementStatus.POSSIBLE_REVIEW and not (
        customer is CustomerContinuityStatus.PROVED
        and product is ProductContinuityStatus.NONEXACT
    ):
        raise SalesCreditValidationError(code)
    timing_reasons = reasons.intersection(
        {
            SalesCreditReason.ORDER_AFTER_REPLACEMENT_WINDOW,
            SalesCreditReason.ORDER_BEFORE_CANCELLATION,
        }
    )
    if timing_reasons and (
        status is not ReplacementStatus.NOT_CONTINUATION
        or len(timing_reasons) != 1
    ):
        raise SalesCreditValidationError(code)
    outside_window = len(timing_reasons) == 1
    if status is ReplacementStatus.NOT_CONTINUATION and not (
        customer is CustomerContinuityStatus.ABSENT
        or product is ProductContinuityStatus.ABSENT
        or outside_window
    ):
        raise SalesCreditValidationError(code)


@dataclass(frozen=True, slots=True, repr=False)
class ReplacementCandidateResult:
    """One closed, independently derived decision for one enumerated Order ID."""

    order_id: OrderId
    snapshot_id: SnapshotId
    status: ReplacementStatus
    customer_continuity: CustomerContinuityStatus
    product_continuity: ProductContinuityStatus
    reasons: tuple[SalesCreditReason, ...]

    def __post_init__(self) -> None:
        _require_type(self.order_id, OrderId, "replacement_result_order")
        _require_type(self.snapshot_id, SnapshotId, "replacement_result_snapshot")
        _require_type(self.status, ReplacementStatus, "replacement_result_status")
        _require_type(
            self.customer_continuity,
            CustomerContinuityStatus,
            "replacement_result_customer",
        )
        _require_type(
            self.product_continuity,
            ProductContinuityStatus,
            "replacement_result_product",
        )
        if self.status not in _CANDIDATE_REPLACEMENT_STATUSES:
            raise SalesCreditValidationError("replacement_result_status")
        _require_sorted_unique(
            self.reasons,
            item_type=SalesCreditReason,
            key=lambda item: item.value,
            code="replacement_result_reasons",
        )
        if not self.reasons:
            raise SalesCreditValidationError("replacement_result_reasons")
        reason_set = set(self.reasons)
        _require_replacement_continuity_partition(
            status=self.status,
            customer=self.customer_continuity,
            product=self.product_continuity,
            code="replacement_result_partition",
            reasons=frozenset(reason_set),
        )
        if self.status is ReplacementStatus.EXACT_RELEVANT:
            exact_reason = (
                SalesCreditReason.EXACT_ES_PRODUCT_CONTINUITY
                if self.product_continuity is ProductContinuityStatus.EXACT_ES
                else SalesCreditReason.EXACT_MFG_OE_PRODUCT_CONTINUITY
            )
            if exact_reason not in reason_set:
                raise SalesCreditValidationError("replacement_result_reasons")
        elif self.status is ReplacementStatus.POSSIBLE_REVIEW:
            if (
                SalesCreditReason.NONEXACT_PRODUCT_CONTINUITY_REQUIRES_REVIEW
                not in reason_set
            ):
                raise SalesCreditValidationError("replacement_result_reasons")
        elif self.status is ReplacementStatus.NOT_CONTINUATION:
            if (
                self.customer_continuity is CustomerContinuityStatus.ABSENT
                and SalesCreditReason.CUSTOMER_CONTINUITY_MISMATCH not in reason_set
            ) or (
                self.product_continuity is ProductContinuityStatus.ABSENT
                and SalesCreditReason.NO_PRODUCT_CONTINUITY not in reason_set
            ):
                raise SalesCreditValidationError("replacement_result_reasons")
        else:
            blocking_reasons = {
                SalesCreditReason.AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW,
                SalesCreditReason.CONTRADICTORY_FACTS,
                SalesCreditReason.CUSTOMER_CONTINUITY_UNPROVED,
                SalesCreditReason.IDENTIFIER_SEARCH_INCOMPLETE,
                SalesCreditReason.MISSING_REQUIRED_FIELD,
                SalesCreditReason.SNAPSHOT_INVALID,
                SalesCreditReason.SNAPSHOT_PARTIAL_DEPENDENCY_BLOCKED,
            }
            if reason_set.isdisjoint(blocking_reasons):
                raise SalesCreditValidationError("replacement_result_reasons")

    def to_dict(self) -> dict[str, object]:
        return {
            "customer_continuity": self.customer_continuity.value,
            "order_id": self.order_id.value,
            "product_continuity": self.product_continuity.value,
            "reasons": [reason.value for reason in self.reasons],
            "snapshot_id": self.snapshot_id.value,
            "status": self.status.value,
        }

    def __repr__(self) -> str:
        return "ReplacementCandidateResult(<redacted>)"


@dataclass(frozen=True, slots=True)
class AttributionDecision:
    classification: AttributionClassification
    raw_order_rep_present: bool

    def __post_init__(self) -> None:
        _require_type(self.classification, AttributionClassification, "attribution")
        if type(self.raw_order_rep_present) is not bool:
            raise SalesCreditValidationError("attribution_rep_presence")
        if (
            self.classification is not AttributionClassification.UNKNOWN
            and not self.raw_order_rep_present
        ):
            raise SalesCreditValidationError("attribution_coherence")

    def to_dict(self) -> dict[str, object]:
        return {
            "classification": self.classification.value,
            "raw_order_rep_present": self.raw_order_rep_present,
        }


@dataclass(frozen=True, slots=True)
class ValueDecision:
    status: OrderValueStatus
    placed_value: Money | None
    active_value: Money | None
    material_changes: tuple[MaterialChangeKind, ...]

    def __post_init__(self) -> None:
        _require_type(self.status, OrderValueStatus, "value_status")
        _require_nonnegative_money(self.placed_value, "value_placed")
        _require_nonnegative_money(self.active_value, "value_active")
        _require_sorted_unique(
            self.material_changes,
            item_type=MaterialChangeKind,
            key=lambda item: item.value,
            code="value_material_changes",
        )
        if self.status is OrderValueStatus.PLACED_VALUE_VERIFIED and self.placed_value is None:
            raise SalesCreditValidationError("value_verified_without_amount")
        if self.status is OrderValueStatus.PLACED_VALUE_VERIFIED:
            if self.active_value is None or self.material_changes:
                raise SalesCreditValidationError("value_verified_partition")
            if self.active_value.currency_code != self.placed_value.currency_code:
                raise SalesCreditValidationError("value_verified_currency")
            if self.active_value.registry_version != self.placed_value.registry_version:
                raise SalesCreditValidationError("value_verified_currency")
            if self.active_value.scale != self.placed_value.scale:
                raise SalesCreditValidationError("value_verified_currency")
            if self.active_value.minor_units not in {0, self.placed_value.minor_units}:
                raise SalesCreditValidationError("value_verified_active")
        elif self.status is OrderValueStatus.CURRENT_ONLY:
            if (
                self.placed_value is not None
                or self.active_value is not None
                or self.material_changes
            ):
                raise SalesCreditValidationError("value_current_partition")
        elif self.status is OrderValueStatus.CHANGED_REVIEW:
            if not self.material_changes or self.active_value is not None:
                raise SalesCreditValidationError("value_changed_partition")
        elif any((self.placed_value, self.active_value, self.material_changes)):
            raise SalesCreditValidationError("value_unknown_partition")

    def to_dict(self) -> dict[str, object]:
        return {
            "active_value": _money_dict(self.active_value),
            "material_changes": [change.value for change in self.material_changes],
            "placed_value": _money_dict(self.placed_value),
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class ReplacementDecision:
    status: ReplacementStatus
    customer_continuity: CustomerContinuityStatus
    product_continuity: ProductContinuityStatus
    search_run_id: RunId | None = None
    enumeration_complete: bool = False
    candidate_results: tuple[ReplacementCandidateResult, ...] = ()

    def __post_init__(self) -> None:
        _require_type(self.status, ReplacementStatus, "replacement_status")
        _require_type(self.customer_continuity, CustomerContinuityStatus, "replacement_customer")
        _require_type(self.product_continuity, ProductContinuityStatus, "replacement_product")
        _require_optional_type(self.search_run_id, RunId, "replacement_search_run")
        if type(self.enumeration_complete) is not bool:
            raise SalesCreditValidationError("replacement_enumeration_complete")
        _require_sorted_unique(
            self.candidate_results,
            item_type=ReplacementCandidateResult,
            key=lambda item: (item.order_id.value, item.snapshot_id.value),
            code="replacement_candidate_results",
        )
        if len({item.order_id for item in self.candidate_results}) != len(
            self.candidate_results
        ) or len({item.snapshot_id for item in self.candidate_results}) != len(
            self.candidate_results
        ):
            raise SalesCreditValidationError("replacement_candidate_results")
        _require_replacement_continuity_partition(
            status=self.status,
            customer=self.customer_continuity,
            product=self.product_continuity,
            code="replacement_continuity_partition",
        )
        neutral = (
            self.customer_continuity is CustomerContinuityStatus.UNKNOWN
            and self.product_continuity is ProductContinuityStatus.UNKNOWN
        )
        if self.status in {
            ReplacementStatus.NOT_APPLICABLE,
            ReplacementStatus.WINDOW_ACTIVE,
            ReplacementStatus.WINDOW_EXPIRED,
        } and not neutral:
            raise SalesCreditValidationError("replacement_window_partition")

        if self.status is ReplacementStatus.WINDOW_EXPIRED and (
            self.search_run_id is None
            or not self.enumeration_complete
            or any(
                item.status is not ReplacementStatus.NOT_CONTINUATION
                for item in self.candidate_results
            )
        ):
            raise SalesCreditValidationError("replacement_terminal_enumeration")

        if self.search_run_id is None:
            if self.enumeration_complete or self.candidate_results:
                raise SalesCreditValidationError("replacement_enumeration_association")
            if self.status not in {
                ReplacementStatus.NOT_APPLICABLE,
                ReplacementStatus.WINDOW_ACTIVE,
                ReplacementStatus.BLOCKED,
            }:
                raise SalesCreditValidationError("replacement_enumeration_required")
            return

        if not self.enumeration_complete:
            if self.status is not ReplacementStatus.BLOCKED or not neutral:
                raise SalesCreditValidationError("replacement_incomplete_enumeration")
            return

        if self.status is ReplacementStatus.NOT_APPLICABLE:
            raise SalesCreditValidationError("replacement_enumeration_not_applicable")
        if not self.candidate_results:
            if self.status not in {
                ReplacementStatus.WINDOW_ACTIVE,
                ReplacementStatus.WINDOW_EXPIRED,
            }:
                raise SalesCreditValidationError("replacement_empty_enumeration")
            return

        highest_priority = max(
            _REPLACEMENT_STATUS_PRIORITY[item.status]
            for item in self.candidate_results
        )
        winner = next(
            item
            for item in self.candidate_results
            if _REPLACEMENT_STATUS_PRIORITY[item.status] == highest_priority
        )
        if winner.status is ReplacementStatus.NOT_CONTINUATION:
            if self.status not in {
                ReplacementStatus.NOT_CONTINUATION,
                ReplacementStatus.WINDOW_ACTIVE,
                ReplacementStatus.WINDOW_EXPIRED,
            }:
                raise SalesCreditValidationError("replacement_aggregate_mismatch")
            if self.status is ReplacementStatus.NOT_CONTINUATION and (
                self.customer_continuity is not winner.customer_continuity
                or self.product_continuity is not winner.product_continuity
            ):
                raise SalesCreditValidationError("replacement_aggregate_mismatch")
            return
        if (
            self.status is not winner.status
            or self.customer_continuity is not winner.customer_continuity
            or self.product_continuity is not winner.product_continuity
        ):
            raise SalesCreditValidationError("replacement_aggregate_mismatch")

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_results": [item.to_dict() for item in self.candidate_results],
            "customer_continuity": self.customer_continuity.value,
            "enumeration_complete": self.enumeration_complete,
            "product_continuity": self.product_continuity.value,
            "search_run_id": (
                None if self.search_run_id is None else self.search_run_id.value
            ),
            "status": self.status.value,
        }

    def __repr__(self) -> str:
        return "ReplacementDecision(<redacted>)"


@dataclass(frozen=True, slots=True, kw_only=True)
class SalesCreditEvaluation:
    evaluation_id: EvaluationId
    order_id: OrderId
    snapshot_id: SnapshotId
    workflow_state: WorkflowState
    attribution: AttributionDecision
    value: ValueDecision
    replacement: ReplacementDecision
    reasons: tuple[SalesCreditReason, ...]
    human_review_required: bool
    supplied_facts: tuple[SalesCreditFact, ...]
    validations: tuple[SalesCreditValidation, ...]
    rules_evaluated: tuple[SalesCreditRule, ...]
    rules_fired: tuple[SalesCreditRule, ...]
    persistence_effects: tuple[SalesCreditEffect, ...]
    rule_pack_version: str = SALES_CREDIT_RULE_PACK_VERSION
    schema_version: str = SALES_CREDIT_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "sales-credit-evaluation/v1"

    def __post_init__(self) -> None:
        _require_type(self.evaluation_id, EvaluationId, "evaluation_id")
        _require_type(self.order_id, OrderId, "evaluation_order_id")
        _require_type(self.snapshot_id, SnapshotId, "evaluation_snapshot_id")
        _require_type(self.workflow_state, WorkflowState, "evaluation_workflow")
        _require_type(self.attribution, AttributionDecision, "evaluation_attribution")
        _require_type(self.value, ValueDecision, "evaluation_value")
        _require_type(self.replacement, ReplacementDecision, "evaluation_replacement")
        _require_sorted_unique(
            self.reasons,
            item_type=SalesCreditReason,
            key=lambda item: item.value,
            code="evaluation_reasons",
        )
        terminal_replacement = (
            self.replacement.status is ReplacementStatus.WINDOW_EXPIRED
        )
        if terminal_replacement and (
            SalesCreditReason.REPLACEMENT_WINDOW_EXPIRED not in self.reasons
        ):
            raise SalesCreditValidationError("evaluation_replacement_terminal_reason")
        if (
            self.workflow_state is WorkflowState.CANCELED_NO_REPLACEMENT
            and not terminal_replacement
        ):
            raise SalesCreditValidationError("evaluation_replacement_terminal_state")
        if type(self.human_review_required) is not bool:
            raise SalesCreditValidationError("evaluation_human_review")
        for values, item_type, code in (
            (self.supplied_facts, SalesCreditFact, "evaluation_supplied_facts"),
            (self.validations, SalesCreditValidation, "evaluation_validations"),
            (self.rules_evaluated, SalesCreditRule, "evaluation_rules_evaluated"),
            (self.rules_fired, SalesCreditRule, "evaluation_rules_fired"),
            (
                self.persistence_effects,
                SalesCreditEffect,
                "evaluation_persistence_effects",
            ),
        ):
            _require_sorted_unique(
                values,
                item_type=item_type,
                key=lambda item: item.value,
                code=code,
            )
        if not set(self.rules_fired).issubset(self.rules_evaluated):
            raise SalesCreditValidationError("evaluation_rule_subset")
        human_review_states = {
            WorkflowState.INBOUND_EVIDENCE_HUMAN_REVIEW,
            WorkflowState.MANUAL_REVIEW_REQUIRED,
            WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
            WorkflowState.OTHER_REP_HUMAN_REVIEW,
            WorkflowState.OUTBOUND_EVIDENCE_HUMAN_REVIEW,
            WorkflowState.POSSIBLE_REPLACEMENT_HUMAN_REVIEW,
            WorkflowState.TIMING_UNCERTAIN_HUMAN_REVIEW,
        }
        if self.human_review_required != (self.workflow_state in human_review_states):
            raise SalesCreditValidationError("evaluation_human_workflow")
        effects = set(self.persistence_effects)
        if SalesCreditEffect.NO_PERSISTENCE_MILESTONE_2 not in effects:
            raise SalesCreditValidationError("evaluation_no_persistence_effect")
        if self.human_review_required:
            if (
                SalesCreditEffect.HUMAN_REVIEW_REQUIRED not in effects
                or SalesCreditEffect.ACTIVE_CASE_CLASSIFICATION in effects
            ):
                raise SalesCreditValidationError("evaluation_human_effect")
        elif (
            SalesCreditEffect.ACTIVE_CASE_CLASSIFICATION not in effects
            or SalesCreditEffect.HUMAN_REVIEW_REQUIRED in effects
        ):
            raise SalesCreditValidationError("evaluation_active_effect")
        canceled = SalesCreditReason.CANCELED_ORDER_ZERO_ACTIVE_VALUE in self.reasons
        if canceled != (SalesCreditEffect.ZERO_ACTIVE_VALUE in effects):
            raise SalesCreditValidationError("evaluation_zero_value_effect")
        if self.rule_pack_version != SALES_CREDIT_RULE_PACK_VERSION:
            raise SalesCreditValidationError("evaluation_rule_version")
        if self.schema_version != SALES_CREDIT_SCHEMA_VERSION:
            raise SalesCreditValidationError("evaluation_schema")

    def to_dict(self) -> dict[str, object]:
        return {
            "attribution": self.attribution.to_dict(),
            "evaluation_id": self.evaluation_id.value,
            "human_review_required": self.human_review_required,
            "order_id": self.order_id.value,
            "persistence_effects": [item.value for item in self.persistence_effects],
            "reasons": [reason.value for reason in self.reasons],
            "replacement": self.replacement.to_dict(),
            "rule_pack_version": self.rule_pack_version,
            "rules_evaluated": [item.value for item in self.rules_evaluated],
            "rules_fired": [item.value for item in self.rules_fired],
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id.value,
            "supplied_facts": [item.value for item in self.supplied_facts],
            "validations": [item.value for item in self.validations],
            "value": self.value.to_dict(),
            "workflow_state": self.workflow_state.value,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())


@dataclass(frozen=True, slots=True, repr=False, kw_only=True)
class ManagerOutcome:
    occurrence_id: EvidenceId
    outcome: HumanOutcomeType
    decided_at: CanonicalTimestamp
    actor: RepId
    recorded_at: CanonicalTimestamp
    approved_amount: Money | None = None
    controlled_reason: SalesCreditReason | None = None
    active_note: str | None = field(default=None, repr=False)
    schema_version: str = SALES_CREDIT_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "sales-credit-manager-outcome/v1"

    def __post_init__(self) -> None:
        _require_type(self.occurrence_id, EvidenceId, "manager_occurrence_id")
        _require_type(self.outcome, HumanOutcomeType, "manager_outcome")
        _require_type(self.decided_at, CanonicalTimestamp, "manager_decided_at")
        _require_type(self.actor, RepId, "manager_actor")
        _require_type(self.recorded_at, CanonicalTimestamp, "manager_recorded_at")
        _require_nonnegative_money(self.approved_amount, "manager_approved_amount")
        _require_optional_type(
            self.controlled_reason,
            SalesCreditReason,
            "manager_reason",
        )
        _require_active_text(self.active_note, "manager_note")
        if self.outcome is HumanOutcomeType.PARTIAL:
            if self.approved_amount is None or self.approved_amount.minor_units <= 0:
                raise SalesCreditValidationError("manager_partial_amount")
        elif (
            self.outcome is not HumanOutcomeType.APPROVED
            and self.approved_amount is not None
        ):
            raise SalesCreditValidationError("manager_nonpartial_amount")
        if (self.recorded_at.epoch_seconds, self.recorded_at.nanosecond) < (
            self.decided_at.epoch_seconds,
            self.decided_at.nanosecond,
        ):
            raise SalesCreditValidationError("manager_time_order")
        if self.schema_version != SALES_CREDIT_SCHEMA_VERSION:
            raise SalesCreditValidationError("manager_schema")

    def to_dict(self) -> dict[str, object]:
        return {
            "active_note": self.active_note,
            "actor": self.actor.value,
            "approved_amount": _money_dict(self.approved_amount),
            "controlled_reason": (
                None if self.controlled_reason is None else self.controlled_reason.value
            ),
            "decided_at": self.decided_at.value,
            "occurrence_id": self.occurrence_id.value,
            "outcome": self.outcome.value,
            "recorded_at": self.recorded_at.value,
            "schema_version": self.schema_version,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "ManagerOutcome(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False, kw_only=True)
class SalesCreditCase:
    order_id: OrderId
    interaction_ids: tuple[InteractionId, ...]
    snapshot_ids: tuple[SnapshotId, ...]
    evidence_ids: tuple[EvidenceId, ...]
    evaluation_ids: tuple[EvaluationId, ...]
    attribution: AttributionClassification
    order_value_status: OrderValueStatus
    placed_value: Money | None
    workflow_state: WorkflowState
    replacement_parent: OrderId | None
    manager_outcome: ManagerOutcome | None
    created_at: CanonicalTimestamp
    updated_at: CanonicalTimestamp
    active_note: str | None = field(default=None, repr=False)
    schema_version: str = SALES_CREDIT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_type(self.order_id, OrderId, "case_order_id")
        for values, item_type, code in (
            (self.interaction_ids, InteractionId, "case_interactions"),
            (self.snapshot_ids, SnapshotId, "case_snapshots"),
            (self.evidence_ids, EvidenceId, "case_evidence"),
            (self.evaluation_ids, EvaluationId, "case_evaluations"),
        ):
            _require_sorted_unique(
                values,
                item_type=item_type,
                key=lambda item: item.value,
                code=code,
            )
        _require_type(self.attribution, AttributionClassification, "case_attribution")
        _require_type(self.order_value_status, OrderValueStatus, "case_value_status")
        _require_nonnegative_money(self.placed_value, "case_placed_value")
        _require_type(self.workflow_state, WorkflowState, "case_workflow")
        _require_optional_type(self.replacement_parent, OrderId, "case_replacement_parent")
        _require_optional_type(self.manager_outcome, ManagerOutcome, "case_manager_outcome")
        _require_type(self.created_at, CanonicalTimestamp, "case_created_at")
        _require_type(self.updated_at, CanonicalTimestamp, "case_updated_at")
        if (self.updated_at.epoch_seconds, self.updated_at.nanosecond) < (
            self.created_at.epoch_seconds,
            self.created_at.nanosecond,
        ):
            raise SalesCreditValidationError("case_time_order")
        if (
            self.manager_outcome is not None
            and self.workflow_state is not WorkflowState.CLOSED
        ):
            raise SalesCreditValidationError("case_outcome_workflow")
        _require_active_text(self.active_note, "case_note")
        if self.schema_version != SALES_CREDIT_SCHEMA_VERSION:
            raise SalesCreditValidationError("case_schema")

    def __repr__(self) -> str:
        return "SalesCreditCase(<redacted>)"


@dataclass(frozen=True, slots=True, kw_only=True)
class ClosedAuditRecord:
    order_id: OrderId
    opened_at: CanonicalTimestamp
    closed_at: CanonicalTimestamp
    interaction_precisions: tuple[TimestampPrecision, ...]
    system_workflow_before_close: WorkflowState
    attribution: AttributionClassification
    order_value_status: OrderValueStatus
    evidence_source_types: tuple[EvidenceSourceType, ...]
    evidence_classifications: tuple[EvidenceClassification, ...]
    reasons: tuple[SalesCreditReason, ...]
    human_outcome: HumanOutcomeType | None
    human_decided_at: CanonicalTimestamp | None
    human_recorded_at: CanonicalTimestamp | None
    decision_actor: RepId | None
    approved_amount: Money | None
    controlled_reason: SalesCreditReason | None
    concise_note: ClosedNoteCode
    rule_pack_version: str
    retention_policy_version: str = "sales-credit-retention-elapsed-90d/v1"
    schema_version: str = SALES_CREDIT_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "sales-credit-closed-audit/v1"

    def __post_init__(self) -> None:
        _require_type(self.order_id, OrderId, "closed_order_id")
        _require_type(self.opened_at, CanonicalTimestamp, "closed_opened_at")
        _require_type(self.closed_at, CanonicalTimestamp, "closed_closed_at")
        if (self.closed_at.epoch_seconds, self.closed_at.nanosecond) < (
            self.opened_at.epoch_seconds,
            self.opened_at.nanosecond,
        ):
            raise SalesCreditValidationError("closed_time_order")
        _require_sorted_unique(
            self.interaction_precisions,
            item_type=TimestampPrecision,
            key=lambda item: item.value,
            code="closed_precisions",
        )
        _require_type(
            self.system_workflow_before_close,
            WorkflowState,
            "closed_system_workflow",
        )
        if self.system_workflow_before_close is WorkflowState.CLOSED:
            raise SalesCreditValidationError("closed_prior_workflow")
        _require_type(self.attribution, AttributionClassification, "closed_attribution")
        _require_type(self.order_value_status, OrderValueStatus, "closed_value_status")
        _require_sorted_unique(
            self.evidence_source_types,
            item_type=EvidenceSourceType,
            key=lambda item: item.value,
            code="closed_evidence_source_types",
        )
        _require_sorted_unique(
            self.evidence_classifications,
            item_type=EvidenceClassification,
            key=lambda item: item.value,
            code="closed_evidence_classifications",
        )
        _require_sorted_unique(
            self.reasons,
            item_type=SalesCreditReason,
            key=lambda item: item.value,
            code="closed_reasons",
        )
        _require_optional_type(
            self.human_outcome,
            HumanOutcomeType,
            "closed_human_outcome",
        )
        for value, expected, code in (
            (self.human_decided_at, CanonicalTimestamp, "closed_decided_at"),
            (self.human_recorded_at, CanonicalTimestamp, "closed_recorded_at"),
            (self.decision_actor, RepId, "closed_decision_actor"),
            (self.approved_amount, Money, "closed_approved_amount"),
            (self.controlled_reason, SalesCreditReason, "closed_controlled_reason"),
        ):
            _require_optional_type(value, expected, code)
        _require_type(self.concise_note, ClosedNoteCode, "closed_concise_note")
        outcome_values = (
            self.human_decided_at,
            self.human_recorded_at,
            self.decision_actor,
            self.approved_amount,
            self.controlled_reason,
        )
        if self.human_outcome is None and any(value is not None for value in outcome_values):
            raise SalesCreditValidationError("closed_outcome_metadata")
        if self.human_outcome is not None:
            required = (
                self.human_decided_at,
                self.human_recorded_at,
                self.decision_actor,
            )
            if any(value is None for value in required):
                raise SalesCreditValidationError("closed_outcome_metadata")
        _require_nonnegative_money(self.approved_amount, "closed_approved_amount")
        if self.human_outcome is None:
            if self.system_workflow_before_close not in {
                WorkflowState.CANCELED_NO_REPLACEMENT,
                WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
                WorkflowState.VERIFIED_PREORDER_EVIDENCE,
            }:
                raise SalesCreditValidationError("closed_system_terminal")
            if self.system_workflow_before_close is WorkflowState.CANCELED_NO_REPLACEMENT:
                expected_note = ClosedNoteCode.CANCELED_NO_REPLACEMENT
            else:
                expected_note = ClosedNoteCode.AUTOMATIC_CLASSIFICATION_CLOSED
        elif self.human_outcome is HumanOutcomeType.PARTIAL:
            if self.approved_amount is None or self.approved_amount.minor_units <= 0:
                raise SalesCreditValidationError("closed_partial_amount")
        elif (
            self.human_outcome is not HumanOutcomeType.APPROVED
            and self.approved_amount is not None
        ):
                raise SalesCreditValidationError("closed_nonapproved_amount")
        if self.human_outcome is not None:
            expected_note = ClosedNoteCode.HUMAN_OUTCOME_RECORDED
        if self.concise_note is not expected_note:
            raise SalesCreditValidationError("closed_concise_note_coherence")
        if self.human_decided_at is not None and self.human_recorded_at is not None:
            opened = (self.opened_at.epoch_seconds, self.opened_at.nanosecond)
            decided = (
                self.human_decided_at.epoch_seconds,
                self.human_decided_at.nanosecond,
            )
            recorded = (
                self.human_recorded_at.epoch_seconds,
                self.human_recorded_at.nanosecond,
            )
            closed = (self.closed_at.epoch_seconds, self.closed_at.nanosecond)
            if decided < opened or decided > recorded or recorded > closed:
                raise SalesCreditValidationError("closed_decision_time_order")
        if self.retention_policy_version != "sales-credit-retention-elapsed-90d/v1":
            raise SalesCreditValidationError("closed_retention_version")
        if self.rule_pack_version != SALES_CREDIT_RULE_PACK_VERSION:
            raise SalesCreditValidationError("closed_rule_version")
        if self.schema_version != SALES_CREDIT_SCHEMA_VERSION:
            raise SalesCreditValidationError("closed_schema")

    def to_dict(self) -> dict[str, object]:
        return {
            "attribution": self.attribution.value,
            "closed_at": self.closed_at.value,
            "concise_note": self.concise_note.value,
            "controlled_reason": (
                None if self.controlled_reason is None else self.controlled_reason.value
            ),
            "decision_actor": (
                None if self.decision_actor is None else self.decision_actor.value
            ),
            "evidence_classifications": [
                item.value for item in self.evidence_classifications
            ],
            "evidence_source_types": [item.value for item in self.evidence_source_types],
            "approved_amount": _money_dict(self.approved_amount),
            "human_decided_at": (
                None if self.human_decided_at is None else self.human_decided_at.value
            ),
            "human_outcome": (
                None if self.human_outcome is None else self.human_outcome.value
            ),
            "human_recorded_at": (
                None if self.human_recorded_at is None else self.human_recorded_at.value
            ),
            "interaction_precisions": [
                item.value for item in self.interaction_precisions
            ],
            "opened_at": self.opened_at.value,
            "order_id": self.order_id.value,
            "order_value_status": self.order_value_status.value,
            "reasons": [reason.value for reason in self.reasons],
            "retention_policy_version": self.retention_policy_version,
            "rule_pack_version": self.rule_pack_version,
            "schema_version": self.schema_version,
            "system_workflow_before_close": self.system_workflow_before_close.value,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())


def sorted_reasons(*reasons: SalesCreditReason) -> tuple[SalesCreditReason, ...]:
    return tuple(sorted(set(reasons), key=lambda item: item.value))


__all__ = [
    "AttributionClassification",
    "AttributionDecision",
    "ClosedNoteCode",
    "ClosedAuditRecord",
    "CustomerContinuityStatus",
    "EvidenceClassification",
    "EvidenceDirection",
    "EvidenceEvent",
    "EvidenceIdentifierKind",
    "EvidenceSourceType",
    "EvidenceTimingRelation",
    "HumanOutcomeType",
    "InteractionRecord",
    "LineItemSnapshot",
    "ManagerOutcome",
    "MaterialChange",
    "MaterialChangeKind",
    "NotesScanStatus",
    "OrderLifecycleStatus",
    "OrderSnapshot",
    "OrderValueStatus",
    "ProductContinuityStatus",
    "ReplacementCandidateInput",
    "ReplacementCandidateResult",
    "ReplacementDecision",
    "ReplacementFacts",
    "ReplacementStatus",
    "SALES_CREDIT_RULE_PACK_VERSION",
    "SALES_CREDIT_PARSER_VERSION",
    "SALES_CREDIT_SCHEMA_VERSION",
    "SalesCreditCase",
    "SalesCreditEffect",
    "SalesCreditEvaluation",
    "SalesCreditFact",
    "SalesCreditReason",
    "SalesCreditRule",
    "SalesCreditValidation",
    "SalesCreditValidationError",
    "SearchTriggerType",
    "SnapshotStatus",
    "TimestampPrecision",
    "ValueDecision",
    "WorkflowState",
    "derive_evidence_classification",
    "order_provenance_binding",
    "sorted_reasons",
]
