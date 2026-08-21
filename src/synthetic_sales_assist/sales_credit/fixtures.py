"""Deterministic synthetic fixtures for Milestone 2 hash known-answer tests."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date

from synthetic_sales_assist.domain.canonical import HashBinding
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
from synthetic_sales_assist.domain.numeric import CURRENCY_REGISTRY_VERSION, Money, Quantity
from synthetic_sales_assist.domain.records import VersionBinding
from synthetic_sales_assist.domain.timestamps import CanonicalTimestamp
from synthetic_sales_assist.sales_credit.accumulator import CaseMutation
from synthetic_sales_assist.sales_credit.discovery import (
    NativeSearchResultSet,
    OrderSearchRun,
    SearchCompleteness,
    SearchIdentifier,
    SearchIdentifierKind,
)
from synthetic_sales_assist.sales_credit.evaluator import (
    KNOWN_OTHER_REP_CATALOG,
    evaluate_sales_credit,
    evidence_identifier_binding,
)
from synthetic_sales_assist.sales_credit.models import (
    SALES_CREDIT_RULE_PACK_VERSION,
    AttributionClassification,
    ClosedAuditRecord,
    ClosedNoteCode,
    EvidenceClassification,
    EvidenceIdentifierKind,
    EvidenceSourceType,
    HumanOutcomeType,
    InteractionRecord,
    LineItemSnapshot,
    ManagerOutcome,
    NotesScanStatus,
    OrderLifecycleStatus,
    OrderSnapshot,
    OrderValueStatus,
    SalesCreditReason,
    SearchTriggerType,
    SnapshotStatus,
    TimestampPrecision,
    WorkflowState,
    order_provenance_binding,
)
from synthetic_sales_assist.sales_credit.retention import NoOrderClosedAuditRecord


_FIXTURE_NAME = re.compile(r"\A[A-Za-z][A-Za-z0-9:._-]{0,95}\Z", re.ASCII)
_INSTANCE_KEY = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z", re.ASCII)


@dataclass(frozen=True, slots=True, repr=False)
class HashOracleFixture:
    """One named hash binding with retained canonical bytes."""

    name: str
    binding: HashBinding

    def __post_init__(self) -> None:
        if type(self.name) is not str or _FIXTURE_NAME.fullmatch(self.name) is None:
            raise ValueError("hash oracle fixture rejected")
        if type(self.binding) is not HashBinding:
            raise ValueError("hash oracle fixture rejected")

    def __repr__(self) -> str:
        return f"HashOracleFixture(name={self.name}, binding=<redacted>)"


def _usd(minor_units: int) -> Money:
    return Money.from_minor_units(
        minor_units,
        currency_code="USD",
        registry_version=CURRENCY_REGISTRY_VERSION,
        scale=2,
    )


def _manager_outcome() -> ManagerOutcome:
    return ManagerOutcome(
        occurrence_id=EvidenceId("SYN-EVIDENCE-M2-MANAGER-0001"),
        outcome=HumanOutcomeType.APPROVED,
        decided_at=CanonicalTimestamp("2026-08-22T15:55:00Z"),
        actor=RepId("SYN-REP-M2-MANAGER-0001"),
        recorded_at=CanonicalTimestamp("2026-08-22T16:00:00Z"),
        approved_amount=_usd(12_345),
        controlled_reason=SalesCreditReason.TARGET_REP,
        active_note=None,
    )


def _closed_audit() -> ClosedAuditRecord:
    return ClosedAuditRecord(
        order_id=OrderId("SYN-ORDER-M2-KAT-0001"),
        opened_at=CanonicalTimestamp("2026-08-20T16:00:00Z"),
        closed_at=CanonicalTimestamp("2026-08-22T16:00:00Z"),
        interaction_precisions=(TimestampPrecision.EXACT,),
        system_workflow_before_close=WorkflowState.CREDIT_CONFIRMED_TARGET_REP,
        attribution=AttributionClassification.TARGET_REP,
        order_value_status=OrderValueStatus.PLACED_VALUE_VERIFIED,
        evidence_source_types=(EvidenceSourceType.SYNTHETIC_EMAIL,),
        evidence_classifications=(EvidenceClassification.VERIFIED_PREORDER_EVIDENCE,),
        reasons=(SalesCreditReason.TARGET_REP,),
        human_outcome=HumanOutcomeType.APPROVED,
        human_decided_at=CanonicalTimestamp("2026-08-22T15:55:00Z"),
        human_recorded_at=CanonicalTimestamp("2026-08-22T16:00:00Z"),
        decision_actor=RepId("SYN-REP-M2-MANAGER-0001"),
        approved_amount=_usd(12_345),
        controlled_reason=SalesCreditReason.TARGET_REP,
        concise_note=ClosedNoteCode.HUMAN_OUTCOME_RECORDED,
        rule_pack_version=SALES_CREDIT_RULE_PACK_VERSION,
    )


def _no_order_closed_audit() -> NoOrderClosedAuditRecord:
    return NoOrderClosedAuditRecord(
        opened_at=CanonicalTimestamp("2026-08-01T14:00:00Z"),
        closed_at=CanonicalTimestamp("2026-08-17T16:00:00.000000001Z"),
        latest_review_window_end=date(2026, 8, 16),
        interaction_count=2,
        interaction_precisions=(
            TimestampPrecision.EXACT,
            TimestampPrecision.HISTORICAL_APPROXIMATION,
        ),
        search_trigger=SearchTriggerType.NORMAL,
        identifiers_required=2,
        identifiers_attempted=2,
        identifiers_completed=2,
        enumeration_complete=True,
        system_workflow_before_close=(
            WorkflowState.REVIEW_WINDOW_CLOSED_NO_ORDER
        ),
        reasons=(SalesCreditReason.NO_ORDER_WINDOW_CLOSED,),
        concise_note=ClosedNoteCode.REVIEW_WINDOW_CLOSED_NO_ORDER,
        search_adapter_version="sales-credit-search-adapter/v1",
        search_run_schema_version="sales-credit-order-search-run/v1",
        rule_pack_version=SALES_CREDIT_RULE_PACK_VERSION,
    )


def milestone2_hash_fixtures() -> tuple[HashOracleFixture, ...]:
    """Return every Milestone 2 hash-bearing fixture in a closed order."""

    captured_at = CanonicalTimestamp("2026-08-21T16:00:00Z")
    parser = VersionBinding("sales_credit_parser", "sales-credit-parser/v1")
    line = LineItemSnapshot.create(
        line_id=EvidenceId("SYN-EVIDENCE-M2-LINE-0001"),
        sku_id=SkuId("SYN-SKU-M2-KAT-0001"),
        quantity=Quantity(2),
        line_value=_usd(2_500),
        raw_es_number="synthetic: ES#000123",
        canonical_es_number="123",
        raw_mfg_oe_number="synthetic: ab-001 / c",
        canonical_mfg_oe_number="AB-001 / C",
    )
    provenance = order_provenance_binding(
        source_ref=EvidenceId("SYN-EVIDENCE-M2-ORDER-SOURCE-0001"),
        captured_at=captured_at,
        parser=parser,
    )
    identifier = evidence_identifier_binding(
        interaction_id=InteractionId("SYN-INTERACTION-M2-KAT-0001"),
        identifier_kind=EvidenceIdentifierKind.EMAIL,
    )
    command = milestone2_case_mutation()
    evaluation = command.evaluation
    if evaluation is None:
        raise RuntimeError("accepted case mutation fixture lacks evaluation")
    manager = _manager_outcome()
    no_order_closed = _no_order_closed_audit()
    closed = _closed_audit()
    fixtures = (
        HashOracleFixture("CaseMutation", command.hash_binding()),
        HashOracleFixture("ClosedAuditRecord", closed.hash_binding()),
        HashOracleFixture("EvidenceIdentifierRef", identifier),
        HashOracleFixture("LineItemContent", line.content),
        HashOracleFixture("ManagerOutcome", manager.hash_binding()),
        HashOracleFixture(
            "NoOrderClosedAuditRecord",
            no_order_closed.hash_binding(),
        ),
        HashOracleFixture("OrderProvenance", provenance),
        HashOracleFixture("SalesCreditEvaluation", evaluation.hash_binding()),
    )
    if tuple(item.name for item in fixtures) != tuple(
        sorted(item.name for item in fixtures)
    ):
        raise RuntimeError("hash fixture inventory order violated")
    return fixtures


def milestone2_case_mutation() -> CaseMutation:
    """Return a complete command accepted by a fresh Milestone 2 accumulator."""

    order_id = OrderId("SYN-ORDER-M2-KAT-0001")
    interaction = InteractionRecord(
        interaction_id=InteractionId("SYN-INTERACTION-M2-KAT-0001"),
        source_ref=EvidenceId("SYN-EVIDENCE-M2-INTERACTION-SOURCE-0001"),
        recorded_at=CanonicalTimestamp("2026-08-20T16:00:00Z"),
        timestamp_precision=TimestampPrecision.EXACT,
        review_window_start=date(2026, 8, 20),
        review_window_end=date(2026, 9, 3),
        workflow_state=WorkflowState.AWAITING_SOURCE_REVIEW,
        provenance=VersionBinding(
            "sales_credit_interaction_source",
            "sales-credit-interaction-source/v1",
        ),
        email="m2-kat@example.test",
    )
    captured_at = CanonicalTimestamp("2026-08-21T16:00:00Z")
    parser = VersionBinding("sales_credit_parser", "sales-credit-parser/v1")
    source_ref = EvidenceId("SYN-EVIDENCE-M2-ORDER-SOURCE-0001")
    line = LineItemSnapshot.create(
        line_id=EvidenceId("SYN-EVIDENCE-M2-LINE-0001"),
        sku_id=SkuId("SYN-SKU-M2-KAT-0001"),
        quantity=Quantity(2),
        line_value=_usd(2_500),
        raw_es_number="synthetic: ES#000123",
        canonical_es_number="123",
        raw_mfg_oe_number="synthetic: ab-001 / c",
        canonical_mfg_oe_number="AB-001 / C",
    )
    snapshot = OrderSnapshot(
        snapshot_id=SnapshotId("SYN-SNAPSHOT-M2-KAT-0001"),
        order_id=order_id,
        source_ref=source_ref,
        captured_at=captured_at,
        parser=parser,
        extraction_status=SnapshotStatus.VALID,
        lifecycle_status=OrderLifecycleStatus.ACTIVE,
        notes_scan_status=NotesScanStatus.COMPLETE,
        placed_at=CanonicalTimestamp("2026-08-21T15:00:00Z"),
        placed_at_precision=TimestampPrecision.EXACT,
        raw_order_status="active",
        raw_order_rep="target_rep",
        current_value=_usd(12_345),
        placed_value=_usd(12_345),
        customer_ids=(CustomerId("SYN-CUSTOMER-M2-KAT-0001"),),
        lines=(line,),
        material_changes=(),
        provenance=order_provenance_binding(
            source_ref=source_ref,
            captured_at=captured_at,
            parser=parser,
        ),
    )
    occurred_at = CanonicalTimestamp("2026-08-21T17:00:00Z")
    search_run = OrderSearchRun(
        run_id=RunId("SYN-RUN-M2-KAT-0001"),
        trigger=SearchTriggerType.NORMAL,
        interactions=(interaction,),
        native_result_sets=(
            NativeSearchResultSet(
                identifier=SearchIdentifier(
                    SearchIdentifierKind.EMAIL,
                    "m2-kat@example.test",
                ),
                completeness=SearchCompleteness.COMPLETE,
                order_ids=(order_id,),
            ),
        ),
        adapter=VersionBinding(
            "sales_credit_search_adapter",
            "sales-credit-search-adapter/v1",
        ),
        started_at=CanonicalTimestamp("2026-08-21T16:15:00Z"),
        completed_at=CanonicalTimestamp("2026-08-21T16:30:00Z"),
    )
    evaluation = evaluate_sales_credit(
        evaluation_id=EvaluationId("SYN-EVALUATION-M2-KAT-0001"),
        expected_order_id=order_id,
        snapshot=snapshot,
        evaluated_at=occurred_at,
        known_other_reps=KNOWN_OTHER_REP_CATALOG,
        interactions=(interaction,),
    )
    return CaseMutation(
        command_id=EvidenceId("SYN-EVIDENCE-M2-COMMAND-0001"),
        order_id=order_id,
        occurred_at=occurred_at,
        interactions=(interaction,),
        snapshots=(snapshot,),
        evaluation=evaluation,
        discovery_run=search_run,
    )


def milestone5_case_fixture(alias: str, instance_key: str) -> CaseMutation:
    """Build one fresh source-bound Sales Credit case without evaluating it."""

    if alias not in {
        "sales-credit-target-rep",
        "sales-credit-human-review",
        "sales-credit-cancellation-replacement",
    }:
        raise KeyError(alias)
    if type(instance_key) is not str or _INSTANCE_KEY.fullmatch(instance_key) is None:
        raise ValueError("SALES_CREDIT_FIXTURE_INSTANCE_INVALID")
    instance = hashlib.sha256(instance_key.encode("ascii")).hexdigest().upper()[:16]
    order_id = OrderId(f"SYN-ORDER-M5-SC-{instance}")
    interaction = InteractionRecord(
        interaction_id=InteractionId(f"SYN-INTERACTION-M5-SC-{instance}"),
        source_ref=EvidenceId(f"SYN-EVIDENCE-M5-SC-INTERACTION-SOURCE-{instance}"),
        recorded_at=CanonicalTimestamp("2026-08-20T16:00:00Z"),
        timestamp_precision=TimestampPrecision.EXACT,
        review_window_start=date(2026, 8, 20),
        review_window_end=date(2026, 9, 3),
        workflow_state=WorkflowState.AWAITING_SOURCE_REVIEW,
        provenance=VersionBinding(
            "sales_credit_interaction_source",
            "sales-credit-interaction-source/v1",
        ),
        email=f"m5-{instance.lower()}@example.test",
    )
    captured_at = CanonicalTimestamp("2026-08-21T16:00:00Z")
    parser = VersionBinding("sales_credit_parser", "sales-credit-parser/v1")
    source_ref = EvidenceId(f"SYN-EVIDENCE-M5-SC-ORDER-SOURCE-{instance}")
    line = LineItemSnapshot.create(
        line_id=EvidenceId(f"SYN-EVIDENCE-M5-SC-LINE-{instance}-0001"),
        sku_id=SkuId(f"SYN-SKU-M5-SC-{instance}-0001"),
        quantity=Quantity(2),
        line_value=_usd(2_500),
        raw_es_number="synthetic: ES#000123",
        canonical_es_number="123",
        raw_mfg_oe_number="synthetic: ab-001 / c",
        canonical_mfg_oe_number="AB-001 / C",
        observed_availability="IN_STOCK",
        observed_eta=CanonicalTimestamp("2026-08-22T16:00:00Z"),
    )
    canceled = alias == "sales-credit-cancellation-replacement"
    snapshot = OrderSnapshot(
        snapshot_id=SnapshotId(f"SYN-SNAPSHOT-M5-SC-{instance}"),
        order_id=order_id,
        source_ref=source_ref,
        captured_at=captured_at,
        parser=parser,
        extraction_status=SnapshotStatus.VALID,
        lifecycle_status=(
            OrderLifecycleStatus.CANCELED if canceled else OrderLifecycleStatus.ACTIVE
        ),
        notes_scan_status=NotesScanStatus.COMPLETE,
        placed_at=CanonicalTimestamp("2026-08-21T15:00:00Z"),
        placed_at_precision=TimestampPrecision.EXACT,
        raw_order_status="canceled" if canceled else "active",
        raw_order_rep=(
            "synthetic_unrecognized_rep"
            if alias == "sales-credit-human-review"
            else "target_rep"
        ),
        current_value=_usd(12_345),
        placed_value=_usd(12_345),
        customer_ids=(CustomerId(f"SYN-CUSTOMER-M5-SC-{instance}"),),
        lines=(line,),
        material_changes=(),
        provenance=order_provenance_binding(
            source_ref=source_ref,
            captured_at=captured_at,
            parser=parser,
        ),
        canceled_at=(
            CanonicalTimestamp("2026-08-21T15:30:00Z") if canceled else None
        ),
    )
    search_run = OrderSearchRun(
        run_id=RunId(f"SYN-RUN-M5-SC-{instance}"),
        trigger=SearchTriggerType.NORMAL,
        interactions=(interaction,),
        native_result_sets=(
            NativeSearchResultSet(
                identifier=SearchIdentifier(
                    SearchIdentifierKind.EMAIL,
                    f"m5-{instance.lower()}@example.test",
                ),
                completeness=SearchCompleteness.COMPLETE,
                order_ids=(order_id,),
            ),
        ),
        adapter=VersionBinding(
            "sales_credit_search_adapter",
            "sales-credit-search-adapter/v1",
        ),
        started_at=CanonicalTimestamp("2026-08-21T16:15:00Z"),
        completed_at=CanonicalTimestamp("2026-08-21T16:30:00Z"),
    )
    return CaseMutation(
        command_id=EvidenceId(f"SYN-EVIDENCE-M5-SC-COMMAND-{instance}"),
        order_id=order_id,
        occurred_at=CanonicalTimestamp("2026-08-21T17:00:00Z"),
        interactions=(interaction,),
        snapshots=(snapshot,),
        evaluation=None,
        discovery_run=search_run,
    )


__all__ = [
    "HashOracleFixture",
    "milestone2_case_mutation",
    "milestone2_hash_fixtures",
    "milestone5_case_fixture",
]
