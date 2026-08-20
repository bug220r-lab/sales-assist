from __future__ import annotations

import hashlib
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from synthetic_sales_assist.domain.identities import (
    EvaluationId,
    CustomerId,
    EvidenceId,
    InteractionId,
    OrderId,
    RepId,
    RunId,
    SkuId,
    SnapshotId,
)
from synthetic_sales_assist.domain.canonical import canonical_json_bytes, domain_hash
from synthetic_sales_assist.domain.records import VersionBinding
from synthetic_sales_assist.domain.numeric import CURRENCY_REGISTRY_VERSION, Money, Quantity
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.sales_credit.accumulator import (
    CaseAccumulatorError,
    CaseMutation,
    ClosureResult,
    InMemoryCaseAccumulator as _InMemoryCaseAccumulator,
    InMemorySalesCreditState,
    OutcomeResult,
    SearchEvaluationBatch,
)
from synthetic_sales_assist.sales_credit.discovery import (
    IdentifierSearchResult,
    InMemoryNoOrderStateLedger,
    InMemorySearchRunAuthority,
    NoOrderLedgerError,
    OrderSearchRun,
    SearchCompleteness,
    SearchRunAuthorityError,
    SearchRunPartitionKind,
    SelectorOwnedCandidateEvaluation,
    plan_discovery,
)
from synthetic_sales_assist.sales_credit.evaluator import (
    KNOWN_OTHER_REP_CATALOG,
    evidence_identifier_binding,
    evaluate_sales_credit,
)
from synthetic_sales_assist.sales_credit.models import (
    AttributionClassification,
    AttributionDecision,
    CustomerContinuityStatus,
    EvidenceDirection,
    EvidenceEvent,
    EvidenceIdentifierKind,
    EvidenceSourceType,
    EvidenceTimingRelation,
    HumanOutcomeType,
    InteractionRecord,
    LineItemSnapshot,
    ManagerOutcome,
    MaterialChange,
    MaterialChangeKind,
    NotesScanStatus,
    OrderLifecycleStatus,
    OrderSnapshot,
    OrderValueStatus,
    ProductContinuityStatus,
    ReplacementCandidateInput,
    ReplacementDecision,
    ReplacementStatus,
    SnapshotStatus,
    SalesCreditEffect,
    SalesCreditEvaluation,
    SalesCreditFact,
    SalesCreditReason,
    SalesCreditRule,
    SalesCreditValidation,
    SearchTriggerType,
    TimestampPrecision,
    ValueDecision,
    WorkflowState,
    order_provenance_binding,
)


def ts(value: str) -> CanonicalTimestamp:
    return CanonicalTimestamp(value)


class _TestAccumulator:
    """Compatibility facade routing discovery through the supported coordinator."""

    def __init__(
        self,
        *,
        digest_function: object | None = None,
        search_run_authority: InMemorySearchRunAuthority | None = None,
    ) -> None:
        kwargs: dict[str, object] = {}
        if digest_function is not None:
            kwargs["digest_function"] = digest_function
        if search_run_authority is not None:
            kwargs["search_run_authority"] = search_run_authority
        self.state = InMemorySalesCreditState(**kwargs)  # type: ignore[arg-type]

    @property
    def case_accumulator(self) -> _InMemoryCaseAccumulator:
        return self.state.case_accumulator

    def apply_mutation(self, value: CaseMutation):  # type: ignore[no-untyped-def]
        if value.discovery_run is None:
            return self.case_accumulator.apply_mutation(value)
        if value.discovery_run.result.order_ids != (value.order_id,):
            return self.case_accumulator.apply_mutation(value)
        batch = SearchEvaluationBatch(value.discovery_run, (value,))
        coordinated = self.state.apply_discovery_batch(
            batch,
            candidate_evaluations=selector_evaluations(batch),
        )
        return coordinated.case_results[0]

    def apply_discovery_batch(
        self,
        batch: SearchEvaluationBatch,
    ) -> tuple[object, ...]:
        return self.state.apply_discovery_batch(
            batch,
            candidate_evaluations=selector_evaluations(batch),
        ).case_results

    def __getattr__(self, name: str) -> object:
        return getattr(self.case_accumulator, name)


def InMemoryCaseAccumulator(
    *,
    digest_function: object | None = None,
    search_run_authority: InMemorySearchRunAuthority | None = None,
) -> _TestAccumulator:
    """Build one explicitly isolated test composition."""
    return _TestAccumulator(
        digest_function=digest_function,
        search_run_authority=search_run_authority,
    )


def interaction(
    suffix: str = "001",
    *,
    recorded_at: str = "2026-08-01T14:00:00Z",
    email_local: str | None = None,
) -> InteractionRecord:
    observed = ts(recorded_at)
    local = email_local or f"case{suffix.lower()}"
    return InteractionRecord(
        interaction_id=InteractionId(f"SYN-INTERACTION-{suffix}"),
        source_ref=EvidenceId(f"SYN-EVIDENCE-SOURCE-{suffix}"),
        recorded_at=observed,
        timestamp_precision=TimestampPrecision.EXACT,
        review_window_start=date(2026, 8, 1),
        review_window_end=date(2026, 8, 15),
        workflow_state=WorkflowState.AWAITING_SOURCE_REVIEW,
        provenance=VersionBinding(
            "sales_credit_interaction_source",
            "sales-credit-interaction-source/v1",
        ),
        email=f"{local}@example.test",
        phone="212-555-0100",
        active_notes="synthetic: accumulator fixture",
    )


def mutation(
    command_suffix: str = "COMMAND-001",
    *,
    order_suffix: str = "001",
    occurred_at: str = "2026-08-01T14:00:00Z",
    interactions: tuple[InteractionRecord, ...] | None = None,
) -> CaseMutation:
    return CaseMutation(
        command_id=EvidenceId(f"SYN-EVIDENCE-{command_suffix}"),
        order_id=OrderId(f"SYN-ORDER-{order_suffix}"),
        occurred_at=ts(occurred_at),
        interactions=(interaction(),) if interactions is None else interactions,
        active_note="synthetic: active case fixture",
    )


def usd(amount: str = "100.00") -> Money:
    return Money(Decimal(amount), "USD", CURRENCY_REGISTRY_VERSION, 2)


def search_run(
    *,
    suffix: str,
    interactions: tuple[InteractionRecord, ...],
    order_ids: tuple[OrderId, ...],
    trigger: SearchTriggerType = SearchTriggerType.NORMAL,
    started_at: str = "2026-08-01T14:05:00Z",
    completed_at: str = "2026-08-01T14:06:00Z",
) -> OrderSearchRun:
    plan = plan_discovery(
        email_values=tuple(
            item.email for item in interactions if item.email is not None
        ),
        phone_values=tuple(
            item.phone for item in interactions if item.phone is not None
        ),
    )
    return OrderSearchRun(
        run_id=RunId(f"SYN-RUN-{suffix}"),
        trigger=trigger,
        interactions=interactions,
        native_result_sets=tuple(
            IdentifierSearchResult(
                identifier=item,
                completeness=SearchCompleteness.COMPLETE,
                order_ids=order_ids,
            )
            for item in plan.identifiers
        ),
        adapter=VersionBinding(
            "sales_credit_search_adapter",
            "sales-credit-search-adapter/v1",
        ),
        started_at=ts(started_at),
        completed_at=ts(completed_at),
    )


def two_candidate_discovery_batch() -> SearchEvaluationBatch:
    interactions = (
        replace(interaction("101", email_local="batcha"), phone=None),
        replace(interaction("102", email_local="batchb"), phone=None),
    )
    order_ids = (OrderId("SYN-ORDER-101"), OrderId("SYN-ORDER-102"))
    plan = plan_discovery(
        email_values=tuple(item.email for item in interactions),
    )
    native_results = tuple(
        IdentifierSearchResult(
            identifier=identifier,
            completeness=SearchCompleteness.COMPLETE,
            order_ids=(order_ids[index],),
        )
        for index, identifier in enumerate(plan.identifiers)
    )
    run = OrderSearchRun(
        run_id=RunId("SYN-RUN-DISCOVERY-BATCH-001"),
        trigger=SearchTriggerType.NORMAL,
        interactions=interactions,
        native_result_sets=native_results,
        adapter=VersionBinding(
            "sales_credit_search_adapter",
            "sales-credit-search-adapter/v1",
        ),
        started_at=ts("2026-08-01T15:35:00Z"),
        completed_at=ts("2026-08-01T15:40:00Z"),
    )
    base = evaluated_mutation("BATCH-BASE")
    mutations: list[CaseMutation] = []
    for index, (order_id, interaction_value) in enumerate(
        zip(order_ids, interactions, strict=True),
        start=1,
    ):
        source_ref = EvidenceId(f"SYN-EVIDENCE-BATCH-SOURCE-{index:03d}")
        snapshot = replace(
            base.snapshots[0],
            snapshot_id=SnapshotId(f"SYN-SNAPSHOT-BATCH-{index:03d}"),
            order_id=order_id,
            source_ref=source_ref,
            provenance=order_provenance_binding(
                source_ref=source_ref,
                captured_at=base.snapshots[0].captured_at,
                parser=base.snapshots[0].parser,
            ),
        )
        evaluation_value = evaluate_sales_credit(
            evaluation_id=EvaluationId(f"SYN-EVALUATION-BATCH-{index:03d}"),
            expected_order_id=order_id,
            snapshot=snapshot,
            evaluated_at=ts("2026-08-01T16:00:00Z"),
            known_other_reps=KNOWN_OTHER_REP_CATALOG,
            interactions=(interaction_value,),
        )
        mutations.append(
            CaseMutation(
                command_id=EvidenceId(f"SYN-EVIDENCE-BATCH-COMMAND-{index:03d}"),
                order_id=order_id,
                occurred_at=ts("2026-08-01T16:00:00Z"),
                interactions=(interaction_value,),
                snapshots=(snapshot,),
                evaluation=evaluation_value,
                discovery_run=run,
            )
        )
    return SearchEvaluationBatch(run, tuple(mutations))


def selector_evaluations(
    batch: SearchEvaluationBatch,
) -> tuple[SelectorOwnedCandidateEvaluation, ...]:
    """Build exact independent order/selector evaluations for a test batch."""

    mutation_by_order = {item.order_id: item for item in batch.mutations}
    result_by_identifier = {
        item.identifier: item for item in batch.run.native_result_sets
    }
    pairs: list[tuple[OrderId, InteractionRecord]] = []
    for interaction_value in batch.run.interactions:
        plan = plan_discovery(
            email_values=(
                ()
                if interaction_value.email is None
                else (interaction_value.email,)
            ),
            phone_values=(
                ()
                if interaction_value.phone is None
                else (interaction_value.phone,)
            ),
        )
        owned_orders = {
            order_id
            for identifier in plan.identifiers
            for order_id in result_by_identifier[identifier].order_ids
        }
        pairs.extend(
            (order_id, interaction_value)
            for order_id in sorted(owned_orders, key=lambda item: item.value)
        )
    pairs.sort(key=lambda item: (item[0].value, item[1].interaction_id.value))
    results: list[SelectorOwnedCandidateEvaluation] = []
    for index, (order_id, interaction_value) in enumerate(pairs, start=1):
        mutation_value = mutation_by_order[order_id]
        claimed = mutation_value.evaluation
        if claimed is None:
            raise AssertionError("test batch mutation must be evaluated")
        snapshot_value = next(
            item
            for item in mutation_value.snapshots
            if item.snapshot_id == claimed.snapshot_id
        )
        evaluated_at = mutation_value.occurred_at
        evaluation_value = evaluate_sales_credit(
            evaluation_id=EvaluationId(
                f"SYN-EVALUATION-SELECTOR-{index:06d}"
            ),
            expected_order_id=order_id,
            snapshot=snapshot_value,
            evaluated_at=evaluated_at,
            known_other_reps=KNOWN_OTHER_REP_CATALOG,
            interactions=(interaction_value,),
        )
        results.append(
            SelectorOwnedCandidateEvaluation(
                interaction_id=interaction_value.interaction_id,
                snapshot=snapshot_value,
                evaluation=evaluation_value,
                evaluated_at=evaluated_at,
            )
        )
    return tuple(results)


def positive_recheck_batch(
    *,
    interaction_value: InteractionRecord,
    order_suffix: str,
    run_suffix: str,
    started_at: str,
    completed_at: str,
    occurred_at: str,
) -> tuple[
    SearchEvaluationBatch,
    tuple[SelectorOwnedCandidateEvaluation, ...],
]:
    """Build one exact positive automatic recheck for a retained no-order root."""

    base = evaluated_mutation(f"{run_suffix}-BASE")
    order_id = OrderId(f"SYN-ORDER-{order_suffix}")
    source_ref = EvidenceId(f"SYN-EVIDENCE-{run_suffix}-SOURCE")
    snapshot_value = replace(
        base.snapshots[0],
        snapshot_id=SnapshotId(f"SYN-SNAPSHOT-{run_suffix}"),
        order_id=order_id,
        source_ref=source_ref,
        provenance=order_provenance_binding(
            source_ref=source_ref,
            captured_at=base.snapshots[0].captured_at,
            parser=base.snapshots[0].parser,
        ),
    )
    run = search_run(
        suffix=run_suffix,
        interactions=(interaction_value,),
        order_ids=(order_id,),
        trigger=SearchTriggerType.AUTOMATIC_RECHECK,
        started_at=started_at,
        completed_at=completed_at,
    )
    evaluated_at = ts(occurred_at)
    evaluation_value = evaluate_sales_credit(
        evaluation_id=EvaluationId(f"SYN-EVALUATION-{run_suffix}-CASE"),
        expected_order_id=order_id,
        snapshot=snapshot_value,
        evaluated_at=evaluated_at,
        known_other_reps=KNOWN_OTHER_REP_CATALOG,
        interactions=(interaction_value,),
    )
    mutation_value = CaseMutation(
        command_id=EvidenceId(f"SYN-EVIDENCE-{run_suffix}-COMMAND"),
        order_id=order_id,
        occurred_at=evaluated_at,
        interactions=(interaction_value,),
        snapshots=(snapshot_value,),
        evaluation=evaluation_value,
        discovery_run=run,
    )
    batch = SearchEvaluationBatch(run, (mutation_value,))
    return batch, selector_evaluations(batch)


