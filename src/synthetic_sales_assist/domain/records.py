"""Immutable neutral records shared by later synthetic-only workflows.

These envelopes bind versions, canonical bytes, and synthetic identities.  They do not model a
business entity, execute a transition, emit a reason, or persist any workflow state.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar, TypeVar, cast

from synthetic_sales_assist.domain.canonical import (
    HashBinding,
    canonical_json_bytes,
    domain_hash,
    parse_canonical_json_bytes,
)
from synthetic_sales_assist.domain.identities import (
    EvaluationId,
    EvidenceId,
    InteractionId,
    OrderId,
    RunId,
    SkuId,
    SnapshotId,
)
from synthetic_sales_assist.domain.numeric import NonNegativeCount, PositiveOrdinal
from synthetic_sales_assist.domain.registries import ReasonRef
from synthetic_sales_assist.domain.timestamps import (
    CanonicalTimestamp,
    assert_same_canonical_instant,
    timestamps_same_instant,
)
from synthetic_sales_assist.domain.tokens import ImmutableStrEnum


_VERSION_TOKEN = re.compile(
    r"\A[a-z][a-z0-9]*(?:[._/-][a-z0-9]+)*/v[1-9][0-9]*(?:\.[0-9]+)*\Z",
    re.ASCII,
)
_COMPONENT_TOKEN = re.compile(r"\A[a-z][a-z0-9_.-]{0,63}\Z", re.ASCII)
_KIND_TOKEN = re.compile(r"\A[A-Z][A-Z0-9_]{0,63}\Z", re.ASCII)
_SECTION_TOKEN = re.compile(r"\A[A-Z][A-Z0-9_]{0,63}\Z", re.ASCII)
_SNAPSHOT_COMPLETENESS_PROOF_DOMAIN = "shared-snapshot-completeness-proof/v1"


class DomainRecordError(ValueError):
    """Fail closed with a non-sensitive, stable error code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ErrorCategory(ImmutableStrEnum):
    VALIDATION = "VALIDATION"
    VERSION = "VERSION"
    PRIVACY = "PRIVACY"
    CONFLICT = "CONFLICT"
    COLLISION = "COLLISION"


class StructuredErrorCode(ImmutableStrEnum):
    VALUE_REJECTED = "VALUE_REJECTED"
    NATURAL_KEY_NAMESPACE_INVALID = "NATURAL_KEY_NAMESPACE_INVALID"
    NATURAL_KEY_COMPONENTS_INVALID = "NATURAL_KEY_COMPONENTS_INVALID"
    COMMAND_TOKEN_CONSTRUCTION_INVALID = "COMMAND_TOKEN_CONSTRUCTION_INVALID"
    COMMAND_DIGEST_INVALID = "COMMAND_DIGEST_INVALID"
    RECEIPT_ID_INVALID = "RECEIPT_ID_INVALID"
    RECEIPT_TIMESTAMP_INVALID = "RECEIPT_TIMESTAMP_INVALID"
    RECEIPT_RESULT_INVALID = "RECEIPT_RESULT_INVALID"
    RECEIPT_SHAPE_INVALID = "RECEIPT_SHAPE_INVALID"
    REPLAY_OUTCOME_INVALID = "REPLAY_OUTCOME_INVALID"
    IDEMPOTENCY_DOMAIN_INVALID = "IDEMPOTENCY_DOMAIN_INVALID"
    COMMAND_BYTES_INVALID = "COMMAND_BYTES_INVALID"
    DIGEST_FUNCTION_INVALID = "DIGEST_FUNCTION_INVALID"
    DIGEST_FUNCTION_FAILED = "DIGEST_FUNCTION_FAILED"
    IDEMPOTENCY_REQUEST_INVALID = "IDEMPOTENCY_REQUEST_INVALID"
    IDEMPOTENCY_KEY_MATERIAL_CONFLICT = "IDEMPOTENCY_KEY_MATERIAL_CONFLICT"
    IDEMPOTENCY_DIGEST_COLLISION = "IDEMPOTENCY_DIGEST_COLLISION"
    IDEMPOTENCY_REENTRANT_REQUEST = "IDEMPOTENCY_REENTRANT_REQUEST"
    RECEIPT_ALLOCATION_FAILED = "RECEIPT_ALLOCATION_FAILED"
    RECEIPT_ALLOCATION_INVALID = "RECEIPT_ALLOCATION_INVALID"
    NATURAL_KEY_INVALID = "NATURAL_KEY_INVALID"
    IDEMPOTENCY_ERROR_CODE_INVALID = "IDEMPOTENCY_ERROR_CODE_INVALID"


class ErrorPathMember(ImmutableStrEnum):
    PAYLOAD = "payload"
    SCHEMA = "schema"
    IDENTITY = "identity"
    VERSION = "version"
    CONTENT = "content"
    ITEMS = "items"
    SOURCE_REFS = "source_refs"
    TIMESTAMP = "timestamp"


class SourceKind(ImmutableStrEnum):
    SYNTHETIC_ORDER_FIXTURE = "SYNTHETIC_ORDER_FIXTURE"
    SYNTHETIC_PRODUCT_FIXTURE = "SYNTHETIC_PRODUCT_FIXTURE"
    SYNTHETIC_INTERACTION_FIXTURE = "SYNTHETIC_INTERACTION_FIXTURE"


class SourceObjectNamespace(ImmutableStrEnum):
    SYNTHETIC_ORDER = "SYNTHETIC_ORDER"
    SYNTHETIC_PRODUCT = "SYNTHETIC_PRODUCT"
    SYNTHETIC_INTERACTION = "SYNTHETIC_INTERACTION"


class EvaluationDimensionRole(ImmutableStrEnum):
    SUPPLIED_FACTS = "SUPPLIED_FACTS"
    RULES_EVALUATED = "RULES_EVALUATED"
    RULES_FIRED = "RULES_FIRED"
    RESULT = "RESULT"
    PERSISTENCE_EFFECTS = "PERSISTENCE_EFFECTS"


