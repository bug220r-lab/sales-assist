"""Executable DOI reason and transition ownership for Milestone 3.

The supplied registries remain immutable.  This module derives the effective ownership view
after applying the approved opportunity-preservation decision and binds every reason and every
registered transition to a stable, real ``unittest`` selector.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType

from synthetic_sales_assist.doi.evaluator import (
    assert_reason_route_legal,
    effective_reason_routes,
)
from synthetic_sales_assist.domain.registries import (
    DoiRegistries,
    ReasonRef,
    TransitionRef,
    load_doi_registries,
)


DOI_TRACEABILITY_VERSION = "synthetic-doi-traceability/v1"
_SELECTOR = re.compile(
    r"^tests\.test_doi_[a-z0-9_]+\.[A-Za-z][A-Za-z0-9_]+\.test_[a-z0-9_]+$",
    re.ASCII,
)


class DOITraceabilityError(ValueError):
    """Reject an incomplete or non-executable traceability row."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ReasonOracleRow:
    """One closed reason row and its effective transition/test ownership."""

    reason: ReasonRef
    effective_transitions: tuple[TransitionRef, ...]
    rule_or_boundary_only: bool
    ownership_mode: str
    actual_test_selector: str
    decision_overlay_applied: bool
    version: str = DOI_TRACEABILITY_VERSION

    def __post_init__(self) -> None:
        if type(self.reason) is not ReasonRef:
            raise DOITraceabilityError("REASON_ORACLE_REASON_INVALID")
        if type(self.effective_transitions) is not tuple or any(
            type(item) is not TransitionRef for item in self.effective_transitions
        ):
            raise DOITraceabilityError("REASON_ORACLE_TRANSITIONS_INVALID")
        transition_ids = tuple(item.transition_id for item in self.effective_transitions)
        if transition_ids != tuple(sorted(set(transition_ids))):
            raise DOITraceabilityError("REASON_ORACLE_TRANSITIONS_INVALID")
        if type(self.rule_or_boundary_only) is not bool or (
            self.rule_or_boundary_only == bool(self.effective_transitions)
        ):
            raise DOITraceabilityError("REASON_ORACLE_ROUTE_PARTITION_INVALID")
        if self.ownership_mode not in {
            "ASSERTED_ONLY_UNREACHABLE",
            "EMITTED_AND_ASSERTED",
        }:
            raise DOITraceabilityError("REASON_ORACLE_MODE_INVALID")
        _require_selector(self.actual_test_selector)
        if type(self.decision_overlay_applied) is not bool:
            raise DOITraceabilityError("REASON_ORACLE_OVERLAY_INVALID")
        if self.version != DOI_TRACEABILITY_VERSION:
            raise DOITraceabilityError("REASON_ORACLE_VERSION_INVALID")


@dataclass(frozen=True, slots=True)
class TransitionCoverageRow:
    """One registered transition and its collected legal/invalid test pair."""

    transition: TransitionRef
    legal_test_selector: str
    invalid_test_selector: str
    version: str = DOI_TRACEABILITY_VERSION

    def __post_init__(self) -> None:
        if type(self.transition) is not TransitionRef:
            raise DOITraceabilityError("TRANSITION_COVERAGE_TRANSITION_INVALID")
        _require_selector(self.legal_test_selector)
        _require_selector(self.invalid_test_selector)
        if self.legal_test_selector == self.invalid_test_selector:
            raise DOITraceabilityError("TRANSITION_COVERAGE_SELECTORS_INVALID")
        if self.version != DOI_TRACEABILITY_VERSION:
            raise DOITraceabilityError("TRANSITION_COVERAGE_VERSION_INVALID")


def _require_selector(selector: object) -> None:
    if type(selector) is not str or _SELECTOR.fullmatch(selector) is None:
        raise DOITraceabilityError("TEST_SELECTOR_INVALID")