def mixed_selector_batch(
    *,
    uncertain_second: bool = False,
    terminal_second: bool = False,
    run_suffix: str = "MIXED-SELECTOR-001",
) -> tuple[
    SearchEvaluationBatch,
    tuple[SelectorOwnedCandidateEvaluation, ...],
]:
    """One favorable selector plus one nonfavorable shared-identifier owner."""

    shared_email = "mixed.selector@example.test"
    first = replace(
        interaction(
            "301",
            recorded_at="2026-08-01T14:00:00Z",
            email_local="mixed.selector",
        ),
        email=shared_email,
        phone=None,
    )
    second = replace(
        interaction(
            "302",
            recorded_at=(
                "2026-08-01T15:00:00Z"
                if uncertain_second
                else "2026-08-01T15:30:00Z"
            ),
            email_local="mixed.selector",
        ),
        email=shared_email,
        phone=None,
        timestamp_precision=(
            TimestampPrecision.HISTORICAL_APPROXIMATION
            if uncertain_second
            else TimestampPrecision.EXACT
        ),
    )
    base = evaluated_mutation(f"{run_suffix}-BASE")
    order_id = base.order_id
    snapshot_value = base.snapshots[0]
    plan = plan_discovery(email_values=(shared_email,))
    run = OrderSearchRun(
        run_id=RunId(f"SYN-RUN-{run_suffix}"),
        trigger=SearchTriggerType.NORMAL,
        interactions=(first, second),
        native_result_sets=(
            IdentifierSearchResult(
                identifier=plan.identifiers[0],
                completeness=SearchCompleteness.COMPLETE,
                order_ids=(order_id,),
            ),
        ),
        adapter=VersionBinding(
            "sales_credit_search_adapter",
            OrderSearchRun.ADAPTER_VERSION,
        ),
        started_at=ts(
            "2026-08-17T16:05:00Z"
            if terminal_second
            else (
                "2026-08-02T16:05:00Z"
                if uncertain_second
                else "2026-08-01T16:05:00Z"
            )
        ),
        completed_at=ts(
            "2026-08-17T16:06:00Z"
            if terminal_second
            else (
                "2026-08-02T16:06:00Z"
                if uncertain_second
                else "2026-08-01T16:06:00Z"
            )
        ),
    )
    occurred_at = ts(
        "2026-08-17T16:10:00Z"
        if terminal_second
        else (
            "2026-08-02T16:10:00Z"
            if uncertain_second
            else "2026-08-01T16:10:00Z"
        )
    )
    mutation_evaluation = evaluate_sales_credit(
        evaluation_id=EvaluationId(
            f"SYN-EVALUATION-{run_suffix}-CASE"
        ),
        expected_order_id=order_id,
        snapshot=snapshot_value,
        evaluated_at=occurred_at,
        known_other_reps=KNOWN_OTHER_REP_CATALOG,
        interactions=(first,),
    )
    mutation_value = CaseMutation(
        command_id=EvidenceId(f"SYN-EVIDENCE-{run_suffix}-COMMAND"),
        order_id=order_id,
        occurred_at=occurred_at,
        interactions=(first,),
        snapshots=(snapshot_value,),
        evaluation=mutation_evaluation,
        discovery_run=run,
    )
    candidates = tuple(
        SelectorOwnedCandidateEvaluation(
            interaction_id=scoped.interaction_id,
            snapshot=snapshot_value,
            evaluated_at=occurred_at,
            evaluation=evaluate_sales_credit(
                evaluation_id=EvaluationId(
                    f"SYN-EVALUATION-{run_suffix}-SELECTOR-{index:03d}"
                ),
                expected_order_id=order_id,
                snapshot=snapshot_value,
                evaluated_at=occurred_at,
                known_other_reps=KNOWN_OTHER_REP_CATALOG,
                interactions=(scoped,),
            ),
        )
        for index, scoped in enumerate(run.interactions, start=1)
    )
    return SearchEvaluationBatch(run, (mutation_value,)), candidates


def evaluated_mutation(
    command_suffix: str = "EVALUATED-COMMAND-001",
    *,
    workflow_rep: str = "target_rep",
    occurred_at: str = "2026-08-01T16:00:00Z",
    canceled: bool = False,
) -> CaseMutation:
    order_id = OrderId("SYN-ORDER-001")
    interaction_value = interaction()
    captured_at = ts("2026-08-01T15:30:00Z")
    parser = VersionBinding("sales_credit_parser", "sales-credit-parser/v1")
    source_ref = EvidenceId("SYN-EVIDENCE-ORDER-SOURCE-001")
    snapshot_value = OrderSnapshot(
        snapshot_id=SnapshotId("SYN-SNAPSHOT-001"),
        order_id=order_id,
        source_ref=source_ref,
        captured_at=captured_at,
        parser=parser,
        extraction_status=SnapshotStatus.VALID,
        lifecycle_status=(
            OrderLifecycleStatus.CANCELED
            if canceled
            else OrderLifecycleStatus.ACTIVE
        ),
        notes_scan_status=NotesScanStatus.COMPLETE,
        placed_at=ts("2026-08-01T15:00:00Z"),
        placed_at_precision=TimestampPrecision.EXACT,
        raw_order_status="canceled" if canceled else "active",
        raw_order_rep=workflow_rep,
        current_value=usd(),
        placed_value=usd(),
        customer_ids=(CustomerId("SYN-CUSTOMER-ACCUMULATOR-001"),),
        lines=(),
        material_changes=(),
        provenance=order_provenance_binding(
            source_ref=source_ref,
            captured_at=captured_at,
            parser=parser,
        ),
        canceled_at=ts("2026-08-01T15:15:00Z") if canceled else None,
    )
    evaluation_value = evaluate_sales_credit(
        evaluation_id=EvaluationId("SYN-EVALUATION-001"),
        expected_order_id=order_id,
        snapshot=snapshot_value,
        evaluated_at=ts(occurred_at),
        known_other_reps=KNOWN_OTHER_REP_CATALOG,
        interactions=(interaction_value,),
    )
    discovery = search_run(
        suffix=f"DISCOVERY-{command_suffix}",
        interactions=(interaction_value,),
        order_ids=(order_id,),
        started_at="2026-08-01T15:35:00Z",
        completed_at="2026-08-01T15:40:00Z",
    )
    return CaseMutation(
        command_id=EvidenceId(f"SYN-EVIDENCE-{command_suffix}"),
        order_id=order_id,
        occurred_at=ts(occurred_at),
        interactions=(interaction_value,),
        snapshots=(snapshot_value,),
        evaluation=evaluation_value,
        discovery_run=discovery,
        active_note="synthetic: evaluated case fixture",
    )


def evaluated_mutation_for_interaction(
    *,
    command_suffix: str,
    interaction_value: InteractionRecord,
) -> CaseMutation:
    value = evaluated_mutation(command_suffix)
    evaluation_value = evaluate_sales_credit(
        evaluation_id=value.evaluation.evaluation_id,  # type: ignore[union-attr]
        expected_order_id=value.order_id,
        snapshot=value.snapshots[0],
        evaluated_at=value.occurred_at,
        known_other_reps=KNOWN_OTHER_REP_CATALOG,
        interactions=(interaction_value,),
    )
    discovery = search_run(
        suffix=f"INTERACTION-PARITY-{command_suffix}",
        interactions=(interaction_value,),
        order_ids=(value.order_id,),
        started_at="2026-08-01T15:35:00Z",
        completed_at="2026-08-01T15:40:00Z",
    )
    return replace(
        value,
        interactions=(interaction_value,),
        evaluation=evaluation_value,
        discovery_run=discovery,
    )


def replacement_evaluated_mutations(
    command_suffix: str = "REPLACEMENT-COMMAND-001",
) -> tuple[CaseMutation, CaseMutation]:
    parent_order = OrderId("SYN-ORDER-001")
    replacement_order = OrderId("SYN-ORDER-002")
    interaction_value = interaction()
    parser = VersionBinding("sales_credit_parser", "sales-credit-parser/v1")
    customer = CustomerId("SYN-CUSTOMER-ACCUMULATOR-001")
    parent_line = LineItemSnapshot.create(
        line_id=EvidenceId("SYN-EVIDENCE-REPLACEMENT-LINE-001"),
        sku_id=SkuId("SYN-SKU-REPLACEMENT-001"),
        quantity=Quantity(1),
        line_value=usd("25.00"),
        raw_es_number="synthetic: ES#000123",
        canonical_es_number="123",
    )
    candidate_line = LineItemSnapshot.create(
        line_id=EvidenceId("SYN-EVIDENCE-REPLACEMENT-LINE-002"),
        sku_id=SkuId("SYN-SKU-REPLACEMENT-002"),
        quantity=Quantity(1),
        line_value=usd("25.00"),
        raw_es_number="synthetic: 123",
        canonical_es_number="123",
    )

    def order_snapshot(
        *,
        suffix: str,
        order_id: OrderId,
        captured_at: CanonicalTimestamp,
        placed_at: CanonicalTimestamp,
        lifecycle: OrderLifecycleStatus,
        line: LineItemSnapshot,
        canceled_at: CanonicalTimestamp | None = None,
    ) -> OrderSnapshot:
        source_ref = EvidenceId(f"SYN-EVIDENCE-REPLACEMENT-SOURCE-{suffix}")
        return OrderSnapshot(
            snapshot_id=SnapshotId(f"SYN-SNAPSHOT-REPLACEMENT-{suffix}"),
            order_id=order_id,
            source_ref=source_ref,
            captured_at=captured_at,
            parser=parser,
            extraction_status=SnapshotStatus.VALID,
            lifecycle_status=lifecycle,
            notes_scan_status=NotesScanStatus.COMPLETE,
            placed_at=placed_at,
            placed_at_precision=TimestampPrecision.EXACT,
            raw_order_status=(
                "canceled"
                if lifecycle is OrderLifecycleStatus.CANCELED
                else "active"
            ),
            raw_order_rep="target_rep",
            current_value=usd(),
            placed_value=usd(),
            customer_ids=(customer,),
            lines=(line,),
            material_changes=(),
            provenance=order_provenance_binding(
                source_ref=source_ref,
                captured_at=captured_at,
                parser=parser,
            ),
            canceled_at=canceled_at,
        )

    parent = order_snapshot(
        suffix="001",
        order_id=parent_order,
        captured_at=ts("2026-08-01T15:30:00Z"),
        placed_at=ts("2026-08-01T15:00:00Z"),
        lifecycle=OrderLifecycleStatus.CANCELED,
        line=parent_line,
        canceled_at=ts("2026-08-01T15:15:00Z"),
    )
    candidate = order_snapshot(
        suffix="002",
        order_id=replacement_order,
        captured_at=ts("2026-08-02T15:30:00Z"),
        placed_at=ts("2026-08-02T15:00:00Z"),
        lifecycle=OrderLifecycleStatus.ACTIVE,
        line=candidate_line,
    )
    parent_evaluated_at = ts("2026-08-01T16:00:00Z")
    parent_evaluation = evaluate_sales_credit(
        evaluation_id=EvaluationId("SYN-EVALUATION-REPLACEMENT-PARENT-001"),
        expected_order_id=parent_order,
        snapshot=parent,
        evaluated_at=parent_evaluated_at,
        known_other_reps=KNOWN_OTHER_REP_CATALOG,
        interactions=(interaction_value,),
    )
    parent_discovery = search_run(
        suffix="DISCOVERY-REPLACEMENT-PARENT-001",
        interactions=(interaction_value,),
        order_ids=(parent_order,),
        started_at="2026-08-01T15:35:00Z",
        completed_at="2026-08-01T15:40:00Z",
    )
    parent_command = CaseMutation(
        command_id=EvidenceId("SYN-EVIDENCE-REPLACEMENT-PARENT-COMMAND-001"),
        order_id=parent_order,
        occurred_at=parent_evaluated_at,
        interactions=(interaction_value,),
        snapshots=(parent,),
        evaluation=parent_evaluation,
        discovery_run=parent_discovery,
        active_note="synthetic: replacement parent fixture",
    )
    occurred_at = ts("2026-08-02T16:00:00Z")
    replacement_run = search_run(
        suffix="REPLACEMENT-CHECK-001",
        interactions=(interaction_value,),
        order_ids=(replacement_order,),
        trigger=SearchTriggerType.REPLACEMENT_CHECK,
        started_at="2026-08-02T15:20:00Z",
        completed_at="2026-08-02T15:21:00Z",
    )
    candidate_input = ReplacementCandidateInput(
        snapshot=candidate,
        line_universe_complete=True,
    )
    evaluation_value = evaluate_sales_credit(
        evaluation_id=EvaluationId("SYN-EVALUATION-REPLACEMENT-001"),
        expected_order_id=parent_order,
        snapshot=parent,
        evaluated_at=occurred_at,
        known_other_reps=KNOWN_OTHER_REP_CATALOG,
        interactions=(interaction_value,),
        replacement_run=replacement_run,
        replacement_candidates=(candidate_input,),
    )
    replacement_command = CaseMutation(
        command_id=EvidenceId(f"SYN-EVIDENCE-{command_suffix}"),
        order_id=parent_order,
        occurred_at=occurred_at,
        interactions=(interaction_value,),
        snapshots=(),
        evaluation=evaluation_value,
        replacement_run=replacement_run,
        replacement_candidates=(candidate_input,),
        active_note="synthetic: replacement evaluation fixture",
    )
    return parent_command, replacement_command


