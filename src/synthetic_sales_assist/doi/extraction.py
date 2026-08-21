"""Pure construction of complete synthetic DOI snapshots.

The extractor consumes already supplied in-memory fictional facts.  It deliberately exposes no
browser, file, network, selector, session, or mutation capability.  Missing/unreadable input
fails the extraction; a field-specific ``UNKNOWN`` remains an explicit observed value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import ClassVar, cast

from synthetic_sales_assist.doi.identities import (
    DoiOrderId,
    DoiRunId,
    DoiSnapshotId,
    ExtractionAttemptId,
    LineSnapshotId,
)
from synthetic_sales_assist.doi.models import (
    AttentionCondition,
    ContinuityProofType,
    DOIModelError,
    DOILineItemSnapshot,
    DOIOrderSnapshot,
    DedupeFinding,
    DedupeState,
    LineContinuityProof,
    LineContinuityState,
    SourcePresence,
    WWCFinding,
)
from synthetic_sales_assist.domain.canonical import (
    HashBinding,
    canonical_json_bytes,
    domain_hash,
)
from synthetic_sales_assist.domain.identities import (
    EvidenceId,
    InteractionId,
    OrderId,
    RepId,
    RunId,
    SkuId,
)
from synthetic_sales_assist.domain.numeric import Money, NonNegativeCount, PositiveOrdinal, Quantity
from synthetic_sales_assist.domain.observed import (
    FindingPresenceV2,
    KnownObservedValue,
    NotApplicableObservedValue,
    ObservedTaggedValue,
)
from synthetic_sales_assist.domain.records import (
    DomainRecordError,
    LineManifestEntry,
    ReasonSet,
    RequiredSectionProof,
    SourceKind,
    SourceObjectNamespace,
    SourceRef,
    VersionBinding,
    WholeOrderCompletenessProof,
)
from synthetic_sales_assist.domain.timestamps import (
    CanonicalTimestamp,
    TimestampValidationError,
    timestamps_same_instant,
)
from synthetic_sales_assist.domain.tokens import ImmutableStrEnum


EXTRACTION_SCHEMA_VERSION = "doi-extraction-attempt/v1"
COMPOSITE_CONTINUITY_SCHEMA_VERSION = "doi-line-continuity-composite/v1"
_SECTION = re.compile(r"\A[A-Z][A-Z0-9_]{0,63}\Z", re.ASCII)


class DOIExtractionError(ValueError):
    """A diagnostic-safe extraction adapter or model error."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"DOI extraction rejected: {code}")