def _actual_reason_owner_selectors() -> MappingProxyType[str, str]:
    """Build the closed map to independent owning rule/service behavior tests.

    Repeated selectors are intentional: one actual behavior test may assert several reasons.
    These selectors never point at the generated lifecycle route-acceptance inventory.
    """

    selectors: dict[str, str] = {}

    def bind(codes: tuple[str, ...], selector: str) -> None:
        _require_selector(selector)
        for code in codes:
            if code in selectors:
                raise DOITraceabilityError("REASON_OWNER_SELECTOR_DUPLICATE")
            selectors[code] = selector

    bind(
        ("RC-001",),
        "tests.test_doi_source.DOIRunControlTests."
        "test_tab_confirmation_is_preallocation_gate_and_start_replays",
    )
    bind(
        ("RC-002", "RC-003", "RC-007"),
        "tests.test_doi_source.DOISourceClassificationTests."
        "test_locked_schema_invalid_order_is_attempt_failure_and_rc003_is_unreachable",
    )
    bind(
        ("RC-004", "RC-005", "RC-006", "RC-008"),
        "tests.test_doi_source.DOISourceClassificationTests."
        "test_duplicates_merge_conflicts_reject_and_row_count_equation_is_exact",
    )
    bind(
        ("RC-009", "RC-089", "RC-090"),
        "tests.test_doi_source.DOISourceClassificationTests."
        "test_source_change_revision_partition_and_inaccessible_reads_fail_closed",
    )
    bind(
        ("RC-010",),
        "tests.test_doi_evaluator.DOIEvaluatorBranchTests."
        "test_source_absence_forces_recheck_monitor_and_suppresses_stale_closure",
    )
    bind(
        ("RC-011",),
        "tests.test_doi_extraction.DOIExtractionTests."
        "test_identity_missing_or_mismatch_is_rc011",
    )
    bind(
        ("RC-012",),
        "tests.test_doi_extraction.DOIExtractionTests."
        "test_whole_order_proof_failures_are_rc012",
    )
    bind(
        ("RC-013", "RC-014", "RC-015"),
        "tests.test_doi_extraction.DOIExtractionTests."
        "test_missing_or_unreadable_required_input_is_rc013_not_unknown",
    )
    bind(
        ("RC-016",),
        "tests.test_doi_evaluator.DOIEvaluatorOverlayTests."
        "test_known_split_preserved_with_unrelated_unknown_availability",
    )
    bind(
        ("RC-017",),
        "tests.test_doi_evaluator.DOIEvaluatorOverlayTests."
        "test_known_split_preserved_with_unrelated_unknown_ds_state",
    )
    bind(
        ("RC-018",),
        "tests.test_doi_evaluator.DOIEvaluatorOverlayTests."
        "test_unknown_continuity_routes_to_actual_opportunity_not_tr037",
    )
    bind(
        (
            "RC-019",
            "RC-020",
            "RC-021",
            "RC-022",
            "RC-023",
            "RC-028",
            "RC-029",
            "RC-030",
            "RC-031",
            "RC-032",
            "RC-052",
        ),
        "tests.test_doi_reason_owners.DOIActualRuleReasonOwnershipTests."
        "test_core_rule_outputs_emit_exact_registered_reasons",
    )
    bind(
        ("RC-024", "RC-058"),
        "tests.test_doi_evaluator.DOIEvaluatorOverlayTests."
        "test_dedupe_approval_does_not_close_but_verified_later_note_does",
    )
    bind(
        ("RC-025",),
        "tests.test_doi_evaluator.DOIEvaluatorBranchTests."
        "test_default_monitor_is_tr038_and_human_out_of_scope_is_exact_closure",
    )
    bind(
        ("RC-026", "RC-027"),
        "tests.test_doi_evaluator.DOIEvaluatorBranchTests."
        "test_payment_only_excludes_but_payment_with_split_preserves_opportunity",
    )
    bind(
        ("RC-033",),
        "tests.test_doi_evaluator.DOIEvaluatorBranchTests."
        "test_exact_sku_standalone_is_rc033_and_never_substitution",
    )
    bind(
        ("RC-034", "RC-035", "RC-036", "RC-037", "RC-042"),
        "tests.test_doi_evaluator.DOIEvaluatorBranchTests."
        "test_every_valid_alternate_type_reaches_tr035_with_exact_reason",
    )
    bind(
        ("RC-038", "RC-039", "RC-040", "RC-041", "RC-043", "RC-048", "RC-059"),
        "tests.test_doi_evaluator.DOIEvaluatorBranchTests."
        "test_alternate_research_and_compatibility_decisions_are_distinct",
    )
    bind(
        ("RC-044", "RC-045", "RC-046", "RC-047"),
        "tests.test_doi_evaluator.DOIEvaluatorBranchTests."
        "test_alternate_observation_and_terminal_relationship_blocks_are_exact",
    )
    bind(
        ("RC-049", "RC-050", "RC-051"),
        "tests.test_doi_evaluator.DOIEvaluatorBranchTests."
        "test_every_geography_class_has_its_exact_split_handling",
    )
    bind(
        ("RC-053", "RC-054", "RC-055", "RC-056", "RC-057"),
        "tests.test_doi_evaluator.DOIEvaluatorBranchTests."
        "test_wwc_known_author_and_timing_matrix_has_exact_behavior",
    )
    bind(
        ("RC-060", "RC-077"),
        "tests.test_doi_interventions.TestDoiInterventions."
        "test_unverified_action_and_reversal_emit_verification_requirements",
    )
    bind(
        ("RC-061",),
        "tests.test_doi_interventions.TestDoiInterventions."
        "test_only_verified_action_creates_intervention",
    )
    bind(
        ("RC-062", "RC-112"),
        "tests.test_doi_interventions.TestDoiInterventions."
        "test_human_action_requires_authority_and_emits_exact_reason",
    )
    bind(
        ("RC-063", "RC-099"),
        "tests.test_doi_retention.TestDoiRetention."
        "test_unverified_value_is_zero_and_action_date_unavailable_has_no_row",
    )
    bind(
        ("RC-064", "RC-068", "RC-069"),
        "tests.test_doi_interventions.TestDoiInterventions."
        "test_system_value_and_append_only_partial_full_reversal",
    )
    bind(
        ("RC-065", "RC-066"),
        "tests.test_doi_interventions.TestDoiInterventions."
        "test_system_value_controls_conflicting_human_history",
    )
    bind(
        ("RC-067",),
        "tests.test_doi_interventions.TestDoiInterventions."
        "test_human_estimate_is_rejected_and_history_unchanged",
    )
    bind(
        ("RC-070", "RC-071", "RC-072", "RC-104"),
        "tests.test_doi_interventions.TestDoiInterventions."
        "test_resulting_link_conflict_and_resolution_preserve_revisions",
    )
    bind(
        ("RC-073",),
        "tests.test_doi_interventions.TestDoiInterventions."
        "test_search_not_found_and_ambiguous_are_not_exact_links",
    )
    bind(
        ("RC-074", "RC-075"),
        "tests.test_doi_retention.TestDoiRetention."
        "test_split_rep_proof_is_resulting_order_scoped",
    )
    bind(
        ("RC-076", "RC-102"),
        "tests.test_doi_interventions.TestDoiInterventions."
        "test_value_exact_replay_and_occurrence_conflict",
    )
    bind(
        ("RC-078", "RC-080"),
        "tests.test_doi_retention.TestDoiRetention."
        "test_reversible_reopen_requires_byte_equal_prior_binding",
    )
    bind(
        ("RC-079",),
        "tests.test_doi_retention.TestDoiRetention."
        "test_retention_binds_policy_timezone_and_exact_deadline",
    )
    bind(
        ("RC-081",),
        "tests.test_doi_retention.TestDoiRetention."
        "test_kpi_rejects_cross_intervention_link_and_direct_contribution_forgery",
    )
    bind(
        ("RC-082", "RC-083"),
        "tests.test_doi_boundaries.DOIMilestone3CapabilityBoundaryTests."
        "test_read_only_is_allowed_and_prohibited_capabilities_emit_exact_reasons",
    )
    bind(
        ("RC-084",),
        "tests.test_doi_evaluator.DOIEvaluatorOverlayTests."
        "test_rc084_evaluation_gate_creates_no_substitute_evaluation",
    )
    bind(
        ("RC-085", "RC-095"),
        "tests.test_doi_evaluator.DOIEvaluatorOverlayTests."
        "test_value_unavailability_and_mixed_currency_emit_exact_reasons",
    )
    bind(
        ("RC-086", "RC-088"),
        "tests.test_doi_retention.TestDoiRetention."
        "test_atomic_purge_finalizes_bucket_and_leaves_no_drillthrough_identity",
    )
    bind(
        ("RC-087", "RC-098"),
        "tests.test_doi_evaluator.DOIEvaluatorOverlayTests."
        "test_overlapping_opportunities_survive_and_withhold_aggregate",
    )
    bind(
        ("RC-091",),
        "tests.test_doi_source.DOISourceClassificationTests."
        "test_batch_identity_reuses_exact_material_without_reusing_candidate_id",
    )
    bind(
        ("RC-092", "RC-093", "RC-114"),
        "tests.test_doi_retention.TestDoiRetention."
        "test_noncase_identity_schedule_and_transaction_local_purge_reasons",
    )
    bind(
        ("RC-094", "RC-106"),
        "tests.test_doi_evaluator.DOIEvaluatorOverlayTests."
        "test_currency_and_evaluation_hash_boundaries_emit_exact_reasons",
    )
    bind(
        ("RC-096",),
        "tests.test_doi_retention.TestDoiRetention."
        "test_retention_clock_failure_emits_rc096",
    )
    bind(
        ("RC-097",),
        "tests.test_doi_evaluator.DOIEvaluatorOverlayTests."
        "test_forged_alternate_candidate_material_cannot_enable_tr035",
    )
    bind(
        ("RC-100",),
        "tests.test_doi_retention.TestDoiRetention."
        "test_finalization_function_rejects_mixed_bucket_identity",
    )
    bind(
        ("RC-101",),
        "tests.test_doi_retention.TestDoiRetention."
        "test_reconciliation_mismatch_and_fault_roll_back_transfer_and_delete",
    )
    bind(
        ("RC-103",),
        "tests.test_doi_lifecycle.TestDoiLifecycle."
        "test_same_occurrence_with_changed_material_conflicts",
    )
    bind(
        ("RC-105",),
        "tests.test_doi_evaluator.DOIEvaluatorOverlayTests."
        "test_disjoint_mutually_exclusive_options_require_scenario_selection",
    )
    bind(
        ("RC-107", "RC-108", "RC-109"),
        "tests.test_doi_knowledge.DOIProductKnowledgeTests."
        "test_revision_history_is_immutable_sequential_and_terminal",
    )
    bind(
        ("RC-110",),
        "tests.test_doi_knowledge.DOIProductKnowledgeTests."
        "test_action_context_binding_invalid_emits_rc110",
    )
    bind(
        ("RC-111",),
        "tests.test_doi_lifecycle.TestDoiLifecycle."
        "test_sequence_predecessor_and_from_state_conflicts_preserve_stream",
    )
    bind(
        ("RC-113",),
        "tests.test_doi_lifecycle.TestDoiLifecycle."
        "test_malformed_lifecycle_event_schema_is_rc113_before_append",
    )
    bind(
        tuple(f"RC-{number:03d}" for number in range(115, 139)),
        "tests.test_doi_evaluator.DOIEvaluatorOverlayTests."
        "test_every_field_specific_unknown_reason_is_emitted_by_actual_evaluation",
    )
    return MappingProxyType(selectors)