def manager_outcome(
    suffix: str = "OUTCOME-001",
    *,
    decided_at: str = "2026-08-02T14:00:00Z",
    recorded_at: str = "2026-08-02T14:01:00Z",
    outcome: HumanOutcomeType = HumanOutcomeType.DENIED,
) -> ManagerOutcome:
    return ManagerOutcome(
        occurrence_id=EvidenceId(f"SYN-EVIDENCE-{suffix}"),
        outcome=outcome,
        decided_at=ts(decided_at),
        actor=RepId("SYN-REP-MANAGER-001"),
        recorded_at=ts(recorded_at),
        approved_amount=None,
        controlled_reason=SalesCreditReason.AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW,
        active_note="synthetic: reviewed outcome",
    )


def contact_evidence(*, interaction_suffix: str = "ORPHAN") -> EvidenceEvent:
    identifier_ref = domain_hash(
        EvidenceEvent.IDENTIFIER_REF_DOMAIN,
        canonical_json_bytes(
            {"kind": "EMAIL", "reference": "SYN-EVIDENCE-IDENTIFIER-001"},
            expected_members={"kind", "reference"},
        ),
    )
    return EvidenceEvent(
        evidence_id=EvidenceId("SYN-EVIDENCE-CONTACT-001"),
        order_id=OrderId("SYN-ORDER-001"),
        interaction_id=InteractionId(f"SYN-INTERACTION-{interaction_suffix}"),
        source_type=EvidenceSourceType.SYNTHETIC_CONVERSATION,
        source_ref=EvidenceId("SYN-EVIDENCE-CONVERSATION-SOURCE-001"),
        occurred_at=ts("2026-08-01T13:00:00Z"),
        timestamp_precision=TimestampPrecision.EXACT,
        direction=EvidenceDirection.TWO_WAY,
        target_rep_participated=True,
        connected=True,
        two_way=True,
        identifier_kind=EvidenceIdentifierKind.EMAIL,
        matched_identifier_ref=identifier_ref,
        timing=EvidenceTimingRelation.PRE_ORDER,
    )


def evaluation(*, snapshot_suffix: str = "ORPHAN") -> SalesCreditEvaluation:
    return SalesCreditEvaluation(
        evaluation_id=EvaluationId("SYN-EVALUATION-001"),
        order_id=OrderId("SYN-ORDER-001"),
        snapshot_id=SnapshotId(f"SYN-SNAPSHOT-{snapshot_suffix}"),
        workflow_state=WorkflowState.MANUAL_REVIEW_REQUIRED,
        attribution=AttributionDecision(
            AttributionClassification.UNKNOWN,
            False,
        ),
        value=ValueDecision(
            OrderValueStatus.UNKNOWN,
            None,
            None,
            (),
        ),
        replacement=ReplacementDecision(
            ReplacementStatus.NOT_APPLICABLE,
            CustomerContinuityStatus.UNKNOWN,
            ProductContinuityStatus.UNKNOWN,
        ),
        reasons=(SalesCreditReason.REP_MISSING,),
        human_review_required=True,
        supplied_facts=(SalesCreditFact.ORDER_REP, SalesCreditFact.SNAPSHOT),
        validations=(SalesCreditValidation.SNAPSHOT_ACCEPTED,),
        rules_evaluated=(
            SalesCreditRule.AMBIGUITY_ROUTING,
            SalesCreditRule.ORDER_REP_ATTRIBUTION,
            SalesCreditRule.SNAPSHOT_VALIDATION,
        ),
        rules_fired=(
            SalesCreditRule.AMBIGUITY_ROUTING,
            SalesCreditRule.ORDER_REP_ATTRIBUTION,
        ),
        persistence_effects=(
            SalesCreditEffect.HUMAN_REVIEW_REQUIRED,
            SalesCreditEffect.NO_PERSISTENCE_MILESTONE_2,
        ),
    )


class CaseMutationContractTests(unittest.TestCase):
    def test_mutation_is_strict_immutable_and_redacted(self) -> None:
        value = mutation()
        self.assertNotIn("example.test", repr(value))
        self.assertNotIn("SYN-ORDER", repr(value))
        with self.assertRaises(FrozenInstanceError):
            value.active_note = None  # type: ignore[misc]
        with self.assertRaisesRegex(CaseAccumulatorError, "mutation_interactions"):
            CaseMutation(
                command_id=value.command_id,
                order_id=value.order_id,
                occurred_at=value.occurred_at,
                interactions=list(value.interactions),  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(CaseAccumulatorError, "mutation_empty"):
            CaseMutation(
                command_id=value.command_id,
                order_id=value.order_id,
                occurred_at=value.occurred_at,
            )

    def test_mutation_rejects_unsorted_duplicates_and_wrong_order_material(self) -> None:
        later = interaction("002")
        earlier = interaction("001")
        with self.assertRaisesRegex(CaseAccumulatorError, "mutation_interactions"):
            mutation(interactions=(later, earlier))
        with self.assertRaisesRegex(CaseAccumulatorError, "mutation_interactions"):
            mutation(interactions=(earlier, earlier))

    def test_replacement_candidate_is_the_only_role_tagged_cross_order_snapshot(self) -> None:
        _, value = replacement_evaluated_mutations()
        self.assertIs(
            value.evaluation.workflow_state,
            WorkflowState.POSSIBLE_REPLACEMENT_HUMAN_REVIEW,
        )
        candidate = value.replacement_candidates[0].snapshot
        self.assertEqual(
            candidate.order_id,
            value.evaluation.replacement.candidate_results[0].order_id,
        )

        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "mutation_replacement_parity",
        ):
            replace(
                value,
                replacement_candidates=(),
            )
        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "mutation_replacement_parity",
        ):
            replace(
                value,
                replacement_candidates=(
                    replace(
                        value.replacement_candidates[0],
                        snapshot=replace(candidate, order_id=OrderId("SYN-ORDER-003")),
                    ),
                ),
            )
        with self.assertRaisesRegex(CaseAccumulatorError, "mutation_snapshot_order"):
            replace(
                value,
                snapshots=(
                    replace(candidate, order_id=OrderId("SYN-ORDER-003")),
                ),
            )
        self.assertFalse(hasattr(value, "replacement_parent"))

    def test_result_wrappers_are_closed_immutable_values(self) -> None:
        store = InMemoryCaseAccumulator()
        result = store.apply_mutation(mutation())
        with self.assertRaises(FrozenInstanceError):
            result.replayed = True  # type: ignore[misc]
        with self.assertRaises(CaseAccumulatorError):
            type(result)(result.state, 1)
        with self.assertRaises(CaseAccumulatorError):
            OutcomeResult("not-a-state", 1)  # type: ignore[arg-type]
        with self.assertRaises(CaseAccumulatorError):
            ClosureResult("not-a-projection", "not-a-digest", 1)  # type: ignore[arg-type]