class ExtractionStatus(ImmutableStrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


def _reason_set(*codes: str) -> ReasonSet:
    from synthetic_sales_assist.domain.registries import load_doi_registries

    registry = load_doi_registries()
    return ReasonSet(
        tuple(sorted((registry.reason_ref(code) for code in codes), key=lambda ref: ref.code))
    )


def _binding_dict(binding: HashBinding) -> dict[str, str]:
    return {"domain": binding.domain, "sha256": binding.sha256}


def _timestamp(value: object) -> CanonicalTimestamp:
    if type(value) is CanonicalTimestamp:
        return cast(CanonicalTimestamp, value)
    return CanonicalTimestamp(value)


@dataclass(frozen=True, slots=True, repr=False)
class CompositeLineContinuityIdentity:
    """A closed fallback identity; description text is intentionally absent."""

    order_id: OrderId
    source_section: str
    source_ordinal: PositiveOrdinal
    es_number: SkuId | None
    mfg_number: SkuId | None
    ordered_quantity: Quantity
    schema_version: str = COMPOSITE_CONTINUITY_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-line-continuity-composite/v1"

    def __post_init__(self) -> None:
        if (
            type(self.order_id) is not OrderId
            or type(self.source_section) is not str
            or _SECTION.fullmatch(self.source_section) is None
            or type(self.source_ordinal) is not PositiveOrdinal
            or (self.es_number is not None and type(self.es_number) is not SkuId)
            or (self.mfg_number is not None and type(self.mfg_number) is not SkuId)
            or (self.es_number is None and self.mfg_number is None)
            or type(self.ordered_quantity) is not Quantity
            or self.schema_version != COMPOSITE_CONTINUITY_SCHEMA_VERSION
        ):
            raise DOIExtractionError("line_composite_identity")

    def to_dict(self) -> dict[str, object]:
        return {
            "es_number": None if self.es_number is None else self.es_number.value,
            "mfg_number": None if self.mfg_number is None else self.mfg_number.value,
            "order_id": self.order_id.value,
            "ordered_quantity": self.ordered_quantity.to_json_value(),
            "schema_version": self.schema_version,
            "source_ordinal": self.source_ordinal.to_json_value(),
            "source_section": self.source_section,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "CompositeLineContinuityIdentity(<closed>)"


def _known_observed(value: ObservedTaggedValue[object]) -> object | None:
    return value.value if type(value) is KnownObservedValue else None


def build_line_snapshot(
    *,
    line_snapshot_id: LineSnapshotId,
    stable_source_line_id: ObservedTaggedValue[EvidenceId],
    relevant_merchandise: bool,
    activity: ObservedTaggedValue[str],
    drop_ship_state: ObservedTaggedValue[str],
    availability: ObservedTaggedValue[str],
    eta: ObservedTaggedValue[CanonicalTimestamp],
    ordered_quantity: ObservedTaggedValue[Quantity],
    active_quantity: ObservedTaggedValue[Quantity],
    canceled_quantity: ObservedTaggedValue[Quantity],
    explicitly_available_quantity: ObservedTaggedValue[Quantity],
    quantity_availability: ObservedTaggedValue[str],
    es_number: ObservedTaggedValue[SkuId],
    mfg_number: ObservedTaggedValue[SkuId],
    unit_value: ObservedTaggedValue[Money],
    active_line_value: ObservedTaggedValue[Money],
    line_sales_rep: ObservedTaggedValue[RepId],
    source: SourceRef,
    composite_continuity: CompositeLineContinuityIdentity | None = None,
) -> DOILineItemSnapshot:
    """Construct one immutable line and select the strongest legal continuity proof."""

    stable = _known_observed(cast(ObservedTaggedValue[object], stable_source_line_id))
    if type(stable) is EvidenceId:
        continuity = LineContinuityProof(
            LineContinuityState.VERIFIED,
            ContinuityProofType.STABLE_SOURCE_LINE_ID,
            stable,
            None,
        )
    elif composite_continuity is not None:
        if type(composite_continuity) is not CompositeLineContinuityIdentity:
            raise DOIExtractionError("line_composite_identity")
        es = _known_observed(cast(ObservedTaggedValue[object], es_number))
        mfg = _known_observed(cast(ObservedTaggedValue[object], mfg_number))
        quantity = _known_observed(cast(ObservedTaggedValue[object], ordered_quantity))
        if (
            type(source) is not SourceRef
            or source.object_id != composite_continuity.order_id
            or es != composite_continuity.es_number
            or mfg != composite_continuity.mfg_number
            or quantity != composite_continuity.ordered_quantity
        ):
            raise DOIExtractionError("line_composite_fact_mismatch")
        continuity = LineContinuityProof(
            LineContinuityState.VERIFIED,
            ContinuityProofType.CLOSED_COMPOSITE,
            None,
            composite_continuity.hash_binding(),
        )
    else:
        continuity = LineContinuityProof(
            LineContinuityState.UNVERIFIED,
            ContinuityProofType.NONE,
            None,
            None,
        )
    line: DOILineItemSnapshot | None = None
    invalid = False
    try:
        line = DOILineItemSnapshot(
            line_snapshot_id=line_snapshot_id,
            stable_source_line_id=stable_source_line_id,
            relevant_merchandise=relevant_merchandise,
            activity=activity,
            drop_ship_state=drop_ship_state,
            availability=availability,
            eta=eta,
            ordered_quantity=ordered_quantity,
            active_quantity=active_quantity,
            canceled_quantity=canceled_quantity,
            explicitly_available_quantity=explicitly_available_quantity,
            quantity_availability=quantity_availability,
            es_number=es_number,
            mfg_number=mfg_number,
            unit_value=unit_value,
            active_line_value=active_line_value,
            line_sales_rep=line_sales_rep,
            continuity=continuity,
            source=source,
        )
    except DOIModelError:
        invalid = True
    if invalid or line is None:
        raise DOIExtractionError("line_fact_contract")
    return line


def build_wwc_finding(
    *,
    finding_id: EvidenceId,
    presence: FindingPresenceV2,
    author_relation: ObservedTaggedValue[str],
    timing_state: ObservedTaggedValue[str],
    marker: ObservedTaggedValue[str],
    observed_at: ObservedTaggedValue[CanonicalTimestamp],
    source: SourceRef,
) -> WWCFinding:
    """Build direct FindingPresenceV2 with its complete closed nested partition."""

    nested = (author_relation, timing_state, marker, observed_at)
    if presence is FindingPresenceV2.PRESENT and any(
        type(value) is NotApplicableObservedValue for value in nested
    ):
        raise DOIExtractionError("wwc_finding_contract")
    finding: WWCFinding | None = None
    invalid = False
    try:
        finding = WWCFinding(
            finding_id=finding_id,
            presence=presence,
            author_relation=author_relation,
            timing_state=timing_state,
            marker=marker,
            observed_at=observed_at,
            source=source,
        )
    except DOIModelError:
        invalid = True
    if invalid or finding is None:
        raise DOIExtractionError("wwc_finding_contract")
    return finding


def build_dedupe_finding(
    *,
    finding_id: EvidenceId,
    presence: FindingPresenceV2,
    observed_at: object | None,
    state: DedupeState,
    source: SourceRef,
) -> DedupeFinding:
    """Reject a PRESENT finding before adapter success unless its time is constructible."""

    canonical_time: CanonicalTimestamp | None = None
    if presence is FindingPresenceV2.PRESENT:
        invalid_time = False
        try:
            canonical_time = _timestamp(observed_at)
        except (TimestampValidationError, ValueError, TypeError):
            invalid_time = True
        if invalid_time:
            raise DOIExtractionError("dedupe_present_timestamp")
    elif observed_at is not None:
        raise DOIExtractionError("dedupe_nonpresent_timestamp")
    finding: DedupeFinding | None = None
    invalid = False
    try:
        finding = DedupeFinding(
            finding_id=finding_id,
            presence=presence,
            observed_at=canonical_time,
            state=state,
            source=source,
        )
    except DOIModelError:
        invalid = True
    if invalid or finding is None:
        raise DOIExtractionError("dedupe_finding_contract")
    return finding


@dataclass(frozen=True, slots=True, repr=False)
class RequiredSectionObservation:
    section: str
    source: SourceRef
    readable: bool
    hidden_regions_exhausted: bool
    paginated_regions_exhausted: bool
    collapsed_regions_exhausted: bool

    def __post_init__(self) -> None:
        if (
            type(self.section) is not str
            or _SECTION.fullmatch(self.section) is None
            or type(self.source) is not SourceRef
            or any(
                type(value) is not bool
                for value in (
                    self.readable,
                    self.hidden_regions_exhausted,
                    self.paginated_regions_exhausted,
                    self.collapsed_regions_exhausted,
                )
            )
        ):
            raise DOIExtractionError("section_observation_shape")

    @classmethod
    def complete(cls, section: str, source: SourceRef) -> RequiredSectionObservation:
        return cls(section, source, True, True, True, True)


@dataclass(frozen=True, slots=True, repr=False)
class DOIOrderObservedFacts:
    order_state: ObservedTaggedValue[str]
    current_rep_value: ObservedTaggedValue[RepId]
    current_rep_relation: ObservedTaggedValue[str]
    geography_class: ObservedTaggedValue[str]
    payment_condition: ObservedTaggedValue[str]
    order_total: ObservedTaggedValue[Money]
    wwc_finding: WWCFinding
    dedupe_finding: DedupeFinding
    source_presence: SourcePresence = SourcePresence.PRESENT

    def __post_init__(self) -> None:
        if (
            type(self.wwc_finding) is not WWCFinding
            or type(self.dedupe_finding) is not DedupeFinding
            or type(self.source_presence) is not SourcePresence
        ):
            raise DOIExtractionError("order_fact_shape")


@dataclass(frozen=True, slots=True, repr=False)
class DOIExtractionSurface:
    """A finite in-memory read result; raw source times are validated by extraction."""

    attempt_id: ExtractionAttemptId
    run_id: DoiRunId
    snapshot_id: DoiSnapshotId
    requested_order_id: DoiOrderId
    observed_order_id: DoiOrderId | None
    started_at: CanonicalTimestamp
    completed_at: CanonicalTimestamp
    order_source_observed_at: object = field(repr=False)
    proof_source_observed_at: object = field(repr=False)
    sections: tuple[RequiredSectionObservation, ...] | None
    declared_relevant_line_count: object
    lines: tuple[DOILineItemSnapshot, ...] | None
    order_facts: DOIOrderObservedFacts | None
    source_changed: bool
    empty_universe_proved: bool
    extractor_version: str = WholeOrderCompletenessProof.EXTRACTOR_VERSION
    fixture_version: str = WholeOrderCompletenessProof.FIXTURE_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.attempt_id) is not ExtractionAttemptId
            or type(self.run_id) is not DoiRunId
            or type(self.snapshot_id) is not DoiSnapshotId
            or type(self.requested_order_id) is not DoiOrderId
            or (
                self.observed_order_id is not None
                and type(self.observed_order_id) is not DoiOrderId
            )
            or type(self.started_at) is not CanonicalTimestamp
            or type(self.completed_at) is not CanonicalTimestamp
            or type(self.source_changed) is not bool
            or type(self.empty_universe_proved) is not bool
            or type(self.extractor_version) is not str
            or type(self.fixture_version) is not str
        ):
            raise DOIExtractionError("extraction_surface_shape")

    def __repr__(self) -> str:
        return "DOIExtractionSurface(<transient>)"