ACTUAL_REASON_OWNER_SELECTORS = _actual_reason_owner_selectors()


def _reason_selector(reason: ReasonRef) -> str:
    try:
        return ACTUAL_REASON_OWNER_SELECTORS[reason.code]
    except KeyError:
        raise DOITraceabilityError("REASON_OWNER_SELECTOR_MISSING") from None


def _transition_selector(transition: TransitionRef, branch: str) -> str:
    stem = transition.transition_id.lower().replace("-", "_")
    suffix = {
        "legal": "production_owner_legal",
        "invalid": "production_owner_invalid_from_state",
    }.get(branch)
    if suffix is None:
        raise DOITraceabilityError("TRANSITION_SELECTOR_BRANCH_INVALID")
    return (
        "tests.test_doi_lifecycle.TestAllRegisteredDoiTransitions."
        f"test_{stem}_{suffix}"
    )


def reason_oracle_rows(
    registries: DoiRegistries | None = None,
) -> tuple[ReasonOracleRow, ...]:
    """Derive exactly one effective executable ownership row per supplied reason."""

    registry = registries or load_doi_registries()
    if set(ACTUAL_REASON_OWNER_SELECTORS) != {
        reason.code for reason in registry.reason_refs
    }:
        raise DOITraceabilityError("REASON_OWNER_SELECTOR_SET_INVALID")
    effective = effective_reason_routes(registry)
    rows: list[ReasonOracleRow] = []
    for reason in registry.reason_refs:
        supplied = registry.ownership_transition_refs(reason)
        routes = effective[reason.code]
        ownership = registry.ownership_record(reason)
        row = ReasonOracleRow(
            reason=reason,
            effective_transitions=routes,
            rule_or_boundary_only=not routes,
            ownership_mode=ownership.ownership_mode,
            actual_test_selector=_reason_selector(reason),
            decision_overlay_applied=routes != supplied,
        )
        for transition in routes:
            assert_reason_route_legal(reason, transition, registries=registry)
        if not routes:
            assert_reason_route_legal(reason, None, registries=registry)
        rows.append(row)
    return tuple(rows)


