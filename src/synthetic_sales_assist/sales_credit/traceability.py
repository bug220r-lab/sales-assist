"""Immutable executable-test ownership for the Milestone 2 Sales Credit rule pack.

The catalog contains no test execution or environment access.  It is a closed, deterministic
index from synthetic scenarios and acceptance requirements to collected ``unittest`` selectors.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from synthetic_sales_assist.domain.identities import EvidenceId
from synthetic_sales_assist.domain.tokens import ImmutableStrEnum
from synthetic_sales_assist.sales_credit.models import (
    EvidenceClassification,
    HumanOutcomeType,
    MaterialChangeKind,
    SalesCreditEffect,
    SalesCreditReason,
    WorkflowState,
)


TRACEABILITY_VERSION = "synthetic-sales-credit-traceability/v1"
_TOKEN = re.compile(r"^[A-Z][A-Z0-9_]{0,95}$", re.ASCII)
_SELECTOR = re.compile(
    r"^tests\.test_[a-z0-9_]+\.[A-Za-z][A-Za-z0-9_]+\.test_[a-z0-9_]+$",
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

_HUMAN_REVIEW_WORKFLOWS = frozenset(
    {
        WorkflowState.INBOUND_EVIDENCE_HUMAN_REVIEW,
        WorkflowState.MANUAL_REVIEW_REQUIRED,
        WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
        WorkflowState.OTHER_REP_HUMAN_REVIEW,
        WorkflowState.OUTBOUND_EVIDENCE_HUMAN_REVIEW,
        WorkflowState.POSSIBLE_REPLACEMENT_HUMAN_REVIEW,
        WorkflowState.TIMING_UNCERTAIN_HUMAN_REVIEW,
    }
)


class TraceabilityValidationError(ValueError):
    """Reject an incomplete or open traceability catalog."""


class AcceptanceFamily(ImmutableStrEnum):
    SCHEMA_AND_NORMALIZATION = "SCHEMA_AND_NORMALIZATION"
    WINDOWS = "WINDOWS"
    DISCOVERY = "DISCOVERY"
    RULES = "RULES"
    CASE_IDENTITY = "CASE_IDENTITY"
    RETENTION = "RETENTION"
    SAFETY = "SAFETY"
    METRICS = "METRICS"


@dataclass(frozen=True, slots=True)
class ScenarioCatalogRow:
    """One versioned synthetic scenario with an executable ownership selector."""

    scenario_id: EvidenceId
    version: str
    expected_branch: str
    expected_workflow: WorkflowState
    expected_reasons: tuple[SalesCreditReason, ...]
    human_review_required: bool
    persistence_effects: tuple[SalesCreditEffect, ...]
    safety_counters: tuple[tuple[str, int], ...]
    test_selectors: tuple[str, ...]
    evidence_branch: EvidenceClassification | None = None
    material_branch: MaterialChangeKind | None = None
    human_outcome: HumanOutcomeType | None = None

    def __post_init__(self) -> None:
        if type(self.scenario_id) is not EvidenceId:
            raise TraceabilityValidationError("scenario_id")
        if self.version != TRACEABILITY_VERSION:
            raise TraceabilityValidationError("scenario_version")
        if type(self.expected_branch) is not str or _TOKEN.fullmatch(
            self.expected_branch
        ) is None:
            raise TraceabilityValidationError("scenario_branch")
        if type(self.expected_workflow) is not WorkflowState:
            raise TraceabilityValidationError("scenario_workflow")
        _require_sorted_enum_tuple(
            self.expected_reasons,
            SalesCreditReason,
            "scenario_reasons",
        )
        if type(self.human_review_required) is not bool:
            raise TraceabilityValidationError("scenario_human_review")
        if self.human_review_required != (
            self.expected_workflow in _HUMAN_REVIEW_WORKFLOWS
        ):
            raise TraceabilityValidationError("scenario_human_review_coherence")
        _require_sorted_enum_tuple(
            self.persistence_effects,
            SalesCreditEffect,
            "scenario_effects",
        )
        if SalesCreditEffect.NO_PERSISTENCE_MILESTONE_2 not in self.persistence_effects:
            raise TraceabilityValidationError("scenario_no_persistence")
        has_human_effect = (
            SalesCreditEffect.HUMAN_REVIEW_REQUIRED in self.persistence_effects
        )
        if has_human_effect != self.human_review_required:
            raise TraceabilityValidationError("scenario_human_effect_coherence")
        if self.safety_counters != ZERO_SAFETY_COUNTERS:
            raise TraceabilityValidationError("scenario_safety_counters")
        _require_selectors(self.test_selectors, "scenario_selectors")
        for value, expected, code in (
            (self.evidence_branch, EvidenceClassification, "scenario_evidence"),
            (self.material_branch, MaterialChangeKind, "scenario_material"),
            (self.human_outcome, HumanOutcomeType, "scenario_outcome"),
        ):
            if value is not None and type(value) is not expected:
                raise TraceabilityValidationError(code)


@dataclass(frozen=True, slots=True)
class AcceptanceCoverageRow:
    """One acceptance requirement and its real collected-test ownership."""

    acceptance_id: str
    family: AcceptanceFamily
    requirement: str
    test_selectors: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.acceptance_id) is not str or _TOKEN.fullmatch(
            self.acceptance_id
        ) is None:
            raise TraceabilityValidationError("acceptance_id")
        if type(self.family) is not AcceptanceFamily:
            raise TraceabilityValidationError("acceptance_family")
        if (
            type(self.requirement) is not str
            or not self.requirement
            or not self.requirement.isascii()
            or "\n" in self.requirement
        ):
            raise TraceabilityValidationError("acceptance_requirement")
        _require_selectors(self.test_selectors, "acceptance_selectors")


def _require_sorted_enum_tuple(
    values: object,
    expected_type: type[object],
    code: str,
) -> None:
    if type(values) is not tuple or any(type(item) is not expected_type for item in values):
        raise TraceabilityValidationError(code)
    names = tuple(item.value for item in values)  # type: ignore[attr-defined]
    if names != tuple(sorted(names)) or len(names) != len(set(names)):
        raise TraceabilityValidationError(code)


def _require_selectors(values: object, code: str) -> None:
    if (
        type(values) is not tuple
        or not values
        or any(type(item) is not str or _SELECTOR.fullmatch(item) is None for item in values)
        or values != tuple(sorted(set(values)))
    ):
        raise TraceabilityValidationError(code)


def _selector(module: str, owner: str, method: str) -> str:
    return f"tests.test_sales_credit_{module}.{owner}.{method}"


WINDOW_ORDER_TIMING = _selector(
    "windows",
    "TimingClassificationTests",
    "test_exact_same_day_before_equal_and_after",
)
WINDOW_UNCERTAIN = _selector(
    "windows",
    "TimingClassificationTests",
    "test_same_day_unreliable_never_proves_order_qualification",
)
EVALUATOR_ORDER_TIMING = _selector(
    "evaluator",
    "SnapshotPrecedenceTests",
    "test_candidate_order_must_qualify_against_an_attached_interaction",
)
WINDOW_AUTOMATIC = _selector(
    "windows",
    "RecheckEligibilityTests",
    "test_automatic_check_is_eligible_once_per_new_york_date",
)
WINDOW_FORCE = _selector(
    "windows",
    "RecheckEligibilityTests",
    "test_selected_force_bypasses_only_daily_throttle_and_is_audited",
)
DISCOVERY_NO_IDENTIFIER = _selector(
    "discovery",
    "DiscoveryPlanningTests",
    "test_no_valid_identifier_requires_manual_review",
)
DISCOVERY_INCOMPLETE = _selector(
    "discovery",
    "DiscoveryCombinationTests",
    "test_missing_or_incomplete_identifier_can_never_conclude_no_order",
)
DISCOVERY_NO_ORDER = _selector(
    "discovery",
    "DiscoveryCombinationTests",
    "test_complete_empty_union_uses_exact_active_and_closed_states",
)
NO_ORDER_IDENTIFIERLESS_APPLIED = _selector(
    "no_order_closure",
    "PostEvaluationNoOrderReducerTests",
    "test_identifierless_manual_transition_is_applied_and_replay_safe",
)
NO_ORDER_INCOMPLETE_APPLIED = _selector(
    "no_order_closure",
    "PostEvaluationNoOrderReducerTests",
    "test_incomplete_enumeration_applies_governed_manual_state",
)
COORDINATOR_NO_ORDER_ACTIVE = _selector(
    "accumulator",
    "DiscoveryBatchAuthorityTests",
    "test_state_is_the_only_supported_no_order_entrypoint",
)
NO_ORDER_ACTIVE_APPLIED = _selector(
    "search_run",
    "OrderSearchRunTests",
    "test_ledger_commits_active_state_exact_replay_and_conflict_atomically",
)
NO_ORDER_TERMINAL_APPLIED = _selector(
    "no_order_closure",
    "NoOrderClosureProjectionTests",
    "test_terminal_run_derives_the_identity_free_minimized_root",
)
COORDINATOR_MIXED_ATOMIC = _selector(
    "accumulator",
    "DiscoveryBatchAuthorityTests",
    "test_mixed_positive_and_terminal_effects_commit_atomically",
)
COORDINATOR_CASE_ATTACH = _selector(
    "accumulator",
    "DiscoveryBatchAuthorityTests",
    "test_complete_multi_candidate_discovery_is_atomic_and_has_no_early_exit",
)
EVALUATOR_SNAPSHOT = _selector(
    "evaluator",
    "SnapshotPrecedenceTests",
    "test_invalid_or_missing_core_fact_stops_all_favorable_rules",
)
EVALUATOR_PARTIAL = _selector(
    "evaluator",
    "SnapshotPrecedenceTests",
    "test_partial_snapshot_blocks_only_its_dependent_dimension",
)
EVALUATOR_CONTRADICTION = _selector(
    "evaluator",
    "SnapshotPrecedenceTests",
    "test_lifecycle_raw_fact_contradiction_fails_before_rules",
)
EVALUATOR_REP = _selector(
    "evaluator",
    "AttributionAndValueTests",
    "test_every_exact_order_rep_branch_and_no_line_rep_substitution",
)
EVALUATOR_MATERIAL = _selector(
    "evaluator",
    "AttributionAndValueTests",
    "test_each_material_change_overrides_workflow_but_not_attribution",
)
EVALUATOR_VALUE = _selector(
    "evaluator",
    "AttributionAndValueTests",
    "test_routine_changes_are_nonmaterial_but_current_value_never_substitutes",
)
EVALUATOR_EVIDENCE = _selector(
    "evaluator",
    "EvidenceClassificationTests",
    "test_every_binding_evidence_branch",
)
EVALUATOR_REPLACEMENT_WINDOW = _selector(
    "evaluator",
    "CancellationAndReplacementTests",
    "test_canceled_order_open_and_expired_windows_have_zero_active_value",
)
EVALUATOR_REPLACEMENT_PRODUCT = _selector(
    "evaluator",
    "CancellationAndReplacementTests",
    "test_exact_es_mfg_one_among_many_nonexact_and_absent_branches",
)
EVALUATOR_REPLACEMENT_CUSTOMER = _selector(
    "evaluator",
    "CancellationAndReplacementTests",
    "test_customer_absence_and_incomplete_lines_cannot_prove_replacement",
)
EVALUATOR_REPLACEMENT_FAIL_CLOSED = _selector(
    "evaluator",
    "CancellationAndReplacementTests",
    "test_forged_or_out_of_window_replacement_facts_fail_closed",
)
MODEL_MATERIAL = _selector(
    "models",
    "MaterialChangeTests",
    "test_all_fourteen_kinds_have_exact_material_partition",
)
MODEL_HUMAN_OUTCOME = _selector(
    "models",
    "ManagerOutcomeTests",
    "test_all_five_human_outcomes_have_separate_coherent_records",
)
ACCUMULATOR_INITIAL = _selector(
    "accumulator",
    "ReplayAndAtomicityTests",
    "test_exact_replay_returns_the_original_logical_result_without_duplication",
)
ACCUMULATOR_CLOSED = _selector(
    "accumulator",
    "OutcomeClosureAndPurgeTests",
    "test_manager_outcome_is_separate_replay_safe_and_blocks_later_mutation",
)


def _effects(
    workflow: WorkflowState,
    *,
    component_only: bool = False,
    zero_active: bool = False,
) -> tuple[SalesCreditEffect, ...]:
    values = {SalesCreditEffect.NO_PERSISTENCE_MILESTONE_2}
    if workflow in _HUMAN_REVIEW_WORKFLOWS:
        values.add(SalesCreditEffect.HUMAN_REVIEW_REQUIRED)
    elif not component_only and workflow is not WorkflowState.CLOSED:
        values.add(SalesCreditEffect.ACTIVE_CASE_CLASSIFICATION)
    if zero_active:
        values.add(SalesCreditEffect.ZERO_ACTIVE_VALUE)
    return tuple(sorted(values, key=lambda item: item.value))


def _row(
    index: int,
    *,
    branch: str,
    workflow: WorkflowState,
    reasons: tuple[SalesCreditReason, ...],
    selectors: tuple[str, ...],
    component_only: bool = False,
    zero_active: bool = False,
    evidence: EvidenceClassification | None = None,
    material: MaterialChangeKind | None = None,
    outcome: HumanOutcomeType | None = None,
) -> ScenarioCatalogRow:
    return ScenarioCatalogRow(
        scenario_id=EvidenceId(f"SYN-EVIDENCE-M2-SCENARIO-{index:03d}"),
        version=TRACEABILITY_VERSION,
        expected_branch=branch,
        expected_workflow=workflow,
        expected_reasons=tuple(sorted(reasons, key=lambda item: item.value)),
        human_review_required=workflow in _HUMAN_REVIEW_WORKFLOWS,
        persistence_effects=_effects(
            workflow,
            component_only=component_only,
            zero_active=zero_active,
        ),
        safety_counters=ZERO_SAFETY_COUNTERS,
        test_selectors=tuple(sorted(selectors)),
        evidence_branch=evidence,
        material_branch=material,
        human_outcome=outcome,
    )


_REASON_SPECS = (
    (SalesCreditReason.NO_USABLE_SEARCH_IDENTIFIER, WorkflowState.MANUAL_REVIEW_REQUIRED,
     NO_ORDER_IDENTIFIERLESS_APPLIED, True, False, None),
    (SalesCreditReason.IDENTIFIER_SEARCH_INCOMPLETE, WorkflowState.MANUAL_REVIEW_REQUIRED,
     NO_ORDER_INCOMPLETE_APPLIED, True, False, None),
    (SalesCreditReason.NO_ORDER_WINDOW_ACTIVE, WorkflowState.CHECKED_NO_ORDER_WINDOW_ACTIVE,
     NO_ORDER_ACTIVE_APPLIED, True, False, None),
    (SalesCreditReason.NO_ORDER_WINDOW_CLOSED, WorkflowState.REVIEW_WINDOW_CLOSED_NO_ORDER,
     NO_ORDER_TERMINAL_APPLIED, True, False, None),
    (SalesCreditReason.ORDER_BEFORE_INTERACTION, WorkflowState.MANUAL_REVIEW_REQUIRED,
     EVALUATOR_ORDER_TIMING, False, False, None),
    (SalesCreditReason.ORDER_AFTER_REVIEW_WINDOW, WorkflowState.MANUAL_REVIEW_REQUIRED,
     EVALUATOR_ORDER_TIMING, False, False, None),
    (SalesCreditReason.ORDER_BEFORE_CANCELLATION,
     WorkflowState.CANCELED_REPLACEMENT_WINDOW_ACTIVE,
     EVALUATOR_REPLACEMENT_FAIL_CLOSED, False, True, None),
    (SalesCreditReason.ORDER_AFTER_REPLACEMENT_WINDOW,
     WorkflowState.CANCELED_NO_REPLACEMENT,
     EVALUATOR_REPLACEMENT_FAIL_CLOSED, False, True, None),
    (SalesCreditReason.ORDER_TIMING_UNCERTAIN, WorkflowState.TIMING_UNCERTAIN_HUMAN_REVIEW,
     EVALUATOR_ORDER_TIMING, False, False, None),
    (SalesCreditReason.AUTOMATIC_RECHECK_THROTTLED_LOCAL_DAY,
     WorkflowState.CHECKED_NO_ORDER_WINDOW_ACTIVE, WINDOW_AUTOMATIC, True, False, None),
    (SalesCreditReason.FORCE_RECHECK_ACCEPTED, WorkflowState.CHECKED_NO_ORDER_WINDOW_ACTIVE,
     WINDOW_FORCE, True, False, None),
    (SalesCreditReason.SNAPSHOT_INVALID, WorkflowState.MANUAL_REVIEW_REQUIRED,
     EVALUATOR_SNAPSHOT, False, False, None),
    (SalesCreditReason.SNAPSHOT_PARTIAL_DEPENDENCY_BLOCKED,
     WorkflowState.ORDER_CHANGED_HUMAN_REVIEW, EVALUATOR_PARTIAL, False, False, None),
    (SalesCreditReason.MISSING_REQUIRED_FIELD, WorkflowState.MANUAL_REVIEW_REQUIRED,
     EVALUATOR_SNAPSHOT, False, False, None),
    (SalesCreditReason.UNSUPPORTED_SCHEMA_OR_SNAPSHOT, WorkflowState.MANUAL_REVIEW_REQUIRED,
     EVALUATOR_CONTRADICTION, False, False, None),
    (SalesCreditReason.CONTRADICTORY_FACTS, WorkflowState.MANUAL_REVIEW_REQUIRED,
     EVALUATOR_CONTRADICTION, False, False, None),
    (SalesCreditReason.TARGET_REP, WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
     EVALUATOR_REP, False, False, None),
    (SalesCreditReason.TARGET_REP_WEB, WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
     EVALUATOR_REP, False, False, None),
    (SalesCreditReason.UNASSIGNED_WEB, WorkflowState.EVIDENCE_NEEDED,
     EVALUATOR_REP, False, False, None),
    (SalesCreditReason.OTHER_KNOWN_REP, WorkflowState.OTHER_REP_HUMAN_REVIEW,
     EVALUATOR_REP, False, False, None),
    (SalesCreditReason.REP_MISSING, WorkflowState.MANUAL_REVIEW_REQUIRED,
     EVALUATOR_REP, False, False, None),
    (SalesCreditReason.REP_UNRECOGNIZED, WorkflowState.MANUAL_REVIEW_REQUIRED,
     EVALUATOR_REP, False, False, None),
    (SalesCreditReason.TWO_WAY_PREORDER_INTERACTION, WorkflowState.VERIFIED_PREORDER_EVIDENCE,
     EVALUATOR_EVIDENCE, False, False, EvidenceClassification.VERIFIED_PREORDER_EVIDENCE),
    (SalesCreditReason.CONNECTED_PREORDER_CALL, WorkflowState.VERIFIED_PREORDER_EVIDENCE,
     EVALUATOR_EVIDENCE, False, False, None),
    (SalesCreditReason.INBOUND_ONLY_PREORDER_CONTACT,
     WorkflowState.INBOUND_EVIDENCE_HUMAN_REVIEW, EVALUATOR_EVIDENCE, False, False,
     EvidenceClassification.INBOUND_EVIDENCE_HUMAN_REVIEW),
    (SalesCreditReason.OUTBOUND_ONLY_PREORDER_CONTACT,
     WorkflowState.OUTBOUND_EVIDENCE_HUMAN_REVIEW, EVALUATOR_EVIDENCE, False, False,
     EvidenceClassification.OUTBOUND_EVIDENCE_HUMAN_REVIEW),
    (SalesCreditReason.MISSED_OR_UNANSWERED_INBOUND_CALL,
     WorkflowState.INBOUND_EVIDENCE_HUMAN_REVIEW, EVALUATOR_EVIDENCE, False, False, None),
    (SalesCreditReason.POST_ORDER_CONTACT_ONLY, WorkflowState.MANUAL_REVIEW_REQUIRED,
     EVALUATOR_EVIDENCE, False, False, EvidenceClassification.POST_ORDER_CONTACT_ONLY),
    (SalesCreditReason.EVIDENCE_TIMING_UNCERTAIN,
     WorkflowState.TIMING_UNCERTAIN_HUMAN_REVIEW, EVALUATOR_EVIDENCE, False, False,
     EvidenceClassification.TIMING_UNCERTAIN_HUMAN_REVIEW),
    (SalesCreditReason.EVIDENCE_IDENTITY_UNPROVED, WorkflowState.MANUAL_REVIEW_REQUIRED,
     EVALUATOR_EVIDENCE, False, False,
     EvidenceClassification.UNKNOWN_OR_CONTRADICTORY),
    (SalesCreditReason.NO_QUALIFYING_PREORDER_EVIDENCE, WorkflowState.EVIDENCE_NEEDED,
     EVALUATOR_EVIDENCE, False, False, None),
    (SalesCreditReason.CANCELED_ORDER_ZERO_ACTIVE_VALUE,
     WorkflowState.CANCELED_REPLACEMENT_WINDOW_ACTIVE, EVALUATOR_REPLACEMENT_WINDOW,
     False, True, None),
    (SalesCreditReason.REPLACEMENT_WINDOW_ACTIVE,
     WorkflowState.CANCELED_REPLACEMENT_WINDOW_ACTIVE, EVALUATOR_REPLACEMENT_WINDOW,
     False, True, None),
    (SalesCreditReason.EXACT_ES_PRODUCT_CONTINUITY,
     WorkflowState.POSSIBLE_REPLACEMENT_HUMAN_REVIEW, EVALUATOR_REPLACEMENT_PRODUCT,
     False, True, None),
    (SalesCreditReason.EXACT_MFG_OE_PRODUCT_CONTINUITY,
     WorkflowState.POSSIBLE_REPLACEMENT_HUMAN_REVIEW, EVALUATOR_REPLACEMENT_PRODUCT,
     False, True, None),
    (SalesCreditReason.NONEXACT_PRODUCT_CONTINUITY_REQUIRES_REVIEW,
     WorkflowState.POSSIBLE_REPLACEMENT_HUMAN_REVIEW, EVALUATOR_REPLACEMENT_PRODUCT,
     False, True, None),
    (SalesCreditReason.CUSTOMER_CONTINUITY_UNPROVED,
     WorkflowState.POSSIBLE_REPLACEMENT_HUMAN_REVIEW, EVALUATOR_REPLACEMENT_CUSTOMER,
     False, True, None),
    (SalesCreditReason.CUSTOMER_CONTINUITY_MISMATCH,
     WorkflowState.CANCELED_REPLACEMENT_WINDOW_ACTIVE, EVALUATOR_REPLACEMENT_CUSTOMER,
     False, True, None),
    (SalesCreditReason.NO_PRODUCT_CONTINUITY,
     WorkflowState.CANCELED_REPLACEMENT_WINDOW_ACTIVE, EVALUATOR_REPLACEMENT_PRODUCT,
     False, True, None),
    (SalesCreditReason.REPLACEMENT_WINDOW_EXPIRED, WorkflowState.CANCELED_NO_REPLACEMENT,
     EVALUATOR_REPLACEMENT_WINDOW, False, True, None),
    (SalesCreditReason.PLACED_VALUE_PROVED, WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
     EVALUATOR_VALUE, False, False, None),
    (SalesCreditReason.PLACED_VALUE_UNAVAILABLE, WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
     EVALUATOR_VALUE, False, False, None),
    (SalesCreditReason.MATERIAL_CHANGE_DETECTED, WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
     EVALUATOR_MATERIAL, False, False, None),
    (SalesCreditReason.ROUTINE_LIFECYCLE_CHANGE_NONMATERIAL,
     WorkflowState.CREDIT_CONFIRMED_TARGET_REP, EVALUATOR_VALUE, False, False, None),
    (SalesCreditReason.AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW,
     WorkflowState.MANUAL_REVIEW_REQUIRED, EVALUATOR_REPLACEMENT_FAIL_CLOSED,
     False, False, None),
)


REASON_SCENARIOS = tuple(
    _row(
        index,
        branch=reason.value,
        workflow=workflow,
        reasons=(reason,),
        selectors=(selector,) if type(selector) is str else selector,
        component_only=component_only,
        zero_active=zero_active,
        evidence=evidence,
    )
    for index, (
        reason,
        workflow,
        selector,
        component_only,
        zero_active,
        evidence,
    ) in enumerate(_REASON_SPECS, start=1)
)

_next_index = len(REASON_SCENARIOS) + 1
MATERIAL_SCENARIOS = tuple(
    _row(
        _next_index + index,
        branch=f"MATERIAL_{kind.value}",
        workflow=(
            WorkflowState.ORDER_CHANGED_HUMAN_REVIEW
            if kind.is_material
            else WorkflowState.CREDIT_CONFIRMED_TARGET_REP
        ),
        reasons=(
            SalesCreditReason.MATERIAL_CHANGE_DETECTED
            if kind.is_material
            else SalesCreditReason.ROUTINE_LIFECYCLE_CHANGE_NONMATERIAL,
        ),
        selectors=(MODEL_MATERIAL, EVALUATOR_MATERIAL if kind.is_material else EVALUATOR_VALUE),
        material=kind,
    )
    for index, kind in enumerate(MaterialChangeKind)
)

_next_index += len(MATERIAL_SCENARIOS)
HUMAN_OUTCOME_SCENARIOS = tuple(
    _row(
        _next_index + index,
        branch=f"HUMAN_OUTCOME_{outcome.value}",
        workflow=WorkflowState.CLOSED,
        reasons=(),
        selectors=(MODEL_HUMAN_OUTCOME,),
        component_only=True,
        outcome=outcome,
    )
    for index, outcome in enumerate(HumanOutcomeType)
)

_next_index += len(HUMAN_OUTCOME_SCENARIOS)
WORKFLOW_BOUNDARY_SCENARIOS = (
    _row(
        _next_index,
        branch="INITIAL_AWAITING_SOURCE_REVIEW",
        workflow=WorkflowState.AWAITING_SOURCE_REVIEW,
        reasons=(),
        selectors=(ACCUMULATOR_INITIAL,),
        component_only=True,
    ),
    _row(
        _next_index + 1,
        branch="TERMINAL_CLOSED",
        workflow=WorkflowState.CLOSED,
        reasons=(),
        selectors=(ACCUMULATOR_CLOSED,),
        component_only=True,
    ),
)

SCENARIO_CATALOG = (
    REASON_SCENARIOS
    + MATERIAL_SCENARIOS
    + HUMAN_OUTCOME_SCENARIOS
    + WORKFLOW_BOUNDARY_SCENARIOS
)


def _acceptance(
    identifier: str,
    family: AcceptanceFamily,
    requirement: str,
    *selectors: str,
) -> AcceptanceCoverageRow:
    return AcceptanceCoverageRow(
        identifier,
        family,
        requirement,
        tuple(sorted(set(selectors))),
    )


ACCEPTANCE_COVERAGE = (
    _acceptance(
        "SCHEMA_FIELDS",
        AcceptanceFamily.SCHEMA_AND_NORMALIZATION,
        "Required, optional, and conditional fields.",
        _selector(
            "models",
            "ClosedModelShapeTests",
            "test_required_constructor_fields_are_exact",
        ),
    ),
    _acceptance(
        "SCHEMA_TIMESTAMPS",
        AcceptanceFamily.SCHEMA_AND_NORMALIZATION,
        "Timezone-aware timestamps and timestamp precision.",
        _selector(
            "models",
            "InteractionRecordTests",
            "test_review_dates_are_exact_new_york_anchor_plus_fourteen",
        ),
    ),
    _acceptance(
        "SCHEMA_MONEY",
        AcceptanceFamily.SCHEMA_AND_NORMALIZATION,
        "Exact nonnegative decimal money and integer quantity.",
        _selector(
            "models",
            "LineItemSnapshotTests",
            "test_quantity_money_and_tuple_shapes_are_strict",
        ),
    ),
    _acceptance(
        "SCHEMA_EMAIL",
        AcceptanceFamily.SCHEMA_AND_NORMALIZATION,
        "ASCII-four-trim and ASCII-lowercase email normalization.",
        _selector(
            "discovery",
            "ContactNormalizationTests",
            "test_email_uses_ascii_four_trim_and_ascii_lowercase",
        ),
    ),
    _acceptance(
        "SCHEMA_PHONE",
        AcceptanceFamily.SCHEMA_AND_NORMALIZATION,
        "Fictional phone normalization without guessed digits.",
        _selector(
            "discovery",
            "ContactNormalizationTests",
            "test_phone_accepts_only_firewall_formats_and_never_guesses_area_code",
        ),
    ),
    _acceptance(
        "SCHEMA_MALFORMED_PHONE",
        AcceptanceFamily.SCHEMA_AND_NORMALIZATION,
        "Malformed or non-fictional phones fail closed.",
        _selector(
            "discovery",
            "ContactNormalizationTests",
            "test_malformed_or_nonfictional_phone_rejects_without_correction",
        ),
    ),
    _acceptance(
        "WINDOW_INCLUSIVE",
        AcceptanceFamily.WINDOWS,
        "Interaction date plus fourteen full calendar days is inclusive.",
        _selector(
            "windows",
            "CalendarWindowTests",
            "test_timezone_and_ordinary_inclusive_fourteen_day_window",
        ),
    ),
    _acceptance(
        "WINDOW_DST",
        AcceptanceFamily.WINDOWS,
        "Spring and fall DST do not alter local-date windows.",
        _selector(
            "windows",
            "CalendarWindowTests",
            "test_spring_and_fall_dst_do_not_change_calendar_day_count",
        ),
    ),
    _acceptance(
        "WINDOW_TIMING",
        AcceptanceFamily.WINDOWS,
        "Same-day uncertain ordering never proves qualification.",
        WINDOW_UNCERTAIN,
    ),
    _acceptance(
        "WINDOW_REPLACEMENT",
        AcceptanceFamily.WINDOWS,
        "Cancellation opens an independently extended replacement window.",
        _selector(
            "windows",
            "CalendarWindowTests",
            "test_cancellation_has_its_own_window_that_may_extend_review",
        ),
    ),
    _acceptance(
        "WINDOW_RECHECK",
        AcceptanceFamily.WINDOWS,
        "Automatic recheck is limited to once per New York local date.",
        WINDOW_AUTOMATIC,
    ),
    _acceptance(
        "WINDOW_FORCE",
        AcceptanceFamily.WINDOWS,
        "Selected force recheck bypasses only the daily throttle and is audited.",
        WINDOW_FORCE,
    ),
    _acceptance(
        "DISCOVERY_BOTH_IDS",
        AcceptanceFamily.DISCOVERY,
        "Every valid email and phone is searched.",
        _selector(
            "discovery",
            "DiscoveryCombinationTests",
            "test_both_identifiers_are_mandatory_and_union_deduplicates_order_ids",
        ),
    ),
    _acceptance(
        "DISCOVERY_COMPLETE",
        AcceptanceFamily.DISCOVERY,
        "Complete native result sets are combined without early exit.",
        _selector(
            "discovery",
            "DiscoveryCombinationTests",
            "test_observed_candidates_survive_incomplete_enumeration_for_evaluation",
        ),
    ),
    _acceptance(
        "DISCOVERY_DEDUPE",
        AcceptanceFamily.DISCOVERY,
        "Canonical Order Number deduplication is deterministic.",
        _selector(
            "discovery",
            "DiscoveryCombinationTests",
            "test_result_order_does_not_change_deterministic_union",
        ),
    ),
    _acceptance(
        "DISCOVERY_INCOMPLETE",
        AcceptanceFamily.DISCOVERY,
        "Incomplete enumeration cannot conclude no-order.",
        DISCOVERY_INCOMPLETE,
        NO_ORDER_INCOMPLETE_APPLIED,
    ),
    _acceptance(
        "DISCOVERY_EMPTY",
        AcceptanceFamily.DISCOVERY,
        "Complete empty results distinguish active and closed windows.",
        DISCOVERY_NO_ORDER,
        COORDINATOR_NO_ORDER_ACTIVE,
    ),
    _acceptance(
        "RULE_REP",
        AcceptanceFamily.RULES,
        "Target, web, other, missing, and unrecognized rep branches.",
        EVALUATOR_REP,
    ),
    _acceptance(
        "RULE_EVIDENCE",
        AcceptanceFamily.RULES,
        "Every contact-evidence classification and timing branch.",
        EVALUATOR_EVIDENCE,
    ),
    _acceptance(
        "RULE_CANCELLATION",
        AcceptanceFamily.RULES,
        "Canceled orders and open or expired replacement windows.",
        EVALUATOR_REPLACEMENT_WINDOW,
    ),
    _acceptance(
        "RULE_CONTINUITY",
        AcceptanceFamily.RULES,
        "Exact ES, exact MFG/OE, nonexact, and absent product continuity.",
        EVALUATOR_REPLACEMENT_PRODUCT,
    ),
    _acceptance(
        "RULE_CUSTOMER",
        AcceptanceFamily.RULES,
        "Customer mismatch and unproved continuity fail closed.",
        EVALUATOR_REPLACEMENT_CUSTOMER,
    ),
    _acceptance(
        "RULE_MATERIAL",
        AcceptanceFamily.RULES,
        "All material and routine lifecycle change kinds.",
        EVALUATOR_MATERIAL,
        EVALUATOR_VALUE,
    ),
    _acceptance(
        "RULE_VALUE",
        AcceptanceFamily.RULES,
        "Placed value is exact and current value is never substituted.",
        EVALUATOR_VALUE,
    ),
    _acceptance(
        "CASE_ATTACH",
        AcceptanceFamily.CASE_IDENTITY,
        "Multiple interactions attach to one logical order case.",
        _selector(
            "accumulator",
            "ReplayAndAtomicityTests",
            "test_distinct_commands_union_facts_without_double_counting",
        ),
        COORDINATOR_CASE_ATTACH,
        COORDINATOR_MIXED_ATOMIC,
    ),
    _acceptance(
        "CASE_REPLAY",
        AcceptanceFamily.CASE_IDENTITY,
        "Exact replay returns the original logical result.",
        ACCUMULATOR_INITIAL,
    ),
    _acceptance(
        "CASE_CONFLICT",
        AcceptanceFamily.CASE_IDENTITY,
        "Conflicting replay and digest collision fail safely.",
        _selector(
            "accumulator",
            "ReplayAndAtomicityTests",
            "test_same_command_different_material_is_a_conflict",
        ),
        _selector(
            "accumulator",
            "ReplayAndAtomicityTests",
            "test_equal_digest_different_bytes_is_a_collision_not_replay",
        ),
    ),
    _acceptance(
        "CASE_OUTCOME",
        AcceptanceFamily.CASE_IDENTITY,
        "Human outcome is separate and replay-safe.",
        ACCUMULATOR_CLOSED,
    ),
    _acceptance(
        "RETENTION_MINIMIZE",
        AcceptanceFamily.RETENTION,
        "Closure atomically writes minimized governed metadata.",
        _selector(
            "retention",
            "ClosureProjectionTests",
            "test_human_closure_preserves_only_minimized_governed_metadata",
        ),
        _selector(
            "accumulator",
            "OutcomeClosureAndPurgeTests",
            "test_closure_is_atomic_minimization_and_exact_replay",
        ),
    ),
    _acceptance(
        "RETENTION_SYSTEM",
        AcceptanceFamily.RETENTION,
        "Terminal system closure fabricates no human outcome.",
        _selector(
            "retention",
            "ClosureProjectionTests",
            "test_terminal_system_closure_requires_no_fabricated_human_outcome",
        ),
    ),
    _acceptance(
        "RETENTION_BOUNDARY",
        AcceptanceFamily.RETENTION,
        "Purge begins at exactly ninety elapsed days.",
        _selector(
            "retention",
            "PurgeBoundaryTests",
            "test_exact_elapsed_ninety_day_nanosecond_boundary",
        ),
    ),
    _acceptance(
        "RETENTION_IDEMPOTENT",
        AcceptanceFamily.RETENTION,
        "Purge is idempotent and removes identity-bearing receipts.",
        _selector(
            "accumulator",
            "OutcomeClosureAndPurgeTests",
            "test_purge_boundary_is_idempotent_and_deletes_identity_receipts",
        ),
    ),
    _acceptance(
        "SAFETY_NO_UI",
        AcceptanceFamily.SAFETY,
        "No portal, write API, dashboard, or extension exists in Milestone 2.",
        "tests.test_milestone_boundary.MilestoneBoundaryTests."
        "test_milestone_three_and_user_interface_modules_are_absent",
    ),
    _acceptance(
        "SAFETY_NO_NETWORK",
        AcceptanceFamily.SAFETY,
        "Package code imports no network client.",
        "tests.test_milestone_boundary.MilestoneBoundaryTests."
        "test_package_has_no_network_client_import",
    ),
    _acceptance(
        "SAFETY_COUNTERS",
        AcceptanceFamily.SAFETY,
        "All nine safety counters remain zero.",
        "tests.test_foundation_audit.FoundationAuditTests."
        "test_all_safety_counters_are_zero",
    ),
    _acceptance(
        "SAFETY_PAYLOAD",
        AcceptanceFamily.SAFETY,
        "Malformed or private payloads fail closed without echo.",
        _selector(
            "evaluator",
            "ExplanationAndSafetyTests",
            "test_wrong_shapes_and_private_payloads_reject_without_echo",
        ),
    ),
    _acceptance(
        "METRICS_DEFINITIONS",
        AcceptanceFamily.METRICS,
        "Pure aggregate definitions, rates, latency, and agreement are exact.",
        _selector(
            "metrics",
            "AggregateMetricsTests",
            "test_aggregate_definitions_median_nearest_rank_and_agreement_are_exact",
        ),
    ),
    _acceptance(
        "METRICS_REPLAY",
        AcceptanceFamily.METRICS,
        "Exact duplicate observations are idempotent and conflicts fail.",
        _selector(
            "metrics",
            "AggregateMetricsTests",
            "test_exact_duplicate_is_idempotent_and_conflicting_duplicate_fails",
        ),
    ),
    _acceptance(
        "METRICS_PRIVACY",
        AcceptanceFamily.METRICS,
        "Aggregate output contains no identity or contact detail.",
        _selector(
            "metrics",
            "AggregateMetricsTests",
            "test_input_shape_is_closed_and_output_contains_no_identity_or_contact_detail",
        ),
    ),
)


def _validate_catalog() -> None:
    scenario_ids = tuple(row.scenario_id.value for row in SCENARIO_CATALOG)
    if len(scenario_ids) != len(set(scenario_ids)):
        raise TraceabilityValidationError("duplicate_scenario_id")
    owned_reasons = tuple(row.expected_reasons[0] for row in REASON_SCENARIOS)
    if owned_reasons != tuple(SalesCreditReason):
        raise TraceabilityValidationError("reason_inventory")
    if {row.expected_workflow for row in SCENARIO_CATALOG} != set(WorkflowState):
        raise TraceabilityValidationError("workflow_inventory")
    if {
        row.evidence_branch for row in SCENARIO_CATALOG if row.evidence_branch is not None
    } != set(EvidenceClassification):
        raise TraceabilityValidationError("evidence_inventory")
    if {
        row.material_branch for row in SCENARIO_CATALOG if row.material_branch is not None
    } != set(MaterialChangeKind):
        raise TraceabilityValidationError("material_inventory")
    if {
        row.human_outcome for row in SCENARIO_CATALOG if row.human_outcome is not None
    } != set(HumanOutcomeType):
        raise TraceabilityValidationError("human_outcome_inventory")
    acceptance_ids = tuple(row.acceptance_id for row in ACCEPTANCE_COVERAGE)
    if len(acceptance_ids) != len(set(acceptance_ids)):
        raise TraceabilityValidationError("duplicate_acceptance_id")
    if {row.family for row in ACCEPTANCE_COVERAGE} != set(AcceptanceFamily):
        raise TraceabilityValidationError("acceptance_family_inventory")


_validate_catalog()


def reason_owner(reason: SalesCreditReason) -> ScenarioCatalogRow:
    """Return the one canonical reason-ownership row without accepting aliases."""

    if type(reason) is not SalesCreditReason:
        raise TraceabilityValidationError("reason_owner_type")
    return REASON_SCENARIOS[tuple(SalesCreditReason).index(reason)]


def collected_test_selectors() -> tuple[str, ...]:
    """Return every referenced selector once in deterministic lexical order."""

    return tuple(
        sorted(
            {
                selector
                for row in (*SCENARIO_CATALOG, *ACCEPTANCE_COVERAGE)
                for selector in row.test_selectors
            }
        )
    )


def _joined(values: tuple[object, ...]) -> str:
    return ", ".join(item.value for item in values) if values else "-"  # type: ignore[attr-defined]


def render_traceability_markdown() -> str:
    """Render the checked-in traceability document from the immutable catalog."""

    lines = [
        "# Milestone 2 Sales Credit traceability",
        "",
        "Generated from `sales_credit.traceability`; manual edits are rejected by tests.",
        "",
        f"- Catalog version: `{TRACEABILITY_VERSION}`",
        f"- Synthetic scenarios: {len(SCENARIO_CATALOG)}",
        f"- Owned decision reasons: {len(REASON_SCENARIOS)}",
        f"- Workflow states: {len(set(row.expected_workflow for row in SCENARIO_CATALOG))}",
        f"- Collected test selectors: {len(collected_test_selectors())}",
        "- Safety expectation: all nine counters are zero for every scenario",
        "",
        "## Reason ownership",
        "",
        "| Scenario | Branch | Workflow | Human review | Reasons | Effects | Test selectors |",
        "|---|---|---|---:|---|---|---|",
    ]
    for row in REASON_SCENARIOS:
        lines.append(
            f"| `{row.scenario_id.value}` | `{row.expected_branch}` | "
            f"`{row.expected_workflow.value}` | `{str(row.human_review_required).lower()}` | "
            f"`{_joined(row.expected_reasons)}` | `{_joined(row.persistence_effects)}` | "
            f"`{', '.join(row.test_selectors)}` |"
        )
    lines.extend(
        (
            "",
            "## Closed branch inventories",
            "",
            "| Scenario | Evidence | Material | Human outcome | Workflow | Test selectors |",
            "|---|---|---|---|---|---|",
        )
    )
    branch_rows = tuple(
        row
        for row in SCENARIO_CATALOG
        if any(
            value is not None
            for value in (row.evidence_branch, row.material_branch, row.human_outcome)
        )
        or row in WORKFLOW_BOUNDARY_SCENARIOS
    )
    for row in branch_rows:
        evidence = "-" if row.evidence_branch is None else row.evidence_branch.value
        material = "-" if row.material_branch is None else row.material_branch.value
        outcome = "-" if row.human_outcome is None else row.human_outcome.value
        lines.append(
            f"| `{row.scenario_id.value}` | `{evidence}` | `{material}` | `{outcome}` | "
            f"`{row.expected_workflow.value}` | `{', '.join(row.test_selectors)}` |"
        )
    lines.extend(
        (
            "",
            "## Workflow ownership",
            "",
            "| Workflow | Owning synthetic scenario |",
            "|---|---|",
        )
    )
    for workflow in WorkflowState:
        owner = next(row for row in SCENARIO_CATALOG if row.expected_workflow is workflow)
        lines.append(f"| `{workflow.value}` | `{owner.scenario_id.value}` |")
    lines.extend(
        (
            "",
            "## Acceptance coverage",
            "",
            "| ID | Family | Requirement | Test selectors |",
            "|---|---|---|---|",
        )
    )
    for row in ACCEPTANCE_COVERAGE:
        lines.append(
            f"| `{row.acceptance_id}` | `{row.family.value}` | {row.requirement} | "
            f"`{', '.join(row.test_selectors)}` |"
        )
    lines.extend(("", "## Safety counters", "", "| Counter | Expected |", "|---|---:|"))
    for name, value in ZERO_SAFETY_COUNTERS:
        lines.append(f"| `{name}` | {value} |")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "ACCEPTANCE_COVERAGE",
    "AcceptanceCoverageRow",
    "AcceptanceFamily",
    "REASON_SCENARIOS",
    "SAFETY_COUNTER_NAMES",
    "SCENARIO_CATALOG",
    "ScenarioCatalogRow",
    "TRACEABILITY_VERSION",
    "TraceabilityValidationError",
    "WORKFLOW_BOUNDARY_SCENARIOS",
    "ZERO_SAFETY_COUNTERS",
    "collected_test_selectors",
    "reason_owner",
    "render_traceability_markdown",
]