PathMember = ErrorPathMember | int
_ItemT = TypeVar("_ItemT")
_SortKey = str | tuple[str, str]


@dataclass(frozen=True, slots=True)
class StructuredDomainError:
    """A diagnostic-safe error value containing no rejected material."""

    code: StructuredErrorCode
    category: ErrorCategory = ErrorCategory.VALIDATION
    path: tuple[PathMember, ...] = ()
    retryable: bool = False
    schema_version: str = field(default="shared-domain-error/v1", init=False)

    def __post_init__(self) -> None:
        if type(self.code) is not StructuredErrorCode:
            raise DomainRecordError("STRUCTURED_ERROR_CODE_INVALID")
        if type(self.category) is not ErrorCategory:
            raise DomainRecordError("STRUCTURED_ERROR_CATEGORY_INVALID")
        if type(self.path) is not tuple or len(self.path) > 16:
            raise DomainRecordError("STRUCTURED_ERROR_PATH_INVALID")
        for member in self.path:
            enum_member = type(member) is ErrorPathMember
            integer_member = type(member) is int and 0 <= member <= 1_000_000
            if not enum_member and not integer_member:
                raise DomainRecordError("STRUCTURED_ERROR_PATH_INVALID")
        if type(self.retryable) is not bool:
            raise DomainRecordError("STRUCTURED_ERROR_RETRYABLE_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "category": self.category.value,
            "code": self.code.value,
            "path": [
                member.value if type(member) is ErrorPathMember else member
                for member in self.path
            ],
            "retryable": self.retryable,
            "schema_version": self.schema_version,
        }

    def __repr__(self) -> str:
        return (
            "StructuredDomainError("
            f"code={self.code.value}, category={self.category.value}, "
            f"path_length={len(self.path)}, retryable={self.retryable})"
        )


@dataclass(frozen=True, slots=True)
class VersionBinding:
    """Bind a neutral component name to one exact immutable version."""

    component: str
    version: str

    def __post_init__(self) -> None:
        if type(self.component) is not str or _COMPONENT_TOKEN.fullmatch(self.component) is None:
            raise DomainRecordError("VERSION_COMPONENT_INVALID")
        if (
            type(self.version) is not str
            or len(self.version) > 128
            or _VERSION_TOKEN.fullmatch(self.version) is None
        ):
            raise DomainRecordError("VERSION_VALUE_INVALID")

    def to_dict(self) -> dict[str, str]:
        return {"component": self.component, "version": self.version}


def _binding_dict(binding: HashBinding) -> dict[str, str]:
    if type(binding) is not HashBinding:
        raise DomainRecordError("HASH_BINDING_TYPE_INVALID")
    return {"domain": binding.domain, "sha256": binding.sha256}


def _require_hash_binding(binding: object, *, domain: str, code: str) -> None:
    if type(binding) is not HashBinding or binding.domain != domain:
        raise DomainRecordError(code)


def _require_version_binding(
    binding: object,
    *,
    component: str,
    version: str | None,
    code: str,
) -> None:
    if type(binding) is not VersionBinding or binding.component != component:
        raise DomainRecordError(code)
    if version is not None and binding.version != version:
        raise DomainRecordError(code)


def _require_kind(value: object) -> str:
    if type(value) is not str or _KIND_TOKEN.fullmatch(value) is None:
        raise DomainRecordError("RECORD_KIND_INVALID")
    return value


def _require_sorted_unique(
    values: object,
    *,
    item_type: type[_ItemT],
    key: Callable[[_ItemT], _SortKey],
    code: str,
) -> None:
    if type(values) is not tuple or any(type(item) is not item_type for item in values):
        raise DomainRecordError(code)
    typed_values = cast(tuple[_ItemT, ...], values)
    keys = [key(item) for item in typed_values]
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        raise DomainRecordError(code)


@dataclass(frozen=True, slots=True)
class ReasonSet:
    """A duplicate-free, code-ordered tuple of registry-issued reason references."""

    reasons: tuple[ReasonRef, ...] = ()

    def __post_init__(self) -> None:
        _require_sorted_unique(
            self.reasons,
            item_type=ReasonRef,
            key=lambda reason: reason.code,
            code="REASON_SET_INVALID",
        )

    def to_json_value(self) -> list[dict[str, str]]:
        return [
            {
                "code": reason.code,
                "label": reason.label,
                "registry_version": reason.registry_version,
            }
            for reason in self.reasons
        ]