@dataclass(frozen=True, slots=True)
class DOIExtractionAttempt:
    attempt_id: ExtractionAttemptId
    run_id: DoiRunId
    order_id: DoiOrderId
    started_at: CanonicalTimestamp
    completed_at: CanonicalTimestamp
    status: ExtractionStatus
    snapshot_id: DoiSnapshotId | None
    reasons: ReasonSet
    portal_read_count: NonNegativeCount
    schema_version: str = EXTRACTION_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-extraction-attempt/v1"

    def __post_init__(self) -> None:
        if (
            type(self.attempt_id) is not ExtractionAttemptId
            or type(self.run_id) is not DoiRunId
            or type(self.order_id) is not DoiOrderId
            or type(self.started_at) is not CanonicalTimestamp
            or type(self.completed_at) is not CanonicalTimestamp
            or type(self.status) is not ExtractionStatus
            or type(self.reasons) is not ReasonSet
            or type(self.portal_read_count) is not NonNegativeCount
            or self.portal_read_count.value != 1
            or self.schema_version != EXTRACTION_SCHEMA_VERSION
        ):
            raise DOIExtractionError("extraction_attempt_shape")
        if (self.completed_at.epoch_seconds, self.completed_at.nanosecond) < (
            self.started_at.epoch_seconds,
            self.started_at.nanosecond,
        ):
            raise DOIExtractionError("extraction_attempt_time_order")
        succeeded = self.status is ExtractionStatus.SUCCEEDED
        if succeeded != (type(self.snapshot_id) is DoiSnapshotId):
            raise DOIExtractionError("extraction_attempt_snapshot_partition")
        if succeeded != (not self.reasons.reasons):
            raise DOIExtractionError("extraction_attempt_reason_partition")
        if not succeeded:
            codes = {reason.code for reason in self.reasons.reasons}
            if (
                not {"RC-014", "RC-015"}.issubset(codes)
                or not codes.intersection({"RC-011", "RC-012", "RC-013"})
            ):
                raise DOIExtractionError("extraction_attempt_failure_reasons")

    def to_dict(self) -> dict[str, object]:
        return {
            "attempt_id": self.attempt_id.to_json_value(),
            "completed_at": self.completed_at.value,
            "order_id": self.order_id.to_json_value(),
            "portal_read_count": self.portal_read_count.to_json_value(),
            "reasons": self.reasons.to_json_value(),
            "run_id": self.run_id.to_json_value(),
            "schema_version": self.schema_version,
            "snapshot_id": None if self.snapshot_id is None else self.snapshot_id.to_json_value(),
            "started_at": self.started_at.value,
            "status": self.status.value,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())