def transition_coverage_rows(
    registries: DoiRegistries | None = None,
) -> tuple[TransitionCoverageRow, ...]:
    """Derive the real collected legal/invalid selector pair for all transitions."""

    registry = registries or load_doi_registries()
    return tuple(
        TransitionCoverageRow(
            transition=transition,
            legal_test_selector=_transition_selector(transition, "legal"),
            invalid_test_selector=_transition_selector(transition, "invalid"),
        )
        for transition in registry.transition_refs
    )


def traceability_test_selectors() -> tuple[str, ...]:
    """Return the duplicate-free required selector inventory in byte order."""

    selectors = {
        row.actual_test_selector for row in reason_oracle_rows()
    }
    for row in transition_coverage_rows():
        selectors.add(row.legal_test_selector)
        selectors.add(row.invalid_test_selector)
    return tuple(sorted(selectors))


def _markdown_cell(value: str) -> str:
    return " ".join(value.split()).replace("|", "\\|")


def render_reason_ownership_markdown() -> str:
    """Render the checked-in effective 138-row reason/oracle reconciliation."""

    registry = load_doi_registries()
    rows = reason_oracle_rows(registry)
    overlay_rows = tuple(row for row in rows if row.decision_overlay_applied)
    lines = [
        "# Milestone 3 DOI reason ownership reconciliation",
        "",
        "Generated from the supplied registries plus the approved repository-side",
        "opportunity-preservation overlay. Manual edits are rejected by executable tests.",
        "",
        f"- Traceability version: `{DOI_TRACEABILITY_VERSION}`",
        f"- Supplied reasons: {len(registry.reason_refs)}",
        f"- Supplied ownership rows: {len(rows)}",
        f"- Effective oracle rows: {len(rows)}",
        f"- Overlay-adjusted rows: {len(overlay_rows)}",
        "- Illegal accepted reason/transition routes: 0",
        "",
        "| Reason | Label | Effective transitions | Ownership mode | Overlay | Collected oracle |",
        "|---|---|---|---|---:|---|",
    ]
    for row in rows:
        routes = (
            ", ".join(item.transition_id for item in row.effective_transitions)
            or "BOUNDARY_ONLY"
        )
        lines.append(
            f"| `{row.reason.code}` | `{_markdown_cell(row.reason.label)}` | `{routes}` | "
            f"`{row.ownership_mode}` | `{str(row.decision_overlay_applied).lower()}` | "
            f"`{row.actual_test_selector}` |"
        )
    lines.append("")
    return "\n".join(lines)


