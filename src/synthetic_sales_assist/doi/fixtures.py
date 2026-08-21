"""Deterministic synthetic-only DOI scenario catalog for Milestone 3.

The catalog is generated from rule requirements and registered transitions, never from real
records.  It carries no adapter, clock, persistence, or network capability.  Every row binds a
real collected test selector and declares the complete expected-result dimensions, including
explicitly inapplicable dimensions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from synthetic_sales_assist.doi.models import (
    AttentionCondition,
    DOIState,
    HumanReviewKind,
    OpportunityType,
    TerminalClosureReason,
    ValueAvailabilityState,
)
from synthetic_sales_assist.doi.traceability import transition_coverage_rows
from synthetic_sales_assist.domain.identities import EvidenceId
from synthetic_sales_assist.domain.registries import (
    ReasonRef,
    TransitionRef,
    load_doi_registries,
)
from synthetic_sales_assist.domain.tokens import ImmutableStrEnum


DOI_SCENARIO_CATALOG_VERSION = "synthetic-doi-scenario-catalog/v2"
_TOKEN = re.compile(r"^[A-Z][A-Z0-9_]{0,95}$", re.ASCII)
_SELECTOR = re.compile(
    r"^tests\.test_doi_[a-z0-9_]+\.[A-Za-z][A-Za-z0-9_]+\.test_[a-z0-9_]+$",
    re.ASCII,
)
SAFETY_COUNTER_NAMES = (
    "EXTERNAL_MUTATION_REQUEST_COUNT",
    "EXTERNAL_PRODUCTION_SYSTEM_ACCESS_COUNT",
    "NON_LOCALHOST_RUNTIME_REQUEST_COUNT",
    "NON_SYNTHETIC_FIXTURE_COUNT",
    "PRODUCTION_MUTATION_REQUEST_COUNT",
    "PRODUCTION_SYSTEM_ACCESS_COUNT",
    "REAL_CUSTOMER_DATA_COUNT",
    "REAL_CUSTOMER_IDENTITY_COUNT",
    "SECRET_MATERIAL_COUNT",
)
ZERO_SAFETY_COUNTERS = tuple((name, 0) for name in SAFETY_COUNTER_NAMES)


class DOIFixtureError(ValueError):
    """Reject an incomplete, unsafe, or open synthetic scenario declaration."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ScenarioFamily(ImmutableStrEnum):
    SOURCE_RUN = "SOURCE_RUN"
    EXTRACTION = "EXTRACTION"
    CORE_RULES = "CORE_RULES"
    ALTERNATES = "ALTERNATES"
    CONTACT_WWC_DEDUPE = "CONTACT_WWC_DEDUPE"
    INTERVENTION_RESULT_KPI = "INTERVENTION_RESULT_KPI"
    LIFECYCLE_TRANSITION = "LIFECYCLE_TRANSITION"


class ScenarioExecutionKind(ImmutableStrEnum):
    """Closed proof route by which a scenario is reconciled to executable behavior."""

    EVALUATION_RESULT = "EVALUATION_RESULT"
    OWNER_BOUNDARY_ORACLE = "OWNER_BOUNDARY_ORACLE"
    TRANSITION_LEGAL = "TRANSITION_LEGAL"
    TRANSITION_INVALID_GUARD = "TRANSITION_INVALID_GUARD"