@dataclass(frozen=True, slots=True)
class HumanReviewRequirement:
    """A neutral requirement flag with its complete registry-backed rationale."""

    required: bool
    reasons: ReasonSet

    def __post_init__(self) -> None:
        if type(self.required) is not bool or type(self.reasons) is not ReasonSet:
            raise DomainRecordError("HUMAN_REVIEW_REQUIREMENT_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {"reasons": self.reasons.to_json_value(), "required": self.required}


@dataclass(frozen=True, slots=True)
class SourceRef:
    """A privacy-minimized reference to retained synthetic source material."""

    source_ref_id: EvidenceId
    source_kind: SourceKind
    object_namespace: SourceObjectNamespace
    object_id: OrderId | SkuId | InteractionId
    schema: VersionBinding
    content: HashBinding

    HASH_DOMAIN: ClassVar[str] = "shared-source-ref/v1"
    SCHEMA_VERSION: ClassVar[str] = "shared-source/v1"
    CONTENT_DOMAIN: ClassVar[str] = "shared-source-content/v1"

    @classmethod
    def create(
        cls,
        *,
        source_ref_id: EvidenceId,
        source_kind: SourceKind,
        object_namespace: SourceObjectNamespace,
        object_id: OrderId | SkuId | InteractionId,
    ) -> SourceRef:
        """Build a minimized source locator whose content cannot hide source payload text."""

        if (
            type(source_ref_id) is not EvidenceId
            or type(source_kind) is not SourceKind
            or type(object_namespace) is not SourceObjectNamespace
            or type(object_id) not in {OrderId, SkuId, InteractionId}
        ):
            raise DomainRecordError("SOURCE_REF_OBJECT_INVALID")
        schema = VersionBinding("source", cls.SCHEMA_VERSION)
        content_value = {
            "object_id": object_id.value,
            "object_namespace": object_namespace.value,
            "schema_version": cls.SCHEMA_VERSION,
            "source_kind": source_kind.value,
        }
        content = domain_hash(
            cls.CONTENT_DOMAIN,
            canonical_json_bytes(content_value, expected_members=set(content_value)),
        )
        return cls(
            source_ref_id=source_ref_id,
            source_kind=source_kind,
            object_namespace=object_namespace,
            object_id=object_id,
            schema=schema,
            content=content,
        )

    def __post_init__(self) -> None:
        if type(self.source_ref_id) is not EvidenceId:
            raise DomainRecordError("SOURCE_REF_ID_INVALID")
        if (
            type(self.source_kind) is not SourceKind
            or type(self.object_namespace) is not SourceObjectNamespace
        ):
            raise DomainRecordError("SOURCE_REF_KIND_INVALID")
        expected_identity_type: type[OrderId] | type[SkuId] | type[InteractionId]
        expected_kind: SourceKind
        if self.object_namespace is SourceObjectNamespace.SYNTHETIC_ORDER:
            expected_identity_type = OrderId
            expected_kind = SourceKind.SYNTHETIC_ORDER_FIXTURE
        elif self.object_namespace is SourceObjectNamespace.SYNTHETIC_PRODUCT:
            expected_identity_type = SkuId
            expected_kind = SourceKind.SYNTHETIC_PRODUCT_FIXTURE
        else:
            expected_identity_type = InteractionId
            expected_kind = SourceKind.SYNTHETIC_INTERACTION_FIXTURE
        if (
            type(self.object_id) is not expected_identity_type
            or self.source_kind is not expected_kind
        ):
            raise DomainRecordError("SOURCE_REF_OBJECT_INVALID")
        _require_version_binding(
            self.schema,
            component="source",
            version=self.SCHEMA_VERSION,
            code="SOURCE_REF_BINDING_INVALID",
        )
        _require_hash_binding(
            self.content,
            domain=self.CONTENT_DOMAIN,
            code="SOURCE_REF_BINDING_INVALID",
        )
        expected_content = {
            "object_id": self.object_id.value,
            "object_namespace": self.object_namespace.value,
            "schema_version": self.SCHEMA_VERSION,
            "source_kind": self.source_kind.value,
        }
        expected_bytes = canonical_json_bytes(
            expected_content,
            expected_members=set(expected_content),
        )
        if self.content.canonical_bytes != expected_bytes:
            raise DomainRecordError("SOURCE_REF_CONTENT_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "content": _binding_dict(self.content),
            "object_id": self.object_id.value,
            "object_namespace": self.object_namespace.value,
            "schema": self.schema.to_dict(),
            "source_kind": self.source_kind.value,
            "source_ref_id": self.source_ref_id.value,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), expected_members=set(self.to_dict()))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """Bind one synthetic evidence identity to a source and exact content bytes."""

    evidence_id: EvidenceId
    source: SourceRef
    schema: VersionBinding
    content: HashBinding

    HASH_DOMAIN: ClassVar[str] = "shared-evidence-ref/v1"
    SCHEMA_VERSION: ClassVar[str] = "shared-evidence/v1"
    CONTENT_DOMAIN: ClassVar[str] = "shared-evidence-content/v1"

    def __post_init__(self) -> None:
        if type(self.evidence_id) is not EvidenceId or type(self.source) is not SourceRef:
            raise DomainRecordError("EVIDENCE_REF_ID_INVALID")
        _require_version_binding(
            self.schema,
            component="evidence",
            version=self.SCHEMA_VERSION,
            code="EVIDENCE_REF_BINDING_INVALID",
        )
        _require_hash_binding(
            self.content,
            domain=self.CONTENT_DOMAIN,
            code="EVIDENCE_REF_BINDING_INVALID",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "content": _binding_dict(self.content),
            "evidence_id": self.evidence_id.value,
            "schema": self.schema.to_dict(),
            "source": self.source.to_dict(),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), expected_members=set(self.to_dict()))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())


@dataclass(frozen=True, slots=True)
class ProcessingRunIdentity:
    """Identify a run without defining its state machine or terminal behavior."""

    run_id: RunId
    schema: VersionBinding
    request: HashBinding

    HASH_DOMAIN: ClassVar[str] = "shared-processing-run-identity/v1"
    SCHEMA_VERSION: ClassVar[str] = "shared-run/v1"
    REQUEST_DOMAIN: ClassVar[str] = "shared-run-request/v1"

    def __post_init__(self) -> None:
        if type(self.run_id) is not RunId:
            raise DomainRecordError("PROCESSING_RUN_ID_INVALID")
        _require_version_binding(
            self.schema,
            component="run",
            version=self.SCHEMA_VERSION,
            code="PROCESSING_RUN_BINDING_INVALID",
        )
        _require_hash_binding(
            self.request,
            domain=self.REQUEST_DOMAIN,
            code="PROCESSING_RUN_BINDING_INVALID",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "request": _binding_dict(self.request),
            "run_id": self.run_id.value,
            "schema": self.schema.to_dict(),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), expected_members=set(self.to_dict()))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())


@dataclass(frozen=True, slots=True, repr=False)
class LineManifestEntry:
    """One ordered synthetic line reference inside a completeness proof."""

    line_id: EvidenceId
    ordinal: PositiveOrdinal
    source: SourceRef
    content: HashBinding

    CONTENT_DOMAIN: ClassVar[str] = "shared-snapshot-line-content/v1"

    def __post_init__(self) -> None:
        if (
            type(self.line_id) is not EvidenceId
            or type(self.ordinal) is not PositiveOrdinal
            or type(self.source) is not SourceRef
        ):
            raise DomainRecordError("LINE_MANIFEST_ENTRY_INVALID")
        _require_hash_binding(
            self.content,
            domain=self.CONTENT_DOMAIN,
            code="LINE_MANIFEST_ENTRY_INVALID",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "content": _binding_dict(self.content),
            "line_id": self.line_id.value,
            "ordinal": self.ordinal.to_json_value(),
            "source_ref_id": self.source.source_ref_id.value,
        }

    def __repr__(self) -> str:
        return "LineManifestEntry(<closed>)"