@dataclass(frozen=True, slots=True)
class DOIExtractionResult:
    attempt: DOIExtractionAttempt
    snapshot: DOIOrderSnapshot | None
    attention_conditions: tuple[AttentionCondition, ...]

    def __post_init__(self) -> None:
        if (
            type(self.attempt) is not DOIExtractionAttempt
            or (self.snapshot is not None and type(self.snapshot) is not DOIOrderSnapshot)
            or type(self.attention_conditions) is not tuple
            or any(type(item) is not AttentionCondition for item in self.attention_conditions)
        ):
            raise DOIExtractionError("extraction_result_shape")
        succeeded = self.attempt.status is ExtractionStatus.SUCCEEDED
        if succeeded:
            if self.snapshot is None or self.attention_conditions:
                raise DOIExtractionError("extraction_success_result_partition")
        elif self.snapshot is not None or self.attention_conditions != (
            AttentionCondition.RECHECK_REQUIRED,
        ):
            raise DOIExtractionError("extraction_failure_result_partition")


def _failure(surface: DOIExtractionSurface, specific_reason: str) -> DOIExtractionResult:
    reasons = _reason_set(specific_reason, "RC-014", "RC-015")
    attempt = DOIExtractionAttempt(
        attempt_id=surface.attempt_id,
        run_id=surface.run_id,
        order_id=surface.requested_order_id,
        started_at=surface.started_at,
        completed_at=surface.completed_at,
        status=ExtractionStatus.FAILED,
        snapshot_id=None,
        reasons=reasons,
        portal_read_count=NonNegativeCount(1),
    )
    return DOIExtractionResult(
        attempt,
        None,
        (AttentionCondition.RECHECK_REQUIRED,),
    )