class ScopeExpectation(ImmutableStrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NONE = "NONE"
    EXACT_SINGLE = "EXACT_SINGLE"
    EXACT_MULTI_LINE = "EXACT_MULTI_LINE"
    PRESERVED_SEPARATE = "PRESERVED_SEPARATE"


class ScenarioEffect(ImmutableStrEnum):
    APPEND_ATTEMPT = "APPEND_ATTEMPT"
    APPEND_BATCH = "APPEND_BATCH"
    APPEND_EVALUATION = "APPEND_EVALUATION"
    APPEND_EVENT = "APPEND_EVENT"
    APPEND_INTERVENTION = "APPEND_INTERVENTION"
    APPEND_KPI_CONTRIBUTION = "APPEND_KPI_CONTRIBUTION"
    APPEND_REJECTION = "APPEND_REJECTION"
    APPEND_RUN = "APPEND_RUN"
    APPEND_SNAPSHOT = "APPEND_SNAPSHOT"
    APPEND_WORK_ITEM = "APPEND_WORK_ITEM"
    CLEAR_ATTENTION = "CLEAR_ATTENTION"
    CLOSE_CASE = "CLOSE_CASE"
    DELETE_CASE_GRAPH = "DELETE_CASE_GRAPH"
    FINALIZE_NONIDENTIFYING_KPI = "FINALIZE_NONIDENTIFYING_KPI"
    NO_ACCEPTED_APPEND = "NO_ACCEPTED_APPEND"
    NO_DURABLE_BUSINESS_PERSISTENCE = "NO_DURABLE_BUSINESS_PERSISTENCE"
    NO_EXTERNAL_MUTATION = "NO_EXTERNAL_MUTATION"
    SCHEDULE_RETENTION = "SCHEDULE_RETENTION"
    SET_ATTENTION = "SET_ATTENTION"
    UPDATE_PROJECTION = "UPDATE_PROJECTION"
    UPDATE_VALUE_HISTORY = "UPDATE_VALUE_HISTORY"


@dataclass(frozen=True, slots=True)
class DOISyntheticScenario:
    """One closed synthetic scenario and all expected result dimensions."""

    scenario_id: EvidenceId
    scenario_key: str
    family: ScenarioFamily
    execution_kind: ScenarioExecutionKind
    synthetic_inputs: tuple[EvidenceId, ...]
    expected_top_level_state: DOIState | None
    expected_reasons: tuple[ReasonRef, ...]
    expected_opportunities: tuple[OpportunityType, ...]
    scope_expectation: ScopeExpectation
    human_review: tuple[HumanReviewKind, ...]
    attention: tuple[AttentionCondition, ...]
    closure: TerminalClosureReason | None
    transitions: tuple[TransitionRef, ...]
    event_effects: tuple[ScenarioEffect, ...]
    expected_value_state: ValueAvailabilityState | None
    test_selectors: tuple[str, ...]
    safety_counters: tuple[tuple[str, int], ...] = ZERO_SAFETY_COUNTERS
    version: str = DOI_SCENARIO_CATALOG_VERSION

    def __post_init__(self) -> None:
        if type(self.scenario_id) is not EvidenceId:
            raise DOIFixtureError("SCENARIO_ID_INVALID")
        if type(self.scenario_key) is not str or _TOKEN.fullmatch(self.scenario_key) is None:
            raise DOIFixtureError("SCENARIO_KEY_INVALID")
        if type(self.family) is not ScenarioFamily:
            raise DOIFixtureError("SCENARIO_FAMILY_INVALID")
        if type(self.execution_kind) is not ScenarioExecutionKind:
            raise DOIFixtureError("SCENARIO_EXECUTION_KIND_INVALID")
        if self.expected_top_level_state is not None:
            expected_execution_kind = ScenarioExecutionKind.EVALUATION_RESULT
        elif self.family is ScenarioFamily.LIFECYCLE_TRANSITION:
            expected_execution_kind = (
                ScenarioExecutionKind.TRANSITION_LEGAL
                if self.scenario_key.endswith("_LEGAL")
                else ScenarioExecutionKind.TRANSITION_INVALID_GUARD
            )
        else:
            expected_execution_kind = ScenarioExecutionKind.OWNER_BOUNDARY_ORACLE
        if self.execution_kind is not expected_execution_kind:
            raise DOIFixtureError("SCENARIO_EXECUTION_KIND_PARTITION_INVALID")
        _require_exact_tuple(self.synthetic_inputs, EvidenceId, "SCENARIO_INPUTS_INVALID")
        if not self.synthetic_inputs:
            raise DOIFixtureError("SCENARIO_INPUTS_INVALID")
        if self.expected_top_level_state is not None and (
            type(self.expected_top_level_state) is not DOIState
        ):
            raise DOIFixtureError("SCENARIO_STATE_INVALID")
        _require_sorted_unique(
            self.expected_reasons,
            ReasonRef,
            lambda item: item.code,
            "SCENARIO_REASONS_INVALID",
        )
        _require_sorted_unique(
            self.expected_opportunities,
            OpportunityType,
            lambda item: item.value,
            "SCENARIO_OPPORTUNITIES_INVALID",
        )
        if type(self.scope_expectation) is not ScopeExpectation:
            raise DOIFixtureError("SCENARIO_SCOPE_INVALID")
        _require_sorted_unique(
            self.human_review,
            HumanReviewKind,
            lambda item: item.value,
            "SCENARIO_REVIEW_INVALID",
        )
        _require_sorted_unique(
            self.attention,
            AttentionCondition,
            lambda item: item.value,
            "SCENARIO_ATTENTION_INVALID",
        )
        if self.closure is not None and type(self.closure) is not TerminalClosureReason:
            raise DOIFixtureError("SCENARIO_CLOSURE_INVALID")
        _require_sorted_unique(
            self.transitions,
            TransitionRef,
            lambda item: item.transition_id,
            "SCENARIO_TRANSITIONS_INVALID",
        )
        _require_sorted_unique(
            self.event_effects,
            ScenarioEffect,
            lambda item: item.value,
            "SCENARIO_EFFECTS_INVALID",
        )
        if ScenarioEffect.NO_EXTERNAL_MUTATION not in self.event_effects:
            raise DOIFixtureError("SCENARIO_EXTERNAL_MUTATION_GUARD_MISSING")
        if ScenarioEffect.NO_DURABLE_BUSINESS_PERSISTENCE not in self.event_effects:
            raise DOIFixtureError("SCENARIO_PERSISTENCE_BOUNDARY_MISSING")
        if self.expected_value_state is not None and (
            type(self.expected_value_state) is not ValueAvailabilityState
        ):
            raise DOIFixtureError("SCENARIO_VALUE_INVALID")
        if (
            type(self.test_selectors) is not tuple
            or not self.test_selectors
            or self.test_selectors != tuple(sorted(set(self.test_selectors)))
            or any(_SELECTOR.fullmatch(item) is None for item in self.test_selectors)
        ):
            raise DOIFixtureError("SCENARIO_SELECTORS_INVALID")
        if self.safety_counters != ZERO_SAFETY_COUNTERS:
            raise DOIFixtureError("SCENARIO_SAFETY_COUNTERS_INVALID")
        if self.version != DOI_SCENARIO_CATALOG_VERSION:
            raise DOIFixtureError("SCENARIO_VERSION_INVALID")


def _require_exact_tuple(values: object, expected: type[object], code: str) -> None:
    if type(values) is not tuple or any(type(item) is not expected for item in values):
        raise DOIFixtureError(code)


def _require_sorted_unique(
    values: object,
    expected: type[object],
    key: object,
    code: str,
) -> None:
    _require_exact_tuple(values, expected, code)
    key_function = key
    names = tuple(key_function(item) for item in values)  # type: ignore[operator]
    if names != tuple(sorted(set(names))):
        raise DOIFixtureError(code)


@dataclass(frozen=True, slots=True)
class _ScenarioSeed:
    key: str
    family: ScenarioFamily
    selector: str
    state: DOIState | None = None
    reasons: tuple[str, ...] = ()
    opportunities: tuple[OpportunityType, ...] = ()
    scope: ScopeExpectation = ScopeExpectation.NOT_APPLICABLE
    reviews: tuple[HumanReviewKind, ...] = ()
    attention: tuple[AttentionCondition, ...] = ()
    closure: TerminalClosureReason | None = None
    transitions: tuple[str, ...] = ()
    effects: tuple[ScenarioEffect, ...] = ()
    value: ValueAvailabilityState | None = None


_SOURCE = "tests.test_doi_source."
_EXTRACTION = "tests.test_doi_extraction.DOIExtractionTests."
_EVALUATOR = "tests.test_doi_evaluator."
_KNOWLEDGE = "tests.test_doi_knowledge.DOIProductKnowledgeTests."
_MODELS = "tests.test_doi_models.DOIModelTests."
_LIFECYCLE = "tests.test_doi_lifecycle.TestDoiLifecycle."
_INTERVENTIONS = "tests.test_doi_interventions.TestDoiInterventions."
_RETENTION = "tests.test_doi_retention.TestDoiRetention."
_STATE = "tests.test_doi_state.TestInMemoryDoiState."


def _seed(
    key: str,
    family: ScenarioFamily,
    selector: str,
    **values: object,
) -> _ScenarioSeed:
    return _ScenarioSeed(key, family, selector, **values)  # type: ignore[arg-type]


def _identity_suffix(scenario_key: str) -> str:
    return scenario_key.replace("_", "-")


_NAMED_SEEDS = (
    _seed(
        "VALID_REVIEW_RUN",
        ScenarioFamily.SOURCE_RUN,
        _SOURCE
        + "DOIRunControlTests."
        "test_tab_confirmation_is_preallocation_gate_and_start_replays",
        transitions=("TR-001", "TR-098"),
        effects=(ScenarioEffect.APPEND_ATTEMPT, ScenarioEffect.APPEND_RUN),
    ),
    _seed(
        "DUPLICATE_ROWS_MERGED",
        ScenarioFamily.SOURCE_RUN,
        _SOURCE
        + "DOISourceClassificationTests."
        "test_duplicates_merge_conflicts_reject_and_row_count_equation_is_exact",
        reasons=("RC-006",),
        transitions=("TR-099",),
        effects=(ScenarioEffect.APPEND_BATCH, ScenarioEffect.APPEND_WORK_ITEM),
    ),
    _seed(
        "INVALID_ORDER_NUMBER",
        ScenarioFamily.SOURCE_RUN,
        _SOURCE
        + "DOISourceClassificationTests."
        "test_locked_schema_invalid_order_is_attempt_failure_and_rc003_is_unreachable",
        reasons=("RC-002", "RC-090"),
        transitions=("TR-100",),
        effects=(ScenarioEffect.APPEND_ATTEMPT,),
    ),
    _seed(
        "OUT_OF_SCOPE_ASSIGNEE",
        ScenarioFamily.SOURCE_RUN,
        _SOURCE
        + "DOISourceClassificationTests."
        "test_duplicates_merge_conflicts_reject_and_row_count_equation_is_exact",
        reasons=("RC-005",),
    ),
    _seed(
        "ASSIGNEE_CONFLICT",
        ScenarioFamily.SOURCE_RUN,
        _SOURCE
        + "DOISourceClassificationTests."
        "test_duplicates_merge_conflicts_reject_and_row_count_equation_is_exact",
        reasons=("RC-008",),
        transitions=("TR-103",),
        effects=(ScenarioEffect.APPEND_REJECTION,),
    ),
    _seed(
        "SOURCE_CHANGED",
        ScenarioFamily.SOURCE_RUN,
        _SOURCE
        + "DOISourceClassificationTests."
        "test_source_change_revision_partition_and_inaccessible_reads_fail_closed",
        reasons=("RC-009", "RC-090"),
        transitions=("TR-100",),
        effects=(ScenarioEffect.APPEND_ATTEMPT,),
    ),
    _seed(
        "SOURCE_INACCESSIBLE",
        ScenarioFamily.SOURCE_RUN,
        _SOURCE
        + "DOISourceClassificationTests."
        "test_source_change_revision_partition_and_inaccessible_reads_fail_closed",
        reasons=("RC-089", "RC-090"),
        transitions=("TR-100",),
        effects=(ScenarioEffect.APPEND_ATTEMPT,),
    ),
    _seed(
        "FAILED_ATTEMPT_WAIT_AND_EXACT_RETRY",
        ScenarioFamily.SOURCE_RUN,
        _SOURCE
        + "DOIRunControlTests."
        "test_failed_attempt_waits_indefinitely_then_retry_is_next_ordinal_and_replays",
        transitions=("TR-098", "TR-100"),
        effects=(ScenarioEffect.APPEND_ATTEMPT,),
    ),
    _seed(
        "RETRY_CONFLICT",
        ScenarioFamily.SOURCE_RUN,
        _SOURCE
        + "DOIRunControlTests."
        "test_failed_attempt_waits_indefinitely_then_retry_is_next_ordinal_and_replays",
        transitions=("TR-098",),
        effects=(ScenarioEffect.NO_ACCEPTED_APPEND,),
    ),
    _seed(
        "EXPLICIT_NO_RETRY_FINALIZATION",
        ScenarioFamily.SOURCE_RUN,
        _SOURCE + "DOIRunControlTests.test_explicit_no_retry_terminalizes_and_replays_before_state",
        transitions=("TR-004",),
        effects=(ScenarioEffect.APPEND_EVENT, ScenarioEffect.UPDATE_PROJECTION),
    ),
    _seed(
        "RETRY_WINS_RACE",
        ScenarioFamily.SOURCE_RUN,
        _SOURCE + "DOIRunControlTests.test_retry_commit_wins_over_no_retry_for_prior_attempt",
        transitions=("TR-098",),
        effects=(ScenarioEffect.APPEND_ATTEMPT,),
    ),
    _seed(
        "FINALIZATION_WINS_RACE",
        ScenarioFamily.SOURCE_RUN,
        _STATE + "test_authoritative_crossed_race_has_exactly_one_winner",
        transitions=("TR-004",),
        effects=(ScenarioEffect.APPEND_EVENT, ScenarioEffect.UPDATE_PROJECTION),
    ),
    _seed(
        "RECHECK_RUN_TYPES",
        ScenarioFamily.SOURCE_RUN,
        _SOURCE + "DOIRunControlTests.test_rechecks_have_one_work_item_and_no_source_attempt",
        effects=(ScenarioEffect.APPEND_RUN, ScenarioEffect.APPEND_WORK_ITEM),
    ),
    _seed(
        "RC084_PRE_EXTRACTION_FAILURE",
        ScenarioFamily.SOURCE_RUN,
        _SOURCE
        + "DOIRunControlTests."
        "test_extraction_reservation_and_rc084_systemic_failure_both_race_orders",
        reasons=("RC-084",),
        transitions=("TR-004",),
        effects=(ScenarioEffect.APPEND_EVENT, ScenarioEffect.UPDATE_PROJECTION),
    ),
    _seed(
        "SYSTEMIC_ONE_WORK_ZERO_DISPOSITIONS",
        ScenarioFamily.SOURCE_RUN,
        _STATE + "test_rc084_branch_wins_with_zero_reads_dispositions_and_evaluations",
        reasons=("RC-084",),
        transitions=("TR-004",),
        effects=(ScenarioEffect.APPEND_EVENT, ScenarioEffect.UPDATE_PROJECTION),
    ),
    _seed(
        "NORMAL_COMPLETION_COUNTS",
        ScenarioFamily.SOURCE_RUN,
        _SOURCE
        + "DOIRunControlTests."
        "test_normal_completion_is_derived_from_one_disposition_per_work_item",
        transitions=("TR-002",),
        effects=(ScenarioEffect.APPEND_EVENT, ScenarioEffect.UPDATE_PROJECTION),
    ),
    _seed(
        "ALL_BLOCKED_COMPLETION_WITH_EXCEPTIONS",
        ScenarioFamily.SOURCE_RUN,
        _SOURCE
        + "DOIRunControlTests."
        "test_all_blocked_run_completes_with_exceptions_and_zero_success",
        transitions=("TR-003",),
        effects=(ScenarioEffect.APPEND_EVENT, ScenarioEffect.UPDATE_PROJECTION),
    ),
    _seed(
        "EMPTY_COHERENT_BATCH_COMPLETION",
        ScenarioFamily.SOURCE_RUN,
        _SOURCE
        + "DOIRunControlTests."
        "test_empty_coherent_personal_batch_completes_without_dispositions",
        transitions=("TR-002",),
        effects=(ScenarioEffect.APPEND_EVENT, ScenarioEffect.UPDATE_PROJECTION),
    ),
    _seed(
        "SOURCE_CELL_PRIVACY_FIREWALL",
        ScenarioFamily.SOURCE_RUN,
        _SOURCE
        + "DOISourceClassificationTests."
        "test_source_cells_are_firewalled_and_raw_assignee_is_not_hash_retained",
        effects=(ScenarioEffect.NO_ACCEPTED_APPEND,),
    ),
    _seed(
        "COMPLETE_ORDINARY_ORDER",
        ScenarioFamily.EXTRACTION,
        _EXTRACTION + "test_complete_snapshot_binds_canonical_source_time_and_manifest",
        transitions=("TR-005",),
        effects=(ScenarioEffect.APPEND_SNAPSHOT,),
    ),
    _seed(
        "LARGE_AND_ZERO_RELEVANT_ORDERS",
        ScenarioFamily.EXTRACTION,
        _EXTRACTION + "test_large_and_explicitly_empty_complete_orders_succeed",
        transitions=("TR-005",),
        effects=(ScenarioEffect.APPEND_SNAPSHOT,),
    ),
    _seed(
        "WRONG_ORDER_IDENTITY",
        ScenarioFamily.EXTRACTION,
        _EXTRACTION + "test_identity_missing_or_mismatch_is_rc011",
        reasons=("RC-011", "RC-014", "RC-015"),
        transitions=("TR-006", "TR-020"),
        attention=(AttentionCondition.RECHECK_REQUIRED,),
        effects=(ScenarioEffect.APPEND_ATTEMPT, ScenarioEffect.SET_ATTENTION),
    ),
    _seed(
        "MISSING_REQUIRED_SECTION",
        ScenarioFamily.EXTRACTION,
        _EXTRACTION + "test_missing_or_unreadable_required_input_is_rc013_not_unknown",
        reasons=("RC-013", "RC-014", "RC-015"),
        transitions=("TR-006", "TR-020"),
        attention=(AttentionCondition.RECHECK_REQUIRED,),
        effects=(ScenarioEffect.APPEND_ATTEMPT, ScenarioEffect.SET_ATTENTION),
    ),
    _seed(
        "WHOLE_ORDER_COUNT_DUPLICATE_CHANGE_OR_TIME_FAILURE",
        ScenarioFamily.EXTRACTION,
        _EXTRACTION + "test_whole_order_proof_failures_are_rc012",
        reasons=("RC-012", "RC-014", "RC-015"),
        transitions=("TR-006", "TR-020"),
        attention=(AttentionCondition.RECHECK_REQUIRED,),
        effects=(ScenarioEffect.APPEND_ATTEMPT, ScenarioEffect.SET_ATTENTION),
    ),
    _seed(
        "UNNORMALIZABLE_REQUIRED_TIMESTAMP",
        ScenarioFamily.EXTRACTION,
        _EXTRACTION + "test_unnormalizable_required_source_time_is_extraction_failure",
        reasons=("RC-013", "RC-014", "RC-015"),
        transitions=("TR-006", "TR-020"),
        attention=(AttentionCondition.RECHECK_REQUIRED,),
        effects=(ScenarioEffect.APPEND_ATTEMPT, ScenarioEffect.SET_ATTENTION),
    ),
    _seed(
        "UNKNOWN_FIELD_VERSUS_MISSING_FIELD",
        ScenarioFamily.EXTRACTION,
        _EXTRACTION + "test_field_unknown_survives_success_while_missing_line_fails",
        transitions=("TR-005", "TR-006"),
        effects=(ScenarioEffect.APPEND_ATTEMPT, ScenarioEffect.APPEND_SNAPSHOT),
    ),
    _seed(
        "STABLE_AND_COMPOSITE_CONTINUITY",
        ScenarioFamily.EXTRACTION,
        _EXTRACTION + "test_stable_and_closed_composite_line_continuity_and_no_description_guess",
        transitions=("TR-005",),
        effects=(ScenarioEffect.APPEND_SNAPSHOT,),
    ),
    _seed(
        "FULL_DIRECT_SHIP",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR + "DOIEvaluatorBranchTests.test_full_ds_is_excluded_but_has_no_closure",
        state=DOIState.DOI_EXCLUDED,
        reasons=("RC-019",),
        scope=ScopeExpectation.NONE,
        transitions=("TR-027", "TR-031"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.UNAVAILABLE,
    ),
    _seed(
        "MIXED_DIRECT_SHIP",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR + "DOIEvaluatorBranchTests.test_mixed_ds_continues_non_ds_analysis",
        state=DOIState.DOI_OPPORTUNITY,
        reasons=("RC-020", "RC-030"),
        opportunities=(OpportunityType.DS_SEPARATION,),
        scope=ScopeExpectation.EXACT_MULTI_LINE,
        reviews=(HumanReviewKind.COMMERCIAL_DECISION,),
        transitions=("TR-027", "TR-033"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.AVAILABLE,
    ),
    _seed(
        "ORDINARY_FULFILLMENT_SPLIT",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR
        + "DOIEvaluatorBranchTests."
        "test_every_geography_class_has_its_exact_split_handling",
        state=DOIState.DOI_OPPORTUNITY,
        reasons=("RC-031", "RC-052"),
        opportunities=(OpportunityType.FULFILLMENT_SPLIT,),
        scope=ScopeExpectation.EXACT_MULTI_LINE,
        reviews=(HumanReviewKind.COMMERCIAL_DECISION,),
        transitions=("TR-027", "TR-034", "TR-060"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.AVAILABLE,
    ),
    _seed(
        "FULFILLMENT_SPLIT_WITH_UNRELATED_UNKNOWN",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR
        + "DOIEvaluatorOverlayTests."
        "test_known_split_preserved_with_unrelated_unknown_availability",
        state=DOIState.DOI_OPPORTUNITY,
        reasons=("RC-016", "RC-031", "RC-052"),
        opportunities=(OpportunityType.FULFILLMENT_SPLIT,),
        scope=ScopeExpectation.EXACT_MULTI_LINE,
        reviews=(
            HumanReviewKind.COMMERCIAL_DECISION,
            HumanReviewKind.UNKNOWN_FACT,
        ),
        transitions=("TR-027", "TR-034", "TR-060"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.AVAILABLE,
    ),
    _seed(
        "FULFILLMENT_SPLIT_WITH_UNRELATED_UNKNOWN_DS",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR
        + "DOIEvaluatorOverlayTests."
        "test_known_split_preserved_with_unrelated_unknown_ds_state",
        state=DOIState.DOI_OPPORTUNITY,
        reasons=("RC-017", "RC-031", "RC-052"),
        opportunities=(OpportunityType.FULFILLMENT_SPLIT,),
        scope=ScopeExpectation.EXACT_MULTI_LINE,
        reviews=(
            HumanReviewKind.COMMERCIAL_DECISION,
            HumanReviewKind.UNKNOWN_FACT,
        ),
        transitions=("TR-027", "TR-034", "TR-060"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.AVAILABLE,
    ),
    _seed(
        "ONLY_CANDIDATE_BLOCKED_BY_UNKNOWN",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR
        + "DOIEvaluatorOverlayTests."
        "test_unknown_that_blocks_only_candidate_routes_to_tr037",
        state=DOIState.DOI_MANUAL_REVIEW,
        reasons=("RC-016",),
        scope=ScopeExpectation.NONE,
        reviews=(HumanReviewKind.UNKNOWN_FACT,),
        transitions=("TR-027", "TR-037"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.UNAVAILABLE,
    ),
    _seed(
        "UNKNOWN_CONTINUITY_PRESERVES_INDEPENDENT_SPLIT",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR
        + "DOIEvaluatorOverlayTests."
        "test_unknown_continuity_routes_to_actual_opportunity_not_tr037",
        state=DOIState.DOI_OPPORTUNITY,
        reasons=("RC-018", "RC-031", "RC-052", "RC-124"),
        opportunities=(OpportunityType.FULFILLMENT_SPLIT,),
        scope=ScopeExpectation.EXACT_MULTI_LINE,
        reviews=(
            HumanReviewKind.COMMERCIAL_DECISION,
            HumanReviewKind.UNKNOWN_FACT,
        ),
        transitions=("TR-027", "TR-034", "TR-060"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.AVAILABLE,
    ),
    _seed(
        "MULTI_UNKNOWN_EXACT_SET_UNION",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR
        + "DOIEvaluatorOverlayTests."
        "test_multiple_independent_unknowns_emit_the_exact_set_union",
        state=DOIState.DOI_MANUAL_REVIEW,
        reasons=("RC-016", "RC-017", "RC-115", "RC-121", "RC-122", "RC-123"),
        scope=ScopeExpectation.NONE,
        reviews=(HumanReviewKind.UNKNOWN_FACT,),
        transitions=("TR-027", "TR-037"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.UNAVAILABLE,
    ),
    _seed(
        "PARTIAL_QUANTITY_REVIEW",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR + "DOIEvaluatorBranchTests.test_partial_quantity_is_never_an_automatic_action",
        state=DOIState.DOI_OPPORTUNITY,
        reasons=("RC-032", "RC-052"),
        opportunities=(OpportunityType.PARTIAL_QUANTITY_REVIEW,),
        scope=ScopeExpectation.EXACT_SINGLE,
        reviews=(HumanReviewKind.COMMERCIAL_DECISION,),
        transitions=("TR-027", "TR-034", "TR-060"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.AVAILABLE,
    ),
    _seed(
        "PAYMENT_ONLY_EXCLUSION",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR
        + "DOIEvaluatorBranchTests."
        "test_payment_only_excludes_but_payment_with_split_preserves_opportunity",
        state=DOIState.DOI_EXCLUDED,
        reasons=("RC-026",),
        scope=ScopeExpectation.NONE,
        transitions=("TR-027", "TR-032"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.UNAVAILABLE,
    ),
    _seed(
        "PAYMENT_WITH_SPLIT_OPPORTUNITY",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR
        + "DOIEvaluatorBranchTests."
        "test_payment_only_excludes_but_payment_with_split_preserves_opportunity",
        state=DOIState.DOI_OPPORTUNITY,
        reasons=("RC-027", "RC-031", "RC-052"),
        opportunities=(OpportunityType.FULFILLMENT_SPLIT,),
        scope=ScopeExpectation.EXACT_MULTI_LINE,
        reviews=(HumanReviewKind.COMMERCIAL_DECISION,),
        transitions=("TR-027", "TR-034", "TR-060"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.AVAILABLE,
    ),
    _seed(
        "ALL_IN_STOCK_PROGRESS_REVIEW",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR + "DOIEvaluatorBranchTests.test_all_in_stock_progress_review_and_monitor",
        state=DOIState.DOI_MANUAL_REVIEW,
        reasons=("RC-028",),
        scope=ScopeExpectation.NONE,
        reviews=(HumanReviewKind.ORDER_PROGRESS,),
        transitions=("TR-027", "TR-036"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.UNAVAILABLE,
    ),
    _seed(
        "HUMAN_NO_ACTION_MONITOR",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR + "DOIEvaluatorBranchTests.test_all_in_stock_progress_review_and_monitor",
        state=DOIState.DOI_MONITOR,
        reasons=("RC-029",),
        scope=ScopeExpectation.NONE,
        transitions=("TR-027", "TR-039"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.UNAVAILABLE,
    ),
    _seed(
        "SHIPPED_HARD_CLOSURE",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR
        + "DOIEvaluatorBranchTests."
        "test_hard_and_reversible_closures_precede_product_rules",
        state=DOIState.DOI_EXCLUDED,
        reasons=("RC-021",),
        scope=ScopeExpectation.NONE,
        closure=TerminalClosureReason.SHIPPED,
        transitions=("TR-027", "TR-029"),
        effects=(ScenarioEffect.APPEND_EVALUATION, ScenarioEffect.CLOSE_CASE),
        value=ValueAvailabilityState.UNAVAILABLE,
    ),
    _seed(
        "CANCELED_HARD_CLOSURE",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR
        + "DOIEvaluatorBranchTests."
        "test_hard_and_reversible_closures_precede_product_rules",
        state=DOIState.DOI_EXCLUDED,
        reasons=("RC-022",),
        scope=ScopeExpectation.NONE,
        closure=TerminalClosureReason.CANCELED,
        transitions=("TR-027", "TR-029"),
        effects=(ScenarioEffect.APPEND_EVALUATION, ScenarioEffect.CLOSE_CASE),
        value=ValueAvailabilityState.UNAVAILABLE,
    ),
    _seed(
        "REP_TRANSFER_REVERSIBLE_CLOSURE",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR
        + "DOIEvaluatorBranchTests."
        "test_hard_and_reversible_closures_precede_product_rules",
        state=DOIState.DOI_EXCLUDED,
        reasons=("RC-023",),
        scope=ScopeExpectation.NONE,
        closure=TerminalClosureReason.REP_TRANSFERRED,
        transitions=("TR-027", "TR-030"),
        effects=(ScenarioEffect.APPEND_EVALUATION, ScenarioEffect.CLOSE_CASE),
        value=ValueAvailabilityState.UNAVAILABLE,
    ),
    _seed(
        "HUMAN_OUT_OF_SCOPE_REVERSIBLE_CLOSURE",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR
        + "DOIEvaluatorBranchTests."
        "test_default_monitor_is_tr038_and_human_out_of_scope_is_exact_closure",
        state=DOIState.DOI_EXCLUDED,
        reasons=("RC-025",),
        scope=ScopeExpectation.NONE,
        closure=TerminalClosureReason.HUMAN_OUT_OF_SCOPE,
        transitions=("TR-027", "TR-030"),
        effects=(ScenarioEffect.APPEND_EVALUATION, ScenarioEffect.CLOSE_CASE),
        value=ValueAvailabilityState.UNAVAILABLE,
    ),
    _seed(
        "SOURCE_ABSENCE_RECHECK",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR
        + "DOIEvaluatorBranchTests."
        "test_source_absence_forces_recheck_monitor_and_suppresses_stale_closure",
        state=DOIState.DOI_MONITOR,
        reasons=("RC-010",),
        scope=ScopeExpectation.NONE,
        attention=(AttentionCondition.SOURCE_ABSENCE_RECHECK_REQUIRED,),
        transitions=("TR-021", "TR-027", "TR-038"),
        effects=(ScenarioEffect.APPEND_EVALUATION, ScenarioEffect.SET_ATTENTION),
        value=ValueAvailabilityState.UNAVAILABLE,
    ),
    _seed(
        "DOMESTIC_SPECIAL_REVIEW_SPLIT",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR
        + "DOIEvaluatorBranchTests."
        "test_every_geography_class_has_its_exact_split_handling",
        state=DOIState.DOI_OPPORTUNITY,
        reasons=("RC-031", "RC-049", "RC-052"),
        opportunities=(OpportunityType.FULFILLMENT_SPLIT,),
        scope=ScopeExpectation.EXACT_MULTI_LINE,
        reviews=(HumanReviewKind.COMMERCIAL_DECISION, HumanReviewKind.SHIPPING),
        transitions=("TR-027", "TR-034", "TR-060"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.AVAILABLE,
    ),
    _seed(
        "INTERNATIONAL_SPLIT",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR
        + "DOIEvaluatorBranchTests."
        "test_every_geography_class_has_its_exact_split_handling",
        state=DOIState.DOI_OPPORTUNITY,
        reasons=("RC-031", "RC-050", "RC-051", "RC-052"),
        opportunities=(OpportunityType.FULFILLMENT_SPLIT,),
        scope=ScopeExpectation.EXACT_MULTI_LINE,
        reviews=(
            HumanReviewKind.COMMERCIAL_DECISION,
            HumanReviewKind.CUSTOMER_CONTACT,
            HumanReviewKind.SHIPPING,
        ),
        transitions=("TR-027", "TR-034", "TR-060", "TR-065"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.AVAILABLE,
    ),
    _seed(
        "UNKNOWN_GEOGRAPHY_SPLIT",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR
        + "DOIEvaluatorBranchTests."
        "test_every_geography_class_has_its_exact_split_handling",
        state=DOIState.DOI_OPPORTUNITY,
        reasons=("RC-031", "RC-052", "RC-119"),
        opportunities=(OpportunityType.FULFILLMENT_SPLIT,),
        scope=ScopeExpectation.EXACT_MULTI_LINE,
        reviews=(
            HumanReviewKind.COMMERCIAL_DECISION,
            HumanReviewKind.SHIPPING,
            HumanReviewKind.UNKNOWN_FACT,
        ),
        transitions=("TR-027", "TR-034", "TR-060"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.AVAILABLE,
    ),
    _seed(
        "INTERNATIONAL_SPLIT_WITH_UNKNOWN_ETA",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR
        + "DOIEvaluatorBranchTests."
        "test_geography_and_unknown_eta_do_not_erase_split",
        state=DOIState.DOI_OPPORTUNITY,
        reasons=("RC-031", "RC-050", "RC-051", "RC-052", "RC-115"),
        opportunities=(OpportunityType.FULFILLMENT_SPLIT,),
        scope=ScopeExpectation.EXACT_MULTI_LINE,
        reviews=(
            HumanReviewKind.COMMERCIAL_DECISION,
            HumanReviewKind.CUSTOMER_CONTACT,
            HumanReviewKind.SHIPPING,
            HumanReviewKind.UNKNOWN_FACT,
        ),
        transitions=("TR-027", "TR-034", "TR-060", "TR-065"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.AVAILABLE,
    ),
    _seed(
        "OVERLAP_UNAVAILABLE_THEN_HUMAN_SELECTED",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR
        + "DOIEvaluatorOverlayTests."
        "test_overlapping_opportunities_survive_and_withhold_aggregate",
        state=DOIState.DOI_OPPORTUNITY,
        reasons=("RC-031", "RC-033", "RC-052", "RC-087"),
        opportunities=(
            OpportunityType.EXACT_SKU_RECHECK,
            OpportunityType.FULFILLMENT_SPLIT,
        ),
        scope=ScopeExpectation.PRESERVED_SEPARATE,
        reviews=(
            HumanReviewKind.COMMERCIAL_DECISION,
            HumanReviewKind.SCENARIO_SELECTION,
        ),
        transitions=("TR-027", "TR-034", "TR-035", "TR-060"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.UNAVAILABLE,
    ),
    _seed(
        "HUMAN_SCENARIO_SELECTION_RESOLVES_AGGREGATE",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR
        + "DOIEvaluatorOverlayTests."
        "test_overlapping_opportunities_survive_and_withhold_aggregate",
        state=DOIState.DOI_OPPORTUNITY,
        reasons=("RC-031", "RC-033", "RC-052"),
        opportunities=(
            OpportunityType.EXACT_SKU_RECHECK,
            OpportunityType.FULFILLMENT_SPLIT,
        ),
        scope=ScopeExpectation.PRESERVED_SEPARATE,
        reviews=(HumanReviewKind.COMMERCIAL_DECISION,),
        transitions=("TR-027", "TR-034", "TR-035", "TR-060"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.AVAILABLE,
    ),
    _seed(
        "DISJOINT_MUTUALLY_EXCLUSIVE_OPTIONS",
        ScenarioFamily.CORE_RULES,
        _EVALUATOR
        + "DOIEvaluatorOverlayTests."
        "test_disjoint_mutually_exclusive_options_require_scenario_selection",
        state=DOIState.DOI_OPPORTUNITY,
        reasons=("RC-033", "RC-087"),
        opportunities=(OpportunityType.EXACT_SKU_RECHECK,),
        scope=ScopeExpectation.PRESERVED_SEPARATE,
        reviews=(HumanReviewKind.SCENARIO_SELECTION,),
        transitions=("TR-027", "TR-035"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.UNAVAILABLE,
    ),
    _seed(
        "ALTERNATE_HIERARCHY_AND_COMPATIBILITY",
        ScenarioFamily.ALTERNATES,
        _KNOWLEDGE + "test_relationship_hierarchy_stays_distinct_and_product_only",
        effects=(ScenarioEffect.APPEND_EVENT,),
    ),
    _seed(
        "EXACT_SKU_RECHECK",
        ScenarioFamily.ALTERNATES,
        _EVALUATOR
        + "DOIEvaluatorBranchTests."
        "test_exact_sku_standalone_is_rc033_and_never_substitution",
        state=DOIState.DOI_OPPORTUNITY,
        reasons=("RC-033",),
        opportunities=(OpportunityType.EXACT_SKU_RECHECK,),
        scope=ScopeExpectation.EXACT_SINGLE,
        transitions=("TR-027", "TR-035"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.AVAILABLE,
    ),
    *(
        _seed(
            key,
            ScenarioFamily.ALTERNATES,
            _EVALUATOR
            + "DOIEvaluatorBranchTests."
            "test_every_valid_alternate_type_reaches_tr035_with_exact_reason",
            state=DOIState.DOI_OPPORTUNITY,
            reasons=(reason, "RC-042"),
            opportunities=(opportunity,),
            scope=ScopeExpectation.EXACT_SINGLE,
            reviews=(HumanReviewKind.CUSTOMER_APPROVAL,),
            transitions=("TR-027", "TR-035"),
            effects=(ScenarioEffect.APPEND_EVALUATION,),
            value=ValueAvailabilityState.AVAILABLE,
        )
        for key, reason, opportunity in (
            (
                "EXACT_MFG_ALTERNATE",
                "RC-034",
                OpportunityType.EXACT_MFG_ALTERNATE,
            ),
            (
                "MFG_CROSS_REFERENCE",
                "RC-035",
                OpportunityType.MFG_CROSS_REFERENCE,
            ),
            (
                "MFG_SUPERSESSION",
                "RC-036",
                OpportunityType.MFG_SUPERSESSION,
            ),
            (
                "FUNCTIONAL_ALTERNATE",
                "RC-037",
                OpportunityType.FUNCTIONAL_ALTERNATE,
            ),
        )
    ),
    _seed(
        "NO_EXACT_MFG_OR_VERIFIED_ALTERNATE",
        ScenarioFamily.ALTERNATES,
        _EVALUATOR
        + "DOIEvaluatorBranchTests."
        "test_alternate_research_and_compatibility_decisions_are_distinct",
        state=DOIState.DOI_MONITOR,
        reasons=("RC-038", "RC-039", "RC-058"),
        scope=ScopeExpectation.NONE,
        reviews=(HumanReviewKind.DEDUPE_DECISION,),
        transitions=("TR-027", "TR-038", "TR-060"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.UNAVAILABLE,
    ),
    _seed(
        "MANUAL_ALTERNATE_IDENTIFICATION",
        ScenarioFamily.ALTERNATES,
        _EVALUATOR
        + "DOIEvaluatorBranchTests."
        "test_alternate_research_and_compatibility_decisions_are_distinct",
        state=DOIState.DOI_MANUAL_REVIEW,
        reasons=("RC-040", "RC-059"),
        scope=ScopeExpectation.NONE,
        reviews=(HumanReviewKind.UNKNOWN_FACT,),
        transitions=("TR-027", "TR-037"),
        effects=(ScenarioEffect.APPEND_EVALUATION,),
        value=ValueAvailabilityState.UNAVAILABLE,
    ),
    _seed(
        "ALTERNATE_REVISION_SUPERSEDED_INVALIDATED",
        ScenarioFamily.ALTERNATES,
        _KNOWLEDGE + "test_revision_history_is_immutable_sequential_and_terminal",
        transitions=("TR-040", "TR-041", "TR-083"),
        effects=(ScenarioEffect.APPEND_EVENT,),
    ),
    _seed(
        "STALE_ALTERNATE_OBSERVATION",
        ScenarioFamily.ALTERNATES,
        _KNOWLEDGE + "test_stale_observation_never_binds_as_current",
        reasons=("RC-045",),
        transitions=("TR-042",),
        effects=(ScenarioEffect.APPEND_EVENT,),
    ),
    _seed(
        "WWC_ALL_PRESENT_PARTITIONS",
        ScenarioFamily.CONTACT_WWC_DEDUPE,
        _EXTRACTION + "test_all_wwc_present_known_unknown_nested_partitions_are_constructible",
        effects=(ScenarioEffect.APPEND_SNAPSHOT,),
    ),
    _seed(
        "WWC_MALFORMED_NESTED_FINDING",
        ScenarioFamily.CONTACT_WWC_DEDUPE,
        _MODELS + "test_all_wwc_present_known_unknown_partitions_are_constructible",
        effects=(ScenarioEffect.NO_ACCEPTED_APPEND,),
    ),
    _seed(
        "CONTACT_ALL_GOVERNED_STATES",
        ScenarioFamily.CONTACT_WWC_DEDUPE,
        _MODELS + "test_action_context_and_contact_histories_replay_and_correct_exactly",
        effects=(ScenarioEffect.APPEND_EVENT, ScenarioEffect.UPDATE_PROJECTION),
    ),
    _seed(
        "DEDUPE_CANDIDATE_INCOMPLETE_AND_REJECTED",
        ScenarioFamily.CONTACT_WWC_DEDUPE,
        _EVALUATOR
        + "DOIEvaluatorOverlayTests."
        "test_dedupe_approval_does_not_close_but_verified_later_note_does",
        reasons=("RC-058", "RC-059"),
        transitions=("TR-061", "TR-062", "TR-064"),
        effects=(ScenarioEffect.APPEND_EVALUATION, ScenarioEffect.APPEND_EVENT),
    ),
    _seed(
        "DEDUPE_APPROVAL_AWAITING_AND_LATER_CONFIRMATION",
        ScenarioFamily.CONTACT_WWC_DEDUPE,
        _EVALUATOR
        + "DOIEvaluatorOverlayTests."
        "test_dedupe_approval_does_not_close_but_verified_later_note_does",
        transitions=("TR-061", "TR-063"),
        effects=(ScenarioEffect.APPEND_EVALUATION, ScenarioEffect.CLOSE_CASE),
    ),
    _seed(
        "ATTENTION_COEXISTENCE_AND_EXACT_CLEAR",
        ScenarioFamily.CONTACT_WWC_DEDUPE,
        _LIFECYCLE + "test_attention_causes_coexist_and_clear_references_exact_set",
        effects=(
            ScenarioEffect.APPEND_EVENT,
            ScenarioEffect.CLEAR_ATTENTION,
            ScenarioEffect.SET_ATTENTION,
        ),
    ),
    _seed(
        "UNVERIFIED_SYSTEM_AND_HUMAN_ACTION",
        ScenarioFamily.INTERVENTION_RESULT_KPI,
        _INTERVENTIONS + "test_only_verified_action_creates_intervention",
        effects=(ScenarioEffect.APPEND_INTERVENTION,),
    ),
    _seed(
        "ACTION_REPLAY_AND_OCCURRENCE_CONFLICT",
        ScenarioFamily.INTERVENTION_RESULT_KPI,
        _INTERVENTIONS + "test_action_exact_replay_and_changed_occurrence_conflict",
        effects=(ScenarioEffect.APPEND_INTERVENTION,),
    ),
    _seed(
        "VALUE_CORRECTION_PARTIAL_AND_FULL_REVERSAL",
        ScenarioFamily.INTERVENTION_RESULT_KPI,
        _INTERVENTIONS + "test_system_value_and_append_only_partial_full_reversal",
        transitions=("TR-046", "TR-050", "TR-051"),
        effects=(ScenarioEffect.UPDATE_VALUE_HISTORY,),
    ),
    _seed(
        "HUMAN_VALUE_ESTIMATE_REJECTED",
        ScenarioFamily.INTERVENTION_RESULT_KPI,
        _INTERVENTIONS + "test_human_estimate_is_rejected_and_history_unchanged",
        reasons=("RC-067",),
        transitions=("TR-047",),
        effects=(ScenarioEffect.NO_ACCEPTED_APPEND,),
    ),
    _seed(
        "RESULT_LINK_AUTO_HUMAN_AMBIGUOUS_NOT_FOUND",
        ScenarioFamily.INTERVENTION_RESULT_KPI,
        _INTERVENTIONS + "test_resulting_link_conflict_and_resolution_preserve_revisions",
        transitions=("TR-054", "TR-058", "TR-056"),
        effects=(ScenarioEffect.APPEND_EVENT,),
    ),
    _seed(
        "RESULT_LINK_SEARCH_NOT_FOUND_AND_AMBIGUOUS",
        ScenarioFamily.INTERVENTION_RESULT_KPI,
        _INTERVENTIONS + "test_search_not_found_and_ambiguous_are_not_exact_links",
        transitions=("TR-088", "TR-089"),
        effects=(ScenarioEffect.APPEND_EVENT,),
    ),
    _seed(
        "KPI_EXACT_ONCE_AND_SCOPED_REP",
        ScenarioFamily.INTERVENTION_RESULT_KPI,
        _RETENTION + "test_verified_substitution_contributes_once_on_new_york_action_date",
        effects=(ScenarioEffect.APPEND_KPI_CONTRIBUTION,),
    ),
    _seed(
        "KPI_MIXED_CURRENCY_SEGMENTATION",
        ScenarioFamily.INTERVENTION_RESULT_KPI,
        _RETENTION + "test_mixed_currencies_remain_separate_buckets",
        reasons=("RC-095",),
        effects=(ScenarioEffect.APPEND_KPI_CONTRIBUTION,),
    ),
    _seed(
        "PURGE_FINALIZATION_AND_ROLLBACK",
        ScenarioFamily.INTERVENTION_RESULT_KPI,
        _RETENTION + "test_reconciliation_mismatch_and_fault_roll_back_transfer_and_delete",
        transitions=("TR-112",),
        effects=(ScenarioEffect.DELETE_CASE_GRAPH, ScenarioEffect.FINALIZE_NONIDENTIFYING_KPI),
    ),
)


def _scenario_from_seed(seed: _ScenarioSeed) -> DOISyntheticScenario:
    registries = load_doi_registries()
    base_effects = {
        ScenarioEffect.NO_DURABLE_BUSINESS_PERSISTENCE,
        ScenarioEffect.NO_EXTERNAL_MUTATION,
        *seed.effects,
    }
    execution_kind = (
        ScenarioExecutionKind.EVALUATION_RESULT
        if seed.state is not None
        else ScenarioExecutionKind.OWNER_BOUNDARY_ORACLE
    )
    return DOISyntheticScenario(
        scenario_id=EvidenceId(
            f"SYN-EVIDENCE-DOI-SCENARIO-{_identity_suffix(seed.key)}"
        ),
        scenario_key=seed.key,
        family=seed.family,
        execution_kind=execution_kind,
        synthetic_inputs=(
            EvidenceId(f"SYN-EVIDENCE-DOI-INPUT-{_identity_suffix(seed.key)}"),
        ),
        expected_top_level_state=seed.state,
        expected_reasons=tuple(
            sorted(
                (registries.reason_ref(code) for code in seed.reasons),
                key=lambda item: item.code,
            )
        ),
        expected_opportunities=tuple(
            sorted(seed.opportunities, key=lambda item: item.value)
        ),
        scope_expectation=seed.scope,
        human_review=tuple(sorted(seed.reviews, key=lambda item: item.value)),
        attention=tuple(sorted(seed.attention, key=lambda item: item.value)),
        closure=seed.closure,
        transitions=tuple(
            sorted(
                (registries.transition_ref(code) for code in seed.transitions),
                key=lambda item: item.transition_id,
            )
        ),
        event_effects=tuple(sorted(base_effects, key=lambda item: item.value)),
        expected_value_state=seed.value,
        test_selectors=(seed.selector,),
    )


def named_scenarios() -> tuple[DOISyntheticScenario, ...]:
    """Return the requirement-derived scenario catalog, independent of source quotas."""

    return tuple(
        _scenario_from_seed(seed)
        for seed in _NAMED_SEEDS
    )


def transition_scenarios() -> tuple[DOISyntheticScenario, ...]:
    """Generate one legal and one focused false-guard scenario per registered transition."""

    rows: list[DOISyntheticScenario] = []
    for coverage in transition_coverage_rows():
        transition = coverage.transition
        for branch, selector, accepted in (
            ("LEGAL", coverage.legal_test_selector, True),
            ("INVALID_GUARD", coverage.invalid_test_selector, False),
        ):
            effects = {
                ScenarioEffect.NO_DURABLE_BUSINESS_PERSISTENCE,
                ScenarioEffect.NO_EXTERNAL_MUTATION,
                (
                    ScenarioEffect.APPEND_EVENT
                    if accepted
                    else ScenarioEffect.NO_ACCEPTED_APPEND
                ),
            }
            scenario_key = transition.transition_id.replace("-", "_") + "_" + branch
            rows.append(
                DOISyntheticScenario(
                    scenario_id=EvidenceId(
                        "SYN-EVIDENCE-DOI-SCENARIO-"
                        + _identity_suffix(scenario_key)
                    ),
                    scenario_key=scenario_key,
                    family=ScenarioFamily.LIFECYCLE_TRANSITION,
                    execution_kind=(
                        ScenarioExecutionKind.TRANSITION_LEGAL
                        if accepted
                        else ScenarioExecutionKind.TRANSITION_INVALID_GUARD
                    ),
                    synthetic_inputs=(
                        EvidenceId(
                            "SYN-EVIDENCE-DOI-INPUT-"
                            + _identity_suffix(scenario_key)
                        ),
                    ),
                    expected_top_level_state=None,
                    expected_reasons=(),
                    expected_opportunities=(),
                    scope_expectation=ScopeExpectation.NOT_APPLICABLE,
                    human_review=(),
                    attention=(),
                    closure=None,
                    transitions=(transition,),
                    event_effects=tuple(sorted(effects, key=lambda item: item.value)),
                    expected_value_state=None,
                    test_selectors=(selector,),
                )
            )
    return tuple(rows)


def scenario_catalog() -> tuple[DOISyntheticScenario, ...]:
    """Return all named plus registry-derived scenarios with unique IDs and keys."""

    rows = (*named_scenarios(), *transition_scenarios())
    if len({row.scenario_id for row in rows}) != len(rows):
        raise DOIFixtureError("SCENARIO_ID_DUPLICATE")
    if len({row.scenario_key for row in rows}) != len(rows):
        raise DOIFixtureError("SCENARIO_KEY_DUPLICATE")
    return rows


def _joined(values: tuple[object, ...], attribute: str) -> str:
    return ", ".join(str(getattr(item, attribute)) for item in values) or "-"


def render_scenario_inventory_markdown() -> str:
    """Render the checked-in inventory from actual scenario and selector rows."""

    rows = scenario_catalog()
    named_count = len(named_scenarios())
    transition_count = len(transition_scenarios())
    selector_count = len(
        {selector for row in rows for selector in row.test_selectors}
    )
    lines = [
        "# Milestone 3 synthetic DOI scenario inventory",
        "",
        "Generated from `doi.fixtures`; every selector is collected by the executable test",
        "inventory and every scenario carries the same nine zero safety counters.",
        "",
        f"- Catalog version: `{DOI_SCENARIO_CATALOG_VERSION}`",
        f"- Requirement-derived scenarios: {named_count}",
        f"- Registry-derived transition scenarios: {transition_count}",
        f"- Total scenarios: {len(rows)}",
        f"- Distinct collected selectors: {selector_count}",
        "- Safety expectation: all nine counters are zero for every scenario",
        "",
        (
            "| Scenario | Family | Execution | State | Reasons | Opportunities | Scope | Reviews | "
            "Attention | Closure | Transitions | Effects | Value | Collected test |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        state = "-" if row.expected_top_level_state is None else row.expected_top_level_state.value
        closure = "-" if row.closure is None else row.closure.value
        value = "-" if row.expected_value_state is None else row.expected_value_state.value
        lines.append(
            f"| `{row.scenario_id.value}` / `{row.scenario_key}` | `{row.family.value}` | "
            f"`{row.execution_kind.value}` | `{state}` | "
            f"`{_joined(row.expected_reasons, 'code')}` | "
            f"`{_joined(row.expected_opportunities, 'value')}` | `{row.scope_expectation.value}` | "
            f"`{_joined(row.human_review, 'value')}` | `{_joined(row.attention, 'value')}` | "
            f"`{closure}` | `{_joined(row.transitions, 'transition_id')}` | "
            f"`{_joined(row.event_effects, 'value')}` | `{value}` | "
            f"`{', '.join(row.test_selectors)}` |"
        )
    lines.extend(("", "## Safety counters", "", "| Counter | Expected |", "|---|---:|"))
    for name, value in ZERO_SAFETY_COUNTERS:
        lines.append(f"| `{name}` | {value} |")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "DOI_SCENARIO_CATALOG_VERSION",
    "DOIFixtureError",
    "DOISyntheticScenario",
    "SAFETY_COUNTER_NAMES",
    "ScenarioEffect",
    "ScenarioExecutionKind",
    "ScenarioFamily",
    "ScopeExpectation",
    "ZERO_SAFETY_COUNTERS",
    "named_scenarios",
    "render_scenario_inventory_markdown",
    "scenario_catalog",
    "transition_scenarios",
]