@dataclass(frozen=True, slots=True, repr=False)
class RequiredSectionProof:
    """Prove one required section is readable and every expandable region is exhausted."""

    section: str
    schema: VersionBinding
    exhaustion_strategy: VersionBinding
    source: SourceRef
    observed_at: CanonicalTimestamp
    readable: bool
    hidden_regions_exhausted: bool
    paginated_regions_exhausted: bool
    collapsed_regions_exhausted: bool

    SCHEMA_VERSION: ClassVar[str] = "shared-required-section/v1"
    EXHAUSTION_STRATEGY_VERSION: ClassVar[str] = "shared-section-exhaustion/v1"
    HASH_DOMAIN: ClassVar[str] = "shared-required-section-proof/v1"

    @classmethod
    def complete(
        cls,
        *,
        section: str,
        source: SourceRef,
        observed_at: CanonicalTimestamp,
    ) -> RequiredSectionProof:
        """Build the only section state that may enter a successful completeness proof."""

        return cls(
            section=section,
            schema=VersionBinding("required_section", cls.SCHEMA_VERSION),
            exhaustion_strategy=VersionBinding(
                "section_exhaustion",
                cls.EXHAUSTION_STRATEGY_VERSION,
            ),
            source=source,
            observed_at=observed_at,
            readable=True,
            hidden_regions_exhausted=True,
            paginated_regions_exhausted=True,
            collapsed_regions_exhausted=True,
        )

    def __post_init__(self) -> None:
        if (
            type(self.section) is not str
            or _SECTION_TOKEN.fullmatch(self.section) is None
            or type(self.source) is not SourceRef
            or type(self.observed_at) is not CanonicalTimestamp
        ):
            raise DomainRecordError("REQUIRED_SECTION_PROOF_INVALID")
        _require_version_binding(
            self.schema,
            component="required_section",
            version=self.SCHEMA_VERSION,
            code="REQUIRED_SECTION_PROOF_INVALID",
        )
        _require_version_binding(
            self.exhaustion_strategy,
            component="section_exhaustion",
            version=self.EXHAUSTION_STRATEGY_VERSION,
            code="REQUIRED_SECTION_PROOF_INVALID",
        )
        proof_flags = (
            self.readable,
            self.hidden_regions_exhausted,
            self.paginated_regions_exhausted,
            self.collapsed_regions_exhausted,
        )
        if any(type(flag) is not bool or not flag for flag in proof_flags):
            raise DomainRecordError("REQUIRED_SECTION_INCOMPLETE")

    def to_dict(self) -> dict[str, object]:
        return {
            "collapsed_regions_exhausted": self.collapsed_regions_exhausted,
            "exhaustion_strategy": self.exhaustion_strategy.to_dict(),
            "hidden_regions_exhausted": self.hidden_regions_exhausted,
            "observed_at": self.observed_at.value,
            "paginated_regions_exhausted": self.paginated_regions_exhausted,
            "readable": self.readable,
            "schema": self.schema.to_dict(),
            "section": self.section,
            "source": _binding_dict(self.source.hash_binding()),
            "source_ref_id": self.source.source_ref_id.value,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "RequiredSectionProof(<closed>)"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class WholeOrderCompletenessProof:
    """A closed shared proof value; it performs no extraction or DOI evaluation."""

    requested_order_id: OrderId
    observed_order_id: OrderId
    schema: VersionBinding
    extractor: VersionBinding
    fixture: VersionBinding
    order_source_observed_at: CanonicalTimestamp
    proof_source_observed_at: CanonicalTimestamp
    required_sections: tuple[str, ...]
    section_proofs: tuple[RequiredSectionProof, ...]
    declared_relevant_line_count: NonNegativeCount
    observed_relevant_line_count: NonNegativeCount
    ordered_line_manifest: tuple[LineManifestEntry, ...]
    duplicate_rule: VersionBinding
    reordering_rule: VersionBinding
    source_refs: tuple[SourceRef, ...]
    coherence_state: str
    change_detection_state: str
    empty_universe_proved: bool
    _manifest: HashBinding = field(init=False, repr=False, compare=True)

    HASH_DOMAIN: ClassVar[str] = _SNAPSHOT_COMPLETENESS_PROOF_DOMAIN
    SCHEMA_VERSION: ClassVar[str] = "shared-whole-order-completeness/v1"
    MANIFEST_DOMAIN: ClassVar[str] = "shared-snapshot-line-manifest/v1"
    EXTRACTOR_VERSION: ClassVar[str] = "shared-extractor/v1"
    FIXTURE_VERSION: ClassVar[str] = "shared-fixture/v1"
    DUPLICATE_RULE_VERSION: ClassVar[str] = "shared-duplicate-rule/v1"
    REORDERING_RULE_VERSION: ClassVar[str] = "shared-reordering-rule/v1"
    REQUIRED_SECTIONS: ClassVar[tuple[str, ...]] = (
        "ORDER_IDENTITY",
        "ORDER_FACTS",
        "LINE_ITEMS",
        "WWC_FINDING",
        "DEDUPE_FINDING",
    )

    def __post_init__(self) -> None:
        if (
            type(self.requested_order_id) is not OrderId
            or type(self.observed_order_id) is not OrderId
            or self.requested_order_id != self.observed_order_id
        ):
            raise DomainRecordError("COMPLETENESS_ORDER_IDENTITY_INVALID")
        _require_version_binding(
            self.schema,
            component="whole_order_completeness",
            version=self.SCHEMA_VERSION,
            code="COMPLETENESS_VERSION_INVALID",
        )
        _require_version_binding(
            self.extractor,
            component="extractor",
            version=self.EXTRACTOR_VERSION,
            code="COMPLETENESS_VERSION_INVALID",
        )
        _require_version_binding(
            self.fixture,
            component="fixture",
            version=self.FIXTURE_VERSION,
            code="COMPLETENESS_VERSION_INVALID",
        )
        _require_version_binding(
            self.duplicate_rule,
            component="duplicate_rule",
            version=self.DUPLICATE_RULE_VERSION,
            code="COMPLETENESS_VERSION_INVALID",
        )
        _require_version_binding(
            self.reordering_rule,
            component="reordering_rule",
            version=self.REORDERING_RULE_VERSION,
            code="COMPLETENESS_VERSION_INVALID",
        )
        if (
            type(self.order_source_observed_at) is not CanonicalTimestamp
            or type(self.proof_source_observed_at) is not CanonicalTimestamp
        ):
            raise DomainRecordError("COMPLETENESS_SOURCE_TIME_INVALID")
        source_time_invalid = False
        try:
            assert_same_canonical_instant(
                self.order_source_observed_at,
                self.proof_source_observed_at,
            )
        except ValueError:
            source_time_invalid = True
        if source_time_invalid:
            raise DomainRecordError("COMPLETENESS_SOURCE_TIME_INVALID")
        self._validate_sections_counts_and_sources()
        manifest_value = {
            "entries": [entry.to_dict() for entry in self.ordered_line_manifest],
            "schema_version": self.MANIFEST_DOMAIN,
        }
        manifest_bytes = canonical_json_bytes(
            manifest_value,
            expected_members={"entries", "schema_version"},
        )
        object.__setattr__(
            self,
            "_manifest",
            domain_hash(self.MANIFEST_DOMAIN, manifest_bytes),
        )

    def _validate_sections_counts_and_sources(self) -> None:
        if (
            type(self.required_sections) is not tuple
            or self.required_sections != self.REQUIRED_SECTIONS
        ):
            raise DomainRecordError("COMPLETENESS_SECTIONS_INVALID")
        if (
            type(self.section_proofs) is not tuple
            or any(type(proof) is not RequiredSectionProof for proof in self.section_proofs)
        ):
            raise DomainRecordError("COMPLETENESS_SECTIONS_INVALID")
        if tuple(proof.section for proof in self.section_proofs) != self.required_sections:
            raise DomainRecordError("COMPLETENESS_SECTIONS_INVALID")
        if any(
            not timestamps_same_instant(self.order_source_observed_at, proof.observed_at)
            for proof in self.section_proofs
        ):
            raise DomainRecordError("COMPLETENESS_SECTION_SOURCE_TIME_INVALID")
        if (
            type(self.declared_relevant_line_count) is not NonNegativeCount
            or type(self.observed_relevant_line_count) is not NonNegativeCount
            or self.declared_relevant_line_count != self.observed_relevant_line_count
            or type(self.ordered_line_manifest) is not tuple
            or any(type(entry) is not LineManifestEntry for entry in self.ordered_line_manifest)
            or self.declared_relevant_line_count.value != len(self.ordered_line_manifest)
        ):
            raise DomainRecordError("COMPLETENESS_LINE_COUNT_INVALID")
        expected_ordinals = tuple(range(1, len(self.ordered_line_manifest) + 1))
        actual_ordinals = tuple(entry.ordinal.value for entry in self.ordered_line_manifest)
        line_ids = tuple(entry.line_id.value for entry in self.ordered_line_manifest)
        if actual_ordinals != expected_ordinals or len(line_ids) != len(set(line_ids)):
            raise DomainRecordError("COMPLETENESS_LINE_MANIFEST_INVALID")
        _validate_source_refs(self.source_refs, require_nonempty=True)
        source_by_id = {source.source_ref_id: source for source in self.source_refs}
        allowed_source_kinds = {
            SourceKind.SYNTHETIC_ORDER_FIXTURE,
            SourceKind.SYNTHETIC_PRODUCT_FIXTURE,
        }
        if any(source.source_kind not in allowed_source_kinds for source in self.source_refs):
            raise DomainRecordError("COMPLETENESS_SOURCE_KIND_INVALID")
        if any(
            source_by_id.get(entry.source.source_ref_id) != entry.source
            for entry in self.ordered_line_manifest
        ):
            raise DomainRecordError("COMPLETENESS_LINE_SOURCE_INVALID")
        if any(
            source_by_id.get(section.source.source_ref_id) != section.source
            for section in self.section_proofs
        ):
            raise DomainRecordError("COMPLETENESS_SECTION_SOURCE_INVALID")
        if any(
            section.source.source_kind is not SourceKind.SYNTHETIC_ORDER_FIXTURE
            or section.source.object_namespace
            is not SourceObjectNamespace.SYNTHETIC_ORDER
            or type(section.source.object_id) is not OrderId
            or section.source.object_id != self.requested_order_id
            for section in self.section_proofs
        ):
            raise DomainRecordError("COMPLETENESS_ORDER_SOURCE_INVALID")
        referenced_source_ids = {
            entry.source.source_ref_id for entry in self.ordered_line_manifest
        } | {section.source.source_ref_id for section in self.section_proofs}
        if set(source_by_id) != referenced_source_ids:
            raise DomainRecordError("COMPLETENESS_UNUSED_SOURCE_INVALID")
        if (
            type(self.empty_universe_proved) is not bool
            or self.empty_universe_proved != (not self.ordered_line_manifest)
            or type(self.coherence_state) is not str
            or self.coherence_state != "COHERENT"
            or type(self.change_detection_state) is not str
            or self.change_detection_state != "UNCHANGED"
        ):
            raise DomainRecordError("COMPLETENESS_STATE_INVALID")

    @property
    def manifest_binding(self) -> HashBinding:
        return self._manifest

    def to_dict(self) -> dict[str, object]:
        return {
            "change_detection_state": self.change_detection_state,
            "coherence_state": self.coherence_state,
            "declared_relevant_line_count": self.declared_relevant_line_count.to_json_value(),
            "duplicate_rule": self.duplicate_rule.to_dict(),
            "empty_universe_proved": self.empty_universe_proved,
            "extractor": self.extractor.to_dict(),
            "fixture": self.fixture.to_dict(),
            "line_manifest": [entry.to_dict() for entry in self.ordered_line_manifest],
            "line_manifest_binding": _binding_dict(self.manifest_binding),
            "observed_order_id": self.observed_order_id.value,
            "observed_relevant_line_count": self.observed_relevant_line_count.to_json_value(),
            "order_source_observed_at": self.order_source_observed_at.value,
            "proof_source_observed_at": self.proof_source_observed_at.value,
            "reordering_rule": self.reordering_rule.to_dict(),
            "requested_order_id": self.requested_order_id.value,
            "required_section_bindings": [
                _binding_dict(proof.hash_binding()) for proof in self.section_proofs
            ],
            "required_sections": list(self.required_sections),
            "schema": self.schema.to_dict(),
            "section_proofs": [proof.to_dict() for proof in self.section_proofs],
            "source_refs": [source.to_dict() for source in self.source_refs],
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "WholeOrderCompletenessProof(<closed>)"


def _validate_source_refs(values: object, *, require_nonempty: bool = False) -> None:
    _require_sorted_unique(
        values,
        item_type=SourceRef,
        key=lambda item: item.source_ref_id.value,
        code="SOURCE_REFS_INVALID",
    )
    if require_nonempty and not values:
        raise DomainRecordError("SOURCE_REFS_INVALID")


@dataclass(frozen=True, slots=True, kw_only=True)
class SnapshotEnvelope:
    """Bind a snapshot payload and completeness proof without evaluating either."""

    snapshot_id: SnapshotId
    run_id: RunId
    schema: VersionBinding
    payload: HashBinding
    completeness_proof: WholeOrderCompletenessProof
    source_refs: tuple[SourceRef, ...]

    HASH_DOMAIN: ClassVar[str] = "shared-snapshot-envelope/v1"
    SCHEMA_VERSION: ClassVar[str] = "shared-snapshot/v1"
    PAYLOAD_DOMAIN: ClassVar[str] = "shared-snapshot-payload/v1"
    COMPLETENESS_PROOF_DOMAIN: ClassVar[str] = _SNAPSHOT_COMPLETENESS_PROOF_DOMAIN

    def __post_init__(self) -> None:
        if type(self.snapshot_id) is not SnapshotId or type(self.run_id) is not RunId:
            raise DomainRecordError("SNAPSHOT_ENVELOPE_ID_INVALID")
        _require_version_binding(
            self.schema,
            component="snapshot",
            version=self.SCHEMA_VERSION,
            code="SNAPSHOT_ENVELOPE_BINDING_INVALID",
        )
        _require_hash_binding(
            self.payload,
            domain=self.PAYLOAD_DOMAIN,
            code="SNAPSHOT_ENVELOPE_BINDING_INVALID",
        )
        if type(self.completeness_proof) is not WholeOrderCompletenessProof:
            raise DomainRecordError("SNAPSHOT_ENVELOPE_BINDING_INVALID")
        _validate_source_refs(self.source_refs)
        if self.source_refs != self.completeness_proof.source_refs:
            raise DomainRecordError("SNAPSHOT_ENVELOPE_SOURCE_PROOF_MISMATCH")

    def to_dict(self) -> dict[str, object]:
        return {
            "completeness_proof": _binding_dict(self.completeness_proof.hash_binding()),
            "payload": _binding_dict(self.payload),
            "run_id": self.run_id.value,
            "schema": self.schema.to_dict(),
            "snapshot_id": self.snapshot_id.value,
            "source_refs": [source.to_dict() for source in self.source_refs],
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), expected_members=set(self.to_dict()))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())