class ReplayAndAtomicityTests(unittest.TestCase):
    def test_exact_replay_returns_the_original_logical_result_without_duplication(self) -> None:
        store = InMemoryCaseAccumulator()
        command = mutation()
        first = store.apply_mutation(command)
        replay = store.apply_mutation(command)

        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        self.assertIs(first.state, replay.state)
        self.assertFalse(hasattr(first, "command_sha256"))
        active = store.get_active_case(command.order_id)
        self.assertIsNotNone(active)
        self.assertEqual(active.interaction_ids, (interaction().interaction_id,))
        self.assertEqual(store.active_case_count, 1)
        self.assertEqual(store.closed_case_count, 0)

    def test_replacement_candidate_command_is_accepted_replayed_and_conflict_safe(self) -> None:
        store = InMemoryCaseAccumulator()
        parent_command, command = replacement_evaluated_mutations()
        store.apply_mutation(parent_command)
        first = store.apply_mutation(command)
        replay = store.apply_mutation(command)
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        self.assertEqual(first.state, replay.state)
        parent_snapshot = parent_command.snapshots[0]
        candidate = command.replacement_candidates[0].snapshot
        active_parent = store.get_active_case(command.order_id)
        self.assertIsNotNone(active_parent)
        self.assertIn(parent_snapshot.snapshot_id, active_parent.snapshot_ids)
        self.assertNotIn(candidate.snapshot_id, active_parent.snapshot_ids)
        replacement_order = candidate.order_id
        self.assertIsNotNone(replacement_order)
        linked = store.get_active_case(replacement_order)
        self.assertIsNotNone(linked)
        self.assertEqual(linked.replacement_parent, command.order_id)
        self.assertEqual(linked.snapshot_ids, (candidate.snapshot_id,))
        owners = sum(
            candidate.snapshot_id in case.snapshot_ids
            for case in (active_parent, linked)
        )
        self.assertEqual(owners, 1)
        self.assertIs(linked.workflow_state, WorkflowState.AWAITING_SOURCE_REVIEW)
        self.assertEqual(store.active_case_count, 2)

        with self.assertRaisesRegex(CaseAccumulatorError, "command_material_conflict"):
            store.apply_mutation(
                replace(command, active_note="synthetic: conflicting replacement command")
            )
        self.assertEqual(store.get_active_case(command.order_id), active_parent)
        self.assertEqual(store.get_active_case(replacement_order), linked)

    def test_relevant_candidate_already_closed_is_not_reopened_or_duplicated(self) -> None:
        store = InMemoryCaseAccumulator()
        parent_command, replacement_command = replacement_evaluated_mutations(
            "CLOSED-CANDIDATE-REPLACEMENT-001"
        )
        candidate = replacement_command.replacement_candidates[0].snapshot
        candidate_order = candidate.order_id
        self.assertIsNotNone(candidate_order)
        candidate_interactions = replacement_command.interactions
        candidate_evaluated_at = ts("2026-08-02T15:45:00Z")
        candidate_evaluation = evaluate_sales_credit(
            evaluation_id=EvaluationId("SYN-EVALUATION-CLOSED-CANDIDATE-001"),
            expected_order_id=candidate_order,
            snapshot=candidate,
            evaluated_at=candidate_evaluated_at,
            known_other_reps=KNOWN_OTHER_REP_CATALOG,
            interactions=candidate_interactions,
        )
        candidate_run = search_run(
            suffix="CLOSED-CANDIDATE-DISCOVERY-001",
            interactions=candidate_interactions,
            order_ids=(candidate_order,),
            started_at="2026-08-02T15:35:00Z",
            completed_at="2026-08-02T15:40:00Z",
        )
        candidate_command = CaseMutation(
            command_id=EvidenceId("SYN-EVIDENCE-CLOSED-CANDIDATE-COMMAND-001"),
            order_id=candidate_order,
            occurred_at=candidate_evaluated_at,
            interactions=candidate_interactions,
            snapshots=(candidate,),
            evaluation=candidate_evaluation,
            discovery_run=candidate_run,
        )
        store.apply_mutation(candidate_command)
        closed_candidate = store.close_and_minimize(
            command_id=EvidenceId("SYN-EVIDENCE-CLOSED-CANDIDATE-CLOSE-001"),
            order_id=candidate_order,
            closed_at=ts("2026-08-02T15:50:00Z"),
            reasons=candidate_evaluation.reasons,
        ).projection

        store.apply_mutation(parent_command)
        parent = store.apply_mutation(replacement_command).state
        self.assertIs(
            parent.workflow_state,
            WorkflowState.POSSIBLE_REPLACEMENT_HUMAN_REVIEW,
        )
        self.assertEqual(
            store.get_closed_projection(candidate_order),
            closed_candidate,
        )
        self.assertIsNone(store.get_active_case(candidate_order))
        self.assertEqual(store.active_case_count, 1)

    def test_purge_severs_active_child_link_at_the_exact_parent_retention_boundary(
        self,
    ) -> None:
        authority = InMemorySearchRunAuthority()
        store = InMemoryCaseAccumulator(search_run_authority=authority)
        parent_command, command = replacement_evaluated_mutations()
        store.apply_mutation(parent_command)
        accepted = store.apply_mutation(command)
        store.apply_manager_outcome(
            command_id=EvidenceId("SYN-EVIDENCE-REPLACEMENT-OUTCOME-001"),
            order_id=command.order_id,
            outcome=manager_outcome(
                "REPLACEMENT-OUTCOME-001",
                decided_at="2026-08-02T17:00:00Z",
                recorded_at="2026-08-02T17:01:00Z",
            ),
        )
        closed = store.close_and_minimize(
            command_id=EvidenceId("SYN-EVIDENCE-REPLACEMENT-CLOSE-001"),
            order_id=command.order_id,
            closed_at=ts("2026-08-02T18:00:00Z"),
            reasons=command.evaluation.reasons,  # type: ignore[union-attr]
        )

        replacement_order = command.replacement_candidates[0].snapshot.order_id
        child = store.get_active_case(replacement_order)
        self.assertIsNotNone(child)
        self.assertEqual(child.replacement_parent, command.order_id)
        retained_replay = store.apply_mutation(command)
        self.assertIsInstance(retained_replay, type(accepted))
        self.assertTrue(retained_replay.replayed)
        self.assertIs(retained_replay.state, accepted.state)
        self.assertEqual(len(authority.retained_canonical_material), 1)
        self.assertEqual(
            store.purge(now=ts("2026-10-31T17:59:59.999999999Z")),
            0,
        )
        retained_child = store.get_active_case(replacement_order)
        self.assertIsNotNone(retained_child)
        self.assertEqual(retained_child.replacement_parent, command.order_id)

        self.assertEqual(store.purge(now=ts("2026-10-31T18:00:00Z")), 1)
        self.assertIsNone(store.get_closed_projection(command.order_id))
        child = store.get_active_case(replacement_order)
        self.assertIsNotNone(child)
        self.assertIsNone(child.replacement_parent)
        self.assertEqual(authority.retained_canonical_material, ())
        self.assertEqual(authority.retired_run_ids, ())

    def test_distinct_commands_union_facts_without_double_counting(self) -> None:
        store = InMemoryCaseAccumulator()
        first_interaction = interaction("001")
        second_interaction = interaction("002", email_local="case2")
        store.apply_mutation(mutation(interactions=(first_interaction,)))
        result = store.apply_mutation(
            mutation(
                "COMMAND-002",
                occurred_at="2026-08-01T15:00:00Z",
                interactions=(first_interaction, second_interaction),
            )
        )
        active = store.get_active_case(result_order := OrderId("SYN-ORDER-001"))
        self.assertIsNotNone(active)
        self.assertEqual(
            tuple(item.value for item in active.interaction_ids),
            ("SYN-INTERACTION-001", "SYN-INTERACTION-002"),
        )
        self.assertEqual(result.state.workflow_state, active.workflow_state)
        self.assertEqual(result_order, active.order_id)
        self.assertEqual(store.active_case_count, 1)

    def test_clean_later_snapshot_cannot_erase_unresolved_material_review(self) -> None:
        store = InMemoryCaseAccumulator()
        changed = evaluated_mutation("STICKY-MATERIAL-001")
        changed_snapshot = replace(
            changed.snapshots[0],
            material_changes=(
                MaterialChange(
                    EvidenceId("SYN-EVIDENCE-STICKY-CHANGE-001"),
                    MaterialChangeKind.PRICE_ADJUSTMENT,
                    True,
                ),
            ),
        )
        changed_evaluation = evaluate_sales_credit(
            evaluation_id=EvaluationId("SYN-EVALUATION-STICKY-001"),
            expected_order_id=changed.order_id,
            snapshot=changed_snapshot,
            evaluated_at=changed.occurred_at,
            known_other_reps=KNOWN_OTHER_REP_CATALOG,
            interactions=changed.interactions,
        )
        first = store.apply_mutation(
            replace(
                changed,
                snapshots=(changed_snapshot,),
                evaluation=changed_evaluation,
            )
        )
        self.assertIs(
            first.state.workflow_state,
            WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
        )

        clean_base = evaluated_mutation(
            "STICKY-MATERIAL-002",
            occurred_at="2026-08-02T17:00:00Z",
        )
        clean_snapshot = replace(
            clean_base.snapshots[0],
            snapshot_id=SnapshotId("SYN-SNAPSHOT-STICKY-002"),
        )
        clean_evaluation = evaluate_sales_credit(
            evaluation_id=EvaluationId("SYN-EVALUATION-STICKY-002"),
            expected_order_id=clean_base.order_id,
            snapshot=clean_snapshot,
            evaluated_at=clean_base.occurred_at,
            known_other_reps=KNOWN_OTHER_REP_CATALOG,
            interactions=clean_base.interactions,
            prior_snapshots=(changed_snapshot,),
        )
        clean = replace(
            clean_base,
            snapshots=(clean_snapshot,),
            evaluation=clean_evaluation,
        )
        retained = store.apply_mutation(clean)
        self.assertIs(
            retained.state.workflow_state,
            WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
        )
        self.assertIs(
            retained.state.order_value_status,
            OrderValueStatus.CHANGED_REVIEW,
        )
        active = store.get_active_case(clean.order_id)
        self.assertIsNotNone(active)
        self.assertEqual(len(active.snapshot_ids), 2)

    def test_same_command_different_material_is_a_conflict(self) -> None:
        store = InMemoryCaseAccumulator()
        command = mutation()
        store.apply_mutation(command)
        changed = replace(command, active_note="synthetic: materially changed command")
        with self.assertRaisesRegex(CaseAccumulatorError, "command_material_conflict"):
            store.apply_mutation(changed)
        prior = store.get_active_case(command.order_id)
        store.apply_mutation(command)
        self.assertIs(store.get_active_case(command.order_id), prior)

    def test_equal_digest_different_bytes_is_a_collision_not_replay(self) -> None:
        fixed_digest = "a" * 64
        store = InMemoryCaseAccumulator(digest_function=lambda _: fixed_digest)
        command = mutation()
        store.apply_mutation(command)
        with self.assertRaisesRegex(CaseAccumulatorError, "command_material_conflict"):
            store.apply_mutation(
                replace(command, active_note="synthetic: collision candidate")
            )
        self.assertEqual(store.active_case_count, 1)

    def test_digest_failure_and_invalid_digest_leave_no_case(self) -> None:
        def fail(_: bytes) -> str:
            raise RuntimeError("synthetic failure")

        for digest_function, code in (
            (fail, "digest_failure"),
            (lambda _: "A" * 64, "digest_invalid"),
        ):
            with self.subTest(code=code):
                store = InMemoryCaseAccumulator(digest_function=digest_function)
                with self.assertRaisesRegex(CaseAccumulatorError, code):
                    store.apply_mutation(mutation())
                self.assertEqual(store.active_case_count, 0)

    def test_object_conflict_rolls_back_and_failed_command_can_be_corrected(self) -> None:
        store = InMemoryCaseAccumulator()
        original = interaction("001")
        store.apply_mutation(mutation(interactions=(original,)))
        conflicting = interaction("001", email_local="different")
        failed = mutation(
            "COMMAND-002",
            occurred_at="2026-08-01T15:00:00Z",
            interactions=(conflicting,),
        )
        prior = store.get_active_case(OrderId("SYN-ORDER-001"))
        with self.assertRaisesRegex(CaseAccumulatorError, "interaction_conflict"):
            store.apply_mutation(failed)
        self.assertIs(store.get_active_case(OrderId("SYN-ORDER-001")), prior)

        corrected = replace(failed, interactions=(interaction("002", email_local="second"),))
        accepted = store.apply_mutation(corrected)
        self.assertFalse(accepted.replayed)
        active = store.get_active_case(corrected.order_id)
        self.assertIsNotNone(active)
        self.assertEqual(len(active.interaction_ids), 2)

    def test_one_global_command_identity_cannot_cross_orders_or_operation_kinds(self) -> None:
        store = InMemoryCaseAccumulator()
        first = mutation()
        store.apply_mutation(first)
        with self.assertRaisesRegex(CaseAccumulatorError, "command_material_conflict"):
            store.apply_mutation(
                mutation(
                    "COMMAND-001",
                    order_suffix="002",
                    interactions=(interaction("002", email_local="second"),),
                )
            )
        with self.assertRaisesRegex(CaseAccumulatorError, "command_material_conflict"):
            store.apply_manager_outcome(
                command_id=first.command_id,
                order_id=first.order_id,
                outcome=manager_outcome(),
            )

    def test_concurrent_exact_command_has_one_winner_and_only_one_case(self) -> None:
        store = InMemoryCaseAccumulator()
        command = mutation()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = tuple(pool.map(lambda _: store.apply_mutation(command), range(16)))
        self.assertEqual(sum(not item.replayed for item in results), 1)
        self.assertEqual(sum(item.replayed for item in results), 15)
        self.assertEqual({item.state for item in results}, {results[0].state})
        self.assertEqual(store.active_case_count, 1)
        retained = store.get_active_case(command.order_id)
        self.assertIsNotNone(retained)
        self.assertEqual(len(retained.interaction_ids), 1)  # type: ignore[union-attr]

    def test_mutations_may_not_regress_case_time(self) -> None:
        store = InMemoryCaseAccumulator()
        store.apply_mutation(mutation(occurred_at="2026-08-01T10:00:00Z"))
        store.apply_mutation(
            mutation(
                "COMMAND-002",
                occurred_at="2026-08-01T12:00:00Z",
                interactions=(interaction("002", email_local="second"),),
            )
        )
        prior = store.get_active_case(OrderId("SYN-ORDER-001"))
        with self.assertRaises(CaseAccumulatorError):
            store.apply_mutation(
                mutation(
                    "COMMAND-003",
                    occurred_at="2026-08-01T11:00:00Z",
                    interactions=(interaction("003", email_local="third"),),
                )
            )
        self.assertIs(store.get_active_case(OrderId("SYN-ORDER-001")), prior)

    def test_evidence_must_resolve_to_an_attached_interaction(self) -> None:
        store = InMemoryCaseAccumulator()
        orphan = CaseMutation(
            command_id=EvidenceId("SYN-EVIDENCE-COMMAND-ORPHAN-EVIDENCE"),
            order_id=OrderId("SYN-ORDER-001"),
            occurred_at=ts("2026-08-01T14:00:00Z"),
            evidence=(contact_evidence(),),
        )
        with self.assertRaisesRegex(CaseAccumulatorError, "evidence_interaction"):
            store.apply_mutation(orphan)
        self.assertEqual(store.active_case_count, 0)

    def test_evaluation_must_resolve_to_an_attached_snapshot(self) -> None:
        store = InMemoryCaseAccumulator()
        seed = evaluated_mutation("ORPHAN-EVALUATION-SEED")
        store.apply_mutation(seed)
        orphan = CaseMutation(
            command_id=EvidenceId("SYN-EVIDENCE-COMMAND-ORPHAN-EVALUATION"),
            order_id=OrderId("SYN-ORDER-001"),
            occurred_at=ts("2026-08-01T16:01:00Z"),
            evaluation=replace(
                evaluation(),
                evaluation_id=EvaluationId("SYN-EVALUATION-ORPHAN-001"),
            ),
        )
        with self.assertRaisesRegex(CaseAccumulatorError, "evaluation_snapshot_missing"):
            store.apply_mutation(orphan)
        self.assertEqual(store.active_case_count, 1)

    def test_claimed_evaluation_is_recomputed_from_retained_facts(self) -> None:
        store = InMemoryCaseAccumulator()
        command = evaluated_mutation("RECOMPUTE-COMMAND-001")
        claimed = command.evaluation
        self.assertIsNotNone(claimed)
        forged = replace(
            claimed,
            reasons=tuple(
                sorted(
                    (
                        *claimed.reasons,
                        SalesCreditReason.ROUTINE_LIFECYCLE_CHANGE_NONMATERIAL,
                    ),
                    key=lambda item: item.value,
                )
            ),
        )
        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "evaluation_material_mismatch",
        ):
            store.apply_mutation(replace(command, evaluation=forged))
        self.assertEqual(store.active_case_count, 0)

        accepted = store.apply_mutation(command)
        self.assertFalse(accepted.replayed)
        active = store.get_active_case(command.order_id)
        self.assertIsNotNone(active)
        self.assertEqual(active.evaluation_ids, (claimed.evaluation_id,))

    def test_new_classification_facts_require_a_cumulative_evaluation(self) -> None:
        store = InMemoryCaseAccumulator()
        initial = evaluated_mutation("FACT-GUARD-INITIAL-001")
        store.apply_mutation(initial)
        prior_case = store.get_active_case(initial.order_id)
        prior_receipt_ids = tuple(store.case_accumulator._receipts)
        prior_snapshot = initial.snapshots[0]
        captured_at = ts("2026-08-02T15:30:00Z")
        source_ref = EvidenceId("SYN-EVIDENCE-FACT-GUARD-SOURCE-002")
        changed_snapshot = replace(
            prior_snapshot,
            snapshot_id=SnapshotId("SYN-SNAPSHOT-FACT-GUARD-002"),
            source_ref=source_ref,
            captured_at=captured_at,
            current_value=usd("125.00"),
            material_changes=(
                MaterialChange(
                    EvidenceId("SYN-EVIDENCE-FACT-GUARD-CHANGE-002"),
                    MaterialChangeKind.PRICE_ADJUSTMENT,
                    True,
                ),
            ),
            provenance=order_provenance_binding(
                source_ref=source_ref,
                captured_at=captured_at,
                parser=prior_snapshot.parser,
            ),
        )
        unevaluated = CaseMutation(
            command_id=EvidenceId("SYN-EVIDENCE-FACT-GUARD-UNEVALUATED-002"),
            order_id=initial.order_id,
            occurred_at=ts("2026-08-02T16:00:00Z"),
            snapshots=(changed_snapshot,),
        )
        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "evaluation_required_for_facts",
        ):
            store.apply_mutation(unevaluated)
        self.assertIs(store.get_active_case(initial.order_id), prior_case)
        self.assertEqual(tuple(store.case_accumulator._receipts), prior_receipt_ids)

        evaluated_at = ts("2026-08-02T16:00:00Z")
        cumulative = evaluate_sales_credit(
            evaluation_id=EvaluationId("SYN-EVALUATION-FACT-GUARD-002"),
            expected_order_id=initial.order_id,
            snapshot=changed_snapshot,
            evaluated_at=evaluated_at,
            known_other_reps=KNOWN_OTHER_REP_CATALOG,
            interactions=initial.interactions,
            prior_snapshots=(prior_snapshot,),
        )
        accepted = store.apply_mutation(
            replace(
                unevaluated,
                command_id=EvidenceId(
                    "SYN-EVIDENCE-FACT-GUARD-EVALUATED-002"
                ),
                evaluation=cumulative,
            )
        )
        self.assertIs(
            accepted.state.workflow_state,
            WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
        )


