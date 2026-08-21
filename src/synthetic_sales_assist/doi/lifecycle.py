"""Pure, registry-backed DOI lifecycle event reduction.

The supplied transition registry is descriptive and contains two historical row shapes.
This module closes those rows into one executable definition type.  A command carries a
registry-issued :class:`TransitionRef`; its target and persistence-neutral effects are
derived here and can never be selected by a caller.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import wraps
from hashlib import sha256
from types import MappingProxyType
from typing import ClassVar

from synthetic_sales_assist.domain.canonical import (
    CanonicalHashCollision,
    HashBinding,
    canonical_json_bytes,
    compare_retained_canonical_bytes,
    domain_hash,
    parse_canonical_json_bytes,
)
from synthetic_sales_assist.domain.identities import EvidenceId
from synthetic_sales_assist.domain.records import ReasonSet
from synthetic_sales_assist.domain.registries import (
    DoiRegistries,
    ReasonRef,
    RegistryLookupError,
    TransitionRef,
    load_doi_registries,
)
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.domain.tokens import ImmutableStrEnum
from synthetic_sales_assist.doi.models import AttentionCondition
from synthetic_sales_assist.safety.content import ProhibitedInputError, assert_payload_safe


LIFECYCLE_SCHEMA_VERSION = "doi-lifecycle/v1"
_STATE_LIMIT = 512
_HEX_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z", re.ASCII)
_COMMAND_TOKEN = object()
_GUARD_PROOF_TOKEN = object()
_GUARD_AUTHORITY_TOKEN = object()
_FIXTURE_AUTHORITY_ISSUER_TOKEN = object()
_OWNING_SERVICE_AUTHORITY_ISSUER_TOKEN = object()


def _typed_owner_evidence_id(*, purpose: str, value: str) -> EvidenceId:
    """Project a non-Evidence typed owner ID into one exact bounded EvidenceId."""

    digest = sha256(f"{purpose}\x00{value}".encode("utf-8")).hexdigest().upper()
    return EvidenceId(f"SYN-EVIDENCE-DOI-{purpose}-{digest}")


def evaluation_transition_stream_id(evaluation: object) -> EvidenceId:
    """Return the only lifecycle stream ID legal for a top-level evaluation."""

    from synthetic_sales_assist.doi.models import DOIEvaluation

    if type(evaluation) is not DOIEvaluation:
        raise LifecycleSchemaError(
            "TRANSITION_EVALUATION_OWNER_INVALID",
            reason=_reason("RC-113"),
        )
    return _typed_owner_evidence_id(
        purpose="EVALUATION",
        value=evaluation.evaluation_id.value,
    )


def evaluation_transition_occurrence_id(evaluation: object) -> EvidenceId:
    """Return the only lifecycle occurrence ID legal for an evaluation result."""

    from synthetic_sales_assist.doi.models import DOIEvaluation

    if type(evaluation) is not DOIEvaluation:
        raise LifecycleSchemaError(
            "TRANSITION_EVALUATION_OWNER_INVALID",
            reason=_reason("RC-113"),
        )
    return _typed_owner_evidence_id(
        purpose="EVALUATION-EVENT",
        value=evaluation.evaluation_id.value,
    )


def observation_deletion_occurrence_id(observation: object) -> EvidenceId:
    """Return the exact deletion occurrence for one retained observation."""

    from synthetic_sales_assist.doi.knowledge import (
        DOIAlternateObservation,
        DOIExactSKUObservation,
    )

    if type(observation) not in {DOIAlternateObservation, DOIExactSKUObservation}:
        raise LifecycleSchemaError(
            "TRANSITION_OBSERVATION_OWNER_INVALID",
            reason=_reason("RC-113"),
        )
    return _typed_owner_evidence_id(
        purpose="OBSERVATION-DELETE",
        value=observation.observation_id.value,
    )


def case_purge_occurrence_id(
    transition: TransitionRef,
    graph: object,
) -> EvidenceId:
    """Return the exact purge occurrence for one retained case graph."""

    from synthetic_sales_assist.doi.retention import DOICaseGraph

    if (
        type(transition) is not TransitionRef
        or transition.transition_id not in {"TR-018", "TR-019", "TR-112"}
        or type(graph) is not DOICaseGraph
    ):
        raise LifecycleSchemaError(
            "TRANSITION_CASE_PURGE_OWNER_INVALID",
            reason=_reason("RC-113"),
        )
    return _typed_owner_evidence_id(
        purpose=f"CASE-PURGE-{transition.transition_id}",
        value=graph.case_id.value,
    )


def identity_retention_stream_id(identity_record: object) -> EvidenceId:
    """Return the exact lifecycle stream for a retained non-case identity graph."""

    from synthetic_sales_assist.doi.source import (
        DOIRejectedSourceRecord,
        DOISourceImportAttempt,
    )

    if type(identity_record) is DOIRejectedSourceRecord:
        owner = identity_record.hash_binding().sha256
        purpose = "REJECTED-SOURCE-RECORD"
    elif type(identity_record) is DOISourceImportAttempt:
        owner = identity_record.attempt_id.to_json_value()
        purpose = "SOURCE-IMPORT-ATTEMPT"
    else:
        raise LifecycleSchemaError(
            "TRANSITION_IDENTITY_OWNER_INVALID",
            reason=_reason("RC-113"),
        )
    return _typed_owner_evidence_id(purpose=purpose, value=owner)


def identity_retention_occurrence_id(
    transition: TransitionRef,
    identity_record: object,
) -> EvidenceId:
    """Return the exact purge occurrence for one identity owner and route."""

    if type(transition) is not TransitionRef or transition.transition_id not in {
        "TR-105",
        "TR-114",
    }:
        raise LifecycleSchemaError(
            "TRANSITION_IDENTITY_OWNER_INVALID",
            reason=_reason("RC-113"),
        )
    owner = identity_retention_stream_id(identity_record)
    return _typed_owner_evidence_id(
        purpose=f"IDENTITY-PURGE-{transition.transition_id}",
        value=owner.value,
    )


def source_batch_release_occurrence_id(source_batch: object) -> EvidenceId:
    """Return the exact owner-release occurrence for one retained source batch."""

    from synthetic_sales_assist.doi.source import DOISourceBatch

    if type(source_batch) is not DOISourceBatch:
        raise LifecycleSchemaError(
            "TRANSITION_SOURCE_BATCH_OWNER_INVALID",
            reason=_reason("RC-113"),
        )
    return _typed_owner_evidence_id(
        purpose="SOURCE-BATCH-RELEASE",
        value=source_batch.batch_id.to_json_value(),
    )


def run_transition_stream_id(run: object) -> EvidenceId:
    """Return the exact lifecycle stream for one reducer-owned DOI run."""

    from synthetic_sales_assist.doi.source import DOIRun

    if type(run) is not DOIRun:
        raise LifecycleSchemaError(
            "TRANSITION_RUN_OWNER_INVALID",
            reason=_reason("RC-113"),
        )
    return _typed_owner_evidence_id(purpose="RUN", value=run.run_id.value)


def run_transition_occurrence_id(run_event: object) -> EvidenceId:
    """Return the exact lifecycle occurrence for one retained run event."""

    from synthetic_sales_assist.doi.source import DOIRunEvent

    if type(run_event) is not DOIRunEvent:
        raise LifecycleSchemaError(
            "TRANSITION_RUN_OWNER_INVALID",
            reason=_reason("RC-113"),
        )
    return _typed_owner_evidence_id(
        purpose="RUN-EVENT",
        value=(
            f"{run_event.run_id.value}:{run_event.sequence.value}:"
            f"{run_event.event_kind.value}"
        ),
    )


def extraction_transition_stream_id(attempt: object) -> EvidenceId:
    """Return the exact lifecycle stream for one extraction reducer output."""

    from synthetic_sales_assist.doi.extraction import DOIExtractionAttempt

    if type(attempt) is not DOIExtractionAttempt:
        raise LifecycleSchemaError(
            "TRANSITION_EXTRACTION_OWNER_INVALID",
            reason=_reason("RC-113"),
        )
    return _typed_owner_evidence_id(
        purpose="EXTRACTION",
        value=attempt.attempt_id.to_json_value(),
    )


def extraction_transition_occurrence_id(attempt: object) -> EvidenceId:
    """Return the exact terminal occurrence for one extraction attempt."""

    from synthetic_sales_assist.doi.extraction import DOIExtractionAttempt

    if type(attempt) is not DOIExtractionAttempt:
        raise LifecycleSchemaError(
            "TRANSITION_EXTRACTION_OWNER_INVALID",
            reason=_reason("RC-113"),
        )
    return _typed_owner_evidence_id(
        purpose="EXTRACTION-EVENT",
        value=f"{attempt.attempt_id.to_json_value()}:{attempt.status.value}",
    )


def source_import_transition_stream_id(attempt: object) -> EvidenceId:
    """Return the exact lifecycle stream for one source-import attempt."""

    from synthetic_sales_assist.doi.source import DOISourceImportAttempt

    if type(attempt) is not DOISourceImportAttempt:
        raise LifecycleSchemaError(
            "TRANSITION_SOURCE_IMPORT_OWNER_INVALID",
            reason=_reason("RC-113"),
        )
    return _typed_owner_evidence_id(
        purpose="SOURCE-IMPORT",
        value=attempt.attempt_id.to_json_value(),
    )


def source_import_event_occurrence_id(event: object) -> EvidenceId:
    """Return the exact occurrence for one retained source-import event."""

    from synthetic_sales_assist.doi.source import DOISourceImportAttemptEvent

    if type(event) is not DOISourceImportAttemptEvent:
        raise LifecycleSchemaError(
            "TRANSITION_SOURCE_IMPORT_OWNER_INVALID",
            reason=_reason("RC-113"),
        )
    return _typed_owner_evidence_id(
        purpose="SOURCE-IMPORT-EVENT",
        value=(
            f"{event.attempt_id.to_json_value()}:{event.sequence.value}:"
            f"{event.event_kind.value}"
        ),
    )


def source_rejection_retention_occurrence_id(
    rejected_record: object,
    terminal_run: object,
) -> EvidenceId:
    """Return the exact scheduling occurrence for one rejected identity graph."""

    from synthetic_sales_assist.doi.source import DOIRejectedSourceRecord, DOIRun

    if (
        type(rejected_record) is not DOIRejectedSourceRecord
        or type(terminal_run) is not DOIRun
        or terminal_run.completed_at is None
    ):
        raise LifecycleSchemaError(
            "TRANSITION_SOURCE_REJECTION_OWNER_INVALID",
            reason=_reason("RC-113"),
        )
    return _typed_owner_evidence_id(
        purpose="SOURCE-REJECTION-RETENTION",
        value=(
            f"{rejected_record.hash_binding().sha256}:"
            f"{terminal_run.run_id.value}:{terminal_run.completed_at.value}"
        ),
    )


def alternate_observation_occurrence_id(observation: object) -> EvidenceId:
    """Return the exact lifecycle occurrence for one immutable observation."""

    from synthetic_sales_assist.doi.knowledge import DOIAlternateObservation

    if type(observation) is not DOIAlternateObservation:
        raise LifecycleSchemaError(
            "TRANSITION_ALTERNATE_OBSERVATION_OWNER_INVALID",
            reason=_reason("RC-113"),
        )
    return _typed_owner_evidence_id(
        purpose="ALTERNATE-OBSERVATION-EVENT",
        value=observation.observation_id.value,
    )


def action_context_event_occurrence_id(event: object) -> EvidenceId:
    """Return the exact retained Action Context event occurrence."""

    from synthetic_sales_assist.doi.models import DOIActionContextEvent

    if type(event) is not DOIActionContextEvent:
        raise LifecycleSchemaError(
            "TRANSITION_ACTION_CONTEXT_EVENT_INVALID",
            reason=_reason("RC-113"),
        )
    return event.event_id


def contact_workflow_event_occurrence_id(event: object) -> EvidenceId:
    """Return the exact retained contact-workflow event occurrence."""

    from synthetic_sales_assist.doi.models import ContactWorkflowEvent

    if type(event) is not ContactWorkflowEvent:
        raise LifecycleSchemaError(
            "TRANSITION_CONTACT_WORKFLOW_EVENT_INVALID",
            reason=_reason("RC-113"),
        )
    return event.event_id


def wwc_event_occurrence_id(event: object) -> EvidenceId:
    """Return the exact retained WWC projection event occurrence."""

    from synthetic_sales_assist.doi.models import DOIWWCEvent

    if type(event) is not DOIWWCEvent:
        raise LifecycleSchemaError(
            "TRANSITION_WWC_EVENT_INVALID",
            reason=_reason("RC-113"),
        )
    return event.event_id


class LifecycleError(RuntimeError):
    """A closed lifecycle rejection that contains no supplied business material."""

    def __init__(self, code: str, *, reason: ReasonRef | None = None) -> None:
        self.code = code
        self.reason = reason
        super().__init__(f"DOI lifecycle rejected: {code}")


class LifecycleSchemaError(LifecycleError):
    """A malformed typed lifecycle payload (RC-113)."""


class LifecycleConflictError(LifecycleError):
    """A natural-key, sequence, predecessor, or state conflict."""


class LifecycleCollisionError(LifecycleConflictError):
    """Equal digest with different retained canonical bytes (RC-103)."""


class TransitionEffectKind(ImmutableStrEnum):
    """A persistence-neutral instruction to apply one exact registered effect row."""

    REGISTERED_EFFECTS = "REGISTERED_EFFECTS"


class AttentionAction(ImmutableStrEnum):
    SET = "SET"
    CLEAR = "CLEAR"


class TransitionGuardVerdict(ImmutableStrEnum):
    """Closed result issued by a domain guard reducer."""

    SATISFIED = "SATISFIED"
    NOT_SATISFIED = "NOT_SATISFIED"


class TransitionGuardAuthorityIssuer(ImmutableStrEnum):
    """Closed issuer class for opaque lifecycle guard capabilities."""

    OWNING_SERVICE = "OWNING_SERVICE"
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"


class TransitionGuardEvidenceKind(ImmutableStrEnum):
    """Closed provenance class for the evidence from which a guard was derived."""

    RUN_CONTROL_REDUCTION = "RUN_CONTROL_REDUCTION"
    EXTRACTION_REDUCTION = "EXTRACTION_REDUCTION"
    SOURCE_IMPORT_REDUCTION = "SOURCE_IMPORT_REDUCTION"
    CASE_OWNER_REDUCTION = "CASE_OWNER_REDUCTION"
    ATTENTION_OWNER_REDUCTION = "ATTENTION_OWNER_REDUCTION"
    PRODUCT_KNOWLEDGE_REDUCTION = "PRODUCT_KNOWLEDGE_REDUCTION"
    CONTACT_WORKFLOW_REDUCTION = "CONTACT_WORKFLOW_REDUCTION"
    WWC_REDUCTION = "WWC_REDUCTION"
    ACTION_CONTEXT_REDUCTION = "ACTION_CONTEXT_REDUCTION"
    EVALUATION_REDUCTION = "EVALUATION_REDUCTION"
    INTERVENTION_REDUCTION = "INTERVENTION_REDUCTION"
    VALUE_REDUCTION = "VALUE_REDUCTION"
    RESULTING_LINK_REDUCTION = "RESULTING_LINK_REDUCTION"
    RESULTING_LINK_SEARCH_REDUCTION = "RESULTING_LINK_SEARCH_REDUCTION"
    KPI_CONTRIBUTION_REDUCTION = "KPI_CONTRIBUTION_REDUCTION"
    HUMAN_REVIEW_EVALUATION = "HUMAN_REVIEW_EVALUATION"
    DEDUPE_REDUCTION = "DEDUPE_REDUCTION"
    HUMAN_FACT_REDUCTION = "HUMAN_FACT_REDUCTION"
    CASE_RECHECK_REDUCTION = "CASE_RECHECK_REDUCTION"
    STRUCTURED_HUMAN_FACT = "STRUCTURED_HUMAN_FACT"
    SYSTEM_ACTION_VERIFICATION = "SYSTEM_ACTION_VERIFICATION"
    HUMAN_ACTION_VERIFICATION = "HUMAN_ACTION_VERIFICATION"
    ACTION_CONTEXT_COMPLETION = "ACTION_CONTEXT_COMPLETION"
    COMPLETE_CLOSURE_EVALUATION = "COMPLETE_CLOSURE_EVALUATION"
    CASE_PURGE_RECONCILIATION = "CASE_PURGE_RECONCILIATION"
    OBSERVATION_GRAPH_DELETION = "OBSERVATION_GRAPH_DELETION"
    IDENTITY_RETENTION_PURGE = "IDENTITY_RETENTION_PURGE"
    SOURCE_BATCH_RELEASE = "SOURCE_BATCH_RELEASE"
    SYNTHETIC_REGISTRY_FIXTURE = "SYNTHETIC_REGISTRY_FIXTURE"


@dataclass(frozen=True, slots=True)
class TransitionDefinition:
    """One closed normalized row from the supplied 115-transition registry."""

    transition: TransitionRef
    section: str
    from_state: str
    to_state: str
    guard: str
    required_effects: str

    def __post_init__(self) -> None:
        if type(self.transition) is not TransitionRef:
            raise LifecycleSchemaError("TRANSITION_REFERENCE_INVALID", reason=_reason("RC-113"))
        for value in (
            self.section,
            self.from_state,
            self.to_state,
            self.guard,
            self.required_effects,
        ):
            if type(value) is not str or not value or len(value) > 8_192:
                raise LifecycleSchemaError(
                    "TRANSITION_DEFINITION_INVALID",
                    reason=_reason("RC-113"),
                )


_TRANSITION_GUARD_FACT_KEYS = MappingProxyType(
    {
        "TR-001": ("human_run_review_accepted", "exactly_one_locked_tab_confirmed"),
        "TR-002": ("coherent_batch_bound", "processing_terminal", "zero_order_exceptions"),
        "TR-003": ("coherent_batch_bound", "processing_terminal", "order_exception_present"),
        "TR-004": (
            "exactly_one_registered_terminal_branch",
            "serialized_run_control_boundary",
            "branch_predecessor_valid",
            "terminal_side_effect_partition_valid",
        ),
        "TR-005": (
            "exact_identity_observed",
            "whole_order_proof_complete",
            "every_relevant_line_captured",
        ),
        "TR-006": ("identity_completeness_or_required_data_failure_proved",),
        "TR-007": (
            "target_rep_order_number_valid",
            "source_batch_safely_bound",
            "no_retained_case_exists",
        ),
        "TR-008": (
            "later_review_succeeded",
            "current_source_admission_safe",
            "no_terminal_closure",
        ),
        "TR-009": ("complete_snapshot", "shipped_proved"),
        "TR-010": ("complete_snapshot", "full_cancellation_proved"),
        "TR-011": ("complete_snapshot", "rep_transfer_proved"),
        "TR-012": ("read_only_recheck_complete", "dedupe_note_proved"),
        "TR-013": ("authorized_human", "out_of_scope_closure_explicit"),
        "TR-014": (
            "recheck_doi_eligibility_proved",
            "prior_closure_binding_complete",
            "prior_closure_binding_matches",
            "prior_deadline_matches_active_deadline",
        ),
        "TR-015": (
            "explicit_recheck_complete",
            "same_reversible_closure_proved",
            "no_doi_eligibility",
        ),
        "TR-016": ("recheck_complete", "shipped_proved"),
        "TR-017": ("recheck_complete", "full_cancellation_proved"),
        "TR-018": (
            "purge_eligible",
            "ledger_guards_pass",
            "bucket_guards_pass",
            "hash_guards_pass",
        ),
        "TR-019": (
            "purge_eligible",
            "deadline_not_canceled",
            "case_not_reopened",
            "tr_112_guards_pass",
        ),
        "TR-020": ("failed_or_incomplete_extraction_event_valid",),
        "TR-021": ("active_case_absent", "absence_event_valid"),
        "TR-022": ("disappearance_verification_incomplete_or_failed",),
        "TR-023": ("disappearance_verification_evaluation_complete",),
        "TR-024": ("later_read_only_extraction_and_evaluation_complete",),
        "TR-025": (
            "accepted_evaluation_exact",
            "changed_condition_detected",
            "action_not_proved",
        ),
        "TR-026": ("verified_action_proved",),
        "TR-027": (
            "snapshot_hash_exact",
            "rules_binding_exact",
            "reason_binding_exact",
            "calendar_binding_exact",
            "relationship_bindings_complete",
            "action_context_bindings_complete",
            "human_fact_usage_bindings_valid",
        ),
        "TR-028": (
            "accepted_evaluation_input_changed",
            "binding_manifest_complete",
            "binding_manifest_registry_valid",
        ),
        "TR-029": ("hard_closure_snapshot_proved",),
        "TR-030": ("reversible_closure_proved",),
        "TR-031": ("active_merchandise_set_complete", "all_active_merchandise_direct_ship"),
        "TR-032": (
            "payment_issue_proved",
            "payment_is_sole_blocker",
            "no_product_opportunity",
        ),
        "TR-033": ("mixed_direct_ship_proved",),
        "TR-034": (
            "split_base_rule_proved",
            "availability_basis_complete",
            "direct_ship_basis_complete",
            "quantity_basis_complete",
        ),
        "TR-035": ("safe_alternate_or_exact_sku_opportunity_proved",),
        "TR-036": (
            "all_active_non_ds_lines_in_stock_full",
            "order_active",
            "order_unshipped",
        ),
        "TR-037": (
            "blocking_uncertainty_present",
            "no_safe_opportunity",
            "no_safe_exclusion",
            "no_safe_closure",
            "no_safe_monitor_conclusion",
        ),
        "TR-038": (
            "active_valid_doi_condition",
            "no_current_opportunity",
            "no_blocking_uncertainty",
        ),
        "TR-039": ("human_review_recorded", "normal_or_out_of_scope_progression"),
        "TR-040": (
            "successor_relationship_explicit_product_only",
            "current_predecessor_exact",
        ),
        "TR-041": (
            "contradictory_evidence_explicit_product_only",
            "current_predecessor_exact",
        ),
        "TR-042": (
            "alternate_observation_succeeded",
            "active_relationship_revision_exact",
            "open_action_context_if_used",
        ),
        "TR-043": ("observation_or_link_graph_due", "applicable_deadline_reached"),
        "TR-044": (
            "deterministic_system_action_proof",
            "completed_human_action_proved",
            "scope_time_key_fingerprint_exact",
        ),
        "TR-045": (
            "structured_human_action_proof_complete",
            "completed_human_action_proved",
            "scope_time_key_fingerprint_exact",
        ),
        "TR-045A": ("completed_ds_separation_verified", "non_credit_scope_exact"),
        "TR-046": (
            "system_verified_original_money_exact",
            "currency_valid",
            "currency_registry_and_scale_identical",
        ),
        "TR-047": ("human_verified_original_money_exact", "human_value_exact"),
        "TR-048": ("correction_or_authority_event_legal", "predecessor_exact"),
        "TR-049": ("reversal_reducer_accepted", "active_reversal_sum_zero"),
        "TR-050": (
            "reversal_reducer_accepted",
            "active_reversal_sum_positive",
            "active_reversal_sum_below_original",
        ),
        "TR-051": ("reversal_reducer_accepted", "active_reversal_sum_equals_original"),
        "TR-052": (
            "reversal_correction_or_void_valid",
            "current_predecessor_exact",
            "natural_key_and_fingerprint_valid",
        ),
        "TR-053": (
            "original_value_correction_accepted_after_reversal",
            "authoritative_predecessor_exact",
        ),
        "TR-054": (
            "parent_type_child_natural_key_exact",
            "deterministic_system_proof_exact",
            "mapping_exact",
        ),
        "TR-055": (
            "authorized_human_mapping_proof_complete",
            "child_exact",
            "mapping_exact",
        ),
        "TR-056": (
            "later_deterministic_resolution_exact",
            "current_conflict_revision_exact",
            "single_mapping_proved",
        ),
        "TR-057": (
            "authorized_human_mapping_resolution_complete",
            "current_conflict_revision_exact",
            "single_mapping_proved",
        ),
        "TR-058": ("same_natural_link_exact", "canonical_mapping_contradiction_proved"),
        "TR-059": (
            "later_system_evidence_exact",
            "evidence_conflict_proved",
            "no_authority_resolution",
        ),
        "TR-060": (
            "evaluation_complete",
            "one_no_solution_analysis_proved",
            "every_dedupe_blocker_absent",
        ),
        "TR-061": (
            "dedupe_approval_fact_complete",
            "candidate_evaluation_review_proof_fingerprint_exact",
            "no_prior_decision",
        ),
        "TR-062": (
            "dedupe_rejection_fact_complete",
            "correction_predecessor_exact_if_correction",
            "rejection_route_legal",
        ),
        "TR-063": ("later_read_only_snapshot_complete", "dedupe_note_proved"),
        "TR-064": ("explicit_dedupe_recheck_complete", "doi_eligibility_returned"),
        "TR-065": ("accepted_evaluation_opportunity_exact", "contact_required_proved"),
        "TR-066": ("actual_contact_attempt_human_recorded",),
        "TR-067": (
            "actual_contact_attempt_human_recorded",
            "attempt_precedes_state_entry",
        ),
        "TR-068": ("awaiting_customer_response_human_recorded",),
        "TR-069": ("explicit_customer_approval_human_recorded",),
        "TR-070": ("customer_decline_human_recorded",),
        "TR-071": ("customer_no_response_human_recorded",),
        "TR-072": ("immediate_customer_approval_human_recorded",),
        "TR-073": ("immediate_customer_decline_human_recorded",),
        "TR-074": ("accepted_evaluation_exact", "no_qualifying_contact"),
        "TR-075": ("latest_qualifying_self_evidence_deterministic",),
        "TR-076": (
            "latest_other_rep_evidence_deterministic",
            "before_protected_until_boundary",
        ),
        "TR-077": ("as_of_instant_exact", "eligibility_boundary_reached"),
        "TR-078": ("accepted_evaluation_exact", "author_time_or_calendar_unresolved"),
        "TR-079": ("new_accepted_binding", "binding_kind_supported"),
        "TR-080": (
            "distinct_later_actual_attempt_human_recorded",
            "same_action_context_open",
        ),
        "TR-081": ("human_withdrawal_or_decline_explicit", "action_not_completed"),
        "TR-082": (
            "product_evidence_explicit_verified_canonical",
            "identity_invariant_passes",
            "type_invariant_passes",
            "privacy_invariant_passes",
        ),
        "TR-083": (
            "product_fact_change_explicit",
            "current_predecessor_exact",
            "relationship_not_terminal",
        ),
        "TR-084": (
            "authorized_human",
            "retained_case_evaluation_opportunity_kind_exact",
        ),
        "TR-085": (
            "current_alternate_observation_succeeded",
            "observation_after_context_creation",
            "case_opportunity_product_revision_match",
        ),
        "TR-086": (
            "same_context_source_accepted",
            "registered_completion_trigger_exact",
            "excluded_completion_triggers_absent",
        ),
        "TR-087": ("abandonment_explicit_or_superseding_attempt_recorded",),
        "TR-088": (
            "resulting_order_search_complete",
            "no_exact_child",
            "prior_candidates_disproved_if_ambiguous",
        ),
        "TR-089": ("unresolved_candidate_set_or_mapping_accepted",),
        "TR-090": ("corroborating_evidence_distinct", "corroboration_agrees_exactly"),
        "TR-091": ("later_system_evidence_exact", "corroboration_agrees_exactly"),
        "TR-092": ("ambiguous_search_or_mapping_conflict_event_exact",),
        "TR-093": (
            "resolver_complete",
            "resolver_subject_matches",
            "active_attention_set_exact",
        ),
        "TR-094": ("uncertain_wwc_event_exact",),
        "TR-095": (
            "resolving_evaluation_or_human_fact_exact",
            "registered_partition_established",
            "wwc_projection_atomic_output",
        ),
        "TR-096": ("new_evaluation_accepted", "blocker_or_opportunity_proved"),
        "TR-097": (
            "authorized_human_fact_complete",
            "fact_kind_result_payload_registered",
        ),
        "TR-098": (
            "initial_invocation_or_retry_legal",
            "attempt_id_fresh",
            "attempt_ordinal_next",
            "attempt_command_token_exact",
        ),
        "TR-099": (
            "source_structure_valid",
            "source_read_coherent",
            "source_identity_calculated",
            "source_batch_binding_safe",
            "target_rep_consolidation_complete",
        ),
        "TR-100": ("registered_terminal_non_success_branch_proved",),
        "TR-101": ("source_digest_unique", "canonical_material_verified"),
        "TR-102": ("matching_source_identity", "canonical_material_byte_identical"),
        "TR-103": (
            "source_import_coherent",
            "order_number_valid",
            "target_rep_occurrence_proved",
            "non_target_rep_occurrence_proved",
        ),
        "TR-104": ("associated_run_terminal",),
        "TR-105": (
            "purge_eligible",
            "record_lock_valid",
            "reference_locks_valid",
            "stream_lock_valid",
        ),
        "TR-106": (
            "exactly_one_intervention_accepted",
            "intervention_keys_valid",
            "split_child_link_exact_if_split",
            "replacement_line_exact_if_swap",
        ),
        "TR-107": (
            "original_value_accepted_exact",
            "currency_and_registry_valid",
            "business_action_date_exact",
        ),
        "TR-108": (
            "value_correction_legal",
            "current_predecessor_exact",
            "authoritative_evidence_exact",
        ),
        "TR-109": (
            "originating_value_transition_accepted",
            "reversal_or_correction_binding_exact",
            "scope_currency_registry_binding_identical",
        ),
        "TR-110": (
            "natural_link_exact",
            "link_proof_exact",
            "canonical_mapping_exact",
            "current_predecessor_exact",
            "resolution_supersession_valid",
        ),
        "TR-111": (
            "same_natural_link_exact",
            "canonical_mapping_contradiction_proved",
            "current_predecessor_exact",
        ),
        "TR-112": (
            "purge_eligible",
            "originating_purge_transition_accepted",
            "optional_contribution_lookup_exact",
            "reconciliation_matches",
            "acid_transaction_ready",
        ),
        "TR-113": (
            "owner_deletion_or_delink_valid",
            "owner_reference_foreign_keys_valid",
            "aggregate_write_set_valid",
            "batch_and_reference_locks_valid",
            "not_exists_checked_after_due_releases",
        ),
        "TR-114": (
            "associated_run_terminal",
            "attempt_outcome_closed",
            "purge_eligible",
            "calendar_deadline_matches",
            "aggregate_finalization_input_exact",
            "attempt_batch_run_locks_valid",
            "owner_and_last_reference_predicates_valid",
        ),
    }
)


def _reason(code: str) -> ReasonRef:
    return load_doi_registries().reason_ref(code)


def _required_text(row: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        candidate = row.get(key)
        if type(candidate) is str and candidate:
            return candidate
    raise LifecycleSchemaError("TRANSITION_REGISTRY_ROW_INVALID", reason=_reason("RC-113"))


def transition_definition(
    transition: TransitionRef, *, registries: DoiRegistries | None = None
) -> TransitionDefinition:
    """Resolve one registry-issued reference into its normalized executable definition."""

    active = registries or load_doi_registries()
    if type(transition) is not TransitionRef:
        raise LifecycleSchemaError("TRANSITION_REFERENCE_INVALID", reason=_reason("RC-113"))
    try:
        row = active.transition_record(transition)
    except RegistryLookupError:
        raise LifecycleConflictError("TRANSITION_UNREGISTERED", reason=_reason("RC-081")) from None
    return TransitionDefinition(
        transition=transition,
        section=_required_text(row, "section"),
        from_state=_required_text(row, "From", "Entity/from"),
        to_state=_required_text(row, "To", "To/action"),
        guard=_required_text(row, "Required guard/evidence", "Deterministic guard/evidence"),
        required_effects=_required_text(
            row,
            "Required effects",
            "Required effects/precedence",
        ),
    )


def recognized_transition_ids() -> tuple[str, ...]:
    """Return the exact closed transition IDs in registry order."""

    return tuple(ref.transition_id for ref in load_doi_registries().transition_refs)


def legal_reason_refs(transition: TransitionRef) -> tuple[ReasonRef, ...]:
    """Return reasons on the effective route owned by ``transition``.

    The evaluator owns the approved implementation-side overlay. Importing it lazily keeps
    this reducer dependent on that one policy authority without mutating the supplied registry.
    """

    from synthetic_sales_assist.doi.evaluator import effective_reason_routes

    registries = load_doi_registries()
    definition = transition_definition(transition, registries=registries)
    del definition
    routes = effective_reason_routes(registries)
    return tuple(
        reason
        for reason in registries.reason_refs
        if transition in routes[reason.code]
        and registries.ownership_record(reason).ownership_mode
        != "ASSERTED_ONLY_UNREACHABLE"
    )


def _state(value: object, code: str) -> str:
    if type(value) is not str or not value or len(value) > _STATE_LIMIT:
        raise LifecycleSchemaError(code, reason=_reason("RC-113"))
    if any(ord(character) < 0x20 for character in value):
        raise LifecycleSchemaError(code, reason=_reason("RC-113"))
    return value


def _sha256_or_none(value: object, code: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str or _HEX_SHA256.fullmatch(value) is None:
        raise LifecycleSchemaError(code, reason=_reason("RC-113"))
    return value


def _hash_dict(value: HashBinding) -> dict[str, str]:
    return {"domain": value.domain, "sha256": value.sha256}


def _registry_text(value: object, code: str) -> str:
    if type(value) is not str or not value or len(value) > 8_192:
        raise LifecycleSchemaError(code, reason=_reason("RC-113"))
    if any(ord(character) < 0x20 and character not in "\t\n\r" for character in value):
        raise LifecycleSchemaError(code, reason=_reason("RC-113"))
    return value


GUARD_AUTHORITY_SCHEMA_VERSION = "doi-transition-guard-authority/v1"


def _guard_authority_value(
    *,
    transition: TransitionRef,
    issuer: TransitionGuardAuthorityIssuer,
    evidence_kind: TransitionGuardEvidenceKind,
    evidence: object,
    satisfied_at: CanonicalTimestamp,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    guard_facts: HashBinding,
) -> dict[str, object]:
    return {
        "authority_schema_version": GUARD_AUTHORITY_SCHEMA_VERSION,
        "evidence": evidence,
        "evidence_kind": evidence_kind.value,
        "guard_facts_binding": _hash_dict(guard_facts),
        "issuer": issuer.value,
        "occurrence_id": occurrence_id.value,
        "satisfied_at": satisfied_at.value,
        "stream_id": stream_id.value,
        "transition_id": transition.transition_id,
    }


@dataclass(frozen=True, slots=True, init=False, repr=False)
class TransitionGuardAuthorityEvidence:
    """Opaque, scope-bound capability issued by a guard-owning service."""

    transition: TransitionRef
    issuer: TransitionGuardAuthorityIssuer
    evidence_kind: TransitionGuardEvidenceKind
    evidence: object = field(repr=False)
    satisfied_at: CanonicalTimestamp
    stream_id: EvidenceId
    occurrence_id: EvidenceId
    guard_facts: HashBinding = field(repr=False)
    _canonical_bytes: bytes = field(repr=False, compare=False)
    _issuer_token: object = field(repr=False, compare=False)

    HASH_DOMAIN: ClassVar[str] = "doi-transition-guard-authority/v1"

    def __new__(cls) -> TransitionGuardAuthorityEvidence:
        raise LifecycleSchemaError(
            "TRANSITION_GUARD_AUTHORITY_CONSTRUCTION_INVALID",
            reason=_reason("RC-113"),
        )

    @classmethod
    def _create(
        cls,
        *,
        transition: TransitionRef,
        issuer: TransitionGuardAuthorityIssuer,
        evidence_kind: TransitionGuardEvidenceKind,
        evidence: object,
        satisfied_at: CanonicalTimestamp,
        stream_id: EvidenceId,
        occurrence_id: EvidenceId,
        guard_facts: HashBinding,
        canonical_bytes: bytes,
        _token: object,
    ) -> TransitionGuardAuthorityEvidence:
        if _token is not _GUARD_AUTHORITY_TOKEN:
            raise LifecycleSchemaError(
                "TRANSITION_GUARD_AUTHORITY_CONSTRUCTION_INVALID",
                reason=_reason("RC-113"),
            )
        instance = object.__new__(cls)
        for name, value in (
            ("transition", transition),
            ("issuer", issuer),
            ("evidence_kind", evidence_kind),
            ("evidence", evidence),
            ("satisfied_at", satisfied_at),
            ("stream_id", stream_id),
            ("occurrence_id", occurrence_id),
            ("guard_facts", guard_facts),
            ("_canonical_bytes", canonical_bytes),
            ("_issuer_token", _token),
        ):
            object.__setattr__(instance, name, value)
        return instance

    def canonical_bytes(self) -> bytes:
        return self._canonical_bytes

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self._canonical_bytes)

    def __repr__(self) -> str:
        return "TransitionGuardAuthorityEvidence(<redacted>)"


def _issue_transition_guard_authority(
    *,
    transition: TransitionRef,
    issuer: TransitionGuardAuthorityIssuer,
    evidence_kind: TransitionGuardEvidenceKind,
    evidence: Mapping[str, object],
    satisfied_at: CanonicalTimestamp,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    guard_facts: HashBinding,
    _issuer_token: object,
) -> TransitionGuardAuthorityEvidence:
    expected_token = {
        TransitionGuardAuthorityIssuer.OWNING_SERVICE: (
            _OWNING_SERVICE_AUTHORITY_ISSUER_TOKEN
        ),
        TransitionGuardAuthorityIssuer.SYNTHETIC_FIXTURE: (
            _FIXTURE_AUTHORITY_ISSUER_TOKEN
        ),
    }.get(issuer)
    if expected_token is None or _issuer_token is not expected_token:
        raise LifecycleSchemaError(
            "TRANSITION_GUARD_AUTHORITY_ISSUER_INVALID",
            reason=_reason("RC-113"),
        )
    definition = transition_definition(transition)
    if (
        type(stream_id) is not EvidenceId
        or type(occurrence_id) is not EvidenceId
        or type(evidence_kind) is not TransitionGuardEvidenceKind
        or type(satisfied_at) is not CanonicalTimestamp
        or type(guard_facts) is not HashBinding
        or guard_facts.domain != "doi-transition-guard-facts/v1"
    ):
        raise LifecycleSchemaError(
            "TRANSITION_GUARD_AUTHORITY_INPUT_INVALID",
            reason=_reason("RC-113"),
        )
    try:
        evidence_bytes = canonical_json_bytes(evidence, expected_members=set(evidence))
        retained_evidence = parse_canonical_json_bytes(evidence_bytes)
    except (ProhibitedInputError, TypeError, ValueError):
        raise LifecycleSchemaError(
            "TRANSITION_GUARD_AUTHORITY_INPUT_INVALID",
            reason=_reason("RC-113"),
        ) from None
    if issuer is TransitionGuardAuthorityIssuer.SYNTHETIC_FIXTURE:
        if evidence_kind is not TransitionGuardEvidenceKind.SYNTHETIC_REGISTRY_FIXTURE:
            raise LifecycleSchemaError(
                "TRANSITION_GUARD_AUTHORITY_EVIDENCE_INVALID",
                reason=_reason("RC-113"),
            )
    elif evidence_kind is TransitionGuardEvidenceKind.SYNTHETIC_REGISTRY_FIXTURE:
        raise LifecycleSchemaError(
            "TRANSITION_GUARD_AUTHORITY_EVIDENCE_INVALID",
            reason=_reason("RC-113"),
        )
    value = _guard_authority_value(
        transition=definition.transition,
        issuer=issuer,
        evidence_kind=evidence_kind,
        evidence=retained_evidence,
        satisfied_at=satisfied_at,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        guard_facts=guard_facts,
    )
    canonical_bytes = canonical_json_bytes(value, expected_members=set(value))
    return TransitionGuardAuthorityEvidence._create(
        transition=definition.transition,
        issuer=issuer,
        evidence_kind=evidence_kind,
        evidence=retained_evidence,
        satisfied_at=satisfied_at,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        guard_facts=guard_facts,
        canonical_bytes=canonical_bytes,
        _token=_GUARD_AUTHORITY_TOKEN,
    )


def _validate_transition_guard_authority(
    authority: object,
    *,
    transition: TransitionRef,
    guard_facts: HashBinding,
) -> TransitionGuardAuthorityEvidence:
    if (
        type(authority) is not TransitionGuardAuthorityEvidence
        or authority._issuer_token is not _GUARD_AUTHORITY_TOKEN
    ):
        raise LifecycleSchemaError(
            "TRANSITION_GUARD_AUTHORITY_REQUIRED",
            reason=_reason("RC-113"),
        )
    if authority.transition != transition or authority.guard_facts != guard_facts:
        raise LifecycleConflictError(
            "TRANSITION_GUARD_AUTHORITY_BINDING_CONFLICT",
            reason=_reason("RC-081"),
        )
    if (
        type(authority.issuer) is not TransitionGuardAuthorityIssuer
        or type(authority.evidence_kind) is not TransitionGuardEvidenceKind
        or not isinstance(authority.evidence, Mapping)
        or type(authority.satisfied_at) is not CanonicalTimestamp
    ):
        raise LifecycleSchemaError(
            "TRANSITION_GUARD_AUTHORITY_INVALID",
            reason=_reason("RC-113"),
        )
    transition_id = transition.transition_id
    if authority.issuer is TransitionGuardAuthorityIssuer.SYNTHETIC_FIXTURE:
        valid_route = (
            authority.evidence_kind
            is TransitionGuardEvidenceKind.SYNTHETIC_REGISTRY_FIXTURE
        )
    else:
        valid_route = transition_id in _OWNING_EVIDENCE_TRANSITION_IDS.get(
            authority.evidence_kind,
            frozenset(),
        )
    if not valid_route:
        raise LifecycleSchemaError(
            "TRANSITION_GUARD_AUTHORITY_EVIDENCE_INVALID",
            reason=_reason("RC-113"),
        )
    expected = _guard_authority_value(
        transition=transition,
        issuer=authority.issuer,
        evidence_kind=authority.evidence_kind,
        evidence=authority.evidence,
        satisfied_at=authority.satisfied_at,
        stream_id=authority.stream_id,
        occurrence_id=authority.occurrence_id,
        guard_facts=guard_facts,
    )
    expected_bytes = canonical_json_bytes(expected, expected_members=set(expected))
    if authority.canonical_bytes() != expected_bytes:
        raise LifecycleSchemaError(
            "TRANSITION_GUARD_AUTHORITY_INVALID",
            reason=_reason("RC-113"),
        )
    return authority


GUARD_FACT_SCHEMA_VERSION = "doi-transition-guard-fact-schema/v1"
_GUARD_FACT_NAME = re.compile(r"\A[a-z][a-z0-9]*(?:_[a-z0-9]+)*\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class TransitionGuardFactSchema:
    """The exact positive propositions required by one registered transition."""

    transition: TransitionRef
    required_facts: tuple[str, ...]
    schema_version: str = GUARD_FACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.transition) is not TransitionRef
            or type(self.required_facts) is not tuple
            or not self.required_facts
            or any(
                type(name) is not str or _GUARD_FACT_NAME.fullmatch(name) is None
                for name in self.required_facts
            )
            or len(self.required_facts) != len(set(self.required_facts))
            or self.schema_version != GUARD_FACT_SCHEMA_VERSION
        ):
            raise LifecycleSchemaError(
                "TRANSITION_GUARD_FACT_SCHEMA_INVALID",
                reason=_reason("RC-113"),
            )


def transition_guard_fact_schema(
    transition: TransitionRef,
) -> TransitionGuardFactSchema:
    """Return the one closed semantic fact schema for a registered transition."""

    definition = transition_definition(transition)
    registered_ids = frozenset(recognized_transition_ids())
    if frozenset(_TRANSITION_GUARD_FACT_KEYS) != registered_ids:
        raise LifecycleSchemaError(
            "TRANSITION_GUARD_SCHEMA_INVENTORY_INVALID",
            reason=_reason("RC-113"),
        )
    required = _TRANSITION_GUARD_FACT_KEYS.get(definition.transition.transition_id)
    if required is None:
        raise LifecycleSchemaError(
            "TRANSITION_GUARD_SCHEMA_UNREGISTERED",
            reason=_reason("RC-113"),
        )
    return TransitionGuardFactSchema(
        transition=definition.transition,
        required_facts=required,
    )


def satisfying_transition_guard_facts(
    transition: TransitionRef,
) -> dict[str, bool]:
    """Build deterministic semantically positive facts for executable registry fixtures."""

    schema = transition_guard_fact_schema(transition)
    return dict.fromkeys(schema.required_facts, True)


def failing_transition_guard_facts(
    transition: TransitionRef,
) -> dict[str, bool]:
    """Build a focused negative by falsifying exactly one required proposition."""

    facts = satisfying_transition_guard_facts(transition)
    first_required = transition_guard_fact_schema(transition).required_facts[0]
    facts[first_required] = False
    return facts


def _closed_guard_facts(
    value: object,
    schema: TransitionGuardFactSchema,
) -> tuple[HashBinding, object, TransitionGuardVerdict]:
    if not isinstance(value, Mapping):
        raise LifecycleSchemaError(
            "TRANSITION_GUARD_FACTS_INVALID",
            reason=_reason("RC-113"),
        )
    invalid = False
    encoded = b""
    closed: dict[object, object] = {}
    try:
        closed = dict(value)
        assert_payload_safe(closed)
    except (ProhibitedInputError, TypeError, ValueError):
        invalid = True
    if invalid:
        raise LifecycleSchemaError(
            "TRANSITION_GUARD_FACTS_INVALID",
            reason=_reason("RC-113"),
        )
    if (
        set(closed) != set(schema.required_facts)
        or any(type(key) is not str for key in closed)
        or any(type(value) is not bool for value in closed.values())
    ):
        raise LifecycleSchemaError(
            "TRANSITION_GUARD_FACT_SCHEMA_INVALID",
            reason=_reason("RC-113"),
        )
    encoded = canonical_json_bytes(
        closed,
        expected_members=set(schema.required_facts),
    )
    verdict = (
        TransitionGuardVerdict.SATISFIED
        if all(closed[name] is True for name in schema.required_facts)
        else TransitionGuardVerdict.NOT_SATISFIED
    )
    return (
        domain_hash("doi-transition-guard-facts/v1", encoded),
        parse_canonical_json_bytes(encoded),
        verdict,
    )


def _guard_proof_value(
    *,
    definition: TransitionDefinition,
    fact_schema: TransitionGuardFactSchema,
    guard_facts: object,
    guard_facts_binding: HashBinding,
    authority_evidence: TransitionGuardAuthorityEvidence,
    verdict: TransitionGuardVerdict,
) -> dict[str, object]:
    return {
        "authority_evidence_binding": _hash_dict(authority_evidence.hash_binding()),
        "from_state": definition.from_state,
        "guard_fact_schema_version": fact_schema.schema_version,
        "guard_facts": guard_facts,
        "guard_facts_binding": _hash_dict(guard_facts_binding),
        "registered_guard": definition.guard,
        "required_effects": definition.required_effects,
        "required_guard_facts": list(fact_schema.required_facts),
        "schema_version": LIFECYCLE_SCHEMA_VERSION,
        "section": definition.section,
        "to_state": definition.to_state,
        "transition_id": definition.transition.transition_id,
        "transition_registry_version": definition.transition.registry_version,
        "verdict": verdict.value,
    }


@dataclass(frozen=True, slots=True, init=False, repr=False)
class TransitionGuardProof:
    """Registry-bound, canonical proof of one domain guard result.

    The public factory derives and validates every registry member.  A proof cannot be
    constructed directly, rebound to another transition, or reduced to a caller Boolean.
    """

    transition: TransitionRef
    section: str
    from_state: str
    to_state: str
    registered_guard: str
    required_effects: str
    fact_schema: TransitionGuardFactSchema
    guard_facts: HashBinding = field(repr=False)
    authority_evidence: TransitionGuardAuthorityEvidence = field(repr=False)
    verdict: TransitionGuardVerdict
    _canonical_bytes: bytes = field(repr=False, compare=False)
    _issuer_token: object = field(repr=False, compare=False)

    HASH_DOMAIN: ClassVar[str] = "doi-transition-guard-proof/v1"

    def __new__(cls) -> TransitionGuardProof:
        raise LifecycleSchemaError(
            "TRANSITION_GUARD_PROOF_CONSTRUCTION_INVALID",
            reason=_reason("RC-113"),
        )

    @classmethod
    def _create(
        cls,
        *,
        definition: TransitionDefinition,
        fact_schema: TransitionGuardFactSchema,
        guard_facts: HashBinding,
        authority_evidence: TransitionGuardAuthorityEvidence,
        verdict: TransitionGuardVerdict,
        canonical_bytes: bytes,
        _token: object,
    ) -> TransitionGuardProof:
        if _token is not _GUARD_PROOF_TOKEN:
            raise LifecycleSchemaError(
                "TRANSITION_GUARD_PROOF_CONSTRUCTION_INVALID",
                reason=_reason("RC-113"),
            )
        instance = object.__new__(cls)
        for name, value in (
            ("transition", definition.transition),
            ("section", definition.section),
            ("from_state", definition.from_state),
            ("to_state", definition.to_state),
            ("registered_guard", definition.guard),
            ("required_effects", definition.required_effects),
            ("fact_schema", fact_schema),
            ("guard_facts", guard_facts),
            ("authority_evidence", authority_evidence),
            ("verdict", verdict),
            ("_canonical_bytes", canonical_bytes),
            ("_issuer_token", _token),
        ):
            object.__setattr__(instance, name, value)
        return instance

    @property
    def satisfied(self) -> bool:
        return self.verdict is TransitionGuardVerdict.SATISFIED

    def canonical_bytes(self) -> bytes:
        return self._canonical_bytes

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self._canonical_bytes)

    def __repr__(self) -> str:
        return "TransitionGuardProof(<redacted>)"


def make_transition_guard_proof(
    *,
    transition: TransitionRef,
    from_state: str,
    expected_to_state: str,
    registered_guard: str,
    required_effects: str,
    guard_facts: Mapping[str, object],
    authority_evidence: TransitionGuardAuthorityEvidence | None = None,
) -> TransitionGuardProof:
    """Evaluate facts presented with an opaque guard-owner capability."""

    definition = transition_definition(transition)
    claimed_from = _state(from_state, "TRANSITION_GUARD_FROM_STATE_INVALID")
    claimed_to = _state(expected_to_state, "TRANSITION_GUARD_TARGET_INVALID")
    claimed_guard = _registry_text(
        registered_guard,
        "TRANSITION_REGISTERED_GUARD_INVALID",
    )
    claimed_effects = _registry_text(
        required_effects,
        "TRANSITION_REGISTERED_EFFECTS_INVALID",
    )
    if claimed_from != definition.from_state:
        raise LifecycleConflictError(
            "TRANSITION_GUARD_FROM_STATE_CONFLICT",
            reason=_reason("RC-081"),
        )
    if claimed_to != definition.to_state:
        raise LifecycleConflictError(
            "TRANSITION_GUARD_TARGET_CONFLICT",
            reason=_reason("RC-081"),
        )
    if claimed_guard != definition.guard:
        raise LifecycleConflictError(
            "TRANSITION_REGISTERED_GUARD_CONFLICT",
            reason=_reason("RC-081"),
        )
    if claimed_effects != definition.required_effects:
        raise LifecycleConflictError(
            "TRANSITION_REGISTERED_EFFECTS_CONFLICT",
            reason=_reason("RC-081"),
        )
    fact_schema = transition_guard_fact_schema(transition)
    facts_binding, facts_value, verdict = _closed_guard_facts(
        guard_facts,
        fact_schema,
    )
    checked_authority = _validate_transition_guard_authority(
        authority_evidence,
        transition=definition.transition,
        guard_facts=facts_binding,
    )
    value = _guard_proof_value(
        definition=definition,
        fact_schema=fact_schema,
        guard_facts=facts_value,
        guard_facts_binding=facts_binding,
        authority_evidence=checked_authority,
        verdict=verdict,
    )
    proof_bytes = canonical_json_bytes(value, expected_members=set(value))
    return TransitionGuardProof._create(
        definition=definition,
        fact_schema=fact_schema,
        guard_facts=facts_binding,
        authority_evidence=checked_authority,
        verdict=verdict,
        canonical_bytes=proof_bytes,
        _token=_GUARD_PROOF_TOKEN,
    )


_CLOSURE_EVIDENCE_TRANSITION_IDS = frozenset(
    {
        "TR-009",
        "TR-010",
        "TR-011",
        "TR-012",
        "TR-016",
        "TR-017",
        "TR-029",
        "TR-030",
    }
)
_OWNING_EVIDENCE_TRANSITION_IDS = MappingProxyType(
    {
        TransitionGuardEvidenceKind.RUN_CONTROL_REDUCTION: frozenset(
            {"TR-001", "TR-002", "TR-003", "TR-004"}
        ),
        TransitionGuardEvidenceKind.EXTRACTION_REDUCTION: frozenset(
            {"TR-005", "TR-006"}
        ),
        TransitionGuardEvidenceKind.SOURCE_IMPORT_REDUCTION: frozenset(
            {
                "TR-098",
                "TR-099",
                "TR-100",
                "TR-101",
                "TR-102",
                "TR-103",
                "TR-104",
            }
        ),
        TransitionGuardEvidenceKind.CASE_OWNER_REDUCTION: frozenset(
            {"TR-007", "TR-008"}
        ),
        TransitionGuardEvidenceKind.ATTENTION_OWNER_REDUCTION: frozenset(
            {
                "TR-020",
                "TR-021",
                "TR-022",
                "TR-023",
                "TR-024",
                "TR-025",
                "TR-026",
                "TR-092",
                "TR-093",
                "TR-094",
                "TR-095",
            }
        ),
        TransitionGuardEvidenceKind.PRODUCT_KNOWLEDGE_REDUCTION: frozenset(
            {"TR-040", "TR-041", "TR-042", "TR-082", "TR-083"}
        ),
        TransitionGuardEvidenceKind.CONTACT_WORKFLOW_REDUCTION: frozenset(
            {
                "TR-065",
                "TR-066",
                "TR-067",
                "TR-068",
                "TR-069",
                "TR-070",
                "TR-071",
                "TR-072",
                "TR-073",
                "TR-080",
                "TR-081",
            }
        ),
        TransitionGuardEvidenceKind.WWC_REDUCTION: frozenset(
            {"TR-074", "TR-075", "TR-076", "TR-077", "TR-078", "TR-079"}
        ),
        TransitionGuardEvidenceKind.ACTION_CONTEXT_REDUCTION: frozenset(
            {"TR-084", "TR-085", "TR-087"}
        ),
        TransitionGuardEvidenceKind.EVALUATION_REDUCTION: frozenset(
            {
                "TR-027",
                "TR-028",
                "TR-031",
                "TR-032",
                "TR-033",
                "TR-034",
                "TR-035",
                "TR-036",
                "TR-037",
                "TR-038",
            }
        ),
        TransitionGuardEvidenceKind.VALUE_REDUCTION: frozenset(
            {
                "TR-046",
                "TR-047",
                "TR-048",
                "TR-049",
                "TR-050",
                "TR-051",
                "TR-052",
                "TR-053",
            }
        ),
        TransitionGuardEvidenceKind.INTERVENTION_REDUCTION: frozenset(
            {"TR-045A"}
        ),
        TransitionGuardEvidenceKind.RESULTING_LINK_REDUCTION: frozenset(
            {
                "TR-054",
                "TR-055",
                "TR-056",
                "TR-057",
                "TR-058",
                "TR-059",
                "TR-090",
                "TR-091",
                "TR-110",
                "TR-111",
            }
        ),
        TransitionGuardEvidenceKind.RESULTING_LINK_SEARCH_REDUCTION: frozenset(
            {"TR-088", "TR-089"}
        ),
        TransitionGuardEvidenceKind.KPI_CONTRIBUTION_REDUCTION: frozenset(
            {"TR-106", "TR-107", "TR-108", "TR-109"}
        ),
        TransitionGuardEvidenceKind.HUMAN_REVIEW_EVALUATION: frozenset(
            {"TR-039"}
        ),
        TransitionGuardEvidenceKind.DEDUPE_REDUCTION: frozenset(
            {"TR-060", "TR-061", "TR-062", "TR-063", "TR-064", "TR-096"}
        ),
        TransitionGuardEvidenceKind.HUMAN_FACT_REDUCTION: frozenset({"TR-097"}),
        TransitionGuardEvidenceKind.CASE_RECHECK_REDUCTION: frozenset(
            {"TR-014", "TR-015"}
        ),
        TransitionGuardEvidenceKind.STRUCTURED_HUMAN_FACT: frozenset({"TR-013"}),
        TransitionGuardEvidenceKind.SYSTEM_ACTION_VERIFICATION: frozenset({"TR-044"}),
        TransitionGuardEvidenceKind.HUMAN_ACTION_VERIFICATION: frozenset({"TR-045"}),
        TransitionGuardEvidenceKind.ACTION_CONTEXT_COMPLETION: frozenset({"TR-086"}),
        TransitionGuardEvidenceKind.COMPLETE_CLOSURE_EVALUATION: (
            _CLOSURE_EVIDENCE_TRANSITION_IDS
        ),
        TransitionGuardEvidenceKind.CASE_PURGE_RECONCILIATION: frozenset(
            {"TR-018", "TR-019", "TR-112"}
        ),
        TransitionGuardEvidenceKind.OBSERVATION_GRAPH_DELETION: frozenset({"TR-043"}),
        TransitionGuardEvidenceKind.IDENTITY_RETENTION_PURGE: frozenset(
            {"TR-105", "TR-114"}
        ),
        TransitionGuardEvidenceKind.SOURCE_BATCH_RELEASE: frozenset({"TR-113"}),
    }
)
_PROTECTED_TRANSITION_IDS = frozenset(
    transition_id
    for transition_ids in _OWNING_EVIDENCE_TRANSITION_IDS.values()
    for transition_id in transition_ids
)


def protected_transition_ids() -> tuple[str, ...]:
    """Return routes whose production guards require concrete owning evidence."""

    return tuple(
        transition_id
        for transition_id in recognized_transition_ids()
        if transition_id in _PROTECTED_TRANSITION_IDS
    )


def production_owner_adapter_transition_ids() -> tuple[str, ...]:
    """Return every registry row with a named typed production owner adapter."""

    return protected_transition_ids()


def missing_production_owner_adapter_transition_ids() -> tuple[str, ...]:
    """Return registry rows not yet reachable through typed production evidence."""

    covered = frozenset(production_owner_adapter_transition_ids())
    return tuple(
        transition_id
        for transition_id in recognized_transition_ids()
        if transition_id not in covered
    )


def _make_service_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    satisfied_at: CanonicalTimestamp,
    evidence_kind: TransitionGuardEvidenceKind,
    evidence: Mapping[str, object],
) -> TransitionGuardProof:
    definition = transition_definition(transition)
    allowed = _OWNING_EVIDENCE_TRANSITION_IDS.get(evidence_kind, frozenset())
    if definition.transition.transition_id not in allowed:
        raise LifecycleSchemaError(
            "TRANSITION_OWNING_EVIDENCE_ROUTE_INVALID",
            reason=_reason("RC-113"),
        )
    facts = satisfying_transition_guard_facts(definition.transition)
    facts_binding, _, verdict = _closed_guard_facts(
        facts,
        transition_guard_fact_schema(definition.transition),
    )
    if verdict is not TransitionGuardVerdict.SATISFIED:
        raise LifecycleSchemaError(
            "TRANSITION_OWNING_EVIDENCE_DERIVATION_INVALID",
            reason=_reason("RC-113"),
        )
    authority = _issue_transition_guard_authority(
        transition=definition.transition,
        issuer=TransitionGuardAuthorityIssuer.OWNING_SERVICE,
        evidence_kind=evidence_kind,
        evidence=evidence,
        satisfied_at=satisfied_at,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        guard_facts=facts_binding,
        _issuer_token=_OWNING_SERVICE_AUTHORITY_ISSUER_TOKEN,
    )
    return make_transition_guard_proof(
        transition=definition.transition,
        from_state=definition.from_state,
        expected_to_state=definition.to_state,
        registered_guard=definition.guard,
        required_effects=definition.required_effects,
        guard_facts=facts,
        authority_evidence=authority,
    )


def make_case_owner_transition_guard_proof(
    *,
    transition: TransitionRef,
    decision: object,
) -> TransitionGuardProof:
    """Derive TR-007/008 only from a sealed, replayed case-owner decision."""

    from synthetic_sales_assist.doi.case_attention import (
        CaseAttentionOwnerError,
        CaseOwnerDecision,
        validate_case_owner_decision,
    )

    try:
        validated = validate_case_owner_decision(decision)
    except (CaseAttentionOwnerError, AttributeError, TypeError, ValueError):
        raise LifecycleConflictError(
            "CASE_OWNER_REDUCTION_GUARD_NOT_SATISFIED",
            reason=_reason("RC-081"),
        ) from None
    if (
        type(validated) is not CaseOwnerDecision
        or validated.transition != transition
        or validated.transition_id != transition.transition_id
    ):
        raise LifecycleConflictError(
            "CASE_OWNER_REDUCTION_ROUTE_INVALID",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=validated.stream_id,
        occurrence_id=validated.occurrence_id,
        satisfied_at=validated.occurred_at,
        evidence_kind=TransitionGuardEvidenceKind.CASE_OWNER_REDUCTION,
        evidence={
            "decision": _hash_dict(validated.hash_binding()),
            "owner_event": _hash_dict(validated.owner_binding),
            "result_event": _hash_dict(validated.result.event.hash_binding()),
        },
    )


def make_attention_owner_transition_guard_proof(
    *,
    transition: TransitionRef,
    decision: object,
) -> TransitionGuardProof:
    """Derive attention routes only from the sealed v2 owner reducer decision."""

    from synthetic_sales_assist.doi.case_attention import (
        AttentionOwnerDecision,
        CaseAttentionOwnerError,
        validate_attention_owner_decision,
    )

    try:
        validated = validate_attention_owner_decision(decision)
    except (CaseAttentionOwnerError, AttributeError, TypeError, ValueError):
        raise LifecycleConflictError(
            "ATTENTION_OWNER_REDUCTION_GUARD_NOT_SATISFIED",
            reason=_reason("RC-081"),
        ) from None
    if (
        type(validated) is not AttentionOwnerDecision
        or validated.transition != transition
        or validated.transition_id != transition.transition_id
    ):
        raise LifecycleConflictError(
            "ATTENTION_OWNER_REDUCTION_ROUTE_INVALID",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=validated.stream_id,
        occurrence_id=validated.occurrence_id,
        satisfied_at=validated.occurred_at,
        evidence_kind=TransitionGuardEvidenceKind.ATTENTION_OWNER_REDUCTION,
        evidence={
            "decision": _hash_dict(validated.hash_binding()),
            "owner_event": _hash_dict(validated.owner_binding),
            "result_event": _hash_dict(validated.result.event.hash_binding()),
        },
    )


def make_run_control_transition_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    run_control: object,
    owner_result: object,
    accepted_command: object | None = None,
) -> TransitionGuardProof:
    """Derive TR-001..004 only from the owning run-control reducer state."""

    from synthetic_sales_assist.doi.source import (
        FinalizeFailedSourceImportNoRetryCommand,
        InMemoryDOIRunControl,
        NoRetryCommandReceipt,
        PreExtractionRulesUnavailableReceipt,
        RunControlConflict,
        RunEventKind,
        RunStartResult,
        RunStatus,
        RunTerminalizationResult,
    )

    if type(run_control) is not InMemoryDOIRunControl:
        raise LifecycleConflictError(
            "RUN_CONTROL_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    transition_id = transition.transition_id
    run = None
    event = None
    owner_binding: HashBinding | None = None
    extra: dict[str, object] = {}
    try:
        if transition_id == "TR-001" and type(owner_result) is RunStartResult:
            run = owner_result.run
            event = owner_result.run_event
            if (
                accepted_command is not None
                or run.status is not RunStatus.IN_PROGRESS
                or event.event_kind is not RunEventKind.RUN_STARTED
                or run_control.run(run.run_id) != run
                or run_control.run_events(run.run_id) != (event,)
                or owner_result.source_attempt is None
                or owner_result.source_attempt_event is None
                or run_control.attempt(owner_result.source_attempt.attempt_id)
                != owner_result.source_attempt
                or run_control.work_items(run.run_id) != owner_result.work_items
            ):
                raise LifecycleConflictError(
                    "RUN_CONTROL_OWNER_INVALID",
                    reason=_reason("RC-081"),
                )
            owner_binding = run.hash_binding()
            extra = {
                "source_attempt": _hash_dict(
                    owner_result.source_attempt.hash_binding()
                ),
                "source_attempt_event": _hash_dict(
                    owner_result.source_attempt_event.hash_binding()
                ),
            }
        elif transition_id in {"TR-002", "TR-003"} and type(
            owner_result
        ) is RunTerminalizationResult:
            run = owner_result.run
            event = owner_result.run_event
            expected_status = (
                RunStatus.COMPLETED
                if transition_id == "TR-002"
                else RunStatus.COMPLETED_WITH_EXCEPTIONS
            )
            if (
                accepted_command is not None
                or run.status is not expected_status
                or event.event_kind is not RunEventKind.RUN_TERMINAL
                or run_control.run(run.run_id) != run
                or run_control.run_events(run.run_id)[-1] != event
            ):
                raise LifecycleConflictError(
                    "RUN_CONTROL_OWNER_INVALID",
                    reason=_reason("RC-081"),
                )
            owner_binding = run.hash_binding()
        elif transition_id == "TR-004" and type(
            owner_result
        ) is NoRetryCommandReceipt:
            if type(accepted_command) is not FinalizeFailedSourceImportNoRetryCommand:
                raise LifecycleConflictError(
                    "RUN_CONTROL_OWNER_INVALID",
                    reason=_reason("RC-081"),
                )
            replay = run_control.finalize_failed_source_import_no_retry(
                accepted_command
            )
            if replay != owner_result:
                raise LifecycleConflictError(
                    "RUN_CONTROL_OWNER_INVALID",
                    reason=_reason("RC-081"),
                )
            run = run_control.run(accepted_command.run_id)
            event = run_control.run_events(run.run_id)[-1]
            if (
                run.status is not RunStatus.FAILED
                or owner_result.run != run.hash_binding()
                or owner_result.run_event != event.hash_binding()
            ):
                raise LifecycleConflictError(
                    "RUN_CONTROL_OWNER_INVALID",
                    reason=_reason("RC-081"),
                )
            owner_binding = owner_result.hash_binding()
            extra = {"accepted_command": _hash_dict(accepted_command.hash_binding())}
        elif transition_id == "TR-004" and type(
            owner_result
        ) is PreExtractionRulesUnavailableReceipt:
            run = owner_result.run
            event = owner_result.event
            if (
                accepted_command is not None
                or run.status is not RunStatus.FAILED
                or run_control.run(run.run_id) != run
                or run_control.run_events(run.run_id)[-1] != event
            ):
                raise LifecycleConflictError(
                    "RUN_CONTROL_OWNER_INVALID",
                    reason=_reason("RC-081"),
                )
            owner_binding = owner_result.hash_binding()
        else:
            raise LifecycleConflictError(
                "RUN_CONTROL_OWNER_INVALID",
                reason=_reason("RC-081"),
            )
    except (RunControlConflict, ValueError):
        raise LifecycleConflictError(
            "RUN_CONTROL_OWNER_INVALID",
            reason=_reason("RC-081"),
        ) from None
    if (
        run is None
        or event is None
        or owner_binding is None
        or stream_id != run_transition_stream_id(run)
        or occurrence_id != run_transition_occurrence_id(event)
    ):
        raise LifecycleConflictError(
            "RUN_CONTROL_OWNER_SCOPE_INVALID",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=event.occurred_at,
        evidence_kind=TransitionGuardEvidenceKind.RUN_CONTROL_REDUCTION,
        evidence={
            "owner_result": _hash_dict(owner_binding),
            "run": _hash_dict(run.hash_binding()),
            "run_event": _hash_dict(event.hash_binding()),
            **extra,
        },
    )


def make_extraction_transition_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    surface: object,
    result: object,
) -> TransitionGuardProof:
    """Derive TR-005/006 only from the pure extraction reducer output."""

    from synthetic_sales_assist.doi.extraction import (
        DOIExtractionError,
        DOIExtractionResult,
        DOIExtractionSurface,
        ExtractionStatus,
        extract_order_snapshot,
    )

    try:
        derived = (
            extract_order_snapshot(surface)
            if type(surface) is DOIExtractionSurface
            else None
        )
    except DOIExtractionError:
        derived = None
    if (
        transition.transition_id not in {"TR-005", "TR-006"}
        or type(result) is not DOIExtractionResult
        or type(derived) is not DOIExtractionResult
        or derived != result
        or stream_id != extraction_transition_stream_id(result.attempt)
        or occurrence_id != extraction_transition_occurrence_id(result.attempt)
    ):
        raise LifecycleConflictError(
            "EXTRACTION_REDUCTION_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    succeeded = result.attempt.status is ExtractionStatus.SUCCEEDED
    if succeeded != (transition.transition_id == "TR-005"):
        raise LifecycleConflictError(
            "EXTRACTION_REDUCTION_ROUTE_INVALID",
            reason=_reason("RC-081"),
        )
    snapshot = result.snapshot
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=result.attempt.completed_at,
        evidence_kind=TransitionGuardEvidenceKind.EXTRACTION_REDUCTION,
        evidence={
            "attention_conditions": [
                item.value for item in result.attention_conditions
            ],
            "attempt": _hash_dict(result.attempt.hash_binding()),
            "snapshot": (
                None if snapshot is None else _hash_dict(snapshot.hash_binding())
            ),
            "whole_order_completeness": (
                None
                if snapshot is None
                else _hash_dict(snapshot.completeness_proof.hash_binding())
            ),
        },
    )


def make_source_import_start_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    run_control: object,
    started_attempt: object,
    retry_command_id: object | None = None,
) -> TransitionGuardProof:
    """Derive TR-098 from an accepted initial invocation or retained retry command."""

    from synthetic_sales_assist.doi.identities import AcceptedCommandId
    from synthetic_sales_assist.doi.source import (
        DOISourceImportAttempt,
        InMemoryDOIRunControl,
        RunControlConflict,
        SourceAttemptEventKind,
        SourceImportAttemptState,
    )

    if (
        transition.transition_id != "TR-098"
        or type(run_control) is not InMemoryDOIRunControl
        or type(started_attempt) is not DOISourceImportAttempt
        or started_attempt.state is not SourceImportAttemptState.STARTED
    ):
        raise LifecycleConflictError(
            "SOURCE_IMPORT_START_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    try:
        retained_attempts = run_control.attempts_for_run(started_attempt.run_id)
        current = next(
            item
            for item in retained_attempts
            if item.attempt_id == started_attempt.attempt_id
        )
        events = run_control.attempt_events(started_attempt.attempt_id)
        start_event = events[0]
        if (
            current.ordinal != started_attempt.ordinal
            or current.run_id != started_attempt.run_id
            or current.source_identity_id != started_attempt.source_identity_id
            or current.started_at != started_attempt.started_at
            or start_event.event_kind
            is not SourceAttemptEventKind.SOURCE_IMPORT_STARTED
            or start_event.occurred_at != started_attempt.started_at
        ):
            raise LifecycleConflictError(
                "SOURCE_IMPORT_START_OWNER_INVALID",
                reason=_reason("RC-081"),
            )
        if started_attempt.ordinal.value == 1:
            accepted_start = run_control.run_start_result(started_attempt.run_id)
            if (
                retry_command_id is not None
                or accepted_start.source_attempt != started_attempt
                or accepted_start.source_attempt_event != start_event
            ):
                raise LifecycleConflictError(
                    "SOURCE_IMPORT_START_OWNER_INVALID",
                    reason=_reason("RC-081"),
                )
            command_evidence = None
        else:
            if (
                type(retry_command_id) is not AcceptedCommandId
                or run_control.retry_attempt(retry_command_id) != started_attempt
                or started_attempt.ordinal.value > len(retained_attempts)
            ):
                raise LifecycleConflictError(
                    "SOURCE_IMPORT_START_OWNER_INVALID",
                    reason=_reason("RC-081"),
                )
            predecessor = retained_attempts[started_attempt.ordinal.value - 2]
            if (
                predecessor.ordinal.value + 1 != started_attempt.ordinal.value
                or predecessor.state
                not in {
                    SourceImportAttemptState.FAILED,
                    SourceImportAttemptState.ABORTED,
                }
            ):
                raise LifecycleConflictError(
                    "SOURCE_IMPORT_START_OWNER_INVALID",
                    reason=_reason("RC-081"),
                )
            command_evidence = retry_command_id.to_json_value()
    except (RunControlConflict, StopIteration, ValueError):
        raise LifecycleConflictError(
            "SOURCE_IMPORT_START_OWNER_INVALID",
            reason=_reason("RC-081"),
        ) from None
    if (
        stream_id != source_import_transition_stream_id(started_attempt)
        or occurrence_id != source_import_event_occurrence_id(start_event)
    ):
        raise LifecycleConflictError(
            "SOURCE_IMPORT_START_SCOPE_INVALID",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=start_event.occurred_at,
        evidence_kind=TransitionGuardEvidenceKind.SOURCE_IMPORT_REDUCTION,
        evidence={
            "attempt": _hash_dict(started_attempt.hash_binding()),
            "attempt_event": _hash_dict(start_event.hash_binding()),
            "retry_command_id": command_evidence,
            "run_id": started_attempt.run_id.value,
        },
    )


def make_source_import_commit_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    run_control: object,
    committed_attempt: object,
    source_result: object | None = None,
    before_image: object | None = None,
    after_image: object | None = None,
    candidate_batch_id: object | None = None,
    rejected_record: object | None = None,
) -> TransitionGuardProof:
    """Derive TR-099..103 from the retained import commit and pure source reducer."""

    from synthetic_sales_assist.doi.identities import SourceBatchId
    from synthetic_sales_assist.doi.source import (
        DOIRejectedSourceRecord,
        DOISourceImportAttempt,
        DOISourceError,
        InMemoryDOIRunControl,
        RunControlConflict,
        SourceAttemptEventKind,
        SourceImportAttemptState,
        SourceImportResult,
        SourceImportResultKind,
        SyntheticQueueImage,
        ingest_synthetic_queue,
    )

    if (
        transition.transition_id
        not in {"TR-099", "TR-100", "TR-101", "TR-102", "TR-103"}
        or type(run_control) is not InMemoryDOIRunControl
        or type(committed_attempt) is not DOISourceImportAttempt
    ):
        raise LifecycleConflictError(
            "SOURCE_IMPORT_COMMIT_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    try:
        if run_control.attempt(committed_attempt.attempt_id) != committed_attempt:
            raise LifecycleConflictError(
                "SOURCE_IMPORT_COMMIT_OWNER_INVALID",
                reason=_reason("RC-081"),
            )
        events = run_control.attempt_events(committed_attempt.attempt_id)
        if len(events) != 2:
            raise LifecycleConflictError(
                "SOURCE_IMPORT_COMMIT_OWNER_INVALID",
                reason=_reason("RC-081"),
            )
        terminal_event = events[-1]
        retained_result_binding = run_control.attempt_commit_binding(
            committed_attempt.attempt_id
        )
    except RunControlConflict:
        raise LifecycleConflictError(
            "SOURCE_IMPORT_COMMIT_OWNER_INVALID",
            reason=_reason("RC-081"),
        ) from None

    aborted = committed_attempt.state is SourceImportAttemptState.ABORTED
    derived_result = None
    if aborted:
        if (
            terminal_event.event_kind
            is not SourceAttemptEventKind.SOURCE_IMPORT_ABORTED
            or retained_result_binding is not None
            or any(
                item is not None
                for item in (
                    source_result,
                    before_image,
                    after_image,
                    candidate_batch_id,
                    rejected_record,
                )
            )
        ):
            raise LifecycleConflictError(
                "SOURCE_IMPORT_ABORT_OWNER_INVALID",
                reason=_reason("RC-081"),
            )
    else:
        if (
            type(source_result) is not SourceImportResult
            or type(before_image) is not SyntheticQueueImage
            or type(after_image) is not SyntheticQueueImage
            or type(candidate_batch_id) is not SourceBatchId
        ):
            raise LifecycleConflictError(
                "SOURCE_IMPORT_RESULT_OWNER_INVALID",
                reason=_reason("RC-081"),
            )
        try:
            derived_result = ingest_synthetic_queue(
                before_image,
                after_image,
                candidate_batch_id=candidate_batch_id,
            )
        except DOISourceError:
            raise LifecycleConflictError(
                "SOURCE_IMPORT_RESULT_OWNER_INVALID",
                reason=_reason("RC-081"),
            ) from None
        if (
            derived_result.hash_binding() != source_result.hash_binding()
            or retained_result_binding != source_result.hash_binding()
        ):
            raise LifecycleConflictError(
                "SOURCE_IMPORT_RESULT_OWNER_INVALID",
                reason=_reason("RC-081"),
            )

    success = (
        not aborted
        and source_result.kind is SourceImportResultKind.SUCCEEDED
    )
    failure = (
        not aborted
        and source_result.kind is SourceImportResultKind.FAILED
    )
    actual_batch = None
    batch_created = None
    if success:
        if (
            committed_attempt.state is not SourceImportAttemptState.SUCCEEDED
            or terminal_event.event_kind
            is not SourceAttemptEventKind.SOURCE_IMPORT_SUCCEEDED
            or committed_attempt.source_batch_id is None
        ):
            raise LifecycleConflictError(
                "SOURCE_IMPORT_SUCCESS_OWNER_INVALID",
                reason=_reason("RC-081"),
            )
        try:
            actual_batch = run_control.source_batch(
                committed_attempt.source_batch_id
            )
            batch_created = run_control.attempt_created_source_batch(
                committed_attempt.attempt_id
            )
        except (DOISourceError, RunControlConflict):
            raise LifecycleConflictError(
                "SOURCE_IMPORT_SUCCESS_OWNER_INVALID",
                reason=_reason("RC-081"),
            ) from None
        if (
            source_result.batch is None
            or source_result.batch.identity != actual_batch.identity
        ):
            raise LifecycleConflictError(
                "SOURCE_IMPORT_SUCCESS_OWNER_INVALID",
                reason=_reason("RC-081"),
            )
    elif failure:
        if (
            committed_attempt.state is not SourceImportAttemptState.FAILED
            or terminal_event.event_kind
            is not SourceAttemptEventKind.SOURCE_IMPORT_FAILED
        ):
            raise LifecycleConflictError(
                "SOURCE_IMPORT_FAILURE_OWNER_INVALID",
                reason=_reason("RC-081"),
            )

    transition_id = transition.transition_id
    if transition_id == "TR-099":
        route_valid = success and rejected_record is None
        expected_stream = source_import_transition_stream_id(committed_attempt)
    elif transition_id == "TR-100":
        route_valid = (failure or aborted) and rejected_record is None
        expected_stream = source_import_transition_stream_id(committed_attempt)
    elif transition_id in {"TR-101", "TR-102"}:
        route_valid = (
            success
            and rejected_record is None
            and batch_created is (transition_id == "TR-101")
        )
        expected_stream = (
            actual_batch.batch_id.value
            if actual_batch is not None
            else EvidenceId("SYN-EVIDENCE-INVALID-SOURCE-BATCH")
        )
    else:
        route_valid = (
            success
            and batch_created is True
            and type(rejected_record) is DOIRejectedSourceRecord
            and actual_batch is not None
            and rejected_record in actual_batch.rejected_records
            and all(
                item.order_id != rejected_record.order_id
                for item in actual_batch.staged_orders
            )
        )
        expected_stream = (
            identity_retention_stream_id(rejected_record)
            if type(rejected_record) is DOIRejectedSourceRecord
            else EvidenceId("SYN-EVIDENCE-INVALID-SOURCE-REJECTION")
        )
    if (
        not route_valid
        or stream_id != expected_stream
        or occurrence_id != source_import_event_occurrence_id(terminal_event)
    ):
        raise LifecycleConflictError(
            "SOURCE_IMPORT_COMMIT_ROUTE_INVALID",
            reason=_reason("RC-081"),
        )

    source_derivation = (
        None
        if aborted
        else {
            "after_accessible": after_image.accessible,
            "after_content": _hash_dict(after_image.content_binding()),
            "after_revision": after_image.revision,
            "before_accessible": before_image.accessible,
            "before_content": _hash_dict(before_image.content_binding()),
            "before_revision": before_image.revision,
            "candidate_batch_id": candidate_batch_id.to_json_value(),
        }
    )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=terminal_event.occurred_at,
        evidence_kind=TransitionGuardEvidenceKind.SOURCE_IMPORT_REDUCTION,
        evidence={
            "actual_batch": (
                None
                if actual_batch is None
                else _hash_dict(actual_batch.hash_binding())
            ),
            "attempt": _hash_dict(committed_attempt.hash_binding()),
            "attempt_event": _hash_dict(terminal_event.hash_binding()),
            "batch_created": batch_created,
            "rejected_record": (
                None
                if rejected_record is None
                else _hash_dict(rejected_record.hash_binding())
            ),
            "source_derivation": source_derivation,
            "source_result": (
                None
                if source_result is None
                else _hash_dict(source_result.hash_binding())
            ),
        },
    )


def make_source_rejection_retention_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    run_control: object,
    rejected_record: object,
    terminal_run: object,
) -> TransitionGuardProof:
    """Derive TR-104 from an exact rejected record and its terminal owner run."""

    from synthetic_sales_assist.doi.retention import (
        IdentityRetentionKind,
        schedule_identity_retention,
    )
    from synthetic_sales_assist.doi.source import (
        DOIRejectedSourceRecord,
        DOIRun,
        DOISourceError,
        InMemoryDOIRunControl,
        RunControlConflict,
        RunStatus,
    )

    if (
        transition.transition_id != "TR-104"
        or type(run_control) is not InMemoryDOIRunControl
        or type(rejected_record) is not DOIRejectedSourceRecord
        or type(terminal_run) is not DOIRun
        or terminal_run.status is RunStatus.IN_PROGRESS
        or terminal_run.completed_at is None
        or terminal_run.source_batch_id is None
    ):
        raise LifecycleConflictError(
            "SOURCE_REJECTION_RETENTION_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    try:
        batch = run_control.source_batch(terminal_run.source_batch_id)
        if (
            run_control.run(terminal_run.run_id) != terminal_run
            or run_control.source_batch_creator_run(batch.batch_id) != terminal_run
            or rejected_record not in batch.rejected_records
        ):
            raise LifecycleConflictError(
                "SOURCE_REJECTION_RETENTION_OWNER_INVALID",
                reason=_reason("RC-081"),
            )
        decision = schedule_identity_retention(
            kind=IdentityRetentionKind.REJECTED_SOURCE_RECORD,
            identity_binding=rejected_record.hash_binding(),
            run_completed_at=terminal_run.completed_at,
        )
    except (DOISourceError, RunControlConflict, ValueError):
        raise LifecycleConflictError(
            "SOURCE_REJECTION_RETENTION_OWNER_INVALID",
            reason=_reason("RC-081"),
        ) from None
    if (
        stream_id != identity_retention_stream_id(rejected_record)
        or occurrence_id
        != source_rejection_retention_occurrence_id(
            rejected_record,
            terminal_run,
        )
    ):
        raise LifecycleConflictError(
            "SOURCE_REJECTION_RETENTION_SCOPE_INVALID",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=terminal_run.completed_at,
        evidence_kind=TransitionGuardEvidenceKind.SOURCE_IMPORT_REDUCTION,
        evidence={
            "batch": _hash_dict(batch.hash_binding()),
            "purge_eligible_at": decision.purge_eligible_at.value,
            "rejected_record": _hash_dict(rejected_record.hash_binding()),
            "retention_reasons": decision.transaction_reasons.to_json_value(),
            "terminal_run": _hash_dict(terminal_run.hash_binding()),
        },
    )


def make_relationship_transition_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    result_relationship: object,
    recorded_at: CanonicalTimestamp,
    prior_relationship: object | None = None,
) -> TransitionGuardProof:
    """Derive relationship create/revision routes from product-only reducers."""

    from synthetic_sales_assist.doi.knowledge import (
        DOIAlternateRelationship,
        ProductKnowledgeError,
        append_relationship_revision,
        create_relationship,
    )
    from synthetic_sales_assist.doi.models import (
        AlternateRelationshipState,
        AlternateRevisionKind,
    )

    if (
        transition.transition_id
        not in {"TR-040", "TR-041", "TR-082", "TR-083"}
        or type(result_relationship) is not DOIAlternateRelationship
        or type(recorded_at) is not CanonicalTimestamp
        or stream_id != result_relationship.relationship_id
        or occurrence_id != result_relationship.current_revision.revision_id
    ):
        raise LifecycleConflictError(
            "RELATIONSHIP_REDUCTION_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    current = result_relationship.current_revision
    transition_id = transition.transition_id
    try:
        if transition_id == "TR-082":
            if prior_relationship is not None:
                raise LifecycleConflictError(
                    "RELATIONSHIP_REDUCTION_ROUTE_INVALID",
                    reason=_reason("RC-081"),
                )
            derived = create_relationship(
                relationship_id=result_relationship.relationship_id,
                revision_id=current.revision_id,
                relationship_type=result_relationship.relationship_type,
                ordered_sku=result_relationship.ordered_sku,
                candidate_sku=result_relationship.candidate_sku,
                ordered_mfg=current.ordered_mfg,
                candidate_mfg=current.candidate_mfg,
                compatibility_review_required=(
                    current.compatibility_review_required
                ),
                evidence_source=current.evidence_source,
            )
        else:
            if type(prior_relationship) is not DOIAlternateRelationship:
                raise LifecycleConflictError(
                    "RELATIONSHIP_REDUCTION_ROUTE_INVALID",
                    reason=_reason("RC-081"),
                )
            derived = append_relationship_revision(
                prior_relationship,
                revision_id=current.revision_id,
                revision_kind=current.revision_kind,
                state=current.state,
                compatibility_review_required=(
                    current.compatibility_review_required
                ),
                evidence_source=current.evidence_source,
            )
    except ProductKnowledgeError:
        raise LifecycleConflictError(
            "RELATIONSHIP_REDUCTION_GUARD_NOT_SATISFIED",
            reason=_reason("RC-081"),
        ) from None
    expected_route = {
        "TR-082": (
            AlternateRevisionKind.CREATED,
            AlternateRelationshipState.ACTIVE,
        ),
        "TR-083": (
            AlternateRevisionKind.UPDATED,
            AlternateRelationshipState.ACTIVE,
        ),
        "TR-040": (
            AlternateRevisionKind.SUPERSEDED,
            AlternateRelationshipState.SUPERSEDED,
        ),
        "TR-041": (
            AlternateRevisionKind.INVALIDATED,
            AlternateRelationshipState.INVALIDATED,
        ),
    }[transition_id]
    if (
        derived.canonical_bytes() != result_relationship.canonical_bytes()
        or current.revision_kind is not expected_route[0]
        or current.state is not expected_route[1]
    ):
        raise LifecycleConflictError(
            "RELATIONSHIP_REDUCTION_ROUTE_INVALID",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=recorded_at,
        evidence_kind=TransitionGuardEvidenceKind.PRODUCT_KNOWLEDGE_REDUCTION,
        evidence={
            "prior_relationship": (
                None
                if prior_relationship is None
                else _hash_dict(prior_relationship.hash_binding())
            ),
            "result_relationship": _hash_dict(
                result_relationship.hash_binding()
            ),
            "result_revision": _hash_dict(current.hash_binding()),
            "revision_kind": current.revision_kind.value,
        },
    )


def make_alternate_observation_transition_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    observation: object,
    relationship: object,
    action_context: object,
) -> TransitionGuardProof:
    """Derive TR-042 from an active relationship and exact OPEN context binding."""

    from synthetic_sales_assist.doi.knowledge import (
        DOIAlternateObservation,
        DOIAlternateRelationship,
    )
    from synthetic_sales_assist.doi.models import (
        ActionContextState,
        AlternateRelationshipState,
        DOIActionContext,
    )
    from synthetic_sales_assist.doi.retention import calendar90

    if (
        transition.transition_id != "TR-042"
        or type(observation) is not DOIAlternateObservation
        or type(relationship) is not DOIAlternateRelationship
        or type(action_context) is not DOIActionContext
        or action_context.state is not ActionContextState.OPEN
        or observation.action_context_id != action_context.action_context_id
        or observation.action_context_binding != action_context.hash_binding()
        or relationship.current_revision.state
        is not AlternateRelationshipState.ACTIVE
        or observation.relationship_revision_binding
        != relationship.current_revision.hash_binding()
        or observation.candidate_sku != relationship.candidate_sku
        or stream_id != observation.observation_id
        or occurrence_id != alternate_observation_occurrence_id(observation)
    ):
        raise LifecycleConflictError(
            "ALTERNATE_OBSERVATION_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=observation.observed_at,
        evidence_kind=TransitionGuardEvidenceKind.PRODUCT_KNOWLEDGE_REDUCTION,
        evidence={
            "action_context": _hash_dict(action_context.hash_binding()),
            "nominal_purge_eligible_at": calendar90(
                observation.observed_at
            ).value,
            "observation": _hash_dict(observation.hash_binding()),
            "relationship": _hash_dict(relationship.hash_binding()),
            "relationship_revision": _hash_dict(
                relationship.current_revision.hash_binding()
            ),
        },
    )


def _replay_action_context_history(history: object) -> object:
    from synthetic_sales_assist.doi.models import (
        DOIActionContextHistory,
        DOIModelError,
        reduce_action_context,
    )

    if type(history) is not DOIActionContextHistory:
        raise LifecycleConflictError(
            "ACTION_CONTEXT_OWNER_HISTORY_INVALID",
            reason=_reason("RC-081"),
        )
    try:
        replayed = DOIActionContextHistory(
            action_context_id=history.action_context_id
        )
        for event in history.events:
            replayed = reduce_action_context(replayed, event).history
        if replayed != history:
            raise DOIModelError("ACTION_CONTEXT_HISTORY_REPLAY_CONFLICT")
    except (AttributeError, DOIModelError, TypeError, ValueError):
        raise LifecycleConflictError(
            "ACTION_CONTEXT_OWNER_HISTORY_INVALID",
            reason=_reason("RC-081"),
        ) from None
    return replayed


def _replay_action_context_store(store: object) -> object:
    from synthetic_sales_assist.doi.models import (
        DOIActionContextStore,
        DOIModelError,
    )

    if type(store) is not DOIActionContextStore:
        raise LifecycleConflictError(
            "ACTION_CONTEXT_OWNER_STORE_INVALID",
            reason=_reason("RC-081"),
        )
    try:
        replayed = DOIActionContextStore(
            histories=tuple(
                _replay_action_context_history(history)
                for history in store.histories
            )
        )
        if replayed != store:
            raise DOIModelError("ACTION_CONTEXT_STORE_REPLAY_CONFLICT")
    except (AttributeError, DOIModelError, TypeError, ValueError):
        raise LifecycleConflictError(
            "ACTION_CONTEXT_OWNER_STORE_INVALID",
            reason=_reason("RC-081"),
        ) from None
    return replayed


def make_action_context_transition_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    prior_store: object,
    event: object,
    observation: object | None = None,
    relationship_revision: object | None = None,
    human_authority: object | None = None,
) -> TransitionGuardProof:
    """Derive TR-084/085/087 from the exact Action Context store reducer."""

    from synthetic_sales_assist.doi.knowledge import (
        DOIAlternateObservation,
        DOIAlternateRelationshipRevision,
    )
    from synthetic_sales_assist.doi.models import (
        ActionContextEventType,
        ActionContextState,
        DOIActionContextEvent,
        DOIActionContextStore,
        DOIModelError,
        HumanAuthorityGrant,
        reduce_action_context_store,
    )

    replayed_store = _replay_action_context_store(prior_store)
    try:
        owner_invalid = (
            type(replayed_store) is not DOIActionContextStore
            or type(event) is not DOIActionContextEvent
            or transition.transition_id not in {"TR-084", "TR-085", "TR-087"}
            or stream_id != event.action_context_id
            or occurrence_id != action_context_event_occurrence_id(event)
        )
    except (AttributeError, TypeError):
        owner_invalid = True
    if owner_invalid:
        raise LifecycleConflictError(
            "ACTION_CONTEXT_REDUCTION_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    try:
        reduction = reduce_action_context_store(replayed_store, event)
    except (AttributeError, DOIModelError, TypeError, ValueError):
        raise LifecycleConflictError(
            "ACTION_CONTEXT_REDUCTION_GUARD_NOT_SATISFIED",
            reason=_reason("RC-081"),
        ) from None
    if reduction.replayed or reduction.event != event:
        raise LifecycleConflictError(
            "ACTION_CONTEXT_REDUCTION_REPLAY_INVALID",
            reason=_reason("RC-081"),
        )
    result_context = reduction.history.projection
    transition_id = transition.transition_id
    extra_evidence: dict[str, object] = {}
    if transition_id == "TR-084":
        if (
            event.event_type is not ActionContextEventType.OPENED
            or result_context is None
            or result_context.state is not ActionContextState.OPEN
            or observation is not None
            or relationship_revision is not None
            or human_authority is not None
        ):
            raise LifecycleConflictError(
                "ACTION_CONTEXT_OPEN_ROUTE_INVALID",
                reason=_reason("RC-081"),
            )
    elif transition_id == "TR-085":
        link = event.observation_link
        if (
            event.event_type is not ActionContextEventType.OBSERVATION_LINKED
            or result_context is None
            or result_context.state is not ActionContextState.OPEN
            or type(observation) is not DOIAlternateObservation
            or type(relationship_revision) is not DOIAlternateRelationshipRevision
            or type(human_authority) is not HumanAuthorityGrant
            or link is None
            or link.alternate_observation_id != observation.observation_id
            or link.alternate_observation_binding != observation.hash_binding()
            or link.relationship_revision_id != relationship_revision.revision_id
            or link.relationship_revision_binding
            != relationship_revision.hash_binding()
            or event.human_authority_binding != human_authority.hash_binding()
            or (
                observation.observed_at.epoch_seconds,
                observation.observed_at.nanosecond,
            )
            <= (
                result_context.created_at.epoch_seconds,
                result_context.created_at.nanosecond,
            )
        ):
            raise LifecycleConflictError(
                "ACTION_CONTEXT_OBSERVATION_LINK_ROUTE_INVALID",
                reason=_reason("RC-081"),
            )
        extra_evidence = {
            "human_authority": _hash_dict(human_authority.hash_binding()),
            "observation": _hash_dict(observation.hash_binding()),
            "relationship_revision": _hash_dict(
                relationship_revision.hash_binding()
            ),
        }
    else:
        if (
            result_context is None
            or result_context.state
            not in {
                ActionContextState.CLOSED_ABANDONED,
                ActionContextState.CLOSED_SUPERSEDED,
            }
            or event.event_type
            not in {
                ActionContextEventType.ABANDONED,
                ActionContextEventType.SUPERSEDED,
            }
            or observation is not None
            or relationship_revision is not None
        ):
            raise LifecycleConflictError(
                "ACTION_CONTEXT_CLOSE_ROUTE_INVALID",
                reason=_reason("RC-081"),
            )
        if event.event_type is ActionContextEventType.ABANDONED:
            if (
                type(human_authority) is not HumanAuthorityGrant
                or event.human_authority_binding
                != human_authority.hash_binding()
            ):
                raise LifecycleConflictError(
                    "ACTION_CONTEXT_ABANDONMENT_AUTHORITY_INVALID",
                    reason=_reason("RC-081"),
                )
            extra_evidence = {
                "human_authority": _hash_dict(human_authority.hash_binding())
            }
        else:
            if human_authority is not None:
                raise LifecycleConflictError(
                    "ACTION_CONTEXT_SUPERSESSION_AUTHORITY_INVALID",
                    reason=_reason("RC-081"),
                )
            superseding = tuple(
                retained
                for history in replayed_store.histories
                for retained in history.events
                if retained.event_type is ActionContextEventType.OPENED
                and retained.hash_binding() == event.superseding_context_binding
            )
            if len(superseding) != 1:
                raise LifecycleConflictError(
                    "ACTION_CONTEXT_SUPERSESSION_OWNER_INVALID",
                    reason=_reason("RC-081"),
                )
            extra_evidence = {
                "superseding_open_event": _hash_dict(
                    superseding[0].hash_binding()
                )
            }
    assert result_context is not None
    prior_history = next(
        (
            history
            for history in replayed_store.histories
            if history.action_context_id == event.action_context_id
        ),
        None,
    )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=event.occurred_at,
        evidence_kind=TransitionGuardEvidenceKind.ACTION_CONTEXT_REDUCTION,
        evidence={
            "event": _hash_dict(event.hash_binding()),
            "opening_authorization": _hash_dict(
                event.opening_authorization.hash_binding()
            ),
            "prior_head": (
                None
                if prior_history is None or not prior_history.events
                else _hash_dict(prior_history.events[-1].hash_binding())
            ),
            "result_context": _hash_dict(result_context.hash_binding()),
            "result_head": _hash_dict(
                reduction.history.events[-1].hash_binding()
            ),
            **extra_evidence,
        },
    )


def _replay_contact_workflow_history(history: object) -> object:
    from synthetic_sales_assist.doi.models import (
        ContactWorkflowHistory,
        DOIModelError,
        reduce_contact_workflow,
    )

    if type(history) is not ContactWorkflowHistory:
        raise LifecycleConflictError(
            "CONTACT_WORKFLOW_OWNER_HISTORY_INVALID",
            reason=_reason("RC-081"),
        )
    replayed = ContactWorkflowHistory.empty(
        stream_id=history.stream_id,
        action_context=history.action_context,
    )
    try:
        for event in history.events:
            replayed = reduce_contact_workflow(replayed, event).history
    except (DOIModelError, TypeError, ValueError):
        raise LifecycleConflictError(
            "CONTACT_WORKFLOW_OWNER_HISTORY_INVALID",
            reason=_reason("RC-081"),
        ) from None
    if replayed != history:
        raise LifecycleConflictError(
            "CONTACT_WORKFLOW_OWNER_HISTORY_INVALID",
            reason=_reason("RC-081"),
        )
    return replayed


def make_contact_workflow_transition_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    prior_history: object,
    event: object,
    action_context_history: object,
    evaluation_input: object | None = None,
) -> TransitionGuardProof:
    """Derive TR-065..073/080..081 from the contact workflow reducer."""

    from synthetic_sales_assist.doi.evaluator import evaluate_doi
    from synthetic_sales_assist.doi.models import (
        ActionContextKind,
        ActionContextState,
        ContactWorkflowEvent,
        ContactWorkflowEventType,
        ContactWorkflowHistory,
        ContactWorkflowState,
        DOIEvaluationInput,
        DOIModelError,
        HandlingFlag,
        OpportunityType,
        reduce_contact_workflow,
    )

    replayed_context = _replay_action_context_history(action_context_history)
    replayed_history = _replay_contact_workflow_history(prior_history)
    if (
        type(replayed_history) is not ContactWorkflowHistory
        or type(event) is not ContactWorkflowEvent
        or replayed_context.projection != replayed_history.action_context
        or replayed_context.projection is None
        or replayed_context.projection.state is not ActionContextState.OPEN
        or stream_id != event.stream_id
        or occurrence_id != contact_workflow_event_occurrence_id(event)
    ):
        raise LifecycleConflictError(
            "CONTACT_WORKFLOW_REDUCTION_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    try:
        reduction = reduce_contact_workflow(replayed_history, event)
    except (DOIModelError, TypeError, ValueError):
        raise LifecycleConflictError(
            "CONTACT_WORKFLOW_REDUCTION_GUARD_NOT_SATISFIED",
            reason=_reason("RC-081"),
        ) from None
    if reduction.replayed:
        raise LifecycleConflictError(
            "CONTACT_WORKFLOW_REDUCTION_REPLAY_INVALID",
            reason=_reason("RC-081"),
        )
    route_pairs = {
        "TR-065": frozenset(
            {
                (
                    ContactWorkflowState.NOT_CONTACTED,
                    ContactWorkflowState.CONTACT_REQUIRED,
                )
            }
        ),
        "TR-066": frozenset(
            {
                (
                    ContactWorkflowState.CONTACT_REQUIRED,
                    ContactWorkflowState.CONTACT_ATTEMPTED,
                )
            }
        ),
        "TR-067": frozenset(
            {
                (
                    ContactWorkflowState.NOT_CONTACTED,
                    ContactWorkflowState.CONTACT_ATTEMPTED,
                )
            }
        ),
        "TR-068": frozenset(
            {
                (
                    ContactWorkflowState.CONTACT_ATTEMPTED,
                    ContactWorkflowState.AWAITING_CUSTOMER,
                )
            }
        ),
        "TR-069": frozenset(
            {
                (
                    ContactWorkflowState.AWAITING_CUSTOMER,
                    ContactWorkflowState.CUSTOMER_APPROVED,
                )
            }
        ),
        "TR-070": frozenset(
            {
                (
                    ContactWorkflowState.AWAITING_CUSTOMER,
                    ContactWorkflowState.CUSTOMER_DECLINED,
                )
            }
        ),
        "TR-071": frozenset(
            {
                (
                    ContactWorkflowState.AWAITING_CUSTOMER,
                    ContactWorkflowState.NO_RESPONSE,
                )
            }
        ),
        "TR-072": frozenset(
            {
                (
                    ContactWorkflowState.CONTACT_ATTEMPTED,
                    ContactWorkflowState.CUSTOMER_APPROVED,
                )
            }
        ),
        "TR-073": frozenset(
            {
                (
                    ContactWorkflowState.CONTACT_ATTEMPTED,
                    ContactWorkflowState.CUSTOMER_DECLINED,
                )
            }
        ),
        "TR-080": frozenset(
            (
                prior,
                ContactWorkflowState.CONTACT_ATTEMPTED,
            )
            for prior in (
                ContactWorkflowState.CONTACT_ATTEMPTED,
                ContactWorkflowState.AWAITING_CUSTOMER,
                ContactWorkflowState.CUSTOMER_DECLINED,
                ContactWorkflowState.NO_RESPONSE,
            )
        ),
        "TR-081": frozenset(
            {
                (
                    ContactWorkflowState.CUSTOMER_APPROVED,
                    ContactWorkflowState.CUSTOMER_DECLINED,
                )
            }
        ),
    }
    route = (
        replayed_history.projection.state,
        reduction.history.projection.state,
    )
    allowed_pairs = route_pairs.get(transition.transition_id)
    if allowed_pairs is None or route not in allowed_pairs:
        raise LifecycleConflictError(
            "CONTACT_WORKFLOW_REDUCTION_ROUTE_INVALID",
            reason=_reason("RC-081"),
        )
    evaluation = None
    if transition.transition_id == "TR-065":
        evaluation = (
            evaluate_doi(evaluation_input)
            if type(evaluation_input) is DOIEvaluationInput
            else None
        )
        opportunity = next(
            (
                item
                for item in (() if evaluation is None else evaluation.opportunities)
                if item.opportunity_id
                == replayed_history.action_context.opportunity_id
            ),
            None,
        )
        if (
            event.event_type
            is not ContactWorkflowEventType.CONTACT_REQUIRED_DERIVED
            or event.evaluation != evaluation
            or evaluation is None
            or opportunity is None
            or opportunity.opportunity_type is not OpportunityType.FULFILLMENT_SPLIT
            or HandlingFlag.CUSTOMER_CONTACT_BEFORE_SPLIT
            not in evaluation.handling_flags
            or "RC-051" not in {reason.code for reason in evaluation.reasons.reasons}
            or replayed_history.action_context.context_kind
            is not ActionContextKind.CUSTOMER_CONTACT
        ):
            raise LifecycleConflictError(
                "CONTACT_WORKFLOW_SYSTEM_OWNER_INVALID",
                reason=_reason("RC-081"),
            )
    elif evaluation_input is not None or event.evaluation is not None:
        raise LifecycleConflictError(
            "CONTACT_WORKFLOW_HUMAN_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    if transition.transition_id == "TR-080":
        prior_times = tuple(
            retained.contact_occurred_at
            for retained in replayed_history.events
            if retained.contact_occurred_at is not None
        )
        if (
            not prior_times
            or event.contact_occurred_at is None
            or (
                event.contact_occurred_at.epoch_seconds,
                event.contact_occurred_at.nanosecond,
            )
            <= max(
                (item.epoch_seconds, item.nanosecond)
                for item in prior_times
            )
        ):
            raise LifecycleConflictError(
                "CONTACT_WORKFLOW_LATER_ATTEMPT_INVALID",
                reason=_reason("RC-081"),
            )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=event.recorded_at,
        evidence_kind=TransitionGuardEvidenceKind.CONTACT_WORKFLOW_REDUCTION,
        evidence={
            "action_context": _hash_dict(
                replayed_history.action_context.hash_binding()
            ),
            "action_context_head": _hash_dict(
                replayed_context.events[-1].hash_binding()
            ),
            "event": _hash_dict(event.hash_binding()),
            "evaluation": (
                None if evaluation is None else _hash_dict(evaluation.hash_binding())
            ),
            "evaluation_input": (
                None
                if evaluation_input is None
                else _hash_dict(evaluation_input.hash_binding())
            ),
            "prior_projection": _hash_dict(
                replayed_history.projection.hash_binding()
            ),
            "result_projection": _hash_dict(
                reduction.history.projection.hash_binding()
            ),
        },
    )


def _replay_wwc_history(history: object) -> object:
    from synthetic_sales_assist.doi.models import (
        DOIModelError,
        DOIWWCHistory,
        reduce_wwc,
    )

    if type(history) is not DOIWWCHistory:
        raise LifecycleConflictError(
            "WWC_OWNER_HISTORY_INVALID",
            reason=_reason("RC-081"),
        )
    replayed = DOIWWCHistory(
        stream_id=history.stream_id,
        order_id=history.order_id,
    )
    try:
        for event in history.events:
            replayed = reduce_wwc(replayed, event).history
    except (DOIModelError, TypeError, ValueError):
        raise LifecycleConflictError(
            "WWC_OWNER_HISTORY_INVALID",
            reason=_reason("RC-081"),
        ) from None
    if replayed != history:
        raise LifecycleConflictError(
            "WWC_OWNER_HISTORY_INVALID",
            reason=_reason("RC-081"),
        )
    return replayed


def make_wwc_transition_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    prior_history: object,
    event: object,
    evaluation_input: object,
) -> TransitionGuardProof:
    """Derive TR-074..079 from accepted input and the exact WWC reducer."""

    from synthetic_sales_assist.doi.evaluator import evaluate_doi
    from synthetic_sales_assist.doi.models import (
        DOIEvaluationInput,
        DOIModelError,
        DOIWWCEvent,
        DOIWWCHistory,
        WWCProjectionState,
        reduce_wwc,
    )

    replayed_history = _replay_wwc_history(prior_history)
    evaluation = (
        evaluate_doi(evaluation_input)
        if type(evaluation_input) is DOIEvaluationInput
        else None
    )
    if (
        type(replayed_history) is not DOIWWCHistory
        or type(event) is not DOIWWCEvent
        or evaluation is None
        or evaluation_input.snapshot.wwc_finding != event.finding
        or evaluation.order_id != event.order_id
        or evaluation.input_binding != evaluation_input.hash_binding()
        or stream_id != event.stream_id
        or occurrence_id != wwc_event_occurrence_id(event)
    ):
        raise LifecycleConflictError(
            "WWC_REDUCTION_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    try:
        reduction = reduce_wwc(replayed_history, event)
    except (DOIModelError, TypeError, ValueError):
        raise LifecycleConflictError(
            "WWC_REDUCTION_GUARD_NOT_SATISFIED",
            reason=_reason("RC-081"),
        ) from None
    if reduction.replayed or reduction.history.projection is None:
        raise LifecycleConflictError(
            "WWC_REDUCTION_REPLAY_INVALID",
            reason=_reason("RC-081"),
        )
    states = {
        "TR-074": frozenset({WWCProjectionState.NOT_APPLICABLE}),
        "TR-075": frozenset({WWCProjectionState.ACTIVE_SELF}),
        "TR-076": frozenset({WWCProjectionState.ACTIVE_OTHER_REP}),
        "TR-077": frozenset({WWCProjectionState.EXPIRED_OTHER_REP}),
        "TR-078": frozenset(
            {
                WWCProjectionState.AUTHOR_UNCERTAIN,
                WWCProjectionState.TIMING_UNCERTAIN,
                WWCProjectionState.AUTHOR_AND_TIMING_UNCERTAIN,
            }
        ),
    }
    transition_id = transition.transition_id
    if transition_id == "TR-079":
        if not replayed_history.events:
            raise LifecycleConflictError(
                "WWC_REEVALUATION_PRIOR_REQUIRED",
                reason=_reason("RC-081"),
            )
        prior_event = replayed_history.events[-1]
        if (
            event.finding == prior_event.finding
            and (
                event.recorded_at.epoch_seconds,
                event.recorded_at.nanosecond,
            )
            <= (
                prior_event.recorded_at.epoch_seconds,
                prior_event.recorded_at.nanosecond,
            )
        ):
            raise LifecycleConflictError(
                "WWC_REEVALUATION_EVIDENCE_UNCHANGED",
                reason=_reason("RC-081"),
            )
    elif (
        transition_id not in states
        or reduction.history.projection.state not in states[transition_id]
    ):
        raise LifecycleConflictError(
            "WWC_REDUCTION_ROUTE_INVALID",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=event.recorded_at,
        evidence_kind=TransitionGuardEvidenceKind.WWC_REDUCTION,
        evidence={
            "evaluation": _hash_dict(evaluation.hash_binding()),
            "evaluation_input": _hash_dict(evaluation_input.hash_binding()),
            "event": _hash_dict(event.hash_binding()),
            "prior_projection": (
                None
                if replayed_history.projection is None
                else _hash_dict(replayed_history.projection.hash_binding())
            ),
            "result_projection": _hash_dict(
                reduction.history.projection.hash_binding()
            ),
        },
    )


def make_evaluation_transition_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    evaluation_input: object,
    evaluation: object,
    prior_evaluation: object | None = None,
) -> TransitionGuardProof:
    """Derive evaluation append/top-level routes from the pure evaluator output.

    TR-027 is the first evaluation for the supplied input. TR-028 requires an exact
    prior evaluation for the same order and a materially different complete input.
    TR-031..038 are the top-level route selected by the recomputed evaluation itself.
    """

    from synthetic_sales_assist.doi.evaluator import evaluate_doi
    from synthetic_sales_assist.doi.models import DOIEvaluation, DOIEvaluationInput

    supported = frozenset(
        {
            "TR-027",
            "TR-028",
            "TR-031",
            "TR-032",
            "TR-033",
            "TR-034",
            "TR-035",
            "TR-036",
            "TR-037",
            "TR-038",
        }
    )
    derived = (
        evaluate_doi(evaluation_input)
        if type(evaluation_input) is DOIEvaluationInput
        else None
    )
    if (
        transition.transition_id not in supported
        or type(evaluation) is not DOIEvaluation
        or type(derived) is not DOIEvaluation
        or derived.canonical_bytes() != evaluation.canonical_bytes()
        or evaluation.input_binding != evaluation_input.hash_binding()
        or evaluation.snapshot_id != evaluation_input.snapshot.snapshot_id
        or evaluation.run_id != evaluation_input.snapshot.run_id
        or evaluation.order_id != evaluation_input.snapshot.order_id
        or stream_id != evaluation_transition_stream_id(evaluation)
        or occurrence_id != evaluation_transition_occurrence_id(evaluation)
    ):
        raise LifecycleConflictError(
            "EVALUATION_REDUCTION_OWNER_INVALID",
            reason=_reason("RC-081"),
        )

    transition_id = transition.transition_id
    if transition_id == "TR-027":
        if prior_evaluation is not None or transition not in evaluation.append_transitions:
            raise LifecycleConflictError(
                "EVALUATION_APPEND_ROUTE_INVALID",
                reason=_reason("RC-081"),
            )
    elif transition_id == "TR-028":
        if (
            type(prior_evaluation) is not DOIEvaluation
            or prior_evaluation.order_id != evaluation.order_id
            or prior_evaluation.evaluation_id == evaluation.evaluation_id
            or prior_evaluation.input_binding == evaluation.input_binding
        ):
            raise LifecycleConflictError(
                "EVALUATION_REEVALUATION_ROUTE_INVALID",
                reason=_reason("RC-081"),
            )
    elif (
        prior_evaluation is not None
        or evaluation.transition.transition_id != transition_id
    ):
        raise LifecycleConflictError(
            "EVALUATION_TOP_LEVEL_ROUTE_INVALID",
            reason=_reason("RC-081"),
        )

    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=evaluation_input.evaluated_at,
        evidence_kind=TransitionGuardEvidenceKind.EVALUATION_REDUCTION,
        evidence={
            "evaluation": _hash_dict(evaluation.hash_binding()),
            "evaluation_input": _hash_dict(evaluation_input.hash_binding()),
            "prior_evaluation": (
                None
                if prior_evaluation is None
                else _hash_dict(prior_evaluation.hash_binding())
            ),
            "selected_top_level_transition": evaluation.transition.transition_id,
        },
    )


def make_out_of_scope_closure_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    human_fact: object,
    case: object,
) -> TransitionGuardProof:
    """Derive TR-013 only from an authorized, scope-bound out-of-scope fact."""

    from synthetic_sales_assist.doi.models import (
        ActionContextState,
        CaseLifecycleState,
        DOIOrderCase,
        HumanFactResultCode,
        HumanFactUsageKind,
        StructuredHumanFact,
    )

    if (
        transition.transition_id != "TR-013"
        or type(human_fact) is not StructuredHumanFact
        or type(case) is not DOIOrderCase
        or stream_id != case.case_id
        or occurrence_id != human_fact.fact_id
        or case.order_id != human_fact.order_id
        or case.current_evaluation_id != human_fact.evaluation_id
        or case.lifecycle_state is not CaseLifecycleState.ACTIVE
        or human_fact.usage_kind is not HumanFactUsageKind.OUT_OF_SCOPE_CLOSURE
        or human_fact.result_code is not HumanFactResultCode.OUT_OF_SCOPE
        or human_fact.action_context.state is not ActionContextState.OPEN
        or human_fact.source != human_fact.authority_grant.source
        or human_fact.authority_grant.action_context_binding
        != human_fact.action_context.hash_binding()
        or (
            human_fact.occurred_at.epoch_seconds,
            human_fact.occurred_at.nanosecond,
        )
        < (
            human_fact.authority_grant.granted_at.epoch_seconds,
            human_fact.authority_grant.granted_at.nanosecond,
        )
    ):
        raise LifecycleConflictError(
            "OUT_OF_SCOPE_CLOSURE_EVIDENCE_INVALID",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=human_fact.occurred_at,
        evidence_kind=TransitionGuardEvidenceKind.STRUCTURED_HUMAN_FACT,
        evidence={
            "action_context": _hash_dict(human_fact.action_context.hash_binding()),
            "authority_grant": _hash_dict(human_fact.authority_grant.hash_binding()),
            "case": {
                "case_id": case.case_id.value,
                "current_evaluation_id": case.current_evaluation_id.value,
                "current_snapshot_id": (
                    None
                    if case.current_snapshot_id is None
                    else case.current_snapshot_id.to_json_value()
                ),
                "lifecycle_state": case.lifecycle_state.value,
                "order_id": case.order_id.to_json_value(),
            },
            "evaluation_id": human_fact.evaluation_id.value,
            "human_fact": _hash_dict(human_fact.hash_binding()),
            "order_id": human_fact.order_id.to_json_value(),
            "source": _hash_dict(human_fact.source.hash_binding()),
        },
    )


def make_human_review_evaluation_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    evaluation_input: object,
    evaluation: object,
    human_fact: object,
) -> TransitionGuardProof:
    """Derive TR-039 from its authorized fact and recomputed exact evaluation."""

    from synthetic_sales_assist.doi.evaluator import evaluate_doi
    from synthetic_sales_assist.doi.models import (
        DOIEvaluation,
        DOIEvaluationInput,
        DOIState,
        HumanFactResultCode,
        HumanFactUsageKind,
        StructuredHumanFact,
    )

    derived = (
        evaluate_doi(evaluation_input)
        if type(evaluation_input) is DOIEvaluationInput
        else None
    )
    if (
        transition.transition_id != "TR-039"
        or type(evaluation) is not DOIEvaluation
        or type(derived) is not DOIEvaluation
        or derived.canonical_bytes() != evaluation.canonical_bytes()
        or evaluation.transition.transition_id != "TR-039"
        or evaluation.state is not DOIState.DOI_MONITOR
        or type(human_fact) is not StructuredHumanFact
        or human_fact not in evaluation_input.human_facts
        or human_fact.usage_kind is not HumanFactUsageKind.NO_ACTION_DECISION
        or human_fact.result_code is not HumanFactResultCode.APPROVED
        or human_fact.evaluation_id != evaluation.evaluation_id
        or human_fact.order_id != evaluation.order_id
        or stream_id != evaluation_transition_stream_id(evaluation)
        or occurrence_id != human_fact.fact_id
    ):
        raise LifecycleConflictError(
            "HUMAN_REVIEW_EVALUATION_EVIDENCE_INVALID",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=human_fact.occurred_at,
        evidence_kind=TransitionGuardEvidenceKind.HUMAN_REVIEW_EVALUATION,
        evidence={
            "evaluation": _hash_dict(evaluation.hash_binding()),
            "evaluation_input": _hash_dict(evaluation_input.hash_binding()),
            "human_fact": _hash_dict(human_fact.hash_binding()),
        },
    )


def _validated_action_context_completion(history: object) -> tuple[object, object, object]:
    from synthetic_sales_assist.doi.models import (
        ActionContextEventType,
        ActionContextState,
        DOIActionContext,
        DOIActionContextHistory,
        reduce_action_context,
    )

    if type(history) is not DOIActionContextHistory or len(history.events) < 2:
        raise LifecycleConflictError(
            "ACTION_CONTEXT_COMPLETION_EVIDENCE_INVALID",
            reason=_reason("RC-081"),
        )
    replayed = _replay_action_context_history(history)
    opening_event = history.events[0]
    completion_event = history.events[-1]
    opened = reduce_action_context(
        DOIActionContextHistory(action_context_id=history.action_context_id),
        opening_event,
    )
    before_completion = DOIActionContextHistory(
        action_context_id=history.action_context_id
    )
    for retained in history.events[:-1]:
        before_completion = reduce_action_context(
            before_completion,
            retained,
        ).history
    if (
        opening_event.event_type is not ActionContextEventType.OPENED
        or completion_event.event_type is not ActionContextEventType.COMPLETED
        or replayed != history
        or type(opened.history.projection) is not DOIActionContext
        or type(before_completion.projection) is not DOIActionContext
        or type(replayed.projection) is not DOIActionContext
        or opened.history.projection.state is not ActionContextState.OPEN
        or before_completion.projection.state is not ActionContextState.OPEN
        or replayed.projection.state is not ActionContextState.CLOSED_COMPLETED
    ):
        raise LifecycleConflictError(
            "ACTION_CONTEXT_COMPLETION_EVIDENCE_INVALID",
            reason=_reason("RC-081"),
        )
    return opened.history.projection, replayed.projection, completion_event


def make_system_action_transition_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    action_event: object,
    action_context_history: object,
) -> TransitionGuardProof:
    """Derive TR-044 from a reducer-accepted SYSTEM_VERIFIED completion."""

    from synthetic_sales_assist.doi.interventions import ActionVerificationEvent
    from synthetic_sales_assist.doi.models import (
        ActionContextCompletionTrigger,
        ActionVerificationState,
        DOIActionContext,
    )

    _, completed_context, completion_event = _validated_action_context_completion(
        action_context_history
    )
    if type(action_event) is not ActionVerificationEvent:
        raise LifecycleConflictError(
            "SYSTEM_ACTION_EVIDENCE_INVALID",
            reason=_reason("RC-081"),
        )
    material = action_event.evidence.material
    if (
        transition.transition_id != "TR-044"
        or stream_id != action_event.intervention_id
        or occurrence_id != action_event.event_id
        or material.verification is not ActionVerificationState.SYSTEM_VERIFIED
        or material.authority_binding is not None
        or material.action_context_binding.domain != DOIActionContext.HASH_DOMAIN
        or material.action_context_binding != completed_context.hash_binding()
        or completed_context.completion_trigger
        is not ActionContextCompletionTrigger.SYSTEM_VERIFIED
        or material.occurred_at is None
        or material.occurred_at != completion_event.occurred_at
    ):
        raise LifecycleConflictError(
            "SYSTEM_ACTION_EVIDENCE_INVALID",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=material.occurred_at,
        evidence_kind=TransitionGuardEvidenceKind.SYSTEM_ACTION_VERIFICATION,
        evidence={
            "action_context": _hash_dict(material.action_context_binding),
            "action_event": _hash_dict(action_event.hash_binding()),
            "completion_event": _hash_dict(completion_event.hash_binding()),
            "intervention_id": action_event.intervention_id.value,
            "opportunity_id": action_event.opportunity_id.value,
            "verification_evidence": _hash_dict(action_event.evidence.hash_binding()),
            "verification_material": _hash_dict(material.hash_binding()),
        },
    )


def make_human_action_transition_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    action_event: object,
) -> TransitionGuardProof:
    """Derive TR-045 from a sealed completed HUMAN_ACCEPTED action event."""

    from synthetic_sales_assist.doi.interventions import ActionVerificationEvent
    from synthetic_sales_assist.doi.models import (
        ActionVerificationState,
        DOIActionContext,
        HumanAuthorityGrant,
    )

    if type(action_event) is not ActionVerificationEvent:
        raise LifecycleConflictError(
            "HUMAN_ACTION_EVIDENCE_INVALID",
            reason=_reason("RC-081"),
        )
    material = action_event.evidence.material
    if (
        transition.transition_id != "TR-045"
        or stream_id != action_event.intervention_id
        or occurrence_id != action_event.event_id
        or material.verification is not ActionVerificationState.HUMAN_VERIFIED
        or material.authority_binding is None
        or material.authority_binding.domain != HumanAuthorityGrant.HASH_DOMAIN
        or material.action_context_binding.domain != DOIActionContext.HASH_DOMAIN
        or material.occurred_at is None
    ):
        raise LifecycleConflictError(
            "HUMAN_ACTION_EVIDENCE_INVALID",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=material.occurred_at,
        evidence_kind=TransitionGuardEvidenceKind.HUMAN_ACTION_VERIFICATION,
        evidence={
            "action_context": _hash_dict(material.action_context_binding),
            "action_event": _hash_dict(action_event.hash_binding()),
            "authority_grant": _hash_dict(material.authority_binding),
            "intervention_id": action_event.intervention_id.value,
            "opportunity_id": action_event.opportunity_id.value,
            "verification_evidence": _hash_dict(action_event.evidence.hash_binding()),
            "verification_material": _hash_dict(material.hash_binding()),
        },
    )


def _replay_intervention(intervention: object) -> object:
    """Rebuild one retained intervention solely through its owning reducers."""

    from synthetic_sales_assist.doi.interventions import (
        DOIIntervention,
        InterventionError,
        append_value_event,
        record_verified_intervention,
    )

    if type(intervention) is not DOIIntervention:
        raise InterventionError("INTERVENTION_REPLAY_INPUT_INVALID")
    try:
        replayed = None
        for action_event in intervention.action_events:
            replayed = record_verified_intervention(
                replayed,
                action_event,
            ).intervention
        if type(replayed) is not DOIIntervention:
            raise InterventionError("INTERVENTION_REPLAY_INPUT_INVALID")
        for value_event in intervention.value_events:
            replayed = append_value_event(replayed, value_event).intervention
        if replayed != intervention:
            raise InterventionError("INTERVENTION_REPLAY_CONFLICT")
    except (AttributeError, TypeError):
        raise InterventionError("INTERVENTION_REPLAY_INPUT_INVALID") from None
    return replayed


def make_intervention_transition_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    prior_intervention: object | None,
    action_event: object,
) -> TransitionGuardProof:
    """Derive TR-045A from the exact DS intervention owner reduction."""

    from synthetic_sales_assist.doi.interventions import (
        ActionVerificationEvent,
        DOIIntervention,
        InterventionError,
        record_verified_intervention,
    )
    from synthetic_sales_assist.doi.models import (
        InterventionStatus,
        InterventionType,
        ValueVerificationState,
    )

    try:
        owner_invalid = (
            transition.transition_id != "TR-045A"
            or type(action_event) is not ActionVerificationEvent
            or stream_id != action_event.intervention_id
            or occurrence_id != action_event.event_id
        )
    except (AttributeError, TypeError):
        owner_invalid = True
    if owner_invalid:
        raise LifecycleConflictError(
            "INTERVENTION_REDUCTION_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    try:
        prior = (
            None
            if prior_intervention is None
            else _replay_intervention(prior_intervention)
        )
        result = record_verified_intervention(prior, action_event)
    except (AttributeError, InterventionError, TypeError):
        raise LifecycleConflictError(
            "INTERVENTION_REDUCTION_GUARD_NOT_SATISFIED",
            reason=_reason("RC-081"),
        ) from None
    projection = result.intervention
    occurred_at = action_event.evidence.material.occurred_at
    if (
        type(projection) is not DOIIntervention
        or action_event.intervention_type is not InterventionType.DS_SEPARATION
        or projection.intervention_type is not InterventionType.DS_SEPARATION
        or projection.status is not InterventionStatus.VERIFIED_ACTIVE
        or projection.value.verification is not ValueVerificationState.NOT_APPLICABLE
        or projection.value_events
        or projection.value.authoritative_original is not None
        or projection.value.reversed_value is not None
        or projection.value.net_value is not None
        or projection.value.authoritative_event_id is not None
        or type(occurred_at) is not CanonicalTimestamp
    ):
        raise LifecycleConflictError(
            "INTERVENTION_REDUCTION_ROUTE_INVALID",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=occurred_at,
        evidence_kind=TransitionGuardEvidenceKind.INTERVENTION_REDUCTION,
        evidence={
            "action_event": _hash_dict(action_event.hash_binding()),
            "prior_intervention": (
                None
                if prior_intervention is None
                else _hash_dict(prior_intervention.hash_binding())
            ),
            "result_intervention": _hash_dict(projection.hash_binding()),
            "result_replayed": result.replayed,
            "result_reasons": result.reasons.to_json_value(),
        },
    )


def make_value_reduction_transition_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    prior_intervention: object,
    value_event: object,
) -> TransitionGuardProof:
    """Derive TR-046..053 by replaying the exact intervention value reducer."""

    from synthetic_sales_assist.doi.interventions import (
        DOIIntervention,
        InterventionError,
        ValueCorrectionKind,
        ValueEvent,
        append_value_event,
        record_verified_intervention,
    )
    from synthetic_sales_assist.doi.models import (
        InterventionStatus,
        ValueEventType,
        ValueVerificationState,
    )

    try:
        owner_invalid = (
            type(prior_intervention) is not DOIIntervention
            or type(value_event) is not ValueEvent
            or stream_id != prior_intervention.intervention_id
            or occurrence_id != value_event.event_id
        )
    except (AttributeError, TypeError):
        owner_invalid = True
    if owner_invalid:
        raise LifecycleConflictError(
            "VALUE_REDUCTION_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    try:
        replayed = record_verified_intervention(
            None,
            prior_intervention.action_events[0],
        ).intervention
        for action_event in prior_intervention.action_events[1:]:
            replayed = record_verified_intervention(
                replayed,
                action_event,
            ).intervention
        for retained_value_event in prior_intervention.value_events:
            replayed = append_value_event(
                replayed,
                retained_value_event,
            ).intervention
        if replayed != prior_intervention:
            raise InterventionError("INTERVENTION_VALUE_HISTORY_INVALID")
        result = append_value_event(replayed, value_event)
    except (AttributeError, InterventionError, TypeError):
        raise LifecycleConflictError(
            "VALUE_REDUCTION_GUARD_NOT_SATISFIED",
            reason=_reason("RC-081"),
        ) from None
    if (
        result.replayed
        or result.intervention.value_events[-1] != value_event
        or result.intervention.intervention_id != prior_intervention.intervention_id
    ):
        raise LifecycleConflictError(
            "VALUE_REDUCTION_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    transition_id = transition.transition_id
    prior_human_original = any(
        event.event_type is ValueEventType.INITIAL_VERIFIED_VALUE
        and event.verification is ValueVerificationState.HUMAN_VERIFIED
        for event in prior_intervention.value_events
    )
    route_valid = {
        "TR-046": (
            value_event.event_type is ValueEventType.INITIAL_VERIFIED_VALUE
            and value_event.verification is ValueVerificationState.SYSTEM_VERIFIED
            and not prior_intervention.value_events
        ),
        "TR-047": (
            value_event.event_type is ValueEventType.INITIAL_VERIFIED_VALUE
            and value_event.verification is ValueVerificationState.HUMAN_VERIFIED
            and not prior_intervention.value_events
        ),
        "TR-048": (
            value_event.event_type is ValueEventType.CORRECTION
            or (
                value_event.event_type is ValueEventType.INITIAL_VERIFIED_VALUE
                and value_event.verification
                is ValueVerificationState.SYSTEM_VERIFIED
                and prior_human_original
            )
        ),
        "TR-049": (
            bool(prior_intervention.value_events)
            and result.intervention.status is InterventionStatus.VERIFIED_ACTIVE
        ),
        "TR-050": (
            result.intervention.status is InterventionStatus.PARTIALLY_REVERSED
        ),
        "TR-051": result.intervention.status is InterventionStatus.REVERSED,
        "TR-052": (
            value_event.event_type is ValueEventType.CORRECTION
            and value_event.correction_kind
            in {
                ValueCorrectionKind.REVERSAL_CORRECTED,
                ValueCorrectionKind.REVERSAL_VOIDED,
            }
        ),
        "TR-053": (
            value_event.event_type is ValueEventType.CORRECTION
            and value_event.correction_kind
            is ValueCorrectionKind.ORIGINAL_VALUE_CORRECTED
        ),
    }.get(transition_id, False)
    if not route_valid:
        raise LifecycleConflictError(
            "VALUE_REDUCTION_ROUTE_INVALID",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=value_event.occurred_at,
        evidence_kind=TransitionGuardEvidenceKind.VALUE_REDUCTION,
        evidence={
            "prior_intervention": _hash_dict(prior_intervention.hash_binding()),
            "result_intervention": _hash_dict(result.intervention.hash_binding()),
            "result_reasons": result.reasons.to_json_value(),
            "value_event": _hash_dict(value_event.hash_binding()),
        },
    )


def _replay_resulting_link(
    prior_link: object,
    intervention: object,
) -> object:
    """Rebuild an exact-link projection from every retained typed revision."""

    from synthetic_sales_assist.doi.interventions import (
        DOIIntervention,
        DOIResultingOrderLink,
        InterventionError,
        append_resulting_link_revision,
    )

    if (
        type(prior_link) is not DOIResultingOrderLink
        or type(intervention) is not DOIIntervention
    ):
        raise InterventionError("RESULTING_LINK_REPLAY_INPUT_INVALID")
    replayed = None
    for revision in prior_link.revisions:
        result = append_resulting_link_revision(
            replayed,
            revision_id=revision.revision_id,
            intervention=intervention,
            evidence=revision.evidence_record,
        )
        if result.replayed:
            raise InterventionError("RESULTING_LINK_REPLAY_INVALID")
        replayed = result.link
    if replayed != prior_link:
        raise InterventionError("RESULTING_LINK_REPLAY_CONFLICT")
    return replayed


def make_resulting_link_transition_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    prior_link: object | None,
    intervention: object,
    evidence: object,
) -> TransitionGuardProof:
    """Derive TR-054..059/090/091/110/111 from one exact link append."""

    from synthetic_sales_assist.doi.interventions import (
        AuthorizedHumanResultingLinkEvidence,
        DOIIntervention,
        DOIResultingOrderLink,
        InterventionError,
        SystemResultingLinkEvidence,
        append_resulting_link_revision,
    )
    from synthetic_sales_assist.doi.models import ResultingOrderLinkState

    try:
        owner_invalid = (
            type(intervention) is not DOIIntervention
            or type(evidence)
            not in {
                SystemResultingLinkEvidence,
                AuthorizedHumanResultingLinkEvidence,
            }
            or stream_id != evidence.link_id
        )
    except (AttributeError, TypeError):
        owner_invalid = True
    if owner_invalid:
        raise LifecycleConflictError(
            "RESULTING_LINK_REDUCTION_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    try:
        prior = (
            None
            if prior_link is None
            else _replay_resulting_link(prior_link, intervention)
        )
        result = append_resulting_link_revision(
            prior,
            revision_id=occurrence_id,
            intervention=intervention,
            evidence=evidence,
        )
    except (AttributeError, InterventionError, TypeError):
        raise LifecycleConflictError(
            "RESULTING_LINK_REDUCTION_GUARD_NOT_SATISFIED",
            reason=_reason("RC-081"),
        ) from None
    if (
        result.replayed
        or type(result.link) is not DOIResultingOrderLink
        or result.link.link_id != stream_id
        or result.link.revisions[-1].revision_id != occurrence_id
    ):
        raise LifecycleConflictError(
            "RESULTING_LINK_REDUCTION_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    system_evidence = type(evidence) is SystemResultingLinkEvidence
    human_evidence = type(evidence) is AuthorizedHumanResultingLinkEvidence
    result_state = result.link.state
    prior_state = None if prior is None else prior.state
    same_mapping = (
        False
        if prior is None
        else prior.revisions[-1].mappings == result.link.revisions[-1].mappings
    )
    verified_initial_or_resolution = (
        (
            prior is None
            and result_state
            in {
                ResultingOrderLinkState.AUTO_LINKED,
                ResultingOrderLinkState.HUMAN_CONFIRMED,
            }
        )
        or (
            prior_state is ResultingOrderLinkState.AMBIGUOUS
            and result_state
            in {
                ResultingOrderLinkState.AUTO_LINKED,
                ResultingOrderLinkState.HUMAN_CONFIRMED,
            }
        )
    )
    contradictory_revision = (
        prior_state
        in {
            ResultingOrderLinkState.AUTO_LINKED,
            ResultingOrderLinkState.HUMAN_CONFIRMED,
        }
        and result_state is ResultingOrderLinkState.AMBIGUOUS
        and not same_mapping
    )
    route_valid = {
        "TR-054": (
            prior is None
            and system_evidence
            and result_state is ResultingOrderLinkState.AUTO_LINKED
        ),
        "TR-055": (
            prior is None
            and human_evidence
            and result_state is ResultingOrderLinkState.HUMAN_CONFIRMED
        ),
        "TR-056": (
            prior_state is ResultingOrderLinkState.AMBIGUOUS
            and system_evidence
            and result_state is ResultingOrderLinkState.AUTO_LINKED
        ),
        "TR-057": (
            prior_state is ResultingOrderLinkState.AMBIGUOUS
            and human_evidence
            and result_state is ResultingOrderLinkState.HUMAN_CONFIRMED
        ),
        "TR-058": (
            prior_state is ResultingOrderLinkState.AUTO_LINKED
            and contradictory_revision
        ),
        "TR-059": (
            prior_state is ResultingOrderLinkState.HUMAN_CONFIRMED
            and system_evidence
            and contradictory_revision
        ),
        "TR-090": (
            prior_state
            in {
                ResultingOrderLinkState.AUTO_LINKED,
                ResultingOrderLinkState.HUMAN_CONFIRMED,
            }
            and result_state is prior_state
            and same_mapping
        ),
        "TR-091": (
            prior_state is ResultingOrderLinkState.HUMAN_CONFIRMED
            and system_evidence
            and result_state is ResultingOrderLinkState.AUTO_LINKED
            and same_mapping
        ),
        "TR-110": verified_initial_or_resolution,
        "TR-111": contradictory_revision,
    }.get(transition.transition_id, False)
    if not route_valid:
        raise LifecycleConflictError(
            "RESULTING_LINK_REDUCTION_ROUTE_INVALID",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=evidence.observed_at,
        evidence_kind=TransitionGuardEvidenceKind.RESULTING_LINK_REDUCTION,
        evidence={
            "intervention": _hash_dict(intervention.hash_binding()),
            "owner_evidence": _hash_dict(evidence.hash_binding()),
            "prior_link": (
                None if prior is None else _hash_dict(prior.hash_binding())
            ),
            "result_link": _hash_dict(result.link.hash_binding()),
            "result_reasons": result.reasons.to_json_value(),
            "result_revision": _hash_dict(
                result.link.revisions[-1].hash_binding()
            ),
        },
    )


def make_resulting_link_search_transition_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    prior_history: object,
    evidence: object,
) -> TransitionGuardProof:
    """Derive TR-088/089 by replaying the complete exact-link search history."""

    from synthetic_sales_assist.doi.interventions import (
        DOIResultingOrderLinkSearchHistory,
        InterventionError,
        ResultingLinkSearchEvidence,
        ResultingOrderLinkSearchState,
        append_resulting_link_search,
    )

    try:
        owner_invalid = (
            type(prior_history) is not DOIResultingOrderLinkSearchHistory
            or type(evidence) is not ResultingLinkSearchEvidence
            or stream_id != prior_history.search_id
            or stream_id != evidence.search_id
        )
    except (AttributeError, TypeError):
        owner_invalid = True
    if owner_invalid:
        raise LifecycleConflictError(
            "RESULTING_LINK_SEARCH_REDUCTION_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    try:
        replayed = DOIResultingOrderLinkSearchHistory(
            search_id=prior_history.search_id,
            parent_order_id=prior_history.parent_order_id,
            intervention_type=prior_history.intervention_type,
        )
        for retained in prior_history.events:
            replayed = append_resulting_link_search(
                replayed,
                event_id=retained.event_id,
                evidence=retained.evidence,
            ).history
        if replayed != prior_history:
            raise InterventionError("RESULTING_LINK_SEARCH_REPLAY_CONFLICT")
        result = append_resulting_link_search(
            replayed,
            event_id=occurrence_id,
            evidence=evidence,
        )
    except (AttributeError, InterventionError, TypeError):
        raise LifecycleConflictError(
            "RESULTING_LINK_SEARCH_REDUCTION_GUARD_NOT_SATISFIED",
            reason=_reason("RC-081"),
        ) from None
    if (
        result.replayed
        or result.event.event_id != occurrence_id
        or result.history.events[-1] != result.event
        or result.history.projection is None
    ):
        raise LifecycleConflictError(
            "RESULTING_LINK_SEARCH_REDUCTION_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    route_valid = {
        "TR-088": (
            result.history.projection.state
            is ResultingOrderLinkSearchState.NOT_FOUND
        ),
        "TR-089": (
            result.history.projection.state
            is ResultingOrderLinkSearchState.AMBIGUOUS
        ),
    }.get(transition.transition_id, False)
    if not route_valid:
        raise LifecycleConflictError(
            "RESULTING_LINK_SEARCH_REDUCTION_ROUTE_INVALID",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=evidence.observed_at,
        evidence_kind=TransitionGuardEvidenceKind.RESULTING_LINK_SEARCH_REDUCTION,
        evidence={
            "owner_evidence": _hash_dict(evidence.hash_binding()),
            "prior_event_bindings": [
                _hash_dict(item.hash_binding()) for item in prior_history.events
            ],
            "prior_projection": (
                None
                if prior_history.projection is None
                else _hash_dict(prior_history.projection.hash_binding())
            ),
            "result_event": _hash_dict(result.event.hash_binding()),
            "result_projection": _hash_dict(
                result.history.projection.hash_binding()
            ),
            "result_reasons": result.reasons.to_json_value(),
        },
    )


def make_kpi_contribution_transition_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    prior_history: object,
    prior_interventions: tuple[object, ...],
    prior_resulting_links: tuple[object | None, ...],
    prior_currency_evidence: tuple[object | None, ...],
    intervention: object,
    resulting_link: object | None,
    currency_evidence: object | None = None,
) -> TransitionGuardProof:
    """Derive TR-106..109 from a fully replayed retained KPI history."""

    from synthetic_sales_assist.doi.interventions import (
        DOIIntervention,
        DOIResultingOrderLink,
        InterventionError,
    )
    from synthetic_sales_assist.doi.models import (
        InterventionType,
        ResultingOrderLinkState,
    )
    from synthetic_sales_assist.doi.retention import (
        DoiRetentionError,
        KPIContributionEventKind,
        KPIContributionHistory,
        VerifiedCurrencyEnvelope,
        reduce_kpi_contribution,
    )

    try:
        owner_invalid = (
            type(prior_history) is not KPIContributionHistory
            or type(prior_interventions) is not tuple
            or type(prior_resulting_links) is not tuple
            or type(prior_currency_evidence) is not tuple
            or len(prior_interventions) != len(prior_history.events)
            or len(prior_resulting_links) != len(prior_history.events)
            or len(prior_currency_evidence) != len(prior_history.events)
            or type(intervention) is not DOIIntervention
            or stream_id != intervention.intervention_id
            or stream_id != prior_history.intervention_id
            or occurrence_id.value == ""
            or (
                resulting_link is not None
                and type(resulting_link) is not DOIResultingOrderLink
            )
            or (
                currency_evidence is not None
                and type(currency_evidence) is not VerifiedCurrencyEnvelope
            )
        )
    except (AttributeError, TypeError):
        owner_invalid = True
    if owner_invalid:
        raise LifecycleConflictError(
            "KPI_CONTRIBUTION_REDUCTION_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    try:
        current_intervention = _replay_intervention(intervention)
        replayed = KPIContributionHistory(
            intervention_id=prior_history.intervention_id,
            intervention_type=prior_history.intervention_type,
        )
        for retained, snapshot, link, envelope in zip(
            prior_history.events,
            prior_interventions,
            prior_resulting_links,
            prior_currency_evidence,
            strict=True,
        ):
            snapshot = _replay_intervention(snapshot)
            replay_result = reduce_kpi_contribution(
                replayed,
                event_id=retained.event_id,
                intervention=snapshot,
                resulting_link=link,
                currency_evidence=envelope,
            )
            if (
                replay_result.replayed
                or replay_result.event != retained
                or replay_result.history is None
            ):
                raise DoiRetentionError("KPI_CONTRIBUTION_REPLAY_INVALID")
            replayed = replay_result.history
        if replayed != prior_history:
            raise DoiRetentionError("KPI_CONTRIBUTION_REPLAY_CONFLICT")
        result = reduce_kpi_contribution(
            replayed,
            event_id=occurrence_id,
            intervention=current_intervention,
            resulting_link=resulting_link,
            currency_evidence=currency_evidence,
        )
    except (AttributeError, DoiRetentionError, InterventionError, TypeError):
        raise LifecycleConflictError(
            "KPI_CONTRIBUTION_REDUCTION_GUARD_NOT_SATISFIED",
            reason=_reason("RC-081"),
        ) from None
    occurrence_valid = (
        result.event.event_id == occurrence_id
        if result.event is not None
        else occurrence_id == current_intervention.action_events[0].event_id
    )
    if result.replayed or result.history is None or not occurrence_valid:
        raise LifecycleConflictError(
            (
                "KPI_CONTRIBUTION_REDUCTION_OWNER_INVALID"
                if occurrence_valid
                else "KPI_CONTRIBUTION_REDUCTION_OCCURRENCE_INVALID"
            ),
            reason=_reason("RC-081"),
        )
    if intervention.intervention_type is InterventionType.DS_SEPARATION:
        link_scope_valid = resulting_link is None
    else:
        link_scope_valid = (
            type(resulting_link) is DOIResultingOrderLink
            and resulting_link.state
            in {
                ResultingOrderLinkState.AUTO_LINKED,
                ResultingOrderLinkState.HUMAN_CONFIRMED,
            }
        )
    event_kind = None if result.event is None else result.event.kind
    route_valid = {
        "TR-106": not prior_history.events,
        "TR-107": event_kind is KPIContributionEventKind.ORIGINAL_VALUE,
        "TR-108": event_kind is KPIContributionEventKind.VALUE_CORRECTION,
        "TR-109": event_kind is KPIContributionEventKind.REVERSAL_RECOMPUTE,
    }.get(transition.transition_id, False)
    if not link_scope_valid or not route_valid:
        raise LifecycleConflictError(
            "KPI_CONTRIBUTION_REDUCTION_ROUTE_INVALID",
            reason=_reason("RC-081"),
        )
    if result.event is not None:
        satisfied_at = result.event.action_occurred_at
    elif type(intervention.action_occurred_at) is CanonicalTimestamp:
        satisfied_at = intervention.action_occurred_at
    elif type(currency_evidence) is VerifiedCurrencyEnvelope:
        satisfied_at = currency_evidence.observed_at
    elif type(resulting_link) is DOIResultingOrderLink:
        satisfied_at = resulting_link.revisions[-1].evidence_record.observed_at
    else:
        satisfied_at = None
    if type(satisfied_at) is not CanonicalTimestamp:
        raise LifecycleConflictError(
            "KPI_CONTRIBUTION_REDUCTION_TIME_INVALID",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=satisfied_at,
        evidence_kind=TransitionGuardEvidenceKind.KPI_CONTRIBUTION_REDUCTION,
        evidence={
            "currency_evidence": (
                None
                if currency_evidence is None
                else _hash_dict(currency_evidence.hash_binding())
            ),
            "intervention": _hash_dict(intervention.hash_binding()),
            "prior_event_bindings": [
                _hash_dict(item.hash_binding()) for item in prior_history.events
            ],
            "prior_projection": (
                None
                if prior_history.projection is None
                else _hash_dict(prior_history.projection.hash_binding())
            ),
            "result_contribution": (
                None
                if result.contribution is None
                else _hash_dict(result.contribution.hash_binding())
            ),
            "result_event": (
                None
                if result.event is None
                else _hash_dict(result.event.hash_binding())
            ),
            "result_reasons": result.reasons.to_json_value(),
            "resulting_link": (
                None
                if resulting_link is None
                else _hash_dict(resulting_link.hash_binding())
            ),
        },
    )


def make_dedupe_reduction_transition_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    prior_history: object,
    event: object,
) -> TransitionGuardProof:
    """Derive DEDUPE lifecycle routes from a replayed typed history append."""

    from synthetic_sales_assist.doi.models import (
        DedupeEventType,
        DedupeState,
        DOIDedupeEvent,
        DOIDedupeHistory,
        DOIModelError,
        DOIState,
        reduce_dedupe,
    )

    if (
        type(prior_history) is not DOIDedupeHistory
        or type(event) is not DOIDedupeEvent
        or stream_id != prior_history.projection.stream_id
        or occurrence_id != event.event_id
    ):
        raise LifecycleConflictError(
            "DEDUPE_REDUCTION_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    try:
        replayed = DOIDedupeHistory.empty(
            stream_id=prior_history.projection.stream_id,
            order_id=prior_history.projection.order_id,
        )
        for retained_event in prior_history.events:
            replayed = reduce_dedupe(replayed, retained_event).history
        if replayed != prior_history:
            raise LifecycleConflictError(
                "DEDUPE_REDUCTION_HISTORY_INVALID",
                reason=_reason("RC-081"),
            )
        result = reduce_dedupe(prior_history, event)
    except DOIModelError:
        raise LifecycleConflictError(
            "DEDUPE_REDUCTION_GUARD_NOT_SATISFIED",
            reason=_reason("RC-081"),
        ) from None
    if result.replayed:
        raise LifecycleConflictError(
            "DEDUPE_REDUCTION_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    route = {
        "TR-060": (
            DedupeEventType.CANDIDATE_IDENTIFIED,
            frozenset({DedupeState.NOT_CANDIDATE, DedupeState.REJECTED}),
            DedupeState.CANDIDATE,
        ),
        "TR-061": (
            DedupeEventType.HUMAN_APPROVED,
            frozenset({DedupeState.CANDIDATE}),
            DedupeState.APPROVED_AWAITING_VERIFICATION,
        ),
        "TR-062": (
            DedupeEventType.HUMAN_REJECTED,
            frozenset(
                {
                    DedupeState.CANDIDATE,
                    DedupeState.APPROVED_AWAITING_VERIFICATION,
                }
            ),
            DedupeState.REJECTED,
        ),
        "TR-063": (
            DedupeEventType.VERIFIED_SOURCE_CONFIRMED,
            frozenset({DedupeState.APPROVED_AWAITING_VERIFICATION}),
            DedupeState.CONFIRMED,
        ),
        "TR-064": (
            DedupeEventType.ELIGIBILITY_RETURNED,
            frozenset({DedupeState.CONFIRMED}),
            DedupeState.NOT_CANDIDATE,
        ),
        "TR-096": (
            DedupeEventType.CANDIDATE_WITHDRAWN,
            frozenset(
                {
                    DedupeState.CANDIDATE,
                    DedupeState.APPROVED_AWAITING_VERIFICATION,
                    DedupeState.REJECTED,
                }
            ),
            DedupeState.NOT_CANDIDATE,
        ),
    }.get(transition.transition_id)
    if route is None or (
        event.event_type is not route[0]
        or prior_history.projection.state not in route[1]
        or result.history.projection.state is not route[2]
        or (
            transition.transition_id == "TR-064"
            and event.evaluation.state is not DOIState.DOI_OPPORTUNITY
        )
        or (
            transition.transition_id == "TR-096"
            and event.evaluation.state
            not in {DOIState.DOI_OPPORTUNITY, DOIState.DOI_EXCLUDED}
        )
    ):
        raise LifecycleConflictError(
            "DEDUPE_REDUCTION_ROUTE_INVALID",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=event.recorded_at,
        evidence_kind=TransitionGuardEvidenceKind.DEDUPE_REDUCTION,
        evidence={
            "event": _hash_dict(event.hash_binding()),
            "prior_projection": _hash_dict(
                prior_history.projection.hash_binding()
            ),
            "result_projection": _hash_dict(
                result.history.projection.hash_binding()
            ),
        },
    )


def make_human_fact_reduction_transition_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    prior_history: object,
    event: object,
) -> TransitionGuardProof:
    """Derive TR-097 from a replayed authorized human-fact history append."""

    from synthetic_sales_assist.doi.models import (
        DOIHumanFactEvent,
        DOIHumanFactHistory,
        DOIModelError,
        reduce_human_fact,
    )

    if (
        transition.transition_id != "TR-097"
        or type(prior_history) is not DOIHumanFactHistory
        or type(event) is not DOIHumanFactEvent
        or stream_id != prior_history.stream_id
        or occurrence_id != event.event_id
    ):
        raise LifecycleConflictError(
            "HUMAN_FACT_REDUCTION_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    try:
        replayed = DOIHumanFactHistory(stream_id=prior_history.stream_id)
        for retained_event in prior_history.events:
            replayed = reduce_human_fact(replayed, retained_event).history
        if replayed != prior_history:
            raise LifecycleConflictError(
                "HUMAN_FACT_REDUCTION_HISTORY_INVALID",
                reason=_reason("RC-081"),
            )
        result = reduce_human_fact(prior_history, event)
    except DOIModelError:
        raise LifecycleConflictError(
            "HUMAN_FACT_REDUCTION_GUARD_NOT_SATISFIED",
            reason=_reason("RC-081"),
        ) from None
    if result.replayed or result.history.events[-1] != event:
        raise LifecycleConflictError(
            "HUMAN_FACT_REDUCTION_OWNER_INVALID",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=event.recorded_at,
        evidence_kind=TransitionGuardEvidenceKind.HUMAN_FACT_REDUCTION,
        evidence={
            "event": _hash_dict(event.hash_binding()),
            "fact": _hash_dict(event.fact.hash_binding()),
            "result_projection": _hash_dict(
                result.history.projection.hash_binding()
            ),
        },
    )


def make_action_context_completion_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    action_context_history: object,
) -> TransitionGuardProof:
    """Derive TR-086 from its exact reducer-accepted completion event/history."""

    from synthetic_sales_assist.doi.models import ActionContextCompletionTrigger

    opening_context, completed_context, completion_event = (
        _validated_action_context_completion(action_context_history)
    )
    if (
        transition.transition_id != "TR-086"
        or stream_id != completed_context.action_context_id
        or occurrence_id != completion_event.event_id
        or completed_context.completion_trigger
        not in {
            ActionContextCompletionTrigger.HUMAN_ACCEPTED,
            ActionContextCompletionTrigger.SYSTEM_VERIFIED,
        }
    ):
        raise LifecycleConflictError(
            "ACTION_CONTEXT_COMPLETION_EVIDENCE_INVALID",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=completion_event.occurred_at,
        evidence_kind=TransitionGuardEvidenceKind.ACTION_CONTEXT_COMPLETION,
        evidence={
            "completed_context": _hash_dict(completed_context.hash_binding()),
            "completion_event": _hash_dict(completion_event.hash_binding()),
            "completion_trigger": completed_context.completion_trigger.value,
            "opening_context": _hash_dict(opening_context.hash_binding()),
        },
    )


def make_closure_transition_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    evaluation_input: object,
    evaluation: object,
    case: object | None = None,
) -> TransitionGuardProof:
    """Derive a closure guard from one complete input and its bound evaluation."""

    from synthetic_sales_assist.doi.evaluator import evaluate_doi
    from synthetic_sales_assist.doi.models import (
        CaseLifecycleState,
        DOIEvaluation,
        DOIEvaluationInput,
        DOIOrderCase,
        SourcePresence,
        TerminalClosureReason,
    )

    transition_id = transition.transition_id
    derived_evaluation = (
        evaluate_doi(evaluation_input)
        if type(evaluation_input) is DOIEvaluationInput
        else None
    )
    if (
        transition_id not in _CLOSURE_EVIDENCE_TRANSITION_IDS
        or type(evaluation_input) is not DOIEvaluationInput
        or type(evaluation) is not DOIEvaluation
        or type(derived_evaluation) is not DOIEvaluation
        or derived_evaluation.canonical_bytes() != evaluation.canonical_bytes()
        or evaluation.input_binding != evaluation_input.hash_binding()
        or evaluation.snapshot_id != evaluation_input.snapshot.snapshot_id
        or evaluation.run_id != evaluation_input.snapshot.run_id
        or evaluation.order_id != evaluation_input.snapshot.order_id
        or evaluation_input.snapshot.source_presence is not SourcePresence.PRESENT
        or evaluation.closure_proposal is None
    ):
        raise LifecycleConflictError(
            "CLOSURE_EVALUATION_EVIDENCE_INVALID",
            reason=_reason("RC-081"),
        )
    reason = evaluation.closure_proposal.reason
    state = evaluation.closure_proposal.lifecycle_state
    exact_reasons = {
        "TR-009": frozenset({TerminalClosureReason.SHIPPED}),
        "TR-010": frozenset({TerminalClosureReason.CANCELED}),
        "TR-011": frozenset({TerminalClosureReason.REP_TRANSFERRED}),
        "TR-012": frozenset({TerminalClosureReason.DEDUPE_CONFIRMED}),
        "TR-016": frozenset({TerminalClosureReason.SHIPPED}),
        "TR-017": frozenset({TerminalClosureReason.CANCELED}),
        "TR-029": frozenset(
            {TerminalClosureReason.SHIPPED, TerminalClosureReason.CANCELED}
        ),
        "TR-030": frozenset(
            {
                TerminalClosureReason.REP_TRANSFERRED,
                TerminalClosureReason.DEDUPE_CONFIRMED,
                TerminalClosureReason.HUMAN_OUT_OF_SCOPE,
            }
        ),
    }
    expected_state = (
        CaseLifecycleState.CLOSED_HARD
        if transition_id in {"TR-009", "TR-010", "TR-016", "TR-017", "TR-029"}
        else CaseLifecycleState.CLOSED_REVERSIBLE
    )
    if reason not in exact_reasons[transition_id] or state is not expected_state:
        raise LifecycleConflictError(
            "CLOSURE_EVALUATION_EVIDENCE_INVALID",
            reason=_reason("RC-081"),
        )
    if transition_id == "TR-012" and evaluation_input.dedupe_verification is None:
        raise LifecycleConflictError(
            "CLOSURE_EVALUATION_EVIDENCE_INVALID",
            reason=_reason("RC-081"),
        )
    case_routes = frozenset(
        {"TR-009", "TR-010", "TR-011", "TR-012", "TR-016", "TR-017"}
    )
    evaluation_routes = frozenset({"TR-029", "TR-030"})
    owner_evidence: dict[str, object]
    if transition_id in case_routes:
        expected_case_state = (
            CaseLifecycleState.ACTIVE
            if transition_id in {"TR-009", "TR-010", "TR-011", "TR-012"}
            else CaseLifecycleState.CLOSED_REVERSIBLE
        )
        if (
            type(case) is not DOIOrderCase
            or stream_id != case.case_id
            or occurrence_id != evaluation_transition_occurrence_id(evaluation)
            or case.order_id != evaluation.order_id
            or case.current_snapshot_id != evaluation.snapshot_id
            or case.current_evaluation_id != evaluation.evaluation_id
            or case.lifecycle_state is not expected_case_state
        ):
            raise LifecycleConflictError(
                "CLOSURE_CASE_OWNER_BINDING_INVALID",
                reason=_reason("RC-081"),
            )
        owner_evidence = {
            "case_id": case.case_id.value,
            "current_evaluation_id": case.current_evaluation_id.value,
            "current_snapshot_id": case.current_snapshot_id.to_json_value(),
            "lifecycle_state": case.lifecycle_state.value,
            "order_id": case.order_id.to_json_value(),
        }
    elif transition_id in evaluation_routes:
        if (
            case is not None
            or stream_id != evaluation_transition_stream_id(evaluation)
            or occurrence_id != evaluation_transition_occurrence_id(evaluation)
        ):
            raise LifecycleConflictError(
                "CLOSURE_EVALUATION_OWNER_BINDING_INVALID",
                reason=_reason("RC-081"),
            )
        owner_evidence = {
            "evaluation_id": evaluation.evaluation_id.value,
            "stream_id": stream_id.value,
        }
    else:
        raise LifecycleSchemaError(
            "CLOSURE_EVALUATION_ROUTE_INVALID",
            reason=_reason("RC-113"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=evaluation_input.evaluated_at,
        evidence_kind=TransitionGuardEvidenceKind.COMPLETE_CLOSURE_EVALUATION,
        evidence={
            "closure_reason": reason.value,
            "closure_state": state.value,
            "completeness_proof": _hash_dict(
                evaluation_input.snapshot.completeness_proof.hash_binding()
            ),
            "evaluation": _hash_dict(evaluation.hash_binding()),
            "evaluation_input": _hash_dict(evaluation_input.hash_binding()),
            "owner": owner_evidence,
            "snapshot": _hash_dict(evaluation_input.snapshot.hash_binding()),
        },
    )


def make_case_recheck_transition_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    case: object,
    retention: object,
    evaluation_input: object,
    evaluation: object,
    supplied_prior_binding: object | None = None,
) -> TransitionGuardProof:
    """Derive TR-014/015 from exact case, recheck, and retention owners."""

    from synthetic_sales_assist.doi.evaluator import evaluate_doi
    from synthetic_sales_assist.doi.models import (
        CaseLifecycleState,
        DOIEvaluation,
        DOIEvaluationInput,
        DOIOrderCase,
        DOIState,
        SourcePresence,
    )
    from synthetic_sales_assist.doi.retention import (
        DoiRetentionError,
        DoiRetentionProjection,
        PriorClosureRetentionBindingV1,
        cancel_retention_on_reopen,
    )

    derived = (
        evaluate_doi(evaluation_input)
        if type(evaluation_input) is DOIEvaluationInput
        else None
    )
    if (
        transition.transition_id not in {"TR-014", "TR-015"}
        or type(case) is not DOIOrderCase
        or case.lifecycle_state is not CaseLifecycleState.CLOSED_REVERSIBLE
        or type(retention) is not DoiRetentionProjection
        or retention.purge_eligible_at is None
        or retention.binding.case_id != case.case_id
        or retention.binding.lifecycle_state
        is not CaseLifecycleState.CLOSED_REVERSIBLE
        or retention.binding.closure_reason != case.terminal_closure_reason
        or type(evaluation) is not DOIEvaluation
        or type(derived) is not DOIEvaluation
        or derived.canonical_bytes() != evaluation.canonical_bytes()
        or evaluation.order_id != case.order_id
        or evaluation.snapshot_id != case.current_snapshot_id
        or evaluation.evaluation_id != case.current_evaluation_id
        or evaluation_input.snapshot.source_presence is not SourcePresence.PRESENT
        or stream_id != case.case_id
        or occurrence_id != evaluation_transition_occurrence_id(evaluation)
    ):
        raise LifecycleConflictError(
            "CASE_RECHECK_OWNER_BINDING_INVALID",
            reason=_reason("RC-081"),
        )
    canceled = None
    if transition.transition_id == "TR-014":
        if (
            type(supplied_prior_binding) is not PriorClosureRetentionBindingV1
            or evaluation.closure_proposal is not None
            or evaluation.state not in {DOIState.DOI_OPPORTUNITY, DOIState.DOI_MONITOR}
        ):
            raise LifecycleConflictError(
                "CASE_REOPEN_EVALUATION_INVALID",
                reason=_reason("RC-081"),
            )
        try:
            canceled = cancel_retention_on_reopen(
                retention,
                supplied_binding=supplied_prior_binding,
                reopen_event_id=occurrence_id,
            )
        except DoiRetentionError:
            raise LifecycleConflictError(
                "CASE_REOPEN_RETENTION_INVALID",
                reason=_reason("RC-081"),
            ) from None
    elif (
        supplied_prior_binding is not None
        or evaluation.closure_proposal is None
        or evaluation.closure_proposal.lifecycle_state
        is not CaseLifecycleState.CLOSED_REVERSIBLE
        or evaluation.closure_proposal.reason != retention.binding.closure_reason
    ):
        raise LifecycleConflictError(
            "CASE_RECHECK_CLOSURE_INVALID",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=evaluation_input.evaluated_at,
        evidence_kind=TransitionGuardEvidenceKind.CASE_RECHECK_REDUCTION,
        evidence={
            "case": {
                "case_id": case.case_id.value,
                "current_evaluation_id": case.current_evaluation_id.value,
                "current_snapshot_id": case.current_snapshot_id.to_json_value(),
                "order_id": case.order_id.to_json_value(),
                "terminal_closure_reason": case.terminal_closure_reason.value,
            },
            "canceled_retention": (
                None
                if canceled is None
                else {
                    "binding": _hash_dict(canceled.binding.hash_binding()),
                    "canceled_by_reopen_event_id": (
                        canceled.canceled_by_reopen_event_id.value
                    ),
                }
            ),
            "evaluation": _hash_dict(evaluation.hash_binding()),
            "evaluation_input": _hash_dict(evaluation_input.hash_binding()),
            "retention_binding": _hash_dict(retention.binding.hash_binding()),
        },
    )


def make_case_purge_transition_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    graph: object,
    now: CanonicalTimestamp,
    existing_bucket: object | None,
    expected_contribution: object | None,
) -> TransitionGuardProof:
    """Derive TR-112 only by executing the pure retention reconciliation oracle."""

    from synthetic_sales_assist.doi.models import CaseLifecycleState
    from synthetic_sales_assist.doi.retention import (
        DOICaseGraph,
        DoiRetentionError,
        NonidentifyingKPIBucket,
        RetainedKPIContribution,
        finalize_case_purge,
    )

    transition_id = transition.transition_id
    expected_lifecycle = {
        "TR-018": CaseLifecycleState.CLOSED_HARD,
        "TR-019": CaseLifecycleState.CLOSED_REVERSIBLE,
    }.get(transition_id)
    if (
        transition_id not in {"TR-018", "TR-019", "TR-112"}
        or type(graph) is not DOICaseGraph
        or stream_id != graph.case_id
        or occurrence_id != case_purge_occurrence_id(transition, graph)
        or type(now) is not CanonicalTimestamp
        or type(existing_bucket) not in {NonidentifyingKPIBucket, type(None)}
        or type(expected_contribution) not in {RetainedKPIContribution, type(None)}
        or (
            expected_lifecycle is not None
            and graph.retention.binding.lifecycle_state is not expected_lifecycle
        )
    ):
        raise LifecycleConflictError(
            "CASE_PURGE_EVIDENCE_INVALID",
            reason=_reason("RC-081"),
        )
    try:
        result = finalize_case_purge(
            graph,
            now=now,
            existing_bucket=existing_bucket,
            expected_contribution=expected_contribution,
        )
    except DoiRetentionError as error:
        reason = (
            error.reasons.reasons[0]
            if error.reasons.reasons
            else _reason("RC-081")
        )
        raise LifecycleConflictError(
            "CASE_PURGE_GUARD_NOT_SATISFIED",
            reason=reason,
        ) from None
    contribution_binding = (
        None
        if graph.contribution is None
        else _hash_dict(graph.contribution.hash_binding())
    )
    existing_bucket_binding = (
        None
        if existing_bucket is None
        else _hash_dict(existing_bucket.hash_binding())
    )
    finalized_bucket_binding = (
        None
        if result.finalized_bucket is None
        else _hash_dict(result.finalized_bucket.hash_binding())
    )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=now,
        evidence_kind=TransitionGuardEvidenceKind.CASE_PURGE_RECONCILIATION,
        evidence={
            "case_id": graph.case_id.value,
            "contribution": contribution_binding,
            "existing_bucket": existing_bucket_binding,
            "finalized_bucket": finalized_bucket_binding,
            "graph_deleted": result.graph_deleted,
            "identity_node_count": len(graph.identity_nodes),
            "order_id": graph.order_id.to_json_value(),
            "purge_absence_noop": result.absence_noop,
            "purge_reasons": result.reasons.to_json_value(),
            "removed_identity_count": result.removed_identity_count,
            "retention_binding": _hash_dict(graph.retention.binding.hash_binding()),
            "transition_id": transition_id,
        },
    )


def make_observation_graph_deletion_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    observation: object,
    action_context_history: object,
    now: CanonicalTimestamp,
    active_case_retention: object | None = None,
    case: object | None = None,
) -> TransitionGuardProof:
    """Derive TR-043 from a terminal linked context and its exact due deadline."""

    from synthetic_sales_assist.doi.knowledge import (
        DOIAlternateObservation,
        DOIExactSKUObservation,
    )
    from synthetic_sales_assist.doi.retention import (
        DoiRetentionProjection,
        calendar90,
    )
    from synthetic_sales_assist.doi.models import DOIOrderCase

    opening_context, terminal_context, completion_event = (
        _validated_action_context_completion(action_context_history)
    )
    if (
        transition.transition_id != "TR-043"
        or type(observation) not in {DOIAlternateObservation, DOIExactSKUObservation}
        or type(now) is not CanonicalTimestamp
        or stream_id != observation.observation_id
        or occurrence_id != observation_deletion_occurrence_id(observation)
        or observation.action_context_id != opening_context.action_context_id
        or observation.action_context_binding != opening_context.hash_binding()
        or terminal_context.action_context_id != opening_context.action_context_id
        or type(active_case_retention) not in {DoiRetentionProjection, type(None)}
        or type(case) not in {DOIOrderCase, type(None)}
        or (active_case_retention is None) != (case is None)
        or (
            type(active_case_retention) is DoiRetentionProjection
            and (
                active_case_retention.purge_eligible_at is None
                or type(case) is not DOIOrderCase
                or case.case_id != active_case_retention.binding.case_id
                or case.order_id != opening_context.order_id
                or case.lifecycle_state
                is not active_case_retention.binding.lifecycle_state
            )
        )
    ):
        raise LifecycleConflictError(
            "OBSERVATION_DELETION_EVIDENCE_INVALID",
            reason=_reason("RC-081"),
        )
    nominal_deadline = calendar90(observation.observed_at)
    active_deadline = (
        active_case_retention.purge_eligible_at
        if type(active_case_retention) is DoiRetentionProjection
        else None
    )
    deadline = nominal_deadline
    if active_deadline is not None and (
        active_deadline.epoch_seconds,
        active_deadline.nanosecond,
    ) < (deadline.epoch_seconds, deadline.nanosecond):
        deadline = active_deadline
    if (now.epoch_seconds, now.nanosecond) < (
        deadline.epoch_seconds,
        deadline.nanosecond,
    ):
        raise LifecycleConflictError(
            "OBSERVATION_DELETION_NOT_DUE",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=now,
        evidence_kind=TransitionGuardEvidenceKind.OBSERVATION_GRAPH_DELETION,
        evidence={
            "active_case_retention": (
                None
                if active_case_retention is None
                else _hash_dict(active_case_retention.binding.hash_binding())
            ),
            "case": (
                None
                if case is None
                else {
                    "case_id": case.case_id.value,
                    "lifecycle_state": case.lifecycle_state.value,
                    "order_id": case.order_id.to_json_value(),
                }
            ),
            "completion_event": _hash_dict(completion_event.hash_binding()),
            "effective_deadline": deadline.value,
            "nominal_deadline": nominal_deadline.value,
            "observation": _hash_dict(observation.hash_binding()),
            "opening_context": _hash_dict(opening_context.hash_binding()),
            "terminal_context": _hash_dict(terminal_context.hash_binding()),
        },
    )


def make_identity_retention_purge_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    scheduled_decision: object,
    identity_record: object,
    terminal_run: object,
    run_control: object,
    source_batch: object | None = None,
    now: CanonicalTimestamp,
) -> TransitionGuardProof:
    """Derive identity deletion only through the exact retention purge reducer."""

    from synthetic_sales_assist.doi.retention import (
        DoiRetentionError,
        IdentityRetentionDecision,
        IdentityRetentionKind,
        IdentityRetentionState,
        finalize_identity_purge,
        schedule_identity_retention,
    )
    from synthetic_sales_assist.doi.source import (
        DOIRejectedSourceRecord,
        DOIRun,
        InMemoryDOIRunControl,
        RunControlConflict,
        DOISourceBatch,
        DOISourceImportAttempt,
        RunStatus,
    )

    transition_id = transition.transition_id
    expected_kind = {
        "TR-105": IdentityRetentionKind.REJECTED_SOURCE_RECORD,
        "TR-114": IdentityRetentionKind.SOURCE_IMPORT_ATTEMPT,
    }.get(transition_id)
    record_type = {
        "TR-105": DOIRejectedSourceRecord,
        "TR-114": DOISourceImportAttempt,
    }.get(transition_id)
    terminal = (
        type(terminal_run) is DOIRun
        and terminal_run.status is not RunStatus.IN_PROGRESS
        and terminal_run.completed_at is not None
    )
    controlled_run = None
    controlled_batch = None
    controlled_attempt = None
    if type(run_control) is InMemoryDOIRunControl and type(terminal_run) is DOIRun:
        try:
            controlled_run = run_control.run(terminal_run.run_id)
            if type(source_batch) is DOISourceBatch:
                controlled_batch = run_control.source_batch(source_batch.batch_id)
            if type(identity_record) is DOISourceImportAttempt:
                controlled_attempt = run_control.attempt(identity_record.attempt_id)
        except (RunControlConflict, ValueError):
            controlled_run = None
    record_binding = (
        identity_record.hash_binding()
        if type(identity_record) in {DOIRejectedSourceRecord, DOISourceImportAttempt}
        else None
    )
    exact_owner = False
    if record_type is DOIRejectedSourceRecord:
        exact_owner = (
            type(identity_record) is DOIRejectedSourceRecord
            and type(source_batch) is DOISourceBatch
            and controlled_run == terminal_run
            and controlled_batch == source_batch
            and identity_record in source_batch.rejected_records
            and terminal
            and terminal_run.source_batch_id == source_batch.batch_id
        )
    elif record_type is DOISourceImportAttempt:
        exact_owner = (
            type(identity_record) is DOISourceImportAttempt
            and source_batch is None
            and controlled_run == terminal_run
            and controlled_attempt == identity_record
            and terminal
            and identity_record.run_id == terminal_run.run_id
            and identity_record.state.value != "STARTED"
        )
    if (
        expected_kind is None
        or record_type is None
        or not exact_owner
        or type(record_binding) is not HashBinding
        or type(scheduled_decision) is not IdentityRetentionDecision
        or scheduled_decision.kind is not expected_kind
        or scheduled_decision.state is not IdentityRetentionState.SCHEDULED
        or type(now) is not CanonicalTimestamp
        or stream_id != identity_retention_stream_id(identity_record)
        or occurrence_id
        != identity_retention_occurrence_id(transition, identity_record)
        or scheduled_decision.retained_identity_binding != record_binding
    ):
        raise LifecycleConflictError(
            "IDENTITY_RETENTION_PURGE_EVIDENCE_INVALID",
            reason=_reason("RC-081"),
        )
    derived_schedule = schedule_identity_retention(
        kind=expected_kind,
        identity_binding=record_binding,
        run_completed_at=terminal_run.completed_at,
    )
    if derived_schedule != scheduled_decision:
        raise LifecycleConflictError(
            "IDENTITY_RETENTION_TERMINAL_CLOCK_INVALID",
            reason=_reason("RC-081"),
        )
    try:
        purged = finalize_identity_purge(scheduled_decision, now=now)
    except DoiRetentionError as error:
        reason = (
            error.reasons.reasons[0]
            if error.reasons.reasons
            else _reason("RC-081")
        )
        raise LifecycleConflictError(
            "IDENTITY_RETENTION_PURGE_NOT_DUE",
            reason=reason,
        ) from None
    retained = scheduled_decision.retained_identity_binding
    if type(retained) is not HashBinding or purged.retained_identity_binding is not None:
        raise LifecycleSchemaError(
            "IDENTITY_RETENTION_PURGE_DERIVATION_INVALID",
            reason=_reason("RC-113"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=now,
        evidence_kind=TransitionGuardEvidenceKind.IDENTITY_RETENTION_PURGE,
        evidence={
            "identity_kind": scheduled_decision.kind.value,
            "identity_record": _hash_dict(record_binding),
            "purge_eligible_at": scheduled_decision.purge_eligible_at.value,
            "purged_reasons": purged.transaction_reasons.to_json_value(),
            "retained_identity": _hash_dict(retained),
            "source_batch": (
                None
                if source_batch is None
                else _hash_dict(source_batch.hash_binding())
            ),
            "terminal_run": _hash_dict(terminal_run.hash_binding()),
            "transition_id": transition_id,
        },
    )


def make_source_batch_release_guard_proof(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    source_batch: object,
    run_control: object,
    now: CanonicalTimestamp,
) -> TransitionGuardProof:
    """Derive TR-113 release-or-delete authority from immutable batch run owners."""

    from synthetic_sales_assist.doi.source import (
        DOIRun,
        DOISourceBatch,
        InMemoryDOIRunControl,
        RunControlConflict,
        RunStatus,
    )

    owner_runs: tuple[object, ...] = ()
    retained_batch = None
    if type(source_batch) is DOISourceBatch and type(run_control) is InMemoryDOIRunControl:
        try:
            retained_batch = run_control.source_batch(source_batch.batch_id)
            owner_runs = run_control.runs_for_source_batch(source_batch.batch_id)
        except (RunControlConflict, ValueError):
            retained_batch = None

    if (
        transition.transition_id != "TR-113"
        or type(source_batch) is not DOISourceBatch
        or retained_batch != source_batch
        or stream_id != source_batch.batch_id.value
        or occurrence_id != source_batch_release_occurrence_id(source_batch)
        or type(owner_runs) is not tuple
        or not owner_runs
        or any(type(owner) is not DOIRun for owner in owner_runs)
        or any(owner.source_batch_id != source_batch.batch_id for owner in owner_runs)
        or type(now) is not CanonicalTimestamp
    ):
        raise LifecycleConflictError(
            "SOURCE_BATCH_RELEASE_EVIDENCE_INVALID",
            reason=_reason("RC-081"),
        )
    owner_keys = tuple(owner.run_id.value for owner in owner_runs)
    if owner_keys != tuple(sorted(owner_keys)) or len(owner_keys) != len(set(owner_keys)):
        raise LifecycleConflictError(
            "SOURCE_BATCH_RELEASE_OWNER_SET_INVALID",
            reason=_reason("RC-081"),
        )
    due: list[object] = []
    remaining: list[object] = []
    now_instant = (now.epoch_seconds, now.nanosecond)
    for owner in owner_runs:
        deadline = owner.purge_eligible_at
        if (
            owner.status is not RunStatus.IN_PROGRESS
            and type(deadline) is CanonicalTimestamp
            and (deadline.epoch_seconds, deadline.nanosecond) <= now_instant
        ):
            due.append(owner)
        else:
            remaining.append(owner)
    if not due:
        raise LifecycleConflictError(
            "SOURCE_BATCH_RELEASE_NOT_DUE",
            reason=_reason("RC-081"),
        )
    return _make_service_guard_proof(
        transition=transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        satisfied_at=now,
        evidence_kind=TransitionGuardEvidenceKind.SOURCE_BATCH_RELEASE,
        evidence={
            "batch": _hash_dict(source_batch.hash_binding()),
            "batch_identity": _hash_dict(source_batch.identity),
            "delete_batch": not remaining,
            "due_owner_runs": [_hash_dict(owner.hash_binding()) for owner in due],
            "remaining_owner_runs": [
                _hash_dict(owner.hash_binding()) for owner in remaining
            ],
        },
    )


def _fail_closed_owner_adapter(
    factory: Callable[..., TransitionGuardProof],
) -> Callable[..., TransitionGuardProof]:
    """Normalize malformed exact-type records at the public owner boundary."""

    @wraps(factory)
    def guarded(*args: object, **kwargs: object) -> TransitionGuardProof:
        try:
            return factory(*args, **kwargs)
        except LifecycleError:
            raise
        except (AttributeError, TypeError):
            raise LifecycleConflictError(
                "TRANSITION_OWNER_ADAPTER_INPUT_INVALID",
                reason=_reason("RC-081"),
            ) from None

    return guarded


_FAIL_CLOSED_OWNER_ADAPTER_NAMES = (
    "make_case_owner_transition_guard_proof",
    "make_attention_owner_transition_guard_proof",
    "make_run_control_transition_guard_proof",
    "make_extraction_transition_guard_proof",
    "make_source_import_start_guard_proof",
    "make_source_import_commit_guard_proof",
    "make_source_rejection_retention_guard_proof",
    "make_relationship_transition_guard_proof",
    "make_alternate_observation_transition_guard_proof",
    "make_action_context_transition_guard_proof",
    "make_contact_workflow_transition_guard_proof",
    "make_wwc_transition_guard_proof",
    "make_evaluation_transition_guard_proof",
    "make_out_of_scope_closure_guard_proof",
    "make_human_review_evaluation_guard_proof",
    "make_system_action_transition_guard_proof",
    "make_human_action_transition_guard_proof",
    "make_intervention_transition_guard_proof",
    "make_value_reduction_transition_guard_proof",
    "make_resulting_link_transition_guard_proof",
    "make_resulting_link_search_transition_guard_proof",
    "make_kpi_contribution_transition_guard_proof",
    "make_dedupe_reduction_transition_guard_proof",
    "make_human_fact_reduction_transition_guard_proof",
    "make_action_context_completion_guard_proof",
    "make_closure_transition_guard_proof",
    "make_case_recheck_transition_guard_proof",
    "make_case_purge_transition_guard_proof",
    "make_observation_graph_deletion_guard_proof",
    "make_identity_retention_purge_guard_proof",
    "make_source_batch_release_guard_proof",
)
for _owner_adapter_name in _FAIL_CLOSED_OWNER_ADAPTER_NAMES:
    globals()[_owner_adapter_name] = _fail_closed_owner_adapter(
        globals()[_owner_adapter_name]
    )
del _owner_adapter_name


def _validate_transition_guard_proof(
    proof: object,
    definition: TransitionDefinition,
) -> TransitionGuardProof:
    if type(proof) is not TransitionGuardProof or proof._issuer_token is not _GUARD_PROOF_TOKEN:
        raise LifecycleSchemaError(
            "TRANSITION_GUARD_PROOF_INVALID",
            reason=_reason("RC-113"),
        )
    if (
        proof.transition != definition.transition
        or proof.section != definition.section
        or proof.from_state != definition.from_state
        or proof.to_state != definition.to_state
        or proof.registered_guard != definition.guard
        or proof.required_effects != definition.required_effects
        or proof.fact_schema != transition_guard_fact_schema(definition.transition)
    ):
        raise LifecycleConflictError(
            "TRANSITION_GUARD_PROOF_BINDING_CONFLICT",
            reason=_reason("RC-081"),
        )
    if (
        type(proof.guard_facts) is not HashBinding
        or proof.guard_facts.domain != "doi-transition-guard-facts/v1"
        or type(proof.fact_schema) is not TransitionGuardFactSchema
        or type(proof.authority_evidence) is not TransitionGuardAuthorityEvidence
        or type(proof.verdict) is not TransitionGuardVerdict
    ):
        raise LifecycleSchemaError(
            "TRANSITION_GUARD_PROOF_INVALID",
            reason=_reason("RC-113"),
        )
    facts_value = parse_canonical_json_bytes(proof.guard_facts.canonical_bytes)
    facts_binding, checked_facts, expected_verdict = _closed_guard_facts(
        facts_value,
        proof.fact_schema,
    )
    if (
        facts_binding != proof.guard_facts
        or checked_facts != facts_value
        or proof.verdict is not expected_verdict
    ):
        raise LifecycleSchemaError(
            "TRANSITION_GUARD_PROOF_INVALID",
            reason=_reason("RC-113"),
        )
    checked_authority = _validate_transition_guard_authority(
        proof.authority_evidence,
        transition=definition.transition,
        guard_facts=proof.guard_facts,
    )
    expected = _guard_proof_value(
        definition=definition,
        fact_schema=proof.fact_schema,
        guard_facts=facts_value,
        guard_facts_binding=proof.guard_facts,
        authority_evidence=checked_authority,
        verdict=proof.verdict,
    )
    expected_bytes = canonical_json_bytes(expected, expected_members=set(expected))
    if proof.canonical_bytes() != expected_bytes:
        raise LifecycleSchemaError(
            "TRANSITION_GUARD_PROOF_INVALID",
            reason=_reason("RC-113"),
        )
    return proof


@dataclass(frozen=True, slots=True, init=False, repr=False)
class TransitionCommand:
    """A closed transition intent whose target is registry-derived.

    Construction is restricted to :func:`make_transition_command`, which validates the
    transition reference, reason ownership, sequence, and canonical guard evidence.
    """

    transition: TransitionRef
    stream_id: EvidenceId
    occurrence_id: EvidenceId
    current_state: str
    expected_sequence: int
    expected_predecessor_sha256: str | None
    guard_proof: TransitionGuardProof = field(repr=False)
    reasons: ReasonSet
    _canonical_bytes: bytes = field(repr=False, compare=False)
    _issuer_token: object = field(repr=False, compare=False)

    HASH_DOMAIN: ClassVar[str] = "doi-transition-command/v1"

    def __new__(cls) -> TransitionCommand:
        raise LifecycleSchemaError(
            "TRANSITION_COMMAND_CONSTRUCTION_INVALID",
            reason=_reason("RC-113"),
        )

    @classmethod
    def _create(
        cls,
        *,
        transition: TransitionRef,
        stream_id: EvidenceId,
        occurrence_id: EvidenceId,
        current_state: str,
        expected_sequence: int,
        expected_predecessor_sha256: str | None,
        guard_proof: TransitionGuardProof,
        reasons: ReasonSet,
        canonical_bytes: bytes,
        _token: object,
    ) -> TransitionCommand:
        if _token is not _COMMAND_TOKEN:
            raise LifecycleSchemaError(
                "TRANSITION_COMMAND_CONSTRUCTION_INVALID",
                reason=_reason("RC-113"),
            )
        instance = object.__new__(cls)
        for name, value in (
            ("transition", transition),
            ("stream_id", stream_id),
            ("occurrence_id", occurrence_id),
            ("current_state", current_state),
            ("expected_sequence", expected_sequence),
            ("expected_predecessor_sha256", expected_predecessor_sha256),
            ("guard_proof", guard_proof),
            ("reasons", reasons),
            ("_canonical_bytes", canonical_bytes),
            ("_issuer_token", _token),
        ):
            object.__setattr__(instance, name, value)
        return instance

    def canonical_bytes(self) -> bytes:
        return self._canonical_bytes

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self._canonical_bytes)

    def __repr__(self) -> str:
        return "TransitionCommand(<redacted>)"


def make_transition_command(
    *,
    transition: TransitionRef,
    stream_id: EvidenceId,
    occurrence_id: EvidenceId,
    current_state: str,
    expected_sequence: int,
    expected_predecessor_sha256: str | None,
    guard_proof: TransitionGuardProof,
    reasons: tuple[ReasonRef, ...] = (),
) -> TransitionCommand:
    """Validate and construct one typed transition command.

    The caller supplies a restricted registry-bound proof, never a Boolean assertion or an
    arbitrary facts map.  The full proof preimage is retained in the command so different
    guard material cannot replay merely because a digest comparison was incomplete.
    """

    definition = transition_definition(transition)
    if type(stream_id) is not EvidenceId or type(occurrence_id) is not EvidenceId:
        raise LifecycleSchemaError("TRANSITION_COMMAND_ID_INVALID", reason=_reason("RC-113"))
    state = _state(current_state, "TRANSITION_COMMAND_STATE_INVALID")
    if state != definition.from_state:
        raise LifecycleConflictError(
            "TRANSITION_FROM_STATE_CONFLICT",
            reason=_reason("RC-081"),
        )
    proof = _validate_transition_guard_proof(guard_proof, definition)
    if proof.from_state != state:
        raise LifecycleConflictError(
            "TRANSITION_GUARD_FROM_STATE_CONFLICT",
            reason=_reason("RC-081"),
        )
    if (
        proof.authority_evidence.stream_id != stream_id
        or proof.authority_evidence.occurrence_id != occurrence_id
    ):
        raise LifecycleConflictError(
            "TRANSITION_GUARD_AUTHORITY_SCOPE_CONFLICT",
            reason=_reason("RC-081"),
        )
    if type(expected_sequence) is not int or not 1 <= expected_sequence <= 1_000_000_000:
        raise LifecycleSchemaError("TRANSITION_COMMAND_SEQUENCE_INVALID", reason=_reason("RC-113"))
    predecessor = _sha256_or_none(
        expected_predecessor_sha256,
        "TRANSITION_COMMAND_PREDECESSOR_INVALID",
    )
    if (expected_sequence == 1) != (predecessor is None):
        raise LifecycleSchemaError(
            "TRANSITION_COMMAND_PREDECESSOR_INVALID",
            reason=_reason("RC-113"),
        )
    reason_set = ReasonSet(reasons)
    allowed = frozenset(legal_reason_refs(transition))
    if any(reason not in allowed for reason in reason_set.reasons):
        raise LifecycleConflictError(
            "REASON_TRANSITION_OWNERSHIP_INVALID",
            reason=_reason("RC-081"),
        )
    value = {
        "current_state": state,
        "expected_predecessor_sha256": predecessor,
        "expected_sequence": expected_sequence,
        "guard_proof": parse_canonical_json_bytes(proof.canonical_bytes()),
        "guard_proof_binding": _hash_dict(proof.hash_binding()),
        "occurrence_id": occurrence_id.value,
        "reasons": reason_set.to_json_value(),
        "schema_version": LIFECYCLE_SCHEMA_VERSION,
        "stream_id": stream_id.value,
        "transition_id": definition.transition.transition_id,
        "transition_registry_version": definition.transition.registry_version,
    }
    command_bytes = canonical_json_bytes(value, expected_members=set(value))
    return TransitionCommand._create(
        transition=definition.transition,
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        current_state=state,
        expected_sequence=expected_sequence,
        expected_predecessor_sha256=predecessor,
        guard_proof=proof,
        reasons=reason_set,
        canonical_bytes=command_bytes,
        _token=_COMMAND_TOKEN,
    )


@dataclass(frozen=True, slots=True, repr=False)
class TransitionEvent:
    event_id: EvidenceId
    stream_id: EvidenceId
    sequence: int
    transition: TransitionRef
    from_state: str
    to_state: str
    occurred_at: CanonicalTimestamp
    predecessor_sha256: str | None
    command: HashBinding = field(repr=False)
    command_bytes: bytes = field(repr=False)
    reasons: ReasonSet
    schema_version: str = LIFECYCLE_SCHEMA_VERSION

    HASH_DOMAIN: ClassVar[str] = "doi-lifecycle-event/v1"

    def __post_init__(self) -> None:
        if type(self.event_id) is not EvidenceId or type(self.stream_id) is not EvidenceId:
            raise LifecycleSchemaError("LIFECYCLE_EVENT_ID_INVALID", reason=_reason("RC-113"))
        if (
            type(self.transition) is not TransitionRef
            or type(self.occurred_at) is not CanonicalTimestamp
        ):
            raise LifecycleSchemaError("LIFECYCLE_EVENT_BINDING_INVALID", reason=_reason("RC-113"))
        _state(self.from_state, "LIFECYCLE_EVENT_STATE_INVALID")
        _state(self.to_state, "LIFECYCLE_EVENT_STATE_INVALID")
        if type(self.sequence) is not int or self.sequence <= 0:
            raise LifecycleSchemaError("LIFECYCLE_EVENT_SEQUENCE_INVALID", reason=_reason("RC-113"))
        _sha256_or_none(self.predecessor_sha256, "LIFECYCLE_EVENT_PREDECESSOR_INVALID")
        if (
            type(self.command) is not HashBinding
            or self.command.domain != TransitionCommand.HASH_DOMAIN
        ):
            raise LifecycleSchemaError("LIFECYCLE_EVENT_COMMAND_INVALID", reason=_reason("RC-113"))
        if (
            type(self.command_bytes) is not bytes
            or self.command.canonical_bytes != self.command_bytes
        ):
            raise LifecycleSchemaError("LIFECYCLE_EVENT_COMMAND_INVALID", reason=_reason("RC-113"))
        if type(self.reasons) is not ReasonSet or self.schema_version != LIFECYCLE_SCHEMA_VERSION:
            raise LifecycleSchemaError("LIFECYCLE_EVENT_SCHEMA_INVALID", reason=_reason("RC-113"))

    def to_dict(self) -> dict[str, object]:
        return {
            "command": _hash_dict(self.command),
            "event_id": self.event_id.value,
            "from_state": self.from_state,
            "occurred_at": self.occurred_at.value,
            "predecessor_sha256": self.predecessor_sha256,
            "reasons": self.reasons.to_json_value(),
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "stream_id": self.stream_id.value,
            "to_state": self.to_state,
            "transition_id": self.transition.transition_id,
            "transition_registry_version": self.transition.registry_version,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "TransitionEvent(<redacted>)"


@dataclass(frozen=True, slots=True)
class TransitionEffect:
    kind: TransitionEffectKind
    transition: TransitionRef
    ordinal: int
    required_effects: str

    def __post_init__(self) -> None:
        if (
            type(self.kind) is not TransitionEffectKind
            or type(self.transition) is not TransitionRef
            or self.kind is not TransitionEffectKind.REGISTERED_EFFECTS
        ):
            raise LifecycleSchemaError("TRANSITION_EFFECT_INVALID", reason=_reason("RC-113"))
        if type(self.ordinal) is not int or self.ordinal != 1:
            raise LifecycleSchemaError("TRANSITION_EFFECT_INVALID", reason=_reason("RC-113"))
        definition = transition_definition(self.transition)
        if (
            type(self.required_effects) is not str
            or self.required_effects != definition.required_effects
        ):
            raise LifecycleSchemaError(
                "TRANSITION_REGISTERED_EFFECTS_INVALID",
                reason=_reason("RC-113"),
            )


@dataclass(frozen=True, slots=True)
class TransitionProjection:
    stream_id: EvidenceId
    state: str
    sequence: int = 0
    head_sha256: str | None = None

    def __post_init__(self) -> None:
        if type(self.stream_id) is not EvidenceId:
            raise LifecycleSchemaError("TRANSITION_PROJECTION_ID_INVALID", reason=_reason("RC-113"))
        _state(self.state, "TRANSITION_PROJECTION_STATE_INVALID")
        if type(self.sequence) is not int or self.sequence < 0:
            raise LifecycleSchemaError(
                "TRANSITION_PROJECTION_SEQUENCE_INVALID",
                reason=_reason("RC-113"),
            )
        _sha256_or_none(self.head_sha256, "TRANSITION_PROJECTION_HEAD_INVALID")
        if (self.sequence == 0) != (self.head_sha256 is None):
            raise LifecycleSchemaError(
                "TRANSITION_PROJECTION_HEAD_INVALID",
                reason=_reason("RC-113"),
            )


@dataclass(frozen=True, slots=True)
class TransitionStream:
    projection: TransitionProjection
    events: tuple[TransitionEvent, ...] = ()

    def __post_init__(self) -> None:
        if type(self.projection) is not TransitionProjection:
            raise LifecycleSchemaError(
                "TRANSITION_STREAM_PROJECTION_INVALID",
                reason=_reason("RC-113"),
            )
        if type(self.events) is not tuple or any(
            type(event) is not TransitionEvent for event in self.events
        ):
            raise LifecycleSchemaError("TRANSITION_STREAM_EVENTS_INVALID", reason=_reason("RC-113"))
        if len(self.events) != self.projection.sequence:
            raise LifecycleSchemaError(
                "TRANSITION_STREAM_SEQUENCE_INVALID",
                reason=_reason("RC-113"),
            )
        predecessor: str | None = None
        for sequence, event in enumerate(self.events, start=1):
            if (
                event.stream_id != self.projection.stream_id
                or event.sequence != sequence
                or event.predecessor_sha256 != predecessor
            ):
                raise LifecycleSchemaError(
                    "TRANSITION_STREAM_SEQUENCE_INVALID",
                    reason=_reason("RC-113"),
                )
            predecessor = event.hash_binding().sha256
        if predecessor != self.projection.head_sha256:
            raise LifecycleSchemaError("TRANSITION_STREAM_HEAD_INVALID", reason=_reason("RC-113"))

    @classmethod
    def initial(cls, *, stream_id: EvidenceId, state: str) -> TransitionStream:
        return cls(TransitionProjection(stream_id=stream_id, state=state))


@dataclass(frozen=True, slots=True)
class TransitionResult:
    stream: TransitionStream
    event: TransitionEvent
    effects: tuple[TransitionEffect, ...]
    replayed: bool

    def __post_init__(self) -> None:
        if (
            type(self.stream) is not TransitionStream
            or type(self.event) is not TransitionEvent
            or type(self.effects) is not tuple
            or any(type(effect) is not TransitionEffect for effect in self.effects)
            or type(self.replayed) is not bool
        ):
            raise LifecycleSchemaError("TRANSITION_RESULT_INVALID", reason=_reason("RC-113"))
        if self.effects != registered_transition_effects(self.event.transition):
            raise LifecycleSchemaError(
                "TRANSITION_RESULT_EFFECTS_INVALID",
                reason=_reason("RC-113"),
            )


def registered_transition_effects(
    transition: TransitionRef,
) -> tuple[TransitionEffect, ...]:
    """Return the exact immutable registry instruction for one transition row."""

    definition = transition_definition(transition)
    return (
        TransitionEffect(
            kind=TransitionEffectKind.REGISTERED_EFFECTS,
            transition=definition.transition,
            ordinal=1,
            required_effects=definition.required_effects,
        ),
    )


def _replay_event(stream: TransitionStream, command: TransitionCommand) -> TransitionEvent | None:
    retained = next(
        (event for event in stream.events if event.event_id == command.occurrence_id),
        None,
    )
    if retained is None:
        return None
    candidate = command.hash_binding()
    try:
        replay = compare_retained_canonical_bytes(
            retained.command.sha256,
            retained.command_bytes,
            candidate.sha256,
            command.canonical_bytes(),
        )
    except CanonicalHashCollision:
        raise LifecycleCollisionError(
            "TRANSITION_COMMAND_DIGEST_COLLISION",
            reason=_reason("RC-103"),
        ) from None
    if not replay:
        raise LifecycleConflictError(
            "TRANSITION_OCCURRENCE_MATERIAL_CONFLICT",
            reason=_reason("RC-111"),
        )
    return retained


def _reduce_transition(
    stream: TransitionStream,
    command: TransitionCommand,
    *,
    occurred_at: CanonicalTimestamp,
    allow_synthetic_fixture: bool,
) -> TransitionResult:
    """Shared reducer with one explicit structural-fixture test boundary."""

    if (
        type(stream) is not TransitionStream
        or type(command) is not TransitionCommand
        or command._issuer_token is not _COMMAND_TOKEN
    ):
        raise LifecycleSchemaError("TRANSITION_REDUCER_INPUT_INVALID", reason=_reason("RC-113"))
    if type(occurred_at) is not CanonicalTimestamp:
        raise LifecycleSchemaError("TRANSITION_EVENT_TIMESTAMP_INVALID", reason=_reason("RC-113"))
    if stream.projection.stream_id != command.stream_id:
        raise LifecycleConflictError("TRANSITION_STREAM_ID_CONFLICT", reason=_reason("RC-111"))
    replay = _replay_event(stream, command)
    definition = transition_definition(command.transition)
    proof = _validate_transition_guard_proof(command.guard_proof, definition)
    if (
        proof.authority_evidence.stream_id != command.stream_id
        or proof.authority_evidence.occurrence_id != command.occurrence_id
    ):
        raise LifecycleConflictError(
            "TRANSITION_GUARD_AUTHORITY_SCOPE_CONFLICT",
            reason=_reason("RC-081"),
        )
    if (
        proof.authority_evidence.issuer
        is TransitionGuardAuthorityIssuer.SYNTHETIC_FIXTURE
        and not allow_synthetic_fixture
    ):
        raise LifecycleSchemaError(
            "TRANSITION_SYNTHETIC_FIXTURE_AUTHORITY_FORBIDDEN",
            reason=_reason("RC-113"),
        )
    effects = registered_transition_effects(definition.transition)
    if replay is not None:
        return TransitionResult(stream=stream, event=replay, effects=effects, replayed=True)
    if proof.authority_evidence.issuer is TransitionGuardAuthorityIssuer.OWNING_SERVICE:
        satisfied_at = proof.authority_evidence.satisfied_at
        if definition.transition.transition_id == "TR-013":
            evidence_instant = (satisfied_at.epoch_seconds, satisfied_at.nanosecond)
            event_instant = (occurred_at.epoch_seconds, occurred_at.nanosecond)
            time_valid = event_instant >= evidence_instant
        else:
            time_valid = occurred_at == satisfied_at
        if not time_valid:
            raise LifecycleConflictError(
                "TRANSITION_GUARD_EVIDENCE_TIME_CONFLICT",
                reason=_reason("RC-081"),
            )
    if command.current_state != definition.from_state:
        raise LifecycleConflictError("TRANSITION_FROM_STATE_CONFLICT", reason=_reason("RC-081"))
    if not proof.satisfied:
        raise LifecycleConflictError("TRANSITION_GUARD_FALSE", reason=_reason("RC-081"))
    if command.expected_sequence != stream.projection.sequence + 1:
        raise LifecycleConflictError("TRANSITION_SEQUENCE_CONFLICT", reason=_reason("RC-111"))
    if command.expected_predecessor_sha256 != stream.projection.head_sha256:
        raise LifecycleConflictError("TRANSITION_PREDECESSOR_CONFLICT", reason=_reason("RC-111"))
    if command.current_state != stream.projection.state:
        raise LifecycleConflictError("TRANSITION_FROM_STATE_CONFLICT", reason=_reason("RC-081"))
    command_binding = command.hash_binding()
    event = TransitionEvent(
        event_id=command.occurrence_id,
        stream_id=command.stream_id,
        sequence=command.expected_sequence,
        transition=definition.transition,
        from_state=command.current_state,
        to_state=definition.to_state,
        occurred_at=occurred_at,
        predecessor_sha256=command.expected_predecessor_sha256,
        command=command_binding,
        command_bytes=command.canonical_bytes(),
        reasons=command.reasons,
    )
    head = event.hash_binding().sha256
    projection = TransitionProjection(
        stream_id=command.stream_id,
        state=definition.to_state,
        sequence=event.sequence,
        head_sha256=head,
    )
    updated = TransitionStream(projection=projection, events=(*stream.events, event))
    return TransitionResult(stream=updated, event=event, effects=effects, replayed=False)


def reduce_transition(
    stream: TransitionStream,
    command: TransitionCommand,
    *,
    occurred_at: CanonicalTimestamp,
) -> TransitionResult:
    """Append only a production-authorized transition guard proof."""

    return _reduce_transition(
        stream,
        command,
        occurred_at=occurred_at,
        allow_synthetic_fixture=False,
    )


def reduce_fixture_transition(
    stream: TransitionStream,
    command: TransitionCommand,
    *,
    occurred_at: CanonicalTimestamp,
) -> TransitionResult:
    """Exercise registry structure with synthetic facts; never a business-proof oracle."""

    return _reduce_transition(
        stream,
        command,
        occurred_at=occurred_at,
        allow_synthetic_fixture=True,
    )


_ATTENTION_SET_TRANSITIONS = {
    AttentionCondition.RECHECK_REQUIRED: "TR-020",
    AttentionCondition.SOURCE_ABSENCE_RECHECK_REQUIRED: "TR-021",
    AttentionCondition.INTERVENTION_VERIFICATION_REQUIRED: "TR-025",
    AttentionCondition.RESULTING_ORDER_LINK_REVIEW: "TR-092",
    AttentionCondition.HUMAN_COORDINATION_REVIEW_REQUIRED: "TR-094",
}
_ATTENTION_CLEAR_TRANSITIONS = {
    AttentionCondition.RECHECK_REQUIRED: "TR-024",
    AttentionCondition.SOURCE_ABSENCE_RECHECK_REQUIRED: "TR-023",
    AttentionCondition.INTERVENTION_VERIFICATION_REQUIRED: "TR-026",
    AttentionCondition.RESULTING_ORDER_LINK_REVIEW: "TR-093",
    AttentionCondition.HUMAN_COORDINATION_REVIEW_REQUIRED: "TR-095",
}


@dataclass(frozen=True, slots=True, repr=False)
class AttentionEvent:
    event_id: EvidenceId
    case_id: EvidenceId
    action: AttentionAction
    condition: AttentionCondition
    cause_key: EvidenceId
    active_set_event_id: EvidenceId | None
    resolver_id: EvidenceId | None
    occurred_at: CanonicalTimestamp
    transition: TransitionRef
    schema_version: str = "doi-attention-event/v1"

    HASH_DOMAIN: ClassVar[str] = "doi-attention-event/v1"

    def __post_init__(self) -> None:
        if (
            type(self.event_id) is not EvidenceId
            or type(self.case_id) is not EvidenceId
            or type(self.action) is not AttentionAction
            or type(self.condition) is not AttentionCondition
            or type(self.cause_key) is not EvidenceId
            or type(self.occurred_at) is not CanonicalTimestamp
            or type(self.transition) is not TransitionRef
            or self.schema_version != "doi-attention-event/v1"
        ):
            raise LifecycleSchemaError("ATTENTION_EVENT_INVALID", reason=_reason("RC-113"))
        expected_transition = (
            _ATTENTION_SET_TRANSITIONS[self.condition]
            if self.action is AttentionAction.SET
            else _ATTENTION_CLEAR_TRANSITIONS[self.condition]
        )
        if self.transition.transition_id != expected_transition:
            raise LifecycleSchemaError("ATTENTION_TRANSITION_INVALID", reason=_reason("RC-113"))
        if self.action is AttentionAction.SET:
            if self.active_set_event_id is not None or self.resolver_id is not None:
                raise LifecycleSchemaError(
                    "ATTENTION_SET_PARTITION_INVALID",
                    reason=_reason("RC-113"),
                )
        elif (
            type(self.active_set_event_id) is not EvidenceId
            or type(self.resolver_id) is not EvidenceId
        ):
            raise LifecycleSchemaError(
                "ATTENTION_CLEAR_PARTITION_INVALID",
                reason=_reason("RC-113"),
            )

    @classmethod
    def set(
        cls,
        *,
        event_id: EvidenceId,
        case_id: EvidenceId,
        condition: AttentionCondition,
        cause_key: EvidenceId,
        occurred_at: CanonicalTimestamp,
    ) -> AttentionEvent:
        transition = load_doi_registries().transition_ref(
            _ATTENTION_SET_TRANSITIONS[condition]
        )
        return cls(
            event_id=event_id,
            case_id=case_id,
            action=AttentionAction.SET,
            condition=condition,
            cause_key=cause_key,
            active_set_event_id=None,
            resolver_id=None,
            occurred_at=occurred_at,
            transition=transition,
        )

    @classmethod
    def clear(
        cls,
        *,
        event_id: EvidenceId,
        active_set: AttentionEvent,
        resolver_id: EvidenceId,
        occurred_at: CanonicalTimestamp,
    ) -> AttentionEvent:
        if type(active_set) is not AttentionEvent or active_set.action is not AttentionAction.SET:
            raise LifecycleSchemaError("ATTENTION_CLEAR_SET_INVALID", reason=_reason("RC-113"))
        transition = load_doi_registries().transition_ref(
            _ATTENTION_CLEAR_TRANSITIONS[active_set.condition]
        )
        return cls(
            event_id=event_id,
            case_id=active_set.case_id,
            action=AttentionAction.CLEAR,
            condition=active_set.condition,
            cause_key=active_set.cause_key,
            active_set_event_id=active_set.event_id,
            resolver_id=resolver_id,
            occurred_at=occurred_at,
            transition=transition,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action.value,
            "active_set_event_id": (
                None if self.active_set_event_id is None else self.active_set_event_id.value
            ),
            "case_id": self.case_id.value,
            "cause_key": self.cause_key.value,
            "condition": self.condition.value,
            "event_id": self.event_id.value,
            "occurred_at": self.occurred_at.value,
            "resolver_id": None if self.resolver_id is None else self.resolver_id.value,
            "schema_version": self.schema_version,
            "transition_id": self.transition.transition_id,
        }

    def canonical_bytes(self) -> bytes:
        value = self.to_dict()
        return canonical_json_bytes(value, expected_members=set(value))

    def hash_binding(self) -> HashBinding:
        return domain_hash(self.HASH_DOMAIN, self.canonical_bytes())

    def __repr__(self) -> str:
        return "AttentionEvent(<redacted>)"


@dataclass(frozen=True, slots=True)
class ActiveAttention:
    condition: AttentionCondition
    cause_key: EvidenceId
    set_event_id: EvidenceId

    def __post_init__(self) -> None:
        if (
            type(self.condition) is not AttentionCondition
            or type(self.cause_key) is not EvidenceId
            or type(self.set_event_id) is not EvidenceId
        ):
            raise LifecycleSchemaError("ACTIVE_ATTENTION_INVALID", reason=_reason("RC-113"))


@dataclass(frozen=True, slots=True)
class AttentionStream:
    case_id: EvidenceId
    active: tuple[ActiveAttention, ...] = ()
    events: tuple[AttentionEvent, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.case_id) is not EvidenceId
            or type(self.active) is not tuple
            or any(type(item) is not ActiveAttention for item in self.active)
            or type(self.events) is not tuple
            or any(type(item) is not AttentionEvent for item in self.events)
            or any(item.case_id != self.case_id for item in self.events)
        ):
            raise LifecycleSchemaError("ATTENTION_STREAM_INVALID", reason=_reason("RC-113"))
        keys = tuple((item.condition.value, item.cause_key.value) for item in self.active)
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise LifecycleSchemaError("ATTENTION_STREAM_ACTIVE_INVALID", reason=_reason("RC-113"))


@dataclass(frozen=True, slots=True)
class AttentionResult:
    stream: AttentionStream
    event: AttentionEvent
    replayed: bool


def reduce_attention(stream: AttentionStream, event: AttentionEvent) -> AttentionResult:
    """Apply one exact cause-keyed SET/CLEAR without affecting unrelated causes."""

    if type(stream) is not AttentionStream or type(event) is not AttentionEvent:
        raise LifecycleSchemaError("ATTENTION_REDUCER_INPUT_INVALID", reason=_reason("RC-113"))
    if stream.case_id != event.case_id:
        raise LifecycleConflictError("ATTENTION_CASE_CONFLICT", reason=_reason("RC-081"))
    prior = next((item for item in stream.events if item.event_id == event.event_id), None)
    if prior is not None:
        if prior.canonical_bytes() != event.canonical_bytes():
            raise LifecycleConflictError("ATTENTION_EVENT_CONFLICT", reason=_reason("RC-111"))
        return AttentionResult(stream=stream, event=prior, replayed=True)
    key = (event.condition, event.cause_key)
    active_by_key = {(item.condition, item.cause_key): item for item in stream.active}
    if event.action is AttentionAction.SET:
        if key in active_by_key:
            raise LifecycleConflictError("ATTENTION_CAUSE_ALREADY_ACTIVE", reason=_reason("RC-081"))
        active_by_key[key] = ActiveAttention(
            condition=event.condition,
            cause_key=event.cause_key,
            set_event_id=event.event_id,
        )
    else:
        active = active_by_key.get(key)
        if active is None or active.set_event_id != event.active_set_event_id:
            raise LifecycleConflictError("ATTENTION_CLEAR_SET_CONFLICT", reason=_reason("RC-081"))
        del active_by_key[key]
    active_values = tuple(
        sorted(
            active_by_key.values(),
            key=lambda item: (item.condition.value, item.cause_key.value),
        )
    )
    updated = AttentionStream(
        case_id=stream.case_id,
        active=active_values,
        events=(*stream.events, event),
    )
    return AttentionResult(stream=updated, event=event, replayed=False)


def _fixture_guard_scope(
    transition: TransitionRef,
) -> tuple[EvidenceId, EvidenceId]:
    suffix = transition.transition_id
    return (
        EvidenceId(f"SYN-EVIDENCE-STREAM-{suffix}"),
        EvidenceId(f"SYN-EVIDENCE-EVENT-{suffix}"),
    )


def _make_fixture_transition_guard_proof(
    transition: TransitionRef,
    guard_facts: Mapping[str, object],
) -> TransitionGuardProof:
    """Issue a test-only proof fixed to the closed synthetic registry fixture scope."""

    definition = transition_definition(transition)
    fact_schema = transition_guard_fact_schema(transition)
    facts_binding, _, _ = _closed_guard_facts(guard_facts, fact_schema)
    stream_id, occurrence_id = _fixture_guard_scope(transition)
    authority = _issue_transition_guard_authority(
        transition=transition,
        issuer=TransitionGuardAuthorityIssuer.SYNTHETIC_FIXTURE,
        evidence_kind=TransitionGuardEvidenceKind.SYNTHETIC_REGISTRY_FIXTURE,
        evidence={
            "fixture": "CLOSED_REGISTRY_STRUCTURAL_COVERAGE",
            "transition_id": definition.transition.transition_id,
        },
        satisfied_at=CanonicalTimestamp("2026-08-20T12:00:00Z"),
        stream_id=stream_id,
        occurrence_id=occurrence_id,
        guard_facts=facts_binding,
        _issuer_token=_FIXTURE_AUTHORITY_ISSUER_TOKEN,
    )
    return make_transition_guard_proof(
        transition=transition,
        from_state=definition.from_state,
        expected_to_state=definition.to_state,
        registered_guard=definition.guard,
        required_effects=definition.required_effects,
        guard_facts=guard_facts,
        authority_evidence=authority,
    )


@dataclass(frozen=True, slots=True)
class TransitionFixture:
    """Deterministic registry coverage input used by real collected tests."""

    definition: TransitionDefinition
    stream: TransitionStream
    command: TransitionCommand
    occurred_at: CanonicalTimestamp

    @classmethod
    def legal(cls, transition: TransitionRef) -> TransitionFixture:
        definition = transition_definition(transition)
        stream_id, event_id = _fixture_guard_scope(transition)
        stream = TransitionStream.initial(stream_id=stream_id, state=definition.from_state)
        proof = _make_fixture_transition_guard_proof(
            transition,
            satisfying_transition_guard_facts(transition),
        )
        command = make_transition_command(
            transition=transition,
            stream_id=stream_id,
            occurrence_id=event_id,
            current_state=definition.from_state,
            expected_sequence=1,
            expected_predecessor_sha256=None,
            guard_proof=proof,
        )
        return cls(
            definition=definition,
            stream=stream,
            command=command,
            occurred_at=CanonicalTimestamp("2026-08-20T12:00:00Z"),
        )

    @classmethod
    def invalid(cls, transition: TransitionRef) -> TransitionFixture:
        fixture = cls.legal(transition)
        proof = _make_fixture_transition_guard_proof(
            transition,
            failing_transition_guard_facts(transition),
        )
        command = make_transition_command(
            transition=transition,
            stream_id=fixture.command.stream_id,
            occurrence_id=fixture.command.occurrence_id,
            current_state=fixture.command.current_state,
            expected_sequence=1,
            expected_predecessor_sha256=None,
            guard_proof=proof,
        )
        return cls(
            definition=fixture.definition,
            stream=fixture.stream,
            command=command,
            occurred_at=fixture.occurred_at,
        )


def transition_matrix() -> Mapping[str, TransitionDefinition]:
    """Expose an immutable 115-row normalized matrix for trace generation."""

    registries = load_doi_registries()
    return MappingProxyType(
        {
            ref.transition_id: transition_definition(ref, registries=registries)
            for ref in registries.transition_refs
        }
    )


def lifecycle_hash_fixtures() -> tuple[tuple[str, str, bytes, str], ...]:
    """Return deterministic representative command/event bindings for central KATs."""

    fixture = TransitionFixture.legal(load_doi_registries().transition_ref("TR-044"))
    result = reduce_fixture_transition(
        fixture.stream,
        fixture.command,
        occurred_at=fixture.occurred_at,
    )
    attention = AttentionEvent.set(
        event_id=EvidenceId("SYN-EVIDENCE-KAT-ATTENTION-EVENT"),
        case_id=EvidenceId("SYN-EVIDENCE-KAT-ATTENTION-CASE"),
        condition=AttentionCondition.RECHECK_REQUIRED,
        cause_key=EvidenceId("SYN-EVIDENCE-KAT-ATTENTION-CAUSE"),
        occurred_at=fixture.occurred_at,
    )
    values = (
        (
            "TransitionGuardAuthorityEvidence",
            fixture.command.guard_proof.authority_evidence.hash_binding(),
        ),
        ("TransitionGuardFacts", fixture.command.guard_proof.guard_facts),
        ("TransitionGuardProof", fixture.command.guard_proof.hash_binding()),
        ("TransitionCommand", fixture.command.hash_binding()),
        ("TransitionEvent", result.event.hash_binding()),
        ("AttentionEvent", attention.hash_binding()),
    )
    return tuple(
        (name, binding.domain, binding.canonical_bytes, binding.sha256)
        for name, binding in values
    )


__all__ = [
    "ActiveAttention",
    "action_context_event_occurrence_id",
    "alternate_observation_occurrence_id",
    "AttentionAction",
    "AttentionEvent",
    "AttentionResult",
    "AttentionStream",
    "case_purge_occurrence_id",
    "contact_workflow_event_occurrence_id",
    "GUARD_AUTHORITY_SCHEMA_VERSION",
    "GUARD_FACT_SCHEMA_VERSION",
    "LIFECYCLE_SCHEMA_VERSION",
    "LifecycleCollisionError",
    "LifecycleConflictError",
    "LifecycleError",
    "LifecycleSchemaError",
    "TransitionCommand",
    "TransitionDefinition",
    "TransitionEffect",
    "TransitionEffectKind",
    "TransitionEvent",
    "TransitionGuardAuthorityEvidence",
    "TransitionGuardAuthorityIssuer",
    "TransitionGuardEvidenceKind",
    "TransitionGuardFactSchema",
    "TransitionGuardProof",
    "TransitionGuardVerdict",
    "TransitionProjection",
    "TransitionResult",
    "TransitionStream",
    "legal_reason_refs",
    "lifecycle_hash_fixtures",
    "evaluation_transition_occurrence_id",
    "evaluation_transition_stream_id",
    "extraction_transition_occurrence_id",
    "extraction_transition_stream_id",
    "identity_retention_occurrence_id",
    "identity_retention_stream_id",
    "make_transition_command",
    "make_action_context_transition_guard_proof",
    "make_action_context_completion_guard_proof",
    "make_alternate_observation_transition_guard_proof",
    "make_attention_owner_transition_guard_proof",
    "make_case_purge_transition_guard_proof",
    "make_case_owner_transition_guard_proof",
    "make_closure_transition_guard_proof",
    "make_contact_workflow_transition_guard_proof",
    "make_dedupe_reduction_transition_guard_proof",
    "make_evaluation_transition_guard_proof",
    "make_extraction_transition_guard_proof",
    "make_human_action_transition_guard_proof",
    "make_human_fact_reduction_transition_guard_proof",
    "make_identity_retention_purge_guard_proof",
    "make_intervention_transition_guard_proof",
    "make_kpi_contribution_transition_guard_proof",
    "make_observation_graph_deletion_guard_proof",
    "make_out_of_scope_closure_guard_proof",
    "make_run_control_transition_guard_proof",
    "make_relationship_transition_guard_proof",
    "make_resulting_link_search_transition_guard_proof",
    "make_resulting_link_transition_guard_proof",
    "make_source_batch_release_guard_proof",
    "make_source_import_commit_guard_proof",
    "make_source_import_start_guard_proof",
    "make_source_rejection_retention_guard_proof",
    "make_system_action_transition_guard_proof",
    "make_transition_guard_proof",
    "make_wwc_transition_guard_proof",
    "observation_deletion_occurrence_id",
    "production_owner_adapter_transition_ids",
    "protected_transition_ids",
    "missing_production_owner_adapter_transition_ids",
    "recognized_transition_ids",
    "registered_transition_effects",
    "run_transition_occurrence_id",
    "run_transition_stream_id",
    "reduce_attention",
    "reduce_fixture_transition",
    "reduce_transition",
    "failing_transition_guard_facts",
    "satisfying_transition_guard_facts",
    "source_batch_release_occurrence_id",
    "source_import_event_occurrence_id",
    "source_import_transition_stream_id",
    "source_rejection_retention_occurrence_id",
    "transition_definition",
    "transition_guard_fact_schema",
    "transition_matrix",
    "wwc_event_occurrence_id",
]