def _evaluation_dimension_contract(
    role: EvaluationDimensionRole,
) -> tuple[str, str, str, str, str, bool]:
    if role is EvaluationDimensionRole.SUPPLIED_FACTS:
        return (
            "supplied_facts",
            "shared-evaluation-supplied-facts/v1",
            "supplied_fact",
            "shared-evaluation-supplied-fact-item/v1",
            "shared-evaluation-supplied-fact-content/v1",
            False,
        )
    if role is EvaluationDimensionRole.RULES_EVALUATED:
        return (
            "rules_evaluated",
            "shared-evaluation-rules-evaluated/v1",
            "rule_evaluated",
            "shared-evaluation-rule-evaluated-item/v1",
            "shared-evaluation-rule-evaluated-content/v1",
            False,
        )
    if role is EvaluationDimensionRole.RULES_FIRED:
        return (
            "rules_fired",
            "shared-evaluation-rules-fired/v1",
            "rule_fired",
            "shared-evaluation-rule-fired-item/v1",
            "shared-evaluation-rule-fired-content/v1",
            True,
        )
    if role is EvaluationDimensionRole.RESULT:
        return (
            "result",
            "shared-evaluation-result/v1",
            "result_item",
            "shared-evaluation-result-item/v1",
            "shared-evaluation-result-content/v1",
            False,
        )
    if role is EvaluationDimensionRole.PERSISTENCE_EFFECTS:
        return (
            "persistence_effects",
            "shared-evaluation-persistence-effects/v1",
            "persistence_effect",
            "shared-evaluation-persistence-effect-item/v1",
            "shared-evaluation-persistence-effect-content/v1",
            True,
        )
    raise DomainRecordError("EVALUATION_DIMENSION_ROLE_INVALID")


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class EvaluationExplanationItem:
    """A neutral, enumerable explanation item with a closed role and content binding."""

    item_id: EvidenceId
    role: EvaluationDimensionRole
    schema: VersionBinding
    content: HashBinding

    @classmethod
    def create(
        cls,
        *,
        item_id: EvidenceId,
        role: EvaluationDimensionRole,
        content: HashBinding,
    ) -> EvaluationExplanationItem:
        """Build a role-bound item without exposing private contract literals."""

        _, _, component, version, _, _ = _evaluation_dimension_contract(role)
        return cls(
            item_id=item_id,
            role=role,
            schema=VersionBinding(component, version),
            content=content,
        )

    @classmethod
    def create_from_content(
        cls,
        *,
        item_id: EvidenceId,
        role: EvaluationDimensionRole,
        content_value: object,
        expected_members: set[str] | frozenset[str],
    ) -> EvaluationExplanationItem:
        """Canonicalize a caller's closed neutral item without exposing its hash domain."""

        if (
            type(content_value) is not dict
            or type(expected_members) not in {set, frozenset}
            or not expected_members
        ):
            raise DomainRecordError("EVALUATION_EXPLANATION_CONTENT_INVALID")
        content_domain = _evaluation_dimension_contract(role)[4]
        canonicalization_failed = False
        content_bytes = b""
        try:
            content_bytes = canonical_json_bytes(
                content_value,
                expected_members=expected_members,
            )
        except ValueError:
            canonicalization_failed = True
        if canonicalization_failed:
            raise DomainRecordError("EVALUATION_EXPLANATION_CONTENT_INVALID")
        content = domain_hash(content_domain, content_bytes)
        return cls.create(item_id=item_id, role=role, content=content)

    def __post_init__(self) -> None:
        if type(self.item_id) is not EvidenceId or type(self.role) is not EvaluationDimensionRole:
            raise DomainRecordError("EVALUATION_EXPLANATION_ITEM_INVALID")
        _, _, component, version, content_domain, _ = _evaluation_dimension_contract(
            self.role
        )
        _require_version_binding(
            self.schema,
            component=component,
            version=version,
            code="EVALUATION_EXPLANATION_ITEM_INVALID",
        )
        _require_hash_binding(
            self.content,
            domain=content_domain,
            code="EVALUATION_EXPLANATION_ITEM_INVALID",
        )
        parse_failed = False
        parsed_content: object = None
        try:
            parsed_content = parse_canonical_json_bytes(self.content.canonical_bytes)
        except ValueError:
            parse_failed = True
        if parse_failed or type(parsed_content) is not dict or not parsed_content:
            raise DomainRecordError("EVALUATION_EXPLANATION_CONTENT_INVALID")

    @property
    def content_domain(self) -> str:
        return _evaluation_dimension_contract(self.role)[4]

    def to_dict(self) -> dict[str, object]:
        return {
            "content": _binding_dict(self.content),
            "item_id": self.item_id.value,
            "role": self.role.value,
            "schema": self.schema.to_dict(),
        }

    def __repr__(self) -> str:
        return f"EvaluationExplanationItem(role={self.role.value}, <closed>)"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class EvaluationDimensionBinding:
    """One closed, role-specific explanation list or explicit empty set."""

    role: EvaluationDimensionRole
    schema: VersionBinding
    items: tuple[EvaluationExplanationItem, ...]
    explicitly_empty: bool

    @classmethod
    def create(
        cls,
        *,
        role: EvaluationDimensionRole,
        items: tuple[EvaluationExplanationItem, ...],
    ) -> EvaluationDimensionBinding:
        """Build a dimension with its exact role-derived schema and empty marker."""

        component, version, _, _, _, _ = _evaluation_dimension_contract(role)
        return cls(
            role=role,
            schema=VersionBinding(component, version),
            items=items,
            explicitly_empty=not items,
        )

    def __post_init__(self) -> None:
        if type(self.role) is not EvaluationDimensionRole:
            raise DomainRecordError("EVALUATION_DIMENSION_ROLE_INVALID")
        component, version, _, _, _, allow_empty = _evaluation_dimension_contract(self.role)
        _require_version_binding(
            self.schema,
            component=component,
            version=version,
            code="EVALUATION_DIMENSION_VERSION_INVALID",
        )
        _require_sorted_unique(
            self.items,
            item_type=EvaluationExplanationItem,
            key=lambda item: item.item_id.value,
            code="EVALUATION_DIMENSION_ITEMS_INVALID",
        )
        if len(self.items) > 1024 or any(item.role is not self.role for item in self.items):
            raise DomainRecordError("EVALUATION_DIMENSION_ITEMS_INVALID")
        if (
            type(self.explicitly_empty) is not bool
            or self.explicitly_empty != (not self.items)
            or (self.explicitly_empty and not allow_empty)
        ):
            raise DomainRecordError("EVALUATION_DIMENSION_EMPTY_INVALID")
        if self.role is EvaluationDimensionRole.RESULT and len(self.items) != 1:
            raise DomainRecordError("EVALUATION_DIMENSION_RESULT_CARDINALITY_INVALID")

    @property
    def hash_domain(self) -> str:
        return _evaluation_dimension_contract(self.role)[1]

    @property
    def item_schema_version(self) -> str:
        return _evaluation_dimension_contract(self.role)[3]

    def to_dict(self) -> dict[str, object]:
        return {
            "explicitly_empty": self.explicitly_empty,
            "items": [item.to_dict() for item in self.items],
            "role": self.role.value,
            "schema": self.schema.to_dict(),
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.hash_domain, self.canonical_bytes())

    def __repr__(self) -> str:
        return f"EvaluationDimensionBinding(role={self.role.value})"