def _deduplicated_sorted_sources(sources: tuple[SourceRef, ...]) -> tuple[SourceRef, ...]:
    by_id: dict[str, SourceRef] = {}
    for source in sources:
        prior = by_id.get(source.source_ref_id.value)
        if prior is not None and prior != source:
            raise DOIExtractionError("source_reference_conflict")
        by_id[source.source_ref_id.value] = source
    return tuple(by_id[key] for key in sorted(by_id))


def extract_order_snapshot(surface: DOIExtractionSurface) -> DOIExtractionResult:
    """Validate completeness and return exactly one terminal attempt plus optional snapshot."""

    if type(surface) is not DOIExtractionSurface:
        raise DOIExtractionError("extraction_surface_type")
    if (
        surface.observed_order_id is None
        or surface.observed_order_id != surface.requested_order_id
    ):
        return _failure(surface, "RC-011")
    if surface.order_facts is None or surface.sections is None or surface.lines is None:
        return _failure(surface, "RC-013")
    if (
        surface.extractor_version != WholeOrderCompletenessProof.EXTRACTOR_VERSION
        or surface.fixture_version != WholeOrderCompletenessProof.FIXTURE_VERSION
        or surface.source_changed
    ):
        return _failure(surface, "RC-012")
    try:
        order_time = _timestamp(surface.order_source_observed_at)
        proof_time = _timestamp(surface.proof_source_observed_at)
    except (TimestampValidationError, ValueError, TypeError):
        return _failure(surface, "RC-013")
    if not timestamps_same_instant(order_time, proof_time):
        return _failure(surface, "RC-012")
    section_by_name: dict[str, RequiredSectionObservation] = {}
    for section in surface.sections:
        if type(section) is not RequiredSectionObservation or section.section in section_by_name:
            return _failure(surface, "RC-012")
        section_by_name[section.section] = section
    if set(section_by_name) != set(WholeOrderCompletenessProof.REQUIRED_SECTIONS):
        return _failure(surface, "RC-013")
    ordered_sections = tuple(
        section_by_name[name] for name in WholeOrderCompletenessProof.REQUIRED_SECTIONS
    )
    if any(not section.readable for section in ordered_sections):
        return _failure(surface, "RC-013")
    if any(
        not (
            section.hidden_regions_exhausted
            and section.paginated_regions_exhausted
            and section.collapsed_regions_exhausted
        )
        for section in ordered_sections
    ):
        return _failure(surface, "RC-012")
    if type(surface.declared_relevant_line_count) is not NonNegativeCount:
        return _failure(surface, "RC-012")
    lines = surface.lines
    line_ids = tuple(line.line_snapshot_id.to_json_value() for line in lines)
    if (
        any(type(line) is not DOILineItemSnapshot for line in lines)
        or len(line_ids) != len(set(line_ids))
        or surface.declared_relevant_line_count.value != len(lines)
        or surface.empty_universe_proved != (len(lines) == 0)
    ):
        return _failure(surface, "RC-012")
    requested_order = surface.requested_order_id.value
    facts = surface.order_facts
    all_sources = tuple(section.source for section in ordered_sections) + tuple(
        line.source for line in lines
    )
    sources = _deduplicated_sorted_sources(all_sources)
    if not sources or any(
        source.source_kind is not SourceKind.SYNTHETIC_ORDER_FIXTURE
        or source.object_namespace is not SourceObjectNamespace.SYNTHETIC_ORDER
        or source.object_id != requested_order
        for source in sources
    ):
        return _failure(surface, "RC-012")
    source_ids = {source.source_ref_id for source in sources}
    if (
        facts.wwc_finding.source.source_ref_id not in source_ids
        or facts.dedupe_finding.source.source_ref_id not in source_ids
    ):
        return _failure(surface, "RC-012")
    manifest = tuple(
        LineManifestEntry(
            line.line_snapshot_id.value,
            PositiveOrdinal(index),
            line.source,
            domain_hash(
                LineManifestEntry.CONTENT_DOMAIN,
                canonical_json_bytes(
                    {
                        "line": _binding_dict(line.hash_binding()),
                        "schema_version": "doi-line-manifest-content/v1",
                    },
                    expected_members={"line", "schema_version"},
                ),
            ),
        )
        for index, line in enumerate(lines, start=1)
    )
    try:
        section_proofs = tuple(
            RequiredSectionProof.complete(
                section=section.section,
                source=section.source,
                observed_at=order_time,
            )
            for section in ordered_sections
        )
        proof = WholeOrderCompletenessProof(
            requested_order_id=requested_order,
            observed_order_id=surface.observed_order_id.value,
            schema=VersionBinding(
                "whole_order_completeness",
                WholeOrderCompletenessProof.SCHEMA_VERSION,
            ),
            extractor=VersionBinding("extractor", surface.extractor_version),
            fixture=VersionBinding("fixture", surface.fixture_version),
            order_source_observed_at=order_time,
            proof_source_observed_at=proof_time,
            required_sections=WholeOrderCompletenessProof.REQUIRED_SECTIONS,
            section_proofs=section_proofs,
            declared_relevant_line_count=surface.declared_relevant_line_count,
            observed_relevant_line_count=NonNegativeCount(len(lines)),
            ordered_line_manifest=manifest,
            duplicate_rule=VersionBinding(
                "duplicate_rule", WholeOrderCompletenessProof.DUPLICATE_RULE_VERSION
            ),
            reordering_rule=VersionBinding(
                "reordering_rule", WholeOrderCompletenessProof.REORDERING_RULE_VERSION
            ),
            source_refs=sources,
            coherence_state="COHERENT",
            change_detection_state="UNCHANGED",
            empty_universe_proved=surface.empty_universe_proved,
        )
        snapshot = DOIOrderSnapshot(
            snapshot_id=surface.snapshot_id,
            run_id=surface.run_id,
            order_id=surface.requested_order_id,
            source_observed_at=order_time,
            completeness_proof=proof,
            source_presence=facts.source_presence,
            order_state=facts.order_state,
            current_rep_value=facts.current_rep_value,
            current_rep_relation=facts.current_rep_relation,
            geography_class=facts.geography_class,
            payment_condition=facts.payment_condition,
            order_total=facts.order_total,
            wwc_finding=facts.wwc_finding,
            dedupe_finding=facts.dedupe_finding,
            lines=lines,
        )
    except (DOIModelError, DomainRecordError, ValueError, TypeError):
        return _failure(surface, "RC-012")
    attempt = DOIExtractionAttempt(
        attempt_id=surface.attempt_id,
        run_id=surface.run_id,
        order_id=surface.requested_order_id,
        started_at=surface.started_at,
        completed_at=surface.completed_at,
        status=ExtractionStatus.SUCCEEDED,
        snapshot_id=surface.snapshot_id,
        reasons=ReasonSet(),
        portal_read_count=NonNegativeCount(1),
    )
    return DOIExtractionResult(attempt, snapshot, ())