def render_transition_matrix_markdown() -> str:
    """Render all 115 supplied transitions and their collected legal/invalid tests."""

    from synthetic_sales_assist.doi.lifecycle import transition_definition

    rows = transition_coverage_rows()
    lines = [
        "# Milestone 3 DOI transition implementation matrix",
        "",
        "Generated from the immutable transition registry and executable lifecycle inventory.",
        "",
        f"- Traceability version: `{DOI_TRACEABILITY_VERSION}`",
        f"- Registered transitions: {len(rows)}",
        f"- Collected legal-path selectors: {len(rows)}",
        f"- Collected invalid-family selectors: {len(rows)}",
        "",
        (
            "| Transition | From | To | Registered guard/evidence | Required effects | "
            "Legal test | Invalid test |"
        ),
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        definition = transition_definition(row.transition)
        lines.append(
            f"| `{row.transition.transition_id}` | `{_markdown_cell(definition.from_state)}` | "
            f"`{_markdown_cell(definition.to_state)}` | {_markdown_cell(definition.guard)} | "
            f"{_markdown_cell(definition.required_effects)} | `{row.legal_test_selector}` | "
            f"`{row.invalid_test_selector}` |"
        )
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "ACTUAL_REASON_OWNER_SELECTORS",
    "DOI_TRACEABILITY_VERSION",
    "DOITraceabilityError",
    "ReasonOracleRow",
    "TransitionCoverageRow",
    "reason_oracle_rows",
    "render_reason_ownership_markdown",
    "render_transition_matrix_markdown",
    "traceability_test_selectors",
    "transition_coverage_rows",
]