def _require_evaluation_dimension(
    value: object,
    role: EvaluationDimensionRole,
) -> EvaluationDimensionBinding:
    if type(value) is not EvaluationDimensionBinding or value.role is not role:
        raise DomainRecordError("EVALUATION_ENVELOPE_INVALID")
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class EvaluationEnvelope:
    """Explain every neutral evaluation dimension without evaluating a business rule."""

    evaluation_id: EvaluationId
    snapshot_id: SnapshotId
    run_id: RunId
    schema: VersionBinding
    rule_pack: VersionBinding
    supplied_facts: EvaluationDimensionBinding
    rules_evaluated: EvaluationDimensionBinding
    rules_fired: EvaluationDimensionBinding
    reasons: ReasonSet
    result: EvaluationDimensionBinding
    human_review: HumanReviewRequirement
    persistence_effects: EvaluationDimensionBinding

    HASH_DOMAIN: ClassVar[str] = "shared-evaluation-envelope/v1"
    SCHEMA_VERSION: ClassVar[str] = "shared-evaluation/v1"
    SUPPLIED_FACTS_DOMAIN: ClassVar[str] = "shared-evaluation-supplied-facts/v1"
    RULES_EVALUATED_DOMAIN: ClassVar[str] = "shared-evaluation-rules-evaluated/v1"
    RULES_FIRED_DOMAIN: ClassVar[str] = "shared-evaluation-rules-fired/v1"
    RESULT_DOMAIN: ClassVar[str] = "shared-evaluation-result/v1"
    PERSISTENCE_EFFECTS_DOMAIN: ClassVar[str] = (
        "shared-evaluation-persistence-effects/v1"
    )

    def __post_init__(self) -> None:
        valid_ids = (
            type(self.evaluation_id) is EvaluationId
            and type(self.snapshot_id) is SnapshotId
            and type(self.run_id) is RunId
        )
        _require_version_binding(
            self.schema,
            component="evaluation",
            version=self.SCHEMA_VERSION,
            code="EVALUATION_ENVELOPE_INVALID",
        )
        _require_version_binding(
            self.rule_pack,
            component="rule_pack",
            version=None,
            code="EVALUATION_ENVELOPE_INVALID",
        )
        _require_evaluation_dimension(
            self.supplied_facts,
            EvaluationDimensionRole.SUPPLIED_FACTS,
        )
        _require_evaluation_dimension(
            self.rules_evaluated,
            EvaluationDimensionRole.RULES_EVALUATED,
        )
        _require_evaluation_dimension(
            self.rules_fired,
            EvaluationDimensionRole.RULES_FIRED,
        )
        _require_evaluation_dimension(
            self.result,
            EvaluationDimensionRole.RESULT,
        )
        _require_evaluation_dimension(
            self.persistence_effects,
            EvaluationDimensionRole.PERSISTENCE_EFFECTS,
        )
        valid_values = (
            type(self.reasons) is ReasonSet
            and type(self.human_review) is HumanReviewRequirement
        )
        evaluated_ids = {item.item_id for item in self.rules_evaluated.items}
        fired_ids = {item.item_id for item in self.rules_fired.items}
        if not valid_ids or not valid_values or not fired_ids.issubset(evaluated_ids):
            raise DomainRecordError("EVALUATION_ENVELOPE_INVALID")

    def to_dict(self) -> dict[str, object]:
        return {
            "evaluation_id": self.evaluation_id.value,
            "human_review": self.human_review.to_dict(),
            "persistence_effects": self.persistence_effects.to_dict(),
            "reasons": self.reasons.to_json_value(),
            "result": self.result.to_dict(),
            "rule_pack": self.rule_pack.to_dict(),
            "rules_evaluated": self.rules_evaluated.to_dict(),
            "rules_fired": self.rules_fired.to_dict(),
            "run_id": self.run_id.value,
            "schema": self.schema.to_dict(),
            "snapshot_id": self.snapshot_id.value,
            "supplied_facts": self.supplied_facts.to_dict(),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), expected_members=set(self.to_dict()))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())