class DiscoveryBatchAuthorityTests(unittest.TestCase):
    def test_legacy_discovery_entrypoints_require_the_atomic_coordinator(
        self,
    ) -> None:
        authority = InMemorySearchRunAuthority()
        direct = _InMemoryCaseAccumulator(search_run_authority=authority)
        batch = two_candidate_discovery_batch()
        partial = SearchEvaluationBatch(batch.run, batch.mutations[:1])
        shared_batch, _ = mixed_selector_batch(
            terminal_second=True,
            run_suffix="LEGACY-SHARED-NONQUALIFYING-001",
        )
        for call in (
            lambda: direct.apply_mutation(batch.mutations[0]),
            lambda: direct.apply_discovery_batch(batch),
            lambda: direct.apply_discovery_batch(partial),
            lambda: direct.apply_mutation(shared_batch.mutations[0]),
            lambda: direct.apply_discovery_batch(shared_batch),
        ):
            with self.subTest(call=call):
                with self.assertRaisesRegex(
                    CaseAccumulatorError,
                    "discovery_coordinator_required",
                ):
                    call()
        self.assertEqual(direct.active_case_count, 0)
        self.assertEqual(authority.retained_canonical_material, ())
        self.assertEqual(authority.sealed_run_ids, ())

    def test_state_is_the_only_supported_no_order_entrypoint(self) -> None:
        state = InMemorySalesCreditState()
        run = search_run(
            suffix="STATE-NO-ORDER-001",
            interactions=(interaction("311", email_local="state.no.order"),),
            order_ids=(),
        )
        with self.assertRaisesRegex(
            NoOrderLedgerError,
            "no_order_coordinator_required",
        ):
            state.no_order_ledger.apply_run(run)
        first = state.apply_no_order_run(run)
        replay = state.apply_no_order_run(run)
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        self.assertEqual(len(first.active_no_order), 1)
        self.assertEqual(state.case_accumulator.active_case_count, 0)
        self.assertEqual(
            state.search_run_authority.retained_canonical_material,
            (),
        )
        self.assertEqual(
            state.search_run_authority.sealed_run_ids,
            (run.run_id,),
        )
        sealed = state.search_run_authority._sealed[run.run_id.value]
        self.assertEqual(
            tuple(partition.kind for partition in sealed.partitions),
            (SearchRunPartitionKind.NO_ORDER_ACTIVE,),
        )

    def test_all_positive_receipt_survives_ledger_purge_for_exact_replay(
        self,
    ) -> None:
        state = InMemorySalesCreditState()
        batch = two_candidate_discovery_batch()
        first = state.apply_discovery_batch(
            batch,
            candidate_evaluations=selector_evaluations(batch),
        )
        self.assertTrue(first.case_results)
        self.assertEqual(
            state.no_order_ledger.purge_closed(
                now=ts("2027-01-01T00:00:00Z")
            ),
            0,
        )

        replay = state.apply_discovery_batch(
            batch,
            candidate_evaluations=selector_evaluations(batch),
        )
        self.assertTrue(all(item.replayed for item in replay.case_results))
        self.assertTrue(replay.no_order_result.replayed)
        sealed = state.search_run_authority._sealed[batch.run.run_id.value]
        self.assertEqual(
            tuple(partition.kind for partition in sealed.partitions),
            (SearchRunPartitionKind.POSITIVE_CASE_ACTIVE,),
        )

    def test_zero_case_mixed_negative_run_has_no_orphan_case_partition(
        self,
    ) -> None:
        state = InMemorySalesCreditState()
        active = replace(
            interaction("611", email_local="zero.case.active"),
            phone=None,
            recorded_at=ts("2026-08-17T14:00:00Z"),
            review_window_start=date(2026, 8, 17),
            review_window_end=date(2026, 8, 31),
        )
        terminal = replace(
            interaction("612", email_local="zero.case.terminal"),
            phone=None,
        )
        initial = search_run(
            suffix="ZERO-CASE-MIXED-001",
            interactions=(active, terminal),
            order_ids=(),
            started_at="2026-08-17T16:05:00Z",
            completed_at="2026-08-17T16:06:00Z",
        )
        result = state.apply_no_order_run(initial)
        self.assertEqual(len(result.active_no_order), 1)
        self.assertEqual(len(result.terminal_no_order), 1)
        self.assertEqual(state.case_accumulator.active_case_count, 0)
        sealed = state.search_run_authority._sealed[initial.run_id.value]
        self.assertEqual(
            tuple(partition.kind for partition in sealed.partitions),
            (SearchRunPartitionKind.NO_ORDER_ACTIVE,),
        )

        retained = state.no_order_ledger.retained_interactions
        self.assertEqual(len(retained), 1)
        final_run = search_run(
            suffix="ZERO-CASE-MIXED-002",
            interactions=retained,
            order_ids=(),
            trigger=SearchTriggerType.AUTOMATIC_RECHECK,
            started_at="2026-09-01T16:05:00Z",
            completed_at="2026-09-01T16:06:00Z",
        )
        final = state.apply_no_order_run(final_run)
        self.assertEqual(len(final.terminal_no_order), 1)
        self.assertEqual(state.case_accumulator.active_case_count, 0)
        for authority_entry in state.search_run_authority._sealed.values():
            self.assertNotIn(
                SearchRunPartitionKind.POSITIVE_CASE_ACTIVE,
                tuple(
                    partition.kind
                    for partition in authority_entry.partitions
                ),
            )

        self.assertEqual(
            state.no_order_ledger.purge_closed(
                now=ts("2026-11-15T16:06:00Z")
            ),
            1,
        )
        self.assertTrue(state.search_run_authority.sealed_run_ids)
        self.assertEqual(
            state.no_order_ledger.purge_closed(
                now=ts("2026-11-30T16:06:00Z")
            ),
            1,
        )
        self.assertEqual(state.search_run_authority.sealed_run_ids, ())

    def test_staggered_positive_roots_split_and_purge_independently(
        self,
    ) -> None:
        state = InMemorySalesCreditState()
        roots = (
            replace(
                interaction("621", email_local="transfer.root.a"),
                phone=None,
            ),
            replace(
                interaction("622", email_local="transfer.root.b"),
                phone=None,
            ),
        )
        source_run = search_run(
            suffix="TRANSFER-SOURCE-001",
            interactions=roots,
            order_ids=(),
            started_at="2026-08-01T16:05:00Z",
            completed_at="2026-08-01T16:06:00Z",
        )
        state.apply_no_order_run(source_run)
        retained_a, retained_b = state.no_order_ledger.retained_interactions

        batch_x, candidates_x = positive_recheck_batch(
            interaction_value=retained_a,
            order_suffix="TRANSFER-X-001",
            run_suffix="TRANSFER-POSITIVE-X-001",
            started_at="2026-08-02T16:05:00Z",
            completed_at="2026-08-02T16:06:00Z",
            occurred_at="2026-08-02T16:10:00Z",
        )
        state.apply_discovery_batch(
            batch_x,
            candidate_evaluations=candidates_x,
        )
        self.assertEqual(
            state.no_order_ledger.retained_interactions,
            (retained_b,),
        )

        batch_y, candidates_y = positive_recheck_batch(
            interaction_value=retained_b,
            order_suffix="TRANSFER-Y-001",
            run_suffix="TRANSFER-POSITIVE-Y-001",
            started_at="2026-08-02T17:05:00Z",
            completed_at="2026-08-02T17:06:00Z",
            occurred_at="2026-08-02T17:10:00Z",
        )
        state.apply_discovery_batch(
            batch_y,
            candidate_evaluations=candidates_y,
        )
        source_receipt = state.case_accumulator._run_receipts[
            source_run.run_id.value
        ]
        self.assertEqual(len(source_receipt.transferred_partitions), 2)
        self.assertEqual(
            {
                item.active_order_ids
                for item in source_receipt.transferred_partitions
            },
            {
                (batch_x.mutations[0].order_id.value,),
                (batch_y.mutations[0].order_id.value,),
            },
        )
        self.assertTrue(state.apply_no_order_run(source_run).replayed)
        self.assertTrue(
            state.apply_discovery_batch(
                batch_x,
                candidate_evaluations=candidates_x,
            ).case_results[0].replayed
        )
        self.assertTrue(
            state.apply_discovery_batch(
                batch_y,
                candidate_evaluations=candidates_y,
            ).case_results[0].replayed
        )

        mutation_x = batch_x.mutations[0]
        mutation_y = batch_y.mutations[0]
        state.case_accumulator.close_and_minimize(
            command_id=EvidenceId("SYN-EVIDENCE-TRANSFER-CLOSE-Y-001"),
            order_id=mutation_y.order_id,
            closed_at=ts("2026-08-04T18:00:00Z"),
            reasons=mutation_y.evaluation.reasons,
        )
        state.case_accumulator.close_and_minimize(
            command_id=EvidenceId("SYN-EVIDENCE-TRANSFER-CLOSE-X-001"),
            order_id=mutation_x.order_id,
            closed_at=ts("2026-08-03T18:00:00Z"),
            reasons=mutation_x.evaluation.reasons,
        )
        self.assertIn(
            source_run.run_id,
            state.search_run_authority.sealed_run_ids,
        )
        self.assertTrue(state.apply_no_order_run(source_run).replayed)

        self.assertEqual(
            state.case_accumulator.purge(
                now=ts("2026-11-01T18:00:00Z")
            ),
            1,
        )
        self.assertIn(
            source_run.run_id,
            state.search_run_authority.sealed_run_ids,
        )
        self.assertEqual(
            state.case_accumulator.purge(
                now=ts("2026-11-02T18:00:00Z")
            ),
            1,
        )
        state.no_order_ledger.purge_closed(
            now=ts("2026-11-02T18:00:00Z")
        )
        self.assertEqual(state.search_run_authority.sealed_run_ids, ())

    def test_positive_transfer_rolls_back_both_ledgers_and_authority(
        self,
    ) -> None:
        state = InMemorySalesCreditState()
        source_run = search_run(
            suffix="TRANSFER-ROLLBACK-SOURCE-001",
            interactions=(
                replace(
                    interaction("631", email_local="transfer.rollback"),
                    phone=None,
                ),
            ),
            order_ids=(),
            started_at="2026-08-01T16:05:00Z",
            completed_at="2026-08-01T16:06:00Z",
        )
        state.apply_no_order_run(source_run)
        retained = state.no_order_ledger.retained_interactions
        source_partitions = state.search_run_authority._sealed[
            source_run.run_id.value
        ].partitions
        batch, candidates = positive_recheck_batch(
            interaction_value=retained[0],
            order_suffix="TRANSFER-ROLLBACK-001",
            run_suffix="TRANSFER-ROLLBACK-POSITIVE-001",
            started_at="2026-08-02T16:05:00Z",
            completed_at="2026-08-02T16:06:00Z",
            occurred_at="2026-08-02T16:10:00Z",
        )

        with patch.object(
            InMemoryNoOrderStateLedger,
            "commit_post_evaluation_stage",
            side_effect=NoOrderLedgerError("synthetic_transfer_failure"),
        ):
            with self.assertRaisesRegex(
                NoOrderLedgerError,
                "synthetic_transfer_failure",
            ):
                state.apply_discovery_batch(
                    batch,
                    candidate_evaluations=candidates,
                )
        self.assertEqual(state.case_accumulator.active_case_count, 0)
        self.assertEqual(
            state.no_order_ledger.retained_interactions,
            retained,
        )
        self.assertEqual(
            state.search_run_authority._sealed[
                source_run.run_id.value
            ].partitions,
            source_partitions,
        )
        self.assertNotIn(
            batch.run.run_id,
            state.search_run_authority.sealed_run_ids,
        )
        self.assertNotIn(
            source_run.run_id.value,
            state.case_accumulator._run_receipts,
        )

        accepted = state.apply_discovery_batch(
            batch,
            candidate_evaluations=candidates,
        )
        self.assertFalse(accepted.case_results[0].replayed)
        self.assertEqual(state.no_order_ledger.retained_interactions, ())

    def test_mixed_positive_and_terminal_effects_commit_atomically(self) -> None:
        batch, candidates = mixed_selector_batch(
            terminal_second=True,
            run_suffix="MIXED-TERMINAL-001",
        )
        state = InMemorySalesCreditState()
        result = state.apply_discovery_batch(
            batch,
            candidate_evaluations=candidates,
        )
        self.assertEqual(len(result.case_results), 1)
        self.assertEqual(len(result.no_order_result.terminal_no_order), 1)
        self.assertEqual(result.no_order_result.active_no_order, ())
        case = state.case_accumulator.get_active_case(
            batch.mutations[0].order_id
        )
        self.assertIsNotNone(case)
        self.assertEqual(
            case.interaction_ids,
            (batch.run.interactions[0].interaction_id,),
        )
        self.assertEqual(state.no_order_ledger.retained_interactions, ())
        self.assertEqual(
            state.search_run_authority.retained_canonical_material,
            (),
        )
        terminal_contact = batch.run.interactions[1].email.encode("ascii")
        for receipt in state.case_accumulator._receipts.values():
            self.assertFalse(hasattr(receipt, "canonical_bytes"))
            self.assertNotIn(terminal_contact, receipt.material_authenticator)
        for receipt in state.case_accumulator._run_receipts.values():
            self.assertFalse(hasattr(receipt, "canonical_bytes"))
            self.assertNotIn(terminal_contact, receipt.binding_authenticator)

    def test_same_order_positive_scope_excludes_preserved_uncertain_owner(
        self,
    ) -> None:
        batch, candidates = mixed_selector_batch(
            uncertain_second=True,
            run_suffix="MIXED-UNCERTAIN-001",
        )
        state = InMemorySalesCreditState()
        result = state.apply_discovery_batch(
            batch,
            candidate_evaluations=candidates,
        )
        case = state.case_accumulator.get_active_case(
            batch.mutations[0].order_id
        )
        self.assertIsNotNone(case)
        self.assertEqual(
            case.interaction_ids,
            (batch.run.interactions[0].interaction_id,),
        )
        self.assertEqual(len(result.no_order_result.manual_review), 1)
        self.assertEqual(
            tuple(
                item.interaction_id
                for item in state.no_order_ledger.retained_interactions
            ),
            (batch.run.interactions[1].interaction_id,),
        )
        self.assertIs(
            state.no_order_ledger.retained_interactions[0].workflow_state,
            WorkflowState.MANUAL_REVIEW_REQUIRED,
        )

    def test_mixed_coordinator_rolls_back_after_case_side_failure(self) -> None:
        batch, candidates = mixed_selector_batch(
            terminal_second=True,
            run_suffix="MIXED-CASE-ROLLBACK-001",
        )
        mutation_value = batch.mutations[0]
        forged = replace(
            mutation_value.evaluation,
            reasons=tuple(
                sorted(
                    {
                        *mutation_value.evaluation.reasons,
                        SalesCreditReason.ROUTINE_LIFECYCLE_CHANGE_NONMATERIAL,
                    },
                    key=lambda item: item.value,
                )
            ),
        )
        crossed = SearchEvaluationBatch(
            batch.run,
            (replace(mutation_value, evaluation=forged),),
        )
        state = InMemorySalesCreditState()
        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "evaluation_material_mismatch",
        ):
            state.apply_discovery_batch(
                crossed,
                candidate_evaluations=candidates,
            )
        self.assertEqual(state.case_accumulator.active_case_count, 0)
        self.assertEqual(state.no_order_ledger.retained_interactions, ())
        self.assertEqual(state.no_order_ledger.closure_receipt_count, 0)
        self.assertEqual(state.search_run_authority.sealed_run_ids, ())
        self.assertEqual(
            state.search_run_authority.retained_canonical_material,
            (),
        )

    def test_mixed_coordinator_rolls_back_after_ledger_side_failure(self) -> None:
        batch, candidates = mixed_selector_batch(
            terminal_second=True,
            run_suffix="MIXED-LEDGER-ROLLBACK-001",
        )
        state = InMemorySalesCreditState()
        with patch.object(
            InMemoryNoOrderStateLedger,
            "commit_post_evaluation_stage",
            side_effect=NoOrderLedgerError("synthetic_commit_failure"),
        ):
            with self.assertRaisesRegex(
                NoOrderLedgerError,
                "synthetic_commit_failure",
            ):
                state.apply_discovery_batch(
                    batch,
                    candidate_evaluations=candidates,
                )
        self.assertEqual(state.case_accumulator.active_case_count, 0)
        self.assertEqual(state.no_order_ledger.retained_interactions, ())
        self.assertEqual(state.no_order_ledger.closure_receipt_count, 0)
        self.assertEqual(state.search_run_authority.sealed_run_ids, ())
        self.assertEqual(
            state.search_run_authority.retained_canonical_material,
            (),
        )

    def test_selector_snapshot_and_mutation_snapshot_must_match_exactly(
        self,
    ) -> None:
        original_batch = SearchEvaluationBatch(
            evaluated_mutation("SNAPSHOT-BINDING-001").discovery_run,
            (evaluated_mutation("SNAPSHOT-BINDING-001"),),
        )
        original = original_batch.mutations[0]
        candidates = selector_evaluations(original_batch)
        for suffix, changed_snapshot in (
            (
                "ID",
                replace(
                    original.snapshots[0],
                    snapshot_id=SnapshotId(
                        "SYN-SNAPSHOT-SNAPSHOT-BINDING-CHANGED"
                    ),
                ),
            ),
            (
                "REP",
                replace(original.snapshots[0], raw_order_rep="unassigned_web"),
            ),
            (
                "VALUE",
                replace(
                    original.snapshots[0],
                    current_value=usd("125.00"),
                    placed_value=usd("125.00"),
                ),
            ),
            (
                "TIMING",
                replace(
                    original.snapshots[0],
                    placed_at=ts("2026-08-01T15:01:00Z"),
                ),
            ),
        ):
            with self.subTest(suffix=suffix):
                authority = InMemorySearchRunAuthority()
                state = InMemorySalesCreditState(
                    search_run_authority=authority
                )
                evaluation_value = evaluate_sales_credit(
                    evaluation_id=EvaluationId(
                        f"SYN-EVALUATION-SNAPSHOT-BINDING-{suffix}"
                    ),
                    expected_order_id=original.order_id,
                    snapshot=changed_snapshot,
                    evaluated_at=original.occurred_at,
                    known_other_reps=KNOWN_OTHER_REP_CATALOG,
                    interactions=original.interactions,
                )
                changed = replace(
                    original,
                    command_id=EvidenceId(
                        f"SYN-EVIDENCE-SNAPSHOT-BINDING-{suffix}"
                    ),
                    snapshots=(changed_snapshot,),
                    evaluation=evaluation_value,
                )
                with self.assertRaisesRegex(
                    CaseAccumulatorError,
                    "search_batch_snapshot_binding",
                ):
                    state.apply_discovery_batch(
                        SearchEvaluationBatch(original_batch.run, (changed,)),
                        candidate_evaluations=candidates,
                    )
                self.assertEqual(state.case_accumulator.active_case_count, 0)
                self.assertEqual(authority.retained_canonical_material, ())
                self.assertEqual(authority.sealed_run_ids, ())
    def test_complete_multi_candidate_discovery_is_atomic_and_has_no_early_exit(
        self,
    ) -> None:
        batch = two_candidate_discovery_batch()
        store = InMemoryCaseAccumulator()
        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "discovery_coordinator_required",
        ):
            store.apply_mutation(batch.mutations[0])
        partial = SearchEvaluationBatch(batch.run, batch.mutations[:1])
        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "search_batch_scope_order_parity",
        ):
            store.state.apply_discovery_batch(
                partial,
                candidate_evaluations=selector_evaluations(batch),
            )

        first = store.apply_discovery_batch(batch)
        replay = store.apply_discovery_batch(batch)
        self.assertEqual(len(first), 2)
        self.assertTrue(all(not item.replayed for item in first))
        self.assertTrue(all(item.replayed for item in replay))
        self.assertEqual(store.active_case_count, 2)
        for mutation_value in batch.mutations:
            case = store.get_active_case(mutation_value.order_id)
            self.assertIsNotNone(case)
            self.assertEqual(case.snapshot_ids, (mutation_value.snapshots[0].snapshot_id,))

    def test_candidate_interaction_scope_is_owned_by_the_native_selector(self) -> None:
        batch = two_candidate_discovery_batch()
        crossed = batch.mutations[1].interactions
        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "mutation_discovery_interactions",
        ):
            replace(batch.mutations[0], interactions=crossed)

    def test_existing_interaction_only_case_cannot_bypass_discovery(self) -> None:
        store = InMemoryCaseAccumulator()
        store.apply_mutation(mutation("AUTHORITY-SEED-001"))
        favorable = evaluated_mutation("AUTHORITY-FAVORABLE-001")
        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "discovery_authority_missing",
        ):
            store.apply_mutation(replace(favorable, discovery_run=None))

    def test_unsearched_interaction_cannot_influence_later_evaluation(self) -> None:
        store = InMemoryCaseAccumulator()
        first = evaluated_mutation("AUTHORIZED-INTERACTION-001")
        store.apply_mutation(first)
        other = interaction("002", email_local="unsearched")
        prior = first.snapshots[0]
        captured_at = ts("2026-08-02T15:30:00Z")
        source_ref = EvidenceId("SYN-EVIDENCE-UNSEARCHED-SOURCE-001")
        current = replace(
            prior,
            snapshot_id=SnapshotId("SYN-SNAPSHOT-UNSEARCHED-001"),
            captured_at=captured_at,
            source_ref=source_ref,
            provenance=order_provenance_binding(
                source_ref=source_ref,
                captured_at=captured_at,
                parser=prior.parser,
            ),
        )
        evaluated_at = ts("2026-08-02T16:00:00Z")
        claimed = evaluate_sales_credit(
            evaluation_id=EvaluationId("SYN-EVALUATION-UNSEARCHED-001"),
            expected_order_id=first.order_id,
            snapshot=current,
            evaluated_at=evaluated_at,
            known_other_reps=KNOWN_OTHER_REP_CATALOG,
            interactions=(*first.interactions, other),
            prior_snapshots=(prior,),
        )
        command = CaseMutation(
            command_id=EvidenceId("SYN-EVIDENCE-UNSEARCHED-COMMAND-001"),
            order_id=first.order_id,
            occurred_at=evaluated_at,
            interactions=(*first.interactions, other),
            snapshots=(current,),
            evaluation=claimed,
        )
        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "discovery_interaction_unauthorized",
        ):
            store.apply_mutation(command)

    def test_run_identity_rejects_changed_material_across_fresh_commands(self) -> None:
        store = InMemoryCaseAccumulator()
        normal = evaluated_mutation("RUN-IDENTITY-NORMAL-001")
        store.apply_mutation(normal)
        changed_run = replace(
            normal.discovery_run,
            completed_at=ts("2026-08-01T15:41:00Z"),
        )
        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "search_run_material_conflict",
        ):
            store.apply_mutation(
                replace(
                    normal,
                    command_id=EvidenceId(
                        "SYN-EVIDENCE-RUN-IDENTITY-NORMAL-002"
                    ),
                    occurred_at=ts("2026-08-01T17:00:00Z"),
                    discovery_run=changed_run,
                )
            )

        parent, replacement_command = replacement_evaluated_mutations(
            "RUN-IDENTITY-REPLACEMENT-001"
        )
        replacement_store = InMemoryCaseAccumulator()
        replacement_store.apply_mutation(parent)
        replacement_store.apply_mutation(replacement_command)
        changed_replacement_run = replace(
            replacement_command.replacement_run,
            completed_at=ts("2026-08-02T15:22:00Z"),
        )
        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "search_run_material_conflict",
        ):
            replacement_store.apply_mutation(
                replace(
                    replacement_command,
                    command_id=EvidenceId(
                        "SYN-EVIDENCE-RUN-IDENTITY-REPLACEMENT-002"
                    ),
                    occurred_at=ts("2026-08-02T16:01:00Z"),
                    replacement_run=changed_replacement_run,
                )
            )

    def test_global_evaluation_id_conflict_rolls_back_the_entire_batch(self) -> None:
        authority = InMemorySearchRunAuthority()
        store = InMemoryCaseAccumulator(search_run_authority=authority)
        batch = two_candidate_discovery_batch()
        first, second = batch.mutations
        duplicated_evaluation = evaluate_sales_credit(
            evaluation_id=first.evaluation.evaluation_id,  # type: ignore[union-attr]
            expected_order_id=second.order_id,
            snapshot=second.snapshots[0],
            evaluated_at=second.occurred_at,
            known_other_reps=KNOWN_OTHER_REP_CATALOG,
            interactions=second.interactions,
        )
        crossed = SearchEvaluationBatch(
            batch.run,
            (first, replace(second, evaluation=duplicated_evaluation)),
        )

        with self.assertRaisesRegex(CaseAccumulatorError, "evaluation_conflict"):
            store.apply_discovery_batch(crossed)
        self.assertEqual(store.active_case_count, 0)
        self.assertEqual(store.closed_case_count, 0)
        self.assertEqual(authority.retained_canonical_material, ())

    def test_global_evidence_id_conflict_rolls_back_the_entire_batch(self) -> None:
        authority = InMemorySearchRunAuthority()
        store = InMemoryCaseAccumulator(search_run_authority=authority)
        batch = two_candidate_discovery_batch()
        shared_evidence_id = EvidenceId("SYN-EVIDENCE-GLOBAL-EVENT-001")
        enriched: list[CaseMutation] = []
        for index, mutation_value in enumerate(batch.mutations, start=1):
            interaction_value = mutation_value.interactions[0]
            event = EvidenceEvent(
                evidence_id=shared_evidence_id,
                order_id=mutation_value.order_id,
                interaction_id=interaction_value.interaction_id,
                source_type=EvidenceSourceType.SYNTHETIC_CONVERSATION,
                source_ref=EvidenceId(
                    f"SYN-EVIDENCE-GLOBAL-EVENT-SOURCE-{index:03d}"
                ),
                occurred_at=ts("2026-08-01T13:00:00Z"),
                timestamp_precision=TimestampPrecision.EXACT,
                direction=EvidenceDirection.TWO_WAY,
                target_rep_participated=True,
                connected=True,
                two_way=True,
                identifier_kind=EvidenceIdentifierKind.EMAIL,
                matched_identifier_ref=evidence_identifier_binding(
                    interaction_id=interaction_value.interaction_id,
                    identifier_kind=EvidenceIdentifierKind.EMAIL,
                ),
                timing=EvidenceTimingRelation.PRE_ORDER,
            )
            evaluation_value = evaluate_sales_credit(
                evaluation_id=mutation_value.evaluation.evaluation_id,  # type: ignore[union-attr]
                expected_order_id=mutation_value.order_id,
                snapshot=mutation_value.snapshots[0],
                evaluated_at=mutation_value.occurred_at,
                known_other_reps=KNOWN_OTHER_REP_CATALOG,
                interactions=mutation_value.interactions,
                evidence_events=(event,),
            )
            enriched.append(
                replace(
                    mutation_value,
                    evidence=(event,),
                    evaluation=evaluation_value,
                )
            )
        crossed = SearchEvaluationBatch(batch.run, tuple(enriched))

        with self.assertRaisesRegex(CaseAccumulatorError, "evidence_conflict"):
            store.apply_discovery_batch(crossed)
        self.assertEqual(store.active_case_count, 0)
        self.assertEqual(store.closed_case_count, 0)
        self.assertEqual(authority.retained_canonical_material, ())

    def test_global_interaction_id_allows_exact_material_only(self) -> None:
        batch = two_candidate_discovery_batch()
        shared = batch.mutations[0].interactions[0]

        exact_store = InMemoryCaseAccumulator()
        exact_store.apply_discovery_batch(batch)
        exact_store.apply_mutation(
            evaluated_mutation_for_interaction(
                command_suffix="GLOBAL-INTERACTION-EXACT-001",
                interaction_value=shared,
            )
        )
        self.assertEqual(exact_store.active_case_count, 3)

        authority = InMemorySearchRunAuthority()
        conflict_store = InMemoryCaseAccumulator(search_run_authority=authority)
        conflict_store.apply_discovery_batch(batch)
        changed = replace(shared, active_notes="synthetic: changed shared interaction")
        with self.assertRaisesRegex(CaseAccumulatorError, "interaction_conflict"):
            conflict_store.apply_mutation(
                evaluated_mutation_for_interaction(
                    command_suffix="GLOBAL-INTERACTION-CONFLICT-001",
                    interaction_value=changed,
                )
            )
        self.assertEqual(conflict_store.active_case_count, 2)
        self.assertEqual(authority.retained_canonical_material, ())
        self.assertEqual(authority.sealed_run_ids, (batch.run.run_id,))

    def test_composed_ledgers_reject_changed_shared_run_id(self) -> None:
        authority = InMemorySearchRunAuthority()
        store = InMemoryCaseAccumulator(search_run_authority=authority)
        batch = two_candidate_discovery_batch()
        store.apply_discovery_batch(batch)
        changed = replace(
            batch.run,
            native_result_sets=tuple(
                replace(result, order_ids=())
                for result in batch.run.native_result_sets
            ),
        )

        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "search_run_material_conflict",
        ):
            store.state.apply_discovery_batch(
                SearchEvaluationBatch(changed, ()),
                candidate_evaluations=(),
            )
        self.assertEqual(store.state.no_order_ledger.retained_interactions, ())
        self.assertEqual(store.active_case_count, 2)
        self.assertEqual(authority.retained_canonical_material, ())
        self.assertEqual(authority.sealed_run_ids, (batch.run.run_id,))

    def test_run_material_retires_after_last_case_and_purges_after_last_projection(
        self,
    ) -> None:
        authority = InMemorySearchRunAuthority()
        store = InMemoryCaseAccumulator(search_run_authority=authority)
        batch = two_candidate_discovery_batch()
        store.apply_discovery_batch(batch)
        first, second = batch.mutations

        store.close_and_minimize(
            command_id=EvidenceId("SYN-EVIDENCE-BATCH-CLOSE-001"),
            order_id=first.order_id,
            closed_at=ts("2026-08-10T18:00:00Z"),
            reasons=first.evaluation.reasons,  # type: ignore[union-attr]
        )
        self.assertEqual(authority.retained_canonical_material, ())
        self.assertEqual(authority.sealed_run_ids, (batch.run.run_id,))
        self.assertEqual(authority.retired_run_ids, ())

        store.close_and_minimize(
            command_id=EvidenceId("SYN-EVIDENCE-BATCH-CLOSE-002"),
            order_id=second.order_id,
            closed_at=ts("2026-08-03T18:00:00Z"),
            reasons=second.evaluation.reasons,  # type: ignore[union-attr]
        )
        self.assertEqual(authority.retained_canonical_material, ())
        self.assertEqual(authority.sealed_run_ids, (batch.run.run_id,))
        self.assertEqual(authority.retired_run_ids, ())

        self.assertEqual(store.purge(now=ts("2026-11-01T18:00:00Z")), 1)
        self.assertEqual(authority.sealed_run_ids, (batch.run.run_id,))
        self.assertEqual(store.purge(now=ts("2026-11-08T18:00:00Z")), 1)
        self.assertEqual(authority.sealed_run_ids, ())

    def test_search_authority_precedes_command_and_every_discovered_order(self) -> None:
        command = evaluated_mutation("SEARCH-CHRONOLOGY-001")
        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "mutation_search_not_completed",
        ):
            replace(command, occurred_at=ts("2026-08-01T15:39:59Z"))

        snapshot = command.snapshots[0]
        future_snapshot = replace(
            snapshot,
            placed_at=ts("2026-08-01T15:41:00Z"),
            captured_at=ts("2026-08-01T15:42:00Z"),
            provenance=order_provenance_binding(
                source_ref=snapshot.source_ref,
                captured_at=ts("2026-08-01T15:42:00Z"),
                parser=snapshot.parser,
            ),
        )
        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "mutation_order_after_search",
        ):
            replace(command, snapshots=(future_snapshot,), evaluation=None)

        _, replacement = replacement_evaluated_mutations(
            "SEARCH-CHRONOLOGY-REPLACEMENT-001"
        )
        candidate_input = replacement.replacement_candidates[0]
        future_candidate = replace(
            candidate_input,
            snapshot=replace(
                candidate_input.snapshot,
                placed_at=ts("2026-08-02T15:22:00Z"),
            ),
        )
        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "mutation_order_after_search",
        ):
            replace(
                replacement,
                replacement_candidates=(future_candidate,),
            )


class OutcomeClosureAndPurgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryCaseAccumulator()
        self.mutation = evaluated_mutation()
        self.store.apply_mutation(self.mutation)

    def test_manager_outcome_is_separate_replay_safe_and_blocks_later_mutation(self) -> None:
        command_id = EvidenceId("SYN-EVIDENCE-OUTCOME-COMMAND-001")
        outcome = manager_outcome()
        first = self.store.apply_manager_outcome(
            command_id=command_id,
            order_id=self.mutation.order_id,
            outcome=outcome,
        )
        replay = self.store.apply_manager_outcome(
            command_id=command_id,
            order_id=self.mutation.order_id,
            outcome=outcome,
        )
        occurrence_replay = self.store.apply_manager_outcome(
            command_id=EvidenceId("SYN-EVIDENCE-OUTCOME-COMMAND-REPLAY-002"),
            order_id=self.mutation.order_id,
            outcome=outcome,
        )
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        self.assertTrue(occurrence_replay.replayed)
        self.assertIs(first.state, replay.state)
        self.assertIs(first.state, occurrence_replay.state)
        self.assertIs(first.state.workflow_state, WorkflowState.CLOSED)
        self.assertIs(first.state.human_outcome, outcome.outcome)
        with self.assertRaisesRegex(CaseAccumulatorError, "resolved_case_mutation"):
            self.store.apply_mutation(
                mutation(
                    "COMMAND-AFTER-OUTCOME",
                    occurred_at="2026-08-03T00:00:00Z",
                    interactions=(interaction("002", email_local="later"),),
                )
            )

    def test_manager_occurrence_cannot_be_duplicated_across_order_cases(self) -> None:
        batch = two_candidate_discovery_batch()
        human_mutations: list[CaseMutation] = []
        for mutation_value in batch.mutations:
            snapshot_value = replace(
                mutation_value.snapshots[0],
                raw_order_rep="synthetic_other_rep",
            )
            evaluation = evaluate_sales_credit(
                evaluation_id=mutation_value.evaluation.evaluation_id,
                expected_order_id=mutation_value.order_id,
                snapshot=snapshot_value,
                evaluated_at=mutation_value.occurred_at,
                known_other_reps=KNOWN_OTHER_REP_CATALOG,
                interactions=mutation_value.interactions,
            )
            human_mutations.append(
                replace(
                    mutation_value,
                    snapshots=(snapshot_value,),
                    evaluation=evaluation,
                )
            )
        human_batch = SearchEvaluationBatch(batch.run, tuple(human_mutations))
        self.store.apply_discovery_batch(human_batch)
        shared_outcome = manager_outcome("SHARED-OCCURRENCE-001")
        self.store.apply_manager_outcome(
            command_id=EvidenceId("SYN-EVIDENCE-SHARED-OUTCOME-COMMAND-001"),
            order_id=human_batch.mutations[0].order_id,
            outcome=shared_outcome,
        )
        second_before = self.store.get_active_case(
            human_batch.mutations[1].order_id
        )
        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "outcome_occurrence_conflict",
        ):
            self.store.apply_manager_outcome(
                command_id=EvidenceId(
                    "SYN-EVIDENCE-SHARED-OUTCOME-COMMAND-002"
                ),
                order_id=human_batch.mutations[1].order_id,
                outcome=shared_outcome,
            )
        self.assertIs(
            self.store.get_active_case(human_batch.mutations[1].order_id),
            second_before,
        )

    def test_manager_outcome_requires_a_workflow_with_a_human_exit(self) -> None:
        store = InMemoryCaseAccumulator()
        awaiting = mutation()
        store.apply_mutation(awaiting)
        prior = store.get_active_case(awaiting.order_id)
        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "outcome_workflow_not_authorized",
        ):
            store.apply_manager_outcome(
                command_id=EvidenceId("SYN-EVIDENCE-OUTCOME-AWAITING"),
                order_id=awaiting.order_id,
                outcome=manager_outcome(),
            )
        self.assertIs(store.get_active_case(awaiting.order_id), prior)

    def test_terminal_system_case_cannot_reopen_and_can_only_close(self) -> None:
        store = InMemoryCaseAccumulator()
        parent = evaluated_mutation(
            "TERMINAL-PARENT-COMMAND-001",
            occurred_at="2026-08-01T16:00:00Z",
            canceled=True,
        )
        store.apply_mutation(parent)
        replacement_run = search_run(
            suffix="TERMINAL-REPLACEMENT-CHECK-001",
            interactions=parent.interactions,
            order_ids=(),
            trigger=SearchTriggerType.REPLACEMENT_CHECK,
            started_at="2026-08-16T14:00:00Z",
            completed_at="2026-08-16T14:01:00Z",
        )
        terminal_evaluation = evaluate_sales_credit(
            evaluation_id=EvaluationId("SYN-EVALUATION-TERMINAL-001"),
            expected_order_id=parent.order_id,
            snapshot=parent.snapshots[0],
            evaluated_at=ts("2026-08-16T16:00:00Z"),
            known_other_reps=KNOWN_OTHER_REP_CATALOG,
            interactions=parent.interactions,
            replacement_run=replacement_run,
        )
        terminal = CaseMutation(
            command_id=EvidenceId("SYN-EVIDENCE-TERMINAL-COMMAND-001"),
            order_id=parent.order_id,
            occurred_at=ts("2026-08-16T16:00:00Z"),
            interactions=parent.interactions,
            evaluation=terminal_evaluation,
            replacement_run=replacement_run,
        )
        accepted = store.apply_mutation(terminal)
        self.assertIs(
            accepted.state.workflow_state,
            WorkflowState.CANCELED_NO_REPLACEMENT,
        )
        with self.assertRaisesRegex(CaseAccumulatorError, "terminal_case_mutation"):
            store.apply_mutation(
                mutation(
                    "TERMINAL-REOPEN-001",
                    occurred_at="2026-08-17T16:00:00Z",
                )
            )
        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "outcome_workflow_not_authorized",
        ):
            store.apply_manager_outcome(
                command_id=EvidenceId("SYN-EVIDENCE-TERMINAL-OUTCOME-001"),
                order_id=terminal.order_id,
                outcome=manager_outcome(
                    decided_at="2026-08-17T16:00:00Z",
                    recorded_at="2026-08-17T16:01:00Z",
                ),
            )
        closed = store.close_and_minimize(
            command_id=EvidenceId("SYN-EVIDENCE-TERMINAL-CLOSE-001"),
            order_id=terminal.order_id,
            closed_at=ts("2026-08-17T17:00:00Z"),
            reasons=terminal.evaluation.reasons,  # type: ignore[union-attr]
        )
        self.assertIs(
            closed.projection.record.system_workflow_before_close,
            WorkflowState.CANCELED_NO_REPLACEMENT,
        )

    def test_automatic_favorable_classification_may_close_without_human_outcome(self) -> None:
        store = InMemoryCaseAccumulator()
        command = evaluated_mutation("AUTO-CLOSE-COMMAND-001")
        result = store.apply_mutation(command)
        self.assertIs(
            result.state.workflow_state,
            WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
        )
        closed = store.close_and_minimize(
            command_id=EvidenceId("SYN-EVIDENCE-AUTO-CLOSE-001"),
            order_id=command.order_id,
            closed_at=ts("2026-08-02T16:00:00Z"),
            reasons=command.evaluation.reasons,  # type: ignore[union-attr]
        )
        self.assertIsNone(closed.projection.record.human_outcome)

    def test_open_replacement_window_cannot_be_truncated_by_value_review(self) -> None:
        store = InMemoryCaseAccumulator()
        command = evaluated_mutation("OPEN-WINDOW-VALUE-001", canceled=True)
        changed_snapshot = replace(
            command.snapshots[0],
            material_changes=(
                MaterialChange(
                    EvidenceId("SYN-EVIDENCE-OPEN-WINDOW-CHANGE-001"),
                    MaterialChangeKind.PRICE_ADJUSTMENT,
                    True,
                ),
            ),
        )
        evaluation = evaluate_sales_credit(
            evaluation_id=EvaluationId("SYN-EVALUATION-OPEN-WINDOW-VALUE-001"),
            expected_order_id=command.order_id,
            snapshot=changed_snapshot,
            evaluated_at=command.occurred_at,
            known_other_reps=KNOWN_OTHER_REP_CATALOG,
            interactions=command.interactions,
        )
        command = replace(
            command,
            snapshots=(changed_snapshot,),
            evaluation=evaluation,
        )
        result = store.apply_mutation(command)
        self.assertIs(
            result.state.workflow_state,
            WorkflowState.ORDER_CHANGED_HUMAN_REVIEW,
        )
        self.assertIs(
            evaluation.replacement.status,
            ReplacementStatus.WINDOW_ACTIVE,
        )
        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "outcome_replacement_window_active",
        ):
            store.apply_manager_outcome(
                command_id=EvidenceId("SYN-EVIDENCE-OPEN-WINDOW-OUTCOME-001"),
                order_id=command.order_id,
                outcome=manager_outcome("OPEN-WINDOW-OUTCOME-001"),
            )
        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "closure_replacement_window_active",
        ):
            store.close_and_minimize(
                command_id=EvidenceId("SYN-EVIDENCE-OPEN-WINDOW-CLOSE-001"),
                order_id=command.order_id,
                closed_at=ts("2026-08-02T16:00:00Z"),
                reasons=evaluation.reasons,
            )
        active = store.get_active_case(command.order_id)
        self.assertIsNotNone(active)
        self.assertIs(active.workflow_state, result.state.workflow_state)

    def test_incomplete_replacement_search_cannot_truncate_open_window(self) -> None:
        store = InMemoryCaseAccumulator(
            search_run_authority=InMemorySearchRunAuthority()
        )
        parent, replacement = replacement_evaluated_mutations(
            "OPEN-WINDOW-INCOMPLETE-001"
        )
        incomplete_run = replace(
            replacement.replacement_run,
            native_result_sets=tuple(
                replace(
                    result,
                    completeness=SearchCompleteness.INCOMPLETE,
                    order_ids=(),
                )
                for result in replacement.replacement_run.native_result_sets
            ),
        )
        evaluation = evaluate_sales_credit(
            evaluation_id=EvaluationId("SYN-EVALUATION-OPEN-WINDOW-INCOMPLETE-001"),
            expected_order_id=parent.order_id,
            snapshot=parent.snapshots[0],
            evaluated_at=replacement.occurred_at,
            known_other_reps=KNOWN_OTHER_REP_CATALOG,
            interactions=replacement.interactions,
            replacement_run=incomplete_run,
        )
        blocked = replace(
            replacement,
            command_id=EvidenceId(
                "SYN-EVIDENCE-OPEN-WINDOW-INCOMPLETE-COMMAND-001"
            ),
            evaluation=evaluation,
            replacement_run=incomplete_run,
            replacement_candidates=(),
        )
        store.apply_mutation(parent)
        result = store.apply_mutation(blocked)
        self.assertIs(
            result.state.workflow_state,
            WorkflowState.MANUAL_REVIEW_REQUIRED,
        )
        self.assertIs(evaluation.replacement.status, ReplacementStatus.BLOCKED)
        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "outcome_replacement_window_active",
        ):
            store.apply_manager_outcome(
                command_id=EvidenceId(
                    "SYN-EVIDENCE-OPEN-WINDOW-INCOMPLETE-OUTCOME-001"
                ),
                order_id=parent.order_id,
                outcome=manager_outcome("OPEN-WINDOW-INCOMPLETE-OUTCOME-001"),
            )
        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "closure_replacement_window_active",
        ):
            store.close_and_minimize(
                command_id=EvidenceId(
                    "SYN-EVIDENCE-OPEN-WINDOW-INCOMPLETE-CLOSE-001"
                ),
                order_id=parent.order_id,
                closed_at=ts("2026-08-02T18:00:00Z"),
                reasons=evaluation.reasons,
            )

    def test_missing_case_and_second_distinct_outcome_fail_without_new_state(self) -> None:
        with self.assertRaisesRegex(CaseAccumulatorError, "outcome_case_missing"):
            self.store.apply_manager_outcome(
                command_id=EvidenceId("SYN-EVIDENCE-OUTCOME-MISSING"),
                order_id=OrderId("SYN-ORDER-MISSING"),
                outcome=manager_outcome(),
            )
        self.store.apply_manager_outcome(
            command_id=EvidenceId("SYN-EVIDENCE-OUTCOME-COMMAND-001"),
            order_id=self.mutation.order_id,
            outcome=manager_outcome(),
        )
        closed_case = self.store.get_active_case(self.mutation.order_id)
        with self.assertRaisesRegex(CaseAccumulatorError, "outcome_already_recorded"):
            self.store.apply_manager_outcome(
                command_id=EvidenceId("SYN-EVIDENCE-OUTCOME-COMMAND-002"),
                order_id=self.mutation.order_id,
                outcome=manager_outcome("OUTCOME-002"),
            )
        self.assertIs(self.store.get_active_case(self.mutation.order_id), closed_case)

    def test_manager_outcome_may_not_regress_case_time(self) -> None:
        self.store.apply_mutation(
            mutation(
                "COMMAND-002",
                occurred_at="2026-08-03T12:00:00Z",
                interactions=(interaction(),),
            )
        )
        prior = self.store.get_active_case(self.mutation.order_id)
        with self.assertRaises(CaseAccumulatorError):
            self.store.apply_manager_outcome(
                command_id=EvidenceId("SYN-EVIDENCE-OUTCOME-EARLY"),
                order_id=self.mutation.order_id,
                outcome=manager_outcome(
                    decided_at="2026-08-02T10:00:00Z",
                    recorded_at="2026-08-02T11:00:00Z",
                ),
            )
        self.assertIs(self.store.get_active_case(self.mutation.order_id), prior)

        with self.assertRaisesRegex(CaseAccumulatorError, "outcome_time_regression"):
            self.store.apply_manager_outcome(
                command_id=EvidenceId("SYN-EVIDENCE-OUTCOME-EARLY-DECISION"),
                order_id=self.mutation.order_id,
                outcome=manager_outcome(
                    decided_at="2026-08-03T11:59:59.999999999Z",
                    recorded_at="2026-08-03T13:00:00Z",
                ),
            )
        self.assertIs(self.store.get_active_case(self.mutation.order_id), prior)

    def test_closure_is_atomic_minimization_and_exact_replay(self) -> None:
        self.store.apply_manager_outcome(
            command_id=EvidenceId("SYN-EVIDENCE-OUTCOME-COMMAND-001"),
            order_id=self.mutation.order_id,
            outcome=manager_outcome(),
        )
        command_id = EvidenceId("SYN-EVIDENCE-CLOSE-COMMAND-001")
        reasons = self.mutation.evaluation.reasons  # type: ignore[union-attr]
        first = self.store.close_and_minimize(
            command_id=command_id,
            order_id=self.mutation.order_id,
            closed_at=ts("2026-08-03T00:00:00Z"),
            reasons=reasons,
        )
        replay = self.store.close_and_minimize(
            command_id=command_id,
            order_id=self.mutation.order_id,
            closed_at=ts("2026-08-03T00:00:00Z"),
            reasons=reasons,
        )
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        self.assertIs(first.projection, replay.projection)
        self.assertIsNone(self.store.get_active_case(self.mutation.order_id))
        self.assertIs(
            self.store.get_closed_projection(self.mutation.order_id),
            first.projection,
        )
        self.assertEqual(self.store.active_case_count, 0)
        self.assertEqual(self.store.closed_case_count, 1)
        self.assertEqual(first.projection.interactions_removed, 1)
        self.assertEqual(
            tuple(item.value for item in first.projection.record.reasons),
            (
                "PLACED_VALUE_PROVED",
                "TARGET_REP",
            ),
        )

    def test_sealed_search_partition_rejects_a_late_foreign_owner(
        self,
    ) -> None:
        authority = InMemorySearchRunAuthority()
        store = InMemoryCaseAccumulator(search_run_authority=authority)
        command = evaluated_mutation("SHARED-RETIRE-001")
        store.apply_mutation(command)
        foreign_owner = authority.new_owner()
        with self.assertRaisesRegex(
            SearchRunAuthorityError,
            "search_run_sealed_owner",
        ):
            authority.claim(command.discovery_run, owner=foreign_owner)
        close_kwargs = {
            "command_id": EvidenceId("SYN-EVIDENCE-SHARED-RETIRE-CLOSE-001"),
            "order_id": command.order_id,
            "closed_at": ts("2026-08-03T00:00:00Z"),
            "reasons": command.evaluation.reasons,  # type: ignore[union-attr]
        }

        closed = store.close_and_minimize(**close_kwargs)
        self.assertFalse(closed.replayed)
        self.assertIsNone(store.get_active_case(command.order_id))
        self.assertEqual(authority.retained_canonical_material, ())
        self.assertEqual(
            authority.sealed_run_ids,
            (command.discovery_run.run_id,),  # type: ignore[union-attr]
        )

    def test_closure_reasons_are_an_equality_assertion_not_caller_authority(self) -> None:
        self.store.apply_manager_outcome(
            command_id=EvidenceId("SYN-EVIDENCE-OUTCOME-COMMAND-001"),
            order_id=self.mutation.order_id,
            outcome=manager_outcome(),
        )
        prior = self.store.get_active_case(self.mutation.order_id)
        with self.assertRaisesRegex(CaseAccumulatorError, "closure_reason_mismatch"):
            self.store.close_and_minimize(
                command_id=EvidenceId("SYN-EVIDENCE-CLOSE-FORGED-001"),
                order_id=self.mutation.order_id,
                closed_at=ts("2026-08-03T00:00:00Z"),
                reasons=(SalesCreditReason.AMBIGUOUS_FACTS_REQUIRE_HUMAN_REVIEW,),
            )
        self.assertIs(self.store.get_active_case(self.mutation.order_id), prior)

    def test_failed_closure_rolls_back_and_same_command_can_retry(self) -> None:
        prior = self.store.get_active_case(self.mutation.order_id)
        command_id = EvidenceId("SYN-EVIDENCE-CLOSE-COMMAND-FAIL")
        with self.assertRaises(ValueError):
            self.store.close_and_minimize(
                command_id=command_id,
                order_id=self.mutation.order_id,
                closed_at=ts("2026-07-31T00:00:00Z"),
                reasons=self.mutation.evaluation.reasons,  # type: ignore[union-attr]
            )
        self.assertIs(self.store.get_active_case(self.mutation.order_id), prior)
        self.assertEqual(self.store.closed_case_count, 0)

        self.store.apply_manager_outcome(
            command_id=EvidenceId("SYN-EVIDENCE-OUTCOME-COMMAND-001"),
            order_id=self.mutation.order_id,
            outcome=manager_outcome(),
        )
        accepted = self.store.close_and_minimize(
            command_id=command_id,
            order_id=self.mutation.order_id,
            closed_at=ts("2026-08-03T00:00:00Z"),
            reasons=self.mutation.evaluation.reasons,  # type: ignore[union-attr]
        )
        self.assertFalse(accepted.replayed)

    def test_purge_boundary_is_idempotent_and_deletes_identity_receipts(self) -> None:
        self.store.apply_manager_outcome(
            command_id=EvidenceId("SYN-EVIDENCE-OUTCOME-COMMAND-001"),
            order_id=self.mutation.order_id,
            outcome=manager_outcome(),
        )
        close_command = EvidenceId("SYN-EVIDENCE-CLOSE-COMMAND-001")
        self.store.close_and_minimize(
            command_id=close_command,
            order_id=self.mutation.order_id,
            closed_at=ts("2026-08-03T00:00:00.000000001Z"),
            reasons=self.mutation.evaluation.reasons,  # type: ignore[union-attr]
        )
        self.assertEqual(
            self.store.purge(now=ts("2026-11-01T00:00:00Z")),
            0,
        )
        self.assertEqual(
            self.store.purge(now=ts("2026-11-01T00:00:00.000000001Z")),
            1,
        )
        self.assertEqual(self.store.purge(now=ts("2026-11-02T00:00:00Z")), 0)
        self.assertIsNone(self.store.get_closed_projection(self.mutation.order_id))
        self.assertEqual(self.store.closed_case_count, 0)
        with self.assertRaisesRegex(CaseAccumulatorError, "closure_case_missing"):
            self.store.close_and_minimize(
                command_id=close_command,
                order_id=self.mutation.order_id,
                closed_at=ts("2026-08-03T00:00:00.000000001Z"),
                reasons=(),
            )

    def test_closure_deletes_active_detail_receipts_but_retains_its_own_replay(self) -> None:
        outcome_command = EvidenceId("SYN-EVIDENCE-OUTCOME-COMMAND-001")
        outcome_value = manager_outcome()
        mutation_canonical = self.mutation.canonical_bytes()
        mutation_unkeyed_digest = hashlib.sha256(
            CaseMutation.HASH_DOMAIN.encode("ascii")
            + b"\n"
            + mutation_canonical
        ).hexdigest()
        mutation_before_close = self.store.apply_mutation(self.mutation)
        active_receipt = self.store.case_accumulator._receipts[
            self.mutation.command_id.value
        ]
        self.assertFalse(hasattr(active_receipt, "canonical_bytes"))
        self.assertFalse(hasattr(active_receipt, "command_sha256"))
        outcome_before_close = self.store.apply_manager_outcome(
            command_id=outcome_command,
            order_id=self.mutation.order_id,
            outcome=outcome_value,
        )
        close_command = EvidenceId("SYN-EVIDENCE-CLOSE-COMMAND-001")
        close_kwargs = {
            "command_id": close_command,
            "order_id": self.mutation.order_id,
            "closed_at": ts("2026-08-03T00:00:00Z"),
            "reasons": self.mutation.evaluation.reasons,  # type: ignore[union-attr]
        }
        first = self.store.close_and_minimize(**close_kwargs)
        accumulator = self.store.case_accumulator
        self.assertEqual(accumulator._receipts, {})
        self.assertEqual(accumulator._run_receipts, {})
        self.assertEqual(
            accumulator.search_run_authority.retained_canonical_material,
            (),
        )
        for retained in accumulator._closed_command_authenticators.values():
            self.assertFalse(hasattr(retained, "canonical_bytes"))
            if not isinstance(retained.result, ClosureResult):
                self.assertFalse(hasattr(retained.result, "command_sha256"))
            self.assertNotEqual(
                retained.authenticator.hex(),
                mutation_unkeyed_digest,
            )
            self.assertNotEqual(retained.authenticator, mutation_canonical)

        mutation_replay = self.store.apply_mutation(self.mutation)
        outcome_replay = self.store.apply_manager_outcome(
            command_id=outcome_command,
            order_id=self.mutation.order_id,
            outcome=outcome_value,
        )
        occurrence_replay = self.store.apply_manager_outcome(
            command_id=EvidenceId(
                "SYN-EVIDENCE-OUTCOME-COMMAND-CLOSED-OCCURRENCE-002"
            ),
            order_id=self.mutation.order_id,
            outcome=outcome_value,
        )
        self.assertIsInstance(mutation_replay, type(mutation_before_close))
        self.assertIs(mutation_replay.state, mutation_before_close.state)
        for retired_replay in (outcome_replay, occurrence_replay):
            self.assertIsInstance(retired_replay, type(outcome_before_close))
            self.assertIs(retired_replay.state, outcome_before_close.state)
        for retired_replay in (mutation_replay, outcome_replay, occurrence_replay):
            self.assertTrue(retired_replay.replayed)
            self.assertFalse(hasattr(retired_replay, "case"))
            for prohibited in (
                "active_note",
                "evidence_ids",
                "evaluation_ids",
                "interaction_ids",
                "order_id",
                "placed_value",
                "snapshot_ids",
                "updated_at",
            ):
                self.assertFalse(hasattr(retired_replay.state, prohibited))
        with self.assertRaisesRegex(CaseAccumulatorError, "command_material_conflict"):
            self.store.apply_mutation(
                replace(
                    self.mutation,
                    active_note="synthetic: changed retired command",
                )
            )
        with self.assertRaisesRegex(CaseAccumulatorError, "command_material_conflict"):
            self.store.apply_manager_outcome(
                command_id=outcome_command,
                order_id=self.mutation.order_id,
                outcome=replace(
                    outcome_value,
                    active_note="synthetic: changed retired outcome",
                ),
            )
        with self.assertRaisesRegex(
            CaseAccumulatorError,
            "outcome_occurrence_conflict",
        ):
            self.store.apply_manager_outcome(
                command_id=EvidenceId(
                    "SYN-EVIDENCE-OUTCOME-COMMAND-CLOSED-OCCURRENCE-003"
                ),
                order_id=self.mutation.order_id,
                outcome=replace(
                    outcome_value,
                    active_note="synthetic: changed occurrence material",
                ),
            )
        replay = self.store.close_and_minimize(**close_kwargs)
        self.assertTrue(replay.replayed)
        self.assertIs(replay.projection, first.projection)


if __name__ == "__main__":
    unittest.main()
