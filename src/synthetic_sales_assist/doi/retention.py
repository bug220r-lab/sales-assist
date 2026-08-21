"""Pure DOI calendar-90 retention and identity-free KPI finalization."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from threading import RLock
from types import MappingProxyType
from typing import ClassVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from synthetic_sales_assist.doi.identities import DoiOrderId
from synthetic_sales_assist.doi.interventions import (
    ActionVerificationEvent,
    DOIIntervention,
    DOIResultingOrderLink,
    ValueCorrectionKind,
    ValueEvent,
    _intervention_hash_fixture_records,
)
from synthetic_sales_assist.doi.models import (
    ActionContextState,
    CaseLifecycleState,
    DOIActionContext,
    InterventionType,
    KPIContributionState,
    ResultingOrderLinkState,
    TerminalClosureReason,
    ValueEventType,
    ValueVerificationState,
)
from synthetic_sales_assist.domain.canonical import HashBinding, canonical_json_bytes, domain_hash
from synthetic_sales_assist.domain.identities import EvidenceId
from synthetic_sales_assist.domain.numeric import Money
from synthetic_sales_assist.domain.records import (
    ReasonSet,
    SourceKind,
    SourceObjectNamespace,
    SourceRef,
)
from synthetic_sales_assist.domain.registries import load_doi_registries
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.domain.tokens import ImmutableStrEnum


DOI_RETENTION_POLICY_VERSION = "doi-retention-calendar90-ny/v1"
DOI_TIMEZONE_DATABASE_BINDING = "python-zoneinfo-America-New_York/v1"
DOI_BUSINESS_TIMEZONE = "America/New_York"
RETENTION_HASH_KNOWN_ANSWERS = MappingProxyType(
    {
        "KPIContributionEvent": "cbdecc9843c29639bac1d135edae6ad810aab15778e55027dab91e896571e003",
        "NonidentifyingKPIBucket": (
            "abdfd0a7738ea80af8d8181d19f4657a20b93c9a3140404fc869e4370ec329a6"
        ),
        "PriorClosureRetentionBindingV1": (
            "811001092428f0db2b2069457b5197b780a1326afe1414674afab653ad07bf8e"
        ),
        "RetainedKPIContribution": (
            "d8bd285659a6d531d6e4568a6119b0a3704bf0caec4a72037f3aaa4c7a63e592"
        ),
        "VerifiedCurrencyEnvelope": (
            "177a78b1d98ab7f38f049b3d438a9f60fa1b56010c8ef2da92c91617833f34f5"
        ),
    }
)


class DoiRetentionError(RuntimeError):
    """A closed retention/KPI rejection with no supplied identity in diagnostics."""

    def __init__(self, code: str, *, reasons: ReasonSet | None = None) -> None:
        self.code = code
        self.reasons = reasons or ReasonSet()
        super().__init__(f"DOI retention rejected: {code}")


def _reasons(*codes: str) -> ReasonSet:
    registries = load_doi_registries()
    return ReasonSet(
        tuple(sorted((registries.reason_ref(code) for code in codes), key=lambda item: item.code))
    )


def _instant(value: CanonicalTimestamp) -> tuple[int, int]:
    return (value.epoch_seconds, value.nanosecond)


def _zone() -> ZoneInfo:
    try:
        return ZoneInfo(DOI_BUSINESS_TIMEZONE)
    except ZoneInfoNotFoundError:
        raise DoiRetentionError(
            "RETENTION_TIMEZONE_UNAVAILABLE",
            reasons=_reasons("RC-096"),
        ) from None


def _valid_local_candidates(naive: datetime, zone: ZoneInfo) -> tuple[datetime, ...]:
    candidates: list[datetime] = []
    for fold in (0, 1):
        local = naive.replace(tzinfo=zone, fold=fold)
        round_trip = local.astimezone(UTC).astimezone(zone)
        if round_trip.replace(tzinfo=None) == naive and round_trip.fold == fold:
            candidates.append(local)
    unique = {candidate.astimezone(UTC): candidate for candidate in candidates}
    return tuple(unique[key] for key in sorted(unique))


def _canonical_utc(utc_value: datetime, nanosecond: int) -> CanonicalTimestamp:
    normalized = utc_value.astimezone(UTC)
    text = normalized.strftime("%Y-%m-%dT%H:%M:%S")
    if nanosecond:
        text += f".{nanosecond:09d}".rstrip("0")
    return CanonicalTimestamp(text + "Z")


def calendar90(closed_at: CanonicalTimestamp) -> CanonicalTimestamp:
    """Add 90 New York local dates with closed DST gap/overlap resolution.

    The source wall time is preserved.  A spring-forward gap resolves to its first valid local
    instant; a fall-back overlap resolves to the later occurrence.
    """

    if type(closed_at) is not CanonicalTimestamp:
        raise DoiRetentionError("RETENTION_TIMESTAMP_INVALID")
    zone = _zone()
    try:
        utc = datetime.fromtimestamp(closed_at.epoch_seconds, tz=UTC)
        local = utc.astimezone(zone)
        target_date = local.date() + timedelta(days=90)
        naive = datetime.combine(target_date, local.timetz().replace(tzinfo=None))
    except (OverflowError, ValueError):
        raise DoiRetentionError(
            "RETENTION_CLOCK_CALCULATION_FAILED",
            reasons=_reasons("RC-096"),
        ) from None
    candidates = _valid_local_candidates(naive, zone)
    target_nanosecond = closed_at.nanosecond
    if not candidates:
        # Modern IANA New York gaps have minute boundaries.  Start inside the rejected gap
        # and select the first constructible wall-clock minute, with no fabricated fraction.
        probe = naive.replace(second=0, microsecond=0)
        for _ in range(241):
            candidates = _valid_local_candidates(probe, zone)
            if candidates:
                target_nanosecond = 0
                break
            probe += timedelta(minutes=1)
    if not candidates:
        raise DoiRetentionError(
            "RETENTION_CLOCK_CALCULATION_FAILED",
            reasons=_reasons("RC-096"),
        )
    selected = max(candidates, key=lambda item: item.astimezone(UTC))
    return _canonical_utc(selected.astimezone(UTC), target_nanosecond)


def business_action_date(action_at: CanonicalTimestamp) -> date:
    """Return the exact New York local action date for one verified instant."""

    if type(action_at) is not CanonicalTimestamp:
        raise DoiRetentionError("KPI_ACTION_TIMESTAMP_INVALID", reasons=_reasons("RC-099"))
    try:
        return datetime.fromtimestamp(action_at.epoch_seconds, tz=UTC).astimezone(_zone()).date()
    except (OverflowError, ValueError):
        raise DoiRetentionError(
            "KPI_ACTION_TIMESTAMP_INVALID",
            reasons=_reasons("RC-099"),
        ) from None


def _hash(value: HashBinding) -> dict[str, str]:
    return {"domain": value.domain, "sha256": value.sha256}


@dataclass(frozen=True, slots=True, repr=False)
class PriorClosureRetentionBindingV1:
    case_id: EvidenceId
    closure_event_id: EvidenceId
    lifecycle_state: CaseLifecycleState
    closure_reason: TerminalClosureReason
    closed_at: CanonicalTimestamp
    prior_purge_eligible_at: CanonicalTimestamp
    projection_revision: int
    projection_sha256: str
    retention_policy_version: str = DOI_RETENTION_POLICY_VERSION
    timezone_database_binding: str = DOI_TIMEZONE_DATABASE_BINDING

    HASH_DOMAIN: ClassVar[str] = "doi-prior-closure-retention-binding/v1"

    def __post_init__(self) -> None:
        if (
            type(self.case_id) is not EvidenceId
            or type(self.closure_event_id) is not EvidenceId
            or self.lifecycle_state
            not in {CaseLifecycleState.CLOSED_HARD, CaseLifecycleState.CLOSED_REVERSIBLE}
            or type(self.closure_reason) is not TerminalClosureReason
            or type(self.closed_at) is not CanonicalTimestamp
            or type(self.prior_purge_eligible_at) is not CanonicalTimestamp
            or type(self.projection_revision) is not int
            or self.projection_revision < 1
            or type(self.projection_sha256) is not str
            or len(self.projection_sha256) != 64
            or self.retention_policy_version != DOI_RETENTION_POLICY_VERSION
            or self.timezone_database_binding != DOI_TIMEZONE_DATABASE_BINDING
        ):
            raise DoiRetentionError("PRIOR_CLOSURE_BINDING_INVALID", reasons=_reasons("RC-113"))
        if self.prior_purge_eligible_at != calendar90(self.closed_at):
            raise DoiRetentionError("PRIOR_CLOSURE_DEADLINE_INVALID", reasons=_reasons("RC-113"))
        hard_reasons = {TerminalClosureReason.SHIPPED, TerminalClosureReason.CANCELED}
        if (self.lifecycle_state is CaseLifecycleState.CLOSED_HARD) != (
            self.closure_reason in hard_reasons
        ):
            raise DoiRetentionError("PRIOR_CLOSURE_PARTITION_INVALID", reasons=_reasons("RC-113"))

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id.value,
            "closed_at": self.closed_at.value,
            "closure_event_id": self.closure_event_id.value,
            "closure_reason": self.closure_reason.value,
            "lifecycle_state": self.lifecycle_state.value,
            "prior_purge_eligible_at": self.prior_purge_eligible_at.value,
            "projection_revision": self.projection_revision,
            "projection_sha256": self.projection_sha256,
            "retention_policy_version": self.retention_policy_version,
            "timezone_database_binding": self.timezone_database_binding,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "PriorClosureRetentionBindingV1(<redacted>)"


@dataclass(frozen=True, slots=True)
class DoiRetentionProjection:
    binding: PriorClosureRetentionBindingV1
    purge_eligible_at: CanonicalTimestamp | None
    canceled_by_reopen_event_id: EvidenceId | None = None
    reasons: ReasonSet = field(default_factory=ReasonSet)

    def __post_init__(self) -> None:
        if (
            type(self.binding) is not PriorClosureRetentionBindingV1
            or type(self.reasons) is not ReasonSet
        ):
            raise DoiRetentionError("RETENTION_PROJECTION_INVALID")
        active = self.purge_eligible_at is not None
        if active:
            if (
                self.purge_eligible_at != self.binding.prior_purge_eligible_at
                or self.canceled_by_reopen_event_id is not None
                or self.reasons != _reasons("RC-079")
            ):
                raise DoiRetentionError("RETENTION_PROJECTION_INVALID")
        elif (
            type(self.canceled_by_reopen_event_id) is not EvidenceId
            or self.reasons != _reasons("RC-078", "RC-080")
        ):
            raise DoiRetentionError("RETENTION_PROJECTION_INVALID")


def schedule_retention(
    *,
    case_id: EvidenceId,
    closure_event_id: EvidenceId,
    lifecycle_state: CaseLifecycleState,
    closure_reason: TerminalClosureReason,
    closed_at: CanonicalTimestamp,
    projection_revision: int,
    projection_sha256: str,
) -> DoiRetentionProjection:
    deadline = calendar90(closed_at)
    binding = PriorClosureRetentionBindingV1(
        case_id=case_id,
        closure_event_id=closure_event_id,
        lifecycle_state=lifecycle_state,
        closure_reason=closure_reason,
        closed_at=closed_at,
        prior_purge_eligible_at=deadline,
        projection_revision=projection_revision,
        projection_sha256=projection_sha256,
    )
    return DoiRetentionProjection(
        binding=binding,
        purge_eligible_at=deadline,
        reasons=_reasons("RC-079"),
    )


def cancel_retention_on_reopen(
    projection: DoiRetentionProjection,
    *,
    supplied_binding: PriorClosureRetentionBindingV1,
    reopen_event_id: EvidenceId,
) -> DoiRetentionProjection:
    """Cancel only an exact reversible-closure deadline with byte-equal binding."""

    if (
        type(projection) is not DoiRetentionProjection
        or type(supplied_binding) is not PriorClosureRetentionBindingV1
        or type(reopen_event_id) is not EvidenceId
    ):
        raise DoiRetentionError("REOPEN_RETENTION_INPUT_INVALID", reasons=_reasons("RC-113"))
    if projection.binding.lifecycle_state is CaseLifecycleState.CLOSED_HARD:
        raise DoiRetentionError("HARD_CLOSURE_CANNOT_REOPEN", reasons=_reasons("RC-081"))
    if projection.purge_eligible_at is None:
        raise DoiRetentionError("PURGE_ALREADY_CANCELED", reasons=_reasons("RC-081"))
    if projection.binding.canonical_bytes() != supplied_binding.canonical_bytes():
        raise DoiRetentionError("PRIOR_CLOSURE_BINDING_MISMATCH", reasons=_reasons("RC-113"))
    return DoiRetentionProjection(
        binding=projection.binding,
        purge_eligible_at=None,
        canceled_by_reopen_event_id=reopen_event_id,
        reasons=_reasons("RC-078", "RC-080"),
    )


class IdentityRetentionKind(ImmutableStrEnum):
    """Closed non-case identifying graphs governed by the pure retention boundary."""

    REJECTED_SOURCE_RECORD = "REJECTED_SOURCE_RECORD"
    SOURCE_IMPORT_ATTEMPT = "SOURCE_IMPORT_ATTEMPT"


class IdentityRetentionState(ImmutableStrEnum):
    SCHEDULED = "SCHEDULED"
    PURGED = "PURGED"


@dataclass(frozen=True, slots=True, repr=False)
class IdentityRetentionDecision:
    """A pure decision whose purge reason exists only inside the deleting transaction."""

    kind: IdentityRetentionKind
    state: IdentityRetentionState
    purge_eligible_at: CanonicalTimestamp
    retained_identity_binding: HashBinding | None
    transaction_reasons: ReasonSet

    def __post_init__(self) -> None:
        if (
            type(self.kind) is not IdentityRetentionKind
            or type(self.state) is not IdentityRetentionState
            or type(self.purge_eligible_at) is not CanonicalTimestamp
            or type(self.transaction_reasons) is not ReasonSet
        ):
            raise DoiRetentionError("IDENTITY_RETENTION_DECISION_INVALID")
        scheduled = self.state is IdentityRetentionState.SCHEDULED
        if scheduled != (type(self.retained_identity_binding) is HashBinding):
            raise DoiRetentionError("IDENTITY_RETENTION_DECISION_INVALID")
        expected = {
            (IdentityRetentionKind.REJECTED_SOURCE_RECORD, IdentityRetentionState.SCHEDULED): (
                "RC-092",
            ),
            (IdentityRetentionKind.REJECTED_SOURCE_RECORD, IdentityRetentionState.PURGED): (
                "RC-093",
            ),
            (IdentityRetentionKind.SOURCE_IMPORT_ATTEMPT, IdentityRetentionState.SCHEDULED): (),
            (IdentityRetentionKind.SOURCE_IMPORT_ATTEMPT, IdentityRetentionState.PURGED): (
                "RC-114",
            ),
        }[(self.kind, self.state)]
        if self.transaction_reasons != _reasons(*expected):
            raise DoiRetentionError("IDENTITY_RETENTION_DECISION_INVALID")

    def __repr__(self) -> str:
        return "IdentityRetentionDecision(<redacted>)"


def schedule_identity_retention(
    *,
    kind: IdentityRetentionKind,
    identity_binding: HashBinding,
    run_completed_at: CanonicalTimestamp,
) -> IdentityRetentionDecision:
    """Schedule one exact identity graph from the common terminal-run clock."""

    domains = {
        IdentityRetentionKind.REJECTED_SOURCE_RECORD: "doi-rejected-source-record/v1",
        IdentityRetentionKind.SOURCE_IMPORT_ATTEMPT: "doi-source-import-attempt/v1",
    }
    if (
        type(kind) is not IdentityRetentionKind
        or type(identity_binding) is not HashBinding
        or type(run_completed_at) is not CanonicalTimestamp
        or identity_binding.domain != domains.get(kind)
    ):
        raise DoiRetentionError(
            "IDENTITY_RETENTION_INPUT_INVALID",
            reasons=_reasons("RC-113"),
        )
    return IdentityRetentionDecision(
        kind=kind,
        state=IdentityRetentionState.SCHEDULED,
        purge_eligible_at=calendar90(run_completed_at),
        retained_identity_binding=identity_binding,
        transaction_reasons=(
            _reasons("RC-092")
            if kind is IdentityRetentionKind.REJECTED_SOURCE_RECORD
            else ReasonSet()
        ),
    )


def finalize_identity_purge(
    decision: IdentityRetentionDecision,
    *,
    now: CanonicalTimestamp,
) -> IdentityRetentionDecision:
    """Return an identity-free deletion decision at or after exact eligibility."""

    if (
        type(decision) is not IdentityRetentionDecision
        or decision.state is not IdentityRetentionState.SCHEDULED
        or type(now) is not CanonicalTimestamp
    ):
        raise DoiRetentionError(
            "IDENTITY_PURGE_INPUT_INVALID",
            reasons=_reasons("RC-113"),
        )
    if _instant(now) < _instant(decision.purge_eligible_at):
        raise DoiRetentionError("IDENTITY_PURGE_NOT_ELIGIBLE", reasons=_reasons("RC-081"))
    return IdentityRetentionDecision(
        kind=decision.kind,
        state=IdentityRetentionState.PURGED,
        purge_eligible_at=decision.purge_eligible_at,
        retained_identity_binding=None,
        transaction_reasons=_reasons(
            "RC-093"
            if decision.kind is IdentityRetentionKind.REJECTED_SOURCE_RECORD
            else "RC-114"
        ),
    )


_KPI_CONTRIBUTION_TOKEN = object()


class KPIContributionEventKind(ImmutableStrEnum):
    UNVERIFIED_INITIALIZATION = "UNVERIFIED_INITIALIZATION"
    ORIGINAL_VALUE = "ORIGINAL_VALUE"
    VALUE_CORRECTION = "VALUE_CORRECTION"
    REVERSAL_RECOMPUTE = "REVERSAL_RECOMPUTE"


@dataclass(frozen=True, slots=True, init=False, repr=False)
class VerifiedCurrencyEnvelope:
    """Currency metadata observed without fabricating an unverified Money amount."""

    evidence_id: EvidenceId
    intervention_id: EvidenceId
    intervention_action_binding: HashBinding
    action_context_binding: HashBinding
    subject_order_id: DoiOrderId
    currency_code: str
    registry_version: str
    scale: int
    observed_at: CanonicalTimestamp
    source: SourceRef
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-verified-currency-envelope/v1"

    def __new__(cls) -> VerifiedCurrencyEnvelope:
        raise DoiRetentionError("KPI_CURRENCY_ENVELOPE_FACTORY_REQUIRED")

    @classmethod
    def from_order_observation(
        cls,
        *,
        evidence_id: EvidenceId,
        intervention: DOIIntervention,
        completed_action_context: DOIActionContext,
        currency_code: str,
        registry_version: str,
        scale: int,
        observed_at: CanonicalTimestamp,
        source: SourceRef,
    ) -> VerifiedCurrencyEnvelope:
        if type(intervention) is not DOIIntervention:
            raise DoiRetentionError("KPI_CURRENCY_INTERVENTION_INVALID")
        expected_context = (
            intervention.action_events[0].evidence.material.action_context_binding
        )
        if (
            type(evidence_id) is not EvidenceId
            or type(completed_action_context) is not DOIActionContext
            or completed_action_context.state is not ActionContextState.CLOSED_COMPLETED
            or completed_action_context.hash_binding() != expected_context
            or type(observed_at) is not CanonicalTimestamp
            or type(source) is not SourceRef
            or source.source_kind is not SourceKind.SYNTHETIC_ORDER_FIXTURE
            or source.object_namespace is not SourceObjectNamespace.SYNTHETIC_ORDER
            or source.object_id != completed_action_context.order_id.value
        ):
            raise DoiRetentionError("KPI_CURRENCY_ENVELOPE_OWNER_INVALID")
        try:
            Money.from_minor_units(
                0,
                currency_code=currency_code,
                registry_version=registry_version,
                scale=scale,
            )
        except (TypeError, ValueError):
            raise DoiRetentionError(
                "KPI_CURRENCY_ENVELOPE_INVALID",
                reasons=_reasons("RC-094"),
            ) from None
        instance = object.__new__(cls)
        object.__setattr__(instance, "evidence_id", evidence_id)
        object.__setattr__(instance, "intervention_id", intervention.intervention_id)
        object.__setattr__(
            instance,
            "intervention_action_binding",
            intervention.action_events[0].hash_binding(),
        )
        object.__setattr__(
            instance,
            "action_context_binding",
            completed_action_context.hash_binding(),
        )
        object.__setattr__(instance, "subject_order_id", completed_action_context.order_id)
        object.__setattr__(instance, "currency_code", currency_code)
        object.__setattr__(instance, "registry_version", registry_version)
        object.__setattr__(instance, "scale", scale)
        object.__setattr__(instance, "observed_at", observed_at)
        object.__setattr__(instance, "source", source)
        object.__setattr__(instance, "schema_version", "doi-kpi-history/v1")
        instance.__post_init__()
        return instance

    def __post_init__(self) -> None:
        if (
            type(self.evidence_id) is not EvidenceId
            or type(self.intervention_id) is not EvidenceId
            or type(self.intervention_action_binding) is not HashBinding
            or self.intervention_action_binding.domain != ActionVerificationEvent.HASH_DOMAIN
            or type(self.action_context_binding) is not HashBinding
            or self.action_context_binding.domain != DOIActionContext.HASH_DOMAIN
            or type(self.subject_order_id) is not DoiOrderId
            or type(self.currency_code) is not str
            or type(self.registry_version) is not str
            or type(self.scale) is not int
            or type(self.observed_at) is not CanonicalTimestamp
            or type(self.source) is not SourceRef
            or self.source.object_id != self.subject_order_id.value
            or self.schema_version != "doi-kpi-history/v1"
        ):
            raise DoiRetentionError("KPI_CURRENCY_ENVELOPE_INVALID")

    def zero_money(self) -> Money:
        return Money.from_minor_units(
            0,
            currency_code=self.currency_code,
            registry_version=self.registry_version,
            scale=self.scale,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "action_context_binding": _hash(self.action_context_binding),
            "currency_code": self.currency_code,
            "evidence_id": self.evidence_id.value,
            "intervention_action_binding": _hash(self.intervention_action_binding),
            "intervention_id": self.intervention_id.value,
            "observed_at": self.observed_at.value,
            "registry_version": self.registry_version,
            "scale": self.scale,
            "schema_version": self.schema_version,
            "source": _hash(self.source.hash_binding()),
            "subject_order_id": self.subject_order_id.to_json_value(),
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())


@dataclass(frozen=True, slots=True, init=False, repr=False)
class KPIContributionEvent:
    event_id: EvidenceId
    intervention_id: EvidenceId
    intervention_action_binding: HashBinding
    resulting_link_id: EvidenceId
    resulting_link_binding: HashBinding
    kind: KPIContributionEventKind
    trigger_binding: HashBinding
    action_occurred_at: CanonicalTimestamp
    action_date: date
    current_value: Money
    sequence: int
    predecessor_binding: HashBinding | None
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-kpi-contribution-event/v1"

    def __new__(cls) -> KPIContributionEvent:
        raise DoiRetentionError("KPI_CONTRIBUTION_REDUCER_REQUIRED")

    @classmethod
    def _create(
        cls,
        *,
        event_id: EvidenceId,
        intervention: DOIIntervention,
        resulting_link: DOIResultingOrderLink,
        kind: KPIContributionEventKind,
        trigger_binding: HashBinding,
        current_value: Money,
        sequence: int,
        predecessor_binding: HashBinding | None,
        factory_capability: object,
    ) -> KPIContributionEvent:
        if (
            factory_capability is not _KPI_CONTRIBUTION_TOKEN
            or type(event_id) is not EvidenceId
            or type(intervention.action_occurred_at) is not CanonicalTimestamp
        ):
            raise DoiRetentionError("KPI_CONTRIBUTION_REDUCER_REQUIRED")
        instance = object.__new__(cls)
        object.__setattr__(instance, "event_id", event_id)
        object.__setattr__(instance, "intervention_id", intervention.intervention_id)
        object.__setattr__(
            instance,
            "intervention_action_binding",
            intervention.action_events[0].hash_binding(),
        )
        object.__setattr__(instance, "resulting_link_id", resulting_link.link_id)
        object.__setattr__(
            instance,
            "resulting_link_binding",
            resulting_link.hash_binding(),
        )
        object.__setattr__(instance, "kind", kind)
        object.__setattr__(instance, "trigger_binding", trigger_binding)
        object.__setattr__(instance, "action_occurred_at", intervention.action_occurred_at)
        object.__setattr__(
            instance,
            "action_date",
            business_action_date(intervention.action_occurred_at),
        )
        object.__setattr__(instance, "current_value", current_value)
        object.__setattr__(instance, "sequence", sequence)
        object.__setattr__(instance, "predecessor_binding", predecessor_binding)
        object.__setattr__(instance, "schema_version", "doi-kpi-history/v1")
        instance.__post_init__()
        return instance

    def __post_init__(self) -> None:
        if (
            type(self.event_id) is not EvidenceId
            or type(self.intervention_id) is not EvidenceId
            or type(self.intervention_action_binding) is not HashBinding
            or self.intervention_action_binding.domain != ActionVerificationEvent.HASH_DOMAIN
            or type(self.resulting_link_id) is not EvidenceId
            or type(self.resulting_link_binding) is not HashBinding
            or self.resulting_link_binding.domain != DOIResultingOrderLink.HASH_DOMAIN
            or type(self.kind) is not KPIContributionEventKind
            or type(self.trigger_binding) is not HashBinding
            or self.trigger_binding.domain
            not in {ValueEvent.HASH_DOMAIN, ActionVerificationEvent.HASH_DOMAIN}
            or type(self.action_occurred_at) is not CanonicalTimestamp
            or self.action_date != business_action_date(self.action_occurred_at)
            or type(self.current_value) is not Money
            or type(self.sequence) is not int
            or self.sequence < 1
            or (self.sequence == 1) != (self.predecessor_binding is None)
            or (
                self.predecessor_binding is not None
                and self.predecessor_binding.domain != self.HASH_DOMAIN
            )
            or self.schema_version != "doi-kpi-history/v1"
        ):
            raise DoiRetentionError("KPI_CONTRIBUTION_EVENT_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "action_date": self.action_date.isoformat(),
            "action_occurred_at": self.action_occurred_at.value,
            "current_value": self.current_value.to_json_value(),
            "event_id": self.event_id.value,
            "intervention_action_binding": _hash(self.intervention_action_binding),
            "intervention_id": self.intervention_id.value,
            "kind": self.kind.value,
            "predecessor_binding": (
                None
                if self.predecessor_binding is None
                else _hash(self.predecessor_binding)
            ),
            "resulting_link_binding": _hash(self.resulting_link_binding),
            "resulting_link_id": self.resulting_link_id.value,
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "trigger_binding": _hash(self.trigger_binding),
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())


@dataclass(frozen=True, slots=True, init=False, repr=False)
class RetainedKPIContribution:
    intervention_id: EvidenceId
    intervention_type: InterventionType
    intervention_action_binding: HashBinding
    resulting_link_id: EvidenceId
    resulting_link_binding: HashBinding
    action_occurred_at: CanonicalTimestamp
    action_date: date
    current_value: Money
    intervention_count: int
    revision: int
    head_event_binding: HashBinding
    state: KPIContributionState
    schema_version: str

    HASH_DOMAIN: ClassVar[str] = "doi-retained-kpi-contribution/v1"

    def __new__(cls) -> RetainedKPIContribution:
        raise DoiRetentionError("KPI_CONTRIBUTION_REDUCER_REQUIRED")

    @classmethod
    def _from_event(
        cls,
        *,
        intervention_type: InterventionType,
        event: KPIContributionEvent,
    ) -> RetainedKPIContribution:
        instance = object.__new__(cls)
        object.__setattr__(instance, "intervention_id", event.intervention_id)
        object.__setattr__(instance, "intervention_type", intervention_type)
        object.__setattr__(
            instance,
            "intervention_action_binding",
            event.intervention_action_binding,
        )
        object.__setattr__(instance, "resulting_link_id", event.resulting_link_id)
        object.__setattr__(instance, "resulting_link_binding", event.resulting_link_binding)
        object.__setattr__(instance, "action_occurred_at", event.action_occurred_at)
        object.__setattr__(instance, "action_date", event.action_date)
        object.__setattr__(instance, "current_value", event.current_value)
        object.__setattr__(instance, "intervention_count", 1)
        object.__setattr__(instance, "revision", event.sequence)
        object.__setattr__(instance, "head_event_binding", event.hash_binding())
        object.__setattr__(instance, "state", KPIContributionState.RETAINED)
        object.__setattr__(instance, "schema_version", "doi-kpi-history/v1")
        instance.__post_init__()
        return instance

    def __post_init__(self) -> None:
        if (
            type(self.intervention_id) is not EvidenceId
            or self.intervention_type
            not in {
                InterventionType.FULFILLMENT_SPLIT,
                InterventionType.PRODUCT_SUBSTITUTION,
            }
            or type(self.intervention_action_binding) is not HashBinding
            or self.intervention_action_binding.domain != ActionVerificationEvent.HASH_DOMAIN
            or type(self.resulting_link_id) is not EvidenceId
            or type(self.resulting_link_binding) is not HashBinding
            or self.resulting_link_binding.domain != DOIResultingOrderLink.HASH_DOMAIN
            or type(self.action_occurred_at) is not CanonicalTimestamp
            or type(self.action_date) is not date
            or type(self.current_value) is not Money
            or self.intervention_count != 1
            or type(self.revision) is not int
            or self.revision < 1
            or type(self.head_event_binding) is not HashBinding
            or self.head_event_binding.domain != KPIContributionEvent.HASH_DOMAIN
            or self.state is not KPIContributionState.RETAINED
            or self.schema_version != "doi-kpi-history/v1"
        ):
            raise DoiRetentionError("RETAINED_KPI_CONTRIBUTION_INVALID")
        if self.action_date != business_action_date(self.action_occurred_at):
            raise DoiRetentionError("RETAINED_KPI_ACTION_DATE_BINDING_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "action_occurred_at": self.action_occurred_at.value,
            "action_date": self.action_date.isoformat(),
            "current_value": self.current_value.to_json_value(),
            "head_event_binding": _hash(self.head_event_binding),
            "intervention_count": self.intervention_count,
            "intervention_action_binding": _hash(self.intervention_action_binding),
            "intervention_id": self.intervention_id.value,
            "intervention_type": self.intervention_type.value,
            "resulting_link_binding": _hash(self.resulting_link_binding),
            "resulting_link_id": self.resulting_link_id.value,
            "revision": self.revision,
            "schema_version": self.schema_version,
            "state": self.state.value,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "RetainedKPIContribution(<redacted>)"


@dataclass(frozen=True, slots=True)
class KPIContributionHistory:
    intervention_id: EvidenceId
    intervention_type: InterventionType
    projection: RetainedKPIContribution | None = None
    events: tuple[KPIContributionEvent, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.intervention_id) is not EvidenceId
            or self.intervention_type
            not in {
                InterventionType.FULFILLMENT_SPLIT,
                InterventionType.PRODUCT_SUBSTITUTION,
                InterventionType.DS_SEPARATION,
            }
            or type(self.events) is not tuple
            or any(type(item) is not KPIContributionEvent for item in self.events)
        ):
            raise DoiRetentionError("KPI_CONTRIBUTION_HISTORY_INVALID")
        if self.intervention_type is InterventionType.DS_SEPARATION and (
            self.projection is not None or self.events
        ):
            raise DoiRetentionError("KPI_DS_HISTORY_MUST_REMAIN_EMPTY")
        for index, event in enumerate(self.events, start=1):
            predecessor = None if index == 1 else self.events[index - 2].hash_binding()
            if (
                event.intervention_id != self.intervention_id
                or event.sequence != index
                or event.predecessor_binding != predecessor
            ):
                raise DoiRetentionError("KPI_CONTRIBUTION_HISTORY_INVALID")
        if not self.events:
            if self.projection is not None:
                raise DoiRetentionError("KPI_CONTRIBUTION_HISTORY_INVALID")
        elif (
            type(self.projection) is not RetainedKPIContribution
            or self.projection.intervention_id != self.intervention_id
            or self.projection.intervention_type is not self.intervention_type
            or self.projection.revision != len(self.events)
            or self.projection.head_event_binding != self.events[-1].hash_binding()
        ):
            raise DoiRetentionError("KPI_CONTRIBUTION_HISTORY_INVALID")


@dataclass(frozen=True, slots=True)
class KPIContributionDecision:
    contribution: RetainedKPIContribution | None
    reasons: ReasonSet
    history: KPIContributionHistory | None = None
    event: KPIContributionEvent | None = None
    replayed: bool = False


def _kpi_event_kind(event: ValueEvent) -> KPIContributionEventKind:
    if event.event_type is ValueEventType.INITIAL_VERIFIED_VALUE:
        return KPIContributionEventKind.ORIGINAL_VALUE
    if (
        event.event_type is ValueEventType.CORRECTION
        and event.correction_kind is ValueCorrectionKind.ORIGINAL_VALUE_CORRECTED
    ):
        return KPIContributionEventKind.VALUE_CORRECTION
    return KPIContributionEventKind.REVERSAL_RECOMPUTE


def reduce_kpi_contribution(
    history: KPIContributionHistory,
    *,
    event_id: EvidenceId,
    intervention: DOIIntervention,
    resulting_link: DOIResultingOrderLink | None,
    currency_evidence: VerifiedCurrencyEnvelope | None = None,
) -> KPIContributionDecision:
    """Reduce TR-106/TR-109 from retained intervention and value history exactly once."""

    if (
        type(history) is not KPIContributionHistory
        or type(event_id) is not EvidenceId
        or type(intervention) is not DOIIntervention
        or history.intervention_id != intervention.intervention_id
        or history.intervention_type is not intervention.intervention_type
    ):
        raise DoiRetentionError("KPI_REDUCER_INPUT_INVALID")
    if intervention.intervention_type is InterventionType.DS_SEPARATION:
        if resulting_link is not None or currency_evidence is not None:
            raise DoiRetentionError(
                "KPI_DS_SCOPE_NOT_APPLICABLE",
                reasons=_reasons("RC-081"),
            )
        return KPIContributionDecision(None, ReasonSet(), history, None, False)
    reason_codes: list[str] = []
    action_at = intervention.action_occurred_at
    if action_at is None:
        reason_codes.append("RC-099")
    action_binding = intervention.action_events[0].hash_binding()
    if resulting_link is not None and (
        type(resulting_link) is not DOIResultingOrderLink
        or resulting_link.intervention_id != intervention.intervention_id
        or resulting_link.intervention_type is not intervention.intervention_type
        or resulting_link.intervention_action_binding != action_binding
    ):
        raise DoiRetentionError(
            "KPI_RESULTING_LINK_BINDING_INVALID",
            reasons=_reasons("RC-081"),
        )
    if intervention.value.verification is ValueVerificationState.UNVERIFIED:
        reason_codes.append("RC-063")
        if currency_evidence is None:
            value = None
        else:
            if (
                type(currency_evidence) is not VerifiedCurrencyEnvelope
                or currency_evidence.intervention_id != intervention.intervention_id
                or currency_evidence.intervention_action_binding != action_binding
            ):
                raise DoiRetentionError(
                    "KPI_CURRENCY_ENVELOPE_BINDING_INVALID",
                    reasons=_reasons("RC-081"),
                )
            value = currency_evidence.zero_money()
        trigger = action_binding
        kind = KPIContributionEventKind.UNVERIFIED_INITIALIZATION
    else:
        if (
            not intervention.value_events
            or type(intervention.value.net_value) is not Money
        ):
            raise DoiRetentionError("KPI_VERIFIED_VALUE_HISTORY_INVALID")
        trigger_event = intervention.value_events[-1]
        trigger = trigger_event.hash_binding()
        kind = _kpi_event_kind(trigger_event)
        value = intervention.value.net_value
        if currency_evidence is not None:
            raise DoiRetentionError("KPI_CURRENCY_ENVELOPE_NOT_APPLICABLE")
    if intervention.intervention_type is InterventionType.FULFILLMENT_SPLIT:
        rep_verified = (
            type(resulting_link) is DOIResultingOrderLink
            and resulting_link.state
            in {
                ResultingOrderLinkState.AUTO_LINKED,
                ResultingOrderLinkState.HUMAN_CONFIRMED,
            }
            and resulting_link.resulting_order_target_rep_proof is not None
        )
        if not rep_verified:
            reason_codes.append("RC-074")
    else:
        rep_verified = (
            type(resulting_link) is DOIResultingOrderLink
            and resulting_link.state
            in {
                ResultingOrderLinkState.AUTO_LINKED,
                ResultingOrderLinkState.HUMAN_CONFIRMED,
            }
            and all(
                mapping.replacement_line_target_rep_proof is not None
                for mapping in resulting_link.revisions[-1].mappings
            )
        )
        if not rep_verified:
            reason_codes.append("RC-075")
    if not rep_verified and value is not None:
        value = Money.from_minor_units(
            0,
            currency_code=value.currency_code,
            registry_version=value.registry_version,
            scale=value.scale,
        )
    reasons = _reasons(*reason_codes)
    if action_at is None or value is None or resulting_link is None:
        return KPIContributionDecision(None, reasons, history, None, False)

    for retained in history.events:
        if retained.event_id == event_id or retained.trigger_binding == trigger:
            if (
                retained.trigger_binding != trigger
                or retained.current_value != value
                or retained.resulting_link_binding != resulting_link.hash_binding()
            ):
                raise DoiRetentionError(
                    "KPI_CONTRIBUTION_EVENT_CONFLICT",
                    reasons=_reasons("RC-102"),
                )
            return KPIContributionDecision(
                history.projection,
                reasons,
                history,
                retained,
                True,
            )

    represented_value_triggers = tuple(
        event.trigger_binding
        for event in history.events
        if event.kind is not KPIContributionEventKind.UNVERIFIED_INITIALIZATION
    )
    candidate_value_triggers = represented_value_triggers
    if kind is not KPIContributionEventKind.UNVERIFIED_INITIALIZATION:
        candidate_value_triggers = (*candidate_value_triggers, trigger)
    expected_value_triggers = tuple(
        event.hash_binding() for event in intervention.value_events
    )
    if candidate_value_triggers != expected_value_triggers:
        raise DoiRetentionError(
            "KPI_VALUE_HISTORY_GAP",
            reasons=_reasons("RC-111"),
        )
    prior = history.projection
    if prior is not None:
        if (
            prior.intervention_action_binding != action_binding
            or prior.resulting_link_id != resulting_link.link_id
            or prior.action_occurred_at != action_at
            or (
                prior.current_value.currency_code,
                prior.current_value.registry_version,
                prior.current_value.scale,
            )
            != (
                value.currency_code,
                value.registry_version,
                value.scale,
            )
        ):
            raise DoiRetentionError(
                "KPI_BUCKET_IDENTITY_CONFLICT",
                reasons=_reasons("RC-100"),
            )
    event = KPIContributionEvent._create(
        event_id=event_id,
        intervention=intervention,
        resulting_link=resulting_link,
        kind=kind,
        trigger_binding=trigger,
        current_value=value,
        sequence=len(history.events) + 1,
        predecessor_binding=(
            None if not history.events else history.events[-1].hash_binding()
        ),
        factory_capability=_KPI_CONTRIBUTION_TOKEN,
    )
    projection = RetainedKPIContribution._from_event(
        intervention_type=intervention.intervention_type,
        event=event,
    )
    updated = KPIContributionHistory(
        intervention_id=history.intervention_id,
        intervention_type=history.intervention_type,
        projection=projection,
        events=(*history.events, event),
    )
    return KPIContributionDecision(projection, reasons, updated, event, False)


def build_retained_kpi_contribution(
    intervention: DOIIntervention,
    *,
    event_id: EvidenceId,
    resulting_link: DOIResultingOrderLink | None = None,
    currency_evidence: VerifiedCurrencyEnvelope | None = None,
) -> KPIContributionDecision:
    """Initialize one KPI history; updates must use ``reduce_kpi_contribution``."""

    if type(intervention) is not DOIIntervention:
        raise DoiRetentionError("KPI_INTERVENTION_INVALID")
    history = KPIContributionHistory(
        intervention_id=intervention.intervention_id,
        intervention_type=intervention.intervention_type,
    )
    return reduce_kpi_contribution(
        history,
        event_id=event_id,
        intervention=intervention,
        resulting_link=resulting_link,
        currency_evidence=currency_evidence,
    )


@dataclass(frozen=True, slots=True, repr=False)
class NonidentifyingKPIBucket:
    action_date: date
    intervention_type: InterventionType
    current_value: Money
    intervention_count: int
    state: KPIContributionState = KPIContributionState.FINALIZED
    schema_version: str = "doi-nonidentifying-kpi-bucket/v1"

    HASH_DOMAIN: ClassVar[str] = "doi-nonidentifying-kpi-bucket/v1"

    def __post_init__(self) -> None:
        if (
            type(self.action_date) is not date
            or type(self.intervention_type) is not InterventionType
            or type(self.current_value) is not Money
            or type(self.intervention_count) is not int
            or self.intervention_count < 0
            or self.state is not KPIContributionState.FINALIZED
            or self.schema_version != "doi-nonidentifying-kpi-bucket/v1"
        ):
            raise DoiRetentionError("NONIDENTIFYING_KPI_BUCKET_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "action_date": self.action_date.isoformat(),
            "current_value": self.current_value.to_json_value(),
            "intervention_count": self.intervention_count,
            "intervention_type": self.intervention_type.value,
            "schema_version": self.schema_version,
            "state": self.state.value,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "NonidentifyingKPIBucket(<nonidentifying>)"


@dataclass(frozen=True, slots=True, repr=False)
class DOICaseGraph:
    case_id: EvidenceId
    order_id: DoiOrderId
    identity_nodes: tuple[EvidenceId, ...]
    retention: DoiRetentionProjection
    contribution: RetainedKPIContribution | None

    def __post_init__(self) -> None:
        if (
            type(self.case_id) is not EvidenceId
            or type(self.order_id) is not DoiOrderId
            or type(self.identity_nodes) is not tuple
            or any(type(item) is not EvidenceId for item in self.identity_nodes)
            or len(set(self.identity_nodes)) != len(self.identity_nodes)
            or type(self.retention) is not DoiRetentionProjection
            or (
                self.contribution is not None
                and type(self.contribution) is not RetainedKPIContribution
            )
        ):
            raise DoiRetentionError("DOI_CASE_GRAPH_INVALID")
        if self.retention.binding.case_id != self.case_id:
            raise DoiRetentionError("DOI_CASE_GRAPH_RETENTION_INVALID")

    def __repr__(self) -> str:
        return "DOICaseGraph(<redacted>)"


@dataclass(frozen=True, slots=True)
class PurgeResult:
    graph_deleted: bool
    absence_noop: bool
    finalized_bucket: NonidentifyingKPIBucket | None
    reasons: ReasonSet
    removed_identity_count: int

    def __post_init__(self) -> None:
        if (
            type(self.graph_deleted) is not bool
            or type(self.absence_noop) is not bool
            or (
                self.finalized_bucket is not None
                and type(self.finalized_bucket) is not NonidentifyingKPIBucket
            )
            or type(self.reasons) is not ReasonSet
            or type(self.removed_identity_count) is not int
            or self.removed_identity_count < 0
        ):
            raise DoiRetentionError("PURGE_RESULT_INVALID")
        if self.graph_deleted:
            if self.absence_noop or self.removed_identity_count < 2:
                raise DoiRetentionError("PURGE_RESULT_INVALID")
        elif (
            not self.absence_noop
            or self.finalized_bucket is not None
            or self.reasons.reasons
            or self.removed_identity_count != 0
        ):
            raise DoiRetentionError("PURGE_RESULT_INVALID")


def finalize_case_purge(
    graph: DOICaseGraph,
    *,
    now: CanonicalTimestamp,
    existing_bucket: NonidentifyingKPIBucket | None,
    expected_contribution: RetainedKPIContribution | None,
) -> PurgeResult:
    """Purely finalize one exact contribution and return complete graph deletion effects."""

    if type(graph) is not DOICaseGraph or type(now) is not CanonicalTimestamp:
        raise DoiRetentionError("PURGE_INPUT_INVALID")
    deadline = graph.retention.purge_eligible_at
    if deadline is None or _instant(now) < _instant(deadline):
        raise DoiRetentionError("PURGE_NOT_ELIGIBLE", reasons=_reasons("RC-081"))
    if graph.contribution != expected_contribution:
        raise DoiRetentionError("KPI_FINALIZATION_CONFLICT", reasons=_reasons("RC-101"))
    contribution = graph.contribution
    if contribution is None:
        bucket = existing_bucket
        reasons = _reasons("RC-086")
    else:
        if existing_bucket is None:
            bucket = NonidentifyingKPIBucket(
                action_date=contribution.action_date,
                intervention_type=contribution.intervention_type,
                current_value=contribution.current_value,
                intervention_count=contribution.intervention_count,
            )
        else:
            same_identity = (
                existing_bucket.action_date == contribution.action_date
                and existing_bucket.intervention_type is contribution.intervention_type
                and existing_bucket.current_value.currency_code
                == contribution.current_value.currency_code
                and existing_bucket.current_value.registry_version
                == contribution.current_value.registry_version
                and existing_bucket.current_value.scale == contribution.current_value.scale
            )
            if not same_identity:
                raise DoiRetentionError("KPI_BUCKET_IDENTITY_CONFLICT", reasons=_reasons("RC-100"))
            bucket = replace(
                existing_bucket,
                current_value=existing_bucket.current_value + contribution.current_value,
                intervention_count=(
                    existing_bucket.intervention_count + contribution.intervention_count
                ),
            )
        reasons = _reasons("RC-086", "RC-088")
    return PurgeResult(
        graph_deleted=True,
        absence_noop=False,
        finalized_bucket=bucket,
        reasons=reasons,
        removed_identity_count=2 + len(graph.identity_nodes),
    )


class InMemoryDoiRetentionState:
    """One-lock atomic simulation of KPI transfer plus graph deletion."""

    def __init__(self) -> None:
        self._graphs: dict[EvidenceId, DOICaseGraph] = {}
        self._buckets: dict[tuple[date, InterventionType, str], NonidentifyingKPIBucket] = {}
        self._lock = RLock()

    def retain(self, graph: DOICaseGraph) -> None:
        if type(graph) is not DOICaseGraph:
            raise DoiRetentionError("RETENTION_GRAPH_INVALID")
        with self._lock:
            if graph.case_id in self._graphs and self._graphs[graph.case_id] != graph:
                raise DoiRetentionError("RETENTION_GRAPH_CONFLICT")
            updated = dict(self._graphs)
            updated[graph.case_id] = graph
            self._graphs = updated

    def purge(
        self,
        case_id: EvidenceId,
        *,
        now: CanonicalTimestamp,
        expected_contribution: RetainedKPIContribution | None,
        fault_injector: Callable[[PurgeResult], None] | None = None,
    ) -> PurgeResult:
        if type(case_id) is not EvidenceId:
            raise DoiRetentionError("PURGE_CASE_ID_INVALID")
        with self._lock:
            graph = self._graphs.get(case_id)
            if graph is None:
                return PurgeResult(
                    graph_deleted=False,
                    absence_noop=True,
                    finalized_bucket=None,
                    reasons=ReasonSet(),
                    removed_identity_count=0,
                )
            contribution = graph.contribution
            key = (
                None
                if contribution is None
                else (
                    contribution.action_date,
                    contribution.intervention_type,
                    contribution.current_value.currency_code,
                )
            )
            existing = None if key is None else self._buckets.get(key)
            candidate = finalize_case_purge(
                graph,
                now=now,
                existing_bucket=existing,
                expected_contribution=expected_contribution,
            )
            if fault_injector is not None:
                fault_injector(candidate)
            graphs = dict(self._graphs)
            del graphs[case_id]
            buckets = dict(self._buckets)
            if key is not None and candidate.finalized_bucket is not None:
                buckets[key] = candidate.finalized_bucket
            self._graphs = graphs
            self._buckets = buckets
            return candidate

    def graph(self, case_id: EvidenceId) -> DOICaseGraph | None:
        with self._lock:
            return self._graphs.get(case_id)

    @property
    def identity_graph_count(self) -> int:
        with self._lock:
            return len(self._graphs)

    @property
    def buckets(self) -> tuple[NonidentifyingKPIBucket, ...]:
        with self._lock:
            return tuple(self._buckets[key] for key in sorted(self._buckets, key=str))


def retention_hash_contracts() -> dict[str, str]:
    return {
        class_.__name__: class_.HASH_DOMAIN
        for class_ in (
            PriorClosureRetentionBindingV1,
            VerifiedCurrencyEnvelope,
            KPIContributionEvent,
            RetainedKPIContribution,
            NonidentifyingKPIBucket,
        )
    }


def retention_hash_fixtures() -> tuple[tuple[str, str, bytes, str], ...]:
    """Return deterministic representative closure/contribution/bucket KAT records."""

    case_id = EvidenceId("SYN-EVIDENCE-KAT-RETENTION-CASE")
    projection = schedule_retention(
        case_id=case_id,
        closure_event_id=EvidenceId("SYN-EVIDENCE-KAT-RETENTION-CLOSURE"),
        lifecycle_state=CaseLifecycleState.CLOSED_REVERSIBLE,
        closure_reason=TerminalClosureReason.REP_TRANSFERRED,
        closed_at=CanonicalTimestamp("2026-08-20T12:00:00Z"),
        projection_revision=1,
        projection_sha256="a" * 64,
    )
    intervention_records, completed_context, order_source = (
        _intervention_hash_fixture_records()
    )
    intervention = intervention_records["DOIIntervention"]
    resulting_link = intervention_records["DOIResultingOrderLink"]
    if (
        type(intervention) is not DOIIntervention
        or type(resulting_link) is not DOIResultingOrderLink
    ):
        raise DoiRetentionError("RETENTION_HASH_OWNER_FIXTURE_INVALID")
    currency = VerifiedCurrencyEnvelope.from_order_observation(
        evidence_id=EvidenceId("SYN-EVIDENCE-KAT-RETENTION-CURRENCY"),
        intervention=intervention,
        completed_action_context=completed_context,
        currency_code="USD",
        registry_version="synthetic-iso-style-currency-registry/v1",
        scale=2,
        observed_at=CanonicalTimestamp("2026-08-20T14:19:00Z"),
        source=order_source,
    )
    decision = build_retained_kpi_contribution(
        intervention,
        event_id=EvidenceId("SYN-EVIDENCE-KAT-RETENTION-KPI-EVENT"),
        resulting_link=resulting_link,
    )
    contribution = decision.contribution
    contribution_event = decision.event
    if (
        type(contribution) is not RetainedKPIContribution
        or type(contribution_event) is not KPIContributionEvent
    ):
        raise DoiRetentionError("RETENTION_HASH_KPI_FIXTURE_INVALID")
    bucket = NonidentifyingKPIBucket(
        action_date=contribution.action_date,
        intervention_type=contribution.intervention_type,
        current_value=contribution.current_value,
        intervention_count=1,
    )
    records = {
        "PriorClosureRetentionBindingV1": projection.binding,
        "VerifiedCurrencyEnvelope": currency,
        "KPIContributionEvent": contribution_event,
        "RetainedKPIContribution": contribution,
        "NonidentifyingKPIBucket": bucket,
    }
    fixtures = tuple(
        (
            name,
            record.hash_binding().domain,
            record.canonical_bytes(),
            record.hash_binding().sha256,
        )
        for name, record in sorted(records.items())
    )
    contracts = retention_hash_contracts()
    if set(records) != set(contracts) or any(
        records[name].HASH_DOMAIN != domain for name, domain in contracts.items()
    ):
        raise DoiRetentionError("RETENTION_HASH_FIXTURE_INVENTORY_INVALID")
    if RETENTION_HASH_KNOWN_ANSWERS and {
        name: digest for name, _, _, digest in fixtures
    } != dict(RETENTION_HASH_KNOWN_ANSWERS):
        raise DoiRetentionError("RETENTION_HASH_KNOWN_ANSWER_MISMATCH")
    return fixtures


__all__ = [
    "DOI_BUSINESS_TIMEZONE",
    "DOI_RETENTION_POLICY_VERSION",
    "DOI_TIMEZONE_DATABASE_BINDING",
    "DOICaseGraph",
    "DoiRetentionError",
    "DoiRetentionProjection",
    "IdentityRetentionDecision",
    "IdentityRetentionKind",
    "IdentityRetentionState",
    "InMemoryDoiRetentionState",
    "KPIContributionDecision",
    "KPIContributionEvent",
    "KPIContributionEventKind",
    "KPIContributionHistory",
    "NonidentifyingKPIBucket",
    "PriorClosureRetentionBindingV1",
    "PurgeResult",
    "RETENTION_HASH_KNOWN_ANSWERS",
    "RetainedKPIContribution",
    "VerifiedCurrencyEnvelope",
    "build_retained_kpi_contribution",
    "business_action_date",
    "calendar90",
    "cancel_retention_on_reopen",
    "finalize_case_purge",
    "finalize_identity_purge",
    "retention_hash_contracts",
    "retention_hash_fixtures",
    "reduce_kpi_contribution",
    "schedule_retention",
    "schedule_identity_retention",
]