def _validate_versions(values: object) -> None:
    _require_sorted_unique(
        values,
        item_type=VersionBinding,
        key=lambda item: (item.component, item.version),
        code="EVENT_VERSIONS_INVALID",
    )
    components = [item.component for item in values]  # type: ignore[union-attr]
    if len(components) != len(set(components)):
        raise DomainRecordError("EVENT_VERSIONS_INVALID")


@dataclass(frozen=True, slots=True)
class ImmutableEventEnvelope:
    """A generic append-only event envelope with no workflow transition semantics."""

    event_id: InteractionId
    run_id: RunId
    occurred_at: CanonicalTimestamp
    event_kind: str
    schema: VersionBinding
    payload: HashBinding
    versions: tuple[VersionBinding, ...]

    HASH_DOMAIN: ClassVar[str] = "shared-immutable-event-envelope/v1"
    SCHEMA_VERSION: ClassVar[str] = "shared-event/v1"
    PAYLOAD_DOMAIN: ClassVar[str] = "shared-event-payload/v1"

    def __post_init__(self) -> None:
        if type(self.event_id) is not InteractionId or type(self.run_id) is not RunId:
            raise DomainRecordError("EVENT_ID_INVALID")
        if type(self.occurred_at) is not CanonicalTimestamp:
            raise DomainRecordError("EVENT_TIMESTAMP_INVALID")
        _require_kind(self.event_kind)
        _require_version_binding(
            self.schema,
            component="event",
            version=self.SCHEMA_VERSION,
            code="EVENT_BINDING_INVALID",
        )
        _require_hash_binding(
            self.payload,
            domain=self.PAYLOAD_DOMAIN,
            code="EVENT_BINDING_INVALID",
        )
        _validate_versions(self.versions)

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id.value,
            "event_kind": self.event_kind,
            "occurred_at": self.occurred_at.value,
            "payload": _binding_dict(self.payload),
            "run_id": self.run_id.value,
            "schema": self.schema.to_dict(),
            "versions": [binding.to_dict() for binding in self.versions],
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), expected_members=set(self.to_dict()))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())


__all__ = [
    "DomainRecordError",
    "ErrorCategory",
    "ErrorPathMember",
    "EvaluationDimensionBinding",
    "EvaluationDimensionRole",
    "EvaluationExplanationItem",
    "EvaluationEnvelope",
    "EvidenceRef",
    "HashBinding",
    "HumanReviewRequirement",
    "ImmutableEventEnvelope",
    "LineManifestEntry",
    "ProcessingRunIdentity",
    "ReasonSet",
    "RequiredSectionProof",
    "SnapshotEnvelope",
    "SourceKind",
    "SourceObjectNamespace",
    "SourceRef",
    "StructuredDomainError",
    "StructuredErrorCode",
    "VersionBinding",
    "WholeOrderCompletenessProof",
]