def extraction_hash_fixture_records() -> tuple[tuple[str, str, bytes, str], ...]:
    """Return representative extraction-owned records for central KAT generation."""

    composite = CompositeLineContinuityIdentity(
        order_id=OrderId("SYN-ORDER-1"),
        source_section="LINE_ITEMS",
        source_ordinal=PositiveOrdinal(1),
        es_number=SkuId("SYN-SKU-ES-1"),
        mfg_number=SkuId("SYN-SKU-MFG-1"),
        ordered_quantity=Quantity(2),
    )
    attempt = DOIExtractionAttempt(
        attempt_id=ExtractionAttemptId(InteractionId("SYN-INTERACTION-DOI-EXTRACT-0001")),
        run_id=DoiRunId(RunId("SYN-RUN-DOI-EXTRACT-0001")),
        order_id=DoiOrderId(OrderId("SYN-ORDER-1")),
        started_at=CanonicalTimestamp("2026-08-10T12:00:00Z"),
        completed_at=CanonicalTimestamp("2026-08-10T12:00:01Z"),
        status=ExtractionStatus.FAILED,
        snapshot_id=None,
        reasons=_reason_set("RC-011", "RC-014", "RC-015"),
        portal_read_count=NonNegativeCount(1),
    )
    records: tuple[tuple[str, object], ...] = (
        ("CompositeLineContinuityIdentity", composite),
        ("DOIExtractionAttempt", attempt),
    )
    return tuple(
        (
            name,
            cast(str, getattr(record, "HASH_DOMAIN")),
            record.canonical_bytes(),
            record.hash_binding().sha256,
        )
        for name, record in records
    )


__all__ = [
    "COMPOSITE_CONTINUITY_SCHEMA_VERSION",
    "CompositeLineContinuityIdentity",
    "DOIExtractionAttempt",
    "DOIExtractionError",
    "DOIExtractionResult",
    "DOIExtractionSurface",
    "DOIOrderObservedFacts",
    "EXTRACTION_SCHEMA_VERSION",
    "ExtractionStatus",
    "RequiredSectionObservation",
    "build_dedupe_finding",
    "build_line_snapshot",
    "build_wwc_finding",
    "extract_order_snapshot",
    "extraction_hash_fixture_records",
]
